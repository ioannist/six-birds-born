#!/usr/bin/env python3
"""Independent retained-input binding for the original B05 completion word.

Fraction loops and integer square roots; no production transport arithmetic.
The exact equations and inequalities are subsequently checked by Lean.
"""
from fractions import Fraction as Q
from pathlib import Path
import argparse
import hashlib
import json
import math

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from born_ladder.reproduction.embedding.ensemble import rational, vector, matrix, quant, linear, extract, render

COMMITMENTS = {
 'context':'727485bbf8c66d80d53905c62191f10606f67a6b9929eb14800b2e9e30b014c0',
 'certificate':'6bb8acd16d9d7976fa798796b56eec1c7a35c18d191d768cd15b3b45f9ad81a1',
}

SHARED_INPUTS_SHA256='cb8e0be468d9281f1c04c43fa5c4ecedb233c92336e952230d25997806ffa591'








def check(evidence,lean_root):
 c=evidence.config('B05');docs={}
 for role,commitment in COMMITMENTS.items():
  data=evidence.path(c[role]).read_bytes()
  if hashlib.sha256(data).hexdigest()!=commitment:raise ValueError('B05 input commitment differs: '+role)
  docs[role]=json.loads(data)
 w,s,K,labels,_,_=extract(docs['context'],docs['certificate'])
 # Bind every shared B04 parameter used by the B05 theorem, without importing
 # production arithmetic or requiring the unrelated B04 fiber certificates.
 prefix='import BornCalculus.Definitions\n\nnamespace BornCalculus\n\n'
 prefix+='/- Original EXP-112/loo_A25 exact kernel and four B04 fiber witnesses.\nExternal archive binding is separate from the kernel proof. -/\n'
 prefix+='def b04SQ : ℚ := '+rational(s)+'\n'
 prefix+='def b04WQ : Fin 32 → ℚ :=\n '+vector(w)+'\n'
 prefix+='def b04KQ : Matrix (Fin 32) (Fin 32) ℚ :=\n '+matrix(K)+'\n'
 root=Path(lean_root)/'BornCalculus';shared_bytes=(root/'B04Inputs.lean').read_bytes()
 if hashlib.sha256(shared_bytes).hexdigest()!=SHARED_INPUTS_SHA256:
  raise ValueError('B05 shared metric/kernel/lens embedding differs')
 shared=shared_bytes.decode()
 joint='def b04Joint : Fin 32 → Fin 3 := !['+','.join(map(str,labels))+']'
 if shared.split('def b04PQ',1)[0]!=prefix or joint not in shared.splitlines():
  raise ValueError('B05 shared metric/kernel/lens embedding differs')
 expected=render(docs['context'],docs['certificate']);actual=(root/'B05Inputs.lean').read_text()
 if actual!=expected:raise ValueError('B05 completion/root/readout embedding differs')
 return {'status':'PASS','input_sha256':COMMITMENTS,'root_bits':64,'chart_bits':48,'readout_bits':40,'ensemble_pairs':1,'atoms':4,'embedding_sha256':hashlib.sha256(actual.encode()).hexdigest(),'shared_inputs_sha256':SHARED_INPUTS_SHA256,'boundary':'external archive/extraction binding, not a Lean provenance theorem'}

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--data',type=Path,required=True)
 parser.add_argument('--lean-root',type=Path,default=Path(__file__).resolve().parents[1])
 args=parser.parse_args()
 from born_ladder.claims import Evidence
 try:print(json.dumps(check(Evidence(args.data),args.lean_root),sort_keys=True))
 except (ValueError,OSError,KeyError) as exc:parser.exit(1,f'FAIL: {exc}\n')

if __name__=='__main__':main()
