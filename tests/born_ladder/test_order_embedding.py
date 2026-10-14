"""Original principal-root word order must be bound to the actual effect table."""
import importlib.util,json,os
from pathlib import Path
import pytest
from born_ladder.claims import Evidence
ROOT=Path(__file__).resolve().parents[2]

def checker():
    p=ROOT/'lean_born/tools/check_order_embedding.py'
    spec=importlib.util.spec_from_file_location('order_embedding_test',p)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m

def test_order_embedding_refuses_replaced_context(tmp_path):
    m=checker();p=tmp_path/'context.json';p.write_text('{}')
    class Inputs:
        def config(self,_):return {'context':'replacement'}
        def path(self,_):return p
    with pytest.raises(ValueError,match='context commitment differs'):m.check(Inputs(),tmp_path)

@pytest.mark.data
def test_order_embedding_binds_scalar_probability_certificates(tmp_path):
    m=checker();e=Evidence(os.environ['BORN_LADDER_DATA']);target=tmp_path/'BornCalculus';target.mkdir()
    for name in ('B06Inputs.lean','B07Inputs.lean'):
        (target/name).write_bytes((ROOT/'lean_born/BornCalculus'/name).read_bytes())
    assert m.check(e,tmp_path)['word_orders']==2
    p=target/'B07Inputs.lean';p.write_text(p.read_text().replace('def b07LowerQ','def alteredLowerQ',1))
    with pytest.raises(ValueError,match='coefficient/root/order embedding differs'):m.check(e,tmp_path)
