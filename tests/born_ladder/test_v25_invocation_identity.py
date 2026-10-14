"""Invocation plumbing controls; no production seeds are executed or scored."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from born_ladder.reproduction.runs import RunSpecifications, Manifest
from born_ladder.reproduction.units import source_inputs
from born_ladder.reproduction.v25.fresh import (
    FreshSpecification, structural_invocation,
)
from born_ladder.reproduction.v25.specification import Specification
from born_ladder.snapshot.completeness import invocation_id_for
from born_ladder.snapshot.errors import IncompleteCampaign

SPECS=Path(__file__).resolve().parents[2]/'specifications'


@pytest.mark.parametrize('evaluation,experiment', [
    ('competitor','EXP-112'), ('cross-term','EXP-112'), ('cross-term','EXP-105')])
def test_large_seed_plan_manifest_collector_identity(tmp_path, monkeypatch, evaluation, experiment):
    """Real grid -> persisted P2a journal -> production adapter -> collector gate.

    Payload shape/scientific extraction is stubbed; the two real collectors'
    invocation comparisons and canonical identity helper are exercised.
    """
    spec=Specification(SPECS);source=FreshSpecification(spec,evaluation)
    jobs=RunSpecifications(SPECS).grid('v25-'+evaluation)
    job=next(j for j in jobs if j.experiment==experiment)
    assert job.seed>10**12 and type(job.seed) is int
    root=tmp_path/'runs';directory=root/'invocations'/job.id/'attempt_0001';directory.mkdir(parents=True)
    (root/'runset.json').write_text(json.dumps({'invocations':[
        {'id':job.id,'experiment':job.experiment,'configuration':job.configuration,'seed':job.seed,'scale':job.scale}]}))
    raw=(b'KEY_BORN_PROBE_JSON {"step_index":0,"k":2}\n'
         b'KEY_DISCOVERY_GRADE_JSON {"contexts":[],"rows":[]}\n'
         b'KEY_AUDIT_JSON {"multi_scale_scan":[{"k":2}]}\n'
         b'RB1_STRUCTURAL_END_JSON:{}\n')
    (directory/'stdout.bin').write_bytes(raw)
    from born_ladder.reproduction.runs import digest
    path=directory/'stdout.bin'
    Manifest(root).append({'event':'finished','status':'completed','invocation_id':job.id,'attempt':1,
        'directory':directory.relative_to(root).as_posix(),
        'artifacts':[{'path':path.relative_to(root).as_posix(),'bytes':len(raw),'sha256':digest(path)}]})
    entry=source_inputs([root])[0][(job.experiment,job.configuration,job.seed,job.scale)]
    invocation=structural_invocation(source,job,entry)
    expected=invocation_id_for(source,experiment=job.experiment,config_or_null=job.configuration,seed=job.seed,scale=job.scale)
    assert invocation['invocation_id']==expected!=job.id
    assert type(invocation['seed']) is int and invocation['seed']==job.seed
    from born_ladder.snapshot import runner_structural as runner, collector_structural as collector
    monkeypatch.setattr(runner,'_validate_shape',lambda *a:None)
    monkeypatch.setattr(collector,'_unit_from_raw',lambda *a:{'synthetic':True})
    if evaluation=='competitor':
        # Keep actual spec invocation contract and isolate identity from raw shapes.
        monkeypatch.setattr(collector,'_validate_raw_shape',lambda *a:None)
        fn=collector.reconstruct_collector_record
    else:
        from born_ladder.snapshot import g2c_collector_structural as cross
        monkeypatch.setattr(cross,'parse_g2c_raw_segments',lambda *a,**k:[SimpleNamespace(
            complete_suppression=None,discovery={'contexts':[],'rows':[]},audit={},born=[{}],label='synthetic')])
        monkeypatch.setattr(cross,'_unit_from_raw',lambda *a:{'synthetic':True})
        fn=cross.reconstruct_g2c_collector_record
    assert fn(source,raw,invocation)['invocation_id']==expected
    # This is the exact pre-fix representation; it must be rejected.
    with pytest.raises(IncompleteCampaign,match='invocation ID'):
        fn(source,raw,{**invocation,'invocation_id':job.id})
    assert list(Manifest(root).completed())==[job.id]  # Storage keys unchanged.


@pytest.mark.parametrize('field,value', [('seed',2000000001000.0),('seed','2000000001000'),('config_or_null',None)])
def test_structural_invocation_rejects_changed_capture_identity(field,value):
    spec=Specification(SPECS);source=FreshSpecification(spec,'competitor')
    job=RunSpecifications(SPECS).grid('v25-competitor')[0]
    invocation={'experiment':job.experiment,'config_or_null':job.configuration,'seed':job.seed,'scale':job.scale}
    invocation[field]=value
    with pytest.raises(ValueError,match='metadata differs'):
        structural_invocation(source,job,{'invocation':invocation})


@pytest.mark.parametrize('evaluation', ['competitor','cross-term'])
def test_fresh_constructor_uses_collector_identity_and_resumes_orphan(tmp_path, monkeypatch, evaluation):
    from born_ladder.reproduction.v25 import fresh, pipeline
    from born_ladder.reproduction.unit_builders import BuiltInvocation
    from born_ladder.snapshot import runner_structural, g2a, g2c_collector_structural
    spec=Specification(SPECS);job=RunSpecifications(SPECS).grid('v25-'+evaluation)[0]
    source=FreshSpecification(spec,evaluation)
    identity=invocation_id_for(source,experiment=job.experiment,config_or_null=job.configuration,seed=job.seed,scale=job.scale)
    root=tmp_path/'runs';directory=root/'invocations'/job.id/'attempt_0001';directory.mkdir(parents=True)
    (root/'runset.json').write_text(json.dumps({'v25_scientific_digest':spec.digest,'invocations':[
        {'id':job.id,'experiment':job.experiment,'configuration':job.configuration,'seed':job.seed,'scale':job.scale}]}))
    path=directory/'stdout.bin';path.write_bytes(b'synthetic identity plumbing only\n')
    from born_ladder.reproduction.runs import digest
    Manifest(root).append({'event':'finished','status':'completed','invocation_id':job.id,'attempt':1,
        'directory':directory.relative_to(root).as_posix(),'artifacts':[
            {'path':path.relative_to(root).as_posix(),'bytes':path.stat().st_size,'sha256':digest(path)}]})
    monkeypatch.setattr(RunSpecifications,'grid',lambda self,name:[job])
    monkeypatch.setattr(pipeline,'worker_identity',lambda spec:{'synthetic_runtime':True})
    monkeypatch.setattr(runner_structural,'parse_runner_stdout',lambda *a:SimpleNamespace(manifest={'invocation_id':identity,'units':[]}))
    monkeypatch.setattr(g2a,'_raw_segments',lambda *a:([],None,None))
    monkeypatch.setattr(g2c_collector_structural,'parse_g2c_raw_segments',lambda *a:[])
    calls=[]
    def build(spec,evaluation,stdout,invocation,attempt):
        assert invocation['invocation_id']==identity!=job.id
        calls.append(identity)
        return BuiltInvocation({}, {'units.jsonl':b''}, {'status':'completed'})
    monkeypatch.setattr('born_ladder.reproduction.unit_builders.build_invocation',build)
    output=tmp_path/'units';orphan=output/'invocations'/job.id/'attempt_0001';orphan.mkdir(parents=True)
    Manifest(output).append({'event':'started','invocation_id':job.id,'attempt':1,'directory':orphan.relative_to(output).as_posix()})
    result=fresh.construct_fresh(runs=[root],output=output,evaluation=evaluation,specifications=SPECS)
    assert result['incomplete']==0 and calls==[identity]
    completed=Manifest(output).completed()[job.id]
    assert completed['attempt']==2 and orphan.exists()
    original_manifest=(root/'manifest.jsonl').read_bytes()
    assert fresh.construct_fresh(runs=[root],output=output,evaluation=evaluation,specifications=SPECS)['incomplete']==0
    assert calls==[identity] and (root/'manifest.jsonl').read_bytes()==original_manifest
