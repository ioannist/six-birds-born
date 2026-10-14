"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
from born_ladder.snapshot.errors import IncompleteCampaign
from pathlib import Path
from born_ladder.snapshot.frozen_spec import FrozenSpec

_IMPLEMENTATION_POINTERS = {"status_contract": "/status_sets"}



def _contract(spec: FrozenSpec, implementation_manifest_path: Path | None = None) -> dict:
    spec.audit_implementation_manifest(
        "status", manifest_path=implementation_manifest_path,
        declared_pointers=_IMPLEMENTATION_POINTERS,
    )
    return spec.get("/status_sets", expected_type=dict)


def preemptive_status(
    spec: FrozenSpec,
    stage: str,
    condition: str,
    *,
    implementation_manifest_path: Path | None = None,
) -> str:
    """Resolve SPEC_MISMATCH/BLOCKED/INCOMPLETE/CONTROL from frozen status sets."""
    contract = _contract(spec, implementation_manifest_path)
    if stage in contract["global_preemptive_by_stage"]:
        candidates = contract["global_preemptive_by_stage"][stage]
    elif stage == "G2R":
        candidates = contract["recognized"].get("g2r", [])[:4]
    else:
        raise IncompleteCampaign(f"unknown frozen stage {stage!r}")
    suffixes = {
        "spec_mismatch": "_SPEC_MISMATCH",
        "blocked": "_BLOCKED_INFRASTRUCTURE",
        "incomplete": "_INCOMPLETE",
        "control_failure": "_CONTROL_FAILURE",
    }
    if condition not in suffixes:
        raise IncompleteCampaign(f"unknown preemptive condition {condition!r}")
    matches = [status for status in candidates if status.endswith(suffixes[condition])]
    if len(matches) != 1:
        raise IncompleteCampaign(
            f"frozen stage {stage} has no unique {condition} status"
        )
    return matches[0]


def recognized_statuses(
    spec: FrozenSpec, family: str, *, implementation_manifest_path: Path | None = None
) -> tuple[str, ...]:
    contract = _contract(spec, implementation_manifest_path)
    recognized = contract["recognized"]
    if family not in recognized:
        raise IncompleteCampaign(f"unknown frozen status family {family!r}")
    statuses = recognized[family]
    if not statuses or len(statuses) != len(set(statuses)):
        raise IncompleteCampaign(f"invalid frozen status family {family!r}")
    return tuple(statuses)


def require_recognized_status(
    spec: FrozenSpec,
    family: str,
    status: str,
    *,
    implementation_manifest_path: Path | None = None,
) -> str:
    if status not in recognized_statuses(
        spec, family, implementation_manifest_path=implementation_manifest_path
    ):
        raise IncompleteCampaign(
            f"unknown status {status!r} for frozen family {family!r}"
        )
    return status

# Production writers restored from the same historical implementation.

def stage_ids(
    spec: FrozenSpec, *, implementation_manifest_path: Path | None = None
) -> tuple[str, ...]:
    contract = _contract(spec, implementation_manifest_path)
    stages = set(contract["global_preemptive_by_stage"])
    if "g2r" in contract["recognized"]:
        stages.add("G2R")
    return tuple(sorted(stages))
