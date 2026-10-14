"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from born_ladder.snapshot.errors import IncompleteCampaign
from born_ladder.snapshot.frozen_spec import FrozenSpec, canonical_json_bytes, sha256_bytes

SCHEMA = "RB1_COLLECTOR_STRUCTURAL_CAPTURE_V3"


_STRUCTURAL_MARKER = b"RB1_STRUCTURAL_END_JSON:"


_MARKERS = {
    b"KEY_BORN_PROBE_JSON ": "KEY_BORN_PROBE_JSON",
    b"KEY_SEQUENTIAL_PROBE_JSON ": "KEY_SEQUENTIAL_PROBE_JSON",
    b"KEY_DISCOVERY_GRADE_JSON ": "KEY_DISCOVERY_GRADE_JSON",
    b"KEY_AUDIT_JSON ": "KEY_AUDIT_JSON",
}


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


_IMPLEMENTATION_POINTERS = {
    "collector_derivation_registry": "/completeness/g2a_raw_stdout_derivation",
    "collector_structural_end_record": "/completeness/structural_end_record",
}


import copy

@dataclass(frozen=True)
class CollectorCapture:
    records: tuple[dict[str, Any], ...]

    origins: tuple[tuple[Path, str], ...]



def _closed_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IncompleteCampaign(f"collector raw JSON repeats key {key!r}")
        result[key] = value
    return result


def _finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ValueError(f"collector raw JSON numeric conversion is nonfinite: {token}")
    return value


def _reject_constant(token: str) -> None:
    raise ValueError(f"collector raw JSON nonfinite token: {token}")


def strict_raw_json_loads(raw: bytes) -> Any:
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"), object_pairs_hook=_closed_pairs,
            parse_constant=_reject_constant, parse_float=_finite_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise IncompleteCampaign(f"collector raw marker is not strict finite JSON: {error}") from error


def _validate_raw_shape(value: Any, shape: Mapping[str, Any], path: str) -> None:
    kind = shape["kind"]
    if kind == "opaque_strict_json_subtree":
        return
    if kind == "scalar":
        leaf = shape["leaf_type"]
        if leaf == "UTF-8 string":
            valid = isinstance(value, str)
        elif leaf == "JSON integer":
            valid = type(value) is int
        elif leaf == "finite JSON number":
            valid = type(value) in (int, float) and math.isfinite(float(value))
        else:
            raise IncompleteCampaign(f"collector raw descriptor leaf is unsupported at {path}")
        if not valid or shape.get("constraint") == ">=0" and value < 0:
            raise IncompleteCampaign(f"collector raw marker value disagrees at {path}")
        return
    if kind == "array":
        if not isinstance(value, list):
            raise IncompleteCampaign(f"collector raw marker array expected at {path}")
        for index, item in enumerate(value):
            _validate_raw_shape(item, shape["items"], f"{path}/{index}")
        return
    if kind == "closed_raw_object":
        if not isinstance(value, dict) or set(value) != set(shape["keys"]):
            raise IncompleteCampaign(f"collector raw marker keys disagree at {path}")
        for key in shape["keys"]:
            _validate_raw_shape(value[key], shape["properties"][key], f"{path}/{key}")
        return
    if kind == "closed_raw_object_variants":
        variants = [
            candidate for candidate in shape["variants"]
            if isinstance(value, dict) and set(value) == set(candidate["keys"])
        ]
        if len(variants) != 1:
            raise IncompleteCampaign(f"collector raw marker selects no unique variant at {path}")
        _validate_raw_shape(value, variants[0], path)
        return
    raise IncompleteCampaign(f"collector raw descriptor kind is unsupported at {path}")


def _identity(value: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(dict(value)))


def _pre_marker_stdout(raw: bytes) -> bytes:
    if not raw.endswith(b"\n"):
        raise IncompleteCampaign("collector stdout lacks a final LF")
    lines = raw.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if line.startswith(_STRUCTURAL_MARKER)]
    if matches != [len(lines) - 1]:
        raise IncompleteCampaign("collector input lacks exactly one final structural marker")
    return b"".join(lines[:-1])


def _unit_from_raw(
    born: Mapping[str, Any], discovery: Mapping[str, Any], audit: Mapping[str, Any],
    invocation: Mapping[str, Any],
) -> dict[str, Any]:
    step = born["step_index"]
    resolution = born["k"]
    contexts = [
        item for item in discovery["contexts"]
        if item["step_index"] == step and item["k"] == resolution
    ]
    if not contexts:
        raise IncompleteCampaign("collector cannot join Born and Discovery context")
    identity_fields = {
        (item["level_id"], item["protocol_step_id"], item["resolution_id"])
        for item in contexts
    }
    if len(identity_fields) != 1:
        raise IncompleteCampaign("collector Discovery context identities disagree across kinds")
    level_id, protocol_step_id, resolution_id = next(iter(identity_fields))
    if protocol_step_id != f"protocol_pica_multiscale_scan_step_{step}" or resolution_id != f"resolution_k_{resolution}":
        raise IncompleteCampaign("collector Discovery context identity is not frozen canonical form")
    rows = [
        item for item in discovery["rows"]
        if item["step_index"] == step
        and item["protocol_step_id"] == protocol_step_id
        and item["resolution_id"] == resolution_id
        and item["observation_payload"]["context_k"] == resolution
    ]
    if not rows:
        raise IncompleteCampaign("collector Discovery unit has no joined rows")
    trajectory_count = discovery["trajectory_count"]
    trajectory_ids = list(dict.fromkeys(item["trajectory_id"] for item in rows))
    expected_trajectories = [f"traj_{index:04d}" for index in range(trajectory_count)]
    if trajectory_ids != expected_trajectories:
        raise IncompleteCampaign("collector Discovery trajectory order/census disagrees")
    if any(
        born[name] != invocation[name if name != "cell" else "config_or_null"]
        for name in ("cell", "seed", "scale")
    ):
        raise IncompleteCampaign("collector Born identity disagrees with invocation manifest")
    if (
        audit["config_name"] != born["cell"] or audit["seed"] != born["seed"]
        or audit["n"] != born["scale"] or audit["exp_id"] != invocation["experiment"]
    ):
        raise IncompleteCampaign("collector Audit identity disagrees with Born/invocation")
    partition = born["partition"]
    packaging = born["packaging"]
    if len(partition) != born["scale"] or len(packaging) != born["scale"]:
        raise IncompleteCampaign("collector mapping arrays disagree with state census")
    raw_count = max(partition) + 1
    pkg_count = max(packaging) + 1
    kinds = ["raw"] + (["pkg"] if pkg_count >= 2 else [])
    expected_labels = {
        "raw": [f"group_{index}" for index in range(raw_count)],
        **({"pkg": [f"package_{index}" for index in range(pkg_count)]} if "pkg" in kinds else {}),
    }
    observed_labels = {
        kind: list(dict.fromkeys(
            item["observation_label"] for item in rows
            if ("packaging_source" in item["observation_payload"]) == (kind == "pkg")
        ))
        for kind in kinds
    }
    if any(
        not set(observed_labels[kind]) <= set(expected_labels[kind])
        for kind in kinds
    ):
        raise IncompleteCampaign("collector observed outcome labels disagree with mappings")
    context_id = _identity({
        "config_id": born["cell"], "experiment": invocation["experiment"],
        "level_id": level_id, "protocol_step_id": protocol_step_id,
        "resolution_id": resolution_id,
    })
    return {
        "config_id": born["cell"],
        "kind_availability": kinds,
        "mapping_dimensions_by_kind": {
            "raw": {"columns": born["scale"], "rows": raw_count},
            **({"pkg": {"columns": born["scale"], "rows": pkg_count}} if "pkg" in kinds else {}),
        },
        "ordered_outcome_labels_by_kind": expected_labels,
        "ordered_state_labels": [f"state_{index}" for index in range(born["scale"])],
        "partition_id": _identity({"partition": partition}),
        "resolution": resolution,
        "runner_context_id": context_id,
        "schema_versions": {
            "audit": str(audit["schema_version"]),
            "born_probe": "UNVERSIONED_PRE_V8",
            "discovery_grade": "UNVERSIONED_PRE_V8",
        },
        "source_identifier": audit["exp_id"],
        "step_id": str(step),
        "trajectory_slots": expected_trajectories,
    }


def reconstruct_collector_record(
    spec: FrozenSpec, stdout: bytes, invocation: Mapping[str, Any], *,
    implementation_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Reconstruct without reading any runner structural payload field."""
    spec.audit_implementation_manifest(
        "collector_structural", manifest_path=implementation_manifest_path,
        declared_pointers=_IMPLEMENTATION_POINTERS,
    )
    derivation = spec.get("/completeness/g2a_raw_stdout_derivation", expected_type=dict)
    descriptors = derivation["raw_marker_descriptors"]
    pre_marker = _pre_marker_stdout(stdout)
    emitted: list[str] = []
    counts = {
        "audit_records": 0, "born_probe_records": 0,
        "discovery_contexts": 0, "discovery_grade_records": 0,
        "discovery_rows": 0, "sequential_probe_records": 0, "units": 0,
    }
    born_block: list[dict[str, Any]] = []
    discovery: dict[str, Any] | None = None
    units: list[dict[str, Any]] = []
    for line in pre_marker.splitlines():
        match = next(((marker, family) for marker, family in _MARKERS.items() if line.startswith(marker)), None)
        if match is None:
            continue
        marker, family = match
        if family not in emitted:
            emitted.append(family)
        value = strict_raw_json_loads(line[len(marker):])
        if not isinstance(value, dict):
            raise IncompleteCampaign(f"collector {family} payload is not an object")
        descriptor = descriptors.get(marker.decode("ascii"))
        if descriptor is not None:
            _validate_raw_shape(value, descriptor["shape"], f"/{family}")
        if family == "KEY_BORN_PROBE_JSON":
            if discovery is not None:
                raise IncompleteCampaign("collector encountered Born after Discovery before Audit")
            born_block.append(value)
            counts["born_probe_records"] += 1
        elif family == "KEY_SEQUENTIAL_PROBE_JSON":
            counts["sequential_probe_records"] += 1
        elif family == "KEY_DISCOVERY_GRADE_JSON":
            if not born_block or discovery is not None:
                raise IncompleteCampaign("collector config segment lacks one Born block then Discovery")
            discovery = value
            counts["discovery_grade_records"] += 1
            counts["discovery_contexts"] += len(value["contexts"])
            counts["discovery_rows"] += len(value["rows"])
        elif family == "KEY_AUDIT_JSON":
            counts["audit_records"] += 1
            if discovery is None or not born_block:
                raise IncompleteCampaign("collector config segment lacks Born/Discovery before Audit")
            born_pairs = [(item["step_index"], item["k"]) for item in born_block]
            if len(born_pairs) != len(set(born_pairs)) or born_pairs != sorted(born_pairs):
                raise IncompleteCampaign("collector Born step/k census is duplicated or unordered")
            if [item["k"] for item in value["multi_scale_scan"]] != [item["k"] for item in born_block]:
                raise IncompleteCampaign("collector Audit k census disagrees with Born block")
            units.extend(_unit_from_raw(item, discovery, value, invocation) for item in born_block)
            born_block = []
            discovery = None
    if born_block or discovery is not None or not units:
        raise IncompleteCampaign("collector stdout ends with an incomplete or empty config segment")
    counts["units"] = len(units)
    expected_invocation_id = _identity({
        "config_or_null": invocation["config_or_null"],
        "experiment": invocation["experiment"], "scale": invocation["scale"],
        "seed": invocation["seed"],
    })
    if invocation["invocation_id"] != expected_invocation_id:
        raise IncompleteCampaign("collector frozen invocation ID disagrees")
    manifest = {
        "emitted_families": emitted, "engine_declared_counts": counts,
        "invocation_id": expected_invocation_id,
        "required_families": list(invocation["required_emission_families"]),
        "units": units,
    }
    structural = spec.get("/completeness/structural_end_record", expected_type=dict)
    from born_ladder.snapshot.runner_structural import _validate_shape
    _validate_shape(manifest, structural["ordered_structural_manifest"], "/ordered_structural_manifest")
    return manifest


def parse_collector_capture_bundle(
    spec: FrozenSpec, raw: bytes, invocation_records: Sequence[Mapping[str, Any]], *,
    implementation_manifest_path: Path | None = None,
) -> CollectorCapture:
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_closed_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IncompleteCampaign(f"collector structural capture parse failure: {error}") from error
    if not isinstance(payload, dict) or set(payload) != {"entries", "schema"}:
        raise IncompleteCampaign("collector structural capture has a non-closed schema")
    if canonical_json_bytes(payload) != raw or payload["schema"] != SCHEMA:
        raise IncompleteCampaign("collector structural capture is not canonical frozen-schema JSON")
    expected = {item["invocation_id"]: item for item in invocation_records}
    if len(expected) != len(invocation_records) or len(payload["entries"]) != len(expected):
        raise IncompleteCampaign("collector structural capture invocation census disagrees")
    records: list[dict[str, Any]] = []
    origins: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for entry in payload["entries"]:
        if not isinstance(entry, dict) or set(entry) != {"invocation_id", "record", "stdout_path", "stdout_sha256"}:
            raise IncompleteCampaign("collector structural capture entry has a non-closed schema")
        invocation_id = entry["invocation_id"]
        if invocation_id in seen or invocation_id not in expected:
            raise IncompleteCampaign("collector structural capture has duplicate/unknown invocation ID")
        seen.add(invocation_id)
        path = Path(entry["stdout_path"])
        if not path.is_absolute() or not isinstance(entry["stdout_sha256"], str) or not _HEX64.fullmatch(entry["stdout_sha256"]):
            raise IncompleteCampaign("collector structural origin identity is invalid")
        try:
            current = path.read_bytes()
        except OSError as error:
            raise IncompleteCampaign(f"collector stdout origin unavailable: {error}") from error
        if sha256_bytes(current) != entry["stdout_sha256"]:
            raise IncompleteCampaign("collector stdout origin hash disagrees")
        reconstructed = reconstruct_collector_record(
            spec, current, expected[invocation_id],
            implementation_manifest_path=implementation_manifest_path,
        )
        if reconstructed != entry["record"]:
            raise IncompleteCampaign("collector capture disagrees with independent stdout reconstruction")
        records.append(reconstructed)
        origins.append((path.resolve(), entry["stdout_sha256"]))
    return CollectorCapture(tuple(records), tuple(origins))

# Production writers restored from the same historical implementation.

def build_collector_capture(
    spec: FrozenSpec, stdout_paths: Sequence[Path], invocation_records: Sequence[Mapping[str, Any]], *,
    implementation_manifest_path: Path | None = None,
) -> bytes:
    paths = [Path(path).resolve() for path in stdout_paths]
    if not paths or len(paths) != len(set(paths)) or len(paths) != len(invocation_records):
        raise IncompleteCampaign("collector stdout origins/invocation census are empty, duplicated, or unequal")
    entries: list[dict[str, Any]] = []
    for path, invocation in zip(paths, invocation_records, strict=True):
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise IncompleteCampaign(f"collector stdout origin unavailable: {error}") from error
        entries.append({
            "invocation_id": invocation["invocation_id"],
            "record": reconstruct_collector_record(
                spec, raw, invocation, implementation_manifest_path=implementation_manifest_path
            ),
            "stdout_path": str(path), "stdout_sha256": sha256_bytes(raw),
        })
    return canonical_json_bytes({"entries": entries, "schema": SCHEMA})

def parse_collector_capture(
    spec: FrozenSpec, raw: bytes, invocation_records: Sequence[Mapping[str, Any]], *,
    implementation_manifest_path: Path | None = None,
) -> list[dict[str, Any]]:
    return [copy.deepcopy(record) for record in parse_collector_capture_bundle(
        spec, raw, invocation_records,
        implementation_manifest_path=implementation_manifest_path,
    ).records]
