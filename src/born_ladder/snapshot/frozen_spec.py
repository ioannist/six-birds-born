"""Read-only historical verification and archived-law helpers."""
from __future__ import annotations
import copy
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from born_ladder.snapshot.historical import HistoricalInputs
from born_ladder.snapshot.errors import IncompleteCampaign, SpecMismatch

_MISSING = object()


_CONSTRUCTION_TOKEN = object()


_HEX40 = re.compile(r"^[0-9a-f]{40}$")


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


FROZEN_COMPANION = "born_route_rebuild1_spec_v24.json"


FROZEN_SPEC_ID = "born-route-rebuild1.v24"


FROZEN_TAG = "born-route-rebuild1-v24-freeze"


FROZEN_JSON_SHA256 = "ba641075c7a3d38a4273172a99e0e92e2927b7acdeb9124886227f5077b61fac"


FROZEN_SELF_SHA256 = "86289edbf290d61ecb8c29780354f64c349135772587478557b4b770b979e10f"


_V23_PUBLICATION_COMPANION = "born_route_rebuild1_spec_v23.json"


_V23_PUBLICATION_SPEC_ID = "born-route-rebuild1.v23"


_V23_PUBLICATION_TAG = "born-route-rebuild1-v23-freeze"


_V23_PUBLICATION_JSON_SHA256 = "7deaeacfe9a2d403030df6c5115afc567d99fde9ff4e07a131a90d91c80b22b8"


_V23_PUBLICATION_SELF_SHA256 = "f9955b5fc424b8aef49d4f0afc50583dbaccf25be09eb7638b2360237cb4604a"


_V23_PUBLICATION_FREEZE_COMMIT = "173c24fb89ef1db0052bdd80e07c915ff86a89de"


_V22_PUBLICATION_COMPANION = "born_route_rebuild1_spec_v22.json"


_V22_PUBLICATION_SPEC_ID = "born-route-rebuild1.v22"


_V22_PUBLICATION_TAG = "born-route-rebuild1-v22-freeze"


_V22_PUBLICATION_JSON_SHA256 = "e7c8ccbd71123354413bcc39d649cd1afcc34c2f716d33ff6ff5c68ed64bfd01"


_V22_PUBLICATION_SELF_SHA256 = "bef9ec230c2ac9f49489b79dc9eedc8afb6977f462cc2849b66c4e13bb48c527"


_V22_PUBLICATION_FREEZE_COMMIT = "8b00c44951c53e6c027f1c651ef70e9aa9f8f96a"


_V21_G2C_COMPANION = "born_route_rebuild1_spec_v21.json"


_V21_G2C_SPEC_ID = "born-route-rebuild1.v21"


_V21_G2C_TAG = "born-route-rebuild1-v21-freeze"


_V21_G2C_JSON_SHA256 = "65a50c9e56f4aa4ce30478b46463adcf0c46ab4c5c12db821e66b66a9019f39d"


_V21_G2C_SELF_SHA256 = "693dac0f24cccb57424cc64109481b213381fbfe38e8c230e64cc0d2400bc410"


_V21_G2C_FREEZE_COMMIT = "e83e32ff982bf26dd058a6a0332c7bedb6fbe1d9"


_V20_G2X_IMPLEMENTATION_SHA256 = (
    "fd72f357f850613e89a040c2624ccfc08c9244f3896e6092caa8e9f5bbc19f6f"
)


_V8_REPLAY_COMPANION = "born_route_rebuild1_spec_v8.json"


_V8_REPLAY_SPEC_ID = "born-route-rebuild1.v8"


_V8_REPLAY_TAG = "born-route-rebuild1-v8-freeze"


_V8_REPLAY_JSON_SHA256 = "8eee39e3da7044a0bca1ea26b815fbf3aadb3024e2b334ae0a8d577047ba2512"


_V8_REPLAY_SELF_SHA256 = "7799865e3b686f8e48bfd89ff04297e39ca5387faccac2902aad1753a2269f03"


_V8_REPLAY_IMPLEMENTATION_COMMIT = "ccd7f7c53a499c1f7ed7e9892ce39441ebd98e39"


_V8_REPLAY_IMPLEMENTATION_SHA256 = "b9e868069fabb7441dfa46e8d934415c947a44e66b6403e6d734b4ee61fff459"


_V8_REPLAY_RNG_SHA256 = "86aad67cbfd96e56ed7b5335db5ed0af5d6591207a97b7ed00503e42537e1a73"


IMPLEMENTATION_MANIFEST = Path("scripts/rebuild1/implementation_manifest.jsonl")


_MANIFEST_FIELDS = {
    "consumer",
    "expected_type",
    "ordinal",
    "pointer",
    "source_path",
    "source_sha256",
    "symbol",
    "value_sha256",
}


_MANIFEST_TYPES: dict[str, type[Any]] = {
    "bool": bool,
    "dict": dict,
    "float": float,
    "int": int,
    "list": list,
    "str": str,
}


_REQUIRED_INFRA_CONSUMERS = {
    "artifact_paths",
    "completeness",
    "collector_structural",
    "evidence",
    "frozen_spec",
    "identities",
    "inventory",
    "provenance",
    "rng",
    "runner_structural",
    "self_check",
    "status",
}


_V8_REPLAY_POINTER = "/comparison_policies/g2r/version_aware_replay"


_V17_SOURCE_POINTER = "/completeness/g2h_v17_sealed_input_route/source_identity"


_V18_SOURCE_POINTER = "/completeness/g2h_v18_sealed_input_route/source_identity"


_IMPLEMENTATION_POINTERS = {
    "identity_contract": "/identity",
    "version_aware_replay_contract": _V8_REPLAY_POINTER,
    "g2h_v17_source_identity": _V17_SOURCE_POINTER,
    "g2h_v18_source_identity": _V18_SOURCE_POINTER,
    "g2c_v24_sealed_route": "/completeness/g2c_v24_sealed_input_route",
}


_V8_REPLAY_CONTRACT = {
    "default_post_amendment_loader": "signed v23",
    "default_pin_repointing_preserves_v8_path": True,
    "g2a_builder_replay": {
        "bindings": [
            "attested JSON hash",
            "implementation manifest",
            "RNG identity",
        ],
        "companion": _V8_REPLAY_COMPANION,
        "spec_id": _V8_REPLAY_SPEC_ID,
        "tag": _V8_REPLAY_TAG,
    },
    "g2h_h3_routes": {
        "mixing_prohibited": True,
        "operative": (
            "accepted v13 H3 manifest only after independent review of a "
            "complete v13 evaluation"
        ),
        "v12_incomplete_history": "preserved immutable replay/history path",
    },
    "g2x_routes": {
        "caller_selectable": False,
        "historical_v19": "immutable incomplete history only",
        "mixing_prohibited": True,
        "operative_v20": "full dedicated re-execution only",
    },
    "g2c_routes": {
        "caller_selectable": False,
        "historical_v21": "immutable executed control-failure history and signed source identity",
        "historical_v22": "immutable never-executed publication contract; no authorization or guard existed",
        "mixing_prohibited": True,
        "operative_v23": "non-caller-selectable sealed-source reconstruction and distinct detached-completion publication only after adoption",
    },
    "other_post_v19_stages": "signed v23",
    "selection": "reproduction-plan-selected and not caller-selectable",
}


_TAG_FIELDS = (
    "spec_id",
    "freeze_commit",
    "markdown_sha256",
    "json_sha256",
    "manager",
    "reviewer_ruling",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_identity(path: Path) -> tuple[int, str]:
    if path.is_symlink() or not path.is_file():
        raise SpecMismatch(f"sealed input is not a regular nonsymlink file: {path}")
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
    except OSError as error:
        raise SpecMismatch(f"cannot read sealed input {path}: {error}") from error
    return size, digest.hexdigest()


def _verify_identity_row(root: Path, row: Mapping[str, Any], history=None) -> None:
    if set(row) != {"path", "role", "sha256", "size_bytes"}:
        raise SpecMismatch("sealed-input identity row is not closed")
    path = ((history.path(row["path"], expected_sha256=row["sha256"]) if history is not None and (row["path"] in history.manifest["files"] or row["path"]+"@"+row["sha256"] in history.manifest["files"]) else root / row["path"])).resolve()
    try:
        path.relative_to(history.root if history is not None and path.is_relative_to(history.root) else root)
    except ValueError as error:
        raise SpecMismatch("sealed-input identity path escapes repository") from error
    if _file_identity(path) != (row["size_bytes"], row["sha256"]):
        raise SpecMismatch(f"sealed-input identity disagrees for role {row['role']}")


def _verify_capture_inventory(root: Path, contract: Mapping[str, Any]) -> None:
    capture_root = (root / contract["root"]).resolve()
    if capture_root.is_symlink() or not capture_root.is_dir():
        raise SpecMismatch("sealed capture root is not a nonsymlink directory")
    rows: list[dict[str, Any]] = []
    type_counts = {"attempt_sidecar": 0, "stderr": 0, "stdout": 0}
    for path in sorted(
        capture_root.rglob("*"),
        key=lambda item: item.relative_to(capture_root).as_posix().encode("utf-8"),
    ):
        if path.is_symlink():
            raise SpecMismatch(f"sealed capture inventory contains a symlink: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise SpecMismatch(f"sealed capture inventory contains a non-file: {path}")
        relative = path.relative_to(capture_root).as_posix()
        size, digest = _file_identity(path)
        rows.append({"path": relative, "sha256": digest, "size_bytes": size})
        if relative.endswith(".attempt.json"):
            type_counts["attempt_sidecar"] += 1
        elif relative.endswith(".stderr.bin"):
            type_counts["stderr"] += 1
        elif relative.endswith(".stdout.bin"):
            type_counts["stdout"] += 1
        else:
            raise SpecMismatch(f"sealed capture has an unknown suffix: {relative}")
    inventory_sha = sha256_bytes(canonical_json_bytes(rows))
    summary = {
        "file_count": len(rows), "sha256": inventory_sha,
        "total_size_bytes": sum(row["size_bytes"] for row in rows),
        "type_counts": type_counts,
    }
    if (
        summary["file_count"] != contract["file_count"]
        or summary["total_size_bytes"] != contract["size_bytes"]
        or inventory_sha != contract["canonical_inventory_sha256"]
        or sha256_bytes(canonical_json_bytes(summary)) != contract["receipt_digest"]
    ):
        raise SpecMismatch("sealed capture inventory identity disagrees")


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise SpecMismatch(f"duplicate JSON object key {key!r}")
        value[key] = item
    return value






def _parse_annotation(contents: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in contents.splitlines():
        for field in _TAG_FIELDS:
            prefix = f"{field}: "
            if line.startswith(prefix):
                if field in fields:
                    raise SpecMismatch(f"duplicate signed-tag field {field}")
                fields[field] = line[len(prefix) :]
    if tuple(fields) != _TAG_FIELDS:
        missing = [field for field in _TAG_FIELDS if field not in fields]
        raise SpecMismatch(f"signed-tag fields missing or out of order: {missing}")
    if not _HEX40.fullmatch(fields["freeze_commit"]):
        raise SpecMismatch("freeze_commit is not 40 lowercase hexadecimal characters")
    for field in ("markdown_sha256", "json_sha256"):
        if not _HEX64.fullmatch(fields[field]):
            raise SpecMismatch(f"{field} is not 64 lowercase hexadecimal characters")
    return fields








def _resolve_pointer(payload: Any, pointer: str) -> Any:
    if pointer == "":
        return payload
    if not pointer.startswith("/"):
        raise SpecMismatch(f"invalid JSON Pointer {pointer!r}")
    current = payload
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                raise SpecMismatch(f"missing JSON Pointer {pointer}")
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit() or int(token) >= len(current):
                raise SpecMismatch(f"missing JSON Pointer {pointer}")
            current = current[int(token)]
        else:
            raise SpecMismatch(f"JSON Pointer traverses a scalar: {pointer}")
    return current


@dataclass(frozen=True)
class FrozenAttestation:
    tag: str

    freeze_commit: str

    spec_id: str

    markdown_sha256: str

    json_sha256: str

    manager: str

    reviewer_ruling_path: str

    reviewer_ruling_sha256: str

    verification_output: str



class FrozenSpec:
    """Verified frozen payload with a fail-closed JSON-pointer accessor."""

    def __init__(
        self,
        *,
        payload: dict[str, Any],
        raw_bytes: bytes,
        path: Path,
        repo_root: Path,
        attestation: FrozenAttestation,
        loader_role: str,
        construction_token: object,
    ) -> None:
        if construction_token is not _CONSTRUCTION_TOKEN:
            raise SpecMismatch("FrozenSpec construction requires signed attestation")
        self._payload = payload
        self.history = None
        self.raw_bytes = raw_bytes
        self.path = path
        self.repo_root = repo_root
        self.attestation = attestation
        self.loader_role = loader_role
        self._implementation_manifest_sha256 = ""
        self._replay_implementation_manifest_raw: bytes | None = None
        self._replay_implementation_manifest_sha256: str | None = None
        self._wrapper_implementation_manifest_sha256: str | None = None
        self._replay_rng_sha256: str | None = None
        self._implementation_binding_spec: FrozenSpec | None = None
        self._implementation_audit_cache: dict[
            tuple[str, str, str, str | None, tuple[tuple[str, str], ...] | None],
            str,
        ] = {}

    @classmethod
    def load(cls, spec_path: Path | str, *, repo_root: Path | str, historical_root: Path | str | None = None) -> "FrozenSpec":
        """Load only the default v24 payload and verify its signed freeze identity."""
        return cls._load_attested(
            spec_path,
            repo_root=repo_root,
            historical_root=historical_root,
            expected_companion=FROZEN_COMPANION,
            expected_spec_id=FROZEN_SPEC_ID,
            expected_tag=FROZEN_TAG,
            expected_json_sha256=FROZEN_JSON_SHA256,
            expected_self_sha256=FROZEN_SELF_SHA256,
            require_checked_out_markdown=True,
            loader_role="default",
        )

    @classmethod
    def load_g2r_g2a_replay(cls, *, repo_root: Path | str, historical_root: Path | str | None = None) -> "FrozenSpec":
        """Load the fixed v8 G2a replay identity selected by the G2r plan."""
        root = Path(repo_root).resolve()
        history = HistoricalInputs(historical_root)
        default = cls.load(history.path(FROZEN_COMPANION), repo_root=root, historical_root=history.root)
        default.get(
            _V8_REPLAY_POINTER,
            expected=_V8_REPLAY_CONTRACT,
            expected_type=dict,
        )
        replay = cls._load_attested(
            history.path(_V8_REPLAY_COMPANION),
            repo_root=root,
            historical_root=historical_root,
            expected_companion=_V8_REPLAY_COMPANION,
            expected_spec_id=_V8_REPLAY_SPEC_ID,
            expected_tag=_V8_REPLAY_TAG,
            expected_json_sha256=_V8_REPLAY_JSON_SHA256,
            expected_self_sha256=_V8_REPLAY_SELF_SHA256,
            require_checked_out_markdown=False,
            loader_role="g2r_g2a_replay",
        )
        historical_manifest = history.commit_bytes(
            _V8_REPLAY_IMPLEMENTATION_COMMIT,
            IMPLEMENTATION_MANIFEST.as_posix(),
        )
        if sha256_bytes(historical_manifest) != _V8_REPLAY_IMPLEMENTATION_SHA256:
            raise SpecMismatch("v8 replay implementation manifest SHA-256 disagrees")
        replay._replay_implementation_manifest_raw = historical_manifest
        replay._replay_implementation_manifest_sha256 = (
            _V8_REPLAY_IMPLEMENTATION_SHA256
        )
        replay._wrapper_implementation_manifest_sha256 = (
            default.implementation_manifest_sha256
        )
        replay._replay_rng_sha256 = sha256_bytes(
            canonical_json_bytes(replay.get("/rng", expected_type=dict))
        )
        if replay._replay_rng_sha256 != _V8_REPLAY_RNG_SHA256:
            raise SpecMismatch("v8 replay RNG identity SHA-256 disagrees")
        return replay

    @classmethod
    def load_g2c_v22_sealed_source(cls, *, repo_root: Path | str, historical_root: Path | str | None = None) -> "FrozenSpec":
        """Load the fixed signed-v22 publication contract as immutable history."""
        root = Path(repo_root).resolve()
        history = HistoricalInputs(historical_root)
        default = cls.load(history.path(FROZEN_COMPANION), repo_root=root, historical_root=history.root)
        preserved = default.get(
            "/artifact_paths/prior_freeze_identities_preserved", expected_type=list
        )
        if preserved.count({
            "companion": _V22_PUBLICATION_COMPANION,
            "tag": _V22_PUBLICATION_TAG,
        }) != 1:
            raise SpecMismatch("v22 G2c publication history is not uniquely preserved")
        current = cls._load_attested(
            history.path(_V22_PUBLICATION_COMPANION),
            repo_root=root,
            historical_root=historical_root,
            expected_companion=_V22_PUBLICATION_COMPANION,
            expected_spec_id=_V22_PUBLICATION_SPEC_ID,
            expected_tag=_V22_PUBLICATION_TAG,
            expected_json_sha256=_V22_PUBLICATION_JSON_SHA256,
            expected_self_sha256=_V22_PUBLICATION_SELF_SHA256,
            require_checked_out_markdown=False,
            loader_role="g2c_v22_publication_history",
        )
        if current.attestation.freeze_commit != _V22_PUBLICATION_FREEZE_COMMIT:
            raise SpecMismatch("v22 G2c publication-history freeze commit disagrees")
        current._implementation_manifest_sha256 = default.implementation_manifest_sha256
        current._implementation_binding_spec = default
        return cls._load_g2c_sealed_source(
            current=current,
            route_pointer="/completeness/g2c_v22_sealed_input_route",
            route_version="v22",
        )

    @classmethod
    def load_g2c_v23_sealed_source(cls, *, repo_root: Path | str, historical_root: Path | str | None = None) -> "FrozenSpec":
        """Load the fixed signed-v23 publication contract as immutable history."""
        root = Path(repo_root).resolve()
        history = HistoricalInputs(historical_root)
        default = cls.load(history.path(FROZEN_COMPANION), repo_root=root, historical_root=history.root)
        preserved = default.get(
            "/artifact_paths/prior_freeze_identities_preserved", expected_type=list
        )
        if preserved.count({
            "companion": _V23_PUBLICATION_COMPANION,
            "tag": _V23_PUBLICATION_TAG,
        }) != 1:
            raise SpecMismatch("v23 G2c publication history is not uniquely preserved")
        current = cls._load_attested(
            history.path(_V23_PUBLICATION_COMPANION),
            repo_root=root,
            historical_root=historical_root,
            expected_companion=_V23_PUBLICATION_COMPANION,
            expected_spec_id=_V23_PUBLICATION_SPEC_ID,
            expected_tag=_V23_PUBLICATION_TAG,
            expected_json_sha256=_V23_PUBLICATION_JSON_SHA256,
            expected_self_sha256=_V23_PUBLICATION_SELF_SHA256,
            require_checked_out_markdown=False,
            loader_role="g2c_v23_publication_history",
        )
        if current.attestation.freeze_commit != _V23_PUBLICATION_FREEZE_COMMIT:
            raise SpecMismatch("v23 G2c publication-history freeze commit disagrees")
        current._implementation_manifest_sha256 = default.implementation_manifest_sha256
        current._implementation_binding_spec = default
        return cls._load_g2c_sealed_source(
            current=current,
            route_pointer="/completeness/g2c_v23_sealed_input_route",
            route_version="v23",
        )

    @classmethod
    def load_g2c_v24_sealed_source(cls, *, repo_root: Path | str, historical_root: Path | str | None = None) -> "FrozenSpec":
        """Load signed-v24 publication authority and its fixed signed-v21 source."""
        root = Path(repo_root).resolve()
        history = HistoricalInputs(historical_root)
        current = cls.load(history.path(FROZEN_COMPANION), repo_root=root, historical_root=history.root)
        return cls._load_g2c_sealed_source(
            current=current,
            route_pointer="/completeness/g2c_v24_sealed_input_route",
            route_version="v24",
        )

    @classmethod
    def _load_g2c_sealed_source(
        cls, *, current: "FrozenSpec", route_pointer: str, route_version: str,
    ) -> "FrozenSpec":
        """Verify one internally selected G2c sealed-source publication route."""
        root = current.repo_root
        history = current.history
        historical_root = history.root
        route = current.get(
            route_pointer, expected_type=dict
        )
        if route.get("caller_selectable") is not False:
            raise SpecMismatch(f"{route_version} G2c sealed-source route is caller-selectable")
        identity = route.get("source_identity")
        expected_identity = {
            "companion": _V21_G2C_COMPANION,
            "companion_sha256": _V21_G2C_JSON_SHA256,
            "companion_self_hash": _V21_G2C_SELF_SHA256,
            "freeze_commit": _V21_G2C_FREEZE_COMMIT,
            "spec_id": _V21_G2C_SPEC_ID,
            "tag": _V21_G2C_TAG,
        }
        if identity != expected_identity:
            raise SpecMismatch(f"{route_version} G2c sealed-source identity disagrees")
        source = cls._load_attested(
            history.path(_V21_G2C_COMPANION),
            repo_root=root,
            historical_root=historical_root,
            expected_companion=_V21_G2C_COMPANION,
            expected_spec_id=_V21_G2C_SPEC_ID,
            expected_tag=_V21_G2C_TAG,
            expected_json_sha256=_V21_G2C_JSON_SHA256,
            expected_self_sha256=_V21_G2C_SELF_SHA256,
            require_checked_out_markdown=False,
            loader_role=f"g2c_{route_version}_sealed_source",
        )
        if source.attestation.freeze_commit != _V21_G2C_FREEZE_COMMIT:
            raise SpecMismatch(f"{route_version} G2c source freeze commit disagrees")
        for collection in (
            route.get("input_bindings"),
            route.get("complete_dependency_closure"),
            route.get("reused_campaign_side_receipts"),
            route.get("source_outcome_evidence"),
        ):
            if type(collection) is not list:
                raise SpecMismatch(f"{route_version} G2c sealed-source identity collection is absent")
            seen_roles: set[str] = set()
            seen_paths: set[str] = set()
            for row in collection:
                if not isinstance(row, Mapping):
                    raise SpecMismatch(f"{route_version} G2c sealed-source identity row is malformed")
                if row.get("role") in seen_roles or row.get("path") in seen_paths:
                    raise SpecMismatch(f"{route_version} G2c sealed-source identity repeats")
                seen_roles.add(row["role"])
                seen_paths.add(row["path"])
                _verify_identity_row(root, row, history)
        historical_authorization = route.get("consumed_v21_evaluation_authorization")
        if not isinstance(historical_authorization, Mapping):
            raise SpecMismatch(f"{route_version} G2c historical evaluation authorization is absent")
        _verify_identity_row(root, historical_authorization, history)
        capture = route.get("capture_inventory")
        if not isinstance(capture, Mapping):
            raise SpecMismatch(f"{route_version} G2c capture inventory binding is absent")
        _verify_capture_inventory(root, capture)
        selector = route.get("recovery_resolution", {}).get("selectors", [None])[0]
        if not isinstance(selector, dict):
            raise SpecMismatch(f"{route_version} G2c historical recovery selector is absent")
        blob = selector.get("immutable_git_blob")
        if not isinstance(blob, dict) or selector.get("selector_order") != ["immutable_git_blob"]:
            raise SpecMismatch(f"{route_version} G2c recovery selector order disagrees")
        if route_version == "v24":
            graph_interpretation = route.get("recovery_resolution", {}).get("graph_interpretation")
            expected_interpretation = {
                "current_node_id": "current_implementation_manifest",
                "current_resolved_graph_location": ["filesystem", "canonical_resolved_absolute_destination"],
                "current_role": "current_implementation_manifest",
                "current_textual_path": IMPLEMENTATION_MANIFEST.as_posix(),
                "historical_node_id": "historical_implementation_manifest",
                "historical_resolved_graph_location": [
                    "immutable_git_blob", "bound_repository_root", blob.get("commit"),
                    blob.get("path"), blob.get("git_object_id_sha1"),
                ],
                "historical_role": "historical_implementation_manifest",
                "historical_textual_path": IMPLEMENTATION_MANIFEST.as_posix(),
                "same_path_exception": "exactly this historical/current pair; no other role, node ID, digest, selector, path or filesystem destination",
                "selector_pointer": "/completeness/g2c_v24_sealed_input_route/recovery_resolution/selectors/0",
                "validation_only_not_serialized": True,
            }
            if graph_interpretation != expected_interpretation:
                raise SpecMismatch("v24 G2c graph interpretation disagrees")
        try:
            recovered = history.commit_bytes(blob["commit"], blob["path"],
                expected_sha256=blob["sha256"], object_id=blob["git_object_id_sha1"])
            if (
                len(recovered) != blob["size_bytes"]
                or sha256_bytes(recovered) != blob["sha256"]
                or blob["sha256"] != selector["expected_sha256"]
                or len(recovered) != selector["expected_size_bytes"]
            ):
                raise SpecMismatch(
                    f"{route_version} G2c recovered implementation identity disagrees"
                )
        except (IncompleteCampaign, SpecMismatch) as error:
            # Recovery happens only after both publication and sealed-source
            # identities have been verified.  Retain those identities so the
            # CLI can realize the frozen G2c disposition without inventing
            # campaign, attempt, or guard evidence.
            current._g2c_source_spec = source
            error.g2c_verified_spec = current
            if route_version == "v22":
                error.g2c_v22_verified_spec = current
            elif route_version == "v23":
                error.g2c_v23_verified_spec = current
            else:
                error.g2c_v24_verified_spec = current
            raise
        source._replay_implementation_manifest_raw = recovered
        source._replay_implementation_manifest_sha256 = blob["sha256"]
        source.history = history
        source._wrapper_implementation_manifest_sha256 = current.implementation_manifest_sha256
        source._implementation_binding_spec = current
        current._g2c_source_spec = source
        current._g2c_sealed_route = copy.deepcopy(route)
        return current

    @classmethod
    def _load_attested(
        cls,
        spec_path: Path | str,
        *,
        repo_root: Path | str,
        historical_root: Path | str | None,
        expected_companion: str,
        expected_spec_id: str,
        expected_tag: str,
        expected_json_sha256: str,
        expected_self_sha256: str,
        require_checked_out_markdown: bool,
        loader_role: str,
    ) -> "FrozenSpec":
        """Load one internally selected signed identity."""
        path = Path(spec_path).resolve()
        root = Path(repo_root).resolve()
        history = HistoricalInputs(historical_root)
        expected_path = history.path(expected_companion, expected_sha256=expected_json_sha256)
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise SpecMismatch(f"cannot read explicit spec path {path}: {error}") from error
        if raw != expected_path.read_bytes():
            raise SpecMismatch("explicit payload differs from selected historical companion bytes")
        try:
            payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SpecMismatch(f"payload is not valid duplicate-free UTF-8 JSON: {error}") from error
        if not isinstance(payload, dict):
            raise SpecMismatch("payload root is not an object")
        if canonical_json_bytes(payload) != raw:
            raise SpecMismatch("payload bytes are not canonical sorted compact JSON with final LF")

        try:
            identity = payload["identity"]
            tag = identity["attestation"]["tag"]
            allowed_relative = identity["attestation"]["allowed_signers_path"]
            allowed_sha256 = identity["attestation"]["allowed_signers_sha256"]
            principal = identity["attestation"]["signer_principal"]
            public_key = identity["attestation"]["public_key"]
            spec_id = identity["spec_id"]
            self_hash = identity["json_sha256"]
        except (KeyError, TypeError) as error:
            raise SpecMismatch(f"payload identity contract is incomplete: {error}") from error
        if not all(
            isinstance(value, str)
            for value in (tag, allowed_relative, allowed_sha256, principal, public_key, spec_id, self_hash)
        ):
            raise SpecMismatch("payload identity fields have unexpected types")
        if spec_id != expected_spec_id or tag != expected_tag:
            raise SpecMismatch("payload is not the selected frozen identity")
        if self_hash != expected_self_sha256:
            raise SpecMismatch("payload self-hash is not the selected frozen identity")

        unhashed = copy.deepcopy(payload)
        del unhashed["identity"]["json_sha256"]
        if sha256_bytes(canonical_json_bytes(unhashed)) != self_hash:
            raise SpecMismatch("payload omit-field self-hash disagrees")

        allowed_path = history.path(allowed_relative, expected_sha256=allowed_sha256)
        try:
            allowed_path.relative_to(history.root)
        except ValueError as error:
            raise SpecMismatch("allowed-signers path escapes repository root") from error
        try:
            allowed_bytes = allowed_path.read_bytes()
        except OSError as error:
            raise SpecMismatch(f"cannot read allowed-signers file: {error}") from error
        if sha256_bytes(allowed_bytes) != allowed_sha256:
            raise SpecMismatch("allowed-signers SHA-256 disagrees with frozen payload")
        key_parts = public_key.split()
        if len(key_parts) < 2:
            raise SpecMismatch("frozen SSH public key is malformed")
        expected_allowed = f"{principal} {key_parts[0]} {key_parts[1]}\n".encode("utf-8")
        if allowed_bytes != expected_allowed:
            raise SpecMismatch("allowed-signers content is not the exact frozen principal and key")

        target, tag_contents, verification_output = history.verify_tag(tag, allowed_bytes, principal)
        annotation = _parse_annotation(tag_contents)
        if annotation["spec_id"] != spec_id:
            raise SpecMismatch("signed spec_id disagrees with payload")
        if target != annotation["freeze_commit"]:
            raise SpecMismatch("signed tag target disagrees with freeze_commit annotation")

        json_digest = sha256_bytes(raw)
        if json_digest != expected_json_sha256:
            raise SpecMismatch("JSON SHA-256 is not the selected frozen identity")
        frozen_markdown = history.commit_bytes(target, "born_route_rebuild1_spec.md")
        if require_checked_out_markdown:
            markdown_path = history.path("born_route_rebuild1_spec.md")
            try:
                markdown_bytes = markdown_path.read_bytes()
            except OSError as error:
                raise SpecMismatch(f"cannot read frozen Markdown: {error}") from error
        else:
            markdown_bytes = frozen_markdown
        markdown_digest = sha256_bytes(markdown_bytes)
        if json_digest != annotation["json_sha256"]:
            raise SpecMismatch("JSON SHA-256 disagrees with signed attestation")
        if markdown_digest != annotation["markdown_sha256"]:
            raise SpecMismatch("Markdown SHA-256 disagrees with signed attestation")

        frozen_json = history.commit_bytes(target, expected_companion)
        frozen_allowed = history.commit_bytes(target, allowed_relative)
        if frozen_json != raw or frozen_markdown != markdown_bytes or frozen_allowed != allowed_bytes:
            raise SpecMismatch("checked-out frozen payload bytes disagree with signed commit")

        reviewer_parts = annotation["reviewer_ruling"].rsplit(" ", 1)
        if len(reviewer_parts) != 2 or not _HEX64.fullmatch(reviewer_parts[1]):
            raise SpecMismatch("reviewer_ruling annotation is malformed")
        reviewer_path, reviewer_sha256 = reviewer_parts
        if sha256_bytes(history.commit_bytes(target, reviewer_path)) != reviewer_sha256:
            raise SpecMismatch("reviewer ruling hash disagrees with signed attestation")

        verified = cls(
            payload=payload,
            raw_bytes=raw,
            path=path,
            repo_root=root,
            attestation=FrozenAttestation(
                tag=tag,
                freeze_commit=target,
                spec_id=spec_id,
                markdown_sha256=markdown_digest,
                json_sha256=json_digest,
                manager=annotation["manager"],
                reviewer_ruling_path=reviewer_path,
                reviewer_ruling_sha256=reviewer_sha256,
                verification_output=verification_output,
            ),
            loader_role=loader_role,
            construction_token=_CONSTRUCTION_TOKEN,
        )
        verified.history = history
        verified.historical_companion = expected_companion
        if loader_role == "default":
            verified.audit_implementation_manifest(declared_pointers=None)
            verified.audit_implementation_manifest(
                "frozen_spec", declared_pointers=_IMPLEMENTATION_POINTERS
            )
        return verified

    @property
    def payload(self) -> Mapping[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def implementation_manifest_sha256(self) -> str:
        if self.loader_role == "g2r_g2a_replay":
            if self._replay_implementation_manifest_sha256 is None:
                raise SpecMismatch("historical replay manifest audit has not completed")
            return self._replay_implementation_manifest_sha256
        if not self._implementation_manifest_sha256:
            raise SpecMismatch("implementation manifest startup audit has not completed")
        return self._implementation_manifest_sha256

    @property
    def wrapper_implementation_manifest_sha256(self) -> str:
        if (
            self.loader_role not in {"g2r_g2a_replay", "g2x_v20_reproduction"}
            or self._wrapper_implementation_manifest_sha256 is None
        ):
            raise SpecMismatch(
                "wrapper manifest identity is unavailable on this loader route"
            )
        return self._wrapper_implementation_manifest_sha256

    @property
    def replay_rng_sha256(self) -> str:
        if self.loader_role != "g2r_g2a_replay" or self._replay_rng_sha256 is None:
            raise SpecMismatch("RNG replay identity is available only on the G2r G2a path")
        return self._replay_rng_sha256

    def _parse_implementation_manifest(
        self,
        raw: bytes,
        *,
        source_consumers: set[str] | None,
    ) -> tuple[list[dict[str, Any]], str]:
        if not raw or not raw.endswith(b"\n"):
            raise SpecMismatch("implementation manifest must be nonempty JSONL with final LF")
        entries: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for ordinal, raw_line in enumerate(raw.splitlines(), 1):
            try:
                entry = json.loads(
                    raw_line.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise SpecMismatch(
                    f"implementation manifest line {ordinal} is invalid: {error}"
                ) from error
            if not isinstance(entry, dict) or set(entry) != _MANIFEST_FIELDS:
                raise SpecMismatch(
                    f"implementation manifest line {ordinal} has a non-closed schema"
                )
            if entry["ordinal"] != ordinal:
                raise SpecMismatch("implementation manifest ordinals are not append-only")
            if entry["expected_type"] not in _MANIFEST_TYPES:
                raise SpecMismatch("implementation manifest has an unknown expected type")
            for field_name in (
                "consumer", "pointer", "source_path", "source_sha256", "symbol",
                "value_sha256",
            ):
                if not isinstance(entry[field_name], str) or not entry[field_name]:
                    raise SpecMismatch(
                        f"implementation manifest {field_name} must be nonempty"
                    )
            if not _HEX64.fullmatch(entry["value_sha256"]):
                raise SpecMismatch("implementation manifest value hash is malformed")
            if not _HEX64.fullmatch(entry["source_sha256"]):
                raise SpecMismatch("implementation manifest source hash is malformed")
            if source_consumers is None or entry["consumer"] in source_consumers:
                source_path = self.history.path(entry["source_path"], expected_sha256=entry["source_sha256"])
                try:
                    source_path.relative_to(self.history.root)
                except ValueError as error:
                    raise SpecMismatch(
                        "implementation source path escapes repository"
                    ) from error
                try:
                    source_bytes = source_path.read_bytes()
                except OSError as error:
                    raise SpecMismatch(
                        f"cannot read implementation source: {error}"
                    ) from error
                if sha256_bytes(source_bytes) != entry["source_sha256"]:
                    raise SpecMismatch(
                        f"implementation source hash disagrees for {entry['source_path']}"
                    )
            key = (entry["consumer"], entry["symbol"])
            if key in seen:
                raise SpecMismatch(f"duplicate implementation symbol {key}")
            seen.add(key)
            canonical_line = canonical_json_bytes(entry)[:-1]
            if canonical_line != raw_line:
                raise SpecMismatch("implementation manifest line is not canonical JSON")
            entries.append(entry)
        consumers = {entry["consumer"] for entry in entries}
        if not _REQUIRED_INFRA_CONSUMERS <= consumers:
            missing = sorted(_REQUIRED_INFRA_CONSUMERS - consumers)
            raise SpecMismatch(f"implementation manifest misses consumers {missing}")
        return entries, sha256_bytes(raw)

    def audit_implementation_manifest(
        self,
        consumer: str | None = None,
        *,
        manifest_path: Path | str | None = None,
        declared_pointers: Mapping[str, str] | None,
    ) -> str:
        """Require every selected implementation symbol to bind to its pointer."""
        if self.loader_role == "g2r_g2a_replay":
            if manifest_path is not None:
                raise SpecMismatch(
                    "G2r G2a replay implementation manifest path is fixed"
                )
            if consumer is None:
                raise SpecMismatch(
                    "G2r G2a replay requires a named historical consumer audit"
                )
            raw = self._replay_implementation_manifest_raw
            expected_digest = self._replay_implementation_manifest_sha256
            if raw is None or expected_digest is None:
                raise SpecMismatch("historical replay manifest is unavailable")
            digest = sha256_bytes(raw)
            if digest != expected_digest:
                raise SpecMismatch("historical replay manifest SHA-256 changed after load")
            resolved_manifest_path = (self.history.path(IMPLEMENTATION_MANIFEST.as_posix())).resolve()
        else:
            resolved_manifest_path = (
                (self.history.path(IMPLEMENTATION_MANIFEST.as_posix()))
                if manifest_path is None
                else Path(manifest_path)
            ).resolve()
            try:
                raw = resolved_manifest_path.read_bytes()
            except OSError as error:
                raise SpecMismatch(f"cannot read implementation manifest: {error}") from error
            digest = sha256_bytes(raw)
        declaration_key = (
            None
            if declared_pointers is None
            else tuple(sorted(declared_pointers.items()))
        )
        audit_key = (
            self.loader_role,
            str(resolved_manifest_path),
            digest,
            consumer,
            declaration_key,
        )
        cached = self._implementation_audit_cache.get(audit_key)
        if cached is not None:
            return cached
        if self.loader_role == "g2r_g2a_replay":
            entries, parsed_digest = self._parse_implementation_manifest(
                raw, source_consumers={consumer}
            )
            if parsed_digest != _V8_REPLAY_IMPLEMENTATION_SHA256:
                raise SpecMismatch("historical replay manifest SHA-256 disagrees")
        else:
            entries, parsed_digest = self._parse_implementation_manifest(
                raw, source_consumers=None
            )
        if parsed_digest != digest:
            raise SpecMismatch("implementation manifest SHA-256 changed during audit")
        selected = entries if consumer is None else [
            entry for entry in entries if entry["consumer"] == consumer
        ]
        if not selected:
            raise SpecMismatch(f"implementation consumer {consumer!r} is unmapped")
        if consumer is not None and declared_pointers is None:
            raise SpecMismatch(
                f"implementation consumer {consumer!r} lacks pointer declarations"
            )
        if declared_pointers is not None:
            if consumer is None:
                raise SpecMismatch("declared implementation pointers require one consumer")
            selected_by_symbol = {entry["symbol"]: entry for entry in selected}
            if set(selected_by_symbol) != set(declared_pointers):
                raise SpecMismatch(
                    f"implementation pointer declarations for {consumer} are incomplete"
                )
            for symbol, expected_pointer in declared_pointers.items():
                if selected_by_symbol[symbol]["pointer"] != expected_pointer:
                    raise SpecMismatch(
                        f"implementation binding {consumer}.{symbol} pointer disagrees"
                    )
        binding_spec = self._implementation_binding_spec or self
        for entry in selected:
            expected_type = _MANIFEST_TYPES[entry["expected_type"]]
            value = binding_spec.get(entry["pointer"], expected_type=expected_type)
            actual = sha256_bytes(canonical_json_bytes(value))
            if actual != entry["value_sha256"]:
                raise SpecMismatch(
                    f"implementation binding {entry['consumer']}.{entry['symbol']} "
                    f"disagrees at {entry['pointer']}"
                )
        if self.loader_role == "g2r_g2a_replay":
            if digest != self.implementation_manifest_sha256:
                raise SpecMismatch("historical replay manifest identity changed")
        elif self.loader_role == "g2x_v20_reproduction":
            if self._implementation_manifest_sha256 != _V20_G2X_IMPLEMENTATION_SHA256:
                raise SpecMismatch("historical G2x implementation identity changed")
            if manifest_path is None:
                self._wrapper_implementation_manifest_sha256 = digest
        elif manifest_path is None:
            self._implementation_manifest_sha256 = digest
        self._implementation_audit_cache[audit_key] = digest
        return digest

    def get(
        self,
        pointer: str,
        *,
        expected: Any = _MISSING,
        expected_type: type[Any] | tuple[type[Any], ...] | None = None,
    ) -> Any:
        """Return a deep copy of a frozen value, optionally enforcing type/value."""
        value = _resolve_pointer(self._payload, pointer)
        if expected_type is not None:
            accepted = expected_type if isinstance(expected_type, tuple) else (expected_type,)
            if type(value) not in accepted:
                names = ", ".join(item.__name__ for item in accepted)
                raise SpecMismatch(
                    f"{pointer} type is {type(value).__name__}; expected exactly {names}"
                )
        if expected is not _MISSING and value != expected:
            raise SpecMismatch(f"{pointer} value disagrees with implementation binding")
        return copy.deepcopy(value)
