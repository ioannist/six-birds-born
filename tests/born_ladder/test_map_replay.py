"""Use a retained public-export fixture; never manufacture reference maps."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from born_ladder.__main__ import main
from born_ladder.reproduction.map_replay import census_inputs, compare_replay, float_bits, replay_input

FIXTURE = Path(__file__).parent/'fixtures/map_replay/original.json'


def fixture():
    return json.loads(FIXTURE.read_text())


def sealed_census(root, *, corrupt=False, exponent=1):
    context = fixture(); context.pop('fixture_provenance')
    uid = 'retained-fixture'
    context['identity'] = {'unit_id': uid, 'resolution': 2}
    if corrupt:
        context['lens']['raw_by_state'][0] = 1-context['lens']['raw_by_state'][0]
        context['born']['partition'] = context['lens']['raw_by_state'][:]
    matrix = json.dumps(context['kernel'], separators=(',', ':'))
    kernel_path = root/'kernel.jsonl'; kernel_path.parent.mkdir(parents=True)
    kernel_path.write_text('KEY_KERNEL '+matrix+'\n')
    digest = lambda data: hashlib.sha256(data).hexdigest()
    pointer = {'path': 'kernel.jsonl', 'byte_offset': 0, 'char_range': [0, len(matrix)],
               'file_sha256': digest(kernel_path.read_bytes()), 'payload_sha256': digest(matrix.encode()),
               'field_sha256': digest(matrix.encode()), 'exponent': exponent}
    kernel = {'operation': 'K', 'artifact': pointer}
    inventory = [{'unit_id': uid, 'kernel': kernel, 'provenance_key': {'kernel': kernel},
                  'lenses': {name+'_map': context['lens'][name+'_by_state'] for name in ('raw', 'package', 'joint')}}]
    outputs = {'contexts/fixture/CONTEXT.json': context, 'inventory/INVENTORY.json': inventory,
               'summary/structural_completion_results.json': [
                   {'index': 0, 'unit_id': uid, 'status': 'PASS', 'context_directory': 'contexts/fixture'}]}
    for name, value in outputs.items():
        path = root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value))
    artifacts = [{'path': str(p.relative_to(root)), 'sha256': digest(p.read_bytes())} for p in root.rglob('*') if p.is_file()]
    (root/'complete.json').write_text(json.dumps({'status': 'PASS', 'artifacts': artifacts,
        'summary': {'completion_status': 'PASS', 'selected_count': 1,
                    'inventory_directory': 'inventory', 'summary_directory': 'summary'}}))


def test_public_cli_replays_retained_fixture_and_corrupted_map_fails(tmp_path, capsys):
    # The caller supplies --basetemp under repository scratch. Rust is built
    # once, offline, then the same command reruns against a scientific mutation.
    good = tmp_path/'good'; bad = tmp_path/'bad'
    sealed_census(good); sealed_census(bad, corrupt=True)
    original = tmp_path/'original/CONTEXT.json'; original.parent.mkdir()
    original.write_text(FIXTURE.read_text())
    build = tmp_path/'rust-build'
    for root, expected in [(good, 0), (bad, 1)]:
        output = tmp_path/(root.name+'-replay')
        assert main(['reproduce', 'replay-maps', '--census', str(root),
                     '--original-context', str(original), '--output', str(output),
                     '--build-directory', str(build)]) == expected
        summary = json.loads((output/'attempt_0001/summary.json').read_text())
        assert summary['original_worked_case']['status'] == 'PASS'
        if expected:
            assert summary['matched_per_map'] == {'raw': 0, 'package': 1, 'joint': 1}
            difference = summary['mismatches'][0]['differences'][0]
            assert difference['map'] == 'raw'
            assert difference['differing_states'][0]['state'] == 0
        else:
            assert summary['matched_per_map'] == {'raw': 1, 'package': 1, 'joint': 1}
            assert summary['diagnostics_matched'] == {'stationary_exact': 1, 'observable_pi_exact': 1, 'emitted_vectors_exact': 1}
    capsys.readouterr()


def test_exponent_one_required(tmp_path):
    sealed_census(tmp_path/'census', exponent=2)
    with pytest.raises(ValueError, match='exponent one'):
        census_inputs(tmp_path/'census')


def test_historical_stdout_kernel_uses_sealed_storage_view(tmp_path):
    root = tmp_path/'census'; sealed_census(root)
    capture = tmp_path/'capture/stdout.bin'; capture.parent.mkdir()
    (root/'kernel.jsonl').rename(capture)
    name = 'invocations/historical/attempt_0001/stdout.bin'
    inventory_path = root/'inventory/INVENTORY.json'
    inventory = json.loads(inventory_path.read_text())
    for field in (inventory[0]['kernel'], inventory[0]['provenance_key']['kernel']):
        field['artifact']['path'] = name
    inventory_path.write_text(json.dumps(inventory))
    plan = root/'census_plan.json'
    plan.write_text(json.dumps({'logical_to_execution_files': {name: str(capture)}}))
    seal = json.loads((root/'complete.json').read_text())
    seal['artifacts'] = [{'path': str(p.relative_to(root)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                         for p in root.rglob('*') if p.is_file() and p.name != 'complete.json']
    (root/'complete.json').write_text(json.dumps(seal))
    rows, receipt = census_inputs(root)
    assert receipt['sealed_inputs_checked'] is True
    assert rows[0]['input_receipt']['native_kernel_source'] == str(capture)
    assert rows[0]['kernel'] == fixture()['kernel']


@pytest.mark.parametrize('name', ['raw', 'package', 'joint'])
def test_each_scientific_map_difference_is_reported(name):
    c = replay_input(fixture(), 1284, 'example', {})
    r = {'index': c['index'], 'unit_id': c['unit_id'], 'maps': copy.deepcopy(c['retained_maps']),
         'fallback': True, 'stationary_bits': float_bits(c['retained_pi']),
         'observable_pi_bits': float_bits(c['retained_pi']),
         'emitted_vector_bits': [float_bits(v) for v in c['retained_vectors']]}
    r['maps'][name][3] += 1
    result = compare_replay(c, r)
    assert result['status'] == 'FAIL'
    assert result['differences'] == [{'map': name, 'differing_states': [
        {'state': 3, 'retained': c['retained_maps'][name][3],
         'recomputed': c['retained_maps'][name][3]+1, 'absolute_difference': 1}]}]


def test_missing_emitted_component_cannot_pass():
    c = replay_input(fixture(), 0, 'example', {})
    r = {'index': 0, 'unit_id': 'example', 'maps': c['retained_maps'], 'fallback': True,
         'stationary_bits': float_bits(c['retained_pi']), 'observable_pi_bits': float_bits(c['retained_pi']),
         'emitted_vector_bits': []}
    result = compare_replay(c, r)
    assert result['status'] == 'FAIL'
    assert result['diagnostics']['emitted_vectors_exact'] is False
