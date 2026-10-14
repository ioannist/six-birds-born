"""Round-6 probes use real case 0, with immutable source reads and local copies."""
import json
import os
from pathlib import Path
import shutil
import io

import pytest

from born_ladder.reproduction.census_case_validation import RetainedInputs
from born_ladder.reproduction.census_comparison import read, validate_new_case
from born_ladder.reproduction.comparison_policy import PolicyComparison
from test_e2e_p8 import reordered_census

pytestmark = pytest.mark.data


@pytest.fixture(scope='module')
def retained():
    root=os.environ.get('E2E_P8_CENSUS_OUTPUT')
    if not root:pytest.skip('set E2E_P8_CENSUS_OUTPUT to the full retained census')
    inputs=RetainedInputs(root);summary=read(inputs.root/'complete.json')['summary']
    completed=read(inputs.root/summary['summary_directory']/'structural_completion_results.json')
    original=read(inputs.root/summary['summary_directory']/'original_implementation_results.json')
    return inputs,completed,original


@pytest.fixture
def case_zero(tmp_path,retained):
    inputs,completed,original=retained;row=completed[0]
    assert row['unit_id']=='21cb64fbd54925c4060a39657f0e540db90b0a8b3e7affab8bfefb73c647952d'
    directory=tmp_path/'case';shutil.copytree(inputs.root/row['context_directory'],directory)
    return directory,row,original[0],inputs


PROBES = [
    ('CONTEXT.json',('born','seed'),840016),
    ('structural_completion_certificate.json',('certificates','kernel','exponent'),2),
    ('structural_completion_certificate.json',('certificates','kernel','source','matrix_shape'),[31,32]),
    ('structural_completion_certificate.json',('certificates','carrier','rank'),3),
    ('structural_completion_certificate.json',('certificates','carrier','distinct_w'),23),
    ('structural_completion_certificate.json',('certificates','carrier','G',0,0),'31'),
    ('CONTEXT.json',('born','cell'),'A13_A11'),
    ('CONTEXT.json',('born','k'),3),
    ('structural_completion_certificate.json',('certificates','strictness','rho_left',0,0),'1'),
    ('structural_completion_certificate.json',('certificates','strictness','preparations','p',0),'0'),
    ('structural_completion_certificate.json',('certificates','factorization_controls','indexed_receipt','tau'),1),
    ('structural_completion_certificate.json',('certificates','C_premises','C_M'),'FAIL'),
    ('structural_completion_certificate.json',('certificates','C_premises','atom_certificates',0,'positive'),False),
    ('structural_completion_certificate.json',('certificates','diagnostics','nonconstant_amplitude_energy_fraction','hi'),'1'),
    ('structural_completion_certificate.json',('certificates','correspondence','delta_interval','hi'),'1'),
    ('structural_completion_certificate.json',('certificates','correspondence','uniform_floating_envelope','floating_TV_error_exact'),'1'),
    ('structural_completion_certificate.json',('key_sha256',),'wrong-digest'),
    ('structural_completion_certificate.json',('certificates','carrier','unexpected_scientific_value'),1),
    ('six_state_exact_completion.json',('projector_roots',),False),
    ('six_state_exact_completion.json',('real_positivity',),'wrong-premise'),
    ('six_state_exact_completion.json',('states_and_sharp_yes_effects',0,0,0,'unexpected_scientific_value'),1),
    ('atom_classes.json',('atoms',0,'constant_block'),True),
    ('instrument_root_controls.json',(1,'root_certificate','denominator','hi_approx'),1.0),
    ('landed_own_input_prediction.json',('q_full',0),1.0),
    ('maximal_gap_witness.json',('cases',0,'gap_exact'),'1'),
    ('integer_frame.json',('M0',),999),
]


@pytest.mark.parametrize('file,path,value',PROBES,ids=[file+':'+('/'.join(map(str,path))) for file,path,_ in PROBES])
def test_every_scientific_group_rejects_corruption(case_zero,file,path,value):
    directory,row,original,inputs=case_zero
    target=directory/file;doc=read(target);parent=doc
    for key in path[:-1]:parent=parent[key]
    parent[path[-1]]=value;target.write_text(json.dumps(doc))
    result=validate_new_case(directory,row,original,inputs=inputs)
    assert result['independent_validation']['overall_agreement'] is False
    assert result['historical_matches']==0
    assert any(g['differences'] for g in result['independent_validation']['field_groups'].values())


def test_real_case_zero_has_no_unchecked_scientific_fields(case_zero):
    directory,row,original,inputs=case_zero
    result=validate_new_case(directory,row,original,inputs=inputs)
    assert result['independent_validation']['overall_agreement']
    assert result['validation_coverage']['unchecked_scientific_fields']==[]


def test_other_cases_valid_kernel_adapter_cannot_be_substituted(case_zero):
    import copy
    from born_ladder.reproduction.census_case_validation import bind_inputs
    from born_ladder.reproduction.census_comparison import Comparison
    directory,row,_,inputs=case_zero
    inventory=copy.deepcopy(inputs.inventory[row['unit_id']]);context=read(directory/'CONTEXT.json')
    native=inventory['kernel']['artifact']['native_capture_sha256']
    other=next(r for r in inputs.inventory.values() if r['kernel']['artifact'].get('native_capture_sha256',native)!=native)
    inventory['kernel']=copy.deepcopy(other['kernel']);inventory['provenance_key']['kernel']=inventory['kernel']
    pointer=inventory['kernel']['artifact'];body,_,_=inputs.line(pointer,True);lo,hi=pointer['char_range']
    context['kernel']=json.loads(body[lo:hi])
    c=Comparison(project_bindings=False);bind_inputs(c,context,inventory,inputs)
    assert not c.result()['overall_agreement']
    assert c.groups['retained_kernel_capture_join']['differences']


def test_missing_retained_sources_cannot_pass(case_zero,tmp_path):
    directory,row,original,_=case_zero
    with pytest.raises(ValueError,match='retained inventory/source view required'):
        validate_new_case(directory,row,original)


def test_multiple_configurations_in_one_invocation_are_bound_separately(retained):
    from born_ladder.reproduction.census_case_validation import bind_inputs
    from born_ladder.reproduction.census_comparison import Comparison
    inputs, completed, _ = retained
    configurations = {}
    for invocation, configuration in inputs.capture_bindings:
        configurations.setdefault(invocation, set()).add(configuration)
    row = next(row for row in completed
               if len(configurations.get(inputs.inventory[row['unit_id']]['provenance_key']['invocation_id'], ())) > 1)
    inventory = inputs.inventory[row['unit_id']]
    context = read(inputs.root/row['context_directory']/'CONTEXT.json')
    c = Comparison(project_bindings=False)
    bind_inputs(c, context, inventory, inputs)
    assert c.result()['overall_agreement']
    assert c.groups['retained_kernel_capture_join']['exact'] == 5


@pytest.fixture
def three_real_cases(tmp_path,retained):
    """Two genuine archived cases and genuine added case 0; no fake witnesses."""
    import copy
    from born_ladder.archive import sha
    inputs,completed,original=retained
    old_root=Path(os.environ.get('E2E_P8_CENSUS_REFERENCE','scratch/ladder/CENSUS'))
    old_inventory=read(old_root/'INVENTORY.json')[:2]
    wanted=[completed[0]['unit_id'],*[r['unit_id'] for r in old_inventory]]
    by_id={r['unit_id']:r for r in completed};orig_by_id={r['unit_id']:r for r in original}
    generated=tmp_path/'generated';reference=tmp_path/'reference';generated.mkdir();reference.mkdir()
    def put(path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
    inventory=[];rows=[];originals=[]
    for index,uid in enumerate(wanted):
        inventory.append(inputs.inventory[uid]);row=copy.deepcopy(by_id[uid]);row['index']=index
        row['context_directory']='contexts/'+uid;rows.append(row)
        original_row=copy.deepcopy(orig_by_id[uid]);original_row['index']=index;originals.append(original_row)
        target=generated/row['context_directory']
        shutil.copytree(inputs.root/by_id[uid]['context_directory'],target)
        cert=read(target/'structural_completion_certificate.json');cert['index']=index
        cert['certificates']['carrier']['uniform_proof_binding']['frame_context']=str(target/'CONTEXT.json')
        cert['certificates']['C_premises']['six_state_certificate']=str(target/'six_state_exact_completion.json')
        put(target/'structural_completion_certificate.json',cert)
        gaps=read(target/'maximal_gap_witness.json')
        gaps['cases'][0]['case']=index;gaps['minimum_cases']=[index];put(target/'maximal_gap_witness.json',gaps)
    old_certificates=[]
    for index,row in enumerate(old_inventory):
        uid=row['unit_id'];target=reference/'contexts'/uid
        shutil.copytree(old_root/'contexts'/uid,target)
        cert=read(target/'certificates.json');cert['index']=index;put(target/'certificates.json',cert);old_certificates.append(cert)
        completion=read(target/'structural_completion.json');completion['index']=index;put(target/'structural_completion.json',completion)
    put(reference/'INVENTORY.json',old_inventory);put(reference/'structural_results.json',old_certificates)
    put(generated/'inventory/INVENTORY.json',inventory)
    put(generated/'summary/structural_completion_results.json',rows)
    put(generated/'summary/original_implementation_results.json',originals)
    files=dict(inputs.files)
    for item in inventory:
        pointer=item['kernel']['artifact'];files[pointer['path']]=str(inputs.path(pointer['path']))
    put(generated/'census_plan.json',{'logical_to_execution_files':files,
        'capture_bindings':list(inputs.capture_bindings.values())})
    def seal():
        artifacts=[{'path':str(p.relative_to(generated)),'sha256':sha(p)} for p in generated.rglob('*') if p.is_file() and p.name!='complete.json']
        put(generated/'complete.json',{'status':'PASS','artifacts':artifacts,'summary':{'completion_status':'PASS','selected_count':3,
            'inventory_directory':'inventory','summary_directory':'summary'}})
    seal()
    return generated,reference,rows[0],seal


@pytest.mark.parametrize('file,path,value',PROBES[:6],ids=['eddy_seed','eddy_exponent','eddy_shape','eddy_rank','eddy_distinct_w','eddy_gram'])
def test_eddy_mutations_fail_in_real_three_case_comparison(three_real_cases,file,path,value):
    from born_ladder.reproduction.census_comparison import compare_census
    generated,reference,row,seal=three_real_cases
    target=generated/row['context_directory']/file;doc=read(target);parent=doc
    for key in path[:-1]:parent=parent[key]
    parent[path[-1]]=value;target.write_text(json.dumps(doc));seal()
    result=compare_census(generated,reference,comparison=PolicyComparison(io.StringIO()))
    assert not result['overall_agreement']
    assert result['historical_compared_fields_agreement']
    assert result['historical_contexts_compared']==2
    assert result['new_case_validation_agreement'] is False
    assert result['new_results_without_archived_counterpart'][0]['historical_matches']==0


def test_valid_three_case_comparison_passes(three_real_cases):
    from born_ladder.reproduction.census_comparison import compare_census
    generated,reference,_,_=three_real_cases
    result=compare_census(generated,reference,comparison=PolicyComparison(io.StringIO()))
    assert result['overall_agreement']
    assert result['new_contexts']==1 and result['new_historical_matches']==0


def test_historical_unpaired_root_files_are_independently_checked(reordered_census):
    # The companion fixture has complete mathematical frames, while its normal
    # comparison uses mocked unrelated checks. Exercise root population and
    # endpoints here without inventing a historical equality.
    from fractions import Fraction as Q
    from born_ladder.reproduction.census_case_validation import principal
    from born_ladder.reproduction.census_comparison import compare_census
    root,archive,lean=reordered_census
    uid='a';context=read(root/'contexts'/uid/'CONTEXT.json');w=list(map(Q,context['exact']['w']));s=Q(context['exact']['s'])
    labels=context['lens']['raw_by_state'];blocks=[{i for i,v in enumerate(labels) if v==g} for g in sorted(set(labels))]
    subsets=[[],sorted(blocks[0]),sorted(blocks[1]),list(range(32))];controls=[]
    for states in subsets:
        a=sum((w[i] for i in states),Q(0));b=sum(w[i]**2 for i in states)
        _,certificate=principal([[Q(len(states),32),a/32],[a/s,b/s]])
        controls.append({'subset':states,'root_certificate':certificate})
    (archive/'contexts'/uid/'instrument_root_controls.json').unlink()
    path=root/'contexts'/uid/'instrument_root_controls.json';path.write_text(json.dumps(controls))
    result=compare_census(root,archive,lean_root=lean)
    assert result['overall_agreement']
    assert not result['unavailable_stored_reference_files']
    unpaired=result['historical_outputs_without_archived_counterpart']
    assert len(unpaired)==1 and unpaired[0]['historical_matches']==0
    assert unpaired[0]['independent_validation']['overall_agreement']
    path.write_text('[]')
    result=compare_census(root,archive,lean_root=lean)
    assert not result['overall_agreement']


ROUND7_PROBES = [
    ('original_implementation.json',('status',),'FAILED','complete_original_outcome'),
    ('original_implementation.json',('C_premises','status'),'FAILED','original_native_premise_schema'),
    ('original_implementation.json',('correspondence_status',),'FAILED','complete_original_outcome'),
    ('original_implementation.json',('unexpected_scientific_value',),1,'complete_original_outcome'),
    ('six_state_exact_completion.json',('five_mixture_identities',0,0,0),0.5,'complete_typed_six_state_fields'),
    ('six_state_exact_completion.json',('YES_table_exact',0,0),True,'complete_typed_six_state_fields'),
    ('six_state_exact_completion.json',('YES_table_exact',0,0),1.0,'complete_typed_six_state_fields'),
    ('six_state_exact_completion.json',('states_and_sharp_yes_effects',0,0,0,'rational'),True,'complete_typed_six_state_fields'),
    ('six_state_exact_completion.json',('five_mixture_identities',0,0,1),0.5,'complete_typed_six_state_fields'),
    ('six_state_symbolic_original.json',('contradiction_value',),3.0,'complete_original_symbolic_native_replay'),
    ('six_state_symbolic_original.json',('G_states',0),'wrong matrix','complete_original_symbolic_native_replay'),
    ('six_state_symbolic_original.json',('unexpected_scientific_value',),1,'complete_original_symbolic_native_replay'),
    ('structural_completion_certificate.json',('certificates','kernel','exponent'),True,'complete_scientific_certificate_groups'),
    ('structural_completion_certificate.json',('certificates','carrier','G',0,0),32,'complete_scientific_certificate_groups'),
    ('structural_completion_certificate.json',('certificates','carrier','uniform_proof_binding','wall_seconds'),1,'complete_scientific_certificate_groups'),
    ('integer_frame.json',('M0',),25.0,'exact_integer_frame'),
    ('landed_own_input_prediction.json',('no_scores_or_losses_computed',),1,'complete_own_input_prediction'),
    ('atom_classes.json',('atoms',0,'singleton'),0,'complete_atom_classes'),
]


def mutate_and_rebind(directory, row, original, file, path, value):
    """Repair every affected certificate digest, then let the caller reseal."""
    from born_ladder.archive import sha
    target=directory/file;doc=read(target);parent=doc
    for key in path[:-1]:parent=parent[key]
    parent[path[-1]]=value;target.write_text(json.dumps(doc))
    if file=='original_implementation.json':
        original={'index':row['index'],'unit_id':row['unit_id'],**doc}
    cert_path=directory/'structural_completion_certificate.json';cert=read(cert_path)
    cp=cert['certificates']['C_premises']
    cp['six_state_certificate_sha256']=sha(directory/'six_state_exact_completion.json')
    cp['context_frame_sha256']=sha(directory/'CONTEXT.json')
    cert['certificates']['carrier']['uniform_proof_binding']['frame_context_sha256']=sha(directory/'CONTEXT.json')
    cert_path.write_text(json.dumps(cert))
    return original


@pytest.mark.parametrize('file,path,value,group',ROUND7_PROBES)
def test_round7_resealed_scientific_changes_fail_direct_and_comparison(three_real_cases,file,path,value,group):
    from born_ladder.reproduction.census import verify_artifacts
    from born_ladder.reproduction.census_comparison import compare_census
    generated,reference,row,seal=three_real_cases;directory=generated/row['context_directory']
    original_path=generated/'summary/original_implementation_results.json';originals=read(original_path)
    originals[0]=mutate_and_rebind(directory,row,originals[0],file,path,value)
    original_path.write_text(json.dumps(originals));seal()
    # Verify the freshly changed case against its own new commitments, not
    # the parent run's immutable hashes. A stale digest cannot make this fail.
    verify_artifacts(generated,read(generated/'complete.json')['artifacts'])
    direct=validate_new_case(directory,row,originals[0],inputs=RetainedInputs(generated))
    groups=direct['independent_validation']['field_groups']
    assert not direct['independent_validation']['overall_agreement']
    assert groups[group]['differences']
    assert not any('sha256' in d['field'] for g in groups.values() for d in g['differences'])
    result=compare_census(generated,reference,comparison=PolicyComparison(io.StringIO()))
    assert result['historical_compared_fields_agreement']
    assert not result['new_case_validation_agreement'] and not result['overall_agreement']


def test_round7_original_summary_is_bound_to_case_file(three_real_cases):
    from born_ladder.reproduction.census_comparison import compare_census
    generated,reference,row,seal=three_real_cases
    path=generated/'summary/original_implementation_results.json';originals=read(path)
    originals[0]['status']='FAILED';path.write_text(json.dumps(originals));seal()
    result=compare_census(generated,reference,comparison=PolicyComparison(io.StringIO()))
    new=result['new_results_without_archived_counterpart'][0]
    assert not new['independent_validation']['overall_agreement']
    assert new['independent_validation']['field_groups']['original_summary_file_binding']['differences']


def test_round7_unrecognized_case_record_fails(three_real_cases):
    from born_ladder.reproduction.census_comparison import compare_census
    generated,reference,row,seal=three_real_cases
    (generated/row['context_directory']/'unreviewed_science.json').write_text('{"value":1}')
    seal();result=compare_census(generated,reference,comparison=PolicyComparison(io.StringIO()))
    new=result['new_results_without_archived_counterpart'][0]
    assert not new['independent_validation']['overall_agreement']
    assert new['independent_validation']['field_groups']['complete_case_record_population']['differences']


@pytest.mark.parametrize('empty_error',[False,True])
def test_round7_native_failure_event_is_explicitly_qualified(tmp_path,retained,empty_error):
    inputs,completed,originals=retained
    index=next(i for i,v in enumerate(originals) if v['C_premises']['status']=='FAILED')
    row=completed[index];directory=tmp_path/'case';shutil.copytree(inputs.root/row['context_directory'],directory)
    original=originals[index]
    if empty_error:
        # str(AssertionError()) is legitimately empty. Exception text is a
        # named qualified field; schema must not require a nonempty message.
        stored=read(directory/'original_implementation.json');stored['C_premises']['error']=''
        (directory/'original_implementation.json').write_text(json.dumps(stored))
        original={'index':row['index'],'unit_id':row['unit_id'],**stored}
    result=validate_new_case(directory,row,original,inputs=inputs)
    assert result['independent_validation']['overall_agreement']
    fields=result['validation_coverage']['unchecked_scientific_fields']
    assert any('original_implementation.json/C_premises/status'==f for f in fields)
    assert all('original_implementation.json/' in f for f in fields)
