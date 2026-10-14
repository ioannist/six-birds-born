"""Targeted closure regressions, using compact non-empirical synthetic controls."""
import sys,json,hashlib,itertools,os
from pathlib import Path
from fractions import Fraction as Q
import pytest
sys.dont_write_bytecode=True
sys.set_int_max_str_digits(0)
from born_ladder import arithmetic as A
from born_ladder.instruments import Instrument,FIELDS
from born_ladder.certificates import point_search,diffs
from born_ladder.archive import Archive,put,verify_files
from born_ladder.summaries import quantiles,summarise
from born_ladder.independent import recompute,independent_type7

from synthetic import fixture

def model(name='ordinary'):
 c=fixture(name)['context'];return Instrument(c,list(map(Q,c['exact']['w'])),Q(c['exact']['s']),[[Q(x) for x in r] for r in c['exact']['P']],[[Q(x) for x in r] for r in c['kernel']])

def test_basis_pivot_difference_is_not_projector_failure():
 f=fixture('basis');c=f['reviewed_certificates']['certificates']['correspondence']
 assert c['status']=='FAILED' and Q(c['constructor_maximum_difference'])>Q(1,10**12)
 assert c['constructor_literal_bit_equality_status']=='FAILED'
 assert Q(c['uniform_projector_TV_bound_exact'])<Q(1,10**12)
 assert f['completion']['registered_numerical_gate_status']=='PASS'
 independent=recompute(f['context']);assert independent['delta_squared_exact']==c['delta_squared_exact']

def test_exact_trine_no_float_coercion():
 for s in (Q(32),Q(1,2**2200),Q(fixture('tiny')['context']['exact']['s'])):
  c=A.certify_G(s);assert c['YES_table_exact'][1]==['1/4',1,'1/4'] and len(c['five_mixture_identities'])==5
 from born_ladder.independent_trine import check
 f=fixture('tiny');s0=Q(f['context']['exact']['s']);assert max(s0.numerator.bit_length(),s0.denominator.bit_length())>1024
 assert check(A.certify_G(s0))['mixture_identities']==5
 assert f['reviewed_certificates']['certificates']['C_premises']['error_type']=='OverflowError'

def test_singleton_zero_determinant_is_nonzero_not_projector():
 m=model('basis');found=[]
 for f in FIELDS:
  for S in m.parts[f].values():
   if len(S)==1:
    E=m.C[S];assert A.det(E)==0 and E!=A.zero() and 0<A.trace(E)<1
    assert A.matmul(E,E)!=E;found.append(S)
 assert found

def test_tiny_exact_witness_and_frozen_order():
 f=fixture('tiny');m=model('tiny');s=point_search(A,m);old=f['reviewed_certificates']['certificates']['strictness'];s.pop('wall_seconds',None);old.pop('wall_seconds',None)
 assert s==old
 d=Q(s['first_separating_readout']['difference_exact']);assert 0<abs(d)<Q(1,10**60)
 independent=recompute(f['context']);assert independent['witness']['difference']==str(d) and independent['witness']['pair']==s['pair']

def test_altered_inputs_seals_and_write_once_refused(tmp_path):
 p=tmp_path/'data';p.write_bytes(b'original');h=hashlib.sha256(p.read_bytes()).hexdigest();verify_files(tmp_path,{'data':h})
 seal={'outputs':{'data':h}};(tmp_path/'seal.json').write_text(json.dumps(seal));Archive(tmp_path).verify_seal('seal.json')
 p.write_bytes(b'changed')
 with pytest.raises(ValueError):verify_files(tmp_path,{'data':h})
 with pytest.raises(ValueError):Archive(tmp_path).verify_seal('seal.json')
 with pytest.raises(FileExistsError):put(p,b'replacement')
 with pytest.raises(ValueError):Archive(tmp_path).path('../outside')

def test_type7_no_structural_filter_missing_null_failure():
 rows=[]
 for view in ['raw','pkg']:
  for i,(v,status,eligible) in enumerate([(0.,'FAILED',True),(2.,'PASS',True),(None,'PASS',True),(1.,'PASS',False)]):
   rows.append({'view':view,'unit_id':str(i),'status':'PASS','structural_overall_status':status,'fields':{'eligibility':eligible,'dtv_loss':{'q_full':v},'exclusion_reason_code':None},'original_failure':{'status':'FAILED','error':None}})
 s=summarise(rows,4);r=next(x for x in s if x['view']=='raw' and x['metric']=='dtv_loss' and x['model_or_recorded_contrast']=='q_full')
 assert r['quantiles']['exact']==independent_type7([0.,2.]) and r['quantiles']['exact']['q1']=='1/2'
 assert r['historically_eligible_finite_denominator']==2 and r['excluded_count']==1 and r['missing_count']==1 and not r['structural_status_filter']
 assert rows[0]['structural_overall_status']=='FAILED' and rows[2]['fields']['dtv_loss']['q_full'] is None and rows[0]['original_failure']['error'] is None
 assert quantiles([])['exact'] is None

def test_roots_gauge_frame_zero_and_density_domain():
 m=model();R=m.pure(0);J=[[Q(1),Q(1,3)],[Q(0),Q(1)]];Ji=[[Q(1),Q(-1,3)],[Q(0),Q(1)]]
 for S,E in m.C.items():
  root=m.A[S];assert A.encloses(A.matmul(root,root),E)
  transformed=A.matmul(A.matmul(Ji,root),J);root2=A.principal(A.matmul(A.matmul(Ji,E),J))[0]
  assert all(max(x.lo,y.lo)<=min(x.hi,y.hi) for rr,ss in zip(transformed,root2) for x,y in zip(rr,ss))
 z,mass,posterior=m.branch(R,());assert mass.hi==0 and posterior is None
 for bad in ([[Q(1)]],[[Q(-1),0],[0,Q(2)]],[[1,1],[0,0]]):
  with pytest.raises(ValueError):m.validate(bad)

def test_nonadaptive_words_normalization_composition_and_forgetting():
 m=model();R=m.pure(0)
 for cs in [(),(FIELDS[0],),(FIELDS[0],FIELDS[1]),(FIELDS[0],)*3]:
  words=list(itertools.product(*(m.parts[f] for f in cs)));total=A.asinterval(A.zero())
  for gs in words:
   M,E=m.word(cs,gs);total=A.add(total,E)
   for k in range(len(cs)+1):
    left,_=m.word(cs[:k],gs[:k]);right,_=m.word(cs[k:],gs[k:]);other=A.matmul(right,left)
    assert all(max(x.lo,y.lo)<=min(x.hi,y.hi) for rr,ss in zip(M,other) for x,y in zip(rr,ss))
  assert A.encloses(total,A.eye())
 raw=m.nonselective(R,FIELDS[0]);pkg=m.nonselective(R,FIELDS[1]);assert A.separated(raw,pkg) # effect I never quotients instruments
 with pytest.raises(ValueError):m.word((FIELDS[0],),())
 with pytest.raises(KeyError):m.word(('adaptive/if',),(0,))

def test_mixture_instantaneous_trace_and_preparation_receipts():
 m=model();R0=m.pure(0);R1=m.pure(1);R=A.scale(A.add(R0,R1),Q(1,2));m.validate(R)
 for E in m.C.values():assert A.trace(A.matmul(R,E))==(A.trace(A.matmul(R0,E))+A.trace(A.matmul(R1,E)))/2
 from born_ladder.certificates import old_view
 p=[Q(1,32)]*32;v=old_view(m,p);assert v['preparation_receipt']['recipe_id'] is None
 assert old_view(m,p,{'recipe_id':'public1'})!=old_view(m,p,{'recipe_id':'public2'})
 # Derive the finite-table contradiction from this frame's actual trine:
 # the three preparations average to I/2, so deterministic YES values would
 # sum to 3/2; no triple of binary values does. This is not the global theorem.
 cert=A.certify_G(m.s);from born_ladder.independent_trine import check
 assert check(cert)['mixture_identities']==5
 target=sum(Q(row[j]) for row in cert['YES_table_exact'][:3] for j in [0])/3
 assert target==Q(1,2)
 assert all(sum(bits)/Q(3)!=target for bits in itertools.product([Q(0),Q(1)],repeat=3))

def test_independent_root_bound_checks():
 from born_ladder.independent import verify_root_certificate
 m=model('tiny')
 for S,E in m.C.items():assert verify_root_certificate(E,m.roots[S])

def test_registered_gate_excludes_extra_coordinate_threshold():
 from born_ladder.certificates import registered_correspondence
 c=fixture('basis')['reviewed_certificates']['certificates']['correspondence']
 assert registered_correspondence(c) and c['status']=='FAILED'
 changed=dict(c);changed['uniform_projector_TV_bound_exact']='1/1000';assert not registered_correspondence(changed)

@pytest.mark.parametrize('optimized',[False,True])
def test_independent_exact_verification_survives_optimization(optimized):
 import subprocess,textwrap
 code=textwrap.dedent('''
 from copy import deepcopy
 from born_ladder.arithmetic import certify_G,normalize
 from born_ladder.independent_trine import check
 certificate=certify_G(32)
 if check(certificate)['status']!='PASS':raise RuntimeError('valid trine rejected')
 for corruption in ('table','root_sign','mixture','shape'):
  bad=deepcopy(certificate)
  if corruption=='table':bad['YES_table_exact'][0][0]='0'
  if corruption=='root_sign':bad['states_and_sharp_yes_effects'][1][0][1]['root']='negative square root'
  if corruption=='mixture':bad['five_mixture_identities'][0][0][1]='-1/2'
  if corruption=='shape':bad['states_and_sharp_yes_effects'][0]=[]
  try:check(bad)
  except AssertionError:pass
  else:raise RuntimeError('false certificate accepted: '+corruption)
 for vector in ([],[0,0],[-1,0]):
  try:normalize(vector)
  except ValueError:pass
  else:raise RuntimeError('invalid normalization accepted')
 ''')
 r=subprocess.run([sys.executable,*(['-O'] if optimized else []),'-c',code],capture_output=True,text=True)
 assert r.returncode==0,r.stdout+r.stderr
