"""Synthetic checks for the simplified single-command v25 workflow."""
import json
from pathlib import Path
import pytest

from born_ladder.reproduction.v25.specification import Specification
from born_ladder.reproduction.v25.seeds import acquisition_identities

SPEC = Path(__file__).resolve().parents[2] / 'specifications'


def test_registered_seed_identities_are_disjoint():
    spec = Specification(SPEC)
    identities = acquisition_identities(spec.science)
    assert len(identities) == len({r['seed'] for r in identities}) == 1000
    assert all(int(float(r['seed'])) == r['seed'] and 0 <= r['seed'] < 2**64 for r in identities)
    assert min(r['seed'] for r in identities) > 910000 + 50000 + 23
    for campaign in ('cross-term', 'competitor'):
        seeds = spec.grid(campaign)['seeds']
        assert all(b-a == 1000 for a, b in zip(seeds, seeds[1:]))
        assert sum(r['campaign'] == campaign for r in identities) == 500


def setup_workflow(monkeypatch, tmp_path):
    from born_ladder.reproduction.v25 import workflow, pipeline
    monkeypatch.setattr(pipeline, 'worker_identity', lambda spec: {'numpy': '2.5.2', 'threads': 1})
    monkeypatch.setattr('born_ladder.reproduction.runs.validate_output', lambda path, repo: Path(path))
    calls = []
    def runs(**kwargs):
        calls.append(('runs', kwargs['grid'], kwargs['workers']))
        return {'failed': 0, 'unlaunched': 0}
    def units(**kwargs):
        calls.append(('units', kwargs['evaluation'], kwargs['workers']))
        root = Path(kwargs['output']); root.mkdir(parents=True, exist_ok=True)
        (root/'collection_0001.json').write_text('{}')
        return {'incomplete': 0}
    def infer(**kwargs):
        calls.append(('inference', kwargs['evaluation']))
        root = Path(kwargs['output']); (root/'attempt').mkdir(parents=True, exist_ok=True)
        (root/'complete.json').write_text(json.dumps({'attempt': 'attempt'}))
        (root/'attempt'/'population.json').write_text(json.dumps({
            'joint': {'status': 'SYNTHETIC_TEST_VERDICT'}, 'paper_values': {
                'synthetic endpoint': {'status': 'SYNTHETIC_TEST', 'point': 0.25, 'lower': 0, 'upper': 0.5}}}))
    monkeypatch.setattr('born_ladder.reproduction.runs.run_grid', runs)
    monkeypatch.setattr('born_ladder.reproduction.v25.fresh.construct_fresh', units)
    monkeypatch.setattr('born_ladder.reproduction.v25.fresh.infer_fresh', infer)
    monkeypatch.setattr(workflow.subprocess, 'run', lambda *a, **k: None)
    return workflow, calls


def test_whole_workflow_calls_capture_units_inference_in_order(monkeypatch, tmp_path):
    workflow, calls = setup_workflow(monkeypatch, tmp_path)
    result = workflow.run(output=tmp_path/'output', workers=4, specifications=SPEC)
    assert result['status'] == 'complete'
    assert calls == [('runs', 'v25-competitor', 4), ('units', 'competitor', 4), ('inference', 'competitor'),
                     ('runs', 'v25-cross-term', 4), ('units', 'cross-term', 4), ('inference', 'cross-term')]
    assert (tmp_path/'output'/'verdicts.csv').read_text().startswith('evaluation,endpoint,status,point,lower,upper')
    before = (tmp_path/'output'/'verdicts.json').read_bytes()
    assert workflow.run(output=tmp_path/'output', workers=8, specifications=SPEC)['status'] == 'complete'
    assert (tmp_path/'output'/'verdicts.json').read_bytes() == before


def test_interrupted_acquisition_never_scores_incomplete_captures(monkeypatch, tmp_path):
    workflow, calls = setup_workflow(monkeypatch, tmp_path)
    monkeypatch.setattr('born_ladder.reproduction.runs.run_grid', lambda **k: {'failed': 0, 'unlaunched': 1})
    result = workflow.run(output=tmp_path/'output', workers=2, specifications=SPEC)
    assert result['incomplete'] and result['stage'] == 'runs'
    assert not calls and not (tmp_path/'output'/'verdicts.csv').exists()


def test_removed_gates_are_not_public_cli_requirements(capsys, monkeypatch):
    from born_ladder.__main__ import main
    monkeypatch.setattr('born_ladder.reproduction.stage_environment.ensure_environment', lambda *a: None)
    with pytest.raises(SystemExit) as stopped:
        main(['reproduce', 'v25', '--help'])
    assert stopped.value.code == 0
    help_text = capsys.readouterr().out
    assert '--workers' in help_text and '--synthetic' in help_text
    assert '--freeze' not in help_text and '--seed-record' not in help_text


def test_version_check_accepts_cpython_patch_variants(monkeypatch):
    from born_ladder.reproduction import stage_environment as stage
    profile = json.loads((SPEC/'environments'/'predictive_v25.json').read_bytes())
    monkeypatch.setattr(stage.platform, 'python_version', lambda: '3.12.99')
    monkeypatch.setattr(stage.platform, 'python_implementation', lambda: 'CPython')
    assert stage.base_matches(profile)
    monkeypatch.setattr(stage.platform, 'python_version', lambda: '3.13.0')
    assert not stage.base_matches(profile)
