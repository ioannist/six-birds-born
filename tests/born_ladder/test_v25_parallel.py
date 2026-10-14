"""Scheduling/resume controls use synthetic inputs, never a registered run."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
from pathlib import Path
import time

import pytest

from born_ladder.reproduction import runs, worker_pool
from born_ladder.reproduction.v25 import fresh, pipeline
from born_ladder.reproduction.v25.specification import Specification, digest
from born_ladder.reproduction.unit_builders import BuiltInvocation
from born_ladder.snapshot.completeness import invocation_id_for

SPECS=Path(__file__).resolve().parents[2]/'specifications'


@pytest.fixture
def synthetic_captures(tmp_path,monkeypatch):
    jobs=[runs.Invocation('EXP-112','synthetic-'+str(i),101+i,32) for i in range(3)]
    root=tmp_path/'runs';root.mkdir()
    spec=Specification(SPECS)
    (root/'runset.json').write_text(json.dumps({'v25_scientific_digest':spec.digest,
        'invocations':[{**asdict(j),'id':j.id} for j in jobs]}))
    for job in jobs:
        payload=pipeline.synthetic_payload(2,8)
        born={'cell':job.configuration,'step_index':0,'k':2,
              'sym_eigvec_basis':payload['emitted'],'p_theory':payload['preparation'],
              'partition':payload['labels']['raw'],'packaging':payload['labels']['package']}
        directory=root/job.id;directory.mkdir();file=directory/'stdout.bin'
        file.write_text(json.dumps({'job':asdict(job),'born':born}))
        runs.Manifest(root).append({'event':'finished','status':'completed','invocation_id':job.id,
            'attempt':1,'directory':job.id,'artifacts':[{'path':job.id+'/stdout.bin',
                'bytes':file.stat().st_size,'sha256':runs.digest(file)}]})
    monkeypatch.setattr(runs.RunSpecifications,'grid',lambda *a:jobs)
    monkeypatch.setattr(pipeline,'worker_identity',lambda spec:{'synthetic_runtime':True})
    def parse(spec,stdout):
        from types import SimpleNamespace
        x=json.loads(stdout);j=x['job'];b=x['born']
        identity=invocation_id_for(spec,experiment=j['experiment'],config_or_null=j['configuration'],seed=j['seed'],scale=j['scale'])
        return SimpleNamespace(manifest={'invocation_id':identity,'units':[
            {'config_id':j['configuration'],'step_id':'0','resolution':2,'runner_context_id':'synthetic-context'}]})
    monkeypatch.setattr('born_ladder.snapshot.runner_structural.parse_runner_stdout',parse)
    monkeypatch.setattr('born_ladder.snapshot.g2a._raw_segments',lambda spec,stdout:([json.loads(stdout)['born']],None,None))
    calls=[]
    def builder(spec,evaluation,stdout,invocation,attempt):
        calls.append(invocation['seed'])
        # Force reverse completion order to test registered publication order.
        time.sleep((104-invocation['seed'])*.01)
        unit={'unit_id':str(invocation['seed']),'kind_cell_id':str(invocation['seed']),
              'context':'synthetic-context','resolution':2,'step':0}
        return BuiltInvocation({}, {'units.jsonl':(json.dumps(unit,sort_keys=True)+'\n').encode()},
                               {'status':'completed'})
    monkeypatch.setattr('born_ladder.reproduction.unit_builders.build_invocation',builder)
    # Exercise the real canonical/prediction/QR writer. Only the legacy capture
    # parser/scorer is stubbed in this portable I/O fixture; fresh-capture
    # benchmarking additionally exercises all production scientific bodies.
    monkeypatch.setattr(fresh,'adapt_record',lambda spec,row,prediction,**k:{**row,
        'prediction_commitment_sha256':digest(prediction),
        'canonical_q':prediction['canonical_certificate']['q_diag_canonical']})
    monkeypatch.setattr(fresh,'ProcessPoolExecutor',lambda max_workers,**k:ThreadPoolExecutor(max_workers=max_workers))
    return root,jobs,calls,builder


def collection(output):
    return json.loads(sorted(output.glob('collection_*.json'))[-1].read_bytes())


def science(output):
    return {p.relative_to(output).as_posix():p.read_bytes() for p in output.rglob('*') if p.is_file()
            and (p.name in ('v25_units.json','v25_controls.json','prediction.json','commitment.json') or 'legacy' in p.parts)}


def test_serial_parallel_scientific_files_and_grid_order(tmp_path,synthetic_captures):
    root,jobs,calls,_=synthetic_captures
    serial=tmp_path/'serial';parallel=tmp_path/'parallel'
    for output,workers in [(serial,1),(parallel,3)]:
        result=fresh.construct_fresh(runs=[root],output=output,evaluation='competitor',specifications=SPECS,workers=workers)
        assert result['incomplete']==0 and result['launched']==3
        assert [r['invocation_id'] for r in collection(output)['dispositions']]==[j.id for j in jobs]
    assert science(serial)==science(parallel)
    assert collection(serial)['units']==collection(parallel)['units']
    assert collection(serial)['controls']==collection(parallel)['controls']
    before=science(serial)
    result=fresh.construct_fresh(runs=[root],output=serial,evaluation='competitor',specifications=SPECS,workers=3)
    assert result['launched']==0 and result['skipped_completed']==3 and science(serial)==before
    assert len(collection(serial)['units'])==3 and len(set(calls))==3 and len(calls)==6


def test_interrupted_and_torn_attempt_redone_without_double_count(tmp_path,synthetic_captures,monkeypatch):
    root,jobs,calls,builder=synthetic_captures;output=tmp_path/'units'
    stop_once=True
    def interrupted(*a):
        nonlocal stop_once
        if a[3]['seed']==jobs[1].seed and stop_once:
            stop_once=False
            raise KeyboardInterrupt('synthetic interruption after prediction commitment')
        return builder(*a)
    monkeypatch.setattr('born_ladder.reproduction.unit_builders.build_invocation',interrupted)
    with pytest.raises(KeyboardInterrupt):
        fresh.construct_fresh(runs=[root],output=output,evaluation='competitor',specifications=SPECS,workers=1)
    complete=runs.Manifest(output).completed();assert list(complete)==[jobs[0].id]
    first=output/complete[jobs[0].id]['directory'];before={p:p.read_bytes() for p in first.rglob('*') if p.is_file()}
    partial=output/'invocations'/jobs[1].id/'attempt_0001'
    assert (partial/'predictions').exists()
    tail=b'{"event":"finished","incomplete_write":'
    with (output/'manifest.jsonl').open('ab') as stream:stream.write(tail)
    result=fresh.construct_fresh(runs=[root],output=output,evaluation='competitor',specifications=SPECS,workers=3)
    assert result['incomplete']==0 and result['skipped_completed']==1 and result['launched']==2
    assert all(p.read_bytes()==raw for p,raw in before.items()) and partial.exists()
    complete=runs.Manifest(output).completed()
    assert complete[jobs[1].id]['attempt']==2
    assert any(r.get('status')=='interrupted_coordinator' for r in runs.Manifest(output).rows)
    assert next((output/'journal_recovery').glob('tail_*.bin')).read_bytes()==tail
    assert [r['kind_cell_id'] for r in collection(output)['units']]==['101','102','103']
    assert calls.count(101)==calls.count(102)==calls.count(103)==1


def test_spawn_inherits_cli_exact_integer_serialization_policy():
    huge=1<<20000
    results=list(worker_pool.invocation_results([1,2],workers=2,
        prepare=lambda i:(i,huge),construct=str))
    assert len(results)==2 and all(isinstance(value,str) and len(value)>4300 for _,value in results)


def test_worker_refuses_actual_runtime_change(tmp_path,synthetic_captures,monkeypatch):
    root,jobs,calls,_=synthetic_captures
    from born_ladder.reproduction.units import source_inputs
    entry=source_inputs([root])[0][('EXP-112',jobs[0].configuration,jobs[0].seed,32)]
    directory=tmp_path/'attempt';directory.mkdir()
    monkeypatch.setattr(pipeline,'worker_identity',lambda spec:{'mismatch':True})
    result=fresh.construct_fresh_one({'job':jobs[0],'input':entry,'directory':str(directory),
        'specifications':str(SPECS),'evaluation':'competitor','runtime':{'synthetic_runtime':True}})
    assert result['status']=='failed' and 'computing runtime differs' in result['reason']
    assert not calls and not (directory/'predictions').exists()


def test_standalone_construct_cli_forwards_workers(monkeypatch,tmp_path,capsys):
    from born_ladder.__main__ import main
    monkeypatch.setattr('born_ladder.reproduction.stage_environment.ensure_environment',lambda *a:None)
    received=[]
    monkeypatch.setattr(fresh,'construct_fresh',lambda **kw:received.append(kw) or {'incomplete':0})
    assert main(['reproduce','v25-construct','--evaluation','competitor','--runs',str(tmp_path/'runs'),
                 '--output',str(tmp_path/'units'),'--workers','7'])==0
    assert received[0]['workers']==7
