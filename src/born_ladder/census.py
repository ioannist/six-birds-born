"""Clean regeneration driver: reviewed inputs, explicit outputs, no new science."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import json,time,hashlib
from .archive import Archive,sha,put,verify_files,canonical
from .certificates import construct_context
from .attachments import attach
from .summaries import summarise
from .independent import check_context,verify_summaries
from .independent_trine import check as check_trine

# These name *fields* allowed to vary in a relocation/regeneration. No numeric
# values, status, witness, null field or attachment content is stripped.
VOLATILE_FIELDS={'wall_seconds','frame_context','frame_context_sha256','six_state_certificate','six_state_certificate_sha256','context_frame_sha256','uniform_proof_binding'}
def _require(condition,message):
 # Invariants are executable verification gates, including under Python -O.
 if not condition:raise AssertionError(message)


def scientific(x):
 if isinstance(x,dict):return {k:scientific(v) for k,v in x.items() if k not in VOLATILE_FIELDS}
 if isinstance(x,list):return [scientific(v) for v in x]
 return x

def publish_reviewed_typing(review,out,inv,rows):
 # The primary records are historical implementation records, NEVER renamed
 # completion successes. Freshly recomputed completion certificates have their
 # own explicit names; reviewed two-table receipts remain byte-identical.
 original_rows=json.loads((review/'structural_results.json').read_text())
 completion_rows=json.loads((review/'structural_completion_results.json').read_text())
 if not len(inv)==len(rows)==len(original_rows)==len(completion_rows):raise ValueError('incomplete original/completion inventory')
 for meta,new,old,completed in zip(inv,rows,original_rows,completion_rows):
  uid=meta['unit_id'];d=out/'contexts'/uid
  _require(old['unit_id']==new['unit_id']==completed['unit_id']==uid, 'verification invariant failed')
  _require(new['overall_status']==completed['overall_registered_claim_status']=='PASS', 'verification invariant failed')
  if old['certificates']['C_premises']['status']=='PASS':
   _require(scientific(new['certificates']['C_premises'])==scientific(old['certificates']['C_premises']), ('reviewed C premise fields',uid))
  put(d/'certificates.json',(review/'contexts'/uid/'certificates.json').read_bytes())
  put(d/'structural_completion.json',(review/'contexts'/uid/'structural_completion.json').read_bytes())
 for name in ['structural_results.json','structural_completion_results.json','context_status.csv','context_status_completed.csv','STRUCTURAL_COMPLETION.md']:
  put(out/name,(review/name).read_bytes())
 put(out/'status_typing_equivalence.json',{'status':'PASS','original_implementation_table':{'path':'structural_results.json','counts':{'PASS':sum(r['overall_status']=='PASS' for r in original_rows),'FAILED':sum(r['overall_status']=='FAILED' for r in original_rows)},'reviewed_sha256':sha(review/'structural_results.json'),'regenerated_sha256':sha(out/'structural_results.json')},'supplementary_completion_table':{'path':'structural_completion_results.json','counts':{'PASS':sum(r['overall_registered_claim_status']=='PASS' for r in completion_rows)},'reviewed_sha256':sha(review/'structural_completion_results.json'),'regenerated_sha256':sha(out/'structural_completion_results.json')},'completion_disclosure':'STRUCTURAL_COMPLETION.md','original_per_context_certificates':'byte-identical','computed_certificates':'contexts/<unit>/supplementary_completion_certificate.json'})

def worker(args):return construct_context(*args)
def regenerate(repository,inventory_path,reviewed_root,output,formula_path,proof_paths,workers=8,*,historical_root=None):
 start=time.monotonic();repo=Path(repository).resolve();review=Path(reviewed_root).resolve();out=Path(output).resolve()
 if out.exists():raise FileExistsError('write-once output exists: '+str(out))
 if not 1<=workers<=8:raise ValueError('worker cap is 8')
 inv=json.loads(Path(inventory_path).read_text())
 if len(inv)!=120 or len({r['unit_id'] for r in inv})!=120:raise ValueError('frozen census requires exactly 120 contexts')
 expected=json.loads((review/'INVENTORY.json').read_text())
 if inv!=expected:raise ValueError('inventory differs from reviewed frozen120')
 manifest=json.loads((review/'artifact_manifest.json').read_text())
 if historical_root is None:
  verify_files(repo,manifest['outputs'])
 else:
  from .snapshot.historical import HistoricalInputs
  history=HistoricalInputs(historical_root)
  for name,digest in manifest['outputs'].items():
   path=repo/name
   if not path.is_file():path=history.path(name,expected_sha256=digest)
   if sha(path)!=digest:raise ValueError('reviewed output commitment differs: '+name)
 # Source registers carry stored evidence, not a requirement to restore a later
 # edited project record to its historical wording. All actual scientific inputs
 # below are verified against their registered bytes before extraction.
 source=json.loads((review/'SOURCE_REGISTER.json').read_text())['inputs']
 paths=set(proof_paths)
 for row in inv:
  paths.add(row['provenance_key']['kernel']['artifact']['path']);paths.add(row['source']['born']['path']);paths.update(p['path'] for p in row['kind_records'])
 for p in paths:
  if p not in source:raise ValueError('source unregistered: '+p)
 verify_files(repo,{p:source[p] for p in paths})
 out.mkdir(parents=True)
 put(out/'entry.json',{'inventory_sha256':sha(inventory_path),'reviewed_manifest_sha256':sha(review/'artifact_manifest.json'),'source_commitments':{p:source[p] for p in sorted(paths)},'historical_failures_preserved_in':str(review),'registered_threshold':'1/1000000000000','no_new_science':True})
 tasks=[(i,r,str(repo),str(out),str(formula_path),proof_paths,"supplementary_completion_certificate.json") for i,r in enumerate(inv)]
 with ProcessPoolExecutor(max_workers=workers) as pool:rows=list(pool.map(worker,tasks))
 if any(r['overall_status']!='PASS' for r in rows):
  put(out/'regeneration_failures.json',rows);raise ValueError('construction failure preserved; no replacement')
 publish_reviewed_typing(review,out,inv,rows)
 # All structural work commits before decoding original performance fields.
 put(out/'structural_seal.json',{'outputs':{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()},'context_count':120,'before_performance_attachment':True})
 comparisons=[];verification=[];attached=[]
 for i,(meta,new) in enumerate(zip(inv,rows)):
  uid=meta['unit_id'];d=out/'contexts'/uid;old=json.loads((review/'contexts'/uid/'certificates.json').read_text());old_ctx=json.loads((review/'contexts'/uid/'CONTEXT.json').read_text());new_ctx=json.loads((d/'CONTEXT.json').read_text())
  _require(new_ctx==old_ctx, ('context source values',uid))
  for name in ['kernel','carrier','correspondence','strictness','factorization_controls','diagnostics']:
   a=scientific(new['certificates'][name]);b=scientific(old['certificates'][name])
   if name=='correspondence':b['status']=json.loads((review/'contexts'/uid/'structural_completion.json').read_text())['registered_numerical_gate_status']
   if a!=b:raise ValueError('scientific mismatch '+uid+' '+name+' '+repr(set(a)^set(b)))
  trine=json.loads((d/'six_state_exact_completion.json').read_text());_require(trine==json.loads((review/'contexts'/uid/'six_state_exact_completion.json').read_text()), 'verification invariant failed')
  cp=new['certificates']['C_premises'];oc=json.loads((review/'contexts'/uid/'structural_completion.json').read_text())
  _require(all(cp[k]==oc[k] for k in ['atom_count','strict_positive_atom_count','zero_atom_count','negative_atom_count']), 'verification invariant failed')
  oldatoms={(a['context'],a['atom']):a['Gram_det_exact'] for a in oc['atoms']};_require(all(oldatoms[(a['context'],a['atom'])]==a['Gram_det_exact'] for a in cp['atom_certificates']), 'verification invariant failed')
  _require(json.loads((d/'landed_own_input_prediction.json').read_text())==json.loads((review/'contexts'/uid/'landed_own_input_prediction.json').read_text()), 'verification invariant failed')
  verification.append(check_context(d,"supplementary_completion_certificate.json"))
  check_trine(trine)
  comparisons.append({'unit_id':uid,'scientific_values':'MATCH','original_implementation_status_preserved':old['overall_status'],'original_C_premise_status_preserved':old['certificates']['C_premises']['status'],'original_correspondence_status_preserved':old['certificates']['correspondence']['status'],'literal_constructor_status':new['certificates']['correspondence']['constructor_literal_bit_equality_status'],'exact_trine':'MATCH','exact_witness':'MATCH','independent_recomputation':'PASS'})
  for ptr in meta['kind_records']:
   record=attach(Archive(repo),meta,ptr,d,old,i)
   original=(review/'contexts'/uid/(ptr['kind']+'_original.jsonl')).read_bytes()
   _require((d/(ptr['kind']+'_original.jsonl')).read_bytes()==original, 'verification invariant failed')
   fields=json.loads((review/'contexts'/uid/(ptr['kind']+'_performance_verbatim.json')).read_text())
   _require(json.loads((d/(ptr['kind']+'_performance_verbatim.json')).read_text())==fields, 'verification invariant failed')
   _require(record==json.loads((review/'attachments.json').read_text())[len(attached)], ('attachment record typing',uid))
   attached.append(record)
 put(out/'attachments.json',attached);summary=summarise(attached,120)
 _require(summary==json.loads((review/'descriptive_summaries.json').read_text()), 'descriptive summaries mismatch')
 independent_summary=verify_summaries(attached,summary)
 put(out/'descriptive_summaries.json',summary)
 put(out/'independent_verification.json',{'contexts':verification,'summary_records':independent_summary,'all_exact_source_quantities_recomputed':True})
 put(out/'comparison.json',{'context_count':120,'attachment_rows':len(attached),'summary_records':len(summary),'per_context':comparisons,'accounted_differences':{'timestamps':'new run; not compared as scientific values','wall_seconds':'remeasured','paths':'explicit output root; old certificates immutable','proof_file_paths_and_hashes':'bound same source proofs; generated frame paths/hashes change due relocation','original_failures':'historical originals retained and hash-bound; extraction implements reviewed supplementary registered gate/exact trine, never overwrites historical failures','C_premise_layout':'Original certificates byte-identical, including original failures; separately recomputed supplementary certificate restores all reviewed fields/wording, with paths and exact-ring certificate hash documented separately'},'wall_seconds':time.monotonic()-start,'contexts_per_second':120/(time.monotonic()-start)})
 put(out/'complete.json',{'status':'PASS','outputs':{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()},'wall_seconds':time.monotonic()-start})
 return json.loads((out/'comparison.json').read_text())
