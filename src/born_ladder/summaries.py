"""Descriptive attachment summaries; no scores are recomputed.
No structural-status filtering.
"""
from fractions import Fraction as Q
from collections import Counter
import math
from .arithmetic import qserial
def _require(condition,message):
 # Invariants are executable verification gates, including under Python -O.
 if not condition:raise AssertionError(message)


def quantiles(values):
 a=sorted(Q(float(v)) for v in values);n=len(a)
 if not n:return {'n':0,'exact':None,'display':None}
 out={}
 for name,p in [('min',Q(0)),('q1',Q(1,4)),('median',Q(1,2)),('q3',Q(3,4)),('max',Q(1))]:
  u=(n-1)*p;j=u.numerator//u.denominator;t=u-j;out[name]=(1-t)*a[j]+t*a[min(j+1,n-1)]
 return {'n':n,'exact':qserial(out),'display':{k:float(v) for k,v in out.items()}}

def summarise(attached,expected_contexts):
 models=set(['q_full','q_diag','L_clipped_linear','L_uniform','L_full']);metrics=set(['dtv_loss','brier_score']);contrasts=set()
 for a in attached:
  for metric in metrics:
   models.update(a.get('fields',{}).get(metric,{}))
  contrasts.update(k for k in a.get('fields',{}).get('pairwise_contrast',{}) if 'q_diag' in k and 'q_full' in k)
 allrows=[]
 for kind in ['raw','pkg']:
  rows=[a for a in attached if a['view']==kind];_require(len(rows)==expected_contexts, 'verification invariant failed')
  for metric,model in [(metric,model) for metric in sorted(metrics) for model in sorted(models)]+[('pairwise_contrast',k) for k in sorted(contrasts)]:
   included=[];excluded_values=[];missing=Counter();excluded=Counter();missing_ids=[];excluded_ids=[];allfinite=[]
   for row in rows:
    f=row.get('fields',{});eligible_value=f.get('eligibility');reason=f.get('exclusion_reason_code')
    if eligible_value is False:excluded[str(reason)]+=1;excluded_ids.append(row['unit_id'])
    v=f.get(metric,{}).get(model) if isinstance(f.get(metric,{}),dict) else None
    finite=isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
    if not finite:
     code='INTEGRITY FAILURE' if row['status']=='INTEGRITY FAILURE' else 'MISSING ROW' if not f else 'ABSENT/NULL/NONFINITE METRIC'
     missing[code]+=1;missing_ids.append(row['unit_id']);continue
    allfinite.append(v)
    if eligible_value is True:included.append(v)
    elif eligible_value is False:excluded_values.append(v)
    else:missing['ELIGIBILITY MISSING/NULL']+=1;missing_ids.append(row['unit_id'])
   allrows.append({'view':kind,'metric':metric,'model_or_recorded_contrast':model,'scheduled_contexts':expected_contexts,'historically_eligible_finite_denominator':len(included),'quantiles':quantiles(included),'missing_count':sum(missing.values()),'missing_reasons':dict(missing),'missing_unit_ids':missing_ids,'excluded_count':sum(excluded.values()),'exclusion_reasons':dict(excluded),'excluded_unit_ids':excluded_ids,'excluded_finite_denominator':len(excluded_values),'excluded_values_quantiles':quantiles(excluded_values),'all_available_finite_quantiles_descriptive_only':quantiles(allfinite),'structural_status_filter':False,'contrast_definition':'recorded original field, never recomputed from losses' if metric=='pairwise_contrast' else 'original recorded metric'})
 return allrows
