"""Exact serialization/quantiles recovered from the census writer."""
from fractions import Fraction as Q
from pathlib import Path
import hashlib,json,time,math


def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def hb(b):return hashlib.sha256(b).hexdigest()

def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def qs(x):
 if isinstance(x,Q):return str(x)
 if isinstance(x,dict):return {str(k):qs(v) for k,v in x.items()}
 if isinstance(x,(list,tuple)):return [qs(v) for v in x]
 return x

def put(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:f.write(x if isinstance(x,str) else json.dumps(qs(x),indent=2,sort_keys=True,allow_nan=False)+'\n')

def quantiles(values):
 a=sorted(Q(float(v)) for v in values);n=len(a)
 if not n:return {'n':0,'exact':None,'display':None}
 out={}
 for name,p in [('min',Q(0)),('q1',Q(1,4)),('median',Q(1,2)),('q3',Q(3,4)),('max',Q(1))]:
  u=(n-1)*p;j=u.numerator//u.denominator;t=u-j;out[name]=(1-t)*a[j]+t*a[min(j+1,n-1)]
 return {'n':n,'exact':qs(out),'display':{k:float(v) for k,v in out.items()}}
