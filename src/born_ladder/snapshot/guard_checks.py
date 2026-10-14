"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping
from born_ladder.snapshot.errors import IncompleteCampaign

_GUARD_PATH_ROLES = (
    "state_path", "failed_attempt_evidence_path", "execution_record_path",
)


def validate_guard_destinations(
    guard: Mapping[str, Any], *, forbidden_paths: tuple[Path, ...],
) -> dict[str, Path]:
    """Resolve all destinations and reject aliases before any parent is created."""
    resolved: dict[str, Path] = {}
    try:
        forbidden = {path.resolve(strict=False) for path in forbidden_paths}
        for role in _GUARD_PATH_ROLES:
            raw = guard.get(role)
            if type(raw) is not str:
                raise IncompleteCampaign("G2c v22 single-attempt guard paths disagree")
            path = Path(raw)
            canonical = path.resolve(strict=False)
            protected_relation = any(
                canonical == protected
                or protected in canonical.parents
                or canonical in protected.parents
                for protected in forbidden
            )
            existing_ancestor = canonical.parent
            while not existing_ancestor.exists():
                existing_ancestor = existing_ancestor.parent
            if (
                not path.is_absolute()
                or ".." in path.parts
                or path != canonical
                or protected_relation
                or not existing_ancestor.is_dir()
            ):
                raise IncompleteCampaign(
                    f"G2c v22 {role} is noncanonical, aliased, or protected"
                )
            resolved[role] = canonical
    except IncompleteCampaign:
        raise
    except (OSError, RuntimeError) as error:
        raise IncompleteCampaign(
            "G2c v22 single-attempt guard paths cannot be resolved"
        ) from error
    destinations = tuple(resolved.values())
    if len(set(destinations)) != len(_GUARD_PATH_ROLES) or any(
        left in right.parents or right in left.parents
        for index, left in enumerate(destinations)
        for right in destinations[index + 1:]
    ):
        raise IncompleteCampaign(
            "G2c v22 single-attempt guard paths alias or have an ancestor relationship"
        )
    return resolved
