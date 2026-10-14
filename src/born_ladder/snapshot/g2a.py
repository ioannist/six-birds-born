"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import math
import operator
import statistics
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
import numpy as np
from born_ladder.snapshot.completeness import AttemptRegistry, StructuralGate, assess_completeness
from born_ladder.snapshot.collector_structural import strict_raw_json_loads
from born_ladder.snapshot.errors import ControlFailureEvidence, IncompleteCampaign, SpecMismatch
from born_ladder.snapshot.frozen_spec import FrozenSpec, canonical_json_bytes, sha256_bytes
from born_ladder.snapshot.inventory import InventoryAuthorization
from born_ladder.snapshot.identities import kind_cell_id, stable_unit_id
from born_ladder.snapshot.provenance import file_sha256, validate_provenance
from born_ladder.snapshot.rng import RNGStream, key_deriver, typed_frame
from born_ladder.snapshot.status import preemptive_status, require_recognized_status
from born_ladder.snapshot.universal_shapes import _formula_contract, _numeric_leaf_count, _recomputed_laws, _residual_contract, canonical_jsonl_bytes, load_canonical_record_artifact, validate_stage_records

_IMPLEMENTATION_POINTERS = {
    "g2a_artifact_identities": "/artifact_paths/artifacts/g2a",
    "g2a_branch_table": "/branch_truth_tables/tables/7",
    "g2a_campaign": "/confirmation_data/campaigns/0",
    "g2a_claim_mapping": "/claim_mapping/rows",
    "g2a_expected_matrix": "/completeness/expected_matrices/0",
    "g2a_grid": "/grid",
    "g2a_inference": "/inference",
    "g2a_loss_formula": "/observation_maps/formulas/loss_k",
    "g2a_observation_maps": "/observation_maps",
    "g2a_planned_exclusions": "/completeness/planned_exclusions",
    "g2a_provenance": "/provenance",
    "g2a_raw_stdout_derivation": "/completeness/g2a_raw_stdout_derivation",
    "g2a_rng_contract": "/rng",
    "g2a_scoring_factor2_formula": "/identity/normative_expression_registry/s_2_k",
    "g2a_synthetic_prefix": "/confirmation_data/exploratory/post_freeze_debug_prefix",
    "g2a_statuses": "/status_sets/recognized/g2a",
    "g2a_dtv_tie_tolerance": "/thresholds/items/5/value",
    "g2a_universal_shapes": "/completeness/universal_evidence_shapes",
}


import json
from born_ladder.snapshot.completeness import CompletenessReport

@dataclass(frozen=True)
class G2aDecisionInputs:
    """Only the frozen G2a table's unrounded branch-driving atoms."""

    sensitivity_reversal: bool

    lower: Mapping[str, Mapping[str, float | None]]

    upper: Mapping[str, Mapping[str, float | None]]

    holm_adjusted_p: Mapping[str, Mapping[str, float]]

    serviceability_lower: Mapping[str, float | None]

    serviceability_upper: Mapping[str, float | None]



@dataclass(frozen=True)
class G2aStatistic:
    statistic_id: str

    kind: str

    competitor_or_null: str | None

    orientation: str

    seed_block_estimates: tuple[float, ...]

    point_estimate: float

    standard_error: float

    conditional_two_sided_p: float

    conditional_one_sided_p: float

    holm_adjusted_p: float

    percentile_interval: tuple[float, float]

    bca_equal_tail_interval: tuple[float | None, float | None]

    bca_simultaneous_lower: float | None

    bca_simultaneous_upper: float | None

    z0: float | None

    acceleration: float

    adjusted_probabilities: Mapping[str, float | None]

    jackknife_values: tuple[float, ...]

    replicate_estimates: tuple[float, ...]

    hierarchy_counts: Mapping[str, int]

    raw_pkg_view_counts: Mapping[str, int]

    sensitivity_atoms: Mapping[str, tuple[float, ...]]

    sensitivity_results: Mapping[str, Mapping[str, Any]]

    rng_audit: tuple[Mapping[str, Any], ...]



@dataclass(frozen=True)
class SealedG2aUnitArtifact:
    """Canonical unit evidence rebuilt only from sealed successful captures."""

    records: tuple[dict[str, Any], ...]

    sha256: str

    attempt_bindings: Mapping[str, str]

    structural_bindings: Mapping[str, str]



class SealedG2aFiniteFailure(ControlFailureEvidence):
    """Finite-number control failure retaining its sealed artifact binding."""

    def __init__(
        self, message: str, *, artifact_bytes: bytes,
        attempt_bindings: Mapping[str, str],
    ) -> None:
        super().__init__(message)
        self.artifact_bytes = artifact_bytes
        self.artifact_sha256 = sha256_bytes(artifact_bytes)
        self.attempt_bindings = dict(attempt_bindings)



def _raw_marker_contract(spec: FrozenSpec) -> dict[bytes, str]:
    markers = spec.get(
        "/completeness/g2a_raw_stdout_derivation/raw_marker_order",
        expected_type=list,
    )
    roles = ("born", "discovery", "audit")
    if len(markers) != len(roles) or not all(
        isinstance(marker, str)
        and marker.endswith(" ")
        and marker[:-1]
        and not marker[:-1].endswith(" ")
        for marker in markers
    ):
        raise SpecMismatch("frozen G2a raw marker order is malformed")
    encoded = [marker.encode("utf-8") for marker in markers]
    if len(encoded) != len(set(encoded)):
        raise SpecMismatch("frozen G2a raw marker order repeats")
    return dict(zip(encoded, roles, strict=True))


def _raw_segments(
    spec: FrozenSpec, stdout: bytes,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    marker_contract = _raw_marker_contract(spec)
    values: dict[str, list[dict[str, Any]]] = {
        name: [] for name in marker_contract.values()
    }
    for line in stdout.splitlines():
        for marker, name in marker_contract.items():
            if line.startswith(marker):
                decoded = strict_raw_json_loads(line[len(marker):])
                if not isinstance(decoded, dict):
                    raise IncompleteCampaign(f"sealed G2a {name} marker is not an object")
                values[name].append(decoded)
                break
    if not values["born"] or len(values["discovery"]) != 1 or len(values["audit"]) != 1:
        raise IncompleteCampaign("sealed G2a stdout does not contain one closed raw segment")
    return values["born"], values["discovery"][0], values["audit"][0]


def _oriented_basis(born: Mapping[str, Any]) -> dict[str, Any]:
    p = np.asarray(born["p_theory"], dtype=np.float64)
    m = int(p.size)
    emitted = np.asarray(born["sym_eigvec_basis"], dtype=np.float64)
    if emitted.ndim != 2 or emitted.shape[1] != m:
        raise ControlFailureEvidence("sealed G2a emitted span dimensions disagree")
    matrix = np.column_stack((np.full(m, 1.0 / math.sqrt(m)), emitted.T))
    u, singular, _ = np.linalg.svd(matrix, full_matrices=False)
    cutoff = max(m, matrix.shape[1]) * np.finfo(np.float64).eps * singular[0]
    rank = int(np.count_nonzero(singular > cutoff))
    u = u[:, :rank]
    for column in range(rank):
        pivot = int(np.flatnonzero(np.abs(u[:, column]) == np.max(np.abs(u[:, column])))[0])
        if u[pivot, column] < 0:
            u[:, column] *= -1.0
    projector = u @ u.T
    constant = np.full(m, 1.0 / math.sqrt(m))
    pivots = [int(np.flatnonzero(np.abs(u[:, c]) == np.max(np.abs(u[:, c])))[0]) for c in range(rank)]
    return {
        "emitted_basis": u.tolist(),
        "projector": projector.tolist(),
        "effective_rank": rank,
        "n_cols_original": int(matrix.shape[1]),
        "singular_values_all": singular.tolist(),
        "singular_values": singular[:rank].tolist(),
        "svd_cutoff": float(cutoff),
        "orientation_pivot_indices": pivots,
        "constant_span_residual": float(np.max(np.abs(projector @ constant - constant))),
    }


def _derive_unit_pair(
    spec: FrozenSpec, *, born: Mapping[str, Any], discovery: Mapping[str, Any],
    audit: Mapping[str, Any], invocation: Mapping[str, Any],
    structural_unit: Mapping[str, Any], structural_manifest_sha256: str,
    attempt_record_sha256: str,
) -> list[dict[str, Any]]:
    shapes = spec.get("/completeness/universal_evidence_shapes", expected_type=dict)
    formulas = _formula_contract(spec)
    state_labels = list(structural_unit["ordered_state_labels"])
    raw_labels = list(structural_unit["ordered_outcome_labels_by_kind"]["raw"])
    pkg_labels = list(structural_unit["ordered_outcome_labels_by_kind"]["pkg"])
    outcome_labels = sorted(set(raw_labels + pkg_labels), key=lambda item: item.encode("utf-8"))
    index = {label: position for position, label in enumerate(outcome_labels)}
    mappings: dict[str, list[list[float]]] = {}
    for kind, source, labels in (
        ("raw", born["partition"], raw_labels),
        ("pkg", born["packaging"], pkg_labels),
    ):
        matrix = [[0.0] * len(state_labels) for _ in outcome_labels]
        for state, group in enumerate(source):
            matrix[index[labels[group]]][state] = 1.0
        mappings[kind] = matrix
    rows = [
        row for row in discovery["rows"]
        if row["step_index"] == born["step_index"]
        and row["observation_payload"]["context_k"] == born["k"]
    ]
    counts: dict[str, list[int]] = {}
    for kind in ("raw", "pkg"):
        selected = [
            row for row in rows
            if ("packaging_source" in row["observation_payload"]) == (kind == "pkg")
        ]
        vector = [0] * len(outcome_labels)
        for row in selected:
            vector[index[row["observation_label"]]] += 1
        if sum(vector) != discovery["trajectory_count"]:
            raise IncompleteCampaign("sealed G2a discovery count census disagrees")
        counts[kind] = vector
    empirical = {
        kind: [value / discovery["trajectory_count"] for value in vector]
        for kind, vector in counts.items()
    }
    basis = _oriented_basis(born)
    root_p = np.sqrt(np.maximum(np.asarray(born["p_theory"], dtype=np.float64), 0.0))
    coefficients = (np.asarray(basis["emitted_basis"]).T @ root_p).tolist()
    common: dict[str, Any] = {
        "unrounded_p_full": list(born["p_theory"]),
        "basis_and_projector_inputs": basis,
        "spectral_coefficients": {
            "mode_ids": [f"M{index}" for index in range(len(coefficients))],
            "values": coefficients,
        },
    }
    predictions, masses, diagnostics = _recomputed_laws(common, formulas)
    numerators = {
        law: [value * masses[law] for value in predictions[law]]
        for law in shapes["all_law_labels"]
    }
    common.update({
        "law_numerators": numerators,
        "normalization_mass": masses,
        "state_space_prediction": predictions,
    })
    source = audit["exp_id"]
    step = born["step_index"]
    unit_id = stable_unit_id(
        spec, source=source, experiment_id=source,
        config_id_or_null=born["cell"], seed=born["seed"], scale=born["scale"],
        runner_context_id=structural_unit["runner_context_id"], resolution=born["k"],
        step_id=str(step), partition_id=structural_unit["partition_id"],
        expected_state_labels=state_labels,
    )
    residual_tolerances = _residual_contract(spec)
    records: list[dict[str, Any]] = []
    for kind in ("raw", "pkg"):
        mapped = {
            law: (np.asarray(mappings[kind]) @ np.asarray(predictions[law])).tolist()
            for law in shapes["all_law_labels"]
        }
        losses = {
            law: formulas["loss_half"] * math.fsum(
                abs(left - right) for left, right in zip(empirical[kind], mapped[law])
            ) for law in shapes["all_law_labels"]
        }
        brier = {
            law: math.fsum(
                (left - right) ** formulas["brier_power"]
                for left, right in zip(empirical[kind], mapped[law])
            ) for law in shapes["all_law_labels"]
        }
        contrasts = {}
        for name in shapes["contrast_identifiers"]["tie_flags"]:
            left, right = name.removeprefix("D__").split("_minus_", 1)
            contrasts[name] = losses[left] - losses[right]
        factor_name = shapes["contrast_identifiers"]["factor2"]
        contrasts[factor_name] = losses["q_full"] - formulas["factor"] * losses["L_full"]
        descriptive_delta = next(
            name for name in shapes["contrast_identifiers"]["descriptive"]
            if name.startswith("DELTA1__")
        )
        contrasts[descriptive_delta] = (
            losses["q_full"] - losses["L_full"]
        )
        mass_residuals = {
            "empirical_raw": math.fsum(empirical["raw"]) - 1.0,
            "empirical_pkg": math.fsum(empirical["pkg"]) - 1.0,
            **{law: math.fsum(predictions[law]) - 1.0 for law in shapes["all_law_labels"]},
        }
        record = {
            "unit_id": unit_id,
            "kind_cell_id": kind_cell_id(unit_id, kind),
            "invocation_id": invocation["invocation_id"],
            "source": source, "experiment": source,
            "config_or_null": born["cell"], "seed": born["seed"], "scale": born["scale"],
            "resolution": born["k"], "context": structural_unit["runner_context_id"],
            "partition": structural_unit["partition_id"], "step": step,
            "trajectory": None, "eligibility": born["cell"] != "empty",
            "frozen_inclusion_population": "EXP-112_FROZEN_69_WITH_68_PRIMARY_ELIGIBLE",
            "exclusion_reason_code": None if born["cell"] != "empty" else "EMPTY_CONFIG_STRUCTURAL_EXCLUSION",
            "structural_manifest_sha256": structural_manifest_sha256,
            "attempt_record_sha256": attempt_record_sha256,
            "applicable_control_record_links": [],
            "integer_counts": counts[kind], "total_count": discovery["trajectory_count"],
            "ordered_state_labels": state_labels,
            "ordered_union_outcome_labels": outcome_labels,
            "M_raw_or_content_hash": mappings["raw"],
            "M_pkg_or_content_hash": mappings["pkg"],
            "unrounded_y_raw": empirical["raw"], "unrounded_y_pkg": empirical["pkg"],
            **common,
            "mapped_outcome_prediction": mapped, "dtv_loss": losses,
            "brier_score": brier, "pairwise_contrast": contrasts,
            "tie_flag": {
                name: abs(contrasts[name]) <= spec.get("/thresholds/items/5/value")
                for name in shapes["contrast_identifiers"]["tie_flags"]
            },
            "seed_block_key": str(born["seed"]),
            "fixed_census_config_or_experiment_key": born["cell"],
            "source_key": source,
            "bootstrap_hierarchy_keys": [str(born["seed"]), born["cell"], source],
            "raw_pkg_pairing_key": unit_id,
            "finite_residuals": {"checked_value_count": 0, "nonfinite_value_count": 0},
            "mass_residuals": mass_residuals,
            "parseval_residuals": {
                "p_full_norm_minus_one": diagnostics["p_mass"],
                "spectral_energy_minus_p_full_energy": diagnostics["spectral_energy"],
            },
            "rotation_residuals": {
                "q_full_max_component": diagnostics["q_full_component"],
                "q_full_dtv": diagnostics["q_full_dtv"],
                "q_diag_max_component_diagnostic": 0.0,
            },
            "identity_residuals": None, "sequential_residuals": None,
            "tolerance_for_each_residual": residual_tolerances,
            "pass_boolean_for_each_residual": {
                "finite_residuals": True, "mass_residuals": True,
                "parseval_residuals": True, "rotation_residuals": True,
                "identity_residuals": False, "sequential_residuals": False,
            },
        }
        profile = shapes["stage_profiles"]["g2a"]
        record["finite_residuals"]["checked_value_count"] = sum(
            _numeric_leaf_count(record[field])
            for group in ("empirical", "law_evidence")
            for field in profile["group_field_order"][group]
        )
        if not record["eligibility"]:
            for group in ("empirical", "law_evidence"):
                for field in profile["group_field_order"][group]:
                    record[field] = None
        records.append(record)
    return records


def _sealed_g2a_unit_artifact(
    spec: FrozenSpec, attempt_registry: AttemptRegistry,
    structural_gate: StructuralGate,
) -> SealedG2aUnitArtifact:
    """Derive canonical unit evidence solely from sealed v8 raw stdout."""
    if type(attempt_registry) is not AttemptRegistry or type(structural_gate) is not StructuralGate:
        raise IncompleteCampaign("G2a evidence requires production-sealed registries")
    structural = {
        record["invocation_id"]: record
        for record in structural_gate.records_for(
            spec, "g2a_v2", attempt_registry.census_sha256
        )
    }
    invocation_ids = sorted(attempt_registry.invocation_ids())
    attempt_bindings = {
        identity: attempt_registry.successful_attempt_record_sha256(identity)
        for identity in invocation_ids
    }
    structural_bindings = {
        identity: sha256_bytes(canonical_json_bytes(record)[:-1])
        for identity, record in structural.items()
    }
    records: list[dict[str, Any]] = []
    for invocation_id in invocation_ids:
        invocation = attempt_registry.invocation_record(invocation_id)
        born, discovery, audit = _raw_segments(
            spec, attempt_registry.successful_stdout(invocation_id)
        )
        structural_record = structural.get(invocation_id)
        if structural_record is None:
            raise IncompleteCampaign("sealed G2a invocation lacks structural evidence")
        units = {(item["step_id"], item["resolution"]): item for item in structural_record["units"]}
        if len(units) != len(structural_record["units"]):
            raise IncompleteCampaign("sealed G2a structural unit identity repeats")
        for item in born:
            unit = units.get((str(item["step_index"]), item["k"]))
            if unit is None:
                raise IncompleteCampaign("sealed G2a Born record lacks structural unit")
            records.extend(_derive_unit_pair(
                spec, born=item, discovery=discovery, audit=audit,
                invocation=invocation, structural_unit=unit,
                structural_manifest_sha256=structural_bindings[invocation_id],
                attempt_record_sha256=attempt_bindings[invocation_id],
            ))
    raw = canonical_jsonl_bytes(records)
    return SealedG2aUnitArtifact(
        records=tuple(records), sha256=sha256_bytes(raw),
        attempt_bindings=attempt_bindings,
        structural_bindings=structural_bindings,
    )


def _contract(
    spec: FrozenSpec, implementation_manifest_path: Path | None = None
) -> dict[str, Any]:
    spec.audit_implementation_manifest(
        "g2a", manifest_path=implementation_manifest_path,
        declared_pointers=_IMPLEMENTATION_POINTERS,
    )
    table = spec.get("/branch_truth_tables/tables/7", expected_type=dict)
    if table.get("id") != "g2a" or not table.get("ordered") or not table.get("exhaustive"):
        raise SpecMismatch("frozen G2a truth table identity or closure disagrees")
    campaign = spec.get("/confirmation_data/campaigns/0", expected_type=dict)
    matrix = spec.get("/completeness/expected_matrices/0", expected_type=dict)
    stage_profile = matrix.get("campaign")
    if (
        not isinstance(stage_profile, str)
        or campaign.get("name") != f"{stage_profile}_v2"
        or not isinstance(campaign.get("experiments"), list)
        or len(campaign["experiments"]) != 1
    ):
        raise SpecMismatch("frozen G2a campaign pointers disagree")
    expected_invocations = (
        len(spec.get("/grid/labels", expected_type=list))
        * len(campaign.get("seeds", []))
        * len(campaign.get("scales", []))
    )
    if matrix.get("expected_invocations") != expected_invocations:
        raise SpecMismatch("frozen G2a campaign matrix is not closed")
    statuses = spec.get("/status_sets/recognized/g2a", expected_type=list)
    if [row["status"] for row in table["rows"]] != statuses:
        raise SpecMismatch("frozen G2a truth table and status set disagree")
    s2_formula = spec.get(
        "/identity/normative_expression_registry/s_2_k", expected_type=dict
    )
    loss_formula = spec.get("/observation_maps/formulas/loss_k", expected_type=dict)
    try:
        factor2 = float(s2_formula["arguments"][1]["arguments"][0]["value"])
        loss_half = float(loss_formula["arguments"][0]["value"])
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise SpecMismatch("frozen G2a scoring formula tree is unsupported") from error
    return {
        "artifacts": spec.get("/artifact_paths/artifacts/g2a", expected_type=list),
        "campaign": campaign,
        "claims": spec.get("/claim_mapping/rows", expected_type=list),
        "grid": spec.get("/grid", expected_type=dict),
        "inference": spec.get("/inference", expected_type=dict),
        "loss_formula": loss_formula,
        "matrix": matrix,
        "observation_maps": spec.get("/observation_maps", expected_type=dict),
        "planned_exclusions": spec.get(
            "/completeness/planned_exclusions", expected_type=list
        ),
        "provenance": spec.get("/provenance", expected_type=dict),
        "raw_derivation": spec.get(
            "/completeness/g2a_raw_stdout_derivation", expected_type=dict
        ),
        "rng": spec.get("/rng", expected_type=dict),
        "s2_formula": s2_formula,
        "factor2": factor2,
        "loss_half": loss_half,
        "shapes": spec.get("/completeness/universal_evidence_shapes", expected_type=dict),
        "statuses": statuses,
        "stage": stage_profile.upper(),
        "stage_profile": stage_profile,
        "table": table,
        "dtv_tie_tolerance": spec.get("/thresholds/items/5/value"),
        "synthetic_prefix": spec.get(
            "/confirmation_data/exploratory/post_freeze_debug_prefix", expected_type=str
        ),
    }


def _finite_number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def _validate_decision_inputs(
    decision: G2aDecisionInputs,
    *,
    kinds: Sequence[str],
    competitors: Sequence[str],
) -> None:
    if type(decision.sensitivity_reversal) is not bool:
        raise IncompleteCampaign("G2a sensitivity-reversal atom must be Boolean")
    expected_kinds = set(kinds)
    expected_competitors = set(competitors)
    for name, values in (
        ("lower", decision.lower),
        ("upper", decision.upper),
        ("holm_adjusted_p", decision.holm_adjusted_p),
    ):
        if set(values) != expected_kinds:
            raise IncompleteCampaign(f"G2a {name} kind keys disagree with the frozen set")
        for kind in kinds:
            if set(values[kind]) != expected_competitors:
                raise IncompleteCampaign(
                    f"G2a {name}.{kind} competitor keys disagree with the frozen set"
                )
            for value in values[kind].values():
                if name == "holm_adjusted_p":
                    if not _finite_number(value) or not 0.0 <= float(value) <= 1.0:
                        raise IncompleteCampaign("G2a adjusted p-value is outside [0,1]")
                elif value is not None and not _finite_number(value):
                    raise IncompleteCampaign("G2a interval endpoint is not finite or null")
    for name, values in (
        ("serviceability_lower", decision.serviceability_lower),
        ("serviceability_upper", decision.serviceability_upper),
    ):
        if set(values) != expected_kinds:
            raise IncompleteCampaign(f"G2a {name} kind keys disagree with the frozen set")
        if any(value is not None and not _finite_number(value) for value in values.values()):
            raise IncompleteCampaign("G2a serviceability endpoint is not finite or null")


def _lookup_variable(name: str, env: Mapping[str, Any], bound: Mapping[str, str]) -> Any:
    if "[" not in name:
        if name in bound:
            return bound[name]
        if name not in env:
            raise SpecMismatch(f"G2a truth-table variable {name!r} is unsupported")
        return env[name]
    base, indices = name[:-1].split("[", 1)
    if base not in env:
        raise SpecMismatch(f"G2a truth-table variable {base!r} is unsupported")
    value = env[base]
    for token in indices.split(","):
        key = bound.get(token, token)
        value = value[key]
    if value is None:
        return math.nan
    return value


def _eval_predicate(node: Mapping[str, Any], env: Mapping[str, Any], bound: dict[str, str]) -> Any:
    kind = node["kind"]
    if kind == "literal":
        return node["value"]
    if kind == "variable":
        return _lookup_variable(node["name"], env, bound)
    if kind == "comparison":
        operations: dict[str, Callable[[Any, Any], bool]] = {
            "<": operator.lt, "<=": operator.le, ">": operator.gt,
            ">=": operator.ge, "==": operator.eq,
        }
        operation = node["operator"]
        if operation not in operations:
            raise SpecMismatch(f"unsupported G2a comparison operator {operation!r}")
        return operations[operation](
            _eval_predicate(node["left"], env, bound),
            _eval_predicate(node["right"], env, bound),
        )
    if kind == "boolean_operator":
        arguments = [_eval_predicate(item, env, bound) for item in node["arguments"]]
        if node["operator"] == "not" and len(arguments) == 1:
            return not arguments[0]
        if node["operator"] == "and":
            return all(arguments)
        if node["operator"] == "or":
            return any(arguments)
        raise SpecMismatch(f"unsupported G2a Boolean operator {node['operator']!r}")
    if kind == "quantifier":
        results: list[bool] = []
        for value in node["domain"]:
            nested = dict(bound)
            nested[node["variable"]] = value
            results.append(bool(_eval_predicate(node["expression"], env, nested)))
        if node["quantifier"] == "all":
            return all(results)
        if node["quantifier"] == "exists":
            return any(results)
        raise SpecMismatch(f"unsupported G2a quantifier {node['quantifier']!r}")
    if kind == "predicate":
        arguments = [_eval_predicate(item, env, bound) for item in node["arguments"]]
        if node["name"] == "exists_named_sensitivity_sign_reversal" and not arguments:
            return env["exists_named_sensitivity_sign_reversal"]
        if node["name"] == "comparison_unresolved" and len(arguments) == 1:
            competitor = arguments[0]
            return any(
                not (
                    env["D_lower"][kind_name][competitor] is not None
                    and env["D_lower"][kind_name][competitor] > 0
                    and env["holm_adjusted_p"][kind_name][competitor] <= env["alpha"]
                )
                and not (
                    env["D_upper"][kind_name][competitor] is not None
                    and env["D_upper"][kind_name][competitor] < 0
                )
                for kind_name in env["kinds"]
            )
        raise SpecMismatch(f"unsupported G2a named predicate {node['name']!r}")
    raise SpecMismatch(f"unsupported G2a predicate node {kind!r}")


def select_g2a_branch(
    spec: FrozenSpec,
    decision: G2aDecisionInputs,
    *,
    implementation_manifest_path: Path | None = None,
) -> str:
    """Evaluate the frozen typed table in priority order with no default status."""
    contract = _contract(spec, implementation_manifest_path)
    inference = contract["inference"]
    competitors = contract["shapes"]["competitor_labels"]
    kinds = contract["observation_maps"]["kind_set"]
    _validate_decision_inputs(decision, kinds=kinds, competitors=competitors)
    clipped = competitors[0]
    env = {
        "D_clipped_linear_upper": {
            kind: decision.upper[kind][clipped] for kind in kinds
        },
        "D_lower": decision.lower,
        "D_upper": decision.upper,
        "S_2_lower": decision.serviceability_lower,
        "S_2_upper": decision.serviceability_upper,
        "alpha": inference["multiplicity"]["alpha"],
        "exists_named_sensitivity_sign_reversal": decision.sensitivity_reversal,
        "holm_adjusted_p": decision.holm_adjusted_p,
        "kinds": kinds,
    }
    matched: list[str] = []
    fallback_rows = [row for row in contract["table"]["rows"] if row["ordered_fallback"]]
    if len(fallback_rows) != 1 or fallback_rows[0] is not contract["table"]["rows"][-1]:
        raise SpecMismatch("G2a truth table lacks one final ordered fallback")
    for expected_priority, row in enumerate(contract["table"]["rows"], start=1):
        if row["priority"] != expected_priority or row["ordered_fallback"] != (expected_priority == len(contract["table"]["rows"])):
            raise SpecMismatch("G2a truth table priority or fallback marker disagrees")
        if _eval_predicate(row["predicate"], env, {}):
            matched.append(row["status"])
            break
    if len(matched) != 1:
        raise SpecMismatch("G2a truth table did not select exactly one branch")
    return require_recognized_status(
        spec, "g2a", matched[0], implementation_manifest_path=implementation_manifest_path
    )


def _mean(values: Sequence[float]) -> float:
    if not values or not all(math.isfinite(value) for value in values):
        raise IncompleteCampaign("G2a inference received empty or nonfinite values")
    return math.fsum(values) / len(values)


def _type7(values: Sequence[float], probability: float) -> float:
    if not 0 <= probability <= 1 or not values:
        raise IncompleteCampaign("G2a quantile input is invalid")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    location = (len(ordered) - 1) * probability
    lower = math.floor(location)
    fraction = location - lower
    if lower == len(ordered) - 1:
        return ordered[-1]
    return ordered[lower] + fraction * (ordered[lower + 1] - ordered[lower])


def _conditional_sign_p(values: Sequence[float]) -> tuple[float, float]:
    observed_sum = math.fsum(values)
    sums = [0.0]
    for value in values:
        sums = [current + value for current in sums] + [current - value for current in sums]
    denominator = len(sums)
    two_sided = sum(abs(value) >= abs(observed_sum) for value in sums) / denominator
    one_sided = sum(value >= observed_sum for value in sums) / denominator
    return two_sided, one_sided


def _holm(p_values: Mapping[str, float]) -> dict[str, float]:
    ordered = sorted(p_values, key=lambda key: (p_values[key], key))
    adjusted: dict[str, float] = {}
    running = 0.0
    size = len(ordered)
    for rank, key in enumerate(ordered):
        running = max(running, min(1.0, (size - rank) * p_values[key]))
        adjusted[key] = running
    return adjusted


def _bca_probability(z0: float, acceleration: float, probability: float) -> float | None:
    normal = statistics.NormalDist()
    z_alpha = normal.inv_cdf(probability)
    denominator = 1.0 - acceleration * (z0 + z_alpha)
    if denominator == 0:
        return None
    transformed = normal.cdf(z0 + (z0 + z_alpha) / denominator)
    if math.isnan(transformed):
        return None
    return min(1.0, max(0.0, transformed))


def _bootstrap_rng_audit(
    *, stage_id: str, statistic_id: str, replicate_index: int,
    key: bytes, stream: RNGStream, rng_contract: Mapping[str, Any],
    attested_json_sha256: str,
) -> dict[str, Any]:
    descriptors = rng_contract["algorithms"]["bootstrap"]["key_fields"]
    expected = [
        ("str", "bootstrap-v2", "bootstrap-v2"),
        ("bytes", "attested JSON SHA-256", bytes.fromhex(attested_json_sha256)),
        ("str", "stage_id", stage_id),
        ("str", "statistic_id", statistic_id),
        ("u64", "replicate_index", replicate_index),
    ]
    if descriptors != [f"{kind}:{name}" for kind, name, _ in expected]:
        raise SpecMismatch("frozen bootstrap RNG fields disagree")
    prefix = rng_contract["framing"]["master_prefix"]
    prefix_frame = typed_frame("str", prefix)
    framed = [
        {"kind": kind, "name": name, "framed_hex": typed_frame(kind, value).hex()}
        for kind, name, value in expected
    ]
    derived = hashlib.sha256(
        prefix_frame + b"".join(bytes.fromhex(item["framed_hex"]) for item in framed)
    ).digest()
    if derived != key:
        raise SpecMismatch("bootstrap RNG audit master key disagrees")
    if stream.counter < 1:
        raise SpecMismatch("bootstrap RNG audit consumed no counter")
    return {
        "framed_fields": framed,
        "highest_counter": stream.counter - 1,
        "implementation_version": prefix,
        "master_key": key.hex(),
        "prefix_frame_hex": prefix_frame.hex(),
        "replicate_index": replicate_index,
    }


def _bootstrap_result(
    seed_values: Sequence[float],
    *,
    stage_id: str,
    statistic_id: str,
    inference: Mapping[str, Any],
    derive_key: Callable[[str, Mapping[str, str | int]], bytes],
    rng_contract: Mapping[str, Any],
    attested_json_sha256: str,
) -> dict[str, Any]:
    replicates = inference["bootstrap"]["replicates"]
    if len(seed_values) != inference["conditional_sign_randomization"]["seed_blocks"]:
        raise IncompleteCampaign("G2a seed-block count disagrees with frozen inference")
    estimates: list[float] = []
    rng_audit: list[dict[str, Any]] = []
    for replicate in range(replicates):
        key = derive_key(
            "bootstrap",
            {"stage_id": stage_id, "statistic_id": statistic_id, "replicate_index": replicate},
        )
        stream = RNGStream(key)
        estimates.append(_mean([seed_values[stream.unbiased_index(len(seed_values))] for _ in seed_values]))
        rng_audit.append(_bootstrap_rng_audit(
            stage_id=stage_id, statistic_id=statistic_id,
            replicate_index=replicate, key=key, stream=stream,
            rng_contract=rng_contract, attested_json_sha256=attested_json_sha256,
        ))
    summary = _bca_summary(seed_values, estimates, inference)
    return {
        **summary,
        "replicate_estimates": tuple(estimates),
        "rng_audit": tuple(rng_audit),
    }


def _bca_summary(
    seed_values: Sequence[float], estimates: Sequence[float],
    inference: Mapping[str, Any],
) -> dict[str, Any]:
    """Compute the frozen no-fallback BCa endpoints from complete finite vectors."""
    theta = _mean(seed_values)
    jackknife = [_mean([value for index, value in enumerate(seed_values) if index != omitted]) for omitted in range(len(seed_values))]
    jackknife_mean = _mean(jackknife)
    deviations = [jackknife_mean - value for value in jackknife]
    quadratic = math.fsum(value * value for value in deviations)
    acceleration = 0.0 if quadratic == 0 else math.fsum(value**3 for value in deviations) / (6.0 * quadratic**1.5)
    less = sum(value < theta for value in estimates)
    ties = sum(value == theta for value in estimates)
    if not estimates:
        raise IncompleteCampaign("G2a BCa replicate vector is empty")
    proportion = (
        less + inference["bca"]["bootstrap_tie_weight"] * ties
    ) / len(estimates)
    z0 = None if proportion in {0.0, 1.0} else statistics.NormalDist().inv_cdf(proportion)
    alpha = inference["multiplicity"]["alpha"]
    ledger = inference["multiplicity"]["endpoint_ledgers"]["g2a"]
    probabilities = {
        "equal_tail_lower": alpha / 2.0,
        "equal_tail_upper": 1.0 - alpha / 2.0,
        "simultaneous_lower": alpha / ledger,
        "simultaneous_upper": 1.0 - alpha / ledger,
    }
    adjusted = {
        name: None if z0 is None else _bca_probability(z0, acceleration, probability)
        for name, probability in probabilities.items()
    }
    quantiles = {
        name: None if probability is None else _type7(estimates, probability)
        for name, probability in adjusted.items()
    }
    return {
        "acceleration": acceleration,
        "adjusted_probabilities": adjusted,
        "bca_equal_tail_interval": (quantiles["equal_tail_lower"], quantiles["equal_tail_upper"]),
        "bca_simultaneous_lower": quantiles["simultaneous_lower"],
        "bca_simultaneous_upper": quantiles["simultaneous_upper"],
        "jackknife_values": tuple(jackknife),
        "percentile_interval": (_type7(estimates, alpha / 2.0), _type7(estimates, 1.0 - alpha / 2.0)),
        "z0": z0,
    }


def _hierarchical_values(
    records: Sequence[Mapping[str, Any]], field: str, *, factor2: float
) -> tuple[dict[int, dict[str, float]], dict[int, dict[str, float]], dict[str, int]]:
    dtv: dict[int, dict[str, dict[str, dict[tuple[str, str, int], dict[int, float]]]]] = {}
    brier: dict[int, dict[str, dict[str, dict[tuple[str, str, int], dict[int, float]]]]] = {}
    for record in records:
        seed = record["seed"]
        config = record["config_or_null"]
        if not isinstance(config, str):
            raise IncompleteCampaign("G2a eligible record lacks its frozen config label")
        invocation = record["invocation_id"]
        context_key = (record["context"], record["partition"], record["resolution"])
        step = record["step"]
        dtv_steps = (
            dtv.setdefault(seed, {}).setdefault(config, {}).setdefault(invocation, {})
            .setdefault(context_key, {})
        )
        brier_steps = (
            brier.setdefault(seed, {}).setdefault(config, {}).setdefault(invocation, {})
            .setdefault(context_key, {})
        )
        if step in dtv_steps or step in brier_steps:
            raise IncompleteCampaign("G2a hierarchy repeats a context/partition/step kind-cell")
        dtv_steps[step] = record["pairwise_contrast"][field]
        if field.startswith("D__"):
            terms = field.removeprefix("D__").split("_minus_", 1)
            if len(terms) != 2:
                raise SpecMismatch(f"malformed G2a competitor contrast {field!r}")
            brier_value = record["brier_score"][terms[0]] - record["brier_score"][terms[1]]
        elif field.startswith("S2__"):
            terms = field.removeprefix("S2__").split("_minus_2x", 1)
            if len(terms) != 2:
                raise SpecMismatch(f"malformed G2a factor-2 contrast {field!r}")
            brier_value = record["brier_score"][terms[0]] - factor2 * record["brier_score"][terms[1]]
        else:
            raise SpecMismatch(f"unsupported G2a inferential contrast {field!r}")
        brier_steps[step] = brier_value

    def collapse(
        values: Mapping[int, Mapping[str, Mapping[str, Mapping[tuple[str, str, int], Mapping[int, float]]]]]
    ) -> dict[int, dict[str, float]]:
        collapsed: dict[int, dict[str, float]] = {}
        for seed, configs in values.items():
            collapsed[seed] = {}
            for config, invocations in configs.items():
                if len(invocations) != 1:
                    raise IncompleteCampaign(
                        "G2a seed/config has other than one runner invocation"
                    )
                context_means = [
                    _mean([steps[step] for step in sorted(steps)])
                    for contexts in invocations.values()
                    for _, steps in sorted(contexts.items())
                ]
                collapsed[seed][config] = _mean(context_means)
        return collapsed

    context_count = sum(
        len(contexts)
        for configs in dtv.values()
        for invocations in configs.values()
        for contexts in invocations.values()
    )
    invocation_count = sum(
        len(invocations) for configs in dtv.values() for invocations in configs.values()
    )
    counts = {
        "seed_blocks": len(dtv),
        "configs": len({config for configs in dtv.values() for config in configs}),
        "runner_invocations": invocation_count,
        "contexts": context_count,
        "steps": len(records),
        "kind_cells": len(records),
    }
    return collapse(dtv), collapse(brier), counts


def _sensitivity_atoms(
    primary: float,
    values: Mapping[int, Mapping[str, float]],
    brier: Mapping[int, Mapping[str, float]],
    *,
    orientation: float,
    seeds: Sequence[int],
    configs: Sequence[str],
) -> dict[str, tuple[float, ...]]:
    if set(values) != set(seeds) or set(brier) != set(seeds):
        raise IncompleteCampaign("G2a sensitivity seed census disagrees")
    if any(set(values[seed]) != set(configs) or set(brier[seed]) != set(configs) for seed in seeds):
        raise IncompleteCampaign("G2a sensitivity config census disagrees")
    seed_means = [_mean([values[seed][config] for config in configs]) * orientation for seed in seeds]
    config_means = [_mean([values[seed][config] for seed in seeds]) * orientation for config in configs]
    brier_seed_means = [_mean([brier[seed][config] for config in configs]) * orientation for seed in seeds]
    return {
        "seed_only_fixed_census": (primary,),
        "config_only_superpopulation": (_mean(config_means),),
        "hierarchical_seed_config_superpopulation": (primary,),
        "leave_one_seed_out": tuple(_mean([value for index, value in enumerate(seed_means) if index != omitted]) for omitted in range(len(seeds))),
        "leave_one_config_out": tuple(_mean([value for index, value in enumerate(config_means) if index != omitted]) for omitted in range(len(configs))),
        "two_way_pigeonhole_seed_by_config": (primary,),
        "brier_complete_ranking": (_mean(brier_seed_means),),
    }


def _percentile_summary(values: Sequence[float], alpha: float) -> dict[str, Any]:
    return {
        "percentile_interval": (
            _type7(values, alpha / 2.0),
            _type7(values, 1.0 - alpha / 2.0),
        ),
        "replicate_estimates": tuple(values),
    }


def _sensitivity_results(
    *,
    stage_id: str,
    statistic_id: str,
    primary_bootstrap: Mapping[str, Any],
    atoms: Mapping[str, tuple[float, ...]],
    values: Mapping[int, Mapping[str, float]],
    brier: Mapping[int, Mapping[str, float]],
    orientation: float,
    seeds: Sequence[int],
    configs: Sequence[str],
    inference: Mapping[str, Any],
    derive_key: Callable[[str, Mapping[str, str | int]], bytes],
    rng_contract: Mapping[str, Any],
    attested_json_sha256: str,
    sign_p=None,
) -> dict[str, Mapping[str, Any]]:
    replicates = inference["bootstrap"]["replicates"]
    alpha = inference["multiplicity"]["alpha"]
    seed_values = [
        _mean([values[seed][config] for config in configs]) * orientation
        for seed in seeds
    ]
    config_values = [
        _mean([values[seed][config] for seed in seeds]) * orientation
        for config in configs
    ]

    def samples(
        name: str, sampler: Callable[[RNGStream], float]
    ) -> tuple[list[float], tuple[Mapping[str, Any], ...]]:
        result: list[float] = []
        audits: list[Mapping[str, Any]] = []
        keyed_statistic = f"{statistic_id}::sensitivity::{name}"
        for replicate in range(replicates):
            key = derive_key(
                "bootstrap",
                {
                    "stage_id": stage_id,
                    "statistic_id": keyed_statistic,
                    "replicate_index": replicate,
                },
            )
            stream = RNGStream(key)
            result.append(sampler(stream))
            audits.append(_bootstrap_rng_audit(
                stage_id=stage_id, statistic_id=keyed_statistic,
                replicate_index=replicate, key=key, stream=stream,
                rng_contract=rng_contract, attested_json_sha256=attested_json_sha256,
            ))
        return result, tuple(audits)

    config_bootstrap, config_audit = samples(
        "config_only_superpopulation",
        lambda stream: _mean([
            config_values[stream.unbiased_index(len(config_values))]
            for _ in configs
        ]),
    )

    def hierarchical(stream: RNGStream) -> float:
        selected_seed_indices = [stream.unbiased_index(len(seeds)) for _ in seeds]
        return _mean([
            _mean([
                values[seeds[seed_index]][configs[stream.unbiased_index(len(configs))]]
                * orientation
                for _ in configs
            ])
            for seed_index in selected_seed_indices
        ])

    hierarchical_bootstrap, hierarchical_audit = samples(
        "hierarchical_seed_config_superpopulation", hierarchical
    )

    def pigeonhole(stream: RNGStream) -> float:
        selected_seeds = [seeds[stream.unbiased_index(len(seeds))] for _ in seeds]
        selected_configs = [configs[stream.unbiased_index(len(configs))] for _ in configs]
        return _mean([
            values[seed][config] * orientation
            for seed in selected_seeds
            for config in selected_configs
        ])

    pigeonhole_bootstrap, pigeonhole_audit = samples(
        "two_way_pigeonhole_seed_by_config", pigeonhole
    )
    brier_seed_values = [
        _mean([brier[seed][config] for config in configs]) * orientation
        for seed in seeds
    ]
    brier_two_sided, brier_one_sided = (_conditional_sign_p if sign_p is None else sign_p)(brier_seed_values)
    brier_bootstrap = _bootstrap_result(
        brier_seed_values,
        stage_id=stage_id,
        statistic_id=f"{statistic_id}::sensitivity::brier_complete_ranking",
        inference=inference,
        derive_key=derive_key,
        rng_contract=rng_contract,
        attested_json_sha256=attested_json_sha256,
    )
    return {
        "seed_only_fixed_census": {
            "point_estimate": atoms["seed_only_fixed_census"][0],
            "replicate_estimates": primary_bootstrap["replicate_estimates"],
            "percentile_interval": primary_bootstrap["percentile_interval"],
            "rng_audit": primary_bootstrap["rng_audit"],
        },
        "config_only_superpopulation": {
            "point_estimate": atoms["config_only_superpopulation"][0],
            **_percentile_summary(config_bootstrap, alpha),
            "rng_audit": config_audit,
        },
        "hierarchical_seed_config_superpopulation": {
            "point_estimate": atoms["hierarchical_seed_config_superpopulation"][0],
            **_percentile_summary(hierarchical_bootstrap, alpha),
            "rng_audit": hierarchical_audit,
        },
        "leave_one_seed_out": {"atomic_estimates": atoms["leave_one_seed_out"]},
        "leave_one_config_out": {"atomic_estimates": atoms["leave_one_config_out"]},
        "two_way_pigeonhole_seed_by_config": {
            "point_estimate": atoms["two_way_pigeonhole_seed_by_config"][0],
            **_percentile_summary(pigeonhole_bootstrap, alpha),
            "rng_audit": pigeonhole_audit,
        },
        "brier_complete_ranking": {
            "point_estimate": atoms["brier_complete_ranking"][0],
            "conditional_two_sided_p": brier_two_sided,
            "conditional_one_sided_p": brier_one_sided,
            **brier_bootstrap,
        },
    }


def _has_reversal(statistics_by_id: Mapping[str, G2aStatistic]) -> bool:
    return any(
        statistic.point_estimate * atom < 0
        for statistic in statistics_by_id.values()
        for atoms in statistic.sensitivity_atoms.values()
        for atom in atoms
    )


def _controls_pass(records: Sequence[Mapping[str, Any]], profile: Mapping[str, Any]) -> bool:
    applicable = {
        name
        for name in profile["group_field_order"]["controls"]
        if name.endswith("_residuals")
        if profile["field_applicability"][name]["disposition"] == "APPLICABLE"
    }
    return all(
        all(
            record["pass_boolean_for_each_residual"][name]
            for name in applicable
        )
        and all(
            record["pass_boolean_for_each_residual"][name] is False
            for name in set(record["pass_boolean_for_each_residual"]) - applicable
        )
        for record in records if record["eligibility"]
    )


def _reject_synthetic_campaign_evidence(
    value: Any, prefix: str, path: str = "campaign"
) -> None:
    if isinstance(value, str) and value.startswith(prefix):
        raise IncompleteCampaign(
            f"production G2a evaluator rejects synthetic fixture value at {path}"
        )
    if isinstance(value, Mapping):
        for key, nested in value.items():
            _reject_synthetic_campaign_evidence(nested, prefix, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested in enumerate(value):
            _reject_synthetic_campaign_evidence(nested, prefix, f"{path}[{index}]")


def _validate_provenance_binding(
    spec: FrozenSpec,
    provenance: Mapping[str, Any],
    contract: Mapping[str, Any],
    unit_artifact_sha256: str,
) -> None:
    validate_provenance(spec, provenance)
    pins = contract["provenance"]["candidate_pins"]
    expected = {
        "Cargo.lock_sha256": pins["Cargo.lock_sha256"],
        "attestation_tag": spec.attestation.tag,
        "attested_json_sha256": spec.attestation.json_sha256,
        "attested_markdown_sha256": spec.attestation.markdown_sha256,
        "build_command": contract["provenance"]["build_command"],
        "cargo_version": pins["cargo"],
        "experiment_definition_hashes": {
            item["experiment"]: item["sha256"]
            for item in contract["grid"]["definition_identities"]
        },
        "freeze_payload_commit": spec.attestation.freeze_commit,
        "host_os_architecture": {
            "architecture": pins["architecture"],
            "os": pins["os"],
        },
        "python_environment_lock_sha256": pins["python_lock_sha256"],
        "python_version": pins["python"],
        "runner_binary_path_sha256": {
            "path": pins["runner_binary"],
            "sha256": pins["runner_binary_sha256"],
        },
        "runner_source_sha256": pins["runner_source_sha256"],
        "rustc_version": pins["rustc"],
        "spec_id": spec.get("/identity/spec_id", expected_type=str),
        "vendored_source_commit": spec.attestation.freeze_commit,
    }
    for name, value in expected.items():
        if provenance[name] != value:
            raise SpecMismatch(f"G2a provenance {name} disagrees with frozen identity")
    builder = provenance["builder_path_sha256"]
    # Verify the original builder identity from explicit archived bytes.
    history = getattr(spec, "history", None)
    if history is not None:
        if builder["path"] != "scripts/rebuild1/g2a.py":
            raise SpecMismatch("G2a provenance builder historical identity differs")
        history.path(builder["path"], expected_sha256=builder["sha256"])
    else:
        # New production binds the public implementation, never a historical
        # execution identity. This branch requires an explicit output root.
        if getattr(spec, "scientific_rng_identity", None) is None or spec.repo_root is None:
            raise IncompleteCampaign("explicit historical_root or public production inputs required")
        builder_path = Path(builder["path"])
        if not builder_path.is_absolute():
            builder_path = spec.repo_root / builder_path
        if builder_path.resolve() != Path(__file__).resolve():
            raise SpecMismatch("G2a provenance builder path is not this evaluator")
        if builder["sha256"] != file_sha256(Path(__file__).resolve()):
            raise SpecMismatch("G2a provenance builder SHA-256 disagrees")
    if provenance["input_sha256s"]["implementation_manifest"] != (
        spec.implementation_manifest_sha256
    ):
        raise SpecMismatch("G2a provenance implementation-manifest binding disagrees")
    if provenance["input_sha256s"].get(contract["artifacts"][1]) != unit_artifact_sha256:
        raise IncompleteCampaign("G2a provenance unit-artifact binding disagrees")


def _control_failure_artifact(
    spec: FrozenSpec, contract: Mapping[str, Any], provenance: Mapping[str, Any],
    schema_version: str, detail: str, implementation_manifest_path: Path | None,
) -> dict[str, Any]:
    return {
        "artifact": contract["artifacts"][2],
        "control_failure": detail,
        "provenance": dict(provenance),
        "schema_version": schema_version,
        "stage_id": contract["campaign"]["name"],
        "status": preemptive_status(
            spec, contract["stage"], "control_failure",
            implementation_manifest_path=implementation_manifest_path,
        ),
    }


def evaluate_g2a(
    spec: FrozenSpec,
    *,
    inventory_authorization: InventoryAuthorization,
    persisted_invocation_manifest_path: Path,
    persisted_invocation_manifest_sha256: str,
    structural_gate: StructuralGate | None,
    attempt_registry: AttemptRegistry,
    unit_records_path: Path,
    provenance: Mapping[str, Any],
    content_root: Path | None = None,
    implementation_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Evaluate a sealed complete G2a campaign without invoking scientific code."""
    contract = _contract(spec, implementation_manifest_path)
    shapes = contract["shapes"]
    schema_version = shapes["version"]
    emission_families = [
        marker.decode("utf-8")[:-1] for marker in _raw_marker_contract(spec)
    ]
    report = assess_completeness(
        spec, stage=contract["stage"], campaign_name=contract["campaign"]["name"],
        expected_schema=schema_version, required_emission_families=emission_families,
        inventory_authorization=inventory_authorization,
        persisted_invocation_manifest_path=persisted_invocation_manifest_path,
        persisted_invocation_manifest_sha256=persisted_invocation_manifest_sha256,
        structural_gate=structural_gate, attempt_registry=attempt_registry,
        implementation_manifest_path=implementation_manifest_path,
    )
    report.require_complete()
    if structural_gate is None:
        raise IncompleteCampaign("complete G2a report lacks its sealed structural gate")
    try:
        sealed_units = _sealed_g2a_unit_artifact(
            spec, attempt_registry, structural_gate
        )
    except SealedG2aFiniteFailure as error:
        try:
            persisted = unit_records_path.read_bytes()
        except OSError as read_error:
            raise IncompleteCampaign(
                f"G2a unit artifact is unavailable: {read_error}"
            ) from read_error
        if persisted != error.artifact_bytes:
            raise IncompleteCampaign(
                "G2a finite-control artifact bytes disagree with sealed captures"
            )
        _validate_provenance_binding(
            spec, provenance, contract, error.artifact_sha256
        )
        return _control_failure_artifact(
            spec, contract, provenance, schema_version, error.message,
            implementation_manifest_path,
        )
    try:
        unit_records = load_canonical_record_artifact(
            unit_records_path, sealed_units.sha256
        )
    except ControlFailureEvidence as error:
        _validate_provenance_binding(spec, provenance, contract, sealed_units.sha256)
        return _control_failure_artifact(
            spec, contract, provenance, schema_version, error.message,
            implementation_manifest_path,
        )
    _reject_synthetic_campaign_evidence(unit_records, contract["synthetic_prefix"])
    _validate_provenance_binding(spec, provenance, contract, sealed_units.sha256)
    try:
        records = validate_stage_records(
            spec, unit_records, stage_profile=contract["stage_profile"],
                expected_structural_manifest_sha256=sealed_units.structural_bindings,
            expected_attempt_record_sha256=sealed_units.attempt_bindings,
            content_root=content_root,
            implementation_manifest_path=implementation_manifest_path,
        )
    except ControlFailureEvidence as error:
        return _control_failure_artifact(
            spec, contract, provenance, schema_version, error.message,
            implementation_manifest_path,
        )
    return evaluate_g2a_records(spec, records, provenance=provenance,
        completeness=asdict(report), implementation_manifest_path=implementation_manifest_path)


def evaluate_g2a_records(spec, records, *, provenance, completeness,
                         implementation_manifest_path=None):
    """Inference on validated records; shared by historical and public I/O.

    The registered arithmetic and RNG domains are unchanged. The caller must
    bind completeness and validate universal records before this boundary.
    """
    contract = _contract(spec, implementation_manifest_path)
    shapes = contract["shapes"]
    schema_version = shapes["version"]
    tie_tolerance = contract["dtv_tie_tolerance"]
    if type(tie_tolerance) not in (int, float) or not math.isfinite(float(tie_tolerance)):
        raise SpecMismatch("frozen G2a dTV tie tolerance is not finite numeric")
    for record in records:
        if not record["eligibility"]:
            continue
        expected_ties = {
            contrast_id: abs(record["pairwise_contrast"][contrast_id]) <= tie_tolerance
            for contrast_id in shapes["contrast_identifiers"]["tie_flags"]
        }
        if record["tie_flag"] != expected_ties:
            return _control_failure_artifact(
                spec, contract, provenance, schema_version,
                "G2a tie flags disagree with the frozen dTV tolerance",
                implementation_manifest_path,
            )
    if not _controls_pass(records, shapes["stage_profiles"]["g2a"]):
        return _control_failure_artifact(
            spec, contract, provenance, schema_version,
            "one or more independently recomputed controls did not pass",
            implementation_manifest_path,
        )
    eligible = [record for record in records if record["eligibility"]]
    grid = contract["grid"]
    excluded_labels = {label for item in grid["ineligible"] for label in item["labels"] if label in grid["labels"]}
    expected_configs = [label for label in grid["labels"] if label not in excluded_labels]
    expected_seeds = contract["campaign"]["seeds"]
    if len(expected_configs) != grid["eligibility"]["eligible_count"]:
        raise SpecMismatch("frozen G2a eligible config population disagrees")
    present_excluded = sorted(excluded_labels)
    exclusion_reason = spec.get(
        "/completeness/g2a_raw_stdout_derivation/field_derivations/exclusion_reason_code/expression/arguments/1/value",
        expected_type=str,
    )
    exclusion_reasons = {label: exclusion_reason for label in present_excluded}
    campaign_experiment = contract["campaign"]["experiments"][0]
    for record in records:
        if (
            record["experiment"] != campaign_experiment
            or record["scale"] not in contract["campaign"]["scales"]
            or record["seed"] not in expected_seeds
            or record["config_or_null"] not in grid["labels"]
        ):
            raise IncompleteCampaign("G2a unit lies outside the frozen campaign census")
        if record["config_or_null"] in expected_configs:
            if not record["eligibility"] or record["exclusion_reason_code"] is not None:
                raise IncompleteCampaign("G2a eligible-config disposition disagrees")
        elif (
            record["eligibility"]
            or record["config_or_null"] not in exclusion_reasons
            or record["exclusion_reason_code"]
            != exclusion_reasons[record["config_or_null"]]
        ):
            raise IncompleteCampaign("G2a inert-control disposition disagrees")
    expected_all = {
        (seed, config)
        for seed in expected_seeds
        for config in grid["labels"]
    }
    for kind in contract["observation_maps"]["kind_set"]:
        all_observed = {
            (record["seed"], record["config_or_null"])
            for record in records if record["_derived_kind"] == kind
        }
        if all_observed != expected_all:
            raise IncompleteCampaign(
                f"G2a {kind} universal registry omits or adds campaign invocations"
            )
        observed = {(record["seed"], record["config_or_null"]) for record in eligible if record["_derived_kind"] == kind}
        expected = {(seed, config) for seed in expected_seeds for config in expected_configs}
        if observed != expected:
            raise IncompleteCampaign(f"G2a eligible {kind} fixed census is incomplete or altered")

    competitor_labels = shapes["competitor_labels"]
    contrast_ids = shapes["contrast_identifiers"]
    kinds = contract["observation_maps"]["kind_set"]
    primary_contrast_ids = contrast_ids["primary_competitor"]
    if len(primary_contrast_ids) != len(competitor_labels) or any(
        not contrast_id.startswith(f"D__{competitor}_minus_")
        for competitor, contrast_id in zip(competitor_labels, primary_contrast_ids)
    ):
        raise SpecMismatch("frozen G2a competitor labels and contrasts disagree")
    candidate_labels = {
        contrast_id.split("_minus_", 1)[1]
        for contrast_id in primary_contrast_ids
    }
    if len(candidate_labels) != 1:
        raise SpecMismatch("frozen G2a competitor contrasts lack one candidate")
    candidate_label = next(iter(candidate_labels))
    definitions = [
        (kind, competitor, contrast_id, 1.0)
        for kind in kinds
        for competitor, contrast_id in zip(competitor_labels, primary_contrast_ids)
    ] + [
        (kind, None, contrast_ids["factor2"], -1.0) for kind in kinds
    ]
    raw_results: dict[str, dict[str, Any]] = {}
    pending: dict[str, dict[str, Any]] = {}
    one_sided: dict[str, float] = {}
    derive_key = key_deriver(
        spec, implementation_manifest_path=implementation_manifest_path
    )
    raw_pkg_view_counts = {
        kind: sum(record["_derived_kind"] == kind for record in records)
        for kind in kinds
    }
    for kind, competitor, contrast_id, orientation in definitions:
        statistic_id = f"{kind}::{contrast_id}"
        selected = [record for record in eligible if record["_derived_kind"] == kind]
        values, brier, hierarchy_counts = _hierarchical_values(
            selected, contrast_id, factor2=contract["factor2"]
        )
        seed_values = tuple(
            _mean([values[seed][config] for config in expected_configs]) * orientation
            for seed in expected_seeds
        )
        point = _mean(seed_values)
        two_sided_p, one_sided_p = _conditional_sign_p(seed_values)
        boot = _bootstrap_result(
            seed_values, stage_id=contract["campaign"]["name"],
            statistic_id=statistic_id, inference=contract["inference"],
            derive_key=derive_key,
            rng_contract=contract["rng"],
            attested_json_sha256=spec.attestation.json_sha256,
        )
        sensitivities = _sensitivity_atoms(
            point, values, brier, orientation=orientation,
            seeds=expected_seeds, configs=expected_configs,
        )
        sensitivity_results = _sensitivity_results(
            stage_id=contract["campaign"]["name"], statistic_id=statistic_id,
            primary_bootstrap=boot,
            atoms=sensitivities, values=values, brier=brier,
            orientation=orientation, seeds=expected_seeds,
            configs=expected_configs, inference=contract["inference"],
            derive_key=derive_key,
            rng_contract=contract["rng"],
            attested_json_sha256=spec.attestation.json_sha256,
        )
        pending[statistic_id] = {
            "kind": kind, "competitor": competitor, "contrast_id": contrast_id,
            "orientation": orientation, "seed_values": seed_values, "point": point,
            "two_sided_p": two_sided_p, "one_sided_p": one_sided_p,
            "boot": boot, "hierarchy_counts": hierarchy_counts,
            "sensitivities": sensitivities,
            "sensitivity_results": sensitivity_results,
        }
        one_sided[statistic_id] = one_sided_p
    adjusted = _holm(one_sided)
    statistics_by_id: dict[str, G2aStatistic] = {}
    for statistic_id, item in pending.items():
        standard_error = statistics.stdev(item["seed_values"]) / math.sqrt(len(item["seed_values"]))
        statistic = G2aStatistic(
            statistic_id=statistic_id, kind=item["kind"], competitor_or_null=item["competitor"],
            orientation=(
                f"positive favors {candidate_label}"
                if item["orientation"] == 1
                else "positive favors factor-2 serviceability"
            ),
            seed_block_estimates=item["seed_values"], point_estimate=item["point"],
            standard_error=standard_error, conditional_two_sided_p=item["two_sided_p"],
            conditional_one_sided_p=item["one_sided_p"], holm_adjusted_p=adjusted[statistic_id],
            percentile_interval=item["boot"]["percentile_interval"],
            bca_equal_tail_interval=item["boot"]["bca_equal_tail_interval"],
            bca_simultaneous_lower=item["boot"]["bca_simultaneous_lower"],
            bca_simultaneous_upper=item["boot"]["bca_simultaneous_upper"],
            z0=item["boot"]["z0"], acceleration=item["boot"]["acceleration"],
            adjusted_probabilities=item["boot"]["adjusted_probabilities"],
            jackknife_values=item["boot"]["jackknife_values"],
            replicate_estimates=item["boot"]["replicate_estimates"],
            hierarchy_counts=item["hierarchy_counts"],
            raw_pkg_view_counts=raw_pkg_view_counts,
            sensitivity_atoms=item["sensitivities"],
            sensitivity_results=item["sensitivity_results"],
            rng_audit=item["boot"]["rng_audit"],
        )
        statistics_by_id[statistic_id] = statistic
        raw_results[statistic_id] = asdict(statistic)

    lower = {kind: {} for kind in kinds}
    upper = {kind: {} for kind in kinds}
    p_adjusted = {kind: {} for kind in kinds}
    service_lower: dict[str, float | None] = {}
    service_upper: dict[str, float | None] = {}
    for statistic in statistics_by_id.values():
        if statistic.competitor_or_null is None:
            service_lower[statistic.kind] = None if statistic.bca_simultaneous_upper is None else -statistic.bca_simultaneous_upper
            service_upper[statistic.kind] = None if statistic.bca_simultaneous_lower is None else -statistic.bca_simultaneous_lower
        else:
            lower[statistic.kind][statistic.competitor_or_null] = statistic.bca_simultaneous_lower
            upper[statistic.kind][statistic.competitor_or_null] = statistic.bca_simultaneous_upper
            p_adjusted[statistic.kind][statistic.competitor_or_null] = statistic.holm_adjusted_p
    status = select_g2a_branch(
        spec,
        G2aDecisionInputs(
            sensitivity_reversal=_has_reversal(statistics_by_id), lower=lower, upper=upper,
            holm_adjusted_p=p_adjusted, serviceability_lower=service_lower,
            serviceability_upper=service_upper,
        ),
        implementation_manifest_path=implementation_manifest_path,
    )
    claims = [
        row for row in contract["claims"]
        if any(
            slot.startswith(f"{contract['campaign']['name']}_")
            for slot in row.get("v2_slots", [])
        )
    ]
    if len(claims) != 2:
        raise SpecMismatch("frozen G2a claim-slot mapping is not exactly two rows")
    return {
        "artifact": contract["artifacts"][2],
        "claim_slots": claims,
        "completeness": dict(completeness),
        "competitor_order": competitor_labels,
        "endpoint_ledger_size": contract["inference"]["multiplicity"]["endpoint_ledgers"]["g2a"],
        "p_value_family_size": contract["inference"]["multiplicity"]["p_value_family_sizes"]["g2a"],
        "provenance": dict(provenance),
        "schema_version": schema_version,
        "stage_id": contract["campaign"]["name"],
        "statistics": raw_results,
        "status": status,
    }

# Production writers restored from the same historical implementation.

def _attempt_bindings(
    registry: AttemptRegistry, invocation_ids: Sequence[str]
) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for invocation_id in sorted(set(invocation_ids)):
        attempts = registry.attempts_for(invocation_id)
        if not attempts:
            raise IncompleteCampaign(
                f"sealed G2a attempt record is absent for {invocation_id}"
            )
        bindings[invocation_id] = sha256_bytes(canonical_json_bytes(attempts[-1]))
    return bindings
