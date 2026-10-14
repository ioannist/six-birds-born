"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import copy
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from born_ladder.snapshot.errors import IncompleteCampaign, SpecMismatch
from born_ladder.snapshot.frozen_spec import FrozenSpec, canonical_json_bytes, sha256_bytes

CURRENT_ABSOLUTE_ROLES = {
    "attempt_guard_state",
    "execution_record",
    "completion_receipt",
    "failed_attempt_evidence",
    "completion_failure_evidence",
}


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


_HEX40 = re.compile(r"^[0-9a-f]{40}$")


_RFC3339_UTC = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
)


_V24_HISTORICAL_MANIFEST_SELECTOR = {
    "expected_sha256": "3d42b50e42e28611bafa883a252eb1156c9336f24848bc71ff4e27bc4641ebda",
    "expected_size_bytes": 126678,
    "immutable_git_blob": {
        "commit": "7f1dffbf3131bddbca05b146428953275acfb0b6",
        "git_object_id_sha1": "a8fb77e4a556438df941e034cc57f753fa73419c",
        "git_object_type": "blob",
        "path": "scripts/rebuild1/implementation_manifest.jsonl",
        "sha256": "3d42b50e42e28611bafa883a252eb1156c9336f24848bc71ff4e27bc4641ebda",
        "size_bytes": 126678,
    },
    "original_path": "scripts/rebuild1/implementation_manifest.jsonl",
    "role": "historical_implementation_manifest",
    "selector_order": ["immutable_git_blob"],
}


_IMPLEMENTATION_POINTERS = {
    "attempt_guard": "/completeness/g2c_v24_attempt_guard",
    "completion_failure": "/completeness/g2c_v24_completion_failure_evidence",
    "completion_receipt": "/completeness/g2c_v24_completion_receipt",
    "destination_contract": "/completeness/g2c_v24_destination_contract",
    "detached_receipt": "/completeness/g2c_v24_detached_provenance_receipt",
    "evaluation_authorization": "/completeness/g2c_v24_evaluation_authorization",
    "execution_record": "/completeness/g2c_v24_execution_record",
    "execution_packet": "/execution_packets/g2c_v24_sealed_evaluation",
    "output_absence": "/artifact_paths/g2c_v23_output_absence",
    "prepublication_record": "/completeness/g2c_v24_prepublication_provenance_record",
    "sealed_input_route": "/completeness/g2c_v24_sealed_input_route",
    "validation_coverage": "/completeness/g2c_v24_validation_and_mutation_coverage",
}


_REQUIRED_EXECUTING_CODE = (
    ("scripts/rebuild1/evaluate_g2c_campaign.py", "v23_evaluator_entrypoint"),
    ("scripts/rebuild1/evidence.py", "v23_evidence_validator"),
    ("scripts/rebuild1/frozen_spec.py", "v23_sealed_source_loader"),
    ("scripts/rebuild1/g2c_controls.py", "v23_rotation_control"),
    ("scripts/rebuild1/g2c_evaluate.py", "v23_scientific_evaluator"),
    ("scripts/rebuild1/g2c_rotation_certificate.py", "v23_rotation_certificate"),
    ("scripts/rebuild1/g2c_units.py", "v23_unit_finalizer"),
    ("scripts/rebuild1/g2c_v23.py", "v23_record_validator"),
    ("scripts/rebuild1/universal_shapes.py", "v23_universal_validator"),
)


def audit_v23_contracts(spec: FrozenSpec) -> None:
    spec.audit_implementation_manifest(
        "g2c_v23", declared_pointers=_IMPLEMENTATION_POINTERS,
    )


def publication_identity(spec: FrozenSpec) -> dict[str, str]:
    return {
        "companion": spec.historical_companion,
        "companion_sha256": spec.attestation.json_sha256,
        "companion_self_hash": spec.get("/identity/json_sha256", expected_type=str),
        "freeze_commit": spec.attestation.freeze_commit,
        "spec_id": spec.attestation.spec_id,
        "tag": spec.attestation.tag,
    }


def source_identity(spec: FrozenSpec) -> dict[str, Any]:
    return spec.get(
        "/completeness/g2c_v24_sealed_input_route/source_identity",
        expected_type=dict,
    )


def parse_canonical_json(raw: bytes, *, label: str = "record") -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise SpecMismatch(f"{label} contains duplicate object key {key!r}")
            result[key] = value
        return result

    def nonfinite(value: str) -> Any:
        raise SpecMismatch(f"{label} contains nonfinite JSON number {value}")

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_constant=nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SpecMismatch(f"{label} is not duplicate-free UTF-8 JSON: {error}") from error
    if canonical_json_bytes(value) != raw:
        raise SpecMismatch(f"{label} is not canonical compact sorted-key JSON with final LF")
    return value


def _identity(path: Path) -> tuple[int, str]:
    if path.is_symlink() or not path.is_file():
        raise IncompleteCampaign(f"required predecessor is not a regular nonsymlink file: {path}")
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
    except OSError as error:
        raise IncompleteCampaign(f"cannot measure predecessor {path}: {error}") from error
    return size, digest.hexdigest()


def identity_descriptor(
    path: Path,
    *,
    role: str,
    repo_root: Path,
    absolute: bool,
) -> dict[str, Any]:
    root = repo_root.resolve()
    resolved = path.resolve(strict=False)
    if absolute:
        textual = str(resolved)
    else:
        try:
            textual = resolved.relative_to(root).as_posix()
        except ValueError as error:
            raise SpecMismatch(f"repository-relative descriptor escapes root: {path}") from error
    size, digest = _identity(resolved)
    return {"role": role, "path": textual, "size_bytes": size, "sha256": digest}


def _resolved_descriptor_path(row: Mapping[str, Any], root: Path) -> Path:
    raw = row.get("path")
    if type(raw) is not str or not raw:
        raise SpecMismatch("identity descriptor path must be a nonempty string")
    path = Path(raw)
    if row.get("role") in CURRENT_ABSOLUTE_ROLES:
        if not path.is_absolute() or ".." in path.parts:
            raise SpecMismatch("current evidence descriptor path is not canonical absolute")
        if any(node.is_symlink() for node in (path, *path.parents) if node.exists()):
            raise SpecMismatch("current evidence descriptor path contains a symlink")
        resolved = path.resolve(strict=False)
        if str(resolved) != raw:
            raise SpecMismatch("current evidence descriptor path is not canonical")
        return resolved
    if path.is_absolute() or ".." in path.parts or path.as_posix() != raw:
        raise SpecMismatch("inherited/output descriptor path is not canonical repository-relative")
    candidate = root / path
    if any(node.is_symlink() for node in (candidate, *candidate.parents) if node.exists()):
        raise SpecMismatch("repository-relative descriptor path contains a symlink")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise SpecMismatch("descriptor path escapes repository root") from error
    return resolved


def validate_identity_descriptor(
    row: Any, *, repo_root: Path, measure: bool = True,
) -> Path:
    if type(row) is not dict or set(row) != {"role", "path", "size_bytes", "sha256"}:
        raise SpecMismatch("identity descriptor is not a closed four-key object")
    if type(row["role"]) is not str or not row["role"]:
        raise SpecMismatch("identity descriptor role must be nonempty")
    if type(row["size_bytes"]) is not int or isinstance(row["size_bytes"], bool) or row["size_bytes"] < 0:
        raise SpecMismatch("identity descriptor byte count is invalid")
    if type(row["sha256"]) is not str or not _HEX64.fullmatch(row["sha256"]):
        raise SpecMismatch("identity descriptor SHA-256 is invalid")
    path = _resolved_descriptor_path(row, repo_root.resolve())
    if measure and _identity(path) != (row["size_bytes"], row["sha256"]):
        raise SpecMismatch(f"identity descriptor disagrees for role {row['role']}")
    return path


def _canonical_absolute_destination(value: Any, *, label: str) -> Path:
    """Validate the frozen textual and filesystem form of an absolute path."""
    if type(value) is not str or not value:
        raise SpecMismatch(f"{label} must be a nonempty canonical absolute path")
    path = Path(value)
    # ``Path`` normalizes repeated separators and dot components.  Requiring
    # its textual form to agree catches those spellings before resolution;
    # the explicit segment check also makes the rejection independent of the
    # host pathlib implementation.
    segments = value.split("/")[1:]
    if (
        not path.is_absolute()
        or value != str(path)
        or any(segment in {"", ".", ".."} for segment in segments)
    ):
        raise SpecMismatch(f"{label} is not canonical absolute")
    if any(
        node.is_symlink()
        for node in (path, *path.parents)
        if node.exists() or node.is_symlink()
    ):
        raise SpecMismatch(f"{label} contains a symlinked component")
    resolved = path.resolve(strict=False)
    if value != str(resolved):
        raise SpecMismatch(f"{label} is not its canonical resolved spelling")
    return resolved


def _validate_scalar(value: Any, schema: Mapping[str, Any], label: str) -> None:
    type_name = schema.get("type", "")
    constraint = schema.get("constraint", "")
    if "JSON integer" in type_name:
        if type(value) is not int:
            raise SpecMismatch(f"{label} must be a JSON integer")
        if ">=0" in constraint and value < 0:
            raise SpecMismatch(f"{label} must be nonnegative")
        if ">0" in constraint and value <= 0:
            raise SpecMismatch(f"{label} must be positive")
    elif "JSON Boolean" in type_name:
        if type(value) is not bool:
            raise SpecMismatch(f"{label} must be a JSON Boolean")
    elif "UTF-8 string" in type_name:
        if type(value) is not str:
            raise SpecMismatch(f"{label} must be a UTF-8 string")
        if "nonempty" in constraint and not value:
            raise SpecMismatch(f"{label} must be nonempty")
        if "64 lowercase hexadecimal" in constraint and not _HEX64.fullmatch(value):
            raise SpecMismatch(f"{label} must be a lowercase SHA-256")
        if "40 lowercase hexadecimal" in constraint and not _HEX40.fullmatch(value):
            raise SpecMismatch(f"{label} must be a lowercase Git commit")
        if "RFC3339 UTC" in constraint and not _RFC3339_UTC.fullmatch(value):
            raise SpecMismatch(f"{label} must be RFC3339 UTC")
        if "RFC3339 UTC" in constraint:
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as error:
                raise SpecMismatch(f"{label} is not a real RFC3339 timestamp") from error
        if "begins with /" in constraint:
            _canonical_absolute_destination(value, label=label)
    elif type(value) is float and not math.isfinite(value):
        raise SpecMismatch(f"{label} must be finite")


def validate_schema_value(value: Any, schema: Mapping[str, Any], *, label: str) -> None:
    """Validate the executable closed/type subset used by all v23 record schemas."""
    kind = schema.get("kind")
    if kind == "literal":
        if value != schema.get("value") or type(value) is not type(schema.get("value")):
            raise SpecMismatch(f"{label} literal disagrees")
        return
    if kind == "enum":
        if value not in schema.get("values", []):
            raise SpecMismatch(f"{label} is outside the frozen enum")
        return
    if kind == "enum_or_stage_status":
        if type(value) is not str or not value:
            raise SpecMismatch(f"{label} must be a nonempty status string")
        return
    if kind == "scalar":
        _validate_scalar(value, schema, label)
        return
    if kind == "nullable":
        if value is not None:
            validate_schema_value(value, schema["value"], label=label)
        return
    if kind == "literal_array":
        if value != schema.get("values"):
            raise SpecMismatch(f"{label} literal array disagrees")
        return
    if kind == "closed_string_map":
        if type(value) is not dict or any(
            type(key) is not str or type(item) is not str or not item
            for key, item in value.items()
        ):
            raise SpecMismatch(f"{label} must be a closed nonempty-string map")
        return
    if kind in {"row_reference", "exact_reference"}:
        if "expected_values" in schema and value != schema["expected_values"]:
            raise SpecMismatch(f"{label} exact frozen value disagrees")
        nested = schema.get("shape")
        if nested is not None:
            validate_schema_value(value, nested, label=label)
        elif "keys" in schema:
            validate_schema_value(
                value,
                {
                    "kind": "closed_object",
                    "keys": schema["keys"],
                    "properties": schema.get("properties", {}),
                },
                label=label,
            )
        return
    if kind == "array":
        if type(value) is not list:
            raise SpecMismatch(f"{label} must be an array")
        cardinality = schema.get("cardinality")
        if cardinality is not None and len(value) != cardinality:
            raise SpecMismatch(f"{label} cardinality disagrees")
        item_schema = schema.get("item")
        if item_schema:
            for index, item in enumerate(value):
                validate_schema_value(item, item_schema, label=f"{label}/{index}")
        required_roles = schema.get("required_roles")
        if required_roles is not None and [item.get("role") for item in value] != required_roles:
            raise SpecMismatch(f"{label} role order disagrees")
        expected_paths = schema.get("expected_paths")
        if expected_paths is not None and [item.get("path") for item in value] != expected_paths:
            raise SpecMismatch(f"{label} path order disagrees")
        duplicates = schema.get("duplicates", "")
        if duplicates and all(type(item) is dict for item in value):
            for key in ("role", "path"):
                if key in duplicates:
                    items = [item.get(key) for item in value]
                    if len(items) != len(set(items)):
                        raise SpecMismatch(f"{label} duplicates {key}")
        return
    if kind == "closed_signed_identity":
        shape = schema.get("shape")
        if not isinstance(shape, Mapping):
            raise SpecMismatch(f"{label} signed-identity shape is absent")
        validate_schema_value(value, shape, label=label)
        return
    if kind == "closed_object":
        keys = schema.get("keys")
        if type(value) is not dict or type(keys) is not list or set(value) != set(keys):
            raise SpecMismatch(f"{label} is not the required closed object")
        for key in keys:
            property_schema = schema.get("properties", {}).get(key)
            if property_schema is not None:
                validate_schema_value(value[key], property_schema, label=f"{label}/{key}")
        return
    if kind == "closed_tagged_union":
        if type(value) is not dict:
            raise SpecMismatch(f"{label} must be an object")
        tag = schema["tag"]
        variant = schema.get("variants", {}).get(value.get(tag))
        if variant is None:
            raise SpecMismatch(f"{label} has an unknown tagged-union variant")
        validate_schema_value(value, {"kind": "closed_object", **variant}, label=label)
        return
    raise SpecMismatch(f"{label} uses unsupported frozen schema kind {kind!r}")


def _authorization_guard(authorization: Mapping[str, Any]) -> Mapping[str, Any]:
    guard = authorization.get("v23_single_attempt_guard")
    if not isinstance(guard, Mapping):
        raise SpecMismatch("v23 authorization has no single-attempt guard")
    return guard


def completion_writer_descriptor(authorization: Mapping[str, Any], source: Path | None, *, original_path: str | None) -> dict[str, Any]:
    """Retain the original record identity; measure the supplied archived bytes."""
    if source is None or not original_path:
        raise IncompleteCampaign("explicit historical completion-writer input and original identity required")
    rows = [row for row in authorization["executing_code"]
            if row.get("role") == "v23_completion_writer"]
    if len(rows) != 1 or set(rows[0]) != {"role", "path", "size_bytes", "sha256"}:
        raise SpecMismatch("historical completion-writer descriptor is not unique/complete")
    row = rows[0]
    if row["path"] != original_path:
        raise SpecMismatch("historical completion-writer original identity disagrees")
    size, digest = _identity(Path(source))
    if (size, digest) != (row["size_bytes"], row["sha256"]):
        raise SpecMismatch("historical completion-writer input disagrees with its commitment")
    return dict(row)


def remeasure_authorization_descriptor(
    row: Mapping[str, Any], *, repo_root: Path,
    completion_writer_input: Path | None, completion_writer_original_path: str | None,
    historical_inputs=None,
) -> Path:
    """Remeasure relocated writer evidence without reopening its old location."""
    if row.get("role") == "v23_completion_writer":
        completion_writer_descriptor(
            {"executing_code": [row]}, completion_writer_input,
            original_path=completion_writer_original_path,
        )
        return Path(completion_writer_input)
    # The relocation manifest points to preserved bytes, not current source files.
    if historical_inputs is not None:
        key = row["path"] + "@" + row["sha256"]
        if key in historical_inputs.manifest["files"] or row["path"] in historical_inputs.manifest["files"]:
            validate_identity_descriptor(dict(row), repo_root=repo_root, measure=False)
            path = historical_inputs.path(row["path"], expected_sha256=row["sha256"])
            if _identity(path) != (row["size_bytes"], row["sha256"]):
                raise SpecMismatch("historical relocated descriptor byte count disagrees")
            return path
        if row["path"].startswith(("scripts/", "src/", "vendor/", "born_route_rebuild1_spec")):
            raise IncompleteCampaign("missing preserved historical identity: " + row["path"])
    return validate_identity_descriptor(row, repo_root=repo_root)


def validate_v23_authorization(
    spec: FrozenSpec,
    authorization: Any,
    *,
    allow_publication_fallback_probe: bool = False,
    measure_current_implementation: bool = True,
    remeasure_bound_evidence: bool = True,
    completion_writer_input: Path | None = None,
    completion_writer_original_path: str | None = None,
) -> None:
    # Destination and retired-identity checks happen before the attempt exists.
    # The mutable current implementation census is deliberately measured only
    # after acquisition, so a disagreement realizes v24.8 with a consumed guard.
    if measure_current_implementation:
        try:
            audit_v23_contracts(spec)
        except (IncompleteCampaign, SpecMismatch) as error:
            raise SpecMismatch(
                "spec_mismatch:current_implementation_manifest_identity"
            ) from error
    contract = spec.get("/completeness/g2c_v24_evaluation_authorization", expected_type=dict)
    if type(authorization) is dict and authorization.get("schema") == "RB1_G2C_V22_EVALUATION_AUTHORIZATION_V1":
        raise SpecMismatch("spec_mismatch:v23_authorization_guard_identity")
    if type(authorization) is not dict or set(authorization) != set(contract["keys"]):
        raise SpecMismatch("spec_mismatch:v23_authorization_guard_identity")
    if authorization.get("schema") != contract["record_schema"]:
        raise SpecMismatch("spec_mismatch:v23_authorization_guard_identity")
    for key, item_schema in contract["types"].items():
        schema = copy.deepcopy(item_schema)
        if allow_publication_fallback_probe and key == "authorized_outputs":
            schema.pop("expected_values", None)
        validate_schema_value(authorization[key], schema, label=f"authorization/{key}")
    if authorization["publication_spec_identity"] != publication_identity(spec):
        if not allow_publication_fallback_probe:
            raise SpecMismatch("spec_mismatch:v22_publication_fallback")
    if authorization["source_spec_identity"] != source_identity(spec):
        raise SpecMismatch("spec_mismatch:v23_authorization_guard_identity")
    if authorization["v23_evaluation_count"] != 1 or authorization["sealed_input_reuse_authorized"] is not True:
        raise SpecMismatch("spec_mismatch:v23_authorization_guard_identity")
    route = spec.get("/completeness/g2c_v24_sealed_input_route", expected_type=dict)
    expected_outputs = contract["types"]["authorized_outputs"]["expected_values"]
    if (
        not allow_publication_fallback_probe
        and authorization["authorized_outputs"] != expected_outputs
    ):
        raise SpecMismatch("spec_mismatch:v22_publication_fallback")
    if (
        authorization["complete_input_identities"]
        != route["input_bindings"] + route["complete_dependency_closure"]
        or authorization["historical_evaluation_authorization"]
        != route["consumed_v21_evaluation_authorization"]
        or authorization["reused_campaign_side_receipts"]
        != route["reused_campaign_side_receipts"]
        or authorization["preserved_v21_outcome_evidence"]
        != route["source_outcome_evidence"]
        or authorization["sealed_input_route_sha256"]
        != sha256_bytes(canonical_json_bytes(route))
        or authorization["approved_rotation_contract_sha256"]
        != sha256_bytes(canonical_json_bytes(spec.get(
            "/completeness/g2c_raw_stdout_derivation/controls/rotation",
            expected_type=dict,
        )))
    ):
        raise SpecMismatch("v23 evaluation authorization frozen bindings disagree")
    freeze = spec.get(
        "/provenance/publication_environment_freeze_measurement/evidence",
        expected_type=dict,
    )
    transition = spec.get(
        "/provenance/environment_transitions/0/package_update_evidence",
        expected_type=dict,
    )
    environment = authorization["publication_environment_evidence"]
    if (
        len(environment) != 3
        or environment[0] != {"role": "v23_freeze_environment_census", **freeze}
        or environment[1] != {"role": "v23_glibc_transition_evidence", **transition}
        or environment[2].get("role") != "v23_execution_environment_admission"
    ):
        raise SpecMismatch("v23 publication-environment evidence disagrees")
    if measure_current_implementation:
        rows = {row["role"]: row for row in authorization["executing_code"]}
        expected_code = []
        for path, role in sorted(_REQUIRED_EXECUTING_CODE, key=lambda item: item[0].encode("utf-8")):
            row = rows.get(role)
            if row is None or row["path"] != path:
                raise SpecMismatch("historical executing-source identity differs")
            remeasure_authorization_descriptor(row, repo_root=spec.repo_root,
                completion_writer_input=completion_writer_input,
                completion_writer_original_path=completion_writer_original_path,
                historical_inputs=getattr(spec, "history", None))
            expected_code.append(dict(row))
        expected_code.append(completion_writer_descriptor(authorization, completion_writer_input, original_path=completion_writer_original_path))
        expected_code.sort(key=lambda row: row["path"].encode("utf-8"))
        by_role = {row["role"]: row for row in expected_code}
        expected_reviewed = [
            by_role["v23_evaluator_entrypoint"], by_role["v23_completion_writer"],
            *[
                row for row in expected_code
                if row["role"] not in {"v23_evaluator_entrypoint", "v23_completion_writer"}
            ],
        ]
        expected_manifest = dict(authorization["implementation_manifest"])
        if expected_manifest["path"] != "scripts/rebuild1/implementation_manifest.jsonl" or expected_manifest["role"] != "current_implementation_manifest":
            raise SpecMismatch("historical implementation-manifest identity differs")
        remeasure_authorization_descriptor(expected_manifest, repo_root=spec.repo_root,
            completion_writer_input=completion_writer_input,
            completion_writer_original_path=completion_writer_original_path,
            historical_inputs=getattr(spec, "history", None))
        expected_launcher = by_role["v23_completion_writer"]
        if measure_current_implementation and (
            authorization["executing_code"] != expected_code
            or authorization["reviewed_responsibility_code"] != expected_reviewed
            or authorization["implementation_manifest"] != expected_manifest
            or _authorization_guard(authorization)["mechanism_identity"] != expected_launcher
        ):
            raise SpecMismatch("spec_mismatch:current_implementation_manifest_identity")
    descriptor_groups = [
        authorization["complete_input_identities"],
        authorization["preserved_v21_outcome_evidence"],
        authorization["publication_environment_evidence"],
        authorization["reused_campaign_side_receipts"],
        [authorization["historical_evaluation_authorization"]],
        [authorization["preserved_v21_guard_launcher"]],
    ]
    if measure_current_implementation:
        descriptor_groups.extend([
            authorization["executing_code"],
            authorization["reviewed_responsibility_code"],
            [authorization["implementation_manifest"]],
            [_authorization_guard(authorization)["mechanism_identity"]],
        ])
    if remeasure_bound_evidence:
        for rows in descriptor_groups:
            for row in rows:
                remeasure_authorization_descriptor(
                    row, repo_root=spec.repo_root,
                    completion_writer_input=completion_writer_input,
                    completion_writer_original_path=completion_writer_original_path,
                    historical_inputs=getattr(spec, "history", None),
                )


def _historical_manifest_bytes(spec: FrozenSpec) -> tuple[dict[str, Any], bytes, tuple[str, ...]]:
    route = spec.get("/completeness/g2c_v24_sealed_input_route", expected_type=dict)
    recovery = route.get("recovery_resolution")
    if type(recovery) is not dict or type(recovery.get("selectors")) is not list:
        raise IncompleteCampaign("incomplete:historical_dependency_recovery")
    selector = recovery["selectors"][0]
    graph = recovery.get("graph_interpretation")
    blob = selector.get("immutable_git_blob") if type(selector) is dict else None
    pointer = "/completeness/g2c_v24_sealed_input_route/recovery_resolution/selectors/0"
    if (
        selector != _V24_HISTORICAL_MANIFEST_SELECTOR
        or type(blob) is not dict
        or graph != {
            "current_node_id": "current_implementation_manifest",
            "current_resolved_graph_location": ["filesystem", "canonical_resolved_absolute_destination"],
            "current_role": "current_implementation_manifest",
            "current_textual_path": "scripts/rebuild1/implementation_manifest.jsonl",
            "historical_node_id": "historical_implementation_manifest",
            "historical_resolved_graph_location": [
                "immutable_git_blob", "bound_repository_root", blob.get("commit"),
                blob.get("path"), blob.get("git_object_id_sha1"),
            ],
            "historical_role": "historical_implementation_manifest",
            "historical_textual_path": "scripts/rebuild1/implementation_manifest.jsonl",
            "same_path_exception": "exactly this historical/current pair; no other role, node ID, digest, selector, path or filesystem destination",
            "selector_pointer": pointer,
            "validation_only_not_serialized": True,
        }
        or selector.get("original_path") != blob.get("path")
        or selector.get("selector_order") != ["immutable_git_blob"]
        or blob.get("git_object_type") != "blob"
    ):
        raise IncompleteCampaign("incomplete:historical_dependency_recovery")
    root = spec.repo_root.resolve()
    object_id = blob["git_object_id_sha1"]
    history = getattr(spec, "history", None)
    if history is None:
        raise IncompleteCampaign("explicit historical_root is required for historical manifest bytes")
    raw = history.commit_bytes(blob["commit"], blob["path"],
        expected_sha256=blob["sha256"], object_id=object_id)
    if len(raw) != blob["size_bytes"] or len(raw) != selector["expected_size_bytes"] or sha256_bytes(raw) != selector["expected_sha256"]:
        raise IncompleteCampaign("incomplete:historical_dependency_recovery")
    descriptor = {
        "role": "historical_implementation_manifest",
        "path": selector["original_path"],
        "size_bytes": len(raw),
        "sha256": sha256_bytes(raw),
    }
    location = (
        "immutable_git_blob", str(root), blob["commit"], blob["path"], object_id,
    )
    return descriptor, raw, location


def _graph_node_bytes(
    spec: FrozenSpec, row: Mapping[str, Any], *, repo_root: Path,
    completion_writer_input: Path | None = None,
    completion_writer_original_path: str | None = None,
) -> tuple[bytes, tuple[str, ...]]:
    if row.get("node_id") == "historical_implementation_manifest" or row.get("role") == "historical_implementation_manifest":
        descriptor, raw, location = _historical_manifest_bytes(spec)
        if row != {"node_id": "historical_implementation_manifest", **descriptor}:
            raise SpecMismatch("historical manifest graph node disagrees with the frozen selector")
        return raw, location
    descriptor = {key: row[key] for key in ("role", "path", "size_bytes", "sha256")}
    path = remeasure_authorization_descriptor(
        descriptor, repo_root=repo_root,
        completion_writer_input=completion_writer_input,
        completion_writer_original_path=completion_writer_original_path,
        historical_inputs=getattr(spec, "history", None),
    )
    raw = path.read_bytes()
    return raw, ("filesystem", str(path.resolve(strict=False)))


def _graph_node_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    preferred = ["historical_implementation_manifest", "publication_companion"]
    role = row["role"]
    return (
        1 if role == "publication_companion" else
        2 if role == "v23_evaluation_authorization" else
        3 if role in {"attempt_guard_state", "units", "controls", "package_reconstruction", "evaluation"} else
        4 if role == "execution_record" else
        5 if role == "completion_receipt" else 0,
        preferred.index(role) if role in preferred else 99,
        role.encode("utf-8"), row["path"].encode("utf-8"), row["node_id"].encode("utf-8"),
    )


def _graph_binding_relation(
    spec: FrozenSpec, nodes: Sequence[Mapping[str, Any]],
    *,
    completion_writer_input: Path | None = None,
    completion_writer_original_path: str | None = None,
) -> set[tuple[str, str, str]]:
    """Discover every raw-byte digest binding before choosing a graph order."""
    raw_by_id: dict[str, bytes] = {}
    parsed_by_id: dict[str, Any] = {}
    for row in nodes:
        raw, _ = _graph_node_bytes(spec, row, repo_root=spec.repo_root.resolve(),
            completion_writer_input=completion_writer_input,
            completion_writer_original_path=completion_writer_original_path,
        )
        raw_by_id[row["node_id"]] = raw
        try:
            parsed_by_id[row["node_id"]] = parse_canonical_json(
                raw, label=f"graph successor {row['node_id']}",
            )
        except SpecMismatch:
            pass
    predecessor_ids: dict[str, list[str]] = {}
    for predecessor_id, raw in raw_by_id.items():
        predecessor_ids.setdefault(sha256_bytes(raw), []).append(predecessor_id)

    def bindings(value: Any, pointer: str = "") -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        if type(value) is dict:
            for key, child in value.items():
                escaped = key.replace("~", "~0").replace("/", "~1")
                found.extend(bindings(child, f"{pointer}/{escaped}"))
        elif type(value) is list:
            for index, child in enumerate(value):
                found.extend(bindings(child, f"{pointer}/{index}"))
        elif type(value) is str:
            found.extend((node_id, pointer) for node_id in predecessor_ids.get(value, ()))
        return found

    relation: set[tuple[str, str, str]] = set()
    for successor_id, successor in parsed_by_id.items():
        for predecessor_id, pointer in bindings(successor):
            if predecessor_id != successor_id:
                relation.add((predecessor_id, successor_id, pointer))
    return relation


def _topological_graph_nodes(
    nodes: Sequence[Mapping[str, Any]], relation: set[tuple[str, str, str]],
) -> list[dict[str, Any]]:
    by_id = {row["node_id"]: copy.deepcopy(dict(row)) for row in nodes}
    incoming = {node_id: set() for node_id in by_id}
    outgoing = {node_id: set() for node_id in by_id}
    for predecessor, successor, _ in relation:
        incoming[successor].add(predecessor)
        outgoing[predecessor].add(successor)
    ready = sorted(
        (by_id[node_id] for node_id, parents in incoming.items() if not parents),
        key=_graph_node_sort_key,
    )
    ordered: list[dict[str, Any]] = []
    while ready:
        row = ready.pop(0)
        ordered.append(row)
        for successor in sorted(outgoing[row["node_id"]]):
            incoming[successor].discard(row["node_id"])
            if not incoming[successor]:
                candidate = by_id[successor]
                if candidate not in ready and candidate not in ordered:
                    ready.append(candidate)
                    ready.sort(key=_graph_node_sort_key)
    if len(ordered) != len(nodes):
        raise SpecMismatch("hash-binding relation contains a cycle")
    return ordered


def build_hash_graph(spec: FrozenSpec, nodes: Sequence[Mapping[str, Any]],
    *,
    completion_writer_input: Path | None = None,
    completion_writer_original_path: str | None = None,
) -> dict[str, Any]:
    relation = _graph_binding_relation(spec, nodes,
        completion_writer_input=completion_writer_input,
        completion_writer_original_path=completion_writer_original_path,
    )
    ordered = _topological_graph_nodes(nodes, relation)
    positions = {row["node_id"]: index for index, row in enumerate(ordered)}
    edges = [{
        "predecessor_node_id": predecessor,
        "successor_node_id": successor,
        "binding_field": pointer,
    } for predecessor, successor, pointer in relation]
    edges.sort(key=lambda edge: (
        positions[edge["successor_node_id"]], positions[edge["predecessor_node_id"]],
        edge["binding_field"].encode("utf-8"),
    ))
    return {
        "serialization": "canonical compact sorted-key JSON, UTF-8, final LF",
        "nodes": ordered,
        "edges": edges,
        "topological_order": [row["node_id"] for row in ordered],
    }


def _independent_raw_binding_census(
    spec: FrozenSpec, nodes: Sequence[Mapping[str, Any]], *, repo_root: Path,
    completion_writer_input: Path | None = None,
    completion_writer_original_path: str | None = None,
) -> set[tuple[str, str, str]]:
    """Validator-side binding census, deliberately independent of the builder."""
    measured: dict[str, str] = {}
    parsed: dict[str, Any] = {}
    for row in nodes:
        raw, _ = _graph_node_bytes(spec, row, repo_root=repo_root,
            completion_writer_input=completion_writer_input,
            completion_writer_original_path=completion_writer_original_path,
        )
        measured[row["node_id"]] = sha256_bytes(raw)
        try:
            parsed[row["node_id"]] = parse_canonical_json(
                raw, label=f"independent graph successor {row['node_id']}",
            )
        except SpecMismatch:
            pass

    ids_by_digest: dict[str, list[str]] = {}
    for node_id, digest in measured.items():
        ids_by_digest.setdefault(digest, []).append(node_id)

    def locations(value: Any, pointer: str = "") -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        if isinstance(value, dict):
            for key, child in value.items():
                escaped = key.replace("~", "~0").replace("/", "~1")
                result += locations(child, f"{pointer}/{escaped}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                result += locations(child, f"{pointer}/{index}")
        elif type(value) is str:
            result += [(node_id, pointer) for node_id in ids_by_digest.get(value, ())]
        return result

    return {
        (predecessor_id, successor_id, pointer)
        for successor_id, successor in parsed.items()
        for predecessor_id, pointer in locations(successor)
        if predecessor_id != successor_id
    }
