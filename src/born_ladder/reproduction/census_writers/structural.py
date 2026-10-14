"""Unchanged exact witness helpers; construction backend is public."""
from .common import *


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
   for f in L.FIELDS:
    for g in sorted(m.parts[f]):
     S=m.parts[f][g];a=L.trace(L.matmul(rho,m.C[S]));b=L.trace(L.matmul(rr,m.C[S]));d=a-b
     if d:
      assert old_view(m,p,{'recipe_id':'delta'+str(i)})!=old_view(m,pp,{'recipe_id':'delta'+str(j)})
      return {'status':'PASS','witness_type':'CERTIFIED STRICT REFINEMENT','pairs_visited':tested,'pair':[i,j],'preparations':{'p':qs(p),'p_prime':qs(pp)},'complete_equal_old_view':v,'all_old_fields_exact_equal':True,'rho_left':qs(rho),'rho_right':qs(rr),'density_exact_inequality':True,'first_separating_readout':{'context':f,'numeric_atom':g,'left_exact':str(a),'right_exact':str(b),'difference_exact':str(d),'difference_display':float(d)},'point_identifying_receipt_rejects_witness':True}
 return {'status':'UNPROVED','disposition':'UNPROVED BY THIS POINT SEARCH','pairs_visited':tested,'search_domain':'all496 point pairs lexicographic; no full-simplex factorization inferred'}
