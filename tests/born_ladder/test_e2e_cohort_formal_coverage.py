"""Fresh-cohort integration: exact checks without changing the registered proofs."""
import copy
import json
from fractions import Fraction as Q
from pathlib import Path
import subprocess

import pytest

from born_ladder import arithmetic as A
from born_ladder.robust_census import integer_record, scan_records
from born_ladder.reproduction import lean_inputs as L, pipeline as P

REPO=Path(__file__).resolve().parents[2]
SPECS=REPO/'specifications'


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')


@pytest.fixture(scope='module')
def exact_case():
    # Small exact synthetic frame, identity kernel and uniform preparation.
    # No retained capture, scored unit or external fixture is read.
    from born_ladder.instruments import Instrument
    from born_ladder.reproduction.census_writers.certificates import point_search
    w=[Q(2*i-31,2) for i in range(32)];s=sum(v*v for v in w)
    raw=[int(i>=16) for i in range(32)];package=[i%2 for i in range(32)]
    labels=[raw,package,[2*a+b for a,b in zip(raw,package)]]
    projector=[[Q(1,32)+x*y/s for y in w] for x in w]
    K=[[float(i==j) for j in range(32)] for i in range(32)]
    context={'identity':{'unit_id':'synthetic'},'kernel':K,
        'born':{'sym_eigvec_basis':[list(map(str,w))],'starts':list(range(32)),
                'tau':1,'p_theory':[1/32]*32},
        'lens':dict(zip(L.C.FIELDS,labels)),
        'exact':{'w':list(map(str,w)),'s':str(s),'P':A.qserial(projector)},
        'archived_unit_structural':{'raw':{'basis_and_projector_inputs':{
            'projector':[[float(x) for x in row] for row in projector]}}}}
    model=Instrument(context,w,s,projector,K)
    atoms=[]
    for f,parts in model.parts.items():
        for label,block in parts.items():
            det=len(block)*sum(w[i]**2 for i in block)-sum(w[i] for i in block)**2
            atoms.append({'context':f,'atom':label,'states':list(block),
                'Gram_det_exact':str(det),'effect_exact':A.qserial(model.C[block]),'positive':det>0})
    delta2=sum((x-Q(float(x)))**2 for row in projector for x in row)
    cert={'certificates':{'strictness':point_search(A,model),
        'kernel':{'maximum_row_mass_error_exact':'0'},
        'correspondence':{'delta_squared_exact':str(delta2)},
        'C_premises':{'atom_certificates':atoms,'zero_atom_count':sum(not a['positive'] for a in atoms)},
        'diagnostics':{name:{'lo':'0','hi':'0'} for name in
            ('nonconstant_amplitude_energy_fraction','TV_exact_projected_square_to_uniform_micro32')}}}
    integer=integer_record(context['exact']['w'],labels)
    return context,cert,integer,[{'subset':list(block),'root_certificate':c} for block,c in model.roots.items()],A.certify_G(s)


def cohort(root,count,case):
    context,certificate,integer,roots,six=case;inventory=[];completion=[];pairs=[]
    for i in range(count):
        identity='synthetic-'+str(i);relative='cases/'+identity
        ctx=copy.deepcopy(context);ctx['identity']['unit_id']=identity
        cert=copy.deepcopy(certificate)
        cert['certificates']['strictness']['complete_equal_old_view']['context']=ctx['identity']
        gap=scan_records([integer],require_bound=False);gap['cases'][0]['case']=i;gap['minimum_cases']=[i]
        for name,value in [('CONTEXT.json',ctx),('structural_completion_certificate.json',cert),
            ('integer_frame.json',integer),('maximal_gap_witness.json',gap),
            ('instrument_root_controls.json',roots),('six_state_exact_completion.json',six)]:
            dump(root/relative/name,value)
        inventory.append({'unit_id':identity})
        completion.append({'index':i,'unit_id':identity,'status':'PASS','context_directory':relative})
        pairs.extend(gap['cases'])
    dump(root/'inventory/INVENTORY.json',inventory)
    dump(root/'summary/structural_completion_results.json',completion)
    dump(root/'summary/maximal_gap_witnesses.json',pairs)
    dump(root/'complete.json',{'summary':{'inventory_directory':'inventory','summary_directory':'summary'}})


@pytest.mark.parametrize('count',[121,3])
def test_full_pipeline_other_cohort_checks_all_and_continues(tmp_path,monkeypatch,exact_case,count):
    root=tmp_path/'pipeline';cohort(root/'census',count,exact_case)
    monkeypatch.setattr(P,'validate_output',lambda path,*a:Path(path))
    monkeypatch.setattr(L,'validate_output',lambda path,*a:Path(path))
    checked=[]
    monkeypatch.setattr(L,'checked_worked',lambda path:checked.append(str(path)) or (None,)*4)
    monkeypatch.setattr(L,'project_sources',lambda *a:pytest.fail('off-cohort proof project must not be built'))
    calls=[]
    def child(argv,**kwargs):
        calls.append(argv)
        if 'verify' in argv:
            identifier=argv[argv.index('verify')+1]
            keys=('exact_certificates_rederived','worked_Lean_input_binding','formal_or_control_check',
                  'numerical_artifacts_verified','full_population_recomputed_here','numerically_verified','inference_exact','contexts',
                  'numerical_cases','public_K_map_replay','axiom_audit','validation_coverage',
                  'records','type_7_summaries','per_case_witnesses','registered_3_over_20',
                  'overall','coordinate','symbolic','bit_equality','active','positive','singular',
                  'collection','rank_two','rank_counts')
            receipt={'id':identifier,'status':'VERIFIED','checks':dict.fromkeys(keys,True)}
            kwargs['stdout'].write(('PASS '+identifier+': '+json.dumps(receipt)+'\n').encode())
        if argv[0]=='make':pytest.fail('off-cohort Lean build/audit must not run')
        if 'lean-inputs' in argv:
            L.run_lean_inputs(census=root/'census',worked_cases=root/'worked',output=root/'lean',lean_root=REPO/'lean_born')
        return subprocess.CompletedProcess(argv,0)
    monkeypatch.setattr(P.subprocess,'run',child)
    result=P.run_all(output=root,workers=2,profile='full',specifications=SPECS)
    coverage=result['formal_endpoints']
    assert result['status']=='COMPLETE' and checked
    assert coverage['status']=='NOT_APPLICABLE' and coverage['scope']=='not applicable to this cohort'
    assert coverage['reason']==(
        'formal coverage requires the complete 2,122-case census, or enabled historical '
        'rendering with byte-identical registered ordered 120-case inputs; neither applies to this cohort')
    assert coverage['census_cases']==coverage['exact_certificate_cases_checked']==count
    assert len(json.loads((root/'census/inventory/INVENTORY.json').read_text()))==count
    assert any('test-b-locked' in argv for argv in calls) and any('bundle' in argv for argv in calls)
    # Even the last case must be checked on resume; no truncation to 120.
    last=root/f'census/cases/synthetic-{count-1}/integer_frame.json'
    bad=json.loads(last.read_text());bad['S']+=1;dump(last,bad)
    with pytest.raises(ValueError,match='integer frame differs'):
        L.run_lean_inputs(census=root/'census',worked_cases=root/'worked',output=root/'lean')


def test_other_ordered_hundred_twenty_is_not_registered(tmp_path,monkeypatch):
    # A count alone is not cohort identity. Exercise applicability separately
    # from the exact-check integration above.
    monkeypatch.setattr(L,'validate_output',lambda path,*a:Path(path))
    monkeypatch.setattr(L,'checked_worked',lambda *a:(None,)*4)
    monkeypatch.setattr(L,'census_records',lambda *a,**k:([{}]*120,[]))
    monkeypatch.setattr(L,'input_texts',lambda *a:{name:'different ordered data' for name in L.MODULES})
    monkeypatch.setattr(L,'project_sources',lambda *a:pytest.fail('unmatched cohort must not build'))
    result=L.run_lean_inputs(census='unused',worked_cases='unused',output=tmp_path/'lean',lean_root=REPO/'lean_born')
    assert result['status']=='NOT_APPLICABLE' and result['exact_certificate_cases_checked']==120
    assert 'complete 2,122-case census' in result['reason']
    assert 'enabled historical rendering with byte-identical registered ordered 120-case inputs' in result['reason']


def test_smoke_reason_describes_current_and_historical_inputs(tmp_path,monkeypatch):
    monkeypatch.setattr(L,'validate_output',lambda path,*a:Path(path))
    monkeypatch.setattr(L,'checked_worked',lambda *a:(None,)*4)
    monkeypatch.setattr(L,'census_records',lambda *a,**k:([{}]*15,[]))
    monkeypatch.setattr(L,'input_texts',lambda *a:pytest.fail('smoke must not render historical inputs'))
    result=L.run_lean_inputs(census=tmp_path/'census',worked_cases='unused',
        output=tmp_path/'lean',lean_root=REPO/'lean_born',render_registered=False)
    coverage=json.loads((tmp_path/'lean/formal_coverage.json').read_text())
    assert result['status']==coverage['status']=='NOT_APPLICABLE'
    assert result['reason']==coverage['reason']==(
        'formal coverage requires the complete 2,122-case census, or enabled historical '
        'rendering with byte-identical registered ordered 120-case inputs; neither applies to this cohort')
    assert coverage['census_cases']==15 and result['modules']==[]


@pytest.mark.parametrize('field,changed',[
    ('schema','different-schema'),
    ('census_cases',14),
    ('exact_certificate_cases_checked',14),
    ('worked_certificates_checked',False),
    ('registered_ordered_inputs_match',True),
    ('full_cohort_inputs',True),
    ('status','APPLICABLE'),
    ('scope','registered eight-module proof inputs'),
    ('registered_gap_bound_satisfied',False),
])
def test_smoke_coverage_resume_ignores_old_reason_but_checks_inputs(tmp_path,monkeypatch,field,changed):
    monkeypatch.setattr(L,'validate_output',lambda path,*a:Path(path))
    monkeypatch.setattr(L,'checked_worked',lambda *a:(None,)*4)
    monkeypatch.setattr(L,'census_records',lambda *a,**k:([{}]*15,[]))
    kwargs=dict(census=tmp_path/'census',worked_cases='unused',output=tmp_path/'lean',
        lean_root=REPO/'lean_born',render_registered=False)
    L.run_lean_inputs(**kwargs)
    receipt=tmp_path/'lean/formal_coverage.json'
    expected=json.loads(receipt.read_text())
    old={**expected,'reason':'the public census statements are specific to the registered ordered 120-case inputs'}
    dump(receipt,old)
    resumed=L.run_lean_inputs(**kwargs)
    assert resumed['status']=='NOT_APPLICABLE'
    assert json.loads(receipt.read_text())==expected
    assert resumed['reason']==expected['reason']
    assert expected[field]!=changed
    dump(receipt,{**old,field:changed})
    with pytest.raises(ValueError,match='formal coverage inputs changed on resume'):
        L.run_lean_inputs(**kwargs)


def test_registered_renderer_publishes_identical_eight_bytes(tmp_path,monkeypatch):
    texts={name:(REPO/'lean_born/BornCalculus'/f'{name}.lean').read_text() for name in L.MODULES}
    monkeypatch.setattr(L,'validate_output',lambda path,*a:Path(path))
    monkeypatch.setattr(L,'checked_worked',lambda *a:(None,)*4)
    monkeypatch.setattr(L,'census_records',lambda *a,**k:([{}]*120,[{'gap_exact':'3/20'}]*120))
    monkeypatch.setattr(L,'input_texts',lambda *a:texts)
    monkeypatch.setattr(L,'project_sources',lambda source,out:(out/'BornCalculus').mkdir())
    result=L.run_lean_inputs(census='unused',worked_cases='unused',output=tmp_path/'lean',lean_root=REPO/'lean_born')
    assert result['formal_coverage']['status']=='APPLICABLE' and result['all_eight_byte_equal']
    assert all((tmp_path/'lean/BornCalculus'/f'{name}.lean').read_bytes()==texts[name].encode() for name in L.MODULES)


def test_smoke_never_parameterizes_input_modules(tmp_path,monkeypatch):
    from born_ladder.reproduction.smoke_stages import lean
    calls=[]
    monkeypatch.setattr(L,'run_lean_inputs',lambda **kw:calls.append(kw) or {'status':'NOT_APPLICABLE'})
    assert lean(tmp_path,tmp_path/'lean')['status']=='NOT_APPLICABLE'
    assert calls[0]['render_registered'] is False


def test_off_cohort_formal_verification_is_not_a_failure(tmp_path,monkeypatch):
    from born_ladder.reproduction import regenerated_bundle as B
    dump(tmp_path/'formal_coverage.json',{'status':'NOT_APPLICABLE'})
    monkeypatch.setattr(B,'Bundle',lambda path:type('Bundle',(),{'roots':{'lean':tmp_path},'doc':{'reduced':False}})())
    from born_ladder.__main__ import REGISTRY
    endpoint=next(k for k,v in REGISTRY.items() if v[1]!='data' and k not in B.HISTORICAL_ONLY and not any(k in ids for ids in B.GROUPS.values()))
    dump(tmp_path/'bundle.json',{'reduced':False})
    result=B.verify(endpoint,tmp_path/'bundle.json')
    assert result['status']=='NOT_APPLICABLE' and 'not applicable to this cohort' in result['reason']


@pytest.mark.parametrize('workers',[1,48,96])
def test_registered_pipeline_still_builds_and_audits(tmp_path,monkeypatch,workers):
    root=tmp_path/'pipeline'
    monkeypatch.setattr(P,'validate_output',lambda path,*a:Path(path))
    calls=[]
    def child(argv,**kwargs):
        calls.append(argv)
        if 'verify' in argv:
            identifier=argv[argv.index('verify')+1]
            keys=('exact_certificates_rederived','worked_Lean_input_binding','formal_or_control_check',
                  'numerical_artifacts_verified','full_population_recomputed_here','numerically_verified','inference_exact','contexts',
                  'numerical_cases','public_K_map_replay','axiom_audit','validation_coverage',
                  'records','type_7_summaries','per_case_witnesses','registered_3_over_20',
                  'overall','coordinate','symbolic','bit_equality','active','positive','singular',
                  'collection','rank_two','rank_counts')
            receipt={'id':identifier,'status':'VERIFIED','checks':dict.fromkeys(keys,True)}
            kwargs['stdout'].write(('PASS '+identifier+': '+json.dumps(receipt)+'\n').encode())
        if 'lean-inputs' in argv:
            dump(root/'lean/formal_coverage.json',{'status':'APPLICABLE','census_cases':120,
                'exact_certificate_cases_checked':120,'scope':'registered eight-module proof inputs'})
        return subprocess.CompletedProcess(argv,0)
    monkeypatch.setattr(P.subprocess,'run',child)
    report=P.run_all(output=root,workers=workers,profile='full',specifications=SPECS)
    assert [cmd[1] for cmd in calls if cmd[0]=='make']==['lean','lean-audit']
    assert report['formal_endpoints']['status']=='BUILT_AND_AUDITED'
    verification=[cmd for cmd in calls if 'verify' in cmd]
    from born_ladder.reproduction.regenerated_bundle import GROUPS
    assert len(verification)==sum(map(len,GROUPS.values()))
    assert all(cmd[cmd.index('--workers')+1]==str(min(workers,64)) for cmd in verification)
    assert any(cmd[cmd.index('verify')+1]=='P12' for cmd in verification)


def test_fresh_lexicographic_pair_need_not_start_at_zero(exact_case):
    from born_ladder.instruments import Instrument
    from born_ladder.reproduction.census_writers.certificates import point_search
    context=copy.deepcopy(exact_case[0]);raw=[1]+[0]*31
    context['lens']=dict(zip(L.C.FIELDS,[raw,[0]*32,raw]))
    w=list(map(Q,context['exact']['w']));s=Q(context['exact']['s'])
    model=Instrument(context,w,s,context['exact']['P'],context['kernel'])
    certificate=point_search(A,model)
    assert certificate['pair']==[1,2]
    L.C.extract(context,certificate,registered=False)
    assert L.C.extract(context,certificate)['i']==1
    later=copy.deepcopy(certificate);later['pair']=[2,3]
    with pytest.raises(ValueError,match='earlier eligible point pair'):
        L.C.extract(context,later)
