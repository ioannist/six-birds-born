"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import hashlib
import math
from typing import Any, Mapping, Sequence
from born_ladder.snapshot.errors import ControlFailureEvidence, IncompleteCampaign, SpecMismatch
from born_ladder.snapshot.g2a import _bca_summary
from born_ladder.snapshot.rng import RNGStream, typed_frame

def _scaled_binary64_integers(values: Sequence[float]) -> tuple[int, ...]:
    """Represent finite binary64 values over one exact power-of-two denominator."""
    if not values or not all(math.isfinite(float(value)) for value in values):
        raise IncompleteCampaign("G2H sign-randomization input is empty or nonfinite")
    ratios = [float(value).as_integer_ratio() for value in values]
    denominator = max(item[1] for item in ratios)
    return tuple(numerator * (denominator // item_denominator)
                 for numerator, item_denominator in ratios)


def _conditional_sign_counts(values: Sequence[float]) -> tuple[int, int, int]:
    """Count exact binary64 sign assignments, including every boundary tie."""
    integers = _scaled_binary64_integers(values)
    observed = sum(integers)
    signed = -observed
    previous_gray = 0
    one_sided = int(signed >= observed)
    two_sided = int(abs(signed) >= abs(observed))
    denominator = 1 << len(integers)
    for assignment in range(1, denominator):
        gray = assignment ^ (assignment >> 1)
        changed = gray ^ previous_gray
        index = changed.bit_length() - 1
        delta = 2 * integers[index]
        signed += delta if gray & changed else -delta
        one_sided += signed >= observed
        two_sided += abs(signed) >= abs(observed)
        previous_gray = gray
    return two_sided, one_sided, denominator


def _conditional_sign_p_exact(values: Sequence[float]) -> tuple[float, float]:
    two_sided, one_sided, denominator = _conditional_sign_counts(values)
    return two_sided / denominator, one_sided / denominator


def _validate_bootstrap_rng_audit(
    record: Mapping[str, Any], *, shape: Mapping[str, Any],
    expected_replicate_index: int, expected_fields: Sequence[Mapping[str, str]],
    expected_master_key: str, expected_highest_counter: int,
    expected_implementation_version: str,
) -> dict[str, Any]:
    """Validate one retained v16 bootstrap audit against its closed descriptor."""
    from born_ladder.snapshot.universal_shapes import _validate_descriptor

    descriptor = {
        "kind": "object",
        "keys": shape["keys"],
        "properties": shape["field_shapes"],
    }
    checked = _validate_descriptor(
        record, descriptor, path="bootstrap.rng_audit",
        dimensions={}, content_root=None,
    )
    expected = {
        "replicate_index": expected_replicate_index,
        "framed_rng_fields": list(expected_fields),
        "master_key_sha256": expected_master_key,
        "highest_counter": expected_highest_counter,
        "implementation_version": expected_implementation_version,
    }
    if checked != expected:
        raise ControlFailureEvidence("G2H bootstrap RNG audit disagrees with its retained stream")
    return checked


def _bootstrap_rng_audit_v16(
    *, stage_id: str, statistic_id: str, replicate_index: int,
    key: bytes, stream: RNGStream, rng_contract: Mapping[str, Any],
    attested_json_sha256: str, shape: Mapping[str, Any],
    implementation_version: str,
) -> dict[str, Any]:
    descriptors = rng_contract["algorithms"]["bootstrap"]["key_fields"]
    semantic = [
        ("str", "string", "bootstrap-v2".encode("utf-8"), "bootstrap-v2"),
        (
            "bytes",
            "bytes",
            bytes.fromhex(attested_json_sha256),
            bytes.fromhex(attested_json_sha256),
        ),
        ("str", "string", stage_id.encode("utf-8"), stage_id),
        ("str", "string", statistic_id.encode("utf-8"), statistic_id),
        ("u64", "u64", replicate_index.to_bytes(8, "big"), replicate_index),
    ]
    if descriptors != [
        "str:bootstrap-v2", "bytes:attested JSON SHA-256", "str:stage_id",
        "str:statistic_id", "u64:replicate_index",
    ]:
        raise SpecMismatch("frozen G2H bootstrap RNG fields disagree")
    framed_fields = [
        {"type_tag": persisted_type, "raw_hex": raw.hex()}
        for _, persisted_type, raw, _ in semantic
    ]
    derived = hashlib.sha256(
        typed_frame("str", implementation_version)
        + b"".join(typed_frame(frame_type, value) for frame_type, _, _, value in semantic)
    ).digest()
    if derived != key or stream.counter < 1:
        raise ControlFailureEvidence("G2H bootstrap RNG audit key or counter disagrees")
    record = {
        "replicate_index": replicate_index,
        "framed_rng_fields": framed_fields,
        "master_key_sha256": key.hex(),
        "highest_counter": stream.counter - 1,
        "implementation_version": implementation_version,
    }
    return _validate_bootstrap_rng_audit(
        record, shape=shape, expected_replicate_index=replicate_index,
        expected_fields=framed_fields, expected_master_key=key.hex(),
        expected_highest_counter=stream.counter - 1,
        expected_implementation_version=implementation_version,
    )
