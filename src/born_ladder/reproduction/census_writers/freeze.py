"""Freeze every available rank-two context with the historical ordering rule."""
from .common import *


def eligible(row):
    return row['n']==32 and row['retained_rank']==2 and row['source_span_available'] and row['kernel']['status']=='AVAILABLE' and row['immutable_join_verified']


def order(rows):
    return sorted((r for r in rows if eligible(r)),key=lambda r:(hb(canonical(r['provenance_key'])),r['unit_id']))


def freeze(rows, output):
    rows=order(rows)
    output=Path(output)
    put(output/'INVENTORY.json',rows)
    put(output/'CONTEXT_LIST.json',[{'index':i,'unit_id':r['unit_id'],'provenance_key_sha256':hb(canonical(r['provenance_key'])),'complete_provenance_key':r['provenance_key']} for i,r in enumerate(rows)])
    return rows
