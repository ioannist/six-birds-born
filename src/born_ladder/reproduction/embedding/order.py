"""Numerical extraction/rendering shared by production and external checks."""
from fractions import Fraction as Q
from fractions import Fraction as F
from pathlib import Path
import json, math
FIELDS=("raw_by_state", "package_by_state", "joint_by_state")

def rational(x):
 x=Q(x);return f'({x.numerator} : ℚ) / {x.denominator}'

def mm(A,B):return [[sum(A[i][k]*B[k][j] for k in range(2)) for j in range(2)] for i in range(2)]

def det(A):return A[0][0]*A[1][1]-A[0][1]*A[1][0]

def linear(a,lo,hi):return a*(lo if a>=0 else hi)

def extract(context):
 v=list(map(Q,context['born']['sym_eigvec_basis'][0]))
 if len(v)!=32:raise ValueError('B07 carrier dimension differs')
 w=[a-sum(v)/32 for a in v];s=sum(a*a for a in w)
 if s<=0:raise ValueError('B07 metric is not positive')
 def effect(field,a):
  labels=context['lens'][field]
  if len(labels)!=32:raise ValueError('B07 lens dimension differs')
  block=[i for i,label in enumerate(labels) if label==a]
  return [[Q(len(block),32),sum(w[i] for i in block)/32],
          [sum(w[i] for i in block)/s,sum(w[i]**2 for i in block)/s]]
 E,F=effect('raw_by_state',1),effect('package_by_state',0)
 rows=[]
 for C,D in ((E,F),(F,E)):
  d=det(C);t=C[0][0]+C[1][1]
  a=mm(mm(C,D),C)[0][0]+d*D[0][0]
  b=mm(D,C)[0][0]+mm(C,D)[0][0]
  if d<=0 or t<=0:raise ValueError('B07 effect scalar domain differs')
  k=math.isqrt((d.numerator<<128)//d.denominator);lo=Q(k,1<<64)
  hi=lo if lo*lo==d else Q(k+1,1<<64)
  values=[N/Z for N in (a+linear(b,lo,hi),a-linear(-b,lo,hi)) for Z in (t+2*lo,t+2*hi)]
  grid=1<<40;l,u=min(values),max(values)
  L=Q(l.numerator*grid//l.denominator-1,grid);U=Q(-((-u.numerator*grid)//u.denominator)+1,grid)
  if a-L*t+linear(b-2*L,lo,hi)<0 or U*t-a+linear(2*U-b,lo,hi)<0:
   raise ValueError('B07 linear-radical certificate failed')
  rows.append(dict(d=d,t=t,a=a,b=b,lo=lo,hi=hi,L=L,U=U))
 if not (rows[0]['U']<rows[1]['L'] or rows[1]['U']<rows[0]['L']):raise ValueError('B07 order intervals overlap')
 return rows

def render_checked(rows):
 out='import BornCalculus.B06Inputs\n\nnamespace BornCalculus\n\n'
 out+='/- Original EXP-112/loo_A25 raw1/package0 principal-root order witness. -/\n'
 for name,key in [('b07DetQ','d'),('b07TraceQ','t'),('b07ConstantQ','a'),('b07LinearQ','b'),('b07LoQ','lo'),('b07HiQ','hi'),('b07LowerQ','L'),('b07UpperQ','U')]:
  out+=f'def {name} : Fin 2 → ℚ := !['+','.join(rational(row[key]) for row in rows)+']\n'
 return out+'end BornCalculus\n'

def render(context):
 return render_checked(extract(context))
