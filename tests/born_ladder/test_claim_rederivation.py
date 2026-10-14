"""Actual re-derivations versus attachments, including false-positive controls."""
import copy
import hashlib
import json
import os
from pathlib import Path
from fractions import Fraction as Q
import pytest
from born_ladder import arithmetic as A
from born_ladder.claims import Evidence, bundle_content_digest, model, census
from born_ladder.claim_checks import embedded_carrier, parent_certificate, non_trace_fragment


def test_rehashed_replacement_bundle_fails_before_roots_or_dispatch(tmp_path):
    # Use an anchor-bound manifest from the original receipt only in the data
    # lane below. A self-consistent new synthetic bundle is also refused.
    p=tmp_path/'data';p.write_text('replacement')
    doc={'schema':'born_claim_bundle_v1','roots':{'local':'missing-root'},
         'files':{'local/data':hashlib.sha256(p.read_bytes()).hexdigest()},'claims':{'B08':{}}}
    bundle=tmp_path/'bundle.json';bundle.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match='trust anchor mismatch'):Evidence(bundle)
    doc['claims']={'P03':{}};bundle.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match='trust anchor mismatch'):Evidence(bundle)


def test_matched_simplex_rederivation_rejects_collapsed_branches():
    from born_ladder.comparator import check_preservation
    from born_ladder.programs import execute
    m=embedded_carrier('lean_born');R=m.pure(0)
    source={'kind':'density','matrix':A.qstrings(R),'protocol':{'public':True}}
    commands=[{'kind':'lens','field':'raw_by_state','mode':'retain'},
              {'kind':'lens','field':'package_by_state','mode':'forget'}]
    assert check_preservation(m,R,source,commands)==6
    def collapsed(*args):
        run=execute(*args);out=A.zero()
        for word,S in run['full_rows']:out=A.add(out,S)
        # The old B02 test still passes: collapse preserves total mass.
        assert A.asI(A.trace(out)).lo<=1<=A.asI(A.trace(out)).hi
        run['full_rows']=[((0,0),out)]
        return run
    with pytest.raises(ValueError,match='labelled branch preservation'):
        check_preservation(m,R,source,commands,runner=collapsed)
    def forgets_retained(*args):
        run=execute(*args)
        from born_ladder.packaging import pack_law
        run['public']=pack_law(run['full_rows'],['forget','forget'],json.loads(run['public'].public_ledger))
        return run
    with pytest.raises(ValueError,match='forgetting preservation'):
        check_preservation(m,R,source,commands,runner=forgets_retained)

    def drops_read_stage(*args):
        run=execute(*args);run['stages']=run['stages'][1:];return run
    with pytest.raises(ValueError,match='read-stage retention'):
        check_preservation(m,R,source,commands,runner=drops_read_stage)


def test_all_parent_and_coarse_effects_uniform_exact_certificate():
    m=embedded_carrier('lean_born')
    assert parent_certificate(m)=={'parents':32,'coarse_atoms':8,'all_three_lenses':True,'uniform_quadratic_coefficient_identity':True}
    S=m.parts['raw_by_state'][0]
    m.C[S][0][0]+=Q(1,1000)
    with pytest.raises(ValueError,match='trace coefficient identity'):parent_certificate(m)


def test_non_trace_fragment_rederives_non_psd_positive_valuation():
    m=embedded_carrier('lean_born')
    basis=[A.eye(),m.C[m.parts['joint_by_state'][0]],m.C[m.parts['joint_by_state'][1]]]
    r=non_trace_fragment(m,basis)
    assert r['events']==2340 and r['proper_groupings_checked']==2316
    assert Q(r['witness_determinant_exact'])<0 and Q(r['minimum_valuation_margin_exact'])>0
    assert Q(r['epsilon_exact'])>0 and Q(r['coordinate_determinant_exact'])!=0
    assert r['generated_H'].startswith('UNRESOLVED')
    broken=copy.deepcopy(basis);broken[1][0][0]+=1
    with pytest.raises(ValueError,match='basis not bound'):non_trace_fragment(m,broken)


@pytest.mark.data
def test_frozen_anchor_rejects_rehashed_historical_replacement(tmp_path):
    doc=json.loads(Path(os.environ['BORN_LADDER_DATA']).read_text())
    expected=bundle_content_digest(doc)
    # Relocating roots alone is permissible; changing the scientific contract
    # is not. Verification of bytes still follows anchoring.
    relocated=copy.deepcopy(doc);relocated['roots']={k:'/missing' for k in doc['roots']}
    assert bundle_content_digest(relocated)==expected
    key=next(iter(doc['files']));doc['files'][key]=hashlib.sha256(b'replacement bytes').hexdigest()
    doc['roots']={k:'/missing' for k in doc['roots']}
    p=tmp_path/'bundle.json';p.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match='trust anchor mismatch'):Evidence(p)
    # A separately rehashed historical-source manifest cannot bypass the
    # governing source pin, even with the correct primary evidence bundle.
    from born_ladder.claims import historical_claim
    (tmp_path/'manifest.json').write_text(json.dumps({'schema':'born_snapshot_historical_inputs_v1','files':{}}))
    with pytest.raises(ValueError,match='source manifest trust anchor mismatch'):
        historical_claim('P12',Evidence(os.environ['BORN_LADDER_DATA']),tmp_path)


@pytest.mark.data
def test_rederive_all_census_pipeline_quantities_exact_access_and_non_trace_argument():
    e=Evidence(os.environ['BORN_LADDER_DATA'])
    from born_ladder.claims import historical_claim
    for identifier in ('P03','B08','B06'):
        message=historical_claim(identifier,e,None)
        assert 'recomputed' in message
    # Altering only the readout attachment cannot fool B08; the fresh exact
    # arithmetic must disagree. No historical bytes are written.
    class Changed:
        path=e.path
        def read(self,key):
            doc=e.read(key)
            if key==e.config('B08')['original']:
                doc[0]['certificates']['strictness']['first_separating_readout']['difference_exact']='1'
            return doc
    with pytest.raises(ValueError,match='recomputed exact access witness differs'):
        census(Changed(),e.config('B08'),'B08')


def test_simplex_public_source_and_zero_failure_contracts():
    from born_ladder.comparator import source_state,check_preservation
    from born_ladder.programs import decode_source
    m=embedded_carrier('lean_born')
    R=m.pure(0);pure={'kind':'density','matrix':A.qstrings(R),'protocol':{'public':True}}
    encoded={'kind':'encoded','p':['1/32']*32,'protocol':{'public':True}}
    mixture={'kind':'mixture','components':[[pure,'1/2'],[encoded,'1/2']],'protocol':{'public':True}}
    command=[{'kind':'binary','effect':A.qstrings(A.zero()),'mode':'retain'}]
    for source in (encoded,mixture):
        assert check_preservation(m,decode_source(m,source),source,command)==1
    for bad in ({'kind':'density','matrix':[['2','0'],['0','-1']],'protocol':{}},
                {'kind':'density','matrix':A.qstrings(R)},
                {'kind':'mixture','components':[[pure,'1/3']],'protocol':{}}):
        with pytest.raises(ValueError,match='INVALID_SOURCE'):source_state(m,bad)


def test_claim_b02_dispatch_itself_rejects_collapsed_branches(monkeypatch):
    from born_ladder import programs
    from born_ladder.__main__ import verify_claim
    original=programs.execute
    def collapsed(*args):
        result=original(*args)
        if result['status']=='HALT' and result['full_rows']:
            S=A.zero()
            for _,state in result['full_rows']:S=A.add(S,state)
            result['full_rows']=[(result['full_rows'][0][0],S)]
        return result
    monkeypatch.setattr(programs,'execute',collapsed)
    with pytest.raises(ValueError,match='labelled branch preservation'):verify_claim('B02')


def test_claim_registry_reports_exact_formal_scope():
    from born_ladder.__main__ import REGISTRY,LEAN_SCOPE
    assert 'embedded RI projector' in LEAN_SCOPE['P01']
    assert 'all-three-lens readouts' in LEAN_SCOPE['P02']
    assert 'retained-space unit riP' in LEAN_SCOPE['P02'] and 'exact 2x2 frame coefficients' in LEAN_SCOPE['P02']
    assert 'pairing bridge are proved' in LEAN_SCOPE['P02']
    assert 'strict interior of proper word groupings' in LEAN_SCOPE['B06']
    assert 'finite/generated fragment' in LEAN_SCOPE['P07']
    assert 'not all unrestricted stochastic' in LEAN_SCOPE['P08']
    assert 'not native reachability' in LEAN_SCOPE['P09']
    assert REGISTRY['P06'][2] and REGISTRY['B02'][2]


def test_independent_comparator_preserves_nondyadic_projector_zero_branch():
    from born_ladder.comparator import check_preservation
    from born_ladder.programs import execute
    m=embedded_carrier('lean_born');E=m.pure(1);R=A.sub(A.eye(),E)
    source={'kind':'density','matrix':A.qstrings(R),'protocol':{}}
    commands=[{'kind':'binary','effect':A.qstrings(E),'mode':'retain'},
              {'kind':'binary','effect':A.qstrings(E),'mode':'forget'}]
    assert check_preservation(m,R,source,commands)==1
    run=execute(m,source,commands)
    assert [word for word,_ in run['full_rows']]==[(0,0)]
    assert len(run['zero_edges'])==2


def test_irrational_projector_root_preserves_exact_zero_support():
    from born_ladder.comparator import check_preservation
    from born_ladder.programs import execute
    m=embedded_carrier('lean_born');P=m.pure(1);R=A.sub(A.eye(),P)
    E=A.scale(P,Q(1,3))
    source={'kind':'density','matrix':A.qstrings(R),'protocol':{}}
    commands=[{'kind':'binary','effect':A.qstrings(E),'mode':'retain'}]*3
    run=execute(m,source,commands)
    assert run['status']=='HALT' and [w for w,_ in run['full_rows']]==[(0,0,0)]
    assert run['full_rows'][0][1]==R and len(run['zero_edges'])==3
    assert check_preservation(m,R,source,commands)==1


def test_uniform_encoded_source_preserves_projector_zero_support():
    from born_ladder.comparator import check_preservation,source_state
    from born_ladder.programs import execute,decode_source
    m=embedded_carrier('lean_born');R=m.pure(0)
    source={'kind':'encoded','p':['1/32']*32,'protocol':{}}
    commands=[{'kind':'binary','effect':A.qstrings(R),'mode':'retain'}]*2
    assert decode_source(m,source)==source_state(m,source)==R
    run=execute(m,source,commands)
    assert run['status']=='HALT' and [w for w,_ in run['full_rows']]==[(1,1)]
    assert len(run['zero_edges'])==2 and check_preservation(m,R,source,commands)==1


def test_program_does_not_certify_unresolved_branch_support(monkeypatch):
    from born_ladder import programs
    m=embedded_carrier('lean_born')
    source={'kind':'density','matrix':A.qstrings(m.pure(0)),'protocol':{}}
    commands=[{'kind':'binary','effect':A.qstrings(A.eye()),'mode':'retain'}]
    # A bound that permits both zero and positive mass cannot justify an
    # emitted positive branch or a selective posterior.
    monkeypatch.setattr(programs,'apply_root',lambda *_:[[A.I(0,1),A.I(0)],[A.I(0),A.I(0)]])
    run=programs.execute(m,source,commands)
    assert run['status']=='HALT_FAILURE' and run['measurements_completed']==0
    assert run['records'][0]=='PUBLIC_FAILURE:UNRESOLVED_NUMERICAL'


@pytest.mark.parametrize('root',[[['-1','0'],['0','-1']],
                                 [['1','0'],['0','-1']]])
def test_independent_root_certificate_rejects_nonprincipal_square_roots(root):
    from born_ladder.independent import verify_root_certificate
    _,cert=A.principal(A.eye())
    assert verify_root_certificate(A.eye(),cert)
    cert['rational_root']=root
    with pytest.raises(AssertionError):verify_root_certificate(A.eye(),cert)


def test_enclosure_checks_entire_matrix_shape():
    assert A.encloses(A.asinterval(A.eye()),A.eye())
    for wrong in ([],[[1,0]],[[],[]],[[1],[0]],[[1,0,0],[0,1,0]]):
        assert not A.encloses(wrong,A.eye())
        assert not A.encloses(A.asinterval(A.eye()),wrong)


def test_zero_root_certificate_rejects_nonzero_nilpotent():
    from born_ladder.independent import verify_root_certificate
    _,cert=A.principal(A.zero())
    assert verify_root_certificate(A.zero(),cert)
    # This squares to zero, but the unique PSD square root is the zero matrix.
    cert['rational_root']=[['0','1'],['0','0']]
    with pytest.raises(AssertionError):verify_root_certificate(A.zero(),cert)


def test_parent_certificate_rejects_unrelated_projector():
    m=embedded_carrier('lean_born')
    # I also retains constants and is idempotent, but it is not the rank-two
    # projector represented by the declared frame or its 2x2 parent effects.
    m.P=[[Q(int(i==j)) for j in range(m.n)] for i in range(m.n)]
    with pytest.raises(ValueError,match='projector not bound'):parent_certificate(m)


def test_sequential_boundary_rejects_signed_ensembles(monkeypatch):
    from born_ladder import claims
    m=embedded_carrier('lean_born')
    monkeypatch.setattr(claims,'model',lambda _:m)
    cert={'pair_certificate':{'left':[['0','2'],['1','-1']],
                              'right':[['0','2'],['1','-1']]},'witness':{}}
    class Inputs:
        def read(self,key):return cert if key=='certificate' else {}
    with pytest.raises(ValueError,match='nonnegative probability ensembles'):
        claims.sequential_boundary(Inputs(),{'context':'context','certificate':'certificate'})


def test_no_lift_checker_requires_full_simplex_dimension(monkeypatch):
    from born_ladder import claims
    m=embedded_carrier('lean_born')
    monkeypatch.setattr(claims,'model',lambda _:m)
    cert={'operations':{'K':{'certificate':{'p':['1'],'p_prime':['1']}}}}
    class Inputs:
        def read(self,key):return cert if key=='certificate' else {}
    with pytest.raises(ValueError,match='encoder-fiber equality'):
        claims.no_lift(Inputs(),{'context':'context','amplitude_certificate':'certificate',
                                'joined_certificate':'certificate'})


def test_radical_root_certificate_rejects_negative_upper_denominator():
    from born_ladder.independent import verify_root_certificate
    E=[[Q(1,3),Q(0)],[Q(0),Q(2,3)]]
    _,cert=A.principal(E)
    assert verify_root_certificate(E,cert)
    # Squaring a negative endpoint can satisfy an upper square bound while
    # failing to enclose the positive denominator at all.
    cert['denominator']['hi']='-10'
    with pytest.raises(AssertionError):verify_root_certificate(E,cert)


def test_root_certificate_checks_survive_optimized_python():
    import subprocess
    import sys
    code='''
from fractions import Fraction as Q
from born_ladder import arithmetic as A
from born_ladder.independent import verify_root_certificate
bad=[]
for E in (A.eye(),A.zero(),[[Q(1,3),Q(0)],[Q(0),Q(2,3)]]):
    _,cert=A.principal(E)
    if not verify_root_certificate(E,cert):raise RuntimeError('valid certificate refused')
    if E==A.eye():cert['rational_root']=[['-1','0'],['0','-1']]
    elif E==A.zero():cert['rational_root']=[['0','1'],['0','0']]
    else:cert['denominator']['hi']='-10'
    bad.append((E,cert))
for E,cert in bad:
    try:verify_root_certificate(E,cert)
    except AssertionError:pass
    else:raise RuntimeError('false certificate accepted with optimization')
'''
    subprocess.run([sys.executable,'-O','-c',code],check=True,capture_output=True,text=True)

@pytest.mark.parametrize('projector',[False,True])
def test_b10_rejects_false_singleton_or_nonprojector_description(monkeypatch,projector):
    from born_ladder.claims import census
    import born_ladder.independent as independent
    from born_ladder.instruments import FIELDS
    if projector:
        w=[Q(31)]+[Q(-1)]*31;q=[0]+[1]*31;s=Q(992)
        message='zero or a projector'
    else:
        w=[Q(-1)]*16+[Q(1)]*16;q=[0]*16+[1]*16;s=Q(32)
        message='not a singleton'
    context={'lens':{f:q for f in FIELDS}}
    report={'zero_atoms':1,'atoms':[('raw_by_state',0,'0')],'w':list(map(str,w)),'s':str(s)}
    monkeypatch.setattr(independent,'recompute',lambda _:report)
    original=[{'unit_id':str(i),'overall_status':'PASS' if i<100 else 'FAILED'} for i in range(120)]
    completed=[{'unit_id':str(i),'overall_registered_claim_status':'PASS'} for i in range(120)]
    class Inputs:
        def read(self,name):return original if name=='original' else completed if name=='completed' else context
    with pytest.raises(ValueError,match=message):
        census(Inputs(),{'original':'original','completed':'completed','contexts':'contexts'},'B10')
