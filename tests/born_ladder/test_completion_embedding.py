"""B05 must bind both its certificate and the shared transport parameters."""
import importlib.util
import json
import os
from pathlib import Path
import pytest
from born_ladder.claims import Evidence

ROOT=Path(__file__).resolve().parents[2]


def checker():
    path=ROOT/'lean_born/tools/check_completion_embedding.py'
    spec=importlib.util.spec_from_file_location('b05_embedding_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_completion_embedding_refuses_uncommitted_input(tmp_path):
    module=checker();path=tmp_path/'context.json';path.write_text(json.dumps({'replacement':True}))
    class Inputs:
        def config(self,_):return dict.fromkeys(module.COMMITMENTS,'replacement')
        def path(self,_):return path
    with pytest.raises(ValueError,match='input commitment differs'):
        module.check(Inputs(),tmp_path/'missing-lean')


@pytest.mark.data
def test_completion_embedding_binds_shared_metric_and_post_read_successor(tmp_path):
    module=checker();e=Evidence(os.environ['BORN_LADDER_DATA'])
    target=tmp_path/'BornCalculus';target.mkdir()
    shared=(ROOT/'lean_born/BornCalculus/B04Inputs.lean').read_text()
    source=(ROOT/'lean_born/BornCalculus/B05Inputs.lean').read_text()
    shared_path=target/'B04Inputs.lean';shared_path.write_text(shared)
    path=target/'B05Inputs.lean';path.write_text(source)
    assert module.check(e,tmp_path)['atoms']==4
    shared_path.write_text(shared.replace('def b04SQ : ℚ := (','def b04SQ : ℚ := (0',1))
    with pytest.raises(ValueError,match='shared metric/kernel/lens embedding differs'):
        module.check(e,tmp_path)
    shared_path.write_text(shared)
    left,right=source.split('def b05PostQ',1)
    path.write_text(left+'def b05PostQ'+right.replace(' : ℚ) /','0 : ℚ) /',1))
    with pytest.raises(ValueError,match='completion/root/readout embedding differs'):
        module.check(e,tmp_path)
