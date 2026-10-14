"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import copy
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from born_ladder.snapshot.errors import IncompleteCampaign
from born_ladder.snapshot.frozen_spec import FrozenSpec, canonical_json_bytes, sha256_bytes

SCHEMA = "RB1_RUNNER_STRUCTURAL_CAPTURE_V3"


STDOUT_PREFIX = b"RB1_STRUCTURAL_END_JSON:"


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


_IMPLEMENTATION_POINTERS = {
    "runner_structural_end_record": "/completeness/structural_end_record"
}


from typing import Sequence

@dataclass(frozen=True)
class ParsedStructuralEnd:
    manifest: dict[str, Any]

    manifest_sha256: str

    pre_marker_stdout: bytes

    record: dict[str, Any]



@dataclass(frozen=True)
class RunnerCapture:
    records: tuple[dict[str, Any], ...]

    origins: tuple[tuple[Path, str], ...]

    carried_hashes: tuple[str, ...]



def _closed_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IncompleteCampaign(f"runner structural JSON repeats key {key!r}")
        result[key] = value
    return result


def _finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ValueError(f"runner structural numeric conversion is nonfinite: {token}")
    return value


def _reject_constant(token: str) -> None:
    raise ValueError(f"runner structural nonfinite token: {token}")


def _leaf(value: Any, descriptor: Mapping[str, Any], path: str) -> None:
    leaf = descriptor["leaf_type"]
    if leaf == "nonnegative JSON integer":
        valid = type(value) is int and value >= 0
    elif leaf == "nonempty UTF-8 string":
        valid = isinstance(value, str) and bool(value)
    elif leaf == "UTF-8 string":
        valid = isinstance(value, str)
    elif leaf == "exactly 64 lowercase hexadecimal characters":
        valid = isinstance(value, str) and bool(_HEX64.fullmatch(value))
    elif leaf.startswith("exact string "):
        valid = value == leaf.removeprefix("exact string ")
    else:
        raise IncompleteCampaign(f"unsupported runner structural leaf at {path}: {leaf}")
    if not valid:
        raise IncompleteCampaign(f"runner structural value disagrees at {path}")


def _validate_shape(value: Any, descriptor: Mapping[str, Any], path: str) -> None:
    kind = descriptor.get("kind")
    if kind is None:
        _leaf(value, descriptor, path)
        return
    if kind == "scalar":
        _leaf(value, descriptor, path)
        if "canonical decimal" in descriptor.get("constraint", ""):
            if not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]*", value):
                raise IncompleteCampaign(f"runner structural step_id is not canonical decimal at {path}")
        return
    if kind == "closed_object":
        if not isinstance(value, dict) or sorted(value) != descriptor["keys"]:
            raise IncompleteCampaign(f"runner structural object keys disagree at {path}")
        for key in descriptor["keys"]:
            _validate_shape(value[key], descriptor["properties"][key], f"{path}/{key}")
        return
    if kind == "array":
        if not isinstance(value, list):
            raise IncompleteCampaign(f"runner structural array expected at {path}")
        for index, item in enumerate(value):
            _validate_shape(item, descriptor["items"], f"{path}/{index}")
        if "unique" in descriptor.get("ordering", ""):
            identities = [canonical_json_bytes(item) for item in value]
            if len(identities) != len(set(identities)):
                raise IncompleteCampaign(f"runner structural array repeats values at {path}")
        if descriptor.get("exact") is not None and value != descriptor["exact"]:
            raise IncompleteCampaign(f"runner structural exact array disagrees at {path}")
        if descriptor.get("allowed") is not None and any(
            item not in descriptor["allowed"] for item in value
        ):
            raise IncompleteCampaign(f"runner structural array has an unknown value at {path}")
        return
    if kind == "applicability_closed_map":
        allowed = descriptor["key_set"]
        if not isinstance(value, dict) or not value or any(key not in allowed for key in value):
            raise IncompleteCampaign(f"runner structural applicability map disagrees at {path}")
        for key, item in value.items():
            _validate_shape(item, descriptor["value"], f"{path}/{key}")
        return
    raise IncompleteCampaign(f"unsupported runner structural descriptor at {path}: {kind}")


def parse_runner_stdout(
    spec: FrozenSpec, raw: bytes, *, implementation_manifest_path: Path | None = None
) -> ParsedStructuralEnd:
    """Parse the sole final v8 record and verify its manifest-only digest."""
    spec.audit_implementation_manifest(
        "runner_structural", manifest_path=implementation_manifest_path,
        declared_pointers=_IMPLEMENTATION_POINTERS,
    )
    contract = spec.get("/completeness/structural_end_record", expected_type=dict)
    marker = contract["final_line"]["marker"].encode("ascii")
    if marker != STDOUT_PREFIX or not raw.endswith(b"\n"):
        raise IncompleteCampaign("runner stdout lacks the frozen final LF structural record")
    lines = raw.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if line.startswith(marker)]
    if matches != [len(lines) - 1]:
        raise IncompleteCampaign("runner stdout does not contain exactly one final structural record")
    payload_bytes = lines[-1][len(marker):-1]
    if not payload_bytes or b"\n" in payload_bytes or b"\r" in payload_bytes:
        raise IncompleteCampaign("runner structural end record is not one LF-terminated line")
    try:
        record = json.loads(
            payload_bytes.decode("utf-8", errors="strict"),
            object_pairs_hook=_closed_pairs,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise IncompleteCampaign(f"runner structural end-record parse failure: {error}") from error
    if not isinstance(record, dict) or canonical_json_bytes(record)[:-1] != payload_bytes:
        raise IncompleteCampaign("runner structural end record is not canonical JSON")
    if sorted(record) != contract["wrapper"]["keys"]:
        raise IncompleteCampaign("runner structural wrapper keys disagree")
    if record["schema"] != contract["schema"]:
        raise IncompleteCampaign("runner structural schema disagrees")
    manifest = record["ordered_structural_manifest"]
    _validate_shape(manifest, contract["ordered_structural_manifest"], "/ordered_structural_manifest")
    digest = sha256_bytes(canonical_json_bytes(manifest)[:-1])
    if record["structural_manifest_sha256"] != digest:
        raise IncompleteCampaign("runner structural manifest-only SHA-256 disagrees")
    return ParsedStructuralEnd(
        manifest=copy.deepcopy(manifest), manifest_sha256=digest,
        pre_marker_stdout=b"".join(lines[:-1]), record=copy.deepcopy(record),
    )


def parse_runner_capture_bundle(
    spec: FrozenSpec, raw: bytes, *, implementation_manifest_path: Path | None = None,
) -> RunnerCapture:
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_closed_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IncompleteCampaign(f"runner structural capture parse failure: {error}") from error
    if not isinstance(payload, dict) or set(payload) != {"entries", "schema"}:
        raise IncompleteCampaign("runner structural capture has a non-closed schema")
    if canonical_json_bytes(payload) != raw or payload["schema"] != SCHEMA:
        raise IncompleteCampaign("runner structural capture is not canonical frozen-schema JSON")
    if not isinstance(payload["entries"], list) or not payload["entries"]:
        raise IncompleteCampaign("runner structural capture entries are empty")
    records: list[dict[str, Any]] = []
    origins: list[tuple[Path, str]] = []
    carried: list[str] = []
    for entry in payload["entries"]:
        if not isinstance(entry, dict) or set(entry) != {"record", "stdout_path", "stdout_sha256"}:
            raise IncompleteCampaign("runner structural capture entry has a non-closed schema")
        path = Path(entry["stdout_path"])
        if not path.is_absolute() or not isinstance(entry["stdout_sha256"], str) or not _HEX64.fullmatch(entry["stdout_sha256"]):
            raise IncompleteCampaign("runner structural capture origin identity is invalid")
        try:
            current = path.read_bytes()
        except OSError as error:
            raise IncompleteCampaign(f"runner stdout origin unavailable: {error}") from error
        if sha256_bytes(current) != entry["stdout_sha256"]:
            raise IncompleteCampaign("runner stdout origin hash disagrees")
        parsed = parse_runner_stdout(
            spec, current, implementation_manifest_path=implementation_manifest_path
        )
        if parsed.record != entry["record"]:
            raise IncompleteCampaign("runner capture record disagrees with captured stdout")
        records.append(parsed.manifest)
        origins.append((path.resolve(), entry["stdout_sha256"]))
        carried.append(parsed.manifest_sha256)
    if len(origins) != len({path for path, _ in origins}):
        raise IncompleteCampaign("runner structural capture reuses a stdout origin")
    return RunnerCapture(tuple(records), tuple(origins), tuple(carried))

# Production writers restored from the same historical implementation.

def build_runner_capture(
    spec: FrozenSpec, stdout_paths: Sequence[Path], *,
    implementation_manifest_path: Path | None = None,
) -> bytes:
    paths = [Path(path).resolve() for path in stdout_paths]
    if not paths or len(paths) != len(set(paths)):
        raise IncompleteCampaign("runner structural stdout origins are empty or duplicated")
    entries: list[dict[str, Any]] = []
    for path in paths:
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise IncompleteCampaign(f"runner stdout origin unavailable: {error}") from error
        parsed = parse_runner_stdout(
            spec, raw, implementation_manifest_path=implementation_manifest_path
        )
        entries.append({
            "record": parsed.record, "stdout_path": str(path),
            "stdout_sha256": sha256_bytes(raw),
        })
    return canonical_json_bytes({"entries": entries, "schema": SCHEMA})

def parse_runner_capture(
    spec: FrozenSpec, raw: bytes, *, implementation_manifest_path: Path | None = None,
) -> list[dict[str, Any]]:
    return [copy.deepcopy(record) for record in parse_runner_capture_bundle(
        spec, raw, implementation_manifest_path=implementation_manifest_path
    ).records]
