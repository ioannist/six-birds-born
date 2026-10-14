"""Numerical extraction/rendering shared by production and external checks."""
from fractions import Fraction as Q
from fractions import Fraction as F
from pathlib import Path
import json, math
FIELDS=("raw_by_state", "package_by_state", "joint_by_state")

def rational(x):
 q=F(x);return f'({q.numerator} : ℚ) / {q.denominator}'

def vector(xs, typ):return '!['+',\n '.join(str(x) for x in xs)+']'

def extract(context, strictness):
 c=context;d=strictness
 r=d['certificate']['readout_splits'][0]
 if d['certificate']['point_indices']!=[1,3] or r['context']!='raw_by_state' or r['outcome']!=0:raise ValueError('RI registered point pair/readout differs')
 if F(r['left']['lo'])!=F(r['left']['hi']) or F(r['right']['lo'])!=F(r['right']['hi']):raise ValueError('RI exact point readout differs')
 gap=F(r['left']['lo'])-F(r['right']['lo'])
 if not F(r['difference']['lo'])<=gap<=F(r['difference']['hi']):raise ValueError('RI gap enclosure differs')
 w=list(map(F,c['exact']['w']));s=F(c['exact']['s'])
 if len(w)!=32 or sum(w)!=0 or s<=0 or sum(x*x for x in w)!=s:raise ValueError('RI exact frame differs')
 labels=[c['lens'][field] for field in FIELDS]
 if any(len(q)!=32 or sorted(set(q))!=list(range(size)) for q,size in zip(labels,(2,3,3))):raise ValueError('RI label alphabets differ')
 return dict(w=w,s=s,labels=labels,gap=gap,lo=F(r['difference']['lo']),hi=F(r['difference']['hi']))


def render_checked(data):
 w,s,labels,gap,lo,hi=(data[k] for k in ('w','s','labels','gap','lo','hi'))
 out='import BornCalculus.Definitions\nnamespace BornCalculus\n'
 out+='def riWQ : Fin 32 → ℚ := '+vector([rational(x) for x in w], 'ℚ')+'\n'
 out+='def riSQ : ℚ := '+rational(s)+'\n'
 for i,(name,typ) in enumerate([('riRaw','Fin 2'),('riPackage','Fin 3'),('riJoint','Fin 3')]):
  out+=f'def {name} : Fin 32 → {typ} := '+vector(labels[i],typ)+'\n'
 out+='def riGapQ : ℚ := '+rational(gap)+'\n'
 out+='def riGapLoQ : ℚ := '+rational(lo)+'\n'
 out+='def riGapHiQ : ℚ := '+rational(hi)+'\n'
 out+='end BornCalculus\n'
 return out


def render(input_root):
 root=Path(input_root)
 return render_checked(extract(json.loads((root/'CONTEXT.json').read_text()),json.loads((root/'initial_strictness_certificate.json').read_text())))
