"""Extracted frozen v6.1 record scoring and real claim predicate. No writes."""
import numpy as np
from . import scorer as S

def rank_claim(nonempty: bool, scope: bool, signal: float, margin: float,
               bounds: dict) -> bool:
    return bool(nonempty and scope and signal>margin
        and bounds['D']>margin and bounds['G']>.01
        and bounds['R']<margin and bounds['O']>margin)


def expected_excess(laws: np.ndarray, pred: np.ndarray) -> float:
    if laws.shape != pred.shape or laws.shape[0:2] != (12, 8):
        raise ValueError('wrong exact expected-loss shape')
    return float(np.mean([S.excess_log_loss(laws[a,t], pred[a,t])
                          for a in range(12) for t in range(8)]))


def sampled_loss(pred: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Loss array [20 blocks, 12 recipes, 32 paths, 8 future readings]."""
    labels = np.asarray(labels, dtype=np.int64)
    if labels.shape != (20, 12, 32, 8):
        raise ValueError('wrong v6 scored path shape')
    p = S.scoring_probability(pred)
    a = np.arange(12)[None, :, None, None]
    t = np.arange(8)[None, None, None, :]
    return -np.log(p[a, t, labels])


def signal(laws: list[np.ndarray]) -> tuple[float, list[float]]:
    gains = []
    for law in laws:
        if law.shape[0:2] != (12, 8):
            raise ValueError('wrong v6 oracle law shape')
        constant = law.mean(axis=(0, 1))
        gains.append(float(np.mean([S.excess_log_loss(p, constant)
                                    for p in law.reshape(-1, law.shape[-1])])))
    return float(np.mean(gains)), gains


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
    losses = {name: sampled_loss(np.asarray(p), labels) for name, p in pred['predictions'].items()}
    square = losses['square']; rank = pred['rank']
    contrasts = {'D': (losses['selected_classical'] - square).mean(axis=(1, 2, 3)),
                 'G': (losses['diagonal'] - square).mean(axis=(1, 2, 3)),
                 'R': (square - losses[f'ed{rank}']).mean(axis=(1, 2, 3)),
                 'O': (losses['selected_order'] - square).mean(axis=(1, 2, 3))}
    oracle_loss = sampled_loss(laws, labels)
    report = {'paired_blocks': {k: v.tolist() for k, v in contrasts.items()},
              'selectors': pred['selectors'], 'models': {}}
    # §5: primary loss above the optimal record law; secondary calibration/TV.
    # Calibration here is pooled label-frequency minus mean forecast, not a new gate.
    observed = np.bincount(labels.ravel(), minlength=laws.shape[-1]) / labels.size
    for name, p in pred['predictions'].items():
        probabilities = S.scoring_probability(np.asarray(p))
        report['models'][name] = {'mean_log_loss': float(losses[name].mean()),
            'excess_log_loss': float((losses[name] - oracle_loss).mean()),
            'expected_excess': float(expected_excess(laws, np.asarray(p))),
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
        signals[r] = signal([x['laws'] for x in group])[0] if group else None
        for letter, family in [('D', 'primary'), ('G', 'primary'), ('R', 'reversal'), ('O', 'order')]:
            blocks[family][f'{letter}{r}'] = np.mean([x['contrasts'][letter] for x in group], axis=0) if group else None
    limits = {'primary': {f'{x}{r}': .01 if x == 'G' else margins[r] for r in (2,3,4) for x in ('D','G')},
              'reversal': {f'R{r}': margins[r] for r in (2,3,4)},
              'order': {f'O{r}': margins[r] for r in (2,3,4)}}
    inference = {f: S.family_inference(blocks[f], limits[f], f, bootstrap[f]) for f in blocks}
    ranks = {}
    for r in (2,3,4):
        scope = scopes[r]['status'] == 'in_scope'; nonempty = signals[r] is not None
        bounds = {x: inference[f]['bounds'][f'{x}{r}'] for x, f in
                  [('D','primary'),('G','primary'),('R','reversal'),('O','order')]}
        passed = rank_claim(nonempty, scope, signals[r] or 0., margins[r], bounds) if nonempty else False
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

