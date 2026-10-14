"""One registered configuration and digest, independent of draft receipts."""
import hashlib
import json
from pathlib import Path
from born_ladder.snapshot.rng import master_key


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class Specification:
    def __init__(self, directory='specifications'):
        self.directory = Path(directory).resolve()
        self.document = json.loads((self.directory/'predictive_v25.json').read_bytes())
        self.science = self.document['scientific']
        self.digest = digest(self.science)
        if self.digest != self.document['scientific_digest_preview']:
            raise ValueError('v25 scientific digest does not match')
        self.domains = self.science['inference']['bootstrap_domain_table']
        if len(self.domains) != 17:
            raise ValueError('v25 requires the complete seventeen-row domain table')
        from .seeds import acquisition_identities
        acquisition_identities(self.science)

    def grid(self, evaluation):
        if evaluation not in ('competitor', 'cross-term'):
            raise ValueError('unknown v25 evaluation')
        return self.science['acquisition']['grids']['v25-'+evaluation]

    def bootstrap_key(self, evaluation, statistic, replicate):
        if not 0 <= replicate < self.science['inference']['bootstrap']['replicates']:
            raise ValueError('replicate outside registration')
        return master_key(self.science['rng']['master_prefix'], [
            ('str','bootstrap-v2'), ('bytes',bytes.fromhex(self.digest)),
            ('str','v25-'+evaluation), ('str',statistic), ('u64',replicate)])

    def orientation_key(self, evaluation, identity, restricted_hash, slot, attempt):
        if not 0 <= slot < self.science['orientation_sensitivity']['random_orientation_count'] or not 0 <= attempt < 8:
            raise ValueError('orientation index/attempt outside registration')
        seed = self.science['orientation_sensitivity']['seeds'][evaluation.replace('-','_')]
        return master_key(self.science['rng']['master_prefix'], [
            ('str','orientation-report-v1'), ('bytes',bytes.fromhex(self.digest)),
            ('str','v25-'+evaluation), ('u64',seed), ('str',canonical_bytes(identity).decode()),
            ('bytes',bytes.fromhex(restricted_hash)), ('u64',slot), ('u64',attempt)])
