"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from born_ladder.snapshot.completeness import AttemptRegistry, StructuralGate
from born_ladder.snapshot.collector_structural import _unit_from_raw
from born_ladder.snapshot.errors import ControlFailureEvidence, IncompleteCampaign, SpecMismatch
from born_ladder.snapshot.evidence import g2c_control_input_projection, validate_g2c_control_input_binding
from born_ladder.snapshot.frozen_spec import FrozenSpec, canonical_json_bytes, sha256_bytes
from born_ladder.snapshot.g2c_collector_structural import parse_g2c_raw_segments
from born_ladder.snapshot.g2c_controls import validate_g2c_v22_rotation_evidence
from born_ladder.snapshot.record_helpers import _science_fields
from born_ladder.snapshot.source_pairs import _derive_pair as _derive_source_pair
from born_ladder.snapshot.identities import kind_cell_id, stable_unit_id
from born_ladder.snapshot.universal_shapes import canonical_jsonl_bytes, validate_stage_records

_HEX64 = re.compile(r"[0-9a-f]{64}")


_POINTERS = {
    "g2c_units_campaign": "/confirmation_data/campaigns/6",
    "g2c_units_derivation": "/completeness/g2c_raw_stdout_derivation",
    "g2c_units_plan": "/artifact_paths/g2c_per_unit_reproduction_plan",
    "g2c_units_shapes": "/completeness/universal_evidence_shapes",
    "g2c_units_effective_schema": "/completeness/g2c_v24_effective_schema",
}


@dataclass(frozen=True)
class SealedG2CUnitDrafts:
    records: tuple[dict[str, Any], ...]

    control_sources: tuple[dict[str, Any], ...]

    control_input_projections: dict[str, dict[str, Any]]

    package_reconstruction_rows: tuple[dict[str, Any], ...]

    attempt_bindings: dict[str, str]

    structural_bindings: dict[str, str]

    dual_kind_parity_units: int



@dataclass(frozen=True)
class G2CArtifacts:
    units: bytes

    units_sha256: str

    controls: bytes

    controls_sha256: str

    package_reconstruction: bytes

    package_reconstruction_sha256: str

    records: tuple[dict[str, Any], ...]

    controls_records: tuple[dict[str, Any], ...]

    control_sources: tuple[dict[str, Any], ...]

    control_input_projections: dict[str, dict[str, Any]]

    reconstructed_units: int

    dual_kind_parity_units: int



def _contract(spec: FrozenSpec, manifest: Path | None = None) -> dict[str, Any]:
    spec.audit_implementation_manifest(
        "g2c_units", manifest_path=manifest, declared_pointers=_POINTERS
    )
    derivation = spec.get(_POINTERS["g2c_units_derivation"], expected_type=dict)
    overlay = derivation.get("overlays", {}).get("g2c_v2")
    plan = spec.get(_POINTERS["g2c_units_plan"], expected_type=dict)
    if (
        derivation.get("overlay_keys") != ["g2c_v2"]
        or not isinstance(overlay, dict)
        or plan.get("derivation_registry_pointer") != _POINTERS["g2c_units_derivation"]
        or plan.get("artifacts", [None] * 10)[6:10]
        != [
            "rb1v2_g2c_v23_units.jsonl",
            "rb1v2_g2c_v23_controls.jsonl",
            "rb1v2_g2c_v23_pkg_reconstruction.jsonl",
            "rb1v2_g2c_v23_evaluation.json",
        ]
        or overlay.get("control_link", {}).get("dedicated_link_order") != ["g2c_controls"]
    ):
        raise SpecMismatch("frozen G2c unit transport contract disagrees")
    return {
        "campaign": spec.get(_POINTERS["g2c_units_campaign"], expected_type=dict),
        "derivation": derivation,
        "overlay": overlay,
        "plan": plan,
        "shapes": spec.get(_POINTERS["g2c_units_shapes"], expected_type=dict),
        "effective_schema": spec.get(
            _POINTERS["g2c_units_effective_schema"], expected_type=dict
        ),
    }


def _source_key(experiment: str) -> str:
    return "EXP-112" if experiment == "EXP-112" else "G2x"


def _rekey_pair(
    spec: FrozenSpec,
    pair: Sequence[Mapping[str, Any]],
    *,
    invocation: Mapping[str, Any],
    label: str,
    population: str,
    structural_unit: Mapping[str, Any],
) -> list[dict[str, Any]]:
    identity_spec = getattr(spec, "_g2c_source_spec", spec)
    result = [copy.deepcopy(dict(record)) for record in pair]
    for record in result:
        record["context"] = structural_unit["runner_context_id"]
        record["partition"] = structural_unit["partition_id"]
        record["resolution"] = structural_unit["resolution"]
        record["step"] = int(structural_unit["step_id"])
    first = result[0]
    config = label if invocation["experiment"] == "EXP-112" else None
    identity = stable_unit_id(
        identity_spec,
        source=invocation["experiment"],
        experiment_id=invocation["experiment"],
        config_id_or_null=config,
        seed=first["seed"],
        scale=first["scale"],
        runner_context_id=first["context"],
        resolution=first["resolution"],
        step_id=str(first["step"]),
        partition_id=first["partition"],
        expected_state_labels=first["ordered_state_labels"],
    )
    eligible = not (invocation["experiment"] == "EXP-112" and label == "empty")
    for kind, record in zip(("raw", "pkg"), result, strict=True):
        record["unit_id"] = identity
        record["kind_cell_id"] = kind_cell_id(identity, kind)
        record["raw_pkg_pairing_key"] = identity
        record["config_or_null"] = config
        record["eligibility"] = eligible
        record["exclusion_reason_code"] = (
            None if eligible else "EMPTY_CONFIG_STRUCTURAL_EXCLUSION"
        )
        record["frozen_inclusion_population"] = population
        group = label if invocation["experiment"] == "EXP-112" else invocation["experiment"]
        record["fixed_census_config_or_experiment_key"] = group
        record["source_key"] = _source_key(invocation["experiment"])
        record["bootstrap_hierarchy_keys"] = [
            str(record["seed"]), group, record["source_key"]
        ]
        record["applicable_control_record_links"] = []
    return result


def _pair_and_control_source(
    spec: FrozenSpec,
    *,
    segment: Any,
    born: Mapping[str, Any],
    invocation: Mapping[str, Any],
    structural_unit: Mapping[str, Any],
    structural_sha256: str,
    runner_sha256: str,
    attempt_sha256: str,
    contract: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    local_contract = dict(contract)
    local_contract["overlay"] = {
        **contract["overlay"],
        "frozen_inclusion_population": contract["overlay"]["population"]["identifier"],
    }
    selected_born = born
    selected_audit = segment.audit
    selected_invocation = invocation
    selected_structural = structural_unit
    empty_exp112 = invocation["experiment"] == "EXP-112" and segment.label == "empty"
    if empty_exp112:
        # The sealed universal row is required to null its scientific fields, but
        # the construction-time control source is evaluated from the governed raw
        # evidence before that serialization rule is applied.  Reconstruct that
        # in-memory representation with a non-excluded label solely to prevent the
        # shared builder from nulling it; the original invocation identity is
        # restored below before either record is retained.
        shadow_label = next(
            value for value in spec.get("/grid/labels", expected_type=list)
            if value != "empty"
        )
        selected_born = copy.deepcopy(dict(born))
        selected_born["cell"] = shadow_label
        selected_audit = copy.deepcopy(dict(segment.audit))
        selected_audit["config_name"] = shadow_label
        selected_invocation = {**invocation, "config_or_null": shadow_label}
        selected_structural = _unit_from_raw(
            selected_born,
            segment.discovery,
            selected_audit,
            selected_invocation,
        )
    one = type(segment)(
        selected_born["cell"],
        (selected_born,),
        segment.discovery,
        selected_audit,
        segment.suppressed_pairs,
        segment.complete_suppression,
    )
    pair, reconstruction = _derive_source_pair(
        spec,
        segment=one,
        invocation=selected_invocation,
        structural_unit=selected_structural,
        structural_sha256=structural_sha256,
        runner_manifest_sha256=runner_sha256,
        attempt_sha256=attempt_sha256,
        contract=local_contract,
    )
    pair = _rekey_pair(
        spec,
        pair,
        invocation=invocation,
        label=segment.label,
        population=contract["overlay"]["population"]["identifier"],
        structural_unit=structural_unit,
    )
    control = copy.deepcopy(pair)
    if empty_exp112:
        science = _science_fields(contract["shapes"]["stage_profiles"]["g2c"])
        for target in pair:
            for field in science:
                target[field] = None
    if reconstruction is not None:
        reconstruction["unit_id"] = pair[0]["unit_id"]
        reconstruction["config_id"] = segment.label
    return pair, control, reconstruction


def require_scientific_g2c_segments(segments: Sequence[Any]) -> None:
    """Apply complete-suppression preemption before any unit/control calculation."""
    if any(segment.complete_suppression is not None for segment in segments):
        raise IncompleteCampaign(
            "G2c complete suppression preempts unit construction and statistics"
        )


def derive_sealed_g2c_unit_drafts(
    spec: FrozenSpec,
    *,
    attempt_registry: AttemptRegistry,
    structural_gate: StructuralGate,
    implementation_manifest_path: Path | None = None,
) -> SealedG2CUnitDrafts:
    """Derive the complete ordered mixed-source census from sealed evidence."""
    contract = _contract(spec, implementation_manifest_path)
    source_spec = getattr(spec, "_g2c_source_spec", None)
    if not isinstance(source_spec, FrozenSpec):
        raise SpecMismatch("G2c v22 derivation requires the fixed signed-v21 source loader")
    if type(attempt_registry) is not AttemptRegistry or type(structural_gate) is not StructuralGate:
        raise IncompleteCampaign("G2c derivation requires production-sealed objects")
    campaign = contract["campaign"]["name"]
    attempt_registry.require_binding(source_spec, campaign, attempt_registry.census_sha256)
    structural, runner_hashes = structural_gate.records_and_runner_record_sha256s_for(
        source_spec, campaign, attempt_registry.census_sha256
    )
    invocations = attempt_registry.invocation_records()
    if [row["invocation_id"] for row in structural] != [
        row["invocation_id"] for row in invocations
    ]:
        raise IncompleteCampaign("G2c structural/manifest order disagrees")
    records: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    reconstructions: list[dict[str, Any]] = []
    parity = 0
    structural_bindings: dict[str, str] = {}
    attempt_bindings: dict[str, str] = {}
    for structural_record, invocation in zip(structural, invocations, strict=True):
        identity = invocation["invocation_id"]
        structural_sha = sha256_bytes(canonical_json_bytes(structural_record))
        attempt_sha = attempt_registry.successful_attempt_record_sha256(identity)
        structural_bindings[identity] = structural_sha
        attempt_bindings[identity] = attempt_sha
        segments = parse_g2c_raw_segments(
            source_spec,
            attempt_registry.successful_stdout(identity),
            invocation,
            implementation_manifest_path=implementation_manifest_path,
        )
        require_scientific_g2c_segments(segments)
        unit_map = {
            (row["config_id"], row["step_id"], row["resolution"]): row
            for row in structural_record["units"]
        }
        if len(unit_map) != len(structural_record["units"]):
            raise IncompleteCampaign("G2c structural unit identity repeats")
        observed: list[tuple[str, str, int]] = []
        for segment in segments:
            for born in segment.born:
                key = (segment.label, str(born["step_index"]), born["k"])
                unit = unit_map.get(key)
                if unit is None:
                    raise IncompleteCampaign("G2c Born record lacks structural unit")
                pair, control_pair, reconstruction = _pair_and_control_source(
                    source_spec,
                    segment=segment,
                    born=born,
                    invocation=invocation,
                    structural_unit=unit,
                    structural_sha256=structural_sha,
                    runner_sha256=runner_hashes[identity],
                    attempt_sha256=attempt_sha,
                    contract=contract,
                )
                records.extend(pair)
                controls.extend(control_pair)
                parity += unit["kind_availability"] == ["raw", "pkg"]
                if reconstruction is not None:
                    reconstructions.append(reconstruction)
                observed.append(key)
        expected = [
            (row["config_id"], row["step_id"], row["resolution"])
            for row in structural_record["units"]
        ]
        if observed != expected:
            raise IncompleteCampaign("G2c derived unit order differs from structural order")
    projections = {
        row["kind_cell_id"]: g2c_control_input_projection(row) for row in controls
    }
    if len(projections) != len(controls):
        raise IncompleteCampaign("G2c sealed control-input projection identities repeat")
    return SealedG2CUnitDrafts(
        records=tuple(records),
        control_sources=tuple(controls),
        control_input_projections=projections,
        package_reconstruction_rows=tuple(reconstructions),
        attempt_bindings=attempt_bindings,
        structural_bindings=structural_bindings,
        dual_kind_parity_units=parity,
    )


def bind_g2c_rotation_result(
    spec: FrozenSpec,
    record: dict[str, Any],
    *,
    control_source: Mapping[str, Any],
    control: Mapping[str, Any],
    rotation_evidence: Mapping[str, Any],
    sealed_control_input_projection: Mapping[str, Any],
    implementation_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Reconstruct and bind the v22 rotation result retained by a universal row."""
    validate_g2c_control_input_binding(
        record,
        control_source,
        sealed_control_input_projection=sealed_control_input_projection,
    )
    try:
        reconstructed = validate_g2c_v22_rotation_evidence(
            spec,
            control_source,
            control,
            rotation_evidence,
            implementation_manifest_path=implementation_manifest_path,
        )
    except (ControlFailureEvidence, SpecMismatch) as error:
        raise IncompleteCampaign(
            f"G2c certified rotation replicate evidence reconstruction failed: {error}"
        ) from error
    pass_map = record.get("pass_boolean_for_each_residual")
    if pass_map is None:
        pass_map = {}
        record["pass_boolean_for_each_residual"] = pass_map
    if type(pass_map) is not dict:
        raise IncompleteCampaign("G2c universal residual-pass map is not an object")
    record["rotation_residuals"] = copy.deepcopy(
        reconstructed["rotation_residuals"]
    )
    pass_map["rotation_residuals"] = reconstructed["rotation_pass"]
    return reconstructed


def finalize_g2c_artifacts(
    spec: FrozenSpec,
    drafts: SealedG2CUnitDrafts,
    *,
    control_rows: Sequence[Mapping[str, Any]],
    rotation_evidence: Mapping[str, Mapping[str, Any]],
    implementation_manifest_path: Path | None = None,
) -> G2CArtifacts:
    """Link, validate, and canonicalize the unit, control and reconstruction streams."""
    contract = _contract(spec, implementation_manifest_path)
    controls_raw = canonical_jsonl_bytes(control_rows)
    controls_sha = sha256_bytes(controls_raw)
    link = {
        "path": contract["overlay"]["control_link"]["artifact"],
        "sha256": controls_sha,
    }
    linked = [copy.deepcopy(record) for record in drafts.records]
    controls_by_id = {row.get("kind_cell_id"): row for row in control_rows}
    sources_by_id = {
        row.get("kind_cell_id"): row for row in drafts.control_sources
    }
    projections_by_id = drafts.control_input_projections
    if (
        len(sources_by_id) != len(drafts.control_sources)
        or type(projections_by_id) is not dict
        or set(projections_by_id) != set(sources_by_id)
    ):
        raise IncompleteCampaign("G2c control-source identities repeat")
    if len(controls_by_id) != len(control_rows) or set(controls_by_id) != set(rotation_evidence):
        raise IncompleteCampaign("G2c control and rotation-evidence identities disagree")
    for record in linked:
        record["applicable_control_record_links"] = [copy.deepcopy(link)]
        control = controls_by_id.get(record["kind_cell_id"])
        detail = rotation_evidence.get(record["kind_cell_id"])
        control_source = sources_by_id.get(record["kind_cell_id"])
        if control is None or control_source is None or detail is None:
            raise IncompleteCampaign("G2c linked control evidence is absent")
        reconstructed = bind_g2c_rotation_result(
            spec,
            record,
            control_source=control_source,
            control=control,
            rotation_evidence=detail,
            sealed_control_input_projection=projections_by_id[record["kind_cell_id"]],
            implementation_manifest_path=implementation_manifest_path,
        )
        expected_rotation = reconstructed["rotation_residuals"]
        if control.get("rotation_residuals") != expected_rotation:
            raise IncompleteCampaign(
                "G2c linked control rotation residuals disagree with replicate evidence"
            )
        replicate_keys = contract["derivation"]["controls"]["rotation"]["rng"][
            "replicate_record_keys"
        ]
        replicates = detail.get("replicates")
        if (
            type(replicates) is not list
            or len(replicates) != 16
            or any(
                not isinstance(item, Mapping)
                or len(item) != len(replicate_keys)
                or set(item) != set(replicate_keys)
                for item in replicates
            )
            or control.get("normalization_mass_q_full_control") is None
        ):
            raise IncompleteCampaign("G2c certified replicate evidence is incomplete")
        record["tolerance_for_each_residual"]["rotation_residuals"] = {
            "absolute_or_null": None,
            "relative_or_null": None,
            "comparison": "all-sixteen-v22-certificate-comparisons",
        }
        record["parseval_residuals"] = copy.deepcopy(control["parseval_residuals"])
        record["pass_boolean_for_each_residual"]["parseval_residuals"] = control[
            "pass_boolean_for_each_control"
        ]["parseval"]
        if (
            (record["eligibility"] and record["spectral_coefficients"] != control.get(
                "spectral_coefficients"
            ))
            or record["parseval_residuals"] != control.get("parseval_residuals")
            or record["rotation_residuals"] != control.get("rotation_residuals")
        ):
            raise IncompleteCampaign(
                "G2c universal scientific fields disagree with linked controls"
            )
    validated = validate_stage_records(
        spec,
        linked,
        stage_profile="g2c",
        expected_structural_manifest_sha256=drafts.structural_bindings,
        expected_attempt_record_sha256=drafts.attempt_bindings,
        implementation_manifest_path=implementation_manifest_path,
        g2c_control_sources=drafts.control_sources,
        g2c_control_input_projections=drafts.control_input_projections,
        g2c_controls=control_rows,
        g2c_rotation_evidence=rotation_evidence,
    )
    published = tuple(
        {key: value for key, value in record.items() if key != "_derived_kind"}
        for record in validated
    )
    if len(control_rows) != len(published):
        raise IncompleteCampaign("G2c control/unit census disagrees")
    expected_pairs = [
        (record["unit_id"], record["kind_cell_id"]) for record in published
    ]
    observed_pairs = [
        (record.get("unit_id"), record.get("kind_cell_id")) for record in control_rows
    ]
    if observed_pairs != expected_pairs or len(set(observed_pairs)) != len(observed_pairs):
        raise IncompleteCampaign("G2c control links are not one-to-one in unit order")
    unit_raw = canonical_jsonl_bytes(published)
    reconstruction_contract = contract["derivation"][
        "packaging_suppression_reconstruction"
    ]
    reconstruction_artifact = reconstruction_contract["artifact"]
    reconstruction_rows: list[dict[str, Any]] = []
    seen_reconstructed: set[str] = set()
    by_unit: dict[str, list[dict[str, Any]]] = {}
    for record in published:
        by_unit.setdefault(record["unit_id"], []).append(record)
    for value in drafts.package_reconstruction_rows:
        row = copy.deepcopy(dict(value))
        if (
            list(row) != reconstruction_artifact["field_order"]
            or row.get("schema") != reconstruction_artifact["schema"]
            or row.get("classification")
            != reconstruction_contract["activation"]["classification"]
        ):
            raise IncompleteCampaign("G2c package-reconstruction row schema disagrees")
        unit_id = row.get("unit_id")
        matches = by_unit.get(unit_id, [])
        if (
            type(unit_id) is not str
            or not _HEX64.fullmatch(unit_id)
            or unit_id in seen_reconstructed
            or len(matches) != 2
            or {record["kind_cell_id"] for record in matches}
            != {kind_cell_id(unit_id, "raw"), kind_cell_id(unit_id, "pkg")}
        ):
            raise IncompleteCampaign("G2c reconstructed row lacks one universal raw/pkg pair")
        seen_reconstructed.add(unit_id)
        pkg = next(record for record in matches if record["kind_cell_id"] == kind_cell_id(unit_id, "pkg"))
        labels = row.get("ordered_pkg_outcome_labels")
        counts = row.get("integer_counts_pkg")
        total = row.get("total_count_pkg")
        empirical = row.get("unrounded_y_pkg")
        mapping = row.get("M_pkg_or_content_hash")
        if (
            type(labels) is not list
            or not labels
            or len(set(labels)) != len(labels)
            or type(counts) is not list
            or len(counts) != len(labels)
            or any(type(item) is not int or item < 0 for item in counts)
            or type(total) is not int
            or total < 1
            or sum(counts) != total
            or empirical != [count / total for count in counts]
            or type(mapping) is not list
            or len(mapping) != len(labels)
            or any(type(vector) is not list or len(vector) != row.get("scale") for vector in mapping)
            or any(
                type(row.get(field)) is not str
                or not _HEX64.fullmatch(row[field])
                for field in (
                    "attempt_record_sha256", "invocation_id",
                    "raw_trajectory_census_sha256", "structural_manifest_sha256",
                )
            )
            or type(row.get("resolution")) is not int
            or row["resolution"] < 1
            or type(row.get("scale")) is not int
            or row["scale"] < 1
            or type(row.get("seed")) is not int
            or row["seed"] < 0
            or type(row.get("step_id")) is not str
            or not row["step_id"]
            or type(row.get("config_id")) is not str
            or not row["config_id"]
            or pkg.get("invocation_id") != row["invocation_id"]
            or pkg.get("attempt_record_sha256") != row["attempt_record_sha256"]
            or pkg.get("structural_manifest_sha256") != row["structural_manifest_sha256"]
            or pkg.get("seed") != row["seed"]
            or pkg.get("scale") != row["scale"]
            or pkg.get("resolution") != row["resolution"]
            or str(pkg.get("step")) != row["step_id"]
            or pkg.get("ordered_union_outcome_labels", [])[-len(labels):] != labels
            or pkg.get("integer_counts", [])[-len(labels):] != counts
            or pkg.get("total_count") != total
            or pkg.get("unrounded_y_pkg", [])[-len(labels):] != empirical
            or pkg.get("M_pkg_or_content_hash", [])[-len(labels):] != mapping
        ):
            raise IncompleteCampaign("G2c package-reconstruction numeric or parity binding disagrees")
        reconstruction_rows.append(row)
    reconstruction_raw = canonical_jsonl_bytes(reconstruction_rows)
    result = G2CArtifacts(
        units=unit_raw,
        units_sha256=sha256_bytes(unit_raw),
        controls=controls_raw,
        controls_sha256=controls_sha,
        package_reconstruction=reconstruction_raw,
        package_reconstruction_sha256=sha256_bytes(reconstruction_raw),
        records=tuple(copy.deepcopy(record) for record in published),
        controls_records=tuple(copy.deepcopy(dict(record)) for record in control_rows),
        control_sources=tuple(
            copy.deepcopy(dict(record)) for record in drafts.control_sources
        ),
        control_input_projections=copy.deepcopy(drafts.control_input_projections),
        reconstructed_units=len(reconstruction_rows),
        dual_kind_parity_units=drafts.dual_kind_parity_units,
    )
    validate_g2c_artifacts(result)
    return result


def validate_g2c_artifacts(value: G2CArtifacts) -> None:
    if type(value) is not G2CArtifacts:
        raise IncompleteCampaign("G2c artifact bundle is not production-built")
    for raw, digest, label in (
        (value.units, value.units_sha256, "units"),
        (value.controls, value.controls_sha256, "controls"),
        (value.package_reconstruction, value.package_reconstruction_sha256, "reconstruction"),
    ):
        if sha256_bytes(raw) != digest:
            raise IncompleteCampaign(f"G2c {label} hash disagrees")
        try:
            rows = [json.loads(line) for line in raw.splitlines()]
        except json.JSONDecodeError as error:
            raise IncompleteCampaign(f"G2c {label} is not JSONL: {error}") from error
        if canonical_jsonl_bytes(rows) != raw:
            raise IncompleteCampaign(f"G2c {label} is not canonical JSONL")
    if canonical_jsonl_bytes(value.records) != value.units:
        raise IncompleteCampaign("G2c unit bytes differ from retained records")
    if canonical_jsonl_bytes(value.controls_records) != value.controls:
        raise IncompleteCampaign("G2c control bytes differ from retained records")
    if (
        len(value.control_sources) != len(value.controls_records)
        or [row.get("kind_cell_id") for row in value.control_sources]
        != [row.get("kind_cell_id") for row in value.controls_records]
        or type(value.control_input_projections) is not dict
        or set(value.control_input_projections)
        != {row.get("kind_cell_id") for row in value.control_sources}
    ):
        raise IncompleteCampaign("G2c control-source census differs from retained controls")
    for source in value.control_sources:
        identity = source["kind_cell_id"]
        if canonical_json_bytes(
            value.control_input_projections[identity]
        ) != canonical_json_bytes(g2c_control_input_projection(source)):
            raise IncompleteCampaign(
                "G2c retained control source differs from its sealed input projection"
            )
