"""Scientific paper values require run-derived extractors, not ledger agreement."""
import io
import json
from fractions import Fraction as Q
from pathlib import Path

import pytest

from born_ladder.archive import sha
from born_ladder.reproduction.comparison_policy import PolicyComparison
from born_ladder.reproduction.full_comparison import compare_paper
from born_ladder.reproduction import paper_census as P


def put(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))


def seal(root,summary):
    put(root/'complete.json',{'status':'PASS','summary':summary,'artifacts':[
        {'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
        for p in sorted(root.rglob('*')) if p.is_file() and p.name!='complete.json']})


@pytest.fixture
def census(tmp_path):
    root=tmp_path/'census';completed=[];original=[];inventory=[];pairs=[]
    w=[Q(-1),Q(1)]+[Q(0)]*30;labels=[i%2 for i in range(32)]
    context={'born':{'p_theory':[1/32]*32,'sym_eigvec_basis':[list(map(float,w))]},
             'exact':{'w':list(map(str,w)),'s':'2'},'lens':{k:labels for k in ('raw_by_state','package_by_state','joint_by_state')}}
    atoms=[]
    for field in context['lens']:
        for label in (0,1):
            block=[i for i,l in enumerate(labels) if l==label];a=sum(w[i] for i in block);b=sum(w[i]**2 for i in block)
            atoms.append({'context':field,'atom':label,'states':block,'Gram_det_exact':str(len(block)*b-a*a),
                          'effect_exact':[[str(Q(len(block),32)),str(a/32)],[str(a/2),str(b/2)]],'positive':True})
    for index,gap in enumerate(('1/10','1/5')):
        uid='unit-'+str(index);directory='contexts/'+uid
        native={'status':'PASS','C_premises':{'status':'PASS'},'correspondence_status':'PASS'}
        cert={'index':index,'unit_id':uid,'overall_status':'PASS','certificates':{
            'C_premises':{'status':'PASS','atom_count':6,'strict_positive_atom_count':6,'zero_atom_count':0,'negative_atom_count':0,'atom_certificates':atoms},
            'correspondence':{'status':'PASS','constructor_literal_bit_equality_status':'PASS','uniform_projector_TV_bound_exact':'1/200',
                              'own_input_exact_source_vs_landed_maximum_error':'1/300','uniform_floating_envelope':{'total_with_projector_TV_exact':'1/100'}},
            'strictness':{'status':'PASS','pair':[0,2],'first_separating_readout':{'difference_exact':gap,'left_exact':gap,'right_exact':'0'}}}}
        for name,value in [('CONTEXT.json',context),('structural_completion_certificate.json',cert),('original_implementation.json',native),
                           ('atom_classes.json',P.atom_classes(context,cert))]:put(root/directory/name,value)
        completed.append({'index':index,'unit_id':uid,'context_directory':directory,'status':'PASS'})
        original.append({'index':index,'unit_id':uid,**native})
        inventory.append({'unit_id':uid,'provenance_key':{'experiment':'EXP-102','audit_metadata':{'config_name':'A'}}})
        pairs.append({'case':index,'gap_exact':gap})
    put(root/'summary/structural_completion_results.json',completed);put(root/'summary/original_implementation_results.json',original)
    put(root/'summary/maximal_gap_witnesses.json',pairs);put(root/'summary/robust_bound_outcomes.json',P.robust_outcomes(pairs))
    put(root/'inventory/INVENTORY.json',inventory)
    put(root/'inventory/RETURN_CARRIER_INVENTORY.json',{'rows':[{'retained_rank':2},{'retained_rank':2}],
                                                     'rank_counts':{'2':2},'paired_unit_contexts':2})
    seal(root,{'summary_directory':'summary','inventory_directory':'inventory'})
    return tmp_path


def test_missing_full_cohort_scientific_extractor_is_unresolved(tmp_path):
    c=PolicyComparison(io.StringIO())
    result=compare_paper(c,{'entries':[{'id':'FutureCensusValue','value':42,'source':'ledger-only',
                                     'evidence_type':'full_cohort_external_exact_check'}]},
                         [{'macro':'FutureCensusValue','id':'FutureCensusValue','format':'int'}],[],tmp_path,{}, {})
    assert result['status']=='UNRESOLVED' and not result['overall_agreement']
    assert result['unavailable_paper_quantities'][0]['macro']=='FutureCensusValue'
    assert not result['documentary_or_formal_macros'] and not result['paper_macros_compared']


def test_false_scientific_ledger_and_manuscript_together_fail(census):
    paper=census/'paper.tex';paper.write_text('% >>> BEGIN GENERATED RESULT MACROS\n'+
        r'\newcommand{\CensusCases}{\ensuremath{3}}'+'\n% <<< END GENERATED RESULT MACROS\n'+r'\CensusCases{}')
    c=PolicyComparison(io.StringIO())
    result=compare_paper(c,{'entries':[{'id':'CensusCases','value':3,'source':'scratch/earlier/census/complete.json',
                                      'evidence_type':'full_cohort_external_exact_check'}]},
                        [{'macro':'CensusCases','id':'CensusCases','format':'int'}],[],census,{'census':'census'}, {},paper=paper)
    assert result['status']=='FAIL' and not result['overall_agreement']
    assert c.groups['manuscript_defined_display_vs_ledger']['exact']==1
    assert c.groups['paper_full_precision']['failed']==1
    row=result['paper_quantity_checks'][0]
    assert row['ledger_source']=='scratch/earlier/census/complete.json'
    assert row['regenerated_value']==2 and not row['full_precision_exact']
    assert str(census/'census/complete.json') in row['regenerated_source']['sources']
    assert not result['documentary_or_formal_macros']


def test_census_counts_bounds_and_configurations_come_from_run(census):
    view=P.census_quantities(census/'census');v=view['full_cohort']
    assert (v['CensusCases'],v['ArchiveCases'],v['WitnessCount'],v['ActiveAtoms'])==(2,2,2,12)
    assert (v['RegisteredPass'],v['RegisteredRobustPass'],v['RegisteredRobustFail'],v['AmendedRobustPass'])==(2,1,1,2)
    assert v['CertificateProjectorMin']==v['CertificateProjectorMax']=='1/200'
    assert v['RobustGapMinimumLower']==v['RobustGapMinimumUpper']=='1/10'
    assert view['configuration_counts']=={'EXP-102':{'A':2}}


def test_changed_committed_census_input_is_unresolved(census):
    path=census/'census/contexts/unit-0/CONTEXT.json';put(path,{'changed':'input'})
    with pytest.raises(ValueError,match='committed paper input changed'):P.census_quantities(census/'census')


def test_configuration_binding_uses_identity_not_position():
    row=P.binding({'evidence_type':'full_cohort_external_exact_check','source':"old/census#configuration ('EXP-102', 'A/B')"},'ConfigCasesA')
    assert row['pointer']=='/EXP-102/A~1B'


def test_canonical_population_summaries_are_not_selected_case_summaries(tmp_path,monkeypatch):
    from born_ladder.reproduction import v25_paper as V
    calls=[]
    def fresh(root,components,specifications):
        calls.append(root)
        return {'summaries':{'raw':{'exact':{'median':'1/4'}}},
                'provenance':{'sources':['own/contexts/a','own/contexts/b'],'aggregation':'two-case canonical TV; exact dyadic type-seven median'}}
    monkeypatch.setattr(V,'canonical_population',fresh)
    monkeypatch.setattr(V,'selected_canonical',lambda *a:pytest.fail('selected fixture cannot supply population summary'))
    result=compare_paper(PolicyComparison(io.StringIO()),{'entries':[{'id':'CanonicalDiagRawMedian','value':'1/4','source':'old/internal/summary',
                        'evidence_type':'full_cohort_external_exact_check'}]},
                        [{'macro':'CanonicalDiagRawMedian','id':'CanonicalDiagRawMedian','format':'sig:4'}],[],tmp_path,
                        {'census':'census','attachments':'attachments'}, {})
    assert result['status']=='PASS' and calls==[tmp_path]
    assert result['paper_quantity_checks'][0]['ledger_source']=='old/internal/summary'
    assert result['paper_regenerated_evidence']['canonical_census']['sources']==['own/contexts/a','own/contexts/b']


def test_paper_full_precision_rejects_one_ulp(tmp_path):
    import math
    actual=math.nextafter(.25,1.)
    c=PolicyComparison(io.StringIO())
    result=compare_paper(c,{'entries':[{'id':'Value','value':'.25','evidence_type':'recomputed_by_public_command'}]},
        [{'macro':'Value','id':'Value','format':'sig:4'}],[{'macro':'Value','evaluation':'competitor','pointer':'/value'}],
        tmp_path,{}, {'competitor':{'value':actual}})
    assert result['status']=='FAIL' and c.groups['paper_full_precision']['failed']==1
    assert c.groups['manuscript_display']['exact']==1


def test_missing_scientific_extractor_propagates_to_overall_verdict(tmp_path,monkeypatch):
    from born_ladder.reproduction import full_comparison as F
    root=tmp_path/'run';root.mkdir()
    components={k:k for k in ('census','worked','attachments','lean','locked','test_b','competitor_units','cross_term_units','competitor_evaluation','cross_term_evaluation')}
    put(root/'pipeline.json',{'profile':'full','components':components});put(root/'verification_report.json',{})
    put(tmp_path/'archive.json',{'schema':'born_reproduction_reference_v1','roots':{}})
    put(tmp_path/'ledger.json',{'entries':[{'id':'UnboundScience','value':1,'source':'unbound',
                                         'evidence_type':'full_cohort_external_exact_check'}]})
    put(tmp_path/'aliases.json',[{'macro':'UnboundScience','id':'UnboundScience','format':'int'}])
    paper=tmp_path/'paper.tex';paper.write_text('% >>> BEGIN GENERATED RESULT MACROS\n'+
        r'\newcommand{\UnboundScience}{\ensuremath{1}}'+'\n% <<< END GENERATED RESULT MACROS\n'+r'\UnboundScience{}')
    monkeypatch.setattr(F,'protocol',lambda *a:{'verdict':'PASS'})
    result=F.run_comparison(run=root,archive=tmp_path/'archive.json',output=tmp_path/'comparison',
                            ledger=tmp_path/'ledger.json',aliases=tmp_path/'aliases.json',paper=paper)
    assert result['reported_results_reproduced']=='UNRESOLVED'
    saved=json.loads((Path(result['report']).parent/'paper.json').read_bytes())
    assert saved['status']=='UNRESOLVED' and saved['unavailable_paper_quantities'][0]['macro']=='UnboundScience'


def test_canonical_scoring_uses_all_cases_and_registered_rounding(census,monkeypatch):
    from born_ladder.reproduction.v25 import canonical
    from born_ladder.reproduction import stage_environment as S
    root=census/'attachments';records=[]
    for index in (0,1):
        uid='unit-'+str(index);records.extend([{'unit_id':uid,'view':view,'status':'PASS','fields':{'eligibility':True,'dtv_loss':{'q_diag':.25}}} for view in ('raw','pkg')])
        matrix=[[1.]+[0.]*31,[0.]+[1.]*31]
        for view,counts in [('raw',[3,1] if index==0 else [1,3]),('pkg',[2,2])]:
            row={'unit_id':uid,'total_count':4,'integer_counts':counts,
                 'M_raw_or_content_hash' if view=='raw' else 'M_pkg_or_content_hash':matrix,
                 'unrounded_y_raw' if view=='raw' else 'unrounded_y_pkg':[x/4 for x in counts]}
            put(root/'attempt/contexts'/uid/(view+'_original.jsonl'),row)
    put(root/'attempt/attachments.json',records)
    put(root/'attempt/descriptive_summaries.json',P.summarise(records,2));seal(root,{'directory':'attempt'})
    monkeypatch.setattr(S,'check_current',lambda profile:{'numpy':'stub pinned runtime'})
    called=[]
    def public(emitted,preparation,*,refinement):
        called.append((emitted,preparation,refinement))
        return {'status':'certified','rank':2,'bits':384,'input_sha256':'stub','q_diag_canonical':[.75,.25]+[0.]*30}
    monkeypatch.setattr(canonical,'construct',public)
    result=P.canonical_quantities(census/'census',root,'specifications')
    assert len(called)==2 and all(call[2]==(384,768,1536,3072,4096) for call in called)
    assert result['summaries']['raw']['exact']['median']=='1/4'
    assert result['summaries']['raw']['exact']['q1']=='1/8'
    assert result['summaries']['pkg']['exact']['median']=='1/4'
    attachments=P.attachment_quantities(root)
    assert attachments['rows']==4 and next(r for r in attachments['records'] if r['view']=='raw' and r['metric']=='dtv_loss' and r['model_or_recorded_contrast']=='q_diag')['quantiles']['exact']['median']=='1/4'


def test_canonical_cli_selects_public_predictive_v25_runtime(tmp_path,monkeypatch):
    import born_ladder.__main__ as M
    from born_ladder.reproduction import stage_environment as S
    calls=[]
    monkeypatch.setattr(S,'ensure_environment',lambda profile,*a:calls.append(profile) or None)
    monkeypatch.setattr(P,'canonical_quantities',lambda *a:{'summaries':{}})
    assert M.main(['reproduce','paper-canonical','--census',str(tmp_path/'census'),'--attachments',str(tmp_path/'attachments')])==0
    assert calls==['predictive_v25']


def test_failed_canonical_runtime_is_unresolved(tmp_path,monkeypatch):
    import subprocess
    def failed(*a,**kw):raise subprocess.CalledProcessError(1,a[0])
    monkeypatch.setattr(subprocess,'run',failed)
    result=compare_paper(PolicyComparison(io.StringIO()),{'entries':[{'id':'CanonicalDiagRawMedian','value':'1/4',
        'source':'old/internal','evidence_type':'full_cohort_external_exact_check'}]},
        [{'macro':'CanonicalDiagRawMedian','id':'CanonicalDiagRawMedian','format':'sig:4'}],[],tmp_path,
        {'census':'census','attachments':'attachments'}, {})
    assert result['status']=='UNRESOLVED' and 'child exit 1' in result['unavailable_paper_quantities'][0]['reason']
