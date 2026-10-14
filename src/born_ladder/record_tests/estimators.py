"""Record-only Test B models. This module has no audit-file entry point.

The only filesystem loader accepts files named and hashed by a filtered
training/validation manifest. Synthetic plants may construct RecordData in memory.
"""
from __future__ import annotations

import hashlib
import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Set defaults before the first native import. Public production routing pins
# these values before process startup; an incompatible preloaded Torch runtime
# is refused rather than resized after an OpenMP/autograd pool exists.
for _thread_key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):
    os.environ.setdefault(_thread_key,'1')

import numpy as np
import torch
from scipy.optimize import minimize

if torch.get_num_threads()!=1:
    raise ValueError('Test B requires OMP_NUM_THREADS=1 and MKL_NUM_THREADS=1 before importing Torch; re-execute the process')
DT = torch.float64
FLOOR = 1e-12
CHECKPOINTS = (25, 50, 100, 200, 500)
SPEC_HASH = 'ee9be77e2dcfc308e31f31f2a97622d4c81db79c729ce328e796813d727896e0'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _split(recipe: int, block: int, design: str = 'v5') -> str:
    train_end, valid_end = (36, 48) if design == 'v6' else (12, 18)
    if design not in ('v5', 'v6'):
        raise ValueError('unknown Test B record design')
    if recipe < train_end and 910001 <= block <= 910010:
        return 'train'
    if train_end <= recipe < valid_end and 910011 <= block <= 910015:
        return 'validation'
    raise ValueError('path outside frozen training/validation cells')


class RecordAllowlist:
    def __init__(self, manifest_path: Path):
        manifest_path = Path(manifest_path).resolve(strict=True)
        self.root = manifest_path.parent
        self.manifest = json.loads(manifest_path.read_bytes())
        self.design = {'test_b_trainval_manifest_v1': 'v5',
                       'test_b_v6_trainval_manifest_v1': 'v6'}.get(self.manifest['schema'])
        if self.design is None:
            raise ValueError('wrong manifest schema')
        if self.design == 'v6' and self.manifest.get('spec_sha256') != '3abc68c6f0a8070240a2302434b28644fbf8b67f955a65af2cf33667cfd6d2cd':
            raise ValueError('wrong frozen v6 specification')
        for entry in self.manifest['allowed_files']:
            name=entry['file']
            if Path(name).name!=name or not name.endswith('.json') or '.audit.' in name or '.record.' in name:
                raise PermissionError('manifest names must be filtered record basenames')
        self.allowed = {str((self.root / x['file']).resolve(strict=True)): x for x in self.manifest['allowed_files']}
        if len(self.allowed) != len(self.manifest['allowed_files']):
            raise ValueError('duplicate allowlist path')
        if any(Path(path).parent!=self.root for path in self.allowed):
            raise PermissionError('manifest path escapes filtered record directory')

    def load(self, path: Path) -> 'RecordData':
        path = Path(path).resolve(strict=True)
        item = self.allowed.get(str(path))
        if item is None or '.audit.' in path.name or '.record.' in path.name:
            raise PermissionError('record path absent from filtered manifest')
        payload = path.read_bytes()
        if sha(payload) != item['sha256']:
            raise ValueError('record file hash mismatch')
        raw = json.loads(payload)
        expected_schema = 'test_b_v6_trainval_context_v1' if self.design == 'v6' else 'test_b_trainval_context_v1'
        if raw.get('schema') != expected_schema:
            raise ValueError('wrong filtered record schema')
        if set(raw)!={'schema','exp','config','k','step_index','h_c','m','map_sha256','calibration','paths'}:
            raise ValueError('filtered record has extra or missing fields')
        identity = (raw['exp'], raw['config'], raw['k'], raw['step_index'], raw['h_c'], raw['m'])
        expected = (item['exp'], item['config'], item['k'], item['step_index'], item['h_c'], item['m'])
        if identity != expected or raw['schema'] != expected_schema:
            raise ValueError('record context mismatch')
        if self.design == 'v6' and raw['map_sha256'] != item['map_sha256']:
            raise ValueError('record label map differs from v6 census')
        m = raw['m']
        calibration = {int(k): np.asarray(v, dtype=np.int64) for k,v in raw['calibration'].items()}
        calibration_draws = 8192 if self.design == 'v6' else 256
        recipe_count = 60 if self.design == 'v6' else 18
        if set(calibration) != set(range(recipe_count)) or any(len(v) != calibration_draws or np.any((v<0)|(v>=m)) for v in calibration.values()):
            raise ValueError('bad calibration table')
        rows = raw['paths']
        if len(rows) != (13440 if self.design == 'v6' else 4800):
            raise ValueError('wrong path count')
        labels, recipes, blocks, reps = [], [], [], []
        seen = set()
        for row in rows:
            a,b,rep = row['recipe'],row['block'],row['replicate']
            split = _split(a,b,self.design)
            if row['split'] != split or row['selected_h'] != raw['h_c'] or (row['k'],row['step_index']) != (raw['k'],raw['step_index']):
                raise ValueError('undeclared split, interval or context')
            ys = np.asarray(row['labels'],dtype=np.int64)
            if len(ys) != 9 or np.any((ys<0)|(ys>=m)) or not 0 <= rep < 32:
                raise ValueError('bad record readings')
            key = (b,a,rep)
            if key in seen:
                raise ValueError('duplicate trajectory')
            seen.add(key)
            labels.append(ys);recipes.append(a);blocks.append(b);reps.append(rep)
        if sum(1 for a in recipes if a < (36 if self.design == 'v6' else 12)) != (11520 if self.design == 'v6' else 3840):
            raise ValueError('wrong training count')
        return RecordData(m,calibration,np.asarray(labels),np.asarray(recipes),np.asarray(blocks),np.asarray(reps),
                          context=f"{raw['exp']}::{raw['config']}::k{raw['k']}::s{raw['step_index']}",
                          design=self.design)


@dataclass
class RecordData:
    m: int
    calibration: dict[int,np.ndarray]
    labels: np.ndarray
    recipes: np.ndarray
    blocks: np.ndarray
    replicates: np.ndarray
    context: str
    design: str = 'v5'

    def canonical(self, original_ids: np.ndarray | None = None) -> 'CanonicalData':
        ids = np.arange(self.m) if original_ids is None else np.asarray(original_ids)
        if sorted(ids.tolist()) != list(range(self.m)):
            raise ValueError('original label IDs must be a permutation')
        train_count = 36 if self.design == 'v6' else 12
        calibration_draws = 8192 if self.design == 'v6' else 256
        train = np.flatnonzero((self.recipes<train_count)&(self.blocks>=910001)&(self.blocks<=910010))
        order_rows = sorted(train,key=lambda i:(self.blocks[i],self.recipes[i],self.replicates[i]))
        freq = np.zeros(self.m,dtype=np.int64)
        first = np.full(self.m,np.iinfo(np.int64).max,dtype=np.int64)
        pos = 0
        for i in order_rows:
            for y in self.labels[i]:
                freq[y] += 1
                if first[y] == np.iinfo(np.int64).max:first[y]=pos
                pos += 1
        perm = np.array(sorted(range(self.m),key=lambda j:(-freq[j],first[j],ids[j])),dtype=np.int64)
        inv = np.argsort(perm)
        labels = inv[self.labels]
        u = {}
        for a,ys in self.calibration.items():
            u[a]=np.bincount(inv[ys],minlength=self.m).astype(float)/calibration_draws
        table = [(int(self.blocks[i]),int(self.recipes[i]),int(self.replicates[i]),labels[i].tolist()) for i in order_rows]
        table_hash=sha(json.dumps(table,separators=(',',':')).encode())
        return CanonicalData(self.m,u,labels,self.recipes.copy(),self.blocks.copy(),self.replicates.copy(),
                             perm,inv,self.context,table_hash,
                             train_recipe_count=train_count,
                             validation_recipe_count=12 if self.design == 'v6' else 6)


@dataclass
class CanonicalData:
    m: int
    u: dict[int,np.ndarray]
    labels: np.ndarray
    recipes: np.ndarray
    blocks: np.ndarray
    replicates: np.ndarray
    to_original: np.ndarray
    from_original: np.ndarray
    context: str
    table_hash: str
    fold_train_blocks: tuple[int,...]|None=None
    fold_validation_blocks: tuple[int,...]|None=None
    train_recipe_count: int=12
    validation_recipe_count: int=6

    def counts(self, split: Literal['train','validation'], only_t1=False, reverse=False):
        if self.fold_train_blocks is not None:
            recipes=range(self.train_recipe_count)
            blocks=self.fold_train_blocks if split=='train' else self.fold_validation_blocks
        else:
            recipes = range(self.train_recipe_count) if split=='train' else range(self.train_recipe_count,self.train_recipe_count+self.validation_recipe_count)
            blocks = range(910001,910011) if split=='train' else range(910011,910016)
        cells=np.zeros((len(recipes),8,self.m),dtype=float)
        for ai,a in enumerate(recipes):
            mask=(self.recipes==a)&np.isin(self.blocks,list(blocks))
            y=self.labels[mask,1:]
            if reverse:y=y[:,::-1]
            for t in range(8):
                if only_t1 and t:continue
                cells[ai,t]=np.bincount(y[:,t],minlength=self.m)
        u=np.stack([self.u[a] for a in recipes])
        return u,cells

    def transport(self,pred: np.ndarray) -> np.ndarray:
        result=np.empty_like(pred)
        result[...,self.to_original]=pred
        return result


def parameter_counts(m:int,r:int,kind:str,k:int|None=None) -> dict:
    cap=m*r-r*(r+1)//2+r*r
    if kind in ('square','linear','a_identity','reverse','b1','random_mode'):
        raw=cap if kind not in ('a_identity','random_mode') else (m*r-r*(r+1)//2 if kind=='a_identity' else r*r)
        return {'raw':raw,'effective':m*r-1 if kind in ('square','linear','reverse','b1') else raw,'cap':cap}
    k=r if k is None else k
    if kind=='ed':count=m*(k-1)+k*(m-1)
    elif kind=='hmm':count=m*(k-1)+k*(k-1)+k*(m-1)
    elif kind=='markov':count=m*(m-1)
    elif kind=='constant':count=m-1
    else:raise ValueError(kind)
    return {'raw':count,'effective':count,'cap':cap}


def capped_classical(m:int,r:int) -> list[tuple[str,int]]:
    cap=parameter_counts(m,r,'square')['cap']
    return [('linear',r)]+[(kind,k) for kind in ('ed','hmm') for k in range(1,r+1)
                            if parameter_counts(m,r,kind,k)['raw']<=cap]


def _seed(*parts) -> int:
    blob='TestB/v4/fit/'+ '/'.join(map(str,parts))
    return int.from_bytes(hashlib.sha256(blob.encode()).digest()[:8],'little')


def _control_seed(*parts) -> int:
    blob='TestB/v5/control/'+ '/'.join(map(str,parts))
    return int.from_bytes(hashlib.sha256(blob.encode()).digest()[:8],'little')


def _qr(raw:torch.Tensor) -> torch.Tensor:
    q,r=torch.linalg.qr(raw,mode='reduced')
    sign=torch.where(torch.diagonal(r)>=0,1.0,-1.0)
    return q*sign


def _softmax_rows(x:torch.Tensor) -> torch.Tensor:
    return torch.softmax(x,dim=-1)


def _size(kind,m,r,k):
    if kind in ('square','linear','reverse','b1'):return m*r+r*r
    if kind=='a_identity':return m*r
    if kind=='random_mode':return r*r
    if kind=='ed':return m*k+k*m
    if kind=='hmm':return m*k+k*k+k*m
    if kind=='markov':return m*m
    raise ValueError(kind)


def _pred_torch(theta:torch.Tensor,kind:str,u:torch.Tensor,m:int,r:int,k:int,times:int=8,fixed_u=None):
    if kind in ('square','linear','reverse','b1','a_identity','random_mode'):
        if kind=='random_mode':
            U=fixed_u
            A=theta.reshape(r,r)
        else:
            U=_qr(theta[:m*r].reshape(m,r))
            A=torch.eye(r,dtype=DT) if kind=='a_identity' else theta[m*r:].reshape(r,r)
        if kind!='a_identity':A=A/torch.linalg.vector_norm(A).clamp_min(1e-12)
        z=(torch.sqrt(u) if kind!='linear' else u)@U
        predictions=[]
        for t in range(1,times+1):
            if kind!='a_identity':z=z@A.T
            y=z@U.T
            if kind=='linear':
                positive=torch.clamp(y,min=0.0)
                total=positive.sum(dim=-1,keepdim=True)
                p=torch.where(total>0,positive/total.clamp_min(1e-30),torch.full_like(positive,1/m))
            else:
                amp=y.square();p=amp/amp.sum(dim=-1,keepdim=True).clamp_min(1e-30)
            predictions.append(p)
        pred=torch.stack(predictions,dim=1)
        if kind=='b1':pred=pred[:,0:1,:].expand(-1,times,-1)
        return pred
    if kind=='ed':
        E=_softmax_rows(theta[:m*k].reshape(m,k));D=_softmax_rows(theta[m*k:].reshape(k,m))
        T=E@D;z=u;pred=[]
        for _ in range(times):z=z@T;pred.append(z)
        return torch.stack(pred,dim=1)
    if kind=='hmm':
        E=_softmax_rows(theta[:m*k].reshape(m,k));T=_softmax_rows(theta[m*k:m*k+k*k].reshape(k,k));D=_softmax_rows(theta[m*k+k*k:].reshape(k,m))
        z=u@E;pred=[]
        for _ in range(times):pred.append(z@D);z=z@T
        return torch.stack(pred,dim=1)
    if kind=='markov':
        M=_softmax_rows(theta.reshape(m,m));z=u;pred=[]
        for _ in range(times):z=z@M;pred.append(z)
        return torch.stack(pred,dim=1)
    raise ValueError(kind)


def score_probability(p:np.ndarray) -> np.ndarray:
    p=np.maximum(p,FLOOR)
    return p/p.sum(axis=-1,keepdims=True)


def _loss(pred:torch.Tensor,counts:torch.Tensor) -> torch.Tensor:
    p=pred.clamp_min(FLOOR)
    return -(counts*torch.log(p)).sum()/counts.sum().clamp_min(1.0)


@dataclass
class Fit:
    kind:str
    rank:int
    k:int
    m:int
    theta:np.ndarray|None
    train_loss:float
    validation_loss:float
    iteration:int
    failed:bool
    fixed_u:np.ndarray|None=None
    orientation:np.ndarray|None=None
    metadata:dict|None=None

    def predict(self,u:np.ndarray,times=8):
        u=np.asarray(u,dtype=float)
        if u.ndim==1:u=u[None,:]
        if self.kind=='constant':return np.broadcast_to(self.theta,(len(u),times,self.m)).copy()
        fixed=None if self.fixed_u is None else torch.as_tensor(self.fixed_u,dtype=DT)
        with torch.no_grad():
            p=_pred_torch(torch.as_tensor(self.theta,dtype=DT),self.kind,torch.as_tensor(u,dtype=DT),self.m,self.rank,self.k,times,fixed).numpy()
        if self.kind=='diagonal':raise RuntimeError('use diagonal_predict')
        return p


def _optimize(kind,data:CanonicalData,r:int,k:int,train_u,train_counts,val_u,val_counts,tag:str,
              fixed_u=None,starts=16,maxiter=500) -> Fit:
    m=data.m; size=_size(kind,m,r,k)
    tu=torch.as_tensor(train_u,dtype=DT);tc=torch.as_tensor(train_counts,dtype=DT)
    vu=torch.as_tensor(val_u,dtype=DT);vc=torch.as_tensor(val_counts,dtype=DT)
    fu=None if fixed_u is None else torch.as_tensor(fixed_u,dtype=DT)
    best=None
    for start in range(starts):
        seed=(_control_seed(tag,kind,data.table_hash,data.context,r,k,start)
              if kind in ('a_identity','reverse','b1')
              else _seed(SPEC_HASH,tag,kind,data.table_hash,data.context,r,k,start))
        rng=np.random.default_rng(seed)
        x0=rng.standard_normal(size)*0.5
        history=[]; recent=[]
        def fun(x):
            theta=torch.tensor(x,dtype=DT,requires_grad=True)
            obj=_loss(_pred_torch(theta,kind,tu,m,r,k,fixed_u=fu),tc)
            obj.backward()
            return float(obj.detach()),theta.grad.detach().numpy().astype(float)
        def callback(x):
            iteration=len(history)+1
            if iteration in CHECKPOINTS:
                with torch.no_grad():
                    pred=_pred_torch(torch.as_tensor(x,dtype=DT),kind,vu,m,r,k,fixed_u=fu)
                    val=float(_loss(pred,vc))
                history.append((iteration,x.copy(),val))
            else:history.append((iteration,None,None))
            if iteration>1:
                prev=recent[-1]
                now=fun(x)[0]
                rel=abs(now-prev)/max(1.0,abs(prev))
                recent.append(now)
                if len(recent)>11:recent.pop(0)
                if len(recent)==11 and all(abs(recent[i+1]-recent[i])/max(1.0,abs(recent[i]))<1e-9 for i in range(10)):
                    raise _Stop(x.copy())
            else:recent.append(fun(x)[0])
        stopped=False
        try:
            opt=minimize(fun,x0,method='L-BFGS-B',jac=True,callback=callback,
                         options={'maxiter':maxiter,'gtol':1e-7,'ftol':0.0,'maxls':20,'maxcor':10})
            x=opt.x; failed=not opt.success and opt.status not in (1,)
        except _Stop as exc:
            x=exc.x;stopped=True;failed=False
        tr=fun(x)[0]
        with torch.no_grad():v=float(_loss(_pred_torch(torch.as_tensor(x,dtype=DT),kind,vu,m,r,k,fixed_u=fu),vc))
        if not history or history[-1][1] is None:history.append((len(history),x.copy(),v))
        checkpoints=[h for h in history if h[1] is not None]
        chosen=min(checkpoints,key=lambda h:(h[2],h[0]))
        fit=Fit(kind,r,k,m,chosen[1],tr,chosen[2],chosen[0],failed,
                None if fixed_u is None else np.asarray(fixed_u),metadata={'start':start,'stopped_relative':stopped})
        if best is None or (fit.train_loss,start)<(best.train_loss,best.metadata['start']):best=fit
    return best


V5_STARTS = 96
V5_WARM_ITER = 200
V5_POLISH_ITER = 500


def _symmetric_pred(theta:torch.Tensor,u:torch.Tensor,m:int,r:int,epsilon:float):
    U=_qr(theta[:m*r].reshape(m,r))
    lam=theta[m*r:]
    lam=lam/torch.linalg.vector_norm(lam).clamp_min(1e-12)
    z=torch.sqrt(u)@U
    result=[]
    for _ in range(8):
        z=z*lam
        y=z@U.T
        y=y/torch.linalg.vector_norm(y,dim=-1,keepdim=True).clamp_min(1e-30)
        q=y.square()+epsilon
        result.append(q/q.sum(dim=-1,keepdim=True))
        z=z/torch.linalg.vector_norm(z,dim=-1,keepdim=True).clamp_min(1e-30)
    return torch.stack(result,dim=1)


def _v5_late_candidates(u:np.ndarray,counts:np.ndarray,m:int):
    """Training-only rank-two sign enumeration; no generator parameters."""
    freq=counts/counts.sum(axis=-1,keepdims=True).clip(min=1)
    root=np.sqrt(freq)
    late=freq[:,6:8].mean(axis=(0,1))
    amplitude=np.sqrt(late)
    amplitude/=np.linalg.norm(amplitude)
    candidates=[]
    tu=torch.as_tensor(u,dtype=DT)
    tc=torch.as_tensor(counts,dtype=DT)
    for bit in range(1<<(m-1)):
        signs=np.ones(m)
        for j in range(1,m):signs[j]=1. if ((bit>>(j-1))&1)==0 else -1.
        v1=signs*amplitude
        global_sign=np.where(np.sqrt(u)@v1>=0,1.,-1.)
        signed=global_sign[:,None,None]*signs[None,None,:]*root
        segment=signed[:,2:]
        residual=segment-np.einsum('atm,m->at',segment,v1)[:,:,None]*v1
        _,_,vh=np.linalg.svd(residual.reshape(-1,m),full_matrices=False)
        v2=vh[0]-v1*(vh[0]@v1)
        v2/=np.linalg.norm(v2)
        U=np.column_stack([v1,v2])
        for q in np.linspace(-.95,.95,77):
            if abs(q)<.02:continue
            theta=np.r_[U.ravel(),np.diag([1.,q]).ravel()]
            with torch.no_grad():
                p=_pred_torch(torch.as_tensor(theta,dtype=DT),'square',tu,m,2,2)
                score=float(_loss(p,tc))
            candidates.append((score,bit,float(q),theta))
    best=[];seen=set();chosen=set()
    ordered=sorted(candidates,key=lambda x:(x[0],x[1],x[2]))
    for item in ordered:
        if item[1] not in seen:
            best.append(item[3]);seen.add(item[1]);chosen.add((item[1],item[2]))
            if len(best)==16:break
    if len(best)<16:
        for item in ordered:
            key=(item[1],item[2])
            if key in chosen:continue
            best.append(item[3]);chosen.add(key)
            if len(best)==16:break
    return best


def _v5_spectral_start(kind:str,counts:np.ndarray,m:int,r:int,k:int,rng:np.random.Generator):
    """One of 16 starts from the training frequency second moment."""
    freq=counts/counts.sum(axis=-1,keepdims=True).clip(min=1)
    root=np.sqrt(freq) if kind=='square' else freq
    second=root.reshape(-1,m).T@root.reshape(-1,m)
    _,vectors=np.linalg.eigh(second)
    width=r if kind in ('square','linear') else k
    U=vectors[:,-width:][:,::-1].copy()
    U=U@np.linalg.qr(rng.standard_normal((width,width)))[0]
    if kind=='square':
        lam=rng.uniform(.3,.9,r)*rng.choice([-1.,1.],r)
        return np.r_[U.ravel(),lam]
    if kind=='linear':
        return np.r_[U.ravel(),rng.standard_normal(r*r)*.5]
    logits=np.log(np.abs(U)+.05)
    encoder=logits+rng.standard_normal((m,k))*.2
    decoder=logits.T+rng.standard_normal((k,m))*.2
    if kind=='ed':return np.r_[encoder.ravel(),decoder.ravel()]
    transition=rng.standard_normal((k,k))*.2
    return np.r_[encoder.ravel(),transition.ravel(),decoder.ravel()]


def _v5_fit(kind:str,data:CanonicalData,r:int,k:int,starts:int,maxiter:int)->Fit:
    if starts!=V5_STARTS or maxiter!=V5_POLISH_ITER:
        raise ValueError('v5 confirmatory budget is frozen at 96 starts and 500 polish iterations')
    m=data.m
    train_u,train_counts=data.counts('train')
    val_u,val_counts=data.counts('validation')
    tu=torch.as_tensor(train_u,dtype=DT);tc=torch.as_tensor(train_counts,dtype=DT)
    vu=torch.as_tensor(val_u,dtype=DT);vc=torch.as_tensor(val_counts,dtype=DT)
    target=tc/tc.sum(dim=-1,keepdim=True).clamp_min(1)
    late=_v5_late_candidates(train_u,train_counts,m) if kind=='square' and r==2 else []
    best=None
    invalid_starts=0
    line_search_failures=0
    for start in range(starts):
        rng=np.random.default_rng(_seed('v5',kind,data.table_hash,data.context,r,k,start))
        if kind=='square':
            if r==2 and 64<=start<80:
                x=late[start-64].copy();analytic=True
            elif start>=80 and r!=2:
                x=_v5_spectral_start(kind,train_counts,m,r,k,rng);analytic=False
            else:
                x=np.r_[rng.standard_normal(m*r)*.5,
                        rng.uniform(.3,.9,r)*rng.choice([-1.,1.],r)]
                analytic=False
        else:
            x=(_v5_spectral_start(kind,train_counts,m,r,k,rng) if start>=80
               else rng.standard_normal(_size(kind,m,r,k))*.5)
            analytic=False
        def objective(y,phase,epsilon=0.):
            th=torch.tensor(y,dtype=DT,requires_grad=True)
            if phase=='symmetric':pred=_symmetric_pred(th,tu,m,r,epsilon)
            else:pred=_pred_torch(th,kind,tu,m,r,k)
            if phase in ('symmetric','polish'):
                obj=_loss(pred,tc)
            else:
                obj=(1-torch.sum(torch.sqrt(target)*torch.sqrt(pred.clamp_min(1e-12)),dim=-1)).mean()
            obj.backward()
            return float(obj.detach()),th.grad.detach().numpy().astype(float)
        if kind=='square':
            if not analytic:
                for eps in (.10,.03,.01,.003,0.):
                    opt=minimize(lambda y:objective(y,'symmetric',eps),x,method='L-BFGS-B',jac=True,
                                 options={'maxiter':V5_WARM_ITER//5,'gtol':1e-7,'ftol':1e-10,'maxls':20,'maxcor':10})
                    x=opt.x
                    line_search_failures+=int(opt.status==2)
                with torch.no_grad():U=_qr(torch.as_tensor(x[:m*r].reshape(m,r),dtype=DT)).numpy()
                x=np.r_[U.ravel(),np.diag(x[m*r:]).ravel()]
        else:
            opt=minimize(lambda y:objective(y,'warm'),x,method='L-BFGS-B',jac=True,
                         options={'maxiter':V5_WARM_ITER,'gtol':1e-7,'ftol':1e-10,'maxls':20,'maxcor':10})
            x=opt.x
            line_search_failures+=int(opt.status==2)
        opt=minimize(lambda y:objective(y,'polish'),x,method='L-BFGS-B',jac=True,
                     options={'maxiter':maxiter,'gtol':1e-7,'ftol':1e-10,'maxls':20,'maxcor':10})
        x=opt.x
        line_search_failures+=int(opt.status==2)
        if not np.all(np.isfinite(x)):
            invalid_starts+=1
            continue
        tr=objective(x,'polish')[0]
        if not np.isfinite(tr):
            invalid_starts+=1
            continue
        if best is None or (tr,start)<(best[0],best[1]):best=(tr,start,x.copy(),opt.nit)
    if best is None:
        raise RuntimeError('all v5 optimizer starts invalid')
    tr,start,x,nit=best
    with torch.no_grad():val=float(_loss(_pred_torch(torch.as_tensor(x,dtype=DT),kind,vu,m,r,k),vc))
    return Fit(kind,r,k,m,x,tr,val,nit,invalid_starts/starts>.01,
               metadata={'start':start,'budget':'v5-96x200+500',
                         'invalid_starts':invalid_starts,'line_search_failures':line_search_failures,
                         'initialization_candidates':((1<<(m-1))*76 if kind=='square' and r==2 else 16),
                         'initialization_candidate_cap':(1<<(m-1))*77})


class _Stop(Exception):
    def __init__(self,x):self.x=x


def fit_model(kind:str,data:CanonicalData,r:int,k:int|None=None,starts=V5_STARTS,maxiter=V5_POLISH_ITER) -> Fit:
    k=r if k is None else k
    if kind in ('square','linear','ed','hmm'):
        return _v5_fit(kind,data,r,k,starts,maxiter)
    train_u,train_counts=data.counts('train',only_t1=kind=='b1',reverse=kind=='reverse')
    val_u,val_counts=data.counts('validation')
    if kind=='constant':
        counts=train_counts.sum(axis=(0,1));p=counts/counts.sum()
        val=-float((val_counts*np.log(score_probability(p))).sum()/val_counts.sum())
        tr=-float((train_counts*np.log(score_probability(p))).sum()/train_counts.sum())
        return Fit(kind,r,k,data.m,p,tr,val,0,False)
    if kind=='random_mode':
        rng=np.random.default_rng(_seed(SPEC_HASH,'random_mode',data.table_hash,data.context,r))
        fixed_u=np.linalg.qr(rng.standard_normal((data.m,r)))[0]
    else:fixed_u=None
    return _optimize(kind,data,r,k,train_u,train_counts,val_u,val_counts,'fit',fixed_u,starts,maxiter)


def diagonal_predict(square:Fit,R:np.ndarray,u:np.ndarray) -> np.ndarray:
    m,r=square.m,square.rank
    theta=torch.as_tensor(square.theta,dtype=DT)
    U=_qr(theta[:m*r].reshape(m,r)).detach().numpy()
    A=theta[m*r:].reshape(r,r).detach().numpy();A=A/np.linalg.norm(A)
    u=np.asarray(u);u=u[None,:] if u.ndim==1 else u
    z=np.sqrt(u)@U
    UR=U@R;pred=[]
    for _ in range(8):
        z=z@A.T;zr=z@R
        p=(zr*zr)@(UR*UR).T
        pred.append(p/p.sum(axis=1,keepdims=True))
    return np.stack(pred,axis=1)


def fit_diagonal(square:Fit,data:CanonicalData,starts=16,maxiter=500) -> Fit:
    r=square.rank
    train_u,counts=data.counts('train');val_u,vcounts=data.counts('validation')
    best=None
    for s in range(starts):
        rng=np.random.default_rng(_control_seed('diagonal',data.table_hash,data.context,r,s))
        x0=rng.standard_normal(r*r)
        def fun(x):
            x_t=torch.tensor(x,dtype=DT,requires_grad=True)
            R=_qr(x_t.reshape(r,r))
            m=square.m
            th=torch.as_tensor(square.theta,dtype=DT)
            U=_qr(th[:m*r].reshape(m,r)).detach()
            A=th[m*r:].reshape(r,r);A=A/torch.linalg.vector_norm(A)
            z=torch.as_tensor(np.sqrt(train_u),dtype=DT)@U
            UR=U@R;pred=[]
            for _ in range(8):
                z=z@A.T;zr=z@R
                p=zr.square()@(UR*UR).T
                pred.append(p/p.sum(dim=1,keepdim=True).clamp_min(1e-30))
            obj=_loss(torch.stack(pred,dim=1),torch.as_tensor(counts,dtype=DT))
            obj.backward()
            return float(obj.detach()),x_t.grad.detach().numpy()
        recent=[]
        def callback(x):
            recent.append(fun(x)[0])
            if len(recent)>11:recent.pop(0)
            if len(recent)==11 and all(abs(recent[i+1]-recent[i])/max(1.0,abs(recent[i]))<1e-9 for i in range(10)):
                raise _Stop(x.copy())
        try:
            opt=minimize(fun,x0,method='L-BFGS-B',jac=True,callback=callback,
                         options={'maxiter':maxiter,'gtol':1e-7,'ftol':0.0,'maxls':20})
            x=opt.x;iteration=opt.nit;failed=not opt.success and opt.status not in (1,)
        except _Stop as exc:
            x=exc.x;iteration=len(recent);failed=False
        R=_qr(torch.as_tensor(x.reshape(r,r),dtype=DT)).numpy()
        tr=fun(x)[0]
        p=diagonal_predict(square,R,val_u);val=-float((vcounts*np.log(np.maximum(p,FLOOR))).sum()/vcounts.sum())
        serialized=json.dumps(R.tolist(),separators=(',',':'))
        result=Fit('diagonal',r,r,square.m,square.theta,tr,val,iteration,failed,orientation=R,metadata={'start':s,'serialized_R':serialized})
        if best is None or (tr,serialized)<(best.train_loss,best.metadata['serialized_R']):best=result
    return best


def fit_family(data:CanonicalData,r:int,starts=V5_STARTS,maxiter=V5_POLISH_ITER) -> dict:
    fits={}
    for kind,k in capped_classical(data.m,r):fits[f'{kind}{k}']=fit_model(kind,data,r,k,starts,maxiter)
    for kind in ('ed','hmm'):
        key=f'{kind}{r}'
        if key not in fits:fits[key]=fit_model(kind,data,r,r,starts,maxiter)
    for kind in ('square','markov','a_identity','reverse','b1','constant','random_mode'):
        fits[kind]=fit_model(kind,data,r,r,starts,maxiter)
    fits['diagonal']=fit_diagonal(fits['square'],data,starts,maxiter)
    capped=[fits[f'{kind}{k}'] for kind,k in capped_classical(data.m,r)]
    fits['selected_classical']=min(capped,key=lambda f:(f.validation_loss,f.kind,f.k))
    rivals=[fits[k] for k in ('a_identity','reverse','b1','constant')]
    fits['selected_order']=min(enumerate(rivals),key=lambda x:(x[1].validation_loss,x[0]))[1]
    return fits
