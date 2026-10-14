"""False bindings must fail separately from the concrete kernel theorem."""
import importlib.util
import json
import os
from pathlib import Path
import pytest

from born_ladder.claims import Evidence
from born_ladder.__main__ import REGISTRY

ROOT = Path(__file__).resolve().parents[2]


def checker():
    path=ROOT/'lean_born/tools/check_fragment_embedding.py'
    spec=importlib.util.spec_from_file_location('b06_embedding_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_concrete_fragment_endpoints_are_the_verification_target():
    assert {'b06_event_count','b06_proper_event_count','b06_non_trace_finite_fragment'} <= set(REGISTRY['B06'][2])


def test_fragment_binding_refuses_uncommitted_input_before_extraction(tmp_path):
    module=checker();path=tmp_path/'input.json';path.write_text(json.dumps({'replacement':True}))
    class Inputs:
        def config(self,_):return {'context':'context','certificate':'certificate'}
        def path(self,_):return path
    with pytest.raises(ValueError,match='input commitment differs'):
        module.check(Inputs(),tmp_path/'missing-lean')


@pytest.mark.data
def test_fragment_binding_covers_effects_and_ordered_program_registration(tmp_path):
    module=checker();e=Evidence(os.environ['BORN_LADDER_DATA'])
    target=tmp_path/'BornCalculus';target.mkdir()
    for name in ('B06Inputs.lean','B06Witness.lean'):
        (target/name).write_bytes((ROOT/'lean_born/BornCalculus'/name).read_bytes())
    result=module.check(e,tmp_path)
    assert result['atomic_effects']==8 and result['programs']==12
    assert result['registered_event_occurrences']==2340
    inputs=target/'B06Inputs.lean';original=inputs.read_text()
    inputs.write_text(original.replace('(29 : ℚ) / 32','(28 : ℚ) / 32',1))
    with pytest.raises(ValueError,match='effect/metric embedding differs'):
        module.check(e,tmp_path)
    inputs.write_text(original)
    programs=target/'B06Witness.lean'
    # Same arities/event count, different apparatus word: count alone cannot
    # establish the mathematical family used by the original certificate.
    programs.write_text(programs.read_text().replace(
        '| 4 => [b06RawTest,b06PackageTest]',
        '| 4 => [b06RawTest,b06JointTest]',1))
    with pytest.raises(ValueError,match='Lean program registration differs'):
        module.check(e,tmp_path)
