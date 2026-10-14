"""Numerical extraction/rendering shared by production and external checks."""
from fractions import Fraction as Q
from fractions import Fraction as F
from pathlib import Path
import json, math
FIELDS=("raw_by_state", "package_by_state", "joint_by_state")

def rational(z):
 z=Q(z);return f'({z.numerator} : ℚ) / {z.denominator}'

def vector(a):return '!['+',\n   '.join(rational(z) for z in a)+']'

def matrix(a):return '!!['+';\n   '.join(','.join(rational(z) for z in row) for row in a)+']'

def quant(lo,hi,bits):
 g=1<<bits
 return Q(lo.numerator*g//lo.denominator-1,g),Q(-((-hi.numerator*g)//hi.denominator)+1,g)

def linear(a,lo,hi):return a*(lo if a>=0 else hi)

def extract(context,certificate):
 v=list(map(Q,context['born']['sym_eigvec_basis'][0]));K=[list(map(Q,row)) for row in context['kernel']]
 labels=context['lens']['joint_by_state']
 if len(v)!=32 or len(K)!=32 or any(len(row)!=32 for row in K) or len(labels)!=32:
  raise ValueError('B05 carrier dimension differs')
 if any(a<0 for row in K for a in row) or any(sum(row)<=0 for row in K):
  raise ValueError('B05 kernel positivity/row support differs')
 w=[t-sum(v)/32 for t in v];s=sum(t*t for t in w)
 if s<=0:raise ValueError('B05 metric is not positive')
 word=certificate['witness']
 if (word['context'],word['g'],word['h'],word['j'])!=('joint_by_state',0,1,0):
  raise ValueError('B05 registered word differs')
 block=[i for i,label in enumerate(labels) if label==0]
 moments=[Q(len(block)),2*sum(w[i] for i in block),sum(w[i]**2 for i in block)]
 records=[]
 for side in ('left','right'):
  pair=certificate['pair_certificate'][side]
  if len(pair)!=2:raise ValueError('B05 ensemble dimension differs')
  rows=[]
  for ray,weight in pair:
   t,z=Q(ray),Q(weight);amp=[1+t*a for a in w]
   if z<0 or min(amp)<=0:raise ValueError('B05 source weight/amplitude is not positive')
   mass=sum(amp[i]**2 for i in block)/(32+s*t*t)
   post=[sum(K[i][j]*amp[i]**2 for i in block) for j in range(32)]
   rl=[];rh=[]
   for q in post:
    if q<0:raise ValueError('B05 negative post-read successor')
    k=math.isqrt((q.numerator<<128)//q.denominator);lo=Q(k,1<<64)
    hi=lo if lo*lo==q else Q(k+1,1<<64)
    rl.append(lo);rh.append(hi)
   Sl,Su=sum(rl),sum(rh)
   if Sl<=0:raise ValueError('B05 successor root sum unresolved')
   Tl=sum(linear(a,l,u) for a,l,u in zip(w,rl,rh))
   Tu=-sum(linear(-a,l,u) for a,l,u in zip(w,rl,rh))
   values=[32/s*T/S for T in (Tl,Tu) for S in (Sl,Su)]
   L,U=quant(min(values),max(values),48)
   if sum(linear(32*a/s-L,l,u) for a,l,u in zip(w,rl,rh))<0 or sum(linear(U-32*a/s,l,u) for a,l,u in zip(w,rl,rh))<0:
    raise ValueError('B05 chart certificate failed')
   sqlo=Q(0) if L<=0<=U else min(L*L,U*U);sqhi=max(L*L,U*U)
   nl=moments[0]+linear(moments[1],L,U)+linear(moments[2],sqlo,sqhi)
   nu=moments[0]-linear(-moments[1],L,U)-linear(-moments[2],sqlo,sqhi)
   vals=[N/D for N in (nl,nu) for D in (32+s*sqlo,32+s*sqhi)]
   Plo,Phi=quant(min(vals),max(vals),40)
   if moments[0]-32*Plo+linear(moments[1],L,U)+linear(moments[2]-s*Plo,sqlo,sqhi)<0 or 32*Phi-moments[0]+linear(-moments[1],L,U)+linear(s*Phi-moments[2],sqlo,sqhi)<0:
    raise ValueError('B05 quadratic readout certificate failed')
   rows.append(dict(ray=t,weight=z,mass=mass,post=post,lo=rl,hi=rh,L=L,U=U,sqlo=sqlo,sqhi=sqhi,Plo=Plo,Phi=Phi))
  if sum(r['weight'] for r in rows)!=1:raise ValueError('B05 ensemble is not normalized')
  records.append(rows)
 def barycenter(rows):
  result=[[Q(0),Q(0)],[Q(0),Q(0)]]
  for row in rows:
   v=[Q(1),row['ray']];metric=[Q(32),s];denominator=32+s*row['ray']**2
   for i in range(2):
    for j in range(2):result[i][j]+=row['weight']*v[i]*v[j]*metric[j]/denominator
  return result
 left,right=map(barycenter,records)
 given=[list(map(Q,row)) for row in certificate['pair_certificate']['coordinate_barycenter']]
 if left!=right or left!=given:raise ValueError('B05 equal barycenter certificate differs')
 if sum(r['weight']*r['mass']*r['Phi'] for r in records[0])>=sum(r['weight']*r['mass']*r['Plo'] for r in records[1]):
  raise ValueError('B05 total probability intervals overlap')
 return w,s,K,labels,moments,records

def render_checked(certificate,data):
 w,s,K,labels,moments,records=data
 out='import BornCalculus.B04Inputs\n\nnamespace BornCalculus\n\n'
 out+='/- Original EXP-112/loo_A25 completion apparatus, joint read 0, K, joint read 0.\nRetained-input binding is external; finite inequalities are kernel checked. -/\n'
 out+='def b05MomentsQ : Fin 3 → ℚ := '+vector(moments)+'\n'
 out+='def b05BarycenterQ : Matrix (Fin 2) (Fin 2) ℚ := '+matrix(certificate['pair_certificate']['coordinate_barycenter'])+'\n'
 for name,key,is_vector in [('b05RayQ','ray',False),('b05WeightQ','weight',False),('b05MassQ','mass',False),('b05PostQ','post',True),('b05LoQ','lo',True),('b05HiQ','hi',True),('b05LowerQ','L',False),('b05UpperQ','U',False),('b05SqLowerQ','sqlo',False),('b05SqUpperQ','sqhi',False),('b05ReadLowerQ','Plo',False),('b05ReadUpperQ','Phi',False)]:
  typ='Fin 32 → ℚ' if is_vector else 'ℚ'
  out+=f'def {name} (side atom : Fin 2) : {typ} := match side.val, atom.val with\n'
  for i,rows in enumerate(records):
   for j,row in enumerate(rows):
    pattern=f'{i}, {j}' if (i,j)!=(1,1) else '_, _'
    out+=' | '+pattern+' => '+(vector(row[key]) if is_vector else rational(row[key]))+'\n'
 return out+'end BornCalculus\n'

def render(context,certificate):
 return render_checked(certificate,extract(context,certificate))
