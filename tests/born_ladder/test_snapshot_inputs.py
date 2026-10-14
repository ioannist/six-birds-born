"""Portable historical byte admission; no private Git or source substitution."""
import ast
import hashlib
import json
from pathlib import Path
import pytest
from born_ladder.snapshot.historical import HistoricalInputs
from born_ladder.snapshot.g2c_v23 import remeasure_authorization_descriptor
from born_ladder.snapshot.errors import IncompleteCampaign, SpecMismatch


def bundle(tmp_path):
    root=tmp_path/'evidence';root.mkdir();raw=b'archived original source\n';h=hashlib.sha256(raw).hexdigest()
    (root/'preserved').write_bytes(raw)
    row={'file':'preserved','sha256':h,'size_bytes':len(raw)}
    blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    (root/'manifest.json').write_text(json.dumps({'schema':'born_snapshot_historical_inputs_v1',
       'files':{'scripts/rebuild1/g2c_evaluate.py@'+h:row},
       'commit_files':{'frozen:scripts/rebuild1/g2c_evaluate.py':row},'tags':{}}))
    return root,raw,h,blob


def test_explicit_inputs_missing_altered_and_wrong_blob_refused(tmp_path):
    with pytest.raises(IncompleteCampaign,match='historical_root'):HistoricalInputs(None)
    root,raw,h,blob=bundle(tmp_path);history=HistoricalInputs(root)
    assert history.commit_bytes('frozen','scripts/rebuild1/g2c_evaluate.py',expected_sha256=h,object_id=blob)==raw
    with pytest.raises(SpecMismatch,match='blob identity'):history.commit_bytes('frozen','scripts/rebuild1/g2c_evaluate.py',object_id='0'*40)
    with pytest.raises(IncompleteCampaign):history.path('missing')
    (root/'preserved').write_bytes(b'altered')
    with pytest.raises(SpecMismatch,match='byte commitment'):history.read('scripts/rebuild1/g2c_evaluate.py',expected_sha256=h)


def test_relocated_release_source_never_counts_as_historical_execution(tmp_path):
    root,raw,h,blob=bundle(tmp_path);history=HistoricalInputs(root);public=tmp_path/'public';public.mkdir()
    name='scripts/rebuild1/g2c_evaluate.py';p=public/name;p.parent.mkdir(parents=True);p.write_bytes(b'new release implementation')
    row={'path':name,'sha256':h,'size_bytes':len(raw),'role':'v23_scientific_evaluator'}
    kwargs=dict(repo_root=public,completion_writer_input=None,completion_writer_original_path=None,historical_inputs=history)
    assert remeasure_authorization_descriptor(row,**kwargs)==root/'preserved'
    row['sha256']=hashlib.sha256(p.read_bytes()).hexdigest();row['size_bytes']=p.stat().st_size
    with pytest.raises(IncompleteCampaign,match='missing preserved historical'):remeasure_authorization_descriptor(row,**kwargs)


def test_bundle_escape_and_unregistered_source_refused(tmp_path):
    root,raw,h,blob=bundle(tmp_path);history=HistoricalInputs(root)
    history.manifest['files']['escape']={'file':'../outside','sha256':h,'size_bytes':len(raw)}
    with pytest.raises(SpecMismatch,match='malformed'):history.path('escape')
    row={'path':'scripts/rebuild1/other.py','sha256':h,'size_bytes':len(raw),'role':'source'}
    with pytest.raises(IncompleteCampaign,match='missing preserved'):remeasure_authorization_descriptor(row,repo_root=tmp_path,completion_writer_input=None,completion_writer_original_path=None,historical_inputs=history)


def test_snapshot_contains_no_git_execution_or_campaign_entrypoints():
    root=Path('src/born_ladder/snapshot')
    removed=['adopt_g2h_h1_h2_v10','campaign','evaluate_g2h_campaign','finalize_g2h_h3_incomplete','verify_large_outputs','g2h_campaign','g2x_campaign','g2c_campaign','g2c_v22_launcher']
    assert all(not (root/(name+'.py')).exists() for name in removed)
    for p in root.glob('*.py'):
        tree=ast.parse(p.read_text())
        for call in (n for n in ast.walk(tree) if isinstance(n,ast.Call)):
            if isinstance(call.func,ast.Attribute) and call.func.attr in {'run','Popen','check_output'} and call.args and isinstance(call.args[0],(ast.List,ast.Tuple)):
                first=call.args[0].elts[0]
                assert not (isinstance(first,ast.Constant) and first.value=='git'),(p,call.lineno)
        assert not any(isinstance(n,ast.FunctionDef) and (n.name.startswith('run_campaign') or n.name=='write_authorization') for n in ast.walk(tree))


def test_legacy_receipt_sources_use_the_same_explicit_relocation(tmp_path):
    from types import SimpleNamespace
    from born_ladder.snapshot.evaluate_g2c_campaign import _fixed_identity_rows
    root,raw,h,blob=bundle(tmp_path);history=HistoricalInputs(root)
    spec=SimpleNamespace(repo_root=tmp_path/'absent-release',history=history)
    name='scripts/rebuild1/g2c_evaluate.py';role='v22_scientific_evaluator'
    row={'path':name,'role':role,'sha256':h,'size_bytes':len(raw)}
    assert _fixed_identity_rows(spec,[(name,role)],recorded_rows=[row])==[row]
    with pytest.raises(IncompleteCampaign,match='identity census'):
        _fixed_identity_rows(spec,[(name,role)],recorded_rows=[])
    (root/'preserved').write_bytes(b'corrupt')
    with pytest.raises(SpecMismatch):_fixed_identity_rows(spec,[(name,role)],recorded_rows=[row])
