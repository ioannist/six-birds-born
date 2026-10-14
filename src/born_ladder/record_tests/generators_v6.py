"""Fresh v6 synthetic generators. No estimator or real sidecar imports.

Only TestB/v6/fidelity, TestB/v6/main/* and TestB/v6/pseudocampaign
seed domains are accepted. Development uses born_ladder.record_tests.dev6 instead.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from born_ladder.record_tests import generators as G
from born_ladder.record_tests.test_b_census_v6 import recipes_v6

BLOCK_IDS = tuple(range(910001, 910016)) + tuple(range(910036, 910056))
TRAIN_RECIPES, VALID_RECIPES, TEST_RECIPES = range(36), range(36, 48), range(48, 60)
CALIBRATION_DRAWS = 8192
REPLICATES = 32


def valid_cell(block: int, recipe: int) -> bool:
    return ((910001 <= block <= 910010 and 0 <= recipe < 36)
            or (910011 <= block <= 910015 and 36 <= recipe < 48)
            or (910036 <= block <= 910055 and 48 <= recipe < 60))


def path_block_domain(domain: str, block: int) -> str | int:
    if domain != 'pseudocampaign':
        return block
    if 910001 <= block <= 910010:
        return f'v6-train-{block-910000:02d}'
    if 910011 <= block <= 910015:
        return f'v6-valid-{block-910010:02d}'
    if 910036 <= block <= 910055:
        return f'v6-test-{block-910035:02d}'
    raise ValueError('undeclared pseudo-campaign block')


def rng(domain: str, *parts) -> np.random.Generator:
    if domain.startswith('dev6/'):
        prefix = 'TestB/' + domain
    elif domain == 'fidelity' or domain == 'pseudocampaign' or domain.startswith('main/'):
        prefix = 'TestB/v6/' + domain
    else:
        raise ValueError('v6 confirmation RNG domain must be fidelity, main/* or pseudocampaign')
    key = prefix + '/' + '/'.join(map(str, parts))
    seed = int.from_bytes(hashlib.sha256(key.encode()).digest()[:16], 'little')
    return np.random.default_rng(seed)


def _dimensions(domain: str, index: int, m: int | None, r: int | None) -> tuple[int, int]:
    gen = rng(domain, 'dimensions', index)
    if m is None: m = int(gen.integers(5, 9))
    if r is None: r = int(gen.integers(2, min(5, m)))
    if not 2 <= r < m: raise ValueError('rank must be below label count')
    return m, r


def _preparations(gen: np.random.Generator, m: int) -> np.ndarray:
    alpha = gen.uniform(.5, 2., size=(60, m))
    return np.stack([gen.dirichlet(row) for row in alpha])


def _calibration(domain: str, family: str, index: int, true_u: np.ndarray) -> dict[int, np.ndarray]:
    m = true_u.shape[1]
    return {a: rng(domain, family, 'Y0cal', index, a).choice(m, size=CALIBRATION_DRAWS,
                                                            p=true_u[a]).astype(np.int16)
            for a in range(60)}


def _paths_distribution(domain: str, family: str, index: int,
                        true_u: np.ndarray, laws: np.ndarray) -> np.ndarray:
    m = true_u.shape[1]
    paths = np.full((len(BLOCK_IDS), 60, REPLICATES, 9), -1, dtype=np.int16)
    for bi, block in enumerate(BLOCK_IDS):
        for a in range(60):
            if not valid_cell(block, a):
                continue
            gen = rng(domain, family, 'path', index, path_block_domain(domain, block), a)
            paths[bi, a, :, 0] = gen.choice(m, size=REPLICATES, p=true_u[a])
            for t in range(8):
                paths[bi, a, :, t + 1] = gen.choice(m, size=REPLICATES, p=laws[a, t])
    return paths


def _paths_chain(domain: str, family: str, index: int,
                 initial: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    n = kernel.shape[0]
    paths = np.full((len(BLOCK_IDS), 60, REPLICATES, 65), -1, dtype=np.int16)
    for bi, block in enumerate(BLOCK_IDS):
        for a in range(60):
            if not valid_cell(block, a):
                continue
            gen = rng(domain, family, 'path', index, path_block_domain(domain, block), a)
            states = gen.choice(n, size=REPLICATES, p=initial[a])
            paths[bi, a, :, 0] = states
            for t in range(64):
                states = G.sample_rows(gen, kernel, states)
                paths[bi, a, :, t + 1] = states
    return paths


@dataclass
class V6Plant:
    family: str
    index: int
    m: int
    r: int
    domain: str
    true_u: np.ndarray
    calibration: dict[int, np.ndarray]
    paths: np.ndarray | None
    parameters: dict
    kernel: np.ndarray | None = None
    q: np.ndarray | None = None
    initial_micro: np.ndarray | None = None
    distribution_laws: np.ndarray | None = None

    def readings(self, h: int) -> np.ndarray:
        if h not in (1, 2, 4, 8): raise ValueError('reading interval outside frozen ladder')
        if self.paths is None: raise ValueError('paths were not generated')
        if self.kernel is None:
            if h != 1: raise ValueError('distribution-level plant has h=1')
            return self.paths
        assert self.q is not None
        return self.q[self.paths[..., np.arange(9) * h]]

    def marginals(self, h: int) -> np.ndarray:
        if self.kernel is None:
            if h != 1: raise ValueError('distribution-level plant has h=1')
            assert self.distribution_laws is not None
            return self.distribution_laws
        if h not in (1, 2, 4, 8): raise ValueError('reading interval outside frozen ladder')
        assert self.q is not None and self.initial_micro is not None
        kh = np.linalg.matrix_power(self.kernel, h)
        mu = self.initial_micro.copy()
        out = np.empty((60, 8, self.m))
        for t in range(8):
            mu = mu @ kh
            for a in range(60): out[a, t] = np.bincount(self.q, weights=mu[a], minlength=self.m)
        return out

    def true_predictions(self, empirical_u: np.ndarray, h: int) -> np.ndarray:
        if self.family == 'quadratic':
            return G.square_law(self.parameters['U'], self.parameters['A'], empirical_u)
        if self.family == 'clipped_linear':
            return G.clipped_law(self.parameters['U'], self.parameters['A'], empirical_u)
        if h not in (1, 2, 4, 8): raise ValueError('reading interval outside frozen ladder')
        assert self.kernel is not None and self.q is not None
        if self.family.startswith('ed'):
            mu = empirical_u.copy()
        elif self.family == 'hmm':
            e = self.parameters['E']
            mu = (empirical_u[:, :, None] * e[None, :, :]).reshape(len(empirical_u), -1)
        else:
            raise ValueError('split-state has no fitted own-law benchmark')
        kh = np.linalg.matrix_power(self.kernel, h)
        out = np.empty((len(empirical_u), 8, self.m))
        for t in range(8):
            mu = mu @ kh
            for a in range(len(empirical_u)):
                out[a, t] = np.bincount(self.q, weights=mu[a], minlength=self.m)
        return out


def quadratic(index: int, domain: str = 'fidelity', m: int | None = None,
              r: int | None = None, paths: bool = True) -> V6Plant:
    m, r = _dimensions(domain, index, m, r)
    rejections = []
    for attempt in range(1000):
        gen = rng(domain, 'quadratic', 'parameters', index, attempt)
        u = _preparations(gen, m)
        U, A = G.qr_frame(gen, m, r), G.amplitude_matrix(gen, r)
        try: laws = G.square_law(U, A, u)
        except ValueError as exc:
            rejections.append({'attempt':attempt,'reason':str(exc),
                               'parameter_sha256':hashlib.sha256(U.tobytes()+A.tobytes()+u.tobytes()).hexdigest()})
            continue
        break
    else: raise ValueError('1000 deterministic quadratic normalization attempts failed')
    cal = _calibration(domain, 'quadratic', index, u)
    sampled = _paths_distribution(domain, 'quadratic', index, u, laws) if paths else None
    return V6Plant('quadratic', index, m, r, domain, u, cal, sampled,
                   {'U': U, 'A': A, 'attempt': attempt,'rejections':rejections}, distribution_laws=laws)


def clipped_linear(index: int, domain: str = 'main/clipped_linear', m: int | None = None,
                   r: int | None = None, paths: bool = True) -> V6Plant:
    m, r = _dimensions(domain, index, m, r)
    rejections = []
    for attempt in range(1000):
        gen = rng(domain, 'clipped_linear', 'parameters', index, attempt)
        u = _preparations(gen, m)
        U, A = G.qr_frame(gen, m, r), G.amplitude_matrix(gen, r)
        try: laws = G.clipped_law(U, A, u)
        except ValueError as exc:
            rejections.append({'attempt':attempt,'reason':str(exc),
                               'parameter_sha256':hashlib.sha256(U.tobytes()+A.tobytes()+u.tobytes()).hexdigest()})
            continue
        break
    else: raise ValueError('1000 deterministic clipped normalization attempts failed')
    cal = _calibration(domain, 'clipped_linear', index, u)
    sampled = _paths_distribution(domain, 'clipped_linear', index, u, laws) if paths else None
    return V6Plant('clipped_linear', index, m, r, domain, u, cal, sampled,
                   {'U': U, 'A': A, 'attempt': attempt,'rejections':rejections}, distribution_laws=laws)


def ed(index: int, domain: str = 'main/ed_capped', m: int | None = None,
       r: int | None = None, k: int | None = None, paths: bool = True) -> V6Plant:
    m, r = _dimensions(domain, index, m, r)
    if k is None:
        if 'capped' in domain:
            cap = m * r - r * (r + 1) // 2 + r * r
            allowed = [candidate for candidate in range(1, r + 1)
                       if m * (candidate - 1) + candidate * (m - 1) <= cap]
            k = allowed[int(rng(domain, 'ed', 'capped_k', index).integers(len(allowed)))]
        else:
            k = r
    if not 1 <= k <= r: raise ValueError('invalid ED rank')
    gen = rng(domain, 'ed', 'parameters', index)
    u = _preparations(gen, m)
    E, D = G.stochastic((m, k), gen), G.stochastic((k, m), gen)
    kernel = E @ D
    cal = _calibration(domain, 'ed', index, u)
    sampled = _paths_chain(domain, 'ed', index, u, kernel) if paths else None
    return V6Plant('ed_capped' if 'capped' in domain else 'ed_same_rank', index, m, r,
                   domain, u, cal, sampled, {'E': E, 'D': D, 'k': k},
                   kernel, np.arange(m), u)


def hmm(index: int, domain: str = 'main/hmm', m: int | None = None,
        r: int | None = None, paths: bool = True) -> V6Plant:
    m, r = _dimensions(domain, index, m, r)
    gen = rng(domain, 'hmm', 'parameters', index)
    u = _preparations(gen, m)
    E, T, D = G.stochastic((m, r), gen), G.stochastic((r, r), gen), G.stochastic((r, m), gen)
    kernel = np.empty((m * r, m * r))
    for y in range(m):
        for hidden in range(r):
            kernel[y * r + hidden] = np.outer(D[hidden], T[hidden]).reshape(-1)
    q = np.repeat(np.arange(m), r)
    initial = (u[:, :, None] * E[None, :, :]).reshape(60, -1)
    cal = _calibration(domain, 'hmm', index, u)
    sampled = _paths_chain(domain, 'hmm', index, initial, kernel) if paths else None
    return V6Plant('hmm', index, m, r, domain, u, cal, sampled,
                   {'E': E, 'T': T, 'D': D}, kernel, q, initial)


def split_state(index: int, domain: str = 'main/split_state', m: int | None = None,
                r: int | None = None) -> dict:
    m, r = _dimensions(domain, index, m, r)
    gen = rng(domain, 'split', 'parameters', index)
    kernel = np.zeros((2 * m, 2 * m))
    defects = []
    for a in range(m):
        b1, b2 = gen.choice(m, size=2, replace=False)
        w = gen.dirichlet(gen.uniform(.5, 2., size=m))
        d = float(gen.uniform(.2, .4))
        defects.append(d)
        kernel[2 * a, 0::2] = (1 - d) * w + d * np.eye(m)[b1]
        kernel[2 * a + 1, 1::2] = (1 - d) * w + d * np.eye(m)[b2]
    legacy = [[a % m, (a + 7) % m, (a + 19) % m] for a in range(24)]
    source_hash = hashlib.sha256(f'TestB/v6/{domain}/split/{index}/{m}'.encode()).hexdigest()
    recipes = recipes_v6(m, source_hash, legacy)
    initial = np.zeros((60, 2 * m))
    for a, recipe in enumerate(recipes):
        for state, weight in zip(recipe['states'], recipe['weights_num']):
            initial[a, 2 * state:2 * state + 2] += weight / (2 * recipe['denominator'])
    calibration = {}
    q = np.repeat(np.arange(m), 2)
    for a in range(60):
        gen = rng(domain, 'split', 'Y0cal', index, a)
        calibration[a] = q[gen.choice(2*m, size=CALIBRATION_DRAWS, p=initial[a])].astype(np.int16)
    paths = _paths_chain(domain, 'split', index, initial, kernel)
    return {'family': 'split_state', 'index': index, 'm': m, 'r': r,
            'K': kernel, 'q': q, 'recipes': recipes,
            'initial': initial, 'calibration': calibration, 'paths': paths,
            'd': defects, 'semantic': 'fixed micro kernel'}


def pseudocampaign_context(campaign: int, slot: int, m: int, r: int | None = None,
                           paths: bool = True) -> V6Plant:
    """Give every census slot in every campaign its own fresh RNG substream."""
    if campaign < 0 or slot < 0:
        raise ValueError('campaign and slot IDs must be nonnegative')
    return quadratic(f'{campaign}:{slot}', domain='pseudocampaign', m=m, r=r, paths=paths)
