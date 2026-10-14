"""Frozen Test B numerical inference; read-only, no model fitting."""
import math
import numpy as np

FLOOR = 1e-12

def scoring_probability(p):
    p=np.maximum(np.asarray(p,dtype=float),FLOOR)
    return p/p.sum(axis=-1,keepdims=True)


def excess_log_loss(oracle,pred):
    pstar=np.asarray(oracle,dtype=float);pred=scoring_probability(pred)
    positive=pstar>0
    return float(np.sum(pstar[positive]*np.log(pstar[positive]/pred[positive])))


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
