"""Evaluator for signed-v24 publication under retained-v23 G2c names."""
from __future__ import annotations
import argparse
import copy
import json
import os
import sys
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from born_ladder.snapshot.artifact_paths import authorized_output_path, reject_symlink_chain
from born_ladder.snapshot.completeness import AttemptRegistry, _capture_inventory, assess_completeness, load_structural_gate
from born_ladder.snapshot.errors import (
    BlockedInfrastructure,
    ControlFailureEvidence,
    IncompleteCampaign,
    Rebuild1Error,
    SpecMismatch,
)
from born_ladder.reproduction.specification import PublicSpecification as FrozenSpec
from born_ladder.snapshot.frozen_spec import canonical_json_bytes, sha256_bytes
from born_ladder.reproduction.predictive.g2c_campaign import _contract as _campaign_contract, validate_g2c_invocation_manifest_records, validate_v21_campaign_timeout_artifact
from born_ladder.snapshot.g2c_collector_structural import segment_census_record
from born_ladder.snapshot.g2c_controls import build_g2c_controls
from born_ladder.snapshot.g2c_evaluate import evaluate_g2c_records
from born_ladder.snapshot.g2c_units import derive_sealed_g2c_unit_drafts, finalize_g2c_artifacts, validate_g2c_artifacts
from born_ladder.snapshot.inventory import build_inventory
from born_ladder.snapshot.provenance import ProvenanceFiles, file_sha256, validate_provenance
from born_ladder.snapshot.status import preemptive_status
_POINTERS = {
    "g2c_entry_archive": "/completeness/g2c_raw_stdout_derivation/archive2_consumption_binding",
    "g2c_entry_campaign": "/confirmation_data/campaigns/6",
    "g2c_entry_derivation": "/completeness/g2c_raw_stdout_derivation",
    "g2c_entry_matrix": "/completeness/expected_matrices/6",
    "g2c_entry_namespace": "/artifact_paths/namespace",
    "g2c_entry_pins": "/provenance/candidate_pins",
    "g2c_entry_plan": "/artifact_paths/g2c_per_unit_reproduction_plan",
    "g2c_entry_shapes": "/completeness/universal_evidence_shapes",
    "g2c_entry_statuses": "/status_sets/global_preemptive_by_stage/G2C",
    "g2c_entry_v23_route": "/completeness/g2c_v24_sealed_input_route",
    "g2c_entry_v23_prepublication": "/completeness/g2c_v24_prepublication_provenance_record",
    "g2c_entry_v23_absence": "/artifact_paths/g2c_v23_output_absence",
}
@dataclass(frozen=True)
class G2CEvaluationArtifacts:
    units_path: Path
    controls_path: Path
    package_reconstruction_path: Path
    evaluation_path: Path
    evaluation: Mapping[str, Any]
@dataclass(frozen=True)
class G2CLoadedAdmission:
    """Independent campaign documents retained after ordered admission."""

    admission_record: Mapping[str, Any]
    receipt_paths: Mapping[str, Path]
    root: Path
    names: Sequence[str]
    campaign_path: Path
    campaign: Mapping[str, Any]
    traceability: Mapping[str, Any]
@dataclass(frozen=True)
class G2CBoundInputs:
    """Closed input identities retained after aggregate sealed-input admission."""

    paths: Mapping[str, Path]
    sha256s: Mapping[str, str]
    capture_root: Path
_G2C_EXECUTION_INPUT_ROLES = [
    "campaign",
    "capture_inventory",
    "collector_structural_capture",
    "implementation_manifest",
    "invocation_manifest",
    "runner_structural_capture",
    "sealed_attempt_registry",
    "structural_acceptance",
    "structural_acceptance_signature",
    "structural_manifest",
    "v21_execution_policy",
]
_G2C_ARCHIVAL_LOCAL_ROLES = [
    "campaign", "collector_structural_capture", "invocation_manifest",
    "runner_structural_capture", "sealed_attempt_registry",
    "structural_acceptance", "structural_acceptance_signature",
    "structural_manifest",
]
_G2C_ARCHIVAL_RECOVERY_ROLES = [
    "implementation_manifest", "v21_execution_policy",
]
_G2C_REFERENCE_ENVIRONMENT_FIELDS = [
    "architecture", "cargo", "glibc", "kernel", "numpy", "os", "pydantic",
    "python", "python_lock_sha256", "rustc", "scipy",
]
_G2C_INVENTORY_REPORT_FIELDS = [
    "definition_sha256", "independent_runner_mode", "inventory_stdout_sha256",
    "labels", "labels_count", "runner", "runner_equals_frozen",
    "runner_equals_source", "runner_sha256", "source", "source_equals_frozen",
    "source_sha256",
]
_G2C_UNIT_ACCOUNTING_FIELDS = [
    "cpu_accounting", "exit_code", "exit_utc", "launch_utc",
    "memory_accounting", "unit",
]
_G2C_V22_GUARD_ID = "RB1_G2C_V22_SINGLE_ATTEMPT_GUARD_V1"
_G2C_V22_GUARD_MECHANISM = "atomic_O_CREAT_O_EXCL_canonical_attempt_record"
_G2C_V21_GUARD_LAUNCHER = []  # historical launcher accounting removed
_G2C_V22_EXECUTING_CODE = [
    ("scripts/rebuild1/evaluate_g2c_campaign.py", "v22_evaluator_entrypoint"),
    ("scripts/rebuild1/evidence.py", "v22_evidence_validator"),
    ("scripts/rebuild1/frozen_spec.py", "v22_sealed_source_loader"),
    ("scripts/rebuild1/g2c_controls.py", "v22_rotation_control"),
    ("scripts/rebuild1/g2c_evaluate.py", "v22_scientific_evaluator"),
    ("scripts/rebuild1/g2c_rotation_certificate.py", "v22_rotation_certificate"),
    ("scripts/rebuild1/g2c_units.py", "v22_unit_finalizer"),
    ("scripts/rebuild1/g2c_v22_launcher.py", "v22_pre_dispatch_attempt_guard_launcher"),
    ("scripts/rebuild1/universal_shapes.py", "v22_universal_validator"),
]
_G2C_V22_REVIEWED_LAUNCHERS = [
    ("scripts/rebuild1/g2c_v22_launcher.py", "v22_pre_dispatch_attempt_guard_launcher"),
    ("scripts/rebuild1/evaluate_g2c_campaign.py", "v22_evaluation_entrypoint"),
]
_G2C_CANONICAL_SERIALIZATION = {
    "python_expression": (
        "json.dumps(value,sort_keys=True,separators=(',',':'),"
        "ensure_ascii=False).encode('utf-8') + b'\\n'"
    ),
    "encoding": "UTF-8",
    "object_key_order": "lexicographic Unicode code-point order from sort_keys=True",
    "separators": [",", ":"],
    "ensure_ascii": False,
    "final_lf": True,
}
_G2C_CAPTURE_INVENTORY_CONTRACT = {
    "row_keys": ["path", "sha256", "size_bytes"],
    "path_basis": "POSIX path relative to the content-addressed capture root",
    "path_order": "ascending bytewise order of root-relative POSIX paths encoded as UTF-8",
    "node_rule": "recursive regular files only; symlinks reject; directories are not rows",
    "type_counts_keys": ["attempt_sidecar", "stderr", "stdout"],
    "type_suffixes": {
        "attempt_sidecar": ".attempt.json",
        "stderr": ".stderr.bin",
        "stdout": ".stdout.bin",
    },
    "unknown_suffix_disposition": "reject",
    "canonical_rows_digest": "SHA-256(C(ordered inventory rows))",
    "summary_keys": ["file_count", "sha256", "total_size_bytes", "type_counts"],
    "receipt_digest": "SHA-256(C(summary object))",
}
_G2C_EXECUTION_ROLE_DERIVATIONS: Mapping[str, Mapping[str, Any]] = {
    "campaign": {
        "source": "fixed_artifact", "artifact_index": 5,
        "path": "namespace / rb1v2_g2c_campaign.json",
    },
    "capture_inventory": {
        "source": "capture_root_inventory", "artifact_index": 1,
        "path": "namespace / rb1v2_g2c_campaign_attempts_content_addressed",
        "digest": "SHA-256(C(capture inventory summary))",
    },
    "collector_structural_capture": {
        "source": "campaign_binding", "campaign_field": "collector_structural_capture",
        "path_rule": "content-addressed namespace child <sha256>.json",
    },
    "implementation_manifest": {
        "source": "fixed_repository_path",
        "path": "implementation_manifest.jsonl",
    },
    "invocation_manifest": {
        "source": "campaign_binding", "campaign_field": "invocation_manifest",
        "artifact_index": 0,
        "path_rule": "exact namespace / rb1v2_g2c_invocation_manifest.json",
    },
    "runner_structural_capture": {
        "source": "campaign_binding", "campaign_field": "runner_structural_capture",
        "path_rule": "content-addressed namespace child <sha256>.json",
    },
    "sealed_attempt_registry": {
        "source": "campaign_binding", "campaign_field": "attempt_registry",
        "path_rule": "content-addressed namespace child <sha256>.json",
    },
    "structural_acceptance": {
        "source": "fixed_artifact", "artifact_index": 3,
        "path": "namespace / rb1v2_g2c_structural_acceptance.json",
    },
    "structural_acceptance_signature": {
        "source": "fixed_artifact", "artifact_index": 4,
        "path": "namespace / rb1v2_g2c_structural_acceptance.json.sig",
    },
    "structural_manifest": {
        "source": "campaign_binding", "campaign_field": "structural_manifest",
        "artifact_index": 2,
        "path_rule": "exact namespace / rb1v2_g2c_structural_manifest.jsonl",
    },
    "v21_execution_policy": {
        "source": "campaign_binding", "campaign_field": "execution_policy",
        "path_rule": "content-addressed namespace child <sha256>.json",
    },
}
_G2C_SPEC_IDENTITY_CONTRACT = {
    "keys": ["freeze_commit", "json_sha256", "spec_id", "tag"],
    "field_types": {
        "freeze_commit": "40-character lowercase-hex commit string",
        "json_sha256": "lowercase-hex SHA-256 string",
        "spec_id": "string; exactly born-route-rebuild1.v21",
        "tag": "string; exactly born-route-rebuild1-v21-freeze",
    },
    "derivation": "signed-v21 FrozenSpec attestation; no caller substitution",
}
_G2C_TIMEOUT_DESCRIPTOR_CONTRACT = {
    "outer_keys": [
        "agreement_rule", "descriptors", "historical_shapes", "ordered_channels",
        "schema_version",
    ],
    "descriptor_map_keys": [
        "attempt_sidecar", "campaign_provenance", "execution_policy",
        "retry_identity", "subprocess_argument",
    ],
    "descriptor_keys": [
        "channel", "container", "field_name", "field_type", "required",
        "schema_version", "value", "value_json_pointer",
    ],
    "derivation": (
        "exact deep copy of /confirmation_data/g2c_v21_execution/"
        "timeout_channel_descriptors; every value is the pointer-served integer 1800"
    ),
}
G2C_RECEIPT_CONTRACTS: Mapping[str, Mapping[str, Any]] = {
    "execution_authorization": {
        "schema": "RB1_G2C_V21_EXECUTION_AUTHORIZATION_V1",
        "required_fields": [
            "authorized_campaign_identity", "authorized_invocation_manifest_sha256",
            "execution_environment_allowlist", "preflight_receipt_sha256",
            "schema", "spec_identity",
        ],
        "derivation": "pre-run authorization over signed-v21 preflight and planned manifest",
        "canonical_serialization": "sorted compact UTF-8 JSON followed by LF",
        "canonical_serialization_contract": _G2C_CANONICAL_SERIALIZATION,
        "field_types": {
            "authorized_campaign_identity": "string",
            "authorized_invocation_manifest_sha256": "lowercase-hex SHA-256 string",
            "execution_environment_allowlist": "closed object<string,string>; exactly {}",
            "preflight_receipt_sha256": "lowercase-hex SHA-256 string",
            "schema": "string",
            "spec_identity": "closed object",
        },
        "field_derivations": {
            "authorized_campaign_identity": "literal g2c_v2",
            "authorized_invocation_manifest_sha256": (
                "SHA-256 of the canonical persisted invocation-manifest bytes"
            ),
            "execution_environment_allowlist": (
                "exact subprocess environment passed to every runner child; the closed empty map"
            ),
            "preflight_receipt_sha256": (
                "SHA-256 of the canonical preflight receipt named by the admission identity"
            ),
            "schema": "literal RB1_G2C_V21_EXECUTION_AUTHORIZATION_V1",
            "spec_identity": (
                "closed {freeze_commit,json_sha256,spec_id,tag} from signed v21"
            ),
        },
        "nested_contracts": {
            "execution_environment_allowlist": {
                "keys": [],
                "derivation": "exact frozen runner-child environment",
            },
            "spec_identity": _G2C_SPEC_IDENTITY_CONTRACT,
        },
    },
    "preflight_receipt": {
        "schema": "RB1_G2C_V21_PREFLIGHT_RECEIPT_V1",
        "required_fields": [
            "campaign_identity", "inventory_report", "reference_environment", "schema",
            "spec_identity", "timeout_channel_descriptors",
        ],
        "derivation": "canonical output of build_g2c_preflight_report(spec)",
        "canonical_serialization": "sorted compact UTF-8 JSON followed by LF",
        "canonical_serialization_contract": _G2C_CANONICAL_SERIALIZATION,
        "field_types": {
            "campaign_identity": "string",
            "inventory_report": "closed object",
            "reference_environment": "closed object<string,string>",
            "schema": "string",
            "spec_identity": "closed object",
            "timeout_channel_descriptors": "closed object",
        },
        "field_derivations": {
            "campaign_identity": "literal g2c_v2",
            "inventory_report": (
                "InventoryAuthorization.report from live pinned runner/source measurement; "
                "all twelve fields follow nested_contracts.inventory_report"
            ),
            "reference_environment": (
                "measure_reference_environment(spec), field-for-field equal to the eleven "
                "/provenance/candidate_pins named by nested_contracts.reference_environment"
            ),
            "schema": "literal RB1_G2C_V21_PREFLIGHT_RECEIPT_V1",
            "spec_identity": "signed-v21 FrozenSpec attestation",
            "timeout_channel_descriptors": (
                "exact deep copy of /confirmation_data/g2c_v21_execution/"
                "timeout_channel_descriptors"
            ),
        },
        "nested_contracts": {
            "inventory_report": {
                "keys": _G2C_INVENTORY_REPORT_FIELDS,
                "field_types": {
                    "definition_sha256": "closed object<string,lowercase-hex SHA-256 string>",
                    "independent_runner_mode": "string; exactly LIVE_RUNNER_MATCH",
                    "inventory_stdout_sha256": "lowercase-hex SHA-256 string",
                    "labels": "ordered array<string>",
                    "labels_count": "integer",
                    "runner": "absolute-path string",
                    "runner_equals_frozen": "boolean; exactly true",
                    "runner_equals_source": "boolean; exactly true",
                    "runner_sha256": "lowercase-hex SHA-256 string",
                    "source": "absolute-path string",
                    "source_equals_frozen": "boolean; exactly true",
                    "source_sha256": "lowercase-hex SHA-256 string",
                },
                "derivation": (
                    "InventoryAuthorization.report from the live pinned runner/source "
                    "three-way inventory measurement"
                ),
            },
            "reference_environment": {
                "keys": _G2C_REFERENCE_ENVIRONMENT_FIELDS,
                "field_types": {name: "string" for name in _G2C_REFERENCE_ENVIRONMENT_FIELDS},
                "derivation": (
                    "measure_reference_environment(spec); every value equals the "
                    "corresponding /provenance/candidate_pins value"
                ),
            },
            "spec_identity": _G2C_SPEC_IDENTITY_CONTRACT,
            "timeout_channel_descriptors": _G2C_TIMEOUT_DESCRIPTOR_CONTRACT,
        },
    },
    "execution_receipt": {
        "schema": "RB1_G2C_V21_EXECUTION_RECEIPT_V1",
        "required_fields": [
            "campaign_sha256", "execution_environment_allowlist", "input_sha256s",
            "pre_run_execution_authorization_sha256", "preflight_receipt_sha256",
            "preflight_reference_environment_sha256", "schema", "spec_identity",
            "unit_accounting",
        ],
        "derivation": "post-run accounting and measured campaign input/environment identities",
        "canonical_serialization": "sorted compact UTF-8 JSON followed by LF",
        "canonical_serialization_contract": _G2C_CANONICAL_SERIALIZATION,
        "field_types": {
            "campaign_sha256": "lowercase-hex SHA-256 string",
            "execution_environment_allowlist": "closed object<string,string>; exactly {}",
            "input_sha256s": "closed object<string,lowercase-hex SHA-256 string>",
            "pre_run_execution_authorization_sha256": "lowercase-hex SHA-256 string",
            "preflight_receipt_sha256": "lowercase-hex SHA-256 string",
            "preflight_reference_environment_sha256": "lowercase-hex SHA-256 string",
            "schema": "string",
            "spec_identity": "closed object",
            "unit_accounting": "closed object",
        },
        "field_derivations": {
            "campaign_sha256": "streamed SHA-256 of the fixed campaign artifact",
            "execution_environment_allowlist": (
                "exact frozen runner-child environment; closed empty object"
            ),
            "input_sha256s": (
                "closed role map derived by role_derivations and capture_inventory_contract"
            ),
            "pre_run_execution_authorization_sha256": (
                "SHA-256 of canonical execution_authorization bytes"
            ),
            "preflight_receipt_sha256": "SHA-256 of canonical preflight_receipt bytes",
            "preflight_reference_environment_sha256": (
                "SHA-256(C(preflight_receipt.reference_environment))"
            ),
            "schema": "literal RB1_G2C_V21_EXECUTION_RECEIPT_V1",
            "spec_identity": "signed-v21 FrozenSpec attestation",
            "unit_accounting": "manager launch/accounting receipt per nested contract",
        },
        "role_derivations": _G2C_EXECUTION_ROLE_DERIVATIONS,
        "capture_inventory_contract": _G2C_CAPTURE_INVENTORY_CONTRACT,
        "nested_contracts": {
            "execution_environment_allowlist": {
                "keys": [],
                "derivation": "exact closed subprocess environment; not controller environment",
            },
            "input_sha256s": {
                "keys": _G2C_EXECUTION_INPUT_ROLES,
                "derivation": (
                    "streamed SHA-256 of each named file; capture_inventory is SHA-256(C({"
                    "file_count,sha256,total_size_bytes,type_counts})), where sha256 is "
                    "SHA-256(C(sorted recursive regular-file {path,sha256,size_bytes} rows))"
                ),
            },
            "unit_accounting": {
                "keys": _G2C_UNIT_ACCOUNTING_FIELDS,
                "field_types": {
                    "cpu_accounting": "boolean",
                    "exit_code": "integer",
                    "exit_utc": "RFC3339 UTC string",
                    "launch_utc": "RFC3339 UTC string",
                    "memory_accounting": "boolean",
                    "unit": "nonempty string",
                },
                "derivation": (
                    "manager launch receipt: systemd unit, UTC launch/exit, integer exit code, "
                    "and booleans recording CPUAccounting/MemoryAccounting"
                ),
            },
            "spec_identity": _G2C_SPEC_IDENTITY_CONTRACT,
        },
    },
    "evaluation_authorization": {
        "schema": "RB1_G2C_V22_EVALUATION_AUTHORIZATION_V1",
        "required_fields": [
            "approved_rotation_contract_sha256", "authorized_outputs",
            "complete_input_identities", "executing_code",
            "historical_evaluation_authorization", "implementation_manifest",
            "planned_process", "preserved_v21_guard_launcher",
            "preserved_v21_outcome_evidence",
            "publication_spec_identity", "reused_campaign_side_receipts",
            "reviewed_launchers",
            "schema", "sealed_input_reuse_authorized",
            "sealed_input_route_sha256", "source_spec_identity",
            "v22_evaluation_count", "v22_single_attempt_guard",
        ],
        "derivation": "pre-evaluation authorization for one signed-v22 sealed-input evaluation",
        "canonical_serialization": "sorted compact UTF-8 JSON followed by LF",
        "canonical_serialization_contract": _G2C_CANONICAL_SERIALIZATION,
        "field_types": {
            "approved_rotation_contract_sha256": "lowercase-hex SHA-256 string",
            "authorized_outputs": "ordered array of four repository-relative paths",
            "complete_input_identities": "ordered array<identity_row>",
            "executing_code": "ordered array<identity_row>",
            "historical_evaluation_authorization": "identity_row",
            "implementation_manifest": "identity_row",
            "planned_process": "closed object {argv,cwd,environment}",
            "preserved_v21_guard_launcher": "identity_row",
            "preserved_v21_outcome_evidence": "ordered array<identity_row>",
            "publication_spec_identity": "closed signed-v22 six-field identity",
            "reused_campaign_side_receipts": "ordered array<identity_row>",
            "reviewed_launchers": "ordered array<identity_row>",
            "schema": "string",
            "sealed_input_reuse_authorized": "boolean true",
            "sealed_input_route_sha256": "lowercase-hex SHA-256 string",
            "source_spec_identity": "closed signed-v21 six-field identity",
            "v22_evaluation_count": "JSON integer exactly 1",
            "v22_single_attempt_guard": "closed distinct guard identity",
        },
        "field_derivations": {
            "approved_rotation_contract_sha256": "SHA-256(C(current v22 G2c rotation object))",
            "authorized_outputs": "exact /artifact_paths/g2c_v22_output_absence/v22_outputs",
            "complete_input_identities": "exact route input_bindings followed by complete_dependency_closure",
            "executing_code": "ordered identities for every executing v22 implementation module named by the authorization",
            "historical_evaluation_authorization": "exact route consumed_v21_evaluation_authorization",
            "implementation_manifest": "identity row for the current reviewed v22 implementation manifest",
            "planned_process": "manager-authorized exact argv, absolute cwd and closed environment",
            "preserved_v21_guard_launcher": (
                "measured identity of the archived v21 exclusive-guard launcher"
            ),
            "preserved_v21_outcome_evidence": "exact route source_outcome_evidence",
            "publication_spec_identity": (
                "closed six-field signed-v22 loader identity: companion basename, "
                "whole-file companion SHA-256, embedded companion self-hash, freeze commit, "
                "spec id and signed tag"
            ),
            "reused_campaign_side_receipts": "exact route reused_campaign_side_receipts",
            "reviewed_launchers": "exact identities in the fixed reviewed-launcher census",
            "schema": "literal RB1_G2C_V22_EVALUATION_AUTHORIZATION_V1",
            "sealed_input_reuse_authorized": "literal true",
            "sealed_input_route_sha256": "SHA-256(C(/completeness/g2c_v22_sealed_input_route))",
            "source_spec_identity": "closed six-field /completeness/g2c_v22_sealed_input_route/source_identity",
            "v22_evaluation_count": "JSON integer literal 1",
            "v22_single_attempt_guard": "closed distinct v22 guard binding with the v21 guard preserved",
        },
        "nested_contracts": {
            "identity_row": {
                "keys": ["path", "role", "sha256", "size_bytes"],
                "order": "frozen route order",
            },
            "planned_process": {
                "keys": ["argv", "cwd", "environment"],
                "cwd": "absolute measured execution directory",
            },
            "v22_single_attempt_guard": {
                "keys": [
                    "authorized_attempts", "execution_record_path",
                    "failed_attempt_evidence_path", "guard_id", "mechanism",
                    "mechanism_identity", "state_path", "v21_guard_preserved",
                ],
                "derivation": (
                    "authorized_attempts is JSON integer 1; guard_id is the literal "
                    "RB1_G2C_V22_SINGLE_ATTEMPT_GUARD_V1; mechanism is atomic "
                    "O_CREAT|O_EXCL creation of state_path before reconstruction; "
                    "mechanism_identity is the fixed pre-dispatch launcher identity; "
                    "the canonical execution record binds the authorization, guard, "
                    "source/publication identities and final preemption audit; a failed "
                    "attempt is retained at failed_attempt_evidence_path and is never retried"
                ),
            },
        },
    },
    "archival_supplement": {
        "schema": "RB1_G2C_V21_ARCHIVAL_SUPPLEMENT_V1",
        "required_fields": [
            "campaign_inputs", "capture_inventory", "execution_receipt_sha256",
            "local_outputs", "recovery_dependencies", "schema", "spec_identity",
        ],
        "derivation": "noncircular post-campaign registry of local outputs and recovery dependencies",
        "canonical_serialization": "sorted compact UTF-8 JSON followed by LF",
        "canonical_serialization_contract": _G2C_CANONICAL_SERIALIZATION,
        "field_types": {
            "campaign_inputs": "closed object<string,lowercase-hex SHA-256 string>",
            "capture_inventory": "closed object",
            "execution_receipt_sha256": "lowercase-hex SHA-256 string",
            "local_outputs": "ordered array<identity_row>",
            "recovery_dependencies": "ordered array<identity_row>",
            "schema": "string",
            "spec_identity": "closed object",
        },
        "field_derivations": {
            "campaign_inputs": "byte-identical copy from execution_receipt.input_sha256s",
            "capture_inventory": (
                "root and measured summary fields derived by capture_inventory_contract"
            ),
            "execution_receipt_sha256": "SHA-256 of canonical execution_receipt bytes",
            "local_outputs": (
                "identity rows in required_local_output_roles order, using role_derivations"
            ),
            "recovery_dependencies": (
                "identity rows in required_recovery_dependency_roles order, using role_derivations"
            ),
            "schema": "literal RB1_G2C_V21_ARCHIVAL_SUPPLEMENT_V1",
            "spec_identity": "signed-v21 FrozenSpec attestation",
        },
        "role_derivations": _G2C_EXECUTION_ROLE_DERIVATIONS,
        "capture_inventory_contract": _G2C_CAPTURE_INVENTORY_CONTRACT,
        "required_local_output_roles": _G2C_ARCHIVAL_LOCAL_ROLES,
        "required_recovery_dependency_roles": _G2C_ARCHIVAL_RECOVERY_ROLES,
        "nested_contracts": {
            "campaign_inputs": {
                "keys": _G2C_EXECUTION_INPUT_ROLES,
                "derivation": "byte-identical copy from the admitted execution receipt",
            },
            "capture_inventory": {
                "keys": [
                    "canonical_inventory_sha256", "file_count", "root", "size_bytes"
                ],
                "field_types": {
                    "canonical_inventory_sha256": "lowercase-hex SHA-256 string",
                    "file_count": "positive integer",
                    "root": "normalized repository-relative directory path string",
                    "size_bytes": "positive integer",
                },
                "derivation": (
                    "root is the repository-relative content-addressed capture root; "
                    "other fields are recomputed from its sorted recursive regular-file inventory"
                ),
            },
            "identity_row": {
                "keys": ["path", "role", "sha256", "size_bytes"],
                "field_types": {
                    "path": "normalized repository-relative regular-file path string",
                    "role": "string from the ordered role contract",
                    "sha256": "lowercase-hex SHA-256 string",
                    "size_bytes": "nonnegative integer",
                },
                "order": {
                    "local_outputs": _G2C_ARCHIVAL_LOCAL_ROLES,
                    "recovery_dependencies": _G2C_ARCHIVAL_RECOVERY_ROLES,
                },
                "derivation": (
                    "repository-relative non-symlink regular-file path, streamed SHA-256, "
                    "and exact byte count"
                ),
            },
            "spec_identity": _G2C_SPEC_IDENTITY_CONTRACT,
        },
    },
}
for _receipt_role, _receipt_contract in G2C_RECEIPT_CONTRACTS.items():
    _cli_name = _receipt_role.replace("_", "-")
    _receipt_contract["receipt_identity_contract"] = {
        "path_argument": f"--{_cli_name}",
        "sha256_argument": f"--{_cli_name}-sha256",
        "path_derivation": (
            "manager-supplied repository or external records path; resolve without "
            "symlinks and require a regular file"
        ),
        "sha256_derivation": (
            "streamed SHA-256 of the exact canonical receipt bytes at path_argument"
        ),
        "admission_rule": (
            "the supplied digest equals the measured digest and the file bytes equal "
            "the canonical_serialization_contract applied to the parsed closed object"
        ),
    }
def g2c_receipt_contracts() -> dict[str, Any]:
    """Return the complete public manager-facing receipt construction contract."""
    return copy.deepcopy(dict(G2C_RECEIPT_CONTRACTS))
def _g2c_capture_inventory(capture_root: Path) -> dict[str, Any]:
    """Measure the inventory using the algorithm published in the receipt contract."""
    contract = _G2C_CAPTURE_INVENTORY_CONTRACT
    inventory = _capture_inventory(capture_root)
    suffixes = contract["type_suffixes"]
    measured_counts = {name: 0 for name in contract["type_counts_keys"]}
    children = sorted(
        capture_root.rglob("*"),
        key=lambda path: path.relative_to(capture_root).as_posix().encode("utf-8"),
    )
    for path in children:
        if path.is_symlink():
            raise IncompleteCampaign("G2c capture inventory contains a symlink")
        if path.is_dir():
            continue
        if not path.is_file():
            raise IncompleteCampaign("G2c capture inventory contains a non-regular node")
        relative = path.relative_to(capture_root).as_posix()
        matches = [name for name, suffix in suffixes.items() if relative.endswith(suffix)]
        if len(matches) != 1:
            raise IncompleteCampaign("G2c capture inventory has an additional child type")
        measured_counts[matches[0]] += 1
    if (
        sorted(inventory) != sorted(contract["summary_keys"])
        or list(inventory.get("type_counts", {})) != contract["type_counts_keys"]
        or inventory.get("type_counts") != measured_counts
        or inventory.get("file_count") != sum(measured_counts.values())
    ):
        raise IncompleteCampaign("G2c capture inventory contract derivation disagrees")
    return inventory
def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
def _contract(spec: FrozenSpec, manifest: Path | None = None) -> dict[str, Any]:
    spec.audit_implementation_manifest(
        "evaluate_g2c_campaign", manifest_path=manifest, declared_pointers=_POINTERS
    )
    value = {name.removeprefix("g2c_entry_"): spec.get(pointer) for name, pointer in _POINTERS.items()}
    expected = [
        "rb1v2_g2c_invocation_manifest.json",
        "rb1v2_g2c_campaign_attempts_content_addressed/",
        "rb1v2_g2c_structural_manifest.jsonl",
        "rb1v2_g2c_structural_acceptance.json",
        "rb1v2_g2c_structural_acceptance.json.sig",
        "rb1v2_g2c_campaign.json",
        "rb1v2_g2c_v23_units.jsonl",
        "rb1v2_g2c_v23_controls.jsonl",
        "rb1v2_g2c_v23_pkg_reconstruction.jsonl",
        "rb1v2_g2c_v23_evaluation.json",
    ]
    if (
        value["plan"].get("artifacts") != expected
        or value["plan"].get("publication_count") != 4
        or value["plan"].get("archive_binding_pointer") != _POINTERS["g2c_entry_archive"]
        or value["matrix"].get("campaign") != "g2c"
        or value["matrix"].get("expected_invocations") != 1500
        or value["campaign"].get("name") != "g2c_v2"
        or value["statuses"] != [
            "G2C_V2_SPEC_MISMATCH", "G2C_V2_BLOCKED_INFRASTRUCTURE",
            "G2C_V2_INCOMPLETE", "G2C_V2_CONTROL_FAILURE",
        ]
        or value["derivation"]["controls"]["evaluation_order"] != [
            "G2C_V2_SPEC_MISMATCH", "G2C_V2_BLOCKED_INFRASTRUCTURE",
            "G2C_V2_INCOMPLETE", "G2C_V2_CONTROL_FAILURE", "table 9",
        ]
    ):
        raise SpecMismatch("frozen G2c entrypoint identities disagree")
    value["artifacts"] = expected
    return value
def _canonical_object(path: Path, root: Path) -> tuple[dict[str, Any], bytes]:
    reject_symlink_chain(path, repo_root=root)
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IncompleteCampaign(f"G2c campaign artifact is unavailable: {error}") from error
    if type(value) is not dict or canonical_json_bytes(value) != raw:
        raise IncompleteCampaign("G2c campaign artifact is not canonical JSON")
    return value, raw
def _empty_preemption_findings() -> dict[str, list[dict[str, Any]]]:
    return {
        "spec_mismatch": [], "blocked": [], "incomplete": [],
        "control_failure": [],
    }
def _merge_preemption_findings(
    target: dict[str, list[dict[str, Any]]],
    source: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    for condition in target:
        target[condition].extend(
            copy.deepcopy([dict(row) for row in source.get(condition, ())])
        )
def _require_execution_input_bindings(
    admission_record: Mapping[str, Any], actual: Mapping[str, str], *,
    spec: FrozenSpec | None = None,
    campaign: Mapping[str, Any] | None = None,
    campaign_path: Path | None = None,
    actual_paths: Mapping[str, Path] | None = None,
) -> None:
    if admission_record.get("input_sha256s") != dict(actual):
        raise IncompleteCampaign("G2c execution receipt input bindings disagree")
    if spec is None or campaign is None or campaign_path is None or actual_paths is None:
        return
    if admission_record.get("campaign_sha256") != file_sha256(campaign_path):
        raise IncompleteCampaign("G2c execution campaign identity disagrees")
    if admission_record.get("authorized_invocation_manifest_sha256") != actual.get(
        "invocation_manifest"
    ):
        raise IncompleteCampaign("G2c pre-run invocation authorization disagrees")
    provenance = campaign.get("provenance")
    source_spec = getattr(spec, "_g2c_source_spec", spec)
    pins = source_spec.get("/provenance/candidate_pins", expected_type=dict)
    reference_environment = admission_record.get("preflight_reference_environment")
    expected_host = {
        "architecture": pins["architecture"],
        "os": pins["os"],
    }
    expected_definitions = {
        row["experiment"]: row["sha256"]
        for row in source_spec.get("/grid/definition_identities", expected_type=list)
    }
    if (
        type(provenance) is not dict
        or provenance.get("attestation_tag") != source_spec.attestation.tag
        or provenance.get("attested_json_sha256") != source_spec.attestation.json_sha256
        or provenance.get("freeze_payload_commit") != source_spec.attestation.freeze_commit
        or provenance.get("spec_id") != source_spec.attestation.spec_id
        or provenance.get("runner_binary_path_sha256") != {
            "path": pins["runner_binary"],
            "sha256": pins["runner_binary_sha256"],
        }
        or provenance.get("runner_source_sha256") != pins["runner_source_sha256"]
        or provenance.get("environment_allowlist")
        != admission_record.get("execution_environment_allowlist")
        or provenance.get("python_version") != reference_environment.get("python")
        or provenance.get("python_environment_lock_sha256")
        != reference_environment.get("python_lock_sha256")
        or provenance.get("host_os_architecture") != expected_host
        or provenance.get("Cargo.lock_sha256") != pins["Cargo.lock_sha256"]
        or provenance.get("cargo_version") != reference_environment.get("cargo")
        or provenance.get("rustc_version") != reference_environment.get("rustc")
        or provenance.get("experiment_definition_hashes") != expected_definitions
        or provenance.get("attested_markdown_sha256")
        != source_spec.attestation.markdown_sha256
        or provenance.get("vendored_source_commit")
        != source_spec.attestation.freeze_commit
    ):
        raise IncompleteCampaign("G2c campaign attestation, runner, or environment binding disagrees")

    archive_contract = G2C_RECEIPT_CONTRACTS["archival_supplement"]
    row_groups = {
        "local_outputs": admission_record.get("archival_local_outputs"),
        "recovery_dependencies": admission_record.get("archival_recovery_dependencies"),
    }
    for group_name, rows in row_groups.items():
        required_key = (
            "required_local_output_roles"
            if group_name == "local_outputs"
            else "required_recovery_dependency_roles"
        )
        if [row["role"] for row in rows] != archive_contract[required_key]:
            raise IncompleteCampaign(f"G2c archival {group_name} role order disagrees")
        for row in rows:
            role = row["role"]
            if role == "implementation_manifest":
                selector = spec.get(
                    _POINTERS["g2c_entry_v23_route"], expected_type=dict
                )["recovery_resolution"]["selectors"][0]
                if (
                    row["path"] != selector["original_path"]
                    or row["size_bytes"] != selector["expected_size_bytes"]
                    or row["sha256"] != selector["expected_sha256"]
                    or actual.get(role) != selector["expected_sha256"]
                ):
                    raise IncompleteCampaign(
                        "G2c archival historical implementation identity disagrees"
                    )
                continue
            if role not in actual_paths or role not in actual:
                raise IncompleteCampaign(f"G2c archival role {role} has no execution binding")
            path = actual_paths[role]
            expected_relative = path.resolve().relative_to(spec.repo_root).as_posix()
            if (
                row["path"] != expected_relative
                or path.is_symlink()
                or not path.is_file()
                or row["size_bytes"] != path.stat().st_size
                or row["sha256"] != actual[role]
                or file_sha256(path) != row["sha256"]
            ):
                raise IncompleteCampaign(f"G2c archival role {role} identity disagrees")

    capture = admission_record.get("archival_capture_inventory")
    capture_root = actual_paths.get("capture_root")
    if not isinstance(capture_root, Path):
        raise IncompleteCampaign("G2c capture root has no archival binding")
    reject_symlink_chain(capture_root, repo_root=spec.repo_root)
    inventory = _g2c_capture_inventory(capture_root)
    inventory_digest = sha256_bytes(canonical_json_bytes(inventory))
    if (
        capture_root.is_symlink()
        or not capture_root.is_dir()
        or capture.get("root")
        != capture_root.resolve().relative_to(spec.repo_root).as_posix()
        or capture.get("file_count") != inventory["file_count"]
        or capture.get("size_bytes") != inventory["total_size_bytes"]
        or capture.get("canonical_inventory_sha256") != inventory["sha256"]
        or actual.get("capture_inventory") != inventory_digest
    ):
        raise IncompleteCampaign("G2c archival capture-inventory identity disagrees")
def _admit_loaded_execution_bindings(
    spec: FrozenSpec,
    loaded: G2CLoadedAdmission,
    *,
    actual: Mapping[str, str],
    actual_paths: Mapping[str, Path],
) -> None:
    """Apply execution-chain equality checks to the campaign bytes admitted above."""
    _require_execution_input_bindings(
        loaded.admission_record,
        actual,
        spec=spec,
        campaign=loaded.campaign,
        campaign_path=loaded.campaign_path,
        actual_paths=actual_paths,
    )
def _append_preemption_error(
    findings: dict[str, list[dict[str, Any]]], *, stage: str, error: Exception,
) -> None:
    condition = (
        "spec_mismatch" if isinstance(error, SpecMismatch)
        else "blocked" if isinstance(error, BlockedInfrastructure)
        else "control_failure" if isinstance(error, ControlFailureEvidence)
        else "incomplete"
    )
    findings[condition].append({
        "stage": stage,
        "unit_id": getattr(error, "unit_id", None),
        "kind_cell_id": getattr(error, "kind_cell_id", None),
        "invariant": type(error).__name__,
        "detail": str(error),
    })
def _bound_path(
    identity: Any,
    *,
    root: Path,
    exact: Path | None = None,
    content_addressed: bool = False,
) -> tuple[Path, str]:
    if type(identity) is not dict or set(identity) != {"path", "sha256"}:
        raise IncompleteCampaign("G2c campaign input identity is not closed")
    path = Path(identity["path"])
    if not path.is_absolute():
        path = root / path
    reject_symlink_chain(path, repo_root=root)
    if exact is not None and path.resolve() != exact.resolve():
        raise IncompleteCampaign("G2c campaign input path is not the frozen path")
    if content_addressed and (
        path.resolve().parent != root.resolve()
        or path.name != f'{identity["sha256"]}.json'
    ):
        raise IncompleteCampaign("G2c campaign input is not content-addressed")
    if file_sha256(path) != identity["sha256"]:
        raise IncompleteCampaign("G2c campaign input hash disagrees")
    return path.resolve(), identity["sha256"]
def _traceability_binding(spec: FrozenSpec, contract: Mapping[str, Any]) -> dict[str, Any]:
    archive = contract["archive"]
    if (
        archive.get("consumes_adopted_results") is not False
        or archive.get("adopted_result_inputs") != []
        or archive.get("traceability_only") is not True
        or archive.get("verification_claimed_for_large_adopted_artifacts") is not False
    ):
        raise SpecMismatch("frozen G2c non-consumption archive contract disagrees")
    rows = [archive["large_output_manifest"], *archive["traceability_references"]]
    measured = []
    for identity in rows:
        if type(identity) is not dict or set(identity) != {"path", "sha256"}:
            raise SpecMismatch("frozen G2c traceability identity is malformed")
        path = spec.repo_root / identity["path"]
        reject_symlink_chain(path, repo_root=spec.repo_root)
        if file_sha256(path) != identity["sha256"]:
            raise IncompleteCampaign("G2c traceability identity disagrees")
        measured.append(dict(identity))
    return {
        "consumes_adopted_results": False,
        "traceability_only": True,
        "verified_identities": measured,
        "verification_claimed_for_large_adopted_artifacts": False,
    }
def _validate_stdout_bindings(campaign: Mapping[str, Any], registry: AttemptRegistry) -> None:
    rows = campaign.get("stdout_execution_bindings")
    if not isinstance(rows, list):
        raise IncompleteCampaign("G2c stdout binding census is absent")
    seen = set()
    for row in rows:
        if type(row) is not dict or set(row) != {
            "attempt_record_sha256", "invocation_id", "stdout_path", "stdout_sha256"
        }:
            raise IncompleteCampaign("G2c stdout binding shape disagrees")
        identity = row["invocation_id"]
        path, digest = registry.successful_capture_identity(identity)
        if (
            identity in seen
            or Path(row["stdout_path"]).resolve() != path.resolve()
            or row["stdout_sha256"] != digest
            or row["attempt_record_sha256"] != registry.successful_attempt_record_sha256(identity)
        ):
            raise IncompleteCampaign("G2c stdout binding identity disagrees")
        seen.add(identity)
    if seen != registry.invocation_ids():
        raise IncompleteCampaign("G2c stdout bindings do not cover the invocation census")
from born_ladder.snapshot.evaluate_g2c_campaign import (
    G2CEvaluationAdmission,
    G2CLateFailure,
    G2CPreempted,
    G2CPreparedArtifacts,
    G2CReceiptIdentity,
    _expected_reference_environment,
    _fixed_identity_rows,
    _initial_scientific_findings,
    _is_sha256,
    _load_receipt,
    _v22_guard_forbidden_paths,
    _validate_archival_identity_rows,
    _validate_preflight_inventory,
    _validate_receipt_input_map,
    _validate_unit_accounting,
)
