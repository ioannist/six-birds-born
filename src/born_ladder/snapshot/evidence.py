"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import copy
import math
from typing import Any, Mapping
from born_ladder.snapshot.errors import IncompleteCampaign
from born_ladder.snapshot.identities import kind_cell_id

_G2C_CONTROL_SOURCE_IDENTITY_FIELDS = (
    "unit_id", "kind_cell_id", "invocation_id", "source", "experiment",
    "config_or_null", "seed", "scale", "resolution", "context", "partition",
    "step", "structural_manifest_sha256", "attempt_record_sha256",
)


_G2C_CONTROL_SOURCE_ROUTE_FIELDS = (
    "eligibility", "exclusion_reason_code", "frozen_inclusion_population",
    "seed_block_key", "fixed_census_config_or_experiment_key", "source_key",
    "bootstrap_hierarchy_keys", "raw_pkg_pairing_key",
)


import re
from pathlib import Path
from typing import Sequence
from born_ladder.snapshot.completeness import invocation_id_for
from born_ladder.snapshot.identities import stable_unit_id
from born_ladder.snapshot.provenance import file_sha256

def g2c_control_input_projection(control_source: Mapping[str, Any]) -> dict[str, Any]:
    """Retain the complete numerical projection reconstructed from sealed bytes."""
    if not isinstance(control_source, Mapping):
        raise IncompleteCampaign("G2c sealed control-input source is not an object")
    unit_id = control_source.get("unit_id")
    kind_id = control_source.get("kind_cell_id")
    matches = [
        kind for kind in ("raw", "pkg")
        if isinstance(unit_id, str) and kind_cell_id(unit_id, kind) == kind_id
    ]
    if len(matches) != 1:
        raise IncompleteCampaign("G2c sealed control-input projection lacks one selected kind")
    kind = matches[0]
    fields = (
        *_G2C_CONTROL_SOURCE_IDENTITY_FIELDS,
        *_G2C_CONTROL_SOURCE_ROUTE_FIELDS,
        "integer_counts", "total_count", "ordered_state_labels",
        "ordered_union_outcome_labels", f"M_{kind}_or_content_hash",
        f"unrounded_y_{kind}", "unrounded_p_full", "basis_and_projector_inputs",
    )
    if any(field not in control_source for field in fields):
        raise IncompleteCampaign("G2c sealed control-input projection is incomplete")
    return {field: copy.deepcopy(control_source[field]) for field in fields}


def _g2c_exact_projection_equal(actual: Any, expected: Any) -> bool:
    """Compare a JSON projection with exact types/binary64 and unordered objects."""
    if type(actual) is not type(expected):
        return False
    if type(expected) is float:
        return math.isfinite(actual) and actual.hex() == expected.hex()
    if type(expected) is dict:
        return (
            len(actual) == len(expected)
            and set(actual) == set(expected)
            and all(
                _g2c_exact_projection_equal(actual[key], expected[key])
                for key in expected
            )
        )
    if type(expected) is list:
        return len(actual) == len(expected) and all(
            _g2c_exact_projection_equal(left, right)
            for left, right in zip(actual, expected, strict=True)
        )
    return actual == expected


def validate_g2c_control_input_binding(
    universal_record: Mapping[str, Any], control_source: Mapping[str, Any],
    *, sealed_control_input_projection: Mapping[str, Any] | None = None,
) -> None:
    """Bind the complete selected control projection to its scientific row."""
    if not isinstance(universal_record, Mapping) or not isinstance(
        control_source, Mapping
    ):
        raise IncompleteCampaign("G2c control-input binding requires two objects")
    for field in (*_G2C_CONTROL_SOURCE_IDENTITY_FIELDS, *_G2C_CONTROL_SOURCE_ROUTE_FIELDS):
        if field not in universal_record or field not in control_source or not (
            _g2c_exact_projection_equal(
                universal_record[field], control_source[field]
            )
        ):
            raise IncompleteCampaign(
                f"G2c control-source evidence identity differs at {field}"
            )
    source_projection = g2c_control_input_projection(control_source)
    kind = "raw" if f"M_raw_or_content_hash" in source_projection else "pkg"
    numeric_fields = (
        "integer_counts", "total_count", "ordered_state_labels",
        "ordered_union_outcome_labels", f"M_{kind}_or_content_hash",
        f"unrounded_y_{kind}", "unrounded_p_full", "basis_and_projector_inputs",
    )
    eligibility = universal_record.get("eligibility")
    if type(eligibility) is not bool:
        raise IncompleteCampaign("G2c control-input binding lacks Boolean eligibility")
    if sealed_control_input_projection is not None and (
        not isinstance(sealed_control_input_projection, Mapping)
        or not _g2c_exact_projection_equal(
            dict(sealed_control_input_projection), source_projection,
        )
    ):
        raise IncompleteCampaign(
            "G2c control-input projection differs from sealed reconstruction binding"
        )
    if eligibility:
        for field in numeric_fields:
            if field not in universal_record or field not in control_source or not (
                _g2c_exact_projection_equal(
                    universal_record[field], control_source[field]
                )
            ):
                raise IncompleteCampaign(
                    f"G2c scientific control-input projection differs at {field}"
                )
    else:
        # Excluded universal rows retain no scientific values.  Their numerical
        # source is authenticated by the separately retained projection captured
        # at sealed stdout/structural derivation, never by non-null presence.
        if any(
            field not in universal_record or universal_record[field] is not None
            for field in numeric_fields
        ):
            raise IncompleteCampaign(
                "G2c excluded universal scientific control-input projection is not null"
            )
        if sealed_control_input_projection is None:
            raise IncompleteCampaign(
                "G2c excluded control source lacks a sealed numerical projection binding"
            )
        if any(control_source.get(field) is None for field in numeric_fields):
            raise IncompleteCampaign(
                "G2c excluded control source lacks its sealed reconstruction inputs"
            )

# Production writers restored from the same historical implementation.

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

_NULLABLE_HIERARCHY = {"config_or_null", "trajectory"}

_THRESHOLD_POINTERS = {
    "mass": ("probability_mass_error", "/thresholds/items/15/value"),
    "parseval": ("parseval_residual", "/thresholds/items/6/value"),
    "rotation": ("qfull_rotation_residual", "/thresholds/items/7/value"),
    "distribution_absolute": ("distribution_absolute", "/thresholds/items/8/value"),
    "distribution_relative": ("distribution_relative", "/thresholds/items/9/value"),
}

_IMPLEMENTATION_POINTERS = {
    "universal_evidence_contract": "/completeness/universal_evidence_schema",
    "recognized_structural_exclusions": "/completeness/planned_exclusions",
    "mass_residual_tolerance": "/thresholds/items/15/value",
    "parseval_residual_tolerance": "/thresholds/items/6/value",
    "rotation_residual_tolerance": "/thresholds/items/7/value",
    "distribution_absolute_tolerance": "/thresholds/items/8/value",
    "distribution_relative_tolerance": "/thresholds/items/9/value",
    "g2c_v24_effective_schema": "/completeness/g2c_v24_effective_schema",
}

def universal_fields(
    spec: FrozenSpec, *, implementation_manifest_path: Path | None = None
) -> tuple[str, ...]:
    spec.audit_implementation_manifest(
        "evidence", manifest_path=implementation_manifest_path,
        declared_pointers=_IMPLEMENTATION_POINTERS,
    )
    contract = spec.get(
        "/completeness/universal_evidence_schema", expected_type=dict
    )
    groups = ("hierarchy", "eligibility", "empirical", "law_evidence", "inference", "controls")
    fields = [field for group in groups for field in contract[group]]
    if len(fields) != len(set(fields)):
        raise IncompleteCampaign("universal evidence schema has duplicate fields")
    return tuple(fields)

def residual_tolerance_contract(
    spec: FrozenSpec, *, implementation_manifest_path: Path | None = None,
    stage_profile: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Serve the exact frozen tolerance dimensions; never collapse abs/rel."""
    spec.audit_implementation_manifest(
        "evidence", manifest_path=implementation_manifest_path,
        declared_pointers=_IMPLEMENTATION_POINTERS,
    )
    values: dict[str, float] = {}
    for name, (threshold_id, pointer) in _THRESHOLD_POINTERS.items():
        item_pointer = pointer.rsplit("/", 1)[0]
        item = spec.get(item_pointer, expected_type=dict)
        if item.get("id") != threshold_id:
            raise IncompleteCampaign(f"frozen threshold pointer for {name} has wrong identity")
        value = spec.get(pointer)
        if type(value) not in (int, float) or not math.isfinite(float(value)):
            raise IncompleteCampaign(f"frozen threshold pointer for {name} is not finite numeric")
        values[name] = float(value)
    result = {
        "finite_residuals": {"mode": "finite"},
        "mass_residuals": {"absolute": values["mass"]},
        "parseval_residuals": {"absolute": values["parseval"]},
        "rotation_residuals": {"absolute": values["rotation"]},
        "identity_residuals": {
            "absolute": values["distribution_absolute"],
            "relative": values["distribution_relative"],
        },
        "sequential_residuals": {
            "absolute": values["distribution_absolute"],
            "relative": values["distribution_relative"],
        },
    }
    if stage_profile == "g2c":
        spec.get(_IMPLEMENTATION_POINTERS["g2c_v24_effective_schema"], expected_type=dict)
        result["rotation_residuals"] = {
            "mode": "all-sixteen-v22-certificate-comparisons"
        }
    return result

def validate_g2c_rotation_binding(
    spec: FrozenSpec,
    universal_record: Mapping[str, Any],
    control_source: Mapping[str, Any],
    control: Mapping[str, Any],
    rotation_evidence: Mapping[str, Any],
    *,
    stage_profile: str,
    sealed_control_input_projection: Mapping[str, Any] | None = None,
    implementation_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Reconstruct the v22 G2c instrument at the evidence-consumer boundary."""
    if stage_profile != "g2c":
        raise IncompleteCampaign("G2c certified evidence requires the g2c stage profile")
    frozen = residual_tolerance_contract(
        spec,
        implementation_manifest_path=implementation_manifest_path,
        stage_profile=stage_profile,
    )
    if frozen["rotation_residuals"] != {
        "mode": "all-sixteen-v22-certificate-comparisons"
    }:
        raise IncompleteCampaign("G2c certified rotation mode is not active")
    from born_ladder.snapshot.g2c_controls import validate_g2c_v22_rotation_evidence

    validate_g2c_control_input_binding(
        universal_record,
        control_source,
        sealed_control_input_projection=sealed_control_input_projection,
    )
    expected = validate_g2c_v22_rotation_evidence(
        spec,
        control_source,
        control,
        rotation_evidence,
        implementation_manifest_path=implementation_manifest_path,
    )
    residuals = universal_record.get("rotation_residuals")
    if type(residuals) is not dict or set(residuals) != set(expected["rotation_residuals"]):
        raise IncompleteCampaign(
            "G2c universal rotation residuals lack reconstructed evidence"
        )
    for name, target in expected["rotation_residuals"].items():
        value = residuals[name]
        if type(value) is not float or value.hex() != target.hex():
            raise IncompleteCampaign(
                f"G2c universal rotation residual {name} differs from reconstruction"
            )
    actual_pass = universal_record.get("pass_boolean_for_each_residual", {}).get(
        "rotation_residuals"
    )
    if type(actual_pass) is not bool or actual_pass is not expected["rotation_pass"]:
        raise IncompleteCampaign(
            "G2c universal rotation Boolean differs from reconstruction"
        )
    return expected

def _nonempty_string(name: str, value: Any) -> None:
    if not isinstance(value, str) or not value:
        raise IncompleteCampaign(f"per-unit {name} must be a nonempty string")

def _finite_tree(name: str, value: Any) -> None:
    if type(value) in (int, float):
        if not math.isfinite(float(value)):
            raise IncompleteCampaign(f"per-unit {name} contains a nonfinite number")
        return
    if isinstance(value, list):
        if not value:
            raise IncompleteCampaign(f"per-unit {name} is empty applicable evidence")
        for index, item in enumerate(value):
            _finite_tree(f"{name}[{index}]", item)
        return
    if isinstance(value, dict):
        if not value:
            raise IncompleteCampaign(f"per-unit {name} is empty applicable evidence")
        for key, item in value.items():
            if not isinstance(key, str):
                raise IncompleteCampaign(f"per-unit {name} has a non-string key")
            _finite_tree(f"{name}.{key}", item)
        return
    raise IncompleteCampaign(f"per-unit {name} must contain only finite numerics")

def _content_or_numeric(
    name: str, value: Any, *, content_root: Path | None
) -> None:
    if isinstance(value, dict) and set(value) == {"path", "sha256"}:
        _nonempty_string(f"{name}.path", value["path"])
        if not isinstance(value["sha256"], str) or not _HEX64.fullmatch(value["sha256"]):
            raise IncompleteCampaign(f"per-unit {name}.sha256 is malformed")
        if content_root is None:
            raise IncompleteCampaign(f"per-unit {name} content root is unavailable")
        path = (content_root / value["path"]).resolve()
        try:
            path.relative_to(content_root.resolve())
        except ValueError as error:
            raise IncompleteCampaign(f"per-unit {name} content path escapes root") from error
        if file_sha256(path) != value["sha256"]:
            raise IncompleteCampaign(f"per-unit {name} has a broken content hash")
        return
    _finite_tree(name, value)

def validate_per_unit_record(
    spec: FrozenSpec,
    record: Mapping[str, Any],
    *,
    expected_structural_manifest_sha256: str,
    expected_attempt_record_sha256: str,
    content_root: Path | None = None,
    implementation_manifest_path: Path | None = None,
) -> None:
    spec.audit_implementation_manifest(
        "evidence", manifest_path=implementation_manifest_path,
        declared_pointers=_IMPLEMENTATION_POINTERS,
    )
    expected = set(universal_fields(
        spec, implementation_manifest_path=implementation_manifest_path
    ))
    if set(record) != expected:
        missing = sorted(expected - set(record))
        unknown = sorted(set(record) - expected)
        raise IncompleteCampaign(
            f"per-unit field mismatch missing={missing} unknown={unknown}"
        )
    reason = record["exclusion_reason_code"]
    eligibility = record["eligibility"]
    if type(eligibility) is not bool:
        raise IncompleteCampaign("per-unit eligibility must be Boolean")
    recognized_reasons = spec.get("/completeness/planned_exclusions", expected_type=list)
    if eligibility:
        if reason is not None:
            raise IncompleteCampaign("eligible per-unit record has an exclusion reason")
    elif reason not in recognized_reasons:
        raise IncompleteCampaign("excluded per-unit record lacks a recognized structural reason")
    for name, value in record.items():
        if value is None and name not in _NULLABLE_HIERARCHY and name != "exclusion_reason_code":
            if eligibility:
                raise IncompleteCampaign(
                    f"eligible per-unit {name} is null"
                )
    for name in (
        "unit_id", "kind_cell_id", "invocation_id", "source", "experiment",
        "context", "partition", "step", "frozen_inclusion_population",
        "seed_block_key", "fixed_census_config_or_experiment_key", "source_key",
        "raw_pkg_pairing_key", "structural_manifest_sha256", "attempt_record_sha256",
    ):
        _nonempty_string(name, record[name])
    for name in (
        "unit_id", "kind_cell_id", "invocation_id", "structural_manifest_sha256",
        "attempt_record_sha256",
    ):
        if not _HEX64.fullmatch(record[name]):
            raise IncompleteCampaign(f"per-unit {name} must be a SHA-256 digest")
    for name, observed, expected_hash in (
        ("structural_manifest_sha256", record["structural_manifest_sha256"], expected_structural_manifest_sha256),
        ("attempt_record_sha256", record["attempt_record_sha256"], expected_attempt_record_sha256),
    ):
        if not isinstance(expected_hash, str) or not _HEX64.fullmatch(expected_hash):
            raise IncompleteCampaign(f"expected {name} binding is malformed")
        if observed != expected_hash:
            raise IncompleteCampaign(f"per-unit {name} disagrees with expected evidence link")
    expected_invocation_id = invocation_id_for(
        spec,
        experiment=record["experiment"],
        config_or_null=record["config_or_null"],
        seed=record["seed"],
        scale=record["scale"],
    )
    if record["invocation_id"] != expected_invocation_id:
        raise IncompleteCampaign("per-unit invocation_id disagrees with frozen identity")
    expected_unit_id = stable_unit_id(
        spec,
        source=record["source"],
        experiment_id=record["experiment"],
        config_id_or_null=record["config_or_null"],
        seed=record["seed"],
        scale=record["scale"],
        runner_context_id=record["context"],
        resolution=record["resolution"],
        step_id=record["step"],
        partition_id=record["partition"],
        expected_state_labels=record["ordered_state_labels"],
        implementation_manifest_path=implementation_manifest_path,
    )
    if record["unit_id"] != expected_unit_id:
        raise IncompleteCampaign("per-unit unit_id disagrees with frozen identity")
    expected_kind_ids = {
        kind_cell_id(expected_unit_id, "raw"),
        kind_cell_id(expected_unit_id, "pkg"),
    }
    if record["kind_cell_id"] not in expected_kind_ids:
        raise IncompleteCampaign("per-unit kind_cell_id disagrees with raw/pkg identity")
    if record["raw_pkg_pairing_key"] != expected_unit_id:
        raise IncompleteCampaign("per-unit raw_pkg_pairing_key disagrees with unit_id")
    for name in ("seed", "scale", "resolution", "total_count"):
        value = record[name]
        if type(value) is not int or value < 0 or (name in {"scale", "resolution"} and value == 0):
            raise IncompleteCampaign(f"per-unit {name} has an invalid integer")
    counts = record["integer_counts"]
    if not isinstance(counts, list) or not counts or not all(type(x) is int and x >= 0 for x in counts):
        raise IncompleteCampaign("per-unit integer_counts must be nonnegative integers")
    if sum(counts) != record["total_count"]:
        raise IncompleteCampaign("per-unit integer_counts disagree with total_count")
    for name in ("ordered_state_labels", "ordered_union_outcome_labels"):
        labels = record[name]
        if not isinstance(labels, list) or not labels or not all(isinstance(x, str) and x for x in labels):
            raise IncompleteCampaign(f"per-unit {name} must be nonempty strings")
        if len(labels) != len(set(labels)):
            raise IncompleteCampaign(f"per-unit {name} contains duplicates")
    links = record["applicable_control_record_links"]
    if not isinstance(links, list) or not all(isinstance(x, str) and x for x in links):
        raise IncompleteCampaign("per-unit control links must be strings")
    hierarchy = record["bootstrap_hierarchy_keys"]
    if not isinstance(hierarchy, list) or not hierarchy or not all(isinstance(x, str) and x for x in hierarchy):
        raise IncompleteCampaign("per-unit bootstrap hierarchy keys are invalid")
    for name in (
        "M_raw_or_content_hash", "M_pkg_or_content_hash", "basis_and_projector_inputs",
        "spectral_coefficients", "law_numerators", "state_space_prediction",
        "mapped_outcome_prediction",
    ):
        _content_or_numeric(name, record[name], content_root=content_root)
    for name in (
        "unrounded_y_raw", "unrounded_y_pkg", "unrounded_p_full", "normalization_mass",
        "dtv_loss", "brier_score", "pairwise_contrast", "finite_residuals",
        "mass_residuals", "parseval_residuals", "rotation_residuals",
        "identity_residuals", "sequential_residuals",
    ):
        if record[name] is not None:
            _finite_tree(name, record[name])
    if type(record["tie_flag"]) is not bool:
        raise IncompleteCampaign("per-unit tie_flag must be Boolean")
    tolerances = record["tolerance_for_each_residual"]
    passes = record["pass_boolean_for_each_residual"]
    frozen_tolerances = residual_tolerance_contract(
        spec, implementation_manifest_path=implementation_manifest_path
    )
    if not isinstance(tolerances, dict) or set(tolerances) != set(frozen_tolerances):
        raise IncompleteCampaign("per-unit residual tolerances have a non-frozen schema")
    if tolerances != frozen_tolerances:
        raise IncompleteCampaign("per-unit residual tolerance disagrees with frozen value")
    if not isinstance(passes, dict) or set(passes) != set(frozen_tolerances):
        raise IncompleteCampaign("per-unit residual pass map has a non-frozen schema")
    for name, tolerance in frozen_tolerances.items():
        residuals = record[name]
        if residuals is None:
            expected_pass = False
        else:
            def collect(value: Any) -> list[float]:
                values: list[float] = []
                if type(value) in (int, float):
                    values.append(float(value))
                elif isinstance(value, (list, dict)):
                    for item in (value if isinstance(value, list) else value.values()):
                        values.extend(collect(item))
                return values

            if tolerance == {"mode": "finite"}:
                values = collect(residuals)
                expected_pass = bool(values) and all(math.isfinite(value) for value in values)
            elif set(tolerance) == {"absolute"}:
                values = collect(residuals)
                expected_pass = bool(values) and all(
                    math.isfinite(value) and abs(value) <= tolerance["absolute"]
                    for value in values
                )
            elif set(tolerance) == {"absolute", "relative"}:
                if not isinstance(residuals, dict) or set(residuals) != {"absolute", "relative"}:
                    raise IncompleteCampaign(
                        f"per-unit {name} must preserve absolute and relative residuals"
                    )
                absolute = collect(residuals["absolute"])
                relative = collect(residuals["relative"])
                expected_pass = bool(absolute) and bool(relative) and all(
                    math.isfinite(value) and abs(value) <= tolerance["absolute"]
                    for value in absolute
                ) and all(
                    math.isfinite(value) and abs(value) <= tolerance["relative"]
                    for value in relative
                )
            else:
                raise IncompleteCampaign(f"per-unit {name} tolerance mode is invalid")
        if type(passes[name]) is not bool or passes[name] is not expected_pass:
            raise IncompleteCampaign(f"per-unit {name} pass Boolean disagrees with residuals")

def validate_per_unit_records(
    spec: FrozenSpec,
    records: Sequence[Mapping[str, Any]],
    *,
    expected_structural_manifest_sha256: str,
    expected_attempt_record_sha256: str,
    content_root: Path | None = None,
    implementation_manifest_path: Path | None = None,
) -> None:
    if not records:
        raise IncompleteCampaign("per-unit registry is empty")
    unit_ids: list[str] = []
    kind_ids: list[str] = []
    for record in records:
        validate_per_unit_record(
            spec, record,
            expected_structural_manifest_sha256=expected_structural_manifest_sha256,
            expected_attempt_record_sha256=expected_attempt_record_sha256,
            content_root=content_root,
            implementation_manifest_path=implementation_manifest_path,
        )
        unit_ids.append(record["unit_id"])
        kind_ids.append(record["kind_cell_id"])
    if len(kind_ids) != len(set(kind_ids)):
        raise IncompleteCampaign("per-unit registry has duplicate kind_cell_id")
    for unit_id in set(unit_ids):
        indices = [index for index, value in enumerate(unit_ids) if value == unit_id]
        if len(indices) != 2:
            raise IncompleteCampaign("per-unit registry lacks an exact raw/pkg pair")
        expected = {kind_cell_id(unit_id, "raw"), kind_cell_id(unit_id, "pkg")}
        observed = {kind_ids[index] for index in indices}
        if observed != expected:
            raise IncompleteCampaign("per-unit registry raw/pkg pairing is incomplete")
