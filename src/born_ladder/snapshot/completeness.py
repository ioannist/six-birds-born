"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import copy
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from born_ladder.snapshot.errors import BlockedInfrastructure, IncompleteCampaign, SpecMismatch
from born_ladder.snapshot.collector_structural import parse_collector_capture_bundle, reconstruct_collector_record
from born_ladder.snapshot.frozen_spec import IMPLEMENTATION_MANIFEST, FrozenSpec, canonical_json_bytes, sha256_bytes
from born_ladder.snapshot.identities import canonical_identity_bytes
from born_ladder.snapshot.inventory import InventoryAuthorization
from born_ladder.snapshot.runner_structural import parse_runner_capture_bundle, parse_runner_stdout
from born_ladder.snapshot.status import preemptive_status

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


_STRUCTURAL_TOKEN = object()


MANAGER_ACCEPTANCE_FIELDS = {
    "accepted_utc", "campaign", "census_sha256", "collector_manifest_sha256",
    "runner_manifest_sha256", "spec_hash",
}


ATTEMPT_REGISTRY_FIELDS = {
    "attempts", "campaign", "census_sha256", "retry_identities", "spec_hash",
}


ATTEMPT_SUMMARY_FIELDS = {
    "duplicate_counts", "emitted_counts", "expected_observed_id_differences",
    "parse_failures",
}


STRUCTURAL_ACCEPTANCE_NAMESPACE = "rb1-structural-acceptance"


_IMPLEMENTATION_POINTERS = {
    "accepted_existing_evidence_contract": "/completeness/g2h_h3_v13_transport_and_evaluation/accepted_existing_evidence",
    "campaign_contract": "/confirmation_data/campaigns",
    "completeness_contract": "/completeness",
    "acceptance_trust_contract": "/identity/attestation",
    "structural_manifest_namespace": "/artifact_paths/namespace",
    "structural_manifest_pattern": "/artifact_paths/structural_manifest_pattern",
    "g2h_v10_adoption_contract": "/completeness/g2h_h1_h2_v10_execution_adoption",
    "g2h_v13_transport_contract": "/completeness/g2h_h3_v13_transport_and_evaluation",
    "g2x_v20_reproduction_plan": "/artifact_paths/g2x_per_unit_reproduction_plan",
    "g2c_v21_reproduction_plan": "/artifact_paths/g2c_per_unit_reproduction_plan",
    "prior_freeze_identities_contract": "/artifact_paths/prior_freeze_identities_preserved",
}


_STRUCTURAL_IMPLEMENTATION_POINTERS = {
    "runner_structural": {
        "runner_structural_end_record": "/completeness/structural_end_record"
    },
    "collector_structural": {
        "collector_derivation_registry": "/completeness/g2a_raw_stdout_derivation",
        "collector_structural_end_record": "/completeness/structural_end_record",
    },
    "g2h_collector_structural": {
        "g2h_collector_complete_suppression": "/completeness/g2h_raw_stdout_derivation/complete_suppression",
        "g2h_collector_derivation": "/completeness/g2h_raw_stdout_derivation",
        "g2h_collector_segment_census": "/completeness/g2h_raw_stdout_derivation/segment_census_agreement",
        "g2h_collector_structural_end": "/completeness/structural_end_record",
    },
    "g2x_collector_structural": {
        "g2x_collector_derivation": "/completeness/g2x_raw_stdout_derivation",
        "g2x_collector_structural_end": "/completeness/structural_end_record",
    },
    "g2c_collector_structural": {
        "g2c_collector_derivation": "/completeness/g2c_raw_stdout_derivation",
        "g2c_collector_structural_end": "/completeness/structural_end_record",
    },
}



def _sha256(value: object) -> str:
    return hashlib.sha256(canonical_identity_bytes(value)).hexdigest()


def _campaign(spec: FrozenSpec, campaign_name: str) -> dict[str, Any]:
    campaigns = spec.get("/confirmation_data/campaigns", expected_type=list)
    matches = [item for item in campaigns if item["name"] == campaign_name]
    if len(matches) != 1:
        raise IncompleteCampaign(
            f"campaign {campaign_name!r} is absent or duplicated in frozen payload"
        )
    return matches[0]


def _is_g2h_campaign(campaign_name: str) -> bool:
    return campaign_name in {
        "g2h_h1_h2_v2",
        "g2h_h3_v2",
        "g2h_h3_v13_reexecution",
        "g2h_h4_v2",
    }


def _is_g2x_campaign(campaign_name: str) -> bool:
    return campaign_name == "g2x_confirm_v2"


def _is_g2c_campaign(campaign_name: str) -> bool:
    return campaign_name == "g2c_v2"


def _argv_for(
    spec: FrozenSpec, *, experiment: str, config: str | None, seed: int, scale: int
) -> list[str]:
    templates = spec.get("/provenance/campaign_argv_templates", expected_type=list)
    template = templates[0] if experiment == "EXP-112" else templates[1]
    replacements = {
        "EXP-112": experiment, "<EXP-102..EXP-107>": experiment,
        "<frozen-seed>": str(seed), "<frozen-scale>": str(scale),
        "<frozen-label>": config,
    }
    argv: list[str] = []
    for value in template:
        replacement = replacements.get(value, value)
        if replacement is None:
            raise IncompleteCampaign("EXP-112 invocation requires a config label")
        argv.append(replacement)
    return argv


def invocation_id_for(
    spec: FrozenSpec, *, experiment: str, config_or_null: str | None, seed: int, scale: int
) -> str:
    contract = spec.get("/completeness/structural_end_record/identity_hashing", expected_type=dict)
    if contract.get("final_lf_included") is not True:
        raise SpecMismatch("frozen structural invocation identity does not include final LF")
    return _sha256({
        "config_or_null": config_or_null, "experiment": experiment,
        "scale": scale, "seed": seed,
    })


def build_invocation_manifest(
    spec: FrozenSpec,
    campaign_name: str,
    *,
    expected_schema: str,
    required_emission_families: Sequence[str],
    inventory_authorization: InventoryAuthorization,
    implementation_manifest_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Regenerate the complete frozen pre-run census after the live inventory gate."""
    spec.audit_implementation_manifest(
        "completeness", manifest_path=implementation_manifest_path,
        declared_pointers=_IMPLEMENTATION_POINTERS,
    )
    inventory_authorization.require_for(spec)
    if not isinstance(expected_schema, str) or not expected_schema:
        raise IncompleteCampaign("expected_schema must be an explicit nonempty identity")
    families = list(required_emission_families)
    if not families or not all(isinstance(item, str) and item for item in families):
        raise IncompleteCampaign("required emission families must be nonempty strings")
    if len(families) != len(set(families)):
        raise IncompleteCampaign("required emission families contain duplicates")
    campaign = _campaign(spec, campaign_name)
    if not campaign["seeds"] or not campaign["scales"]:
        raise IncompleteCampaign(f"campaign {campaign_name} has no runner invocation matrix")
    labels = spec.get("/grid/labels", expected_type=list)
    required_fields = set(spec.get("/completeness/invocation_manifest_fields", expected_type=list))
    records: list[dict[str, Any]] = []
    for experiment in campaign["experiments"]:
        configs: Sequence[str | None] = labels if experiment == "EXP-112" else [None]
        for config in configs:
            for seed in campaign["seeds"]:
                for scale in campaign["scales"]:
                    record = {
                        "argv": _argv_for(spec, experiment=experiment, config=config, seed=seed, scale=scale),
                        "config_or_null": config,
                        "expected_schema": expected_schema,
                        "experiment": experiment,
                        "invocation_id": invocation_id_for(
                            spec, experiment=experiment, config_or_null=config, seed=seed, scale=scale
                        ),
                        "required_emission_families": families,
                        "scale": scale,
                        "seed": seed,
                    }
                    if set(record) != required_fields:
                        raise IncompleteCampaign("invocation record fields disagree with frozen companion")
                    records.append(record)
    ids = [record["invocation_id"] for record in records]
    if not records or len(ids) != len(set(ids)):
        raise IncompleteCampaign("generated invocation manifest is empty or duplicate")
    matrix_name = campaign_name.removesuffix("_v2")
    matrices = spec.get("/completeness/expected_matrices", expected_type=list)
    expected = [item["expected_invocations"] for item in matrices if item["campaign"] == matrix_name]
    if len(expected) != 1 or len(records) != expected[0]:
        raise IncompleteCampaign(
            f"generated {len(records)} records for {campaign_name}; frozen matrix={expected}"
        )
    return records


def invocation_manifest_bytes(records: Sequence[Mapping[str, Any]]) -> bytes:
    if not records:
        raise IncompleteCampaign("invocation census must not be empty")
    return canonical_json_bytes([dict(record) for record in records])


@dataclass(frozen=True)
class RetryIdentity:
    argv: tuple[str, ...]

    cwd: str

    environment_allowlist: tuple[tuple[str, str], ...]

    runner_binary_sha256: str

    seed: int

    per_attempt_timeout_seconds: int | None = None

    @classmethod
    def create(
        cls, *, argv: Sequence[str], cwd: str,
        environment_allowlist: Mapping[str, str], runner_binary_sha256: str, seed: int,
        per_attempt_timeout_seconds: int | None = None,
    ) -> "RetryIdentity":
        if not argv or not all(isinstance(item, str) for item in argv):
            raise IncompleteCampaign("retry argv must be a nonempty string array")
        if not cwd or not isinstance(cwd, str):
            raise IncompleteCampaign("retry cwd must be nonempty")
        if not _HEX64.fullmatch(runner_binary_sha256):
            raise IncompleteCampaign("retry runner hash is malformed")
        if type(seed) is not int or seed < 0:
            raise IncompleteCampaign("retry seed is invalid")
        if per_attempt_timeout_seconds is not None and (
            type(per_attempt_timeout_seconds) is not int
            or per_attempt_timeout_seconds <= 0
        ):
            raise IncompleteCampaign("retry timeout is invalid")
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in environment_allowlist.items()):
            raise IncompleteCampaign("retry environment allowlist is invalid")
        return cls(
            tuple(argv), cwd, tuple(sorted(environment_allowlist.items())),
            runner_binary_sha256, seed, per_attempt_timeout_seconds,
        )



def validate_attempt_record(spec: FrozenSpec, record: Mapping[str, Any]) -> None:
    expected_fields = set(spec.get("/completeness/attempt_record_fields", expected_type=list))
    if set(record) != expected_fields:
        raise IncompleteCampaign(
            f"attempt record field mismatch missing={sorted(expected_fields-set(record))} "
            f"unknown={sorted(set(record)-expected_fields)}"
        )
    if not isinstance(record["argv"], list) or not record["argv"] or not all(isinstance(x, str) for x in record["argv"]):
        raise IncompleteCampaign("attempt argv must be a nonempty string array")
    if not isinstance(record["cwd"], str) or not record["cwd"]:
        raise IncompleteCampaign("attempt cwd must be nonempty")
    for name in ("start_utc", "end_utc"):
        if not isinstance(record[name], str) or not record[name].endswith("Z"):
            raise IncompleteCampaign(f"{name} must be an explicit UTC Z timestamp")
    if record["return_code"] is not None and type(record["return_code"]) is not int:
        raise IncompleteCampaign("return_code must be integer or null")
    if type(record["timeout"]) is not bool:
        raise IncompleteCampaign("timeout must be Boolean")
    for name in ("stdout_sha256", "stderr_sha256", "runner_hash", "spec_hash", "source_hash"):
        if not isinstance(record[name], str) or not _HEX64.fullmatch(record[name]):
            raise IncompleteCampaign(f"{name} must be a SHA-256 digest")
    if not isinstance(record["stderr_or_content_path"], str):
        raise IncompleteCampaign("stderr_or_content_path must be a string")
    for name in ("emitted_counts", "duplicate_counts"):
        value = record[name]
        if not isinstance(value, dict) or not all(
            isinstance(k, str) and type(v) is int and v >= 0 for k, v in value.items()
        ):
            raise IncompleteCampaign(f"{name} must map strings to nonnegative integers")
    differences = record["expected_observed_id_differences"]
    if not isinstance(differences, dict) or set(differences) != {"extra", "missing"}:
        raise IncompleteCampaign("ID differences must have exact extra and missing arrays")
    if not all(isinstance(v, list) and all(isinstance(x, str) for x in v) for v in differences.values()):
        raise IncompleteCampaign("ID differences must contain string arrays")
    if not isinstance(record["parse_failures"], list) or not all(isinstance(x, str) for x in record["parse_failures"]):
        raise IncompleteCampaign("parse_failures must be a string array")
    if record["exclusion_reason"] is not None and not isinstance(record["exclusion_reason"], str):
        raise IncompleteCampaign("exclusion_reason must be string or null")


class AttemptRegistry:
    """Immutable registry loaded from content-addressed canonical attempt evidence."""

    __slots__ = (
        "_campaign", "_capture_hashes", "_capture_paths", "_census_sha256", "_evidence_path",
        "_evidence_sha256", "_invocation_manifest_path", "_invocation_manifest_sha256",
        "_completion_records", "_interpretation_raw", "_interpretation_sha256",
        "_records", "_retry_identities", "_sealed", "_spec_hash",
        "_acceptance_era_spec_hash",
    )

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("AttemptRegistry is immutable")
        object.__setattr__(self, name, value)

    def __init__(
        self,
        *,
        records: dict[str, list[dict[str, Any]]],
        retry_identities: dict[str, RetryIdentity],
        campaign: str,
        census_sha256: str,
        spec_hash: str,
        evidence_path: Path,
        evidence_sha256: str,
        invocation_manifest_path: Path,
        invocation_manifest_sha256: str,
        capture_hashes: dict[Path, tuple[str, str, str]],
        capture_paths: dict[str, tuple[Path, ...]],
        completion_records: dict[str, list[dict[str, Any]]] | None = None,
        interpretation_raw: bytes | None = None,
        acceptance_era_spec_hash: str | None = None,
        token: object,
    ) -> None:
        if token is not _STRUCTURAL_TOKEN:
            raise IncompleteCampaign("attempt registry was not loaded from sealed evidence")
        self._records = copy.deepcopy(records)
        self._completion_records = copy.deepcopy(
            records if completion_records is None else completion_records
        )
        self._retry_identities = dict(retry_identities)
        self._campaign = campaign
        self._census_sha256 = census_sha256
        self._spec_hash = spec_hash
        self._evidence_path = evidence_path
        self._evidence_sha256 = evidence_sha256
        self._invocation_manifest_path = invocation_manifest_path
        self._invocation_manifest_sha256 = invocation_manifest_sha256
        self._capture_hashes = dict(capture_hashes)
        self._capture_paths = dict(capture_paths)
        self._interpretation_raw = interpretation_raw
        self._interpretation_sha256 = (
            None if interpretation_raw is None else sha256_bytes(interpretation_raw)
        )
        self._acceptance_era_spec_hash = acceptance_era_spec_hash
        self._sealed = True

    @classmethod
    def load(
        cls,
        spec: FrozenSpec,
        *,
        evidence_path: Path,
        capture_root: Path,
        invocation_manifest_path: Path,
        campaign_name: str,
        census_sha256: str,
    ) -> "AttemptRegistry":
        try:
            raw = evidence_path.read_bytes()
        except OSError as error:
            raise IncompleteCampaign(f"attempt evidence is unavailable: {error}") from error
        evidence_sha256 = sha256_bytes(raw)
        if evidence_path.name != f"{evidence_sha256}.json":
            raise IncompleteCampaign("attempt registry path is not its content address")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise IncompleteCampaign(f"attempt registry parse failure: {error}") from error
        if not isinstance(payload, dict) or set(payload) != ATTEMPT_REGISTRY_FIELDS:
            raise IncompleteCampaign("attempt registry has a non-closed schema")
        if canonical_json_bytes(payload) != raw:
            raise IncompleteCampaign("attempt registry is not canonical JSON")
        expected_binding = {
            "campaign": campaign_name,
            "census_sha256": census_sha256,
            "spec_hash": spec.attestation.json_sha256,
        }
        for name, expected in expected_binding.items():
            if payload[name] != expected:
                raise IncompleteCampaign(f"attempt registry {name} disagrees")
        try:
            invocation_raw = invocation_manifest_path.read_bytes()
            invocation_records = json.loads(invocation_raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise IncompleteCampaign(f"frozen invocation manifest unavailable or invalid: {error}") from error
        if (
            sha256_bytes(invocation_raw) != census_sha256
            or canonical_json_bytes(invocation_records) != invocation_raw
            or not isinstance(invocation_records, list)
            or not invocation_records
        ):
            raise IncompleteCampaign("frozen invocation manifest bytes/census disagree")
        invocation_by_id = {
            item.get("invocation_id"): item for item in invocation_records
            if isinstance(item, dict)
        }
        if len(invocation_by_id) != len(invocation_records):
            raise IncompleteCampaign("frozen invocation manifest IDs are missing or duplicated")
        attempts = payload["attempts"]
        retries = payload["retry_identities"]
        if not isinstance(attempts, dict) or not attempts or set(attempts) != set(retries):
            raise IncompleteCampaign("attempt/retry registries are empty or differently keyed")
        root = capture_root.resolve()
        parsed_records: dict[str, list[dict[str, Any]]] = {}
        parsed_retries: dict[str, RetryIdentity] = {}
        retries_allowed = spec.get(
            "/completeness/missingness/automatic_retries", expected_type=int
        )
        expected_source = spec.get(
            "/provenance/candidate_pins/runner_source_sha256", expected_type=str
        )
        expected_runner = spec.get(
            "/provenance/candidate_pins/runner_binary_sha256", expected_type=str
        )
        used_capture_paths: set[Path] = set()
        capture_hashes: dict[Path, tuple[str, str, str]] = {}
        capture_paths: dict[str, tuple[Path, ...]] = {}
        timeout_pointer = {
            "g2h_h3_v13_reexecution": (
                "/confirmation_data/g2h_h3_v13_reexecution/per_attempt_timeout_seconds"
            ),
        }.get(campaign_name)
        if campaign_name == "g2x_confirm_v2":
            plan = spec.get(
                "/artifact_paths/g2x_per_unit_reproduction_plan", expected_type=dict
            )
            expected_manifest = plan.get("artifacts", [None])[0]
            if (
                plan.get("campaign_id") == "g2x_confirm_v20_reexecution"
                and invocation_manifest_path.name == expected_manifest
            ):
                timeout_pointer = (
                    "/confirmation_data/g2x_confirm_v20_reexecution/"
                    "per_attempt_timeout_seconds"
                )
        elif campaign_name == "g2c_v2":
            plan = spec.get(
                "/artifact_paths/g2c_per_unit_reproduction_plan", expected_type=dict
            )
            if invocation_manifest_path.name == plan.get("artifacts", [None])[0]:
                timeout_pointer = (
                    "/confirmation_data/g2c_v21_execution/per_attempt_timeout_seconds"
                )
        v13_timeout = (
            spec.get(timeout_pointer, expected_type=int)
            if timeout_pointer is not None else None
        )
        for invocation_id, records in attempts.items():
            if not isinstance(invocation_id, str) or not _HEX64.fullmatch(invocation_id):
                raise IncompleteCampaign("attempt invocation_id is not a SHA-256 digest")
            if invocation_id not in invocation_by_id:
                raise IncompleteCampaign("attempt invocation_id is absent from frozen invocation manifest")
            if not isinstance(records, list) or not 1 <= len(records) <= 1 + retries_allowed:
                raise IncompleteCampaign(f"retry exhaustion or empty attempts for {invocation_id}")
            retry_value = retries[invocation_id]
            retry_fields = {
                "argv", "cwd", "environment_allowlist", "runner_binary_sha256", "seed"
            }
            if v13_timeout is not None:
                retry_fields.add("per_attempt_timeout_seconds")
            if not isinstance(retry_value, dict) or set(retry_value) != retry_fields:
                raise IncompleteCampaign("sealed retry identity has a non-closed schema")
            retry_identity = RetryIdentity.create(**retry_value)
            if retry_identity.per_attempt_timeout_seconds != v13_timeout:
                raise IncompleteCampaign("sealed retry identity timeout disagrees")
            if retry_identity.runner_binary_sha256 != expected_runner:
                raise IncompleteCampaign("sealed retry identity runner hash disagrees")
            checked: list[dict[str, Any]] = []
            invocation_capture_paths: list[Path] = []
            for index, record in enumerate(records):
                if not isinstance(record, dict):
                    raise IncompleteCampaign("attempt evidence record is not an object")
                validation_record = dict(record)
                if v13_timeout is not None:
                    sidecar_timeout = validation_record.pop(
                        "per_attempt_timeout_seconds", None
                    )
                    if (
                        type(sidecar_timeout) is not int
                        or sidecar_timeout != v13_timeout
                    ):
                        raise IncompleteCampaign("attempt sidecar timeout disagrees")
                validate_attempt_record(spec, validation_record)
                if record["argv"] != invocation_by_id[invocation_id]["argv"]:
                    raise IncompleteCampaign("attempt argv disagrees with frozen invocation manifest")
                if tuple(record["argv"]) != retry_identity.argv or record["cwd"] != retry_identity.cwd:
                    raise IncompleteCampaign("attempt record disagrees with sealed retry identity")
                if record["runner_hash"] != expected_runner:
                    raise IncompleteCampaign("attempt runner hash disagrees with frozen binary")
                if record["spec_hash"] != spec.attestation.json_sha256:
                    raise IncompleteCampaign("attempt spec hash disagrees with signed payload")
                if record["source_hash"] != expected_source:
                    raise IncompleteCampaign("attempt source hash disagrees with frozen payload")
                relative = Path(record["stderr_or_content_path"])
                stderr_path = (root / relative).resolve()
                capture_dir = stderr_path.parent
                try:
                    capture_dir.relative_to(root)
                except ValueError as error:
                    raise IncompleteCampaign("attempt capture path escapes its sealed root") from error
                if capture_dir in used_capture_paths:
                    raise IncompleteCampaign("attempt capture path is reused")
                used_capture_paths.add(capture_dir)
                try:
                    stdout_path = capture_dir / f'{record["stdout_sha256"]}.stdout.bin'
                    expected_stderr_path = capture_dir / f'{record["stderr_sha256"]}.stderr.bin'
                    sidecar_sha256 = sha256_bytes(canonical_json_bytes(record))
                    sidecar_path = capture_dir / f"{sidecar_sha256}.attempt.json"
                    if stderr_path != expected_stderr_path.resolve():
                        raise IncompleteCampaign("attempt stderr path is not content-addressed")
                    stdout = stdout_path.read_bytes()
                    stderr = stderr_path.read_bytes()
                    sidecar = sidecar_path.read_bytes()
                except OSError as error:
                    raise IncompleteCampaign(f"attempt captured content unavailable: {error}") from error
                if sidecar != canonical_json_bytes(record):
                    raise IncompleteCampaign("attempt sidecar bytes or content address disagree")
                if sha256_bytes(stdout) != record["stdout_sha256"]:
                    raise IncompleteCampaign("attempt stdout content hash disagrees")
                if sha256_bytes(stderr) != record["stderr_sha256"]:
                    raise IncompleteCampaign("attempt stderr content hash disagrees")
                capture_hashes[capture_dir] = (
                    record["stdout_sha256"], record["stderr_sha256"], sidecar_sha256
                )
                invocation_capture_paths.append(capture_dir)
                summary = _derive_attempt_summary(
                    spec, stdout, invocation_by_id[invocation_id],
                    campaign_name=campaign_name,
                )
                for field_name in ATTEMPT_SUMMARY_FIELDS:
                    if record[field_name] != summary[field_name]:
                        raise IncompleteCampaign(
                            f"attempt {field_name} disagrees with parsed stdout content"
                        )
                if index and records[0]["return_code"] == 0 and not records[0]["timeout"]:
                    raise IncompleteCampaign("retry follows a successful process")
                checked.append(copy.deepcopy(record))
            parsed_records[invocation_id] = checked
            parsed_retries[invocation_id] = retry_identity
            capture_paths[invocation_id] = tuple(invocation_capture_paths)
        return cls(
            records=parsed_records,
            retry_identities=parsed_retries,
            campaign=campaign_name,
            census_sha256=census_sha256,
            spec_hash=spec.attestation.json_sha256,
            evidence_path=evidence_path.resolve(),
            evidence_sha256=evidence_sha256,
            invocation_manifest_path=invocation_manifest_path.resolve(),
            invocation_manifest_sha256=census_sha256,
            capture_hashes=capture_hashes,
            capture_paths=capture_paths,
            token=_STRUCTURAL_TOKEN,
        )

    def require_binding(self, spec: FrozenSpec, campaign: str, census_sha256: str) -> None:
        if self._campaign != campaign or self._census_sha256 != census_sha256:
            raise IncompleteCampaign("attempt registry campaign/census binding disagrees")
        if self._spec_hash != spec.attestation.json_sha256:
            raise IncompleteCampaign("attempt registry spec binding disagrees")
        try:
            current = self._evidence_path.read_bytes()
            invocation_manifest = self._invocation_manifest_path.read_bytes()
        except OSError as error:
            raise IncompleteCampaign(f"sealed attempt or invocation registry disappeared: {error}") from error
        if sha256_bytes(current) != self._evidence_sha256:
            raise IncompleteCampaign("sealed attempt registry changed after loading")
        if sha256_bytes(invocation_manifest) != self._invocation_manifest_sha256:
            raise IncompleteCampaign("sealed invocation manifest changed after attempt loading")
        for capture_dir, (stdout_hash, stderr_hash, sidecar_hash) in self._capture_hashes.items():
            try:
                stdout = (capture_dir / f"{stdout_hash}.stdout.bin").read_bytes()
                stderr = (capture_dir / f"{stderr_hash}.stderr.bin").read_bytes()
                sidecar = (capture_dir / f"{sidecar_hash}.attempt.json").read_bytes()
            except OSError as error:
                raise IncompleteCampaign(f"sealed attempt capture disappeared: {error}") from error
            if (
                sha256_bytes(stdout) != stdout_hash
                or sha256_bytes(stderr) != stderr_hash
                or sha256_bytes(sidecar) != sidecar_hash
            ):
                raise IncompleteCampaign("sealed attempt capture changed after loading")

    def attempts_for(self, invocation_id: str) -> list[dict[str, Any]]:
        return copy.deepcopy(self._completion_records.get(invocation_id, []))

    def successful_stdout(self, invocation_id: str) -> bytes:
        """Return rechecked stdout from the sole sealed successful attempt."""
        records = self._records.get(invocation_id, [])
        paths = self._capture_paths.get(invocation_id, ())
        successes = [
            index for index, record in enumerate(records)
            if record["return_code"] == 0 and record["timeout"] is False
        ]
        if len(successes) != 1 or len(paths) != len(records):
            raise IncompleteCampaign(
                f"sealed invocation {invocation_id} lacks one successful stdout capture"
            )
        index = successes[0]
        capture_dir = paths[index]
        try:
            stdout_hash, stderr_hash, sidecar_hash = self._capture_hashes[capture_dir]
            stdout = (capture_dir / f"{stdout_hash}.stdout.bin").read_bytes()
            stderr = (capture_dir / f"{stderr_hash}.stderr.bin").read_bytes()
            sidecar = (capture_dir / f"{sidecar_hash}.attempt.json").read_bytes()
        except OSError as error:
            raise IncompleteCampaign(
                f"sealed attempt capture disappeared: {error}"
            ) from error
        if (
            sha256_bytes(stdout) != stdout_hash
            or sha256_bytes(stderr) != stderr_hash
            or sha256_bytes(sidecar) != sidecar_hash
        ):
            raise IncompleteCampaign("sealed attempt capture changed after loading")
        return stdout

    def invocation_record(self, invocation_id: str) -> dict[str, Any]:
        """Return the rechecked frozen pre-run record for one sealed invocation."""
        self.require_binding_identity_only()
        records = _load_invocation_records(
            self._invocation_manifest_path, self._invocation_manifest_sha256
        )
        matches = [record for record in records if record["invocation_id"] == invocation_id]
        if len(matches) != 1:
            raise IncompleteCampaign(
                f"sealed invocation manifest has no unique record for {invocation_id}"
            )
        return copy.deepcopy(matches[0])

    def invocation_records(self) -> list[dict[str, Any]]:
        """Return the rechecked pre-run census in its frozen manifest order."""
        self.require_binding_identity_only()
        return copy.deepcopy(_load_invocation_records(
            self._invocation_manifest_path, self._invocation_manifest_sha256
        ))

    def successful_attempt_record_sha256(self, invocation_id: str) -> str:
        """Return the canonical hash of the sole successful orchestrator sidecar."""
        records = self._records.get(invocation_id, [])
        successes = [
            record for record in records
            if record["return_code"] == 0 and record["timeout"] is False
        ]
        if len(successes) != 1:
            raise IncompleteCampaign(
                f"sealed invocation {invocation_id} lacks one successful sidecar"
            )
        return sha256_bytes(canonical_json_bytes(successes[0]))

    def require_binding_identity_only(self) -> None:
        """Recheck immutable registry and capture bytes without a caller campaign tuple."""
        try:
            evidence = self._evidence_path.read_bytes()
            invocation = self._invocation_manifest_path.read_bytes()
        except OSError as error:
            raise IncompleteCampaign(f"sealed registry binding disappeared: {error}") from error
        if sha256_bytes(evidence) != self._evidence_sha256:
            raise IncompleteCampaign("sealed attempt registry changed after loading")
        if sha256_bytes(invocation) != self._invocation_manifest_sha256:
            raise IncompleteCampaign("sealed invocation manifest changed after loading")

    def retry_identity_for(self, invocation_id: str) -> RetryIdentity | None:
        return self._retry_identities.get(invocation_id)

    def invocation_ids(self) -> set[str]:
        return set(self._records)

    @property
    def census_sha256(self) -> str:
        return self._census_sha256

    @property
    def historical_evidence_sha256(self) -> str:
        return self._evidence_sha256

    @property
    def evidence_path(self) -> Path:
        self.require_binding_identity_only()
        return self._evidence_path



    def successful_capture_identity(self, invocation_id: str) -> tuple[Path, str]:
        records = self._records.get(invocation_id, [])
        paths = self._capture_paths.get(invocation_id, ())
        successes = [
            index for index, record in enumerate(records)
            if record["return_code"] == 0 and record["timeout"] is False
        ]
        if len(successes) != 1 or len(paths) != len(records):
            raise IncompleteCampaign(
                f"sealed invocation {invocation_id} lacks exactly one successful capture"
            )
        index = successes[0]
        capture_dir = paths[index]
        stdout_hash = self._capture_hashes[capture_dir][0]
        stdout_path = (capture_dir / f"{stdout_hash}.stdout.bin").resolve()
        stdout = self.successful_stdout(invocation_id)
        return stdout_path, sha256_bytes(stdout)

    @property
    def interpretation_sha256(self) -> str | None:
        return self._interpretation_sha256

def _duplicate_counts(manifest: Mapping[str, Any]) -> dict[str, int]:
    units = manifest["units"]
    def repeats(values: Sequence[Any]) -> int:
        encoded = [canonical_identity_bytes(value) for value in values]
        return len(encoded) - len(set(encoded))
    return {
        "invocation_ids": 0,
        "unit_identities": repeats([
            [unit["config_id"], unit["partition_id"], unit["step_id"]]
            for unit in units
        ]),
        "runner_context_ids": repeats([unit["runner_context_id"] for unit in units]),
    }


_G2C_SEMANTIC_TO_STRUCTURAL_FAMILY = {
    "Born": "KEY_BORN_PROBE_JSON",
    "Discovery": "KEY_DISCOVERY_GRADE_JSON",
    "Audit": "KEY_AUDIT_JSON",
}


def _structural_families_for_campaign(
    campaign_name: str, families: Sequence[str]
) -> list[str]:
    """Resolve the frozen G2c semantic manifest names to marker families."""
    values = list(families)
    if not _is_g2c_campaign(campaign_name):
        return values
    if values != list(_G2C_SEMANTIC_TO_STRUCTURAL_FAMILY):
        raise IncompleteCampaign("G2c semantic emission-family census disagrees")
    return [_G2C_SEMANTIC_TO_STRUCTURAL_FAMILY[value] for value in values]


def _derive_attempt_summary(
    spec: FrozenSpec, stdout: bytes, invocation: Mapping[str, Any], *,
    campaign_name: str,
    implementation_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Derive every structural summary field from captured bytes and frozen input."""
    try:
        parsed = parse_runner_stdout(
            spec, stdout, implementation_manifest_path=implementation_manifest_path
        )
        if _is_g2h_campaign(campaign_name) or _is_g2x_campaign(campaign_name):
            raise IncompleteCampaign("G2h/G2x campaign verification is outside the public execution lane")
        elif _is_g2c_campaign(campaign_name):
            from born_ladder.snapshot.g2c_collector_structural import (
                reconstruct_g2c_collector_record,
            )
            reconstructed = reconstruct_g2c_collector_record(
                spec, stdout, invocation,
                implementation_manifest_path=implementation_manifest_path,
            )
        else:
            reconstructed = reconstruct_collector_record(
                spec, stdout, invocation,
                implementation_manifest_path=implementation_manifest_path,
            )
        if parsed.manifest != reconstructed:
            raise IncompleteCampaign("runner and independent collector manifests disagree")
        expected_families = _structural_families_for_campaign(
            campaign_name, invocation["required_emission_families"]
        )
        observed_families = parsed.manifest["emitted_families"]
        return {
            "duplicate_counts": _duplicate_counts(reconstructed),
            "emitted_counts": copy.deepcopy(reconstructed["engine_declared_counts"]),
            "expected_observed_id_differences": {
                "extra": [
                    family for family in observed_families
                    if family not in expected_families
                    and family != "KEY_SEQUENTIAL_PROBE_JSON"
                ],
                "missing": [family for family in expected_families if family not in observed_families],
            },
            "parse_failures": [],
        }
    except IncompleteCampaign as error:
        count_keys = spec.get(
            "/completeness/structural_end_record/ordered_structural_manifest/properties/engine_declared_counts/keys",
            expected_type=list,
        )
        return {
            "duplicate_counts": {
                "invocation_ids": 0, "runner_context_ids": 0, "unit_identities": 0,
            },
            "emitted_counts": {key: 0 for key in count_keys},
            "expected_observed_id_differences": {
                "extra": [],
                "missing": _structural_families_for_campaign(
                    campaign_name, invocation["required_emission_families"]
                ),
            },
            "parse_failures": [error.message],
        }


def validate_structural_metadata(spec: FrozenSpec, record: Mapping[str, Any]) -> None:
    contract = spec.get(
        "/completeness/structural_end_record/ordered_structural_manifest",
        expected_type=dict,
    )
    from born_ladder.snapshot.runner_structural import _validate_shape
    _validate_shape(dict(record), contract, "/ordered_structural_manifest")


def structural_manifest_bytes(
    spec: FrozenSpec, records: Sequence[Mapping[str, Any]]
) -> bytes:
    if not records:
        raise IncompleteCampaign("structural manifest is empty")
    for record in records:
        validate_structural_metadata(spec, record)
    return b"".join(canonical_json_bytes(dict(record)) for record in records)


@dataclass(frozen=True)
class _StructuralAcceptanceTrust:
    allowed_signers_path: Path

    principal: str

    allowed_signers_sha256: str



def _production_acceptance_trust(
    spec: FrozenSpec, implementation_manifest_path: Path | None = None
) -> _StructuralAcceptanceTrust:
    spec.audit_implementation_manifest(
        "completeness", manifest_path=implementation_manifest_path,
        declared_pointers=_IMPLEMENTATION_POINTERS,
    )
    attestation = spec.get("/identity/attestation", expected_type=dict)
    principal = attestation["signer_principal"]
    allowed_hash = attestation["allowed_signers_sha256"]
    relative = Path(attestation["allowed_signers_path"])
    if relative.is_absolute():
        raise IncompleteCampaign("signed specification structural trust identity is invalid")
    allowed_path = spec.history.path(relative.as_posix(), expected_sha256=allowed_hash)
    try:
        allowed_path.relative_to(spec.history.root)
        allowed_raw = allowed_path.read_bytes()
    except (ValueError, OSError) as error:
        raise IncompleteCampaign(f"frozen allowed-signers file unavailable: {error}") from error
    if sha256_bytes(allowed_raw) != allowed_hash:
        raise IncompleteCampaign("frozen allowed-signers hash disagrees with signed specification")
    return _StructuralAcceptanceTrust(allowed_path, principal, allowed_hash)


@dataclass(frozen=True)
class _StructuralChannel:
    origin_path: Path

    origin_sha256: str

    builder_path: Path

    builder_sha256: str

    manifest_bytes: bytes

    manifest_sha256: str

    linked_origins: tuple[tuple[Path, str], ...]



class _CurrentBuilderAcceptanceEraSpec:
    """Serve historical constants while auditing the current production builders."""

    def __init__(self, historical: FrozenSpec, current: FrozenSpec) -> None:
        self._historical = historical
        self._current = current

    def __getattr__(self, name: str) -> Any:
        return getattr(self._historical, name)

    def audit_implementation_manifest(self, *args: Any, **kwargs: Any) -> str:
        return self._current.audit_implementation_manifest(*args, **kwargs)



def _load_acceptance_era_spec(
    spec: FrozenSpec, acceptance_spec_hash: str
) -> FrozenSpec:
    """Resolve one acceptance era solely by its signed hash and prior registry."""
    if type(spec) is not FrozenSpec or spec.loader_role != "default":
        raise IncompleteCampaign("historical acceptance requires the default signed specification")
    if not isinstance(acceptance_spec_hash, str) or not _HEX64.fullmatch(
        acceptance_spec_hash
    ):
        raise IncompleteCampaign("signed acceptance spec_hash is malformed")
    spec.audit_implementation_manifest(
        "completeness", declared_pointers=_IMPLEMENTATION_POINTERS
    )
    prior = spec.get(
        _IMPLEMENTATION_POINTERS["prior_freeze_identities_contract"],
        expected_type=list,
    )
    if not prior:
        raise IncompleteCampaign("signed prior-identity registry is empty")
    seen_companions: set[str] = set()
    seen_tags: set[str] = set()
    verified: list[FrozenSpec] = []
    for ordinal, identity in enumerate(prior):
        if (
            not isinstance(identity, dict)
            or set(identity) != {"companion", "tag"}
            or not all(isinstance(value, str) and value for value in identity.values())
        ):
            raise IncompleteCampaign(
                f"signed prior-identity entry {ordinal} is not closed"
            )
        companion = identity["companion"]
        tag = identity["tag"]
        if companion in seen_companions or tag in seen_tags:
            raise IncompleteCampaign("signed prior-identity registry repeats an identity")
        seen_companions.add(companion)
        seen_tags.add(tag)
        companion_path = spec.history.path(companion)
        try:
            companion_path.relative_to(spec.history.root)
            raw = companion_path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
            payload_identity = payload["identity"]
            spec_id = payload_identity["spec_id"]
            self_sha256 = payload_identity["json_sha256"]
        except (
            OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError,
            KeyError, TypeError,
        ) as error:
            raise IncompleteCampaign(
                f"signed prior companion {ordinal} is unavailable or invalid: {error}"
            ) from error
        if not isinstance(spec_id, str) or not isinstance(self_sha256, str):
            raise IncompleteCampaign("signed prior companion identity fields are invalid")
        try:
            verified.append(FrozenSpec._load_attested(
                companion_path,
                repo_root=spec.repo_root,
                historical_root=spec.history.root,
                expected_companion=companion,
                expected_spec_id=spec_id,
                expected_tag=tag,
                expected_json_sha256=sha256_bytes(raw),
                expected_self_sha256=self_sha256,
                require_checked_out_markdown=False,
                loader_role="structural_acceptance_era",
            ))
        except SpecMismatch as error:
            raise IncompleteCampaign(
                f"signed prior identity {ordinal} failed verification: {error}"
            ) from error
    matches = [
        candidate for candidate in verified
        if candidate.attestation.json_sha256 == acceptance_spec_hash
    ]
    if len(matches) != 1:
        raise IncompleteCampaign(
            "signed acceptance spec_hash does not select exactly one verified prior identity"
        )
    return matches[0]


def _capture_inventory(capture_root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    type_counts = {"attempt_sidecar": 0, "stderr": 0, "stdout": 0}
    try:
        children = sorted(
            capture_root.rglob("*"),
            key=lambda path: path.relative_to(capture_root).as_posix().encode(),
        )
    except OSError as error:
        raise IncompleteCampaign(f"accepted capture inventory is unavailable: {error}") from error
    for path in children:
        if path.is_symlink():
            raise IncompleteCampaign("accepted capture inventory contains a symlink")
        if not path.is_file():
            continue
        relative = path.relative_to(capture_root).as_posix()
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise IncompleteCampaign(f"accepted capture child is unavailable: {error}") from error
        rows.append({
            "path": relative, "sha256": sha256_bytes(raw), "size_bytes": len(raw),
        })
        if relative.endswith(".attempt.json"):
            type_counts["attempt_sidecar"] += 1
        elif relative.endswith(".stderr.bin"):
            type_counts["stderr"] += 1
        elif relative.endswith(".stdout.bin"):
            type_counts["stdout"] += 1
        else:
            raise IncompleteCampaign("accepted capture inventory has an additional child type")
    return {
        "file_count": len(rows),
        "sha256": sha256_bytes(canonical_json_bytes(rows)),
        "total_size_bytes": sum(row["size_bytes"] for row in rows),
        "type_counts": type_counts,
    }


def _historical_acceptance_identity_key(
    spec: FrozenSpec,
    *,
    campaign_name: str,
    census_sha256: str,
    runner_capture_path: Path,
    collector_capture_path: Path,
    structural_manifest_path: Path,
    invocation_manifest_path: Path,
    attempt_registry: AttemptRegistry,
    manager_acceptance_path: Path,
    manager_acceptance_signature_path: Path,
) -> str | None:
    """Select only an exact signed-v14 accepted-existing-evidence identity."""
    if type(spec) is not FrozenSpec or spec.loader_role != "default":
        return None
    spec.audit_implementation_manifest(
        "completeness", declared_pointers=_IMPLEMENTATION_POINTERS
    )
    accepted_all = spec.get(
        _IMPLEMENTATION_POINTERS["accepted_existing_evidence_contract"],
        expected_type=dict,
    )
    if set(accepted_all) != {"h1_h2", "h4"}:
        raise IncompleteCampaign("signed accepted-existing-evidence registry is not closed")
    root = (
        spec.repo_root / spec.get("/artifact_paths/namespace", expected_type=str)
    ).resolve()
    candidates: list[str] = []
    for key, expected_campaign in (("h1_h2", "g2h_h1_h2_v2"), ("h4", "g2h_h4_v2")):
        accepted = accepted_all[key]
        if campaign_name != expected_campaign or not isinstance(accepted, dict):
            continue
        identity_fields = {
            "acceptance_payload": manager_acceptance_path,
            "acceptance_signature": manager_acceptance_signature_path,
            "collector_capture": collector_capture_path,
            "invocation_manifest": invocation_manifest_path,
            "registry": attempt_registry._evidence_path,
            "runner_capture": runner_capture_path,
            "structural_manifest": structural_manifest_path,
        }
        observed: dict[str, Any] = {}
        consistent = True
        for name, supplied_path in identity_fields.items():
            identity = accepted.get(name)
            if not isinstance(identity, dict) or set(identity) != {"path", "sha256"}:
                consistent = False
                break
            expected_path = (root / identity["path"]).resolve()
            actual_path = supplied_path.resolve()
            try:
                raw = actual_path.read_bytes()
            except OSError:
                consistent = False
                break
            observed[name] = {"path": identity["path"], "sha256": sha256_bytes(raw)}
            if actual_path != expected_path:
                consistent = False
        campaign_identity = accepted.get("campaign")
        if not isinstance(campaign_identity, dict) or set(campaign_identity) != {"path", "sha256"}:
            consistent = False
        else:
            campaign_path = (root / campaign_identity["path"]).resolve()
            try:
                campaign_raw = campaign_path.read_bytes()
            except OSError:
                consistent = False
                campaign_raw = b""
            observed["campaign"] = {
                "path": campaign_identity["path"], "sha256": sha256_bytes(campaign_raw),
            }
        if not consistent:
            continue
        capture_root = (
            root / f"{Path(campaign_identity.get('path', '')).stem}_attempts_content_addressed"
            if isinstance(campaign_identity, dict) else root / "INVALID"
        ).resolve()
        if any(
            not path.resolve().is_relative_to(capture_root)
            for path in attempt_registry._capture_hashes
        ):
            consistent = False
        observed["capture_inventory"] = _capture_inventory(capture_root)
        interpretation = accepted.get("interpretation")
        if key == "h1_h2":
            if not isinstance(interpretation, dict) or set(interpretation) != {"path", "sha256"}:
                consistent = False
            else:
                interpretation_path = (root / interpretation["path"]).resolve()
                try:
                    interpretation_raw = interpretation_path.read_bytes()
                except OSError:
                    consistent = False
                    interpretation_raw = b""
                observed["interpretation"] = {
                    "path": interpretation["path"],
                    "sha256": sha256_bytes(interpretation_raw),
                }
                if (
                    attempt_registry._interpretation_raw != interpretation_raw
                    or attempt_registry._interpretation_sha256 != sha256_bytes(interpretation_raw)
                ):
                    consistent = False
        else:
            observed["interpretation"] = None
            if interpretation is not None or attempt_registry._interpretation_raw is not None:
                consistent = False
        if census_sha256 != observed.get("invocation_manifest", {}).get("sha256"):
            consistent = False
        if consistent and observed == accepted:
            candidates.append(key)
    if len(candidates) > 1:
        raise IncompleteCampaign("multiple historical acceptance identities matched")
    return candidates[0] if candidates else None


def _require_spec_hash_only_difference(
    acceptance_channel: _StructuralChannel,
    current_channel: _StructuralChannel,
    *,
    acceptance_spec_hash: str,
    current_spec_hash: str,
) -> None:
    """Require closed channel objects to differ only at the exact era hash."""
    try:
        acceptance = json.loads(acceptance_channel.manifest_bytes.decode("utf-8"))
        current = json.loads(current_channel.manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IncompleteCampaign(f"structural channel manifest parse failure: {error}") from error
    if set(acceptance) != set(current):
        raise IncompleteCampaign("acceptance/current structural channel keysets disagree")
    if (
        acceptance.get("spec_hash") != acceptance_spec_hash
        or current.get("spec_hash") != current_spec_hash
    ):
        raise IncompleteCampaign("acceptance/current structural spec identities disagree")
    differences = [name for name in acceptance if acceptance[name] != current[name]]
    if differences != ["spec_hash"]:
        raise IncompleteCampaign(
            "acceptance/current structural channels differ beyond spec_hash: "
            + ", ".join(sorted(differences))
        )


def _require_signed_historical_channel(
    acceptance_channel: _StructuralChannel,
    current_channel: _StructuralChannel,
    *,
    acceptance_spec_hash: str,
    current_spec_hash: str,
    signed_manifest_sha256: str,
) -> None:
    """Bind the narrow comparison to the immutable signed channel digest."""
    _require_spec_hash_only_difference(
        acceptance_channel,
        current_channel,
        acceptance_spec_hash=acceptance_spec_hash,
        current_spec_hash=current_spec_hash,
    )
    if acceptance_channel.manifest_sha256 != signed_manifest_sha256:
        raise IncompleteCampaign("acceptance-era structural channel hash disagrees with signature")


def _load_persisted_structural_manifest(
    spec: FrozenSpec,
    path: Path,
    records: Sequence[Mapping[str, Any]],
    *,
    campaign_name: str,
) -> tuple[bytes, str]:
    expected_path = _expected_structural_manifest_path(spec, campaign_name)
    if path.resolve() != expected_path:
        raise IncompleteCampaign("structural manifest does not use its frozen path")
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise IncompleteCampaign(f"persisted structural manifest unavailable: {error}") from error
    expected = structural_manifest_bytes(spec, records)
    if raw != expected:
        raise IncompleteCampaign(
            "persisted structural manifest differs from independently established records"
        )
    lines = raw.splitlines(keepends=True)
    if len(lines) != len(records) or any(not line.endswith(b"\n") for line in lines):
        raise IncompleteCampaign("persisted structural manifest is not ordered JSONL")
    parsed: list[dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise IncompleteCampaign(f"structural JSONL parse failure: {error}") from error
        if not isinstance(value, dict) or canonical_json_bytes(value) != line:
            raise IncompleteCampaign("structural manifest line is not canonical JSON")
        parsed.append(value)
    if parsed != [dict(record) for record in records]:
        raise IncompleteCampaign("structural manifest ordering or content disagrees")
    return raw, sha256_bytes(raw)


def _expected_structural_manifest_path(spec: FrozenSpec, campaign_name: str) -> Path:
    pattern = spec.get("/artifact_paths/structural_manifest_pattern", expected_type=str)
    if campaign_name == "g2h_h3_v13_reexecution":
        transport = spec.get(
            _IMPLEMENTATION_POINTERS["g2h_v13_transport_contract"],
            expected_type=dict,
        )
        matches = [
            item for item in transport.get("transport_paths", [])
            if isinstance(item, str) and item.endswith("_structural_manifest.jsonl")
        ]
        if matches != ["rb1v2_g2h_h3_v13_structural_manifest.jsonl"]:
            raise SpecMismatch("frozen v13 structural-manifest identity disagrees")
        expected_name = matches[0]
    elif campaign_name == "g2x_confirm_v2":
        plan = spec.get(
            _IMPLEMENTATION_POINTERS["g2x_v20_reproduction_plan"],
            expected_type=dict,
        )
        artifacts = plan.get("artifacts")
        if (
            plan.get("campaign_id") != "g2x_confirm_v20_reexecution"
            or not isinstance(artifacts, list)
            or len(artifacts) != 10
            or artifacts[2] != "rb1v2_g2x_confirm_v20_structural_manifest.jsonl"
        ):
            raise SpecMismatch("frozen v20 G2x structural-manifest identity disagrees")
        expected_name = artifacts[2]
    elif campaign_name == "g2c_v2":
        plan = spec.get(
            _IMPLEMENTATION_POINTERS["g2c_v21_reproduction_plan"],
            expected_type=dict,
        )
        artifacts = plan.get("artifacts")
        if (
            not isinstance(artifacts, list)
            or len(artifacts) != 10
            or artifacts[2] != "rb1v2_g2c_structural_manifest.jsonl"
        ):
            raise SpecMismatch("frozen v21 G2c structural-manifest identity disagrees")
        expected_name = artifacts[2]
    else:
        expected_name = pattern.replace("<stage>", campaign_name.removesuffix("_v2"))
    namespace = spec.get("/artifact_paths/namespace", expected_type=str)
    return (spec.repo_root / namespace).resolve() / expected_name


@dataclass(frozen=True)
class _ProductionGatePaths:
    acceptance: Path

    signature: Path

    implementation_manifest: Path



def _production_gate_paths(
    spec: FrozenSpec, campaign_name: str
) -> _ProductionGatePaths:
    """Derive every production-only gate path from frozen identities."""
    spec.audit_implementation_manifest(
        "completeness", declared_pointers=_IMPLEMENTATION_POINTERS
    )
    root = (
        spec.repo_root / spec.get("/artifact_paths/namespace", expected_type=str)
    ).resolve()
    structural_path = _expected_structural_manifest_path(spec, campaign_name)
    accepted_all = spec.get(
        _IMPLEMENTATION_POINTERS["accepted_existing_evidence_contract"],
        expected_type=dict,
    )
    matched = []
    for identity in accepted_all.values():
        if not isinstance(identity, dict):
            raise IncompleteCampaign("frozen accepted-evidence identity is invalid")
        structural = identity.get("structural_manifest")
        if (
            isinstance(structural, dict)
            and structural.get("path") == structural_path.name
        ):
            matched.append(identity)
    if len(matched) > 1:
        raise IncompleteCampaign("frozen gate path resolves multiple accepted identities")
    if matched:
        identity = matched[0]
        acceptance_identity = identity.get("acceptance_payload")
        signature_identity = identity.get("acceptance_signature")
        if not all(
            isinstance(value, dict) and set(value) == {"path", "sha256"}
            for value in (acceptance_identity, signature_identity)
        ):
            raise IncompleteCampaign("frozen accepted gate paths are not closed")
        acceptance = (root / acceptance_identity["path"]).resolve()
        signature = (root / signature_identity["path"]).resolve()
    elif campaign_name == "g2h_h3_v13_reexecution":
        transport = spec.get(
            _IMPLEMENTATION_POINTERS["g2h_v13_transport_contract"],
            expected_type=dict,
        )
        paths = transport.get("transport_paths")
        if not isinstance(paths, list):
            raise IncompleteCampaign("frozen v13 transport paths are unavailable")
        acceptance_names = [
            value for value in paths
            if isinstance(value, str)
            and value.endswith("_structural_acceptance.json")
        ]
        signature_names = [
            value for value in paths
            if isinstance(value, str)
            and value.endswith("_structural_acceptance.json.sig")
        ]
        if len(acceptance_names) != 1 or len(signature_names) != 1:
            raise IncompleteCampaign("frozen v13 gate paths are not unique")
        acceptance = (root / acceptance_names[0]).resolve()
        signature = (root / signature_names[0]).resolve()
    elif campaign_name == "g2x_confirm_v2":
        plan = spec.get(
            _IMPLEMENTATION_POINTERS["g2x_v20_reproduction_plan"],
            expected_type=dict,
        )
        artifacts = plan.get("artifacts")
        if not isinstance(artifacts, list) or len(artifacts) != 10:
            raise IncompleteCampaign("frozen v20 G2x gate paths are unavailable")
        acceptance = (root / artifacts[3]).resolve()
        signature = (root / artifacts[4]).resolve()
    elif campaign_name == "g2c_v2":
        plan = spec.get(
            _IMPLEMENTATION_POINTERS["g2c_v21_reproduction_plan"],
            expected_type=dict,
        )
        artifacts = plan.get("artifacts")
        if not isinstance(artifacts, list) or len(artifacts) != 10:
            raise IncompleteCampaign("frozen v21 G2c gate paths are unavailable")
        acceptance = (root / artifacts[3]).resolve()
        signature = (root / artifacts[4]).resolve()
    else:
        manifest_name = spec.get(
            "/completeness/structural_gate/manifest_name", expected_type=str
        )
        stage = campaign_name.removesuffix("_v2")
        if manifest_name.replace("<stage>", stage) != structural_path.name:
            raise IncompleteCampaign("frozen structural gate naming contracts disagree")
        suffix = "_structural_manifest.jsonl"
        if not structural_path.name.endswith(suffix):
            raise IncompleteCampaign("frozen structural manifest suffix disagrees")
        acceptance = structural_path.with_name(
            structural_path.name.removesuffix(suffix)
            + "_structural_acceptance.json"
        ).resolve()
        signature = Path(f"{acceptance}.sig").resolve()
    implementation = spec.history.path(IMPLEMENTATION_MANIFEST.as_posix())
    for path in (acceptance, signature):
        try:
            path.relative_to(spec.repo_root.resolve())
        except ValueError as error:
            raise IncompleteCampaign("frozen production gate path escapes repository") from error
    return _ProductionGatePaths(acceptance, signature, implementation)


def _load_invocation_records(
    path: Path, expected_sha256: str
) -> list[dict[str, Any]]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IncompleteCampaign(f"invocation manifest unavailable or invalid: {error}") from error
    if (
        sha256_bytes(raw) != expected_sha256 or not isinstance(value, list)
        or not value or canonical_json_bytes(value) != raw
        or any(not isinstance(item, dict) for item in value)
    ):
        raise IncompleteCampaign("invocation manifest canonical bytes/census disagree")
    ids = [item.get("invocation_id") for item in value]
    if len(ids) != len(set(ids)):
        raise IncompleteCampaign("invocation manifest repeats invocation IDs")
    return value


def _verify_acceptance_signature(
    acceptance_raw: bytes,
    signature_path: Path,
    trust: _StructuralAcceptanceTrust,
) -> None:
    try:
        allowed_raw = trust.allowed_signers_path.read_bytes()
    except OSError as error:
        raise IncompleteCampaign(f"cannot read frozen allowed-signers file: {error}") from error
    if sha256_bytes(allowed_raw) != trust.allowed_signers_sha256:
        raise IncompleteCampaign("frozen allowed-signers hash disagrees before signature verification")
    try:
        completed = subprocess.run(
            [
                "ssh-keygen", "-Y", "verify", "-f", str(trust.allowed_signers_path),
                "-I", trust.principal, "-n", STRUCTURAL_ACCEPTANCE_NAMESPACE,
                "-s", str(signature_path),
            ],
            input=acceptance_raw,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except OSError as error:
        raise IncompleteCampaign(f"cannot verify structural acceptance signature: {error}") from error
    if completed.returncode != 0:
        detail = completed.stdout.decode("utf-8", errors="replace").strip()
        raise IncompleteCampaign(f"structural acceptance signature invalid: {detail}")


def _load_structural_channel(
    spec: FrozenSpec,
    *,
    channel: str,
    capture_path: Path,
    structural_manifest_path: Path,
    invocation_records: Sequence[Mapping[str, Any]],
    campaign_name: str,
    census_sha256: str,
    implementation_manifest_path: Path | None,
) -> tuple[_StructuralChannel, list[dict[str, Any]]]:
    if channel == "runner":
        consumer = "runner_structural"
        parser = lambda payload: parse_runner_capture_bundle(
            spec, payload, implementation_manifest_path=implementation_manifest_path
        )
        builder_name = "scripts/rebuild1/runner_structural.py"
    elif channel == "collector":
        if _is_g2h_campaign(campaign_name) or _is_g2x_campaign(campaign_name):
            raise IncompleteCampaign("G2h/G2x campaign verification is outside the public execution lane")
        elif _is_g2c_campaign(campaign_name):
            from born_ladder.snapshot.g2c_collector_structural import (
                parse_g2c_collector_capture_bundle,
            )
            consumer = "g2c_collector_structural"
            parser = lambda payload: parse_g2c_collector_capture_bundle(
                spec, payload, invocation_records,
                implementation_manifest_path=implementation_manifest_path,
            )
            builder_name = "scripts/rebuild1/g2c_collector_structural.py"
        else:
            consumer = "collector_structural"
            parser = lambda payload: parse_collector_capture_bundle(
                spec, payload, invocation_records,
                implementation_manifest_path=implementation_manifest_path,
            )
            builder_name = "scripts/rebuild1/collector_structural.py"
    else:
        raise IncompleteCampaign(f"unknown structural channel {channel}")
    spec.audit_implementation_manifest(
        consumer, manifest_path=implementation_manifest_path,
        declared_pointers=_STRUCTURAL_IMPLEMENTATION_POINTERS[consumer],
    )
    try:
        raw = capture_path.read_bytes()
        manifest_raw = (getattr(spec, "_replay_implementation_manifest_raw", None)
            or spec.history.read("scripts/rebuild1/implementation_manifest.jsonl"))
        pins = {json.loads(line)["source_sha256"] for line in manifest_raw.splitlines()
                if json.loads(line)["source_path"] == builder_name}
        if len(pins) != 1:
            raise IncompleteCampaign("archived structural builder has no unique source commitment")
        builder_path = spec.history.path(builder_name, expected_sha256=pins.pop())
        builder_bytes = builder_path.read_bytes()
    except OSError as error:
        raise IncompleteCampaign(f"{channel} structural channel unavailable: {error}") from error
    origin_sha256 = sha256_bytes(raw)
    if capture_path.name != f"{origin_sha256}.json":
        raise IncompleteCampaign(f"{channel} structural capture path is not content-addressed")
    parsed = parser(raw)
    records = list(parsed.records)
    for record in records:
        validate_structural_metadata(spec, record)
    persisted_records, records_sha256 = _load_persisted_structural_manifest(
        spec, structural_manifest_path, records, campaign_name=campaign_name
    )
    if [record["invocation_id"] for record in records] != [
        record["invocation_id"] for record in invocation_records
    ]:
        raise IncompleteCampaign("structural manifest order differs from frozen census")
    builder_sha256 = sha256_bytes(builder_bytes)
    manifest_bytes = canonical_json_bytes({
        "builder": {
            "path": builder_name,
            "sha256": builder_sha256,
        },
        "campaign": campaign_name,
        "census_sha256": census_sha256,
        "channel": channel,
        "origin": {"path": str(capture_path.resolve()), "sha256": origin_sha256},
        "records_sha256": records_sha256,
        "structural_manifest": {
            "path": str(structural_manifest_path.resolve()),
            "sha256": records_sha256,
        },
        "spec_hash": spec.attestation.json_sha256,
    })
    return _StructuralChannel(
        capture_path.resolve(), origin_sha256, builder_path, builder_sha256,
        manifest_bytes, sha256_bytes(manifest_bytes), parsed.origins,
    ), records


class StructuralGate:
    __slots__ = (
        "_acceptance_collector", "_acceptance_era_attestation",
        "_acceptance_bytes", "_acceptance_fields", "_acceptance_path",
        "_acceptance_runner", "_acceptance_sha256", "_attempt_registry",
        "_campaign", "_census_sha256", "_collector", "_collector_capture_path",
        "_historical_identity_key", "_implementation_manifest_path",
        "_invocation_manifest_path",
        "_manifest_sha256", "_records_bytes", "_runner", "_sealed",
        "_runner_capture_path", "_production_paths_fixed",
        "_signature_path", "_signature_sha256", "_spec_hash", "_trust",
        "_stdout_bindings", "_structural_manifest_path",
        "_structural_manifest_sha256",
    )

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("StructuralGate is immutable")
        object.__setattr__(self, name, value)

    def __init__(
        self,
        *,
        runner: _StructuralChannel,
        collector: _StructuralChannel,
        acceptance_runner: _StructuralChannel | None,
        acceptance_collector: _StructuralChannel | None,
        acceptance_era_attestation: Any | None,
        historical_identity_key: str | None,
        records_bytes: bytes,
        campaign: str,
        census_sha256: str,
        spec_hash: str,
        acceptance_path: Path,
        acceptance_bytes: bytes,
        acceptance_fields: Mapping[str, Any],
        signature_path: Path,
        signature_sha256: str,
        trust: _StructuralAcceptanceTrust,
        manifest_sha256: str,
        stdout_bindings: Sequence[Mapping[str, str]],
        structural_manifest_path: Path,
        structural_manifest_sha256: str,
        runner_capture_path: Path,
        collector_capture_path: Path,
        invocation_manifest_path: Path,
        attempt_registry: AttemptRegistry,
        implementation_manifest_path: Path | None,
        production_paths_fixed: bool,
        token: object,
    ) -> None:
        if token is not _STRUCTURAL_TOKEN:
            raise IncompleteCampaign("structural gate was not independently verified")
        self._runner = runner
        self._collector = collector
        self._acceptance_runner = acceptance_runner
        self._acceptance_collector = acceptance_collector
        self._acceptance_era_attestation = acceptance_era_attestation
        self._historical_identity_key = historical_identity_key
        self._records_bytes = records_bytes
        self._campaign = campaign
        self._census_sha256 = census_sha256
        self._spec_hash = spec_hash
        self._acceptance_path = acceptance_path
        self._acceptance_bytes = acceptance_bytes
        self._acceptance_sha256 = sha256_bytes(acceptance_bytes)
        self._acceptance_fields = copy.deepcopy(dict(acceptance_fields))
        self._signature_path = signature_path
        self._signature_sha256 = signature_sha256
        self._trust = trust
        self._manifest_sha256 = manifest_sha256
        self._stdout_bindings = tuple(copy.deepcopy(dict(item)) for item in stdout_bindings)
        self._structural_manifest_path = structural_manifest_path
        self._structural_manifest_sha256 = structural_manifest_sha256
        self._runner_capture_path = runner_capture_path
        self._collector_capture_path = collector_capture_path
        self._invocation_manifest_path = invocation_manifest_path
        self._attempt_registry = attempt_registry
        self._implementation_manifest_path = implementation_manifest_path
        self._production_paths_fixed = production_paths_fixed
        self._sealed = True

    def records_for(
        self, spec: FrozenSpec, campaign_name: str, census_sha256: str
    ) -> list[dict[str, Any]]:
        if (
            self._campaign != campaign_name
            or self._census_sha256 != census_sha256
            or self._spec_hash != spec.attestation.json_sha256
        ):
            raise IncompleteCampaign("structural gate campaign/spec/census binding disagrees")
        acceptance_runner = self._runner
        acceptance_collector = self._collector
        acceptance_spec_hash = spec.attestation.json_sha256
        if self._production_paths_fixed:
            fixed_paths = _production_gate_paths(spec, campaign_name)
            if (
                self._acceptance_path != fixed_paths.acceptance
                or self._signature_path != fixed_paths.signature
                or self._implementation_manifest_path
                != fixed_paths.implementation_manifest
            ):
                raise IncompleteCampaign(
                    "production structural gate paths changed after loading"
                )
        if self._historical_identity_key is not None:
            selected = self._historical_identity_key
            if self._historical_identity_key == "h3_v13":
                selected = (
                    "h3_v13"
                    if self._attempt_registry._acceptance_era_spec_hash
                    == self._acceptance_fields["spec_hash"]
                    else None
                )
            elif self._historical_identity_key != "g2a":
                selected = _historical_acceptance_identity_key(
                    spec,
                    campaign_name=campaign_name,
                    census_sha256=census_sha256,
                    runner_capture_path=self._runner_capture_path,
                    collector_capture_path=self._collector_capture_path,
                    structural_manifest_path=self._structural_manifest_path,
                    invocation_manifest_path=self._invocation_manifest_path,
                    attempt_registry=self._attempt_registry,
                    manager_acceptance_path=self._acceptance_path,
                    manager_acceptance_signature_path=self._signature_path,
                )
            if selected != self._historical_identity_key:
                raise IncompleteCampaign("historical acceptance identity changed after loading")
            if not self._production_paths_fixed:
                raise IncompleteCampaign(
                    "historical acceptance requires the fixed production route"
                )
            acceptance_spec = _load_acceptance_era_spec(
                spec, self._acceptance_fields["spec_hash"]
            )
            if acceptance_spec.attestation != self._acceptance_era_attestation:
                raise IncompleteCampaign(
                    "signed acceptance-era identity changed after loading"
                )
            invocation_records = _load_invocation_records(
                self._invocation_manifest_path, census_sha256
            )
            current_channels: list[_StructuralChannel] = []
            current_records: list[list[dict[str, Any]]] = []
            acceptance_channels: list[_StructuralChannel] = []
            acceptance_records: list[list[dict[str, Any]]] = []
            acceptance_view = _CurrentBuilderAcceptanceEraSpec(acceptance_spec, spec)
            for channel, capture_path in (
                ("runner", self._runner_capture_path),
                ("collector", self._collector_capture_path),
            ):
                current_channel, current_rows = _load_structural_channel(
                    spec,
                    channel=channel,
                    capture_path=capture_path,
                    structural_manifest_path=self._structural_manifest_path,
                    invocation_records=invocation_records,
                    campaign_name=campaign_name,
                    census_sha256=census_sha256,
                    implementation_manifest_path=self._implementation_manifest_path,
                )
                old_channel, old_rows = _load_structural_channel(
                    acceptance_view,
                    channel=channel,
                    capture_path=capture_path,
                    structural_manifest_path=self._structural_manifest_path,
                    invocation_records=invocation_records,
                    campaign_name=campaign_name,
                    census_sha256=census_sha256,
                    implementation_manifest_path=self._implementation_manifest_path,
                )
                _require_signed_historical_channel(
                    old_channel,
                    current_channel,
                    acceptance_spec_hash=acceptance_spec.attestation.json_sha256,
                    current_spec_hash=spec.attestation.json_sha256,
                    signed_manifest_sha256=self._acceptance_fields[
                        f"{channel}_manifest_sha256"
                    ],
                )
                current_channels.append(current_channel)
                current_records.append(current_rows)
                acceptance_channels.append(old_channel)
                acceptance_records.append(old_rows)
            if not (
                current_records[0] == current_records[1]
                == acceptance_records[0] == acceptance_records[1]
            ):
                raise IncompleteCampaign("dual-era structural records disagree")
            if (
                current_channels[0] != self._runner
                or current_channels[1] != self._collector
                or acceptance_channels[0] != self._acceptance_runner
                or acceptance_channels[1] != self._acceptance_collector
            ):
                raise IncompleteCampaign("dual-era structural identity changed after loading")
            acceptance_runner, acceptance_collector = acceptance_channels
            acceptance_spec_hash = acceptance_spec.attestation.json_sha256
            self._attempt_registry.require_binding(spec, campaign_name, census_sha256)
        for channel in (self._runner, self._collector):
            try:
                origin = channel.origin_path.read_bytes()
                builder = channel.builder_path.read_bytes()
            except OSError as error:
                raise IncompleteCampaign(f"structural channel changed or disappeared: {error}") from error
            if sha256_bytes(origin) != channel.origin_sha256:
                raise IncompleteCampaign("structural origin changed after gate construction")
            if sha256_bytes(builder) != channel.builder_sha256:
                raise IncompleteCampaign("structural parser changed after gate construction")
            if sha256_bytes(channel.manifest_bytes) != channel.manifest_sha256:
                raise IncompleteCampaign("structural channel manifest hash disagrees")
            for linked_path, linked_sha256 in channel.linked_origins:
                try:
                    linked_raw = linked_path.read_bytes()
                except OSError as error:
                    raise IncompleteCampaign(f"structural linked origin disappeared: {error}") from error
                if sha256_bytes(linked_raw) != linked_sha256:
                    raise IncompleteCampaign("structural linked origin changed after gate construction")
        for binding in self._stdout_bindings:
            path = Path(binding["stdout_path"])
            try:
                raw = path.read_bytes()
            except OSError as error:
                raise IncompleteCampaign(f"bound successful stdout disappeared: {error}") from error
            if sha256_bytes(raw) != binding["stdout_sha256"]:
                raise IncompleteCampaign("bound successful stdout changed after gate construction")
            parsed = parse_runner_stdout(spec, raw)
            if parsed.manifest["invocation_id"] != binding["invocation_id"]:
                raise IncompleteCampaign("bound successful stdout invocation changed after gate construction")
        try:
            persisted_records = self._structural_manifest_path.read_bytes()
        except OSError as error:
            raise IncompleteCampaign(f"persisted structural manifest disappeared: {error}") from error
        if (
            persisted_records != self._records_bytes
            or sha256_bytes(persisted_records) != self._structural_manifest_sha256
        ):
            raise IncompleteCampaign("persisted structural manifest changed after gate construction")
        combined_value: dict[str, Any] = {
            "collector_manifest_sha256": self._collector.manifest_sha256,
            "runner_manifest_sha256": self._runner.manifest_sha256,
            "structural_manifest_sha256": self._structural_manifest_sha256,
        }
        if self._historical_identity_key is not None:
            combined_value["acceptance_era"] = {
                "collector_manifest_sha256": acceptance_collector.manifest_sha256,
                "runner_manifest_sha256": acceptance_runner.manifest_sha256,
                "spec_hash": acceptance_spec_hash,
            }
            combined_value["current_era"] = {"spec_hash": spec.attestation.json_sha256}
        combined = sha256_bytes(canonical_json_bytes(combined_value))
        if combined != self._manifest_sha256:
            raise IncompleteCampaign("structural gate manifest SHA-256 disagrees")
        current_trust = _production_acceptance_trust(
            spec, self._implementation_manifest_path
        )
        if current_trust != self._trust:
            raise IncompleteCampaign("structural frozen trust identity changed after loading")
        try:
            acceptance_raw = self._acceptance_path.read_bytes()
            signature_raw = self._signature_path.read_bytes()
        except OSError as error:
            raise IncompleteCampaign(f"signed acceptance/signature disappeared: {error}") from error
        if acceptance_raw != self._acceptance_bytes or sha256_bytes(acceptance_raw) != self._acceptance_sha256:
            raise IncompleteCampaign("signed acceptance changed after loading")
        if sha256_bytes(signature_raw) != self._signature_sha256:
            raise IncompleteCampaign("acceptance receipt signature changed after loading")
        try:
            acceptance = json.loads(acceptance_raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise IncompleteCampaign(f"acceptance receipt reparse failed: {error}") from error
        expected_acceptance = {
            "accepted_utc": self._acceptance_fields["accepted_utc"],
            "campaign": campaign_name,
            "census_sha256": census_sha256,
            "collector_manifest_sha256": acceptance_collector.manifest_sha256,
            "runner_manifest_sha256": acceptance_runner.manifest_sha256,
            "spec_hash": acceptance_spec_hash,
        }
        if (
            acceptance != self._acceptance_fields
            or acceptance != expected_acceptance
            or set(acceptance) != MANAGER_ACCEPTANCE_FIELDS
            or canonical_json_bytes(acceptance) != acceptance_raw
        ):
            raise IncompleteCampaign("acceptance receipt fields changed or disagree with gate")
        _verify_acceptance_signature(acceptance_raw, self._signature_path, self._trust)
        records = []
        for line in self._records_bytes.splitlines(keepends=True):
            try:
                record = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise IncompleteCampaign(f"immutable structural records invalid: {error}") from error
            if not isinstance(record, dict) or canonical_json_bytes(record) != line:
                raise IncompleteCampaign("immutable structural records changed")
            records.append(record)
        return copy.deepcopy(records)

    def records_and_runner_record_sha256s_for(
        self, spec: FrozenSpec, campaign_name: str, census_sha256: str
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """Return structural records and their distinct sealed runner identities."""
        records = self.records_for(spec, campaign_name, census_sha256)
        try:
            payload = json.loads(self._runner.origin_path.read_bytes())
            entries = payload["entries"]
            result = {
                entry["record"]["ordered_structural_manifest"]["invocation_id"]:
                entry["record"]["structural_manifest_sha256"]
                for entry in entries
            }
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise IncompleteCampaign(
                f"sealed runner record identities are unavailable: {error}"
            ) from error
        if len(result) != len(entries) or set(result) != self._attempt_registry.invocation_ids():
            raise IncompleteCampaign("sealed runner record identity census disagrees")
        return records, result

    @property
    def manifest_sha256(self) -> str:
        return self._manifest_sha256



@dataclass(frozen=True)
class CompletenessReport:
    stage: str

    status: str | None

    complete: bool

    recovered_after_retry: tuple[str, ...]

    missing_invocation_ids: tuple[str, ...]

    unexpected_invocation_ids: tuple[str, ...]

    duplicate_invocation_ids: tuple[str, ...]

    violations: tuple[str, ...]

    def require_complete(self) -> None:
        if self.complete:
            return
        message = "; ".join(self.violations) or str(self.status)
        if self.status and self.status.endswith("_BLOCKED_INFRASTRUCTURE"):
            raise BlockedInfrastructure(message)
        raise IncompleteCampaign(message)



def _nested_duplicates(record: Mapping[str, Any]) -> bool:
    units = record["units"]
    unit_keys = [
        (unit["config_id"], unit["partition_id"], unit["step_id"])
        for unit in units
    ]
    contexts = [unit["runner_context_id"] for unit in units]
    return (
        len(record["emitted_families"]) != len(set(record["emitted_families"]))
        or len(unit_keys) != len(set(unit_keys))
        or len(contexts) != len(set(contexts))
        or any(
            len(unit["ordered_state_labels"]) != len(set(unit["ordered_state_labels"]))
            or any(len(labels) != len(set(labels)) for labels in unit["ordered_outcome_labels_by_kind"].values())
            or len(unit["trajectory_slots"]) != len(set(unit["trajectory_slots"]))
            for unit in units
        )
    )


def assess_completeness(
    spec: FrozenSpec,
    *,
    stage: str,
    campaign_name: str,
    expected_schema: str,
    required_emission_families: Sequence[str],
    inventory_authorization: InventoryAuthorization,
    persisted_invocation_manifest_path: Path,
    persisted_invocation_manifest_sha256: str,
    structural_gate: StructuralGate | None,
    attempt_registry: AttemptRegistry,
    campaign_artifact_path: Path | None = None,
    blocked_reasons: Sequence[str] = (),
    implementation_manifest_path: Path | None = None,
    g2c_publication_spec: FrozenSpec | None = None,
) -> CompletenessReport:
    if g2c_publication_spec is not None and (
        campaign_name != "g2c_v2"
        or getattr(g2c_publication_spec, "_g2c_source_spec", None) is not spec
        or g2c_publication_spec.repo_root != spec.repo_root
    ):
        raise SpecMismatch("G2c publication wrapper is not bound to this source")
    spec.audit_implementation_manifest(
        "completeness", manifest_path=implementation_manifest_path,
        declared_pointers=_IMPLEMENTATION_POINTERS,
    )
    incomplete_status = preemptive_status(spec, stage, "incomplete")
    blocked_status = preemptive_status(spec, stage, "blocked")
    if spec.get("/completeness/missingness/tolerance", expected_type=int) != 0:
        raise SpecMismatch("infrastructure implements only frozen zero missingness")
    expected = build_invocation_manifest(
        spec, campaign_name, expected_schema=expected_schema,
        required_emission_families=required_emission_families,
        inventory_authorization=inventory_authorization,
        implementation_manifest_path=implementation_manifest_path,
    )
    expected_bytes = invocation_manifest_bytes(expected)
    census_sha256 = sha256_bytes(expected_bytes)
    violations: list[str] = []
    blocked = [str(reason) for reason in blocked_reasons if str(reason)]
    try:
        persisted = persisted_invocation_manifest_path.read_bytes()
    except OSError as error:
        persisted = b""
        blocked.append(f"invocation manifest unavailable: {error}")
    if persisted:
        if sha256_bytes(persisted) != persisted_invocation_manifest_sha256:
            violations.append("persisted invocation manifest hash mismatch")
        if persisted != expected_bytes:
            violations.append("persisted invocation census differs from frozen regeneration")
        try:
            persisted_records = json.loads(persisted.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            persisted_records = []
            violations.append("persisted invocation manifest parse failure")
        if not isinstance(persisted_records, list) or canonical_json_bytes(persisted_records) != persisted:
            violations.append("persisted invocation manifest is not canonical")
            persisted_records = []
        for record in persisted_records:
            if not isinstance(record, dict) or not {
                "experiment", "config_or_null", "seed", "scale", "invocation_id"
            } <= set(record):
                violations.append("persisted invocation record is malformed")
                continue
            recomputed_persisted = invocation_id_for(
                spec,
                experiment=record["experiment"],
                config_or_null=record["config_or_null"],
                seed=record["seed"],
                scale=record["scale"],
            )
            if record["invocation_id"] != recomputed_persisted:
                violations.append(
                    f"mismatched persisted invocation ID {record['invocation_id']}"
                )
    else:
        violations.append("persisted invocation census is empty")
    expected_by_id = {record["invocation_id"]: record for record in expected}
    if len(expected_by_id) != len(expected):
        raise SpecMismatch("internally regenerated census contains duplicate IDs")
    expected_ids = set(expected_by_id)
    attempt_registry.require_binding(spec, campaign_name, census_sha256)
    if campaign_name == "g2h_h3_v13_reexecution":
        if campaign_artifact_path is None:
            violations.append("v13 campaign timeout channels are absent")
        else:
            try:
                from born_ladder.snapshot.timeout_checks import (
                    validate_v13_campaign_timeout_artifact,
                )
                validate_v13_campaign_timeout_artifact(
                    spec,
                    campaign_artifact_path=campaign_artifact_path,
                    attempt_registry=attempt_registry,
                    implementation_manifest_path=implementation_manifest_path,
                )
            except (IncompleteCampaign, SpecMismatch) as error:
                violations.append(str(error))
    elif campaign_name == "g2x_confirm_v2":
        plan = spec.get(
            _IMPLEMENTATION_POINTERS["g2x_v20_reproduction_plan"],
            expected_type=dict,
        )
        if plan.get("campaign_id") == "g2x_confirm_v20_reexecution":
            if campaign_artifact_path is None:
                violations.append("v20 G2x campaign timeout channels are absent")
            else:
                try:
                    from born_ladder.snapshot.x_timeout_checks import (
                        validate_v20_campaign_timeout_artifact,
                    )

                    campaign = validate_v20_campaign_timeout_artifact(
                        spec,
                        campaign_artifact_path=campaign_artifact_path,
                        implementation_manifest_path=implementation_manifest_path,
                    )
                    binding = campaign.get("attempt_registry")
                    if not isinstance(binding, dict) or set(binding) != {
                        "path", "sha256",
                    }:
                        raise IncompleteCampaign(
                            "G2x-v20 loaded attempt registry binding is malformed"
                        )
                    root = (
                        spec.repo_root
                        / spec.get("/artifact_paths/namespace", expected_type=str)
                    ).resolve()
                    bound_path = Path(binding["path"])
                    if not bound_path.is_absolute():
                        bound_path = root / bound_path
                    if (
                        bound_path.resolve() != attempt_registry.evidence_path
                        or binding["sha256"]
                        != attempt_registry.historical_evidence_sha256
                    ):
                        raise IncompleteCampaign(
                            "G2x-v20 loaded attempt registry binding disagrees"
                        )
                    attempt_registry.require_binding_identity_only()
                except (IncompleteCampaign, SpecMismatch) as error:
                    violations.append(str(error))
    elif campaign_name == "g2c_v2":
        if campaign_artifact_path is None:
            violations.append("v21 G2c campaign timeout channels are absent")
        else:
            try:
                from born_ladder.reproduction.predictive.g2c_campaign import (
                    validate_v21_campaign_timeout_artifact,
                )

                campaign = validate_v21_campaign_timeout_artifact(
                    g2c_publication_spec or spec,
                    campaign_artifact_path=campaign_artifact_path,
                    implementation_manifest_path=implementation_manifest_path,
                )
                binding = campaign.get("attempt_registry")
                if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
                    raise IncompleteCampaign(
                        "G2c-v21 loaded attempt registry binding is malformed"
                    )
                root = (
                    spec.repo_root
                    / spec.get("/artifact_paths/namespace", expected_type=str)
                ).resolve()
                bound_path = Path(binding["path"])
                if not bound_path.is_absolute():
                    bound_path = root / bound_path
                if (
                    bound_path.resolve() != attempt_registry.evidence_path
                    or binding["sha256"] != attempt_registry.historical_evidence_sha256
                ):
                    raise IncompleteCampaign(
                        "G2c-v21 loaded attempt registry binding disagrees"
                    )
                attempt_registry.require_binding_identity_only()
            except (IncompleteCampaign, SpecMismatch) as error:
                violations.append(str(error))
    structural_records = (
        []
        if structural_gate is None
        else structural_gate.records_for(spec, campaign_name, census_sha256)
    )
    if structural_gate is None:
        violations.append("independent structural manifests or acceptance receipt absent")
    structural_by_id: dict[str, list[dict[str, Any]]] = {}
    for record in structural_records:
        structural_by_id.setdefault(record["invocation_id"], []).append(record)
    structural_ids = set(structural_by_id)
    attempt_ids = attempt_registry.invocation_ids()
    missing = sorted((expected_ids - structural_ids) | (expected_ids - attempt_ids))
    unexpected = sorted((structural_ids | attempt_ids) - expected_ids)
    duplicates = sorted(invocation_id for invocation_id, records in structural_by_id.items() if len(records) > 1)
    if missing:
        violations.append(f"missing invocation IDs: {missing}")
    if unexpected:
        violations.append(f"unexpected invocation IDs: {unexpected}")
    if duplicates:
        violations.append(f"duplicate invocation IDs: {duplicates}")
    recovered: list[str] = []
    expected_runner_hash = spec.get("/provenance/candidate_pins/runner_binary_sha256", expected_type=str)
    for invocation_id in sorted(expected_ids):
        expected_record = expected_by_id[invocation_id]
        recomputed = invocation_id_for(
            spec, experiment=expected_record["experiment"],
            config_or_null=expected_record["config_or_null"], seed=expected_record["seed"],
            scale=expected_record["scale"],
        )
        if recomputed != invocation_id:
            violations.append(f"mismatched invocation ID {invocation_id}")
        attempts = attempt_registry.attempts_for(invocation_id)
        retry_identity = attempt_registry.retry_identity_for(invocation_id)
        if attempts:
            final = attempts[-1]
            if final["argv"] != expected_record["argv"]:
                violations.append(f"attempt argv mismatch for {invocation_id}")
            if retry_identity is None or retry_identity.seed != expected_record["seed"]:
                violations.append(f"attempt seed mismatch for {invocation_id}")
            if retry_identity is None or retry_identity.runner_binary_sha256 != expected_runner_hash:
                violations.append(f"attempt runner mismatch for {invocation_id}")
            success = (
                final["return_code"] == 0 and not final["timeout"] and not final["parse_failures"]
                and not final["expected_observed_id_differences"]["missing"]
                and not final["expected_observed_id_differences"]["extra"]
                and all(count == 0 for count in final["duplicate_counts"].values())
            )
            if not success:
                violations.append(f"final attempt failed for {invocation_id}")
            elif len(attempts) == 2:
                recovered.append(invocation_id)
        records = structural_by_id.get(invocation_id, [])
        if len(records) == 1:
            record = records[0]
            structural_families = _structural_families_for_campaign(
                campaign_name, required_emission_families
            )
            if record["required_families"] != structural_families:
                violations.append(f"emission-family mismatch for {invocation_id}")
            if any(family not in record["emitted_families"] for family in structural_families):
                violations.append(f"missing required emission for {invocation_id}")
            if not record["units"]:
                violations.append(f"empty structural unit census for {invocation_id}")
            if _nested_duplicates(record):
                violations.append(f"nested duplicate IDs for {invocation_id}")
            if record["engine_declared_counts"]["units"] != len(record["units"]):
                violations.append(f"engine unit count mismatch for {invocation_id}")
    if blocked:
        violations.extend(f"blocked: {reason}" for reason in blocked)
        status: str | None = blocked_status
    elif violations:
        status = incomplete_status
    else:
        status = None
    return CompletenessReport(
        stage=stage, status=status, complete=not violations,
        recovered_after_retry=tuple(sorted(recovered)), missing_invocation_ids=tuple(missing),
        unexpected_invocation_ids=tuple(unexpected), duplicate_invocation_ids=tuple(duplicates),
        violations=tuple(violations),
    )



def _load_structural_gate_internal(
    spec: FrozenSpec,
    *,
    campaign_name: str,
    census_sha256: str,
    runner_capture_path: Path,
    collector_capture_path: Path,
    structural_manifest_path: Path,
    invocation_manifest_path: Path,
    attempt_registry: AttemptRegistry,
    manager_acceptance_path: Path,
    manager_acceptance_signature_path: Path,
    implementation_manifest_path: Path | None = None,
    production_token: object | None = None,
) -> StructuralGate:
    if runner_capture_path.resolve() == collector_capture_path.resolve():
        raise IncompleteCampaign("runner and collector manifests are not independently sourced")
    invocation_records = _load_invocation_records(
        invocation_manifest_path, census_sha256
    )
    runner_channel, runner_records = _load_structural_channel(
        spec, channel="runner", capture_path=runner_capture_path,
        structural_manifest_path=structural_manifest_path,
        invocation_records=invocation_records,
        campaign_name=campaign_name, census_sha256=census_sha256,
        implementation_manifest_path=implementation_manifest_path,
    )
    collector_channel, collector_records = _load_structural_channel(
        spec, channel="collector", capture_path=collector_capture_path,
        structural_manifest_path=structural_manifest_path,
        invocation_records=invocation_records,
        campaign_name=campaign_name, census_sha256=census_sha256,
        implementation_manifest_path=implementation_manifest_path,
    )
    if runner_records != collector_records:
        raise IncompleteCampaign("independent runner/collector structural records disagree")
    attempt_registry.require_binding(spec, campaign_name, census_sha256)
    if len(runner_records) != len(runner_channel.linked_origins):
        raise IncompleteCampaign("runner structural records and stdout origins differ in count")
    stdout_bindings: list[dict[str, str]] = []
    seen_bindings: set[str] = set()
    for record, (runner_path, runner_sha256) in zip(
        runner_records, runner_channel.linked_origins, strict=True
    ):
        invocation_id = record["invocation_id"]
        if invocation_id in seen_bindings:
            raise IncompleteCampaign("duplicate structural invocation in stdout binding")
        seen_bindings.add(invocation_id)
        attempt_path, attempt_sha256 = attempt_registry.successful_capture_identity(
            invocation_id
        )
        if runner_path.resolve() != attempt_path.resolve() or runner_sha256 != attempt_sha256:
            raise IncompleteCampaign("runner capture and successful attempt stdout identity disagree")
        parsed = parse_runner_stdout(spec, attempt_path.read_bytes())
        if parsed.manifest != record:
            raise IncompleteCampaign("successful attempt reparsed structural record disagrees")
        stdout_bindings.append({
            "invocation_id": invocation_id, "stdout_path": str(attempt_path),
            "stdout_sha256": attempt_sha256,
        })
    if seen_bindings != attempt_registry.invocation_ids():
        raise IncompleteCampaign(
            "structural records do not join every sealed campaign invocation exactly once"
        )
    records_bytes = structural_manifest_bytes(spec, runner_records)
    persisted_records, persisted_records_sha256 = _load_persisted_structural_manifest(
        spec, structural_manifest_path, runner_records, campaign_name=campaign_name
    )
    if persisted_records != records_bytes:
        raise IncompleteCampaign("persisted structural manifest bytes disagree")
    if manager_acceptance_path.resolve() == manager_acceptance_signature_path.resolve():
        raise IncompleteCampaign("acceptance receipt and signature paths must be distinct")
    try:
        acceptance_raw = manager_acceptance_path.read_bytes()
        signature_raw = manager_acceptance_signature_path.read_bytes()
    except OSError as error:
        raise IncompleteCampaign(f"structural gate evidence is unavailable: {error}") from error
    try:
        acceptance = json.loads(acceptance_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IncompleteCampaign(f"structural gate JSON parse failure: {error}") from error
    if not isinstance(acceptance, dict) or canonical_json_bytes(acceptance) != acceptance_raw:
        raise IncompleteCampaign("acceptance receipt is not canonical JSON")
    if set(acceptance) != MANAGER_ACCEPTANCE_FIELDS:
        raise IncompleteCampaign("acceptance receipt has a non-closed schema")
    historical_identity_key = None
    production_fixed = production_token is _PRODUCTION_GATE_TOKEN
    if production_fixed:
        fixed_paths = _production_gate_paths(spec, campaign_name)
        if (
            manager_acceptance_path.resolve() != fixed_paths.acceptance
            or manager_acceptance_signature_path.resolve() != fixed_paths.signature
            or implementation_manifest_path is None
            or implementation_manifest_path.resolve()
            != fixed_paths.implementation_manifest
        ):
            raise IncompleteCampaign("production structural gate paths are not frozen")
        historical_identity_key = _historical_acceptance_identity_key(
            spec,
            campaign_name=campaign_name,
            census_sha256=census_sha256,
            runner_capture_path=runner_capture_path,
            collector_capture_path=collector_capture_path,
            structural_manifest_path=structural_manifest_path,
            invocation_manifest_path=invocation_manifest_path,
            attempt_registry=attempt_registry,
            manager_acceptance_path=manager_acceptance_path,
            manager_acceptance_signature_path=manager_acceptance_signature_path,
        )
        if (
            historical_identity_key is None
            and campaign_name == "g2h_h3_v13_reexecution"
            and attempt_registry._acceptance_era_spec_hash == acceptance["spec_hash"]
            and acceptance["spec_hash"] != spec.attestation.json_sha256
        ):
            historical_identity_key = "h3_v13"
        if (
            historical_identity_key is None
            and campaign_name == "g2a_v2"
            and acceptance["spec_hash"] != spec.attestation.json_sha256
        ):
            historical_identity_key = "g2a"
    acceptance_runner: _StructuralChannel | None = None
    acceptance_collector: _StructuralChannel | None = None
    acceptance_era_attestation = None
    acceptance_spec_hash = spec.attestation.json_sha256
    if historical_identity_key is not None:
        acceptance_spec = _load_acceptance_era_spec(
            spec, acceptance["spec_hash"]
        )
        acceptance_view = _CurrentBuilderAcceptanceEraSpec(acceptance_spec, spec)
        acceptance_runner, acceptance_runner_records = _load_structural_channel(
            acceptance_view,
            channel="runner",
            capture_path=runner_capture_path,
            structural_manifest_path=structural_manifest_path,
            invocation_records=invocation_records,
            campaign_name=campaign_name,
            census_sha256=census_sha256,
            implementation_manifest_path=implementation_manifest_path,
        )
        acceptance_collector, acceptance_collector_records = _load_structural_channel(
            acceptance_view,
            channel="collector",
            capture_path=collector_capture_path,
            structural_manifest_path=structural_manifest_path,
            invocation_records=invocation_records,
            campaign_name=campaign_name,
            census_sha256=census_sha256,
            implementation_manifest_path=implementation_manifest_path,
        )
        if not (
            acceptance_runner_records == acceptance_collector_records
            == runner_records == collector_records
        ):
            raise IncompleteCampaign("dual-era runner/collector structural records disagree")
        _require_signed_historical_channel(
            acceptance_runner,
            runner_channel,
            acceptance_spec_hash=acceptance_spec.attestation.json_sha256,
            current_spec_hash=spec.attestation.json_sha256,
            signed_manifest_sha256=acceptance["runner_manifest_sha256"],
        )
        _require_signed_historical_channel(
            acceptance_collector,
            collector_channel,
            acceptance_spec_hash=acceptance_spec.attestation.json_sha256,
            current_spec_hash=spec.attestation.json_sha256,
            signed_manifest_sha256=acceptance["collector_manifest_sha256"],
        )
        acceptance_era_attestation = acceptance_spec.attestation
        acceptance_spec_hash = acceptance_spec.attestation.json_sha256
    expected_runner = acceptance_runner or runner_channel
    expected_collector = acceptance_collector or collector_channel
    expected_acceptance = {
        "campaign": campaign_name,
        "census_sha256": census_sha256,
        "collector_manifest_sha256": expected_collector.manifest_sha256,
        "runner_manifest_sha256": expected_runner.manifest_sha256,
        "spec_hash": acceptance_spec_hash,
    }
    for name, expected in expected_acceptance.items():
        if acceptance[name] != expected:
            raise IncompleteCampaign(f"acceptance receipt {name} disagrees")
    if not isinstance(acceptance["accepted_utc"], str) or not _UTC_TIMESTAMP.fullmatch(acceptance["accepted_utc"]):
        raise IncompleteCampaign("acceptance receipt timestamp is invalid")
    trust = _production_acceptance_trust(spec, implementation_manifest_path)
    _verify_acceptance_signature(
        acceptance_raw, manager_acceptance_signature_path, trust
    )
    combined_value: dict[str, Any] = {
        "collector_manifest_sha256": collector_channel.manifest_sha256,
        "runner_manifest_sha256": runner_channel.manifest_sha256,
        "structural_manifest_sha256": persisted_records_sha256,
    }
    if historical_identity_key is not None:
        combined_value["acceptance_era"] = {
            "collector_manifest_sha256": expected_collector.manifest_sha256,
            "runner_manifest_sha256": expected_runner.manifest_sha256,
            "spec_hash": acceptance_spec_hash,
        }
        combined_value["current_era"] = {"spec_hash": spec.attestation.json_sha256}
    combined_hash = sha256_bytes(canonical_json_bytes(combined_value))
    return StructuralGate(
        runner=runner_channel,
        collector=collector_channel,
        acceptance_runner=acceptance_runner,
        acceptance_collector=acceptance_collector,
        acceptance_era_attestation=acceptance_era_attestation,
        historical_identity_key=historical_identity_key,
        records_bytes=records_bytes,
        campaign=campaign_name,
        census_sha256=census_sha256,
        spec_hash=spec.attestation.json_sha256,
        acceptance_path=manager_acceptance_path.resolve(),
        acceptance_bytes=acceptance_raw,
        acceptance_fields=acceptance,
        signature_path=manager_acceptance_signature_path.resolve(),
        signature_sha256=sha256_bytes(signature_raw),
        trust=trust,
        manifest_sha256=combined_hash,
        stdout_bindings=stdout_bindings,
        structural_manifest_path=structural_manifest_path.resolve(),
        structural_manifest_sha256=persisted_records_sha256,
        runner_capture_path=runner_capture_path.resolve(),
        collector_capture_path=collector_capture_path.resolve(),
        invocation_manifest_path=invocation_manifest_path.resolve(),
        attempt_registry=attempt_registry,
        implementation_manifest_path=(
            None if implementation_manifest_path is None
            else implementation_manifest_path.resolve()
        ),
        production_paths_fixed=production_fixed,
        token=_STRUCTURAL_TOKEN,
    )


def load_structural_gate(
    spec: FrozenSpec,
    *,
    campaign_name: str,
    census_sha256: str,
    runner_capture_path: Path,
    collector_capture_path: Path,
    structural_manifest_path: Path,
    invocation_manifest_path: Path,
    attempt_registry: AttemptRegistry,
) -> StructuralGate:
    """Load a production gate using only paths derived from frozen identities."""
    paths = _production_gate_paths(spec, campaign_name)
    return _load_structural_gate_internal(
        spec,
        campaign_name=campaign_name,
        census_sha256=census_sha256,
        runner_capture_path=runner_capture_path,
        collector_capture_path=collector_capture_path,
        structural_manifest_path=structural_manifest_path,
        invocation_manifest_path=invocation_manifest_path,
        attempt_registry=attempt_registry,
        manager_acceptance_path=paths.acceptance,
        manager_acceptance_signature_path=paths.signature,
        implementation_manifest_path=paths.implementation_manifest,
        production_token=_PRODUCTION_GATE_TOKEN,
    )

_PRODUCTION_GATE_TOKEN = object()

# Production writers restored from the same historical implementation.

_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")

def _campaign_name_for_invocation(
    spec: FrozenSpec, invocation: Mapping[str, Any]
) -> str:
    """Resolve one invocation to its sole frozen campaign without caller input."""
    required = {"experiment", "seed", "scale"}
    if not required <= set(invocation):
        raise IncompleteCampaign("invocation lacks frozen campaign identity fields")
    matches = []
    for campaign in spec.get("/confirmation_data/campaigns", expected_type=list):
        if (
            invocation["experiment"] in campaign["experiments"]
            and invocation["seed"] in campaign["seeds"]
            and invocation["scale"] in campaign["scales"]
        ):
            matches.append(campaign["name"])
    if len(matches) != 1:
        raise IncompleteCampaign("invocation does not select one frozen campaign")
    return matches[0]

def build_attempt_record(
    spec: FrozenSpec, *, invocation: Mapping[str, Any], argv: Sequence[str], cwd: str,
    start_utc: str, end_utc: str, return_code: int | None, timeout: bool,
    stdout: bytes, stderr: bytes, capture_relative_path: str,
    exclusion_reason: str | None = None,
    implementation_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Construct the frozen sidecar after process closure; no summary is accepted."""
    pins = spec.get("/provenance/candidate_pins", expected_type=dict)
    summary = _derive_attempt_summary(
        spec, stdout, invocation,
        campaign_name=_campaign_name_for_invocation(spec, invocation),
        implementation_manifest_path=implementation_manifest_path,
    )
    record = {
        "argv": list(argv), "cwd": cwd, "start_utc": start_utc, "end_utc": end_utc,
        "return_code": return_code, "timeout": timeout,
        "stdout_sha256": sha256_bytes(stdout), "stderr_sha256": sha256_bytes(stderr),
        "stderr_or_content_path": capture_relative_path,
        **summary,
        "runner_hash": pins["runner_binary_sha256"],
        "spec_hash": spec.attestation.json_sha256,
        "source_hash": pins["runner_source_sha256"],
        "exclusion_reason": exclusion_reason,
    }
    validate_attempt_record(spec, record)
    return record

def build_structural_acceptance_payload(
    spec: FrozenSpec,
    *,
    campaign_name: str,
    census_sha256: str,
    runner_capture_path: Path,
    collector_capture_path: Path,
    structural_manifest_path: Path,
    invocation_manifest_path: Path,
    accepted_utc: str,
    implementation_manifest_path: Path | None = None,
) -> bytes:
    """Build the exact unsigned payload that only the manager may sign."""
    if not isinstance(accepted_utc, str) or not _UTC_TIMESTAMP.fullmatch(accepted_utc):
        raise IncompleteCampaign("manager acceptance timestamp is invalid")
    invocation_records = _load_invocation_records(
        invocation_manifest_path, census_sha256
    )
    runner_channel, runner_records = _load_structural_channel(
        spec, channel="runner", capture_path=runner_capture_path,
        structural_manifest_path=structural_manifest_path,
        invocation_records=invocation_records,
        campaign_name=campaign_name, census_sha256=census_sha256,
        implementation_manifest_path=implementation_manifest_path,
    )
    collector_channel, collector_records = _load_structural_channel(
        spec, channel="collector", capture_path=collector_capture_path,
        structural_manifest_path=structural_manifest_path,
        invocation_records=invocation_records,
        campaign_name=campaign_name, census_sha256=census_sha256,
        implementation_manifest_path=implementation_manifest_path,
    )
    if runner_records != collector_records:
        raise IncompleteCampaign("independent runner/collector structural records disagree")
    return canonical_json_bytes({
        "accepted_utc": accepted_utc,
        "campaign": campaign_name,
        "census_sha256": census_sha256,
        "collector_manifest_sha256": collector_channel.manifest_sha256,
        "runner_manifest_sha256": runner_channel.manifest_sha256,
        "spec_hash": spec.attestation.json_sha256,
    })
