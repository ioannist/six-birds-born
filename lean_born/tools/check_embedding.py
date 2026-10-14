#!/usr/bin/python3
"""Verify immutable Lean extraction against the three fixed RI inputs."""
from pathlib import Path
import hashlib,json,re,argparse
from fractions import Fraction as F
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from born_ladder.reproduction.embedding.ri import rational, vector, render

COMMITMENTS={
 'CONTEXT.json':'33847659630152edfaed13095af43ffb909fcc4369027537fe1a58619a73ec1d',
 'initial_strictness_certificate.json':'201e74ef63e6333c9b894668ed5700fbe166b3108c25b31cbd37d30fbc75d91c',
 'six_state_certificate.json':'8e260bebd7dbb5b1d37777017181eb8116134106778945fde6100e5238f0b756'}



def main():
 parser=argparse.ArgumentParser();parser.add_argument('--evidence',type=Path,required=True,help='Explicit original RI evidence directory; not required for kernel checking of embedded constants');parser.add_argument('--lean-root',type=Path,default=Path(__file__).resolve().parents[1]);args=parser.parse_args();input_root=args.evidence;lean_root=args.lean_root
 for name,h in COMMITMENTS.items():
  if hashlib.sha256((input_root/name).read_bytes()).hexdigest()!=h:
   raise SystemExit('INPUT MISMATCH: '+name)
 p=lean_root/'BornCalculus/RIInputs.lean'
 if p.read_text()!=render(input_root):raise SystemExit('COEFFICIENT/LABEL/INTERVAL EMBEDDING MISMATCH')
 c=json.loads((input_root/'CONTEXT.json').read_text())
 w=(lean_root/'BornCalculus/RIWitness.lean').read_text()
 cert=json.loads((input_root/'initial_strictness_certificate.json').read_text())['certificate']
 if cert['point_indices']!=[1,3]:raise SystemExit('POINT PAIR MISMATCH')
 view=cert['left_old_view']
 if view!=cert['right_old_view']:raise SystemExit('OLD VIEWS DIFFER')
 for side,index in [('left',1),('right',3)]:
  for lens,size in [('raw_by_state',2),('package_by_state',3),('joint_by_state',3)]:
   expected_law={str(label):str(int(c['lens'][lens][index]==label)) for label in range(size)}
   if cert[side+'_old_view']['actual_passive_laws'][lens]!=expected_law:
    raise SystemExit('OLD MARGINAL MISMATCH: '+side+'/'+lens)
 fields={'context':'context','invocationId':'invocation_id','unitId':'unit_id','partition':'partition',
  'experiment':'experiment','cell':'actual_source_cell','seed':'seed','resolution':'resolution',
  'scale':'scale','time':'step'}
 expected={key:view['context'][value] for key,value in fields.items()}
 expected.update(lag=view['lag'],historyHorizons=view['history_horizons'],
  receiptClass=view['preparation_receipt']['class'],recipeIndex=view['preparation_receipt']['recipe_id'],
  acquiredPassivePrefix=view['acquired_passive_prefix'],commands=view['commands'],
  acquiredUpperOutcomes=view['acquired_upper_outcomes'],coefficientHistoryArrays=view['coefficient_history_arrays'],
  precision=view['precision'],sourcePolicy=view['source_policy'],stage=view['status'])
 for key,value in expected.items():
  literal='none' if value is None else json.dumps(value,ensure_ascii=False)
  if not re.search(r'^ '+key+r' := '+re.escape(literal)+r'$',w,re.M):
   raise SystemExit('OLD METADATA MISMATCH: '+key)
 print(json.dumps({'status':'PASS','input_sha256':COMMITMENTS,
  'embedding_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
  'exact_difference':'computed from the archived exact left/right values; Lean proves containment in the archived enclosure',
  'coefficient_mode_and_all_three_label_arrays':'literal exact extraction',
  'metadata':'all fixed old-view fields checked against both archived views'},sort_keys=True))
if __name__=='__main__':main()
