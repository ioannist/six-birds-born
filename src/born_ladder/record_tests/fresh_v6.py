"""P6 BUILD ONLY: write-once locked-test opening and certified audit scoring.

§2:23,25; §3:42,44; §5:92–113; §6:121,139; §7:143.
No development command samples real kernels. Production requires the full P5 seal.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np

from born_ladder.record_tests import real_v6 as R, cert_v6 as C, generation_scorer as S, scorer_v6 as V
from born_ladder.record_tests.test_b_census_v6 import source_header

SEAL_HASH = None  # caller supplies its new-run prediction commitment
RANK_COUNTS = {'2': 8, '3': 6, '4': 6}
UNIT_COUNT = 140
PHASES = ('prepare', 'sample', 'score')
RULES = {'sampling': '§2 lines 23,25; §6 line 121 step (7)',
         'census': '§3 lines 42,44', 'inference': '§5 lines 92–113',
         'controls': '§6 line 139; prospective P5 manager rulings',
         'verdict': '§7 line 143'}


def identity(row):
    return (row['exp'], row['config'], row['k'], row['step_index'], row['map_sha256'])






def commit(out: Path, phase: str, files: list[Path], summary: dict):
    document = {'phase': phase, 'p6_setup_sha256': R.sha(out / 'setup.json'),
                'earlier': {p: R.sha(out / f'{p}.commit.json')
                            for p in PHASES[:PHASES.index(phase)]},
                'files': R.tree_hashes(out, files), 'summary': summary, 'rules': RULES}
    R.put(out / f'{phase}.commit.json', document)
    return document


def verify_commit(out: Path, phase: str):
    doc = C.canonical_document(out / f'{phase}.commit.json')
    if doc['phase'] != phase or doc['p6_setup_sha256'] != R.sha(out / 'setup.json'):
        raise RuntimeError('P6 phase/setup differs')
    R.verify_files(out, doc['files'])
    for p, digest in doc['earlier'].items():
        verify_commit(out, p)
        if R.sha(out / f'{p}.commit.json') != digest:
            raise RuntimeError('P6 earlier commitment differs')
    return doc


def check_out(root: Path, out: Path):
    if out.resolve() == root.resolve() or out.resolve().is_relative_to(root.resolve()) and out.name != 'p6':
        raise ValueError('P6 output must be a separate directory (or P5/p6)')




def copy_once(source: Path, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if R.sha(source) != R.sha(target): raise RuntimeError('write-once copy differs')
        return
    with source.open('rb') as src, target.open('xb') as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
        dst.flush(); os.fsync(dst.fileno())


def validate_census(directory: Path):
    import heapq
    import itertools
    def lines(name):
        with (directory / name).open('rb') as stream:
            for line in stream: yield json.loads(line)
    def key(x):
        return (x['exp'], x['config'], x['k'], x['map_sha256'], x['h'], x['recipe'], x['t'])
    previous = None
    merged = heapq.merge(lines('training_census.jsonl'), lines('sealed/validation_census.jsonl'),
                        lines('sealed/test_census.jsonl'), key=key)
    for full, part in itertools.zip_longest(lines('sealed/full_census.jsonl'), merged):
        if full is None or part is None or full != part or previous is not None and key(full) <= previous:
            raise RuntimeError('census partitions/order differ')
        previous = key(full)
    for name, lo, hi in [('training_census.jsonl', 0, 36), ('sealed/validation_census.jsonl', 36, 48),
                         ('sealed/test_census.jsonl', 48, 60)]:
        if any(not lo <= x['recipe'] < hi for x in lines(name)):
            raise RuntimeError('census split differs')




def fresh_command(setup: dict, job: dict, sidecars: Path):
    args = R.runner_command(setup, job, sidecars)
    i = args.index('--test-b-sidecar-phase')
    args[i + 1] = 'v6-fresh-test'
    return args


def sample_job(root: Path, out: Path, setup: dict, job: dict):
    directory = out / 'jobs' / R.job_name(job)
    marker = directory / 'complete.json'
    if marker.exists():
        row = C.canonical_document(marker); R.verify_files(out, row['files']); return row
    directory.mkdir(parents=True, exist_ok=True)
    started = directory / 'started.json'
    if started.exists():
        raise RuntimeError('incomplete one-time sampling attempt: no automatic rerun')
    R.put(started, {'job': job, 'p5_seal_sha256': C.canonical_document(out / 'setup.json')['p5_seal_sha256']})
    env = os.environ.copy(); env.update({pin: '1' for pin in R.PINS})
    result = subprocess.run(fresh_command(setup, job, out / 'sidecars'), cwd=directory,
                            env=env, capture_output=True)
    R.put_bytes(directory / 'stdout', result.stdout); R.put_bytes(directory / 'stderr', result.stderr)
    if result.returncode:
        raise RuntimeError('fresh sidecar failed: no automatic rerun')
    units = [u for u in setup['units'] if u['exp'] == job['exp'] and
             (job['config'] is None or u['config'] == job['config'])]
    matched = []
    for path in sorted((out / 'sidecars').glob('*.v6.fresh_test.audit.jsonl')):
        try:
            with path.open() as stream: header = json.loads(stream.readline())
        except FileNotFoundError:
            # A different completed invocation atomically published its own file.
            continue
        if (header['exp'], header['config']) not in {(u['exp'], u['config']) for u in units}: continue
        record = path.with_name(path.name.replace('.audit.', '.record.'))
        validate_sidecars(path, record, collect=False)
        for source, side in ((path, 'audit_side'), (record, 'record_side')):
            target = out / side / source.name
            # Atomic publication in physically distinct directories; no overwrite.
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists(): raise RuntimeError('fresh output already published')
            os.link(source, target); source.unlink(); matched.append(target)
    if len(matched) != 2 * len(units): raise RuntimeError('missing fresh sidecar unit')
    files = [started, directory / 'stdout', directory / 'stderr', *matched]
    doc = {'job': job, 'files': R.tree_hashes(out, files), 'units': len(units)}
    R.put(marker, doc)
    return doc


def sample(root: Path, out: Path, workers: int):
    import fcntl
    # Two operational invocations must never launch the same one-time sampler.
    with (out / 'sampling.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('another P6 sampler is active') from None
        return _sample(root, out, workers)


def _sample(root: Path, out: Path, workers: int):
    setup = phase_start(root, out, 'sample')
    if (out / 'sample.commit.json').exists(): return verify_commit(out, 'sample')
    R.put(out / 'opening.json', {'p5_seal_sha256': C.canonical_document(out / 'setup.json')['p5_seal_sha256'],
        'blocks': list(range(910036, 910056)), 'recipes': list(range(48, 60)),
        'one_time': True, 'automatic_replay': False})
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(lambda job: sample_job(root, out, setup, job), setup['jobs']))
    paths = [out / 'opening.json']
    for row in rows:
        paths.extend(out / p for p in row['files'])
        paths.append(out / 'jobs' / R.job_name(row['job']) / 'complete.json')
    return commit(out, 'sample', paths, {'status': 'PASS', 'units': sum(r['units'] for r in rows),
                                       'paths_per_unit': 7680, 'states_per_path': 65})


def read_header(path: Path):
    with path.open() as stream: return json.loads(stream.readline())


def validate_sidecars(audit: Path, record: Path, collect=True, wanted=None):
    """Strict cell/path/lens audit, independent of prediction and scoring outcomes."""
    ah, rh = read_header(audit), read_header(record)
    for header, schema in ((ah, 'test_b_v6_audit_v1'), (rh, 'test_b_v6_record_v1')):
        if header['schema'] != schema or header['mode'] != 'fresh_test' or header['path_steps'] != 64:
            raise RuntimeError('not fresh-test sidecar')
    if (ah['exp'], ah['config'], ah['source_header_sha256']) != (rh['exp'], rh['config'], rh['source_header_sha256']):
        raise RuntimeError('record/audit header mismatch')
    expected = {(b, a, l) for b in range(910036, 910056) for a in range(48, 60) for l in range(32)}
    paths = {}
    with audit.open() as stream:
        next(stream)
        for line in stream:
            row = json.loads(line); key = (row['block'], row['recipe'], row['replicate'])
            if row['type'] != 'path' or key not in expected or key in paths or len(row['states']) != 65:
                raise RuntimeError('invalid or duplicate audit path/cell')
            states = np.asarray(row['states'], dtype=int)
            if np.any(states < 0) or np.any(states >= ah['n']): raise RuntimeError('invalid micro state')
            paths[key] = states
    if set(paths) != expected: raise RuntimeError('missing audit test cells')
    contexts = {(c['k'], c['step_index']): c for c in rh['contexts'] if c['selected_h'] is not None}
    audit_maps = {(c['k'], c['step_index']): c for c in ah['contexts']}
    keys = set(contexts) if wanted is None else set(wanted)
    if not keys.issubset(contexts): raise RuntimeError('selected scoring context missing')
    keys = keys if collect else set()
    seen = set(); labels = {key: np.empty((20, 12, 32, 8), dtype=int) for key in keys}
    with record.open() as stream:
        next(stream)
        for line in stream:
            row = json.loads(line); cell = (row['block'], row['recipe'], row['replicate'])
            key = (row['k'], row['step_index']); unique = (key, cell)
            if row['type'] != 'path' or cell not in expected or key not in contexts or unique in seen:
                raise RuntimeError('invalid or duplicate record path/cell')
            h = contexts[key]['selected_h']
            if row['selected_h'] != h or row['split'] != 'test' or len(row['labels']) != 9:
                raise RuntimeError('wrong readings or split')
            q = np.asarray(audit_maps[key]['joint_by_state'])
            target = q[paths[cell][np.arange(9) * h]].tolist()
            if target != row['labels']: raise RuntimeError('record/micro path mismatch')
            if key in keys:
                b, a, l = cell; labels[key][b - 910036, a - 48, l] = target[1:]
            seen.add(unique)
    if len(seen) != len(expected) * len(contexts): raise RuntimeError('missing record test cells')
    return ah, rh, labels


def reversal_kl(law: np.ndarray):
    """Extended-real KL against path reversal, without flooring or smoothing.

    Reversal is an involution, hence KL = 1/2 sum (P-Q)(log P-log Q)
    on matched support. This equivalent expression avoids cancellation.
    """
    reverse = law.transpose(3,2,1,0)
    mismatch = (law > 0) & (reverse == 0)
    mass = float(law[mismatch].sum())
    matched = (law > 0) & (reverse > 0)
    value = float(.5 * np.sum((law[matched]-reverse[matched]) *
                  (np.log(law[matched])-np.log(reverse[matched]))))
    return {'KL_nats': 'Infinity' if np.any(mismatch) else value,
            'mismatched_mass': mass}


def exact_arrow(header: dict, context: dict, h: int):
    """§1 line 11; manager ruling: exact four-reading mixture path law.

    P_X(i,j,k,l)=mu_bar(i) K^h(i,j) K^h(j,k) K^h(k,l).
    P_Y is its deterministic joint-lens pushforward; no sampled labels enter.
    """
    if h not in (1,2,4,8) or len(header['recipes']) != 60:
        raise RuntimeError('invalid arrow lag or preparation set')
    K = np.asarray(header['kernel'],dtype=np.float64)
    T = np.linalg.matrix_power(K,h)
    q = np.asarray(context['joint_by_state'],dtype=np.int64)
    m = len(context['alphabet_raw_package'])
    mu = np.zeros(len(K),dtype=np.float64)
    for recipe in header['recipes'][48:60]:
        mu[recipe['states']] += np.asarray(recipe['weights_num'],dtype=float) / recipe['denominator'] / 12
    micro = (mu[:,None,None,None] * T[:,:,None,None] *
             T[None,:,:,None] * T[None,None,:,:])
    indices = (q[:,None,None,None]*m**3 + q[None,:,None,None]*m**2 +
               q[None,None,:,None]*m + q[None,None,None,:])
    record = np.bincount(indices.ravel(),weights=micro.ravel(),minlength=m**4).reshape((m,)*4)
    mx, ry = reversal_kl(micro), reversal_kl(record)
    def extended(value): return float('inf') if value == 'Infinity' else value
    assert extended(ry['KL_nats']) <= extended(mx['KL_nats']), 'path-reversal data processing violated'
    return {'record':ry, 'micro':mx, 'data_processing_assertion':'PASS',
            'definition':'D_KL(P(Y_0,Y_1,Y_2,Y_3) || P(Y_3,Y_2,Y_1,Y_0)); exact joint-lens pushforward',
            'path_measure':'equal-weight mixture of test-recipe preparations 48–59; fixed K at times 0,h,2h,3h',
            'micro_times':[0,h,2*h,3*h], 'recipe_ids':list(range(48,60)),
            'descriptive_only':True, 'smoothing':False}


def oracle_laws(header: dict, context: dict, h: int):
    K = np.asarray(header['kernel'], dtype=float)
    q = np.asarray(context['joint_by_state'], dtype=int)
    m = len(context['alphabet_raw_package']); Kh = np.linalg.matrix_power(K, h)
    law = np.empty((12, 8, m))
    for a, recipe in enumerate(header['recipes'][48:60]):
        mu = np.zeros(len(K)); mu[recipe['states']] = np.asarray(recipe['weights_num']) / recipe['denominator']
        for t in range(8):
            mu = mu @ Kh
            law[a, t] = np.bincount(q, weights=mu, minlength=m)
    return law


def evaluate_context(pred: dict, labels: np.ndarray, laws: np.ndarray):
    if labels.shape != (20,12,32,8) or laws.shape[:2] != (12,8):
        raise RuntimeError('wrong scoring dimensions')
    for p in pred['predictions'].values():
        p = np.asarray(p, dtype=float)
        if p.shape != laws.shape or not np.all(np.isfinite(p)) or np.any(p < 0) or not np.allclose(p.sum(-1), 1, atol=1e-12, rtol=0):
            raise RuntimeError('invalid sealed probability')
    losses = {name: V.sampled_loss(np.asarray(p), labels) for name, p in pred['predictions'].items()}
    square = losses['square']; rank = pred['rank']
    contrasts = {'D': (losses['selected_classical'] - square).mean(axis=(1, 2, 3)),
                 'G': (losses['diagonal'] - square).mean(axis=(1, 2, 3)),
                 'R': (square - losses[f'ed{rank}']).mean(axis=(1, 2, 3)),
                 'O': (losses['selected_order'] - square).mean(axis=(1, 2, 3))}
    oracle_loss = V.sampled_loss(laws, labels)
    report = {'paired_blocks': {k: v.tolist() for k, v in contrasts.items()},
              'selectors': pred['selectors'], 'models': {}}
    # §5: primary loss above the optimal record law; secondary calibration/TV.
    # Calibration here is pooled label-frequency minus mean forecast, not a new gate.
    observed = np.bincount(labels.ravel(), minlength=laws.shape[-1]) / labels.size
    for name, p in pred['predictions'].items():
        probabilities = S.scoring_probability(np.asarray(p))
        report['models'][name] = {'mean_log_loss': float(losses[name].mean()),
            'excess_log_loss': float((losses[name] - oracle_loss).mean()),
            'expected_excess': float(C.expected_excess(laws, np.asarray(p))),
            'mean_TV_to_oracle': float(.5 * np.abs(probabilities - laws).sum(axis=-1).mean()),
            'pooled_calibration_TV': float(.5 * np.abs(probabilities.mean(axis=(0,1)) - observed).sum()),
            'pooled_calibration_TV_definition': '0.5 sum_j |(1/96) sum_{a=48..59,t=1..8} p_tilde(a,t,j) - N_j/(20*12*32*8)|; N_j counts pooled observed future labels; descriptive only'}
    return contrasts, report


def campaign(rows: list[dict], margins: dict[int, float], bootstrap: dict):
    """Real claim predicate (no pseudo-campaign expected-separation extra gates)."""
    blocks = {'primary': {}, 'reversal': {}, 'order': {}}; scopes = {}; signals = {}
    for r in (2, 3, 4):
        group = [x for x in rows if x['rank'] == r]
        values = {x['id']: x['test_C_values'] for x in group}
        scopes[r] = S.scope_audit(values, {r: list(values)})[r]
        signals[r] = V.signal([x['laws'] for x in group])[0] if group else None
        for letter, family in [('D', 'primary'), ('G', 'primary'), ('R', 'reversal'), ('O', 'order')]:
            blocks[family][f'{letter}{r}'] = np.mean([x['contrasts'][letter] for x in group], axis=0) if group else None
    limits = {'primary': {f'{x}{r}': .01 if x == 'G' else margins[r] for r in (2,3,4) for x in ('D','G')},
              'reversal': {f'R{r}': margins[r] for r in (2,3,4)},
              'order': {f'O{r}': margins[r] for r in (2,3,4)}}
    inference = {f: V.inference(blocks[f], limits[f], f, bootstrap[f]) for f in blocks}
    ranks = {}
    for r in (2,3,4):
        scope = scopes[r]['status'] == 'in_scope'; nonempty = signals[r] is not None
        bounds = {x: inference[f]['bounds'][f'{x}{r}'] for x, f in
                  [('D','primary'),('G','primary'),('R','reversal'),('O','order')]}
        passed = C.rank_claim(nonempty, scope, signals[r] or 0., margins[r], bounds) if nonempty else False
        status = ('PASS' if passed else 'INELIGIBLE' if not nonempty else 'OUT_OF_ELIGIBLE_SCOPE'
                  if not scope else 'UNINFORMATIVE_AT_SELECTED_LAG' if signals[r] <= margins[r] else 'FAIL')
        gates = {'scope': scope, 'signal': bool(nonempty and signals[r] > margins[r]),
                 'primary_D': bool(nonempty and bounds['D'] > margins[r]),
                 'cross_terms_G': bool(nonempty and bounds['G'] > .01),
                 'no_reversal_R': bool(nonempty and bounds['R'] < margins[r]),
                 'order_O': bool(nonempty and bounds['O'] > margins[r])}
        ranks[str(r)] = {'status': status, 'pass': passed, 'gates': gates,
                         'margin': margins[r], 'bounds': bounds,
                         'scope': scopes[r], 'oracle_signal': signals[r]}
    statuses = {x['status'] for x in ranks.values()}
    category = next(x for x in ('PASS','FAIL','UNINFORMATIVE_AT_SELECTED_LAG','OUT_OF_ELIGIBLE_SCOPE','INELIGIBLE') if x in statuses)
    return {'category': category, 'ranks': ranks, 'inference': inference}


def calibration_sensitivity(root, entry, rank, header, context, labels):
    """§2:21 audit only: exact pushforward changes neither predictions nor selectors."""
    d = R.P5RecordLoader(root).load(root / 'record_view' / entry['file']).canonical()
    directory = root / 'fits/original' / f'{R.fit_identity(entry)}_r{rank}'
    model_doc = C.canonical_document(directory / 'models.json')
    if model_doc['canonical_to_original'] != d.to_original.tolist() or model_doc['table_hash'] != d.table_hash:
        raise RuntimeError('stored canonical model frame differs')
    models = R.load_bundle(directory / 'models.json')
    u = np.stack([d.u[a] for a in range(48,60)])
    # §4:55 scored zero-amplitude events invalidate, without modifying the model.
    torch = R.E.torch
    square = models['square']
    theta = torch.as_tensor(square.theta, dtype=R.E.DT)
    with torch.no_grad():
        U = R.E._qr(theta[:d.m*rank].reshape(d.m,rank))
        A = theta[d.m*rank:].reshape(rank,rank)
        A = A / torch.linalg.vector_norm(A).clamp_min(1e-12)
        z = torch.sqrt(torch.as_tensor(u,dtype=R.E.DT)) @ U
        for _ in range(8):
            z = z @ A.T
            if torch.any(torch.linalg.vector_norm(z @ U.T, dim=-1) < 1e-12):
                raise RuntimeError('scored square zero-amplitude event')
    q = np.asarray(context['joint_by_state']); exact = []
    for recipe in header['recipes'][48:60]:
        exact.append(np.bincount(q[recipe['states']],
                     weights=np.asarray(recipe['weights_num'])/recipe['denominator'], minlength=d.m))
    exact = np.asarray(exact)[:,d.to_original]
    result = {'exact_pushforward_TV': (.5*np.abs(exact-u).sum(-1)).tolist(),
              'rescored_mean_log_loss': {}, 'changes_primary': False,
              'parameter_counts': model_doc['parameter_counts']}
    for name, model in models.items():
        p = R.E.diagonal_predict(square,model.orientation,exact) if name == 'diagonal' else model.predict(exact)
        result['rescored_mean_log_loss'][name] = float(V.sampled_loss(d.transport(p),labels).mean())
    return result


def score(root: Path, out: Path):
    setup = phase_start(root, out, 'score')
    if (out / 'score.commit.json').exists(): return verify_commit(out, 'score')
    fit_commit = C.canonical_document(root / 'fit.commit.json')
    margins, _ = C.read_sealed_margins(root / 'fits/rank_margins.json', fit_commit['summary']['sealed_margin_sha256'])
    # Seal/copy margins before opening any sampled label row.
    R.put_bytes(out / 'margins.json', (root / 'fits/rank_margins.json').read_bytes())
    entries = R.eligible_entries(root, setup)
    selected = {(identity(entry),entry['h_c']) for entry,rank in entries}
    tests = {}
    with (out / 'census/sealed/test_census.jsonl').open() as stream:
        for line in stream:
            row = json.loads(line); key = (identity(row),row['h'])
            if key in selected: tests.setdefault(key, []).append(row)
    wanted = {}
    for entry, rank in entries:
        wanted.setdefault((entry['exp'],entry['config']),set()).add((entry['k'],entry['step_index']))
    units = {}
    for audit in sorted((out / 'audit_side').glob('*.v6.fresh_test.audit.jsonl')):
        header = read_header(audit); unit_key = (header['exp'],header['config'])
        if unit_key not in wanted: continue
        record = out / 'record_side' / audit.name.replace('.audit.', '.record.')
        data = validate_sidecars(audit, record, wanted=wanted[unit_key]); units[unit_key] = data
    rows = []; reports = []; arrow_cache = {}
    for entry, rank in entries:
        pred_path = root / 'fits/original' / f'{R.fit_identity(entry)}_r{rank}' / 'predictions.json'
        pred = S.open_sealed_predictions(pred_path)
        if pred['rank'] != rank or pred['recipe_ids'] != list(range(48,60)) or pred['reading_counts'] != list(range(1,9)) or pred['h_c'] != entry['h_c']:
            raise RuntimeError('prediction recipe/time/rank mismatch')
        ah, rh, labels = units[(entry['exp'], entry['config'])]
        key = (entry['k'], entry['step_index']); h = entry['h_c']
        context = next(c for c in ah['contexts'] if (c['k'], c['step_index']) == key)
        record_context = next(c for c in rh['contexts'] if (c['k'],c['step_index']) == key)
        mapping = hashlib.sha256(C.encoded({k:context[k] for k in ('raw_by_state','package_by_state')})).hexdigest()
        if mapping != entry['map_sha256'] or record_context['selected_h'] != h or record_context['m'] != entry['m']:
            raise RuntimeError('scoring context differs from frozen rank census')
        if identity(entry) not in arrow_cache:
            arrow_cache[identity(entry)] = exact_arrow(ah,context,h)
        laws = oracle_laws(ah, context, h)
        contrasts, report = evaluate_context(pred, labels[key], laws)
        test_rows = tests[(identity(entry), h)]
        if {(x['recipe'],x['t']) for x in test_rows} != {(a,t) for a in range(48,60) for t in range(8)} or len(test_rows) != 96:
            raise RuntimeError('test C95 is not the complete 12×8 census')
        constant = laws.mean(axis=(0,1)); gain, _ = V.signal([laws])
        cid = json.dumps(identity(entry), separators=(',',':'))
        rows.append({'id': cid, 'rank': rank, 'laws': laws, 'contrasts': contrasts,
                     'test_C_values': [x['C'] for x in test_rows]})
        report.update({'context': entry, 'rank': rank, 'test_C95': S.nearest_95([x['C'] for x in test_rows]),
                       'oracle_constant': constant.tolist(), 'oracle_signal': gain,
                       'arrow': arrow_cache[identity(entry)]})
        report['calibration_sensitivity'] = calibration_sensitivity(root,entry,rank,ah,context,labels[key])
        reports.append(report)
    if Counter(str(x['rank']) for x in rows) != Counter(RANK_COUNTS): raise RuntimeError('rank set changed')
    bs = {family: V.bootstrap_indices(family, out / 'bootstrap_cache') for family in ('primary','reversal','order')}
    verdict = campaign(rows, margins, bs)
    verdict.update({'schema': 'test_b_v6_1_real_verdict_v1', 'spec_sha256': R.SPEC_HASH,
        'p5_seal_sha256': C.canonical_document(out / 'setup.json')['p5_seal_sha256'],
        'contexts': reports, 'descriptive_controls': {
            'erasure': C.canonical_document(root / 'controls/erasure.json'),
            'random_mode': 'sealed training-only random-mode predictions scored in contexts.models',
            'training_audit': 'P5-sealed descriptive 1000-campaign audit; unchanged',
            'p5_controls_sha256': C.canonical_document(root / 'seal.commit.json')['files']},
        'arrow_note': 'Exact four-reading path-reversal audit under the equal-test-preparation mixture; extended-real support mismatch, no smoothing; descriptive only, no arrow claim.',
        'scope_claim': 'aggregate, preparation-relative approximate closure on the named preparation/time distribution'})
    verdict['per_source_secondary'] = {}
    for source in ('EXP-112','EXP-102–107'):
        verdict['per_source_secondary'][source] = {}
        for r in (2,3,4):
            group = [x for x in reports if x['rank'] == r and
                     (x['context']['exp'] == 'EXP-112') == (source == 'EXP-112')]
            verdict['per_source_secondary'][source][str(r)] = {
                'contexts':len(group), 'contrasts':{x:float(np.mean([np.mean(g['paired_blocks'][x]) for g in group]))
                    if group else None for x in ('D','G','R','O')}}
    R.put(out / 'verdict.json', verdict)
    paths = [out / 'verdict.json', out / 'margins.json', *sorted((out / 'bootstrap_cache').glob('*.npy'))]
    return commit(out, 'score', paths, {'status': 'COMPLETE', 'category': verdict['category']})




def record_failure(out: Path, phase: str, reason: str):
    document = {'category':'INVALID', 'status':'uncertified on this population',
                'phase':phase, 'reason':reason, 'scientific_square_pass_fail_issued':False}
    R.put(out / 'invalid.json', document)
    if not (out / 'verdict.json').exists(): R.put(out / 'verdict.json', document)




def phase_start(root: Path, out: Path, phase: str):
    """Require the supplied prior-stage prediction commit before opening data."""
    doc = C.canonical_document(Path(out)/'setup.json')
    if doc['p5_root'] != str(Path(root).resolve()):
        raise RuntimeError('new-run prediction root differs')
    if R.sha(Path(root)/'prediction_seal_manifest.json') != doc['p5_seal_sha256']:
        raise RuntimeError('new-run prediction commitment differs')
    setup = R.phase_start(Path(root), 'seal')
    for earlier in PHASES[:PHASES.index(phase)]:
        verify_commit(Path(out), earlier)
    return setup
