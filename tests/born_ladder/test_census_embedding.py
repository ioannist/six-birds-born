"""The 120-context proof must preserve the census and full old-view binding."""
import importlib.util
import json
import os
from pathlib import Path
import pytest
from born_ladder.claims import Evidence

ROOT=Path(__file__).resolve().parents[2]


def checker():
    path=ROOT/'lean_born/tools/check_census_embedding.py'
    spec=importlib.util.spec_from_file_location('census_embedding_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_census_embedding_refuses_replaced_manifest(tmp_path):
    m=checker();path=tmp_path/'replacement.json';path.write_text('[]')
    class Inputs:
        def config(self,_):return dict.fromkeys(m.MANIFESTS,'replacement')
        def path(self,_):return path
    with pytest.raises(ValueError,match='manifest commitment differs'):
        m.check(Inputs(),tmp_path/'missing-lean')


@pytest.mark.data
def test_census_embedding_checks_full_records_and_integer_payload(tmp_path):
    m=checker();e=Evidence(os.environ['BORN_LADDER_DATA']);c=e.config('P10')
    original=e.read(c['original']);row=original[0]
    context=e.read(c['contexts']+'/'+row['unit_id']+'/CONTEXT.json')
    certificate=json.loads(json.dumps(row['certificates']['strictness']))
    certificate['complete_equal_old_view']['lag']=9
    with pytest.raises(ValueError,match='full anonymous initial record differs'):
        m.extract(context,certificate)
    target=tmp_path/'BornCalculus';target.mkdir()
    source=(ROOT/'lean_born/BornCalculus/CensusInputs.lean').read_text()
    path=target/'CensusInputs.lean';path.write_text(source)
    assert m.check(e,tmp_path)['contexts']==120
    path.write_text(source.replace('def censusJ','def alteredCensusJ',1))
    with pytest.raises(ValueError,match='integer frame/label/witness embedding differs'):
        m.check(e,tmp_path)

@pytest.mark.data
def test_b10_binding_covers_group_coordinate_witnesses(tmp_path):
    m=checker();e=Evidence(os.environ['BORN_LADDER_DATA'])
    target=tmp_path/'BornCalculus';target.mkdir()
    for name in ('CensusInputs.lean','CensusAtomInputs.lean'):
        (target/name).write_text((ROOT/'lean_born/BornCalculus'/name).read_text())
    assert m.check(e,tmp_path,'B10')['active_atoms']==1006
    p=target/'CensusAtomInputs.lean'
    p.write_text(p.read_text().replace('def atomSecond','def alteredAtomSecond',1))
    with pytest.raises(ValueError,match='coordinate witness embedding differs'):
        m.check(e,tmp_path,'B10')
