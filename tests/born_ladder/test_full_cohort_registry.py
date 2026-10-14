"""Registry scope, full inputs and consistently sealed corruption controls."""
import json
import os
from pathlib import Path
import shutil

import pytest

from born_ladder.__main__ import REGISTRY,LEAN_SCOPE
from born_ladder.full_cohort_claims import IDS,Inputs,require_equal,checked_rows


def test_full_registry_uses_full_endpoints_and_retains_general_domains():
    for identifier in ('P10','P13','B08','B10'):
        assert REGISTRY[identifier][2]
        assert all(name.startswith('Census.') for name in REGISTRY[identifier][2])
        assert '120' not in LEAN_SCOPE[identifier]
    assert 'General.carrier_and_trace' in REGISTRY['P01'][2]
    assert 'General.orth_n_point_model' in REGISTRY['P02'][2]
    assert 'General.orth_encoder_exact_range' in REGISTRY['P14'][2]
    assert 'General.witness_orth_proper_sets' in REGISTRY['B15'][2]
    assert 'factor_on_image_iff' in REGISTRY['B16'][2]
    assert 'census_maximizing_ties' in str(REGISTRY['P13'][2])
    assert '3/20' in LEAN_SCOPE['P13'] and '1/25' in LEAN_SCOPE['P13']


@pytest.mark.parametrize('left,right',[(True,1),(0.0,0),('1',1),([True],[1])])
def test_full_verification_never_coerces_scientific_types(left,right):
    with pytest.raises(ValueError,match='differs'):require_equal('typed input',left,right)


def test_historical_and_reduced_bundles_cannot_certify_full_rows(tmp_path):
    path=tmp_path/'bundle.json'
    for doc in ({'schema':'born_claim_bundle_v1'},
                {'schema':'born_regenerated_bundle_v1','profile':'regenerated','reduced':True}):
        path.write_text(json.dumps(doc))
        with pytest.raises(ValueError,match='historical|reduced'):Inputs(path)


def test_regenerated_public_dispatch_uses_bundle_project_not_checkout(tmp_path,monkeypatch):
    import born_ladder.full_cohort_claims as full
    from born_ladder.reproduction.regenerated_bundle import verify
    path=tmp_path/'bundle.json';path.write_text(json.dumps({'reduced':False}))
    calls=[]
    monkeypatch.setattr(full,'verify',lambda *a,**kw:(calls.append((a,kw)) or {'contexts':2122}))
    for identifier in IDS:
        result=verify(identifier,path,lean_root='unused-checkout-default')
        assert result['checks']['contexts']==2122
        assert result['historical_claim_asserted'] is False



def test_bundle_relocation_uses_committed_components_and_rejects_corruption(tmp_path,monkeypatch):
    from born_ladder.archive import sha
    import born_ladder.full_cohort_claims as full
    root=tmp_path/'relocated';root.mkdir()
    components={}
    for name in ('census','cross_term_units','lean'):
        path=root/name;path.mkdir();(path/'scientific.json').write_text('{"value":1}')
        components[name]={'scientific.json':sha(path/'scientific.json')}
    manifest=root/'bundle.json';manifest.write_text(json.dumps({
        'schema':'born_regenerated_bundle_v1','profile':'regenerated','reduced':False,
        'roots':{name:name for name in components},'files':components}))
    # After file checks the synthetic census lacks its seal; no arbitrary data
    # is admitted merely because it has a self-consistent regenerated manifest.
    with pytest.raises(FileNotFoundError):Inputs(manifest)
    (root/'census/scientific.json').write_text('{"value":2}')
    with pytest.raises(ValueError,match='commitment differs'):Inputs(manifest)


@pytest.mark.parametrize('field,value,accepted',[
    ('/C_premises/six_state_certificate','/old/run/contexts/case/six_state_exact_completion.json',True),
    ('/carrier/uniform_proof_binding/frame_context','/old/run/contexts/case/CONTEXT.json',True),
    ('/carrier/uniform_proof_binding/frame_context','/old/run/contexts/other/CONTEXT.json',False),
    ('/C_premises/context_frame_sha256','wrong-digest',False),
    ('/C_premises/six_state_certificate',True,False),
])
def test_relocated_address_exception_keeps_case_identity_digests_and_types(monkeypatch,field,value,accepted):
    import born_ladder.full_cohort_claims as full
    group={'compared':1,'exact':0,'differences':[{'field':field,'generated':value,'reference':'new'}]}
    result={'independent_validation':{'field_groups':{'complete_scientific_certificate_groups':group},'overall_agreement':False}}
    monkeypatch.setattr(full,'validate_new_case',lambda *a,**kw:result)
    class Data:source=object()
    got=full.numerical_audit(Data(),{'context_directory':'contexts/case'},None,None,None)
    assert got['independent_validation']['overall_agreement'] is accepted


@pytest.mark.data
def test_corrupted_full_cohort_resealed_input_fails_source_binding(tmp_path):
    from born_ladder.archive import sha
    data=os.environ.get('BORN_FULL_COHORT_DATA')
    if not data:pytest.skip('set BORN_FULL_COHORT_DATA to the actual full stage directory')
    original=Path(data)/'census';seal=json.loads((original/'complete.json').read_text())
    rows=json.loads((original/seal['summary']['summary_directory']/'structural_completion_results.json').read_text())
    row=rows[0];name=Path(row['context_directory']);root=tmp_path/'census';root.mkdir()
    # Copy only the mutated case, with immutable read-only links for the other
    # 2,121 cases. All artifact hashes are checked by the real input loader.
    for item in original.iterdir():
        if item.name==name.parts[0] or item.name=='complete.json':continue
        (root/item.name).symlink_to(item.resolve(),target_is_directory=item.is_dir())
    top=root/name.parts[0];top.mkdir()
    for item in (original/name.parts[0]).iterdir():
        if item.name==name.parts[1]:continue
        (top/item.name).symlink_to(item.resolve(),target_is_directory=item.is_dir())
    directory=root/name;shutil.copytree(original/name,directory)
    target=directory/'CONTEXT.json';context=json.loads(target.read_text())
    context['born']['seed']+=1;target.write_text(json.dumps(context))
    cert_path=directory/'structural_completion_certificate.json';cert=json.loads(cert_path.read_text())
    cert['certificates']['carrier']['uniform_proof_binding']['frame_context_sha256']=sha(target)
    cert['certificates']['C_premises']['context_frame_sha256']=sha(target)
    cert_path.write_text(json.dumps(cert))
    for entry in seal['artifacts']:
        if entry['path'] in (str(name/'CONTEXT.json'),str(name/'structural_completion_certificate.json')):
            entry['sha256']=sha(root/entry['path'])
    (root/'complete.json').write_text(json.dumps(seal))
    inputs=Inputs(root)
    with pytest.raises(ValueError,match='case 0 differs'):
        checked_rows(inputs,'lean_born')


def test_scope_words_exclude_empty_sets_and_specify_gap_statistic():
    assert 'centered nonzero' in LEAN_SCOPE['B15']
    assert 'nonempty proper subsets' in LEAN_SCOPE['B15']
    assert 'raw-label-zero trace gap' in LEAN_SCOPE['P13']
    assert 'all three maps' in LEAN_SCOPE['P13']


def test_group_receipt_cannot_promote_one_check_to_other_claims():
    from born_ladder.reproduction.regenerated_bundle import group_receipt
    first={'id':'P03','status':'VERIFIED','checks':{'numerical_cases':2122}}
    with pytest.raises(ValueError,match='claim-specific'):
        group_receipt(('P03','B13'),{'P03':first})
    with pytest.raises(ValueError,match='claim-specific'):
        group_receipt(('P03','B13'),{'P03':first,'B13':first})
    with pytest.raises(ValueError,match='claim-specific'):
        group_receipt(('B13',),{'B13':{**first,'id':'B13'}})
    with pytest.raises(ValueError,match='claim-specific'):
        group_receipt(('P03',),{'P03':{'id':'P03','status':'VERIFIED'}})


def test_smoke_dispatch_is_nonconfirmatory_and_cannot_claim_full_coverage(tmp_path,monkeypatch):
    from born_ladder.reproduction import regenerated_bundle as b
    path=tmp_path/'bundle.json';path.write_text(json.dumps({'reduced':True}))
    monkeypatch.setattr(b,'Bundle',lambda path:type('Bundle',(),{'doc':{'reduced':True},'roots':{}})())
    calls=[];monkeypatch.setattr(b,'verify_group',lambda bundle,group,**kw:calls.append(group) or {'reduced_cases':2})
    receipt=b.verify('P03',path)
    assert receipt['status']=='REDUCED_NONCONFIRMATORY'
    assert receipt['full_cohort_claim_asserted'] is False and calls==['census']
    group=b.group_receipt(('P03',),{'P03':receipt},reduced=True)
    assert group['claim_ids']==[] and group['reduced_check_ids']==['P03']


@pytest.fixture(scope='module')
def resealed_projector_mutation(tmp_path_factory):
    from born_ladder.archive import sha
    data=os.environ.get('BORN_FULL_COHORT_DATA')
    if not data:pytest.skip('set BORN_FULL_COHORT_DATA to the actual full stage directory')
    original=Path(data)/'census';seal=json.loads((original/'complete.json').read_text())
    rows=json.loads((original/seal['summary']['summary_directory']/'structural_completion_results.json').read_text())
    row=rows[2121];name=Path(row['context_directory']);root=tmp_path_factory.mktemp('projector')/'census';root.mkdir()
    for item in original.iterdir():
        if item.name in (name.parts[0],'complete.json'):continue
        (root/item.name).symlink_to(item.resolve(),target_is_directory=item.is_dir())
    top=root/name.parts[0];top.mkdir()
    for item in (original/name.parts[0]).iterdir():
        if item.name==name.parts[1]:continue
        (top/item.name).symlink_to(item.resolve(),target_is_directory=item.is_dir())
    directory=root/name;shutil.copytree(original/name,directory)
    target=directory/'CONTEXT.json';context=json.loads(target.read_text())
    assert context['exact']['P'][0][0]!='0'
    context['exact']['P'][0][0]='0';target.write_text(json.dumps(context))
    certificate=directory/'structural_completion_certificate.json';cert=json.loads(certificate.read_text())
    cert['certificates']['carrier']['uniform_proof_binding']['frame_context_sha256']=sha(target)
    cert['certificates']['C_premises']['context_frame_sha256']=sha(target);certificate.write_text(json.dumps(cert))
    for entry in seal['artifacts']:
        if entry['path'] in (str(name/'CONTEXT.json'),str(name/'structural_completion_certificate.json')):
            entry['sha256']=sha(root/entry['path'])
    (root/'complete.json').write_text(json.dumps(seal))
    return Inputs(root)


@pytest.mark.data
@pytest.mark.parametrize('identifier',sorted(IDS))
def test_each_full_id_rejects_resealed_case_2121_projector(identifier,resealed_projector_mutation,monkeypatch):
    import born_ladder.full_cohort_claims as full
    # The real loader above checks the updated hashes. Reuse its immutable
    # loaded source view across IDs; dispatch and the common auditor are real.
    monkeypatch.setattr(full,'Inputs',lambda *a,**kw:resealed_projector_mutation)
    with pytest.raises(ValueError,match='case 2121 complete exact frame differs'):
        full.verify(identifier,'resealed-full-cohort','lean_born')


@pytest.mark.parametrize('field,value', [('G',[[32,'0'],['0','1']]),('s',True),('w',[0.5]*32)])
def test_complete_exact_frame_types_and_schema_are_audited(field,value):
    from born_ladder.full_cohort_claims import exact_frame,check_exact_frame
    context={'born':{'sym_eigvec_basis':[list(range(32))]}}
    context['exact']=exact_frame(context);context['exact'][field]=value
    with pytest.raises(ValueError,match='complete exact frame'):check_exact_frame(context,0)


def test_bundle_project_differs_from_rendered_inputs_must_fail(tmp_path,monkeypatch):
    import born_ladder.full_cohort_claims as full
    from types import SimpleNamespace
    directory=tmp_path/'case';directory.mkdir()
    context={'born':{'sym_eigvec_basis':[list(range(32))]}}
    context['exact']=full.exact_frame(context);(directory/'CONTEXT.json').write_text(json.dumps(context))
    root=tmp_path/'run-lean/BornCalculus/Census';root.mkdir(parents=True)
    (root/'input_manifest.json').write_text(json.dumps({'cases':1,'ordered_unit_ids':['case']}))
    (root/'Shard000.lean').write_text('different source frame')
    inputs=SimpleNamespace(lean=tmp_path/'run-lean',bundle=tmp_path/'bundle.json',census='unused',
                           completed=[{'index':0}],directories=[directory])
    monkeypatch.setattr(full,'COUNT',1)
    monkeypatch.setattr(full,'Inputs',lambda *a,**kw:inputs)
    from born_ladder.reproduction import lean_inputs
    monkeypatch.setattr(lean_inputs,'full_census_records',lambda *a:([{'unit_id':'case'}],[]))
    monkeypatch.setattr(lean_inputs,'full_shard_text',lambda *a,**kw:'correct retained frame')
    with pytest.raises(ValueError,match='shard input differs'):
        full.verify('P03','bundle',tmp_path/'checkout-which-must-not-be-used')


def test_p13_saved_receipt_contains_every_exact_pair(tmp_path,monkeypatch):
    import born_ladder.full_cohort_claims as full
    from types import SimpleNamespace
    from born_ladder.reproduction.census_extension import robust_outcomes
    pairs=[{'case':425,'i':2,'j':7,'gap_exact':'1/20','labels':[0,1,2],
            'left_exact':'1/10','right_exact':'3/20','eligible_pairs':1}]
    expected=robust_outcomes(pairs)
    # Exercise saved receipt plumbing with a deterministic independently
    # covered claim result, then check exact per-case contents survive JSON.
    inputs=SimpleNamespace(lean=None,bundle=None,inventory=[{'unit_id':'case'}])
    monkeypatch.setattr(full,'Inputs',lambda *a,**kw:inputs)
    monkeypatch.setattr(full,'checked_rows',lambda *a:([],pairs))
    monkeypatch.setattr(full,'bound_checks',lambda *a:{'per_case_witnesses':pairs})
    import born_ladder.__main__ as cli
    monkeypatch.setattr(cli,'audit_endpoints',lambda *a:{'status':'PASS'})
    path=tmp_path/'receipt.json';result=full.verify('P13','data','lean',certificate_output=path)
    assert json.loads(path.read_text())==result
    assert result['per_case_witnesses']==pairs and result['axiom_audit']['status']=='PASS'


def test_valid_bundle_needs_no_checkout_build(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import born_ladder.full_cohort_claims as full
    inputs=SimpleNamespace(lean=tmp_path/'rendered-and-audited-run',bundle=tmp_path/'bundle.json')
    calls=[];monkeypatch.setattr(full,'Inputs',lambda *a,**kw:inputs)
    monkeypatch.setattr(full,'checked_rows',lambda data,root:calls.append(('render',root)) or ([],[]))
    monkeypatch.setattr(full,'bundle_lean_check',lambda data,root:calls.append(('audit',root)) or {'status':'PASS'})
    monkeypatch.setattr(full,'attachments_check',lambda *a:{'records':4244,'type_7_summaries':58})
    result=full.verify('P11','bundle',tmp_path/'unbuilt-checkout')
    assert result['records']==4244
    assert calls==[('render',inputs.lean),('audit',inputs.lean)]


def test_group_receipts_accept_actual_attachment_and_inventory_result_schemas():
    from born_ladder.reproduction.regenerated_bundle import group_receipt
    checks={'P11':{'records':4244,'type_7_summaries':58,'contexts':2122,'rescored':False},
            'B13':{'collection':11177,'rank_two':2122,'availability_subselection':False,
                   'rank_counts':{'2':2122}}}
    for identifier,payload in checks.items():
        receipt={'id':identifier,'status':'VERIFIED','checks':payload}
        assert group_receipt((identifier,),{identifier:receipt})['claim_ids']==[identifier]
