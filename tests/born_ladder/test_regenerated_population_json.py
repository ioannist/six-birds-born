"""P12 full-branch comparisons use the evaluation writer's JSON representation."""
import copy
from contextlib import nullcontext
import json
import math
from pathlib import Path
import weakref

import numpy as np
import pytest

from born_ladder.archive import put, sha
from born_ladder.reproduction import regenerated_bundle as B


def population_result():
    return {
        'status': 'PASS',
        'provenance': {'public_input_commitments': {'collection': 'sealed', 'construction_manifest': 'fixed-manifest'}},
        'completeness': {'public_collection_complete': True, 'invocations': 7},
        'statistics': {'raw::gap': {
            'estimate': 0.125, 'bca_equal_tail_interval': (0.0625, 0.25),
            'jackknife_values': (0.125, -0.0),
            'replicate_estimates': [(0.125, 0.25), {'nested': (1, False, 'atom', None)}],
            'sensitivity_atoms': {'leave_one_seed_out': (0.125, 0.25)},
            'rng_audit': ({'framed_fields': [('seed', 840015), ('family', 'primary')]},),
            'members': (1, 2), 'reject': True, 'frame_context': 'scientific-value',
        }},
    }


@pytest.fixture
def full_evaluation(tmp_path, monkeypatch):
    from born_ladder.reproduction import evaluation as E
    from born_ladder.snapshot import universal_shapes, g2a, g2c_evaluate, g2c_controls

    result = population_result()
    roots = {}
    for name in ('competitor_evaluation', 'cross_term_evaluation',
                 'competitor_units', 'cross_term_units'):
        root = tmp_path / name
        roots[name] = root
        if name.endswith('_evaluation'):
            # Use the production writer, then read from disk in the real verifier.
            put(root / 'evaluation.json', result)
            put(root / 'complete.json', {'summary': {'evaluation_path': 'evaluation.json'}})
        else:
            put(root / 'unit.json', {'sealed': True})
    manifest = tmp_path / 'bundle.json'
    put(manifest, {'schema': B.SCHEMA, 'profile': 'regenerated', 'reduced': False,
                  'roots': {name: name for name in roots},
                  'files': {name: {p.name: sha(p) for p in root.iterdir()}
                            for name, root in roots.items()}})
    monkeypatch.setattr(E, 'PopulationSpecification', lambda *a: object())
    monkeypatch.setattr(E, 'closed_inputs', lambda *a: (None, None, [], [], {}, {},
        {'collection': 'sealed', 'construction_manifest': 'fixed-manifest'}, {'completed_invocations': 7}))
    monkeypatch.setattr(E, 'cross_term_inputs', lambda *a: ([], {}, [], {}))
    monkeypatch.setattr(universal_shapes, 'validate_stage_records', lambda *a, **k: [])
    monkeypatch.setattr(g2c_controls, 'gradual_underflow_certificate', nullcontext)
    calls = []
    def evaluator(name):
        def run(*a, **k):
            calls.append(name)
            actual=copy.deepcopy(result)
            if name=='competitor':
                actual['provenance']=copy.deepcopy(k['provenance'])
                actual['completeness']=copy.deepcopy(k['completeness'])
            return actual
        return run
    monkeypatch.setattr(g2a, 'evaluate_g2a_records', evaluator('competitor'))
    monkeypatch.setattr(g2c_evaluate, 'evaluate_g2c_records', evaluator('cross-term'))
    return manifest, result, calls


def test_full_population_tuple_containers_match_writer_in_both_evaluations(full_evaluation):
    manifest, _, calls = full_evaluation
    receipt = B.verify('P12', manifest)
    assert receipt['status'] == 'VERIFIED'
    assert receipt['checks']['full_population_recomputed_here'] is True
    assert calls == ['competitor', 'cross-term']


@pytest.mark.parametrize('field,value', [
    ('estimate', 0.25),
    ('estimate', math.nextafter(0.125, math.inf)),
    ('jackknife_values', (0.125, 0.0)),  # Signed zero also has different float bits.
    ('members', (1, 3)),
    ('reject', 1),
    ('frame_context', 'changed'),  # No default binding-field projection for P12.
    ('estimate', None),
    ('members', (1.0, 2)),  # Equal numerical value with a different JSON type.
])
@pytest.mark.parametrize('evaluation', ['competitor', 'cross-term'])
def test_full_population_changed_science_fails(full_evaluation, monkeypatch, field, value, evaluation):
    manifest, result, _ = full_evaluation
    from born_ladder.snapshot import g2a, g2c_evaluate
    changed = copy.deepcopy(result)
    changed['statistics']['raw::gap'][field] = value
    module, function = ((g2a, 'evaluate_g2a_records') if evaluation == 'competitor'
                        else (g2c_evaluate, 'evaluate_g2c_records'))
    monkeypatch.setattr(module, function, lambda *a, **k: changed)
    with pytest.raises(ValueError, match='full regenerated population inference differs'):
        B.verify('P12', manifest)


@pytest.mark.parametrize('change', ['missing-key', 'extra-key', 'verdict'])
@pytest.mark.parametrize('evaluation', ['competitor', 'cross-term'])
def test_full_population_missing_key_or_changed_verdict_fails(full_evaluation, monkeypatch, change, evaluation):
    manifest, result, _ = full_evaluation
    from born_ladder.snapshot import g2a, g2c_evaluate
    changed = copy.deepcopy(result)
    if change == 'missing-key':
        del changed['statistics']['raw::gap']['sensitivity_atoms']
    elif change == 'extra-key':
        changed['statistics']['raw::gap']['unexpected'] = True
    else:
        changed['status'] = 'FAIL'
    module, function = ((g2a, 'evaluate_g2a_records') if evaluation == 'competitor'
                        else (g2c_evaluate, 'evaluate_g2c_records'))
    monkeypatch.setattr(module, function, lambda *a, **k: changed)
    with pytest.raises(ValueError, match='full regenerated population inference differs'):
        B.verify('P12', manifest)


@pytest.mark.parametrize('value', [np.float64(0.125), np.int64(1), np.bool_(True),
                                  {1, 2}, np.array([0.125]), object()])
def test_full_population_non_json_value_is_rejected(full_evaluation, value):
    manifest, result, _ = full_evaluation
    result['statistics']['raw::gap']['estimate'] = value
    with pytest.raises(TypeError, match='non-JSON population value'):
        B.verify('P12', manifest)


def test_full_population_non_string_key_is_rejected(full_evaluation):
    manifest, result, _ = full_evaluation
    result['statistics']['raw::gap']['rng_audit'] = ({1: 'must not become string'},)
    with pytest.raises(TypeError, match='non-string population key'):
        B.verify('P12', manifest)


@pytest.mark.parametrize('value', [math.inf, -math.inf, math.nan])
def test_full_population_nonfinite_value_is_rejected(full_evaluation, value):
    manifest, result, _ = full_evaluation
    result['statistics']['raw::gap']['estimate'] = value
    with pytest.raises(ValueError, match='Out of range float values'):
        B.verify('P12', manifest)


def test_normalization_is_identical_to_evaluation_writer(tmp_path):
    value = population_result()
    put(tmp_path / 'evaluation.json', value)
    original = json.loads((tmp_path / 'evaluation.json').read_bytes())
    from born_ladder.reproduction.census_comparison import Comparison
    comparison = Comparison(project_bindings=False)
    comparison.compare('population', B.population_json(value), original)
    assert comparison.result()['overall_agreement']
    assert comparison.result()['field_groups']['population']['compared'] > 20


@pytest.mark.parametrize('workers',[None,1,4,48])
def test_verify_cli_reuses_parallel_rotation_validator(full_evaluation,monkeypatch,workers,capsys):
    from born_ladder.__main__ import main
    from born_ladder.reproduction import evaluation as E, rotation_admission as R, stage_environment
    from born_ladder.snapshot import g2a, g2c_evaluate

    monkeypatch.setattr(stage_environment,'ensure_environment',lambda *a:None)
    manifest,result,_=full_evaluation
    sources=[{'kind_cell_id':'source'}];controls=[{'kind_cell_id':'control'}]
    rotations={'rotation':'evidence'};projections={'source':'projection'}
    records=[{'record':'input'}];directories=['sealed-directory']
    specs={'competitor':object(),'cross-term':object()}
    monkeypatch.setattr(E,'PopulationSpecification',lambda directory,evaluation:specs[evaluation])
    monkeypatch.setattr(E,'closed_inputs',lambda *a:(None,None,records,directories,{}, {},
        {'collection':'sealed','construction_manifest':'fixed-manifest'},{'completed_invocations':7}))
    bound=[]
    def inputs(spec,rows,paths):
        bound.append((spec,rows,paths))
        return controls,rotations,sources,projections
    monkeypatch.setattr(E,'cross_term_inputs',inputs)
    validator=object();pool_calls=[]
    def parallel(directory,source,control,rotation,count):
        pool_calls.append((directory,source,control,rotation,count))
        return validator
    monkeypatch.setattr(R,'parallel_rotations',parallel)
    evaluated=[]
    def cross(spec,rows,control,**kwargs):
        evaluated.append((spec,rows,control,kwargs))
        return copy.deepcopy(result)
    monkeypatch.setattr(g2c_evaluate,'evaluate_g2c_records',cross)
    def competitor(*args,**kwargs):
        assert 'rotation_validator' not in kwargs
        assert kwargs['provenance']==result['provenance']
        assert kwargs['completeness']==result['completeness']
        return copy.deepcopy(result)
    monkeypatch.setattr(g2a,'evaluate_g2a_records',competitor)
    argv=['verify','P12','--profile','regenerated','--data',str(manifest)]
    if workers is not None:argv+=['--workers',str(workers)]
    assert main(argv)==0
    assert 'PASS P12:' in capsys.readouterr().out
    assert bound==[(specs['cross-term'],records,directories)]
    spec,rows,control,kwargs=evaluated[0]
    assert spec is specs['cross-term'] and rows is records and control is controls
    assert kwargs['rotation_evidence'] is rotations
    assert kwargs['control_sources'] is sources
    assert kwargs['control_input_projections'] is projections
    if workers is None or workers==1:
        assert pool_calls==[]
        assert set(kwargs)=={'rotation_evidence','control_sources','control_input_projections'}
    else:
        assert len(pool_calls)==1
        directory,source,control,rotation,count=pool_calls[0]
        assert directory=='specifications' and count==workers
        assert source is sources and control is controls and rotation is rotations
        assert kwargs['rotation_validator'] is validator
        assert set(kwargs)=={'rotation_evidence','control_sources','control_input_projections','rotation_validator'}


@pytest.mark.parametrize('workers',['0','-1','1.5','invalid'])
def test_verify_cli_rejects_invalid_worker_count(monkeypatch,capsys,workers):
    from born_ladder.__main__ import main
    from born_ladder.reproduction import stage_environment
    monkeypatch.setattr(stage_environment,'ensure_environment',lambda *a:pytest.fail('invalid workers must not provision an environment'))
    monkeypatch.setattr(B,'verify',lambda *a,**kw:pytest.fail('invalid workers must not run verification'))
    with pytest.raises(SystemExit) as error:
        main(['verify','P12','--profile','regenerated','--data','unused','--workers',workers])
    assert error.value.code==2
    assert '--workers' in capsys.readouterr().err


def test_verify_worker_flag_is_ignored_for_other_claims(monkeypatch,capsys):
    import born_ladder.__main__ as M
    from born_ladder.reproduction import stage_environment
    monkeypatch.setattr(stage_environment,'ensure_environment',lambda *a:None)
    calls=[]
    monkeypatch.setattr(M,'verify_claim',lambda *a,**kw:calls.append((a,kw)) or 'control passed')
    assert M.main(['verify','B14','--workers','48'])==0
    assert calls[0][0]==('B14',) and 'workers' not in calls[0][1]
    assert 'PASS B14:' in capsys.readouterr().out


@pytest.mark.parametrize('workers',[1,48])
def test_cross_replay_releases_competitor_and_defers_saved_result(full_evaluation,monkeypatch,workers):
    from born_ladder.reproduction import evaluation as E, rotation_admission as R, census_comparison as C
    from born_ladder.snapshot import universal_shapes, g2a, g2c_evaluate
    manifest,result,_=full_evaluation
    references={};events=[];pending=[]
    class TrackedDict(dict):pass
    class TrackedList(list):pass
    class Spec:pass
    def track(name,value):
        references[name]=weakref.ref(value)
        return value
    loads=json.loads;read_bytes=Path.read_bytes
    def read(path):
        if path.parent.name=='competitor_evaluation':pending.append(path.name)
        if path.parent.name=='cross_term_evaluation' and path.name=='evaluation.json':
            assert 'cross-recomputed' in events
            events.append('saved-cross-loaded')
        return read_bytes(path)
    def decode(*a,**kw):
        value=loads(*a,**kw)
        if pending:
            return track(pending.pop(),TrackedDict(value))
        return value
    monkeypatch.setattr(Path,'read_bytes',read)
    monkeypatch.setattr(json,'loads',decode)
    monkeypatch.setattr(E,'PopulationSpecification',lambda directory,evaluation:
                        track('spec',Spec()) if evaluation=='competitor' else Spec())
    def inputs(root,*a):
        if root.name=='competitor_units':
            records=track('records',TrackedList())
            return track('inputs',TrackedList([None,None,records,[],{}, {},
                {'collection':'sealed','construction_manifest':'fixed-manifest'},{'completed_invocations':7}]))
        return None,None,[],[],{}, {}, {}, {}
    monkeypatch.setattr(E,'closed_inputs',inputs)
    monkeypatch.setattr(universal_shapes,'validate_stage_records',
                        lambda *a,**kw:track('valid',TrackedList()))
    monkeypatch.setattr(g2a,'evaluate_g2a_records',
                        lambda *a,**kw:track('actual',TrackedDict(copy.deepcopy(result))))
    normalize=B.population_json
    monkeypatch.setattr(B,'population_json',lambda value:normalize(dict(value)))
    class TrackedComparison(C.Comparison):
        def __init__(self,**kw):
            super().__init__(**kw)
            if 'cross-start' not in events:track('comparison',self)
    monkeypatch.setattr(C,'Comparison',TrackedComparison)
    def released():
        assert set(references)=={'complete.json','evaluation.json','spec','records','inputs','valid','actual','comparison'}
        assert all(ref() is None for ref in references.values())
    def cross_inputs(*a):
        released();events.append('cross-start')
        return [],{},[],{}
    monkeypatch.setattr(E,'cross_term_inputs',cross_inputs)
    def parallel(*a):
        released();assert 'saved-cross-loaded' not in events
        events.append('validator-built');return object()
    monkeypatch.setattr(R,'parallel_rotations',parallel)
    def cross(*a,**kw):
        released();assert 'saved-cross-loaded' not in events
        assert ('rotation_validator' in kw)==(workers>1)
        events.append('cross-recomputed');return copy.deepcopy(result)
    monkeypatch.setattr(g2c_evaluate,'evaluate_g2c_records',cross)
    assert B.verify('P12',manifest,workers=workers)['status']=='VERIFIED'
    assert events==(['cross-start','validator-built','cross-recomputed','saved-cross-loaded']
                    if workers>1 else ['cross-start','cross-recomputed','saved-cross-loaded'])


@pytest.mark.parametrize('mutation',[
    None,'provenance-value','provenance-key','completeness-flag','completeness-count','completeness-type',
])
def test_competitor_metadata_is_reconstructed_before_saved_result_load(full_evaluation,monkeypatch,mutation):
    from born_ladder.snapshot import g2a
    manifest,result,_=full_evaluation
    saved=manifest.parent/'competitor_evaluation/evaluation.json'
    if mutation is not None:
        document=json.loads(saved.read_bytes())
        if mutation=='provenance-value':
            document['provenance']['public_input_commitments']['collection']='changed'
        elif mutation=='provenance-key':
            del document['provenance']['public_input_commitments']['construction_manifest']
        elif mutation=='completeness-flag':
            document['completeness']['public_collection_complete']=False
        elif mutation=='completeness-count':
            document['completeness']['invocations']=8
        else:
            document['completeness']['invocations']=7.0
        saved.write_text(json.dumps(document))
        bundle=json.loads(manifest.read_bytes())
        bundle['files']['competitor_evaluation']['evaluation.json']=sha(saved)
        manifest.write_text(json.dumps(bundle))
    events=[];read=Path.read_bytes
    def read_after_recompute(path):
        if path==saved:
            assert events==['recomputed']
            events.append('saved-result-loaded')
        return read(path)
    monkeypatch.setattr(Path,'read_bytes',read_after_recompute)
    def evaluate(spec,valid,*,provenance,completeness):
        assert events==[]
        assert provenance=={'public_input_commitments':{'collection':'sealed','construction_manifest':'fixed-manifest'}}
        assert completeness=={'public_collection_complete':True,'invocations':7}
        assert type(completeness['invocations']) is int
        actual=copy.deepcopy(result)
        actual['provenance']=provenance;actual['completeness']=completeness
        events.append('recomputed')
        return actual
    monkeypatch.setattr(g2a,'evaluate_g2a_records',evaluate)
    if mutation is None:
        assert B.verify('P12',manifest)['status']=='VERIFIED'
    else:
        with pytest.raises(ValueError,match='full regenerated population inference differs'):
            B.verify('P12',manifest)
    assert events==['recomputed','saved-result-loaded']
