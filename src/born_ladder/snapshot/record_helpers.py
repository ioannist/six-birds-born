"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import copy
from typing import Any, Mapping, Sequence
from born_ladder.snapshot.errors import IncompleteCampaign
from born_ladder.snapshot.frozen_spec import canonical_json_bytes, sha256_bytes

def _science_fields(profile: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        field
        for group in ("empirical", "law_evidence")
        for field in profile["group_field_order"][group]
    )


def _unit_discovery_rows(
    born: Mapping[str, Any], discovery: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    matching = [
        row for row in discovery.get("rows", ())
        if row.get("step_index") == born.get("step_index")
        and row.get("observation_payload", {}).get("context_k") == born.get("k")
    ]
    raw = [row for row in matching if "packaging_source" not in row["observation_payload"]]
    pkg = [row for row in matching if "packaging_source" in row["observation_payload"]]
    return raw, pkg


def _validate_trajectory_rows(
    rows: Sequence[Mapping[str, Any]], *, trajectory_count: int, state_count: int,
    label: str,
) -> tuple[list[str], list[int]]:
    if len(rows) != trajectory_count or trajectory_count < 1:
        raise IncompleteCampaign(f"G2H {label} trajectory census disagrees")
    trajectory_ids: list[str] = []
    final_states: list[int] = []
    for row in rows:
        trajectory_id = row.get("trajectory_id")
        final_state = row.get("observation_payload", {}).get("final_state")
        if not isinstance(trajectory_id, str) or not trajectory_id:
            raise IncompleteCampaign(f"G2H {label} trajectory identity is invalid")
        if type(final_state) is not int or not 0 <= final_state < state_count:
            raise IncompleteCampaign(f"G2H {label} final-state index is invalid")
        trajectory_ids.append(trajectory_id)
        final_states.append(final_state)
    if len(trajectory_ids) != len(set(trajectory_ids)):
        raise IncompleteCampaign(f"G2H {label} trajectory identity is duplicated")
    return trajectory_ids, final_states


def _validate_kind_structure(
    structural_unit: Mapping[str, Any], *, expected_kinds: tuple[str, ...],
    state_count: int,
) -> None:
    availability = structural_unit.get("kind_availability")
    labels = structural_unit.get("ordered_outcome_labels_by_kind")
    dimensions = structural_unit.get("mapping_dimensions_by_kind")
    if (
        availability != list(expected_kinds)
        or not isinstance(labels, Mapping)
        or not isinstance(dimensions, Mapping)
        or set(labels) != set(expected_kinds)
        or set(dimensions) != set(expected_kinds)
    ):
        raise IncompleteCampaign("G2H structural kind keysets disagree")
    for kind in expected_kinds:
        ordered = labels[kind]
        shape = dimensions[kind]
        if (
            not isinstance(ordered, list)
            or not ordered
            or len(ordered) != len(set(ordered))
            or not isinstance(shape, Mapping)
            or shape.get("rows") != len(ordered)
            or shape.get("columns") != state_count
        ):
            raise IncompleteCampaign(f"G2H {kind} structural dimensions disagree")


def _packaging_vector(born: Mapping[str, Any], state_count: int) -> tuple[list[int], int]:
    packaging = born.get("packaging")
    if (
        not isinstance(packaging, list)
        or len(packaging) != state_count
        or not packaging
        or any(type(value) is not int or value < 0 for value in packaging)
    ):
        raise IncompleteCampaign("G2H Born packaging vector is invalid")
    n_pkg = 1 + max(packaging)
    return list(packaging), n_pkg


def _package_context_present(
    discovery: Mapping[str, Any], born: Mapping[str, Any]
) -> bool:
    for context in discovery.get("contexts", ()):
        if context.get("step_index") != born.get("step_index") or context.get("k") != born.get("k"):
            continue
        values = " ".join(
            str(context.get(key, "")).lower()
            for key in ("closure_id", "lens_id", "level_id", "protocol_step_id", "resolution_id")
        )
        if "packag" in values or "pkg" in values or "lens_p5" in values:
            return True
    return False


def _raw_trajectory_census_sha256(
    trajectory_ids: Sequence[str], final_states: Sequence[int]
) -> str:
    return sha256_bytes(canonical_json_bytes([
        {"final_state": state, "trajectory_id": trajectory_id}
        for trajectory_id, state in zip(trajectory_ids, final_states, strict=True)
    ]))


def _derived_discovery_with_package_rows(
    discovery: Mapping[str, Any], raw_rows: Sequence[Mapping[str, Any]],
    package_groups: Sequence[int], package_labels: Sequence[str],
    packaging_source: str,
) -> dict[str, Any]:
    derived = copy.deepcopy(dict(discovery))
    additions: list[dict[str, Any]] = []
    for raw, group in zip(raw_rows, package_groups, strict=True):
        row = copy.deepcopy(dict(raw))
        row["observation_label"] = package_labels[group]
        row["macrostate_label"] = package_labels[group]
        row["observation_payload"]["macro_group"] = group
        row["observation_payload"]["packaging_source"] = packaging_source
        additions.append(row)
    derived["rows"] = [*copy.deepcopy(list(discovery["rows"])), *additions]
    return derived


def _derived_structural_with_package(
    structural_unit: Mapping[str, Any], labels: Sequence[str], state_count: int,
) -> dict[str, Any]:
    derived = copy.deepcopy(dict(structural_unit))
    derived["kind_availability"] = ["raw", "pkg"]
    derived["ordered_outcome_labels_by_kind"]["pkg"] = list(labels)
    derived["mapping_dimensions_by_kind"]["pkg"] = {
        "columns": state_count, "rows": len(labels),
    }
    return derived
