"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import math
import numpy as np




def _two_pass_mgs(projected: np.ndarray, rank: int, norm_floor: float) -> np.ndarray | None:
    columns: list[np.ndarray] = []
    for column_index in range(rank - 1):
        column = projected[:, column_index].copy()
        for _ in range(2):
            for previous in columns:
                column -= previous * float(previous @ column)
        norm = float(np.linalg.norm(column))
        if norm <= norm_floor:
            return None
        column /= norm
        columns.append(column)
    constant = np.full(projected.shape[0], 1.0 / math.sqrt(projected.shape[0]))
    return np.column_stack((constant, *columns)) if columns else constant[:, None]
