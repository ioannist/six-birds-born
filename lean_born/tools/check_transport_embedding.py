#!/usr/bin/env python3
"""External binding of B04's exact kernel/fibers and rational root certificates.

Independent Fraction/isqrt extraction; no production transport/model arithmetic.
The Lean kernel verifies the equations and inequalities in the extracted data.
"""
from fractions import Fraction as Q
from pathlib import Path
import argparse
import hashlib
import json
import math

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from born_ladder.reproduction.embedding.transport import rational, vector, matrix, rational_root, render

COMMITMENTS = {
    'context': '727485bbf8c66d80d53905c62191f10606f67a6b9929eb14800b2e9e30b014c0',
    'amplitude_certificate': '318e1d8723d52fce061d12dd7f9d4cfa246ea7c0b628183d05b6ffed5b777d9e',
    'joined_certificate': '338c7d46ef3aaa1f6f5559a472d1dd4e3cac41013bf3d35cc882b1c7ee579965',
}












def check(evidence,lean_root):
    c=evidence.config('B04');inputs={}
    for role,commitment in COMMITMENTS.items():
        data=evidence.path(c[role]).read_bytes()
        if hashlib.sha256(data).hexdigest()!=commitment:
            raise ValueError('B04 input commitment differs: '+role)
        inputs[role]=json.loads(data)
    expected=render(inputs['context'],inputs['amplitude_certificate'],inputs['joined_certificate'])
    actual=(Path(lean_root)/'BornCalculus/B04Inputs.lean').read_text()
    if actual!=expected:raise ValueError('B04 exact kernel/fiber/root-certificate embedding differs')
    return {'status':'PASS','input_sha256':COMMITMENTS,'root_bits':40,'fiber_pairs':4,
            'embedding_sha256':hashlib.sha256(actual.encode()).hexdigest(),
            'boundary':'external archive/extraction binding, not a Lean provenance theorem'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--lean-root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    from born_ladder.claims import Evidence
    try:print(json.dumps(check(Evidence(args.data),args.lean_root),sort_keys=True))
    except (ValueError,OSError,KeyError) as exc:parser.exit(1,f'FAIL: {exc}\n')


if __name__=='__main__':main()
