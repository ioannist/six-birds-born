#!/usr/bin/env python3
"""Independent exact binding of the registered raw1/package0 order witness."""
from fractions import Fraction as Q
from pathlib import Path
import argparse,hashlib,json,math

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from born_ladder.reproduction.embedding.order import rational, mm, det, linear, extract, render

CONTEXT_SHA256='727485bbf8c66d80d53905c62191f10606f67a6b9929eb14800b2e9e30b014c0'
SHARED_SHA256='c5d7b6a6d72a65f2c19476d39a12e7830f4733235e2a4dfc98437a436003420f'





def check(evidence,lean_root):
 c=evidence.config('B07');data=evidence.path(c['context']).read_bytes()
 if hashlib.sha256(data).hexdigest()!=CONTEXT_SHA256:raise ValueError('B07 context commitment differs')
 context=json.loads(data);root=Path(lean_root)/'BornCalculus'
 shared=(root/'B06Inputs.lean').read_bytes()
 if hashlib.sha256(shared).hexdigest()!=SHARED_SHA256:raise ValueError('B07 shared effect/metric embedding differs')
 actual=(root/'B07Inputs.lean').read_text()
 if actual!=render(context):raise ValueError('B07 coefficient/root/order embedding differs')
 return {'status':'PASS','context_sha256':CONTEXT_SHA256,'shared_inputs_sha256':SHARED_SHA256,
         'embedding_sha256':hashlib.sha256(actual.encode()).hexdigest(),'root_bits':64,'probability_bits':40,
         'word_orders':2,'boundary':'external byte/extraction binding, not a Lean provenance theorem'}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,required=True)
 p.add_argument('--lean-root',type=Path,default=Path(__file__).resolve().parents[1]);a=p.parse_args()
 from born_ladder.claims import Evidence
 try:print(json.dumps(check(Evidence(a.data),a.lean_root),sort_keys=True))
 except (ValueError,OSError,KeyError) as e:p.exit(1,f'FAIL: {e}\n')
if __name__=='__main__':main()
