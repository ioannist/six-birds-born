"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import copy
from typing import Any, Mapping, Sequence
from born_ladder.snapshot.errors import IncompleteCampaign, SpecMismatch
from born_ladder.snapshot.frozen_spec import FrozenSpec
from born_ladder.snapshot.g2a import _derive_unit_pair
from born_ladder.snapshot.record_helpers import _derived_discovery_with_package_rows, _derived_structural_with_package, _package_context_present, _packaging_vector, _raw_trajectory_census_sha256, _unit_discovery_rows, _validate_kind_structure, _validate_trajectory_rows
from born_ladder.snapshot.identities import kind_cell_id, stable_unit_id

def _direct_package_evidence(
    packaging: Sequence[int], final_states: Sequence[int],
) -> tuple[list[int], list[str], list[int], int, list[float], list[list[float]]]:
    """Evaluate the literal V19/V15 formula trees without a G2H fixture oracle."""
    n_pkg = 1 + max(packaging)
    groups = [packaging[state] for state in final_states]
    labels = [f"package_{index}" for index in range(n_pkg)]
    counts = [groups.count(index) for index in range(n_pkg)]
    total = len(groups)
    if total < 1 or sum(counts) != total:
        raise IncompleteCampaign("G2x reconstructed package count census disagrees")
    empirical = [count / total for count in counts]
    mapping = [
        [1.0 if packaging[state] == group else 0.0 for state in range(len(packaging))]
        for group in range(n_pkg)
    ]
    return groups, labels, counts, total, empirical, mapping


def _validate_dual_kind_parity(
    *, raw_rows: Sequence[Mapping[str, Any]], pkg_rows: Sequence[Mapping[str, Any]],
    packaging: Sequence[int], trajectory_count: int, state_count: int,
    structural_unit: Mapping[str, Any],
) -> None:
    raw_ids, final_states = _validate_trajectory_rows(
        raw_rows, trajectory_count=trajectory_count, state_count=state_count,
        label="G2x raw",
    )
    pkg_ids, _ = _validate_trajectory_rows(
        pkg_rows, trajectory_count=trajectory_count, state_count=state_count,
        label="G2x package",
    )
    groups, labels, _, _, _, _ = _direct_package_evidence(packaging, final_states)
    if raw_ids != pkg_ids:
        raise IncompleteCampaign("G2x raw/package trajectory order disagrees")
    if structural_unit["ordered_outcome_labels_by_kind"]["pkg"] != labels:
        raise IncompleteCampaign("G2x emitted package labels disagree with reconstruction")
    if (
        [row["observation_payload"].get("macro_group") for row in pkg_rows] != groups
        or [row.get("observation_label") for row in pkg_rows]
        != [labels[group] for group in groups]
    ):
        raise IncompleteCampaign("G2x emitted package evidence disagrees with reconstruction")


def _rekey_pair(
    spec: FrozenSpec, pair: Sequence[Mapping[str, Any]], *,
    population: str, experiment: str,
) -> list[dict[str, Any]]:
    result = [copy.deepcopy(dict(record)) for record in pair]
    first = result[0]
    identity = stable_unit_id(
        spec, source=experiment, experiment_id=experiment, config_id_or_null=None,
        seed=first["seed"], scale=first["scale"], runner_context_id=first["context"],
        resolution=first["resolution"], step_id=str(first["step"]),
        partition_id=first["partition"], expected_state_labels=first["ordered_state_labels"],
    )
    for kind, record in zip(("raw", "pkg"), result, strict=True):
        record["unit_id"] = identity
        record["kind_cell_id"] = kind_cell_id(identity, kind)
        record["raw_pkg_pairing_key"] = identity
        record["config_or_null"] = None
        record["eligibility"] = True
        record["frozen_inclusion_population"] = population
        record["exclusion_reason_code"] = None
        record["fixed_census_config_or_experiment_key"] = experiment
        record["source_key"] = "G2x"
        record["bootstrap_hierarchy_keys"] = [str(record["seed"]), experiment, "G2x"]
        record["applicable_control_record_links"] = []
    return result


def _derive_pair(
    spec: FrozenSpec, *, segment: Any, invocation: Mapping[str, Any],
    structural_unit: Mapping[str, Any], structural_sha256: str,
    runner_manifest_sha256: str, attempt_sha256: str,
    contract: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    born = segment.born[0]
    if segment.discovery is None:
        raise IncompleteCampaign("G2x complete suppression cannot produce a scientific unit")
    discovery = segment.discovery
    reconstruction = contract["derivation"]["packaging_suppression_reconstruction"]
    state_count = len(structural_unit.get("ordered_state_labels", ()))
    if state_count < 1:
        raise IncompleteCampaign("G2x structural state census is empty")
    packaging, n_pkg = _packaging_vector(born, state_count)
    raw_rows, pkg_rows = _unit_discovery_rows(born, discovery)
    trajectory_count = discovery.get("trajectory_count")
    if type(trajectory_count) is not int or trajectory_count < 1:
        raise IncompleteCampaign("G2x Discovery trajectory count is invalid")
    kinds = structural_unit.get("kind_availability")
    reconstruction_row = None
    if kinds == ["raw", "pkg"]:
        _validate_kind_structure(structural_unit, expected_kinds=("raw", "pkg"), state_count=state_count)
        _validate_dual_kind_parity(
            raw_rows=raw_rows, pkg_rows=pkg_rows, packaging=packaging,
            trajectory_count=trajectory_count, state_count=state_count,
            structural_unit=structural_unit,
        )
        selected_discovery, selected_structural = discovery, structural_unit
    elif kinds == ["raw"]:
        _validate_kind_structure(structural_unit, expected_kinds=("raw",), state_count=state_count)
        if n_pkg >= 2:
            raise IncompleteCampaign("G2x raw-only unit has nonqualifying package count")
        trajectory_ids, final_states = _validate_trajectory_rows(
            raw_rows, trajectory_count=trajectory_count,
            state_count=state_count, label="G2x raw-only",
        )
        if pkg_rows or _package_context_present(discovery, born):
            raise IncompleteCampaign("G2x raw-only unit contains package material")
        groups, labels, counts, total, empirical, mapping = _direct_package_evidence(
            packaging, final_states
        )
        selected_discovery = _derived_discovery_with_package_rows(
            discovery, raw_rows, groups, labels,
            reconstruction["activation"]["classification"],
        )
        selected_structural = _derived_structural_with_package(
            structural_unit, labels, state_count
        )
        reconstruction_row = {
            "M_pkg_or_content_hash": mapping,
            "attempt_record_sha256": attempt_sha256,
            "classification": reconstruction["activation"]["classification"],
            "config_id": segment.label,
            "integer_counts_pkg": counts,
            "invocation_id": invocation["invocation_id"],
            "ordered_pkg_outcome_labels": labels,
            "raw_trajectory_census_sha256": _raw_trajectory_census_sha256(trajectory_ids, final_states),
            "resolution": born["k"], "scale": born["scale"],
            "schema": reconstruction["artifact"]["schema"], "seed": born["seed"],
            "step_id": str(born["step_index"]),
            "structural_manifest_sha256": structural_sha256,
            "total_count_pkg": total, "unit_id": None, "unrounded_y_pkg": empirical,
        }
    else:
        raise IncompleteCampaign("G2x kind availability is not a closed raw/pkg shape")
    pair = _derive_unit_pair(
        spec, born=born, discovery=selected_discovery, audit=segment.audit,
        invocation={**invocation, "config_or_null": segment.label},
        structural_unit=selected_structural,
        structural_manifest_sha256=structural_sha256,
        attempt_record_sha256=attempt_sha256,
    )
    pair = _rekey_pair(
        spec, pair, population=contract["overlay"]["frozen_inclusion_population"],
        experiment=invocation["experiment"],
    )
    if reconstruction_row is not None:
        reconstruction_row["unit_id"] = pair[0]["unit_id"]
        if list(reconstruction_row) != reconstruction["artifact"]["field_order"]:
            raise SpecMismatch("frozen G2x reconstruction field order disagrees")
    return pair, reconstruction_row
