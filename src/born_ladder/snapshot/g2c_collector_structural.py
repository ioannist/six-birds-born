"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from born_ladder.snapshot.collector_structural import _pre_marker_stdout, _validate_raw_shape, strict_raw_json_loads
from born_ladder.snapshot.errors import IncompleteCampaign, SpecMismatch
from born_ladder.snapshot.frozen_spec import FrozenSpec

_POINTERS = {
    "g2c_collector_derivation": "/completeness/g2c_raw_stdout_derivation",
    "g2c_collector_structural_end": "/completeness/structural_end_record",
}


import copy
import json
import re
from born_ladder.snapshot.collector_structural import SCHEMA, _closed_pairs, _unit_from_raw
from born_ladder.snapshot.completeness import invocation_id_for
from born_ladder.snapshot.frozen_spec import canonical_json_bytes, sha256_bytes

@dataclass(frozen=True)
class G2CRawSegment:
    label: str

    born: tuple[dict[str, Any], ...]

    discovery: dict[str, Any] | None

    audit: dict[str, Any]

    suppressed_pairs: tuple[tuple[int, int, str], ...]

    complete_suppression: str | None

    explained_absent_required_families: tuple[str, ...] = ()



def _contract(
    spec: FrozenSpec, implementation_manifest_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    spec.audit_implementation_manifest(
        "g2c_collector_structural",
        manifest_path=implementation_manifest_path,
        declared_pointers=_POINTERS,
    )
    derivation = spec.get(_POINTERS["g2c_collector_derivation"], expected_type=dict)
    structural = spec.get(_POINTERS["g2c_collector_structural_end"], expected_type=dict)
    if derivation.get("overlay_keys") != ["g2c_v2"]:
        raise SpecMismatch("frozen G2c overlay census disagrees")
    if derivation.get("router") != {
        "EXP-112": "cores/exp112",
        "caller_override": False,
        "named": "cores/named",
        "named_experiments": [f"EXP-{number}" for number in range(102, 108)],
        "selector": "frozen invocation manifest experiment only",
        "stdout_override": False,
        "unknown": "G2C_V2_INCOMPLETE",
    }:
        raise SpecMismatch("frozen G2c source router disagrees")
    return derivation, structural


def _selected_core(
    derivation: Mapping[str, Any], invocation: Mapping[str, Any]
) -> tuple[str, Mapping[str, Any]]:
    experiment = invocation.get("experiment")
    router = derivation["router"]
    if experiment == "EXP-112":
        name = "exp112"
    elif experiment in router["named_experiments"]:
        name = "named"
    else:
        raise IncompleteCampaign("G2c manifest experiment selects no frozen core")
    core = derivation.get("cores", {}).get(name)
    if not isinstance(core, Mapping):
        raise SpecMismatch("frozen G2c selected core is absent")
    return name, core


def _roles(core: Mapping[str, Any], structural: Mapping[str, Any]) -> dict[bytes, str]:
    markers = core.get("raw_marker_order")
    if markers != [
        "KEY_BORN_PROBE_JSON ", "KEY_DISCOVERY_GRADE_JSON ", "KEY_AUDIT_JSON "
    ]:
        raise SpecMismatch("frozen G2c marker order disagrees")
    roles = {
        marker.encode("utf-8"): role
        for marker, role in zip(markers, ("born", "discovery", "audit"), strict=True)
    }
    allowed = structural["ordered_structural_manifest"]["properties"]["emitted_families"]["allowed"]
    if "KEY_SEQUENTIAL_PROBE_JSON" not in allowed:
        raise SpecMismatch("frozen G2c optional Sequential family is absent")
    roles[b"KEY_SEQUENTIAL_PROBE_JSON "] = "sequential"
    return roles


def _collapse_pairs(values: Sequence[tuple[int, int]], label: str) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for value in values:
        if not result or value != result[-1]:
            if value in result:
                raise IncompleteCampaign(f"G2c {label} pairs are reordered")
            result.append(value)
    return result


def _segment_census(
    agreement: Mapping[str, Any], born: Sequence[Mapping[str, Any]],
    discovery: Mapping[str, Any], audit: Mapping[str, Any],
) -> tuple[tuple[int, int, str], ...]:
    classification = agreement.get("suppressed_entry", {}).get("classification")
    if classification != "PINNED_RUNNER_MACRO_N_LT_2":
        raise SpecMismatch("frozen G2c partial-suppression classification disagrees")
    scan = audit.get("multi_scale_scan")
    if not isinstance(scan, list):
        raise IncompleteCampaign("G2c Audit scan census is invalid")
    audit_pairs = [(index, row.get("k")) for index, row in enumerate(scan)]
    born_pairs = [(row.get("step_index"), row.get("k")) for row in born]
    if (
        not born_pairs
        or len(born_pairs) != len(set(born_pairs))
        or [pair[0] for pair in born_pairs] != sorted(pair[0] for pair in born_pairs)
        or any(type(a) is not int or type(b) is not int for a, b in born_pairs)
    ):
        raise IncompleteCampaign("G2c Born index census is invalid")
    if any(index >= len(audit_pairs) or audit_pairs[index] != pair for index, pair in enumerate(born_pairs)):
        # Sparse retained indexes are permitted; compare each literal step index.
        if any(index < 0 or index >= len(audit_pairs) or audit_pairs[index] != (index, resolution)
               for index, resolution in born_pairs):
            raise IncompleteCampaign("G2c Audit/Born index pairing disagrees")
    contexts = _collapse_pairs(
        [(row["step_index"], row["k"]) for row in discovery.get("contexts", [])],
        "Discovery context",
    )
    rows = _collapse_pairs(
        [(row["step_index"], row["observation_payload"]["context_k"])
         for row in discovery.get("rows", [])],
        "Discovery row",
    )
    if contexts != born_pairs or rows != born_pairs:
        raise IncompleteCampaign("G2c Discovery projection differs from Born census")
    present = set(born_pairs)
    return tuple(
        (index, resolution, classification)
        for index, resolution in audit_pairs if (index, resolution) not in present
    )


def _identity(
    source: str, label: str, invocation: Mapping[str, Any],
    born: Sequence[Mapping[str, Any]], audit: Mapping[str, Any],
    derivation: Mapping[str, Any],
) -> None:
    experiment = invocation.get("experiment")
    if source == "exp112":
        expected_label = invocation.get("config_or_null")
    else:
        labels = derivation["overlays"]["g2c_v2"]["internal_labels_by_experiment"]
        if label not in labels.get(experiment, []):
            raise IncompleteCampaign("G2c named label is outside the frozen census")
        if invocation.get("config_or_null") is not None:
            raise IncompleteCampaign("G2c named invocation config is not null")
        expected_label = label
    if (
        not isinstance(label, str)
        or label != expected_label
        or audit.get("config_name") != label
        or audit.get("exp_id") != experiment
        or audit.get("seed") != invocation.get("seed")
        or audit.get("n") != invocation.get("scale")
        or any(
            row.get("cell") != label
            or row.get("seed") != invocation.get("seed")
            or row.get("scale") != invocation.get("scale")
            for row in born
        )
    ):
        raise IncompleteCampaign("G2c segment/raw/invocation identity disagrees")


def parse_g2c_raw_segments(
    spec: FrozenSpec, stdout: bytes, invocation: Mapping[str, Any], *,
    implementation_manifest_path: Path | None = None,
) -> tuple[G2CRawSegment, ...]:
    """Parse one invocation solely through its manifest-selected G2c core."""
    derivation, structural = _contract(spec, implementation_manifest_path)
    source, core = _selected_core(derivation, invocation)
    roles = _roles(core, structural)
    descriptors = core["raw_marker_descriptors"]
    born: list[dict[str, Any]] = []
    discovery: dict[str, Any] | None = None
    sequential = 0
    previous: str | None = None
    segments: list[G2CRawSegment] = []
    for line in _pre_marker_stdout(stdout).splitlines():
        match = next(((marker, role) for marker, role in roles.items() if line.startswith(marker)), None)
        if match is None:
            continue
        marker, role = match
        value = strict_raw_json_loads(line[len(marker):])
        if not isinstance(value, dict):
            raise IncompleteCampaign(f"G2c {role} payload is not an object")
        descriptor = descriptors.get(marker.decode("utf-8"))
        if descriptor is not None:
            _validate_raw_shape(value, descriptor["shape"], f"/{marker.decode().rstrip()}")
        if role == "born":
            if discovery is not None:
                raise IncompleteCampaign("G2c Born follows Discovery")
            born.append(value)
        elif role == "sequential":
            if not born or discovery is not None or previous != "born":
                raise IncompleteCampaign("G2c Sequential is not immediately after Born")
            sequential += 1
        elif role == "discovery":
            if not born or discovery is not None:
                raise IncompleteCampaign("G2c segment lacks one Born block before Discovery")
            discovery = value
        else:
            label = value.get("config_name")
            _identity(source, label, invocation, born, value, derivation)
            if born or discovery is not None:
                if not born or discovery is None:
                    raise IncompleteCampaign("G2c segment has only one of Born and Discovery")
                suppressed = _segment_census(
                    derivation["segment_census_agreement"], born, discovery, value
                )
                complete, explained = None, ()
            else:
                if sequential or not value.get("multi_scale_scan"):
                    raise IncompleteCampaign("G2c Audit-only segment census is invalid")
                complete = derivation["complete_suppression"]["classification"]
                suppressed = ()
                explained = tuple(derivation["complete_suppression"]["required_explained_exclusions"])
            segments.append(G2CRawSegment(
                label, tuple(born), discovery, value, suppressed, complete, explained
            ))
            born, discovery, sequential, previous = [], None, 0, None
            continue
        previous = role
    if born or discovery is not None or sequential or not segments:
        raise IncompleteCampaign("G2c stdout ends with incomplete governed material")
    if source == "exp112":
        if len(segments) != 1 or segments[0].label != invocation["config_or_null"]:
            raise IncompleteCampaign("G2c EXP-112 segment census disagrees")
    else:
        expected = derivation["overlays"]["g2c_v2"]["internal_labels_by_experiment"][invocation["experiment"]]
        if [segment.label for segment in segments] != expected:
            raise IncompleteCampaign("G2c named segment order/census disagrees")
    return tuple(segments)

# Production writers restored from the same historical implementation.

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

@dataclass(frozen=True)
class G2CCollectorCapture:
    records: tuple[dict[str, Any], ...]
    origins: tuple[tuple[Path, str], ...]

def segment_census_record(
    spec: FrozenSpec, stdout: bytes, invocation: Mapping[str, Any], *,
    implementation_manifest_path: Path | None = None,
) -> dict[str, Any]:
    segments = parse_g2c_raw_segments(
        spec, stdout, invocation, implementation_manifest_path=implementation_manifest_path
    )
    return {
        "invocation_id": invocation["invocation_id"],
        "segments": [{
            "born_pairs": [[row["step_index"], row["k"]] for row in segment.born],
            "complete_suppression": None if segment.complete_suppression is None else {
                "classification": segment.complete_suppression,
                "explained_absent_required_families": list(segment.explained_absent_required_families),
            },
            "internal_label": segment.label,
            "suppressed_pairs": [
                {"classification": classification, "pair": [step, resolution]}
                for step, resolution, classification in segment.suppressed_pairs
            ],
        } for segment in segments],
    }

def reconstruct_g2c_collector_record(
    spec: FrozenSpec, stdout: bytes, invocation: Mapping[str, Any], *,
    implementation_manifest_path: Path | None = None,
) -> dict[str, Any]:
    derivation, structural = _contract(spec, implementation_manifest_path)
    source, core = _selected_core(derivation, invocation)
    segments = parse_g2c_raw_segments(
        spec, stdout, invocation, implementation_manifest_path=implementation_manifest_path
    )
    units: list[dict[str, Any]] = []
    for segment in segments:
        if segment.complete_suppression is not None:
            continue
        if segment.discovery is None:
            raise IncompleteCampaign("G2c scientific segment lacks Discovery evidence")
        shadow = dict(invocation)
        if source == "named":
            shadow["config_or_null"] = segment.label
        units.extend(_unit_from_raw(row, segment.discovery, segment.audit, shadow) for row in segment.born)
    emitted: list[str] = []
    counts = {
        "audit_records": 0, "born_probe_records": 0, "discovery_contexts": 0,
        "discovery_grade_records": 0, "discovery_rows": 0,
        "sequential_probe_records": 0, "units": len(units),
    }
    for line in _pre_marker_stdout(stdout).splitlines():
        match = next(((marker, role) for marker, role in _roles(core, structural).items()
                      if line.startswith(marker)), None)
        if match is None:
            continue
        marker, role = match
        family = marker.decode().rstrip()
        if family not in emitted:
            emitted.append(family)
        value = strict_raw_json_loads(line[len(marker):])
        if role == "born": counts["born_probe_records"] += 1
        elif role == "sequential": counts["sequential_probe_records"] += 1
        elif role == "audit": counts["audit_records"] += 1
        else:
            counts["discovery_grade_records"] += 1
            counts["discovery_contexts"] += len(value["contexts"])
            counts["discovery_rows"] += len(value["rows"])
    expected_id = invocation_id_for(
        spec, experiment=invocation["experiment"],
        config_or_null=invocation["config_or_null"],
        seed=invocation["seed"], scale=invocation["scale"],
    )
    if invocation.get("invocation_id") != expected_id:
        raise IncompleteCampaign("G2c invocation ID disagrees")
    manifest = {
        "emitted_families": emitted, "engine_declared_counts": counts,
        "invocation_id": expected_id,
        # The invocation contract uses the semantic names Born/Discovery/Audit;
        # the shared structural-end shape freezes the corresponding marker names.
        "required_families": list(
            structural["ordered_structural_manifest"]["properties"]
            ["required_families"]["exact"]
        ),
        "units": units,
    }
    from born_ladder.snapshot.runner_structural import _validate_shape
    _validate_shape(manifest, structural["ordered_structural_manifest"], "/ordered_structural_manifest")
    return manifest

def build_g2c_collector_capture(
    spec: FrozenSpec, stdout_paths: Sequence[Path],
    invocation_records: Sequence[Mapping[str, Any]], *,
    implementation_manifest_path: Path | None = None,
) -> bytes:
    paths = [Path(path).resolve() for path in stdout_paths]
    if not paths or len(paths) != len(set(paths)) or len(paths) != len(invocation_records):
        raise IncompleteCampaign("G2c collector stdout/invocation census disagrees")
    entries = []
    for path, invocation in zip(paths, invocation_records, strict=True):
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise IncompleteCampaign(f"G2c collector stdout is unavailable: {error}") from error
        entries.append({
            "invocation_id": invocation["invocation_id"],
            "record": reconstruct_g2c_collector_record(
                spec, raw, invocation, implementation_manifest_path=implementation_manifest_path
            ),
            "stdout_path": str(path), "stdout_sha256": sha256_bytes(raw),
        })
    return canonical_json_bytes({"entries": entries, "schema": SCHEMA})

def parse_g2c_collector_capture_bundle(
    spec: FrozenSpec, raw: bytes, invocation_records: Sequence[Mapping[str, Any]], *,
    implementation_manifest_path: Path | None = None,
) -> G2CCollectorCapture:
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_closed_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IncompleteCampaign(f"G2c collector capture is invalid: {error}") from error
    if not isinstance(payload, dict) or set(payload) != {"entries", "schema"} or payload["schema"] != SCHEMA:
        raise IncompleteCampaign("G2c collector capture has a non-closed schema")
    if canonical_json_bytes(payload) != raw:
        raise IncompleteCampaign("G2c collector capture is not canonical")
    expected = {row["invocation_id"]: row for row in invocation_records}
    if len(expected) != len(invocation_records) or len(payload["entries"]) != len(expected):
        raise IncompleteCampaign("G2c collector capture census disagrees")
    records, origins, seen = [], [], set()
    for entry in payload["entries"]:
        if not isinstance(entry, dict) or set(entry) != {"invocation_id", "record", "stdout_path", "stdout_sha256"}:
            raise IncompleteCampaign("G2c collector capture entry schema disagrees")
        identity = entry["invocation_id"]
        path = Path(entry["stdout_path"])
        digest = entry["stdout_sha256"]
        if identity in seen or identity not in expected or not path.is_absolute() or not _HEX64.fullmatch(digest):
            raise IncompleteCampaign("G2c collector origin identity is invalid")
        seen.add(identity)
        try:
            current = path.read_bytes()
        except OSError as error:
            raise IncompleteCampaign(f"G2c collector origin is unavailable: {error}") from error
        if sha256_bytes(current) != digest:
            raise IncompleteCampaign("G2c collector origin hash disagrees")
        reconstructed = reconstruct_g2c_collector_record(
            spec, current, expected[identity], implementation_manifest_path=implementation_manifest_path
        )
        if reconstructed != entry["record"]:
            raise IncompleteCampaign("G2c collector capture differs from sealed reconstruction")
        records.append(reconstructed)
        origins.append((path.resolve(), digest))
    return G2CCollectorCapture(tuple(records), tuple(origins))

def require_g2c_structural_channel_equality(
    runner_records: Sequence[Mapping[str, Any]],
    collector_records: Sequence[Mapping[str, Any]],
    invocation_records: Sequence[Mapping[str, Any]],
) -> None:
    if list(runner_records) != list(collector_records):
        raise IncompleteCampaign("G2c runner and collector structural channels disagree")
    expected = [row["invocation_id"] for row in invocation_records]
    actual = [row.get("invocation_id") for row in runner_records]
    if actual != expected or len(actual) != len(set(actual)):
        raise IncompleteCampaign("G2c structural order differs from invocation manifest")

def parse_g2c_collector_capture(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return [copy.deepcopy(row) for row in parse_g2c_collector_capture_bundle(*args, **kwargs).records]
