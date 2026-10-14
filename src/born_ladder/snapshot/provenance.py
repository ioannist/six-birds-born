"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
from typing import Any, Mapping
from born_ladder.snapshot.errors import IncompleteCampaign, SpecMismatch
from born_ladder.snapshot.frozen_spec import FrozenSpec

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


_PINNED_SOURCE_FIELDS = (
    "born_probe.py_sha256", "born_probe_extended.py_sha256", "contracts.py_sha256",
)


from dataclasses import dataclass

def measure_historical_sources(pins: Mapping[str, Any], sources: Mapping[str, Path]) -> dict[str, str]:
    """Measure supplied original evidence, with no working-source substitution."""
    missing = set(_PINNED_SOURCE_FIELDS) - set(sources)
    if missing:
        raise IncompleteCampaign(f"explicit historical source inputs missing: {sorted(missing)}")
    return {name: _measured_file(Path(sources[name]), pins[name], name)
            for name in _PINNED_SOURCE_FIELDS}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise IncompleteCampaign(f"cannot hash provenance input {path}: {error}") from error
    return digest.hexdigest()


def _measured_file(path: Path, expected: str, name: str) -> str:
    if not isinstance(expected, str) or not _HEX64.fullmatch(expected):
        raise IncompleteCampaign(f"expected {name} SHA-256 is malformed")
    measured = file_sha256(path.resolve())
    if measured != expected:
        raise SpecMismatch(f"measured {name} SHA-256 disagrees with expected identity")
    return measured


def _require_sha256(name: str, value: Any) -> None:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise IncompleteCampaign(f"provenance {name} must be a SHA-256 digest")


def validate_provenance(spec: FrozenSpec, provenance: Mapping[str, Any]) -> None:
    required = set(spec.get("/provenance/artifact_required_fields", expected_type=list))
    if set(provenance) != required:
        raise IncompleteCampaign(
            f"provenance field mismatch missing={sorted(required-set(provenance))} "
            f"unknown={sorted(set(provenance)-required)}"
        )
    for name in (
        "attested_json_sha256", "attested_markdown_sha256", "Cargo.lock_sha256",
        "python_environment_lock_sha256", "runner_source_sha256", "basis_sha256",
        "expected_matrix_sha256", "inventory_sha256",
    ):
        _require_sha256(name, provenance[name])
    for name in ("builder_path_sha256", "runner_binary_path_sha256"):
        value = provenance[name]
        if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
            raise IncompleteCampaign(f"{name} must have exact path and sha256")
        if not isinstance(value["path"], str) or not value["path"]:
            raise IncompleteCampaign(f"{name} path must be nonempty")
        _require_sha256(f"{name}.sha256", value["sha256"])
    if provenance["vendored_source_commit"] != provenance["freeze_payload_commit"]:
        raise SpecMismatch("vendored source commit is not the attested freeze payload commit")
    if not isinstance(provenance["campaign_argv"], list) or not all(isinstance(x, str) for x in provenance["campaign_argv"]):
        raise IncompleteCampaign("campaign_argv must be a string array")
    if not isinstance(provenance["cwd"], str) or not provenance["cwd"]:
        raise IncompleteCampaign("provenance cwd must be nonempty")
    if not isinstance(provenance["environment_allowlist"], dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in provenance["environment_allowlist"].items()
    ):
        raise IncompleteCampaign("environment_allowlist must map strings to strings")
    inputs = provenance["input_sha256s"]
    if not isinstance(inputs, dict) or not inputs or "implementation_manifest" not in inputs:
        raise IncompleteCampaign("input_sha256s must include the implementation manifest")
    for name, digest in inputs.items():
        _require_sha256(f"input_sha256s.{name}", digest)
    timestamps = provenance["utc_timestamps"]
    if not isinstance(timestamps, dict) or set(timestamps) != {"end", "start"} or not all(
        isinstance(value, str) and value.endswith("Z") for value in timestamps.values()
    ):
        raise IncompleteCampaign("UTC timestamps must have exact start/end Z strings")
    host = provenance["host_os_architecture"]
    if not isinstance(host, dict) or set(host) != {"architecture", "os"}:
        raise IncompleteCampaign("host_os_architecture must have exact architecture and os")
    for name in ("artifact_schema_version", "builder_version", "closure_kind", "schema_version", "spectral_algorithm_version"):
        if not isinstance(provenance[name], str) or not provenance[name]:
            raise IncompleteCampaign(f"provenance {name} must be nonempty")
    if not isinstance(provenance["lens_partition_packaging_ids"], dict):
        raise IncompleteCampaign("lens_partition_packaging_ids must be an object")
    if not isinstance(provenance["dirty_tree_paths"], list) or not all(isinstance(x, str) for x in provenance["dirty_tree_paths"]):
        raise IncompleteCampaign("dirty_tree_paths must be a string array")

# Production writers restored from the same historical implementation.

@dataclass(frozen=True)
class ProvenanceFiles:
    builder_path: Path
    builder_expected_sha256: str
    basis_path: Path
    basis_expected_sha256: str
    expected_matrix_path: Path
    expected_matrix_expected_sha256: str
    inventory_path: Path
    inventory_expected_sha256: str
    input_paths: Mapping[str, Path]
    input_expected_sha256s: Mapping[str, str]
