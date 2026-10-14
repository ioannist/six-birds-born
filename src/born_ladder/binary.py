"""Adopted real effect-interval binary instruments; exact descriptors."""
from fractions import Fraction as Q
import itertools
from . import arithmetic as L
def _require(condition,message):
 # Invariants are executable verification gates, including under Python -O.
 if not condition:raise AssertionError(message)


def positive(C,G):
 H=[[Q(G[i])*Q(C[i][j]) for j in range(2)] for i in range(2)]
 return H==L.transpose(H) and H[0][0]>=0 and H[1][1]>=0 and L.det(H)>=0

def strict_positive(C,G):
 H=[[G[i]*C[i][j] for j in range(2)] for i in range(2)]
 return H==L.transpose(H) and H[0][0]>0 and L.det(H)>0
def exact_matrix(C):
 if len(C)!=2 or any(len(r)!=2 for r in C):raise ValueError('matrix shape')
 if any(isinstance(x,(float,bool)) for r in C for x in r):raise ValueError('exact coefficient description required')
 try:return [[Q(x) for x in row] for row in C]
 except (ValueError,TypeError,ZeroDivisionError):raise ValueError('exact coefficient description required')

def effect(C,G):
 C=exact_matrix(C)
 if not positive(C,G) or not positive(L.sub(L.eye(),C),G):raise ValueError('effect domain 0<=E<=I in G metric')
 return C

class Binary:
 def __init__(self,base):self.base=base;self.G=base.G
 def state(self,R):return self.base.validate(exact_matrix(R))
 def roots(self,E):
  E=effect(E,self.G);C=[L.sub(L.eye(),E),E]
  roots=[L.principal(X) for X in C]
  return C,[r[0] for r in roots],[r[1] for r in roots]
 def branch(self,R,E,g):
  R=self.state(R)
  if g not in (0,1):raise ValueError('invalid outcome')
  C,A,cert=self.roots(E);mass=L.trace(L.matmul(R,C[g]));_require(0<=mass<=1, 'verification invariant failed')
  # Exact zero mass + positivity forces the entire unnormalized branch zero.
  if mass==0:return L.asinterval(L.zero()),mass,None
  out=L.matmul(L.matmul(A[g],L.asinterval(R)),A[g]);_require(L.encloses([[L.trace(out)]],[[mass]]), 'verification invariant failed')
  return out,mass,L.scale(out,1/mass)
 def channel(self,R,E):
  return L.add(self.branch(R,E,0)[0],self.branch(R,E,1)[0])
 def word_effects(self,commands):
  
  roots=[]
  for E,mode in commands:
   if mode not in ('retain','forget'):raise ValueError('invalid visibility mode')
   roots.append(self.roots(E)[1])
  result={}
  for word in itertools.product((0,1),repeat=len(commands)):
   M=L.asinterval(L.eye())
   for A,g in zip(roots,word):M=L.matmul(A[g],M)
   result[word]=(M,L.matmul(self.base.adjoint(M),M))
  _require(L.encloses(sum_matrices([E for M,E in result.values()]),L.eye()), 'verification invariant failed')
  return result

def sum_matrices(xs):
 out=L.zero()
 for x in xs:out=L.add(out,x)
 return out

def visible_subset(words,chosen,modes):
 chosen=set(chosen)
 def proj(w):return tuple(g if mode=='retain' else 'FORGOTTEN' for g,mode in zip(w,modes))
 return all((w in chosen)==(v in chosen) for w in words for v in words if proj(w)==proj(v))

def finite_surface(length):
 if length not in (1,2):raise ValueError('bounded command length')
 # Fixed public source/parameters. Full internal prefixes; public projection
 # is separate. Invalid command/source stops; HALT is absorbing.
 nodes=[('ENTRY',),('PUBLIC_FAILURE',),('HALT_FAILURE',)]
 for d in range(length+1):
  nodes += [('READ' if d<length else 'HALT',)+w for w in itertools.product((0,1),repeat=d)]
 edges=[(('ENTRY',),'VALID',('READ',)),(('ENTRY',),'INVALID',('PUBLIC_FAILURE',)),(('PUBLIC_FAILURE',),'HALT',('HALT_FAILURE',)),(('HALT_FAILURE',),'ANY',('HALT_FAILURE',))]
 for d in range(length):
  for pre in itertools.product((0,1),repeat=d):
   src=('READ',)+pre
   for g in (0,1):edges.append((src,('EMIT',g),('HALT' if d+1==length else 'READ',)+pre+(g,)))
   edges.append((src,'INVALID',('PUBLIC_FAILURE',)))
 for pre in itertools.product((0,1),repeat=length):edges.append((('HALT',)+pre,'ANY',('HALT',)+pre))
 _require(all(a in nodes and b in nodes for a,cmd,b in edges), 'verification invariant failed')
 return {'length':length,'nodes':nodes,'edges':edges,'zero_edges':'zero probability, no posterior/no emission; impossible paths omitted from reached support','continuous_parameters_are_not_called_finite':True,'successor_closed_syntax':True}
