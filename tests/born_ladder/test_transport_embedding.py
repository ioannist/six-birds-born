"""The concrete transport proof must stay bound to the original coefficients."""
import importlib.util
import json
import os
from pathlib import Path
import pytest

from born_ladder.claims import Evidence

ROOT=Path(__file__).resolve().parents[2]


def checker():
    path=ROOT/'lean_born/tools/check_transport_embedding.py'
    spec=importlib.util.spec_from_file_location('b04_embedding_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_transport_embedding_refuses_uncommitted_input(tmp_path):
    module=checker();path=tmp_path/'context.json';path.write_text(json.dumps({'replacement':True}))
    class Inputs:
        def config(self,_):return dict.fromkeys(module.COMMITMENTS,'replacement')
        def path(self,_):return path
    with pytest.raises(ValueError,match='input commitment differs'):
        module.check(Inputs(),tmp_path/'missing-lean')


@pytest.mark.data
def test_transport_embedding_checks_successors_not_only_initial_fibers(tmp_path):
    module=checker();e=Evidence(os.environ['BORN_LADDER_DATA'])
    target=tmp_path/'BornCalculus';target.mkdir()
    path=target/'B04Inputs.lean'
    source=(ROOT/'lean_born/BornCalculus/B04Inputs.lean').read_text()
    path.write_text(source)
    assert module.check(e,tmp_path)['fiber_pairs']==4
    # Keep the kernel/initial witnesses and alter only a certificate block.
    left,right=source.split('def b04LoQ',1)
    path.write_text(left+'def b04LoQ'+right.replace(' : ℚ) /','0 : ℚ) /',1))
    with pytest.raises(ValueError,match='kernel/fiber/root-certificate embedding differs'):
        module.check(e,tmp_path)
