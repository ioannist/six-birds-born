"""Independent Fraction/Decimal audit implementation.

No production arithmetic, carrier constructor, interval or instrument imports.
Exact Fraction/Decimal algorithms independently recompute source quantities.
"""
from fractions import Fraction as F
from decimal import Decimal,localcontext
from pathlib import Path
import json,hashlib

def _require(condition,message):
 # Mathematical verification must not disappear under Python optimization.
 if not condition:raise AssertionError(message)


def fraction(x):return F(x)
def recompute(context):
 v=list(map(F,context['born']['sym_eigvec_basis'][0]));n=len(v);avg=sum(v)/n;w=[x-avg for x in v];s=sum(x*x for x in w)
 P=[[F(1,n)+a*b/s for b in w] for a in w]
 _require(all(sum(row)==1 for row in P), 'exact verification invariant failed')
 # Contract the two exact rank-one factors, rather than cubically multiplying
 # the expanded matrix. For P_ij=1/n+w_i*w_j/s, the product is
 # 1/n+(w_i+w_j)*sum(w)/(n*s)+w_i*w_j*sum(w^2)/s^2.
 # This checks the same identity over Fraction, including subnormal frames.
 gram01=sum(w);gram11=sum(x*x for x in w)
 _require(all(F(1,n)+(w[i]+w[j])*gram01/(n*s)+w[i]*w[j]*gram11/(s*s)==P[i][j]
              for i in range(n) for j in range(n)), 'exact verification invariant failed')
 K=[[F(x) for x in row] for row in context['kernel']];row_error=max(abs(sum(row)-1) for row in K)
 atom=[];lens=context['lens'];families=('raw_by_state','package_by_state','joint_by_state');witness=None;visited=0
 parts={f:{g:[i for i,x in enumerate(lens[f]) if x==g] for g in sorted(set(lens[f]))} for f in families}
 for f,groups in parts.items():
  for g,S in groups.items():atom.append((f,g,len(S)*sum(w[i]**2 for i in S)-sum(w[i] for i in S)**2))
 def read(i,S):return sum((1+n*w[i]*w[k]/s)**2 for k in S)/(n*(1+n*w[i]**2/s))
 for i in range(n):
  for j in range(i+1,n):
   visited+=1
   if any(lens[f][i]!=lens[f][j] for f in families) or w[i]==w[j]:continue
   for f in families:
    for g,S in parts[f].items():
     d=read(i,S)-read(j,S)
     if d:witness={'pair':[i,j],'context':f,'atom':g,'difference':str(d),'visited':visited};break
    if witness:break
   if witness:break
  if witness:break
 # Preparation replay reproduces native accumulation order, not a matrix product.
 p=[0.]*n
 for i in context['born']['starts']:p[i]+=1./len(context['born']['starts'])
 for _ in range(context['born']['tau']):
  out=[0.]*n
  for i in range(n):
   for j in range(n):out[j]+=p[i]*context['kernel'][i][j]
  p=out
 _require(p==context['born']['p_theory'], 'exact verification invariant failed')
 tilde=[[F(x) for x in rr] for rr in context['archived_unit_structural']['raw']['basis_and_projector_inputs']['projector']]
 delta2=sum((a-b)**2 for row,rr in zip(P,tilde) for a,b in zip(row,rr))
 with localcontext() as c:
  c.prec=180
  dd=lambda x:Decimal(x.numerator)/Decimal(x.denominator)
  root=[dd(F(x)).sqrt() for x in p];amp=[sum(dd(a)*b for a,b in zip(row,root)) for row in P];mass=sum(a*a for a in amp)
  predictions=[a*a/mass for a in amp]
  energy=(sum(dd(a)*b for a,b in zip(w,root))**2/dd(s))/(sum(root)**2/n+sum(dd(a)*b for a,b in zip(w,root))**2/dd(s))
  tv=sum(abs(q-Decimal(1)/n) for q in predictions)/2
 return {'w':list(map(str,w)),'s':str(s),'P':[[str(x) for x in row] for row in P],'maximum_row_mass_error_exact':str(row_error),'delta_squared_exact':str(delta2),'witness':witness,'atoms':[(f,g,str(d)) for f,g,d in atom],'zero_atoms':sum(d==0 for _,_,d in atom),'energy_decimal_control':str(energy),'tv_decimal_control':str(tv),'predictions_decimal_control':list(map(str,predictions))}

def check_context(path,certificate_name="certificates.json",*,recomputed=None):
 d=Path(path);ctx=json.loads((d/'CONTEXT.json').read_text());cert=json.loads((d/certificate_name).read_text())['certificates'];r=recompute(ctx) if recomputed is None else recomputed
 _require(r['w']==ctx['exact']['w'] and r['s']==ctx['exact']['s'] and r['P']==ctx['exact']['P'], 'exact verification invariant failed')
 _require(r['maximum_row_mass_error_exact']==cert['kernel']['maximum_row_mass_error_exact'] and r['delta_squared_exact']==cert['correspondence']['delta_squared_exact'], 'exact verification invariant failed')
 w=r['witness'];cs=cert['strictness'];_require(w['pair']==cs['pair'] and w['visited']==cs['pairs_visited'] and w['context']==cs['first_separating_readout']['context'] and w['atom']==cs['first_separating_readout']['numeric_atom'] and w['difference']==cs['first_separating_readout']['difference_exact'], 'exact verification invariant failed')
 _require(r['zero_atoms']==cert['C_premises']['zero_atom_count'], 'exact verification invariant failed')
 # Independently validate every stored principal-root scalar/rational bound.
 for item in json.loads((d/'instrument_root_controls.json').read_text()):
  subset=item['subset'];w=list(map(F,r['w']));n=len(w);ss=F(r['s']);E=[[F(len(subset),n),sum(w[i] for i in subset)/n],[sum(w[i] for i in subset)/ss,sum(w[i]**2 for i in subset)/ss]]
  verify_root_certificate(E,item['root_certificate'])
 # Decimal is a separate high-precision CONTROL, not an interval proof.
 for name,value in [('nonconstant_amplitude_energy_fraction',r['energy_decimal_control']),('TV_exact_projected_square_to_uniform_micro32',r['tv_decimal_control'])]:
  interval=cert['diagnostics'][name];_require(abs(Decimal(value)-Decimal(float(F(interval['lo']))))<Decimal('1e-14'), 'exact verification invariant failed')
 return {'unit_id':ctx['identity']['unit_id'],'status':'PASS','exact_source_carrier_witness_atoms_recomputed':True,'decimal_diagnostics_control':True,'not_a_replacement_for_outward_certificates':True}

def independent_type7(values):
 a=sorted(F(v) for v in values);n=len(a)
 if not n:return None
 out={}
 for name,p in [('min',F(0)),('q1',F(1,4)),('median',F(1,2)),('q3',F(3,4)),('max',F(1))]:
  pos=(n-1)*p;k=pos.numerator//pos.denominator;f=pos-k;out[name]=str(a[k]*(1-f)+a[min(k+1,n-1)]*f)
 return out

def verify_summaries(attachments,summaries):
 for r in summaries:
  values=[]
  for a in attachments:
   if a['view']==r['view'] and a['fields'].get('eligibility') is True:
    x=a['fields'].get(r['metric'],{}).get(r['model_or_recorded_contrast'])
    if x is not None:values.append(x)
  _require(independent_type7(values)==r['quantiles']['exact'], 'exact verification invariant failed')
 return len(summaries)

def verify_root_certificate(effect,certificate):
 """Check the principal branch, given an admitted G-positive effect.

 Squaring alone also accepts negative and mixed-sign square roots. For a
 rational principal root D=det(R)>=0 and Z=tr(R)>0 are the exact positive
 radicals sqrt(det(C)) and sqrt(tr(C)+2D); the formula (C+D I)/Z fixes R.
 No production sqrt/enclosure calls are used.
 """
 def require(condition,message):
  # These are verification gates, not debug assertions: Python -O must not
  # turn a false certificate into a successful mathematical check.
  if not condition:raise AssertionError('invalid principal-root certificate: '+message)
 require(len(effect)==2 and all(len(row)==2 for row in effect),'effect shape')
 C=[[F(x) for x in row] for row in effect];d=C[0][0]*C[1][1]-C[0][1]*C[1][0];t=C[0][0]+C[1][1]
 if certificate['method']=='exact zero':
  require(all(x==0 for row in C for x in row),'nonzero effect in zero branch')
  root=certificate['rational_root']
  require(len(root)==2 and all(len(row)==2 for row in root),'zero root shape')
  require(all(F(x)==0 for row in root for x in row),'nonzero root in zero branch')
  return True
 require(str(d)==certificate['det_C'] and str(t)==certificate['trace_C'],'effect scalar commitments')
 require(d>=0 and t>0,'effect scalar domain')
 if 'rational_root' in certificate:
  require(len(certificate['rational_root'])==2 and all(len(row)==2 for row in certificate['rational_root']),'rational root shape')
  R=[[F(x) for x in row] for row in certificate['rational_root']]
  require([[sum(R[i][k]*R[k][j] for k in range(2)) for j in range(2)] for i in range(2)]==C,'root square')
  D=R[0][0]*R[1][1]-R[0][1]*R[1][0];Z=R[0][0]+R[1][1]
  require(D>=0 and D*D==d and Z>0 and Z*Z==t+2*D,'positive principal scalars')
  require(R==[[(C[i][j]+(D if i==j else 0))/Z for j in range(2)] for i in range(2)],'principal matrix formula')
 else:
  a,b=map(F,[certificate['sqrt_det']['lo'],certificate['sqrt_det']['hi']]);lo,hi=map(F,[certificate['denominator']['lo'],certificate['denominator']['hi']])
  require(0<=a<=b and a*a<=d<=b*b and 0<lo<=hi and lo*lo<=t+2*a and hi*hi>=t+2*b,'ordered positive radical bounds')
 return True
