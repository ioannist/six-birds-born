"""Exact rational carrier/effect arithmetic and 384-bit outward root enclosures.
Exact rational interval operations and certified matrix-root enclosures.
"""
from fractions import Fraction as Q
from dataclasses import dataclass
import math
BITS=384
DEN=1<<BITS

def _require(condition,message):
 # Invariants are executable verification gates, including under Python -O.
 if not condition:raise AssertionError(message)


def floorq(x):return Q((x.numerator*DEN)//x.denominator,DEN)
def ceilq(x):return -floorq(-x)
@dataclass(frozen=True)
class I:
    lo:Q
    hi:Q
    def __init__(self,lo,hi=None):
        lo=Q(lo);hi=lo if hi is None else Q(hi)
        if lo>hi:raise ValueError('reversed interval')
        object.__setattr__(self,'lo',lo);object.__setattr__(self,'hi',hi)
    def __add__(self,y):
        y=asI(y);return outward(self.lo+y.lo,self.hi+y.hi)
    __radd__=__add__
    def __neg__(self):return I(-self.hi,-self.lo)
    def __sub__(self,y):return self+-asI(y)
    def __rsub__(self,y):return asI(y)+-self
    def __mul__(self,y):
        y=asI(y);v=[a*b for a in (self.lo,self.hi) for b in (y.lo,y.hi)]
        return outward(min(v),max(v))
    __rmul__=__mul__
    def __truediv__(self,y):
        y=asI(y)
        if y.lo<=0<=y.hi:raise ZeroDivisionError('interval denominator includes zero')
        return self*outward(min(1/y.lo,1/y.hi),max(1/y.lo,1/y.hi))
    def __rtruediv__(self,y):return asI(y)/self
    def square(self):
        return outward(0 if self.lo<=0<=self.hi else min(self.lo**2,self.hi**2),max(self.lo**2,self.hi**2))
    def sqrt(self):
        if self.lo<0:raise ValueError('negative square root interval')
        a=math.isqrt((self.lo.numerator<<(2*BITS))//self.lo.denominator)
        b=math.isqrt((self.hi.numerator<<(2*BITS))//self.hi.denominator)
        lo=Q(a,DEN);hi=Q(b,DEN)
        if hi*hi!=self.hi:hi+=Q(1,DEN)
        return I(lo,hi)
    def abs(self):
        return I(0 if self.lo<=0<=self.hi else min(abs(self.lo),abs(self.hi)),max(abs(self.lo),abs(self.hi)))
    def json(self):return {'lo':str(self.lo),'hi':str(self.hi),'lo_approx':float(self.lo),'hi_approx':float(self.hi)}

def asI(x):return x if isinstance(x,I) else I(x)
def outward(lo,hi):return I(floorq(lo),ceilq(hi))
def isum(xs):return sum(xs,I(0))
def midpoint(x):return (x.lo+x.hi)/2

def mv(A,v):return [sum((a*b for a,b in zip(row,v)),Q(0)) for row in A]
def transpose(A):return list(map(list,zip(*A)))
def mm(A,B):return [[sum((a*b for a,b in zip(row,col)),Q(0)) for col in zip(*B)] for row in A]
def normalize(v):
 s=sum(v)
 if s<=0:raise ValueError('positive normalization mass required')
 return [a/s for a in v]
def prob(a):return normalize([v*v for v in a])

def matmul(X,Y):return [[sum((a*b for a,b in zip(row,col)),Q(0)) for col in zip(*Y)] for row in X]

def transpose(X):return list(map(list,zip(*X)))

def trace(X):return sum(X[i][i] for i in range(len(X)))

def eye():return [[Q(1),Q(0)],[Q(0),Q(1)]]

def zero():return [[Q(0),Q(0)],[Q(0),Q(0)]]

def add(X,Y):return [[x+y for x,y in zip(r,s)] for r,s in zip(X,Y)]

def sub(X,Y):return [[x-y for x,y in zip(r,s)] for r,s in zip(X,Y)]

def scale(X,a):return [[a*x for x in row] for row in X]

def asinterval(X):return [[asI(x) for x in row] for row in X]

def det(X):return X[0][0]*X[1][1]-X[0][1]*X[1][0]

def qstrings(X):return [[str(x) for x in row] for row in X]

def ijs(X):return [[asI(x).json() for x in row] for row in X]

def encloses(X,Y):
 if len(X)!=len(Y) or any(len(r)!=len(s) for r,s in zip(X,Y)):return False
 return all(asI(x).lo<=y<=asI(x).hi for r,s in zip(X,Y) for x,y in zip(r,s))

def separated(X,Y):return [(i,j) for i in range(len(X)) for j in range(len(X[0])) if (asI(X[i][j])-Y[i][j]).lo>0 or (asI(X[i][j])-Y[i][j]).hi<0]

def exact_sqrt(x):
 x=Q(x)
 if x<0:raise ValueError('negative root')
 a,b=math.isqrt(x.numerator),math.isqrt(x.denominator)
 return Q(a,b) if a*a==x.numerator and b*b==x.denominator else None

def principal(C):
 """G-positive 2x2 principal root, exact rational when this formula is rational."""
 if C==zero():return asinterval(zero()),{'method':'exact zero','rational_root':qstrings(zero())}
 d=det(C);t=trace(C)
 if d<0 or t<=0:raise ValueError('not positive input')
 sd=exact_sqrt(d)
 denominator=exact_sqrt(t+2*sd) if sd is not None else None
 if denominator is not None:
  root=scale(add(C,scale(eye(),sd)),1/denominator)
  _require(matmul(root,root)==C, 'verification invariant failed')
  return asinterval(root),{'method':'exact rational principal root','rational_root':qstrings(root),'trace_C':str(t),'det_C':str(d)}
 D=I(d).sqrt();Z=(t+2*D).sqrt();root=[[((I(C[i][j])+D) if i==j else I(C[i][j]))/Z for j in range(2)] for i in range(2)]
 _require(encloses(matmul(root,root),C), 'verification invariant failed')
 return root,{'method':'certified principal radical (C+sqrt(det C)I)/sqrt(tr C+2sqrt(det C))','trace_C':str(t),'det_C':str(d),'sqrt_det':D.json(),'denominator':Z.json(),'root_squared_encloses_C':True}

class Quad:
 """a+b*sqrt(d), exact positive-radical expression; never float conversion."""
 def __init__(self,a=0,b=0,d=3):self.a=Q(a);self.b=Q(b);self.d=Q(d)
 def co(self,x):
  x=x if isinstance(x,Quad) else Quad(x,0,self.d);_require(x.d==self.d, 'verification invariant failed');return x
 def __add__(self,x):x=self.co(x);return Quad(self.a+x.a,self.b+x.b,self.d)
 __radd__=__add__
 def __neg__(self):return Quad(-self.a,-self.b,self.d)
 def __sub__(self,x):return self+-self.co(x)
 def __mul__(self,x):x=self.co(x);return Quad(self.a*x.a+self.b*x.b*self.d,self.a*x.b+self.b*x.a,self.d)
 __rmul__=__mul__
 def __eq__(self,x):x=self.co(x);return self.a==x.a and self.b==x.b
 def json(self):return {'rational':str(self.a),'radical_coefficient':str(self.b),'radicand':str(self.d),'root':'positive square root'}

def qmm(X,Y):return [[sum((a*b for a,b in zip(row,col)),Quad(0,0,X[0][0].d)) for col in zip(*Y)] for row in X]

def dump(X):return [[v.json() for v in row] for row in X]

def certify_G(s):
 s=Q(s);_require(s>0, 'verification invariant failed');d=3*s/32;q=lambda a=0,b=0:Quad(a,b,d);I=[[q(1),q()],[q(),q(1)]]
 states=[[[q(1),q()],[q(),q()]],[[q(Q(1,4)),q(0,Q(1,4))],[q(0,8/s),q(Q(3,4))]],[[q(Q(1,4)),q(0,Q(-1,4))],[q(0,-8/s),q(Q(3,4))]]]
 states +=[qadd(I,qscale(R,-1)) for R in states.copy()]
 for R in states:
  _require(qmm(R,R)==R and qtrace(R)==1 and R[0][0]*R[1][1]-R[0][1]*R[1][0]==0, 'verification invariant failed')
  _require(32*R[0][1]==s*R[1][0], 'verification invariant failed') # G-self-adjoint
 expected=[[1,Q(1,4),Q(1,4)],[Q(1,4),1,Q(1,4)],[Q(1,4),Q(1,4),1],[0,Q(3,4),Q(3,4)],[Q(3,4),0,Q(3,4)],[Q(3,4),Q(3,4),0]]
 table=[[qtrace(qmm(R,E)) for E in states[:3]] for R in states]
 _require(all(v==expected[i][j] for i,row in enumerate(table) for j,v in enumerate(row)), 'verification invariant failed')
 mixtures=[[(i,Q(1,2)),(i+3,Q(1,2))] for i in range(3)]+[[(i,Q(1,3)) for i in range(3)],[(i,Q(1,3)) for i in range(3,6)]]
 for mix in mixtures:
  out=[[q(),q()],[q(),q()]]
  for i,w in mix:out=qadd(out,qscale(states[i],w))
  _require(out==qscale(I,Q(1,2)), 'verification invariant failed')
 # Independently check same table/identities in ordinary orthonormal frame s=32.
 if s!=32:
  orth=certify_G(Q(32));_require(orth['YES_table_exact']==qserial(expected), 'verification invariant failed')
 return {'status':'PASS','G':[['32','0'],['0',str(s)]],'exact_radicand':str(d),'states_and_sharp_yes_effects':[dump(R) for R in states],'YES_table_exact':qserial(expected),'five_mixture_identities':qserial(mixtures),'projector_roots':True,'all_projectors_trace1_idempotent_G_adjoint':True,'transformation':'S=diag(sqrt32,sqrt(s)); R_G=S^-1 R_orth S. upper offdiag=sign sqrt(3s/32)/4, lower=32/s*upper. Every expression multiplied in Q[sqrt(3s/32)], sqrt positive. This is exact conjugacy with the external real trine, not a new state or test.','real_positivity':'Positive G inner product (32,s>0); conjugacy to orthonormal real projectors proves PSD, not just trace/determinant.'}

qadd=add
qscale=scale
qtrace=trace

def qserial(x):
 if isinstance(x,Q):return str(x)
 if isinstance(x,dict):return {str(k):qserial(v) for k,v in x.items()}
 if isinstance(x,(tuple,list)):return [qserial(v) for v in x]
 return x
