"""Constant-first rational GS with certified cutoff, basis and probabilities.

Certificates disclose exact directions, norms, masks and rational enclosures.
Only interval-exhaustion is unresolved; malformed input is an input error.
"""
from fractions import Fraction as Q
from math import fsum, isfinite
from .exact import Interval, Unresolved, rational, square_root, round_cell
from .specification import digest


def dot(a,b): return sum((x*y for x,y in zip(a,b,strict=True)),Q(0))


def cutoff_decision(d, columns, bits=4096):
    """Exact comparison d > max(n,m+1)^2 2^-104 lambda_max.

    A^T A and H=AA^T share all nonzero eigenvalues. A's first column is
    1/sqrt(n); avoid that radical by constructing H over Q only when trace
    bounds do not decide. Its characteristic polynomial and real-root
    isolation decide equality, rather than a numerical epsilon.
    """
    n=len(columns[0]); m=len(columns)-1
    factor=Q(max(n,m+1)**2,1<<104)
    trace=Q(1)+sum((dot(c,c) for c in columns[1:]),Q(0))
    if d > factor*trace:
        return True, {'method':'trace upper','lambda_interval':[str(trace/n),str(trace)]}
    if d < factor*trace/n or d == 0:
        return False, {'method':'trace lower','lambda_interval':[str(trace/n),str(trace)]}
    import sympy as sp
    h=sp.Matrix(n,n,lambda i,j: sp.Rational(1,n)+sum(
        sp.Rational(c[i].numerator,c[i].denominator)*sp.Rational(c[j].numerator,c[j].denominator)
        for c in columns[1:]))
    poly=h.charpoly().as_poly(); target=d/factor
    intervals=poly.intervals(eps=sp.Rational(1,1<<bits))
    (left,right),multiplicity=intervals[-1]
    left,right=Q(left),Q(right)
    proof={'method':'characteristic polynomial isolation','polynomial':[str(c) for c in poly.all_coeffs()],
           'lambda_interval':[str(left),str(right)],'largest_root_multiplicity':multiplicity,
           'comparison_target':str(target)}
    if target > right: return True,proof
    if target < left: return False,proof
    if poly.eval(sp.Rational(target.numerator,target.denominator)) == 0:
        # interval contains only the largest distinct root; target is that root.
        proof['equality']=True
        return False,proof
    raise Unresolved('algebraic cutoff comparison exceeded registered refinement')


def ordered_directions(emitted, cutoff_bits=4096):
    if not emitted or not emitted[0]: raise ValueError('emitted vectors are empty')
    n=len(emitted[0]); columns=[[rational(x) for x in row] for row in emitted]
    if any(len(row)!=n for row in columns): raise ValueError('ragged emitted vectors')
    columns=[[Q(1)]*n,*columns]
    directions=[columns[0]]; norms=[Q(n)]; decisions=[]
    for index,u in enumerate(columns[1:]):
        v=u[:]
        for old,d in zip(directions,norms,strict=True):
            coefficient=dot(old,u)/d
            v=[x-coefficient*y for x,y in zip(v,old,strict=True)]
        d=dot(v,v); keep,proof=cutoff_decision(d,columns,cutoff_bits)
        decisions.append({'source_column':index,'direction':[str(x) for x in v],
                          'norm_squared':str(d),'keep':keep,'cutoff':proof})
        if keep: directions.append(v); norms.append(d)
    return directions,norms,decisions


def algebraic_equal(value, target):
    import sympy as sp
    return sp.simplify(value-sp.Rational(target.numerator,target.denominator)) == 0


def projector(directions,norms):
    n=len(directions[0])
    return [[sum((v[i]*v[j]/d for v,d in zip(directions,norms,strict=True)),Q(0))
             for j in range(n)] for i in range(n)]


def laws(directions,norms,p,bits):
    roots=[square_root(x,bits) for x in p]
    dots=[sum((v[i]*roots[i] for i in range(len(p))),Interval(0)) for v in directions]
    norm=sum((z.square()/d for z,d in zip(dots,norms,strict=True)),Interval(0))
    if norm.lo<=0: raise Unresolved('projected amplitude norm not positive')
    diagonal=[sum((Q(v[i]**2,d)*z.square()/d for v,d,z in zip(directions,norms,dots,strict=True)),Interval(0))/norm
              for i in range(len(p))]
    P=projector(directions,norms)
    full=[sum((P[i][j]*roots[j] for j in range(len(p))),Interval(0)).square()/norm for i in range(len(p))]
    return diagonal,full,norm


def exact_probability(directions,norms,p,index,full=False):
    import sympy as sp
    r=lambda q:sp.Rational(q.numerator,q.denominator)
    roots=[sp.sqrt(r(x)) for x in p]
    dots=[sum(r(v[i])*roots[i] for i in range(len(p))) for v in directions]
    norm=sum(z*z/r(d) for z,d in zip(dots,norms,strict=True))
    if full:
        amplitude=sum(r(v[index])*z/r(d) for v,d,z in zip(directions,norms,dots,strict=True))
        return amplitude**2/norm
    return sum(r(v[index]**2)*z*z/r(d*d) for v,d,z in zip(directions,norms,dots,strict=True))/norm


def construct(emitted, preparation, *, refinement=(384,768,1536,3072,4096)):
    p=[rational(x) for x in preparation]
    if not p or any(x<0 for x in p) or sum(p)==0: raise ValueError('invalid preparation')
    if abs(sum(p)-1)>Q(1,10**10): raise ValueError('preparation mass fails inherited tolerance')
    request={'emitted':emitted,'preparation':preparation}
    cert={'schema':'born_v25_canonical_certificate_v1','input_sha256':digest(request)}
    try:
        if not refinement: raise Unresolved('no registered refinement available')
        vectors,norms,decisions=ordered_directions(emitted,max(refinement))
        if len(vectors[0])!=len(p): raise ValueError('preparation dimensions differ')
        cert.update(directions=[[str(x) for x in row] for row in vectors],
                    norms=[str(d) for d in norms],decisions=decisions,rank=len(vectors),
                    exact_projector=[[str(x) for x in row] for row in projector(vectors,norms)])
        import sympy as sp
        for bits in refinement:
            try:
                basis=[]; basis_cells=[]
                for v,d in zip(vectors,norms,strict=True):
                    root=square_root(d,bits); row=[]; cells=[]
                    for x in v:
                        interval=Interval(x)/root
                        value,cell=round_cell(interval,lambda t,x=x,d=d: algebraic_equal(
                            sp.Rational(x.numerator,x.denominator)/sp.sqrt(sp.Rational(d.numerator,d.denominator)),t))
                        row.append(value); cells.append(cell)
                    basis.append(row); basis_cells.append(cells)
                diagonal,full,norm=laws(vectors,norms,p,bits)
                rounded=[]; probability_cells=[]
                for i,interval in enumerate(diagonal):
                    value,cell=round_cell(interval,lambda t,i=i:algebraic_equal(exact_probability(vectors,norms,p,i),t))
                    rounded.append(value); probability_cells.append(cell)
                full_rounded=[]; full_cells=[]
                for i,interval in enumerate(full):
                    value,cell=round_cell(interval,lambda t,i=i:algebraic_equal(exact_probability(vectors,norms,p,i,True),t))
                    full_rounded.append(value); full_cells.append(cell)
                if any(not isfinite(x) or x<0 for x in rounded) or abs(fsum(rounded)-1)>1e-10:
                    raise Unresolved('rounded law fails inherited probability/mass gate')
                cert.update(status='certified',bits=bits,basis_columns=basis,basis_cells=basis_cells,
                            q_diag_canonical=rounded,probability_cells=probability_cells,
                            q_full_exact_rounded=full_rounded,full_probability_cells=full_cells,
                            projected_norm_interval=norm.data(),reason=None)
                return cert
            except Unresolved: continue
        raise Unresolved('registered rounding refinement exhausted')
    except Unresolved as error:
        cert.update(status='numerical-unresolved',reason=str(error))
        return cert


def controls(cert, legacy_basis, legacy_full, legacy_projector=None):
    """Exact rational projector bound and enclosed ideal-full TV bound."""
    if cert['status']!='certified': return {'status':'unresolved','reason':cert['reason']}
    vectors=[[Q(x) for x in row] for row in cert['directions']]; norms=[Q(d) for d in cert['norms']]
    n=len(vectors[0]); B=[[rational(x) for x in row] for row in legacy_basis]
    if len(B)!=n or any(len(row)!=cert['rank'] for row in B):
        return {'status':'unresolved','rank':False,'reason':'canonical/legacy rank differs'}
    P=projector(vectors,norms)
    legacy_P=([[rational(x) for x in row] for row in legacy_projector]
              if legacy_projector is not None else [[dot(B[i],B[j]) for j in range(n)] for i in range(n)])
    if len(legacy_P)!=n or any(len(row)!=n for row in legacy_P):
        raise ValueError('legacy projector dimensions differ')
    difference=sum((P[i][j]-legacy_P[i][j])**2 for i in range(n) for j in range(n))
    tv=sum((Interval(Q(cell['interval'][0]),Q(cell['interval'][1]))-rational(x)).absolute().hi
           for cell,x in zip(cert['full_probability_cells'],legacy_full,strict=True))/2
    constant=all(sum(row)==1 for row in P)
    result={'rank':True,'projector_distance_squared':str(difference),'projector':difference<=Q(1,10**20),
            'full_law_tv_upper':str(tv),'full_law':tv<=Q(1,10**10),'constant_span_exact':constant,
            'parseval_exact':all(dot(a,b)==(d if i==j else 0)
                for i,(a,d) in enumerate(zip(vectors,norms,strict=True)) for j,b in enumerate(vectors))}
    result['status']='pass' if all(result[k] for k in ('rank','projector','full_law','constant_span_exact','parseval_exact')) else 'unresolved'
    return result
