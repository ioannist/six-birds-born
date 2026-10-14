"""One-attempt, synthetic-only Test B v6 certification driver.

Each domain is generated and hash-committed before any fit in that domain.
The driver stops at the first failed validity gate and never deletes cases.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from born_ladder.record_tests.workers import process_pool as ProcessPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from born_ladder.record_tests.test_b_census import closure_deficit, lumpability_defect, nearest_95
from born_ladder.record_tests import estimators as E
from born_ladder.record_tests import generators_v6 as G
from born_ladder.record_tests import generation_scorer as S
from born_ladder.record_tests import scorer_v6 as V

ROOT = None  # configure() supplies the public run's certification output
SPEC = None  # no private specification path
CENSUS = None  # configure() supplies an earlier public stage's release
CENSUS_HASH = None  # actual configured release, not a historical receipt
FAMILIES = ('clipped_linear', 'ed_capped', 'ed_same_rank', 'hmm')
LAGS = (1, 2, 4, 8)
TRAIN_BLOCKS = tuple(range(910001, 910011))
TEST_BLOCKS = tuple(range(910036, 910056))
WORKERS = int(os.environ.get('TESTB_WORKERS', '16'))
if WORKERS < 1:
    raise ValueError('TESTB_WORKERS must be positive')


def cannot_reach_minimum(total: int, processed: int, passed: int, minimum: int) -> bool:
    return processed < total and passed + (total-processed) < minimum


def fidelity_pass(total: int, processed: int, passed: int, minimum: int,
                  invalid_starts: int, start_count: int) -> bool:
    return (processed == total and passed >= minimum and start_count > 0
            and invalid_starts/start_count <= .01)


def rank_claim(nonempty: bool, scope: bool, signal: float, margin: float,
               bounds: dict) -> bool:
    return bool(nonempty and scope and signal>margin
        and bounds['D']>margin and bounds['G']>.01
        and bounds['R']<margin and bounds['O']>margin)


def pseudo_rank_claim(nonempty: bool, scope: bool, signal: float, margin: float,
                      expected: dict, bounds: dict) -> bool:
    return bool(expected['D']>margin and expected['G']>.01
                and expected['R']<margin and expected['O']>margin
                and rank_claim(nonempty, scope, signal, margin, bounds))


def false_square_pass(expected: dict, margins: dict, rank_pass: dict,
                      invalid_fraction: float) -> bool:
    return (not any(expected[r]['D']>margins[r] for r in margins)
            and not any(rank_pass.values()) and invalid_fraction<=.01)


def split_pass(passed: int) -> bool:
    return passed>=95


def pseudo_pass(processed: int, passed: int, invalid_fraction: float) -> bool:
    return processed==100 and passed>=80 and invalid_fraction<=.01


def encoded(obj) -> bytes:
    def convert(x):
        if isinstance(x, np.ndarray): return x.tolist()
        if isinstance(x, np.generic): return x.item()
        raise TypeError(type(x))
    return (json.dumps(obj, sort_keys=True, separators=(',', ':'), default=convert,
                       allow_nan=False) + '\n').encode()


def write_once(path: Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = encoded(obj)
    with path.open('xb') as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    return hashlib.sha256(data).hexdigest()


def write_or_verify(path: Path, obj) -> str:
    data=encoded(obj)
    if path.exists():
        if path.read_bytes()!=data:raise RuntimeError(f'existing artifact differs: {path}')
        return hashlib.sha256(data).hexdigest()
    return write_once(path,obj)


def append(path: Path, obj) -> None:
    with path.open('ab') as out:
        out.write(encoded(obj))
        out.flush()
        os.fsync(out.fileno())


def read_prefix(path: Path, key: str, total: int) -> list[dict]:
    if not path.exists(): return []
    rows=[]
    with path.open('rb') as stream:
        for expected,line in enumerate(stream):
            if not line.endswith(b'\n'):
                raise RuntimeError(f'incomplete saved row in {path}')
            row=json.loads(line)
            if row.get(key)!=expected or encoded(row)!=line:
                raise RuntimeError(f'noncanonical or out-of-order saved row in {path}')
            rows.append(row)
    if len(rows)>total:raise RuntimeError(f'too many saved rows in {path}')
    return rows


def complete_canonical_rows(path: Path, key: str, total: int) -> list[dict]:
    rows=read_prefix(path,key,total)
    if len(rows)!=total:
        raise RuntimeError(f'incomplete canonical result file: {path}')
    return rows


def canonical_document(path: Path):
    raw=path.read_bytes()
    document=json.loads(raw)
    if encoded(document)!=raw:
        raise RuntimeError(f'noncanonical reused artifact: {path}')
    return document


def verify_fidelity_verdict(kind: str, count: int, minimum: int) -> dict:
    path=ROOT/kind/'verdict.json'
    verdict=canonical_document(path)
    rows=complete_canonical_rows(ROOT/kind/'results.jsonl','index',count)
    passed=sum(row['gap']<=.02 for row in rows)
    failed=sum(row['optimizer_failed'] for row in rows)
    invalid=sum(row['invalid_starts'] for row in rows)
    expected={'gate':kind+'_heldout_fidelity',
              'status':'PASS' if fidelity_pass(count,count,passed,minimum,invalid,
                                               count*E.V5_STARTS) else 'FAIL',
              'required':minimum,'total_committed':count,'processed':count,
              'passed':passed,'failed_fits':failed,'invalid_starts':invalid,
              'worst_gap':max(row['gap'] for row in rows),
              'worst_index':max(rows,key=lambda row:row['gap'])['index']}
    if {k:v for k,v in verdict.items() if k!='wall_seconds'}!=expected:
        raise RuntimeError(f'reused fidelity verdict differs from canonical results: {kind}')
    return verdict


def verify_split_verdict() -> dict:
    verdict=canonical_document(ROOT/'split_state'/'verdict.json')
    rows=canonical_document(ROOT/'split_state'/'closure_results.json')
    if len(rows)!=100 or [row['index'] for row in rows]!=list(range(100)):
        raise RuntimeError('incomplete canonical split-state results')
    passed=sum(bool(row['pass']) for row in rows)
    worst=min(rows,key=lambda row:min(row['C95_train'].values()))
    expected={'gate':'split_state_nonclosure','required':95,'passed':passed,
              'status':'PASS' if split_pass(passed) else 'FAIL',
              'worst_case_index':worst['index'],
              'worst_case_min_C95':min(worst['C95_train'].values())}
    if {k:v for k,v in verdict.items() if k!='wall_seconds'}!=expected:
        raise RuntimeError('reused split-state verdict differs from canonical results')
    return verdict


def verify_pseudo_verdict() -> dict:
    verdict=canonical_document(ROOT/'pseudocampaign'/'verdict.json')
    rows=complete_canonical_rows(ROOT/'pseudocampaign'/'campaign_results.jsonl',
                                 'campaign',100)
    passed=sum(bool(row['pass']) for row in rows)
    fit_rows=[fit for row in rows for case in row['cases']
              for fit in case['ranks'].values()]
    failed=sum(row['failed_fits'] for row in fit_rows)
    invalid=sum(row['invalid_starts'] for row in fit_rows)
    starts=sum(row['start_count'] for row in fit_rows)
    fraction=invalid/starts if starts else 0.
    expected={'gate':'census_matched_pseudocampaign',
              'status':'PASS' if pseudo_pass(100,passed,fraction) else 'FAIL',
              'required':80,'committed':100,'processed':100,'passed':passed,
              'census_contexts':len(rows[0]['census_slots']),
              'rank_counts':{str(r):len(rows[0]['membership'][str(r)]) for r in (2,3,4)},
              'failed_fits':failed,'invalid_starts':invalid,'start_count':starts,
              'invalid_start_fraction':fraction}
    if {k:v for k,v in verdict.items() if k!='wall_seconds'}!=expected:
        raise RuntimeError('reused pseudo verdict differs from canonical results')
    return verdict


def complete_ordered_rows(path: Path, items: list, worker, key: str,
                          total: int, saved_rows: list[dict] | None = None) -> list[dict]:
    rows=read_prefix(path,key,total) if saved_rows is None else saved_rows
    if len(rows)==total:return rows
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        for row in pool.map(worker,items[len(rows):]):
            if row.get(key)!=len(rows):raise RuntimeError('worker returned out-of-order row')
            append(path,row)
            rows.append(row)
    return rows


def seal_rank_margins(path: Path, fit_rows: dict[int,dict],
                      members: dict[int,list[int]]) -> str:
    folds={};margins={}
    for rank in (2,3,4):
        group=[fit_rows[i]['ranks'][str(rank)]['folds'] for i in members[rank]]
        if not group:continue
        values=[float(np.mean([case[fold][0] for case in group])) for fold in range(5)]
        folds[str(rank)]=values
        margins[str(rank)]=max(.01,2*float(np.std(values,ddof=1)))
    return write_once(path,{'schema':'test_b_v6_1_sealed_margins_v1',
                            'rank_members':{str(r):members[r] for r in (2,3,4)},
                            'folds':folds,'margins':margins})


def read_sealed_margins(path: Path, expected_sha256: str) -> tuple[dict,dict]:
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=expected_sha256:
        raise RuntimeError('rank margin seal mismatch')
    document=json.loads(data)
    if document.get('schema')!='test_b_v6_1_sealed_margins_v1':
        raise RuntimeError('wrong rank margin schema')
    return ({int(r):float(v) for r,v in document['margins'].items()},
            {int(r):v for r,v in document['folds'].items()})


def sha_array(x: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(x).tobytes()).hexdigest()


def plant(kind: str, index: int, *, paths: bool = True):
    if kind == 'fidelity': return G.quadratic(index, domain='fidelity', paths=paths)
    if kind == 'quadratic': return G.quadratic(index, domain='main/quadratic', paths=paths)
    if kind == 'clipped_linear': return G.clipped_linear(index, domain='main/clipped_linear', paths=paths)
    if kind == 'ed_capped': return G.ed(index, domain='main/ed_capped', paths=paths)
    if kind == 'ed_same_rank': return G.ed(index, domain='main/ed_same_rank', paths=paths)
    if kind == 'hmm': return G.hmm(index, domain='main/hmm', paths=paths)
    if kind == 'split_state': return G.split_state(index, domain='main/split_state')
    raise ValueError(kind)


def draw_digest(p) -> dict:
    if isinstance(p, dict):
        return {'index': p['index'], 'family': 'split_state',
                'parameter_sha256': hashlib.sha256(encoded({k:v for k,v in p.items()
                    if k not in ('initial', 'K', 'calibration', 'paths')})).hexdigest(),
                'kernel_sha256': sha_array(p['K']), 'initial_sha256': sha_array(p['initial']),
                'calibration_sha256':hashlib.sha256(b''.join(p['calibration'][a].tobytes()
                                                    for a in range(60))).hexdigest(),
                'paths_sha256':sha_array(p['paths'])}
    return {'index': p.index, 'family': p.family, 'm': p.m, 'r': p.r,
            'parameter_sha256': hashlib.sha256(encoded(p.parameters)).hexdigest(),
            'true_u_sha256': sha_array(p.true_u),
            'calibration_sha256': hashlib.sha256(b''.join(p.calibration[a].tobytes()
                                                        for a in range(60))).hexdigest(),
            'paths_sha256': None if p.paths is None else sha_array(p.paths),
            'kernel_sha256': None if p.kernel is None else sha_array(p.kernel)}


def commit_domain(name: str, count: int) -> list[dict]:
    folder = ROOT / name
    folder.mkdir(parents=True, exist_ok=False)
    rows = [draw_digest(plant(name, i)) for i in range(count)]
    digest = write_once(folder / 'draw_commitment.json', rows)
    print('COMMITTED', name, count, digest, flush=True)
    return rows


def plant_readings(p: G.V6Plant, h: int) -> np.ndarray:
    # Distribution-level plants have no micro clock; one generated successor is
    # one reading at their declared context lag.
    return p.readings(1 if p.kernel is None else h)


def plant_marginals(p: G.V6Plant, h: int) -> np.ndarray:
    return p.marginals(1 if p.kernel is None else h)


def record(p: G.V6Plant, h: int) -> E.CanonicalData:
    labels, recipes, blocks, reps = [], [], [], []
    times=np.arange(9)*(h if p.kernel is not None else 1)
    for bi, b in enumerate(G.BLOCK_IDS):
        for a in range(48):
            if not G.valid_cell(b, a): continue
            for rep in range(32):
                raw=p.paths[bi,a,rep,times]
                labels.append(raw if p.q is None else p.q[raw])
                recipes.append(a); blocks.append(b); reps.append(rep)
    raw = E.RecordData(p.m, p.calibration, np.asarray(labels), np.asarray(recipes),
                       np.asarray(blocks), np.asarray(reps),
                       f'v6::{p.domain}::{p.index}::h{h}', design='v6')
    return raw.canonical()


def expected_excess(laws: np.ndarray, pred: np.ndarray) -> float:
    if laws.shape != pred.shape or laws.shape[0:2] != (12, 8):
        raise ValueError('wrong exact expected-loss shape')
    return float(np.mean([S.excess_log_loss(laws[a,t], pred[a,t])
                          for a in range(12) for t in range(8)]))


def fit_failure(fit: E.Fit) -> tuple[int, int]:
    invalid = int((fit.metadata or {}).get('invalid_starts', 0))
    return int(fit.failed), invalid


def fidelity_case(item: tuple[int, dict, str]) -> dict:
    index, committed, kind = item
    started = time.monotonic()
    p = plant(kind, index)
    if draw_digest(p) != committed: raise RuntimeError('fidelity draw hash mismatch')
    audit = fixed_census(p,include_test=False) if p.kernel is not None else None
    h = 1 if audit is None or audit['selected_h'] is None else audit['selected_h']
    d = record(p, h)
    model = {'fidelity':'square', 'clipped_linear':'linear',
             'ed_capped':'ed', 'ed_same_rank':'ed', 'hmm':'hmm'}[kind]
    k = p.parameters.get('k', p.r)
    fit = E.fit_model(model, d, p.r, k)
    u = np.stack([d.u[a] for a in range(48, 60)])
    predictions = d.transport(fit.predict(u))
    if not np.all(np.isfinite(predictions)):
        raise RuntimeError('nonfinite fitted predictions')
    prediction_path = ROOT / kind / f'case_{index:03d}_predictions.json'
    S.seal_predictions(prediction_path, {'kind':kind, 'index':index,
                                           'predictions':predictions.tolist()})
    sealed = np.asarray(S.open_sealed_predictions(prediction_path)['predictions'])
    laws = plant_marginals(p,h)[48:60]
    known = p.true_predictions(d.transport(u), h)
    fitted_excess = expected_excess(laws, sealed)
    known_excess = expected_excess(laws, known)
    failed, invalid = fit_failure(fit)
    return {'index':index, 'family':kind, 'm':p.m, 'r':p.r, 'k':k,
            'h':h, 'C95_train':None if audit is None else audit['C95_train'],
            'fitted_excess':fitted_excess, 'true_calibration_excess':known_excess,
            'gap':fitted_excess-known_excess, 'optimizer_failed':failed,
            'invalid_starts':invalid, 'fit_count':1, 'start_count':E.V5_STARTS,
            'normalization_attempt':p.parameters.get('attempt', 0),
            'normalization_rejections':p.parameters.get('rejections',[]),
            'optimizer_metadata':fit.metadata,'train_objective':fit.train_loss,
            'validation_objective':fit.validation_loss,
            'prediction_sha256':hashlib.sha256(prediction_path.read_bytes()).hexdigest(),
            'worker_seconds':time.monotonic()-started}


def fidelity_gate(kind: str, count: int, minimum: int,
                  commitments: list[dict] | None = None,
                  early_stop: bool = True, resume: bool = False) -> dict:
    if commitments is None:
        commitments = commit_domain(kind, count)
    result_path = ROOT / kind / 'results.jsonl'
    begin = time.monotonic()
    saved=read_prefix(result_path,'index',count) if resume else []
    processed=len(saved)
    passes=sum(row['gap']<=.02 for row in saved)
    failures=sum(row['optimizer_failed'] for row in saved)
    invalid=sum(row['invalid_starts'] for row in saved)
    batches=() if early_stop and cannot_reach_minimum(count,processed,passes,minimum) \
            else range(processed,count,WORKERS)
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        for first in batches:
            batch = list(pool.map(fidelity_case,
                ((i, commitments[i], kind) for i in range(first, min(first+WORKERS, count)))))
            for row in batch:
                append(result_path, row)
                processed += 1
                passes += row['gap'] <= .02
                failures += row['optimizer_failed']
                invalid += row['invalid_starts']
            print('FIDELITY', kind, processed, 'pass', passes, 'worst',
                  round(max(x['gap'] for x in batch), 5), flush=True)
            if early_stop and cannot_reach_minimum(count,processed,passes,minimum):
                break
    rows = [json.loads(line) for line in result_path.read_text().splitlines()]
    verdict = {'gate':kind+'_heldout_fidelity', 'status':'PASS' if fidelity_pass(
               count,processed,passes,minimum,invalid,processed*E.V5_STARTS) else 'FAIL',
               'required':minimum, 'total_committed':count, 'processed':processed,
               'passed':passes, 'failed_fits':failures, 'invalid_starts':invalid,
               'worst_gap':max(row['gap'] for row in rows),
               'worst_index':max(rows,key=lambda row:row['gap'])['index'],
               'wall_seconds':time.monotonic()-begin}
    write_once(ROOT / kind / 'verdict.json', verdict)
    return verdict


def fixed_census(p, include_test: bool = True) -> dict:
    kernel = p['K'] if isinstance(p, dict) else p.kernel
    q = p['q'] if isinstance(p, dict) else p.q
    initial = p['initial'] if isinstance(p, dict) else p.initial_micro
    if kernel is None or q is None or initial is None:
        raise ValueError('fixed-chain closure audit needs micro kernel and initials')
    m = int(q.max())+1
    incidence = np.eye(m)[q]
    lags = {}
    for h in LAGS:
        kh = np.linalg.matrix_power(kernel, h)
        rows = kh @ incidence
        recipe_count=60 if include_test else 36
        mu = initial[:recipe_count].copy()
        values = np.empty((recipe_count, 8), dtype=float)
        for t in range(8):
            for a in range(recipe_count):
                values[a,t] = closure_deficit(mu[a], q, rows)
            mu = mu @ kh
        lags[str(h)] = {'C95_train':nearest_95(values[:36].ravel()),
                        'C95_test':nearest_95(values[48:].ravel()) if include_test else None,
                        'L':lumpability_defect(q, rows),
                        'C_by_recipe_time':values.tolist()}
    selected = next((h for h in LAGS if lags[str(h)]['C95_train']<=.01), None)
    return {'lags':lags, 'selected_h':selected,
            'C95_train':{str(h):lags[str(h)]['C95_train'] for h in LAGS}}


def control_census(p: G.V6Plant, include_test: bool = True) -> dict:
    if p.kernel is not None:
        return fixed_census(p,include_test=include_test)
    # A declared distribution-level classical law has the record itself as its
    # state, so C=L=0 and its one reading interval is h=1.
    zeros=[[0.]*8 for _ in range(60 if include_test else 36)]
    lags={str(h):{'C95_train':0.,'C95_test':0. if include_test else None,
                  'L':0.,'C_by_recipe_time':zeros} for h in LAGS}
    return {'lags':lags,'selected_h':1,'C95_train':{str(h):0. for h in LAGS}}


def fold_record(d: E.CanonicalData, fold: int) -> tuple[E.CanonicalData, tuple[int,int]]:
    held = (910001+2*fold, 910002+2*fold)
    kept = tuple(b for b in TRAIN_BLOCKS if b not in held)
    inner_train, inner_valid = kept[:6], kept[6:]
    mask = np.isin(d.blocks, inner_train) & (d.recipes < 36)
    ids = sorted(np.flatnonzero(mask),
                 key=lambda i:(d.blocks[i], d.recipes[i], d.replicates[i]))
    frequency=np.zeros(d.m,dtype=np.int64)
    first=np.full(d.m,np.iinfo(np.int64).max,dtype=np.int64)
    position=0
    for i in ids:
        for y in d.labels[i]:
            frequency[y]+=1
            if first[y]==np.iinfo(np.int64).max:first[y]=position
            position+=1
    permutation=np.array(sorted(range(d.m),key=lambda j:(-frequency[j],first[j],
                                  d.to_original[j])),dtype=np.int64)
    inverse=np.argsort(permutation)
    labels=inverse[d.labels]
    to_original=d.to_original[permutation]
    table = [(int(d.blocks[i]),int(d.recipes[i]),int(d.replicates[i]),
              labels[i].tolist()) for i in ids]
    digest = hashlib.sha256(json.dumps(table,separators=(',',':')).encode()).hexdigest()
    return replace(d, labels=labels, u={a:vector[permutation] for a,vector in d.u.items()},
                   to_original=to_original, from_original=np.argsort(to_original),
                   fold_train_blocks=inner_train, fold_validation_blocks=inner_valid,
                   table_hash=digest), held


def label_loss(pred: np.ndarray, labels: np.ndarray) -> np.ndarray:
    probability = S.scoring_probability(pred)
    a = np.arange(labels.shape[1])[None,:,None,None]
    t = np.arange(8)[None,None,None,:]
    return -np.log(probability[a,t,labels])


def fold_contrast(p: G.V6Plant, d: E.CanonicalData, h: int, rank: int,
                  fold: int) -> tuple[float,int,int,int]:
    folded, held = fold_record(d, fold)
    models = E.fit_family(folded, rank)
    u = np.stack([folded.u[a] for a in range(36)])
    square = folded.transport(models['square'].predict(u))
    classical = folded.transport(models['selected_classical'].predict(u))
    times=np.arange(1,9)*(h if p.kernel is not None else 1)
    raw=p.paths[np.ix_([b-910001 for b in held],range(36),range(32),times)]
    labels=raw if p.q is None else p.q[raw]
    contrast = float((label_loss(classical, labels)-label_loss(square, labels)).mean())
    fits = [f for name,f in models.items() if not name.startswith('selected_')]
    return (contrast, sum(f.failed for f in fits),
            sum((f.metadata or {}).get('invalid_starts',0) for f in fits),
            (len(fits)-1)*E.V5_STARTS)


def seal_or_verify_prediction(path: Path, payload: dict) -> str:
    # A killed worker may have sealed predictions before its ordered fit row
    # was appended. Existing prediction bytes and their seal are immutable.
    if path.exists() or path.with_suffix(path.suffix+'.seal.json').exists():
        if not path.exists() or S.open_sealed_predictions(path)!=payload:
            raise RuntimeError(f'regenerated prediction differs from orphan seal: {path}')
        if path.read_bytes()!=encoded(payload):
            raise RuntimeError(f'regenerated prediction bytes differ: {path}')
        return hashlib.sha256(path.read_bytes()).hexdigest()
    return S.seal_predictions(path,payload)['sha256']


def fit_seal_case(p: G.V6Plant, d: E.CanonicalData, rank: int,
                  namespace: str) -> dict:
    models = E.fit_family(d, rank)
    u = np.stack([d.u[a] for a in range(48,60)])
    predictions = {}
    for name, fit in models.items():
        if name.startswith('selected_'): continue
        pred = E.diagonal_predict(models['square'], fit.orientation, u) if name=='diagonal' \
               else fit.predict(u)
        predictions[name] = d.transport(pred).tolist()
    predictions['selected_classical'] = d.transport(models['selected_classical'].predict(u)).tolist()
    predictions['selected_order'] = d.transport(models['selected_order'].predict(u)).tolist()
    path = ROOT / namespace / f'case_{p.index}_r{rank}_predictions.json'
    payload={'namespace':namespace,'case':p.index,'rank':rank,
             'predictions':predictions}
    prediction_sha=seal_or_verify_prediction(path,payload)
    actual = [f for name,f in models.items() if not name.startswith('selected_')]
    optimizer={name:{'failed':fit.failed,'train_objective':fit.train_loss,
                     'validation_objective':fit.validation_loss,'metadata':fit.metadata}
               for name,fit in models.items() if not name.startswith('selected_')}
    return {'failed_fits':sum(f.failed for f in actual),
            'invalid_starts':sum((f.metadata or {}).get('invalid_starts',0) for f in actual),
            'fit_count':len(actual),'start_count':(len(actual)-1)*E.V5_STARTS,
            'prediction_sha256':prediction_sha,
            'selected_classical':(models['selected_classical'].kind,models['selected_classical'].k),
            'selected_order':models['selected_order'].kind,
            'optimizer_by_model':optimizer}


def score_sealed_case(p: G.V6Plant, h: int, rank: int, namespace: str,
                      fit_meta: dict) -> dict:
    path = ROOT / namespace / f'case_{p.index}_r{rank}_predictions.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=fit_meta['prediction_sha256']:
        raise RuntimeError('prediction differs from pre-test fit seal')
    sealed = S.open_sealed_predictions(path)['predictions']
    labels = plant_readings(p,h)[15:35,48:60,:,1:9]
    laws = plant_marginals(p,h)[48:60]
    losses = {name:V.sampled_loss(np.asarray(pred),labels) for name,pred in sealed.items()}
    expected = {name:expected_excess(laws,np.asarray(pred)) for name,pred in sealed.items()}
    contrasts = {'D':(losses['selected_classical']-losses['square']).mean(axis=(1,2,3)),
                 'G':(losses['diagonal']-losses['square']).mean(axis=(1,2,3)),
                 'R':(losses['square']-losses[f'ed{rank}']).mean(axis=(1,2,3)),
                 'O':(losses['selected_order']-losses['square']).mean(axis=(1,2,3))}
    return {'contrasts':contrasts,'expected':expected,'law':laws,
            'sampled_mean_loss':{name:float(loss.mean()) for name,loss in losses.items()},
            **fit_meta}


def main_case_fit_package(item: tuple[str,int,dict,list[int],int]) -> dict:
    kind,index,committed,ranks,selected_h = item
    p = plant(kind,index)
    if draw_digest(p)!=committed: raise RuntimeError('main draw hash mismatch')
    audit = control_census(p,include_test=False)
    if audit['selected_h']!=selected_h: raise RuntimeError('selected lag changed after commitment')
    if not ranks: return {'index':index,'ranks':{}}
    d = record(p,selected_h)
    output={}
    for rank in ranks:
        meta=fit_seal_case(p,d,rank,kind)
        folds=[fold_contrast(p,d,selected_h,rank,f) for f in range(5)]
        output[str(rank)]={'fit_meta':meta,'folds':folds}
    return {'index':index,'ranks':output}


def main_case_score_package(item: tuple[str,int,dict,list[int],int,dict,str]) -> dict:
    kind,index,committed,ranks,selected_h,fit_row,margin_sha=item
    read_sealed_margins(ROOT/kind/'rank_margins.json',margin_sha)
    p=plant(kind,index)
    if draw_digest(p)!=committed or fit_row['index']!=index:
        raise RuntimeError('main score draw or fit commitment mismatch')
    output={}
    test_audit=control_census(p,include_test=True)
    for rank in ranks:
        prior=fit_row['ranks'][str(rank)]
        result=score_sealed_case(p,selected_h,rank,kind,prior['fit_meta'])
        fold=prior['folds']
        gain, _ = V.signal([result['law']])
        output[str(rank)] = {
            'contrasts':{k:v.tolist() for k,v in result['contrasts'].items()},
            'expected':result['expected'],
            'sampled_mean_loss':result['sampled_mean_loss'],
            'folds':[x[0] for x in fold],
            'scope_C95_test':test_audit['lags'][str(selected_h)]['C95_test'],
            'signal':gain,
            'oracle_pooled_constant':result['law'].mean(axis=(0,1)).tolist(),
            'selected_classical':result['selected_classical'],
            'selected_order':result['selected_order'],
            'failed_fits':result['failed_fits']+sum(x[1] for x in fold),
            'invalid_starts':result['invalid_starts']+sum(x[2] for x in fold),
            'fit_count':result['fit_count']*6,
            'start_count':result['start_count']+sum(x[3] for x in fold),
            'prediction_sha256':result['prediction_sha256']}
        output[str(rank)]['optimizer_by_model']=result['optimizer_by_model']
    return {'index':index,'ranks':output}


def synthetic_census_commit(kind: str, commitments: list[dict],
                            resume: bool = False) -> tuple[list[dict],dict[int,list[int]]]:
    rows=[];members={r:[] for r in (2,3,4)}
    for i,committed in enumerate(commitments):
        p=plant(kind,i,paths=False)
        hash_no_paths=draw_digest(p)
        if any(hash_no_paths[k]!=committed[k] for k in hash_no_paths if k!='paths_sha256'):
            raise RuntimeError('audit parameters differ from committed draw')
        audit=control_census(p,include_test=False)
        rank=[r for r in (2,3,4) if audit['selected_h'] is not None and p.m>r]
        for r in rank: members[r].append(i)
        rows.append({'index':i,'m':p.m,'r_generator':p.r,'selected_h':audit['selected_h'],
                     'C95_train':audit['C95_train'],
                     'rank_membership':rank,
                     'L':{str(h):audit['lags'][str(h)]['L'] for h in LAGS},
                     'C_by_training_recipe_time':{str(h):audit['lags'][str(h)]['C_by_recipe_time'][:36]
                                         for h in LAGS}})
    writer=write_or_verify if resume else write_once
    writer(ROOT/kind/'closure_census.json',rows)
    writer(ROOT/kind/'rank_sets.json',{str(r):members[r] for r in members})
    return rows,members


def inventory_orphan_seals(kind: str, saved_count: int,
                           by_case: dict[int,list[int]]) -> dict[tuple[int,int],str]:
    folder=ROOT/kind
    pattern=re.compile(r'case_(\d+)_r([234])_predictions\.json(?:\.seal\.json)?$')
    seen={}
    for path in folder.glob('case_*_r*_predictions.json*'):
        match=pattern.fullmatch(path.name)
        if match is None:
            raise RuntimeError(f'unrecognized prediction artifact: {path}')
        i,r=map(int,match.groups())
        if i>=100 or r not in by_case[i]:
            raise RuntimeError(f'unexpected orphan prediction seal: {path}')
        if i>=saved_count:
            seen.setdefault((i,r),set()).add(path.suffixes[-2:] == ['.seal','.json'])
    orphans={}
    for (i,r),parts in seen.items():
        if parts!={False,True}:
            raise RuntimeError(f'incomplete orphan prediction seal: {kind}/{i}/r{r}')
        path=folder/f'case_{i}_r{r}_predictions.json'
        payload=S.open_sealed_predictions(path)
        if (payload.get('namespace'),payload.get('case'),payload.get('rank'))!=(kind,i,r):
            raise RuntimeError(f'orphan prediction header differs: {path}')
        if path.read_bytes()!=encoded(payload):
            raise RuntimeError(f'noncanonical orphan prediction: {path}')
        orphans[i,r]=hashlib.sha256(path.read_bytes()).hexdigest()
    return orphans


def verify_pooled_verdict(kind: str) -> dict:
    folder=ROOT/kind
    verdict=canonical_document(folder/'pooled_verdict.json')
    members=canonical_document(folder/'rank_sets.json')
    census=canonical_document(folder/'closure_census.json')
    if len(census)!=100 or [row['index'] for row in census]!=list(range(100)):
        raise RuntimeError(f'incomplete canonical pooled census: {kind}')
    if verdict['status']=='INELIGIBLE':
        if kind!='hmm' or any(members[str(r)] for r in (2,3,4)):
            raise RuntimeError('reused HMM ineligibility differs from census')
        return verdict
    if verdict['gate']==kind+'_positive_eligibility':
        eligible=len(set().union(*(set(members[str(r)]) for r in (2,3,4))))
        if kind not in ('ed_capped','ed_same_rank') or eligible>=80 or \
           verdict['eligible_any_rank']!=eligible or verdict['status']!='FAIL':
            raise RuntimeError('reused eligibility verdict differs from census')
        return verdict
    fits=complete_canonical_rows(folder/'pooled_fits.jsonl','index',100)
    cases=complete_canonical_rows(folder/'pooled_cases.jsonl','index',100)
    seal=canonical_document(folder/'pooled_fit_seal.json')
    if seal['case_count']!=100 or seal['fit_rows_sha256']!=hashlib.sha256(
            (folder/'pooled_fits.jsonl').read_bytes()).hexdigest():
        raise RuntimeError('reused pooled fit seal differs from canonical fits')
    margin_sha=hashlib.sha256((folder/'rank_margins.json').read_bytes()).hexdigest()
    if verdict['margin_sha256']!=margin_sha:
        raise RuntimeError('reused pooled margin differs from seal')
    failed=invalid=starts=fit_count=0
    for i,(fit,case) in enumerate(zip(fits,cases)):
        if set(fit['ranks'])!=set(case['ranks']):
            raise RuntimeError(f'reused pooled rank set differs: {kind}/{i}')
        for rank,row in case['ranks'].items():
            if row['prediction_sha256']!=fit['ranks'][rank]['fit_meta']['prediction_sha256']:
                raise RuntimeError(f'reused pooled prediction seal differs: {kind}/{i}/r{rank}')
            failed+=row['failed_fits'];invalid+=row['invalid_starts']
            starts+=row['start_count'];fit_count+=row['fit_count']
    fraction=invalid/starts if starts else 0.
    expected={'gate':kind+'_pooled_false_square',
              'status':'PASS' if false_square_pass(verdict['expected'],verdict['margins'],
                                                   verdict['rank_pass'],fraction) else 'FAIL',
              'rank_counts':{str(r):len(members[str(r)]) for r in (2,3,4)},
              'fit_count':fit_count,'failed_fits':failed,'invalid_starts':invalid,
              'start_count':starts,'invalid_start_fraction':fraction}
    for key,value in expected.items():
        if verdict.get(key)!=value:
            raise RuntimeError(f'reused pooled verdict differs from canonical results: {kind}/{key}')
    return verdict


def pooled_false_square(kind: str, commitments: list[dict], resume: bool = False) -> dict:
    started=time.monotonic()
    audits,members=(synthetic_census_commit(kind,commitments,resume=True) if resume else
                    synthetic_census_commit(kind,commitments))
    if kind.startswith('ed') and len(set().union(*[set(x) for x in members.values()]))<80:
        verdict={'gate':kind+'_positive_eligibility','status':'FAIL',
                 'eligible_any_rank':len(set().union(*[set(x) for x in members.values()])),
                 'wall_seconds':time.monotonic()-started}
        write_once(ROOT/kind/'pooled_verdict.json',verdict)
        return verdict
    if kind=='hmm' and not any(members.values()):
        verdict={'gate':'hmm_pooled_false_square','status':'INELIGIBLE',
                 'rank_counts':{'2':0,'3':0,'4':0},
                 'primary_slots':{slot:{'p':1.,'bound':None} for slot in
                                  ('D2','G2','D3','G3','D4','G4')},
                 'reversal_slots':{slot:{'p':1.,'bound':None} for slot in ('R2','R3','R4')},
                 'order_slots':{slot:{'p':1.,'bound':None} for slot in ('O2','O3','O4')},
                 'meaning':'no observed negative square result; neutral main component',
                 'wall_seconds':time.monotonic()-started}
        write_once(ROOT/kind/'pooled_verdict.json',verdict)
        return verdict
    selected={x['index']:x['selected_h'] for x in audits}
    by_case={i:[r for r in (2,3,4) if i in members[r]] for i in range(100)}
    result_path=ROOT/kind/'pooled_cases.jsonl'
    fit_path=ROOT/kind/'pooled_fits.jsonl'
    saved=read_prefix(fit_path,'index',100) if resume else []
    if resume:
        for row in saved:
            i=row['index']
            if draw_digest(plant(kind,i))!=commitments[i]:
                raise RuntimeError(f'saved fit row draw differs from commitment: {kind}/{i}')
            if set(row['ranks'])!=set(map(str,by_case[i])):
                raise RuntimeError(f'saved rank membership differs: {kind}/{i}')
            for rank,entry in row['ranks'].items():
                if len(entry['folds'])!=5:raise RuntimeError('incomplete saved fold set')
                path=ROOT/kind/f'case_{i}_r{rank}_predictions.json'
                if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['fit_meta']['prediction_sha256']:
                    raise RuntimeError(f'saved prediction differs: {kind}/{i}/r{rank}')
                S.open_sealed_predictions(path)
        orphans=inventory_orphan_seals(kind,len(saved),by_case)
    if resume:
        items=[(kind,i,commitments[i],by_case[i],selected[i]) for i in range(100)]
        ordered=complete_ordered_rows(fit_path,items,main_case_fit_package,'index',100,saved)
        for (i,r),digest in orphans.items():
            if ordered[i]['ranks'][str(r)]['fit_meta']['prediction_sha256']!=digest:
                raise RuntimeError(f'regenerated orphan prediction differs: {kind}/{i}/r{r}')
    else:
        with ProcessPoolExecutor(max_workers=WORKERS) as pool:
            for row in pool.map(main_case_fit_package,
                ((kind,i,commitments[i],by_case[i],selected[i]) for i in range(100))):
                append(fit_path,row)
                print('POOLED FIT',kind,row['index']+1,'of 100',flush=True)
        ordered=[json.loads(line) for line in fit_path.read_text().splitlines()]
    fit_rows={row['index']:row for row in ordered}
    fit_sha=hashlib.sha256(fit_path.read_bytes()).hexdigest()
    writer=write_or_verify if resume else write_once
    writer(ROOT/kind/'pooled_fit_seal.json',
               {'fit_rows_sha256':fit_sha,'case_count':100,
                'prediction_sha256s':{str(i):{r:meta['fit_meta']['prediction_sha256']
                        for r,meta in fit_rows[i]['ranks'].items()} for i in range(100)}})
    margin_path=ROOT/kind/'rank_margins.json'
    if resume and margin_path.exists():
        expected=ROOT/kind/'rank_margins_resume_check.json'
        try:
            margin_sha=seal_rank_margins(expected,fit_rows,members)
            if margin_path.read_bytes()!=expected.read_bytes():
                raise RuntimeError('saved margins differ from full fit rows')
        finally:
            expected.unlink(missing_ok=True)
    else:
        margin_sha=seal_rank_margins(margin_path,fit_rows,members)
    margins,folds=read_sealed_margins(margin_path,margin_sha)
    if resume:
        score_items=[(kind,i,commitments[i],by_case[i],selected[i],fit_rows[i],margin_sha)
                     for i in range(100)]
        scored=complete_ordered_rows(result_path,score_items,main_case_score_package,
                                     'index',100)
    else:
        with ProcessPoolExecutor(max_workers=WORKERS) as pool:
            for row in pool.map(main_case_score_package,
                ((kind,i,commitments[i],by_case[i],selected[i],fit_rows[i],margin_sha)
                 for i in range(100))):
                append(result_path,row)
                print('POOLED SCORE',kind,row['index']+1,'of 100',flush=True)
        scored=[json.loads(line) for line in result_path.read_text().splitlines()]
    cases={row['index']:row for row in scored}
    blocks={family:{} for family in ('primary','reversal','order')}
    scope={};signals={};expected={};failed_fits=invalid_starts=fit_count=start_count=0
    for r in (2,3,4):
        group=[cases[i]['ranks'][str(r)] for i in members[r]]
        if not group:
            for family,letter in (('primary','D'),('primary','G'),('reversal','R'),('order','O')):
                blocks[family][f'{letter}{r}']=None
            continue
        scope[r]={'context_C95':[row['scope_C95_test'] for row in group],
                  'mean_C95':float(np.mean([row['scope_C95_test'] for row in group])),
                  'max_C95':float(max(row['scope_C95_test'] for row in group)),
                  'failing_fraction':float(np.mean([row['scope_C95_test']>.01 for row in group]))}
        scope[r]['pass']=scope[r]['mean_C95']<=.01
        signals[r]=float(np.mean([row['signal'] for row in group]))
        expected[r]={letter:float(np.mean([row['expected'][rival]-row['expected']['square']
                 for row in group])) for letter,rival in
                 [('D','selected_classical'),('G','diagonal'),('O','selected_order')]}
        expected[r]['R']=float(np.mean([row['expected']['square']-row['expected'][f'ed{r}']
                                       for row in group]))
        for letter,family in [('D','primary'),('G','primary'),('R','reversal'),('O','order')]:
            blocks[family][f'{letter}{r}']=np.mean([row['contrasts'][letter] for row in group],axis=0)
    # Count a shared case/rank fit once, even when it enters several rank means.
    for case in cases.values():
        for row in case['ranks'].values():
            failed_fits+=row['failed_fits'];invalid_starts+=row['invalid_starts']
            fit_count+=row['fit_count'];start_count+=row['start_count']
    bs={family:V.bootstrap_indices(family,ROOT/'bootstrap_cache')
        for family in ('primary','reversal','order')}
    primary={f'{letter}{r}':(.01 if letter=='G' else margins.get(r,.01))
             for r in (2,3,4) for letter in ('D','G')}
    reversal={f'R{r}':margins.get(r,.01) for r in (2,3,4)}
    order={f'O{r}':margins.get(r,.01) for r in (2,3,4)}
    inf={family:V.inference(blocks[family],limits,family,bs[family])
         for family,limits in [('primary',primary),('reversal',reversal),('order',order)]}
    rank_pass={}
    for r in (2,3,4):
        if not members[r]:
            rank_pass[r]=False
            continue
        rank_pass[r]=rank_claim(bool(members[r]),scope[r]['pass'],signals[r],margins[r],
            {'D':inf['primary']['bounds'][f'D{r}'],
                         'G':inf['primary']['bounds'][f'G{r}'],
                         'R':inf['reversal']['bounds'][f'R{r}'],
                         'O':inf['order']['bounds'][f'O{r}']})
    exact_false=any(expected[r]['D']>margins[r] for r in margins)
    worst_case={str(r):max(members[r],key=lambda i:
        cases[i]['ranks'][str(r)]['expected']['selected_classical']-
        cases[i]['ranks'][str(r)]['expected']['square']) for r in margins}
    invalid_fraction=invalid_starts/start_count if start_count else 0.
    all_empty=kind=='hmm' and not any(members.values())
    verdict={'gate':kind+'_pooled_false_square','status':'PASS' if false_square_pass(
             expected,margins,rank_pass,invalid_fraction) else 'FAIL',
             'component':'INELIGIBLE' if all_empty else 'ELIGIBLE',
             'rank_counts':{str(r):len(members[r]) for r in members},
             'rank_pass':rank_pass,'exact_false_square':exact_false,
             'margins':margins,'folds':folds,'margin_sha256':margin_sha,
             'scope':scope,'signals':signals,
             'expected':expected,'inference':inf,'worst_square_advantage_case':worst_case,
             'fit_count':fit_count,
             'failed_fits':failed_fits,'invalid_starts':invalid_starts,'start_count':start_count,
             'invalid_start_fraction':invalid_fraction,
             'wall_seconds':time.monotonic()-started}
    write_once(ROOT/kind/'pooled_verdict.json',verdict)
    return verdict


def split_control(commitments: list[dict]) -> dict:
    started=time.monotonic();passed=0;rows=[]
    for i,committed in enumerate(commitments):
        p=plant('split_state',i)
        if draw_digest(p)!=committed: raise RuntimeError('split-state draw hash mismatch')
        audit=fixed_census(p)
        ok=all(audit['lags'][str(h)]['C95_train']>.01 for h in LAGS)
        passed+=ok
        rows.append({'index':i,'pass':ok,'selected_h':audit['selected_h'],
                     'C95_train':audit['C95_train'],
                     'L':{str(h):audit['lags'][str(h)]['L'] for h in LAGS},
                     'C_by_recipe_time':{str(h):audit['lags'][str(h)]['C_by_recipe_time']
                                         for h in LAGS}})
    write_once(ROOT/'split_state'/'closure_results.json',rows)
    verdict={'gate':'split_state_nonclosure','required':95,'passed':passed,
             'status':'PASS' if split_pass(passed) else 'FAIL',
             'worst_case_index':min(rows,key=lambda row:min(row['C95_train'].values()))['index'],
             'worst_case_min_C95':min(min(row['C95_train'].values()) for row in rows),
             'wall_seconds':time.monotonic()-started}
    write_once(ROOT/'split_state'/'verdict.json',verdict)
    return verdict


def pseudo_fit_package(item: tuple[int,int,int,dict,list[int],int]) -> dict:
    campaign,slot,m,committed,ranks,selected_h=item
    p=G.pseudocampaign_context(campaign,slot,m)
    if draw_digest(p)!=committed: raise RuntimeError('pseudo-campaign draw hash mismatch')
    # The source law is distribution-level; h_c remains in the record context
    # and seed derivation, while its eight synthetic successors are generated
    # directly as a record process.
    d=record(p,selected_h)
    output={}
    for rank in ranks:
        namespace=f'pseudocampaign/campaign_{campaign:03d}'
        fit_meta=fit_seal_case(p,d,rank,namespace)
        folds=[fold_contrast(p,d,selected_h,rank,f) for f in range(5)]
        output[str(rank)]={'fit_meta':fit_meta,'folds':folds}
    return {'slot':slot,'ranks':output}


def pseudo_rank_task(item: tuple[int,int,int,dict,int,int,int | None]):
    campaign,slot,m,committed,rank,selected_h,fold=item
    p=G.pseudocampaign_context(campaign,slot,m)
    if draw_digest(p)!=committed:raise RuntimeError('pseudo-campaign draw hash mismatch')
    d=record(p,selected_h)
    if fold is None:
        value=fit_seal_case(p,d,rank,f'pseudocampaign/campaign_{campaign:03d}')
    else:
        value=fold_contrast(p,d,selected_h,rank,fold)
    return campaign,slot,rank,fold,value


def pseudo_task_arguments(campaign: int, slots: list, unique: dict,
                          commitment: list, membership: dict) -> list[tuple]:
    tasks=[]
    for slot,key in enumerate(slots):
        base=(campaign,slot,unique[key]['m'],
              commitment[campaign*len(slots)+slot]['draw'],unique[key]['h_c'])
        for rank in (2,3,4):
            if slot not in membership[rank]:continue
            for fold in (None,0,1,2,3,4):
                tasks.append((base[0],base[1],base[2],base[3],rank,base[4],fold))
    return tasks


def assemble_pseudo_fits(campaign: int, slots: list, membership: dict,
                         results: list[tuple]) -> list[dict]:
    values={}
    for c,slot,rank,fold,value in results:
        key=(c,slot,rank,fold)
        if c!=campaign or key in values:raise RuntimeError('duplicate or wrong pseudo task')
        values[key]=value
    rows=[]
    for slot in range(len(slots)):
        ranks={}
        for rank in (2,3,4):
            if slot not in membership[rank]:continue
            ranks[str(rank)]={'fit_meta':values.pop((campaign,slot,rank,None)),
                              'folds':[values.pop((campaign,slot,rank,f)) for f in range(5)]}
        rows.append({'slot':slot,'ranks':ranks})
    if values:raise RuntimeError('unexpected pseudo task result')
    return rows


def pseudo_fit_scheduler(pool, start: int, stop: int, slots: list, unique: dict,
                         commitment: list, membership: dict, lookahead: int = 4,
                         skip_fits: set[int] | None = None):
    """At most four campaigns' rank/fit/fold tasks are pending at once."""
    pending={}
    next_campaign=start
    skip_fits=set() if skip_fits is None else skip_fits
    for campaign in range(start,stop):
        while next_campaign<stop and len(pending)<lookahead:
            if next_campaign not in skip_fits:
                args=pseudo_task_arguments(next_campaign,slots,unique,commitment,membership)
                pending[next_campaign]=[pool.submit(pseudo_rank_task,arg) for arg in args]
            next_campaign+=1
        if campaign in skip_fits:
            yield campaign,None
        else:
            results=[future.result() for future in pending.pop(campaign)]
            yield campaign,assemble_pseudo_fits(campaign,slots,membership,results)


def pseudo_score_package(item: tuple[int,int,int,dict,list[int],int,dict,str]) -> dict:
    campaign,slot,m,committed,ranks,selected_h,fit_row,margin_sha=item
    read_sealed_margins(ROOT/'pseudocampaign'/f'campaign_{campaign:03d}_margins.json',
                        margin_sha)
    p=G.pseudocampaign_context(campaign,slot,m)
    if draw_digest(p)!=committed or fit_row['slot']!=slot:
        raise RuntimeError('pseudo score draw or fit commitment mismatch')
    output={}
    namespace=f'pseudocampaign/campaign_{campaign:03d}'
    for rank in ranks:
        prior=fit_row['ranks'][str(rank)]
        result=score_sealed_case(p,selected_h,rank,namespace,prior['fit_meta'])
        fold=prior['folds']
        gain,_=V.signal([result['law']])
        output[str(rank)]={'contrasts':{k:v.tolist() for k,v in result['contrasts'].items()},
                           'expected':result['expected'],
                           'sampled_mean_loss':result['sampled_mean_loss'],
                           'folds':[x[0] for x in fold],
                           'scope_C95_test':0.,'signal':gain,
                           'oracle_pooled_constant':result['law'].mean(axis=(0,1)).tolist(),
                           'failed_fits':result['failed_fits']+sum(x[1] for x in fold),
                           'invalid_starts':result['invalid_starts']+sum(x[2] for x in fold),
                           'fit_count':result['fit_count']*6,
                           'start_count':result['start_count']+sum(x[3] for x in fold),
                           'prediction_sha256':result['prediction_sha256']}
        output[str(rank)]['optimizer_by_model']=result['optimizer_by_model']
    return {'slot':slot,'ranks':output}


def pseudocampaigns(resume: bool = False, stop_after: int = 100) -> dict:
    started=time.monotonic()
    release=json.loads(CENSUS.read_bytes())
    if release.get('schema')!='test_b_v6_census_release_v1' or release.get('eligible_per_rank')!={'2':8,'3':6,'4':6}:
        raise ValueError('wrong frozen v6 census release')
    unique={}
    for r in ('2','3','4'):
        for ctx in release['rank_contexts'][r]:
            key=(ctx['exp'],ctx['config'],ctx['k'],ctx['step_index'])
            unique[key]=ctx
    slots=sorted(unique)
    membership={r:[slots.index((c['exp'],c['config'],c['k'],c['step_index']))
                   for c in release['rank_contexts'][str(r)]] for r in (2,3,4)}
    if len(slots)!=8 or {r:len(v) for r,v in membership.items()}!={2:8,3:6,4:6}:
        raise ValueError('v6 census incidence differs from frozen P4a release')
    folder=ROOT/'pseudocampaign';folder.mkdir(exist_ok=resume)
    commitment=[]
    for campaign in range(100):
        for slot,key in enumerate(slots):
            p=G.pseudocampaign_context(campaign,slot,unique[key]['m'])
            commitment.append({'campaign':campaign,'slot':slot,
                               'census_context':key,'selected_h':unique[key]['h_c'],
                               'draw':draw_digest(p)})
    digest=(write_or_verify if resume else write_once)(folder/'draw_commitment.json',commitment)
    print('COMMITTED pseudocampaign',len(commitment),digest,flush=True)
    bs={family:V.bootstrap_indices(family,ROOT/'bootstrap_cache')
        for family in ('primary','reversal','order')}
    output=folder/'campaign_results.jsonl'
    saved=read_prefix(output,'campaign',100) if resume else []
    passed=sum(bool(row['pass']) for row in saved)
    processed=len(saved)
    failed_fits=invalid_starts=fit_count=start_count=0
    for campaign in saved:
        for case in campaign['cases']:
            for fit in case['ranks'].values():
                failed_fits+=fit['failed_fits'];invalid_starts+=fit['invalid_starts']
                fit_count+=fit['fit_count'];start_count+=fit['start_count']
    if not len(saved)<=stop_after<=100:raise ValueError('invalid pseudo replay limit')
    skip_fits={campaign for campaign in range(len(saved),stop_after)
               if resume and (folder/f'campaign_{campaign:03d}_fits.json').exists()}
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        scheduled=pseudo_fit_scheduler(pool,len(saved),stop_after,slots,unique,
                    commitment,membership,skip_fits=skip_fits)
        for campaign,scheduled_fits in scheduled:
            items=[(campaign,slot,unique[key]['m'],commitment[campaign*len(slots)+slot]['draw'],
                    [r for r in (2,3,4) if slot in membership[r]],unique[key]['h_c'])
                   for slot,key in enumerate(slots)]
            fit_path=folder/f'campaign_{campaign:03d}_fits.json'
            if resume and fit_path.exists():
                fit_rows=json.loads(fit_path.read_bytes())
                if [row['slot'] for row in fit_rows]!=list(range(len(slots))):
                    raise RuntimeError('saved pseudo fit slots differ')
                for row in fit_rows:
                    slot=row['slot']
                    for rank,entry in row['ranks'].items():
                        path=folder/f'campaign_{campaign:03d}'/f'case_{campaign}:{slot}_r{rank}_predictions.json'
                        if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['fit_meta']['prediction_sha256']:
                            raise RuntimeError('saved pseudo prediction differs')
                        S.open_sealed_predictions(path)
                fit_sha=hashlib.sha256(fit_path.read_bytes()).hexdigest()
            else:
                if scheduled_fits is None:raise RuntimeError('missing scheduled pseudo fits')
                fit_rows=scheduled_fits
                fit_sha=write_once(fit_path,fit_rows)
            (write_or_verify if resume else write_once)(folder/f'campaign_{campaign:03d}_fit_seal.json',
                       {'fit_rows_sha256':fit_sha,'case_count':len(fit_rows),
                        'prediction_sha256s':{str(row['slot']):{r:meta['fit_meta']['prediction_sha256']
                            for r,meta in row['ranks'].items()} for row in fit_rows}})
            margin_path=folder/f'campaign_{campaign:03d}_margins.json'
            if resume and margin_path.exists():
                check=folder/f'campaign_{campaign:03d}_margins_resume_check.json'
                try:
                    margin_sha=seal_rank_margins(check,
                                {row['slot']:row for row in fit_rows},membership)
                    if margin_path.read_bytes()!=check.read_bytes():
                        raise RuntimeError('saved pseudo margins differ from full fit set')
                finally:
                    check.unlink(missing_ok=True)
            else:
                margin_sha=seal_rank_margins(margin_path,
                                {row['slot']:row for row in fit_rows},membership)
            margins,folds=read_sealed_margins(margin_path,margin_sha)
            rows=list(pool.map(pseudo_score_package,
                ((campaign,slot,unique[key]['m'],commitment[campaign*len(slots)+slot]['draw'],
                  [r for r in (2,3,4) if slot in membership[r]],unique[key]['h_c'],
                  fit_rows[slot],margin_sha)
                 for slot,key in enumerate(slots))))
            by_slot={row['slot']:row for row in rows}
            blocks={family:{} for family in ('primary','reversal','order')}
            signals={};scope={};expected={}
            for r in (2,3,4):
                group=[by_slot[i]['ranks'][str(r)] for i in membership[r]]
                if not group:
                    for fam,letter in [('primary','D'),('primary','G'),('reversal','R'),('order','O')]:
                        blocks[fam][f'{letter}{r}']=None
                    continue
                signals[r]=float(np.mean([x['signal'] for x in group]))
                scope[r]={'mean_C95':0.,'max_C95':0.,'failing_fraction':0.,'pass':True}
                expected[r]={letter:float(np.mean([x['expected'][rival]-x['expected']['square']
                    for x in group])) for letter,rival in
                    [('D','selected_classical'),('G','diagonal'),('O','selected_order')]}
                expected[r]['R']=float(np.mean([x['expected']['square']-x['expected'][f'ed{r}']
                                                for x in group]))
                for letter,fam in [('D','primary'),('G','primary'),('R','reversal'),('O','order')]:
                    blocks[fam][f'{letter}{r}']=np.mean([x['contrasts'][letter] for x in group],axis=0)
            primary={f'{letter}{r}':(.01 if letter=='G' else margins.get(r,.01))
                     for r in (2,3,4) for letter in ('D','G')}
            reversal={f'R{r}':margins.get(r,.01) for r in (2,3,4)}
            order={f'O{r}':margins.get(r,.01) for r in (2,3,4)}
            inf={fam:V.inference(blocks[fam],limits,fam,bs[fam]) for fam,limits in
                 [('primary',primary),('reversal',reversal),('order',order)]}
            rank_pass={r:pseudo_rank_claim(bool(membership[r]),scope[r]['pass'],signals[r],margins[r],
                expected[r],{'D':inf['primary']['bounds'][f'D{r}'],
                             'G':inf['primary']['bounds'][f'G{r}'],
                             'R':inf['reversal']['bounds'][f'R{r}'],
                             'O':inf['order']['bounds'][f'O{r}']}) for r in margins}
            for row in rows:
                for fit in row['ranks'].values():
                    failed_fits+=fit['failed_fits'];invalid_starts+=fit['invalid_starts']
                    fit_count+=fit['fit_count'];start_count+=fit['start_count']
            ok=any(rank_pass.values());passed+=ok;processed+=1
            append(output,{'campaign':campaign,'census_slots':slots,'membership':membership,
                           'm_by_slot':[unique[k]['m'] for k in slots],
                           'h_by_slot':[unique[k]['h_c'] for k in slots],
                           'margins':margins,'folds':folds,'margin_sha256':margin_sha,
                           'scope':scope,'signals':signals,
                           'expected':expected,'inference':inf,'rank_pass':rank_pass,'pass':ok,
                           'cases':rows})
            print('PSEUDO',processed,'pass',passed,'fail',processed-passed,flush=True)
    if stop_after<100:
        return {'status':'REPLAY','processed':processed,'passed':passed}
    invalid_fraction=invalid_starts/start_count if start_count else 0.
    verdict={'gate':'census_matched_pseudocampaign','status':'PASS' if pseudo_pass(
             processed,passed,invalid_fraction) else 'FAIL','required':80,'committed':100,
             'processed':processed,'passed':passed,'census_contexts':len(slots),
             'rank_counts':{str(r):len(membership[r]) for r in membership},
             'failed_fits':failed_fits,'invalid_starts':invalid_starts,'start_count':start_count,
             'invalid_start_fraction':invalid_fraction,'wall_seconds':time.monotonic()-started}
    write_once(folder/'verdict.json',verdict)
    return verdict
















def configure(*, output: Path, census: Path) -> None:
    """Bind explicit new-run outputs/inputs; no historical root discovery."""
    global ROOT, CENSUS, CENSUS_HASH
    ROOT = Path(output).resolve()
    CENSUS = Path(census).resolve(strict=True)
    CENSUS_HASH = hashlib.sha256(CENSUS.read_bytes()).hexdigest()
