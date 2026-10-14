"""Numerical extraction/rendering shared by production and external checks."""
from fractions import Fraction as Q
from fractions import Fraction as F
from pathlib import Path
import json, math
FIELDS=("raw_by_state", "package_by_state", "joint_by_state")

def rational(x):
    q=Q(x)
    return f'({q.numerator} : ℚ) / {q.denominator}'

def vector(a):
    return '!['+',\n   '.join(rational(z) for z in a)+']'

def matrix(a):
    return '!!['+';\n   '.join(','.join(rational(z) for z in row) for row in a)+']'

def rational_root(x):
    if x<0:raise ValueError('negative B04 relative root')
    a,b=math.isqrt(x.numerator),math.isqrt(x.denominator)
    if a*a!=x.numerator or b*b!=x.denominator:
        raise ValueError('B04 initial rational-root fiber missing')
    return Q(a,b)

def extract(context, amplitude, joined):
    v=list(map(Q,context['born']['sym_eigvec_basis'][0]))
    if len(v)!=32:raise ValueError('B04 carrier dimension differs')
    w=[a-sum(v)/32 for a in v];s=sum(a*a for a in w)
    K=[list(map(Q,row)) for row in context['kernel']]
    if len(K)!=32 or any(len(row)!=32 for row in K) or s<=0:
        raise ValueError('B04 kernel/frame dimension differs')
    def update(p):return [sum(p[i]*K[i][j] for i in range(32)) for j in range(32)]
    records=[]
    for doc,is_joined in ((amplitude,False),(joined,True)):
        for op in ('K','K2'):
            row=doc['operations'][op]['certificate'];sides=[]
            for key in (('p_minus','p_plus') if is_joined else ('p','p_prime')):
                p=list(map(Q,row[key]))
                if len(p)!=32 or min(p)<0 or sum(p)!=1 or p[0]<=0:
                    raise ValueError('B04 source simplex/pivot differs')
                roots=[rational_root(a/p[0]) for a in p]
                if sum(a*b for a,b in zip(w,roots))!=0:
                    raise ValueError('B04 initial chart is not zero')
                mid=update(p);post=mid if op=='K' else update(mid)
                den=1<<40;lo=[];hi=[]
                for a in post:
                    if a<0:raise ValueError('B04 negative successor')
                    k=math.isqrt((a.numerator<<80)//a.denominator)
                    l=Q(k,den);u=l if l*l==a else Q(k+1,den)
                    lo.append(l);hi.append(u)
                Sl,Su=sum(lo),sum(hi)
                if Sl<=0:raise ValueError('B04 successor root sum unresolved')
                Tl=sum(a*(l if a>=0 else u) for a,l,u in zip(w,lo,hi))
                Tu=sum(a*(u if a>=0 else l) for a,l,u in zip(w,lo,hi))
                values=[32/s*T/S for T in (Tl,Tu) for S in (Sl,Su)]
                grid=1<<24;low,high=min(values),max(values)
                L=Q((low.numerator*grid)//low.denominator-1,grid)
                U=Q(-((-high.numerator*grid)//high.denominator)+1,grid)
                def lower(coeff):
                    return sum(a*(l if a>=0 else u) for a,l,u in zip(coeff,lo,hi))
                if lower([32*a/s-L for a in w])<0 or lower([U-32*a/s for a in w])<0:
                    raise ValueError('B04 linear-root certificate failed')
                sides.append(dict(p=p,r=roots,mid=mid,post=post,lo=lo,hi=hi,L=L,U=U))
            if not (sides[0]['U']<sides[1]['L'] or sides[1]['U']<sides[0]['L']):
                raise ValueError('B04 successor chart intervals overlap')
            records.append(sides)
    return w,s,K,records


def render_checked(context, data):
    w,s,K,records=data

    out='import BornCalculus.Definitions\n\nnamespace BornCalculus\n\n'
    out+='/- Original EXP-112/loo_A25 exact kernel and four B04 fiber witnesses.\nExternal archive binding is separate from the kernel proof. -/\n'
    out+='def b04SQ : ℚ := '+rational(s)+'\n'
    out+='def b04WQ : Fin 32 → ℚ :=\n '+vector(w)+'\n'
    out+='def b04KQ : Matrix (Fin 32) (Fin 32) ℚ :=\n '+matrix(K)+'\n'
    for name,key in [('b04PQ','p'),('b04RootsQ','r'),('b04MidQ','mid'),
                     ('b04FutureQ','post'),('b04LoQ','lo'),('b04HiQ','hi')]:
        out+=f'def {name} (e : Fin 4) (side : Fin 2) : Fin 32 → ℚ := match e.val, side.val with\n'
        for i,record in enumerate(records):
            for side,data in enumerate(record):
                pattern=f'{i}, {side}' if (i,side)!=(3,1) else '_, _'
                out+=' | '+pattern+' => '+vector(data[key])+'\n'
    for name,key in [('b04LowerQ','L'),('b04UpperQ','U')]:
        out+=f'def {name} (e : Fin 4) (side : Fin 2) : ℚ := match e.val, side.val with\n'
        for i,record in enumerate(records):
            for side,data in enumerate(record):
                pattern=f'{i}, {side}' if (i,side)!=(3,1) else '_, _'
                out+=' | '+pattern+' => '+rational(data[key])+'\n'
    for name,field in [('b04Raw','raw_by_state'),('b04Package','package_by_state'),('b04Joint','joint_by_state')]:
        labels=context['lens'][field]
        if len(labels)!=32 or any(a not in range(3) for a in labels):
            raise ValueError('B04 lens labels differ')
        out+=f'def {name} : Fin 32 → Fin 3 := !['+','.join(map(str,labels))+']\n'
    return out+'end BornCalculus\n'

def render(context, amplitude, joined):
    return render_checked(context, extract(context, amplitude, joined))
