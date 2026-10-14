"""Production entrypoint for the single manager-authorized G2a evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from born_ladder.snapshot.artifact_paths import authorized_output_path, reject_symlink_chain
from born_ladder.snapshot.completeness import AttemptRegistry, load_structural_gate
from born_ladder.snapshot.errors import IncompleteCampaign, Rebuild1Error
from born_ladder.reproduction.specification import PublicSpecification as FrozenSpec
from born_ladder.snapshot.frozen_spec import canonical_json_bytes
from born_ladder.snapshot.frozen_spec import sha256_bytes
from born_ladder.snapshot.g2a import SealedG2aFiniteFailure, _sealed_g2a_unit_artifact, evaluate_g2a
from born_ladder.snapshot.inventory import build_inventory
from born_ladder.snapshot.provenance import ProvenanceFiles, file_sha256, validate_provenance
from born_ladder.snapshot.universal_shapes import canonical_jsonl_bytes


_IMPLEMENTATION_POINTERS = {
    "g2a_eval_artifacts": "/artifact_paths/artifacts/g2a",
    "g2a_eval_campaign": "/confirmation_data/campaigns/0",
    "g2a_eval_freeze_artifacts": "/artifact_paths/artifacts/freeze",
    "g2a_eval_matrix": "/completeness/expected_matrices/0",
    "g2a_eval_namespace": "/artifact_paths/namespace",
    "g2a_eval_provenance": "/provenance",
    "g2a_eval_shapes": "/completeness/universal_evidence_shapes",
    "g2a_eval_structural_pattern": "/artifact_paths/structural_manifest_pattern",
}

_CAMPAIGN_FIELDS = {
    "attempt_registry",
    "census_finalization",
    "collector_structural_capture",
    "completed_invocations",
    "expected_invocations",
    "invocation_manifest",
    "provenance",
    "runner_structural_capture",
    "schema",
    "stdout_execution_bindings",
    "structural_manifest",
}
_IDENTITY_FIELDS = {"path", "sha256"}
_ENVIRONMENT_ALLOWLIST: Mapping[str, str] = {}


@dataclass(frozen=True)
class G2aEvaluationArtifacts:
    units_path: Path
    units_sha256: str
    evaluation_path: Path
    evaluation_sha256: str
    evaluation: Mapping[str, Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _production_root(spec: FrozenSpec) -> Path:
    relative = spec.get("/artifact_paths/namespace", expected_type=str)
    candidate = spec.repo_root.absolute() / relative
    reject_symlink_chain(candidate, repo_root=spec.repo_root.absolute())
    root = candidate.resolve()
    try:
        root.relative_to(spec.repo_root.resolve())
    except ValueError as error:
        raise IncompleteCampaign("G2a evaluation namespace escapes repository") from error
    return root


def _read_canonical_object(path: Path, *, safe_root: Path, label: str) -> tuple[dict[str, Any], bytes]:
    reject_symlink_chain(path, repo_root=safe_root)
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IncompleteCampaign(f"{label} is unavailable or invalid: {error}") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise IncompleteCampaign(f"{label} is not a canonical JSON object")
    return value, raw


def _closed_identity(value: Any, *, label: str) -> tuple[Path, str]:
    if not isinstance(value, dict) or set(value) != _IDENTITY_FIELDS:
        raise IncompleteCampaign(f"{label} identity has a non-closed schema")
    path, digest = value["path"], value["sha256"]
    if not isinstance(path, str) or not isinstance(digest, str):
        raise IncompleteCampaign(f"{label} identity fields are invalid")
    return Path(path), digest


def _require_bound_file(
    value: Any,
    *,
    root: Path,
    label: str,
    exact_path: Path | None = None,
    content_addressed: bool = False,
) -> tuple[Path, str]:
    path, expected = _closed_identity(value, label=label)
    resolved = path.resolve()
    reject_symlink_chain(path, repo_root=root)
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise IncompleteCampaign(f"{label} path escapes the frozen namespace") from error
    if exact_path is not None and resolved != exact_path.resolve():
        raise IncompleteCampaign(f"{label} path is not the exact frozen path")
    if content_addressed and (resolved.parent != root.resolve() or resolved.name != f"{expected}.json"):
        raise IncompleteCampaign(f"{label} path is not its namespace content address")
    if file_sha256(resolved) != expected:
        raise IncompleteCampaign(f"{label} content SHA-256 disagrees")
    return resolved, expected


def _write_new(path: Path, raw: bytes, *, root: Path) -> None:
    reject_symlink_chain(path, repo_root=root)
    try:
        with path.open("xb") as handle:
            handle.write(raw)
    except FileExistsError as error:
        raise IncompleteCampaign(f"artifact collision at {path}") from error
    except OSError as error:
        raise IncompleteCampaign(f"cannot persist evaluation artifact {path}: {error}") from error


def _validate_campaign_bindings(
    campaign: Mapping[str, Any], registry: AttemptRegistry
) -> None:
    expected_ids = registry.invocation_ids()
    bindings = campaign["stdout_execution_bindings"]
    seen: set[str] = set()
    for binding in bindings:
        if not isinstance(binding, dict) or set(binding) != {
            "attempt_record_sha256", "invocation_id", "stdout_path", "stdout_sha256"
        }:
            raise IncompleteCampaign("campaign stdout binding has a non-closed schema")
        invocation_id = binding["invocation_id"]
        if not isinstance(invocation_id, str) or invocation_id in seen:
            raise IncompleteCampaign("campaign stdout binding invocation IDs repeat")
        seen.add(invocation_id)
        stdout_path, stdout_sha256 = registry.successful_capture_identity(invocation_id)
        if (
            Path(binding["stdout_path"]).resolve() != stdout_path.resolve()
            or binding["stdout_sha256"] != stdout_sha256
            or binding["attempt_record_sha256"]
            != registry.successful_attempt_record_sha256(invocation_id)
        ):
            raise IncompleteCampaign("campaign stdout binding disagrees with sealed attempt")
    if seen != expected_ids:
        raise IncompleteCampaign("campaign stdout bindings do not cover the sealed registry")


def _load_campaign_inputs(spec: FrozenSpec, root: Path) -> dict[str, Any]:
    artifacts = spec.get("/artifact_paths/artifacts/g2a", expected_type=list)
    freeze_artifacts = spec.get("/artifact_paths/artifacts/freeze", expected_type=list)
    campaign_path = root / artifacts[0]
    campaign, campaign_raw = _read_canonical_object(
        campaign_path, safe_root=root, label="G2a campaign artifact"
    )
    if set(campaign) != _CAMPAIGN_FIELDS or campaign["schema"] != "RB1_G2A_CAMPAIGN_V2":
        raise IncompleteCampaign("G2a campaign artifact has a non-closed schema")
    validate_provenance(spec, campaign["provenance"])
    matrix = spec.get("/completeness/expected_matrices/0", expected_type=dict)
    expected_count = matrix["expected_invocations"]
    if (
        campaign["completed_invocations"] != expected_count
        or campaign["expected_invocations"] != expected_count
        or not isinstance(campaign["stdout_execution_bindings"], list)
        or len(campaign["stdout_execution_bindings"]) != expected_count
    ):
        raise IncompleteCampaign("G2a campaign does not bind the complete frozen census")

    invocation_path, census_sha256 = _require_bound_file(
        campaign["invocation_manifest"], root=root, label="invocation manifest",
        exact_path=root / freeze_artifacts[3],
    )
    inventory_path = root / freeze_artifacts[2]
    reject_symlink_chain(inventory_path, repo_root=root)
    inventory_sha256 = file_sha256(inventory_path)
    registry_path, registry_sha256 = _require_bound_file(
        campaign["attempt_registry"], root=root, label="attempt registry",
        content_addressed=True,
    )
    runner_path, runner_sha256 = _require_bound_file(
        campaign["runner_structural_capture"], root=root,
        label="runner structural capture", content_addressed=True,
    )
    collector_path, collector_sha256 = _require_bound_file(
        campaign["collector_structural_capture"], root=root,
        label="collector structural capture", content_addressed=True,
    )
    structural_name = spec.get(
        "/artifact_paths/structural_manifest_pattern", expected_type=str
    ).replace("<stage>", "g2a")
    structural_path, structural_sha256 = _require_bound_file(
        campaign["structural_manifest"], root=root, label="structural manifest",
        exact_path=root / structural_name,
    )
    campaign_inputs = campaign["provenance"]["input_sha256s"]
    required_campaign_inputs = {
        "collector_structural_capture": collector_sha256,
        "invocation_manifest": census_sha256,
        "runner_structural_capture": runner_sha256,
        "sealed_attempt_registry": registry_sha256,
        "structural_manifest": structural_sha256,
    }
    if any(
        campaign_inputs.get(name) != expected
        for name, expected in required_campaign_inputs.items()
    ):
        raise IncompleteCampaign("G2a campaign provenance input binding disagrees")
    acceptance_stem = structural_name.removesuffix("_manifest.jsonl")
    acceptance_path = root / f"{acceptance_stem}_acceptance.json"
    signature_path = Path(str(acceptance_path) + ".sig")
    for path, label in (
        (acceptance_path, "structural acceptance"),
        (signature_path, "structural acceptance signature"),
    ):
        reject_symlink_chain(path, repo_root=root)
        if not path.is_file():
            raise IncompleteCampaign(f"{label} is unavailable")

    capture_root = root / f"{Path(artifacts[0]).stem}_attempts_content_addressed"
    reject_symlink_chain(capture_root, repo_root=root)
    if not capture_root.is_dir():
        raise IncompleteCampaign("G2a content-addressed attempt root is unavailable")
    return {
        "acceptance_path": acceptance_path,
        "acceptance_sha256": file_sha256(acceptance_path),
        "campaign_path": campaign_path,
        "campaign": campaign,
        "campaign_sha256": sha256_bytes(campaign_raw),
        "capture_root": capture_root,
        "census_sha256": census_sha256,
        "collector_path": collector_path,
        "collector_sha256": collector_sha256,
        "inventory_path": inventory_path,
        "inventory_sha256": inventory_sha256,
        "invocation_path": invocation_path,
        "registry_path": registry_path,
        "registry_sha256": registry_sha256,
        "runner_path": runner_path,
        "runner_sha256": runner_sha256,
        "signature_path": signature_path,
        "signature_sha256": file_sha256(signature_path),
        "structural_path": structural_path,
        "structural_sha256": structural_sha256,
    }






