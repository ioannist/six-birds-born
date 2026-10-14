"""Frozen v8 G2a campaign orchestrator; execution is manager-dispatched separately."""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from born_ladder.snapshot.artifact_paths import authorized_output_path, reject_symlink_chain
from born_ladder.snapshot.collector_structural import build_collector_capture
from born_ladder.snapshot.completeness import AttemptRegistry, build_attempt_record, build_invocation_manifest, invocation_manifest_bytes, structural_manifest_bytes
from born_ladder.snapshot.errors import (
    BlockedInfrastructure,
    IncompleteCampaign,
    Rebuild1Error,
    SpecMismatch,
)
from born_ladder.reproduction.specification import PublicSpecification as FrozenSpec
from born_ladder.snapshot.frozen_spec import canonical_json_bytes
from born_ladder.snapshot.frozen_spec import sha256_bytes
from born_ladder.snapshot.inventory import InventoryAuthorization, build_inventory
from born_ladder.snapshot.provenance import ProvenanceFiles, file_sha256
from born_ladder.snapshot.runner_structural import build_runner_capture, parse_runner_capture_bundle
from born_ladder.snapshot.collector_structural import parse_collector_capture_bundle


_IMPLEMENTATION_POINTERS = {
    "campaign_artifact_paths": "/artifact_paths",
    "campaign_attempt_contract": "/completeness/attempt_record_fields",
    "campaign_g2a": "/confirmation_data/campaigns/0",
    "campaign_matrix": "/completeness/expected_matrices/0",
    "campaign_pins": "/provenance/candidate_pins",
    "campaign_raw_marker_order": "/completeness/g2a_raw_stdout_derivation/raw_marker_order",
    "campaign_grid_inventory_name": "/artifact_paths/artifacts/freeze/2",
    "campaign_invocation_manifest_name": "/artifact_paths/artifacts/freeze/3",
    "campaign_output_name": "/artifact_paths/artifacts/g2a/0",
    "campaign_structural_manifest_pattern": "/artifact_paths/structural_manifest_pattern",
    "campaign_timeout": "/thresholds/items/31/value",
    "campaign_workers": "/thresholds/items/30/value",
}
_EXECUTION_ENVIRONMENT: Mapping[str, str] = MappingProxyType({})


@dataclass(frozen=True)
class CampaignArtifacts:
    invocation_manifest_path: Path
    invocation_manifest_sha256: str
    attempt_registry_path: Path
    capture_root: Path
    runner_capture_path: Path
    collector_capture_path: Path
    structural_manifest_path: Path
    completed_invocations: int
    expected_invocations: int
    campaign_artifact_path: Path | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _raw_emission_families(spec: FrozenSpec) -> list[str]:
    markers = spec.get(
        "/completeness/g2a_raw_stdout_derivation/raw_marker_order",
        expected_type=list,
    )
    if not markers or not all(
        isinstance(marker, str)
        and marker.endswith(" ")
        and marker[:-1]
        and not marker[:-1].endswith(" ")
        for marker in markers
    ):
        raise SpecMismatch("frozen G2a raw marker order is malformed")
    families = [marker[:-1] for marker in markers]
    if len(families) != len(set(families)):
        raise SpecMismatch("frozen G2a raw marker families repeat")
    return families


def _write_new(path: Path, raw: bytes, *, safe_root: Path) -> None:
    reject_symlink_chain(path, repo_root=safe_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    reject_symlink_chain(path, repo_root=safe_root)
    try:
        with path.open("xb") as handle:
            handle.write(raw)
    except FileExistsError as error:
        raise IncompleteCampaign(f"artifact collision at {path}") from error


def _write_or_match(path: Path, raw: bytes, *, safe_root: Path) -> None:
    """Resume only when an already sealed artifact is byte-identical."""
    reject_symlink_chain(path, repo_root=safe_root)
    if path.exists() or path.is_symlink():
        try:
            existing = path.read_bytes()
        except OSError as error:
            raise IncompleteCampaign(f"sealed artifact is unreadable: {error}") from error
        if existing != raw:
            raise IncompleteCampaign(f"resume artifact mismatch at {path}")
        return
    _write_new(path, raw, safe_root=safe_root)


def _production_root(spec: FrozenSpec) -> Path:
    namespace = spec.get("/artifact_paths/namespace", expected_type=str)
    candidate = spec.repo_root.absolute() / namespace
    reject_symlink_chain(candidate, repo_root=spec.repo_root.absolute())
    root = candidate.resolve()
    try:
        root.relative_to(spec.repo_root.resolve())
    except ValueError as error:
        raise IncompleteCampaign("campaign namespace escapes repository") from error
    return root


def _published_path(
    spec: FrozenSpec, root: Path, *, name_pointer: str,
    implementation_manifest_path: Path | None,
) -> Path:
    name = spec.get(name_pointer, expected_type=str)
    target = root / name
    reject_symlink_chain(target, repo_root=root)
    if target.exists():
        return target
    authorized = authorized_output_path(
        spec, artifact_name=name, repo_root=spec.repo_root,
        implementation_manifest_path=implementation_manifest_path,
    )
    if authorized != target.resolve():
        raise IncompleteCampaign("authorized campaign output path disagrees")
    return target


def _published_structural_path(
    spec: FrozenSpec, root: Path, *, implementation_manifest_path: Path | None
) -> Path:
    name = spec.get(
        "/artifact_paths/structural_manifest_pattern", expected_type=str
    ).replace("<stage>", "g2a")
    target = root / name
    reject_symlink_chain(target, repo_root=root)
    if target.exists():
        return target
    authorized = authorized_output_path(
        spec, artifact_name=name, repo_root=spec.repo_root,
        implementation_manifest_path=implementation_manifest_path,
    )
    if authorized != target.resolve():
        raise IncompleteCampaign("authorized structural manifest path disagrees")
    return target


def verify_runner(spec: FrozenSpec, runner_path: Path) -> str:
    """Require the exact v8 hash immediately before a process batch."""
    pins = spec.get("/provenance/candidate_pins", expected_type=dict)
    expected_path = (spec.repo_root / pins["runner_binary"]).resolve()
    if runner_path.resolve() != expected_path:
        raise BlockedInfrastructure("campaign runner path is not the frozen binary path")
    try:
        measured = file_sha256(runner_path)
    except (IncompleteCampaign, OSError) as error:
        raise BlockedInfrastructure(
            f"campaign runner binary is unavailable: {error}"
        ) from error
    if measured != pins["runner_binary_sha256"]:
        raise BlockedInfrastructure("campaign runner binary SHA-256 disagrees with v8")
    return measured


def _execute_one(
    spec: FrozenSpec, invocation: Mapping[str, Any], *, runner_path: Path,
    capture_root: Path, timeout_seconds: int,
) -> tuple[str, list[dict[str, Any]]]:
    invocation_id = invocation["invocation_id"]
    argv = list(invocation["argv"])
    execution_cwd = spec.repo_root.resolve()
    records: list[dict[str, Any]] = []
    for attempt_index in range(2):
        attempt_dir = capture_root / invocation_id / f"attempt_{attempt_index}"
        reject_symlink_chain(attempt_dir, repo_root=capture_root)
        sidecars = sorted(attempt_dir.glob("*.attempt.json")) if attempt_dir.exists() else []
        if sidecars:
            if len(sidecars) != 1:
                raise IncompleteCampaign(f"resume attempt sidecars are not unique for {invocation_id}")
            sidecar_path = sidecars[0]
            try:
                record = json.loads(sidecar_path.read_text(encoding="utf-8"))
                expected_sidecar = attempt_dir / (
                    f"{sha256_bytes(canonical_json_bytes(record))}.attempt.json"
                )
                stdout_path = attempt_dir / f'{record["stdout_sha256"]}.stdout.bin'
                stderr_path = attempt_dir / f'{record["stderr_sha256"]}.stderr.bin'
                for sealed_path in (stdout_path, stderr_path, sidecar_path):
                    reject_symlink_chain(sealed_path, repo_root=capture_root)
                stdout = stdout_path.read_bytes()
                stderr = stderr_path.read_bytes()
            except (KeyError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise IncompleteCampaign(f"resume capture is invalid for {invocation_id}: {error}") from error
            if expected_sidecar != sidecar_path or canonical_json_bytes(record) != sidecar_path.read_bytes():
                raise IncompleteCampaign("resume attempt sidecar is not canonical")
            if record["stdout_sha256"] != sha256_bytes(stdout) or record["stderr_sha256"] != sha256_bytes(stderr):
                raise IncompleteCampaign("resume capture hash disagrees")
            expected_children = {stdout_path.name, stderr_path.name, sidecar_path.name}
            if {path.name for path in attempt_dir.iterdir()} != expected_children:
                raise IncompleteCampaign("resume attempt directory has unknown children")
        else:
            if attempt_dir.exists() or attempt_dir.is_symlink():
                raise IncompleteCampaign(f"partial unsealed attempt collision at {attempt_dir}")
            attempt_dir.mkdir(parents=True, exist_ok=False)
            start = _utc_now()
            try:
                completed = subprocess.run(
                    argv, cwd=execution_cwd, env=dict(_EXECUTION_ENVIRONMENT),
                    check=False, timeout=timeout_seconds,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                return_code: int | None = completed.returncode
                timed_out = False
                stdout, stderr = completed.stdout, completed.stderr
            except subprocess.TimeoutExpired as error:
                return_code = None
                timed_out = True
                stdout = error.stdout or b""
                stderr = error.stderr or b""
            except OSError as error:
                raise BlockedInfrastructure(f"runner process unavailable: {error}") from error
            end = _utc_now()
            stdout_hash = sha256_bytes(stdout)
            stderr_hash = sha256_bytes(stderr)
            stdout_path = attempt_dir / f"{stdout_hash}.stdout.bin"
            stderr_path = attempt_dir / f"{stderr_hash}.stderr.bin"
            _write_new(stdout_path, stdout, safe_root=capture_root)
            _write_new(stderr_path, stderr, safe_root=capture_root)
            relative = str(stderr_path.relative_to(capture_root))
            record = build_attempt_record(
                spec, invocation=invocation, argv=argv, cwd=str(execution_cwd),
                start_utc=start, end_utc=end, return_code=return_code, timeout=timed_out,
                stdout=stdout, stderr=stderr, capture_relative_path=relative,
            )
            sidecar_path = attempt_dir / (
                f"{sha256_bytes(canonical_json_bytes(record))}.attempt.json"
            )
            _write_new(
                sidecar_path, canonical_json_bytes(record), safe_root=capture_root
            )
        records.append(record)
        if record["return_code"] == 0 and record["timeout"] is False:
            break
    return invocation_id, records


def _registry_payload(
    spec: FrozenSpec, invocations: Sequence[Mapping[str, Any]],
    records: Mapping[str, Sequence[Mapping[str, Any]]], *, census_sha256: str,
    runner_hash: str,
) -> bytes:
    retry_identities = {}
    attempts = {}
    for invocation in invocations:
        identity = invocation["invocation_id"]
        if identity not in records:
            continue
        invocation_records = records[identity]
        attempts[identity] = [copy.deepcopy(dict(record)) for record in invocation_records]
        record = invocation_records[0]
        retry_identities[identity] = {
            "argv": record["argv"], "cwd": record["cwd"],
            "environment_allowlist": dict(_EXECUTION_ENVIRONMENT),
            "runner_binary_sha256": runner_hash,
            "seed": invocation["seed"],
        }
    return canonical_json_bytes({
        "attempts": attempts, "campaign": "g2a_v2",
        "census_sha256": census_sha256,
        "retry_identities": retry_identities,
        "spec_hash": spec.attestation.json_sha256,
    })






