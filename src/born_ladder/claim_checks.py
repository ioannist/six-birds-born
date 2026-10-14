"""Re-derivations for public claim adapters; no fits or historical writes."""
from fractions import Fraction as Q
from pathlib import Path
import re
import numpy as np
from . import arithmetic as A


def embedded_carrier(lean_root):
    """Read already-public exact RI constants, not private evidence or floats."""
    from .instruments import Instrument
    text=(Path(lean_root)/'BornCalculus/RIInputs.lean').read_text()
    wtext=text.split('def riWQ',1)[1].split('def riSQ',1)[0]
    w=[Q(int(a),int(b)) for a,b in re.findall(r'\((-?\d+) : ℚ\) / (\d+)',wtext)]
    if len(w)!=32 or sum(w)!=0:raise ValueError('embedded centered frame mismatch')
    s=sum(x*x for x in w)
    a,b=re.search(r'def riSQ[^\n]*?\((\d+) : ℚ\) / (\d+)',text).groups()
    if s!=Q(int(a),int(b)) or s<=0:raise ValueError('embedded frame norm mismatch')
    lens={}
    for name,field in [('riRaw','raw_by_state'),('riPackage','package_by_state'),('riJoint','joint_by_state')]:
        items=re.search(r'def '+name+r'[^!]*!\[([^]]+)\]',text).group(1)
        lens[field]=list(map(int,items.split(',')))
        if len(lens[field])!=32:raise ValueError('embedded lens shape')
    P=[[Q(1,32)+a*b/s for b in w] for a in w]
    return Instrument({'identity':{'source':'public embedded RI analytic apparatus'},'lens':lens},w,s,P,
                      [[Q(int(i==j)) for j in range(32)] for i in range(32)])


def parent_certificate(m):
    """Uniform quadratic-form identity, with exact coefficient comparison.

    G E_S = Σ_i∈S (1,w_i)(1,w_i)^T. Each summand is PSD
    for EVERY real vector. Σ_s GE_s=G, hence parent normalization.
    Thus every coarse partition has positive effects summing to I. Its
    quadratic polynomial equals Σ_i∈S (a+b w_i)^2 for every (a,b).
    Nonvanishing of P sqrt(p) for every simplex p follows from P1=1:
    its sum is Σ sqrt(p_i)>0; normalization and gauge independence follow.
    """
    n=m.n
    if sum(m.w)!=0 or m.s<=0:raise ValueError('carrier frame not centered rank two')
    expected=[[Q(1,n)+a*b/m.s for b in m.w] for a in m.w]
    if m.P!=expected:raise ValueError('projector not bound to the declared rank-two frame')
    if any(sum(row)!=1 for row in m.P):raise ValueError('constant not retained')
    if any(sum(m.P[i][k]*m.P[k][j] for k in range(n))!=m.P[i][j]
           for i in range(n) for j in range(n)):raise ValueError('projector not idempotent')
    parents=[[[Q(1,n),w/n],[w/m.s,w*w/m.s]] for w in m.w]
    if [[sum(F[i][j] for F in parents) for j in range(2)] for i in range(2)]!=A.eye():
        raise ValueError('parent POVM normalization')
    count=0
    for parts in m.parts.values():
        for S in parts.values():
            H=[[Q(len(S)),sum(m.w[i] for i in S)],
               [sum(m.w[i] for i in S),sum(m.w[i]**2 for i in S)]]
            if A.det(H)<0 or [[m.G[i]*m.C[S][i][j] for j in range(2)] for i in range(2)]!=H:
                raise ValueError('coarse positivity/trace coefficient identity')
            count+=1
        if [[sum(m.C[S][i][j] for S in parts.values()) for j in range(2)] for i in range(2)]!=A.eye():
            raise ValueError('coarse normalization')
    return {'parents':n,'coarse_atoms':count,'all_three_lenses':True,
            'uniform_quadratic_coefficient_identity':True}


def structure_checks(m, claim):
    """Executable controls of the uniform constructor/comparator arguments."""
    from itertools import product
    from .instruments import tests, FIELDS
    from .programs import execute
    from .packaging import pack_law, pack_event, visible
    from .comparator import check_preservation, simplex, forget, close
    programs=[[{'kind':'lens','field':f,'mode':'retain'} for f in fs] for fs,_ in tests(m)]
    # Full-interval zero branches, mixed binary/lens words, and >2-command
    # composition controls; this does not limit the uniform induction domain.
    programs += [[{'kind':'binary','effect':A.qstrings(E),'mode':'retain'},
                  {'kind':'lens','field':FIELDS[0],'mode':'forget'},
                  {'kind':'lens','field':FIELDS[1],'mode':'retain'}]
                 for E in (A.zero(),A.eye(),[[Q(1,3),Q(0)],[Q(0),Q(2,3)]])]
    checked=events=0
    for R in (m.pure(0),[[Q(1,2),Q(0)],[Q(0),Q(1,2)]]):
        source={'kind':'density','matrix':A.qstrings(R),'protocol':{'public':'retained'}}
        for commands in programs:
            checked+=check_preservation(m,R,source,commands)
            rows=simplex(m,R,commands)
            # All forgetting policies, with production pack_law checked against
            # an independent projection and unnormalized summation.
            for modes in product(('retain','forget'),repeat=len(commands)):
                ds=[{**c,'mode':mode} for c,mode in zip(commands,modes)]
                run=execute(m,source,ds);expected=forget(rows,modes)
                if set(dict(run['public'].cells))!=set(expected):raise ValueError('forgetting lost outcomes')
                for key,S in run['public'].cells:close(S,expected[key])
                if pack_law(run['public'])!=run['public']:raise ValueError('package idempotence failure')
            if claim=='P06' and len(commands)<=2:
                words=tuple(rows)
                for mask in range(1<<len(words)):
                    chosen=[w for i,w in enumerate(words) if mask&(1<<i)]
                    p=pack_event(str(commands),words,chosen,['retain']*len(commands),source)
                    if pack_event(p)!=p:raise ValueError('event idempotence failure')
                    for modes in product(('retain','forget'),repeat=len(commands)):
                        if not visible(words,chosen,modes):
                            try:pack_event(str(commands),words,chosen,modes,source)
                            except ValueError:pass
                            else:raise ValueError('hidden event accepted')
                    events+=1
        for bad in ('K','F','autonomous','if'):
            if execute(m,source,[{'kind':bad,'mode':'retain'}])['status']!='HALT_FAILURE':
                raise ValueError('public failure outcome missing')
    if claim=='P06':
        raw=pack_event('raw',[()], [()],[],{'command':'raw'})
        pkg=pack_event('pkg',[()], [()],[],{'command':'pkg'})
        if raw==pkg:raise ValueError('distinct instrument protocol record erased')
    return f'recomputed {checked} labelled branch/state comparisons, selective composition, all forgetting policies'+(
        f', {events} local event packaging/idempotence controls' if claim=='P06' else '')+'; uniform finite-program preservation is mechanized separately in Lean Comparator; no finite-state cap'


def pipeline(context, formula_path):
    """Recompute ALL registered correspondence gate quantities on own inputs.

    Same arithmetic/order/enclosures as the reviewed constructor; no scores,
    archived conclusions or row normalization used. Floating error premises
    are explicit conditional accounting, not a platform accuracy theorem.
    """
    from .certificates import FormulaView, diffs, native_step
    from .snapshot.g2a import _oriented_basis
    from .snapshot.universal_shapes import _formula_contract, _recomputed_laws
    born=context['born'];arch=context['archived_unit_structural']['raw']['basis_and_projector_inputs']
    v=list(map(Q,born['sym_eigvec_basis'][0]));w=[x-sum(v)/32 for x in v];s=sum(x*x for x in w)
    P=[[Q(1,32)+a*b/s for b in w] for a in w]
    diff=diffs(_oriented_basis(born),arch)
    p=[0.]*32
    for i in born['starts']:p[i]+=1./len(born['starts'])
    for _ in range(born['tau']):p=native_step(context['kernel'],p)
    native=max(abs(Q(a)-Q(b)) for a,b in zip(p,born['p_theory']))
    record={k:context['archived_unit_structural']['raw'][k] for k in ('unrounded_p_full','basis_and_projector_inputs','spectral_coefficients')}
    laws,_,_=_recomputed_laws(record,_formula_contract(FormulaView(formula_path)));q=laws['q_full']
    tilde=[[Q(x) for x in row] for row in arch['projector']]
    d2=sum((a-b)**2 for row,rr in zip(P,tilde) for a,b in zip(row,rr));du=A.I(d2).sqrt()
    uniform=32*du.hi*(2+du.hi)
    root=[A.I(Q(x)).sqrt() for x in born['p_theory']]
    def probs(M):
        amp=[sum((a*b for a,b in zip(row,root)),A.I(0)) for row in M]
        mass=sum((a.square() for a in amp),A.I(0))
        if mass.lo<=0:raise ValueError('nonvanishing unproved')
        return [a.square()/mass for a in amp]
    exact,rounded=probs(P),probs(tilde)
    source_err=max((a-Q(b)).abs().hi for a,b in zip(exact,q))
    floaterr=max((a-Q(b)).abs().hi for a,b in zip(rounded,q))
    amp=np.array(arch['projector'])@np.sqrt(np.array(born['p_theory']));direct=amp*amp/np.dot(amp,amp)
    parity=max(abs(Q(float(a))-Q(b)) for a,b in zip(direct,q))
    u=Q(1,2**53);eta=Q(1,2**1074);gamma=lambda n:n*u/(1-n*u)
    norm=A.I(sum(a*a for row in tilde for a in row)).sqrt().hi
    eps=(1+du.hi)*u+gamma(66)*norm*(1+u)+4096*eta
    normlo=A.I(Q(1,32)).sqrt().lo-du.hi
    envelope=eps*(2*(1+du.hi)+eps)/normlo**2+gamma(38)+2048*eta/normlo**2 if normlo>0 else None
    return {'delta_squared_exact':str(d2),'constructor_categorical_shape_parity':not any(t.get('categorical_or_shape_mismatch') for t in diff),
            'native_preparation_replay_maximum_error_exact':str(native),'rounded_nonvanishing':normlo>0,
            'uniform_projector_TV_bound_exact':str(uniform),
            'own_input_exact_source_vs_landed_maximum_error':str(source_err),
            'own_input_rounded_evaluation_error':str(floaterr),
            'native_numpy_vs_landed_fsum_maximum_error':str(parity),
            'uniform_floating_envelope':{'dot_root_norm_error':str(eps),'floating_TV_error_exact':str(envelope),
                'total_with_projector_TV_exact':str(uniform+envelope) if envelope is not None else None},
            'constructor_literal_bit_equality':not diff}


def non_trace_fragment(m, basis):
    """Construct an ACTUAL non-density valuation of the registered fragment.

    All nontrivial inherited atoms here are strictly positive; their principal
    roots are invertible. Every word effect is therefore strictly positive,
    and every proper nonempty grouping has both E>0 and I-E>0. This finite
    strict interior permits R=diag(1+eps,-eps), trace one but not PSD.
    Choose eps>0 by certified bounds so tr(RE)>0 for EVERY proper grouping.
    Additivity/complements are linear identities, not sampled checks.
    Informational completeness of the three basis effects rules out ANY
    density with the same valuation (not just the displayed R).
    No extension to the generated infinite H or full interval is asserted.
    """
    from .instruments import tests
    if any(A.det(m.C[S])<=0 for part in m.parts.values() for S in part.values()):
        raise ValueError('strict-interior finite-fragment witness premise missing')
    known=[A.eye(),m.C[m.parts['joint_by_state'][0]],m.C[m.parts['joint_by_state'][1]]]
    if known!=[[[Q(x) for x in row] for row in E] for E in basis]:raise ValueError('fragment basis not bound to apparatus')
    coords=[[E[0][0],E[1][1],E[0][1]] for E in known];a,b,c=coords
    det=a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])
    if not det:raise ValueError('non-trace distinction not informationally complete')
    effects=[];events=0
    for fs,words in tests(m):
        atoms=[m.word(fs,word)[1] for word in words]
        events+=1<<len(atoms)
        for mask in range(1,(1<<len(atoms))-1):
            E=A.zero()
            for i,e in enumerate(atoms):
                if mask&(1<<i):E=A.add(E,e)
            a,b=A.asI(E[0][0]),A.asI(E[1][1])
            margin=min(a.lo,1-a.hi)
            if margin<=0:raise ValueError('finite-fragment interior bound unresolved')
            effects.append((a,b,margin))
    if events!=2340:raise ValueError('registered finite-fragment inventory differs')
    eps=min(margin/(2*(a-b).abs().hi+2) for a,b,margin in effects)
    if eps<=0:raise ValueError('non-trace witness not outside density cone')
    minimum=Q(1)
    for a,b,_ in effects:
        value=(1+eps)*a-eps*b
        if not 0<value.lo<=value.hi<1:raise ValueError('non-trace valuation not positive')
        minimum=min(minimum,value.lo,1-value.hi)
    return {'events':events,'proper_groupings_checked':len(effects),'epsilon_exact':str(eps),
            'trace_one_witness':['1+'+str(eps),'-'+str(eps)],'witness_determinant_exact':str(-eps*(1+eps)),
            'minimum_valuation_margin_exact':str(minimum),'coordinate_determinant_exact':str(det),
            'non_trace_proof':'positive on every registered grouping; trace-linear normalized/additive; injective basis forces unique non-PSD representing matrix',
            'generated_H':'UNRESOLVED; no extension claimed'}
