"""Analytic carrier and instrument controls; no sampled law or performance task."""
from test_regressions import model,fixture
from fractions import Fraction as Q
from born_ladder import arithmetic as A
from born_ladder.transport import Transport
from born_ladder.ensemble import EnsembleInstrument,canonical_measure
from born_ladder.binary import Binary
from born_ladder.programs import execute,word_effects,compile_program
from born_ladder.packaging import pack_law,pack_event,visible
import pytest

def test_declared_ray_transport_and_ensemble_contract():
 m=model();t=Transport(m.x,m.w,m.s,m.P,m.K);e=EnsembleInstrument(t)
 p=[Q(1,32)]*32
 assert t.encode(p).lo<=0<=t.encode(p).hi
 # Compute the same declared transport via explicit dense propagation rather
 # than its cached quadratic coefficients; this checks the actual update.
 lam=Q(1,3);ray=[(1+lam*w)**2/(32+m.s*lam**2) for w in m.w]
 future=A.mv(A.transpose(m.K),ray);roots=[A.I(v).sqrt() for v in future]
 independent=(32/m.s)*A.isum(w*r for w,r in zip(m.w,roots))/A.isum(roots)
 got=t.g(lam);assert max(got.lo,independent.lo)<=min(got.hi,independent.hi)
 assert got.hi-got.lo<Q(1,10**90)
 assert independent.hi<lam or independent.lo>lam
 for field in e.parts:
  out=e.read(Q(0),field);assert A.isum(out).lo<=1<=A.isum(out).hi
  for g,S in e.parts[field].items():
   b,ray=e.general_branch(1,0,S,1);bb,rr=e.general_branch(-1,0,S,1)
   assert b==bb and ray==rr
 assert canonical_measure([(0,Q(1,4)),(0,Q(1,4)),(1,Q(1,2))])==canonical_measure([(1,Q(1,2)),(0,Q(1,2))])
 with pytest.raises(ValueError):e.general_branch(0,0,(),1)
 # This is an internal construction test, not an original-K compatibility claim.

def test_transport_rejects_truncated_vectors_and_undeclared_operations():
 m=model();t=Transport(m.x,m.w,m.s,m.P,m.K);p=[Q(1,m.n)]*m.n
 for wrong in ([],p[:-1],p+[Q(0)]):
  with pytest.raises(ValueError,match='encoder vector dimension'):t.encode(wrong)
  with pytest.raises(ValueError,match='transport vector dimension'):t.propagate(wrong)
 for bad in ('K3','F','',None):
  with pytest.raises(ValueError,match='undeclared transport operation'):t.propagate(p,bad)
 for operation,K in (('K',t.K),('K2',t.K2)):
  expected=[sum(p[i]*K[i][j] for i in range(m.n)) for j in range(m.n)]
  assert t.propagate(p,operation)==expected

def test_binary_programs_registers_failure_and_idempotence():
 m=model();b=Binary(m);source={'kind':'density','matrix':A.qstrings(m.pure(0)),'protocol':{'public':'unchanged'}}
 for commands in ([],[{'kind':'binary','effect':A.qstrings(A.zero()),'mode':'retain'}],[{'kind':'lens','field':'raw_by_state','mode':'forget'},{'kind':'binary','effect':A.qstrings(m.pure(1)),'mode':'retain'}]):
  run=execute(m,source,commands);assert run['status']=='HALT'
  assert pack_law(run['public'])==run['public']
  Ms,Es=word_effects(m,run['compiled'])
  total=A.asinterval(A.zero())
  for E in Es.values():total=A.add(total,E)
  assert A.encloses(total,A.eye())
 invalid=execute(m,source,[{'kind':'K','mode':'retain'}]);assert invalid['status']=='HALT_FAILURE' and invalid['measurements_completed']==0
 assert execute(m,{'kind':'density','matrix':[['-1','0'],['0','2']],'protocol':{}},[])['operational_state']=='NO_STATE'
 assert execute(m,source,[{'kind':'if','outcome':0}])['status']=='HALT_FAILURE'
 assert not visible([(0,0),(1,0)],[(0,0)],['forget','retain'])
 e=pack_event('test',[(0,0),(1,0)],[(0,0),(1,0)],['forget','retain'],{'public':'retained'});assert pack_event(e)==e
 with pytest.raises(ValueError):pack_law(run['public'],ledger={'concealed':'changed'})

def test_retained_density_mixture_and_binary_zero_branch():
 m=model();b=Binary(m);E=m.pure(1);R=m.validate(A.sub(A.eye(),E));out,mass,p=b.branch(R,E,1)
 assert mass==0 and p is None and out==A.asinterval(A.zero())
 descriptor=lambda R:{'kind':'density','matrix':A.qstrings(R),'protocol':{}}
 a=m.pure(0);c=m.pure(1);mix=A.scale(A.add(a,c),Q(1,2));cmd=[{'kind':'lens','field':'raw_by_state','mode':'forget'}]
 left=execute(m,descriptor(mix),cmd)
 right=execute(m,{'kind':'mixture','components':[[descriptor(a),'1/2'],[descriptor(c),'1/2']],'protocol':{}},cmd)
 assert left['full_rows']==right['full_rows'] and left['public'].public_ledger!=right['public'].public_ledger
 for bad in [A.scale(A.eye(),2),[[Q(1,2),Q(1)],[Q(0),Q(1,2)]],[[0.5,0],[0,0.5]]]:
  with pytest.raises(ValueError):b.roots(bad)

@pytest.mark.parametrize('optimized',[False,True])
def test_frame_and_command_admission_are_not_removable_assertions(optimized):
 import subprocess,sys,textwrap
 code=textwrap.dedent('''
 from fractions import Fraction as Q
 from born_ladder.instruments import Instrument,FIELDS
 from born_ladder.programs import execute
 from born_ladder import arithmetic as A
 w=[Q(-1),Q(0),Q(1)];s=Q(2);n=3
 P=[[Q(1,n)+a*b/s for b in w] for a in w]
 K=[[Q(int(i==j)) for j in range(n)] for i in range(n)]
 context={'identity':{'kind':'synthetic-domain-control'},'lens':{f:[0]*n for f in FIELDS}}
 bad={'identity':context['identity'],'lens':{f:[0] for f in FIELDS}}
 try:Instrument(bad,w,s,P,K)
 except ValueError:pass
 else:raise RuntimeError('truncated lens was admitted')
 try:Instrument(context,w,s+1,P,K)
 except ValueError:pass
 else:raise RuntimeError('inconsistent frame norm was admitted')
 source={'kind':'density','matrix':[['3/5','2/5'],['3/5','2/5']],'protocol':{}}
 command=[{'kind':'lens','field':'raw_by_state','mode':'retain'}]
 for corruption in ('incomplete','mixed_sign'):
  m=Instrument(context,w,s,P,K);block=m.parts['raw_by_state'][0]
  if corruption=='incomplete':
   m.C[block]=A.scale(A.eye(),Q(1,2));m.A[block]=A.principal(m.C[block])[0]
  else:m.A[block]=A.asinterval([[Q(1),Q(0)],[Q(0),Q(-1)]])
  result=execute(m,source,command)
  if result['status']!='HALT_FAILURE' or result['records'][0]!='PUBLIC_FAILURE:INVALID_PROGRAM':
   raise RuntimeError('invalid apparatus returned a law: '+corruption)
  if result['operational_state']!='UNCHANGED_INITIAL' or result['measurements_completed']!=0:
   raise RuntimeError('invalid apparatus changed the initial state')
 ''')
 result=subprocess.run([sys.executable,*(['-O'] if optimized else []),'-c',code],capture_output=True,text=True)
 assert result.returncode==0,result.stdout+result.stderr
