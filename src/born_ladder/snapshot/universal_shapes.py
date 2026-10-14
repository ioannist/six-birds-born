"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence
from born_ladder.snapshot.completeness import invocation_id_for
from born_ladder.snapshot.errors import ControlFailureEvidence, IncompleteCampaign, SpecMismatch
from born_ladder.snapshot.frozen_spec import FrozenSpec, canonical_json_bytes, sha256_bytes
from born_ladder.snapshot.identities import kind_cell_id, stable_unit_id

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


_IMPLEMENTATION_POINTERS = {
    "brier_formula": "/observation_maps/formulas/brier",
    "clipped_linear_mass_tolerance": "/thresholds/items/12/value",
    "constant_span_tolerance": "/thresholds/items/16/value",
    "distribution_negative_probability_tolerance": "/thresholds/items/14/value",
    "distribution_absolute_tolerance": "/thresholds/items/8/value",
    "distribution_relative_tolerance": "/thresholds/items/9/value",
    "mass_residual_tolerance": "/thresholds/items/15/value",
    "inference_dimensions": "/inference",
    "g2a_exclusion_reason": "/completeness/g2a_raw_stdout_derivation/field_derivations/exclusion_reason_code/expression/arguments/1/value",
    "g2h_derivation_overlays": "/completeness/g2h_raw_stdout_derivation/overlays",
    "g2x_derivation": "/completeness/g2x_raw_stdout_derivation",
    "g2c_derivation": "/completeness/g2c_raw_stdout_derivation",
    "g2c_grid_labels": "/grid/labels",
    "g2c_v24_effective_schema": "/completeness/g2c_v24_effective_schema",
    "law_L_clipped_linear_formula": "/laws/definitions/L_clipped_linear",
    "law_L_full_formula": "/laws/definitions/L_full",
    "law_L_uniform_formula": "/laws/definitions/L_uniform",
    "law_q_diag_formula": "/laws/definitions/q_diag",
    "law_q_full_formula": "/laws/definitions/q_full",
    "law_q_lambda_formula": "/laws/definitions/q_lambda",
    "law_q_lambda_grid": "/laws/lambda_grid",
    "loss_formula": "/observation_maps/formulas/loss_k",
    "parseval_residual_tolerance": "/thresholds/items/6/value",
    "rng_dimensions": "/rng",
    "rotation_residual_tolerance": "/thresholds/items/7/value",
    "scoring_map_contract": "/observation_maps",
    "scoring_d_contrast_formula": "/identity/normative_expression_registry/d_k",
    "scoring_delta_contrast_formula": "/identity/normative_expression_registry/delta_1_k",
    "scoring_factor2_contrast_formula": "/identity/normative_expression_registry/s_2_k",
    "spectral_r_formula": "/identity/normative_expression_registry/r",
    "svd_census_consistency": "/completeness/universal_evidence_shapes/basis_svd_census_consistency",
    "svd_cutoff_formula": "/thresholds/items/17/value",
    "step_correspondence": "/identity/step_correspondence",
    "universal_evidence_shapes": "/completeness/universal_evidence_shapes",
}


def canonical_jsonl_bytes(records: Sequence[Mapping[str, Any]]) -> bytes:
    """Serialize records with canonical object-key bytes and one record per line."""
    return b"".join(canonical_json_bytes(dict(record)) for record in records)


def _closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IncompleteCampaign(f"universal evidence canonical JSON repeats key {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_token(token: str) -> Any:
    raise ControlFailureEvidence(
        f"universal evidence artifact contains nonfinite JSON token {token}"
    )


def load_canonical_record_artifact(
    path: Path, expected_sha256: str
) -> tuple[dict[str, Any], ...]:
    """Load a sealed canonical JSONL registry and bind its exact bytes to SHA-256."""
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise IncompleteCampaign(f"universal evidence artifact is unavailable: {error}") from error
    if not _HEX64.fullmatch(expected_sha256) or sha256_bytes(raw) != expected_sha256:
        raise IncompleteCampaign("universal evidence artifact SHA-256 disagrees")
    if not raw or not raw.endswith(b"\n") or b"\n\n" in raw:
        raise IncompleteCampaign("universal evidence artifact is not nonempty canonical JSONL")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(keepends=True), 1):
        try:
            decoded = json.loads(
                line[:-1].decode("utf-8", errors="strict"),
                object_pairs_hook=_closed_object,
                parse_constant=_reject_nonfinite_token,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise IncompleteCampaign(
                f"universal evidence artifact line {line_number} is not strict JSON"
            ) from error
        if not isinstance(decoded, dict):
            raise IncompleteCampaign(
                f"universal evidence artifact line {line_number} is not canonical JSON"
            )
        try:
            canonical = canonical_json_bytes(decoded)
        except (TypeError, ValueError) as error:
            raise ControlFailureEvidence(
                f"universal evidence artifact line {line_number} failed the finite-number control"
            ) from error
        if canonical != line:
            raise IncompleteCampaign(
                f"universal evidence artifact line {line_number} is not canonical JSON"
            )
        records.append(decoded)
    return tuple(records)


def _fail(path: str, detail: str) -> None:
    raise IncompleteCampaign(f"universal evidence {path}: {detail}")


def _canonical_step_id(step: int, contract: Mapping[str, Any]) -> str:
    if type(step) is not int or step < 0:
        _fail("step", "must be a nonnegative JSON integer")
    encoding = contract.get("string_encoding")
    if encoding != {
        "base": 10,
        "leading_zeros_allowed": False,
        "sign_allowed": False,
        "zero_encoding": "0",
    }:
        _fail("step", "frozen step correspondence encoding is unsupported")
    if contract.get("evidence_field") != {
        "name": "step", "type": "nonnegative JSON integer"
    } or contract.get("identity_field") != {
        "name": "step_id", "type": "nonempty UTF-8 string"
    }:
        _fail("step", "frozen step correspondence fields disagree")
    return str(step)


def _dimensions(
    record: Mapping[str, Any],
    profile: Mapping[str, Any],
    inference: Mapping[str, Any],
    rng: Mapping[str, Any],
) -> dict[str, int]:
    states = record.get("ordered_state_labels")
    outcomes = record.get("ordered_union_outcome_labels")
    basis = record.get("basis_and_projector_inputs")
    rank = basis.get("effective_rank") if isinstance(basis, Mapping) else None
    n_cols_original = (
        basis.get("n_cols_original") if isinstance(basis, Mapping) else None
    )
    return {
        "m": len(states) if isinstance(states, list) else -1,
        "n_state": len(states) if isinstance(states, list) else -1,
        "n_outcome": len(outcomes) if isinstance(outcomes, list) else -1,
        "n_cols_original": (
            n_cols_original if type(n_cols_original) is int else -1
        ),
        "r": rank if type(rank) is int else -1,
        "d": rank - 1 if type(rank) is int else -1,
        "n_seed": inference["conditional_sign_randomization"]["seed_blocks"],
        "n_bootstrap": inference["bootstrap"]["replicates"],
        "n_null": rng["algorithms"]["h1"]["draws"],
        "n_dose_replicate": rng["algorithms"]["g2s_dose"]["replicates"],
        "n_dedicated_links(stage_profile)": len(profile["dedicated_links"]),
    }


def _dimension(value: str, dimensions: Mapping[str, int]) -> int:
    if value.isdecimal():
        return int(value)
    if value in dimensions:
        return dimensions[value]
    if value == "min(m,n_cols_original)":
        return min(dimensions["m"], dimensions["n_cols_original"])
    _fail("descriptor", f"unsupported dimension {value!r}")


def _check_scalar(value: Any, descriptor: Mapping[str, Any], path: str) -> None:
    leaf = descriptor["leaf_type"]
    if leaf == "finite binary64":
        if type(value) not in (int, float):
            _fail(path, "expected a finite binary64 number")
        if not math.isfinite(float(value)):
            _control_fail(path, "finite-number control failed")
    elif leaf == "JSON integer":
        if type(value) is not int:
            _fail(path, "expected a JSON integer")
    elif leaf == "JSON Boolean":
        if type(value) is not bool:
            _fail(path, "expected a JSON Boolean")
    elif leaf == "JSON null":
        if value is not None:
            _fail(path, "expected JSON null")
    elif leaf == "UTF-8 string":
        if not isinstance(value, str):
            _fail(path, "expected a UTF-8 string")
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise IncompleteCampaign(f"universal evidence {path}: invalid UTF-8") from error
    else:
        _fail(path, f"unsupported scalar type {leaf!r}")

    constraint = descriptor["constraint"]
    if constraint == "nonempty" and not value:
        _fail(path, "must be nonempty")
    elif constraint == ">=0" and value < 0:
        _fail(path, "must be nonnegative")
    elif constraint == ">=1" and value < 1:
        _fail(path, "must be positive")
    elif constraint == "exactly 64 lowercase hexadecimal characters":
        if not isinstance(value, str) or not _HEX64.fullmatch(value):
            _fail(path, "must be a SHA-256 digest")
    elif constraint == "exactly content_addressed_json" and value != "content_addressed_json":
        _fail(path, "has the wrong content-addressed encoding")
    elif constraint == "canonical relative path":
        candidate = PurePosixPath(value)
        if candidate.is_absolute() or not value or ".." in candidate.parts or str(candidate) != value:
            _fail(path, "must be a canonical relative path")
    elif constraint == "even-length lowercase hexadecimal":
        if not re.fullmatch(r"(?:[0-9a-f]{2})*", value):
            _fail(path, "must be even-length lowercase hexadecimal")
    elif constraint.startswith("one of "):
        choices = {part.strip() for part in constraint.removeprefix("one of ").split(",")}
        g2c_v22_certificate_comparison = (
            path.endswith(
                ".tolerance_for_each_residual.rotation_residuals.comparison"
            )
            and value == "all-sixteen-v22-certificate-comparisons"
        )
        if value not in choices and not g2c_v22_certificate_comparison:
            _fail(path, f"must be one of {sorted(choices)}")


def _validate_descriptor(
    value: Any,
    descriptor: Mapping[str, Any],
    *,
    path: str,
    dimensions: Mapping[str, int],
    content_root: Path | None,
) -> Any:
    kind = descriptor.get("kind")
    if kind == "scalar":
        _check_scalar(value, descriptor, path)
        return value
    if kind == "array":
        if not isinstance(value, list):
            _fail(path, "expected an array")
        expected = 1
        for symbol in descriptor["dimensions"]:
            expected *= _dimension(symbol, dimensions)
        if len(value) != expected:
            _fail(path, f"array length {len(value)} disagrees with frozen dimension {expected}")
        return [
            _validate_descriptor(
                item, descriptor["item"], path=f"{path}[{index}]",
                dimensions=dimensions, content_root=content_root,
            )
            for index, item in enumerate(value)
        ]
    if kind == "object":
        if not isinstance(value, Mapping) or set(value) != set(descriptor["keys"]):
            _fail(path, "object keys disagree with the closed shape")
        return {
            key: _validate_descriptor(
                value[key], descriptor["properties"][key], path=f"{path}.{key}",
                dimensions=dimensions, content_root=content_root,
            )
            for key in descriptor["keys"]
        }
    if kind in {"object_map", "dynamic_closed_object_map"}:
        if not isinstance(value, Mapping) or set(value) != set(descriptor["key_set"]):
            _fail(path, "map membership disagrees with the closed shape")
        return {
            key: _validate_descriptor(
                value[key], descriptor["value"], path=f"{path}.{key}",
                dimensions=dimensions, content_root=content_root,
            )
            for key in descriptor["key_set"]
        }
    if kind == "union":
        wrapper = isinstance(value, Mapping) and set(value) == {"encoding", "path", "sha256"}
        if wrapper:
            wrapper_descriptor = next(
                (item for item in descriptor["variants"] if item.get("kind") == "object"), None
            )
            inline_descriptor = next(
                (item for item in descriptor["variants"] if item.get("kind") != "object"), None
            )
            if wrapper_descriptor is None or inline_descriptor is None:
                _fail(path, "content-addressed wrapper is not an allowed union variant")
            _validate_descriptor(
                value, wrapper_descriptor, path=path, dimensions=dimensions,
                content_root=content_root,
            )
            if content_root is None:
                _fail(path, "content-addressed evidence root is unavailable")
            target = (content_root / value["path"]).resolve()
            try:
                target.relative_to(content_root.resolve())
                raw = target.read_bytes()
            except (ValueError, OSError) as error:
                raise IncompleteCampaign(f"universal evidence {path}: content unavailable") from error
            if sha256_bytes(raw) != value["sha256"]:
                _fail(path, "content SHA-256 disagrees")
            try:
                decoded = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise IncompleteCampaign(f"universal evidence {path}: content is not JSON") from error
            try:
                canonical_content = canonical_json_bytes(decoded)
            except (TypeError, ValueError) as error:
                raise ControlFailureEvidence(
                    f"universal evidence {path}: content failed the finite-number control"
                ) from error
            if canonical_content != raw:
                _fail(path, "content is not canonical JSON")
            return _validate_descriptor(
                decoded, inline_descriptor, path=path, dimensions=dimensions,
                content_root=content_root,
            )
        failures: list[IncompleteCampaign] = []
        for variant in descriptor["variants"]:
            try:
                return _validate_descriptor(
                    value, variant, path=path, dimensions=dimensions,
                    content_root=content_root,
                )
            except IncompleteCampaign as error:
                failures.append(error)
        _fail(path, "does not match any closed union variant")
    _fail(path, f"unsupported descriptor kind {kind!r}")


def _kind(record: Mapping[str, Any], shapes: Mapping[str, Any]) -> str:
    kinds = tuple(
        shapes["paired_kind_cell_empirical_rule"]["selected_scoring_view"]
    )
    matches = [
        kind for kind in kinds
        if record.get("kind_cell_id") == kind_cell_id(record.get("unit_id"), kind)
    ]
    if len(matches) != 1:
        _fail("kind_cell_id", "does not derive exactly one raw/pkg kind")
    return matches[0]


def _selected_numeric(value: Any, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise ControlFailureEvidence(f"universal evidence {name}: finite-number control failed")
    return float(value)


def _control_fail(path: str, detail: str) -> None:
    raise ControlFailureEvidence(f"universal evidence {path}: {detail}")


def _max_difference(left: Sequence[float], right: Sequence[float]) -> float:
    return max((abs(a - b) for a, b in zip(left, right)), default=0.0)


def _vector_close(
    actual: Sequence[Any], expected: Sequence[float], *, absolute: float, relative: float
) -> bool:
    return len(actual) == len(expected) and all(
        math.isclose(_selected_numeric(item, "scientific vector"), target,
                     rel_tol=relative, abs_tol=absolute)
        for item, target in zip(actual, expected)
    )


def _matrix_vector(matrix: Sequence[Sequence[Any]], vector: Sequence[float]) -> list[float]:
    return [
        math.fsum(_selected_numeric(value, "scientific matrix") * vector[column]
                  for column, value in enumerate(row))
        for row in matrix
    ]


def _transpose_vector(matrix: Sequence[Sequence[Any]], vector: Sequence[float]) -> list[float]:
    if not matrix:
        return []
    return [
        math.fsum(_selected_numeric(matrix[row][column], "emitted_basis") * vector[row]
                  for row in range(len(matrix)))
        for column in range(len(matrix[0]))
    ]


def _formula_contract(spec: FrozenSpec) -> dict[str, Any]:
    contract = {
        "laws": {
            name: spec.get(f"/laws/definitions/{name}", expected_type=dict)
            for name in ("L_full", "L_uniform", "L_clipped_linear", "q_full", "q_diag", "q_lambda")
        },
        "lambda_grid": spec.get("/laws/lambda_grid", expected_type=list),
        "loss": spec.get("/observation_maps/formulas/loss_k", expected_type=dict),
        "brier": spec.get("/observation_maps/formulas/brier", expected_type=dict),
        "d": spec.get("/identity/normative_expression_registry/d_k", expected_type=dict),
        "delta": spec.get("/identity/normative_expression_registry/delta_1_k", expected_type=dict),
        "factor2": spec.get("/identity/normative_expression_registry/s_2_k", expected_type=dict),
        "r": spec.get("/identity/normative_expression_registry/r", expected_type=dict),
        "absolute": spec.get("/thresholds/items/8/value"),
        "relative": spec.get("/thresholds/items/9/value"),
        "negative_probability": spec.get("/thresholds/items/14/value"),
        "mass": spec.get("/thresholds/items/15/value"),
        "clipped_mass": spec.get("/thresholds/items/12/value"),
        "constant_span": spec.get("/thresholds/items/16/value"),
        "svd_cutoff": spec.get("/thresholds/items/17/value", expected_type=dict),
        "svd_census": spec.get(
            "/completeness/universal_evidence_shapes/basis_svd_census_consistency",
            expected_type=dict,
        ),
        "rotation": spec.get("/thresholds/items/7/value"),
    }
    try:
        loss_half = contract["loss"]["arguments"][0]["value"]
        brier_power = contract["brier"]["arguments"][0]["arguments"][1]["value"]
        factor = contract["factor2"]["arguments"][1]["arguments"][0]["value"]
    except (KeyError, IndexError, TypeError) as error:
        raise SpecMismatch("frozen scoring formula tree is unsupported") from error
    if loss_half != 0.5 or brier_power != 2 or factor != 2:
        raise SpecMismatch("frozen scoring formula coefficients disagree")
    if contract["svd_census"].get("cutoff") != contract["svd_cutoff"]:
        raise SpecMismatch("frozen SVD census and cutoff formulas disagree")
    return {**contract, "loss_half": float(loss_half), "brier_power": int(brier_power),
            "factor": float(factor)}


def _validated_svd_census(
    basis_record: Mapping[str, Any], m: int, formulas: Mapping[str, Any]
) -> list[float]:
    """Apply the frozen original-column SVD cutoff to the complete census."""
    singular_values_all = [
        _selected_numeric(value, "basis_and_projector_inputs.singular_values_all")
        for value in basis_record["singular_values_all"]
    ]
    singular_values = [
        _selected_numeric(value, "basis_and_projector_inputs.singular_values")
        for value in basis_record["singular_values"]
    ]
    rank = basis_record["effective_rank"]
    n_cols_original = basis_record["n_cols_original"]
    if not singular_values_all or len(singular_values_all) != min(m, n_cols_original):
        _control_fail(
            "basis_and_projector_inputs.singular_values_all",
            "complete singular-value census length disagrees",
        )
    if any(
        left < right
        for left, right in zip(singular_values_all, singular_values_all[1:])
    ):
        _control_fail(
            "basis_and_projector_inputs.singular_values_all",
            "complete singular-value census is not in descending order",
        )
    variables = {
        "eps_binary64": math.ulp(1.0), "m": m,
        "n_cols_original": n_cols_original, "sigma_max": singular_values_all[0],
    }

    def evaluate(node: Mapping[str, Any]) -> float:
        kind = node.get("kind")
        if kind == "variable" and node.get("name") in variables:
            return float(variables[node["name"]])
        if kind == "call" and node.get("function") == "max":
            return max(evaluate(argument) for argument in node.get("arguments", []))
        if kind == "operator" and node.get("operator") == "multiply":
            return math.prod(
                evaluate(argument) for argument in node.get("arguments", [])
            )
        raise SpecMismatch("frozen SVD-cutoff formula tree is unsupported")

    expected_cutoff = evaluate(formulas["svd_cutoff"])
    if float(basis_record["svd_cutoff"]) != expected_cutoff:
        _control_fail(
            "basis_and_projector_inputs.svd_cutoff",
            "frozen SVD-cutoff formula disagrees",
        )
    expected_retained = [
        value for value in singular_values_all if value > expected_cutoff
    ]
    if (
        len(singular_values) != rank
        or rank != len(expected_retained)
        or singular_values != expected_retained
        or singular_values != singular_values_all[:rank]
    ):
        _control_fail(
            "basis_and_projector_inputs.singular_values",
            "effective-rank control failed",
        )
    return singular_values


def _recomputed_laws(
    record: Mapping[str, Any], formulas: Mapping[str, Any]
) -> tuple[dict[str, list[float]], dict[str, float], dict[str, float]]:
    p = [_selected_numeric(item, "unrounded_p_full") for item in record["unrounded_p_full"]]
    if any(item < formulas["negative_probability"] for item in p):
        _control_fail("unrounded_p_full", "negative-probability control failed")
    if abs(math.fsum(p) - 1.0) > formulas["mass"]:
        _control_fail("unrounded_p_full", "probability-mass control failed")
    nonnegative_p = [max(0.0, item) for item in p]
    basis_record = record["basis_and_projector_inputs"]
    basis = basis_record["emitted_basis"]
    projector = basis_record["projector"]
    n_state = len(p)
    rank = basis_record["effective_rank"]
    if len(basis) != n_state or any(len(row) != rank for row in basis):
        _control_fail("basis_and_projector_inputs.emitted_basis", "matrix dimensions disagree")
    if len(projector) != n_state or any(len(row) != n_state for row in projector):
        _control_fail("basis_and_projector_inputs.projector", "matrix dimensions disagree")
    expected_projector = [
        [math.fsum(float(basis[row][mode]) * float(basis[column][mode]) for mode in range(rank))
         for column in range(n_state)]
        for row in range(n_state)
    ]
    projector_delta = max(
        abs(float(projector[row][column]) - expected_projector[row][column])
        for row in range(n_state) for column in range(n_state)
    )
    if projector_delta > formulas["rotation"]:
        _control_fail("basis_and_projector_inputs.projector", "projector reconstruction control failed")
    gram_delta = max(
        abs(math.fsum(float(basis[row][left]) * float(basis[row][right])
                      for row in range(n_state)) - (1.0 if left == right else 0.0))
        for left in range(rank) for right in range(rank)
    )
    if gram_delta > formulas["rotation"]:
        _control_fail("basis_and_projector_inputs.emitted_basis", "orthonormality control failed")
    _validated_svd_census(basis_record, n_state, formulas)
    pivots = basis_record["orientation_pivot_indices"]
    expected_pivots = [
        min(
            index for index in range(n_state)
            if abs(float(basis[index][mode])) == max(abs(float(row[mode])) for row in basis)
        )
        for mode in range(rank)
    ]
    if pivots != expected_pivots or any(float(basis[pivots[mode]][mode]) < 0 for mode in range(rank)):
        _control_fail("basis_and_projector_inputs.orientation_pivot_indices", "basis orientation control failed")
    constant = [1.0 / math.sqrt(n_state)] * n_state
    constant_residual = _max_difference(_matrix_vector(projector, constant), constant)
    if constant_residual > formulas["constant_span"] or not math.isclose(
        float(basis_record["constant_span_residual"]), constant_residual,
        rel_tol=0.0, abs_tol=formulas["absolute"],
    ):
        _control_fail("basis_and_projector_inputs.constant_span_residual", "constant-span control failed")
    root_p = [math.sqrt(item) for item in nonnegative_p]
    coefficients = _transpose_vector(basis, root_p)
    mode_ids = record["spectral_coefficients"]["mode_ids"]
    if len(mode_ids) != len(record["spectral_coefficients"]["values"]):
        _fail(
            "spectral_coefficients",
            "parallel mode and value arrays have different lengths",
        )
    if len(mode_ids) != len(set(mode_ids)):
        _fail("spectral_coefficients.mode_ids", "mode IDs must be unique")
    recorded_coefficients = record["spectral_coefficients"]["values"]
    if not _vector_close(recorded_coefficients, coefficients,
                         absolute=formulas["absolute"], relative=formulas["relative"]):
        _control_fail("spectral_coefficients.values", "spectral-coefficient formula disagrees")
    r_projector = _matrix_vector(projector, root_p)
    r_basis = _matrix_vector(basis, coefficients)
    if _max_difference(r_projector, r_basis) > formulas["rotation"]:
        _control_fail("spectral_coefficients", "Parseval/projector reconstruction failed")
    clipped = [max(0.0, value) for value in _matrix_vector(projector, p)]
    q_full = [value * value for value in r_projector]
    q_diag = [
        math.fsum(coefficients[mode] ** 2 * float(basis[state][mode]) ** 2
                  for mode in range(rank))
        for state in range(n_state)
    ]
    numerators: dict[str, list[float]] = {
        "L_full": p,
        "L_uniform": [1.0] * n_state,
        "L_clipped_linear": clipped,
        "q_full": q_full,
        "q_diag": q_diag,
    }
    r_energy = math.fsum(q_full)
    leverage = [float(projector[index][index]) for index in range(n_state)]
    for item in formulas["lambda_grid"]:
        numerator, denominator = item["numerator"], item["denominator"]
        label = f"q_lambda_{numerator}" if denominator == 1 else f"q_lambda_{numerator}_{denominator}"
        ratio = numerator / denominator
        numerators[label] = [value + ratio * r_energy * h for value, h in zip(q_full, leverage)]
    masses = {name: math.fsum(values) for name, values in numerators.items()}
    if masses["L_clipped_linear"] <= formulas["clipped_mass"]:
        _control_fail("law_numerators.L_clipped_linear", "clipped-linear mass control failed")
    if any(not math.isfinite(mass) or mass <= 0.0 for mass in masses.values()):
        _control_fail("normalization_mass", "law normalization control failed")
    predictions = {
        name: [value / masses[name] for value in values]
        for name, values in numerators.items()
    }
    q_full_basis = [
        value * value / math.fsum(component * component for component in r_basis)
        for value in r_basis
    ]
    diagnostics = {
        "p_mass": math.fsum(p) - 1.0,
        "spectral_energy": math.fsum(value * value for value in coefficients) - r_energy,
        "q_full_component": _max_difference(predictions["q_full"], q_full_basis),
        "q_full_dtv": formulas["loss_half"] * math.fsum(
            abs(left - right) for left, right in zip(predictions["q_full"], q_full_basis)
        ),
        "projector_delta": projector_delta,
    }
    return predictions, masses, diagnostics


def _residual_contract(
    spec: FrozenSpec, *, stage_profile: str | None = None
) -> dict[str, dict[str, Any]]:
    absolute = spec.get("/thresholds/items/8/value")
    relative = spec.get("/thresholds/items/9/value")
    result = {
        "finite_residuals": {
            "absolute_or_null": None, "relative_or_null": None,
            "comparison": "count-equals-zero",
        },
        "mass_residuals": {
            "absolute_or_null": spec.get("/thresholds/items/15/value"),
            "relative_or_null": None, "comparison": "<=",
        },
        "parseval_residuals": {
            "absolute_or_null": spec.get("/thresholds/items/6/value"),
            "relative_or_null": None, "comparison": "<=",
        },
        "rotation_residuals": {
            "absolute_or_null": spec.get("/thresholds/items/7/value"),
            "relative_or_null": None, "comparison": "<=",
        },
        "identity_residuals": {
            "absolute_or_null": absolute, "relative_or_null": relative,
            "comparison": "<=",
        },
        "sequential_residuals": {
            "absolute_or_null": absolute, "relative_or_null": relative,
            "comparison": "<=",
        },
    }
    if stage_profile == "g2c":
        spec.get(_IMPLEMENTATION_POINTERS["g2c_v24_effective_schema"], expected_type=dict)
        result["rotation_residuals"] = {
            "absolute_or_null": None,
            "relative_or_null": None,
            "comparison": "all-sixteen-v22-certificate-comparisons",
        }
    return result


def _residual_pass(name: str, value: Mapping[str, Any], tolerance: Mapping[str, Any]) -> bool:
    if name == "finite_residuals":
        return value["checked_value_count"] > 0 and value["nonfinite_value_count"] == 0
    absolute_limit = tolerance["absolute_or_null"]
    relative_limit = tolerance["relative_or_null"]
    absolute_names = {
        "identity_residuals": {"componentwise_absolute", "mass", "dtv"},
        "sequential_residuals": set(value) - {"nonfinite_value_count"},
    }.get(name, set(value))
    relative_names = {"componentwise_relative"} if name == "identity_residuals" else set()
    if absolute_limit is not None and any(abs(float(value[key])) > absolute_limit for key in absolute_names):
        return False
    if relative_limit is not None and any(abs(float(value[key])) > relative_limit for key in relative_names):
        return False
    if name == "sequential_residuals" and value["nonfinite_value_count"] != 0:
        return False
    return True


def _validate_scoring(
    record: Mapping[str, Any], shapes: Mapping[str, Any], kind: str,
    formulas: Mapping[str, Any],
) -> dict[str, float]:
    labels = shapes["all_law_labels"]
    contrast_ids = shapes["contrast_identifiers"]
    losses = record["dtv_loss"]
    scores = record["brier_score"]
    contrasts = record["pairwise_contrast"]
    ties = record["tie_flag"]
    empirical = record[f"unrounded_y_{kind}"]
    matrix = record[f"M_{kind}_or_content_hash"]
    predictions = record["state_space_prediction"]
    mapped = record["mapped_outcome_prediction"]
    expected_predictions, expected_masses, diagnostics = _recomputed_laws(record, formulas)
    for empirical_name in ("unrounded_y_raw", "unrounded_y_pkg"):
        vector = [_selected_numeric(value, empirical_name) for value in record[empirical_name]]
        if any(value < formulas["negative_probability"] for value in vector) or abs(
            math.fsum(vector) - 1.0
        ) > formulas["mass"]:
            _control_fail(empirical_name, "empirical probability control failed")
    for column in range(len(record["ordered_state_labels"])):
        values = [_selected_numeric(row[column], f"M_{kind}") for row in matrix]
        if any(value < formulas["negative_probability"] for value in values) or abs(
            math.fsum(values) - 1.0
        ) > formulas["mass"]:
            _control_fail(f"M_{kind}", "observation-map probability control failed")
    for law in labels:
        expected_state = expected_predictions[law]
        if not _vector_close(
            record["law_numerators"][law],
            [value * expected_masses[law] for value in expected_state],
            absolute=formulas["absolute"], relative=formulas["relative"],
        ):
            _control_fail(f"law_numerators.{law}", "disagrees with the frozen law formula")
        if not math.isclose(float(record["normalization_mass"][law]), expected_masses[law],
                            rel_tol=formulas["relative"], abs_tol=formulas["absolute"]):
            _control_fail(f"normalization_mass.{law}", "disagrees with recomputed law mass")
        if not _vector_close(predictions[law], expected_state,
                             absolute=formulas["absolute"], relative=formulas["relative"]):
            _control_fail(f"state_space_prediction.{law}", "disagrees with frozen law normalization")
        if any(value < formulas["negative_probability"] for value in expected_state) or abs(
            math.fsum(expected_state) - 1.0
        ) > formulas["mass"]:
            _control_fail(f"state_space_prediction.{law}", "law probability control failed")
        expected_mapped = [
            sum(float(matrix[row][column]) * expected_state[column] for column in range(len(expected_state)))
            for row in range(len(empirical))
        ]
        if not _vector_close(mapped[law], expected_mapped,
                             absolute=formulas["absolute"], relative=formulas["relative"]):
            _control_fail(f"mapped_outcome_prediction.{law}", "disagrees with selected observation map")
        expected_dtv = formulas["loss_half"] * math.fsum(
            abs(float(y) - q) for y, q in zip(empirical, expected_mapped)
        )
        expected_brier = math.fsum(
            (float(y) - q) ** formulas["brier_power"] for y, q in zip(empirical, expected_mapped)
        )
        if not math.isclose(float(losses[law]), expected_dtv, rel_tol=0.0, abs_tol=formulas["absolute"]):
            _control_fail(f"dtv_loss.{law}", "disagrees with frozen loss formula")
        if not math.isclose(float(scores[law]), expected_brier, rel_tol=0.0, abs_tol=formulas["absolute"]):
            _control_fail(f"brier_score.{law}", "disagrees with frozen Brier formula")
    expected_contrasts: dict[str, float] = {}
    for contrast_id in contrast_ids["tie_flags"]:
        terms = contrast_id.removeprefix("D__").split("_minus_", 1)
        if len(terms) != 2 or any(term not in losses for term in terms):
            _fail("pairwise_contrast", "frozen dTV contrast identity is malformed")
        expected_contrasts[contrast_id] = losses[terms[0]] - losses[terms[1]]
    factor2_terms = contrast_ids["factor2"].removeprefix("S2__").split(
        "_minus_2x", 1
    )
    if len(factor2_terms) != 2 or any(term not in losses for term in factor2_terms):
        _fail("pairwise_contrast", "frozen factor-2 identity is malformed")
    expected_contrasts[contrast_ids["factor2"]] = (
        losses[factor2_terms[0]] - formulas["factor"] * losses[factor2_terms[1]]
    )
    descriptive_delta = next(
        (
            name for name in contrast_ids["descriptive"]
            if name.startswith("DELTA1__")
        ),
        None,
    )
    if descriptive_delta is None:
        _fail("pairwise_contrast", "frozen descriptive delta identity is absent")
    delta_terms = descriptive_delta.removeprefix("DELTA1__").split("_minus_", 1)
    if len(delta_terms) != 2 or any(term not in losses for term in delta_terms):
        _fail("pairwise_contrast", "frozen descriptive delta identity is malformed")
    expected_contrasts[descriptive_delta] = losses[delta_terms[0]] - losses[delta_terms[1]]
    for name, expected in expected_contrasts.items():
        if not math.isclose(float(contrasts[name]), expected, rel_tol=0.0,
                            abs_tol=formulas["absolute"]):
            _control_fail(f"pairwise_contrast.{name}", "disagrees with frozen loss contrast")
    return diagnostics


def _validate_recomputed_residuals(
    record: Mapping[str, Any], diagnostics: Mapping[str, float],
    shapes: Mapping[str, Any], formulas: Mapping[str, Any],
    *, validate_legacy_rotation: bool = True,
) -> None:
    labels = shapes["all_law_labels"]
    expected_mass = {
        "empirical_raw": math.fsum(float(value) for value in record["unrounded_y_raw"]) - 1.0,
        "empirical_pkg": math.fsum(float(value) for value in record["unrounded_y_pkg"]) - 1.0,
        **{
            law: math.fsum(float(value) for value in record["state_space_prediction"][law]) - 1.0
            for law in labels
        },
    }
    expected_parseval = {
        "p_full_norm_minus_one": diagnostics["p_mass"],
        "spectral_energy_minus_p_full_energy": diagnostics["spectral_energy"],
    }
    expected_rotation = {
        "q_full_max_component": diagnostics["q_full_component"],
        "q_full_dtv": diagnostics["q_full_dtv"],
        "q_diag_max_component_diagnostic": 0.0,
    }
    fields = [
        ("mass_residuals", expected_mass),
        ("parseval_residuals", expected_parseval),
    ]
    if validate_legacy_rotation:
        fields.append(("rotation_residuals", expected_rotation))
    for name, expected in fields:
        actual = record[name]
        for field, target in expected.items():
            if not math.isclose(float(actual[field]), target, rel_tol=0.0,
                                abs_tol=formulas["absolute"]):
                _control_fail(f"{name}.{field}", "disagrees with independently recomputed residual")


def _numeric_leaf_count(value: Any) -> int:
    if type(value) in (int, float):
        return 1
    if isinstance(value, Mapping):
        return sum(_numeric_leaf_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(_numeric_leaf_count(item) for item in value)
    return 0


def validate_stage_records(
    spec: FrozenSpec,
    records: Sequence[Mapping[str, Any]],
    *,
    stage_profile: str,
    expected_structural_manifest_sha256: str | Mapping[str, str],
    expected_attempt_record_sha256: str | Mapping[str, str],
    content_root: Path | None = None,
    implementation_manifest_path: Path | None = None,
    g2c_control_sources: Sequence[Mapping[str, Any]] | None = None,
    g2c_control_input_projections: Mapping[str, Mapping[str, Any]] | None = None,
    g2c_controls: Sequence[Mapping[str, Any]] | None = None,
    g2c_rotation_evidence: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Validate and resolve a complete closed stage-profile registry."""
    spec.audit_implementation_manifest(
        "universal_shapes", manifest_path=implementation_manifest_path,
        declared_pointers=_IMPLEMENTATION_POINTERS,
    )
    shapes = spec.get("/completeness/universal_evidence_shapes", expected_type=dict)
    inference = spec.get("/inference", expected_type=dict)
    rng = spec.get("/rng", expected_type=dict)
    if rng["algorithms"]["h1"]["draws"] != rng["algorithms"]["h2"]["draws"]:
        raise IncompleteCampaign("frozen H1/H2 universal draw dimensions disagree")
    step_correspondence = spec.get("/identity/step_correspondence", expected_type=dict)
    residual_contract = _residual_contract(spec, stage_profile=stage_profile)
    formula_contract = _formula_contract(spec)
    identity_spec = (
        getattr(spec, "_g2c_source_spec", spec)
        if stage_profile == "g2c" else spec
    )
    profiles = shapes["stage_profiles"]
    if stage_profile not in profiles:
        raise IncompleteCampaign(f"unknown universal evidence stage profile {stage_profile!r}")
    if not records:
        raise IncompleteCampaign("universal evidence registry is empty")
    profile = profiles[stage_profile]
    g2c_sources_by_kind: dict[str, Mapping[str, Any]] = {}
    g2c_controls_by_kind: dict[str, Mapping[str, Any]] = {}
    if stage_profile == "g2c":
        if (
            g2c_control_sources is None
            or g2c_control_input_projections is None
            or g2c_controls is None
            or g2c_rotation_evidence is None
        ):
            raise IncompleteCampaign(
                "G2c universal validation requires bound control inputs and ordered replicate evidence"
            )
        g2c_sources_by_kind = {
            row.get("kind_cell_id"): row for row in g2c_control_sources
            if isinstance(row, Mapping)
        }
        g2c_controls_by_kind = {
            row.get("kind_cell_id"): row for row in g2c_controls
            if isinstance(row, Mapping)
        }
        expected_g2c_ids = set(g2c_rotation_evidence)
        if (
            len(g2c_sources_by_kind) != len(g2c_control_sources)
            or len(g2c_controls_by_kind) != len(g2c_controls)
            or type(g2c_control_input_projections) is not dict
        ):
            raise IncompleteCampaign(
                "G2c universal control-input/evidence census disagrees"
            )
        if set(g2c_sources_by_kind) != expected_g2c_ids or set(
            g2c_controls_by_kind
        ) != expected_g2c_ids or set(g2c_control_input_projections) != expected_g2c_ids:
            raise IncompleteCampaign(
                "G2c universal control-input/evidence census disagrees"
            )
    expected_fields = [
        field
        for group in profile["group_field_order"].values()
        for field in group
    ]
    if len(expected_fields) != len(set(expected_fields)):
        raise IncompleteCampaign("frozen stage profile repeats universal fields")
    resolved: list[dict[str, Any]] = []
    for index, source_record in enumerate(records):
        if not isinstance(source_record, Mapping) or set(source_record) != set(expected_fields):
            _fail(str(index), "top-level fields disagree with the closed stage profile")
        record = dict(source_record)
        dimensions = _dimensions(record, profile, inference, rng)
        eligibility = record.get("eligibility")
        if type(eligibility) is not bool:
            _fail(f"{index}.eligibility", "must be Boolean")
        checked: dict[str, Any] = {}
        for field in expected_fields:
            applicability = profile["field_applicability"][field]
            value = record[field]
            if applicability["disposition"] == "STRUCTURALLY_INAPPLICABLE":
                if value is not None:
                    _fail(f"{index}.{field}", "must be null for this stage profile")
                checked[field] = None
                continue
            if not eligibility and field in {
                *profile["group_field_order"]["empirical"],
                *profile["group_field_order"]["law_evidence"],
            }:
                if value is not None:
                    _fail(f"{index}.{field}", "excluded record must carry null scientific evidence")
                checked[field] = None
                continue
            descriptor = shapes["universal_field_shapes"][applicability["shape"]]
            allows_null = descriptor.get("kind") == "union" and any(
                variant.get("kind") == "scalar"
                and variant.get("leaf_type") == "JSON null"
                for variant in descriptor.get("variants", ())
            )
            if value is None and field != "exclusion_reason_code" and not allows_null:
                _fail(f"{index}.{field}", "applicable field is null")
            checked[field] = _validate_descriptor(
                value, descriptor, path=f"{index}.{field}", dimensions=dimensions,
                content_root=content_root,
            )
        reason = checked["exclusion_reason_code"]
        if checked["experiment"] == "EXP-112":
            if type(checked["config_or_null"]) is not str or not checked["config_or_null"]:
                _fail(
                    f"{index}.config_or_null",
                    "EXP-112 record lacks its frozen config label",
                )
        if eligibility and reason is not None:
            _fail(f"{index}.exclusion_reason_code", "eligible record has an exclusion")
        if not eligibility:
            if stage_profile == "g2a":
                expected_reason = spec.get(
                    _IMPLEMENTATION_POINTERS["g2a_exclusion_reason"],
                    expected_type=str,
                )
            elif stage_profile in {"g2h_h1", "g2h_h2", "g2h_h3", "g2h_h4"}:
                overlays = spec.get(
                    _IMPLEMENTATION_POINTERS["g2h_derivation_overlays"],
                    expected_type=dict,
                )
                expected_reason = overlays[stage_profile]["exclusion_rule"][
                    "planned_exclusion"
                ]
            elif stage_profile == "g2c":
                overlay = spec.get(
                    _IMPLEMENTATION_POINTERS["g2c_derivation"], expected_type=dict
                )["overlays"]["g2c_v2"]
                if (
                    checked["experiment"] != "EXP-112"
                    or checked["config_or_null"] != "empty"
                ):
                    _fail(
                        f"{index}.eligibility",
                        "G2c planned exclusion is permitted only for EXP-112/config=empty",
                    )
                expected_reason = overlay["eligibility"]["exp112"]["exclusion_reason"]
            else:
                expected_reason = None
            if expected_reason is None or reason != expected_reason:
                _fail(f"{index}.exclusion_reason_code", "excluded record lacks its frozen stage reason")
        if stage_profile == "g2x":
            g2x = spec.get(_IMPLEMENTATION_POINTERS["g2x_derivation"], expected_type=dict)
            overlay = g2x["overlays"]["g2x_confirm"]
            if not overlay["no_planned_population_exclusion"] or not eligibility or reason is not None:
                _fail(f"{index}.eligibility", "disagrees with the frozen G2x inclusion rule")
            if checked["source"] != checked["experiment"]:
                _fail(f"{index}.source", "must equal the named experiment")
            if checked["config_or_null"] is not None:
                _fail(f"{index}.config_or_null", "must use NON_EXP112_CONFIG null")
            if checked["fixed_census_config_or_experiment_key"] != checked["experiment"]:
                _fail(
                    f"{index}.fixed_census_config_or_experiment_key",
                    "must equal the named experiment",
                )
            if checked["source_key"] != "G2x":
                _fail(f"{index}.source_key", "must equal the frozen G2x source key")
            if checked["frozen_inclusion_population"] != overlay["frozen_inclusion_population"]:
                _fail(
                    f"{index}.frozen_inclusion_population",
                    "disagrees with the frozen G2x population",
                )
            links = checked["applicable_control_record_links"]
            expected_link_path = overlay["named_experiment_artifact"]["path"]
            if len(links) != 1 or links[0]["path"] != expected_link_path:
                _fail(
                    f"{index}.applicable_control_record_links",
                    "disagrees with the frozen named-experiment link order",
                )
        if stage_profile == "g2c":
            g2c = spec.get(_IMPLEMENTATION_POINTERS["g2c_derivation"], expected_type=dict)
            overlay = g2c["overlays"]["g2c_v2"]
            labels = spec.get(_IMPLEMENTATION_POINTERS["g2c_grid_labels"], expected_type=list)
            experiment = checked["experiment"]
            config = checked["config_or_null"]
            exp112 = experiment == "EXP-112"
            named_experiments = set(overlay["internal_labels_by_experiment"])
            if not exp112 and experiment not in named_experiments:
                _fail(
                    f"{index}.experiment",
                    "lies outside the frozen G2c named-experiment census",
                )
            expected_eligible = exp112 and config in labels and config != "empty"
            expected_eligible = expected_eligible or (
                not exp112 and experiment in named_experiments and config is None
            )
            if eligibility is not expected_eligible:
                _fail(f"{index}.eligibility", "disagrees with the frozen G2c eligibility rule")
            if exp112:
                if checked["source"] != "EXP-112":
                    _fail(f"{index}.source", "must equal EXP-112 for the EXP-112 core")
                if config not in labels:
                    _fail(f"{index}.config_or_null", "lies outside the frozen G2c config census")
                expected_group, expected_source = config, "EXP-112"
            else:
                if checked["source"] != experiment:
                    _fail(f"{index}.source", "must equal the named experiment")
                if eligibility is not True or reason is not None:
                    _fail(
                        f"{index}.eligibility",
                        "named G2c records have no planned exclusion",
                    )
                if config is not None:
                    _fail(f"{index}.config_or_null", "must use NON_EXP112_CONFIG null")
                expected_group, expected_source = experiment, "G2x"
            if checked["fixed_census_config_or_experiment_key"] != expected_group:
                _fail(f"{index}.fixed_census_config_or_experiment_key", "disagrees with G2c source routing")
            if checked["source_key"] != expected_source:
                _fail(f"{index}.source_key", "disagrees with the frozen G2c source key")
            if checked["frozen_inclusion_population"] != overlay["population"]["identifier"]:
                _fail(f"{index}.frozen_inclusion_population", "disagrees with the frozen G2c population")
            links = checked["applicable_control_record_links"]
            if len(links) != 1 or links[0]["path"] != overlay["control_link"]["artifact"]:
                _fail(f"{index}.applicable_control_record_links", "disagrees with the frozen G2c control link")
        expected_structural_sha256 = (
            expected_structural_manifest_sha256.get(checked["invocation_id"])
            if isinstance(expected_structural_manifest_sha256, Mapping)
            else expected_structural_manifest_sha256
        )
        if (
            not isinstance(expected_structural_sha256, str)
            or not _HEX64.fullmatch(expected_structural_sha256)
            or checked["structural_manifest_sha256"] != expected_structural_sha256
        ):
            _fail(f"{index}.structural_manifest_sha256", "disagrees with expected binding")
        expected_attempt_sha256 = (
            expected_attempt_record_sha256.get(checked["invocation_id"])
            if isinstance(expected_attempt_record_sha256, Mapping)
            else expected_attempt_record_sha256
        )
        if not isinstance(expected_attempt_sha256, str) or not _HEX64.fullmatch(
            expected_attempt_sha256
        ):
            _fail(
                f"{index}.attempt_record_sha256",
                "has no sealed invocation-specific expected binding",
            )
        if checked["attempt_record_sha256"] != expected_attempt_sha256:
            _fail(f"{index}.attempt_record_sha256", "disagrees with expected binding")
        g2c_rotation_expected: Mapping[str, Any] | None = None
        if stage_profile == "g2c":
            # Defer the evidence consumer import until validation time; its
            # reconstruction delegates to the dedicated implementation while
            # independently binding the universal fields.
            from born_ladder.snapshot.evidence import validate_g2c_rotation_binding

            kind_identity = checked["kind_cell_id"]
            source = g2c_sources_by_kind.get(kind_identity)
            control = g2c_controls_by_kind.get(kind_identity)
            detail = g2c_rotation_evidence.get(kind_identity)
            if source is None or control is None or detail is None:
                _fail(
                    f"{index}.rotation_residuals",
                    "lacks bound G2c control inputs or ordered replicate evidence",
                )
            g2c_rotation_expected = validate_g2c_rotation_binding(
                spec,
                checked,
                source,
                control,
                detail,
                stage_profile="g2c",
                sealed_control_input_projection=g2c_control_input_projections[
                    kind_identity
                ],
                implementation_manifest_path=implementation_manifest_path,
            )
        if checked["tolerance_for_each_residual"] != residual_contract:
            _fail(f"{index}.tolerance_for_each_residual", "disagrees with frozen thresholds")
        for residual_name, tolerance in residual_contract.items():
            residual = checked[residual_name]
            if residual_name == "rotation_residuals" and stage_profile == "g2c":
                expected_pass = g2c_rotation_expected["rotation_pass"]
            else:
                expected_pass = False if residual is None else _residual_pass(
                    residual_name, residual, tolerance
                )
            if checked["pass_boolean_for_each_residual"][residual_name] is not expected_pass:
                _control_fail(
                    f"{index}.pass_boolean_for_each_residual.{residual_name}",
                    "disagrees with residual evidence and frozen tolerance",
                )
        expected_invocation = invocation_id_for(
            identity_spec, experiment=checked["experiment"], config_or_null=checked["config_or_null"],
            seed=checked["seed"], scale=checked["scale"],
        )
        if checked["invocation_id"] != expected_invocation:
            _fail(f"{index}.invocation_id", "disagrees with frozen identity")
        expected_hierarchy = [
            checked["seed_block_key"],
            checked["fixed_census_config_or_experiment_key"],
            checked["source_key"],
        ]
        if checked["bootstrap_hierarchy_keys"] != expected_hierarchy:
            _fail(
                f"{index}.bootstrap_hierarchy_keys",
                "disagrees with the ordered hierarchy fields",
            )
        expected_unit = checked["unit_id"] if not eligibility else stable_unit_id(
            identity_spec, source=checked["source"], experiment_id=checked["experiment"],
            config_id_or_null=checked["config_or_null"], seed=checked["seed"],
            scale=checked["scale"], runner_context_id=checked["context"],
            resolution=checked["resolution"],
            step_id=_canonical_step_id(checked["step"], step_correspondence),
            partition_id=checked["partition"], expected_state_labels=checked["ordered_state_labels"],
            implementation_manifest_path=implementation_manifest_path,
        )
        if checked["unit_id"] != expected_unit or checked["raw_pkg_pairing_key"] != expected_unit:
            _fail(f"{index}.unit_id", "unit or pairing identity disagrees")
        kind = _kind(checked, shapes)
        if eligibility:
            diagnostics = _validate_scoring(checked, shapes, kind, formula_contract)
            _validate_recomputed_residuals(
                checked, diagnostics, shapes, formula_contract,
                validate_legacy_rotation=stage_profile != "g2c",
            )
            finite_fields = [
                *profile["group_field_order"]["empirical"],
                *profile["group_field_order"]["law_evidence"],
            ]
            expected_checked_count = sum(
                _numeric_leaf_count(checked[field]) for field in finite_fields
            )
            if checked["finite_residuals"] != {
                "checked_value_count": expected_checked_count,
                "nonfinite_value_count": 0,
            }:
                _control_fail(
                    f"{index}.finite_residuals",
                    "disagrees with the independently traversed finite-number census",
                )
            counts = checked["integer_counts"]
            total = checked["total_count"]
            if sum(counts) != total or total <= 0:
                _fail(f"{index}.integer_counts", "counts disagree with positive total")
            empirical = checked[f"unrounded_y_{kind}"]
            if empirical != [count / total for count in counts]:
                _fail(f"{index}.integer_counts", "normalization disagrees with selected empirical vector")
        checked["_derived_kind"] = kind
        resolved.append(checked)

    kind_ids = [record["kind_cell_id"] for record in resolved]
    if len(kind_ids) != len(set(kind_ids)):
        raise IncompleteCampaign("universal evidence registry has duplicate kind_cell_id")
    by_unit: dict[str, list[dict[str, Any]]] = {}
    for record in resolved:
        by_unit.setdefault(record["unit_id"], []).append(record)
    pair_equal = shapes["paired_kind_cell_empirical_rule"]["byte_identical_across_pair"]
    explicit_equal = [name for name in pair_equal if name != "all theory inputs"]
    theory_fields = [
        "unrounded_p_full", "basis_and_projector_inputs", "spectral_coefficients",
        "law_numerators", "normalization_mass", "state_space_prediction",
    ]
    for unit_id, pair in by_unit.items():
        expected_kinds = set(
            shapes["paired_kind_cell_empirical_rule"]["selected_scoring_view"]
        )
        if len(pair) != len(expected_kinds) or {
            item["_derived_kind"] for item in pair
        } != expected_kinds:
            raise IncompleteCampaign(f"universal evidence unit {unit_id} lacks an exact raw/pkg pair")
        for field in [*explicit_equal, *theory_fields]:
            if pair[0][field] != pair[1][field]:
                raise IncompleteCampaign(f"universal evidence pair disagrees on {field}")
    return tuple(resolved)
