"""B13: verify a bound, complete structural return-carrier inventory.

Extracted from CB2's metadata-only inventory lane. Caller supplies every
historical commitment; no result, loss or gate value enters membership.
Kernel availability means actual existing exponent-one bytes, never a power
inverse, normalization or regenerated kernel.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
from ..archive import Archive, sha
from ..metadata import UNIT_KEYS, canonical, choose, metadata, refs
from .errors import IncompleteCampaign, SpecMismatch


def verify_return_inventory(*, data_root, inventory_path, inventory_sha256,
                            selection_path, selection_sha256, census_inventory_path,
                            census_inventory_sha256):
    def read(path, expected):
        if sha(path) != expected:
            raise SpecMismatch('structural inventory commitment differs: '+str(path))
        return json.loads(Path(path).read_bytes())
    inventory=read(inventory_path,inventory_sha256)
    selection=read(selection_path,selection_sha256)
    census=read(census_inventory_path,census_inventory_sha256)
    if inventory['performance_fields_decoded_for_inventory'] != [] or selection['performance_inputs'] != []:
        raise SpecMismatch('performance input in structural selector')
    if selection['inventory_sha256'] != inventory_sha256:
        raise SpecMismatch('selector bound to another inventory')
    rows=inventory['rows'];by_id={r['unit_id']:r for r in rows}
    if len(by_id)!=len(rows) or len(rows)!=inventory['paired_unit_contexts']:
        raise SpecMismatch('incomplete/duplicated structural inventory')
    counts=Counter(str(r['retained_rank']) for r in rows)
    if dict(counts)!=inventory['rank_counts'] or counts['2']!=2122:
        raise SpecMismatch('retained-rank census differs')
    reader=Archive(data_root)
    for path,digest in inventory['source_files'].items():
        if sha(reader.path(path))!=digest:raise SpecMismatch('source-file commitment differs: '+path)
    line_count=0
    for r in rows:
        if not r['immutable_join_verified'] or {p['kind'] for p in r['kind_records']}!={'raw','pkg'} or len(r['kind_records'])!=2:
            raise SpecMismatch('raw/package pairing is incomplete')
        for ptr in r['kind_records']:
            raw,_,_=reader.line(ptr);u=metadata(raw,UNIT_KEYS);fields=refs(raw,UNIT_KEYS|{'unrounded_p_full'})
            if u['unit_id']!=r['unit_id'] or u['kind_cell_id']!=ptr['kind_cell_id'] or u['context']!=r['provenance_key']['context']:
                raise SpecMismatch('raw/package provenance join differs')
            if fields!=ptr['fields']:
                raise SpecMismatch('structural field references differ')
            rank=u['basis_and_projector_inputs']['effective_rank'] if u['basis_and_projector_inputs'] is not None else None
            if rank!=r['retained_rank']:
                raise SpecMismatch('stored retained rank differs')
            line_count+=1
        if r['kernel']['status']=='AVAILABLE':
            artifact=r['kernel']['artifact']
            if artifact.get('exponent',1)!=1:
                raise SpecMismatch('kernel bytes are not exponent one')
            text,_,_=reader.line(artifact,True)
            lo,hi=artifact["char_range"];blob=text[lo:hi].encode()
            if hashlib.sha256(blob).hexdigest()!=artifact["field_sha256"]:raise SpecMismatch("kernel field commitment differs")
            K=json.loads(blob)
            if len(K)!=r['n'] or any(len(row)!=r['n'] for row in K):
                raise SpecMismatch('kernel dimensions differ')
    if line_count!=inventory['unit_rows']:
        raise SpecMismatch('incomplete unit-row census')
    pick=choose(rows)
    if pick!=selection['selector_result'] or pick['eligible_count']!=120:
        raise SpecMismatch('frozen structural membership differs')
    eligible=[r for r in rows if r['n']==32 and r['retained_rank']==2 and r['source_span_available'] and r['kernel']['status']=='AVAILABLE' and r['immutable_join_verified']]
    eligible.sort(key=lambda r:(hashlib.sha256(canonical(r['provenance_key'])).hexdigest(),r['unit_id']))
    if eligible!=census:
        raise SpecMismatch('120-context census membership/order differs')
    return {'status':'PASS','paired_contexts':len(rows),'unit_rows':line_count,'rank_two_contexts':counts['2'],
            'kernel_available_rank_two':len(eligible),'performance_inputs':[],'selector':pick}
