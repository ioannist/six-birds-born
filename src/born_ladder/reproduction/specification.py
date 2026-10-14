"""Readable inline scientific specifications, with explicit RNG identities.

An original specification digest is a scientific RNG input. It is not an
assertion that these public files have those historical bytes or were signed.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

from born_ladder.snapshot.errors import SpecMismatch


# Canonical serialization and RNG hashing share the verification implementation.
from born_ladder.snapshot.frozen_spec import canonical_json_bytes, sha256_bytes


class PublicSpecification:
    """Explicit public directory, version and optional produced-data root."""

    def __init__(self, directory: Path, version: str, *, work_root: Path | None = None):
        self.directory = Path(directory).resolve(strict=True)
        self.repo_root = None if work_root is None else Path(work_root).resolve()
        manifest = self._read('predictive.json')
        if manifest.get('schema') != 'born_public_specification_v2':
            raise SpecMismatch('unsupported public specification')
        entry = manifest['versions'][version]
        self.scientific_rng_identity = entry['scientific_rng_identity']
        # Compatibility spelling used by unchanged historical RNG/identity code.
        # This object carries a namespace, not a historical attestation.
        self.attestation = SimpleNamespace(json_sha256=self.scientific_rng_identity)
        self.version = version
        self._values = {}
        index = self._read(entry['section_index'])
        if index['version'] != version:
            raise SpecMismatch('mixed scientific section versions')
        if index.get('schema') != 'born_shared_scientific_sections_v1':
            raise SpecMismatch('unsupported shared-section index')
        part = self._read(index['main_file'])
        if (part['scientific_rng_identity'] != self.scientific_rng_identity
                or part['version'] != version):
            raise SpecMismatch('mixed scientific RNG identities or versions')
        for name,pointer in part['source_json_pointers'].items():
            self._values[pointer] = part[name]
        for section in index['sections']:
            pointer = section['pointer']
            if pointer in self._values:
                raise SpecMismatch('duplicate scientific pointer')
            if section['encoding'] != 'json':
                raise SpecMismatch('unsupported scientific section encoding')
            if not section['file'].endswith('.json'):
                raise SpecMismatch('scientific section encoding differs from filename')
            value = self._read(section['file'])
            encoded = canonical_json_bytes(value).removesuffix(b'\n')
            if sha256_bytes(encoded) != section['scientific_value_sha256']:
                raise SpecMismatch('shared scientific section hash differs')
            self._values[pointer] = value
        self.public_manifest_sha256 = sha256_bytes((self.directory/'predictive.json').read_bytes())
        if version in ('v23','v24'):
            self._g2c_source_spec = PublicSpecification(self.directory,'v21',work_root=work_root)

    def _read(self, name):
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or not name.endswith('.json'):
            raise SpecMismatch('specification includes must be relative public JSON files')
        file = (self.directory/relative).resolve(strict=True)
        if not file.is_relative_to(self.directory):
            raise SpecMismatch('specification include escapes directory')
        try:
            raw = file.read_bytes()
            return json.loads(raw)
        except (OSError,EOFError,ValueError) as error:
            raise SpecMismatch('unreadable scientific section: '+name) from error

    def _assembled(self, pointer):
        """Collect published scientific sections beneath a parent pointer."""
        if pointer in self._values:
            return copy.deepcopy(self._values[pointer])
        prefix = pointer + '/'
        children = sorted({key[len(prefix):].split('/')[0]
                           for key in self._values if key.startswith(prefix)})
        if not children:
            raise SpecMismatch('pointer was not published as science: '+pointer)
        return {key:self._assembled(prefix+key) for key in children}

    def get(self, pointer: str, expected_type=None):
        if not pointer.startswith('/'):
            raise SpecMismatch('scientific pointer must be absolute JSON pointer')
        ancestor = max((key for key in self._values
                        if pointer == key or pointer.startswith(key+'/')),
                       key=len, default=None)
        if ancestor is not None:
            value = copy.deepcopy(self._values[ancestor])
            suffix = pointer[len(ancestor):].strip('/')
            if suffix:
                for key in suffix.split('/'):
                    key = key.replace('~1','/').replace('~0','~')
                    value = value[int(key)] if isinstance(value,list) else value[key]
        else:
            value = self._assembled(pointer)
        if expected_type is not None and not isinstance(value,expected_type):
            raise SpecMismatch('scientific pointer type differs: '+pointer)
        return copy.deepcopy(value)

    def audit_implementation_manifest(self, consumer, *, declared_pointers,
                                      manifest_path=None):
        """Validate scientific reads; no old implementation receipt is opened.

        Original source recovery is audited separately. Process pointer names
        are deliberately absent, rather than supplied by private records.
        """
        if manifest_path is not None:
            raise SpecMismatch('public production does not read implementation receipts')
        checked = {}
        for name, pointer in declared_pointers.items():
            try:
                checked[name] = sha256_bytes(canonical_json_bytes(self.get(pointer)))
            except SpecMismatch:
                # A declaration of an old operational pointer is not a read.
                # Any actual get() of it still fails explicitly above.
                checked[name] = 'process pointer omitted'
        return {'consumer':consumer,'scientific_reads':checked,
                'public_manifest_sha256':self.public_manifest_sha256}

    @classmethod
    def load(cls, directory, *, version='v24', work_root=None):
        return cls(Path(directory),version,work_root=work_root)
