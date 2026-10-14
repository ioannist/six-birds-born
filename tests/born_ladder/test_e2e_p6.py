"""Locked-opening/bundle boundary and sampling regressions; synthetic only."""
import json
from pathlib import Path
import subprocess
import pytest

pytest.importorskip('torch',reason='P6 production checks need the optional fitting stack')
pytest.importorskip('scipy',reason='P6 production checks need the optional fitting stack')
from test_e2e_p5 import headers, B, R, C, E, SPECS, SAMPLER
from born_ladder.reproduction import locked_test as L
from born_ladder.reproduction.regenerated_bundle import Bundle


def committed(root,source):
    B.run_test_b(output=root,headers=source,specifications=SPECS,stage='sample',smoke=True,sampler=SAMPLER)
    setup=C.canonical_document(root/'setup.json');entries=R.eligible_entries(root,setup)
    for entry,rank in entries:
        d=R.P5RecordLoader(root).load(root/'record_view'/entry['file'])
        prediction={'rank':rank,'recipe_ids':list(range(48,60)),'reading_counts':list(range(1,9)),
                    'h_c':entry['h_c'],'selectors':{},'predictions':{'square':[[[1/d.m]*d.m]*8]*12}}
        B._json(root/'fits/original'/f'{R.fit_identity(entry)}_r{rank}'/'predictions.json',prediction)
    margin=root/'fits/rank_margins.json';B._json(margin,{'schema':'test_b_v6_1_sealed_margins_v1','margins':{'2':.01,'3':.01,'4':.01},'folds':{}})
    # Numerical sampling-gate stub only; actual fitting/inference is exercised
    # by the public reduced pipeline. These tests do not certify fit results.
    paths=[p for p in (root/'fits').rglob('*') if p.is_file()]
    R.commit_phase(root,'fit',paths,{'status':'SYNTHETIC_GATE_STUB','sealed_margin_sha256':R.sha(margin)})
    R.commit_phase(root,'seal',[],{'status':'SYNTHETIC_GATE_STUB'})
    files={}
    for phase in R.PHASES:
        doc=R.verify_phase(root,phase);files.update(doc['files']);files[f'{phase}.commit.json']=R.sha(root/f'{phase}.commit.json')
    B._json(root/'prediction_seal_manifest.json',{'files':files,'setup_sha256':R.sha(root/'setup.json'),
        'spec_sha256':R.SPEC_HASH,'locked_test_sampled_or_opened':False,'subset_nonconfirmatory':True,
        'rank_context_counts':{str(r):sum(rank==r for _,rank in entries) for r in (2,3,4)},'mandatory_order_completed':None})
    return entries


def test_missing_prediction_refuses_without_launch(tmp_path,monkeypatch):
    calls=[];monkeypatch.setattr(subprocess,'run',lambda *a,**k:calls.append(a))
    root=tmp_path/'p5';root.mkdir()
    with pytest.raises(FileNotFoundError):L.prediction_commit(root)
    assert calls==[]


def test_locked_sampler_gate_and_completed_numeric_change(tmp_path,headers):
    if not SAMPLER.exists():pytest.skip('make rust-test-b')
    source,_,_=headers;root=tmp_path/'p5';committed(root,source)
    with pytest.raises(ValueError,match='explicit --smoke'):L.prediction_commit(root)
    assert L.prediction_commit(root,reduced=True)[2]=={'2':1,'3':1}
    (root/'fits/rank_margins.json').write_text('{}')
    with pytest.raises(RuntimeError,match='artifact differs'):L.prediction_commit(root,reduced=True)
    result=subprocess.run([str(SAMPLER),'--header',str(next(source.iterdir())),'--output',str(tmp_path/'rust'),
        '--locked-test','--predictions-root',str(root)],capture_output=True)
    assert result.returncode and b'committed numeric file changed' in result.stderr
    assert not (tmp_path/'rust').exists()


def test_actual_locked_sampling_resume_and_interrupted_attempt(tmp_path,headers):
    if not SAMPLER.exists():pytest.skip('make rust-test-b')
    source,_,_=headers;root=tmp_path/'p5';committed(root,source)
    out=tmp_path/'p6';out.mkdir();L.prepare(root,out,reduced=True)
    work=out/'jobs/EXP-112_synthetic/attempts/attempt_0001';work.mkdir(parents=True);(work/'broken').write_text('{')
    a=L.sample(root,out,workers=2,sampler=SAMPLER,reduced=True)
    assert a['summary']['paths_per_kernel']==7680
    assert (work/'broken').read_text()=='{'
    assert len(list(work.parent.glob('attempt_*')))==2
    before=next((out/'record_side').glob('*')).read_bytes()
    assert L.sample(root,out,workers=1,sampler=SAMPLER,reduced=True)==a
    assert next((out/'record_side').glob('*')).read_bytes()==before
    from born_ladder.record_tests.fresh_v6 import validate_sidecars
    audit=next((out/'audit_side').glob('*'));record=next((out/'record_side').glob('*'))
    ah,rh,labels=validate_sidecars(audit,record)
    assert all(v.shape==(20,12,32,8) for v in labels.values())
    assert ah['mode']=='fresh_test' and rh['mode']=='fresh_test'


def test_census_bound_to_committed_predictions(tmp_path,headers):
    source,_,_=headers;root=tmp_path/'p5';committed(root,source)
    path=root/'census/sealed/test_census.jsonl'
    path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='census numerical file differs'):
        L.prediction_commit(root,reduced=True)


def test_partial_score_is_preserved_and_complete_score_is_not_repaired(tmp_path):
    import numpy as np
    root=tmp_path/'p6';cache=root/'bootstrap_cache';cache.mkdir(parents=True)
    (root/'verdict.json').write_text('{')
    (root/'score.commit.json').write_text('{')
    (cache/'truncated.npy').write_bytes(b'partial numpy write')
    from born_ladder.record_tests import scorer_v6 as V
    np.save(cache/'complete.npy',np.zeros((V.DRAW_COUNT,20),dtype=np.uint8))
    L.recover_partial_score(root)
    attempt=root/'incomplete_scores/attempt_0001'
    assert (attempt/'verdict.json').read_text()=='{'
    assert (attempt/'bootstrap_cache/truncated.npy').read_bytes()==b'partial numpy write'
    assert (cache/'complete.npy').exists()
    (root/'score.commit.json').write_text('{}')
    (root/'verdict.json').write_text('changed')
    L.recover_partial_score(root)
    assert (root/'verdict.json').read_text()=='changed'
    assert len(list((root/'incomplete_scores').iterdir()))==1


def test_regenerated_bundle_never_accepted_as_historical(tmp_path):
    from born_ladder.claims import Evidence
    p=tmp_path/'bundle.json';p.write_text(json.dumps({'schema':'born_regenerated_bundle_v1','profile':'regenerated','roots':{},'files':{}}))
    with pytest.raises(ValueError,match='born_claim_bundle_v1'):Evidence(p)
    assert Bundle(p).doc['profile']=='regenerated'


def test_bundle_path_escape_and_modified_data(tmp_path):
    root=tmp_path/'files';root.mkdir();(root/'x.json').write_text('{}')
    p=tmp_path/'bundle.json'
    doc={'schema':'born_regenerated_bundle_v1','profile':'regenerated','roots':{'x':'files'},'files':{'x':{'../x.json':'bad'}}}
    p.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match='escapes'):Bundle(p)
    doc['files']['x']={'x.json':R.sha(root/'x.json')};p.write_text(json.dumps(doc));Bundle(p)
    (root/'x.json').write_text('[]')
    with pytest.raises(ValueError,match='numeric file changed'):Bundle(p)


def test_bundle_resume_accepts_new_cost_record_but_not_changed_science(tmp_path):
    from born_ladder.reproduction.regenerated_bundle import assemble
    names=('worked','census','attachments','competitor_evaluation','cross_term_evaluation',
           'test_b','locked','lean','competitor_units','cross_term_units')
    components={name:name for name in names}
    (tmp_path/'pipeline.json').write_text(json.dumps({'profile':'smoke','components':components}))
    for name in names:
        d=tmp_path/name;d.mkdir();(d/'number.json').write_text('{"value":1}')
    out=tmp_path/'bundle';assemble(tmp_path,out)
    (tmp_path/'census/cost_0002.json').write_text('{"wall_seconds":0.5}')
    assemble(tmp_path,out);Bundle(out)
    assert len(list((out/'inventories').glob('*.json')))==2
    (tmp_path/'census/number.json').write_text('{"value":2}')
    with pytest.raises(ValueError,match='completed bundle data differs'):assemble(tmp_path,out)


def test_regenerated_robust_witness_checks_bound_not_only_saved_table(tmp_path,monkeypatch):
    from born_ladder.reproduction.regenerated_bundle import verify_group
    from born_ladder.reproduction import lean_inputs
    from born_ladder.robust_census import integer_record,scan_records
    # A registered formal cohort must still establish 3/20. For other
    # cohorts, verify the exact maximum and report whether that bound holds.
    integer=integer_record(['-1','1']+['0']*30,[[0]*32]*3)
    def checked(root,*,expected_count,registered):
        return [integer],scan_records([integer],require_bound=registered)['cases']
    monkeypatch.setattr(lean_inputs,'census_records',checked)
    (tmp_path/'formal_coverage.json').write_text(json.dumps({'status':'APPLICABLE'}))
    b=type('Evidence',(),{'roots':{'census':tmp_path,'lean':tmp_path},'doc':{'reduced':False}})()
    with pytest.raises(ValueError,match='robust bound failed'):verify_group(b,'census')
    (tmp_path/'formal_coverage.json').write_text(json.dumps({'status':'NOT_APPLICABLE'}))
    result=verify_group(b,'census')
    assert result['exact_cases_rederived']==1
    assert result['registered_gap_bound_satisfied'] is False
    assert result['full_120_case_claim'] is False


def test_pipeline_failure_stops_downstream_and_profile_resume_bound(tmp_path,monkeypatch):
    from born_ladder.reproduction.pipeline import run_all
    from born_ladder.reproduction import pipeline
    monkeypatch.setattr(pipeline,"validate_output",lambda p,*a:Path(p))
    calls=[]
    def fail(argv,**kwargs):calls.append(argv);return type('Result',(),{'returncode':1})()
    monkeypatch.setattr(subprocess,'run',fail)
    with pytest.raises(RuntimeError,match='stage runs failed'):run_all(output=tmp_path/'out',profile='smoke',specifications=SPECS)
    assert len(calls)==1
    with pytest.raises(ValueError,match='profile changed'):run_all(output=tmp_path/'out',profile='full',specifications=SPECS)


def test_registered_scorer_budget_and_default_historical_profile():
    from born_ladder.record_tests import scorer_v6 as V
    assert V.DRAW_COUNT==200000
    from born_ladder.__main__ import main
    assert main(['verify','--list'])==0
    text=(SPECS.parent/'src/born_ladder/__main__.py').read_text()
    assert "choices=('historical','regenerated'), default='historical'" in text


def test_e2e_capture_grid_covers_every_unit_smoke_invocation():
    from born_ladder.reproduction.runs import RunSpecifications
    from born_ladder.reproduction.units import planned_jobs
    capture={(j.experiment,j.configuration,j.seed,j.scale) for j in RunSpecifications(SPECS).grid('e2e-smoke')}
    # Cross-stage coverage, not a duplicate seed/configuration schedule.
    jobs,_=planned_jobs(SPECS,'smoke')
    for job in jobs:
        assert (job['experiment'],job['config_or_null'],job['seed'],job['scale']) in capture


def test_resume_ignores_process_receipts_but_keeps_numerical_contract():
    from born_ladder.reproduction.checkpoints import numeric_plan
    a={'code':[{'sha256':'old'}],'source_code':{'x':'old'},'runtime':'same','grid':{'seeds':[1,2]}}
    b={'code':[{'sha256':'new'}],'source_code':{'x':'new'},'runtime':'same','grid':{'seeds':[1,2]}}
    assert numeric_plan(a)==numeric_plan(b)
    b['grid']['seeds']=[1,3]
    assert numeric_plan(a)!=numeric_plan(b)
