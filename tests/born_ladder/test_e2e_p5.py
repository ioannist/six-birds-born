"""Targeted Test B production checks; synthetic records and optional Rust binary."""
import hashlib
import json
from pathlib import Path

import pytest

pytest.importorskip('torch', reason='Test B production tests require the optional fitting stack')
pytest.importorskip('scipy', reason='Test B production tests require the optional fitting stack')
from born_ladder.reproduction import test_b as B
from born_ladder.record_tests import real_v6 as R, cert_v6 as C, estimators as E

REPO=Path(__file__).resolve().parents[2]
SPECS=REPO/'specifications'
SAMPLER=REPO/'vendor/pica/target/release/test-b-sampler'


@pytest.fixture
def headers(tmp_path,monkeypatch):
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','RAYON_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):
        monkeypatch.setenv(key,'1')
    h={'type':'header','schema':'test_b_audit_v1','exp':'EXP-112','config':'synthetic','kernel_seed':910000,
       'n':4,'kernel':[[.25]*4 for _ in range(4)],
       'contexts':[{'k':2,'step_index':0,'raw_by_state':[0,0,1,1],
                    'package_by_state':[0,1,0,1],'joint_by_state':[0,1,2,3],
                    'alphabet_raw_package':[[0,0],[0,1],[1,0],[1,1]]}],
       'recipes':[[a%4,(a+7)%4,(a+19)%4] for a in range(24)],
       'path_steps':64,'calibration_draws':256,'block_first':910001,'block_last':910035,'replicates':32,
       'seed_rule':'SHA256 UTF8 TestB/v4/{Y0cal|path}/(EXP::label,seed-or-block,recipe[,replicate]); first 8 bytes LE for calibration/start, bytes 8..16 LE for transition'}
    source=tmp_path/'headers';source.mkdir()
    suffix=hashlib.sha256(b'EXP-112::synthetic').hexdigest()[:8]
    path=source/f'EXP-112__synthetic__910000__{suffix}.audit.jsonl'
    path.write_bytes(C.encoded(h))
    return source,path,h


def test_header_inventory_excludes_old_paths_and_requires_complete_grid(tmp_path,headers):
    source,path,h=headers
    path.write_bytes(path.read_bytes()+b'{"type":"path","old":true}\n')
    with pytest.raises(ValueError,match='scale-32|140'):B.inventory(output=tmp_path/'full',headers=source,specifications=SPECS)
    B.inventory(output=tmp_path/'small',headers=source,specifications=SPECS,smoke=True)
    assert (tmp_path/'small/headers'/path.name).read_bytes()==C.encoded(h)
    (source/'duplicate.audit.jsonl').write_bytes(C.encoded(h))
    with pytest.raises(ValueError,match='duplicate'):B.inventory(output=tmp_path/'bad',headers=source,specifications=SPECS,smoke=True)


def test_wrong_kernel_seed_rejected_before_census(tmp_path,headers):
    source,path,h=headers;h['kernel_seed']=910001;path.write_bytes(C.encoded(h))
    with pytest.raises(ValueError,match='seed-910000'):B.inventory(output=tmp_path/'out',headers=source,specifications=SPECS,smoke=True)


def test_sample_resume_and_serial_parallel_bytes(tmp_path,headers):
    if not SAMPLER.is_file():pytest.skip('build the public sampler with make rust-test-b')
    source,path,h=headers
    second=json.loads(C.encoded(h));second['config']='second'
    suffix=hashlib.sha256(b'EXP-112::second').hexdigest()[:8]
    (source/f'EXP-112__second__910000__{suffix}.audit.jsonl').write_bytes(C.encoded(second))
    one=tmp_path/'one';two=tmp_path/'two'
    for root,workers in [(one,1),(two,2)]:
        result=B.run_test_b(output=root,headers=source,specifications=SPECS,stage='sample',smoke=True,workers=workers,sampler=SAMPLER)
        assert result['locked_test_sampled_or_opened'] is False
        loader=R.P5RecordLoader(root);entry=loader.loader.manifest['allowed_files'][0]
        data=loader.load(root/'record_view'/entry['file'])
        assert data.context.endswith('::h1')
        assert set(data.blocks)==set(range(910001,910016))
        assert set(data.recipes)==set(range(48))
        for name in ('audit.audit.jsonl','locked_910036.record.jsonl'):
            bad=root/name;bad.write_text('{}')
            with pytest.raises(PermissionError):loader.load(bad)
    for folder in ('record_side','audit_side','record_view'):
        a={p.name:p.read_bytes() for p in (one/folder).iterdir() if p.is_file()}
        b={p.name:p.read_bytes() for p in (two/folder).iterdir() if p.is_file()}
        assert a==b
    marker=list((one/'sampling').glob('*/result.json'))[0];before=marker.read_bytes()
    result=B.run_test_b(output=one,headers=source,specifications=SPECS,stage='sample',smoke=True,workers=3,sampler=SAMPLER)
    assert marker.read_bytes()==before
    assert len(list(marker.parent.glob('attempts/*')))==1
    assert result['results']['sample']['eligible_contexts']==2


def test_partial_sampler_attempt_is_redone_and_preserved(tmp_path,headers):
    if not SAMPLER.is_file():pytest.skip('build the public sampler with make rust-test-b')
    source,_,_=headers;root=tmp_path/'out'
    partial=root/'sampling/EXP-112_synthetic/attempts/attempt_0001/sidecars'
    partial.mkdir(parents=True);(partial/'broken.record.jsonl').write_text('{')
    B.run_test_b(output=root,headers=source,specifications=SPECS,stage='sample',smoke=True,workers=2,sampler=SAMPLER)
    assert (partial/'broken.record.jsonl').read_text()=='{'
    assert len(list(partial.parent.parent.glob('attempt_*')))==2
    assert len(E.RecordAllowlist(root/'record_view/manifest.json').allowed)==1


def test_register_sample_requires_certification_before_sampler(tmp_path,headers,monkeypatch):
    source,_,_=headers;root=tmp_path/'out';root.mkdir()
    B.inventory(output=root,headers=source,specifications=SPECS,smoke=True)
    B.census_stage(root,workers=1,smoke=True)
    called=[];monkeypatch.setattr(B.subprocess,'run',lambda *a,**k:called.append(a))
    with pytest.raises(FileNotFoundError):B.sample_stage(root,specifications=SPECS,workers=1,sampler=SAMPLER,smoke=False,only=[])
    assert not called and not (root/'record_side').exists()


def test_census_change_rejected_on_resume(tmp_path,headers):
    source,_,_=headers;root=tmp_path/'out'
    B.inventory(output=root,headers=source,specifications=SPECS,smoke=True)
    B.census_stage(root,workers=1,smoke=True)
    (root/'census/training_census.jsonl').write_text('{}\n')
    with pytest.raises(ValueError,match='census data changed'):B.census_stage(root,workers=1,smoke=True)


def test_runtime_mismatch_rejected_after_scientific_imports(headers):
    from born_ladder.reproduction.test_b_runtime import check_runtime
    profile=json.loads((SPECS/'environments/test_b_fitting.json').read_bytes())
    profile['versions']['numpy']='0.0.0'
    with pytest.raises(ValueError,match='numpy='):check_runtime(profile)


def test_fit_partial_directory_recovery_and_worker_forwarding(tmp_path,headers,monkeypatch):
    root=tmp_path/'out';root.mkdir();runtime=B.science(SPECS)[3]
    B._json(root/'setup.json',{'runtime':runtime})
    partial=root/'fits/original/unit_r2';partial.mkdir(parents=True);(partial/'models.json').write_text('{')
    called=[];monkeypatch.setattr(R,'fit',lambda root,workers:called.append((root,workers)) or {'summary':{'status':'mock'}})
    B.fit_stage(root,specifications=SPECS,workers=7)
    assert not partial.exists() and (root/'incomplete/fits/original/unit_r2/models.json').read_text()=='{'
    assert called==[(root,7)]
    setup=json.loads((root/'setup.json').read_bytes());setup['runtime']['numpy']='wrong';(root/'setup.json').write_bytes(C.encoded(setup))
    with pytest.raises(ValueError,match='numerical resume'):B.fit_stage(root,specifications=SPECS,workers=1)


def test_cli_stage_and_workers_forwarded(monkeypatch,tmp_path):
    from born_ladder.__main__ import main
    from born_ladder.reproduction import stage_environment
    monkeypatch.setattr(stage_environment,'ensure_environment',lambda *a:None)
    called=[];monkeypatch.setattr(B,'run_test_b',lambda **k:called.append(k) or {'ok':True})
    assert main(['reproduce','test-b','--stage','sample','--headers',str(tmp_path),'--output',str(tmp_path/'out'),'--workers','9'])==0
    assert called[0]['stage']=='sample' and called[0]['workers']==9


def test_p5_coordinator_has_no_locked_test_option():
    text=(REPO/'vendor/pica/crates/test_b_sampler/src/main.rs').read_text()
    assert 'sample_trainval_header' in text and 'requires = "predictions_root"' in text
    text=Path(B.__file__).read_text()
    assert 'fresh_v6' not in text and 'manager_approval' not in text


def test_spec_budget_drift_is_refused(tmp_path,headers):
    specs=tmp_path/'specifications';specs.mkdir()
    contract=json.loads((SPECS/'test_b.json').read_bytes());contract['fit']['starts']=95
    (specs/'test_b.json').write_text(json.dumps(contract))
    with pytest.raises(ValueError,match='fit budgets'):B.science(specs)


def test_fake_certification_pass_cannot_admit_real_samples(tmp_path,headers):
    source,_,_=headers;root=tmp_path/'out'
    B.inventory(output=root,headers=source,specifications=SPECS,smoke=True)
    B.census_stage(root,workers=1,smoke=True)
    B._json(root/'certification/complete.json',{'status':'PASS','smoke_nonconfirmatory':False})
    with pytest.raises(FileNotFoundError):B.validate_certification(root)


def test_kernel_grid_filter_accounts_for_unrelated_captures(tmp_path,headers,monkeypatch):
    from born_ladder.reproduction import runs
    source,path,h=headers
    capture=tmp_path/'runs';directory=capture/'invocations/header';directory.mkdir(parents=True)
    file=directory/path.name;file.write_bytes(path.read_bytes())
    valid=runs.Invocation('EXP-112','synthetic',910000,32)
    for job in (valid,runs.Invocation('EXP-112','synthetic',840007,32)):
        runs.Manifest(capture).append({'event':'finished','status':'completed','invocation_id':job.id,
            'attempt':1,'directory':'invocations/header','artifacts':[{'path':str(file.relative_to(capture)),
                'bytes':file.stat().st_size,'sha256':runs.digest(file)}]})
    monkeypatch.setattr(runs.RunSpecifications,'grid',lambda *a:[valid])
    # Use a directory component named headers, matching P2a's artifact schema.
    nested=directory/'headers';nested.mkdir();file.rename(nested/file.name)
    rows=runs.Manifest(capture).rows
    for row in rows:row['artifacts'][0]['path']=str((nested/path.name).relative_to(capture))
    (capture/'manifest.jsonl').write_bytes(b''.join(runs.encoded(r) for r in rows))
    result=B.inventory(output=tmp_path/'out',runs=capture,specifications=SPECS,smoke=True)
    assert len(result)==1
    accounting=json.loads((tmp_path/'out/capture_dispositions.json').read_bytes())
    assert len(accounting['excluded_invocations'])==1 and '840007' in accounting['excluded_invocations'][0]['invocation_id']


def test_unfinished_certification_rows_and_documents_recover(tmp_path):
    root=tmp_path/'out';target=root/'certification/fidelity';target.mkdir(parents=True)
    good=b'{"index":0}\n';tail=b'{"index":1,'
    (target/'results.jsonl').write_bytes(good+tail)
    (target/'verdict.json').write_bytes(b'{')
    B.recover_unfinished_checkpoints(root/'certification',root)
    assert (target/'results.jsonl').read_bytes()==good
    assert not (target/'verdict.json').exists()
    assert (root/'incomplete/certification/fidelity/results.jsonl.tail').read_bytes()==tail
    assert (root/'incomplete/certification/fidelity/verdict.json').read_bytes()==b'{'


def test_numerical_phase_start_needs_no_source_receipt(tmp_path,headers):
    B._json(tmp_path/'setup.json',{'spec_sha256':R.SPEC_HASH})
    assert R.phase_start(tmp_path,'gates')=={'spec_sha256':R.SPEC_HASH}


def test_smoke_control_named_losses_are_contrasts():
    from born_ladder.reproduction.test_b_smoke_controls import expected_contrasts
    losses={'square':.1,'selected_classical':.2,'diagonal':.3,'ed2':.05,'selected_order':.4}
    got=expected_contrasts(losses,2)
    assert got=={'D':.2-.1,'G':.3-.1,'R':.1-.05,'O':.4-.1}


def test_commit_schema_resume_and_completed_data_integrity(tmp_path,headers,monkeypatch):
    if not SAMPLER.is_file():pytest.skip('build the public sampler with make rust-test-b')
    source,_,_=headers;root=tmp_path/'out'
    B.run_test_b(output=root,headers=source,specifications=SPECS,stage='sample',smoke=True,workers=1,sampler=SAMPLER)
    # This fixture exercises publication/control routing, not an empirical fit.
    R.commit_phase(root,'fit',[],{'status':'SYNTHETIC_TEST_STUB'})
    calls=[]
    def relabel(root,entries,workers):
        calls.append(('relabel',len(entries),workers));B._json(root/'controls/relabel.json',{'fixture':True})
        return {'actual_full_refits':22*len(entries)}
    def audit(root,entries,workers):
        calls.append(('audit',len(entries),workers));B._json(root/'controls/training_audit_1000.json',{'fixture':True})
        return {'campaigns':1000,'descriptive':True}
    monkeypatch.setattr(R,'literal_relabel_refits',relabel);monkeypatch.setattr(R,'training_audit',audit)
    result=B.commit_stage(root,specifications=SPECS,workers=5)
    assert result['subset_nonconfirmatory'] and result['mandatory_order_completed'] is None
    assert result['locked_test_sampled_or_opened'] is False and result['structural_erasure']=='NOT_COMPUTED'
    assert result['rank_context_counts']=={'2':1,'3':1,'4':0}
    assert calls==[('relabel',2,5),('audit',2,5)]
    before=(root/'prediction_seal_manifest.json').read_bytes()
    assert B.commit_stage(root,specifications=SPECS,workers=7)==result
    assert (root/'prediction_seal_manifest.json').read_bytes()==before and len(calls)==2
    (root/'controls/relabel.json').write_text('{}')
    with pytest.raises(RuntimeError,match='artifact differs'):B.commit_stage(root,specifications=SPECS,workers=1)
