"""Independent planted Test B processes; no estimator or scorer imports."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

BLOCK_IDS=np.arange(910001,910036,dtype=np.int64)


def rng(domain:str,*parts) -> np.random.Generator:
    label='TestB/v4/'+domain+'/'+('/'.join(map(str,parts)))
    seed=int.from_bytes(hashlib.sha256(label.encode('utf-8')).digest()[:16],'little')
    return np.random.default_rng(seed)


def stochastic(shape,gen):
    alpha=gen.uniform(.5,2.0,size=shape)
    return np.stack([gen.dirichlet(row) for row in alpha.reshape(-1,shape[-1])]).reshape(shape)


def sample_rows(gen,matrix,source):
    cdf=np.cumsum(matrix,axis=1)
    return np.minimum(np.sum(gen.random(len(source))[:,None]>cdf[np.asarray(source)],axis=1),matrix.shape[1]-1)


def dimensions(domain,index,m=None,r=None):
    gen=rng(domain,'dimensions',index)
    if m is None:m=int(gen.integers(5,9))
    if r is None:r=int(gen.integers(2,min(5,m)))
    if not 2<=r<m:raise ValueError('rank not below label count')
    return m,r


def qr_frame(gen,m,r):
    q,R=np.linalg.qr(gen.standard_normal((m,r)))
    return q*np.where(np.diag(R)>=0,1,-1)


def amplitude_matrix(gen,r):
    Q,_=np.linalg.qr(gen.standard_normal((r,r)))
    lam=gen.uniform(.3,.9,size=r)*gen.choice([-1.,1.],size=r)
    return Q@np.diag(lam)@Q.T


def square_law(U,A,u,times=8):
    z=np.sqrt(u)@U
    laws=[]
    for _ in range(times):
        z=z@A.T
        y=(z@U.T)**2
        total=y.sum(axis=-1,keepdims=True)
        if np.any(total<1e-24):raise ValueError('undefined square normalization')
        laws.append(y/total)
    return np.stack(laws,axis=1)


def clipped_law(U,A,u,times=8):
    z=u@U;laws=[]
    for _ in range(times):
        z=z@A.T;y=np.maximum(z@U.T,0)
        total=y.sum(axis=-1,keepdims=True)
        if np.any(total<1e-24):raise ValueError('undefined clipped normalization')
        laws.append(y/total)
    return np.stack(laws,axis=1)


def calibration_and_paths(domain,index,true_u,laws):
    """32 paths for every recipe/block; independent row-wise draws for distribution plants."""
    m=len(true_u[0]);calibration={};labels=np.empty((35,24,32,9),dtype=np.int16)
    for a in range(24):
        calibration[a]=rng(domain,'Y0cal',index,a).choice(m,size=256,p=true_u[a]).astype(np.int64)
        for bi,b in enumerate(BLOCK_IDS):
            gen=rng(domain,'paths',index,int(b),a)
            labels[bi,a,:,0]=gen.choice(m,size=32,p=true_u[a])
            for t in range(8):labels[bi,a,:,t+1]=gen.choice(m,size=32,p=laws[a,t])
    return calibration,labels


@dataclass
class Plant:
    family:str
    index:int
    m:int
    r:int
    calibration:dict[int,np.ndarray]
    paths:np.ndarray
    true_u:np.ndarray
    laws:np.ndarray
    audit:dict
    parameters:dict


def quadratic(index:int,domain='preflight',m=None,r=None) -> Plant:
    m,r=dimensions(domain,index,m,r);gen=rng(domain,'parameters',index)
    U=qr_frame(gen,m,r);A=amplitude_matrix(gen,r)
    alpha=gen.uniform(.5,2.0,size=(24,m))
    true_u=np.stack([gen.dirichlet(row) for row in alpha])
    laws=square_law(U,A,true_u)
    calibration,paths=calibration_and_paths(domain,index,true_u,laws)
    return Plant('quadratic',index,m,r,calibration,paths,true_u,laws,
                 {'C':0.0,'L':0.0,'semantic':'time-indexed record-distribution'},
                 {'U':U,'A':A,'alpha':alpha})


def clipped_linear(index:int,domain='main_clipped',m=None,r=None) -> Plant:
    m,r=dimensions(domain,index,m,r);gen=rng(domain,'parameters',index)
    U=qr_frame(gen,m,r);A=amplitude_matrix(gen,r)
    alpha=gen.uniform(.5,2.0,size=(24,m));true_u=np.stack([gen.dirichlet(row) for row in alpha])
    laws=clipped_law(U,A,true_u)
    calibration,paths=calibration_and_paths(domain,index,true_u,laws)
    return Plant('clipped_linear',index,m,r,calibration,paths,true_u,laws,
                 {'C':0.0,'L':0.0,'semantic':'time-indexed record-distribution'},
                 {'U':U,'A':A,'alpha':alpha})


def ed(index:int,domain='main_ed',m=None,r=None,k=None) -> Plant:
    m,r=dimensions(domain,index,m,r);k=r if k is None else k
    gen=rng(domain,'parameters',index)
    E=stochastic((m,k),gen);D=stochastic((k,m),gen);T=E@D
    alpha=gen.uniform(.5,2.0,size=(24,m));true_u=np.stack([gen.dirichlet(row) for row in alpha])
    z=true_u.copy();laws=[]
    for _ in range(8):z=z@T;laws.append(z)
    laws=np.stack(laws,axis=1)
    calibration={};paths=np.empty((35,24,32,9),dtype=np.int16)
    for a in range(24):
        calibration[a]=rng(domain,'Y0cal',index,a).choice(m,size=256,p=true_u[a])
        for bi,b in enumerate(BLOCK_IDS):
            sample=rng(domain,'paths',index,int(b),a)
            y=sample.choice(m,size=32,p=true_u[a]);paths[bi,a,:,0]=y
            for t in range(64):
                y=sample_rows(sample,T,y)
                if t<8:paths[bi,a,:,t+1]=y
    return Plant('ed',index,m,r,calibration,paths,true_u,laws,
                 {'C':0.0,'L':0.0,'semantic':'fixed label kernel'},
                 {'E':E,'D':D,'T':T,'k':k,'alpha':alpha})


def hmm(index:int,domain='main_hmm',m=None,r=None,h=1) -> Plant:
    m,r=dimensions(domain,index,m,r);gen=rng(domain,'parameters',index)
    E=stochastic((m,r),gen);T=stochastic((r,r),gen);D=stochastic((r,m),gen)
    alpha=gen.uniform(.5,2.0,size=(24,m));true_u=np.stack([gen.dirichlet(row) for row in alpha])
    z=true_u@E;laws=[]
    for micro_step in range(1,65):
        ylaw=z@D
        if micro_step%h==0 and micro_step//h<=8:laws.append(ylaw)
        z=z@T
    laws=np.stack(laws,axis=1)
    calibration={};paths=np.empty((35,24,32,9),dtype=np.int16)
    for a in range(24):
        calibration[a]=rng(domain,'Y0cal',index,a).choice(m,size=256,p=true_u[a])
        for bi,b in enumerate(BLOCK_IDS):
            sample=rng(domain,'paths',index,int(b),a)
            y=sample.choice(m,size=32,p=true_u[a]);paths[bi,a,:,0]=y
            hidden=sample_rows(sample,E,y)
            for micro_step in range(1,65):
                y=sample_rows(sample,D,hidden)
                hidden=sample_rows(sample,T,hidden)
                if micro_step%h==0 and micro_step//h<=8:
                    paths[bi,a,:,micro_step//h]=y
    # The fixed hidden/label chain is audited for preparation-relative closure by runner.
    return Plant('hmm',index,m,r,calibration,paths,true_u,laws,
                 {'semantic':'fixed hidden/label chain','C':None},
                 {'E':E,'T':T,'D':D,'alpha':alpha,'h':h})


def split_state(index:int,domain='main_split',m=None,r=None):
    m,r=dimensions(domain,index,m,r);gen=rng(domain,'parameters',index)
    K=np.zeros((2*m,2*m));dvals=[]
    for a in range(m):
        b1,b2=gen.choice(m,size=2,replace=False)
        w=gen.dirichlet(gen.uniform(.5,2.0,size=m))
        d=float(gen.uniform(.2,.4));dvals.append(d)
        K[2*a,0::2]=(1-d)*w+d*np.eye(m)[b1]
        K[2*a+1,1::2]=(1-d)*w+d*np.eye(m)[b2]
    q=np.repeat(np.arange(m),2)
    # Same label-level recipe pattern, both hidden regimes equally weighted.
    recipes=[]
    for a in range(24):
        labels=[a%m,(a+7)%m,(a+19)%m]
        recipes.append([2*y+bit for y in labels for bit in (0,1)])
    return {'family':'split_state','index':index,'m':m,'r':r,'K':K,'q':q,
            'recipes':recipes,'d':dvals,'semantic':'fixed micro kernel'}
