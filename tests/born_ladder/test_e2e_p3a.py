"""P3a structural I/O checks; synthetic controls are not empirical evidence."""
import copy
import ast
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil

import pytest

from born_ladder.archive import Archive, canonical, sha
from born_ladder import robust_census
from born_ladder.reproduction.census import collection_inputs, original_status
from born_ladder.reproduction.census_comparison import Comparison
from born_ladder.reproduction.census_writers.freeze import order
from born_ladder.reproduction.stage_environment import validate_runtime

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture
def selected_package_path(tmp_path):
    # Bridge only the package selected by this test's interpreter. Exposing its
    # entire site-packages would shadow the managed numerical dependencies.
    bridge=tmp_path/'selected-package';bridge.mkdir()
    (bridge/'born_ladder').symlink_to(Path(robust_census.__file__).resolve().parent)
    return str(bridge)


def test_selected_package_bridge_exposes_only_current_package(selected_package_path):
    bridge=Path(selected_package_path)
    assert [p.name for p in bridge.iterdir()]==['born_ladder']
    assert (bridge/'born_ladder').resolve()==Path(robust_census.__file__).resolve().parent
    result=subprocess.run([sys.executable,'-c',
        'import born_ladder;from pathlib import Path;print(Path(born_ladder.__file__).resolve().parent)'],
        env={**os.environ,'PYTHONPATH':selected_package_path},cwd=ROOT,capture_output=True,text=True,check=True)
    assert result.stdout.strip()==str(Path(robust_census.__file__).resolve().parent)


def test_complete_key_order_and_availability():
    base={'n':32,'retained_rank':2,'source_span_available':True,
          'kernel':{'status':'AVAILABLE'},'immutable_join_verified':True}
    rows=[{**copy.deepcopy(base),'unit_id':str(i),'provenance_key':{'cell':i,'source':{'logical':'capture'}}} for i in range(4)]
    expected=sorted(rows,key=lambda r:(hashlib.sha256(canonical(r['provenance_key'])).hexdigest(),r['unit_id']))
    assert order(rows[::-1])==expected
    for field,value in [('n',31),('retained_rank',3),('source_span_available',False),
                        ('kernel',{'status':'MISSING'}),('immutable_join_verified',False)]:
        altered=copy.deepcopy(rows);altered[0][field]=value
        assert len(order(altered))==3


def test_logical_names_are_checked_not_execution_metadata(tmp_path):
    units=tmp_path/'units';parent=units/'collections/collection_0001/cross-term';parent.mkdir(parents=True)
    stdout=units/'invocations/identity/attempt_0001/stdout.bin';stdout.parent.mkdir(parents=True)
    stdout.write_bytes(b'synthetic capture\n')
    attempt=b'{"synthetic":true}\n';attempt_sha=hashlib.sha256(attempt).hexdigest()
    (stdout.parent/(attempt_sha+'.attempt.json')).write_bytes(attempt)
    structural=parent/'structural.jsonl';structural.write_bytes(b'synthetic structural\n')
    inv=parent/'invocation.json';inv.write_text('[]\n')
    (parent/'units.jsonl').write_text('synthetic units\n')
    campaign={'schema':'born_public_structural_campaign_v1','stdout_execution_bindings':[
        {'invocation_id':'identity','stdout_path':str(stdout.relative_to(units)),
         'stdout_sha256':sha(stdout),'attempt_record_sha256':attempt_sha}],
        'invocation_manifest':{'path':str(inv.relative_to(units)),'sha256':sha(inv)},
        'structural_manifest':{'path':str(structural.relative_to(units)),'sha256':sha(structural)}}
    (parent/'campaign.json').write_text(json.dumps(campaign))
    (parent.parent/'collection.json').write_text(json.dumps({'evaluations':{'cross-term':{
        'path':str(parent.relative_to(units)),'units_file':'units.jsonl','complete':True}}}))
    logical={'schema':'born_census_logical_sources_v1','logical_units_path':'logical/units.jsonl',
        'logical_structural_path':'logical/structural.jsonl','captures':[
            {**campaign['stdout_execution_bindings'][0],'logical_stdout_path':'old/identity/capture.stdout.bin'}]}
    source=tmp_path/'logical.json';source.write_text(json.dumps(logical))
    _,adapted,_,_,files,_,_=collection_inputs(units,'cross-term',source)
    assert adapted['stdout_execution_bindings'][0]['stdout_path']=='old/identity/capture.stdout.bin'
    assert files['old/identity/capture.stdout.bin']==str(stdout)
    logical['captures'][0]['stdout_sha256']='0'*64;source.write_text(json.dumps(logical))
    with pytest.raises(ValueError,match='logical-source hash differs'):
        collection_inputs(units,'cross-term',source)


def test_explicit_archive_view_rejects_escape(tmp_path):
    path=tmp_path/'data';path.write_text('actual execution bytes')
    view=Archive({'schema':'born_structural_input_view_v1','root':str(tmp_path),
                  'files':{'logical/input':str(path)}})
    assert view.path('logical/input').read_text()=='actual execution bytes'
    for name in ('../input','/input'):
        with pytest.raises(ValueError,match='relative'):view.path(name)


def test_integer_frame_and_maximal_gap_tie_rule():
    w=[Fraction(0),Fraction(0),Fraction(-2),Fraction(2)]+[Fraction(0)]*28
    labels=[[0]*4+[1]*28]*3
    r=robust_census.integer_record(w,labels)
    result=robust_census.scan_records([r])
    assert (result['cases'][0]['i'],result['cases'][0]['j'])==(0,2)
    assert result['cases'][0]['gap_exact']=='14/17'
    scaled=robust_census.integer_record([x/Fraction(2**100) for x in w],labels)
    assert [robust_census.point_read(r,i) for i in range(32)]==[robust_census.point_read(scaled,i) for i in range(32)]
    collapsed={**r,'M0':32,'M1':0,'M2':r['S'],'Labels':[[0]*32]*3}
    with pytest.raises(ValueError,match='robust bound failed'):robust_census.scan_records([collapsed])
    assert robust_census.scan_records([collapsed],require_bound=False)['status']=='FAILED'


def test_original_checks_remain_separate_from_completion(monkeypatch):
    from born_ladder.reproduction import census
    completed={'certificates':{'correspondence':{'status':'PASS','constructor_maximum_difference':'1/2',
        'threshold_exact':'1/1000000000000'},'C_premises':{'status':'PASS'}}}
    monkeypatch.setattr(census,'symbolic_witness',lambda s:({'synthetic':True},))
    result,_=original_status(completed,Fraction(32))
    assert result['correspondence_status']=='FAILED' and result['status']=='FAILED'
    assert completed['certificates']['correspondence']['status']=='PASS'
    completed['certificates']['correspondence']['constructor_maximum_difference']='0'
    def overflow(s):raise OverflowError("'mpz' too large to convert to float")
    monkeypatch.setattr(census,'symbolic_witness',overflow)
    result,_=original_status(completed,Fraction(32))
    assert result['C_premises']['error_type']=='OverflowError'
    assert result['classification']=='symbolic implementation failure'
    assert completed['certificates']['C_premises']['status']=='PASS'


def test_recovered_symbolic_body_reference():
    reference=json.loads((Path(__file__).parent/'fixtures/e2e_census_symbolic_reference.json').read_text())
    path=ROOT/'src/born_ladder/reproduction/census_writers/legacy_trine.py'
    node=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='witness')
    assert hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()==reference['adapted_witness_ast_sha256']


def test_original_gmp_overflow_and_exact_completion(tmp_path,selected_package_path):
    # An isolated pinned environment is optional in an ordinary test install.
    interpreter=os.environ.get('E2E_P3A_VERIFICATION_PYTHON')
    if not interpreter:pytest.skip('set E2E_P3A_VERIFICATION_PYTHON to the managed verification interpreter')
    code='''from fractions import Fraction
from born_ladder.robust_census import embedded_records
from born_ladder.reproduction.census_writers.legacy_trine import witness
from born_ladder.arithmetic import certify_G
r=embedded_records('lean_born')[7];s=Fraction(r['S'],r['D']**2)
try: witness(s)
except OverflowError as error: assert str(error)=="'mpz' too large to convert to float"
else: raise AssertionError('original GMP overflow path did not run')
assert certify_G(s)['status']=='PASS'
'''
    result=subprocess.run([interpreter,'-c',code],cwd=ROOT,
        env={**os.environ,'PYTHONPATH':selected_package_path,'SYMPY_GROUND_TYPES':'gmpy'},capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_runtime_profiles_reject_library_and_thread_changes():
    p=json.loads((ROOT/'specifications/environments/predictive.json').read_text())
    r={'numpy_version':p['numpy_version'],'machine':p['machine'],'byte_order':p['byte_order'],
       'libraries':p['libraries'],'blas_lapack_build':p['blas_lapack_build'],
       'numpy_cpu_features':{'X86_V3':True,'X86_V4':False,'AVX512_ICL':False,'AVX512_SPR':False},
       'thread_policy':p['thread_environment'],'effective_thread_pools':[
           {**q,'num_threads':1} for q in p['thread_pools']]}
    validate_runtime(p,r)
    for key in ('numpy_version','libraries','thread_policy','effective_thread_pools'):
        bad=copy.deepcopy(r)
        if key=='numpy_version':bad[key]='0'
        elif key=='libraries':bad[key][0]['sha256']='0'*64
        elif key=='thread_policy':bad[key]['OPENBLAS_NUM_THREADS']='2'
        else:bad[key][0]['num_threads']=2
        with pytest.raises(ValueError,match='mismatch'):validate_runtime(p,bad)


@pytest.mark.parametrize('feature',['X86_V4','AVX512_ICL','AVX512_SPR','all','missing'])
def test_effective_loaded_dispatch_is_required(feature):
    p=json.loads((ROOT/'specifications/environments/predictive.json').read_text())
    r={'numpy_version':p['numpy_version'],'machine':p['machine'],'byte_order':p['byte_order'],
       'libraries':p['libraries'],'blas_lapack_build':p['blas_lapack_build'],
       'numpy_cpu_features':{'X86_V3':True,'X86_V4':False,'AVX512_ICL':False,'AVX512_SPR':False},
       'thread_policy':p['thread_environment'],
       'effective_thread_pools':[{**q,'num_threads':1} for q in p['thread_pools']]}
    for name in ('X86_V4','AVX512_ICL','AVX512_SPR'):
        if feature in (name,'all'):r['numpy_cpu_features'][name]=True
    if feature=='missing':del r['numpy_cpu_features']['X86_V4']
    with pytest.raises(ValueError,match='effective NumPy CPU dispatch'):
        validate_runtime(p,r)


def managed_interpreter(name):
    """Optional provisioned locks; these tests need wheels, never archives."""
    root=os.environ.get('E2E_P3A_ENV_ROOT')
    if not root:pytest.skip('set E2E_P3A_ENV_ROOT to provisioned stage environments')
    profile=ROOT/'specifications/environments'/(name+'.json')
    p=json.loads(profile.read_bytes());lock=profile.parent/p['lock']
    key=hashlib.sha256(profile.read_bytes()+lock.read_bytes()).hexdigest()[:16]
    python=Path(root)/(name+'-'+key)/'bin/python'
    if not python.is_file():pytest.skip('provision the '+name+' locked environment first')
    return python


@pytest.mark.parametrize('caller,target',[('verification','predictive'),('predictive','verification')])
def test_installed_package_routing_isolates_stage_dependencies(tmp_path,caller,target):
    caller_python=managed_interpreter(caller);target_python=managed_interpreter(target)
    # Install-layout package, next to incompatible dependencies. The previous
    # whole-site-packages PYTHONPATH used precisely this parent directory.
    import born_ladder
    site=tmp_path/'foreign-site-packages';site.mkdir()
    shutil.copytree(Path(born_ladder.__file__).resolve().parent,site/'born_ladder',
                    ignore=shutil.ignore_patterns('__pycache__'))
    caller_site=caller_python.parent.parent/'lib/python3.12/site-packages'
    for name in ('numpy','numpy.libs'):
        (site/name).symlink_to(caller_site/name,target_is_directory=True)
    # Poison any inherited PYTHONPATH after the caller's package. The bridge
    # must not forward unrelated dependencies either.
    poison=tmp_path/'poison';poison.mkdir()
    (poison/'sympy.py').write_text('raise RuntimeError("foreign dependency leaked")\n')
    worker='''import json, os, sys
from born_ladder.reproduction.stage_environment import ensure_environment, check_current, profile_path
target, specs = sys.argv[1:]
result=ensure_environment(target,specs,[target,specs])
if result is not None: raise SystemExit(result)
profile=json.loads(profile_path(specs,target).read_bytes())
runtime=check_current(profile)
import numpy
print(json.dumps({'version':numpy.__version__,'numpy':numpy.__file__,'package':__file__,
 'effective_features':runtime['numpy_cpu_features']}))
'''
    (site/'born_ladder/__main__.py').write_text(worker)
    env={**os.environ,'PYTHONPATH':str(site)+os.pathsep+str(poison),
         'BORN_LADDER_ENV_ROOT':os.environ['E2E_P3A_ENV_ROOT'],
         'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1'}
    env.pop('BORN_LADDER_STAGE_PROFILE',None)
    result=subprocess.run([str(caller_python),'-m','born_ladder',target,str(ROOT/'specifications')],
        cwd=tmp_path,env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    document=json.loads(result.stdout)
    assert document['version']==json.loads((ROOT/'specifications/environments'/(target+'.json')).read_bytes())['numpy_version']
    assert Path(document['numpy']).resolve().is_relative_to(target_python.parent.parent.resolve())
    assert not any(document['effective_features'][name] for name in ('X86_V4','AVX512_ICL','AVX512_SPR'))


def test_post_import_predictive_worker_refuses_before_build(tmp_path,monkeypatch):
    from born_ladder.reproduction import units, unit_builders
    observed=[]
    def reject(profile):
        assert 'born_ladder.reproduction.unit_builders' in sys.modules
        assert 'numpy' in sys.modules  # The check follows scientific imports.
        observed.append(profile['profile'])
        raise ValueError('synthetic incompatible computing worker')
    def forbidden(*args):raise AssertionError('science ran before runtime validation')
    monkeypatch.setattr(units,'check_current',reject)
    monkeypatch.setattr(unit_builders,'build_invocation',forbidden)
    task={'threads':1,'specifications':str(ROOT/'specifications'),'directory':str(tmp_path),
          'job':{},'input':{'execution_status':'completed'},'numerical_runtime':{}}
    result=units.construct_one(task)
    assert observed==['predictive']
    assert result['status']=='failed' and 'incompatible computing worker' in result['error']
    assert not (tmp_path/'stdout.bin').exists()


def test_loaded_dispatch_mismatch_reexecutes(tmp_path):
    python=managed_interpreter('verification')
    import born_ladder
    site=tmp_path/'installed';site.mkdir()
    shutil.copytree(Path(born_ladder.__file__).resolve().parent,site/'born_ladder',
                    ignore=shutil.ignore_patterns('__pycache__'))
    code='''import json, os, sys
import numpy
from numpy._core import _multiarray_umath
from born_ladder.reproduction.stage_environment import ensure_environment
if not os.environ.get('BORN_LADDER_STAGE_PROFILE'):
    _multiarray_umath.__cpu_features__['X86_V4']=True
result=ensure_environment('verification',sys.argv[1],[sys.argv[1]])
if result is not None: raise SystemExit(result)
assert _multiarray_umath.__cpu_features__['X86_V4'] is False
print('checked computing child dispatch')
'''
    (site/'born_ladder/__main__.py').write_text(code)
    env={**os.environ,'PYTHONPATH':str(site),'BORN_LADDER_ENV_ROOT':os.environ['E2E_P3A_ENV_ROOT'],
         'PYTHONDONTWRITEBYTECODE':'1'}
    env.pop('BORN_LADDER_STAGE_PROFILE',None)
    result=subprocess.run([str(python),'-m','born_ladder',str(ROOT/'specifications')],
        cwd=tmp_path,env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert 'Using managed verification environment' in result.stderr
    assert result.stdout.strip()=='checked computing child dispatch'


def test_spawned_worker_checks_its_loaded_runtime(tmp_path,selected_package_path):
    python=managed_interpreter('predictive')
    script=tmp_path/'spawn_control.py'
    script.write_text('''from concurrent.futures import ProcessPoolExecutor
import json, multiprocessing, os, pathlib, sys
from born_ladder.reproduction.units import construct_one
from born_ladder.reproduction.numerical_runtime import numerical_runtime
if __name__=='__main__':
    specs, root=sys.argv[1:]
    actual=numerical_runtime(1)
    tasks=[]
    for index in range(2):
        directory=pathlib.Path(root)/str(index);directory.mkdir()
        runtime=dict(actual)
        if index: runtime['numpy_version']='synthetic corrupt coordinator identity'
        tasks.append({'directory':str(directory),'threads':1,'specifications':specs,
            'job':{},'input':{'execution_status':'completed' if index else 'timeout'},
            'numerical_runtime':runtime})
    with ProcessPoolExecutor(max_workers=1,mp_context=multiprocessing.get_context('spawn')) as pool:
        results=list(pool.map(construct_one,tasks))
    assert results[0]['status']=='input_incomplete' and 'input execution is timeout' in results[0]['error']
    assert results[1]['status']=='failed' and 'computing worker' not in results[1]['error']
    assert 'worker numerical runtime differs' in results[1]['error']
    assert all(r['worker_pid']!=os.getpid() for r in results)
    print(json.dumps(results))
''')
    profile=json.loads((ROOT/'specifications/environments/predictive.json').read_bytes())
    env={**os.environ,**profile['thread_environment'],**profile['dispatch_environment'],
         'PYTHONPATH':selected_package_path,'PYTHONDONTWRITEBYTECODE':'1'}
    result=subprocess.run([str(python),str(script),str(ROOT/'specifications'),str(tmp_path)],
        cwd=ROOT,env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert len(json.loads(result.stdout))==2


@pytest.mark.parametrize('table',['completion','original','reference_original'])
@pytest.mark.parametrize('corruption',['missing','truncated','duplicate','reordered','bad_index'])
def test_census_comparison_rejects_incomplete_or_misordered_status_tables(monkeypatch,table,corruption):
    from born_ladder.reproduction import census_comparison as module
    inventory=[{'unit_id':'first'},{'unit_id':'second'}]
    tables={name:[{'unit_id':r['unit_id'],'index':i} for i,r in enumerate(inventory)]
            for name in ('completion','original','reference_original')}
    damaged=tables[table]
    if corruption=='missing':tables[table]=[]
    elif corruption=='truncated':tables[table]=damaged[:1]
    elif corruption=='duplicate':damaged[1]['unit_id']='first'
    elif corruption=='reordered':tables[table]=damaged[::-1]
    else:damaged[1]['index']=0
    def mocked_read(path):
        path=Path(path)
        if path.name=='complete.json':return {'artifacts':[], 'summary':{'inventory_directory':'inventory','summary_directory':'summary'}}
        if path.name=='INVENTORY.json':return copy.deepcopy(inventory)
        if path.name=='structural_completion_results.json':return tables['completion']
        if path.name=='original_implementation_results.json':return tables['original']
        if path.name=='structural_results.json':return tables['reference_original']
        raise AssertionError('certificate comparison started on invalid tables: '+str(path))
    monkeypatch.setattr(module,'read',mocked_read)
    monkeypatch.setattr(module,'verify_artifacts',lambda *args:None)
    with pytest.raises(ValueError,match='table'):
        module.compare_census('generated','reference')


def test_stage_cli_guard_refuses_mismatched_runtime(tmp_path):
    environment={**os.environ,'BORN_LADDER_STAGE_PROFILE':'verification'}
    result=subprocess.run([sys.executable,'-m','born_ladder','reproduce','units','--grid','smoke',
        '--runs',str(tmp_path/'missing'),'--output',str(tmp_path/'output')],cwd=ROOT,env=environment,
        capture_output=True,text=True)
    assert result.returncode==1
    assert 'selected stage runtime refused' in result.stderr
    assert not (tmp_path/'output').exists()


def test_census_incompatible_resume_preserves_manifest(tmp_path,monkeypatch):
    from born_ladder.reproduction import census
    units=tmp_path/'units';runs=tmp_path/'runs';output=tmp_path/'output'
    units.mkdir();runs.mkdir();output.mkdir()
    inv=units/'inv.json';inv.write_text('[]\n')
    monkeypatch.setattr(census,'stage_identity',lambda *args:{'synthetic':True})
    monkeypatch.setattr(census,'collection_inputs',lambda *args:(units,{'stdout_execution_bindings':[]},
        inv,'units.jsonl',{}, {},{'expected_invocations':0,'completed_invocations':0,'complete':True}))
    monkeypatch.setattr(census,'capture_kernels',lambda *args:({},[]))
    monkeypatch.setattr(census,'numerical_runtime',lambda *args:{'synthetic_runtime':'changed'})
    (output/'census_plan.json').write_text(json.dumps({'numerical_runtime':{'synthetic_runtime':'original'}}))
    manifest=b'{"event":"synthetic preservation control"}\n'
    (output/'manifest.jsonl').write_bytes(manifest)
    with pytest.raises(ValueError,match='resume numerical runtime differs'):
        census.run_census(units=units,runs=[runs],output=output,specifications=ROOT/'specifications')
    assert (output/'manifest.jsonl').read_bytes()==manifest


def test_structural_decoder_skips_performance_values(monkeypatch):
    from born_ladder.reproduction.census_writers import cb2_parser
    original=cb2_parser.json.loads
    def reject_score(value,*args,**kwargs):
        if 'do not decode this score' in value:raise AssertionError('performance decoded')
        return original(value,*args,**kwargs)
    monkeypatch.setattr(cb2_parser.json,'loads',reject_score)
    text='{"unit_id":"synthetic","losses":{"q_full":"do not decode this score"}}'
    assert cb2_parser.metadata(text,cb2_parser.UNIT_KEYS)=={'unit_id':'synthetic'}


def test_failed_robust_check_preserves_original_status(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from born_ladder.reproduction import census
    from born_ladder.archive import put
    units=tmp_path/'units';runs=tmp_path/'runs';output=tmp_path/'output'
    units.mkdir();runs.mkdir();inv=units/'inv.json';inv.write_text('[]\n')
    monkeypatch.setattr(census,'stage_identity',lambda *args:{'synthetic':True})
    monkeypatch.setattr(census,'numerical_runtime',lambda *args:{'synthetic':True})
    monkeypatch.setattr(census,'collection_inputs',lambda *args:(units,{'stdout_execution_bindings':[]},
        inv,'units.jsonl',{}, {},{'expected_invocations':1,'completed_invocations':1,'complete':True}))
    monkeypatch.setattr(census,'capture_kernels',lambda *args:({},[]))
    def inventory(**kwargs):
        directory=Path(kwargs['output_dir']);directory.mkdir()
        put(directory/'INVENTORY.json',[{'unit_id':'synthetic'}])
        return {'selected_count':1,'rank_counts':{'2':1}}
    monkeypatch.setattr(census,'rebuild_inventory',inventory)
    monkeypatch.setattr(census,'ProcessPoolExecutor',ThreadPoolExecutor)
    def construct(task):
        directory=Path(task['output'])/'contexts/synthetic';directory.mkdir(parents=True)
        put(directory/'original_implementation.json',{'status':'PASS','classification':'completed original implementation',
            'correspondence_status':'PASS','C_premises':{'status':'PASS'}})
        put(directory/'maximal_gap_witness.json',{'cases':[{'case':0,'gap_exact':'1/10'}]})
        put(directory/'structural_completion_certificate.json',{'overall_status':'PASS'})
        return {'status':'completed','completion_status':'PASS','context_directory':'contexts/synthetic',
                'robust_status':'FAILED','failures':[]}
    monkeypatch.setattr(census,'construct_one',construct)
    result=census.run_census(units=units,runs=[runs],output=output,specifications=ROOT/'specifications')
    originals=json.loads((output/result['summary_directory']/'original_implementation_results.json').read_text())
    assert result['failed']==0 and result['original_pass']==1
    assert result['registered_robust_fail']==1 and result['amended_robust_pass']==1
    assert len(originals)==1 and originals[0]['status']=='PASS'
    assert json.loads((output/'complete.json').read_text())['status']=='PASS'
    monkeypatch.setattr(census,'construct_one',lambda *args:pytest.fail('completed context reconstructed'))
    resumed=census.run_census(units=units,runs=[runs],output=output,specifications=ROOT/'specifications')
    assert resumed['resumed'] and resumed['launched']==0 and resumed['registered_robust_fail']==1


def test_comparison_requires_order_and_exact_binary_values():
    c=Comparison();c.compare('order',['left','right'],['right','left'])
    c.compare('float',0.0,-0.0)
    c.compare('rational','1/3','2/6') # stored exact spelling is part of the certificate
    r=c.result()
    assert not r['overall_agreement']
    assert r['field_groups']['float']['maximum_absolute_difference']=='0'
    assert r['field_groups']['rational']['exact']==0


@pytest.mark.data
def test_complete_retained_structural_comparison():
    output=os.environ.get('E2E_P3A_OUTPUT')
    reference=os.environ.get('E2E_P3A_REFERENCE')
    if not output or not reference:
        pytest.skip('set E2E_P3A_OUTPUT and E2E_P3A_REFERENCE to closed census roots')
    from born_ladder.reproduction.census_comparison import compare_census
    result=compare_census(output,reference,lean_root=ROOT/'lean_born')
    assert result['contexts']==120 and result['overall_agreement'],result['field_groups']
