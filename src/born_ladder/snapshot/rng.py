"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from born_ladder.snapshot.errors import IncompleteCampaign, SpecMismatch
from born_ladder.snapshot.frozen_spec import FrozenSpec

_LITERAL_STRINGS = {"H1", "H2", "G2S_DOSE", "bootstrap-v2"}


_IMPLEMENTATION_POINTERS = {"rng_contract": "/rng"}



def uint64_be(value: int) -> bytes:
    if type(value) is not int or not 0 <= value < 2**64:
        raise IncompleteCampaign("RNG u64 value is outside [0,2^64)")
    return value.to_bytes(8, "big", signed=False)


def typed_frame(kind: str, value: str | int | bytes) -> bytes:
    tags = {"str": b"\x01", "u64": b"\x02", "bytes": b"\x03"}
    if kind not in tags:
        raise IncompleteCampaign(f"unknown RNG frame type {kind!r}")
    if kind == "str":
        if not isinstance(value, str):
            raise IncompleteCampaign("RNG string frame requires str")
        try:
            raw = value.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise IncompleteCampaign("RNG string is not strict UTF-8") from error
    elif kind == "u64":
        raw = uint64_be(value)  # type: ignore[arg-type]
    else:
        if not isinstance(value, bytes):
            raise IncompleteCampaign("RNG bytes frame requires bytes")
        raw = value
    return tags[kind] + uint64_be(len(raw)) + raw


def master_key(prefix: str, fields: list[tuple[str, str | int | bytes]]) -> bytes:
    framed = typed_frame("str", prefix)
    framed += b"".join(typed_frame(kind, value) for kind, value in fields)
    return hashlib.sha256(framed).digest()


def _derive_from_contract(
    spec: FrozenSpec,
    contract: Mapping[str, Any],
    algorithm: str,
    values: Mapping[str, str | int],
) -> bytes:
    algorithms = contract["algorithms"]
    if algorithm not in algorithms:
        raise IncompleteCampaign(f"unknown frozen RNG algorithm {algorithm!r}")
    descriptors = algorithms[algorithm]["key_fields"]
    fields: list[tuple[str, str | int | bytes]] = []
    consumed: set[str] = set()
    for descriptor in descriptors:
        kind, name = descriptor.split(":", 1)
        if kind == "bytes" and name == "attested JSON SHA-256":
            value: str | int | bytes = bytes.fromhex(spec.attestation.json_sha256)
        elif kind == "str" and name in _LITERAL_STRINGS:
            value = name
        else:
            if name not in values:
                raise IncompleteCampaign(f"RNG key field {name!r} is missing")
            value = values[name]
            consumed.add(name)
        fields.append((kind, value))
    unknown = sorted(set(values) - consumed)
    if unknown:
        raise IncompleteCampaign(f"unknown RNG key fields {unknown}")
    prefix = contract["framing"]["master_prefix"]
    if prefix != getattr(spec, 'rng_master_prefix', "RB1v2-RNG-v1"):
        raise SpecMismatch("unsupported frozen RNG master prefix")
    return master_key(prefix, fields)


def key_deriver(
    spec: FrozenSpec, *, implementation_manifest_path=None
) -> Callable[[str, Mapping[str, str | int]], bytes]:
    """Audit the frozen RNG contract once and return a read-only key derivation closure."""
    spec.audit_implementation_manifest(
        "rng", manifest_path=implementation_manifest_path,
        declared_pointers=_IMPLEMENTATION_POINTERS,
    )
    contract = spec.get("/rng", expected_type=dict)

    def derive(algorithm: str, values: Mapping[str, str | int]) -> bytes:
        return _derive_from_contract(spec, contract, algorithm, values)

    return derive


@dataclass
class RNGStream:
    master: bytes

    counter: int = 0

    _buffer: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.master, bytes) or len(self.master) != 32:
            raise IncompleteCampaign("RNG master key must be 32 bytes")
        if type(self.counter) is not int or self.counter < 0:
            raise IncompleteCampaign("RNG counter must be nonnegative")

    def _expand(self) -> None:
        digest = hashlib.sha256(self.master + uint64_be(self.counter)).digest()
        self.counter += 1
        self._buffer.extend(
            int.from_bytes(digest[offset : offset + 8], "big")
            for offset in range(0, 32, 8)
        )

    def word(self) -> int:
        if not self._buffer:
            self._expand()
        return self._buffer.pop(0)

    def uniform(self) -> float:
        return (self.word() + 0.5) / 2**64

    def normal_pair(self) -> tuple[float, float]:
        u1 = self.uniform()
        u2 = self.uniform()
        radius = math.sqrt(-2.0 * math.log(u1))
        angle = 2.0 * math.pi * u2
        return radius * math.cos(angle), radius * math.sin(angle)

    def unbiased_index(self, bound: int) -> int:
        if type(bound) is not int or not 1 <= bound <= 2**64:
            raise IncompleteCampaign("RNG permutation bound is outside [1,2^64]")
        threshold = (2**64 // bound) * bound
        while True:
            word = self.word()
            if word < threshold:
                return word % bound

# Production writers restored from the same historical implementation.

def derive_master_key(
    spec: FrozenSpec,
    algorithm: str,
    values: Mapping[str, str | int],
    *,
    implementation_manifest_path=None,
) -> bytes:
    spec.audit_implementation_manifest(
        "rng", manifest_path=implementation_manifest_path,
        declared_pointers=_IMPLEMENTATION_POINTERS,
    )
    contract = spec.get("/rng", expected_type=dict)
    return _derive_from_contract(spec, contract, algorithm, values)

def h2_permutation(stream: RNGStream, size: int) -> list[int]:
    if type(size) is not int or size < 1:
        raise IncompleteCampaign("H2 permutation size must be positive")
    values = list(range(size))
    for index in range(size - 1, 0, -1):
        selected = stream.unbiased_index(index + 1)
        values[index], values[selected] = values[selected], values[index]
    return values
