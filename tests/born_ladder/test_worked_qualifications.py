"""Round-9 semantic qualifications: corruptions must not become dispositions."""
import copy
import io
import json
import os
from pathlib import Path

import pytest

from born_ladder.reproduction.comparison_policy import PolicyComparison
from born_ladder.reproduction import worked_qualifications as W


def evidence():
    return {key:{'status':'PASS','checks':{'witness_id':'one registered witness'}}
            for key in ('pair','completion','finite','basis','non_density','joins','carrier','strictness','routes')}


def test_named_dispositions_and_same_strictness_witness():
    c=PolicyComparison(io.StringIO());e=evidence()
    rows=W.qualify(c,dict((path,value) for path,value,_ in W.QUALIFICATIONS),e)
    assert all(r['status']=='PASS' and r['historical_matches']==0 for r in rows)
    assert rows[3]['disposition']=='NON_TRACE_EXISTENCE_REPRODUCED; POLYTOPE_CHARACTERIZATION_RETAINED'
    assert rows[4]['disposition']=='DECLARED_BOUNDARY_UNCHANGED'
    assert rows[5]['disposition']=='HISTORICAL_METHOD_ONLY'
    assert rows[9]['disposition']=='HISTORICAL_METHOD_QUALIFICATION; ROUTE_AGREEMENT_RECHECKED'
    assert rows[8]['semantic_checks']==rows[11]['semantic_checks']
    assert 'no vertex enumeration' in rows[5]['regenerated_method_scope']


@pytest.mark.parametrize('index',range(12))
def test_each_retained_qualification_type_substitution_fails(index):
    values=dict((path,value) for path,value,_ in W.QUALIFICATIONS)
    path,expected,_=W.QUALIFICATIONS[index]
    values[path]=int(expected) if type(expected) is bool else [expected]
    c=PolicyComparison(io.StringIO());rows=W.qualify(c,values,evidence())
    assert rows[index]['status']=='FAIL'
    assert not c.result()['overall_agreement']


def test_false_informational_complete_flag_fails():
    values=dict((path,value) for path,value,_ in W.QUALIFICATIONS)
    values[W.QUALIFICATIONS[2][0]]=False
    c=PolicyComparison(io.StringIO());rows=W.qualify(c,values,evidence())
    assert rows[2]['status']=='FAIL' and not c.result()['overall_agreement']


def test_full_driver_resolves_worked_with_limits_and_preserves_boundary(tmp_path,monkeypatch):
    from born_ladder.reproduction import full_comparison as F, worked_comparison as C
    components={key:key for key in ('worked','census','attachments','competitor_evaluation','cross_term_evaluation',
                                   'test_b','locked','lean','competitor_units','cross_term_units')}
    run=tmp_path/'run';(run/'worked/selected').mkdir(parents=True);(run/'worked/original').mkdir()
    for name in ('selected','original'):(run/'worked'/name/'certificates.json').write_text('{}')
    (run/'pipeline.json').write_text(json.dumps({'profile':'full','components':components}))
    archive=tmp_path/'archive.json';archive.write_text(json.dumps({'schema':'born_reproduction_reference_v1','roots':{'repo':str(tmp_path)},'components':{'worked':'repo/reference'}}))
    monkeypatch.setattr(F,'protocol',lambda *a:{'verdict':'UNRESOLVED','stages':{}})
    def compare(generated,reference,*,comparison,**kwargs):
        comparison.compare('carrier_check',True,True)
        assert kwargs['source_runs']==[run/'runs/worked'] and kwargs['lean_root']==run/'lean'
        return {'overall_agreement':True,'resolved_with_declared_limits':True,
                'worked_qualifications':W.qualify(comparison,dict((p,v) for p,v,_ in W.QUALIFICATIONS),evidence()),
                'generated_H_boundary':'UNRESOLVED; no extension claimed'}
    monkeypatch.setattr(C,'compare_worked_cases',compare)
    result=F.run_comparison(run=run,archive=archive,output=tmp_path/'out')
    report=json.loads(Path(result['report']).read_text())
    assert report['reported_results_reproduced']['stages']['worked']['status']=='PASS_WITH_DECLARED_LIMITS'
    assert result['reported_results_reproduced']=='UNRESOLVED'  # missing other evidence still blocks
    assert 'Generated-H mathematical boundary: UNRESOLVED; no extension claimed' in Path(result['report']).with_suffix('.md').read_text()


@pytest.mark.parametrize('group',('pair','completion','finite','basis','non_density','joins','carrier','strictness','routes'))
def test_unavailable_required_evidence_stays_unresolved(group):
    e=evidence();e[group]={'status':'UNRESOLVED','reason':'required input missing'}
    c=PolicyComparison(io.StringIO());rows=W.qualify(c,dict((p,v) for p,v,_ in W.QUALIFICATIONS),e)
    assert any(r['status']=='UNRESOLVED' for r in rows)
    assert not any(r['status']=='FAIL' for r in rows)


@pytest.fixture(scope='module')
def real_worked():
    root=os.environ.get('E2E_P8_WORKED_OUTPUT')
    reference=os.environ.get('E2E_P8_WORKED_REFERENCE')
    non_trace=os.environ.get('E2E_P8_NON_TRACE_REFERENCE')
    if not all((root,reference,non_trace)):pytest.skip('set the three E2E_P8 worked input variables')
    root=Path(root)
    return root,Path(reference),Path(non_trace),{name:W.read(root/name/'CONTEXT.json') for name in ('original','selected')}, {name:W.read(root/name/'certificates.json') for name in ('original','selected')}


@pytest.mark.data
@pytest.mark.parametrize('probe',('zero_determinant','wrong_lens','wrong_frame','wrong_unit','wrong_K','changed_barycenter','non_positive_root','wrong_strictness_witness'))
def test_real_scientific_qualifications_fail(real_worked,monkeypatch,probe):
    root,reference,_,contexts,certs=real_worked
    contexts=copy.deepcopy(contexts);certs=copy.deepcopy(certs)
    if probe=='zero_determinant':certs['original']['finite_family']['non_density']['coordinate_determinant_exact']='0'
    elif probe=='wrong_lens':contexts['selected']['lens']['joint_by_state'][0]+=1
    elif probe=='wrong_frame':contexts['selected']['born']['sym_eigvec_basis'][0][0]+=0.01
    elif probe=='wrong_unit':contexts['selected']['identity']['seed']+=1
    elif probe=='wrong_K':contexts['selected']['kernel'][0][0]+=0.01
    elif probe=='changed_barycenter':certs['original']['ensemble']['pair_certificate']['coordinate_barycenter'][0][0]='0'
    elif probe=='non_positive_root':certs['original']['ensemble']['pair_certificate']['left'][0][0]='-1000000'
    else:certs['selected']['strictness']['certificate']['point_indices'][0]+=1
    normal=W.read
    def read(path):
        path=Path(path)
        if path.parent.parent==root and path.name in ('CONTEXT.json','certificates.json'):
            return contexts[path.parent.name] if path.name=='CONTEXT.json' else certs[path.parent.name]
        return normal(path)
    monkeypatch.setattr(W,'read',read)
    c=PolicyComparison(io.StringIO());c.compare('RI_six_route_control',True,True)
    e=W.semantic_evidence(c,root)
    rows=W.qualify(c,W.retained_values(reference),e)
    expected=2 if probe=='zero_determinant' else 6 if probe.startswith('wrong_') and probe!='wrong_strictness_witness' else 8 if probe=='wrong_strictness_witness' else 10
    assert rows[expected]['status']=='FAIL'
    assert not c.result()['overall_agreement']
    if probe=='wrong_strictness_witness':assert rows[11]['status']=='FAIL'


@pytest.mark.data
def test_real_complete_comparison_and_retained_zero_determinant(real_worked,monkeypatch):
    from born_ladder.reproduction import worked_comparison as C
    root,reference,non_trace,_,_=real_worked
    c=PolicyComparison(io.StringIO());r=C.compare_worked_cases(root,reference,non_trace=non_trace,comparison=c)
    assert r['overall_agreement'] and r['resolved_with_declared_limits']
    assert not c.unresolved_reference_fields
    assert len(r['worked_qualifications'])==12
    assert r['worked_qualifications'][8]['semantic_checks']==r['worked_qualifications'][11]['semantic_checks']
    assert r['worked_validation_coverage']['documentary_method_historical_matches']==0
    assert r['generated_H_boundary']=='UNRESOLVED; no extension claimed'
    normal=C.read
    def read(path):
        d=normal(path)
        if Path(path)==reference/'E3/C1_certificate.json':d['coordinate_determinant_exact']='0'
        return d
    monkeypatch.setattr(C,'read',read)
    r=C.compare_worked_cases(root,reference,non_trace=non_trace,comparison=PolicyComparison(io.StringIO()))
    assert not r['overall_agreement'] and r['worked_qualifications'][2]['status']=='FAIL'
