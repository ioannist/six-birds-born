"""P5: restartable real v6.1 train/validation sampling through prediction seal.

Rules cite frozen spec sections and physical line numbers. No test sampler or
locked-test-label loader exists here. Audit headers are read only by gates;
record workers receive only the hashed filtered record view.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from born_ladder.record_tests.workers import process_pool as ProcessPoolExecutor
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from types import SimpleNamespace

import numpy as np

from born_ladder.record_tests import cert_v6 as C, estimators as E, record_view_v6 as RV
from born_ladder.record_tests import generation_scorer as S, scorer_v6 as V
from born_ladder.record_tests.test_b_census_v6 import source_header

REPO = Path(__file__).resolve().parents[3]
SPEC = None  # configure() supplies a public registered specification
SPEC_HASH = '958c66539b1a1d91ceb9b567e837b2e1d947b3d85af395e315112921a7de743d'
DATA_DESIGN_HASH = RV.SPEC_HASH  # §v6.1 change log, line 154: census provenance carries forward.
PHASES = ('gates', 'sample', 'fit', 'seal')
PINS = ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS',
        'NUMEXPR_NUM_THREADS', 'RAYON_NUM_THREADS')
RULES = {
    'headers_replay_parity': '§2 lines 17,25',
    'calibration': '§2 lines 19,21: 60 recipes; independent 8192 Y0 labels',
    'paths': '§2 line 23: train 910001:910010×0:35; validation 910011:910015×36:47; 32×65 states',
    'loader': '§2 line 25: hashed record-only train/validation allowlist',
    'fit': '§4 lines 66,68,70,72,74,78,80: certified models, selectors, canonicalization, starts',
    'margins': '§5 lines 88,90: five isolated outer folds, six/two inner split, pre-test margins',
    'training_audit': '§5 line 113: 1000 descriptive campaigns; no design adaptation',
    'controls': '§6 line 139: equivariance, random modes, allowlist, structural erasure',
    'stop_at_seal': '§6 line 121: mandatory step (6), no step (7)',
}


CONTROL_RULES = {
    'schema': 'test_b_v6_1_p5_control_rules_v1',
    'structural_erasure': {'status': 'NOT_COMPUTED', 'diagnostic_only': True,
                          'make_erasure_refits': False},
    'relabeling_equivariance': {'mode': 'literal_full_refits', 'permutations': 22,
                              'tolerance': 1e-9},
    'training_block_audit': {'campaigns': 1000, 'resampled_vectors': 10,
                            'available_leave_two_out_vectors': 5,
                            'centered_margins': True, 'descriptive_only': True},
}
PRIOR_P5_DRIVER_HASH = '1341904ab7931de8dd3cba36d2838da1b5d0f90397fbb86fa72bbd82e27336c4'


def validate_control_rules(rules: dict) -> None:
    if C.encoded(rules) != C.encoded(CONTROL_RULES):
        raise ValueError('control_rules.json must encode the three approved manager rulings exactly')






def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def put(path: Path, document) -> str:
    """Canonical, exclusive creation; restarting verifies rather than overwrites."""
    return C.write_or_verify(path, document)


def put_bytes(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise RuntimeError(f'write-once artifact differs: {path}')
    else:
        with path.open('xb') as out:
            out.write(data); out.flush(); os.fsync(out.fileno())
    return hashlib.sha256(data).hexdigest()


def tree_hashes(root: Path, paths: list[Path]) -> dict:
    return {str(p.relative_to(root)): sha(p) for p in sorted(paths)}


def verify_files(root: Path, hashes: dict) -> None:
    for name, digest in hashes.items():
        path = root / name
        if path.resolve().is_relative_to(root.resolve()) is False or not path.is_file() or sha(path) != digest:
            raise RuntimeError(f'committed artifact differs: {path}')


def verify_phase(root: Path, phase: str) -> dict:
    manifest = C.canonical_document(root / f'{phase}.commit.json')
    if manifest['phase'] != phase or manifest['setup_sha256'] != sha(root / 'setup.json'):
        raise RuntimeError(f'phase/setup mismatch: {phase}')
    verify_files(root, manifest['files'])
    for name, digest in manifest['earlier_commits'].items():
        if sha(root / name) != digest:
            raise RuntimeError(f'earlier phase commitment differs: {name}')
    return manifest




def commit_phase(root: Path, phase: str, paths: list[Path], summary: dict) -> dict:
    earlier = {f'{p}.commit.json': sha(root / f'{p}.commit.json')
               for p in PHASES[:PHASES.index(phase)]}
    document = {'schema': 'test_b_p5_phase_v1', 'phase': phase,
                'setup_sha256': sha(root / 'setup.json'),
                'earlier_commits': earlier, 'files': tree_hashes(root, paths),
                'summary': summary, 'spec_rules': RULES}
    put(root / f'{phase}.commit.json', document)
    return document


def unit_key(unit: dict) -> tuple:
    return unit['exp'], unit['config']


def job_name(job: dict) -> str:
    return job['exp'] + ('_' + job['config'] if job['config'] else '')




def runner_command(setup: dict, job: dict, sidecars: Path | None = None) -> list[str]:
    args = [setup['inputs']['runner'], '--exp', job['exp'], '--seed',
            '910000' if sidecars else '0', '--scale', '32']
    if job['config']: args += ['--config', job['config']]
    if sidecars is not None:
        # §2 line 23: this entry point cannot select v6-fresh-test.
        args += ['--test-b-sidecar-dir', str(sidecars.resolve()),
                 '--test-b-sidecar-phase', 'v6-trainval',
                 '--test-b-sidecar-source-audit-dir', setup['inputs']['audit_dir']]
    return args


    # Never copy/open full, validation, or test C files in P5.




def normalized(raw: bytes) -> bytes:
    # §2 line 25, RB1 contract: only KEY_AUDIT_JSON.git_sha.
    lines = []
    for line in raw.splitlines(keepends=True):
        if line.startswith(b'KEY_AUDIT_JSON'):
            line, count = re.subn(rb'("git_sha"\s*:\s*)"(?:\\.|[^"\\])*"',
                                  rb'\1"<normalized>"', line, count=1)
            if count != 1: raise RuntimeError('missing parity git_sha')
        lines.append(line)
    return b''.join(lines)


def legacy_hashes(path: Path) -> dict:
    out = (path / 'stdout').read_bytes()
    return {'stdout_raw': hashlib.sha256(out).hexdigest(),
            'stdout_normalized': hashlib.sha256(normalized(out)).hexdigest(),
            'stderr': sha(path / 'stderr'),
            'other_files': {str(p.relative_to(path)): sha(p) for p in sorted(path.rglob('*'))
                            if p.is_file() and p.name not in ('stdout', 'stderr', 'check.json')}}




class P5RecordLoader:
    """§2 line 25: exact hashed v6 record manifest, no alternate input paths."""
    def __init__(self, root: Path):
        self.root = root.resolve()
        # A record worker must not hash/open audit files merely to verify a
        # phase. The orchestration phase verifies those separately.
        self.commit = C.canonical_document(self.root / 'sample.commit.json')
        if self.commit['phase'] != 'sample' or self.commit['setup_sha256'] != sha(self.root / 'setup.json'):
            raise RuntimeError('record manifest phase/setup mismatch')
        manifest_path = self.root / 'record_view/manifest.json'
        if sha(manifest_path) != self.commit['files']['record_view/manifest.json']:
            raise RuntimeError('trainval manifest is not committed')
        self.loader = E.RecordAllowlist(manifest_path)
        if self.loader.design != 'v6': raise PermissionError('P5 requires v6 record cells')

    def load(self, path: Path):
        raw = self.loader.load(path)
        expected = {(b,a,r) for b in range(910001,910011) for a in range(36) for r in range(32)}
        expected |= {(b,a,r) for b in range(910011,910016) for a in range(36,48) for r in range(32)}
        if set(zip(raw.blocks.tolist(),raw.recipes.tolist(),raw.replicates.tolist())) != expected:
            raise PermissionError('record cells differ from exact P5 allowlist')
        entry = self.loader.allowed[str(Path(path).resolve())]
        return replace(raw, context=raw.context+f"::h{entry['h_c']}")  # §1 lines 11,13.


def validate_sample(record: Path, audit: Path, unit: dict) -> dict:
    """Audit separation/counts, never compute outcomes or read held-out C."""
    with audit.open('rb') as stream:
        ah = json.loads(stream.readline()); paths = set(); calibrations = set()
        if ah['schema'] != 'test_b_v6_audit_v1' or ah['mode'] != 'trainval' or \
           ah['source_header_sha256'] != unit['sealed_kernel_header_sha256']:
            raise RuntimeError('sample audit header differs')
        for line in stream:
            row = json.loads(line)
            if row['type'] == 'calibration':
                if not 0 <= row['recipe'] < 60 or len(row['states']) != 8192:
                    raise RuntimeError('invalid calibration audit')
                if row['recipe'] in calibrations: raise RuntimeError('duplicate calibration')
                calibrations.add(row['recipe'])
            elif row['type'] == 'path':
                E._split(row['recipe'], row['block'], 'v6')
                key = (row['block'], row['recipe'], row['replicate'])
                if key in paths or not 0 <= row['recipe'] < 48 or not 0 <= row['replicate'] < 32 or len(row['states']) != 65:
                    raise RuntimeError('invalid/duplicate sampled path')
                paths.add(key)
            else: raise RuntimeError('undeclared audit row')
        if len(paths) != 13440 or calibrations != set(range(60)):
            raise RuntimeError('sample count differs from frozen cells')
    with record.open('rb') as stream:
        rh = json.loads(stream.readline())
        if rh['mode'] != 'trainval' or rh['schema'] != 'test_b_v6_record_v1' or \
           rh['source_header_sha256'] != ah['source_header_sha256']:
            raise RuntimeError('record/audit header mismatch')
    return {'micro_paths': len(paths), 'calibration_readings': 60 * 8192,
            'micro_transitions': len(paths) * 64, 'record_sha256': sha(record), 'audit_sha256': sha(audit)}


def calibration_census(record_dir: Path, destination: Path) -> dict:
    support_rows = []; duplicates = []; alphabets = []
    for path in sorted(record_dir.glob('*.record.jsonl')):
        with path.open('rb') as stream:
            header = json.loads(stream.readline())
            contexts = {(c['k'], c['step_index']): c for c in header['contexts']}
            counts = {}
            for line in stream:
                row = json.loads(line)
                if row['type'] != 'calibration': continue
                c = contexts[row['k'], row['step_index']]; m = c['m']; a = row['recipe']
                value = np.bincount(row['labels'], minlength=m)
                p = value / 8192; z = 1.959963984540054
                center = (p + z*z/(2*8192))/(1+z*z/8192)
                half = z*np.sqrt(p*(1-p)/8192 + z*z/(4*8192**2))/(1+z*z/8192)
                identity = {'exp': header['exp'], 'config': header['config'],
                            'k': c['k'], 'step_index': c['step_index']}
                support_rows.append({**identity, 'recipe': a,
                    'split': 'train' if a < 36 else 'validation' if a < 48 else 'test_calibration_only',
                    'counts': value.tolist(), 'u': p.tolist(), 'support': int(np.count_nonzero(value)),
                    'wilson95': np.stack([center-half, center+half], axis=1).tolist(),
                    'calibration_label_sha256': hashlib.sha256(C.encoded(row['labels'])).hexdigest()})
                counts.setdefault((row['k'], row['step_index']), {}).setdefault(tuple(value), []).append(a)
            for (k, step), groups in counts.items():
                c = contexts[k, step]
                alphabets.append({'exp': header['exp'], 'config': header['config'], 'k': k,
                                  'step_index': step, 'alphabet': c['alphabet_raw_package']})
                for value, recipes in groups.items():
                    split = lambda a: 0 if a < 36 else 1 if a < 48 else 2
                    if len({split(a) for a in recipes}) > 1:
                        duplicates.append({'exp': header['exp'], 'config': header['config'],
                            'k': k, 'step_index': step, 'counts': list(value), 'recipes': recipes})
    put(destination / 'u_support.json', support_rows)
    put(destination / 'u_duplicates.json', duplicates)
    put(destination / 'alphabets.json', alphabets)
    return {'calibration_context_recipe_rows': len(support_rows),
            'cross_split_duplicate_vectors': len(duplicates),
            'support_histogram': {str(s): sum(row['support'] == s for row in support_rows)
                                  for s in sorted({row['support'] for row in support_rows})}}




def predictions(models: dict, d: E.CanonicalData, recipes=range(48, 60)) -> dict:
    u = np.stack([d.u[a] for a in recipes])
    output = {}
    for name, model in models.items():
        pred = E.diagonal_predict(models['square'], model.orientation, u) if name == 'diagonal' else model.predict(u)
        if not np.all(np.isfinite(pred)) or np.any(pred < 0): raise RuntimeError('invalid model probability')
        output[name] = d.transport(pred)
    return output


def fit_identity(entry: dict) -> str:
    return Path(entry['file']).stem.removeprefix('v6_trainval_')


def load_bundle(path: Path) -> dict:
    document = C.canonical_document(path)
    output = {}
    for name, raw in document['models'].items():
        raw = dict(raw)
        for field in ('theta', 'fixed_u', 'orientation'):
            if raw.get(field) is not None: raw[field] = np.asarray(raw[field], dtype=float)
        output[name] = E.Fit(**raw)
    return output


def fit_record_job(item: tuple) -> dict:
    root_string, entry, rank, fold, erasure = item
    root = Path(root_string)
    if erasure:
        raise ValueError('manager ruled structural erasure NOT_COMPUTED; refits prohibited')
    loader = P5RecordLoader(root)
    raw = loader.load(root / 'record_view' / entry['file'])
    d = raw.canonical()
    if fold is not None: d, held = C.fold_record(d, fold)
    tag = 'original'
    stem = f'{fit_identity(entry)}_r{rank}' + (f'_fold{fold}' if fold is not None else '')
    directory = root / 'fits' / tag / stem
    marker = directory / 'result.json'
    if marker.exists():
        result = C.canonical_document(marker); verify_files(root, result['files']); return result
    started = time.monotonic()
    models = E.fit_family(d, rank)  # §4: the certified four-family and control path.
    model_doc = {'models': {name: asdict(model) for name, model in models.items()},
                 'canonical_to_original': d.to_original.tolist(), 'table_hash': d.table_hash,
                 'context': d.context, 'm': d.m, 'rank': rank,
                 'parameter_counts': {name: E.parameter_counts(d.m, rank, model.kind, model.k)
                                      for name, model in models.items() if model.kind != 'diagonal'}}
    put(directory / 'models.json', model_doc)
    if fold is None:
        output = predictions(models, d)
        payload = {'context_file': entry['file'], 'rank': rank, 'control': tag,
                   'recipe_ids': list(range(48, 60)), 'reading_counts': list(range(1, 9)),
                   'predictions': {k: v.tolist() for k, v in output.items()},
                   'selectors': {'classical': [models['selected_classical'].kind, models['selected_classical'].k],
                                 'order': models['selected_order'].kind},
                   'table_hash': d.table_hash, 'h_c': entry['h_c']}
        C.seal_or_verify_prediction(directory / 'predictions.json', payload)
        artifact_paths = [directory / 'models.json', directory / 'predictions.json',
                          directory / 'predictions.json.seal.json']
        fold_values = None
    else:
        # Same inner fitting/canonicalization as C.fold_contrast; evaluation
        # uses only the two outer record blocks, no micro plant adapter.
        output = predictions(models, d, range(36))
        losses = {}
        for name, pred in output.items():
            per_block = []
            for block in held:
                labels = np.stack([raw.labels[(raw.blocks == block) & (raw.recipes == a), 1:]
                                   for a in range(36)])[None, ...]
                per_block.append(float(C.label_loss(pred, labels).mean()))
            losses[name] = np.array(per_block)
        fold_values = {'D': (losses['selected_classical']-losses['square']).tolist(),
                       'G': (losses['diagonal']-losses['square']).tolist(),
                       'R': (losses['square']-losses[f'ed{rank}']).tolist(),
                       'O': (losses['selected_order']-losses['square']).tolist()}
        put(directory / 'outer_contrasts.json', {'fold': fold, 'blocks': held, 'contrasts': fold_values,
             'inner_train_blocks': d.fold_train_blocks, 'inner_validation_blocks': d.fold_validation_blocks,
             'table_hash': d.table_hash})
        artifact_paths = [directory / 'models.json', directory / 'outer_contrasts.json']
    actual = [model for name, model in models.items() if not name.startswith('selected_')]
    result = {'context_file': entry['file'], 'rank': rank, 'fold': fold, 'control': tag,
              'fold_contrasts': fold_values, 'failed_fits': sum(model.failed for model in actual),
              'invalid_starts': sum((model.metadata or {}).get('invalid_starts', 0) for model in actual),
              'start_count': (len(actual)-1)*E.V5_STARTS,
              'wall_seconds': time.monotonic()-started, 'files': tree_hashes(root, artifact_paths)}
    put(marker, result)
    return result


def eligible_entries(root: Path, setup: dict) -> list[tuple[dict, int]]:
    manifest = C.canonical_document(root / 'record_view/manifest.json')
    census = json.loads(Path(setup['inputs']['census']).read_bytes())
    result = []
    for entry in manifest['allowed_files']:
        for rank in (2, 3, 4):
            if any((entry['exp'], entry['config'], entry['k'], entry['step_index'], entry['map_sha256']) ==
                   (c['exp'], c['config'], c['k'], c['step_index'], c['map_sha256'])
                   for c in census['rank_contexts'][str(rank)]):
                result.append((entry, rank))
    return result


def fit(root: Path, workers: int) -> dict:
    setup = phase_start(root, 'fit')
    if (root / 'fit.commit.json').exists(): return verify_phase(root, 'fit')
    entries = eligible_entries(root, setup)
    tasks = [(str(root), e, r, f, False) for e, r in entries for f in (None, 0, 1, 2, 3, 4)]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(fit_record_job, tasks))
    failed = sum(row['failed_fits'] for row in results)
    invalid = sum(row['invalid_starts'] for row in results); starts = sum(row['start_count'] for row in results)
    if starts and invalid/starts > .01:
        put(root / 'invalid.json', {'status': 'INVALID', 'phase': 'fit', 'reason': 'invalid starts >1%'})
        raise RuntimeError('optimizer validity gate failed')
    # §5 lines 90–92: reuse certified equal-context fold aggregation/margin sealer.
    rows = {}; members = {r: [] for r in (2, 3, 4)}
    for index, entry in enumerate(C.canonical_document(root / 'record_view/manifest.json')['allowed_files']):
        ranks = {}
        for e, rank in entries:
            if e['file'] != entry['file']: continue
            members[rank].append(index)
            group = [next(row for row in results if row['context_file'] == e['file'] and
                          row['rank'] == rank and row['fold'] == f) for f in range(5)]
            ranks[str(rank)] = {'folds': [(float(np.mean(row['fold_contrasts']['D'])),
                row['failed_fits'], row['invalid_starts'], row['start_count']) for row in group]}
        rows[index] = {'ranks': ranks}
    margin_path = root / 'fits/rank_margins.json'
    if not margin_path.exists(): C.seal_rank_margins(margin_path, rows, members)
    else:
        check = root / 'fits/rank_margins.check.json'
        try:
            C.seal_rank_margins(check, rows, members)
            if check.read_bytes() != margin_path.read_bytes(): raise RuntimeError('saved margin changed')
        finally: check.unlink(missing_ok=True)
    put(root / 'fits/timing.json', results)
    paths = [p for p in (root / 'fits').rglob('*') if p.is_file()]
    return commit_phase(root, 'fit', paths, {'status': 'PASS', 'context_rank_fits': len(entries),
        'family_fit_calls': len(tasks), 'failed_fits': failed, 'invalid_starts': invalid,
        'start_count': starts, 'sealed_margin_sha256': sha(margin_path)})


def record_alphabet(root: Path, entry: dict) -> np.ndarray:
    commitment = C.canonical_document(root / 'sample.commit.json')
    if sha(root / 'record_side/alphabets.json') != commitment['files']['record_side/alphabets.json']:
        raise RuntimeError('record alphabet hash mismatch')
    rows = C.canonical_document(root / 'record_side/alphabets.json')
    matches = [r for r in rows if (r['exp'], r['config'], r['k'], r['step_index']) ==
               (entry['exp'], entry['config'], entry['k'], entry['step_index'])]
    if len(matches) != 1: raise RuntimeError('record alphabet missing')
    return np.asarray(matches[0]['alphabet'], dtype=np.int64)


def control_seed(kind: str, context: str, *parts) -> int:
    return int.from_bytes(hashlib.sha256(f'TestB/v6/real/{kind}/{SPEC_HASH}/{context}/'.encode() +
        '/'.join(map(str, parts)).encode()).digest()[:16], 'little')


def erasure_diagnostics(root: Path, entries: list) -> dict:
    """Registered zero-refit disposition plus arithmetic alphabet diagnostics."""
    from .erasure import diagnostics
    return diagnostics(entries, lambda entry: record_alphabet(root, entry))


def erasure_not_computed(root: Path, entries: list, rules: dict) -> dict:
    """Legacy explanatory wrapper; scientific arithmetic has one implementation."""
    return {**erasure_diagnostics(root, entries),
        'spec_reference': '§6 line 139',
        'spec_quote': 'Erasure is diagnostic; equivariance or leakage failure invalidates v6.',
        'manager_ruling': 'Report structural erasure NOT_COMPUTED: the frozen estimator cannot run '
            'on the re-paired product alphabet. Make no erasure refits and invent no encoding, '
            'calibration rule or estimator change. Erasure cannot change a gate or the verdict.',
        'manager_approval': rules['manager_approval']}


def canonical_signature(d: E.CanonicalData) -> str:
    # Includes every model-visible fitting/control input, excludes representation
    # transport maps, which are separately checked on predictions.
    document = asdict(d)
    document.pop('to_original'); document.pop('from_original')
    return hashlib.sha256(C.encoded(document)).hexdigest()


def literal_relabel_case(item: tuple) -> dict:
    """Actual full fit, or verified checkpoint of that same actual full fit; never fit reuse."""
    root_string, entry, rank, index = item
    root = Path(root_string)
    marker = root / 'controls/full_relabel_refits' / f'{fit_identity(entry)}_r{rank}_p{index:02d}.json'
    raw = P5RecordLoader(root).load(root / 'record_view' / entry['file']); base = raw.canonical()
    permutations = [np.arange(raw.m), np.arange(raw.m)[::-1]]
    permutations += [np.random.default_rng(control_seed('relabel', raw.context, i)).permutation(raw.m)
                     for i in range(20)]
    permutation = permutations[index]
    renamed = replace(raw, labels=permutation[raw.labels],
                      calibration={a: permutation[y] for a, y in raw.calibration.items()})
    d = renamed.canonical(original_ids=np.argsort(permutation))
    if canonical_signature(d) != canonical_signature(base):
        raise RuntimeError('relabeling changed canonical fitting inputs or seeds')
    model_path = root / 'fits/original' / f'{fit_identity(entry)}_r{rank}' / 'models.json'
    stored = C.canonical_document(model_path)
    model_hash = hashlib.sha256(C.encoded(stored['models'])).hexdigest()
    orphan = None
    if marker.exists():
        if marker.with_name(marker.name+'.seal.json').exists():
            row = S.open_sealed_predictions(marker)
        else:
            # The pre-ruling 66 literal fits were already bound by the pending
            # manifest. Adopt those checkpoints without rewriting any row.
            pending_path = root / 'prediction_seal_manifest.pending.json'
            pending = C.canonical_document(pending_path) if pending_path.exists() else {}
            name = str(marker.relative_to(root))
            row = C.canonical_document(marker)
            if pending.get('files', {}).get(name) != sha(marker):
                orphan = row  # Interrupted before its seal: refit, compare, never overwrite.
        expected = {'context_file': entry['file'], 'rank': rank, 'permutation_index': index,
            'permutation': permutation.tolist(), 'actual_full_fit_rerun': True, 'fit_start_budget': 96,
            'canonical_input_sha256': canonical_signature(d),
            'regenerated_models_sha256': model_hash, 'model_and_selector_bytes_equal': True}
        if C.encoded({k: row.get(k) for k in expected}) != C.encoded(expected) or \
           not 0 <= row.get('maximum_prediction_error', float('inf')) <= 1e-9 or \
           not 0 <= row.get('maximum_loss_error', float('inf')) <= 1e-9:
            raise RuntimeError('literal-refit checkpoint does not match frozen inputs/model/results')
        if orphan is None:
            put(marker.with_name(marker.name+'.seal.json'),
                {'path': str(marker.resolve()), 'sha256': sha(marker), 'bytes': marker.stat().st_size})
            return row
    started = time.monotonic()
    models = E.fit_family(d, rank)  # §4 line 68: rerun the entire frozen pipeline.
    model_bytes = C.encoded({name: asdict(model) for name, model in models.items()})
    if model_bytes != C.encoded(stored['models']):
        raise RuntimeError('regenerated canonical fit/selector bytes differ')
    original = load_bundle(model_path)
    base_pred = predictions(original, base); candidate = predictions(models, d)
    errors = {name: float(np.max(np.abs(pred[..., permutation]-base_pred[name])))
              for name, pred in candidate.items()}
    losses = {name: max(abs(model.train_loss-original[name].train_loss),
                       abs(model.validation_loss-original[name].validation_loss))
              for name, model in models.items()}
    if max(errors.values()) > 1e-9 or max(losses.values()) > 1e-9:
        raise RuntimeError('literal-refit relabeling equivariance failed')
    row = {'context_file': entry['file'], 'rank': rank, 'permutation_index': index,
        'permutation': permutation.tolist(), 'actual_full_fit_rerun': True, 'fit_start_budget': 96,
        'canonical_input_sha256': canonical_signature(d),
        'regenerated_models_sha256': hashlib.sha256(model_bytes).hexdigest(),
        'model_and_selector_bytes_equal': True, 'maximum_prediction_error': max(errors.values()),
        'maximum_loss_error': max(losses.values()), 'wall_seconds': time.monotonic()-started}
    if orphan is not None:
        row['wall_seconds'] = orphan['wall_seconds']
        if C.encoded(row) != C.encoded(orphan):
            raise RuntimeError('regenerated literal-refit row differs from unsealed orphan')
    put(marker, row)
    put(marker.with_name(marker.name+'.seal.json'),
        {'path': str(marker.resolve()), 'sha256': sha(marker), 'bytes': marker.stat().st_size})
    return row


def literal_relabel_refits(root: Path, entries: list, workers: int) -> dict:
    tasks = [(str(root), e, r, i) for e, r in entries for i in range(22)]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(literal_relabel_case, tasks))
    result = {'status': 'PASS', 'actual_full_refits': len(rows), 'permutations_per_context_rank': 22,
        'maximum_prediction_error': max((r['maximum_prediction_error'] for r in rows), default=0.),
        'maximum_loss_error': max((r['maximum_loss_error'] for r in rows), default=0.),
        'spec_rule': '§4 line 68; §6 line 139',
        'checkpoint_sha256': {str((root / 'controls/full_relabel_refits' /
            f"{fit_identity(e)}_r{r}_p{i:02d}.json").relative_to(root)):
            sha(root / 'controls/full_relabel_refits' / f"{fit_identity(e)}_r{r}_p{i:02d}.json")
            for e, r in entries for i in range(22)}, 'rows': rows}
    put(root / 'controls/relabeling_literal.json', result)
    return result


_TRAINING_BS = None


def training_audit_initialize(cache: str):
    global _TRAINING_BS
    _TRAINING_BS = {family: V.bootstrap_indices(family, Path(cache))
                    for family in ('primary', 'reversal', 'order')}


def training_audit_case(item):
    campaign, rank_vectors, margins = item
    bs = _TRAINING_BS
    rng = np.random.default_rng(control_seed('training_audit', 'equal_context', campaign))
    # Draw ten leave-two-out pairs -> twenty blocks, preserving each pair.
    pairs = rng.integers(0, 5, 10)
    indices = np.array([block for f in pairs for block in (2*f, 2*f+1)])
    result = {'campaign': campaign, 'resampled_pairs': pairs.tolist()}
    for mode in ('observed', 'at_margins'):
        blocks = {family: {} for family in bs}
        limits = {'primary': {f'{letter}{r}': .01 if letter == 'G' else margins.get(r, .01)
                              for r in (2, 3, 4) for letter in ('D', 'G')},
                  'reversal': {f'R{r}': margins.get(r, .01) for r in (2, 3, 4)},
                  'order': {f'O{r}': margins.get(r, .01) for r in (2, 3, 4)}}
        for rank in (2, 3, 4):
            for letter, family in (('D', 'primary'), ('G', 'primary'), ('R', 'reversal'), ('O', 'order')):
                values = None
                if rank in rank_vectors:
                    values = rank_vectors[rank][letter][indices].copy()
                    if mode == 'at_margins': values += limits[family][f'{letter}{rank}']-rank_vectors[rank][letter].mean()
                blocks[family][f'{letter}{rank}'] = values
        # Descriptive rejection rates at fixed thresholds: shared bootstrap
        # p-values and exact Holm; no bounds/scope/signal are promoted here.
        inference = {}
        for family, slots in blocks.items():
            p = {}
            for slot, values in slots.items():
                p[slot] = 1. if values is None else S.centered_p(
                    -values if family == 'reversal' else values,
                    -limits[family][slot] if family == 'reversal' else limits[family][slot], bs[family])
            inference[family] = {'p_raw': p, 'holm': S.holm(p, family)}
        result[mode] = inference
    return result


def training_audit(root: Path, entries: list, workers: int) -> dict:
    """Descriptive only, §5 line 113; manager approved ten paired resamples and margin centering."""
    margins, _ = C.read_sealed_margins(root / 'fits/rank_margins.json', sha(root / 'fits/rank_margins.json'))
    rank_vectors = {}; by_rank = {r: [] for r in (2, 3, 4)}
    for entry, rank in entries:
        contrasts = {letter: [] for letter in ('D', 'G', 'R', 'O')}
        for fold in range(5):
            row = C.canonical_document(root / 'fits/original' /
                       f'{fit_identity(entry)}_r{rank}_fold{fold}' / 'outer_contrasts.json')
            for letter in contrasts: contrasts[letter].extend(row['contrasts'][letter])
        by_rank[rank].append(contrasts)
    for rank, contexts in by_rank.items():
        if contexts: rank_vectors[rank] = {letter: np.mean([c[letter] for c in contexts], axis=0)
                                         for letter in ('D', 'G', 'R', 'O')}
    bs = {family: V.bootstrap_indices(family, root / 'controls/bootstrap_cache')
          for family in ('primary', 'reversal', 'order')}
    with ProcessPoolExecutor(max_workers=workers, initializer=training_audit_initialize,
                             initargs=(str(root / 'controls/bootstrap_cache'),)) as pool:
        rows = list(pool.map(training_audit_case,
                    [(i, rank_vectors, margins) for i in range(1000)]))
    rates = {mode: {family: {slot: float(np.mean([
        row[mode][family]['holm']['reject'][slot] for row in rows]))
        for slot in rows[0][mode][family]['p_raw']} for family in bs}
        for mode in ('observed', 'at_margins')}
    put(root / 'controls/training_audit_1000.json', {'descriptive': True, 'campaigns': rows,
        'rank_training_vectors': rank_vectors, 'margins': margins, 'rejection_rates': rates,
        'seed_domain': 'TestB/v6/real/training_audit', 'resampling': '10 leave-two-out pairs →20 blocks'})
    return {'campaigns': 1000, 'descriptive': True, 'rejection_rates': rates}










def phase_start(root: Path, phase: str) -> dict:
    """Check earlier numerical checkpoints; no source or process receipts."""
    setup = C.canonical_document(Path(root)/'setup.json')
    if setup['spec_sha256'] != SPEC_HASH:
        raise RuntimeError('scientific v6.1 identity changed')
    for earlier in PHASES[:PHASES.index(phase)]:
        verify_phase(Path(root), earlier)
    return setup
