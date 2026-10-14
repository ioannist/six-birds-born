"""Adopted G-metric density instruments; explicit apparatus inputs.
Finite nonadaptive words only; no K or F inserted.
"""
import itertools,hashlib,json
from .arithmetic import *
FIELDS=("raw_by_state","package_by_state","joint_by_state")
class Instrument:
 def __init__(self,context,w,s,projector,kernel):
  w=list(map(Q,w));s=Q(s);n=len(w)
  if not n or s<=0 or sum(w)!=0 or sum(t*t for t in w)!=s:
   raise ValueError('centered rank-two frame required')
  lens=context.get('lens',{})
  if any(f not in lens or not isinstance(lens[f],(list,tuple)) or len(lens[f])!=n for f in FIELDS):
   raise ValueError('complete lens carrier dimension required')
  self.x,self.w,self.s,self.P,self.K=context,w,s,projector,kernel;self.n=n;self.G=[Q(n),s]
  self.parts={f:{g:tuple(i for i,x in enumerate(self.x['lens'][f]) if x==g) for g in sorted(set(self.x['lens'][f]))} for f in FIELDS}
  self.parentsets=sorted({tuple(sorted(i for g in gs for i in part[g])) for part in self.parts.values() for mask in range(1<<len(part)) for gs in [[g for g in part if mask&(1<<g)]]},key=lambda a:(len(a),a))
  self.C={};self.A={};self.roots={}
  for S in self.parentsets:
   H=[[Q(len(S)),sum((self.w[i] for i in S),Q(0))],[sum((self.w[i] for i in S),Q(0)),sum((self.w[i]**2 for i in S),Q(0))]]
   C=[[H[i][j]/self.G[i] for j in range(2)] for i in range(2)]
   _require(H==transpose(H) and H[0][0]>=0 and H[1][1]>=0 and det(H)>=0, 'verification invariant failed')
   self.C[S]=C;self.A[S],self.roots[S]=principal(C)
  self.atomic={f:{g:self.parts[f][g] for g in self.parts[f]} for f in FIELDS}
 def adjoint(self,X):return [[self.G[j]*X[j][i]/self.G[i] for j in range(2)] for i in range(2)]
 def validate(self,R):
  if len(R)!=2 or any(len(row)!=2 for row in R):raise ValueError('density shape')
  try:R=[[Q(v) for v in row] for row in R]
  except (ValueError,TypeError):raise ValueError('external density needs exact coefficients')
  H=[[self.G[i]*R[i][j] for j in range(2)] for i in range(2)]
  if H!=transpose(H) or trace(R)!=1 or H[0][0]<0 or H[1][1]<0 or det(H)<0:raise ValueError('not a G-positive trace-one density')
  return R
 def pure(self,l):
  l=Q(l);v=[Q(1),l];den=self.n+self.s*l*l
  return self.validate([[v[i]*v[j]*self.G[j]/den for j in range(2)] for i in range(2)])
 def branch(self,R,S):
  A=self.A[S];out=matmul(matmul(A,asinterval(R)),A);mass=asI(trace(out))
  if mass.hi==0:return out,mass,None
  if mass.lo<=0:raise ArithmeticError('unresolved positive branch domain')
  return out,mass,[[x/mass for x in row] for row in out]
 def nonselective(self,R,field):
  out=asinterval(zero())
  for S in self.parts[field].values():out=add(out,self.branch(R,S)[0])
  _require(asI(trace(out)).lo<=1<=asI(trace(out)).hi, 'verification invariant failed')
  return out
 def word(self,contexts,outcomes):
  if len(contexts)!=len(outcomes):raise ValueError('outside bounded word domain')
  M=asinterval(eye())
  for f,g in zip(contexts,outcomes):M=matmul(self.A[self.parts[f][g]],M)
  return M,matmul(self.adjoint(M),M)
 def probability(self,R,word_effect):return asI(trace(matmul(asinterval(R),word_effect)))
 def grouped(self,R,field,labels):
  """Coarse readout in fixed context: sum actual branches, not sqrt(sum effects)."""
  if any(g not in self.parts[field] for g in labels):raise ValueError('bad grouped label')
  out=asinterval(zero())
  for g in set(labels):out=add(out,self.branch(R,self.parts[field][g])[0])
  mass=asI(trace(out));posterior=None if mass.hi==0 else [[v/mass for v in row] for row in out]
  return out,mass,posterior

def _require(condition,message):
 # Invariants are executable verification gates, including under Python -O.
 if not condition:raise AssertionError(message)


def tests(model):
 for length in (1,2):
  for cs in itertools.product(FIELDS,repeat=length):
   yield cs,list(itertools.product(*(model.parts[c] for c in cs)))

def constructor(model):
 """Finite per-preparation syntax. Density formulas live on these fixed nodes.
Full branch slots retained internally; visibility/forgetting is a priced projection.
"""
 nodes={('ENTRY',),('PUBLIC_FAILURE','INVALID_SOURCE'),('HALT_FAILURE','INVALID_SOURCE')};edges=[];families=[]
 for cs,words in tests(model):
  families.append({'contexts':list(cs),'words':[list(w) for w in words]})
  for modes in itertools.product(('retain','forget'),repeat=len(cs)):
   base=(cs,modes);first=base+('READ',0,())
   nodes.add(first);edges.append((('ENTRY',),('BEGIN',cs,modes),first))
   for depth in range(len(cs)):
    prefixes=sorted(set(w[:depth] for w in words))
    for pre in prefixes:
     src=base+('READ',depth,pre);nodes.add(src)
     for g in model.parts[cs[depth]]:
      nxt=base+('HALT',pre+(g,)) if depth+1==len(cs) else base+('READ',depth+1,pre+(g,))
      nodes.add(nxt);edges.append((src,('EMIT',g),nxt))
     fail=base+('PUBLIC_FAILURE','BAD_STAGE');halt=base+('HALT_FAILURE','BAD_STAGE');nodes.update((fail,halt));edges.extend([(src,('INVALID',),fail),(fail,('HALT',),halt)])
   for word in words:
    halt=base+('HALT',word);edges.append((halt,('ANY',),halt))
   bad=base+('HALT_FAILURE','BAD_STAGE');edges.append((bad,('ANY',),bad))
 for code in ('BAD_CONTEXT','BAD_LENGTH','BAD_MODE','BAD_COMMAND'):
  fail=('PUBLIC_FAILURE',code);halt=('HALT_FAILURE',code);nodes.update((fail,halt));edges.extend([(('ENTRY',),('INVALID',code),fail),(fail,('HALT',),halt),(halt,('ANY',),halt)])
 edges.extend([(('PUBLIC_FAILURE','INVALID_SOURCE'),('HALT',),('HALT_FAILURE','INVALID_SOURCE')),(('HALT_FAILURE','INVALID_SOURCE'),('ANY',),('HALT_FAILURE','INVALID_SOURCE'))])
 _require(all(a in nodes and b in nodes for a,cmd,b in edges), 'verification invariant failed')
 digest=hashlib.sha256()
 for e in sorted(set(edges),key=repr):digest.update((json.dumps(e,separators=(',',':'))+'\n').encode())
 return {'per_fixed_public_density':True,'finite_node_count':len(nodes),'edge_count':len(set(edges)),'edge_digest':digest.hexdigest(),'test_families':families,'successor_closed':True,'visibility':'commands/stages public; retain emits labelled word; forget projects label to FORGOTTEN, sums unnormalized branches; internal slot does not license hidden-state access','zero_branch':'zero edge, no posterior; singleton atoms may be singular','continuous_carrier_called_finite':False}
