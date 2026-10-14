"""Read-only archived-unit verification, with explicit evidence and data inputs.

This entry checks the landed laws, readout and recorded losses; it does not
launch campaigns, generate authorizations, or create replacement statistics.
Population admission/statistical evaluators remain separately callable with
verified gates and registries. Missing historical inputs fail closed.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from .errors import IncompleteCampaign, SpecMismatch
from .frozen_spec import FrozenSpec
from .historical import HistoricalInputs
from .universal_shapes import _formula_contract, _recomputed_laws, _validate_scoring


def verify_units(stream, *, spec: FrozenSpec, stage: str, expected_sha256: str,
                 expected_size_bytes: int, reference_laws=None) -> dict:
    """Stream every original JSONL row, retaining excluded/null dispositions."""
    if stage not in {'g2a', 'g2c'}:
        raise ValueError('only registered G2a/G2c verification lanes are admitted')
    formulas = _formula_contract(spec)
    shapes = spec.get('/completeness/universal_evidence_shapes', expected_type=dict)
    hasher = hashlib.sha256(); size = 0; count = 0; eligible = 0; max_difference = 0.0
    per_kind = {'raw': 0, 'pkg': 0}; laws_checked = 0
    for raw in stream:
        hasher.update(raw); size += len(raw); count += 1
        record = json.loads(raw)
        kinds = [kind for kind in per_kind if hashlib.sha256((record['unit_id']+kind).encode()).hexdigest() == record['kind_cell_id']]
        if len(kinds) != 1:
            raise SpecMismatch('archived kind identity is not unique')
        kind = kinds[0]; per_kind[kind] += 1
        if record['eligibility'] is False:
            if record['state_space_prediction'] is not None or record['dtv_loss'] is not None:
                raise SpecMismatch('excluded archived unit carries scientific values')
            continue
        if record['eligibility'] is not True:
            raise SpecMismatch('invalid archived eligibility')
        eligible += 1
        actual = _recomputed_laws(record, formulas)
        if reference_laws is not None and actual != reference_laws(record, formulas):
            raise SpecMismatch('extracted law differs from the pre-extraction implementation')
        predictions, _, _ = actual
        _validate_scoring(record, shapes, kind, formulas)
        matrix=record[f'M_{kind}_or_content_hash']; empirical=record[f'unrounded_y_{kind}']
        for name, values in predictions.items():
            mapped=[sum(float(row[i])*values[i] for i in range(len(values))) for row in matrix]
            loss=formulas['loss_half']*math.fsum(abs(float(y)-q) for y,q in zip(empirical,mapped))
            brier=math.fsum((float(y)-q)**formulas['brier_power'] for y,q in zip(empirical,mapped))
            differences=[abs(a-b) for a,b in zip(values,record['state_space_prediction'][name])]
            differences += [abs(a-b) for a,b in zip(mapped,record['mapped_outcome_prediction'][name])]
            differences += [abs(loss-record['dtv_loss'][name]),abs(brier-record['brier_score'][name])]
            max_difference=max(max_difference,*differences); laws_checked += 1
    if size != expected_size_bytes or hasher.hexdigest() != expected_sha256:
        raise SpecMismatch('archived unit stream byte commitment differs')
    if count == 0:
        raise IncompleteCampaign('empty archived unit stream')
    return {'status':'PASS','stage':stage,'rows':count,'eligible':eligible,'excluded':count-eligible,
            'per_kind':per_kind,'laws_checked':laws_checked,'maximum_value_difference':max_difference,
            'sha256':hasher.hexdigest(),'size_bytes':size,
            'reference_value_equality': 'PASS' if reference_laws is not None else 'not requested',
            'archived_scoring_controls':'PASS under unchanged frozen tolerances',
            'scope':'unit laws/readouts/losses only; no new population statistics'}


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--historical-root',required=True,type=Path)
    p.add_argument('--data-root',required=True,type=Path)
    p.add_argument('--units',required=True,type=Path)
    p.add_argument('--sha256',required=True)
    p.add_argument('--size-bytes',required=True,type=int)
    p.add_argument('--stage',required=True,choices=['g2a','g2c'])
    a=p.parse_args()
    history=HistoricalInputs(a.historical_root)
    spec=(FrozenSpec.load_g2r_g2a_replay(repo_root=a.data_root,historical_root=history.root)
          if a.stage=='g2a' else FrozenSpec.load(history.path('born_route_rebuild1_spec_v24.json'),
              repo_root=a.data_root,historical_root=history.root))
    with a.units.open('rb') as stream:
        print(json.dumps(verify_units(stream,spec=spec,stage=a.stage,
              expected_sha256=a.sha256,expected_size_bytes=a.size_bytes),sort_keys=True))

if __name__=='__main__': main()
