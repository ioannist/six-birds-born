"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import math
import ctypes
import contextvars
import struct
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence
import numpy as np
from born_ladder.snapshot.errors import ControlFailureEvidence, IncompleteCampaign, SpecMismatch
from born_ladder.snapshot.frozen_spec import FrozenSpec
from born_ladder.snapshot.linear_helpers import _two_pass_mgs
from born_ladder.snapshot.g2c_rotation_certificate import evaluate_rotation_certificate, evaluate_gradual_underflow_certificate
from born_ladder.snapshot.identities import kind_cell_id
from born_ladder.snapshot.rng import RNGStream, master_key
from born_ladder.snapshot.universal_shapes import _validate_descriptor

_POINTERS = {
    "g2c_controls_derivation": "/completeness/g2c_raw_stdout_derivation",
    "g2c_controls_rng": "/rng/framing/master_prefix",
    "g2c_controls_threshold_coefficient": "/thresholds/items/3/value",
    "g2c_controls_threshold_tie": "/thresholds/items/5/value",
    "g2c_controls_threshold_parseval": "/thresholds/items/6/value",
    "g2c_controls_threshold_admissibility": "/thresholds/items/32/value",
    "g2c_controls_threshold_negative_probability": "/thresholds/items/14/value",
    "g2c_controls_threshold_probability_mass": "/thresholds/items/15/value",
    "g2c_controls_threshold_constant_span": "/thresholds/items/16/value",
    "g2c_controls_threshold_mgs_orientation": "/thresholds/items/21/value",
    "g2c_controls_threshold_mgs_norm": "/thresholds/items/22/value",
    "g2c_controls_v24_route": "/completeness/g2c_v24_sealed_input_route",
    "g2c_controls_v24_schema": "/completeness/g2c_v24_effective_schema",
}


_GRADUAL_UNDERFLOW = contextvars.ContextVar("g2c_gradual_underflow", default=False)


import contextlib

def _require_gradual_underflow() -> None:
    """Exercise scalar, NumPy and BLAS subnormal paths used by the trace."""
    least = np.nextafter(np.float64(0.0), np.float64(1.0))
    if not (
        least == np.float64(2.0 ** -1074)
        and np.float64(least * np.float64(1.0)) == least
        and np.float64(least + least) == np.float64(2.0) * least
        and np.float64(least / np.float64(1.0)) == least
        and np.dot(np.asarray([least, 0.0]), np.asarray([1.0, 0.0])) == least
        and np.sum(np.asarray([least, least])) == np.float64(2.0) * least
    ):
        raise ControlFailureEvidence("G2c certificate gradual underflow is disabled")


@dataclass(frozen=True)
class G2CControlArtifacts:
    records: tuple[dict[str, Any], ...]

    rotation_evidence: dict[str, dict[str, Any]]

    complete: bool

    failures: tuple[dict[str, Any], ...]



def _contract(spec: FrozenSpec, manifest: Path | None = None) -> dict[str, Any]:
    spec.audit_implementation_manifest(
        "g2c_controls", manifest_path=manifest, declared_pointers=_POINTERS
    )
    derivation = spec.get(_POINTERS["g2c_controls_derivation"], expected_type=dict)
    controls = derivation.get("controls")
    if not isinstance(controls, dict):
        raise SpecMismatch("frozen G2c control registry is absent")
    expected = {
        "coefficient": spec.get(_POINTERS["g2c_controls_threshold_coefficient"]),
        "tie": spec.get(_POINTERS["g2c_controls_threshold_tie"]),
        "parseval": spec.get(_POINTERS["g2c_controls_threshold_parseval"]),
        "rotation_admissibility": spec.get(
            _POINTERS["g2c_controls_threshold_admissibility"]
        ),
        "negative_probability": spec.get(
            _POINTERS["g2c_controls_threshold_negative_probability"]
        ),
        "probability_mass": spec.get(
            _POINTERS["g2c_controls_threshold_probability_mass"]
        ),
        "constant_span": spec.get(_POINTERS["g2c_controls_threshold_constant_span"]),
        "mgs_orientation": spec.get(_POINTERS["g2c_controls_threshold_mgs_orientation"]),
        "mgs_norm": spec.get(_POINTERS["g2c_controls_threshold_mgs_norm"]),
    }
    if (
        expected != {
            "coefficient": 1e-9,
            "tie": 1e-12,
            "parseval": 1e-10,
            "rotation_admissibility": 1e-13,
            "negative_probability": -5e-13,
            "probability_mass": 1e-12,
            "constant_span": 1e-10,
            "mgs_orientation": 1e-15,
            "mgs_norm": 1e-12,
        }
        or controls["nondegeneracy"]["threshold"] != expected["coefficient"]
        or controls["ties"]["absolute_tolerance"] != expected["tie"]
        or controls["parseval"]["absolute_tolerance"] != expected["parseval"]
        or controls["rotation"]["admissibility"]["threshold_value"]
        != expected["rotation_admissibility"]
        or controls["rotation"]["q_full"]["maxima_enter_acceptance"] is not False
        or controls["rotation"]["replicate_indices"] != list(range(16))
    ):
        raise SpecMismatch("frozen G2c control thresholds or rotation census disagree")
    return {
        "controls": controls,
        "master_prefix": spec.get(_POINTERS["g2c_controls_rng"], expected_type=str),
        "source_json_sha256": spec.get(
            _POINTERS["g2c_controls_v24_route"], expected_type=dict
        )["source_identity"]["companion_sha256"],
        "effective_schema": spec.get(
            _POINTERS["g2c_controls_v24_schema"], expected_type=dict
        ),
        **expected,
    }


def _kind(record: Mapping[str, Any]) -> str:
    unit = record["unit_id"]
    matches = [kind for kind in ("raw", "pkg") if kind_cell_id(unit, kind) == record["kind_cell_id"]]
    if len(matches) != 1:
        raise IncompleteCampaign("G2c kind-cell identity does not select exactly one kind")
    return matches[0]


def _is_nondegenerate(coefficients: np.ndarray, threshold: float) -> bool:
    return int(np.sum(np.abs(coefficients) > threshold)) >= 2


def _distribution(
    basis: np.ndarray, root_p: np.ndarray, *, diagonal: bool
) -> np.ndarray:
    coefficients = basis.T @ root_p
    if diagonal:
        numerator = (basis * basis) @ (coefficients * coefficients)
    else:
        projected = basis @ coefficients
        numerator = projected * projected
    mass = float(np.sum(numerator))
    if not math.isfinite(mass) or mass <= 0.0:
        raise ControlFailureEvidence("G2c spectral distribution normalization failed")
    return numerator / mass


def _mapped_dtv(mapping: np.ndarray, q: np.ndarray, empirical: np.ndarray) -> float:
    mapped = mapping @ q
    if mapped.shape != empirical.shape or not np.all(np.isfinite(mapped)):
        raise ControlFailureEvidence("G2c mapped spectral distribution is invalid")
    return 0.5 * float(np.sum(np.abs(empirical - mapped)))


def _rotation_candidate_admissible(
    gram_residual: float, span_residual: float, tolerance: float,
) -> bool:
    """Apply the frozen item-32 comparisons with exact binary64 operands."""
    if any(
        type(value) is not float or not math.isfinite(value) or value < 0.0
        for value in (gram_residual, span_residual, tolerance)
    ):
        raise ControlFailureEvidence("G2c rotation admissibility input is invalid")
    return gram_residual <= tolerance and span_residual <= tolerance


def _certificate_residual_passes(residual: float, certificate: float) -> bool:
    """Apply one frozen observed-residual/certificate comparison."""
    if any(
        type(value) is not float or not math.isfinite(value) or value < 0.0
        for value in (residual, certificate)
    ):
        raise ControlFailureEvidence("G2c certificate comparison input is invalid")
    return residual <= certificate


def _validate_empirical_l1_premise(empirical: np.ndarray) -> None:
    """Establish the frozen v3 empirical ``L1 <= 1 + u`` premise exactly."""
    if (
        not isinstance(empirical, np.ndarray)
        or empirical.dtype != np.float64
        or empirical.ndim != 1
        or not np.all(np.isfinite(empirical))
        or np.any(empirical < 0.0)
    ):
        raise ControlFailureEvidence(
            "G2c certificate empirical L1 input is not nonnegative finite binary64"
        )
    exact_l1 = sum(
        (abs(Fraction.from_float(float(value))) for value in empirical),
        start=Fraction(0),
    )
    if exact_l1 > Fraction(1) + Fraction(1, 2**53):
        raise ControlFailureEvidence(
            "G2c certificate empirical L1 exceeds the frozen 1+u premise"
        )


def _validate_v22_operation_envelope(
    *, p: np.ndarray, basis: np.ndarray, mapping: np.ndarray,
    empirical: np.ndarray, negative_probability: float,
    probability_mass: float, rotated: np.ndarray | None = None,
    validate_q_operations: bool = False,
) -> dict[str, Any]:
    """Establish the reviewed binary64 envelope used by the v3 certificate.

    The certificate uses the standard ``gamma_n`` model.  Its precondition is
    stronger than finiteness: every executed nonzero operand, product and
    retained result must be normal binary64, the active rounding mode must be
    round-to-nearest, and every reduction length must satisfy ``n*u < 1``.
    This function checks that quantitative envelope for the original basis and,
    when supplied, the reconstructed candidate basis.  Zeros are admitted by
    the frozen arithmetic premise.
    """
    gradual = _GRADUAL_UNDERFLOW.get()
    m, rank = basis.shape
    tiny = sys.float_info.min
    maximum = sys.float_info.max
    unit_roundoff = 2.0 ** -53

    try:
        # ISO C requires FE_TONEAREST to be represented by zero on the pinned
        # glibc platform.  The comparison is made at every construction and
        # reconstruction boundary rather than inferred from process startup.
        fegetround = ctypes.CDLL(None).fegetround
        fegetround.restype = ctypes.c_int
        rounding_mode = int(fegetround())
    except (AttributeError, OSError) as error:
        raise ControlFailureEvidence(
            "G2c certificate rounding mode cannot be measured"
        ) from error

    def normal_or_zero(name: str, value: np.ndarray) -> None:
        array = np.asarray(value)
        if array.dtype != np.float64 or not np.all(np.isfinite(array)):
            raise ControlFailureEvidence(
                f"G2c certificate {name} is not finite binary64"
            )
        absolute = np.abs(array)
        if not gradual and np.any((absolute != 0.0) & (absolute < tiny)):
            raise ControlFailureEvidence(
                f"G2c certificate {name} contains a subnormal value"
            )

    def product_envelope(name: str, left: np.ndarray, right: np.ndarray,
                         reduction_length: int) -> None:
        left_nonzero = np.abs(np.asarray(left, dtype=np.float64))
        right_nonzero = np.abs(np.asarray(right, dtype=np.float64))
        left_nonzero = left_nonzero[left_nonzero != 0.0]
        right_nonzero = right_nonzero[right_nonzero != 0.0]
        if left_nonzero.size and right_nonzero.size:
            lower_left = float(np.min(left_nonzero))
            lower_right = float(np.min(right_nonzero))
            # Division avoids performing the potentially underflowing product.
            if not gradual and lower_left < tiny / lower_right:
                raise ControlFailureEvidence(
                    f"G2c certificate {name} permits product underflow"
                )
            upper_left = float(np.max(left_nonzero))
            upper_right = float(np.max(right_nonzero))
            if upper_left > maximum / upper_right / max(reduction_length, 1):
                raise ControlFailureEvidence(
                    f"G2c certificate {name} permits product/reduction overflow"
                )
        if type(reduction_length) is not int or reduction_length < 1 or (
            reduction_length * unit_roundoff >= 1.0
        ):
            raise ControlFailureEvidence(
                f"G2c certificate {name} has no gamma_n bound"
            )

    def checked_operation(name: str, operation: Any) -> np.ndarray | float:
        """Execute one reviewed NumPy operation with IEEE exceptions observable."""
        try:
            with np.errstate(
                divide="raise", invalid="raise", over="raise",
                under="ignore" if gradual else "raise",
            ):
                return operation()
        except FloatingPointError as error:
            raise ControlFailureEvidence(
                f"G2c certificate {name} raised a binary64 arithmetic exception"
            ) from error

    def subtraction_envelope(
        name: str, left: np.ndarray, right: np.ndarray,
    ) -> np.ndarray:
        left_values = np.asarray(left, dtype=np.float64).ravel()
        right_values = np.asarray(right, dtype=np.float64).ravel()
        if left_values.shape != right_values.shape:
            raise ControlFailureEvidence(
                f"G2c certificate {name} dimensions disagree"
            )
        result = np.asarray(
            checked_operation(name, lambda: left_values - right_values),
            dtype=np.float64,
        )
        normal_or_zero(name, result)
        # Two equal binary64 operands have exact zero difference.  Distinct
        # binary64 operands cannot lawfully produce rounded zero under this
        # no-underflow envelope; this also detects a flush-to-zero execution
        # mode independently of the retained result's finiteness.
        if np.any((result == 0.0) & (left_values != right_values)):
            raise ControlFailureEvidence(
                f"G2c certificate {name} rounded a nonzero subtraction to zero"
            )
        return result.reshape(np.broadcast_arrays(left, right)[0].shape)

    def division_envelope(
        name: str, numerator: np.ndarray, denominator: float,
    ) -> np.ndarray:
        if type(denominator) is not float or not math.isfinite(denominator) or denominator <= 0.0:
            raise ControlFailureEvidence(
                f"G2c certificate {name} denominator is outside the reviewed domain"
            )
        result = np.asarray(
            checked_operation(name, lambda: numerator / denominator),
            dtype=np.float64,
        )
        normal_or_zero(name, result)
        zeroed = (result == 0.0) & (np.asarray(numerator) != 0.0)
        if np.any(zeroed):
            if not gradual:
                raise ControlFailureEvidence(
                    f"G2c certificate {name} rounded a nonzero quotient to zero"
                )
            for value in np.asarray(numerator)[zeroed].ravel():
                if abs(Fraction.from_float(float(value)) / Fraction.from_float(denominator)) > Fraction(1, 2**1075):
                    raise ControlFailureEvidence(
                        f"G2c certificate {name} quotient violates gradual-underflow bound"
                    )
        return result

    def traced_distribution(
        name: str, candidate: np.ndarray,
    ) -> tuple[np.ndarray, float]:
        candidate_coefficients = np.asarray(
            checked_operation(
                f"{name} coefficient reduction", lambda: candidate.T @ root_p,
            ),
            dtype=np.float64,
        )
        normal_or_zero(f"{name} coefficients", candidate_coefficients)
        candidate_root = np.asarray(
            checked_operation(
                f"{name} projector action", lambda: candidate @ candidate_coefficients,
            ),
            dtype=np.float64,
        )
        normal_or_zero(f"{name} projector action", candidate_root)
        numerator = np.asarray(
            checked_operation(
                f"{name} mass squares", lambda: candidate_root * candidate_root,
            ),
            dtype=np.float64,
        )
        normal_or_zero(f"{name} mass squares", numerator)
        mass = float(checked_operation(f"{name} mass reduction", lambda: np.sum(numerator)))
        normal_or_zero(f"{name} mass", np.asarray([mass], dtype=np.float64))
        if mass <= 0.0:
            raise ControlFailureEvidence(f"G2c certificate {name} mass is nonpositive")
        return division_envelope(f"{name} normalization", numerator, mass), mass

    if m != 32 or not 2 <= rank <= 6:
        raise ControlFailureEvidence("G2c certificate dimensions are outside the frozen domain")
    if (
        p.shape != (m,)
        or mapping.ndim != 2
        or mapping.shape[1] != m
        or mapping.shape[0] > m
        or empirical.shape != (mapping.shape[0],)
        or not np.all(np.isfinite(p))
        or not np.all(np.isfinite(basis))
        or not np.all(np.isfinite(mapping))
        or not np.all(np.isfinite(empirical))
        or float(np.min(p)) < negative_probability
        or abs(float(np.sum(p)) - 1.0) > probability_mass
        or np.any(mapping < 0.0)
        or not np.array_equal(np.sum(mapping, axis=0), np.ones(m))
        or np.any((mapping != 0.0) & (mapping != 1.0))
        or np.any(empirical < 0.0)
        or abs(float(np.sum(empirical)) - 1.0) > probability_mass
        or rounding_mode != 0
    ):
        raise ControlFailureEvidence("G2c certificate operation envelope is not established")
    _validate_empirical_l1_premise(empirical)
    if gradual:
        _require_gradual_underflow()

    clipped = np.asarray(
        checked_operation("probability clipping", lambda: np.maximum(p, 0.0)),
        dtype=np.float64,
    )
    root_p = np.asarray(
        checked_operation("probability square root", lambda: np.sqrt(clipped)),
        dtype=np.float64,
    )
    constant = np.full(m, 1.0 / math.sqrt(m), dtype=np.float64)
    normal_or_zero("probability", p)
    normal_or_zero("clipped probability", clipped)
    normal_or_zero("square-root probability", root_p)
    normal_or_zero("original basis", basis)
    normal_or_zero("one-hot mapping", mapping)
    normal_or_zero("empirical vector", empirical)
    normal_or_zero("constant vector", constant)
    product_envelope("B^T B", basis, basis, m)
    basis_gram = np.asarray(
        checked_operation("B^T B reduction", lambda: basis.T @ basis),
        dtype=np.float64,
    )
    normal_or_zero("original Gram matrix", basis_gram)
    basis_gram_difference = subtraction_envelope(
        "original Gram residual subtraction", basis_gram, np.eye(rank),
    )
    product_envelope("B^T x", basis, root_p, m)
    coefficients = np.asarray(
        checked_operation("B^T x reduction", lambda: basis.T @ root_p),
        dtype=np.float64,
    )
    normal_or_zero("original coefficients", coefficients)
    product_envelope("B c", basis, coefficients, rank)
    projected_root = np.asarray(
        checked_operation("B c reduction", lambda: basis @ coefficients),
        dtype=np.float64,
    )
    normal_or_zero("original projector action", projected_root)
    product_envelope("projector mass squares", projected_root, projected_root, m)
    coefficient_squares = np.asarray(
        checked_operation(
            "coefficient mass squares", lambda: coefficients * coefficients,
        ),
        dtype=np.float64,
    )
    projected_squares = np.asarray(
        checked_operation(
            "projector mass squares", lambda: projected_root * projected_root,
        ),
        dtype=np.float64,
    )
    normal_or_zero("coefficient mass squares", coefficient_squares)
    normal_or_zero("projector mass squares", projected_squares)
    coefficient_mass = float(checked_operation(
        "coefficient mass reduction", lambda: np.sum(coefficient_squares),
    ))
    projected_mass = float(checked_operation(
        "projector mass reduction", lambda: np.sum(projected_squares),
    ))
    parseval_difference = subtraction_envelope(
        "Parseval residual subtraction",
        np.asarray([coefficient_mass]), np.asarray([projected_mass]),
    )
    probability_mass_value = float(checked_operation(
        "probability mass reduction", lambda: np.sum(p),
    ))
    probability_mass_difference = subtraction_envelope(
        "probability-mass residual subtraction",
        np.asarray([probability_mass_value]), np.asarray([1.0]),
    )
    product_envelope("B B^T", basis, basis, rank)
    original_projector = np.asarray(
        checked_operation("B B^T reduction", lambda: basis @ basis.T),
        dtype=np.float64,
    )
    normal_or_zero("original projector", original_projector)
    product_envelope("constant outer product", constant, constant, 1)
    constant_projector = np.asarray(
        checked_operation(
            "constant outer product", lambda: np.outer(constant, constant),
        ),
        dtype=np.float64,
    )
    normal_or_zero("constant projector", constant_projector)
    centered_projector = subtraction_envelope(
        "centered-projector subtraction", original_projector, constant_projector,
    )
    product_envelope("B^T constant", basis, constant, m)
    constant_coefficients = np.asarray(
        checked_operation(
            "B^T constant reduction", lambda: basis.T @ constant,
        ),
        dtype=np.float64,
    )
    normal_or_zero("constant coefficients", constant_coefficients)
    product_envelope("B constant coefficients", basis, constant_coefficients, rank)
    projected_constant = np.asarray(
        checked_operation(
            "B constant-coefficient reduction",
            lambda: basis @ constant_coefficients,
        ),
        dtype=np.float64,
    )
    normal_or_zero("projected constant", projected_constant)
    constant_difference = subtraction_envelope(
        "constant-span residual subtraction", projected_constant, constant,
    )
    trace: dict[str, Any] = {
        "original_gram_residual": float(np.max(np.abs(basis_gram_difference))),
        "constant_span_residual": float(np.max(np.abs(constant_difference))),
        "original_coefficients": coefficients,
        "original_projected_root": projected_root,
        "centered_projector": centered_projector,
        "normalization_mass": projected_mass,
        "p_full_norm_minus_one": float(probability_mass_difference[0]),
        "spectral_energy_minus_p_full_energy": float(parseval_difference[0]),
    }
    if validate_q_operations:
        original_q, normalization_mass = traced_distribution("original q-full", basis)
        normal_or_zero("original q-full", original_q)
        trace["original_q_full"] = original_q
        if normalization_mass.hex() != projected_mass.hex():
            raise ControlFailureEvidence(
                "G2c certificate normalization-mass traces disagree"
            )
    if rotated is not None:
        if rotated.shape != basis.shape:
            raise ControlFailureEvidence(
                "G2c reconstructed rotation dimensions disagree"
            )
        normal_or_zero("rotated basis", rotated)
        product_envelope("R^T R", rotated, rotated, m)
        product_envelope("R R^T", rotated, rotated, rank)
        product_envelope("R^T x", rotated, root_p, m)
        rotated_coefficients = np.asarray(
            checked_operation("R^T x reduction", lambda: rotated.T @ root_p),
            dtype=np.float64,
        )
        normal_or_zero("rotated coefficients", rotated_coefficients)
        product_envelope("R c", rotated, rotated_coefficients, rank)
        rotated_root = np.asarray(
            checked_operation("R c reduction", lambda: rotated @ rotated_coefficients),
            dtype=np.float64,
        )
        normal_or_zero("rotated projector action", rotated_root)
        product_envelope("rotated mass squares", rotated_root, rotated_root, m)
        rotated_gram = np.asarray(
            checked_operation("R^T R reduction", lambda: rotated.T @ rotated),
            dtype=np.float64,
        )
        normal_or_zero("rotated Gram matrix", rotated_gram)
        gram_difference = subtraction_envelope(
            "Gram residual subtraction", rotated_gram, np.eye(rank),
        )
        rotated_projector = np.asarray(
            checked_operation("R R^T reduction", lambda: rotated @ rotated.T),
            dtype=np.float64,
        )
        normal_or_zero("rotated projector", rotated_projector)
        projector_difference = subtraction_envelope(
            "span residual subtraction", rotated_projector, original_projector,
        )
        trace["gram_residual"] = float(np.max(np.abs(gram_difference)))
        trace["span_residual"] = float(np.max(np.abs(projector_difference)))
        if validate_q_operations:
            rotated_q, _ = traced_distribution("rotated q-full", rotated)
            normal_or_zero("rotated q-full", rotated_q)
            product_envelope("original one-hot map", mapping, original_q, m)
            product_envelope("rotated one-hot map", mapping, rotated_q, m)
            original_mapped = np.asarray(
                checked_operation("original one-hot reduction", lambda: mapping @ original_q),
                dtype=np.float64,
            )
            rotated_mapped = np.asarray(
                checked_operation("rotated one-hot reduction", lambda: mapping @ rotated_q),
                dtype=np.float64,
            )
            normal_or_zero("original mapped q-full", original_mapped)
            normal_or_zero("rotated mapped q-full", rotated_mapped)
            original_difference = subtraction_envelope(
                "original empirical subtraction", empirical, original_mapped,
            )
            rotated_difference = subtraction_envelope(
                "rotated empirical subtraction", empirical, rotated_mapped,
            )
            original_absolute = np.abs(original_difference)
            rotated_absolute = np.abs(rotated_difference)
            normal_or_zero("original absolute mapped residual", original_absolute)
            normal_or_zero("rotated absolute mapped residual", rotated_absolute)
            component_difference = subtraction_envelope(
                "component residual subtraction", rotated_q, original_q,
            )
            original_l1 = float(checked_operation(
                "original absolute reduction", lambda: np.sum(original_absolute),
            ))
            rotated_l1 = float(checked_operation(
                "rotated absolute reduction", lambda: np.sum(rotated_absolute),
            ))
            original_dtv = float(checked_operation(
                "original half scaling", lambda: np.float64(0.5) * original_l1,
            ))
            rotated_dtv = float(checked_operation(
                "rotated half scaling", lambda: np.float64(0.5) * rotated_l1,
            ))
            normal_or_zero(
                "mapped dTV values", np.asarray([original_dtv, rotated_dtv]),
            )
            dtv_difference = subtraction_envelope(
                "persisted mapped dTV subtraction",
                np.asarray([rotated_dtv]), np.asarray([original_dtv]),
            )
            trace.update({
                "original_q_full": original_q,
                "rotated_q_full": rotated_q,
                "component_residual": float(np.max(np.abs(component_difference))),
                "dtv_residual": float(np.abs(dtv_difference[0])),
            })
    return {
        "schema": "RB1_G2C_V22_REVIEWED_OPERATION_ENVELOPE_V1",
        "rounding_mode": "binary64_round_to_nearest_ties_to_even",
        "normal_intermediates": not gradual,
        "underflow": gradual,
        "overflow": False,
        "unit_roundoff": unit_roundoff,
        "gamma_m": (m * unit_roundoff) / (1.0 - m * unit_roundoff),
        "gamma_r": (rank * unit_roundoff) / (1.0 - rank * unit_roundoff),
        "operation_families": [
            "projector_products", "coefficient_products", "mass_squares_and_reductions",
            "normalizations", "one_hot_mapping", "gram_and_span_residual_subtraction",
            "constant_span_and_parseval_subtraction", "q_component_subtraction",
            "empirical_subtraction",
            "absolute_reduction_and_half_scaling", "persisted_residual_subtraction",
        ],
        "trace": trace,
    }


def _framed_fields(source_json_sha256: str, unit_id: str, replicate: int, attempt: int) -> list[dict[str, str]]:
    fields = (
        ("string", b"G2C_ROTATION"),
        ("bytes", bytes.fromhex(source_json_sha256)),
        ("string", unit_id.encode("utf-8")),
        ("u64", replicate.to_bytes(8, "big")),
        ("u64", attempt.to_bytes(8, "big")),
    )
    return [{"type_tag": tag, "raw_hex": raw.hex()} for tag, raw in fields]


def _rotation_evidence(
    spec: FrozenSpec,
    record: Mapping[str, Any],
    *,
    p: np.ndarray,
    basis: np.ndarray,
    root_p: np.ndarray,
    mapping: np.ndarray,
    empirical: np.ndarray,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    m, rank = basis.shape
    envelope_p = np.asarray(p, dtype=np.float64)
    constant = np.full(m, 1.0 / math.sqrt(m), dtype=np.float64)
    base_envelope = _validate_v22_operation_envelope(
        p=envelope_p,
        basis=basis,
        mapping=mapping,
        empirical=empirical,
        negative_probability=contract["negative_probability"],
        probability_mass=contract["probability_mass"],
        validate_q_operations=True,
    )
    base_trace = base_envelope["trace"]
    if base_trace["constant_span_residual"] > contract["constant_span"]:
        raise ControlFailureEvidence("G2c retained span omits the frozen constant vector")
    normalization_mass = base_trace["normalization_mass"]
    if not math.isfinite(normalization_mass) or normalization_mass <= 0.0:
        raise ControlFailureEvidence("G2c dedicated q-full mass is invalid")
    original_full = base_trace["original_q_full"]
    original_diag = _distribution(basis, root_p, diagonal=True)
    projector = base_trace["centered_projector"]
    records: list[dict[str, Any]] = []
    full_components: list[float] = []
    full_dtv: list[float] = []
    diag_components: list[float] = []
    diag_dtv: list[float] = []
    for replicate in range(16):
        accepted: tuple[int, bytes, RNGStream, np.ndarray, float, float] | None = None
        for attempt in range(8):
            fields = [
                ("str", "G2C_ROTATION"),
                ("bytes", bytes.fromhex(contract["source_json_sha256"])),
                ("str", record["unit_id"]),
                ("u64", replicate),
                ("u64", attempt),
            ]
            key = master_key(contract["master_prefix"], fields)
            stream = RNGStream(key)
            count = m * max(rank - 1, 0)
            normals: list[float] = []
            while len(normals) < count:
                normals.extend(stream.normal_pair())
            if rank == 1:
                rotated = constant[:, None]
            else:
                gaussian = np.asarray(normals[:count], dtype=np.float64).reshape((m, rank - 1))
                rotated = _two_pass_mgs(projector @ gaussian, rank, contract["mgs_norm"])
                if rotated is None:
                    continue
                for column in range(1, rank):
                    candidates = np.flatnonzero(
                        np.abs(rotated[:, column]) > contract["mgs_orientation"]
                    )
                    if candidates.size and rotated[int(candidates[0]), column] < 0.0:
                        rotated[:, column] *= -1.0
            candidate_envelope = _validate_v22_operation_envelope(
                p=envelope_p,
                basis=basis,
                mapping=mapping,
                empirical=empirical,
                negative_probability=contract["negative_probability"],
                probability_mass=contract["probability_mass"],
                rotated=rotated,
            )
            candidate_trace = candidate_envelope["trace"]
            gram = candidate_trace["gram_residual"]
            span = candidate_trace["span_residual"]
            if not _rotation_candidate_admissible(
                gram, span, contract["rotation_admissibility"]
            ):
                continue
            accepted = attempt, key, stream, rotated, gram, span
            break
        if accepted is None:
            raise ControlFailureEvidence("G2c rotation construction exhausted eight attempts")
        attempt, key, stream, rotated, gram, span = accepted
        operation_envelope = _validate_v22_operation_envelope(
            p=envelope_p,
            basis=basis,
            mapping=mapping,
            empirical=empirical,
            negative_probability=contract["negative_probability"],
            probability_mass=contract["probability_mass"],
            rotated=rotated,
            validate_q_operations=True,
        )
        operation_trace = operation_envelope["trace"]
        q_full = operation_trace["rotated_q_full"]
        q_diag = _distribution(rotated, root_p, diagonal=True)
        component_residual = operation_trace["component_residual"]
        dtv_residual = operation_trace["dtv_residual"]
        full_components.append(component_residual)
        full_dtv.append(dtv_residual)
        diag_components.append(float(np.max(np.abs(q_diag - original_diag))))
        diag_dtv.append(_mapped_dtv(mapping, q_diag, empirical))
        consumed = 0 if rank == 1 else 2 * math.ceil((m * (rank - 1)) / 2)
        certificate_args = dict(
            rho=gram, sigma=span, s_b=normalization_mass,
            m=m, r=rank, a=-contract["negative_probability"],
            t=contract["probability_mass"], b=contract["constant_span"],
        )
        if _GRADUAL_UNDERFLOW.get():
            certificate = evaluate_gradual_underflow_certificate(**certificate_args)
        else:
            certificate = evaluate_rotation_certificate(
                contract["controls"]["rotation"]["certificate"]["expression"],
                **certificate_args,
            )
        if certificate["reason"] is not None:
            raise ControlFailureEvidence(str(certificate["reason"]))
        component_pass = _certificate_residual_passes(
            component_residual, certificate["certificate_component"]
        )
        dtv_pass = _certificate_residual_passes(
            dtv_residual, certificate["certificate_dtv"]
        )
        records.append({
            "replicate_index": replicate,
            "accepted_attempt": attempt,
            "framed_rng_fields": _framed_fields(
                contract["source_json_sha256"], record["unit_id"], replicate, attempt
            ),
            "master_key_sha256": key.hex(),
            "consumed_word_count": consumed,
            "highest_counter": None if consumed == 0 else stream.counter - 1,
            "implementation_version": contract["master_prefix"],
            "gram_residual": gram,
            "span_residual": span,
            "rejected_attempt_count": attempt,
            "certificate_common_mass_lower": certificate[
                "certificate_common_mass_lower"
            ],
            "certificate_component": certificate["certificate_component"],
            "certificate_dtv": certificate["certificate_dtv"],
            "component_pass": component_pass,
            "dtv_pass": dtv_pass,
        })
    detail = {
        "replicates": records,
        "q_full_component_residuals": full_components,
        "q_full_dtv_residuals": full_dtv,
        "q_diag_component_residuals": diag_components,
        "q_diag_dtv_values": diag_dtv,
        "q_diag_dtv_summary": {
            "min": min(diag_dtv),
            "max": max(diag_dtv),
            "mean": math.fsum(diag_dtv) / 16,
        },
        "rotation_certificate_scale": {
            "certificate_component_max": max(
                item["certificate_component"] for item in records
            ),
            "certificate_dtv_max": max(item["certificate_dtv"] for item in records),
            "rejected_attempt_total": sum(
                item["rejected_attempt_count"] for item in records
            ),
        },
    }
    expected_keys = contract["controls"]["rotation"]["evaluation_artifact_encoding"]["keys"]
    if list(detail) != expected_keys:
        raise SpecMismatch("frozen G2c rotation evidence field order disagrees")
    replicate_keys = contract["controls"]["rotation"]["rng"]["replicate_record_keys"]
    for replicate, retained in enumerate(records):
        consumed = 0 if rank == 1 else 2 * math.ceil((m * (rank - 1)) / 2)
        if (
            list(retained) != replicate_keys
            or type(retained["replicate_index"]) is not int
            or retained["replicate_index"] != replicate
            or type(retained["accepted_attempt"]) is not int
            or not 0 <= retained["accepted_attempt"] <= 7
            or retained["framed_rng_fields"] != _framed_fields(
                contract["source_json_sha256"], record["unit_id"], replicate,
                retained["accepted_attempt"]
            )
            or type(retained["master_key_sha256"]) is not str
            or len(retained["master_key_sha256"]) != 64
            or retained["consumed_word_count"] != consumed
            or type(retained["consumed_word_count"]) is not int
            or retained["highest_counter"]
            != (None if consumed == 0 else math.ceil(consumed / 4) - 1)
            or retained["implementation_version"] != contract["master_prefix"]
            or retained["rejected_attempt_count"] != retained["accepted_attempt"]
            or type(retained["component_pass"]) is not bool
            or type(retained["dtv_pass"]) is not bool
        ):
            raise ControlFailureEvidence("G2c rotation replicate evidence disagrees")
    for name in (
        "q_full_component_residuals", "q_full_dtv_residuals",
        "q_diag_component_residuals", "q_diag_dtv_values",
    ):
        if (
            type(detail[name]) is not list
            or len(detail[name]) != 16
            or any(type(value) is not float or not math.isfinite(value) for value in detail[name])
        ):
            raise ControlFailureEvidence("G2c rotation residual array disagrees")
    if detail["q_diag_dtv_summary"] != {
        "min": min(detail["q_diag_dtv_values"]),
        "max": max(detail["q_diag_dtv_values"]),
        "mean": math.fsum(detail["q_diag_dtv_values"]) / 16,
    }:
        raise ControlFailureEvidence("G2c q-diag diagnostic summary disagrees")
    if detail["rotation_certificate_scale"] != {
        "certificate_component_max": max(
            item["certificate_component"] for item in records
        ),
        "certificate_dtv_max": max(item["certificate_dtv"] for item in records),
        "rejected_attempt_total": sum(
            item["rejected_attempt_count"] for item in records
        ),
    }:
        raise ControlFailureEvidence("G2c rotation certificate scale disagrees")
    return detail


def validate_g2c_v22_rotation_evidence(
    spec: FrozenSpec,
    record: Mapping[str, Any],
    control: Mapping[str, Any],
    detail: Mapping[str, Any],
    *,
    implementation_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Independently reconstruct a dedicated v22 control and compare its bytes."""
    contract = _contract(spec, implementation_manifest_path)
    kind = _kind(record)
    p = np.asarray(record["unrounded_p_full"], dtype=np.float64)
    basis = np.asarray(
        record["basis_and_projector_inputs"]["emitted_basis"], dtype=np.float64
    )
    mapping = np.asarray(record[f"M_{kind}_or_content_hash"], dtype=np.float64)
    empirical = np.asarray(record[f"unrounded_y_{kind}"], dtype=np.float64)
    if p.ndim != 1 or basis.ndim != 2 or basis.shape != (32, basis.shape[1]):
        raise ControlFailureEvidence("G2c reconstructed certificate dimensions disagree")
    root_p = np.sqrt(np.maximum(p, 0.0))
    operation_envelope = _validate_v22_operation_envelope(
        p=p,
        basis=basis,
        mapping=mapping,
        empirical=empirical,
        negative_probability=contract["negative_probability"],
        probability_mass=contract["probability_mass"],
    )
    operation_trace = operation_envelope["trace"]
    coefficients = operation_trace["original_coefficients"]
    direct_mass = operation_trace["normalization_mass"]
    parseval = control.get("parseval_residuals", {})
    expected_parseval = {
        "p_full_norm_minus_one": operation_trace["p_full_norm_minus_one"],
        "spectral_energy_minus_p_full_energy": operation_trace[
            "spectral_energy_minus_p_full_energy"
        ],
    }
    recovered_mass = float(
        np.sum(coefficients * coefficients)
        - parseval.get("spectral_energy_minus_p_full_energy")
    )
    retained_mass = control.get("normalization_mass_q_full_control")
    if (
        type(parseval) is not dict
        or set(parseval) != {
            "p_full_norm_minus_one", "spectral_energy_minus_p_full_energy"
        }
        or any(type(value) is not float or not math.isfinite(value) for value in parseval.values())
        or any(
            struct.pack(">d", parseval[name]) != struct.pack(">d", expected)
            for name, expected in expected_parseval.items()
        )
        or
        type(retained_mass) is not float
        or retained_mass.hex() != direct_mass.hex()
        or recovered_mass.hex() != direct_mass.hex()
        or type(control.get("spectral_coefficients")) is not dict
        or type(control["spectral_coefficients"].get("values")) is not list
        or len(control["spectral_coefficients"]["values"]) != len(coefficients)
        or any(
            type(actual) is not float
            or struct.pack(">d", actual) != struct.pack(">d", float(expected))
            for actual, expected in zip(
                control["spectral_coefficients"]["values"], coefficients, strict=True
            )
        )
    ):
        raise ControlFailureEvidence("G2c dedicated normalization-mass reconstruction differs")
    reconstructed = _rotation_evidence(
        spec,
        record,
        p=p,
        basis=basis,
        root_p=root_p,
        mapping=mapping,
        empirical=empirical,
        contract=contract,
    )
    def exact_tree(actual: Any, expected: Any, path: str) -> None:
        if type(expected) is dict:
            if not isinstance(actual, Mapping) or (
                len(actual) != len(expected) or set(actual) != set(expected)
            ):
                raise ControlFailureEvidence(
                    f"G2c rotation reconstruction keys differ at {path}"
                )
            for key in expected:
                exact_tree(actual[key], expected[key], f"{path}/{key}")
            return
        if type(actual) is not type(expected):
            raise ControlFailureEvidence(
                f"G2c rotation reconstruction type differs at {path}"
            )
        if type(expected) is float:
            if not math.isfinite(actual) or struct.pack(">d", actual) != struct.pack(">d", expected):
                raise ControlFailureEvidence(
                    f"G2c rotation reconstruction binary64 differs at {path}"
                )
        elif type(expected) is list:
            if len(actual) != len(expected):
                raise ControlFailureEvidence(
                    f"G2c rotation reconstruction length differs at {path}"
                )
            for index, (left, right) in enumerate(zip(actual, expected, strict=True)):
                exact_tree(left, right, f"{path}/{index}")
        elif actual != expected:
            raise ControlFailureEvidence(
                f"G2c rotation reconstruction differs at {path}"
            )

    exact_tree(detail, reconstructed, "rotation_evidence")
    descriptor = {
        "kind": "object",
        "keys": contract["controls"]["control_record_shape"]["keys"],
        "properties": contract["controls"]["control_record_shape"]["field_shapes"],
    }
    try:
        _validate_descriptor(
            control, descriptor, path="g2c_control", dimensions={"r": basis.shape[1]},
            content_root=None,
        )
    except (IncompleteCampaign, ControlFailureEvidence, SpecMismatch) as error:
        raise ControlFailureEvidence(
            f"G2c persisted control shape differs: {error}"
        ) from error
    detail_keys = contract["controls"]["rotation"]["evaluation_artifact_encoding"]["keys"]
    if len(detail) != len(detail_keys) or set(detail) != set(detail_keys):
        raise ControlFailureEvidence("G2c rotation reconstruction differs from sealed evidence")
    expected_residuals = {
        "q_full_max_component": max(reconstructed["q_full_component_residuals"]),
        "q_full_dtv": max(reconstructed["q_full_dtv_residuals"]),
        "q_diag_max_component_diagnostic": max(
            reconstructed["q_diag_component_residuals"]
        ),
    }
    exact_tree(control.get("rotation_residuals"), expected_residuals, "rotation_residuals")
    if control.get("rotation_residuals") != expected_residuals:
        raise ControlFailureEvidence("G2c rotation residual summary reconstruction differs")
    expected_pass = all(
        row["component_pass"] and row["dtv_pass"]
        for row in reconstructed["replicates"]
    )
    if control.get("pass_boolean_for_each_control", {}).get("rotation") is not expected_pass:
        raise ControlFailureEvidence("G2c rotation Boolean reconstruction differs")
    return {
        "rotation_residuals": expected_residuals,
        "rotation_pass": expected_pass,
        "normalization_mass_q_full_control": direct_mass,
        "parseval_residuals": expected_parseval,
    }


def build_g2c_controls(
    spec: FrozenSpec,
    records: Sequence[Mapping[str, Any]],
    *,
    implementation_manifest_path: Path | None = None,
) -> G2CControlArtifacts:
    """Evaluate every frozen control before the G2c spectral inclusion mask."""
    contract = _contract(spec, implementation_manifest_path)
    fields = contract["controls"]["control_record_shape"]["keys"]
    expected_ties = contract["controls"]["control_record_shape"]["field_shapes"]["tie_residuals"]["key_set"]
    controls: list[dict[str, Any]] = []
    rotation: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    retained_kind_cells: set[str] = set()
    def finding(
        *, condition: str, stage: str, unit_id: Any, kind_cell_id: Any,
        invariant: str, detail: str,
    ) -> dict[str, Any]:
        return {
            "condition": condition,
            "stage": stage,
            "unit_id": unit_id if isinstance(unit_id, str) else None,
            "kind_cell_id": kind_cell_id if isinstance(kind_cell_id, str) else None,
            "invariant": invariant,
            "detail": detail,
        }
    for record in records:
        unit_identity = record.get("unit_id") if isinstance(record, Mapping) else None
        kind_identity = (
            record.get("kind_cell_id") if isinstance(record, Mapping) else None
        )
        try:
            kind = _kind(record)
            if record["kind_cell_id"] in retained_kind_cells:
                failures.append(finding(
                    condition="incomplete",
                    stage="control_construction",
                    unit_id=unit_identity,
                    kind_cell_id=kind_identity,
                    invariant="duplicate_kind_cell_identity",
                    detail="G2c control identity repeats",
                ))
                continue
            p = np.asarray(record["unrounded_p_full"], dtype=np.float64)
            basis = np.asarray(record["basis_and_projector_inputs"]["emitted_basis"], dtype=np.float64)
            if (
                p.ndim != 1
                or basis.ndim != 2
                or basis.shape[0] != len(p)
                or basis.shape[1] < 1
                or not np.all(np.isfinite(p))
                or not np.all(np.isfinite(basis))
            ):
                raise ControlFailureEvidence("G2c probability or basis invariant failed")
            mapping = np.asarray(record[f"M_{kind}_or_content_hash"], dtype=np.float64)
            empirical = np.asarray(record[f"unrounded_y_{kind}"], dtype=np.float64)
            operation_envelope = _validate_v22_operation_envelope(
                p=p,
                basis=basis,
                mapping=mapping,
                empirical=empirical,
                negative_probability=contract["negative_probability"],
                probability_mass=contract["probability_mass"],
            )
            operation_trace = operation_envelope["trace"]
            if operation_trace["original_gram_residual"] > contract["constant_span"]:
                raise ControlFailureEvidence("G2c probability or basis invariant failed")
            root_p = np.sqrt(np.maximum(p, 0.0))
            coefficients = operation_trace["original_coefficients"]
            persisted = np.asarray(record["spectral_coefficients"]["values"], dtype=np.float64)
            if persisted.shape != coefficients.shape or not np.array_equal(persisted, coefficients):
                raise ControlFailureEvidence("G2c spectral coefficient identity disagrees")
            parseval = {
                "p_full_norm_minus_one": operation_trace["p_full_norm_minus_one"],
                "spectral_energy_minus_p_full_energy": operation_trace[
                    "spectral_energy_minus_p_full_energy"
                ],
            }
            normalization_mass = operation_trace["normalization_mass"]
            if not math.isfinite(normalization_mass) or normalization_mass <= 0.0:
                raise ControlFailureEvidence("G2c dedicated q-full mass is invalid")
            local_contract = {**contract, "normalization_mass_q_full_control": normalization_mass}
            detail = _rotation_evidence(
                spec,
                record,
                p=p,
                basis=basis,
                root_p=root_p,
                mapping=mapping,
                empirical=empirical,
                contract=local_contract,
            )
            rotation[record["kind_cell_id"]] = detail
            rotation_residuals = {
                "q_full_max_component": max(detail["q_full_component_residuals"]),
                "q_full_dtv": max(detail["q_full_dtv_residuals"]),
                "q_diag_max_component_diagnostic": max(detail["q_diag_component_residuals"]),
            }
            tie_residuals = {name: float(record["pairwise_contrast"][name]) for name in expected_ties}
            ties_pass = all(
                record["tie_flag"][name] is (abs(value) <= contract["tie"])
                for name, value in tie_residuals.items()
            )
            passing = {
                "parseval": max(abs(value) for value in parseval.values())
                <= contract["parseval"],
                "rotation": (
                    all(item["component_pass"] and item["dtv_pass"] for item in detail["replicates"])
                ),
                "ties": ties_pass,
            }
            control = {
                "unit_id": record["unit_id"],
                "kind_cell_id": record["kind_cell_id"],
                "spectral_coefficients": {
                    "mode_ids": list(record["spectral_coefficients"]["mode_ids"]),
                    "values": coefficients.tolist(),
                },
                "normalization_mass_q_full_control": normalization_mass,
                "nondegenerate": _is_nondegenerate(coefficients, contract["coefficient"]),
                "parseval_residuals": parseval,
                "rotation_residuals": rotation_residuals,
                "tie_residuals": tie_residuals,
                "pass_boolean_for_each_control": passing,
            }
            if list(control) != fields:
                raise SpecMismatch("frozen G2c control record field order disagrees")
            descriptor = {
                "kind": "object",
                "keys": fields,
                "properties": contract["controls"]["control_record_shape"]["field_shapes"],
            }
            try:
                _validate_descriptor(
                    control,
                    descriptor,
                    path="g2c_control",
                    dimensions={"r": basis.shape[1]},
                    content_root=None,
                )
            except (IncompleteCampaign, ControlFailureEvidence, SpecMismatch) as error:
                raise IncompleteCampaign(
                    f"G2c control descriptor validation failed: {error}"
                ) from error
            for invariant, passed in passing.items():
                if not passed:
                    failures.append(finding(
                        condition="control_failure",
                        stage="control_construction",
                        unit_id=record["unit_id"],
                        kind_cell_id=record["kind_cell_id"],
                        invariant=invariant,
                        detail=f"G2c {invariant} control returned false",
                    ))
            controls.append(control)
            retained_kind_cells.add(control["kind_cell_id"])
        except ControlFailureEvidence as error:
            detail = str(error).removeprefix("CONTROL_FAILURE: ")
            retained = finding(
                condition="control_failure",
                stage="control_construction",
                unit_id=unit_identity,
                kind_cell_id=kind_identity,
                invariant="control_calculation",
                detail=detail,
            )
            if "NONPOSITIVE_COMMON_MASS_LOWER" in detail:
                # The execution/completion-failure contracts admit only the
                # five common finding members.  Preserve the certificate's
                # negative result in the admitted detail member rather than
                # leaking the successful-replicate certificate shape into a
                # preemption finding.
                retained["detail"] = (
                    f"{detail}; reason_code=NONPOSITIVE_COMMON_MASS_LOWER; "
                    "certificate_component=null; certificate_dtv=null"
                )
            failures.append(retained)
        except (
            IncompleteCampaign, KeyError, TypeError, ValueError, FloatingPointError,
        ) as error:
            failures.append(finding(
                condition="incomplete",
                stage="control_construction",
                unit_id=unit_identity,
                kind_cell_id=kind_identity,
                invariant="control_input_shape",
                detail=f"G2c control input is malformed: {error}",
            ))
    masses_by_unit: dict[str, list[float]] = {}
    for control in controls:
        masses_by_unit.setdefault(control["unit_id"], []).append(
            control["normalization_mass_q_full_control"]
        )
    for unit_id, masses in masses_by_unit.items():
        if len(masses) != 2 or masses[0].hex() != masses[1].hex():
            failures.append(finding(
                condition="control_failure",
                stage="control_construction",
                unit_id=unit_id,
                kind_cell_id=None,
                invariant="paired_dedicated_normalization_mass",
                detail="G2c raw/package dedicated control masses differ",
            ))
    return G2CControlArtifacts(
        records=tuple(controls),
        rotation_evidence=rotation,
        complete=not failures,
        failures=tuple(failures),
    )

# Production writers restored from the same historical implementation.

@contextlib.contextmanager
def gradual_underflow_certificate():
    """Scope the prospective v4 arithmetic rule to one close-out computation."""
    token = _GRADUAL_UNDERFLOW.set(True)
    try:
        yield
    finally:
        _GRADUAL_UNDERFLOW.reset(token)

def validate_g2c_v4_rotation_evidence(
    spec: FrozenSpec, record: Mapping[str, Any], control: Mapping[str, Any],
    detail: Mapping[str, Any], *, implementation_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Independently reconstruct one prospective gradual-underflow control.

    The original v22 entry remains normal-only for historical evidence.
    """
    with gradual_underflow_certificate():
        return validate_g2c_v22_rotation_evidence(
            spec, record, control, detail,
            implementation_manifest_path=implementation_manifest_path,
        )
