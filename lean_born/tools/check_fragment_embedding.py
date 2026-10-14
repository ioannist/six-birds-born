#!/usr/bin/env python3
"""Bind the embedded B06 atomic effects to the retained original fixture.

This is an external byte/extraction check, not a Lean proof of provenance.
The arithmetic extraction uses its own Fraction loops, not model/Instrument.
"""
from fractions import Fraction as Q
from pathlib import Path
import argparse
import hashlib
import json
import re

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from born_ladder.reproduction.embedding.fragment import rational, matrix, render

COMMITMENTS = {
    'context': '727485bbf8c66d80d53905c62191f10606f67a6b9929eb14800b2e9e30b014c0',
    'certificate': '55c5530b4a1a93d6508512660b9a96adf7db5e22a3961e31da0ed030a1885958',
}
IDENTITY = {
    'config': 'loo_A25', 'exp': 'EXP-112', 'k': 2,
    'map_sha256': '2fcf55976eee6c81300fa2ee5e60e8401fd7531c5b05e9dd6a0e12d4a0222625',
    'step_index': 0,
}








def check(evidence, lean_root):
    contract = evidence.config('B06')
    inputs = {}
    for role, expected in COMMITMENTS.items():
        path = evidence.path(contract[role])
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('B06 input commitment differs: ' + role)
        inputs[role] = json.loads(data)
    expected = render(inputs['context'], inputs['certificate'])
    path = Path(lean_root) / 'BornCalculus/B06Inputs.lean'
    actual = path.read_text()
    if actual != expected:
        raise ValueError('B06 exact effect/metric embedding differs')
    # Registration is a separate bridge from matching the eight coefficients.
    # Check both the executing Python enumeration and the explicit Lean table.
    from itertools import product
    from types import SimpleNamespace
    from born_ladder.instruments import FIELDS, tests
    fields = ('raw_by_state','package_by_state','joint_by_state')
    if FIELDS != fields:
        raise ValueError('B06 executing lens order differs')
    sizes = dict(zip(fields,(2,3,3)))
    rows = list(tests(SimpleNamespace(parts={f:dict.fromkeys(range(sizes[f])) for f in fields})))
    programs = [p for n in (1,2) for p in product(fields,repeat=n)]
    if [tuple(p) for p,_ in rows] != programs:
        raise ValueError('B06 executing program census differs')
    for program,words in rows:
        if words != list(product(*(range(sizes[f]) for f in program))):
            raise ValueError('B06 executing word census differs')
    witness = (Path(lean_root)/'BornCalculus/B06Witness.lean').read_text()
    block = witness.split('noncomputable def b06Programs',1)[1].split('theorem b06_programs_invertible',1)[0]
    entries = re.findall(r'^\s*\|\s*(\d+|_)\s*=>\s*\[([^]]+)\]',block,re.M)
    names = dict(zip(fields,('b06RawTest','b06PackageTest','b06JointTest')))
    wanted = [(str(i) if i<11 else '_',','.join(names[f] for f in p)) for i,p in enumerate(programs)]
    if [(i,','.join(x.strip() for x in body.split(','))) for i,body in entries] != wanted:
        raise ValueError('B06 Lean program registration differs')
    return {'status': 'PASS', 'input_sha256': COMMITMENTS,
            'embedding_sha256': hashlib.sha256(actual.encode()).hexdigest(),
            'atomic_effects': 8, 'families': [2,3,3], 'programs': 12,
            'registered_event_occurrences': sum(2**len(words) for _,words in rows),
            'original_fixture': IDENTITY,
            'boundary': 'external extraction/byte binding, not a cryptographic Lean theorem'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--lean-root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    from born_ladder.claims import Evidence
    try:
        print(json.dumps(check(Evidence(args.data),args.lean_root),sort_keys=True))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f'FAIL: {exc}\n')


if __name__ == '__main__':
    main()
