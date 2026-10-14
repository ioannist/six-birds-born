"""Production transport for the frozen mixed-source G2c v2 census."""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import born_ladder.reproduction.predictive.campaign as transport
from born_ladder.snapshot.artifact_paths import authorized_output_path, reject_symlink_chain
from born_ladder.reproduction.predictive.campaign import CampaignArtifacts
from born_ladder.snapshot.completeness import _argv_for, build_attempt_record, build_invocation_manifest, invocation_id_for, invocation_manifest_bytes, structural_manifest_bytes
from born_ladder.snapshot.errors import BlockedInfrastructure, IncompleteCampaign, Rebuild1Error, SpecMismatch
from born_ladder.reproduction.specification import PublicSpecification as FrozenSpec
from born_ladder.snapshot.frozen_spec import canonical_json_bytes
from born_ladder.snapshot.frozen_spec import sha256_bytes
from born_ladder.snapshot.g2c_collector_structural import build_g2c_collector_capture, parse_g2c_collector_capture_bundle, require_g2c_structural_channel_equality, segment_census_record
from born_ladder.snapshot.inventory import InventoryAuthorization, build_inventory
from born_ladder.snapshot.provenance import ProvenanceFiles, file_sha256
from born_ladder.snapshot.runner_structural import build_runner_capture, parse_runner_capture_bundle


_POINTERS = {
    "g2c_campaign_artifacts": "/artifact_paths/artifacts/g2c",
    "g2c_campaign_campaign": "/confirmation_data/campaigns/6",
    "g2c_campaign_derivation": "/completeness/g2c_raw_stdout_derivation",
    "g2c_campaign_invocation_fields": "/completeness/invocation_manifest_fields",
    "g2c_campaign_matrix": "/completeness/expected_matrices/6",
    "g2c_campaign_namespace": "/artifact_paths/namespace",
    "g2c_campaign_output_absence": "/artifact_paths/g2c_v23_output_absence",
    "g2c_campaign_pins": "/provenance/candidate_pins",
    "g2c_campaign_plan": "/artifact_paths/g2c_per_unit_reproduction_plan",
    "g2c_campaign_manifest_identities": "/completeness/invocation_manifest_identities",
    "g2c_campaign_execution": "/confirmation_data/g2c_v21_execution",
    "g2c_campaign_shapes": "/completeness/universal_evidence_shapes",
    "g2c_campaign_workers": "/thresholds/items/30/value",
    "g2c_campaign_timeout": "/thresholds/items/31/value",
}

_V21_ARTIFACTS = [
    "rb1v2_g2c_invocation_manifest.json",
    "rb1v2_g2c_campaign_attempts_content_addressed/",
    "rb1v2_g2c_structural_manifest.jsonl",
    "rb1v2_g2c_structural_acceptance.json",
    "rb1v2_g2c_structural_acceptance.json.sig",
    "rb1v2_g2c_campaign.json",
    "rb1v2_g2c_units.jsonl",
    "rb1v2_g2c_controls.jsonl",
    "rb1v2_g2c_pkg_reconstruction.jsonl",
    "rb1v2_g2c_evaluation.json",
]
_V21_MANIFESTS = [
    "rb1v2_invocation_manifest.json",
    "rb1v2_g2h_h1_h2_invocation_manifest.json",
    "rb1v2_g2h_h3_v13_invocation_manifest.json",
    "rb1v2_g2h_h4_invocation_manifest.json",
    "rb1v2_g2x_confirm_v20_invocation_manifest.json",
    "rb1v2_g2c_invocation_manifest.json",
    "rb1v2_g2b_invocation_manifest.json",
]


@dataclass(frozen=True)
class G2CCampaignArtifacts(CampaignArtifacts):
    execution_policy_path: Path | None = None
    incomplete_execution_path: Path | None = None


def _contract(spec: FrozenSpec, manifest: Path | None = None) -> dict[str, Any]:
    spec.audit_implementation_manifest(
        "g2c_campaign", manifest_path=manifest, declared_pointers=_POINTERS
    )
    # The v24 route does not create a campaign. Manifest construction and the
    # preflight inventory continue to describe the sealed v21 source campaign.
    # The source selection is fixed by ``load_g2c_v24_sealed_source`` and is not
    # caller selectable.
    source_spec = getattr(spec, "_g2c_source_spec", spec)
    value = {}
    for name, pointer in _POINTERS.items():
        selected = spec if name == "g2c_campaign_output_absence" else source_spec
        value[name.removeprefix("g2c_campaign_")] = selected.get(pointer)
    registry = value["derivation"]
    overlay = registry.get("overlays", {}).get("g2c_v2")
    if not isinstance(overlay, dict) or registry.get("overlay_keys") != ["g2c_v2"]:
        raise SpecMismatch("frozen G2c campaign overlay disagrees")
    plan = value["plan"]
    execution = value["execution"]
    identities = value["manifest_identities"]
    current = identities.get("registries", {}).get("current_v21")
    operative = identities.get("g2r_manifest_sets", {}).get("operative_v21")
    if (
        plan.get("artifacts") != _V21_ARTIFACTS
        or plan.get("publication_count") != 10
        or plan.get("timeout_contract_pointer") != _POINTERS["g2c_campaign_execution"]
        or overlay.get("census", {}).get("invocation_manifest") != _V21_ARTIFACTS[0]
        or execution.get("campaign_id") != "g2c_v2"
        or plan.get("conditional_incomplete_execution") != "rb1v2_g2c_incomplete_execution.json"
        or not isinstance(current, Mapping)
        or current.get("paths", {}).get("g2c") != _V21_ARTIFACTS[0]
        or not isinstance(operative, Mapping)
        or operative.get("manifests") != _V21_MANIFESTS
        or identities.get("registries", {}).get("current_v20", {}).get(
            "paths", {}
        ).get("g2x_confirm") != "rb1v2_g2x_confirm_v20_invocation_manifest.json"
    ):
        raise SpecMismatch("frozen G2c transport identities disagree")
    value["timeout_contract"] = _v21_timeout_contract(execution)
    return value


def _v21_timeout_contract(execution: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve all five closed G2c-v21 timeout channels from one pointer."""
    pointer = _POINTERS["g2c_campaign_execution"] + "/per_attempt_timeout_seconds"
    value = execution.get("per_attempt_timeout_seconds")
    channels = execution.get("timeout_channel_descriptors")
    descriptors = channels.get("descriptors") if isinstance(channels, Mapping) else None
    order = [
        "execution_policy", "retry_identity", "attempt_sidecar",
        "campaign_provenance", "subprocess_argument",
    ]
    keys = {
        "channel", "container", "field_name", "field_type", "required",
        "schema_version", "value", "value_json_pointer",
    }
    schema_versions = {
        "execution_policy": "RB1_G2C_V21_EXECUTION_POLICY_V1",
        "retry_identity": "RB1_G2C_V21_RETRY_IDENTITY_V1",
        "attempt_sidecar": "RB1_G2C_V21_ATTEMPT_SIDECAR_V1",
        "campaign_provenance": "RB1_G2C_V21_CAMPAIGN_PROVENANCE_V1",
        "subprocess_argument": "RB1_G2C_V21_SUBPROCESS_ARGUMENT_V1",
    }
    containers = {
        "execution_policy": (
            "/confirmation_data/g2c_v21_execution/execution_policy"
        ),
        "retry_identity": "G2c v21 retry identity object",
        "attempt_sidecar": "G2c v21 attempt sidecar object",
        "campaign_provenance": "G2c v21 campaign provenance object",
        "subprocess_argument": "subprocess.run timeout argument",
    }
    field_names = {name: "per_attempt_timeout_seconds" for name in order}
    field_names["subprocess_argument"] = "timeout"
    field_types = {name: "JSON_INTEGER" for name in order}
    field_types["subprocess_argument"] = "PYTHON_TIMEOUT_SECONDS_INTEGER"
    if (
        type(value) is not int or value != 1800
        or not isinstance(channels, Mapping)
        or channels.get("schema_version") != "RB1_G2C_V21_TIMEOUT_CHANNELS_V1"
        or channels.get("ordered_channels") != order
        or not isinstance(descriptors, Mapping)
        or set(descriptors) != set(order)
    ):
        raise SpecMismatch("frozen G2c-v21 timeout contract disagrees")
    for channel in order:
        row = descriptors[channel]
        if (
            not isinstance(row, Mapping) or set(row) != keys
            or row["channel"] != channel or row["required"] is not True
            or row["container"] != containers[channel]
            or row["field_name"] != field_names[channel]
            or row["field_type"] != field_types[channel]
            or row["schema_version"] != schema_versions[channel]
            or type(row["value"]) is not int or row["value"] != value
            or row["value_json_pointer"] != pointer
        ):
            raise SpecMismatch(f"frozen G2c-v21 timeout descriptor disagrees for {channel}")
    policy = execution.get("execution_policy")
    if (
        not isinstance(policy, Mapping)
        or type(policy.get("per_attempt_timeout_seconds")) is not int
        or policy.get("per_attempt_timeout_seconds") != value
        or policy.get("identical_retry_count") != 1
        or policy.get("third_attempt_permitted") is not False
        or policy.get("automatic_timeout_increase") is not False
        or policy.get("selective_salvage") is not False
        or policy.get("exhausted_retry_disposition") != "G2C_V2_INCOMPLETE"
    ):
        raise SpecMismatch("frozen G2c-v21 execution policy disagrees")
    return {
        "descriptors": copy.deepcopy(dict(channels)),
        "execution_policy": copy.deepcopy(dict(policy)),
        "pointer": pointer,
        "value": value,
    }


def build_g2c_invocation_manifest(
    spec: FrozenSpec, *, inventory_authorization: InventoryAuthorization,
    implementation_manifest_path: Path | None = None,
) -> list[dict[str, Any]]:
    contract = _contract(spec, implementation_manifest_path)
    registry = contract["derivation"]
    overlay = registry["overlays"]["g2c_v2"]
    if (
        overlay["census"]["campaign_pointer"] != _POINTERS["g2c_campaign_campaign"]
        or overlay["census"]["expected_matrix_pointer"]
        != _POINTERS["g2c_campaign_matrix"]
    ):
        raise SpecMismatch("frozen G2c census pointers disagree")
    campaign = contract["campaign"]
    matrix = contract["matrix"]
    families = list(overlay["invocation_manifest"]["required_emission_families"])
    rows = build_invocation_manifest(
        spec, campaign["name"], expected_schema=overlay["expected_schema"],
        required_emission_families=families,
        inventory_authorization=inventory_authorization,
        implementation_manifest_path=implementation_manifest_path,
    )
    if (
        len(rows) != overlay["census"]["expected_invocations"]
        or len(rows) != matrix["expected_invocations"]
        or any(len(row) != len(contract["invocation_fields"]) for row in rows)
    ):
        raise IncompleteCampaign("G2c invocation manifest census or shape disagrees")
    validate_g2c_invocation_manifest_records(spec, rows, contract=contract)
    return rows


def validate_g2c_invocation_manifest_records(
    spec: FrozenSpec, records: Sequence[Mapping[str, Any]], *,
    contract: Mapping[str, Any] | None = None,
    implementation_manifest_path: Path | None = None,
) -> None:
    """Validate the persisted eight-field mixed-source census as a closed object."""
    value = _contract(spec, implementation_manifest_path) if contract is None else contract
    overlay = value["derivation"]["overlays"]["g2c_v2"]
    fields = set(value["invocation_fields"])
    if (
        overlay["invocation_manifest"]["internal_labels_field_permitted"] is not False
        or len(records) != overlay["census"]["expected_invocations"]
        or any(type(record) is not dict or set(record) != fields for record in records)
    ):
        raise IncompleteCampaign("G2c persisted invocation row shape disagrees")
    expected_census = [
        (experiment, config, seed, scale)
        for experiment in value["campaign"]["experiments"]
        for config in (
            spec.get("/grid/labels", expected_type=list)
            if experiment == "EXP-112" else [None]
        )
        for seed in value["campaign"]["seeds"]
        for scale in value["campaign"]["scales"]
    ]
    expected = [{
        "argv": transport_argv,
        "config_or_null": config,
        "expected_schema": overlay["expected_schema"],
        "experiment": experiment,
        "invocation_id": invocation_id_for(
            spec, experiment=experiment, config_or_null=config,
            seed=seed, scale=scale,
        ),
        "required_emission_families": list(
            overlay["invocation_manifest"]["required_emission_families"]
        ),
        "scale": scale,
        "seed": seed,
    } for experiment, config, seed, scale in expected_census
      for transport_argv in [[*_argv_for(
          spec, experiment=experiment, config=config, seed=seed, scale=scale
      )]]]
    if list(records) != expected:
        raise IncompleteCampaign("G2c persisted invocation census or identity disagrees")


def _validate_v21_attempt_record(
    spec: FrozenSpec, record: Mapping[str, Any], *, timeout_seconds: int,
) -> None:
    expected = set(spec.get("/completeness/attempt_record_fields", expected_type=list))
    if set(record) != expected | {"per_attempt_timeout_seconds"}:
        raise IncompleteCampaign("G2c-v21 attempt sidecar timeout field is missing or extra")
    if type(record["per_attempt_timeout_seconds"]) is not int or record[
        "per_attempt_timeout_seconds"
    ] != timeout_seconds:
        raise IncompleteCampaign("G2c-v21 attempt sidecar timeout disagrees")
    historical = dict(record)
    historical.pop("per_attempt_timeout_seconds")
    from born_ladder.snapshot.completeness import validate_attempt_record

    validate_attempt_record(spec, historical)


def _execute_v21_one(
    spec: FrozenSpec, invocation: Mapping[str, Any], *, runner_path: Path,
    capture_root: Path, timeout_contract: Mapping[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    """Execute one operative invocation with the non-caller-selectable v21 timeout."""
    timeout_seconds = timeout_contract["value"]
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
                raise IncompleteCampaign(
                    f"resume G2c-v21 attempt sidecars are not unique for {invocation_id}"
                )
            sidecar_path = sidecars[0]
            try:
                record = json.loads(sidecar_path.read_text(encoding="utf-8"))
                expected_sidecar = attempt_dir / (
                    f"{sha256_bytes(canonical_json_bytes(record))}.attempt.json"
                )
                stdout_path = attempt_dir / f'{record["stdout_sha256"]}.stdout.bin'
                stderr_path = attempt_dir / f'{record["stderr_sha256"]}.stderr.bin'
                stdout = stdout_path.read_bytes()
                stderr = stderr_path.read_bytes()
            except (KeyError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise IncompleteCampaign(
                    f"resume G2c-v21 capture is invalid for {invocation_id}: {error}"
                ) from error
            _validate_v21_attempt_record(spec, record, timeout_seconds=timeout_seconds)
            if (
                expected_sidecar != sidecar_path
                or sidecar_path.read_bytes() != canonical_json_bytes(record)
                or sha256_bytes(stdout) != record["stdout_sha256"]
                or sha256_bytes(stderr) != record["stderr_sha256"]
                or {path.name for path in attempt_dir.iterdir()}
                != {stdout_path.name, stderr_path.name, sidecar_path.name}
            ):
                raise IncompleteCampaign("resume G2c-v21 capture bytes disagree")
        else:
            if attempt_dir.exists() or attempt_dir.is_symlink():
                raise IncompleteCampaign(
                    f"partial unsealed G2c-v21 attempt collision at {attempt_dir}"
                )
            attempt_dir.mkdir(parents=True, exist_ok=False)
            start = transport._utc_now()
            try:
                completed = transport.subprocess.run(
                    argv, cwd=execution_cwd, env=dict(transport._EXECUTION_ENVIRONMENT),
                    check=False, timeout=timeout_seconds,
                    stdout=transport.subprocess.PIPE, stderr=transport.subprocess.PIPE,
                )
                return_code: int | None = completed.returncode
                timed_out = False
                stdout, stderr = completed.stdout, completed.stderr
            except transport.subprocess.TimeoutExpired as error:
                return_code = None
                timed_out = True
                stdout, stderr = error.stdout or b"", error.stderr or b""
            except OSError as error:
                raise BlockedInfrastructure(
                    f"G2c-v21 runner process unavailable: {error}"
                ) from error
            end = transport._utc_now()
            stdout_hash = sha256_bytes(stdout)
            stderr_hash = sha256_bytes(stderr)
            stdout_path = attempt_dir / f"{stdout_hash}.stdout.bin"
            stderr_path = attempt_dir / f"{stderr_hash}.stderr.bin"
            transport._write_new(stdout_path, stdout, safe_root=capture_root)
            transport._write_new(stderr_path, stderr, safe_root=capture_root)
            historical = build_attempt_record(
                spec, invocation=invocation, argv=argv, cwd=str(execution_cwd),
                start_utc=start, end_utc=end, return_code=return_code,
                timeout=timed_out, stdout=stdout, stderr=stderr,
                capture_relative_path=str(stderr_path.relative_to(capture_root)),
            )
            record = {**historical, "per_attempt_timeout_seconds": timeout_seconds}
            _validate_v21_attempt_record(spec, record, timeout_seconds=timeout_seconds)
            sidecar_path = attempt_dir / (
                f"{sha256_bytes(canonical_json_bytes(record))}.attempt.json"
            )
            transport._write_new(
                sidecar_path, canonical_json_bytes(record), safe_root=capture_root
            )
        records.append(record)
        if record["return_code"] == 0 and record["timeout"] is False:
            break
    return invocation_id, records


def _registry_bytes(
    spec: FrozenSpec, invocations: Sequence[Mapping[str, Any]],
    attempts: Mapping[str, Sequence[Mapping[str, Any]]], *,
    census_sha256: str, runner_sha256: str, timeout_seconds: int,
) -> bytes:
    retry, records = {}, {}
    for invocation in invocations:
        identity = invocation["invocation_id"]
        if identity not in attempts:
            continue
        values = [copy.deepcopy(dict(value)) for value in attempts[identity]]
        records[identity] = values
        first = values[0]
        retry[identity] = {
            "argv": first["argv"], "cwd": first["cwd"],
            "environment_allowlist": dict(transport._EXECUTION_ENVIRONMENT),
            "runner_binary_sha256": runner_sha256, "seed": invocation["seed"],
            "per_attempt_timeout_seconds": timeout_seconds,
        }
    return canonical_json_bytes({
        "attempts": records, "campaign": "g2c_v2",
        "census_sha256": census_sha256, "retry_identities": retry,
        "spec_hash": spec.attestation.json_sha256,
    })


def _authorized(spec: FrozenSpec, root: Path, name: str, manifest: Path | None) -> Path:
    target = root / name
    reject_symlink_chain(target, repo_root=root)
    if target.exists():
        return target
    authorized = authorized_output_path(
        spec, artifact_name=name, repo_root=spec.repo_root,
        implementation_manifest_path=manifest,
    )
    if authorized != target.resolve():
        raise IncompleteCampaign("authorized G2c output path disagrees")
    return target


def _validate_v21_timeout_persistence(
    spec: FrozenSpec, *, contract: Mapping[str, Any], registry: Mapping[str, Any],
    execution_policy_raw: bytes, campaign_provenance: Mapping[str, Any],
    subprocess_timeout_argument: int,
) -> None:
    timeout = contract["timeout_contract"]
    value = timeout["value"]
    try:
        policy = json.loads(execution_policy_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IncompleteCampaign(f"G2c-v21 execution policy is invalid: {error}") from error
    if (
        canonical_json_bytes(policy) != execution_policy_raw
        or execution_policy_raw != canonical_json_bytes(timeout["execution_policy"])
    ):
        raise IncompleteCampaign("G2c-v21 execution policy bytes disagree")
    attempts = registry.get("attempts")
    retries = registry.get("retry_identities")
    if (
        not isinstance(attempts, dict) or not attempts
        or not isinstance(retries, dict) or set(attempts) != set(retries)
    ):
        raise IncompleteCampaign("G2c-v21 timeout evidence registries are incomplete")
    for invocation_id, rows in attempts.items():
        retry = retries[invocation_id]
        if (
            not isinstance(retry, dict)
            or set(retry) != {
                "argv", "cwd", "environment_allowlist",
                "per_attempt_timeout_seconds", "runner_binary_sha256", "seed",
            }
            or type(retry.get("per_attempt_timeout_seconds")) is not int
            or retry["per_attempt_timeout_seconds"] != value
        ):
            raise IncompleteCampaign("G2c-v21 retry identity timeout disagrees")
        if not isinstance(rows, list) or not rows:
            raise IncompleteCampaign("G2c-v21 attempt timeout evidence is empty")
        for row in rows:
            _validate_v21_attempt_record(spec, row, timeout_seconds=value)
    if (
        set(campaign_provenance) != {"per_attempt_timeout_seconds", "provenance"}
        or type(campaign_provenance.get("per_attempt_timeout_seconds")) is not int
        or campaign_provenance.get("per_attempt_timeout_seconds") != value
        or not isinstance(campaign_provenance.get("provenance"), dict)
    ):
        raise IncompleteCampaign("G2c-v21 campaign provenance timeout disagrees")
    if type(subprocess_timeout_argument) is not int or subprocess_timeout_argument != value:
        raise IncompleteCampaign("G2c-v21 subprocess timeout argument disagrees")




def validate_v21_campaign_timeout_artifact(
    spec: FrozenSpec, *, campaign_artifact_path: Path,
    implementation_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Reload and cross-check all five persisted v21 timeout channels."""
    contract = _contract(spec, implementation_manifest_path)
    root = (spec.repo_root / contract["namespace"]).resolve()
    expected = root / contract["plan"]["artifacts"][5]
    if campaign_artifact_path.resolve() != expected:
        raise IncompleteCampaign("G2c-v21 campaign does not use its frozen path")
    reject_symlink_chain(campaign_artifact_path, repo_root=spec.repo_root)
    try:
        raw = campaign_artifact_path.read_bytes()
        campaign = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IncompleteCampaign(f"G2c-v21 campaign is unavailable or invalid: {error}") from error
    if canonical_json_bytes(campaign) != raw:
        raise IncompleteCampaign("G2c-v21 campaign is not canonical JSON")
    if (
        campaign.get("campaign_identity") != "g2c_v2"
        or canonical_json_bytes(campaign.get("timeout_channel_descriptors"))
        != canonical_json_bytes(contract["timeout_contract"]["descriptors"])
        or campaign.get("campaign_provenance", {}).get("provenance")
        != campaign.get("provenance")
    ):
        raise IncompleteCampaign("G2c-v21 persisted timeout descriptors disagree")
    policy_binding = campaign.get("execution_policy")
    registry_binding = campaign.get("attempt_registry")
    if (
        not isinstance(policy_binding, dict) or set(policy_binding) != {"path", "sha256"}
        or not isinstance(registry_binding, dict) or set(registry_binding) != {"path", "sha256"}
    ):
        raise IncompleteCampaign("G2c-v21 timeout artifact bindings are malformed")
    policy_path = Path(policy_binding["path"])
    registry_path = Path(registry_binding["path"])
    if not policy_path.is_absolute():
        policy_path = root / policy_path
    if not registry_path.is_absolute():
        registry_path = root / registry_path
    for path in (policy_path, registry_path):
        reject_symlink_chain(path, repo_root=spec.repo_root)
        if path.resolve().parent != root:
            raise IncompleteCampaign("G2c-v21 timeout evidence leaves the frozen namespace")
    try:
        policy_raw = policy_path.read_bytes()
        registry_raw = registry_path.read_bytes()
        registry = json.loads(registry_raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IncompleteCampaign(f"G2c-v21 timeout evidence is unavailable: {error}") from error
    if (
        sha256_bytes(policy_raw) != policy_binding["sha256"]
        or policy_path.name != f'{policy_binding["sha256"]}.json'
        or sha256_bytes(registry_raw) != registry_binding["sha256"]
        or registry_path.name != f'{registry_binding["sha256"]}.json'
        or canonical_json_bytes(registry) != registry_raw
    ):
        raise IncompleteCampaign("G2c-v21 timeout evidence identity disagrees")
    _validate_v21_timeout_persistence(
        spec, contract=contract, registry=registry,
        execution_policy_raw=policy_raw,
        campaign_provenance=campaign["campaign_provenance"],
        subprocess_timeout_argument=campaign.get("subprocess_argument", {}).get("timeout"),
    )
    provenance = campaign["provenance"].get("input_sha256s", {})
    if (
        provenance.get("v21_execution_policy") != policy_binding["sha256"]
        or provenance.get("sealed_attempt_registry") != registry_binding["sha256"]
    ):
        raise IncompleteCampaign("G2c-v21 provenance timeout binding disagrees")
    return copy.deepcopy(campaign)








