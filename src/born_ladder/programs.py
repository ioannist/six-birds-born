"""Analytic finite nonadaptive program semantics; no native operation inserted."""
from .commands import *
from .packaging import pack_law,project,PackedLaw
from .transport import Transport
from types import SimpleNamespace
def _require(condition,message):
 # Invariants are executable verification gates, including under Python -O.
 if not condition:raise AssertionError(message)


def decode_source(base,desc):
 if not isinstance(desc,dict) or 'protocol' not in desc:raise ValueError('public preparation/protocol descriptor required')
 try:canonical(desc)
 except (TypeError,ValueError):raise ValueError('source/protocol must be a public serializable descriptor, no callbacks')
 if desc.get('kind')=='density' and set(desc)=={'kind','matrix','protocol'}:
  return B.Binary(base).state(desc['matrix'])
 if desc.get('kind')=='encoded' and set(desc)=={'kind','p','protocol'}:
  if len(desc['p'])!=base.n or any(isinstance(v,(float,bool)) for v in desc['p']):raise ValueError('exact simplex description required')
  p=[Q(v) for v in desc['p']]
  if any(v<0 for v in p) or sum(p)!=1:raise ValueError('encoded source simplex')
  # Reuse the bound encoder, without constructing its K/K² transport apparatus.
  proxy=SimpleNamespace(c=Q(base.n)/base.s,w=base.w)
  lam=Transport.encode(proxy,p)
  if lam.lo==lam.hi:
   l=lam.lo;den=base.n+base.s*l*l
   return [[base.n/den,base.s*l/den],[base.n*l/den,base.s*l*l/den]]
  den=base.n+base.s*lam.square()
  return [[base.n/den,base.s*lam/den],[base.n*lam/den,base.s*lam.square()/den]]
 if desc.get('kind')=='mixture' and set(desc)=={'kind','components','protocol'}:
  out=L.zero();weights=[]
  for component in desc['components']:
   if len(component)!=2 or isinstance(component[1],(float,bool)):raise ValueError('exact public mixture weight')
   source,w=component;w=Q(w)
   if w<0:raise ValueError('negative mixture weight')
   weights.append(w);out=L.add(out,L.scale(decode_source(base,source),w))
  if not weights or sum(weights)!=1:raise ValueError('mixture normalization')
  return out
 raise ValueError('unadmitted source descriptor or concealed protocol')

def compile_program(base,descs):
 if not isinstance(descs,(list,tuple)):raise ValueError('finite fixed command list required; adaptive programs excluded')
 return tuple(compile_command(base,c) for c in descs)

def exact_root(A):
 # An enclosure is an exact rational matrix only if every endpoint agrees.
 if all(not isinstance(x,L.I) or x.lo==x.hi for row in A for x in row):
  return [[x.lo if isinstance(x,L.I) else x for x in row] for row in A]
 return A

def apply_root(A,S,effect=None):
 # A is the admitted principal root of effect. A rational commuting state
 # satisfies A S A = effect S exactly, even when A has irrational entries.
 point=exact_root(S)
 if effect is not None and all(not isinstance(x,L.I) for row in point for x in row):
  left=L.matmul(effect,point)
  if left==L.matmul(point,effect):return left
 A=exact_root(A)
 return L.matmul(L.matmul(A,S),A)

def zero_mass(S):
 mass=L.trace(S)
 if isinstance(mass,L.I):return mass.lo==mass.hi==0
 return mass==0

def total(rows):return sum_matrices([S for w,S in rows])

def failure(code,source,descs,has_state):
 return {'status':'HALT_FAILURE','records':['PUBLIC_FAILURE:'+code,'HALT_FAILURE'],'source':source,'original_program':descs,'measurements_completed':0,'operational_state':'UNCHANGED_INITIAL' if has_state else 'NO_STATE'}

def execute(base,source,descs):
 try:R=decode_source(base,source)
 except (ValueError,TypeError,KeyError,ZeroDivisionError):return failure('INVALID_SOURCE',source,descs,False)
 try:cmds=compile_program(base,descs)
 except (ValueError,TypeError,KeyError,ZeroDivisionError):return failure('INVALID_PROGRAM',source,descs,True)
 metadata={'public_source':source,'original_program':[json.loads(c.descriptor) for c in cmds],'stage':len(cmds),'status':'HALT','timing':'release after each completed command; no autonomous dynamics','source_precision':'exact descriptors, certified inherited root enclosures'}
 rows=[((),R)];stages=[];zero_edges=[]
 for j,c in enumerate(cmds):
  nextrows=[]
  for word,S in rows:
   for label,effect,A in zip(c.labels,c.effects,c.roots):
    out=apply_root(A,S,effect)
    if zero_mass(out):zero_edges.append({'stage':j+1,'word':list(word+(label,)),'posterior':None});continue
    if L.asI(L.trace(out)).lo<=0:return failure('UNRESOLVED_NUMERICAL',source,descs,True)
    nextrows.append((word+(label,),out))
  rows=nextrows
  _require(L.encloses([[L.trace(total(rows))]],[[Q(1)]]), 'verification invariant failed')
  stage_meta={**metadata,'stage':j+1,'status':'HALT' if j+1==len(cmds) else 'READ'}
  p=pack_law(rows,[q.mode for q in cmds[:j+1]],stage_meta)
  stages.append(p)
 result=pack_law(rows,[q.mode for q in cmds],metadata)
 return {'status':'HALT','compiled':cmds,'full_rows':rows,'public':result,'stages':stages,'zero_edges':zero_edges,'measurements_completed':len(cmds)}

def word_effects(base,cmds):
 rows={():L.eye()}
 for c in cmds:
  rows={word+(label,):L.matmul(exact_root(A),M) for word,M in rows.items() for label,A in zip(c.labels,c.roots)}
 effects={w:L.matmul(base.adjoint(M),M) for w,M in rows.items()}
 _require(L.encloses(sum_matrices(list(effects.values())),L.eye()), 'verification invariant failed')
 return rows,effects

def positive_posterior(S):
 mass=L.asI(L.trace(S))
 if mass.lo==mass.hi==0:return {'status':'ZERO','posterior':None,'mass':mass}
 if mass.lo<=0:return {'status':'UNRESOLVED_NUMERICAL','posterior':None,'mass':mass}
 out=L.scale(S,1/mass);_require(L.encloses([[L.trace(out)]],[[Q(1)]]), 'verification invariant failed')
 return {'status':'POSITIVE','posterior':out,'mass':mass}

def absorbing_halt(status):
 if status not in ('HALT','HALT_FAILURE'):raise ValueError('not a halt node')
 return status
