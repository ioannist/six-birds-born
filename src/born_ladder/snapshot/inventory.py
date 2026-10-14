"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from born_ladder.snapshot.errors import GridInventoryMismatch
from born_ladder.snapshot.frozen_spec import FrozenSpec, sha256_bytes

_AUTHORIZATION_TOKEN = object()


import argparse
import json
import subprocess
import sys
from born_ladder.snapshot.errors import Rebuild1Error
from born_ladder.snapshot.frozen_spec import canonical_json_bytes

class InventoryAuthorization:
    """Independently cross-checked record that all three inventory channels agree."""

    def __init__(
        self,
        *,
        report: dict[str, Any],
        spec_hash: str,
        token: object,
    ) -> None:
        if token is not _AUTHORIZATION_TOKEN:
            raise GridInventoryMismatch("inventory authorization was not runner-derived")
        self._report = report
        self._spec_hash = spec_hash

    @property
    def report(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._report))

    def require_for(self, spec: FrozenSpec) -> None:
        if self._spec_hash != spec.attestation.json_sha256:
            raise GridInventoryMismatch("inventory authorization targets another spec")
        equality_fields = (
            "source_equals_frozen",
            "runner_equals_source",
            "runner_equals_frozen",
        )
        if any(self._report.get(field) is not True for field in equality_fields):
            raise GridInventoryMismatch("campaign lacks measured three-way equality")




@dataclass(frozen=True)
class RustFunction:
    name: str
    text: str
    first_line: int
    last_line: int
    sha256: str


def _matching_rust_brace(text: str, opening: int) -> int:
    depth = 0
    state = "code"
    block_depth = 0
    index = opening
    while index < len(text):
        char = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if state == "code":
            if char == "/" and following == "/":
                state = "line_comment"
                index += 2
                continue
            if char == "/" and following == "*":
                state = "block_comment"
                block_depth = 1
                index += 2
                continue
            if char == '"':
                state = "string"
            elif char == "'":
                state = "char"
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return index
        elif state == "line_comment":
            if char == "\n":
                state = "code"
        elif state == "block_comment":
            if char == "/" and following == "*":
                block_depth += 1
                index += 2
                continue
            if char == "*" and following == "/":
                block_depth -= 1
                index += 2
                if block_depth == 0:
                    state = "code"
                continue
        elif state in {"string", "char"}:
            terminator = '"' if state == "string" else "'"
            if char == "\\":
                index += 2
                continue
            if char == terminator:
                state = "code"
        index += 1
    raise GridInventoryMismatch("unterminated Rust function body")


def extract_rust_function(source: str, name: str) -> RustFunction:
    matches = list(re.finditer(rf"(?m)^fn\s+{re.escape(name)}\s*\(", source))
    if len(matches) != 1:
        raise GridInventoryMismatch(
            f"expected one Rust item named {name}, found {len(matches)}"
        )
    start = matches[0].start()
    opening = source.find("{", matches[0].end())
    if opening < 0:
        raise GridInventoryMismatch(f"Rust item {name} has no body")
    closing = _matching_rust_brace(source, opening)
    end = closing + 1
    if end < len(source) and source[end] == "\n":
        end += 1
    function_text = source[start:end]
    first_line = source.count("\n", 0, start) + 1
    last_line = source.count("\n", 0, closing) + 1
    return RustFunction(
        name=name,
        text=function_text,
        first_line=first_line,
        last_line=last_line,
        sha256=sha256_bytes(function_text.encode("utf-8")),
    )


def parse_exp112_labels(function_text: str) -> list[str]:
    marker = "let configs: Vec<(&str, PicaConfig)> = vec!["
    start = function_text.find(marker)
    if start < 0 or function_text.find(marker, start + 1) >= 0:
        raise GridInventoryMismatch("EXP-112 must contain exactly one typed configs vector")
    body_start = start + len(marker)
    terminator = "\n    ];"
    body_end = function_text.find(terminator, body_start)
    if body_end < 0:
        raise GridInventoryMismatch("EXP-112 configs vector terminator not found")
    body = function_text[body_start:body_end]
    labels = re.findall(r'(?m)^\s*\("([A-Za-z0-9_]+)",', body)
    if len(labels) != len(set(labels)):
        raise GridInventoryMismatch("duplicate label in EXP-112 configs vector")
    return labels


def verify_definition_identities(
    spec: FrozenSpec, source_path: Path
) -> dict[str, RustFunction]:
    try:
        source_bytes = source_path.read_bytes()
        source = source_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise GridInventoryMismatch(f"cannot read runner source: {error}") from error
    expected_source_hash = spec.get(
        "/provenance/candidate_pins/runner_source_sha256",
        expected_type=str,
    )
    if sha256_bytes(source_bytes) != expected_source_hash:
        raise GridInventoryMismatch("runner source SHA-256 disagrees with frozen payload")

    identities: dict[str, RustFunction] = {}
    definitions = spec.get("/grid/definition_identities", expected_type=list)
    for definition in definitions:
        experiment = definition["experiment"]
        item_name = "run_" + experiment.lower().replace("-", "_")
        function = extract_rust_function(source, item_name)
        expected_lines = definition["inclusive_lines"]
        if [function.first_line, function.last_line] != expected_lines:
            raise GridInventoryMismatch(
                f"{experiment} relocated lines {[function.first_line, function.last_line]} "
                f"disagree with frozen {expected_lines}"
            )
        if function.sha256 != definition["sha256"]:
            raise GridInventoryMismatch(
                f"{experiment} function SHA-256 disagrees with frozen payload"
            )
        identities[experiment] = function
    return identities


def verify_inventory_receipt(spec, *, report_path, report_sha256, source_path):
    """Read a committed historical receipt; never execute or authorize a runner.

    The caller's receipt commitment must come from the committed data record.
    This checks recorded runner incidence plus independently parsed source and
    frozen labels; it does not claim new source/build correspondence.
    """
    import json
    raw=Path(report_path).read_bytes()
    if sha256_bytes(raw)!=report_sha256:
        raise GridInventoryMismatch("historical inventory receipt commitment differs")
    report=json.loads(raw)
    definitions=verify_definition_identities(spec,Path(source_path))
    labels=parse_exp112_labels(definitions["EXP-112"].text)
    pins=spec.get("/provenance/candidate_pins",expected_type=dict)
    if (report["labels"]!=labels or labels!=spec.get("/grid/labels",expected_type=list)
        or report["labels_count"]!=len(labels)
        or report["runner_sha256"]!=pins["runner_binary_sha256"]
        or report["source_sha256"]!=pins["runner_source_sha256"]
        or report["inventory_stdout_sha256"]!=sha256_bytes(("\n".join(labels)+"\n").encode())
        or report["definition_sha256"]!={k:v.sha256 for k,v in definitions.items()}
        or report["independent_runner_mode"]!="LIVE_RUNNER_MATCH"):
        raise GridInventoryMismatch("historical inventory/source/frozen incidence differs")
    authorization=InventoryAuthorization(report=report,spec_hash=spec.attestation.json_sha256,token=_AUTHORIZATION_TOKEN)
    authorization.require_for(spec)
    return authorization

# Production writers restored from the same historical implementation.

_IMPLEMENTATION_POINTERS = {"grid_contract": "/grid"}

def build_inventory(
    spec: FrozenSpec,
    source_path: Path,
    *,
    runner_path: Path,
    implementation_manifest_path: Path | None = None,
) -> InventoryAuthorization:
    spec.audit_implementation_manifest(
        "inventory", manifest_path=implementation_manifest_path,
        declared_pointers=_IMPLEMENTATION_POINTERS,
    )
    identities = verify_definition_identities(spec, source_path)
    source_labels = parse_exp112_labels(identities["EXP-112"].text)
    frozen_labels = spec.get("/grid/labels", expected_type=list)
    frozen_count = spec.get("/grid/labels_count", expected_type=int)
    if source_labels != frozen_labels or len(source_labels) != frozen_count:
        raise GridInventoryMismatch(
            "source EXP-112 label order/count disagrees with frozen inventory"
        )
    pins = spec.get("/provenance/candidate_pins", expected_type=dict)
    try:
        runner_bytes = runner_path.read_bytes()
    except OSError as error:
        raise GridInventoryMismatch(f"runner inventory unavailable: {error}") from error
    runner_sha256 = sha256_bytes(runner_bytes)
    if runner_sha256 != pins["runner_binary_sha256"]:
        raise GridInventoryMismatch("runner inventory binary SHA-256 disagrees")
    try:
        completed = subprocess.run(
            [str(runner_path), "--list-configs", "EXP-112"],
            cwd=spec.repo_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise GridInventoryMismatch(f"runner inventory unavailable: {error}") from error
    if completed.returncode != 0:
        raise GridInventoryMismatch(
            f"runner inventory exited {completed.returncode}: "
            f"{completed.stderr.decode('utf-8', errors='replace').strip()}"
        )
    if completed.stderr:
        raise GridInventoryMismatch("runner inventory emitted unexpected stderr")
    if not completed.stdout.endswith(b"\n"):
        raise GridInventoryMismatch("runner inventory stdout lacks final LF")
    try:
        runner_labels = completed.stdout.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise GridInventoryMismatch("runner inventory is not UTF-8") from error
    if not runner_labels or any(not label for label in runner_labels):
        raise GridInventoryMismatch("runner inventory contains an empty/missing line")
    if runner_labels != source_labels:
        raise GridInventoryMismatch(
            "live runner inventory disagrees with source and frozen inventory"
        )
    report = {
        "definition_sha256": {
            experiment: function.sha256
            for experiment, function in identities.items()
        },
        "independent_runner_mode": "LIVE_RUNNER_MATCH",
        "inventory_stdout_sha256": sha256_bytes(completed.stdout),
        "labels": source_labels,
        "labels_count": len(source_labels),
        "source": str(source_path),
        "source_sha256": sha256_bytes(source_path.read_bytes()),
        "runner": str(runner_path),
        "runner_equals_frozen": runner_labels == frozen_labels,
        "runner_equals_source": runner_labels == source_labels,
        "runner_sha256": runner_sha256,
        "source_equals_frozen": source_labels == frozen_labels,
    }
    return InventoryAuthorization(
        report=report,
        spec_hash=spec.attestation.json_sha256,
        token=_AUTHORIZATION_TOKEN,
    )
