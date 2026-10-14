"""Current and old stage plans exclude examples; allowlists use admitted cells."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from born_ladder.archive import sha
from born_ladder.reproduction.checkpoints import numeric_plan
from born_ladder.reproduction.units import specification_files
from born_ladder.reproduction.test_b import allowlist_control


def test_string_specifications_remain_binding_in_resume():
    old={'specifications':['same','reproduction_reference.example.json'],'source_code':'old'}
    new={**old,'source_code':'new'}
    assert numeric_plan(old)==numeric_plan(new)=={'specifications':old['specifications']}
    new={**new,'specifications':['changed','reproduction_reference.example.json']}
    assert numeric_plan(old)!=numeric_plan(new)


def test_only_path_rows_are_projected_from_mixed_specifications():
    entries=['literal.example.json',{'other':'preserved'},None,3,
             {'path':'documentation.example.json','sha256':'ignored'},
             {'path':'science.json','sha256':'binding'}]
    plan={'specifications':entries}
    before=deepcopy(plan)
    assert numeric_plan(plan)=={'specifications':entries[:4]+entries[5:]}
    assert plan==before


def test_example_hashes_do_not_block_old_or_new_resume(tmp_path):
    (tmp_path/'science.json').write_text('{"seed":1}')
    (tmp_path/'reproduction_reference.example.json').write_text('{"documentation":"old"}')
    old={'specifications':[{'path':p.name,'sha256':sha(p)} for p in sorted(tmp_path.glob('*.json'))],
         'grid':{'seeds':[1,2]},'source_code':{'x':'old'}}
    before=deepcopy(old)
    (tmp_path/'reproduction_reference.example.json').write_text('{"documentation":"new"}')
    current={**old,'specifications':specification_files(tmp_path),'source_code':{'x':'new'}}
    assert numeric_plan(old)==numeric_plan(current)
    assert old==before
    assert [r['path'] for r in current['specifications']]==['science.json']
    changed=deepcopy(current);changed['specifications'][0]['sha256']='changed science'
    assert numeric_plan(old)!=numeric_plan(changed)
    changed=deepcopy(current);changed['grid']['seeds']=[1,3]
    assert numeric_plan(old)!=numeric_plan(changed)
    changed=deepcopy(current);changed['specifications']=[]
    assert numeric_plan(old)!=numeric_plan(changed)


@pytest.mark.parametrize('recipes,blocks,calibration',[
    (range(48),range(910001,910016),range(60)),
    ([3,1],[9,5],[1,3,7]),
])
def test_allowlist_fields_come_from_run_records_and_manifest(tmp_path,recipes,blocks,calibration):
    path=tmp_path/'record_view/manifest.json';path.parent.mkdir();path.write_text('{"own_manifest":true}')
    record=SimpleNamespace(recipes=list(recipes),blocks=list(blocks),calibration=dict.fromkeys(calibration))
    seen=[]
    loader=SimpleNamespace(loader=SimpleNamespace(allowed={'record-a':{},'record-b':{}}),
                           load=lambda name:seen.append(name) or record)
    got=allowlist_control(tmp_path,loader,['forbidden'])
    assert got=={'status':'PASS','rejected':['forbidden'],'sampled_test_paths':0,
                 'allowed_path_recipes':sorted(recipes),'allowed_seed_blocks':sorted(blocks),
                 'calibration_only_recipes':sorted(set(calibration)-set(recipes)),
                 'manifest_sha256':sha(path)}
    assert seen==[Path('record-a'),Path('record-b')]


def test_seal_writer_publishes_the_source_derived_allowlist(tmp_path,monkeypatch):
    from born_ladder.reproduction import test_b as B
    import json
    (tmp_path/'setup.json').write_text('{"subset":true}')
    manifest=tmp_path/'record_view/manifest.json';manifest.parent.mkdir();manifest.write_text('{"own":true}')
    record=SimpleNamespace(recipes=[0,1],blocks=[4,5],calibration={0:[],1:[],2:[]})
    def load(path):
        if str(path)=='admitted':return record
        raise PermissionError('forbidden')
    loader=SimpleNamespace(loader=SimpleNamespace(allowed={'admitted':{}}),load=load)
    def audit(root,entries,workers):
        B._json(root/'controls/training_audit_1000.json',{'values':[1]})
        return {'campaigns':1000}
    r=SimpleNamespace(phase_start=lambda *a:{'runtime':'same','subset':True},eligible_entries=lambda *a:[],
        literal_relabel_refits=lambda *a:{'actual_full_refits':0},P5RecordLoader=lambda *a:loader,
        erasure_diagnostics=lambda *a:{'status':'NOT_COMPUTED'},training_audit=audit,
        sha=sha,PHASES=(),SPEC_HASH='science',CONTROL_RULES={},
        commit_phase=lambda *a:None)
    c=SimpleNamespace(canonical_document=lambda p:json.loads(Path(p).read_bytes()))
    monkeypatch.setattr(B,'science',lambda *a:(r,c,None,'same'))
    B.commit_stage(tmp_path,specifications='unused',workers=1)
    result=json.loads((tmp_path/'controls/allowlist.json').read_bytes())
    assert result['allowed_path_recipes']==[0,1] and result['allowed_seed_blocks']==[4,5]
    assert result['calibration_only_recipes']==[2] and result['manifest_sha256']==sha(manifest)
