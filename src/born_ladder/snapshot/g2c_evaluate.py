"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import copy
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from born_ladder.snapshot.errors import ControlFailureEvidence, IncompleteCampaign, SpecMismatch
from born_ladder.snapshot.frozen_spec import FrozenSpec
from born_ladder.snapshot.g2a import _holm, _mean, _percentile_summary
from born_ladder.snapshot.statistics_helpers import _bca_summary, _bootstrap_rng_audit_v16, _conditional_sign_p_exact
from born_ladder.snapshot.g2c_controls import validate_g2c_v22_rotation_evidence
from born_ladder.snapshot.evidence import validate_g2c_control_input_binding
from born_ladder.snapshot.identities import kind_cell_id
from born_ladder.snapshot.rng import RNGStream, key_deriver
from born_ladder.snapshot.status import require_recognized_status

_POINTERS = {
    "g2c_evaluate_bootstrap": "/inference/bootstrap",
    "g2c_evaluate_bootstrap_audit_shape": "/completeness/universal_evidence_shapes/stage_control_shapes/bootstrap_rng_audit",
    "g2c_evaluate_bca": "/inference/bca",
    "g2c_evaluate_campaign": "/confirmation_data/campaigns/6",
    "g2c_evaluate_claims": "/claim_mapping/rows",
    "g2c_evaluate_derivation": "/completeness/g2c_raw_stdout_derivation",
    "g2c_evaluate_empty_groups": "/estimands/g2c_empty_group_convention",
    "g2c_evaluate_law_labels": "/completeness/universal_evidence_shapes/all_law_labels",
    "g2c_evaluate_multiplicity": "/inference/multiplicity",
    "g2c_evaluate_persistence": "/artifact_paths/g2c_per_unit_reproduction_plan/evaluation_artifact_contract",
    "g2c_evaluate_rng": "/rng",
    "g2c_evaluate_rng_version": "/rng/framing/master_prefix",
    "g2c_evaluate_sensitivities": "/inference/sensitivities",
    "g2c_evaluate_table": "/branch_truth_tables/tables/9",
    "g2c_evaluate_threshold_margin": "/thresholds/items/2/value",
    "g2c_evaluate_threshold_coefficient": "/thresholds/items/3/value",
    "g2c_evaluate_threshold_tie": "/thresholds/items/5/value",
}


@dataclass(frozen=True)
class G2CDecision:
    vacuous: bool

    sensitivity_reversal: bool

    spectral_non_evaluability: bool

    lower: Mapping[str, float | None]

    upper: Mapping[str, float | None]

    holm_adjusted_p: Mapping[str, float]



def _contract(spec: FrozenSpec, manifest: Path | None = None) -> dict[str, Any]:
    spec.audit_implementation_manifest(
        "g2c_evaluate", manifest_path=manifest, declared_pointers=_POINTERS
    )
    value = {name.removeprefix("g2c_evaluate_"): spec.get(pointer) for name, pointer in _POINTERS.items()}
    table = value["table"]
    estimand = value["derivation"]["estimand_realization"]
    if (
        value["campaign"] != {
            "experiments": ["EXP-112", "EXP-102", "EXP-103", "EXP-104", "EXP-105", "EXP-106", "EXP-107"],
            "name": "g2c_v2",
            "scales": [32],
            "seeds": list(range(840001, 840021)),
        }
        or table.get("id") != "g2c"
        or [row["priority"] for row in table["rows"]] != list(range(1, 9))
        or table["rows"][-1].get("ordered_fallback") is not True
        or value["multiplicity"]["p_value_family_sizes"]["g2c"] != 2
        or value["multiplicity"]["endpoint_ledgers"]["g2c"] != 4
        or estimand["source_combination"]["source_order"] != ["EXP-112", "G2x"]
        or estimand["source_combination"]["weights"]
        != [{"numerator": 1, "denominator": 2}, {"numerator": 1, "denominator": 2}]
        or value["threshold_margin"] != {"numerator": 1, "denominator": 240}
        or value["threshold_tie"] != 1e-12
    ):
        raise SpecMismatch("frozen G2c inference contract disagrees")
    return value


def select_g2c_branch(
    spec: FrozenSpec,
    decision: G2CDecision,
    *,
    implementation_manifest_path: Path | None = None,
) -> str:
    """Apply frozen table 9 in priority order, including its sole fallback."""
    contract = _contract(spec, implementation_manifest_path)
    kinds = ("raw", "pkg")
    if (
        type(decision.vacuous) is not bool
        or type(decision.sensitivity_reversal) is not bool
        or type(decision.spectral_non_evaluability) is not bool
        or set(decision.lower) != set(kinds)
        or set(decision.upper) != set(kinds)
        or set(decision.holm_adjusted_p) != set(kinds)
    ):
        raise IncompleteCampaign("G2c branch inputs disagree with their closed census")
    for name, values, nullable in (
        ("lower", decision.lower, True),
        ("upper", decision.upper, True),
        ("adjusted p", decision.holm_adjusted_p, False),
    ):
        for kind, value in values.items():
            if nullable and value is None:
                continue
            if type(value) not in (int, float) or not math.isfinite(float(value)):
                raise IncompleteCampaign(f"G2c {name} {kind} is not finite binary64")
            if name == "adjusted p" and not 0.0 <= float(value) <= 1.0:
                raise IncompleteCampaign("G2c adjusted p lies outside [0,1]")
    margin = contract["threshold_margin"]["numerator"] / contract["threshold_margin"]["denominator"]
    lower = decision.lower
    upper = decision.upper
    sensitivity = decision.sensitivity_reversal or decision.spectral_non_evaluability
    predicates = [
        decision.vacuous,
        not decision.vacuous and sensitivity,
        not decision.vacuous and not sensitivity and all(
            lower[kind] is not None and lower[kind] > margin
            and decision.holm_adjusted_p[kind] <= contract["multiplicity"]["alpha"]
            for kind in kinds
        ),
        not decision.vacuous and not sensitivity and all(
            lower[kind] is not None and lower[kind] > 0 for kind in kinds
        ) and any(lower[kind] <= margin for kind in kinds),
        not decision.vacuous and not sensitivity and all(
            lower[kind] is not None and upper[kind] is not None
            and lower[kind] >= -margin and upper[kind] <= margin
            for kind in kinds
        ) and any(lower[kind] <= 0 <= upper[kind] for kind in kinds),
        not decision.vacuous and not sensitivity and any(
            upper[kind] is not None and upper[kind] < -margin for kind in kinds
        ),
        not decision.vacuous and not sensitivity and all(
            upper[kind] is not None and upper[kind] < 0 for kind in kinds
        ) and all(upper[kind] >= -margin for kind in kinds),
        not decision.vacuous and not sensitivity,
    ]
    rows = contract["table"]["rows"]
    selected = next((row["status"] for row, matched in zip(rows, predicates, strict=True) if matched), None)
    if selected is None:
        raise SpecMismatch("frozen G2c table selected no branch")
    return require_recognized_status(
        spec, "g2c", selected, implementation_manifest_path=implementation_manifest_path
    )


def _record_kind(record: Mapping[str, Any]) -> str:
    unit = record.get("unit_id")
    for kind in ("raw", "pkg"):
        if record.get("kind_cell_id") == kind_cell_id(unit, kind):
            return kind
    raise IncompleteCampaign("G2c record kind-cell identity disagrees")


def _source_seed_values(
    records: Sequence[Mapping[str, Any]],
    controls: Sequence[Mapping[str, Any]],
    *,
    metric: str,
    seeds: Sequence[int],
    diagonal_label: str = "q_diag",
) -> tuple[
    dict[str, dict[str, dict[int, dict[str, float]]]],
    list[dict[str, Any]],
    dict[str, dict[str, dict[int, tuple[str, ...]]]],
    dict[str, dict[str, dict[int, tuple[str, ...]]]],
    list[dict[str, Any]],
]:
    if len(records) != len(controls):
        raise IncompleteCampaign("G2c unit/control census differs")
    census: dict[str, Any] = {
        source: {kind: {seed: {} for seed in seeds} for kind in ("raw", "pkg")}
        for source in ("EXP-112", "G2x")
    }
    eligible_scheduled: dict[str, dict[str, dict[int, set[str]]]] = {
        source: {kind: {seed: set() for seed in seeds} for kind in ("raw", "pkg")}
        for source in ("EXP-112", "G2x")
    }
    structural_scheduled: dict[str, dict[str, dict[int, set[str]]]] = {
        source: {kind: {seed: set() for seed in seeds} for kind in ("raw", "pkg")}
        for source in ("EXP-112", "G2x")
    }
    witnesses: list[dict[str, Any]] = []
    for record, control in zip(records, controls, strict=True):
        if (
            control.get("unit_id") != record.get("unit_id")
            or control.get("kind_cell_id") != record.get("kind_cell_id")
        ):
            raise IncompleteCampaign("G2c unit/control join differs")
        source, seed, kind = record.get("source_key"), record.get("seed"), _record_kind(record)
        if source not in census or seed not in seeds:
            raise IncompleteCampaign("G2c record lies outside frozen source/seed census")
        group = record.get("fixed_census_config_or_experiment_key")
        invocation = record.get("invocation_id")
        context = record.get("context")
        if not all(isinstance(value, str) and value for value in (group, invocation, context)):
            raise IncompleteCampaign("G2c hierarchy identity is absent")
        structural_scheduled[source][kind][seed].add(group)
        eligible = record.get("eligibility") is True
        nondegenerate = control.get("nondegenerate") is True
        if eligible:
            eligible_scheduled[source][kind][seed].add(group)
        classification = (
            "planned_exclusion" if not eligible
            else "eligible_nondegenerate" if nondegenerate
            else "eligible_spectrally_empty"
        )
        contrast: float | None = None
        if eligible and nondegenerate:
            if metric == "dtv":
                values = record.get("dtv_loss", {})
            elif metric == "brier" or metric.startswith("brier_law:"):
                values = record.get("brier_score", {})
            else:
                raise SpecMismatch("unknown G2c metric")
            if metric.startswith("brier_law:"):
                law = metric.split(":", 1)[1]
                value = values.get(law)
                if type(value) not in (int, float):
                    raise IncompleteCampaign("G2c Brier law evidence is nonnumeric")
                contrast = float(value)
            else:
                left, right = values.get(diagonal_label), values.get("q_full")
                if type(left) not in (int, float) or type(right) not in (int, float):
                    raise IncompleteCampaign("G2c q-diag/q-full evidence is nonnumeric")
                contrast = float(left) - float(right)
            if metric == "dtv" and abs(contrast) <= 1e-12:
                contrast = 0.0
        census[source][kind][seed].setdefault(str(group), {}).setdefault(
            str(invocation), {}
        ).setdefault(str(context), []).append({
            "unit_id": record.get("unit_id"),
            "kind_cell_id": record.get("kind_cell_id"),
            "recorded_step": record.get("step"),
            "classification": classification,
            "eligibility": record.get("eligibility"),
            "exclusion_reason_code": record.get("exclusion_reason_code"),
            "nondegenerate": control.get("nondegenerate"),
            "attempt_record_sha256": record.get("attempt_record_sha256"),
            "structural_manifest_sha256": record.get(
                "structural_manifest_sha256"
            ),
            "value": contrast,
        })
    result: dict[str, dict[str, dict[int, dict[str, float]]]] = {
        source: {kind: {} for kind in ("raw", "pkg")} for source in ("EXP-112", "G2x")
    }
    support: dict[str, dict[str, dict[int, tuple[str, ...]]]] = {
        source: {kind: {} for kind in ("raw", "pkg")} for source in ("EXP-112", "G2x")
    }
    structural_support: dict[str, dict[str, dict[int, tuple[str, ...]]]] = {
        source: {kind: {} for kind in ("raw", "pkg")} for source in ("EXP-112", "G2x")
    }
    hierarchy_levels: list[dict[str, Any]] = []
    for source in result:
        for kind in result[source]:
            for seed in seeds:
                groups: dict[str, float] = {}
                for group, invocations in sorted(census[source][kind][seed].items()):
                    invocation_rows: list[dict[str, Any]] = []
                    invocation_means: list[float] = []
                    for invocation_id, contexts in sorted(invocations.items()):
                        context_rows = []
                        for context, step_rows in sorted(contexts.items()):
                            defined = [
                                float(row["value"]) for row in step_rows
                                if row["value"] is not None
                            ]
                            context_rows.append({
                                "context": context,
                                "step_count": len(step_rows),
                                "total_step_count": len(step_rows),
                                "eligible_step_count": sum(
                                    row["eligibility"] is True for row in step_rows
                                ),
                                "nondegenerate_step_count": len(defined),
                                "degenerate_step_count": sum(
                                    row["classification"] == "eligible_spectrally_empty"
                                    for row in step_rows
                                ),
                                "planned_exclusion_step_count": sum(
                                    row["classification"] == "planned_exclusion"
                                    for row in step_rows
                                ),
                                "denominator": len(defined),
                                "step_values": defined,
                                "steps": copy.deepcopy(step_rows),
                                "empty_child_identities": [
                                    row["kind_cell_id"] for row in step_rows
                                    if row["value"] is None
                                ],
                                "context_mean": _mean(defined) if defined else None,
                            })
                        defined_contexts = [
                            float(row["context_mean"]) for row in context_rows
                            if row["context_mean"] is not None
                        ]
                        invocation_mean = (
                            _mean(defined_contexts) if defined_contexts else None
                        )
                        if invocation_mean is not None:
                            invocation_means.append(invocation_mean)
                        invocation_rows.append({
                            "invocation_id": invocation_id,
                            "context_count": len(context_rows),
                            "total_context_count": len(context_rows),
                            "eligible_context_count": sum(
                                bool(row["eligible_step_count"]) for row in context_rows
                            ),
                            "nondegenerate_context_count": len(defined_contexts),
                            "degenerate_context_count": sum(
                                bool(row["degenerate_step_count"]) for row in context_rows
                            ),
                            "planned_exclusion_context_count": sum(
                                bool(row["planned_exclusion_step_count"])
                                for row in context_rows
                            ),
                            "empty_child_identities": [
                                row["context"] for row in context_rows
                                if row["context_mean"] is None
                            ],
                            "denominator": len(defined_contexts),
                            "contexts": context_rows,
                            "invocation_mean": invocation_mean,
                        })
                    if invocation_means:
                        groups[group] = _mean(invocation_means)
                    hierarchy_levels.append({
                        "source_key": source,
                        "kind": kind,
                        "seed": seed,
                        "group": group,
                        "planned_exclusion": (
                            group not in eligible_scheduled[source][kind][seed]
                        ),
                        "spectrally_nonempty": bool(invocation_means),
                        "invocation_count": len(invocation_rows),
                        "total_invocation_count": len(invocation_rows),
                        "eligible_invocation_count": sum(
                            bool(row["eligible_context_count"])
                            for row in invocation_rows
                        ),
                        "nondegenerate_invocation_count": len(invocation_means),
                        "nonempty_invocation_count": len(invocation_means),
                        "empty_invocation_count": len(invocation_rows) - len(invocation_means),
                        "empty_child_identities": [
                            row["invocation_id"] for row in invocation_rows
                            if row["invocation_mean"] is None
                        ],
                        "denominator": len(invocation_means),
                        "invocations": invocation_rows,
                        "group_mean": groups.get(group),
                    })
                result[source][kind][seed] = groups
                support[source][kind][seed] = tuple(
                    sorted(eligible_scheduled[source][kind][seed])
                )
                structural_support[source][kind][seed] = tuple(
                    sorted(structural_scheduled[source][kind][seed])
                )
                if not groups:
                    witnesses.append({
                        "source_key": source,
                        "kind": kind,
                        "seed": seed,
                        "scheduled_groups": list(support[source][kind][seed]),
                        "spectrally_nonempty_groups": [],
                    })
    return result, witnesses, support, structural_support, hierarchy_levels


def _combined_seed_vector(
    values: Mapping[str, Mapping[str, Mapping[int, Mapping[str, float]]]],
    *,
    kind: str,
    seeds: Sequence[int],
) -> tuple[float, ...] | None:
    combined: list[float] = []
    for seed in seeds:
        source_values = []
        for source in ("EXP-112", "G2x"):
            groups = values[source][kind][seed]
            if not groups:
                return None
            source_values.append(_mean(list(groups.values())))
        combined.append(0.5 * source_values[0] + 0.5 * source_values[1])
    return tuple(combined)


def _undefined(
    reason: str, witness: Any, prescribed: int = 1, *, defined: int = 0,
) -> dict[str, Any]:
    if not 0 <= defined <= prescribed:
        raise IncompleteCampaign("G2c undefined-result counts do not reconcile")
    return {
        "value": None,
        "reason_code": reason,
        "empty_population_witness": witness,
        "replicate_counts": {
            "prescribed": prescribed,
            "defined": defined,
            "undefined": prescribed - defined,
        },
    }


def _paired_bootstrap_results(
    spec: FrozenSpec,
    vectors: Mapping[str, Sequence[float]],
    *, inference: Mapping[str, Any], contract: Mapping[str, Any], derive_key: Any,
    stage_id: str = "g2c_v2",
) -> dict[str, dict[str, Any]]:
    """Draw one seed membership per replicate and apply it to every vector."""
    expected = inference["conditional_sign_randomization"]["seed_blocks"]
    if not vectors or any(len(vector) != expected for vector in vectors.values()):
        raise IncompleteCampaign("G2c paired bootstrap vector census disagrees")
    estimates: dict[str, list[float]] = {name: [] for name in vectors}
    memberships: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    statistic = "paired_kinds_sources_metrics"
    for replicate in range(inference["bootstrap"]["replicates"]):
        key = derive_key("bootstrap", {
            "stage_id": stage_id, "statistic_id": statistic,
            "replicate_index": replicate,
        })
        stream = RNGStream(key)
        indices = [stream.unbiased_index(expected) for _ in range(expected)]
        memberships.append({
            "replicate_index": replicate,
            "paired_draw_id": f"g2c_seed_membership_{replicate:05d}",
            "statistic_id": statistic,
            "sampled_seed_indices": indices,
            "support_count": expected,
            "denominator": expected,
        })
        for name, vector in vectors.items():
            estimates[name].append(_mean([float(vector[index]) for index in indices]))
        audits.append(_bootstrap_rng_audit_v16(
            stage_id=stage_id, statistic_id=statistic,
            replicate_index=replicate, key=key, stream=stream,
            rng_contract=contract["rng"],
            attested_json_sha256=getattr(
                spec, "_g2c_source_spec", spec
            ).attestation.json_sha256,
            shape=contract["bootstrap_audit_shape"],
            implementation_version=contract["rng_version"],
        ))
    return {
        name: {
            **_bca_summary(vector, estimates[name], inference),
            "statistic_id": statistic,
            "replicate_estimates": tuple(estimates[name]),
            "replicate_membership": copy.deepcopy(memberships),
            "rng_audit": tuple(copy.deepcopy(audits)),
        }
        for name, vector in vectors.items()
    }


def _config_only_estimate(
    values: Mapping[str, Mapping[str, Mapping[int, Mapping[str, float]]]],
    *,
    kind: str,
    seeds: Sequence[int],
    source_groups: Mapping[str, Sequence[str]],
    selected: Mapping[str, Sequence[int]],
) -> tuple[float | None, dict[str, Any]]:
    """Apply one retained config/experiment-only draw without redraw or imputation."""
    source_estimates: list[float] = []
    support_count = 0
    failure_witnesses: list[dict[str, Any]] = []
    selected_occurrences: list[dict[str, Any]] = []
    for source in ("EXP-112", "G2x"):
        group_estimates: list[float] = []
        source_partial = False
        for occurrence, index in enumerate(selected[source]):
            group = source_groups[source][index]
            present = [values[source][kind][seed].get(group) for seed in seeds]
            present_count = sum(value is not None for value in present)
            support_count += present_count
            occurrence_record = {
                "source_key": source,
                "selected_occurrence": occurrence,
                "group": group,
                "support_count": present_count,
                "prescribed_seed_count": len(seeds),
                "support_state": (
                    "all_seed_spectral_emptiness"
                    if present_count == 0
                    else "complete_across_seed_support"
                    if present_count == len(seeds)
                    else "partial_across_seed_support"
                ),
                "missing_seeds": [
                    seed for seed, value in zip(seeds, present, strict=True)
                    if value is None
                ],
                "included_in_source_denominator": present_count == len(seeds),
            }
            selected_occurrences.append(occurrence_record)
            if present_count == len(seeds):
                group_estimates.append(_mean([float(value) for value in present]))
            elif present_count:
                source_partial = True
                failure_witnesses.append(copy.deepcopy(occurrence_record))
        if source_partial:
            continue
        if group_estimates:
            # All-seed-empty selected occurrences stay in the membership record but
            # contribute neither a numerical term nor source-denominator weight.
            source_estimates.append(_mean(group_estimates))
        else:
            failure_witnesses.append({
                "source_key": source,
                "support_state": "zero_supported_sampled_source_weight",
                "selected_occurrences": [
                    copy.deepcopy(row) for row in selected_occurrences
                    if row["source_key"] == source
                ],
            })
    membership = {
        "selected_group_indices_by_source": copy.deepcopy(dict(selected)),
        "selected_occurrences": selected_occurrences,
        "support_count": support_count,
        "denominator": sum(len(indices) for indices in selected.values()) * len(seeds),
        "empty_population_witness": failure_witnesses or None,
        "reason_code": (
            None if not failure_witnesses
            else "UNDEFINED_REQUIRED_ACROSS_SEED_GROUP_MEAN"
            if any(
                row["support_state"] == "partial_across_seed_support"
                for row in failure_witnesses
            )
            else "EMPTY_REQUIRED_SPECTRAL_POPULATION"
        ),
    }
    estimate = (
        0.5 * source_estimates[0] + 0.5 * source_estimates[1]
        if len(source_estimates) == 2 and not failure_witnesses else None
    )
    return estimate, membership


def _sensitivities(
    values: Mapping[str, Mapping[str, Mapping[int, Mapping[str, float]]]],
    brier: Mapping[str, Mapping[str, Mapping[int, Mapping[str, float]]]],
    *,
    kind: str,
    seeds: Sequence[int],
    primary: float,
    primary_bootstrap: Mapping[str, Any],
    brier_bootstrap: Mapping[str, Any],
    brier_ranking: Mapping[str, Any],
    scheduled: Mapping[str, Mapping[str, Mapping[int, Sequence[str]]]],
    contract: Mapping[str, Any],
    derive_key: Any,
    spec: FrozenSpec,
    paired_membership_cache: dict[str, list[tuple[Any, Mapping[str, Any]]]],
    stage_id: str = "g2c_v2",
) -> tuple[dict[str, Any], bool, bool]:
    names = [
        "seed-only fixed census",
        "config/experiment-only superpopulation",
        "hierarchical seed then config/experiment superpopulation",
        "leave-one-seed-out",
        "leave-one-config/experiment-out",
        "separate EXP-112 and G2x",
        "two-way pigeonhole seed by config/experiment",
        "Brier complete ranking",
    ]
    combined = _combined_seed_vector(values, kind=kind, seeds=seeds)
    if combined is None:
        return {name: _undefined("EMPTY_REQUIRED_SPECTRAL_POPULATION", {"kind": kind}) for name in names}, False, True
    atoms: dict[str, Sequence[float] | None] = {
        names[0]: (primary,),
        names[2]: (primary,),
        names[3]: tuple(_mean([value for index, value in enumerate(combined) if index != omitted]) for omitted in range(len(seeds))),
        names[5]: tuple(
            _mean([_mean(list(values[source][kind][seed].values())) for seed in seeds])
            for source in ("EXP-112", "G2x")
        ),
        names[6]: (primary,),
    }
    leave_one_seed_positions = [
        {
            "deletion_index": omitted,
            "membership": {"omitted_seed": seeds[omitted]},
            "support_count": len(seeds) - 1,
            "denominator": len(seeds) - 1,
            "value": value,
            "reason_code": None,
            "empty_population_witness": None,
        }
        for omitted, value in enumerate(atoms[names[3]] or ())
    ]
    source_groups = {
        source: tuple(sorted({
            group for seed in seeds for group in scheduled[source][kind][seed]
        }))
        for source in ("EXP-112", "G2x")
    }
    across_source_means: list[float] = []
    deletions: list[float] = []
    deletion_positions: list[dict[str, Any]] = []
    across_witnesses: list[dict[str, Any]] = []
    deletion_witnesses: list[dict[str, Any]] = []
    for source in ("EXP-112", "G2x"):
        group_means: list[float] = []
        for group in source_groups[source]:
            per_seed = [values[source][kind][seed].get(group) for seed in seeds]
            if all(value is None for value in per_seed):
                continue
            if any(value is None for value in per_seed):
                across_witnesses.append({"source_key": source, "kind": kind, "group": group})
            else:
                group_means.append(_mean([float(value) for value in per_seed]))
        if group_means:
            across_source_means.append(_mean(group_means))
        else:
            across_witnesses.append({"source_key": source, "kind": kind, "groups": []})
        other = "G2x" if source == "EXP-112" else "EXP-112"
        for omitted in source_groups[source]:
            combined_deletion: list[float] = []
            unsupported: list[dict[str, Any]] = []
            for seed in seeds:
                retained = [value for group, value in values[source][kind][seed].items() if group != omitted]
                if not retained:
                    unsupported.append({
                        "seed": seed,
                        "source_key": source,
                        "reason": "no retained spectrally nonempty group",
                    })
                other_values = list(values[other][kind][seed].values())
                if not other_values:
                    unsupported.append({
                        "seed": seed,
                        "source_key": other,
                        "reason": "zero supported source weight",
                    })
                if not retained or not other_values:
                    continue
                combined_deletion.append(
                    0.5 * _mean(retained) + 0.5 * _mean(other_values)
                )
            if not unsupported:
                value = _mean(combined_deletion)
                deletions.append(value)
                deletion_positions.append({
                    "deletion_index": len(deletion_positions),
                    "membership": {"source_key": source, "omitted_group": omitted},
                    "support_count": len(combined_deletion),
                    "denominator": len(seeds),
                    "value": value,
                    "reason_code": None,
                    "empty_population_witness": None,
                })
            else:
                witness = {
                    "source_key": source, "kind": kind,
                    "omitted_group": omitted,
                    "unsupported_positions": unsupported,
                }
                deletion_witnesses.append(witness)
                deletion_positions.append({
                    "deletion_index": len(deletion_positions),
                    "membership": {"source_key": source, "omitted_group": omitted},
                    "support_count": len(combined_deletion),
                    "denominator": len(seeds),
                    "value": None,
                    "reason_code": "UNDEFINED_REQUIRED_SENSITIVITY_REPLICATE",
                    "empty_population_witness": witness,
                })
    atoms[names[1]] = (
        (0.5 * across_source_means[0] + 0.5 * across_source_means[1],)
        if len(across_source_means) == 2 and not across_witnesses else None
    )
    atoms[names[4]] = tuple(deletions) if deletions else None
    brier_combined = _combined_seed_vector(brier, kind=kind, seeds=seeds)
    atoms[names[7]] = None if brier_combined is None else (_mean(brier_combined),)

    replicate_count = contract["bootstrap"]["replicates"]
    alpha = contract["multiplicity"]["alpha"]

    def sampled_distribution(name: str, sampler: Any) -> dict[str, Any]:
        estimates: list[float | None] = []
        memberships: list[dict[str, Any]] = []
        audits: list[dict[str, Any]] = []
        # The statistic identity intentionally excludes kind: the frozen G2c
        # membership draw is shared by raw/package and by the Brier ranking.
        statistic = f"paired_kinds_and_metrics::sensitivity::{name}"
        for replicate in range(replicate_count):
            cached = paired_membership_cache.get(name, [])
            if replicate < len(cached):
                membership, audit = cached[replicate]
                estimate, observed_membership = sampler(None, membership)
                if observed_membership != membership:
                    raise IncompleteCampaign("G2c paired sensitivity membership changed")
            else:
                key = derive_key("bootstrap", {
                    "stage_id": stage_id,
                    "statistic_id": statistic,
                    "replicate_index": replicate,
                })
                stream = RNGStream(key)
                estimate, membership = sampler(stream, None)
                audit = _bootstrap_rng_audit_v16(
                    stage_id=stage_id, statistic_id=statistic,
                    replicate_index=replicate, key=key, stream=stream,
                    rng_contract=contract["rng"],
                    attested_json_sha256=getattr(
                        spec, "_g2c_source_spec", spec
                    ).attestation.json_sha256,
                    shape=contract["bootstrap_audit_shape"],
                    implementation_version=contract["rng_version"],
                )
                paired_membership_cache.setdefault(name, []).append(
                    (copy.deepcopy(membership), copy.deepcopy(audit))
                )
            estimates.append(estimate)
            support_count = membership.get("support_count")
            denominator = membership.get("denominator")
            witness = membership.get("empty_population_witness")
            if (
                type(support_count) is not int
                or type(denominator) is not int
                or support_count < 0
                or denominator < support_count
            ):
                raise IncompleteCampaign("G2c sensitivity support record disagrees")
            memberships.append({
                "replicate_index": replicate,
                "paired_draw_id": f"g2c_{name.replace(' ', '_')}_{replicate:05d}",
                "statistic_id": statistic,
                "sampled_indices_and_multiplicities": membership,
                "support_count": support_count,
                "denominator": denominator,
                "value": estimate,
                "reason_code": (
                    None if estimate is not None else membership.get(
                        "reason_code", "UNDEFINED_REQUIRED_SENSITIVITY_REPLICATE"
                    )
                ),
                "empty_population_witness": None if estimate is not None else witness,
            })
            audits.append(copy.deepcopy(audit))
        defined = [value for value in estimates if value is not None]
        undefined_count = replicate_count - len(defined)
        interval: Any = (
            _percentile_summary(defined, alpha)["percentile_interval"]
            if not undefined_count
            else _undefined(
                "UNDEFINED_REQUIRED_SENSITIVITY_INTERVAL",
                [row for row in memberships if row["value"] is None],
                prescribed=replicate_count,
                defined=len(defined),
            )
        )
        return {
            "replicate_estimates": estimates,
            "replicate_membership": memberships,
            "percentile_interval": interval,
            "rng_audit": audits,
            "replicate_counts": {
                "prescribed": replicate_count,
                "defined": len(defined),
                "undefined": undefined_count,
            },
        }

    def config_only(stream: RNGStream | None, supplied: Any) -> tuple[float | None, Any]:
        selected: dict[str, list[int]] = copy.deepcopy(
            supplied.get("selected_group_indices_by_source", {}) if supplied else {}
        )
        for source in ("EXP-112", "G2x"):
            groups = source_groups[source]
            if not groups:
                raise IncompleteCampaign("G2c config sensitivity group census is empty")
            indices = selected.get(source)
            if indices is None:
                assert stream is not None
                indices = [stream.unbiased_index(len(groups)) for _ in groups]
            if len(indices) != len(groups) or any(
                type(index) is not int or not 0 <= index < len(groups)
                for index in indices
            ):
                raise IncompleteCampaign("G2c config sensitivity membership disagrees")
            selected[source] = indices
        return _config_only_estimate(
            values, kind=kind, seeds=seeds, source_groups=source_groups,
            selected=selected,
        )

    def hierarchical(stream: RNGStream | None, supplied: Any) -> tuple[float | None, Any]:
        if supplied:
            seed_indices = copy.deepcopy(supplied["selected_seed_indices"])
            selected = copy.deepcopy(supplied["selected_group_indices_by_source_and_seed_occurrence"])
        else:
            assert stream is not None
            seed_indices = [stream.unbiased_index(len(seeds)) for _ in seeds]
            selected = {
                source: [
                    [stream.unbiased_index(len(source_groups[source]))
                     for _ in source_groups[source]]
                    for _ in seed_indices
                ]
                for source in ("EXP-112", "G2x")
            }
        combined_values: list[float] = []
        support_count = 0
        witnesses: list[dict[str, Any]] = []
        for occurrence, seed_index in enumerate(seed_indices):
            seed = seeds[seed_index]
            source_estimates: list[float] = []
            for source in ("EXP-112", "G2x"):
                groups = source_groups[source]
                indices = selected[source][occurrence]
                retained = [
                    values[source][kind][seed][groups[index]]
                    for index in indices
                    if groups[index] in values[source][kind][seed]
                ]
                support_count += len(retained)
                if not retained:
                    witnesses.append({
                        "source_key": source,
                        "seed": seed,
                        "seed_occurrence": occurrence,
                    })
                else:
                    source_estimates.append(_mean(retained))
            if len(source_estimates) == 2:
                combined_values.append(
                    0.5 * source_estimates[0] + 0.5 * source_estimates[1]
                )
        membership = {
            "selected_seed_indices": seed_indices,
            "selected_group_indices_by_source_and_seed_occurrence": selected,
            "support_count": support_count,
            "denominator": sum(
                len(indices) for rows in selected.values() for indices in rows
            ),
            "empty_population_witness": witnesses or None,
        }
        return (
            None if witnesses else _mean(combined_values),
            membership,
        )

    def pigeonhole(stream: RNGStream | None, supplied: Any) -> tuple[float | None, Any]:
        if supplied:
            seed_indices = copy.deepcopy(supplied["selected_seed_indices"])
            selected_groups = copy.deepcopy(supplied["selected_group_indices_by_source"])
        else:
            assert stream is not None
            seed_indices = [stream.unbiased_index(len(seeds)) for _ in seeds]
            selected_groups = {
                source: [
                    stream.unbiased_index(len(source_groups[source]))
                    for _ in source_groups[source]
                ]
                for source in ("EXP-112", "G2x")
            }
        combined_values: list[float] = []
        support_count = 0
        witnesses: list[dict[str, Any]] = []
        for occurrence, seed_index in enumerate(seed_indices):
            seed = seeds[seed_index]
            source_estimates: list[float] = []
            for source in ("EXP-112", "G2x"):
                groups = source_groups[source]
                retained = [
                    values[source][kind][seed][groups[index]]
                    for index in selected_groups[source]
                    if groups[index] in values[source][kind][seed]
                ]
                support_count += len(retained)
                if not retained:
                    witnesses.append({
                        "source_key": source,
                        "seed": seed,
                        "seed_occurrence": occurrence,
                    })
                else:
                    source_estimates.append(_mean(retained))
            if len(source_estimates) == 2:
                combined_values.append(
                    0.5 * source_estimates[0] + 0.5 * source_estimates[1]
                )
        membership = {
            "selected_seed_indices": seed_indices,
            "selected_group_indices_by_source": selected_groups,
            "support_count": support_count,
            "denominator": len(seed_indices) * sum(
                len(indices) for indices in selected_groups.values()
            ),
            "empty_population_witness": witnesses or None,
        }
        return None if witnesses else _mean(combined_values), membership

    sampled: dict[str, dict[str, Any]] = {}
    sampled[names[1]] = sampled_distribution(names[1], config_only)
    sampled[names[2]] = sampled_distribution(names[2], hierarchical)
    sampled[names[6]] = sampled_distribution(names[6], pigeonhole)
    persisted: dict[str, Any] = {}
    reversal = False
    non_evaluable = False
    for name in names:
        atom = atoms[name]
        if atom is None:
            prescribed = (
                replicate_count if name in {names[1], names[2], names[6], names[7]}
                else sum(len(source_groups[source]) for source in source_groups)
                if name == names[4]
                else 1
            )
            record = _undefined(
                (
                    "UNDEFINED_REQUIRED_ACROSS_SEED_GROUP_MEAN"
                    if name == names[1]
                    else "UNDEFINED_REQUIRED_SENSITIVITY_REPLICATE"
                ),
                (
                    across_witnesses if name == names[1]
                    else deletion_witnesses if name == names[4]
                    else {"kind": kind, "sensitivity": name}
                ),
                prescribed=prescribed,
            )
            if name in sampled:
                record.update(sampled[name])
                record["value"] = None
                record["reason_code"] = (
                    "UNDEFINED_REQUIRED_ACROSS_SEED_GROUP_MEAN"
                    if name == names[1]
                    else "UNDEFINED_REQUIRED_SENSITIVITY_INTERVAL"
                )
                record["empty_population_witness"] = [
                    row
                    for row in record["replicate_membership"]
                    if row["value"] is None
                ]
            persisted[name] = record
            non_evaluable = True
        else:
            vector = [float(value) for value in atom]
            record: dict[str, Any] = {
                "value": _mean(vector),
                "values": vector,
                "reason_code": None,
                "empty_population_witness": None,
                "replicate_counts": {"prescribed": len(vector), "defined": len(vector), "undefined": 0},
            }
            if name == names[0]:
                record.update({
                    "replicate_estimates": primary_bootstrap["replicate_estimates"],
                    "replicate_membership": primary_bootstrap["replicate_membership"],
                    "percentile_interval": primary_bootstrap["percentile_interval"],
                    "rng_audit": primary_bootstrap["rng_audit"],
                    "replicate_counts": {
                        "prescribed": replicate_count, "defined": replicate_count, "undefined": 0,
                    },
                })
            elif name == names[3]:
                record["position_records"] = leave_one_seed_positions
            elif name in sampled:
                record.update(sampled[name])
                if sampled[name]["replicate_counts"]["undefined"]:
                    non_evaluable = True
            elif name == names[4]:
                undefined = len(deletion_witnesses)
                record.update({
                    "value": None if undefined else record["value"],
                    "values": [row["value"] for row in deletion_positions],
                    "position_records": deletion_positions,
                    "reason_code": (
                        "UNDEFINED_REQUIRED_SENSITIVITY_REPLICATE"
                        if undefined else None
                    ),
                    "empty_population_witness": deletion_witnesses or None,
                    "replicate_counts": {
                        "prescribed": len(deletion_positions),
                        "defined": len(deletion_positions) - undefined,
                        "undefined": undefined,
                    },
                })
                if undefined:
                    non_evaluable = True
            elif name == names[7]:
                record.update({
                    "replicate_estimates": brier_bootstrap["replicate_estimates"],
                    "replicate_membership": brier_bootstrap["replicate_membership"],
                    "percentile_interval": brier_bootstrap["percentile_interval"],
                    "bca_equal_tail_interval": brier_bootstrap["bca_equal_tail_interval"],
                    "bca_simultaneous_lower": brier_bootstrap["bca_simultaneous_lower"],
                    "bca_simultaneous_upper": brier_bootstrap["bca_simultaneous_upper"],
                    "rng_audit": brier_bootstrap["rng_audit"],
                    "complete_ranking": copy.deepcopy(dict(brier_ranking)),
                    "replicate_counts": {
                        "prescribed": replicate_count, "defined": replicate_count, "undefined": 0,
                    },
                })
            persisted[name] = record
            # Only named point/deletion atoms drive this strict comparison.
            # Bootstrap replicate signs are interval evidence, not sensitivity estimates.
            reversal = reversal or any(primary * value < 0 for value in vector)
    return persisted, reversal, non_evaluable


def _hierarchy_ledger(
    records: Sequence[Mapping[str, Any]],
    controls: Sequence[Mapping[str, Any]],
    values: Mapping[str, Mapping[str, Mapping[int, Mapping[str, float]]]],
    support: Mapping[str, Mapping[str, Mapping[int, Sequence[str]]]],
    structural_support: Mapping[str, Mapping[str, Mapping[int, Sequence[str]]]],
    intermediate_levels_by_metric: Mapping[str, Sequence[Mapping[str, Any]]],
    *, seeds: Sequence[int], coefficient_threshold: float,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    cells: list[dict[str, Any]] = []
    spectral: list[dict[str, Any]] = []
    for record, control in zip(records, controls, strict=True):
        coefficients = control.get("spectral_coefficients", {}).get("values", [])
        active = sum(
            type(value) in (int, float) and abs(float(value)) > coefficient_threshold
            for value in coefficients
        )
        spectral.append({
            "unit_id": record.get("unit_id"),
            "kind_cell_id": record.get("kind_cell_id"),
            "invocation_id": record.get("invocation_id"),
            "source_key": record.get("source_key"),
            "source": record.get("source"),
            "experiment": record.get("experiment"),
            "seed": record.get("seed"),
            "group": record.get("fixed_census_config_or_experiment_key"),
            "context": record.get("context"),
            "recorded_step": record.get("step"),
            "eligibility": record.get("eligibility"),
            "exclusion_reason_code": record.get("exclusion_reason_code"),
            "active_coefficient_count": active,
            "nondegenerate": control.get("nondegenerate"),
            "attempt_record_sha256": record.get("attempt_record_sha256"),
            "structural_manifest_sha256": record.get(
                "structural_manifest_sha256"
            ),
            "applicable_control_record_links": copy.deepcopy(
                record.get("applicable_control_record_links")
            ),
        })
    for source in ("EXP-112", "G2x"):
        for kind in ("raw", "pkg"):
            for seed in seeds:
                selected = [
                    row for row in spectral
                    if row["source_key"] == source and row["seed"] == seed
                    and kind_cell_id(str(row["unit_id"]), kind) == row["kind_cell_id"]
                ]
                scheduled_groups = list(support[source][kind][seed])
                structural_groups = list(structural_support[source][kind][seed])
                group_means = values[source][kind][seed]
                planned_exclusions = sorted(set(structural_groups) - set(scheduled_groups))
                cells.append({
                    "source_key": source, "kind": kind, "seed": seed,
                    "structural_group_ids": structural_groups,
                    "scheduled_group_ids": scheduled_groups,
                    "planned_exclusion_group_ids": planned_exclusions,
                    "spectrally_nonempty_group_ids": sorted(group_means),
                    "spectrally_empty_group_ids": sorted(set(scheduled_groups) - set(group_means)),
                    "total_context_count": len(selected),
                    "planned_exclusion_context_count": sum(
                        row["eligibility"] is False for row in selected
                    ),
                    "eligible_context_count": sum(row["eligibility"] is True for row in selected),
                    "nondegenerate_context_count": sum(row["eligibility"] is True and row["nondegenerate"] is True for row in selected),
                    "degenerate_context_count": sum(row["eligibility"] is True and row["nondegenerate"] is False for row in selected),
                    "nonempty_group_count": len(group_means),
                    "empty_group_count": len(scheduled_groups) - len(group_means),
                    "denominator": len(group_means),
                    "group_means": copy.deepcopy(group_means),
                    "source_estimate": _mean(list(group_means.values())) if group_means else None,
                    "source_weight": {"numerator": 1, "denominator": 2},
                })
    empty = [
        {
            "source_key": row["source_key"], "kind": row["kind"], "seed": row["seed"],
            "empty_group_identities": row["spectrally_empty_group_ids"],
        }
        for row in cells if row["denominator"] == 0
    ]
    combined_seed_estimates = []
    for kind in ("raw", "pkg"):
        for seed in seeds:
            source_rows = [
                row for row in cells
                if row["kind"] == kind and row["seed"] == seed
            ]
            by_source = {row["source_key"]: row for row in source_rows}
            defined = all(
                by_source[source]["source_estimate"] is not None
                for source in ("EXP-112", "G2x")
            )
            combined_seed_estimates.append({
                "kind": kind,
                "seed": seed,
                "source_estimates": {
                    source: by_source[source]["source_estimate"]
                    for source in ("EXP-112", "G2x")
                },
                "source_weights": {
                    source: {"numerator": 1, "denominator": 2}
                    for source in ("EXP-112", "G2x")
                },
                "combined_estimate": (
                    0.5 * float(by_source["EXP-112"]["source_estimate"])
                    + 0.5 * float(by_source["G2x"]["source_estimate"])
                    if defined else None
                ),
                "undefined_reason": (
                    None if defined else "EMPTY_REQUIRED_SPECTRAL_POPULATION"
                ),
            })
    return {
        "cells": cells,
        "combined_seed_estimates": combined_seed_estimates,
        "intermediate_context_invocation_group_means": [
            copy.deepcopy(dict(row))
            for row in intermediate_levels_by_metric["dtv"]
        ],
        "intermediate_means_by_metric": {
            name: [copy.deepcopy(dict(row)) for row in rows]
            for name, rows in intermediate_levels_by_metric.items()
        },
    }, spectral, empty


def _statistic_census_binding(
    hierarchy: Mapping[str, Any], *, kind: str,
) -> tuple[dict[str, int], list[str]]:
    indexed = [
        (index, row)
        for index, row in enumerate(hierarchy["cells"])
        if row["kind"] == kind
    ]
    summary = {
        "source_seed_cells": len(indexed),
        "total_contexts": sum(row["total_context_count"] for _, row in indexed),
        "planned_exclusion_contexts": sum(
            row["planned_exclusion_context_count"] for _, row in indexed
        ),
        "eligible_contexts": sum(row["eligible_context_count"] for _, row in indexed),
        "nondegenerate_contexts": sum(
            row["nondegenerate_context_count"] for _, row in indexed
        ),
        "degenerate_contexts": sum(row["degenerate_context_count"] for _, row in indexed),
        "spectrally_nonempty_groups": sum(row["nonempty_group_count"] for _, row in indexed),
        "spectrally_empty_groups": sum(row["empty_group_count"] for _, row in indexed),
    }
    references = [
        f"/persistence_contract/complete_census_and_hierarchy/cells/{index}"
        for index, _ in indexed
    ]
    return summary, references


def _attach_census_binding(
    record: dict[str, Any], *, summary: Mapping[str, int], references: Sequence[str],
    intermediate_references: Sequence[str] = (),
) -> None:
    record["count_summary"] = copy.deepcopy(dict(summary))
    record["detailed_census_references"] = list(references)
    record["intermediate_mean_references"] = list(intermediate_references)


def _intermediate_references(
    hierarchy: Mapping[str, Any], *, metric: str, kind: str,
) -> list[str]:
    rows = hierarchy["intermediate_means_by_metric"][metric]
    encoded = metric.replace("~", "~0").replace("/", "~1")
    return [
        f"/persistence_contract/complete_census_and_hierarchy/"
        f"intermediate_means_by_metric/{encoded}/{index}"
        for index, row in enumerate(rows) if row["kind"] == kind
    ]


def evaluate_g2c_records(
    spec: FrozenSpec,
    records: Sequence[Mapping[str, Any]],
    controls: Sequence[Mapping[str, Any]],
    *,
    rotation_evidence: Mapping[str, Mapping[str, Any]],
    control_sources: Sequence[Mapping[str, Any]] | None = None,
    control_input_projections: Mapping[str, Mapping[str, Any]] | None = None,
    implementation_manifest_path: Path | None = None,
    rotation_validator=None,
) -> dict[str, Any]:
    """Compute G2c statistics after completeness and control preemption."""
    rotation_validate = (validate_g2c_v22_rotation_evidence
                         if rotation_validator is None else rotation_validator)
    contract = _contract(spec, implementation_manifest_path)
    if control_sources is None:
        raise IncompleteCampaign(
            "G2c downstream admission requires bound rotation-control inputs"
        )
    if any(not all(row.get("pass_boolean_for_each_control", {}).values()) for row in controls):
        raise IncompleteCampaign("G2c control failure preempts statistics")
    if set(rotation_evidence) != {row.get("kind_cell_id") for row in controls}:
        raise IncompleteCampaign("G2c rotation evidence census disagrees")
    controls_by_kind = {row["kind_cell_id"]: row for row in controls}
    sources_by_kind = {row.get("kind_cell_id"): row for row in control_sources}
    records_by_kind = {row.get("kind_cell_id"): row for row in records}
    if (
        len(controls_by_kind) != len(controls)
        or len(sources_by_kind) != len(control_sources)
        or set(sources_by_kind) != set(controls_by_kind)
        or (
            control_input_projections is not None
            and (
                type(control_input_projections) is not dict
                or set(control_input_projections) != set(controls_by_kind)
            )
        )
        or len(records_by_kind) != len(records)
        or set(records_by_kind) != set(controls_by_kind)
    ):
        raise IncompleteCampaign("G2c downstream control-input census disagrees")
    certificate_components: list[float] = []
    certificate_dtv: list[float] = []
    rejected: set[tuple[str, int, int]] = set()
    for kind_identity, detail in rotation_evidence.items():
        control = controls_by_kind[kind_identity]
        universal = records_by_kind[kind_identity]
        validate_g2c_control_input_binding(
            universal, sources_by_kind[kind_identity],
            sealed_control_input_projection=(
                None if control_input_projections is None
                else control_input_projections[kind_identity]
            ),
        )
        try:
            reconstructed = rotation_validate(
                spec,
                sources_by_kind[kind_identity],
                control,
                detail,
                implementation_manifest_path=implementation_manifest_path,
            )
        except (ControlFailureEvidence, SpecMismatch) as error:
            raise IncompleteCampaign(
                f"G2c downstream rotation reconstruction failed: {error}"
            ) from error
        retained_residuals = universal.get("rotation_residuals")
        expected_residuals = reconstructed["rotation_residuals"]
        if (
            type(retained_residuals) is not dict
            or len(retained_residuals) != len(expected_residuals)
            or set(retained_residuals) != set(expected_residuals)
            or any(
                type(retained_residuals[name]) is not float
                or retained_residuals[name].hex() != expected.hex()
                for name, expected in expected_residuals.items()
            )
        ):
            raise IncompleteCampaign(
                "G2c downstream universal rotation residuals differ from reconstruction"
            )
        retained_pass = universal.get("pass_boolean_for_each_residual", {}).get(
            "rotation_residuals"
        )
        if type(retained_pass) is not bool or retained_pass is not reconstructed[
            "rotation_pass"
        ]:
            raise IncompleteCampaign(
                "G2c downstream universal rotation Boolean differs from reconstruction"
            )
        for replicate in detail.get("replicates", []):
            certificate_components.append(replicate["certificate_component"])
            certificate_dtv.append(replicate["certificate_dtv"])
            for attempt in range(replicate["rejected_attempt_count"]):
                rejected.add((control["unit_id"], replicate["replicate_index"], attempt))
    if len(certificate_components) != 16 * len(controls) or any(
        type(value) is not float or not math.isfinite(value)
        for value in (*certificate_components, *certificate_dtv)
    ):
        raise IncompleteCampaign("G2c rotation certificate census is incomplete")
    rotation_certificate_scale = {
        "certificate_component_max": max(certificate_components),
        "certificate_dtv_max": max(certificate_dtv),
        "rejected_attempt_total": len(rejected),
    }
    seeds = tuple(contract["campaign"]["seeds"])
    dtv, witnesses, support, structural_support, hierarchy_levels = _source_seed_values(
        records, controls, metric="dtv", seeds=seeds
    )
    brier, brier_witnesses, brier_support, brier_structural, brier_levels = _source_seed_values(
        records, controls, metric="brier", seeds=seeds
    )
    brier_laws = {
        law: _source_seed_values(
            records, controls, metric=f"brier_law:{law}", seeds=seeds
        ) for law in contract["law_labels"]
    }
    if any(value[2] != support or value[3] != structural_support for value in brier_laws.values()):
        raise IncompleteCampaign("G2c Brier law ranking spectral population differs")
    if support != brier_support or structural_support != brier_structural:
        raise IncompleteCampaign("G2c dTV/Brier scheduled spectral populations differ")
    if any(
        support[source]["raw"][seed] != support[source]["pkg"][seed]
        for source in ("EXP-112", "G2x") for seed in seeds
    ):
        raise IncompleteCampaign("G2c paired-kind scheduled spectral identities differ")
    vacuous = bool(witnesses)
    hierarchy_ledger, spectral_ledger, empty_cells = _hierarchy_ledger(
        records,
        controls,
        dtv,
        support,
        structural_support,
        {
            "dtv": hierarchy_levels,
            "brier": brier_levels,
            **{
                f"brier_law:{law}": brier_laws[law][4]
                for law in contract["law_labels"]
            },
        },
        seeds=seeds,
        coefficient_threshold=contract["threshold_coefficient"],
    )
    inference = {
        "bootstrap": contract["bootstrap"],
        "bca": contract["bca"],
        "multiplicity": copy.deepcopy(contract["multiplicity"]),
        "conditional_sign_randomization": {"seed_blocks": len(seeds)},
    }
    inference["multiplicity"]["endpoint_ledgers"]["g2a"] = 4
    statistics_by_kind: dict[str, Any] = {}
    raw_p: dict[str, float] = {}
    sensitivity_reversal = False
    spectral_non_evaluability = False
    if not vacuous:
        derive_key = key_deriver(
            getattr(spec, "_g2c_source_spec", spec),
            implementation_manifest_path=implementation_manifest_path,
        )
        paired_vectors: dict[str, Sequence[float]] = {}
        for paired_kind in ("raw", "pkg"):
            paired_dtv = _combined_seed_vector(dtv, kind=paired_kind, seeds=seeds)
            paired_brier = _combined_seed_vector(brier, kind=paired_kind, seeds=seeds)
            if paired_dtv is None or paired_brier is None:
                raise IncompleteCampaign("G2c primary paired vector is not evaluable")
            paired_vectors[f"dtv:{paired_kind}"] = paired_dtv
            paired_vectors[f"brier:{paired_kind}"] = paired_brier
            for law in contract["law_labels"]:
                law_vector = _combined_seed_vector(
                    brier_laws[law][0], kind=paired_kind, seeds=seeds
                )
                if law_vector is None:
                    raise IncompleteCampaign("G2c Brier ranking law is not evaluable")
                paired_vectors[f"brier:{paired_kind}:{law}"] = law_vector
        paired_bootstraps = _paired_bootstrap_results(
            spec, paired_vectors, inference=inference,
            contract=contract, derive_key=derive_key,
        )
        sensitivity_memberships: dict[
            str, list[tuple[Any, Mapping[str, Any]]]
        ] = {}
        for kind in ("raw", "pkg"):
            count_summary, census_references = _statistic_census_binding(
                hierarchy_ledger, kind=kind
            )
            dtv_intermediate_references = _intermediate_references(
                hierarchy_ledger, metric="dtv", kind=kind
            )
            brier_intermediate_references = _intermediate_references(
                hierarchy_ledger, metric="brier", kind=kind
            )
            vector = _combined_seed_vector(dtv, kind=kind, seeds=seeds)
            assert vector is not None
            bootstrap = paired_bootstraps[f"dtv:{kind}"]
            brier_vector = _combined_seed_vector(brier, kind=kind, seeds=seeds)
            assert brier_vector is not None
            brier_bootstrap = paired_bootstraps[f"brier:{kind}"]
            law_statistics: dict[str, Any] = {}
            for law in contract["law_labels"]:
                law_vector = _combined_seed_vector(
                    brier_laws[law][0], kind=kind, seeds=seeds
                )
                if law_vector is None:
                    raise IncompleteCampaign("G2c Brier ranking law is not evaluable")
                law_bootstrap = paired_bootstraps[f"brier:{kind}:{law}"]
                law_statistics[law] = {
                    "seed_values": list(law_vector),
                    "point_estimate": _mean(law_vector),
                    "bootstrap": law_bootstrap,
                }
                _attach_census_binding(
                    law_statistics[law], summary=count_summary,
                    references=census_references,
                    intermediate_references=_intermediate_references(
                        hierarchy_ledger, metric=f"brier_law:{law}", kind=kind
                    ),
                )
            brier_ranking = {
                "laws": law_statistics,
                "ordered_best_to_worst": sorted(
                    contract["law_labels"],
                    key=lambda law: (law_statistics[law]["point_estimate"], law),
                ),
                "paired_membership_statistic_id": "paired_kinds_sources_metrics",
            }
            margin = contract["threshold_margin"]["numerator"] / contract["threshold_margin"]["denominator"]
            _, margin_p = _conditional_sign_p_exact([value - margin for value in vector])
            raw_p[kind] = margin_p
            sensitivities, reversal, non_evaluable = _sensitivities(
                dtv, brier, kind=kind, seeds=seeds, primary=_mean(vector),
                primary_bootstrap=bootstrap,
                brier_bootstrap=brier_bootstrap,
                brier_ranking=brier_ranking,
                scheduled=support,
                contract=contract,
                derive_key=derive_key,
                spec=spec,
                paired_membership_cache=sensitivity_memberships,
            )
            sensitivity_reversal |= reversal
            spectral_non_evaluability |= non_evaluable
            for sensitivity in sensitivities.values():
                _attach_census_binding(
                    sensitivity, summary=count_summary,
                    references=census_references,
                    intermediate_references=[
                        *dtv_intermediate_references,
                        *brier_intermediate_references,
                    ],
                )
            statistics_by_kind[kind] = {
                "seed_values": list(vector),
                "point_estimate": _mean(vector),
                "bootstrap": bootstrap,
                "sensitivities": sensitivities,
                "hierarchy_census": {
                    source: {
                        str(seed): {
                            "nonempty_groups": len(dtv[source][kind][seed]),
                            "empty_groups": len(support[source][kind][seed])
                            - len(dtv[source][kind][seed]),
                            "scheduled_groups": len(support[source][kind][seed]),
                            "empty_group_identities": sorted(
                                set(support[source][kind][seed])
                                - set(dtv[source][kind][seed])
                            ),
                            "denominator": len(dtv[source][kind][seed]),
                            "source_estimate": _mean(list(dtv[source][kind][seed].values())),
                        }
                        for seed in seeds
                    }
                    for source in ("EXP-112", "G2x")
                },
                "margin_test": {"unadjusted_p": margin_p, "margin": margin},
                "count_summary": count_summary,
                "detailed_census_references": census_references,
                "intermediate_mean_references": dtv_intermediate_references,
            }
        adjusted = _holm(raw_p)
        for kind in statistics_by_kind:
            statistics_by_kind[kind]["margin_test"]["holm_adjusted_p"] = adjusted[kind]
        lower = {kind: statistics_by_kind[kind]["bootstrap"]["bca_simultaneous_lower"] for kind in statistics_by_kind}
        upper = {kind: statistics_by_kind[kind]["bootstrap"]["bca_simultaneous_upper"] for kind in statistics_by_kind}
    else:
        adjusted = {"raw": 1.0, "pkg": 1.0}
        lower = {"raw": None, "pkg": None}
        upper = {"raw": None, "pkg": None}
        for kind in ("raw", "pkg"):
            count_summary, census_references = _statistic_census_binding(
                hierarchy_ledger, kind=kind
            )
            dtv_intermediate_references = _intermediate_references(
                hierarchy_ledger, metric="dtv", kind=kind
            )
            brier_intermediate_references = _intermediate_references(
                hierarchy_ledger, metric="brier", kind=kind
            )
            vacuous_brier_ranking = {
                "laws": {
                    law: {
                        "seed_values": None,
                        "point_estimate": None,
                        "bootstrap": _undefined(
                            "EMPTY_REQUIRED_SPECTRAL_POPULATION",
                            [row for row in empty_cells if row["kind"] == kind],
                            prescribed=contract["bootstrap"]["replicates"],
                        ),
                        "count_summary": copy.deepcopy(count_summary),
                        "detailed_census_references": list(census_references),
                        "intermediate_mean_references": _intermediate_references(
                            hierarchy_ledger,
                            metric=f"brier_law:{law}",
                            kind=kind,
                        ),
                    }
                    for law in contract["law_labels"]
                },
                "ordered_best_to_worst": None,
                "paired_membership_statistic_id": (
                    "paired_kinds_sources_metrics"
                ),
            }
            vacuous_sensitivities = {
                name: _undefined(
                    "EMPTY_REQUIRED_SPECTRAL_POPULATION",
                    [row for row in empty_cells if row["kind"] == kind],
                )
                for name in contract["empty_groups"]["sensitivities"][
                    "names_in_frozen_order"
                ]
            }
            vacuous_sensitivities["Brier complete ranking"][
                "complete_ranking"
            ] = vacuous_brier_ranking
            for sensitivity in vacuous_sensitivities.values():
                _attach_census_binding(
                    sensitivity, summary=count_summary,
                    references=census_references,
                    intermediate_references=[
                        *dtv_intermediate_references,
                        *brier_intermediate_references,
                    ],
                )
            statistics_by_kind[kind] = {
                "seed_values": None,
                "point_estimate": None,
                "bootstrap": _undefined(
                    "EMPTY_REQUIRED_SPECTRAL_POPULATION",
                    [row for row in empty_cells if row["kind"] == kind],
                    prescribed=contract["bootstrap"]["replicates"],
                ),
                "sensitivities": vacuous_sensitivities,
                "hierarchy_census": {
                    row["source_key"]: {
                        str(cell["seed"]): cell
                        for cell in hierarchy_ledger["cells"]
                        if cell["kind"] == kind and cell["source_key"] == row["source_key"]
                    }
                    for row in ({"source_key": "EXP-112"}, {"source_key": "G2x"})
                },
                "margin_test": {"unadjusted_p": None, "margin": contract["threshold_margin"]["numerator"] / contract["threshold_margin"]["denominator"], "holm_adjusted_p": 1.0},
                "count_summary": count_summary,
                "detailed_census_references": census_references,
                "intermediate_mean_references": dtv_intermediate_references,
            }
    decision = G2CDecision(
        vacuous=vacuous,
        sensitivity_reversal=sensitivity_reversal,
        spectral_non_evaluability=spectral_non_evaluability,
        lower=lower,
        upper=upper,
        holm_adjusted_p=adjusted,
    )
    status = select_g2c_branch(spec, decision, implementation_manifest_path=implementation_manifest_path)
    branch_audit = {
        "global_preemptions": [],
        "whole_source_kind_empty": any(
            not any(cell["denominator"] for cell in hierarchy_ledger["cells"] if cell["source_key"] == source and cell["kind"] == kind)
            for source in ("EXP-112", "G2x") for kind in ("raw", "pkg")
        ),
        "fixed_seed_block_empty": bool(empty_cells),
        "vacuity_witnesses": copy.deepcopy(witnesses),
        "sign_reversal": sensitivity_reversal,
        "spectral_non_evaluability": spectral_non_evaluability,
        "unrounded_lower": copy.deepcopy(lower),
        "unrounded_upper": copy.deepcopy(upper),
        "holm_adjusted_p": copy.deepcopy(adjusted),
        "selected_branch": status,
    }
    return {
        "status": status,
        "statistics": statistics_by_kind,
        "vacuity": {
            "value": vacuous,
            "witnesses": witnesses,
            "undefined_estimates": [
                _undefined("EMPTY_REQUIRED_SPECTRAL_POPULATION", witness)
                for witness in witnesses
            ],
        },
        "sensitivity_causes": {
            "sign_reversal": sensitivity_reversal,
            "spectral_non_evaluability": spectral_non_evaluability,
        },
        "rotation_certificate_scale": rotation_certificate_scale,
        "rotation_evidence": copy.deepcopy(dict(rotation_evidence)),
        "brier_vacuity_witnesses": brier_witnesses,
        "persistence_contract": {
            "schema_version": contract["persistence"]["schema_version"],
            "requirements": copy.deepcopy(contract["persistence"]["persistence_requirements"]),
            "complete_census_and_hierarchy": hierarchy_ledger,
            "spectral_evidence": spectral_ledger,
            "required_empty_cells": empty_cells,
            "branch_audit": branch_audit,
            "requirement_bindings": [
                {
                    "requirement_index": 0,
                    "json_pointers": [
                        "/persistence_contract/complete_census_and_hierarchy/cells",
                        "/persistence_contract/spectral_evidence",
                    ],
                },
                {
                    "requirement_index": 1,
                    "json_pointers": [
                        "/persistence_contract/spectral_evidence",
                    ],
                },
                {
                    "requirement_index": 2,
                    "json_pointers": [
                        "/persistence_contract/complete_census_and_hierarchy/intermediate_context_invocation_group_means",
                        "/persistence_contract/complete_census_and_hierarchy/intermediate_means_by_metric",
                        "/persistence_contract/complete_census_and_hierarchy/cells",
                    ],
                },
                {
                    "requirement_index": 3,
                    "json_pointers": [
                        "/persistence_contract/complete_census_and_hierarchy/combined_seed_estimates",
                        "/persistence_contract/required_empty_cells",
                        "/statistics/raw",
                        "/statistics/pkg",
                    ],
                },
                {
                    "requirement_index": 4,
                    "json_pointers": [
                        "/statistics/raw/sensitivities",
                        "/statistics/pkg/sensitivities",
                    ],
                },
                {
                    "requirement_index": 5,
                    "json_pointers": [
                        "/statistics/raw/sensitivities",
                        "/statistics/pkg/sensitivities",
                    ],
                },
                {
                    "requirement_index": 6,
                    "json_pointers": [
                        "/persistence_contract/branch_audit",
                        "/statistics/raw/count_summary",
                        "/statistics/pkg/count_summary",
                    ],
                },
            ],
        },
        "claim_slots": [
            row for row in contract["claims"]
            if row.get("historical_claim_id") in {
                "g2c_cross_terms_load_bearing", "g2c_primary_scope_is_nondegenerate"
            }
        ],
    }
