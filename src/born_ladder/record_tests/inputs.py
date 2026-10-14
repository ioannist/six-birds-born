"""Explicit, relocated local evidence for an already-opened Test B archive.

The caller supplies the input-receipt digest from a trusted receipt. Paths in
historical seals are identities, never filesystem discovery instructions.
All committed data are verified before any record outcome is read.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

SPEC_HASH = '958c66539b1a1d91ceb9b567e837b2e1d947b3d85af395e315112921a7de743d'
P5_HASH = 'bb905ee637d7e63e9ebe78a9aceb50dff2bba28f39f6c9d469bdc5aa1093094c'
VERDICT_HASH = '48ec464e7be055f33a28880b4b2f70415caa30bdbb6c0f5012023d501b888d9e'
RANK_COUNTS = {'2': 8, '3': 6, '4': 6}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def document(path):
    return json.loads(Path(path).read_bytes())


def safe_path(root, name):
    root = Path(root).resolve(strict=True)
    path = root / name
    if Path(name).is_absolute() or not path.resolve().is_relative_to(root):
        raise ValueError(f'evidence path escapes input root: {name}')
    if not path.is_file():
        raise FileNotFoundError(f'missing explicit Test B input: {path}')
    return path


class Inputs:
    """Read-only allowlist, independently supplied roots and receipt commitment."""

    def __init__(self, manifest, expected_sha256, *, sealed_root, opened_root,
                 certification_root):
        if sha(manifest) != expected_sha256:
            raise ValueError('input receipt hash mismatch')
        self.receipt = document(manifest)
        if self.receipt.get('schema') != 'test_b_score_inputs_v1':
            raise ValueError('wrong input receipt schema')
        self.roots = dict(p5=Path(sealed_root), p6=Path(opened_root),
                          cert=Path(certification_root))
        self.files = self.receipt['files']
        if set(self.files) != set(self.roots):
            raise ValueError('incomplete input roots')
        self.verified = set()
        for root, members in self.files.items():
            for name, digest in members.items():
                path = safe_path(self.roots[root], name)
                if sha(path) != digest:
                    raise ValueError(f'committed input differs: {root}/{name}')
                self.verified.add((root, name))
        self._verify_chain()

    def path(self, root, name):
        if (root, name) not in self.verified:
            raise PermissionError(f'uncommitted input: {root}/{name}')
        return safe_path(self.roots[root], name)

    def read(self, root, name):
        return document(self.path(root, name))

    def check(self, root, name, digest):
        if self.files[root].get(name) != digest:
            raise ValueError(f'commitment not in receipt: {root}/{name}')
        self.path(root, name)

    def _verify_chain(self):
        self.check('p5', 'prediction_seal_manifest.json', P5_HASH)
        self.check('p6', 'verdict.json', VERDICT_HASH)
        seal = self.read('p5', 'prediction_seal_manifest.json')
        if (seal['spec_sha256'] != SPEC_HASH or seal['subset_nonconfirmatory']
            or seal['mandatory_order_completed'] != 6 or seal['locked_test_sampled_or_opened']
            or seal['rank_context_counts'] != RANK_COUNTS):
            raise ValueError('incompatible or subset prediction seal')
        setup_sha = self.files['p5']['setup.json']
        if seal['setup_sha256'] != setup_sha:
            raise ValueError('P5 setup differs')
        union = {}
        for phase in ('gates', 'sample', 'fit', 'seal'):
            name = f'{phase}.commit.json'
            commit = self.read('p5', name)
            if commit['phase'] != phase or commit['setup_sha256'] != setup_sha:
                raise ValueError('P5 phase/setup differs')
            for file, digest in {**commit['files'], **commit['earlier_commits']}.items():
                self.check('p5', file, digest)
            union.update(commit['files'])
            union[name] = self.files['p5'][name]
            if commit['summary']['status'] != 'PASS':
                raise ValueError('P5 gate not passed')
        if union != seal['files']:
            raise ValueError('P5 transitive seal incomplete')
        p6_setup = self.read('p6', 'setup.json')
        if p6_setup['p5_seal_sha256'] != P5_HASH or p6_setup['spec_sha256'] != SPEC_HASH:
            raise ValueError('P6 source seal differs')
        for phase in ('prepare', 'sample', 'score'):
            commit = self.read('p6', f'{phase}.commit.json')
            if commit['phase'] != phase or commit['p6_setup_sha256'] != self.files['p6']['setup.json']:
                raise ValueError('P6 phase/setup differs')
            for name, digest in commit['files'].items():
                self.check('p6', name, digest)
            for earlier, digest in commit['earlier'].items():
                self.check('p6', f'{earlier}.commit.json', digest)
        if self.read('p6', 'score.commit.json')['summary']['status'] != 'COMPLETE':
            raise ValueError('archive was not already scored')
        fit = self.read('p5', 'fit.commit.json')
        digest = fit['summary']['sealed_margin_sha256']
        self.check('p5', 'fits/rank_margins.json', digest)
        self.check('p6', 'margins.json', digest)
        release = self.read('p6', 'census/eligibility.json')
        for name, key in [('training_census.jsonl', 'training_census_sha256'),
                          ('sealed/full_census.jsonl', 'full_census_sha256'),
                          ('sealed/validation_census.jsonl', 'sealed_validation_census_sha256'),
                          ('sealed/test_census.jsonl', 'sealed_test_census_sha256'),
                          ('sealed/recipe_audit.jsonl', 'sealed_recipe_audit_sha256')]:
            self.check('p6', 'census/' + name, release[key])
        for family in ('primary', 'reversal', 'order'):
            name = f'bootstrap_{SPEC_HASH}_{family}_200000.npy'
            if self.files['p6'][f'bootstrap_cache/{name}'] != self.files['p5'][f'controls/bootstrap_cache/{name}']:
                raise ValueError('bootstrap differs from pre-test commitment')
        freeze = self.read('cert', 'code_freeze.json')
        if freeze['spec_sha256'] != SPEC_HASH or self.read('cert', 'complete.json')['status'] != 'PASS':
            raise ValueError('certification not passed')
        # Certification is historical evidence, not rerun: verify rows and gate arithmetic.
        for family, count, minimum in [('fidelity', 200, 180), ('clipped_linear', 100, 90),
                                       ('ed_capped', 100, 90), ('ed_same_rank', 100, 90), ('hmm', 100, 90)]:
            rows = [json.loads(line) for line in self.path('cert', f'{family}/results.jsonl').read_text().splitlines()]
            draws = self.read('cert', f'{family}/draw_commitment.json')
            verdict = self.read('cert', f'{family}/verdict.json')
            if len(draws) != count or [row['index'] for row in rows] != list(range(count)):
                raise ValueError('incomplete certification rows')
            passed = sum(row['gap'] <= .02 for row in rows)
            invalid = sum(row['invalid_starts'] for row in rows)
            if (passed != verdict['passed'] or passed < minimum or verdict['status'] != 'PASS'
                or invalid != verdict['invalid_starts'] or invalid / (count * 96) > .01
                or max(row['gap'] for row in rows) != verdict['worst_gap']):
                raise ValueError('certification verdict differs from rows')
            for row in rows:
                self.check('cert', f"{family}/case_{row['index']:03}_predictions.json", row['prediction_sha256'])
        for family in ('clipped_linear', 'ed_capped', 'ed_same_rank', 'hmm'):
            if self.read('cert', f'{family}/pooled_verdict.json')['status'] not in ('PASS', 'INELIGIBLE'):
                raise ValueError('false-square control failed')
        if self.read('cert', 'split_state/verdict.json')['status'] != 'PASS':
            raise ValueError('split-state control failed')
        rows = [json.loads(line) for line in self.path('cert', 'pseudocampaign/campaign_results.jsonl').read_text().splitlines()]
        verdict = self.read('cert', 'pseudocampaign/verdict.json')
        if ([row['campaign'] for row in rows] != list(range(100))
            or sum(row['pass'] for row in rows) != verdict['passed'] or verdict['passed'] < 80
            or verdict['status'] != 'PASS'):
            raise ValueError('pseudo-campaign result differs')

    def indices(self):
        result = {}
        for family in ('primary', 'reversal', 'order'):
            name = f'bootstrap_cache/bootstrap_{SPEC_HASH}_{family}_200000.npy'
            x = np.load(self.path('p6', name), allow_pickle=False)
            if x.shape != (200000, 20) or x.min() < 0 or x.max() > 19:
                raise ValueError('invalid bootstrap index array')
            result[family] = x
        return result

    def cases(self):
        """Committed record arrays, sealed predictions, audit coefficients and C rows."""
        release = self.read('p6', 'census/eligibility.json')
        manifest = self.read('p5', 'record_view/manifest.json')
        key = lambda x: (x['exp'], x['config'], x['k'], x['step_index'], x['map_sha256'])
        entries = [(e, r) for e in manifest['allowed_files'] for r in (2, 3, 4)
                   if key(e) in {key(c) for c in release['rank_contexts'][str(r)]}]
        if {str(r): sum(rank == r for e, rank in entries) for r in (2, 3, 4)} != RANK_COUNTS:
            raise ValueError('rank membership changed')
        census = {}
        with self.path('p6', 'census/sealed/test_census.jsonl').open() as stream:
            for line in stream:
                row = json.loads(line)
                census.setdefault((key(row), row['h']), []).append(row)
        units = {}
        for name in self.files['p6']:
            if not name.startswith('record_side/') or not name.endswith('.record.jsonl'):
                continue
            with self.path('p6', name).open() as stream:
                head = json.loads(next(stream))
            wanted = [e for e, r in entries if (e['exp'], e['config']) == (head['exp'], head['config'])]
            if not wanted:
                continue
            audit_name = name.replace('record_side/', 'audit_side/').replace('.record.', '.audit.')
            with self.path('p6', audit_name).open() as stream:
                audit = json.loads(next(stream))
            if head['mode'] != 'fresh_test' or audit['source_header_sha256'] != head['source_header_sha256']:
                raise ValueError('wrong opened record header')
            ids = {(e['k'], e['step_index']) for e in wanted}
            arrays = {cid: np.empty((20, 12, 32, 8), dtype=np.int64) for cid in ids}
            seen = set()
            with self.path('p6', name).open() as stream:
                next(stream)
                for line in stream:
                    row = json.loads(line); cid = (row['k'], row['step_index'])
                    if cid not in ids:
                        continue
                    b, a, l = row['block'] - 910036, row['recipe'] - 48, row['replicate']
                    cell = (cid, b, a, l)
                    e = next(e for e in wanted if (e['k'], e['step_index']) == cid)
                    if (not (0 <= b < 20 and 0 <= a < 12 and 0 <= l < 32) or cell in seen
                        or row['split'] != 'test' or row['selected_h'] != e['h_c']
                        or len(row['labels']) != 9 or any(not 0 <= y < e['m'] for y in row['labels'])):
                        raise ValueError('invalid opened record cell')
                    arrays[cid][b, a, l] = row['labels'][1:]; seen.add(cell)
            if len(seen) != len(ids) * 20 * 12 * 32:
                raise ValueError('incomplete record inventory')
            units[head['exp'], head['config']] = (audit, arrays)
        for e, r in entries:
            name = f"fits/original/{Path(e['file']).stem.removeprefix('v6_trainval_')}_r{r}/predictions.json"
            seal = self.read('p5', name + '.seal.json')
            self.check('p5', name, seal['sha256'])  # recorded absolute path is historical identity only
            pred = self.read('p5', name)
            if pred['rank'] != r or pred['recipe_ids'] != list(range(48, 60)) or pred['reading_counts'] != list(range(1, 9)) or pred['h_c'] != e['h_c']:
                raise ValueError('prediction recipe/rank/time changed')
            header, arrays = units[e['exp'], e['config']]
            context = next(c for c in header['contexts'] if (c['k'], c['step_index']) == (e['k'], e['step_index']))
            raw = (json.dumps({k: context[k] for k in ('raw_by_state', 'package_by_state')}, sort_keys=True, separators=(',', ':')) + '\n').encode()
            if hashlib.sha256(raw).hexdigest() != e['map_sha256']:
                raise ValueError('context map changed')
            rows = census[key(e), e['h_c']]
            if len(rows) != 96 or {(x['recipe'], x['t']) for x in rows} != {(a, t) for a in range(48, 60) for t in range(8)}:
                raise ValueError('incomplete 12x8 test scope census')
            yield e, pred, arrays[e['k'], e['step_index']], header, context, [row['C'] for row in rows]
