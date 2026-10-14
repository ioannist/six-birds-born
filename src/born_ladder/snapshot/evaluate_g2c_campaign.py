"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import copy
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from born_ladder.snapshot.artifact_paths import reject_symlink_chain
from born_ladder.snapshot.completeness import AttemptRegistry
from born_ladder.snapshot.errors import BlockedInfrastructure, ControlFailureEvidence, IncompleteCampaign, SpecMismatch
from born_ladder.snapshot.frozen_spec import FrozenSpec, canonical_json_bytes, sha256_bytes
from born_ladder.snapshot.g2c_controls import build_g2c_controls
from born_ladder.snapshot.g2c_evaluate import evaluate_g2c_records
from born_ladder.snapshot.g2c_units import derive_sealed_g2c_unit_drafts, finalize_g2c_artifacts, validate_g2c_artifacts
from born_ladder.snapshot.guard_checks import validate_guard_destinations as _validate_guard_destinations
from born_ladder.snapshot.g2c_v23 import publication_identity as v23_publication_identity, source_identity as v23_source_identity, validate_v23_authorization
from born_ladder.snapshot.provenance import file_sha256
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
class G2CPreparedArtifacts:
    """Validated inputs that may cross the pre-statistics boundary."""

    built: Any

    rotation_evidence: Mapping[str, Mapping[str, Any]]



@dataclass(frozen=True)
class G2CReceiptIdentity:
    path: Path

    sha256: str



@dataclass(frozen=True)
class G2CEvaluationAdmission:
    execution_authorization: G2CReceiptIdentity

    preflight_receipt: G2CReceiptIdentity

    execution_receipt: G2CReceiptIdentity

    evaluation_authorization: G2CReceiptIdentity

    archival_supplement: G2CReceiptIdentity



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


_G2C_V21_GUARD_LAUNCHER = [
    (
        "docs/internal/born_route_review/g2c_outcome_package/evaluation/g2c_eval_launch.sh",
        "preserved_v21_attempt_guard_launcher",
    ),
]


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
        "path": "scripts/rebuild1/implementation_manifest.jsonl",
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


class G2CPreempted(IncompleteCampaign):
    """Ordered, persisted-ready G2c campaign disposition."""

    def __init__(self, audit: Mapping[str, Any]):
        self.audit = copy.deepcopy(dict(audit))
        selected = self.audit["selected_condition"]
        details = "; ".join(
            str(row.get("detail", row))
            for row in self.audit["findings_by_condition"][selected]
        )
        super().__init__(f'{self.audit["selected_status"]}: {details}')



class G2CLateFailure(IncompleteCampaign):
    """Terminal post-computation failure owned by the completion workflow."""

    scientific_evaluation_performed = True

    def __init__(
        self, detail: str, *, failed_operation: str = "before_first_output",
        complete_roles: Sequence[str] = (), partial_roles: Sequence[str] = (),
        findings_by_condition: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ):
        self.failed_operation = failed_operation
        self.complete_roles = list(complete_roles)
        self.partial_roles = list(partial_roles)
        self.findings_by_condition = {
            condition: [copy.deepcopy(dict(row)) for row in (findings_by_condition or {}).get(condition, ())]
            for condition in ("spec_mismatch", "blocked", "incomplete", "control_failure")
        }
        super().__init__(detail)

    def handoff(self) -> dict[str, Any]:
        return {
            "schema": "RB1_G2C_V23_LATE_FAILURE_HANDOFF_V1",
            "failed_operation": self.failed_operation,
            "complete_roles": self.complete_roles,
            "partial_roles": self.partial_roles,
            "findings_by_condition": self.findings_by_condition,
            "scientific_evaluation_performed": True,
            "detail": str(self),
        }



def _load_receipt(
    identity: G2CReceiptIdentity, *, repo_root: Path, role: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    if type(identity) is not G2CReceiptIdentity or not isinstance(identity.path, Path):
        raise IncompleteCampaign(f"G2c {role} identity is not production-bound")
    path = identity.path if identity.path.is_absolute() else repo_root / identity.path
    absolute = path.absolute()
    if any(node.is_symlink() for node in (absolute, *absolute.parents)):
        raise IncompleteCampaign(f"G2c {role} path contains a symlink")
    if not path.is_file():
        raise IncompleteCampaign(f"G2c {role} is not a regular file")
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IncompleteCampaign(f"G2c {role} is unavailable: {error}") from error
    if (
        type(value) is not dict
        or canonical_json_bytes(value) != raw
        or sha256_bytes(raw) != identity.sha256
    ):
        raise IncompleteCampaign(f"G2c {role} identity disagrees")
    return value, {"path": str(path.resolve()), "sha256": identity.sha256}


def _expected_reference_environment(spec: FrozenSpec) -> dict[str, str]:
    pins = spec.get("/provenance/candidate_pins", expected_type=dict)
    expected = {
        name: pins[name]
        for name in _G2C_REFERENCE_ENVIRONMENT_FIELDS
    }
    if list(sorted(expected)) != sorted(_G2C_REFERENCE_ENVIRONMENT_FIELDS):
        raise SpecMismatch("G2c reference-environment contract is incomplete")
    return expected


def _validate_preflight_inventory(spec: FrozenSpec, report: Any) -> None:
    pins = spec.get("/provenance/candidate_pins", expected_type=dict)
    labels = spec.get("/grid/labels", expected_type=list)
    definitions = spec.get("/grid/definition_identities", expected_type=list)
    expected_definitions = {
        row["experiment"]: row["sha256"] for row in definitions
    }
    expected_stdout = sha256_bytes(("\n".join(labels) + "\n").encode("utf-8"))
    if (
        type(report) is not dict
        or list(sorted(report)) != sorted(_G2C_INVENTORY_REPORT_FIELDS)
        or report.get("definition_sha256") != expected_definitions
        or report.get("independent_runner_mode") != "LIVE_RUNNER_MATCH"
        or report.get("inventory_stdout_sha256") != expected_stdout
        or report.get("labels") != labels
        or report.get("labels_count") != len(labels)
        or report.get("source") != str(spec.repo_root / pins["runner_source"])
        or report.get("source_sha256") != pins["runner_source_sha256"]
        or report.get("runner") != str(spec.repo_root / pins["runner_binary"])
        or report.get("runner_sha256") != pins["runner_binary_sha256"]
        or any(
            report.get(name) is not True
            for name in (
                "runner_equals_frozen", "runner_equals_source",
                "source_equals_frozen",
            )
        )
    ):
        raise IncompleteCampaign("G2c preflight inventory binding disagrees")


def _validate_unit_accounting(value: Any) -> None:
    try:
        launch = datetime.fromisoformat(str(value.get("launch_utc", "")).replace("Z", "+00:00"))
        exit_time = datetime.fromisoformat(str(value.get("exit_utc", "")).replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        launch = exit_time = None
    if (
        type(value) is not dict
        or list(sorted(value)) != sorted(_G2C_UNIT_ACCOUNTING_FIELDS)
        or type(value.get("unit")) is not str
        or not value["unit"]
        or type(value.get("launch_utc")) is not str
        or not value["launch_utc"].endswith("Z")
        or type(value.get("exit_utc")) is not str
        or not value["exit_utc"].endswith("Z")
        or type(value.get("exit_code")) is not int
        or type(value.get("cpu_accounting")) is not bool
        or type(value.get("memory_accounting")) is not bool
        or launch is None
        or exit_time is None
        or launch.utcoffset() != timezone.utc.utcoffset(launch)
        or exit_time.utcoffset() != timezone.utc.utcoffset(exit_time)
        or exit_time < launch
    ):
        raise IncompleteCampaign("G2c execution unit accounting disagrees")


def _is_sha256(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _fixed_identity_rows(spec: FrozenSpec, census: Sequence[tuple[str, str]], *, recorded_rows) -> list[dict[str, Any]]:
    """Measure explicit original identities, never relocated release sources."""
    from .g2c_v23 import remeasure_authorization_descriptor
    if not isinstance(recorded_rows, list):
        raise IncompleteCampaign("explicit recorded historical source identities required")
    rows=[]
    for relative, role in census:
        selected=[r for r in recorded_rows if isinstance(r,dict) and r.get("path")==relative and r.get("role")==role]
        if len(selected)!=1:
            raise IncompleteCampaign("historical source identity census differs")
        row=selected[0]
        remeasure_authorization_descriptor(row, repo_root=spec.repo_root,
            completion_writer_input=None, completion_writer_original_path=None,
            historical_inputs=spec.history)
        rows.append(dict(row))
    return rows


def _v22_guard_forbidden_paths(spec: FrozenSpec) -> tuple[Path, ...]:
    """Resolve scientific outputs plus sealed source/history destinations."""
    namespace = (
        spec.repo_root / spec.get(_POINTERS["g2c_entry_namespace"], expected_type=str)
    ).resolve(strict=False)
    absence = spec.get(_POINTERS["g2c_entry_v23_absence"], expected_type=dict)
    protected: set[Path] = {
        (namespace / name).resolve(strict=False) for name in absence["paths"]
    }
    protected.update(
        (namespace / name).resolve(strict=False)
        for name in spec.get("/artifact_paths/artifacts/g2c", expected_type=list)
    )
    protected.add(spec.path.resolve(strict=False))
    source_spec = getattr(spec, "_g2c_source_spec", None)
    if isinstance(source_spec, FrozenSpec):
        protected.add(source_spec.path.resolve(strict=False))
    protected.update(spec.history.path(name).resolve() for name in spec.history.manifest["files"]
        if name.startswith("born_route_rebuild1_spec") and "@" not in name)

    def collect_paths(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key in {"path", "original_path", "companion"} and type(item) is str:
                    path = Path(item)
                    protected.add(
                        (path if path.is_absolute() else spec.repo_root / path).resolve(
                            strict=False
                        )
                    )
                else:
                    collect_paths(item)
        elif isinstance(value, list):
            for item in value:
                collect_paths(item)

    collect_paths(spec.get(_POINTERS["g2c_entry_v23_route"], expected_type=dict))
    return tuple(sorted(protected, key=lambda path: path.as_posix()))


def _validate_v22_attempt_guard(spec: FrozenSpec, guard: Any) -> None:
    expected_keys = {
        "authorized_attempts", "execution_record_path",
        "failed_attempt_evidence_path", "guard_id", "mechanism",
        "mechanism_identity", "state_path", "v21_guard_preserved",
    }
    expected_mechanism = _fixed_identity_rows(
        spec,
        [(
            "scripts/rebuild1/g2c_v22_launcher.py",
            "v22_attempt_guard_mechanism",
        )],
        recorded_rows=[guard.get("mechanism_identity")] if isinstance(guard,dict) else [],
    )[0]
    if (
        type(guard) is not dict
        or set(guard) != expected_keys
        or type(guard.get("authorized_attempts")) is not int
        or guard["authorized_attempts"] != 1
        or guard.get("guard_id") != _G2C_V22_GUARD_ID
        or guard.get("mechanism") != _G2C_V22_GUARD_MECHANISM
        or guard.get("mechanism_identity") != expected_mechanism
        or guard.get("v21_guard_preserved") is not True
    ):
        raise IncompleteCampaign("G2c v22 single-attempt guard binding disagrees")
    path_names = (
        "state_path", "failed_attempt_evidence_path", "execution_record_path",
    )
    if any(type(guard[name]) is not str for name in path_names):
        raise IncompleteCampaign("G2c v22 single-attempt guard paths disagree")
    _validate_guard_destinations(
        guard, forbidden_paths=_v22_guard_forbidden_paths(spec),
    )


def _validate_receipt_input_map(value: Any) -> None:
    if (
        type(value) is not dict
        or list(value) != _G2C_EXECUTION_INPUT_ROLES
        or any(not _is_sha256(digest) for digest in value.values())
    ):
        raise IncompleteCampaign("G2c receipt input-map shape disagrees")


def _validate_archival_identity_rows(value: Any, *, name: str) -> None:
    expected_roles = (
        _G2C_ARCHIVAL_LOCAL_ROLES
        if name == "local_outputs"
        else _G2C_ARCHIVAL_RECOVERY_ROLES
    )
    if type(value) is not list or [row.get("role") for row in value if type(row) is dict] != expected_roles:
        raise IncompleteCampaign(f"G2c archival {name} are absent or reordered")
    for row in value:
        if type(row) is not dict or set(row) != {
            "path", "role", "sha256", "size_bytes"
        }:
            raise IncompleteCampaign(f"G2c archival {name} shape disagrees")
        path = Path(row["path"])
        if (
            type(row["role"]) is not str
            or path.is_absolute()
            or ".." in path.parts
            or type(row["size_bytes"]) is not int
            or row["size_bytes"] < 0
            or not _is_sha256(row["sha256"])
        ):
            raise IncompleteCampaign(f"G2c archival {name} identity disagrees")


def _validate_receipt_semantics_independent(
    spec: FrozenSpec, *, role: str, document: Mapping[str, Any],
    completion_writer_input: Path | None = None,
    completion_writer_original_path: str | None = None,
) -> None:
    """Validate every receipt field that does not depend on another receipt."""
    contract = G2C_RECEIPT_CONTRACTS[role]
    source_spec = getattr(spec, "_g2c_source_spec", spec)
    if role == "evaluation_authorization":
        if document.get("schema") == "RB1_G2C_V23_EVALUATION_AUTHORIZATION_V1":
            try:
                validate_v23_authorization(spec, document,
                    completion_writer_input=completion_writer_input,
                    completion_writer_original_path=completion_writer_original_path,
                )
            except SpecMismatch as error:
                raise IncompleteCampaign(
                    f"G2c v23 evaluation authorization disagrees: {error}"
                ) from error
            return
        if document.get("schema") == "RB1_G2C_V21_EVALUATION_AUTHORIZATION_V1":
            expected_source = {
                "freeze_commit": source_spec.attestation.freeze_commit,
                "json_sha256": source_spec.attestation.json_sha256,
                "spec_id": source_spec.attestation.spec_id,
                "tag": source_spec.attestation.tag,
            }
            expected_fields = [
                "archival_supplement_sha256", "campaign_sha256",
                "authorized_invocation_manifest_sha256", "execution_receipt_sha256",
                "input_sha256s", "pre_run_execution_authorization_sha256",
                "preflight_receipt_sha256", "schema", "spec_identity",
            ]
            if (
                list(sorted(document)) != sorted(expected_fields)
                or document.get("spec_identity") != expected_source
            ):
                raise IncompleteCampaign("G2c historical evaluation authorization differs")
            for field in expected_fields[:7]:
                if field != "input_sha256s" and not _is_sha256(document.get(field)):
                    raise IncompleteCampaign("G2c historical evaluation authorization differs")
            _validate_receipt_input_map(document.get("input_sha256s"))
            return
        legacy_v22 = document.get("schema") == "RB1_G2C_V22_EVALUATION_AUTHORIZATION_V1"
        route = spec.get(
            "/completeness/g2c_v22_sealed_input_route"
            if legacy_v22 else _POINTERS["g2c_entry_v23_route"],
            expected_type=dict,
        )
        absence = spec.get(
            "/artifact_paths/g2c_v22_output_absence"
            if legacy_v22 else _POINTERS["g2c_entry_v23_absence"],
            expected_type=dict,
        )
        identity_spec = (
            FrozenSpec.load_g2c_v22_sealed_source(repo_root=spec.repo_root, historical_root=spec.history.root)
            if legacy_v22 else spec
        )
        publication_identity = {
            "companion": identity_spec.historical_companion,
            "companion_sha256": identity_spec.attestation.json_sha256,
            "companion_self_hash": identity_spec.payload["identity"]["json_sha256"],
            "freeze_commit": identity_spec.attestation.freeze_commit,
            "spec_id": identity_spec.attestation.spec_id,
            "tag": identity_spec.attestation.tag,
        }
        process = document.get("planned_process") if type(document) is dict else None
        guard = document.get("v22_single_attempt_guard") if type(document) is dict else None
        if (
            type(document) is not dict
            or list(sorted(document)) != sorted(contract["required_fields"])
            or document.get("schema") != contract["schema"]
            or document.get("source_spec_identity") != route["source_identity"]
            or document.get("publication_spec_identity") != publication_identity
            or document.get("sealed_input_route_sha256")
            != sha256_bytes(canonical_json_bytes(route))
            or document.get("approved_rotation_contract_sha256")
            != sha256_bytes(canonical_json_bytes(spec.get(
                "/completeness/g2c_raw_stdout_derivation/controls/rotation",
                expected_type=dict,
            )))
            or document.get("complete_input_identities")
            != route["input_bindings"] + route["complete_dependency_closure"]
            or document.get("reused_campaign_side_receipts")
            != route["reused_campaign_side_receipts"]
            or document.get("historical_evaluation_authorization")
            != route["consumed_v21_evaluation_authorization"]
            or document.get("preserved_v21_outcome_evidence")
            != route["source_outcome_evidence"]
            or document.get("preserved_v21_guard_launcher")
            != _fixed_identity_rows(spec, _G2C_V21_GUARD_LAUNCHER, recorded_rows=[document.get("preserved_v21_guard_launcher")])[0]
            or document.get("authorized_outputs") != absence["paths"][4:]
            or document.get("sealed_input_reuse_authorized") is not True
            or type(document.get("v22_evaluation_count")) is not int
            or document.get("v22_evaluation_count") != 1
            or document.get("executing_code") != _fixed_identity_rows(
                spec, _G2C_V22_EXECUTING_CODE, recorded_rows=document.get("executing_code")
            )
            or document.get("reviewed_launchers") != _fixed_identity_rows(
                spec, _G2C_V22_REVIEWED_LAUNCHERS, recorded_rows=document.get("reviewed_launchers")
            )
            or type(document.get("implementation_manifest")) is not dict
            or type(process) is not dict
            or list(process) != ["argv", "cwd", "environment"]
            or type(process.get("argv")) is not list
            or not process["argv"]
            or any(type(item) is not str or not item for item in process["argv"])
            or type(process.get("cwd")) is not str
            or not process["cwd"].startswith("/")
            or type(process.get("environment")) is not dict
            or any(type(k) is not str or type(v) is not str for k, v in process["environment"].items())
        ):
            raise IncompleteCampaign("G2c v22 evaluation authorization disagrees")
        _validate_v22_attempt_guard(spec, guard)
        for rows in (
            document["complete_input_identities"],
            document["reused_campaign_side_receipts"],
            document["preserved_v21_outcome_evidence"],
            document["executing_code"],
            document["reviewed_launchers"],
            [document["historical_evaluation_authorization"]],
            [document["preserved_v21_guard_launcher"]],
            [document["implementation_manifest"]],
        ):
            for row in rows:
                if type(row) is not dict or set(row) != {
                    "path", "role", "sha256", "size_bytes"
                } or not _is_sha256(row.get("sha256")) or type(row.get("size_bytes")) is not int:
                    raise IncompleteCampaign("G2c v22 authorization identity row disagrees")
        return

    expected_spec = {
        "freeze_commit": source_spec.attestation.freeze_commit,
        "json_sha256": source_spec.attestation.json_sha256,
        "spec_id": source_spec.attestation.spec_id,
        "tag": source_spec.attestation.tag,
    }
    if (
        type(document) is not dict
        or list(sorted(document)) != sorted(contract["required_fields"])
        or document.get("schema") != contract["schema"]
        or document.get("spec_identity") != expected_spec
    ):
        raise IncompleteCampaign(f"G2c {role} signed-spec binding disagrees")

    if role == "preflight_receipt":
        if (
            document.get("campaign_identity") != "g2c_v2"
            or document.get("timeout_channel_descriptors") != source_spec.get(
                "/confirmation_data/g2c_v21_execution/timeout_channel_descriptors",
                expected_type=dict,
            )
            or document.get("reference_environment")
            != _expected_reference_environment(source_spec)
        ):
            raise IncompleteCampaign("G2c preflight report binding disagrees")
        _validate_preflight_inventory(source_spec, document.get("inventory_report"))
        return

    if role == "execution_authorization":
        if (
            document.get("authorized_campaign_identity") != "g2c_v2"
            or not _is_sha256(document.get("authorized_invocation_manifest_sha256"))
            or not _is_sha256(document.get("preflight_receipt_sha256"))
            or document.get("execution_environment_allowlist") != {}
        ):
            raise IncompleteCampaign("G2c pre-run execution authorization disagrees")
        return

    if role == "execution_receipt":
        for field in (
            "campaign_sha256", "pre_run_execution_authorization_sha256",
            "preflight_receipt_sha256", "preflight_reference_environment_sha256",
        ):
            if not _is_sha256(document.get(field)):
                raise IncompleteCampaign("G2c execution receipt identity shape disagrees")
        if document.get("execution_environment_allowlist") != {}:
            raise IncompleteCampaign("G2c execution receipt environment disagrees")
        _validate_receipt_input_map(document.get("input_sha256s"))
        _validate_unit_accounting(document.get("unit_accounting"))
        return

    if role == "archival_supplement":
        if not _is_sha256(document.get("execution_receipt_sha256")):
            raise IncompleteCampaign("G2c archival execution identity shape disagrees")
        _validate_receipt_input_map(document.get("campaign_inputs"))
        capture = document.get("capture_inventory")
        if (
            type(capture) is not dict
            or list(sorted(capture)) != [
                "canonical_inventory_sha256", "file_count", "root", "size_bytes"
            ]
            or type(capture.get("root")) is not str
            or not capture["root"]
            or type(capture.get("file_count")) is not int
            or capture["file_count"] < 1
            or type(capture.get("size_bytes")) is not int
            or capture["size_bytes"] < 1
            or not _is_sha256(capture.get("canonical_inventory_sha256"))
        ):
            raise IncompleteCampaign("G2c archival capture-inventory binding disagrees")
        _validate_archival_identity_rows(document.get("local_outputs"), name="local_outputs")
        _validate_archival_identity_rows(
            document.get("recovery_dependencies"), name="recovery_dependencies",
        )
        if {
            row["role"] for row in document["local_outputs"]
        } & {row["role"] for row in document["recovery_dependencies"]}:
            raise IncompleteCampaign("G2c archival roles overlap")
        return

    raise AssertionError(f"unknown G2c receipt role: {role}")


def _admit_evaluation_receipts_strict(
    spec: FrozenSpec, admission: G2CEvaluationAdmission,
    *,
    completion_writer_input: Path | None = None,
    completion_writer_original_path: str | None = None,
) -> tuple[dict[str, Any], dict[str, Path]]:
    if type(admission) is not G2CEvaluationAdmission:
        raise IncompleteCampaign("G2c evaluation receipts are required")
    source_spec = getattr(spec, "_g2c_source_spec", spec)
    route = spec.get(_POINTERS["g2c_entry_v23_route"], expected_type=dict)
    fixed_receipts = {
        row["role"]: row for row in route["reused_campaign_side_receipts"]
    }
    authorization_probe, _ = _load_receipt(
        admission.evaluation_authorization,
        repo_root=spec.repo_root,
        role="evaluation_authorization",
    )
    v23_authorization = (
        authorization_probe.get("schema")
        == "RB1_G2C_V23_EVALUATION_AUTHORIZATION_V1"
    )
    v22_authorization = (
        authorization_probe.get("schema")
        == "RB1_G2C_V22_EVALUATION_AUTHORIZATION_V1"
    )
    documents: dict[str, dict[str, Any]] = {}
    retained: dict[str, dict[str, str]] = {}
    paths: dict[str, Path] = {}
    for role in (
        "execution_authorization", "preflight_receipt",
        "execution_receipt", "evaluation_authorization", "archival_supplement",
    ):
        identity = getattr(admission, role)
        if (v23_authorization or v22_authorization) and role in fixed_receipts:
            expected = fixed_receipts[role]
            supplied = identity.path if identity.path.is_absolute() else spec.repo_root / identity.path
            if (
                supplied.resolve() != (spec.repo_root / expected["path"]).resolve()
                or identity.sha256 != expected["sha256"]
            ):
                raise IncompleteCampaign(f"G2c reused {role} identity disagrees")
        document, measured = _load_receipt(
            getattr(admission, role), repo_root=spec.repo_root, role=role,
        )
        documents[role] = document
        retained[role] = measured
        paths[role] = Path(measured["path"])
    for role, document in documents.items():
        _validate_receipt_semantics_independent(
            spec, role=role, document=document,
            completion_writer_input=completion_writer_input,
            completion_writer_original_path=completion_writer_original_path,
        )

    preflight = documents["preflight_receipt"]
    timeout_descriptors = source_spec.get(
        "/confirmation_data/g2c_v21_execution/timeout_channel_descriptors",
        expected_type=dict,
    )
    reference_environment = preflight.get("reference_environment")
    if (
        preflight.get("campaign_identity") != "g2c_v2"
        or preflight.get("timeout_channel_descriptors") != timeout_descriptors
        or reference_environment != _expected_reference_environment(source_spec)
    ):
        raise IncompleteCampaign("G2c preflight report binding disagrees")
    _validate_preflight_inventory(source_spec, preflight.get("inventory_report"))

    execution_authorization = documents["execution_authorization"]
    execution_environment = execution_authorization.get(
        "execution_environment_allowlist"
    )
    if (
        execution_authorization.get("authorized_campaign_identity") != "g2c_v2"
        or execution_authorization.get("preflight_receipt_sha256")
        != retained["preflight_receipt"]["sha256"]
        or type(execution_authorization.get("authorized_invocation_manifest_sha256"))
        is not str
        or type(execution_environment) is not dict
        or any(
            type(key) is not str or type(value) is not str
            for key, value in execution_environment.items()
        )
        or execution_environment != {}
    ):
        raise IncompleteCampaign("G2c pre-run execution authorization disagrees")

    execution = documents["execution_receipt"]
    if (
        execution.get("pre_run_execution_authorization_sha256")
        != retained["execution_authorization"]["sha256"]
        or execution.get("preflight_receipt_sha256")
        != retained["preflight_receipt"]["sha256"]
        or execution.get("preflight_reference_environment_sha256")
        != sha256_bytes(canonical_json_bytes(reference_environment))
        or execution.get("execution_environment_allowlist") != execution_environment
    ):
        raise IncompleteCampaign("G2c execution receipt chain disagrees")
    _validate_unit_accounting(execution.get("unit_accounting"))

    archival = documents["archival_supplement"]
    if archival.get("execution_receipt_sha256") != retained["execution_receipt"]["sha256"]:
        raise IncompleteCampaign("G2c archival supplement execution binding disagrees")

    def validate_identity_rows(name: str) -> list[dict[str, Any]]:
        rows = archival.get(name)
        if type(rows) is not list or not rows:
            raise IncompleteCampaign(f"G2c archival {name} are absent")
        seen: set[str] = set()
        for row in rows:
            if type(row) is not dict or set(row) != {
                "path", "role", "sha256", "size_bytes"
            }:
                raise IncompleteCampaign(f"G2c archival {name} shape disagrees")
            path = Path(row["path"])
            if (
                type(row["role"]) is not str
                or not row["role"]
                or row["role"] in seen
                or path.is_absolute()
                or ".." in path.parts
                or type(row["size_bytes"]) is not int
                or row["size_bytes"] < 0
                or type(row["sha256"]) is not str
                or len(row["sha256"]) != 64
                or any(character not in "0123456789abcdef" for character in row["sha256"])
            ):
                raise IncompleteCampaign(f"G2c archival {name} identity disagrees")
            seen.add(row["role"])
        return rows

    local_outputs = validate_identity_rows("local_outputs")
    recovery_dependencies = validate_identity_rows("recovery_dependencies")
    if {row["role"] for row in local_outputs} & {
        row["role"] for row in recovery_dependencies
    }:
        raise IncompleteCampaign("G2c archival roles overlap")

    input_sha256s = documents["execution_receipt"].get("input_sha256s")
    if (
        type(input_sha256s) is not dict
        or sorted(input_sha256s) != sorted(_G2C_EXECUTION_INPUT_ROLES)
        or any(
            type(role) is not str
            or type(digest) is not str
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            for role, digest in input_sha256s.items()
        )
        or archival.get("campaign_inputs") != input_sha256s
    ):
        raise IncompleteCampaign("G2c execution-chain input bindings disagree")

    capture_inventory = archival.get("capture_inventory")
    if (
        type(capture_inventory) is not dict
        or list(sorted(capture_inventory)) != [
            "canonical_inventory_sha256", "file_count", "root", "size_bytes"
        ]
        or type(capture_inventory.get("root")) is not str
        or not capture_inventory["root"]
        or type(capture_inventory.get("file_count")) is not int
        or capture_inventory["file_count"] < 1
        or type(capture_inventory.get("size_bytes")) is not int
        or capture_inventory["size_bytes"] < 1
        or type(capture_inventory.get("canonical_inventory_sha256")) is not str
        or len(capture_inventory["canonical_inventory_sha256"]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in capture_inventory["canonical_inventory_sha256"]
        )
    ):
        raise IncompleteCampaign("G2c archival capture-inventory binding disagrees")

    evaluation_authorization = documents["evaluation_authorization"]
    if v23_authorization or v22_authorization:
        planned = evaluation_authorization["planned_process"]
        if (
            planned["cwd"] != os.getcwd()
            or planned["argv"] != list(sys.orig_argv)
            or planned["environment"] != dict(os.environ)
        ):
            raise IncompleteCampaign("G2c current authorized process differs from executing context")
    else:
        expected_source = {
            "freeze_commit": source_spec.attestation.freeze_commit,
            "json_sha256": source_spec.attestation.json_sha256,
            "spec_id": source_spec.attestation.spec_id,
            "tag": source_spec.attestation.tag,
        }
        if evaluation_authorization != {
            "archival_supplement_sha256": retained["archival_supplement"]["sha256"],
            "campaign_sha256": execution["campaign_sha256"],
            "authorized_invocation_manifest_sha256": execution_authorization[
                "authorized_invocation_manifest_sha256"
            ],
            "execution_receipt_sha256": retained["execution_receipt"]["sha256"],
            "input_sha256s": input_sha256s,
            "pre_run_execution_authorization_sha256": retained["execution_authorization"]["sha256"],
            "preflight_receipt_sha256": retained["preflight_receipt"]["sha256"],
            "schema": "RB1_G2C_V21_EVALUATION_AUTHORIZATION_V1",
            "spec_identity": expected_source,
        }:
            raise IncompleteCampaign("G2c historical evaluation authorization disagrees")
    return {
        "schema": (
            "RB1_G2C_V23_EVALUATION_ADMISSION_V1"
            if v23_authorization
            else "RB1_G2C_V22_EVALUATION_ADMISSION_V1"
            if v22_authorization
            else "RB1_G2C_V21_EVALUATION_ADMISSION_V1"
        ),
        "identities": retained,
        "input_sha256s": copy.deepcopy(input_sha256s),
        "campaign_sha256": execution["campaign_sha256"],
        "authorized_invocation_manifest_sha256": execution_authorization[
            "authorized_invocation_manifest_sha256"
        ],
        "execution_environment_allowlist": copy.deepcopy(execution_environment),
        "preflight_reference_environment": copy.deepcopy(reference_environment),
        "archival_local_outputs": copy.deepcopy(local_outputs),
        "archival_recovery_dependencies": copy.deepcopy(recovery_dependencies),
        "archival_capture_inventory": copy.deepcopy(capture_inventory),
        (
            "v23_evaluation_authorization" if v23_authorization
            else "v22_evaluation_authorization" if v22_authorization
            else "historical_evaluation_authorization"
        ): copy.deepcopy(evaluation_authorization),
    }, paths


def select_g2c_preemption(
    spec: FrozenSpec, findings: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any] | None:
    """Select the frozen global priority while retaining every applicable witness."""
    conditions = ("spec_mismatch", "blocked", "incomplete", "control_failure")
    if set(findings) - set(conditions):
        raise SpecMismatch("unknown G2c preemption condition")
    retained = {
        condition: [copy.deepcopy(dict(row)) for row in findings.get(condition, ())]
        for condition in conditions
    }
    selected = next((condition for condition in conditions if retained[condition]), None)
    if selected is None:
        return None
    audit = {
        "schema": (
            "RB1_G2C_V23_PREEMPTION_AUDIT_V1"
            if spec.attestation.spec_id == "born-route-rebuild1.v24"
            else "RB1_G2C_V22_PREEMPTION_AUDIT_V1"
            if spec.attestation.spec_id == "born-route-rebuild1.v22"
            else "RB1_G2C_V21_PREEMPTION_AUDIT_V1"
        ),
        "selected_condition": selected,
        "selected_status": preemptive_status(spec, "G2C", selected),
        "findings_by_condition": retained,
        "scientific_evaluation_performed": False,
    }
    source_spec = getattr(spec, "_g2c_source_spec", None)
    if audit["schema"] in {
        "RB1_G2C_V22_PREEMPTION_AUDIT_V1",
        "RB1_G2C_V23_PREEMPTION_AUDIT_V1",
    }:
        if not isinstance(source_spec, FrozenSpec):
            raise SpecMismatch("G2c current preemption audit lacks its sealed source identity")
        if audit["schema"] == "RB1_G2C_V23_PREEMPTION_AUDIT_V1":
            audit["source_spec_identity"] = v23_source_identity(spec)
            audit["publication_spec_identity"] = v23_publication_identity(spec)
        else:
            audit["source_spec_identity"] = {
                "spec_id": source_spec.attestation.spec_id,
                "tag": source_spec.attestation.tag,
                "json_sha256": source_spec.attestation.json_sha256,
            }
            audit["publication_spec_identity"] = {
                "spec_id": spec.attestation.spec_id,
                "tag": spec.attestation.tag,
                "json_sha256": spec.attestation.json_sha256,
            }
    return audit


def _raise_if_preempted(
    spec: FrozenSpec, findings: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    audit = select_g2c_preemption(spec, findings)
    if audit is not None:
        raise G2CPreempted(audit)


def _initial_scientific_findings(report: Any) -> dict[str, list[dict[str, Any]]]:
    """Retain every independently established pre-statistics campaign finding."""
    findings: dict[str, list[dict[str, Any]]] = {
        "spec_mismatch": [],
        "blocked": (
            [{
                "stage": report.stage,
                "unit_id": None,
                "kind_cell_id": None,
                "invariant": "completeness",
                "detail": "; ".join(report.violations),
                "violations": list(report.violations),
            }]
            if report.status and report.status.endswith("_BLOCKED_INFRASTRUCTURE") else []
        ),
        "incomplete": (
            [{
                "stage": report.stage,
                "unit_id": None,
                "kind_cell_id": None,
                "invariant": "completeness",
                "detail": "; ".join(report.violations),
                "violations": list(report.violations),
            }]
            if not report.complete and not (
                report.status and report.status.endswith("_BLOCKED_INFRASTRUCTURE")
            ) else []
        ),
        "control_failure": [],
    }
    return findings


def _derive_g2c_drafts_with_findings(
    spec: FrozenSpec, *, report: Any, registry: AttemptRegistry, gate: Any,
) -> tuple[Any, dict[str, list[dict[str, Any]]]]:
    """Run the real sealed derivation while retaining prior completeness findings."""
    findings = _initial_scientific_findings(report)
    try:
        drafts = derive_sealed_g2c_unit_drafts(
            spec, attempt_registry=registry, structural_gate=gate
        )
    except (SpecMismatch, BlockedInfrastructure, IncompleteCampaign) as error:
        condition = (
            "spec_mismatch" if isinstance(error, SpecMismatch)
            else "blocked" if isinstance(error, BlockedInfrastructure)
            else "incomplete"
        )
        findings[condition].append({
            "stage": "unit_derivation",
            "unit_id": getattr(error, "unit_id", None),
            "kind_cell_id": getattr(error, "kind_cell_id", None),
            "detail": str(error),
        })
        _raise_if_preempted(spec, findings)
        raise AssertionError("unreachable")
    return drafts, findings


def _prepare_g2c_drafts_with_findings(
    spec: FrozenSpec, *, drafts: Any,
    findings: dict[str, list[dict[str, Any]]],
) -> G2CPreparedArtifacts:
    """Run real controls/finalization and select priority after complete inspection."""
    try:
        controls = build_g2c_controls(spec, drafts.control_sources)
    except (
        SpecMismatch, BlockedInfrastructure, IncompleteCampaign,
        ControlFailureEvidence,
    ) as error:
        condition = (
            "spec_mismatch" if isinstance(error, SpecMismatch)
            else "blocked" if isinstance(error, BlockedInfrastructure)
            else "control_failure" if isinstance(error, ControlFailureEvidence)
            else "incomplete"
        )
        detail = str(error)
        for prefix in (
            "SPEC_MISMATCH: ", "BLOCKED_INFRASTRUCTURE: ",
            "INCOMPLETE: ", "CONTROL_FAILURE: ",
        ):
            detail = detail.removeprefix(prefix)
        findings[condition].append({
            "stage": "control_construction",
            "unit_id": getattr(error, "unit_id", None),
            "kind_cell_id": getattr(error, "kind_cell_id", None),
            "invariant": type(error).__name__,
            "detail": detail,
        })
        _raise_if_preempted(spec, findings)
        raise AssertionError("unreachable")
    if not controls.complete:
        for witness in controls.failures:
            if type(witness) is not dict or witness.get("condition") not in {
                "incomplete", "control_failure",
            }:
                raise IncompleteCampaign("G2c control finding shape disagrees")
            condition = witness["condition"]
            findings[condition].append({
                key: copy.deepcopy(value)
                for key, value in witness.items()
                if key != "condition"
            })
    _raise_if_preempted(spec, findings)
    built = finalize_g2c_artifacts(
        spec,
        drafts,
        control_rows=controls.records,
        rotation_evidence=controls.rotation_evidence,
    )
    validate_g2c_artifacts(built)
    return G2CPreparedArtifacts(built, controls.rotation_evidence)


def _prepare_and_evaluate_g2c_science(
    spec: FrozenSpec, *, report: Any, registry: AttemptRegistry, gate: Any,
) -> tuple[G2CPreparedArtifacts, dict[str, Any]]:
    """Production preemption boundary whose success proceeds directly to statistics."""
    drafts, findings = _derive_g2c_drafts_with_findings(
        spec, report=report, registry=registry, gate=gate,
    )
    return _prepare_and_evaluate_g2c_drafts(
        spec, drafts=drafts, findings=findings,
    )


def _prepare_and_evaluate_g2c_drafts(
    spec: FrozenSpec, *, drafts: Any,
    findings: dict[str, list[dict[str, Any]]],
) -> tuple[G2CPreparedArtifacts, dict[str, Any]]:
    """Actual production control boundary; success calls scientific statistics."""
    prepared = _prepare_g2c_drafts_with_findings(
        spec, drafts=drafts, findings=findings,
    )
    evaluation = evaluate_g2c_records(
        spec,
        prepared.built.records,
        prepared.built.controls_records,
        rotation_evidence=prepared.rotation_evidence,
        control_sources=prepared.built.control_sources,
        control_input_projections=prepared.built.control_input_projections,
    )
    return prepared, evaluation
