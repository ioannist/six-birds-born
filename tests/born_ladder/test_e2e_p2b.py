"""Named P2b I/O regressions; synthetic data below are not empirical evidence."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path

import pytest

from born_ladder.reproduction import units
from born_ladder.reproduction.unit_builders import BuiltInvocation
from born_ladder.snapshot.frozen_spec import canonical_json_bytes

REPO = Path(__file__).resolve().parents[2]
SPECS = REPO/'specifications'


@pytest.fixture
def capture_root(tmp_path):
    jobs,_ = units.planned_jobs(SPECS,'competitor')
    root = tmp_path/'captures';root.mkdir()
    rows = []
    for job in jobs[:2]:
        directory = root/job['identity'];directory.mkdir()
        raw = b'non-empirical synthetic I/O control\n'
        (directory/'stdout.bin').write_bytes(raw)
        attempt = canonical_json_bytes({'synthetic_control':True,'exit_code':0})
        (directory/'attempt.json').write_bytes(attempt)
        rows.append({'invocation':{k:job[k] for k in ('experiment','config_or_null','seed','scale')},
            'execution_status':'completed','stdout_path':job['identity']+'/stdout.bin',
            'stdout_sha256':hashlib.sha256(raw).hexdigest(),
            'attempt_path':job['identity']+'/attempt.json',
            'attempt_sha256':hashlib.sha256(attempt).hexdigest()})
    (root/'capture_index.json').write_text(json.dumps({'schema':'born_unit_capture_index_v1','invocations':rows}))
    return root


@pytest.fixture
def synthetic_builder(monkeypatch):
    from born_ladder.reproduction import unit_builders
    def build(spec,evaluation,stdout,invocation,attempt_sha):
        assert stdout==b'non-empirical synthetic I/O control\n'
        structural={'invocation_id':invocation['invocation_id'],'units':[],'synthetic_control':True}
        raw=canonical_json_bytes({'kind_cell_id':invocation['invocation_id'],'synthetic_control':True})
        return BuiltInvocation(structural,{'units.jsonl':raw,'structural.jsonl':canonical_json_bytes(structural),
            'admission.jsonl':canonical_json_bytes({'eligibility':True,'synthetic_control':True})},
            {'status':'completed','unit_rows':1})
    monkeypatch.setattr(unit_builders,'build_invocation',build)
    # These are synthetic orchestration controls in the test interpreter,
    # not predictive numerical workers. The real post-import check has its
    # own regression controls in test_e2e_p3a.py.
    monkeypatch.setattr(units,'check_worker_runtime',lambda task:None)
    # Threads here isolate orchestration tests from scientific workers. Actual
    # spawn-process production is checked on fresh captures in the packet.
    monkeypatch.setattr(units,'ProcessPoolExecutor',lambda max_workers,**kw:ThreadPoolExecutor(max_workers=max_workers))


def invoke(root,output):
    return units.run_units(grid='competitor',runs=[root],output=output,specifications=SPECS,workers=2)


def test_unit_grids_and_historical_stream_order():
    competitor,document=units.planned_jobs(SPECS,'competitor')
    cross,_=units.planned_jobs(SPECS,'cross-term')
    smoke,_=units.planned_jobs(SPECS,'smoke')
    assert len(competitor)==1380 and len(cross)==1500 and len(smoke)==5
    assert [j['identity'] for j in competitor]==sorted(j['identity'] for j in competitor)
    assert len({j['invocation_id'] for j in smoke})==5
    assert [j['seed'] for j in cross[:20]]==list(range(840001,840021))
    assert all(j['config_or_null']=='empty' for j in cross[:20])
    assert all(j['version']=='v24' for j in cross)
    assert document['policy']['structural_unit_binding'].endswith('without LF')


def test_completed_units_resume_and_corruption_rejected(tmp_path,capture_root,synthetic_builder):
    output=tmp_path/'output'
    first=invoke(capture_root,output)
    assert first['completed']==2 and first['incomplete']==1378
    assert first['input_available']==2
    before=(output/'manifest.jsonl').read_bytes()
    rows=units.Manifest(output).completed()
    second=invoke(capture_root,output)
    assert second['launched']==0 and second['skipped_completed']==2
    assert (output/'manifest.jsonl').read_bytes().startswith(before)
    first_path=output/first['collection']/'competitor/rb1v2_g2a_units.jsonl'
    second_path=output/second['collection']/'competitor/rb1v2_g2a_units.jsonl'
    assert first_path.read_bytes()==second_path.read_bytes()
    target=output/next(iter(rows.values()))['directory']/'units.jsonl'
    target.write_bytes(b'corrupted')
    with pytest.raises(ValueError,match='artifact changed'):invoke(capture_root,output)


def test_missing_failed_and_changed_capture_accounting(tmp_path,capture_root,synthetic_builder):
    path=capture_root/'capture_index.json';doc=json.loads(path.read_bytes())
    doc['invocations'][0]['execution_status']='timeout'
    path.write_text(json.dumps(doc))
    output=tmp_path/'output';result=invoke(capture_root,output)
    assert result['completed']==1 and result['failed']==1
    failed=next(r for r in units.Manifest(output).rows if r.get('status')=='input_incomplete')
    assert 'timeout' in failed['error']
    dispositions=[json.loads(line) for line in (output/result['collection']/'competitor/source_dispositions.jsonl').read_bytes().splitlines()]
    assert len(dispositions)==1380
    assert sum(r['status']=='missing_input' for r in dispositions)==1378
    assert any(r['status']=='input_timeout' and 'timeout' in r['reason'] for r in dispositions)
    doc['invocations'][0]['execution_status']='completed';path.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match='different grid'):invoke(capture_root,output)


def test_bad_stdout_hash_is_retained_as_failure(tmp_path,capture_root,synthetic_builder):
    index=json.loads((capture_root/'capture_index.json').read_bytes())
    (capture_root/index['invocations'][0]['stdout_path']).write_bytes(b'corruption')
    output=tmp_path/'output';result=invoke(capture_root,output)
    assert result['failed']==1
    row=next(r for r in units.Manifest(output).rows if r.get('status')=='failed')
    assert 'stdout hash differs' in row['error']
    assert (output/row['directory']/'failure.json').is_file()


def test_orphaned_attempt_and_no_source_overwrite(tmp_path,capture_root,synthetic_builder):
    output=tmp_path/'output'
    jobs,_=units.planned_jobs(SPECS,'competitor')
    orphan=output/'invocations'/jobs[0]['invocation_id']/'attempt_0001'
    orphan.mkdir(parents=True);(orphan/'partial').write_bytes(b'preserved')
    result=invoke(capture_root,output)
    assert result['completed']==2 and (orphan/'partial').read_bytes()==b'preserved'
    assert any(r.get('status')=='unrecorded_attempt_directory' for r in units.Manifest(output).rows)
    with pytest.raises(ValueError,match='disjoint'):
        invoke(capture_root,capture_root/'nested-output')


def test_capture_paths_and_identity_collisions_rejected(tmp_path,capture_root):
    with pytest.raises(ValueError,match='relative children'):
        units.relative_file(capture_root,'../escape')
    with pytest.raises(ValueError,match='relative children'):
        units.relative_file(capture_root,str(capture_root/'file'))
    with pytest.raises(ValueError,match='duplicate input'):
        units.source_inputs([capture_root,capture_root])
    # An external specification copy must not authorize data under tracked
    # public directories in the actual output worktree.
    with pytest.raises(ValueError,match='Git'):
        units.validate_output(REPO/'src/generated-unit-data',tmp_path)


def test_collection_control_links_are_bound_to_closed_aggregate(tmp_path):
    output=tmp_path/'output';output.mkdir()
    jobs,doc=units.planned_jobs(SPECS,'cross-term');jobs=jobs[:2]
    completed={}
    for index,job in enumerate(jobs):
        relative=Path('invocations')/job['invocation_id']/'attempt_0001'
        directory=output/relative;directory.mkdir(parents=True)
        (directory/'stdout.bin').write_bytes(b'non-empirical I/O fixture')
        (directory/'invocation.json').write_bytes(canonical_json_bytes({'invocation_id':job['identity']}))
        for name,row in [('units.jsonl',{'unit_id':str(index),'applicable_control_record_links':[]}),
                         ('controls.jsonl',{'unit_id':str(index)}),('admission.jsonl',{}),
                         ('structural.jsonl',{'invocation_id':job['identity']})]:
            (directory/name).write_bytes(canonical_json_bytes(row))
        (directory/'package_reconstruction.jsonl').write_bytes(b'')
        completed[job['invocation_id']]={'directory':str(relative),'unit_rows':1,
                                        'input_binding':{'attempt_sha256':'a'*64}}
    doc['_selected_grid']='cross-term'
    path,col=units.assemble(output,jobs,completed,{},doc,1)
    parent=path/'cross-term';control=parent/doc['evaluations']['cross-term']['controls_file']
    rows=[json.loads(line) for line in (parent/doc['evaluations']['cross-term']['units_file']).read_bytes().splitlines()]
    assert len(rows)==2
    assert all(r['applicable_control_record_links'][0]['sha256']==units.digest(control) for r in rows)
    assert not any(Path(link['path']).is_absolute() for r in rows for link in r['applicable_control_record_links'])


def test_comparator_reports_binary64_and_membership_differences(tmp_path):
    from born_ladder.reproduction.unit_comparison import compare_records
    generated=tmp_path/'units.jsonl'
    fresh={'kind_cell_id':'one','dtv_loss':{'q_full':-0.0},'eligibility':True}
    generated.write_bytes(canonical_json_bytes(fresh))
    reference={'kind_cell_id':'one','dtv_loss':{'q_full':0.0},'eligibility':False}
    result=compare_records(generated,[canonical_json_bytes(reference)])
    assert not result['scientific_fields_exact']
    floats=result['groups']['losses_and_contrasts']
    assert floats['float_values_compared']==1 and floats['float_values_binary64_exact']==0
    assert floats['maximum_absolute_difference']==0.0
    assert result['groups']['eligibility_and_dispositions']['scalar_values_exact']==0
    reference['kind_cell_id']='missing'
    result=compare_records(generated,[canonical_json_bytes(reference)])
    assert result['missing_rows']==['missing'] and result['extra_rows']==['one']
    assert not result['row_order_exact']


def test_permuted_scientifically_equal_stream_fails_overall_agreement(tmp_path,capsys):
    from born_ladder.reproduction.unit_comparison import compare_records
    from born_ladder.__main__ import main
    rows=[canonical_json_bytes({'kind_cell_id':name,'dtv_loss':{'q_full':0.25}})
          for name in ('first','second')]
    reference=tmp_path/'reference.jsonl';reference.write_bytes(b''.join(rows))
    generated=tmp_path/'generated.jsonl';generated.write_bytes(b''.join(reversed(rows)))
    result=compare_records(generated,rows)
    assert result['scientific_fields_exact']
    assert not result['row_order_exact'] and not result['overall_agreement']
    assert main(['reproduce','compare-units','--generated',str(generated),
                 '--reference',str(reference)])==1
    assert not json.loads(capsys.readouterr().out)['overall_agreement']
    generated.write_bytes(reference.read_bytes())
    assert main(['reproduce','compare-units','--generated',str(generated),
                 '--reference',str(reference)])==0


@pytest.mark.parametrize('component',['interpreter','numpy_version','libraries','thread_policy'])
def test_incompatible_numerical_runtime_resume_rejected(tmp_path,capture_root,synthetic_builder,monkeypatch,component):
    import copy
    output=tmp_path/'output';first=invoke(capture_root,output)
    assert first['completed']==2
    recorded=json.loads((output/'unit_plan.json').read_bytes())['numerical_runtime']
    changed=copy.deepcopy(recorded)
    if component=='interpreter':changed[component]['executable_sha256']='0'*64
    elif component=='numpy_version':changed[component]='incompatible-version'
    elif component=='libraries':changed[component][0]['sha256']='0'*64
    else:changed[component]['OPENBLAS_NUM_THREADS']='2'
    monkeypatch.setattr(units,'numerical_runtime',lambda threads:changed)
    before=(output/'manifest.jsonl').read_bytes()
    with pytest.raises(ValueError,match='numerical runtime'):invoke(capture_root,output)
    assert (output/'manifest.jsonl').read_bytes()==before


def test_numerical_runtime_identity_is_stable_and_effective_threads_are_bound():
    import numpy as np
    from born_ladder.reproduction.runs import THREAD_VARIABLES
    first=units.numerical_runtime(1)
    assert first==units.numerical_runtime(1)
    assert first['numpy_version']==np.__version__
    assert len(first['interpreter']['executable_sha256'])==64
    assert any('openblas' in row['name'] for row in first['libraries'])
    assert any('_umath_linalg' in row['name'] for row in first['libraries'])
    assert all(len(row['sha256'])==64 for row in first['libraries'])
    assert first['thread_policy']=={key:'1' for key in THREAD_VARIABLES}
    assert first['effective_thread_pools']
    assert all(pool['num_threads']==1 for pool in first['effective_thread_pools'])


def test_fresh_collection_has_independent_laws_and_census_inputs(tmp_path):
    import os
    import math
    import numpy as np
    from born_ladder.reproduction.census_writers.build_inventory import rebuild_inventory
    configured=os.environ.get('E2E_P2B_COLLECTION')
    if not configured:pytest.skip('E2E_P2B_COLLECTION=<fresh P2b output root> required')
    root=Path(configured).resolve(strict=True)
    collection=root/'collections/collection_0001'
    overview=json.loads((collection/'collection.json').read_bytes())
    assert all(row['complete'] for row in overview['evaluations'].values())
    for evaluation,entry in overview['evaluations'].items():
        parent=root/entry['path']
        structural={json.loads(line)['invocation_id']:line for line in
                    (parent/'structural_manifest.jsonl').read_bytes().splitlines(keepends=True)}
        rows=[json.loads(line) for line in (parent/entry['units_file']).read_bytes().splitlines()]
        assert len(rows)==entry['unit_rows']
        for row in rows:
            line=structural[row['invocation_id']]
            bound=line.removesuffix(b'\n') if evaluation=='competitor' else line
            assert hashlib.sha256(bound).hexdigest()==row['structural_manifest_sha256']
            if not row['eligibility']:continue
            for kind in ('raw','pkg'):
                mapping=np.asarray(row['M_'+kind+'_or_content_hash'])
                actual=(mapping@np.asarray(row['state_space_prediction']['q_full'])).tolist()
                # A raw row and a package row store their own mapped prediction.
                from born_ladder.snapshot.identities import kind_cell_id
                if row['kind_cell_id']!=kind_cell_id(row['unit_id'],kind):continue
                assert actual==row['mapped_outcome_prediction']['q_full']
                empirical=row['unrounded_y_'+kind]
                loss=0.5*math.fsum(abs(a-b) for a,b in zip(actual,empirical))
                assert loss==row['dtv_loss']['q_full']
    parent=collection/'cross-term'
    result=rebuild_inventory(archive_root=root,campaign_path=parent/'campaign.json',
        invocation_path=parent/'invocation_manifest.json',
        unit_logical_path=str((parent/'rb1v2_g2c_v23_units.jsonl').relative_to(root)),
        output_dir=tmp_path/'census',historical_inputs=False)
    assert result['paired_contexts']*2==overview['evaluations']['cross-term']['unit_rows']
    assert result['selected_count']>0
