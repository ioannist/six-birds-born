"""Recovered exact worked-case calculations; public arithmetic backends.

The original null-vector search and joined within-label search keep their
historical operation order and 384-bit outward interval arithmetic.
"""
from fractions import Fraction as Q
from fractions import Fraction as F
import itertools, math
from born_ladder.arithmetic import *
from born_ladder import arithmetic as M
from born_ladder.ensemble import EnsembleInstrument
from born_ladder.instruments import tests

def sqrt_interval(x,bits=384):
    if x<0:raise ValueError('negative source root')
    q=math.isqrt((x.numerator<<(2*bits))//x.denominator);lo=F(q,2**bits)
    return lo,lo if lo*lo==x else F(q+1,2**bits)

def interval_add(x,y):return x[0]+y[0],x[1]+y[1]

def interval_scale(a,x):return (a*x[0],a*x[1]) if a>=0 else (a*x[1],a*x[0])

def divide(x,y):
    if y[0]<=0:raise ValueError('source denominator unresolved')
    z=[a/b for a in x for b in y];return min(z),max(z)

def ray_coordinate_interval(p,w,ss):
    roots=[sqrt_interval(t) for t in p]
    S=(F(0),F(0));T=(F(0),F(0))
    for root,a in zip(roots,w):S=interval_add(S,root);T=interval_add(T,interval_scale(a,root))
    return interval_scale(F(len(w),1)/ss,divide(T,S))

def ser(x):return [str(t) for t in x]

def interval_json(x):return {'lo':str(x[0]),'hi':str(x[1]),'lo_approx':float(x[0]),'hi_approx':float(x[1])}

def induced(x,w,ss,P,K):
    n=len(w);base=[F(1,n)]*n;ops={'K':K,'K2':mm(K,K)};results={}
    # Deterministic algebraic null vectors, no optimizer or sampled preparations.
    for name,A in ops.items():
        basefuture=mv(transpose(A),base);iv0=ray_coordinate_interval(basefuture,w,ss);found=None
        for j in range(2,n):
            d=[F(0)]*n;d[0]=w[1]-w[j];d[1]=w[j]-w[0];d[j]=w[0]-w[1]
            if not any(d):continue
            den=max(map(abs,d));d=[v/den for v in d]
            if sum(d)!=0 or sum(a*b for a,b in zip(d,w))!=0:raise ValueError('source null direction differs')
            a=[1+v/4 for v in d]
            if min(a)<=0 or mv(P,a)!=[F(1)]*n:raise ValueError('source encoder fiber differs')
            prep=prob(a);future=mv(transpose(A),prep);iv=ray_coordinate_interval(future,w,ss)
            if iv[0]>iv0[1] or iv0[0]>iv[1]:
                found={'null_coordinate_indices':[0,1,j],'root_direction':ser(d),'positive_root_before_normalization':ser(a),'p':ser(base),'p_prime':ser(prep),'encoder_equality':'EXACT: projected positive roots are both proportional to ones','ray_coordinate_definition':'beta/alpha for projected root = alpha*ones+beta*centered_mode','successor_p':interval_json(iv0),'successor_p_prime':interval_json(iv),'rational_gap_lower':str(max(iv[0]-iv0[1],iv0[0]-iv[1]))};break
        results[name]={'status':'KILL A: certified encoder-fiber successor split' if found else 'UNRESOLVED','certificate':found}
    out={'operations':results,'domain':'entire32-state simplex; homogeneous encoding of exact stored K coefficient action','sqrt_enclosure_bits':384,'stop':any(v['certificate'] for v in results.values())}
    return out

def joined(t):
    q=t.x['lens']['joint_by_state'];blocks=[[i for i in range(t.n) if q[i]==j] for j in range(max(q)+1)]
    triples=[c for block in blocks for c in itertools.combinations(block,3)];results={};tried=[]
    for num,(i,j,k) in enumerate(triples):
        d=[Q(0)]*t.n;d[i]=t.w[j]-t.w[k];d[j]=t.w[k]-t.w[i];d[k]=t.w[i]-t.w[j]
        if not any(d):continue
        d=[v/max(map(abs,d)) for v in d]
        ap=[1+v/4 for v in d];am=[1-v/4 for v in d];p,pp=prob(ap),prob(am)
        if min(ap)<=0 or min(am)<=0:raise ValueError('joined positive roots differ')
        if mv(t.P,ap)!=mv(t.P,am) or mv(t.P,ap)!=[Q(1)]*t.n:raise ValueError('joined encoder fiber differs')
        if t.ru(p)!=t.ru(pp):raise ValueError('joined passive laws differ')
        row={'triple':list((i,j,k)),'joint_label':q[i],'root_direction':[str(v) for v in d],'p_plus':[str(v) for v in p],'p_minus':[str(v) for v in pp],'Ru':[str(v) for v in t.ru(p)],'exact_encoder_equality':True}
        tried.append({'triple':list((i,j,k)),'equal_joined_state':True})
        for name in ('K','K2'):
            if name in results:continue
            f,fp=t.propagate(p,name),t.propagate(pp,name);l,lp=t.encode(f),t.encode(fp);gap=t.distance(l,lp)
            if gap.lo>0:
                results[name]={'status':'KILL A FOR JOINED STATE','certificate':row,'successor_lambda_plus':l.json(),'successor_lambda_minus':lp.json(),'successor_density_distance':gap.json(),'successor_Ru_plus':[str(v) for v in t.ru(normalize(f))],'successor_Ru_minus':[str(v) for v in t.ru(normalize(fp))],'successor_Ru_difference':[str(a-b) for a,b in zip(t.ru(normalize(f)),t.ru(normalize(fp)))]}
        if len(results)==2:break
    for name in ('K','K2'):
        if name not in results:results[name]={'status':'NO SPLIT FOUND IN DECLARED CLASS; NOT UNIVERSAL PASS'}
    # Exact constraint rank and local full-preparation fiber dimension.
    rows=[[Q(1 if q[i]==j else 0) for i in range(t.n)] for j in range(max(q)+1)]+[t.w]
    rank=rational_rank(rows)
    return ({'operations':results,'declared_triples':len(triples),'tested_directions':tried,'exact_constraint_rank_at_uniform_root':rank,'local_full_preparation_fiber_dimension':t.n-rank,'scope':'same fixed joint R_u, full simplex, symmetric rational-root within-label triple search; K/K² exact source-span semantics','no_interface_repair':True})

def rational_rank(rows):
    a=[list(r) for r in rows];rank=0
    for col in range(len(a[0])):
        pivot=next((j for j in range(rank,len(a)) if a[j][col]),None)
        if pivot is None:continue
        a[rank],a[pivot]=a[pivot],a[rank]
        v=a[rank][col];a[rank]=[x/v for x in a[rank]]
        for j in range(rank+1,len(a)):
            v=a[j][col];a[j]=[x-v*y for x,y in zip(a[j],a[rank])]
        rank+=1
        if rank==len(a):break
    return rank


def density(w,l):
    n=len(w);s=sum(x*x for x in w);v=[Q(1),l];g=[Q(n),s]
    return [[v[i]*v[j]*g[j]/(n+s*l*l) for j in range(2)] for i in range(2)]


def barycenter(w, ensemble):
    return [[sum(weight*density(w,l)[i][j] for l,weight in ensemble) for j in range(2)] for i in range(2)]


def ensembles(w, charts):
    # Equal barycenters: solve the off-diagonal equation, then verify all entries.
    a,b=map(Q,charts[0]);c,d=map(Q,charts[1]);n=len(w);s=sum(x*x for x in w)
    off=lambda l:l/(n+s*l*l)
    weight=-off(b)/(off(a)-off(b))
    other=-off(d)/(off(c)-off(d))
    pairs=[[(a,weight),(b,1-weight)],[(c,other),(d,1-other)]]
    if any(z<=0 for e in pairs for l,z in e):raise ValueError('ensemble weights not positive')
    if barycenter(w,pairs[0])!=barycenter(w,pairs[1]):raise ValueError('ensemble barycenters differ')
    if any(min(1+l*x for x in w)<=0 for e in pairs for l,z in e):raise ValueError('ensemble reachability fails')
    return pairs


def sequential_certificate(t, charts):
    m=EnsembleInstrument(t);pair=ensembles(t.w,charts);checked=[]
    for field in sorted(m.parts):
        for h in (1,2,4,8):
            panels=[]
            for ens in pair:
                size=len(m.parts[field]);joint=[[I(0) for _ in range(size)] for _ in range(size)]
                for l,weight in ens:
                    _,j,_=m.sequential(l,field,h)
                    joint=[[x+weight*y for x,y in zip(row,r)] for row,r in zip(joint,j)]
                panels.append(joint)
            for g in range(len(panels[0])):
                for j in range(len(panels[0])):
                    left,right=panels[0][g][j],panels[1][g][j];diff=left-right
                    row={'context':field,'h':h,'word':['BEGIN('+field+','+str(h)+',retain)','FIRST_READ('+str(g)+')','PROPAGATE','FINAL_READ('+str(j)+')','HALT'],
                         'g':g,'j':j,'left_probability':left.json(),'right_probability':right.json(),'left_minus_right':diff.json(),
                         'status':'CERTIFIED UNEQUAL' if diff.lo>0 or diff.hi<0 else 'NO SEPARATION BY THESE ENCLOSURES'}
                    checked.append(row)
                    if row['status']=='CERTIFIED UNEQUAL':
                        return {'pair_certificate':{'left':qserial(pair[0]),'right':qserial(pair[1]),'coordinate_barycenter':qserial(barycenter(t.w,pair[0])),
                                                    'full_barycenter_original_parity':barycenter(t.w,pair[0])==barycenter(t.w,pair[1]),
                                                    'first_read_all_lenses_equal':all(sum(z*(a+b*l+c*l*l)/(32+t.ss*l*l) for l,z in pair[0])==sum(z*(a+b*l+c*l*l)/(32+t.ss*l*l) for l,z in pair[1]) for a,b,c in m.moments.values())},
                                'checked_words':checked,'witness':row}
    raise ValueError('ensemble sequential separation unresolved')


def finite_certificate(m, pair):
    """Historical test/word/subset enumeration, stripped of process prose.

    Numerical fields preserve the E2 writer's subset-doubling operation order.
    """
    from born_ladder.instruments import tests
    records=[];families=[];words_out=[]
    for number,(cs,words) in enumerate(tests(m)):
        effects=[];total=asinterval(zero());kid=f'test_{number:02d}'
        for gs in words:
            product,effect=m.word(cs,gs);total=M.add(total,effect);effects.append(effect)
            if trace(effect).lo<=0:raise ValueError('registered word positivity unresolved')
            words_out.append({'test_id':kid,'contexts':list(cs),'outcomes':list(gs),
                'M':ijs(product),'effect_G_adjoint_M_times_M':ijs(effect),
                'determinant_effect_exact':str(math.prod(det(m.C[m.parts[f][g]]) for f,g in zip(cs,gs)))})
        if not encloses(total,eye()):raise ValueError('word completeness unresolved')
        families.append({'id':kid,'contexts':list(cs),'words':[list(x) for x in words],
                         'sum_word_effects':ijs(total),'identity_enclosed':True,'subset_count':1<<len(words)})
        subset_effects=[asinterval(zero())]
        for effect in effects:subset_effects += [M.add(X,effect) for X in subset_effects]
        for mask,effect in enumerate(subset_effects):
            selected=[list(words[j]) for j in range(len(words)) if mask&(1<<j)]
            records.append({'id':f'{kid}:subset_{mask:03d}','test_id':kid,'contexts':list(cs),
                            'mask':mask,'public_word_subset':selected,'effect':ijs(effect)})
    if (len(records),len(words_out),len(families))!=(2340,72,12):raise ValueError('registered finite inventory differs')
    bars=[barycenter(m.w,ens) for ens in pair]
    if bars[0]!=bars[1]:raise ValueError('equal-density control failed')
    return {'events':records,'families':families,'atomic_words':words_out,'event_count':len(records),
            'atomic_word_count':len(words_out),'complete_test_count':len(families),
            'equal_barycenter_control_exact':qstrings(bars[0])}


def order_certificate(m):
    """Original raw-one/package-zero two-read probability enclosures."""
    R=m.pure(0);left=m.parts['raw_by_state'][1];right=m.parts['package_by_state'][0]
    E,F=m.C[left],m.C[right]
    forward=matmul(matmul(m.A[left],F),m.A[left])
    reverse=matmul(matmul(m.A[right],E),m.A[right])
    p,q=m.probability(R,forward),m.probability(R,reverse);gap=p-q
    if gap.hi>=0:raise ValueError('order separation unresolved')
    passive=m.C[tuple(sorted(set(left)&set(right)))]
    if passive!=zero():raise ValueError('passive common parent differs')
    comm=sub(matmul(E,F),matmul(F,E))
    orth=I(comm[0][1])*I(m.G[0]/m.G[1]).sqrt()
    return {'left_word':'raw1 then package0','right_word':'package0 then raw1',
            'uniform_ray_frame_density':qstrings(R),'left':p.json(),'right':q.json(),
            'left_minus_right':gap.json(),'passive_common_parent_both_orders_exact':'0',
            'commutator_orthonormal_01':orth.json(),'known_construction_witness_not_empirical_discovery':True}


# Full E2 order diagnostics recovered from certify_D.py; same arithmetic/order.
def order_diagnostics(m):
    keys = m.parentsets
    cache = {}
    unresolved = 0
    for i, S in enumerate(keys):
        for j, Tset in enumerate(keys):
            E, F = (m.C[S], m.C[Tset])
            comm = sub(matmul(E, F), matmul(F, E))
            forward = matmul(matmul(m.A[S], F), m.A[S])
            reverse = matmul(matmul(m.A[Tset], E), m.A[Tset])
            if comm == zero():
                status = 'EXACT EQUAL: commuting positive effects imply commuting roots'
                sep = []
            else:
                sep = separated(forward, reverse)
                status = 'CERTIFIED UNEQUAL' if sep else 'UNRESOLVED'
                unresolved += not bool(sep)
            cache[i, j] = {'left_parent_subset': list(S), 'right_parent_subset': list(Tset), 'commutator_exact': qstrings(comm), 'E_EF': ijs(forward), 'E_FE': ijs(reverse), 'status': status, 'separated_entries': sep, 'maximally_mixed_probability_equal': 'EXACT by cyclic trace tr(EF)/2=tr(FE)/2; not operator equality', 'scope': 'roots of inherited subset effects as algebra controls; actual commands only atomic context outcomes'}
    if not unresolved == 0:
        raise ValueError('uncertified pair classification: stop')
    old = []
    for field, part in m.parts.items():
        for bits in itertools.product((0, 1), repeat=len(part)):
            labels = [g for g, bit in zip(part, bits) if bit]
            old.append({'id': field + ':' + ','.join(map(str, labels)), 'labels': labels, 'parent_subset': sorted((i for g in labels for i in part[g]))})
    pairs = []
    for left, right in itertools.product(old, repeat=2):
        i = keys.index(tuple(left['parent_subset']))
        j = keys.index(tuple(right['parent_subset']))
        pairs.append({'left': left['id'], 'right': right['id'], 'canonical_pair': [i, j], 'status': cache[i, j]['status'], 'registered_measurement_pair': len(left['labels']) == len(right['labels']) == 1, 'other_pairs': 'logical subset-root controls, not added measurement commands'})
    if not (len(pairs) == 400 and sum((x['registered_measurement_pair'] for x in pairs)) == 64):
        raise ValueError('worked-case order certificate invariant failed')
    witness = order_certificate(m)
    R = m.pure(0)
    p = I(Q(witness['left']['lo']), Q(witness['left']['hi']))
    passive_panels = []
    for cs, words in tests(m):
        if len(cs) != 2:
            continue
        vals = []
        rows = []
        for gs in words:
            _, EW = m.word(cs, gs)
            pp = m.probability(R, EW)
            S = tuple(sorted(set(m.parts[cs[0]][gs[0]]) & set(m.parts[cs[1]][gs[1]])))
            null = trace(matmul(R, m.C[S]))
            vals.append((pp - null).abs())
            rows.append({'outcomes': list(gs), 'lueders_probability': pp.json(), 'passive_same_parent_probability_exact': str(null)})
        passive_panels.append({'contexts': list(cs), 'uniform_ray_joint_TV': (M.isum(vals) / 2).json(), 'rows': rows, 'comparison': 'passive nondisturbing same-parent null, not matched-instrument exclusion'})
    rawS = m.parts['raw_by_state'][0]
    fine = [0, 2]
    coarse, b1, s1 = m.branch(R, rawS)
    group, b2, s2 = m.grouped(R, 'package_by_state', fine)
    if not set(rawS) == set(m.parts['package_by_state'][0]) | set(m.parts['package_by_state'][2]):
        raise ValueError('worked-case order certificate invariant failed')
    if not separated(coarse, group):
        raise ValueError('worked-case order certificate invariant failed')
    raw = m.nonselective(R, 'raw_by_state')
    pkg = m.nonselective(R, 'package_by_state')
    joint = m.nonselective(R, 'joint_by_state')
    if not separated(raw, pkg):
        raise ValueError('worked-case order certificate invariant failed')
    if not set(m.parts['package_by_state'].values()) == set(m.parts['joint_by_state'].values()):
        raise ValueError('worked-case order certificate invariant failed')
    coarse_result = {'raw0_equals_pkg0_union_pkg2_parent': True, 'initial_group_mass_equal_exact': str(trace(matmul(R, m.C[rawS]))), 'raw0_branch': ijs(coarse), 'fine_grouped_branch': ijs(group), 'branch_separated_entries': separated(coarse, group), 'raw_nonselective': ijs(raw), 'package_nonselective': ijs(pkg), 'raw_vs_package_separated_entries': separated(raw, pkg), 'package_vs_joint_channel': 'EXACT SAME up to public outcome relabeling; full protocol tags retained', 'second_read_differences': {str(g): (m.probability(raw, m.C[S]) - m.probability(pkg, m.C[S])).json() for g, S in m.parts['package_by_state'].items()}, 'whole_event_effect_unit_is_not_identity_channel': True}
    cap = max((Q(len(S), m.n) for S in m.parentsets if len(S) < m.n))
    complement = 1 - p
    if not (complement.lo > cap and complement.hi < 1):
        raise ValueError('worked-case order certificate invariant failed')
    atom_boundary = {'status': 'ATOMIC WORD + PASSIVE FRAGMENT NOT COMPLEMENT-CLOSED', 'witness_word': witness['left_word'], 'complement_uniform_probability': complement.json(), 'largest_nonunit_passive_or_first_atomic_mass_exact': str(cap), 'proof': 'each atomic two-step effect <= its first atomic effect, so every nonunit passive/atomic-word probability <=29/32 on uniform; the complement is >29/32 and <1', 'coarse_complement': 'already admitted as all other word outcomes in fixed raw/package test, NOT a new sqrt-complement operation'}
    C0 = m.C[m.parts['raw_by_state'][0]]
    C1 = m.C[m.parts['raw_by_state'][1]]
    if not (add(C0, C1) == eye() and matmul(C0, C1) == matmul(C1, C0)):
        raise ValueError('worked-case order certificate invariant failed')
    X = matmul(C0, C1)
    if not (det(X) > 0 and trace(X) > 0):
        raise ValueError('worked-case order certificate invariant failed')
    for gs in ((0, 1), (1, 0)):
        _, EW = m.word(('raw_by_state', 'raw_by_state'), gs)
        if not encloses(EW, X):
            raise ValueError('worked-case order certificate invariant failed')
    quotient = {'status': 'OPERATOR-ONLY EVENT QUOTIENT DOES NOT INHERIT DISJOINT-WORD ADDITION', 'context_sequence': ['raw_by_state', 'raw_by_state'], 'left_event_words': [[0, 1]], 'right_event_words': [[1, 0]], 'common_exact_effect': qstrings(X), 'proof_of_operator_equality': 'complementary C0,C1 commute, their principal roots commute; both ordered word effects = C0 C1', 'common_uniform_mass_exact': str(trace(matmul(R, X))), 'public_event_predicates_equal': False, 'partial_sum_ambiguity': 'using representatives {01},{01} is overlapping/undefined, but {01},{10} is disjoint/defined, although the operator arguments are identical', 'protocol_or_event_tag_required': True, 'stronger_operator_quotient_claim': 'KILLED; no full operator effect algebra asserted', 'state_or_instrument_law_failed': False}
    local = {'status': 'CLOSED TEST-TAGGED SUBSET FRAGMENT WITHIN EACH FIXED COMPLETE TEST', 'complement': 'word-set complement in same test; effect I-E_A from completeness', 'partial_sum': 'disjoint word union in same test, effect E_A+E_B', 'global_operator_quotient': 'not representative-independent as a disjoint-word algebra; see exact collision certificate', 'full_interval_admitted': False, 'algebra_scope': 'Boolean event-set algebra for each test, with a normalized positive operator-valued map; image may be noninjective, so no Boolean operator-image/global effect-algebra claim'}
    return {'status': 'ORDER CONSTRUCTION CERTIFIED; EFFECT-QUOTIENT BOUNDARY STOP', 'canonical_pairs': list(cache.values()), 'context_pairs': pairs, 'canonical_equal_count': sum((x['status'].startswith('EXACT') for x in cache.values())), 'canonical_unequal_count': sum((x['status'] == 'CERTIFIED UNEQUAL' for x in cache.values())), 'unresolved_count': unresolved, 'uniform_witness': witness, 'passive_disturbance': passive_panels, 'coarse_fine_forgetting': coarse_result, 'atomic_fragment_boundary': atom_boundary, 'operator_quotient_boundary': quotient, 'admitted_fragment_scope': local, 'no_contextuality_incompatibility_or_quantum_specificity_inference': True}
