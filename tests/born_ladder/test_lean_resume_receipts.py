"""No-op Lean builds retain their producing receipts; real builds stay strict."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from born_ladder.reproduction import pipeline as P
from born_ladder.reproduction.lean_comparison import log_receipt


def prepare(tmp_path):
    root=tmp_path/'lean';root.mkdir()
    build={'status':'PASS','modules':347,'fresh_modules':347,'wall_seconds':2.,
           'peak_tree_rss_bytes':100,'max_processes':2,'max_lean_processes':2,'sample_interval_seconds':.05}
    audit={'status':'PASS','fresh':True,'forbidden':{},
           'measurement':{k:build[k] for k in ('wall_seconds','peak_tree_rss_bytes','max_processes','max_lean_processes','sample_interval_seconds')}}
    for name,data in [('build_receipt.json',build),('audit_receipt.json',audit)]:
        (root/name).write_text(json.dumps(data)+'\n')
    for name,text in [('BornCalculus.lean','import BornCalculus.Basic'),
                      ('BornCalculus/Basic.lean','theorem test : True := trivial'),
                      ('lakefile.toml','name = "BornCalculus"'),('lake-manifest.json','{}'),
                      ('lean-toolchain','leanprover/lean4:v4.28.0'),
                      ('.lake/build/lib/lean/BornCalculus/Basic.olean','compiled')]:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    (root/'build_audit_pair.json').write_text(json.dumps(P.lean_pair_commitment(root)))
    coverage={'status':'APPLICABLE','full_cohort_inputs':True,'census_cases':2122}
    def render():
        (root/'formal_coverage.json').write_text(json.dumps(coverage))
    return root,build,audit,render


def test_noop_build_preserves_receipt_bytes_and_skips_audit(tmp_path,monkeypatch):
    root,build,_,render=prepare(tmp_path)
    before={name:(root/name).read_bytes() for name in ('build_receipt.json','audit_receipt.json','build_audit_pair.json')}
    calls=[]
    def child(argv,**kw):
        calls.append(argv[1]);assert argv[1]=='lean'
        kw['stdout'].write((json.dumps({**build,'fresh_modules':0,'max_lean_processes':0})+'\n').encode())
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(P.subprocess,'run',child)
    for _ in range(2):
        result=P.run_lean_step(lean_directory=root,logs=tmp_path/'logs',render=render,require_full_cohort=True)
        assert result['build_status']=='BUILT_AND_AUDITED'
        assert {name:(root/name).read_bytes() for name in before}==before
    assert calls==['lean','lean']


@pytest.mark.parametrize('fresh,maximum',[(0,0),(1,0)])
def test_noop_without_producing_receipt_and_invalid_real_build_fail(tmp_path,monkeypatch,fresh,maximum):
    root,build,_,render=prepare(tmp_path)
    (root/'build_receipt.json').unlink()
    def child(argv,**kw):
        kw['stdout'].write((json.dumps({**build,'fresh_modules':fresh,'max_lean_processes':maximum})+'\n').encode())
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(P.subprocess,'run',child)
    with pytest.raises(ValueError,match='force a real|invalid measurement'):
        P.run_lean_step(lean_directory=root,logs=tmp_path/'logs',render=render,require_full_cohort=True)


def test_new_real_build_publishes_new_build_and_audit(tmp_path,monkeypatch):
    root,build,audit,render=prepare(tmp_path)
    def child(argv,**kw):
        value={**build,'wall_seconds':3.} if argv[1]=='lean' else {**audit,'declarations':5058}
        if argv[1]=='lean-audit':
            # stderr is merged into the stage log; buffering can put the
            # readable summary before the JSON receipt.
            kw['stdout'].write(b'Lean audit: PASS, 5058 declarations, axioms Classical.choice, Quot.sound, propext; forbidden: none\n')
        kw['stdout'].write((json.dumps(value)+'\n').encode())
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(P.subprocess,'run',child)
    P.run_lean_step(lean_directory=root,logs=tmp_path/'logs',render=render,require_full_cohort=True)
    assert json.loads((root/'build_receipt.json').read_bytes())['wall_seconds']==3.
    assert json.loads((root/'audit_receipt.json').read_bytes())['declarations']==5058
    assert json.loads((root/'build_audit_pair.json').read_bytes())==P.lean_pair_commitment(root)


def test_log_binding_uses_last_producing_build(tmp_path):
    log=tmp_path/'lean.log'
    real={'modules':347,'fresh_modules':347,'max_lean_processes':2}
    log.write_text(json.dumps(real)+'\n'+json.dumps({**real,'fresh_modules':0,'max_lean_processes':0})+'\n')
    assert log_receipt(log,'modules')==real


def test_bundle_can_resume_after_noop_lean_step(tmp_path,monkeypatch):
    from born_ladder.reproduction.regenerated_bundle import assemble
    root,build,_,render=prepare(tmp_path)
    def child(argv,**kw):
        kw['stdout'].write((json.dumps({**build,'fresh_modules':0,'max_lean_processes':0})+'\n').encode())
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(P.subprocess,'run',child)
    P.run_lean_step(lean_directory=root,logs=tmp_path/'logs',render=render)
    names=('worked','census','attachments','competitor_evaluation','cross_term_evaluation','test_b','locked','lean','competitor_units','cross_term_units')
    for name in names:
        if name=='lean':continue
        directory=tmp_path/name;directory.mkdir();(directory/'scientific.json').write_text('{"value":1}')
    (tmp_path/'pipeline.json').write_text(json.dumps({'profile':'full','components':dict(zip(names,names))}))
    assemble(tmp_path,tmp_path/'bundle')
    before=(tmp_path/'bundle/bundle.json').read_bytes()
    P.run_lean_step(lean_directory=root,logs=tmp_path/'logs',render=render)
    assemble(tmp_path,tmp_path/'bundle')
    assert (tmp_path/'bundle/bundle.json').read_bytes()==before


def test_interrupted_audit_cannot_reuse_previous_pair(tmp_path,monkeypatch):
    import subprocess
    root,build,audit,render=prepare(tmp_path)
    before={name:(root/name).read_bytes() for name in ('build_receipt.json','audit_receipt.json')}
    def interrupted(argv,**kw):
        assert not (root/'build_audit_pair.json').exists()
        if argv[1]=='lean-audit':raise subprocess.CalledProcessError(1,argv)
        kw['stdout'].write((json.dumps({**build,'wall_seconds':4.})+'\n').encode())
    monkeypatch.setattr(P.subprocess,'run',interrupted)
    with pytest.raises(subprocess.CalledProcessError):
        P.run_lean_step(lean_directory=root,logs=tmp_path/'logs',render=render)
    assert {name:(root/name).read_bytes() for name in before}==before
    def noop(argv,**kw):
        kw['stdout'].write((json.dumps({**build,'fresh_modules':0})+'\n').encode())
    monkeypatch.setattr(P.subprocess,'run',noop)
    with pytest.raises(ValueError,match='force a real'):
        P.run_lean_step(lean_directory=root,logs=tmp_path/'logs',render=render)


@pytest.mark.parametrize('name',['BornCalculus/Basic.lean','.lake/build/lib/lean/BornCalculus/Basic.olean',
                                'lakefile.toml','lean-toolchain','build_receipt.json','audit_receipt.json',
                                'build_audit_pair.json'])
def test_changed_source_artifact_or_receipt_blocks_noop_resume(tmp_path,monkeypatch,name):
    root,build,_,render=prepare(tmp_path)
    path=root/name;path.write_text(path.read_text()+'\nchanged' if not name.endswith('.json') else path.read_text()+' ')
    if name=='build_audit_pair.json':path.unlink()
    def child(argv,**kw):
        assert argv[1]=='lean'
        kw['stdout'].write((json.dumps({**build,'fresh_modules':0})+'\n').encode())
    monkeypatch.setattr(P.subprocess,'run',child)
    with pytest.raises(ValueError,match='force a real'):
        P.run_lean_step(lean_directory=root,logs=tmp_path/'logs',render=render)


def test_changes_during_audit_do_not_publish_pair(tmp_path,monkeypatch):
    root,build,audit,render=prepare(tmp_path)
    before=(root/'build_receipt.json').read_bytes()
    def child(argv,**kw):
        if argv[1]=='lean-audit':(root/'BornCalculus/Basic.lean').write_text('changed')
        value=build if argv[1]=='lean' else audit
        kw['stdout'].write((json.dumps(value)+'\n').encode())
    monkeypatch.setattr(P.subprocess,'run',child)
    with pytest.raises(ValueError,match='changed during audit'):
        P.run_lean_step(lean_directory=root,logs=tmp_path/'logs',render=render)
    assert not (root/'build_audit_pair.json').exists()
    assert (root/'build_receipt.json').read_bytes()==before


def test_changed_audit_implementation_blocks_noop(tmp_path,monkeypatch):
    root,build,_,render=prepare(tmp_path)
    original=P.sha
    monkeypatch.setattr(P,'sha',lambda p:'changed' if Path(p).name=='audit_declarations.py' else original(p))
    def child(argv,**kw):
        kw['stdout'].write((json.dumps({**build,'fresh_modules':0})+'\n').encode())
    monkeypatch.setattr(P.subprocess,'run',child)
    with pytest.raises(ValueError,match='force a real'):
        P.run_lean_step(lean_directory=root,logs=tmp_path/'logs',render=render)


def test_changed_dependency_artifact_blocks_noop(tmp_path,monkeypatch):
    root,build,_,render=prepare(tmp_path)
    artifact=root/'.lake/packages/mathlib/.lake/build/lib/lean/Mathlib.olean'
    artifact.parent.mkdir(parents=True);artifact.write_text('old')
    (root/'build_audit_pair.json').write_text(json.dumps(P.lean_pair_commitment(root)))
    artifact.write_text('changed')
    def child(argv,**kw):
        kw['stdout'].write((json.dumps({**build,'fresh_modules':0})+'\n').encode())
    monkeypatch.setattr(P.subprocess,'run',child)
    with pytest.raises(ValueError,match='force a real'):
        P.run_lean_step(lean_directory=root,logs=tmp_path/'logs',render=render)


def test_changed_toolchain_kernel_blocks_noop(tmp_path,monkeypatch):
    root,build,_,render=prepare(tmp_path)
    original=P.sha
    monkeypatch.setattr(P,'sha',lambda p:'changed' if Path(p).name=='libleanshared.so' else original(p))
    def child(argv,**kw):
        kw['stdout'].write((json.dumps({**build,'fresh_modules':0})+'\n').encode())
    monkeypatch.setattr(P.subprocess,'run',child)
    with pytest.raises(ValueError,match='force a real'):
        P.run_lean_step(lean_directory=root,logs=tmp_path/'logs',render=render)
