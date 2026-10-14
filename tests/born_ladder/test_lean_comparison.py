"""Round 8: retained statements/axiom sets, additions and fresh receipts."""
from collections import Counter
from copy import deepcopy
import io
import json
from pathlib import Path
import pytest
from born_ladder.reproduction.comparison_policy import PolicyComparison
from born_ladder.reproduction import lean_comparison as L


@pytest.fixture
def evidence(tmp_path):
    old, new = tmp_path/'historical', tmp_path/'fresh'
    for root in (old,new):
        (root/'BornCalculus').mkdir(parents=True)
        (root/'BornCalculus.lean').write_text('import BornCalculus.Basic\n')
        (root/'BornCalculus/Basic.lean').write_text('-- initial header\nnamespace BornCalculus\ndef old : Nat := 1\nend BornCalculus\n')
        for name in ('lakefile.toml','lake-manifest.json','lean-toolchain'):
            (root/name).write_text('retained build configuration\n')
    (new/'BornCalculus/Added.lean').write_text('namespace BornCalculus\ndef added : Nat := 2\nend BornCalculus\n')
    rows=L.driver().inventory(new)
    historical={'status':'PASS','declarations':1,'allowed_axioms':sorted(L.ALLOWED),
                'dependencies':{'BornCalculus.old':['Quot.sound','propext','Classical.choice']},'forbidden':{}}
    measurement={'wall_seconds':1.,'peak_tree_rss_bytes':1,'max_processes':1,'max_lean_processes':1,'sample_interval_seconds':.05}
    audit={'status':'PASS','fresh':True,'declarations':2,'allowed_axioms':sorted(L.ALLOWED),
           'dependencies':{'BornCalculus.old':sorted(L.ALLOWED),'BornCalculus.added':['propext']},'forbidden':{},
           'inventory_scope':L.SCOPE,'breakdown':{'kind':dict(Counter(r['kind'] for r in rows)),
            'directory':dict(Counter(str(Path(r['file']).parent) for r in rows)),
            'namespace':dict(Counter('.'.join(r['components'][:-1]) for r in rows))},
           'ledger':{'LeanDeclarationsAudited':2,'evidence_type':'audit_metadata'},'macros':{'LeanDeclarations':2},
           'measurement':measurement,'kernel_graph':{'reachable_constants':10,'dependency_edges':15,'traversal_ms':1}}
    build={'status':'PASS','modules':3,'fresh_modules':1,**measurement}
    coverage={'status':'APPLICABLE','build_status':'BUILT_AND_AUDITED','full_cohort_inputs':True,
              'census_cases':2122,'exact_certificate_cases_checked':2122,'worked_certificates_checked':True,
              'required_build_targets':['BornCalculus.Census.FullWitness','BornCalculus.Census.AuditFull'],
              'registered_gap_bound_failures':117,'registered_gap_bound_satisfied':False}
    replay=deepcopy(audit)
    return {'target':new,'historical_sources':old,'audit':audit,'historical_audit':historical,
            'build':build,'coverage':coverage,'workspace':tmp_path,
            'fresh_check':lambda *args:deepcopy(replay)}


def compare(evidence):
    stream=io.StringIO();c=PolicyComparison(stream)
    details=L.compare_lean(c,**evidence)
    return c.result(),details,stream.getvalue()


def test_axiom_order_and_initial_header_are_not_failures(evidence):
    p=evidence['target']/'BornCalculus/Basic.lean'
    p.write_text('/- fresh header /- nested -/ -/\n'+p.read_text().split('\n',1)[1])
    result,details,findings=compare(evidence)
    assert result['overall_agreement']
    assert details['historical_declarations']==1 and details['added_declarations']==1
    assert details['historical_matches_for_added_declarations']==0
    assert 'header_projection' in findings
    assert details['receipt_metadata_validation']=='separate from historical equality'


@pytest.mark.parametrize('mutation,group',[
    ('missing_historical','historical_Lean_declaration_membership'),
    ('historical_axioms','historical_Lean_transitive_axiom_sets'),
    ('historical_statement','historical_Lean_statement_sources'),
    ('added_forbidden','added_Lean_allowed_transitive_axioms'),
    ('added_outside_inventory','fresh_Lean_inventory_membership'),
    ('nonfresh','fresh_Lean_audit_freshness'),
    ('stale_disposition','formal_coverage_build_status'),
    ('count','fresh_Lean_declaration_count'),
    ('coverage','formal_exact_cases'),
    ('build','fresh_Lean_build_status'),
    ('type','fresh_Lean_audit_freshness'),
    ('unexpected_field','fresh_Lean_receipt_schema'),
    ('directory_count','fresh_Lean_breakdown'),
    ('added_source_missing','fresh_Lean_inventory_membership'),
])
def test_lean_scientific_corruption_must_fail(evidence,mutation,group):
    audit=evidence['audit']
    if mutation=='missing_historical':del audit['dependencies']['BornCalculus.old']
    elif mutation=='historical_axioms':audit['dependencies']['BornCalculus.old']=['propext']
    elif mutation=='historical_statement':
        p=evidence['target']/'BornCalculus/Basic.lean';p.write_text(p.read_text().replace(':= 1',':= 7'))
    elif mutation=='added_forbidden':audit['dependencies']['BornCalculus.added'].append('sorryAx')
    elif mutation=='added_outside_inventory':audit['dependencies']['BornCalculus.invented']=['propext']
    elif mutation=='nonfresh':audit['fresh']=False
    elif mutation=='stale_disposition':evidence['coverage']['build_status']='PENDING_BUILD_AND_AUDIT'
    elif mutation=='count':audit['declarations']=3
    elif mutation=='coverage':evidence['coverage']['exact_certificate_cases_checked']=120
    elif mutation=='build':evidence['build']['status']='FAIL'
    elif mutation=='type':audit['fresh']=1
    elif mutation=='unexpected_field':audit['unexpected_scientific_field']=1
    elif mutation=='directory_count':audit['breakdown']['directory']['BornCalculus']=3
    elif mutation=='added_source_missing':(evidence['target']/'BornCalculus/Added.lean').unlink()
    result,_,findings=compare(evidence)
    assert not result['overall_agreement']
    assert result['field_groups'][group]['failed']>0
    assert group in findings


@pytest.mark.parametrize('stale',[True,False])
def test_source_change_is_stale_but_cached_source_caption_is_storage_only(evidence,monkeypatch,stale):
    target=evidence['target'];(target/'.lake/packages').mkdir(parents=True)
    paths=[target/'BornCalculus.lean',*sorted((target/'BornCalculus').rglob('*.lean'))]
    hashes={str(p):'current-content-hash' for p in paths}
    for p in paths:
        trace=target/'.lake/build/lib/lean'/p.relative_to(target).with_suffix('.trace')
        trace.parent.mkdir(parents=True,exist_ok=True)
        value='stale-content-hash' if stale and p.name=='Added.lean' else hashes[str(p)]
        caption='/retained/original_checkout/'+p.relative_to(target).as_posix()
        trace.write_text(json.dumps({'inputs':[[caption,value]]}))
    output='\n'.join(json.dumps([p,h]) for p,h in hashes.items())
    monkeypatch.setattr(L.subprocess,'run',lambda *args,**kwargs:type('Result',(),{'stdout':output,'stderr':'','returncode':0})())
    auditor=L.driver();monkeypatch.setattr(auditor,'verify',lambda *args:evidence['audit'])
    monkeypatch.setattr(L,'driver',lambda:auditor)
    if stale:
        with pytest.raises(ValueError,match='stale compiled Lean source: BornCalculus/Added.lean'):
            L.readonly_kernel_check(target,auditor.inventory(target),evidence['workspace'])
    else:
        result=L.readonly_kernel_check(target,auditor.inventory(target),evidence['workspace'])
        assert result['status']=='PASS' and result['source_hashes_checked']==len(paths)


def test_missing_historical_source_file_fails(evidence):
    (evidence['target']/'BornCalculus/Basic.lean').unlink()
    result,_,_=compare(evidence)
    assert not result['overall_agreement']
    assert result['field_groups']['historical_Lean_source_membership']['failed']==1


@pytest.mark.parametrize('fresh,expected',[(True,'PASS'),(False,'FAIL')])
def test_full_comparison_uses_subset_adapter_and_rejects_consistently_logged_nonfresh_receipt(evidence,tmp_path,monkeypatch,fresh,expected):
    from born_ladder.reproduction import full_comparison as F
    root=tmp_path/'run';root.mkdir()
    (root/'lean').symlink_to(evidence['target'],target_is_directory=True)
    components={key:key for key in ('worked','census','attachments','competitor_evaluation',
        'cross_term_evaluation','test_b','locked','lean','competitor_units','cross_term_units')}
    (root/'pipeline.json').write_text(json.dumps({'profile':'full','components':components}))
    coverage={**evidence['coverage'],'audit_receipt':'audit_receipt.json','build_receipt':'build_receipt.json'}
    audit={**evidence['audit'],'fresh':fresh}
    for name,value in [('formal_coverage.json',coverage),('audit_receipt.json',audit),('build_receipt.json',evidence['build'])]:
        (root/'lean'/name).write_text(json.dumps(value))
    logs=root/'logs';logs.mkdir()
    (logs/'lean.log').write_text(json.dumps(evidence['build'])+'\n')
    (logs/'lean-audit.log').write_text(json.dumps(audit)+'\n')
    historical=evidence['historical_sources'];(historical/'audit.json').write_text(json.dumps(evidence['historical_audit']))
    archive=tmp_path/'archive.json';archive.write_text(json.dumps({
        'schema':'born_reproduction_reference_v1','roots':{'old':str(historical)},
        'components':{'lean':'old/.'},'lean_audit':'old/audit.json','lean_historical_sources':'old/.'}))
    original=L.compare_lean
    monkeypatch.setattr(L,'compare_lean',lambda c,**kwargs:original(c,**kwargs,fresh_check=evidence['fresh_check']))
    monkeypatch.setattr(F,'protocol',lambda *args:{'verdict':'UNRESOLVED','stages':{}})
    result=F.run_comparison(run=root,archive=archive,output=tmp_path/'out')
    report=json.loads(Path(result['report']).read_text())
    stage=report['reported_results_reproduced']['stages']['lean']
    assert stage['status']==expected,stage
    assert stage['historical_declarations']==1 and stage['added_declarations']==1
    assert stage['comparison_coverage']['new_results_historical_matches']==0
    assert stage['comparison_coverage']['new_results_no_archived_counterpart']==1
    if fresh:
        assert stage['historical_source_root']==str(historical)
        assert result['reported_results_reproduced']=='UNRESOLVED'
    else:
        assert stage['field_groups']['fresh_Lean_audit_freshness']['failed']==1
        assert result['reported_results_reproduced']=='FAIL'
