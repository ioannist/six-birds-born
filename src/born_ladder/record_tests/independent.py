"""Independent TB01 reconstruction. No production scorer imports or calls.

Equations: floor/normalize forecasts; paired losses over the 20 blocks;
equal-context contrasts; centered >= bootstrap tails with add-one correction;
Holm in frozen slot order; Bonferroni one-sided inversion at 1e-8 resolution.
The sealed index arrays and input parser may be shared; numerical derivation is not.
"""
import math
import json
import numpy as np


def reconstruct_case(entry, prediction, labels, header, context, c_values):
    q = np.array(context['joint_by_state'], dtype=int)
    transition = np.linalg.matrix_power(np.array(header['kernel']), entry['h_c'])
    truth = []
    for recipe in header['recipes'][48:60]:
        distribution = np.zeros(len(q))
        distribution[recipe['states']] = np.array(recipe['weights_num']) / recipe['denominator']
        sequence = []
        for _ in range(8):
            distribution = distribution @ transition
            sequence.append(np.bincount(q, weights=distribution, minlength=entry['m']))
        truth.append(sequence)
    truth = np.array(truth)
    losses = {}
    for name, forecast in prediction['predictions'].items():
        p = np.maximum(np.array(forecast), 1e-12)
        p /= p.sum(-1, keepdims=True)
        losses[name] = -np.log(p[np.arange(12)[None, :, None, None],
                                  np.arange(8)[None, None, None, :], labels])
    rank = prediction['rank']
    contrasts = {}
    for letter, left, right in [('D', 'selected_classical', 'square'),
                                ('G', 'diagonal', 'square'),
                                ('R', 'square', f'ed{rank}'),
                                ('O', 'selected_order', 'square')]:
        contrasts[letter] = (losses[left] - losses[right]).mean(axis=(1, 2, 3))
    constant = truth.mean(axis=(0, 1))
    constant = np.maximum(constant, 1e-12); constant /= constant.sum()
    information = []
    for p in truth.reshape(-1, entry['m']):
        positive = p > 0
        information.append(float(np.sum(p[positive] * np.log(p[positive] / constant[positive]))))
    return {'id': json.dumps((entry['exp'], entry['config'], entry['k'], entry['step_index'], entry['map_sha256']), separators=(',', ':')),
            'rank': rank, 'contrasts': contrasts, 'C95': sorted(map(float, c_values))[91],
            'signal': float(np.mean(information))}


def tail(x, null, samples):
    observed = float(x.mean())
    centered = x[samples].mean(axis=1) - observed
    return (1 + np.sum(centered >= observed - null).item()) / (samples.shape[0] + 1)


def bound(x, samples, family_size):
    mean = float(x.mean()); width = 1.
    alpha = .05 / family_size
    while True:
        lo, hi = mean - width, mean + width
        if tail(x, lo, samples) <= alpha and tail(x, hi, samples) > alpha:
            break
        width *= 2
        if width > 1e12:
            raise ArithmeticError('independent inversion failed')
    while hi - lo >= 1e-8:
        midpoint = (lo + hi) / 2
        if tail(x, midpoint, samples) <= alpha:
            lo = midpoint
        else:
            hi = midpoint
    return math.floor(lo / 1e-8) * 1e-8


def reconstruct(cases, margins, indices):
    slots = {'primary': ['D2', 'G2', 'D3', 'G3', 'D4', 'G4'],
             'reversal': ['R2', 'R3', 'R4'], 'order': ['O2', 'O3', 'O4']}
    estimates, scopes, signals = {}, {}, {}
    for rank in (2, 3, 4):
        group = [c for c in cases if c['rank'] == rank]
        c95 = np.array([c['C95'] for c in group])
        scopes[rank] = {'status': 'in_scope' if float(c95.mean()) <= .01 else 'out_of_eligible_scope',
                        'mean_C95': float(c95.mean()), 'max_C95': float(c95.max()),
                        'failing_fraction': float(np.mean(c95 > .01)),
                        'context_C95': {c['id']: c['C95'] for c in group}}
        signals[rank] = float(np.mean([c['signal'] for c in group]))
        for letter in 'DGRO':
            estimates[f'{letter}{rank}'] = np.mean([c['contrasts'][letter] for c in group], axis=0)
    inference = {}
    for family, order in slots.items():
        probabilities, bounds, means, limits = {}, {}, {}, {}
        for slot in order:
            rank = int(slot[1]); limit = .01 if slot[0] == 'G' else margins[rank]
            x = estimates[slot]; reverse = family == 'reversal'
            y = -x if reverse else x
            probabilities[slot] = tail(y, -limit if reverse else limit, indices[family])
            b = bound(y, indices[family], len(order)); bounds[slot] = -b if reverse else b
            means[slot] = float(x.mean()); limits[slot] = limit
        ordered = sorted(order, key=lambda s: (probabilities[s], order.index(s)))
        adjusted, rejected = {}, {}; running = 0.; stopped = False
        for i, slot in enumerate(ordered):
            running = max(running, (len(order) - i) * probabilities[slot])
            adjusted[slot] = min(1., running)
            rejected[slot] = not stopped and probabilities[slot] <= .05 / (len(order) - i)
            if not rejected[slot]: stopped = True
        inference[family] = {'family': family, 'estimates': means, 'bounds': bounds,
                             'p_raw': probabilities,
                             'holm': {'ordered': ordered, 'adjusted': adjusted, 'reject': rejected},
                             'margins': limits,
                             'qualification': 'nominal simultaneous bounds under bootstrap validity'}
    ranks = {}
    for rank in (2, 3, 4):
        b = {letter: inference[family]['bounds'][f'{letter}{rank}'] for letter, family in
             [('D', 'primary'), ('G', 'primary'), ('R', 'reversal'), ('O', 'order')]}
        gates = {'scope': scopes[rank]['status'] == 'in_scope', 'signal': signals[rank] > margins[rank],
                 'primary_D': b['D'] > margins[rank], 'cross_terms_G': b['G'] > .01,
                 'no_reversal_R': b['R'] < margins[rank], 'order_O': b['O'] > margins[rank]}
        passed = all(gates.values())
        status = ('PASS' if passed else 'OUT_OF_ELIGIBLE_SCOPE' if not gates['scope'] else
                  'UNINFORMATIVE_AT_SELECTED_LAG' if not gates['signal'] else 'FAIL')
        ranks[str(rank)] = {'status': status, 'pass': passed, 'gates': gates, 'margin': margins[rank],
                            'bounds': b, 'scope': scopes[rank], 'oracle_signal': signals[rank]}
    statuses = {r['status'] for r in ranks.values()}
    category = next(c for c in ('PASS', 'FAIL', 'UNINFORMATIVE_AT_SELECTED_LAG', 'OUT_OF_ELIGIBLE_SCOPE') if c in statuses)
    return {'category': category, 'ranks': ranks, 'inference': inference}
