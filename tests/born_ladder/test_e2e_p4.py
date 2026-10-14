"""P4 I/O, arithmetic-preservation and fail-closed boundary regressions."""
import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest

from born_ladder.reproduction import evaluation as E
from born_ladder.reproduction import census_attachments as A
from born_ladder.reproduction.census_comparison import Comparison
from born_ladder.summaries import quantiles

REPO=Path(__file__).resolve().parents[2]


def test_population_body_is_historical_ast():
    tree=ast.parse((REPO/'src/born_ladder/snapshot/g2a.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='evaluate_g2a_records')
    start=next(i for i,n in enumerate(node.body) if isinstance(n,ast.Assign)
               and any(isinstance(t,ast.Name) and t.id=='tie_tolerance' for t in n.targets))
    reference=json.loads((Path(__file__).parent/'fixtures/e2e_source_equivalence.json').read_text())['population_body']
    body=ast.Module(body=node.body[start:],type_ignores=[])
    assert hashlib.sha256(ast.dump(body,include_attributes=False).encode()).hexdigest()==reference['historical_body_normalized_sha256']
    old=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='evaluate_g2a')
    assert isinstance(old.body[-1],ast.Return)
    assert old.body[-1].value.func.id=='evaluate_g2a_records'


def test_inference_refuses_incomplete_collection(monkeypatch,tmp_path):
    monkeypatch.setattr(E,'collection_inputs',lambda *a:(None,None,None,None,None,None,
        {'complete':False,'completed_invocations':1,'expected_invocations':2}))
    with pytest.raises(ValueError,match='complete registered'):
        E.closed_inputs(tmp_path,'competitor',REPO/'specifications')


def test_completed_evaluation_resumes_with_different_worker_count(monkeypatch,tmp_path):
    from types import SimpleNamespace
    from born_ladder.archive import sha
    units=tmp_path/'units';units.mkdir()
    output=tmp_path/'evaluation';output.mkdir()
    artifact=output/'evaluation.json';artifact.write_text('{"status":"COMPLETE"}\n')
    summary={'status':'COMPLETE'}
    (output/'complete.json').write_text(json.dumps({'summary':summary,'artifacts':[
        {'path':'evaluation.json','bytes':artifact.stat().st_size,'sha256':sha(artifact)}]}))
    spec=SimpleNamespace(scientific_rng_identity='registered')
    monkeypatch.setattr(E,'stage_identity',lambda *a:{'profile':'predictive'})
    monkeypatch.setattr(E,'probe_current_runtime',lambda:{'runtime':'pinned'})
    monkeypatch.setattr(E,'validate_output',lambda p,*a:Path(p))
    monkeypatch.setattr(E,'PopulationSpecification',lambda *a:spec)
    monkeypatch.setattr(E,'closed_inputs',lambda *a:(units,units,[],[],None,[],['committed'],{}))
    args={'evaluation':'competitor','units':units,'output':output,'specifications':REPO/'specifications'}
    assert E.run_evaluation(**args,workers=48)==summary
    saved=(output/'evaluation_plan.json').read_bytes()
    assert E.run_evaluation(**args,workers=1)==summary
    assert (output/'evaluation_plan.json').read_bytes()==saved
    spec.scientific_rng_identity='changed'
    with pytest.raises(ValueError,match='resume input/runtime/code'):
        E.run_evaluation(**args,workers=1)


def test_inference_checks_computing_process_after_imports(monkeypatch,tmp_path):
    calls=[]
    def refuse(*args):
        # The actual numerical module is already loaded in the checked process.
        assert E.evaluate_g2a_records.__module__=='born_ladder.snapshot.g2a'
        calls.append(args)
        raise ValueError('incompatible computing runtime')
    monkeypatch.setattr(E,'stage_identity',refuse)
    with pytest.raises(ValueError,match='computing runtime'):
        E.run_evaluation(evaluation='competitor',units=tmp_path,output=tmp_path/'out')
    assert calls


def test_attachment_requires_passed_structural_commitment(monkeypatch,tmp_path):
    census=tmp_path/'census';census.mkdir();units=tmp_path/'units';units.mkdir()
    (census/'complete.json').write_text('{"status":"FAILED"}')
    monkeypatch.setattr(A,'stage_identity',lambda *a:{})
    with pytest.raises(ValueError,match='not complete'):
        A.run_attachments(census=census,units=units,output=tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_comparison_requires_exact_binary64_and_order():
    c=Comparison();c.compare('values',[0.0,1.0],[-0.0,1.0])
    assert not c.result()['overall_agreement']
    c=Comparison();c.compare('ordered_cohort',['first','second'],['second','first'])
    assert not c.result()['overall_agreement']


def test_descriptive_quantiles_exact_and_unrounded():
    q=quantiles([0.125,0.25,0.5,1.0])
    assert q['n']==4
    assert q['exact']['q1']=='7/32' and q['exact']['median']=='3/8' and q['exact']['q3']=='5/8'


@pytest.mark.data
def test_full_retained_evaluation_comparison():
    import os
    from born_ladder.reproduction.evaluation_comparison import compare_evaluation
    if not os.environ.get('E2E_P4_OUTPUT') or not os.environ.get('E2E_P4_REFERENCE'):
        pytest.skip('set E2E_P4_OUTPUT and E2E_P4_REFERENCE to generated and retained evaluation JSON')
    assert compare_evaluation(os.environ['E2E_P4_OUTPUT'],os.environ['E2E_P4_REFERENCE'])['overall_agreement']


def test_population_io_adapter_keeps_scientific_rng_and_budget():
    from born_ladder.reproduction.specification import PublicSpecification
    for name,version in [('competitor','v8'),('cross-term','v24')]:
        spec=E.PopulationSpecification(REPO/'specifications',name)
        original=PublicSpecification(REPO/'specifications',version)
        assert spec.scientific_rng_identity==original.scientific_rng_identity
        assert spec.get('/inference')==original.get('/inference')
        assert spec.get('/inference/bootstrap/replicates')==20000
    spec=E.PopulationSpecification(REPO/'specifications','competitor')
    assert spec.get('/artifact_paths/artifacts/g2a')[2]=='rb1v2_g2a_evaluation.json'
    assert spec.get('/provenance')=={}  # no invented launch attestation


def test_historical_full_sign_enumerations_and_holm():
    from born_ladder.snapshot.g2a import _conditional_sign_p,_holm
    from born_ladder.snapshot.statistics_helpers import _conditional_sign_counts
    assert _conditional_sign_counts([1.0]*20)==(2,1,2**20)
    assert _conditional_sign_p([1.0]*20)==(2/(2**20),1/(2**20))
    assert _conditional_sign_counts([-1.0,1.0])==(4,3,4)
    assert _holm({'a':0.01,'b':0.04,'c':0.9})=={'a':0.03,'b':0.08,'c':0.9}


def test_post_production_comparison_rejects_missing_endpoint(tmp_path):
    from born_ladder.reproduction.evaluation_comparison import compare_evaluation
    generated=tmp_path/'generated.json';reference=tmp_path/'reference.json'
    generated.write_text('{"statistics":{"raw":{"point":0.25}}}')
    reference.write_text('{"statistics":{"raw":{"point":0.25},"pkg":{"point":0.25}}}')
    assert not compare_evaluation(generated,reference)['overall_agreement']


def test_cross_term_scientific_ast_has_only_scheduling_adapter():
    tree=ast.parse((REPO/'src/born_ladder/snapshot/g2c_evaluate.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='evaluate_g2c_records')
    reference=json.loads((Path(__file__).parent/'fixtures/e2e_source_equivalence.json').read_text())
    module=next(m for m in reference['modules'] if m['public_module']=='src/born_ladder/snapshot/g2c_evaluate.py')
    expected=module['definitions']['evaluate_g2c_records']['historical_normalized_ast_sha256']
    normalized=copy.deepcopy(node)
    pairs=[(arg,default) for arg,default in zip(normalized.args.kwonlyargs,normalized.args.kw_defaults)
           if arg.arg!='rotation_validator']
    normalized.args.kwonlyargs=[p[0] for p in pairs];normalized.args.kw_defaults=[p[1] for p in pairs]
    normalized.body=[n for n in normalized.body if not (isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='rotation_validate' for t in n.targets))]
    class UndoScheduling(ast.NodeTransformer):
        def visit_Constant(self,n):
            if isinstance(n.value,str):n.value=n.value.replace('ledger','record')
            return n
        def visit_Name(self,n):
            if n.id=='rotation_validate':n.id='validate_g2c_v22_rotation_evidence'
            return n
    normalized=UndoScheduling().visit(normalized)
    assert hashlib.sha256(ast.dump(normalized,include_attributes=False).encode()).hexdigest()==expected


def test_checked_rotations_reject_changed_inputs_and_duplicates():
    from born_ladder.reproduction.rotation_admission import CheckedRotations,fingerprint
    from types import SimpleNamespace
    spec=SimpleNamespace(scientific_rng_identity='fixed scientific identity')
    source={'kind_cell_id':'one','p':[0.25]};control={'pass':True};detail={'gap':0.125}
    digest=fingerprint(spec.scientific_rng_identity,source,control,detail)
    value={'rotation_pass':True}
    checked=CheckedRotations([('one',digest,value)])
    assert checked(spec,source,control,detail)==value
    with pytest.raises(ValueError,match='input binding'):
        checked(spec,{**source,'p':[0.5]},control,detail)
    with pytest.raises(ValueError,match='duplicate'):
        CheckedRotations([('one',digest,value),('one',digest,value)])


def test_rotation_worker_checks_runtime_before_loading_contract(monkeypatch):
    from born_ladder.reproduction import rotation_admission as R
    R._SPEC=None
    def refuse(*a):raise ValueError('worker actual runtime mismatch')
    monkeypatch.setattr(R,'stage_identity',refuse)
    with pytest.raises(ValueError,match='worker actual'):
        R.initialize(REPO/'specifications')
    assert R._SPEC is None


@pytest.mark.parametrize('identities', [['second','first'],['first','first']])
def test_closed_collection_rejects_reordered_or_duplicate_dispositions(monkeypatch,tmp_path,identities):
    parent=tmp_path/'collection';parent.mkdir()
    (parent/'source_dispositions.jsonl').write_text(''.join(json.dumps({'invocation_id':i,'status':'completed'})+'\n' for i in identities))
    invocations=tmp_path/'invocations.json'
    invocations.write_text(json.dumps([{'invocation_id':'first'},{'invocation_id':'second'}]))
    info={'complete':True,'completed_invocations':2,'expected_invocations':2,'path':'collection'}
    monkeypatch.setattr(E,'collection_inputs',lambda *a:(tmp_path,{},invocations,None,{},None,info))
    with pytest.raises(ValueError,match='ordered|duplicate'):
        E.closed_inputs(tmp_path,'competitor',REPO/'specifications')


@pytest.mark.data
def test_parallel_admission_matches_serial_on_retained_inputs():
    import os
    from born_ladder.reproduction.rotation_admission import parallel_rotations
    from born_ladder.snapshot.g2c_controls import validate_g2c_v22_rotation_evidence,gradual_underflow_certificate
    from born_ladder.snapshot.evidence import g2c_control_input_projection
    root=os.environ.get('E2E_P4_UNITS')
    if not root:pytest.skip('set E2E_P4_UNITS to the historical-stack cross-term P2b root')
    try:E.stage_identity(REPO/'specifications','predictive')
    except ValueError as error:pytest.skip('run this node in the checked predictive profile: '+str(error))
    spec=E.PopulationSpecification(REPO/'specifications','cross-term')
    sources=[];controls=[];evidence={}
    for directory in sorted((Path(root)/'invocations').glob('*/attempt_0001')):
        if not (directory/'units.jsonl').exists():continue
        rows=E.jsonl(directory/'units.jsonl')
        if not rows or not rows[0]['eligibility']:continue
        row=rows[0];key=row['kind_cell_id']
        sources.append(g2c_control_input_projection(row))
        controls.append(next(c for c in E.jsonl(directory/'controls.jsonl') if c['kind_cell_id']==key))
        evidence[key]=E.read(directory/'rotation_evidence.json')[key]
        if len(sources)==2:break
    assert len(sources)==2
    callback=parallel_rotations(REPO/'specifications',sources,controls,evidence,2)
    for source,control in zip(sources,controls):
        with gradual_underflow_certificate():
            serial=validate_g2c_v22_rotation_evidence(spec,source,control,evidence[source['kind_cell_id']])
        parallel=callback(spec,source,control,evidence[source['kind_cell_id']])
        assert compare_exact(serial,parallel)


def compare_exact(a,b):
    from born_ladder.snapshot.evidence import _g2c_exact_projection_equal
    return _g2c_exact_projection_equal(a,b)


@pytest.mark.data
def test_complete_retained_attachment_scientific_comparison():
    import os
    from born_ladder.reproduction.evaluation_comparison import compare_values
    root=os.environ.get('E2E_P4_ATTACHMENTS');reference=os.environ.get('E2E_P4_CENSUS_REFERENCE')
    if not root or not reference:
        pytest.skip('set E2E_P4_ATTACHMENTS and E2E_P4_CENSUS_REFERENCE')
    root,reference=Path(root),Path(reference)
    seal=E.read(root/'complete.json');E.verify_artifacts(root,seal['artifacts'])
    directory=root/seal['summary']['directory']
    a=E.read(directory/'attachments.json');b=E.read(reference/'attachments.json')
    for x,y in zip(a,b):
        x['diagnostics'].pop('wall_seconds');y['diagnostics'].pop('wall_seconds')
    assert compare_values(a,b)['overall_agreement']
    assert compare_values(E.read(directory/'descriptive_summaries.json'),E.read(reference/'descriptive_summaries.json'))['overall_agreement']


def test_closed_controls_are_bound_and_ordered(tmp_path):
    from born_ladder.archive import sha
    directories=[]
    for index in range(2):
        p=tmp_path/str(index);p.mkdir();directories.append(p)
        (p/'controls.jsonl').write_text(json.dumps({'kind_cell_id':str(index),'nondegenerate':True})+'\n')
    path=tmp_path/'aggregate.jsonl'
    path.write_bytes(b''.join((p/'controls.jsonl').read_bytes() for p in directories))
    assert E.validate_control_stream(path,directories)==sha(path)
    path.write_bytes(b''.join((p/'controls.jsonl').read_bytes() for p in reversed(directories)))
    with pytest.raises(ValueError,match='closed control stream'):
        E.validate_control_stream(path,directories)
    path.write_text('{"kind_cell_id":"0","nondegenerate":false}\n{"kind_cell_id":"1","nondegenerate":true}\n')
    with pytest.raises(ValueError,match='closed control stream'):
        E.validate_control_stream(path,directories)
