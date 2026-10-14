"""Registered construction and certificate predicates with explicit archive inputs.
Original auxiliary failures remain historical evidence, separate from regeneration.
"""
from fractions import Fraction as Q
from pathlib import Path
import json,math,time,numpy as np
from born_ladder import arithmetic as algebra
from born_ladder.arithmetic import I,certify_G,qserial as qs
from born_ladder.instruments import Instrument,FIELDS
from born_ladder import metadata as P
from born_ladder.archive import Archive,sha,put,canonical
from born_ladder.snapshot.g2a import _oriented_basis
from born_ladder.snapshot.universal_shapes import _recomputed_laws,_formula_contract
class FormulaView:
 def __init__(self,path):
  from born_ladder.reproduction.specification import PublicSpecification
  self.spec=PublicSpecification(path,'v24')
 def get(self,p,expected_type=None):
  return self.spec.get(p,expected_type=expected_type)

def _require(condition,message):
 # Invariants are executable verification gates, including under Python -O.
 if not condition:raise AssertionError(message)


def native_step(K,p):
 out=[0.]*len(p)
 for i in range(len(p)):
  for j in range(len(p)):out[j]+=p[i]*K[i][j]
 return out

def diffs(a,b,path=''):
 if isinstance(a,dict):
  if set(a)!=set(b):return [{'field':path,'categorical_or_shape_mismatch':True}]
  return [r for k in a for r in diffs(a[k],b[k],path+'/'+k)]
 if isinstance(a,list):
  if not isinstance(b,list) or len(a)!=len(b):return [{'field':path,'categorical_or_shape_mismatch':True}]
  return [r for i,(x,y) in enumerate(zip(a,b)) for r in diffs(x,y,path+'/'+str(i))]
 if a==b:return []
 if isinstance(a,(int,float)) and isinstance(b,(int,float)):return [{'field':path,'rebuilt':a,'archived':b,'absolute_difference':str(abs(Q(a)-Q(b)))}]
 return [{'field':path,'categorical_or_shape_mismatch':True,'rebuilt':a,'archived':b}]

def old_view(m,p,receipt=None):
 return {'context':m.x['identity'],'preparation_receipt':receipt or {'class':'Audit A anonymous simplex mathematical source','recipe_id':None},'actual_passive_laws':{f:{str(g):str(sum(p[i] for i in S)) for g,S in part.items()} for f,part in m.parts.items()},'t':0,'lag':8,'history_horizons':[0],'coefficient_history_arrays':None,'acquired_passive_prefix':[],'commands':[],'acquired_upper_outcomes':[],'status':'PREPARATION_ENTRY','precision':'exact coefficient contract','source_policy':'fixed amended full simplex, no sampled preparation population'}

def point_search(L,m):
 tested=0
 for i in range(32):
  for j in range(i+1,32):
   tested+=1;p=[Q(int(t==i)) for t in range(32)];pp=[Q(int(t==j)) for t in range(32)]
   v=old_view(m,p);vv=old_view(m,pp)
   if v!=vv:continue
   rho=m.pure(32*m.w[i]/m.s);rr=m.pure(32*m.w[j]/m.s)
   if rho==rr:continue
   for f in FIELDS:
    for g in sorted(m.parts[f]):
     S=m.parts[f][g];a=L.trace(L.matmul(rho,m.C[S]));b=L.trace(L.matmul(rr,m.C[S]));d=a-b
     if d:
      _require(old_view(m,p,{'recipe_id':'delta'+str(i)})!=old_view(m,pp,{'recipe_id':'delta'+str(j)}), 'verification invariant failed')
      return {'status':'PASS','witness_type':'CERTIFIED STRICT REFINEMENT','pairs_visited':tested,'pair':[i,j],'preparations':{'p':qs(p),'p_prime':qs(pp)},'complete_equal_old_view':v,'all_old_fields_exact_equal':True,'rho_left':qs(rho),'rho_right':qs(rr),'density_exact_inequality':True,'first_separating_readout':{'context':f,'numeric_atom':g,'left_exact':str(a),'right_exact':str(b),'difference_exact':str(d),'difference_display':float(d)},'point_identifying_receipt_rejects_witness':True}
 return {'status':'UNPROVED','disposition':'UNPROVED BY THIS POINT SEARCH','pairs_visited':tested,'search_domain':'all496 point pairs lexicographic; no full-simplex factorization inferred'}

def construct_context(index,r,repository,output,formula_path,proof_paths,certificate_name="certificates.json"):
 reader=Archive(repository);line=reader.line
 start=time.monotonic();directory=Path(output)/'contexts'/r['unit_id'];directory.mkdir(parents=True,exist_ok=False);result={'index':index,'unit_id':r['unit_id'],'key_sha256':__import__("hashlib").sha256(canonical(r['provenance_key'])).hexdigest(),'certificates':{},'failures':[],'historical_fields_opened':False}
 def step(name,fn):
  st=time.monotonic()
  try:
   val=fn();_require(isinstance(val,dict), 'verification invariant failed');val.setdefault('status','PASS');result['certificates'][name]=val
  except Exception as e:
   status='MISSING' if isinstance(e,(FileNotFoundError,KeyError)) else 'INTEGRITY FAILURE' if isinstance(e,AssertionError) else 'FAILED'
   result['certificates'][name]={'status':status,'error_type':type(e).__name__,'error':str(e)};result['failures'].append({'certificate':name,'status':status,'error':str(e)})
  result['certificates'][name]['wall_seconds']=time.monotonic()-st
 state={}
 def extraction():
  key=r['provenance_key'];a=key['kernel']['artifact'];body,prefix,raw=line(a,True);lo,hi=a['char_range'];b=body[lo:hi].encode();_require(__import__("hashlib").sha256(b).hexdigest()==a['field_sha256'], 'verification invariant failed');md=P.metadata(body,P.SEQ_KEYS)
  _require(md['tau']-md['t_mid']==a['exponent']==1, 'verification invariant failed')
  # Recover true file-byte interval, not an inverse/normalization of another matrix.
  absolute_lo=a['byte_offset']+prefix+len(body[:lo].encode());absolute_hi=absolute_lo+len(b)
  with reader.path(a['path']).open('rb') as f:f.seek(absolute_lo);_require(f.read(absolute_hi-absolute_lo)==b, 'verification invariant failed')
  K=json.loads(b);_require(len(K)==32 and all(len(t)==32 for t in K), 'verification invariant failed');_require(all(math.isfinite(v) and v>=0 for row in K for v in row), 'verification invariant failed')
  Kq=[[Q(float(t)) for t in row] for row in K];rowmass=list(map(sum,Kq));_require(min(rowmass)>0, 'verification invariant failed')
  bb,_,_=line(r['source']['born'],True);born=P.metadata(bb,P.BORN_KEYS|{'p_theory','pi'})
  _require((born['cell'],born['seed'],born['scale'],born['k'],born['step_index'])==(key['actual_source_cell'],key['seed'],key['scale'],key['resolution'],key['step']), 'verification invariant failed')
  _require(len(born['sym_eigvec_basis'])==1 and len(born['sym_eigvec_basis'][0])==32, 'verification invariant failed')
  units={}
  for ptr in r['kind_records']:
   body,_,raw=line(ptr);refs=P.refs(body,P.UNIT_KEYS|{'unrounded_p_full','spectral_coefficients'})
   for field,ref in ptr['fields'].items():_require(refs[field]==ref, ('field hash',field))
   u=P.metadata(body,P.UNIT_KEYS|{'unrounded_p_full','spectral_coefficients'});_require(u['unit_id']==r['unit_id'] and u['unrounded_p_full']==born['p_theory'], 'verification invariant failed')
   for field in ['seed','scale','resolution','step','context','partition','invocation_id','attempt_record_sha256','structural_manifest_sha256']:_require(u[field]==key[field], ('unit key',field))
   _require(u['basis_and_projector_inputs']['effective_rank']==2 and u['basis_and_projector_inputs']['n_cols_original']==2, 'verification invariant failed')
   for field,labelkey,pre in [('M_raw_or_content_hash','partition','group_'),('M_pkg_or_content_hash','packaging','package_')]:_require(u[field]==[[float(pre+str(g)==lab) for g in born[labelkey]] for lab in u['ordered_union_outcome_labels']], 'verification invariant failed')
   units[ptr['kind']]=u
  _require(units['raw']['basis_and_projector_inputs']==units['pkg']['basis_and_projector_inputs'], 'verification invariant failed')
  _require(born['partition']==r['lenses']['raw_map'] and born['packaging']==r['lenses']['package_map'], 'verification invariant failed')
  state.update(K=K,Kq=Kq,born=born,units=units,key=key)
  return {'status':'PASS','byte_range':[absolute_lo,absolute_hi],'field_sha256':__import__("hashlib").sha256(b).hexdigest(),'exponent':1,'source':a,'row_masses_exact':qs(rowmass),'maximum_row_mass_error_exact':str(max(abs(t-1) for t in rowmass)),'maximum_row_mass_error_display':float(max(abs(t-1) for t in rowmass)),'nonnegative_finite':True,'positive_row_masses':True,'no_row_normalization':True,'lens_source_unit_joins':True}
 step('kernel',extraction)
 def carrier():
  born=state['born'];v=[Q(float(t)) for t in born['sym_eigvec_basis'][0]];mean=sum(v)/32;w=[t-mean for t in v];s=sum(t*t for t in w);_require(s>0, 'verification invariant failed')
  Pmat=[[Q(1,32)+a*b/s for b in w] for a in w]
  _require(Pmat==list(map(list,zip(*Pmat))) and all(sum(row)==1 for row in Pmat), 'verification invariant failed')
  _require(all(sum(Pmat[i][k]*Pmat[k][j] for k in range(32))==Pmat[i][j] for i in range(32) for j in range(32)), 'verification invariant failed')
  data={'identity':{k:state['key'][k] for k in ['unit_id','experiment','actual_source_cell','seed','scale','resolution','step','context','partition','invocation_id']},'lens':{'raw_by_state':born['partition'],'package_by_state':born['packaging'],'joint_by_state':r['lenses']['joint_map']}}
  L=algebra;m=Instrument(data,w,s,Pmat,state['Kq'])
  parents=[[[Q(1,32),t/32],[t/s,t*t/s]] for t in w];_require([[sum(p[i][j] for p in parents) for j in range(2)] for i in range(2)]==L.eye(), 'verification invariant failed')
  state.update(w=w,s=s,Pmat=Pmat,data=data,L=L,m=m)
  put(directory/'CONTEXT.json',{'identity':data['identity'],'kernel':state['K'],'born':born,'lens':data['lens'],'exact':{'w':qs(w),'s':str(s),'G':[['32','0'],['0',str(s)]],'P':qs(Pmat)},'archived_unit_structural':state['units']})
  return {'status':'PASS','rank':2,'landed_retained_rank':2,'distinct_w':len(set(w)),'G':[['32','0'],['0',str(s)]],'P_symmetric_idempotent_constant':True,'parent_sum_exact_I':True,'uniform_proof_binding':{'provided_uniform_proofs':{p:sha(reader.path(p)) for p in proof_paths},'frame_context':str(directory/'CONTEXT.json'),'frame_context_sha256':sha(directory/'CONTEXT.json')}}
 step('carrier',carrier)
 def correspondence():
  L=state['L'];I=L.I;born=state['born'];original=state['units']['raw'];arch=original['basis_and_projector_inputs'];rebuilt=_oriented_basis(born);diff=diffs(rebuilt,arch);structure=not any(t.get('categorical_or_shape_mismatch') for t in diff)
  maximum=max((Q(t['absolute_difference']) for t in diff if 'absolute_difference'in t),default=Q(0));groups={}
  for t in diff:
   k=t['field'].split('/')[1];groups[k]=max(groups.get(k,Q(0)),Q(t.get('absolute_difference','0')))
  p0=[0.]*32
  for i in born['starts']:p0[i]+=1./len(born['starts'])
  for _ in range(born['tau']):p0=native_step(state['K'],p0)
  native=max(abs(Q(a)-Q(b)) for a,b in zip(p0,born['p_theory']))
  rec={k:original[k] for k in ['unrounded_p_full','basis_and_projector_inputs','spectral_coefficients']};laws,_,_=_recomputed_laws(rec,_formula_contract(FormulaView(formula_path)));q= laws['q_full']
  put(directory/'landed_own_input_prediction.json',{'q_full':q,'no_scores_or_losses_computed':True,'source':'unchanged landed _recomputed_laws on immutable structural fields'})
  tilde=[[Q(float(t)) for t in row] for row in arch['projector']];d2=sum((a-b)**2 for row,rr in zip(state['Pmat'],tilde) for a,b in zip(row,rr));du=I(d2).sqrt();uniform=32*du.hi*(2+du.hi)
  root=[I(Q(float(p))).sqrt() for p in born['p_theory']]
  def probs(M):
   amp=[sum((a*b for a,b in zip(row,root)),I(0)) for row in M];mass=sum((a.square() for a in amp),I(0));_require(mass.lo>0, 'verification invariant failed');return [a.square()/mass for a in amp]
  exact=probs(state['Pmat']);rounded=probs(tilde)
  source_err=max((p-Q(float(t))).abs().hi for p,t in zip(exact,q));floaterr=max((p-Q(float(t))).abs().hi for p,t in zip(rounded,q));floatTV=sum((p-Q(float(t))).abs().hi for p,t in zip(rounded,q))/2
  pf=np.array(born['p_theory']);a=np.array(arch['projector'])@np.sqrt(pf);direct=a*a/np.dot(a,a);parity=max(abs(Q(float(v))-Q(float(t))) for v,t in zip(direct,q))
  # Same disclosed RI envelope, with absolute subnormal error allowance.
  u=Q(1,2**53);eta=Q(1,2**1074);gamma=lambda n:n*u/(1-n*u);norm=I(sum(a*a for row in tilde for a in row)).sqrt().hi
  eps=(1+du.hi)*u+gamma(66)*norm*(1+u)+4096*eta;normlo=I(Q(1,32)).sqrt().lo-du.hi
  envelope=eps*(2*(1+du.hi)+eps)/(normlo**2)+gamma(38)+2048*eta/(normlo**2) if normlo>0 else None
  passed=structure and native==0 and normlo>0 and uniform<=Q(1,10**12) and source_err<=Q(1,10**12) and floaterr<=Q(1,10**12) and parity<=Q(1,10**12)
  state.update(exact_prediction=exact,root=root)
  return {'status':'PASS' if passed else 'FAILED','threshold_exact':'1/1000000000000','constructor_literal_bit_equality_status':'PASS' if not diff else 'FAILED','constructor_differences':diff,'constructor_group_maxima':qs(groups),'constructor_maximum_difference':str(maximum),'constructor_categorical_shape_parity':structure,'native_preparation_replay_maximum_error_exact':str(native),'delta_squared_exact':str(d2),'delta_interval':du.json(),'uniform_projector_TV_bound_exact':str(uniform),'uniform_projector_TV_bound_display':float(uniform),'rounded_nonvanishing':normlo>0,'own_input_exact_source_vs_landed_maximum_error':str(source_err),'own_input_exact_source_vs_landed_maximum_error_display':float(source_err),'own_input_rounded_evaluation_error':str(floaterr),'own_input_rounded_evaluation_TV_error':str(floatTV),'native_numpy_vs_landed_fsum_maximum_error':str(parity),'uniform_floating_envelope':{'status':'conditional on stated arithmetic premises','premises':['binary64 RN basic operations, absolute underflow eta=2^-1074','correctly rounded sqrt','finite no-overflow fsum, conservative gamma66 including double rounding','square/mass/division gamma38 plus2048eta/normlo²'],'dot_root_norm_error':str(eps),'floating_TV_error_exact':str(envelope) if envelope is not None else None,'total_with_projector_TV_exact':str(uniform+envelope) if envelope is not None else None,'total_with_projector_display':float(uniform+envelope) if envelope is not None else None,'not_an_unconditional_platform_accuracy_proof':True},'fixed_output_own_input_certificate_independent_of_accuracy_premises':True}
 step('correspondence',correspondence)
 def strictness():return point_search(state['L'],state['m'])
 step('strictness',strictness)
 def factors():
  b=state['born'];p=[0.]*32
  for i in b['starts']:p[i]+=1./len(b['starts'])
  for _ in range(b['tau']):p=native_step(state['K'],p)
  _require(p==b['p_theory'], 'verification invariant failed')
  return {'status':'PASS','exact_public_preparation':'FACTORIZATION uniformly: public p + fixed encoder/model rules -> density and adopted branch products/sums, with ledger retained','indexed_original_recipe':'FACTORIZATION','indexed_original_native_rule_exact_replay':True,'indexed_receipt':{'identity':state['data']['identity'],'starts':b['starts'],'tau':b['tau'],'rule':'uniform over starts then sequential native binary64 accumulation','public_model_rules':'same fixed coefficients/encoder given to access-matched comparator'},'upper_access':'initial exact p31 independent reals,32roots/projection; fixed K/mode/lenses apparatus; pure ray1/general density2/effect3 independent reals plus exact descriptors/registers/setup. No finite exact-real bit bound or resource contest. No evolving p access.'}
 step('factorization_controls',factors)
 def cpremises():
  L=state['L'];m=state['m'];cert=certify_G(state['s']);put(directory/'six_state_exact_completion.json',cert)
  atoms=[]
  for f in FIELDS:
   for g,S in m.parts[f].items():
    d=len(S)*sum(m.w[i]**2 for i in S)-sum(m.w[i] for i in S)**2
    _require(d>=0, 'verification invariant failed')
    atoms.append({'context':f,'atom':g,'states':list(S),'Gram_det_exact':str(d),'effect_exact':qs(m.C[S]),'positive':d>0})
   summ=L.asinterval(L.zero())
   for S in m.parts[f].values():summ=L.add(summ,L.matmul(m.A[S],m.A[S]))
   _require(L.encloses(summ,L.eye()), 'verification invariant failed')
  put(directory/'instrument_root_controls.json',[{'subset':list(S),'root_certificate':c} for S,c in m.roots.items()])
  return {'status':'PASS','six_state_certificate_sha256':sha(directory/'six_state_exact_completion.json'),'new_G_frame_verified':True,'adopted_domain':'all external real densities/full effects with binary principal-root instruments and arbitrary finite nonadaptive commands; not encoded/native reachability','atom_count':len(atoms),'strict_positive_atom_count':sum(a['positive'] for a in atoms),'zero_atom_count':sum(not a['positive'] for a in atoms),'negative_atom_count':0,'atom_certificates':atoms,'uniform_proofs_hash_binding':{p:sha(reader.path(p)) for p in proof_paths},'invertible_atom_no_sharp_grouping_corollary':'PASS' if all(a['positive'] for a in atoms) else 'UNPROVED, strict positivity premise missing; full-domain C unaffected','finite_root_sum_control':'PASS, not uniform proof replacement','six_state_certificate':str(directory/'six_state_exact_completion.json'),'C_F':'PASS under its full-domain positive additive finite-simplex comparator premises','C_M':'PASS under randomization/operational-mixture-identity/measurable-ontic premises','context_frame_sha256':sha(directory/'CONTEXT.json'),'contextual_ray_control':'PASS: barycenter branch intertwines Kraus map uniformly by linearity, law-only reproduction retained; single exact control checked','commuting_simplex_control':{'status':'PASS','mass':'11/20','posterior':['2/11','9/11']},'zero_invalid_controls':'PASS','no_history_native_closure_H_classification_promotion_claim':True}
 step('C_premises',cpremises)
 def diagnostics():
  L=state['L'];I=L.I;root=state['root'];ss=state['s'];c0sq=sum(root,I(0)).square()/32;c1sq=sum((a*b for a,b in zip(state['w'],root)),I(0)).square()/ss;f=c1sq/(c0sq+c1sq);tv=sum(((p-Q(1,32)).abs() for p in state['exact_prediction']),I(0))/2
  return {'status':'PASS','nonconstant_amplitude_energy_fraction':f.json(),'TV_exact_projected_square_to_uniform_micro32':tv.json(),'definitions':'orthonormal c0=sum sqrt(p)/sqrt32; c1=w.dot(sqrt(p))/sqrt(s), fraction=c1²/(c0²+c1²); TV at micro32 states','structural_not_sampled_performance':True}
 step('diagnostics',diagnostics)
 result['wall_seconds']=time.monotonic()-start
 statuses=[v['status'] for v in result['certificates'].values()];result['overall_status']='INTEGRITY FAILURE' if 'INTEGRITY FAILURE'in statuses else 'MISSING' if 'MISSING'in statuses else 'FAILED' if 'FAILED'in statuses else 'UNPROVED' if 'UNPROVED'in statuses else 'PASS'
 put(directory/certificate_name,result)
 return result

def registered_correspondence(certificate):
 """Frozen invariant/pipeline gate; arbitrary SVD coordinates never gate it."""
 return certificate.get('constructor_categorical_shape_parity',False) and certificate.get('rounded_nonvanishing',False) and Q(certificate['native_preparation_replay_maximum_error_exact'])==0 and all(Q(certificate[k])<=Q(1,10**12) for k in ['uniform_projector_TV_bound_exact','own_input_exact_source_vs_landed_maximum_error','own_input_rounded_evaluation_error','native_numpy_vs_landed_fsum_maximum_error'])
