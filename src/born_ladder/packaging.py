"""Public register retention/forgetting and idempotent event packaging."""
import json
from dataclasses import dataclass
from . import arithmetic as L
FORGOTTEN="FORGOTTEN"
def canonical(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True)

def project(word,modes):
 if len(word)!=len(modes) or any(m not in ('retain','forget') for m in modes):raise ValueError('visibility domain')
 return tuple(FORGOTTEN if m=='forget' else g for g,m in zip(word,modes))

def visible(words,chosen,modes):
 words=set(map(tuple,words));chosen=set(map(tuple,chosen))
 if not chosen<=words:raise ValueError('event outside test')
 flags={}
 for w in words:
  p=project(w,modes);flag=w in chosen
  if p in flags and flags[p]!=flag:return False
  flags[p]=flag
 return True

@dataclass(frozen=True)
class PackedLaw:
 modes:tuple
 public_ledger:str
 cells:tuple

@dataclass(frozen=True)
class PackedEvent:
 test_id:str
 modes:tuple
 public_ledger:str
 predicate:tuple

def pack_law(rows,modes=None,ledger=None):
 if isinstance(rows,PackedLaw):
  if modes is not None and tuple(modes)!=rows.modes:raise ValueError('changing policy needs an explicit new projection')
  if ledger is not None and canonical(ledger)!=rows.public_ledger:raise ValueError('public protocol record cannot be silently changed')
  modes=rows.modes;public=rows.public_ledger;rows=rows.cells
 else:
  modes=tuple(modes);public=canonical(ledger)
 buckets={}
 for word,S in rows:
  key=project(tuple(word),modes)
  if len(S)!=2 or any(len(r)!=2 for r in S):raise ValueError('state shape')
  value=tuple(tuple(r) for r in S)
  # First entry copied, not rounded by an unnecessary add-with-zero.
  buckets[key]=tuple(tuple(r) for r in L.add(buckets[key],value)) if key in buckets else value
 return PackedLaw(modes,public,tuple((k,buckets[k]) for k in sorted(buckets,key=canonical)))

def pack_event(test_id,words=None,chosen=None,modes=None,ledger=None):
 if isinstance(test_id,PackedEvent):
  if any(x is not None for x in (words,chosen,modes,ledger)):raise ValueError('cannot change packaged event without new declared data')
  # Canonical words/protocol/predicate already lie in the image. No hidden alias.
  e=test_id
  return PackedEvent(e.test_id,e.modes,e.public_ledger,tuple(sorted(set(e.predicate),key=canonical)))
 words=tuple(map(tuple,words));chosen=tuple(map(tuple,chosen));modes=tuple(modes)
 if not visible(words,chosen,modes):raise ValueError('predicate hidden by declared forgetting')
 pred=tuple(sorted({project(w,modes) for w in chosen},key=canonical))
 return PackedEvent(str(test_id),modes,canonical(ledger),pred)

def restore_ledger(package):return json.loads(package.public_ledger)
