"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
from pathlib import Path
from born_ladder.snapshot.errors import IncompleteCampaign

import re

def reject_symlink_chain(path: Path, *, repo_root: Path) -> None:
    """Reject a symlink at the candidate or any ancestor through repo_root."""
    root = repo_root.absolute()
    candidate = path.absolute()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise IncompleteCampaign("artifact path escapes repository") from error
    current = candidate
    while True:
        if current.is_symlink():
            raise IncompleteCampaign(f"artifact path contains a symlink: {current}")
        if current == root:
            break
        current = current.parent

# Production writers restored from the same historical implementation.

_IMPLEMENTATION_POINTERS = {"artifact_paths_contract": "/artifact_paths"}

def authorized_output_path(
    spec: FrozenSpec,
    *,
    artifact_name: str,
    repo_root: Path,
    implementation_manifest_path: Path | None = None,
) -> Path:
    spec.audit_implementation_manifest(
        "artifact_paths", manifest_path=implementation_manifest_path,
        declared_pointers=_IMPLEMENTATION_POINTERS,
    )
    contract = spec.get("/artifact_paths", expected_type=dict)
    if contract["collision_policy"] != "abort rather than overwrite":
        raise IncompleteCampaign("unsupported artifact collision policy")
    if contract["historical_write_prohibited"] is not True:
        raise IncompleteCampaign("historical-write prohibition is not frozen true")
    names = {
        name
        for group in contract["artifacts"].values()
        for name in group
        if name.endswith((".json", ".jsonl"))
    }
    frozen_pattern = contract["structural_manifest_pattern"]
    marker = re.escape("<stage>")
    structural_pattern = re.escape(frozen_pattern).replace(marker, "[a-z0-9_]+")
    if artifact_name not in names and not re.fullmatch(structural_pattern, artifact_name):
        raise IncompleteCampaign(f"artifact identity {artifact_name!r} is not frozen")
    # Frozen companion files are immutable inputs, never writable outputs.
    if artifact_name.startswith("born_route_rebuild1_spec_"):
        raise IncompleteCampaign("frozen companion is a historical-write target")
    root = repo_root.absolute()
    namespace = root / contract["namespace"]
    reject_symlink_chain(namespace, repo_root=root)
    namespace = namespace.resolve()
    try:
        namespace.relative_to(root)
    except ValueError as error:
        raise IncompleteCampaign("frozen artifact namespace escapes repository") from error
    target_candidate = namespace / artifact_name
    reject_symlink_chain(target_candidate, repo_root=root)
    target = target_candidate.resolve()
    try:
        target.relative_to(namespace)
    except ValueError as error:
        raise IncompleteCampaign("artifact target escapes frozen namespace") from error
    if target.exists() or target.is_symlink():
        raise IncompleteCampaign(f"artifact collision at {target}")
    return target
