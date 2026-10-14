"""Audit-only v6 recipe constructor and exact closure census.

Reads only frozen v4 audit header lines. Never imports the record estimator or
opens calibration/path rows. Held-out C values are written once and sealed.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from born_ladder.record_tests.test_b_census import LAGS, THRESHOLD, canonical_bytes, closure_deficit, lumpability_defect, nearest_95

RECIPE_COUNT = 60
TRAIN_COUNT = 36
VALID_COUNT = 12
TEST_COUNT = 12


def source_header(path: Path) -> tuple[dict, str]:
    with path.open('rb') as stream:
        line = stream.readline().removesuffix(b'\n')
    header = json.loads(line)
    if header.get('schema') != 'test_b_audit_v1' or header.get('kernel_seed') != 910000:
        raise ValueError(f'not a frozen seed-910000 audit header: {path}')
    if header.get('path_steps') != 64 or len(header.get('recipes', [])) != 24:
        raise ValueError(f'wrong frozen header contents: {path}')
    return header, hashlib.sha256(line).hexdigest()


def recipes_v6(n: int, header_sha256: str, legacy_recipes: list[list[int]]) -> list[dict]:
    if n < 3 or len(legacy_recipes) != 24:
        raise ValueError('v6 recipe constructor needs n>=3 and 24 old recipes')
    legacy_uniform = {tuple(sorted(x)) for x in legacy_recipes if len(set(x)) == 3}
    tiers: list[list[tuple[bytes, tuple[int, ...], tuple[int, ...], int]]] = [[], []]
    for states in itertools.combinations(range(n), 3):
        if states in legacy_uniform:
            continue
        i, j, k = states
        key = f'TestB/v6/recipe/{header_sha256}/{i}/{j}/{k}/1/3/1/3'.encode()
        tiers[0].append((hashlib.sha256(key).digest(), states, (1, 1, 1), 3))
    tiers[0].sort(key=lambda row: (row[0], row[1], row[2]))
    selected = tiers[0][:RECIPE_COUNT]
    if len(selected) < RECIPE_COUNT:
        for states in itertools.combinations(range(n), 3):
            i, j, k = states
            for p in range(1, 100):
                for q in range(1, 101 - p):
                    weights = (p, q, 101 - p - q)
                    key = f'TestB/v6/recipe/{header_sha256}/{i}/{j}/{k}/{p}/{q}'.encode()
                    tiers[1].append((hashlib.sha256(key).digest(), states, weights, 101))
        tiers[1].sort(key=lambda row: (row[0], row[1], row[2]))
        selected.extend(tiers[1][:RECIPE_COUNT - len(selected)])
    if len(selected) != RECIPE_COUNT:
        raise ValueError('kernel cannot provide 60 distinct v6 recipes')
    recipes = [dict(states=list(states), weights_num=list(weights), denominator=denom)
               for _, states, weights, denom in selected]
    if len({(tuple(r['states']), tuple(r['weights_num']), r['denominator']) for r in recipes}) != RECIPE_COUNT:
        raise AssertionError('duplicate v6 starting measure')
    return recipes


def _context_census(kernel: np.ndarray, q: np.ndarray, recipes: list[dict]) -> tuple[list[dict], dict]:
    n = len(kernel)
    if kernel.shape != (n, n) or q.shape != (n,):
        raise ValueError('kernel/context dimension mismatch')
    if not np.allclose(kernel.sum(axis=1), 1.0, atol=1e-10) or np.min(kernel) < -1e-12:
        raise ValueError('invalid fixed kernel')
    m = int(q.max()) + 1
    incidence = np.eye(m)[q]
    initials = np.zeros((RECIPE_COUNT, n), dtype=float)
    for a, recipe in enumerate(recipes):
        for state, numerator in zip(recipe['states'], recipe['weights_num']):
            initials[a, state] += numerator / recipe['denominator']
    rows: list[dict] = []
    summary = {'m': m, 'lags': {}}
    for h in LAGS:
        kh = np.linalg.matrix_power(kernel, h)
        block_rows = kh @ incidence
        defect = lumpability_defect(q, block_rows)
        mu = initials.copy()
        values = np.empty((RECIPE_COUNT, 8), dtype=float)
        for t in range(8):
            for a in range(RECIPE_COUNT):
                value = closure_deficit(mu[a], q, block_rows)
                values[a, t] = value
                rows.append({'h': h, 'recipe': a, 't': t, 'C': value})
            mu = mu @ kh
        training = values[:TRAIN_COUNT].ravel().tolist()
        summary['lags'][str(h)] = {'C95_train': nearest_95(training),
                                    'Cmax_train': max(training), 'L': defect}
    summary['h_c'] = next((h for h in LAGS if summary['lags'][str(h)]['C95_train'] <= THRESHOLD), None)
    return rows, summary


def _unit(path: Path) -> tuple[list[dict], list[dict], dict]:
    header, header_hash = source_header(path)
    recipes = recipes_v6(header['n'], header_hash, header['recipes'])
    kernel = np.asarray(header['kernel'], dtype=np.float64)
    rows, contexts = [], []
    for context in header['contexts']:
        q = np.asarray(context['joint_by_state'], dtype=np.int64)
        map_hash = hashlib.sha256(canonical_bytes({
            'raw_by_state': context['raw_by_state'],
            'package_by_state': context['package_by_state'],
        })).hexdigest()
        identity = {'exp': header['exp'], 'config': header['config'],
                    'k': context['k'], 'step_index': context['step_index'],
                    'map_sha256': map_hash}
        local, summary = _context_census(kernel, q, recipes)
        rows.extend({**identity, **row} for row in local)
        contexts.append({**identity, **summary})
    unit = {'exp': header['exp'], 'config': header['config'],
            'n': header['n'], 'contexts': len(contexts),
            'sealed_kernel_header_sha256': header_hash,
            'recipes': recipes}
    return rows, contexts, unit


def _write_hashed(path: Path, rows: list[dict]) -> str:
    digest = hashlib.sha256()
    with path.open('xb') as stream:
        for row in rows:
            data = canonical_bytes(row)
            stream.write(data)
            digest.update(data)
        stream.flush()
        os.fsync(stream.fileno())
    return digest.hexdigest()


def run(audit_dir: Path, output_dir: Path, workers: int = 1, expected_units: int = 140) -> dict:
    files = sorted(audit_dir.glob('*.audit.jsonl'))
    if len(files) != expected_units:
        raise ValueError(f'expected exactly {expected_units} audit headers, got {len(files)}')
    if output_dir.exists():
        raise FileExistsError(f'v6 census output already exists: {output_dir}')
    output_dir.mkdir(parents=True)
    sealed = output_dir / 'sealed'
    sealed.mkdir(mode=0o700)
    rows, contexts, units = [], [], []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for local_rows, local_contexts, unit in pool.map(_unit, files):
            rows.extend(local_rows)
            contexts.extend(local_contexts)
            units.append(unit)
    if len({(u['exp'], u['config']) for u in units}) != expected_units:
        raise ValueError('duplicate fixed-kernel identity')
    rows.sort(key=lambda row: (row['exp'], row['config'], row['k'], row['map_sha256'],
                               row['h'], row['recipe'], row['t']))
    full_hash = _write_hashed(sealed / 'full_census.jsonl', rows)
    train_hash = _write_hashed(output_dir / 'training_census.jsonl', [r for r in rows if r['recipe'] < TRAIN_COUNT])
    valid_hash = _write_hashed(sealed / 'validation_census.jsonl', [r for r in rows if TRAIN_COUNT <= r['recipe'] < TRAIN_COUNT + VALID_COUNT])
    test_hash = _write_hashed(sealed / 'test_census.jsonl', [r for r in rows if r['recipe'] >= TRAIN_COUNT + VALID_COUNT])
    recipe_audit = [{field: unit[field] for field in
                     ('exp', 'config', 'sealed_kernel_header_sha256', 'recipes')}
                    for unit in units]
    recipe_hash = _write_hashed(sealed / 'recipe_audit.jsonl', recipe_audit)
    public_units = [{field: unit[field] for field in
                     ('exp', 'config', 'n', 'contexts', 'sealed_kernel_header_sha256')}
                    for unit in units]
    for name in ('full_census.jsonl', 'validation_census.jsonl', 'test_census.jsonl', 'recipe_audit.jsonl'):
        os.chmod(sealed / name, 0o600)
    ranks = {str(r): [] for r in (2, 3, 4)}
    eligible_at_h, primary_eligible_at_h, selected_h = Counter(), Counter(), Counter()
    for context in contexts:
        excluded = context['exp'] == 'EXP-112' and context['config'] == 'empty'
        context['primary_excluded_reason'] = 'frozen empty configuration' if excluded else None
        for h in LAGS:
            if context['lags'][str(h)]['C95_train'] <= THRESHOLD:
                eligible_at_h[str(h)] += 1
                if not excluded:
                    primary_eligible_at_h[str(h)] += 1
        h_c = context['h_c']
        selected_h[str(h_c) if h_c is not None else 'none'] += 1
        if h_c is not None and not excluded:
            for rank in (2, 3, 4):
                if context['m'] > rank:
                    ranks[str(rank)].append({field: context[field]
                        for field in ('exp','config','k','step_index','map_sha256','h_c','m')})
    release = {
        'schema': 'test_b_v6_census_release_v1',
        'spec_sha256': '3abc68c6f0a8070240a2302434b28644fbf8b67f955a65af2cf33667cfd6d2cd',
        'unit_count': len(units), 'context_count': len(contexts),
        'units': public_units, 'training_contexts': contexts,
        'eligible_at_h': {str(h): eligible_at_h[str(h)] for h in LAGS},
        'primary_eligible_at_h': {str(h): primary_eligible_at_h[str(h)] for h in LAGS},
        'selected_h': {str(h): selected_h[str(h)] for h in LAGS} | {'none': selected_h['none']},
        'eligible_per_rank': {r: len(v) for r, v in ranks.items()},
        'rank_contexts': ranks,
        'full_census_sha256': full_hash, 'training_census_sha256': train_hash,
        'sealed_validation_census_sha256': valid_hash,
        'sealed_test_census_sha256': test_hash,
        'sealed_recipe_audit_sha256': recipe_hash,
    }
    (output_dir / 'eligibility.json').write_bytes(canonical_bytes(release))
    return release


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--audit-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=1)
    args = parser.parse_args()
    result = run(args.audit_dir, args.output_dir, args.workers)
    print(json.dumps({key: result[key] for key in
        ('unit_count','context_count','eligible_at_h','primary_eligible_at_h',
         'selected_h','eligible_per_rank','full_census_sha256',
         'sealed_validation_census_sha256','sealed_test_census_sha256')}, sort_keys=True))


if __name__ == '__main__':
    main()
