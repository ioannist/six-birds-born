"""Read-only structural decoder. Never decode unregistered performance values."""
import hashlib, json
from pathlib import Path

UNIT_KEYS = frozenset('unit_id kind_cell_id invocation_id source experiment config_or_null seed scale resolution context partition step structural_manifest_sha256 attempt_record_sha256 ordered_state_labels ordered_union_outcome_labels M_raw_or_content_hash M_pkg_or_content_hash basis_and_projector_inputs raw_pkg_pairing_key'.split())
BORN_KEYS = frozenset('cell k packaging partition scale seed starts step_index sym_eigvec_basis tau'.split())
AUDIT_KEYS = frozenset('cell exp_id config_name git_sha seed n step pica_config_hash tau'.split())
SEQ_KEYS = frozenset('cell seed scale step_index k tau t_mid'.split())
KERNEL_KEYS = frozenset(['kernel','micro_kernel','root_kernel'])

def digest_bytes(b): return hashlib.sha256(b).hexdigest()
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(2**20), b''): h.update(b)
    return h.hexdigest()
def canonical(x): return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def spans(s):
    """Lexical top-level value spans, without decoding skipped JSON values."""
    i=0; n=len(s)
    def ws(i):
        while i<n and s[i].isspace(): i+=1
        return i
    def string_end(i):
        i+=1
        while i<n:
            if s[i]=='\\': i+=2
            elif s[i]=='"': return i+1
            else:i+=1
        raise ValueError('unterminated string')
    i=ws(i)
    if s[i]!='{':raise ValueError('expected object')
    i+=1
    while True:
        i=ws(i)
        if s[i]=='}':return
        j=string_end(i); key=json.loads(s[i:j]); i=ws(j)
        if s[i]!=':':raise ValueError('expected colon')
        i=ws(i+1); start=i
        if s[i]=='"':i=string_end(i)
        elif s[i] in '[{':
            depth=1;i+=1
            while depth:
                if s[i]=='"':i=string_end(i);continue
                if s[i] in '[{':depth+=1
                if s[i] in ']}':depth-=1
                i+=1
        else:
            while i<n and s[i] not in ',}':i+=1
        yield key,start,i
        i=ws(i)
        if s[i]=='}':return
        if s[i]!=',':raise ValueError('expected comma')
        i+=1

def metadata(s,keys):return {k:json.loads(s[a:b]) for k,a,b in spans(s) if k in keys}
def refs(s,keys):return {k:{'field_sha256':digest_bytes(s[a:b].encode()),'char_range':[a,b]} for k,a,b in spans(s) if k in keys}
def choose(rows):
    eligible=[r for r in rows if r['n']==32 and r['retained_rank']==2 and r['source_span_available'] and r['kernel']['status']=='AVAILABLE' and r['immutable_join_verified']]
    eligible.sort(key=lambda r:(digest_bytes(canonical(r['provenance_key'])),r['unit_id']))
    return {'eligible_count':len(eligible),'pick':eligible[0]['unit_id'] if eligible else None,'pick_key_sha256':digest_bytes(canonical(eligible[0]['provenance_key'])) if eligible else None}
