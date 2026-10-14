"""Exact certificate/rendering checks; no sampling, fits or population inference."""
import copy
import json
import os
from pathlib import Path
import re

import pytest

from born_ladder import arithmetic as A
from born_ladder.reproduction import worked_cases as W, lean_inputs as L
from born_ladder.reproduction.worked_science import ensembles, induced, joined
from born_ladder.reproduction.embedding import transport, ensemble, fragment, order, ri
from born_ladder.transport import Transport

REPO=Path(__file__).resolve().parents[2]
SPECS=REPO/'specifications'


def embedded_original():
    """Public Lean frame/kernel, with canonical emitted representative w itself.

    Exact rational strings here are mathematical inputs, not runner captures.
    No private fixture or external historical archive is needed.
    """
    text=(REPO/'lean_born/BornCalculus/B04Inputs.lean').read_text()
    def rationals(name,end):
        section=text.split('def '+name,1)[1].split('def '+end,1)[0]
        return [A.Q(int(a),int(b)) for a,b in re.findall(r'\((-?\d+) : ℚ\) / (\d+)',section)]
    w=rationals('b04WQ','b04KQ');entries=rationals('b04KQ','b04PQ')
    assert len(w)==32 and len(entries)==1024
    labels={}
    for symbol,field in [('b04Raw','raw_by_state'),('b04Package','package_by_state'),('b04Joint','joint_by_state')]:
        labels[field]=list(map(int,re.search(r'def '+symbol+r'[^!]*!\[([^]]+)\]',text).group(1).split(',')))
    return {'identity':{'exp':'EXP-112','config':'loo_A25','k':2,'step_index':0},
            'born':{'sym_eigvec_basis':[[str(x) for x in w]]},
            'kernel':[[str(x) for x in entries[i:i+32]] for i in range(0,1024,32)],'lens':labels}


@pytest.fixture(scope='module')
def original_certificate():
    context=embedded_original()
    return context,W.original_certificates(context,W.read(SPECS/'worked_cases.json'))


def test_embedded_original_exact_pairs_words_and_finite_bounds(original_certificate):
    context,cert=original_certificate
    w,s,P,K=W.frame(context);pairs=ensembles(w,[['-1','1/2'],['-1/2','1']])
    from born_ladder.reproduction.worked_science import barycenter
    assert barycenter(w,pairs[0])==barycenter(w,pairs[1])
    assert all(sum(z for _,z in e)==1 for e in pairs)
    assert cert['ensemble']['witness']['word']==['BEGIN(joint_by_state,1,retain)','FIRST_READ(0)','PROPAGATE','FINAL_READ(0)','HALT']
    assert A.Q(cert['ensemble']['witness']['left_minus_right']['hi'])<0
    finite=cert['finite_family']['non_density']
    assert (finite['events'],finite['proper_groupings_checked'])==(2340,2316)
    assert A.Q(finite['epsilon_exact'])>0 and A.Q(finite['minimum_valuation_margin_exact'])>0
    assert cert['finite_events']['atomic_word_count']==72
    assert cert['finite_events']['complete_test_count']==12
    assert all(A.Q(cert['amplitude']['operations'][op]['certificate']['rational_gap_lower'])>0 for op in ('K','K2'))
    assert all(A.Q(cert['joined']['operations'][op]['successor_density_distance']['lo'])>0 for op in ('K','K2'))
    assert A.Q(cert['order']['left_minus_right']['hi'])<0


@pytest.mark.parametrize('name', ['B04Inputs','B05Inputs','B06Inputs','B07Inputs'])
def test_public_exact_extractors_render_committed_worked_modules(original_certificate,name):
    context,cert=original_certificate
    renderers={'B04Inputs':lambda:transport.render(context,cert['amplitude'],cert['joined']),
               'B05Inputs':lambda:ensemble.render(context,cert['ensemble']),
               'B06Inputs':lambda:fragment.render(context,cert['finite_family']),
               'B07Inputs':lambda:order.render(context)}
    assert renderers[name]().encode()==(REPO/'lean_born/BornCalculus'/(name+'.lean')).read_bytes()


def test_finite_basis_and_ensemble_word_corruption_rejected(original_certificate):
    context,cert=original_certificate
    bad=copy.deepcopy(cert['finite_family']);bad['basis_exact'][1][0][0]='0'
    with pytest.raises(ValueError,match='certificate basis'):fragment.render(context,bad)
    bad=copy.deepcopy(cert['ensemble']);bad['witness']['h']=2
    with pytest.raises(ValueError,match='registered word'):ensemble.extract(context,bad)
    bad=copy.deepcopy(cert['ensemble']);bad['pair_certificate']['coordinate_barycenter'][0][0]='0'
    with pytest.raises(ValueError,match='equal barycenter'):ensemble.extract(context,bad)
    bad=copy.deepcopy(cert['finite_family']);bad['atomic_effects']['raw_by_state'][0][0][0]='0'
    with pytest.raises(ValueError,match='atomic certificate'):fragment.extract(context,bad)


@pytest.mark.parametrize('corruption', ['preparation','joint'])
def test_capture_binding_rejects_wrong_preparation_or_joint(tmp_path,monkeypatch,corruption):
    from dataclasses import asdict
    from born_ladder.reproduction import runs
    job=runs.Invocation('EXP-112','A13_A11',840007,32)
    raw=[0]*16+[1]*16;pkg=[i%2 for i in range(32)]
    alphabet=sorted(set(zip(raw,pkg)));joint=[alphabet.index(p) for p in zip(raw,pkg)]
    K=[[float(i==j) for j in range(32)] for i in range(32)]
    kernel={'exp':job.experiment,'config':job.configuration,'kernel_seed':job.seed,'n':32,'kernel':K}
    born={'cell':job.configuration,'seed':job.seed,'scale':32,'k':2,'step_index':0,'starts':[0],'tau':1,
          'p_theory':[1.]+[0.]*31,'partition':raw,'packaging':pkg,'sym_eigvec_basis':[[i-15.5 for i in range(32)]]}
    header={'kernel':K,'contexts':[{'k':2,'step_index':0,'raw_by_state':raw,'package_by_state':pkg,'joint_by_state':joint}]}
    artifacts=[{'path':name} for name in ('sample.kernel.json','sample.audit.jsonl','stdout.bin')]
    (tmp_path/'runset.json').write_text(json.dumps({'invocations':[{**asdict(job),'id':job.id}]}))
    (tmp_path/'sample.kernel.json').write_text(json.dumps(kernel))
    (tmp_path/'sample.audit.jsonl').write_text(json.dumps(header)+'\n')
    (tmp_path/'stdout.bin').write_text('KEY_BORN_PROBE_JSON '+json.dumps(born)+'\n')
    monkeypatch.setattr(runs.RunSpecifications,'grid',lambda *args:[job])
    monkeypatch.setattr(W.Manifest,'completed',lambda *args:{job.id:{'artifacts':artifacts}})
    wanted={'configuration':job.configuration,'resolution':2,'step_index':0}
    assert W.captured_context([tmp_path],wanted,SPECS,'worked-cases')['kernel']==K
    if corruption=='preparation':
        born['p_theory'][0]=.5
        (tmp_path/'stdout.bin').write_text('KEY_BORN_PROBE_JSON '+json.dumps(born)+'\n')
        message='preparation replay'
    else:
        header['contexts'][0]['joint_by_state'][0]=3
        (tmp_path/'sample.audit.jsonl').write_text(json.dumps(header)+'\n')
        message='immutable joint'
    with pytest.raises(ValueError,match=message):W.captured_context([tmp_path],wanted,SPECS,'worked-cases')


def test_cached_lean_certificate_corruption_rejected(original_certificate,tmp_path):
    context,cert=original_certificate
    # A selected public embedded carrier suffices; no scored archive is read.
    from born_ladder.claim_checks import embedded_carrier
    m=embedded_carrier(REPO/'lean_born');selected=copy.deepcopy(context)
    selected['identity']={'exp':'EXP-112','config':'A13_A11','k':2,'step_index':0}
    selected['born']['sym_eigvec_basis']=[list(map(str,m.w))]
    selected['lens']=m.x['lens']
    w,s,P,K=W.frame(selected);m=__import__('born_ladder.instruments',fromlist=['Instrument']).Instrument(selected,w,s,P,K)
    for name,ctx in [('original',copy.deepcopy(context)),('selected',selected)]:
        w,s,P,_=W.frame(ctx);ctx['exact']={'w':A.qserial(w),'s':str(s),'projector':A.qserial(P)}
        W.write(tmp_path/name/'CONTEXT.json',ctx)
    witness=W.selected_witness(m);other={'strictness':witness,'six_state':A.certify_G(s),'carrier':W.carrier_certificate(m),
        'lean_certificates':{'RI':A.qserial(ri.extract(selected,witness))}}
    W.write(tmp_path/'original/certificates.json',cert);W.write(tmp_path/'selected/certificates.json',other)
    W.write(tmp_path/'selected/initial_strictness_certificate.json',witness);W.write(tmp_path/'selected/six_state_certificate.json',other['six_state'])
    L.checked_worked(tmp_path)
    bad=copy.deepcopy(cert);bad['lean_certificates']['B06'][0]='1'
    (tmp_path/'original/certificates.json').write_text(json.dumps(bad))
    with pytest.raises(ValueError,match='Lean certificate numerical fields'):L.checked_worked(tmp_path)
    (tmp_path/'original/certificates.json').write_text(json.dumps(cert))
    other['lean_certificates']['RI']['gap']='0'
    (tmp_path/'selected/certificates.json').write_text(json.dumps(other))
    with pytest.raises(ValueError,match='RI Lean certificate numerical fields'):L.checked_worked(tmp_path)


def test_contract_parameters_cannot_be_silently_ignored():
    contract=W.read(SPECS/'worked_cases.json');W.validate_contract(contract)
    for key,value in [('source_root_bits',383),('null_direction_amplitude_scale','1/8'),
                      ('lean_root_bits',{'B04':39,'B05':64,'B07':64})]:
        altered={**contract,key:value}
        with pytest.raises(ValueError,match='numerical contract'):W.validate_contract(altered)


def test_certificate_writer_is_deterministic_and_refuses_changed_numbers(tmp_path):
    path=tmp_path/'certificate.json';data={'rational':A.Q(1,3),'nested':[(1,2)]}
    W.write(path,data);first=path.read_bytes();W.write(path,data)
    assert path.read_bytes()==first
    with pytest.raises(ValueError,match='scientific result changed'):W.write(path,{'rational':A.Q(2,3)})


def test_partial_census_cannot_render_full_modules(tmp_path):
    (tmp_path/'inventory').mkdir();(tmp_path/'summary').mkdir()
    (tmp_path/'complete.json').write_text(json.dumps({'summary':{'inventory_directory':'inventory','summary_directory':'summary'}}))
    for path in ('inventory/INVENTORY.json','summary/structural_completion_results.json','summary/maximal_gap_witnesses.json'):
        (tmp_path/path).write_text('[]')
    with pytest.raises(ValueError,match='census count mismatch: expected 120 cases, found 0'):L.census_records(tmp_path)
    with pytest.raises(ValueError,match='census count mismatch: expected 121 cases, found 0'):
        L.census_records(tmp_path,expected_count=121)


def test_historical_algebraic_parser_accepts_only_exact_supported_expressions():
    from born_ladder.reproduction.worked_comparison import algebraic_states
    states=algebraic_states(['Matrix([[1/4, sqrt(12)/8], [sqrt(12)/8, 3/4]])'],A.Q(3))
    assert states[0][0][1]['radical_coefficient']=='1/4'
    with pytest.raises(ValueError,match='unsupported'):
        algebraic_states(['Matrix([[1, __import__("os").system("exit 1")], [0, 0]])'],A.Q(3))


@pytest.mark.data
def test_complete_worked_case_reference_and_eight_modules():
    generated=os.environ.get('E2E_P3BC_WORKED_OUTPUT');reference=os.environ.get('E2E_P3BC_REFERENCE');rendered=os.environ.get('E2E_P3BC_LEAN_OUTPUT')
    if not all((generated,reference,rendered)):
        pytest.skip('set E2E_P3BC_WORKED_OUTPUT, E2E_P3BC_REFERENCE and E2E_P3BC_LEAN_OUTPUT (docs/reproduction.md)')
    from born_ladder.reproduction.worked_comparison import compare_worked_cases
    result=compare_worked_cases(generated,reference)
    assert result['overall_agreement'],result['field_groups']
    assert sum(row['compared'] for row in result['field_groups'].values())>80000
    for name in L.MODULES:
        assert (Path(rendered)/'BornCalculus'/(name+'.lean')).read_bytes()==(REPO/'lean_born/BornCalculus'/(name+'.lean')).read_bytes()
