"""Original implementation and completion are distinct record types."""
from pathlib import Path
from copy import deepcopy
import json
from born_ladder.census import publish_reviewed_typing
from born_ladder.archive import put
from test_regressions import fixture

def test_original_failures_and_completion_tables_remain_separate(tmp_path):
 review=tmp_path/'review';out=tmp_path/'out';review.mkdir();out.mkdir();original=[];completed=[];computed=[];inv=[]
 for name in ['ordinary','basis','tiny']:
  f=fixture(name);old=f['reviewed_certificates'];uid=old['unit_id'];new=deepcopy(old);new['overall_status']='PASS'
  inv.append({'unit_id':uid});original.append(old);computed.append(new)
  completed.append({'unit_id':uid,'overall_registered_claim_status':'PASS','original_overall_status_preserved':old['overall_status']})
  (review/'contexts'/uid).mkdir(parents=True);(out/'contexts'/uid).mkdir(parents=True)
  put(review/'contexts'/uid/'certificates.json',old);put(review/'contexts'/uid/'structural_completion.json',completed[-1])
 put(review/'structural_results.json',original);put(review/'structural_completion_results.json',completed)
 for name in ['context_status.csv','context_status_completed.csv','STRUCTURAL_COMPLETION.md']:put(review/name,b'explicit historical and completed records\n')
 publish_reviewed_typing(review,out,inv,computed)
 assert json.loads((out/'structural_results.json').read_text())==original
 assert json.loads((out/'structural_completion_results.json').read_text())==completed
 statuses=[r['overall_status'] for r in json.loads((out/'structural_results.json').read_text())]
 assert statuses.count('FAILED')==2 and statuses.count('PASS')==1
 assert all(r['overall_registered_claim_status']=='PASS' for r in completed)
 for r in original:
  assert (out/'contexts'/r['unit_id']/'certificates.json').read_bytes()==(review/'contexts'/r['unit_id']/'certificates.json').read_bytes()
 assert json.loads((out/'contexts'/original[-1]['unit_id']/'certificates.json').read_text())['certificates']['C_premises']['error_type']=='OverflowError'
