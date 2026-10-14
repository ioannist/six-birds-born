"""Synthetic-only v25 gates: no retained scores and no acquisition seeds."""
from copy import deepcopy
from fractions import Fraction as Q
import itertools
import json
import math
from pathlib import Path
import subprocess
import sys
import pytest

from born_ladder.reproduction.v25.canonical import construct,cutoff_decision,ordered_directions,controls
from born_ladder.reproduction.v25.checker import check_certificate
from born_ladder.reproduction.v25.exact import Interval,Unresolved,round_cell,square_root
from born_ladder.reproduction.v25.specification import Specification,digest,canonical_bytes
from born_ladder.reproduction.v25.predictions import restricted_input,midpoint_uniform,normal_matrix,orientations,commit,read_committed
from born_ladder.reproduction.v25.inference import joint_verdict,dependency_states,membership,endpoint_status
from born_ladder.snapshot.rng import RNGStream
from born_ladder.snapshot.statistics_helpers import _conditional_sign_counts

SPEC=Path(__file__).resolve().parents[2]/'specifications'


def test_cutoff_equality_and_neighbours():
    a=Q(1,2**51)
    for value,keep in [(a*(1-Q(1,2**52)),False),(a,False),(a*(1+Q(1,2**52)),True)]:
        vectors,norms,decisions=ordered_directions([[value,-value,value,-value]])
        assert decisions[0]['keep'] is keep
        if value==a: assert decisions[0]['cutoff']['equality'] is True
        assert len(vectors)==(2 if keep else 1)


def test_cutoff_unresolved_and_root_enclosure():
    with pytest.raises(Unresolved):
        cutoff_decision(Q(1707,1000)*Q(4,2**104),[[Q(1),Q(1)],[Q(1),Q(0)]],bits=1)
    root=square_root(Q(2),384)
    assert root.lo**2<=2<=root.hi**2


def test_midpoint_nearest_even_and_unresolved():
    midpoint=Q(1)+Q(1,2**53)
    cell=Interval(midpoint-Q(1,2**100),midpoint+Q(1,2**100))
    with pytest.raises(Unresolved): round_cell(cell)
    value,proof=round_cell(cell,lambda target:target==midpoint)
    assert value==1.0 and proof['midpoint_equality']==str(midpoint)
    assert math.copysign(1,round_cell(Interval(0))[0])==1
    negative=round_cell(Interval(-Q(1,2**2000)))[0]
    assert math.copysign(1,negative)==-1


def test_rank_two_identity_order_orientation_and_probability_certificate():
    emitted=[[0.5,-0.5,0.5,-0.5],[1.0]*4,[1.0,-1.0,1.0,-1.0]]
    p=[1.0,0.0,0.0,0.0]; cert=construct(emitted,p)
    assert cert['rank']==2 and [d['keep'] for d in cert['decisions']]==[True,False,False]
    assert cert['directions']==[['1']*4,['1/2','-1/2','1/2','-1/2']]
    assert cert['basis_columns']==[[0.5]*4,[0.5,-0.5,0.5,-0.5]]
    assert cert['q_diag_canonical']==[0.25]*4
    assert cert['q_full_exact_rounded']==[0.5,0.0,0.5,0.0]
    assert check_certificate(emitted,p,cert)
    cert['probability_cells'][0]['interval'][0]='0'
    with pytest.raises(ValueError,match='replay'):check_certificate(emitted,p,cert)


def test_rank_span_full_controls_and_unresolved():
    cert=construct([[0.5,-0.5,0.5,-0.5]],[0.25]*4)
    basis=list(map(list,zip(*cert['basis_columns'])))
    valid=controls(cert,basis,[0.25]*4)
    assert valid['status']=='pass'
    assert controls(cert,[[0.5]]*4,[0.25]*4)['status']=='unresolved'
    assert controls(cert,basis,[1.0,0,0,0])['status']=='unresolved'
    assert construct([[0.5,-0.5,0.5,-0.5]],[0.25]*4,refinement=())['status']=='numerical-unresolved'


def test_sample_poisoning_extractor_and_commitment(tmp_path):
    base={'identity':['SYNTHETIC','a',7,'context',2,0],'emitted':[[0.5,-0.5]],'preparation':[0.5,0.5],
          'labels':{'raw':[0,1],'package':[0,0]}}
    poisoned={**base,'endpoints':[1]*24,'loss':1000,'frequency':[1.0,0.0],'orientation_choice':99}
    assert restricted_input(base)==restricted_input(poisoned)
    prediction={'restricted':restricted_input(base),'restricted_sha256':digest(restricted_input(base)),
                'scientific_digest':'a'*64}
    commit(tmp_path,prediction); assert read_committed(tmp_path)[0]==prediction
    with pytest.raises(FileExistsError):commit(tmp_path,prediction)
    (tmp_path/'prediction.json').write_text('{}')
    with pytest.raises(ValueError):read_committed(tmp_path)


def test_open_uniform_recipe_and_word_consumption():
    assert midpoint_uniform(0)==2**-53
    assert midpoint_uniform(2**64-1)==1-2**-53
    stream=RNGStream(b'k'*32); matrix,words=normal_matrix(stream,3)
    assert len(words)==10 and len(matrix)==3 and len(matrix[0])==3
    a,b=words[:2]; radius=math.sqrt(-2*math.log(midpoint_uniform(a)))
    assert matrix[0][0]==radius*math.cos(2*math.pi*midpoint_uniform(b))


def test_orientation_qr_signs_retry_domain_separation():
    import numpy as np
    spec=Specification(SPEC)
    restricted={'identity':['SYNTHETIC','a',7,'context',2,0],'emitted':[[0.5,-0.5]],'preparation':[0.5,0.5],
                'labels':{'raw':[0,1],'package':[0,0]}}
    cert=construct(restricted['emitted'],restricted['preparation'])
    rows=orientations(spec,'competitor',restricted,cert)
    assert len(rows)==128 and all(row['status']=='complete' for row in rows)
    for row in rows:
        detail=row['attempts'][-1]; Qm=np.array(detail['orthogonal_matrix']); R=np.array(detail['triangular_matrix'])
        assert all(R[i,i]>0 for i in range(2))
        assert np.max(abs(Qm@R-np.array(detail['normal_matrix'])))<1e-12
    def zero(matrix):return np.eye(2),np.zeros((2,2))
    failed=orientations(spec,'competitor',restricted,cert,qr=zero)
    assert all(row['status']=='unresolved' and len(row['attempts'])==8 for row in failed)
    key=spec.orientation_key('competitor',restricted['identity'],digest(restricted),0,0)
    assert key!=spec.orientation_key('competitor',restricted['identity'],digest(restricted),0,1)
    assert key!=spec.orientation_key('cross-term',restricted['identity'],digest(restricted),0,0)
    assert key!=spec.bootstrap_key('competitor','raw::q_diag_canonical',0)


def test_whole_slot_missingness():
    from born_ladder.reproduction.v25.pipeline import descriptive
    spec=Specification(SPEC); count=spec.science['orientation_sensitivity']['random_orientation_count']
    pred={'orientations':[{'status':'unresolved'} for _ in range(count)],
          'canonical_certificate':{'status':'numerical-unresolved'},
          'historical_svd_reference':{'status':'unresolved'}}
    result=descriptive(spec,{'missing':pred},[{'unit_id':'missing','eligibility':True}],
                       'competitor',[7],['a'])
    assert result['status']=='distribution-unavailable' and result['summaries']=={}
    assert len(result['slots'])==count and all(row['missing_units']==['missing'] for row in result['slots'])


def test_exact_tail_cancellation_and_boundary_ties():
    values=[1.0,2**-54,-1.0]
    target=sum(map(Q.from_float,values)); signed=[sum(Q.from_float(x)*sign for x,sign in zip(values,signs)) for signs in itertools.product([-1,1],repeat=3)]
    assert _conditional_sign_counts(values)==(sum(abs(x)>=abs(target) for x in signed),sum(x>=target for x in signed),8)
    assert _conditional_sign_counts([0.0]*20)==(2**20,2**20,2**20)


@pytest.mark.parametrize('flags',list(itertools.product([False,True],repeat=4)))
def test_complete_decision_cube(flags):
    spec=Specification(SPEC); c,u,r,f=flags
    row=joint_verdict(spec,control=c,unresolved=u,reversal=r,failure=f)
    expected='INCONCLUSIVE_CONTROL_FAILURE' if c else 'INCONCLUSIVE_UNRESOLVED' if u else 'INCONCLUSIVE_SENSITIVITY_REVERSAL' if r else 'FAIL' if f else 'PASS'
    assert row['status']==expected


def test_endpoint_control_propagation_and_local_exclusion():
    spec=Specification(SPEC); states={name:'pass' for name in 'IAFCTSO'}
    states['C']='missing'; states['O']='fail'
    canonical=dependency_states(spec,'canonical advantage, each map in either evaluation',states)
    competitor=dependency_states(spec,'non-diagonal competitor advantage, each map',states)
    assert canonical['unresolved'] and not canonical['control_failure']
    assert not competitor['unresolved'] and not competitor['control_failure']
    states['F']='fail'; assert dependency_states(spec,'serviceability S_2, each map',states)['control_failure']
    assert endpoint_status({'bca_simultaneous_lower':-1,'bca_simultaneous_upper':0,'holm_adjusted_p':1},0)=='FAIL'
    assert joint_verdict(spec,unresolved=True,failure=True)['status']=='INCONCLUSIVE_UNRESOLVED'
    assert joint_verdict(spec,infrastructure='runtime')['status']=='INCONCLUSIVE_INFRASTRUCTURE'


def test_seventeen_domains_and_families():
    spec=Specification(SPEC); outputs=[]
    for row in spec.domains:
        row=deepcopy(row); evaluation=row['evaluation']
        row['statistic_id']=row['statistic_id'].replace('{kind}','raw').replace('{contrast_id}','q_diag_canonical')
        groups={'EXP-112':['a','b'],'G2x':['x']} if evaluation=='cross-term' else ['a','b']
        result=membership(spec,evaluation,row,seeds=list(range(20)),groups=groups,replicate=0)
        assert result==membership(spec,evaluation,row,seeds=list(range(20)),groups=groups,replicate=0)
        outputs.append(result)
    assert len(outputs)==17
    assert outputs[0]['indices']['seeds']!=outputs[9]['indices']['seeds']
    assert spec.science['inference']['multiplicity']['competitor']['holm_members']==24
    assert spec.science['inference']['multiplicity']['competitor']['bca_endpoints']==48
    assert spec.science['inference']['multiplicity']['cross_term']['holm_members']==2
    assert spec.science['inference']['multiplicity']['cross_term']['bca_endpoints']==4


def test_v25_grids_use_specification(tmp_path):
    from born_ladder.reproduction.runs import RunSpecifications
    spec=Specification(SPEC); grids=RunSpecifications(SPEC)
    for name in ('competitor','cross-term'):
        jobs=grids.grid('v25-'+name)
        assert {j.seed for j in jobs}==set(spec.grid(name)['seeds'])
        assert len(jobs)==spec.grid(name)['invocations']


def test_historical_helpers_only_have_explicit_v25_hooks():
    import ast,hashlib
    reference=json.loads((Path(__file__).parent/'fixtures/e2e_source_equivalence.json').read_bytes())
    checked=0
    class Restore(ast.NodeTransformer):
        def visit_Constant(self,node):
            if isinstance(node.value,str):node.value=node.value.replace('ledger','record')
            return node
        def visit_Name(self,node):
            if node.id=='stage_id':return ast.Constant('g2c_v2')
            if node.id=='diagonal_label':return ast.Constant('q_diag')
            return node
        def visit_IfExp(self,node):
            if isinstance(node.test,ast.Compare) and isinstance(node.test.left,ast.Name) and node.test.left.id=='sign_p':
                return ast.Name('_conditional_sign_p',ast.Load())
            return self.generic_visit(node)
        def visit_Call(self,node):
            if isinstance(node.func,ast.Name) and node.func.id=='getattr' and len(node.args)==3 and isinstance(node.args[1],ast.Constant) and node.args[1].value=='rng_master_prefix':
                return node.args[2]
            return self.generic_visit(node)
    for module in reference['modules']:
        if module['public_module'] not in ('src/born_ladder/snapshot/g2a.py','src/born_ladder/snapshot/g2c_evaluate.py','src/born_ladder/snapshot/rng.py'):continue
        tree=ast.parse((SPEC.parent/module['public_module']).read_text())
        for name in ('_sensitivity_results','_source_seed_values','_paired_bootstrap_results','_sensitivities','_derive_from_contract'):
            if name not in module['definitions']:continue
            entry=module['definitions'][name]
            if 'historical_normalized_ast_sha256' not in entry:continue
            node=deepcopy(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name))
            pairs=[(a,d) for a,d in zip(node.args.kwonlyargs,node.args.kw_defaults) if a.arg not in ('sign_p','stage_id','diagonal_label') or name=='_sensitivity_results' and a.arg=='stage_id']
            node.args.kwonlyargs=[a for a,d in pairs]; node.args.kw_defaults=[d for a,d in pairs]
            # g2a's original stage_id argument and references must stay names.
            if name=='_sensitivity_results':
                class RestoreG2a(Restore):
                    def visit_Name(self,node):return node
                node=RestoreG2a().visit(node)
            else:node=Restore().visit(node)
            assert hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()==entry['historical_normalized_ast_sha256'],name
            checked+=1
    assert checked==5


def test_default_and_v25_cross_term_bootstrap_pairing():
    from types import SimpleNamespace
    from born_ladder.reproduction.v25.inference import inherited_contract,derive
    from born_ladder.snapshot.g2c_evaluate import _paired_bootstrap_results
    s=Specification(SPEC); c,i=inherited_contract(s,'cross-term',4)
    placeholder=SimpleNamespace(attestation=SimpleNamespace(json_sha256=s.digest))
    rows=_paired_bootstrap_results(placeholder,{'raw':[float(j)/32 for j in range(20)],'package':[float(j*j)/512 for j in range(20)]},inference=i,contract=c,derive_key=derive(s,'cross-term'),stage_id='v25-cross-term')
    assert rows['raw']['replicate_membership']==rows['package']['replicate_membership']
    assert rows['raw']['rng_audit']==rows['package']['rng_audit']
    assert rows['raw']['replicate_estimates']!=rows['package']['replicate_estimates']


def test_fresh_adaptation_keeps_every_nondiagonal_value():
    from born_ladder.reproduction.v25.fresh import adapt_record
    from born_ladder.snapshot.identities import kind_cell_id
    s=Specification(SPEC); unit='a'*64
    original={'unit_id':unit,'kind_cell_id':kind_cell_id(unit,'raw'),'eligibility':True,
          'pass_boolean_for_each_residual':{'finite_residuals':True,'mass_residuals':True,'parseval_residuals':True,'rotation_residuals':True,'identity_residuals':False,'sequential_residuals':False},
          'ordered_union_outcome_labels':['a','b'],'M_raw_or_content_hash':[[1.0,0.0],[0.0,1.0]],
          'unrounded_y_raw':[0.75,0.25],'dtv_loss':{'q_full':0.125,'q_diag':0.25,'L_full':0.5},
          'brier_score':{'q_full':0.03125,'q_diag':0.125,'L_full':0.5},
          'state_space_prediction':{'q_full':[0.625,0.375],'q_diag':[0.5,0.5],'L_full':[0.25,0.75]},
          'pairwise_contrast':{'D__q_diag_minus_q_full':0.125,'D__L_full_minus_q_full':0.375},'tie_flag':{'D__q_diag_minus_q_full':False}}
    pred={'restricted':{'labels':{'raw':[0,1],'package':[0,0]}},'canonical_certificate':{'status':'certified','q_diag_canonical':[0.5,0.5]},'canonical_controls':{'status':'pass'}}
    new=adapt_record(s,original,pred,evaluation='competitor')
    for field in ('dtv_loss','brier_score','state_space_prediction'):
        for law in ('q_full','L_full'):assert new[field][law]==original[field][law]
    assert 'q_diag' not in new['dtv_loss'] and new['dtv_loss']['q_diag_canonical']==0.25
    assert new['controls']['F']=='pass' and new['controls']['C']=='pass'


def test_actual_worker_version_thread_checks_in_managed_interpreter(tmp_path):
    import os
    python=os.environ.get('V25_TEST_PYTHON')
    if not python:pytest.skip('set V25_TEST_PYTHON to the provisioned v25 interpreter for actual-worker checks')
    bridge=tmp_path/'selected-package';bridge.mkdir()
    (bridge/'born_ladder').symlink_to(Path(sys.modules['born_ladder'].__file__).resolve().parent)
    environment={**os.environ,'PYTHONPATH':str(bridge),'PYTHONDONTWRITEBYTECODE':'1',
                 'OPENBLAS_CORETYPE':'Haswell','NPY_DISABLE_CPU_FEATURES':'X86_V4,AVX512_ICL,AVX512_SPR'}
    environment.update({name:'1' for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','RAYON_NUM_THREADS','VECLIB_MAXIMUM_THREADS')})
    script='''
import ctypes,json
from copy import deepcopy
from born_ladder.reproduction.stage_environment import check_current
p=json.load(open('specifications/environments/predictive_v25.json'))
r=check_current(p); assert len(r['pools'])==2
bad=deepcopy(p); bad['numpy_version']='0.0'
try: check_current(bad)
except ValueError: pass
else: raise AssertionError('wrong version accepted')
ctypes.CDLL('libsqlite3.so.0')
check_current(p)  # unrelated native library is not a gate
import numpy as np
from pathlib import Path
import os
for row in Path('/proc/self/maps').read_text().splitlines():
 if 'openblas' in row and '/numpy.libs/' in row:
  library=ctypes.CDLL(row.split(maxsplit=5)[5]); set_threads=library.scipy_openblas_set_num_threads64_; set_threads(2); break
try: check_current(p)
except ValueError as error: assert 'one thread' in str(error)
else: raise AssertionError('wrong threads accepted')
print('actual versions/two pools, extra library accepted, wrong version/thread refused: pass')
'''
    done=subprocess.run([python,'-c',script],cwd=SPEC.parent,env=environment,text=True,capture_output=True)
    assert done.returncode==0,done.stdout+done.stderr


def test_v25_resume_binds_actual_runtime(tmp_path,monkeypatch):
    from born_ladder.reproduction.v25 import pipeline
    monkeypatch.setattr(pipeline,'worker_identity',lambda spec:{'python':'3.12','numpy':'2.5.2'})
    monkeypatch.setattr('born_ladder.reproduction.runs.validate_output',lambda output,repository:Path(output))
    spec=Specification(SPEC)
    pipeline.begin(spec,tmp_path,{'synthetic':True})
    monkeypatch.setattr(pipeline,'worker_identity',lambda spec:{'python':'3.12','numpy':'2.4.4'})
    with pytest.raises(ValueError,match='incompatible resume'):pipeline.begin(spec,tmp_path,{'synthetic':True})


def test_unsealed_partial_prediction_is_not_resumed(tmp_path):
    (tmp_path/'prediction.json').write_text('{')
    with pytest.raises(FileNotFoundError):read_committed(tmp_path)


def test_exact_brier_tail_route_and_independent_competitor_streams():
    import inspect
    from born_ladder.reproduction.v25 import inference
    from born_ladder.snapshot.g2a import _sensitivity_results
    source=inspect.getsource(inference.competitor)
    assert 'sign_p=tail' in source and 'exact_sign_counts' in source
    spec=Specification(SPEC)
    assert spec.bootstrap_key('competitor','raw::q_diag_canonical',0)!=spec.bootstrap_key('competitor','package::q_diag_canonical',0)
    assert spec.bootstrap_key('competitor','raw::q_diag_canonical',0)!=spec.bootstrap_key('competitor','raw::q_diag_canonical::sensitivity::brier_complete_ranking',0)


def test_interrupted_offline_provision_is_repaired(tmp_path,monkeypatch):
    from born_ladder.reproduction import stage_environment as E
    spec=tmp_path/'specifications'; (spec/'environments').mkdir(parents=True)
    for suffix in ('json','lock'):
        (spec/'environments'/('predictive_v25.'+suffix)).write_bytes((SPEC/'environments'/('predictive_v25.'+suffix)).read_bytes())
    cache=tmp_path/'managed'; monkeypatch.setenv('BORN_LADDER_ENV_ROOT',str(cache))
    monkeypatch.setenv('BORN_LADDER_WHEELHOUSE',str(tmp_path/'offline'))
    monkeypatch.delenv('BORN_LADDER_STAGE_PROFILE',raising=False)
    monkeypatch.setattr(E,'check_current',lambda profile:(_ for _ in ()).throw(ValueError('not matching')))
    class Builder:
        def __init__(self,**kwargs):pass
        def create(self,target):
            (target/'bin').mkdir(exist_ok=True); (target/'bin/python').write_text('synthetic installer placeholder')
    monkeypatch.setattr(E.venv,'EnvBuilder',Builder)
    calls=[]
    def interrupted(command,**kwargs):
        calls.append(command)
        if '-m' in command and 'pip' in command:raise subprocess.CalledProcessError(1,command)
        return subprocess.CompletedProcess(command,0)
    monkeypatch.setattr(E.subprocess,'run',interrupted)
    with pytest.raises(ValueError,match='provisioning failed'):E.ensure_environment('predictive_v25',spec,['reproduce','v25-smoke'])
    assert not list(cache.rglob('stage_ready.json'))
    def complete(command,**kwargs):
        calls.append(command);return subprocess.CompletedProcess(command,0)
    monkeypatch.setattr(E.subprocess,'run',complete)
    assert E.ensure_environment('predictive_v25',spec,['reproduce','v25-smoke'])==0
    assert len(list(cache.rglob('stage_ready.json')))==1
    assert all('--no-index' in command for command in calls if 'pip' in command)


def test_completed_scientific_artifacts_reject_corruption(tmp_path):
    from born_ladder.reproduction.v25.pipeline import artifact_bindings,verify_artifacts
    path=tmp_path/'scientific.json';path.write_text('{"synthetic":true}')
    bindings=artifact_bindings(tmp_path)
    verify_artifacts(tmp_path,bindings)
    path.write_text('{"synthetic":false}')
    with pytest.raises(ValueError,match='artifacts changed'):verify_artifacts(tmp_path,bindings)


def test_missing_shared_controls_cannot_establish_a_cross_term_verdict():
    from born_ladder.reproduction.v25.inference import cross_term
    result=cross_term(Specification(SPEC),[{'eligibility':True,'controls':{'I':'pass'}}],[],
                       seeds=list(range(20)),replicates=1)
    assert result['joint']['status']=='INCONCLUSIVE_UNRESOLVED'
    assert len(result['statistics'])==2
    assert all(row['point_estimate'] is None for row in result['statistics'].values())


def test_prediction_bytes_ignore_poisoned_samples():
    from born_ladder.reproduction.v25.pipeline import synthetic_payload
    from born_ladder.reproduction.v25.predictions import predict
    spec=Specification(SPEC);p=synthetic_payload(2)
    a=predict(spec,'competitor',p)
    b=predict(spec,'competitor',{**p,'endpoints':[7]*24,'loss':-999,'frequency':[0,1]})
    assert canonical_bytes(a)==canonical_bytes(b)


def test_descriptive_references_do_not_enter_quantiles_or_primary_verdict():
    from born_ladder.reproduction.v25.pipeline import descriptive,synthetic_payload,scored_rows
    from born_ladder.reproduction.v25.predictions import predict
    spec=Specification(SPEC);payload=synthetic_payload(2);prediction=predict(spec,'competitor',payload)
    unit_id=digest(payload['identity'])
    metadata={'unit_id':unit_id,'seed':7,'config_or_null':'a','invocation_id':'synthetic',
              'context':'synthetic','partition':'synthetic','resolution':2,'step':0,'eligibility':True}
    rows=scored_rows(prediction,{kind:[0,1]*12 for kind in ('raw','package')},metadata)
    report=descriptive(spec,{unit_id:prediction},rows,'competitor',[7],['a'])
    assert report['status']=='complete' and report['complete_slots']==128
    assert set(report['references'])=={'canonical','historical_svd'}
    assert len(report['slots'])==128 and all(len(slot['unit_contrasts'])==2 for slot in report['slots'])
    assert 'inference' not in report and 'verdict' not in report


def test_paper_serviceability_fields_are_in_the_printed_negative_orientation():
    from born_ladder.reproduction.v25.inference import finalize
    spec=Specification(SPEC);rules=spec.science['evaluations']['competitor']['competitors_in_registered_order']
    results={}
    for kind in ('raw','package'):
        for rule in [*rules,None]:
            key=kind+'::'+(rule or 'serviceability_factor_two')
            results[key]={'rule':rule,'kind':kind,'point_estimate':0.25,
                          'bca_simultaneous_lower':0.125,'bca_simultaneous_upper':0.5,
                          'conditional_one_sided_p':0.0}
    result=finalize(spec,'competitor',results,1)
    for kind in ('raw','package'):
        row=result['paper_values'][kind+'::serviceability_factor_two']
        assert row['formula']=='ell(q_full)-2*ell(p)'
        assert (row['point'],row['lower'],row['upper'])==(-0.25,-0.5,-0.125)


def test_nested_acquisition_identity_and_control_stream_use_v25_digest():
    from born_ladder.reproduction.v25.fresh import FreshSpecification
    from born_ladder.snapshot.rng import _derive_from_contract,master_key
    spec=Specification(SPEC);root=FreshSpecification(spec,'cross-term')
    source=root._g2c_source_spec
    assert root.attestation.json_sha256==source.attestation.json_sha256==spec.digest
    assert root.get('/rng')['framing']['master_prefix']==source.get('/rng')['framing']['master_prefix']==spec.science['rng']['master_prefix']
    from born_ladder.snapshot.g2c_controls import _contract as control_contract
    controlled=control_contract(root)
    assert controlled['master_prefix']==spec.science['rng']['master_prefix']
    assert controlled['source_json_sha256']==spec.digest
    contract=source.get('/rng');algorithm=next(iter(contract['algorithms']))
    fields=[];values={}
    for descriptor in contract['algorithms'][algorithm]['key_fields']:
        kind,name=descriptor.split(':',1)
        if kind=='bytes':value=bytes.fromhex(spec.digest)
        elif name in ('H1','H2','G2S_DOSE','bootstrap-v2'):value=name
        else:value=7 if kind=='u64' else 'synthetic';values[name]=value
        fields.append((kind,value))
    assert _derive_from_contract(source,contract,algorithm,values)==master_key(spec.science['rng']['master_prefix'],fields)


def test_planned_exclusion_cannot_invalidate_admitted_cross_term_controls():
    from born_ladder.reproduction.v25.inference import cross_term
    from born_ladder.snapshot.identities import kind_cell_id
    rows=[];controls=[];seeds=list(range(101,121))
    for seed in seeds:
        for source in ('EXP-112','G2x'):
            unit=digest([seed,source])
            for kind in ('raw','pkg'):
                row={'unit_id':unit,'kind_cell_id':kind_cell_id(unit,kind),'eligibility':True,
                     'source_key':source,'seed':seed,'fixed_census_config_or_experiment_key':'synthetic',
                     'invocation_id':unit,'context':'synthetic','resolution':2,'step':0,
                     'dtv_loss':{'q_full':0.125,'q_diag_canonical':0.25},
                     'brier_score':{'q_full':0.03125,'q_diag_canonical':0.125},
                     'controls':dict.fromkeys('IAFC','pass')}
                rows.append(row);controls.append({'unit_id':unit,'kind_cell_id':row['kind_cell_id'],'nondegenerate':True})
    excluded={**deepcopy(rows[0]),'eligibility':False,'brier_score':None,
              'controls':dict.fromkeys('IAFC','fail'),'fixed_census_config_or_experiment_key':'empty'}
    excluded['unit_id']=digest(['planned-empty']);excluded['kind_cell_id']=kind_cell_id(excluded['unit_id'],'raw')
    result=cross_term(Specification(SPEC),[excluded,*rows],
                      [{'unit_id':excluded['unit_id'],'kind_cell_id':excluded['kind_cell_id'],'nondegenerate':False},*controls],
                      seeds=seeds,replicates=1)
    assert not result['joint']['flags']['control_failure']
    assert all(not row['control_failure'] for row in result['statistics'].values())


def test_descriptive_passes_through_noncontributing_rows_without_losses():
    """Planned exclusions (e.g. the empty configuration) carry no losses; the
    descriptive report must pass them through unchanged instead of failing."""
    from born_ladder.reproduction.v25.pipeline import descriptive,synthetic_payload,scored_rows
    from born_ladder.reproduction.v25.predictions import predict
    spec=Specification(SPEC);payload=synthetic_payload(2);prediction=predict(spec,'competitor',payload)
    unit_id=digest(payload['identity'])
    metadata={'unit_id':unit_id,'seed':7,'config_or_null':'a','invocation_id':'synthetic',
              'context':'synthetic','partition':'synthetic','resolution':2,'step':0,'eligibility':True}
    rows=scored_rows(prediction,{kind:[0,1]*12 for kind in ('raw','package')},metadata)
    excluded=[{**row,'unit_id':'excluded','config_or_null':'empty','eligibility':False,
               'dtv_loss':None,'brier_score':None,'pairwise_contrast':{}} for row in rows]
    report=descriptive(spec,{unit_id:prediction},rows+excluded,'competitor',[7],['a'])
    baseline=descriptive(spec,{unit_id:prediction},rows,'competitor',[7],['a'])
    assert report['status']=='complete' and report['complete_slots']==128
    assert [s['contrasts'] for s in report['slots']]==[s['contrasts'] for s in baseline['slots']]
