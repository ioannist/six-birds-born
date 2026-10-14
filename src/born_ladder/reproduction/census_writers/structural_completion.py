"""Unchanged exact quadratic-ring completion, explicit metric input."""
from .common import *


class Quad:
 """a+b*sqrt(d), exact positive-radical expression; never float conversion."""
 def __init__(self,a=0,b=0,d=3):self.a=Q(a);self.b=Q(b);self.d=Q(d)
 def co(self,x):
  x=x if isinstance(x,Quad) else Quad(x,0,self.d);assert x.d==self.d;return x
 def __add__(self,x):x=self.co(x);return Quad(self.a+x.a,self.b+x.b,self.d)
 __radd__=__add__
 def __neg__(self):return Quad(-self.a,-self.b,self.d)
 def __sub__(self,x):return self+-self.co(x)
 def __mul__(self,x):x=self.co(x);return Quad(self.a*x.a+self.b*x.b*self.d,self.a*x.b+self.b*x.a,self.d)
 __rmul__=__mul__
 def __eq__(self,x):x=self.co(x);return self.a==x.a and self.b==x.b
 def json(self):return {'rational':str(self.a),'radical_coefficient':str(self.b),'radicand':str(self.d),'root':'positive square root'}

def mm(X,Y):return [[sum((a*b for a,b in zip(row,col)),Quad(0,0,X[0][0].d)) for col in zip(*Y)] for row in X]

def add(X,Y):return [[a+b for a,b in zip(row,rr)] for row,rr in zip(X,Y)]

def scale(X,a):return [[a*v for v in row] for row in X]

def trace(X):return X[0][0]+X[1][1]

def sub(X,Y):return add(X,scale(Y,-1))

def dump(X):return [[v.json() for v in row] for row in X]

def certify_G(s):
 s=Q(s);assert s>0;d=3*s/32;q=lambda a=0,b=0:Quad(a,b,d);I=[[q(1),q()],[q(),q(1)]]
 states=[[[q(1),q()],[q(),q()]],[[q(Q(1,4)),q(0,Q(1,4))],[q(0,8/s),q(Q(3,4))]],[[q(Q(1,4)),q(0,Q(-1,4))],[q(0,-8/s),q(Q(3,4))]]]
 states +=[sub(I,R) for R in states.copy()]
 for R in states:
  assert mm(R,R)==R and trace(R)==1 and R[0][0]*R[1][1]-R[0][1]*R[1][0]==0
  assert 32*R[0][1]==s*R[1][0] # G-self-adjoint
 expected=[[1,Q(1,4),Q(1,4)],[Q(1,4),1,Q(1,4)],[Q(1,4),Q(1,4),1],[0,Q(3,4),Q(3,4)],[Q(3,4),0,Q(3,4)],[Q(3,4),Q(3,4),0]]
 table=[[trace(mm(R,E)) for E in states[:3]] for R in states]
 assert all(v==expected[i][j] for i,row in enumerate(table) for j,v in enumerate(row))
 mixtures=[[(i,Q(1,2)),(i+3,Q(1,2))] for i in range(3)]+[[(i,Q(1,3)) for i in range(3)],[(i,Q(1,3)) for i in range(3,6)]]
 for mix in mixtures:
  out=[[q(),q()],[q(),q()]]
  for i,w in mix:out=add(out,scale(states[i],w))
  assert out==scale(I,Q(1,2))
 # Independently check same table/identities in ordinary orthonormal frame s=32.
 if s!=32:
  orth=certify_G(Q(32));assert orth['YES_table_exact']==qs(expected)
 return {'status':'PASS','G':[['32','0'],['0',str(s)]],'exact_radicand':str(d),'states_and_sharp_yes_effects':[dump(R) for R in states],'YES_table_exact':qs(expected),'five_mixture_identities':qs(mixtures),'projector_roots':True,'all_projectors_trace1_idempotent_G_adjoint':True,'transformation':'S=diag(sqrt32,sqrt(s)); R_G=S^-1 R_orth S. upper offdiag=sign sqrt(3s/32)/4, lower=32/s*upper. Every expression multiplied in Q[sqrt(3s/32)], sqrt positive. This is exact conjugacy with the external real trine, not a new state or test.','real_positivity':'Positive G inner product (32,s>0); conjugacy to orthonormal real projectors proves PSD, not just trace/determinant.'}
