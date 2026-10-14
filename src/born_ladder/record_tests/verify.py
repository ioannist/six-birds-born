"""Score-only TB01 verification of an already opened, immutable local archive.

No sampling, model evaluation/refitting, certification publication or archive writes.
Descriptive arrow/calibration-sensitivity results stay hash-bound historical
attachments; this command re-derives the claim gates and record losses only.
"""
from __future__ import annotations

import argparse
import json

import numpy as np

from .inputs import Inputs
from . import independent, scoring


def differences(actual, expected, path=''):
    """Exact keys/types, numeric maximum error, with Boolean/string equality."""
    if isinstance(expected, dict):
        if set(actual) != set(expected):
            raise ValueError(f'result keys differ at {path}')
        return max((differences(actual[k], expected[k], f'{path}/{k}') for k in expected), default=0.)
    if isinstance(expected, list):
        if len(actual) != len(expected): raise ValueError(f'result lengths differ at {path}')
        return max((differences(a, b, path) for a, b in zip(actual, expected)), default=0.)
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not np.isfinite(actual) or not np.isfinite(expected):
            raise ValueError(f'nonfinite comparison at {path}')
        return abs(actual - expected)
    if actual != expected: raise ValueError(f'result differs at {path}: {actual!r} != {expected!r}')
    return 0.


def verify(inputs: Inputs):
    archive = inputs.read('p6', 'verdict.json')
    margins = {int(r): value for r, value in inputs.read('p6', 'margins.json')['margins'].items()}
    indices = inputs.indices()
    production_rows, independent_rows, reports = [], [], []
    max_loss_error = 0.
    for entry, pred, labels, header, context, c_values in inputs.cases():
        laws = scoring.oracle_laws(header, context, entry['h_c'])
        contrasts, report = scoring.evaluate_context(pred, labels, laws)
        cid = json.dumps((entry['exp'], entry['config'], entry['k'], entry['step_index'], entry['map_sha256']), separators=(',', ':'))
        production_rows.append({'id': cid, 'rank': pred['rank'], 'laws': laws,
                                'contrasts': contrasts, 'test_C_values': c_values})
        independent_rows.append(independent.reconstruct_case(entry, pred, labels, header, context, c_values))
        old = next(x for x in archive['contexts'] if x['context'] == entry and x['rank'] == pred['rank'])
        loss_error = differences(report, {key: old[key] for key in report})
        max_loss_error = max(max_loss_error, loss_error)
        reports.append({'context': entry, 'rank': pred['rank'], **report})
    production = scoring.campaign(production_rows, margins, indices)
    rebuilt = independent.reconstruct(independent_rows, margins, indices)
    target = {key: archive[key] for key in production}
    production_error = differences(production, target)
    independent_error = differences(rebuilt, target)
    # Frozen gate values (bounds, estimates, raw and Holm p) must match exactly;
    # oracle/secondary floating evaluations get the reviewed 1e-8 acceptance.
    if production['inference'] != archive['inference'] or rebuilt['inference'] != archive['inference']:
        raise ValueError('inference does not exactly reproduce the archived values')
    if max(production_error, independent_error, max_loss_error) > 1e-8:
        raise ValueError('archived score reconstruction differs beyond reviewed tolerance')
    if production['category'] != 'FAIL' or any(r['status'] != 'FAIL' or not r['gates']['scope'] or not r['gates']['signal'] for r in production['ranks'].values()):
        raise ValueError('TB01 informative-negative claim does not match')
    return {'status': 'VERIFIED', 'claim': 'TB01', 'verdict': production,
            'independent_verdict': rebuilt, 'context_scores': reports,
            'comparison': {'production_max_error': production_error,
                           'independent_max_error': independent_error,
                           'context_loss_max_error': max_loss_error,
                           'inference_exact': True},
            'input_files_verified': len(inputs.verified),
            'historical_attachments': {'verdict_sha256': inputs.files['p6']['verdict.json'],
                                      'fields_not_recomputed': ['arrow', 'calibration_sensitivity', 'descriptive_controls', 'per_source_secondary']}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', required=True, help='explicit local evidence receipt JSON')
    parser.add_argument('--inputs-sha256', required=True, help='trusted SHA-256 of the input receipt')
    parser.add_argument('--sealed-root', required=True, help='already sealed P5 data root')
    parser.add_argument('--opened-root', required=True, help='already scored P6 archive root')
    parser.add_argument('--certification-root', required=True, help='historical certification rows')
    args = parser.parse_args()
    inputs = Inputs(args.inputs, args.inputs_sha256, sealed_root=args.sealed_root,
                    opened_root=args.opened_root, certification_root=args.certification_root)
    print(json.dumps(verify(inputs), sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
