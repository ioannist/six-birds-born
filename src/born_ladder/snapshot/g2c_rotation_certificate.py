"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import math
from fractions import Fraction
from functools import lru_cache
from typing import Any, Mapping
from born_ladder.snapshot.errors import ControlFailureEvidence, SpecMismatch
from born_ladder.snapshot.frozen_spec import canonical_json_bytes, sha256_bytes

_F = Fraction


_ONE = _F(1)


_U = _F(1, 2**53)


_ETA = _F(1, 2**1075)


_SQRT_BITS = 256


def _exact_float(value: float) -> Fraction:
    if type(value) is not float or not math.isfinite(value):
        raise ControlFailureEvidence("G2c certificate input is not finite binary64")
    return _F.from_float(value)


def _gamma(n: int) -> Fraction:
    value = n * _U
    return value / (_ONE - value)


def _underflow_sum(n: int) -> Fraction:
    """Outward additive budget for at most n gradually underflowing stages."""
    if type(n) is not int or n < 0 or n * _U >= 1:
        raise ControlFailureEvidence("G2c certificate reduction length is invalid")
    return n * _ETA / (1 - n * _U)


def evaluate_gradual_underflow_certificate(
    *, rho: float, sigma: float, s_b: float, m: int, r: int,
    a: float, t: float, b: float,
) -> dict[str, float | str | None]:
    """Prospective additive-underflow enclosure, in exact rational arithmetic.

    Equations and their operationwise proof are in RB1_G2C_underflow_amendment.
    The signed v3 evaluator above remains unchanged for historical routes.
    """
    if m != 32 or not 2 <= r <= 6:
        raise ControlFailureEvidence("G2c certificate dimensions are outside the frozen domain")
    rho_f, sigma_f, mass = map(_exact_float, (rho, sigma, s_b))
    a_f, t_f, b_f = map(_exact_float, (a, t, b))
    if min(rho_f, sigma_f, mass, a_f, t_f, b_f) < 0 or mass == 0:
        raise ControlFailureEvidence("G2c certificate inputs are outside the frozen domain")
    gm, gr = _gamma(m), _gamma(r)
    hm, h2m, h2r = _underflow_sum(m), _underflow_sum(2*m), _underflow_sum(2*r)
    positive_mass_upper = (
        1 + (t_f + _ETA)/(1-_U) + (1+gm)*m*a_f + hm
    )/(1-gm)
    x = (1+_U)*_sqrt_upper(positive_mass_upper) + _sqrt_upper(_F(m))*_ETA

    def basis_bounds(measured: Fraction) -> tuple[Fraction, Fraction, Fraction]:
        observed = (measured + _ETA)/(1-_U)
        column = (1 + observed + h2m)/(1-gm)
        beta = observed + gm*column + h2m
        action_error = (
            r*column*x*(gm + gr*(1+gm))
            + r*_sqrt_upper(column)*(1+gr)*h2m
            + _sqrt_upper(_F(m))*h2r
        )
        return column, beta, (1+r*beta)*x + action_error

    cb, beta_b, zb = basis_bounds(b_f)
    cr, beta_r, zr = basis_bounds(rho_f)
    def action_error(column: Fraction) -> Fraction:
        return (r*column*x*(gm+gr*(1+gm))
                +r*_sqrt_upper(column)*(1+gr)*h2m
                +_sqrt_upper(_F(m))*h2r)
    span = (sigma_f+_ETA)/(1-_U)+gr*r*(cb+cr)+2*h2r
    # An entrywise m-by-m bound Sigma yields Frobenius/operator bound m*Sigma,
    # not sqrt(m)*Sigma.  The latter bounds one row only.
    dz = m*span*x+action_error(cb)+action_error(cr)
    nb, nr = (1+_U)*zb*zb+_ETA, (1+_U)*zr*zr+_ETA
    dn = (zb+zr)*dz+_U*(zb*zb+zr*zr)+2*_ETA
    ds = m*dn+gm*m*(nb+nr)+2*hm
    lower = mass-ds
    if lower <= 0:
        return {
            "reason": "NONPOSITIVE_COMMON_MASS_LOWER",
            "certificate_common_mass_lower": _downward(lower),
            "certificate_component": None, "certificate_dtv": None,
        }
    raw_component = dn/lower+nb*ds/(lower*mass)+_U*(nb/mass+nr/lower)+2*_ETA
    component = (1+_U)*raw_component+_ETA
    q_max = max((1+_U)*nb/mass+_ETA, (1+_U)*nr/lower+_ETA)
    e_map = gm*m*q_max+m*hm
    l_bound = 1+_U+m*q_max+e_map
    e_sub = _U*l_bound+m*_ETA
    e_red = gm*(l_bound+e_sub)+hm
    e_half = _U*(l_bound+e_sub+e_red)/2+_ETA
    e_eval = (e_map+e_sub+e_red)/2+e_half
    dtv = m*component/2+2*e_eval+_U*(l_bound+2*e_eval)+_ETA
    return {
        "reason": None,
        "certificate_common_mass_lower": _downward(lower),
        "certificate_component": _upward(component),
        "certificate_dtv": _upward(dtv),
    }


@lru_cache(maxsize=None)
def _sqrt_upper(value: Fraction) -> Fraction:
    if value < 0:
        raise ControlFailureEvidence("G2c certificate square-root argument is negative")
    scale = 1 << (2 * _SQRT_BITS)
    ceiling = (value.numerator * scale + value.denominator - 1) // value.denominator
    root = math.isqrt(ceiling)
    if root * root < ceiling:
        root += 1
    result = _F(root, 1 << _SQRT_BITS)
    if result * result < value:
        raise AssertionError("directed square-root enclosure failed")
    return result


def _upward(value: Fraction) -> float:
    result = float(value)
    if _F.from_float(result) < value:
        result = math.nextafter(result, math.inf)
    if not math.isfinite(result) or _F.from_float(result) < value:
        raise ControlFailureEvidence("G2c certificate upward rounding failed")
    return result


def _downward(value: Fraction) -> float:
    result = float(value)
    if _F.from_float(result) > value:
        result = math.nextafter(result, -math.inf)
    if not math.isfinite(result) or _F.from_float(result) > value:
        raise ControlFailureEvidence("G2c certificate downward rounding failed")
    return result


def _evaluate_expression(node: Mapping[str, Any], variables: Mapping[str, Fraction]) -> Any:
    kind = node.get("kind")
    if kind == "literal":
        value = node.get("value")
        if type(value) is not int:
            raise SpecMismatch("G2c certificate literal is not an integer")
        return _F(value)
    if kind == "variable":
        name = node.get("name")
        if name not in variables:
            raise SpecMismatch(f"G2c certificate variable {name!r} is unbound")
        return variables[name]
    if kind == "operator":
        arguments = [_evaluate_expression(item, variables) for item in node.get("arguments", [])]
        if len(arguments) != 2:
            raise SpecMismatch("G2c certificate operator is not binary")
        operator = node.get("operator")
        if operator == "+":
            return arguments[0] + arguments[1]
        if operator == "-":
            return arguments[0] - arguments[1]
        if operator == "*":
            return arguments[0] * arguments[1]
        if operator == "/":
            if arguments[1] == 0:
                raise ControlFailureEvidence("G2c certificate attempted division by zero")
            return arguments[0] / arguments[1]
        raise SpecMismatch("G2c certificate operator is unknown")
    if kind == "call":
        arguments = [_evaluate_expression(item, variables) for item in node.get("arguments", [])]
        if node.get("function") == "sqrt_upper" and len(arguments) == 1:
            return _sqrt_upper(arguments[0])
        if node.get("function") == "min" and len(arguments) == 2:
            return min(arguments)
        raise SpecMismatch("G2c certificate call is unknown")
    if kind == "comparison":
        left = _evaluate_expression(node["left"], variables)
        right = _evaluate_expression(node["right"], variables)
        if node.get("operator") == ">":
            return left > right
        if node.get("operator") == "<=":
            return left <= right
        raise SpecMismatch("G2c certificate comparison is unknown")
    raise SpecMismatch("G2c certificate expression node is unknown")


def evaluate_rotation_certificate(
    expression: Mapping[str, Any], *, rho: float, sigma: float, s_b: float,
    m: int, r: int, a: float, t: float, b: float,
) -> dict[str, float | str | None]:
    """Evaluate the signed tree on exact binary64 inputs with directed outputs."""
    if expression.get("schema") != "RB1_G2C_ROTATION_CERTIFICATE_V3_EXPRESSION_V1":
        raise SpecMismatch("G2c rotation certificate schema differs")
    if sha256_bytes(canonical_json_bytes(expression)) != (
        "160ec3a69964c22652ac94d654cece518a68e541ba31267793137b857b4048d7"
    ):
        raise SpecMismatch("G2c rotation certificate expression identity differs")
    if type(m) is not int or m != 32 or type(r) is not int or not 2 <= r <= 6:
        raise ControlFailureEvidence("G2c certificate dimensions are outside the frozen domain")
    variables = {
        "rho": _exact_float(rho), "sigma": _exact_float(sigma),
        "s_B": _exact_float(s_b), "a": _exact_float(a),
        "t": _exact_float(t), "b": _exact_float(b),
        "m": _F(m), "r": _F(r), "u": _U,
    }
    if variables["rho"] < 0 or variables["sigma"] < 0 or variables["s_B"] <= 0:
        raise ControlFailureEvidence("G2c certificate inputs are outside the frozen domain")
    domain_node = expression.get("domain_predicate")
    if not isinstance(domain_node, Mapping) or domain_node.get("kind") != "comparison":
        raise SpecMismatch("G2c certificate domain predicate is absent")
    common_mass = _evaluate_expression(domain_node["left"], variables)
    if common_mass <= 0:
        return {
            "reason": "NONPOSITIVE_COMMON_MASS_LOWER",
            "certificate_common_mass_lower": _downward(common_mass),
            "certificate_component": None,
            "certificate_dtv": None,
        }
    component = _evaluate_expression(expression["E_comp"], variables)
    dtv = _evaluate_expression(expression["E_dtv"], variables)
    return {
        "reason": None,
        "certificate_common_mass_lower": _downward(common_mass),
        "certificate_component": _upward(component),
        "certificate_dtv": _upward(dtv),
    }
