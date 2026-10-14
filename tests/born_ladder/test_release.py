"""Packaging, fixture/data separation and per-claim dispatch regressions."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import site
import subprocess
import sys

import pytest
from born_ladder.__main__ import REGISTRY, verify_claim
from born_ladder.claims import Evidence, analytic_control


def test_registry_and_clear_missing_data():
    assert set(REGISTRY)=={f'P{i:02}' for i in range(1,15)}|{f'B{i:02}' for i in range(1,17)}|{'TB01'}
    p=subprocess.run([sys.executable,'-m','born_ladder','verify','--list'],capture_output=True,text=True)
    assert p.returncode==0 and len(p.stdout.splitlines())==31
    for identifier,(_,lane,_) in REGISTRY.items():
        if lane=='data':
            with pytest.raises(ValueError,match=identifier+' requires --data'):
                verify_claim(identifier)
    p=subprocess.run([sys.executable,'-m','born_ladder','verify','TB01'],capture_output=True,text=True)
    assert p.returncode==1 and 'FAIL TB01' in p.stderr and 'local' in p.stderr
    for identifier in ('P06','B02','B03','B14'):
        # The default Python lane does not require compiled Lean artifacts.
        # The full command (including its formal audit) runs under make verify.
        assert analytic_control(identifier)


def test_untrusted_input_reader_integrity_and_escape(tmp_path):
    f=tmp_path/'input.json';f.write_text('{}')
    doc={'schema':'born_claim_bundle_v1','roots':{'local':'.'},'files':{'local/input.json':hashlib.sha256(f.read_bytes()).hexdigest()},'claims':{}}
    p=tmp_path/'bundle.json';p.write_text(json.dumps(doc));e=Evidence(p, trusted=False)
    assert e.read('local/input.json')=={}
    with pytest.raises(ValueError,match='not admitted'):e.path('local/other')
    f.write_text('changed')
    with pytest.raises(ValueError,match='commitment'):Evidence(p, trusted=False)
    doc['files']={'local/../escape':'0'*64};p.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match='escapes'):Evidence(p, trusted=False)


def test_installed_environment_and_synthetic_budget():
    import born_ladder
    import numpy
    assert site.ENABLE_USER_SITE is False
    assert numpy.__version__=='2.4.4'
    assert 'site-packages' in str(Path(born_ladder.__file__).resolve())
    assert importlib.util.find_spec('torch') is None
    fixture_root=Path(__file__).with_name('fixtures')
    # Allow the complete source/spec comparison records and retained RNG draw
    # prefixes needed by reproduction tests (about 200 KiB), without trimming
    # useful references. This fixture guard is not a repository size budget.
    assert sum(p.stat().st_size for p in fixture_root.rglob('*') if p.is_file()) <= 256*1024
    # Synthetic controls and code/spec hashes are not empirical historical
    # data; the RNG reference honestly identifies its retained-byte origin.
    expected_history = {'ordinary.json':False,'basis.json':False,'tiny.json':False,
        'e2e_source_equivalence.json':False,'e2e_spec_value_reference.json':False,
        'e2e_census_symbolic_reference.json':False,
        'e2e_rng_reference.json':True}
    assert {p.name for p in fixture_root.glob('*.json')} == set(expected_history)
    for p in fixture_root.glob('*.json'):
        document=json.loads(p.read_text())
        if p.name=='e2e_census_symbolic_reference.json':
            # This source-hash/adaptation reference has no historical-data flag.
            assert document.get('historical_data',False) is expected_history[p.name]
        else:
            assert document['historical_data'] is expected_history[p.name]
    rng_reference=json.loads((fixture_root/'e2e_rng_reference.json').read_text())
    assert rng_reference['reference_type']=='retained_rng_reference_bytes_not_empirical_measurements'
    assert len(rng_reference['g2c']['membership']['sampled_seed_indices'])==20
    assert all(len(row)==20 for ref in rng_reference['test_b'].values() for row in ref['rows'])
    assert all(len(ref['rows'])==64 for ref in rng_reference['test_b'].values())


def load_tool(name):
    path=Path('lean_born/tools')/(name+'.py')
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_portable_lean_axiom_audit_refuses_corruption():
    tool=load_tool('audit_declarations');name='BornCalculus.endpoint'
    good=f"'{name}' depends on axioms: [propext, Classical.choice, Quot.sound]"
    assert tool.verify(good,[name])['status']=='PASS'
    for text in ('', good.replace('propext','sorryAx'), good+'\nerror: invalid'):
        with pytest.raises(ValueError):tool.verify(text,[name])
    assert {p.name for p in Path('lean_born/tools').glob('*.py')}=={'check_embedding.py','check_fragment_embedding.py', 'check_completion_embedding.py', 'check_census_embedding.py', 'check_order_embedding.py','check_transport_embedding.py','audit_declarations.py'}


@pytest.mark.data
def test_historical_fixture_lane():
    e=Evidence(os.environ['BORN_LADDER_DATA'])
    from born_ladder.independent import recompute
    for path in e.config('fixtures')['paths']:
        fixture=e.read(path);ctx=fixture['context'];expected=fixture['reviewed_certificates']['certificates']
        r=recompute(ctx)
        assert r['delta_squared_exact']==expected['correspondence']['delta_squared_exact']
        assert r['witness']['pair']==expected['strictness']['pair']
        assert r['witness']['difference']==expected['strictness']['first_separating_readout']['difference_exact']


def test_unanchored_historical_bundle_fails_before_dispatch(tmp_path):
    bundle=tmp_path/'bundle.json'
    bundle.write_text(json.dumps({'schema':'born_claim_bundle_v1','roots':{'local':'.'},'files':{},'claims':{'P12':{'source_root':'local'}}}))
    command=[sys.executable,'-m','born_ladder','verify','P12','--data',str(bundle)]
    a=subprocess.run(command,capture_output=True,text=True)
    assert a.returncode==1 and 'trust anchor mismatch' in a.stderr and 'Traceback' not in a.stderr
    b=subprocess.run(command+['--historical-root',str(tmp_path/'missing')],capture_output=True,text=True)
    assert b.returncode==1 and 'trust anchor mismatch' in b.stderr and 'Traceback' not in b.stderr


def test_actual_coordinate_discrepancy_with_equal_projector():
    from fractions import Fraction as F
    from synthetic import fixture
    c=fixture('basis')['context'];w=list(map(F,c['exact']['w']));n=len(w);s=F(c['exact']['s'])
    # Two explicitly different bases of the same plane; no SVD or tolerance.
    B=[[F(1),x] for x in w];C=[[F(1),x+F(1,1000)] for x in w]
    def projector(frame):
        G=[[sum(row[i]*row[j] for row in frame) for j in range(2)] for i in range(2)]
        d=G[0][0]*G[1][1]-G[0][1]*G[1][0]
        inv=[[G[1][1]/d,-G[0][1]/d],[-G[1][0]/d,G[0][0]/d]]
        return [[sum(left[i]*inv[i][j]*right[j] for i in range(2) for j in range(2)) for right in frame] for left in frame]
    assert B!=C and max(abs(a-b) for row,other in zip(B,C) for a,b in zip(row,other))==F(1,1000)
    assert projector(B)==projector(C)==[[F(x) for x in row] for row in c['exact']['P']]


def test_explicit_artifact_stream_and_reconstructed_hash(tmp_path):
    import shutil
    from born_ladder.claims import verify_artifact
    raw=b'non-empirical archive-control\n';file=tmp_path/'raw';file.write_bytes(raw)
    digest=hashlib.sha256(raw).hexdigest()
    doc={'schema':'born_claim_bundle_v1','roots':{'local':'.'},'files':{'local/raw':digest},'claims':{}}
    bundle=tmp_path/'bundle.json';bundle.write_text(json.dumps(doc));e=Evidence(bundle, trusted=False)
    assert verify_artifact(e,'local/raw')==digest
    if not shutil.which('zstd'):
        pytest.skip('zstd is optional: needed only for compressed historical archives')
    blob=subprocess.run(['zstd','-q','--stdout'],input=raw,capture_output=True,check=True).stdout
    (tmp_path/'chunk').write_bytes(blob);h=hashlib.sha256(blob).hexdigest()
    manifest={'artifacts':[{'archive_id':'control','chunks':[{'path':'chunk','sha256':h,'size_bytes':len(blob)}],
        'compressed_stream':{'sha256':h,'size_bytes':len(blob)},'original_sha256':digest,'original_size_bytes':len(raw)}]}
    p=tmp_path/'archive.json';p.write_text(json.dumps(manifest))
    doc['files'].update({'local/chunk':h,'local/archive.json':hashlib.sha256(p.read_bytes()).hexdigest()});bundle.write_text(json.dumps(doc))
    e=Evidence(bundle, trusted=False);item={'manifest':'local/archive.json','archive_id':'control','root':'local'}
    assert verify_artifact(e,item)==digest
    manifest['artifacts'][0]['original_sha256']='0'*64;p.write_text(json.dumps(manifest))
    doc['files']['local/archive.json']=hashlib.sha256(p.read_bytes()).hexdigest();bundle.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match='reconstructed artifact'):verify_artifact(Evidence(bundle, trusted=False),item)
