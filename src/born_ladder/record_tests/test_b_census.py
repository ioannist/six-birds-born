"""Audit-only exact Test B closure census. No record estimator imports this module.

The full and test-recipe rows are hashed while written, then sealed without a
readback. stdout and the released summary contain training values only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

LAGS = (1, 2, 4, 8)
THRESHOLD = 0.01


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def nearest_95(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError('empty percentile input')
    return ordered[(95 * len(ordered) + 99) // 100 - 1]


def closure_deficit(mu: np.ndarray, q: np.ndarray, block_rows: np.ndarray) -> float:
    """I(X;Y_next | q(X)) in nats, with zero-mass terms omitted."""
    m = int(q.max()) + 1
    out = 0.0
    for label in range(m):
        states = np.flatnonzero(q == label)
        mass = float(mu[states].sum())
        if mass <= 0.0:
            continue
        mixture = (mu[states, None] * block_rows[states]).sum(axis=0) / mass
        for state in states:
            weight = float(mu[state])
            if weight == 0:
                continue
            row = block_rows[state]
            positive = row > 0
            if np.any(mixture[positive] <= 0):
                raise ArithmeticError('positive row mass has zero mixture mass')
            out += weight * float(np.sum(row[positive] * np.log(row[positive] / mixture[positive])))
    if out < -1e-12:
        raise ArithmeticError(f'negative closure deficit: {out}')
    return max(0.0, out)


def lumpability_defect(q: np.ndarray, block_rows: np.ndarray) -> float:
    defect = 0.0
    for label in np.unique(q):
        rows = block_rows[q == label]
        if len(rows) > 1:
            distances = 0.5 * np.abs(rows[:, None, :] - rows[None, :, :]).sum(axis=2)
            defect = max(defect, float(distances.max()))
    return defect


def census_for_context(kernel: np.ndarray, q: np.ndarray, recipes: list[list[int]]) -> tuple[list[dict], dict]:
    n = len(kernel)
    if kernel.shape != (n, n) or q.shape != (n,):
        raise ValueError('kernel/context dimension mismatch')
    if not np.allclose(kernel.sum(axis=1), 1.0, atol=1e-10) or np.min(kernel) < -1e-12:
        raise ValueError('invalid Markov kernel')
    m = int(q.max()) + 1
    incidence = np.eye(m)[q]
    rows: list[dict] = []
    summary: dict = {'m': m, 'lags': {}}
    for h in LAGS:
        kh = np.linalg.matrix_power(kernel, h)
        block_rows = kh @ incidence
        defect = lumpability_defect(q, block_rows)
        values: dict[tuple[int, int], float] = {}
        for recipe, starts in enumerate(recipes):
            mu = np.zeros(n)
            for state in starts:
                mu[state] += 1.0 / len(starts)
            for t in range(8):
                value = closure_deficit(mu, q, block_rows)
                values[(recipe, t)] = value
                rows.append({'h': h, 'recipe': recipe, 't': t, 'C': value})
                mu = mu @ kh
        training = [values[(a, t)] for a in range(12) for t in range(8)]
        summary['lags'][str(h)] = {
            'C95_train': nearest_95(training),
            'Cmax_train': max(training),
            'L': defect,
        }
    summary['h_c'] = next(
        (h for h in LAGS if summary['lags'][str(h)]['C95_train'] <= THRESHOLD), None
    )
    return rows, summary


def _write_hashed(path: Path, rows: list[dict]) -> str:
    digest = hashlib.sha256()
    with path.open('wb') as out:
        for row in rows:
            data = canonical_bytes(row)
            out.write(data)
            digest.update(data)
    return digest.hexdigest()


def run(audit_dir: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    sealed_dir = output_dir / 'sealed'
    sealed_dir.mkdir(exist_ok=True)
    os.chmod(sealed_dir, 0o700)
    audit_files = sorted(audit_dir.glob('*.audit.jsonl'))
    if not audit_files:
        raise FileNotFoundError(f'no audit sidecars in {audit_dir}')
    all_rows: list[dict] = []
    context_summaries: list[dict] = []
    units = []
    seen = set()
    for path in audit_files:
        with path.open('rb') as stream:
            header = json.loads(stream.readline())
        if header.get('schema') != 'test_b_audit_v1':
            raise ValueError(f'bad audit schema: {path}')
        if header.get('kernel_seed') != 910000 or header.get('path_steps') != 64:
            raise ValueError(f'wrong kernel seed/path length: {path}')
        exp, config = header['exp'], header['config']
        unit_key = (exp, config)
        if unit_key in seen:
            raise ValueError(f'duplicate unit {unit_key}')
        seen.add(unit_key)
        units.append({'exp': exp, 'config': config, 'contexts': len(header['contexts'])})
        kernel = np.asarray(header['kernel'], dtype=np.float64)
        for context in header['contexts']:
            q = np.asarray(context['joint_by_state'], dtype=np.int64)
            map_hash = hashlib.sha256(canonical_bytes({
                'raw_by_state': context['raw_by_state'],
                'package_by_state': context['package_by_state'],
            })).hexdigest()
            identity = {
                'exp': exp, 'config': config, 'k': context['k'],
                'step_index': context['step_index'], 'map_sha256': map_hash,
            }
            rows, summary = census_for_context(kernel, q, header['recipes'])
            for row in rows:
                all_rows.append({**identity, **row})
            context_summaries.append({**identity, **summary})
    key = lambda row: (
        row['exp'], row['config'], row['k'], row['map_sha256'],
        row['h'], row['recipe'], row['t'],
    )
    all_rows.sort(key=key)
    full_hash = _write_hashed(sealed_dir / 'full_census.jsonl', all_rows)
    train_rows = [row for row in all_rows if row['recipe'] < 12]
    validation_rows = [row for row in all_rows if 12 <= row['recipe'] < 18]
    test_rows = [row for row in all_rows if row['recipe'] >= 18]
    training_hash = _write_hashed(output_dir / 'training_census.jsonl', train_rows)
    validation_hash = _write_hashed(sealed_dir / 'validation_census.jsonl', validation_rows)
    test_hash = _write_hashed(sealed_dir / 'test_census.jsonl', test_rows)
    for sealed_name in ('full_census.jsonl', 'validation_census.jsonl', 'test_census.jsonl'):
        os.chmod(sealed_dir / sealed_name, 0o600)
    # Do not reopen either sealed file. These commitments accompany the released training rows.
    eligible_at_h = Counter()
    primary_eligible_at_h = Counter()
    selected_h = Counter()
    ranks = {str(r): [] for r in (2, 3, 4)}
    released_contexts = []
    for context in context_summaries:
        primary_excluded = context['exp'] == 'EXP-112' and context['config'] == 'empty'
        context['primary_excluded_reason'] = 'frozen empty configuration' if primary_excluded else None
        for h in LAGS:
            if context['lags'][str(h)]['C95_train'] <= THRESHOLD:
                eligible_at_h[str(h)] += 1
                if not primary_excluded:
                    primary_eligible_at_h[str(h)] += 1
        h_c = context['h_c']
        selected_h[str(h_c) if h_c is not None else 'none'] += 1
        if h_c is not None and not primary_excluded:
            for rank in (2, 3, 4):
                if context['m'] > rank:
                    ranks[str(rank)].append({
                        field: context[field]
                        for field in ('exp', 'config', 'k', 'step_index', 'map_sha256', 'h_c', 'm')
                    })
        released_contexts.append(context)
    summary = {
        'schema': 'test_b_census_release_v1',
        'units': units,
        'unit_count': len(units),
        'context_count': len(context_summaries),
        'eligible_at_h': {str(h): eligible_at_h[str(h)] for h in LAGS},
        'primary_eligible_at_h': {str(h): primary_eligible_at_h[str(h)] for h in LAGS},
        'selected_h': {str(h): selected_h[str(h)] for h in LAGS} | {'none': selected_h['none']},
        'eligible_per_rank': {r: len(v) for r, v in ranks.items()},
        'rank_contexts': ranks,
        'training_contexts': released_contexts,
        'full_census_sha256': full_hash,
        'training_census_sha256': training_hash,
        'sealed_validation_census_sha256': validation_hash,
        'sealed_test_census_sha256': test_hash,
    }
    release_tmp = output_dir / 'eligibility.json.tmp'
    release_tmp.write_bytes(canonical_bytes(summary))
    release_tmp.replace(output_dir / 'eligibility.json')
    # Output deliberately contains no test-recipe values.
    print(json.dumps({
        key: summary[key] for key in (
            'unit_count', 'context_count', 'eligible_at_h',
            'selected_h', 'eligible_per_rank', 'full_census_sha256',
            'sealed_test_census_sha256',
        )
    }, sort_keys=True))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--audit-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    run(args.audit_dir, args.output_dir)


if __name__ == '__main__':
    main()
