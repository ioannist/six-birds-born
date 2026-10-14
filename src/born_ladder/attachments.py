"""Original-byte joins, never a rescoring or replacement of historical fields."""
import hashlib,json
from . import metadata as P
from .archive import canonical,put,sha

def attach(archive,row,ptr,output,certificate,index):
 body,_,raw=archive.line(ptr);refs=P.refs(body,P.UNIT_KEYS|{'unrounded_p_full','spectral_coefficients'})
 if any(refs[k]!=v for k,v in ptr['fields'].items()):raise ValueError('unit field commitment mismatch')
 structural=P.metadata(body,P.UNIT_KEYS|{'unrounded_p_full','spectral_coefficients'});key=row['provenance_key']
 for name in P.UNIT_KEYS:
  if name in key and structural[name]!=key[name]:raise ValueError('complete provenance join: '+name)
 for name,k in [('basis_and_projector_inputs','basis_projector_field_sha256'),('unrounded_p_full','preparation_input_sha256')]:
  if refs[name]['field_sha256']!=key[k]:raise ValueError('frame/preparation commitment mismatch')
 if structural['kind_cell_id']!=ptr['kind_cell_id']:raise ValueError('kind mismatch')
 fields={k:body[a:b] for k,a,b in P.spans(body) if k not in structural};decoded={k:json.loads(s) for k,s in fields.items()}
 put(output/(ptr['kind']+'_original.jsonl'),raw)
 put(output/(ptr['kind']+'_performance_verbatim.json'),{'source':ptr,'original_JSON_value_substrings':fields,'value_sha256':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in fields.items()},'no_recalculation':True})
 for link in decoded.get('applicable_control_record_links',[]):
  name=str(__import__('pathlib').Path(ptr['path']).parent/link['path'])
  cache=getattr(archive,'verified_file_hashes',None)
  if cache is None:actual=sha(archive.path(name))
  else:
   if name not in cache:cache[name]=sha(archive.path(name))
   actual=cache[name]
  if actual!=link['sha256']:raise ValueError('control link mismatch')
 return {'index':index,'unit_id':row['unit_id'],'key_sha256':hashlib.sha256(canonical(key)).hexdigest(),'complete_provenance_key':key,'view':ptr['kind'],'status':'PASS','original_row_copy_sha256':hashlib.sha256(raw).hexdigest(),'source':ptr,'fields':decoded,'structural_overall_status':certificate['overall_status'],'diagnostics':certificate['certificates']['diagnostics'],'nondegeneracy_record':{k:v for k,v in decoded.items() if any(t in k.lower() for t in ['degener','energy','nonconstant'])} or {'status':'MISSING','reason':'No explicit nondegeneracy field in original unit; structural diagnostics are separately reported, no new threshold.'}}
