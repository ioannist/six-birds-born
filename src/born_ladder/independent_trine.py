"""Independent Fraction/quadratic-ring verifier. No production imports.
Input: stored six-state certificate(s). Output: recomputed algebra and hashes.
"""
from fractions import Fraction as F
from pathlib import Path
import argparse,json,hashlib,sys
sys.set_int_max_str_digits(0)

def _require(condition,message):
 # Mathematical verification must not disappear under Python optimization.
 if not condition:raise AssertionError(message)


def check(c):
 def rational(value):
  _require(type(value) is str, 'exact rational must be a canonical string')
  result=F(value)
  _require(str(result)==value, 'exact rational must be a canonical string')
  return result
 _require(len(c['G'])==2 and all(len(row)==2 for row in c['G']),'metric shape')
 G=[[rational(v) for v in row] for row in c['G']];s=G[1][1];d=rational(c['exact_radicand'])
 _require(G==[[F(32),F(0)],[F(0),s]] and s>0 and d==3*s/32, 'exact verification invariant failed')
 def add(a,b):return (a[0]+b[0],a[1]+b[1])
 def mul(a,b):return (a[0]*b[0]+d*a[1]*b[1],a[0]*b[1]+a[1]*b[0])
 def scale(a,b):return (a[0]*b,a[1]*b)
 z=(F(0),F(0));one=(F(1),F(0));I=[[one,z],[z,one]]
 def mm(A,B):return [[add(mul(A[i][0],B[0][j]),mul(A[i][1],B[1][j])) for j in range(2)] for i in range(2)]
 def trace(A):return add(A[0][0],A[1][1])
 def parse(v):
  _require(set(v)=={'radicand','root','rational','radical_coefficient'}, 'quadratic field schema')
  _require(rational(v['radicand'])==d and type(v['root']) is str and v['root']=='positive square root', 'exact verification invariant failed')
  return (rational(v['rational']),rational(v['radical_coefficient']))
 _require(len(c['states_and_sharp_yes_effects'])==6 and all(len(M)==2 and all(len(row)==2 for row in M) for M in c['states_and_sharp_yes_effects']),'six-state matrix shapes')
 R=[[[parse(v) for v in row] for row in M] for M in c['states_and_sharp_yes_effects']]
 expected=[[[one,z],[z,z]], [[(F(1,4),F(0)),(F(0),F(1,4))],[(F(0),8/s),(F(3,4),F(0))]], [[(F(1,4),F(0)),(F(0),F(-1,4))],[(F(0),-8/s),(F(3,4),F(0))]]]
 expected += [[[add(I[i][j],scale(M[i][j],-1)) for j in range(2)] for i in range(2)] for M in expected[:]]
 _require(R==expected, 'six-state coordinates changed')
 for M in R:
  _require(mm(M,M)==M and trace(M)==one, 'exact verification invariant failed')
  _require(scale(M[0][1],32)==scale(M[1][0],s), 'exact verification invariant failed')
  _require(add(mul(M[0][0],M[1][1]),scale(mul(M[0][1],M[1][0]),-1))==z, 'exact verification invariant failed')
 # In a positive G metric these G-self-adjoint idempotents are PSD projectors.
 table=[[trace(mm(M,E)) for E in R[:3]] for M in R]
 literal=[[1,F(1,4),F(1,4)],[F(1,4),1,F(1,4)],[F(1,4),F(1,4),1],[0,F(3,4),F(3,4)],[F(3,4),0,F(3,4)],[F(3,4),F(3,4),0]]
 _require(table==[[(F(v),F(0)) for v in row] for row in literal], 'exact verification invariant failed')
 _require(len(c['YES_table_exact'])==6 and all(len(row)==3 for row in c['YES_table_exact']), 'YES table shape')
 for row,expected in zip(c['YES_table_exact'],literal):
  for value,want in zip(row,expected):
   _require(type(value) is type(want) if type(want) is int else type(value) is str, 'YES probability representation')
   if type(want) is not int:rational(value)
 _require([[F(v) for v in row] for row in c['YES_table_exact']]==literal, 'stored probability table differs')
 mixtures=[]
 for mix in c['five_mixture_identities']:
  entries=[]
  for i,w in mix:
   _require(type(i) is int and 0<=i<6, 'mixture state index must be an integer in [0,6)')
   entries.append((i,rational(w)))
  mixtures.append(entries)
 _require(mixtures==[[(i,F(1,2)),(i+3,F(1,2))] for i in range(3)]+[[(i,F(1,3)) for i in range(3)],[(i,F(1,3)) for i in range(3,6)]], 'exact verification invariant failed')
 for mix in mixtures:
  _require(sum(w for _,w in mix)==1, 'exact verification invariant failed')
  M=[[z,z],[z,z]]
  for i,w in mix:M=[[add(M[a][b],scale(R[i][a][b],w)) for b in range(2)] for a in range(2)]
  _require(M==[[scale(v,F(1,2)) for v in row] for row in I], 'exact verification invariant failed')
 return {'status':'PASS','six_states_and_effects':6,'probability_entries':18,'mixture_identities':5,'G_self_adjoint_PSD_projectors':'exact algebra plus positive-inner-product spectral theorem'}

def digest(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def audit(paths):return {'checker_sha256':digest(__file__),'certificates':[{'path':str(p),'sha256':digest(p),**check(json.loads(Path(p).read_text()))} for p in paths],'no_production_imports':True}
def main():
 p=argparse.ArgumentParser();p.add_argument('--certificate',action='append',default=[]);p.add_argument('--root');p.add_argument('--output',required=True);a=p.parse_args()
 paths=[Path(v) for v in a.certificate]
 if a.root:paths+=sorted(Path(a.root).glob('contexts/*/six_state_exact_completion.json'))
 if not paths:raise ValueError('no certificate inputs')
 result=audit(paths)
 with Path(a.output).open('x') as f:f.write(json.dumps(result,sort_keys=True,indent=2)+'\n')
 print('PASS',len(paths),'independent exact trines')
if __name__=='__main__':main()
