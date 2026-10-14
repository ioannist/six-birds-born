"""Explicit historical bytes and identities; no repository or Git discovery.

A local evidence bundle has a manifest.json with `files` (historical path keys),
`commit_files` (commit:path keys), and `tags` (annotated tag names). Each record
binds file, sha256 and size_bytes. Multiple source revisions use path@sha256
keys. Bundle locations are not historical execution identities.
"""
from __future__ import annotations
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from .errors import IncompleteCampaign, SpecMismatch


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class HistoricalInputs:
    def __init__(self, root: Path | str | None):
        if root is None:
            raise IncompleteCampaign('historical_root is required: supply the preserved evidence bundle, not private Git history')
        self.root = Path(root).resolve()
        try:
            raw = (self.root / 'manifest.json').read_bytes()
            self.manifest = json.loads(raw)
        except (OSError, ValueError) as error:
            raise IncompleteCampaign(f'missing/invalid historical evidence manifest in {self.root}: {error}') from error
        if self.manifest.get('schema') != 'born_snapshot_historical_inputs_v1':
            raise SpecMismatch('historical evidence manifest schema disagrees')
        self.manifest_sha256 = digest(raw)

    def record(self, name: str, *, section: str = 'files', expected_sha256: str | None = None) -> dict:
        rows = self.manifest.get(section, {})
        row = rows.get(name + '@' + expected_sha256) if expected_sha256 else None
        row = row or rows.get(name)
        if not isinstance(row, dict):
            raise IncompleteCampaign(f'missing explicit historical input {section}/{name}')
        if (set(row) != {'file','sha256','size_bytes'} or not isinstance(row['file'],str)
                or not row['file'] or Path(row['file']).is_absolute() or '..' in Path(row['file']).parts
                or not isinstance(row['sha256'],str) or len(row['sha256'])!=64
                or any(c not in '0123456789abcdef' for c in row['sha256'])
                or type(row['size_bytes']) is not int or row['size_bytes']<0):
            raise SpecMismatch(f'malformed historical relocation entry: {name}')
        if expected_sha256 is not None and row.get('sha256') != expected_sha256:
            raise SpecMismatch(f'historical relocation hash differs: {name}')
        return row

    def path(self, name: str, *, section: str = 'files', expected_sha256: str | None = None) -> Path:
        row = self.record(name, section=section, expected_sha256=expected_sha256)
        path = (self.root / row['file']).resolve()
        try:
            path.relative_to(self.root)
            raw = path.read_bytes()
        except ValueError as error:
            raise SpecMismatch(f'historical location escapes bundle: {name}') from error
        except OSError as error:
            raise IncompleteCampaign(f'historical bytes unavailable for {name}: {error}') from error
        if len(raw) != row.get('size_bytes') or digest(raw) != row.get('sha256'):
            raise SpecMismatch(f'historical byte commitment differs: {name}')
        return path

    def read(self, name: str, *, section: str = 'files', expected_sha256: str | None = None) -> bytes:
        return self.path(name, section=section, expected_sha256=expected_sha256).read_bytes()

    def commit_bytes(self, commit: str, name: str, *, expected_sha256: str | None = None,
                     object_id: str | None = None) -> bytes:
        key = commit + ':' + name
        raw = self.read(key, section='commit_files', expected_sha256=expected_sha256)
        if object_id is not None:
            computed = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            if computed != object_id:
                raise SpecMismatch(f'historical blob identity differs: {key}')
        return raw

    def verify_tag(self, tag: str, allowed: bytes, principal: str) -> tuple[str, str, str]:
        """Verify the archived SSH-signed tag with ssh-keygen, without Git."""
        raw = self.read(tag, section='tags')
        marker = b'-----BEGIN SSH SIGNATURE-----'
        if raw.count(marker) != 1:
            raise SpecMismatch('historical annotated tag lacks a unique SSH signature')
        signed, signature = raw.split(marker, 1)
        headers, message = signed.split(b'\n\n', 1)
        lines = headers.decode().splitlines()
        target = next((line[7:] for line in lines if line.startswith('object ')), None)
        if 'type commit' not in lines or 'tag ' + tag not in lines or target is None:
            raise SpecMismatch('archived annotated tag headers disagree')
        with tempfile.TemporaryDirectory(prefix='born_tag_') as temp:
            root = Path(temp)
            (root/'allowed').write_bytes(allowed)
            (root/'signature').write_bytes(marker + signature)
            try:
                proc = subprocess.run(['ssh-keygen','-Y','verify','-f',str(root/'allowed'),
                    '-I',principal,'-n','git','-s',str(root/'signature')],
                    input=signed, capture_output=True, check=False)
            except OSError as error:
                raise IncompleteCampaign(f'ssh-keygen is needed for archived tag signature verification: {error}') from error
        if proc.returncode:
            raise SpecMismatch('archived signed tag verification failed: ' + proc.stderr.decode(errors='replace'))
        return target, message.decode(), proc.stdout.decode().rstrip('\n')
