"""Separate simplex interpreter for the adopted density instrument.

Uniform preservation argument: for a fixed public initial density R, a node
is (command prefix, labelled prefix, M). Its substochastic weight is
tr(M R M†), and its posterior is M R M† / weight when positive. An edge
appends A on the LEFT of M. Thus by induction its weight and posterior are
those of the instrument's successive congruences, for every finite fixed
program, every admitted density, and every admitted Kraus list. Complete
Kraus lists make outgoing weights sum to the incoming weight. Grouping
nodes by the declared visibility projection sums unnormalized states, never
normalized posteriors. Concatenation multiplies suffix and prefix products.
Invalid descriptors terminate publicly; zero nodes have no posterior.
This is an access-matched representation, without a finite-state cap.

The executable checks use independent product construction and independent
matrix loops/projections, NOT programs.execute, apply_root, pack_law or
word_effects. Only fixed apparatus coefficients and certified root enclosures
are shared; branch updates and source decoding are separately implemented.
The uniform product/trace bridge is mechanized in BornCalculus/Comparator.lean;
the Python descriptor and ledger implementation remains checked by controls.
Overlap alone is not the uniform proof. Enclosure widths are also
bounded above; excessively loose numerical comparisons fail closed.
"""
from fractions import Fraction as Q
import json
import math
from .arithmetic import I, asI
from .instruments import FIELDS


def multiply(a, b):
    return [[sum((a[i][k]*b[k][j] for k in range(2)), Q(0))
             for j in range(2)] for i in range(2)]


def add(a, b):
    return [[a[i][j]+b[i][j] for j in range(2)] for i in range(2)]


def adjoint(m, G):
    return [[G[j]*m[j][i]/G[i] for j in range(2)] for i in range(2)]


def trace(m):
    return m[0][0]+m[1][1]


def close(a, b):
    for i in range(2):
        for j in range(2):
            x, y = asI(a[i][j]), asI(b[i][j])
            if x.hi < y.lo or y.hi < x.lo or max(x.hi-x.lo, y.hi-y.lo) > Q(1,10**70):
                raise ValueError('simplex branch/state preservation failure')


def apparatus(base, command):
    # Independent descriptor dispatch; roots are fixed apparatus coefficients.
    if command.get('mode') not in ('retain', 'forget'):
        raise ValueError('INVALID_PROGRAM')
    if command.get('kind') == 'lens' and set(command) == {'kind','field','mode'}:
        field=command['field']
        if field not in FIELDS:raise ValueError('INVALID_PROGRAM')
        return [(g,base.A[S],base.C[S]) for g,S in base.parts[field].items()]
    if command.get('kind') == 'binary' and set(command) == {'kind','effect','mode'}:
        from .binary import Binary
        effects, roots, _ = Binary(base).roots(command['effect'])
        return [(label,A,effects[label]) for label,A in enumerate(roots)]
    raise ValueError('INVALID_PROGRAM')


def simplex(base, R, commands):
    def point_matrix(S):
        if all(asI(x).lo==asI(x).hi for row in S for x in row):
            return [[asI(x).lo for x in row] for row in S]
        return None
    products={():[[Q(1),Q(0)],[Q(0),Q(1)]]}
    rational_states={():point_matrix(R)}
    for command in commands:
        roots=apparatus(base,command)
        # Degenerate enclosures ARE exact coefficients. Keep them rational so
        # a non-dyadic projector's impossible branch cancels to exactly zero.
        # This decode is local to the independent interpreter.
        roots=[(label,point_matrix(A) if point_matrix(A) is not None else A,C)
               for label,A,C in roots]
        # A separate exact-state certificate supplements the product boxes.
        # It uses local loops and the public effect coefficients, never the
        # production update helper or an observed interpreter state.
        next_states={}
        for word in products:
            S=rational_states[word]
            for label,A,C in roots:
                out=None
                if S is not None:
                    left=multiply(C,S)
                    if left==multiply(S,C):out=left
                    elif point_matrix(A) is not None:
                        out=multiply(multiply(A,S),adjoint(A,base.G))
                next_states[word+(label,)]=out
        products={word+(label,):multiply(A,M) for word,M in products.items() for label,A,C in roots}
        rational_states=next_states
    rows={}
    for word,M in products.items():
        S=multiply(multiply(M,R),adjoint(M,base.G))
        exact=rational_states[word]
        if exact is not None:
            close(S,exact)
            S=exact
        mass=asI(trace(S))
        if mass.lo==mass.hi==0:continue
        if mass.lo<=0:raise ValueError('unresolved simplex positive posterior')
        rows[word]=S
    return rows


def forget(rows, modes):
    result={}
    for word,S in rows.items():
        key=tuple(g if mode=='retain' else 'FORGOTTEN' for g,mode in zip(word,modes))
        result[key]=add(result[key],S) if key in result else S
    return result


def check_preservation(base, R, source, commands, *, runner=None):
    from . import programs
    runner=programs.execute if runner is None else runner
    actual=runner(base,source,commands)
    if actual['status']!='HALT':raise ValueError('instrument unexpectedly failed')
    independently_decoded=source_state(base,source)
    close(independently_decoded,R)
    expected=simplex(base,independently_decoded,commands)
    observed=dict(actual['full_rows'])
    if len(observed)!=len(actual['full_rows']) or set(expected)!=set(observed):
        raise ValueError('simplex labelled branch preservation failure')
    for word,S in expected.items():
        close(S,observed[word])
        mass=asI(trace(S));other=asI(trace(observed[word]))
        close([[mass,0],[0,0]],[[other,0],[0,0]])
        close([[x/mass for x in row] for row in S],
              [[x/other for x in row] for row in observed[word]])
    modes=[c['mode'] for c in commands]
    projected=forget(expected,modes);public=dict(actual['public'].cells)
    if set(projected)!=set(public):raise ValueError('simplex forgetting preservation failure')
    for key,S in projected.items():close(S,public[key])
    ledger={'public_source':source,'original_program':commands,'stage':len(commands),'status':'HALT',
            'timing':'release after each completed command; no autonomous dynamics',
            'source_precision':'exact descriptors, certified inherited root enclosures'}
    if json.loads(actual['public'].public_ledger)!=ledger:
        raise ValueError('simplex public protocol preservation failure')
    if len(actual['stages'])!=len(commands):raise ValueError('simplex read-stage retention failure')
    for j,stage in enumerate(actual['stages'],1):
        prefix=simplex(base,independently_decoded,commands[:j])
        projected_prefix=forget(prefix,modes[:j]);cells=dict(stage.cells)
        if set(cells)!=set(projected_prefix):raise ValueError('simplex read-stage law preservation failure')
        for key,S in projected_prefix.items():close(S,cells[key])
        stage_ledger={**ledger,'stage':j,'status':'HALT' if j==len(commands) else 'READ'}
        if json.loads(stage.public_ledger)!=stage_ledger:
            raise ValueError('simplex read-stage protocol preservation failure')
    # Independent suffix continuation: all prefix/suffix splits, including
    # selective posterior continuation. This checks composition, not just mass.
    for split in range(1,len(commands)):
        prefix=simplex(base,R,commands[:split])
        for pre,S in prefix.items():
            mass=trace(S);posterior=[[x/mass for x in row] for row in S]
            suffix=simplex(base,posterior,commands[split:])
            for post,T in suffix.items():
                close([[mass*x for x in row] for row in T],expected[pre+post])
    return len(expected)


def source_state(base, descriptor):
    """Separate initial-source interpreter (including public mixtures/encoder).

    Root enclosures implement the adopted apparatus precision contract. This
    never reads an evolving preparation, private realization or recipe label.
    """
    if not isinstance(descriptor,dict) or 'protocol' not in descriptor:
        raise ValueError('INVALID_SOURCE')
    json.dumps(descriptor,sort_keys=True)
    kind=descriptor.get('kind')
    if kind=='density' and set(descriptor)=={'kind','matrix','protocol'}:
        R=descriptor['matrix']
        if len(R)!=2 or any(len(row)!=2 for row in R):raise ValueError('INVALID_SOURCE')
        if any(isinstance(x,(float,bool)) for row in R for x in row):raise ValueError('INVALID_SOURCE')
        R=[[Q(x) for x in row] for row in R]
        H=[[base.G[i]*R[i][j] for j in range(2)] for i in range(2)]
        if H[0][1]!=H[1][0] or trace(R)!=1 or H[0][0]<0 or H[1][1]<0 or H[0][0]*H[1][1]-H[0][1]**2<0:
            raise ValueError('INVALID_SOURCE')
        return R
    if kind=='encoded' and set(descriptor)=={'kind','p','protocol'}:
        if len(descriptor['p'])!=base.n or any(isinstance(x,(float,bool)) for x in descriptor['p']):raise ValueError('INVALID_SOURCE')
        p=list(map(Q,descriptor['p']))
        if min(p)<0 or sum(p)!=1:raise ValueError('INVALID_SOURCE')
        pivot=next(x for x in p if x>0)
        rational=[]
        for x in p:
            z=x/pivot;u,v=math.isqrt(z.numerator),math.isqrt(z.denominator)
            if u*u!=z.numerator or v*v!=z.denominator:break
            rational.append(Q(u,v))
        if len(rational)==base.n:
            a=sum(rational)/base.n
            b=sum(w*x for w,x in zip(base.w,rational))/base.s
            den=base.n*a*a+base.s*b*b
            return [[base.n*a*a/den,base.s*a*b/den],
                    [base.n*a*b/den,base.s*b*b/den]]
        roots=[I(x).sqrt() for x in p];a=sum(roots,I(0))/base.n
        b=sum((x*y for x,y in zip(base.w,roots)),I(0))/base.s
        den=base.n*a.square()+base.s*b.square()
        if den.lo<=0:raise ValueError('INVALID_SOURCE')
        return [[base.n*a.square()/den,base.s*a*b/den],
                [base.n*a*b/den,base.s*b.square()/den]]
    if kind=='mixture' and set(descriptor)=={'kind','components','protocol'}:
        total=[[Q(0),Q(0)],[Q(0),Q(0)]];weights=[]
        for d,weight in descriptor['components']:
            if isinstance(weight,(float,bool)):raise ValueError('INVALID_SOURCE')
            weight=Q(weight)
            if weight<0:raise ValueError('INVALID_SOURCE')
            R=source_state(base,d);weights.append(weight)
            total=add(total,[[weight*x for x in row] for row in R])
        if not weights or sum(weights)!=1:raise ValueError('INVALID_SOURCE')
        return total
    raise ValueError('INVALID_SOURCE')
