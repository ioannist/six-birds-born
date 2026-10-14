"""Declared ray transport, explicit coefficients; no induced-K assertion."""
from .arithmetic import *
class Transport:
    def __init__(self,context,w,s,projector,kernel):
        self.x,self.w,self.ss,self.P,self.K=context,w,s,projector,kernel;self.n=len(self.w)
        self.K2=mm(self.K,self.K)
        self.coeff={}
        for name,A in [('K',self.K),('K2',self.K2)]:
            self.coeff[name]=[(sum(row),2*sum(a*b for a,b in zip(row,self.w)),sum(a*b*b for a,b in zip(row,self.w))) for row in transpose(A)]
        self.c=Q(self.n)/self.ss;self.kappa=self.ss/self.n
    def encode(self,p):
        if len(p)!=len(self.w):raise ValueError('encoder vector dimension')
        p=list(map(Q,p))
        if any(v<0 for v in p) or not any(p):raise ValueError('nonzero nonnegative encoder vector required')
        pivot=next(v for v in p if v>0)
        ratios=[exact_sqrt(v/pivot) for v in p]
        if all(v is not None for v in ratios):
            # The common sqrt(pivot) cancels exactly in the homogeneous chart.
            return I(self.c*sum(w*r for w,r in zip(self.w,ratios))/sum(ratios))
        roots=[I(v).sqrt() for v in p]
        return self.c*isum(v*r for v,r in zip(self.w,roots))/isum(roots)
    def poly(self,abc,l):
        a,b,c=abc
        def f(z):return a+b*z+c*z*z
        vals=[f(l.lo),f(l.hi)]
        if c and l.lo<=-b/(2*c)<=l.hi:vals.append(f(-b/(2*c)))
        return outward(min(vals),max(vals))
    def g(self,l,operation='K',derivative=False,reciprocal=False):
        l=asI(l);cs=self.coeff[operation]
        if reciprocal:cs=[(c,b,a) for a,b,c in cs]
        roots=[self.poly(abc,l).sqrt() for abc in cs]
        S=isum(roots);T=isum(w*r for w,r in zip(self.w,roots));value=self.c*T/S
        if not derivative:return value
        dr=[]
        for (a,b,c),root in zip(cs,roots):
            if c and b*b==4*a*c:
                # Exact rank-one polynomial: sqrt(q)=sqrt(c)*abs(l+b/(2c)).
                # At its cusp use an enclosing generalized derivative for Lipschitz bounds.
                at=-b/(2*c);slope=I(c).sqrt()
                dr.append(slope if l.lo>at else -slope if l.hi<at else I(-slope.hi,slope.hi))
            elif a==b==c==0:
                dr.append(I(0))
            else:
                dr.append((b+2*c*l)/(2*root))
        Sd=isum(dr);Td=isum(w*r for w,r in zip(self.w,dr))
        d=self.c*(Td*S-T*Sd)/S.square()
        if reciprocal:
            # d g/d lambda and infinitesimal angular gain at u=1/lambda.
            angular=d.abs()*(l.square()+self.kappa)/(1+self.kappa*value.square())
            dl=-l.square()*d
        else:
            dl=d;angular=d.abs()*(1+self.kappa*l.square())/(1+self.kappa*value.square())
        return value,dl,angular
    def infinity(self,operation='K'):return self.g(I(0),operation,reciprocal=True)
    def ray_prob(self,l):
        l=asI(l);norm=self.n+self.ss*l.square()
        return [(1+w*l).square()/norm for w in self.w]
    def distance(self,a,b):
        a=asI(a);b=asI(b)
        return (self.n*self.ss*(a-b).square()/((self.n+self.ss*a.square())*(self.n+self.ss*b.square()))).sqrt()
    def readout(self,l,field='joint_by_state'):
        p=self.ray_prob(l);q=self.x['lens'][field];return [isum(p[i] for i in range(self.n) if q[i]==j) for j in range(max(q)+1)]
    def readout_tv(self,a,b,field='joint_by_state'):
        return isum((s-t).abs() for s,t in zip(self.readout(a,field),self.readout(b,field)))/2
    def propagate(self,p,operation='K'):
        if len(p)!=self.n:raise ValueError('transport vector dimension')
        if operation not in ('K','K2'):raise ValueError('undeclared transport operation')
        return mv(transpose(self.K if operation=='K' else self.K2),p)
    def ru(self,p):
        q=self.x['lens']['joint_by_state'];return [sum(p[i] for i in range(self.n) if q[i]==j) for j in range(max(q)+1)]
