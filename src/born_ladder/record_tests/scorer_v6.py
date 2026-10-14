"""V6 synthetic audit scorer: twelve test recipes and frozen v6 bootstrap stream."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from born_ladder.record_tests import generation_scorer as base

SPEC_HASH = '958c66539b1a1d91ceb9b567e837b2e1d947b3d85af395e315112921a7de743d'
DRAW_COUNT = 200_000


def bootstrap_indices(family_id: str, cache_dir: Path) -> np.ndarray:
    if family_id not in ('primary', 'reversal', 'order'):
        raise ValueError(family_id)
    path = cache_dir / f'bootstrap_{SPEC_HASH}_{family_id}_{DRAW_COUNT}.npy'
    if path.exists():
        result = np.load(path, allow_pickle=False)
        if result.shape != (DRAW_COUNT, 20) or result.min() < 0 or result.max() > 19:
            raise ValueError('invalid v6 bootstrap cache')
        return result
    result = np.empty((DRAW_COUNT, 20), dtype=np.uint8)
    ceiling = ((1 << 64) // 20) * 20
    for k in range(DRAW_COUNT):
        for i in range(20):
            z = 0
            while True:
                key = f'TestB/v6/bootstrap/{SPEC_HASH}/{family_id}/{k}/{i}/{z}'
                x = int.from_bytes(hashlib.sha256(key.encode('ascii')).digest()[:8], 'little')
                if x < ceiling:
                    result[k, i] = x % 20
                    break
                z += 1
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.save(path, result, allow_pickle=False)
    return result


def sampled_loss(pred: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Loss array [20 blocks, 12 recipes, 32 paths, 8 future readings]."""
    labels = np.asarray(labels, dtype=np.int64)
    if labels.shape != (20, 12, 32, 8):
        raise ValueError('wrong v6 scored path shape')
    p = base.scoring_probability(pred)
    a = np.arange(12)[None, :, None, None]
    t = np.arange(8)[None, None, None, :]
    return -np.log(p[a, t, labels])


def inference(blocks: dict, margins: dict, family: str, indices: np.ndarray) -> dict:
    return base.family_inference(blocks, margins, family, indices)


def signal(laws: list[np.ndarray]) -> tuple[float, list[float]]:
    gains = []
    for law in laws:
        if law.shape[0:2] != (12, 8):
            raise ValueError('wrong v6 oracle law shape')
        constant = law.mean(axis=(0, 1))
        gains.append(float(np.mean([base.excess_log_loss(p, constant)
                                    for p in law.reshape(-1, law.shape[-1])])))
    return float(np.mean(gains)), gains
