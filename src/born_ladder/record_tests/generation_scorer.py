"""Audit-side Test B scoring and frozen block-bootstrap inference.

This module must be run only after a prediction bundle is written and hashed.
It does not import the record estimator or generator modules.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

SPEC_HASH='ee9be77e2dcfc308e31f31f2a97622d4c81db79c729ce328e796813d727896e0'
DRAW_COUNT=200_000
BLOCKS=20
FLOOR=1e-12


def seal_predictions(path:Path, payload:dict) -> dict:
    data=(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    result={'path':str(path.resolve()),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
    path.with_suffix(path.suffix+'.seal.json').write_text(json.dumps(result,sort_keys=True)+'\n')
    return result


def open_sealed_predictions(path:Path) -> dict:
    path=Path(path).resolve(strict=True)
    seal=json.loads(path.with_suffix(path.suffix+'.seal.json').read_text())
    data=path.read_bytes()
    if seal['path']!=str(path) or seal['sha256']!=hashlib.sha256(data).hexdigest():
        raise ValueError('predictions not sealed or hash mismatch')
    return json.loads(data)


def scoring_probability(p):
    p=np.maximum(np.asarray(p,dtype=float),FLOOR)
    return p/p.sum(axis=-1,keepdims=True)


def oracle_law(K:np.ndarray,q:np.ndarray,starts:list[int],h:int,t:int) -> np.ndarray:
    n=len(K);mu=np.zeros(n)
    for s in starts:mu[s]+=1/len(starts)
    mu=mu@np.linalg.matrix_power(K,h*t)
    return np.bincount(q,weights=mu,minlength=int(q.max())+1)


def excess_log_loss(oracle,pred):
    pstar=np.asarray(oracle,dtype=float);pred=scoring_probability(pred)
    positive=pstar>0
    return float(np.sum(pstar[positive]*np.log(pstar[positive]/pred[positive])))


def sampled_loss(pred:np.ndarray,labels:np.ndarray) -> np.ndarray:
    """pred [recipe,time,label], labels [block,recipe,replicate,time]."""
    p=scoring_probability(pred)
    labels=np.asarray(labels,dtype=np.int64)
    if labels.ndim!=4 or labels.shape[2:]!=(32,8):raise ValueError('wrong scored path shape')
    a=np.arange(labels.shape[1])[None,:,None,None]
    t=np.arange(8)[None,None,None,:]
    return -np.log(p[a,t,labels])


def paired_block_statistic(rival_loss,square_loss):
    """Input shape [context,20,6,32,8]; equal context/recipe/path/time mean."""
    rival=np.asarray(rival_loss,dtype=float);square=np.asarray(square_loss,dtype=float)
    if rival.shape!=square.shape or rival.ndim!=5 or rival.shape[1:]!=(20,6,32,8):
        raise ValueError('wrong paired loss shape')
    return (rival-square).mean(axis=(0,2,3,4))


def equal_context_mean(context_values):
    values=np.asarray(context_values,dtype=float)
    if values.ndim<1 or len(values)==0:raise ValueError('empty context set')
    return values.mean(axis=0)


def bootstrap_indices(family_id:str,draw_count:int=DRAW_COUNT,cache_dir:Path|None=None):
    if family_id not in ('primary','reversal','order'):raise ValueError(family_id)
    cache=None if cache_dir is None else Path(cache_dir)/f'bootstrap_{family_id}_{draw_count}.npy'
    if cache is not None and cache.exists():
        index=np.load(cache,allow_pickle=False)
        if index.shape!=(draw_count,20) or index.min()<0 or index.max()>19:raise ValueError('bad bootstrap cache')
        return index
    result=np.empty((draw_count,20),dtype=np.uint8)
    ceiling=(1<<64)//20*20
    prefix=f'TestB/v4/bootstrap/{SPEC_HASH}/{family_id}/'
    for k in range(draw_count):
        for i in range(20):
            z=0
            while True:
                x=int.from_bytes(hashlib.sha256(f'{prefix}{k}/{i}/{z}'.encode('ascii')).digest()[:8],'little')
                if x<ceiling:
                    result[k,i]=x%20;break
                z+=1
    if cache is not None:
        cache.parent.mkdir(parents=True,exist_ok=True)
        np.save(cache,result,allow_pickle=False)
    return result


def centered_p(block_values:np.ndarray,d:float,indices:np.ndarray) -> float:
    x=np.asarray(block_values,dtype=np.float64)
    if x.shape!=(20,):raise ValueError('need 20 paired blocks')
    estimate=float(np.mean(x,dtype=np.float64))
    boot=np.mean(x[indices],axis=1,dtype=np.float64)
    # Equality belongs to the tail and counts against rejection.
    return (1+int(np.count_nonzero((boot-estimate)>=(estimate-float(d)))))/(len(indices)+1)


def holm(pvalues:dict[str,float],family_id:str):
    slots={'primary':['D2','G2','D3','G3','D4','G4'],
           'reversal':['R2','R3','R4'],'order':['O2','O3','O4']}[family_id]
    if set(pvalues)!=set(slots):raise ValueError('wrong Holm slots')
    ordered=sorted(slots,key=lambda s:(pvalues[s],slots.index(s)))
    adjusted={};running=0.0;reject={};stopped=False
    M=len(slots)
    for i,s in enumerate(ordered):
        running=max(running,(M-i)*pvalues[s]);adjusted[s]=min(1.0,running)
        if not stopped and pvalues[s]<=0.05/(M-i):reject[s]=True
        else:stopped=True;reject[s]=False
    return {'ordered':ordered,'adjusted':adjusted,'reject':reject}


def lower_bound(x:np.ndarray,indices:np.ndarray,M:int,tolerance=1e-8):
    if M not in (3,6):raise ValueError(M)
    estimate=float(np.mean(np.asarray(x,dtype=np.float64),dtype=np.float64))
    alpha=0.05/M;width=1.0
    low=estimate-width;high=estimate+width
    while centered_p(x,low,indices)>alpha or centered_p(x,high,indices)<=alpha:
        width*=2
        if width>1e12:raise ArithmeticError('failed to bracket bound')
        low=estimate-width;high=estimate+width
    while high-low>=tolerance:
        mid=(low+high)/2
        if centered_p(x,mid,indices)<=alpha:low=mid
        else:high=mid
    return math.floor(low/1e-8)*1e-8


def family_inference(blocks:dict[str,np.ndarray|None],margins:dict[str,float],family_id:str,indices:np.ndarray):
    slots={'primary':['D2','G2','D3','G3','D4','G4'],
           'reversal':['R2','R3','R4'],'order':['O2','O3','O4']}[family_id]
    M=len(slots);p={};bounds={};estimates={}
    for s in slots:
        x=blocks[s]
        if x is None:
            p[s]=1.0;bounds[s]=None;estimates[s]=None;continue
        x=np.asarray(x,dtype=np.float64)
        if family_id=='reversal':
            y=-x
            p[s]=centered_p(y,-margins[s],indices)
            bounds[s]=-lower_bound(y,indices,M)
        else:
            p[s]=centered_p(x,margins[s],indices)
            bounds[s]=lower_bound(x,indices,M)
        estimates[s]=float(x.mean())
    return {'family':family_id,'estimates':estimates,'bounds':bounds,'p_raw':p,
            'holm':holm(p,family_id),'margins':margins,
            'qualification':'nominal simultaneous bounds under bootstrap validity'}


def nearest_95(values):
    values=sorted(map(float,values))
    if not values:raise ValueError('empty C values')
    return values[(95*len(values)+99)//100-1]


def scope_audit(context_values:dict,rank_members:dict[int,list],threshold=0.01):
    result={}
    for r,members in rank_members.items():
        if not members:result[r]={'status':'ineligible'};continue
        c=np.asarray([nearest_95(context_values[key]) for key in members])
        result[r]={'status':'in_scope' if float(c.mean())<=threshold else 'out_of_eligible_scope',
                   'mean_C95':float(c.mean()),'max_C95':float(c.max()),
                   'failing_fraction':float(np.mean(c>threshold)),
                   'context_C95':dict(zip(members,c.tolist()))}
    return result


def signal_audit(oracle_by_context:dict,rank_members:dict[int,list],order_margins:dict[int,float]):
    gains={};constants={}
    for key,law in oracle_by_context.items():
        law=np.asarray(law,dtype=float)
        if law.ndim!=3 or law.shape[0:2]!=(6,8):raise ValueError('oracle must have 6 recipes x 8 times')
        q=law.mean(axis=(0,1));constants[key]=q.tolist()
        gains[key]=float(np.mean([excess_log_loss(p,q) for p in law.reshape(-1,law.shape[-1])]))
    ranks={}
    for r,members in rank_members.items():
        if not members:ranks[r]={'status':'ineligible'};continue
        signal=float(np.mean([gains[key] for key in members]))
        ranks[r]={'signal':signal,'margin':order_margins[r],
                  'status':'informative' if signal>order_margins[r] else 'uninformative_at_selected_lag'}
    return {'context_constants':constants,'context_gains':gains,'ranks':ranks}
