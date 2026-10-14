"""Build a v6 record-only training/validation view after sidecar sampling.

This module accepts v6 trainval RECORD files only. It never opens audit-side,
fresh-test, v4/v5, or sealed census files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SPEC_HASH = '3abc68c6f0a8070240a2302434b28644fbf8b67f955a65af2cf33667cfd6d2cd'


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def build(record_dir: Path, census_release: Path, output_dir: Path) -> dict:
    census = json.loads(census_release.read_bytes())
    if census.get('schema') != 'test_b_v6_census_release_v1' or census.get('spec_sha256') != SPEC_HASH:
        raise ValueError('wrong v6 training census')
    if output_dir.exists():
        raise FileExistsError('filtered v6 record view already exists')
    files = sorted(record_dir.glob('*.v6.trainval.record.jsonl'))
    if len(files) != census['unit_count']:
        raise ValueError('v6 record unit count differs from frozen census')
    by_unit = {(u['exp'], u['config']): u for u in census['units']}
    eligible = {(c['exp'], c['config'], c['k'], c['step_index']): c
                for c in census['training_contexts'] if c['h_c'] is not None
                and c['primary_excluded_reason'] is None and c['m'] > 2}
    output_dir.mkdir(parents=True)
    allowed = []
    for path in files:
        with path.open() as stream:
            header = json.loads(stream.readline())
            if header.get('schema') != 'test_b_v6_record_v1' or header.get('mode') != 'trainval':
                raise ValueError('record-side v6 trainval header required')
            if header.get('kernel_seed') != 910000 or header.get('recipe_ids') != list(range(60)):
                raise ValueError('wrong kernel seed or v6 recipes')
            exp, config = header['exp'], header['config']
            unit = by_unit.get((exp, config))
            if unit is None or header.get('source_header_sha256') != unit['sealed_kernel_header_sha256']:
                raise ValueError('record header differs from frozen kernel/census')
            selected = {}
            for entry in header['contexts']:
                key = (exp, config, entry['k'], entry['step_index'])
                census_context = eligible.get(key)
                if census_context is not None:
                    if entry['selected_h'] != census_context['h_c'] or entry['m'] != census_context['m']:
                        raise ValueError('record interval/alphabet differs from census')
                    selected[(entry['k'], entry['step_index'])] = {
                        'identity': census_context, 'calibration': {}, 'paths': []}
            for line in stream:
                row = json.loads(line)
                key = (row['k'], row['step_index'])
                target = selected.get(key)
                if target is None:
                    continue
                if row['type'] == 'calibration':
                    a = row['recipe']
                    if a in target['calibration'] or not 0 <= a < 60 or len(row['labels']) != 8192:
                        raise ValueError('bad v6 record calibration row')
                    target['calibration'][a] = row['labels']
                elif row['type'] == 'path':
                    a, b = row['recipe'], row['block']
                    split = 'train' if a < 36 and 910001 <= b <= 910010 else (
                        'validation' if 36 <= a < 48 and 910011 <= b <= 910015 else None)
                    if split is None or row['split'] != split or row['selected_h'] != target['identity']['h_c']:
                        raise ValueError('path outside v6 training/validation manifest')
                    if len(row['labels']) != 9:
                        raise ValueError('wrong v6 reading count')
                    target['paths'].append(row)
                else:
                    raise ValueError('undeclared v6 record row')
        for (k, step), payload in selected.items():
            if set(payload['calibration']) != set(range(60)) or len(payload['paths']) != 13440:
                raise ValueError('incomplete v6 record context')
            ctx = payload['identity']
            raw = {'schema': 'test_b_v6_trainval_context_v1',
                   'exp': exp, 'config': config, 'k': k, 'step_index': step,
                   'h_c': ctx['h_c'], 'm': ctx['m'], 'map_sha256': ctx['map_sha256'],
                   'calibration': {str(a): payload['calibration'][a] for a in range(60)},
                   'paths': payload['paths']}
            namehash = hashlib.sha256(f'{exp}/{config}/{k}/{step}/{ctx["map_sha256"]}'.encode()).hexdigest()[:20]
            name = f'v6_trainval_{namehash}.json'
            encoded = canonical(raw)
            (output_dir / name).write_bytes(encoded)
            allowed.append({'file': name, 'sha256': hashlib.sha256(encoded).hexdigest(),
                            'exp': exp, 'config': config, 'k': k, 'step_index': step,
                            'h_c': ctx['h_c'], 'm': ctx['m'], 'map_sha256': ctx['map_sha256']})
    if len(allowed) != len(eligible):
        raise ValueError('filtered view missing an eligible context')
    manifest = {'schema': 'test_b_v6_trainval_manifest_v1', 'spec_sha256': SPEC_HASH,
                'census_release_sha256': hashlib.sha256(census_release.read_bytes()).hexdigest(),
                'allowed_files': sorted(allowed, key=lambda e: (e['exp'], e['config'], e['k'], e['step_index']))}
    (output_dir / 'manifest.json').write_bytes(canonical(manifest))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--record-dir', type=Path, required=True)
    parser.add_argument('--census-release', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(len(build(args.record_dir, args.census_release, args.output_dir)['allowed_files']))


if __name__ == '__main__':
    main()
