"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Sequence
from born_ladder.snapshot.errors import IncompleteCampaign
from born_ladder.snapshot.frozen_spec import FrozenSpec

_IMPLEMENTATION_POINTERS = {
    "stable_unit_id_formula": "/identity/normative_expression_registry/stable_unit_id",
    "kind_cell_id_formula": "/identity/normative_expression_registry/kind_cell_id",
}


def canonical_identity_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _nonempty_string(name: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise IncompleteCampaign(f"{name} must be a nonempty string")


def stable_unit_id(
    spec: FrozenSpec,
    *,
    source: str,
    experiment_id: str,
    config_id_or_null: str | None,
    seed: int,
    scale: int,
    runner_context_id: str,
    resolution: int,
    step_id: str,
    partition_id: str,
    expected_state_labels: Sequence[str],
    implementation_manifest_path: Path | None = None,
) -> str:
    spec.audit_implementation_manifest(
        "identities", manifest_path=implementation_manifest_path,
        declared_pointers=_IMPLEMENTATION_POINTERS,
    )
    for name, value in (
        ("source", source),
        ("experiment_id", experiment_id),
        ("runner_context_id", runner_context_id),
        ("step_id", step_id),
        ("partition_id", partition_id),
    ):
        _nonempty_string(name, value)
    if config_id_or_null is not None:
        _nonempty_string("config_id_or_null", config_id_or_null)
    if type(seed) is not int or seed < 0:
        raise IncompleteCampaign("seed must be a nonnegative integer")
    if type(scale) is not int or scale <= 0:
        raise IncompleteCampaign("scale must be a positive integer")
    if type(resolution) is not int or resolution <= 0:
        raise IncompleteCampaign("resolution must be a positive integer")
    labels = list(expected_state_labels)
    if not labels or not all(isinstance(label, str) and label for label in labels):
        raise IncompleteCampaign("expected_state_labels must be nonempty strings")
    if len(labels) != len(set(labels)):
        raise IncompleteCampaign("expected_state_labels contains duplicates")
    identity = {
        "config_id_or_null": config_id_or_null,
        "expected_state_labels": labels,
        "experiment_id": experiment_id,
        "partition_id": partition_id,
        "resolution": resolution,
        "runner_context_id": runner_context_id,
        "scale": scale,
        "seed": seed,
        "source": source,
        "spec_payload_sha256": spec.attestation.json_sha256,
        "step_id": step_id,
    }
    return hashlib.sha256(canonical_identity_bytes(identity)).hexdigest()


def kind_cell_id(unit_id: str, kind: str) -> str:
    if not isinstance(unit_id, str) or len(unit_id) != 64:
        raise IncompleteCampaign("unit_id must be a 64-character SHA-256 hex string")
    try:
        int(unit_id, 16)
    except ValueError as error:
        raise IncompleteCampaign("unit_id is not hexadecimal") from error
    if kind not in {"raw", "pkg"}:
        raise IncompleteCampaign("kind must be raw or pkg")
    return hashlib.sha256((unit_id + kind).encode("utf-8")).hexdigest()
