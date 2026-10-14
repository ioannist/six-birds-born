"""Finalize an already sealed G2a campaign into the frozen v8 artifact layout."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from born_ladder.snapshot.artifact_paths import reject_symlink_chain
from born_ladder.reproduction.predictive.campaign import _registry_payload, _write_new
from born_ladder.snapshot.collector_structural import build_collector_capture, parse_collector_capture_bundle
from born_ladder.snapshot.completeness import ATTEMPT_REGISTRY_FIELDS, RetryIdentity, structural_manifest_bytes, validate_attempt_record
from born_ladder.snapshot.errors import IncompleteCampaign, Rebuild1Error
from born_ladder.reproduction.specification import PublicSpecification as FrozenSpec
from born_ladder.snapshot.frozen_spec import canonical_json_bytes
from born_ladder.snapshot.frozen_spec import sha256_bytes
from born_ladder.snapshot.provenance import ProvenanceFiles, file_sha256, validate_provenance
from born_ladder.snapshot.runner_structural import build_runner_capture, parse_runner_capture_bundle


_IMPLEMENTATION_POINTERS = {
    "finalizer_artifact_paths": "/artifact_paths",
    "finalizer_attempt_contract": "/completeness/attempt_record_fields",
    "finalizer_pins": "/provenance/candidate_pins",
    "finalizer_structural_contract": "/completeness/structural_end_record",
}
_CENSUS_SHA256 = "397af44437bf6de5e8ebed9ebfc52f749bc0389656057b3d76714645f41b6ae3"
_LEGACY_CAMPAIGN_SHA256 = "1f1792e3ee288e545ab97a7ad022e477fc15c3d2362454464747389a564e53eb"
_LEGACY_REGISTRY_SHA256 = "c38b0f14981f6e59c9cbfb068893aa60dc1e2d08cc302c100e6836518a99f443"
_LEGACY_RUNNER_CAPTURE_SHA256 = "fdc69df2aa11145becd0e29e952b534b1d3999c558c9c283ef771264c7b05d9c"
_LEGACY_COLLECTOR_CAPTURE_SHA256 = "44e9f0373f99703a7535e1f84a734bcdd4283c808342bbdcc37f8d687accf8bc"
_EXPECTED_INVOCATIONS = 1380
_LEGACY_DIRECTORY = "superseded/pre_census_fix_2026-08-31"
_CURRENT_SUPERSEDED_DIRECTORY = "superseded/pre_final_fix_2026-08-31"
_LEGACY_CAMPAIGN_FIELDS = {
    "attempt_registry", "collector_structural_capture", "completed_invocations",
    "expected_invocations", "invocation_manifest", "provenance",
    "runner_structural_capture", "schema", "stdout_execution_bindings",
}


def _closed_json(path: Path) -> tuple[bytes, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IncompleteCampaign(f"sealed finalization input is unavailable or invalid: {error}") from error
    if canonical_json_bytes(value) != raw:
        raise IncompleteCampaign(f"sealed finalization input is not canonical JSON: {path}")
    return raw, value


def _bound_path(root: Path, binding: Mapping[str, Any], label: str) -> Path:
    if set(binding) != {"path", "sha256"}:
        raise IncompleteCampaign(f"legacy {label} binding is not closed")
    path = Path(binding["path"]).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise IncompleteCampaign(f"legacy {label} path escapes campaign namespace") from error
    if file_sha256(path) != binding["sha256"]:
        raise IncompleteCampaign(f"legacy {label} hash disagrees")
    return path


def _require_sha256(path: Path, expected: str, label: str) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise IncompleteCampaign(f"reviewed legacy {label} is unavailable: {error}") from error
    if sha256_bytes(raw) != expected:
        raise IncompleteCampaign(f"reviewed legacy {label} SHA-256 disagrees")
    return raw


def _legacy_binding(
    campaign: Mapping[str, Any], field: str, expected_sha256: str, expected_name: str
) -> None:
    binding = campaign.get(field)
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise IncompleteCampaign(f"reviewed legacy {field} binding is not closed")
    if binding["sha256"] != expected_sha256 or Path(binding["path"]).name != expected_name:
        raise IncompleteCampaign(f"reviewed legacy {field} identity disagrees")


def _legacy_attempt_paths(
    old_capture_root: Path, record: Mapping[str, Any]
) -> tuple[Path, Path, Path]:
    relative = Path(record["stderr_or_content_path"])
    attempt_dir = (old_capture_root / relative).resolve()
    try:
        attempt_dir.relative_to(old_capture_root.resolve())
    except ValueError as error:
        raise IncompleteCampaign("legacy attempt path escapes its capture root") from error
    return attempt_dir / "stdout.bin", attempt_dir / "stderr.bin", attempt_dir / "attempt.json"


def _write_content_addressed_attempt(
    *,
    root: Path,
    invocation_id: str,
    attempt_index: int,
    record: Mapping[str, Any],
    stdout: bytes,
    stderr: bytes,
) -> tuple[dict[str, Any], Path]:
    attempt_dir = root / invocation_id / f"attempt_{attempt_index}"
    if attempt_dir.exists() or attempt_dir.is_symlink():
        raise IncompleteCampaign(f"finalized attempt collision at {attempt_dir}")
    attempt_dir.mkdir(parents=True, exist_ok=False)
    stdout_hash = sha256_bytes(stdout)
    stderr_hash = sha256_bytes(stderr)
    updated = copy.deepcopy(dict(record))
    stdout_path = attempt_dir / f"{stdout_hash}.stdout.bin"
    stderr_path = attempt_dir / f"{stderr_hash}.stderr.bin"
    updated["stderr_or_content_path"] = str(stderr_path.relative_to(root))
    sidecar_raw = canonical_json_bytes(updated)
    sidecar_path = attempt_dir / f"{sha256_bytes(sidecar_raw)}.attempt.json"
    _write_new(stdout_path, stdout, safe_root=root)
    _write_new(stderr_path, stderr, safe_root=root)
    _write_new(sidecar_path, sidecar_raw, safe_root=root)
    return updated, stdout_path


def _move_to_superseded(path: Path, *, root: Path, superseded: Path) -> Path:
    target = superseded / path.name
    reject_symlink_chain(path, repo_root=root)
    reject_symlink_chain(target, repo_root=root)
    if target.exists() or target.is_symlink():
        raise IncompleteCampaign(f"superseded artifact collision at {target}")
    path.rename(target)
    return target


def _expected_campaign_root(spec: FrozenSpec) -> Path:
    return (spec.repo_root / spec.get("/artifact_paths/namespace", expected_type=str)).resolve()






