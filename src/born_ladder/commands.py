"""Nonadaptive lens/binary command compilation, with full instrument identity."""
from fractions import Fraction as Q
from dataclasses import dataclass
import json
from . import arithmetic as L
from . import binary as B
from .binary import positive,sum_matrices
from .packaging import canonical
from .instruments import FIELDS
@dataclass(frozen=True)
class Command:
 descriptor:str
 mode:str
 labels:tuple
 effects:tuple
 roots:tuple
 instrument_key:str
 label_to_slot:tuple

def compile_command(base,desc):
 if not isinstance(desc,dict):raise ValueError('command must be a fixed public descriptor, no callbacks')
 try:public_descriptor=canonical(desc)
 except (TypeError,ValueError):raise ValueError('command must have a public serializable exact descriptor')
 if desc.get('mode') not in ('retain','forget'):raise ValueError('invalid policy')
 if desc.get('kind')=='lens':
  if set(desc)!={'kind','field','mode'} or desc['field'] not in FIELDS:raise ValueError('invalid lens command')
  labels=tuple(base.parts[desc['field']]);Cs=[base.C[base.parts[desc['field']][g]] for g in labels];As=[base.A[base.parts[desc['field']][g]] for g in labels]
 elif desc.get('kind')=='binary':
  if set(desc)!={'kind','effect','mode'}:raise ValueError('invalid binary command')
  labels=(0,1);Cs,As,_=B.Binary(base).roots(desc['effect'])
 else:raise ValueError('unadmitted command; K/F/adaptive/other operations excluded')
 if len(base.G)!=2 or any(Q(g)<=0 for g in base.G):raise ValueError('positive frame metric required')
 Cs=[B.exact_matrix(C) for C in Cs]
 if sum_matrices(Cs)!=L.eye():raise ValueError('complete instrument required')
 if len(Cs)!=len(As):raise ValueError('labelled branch count differs')
 checked_roots=[]
 for C,A in zip(Cs,As):
  if not positive(C,base.G):raise ValueError('positive labelled effect required')
  if len(A)!=2 or any(len(row)!=2 for row in A):raise ValueError('root matrix shape')
  A=L.asinterval(A)
  expected,_=L.principal(C)
  if A!=expected or not L.encloses(L.matmul(A,A),C):
   raise ValueError('fixed principal-root rule required')
  checked_roots.append(A)
 As=checked_roots
 # Multiplicity retained. Root rule is fixed; full per-atom effects determine
 # these single-Kraus branches by uniqueness, unlike a grouped total effect.
 order=sorted(range(len(labels)),key=lambda j:(canonical(L.qstrings(Cs[j])),labels[j]))
 signature={'fixed_carrier':{'identity':base.x['identity'],'G':[str(t) for t in base.G],'w':[str(t) for t in base.w]},'selected_lift':'one principal G-root Kraus per labelled atom','atomic_branches':[L.qstrings(Cs[j]) for j in order]}
 slots=tuple((labels[j],i) for i,j in enumerate(order))
 return Command(public_descriptor,desc['mode'],labels,tuple(Cs),tuple(As),canonical(signature),slots)

def witness(left,right):
 if len(left)!=len(right):raise ValueError('different program/read-stage domains')
 if any(a.instrument_key!=b.instrument_key or a.mode!=b.mode for a,b in zip(left,right)):raise ValueError('not the same full instrument/visibility; no shared identity')
 maps=[]
 for a,b in zip(left,right):
  slots=dict(a.label_to_slot);inv={slot:label for label,slot in b.label_to_slot}
  maps.append({g:inv[slots[g]] for g in a.labels})
 return {'left_public_commands':[json.loads(c.descriptor) for c in left],'right_public_commands':[json.loads(c.descriptor) for c in right],'outcome_bijections':maps,'fields':{
 'carrierPullbacksCompatible':'wordwise product of the explicitly listed bijections identifies finite read nodes and all subset pullbacks; entire selected Kraus branch list equal under mapping, uniformly in the same public initial density',
 'publicReadoutsCompatible':'reversible command/label namespace adapters; original endpoint descriptors stay in the package ledger, including source/stage/precision; no formerly public coordinate is erased',
 'visibilitySuppressionCompatible':'same retain/forget policies; bijection commutes with FORGOTTEN and transports every saturated subset; explicit modes/endpoint names remain public',
 'exactSixCompatible':'P1 identical branch updates; P2 same exhaustive labelled probabilities under reindexing; P3 inactive on both; P4 same read order/horizon; P5 same subset grouping and erasure; P6 both exact descriptors/domain/provenance/adapters retained; thresholds and collapse cases transported',
 'noHiddenSectionDependence':'structural exact coefficient/principal-root identity, no fitted/readout scalar criterion, hidden preparation, selected outcome or representative-dependent choice'},'identity_scope':'shared operational event isomorphism on explicit comparison adapters, not literal equality of original public command strings','full_instrument_equality':'all atomic single-root maps agree, including rejection/zero/failure domains; not merely equality of event effects'}

def translate(word,w):return tuple(w['outcome_bijections'][i][g] for i,g in enumerate(word))
