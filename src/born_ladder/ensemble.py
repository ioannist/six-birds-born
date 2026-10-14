"""Previously admitted nonlinear ray/linear-measure apparatus, separate from density calculus."""
from fractions import Fraction as Q
from . import arithmetic as M
I=M.I
FIELDS=("raw_by_state","package_by_state","joint_by_state")
def _require(condition,message):
 # Invariants are executable verification gates, including under Python -O.
 if not condition:raise AssertionError(message)


def canonical_measure(components):
 """Exact chart atoms. Protocol equality must be checked separately."""
 out={}
 for atom,weight in components:
  weight=Q(weight)
  if weight<0: raise ValueError('negative measure')
  out[Q(atom)]=out.get(Q(atom),Q(0))+weight
 return tuple(sorted((a,w) for a,w in out.items() if w))

class EnsembleInstrument:
 def __init__(self,transport):
  self.t=transport;self.n=self.t.n;self.w=self.t.w;self.ss=self.t.ss
  self.Kh={1:self.t.K,2:self.t.K2}
  self.Kh[4]=M.mm(self.Kh[2],self.Kh[2]);self.Kh[8]=M.mm(self.Kh[4],self.Kh[4])
  self.parts={f:{j:tuple(i for i,x in enumerate(self.t.x['lens'][f]) if x==j) for j in sorted(set(self.t.x['lens'][f]))} for f in FIELDS}
  self.moments={};self.coefficients={}
  for block in set([tuple(range(self.n)),()]+[b for part in self.parts.values() for b in part.values()]):
   self.moments[block]=(Q(len(block)),2*sum((self.w[i] for i in block),Q(0)),sum((self.w[i]**2 for i in block),Q(0)))
   for h,K in self.Kh.items():
    self.coefficients[h,block]=[(sum((K[i][j] for i in block),Q(0)),2*sum((K[i][j]*self.w[i] for i in block),Q(0)),sum((K[i][j]*self.w[i]**2 for i in block),Q(0))) for j in range(self.n)]
 def read(self,l,field):
  l=M.asI(l);norm=self.n+self.ss*l.square()
  return [self.t.poly(self.moments[b],l)/norm for b in self.parts[field].values()]
 def branch(self,l,block,h):
  l=M.asI(l);num=self.t.poly(self.moments[block],l)
  b=num/(self.n+self.ss*l.square())
  if b.hi==0:return b,None
  if b.lo<=0:raise ArithmeticError('unresolved branch domain')
  roots=[self.t.poly(c,l).sqrt() for c in self.coefficients[h,block]]
  total=M.isum(roots)
  if total.lo<=0:raise ArithmeticError('unresolved projection domain')
  return b,self.t.c*M.isum(w*r for w,r in zip(self.w,roots))/total
 def general_branch(self,a,b,block,h):
  """Homogeneous exact frame coefficients, including the pure-mode ray."""
  a,b=Q(a),Q(b)
  if a==b==0:raise ValueError('zero vector is not a ray')
  den=self.n*a*a+self.ss*b*b
  c0,c1,c2=self.moments[block];mass=(c0*a*a+c1*a*b+c2*b*b)/den
  if mass==0:return I(0),None
  if mass<0:raise ArithmeticError('negative branch mass')
  roots=[I(c0*a*a+c1*a*b+c2*b*b).sqrt() for c0,c1,c2 in self.coefficients[h,block]]
  return I(mass),self.t.c*M.isum(w*r for w,r in zip(self.w,roots))/M.isum(roots)
 def sequential(self,l,field,h):
  retained=[];joint=[]
  for g,block in self.parts[field].items():
   b,succ=self.branch(l,block,h)
   row=[I(0)]*len(self.parts[field]) if succ is None else [b*v for v in self.read(succ,field)]
   retained.append({'g':g,'mass':b,'lambda':succ});joint.append(row)
  forgotten=[M.isum(row[j] for row in joint) for j in range(len(self.parts[field]))]
  # Interval certificates enclose exact stochastic identities, rather than assert
  # floating approximations equal 1. Uniform normalization follows from algebra.
  _require(M.isum(forgotten).lo<=1<=M.isum(forgotten).hi, 'verification invariant failed')
  for rec,row in zip(retained,joint):_require(M.isum(row).lo<=rec['mass'].hi and M.isum(row).hi>=rec['mass'].lo, 'verification invariant failed')
  return retained,joint,forgotten
 def future(self,p,h):return M.normalize(M.mv(M.transpose(self.Kh[h]),p))
 def unconditional(self,l,h):return self.branch(l,tuple(range(self.n)),h)[1]
 def push(self,p,field):return [sum((p[i] for i in block),Q(0)) for block in self.parts[field].values()]
