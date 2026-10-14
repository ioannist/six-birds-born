"""Targeted P8 comparison tests. Synthetic values only; no inference runs."""
import io
import json
from pathlib import Path
import pytest
from born_ladder.reproduction.comparison_policy import PolicyComparison,render
from born_ladder.reproduction.full_comparison import compare_file,compare_tree,compare_paper,Reference,run_comparison


def assess(a,b,group='population',path=''):
    stream=io.StringIO();c=PolicyComparison(stream);c.compare(group,a,b,path)
    return c.result(),[json.loads(x) for x in stream.getvalue().splitlines()]


def test_fixed_float_threshold_reports_every_difference():
    r,d=assess([1+1e-13,1+1e-10],[1.,1.])
    assert not r['overall_agreement'] and r['field_groups']['population']['accepted']==1
    assert len(d)==2 and d[0]['accepted'] and not d[1]['accepted']
    assert all(x['signed_difference'] is not None for x in d)


@pytest.mark.parametrize('group,path',[('source_scientific_inputs','/kernel'),('population','/rng_audit/words'),('population','/bootstrap_membership'),('sampled_sequences','/labels'),('population','/draw_indices')])
def test_source_and_draws_remain_exact(group,path):
    r,_=assess(1+1e-13,1.,group,path)
    assert not r['overall_agreement']


def test_decision_change_fails_despite_acceptable_float():
    r,_=assess({'loss':1+1e-13,'tie':False},{'loss':1.,'tie':True})
    assert not r['overall_agreement']


def test_membership_order_types_and_extra_fields_fail():
    for a,b in [(['b','a'],['a','b']),([1],[]),(1,1.),({'gate':True,'extra':2},{'gate':True})]:
        assert not assess(a,b)[0]['overall_agreement']


def test_process_projection_is_named_and_recorded():
    r,d=assess({'wall_seconds':7,'loss':1.},{'wall_seconds':4,'loss':1.})
    assert r['overall_agreement'] and d[0]['rule']=='process-only projection'
    assert not assess({'table_hash':'new'},{'table_hash':'old'})[0]['overall_agreement']


def test_tree_reports_missing_files_and_binary_draw_changes(tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';a.mkdir();b.mkdir()
    (a/'draw.npy').write_bytes(b'new');(b/'draw.npy').write_bytes(b'old')
    (a/'extra.json').write_text('{}')
    stream=io.StringIO();c=PolicyComparison(stream);compare_tree(c,'rng_and_draws',a,b)
    assert not c.result()['overall_agreement']
    assert 'file_membership' in stream.getvalue() and 'byte_equal' in stream.getvalue()


def test_paper_display_must_agree_even_within_threshold(tmp_path):
    ledger={'entries':[{'id':'Point','value':'0.12345000000001','evidence_type':'recomputed_by_public_command'}]}
    aliases=[{'macro':'Point','id':'Point','format':'sig:4'}]
    bindings=[{'macro':'Point','evaluation':'competitor','pointer':'/point'}]
    c=PolicyComparison(io.StringIO())
    result=compare_paper(c,ledger,aliases,bindings,tmp_path,{}, {'competitor':{'point':.12344999999999}})
    assert not result['overall_agreement']
    assert c.groups['paper_full_precision']['failed']==1
    assert c.groups['manuscript_display']['failed']==1


def test_missing_paper_extractor_is_not_a_match(tmp_path):
    c=PolicyComparison(io.StringIO())
    r=compare_paper(c,{'entries':[{'id':'Point','value':'1','evidence_type':'recomputed_by_public_command'}]},
        [{'macro':'Point','id':'Point','format':'int'}],[],tmp_path,{}, {})
    assert not r['overall_agreement'] and r['unavailable_paper_quantities'][0]['macro']=='Point'
    assert not any(g['failed'] for g in r['field_groups'].values())


def test_directed_rounding_matches_ledger_conventions():
    assert render(-.09157245207086599,'sig:4','lower')=='-0.09158'
    assert render(.09908132256376655,'sig:4','upper')=='0.09909'
    assert render(1000,'int')=='1{,}000'


def test_incomplete_full_run_never_gets_a_pass(tmp_path):
    run=tmp_path/'run';run.mkdir()
    components={'worked':'worked','census':'census','attachments':'attachments',
        'competitor_evaluation':'evaluation/competitor','cross_term_evaluation':'evaluation/cross-term',
        'test_b':'test-b','locked':'locked','lean':'lean','competitor_units':'units/competitor','cross_term_units':'units/cross-term'}
    (run/'pipeline.json').write_text(json.dumps({'profile':'full','components':components}))
    archive=tmp_path/'archive.json';archive.write_text(json.dumps({'schema':'born_reproduction_reference_v1','roots':{}}))
    result=run_comparison(run=run,archive=archive,output=tmp_path/'comparison',specifications=Path(__file__).resolve().parents[2]/'specifications')
    assert result['protocol_executed_successfully']=='UNRESOLVED'
    assert result['reported_results_reproduced']=='UNRESOLVED'
    assert Path(result['report']).is_file()


def test_reference_paths_and_output_must_not_escape(tmp_path):
    p=tmp_path/'ref.json';p.write_text(json.dumps({'schema':'born_reproduction_reference_v1','roots':{'data':str(tmp_path)}}))
    with pytest.raises(ValueError,match='escapes'):Reference(p).path('data/../escape')


def test_automatic_paper_bindings_and_exact_aggregation():
    from born_ladder.reproduction.full_comparison import automatic_paper_binding,expression
    e={'source':'large/rb1v2_g2c_v23_evaluation.json#/statistics/raw/point_estimate'}
    assert automatic_paper_binding(e,'CrossRaw')['evaluation']=='cross-term'
    e={'source':'repo/x/g2a_evaluation.json#/statistics/raw::S2/bca_simultaneous_upper [negation; endpoints swapped]'}
    assert automatic_paper_binding(e,'ServiceLower')['negate']
    records=[{'provenance_key':{'experiment':'EXP-105'},'audit_metadata':{'config_name':'A'},'gap':'1/3'},
             {'provenance_key':{'experiment':'EXP-105'},'audit_metadata':{'config_name':'B'},'gap':'-1/5'}]
    assert expression(records,'x#count(provenance_key.experiment=EXP-105,audit_metadata.config_name=A)')==1
    assert expression(records,'x#min(* /gap [absolute value])')=='1/5'
    assert expression(records,'x#median(* /gap [absolute value])')=='4/15'


def test_ordered_unit_comparator_uses_p8_policy_without_weakening_exact_report(tmp_path):
    from born_ladder.reproduction.unit_comparison import compare_records
    new={'kind_cell_id':'a','dtv_loss':{'q_full':1.+1e-13},'tie_flag':{'q_full':False}}
    old={'kind_cell_id':'a','dtv_loss':{'q_full':1.},'tie_flag':{'q_full':False}}
    path=tmp_path/'units.jsonl';path.write_text(json.dumps(new)+'\n')
    c=PolicyComparison(io.StringIO());result=compare_records(path,[json.dumps(old)],comparison=c)
    assert not result['overall_agreement'] and c.result()['overall_agreement']
    # No tolerance can admit changed dispositions or unrounded source inputs.
    new['tie_flag']['q_full']=True;path.write_text(json.dumps(new)+'\n')
    c=PolicyComparison(io.StringIO());compare_records(path,[json.dumps(old)],comparison=c)
    assert not c.result()['overall_agreement']


def test_signed_difference_extrema_are_actual_not_zero_anchored():
    r,_=assess([1.-1e-13,1.-2e-13],[1.,1.])
    assert r['field_groups']['population']['maximum_signed_difference']<0


def test_source_payloads_are_compared_recursively_with_named_metadata_projection(tmp_path):
    from born_ladder.reproduction.full_comparison import scientific_lines
    a,b=tmp_path/'new',tmp_path/'old'
    a.write_text('KEY_AUDIT_JSON {"git_sha":"new","kernel":[[1.0]],"seed":1000000001000}\n')
    b.write_text('KEY_AUDIT_JSON {"git_sha":"old","kernel":[[1.0]],"seed":1000000001000}\n')
    result,d=assess(list(scientific_lines(a)),list(scientific_lines(b)),'source_scientific_inputs')
    assert result['overall_agreement'] and result['field_groups']['source_scientific_inputs']['floats_binary64_exact']==1
    assert len(d)==1 and d[0]['path'].endswith('/git_sha')


def test_reduced_profile_is_not_compared_even_when_full_stage_paths_are_absent(tmp_path,monkeypatch):
    import born_ladder.reproduction.full_comparison as F
    components={k:k for k in ('worked','census','attachments','competitor_evaluation','cross_term_evaluation',
                              'test_b','locked','lean','competitor_units','cross_term_units')}
    root=tmp_path/'run';root.mkdir();(root/'pipeline.json').write_text(json.dumps({'profile':'smoke','components':components}))
    archive=tmp_path/'ref.json';archive.write_text(json.dumps({'schema':'born_reproduction_reference_v1','roots':{}}))
    monkeypatch.setattr(F,'protocol',lambda *args:{'verdict':'PASS','stages':{}})
    result=F.run_comparison(run=root,archive=archive,output=tmp_path/'out')
    report=json.loads(Path(result['report']).read_text())
    assert result['protocol_executed_successfully']=='PASS'
    assert result['reported_results_reproduced']=='NOT_COMPARABLE'
    assert all(s['status']=='NOT_COMPARABLE' for s in report['reported_results_reproduced']['stages'].values())


def test_reduced_predictive_draw_count_cannot_satisfy_full_comparison():
    from born_ladder.reproduction.full_comparison import predictive_draw_counts
    for evaluation,stat in [('competitor',{'replicate_estimates':[0.]*200}),
                            ('cross-term',{'bootstrap':{'replicate_estimates':[0.]*200}})]:
        with pytest.raises(ValueError,match='reduced primary bootstrap'):
            predictive_draw_counts({'statistics':{'raw':stat}},evaluation)
    stat={'replicate_estimates':[0.]*20000,'rng_audit':[{}]*20000}
    assert predictive_draw_counts({'statistics':{'raw':stat}},'competitor')=={'raw':20000}
    stat['rng_audit'].pop()
    with pytest.raises(ValueError,match='RNG audit'):
        predictive_draw_counts({'statistics':{'raw':stat}},'competitor')


def test_count_macros_are_checked_and_missing_counts_are_unresolved(tmp_path):
    from born_ladder.reproduction.full_comparison import automatic_paper_binding,expression
    assert expression([1,2],'file#length [one per case]')==2
    assert expression([{'atoms':0},{'atoms':3}],'file#count(atoms>0)')==1
    entry={'id':'Count','value':2,'source':'no extractor','evidence_type':'count_of_artifacts'}
    r=compare_paper(PolicyComparison(io.StringIO()),{'entries':[entry]},
        [{'macro':'Count','id':'Count','format':'int'}],[],tmp_path,{}, {})
    assert not r['overall_agreement'] and r['unavailable_paper_quantities']


def test_negative_zero_is_never_described_as_binary64_exact():
    r,_=assess(-0.,0.)
    assert r['field_groups']['population']['floats_binary64_exact']==0
    assert r['field_groups']['population']['accepted']==1
    assert not assess(-0.,0.,'source_scientific_inputs')[0]['overall_agreement']


def test_prediction_seals_are_storage_but_payload_and_training_hashes_remain_scientific(tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';a.mkdir();b.mkdir()
    for root,location in ((a,'new/root'),(b,'old/root')):
        (root/'p.json').write_text('{"probability":0.5}')
        (root/'p.json.seal.json').write_text(json.dumps({'path':location,'sha256':location,'bytes':5}))
    c=PolicyComparison(io.StringIO());compare_tree(c,'predictions',a,b)
    assert c.result()['overall_agreement']
    (a/'p.json').write_text('{"probability":0.7}')
    c=PolicyComparison(io.StringIO());compare_tree(c,'predictions',a,b)
    assert not c.result()['overall_agreement']
    assert not assess({'table_hash':'a'},{'table_hash':'b'})[0]['overall_agreement']


def test_locked_draws_must_have_complete_registered_incidence(tmp_path):
    import numpy as np
    from born_ladder.reproduction.full_comparison import locked_draw_counts
    folder=tmp_path/'bootstrap_cache';folder.mkdir()
    for name in ('primary','reversal','order'):
        np.save(folder/('bootstrap_identity_'+name+'_200000.npy'),np.zeros((200000,20),dtype=np.uint8))
    assert set(locked_draw_counts(tmp_path))=={'primary','reversal','order'}
    np.save(folder/'bootstrap_identity_primary_200000.npy',np.zeros((200,20),dtype=np.uint8))
    with pytest.raises(ValueError,match='reduced or invalid'):
        locked_draw_counts(tmp_path)


def test_internal_identity_tuples_preserve_integer_types():
    assert not assess(('EXP',None,840007.,32),('EXP',None,840007,32))[0]['overall_agreement']


def test_paper_rational_values_are_exact_without_float_or_spelling_coercion(tmp_path):
    ledger={'entries':[{'id':'Ray','value':'-1/1','evidence_type':'lean'}]}
    bindings=[{'macro':'Ray','evaluation':'competitor','pointer':'/ray'}]
    c=PolicyComparison(io.StringIO())
    r=compare_paper(c,ledger,[{'macro':'Ray','id':'Ray','format':'frac'}],bindings,tmp_path,{}, {'competitor':{'ray':'-1'}})
    assert r['overall_agreement'] and r['field_groups']['paper_full_precision']['exact']==1
    assert not assess('-1','-1/1','exact_context')[0]['overall_agreement']


def test_public_specification_margin_and_seed_count_are_extracted_exactly(tmp_path):
    directory=Path(__file__).resolve().parents[2]/'specifications'
    entries=[{'id':'Margin','value':'1/240','source':'source/born_route_rebuild1_spec_v24.json#/thresholds/items[id=m_cross]/value','evidence_type':'hash_bound_attachment'},
             {'id':'Seeds','value':20,'source':'source/born_route_rebuild1_spec_v24.json#/confirmation_data/campaigns/0/seeds [SeedCount]','evidence_type':'hash_bound_attachment'}]
    aliases=[{'macro':'Margin','id':'Margin','format':'frac'},{'macro':'Seeds','id':'Seeds','format':'int'}]
    r=compare_paper(PolicyComparison(io.StringIO()),{'entries':entries},aliases,[],tmp_path,{}, {},specifications=directory)
    assert r['overall_agreement'] and not r['unavailable_paper_quantities']


def test_full_driver_exercises_complete_test_b_tables_and_separates_verdicts(tmp_path,monkeypatch):
    import numpy as np
    import born_ladder.reproduction.full_comparison as F
    root=tmp_path/'run';old=tmp_path/'archive';root.mkdir();old.mkdir()
    def put(path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value)+'\n')
    components={'worked':'worked','census':'census','attachments':'attachments','competitor_evaluation':'evaluation/competitor',
        'cross_term_evaluation':'evaluation/cross-term','test_b':'test-b','locked':'locked','lean':'lean',
        'competitor_units':'units/competitor','cross_term_units':'units/cross-term'}
    put(root/'pipeline.json',{'profile':'full','components':components})
    descriptor={'schema':'born_reproduction_reference_v1','roots':{'data':str(old)},
        'components':{'test_b':'data/test-b','test_b_census':'data/test-b/census','certification':'data/test-b/certification','locked':'data/locked'}}
    put(tmp_path/'ref.json',descriptor)
    for r in (root,old):
        for name in ('eligibility.json','training_census.jsonl','sealed/full_census.jsonl','sealed/validation_census.jsonl','sealed/test_census.jsonl','sealed/recipe_audit.jsonl'):
            put(r/'test-b/census'/name,{'ordered_recipe':[0,1],'eligible':True})
        put(r/'test-b/certification/complete.json',{'status':'PASS'})
        put(r/'test-b/certification/fit.json',{'parameters':[.25,.75],'gate':True})
        put(r/'test-b/sample.commit.json',{'phase':'sample'})
        for name in ('audit_side','record_side','record_view'):
            put(r/'test-b'/name/'paths.json',{'states':[0,1,2],'labels':[1,0,1]})
        put(r/'test-b/fits/fits.json',{'selected_model':'square','training_table_hash':'same','prediction':[.25,.75]})
        put(r/'test-b/controls/refits.json',{'folds':[0,1],'margin':.01,'contrast':.04})
        erasure={'status':'NOT_COMPUTED','diagnostic_only':True,'refits':0,'changes_gate_or_verdict':False}
        erasure.update(subset_infeasibility_reference={'product_labels':20})
        if r==old:erasure.update(manager_approval=True,manager_ruling='historical ruling')
        erasure['campaign_context_figures']=[]
        put(r/'test-b/controls/erasure.json',erasure)
        put(r/'test-b/prediction_seal_manifest.json',{'locked_test_sampled_or_opened':False,'subset_nonconfirmatory':False,'files':{}})
        put(r/'locked/score.commit.json',{'phase':'score'})
        put(r/'locked/verdict.json',{'status':'negative','bound':.01,'recipes':[0,1]})
        put(r/'locked/margins.json',{'2':.005})
        for name in ('audit_side','record_side'):
            put(r/'locked'/name/'paths.json',{'states':[0,2,1]})
        (r/'locked/bootstrap_cache').mkdir()
        for family in ('primary','reversal','order'):
            np.save(r/'locked/bootstrap_cache'/('bootstrap_identity_'+family+'_200000.npy'),np.zeros((200000,20),dtype=np.uint8))
    monkeypatch.setattr(F,'protocol',lambda *args:{'verdict':'PASS','stages':{},'scientific_negative_result_is_execution_failure':False})
    def run():
        result=F.run_comparison(run=root,archive=tmp_path/'ref.json',output=tmp_path/'out')
        return result,json.loads(Path(result['report']).read_text())
    result,report=run();stages=report['reported_results_reproduced']['stages']
    assert all(stages[name]['status']=='PASS' for name in ('test-b/census','test-b/certification','test-b/sampling','test-b/fits','locked'))
    assert len(stages['test-b/fits']['historical_documentary_fields'])==2
    assert result['reported_results_reproduced']=='UNRESOLVED' # Other stages deliberately absent.
    erasure=json.loads((old/'test-b/controls/erasure.json').read_text())
    current=json.loads((root/'test-b/controls/erasure.json').read_text());del current['campaign_context_figures']
    put(root/'test-b/controls/erasure.json',current)
    erasure['campaign_context_figures']=[{'context_file':'x','raw_labels':9}]
    put(old/'test-b/controls/erasure.json',erasure)
    result,report=run()
    assert report['reported_results_reproduced']['stages']['test-b/fits']['status']=='UNRESOLVED'
    assert report['comparison_coverage']['test-b/fits']['unresolved_quantitative_diagnostics']==1
    put(root/'test-b/fits/fits.json',{'selected_model':'square','training_table_hash':'same','prediction':[.35,.65]})
    result,report=run()
    assert result['protocol_executed_successfully']=='PASS' and result['reported_results_reproduced']=='FAIL'
    assert report['reported_results_reproduced']['stages']['test-b/fits']['status']=='FAIL'


@pytest.fixture
def worked_adapter_probe(tmp_path,monkeypatch):
    """Independent fixed reference adapter plus mutable public certificates."""
    import copy
    import born_ladder.reproduction.worked_comparison as W
    from born_ladder import arithmetic as A
    six=A.certify_G(32)
    contexts={'original':{},'selected':{'exact':{'s':'32'}}}
    expected={'original':{'finite_events':{'events':[]},'finite_family':{'atomic_effects':{'raw_by_state':[[['1','0'],['0','1']]]}}},
              'selected':{'six_state':six,'carrier':{'trace_check_preparations':['uniform','delta0']}}}
    reference_six={'G':six['G'],'s':'32','G_states':[], 'ortho_states':[],
        'YES_table':six['YES_table_exact'],'mixtures':six['five_mixture_identities'],
        'principal_roots_are_projectors':True,'projectivity_trace_G_adjoint_conjugacy':True,
        'measure_proof_parity_values':[0,2,4,6],'contradiction_value':3,
        'test_commands':['BIN(Pa)','BIN(Pb)','BIN(Pc)']}
    diagnostic=tmp_path/'generated/original/order_diagnostics.json'
    diagnostic.parent.mkdir(parents=True);diagnostic.write_text('{}')
    generated=copy.deepcopy(expected)
    monkeypatch.setattr(W,'reference_certificates',lambda *a,**k:(contexts,expected,reference_six))
    monkeypatch.setattr(W,'reference_only_fields',lambda *a:None)
    monkeypatch.setattr(W,'algebraic_states',lambda *a:six['states_and_sharp_yes_effects'])
    def read(path):
        path=Path(path)
        if path.name in ('order_diagnostics.json','D_certificate.json'):return {}
        return contexts[path.parent.name] if path.name=='CONTEXT.json' else generated[path.parent.name]
    monkeypatch.setattr(W,'read',read)
    def compare():return W.compare_worked_cases(tmp_path/'generated',tmp_path/'reference',comparison=PolicyComparison(io.StringIO()))
    assert compare()['overall_agreement']
    return generated,compare


@pytest.mark.parametrize('probe',['six_status','atomic_effects','missing_trace_preparations','extra_scientific_field'])
def test_worked_certificate_review_probes_fail(worked_adapter_probe,probe):
    generated,compare=worked_adapter_probe
    if probe=='six_status':generated['selected']['six_state']['status']='FAIL'
    elif probe=='atomic_effects':generated['original']['finite_family']['atomic_effects']={}
    elif probe=='missing_trace_preparations':del generated['selected']['carrier']['trace_check_preparations']
    else:generated['selected']['unexpected_scientific_field']=1
    assert not compare()['overall_agreement']


@pytest.mark.parametrize('change',['changed','missing','extra'])
def test_census_completion_status_and_complete_row_schema(change):
    from born_ladder.reproduction.census_comparison import compare_completion_row
    row={'index':0,'unit_id':'case','status':'PASS','context_directory':'new'}
    reference={'index':0,'unit_id':'case','overall_registered_claim_status':'PASS'}
    if change=='changed':row['status']='FAIL'
    elif change=='missing':del row['status']
    else:row['new_scientific_value']=1
    c=PolicyComparison(io.StringIO());compare_completion_row(c,row,reference)
    assert not c.result()['overall_agreement']


def manuscript(path,definitions,body):
    path.write_text('% >>> BEGIN GENERATED RESULT MACROS (do not edit by hand)\n'+definitions+
                    '\n% <<< END GENERATED RESULT MACROS\n'+body)
    return path


@pytest.mark.parametrize('display,expected_status',[('1','PASS'),('2','FAIL'),(None,'UNRESOLVED')])
def test_full_cli_reaches_actual_manuscript_comparison(tmp_path,display,expected_status):
    import os
    import subprocess
    import sys
    root=tmp_path/'run';root.mkdir()
    components={k:k for k in ('worked','census','attachments','competitor_evaluation',
                              'cross_term_evaluation','test_b','locked','lean',
                              'competitor_units','cross_term_units')}
    (root/'pipeline.json').write_text(json.dumps({'profile':'full','components':components}))
    # Open the real paper-stage gate; unrelated production stages remain absent.
    (root/'verification_report.json').write_text(json.dumps({'status':'COMPLETE','profile':'full',
        'checks':{k:{'status':'VERIFIED'} for k in ('worked','census','attachments','evaluation','test_b')},
        'formal_endpoints':{}}))
    (root/'worked').mkdir();(root/'worked/point.json').write_text('{"point":1}')
    archive=tmp_path/'archive.json'
    archive.write_text(json.dumps({'schema':'born_reproduction_reference_v1','roots':{},
        'paper_quantities':[{'macro':'Point','component':'worked','file':'point.json','pointer':'/point'}]}))
    ledger=tmp_path/'ledger.json'
    ledger.write_text(json.dumps({'entries':[{'id':'Point','value':1,
        'evidence_type':'recomputed_by_public_command'}]}))
    aliases=tmp_path/'aliases.json'
    aliases.write_text(json.dumps([{'macro':'Point','id':'Point','format':'int'}]))
    paper=manuscript(tmp_path/'main.tex',r'\newcommand{\Point}{'+(display or '1')+'}',r'Result: \Point{}')
    repo=Path(__file__).resolve().parents[2]
    command=[sys.executable,'-m','born_ladder','reproduce','compare','--run',str(root),
        '--archive',str(archive),'--output',str(tmp_path/'comparison'),
        '--ledger',str(ledger),'--aliases',str(aliases)]
    if display is not None:command+=['--paper',str(paper)]
    completed=subprocess.run(command,cwd=repo,env={**os.environ,
        'PYTHONDONTWRITEBYTECODE':'1'},text=True,capture_output=True,timeout=60)
    assert completed.returncode==1 # Other production stages are still incomplete.
    result=json.loads(completed.stdout)
    report=json.loads(Path(result['report']).read_text())
    assert result['protocol_executed_successfully']=='UNRESOLVED'
    stage=report['reported_results_reproduced']['stages']['paper']
    assert stage['status']==expected_status,stage
    if display is None:
        assert 'requires --ledger, --aliases and --paper' in stage['reason']
    else:
        groups=stage['field_groups']
        assert groups['manuscript_defined_display_vs_ledger']['compared']==1
        assert groups['manuscript_defined_display_vs_regenerated']['compared']==1
        assert groups['paper_full_precision']['exact']==1
        assert groups['manuscript_defined_display_vs_regenerated']['failed']==(display=='2')
    assert result['reported_results_reproduced']==('FAIL' if display=='2' else 'UNRESOLVED')


def test_actual_manuscript_display_review_probe(tmp_path):
    paper=manuscript(tmp_path/'main.tex',r'\newcommand{\Point}{\ensuremath{0.9}}',r'Result: \Point{}')
    c=PolicyComparison(io.StringIO())
    result=compare_paper(c,{'entries':[{'id':'Point','value':'0.5','evidence_type':'recomputed_by_public_command'}]},
        [{'macro':'Point','id':'Point','format':'dec:1'}],[{'macro':'Point','evaluation':'competitor','pointer':'/point'}],
        tmp_path,{}, {'competitor':{'point':.5}},paper=paper)
    assert not result['overall_agreement']
    assert c.groups['manuscript_defined_display_vs_regenerated']['failed']==1
    assert c.groups['paper_full_precision']['exact']==1


@pytest.mark.parametrize('direction,value,correct,wrong',[
    ('lower','0.123456','0.1234','0.1235'),('upper','0.123451','0.1235','0.1234')])
def test_actual_manuscript_outward_endpoints(tmp_path,direction,value,correct,wrong):
    aliases=[{'macro':'Bound','id':'Bound','format':'sig:4','direction':direction}]
    ledger={'entries':[{'id':'Bound','value':value,'evidence_type':'recomputed_by_public_command'}]}
    binding=[{'macro':'Bound','evaluation':'competitor','pointer':'/bound'}]
    def compare(display):
        paper=manuscript(tmp_path/'main.tex',r'\newcommand{\Bound}{\ensuremath{'+display+'}}',r'\Bound{}')
        return compare_paper(PolicyComparison(io.StringIO()),ledger,aliases,binding,tmp_path,{},
                             {'competitor':{'bound':float(value)}},paper=paper)
    assert compare(correct)['overall_agreement']
    assert not compare(wrong)['overall_agreement']


def test_manuscript_nested_braces_and_overrides(tmp_path):
    from born_ladder.reproduction.full_comparison import manuscript_macros
    paper=manuscript(tmp_path/'main.tex',r'\newcommand{\Count}{\ensuremath{1{,}000}}',r'\Count{}')
    assert manuscript_macros(paper,{'Count':{}})[1]['Count']=='1{,}000'
    with paper.open('a') as stream:stream.write(r'\renewcommand{\Count}{900}')
    with pytest.raises(ValueError,match='overridden'):manuscript_macros(paper,{'Count':{}})


def test_erasure_review_probe_names_documentary_and_unresolved_diagnostics():
    from born_ladder.reproduction.full_comparison import compare_erasure
    actual={'status':'NOT_COMPUTED','diagnostic_only':True,'refits':0,'changes_gate_or_verdict':False}
    reference={**actual,'manager_approval':True,'manager_ruling':'recorded ruling',
        'spec_quote':'diagnostic','spec_reference':'section six',
        'campaign_context_figures':[{'context_file':'x','original_labels':9}],
        'subset_infeasibility_reference':{'product_labels':20}}
    c=PolicyComparison(io.StringIO());compare_erasure(c,actual,reference)
    assert c.result()['overall_agreement']
    assert len(c.documentary_fields)==4 and len(c.unresolved_diagnostics)==2
    assert all(r['disposition']=='HISTORICAL_DOCUMENTARY_ONLY' for r in c.documentary_fields)
    assert c.groups['erasure_scientific_disposition']['compared']==4
    # Quantitative memberships still fail when both are present and differ.
    actual.update(campaign_context_figures=[{'context_file':'different','original_labels':9}])
    c=PolicyComparison(io.StringIO());compare_erasure(c,actual,reference)
    assert not c.result()['overall_agreement']


def test_erasure_scientific_disposition_and_unknown_extra_key_fail():
    from born_ladder.reproduction.full_comparison import compare_erasure
    reference={'status':'NOT_COMPUTED','diagnostic_only':True,'refits':0,'changes_gate_or_verdict':False}
    for actual in ({**reference,'refits':1},{**reference,'unregistered_gate':True},
                   {k:v for k,v in reference.items() if k!='status'}):
        c=PolicyComparison(io.StringIO());compare_erasure(c,actual,reference)
        assert not c.result()['overall_agreement']


def test_absent_counterpart_is_not_missing_production_or_a_match():
    from born_ladder.reproduction.full_comparison import coverage_summary,reproduction_wording
    fields=assess(1,1)[0]['field_groups']
    complete={'status':'UNRESOLVED','field_groups':fields,'unavailable_stored_reference_files':[{'file':'root'}]}
    partial={'status':'UNRESOLVED','missing_generated_outputs':['certificate.json']}
    a,b=coverage_summary(complete),coverage_summary(partial)
    assert a['matched']==1 and a['no_archived_counterpart']==1 and a['missing_generated_outputs']==0
    assert b['matched']==0 and b['missing_generated_outputs']==1
    assert a['wording']!=b['wording']
    assert 'no item without a counterpart' in reproduction_wording('UNRESOLVED',{'census':a}).lower()
    assert 'regenerated outputs are missing' in reproduction_wording('UNRESOLVED',{'census':b})


@pytest.mark.parametrize('gap_field',[
    'unavailable_stored_reference_files','historical_outputs_without_archived_counterpart'])
def test_paper_dependency_on_absent_reference_is_explicit(tmp_path,gap_field):
    from born_ladder.reproduction.full_comparison import paper_counterpart_dependencies
    ledger=tmp_path/'ledger.json';aliases=tmp_path/'aliases.json'
    aliases.write_text(json.dumps([{'macro':'Bound','id':'Bound','format':'sig:4'}]))
    ledger.write_text(json.dumps({'entries':[{'id':'Bound','source':'census/instrument_root_controls.json#/bound'}]}))
    stages={'census':{gap_field:[{'unit_id':'case','file':'instrument_root_controls.json'}]}}
    result=paper_counterpart_dependencies(stages,ledger,aliases,None,[])
    assert result['status']=='DIRECT_DEPENDENCY'
    assert result['items'][0]['direct_paper_value_dependencies']==['Bound']
    ledger.write_text(json.dumps({'entries':[{'id':'Bound','source':'census/certificates.json#/correspondence'}]}))
    result=paper_counterpart_dependencies(stages,ledger,aliases,None,[])
    assert result['status']=='NO_DIRECT_ENDPOINT_VALUE_DEPENDENCY'
    assert 'independently checked' in result['items'][0]['indirect_scope']


def test_braceless_tex_override_cannot_hide_wrong_manuscript_value(tmp_path):
    from born_ladder.reproduction.full_comparison import manuscript_macros
    paper=manuscript(tmp_path/'main.tex',r'\newcommand{\Point}{0.5}',r'\Point{}\def\Point{0.9}')
    with pytest.raises(ValueError,match='overridden'):manuscript_macros(paper,{'Point':{}})


@pytest.mark.data
@pytest.mark.parametrize('probe',['six_status','atomic_effects','missing_trace_preparations'])
def test_retained_worked_review_probe(tmp_path,monkeypatch,probe):
    import os,copy
    import born_ladder.reproduction.worked_comparison as W
    generated=os.environ.get('E2E_P8_WORKED_OUTPUT');reference=os.environ.get('E2E_P8_WORKED_REFERENCE')
    non_trace=os.environ.get('E2E_P8_NON_TRACE_REFERENCE')
    if not all((generated,reference,non_trace)):
        pytest.skip('set E2E_P8_WORKED_OUTPUT, E2E_P8_WORKED_REFERENCE and E2E_P8_NON_TRACE_REFERENCE for retained in-memory review probes')
    generated=Path(generated);normal=W.read
    certificates={name:copy.deepcopy(normal(generated/name/'certificates.json')) for name in ('original','selected')}
    if probe=='six_status':certificates['selected']['six_state']['status']='FAIL'
    elif probe=='atomic_effects':certificates['original']['finite_family']['atomic_effects']={}
    else:del certificates['selected']['carrier']['trace_check_preparations']
    def read(path):
        path=Path(path)
        if path.name=='certificates.json' and path.parent.parent==generated:return certificates[path.parent.name]
        return normal(path)
    monkeypatch.setattr(W,'read',read)
    r=W.compare_worked_cases(generated,reference,non_trace=non_trace,comparison=PolicyComparison(io.StringIO()))
    assert not r['overall_agreement']


@pytest.mark.data
@pytest.mark.parametrize('probe',['status','missing_premise_status','extra_atom_field'])
def test_retained_census_review_probe(monkeypatch,probe):
    import os,copy
    import born_ladder.reproduction.census_comparison as C
    generated=os.environ.get('E2E_P8_CENSUS_OUTPUT');reference=os.environ.get('E2E_P8_CENSUS_REFERENCE')
    if not all((generated,reference)):
        pytest.skip('set E2E_P8_CENSUS_OUTPUT and E2E_P8_CENSUS_REFERENCE for retained in-memory review probes')
    generated,reference=Path(generated),Path(reference);normal=C.read
    # Single actual case with its full certificate, not a statistical sample.
    # The reduced view is a comparator integration fixture only.
    def read(path):
        path=Path(path);value=copy.deepcopy(normal(path))
        if path.name in ('INVENTORY.json','structural_completion_results.json','original_implementation_results.json','structural_results.json'):
            value=value[:1]
            if path.name=='structural_completion_results.json' and probe=='status':value[0]['status']='FAIL'
        elif path.name=='structural_completion_certificate.json':
            if probe=='missing_premise_status':del value['certificates']['C_premises']['status']
            if probe=='extra_atom_field':value['certificates']['C_premises']['atom_certificates'][0]['unregistered_scientific_field']=1
        return value
    monkeypatch.setattr(C,'read',read)
    c=PolicyComparison(io.StringIO())
    try:r=C.compare_census(generated,reference,comparison=c)
    except KeyError:
        # Full driver preserves this failed schema assessment in its FAIL report.
        assert not c.result()['overall_agreement']
    else:assert not r['overall_agreement']


def test_coverage_reports_accepted_numeric_differences_separately():
    from born_ladder.reproduction.full_comparison import coverage_summary
    result=assess(1.+1e-13,1.)[0]
    coverage=coverage_summary(result)
    assert coverage['matched']==0 and coverage['differed']==1
    assert coverage['accepted_nonexact']==1 and coverage['outside_criteria']==0

@pytest.mark.parametrize('definition',[r'\renewcommand\X{0.9}',r'\renewcommand*\X{0.9}',
    r'\providecommand\X{0.9}',r'\DeclareRobustCommand\X{0.9}',r'\newcommand\X{0.9}'])
def test_unbraced_definition_review_probe(tmp_path,definition):
    from born_ladder.reproduction.full_comparison import manuscript_macros
    paper=manuscript(tmp_path/'main.tex',r'\newcommand{\X}{0.5000}',definition+r'\X{}')
    with pytest.raises(ValueError,match='overridden'):manuscript_macros(paper,{'X':{}})


def test_unbraced_initial_definition_and_unsupported_indirection(tmp_path):
    from born_ladder.reproduction.full_comparison import manuscript_macros
    paper=manuscript(tmp_path/'main.tex',r'\newcommand\X{0.5000}',r'\X{}')
    assert manuscript_macros(paper,{'X':{}})[1]=={'X':'0.5000'}
    paper.write_text(paper.read_text()+r'\expandafter\def\csname X\endcsname{0.9}')
    with pytest.raises(ValueError,match='unsupported'):manuscript_macros(paper,{'X':{}})


@pytest.fixture(scope='module')
def complete_order_diagnostics():
    from test_e2e_p3bc import embedded_original
    from born_ladder.reproduction.worked_cases import frame
    from born_ladder.instruments import Instrument
    from born_ladder.reproduction.worked_science import order_diagnostics
    from born_ladder import arithmetic as A
    context=embedded_original();w,s,P,K=frame(context)
    return json.loads(json.dumps(A.qserial(order_diagnostics(Instrument(context,w,s,P,K)))))


def test_complete_order_diagnostics_are_computed(complete_order_diagnostics):
    from fractions import Fraction
    d=complete_order_diagnostics
    assert (d['canonical_equal_count'],d['canonical_unequal_count'],d['unresolved_count'])==(40,24,0)
    assert len(d['canonical_pairs'])==64 and len(d['context_pairs'])==400
    assert len(d['passive_disturbance'])==9
    assert Fraction(d['atomic_fragment_boundary']['largest_nonunit_passive_or_first_atomic_mass_exact'])==Fraction(29,32)
    assert d['operator_quotient_boundary']['public_event_predicates_equal'] is False


@pytest.mark.parametrize('path',[
    ('canonical_equal_count',),('canonical_unequal_count',),('canonical_pairs',0,'status'),
    ('canonical_pairs',0,'maximally_mixed_probability_equal'),
    ('passive_disturbance',0,'rows',0,'lueders_probability','lo'),
    ('coarse_fine_forgetting','raw0_branch',0,0,'hi'),
    ('atomic_fragment_boundary','complement_uniform_probability','lo'),
    ('atomic_fragment_boundary','largest_nonunit_passive_or_first_atomic_mass_exact'),
    ('atomic_fragment_boundary','status'),
    ('operator_quotient_boundary','common_exact_effect',0,0),
    ('operator_quotient_boundary','common_uniform_mass_exact'),
    ('operator_quotient_boundary','protocol_or_event_tag_required'),
    ('operator_quotient_boundary','state_or_instrument_law_failed')])
@pytest.mark.parametrize('mutation',['change','remove'])
def test_order_nested_scientific_fields_review_probe(complete_order_diagnostics,path,mutation):
    import copy
    from born_ladder.reproduction.worked_comparison import compare_order_diagnostics
    actual=copy.deepcopy(complete_order_diagnostics);parent=actual
    for key in path[:-1]:parent=parent[key]
    if mutation=='remove':del parent[path[-1]]
    else:parent[path[-1]]='CORRUPTED'
    c=PolicyComparison(io.StringIO());compare_order_diagnostics(c,actual,complete_order_diagnostics)
    assert not c.result()['overall_agreement']


def test_order_narrative_is_named_but_not_scientific(complete_order_diagnostics):
    import copy
    from born_ladder.reproduction.worked_comparison import compare_order_diagnostics
    actual=copy.deepcopy(complete_order_diagnostics)
    actual['atomic_fragment_boundary']['proof']='Changed historical explanation'
    actual['operator_quotient_boundary']['partial_sum_ambiguity']='Changed explanation'
    c=PolicyComparison(io.StringIO());compare_order_diagnostics(c,actual,complete_order_diagnostics)
    assert c.result()['overall_agreement']
    assert any(r['field'].endswith('/proof') for r in c.documentary_fields)


def test_erasure_arithmetic_regenerated_without_refits():
    from born_ladder.record_tests.erasure import diagnostics
    from born_ladder.reproduction.full_comparison import compare_erasure
    entries=[({'file':'context','m':3},2),({'file':'context','m':3},3)]
    actual=diagnostics(entries,lambda entry:[[0,0],[0,1],[1,0]])
    figure=actual['campaign_context_figures'][0]
    assert len(actual['campaign_context_figures'])==1
    assert figure['rank_two_sign_patterns']==8
    assert figure['rank_two_scored_candidates']==8*76
    assert figure['candidate_theta_arrays_bytes_alone']==8*76*12*8
    assert actual['refits']==0 and actual['changes_gate_or_verdict'] is False
    reference={**actual,'manager_approval':True,'manager_ruling':'historical prose'}
    c=PolicyComparison(io.StringIO());compare_erasure(c,actual,reference)
    assert c.result()['overall_agreement'] and not c.unresolved_diagnostics
    for key in ('campaign_context_figures','subset_infeasibility_reference'):
        changed={**actual,key:[]};c=PolicyComparison(io.StringIO());compare_erasure(c,changed,reference)
        assert not c.result()['overall_agreement']


@pytest.mark.data
def test_retained_order_science_reproduced(complete_order_diagnostics):
    import os
    from born_ladder.reproduction.worked_comparison import compare_order_diagnostics
    reference=os.environ.get('E2E_P8_WORKED_REFERENCE')
    if not reference:pytest.skip('set E2E_P8_WORKED_REFERENCE')
    c=PolicyComparison(io.StringIO())
    compare_order_diagnostics(c,complete_order_diagnostics,json.loads((Path(reference)/'E2/D_certificate.json').read_text()))
    assert c.result()['all_scientific_values_exact']


@pytest.mark.data
@pytest.mark.parametrize('new_count',[1,2002])
def test_extended_census_review_probe_checks_all_historical_certificates(monkeypatch,new_count):
    import os,copy
    import born_ladder.reproduction.census_comparison as C
    generated=os.environ.get('E2E_P8_CENSUS_OUTPUT');reference=os.environ.get('E2E_P8_CENSUS_REFERENCE')
    if not generated or not reference:pytest.skip('set E2E_P8_CENSUS_OUTPUT and E2E_P8_CENSUS_REFERENCE')
    generated,reference=Path(generated),Path(reference);normal=C.read
    inventory=normal(reference/'INVENTORY.json');assert len(inventory)==120
    seen=[]
    def read(path):
        path=Path(path);value=copy.deepcopy(normal(path))
        if path.name in ('INVENTORY.json','structural_completion_results.json','original_implementation_results.json') and path.is_relative_to(generated):
            for i in range(new_count):
                row=copy.deepcopy(value[0]);row['unit_id']='new-'+str(i)
                if path.name!='INVENTORY.json':row['index']=120+i
                value.append(row)
            if new_count==1:
                # New cohort order puts a new identity before the historical
                # projection. Only position fields are explicitly reindexed.
                value=[value[-1],*value[:-1]]
                if path.name!='INVENTORY.json':
                    for index,row in enumerate(value):row['index']=index
        elif new_count==1 and path.is_relative_to(generated):
            if path.name=='structural_completion_certificate.json':value['index']+=1
            elif path.name=='maximal_gap_witness.json':
                for row in value['cases']:row['case']+=1
        return value
    def new_check(directory,row,original,**kwargs):
        seen.append(row['unit_id'])
        return {'unit_id':row['unit_id'],'disposition':'NEW_RESULT_NO_ARCHIVED_COUNTERPART',
                'historical_matches':0,'independent_validation':{'overall_agreement':True}}
    monkeypatch.setattr(C,'read',read);monkeypatch.setattr(C,'validate_new_case',new_check)
    c=PolicyComparison(io.StringIO());result=C.compare_census(generated,reference,lean_root='lean_born',comparison=c)
    assert result['overall_agreement']
    assert result['historical_contexts_compared']==120
    assert c.groups['exact_context']['compared']>120
    assert result['new_contexts']==new_count and len(seen)==new_count
    assert result['new_historical_matches']==0
    assert all(r['historical_matches']==0 for r in result['new_results_without_archived_counterpart'])
    # Absent stored root intervals retain their own honest disposition.
    assert not result['unavailable_stored_reference_files']
    assert len(result['historical_outputs_without_archived_counterpart'])==13
    assert all(r['historical_matches']==0 for r in result['historical_outputs_without_archived_counterpart'])


@pytest.mark.data
def test_new_case_independent_validation_has_no_historical_matches():
    import os
    from born_ladder.reproduction.census_comparison import read,validate_new_case
    generated=os.environ.get('E2E_P8_CENSUS_OUTPUT')
    if not generated:pytest.skip('set E2E_P8_CENSUS_OUTPUT')
    root=Path(generated);summary=read(root/'complete.json')['summary']
    row=read(root/summary['summary_directory']/'structural_completion_results.json')[0]
    original=read(root/summary['summary_directory']/'original_implementation_results.json')[0]
    result=validate_new_case(root/row['context_directory'],row,original)
    assert result['independent_validation']['overall_agreement'] and result['historical_matches']==0


def test_historical_projection_aligns_archive_order_and_reports_missing_identities():
    from born_ladder.reproduction.census_comparison import historical_projection
    old=[{'unit_id':'a'},{'unit_id':'b'}]
    historical,new=historical_projection([{'unit_id':'new'},old[1],old[0]],old)
    assert historical==old and new==[{'unit_id':'new'}]
    assert assess([r['unit_id'] for r in historical],[r['unit_id'] for r in old])[0]['overall_agreement']
    historical,new=historical_projection([old[0],{'unit_id':'new'}],old)
    assert not assess([r['unit_id'] for r in historical],[r['unit_id'] for r in old])[0]['overall_agreement']


@pytest.fixture
def reordered_census(tmp_path,monkeypatch):
    """Two distinct synthetic cases; mock mathematical audits, exercise the real join."""
    import copy
    from fractions import Fraction
    import born_ladder.reproduction.census_comparison as C
    root=tmp_path/'generated';archive=tmp_path/'archive';lean=tmp_path/'lean_reference'
    def put(path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
    frames=[];inventory=[];originals=[];certificates={}
    for index,uid in enumerate(('a','b')):
        w=[str((2*i-31)*(index+1)) for i in range(32)];s=str(sum(Fraction(x)**2 for x in w))
        labels=[0 if i<16+8*index else 1 for i in range(32)]
        context={'identity':{'unit_id':uid},'exact':{'w':w,'s':s},'kernel':[[1.]],
            'lens':{k:labels for k in ('raw_by_state','package_by_state','joint_by_state')}}
        atoms=[]
        for field in context['lens']:
            for label in (0,1):
                states=[i for i,a in enumerate(labels) if a==label]
                a=sum(Fraction(w[i]) for i in states);b=sum(Fraction(w[i])**2 for i in states)
                atoms.append({'context':field,'atom':label,'states':states,
                    'effect_exact':[[str(Fraction(len(states),32)),str(a/32)],[str(a/Fraction(s)),str(b/Fraction(s))]],
                    'Gram_det_exact':str(len(states)*b-a*a),'positive':True})
        cp={'status':'PASS','atom_certificates':atoms,'atom_count':6,
            'strict_positive_atom_count':6,'zero_atom_count':0,'negative_atom_count':0,
            'six_state_certificate':'six_state_certificate.json'}
        import hashlib
        from born_ladder.archive import canonical
        key={'unit_id':uid}
        certificate={'index':index,'unit_id':uid,'key_sha256':hashlib.sha256(canonical(key)).hexdigest(),'overall_status':'PASS','failures':[],
            'certificates':{k:{'status':'PASS'} for k in ('kernel','carrier','strictness','factorization_controls','diagnostics','correspondence')}}
        certificate['certificates']['C_premises']=cp;certificates[uid]=certificate
        inventory.append({'unit_id':uid,'provenance_key':key,'source':{'path':'old.jsonl','line':7,'byte_offset':100},'n':32,
            'lenses':{'raw_map':labels}})
        original={'index':index,'unit_id':uid,'status':'PASS','correspondence_status':'PASS','C_premises':{'status':'PASS'},
            'classification':'completed original implementation',
            'origin':'re-executed original implementation checks on explicit construction inputs; not copied historical verdicts'}
        originals.append(original)
        completion={'index':index,'unit_id':uid,'overall_registered_claim_status':'PASS',
            'registered_numerical_gate_status':'PASS','C_premise_status':'PASS',
            **{k:cp[k] for k in ('atom_count','strict_positive_atom_count','zero_atom_count','negative_atom_count')},
            'atoms':[{k:a[k] for k in ('context','atom','Gram_det_exact','positive')} for a in atoms]}
        for directory in (archive/'contexts'/uid,root/'contexts'/uid):
            put(directory/'CONTEXT.json',context)
            for file in ('six_state_exact_completion.json','instrument_root_controls.json','landed_own_input_prediction.json'):
                put(directory/file,{})
        put(archive/'contexts'/uid/'certificates.json',certificate)
        put(archive/'contexts'/uid/'six_state_certificate.json',{})
        put(root/'contexts'/uid/'six_state_symbolic_original.json',{})
        put(archive/'contexts'/uid/'structural_completion.json',completion)
        frames.append(C.integer_record(w,[labels]*3))
        put(root/'contexts'/uid/'integer_frame.json',frames[-1])
    robust=C.scan_records(frames,require_bound=False)
    put(archive/'INVENTORY.json',inventory)
    put(archive/'structural_results.json',[certificates[uid] for uid in ('a','b')])
    put(root/'inventory/INVENTORY.json',list(reversed(inventory)))
    completed=[];generated_original=[]
    for index,uid in enumerate(('b','a')):
        cert=copy.deepcopy(certificates[uid]);cert['index']=index
        put(root/'contexts'/uid/'structural_completion_certificate.json',cert)
        completed.append({'index':index,'unit_id':uid,'status':'PASS','context_directory':'contexts/'+uid})
        original=copy.deepcopy(originals[('a','b').index(uid)]);original['index']=index;generated_original.append(original)
        rows=copy.deepcopy(robust);rows['cases']=[{**robust['cases'][('a','b').index(uid)],'case':index}]
        put(root/'contexts'/uid/'maximal_gap_witness.json',rows)
    put(root/'summary/structural_completion_results.json',completed)
    put(root/'summary/original_implementation_results.json',generated_original)
    put(root/'complete.json',{'artifacts':[],'summary':{'inventory_directory':'inventory','summary_directory':'summary'}})
    lean_file=lean/'BornCalculus/CensusRobustInputs.lean';lean_file.parent.mkdir(parents=True)
    lean_file.write_text(C.render_pairs(robust['cases']))
    monkeypatch.setattr(C,'verify_artifacts',lambda *args:None)
    monkeypatch.setattr(C,'check_context',lambda *args:{'status':'PASS'})
    monkeypatch.setattr(C,'check_trine',lambda *args:{'status':'PASS'})
    monkeypatch.setattr(C,'embedded_records',lambda *args:frames)
    monkeypatch.setattr(C,'scan',lambda *args:robust)
    return root,archive,lean


def test_reordered_census_compares_same_identities_and_lean_frames(reordered_census):
    from born_ladder.reproduction.census_comparison import compare_census
    root,archive,lean=reordered_census;c=PolicyComparison(io.StringIO())
    result=compare_census(root,archive,lean_root=lean,comparison=c)
    assert result['overall_agreement'],result['field_groups']
    assert result['cohort_position_projection']==[
        {'unit_id':'a','generated_index':1,'historical_index':0},
        {'unit_id':'b','generated_index':0,'historical_index':1}]
    assert c.groups['all_embedded_integer_frame_fields']['compared']>64


def test_census_stored_location_only_change_is_projected(reordered_census):
    from born_ladder.reproduction.census_comparison import compare_census
    root,archive,lean=reordered_census
    path=root/'inventory/INVENTORY.json';rows=json.loads(path.read_text())
    rows[0]['source'].update(path='collections/new.jsonl',line=92,byte_offset=8192)
    path.write_text(json.dumps(rows));stream=io.StringIO();c=PolicyComparison(stream)
    assert compare_census(root,archive,lean_root=lean,comparison=c)['overall_agreement']
    differences=[json.loads(line) for line in stream.getvalue().splitlines()]
    assert any(row['path']=='b/source/line' and row['rule'].startswith('storage-only') for row in differences)


def test_aligned_census_genuine_value_change_still_fails(reordered_census):
    from born_ladder.reproduction.census_comparison import compare_census
    root,archive,lean=reordered_census;path=root/'contexts/b/CONTEXT.json'
    context=json.loads(path.read_text());context['kernel'][0][0]=.9;path.write_text(json.dumps(context))
    stream=io.StringIO();c=PolicyComparison(stream)
    result=compare_census(root,archive,lean_root=lean,comparison=c)
    assert not result['overall_agreement']
    differences=[json.loads(line) for line in stream.getvalue().splitlines()]
    failure=next(row for row in differences if row['path']=='b/kernel/0/0')
    assert not failure['accepted'] and failure['absolute_difference']==pytest.approx(.1)

@pytest.mark.parametrize('override',[r'\RenewDocumentCommand{\X}{}{0.9}',r'\renewrobustcmd\X{0.9}',r'\patchcmd{\X}{0.5}{0.9}{}{}'])
def test_unsupported_result_definition_forms_are_refused(tmp_path,override):
    from born_ladder.reproduction.full_comparison import manuscript_macros
    paper=manuscript(tmp_path/'main.tex',r'\newcommand{\X}{0.5}',override+r'\X{}')
    with pytest.raises(ValueError,match='unsupported'):manuscript_macros(paper,{'X':{}})


def test_missing_both_erasure_diagnostics_never_counts_as_matched():
    from born_ladder.reproduction.full_comparison import compare_erasure
    value={'status':'NOT_COMPUTED','diagnostic_only':True,'refits':0,'changes_gate_or_verdict':False}
    c=PolicyComparison(io.StringIO());compare_erasure(c,value,value)
    assert len(c.unresolved_diagnostics)==2
    assert not c.groups.get('erasure_quantitative_diagnostics')


@pytest.mark.data
def test_retained_erasure_diagnostics_recomputed_from_alphabets():
    import os
    from born_ladder.record_tests.erasure import diagnostics
    from born_ladder.reproduction.full_comparison import compare_erasure
    configured=os.environ.get('E2E_P8_TEST_B_REFERENCE')
    if not configured:pytest.skip('set E2E_P8_TEST_B_REFERENCE to the retained Test B v6 root')
    root=Path(configured)
    entries=json.loads((root/'record_view/manifest.json').read_text())['allowed_files']
    alphabets=json.loads((root/'record_side/alphabets.json').read_text())
    def alphabet(entry):
        matched=[r['alphabet'] for r in alphabets if all(r[k]==entry[k] for k in ('exp','config','k','step_index'))]
        assert len(matched)==1
        return matched[0]
    actual=diagnostics([(entry,2) for entry in entries],alphabet)
    reference=json.loads((root/'controls/erasure.json').read_text())
    c=PolicyComparison(io.StringIO());compare_erasure(c,actual,reference)
    assert c.result()['all_scientific_values_exact'] and not c.unresolved_diagnostics
    assert len(c.documentary_fields)==4


def test_erasure_supplement_compared_and_inconsistent_overlap_fails(tmp_path):
    from born_ladder.record_tests.erasure import diagnostics
    complete=diagnostics([({'file':'context','m':1},2)],lambda entry:[[0,0]])
    a=tmp_path/'new';b=tmp_path/'old';a.mkdir();b.mkdir()
    minimal={k:complete[k] for k in ('status','diagnostic_only','refits','changes_gate_or_verdict')}
    (a/'erasure.json').write_text(json.dumps(minimal));(a/'erasure_diagnostics.json').write_text(json.dumps(complete))
    (b/'erasure.json').write_text(json.dumps(complete))
    c=PolicyComparison(io.StringIO());compare_file(c,'literal_refits_order_and_controls',a/'erasure.json',b/'erasure.json')
    assert c.result()['overall_agreement'] and not c.unresolved_diagnostics
    complete['refits']=1;(a/'erasure_diagnostics.json').write_text(json.dumps(complete))
    c=PolicyComparison(io.StringIO());compare_file(c,'literal_refits_order_and_controls',a/'erasure.json',b/'erasure.json')
    assert not c.result()['overall_agreement']


def test_completed_test_b_commit_backfills_erasure_without_refits(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from born_ladder.reproduction import test_b as B
    from born_ladder.record_tests.erasure import diagnostics
    entry={'file':'context','m':1};entries=[(entry,2)]
    saved={'files':{},'structural_erasure':'NOT_COMPUTED','locked_test_sampled_or_opened':False}
    marker=tmp_path/'prediction_seal_manifest.json';marker.write_text(json.dumps(saved))
    original=marker.read_bytes();calls=[]
    runtime={'versions':'synthetic'}
    R=SimpleNamespace(phase_start=lambda *a:{'runtime':runtime},
        verify_phase=lambda *a:calls.append('verify seal'),
        verify_files=lambda *a:calls.append('verify files'),eligible_entries=lambda *a:entries,
        erasure_diagnostics=lambda root,rows:diagnostics(rows,lambda entry:[[0,0]]))
    C=SimpleNamespace(canonical_document=lambda path:json.loads(Path(path).read_text()))
    monkeypatch.setattr(B,'science',lambda specs:(R,C,None,runtime))
    assert B.commit_stage(tmp_path,specifications='specifications',workers=4)==saved
    supplemental=tmp_path/'controls/erasure_diagnostics.json';bytes_first=supplemental.read_bytes()
    assert json.loads(bytes_first)['refits']==0
    assert B.commit_stage(tmp_path,specifications='specifications',workers=1)==saved
    assert marker.read_bytes()==original and supplemental.read_bytes()==bytes_first
    assert calls==['verify seal','verify files']*2


@pytest.mark.data
def test_retained_worked_complete_order_and_admission_mapping(tmp_path,complete_order_diagnostics):
    import os,shutil
    from born_ladder.reproduction.worked_comparison import compare_worked_cases
    generated=os.environ.get('E2E_P8_WORKED_OUTPUT');reference=os.environ.get('E2E_P8_WORKED_REFERENCE')
    non_trace=os.environ.get('E2E_P8_NON_TRACE_REFERENCE')
    if not all((generated,reference,non_trace)):pytest.skip('set E2E_P8_WORKED_OUTPUT, E2E_P8_WORKED_REFERENCE, E2E_P8_NON_TRACE_REFERENCE')
    target=tmp_path/'worked'
    for name in ('original','selected'):
        (target/name).mkdir(parents=True)
        for file in ('CONTEXT.json','certificates.json'):
            shutil.copyfile(Path(generated)/name/file,target/name/file)
    (target/'original/order_diagnostics.json').write_text(json.dumps(complete_order_diagnostics))
    c=PolicyComparison(io.StringIO())
    result=compare_worked_cases(target,reference,non_trace=non_trace,comparison=c)
    assert result['overall_agreement']
    assert result['event_admission_scope_mapping']['events_mapped']==2340
    assert c.groups['event_admission_scope_mapping']['exact']==2340
    assert c.groups['worked_order_diagnostics']['compared']==c.groups['worked_order_diagnostics']['exact']
    assert not any('/events/' in r['field'] and r['field'].endswith('/status') for r in c.unresolved_reference_fields)


@pytest.mark.data
def test_new_case_invalid_status_does_not_claim_historical_match(monkeypatch):
    import os,copy
    import born_ladder.reproduction.census_comparison as C
    generated=os.environ.get('E2E_P8_CENSUS_OUTPUT')
    if not generated:pytest.skip('set E2E_P8_CENSUS_OUTPUT')
    root=Path(generated);summary=C.read(root/'complete.json')['summary']
    row=copy.deepcopy(C.read(root/summary['summary_directory']/'structural_completion_results.json')[0])
    original=C.read(root/summary['summary_directory']/'original_implementation_results.json')[0]
    row['status']='FAIL'
    result=C.validate_new_case(root/row['context_directory'],row,original)
    assert not result['independent_validation']['overall_agreement'] and result['historical_matches']==0


@pytest.fixture(scope='module')
def retained_census_inputs():
    import os
    from born_ladder.reproduction.census_case_validation import RetainedInputs
    generated=os.environ.get('E2E_P8_CENSUS_OUTPUT')
    if not generated:pytest.skip('set E2E_P8_CENSUS_OUTPUT')
    return RetainedInputs(generated)


@pytest.fixture
def new_case_certificate(tmp_path,retained_census_inputs):
    """Copy a real case so all readers see mutations without touching the run."""
    import os,shutil
    from fractions import Fraction
    from born_ladder.reproduction.census_comparison import read
    generated=os.environ.get('E2E_P8_CENSUS_OUTPUT')
    if not generated:pytest.skip('set E2E_P8_CENSUS_OUTPUT')
    root=Path(generated);summary=read(root/'complete.json')['summary']
    base=root/summary['summary_directory']
    completed=read(base/'structural_completion_results.json')
    originals=read(base/'original_implementation_results.json')
    witnesses=read(base/'maximal_gap_witnesses.json')
    index=next((i for i,w in enumerate(witnesses) if Fraction(w['gap_exact'])<Fraction(3,20)),0)
    row=completed[index];directory=tmp_path/'context';directory.mkdir()
    for name in ('CONTEXT.json','structural_completion_certificate.json',
                 'instrument_root_controls.json','six_state_exact_completion.json',
                 'integer_frame.json','maximal_gap_witness.json','atom_classes.json','landed_own_input_prediction.json',
                 'original_implementation.json','six_state_symbolic_original.json'):
        shutil.copyfile(root/row['context_directory']/name,directory/name)
    return directory,row,originals[index],retained_census_inputs


@pytest.mark.data
@pytest.mark.parametrize('group',[
    'kernel','carrier','correspondence','strictness','factorization_controls','C_premises','diagnostics'])
@pytest.mark.parametrize('mutation',['FAIL','missing'])
def test_new_case_required_scientific_statuses_reject_defects(new_case_certificate,group,mutation):
    from born_ladder.reproduction.census_comparison import read,validate_new_case
    directory,row,original,inputs=new_case_certificate
    path=directory/'structural_completion_certificate.json';cert=read(path)
    if mutation=='missing':del cert['certificates'][group]['status']
    else:cert['certificates'][group]['status']=mutation
    path.write_text(json.dumps(cert))
    result=validate_new_case(directory,row,original,inputs=inputs)
    assert not result['independent_validation']['overall_agreement']
    assert result['independent_validation']['field_groups']['scientific_certificate_statuses']['differences']
    assert result['historical_matches']==0


@pytest.mark.data
@pytest.mark.parametrize('mutation',['empty','missing_subset','duplicate_subset','unexpected_subset'])
def test_new_case_requires_complete_root_population_before_endpoints(new_case_certificate,mutation,monkeypatch):
    import born_ladder.reproduction.census_comparison as C
    directory,row,original,inputs=new_case_certificate
    path=directory/'instrument_root_controls.json';roots=C.read(path)
    if mutation=='empty':roots=[]
    elif mutation=='missing_subset':roots=roots[:-1]
    elif mutation=='duplicate_subset':roots.append(roots[0])
    else:roots.append({'subset':[0],'root_certificate':roots[0]['root_certificate']})
    path.write_text(json.dumps(roots))
    def endpoints(*args):pytest.fail('endpoint checking ran before complete root membership was established')
    monkeypatch.setattr(C,'check_context',endpoints)
    result=C.validate_new_case(directory,row,original,inputs=inputs)
    assert not result['independent_validation']['overall_agreement']
    assert result['independent_validation']['field_groups']['principal_root_subset_membership']['differences']
    assert result['historical_matches']==0


@pytest.mark.data
def test_new_case_registered_robust_shortfall_is_valid_completion(new_case_certificate):
    from born_ladder.reproduction.census_comparison import read,validate_new_case
    directory,row,original,inputs=new_case_certificate
    if read(directory/'maximal_gap_witness.json')['status']!='FAILED':
        pytest.skip('supplied cohort has no registered 3/20 shortfall')
    result=validate_new_case(directory,row,original,inputs=inputs)
    assert result['independent_validation']['overall_agreement']
    assert result['completion_status']=='PASS' and result['historical_matches']==0


@pytest.mark.data
def test_new_case_matching_failed_dispositions_do_not_hide_valid_premises(new_case_certificate):
    from born_ladder.reproduction.census_comparison import read,validate_new_case
    directory,row,original,inputs=new_case_certificate
    path=directory/'structural_completion_certificate.json';cert=read(path)
    cert['overall_status']='FAIL';cert['certificates']['C_premises']['status']='FAIL'
    path.write_text(json.dumps(cert))
    result=validate_new_case(directory,{**row,'status':'FAIL'},original,inputs=inputs)
    assert not result['independent_validation']['overall_agreement']
    assert result['independent_validation']['field_groups']['recomputed_completion_disposition']['differences']


@pytest.fixture
def extended_attachments(tmp_path):
    """Two retained identities plus a distinct third case, with sealed source rows."""
    import hashlib
    from born_ladder.archive import canonical,sha
    from born_ladder import metadata
    from born_ladder.summaries import summarise
    from born_ladder.snapshot.identities import kind_cell_id
    from born_ladder.reproduction.census_comparison import read
    new,old,census,units=[tmp_path/name for name in ('attachments','reference','census','units')]
    for path in (new,old,census,units):path.mkdir()
    ids=[str(i)*64 for i in (1,2,3)];generated_ids=[ids[1],ids[2],ids[0]]
    bodies=[];pointers={};keys={}
    for i,uid in enumerate(ids):
        fields={'eligibility':True,'brier_score':{'q_full':float(i+1)},'dtv_loss':{'q_diag':float(i+1)},
                'bootstrap_hierarchy_keys':[100+i],'pairwise_contrast':{}}
        for view in ('raw','pkg'):
            body={'unit_id':uid,'kind_cell_id':kind_cell_id(uid,view),'basis_and_projector_inputs':[[1,0],[0,1]],
                  'unrounded_p_full':[.5,.5],'spectral_coefficients':[.25,.5],**fields}
            text=json.dumps(body,separators=(',',':'));raw=(text+'\n').encode()
            refs=metadata.refs(text,metadata.UNIT_KEYS|{'unrounded_p_full'})
            ptr={'kind':view,'kind_cell_id':body['kind_cell_id'],'path':'units.jsonl','line':len(bodies)+1,
                 'byte_offset':sum(map(len,bodies)),'line_sha256':hashlib.sha256(raw.rstrip(b'\n')).hexdigest(),'fields':refs}
            pointers[uid,view]=ptr;bodies.append(raw)
            keys[uid]={'unit_id':uid,'basis_projector_field_sha256':refs['basis_and_projector_inputs']['field_sha256'],
                       'preparation_input_sha256':refs['unrounded_p_full']['field_sha256']}
    file=units/'units.jsonl';file.write_bytes(b''.join(bodies))
    for ptr in pointers.values():ptr['file_sha256']=sha(file)
    def put(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
    inventory=[{'unit_id':uid,'provenance_key':keys[uid],'kind_records':[pointers[uid,v] for v in ('raw','pkg')]} for uid in generated_ids]
    put(census/'inventory/INVENTORY.json',inventory)
    put(old/'INVENTORY.json',[{'unit_id':uid} for uid in ids[:2]])
    put(census/'complete.json',{'summary':{'inventory_directory':'inventory','summary_directory':'summaries'}})
    completions=[{'index':i,'unit_id':uid,'status':'PASS','context_directory':'contexts/'+uid} for i,uid in enumerate(generated_ids)]
    originals=[{'index':i,'unit_id':uid,'status':'FAILED' if uid==ids[0] else 'PASS'} for i,uid in enumerate(generated_ids)]
    put(census/'summaries/structural_completion_results.json',completions)
    put(census/'summaries/original_implementation_results.json',originals)
    rows=[]
    for i,uid in enumerate(generated_ids):
        put(census/'contexts'/uid/'structural_completion_certificate.json',{'unit_id':uid,'index':i,
            'key_sha256':hashlib.sha256(canonical(keys[uid])).hexdigest(),'overall_status':'PASS','certificates':{'diagnostics':{'status':'PASS'}}})
        for view in ('raw','pkg'):
            ptr=pointers[uid,view];raw=bodies[ptr['line']-1];fields={k:v for k,v in json.loads(raw).items() if k not in metadata.UNIT_KEYS|{'unrounded_p_full','spectral_coefficients'}}
            rows.append({'index':i,'unit_id':uid,'view':view,'source':ptr,'fields':fields,'complete_provenance_key':keys[uid],
                'key_sha256':hashlib.sha256(canonical(keys[uid])).hexdigest(),'original_row_copy_sha256':hashlib.sha256(raw).hexdigest(),
                'status':'PASS','completion_status':'PASS','structural_overall_status':'PASS','original_implementation_status':originals[i]['status'],
                'diagnostics':{'status':'PASS'},'nondegeneracy_record':{'status':'MISSING','reason':'No explicit nondegeneracy field in original unit; structural diagnostics are separately reported, no new threshold.'}})
    retained=[]
    for i,uid in enumerate(ids[:2]):
        put(old/'contexts'/uid/'certificates.json',{'overall_status':'FAILED' if i==0 else 'PASS'})
        put(old/'contexts'/uid/'structural_completion.json',{'overall_registered_claim_status':'PASS'})
        for view in ('raw','pkg'):
            row=json.loads(json.dumps(next(r for r in rows if (r['unit_id'],r['view'])==(uid,view))))
            row['index']=i;row['structural_overall_status']=row.pop('original_implementation_status');del row['completion_status']
            row['source']['path']='results/derived/old.jsonl';row['source']['line']+=200
            retained.append(row)
    put(new/'attachments.json',rows);put(old/'attachments.json',retained)
    put(new/'descriptive_summaries.json',summarise(rows,3));put(old/'descriptive_summaries.json',summarise(retained,2))
    return new,old,census,units,ids,read,put


def test_attachments_align_identity_and_audit_new_population(extended_attachments):
    from born_ladder.reproduction.attachment_comparison import compare_attachments
    new,old,census,units,ids,read,put=extended_attachments
    c=PolicyComparison(io.StringIO());result=compare_attachments(new,old,census,units,c)
    assert result['overall_agreement'] and result['new_case_validation_agreement']
    assert result['historical_records_compared']==4 and result['generated_records']==6
    assert len(result['new_results_without_archived_counterpart'])==2
    assert all(r['historical_matches']==0 for r in result['new_results_without_archived_counterpart'])
    assert result['summary_population_comparison']['full_generated_summaries_have_archived_cohort_counterpart'] is False
    assert result['cohort_position_projection'][0]=={'unit_id':ids[0],'archived_index':0,'generated_index':2}
    # Distinct whole-population quantiles must not be claimed to match.
    assert read(new/'descriptive_summaries.json')!=read(old/'descriptive_summaries.json')


@pytest.mark.parametrize('mutation',['value','new_value','summary','status','source_hash'])
def test_attachments_scientific_or_integrity_defect_still_fails(extended_attachments,mutation):
    from born_ladder.reproduction.attachment_comparison import compare_attachments
    new,old,census,units,ids,read,put=extended_attachments
    rows=read(new/'attachments.json');target=next(r for r in rows if r['unit_id']==ids[2 if mutation=='new_value' else 0])
    if mutation in ('value','new_value'):target['fields']['brier_score']['q_full']+=.25
    elif mutation=='status':target['completion_status']='FAILED'
    elif mutation=='source_hash':target['original_row_copy_sha256']='wrong'
    else:
        summaries=read(new/'descriptive_summaries.json');summaries[0]['scheduled_contexts']=2
        put(new/'descriptive_summaries.json',summaries)
    put(new/'attachments.json',rows)
    result=compare_attachments(new,old,census,units,PolicyComparison(io.StringIO()))
    assert not result['overall_agreement'] and not result['new_case_validation_agreement']
    if mutation=='value':
        assert any(g['failed'] for g in result.get('field_groups',{}).values()) or not all(r['independent_validation']['overall_agreement'] for r in result['all_record_independent_validations'])


@pytest.mark.parametrize('mutation',['duplicate','missing'])
def test_attachment_membership_is_complete(extended_attachments,mutation):
    from born_ladder.reproduction.attachment_comparison import compare_attachments
    new,old,census,units,ids,read,put=extended_attachments
    rows=read(new/'attachments.json');rows.append(rows[0]) if mutation=='duplicate' else rows.pop()
    put(new/'attachments.json',rows)
    with pytest.raises(ValueError,match='duplicate|membership incomplete'):
        compare_attachments(new,old,census,units,PolicyComparison(io.StringIO()))


@pytest.mark.parametrize('reconstructed',[False,True])
def test_cross_term_package_denominators_decode_immutable_kind(tmp_path,reconstructed):
    from born_ladder.reproduction.full_comparison import package_evidence_counts
    from born_ladder.snapshot.identities import kind_cell_id
    uid='a'*64;units=tmp_path/'units.jsonl';reconstruction=tmp_path/'reconstruction.jsonl'
    units.write_text(''.join(json.dumps({'unit_id':uid,'kind_cell_id':kind_cell_id(uid,k)})+'\n' for k in ('pkg','raw')))
    reconstruction.write_text(json.dumps({'unit_id':uid})+'\n' if reconstructed else '')
    assert package_evidence_counts(units,reconstruction)=={'dual_kind_parity_units':int(not reconstructed),'reconstructed_units':int(reconstructed)}


@pytest.mark.parametrize('mutation',['duplicate','invalid','missing_pair','contradictory','missing_reconstruction','orphan_reconstruction'])
def test_cross_term_kind_and_reconstruction_defects_have_clear_reason(tmp_path,mutation):
    from born_ladder.reproduction.full_comparison import package_evidence_counts
    from born_ladder.snapshot.identities import kind_cell_id
    uid='b'*64;units=tmp_path/'units.jsonl';reconstruction=tmp_path/'reconstruction.jsonl'
    rows=[{'unit_id':uid,'kind_cell_id':kind_cell_id(uid,k)} for k in ('raw','pkg')]
    if mutation=='duplicate':rows.append(rows[0])
    elif mutation=='invalid':rows[0]['kind_cell_id']='invalid'
    elif mutation=='missing_pair':rows.pop()
    elif mutation=='contradictory':rows[0]['kind']='pkg'
    units.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    if mutation!='missing_reconstruction':reconstruction.write_text(json.dumps({'unit_id':'c'*64})+'\n' if mutation=='orphan_reconstruction' else '')
    with pytest.raises((ValueError,FileNotFoundError)) as error:package_evidence_counts(units,reconstruction)
    assert 'kind' not in str(error.value) or str(error.value)!="'kind'"


def test_storage_projection_keeps_input_commitments_and_results():
    for field in ('unit_id','kind_cell_id','basis_projector_field_sha256','preparation_input_sha256','law_numerators','bootstrap_hierarchy_keys'):
        result,_=assess({field:'changed'},{field:'original'},'performance_attachments','uid/raw')
        assert not result['overall_agreement'],field
    result,logs=assess({'path':'new','char_range':[1,2],'file_sha256':'new','line_sha256':'new'},
                       {'path':'old','char_range':[5,7],'file_sha256':'old','line_sha256':'old'},'performance_attachments','uid/raw/source')
    assert result['overall_agreement'] and len(logs)==4


def test_rational_difference_reports_exact_size():
    result,logs=assess('4/7','2/7','complete_certificate_top_fields','uid/gap')
    assert not result['overall_agreement']
    assert logs[0]['absolute_difference_exact']=='2/7' and logs[0]['signed_difference_exact']=='2/7'


@pytest.mark.parametrize('eligibility',[True,False,None])
def test_independent_attachment_summary_checks_all_denominators_and_reasons(eligibility):
    from born_ladder.reproduction.attachment_comparison import audit_summaries
    from born_ladder.summaries import summarise
    rows=[]
    for view in ('raw','pkg'):
        for i,value in enumerate((.1,None,.9)):
            rows.append({'unit_id':str(i),'view':view,'status':'PASS',
                         'fields':{'eligibility':eligibility,'exclusion_reason_code':'known',
                                   'brier_score':{'q_full':value},'dtv_loss':{}}})
    assert audit_summaries(rows,3)==summarise(rows,3)


def test_stored_location_only_change_preserves_exact_science():
    # Identical ordering and science; only the retained container moves.
    old={'unit_id':'same','lenses':{'joint_map':[0,1]},'basis_projector_inputs':[[1.,0.]],
         'source':{'path':'results/derived/units.jsonl','line':7541,'byte_offset':100,
                   'fields':{'basis':{'char_range':[1,4],'field_sha256':'old-envelope'}}}}
    new=json.loads(json.dumps(old))
    new['source'].update(path='collections/collection_0001/units.jsonl',line=6919,byte_offset=300)
    new['source']['fields']['basis'].update(char_range=[5,8],field_sha256='new-envelope')
    result,differences=assess(new,old,'complete_inventory','same')
    assert result['overall_agreement'] and result['all_scientific_values_exact']
    assert len(differences)==5 and all('storage-only projection' in r['rule'] for r in differences)


@pytest.mark.parametrize('reference_native_count,expected_status',[(1,'PASS'),(2,'FAIL')])
def test_full_comparison_cross_term_checks_package_denominators_without_kind(tmp_path,monkeypatch,reference_native_count,expected_status):
    import born_ladder.reproduction.full_comparison as F
    import born_ladder.reproduction.census as C
    from born_ladder.snapshot.identities import kind_cell_id
    root=tmp_path/'run';root.mkdir()
    components={k:k for k in ('worked','census','attachments','competitor_evaluation',
                              'cross_term_evaluation','test_b','locked','lean','competitor_units','cross_term_units')}
    (root/'pipeline.json').write_text(json.dumps({'profile':'full','components':components}))
    evaluation=root/'cross_term_evaluation/attempt';evaluation.mkdir(parents=True)
    (root/'cross_term_evaluation/complete.json').write_text(json.dumps({'summary':{'directory':'attempt'}}))
    science={'statistics':{'raw':{'bootstrap':{'replicate_estimates':[1.]*20000}}}}
    (evaluation/'evaluation.json').write_text(json.dumps(science))
    reference=tmp_path/'reference';reference.mkdir()
    (reference/'evaluation.json').write_text(json.dumps({**science,'package_evidence_census':{
        'dual_kind_parity_units':reference_native_count,'reconstructed_units':0}}))
    archive=tmp_path/'archive.json';archive.write_text(json.dumps({'schema':'born_reproduction_reference_v1',
        'roots':{'data':str(reference)},'predictive':{'cross-term':{'evaluation':'data/evaluation.json'}}}))
    unit_root=tmp_path/'closed_units';unit_root.mkdir();file=unit_root/'units.jsonl';uid='d'*64
    file.write_text(''.join(json.dumps({'unit_id':uid,'kind_cell_id':kind_cell_id(uid,kind)})+'\n' for kind in ('raw','pkg')))
    (unit_root/'rb1v2_g2c_v23_pkg_reconstruction.jsonl').write_text('')
    # The census I/O map intentionally contains only its unit file, not the
    # reconstruction artifact. This is the actual closed-collection schema.
    monkeypatch.setattr(C,'collection_inputs',lambda *args:(None,None,None,'logical/units.jsonl',{'logical/units.jsonl':str(file)},None,{}))
    monkeypatch.setattr(F,'protocol',lambda *args:{'verdict':'UNRESOLVED'})
    result=F.run_comparison(run=root,archive=archive,output=tmp_path/'out')
    stage=json.loads(Path(result['report']).read_text())['reported_results_reproduced']['stages']['evaluation/cross-term']
    assert stage['status']==expected_status,stage
    assert stage['field_groups']['package_evidence_denominators']['compared']==2
    assert stage['field_groups']['package_evidence_denominators']['failed']==(expected_status=='FAIL')
