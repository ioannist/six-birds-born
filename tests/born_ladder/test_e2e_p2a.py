"""Named, small P2a launcher checks; scientific comparisons are opt-in data nodes."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest
from born_ladder.reproduction.runs import (
    Manifest, RunSpecifications, exclusive_output, run_grid, validate_output,
)

REPO = Path(__file__).resolve().parents[2]
SPECS = REPO/'specifications'


@pytest.fixture
def fake_runner(tmp_path):
    path = tmp_path/'runner'
    path.write_text('#!'+sys.executable+'\n'+f'SPEC_ROOT={str(SPECS)!r}\n'+'''import json,os,sys,time
from pathlib import Path
args=sys.argv[1:]
if args==['--list-configs','EXP-112']:
    print('\\n'.join(json.loads((Path(SPEC_ROOT)/'predictive_v8.json').read_text())['grid']['labels']))
    sys.exit(0)
def value(flag,default=None):return args[args.index(flag)+1] if flag in args else default
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','RAYON_NUM_THREADS'):
    assert os.environ[name]=='1'
config=value('--config','internal')
print('KEY_100_DYN cell='+config,flush=True)
time.sleep(float(os.environ.get('RUN_TEST_DELAY','0')))
if os.environ.get('RUN_TEST_FAIL_ONCE') and not Path('failed-once').exists():
    Path('failed-once').write_text('test launch failure')
    print('synthetic failure',file=sys.stderr);sys.exit(7)
header=Path(value('--test-b-sidecar-dir'));header.mkdir(parents=True)
(header/'synthetic.audit.jsonl').write_text(json.dumps({'config':config,'kernel':[[1.0,0.0],[0.0,1.0]]})+'\\n')
print('RB1_STRUCTURAL_END_JSON:{}',flush=True)
''')
    path.chmod(0o755)
    return path


def launch(output, runner, **kwargs):
    return run_grid(grid='worked-cases',output=output,runner=runner,specifications=SPECS,**kwargs)


def test_registered_grid_identity_and_diagnostic_subsets():
    specs=RunSpecifications(SPECS)
    assert {name:len(specs.grid(name)) for name in specs.document['grids']} == {
        'g2a':1380,'g2c':1500,'test-b':75,'worked-cases':2,'smoke':3,'e2e-smoke':3,'benchmark':32}
    assert {j.seed for j in specs.grid('g2a')}==set(range(810001,810021))
    assert {j.seed for j in specs.grid('g2c')}==set(range(840001,840021))
    assert {j.seed for j in specs.grid('test-b')}=={910000}
    assert all(j.scale==32 for name in specs.document['grids'] for j in specs.grid(name))
    assert [j.id for j in specs.grid('worked-cases')]==[
        'EXP-112__A13_A11__s840007__n32','EXP-112__loo_A25__s910000__n32']
    assert set(specs.grid('benchmark')) <= set(specs.grid('test-b'))
    assert len([j for j in specs.grid('benchmark') if j.configuration is None])==6


def test_required_output_is_outside_version_control(tmp_path):
    for target in (REPO,REPO/'src/generated',REPO/'docs/generated'):
        with pytest.raises(ValueError,match='Git'):
            validate_output(target,REPO)
    assert validate_output(REPO/'scratch/e2e/p2a/test-output',REPO).is_relative_to(REPO/'scratch')


def test_output_git_discovery_controls_locale_for_both_probes(tmp_path,monkeypatch):
    from born_ladder.reproduction import runs
    monkeypatch.setenv('LC_ALL','fr_FR.UTF-8')
    monkeypatch.setenv('LANGUAGE','fr')
    monkeypatch.setenv('BORN_GIT_ENV_TEST','inherited')
    calls=[]
    def discover(argv,**kwargs):
        assert argv[-2:]==['rev-parse','--show-toplevel']
        assert kwargs['capture_output'] and kwargs['text']
        env=kwargs['env']
        assert env['LC_ALL']==env['LANGUAGE']=='C'
        assert env['BORN_GIT_ENV_TEST']=='inherited'
        calls.append(argv)
        return subprocess.CompletedProcess(argv,128,'',
            'fatal: not a git repository (or any of the parent directories): .git\n')
    monkeypatch.setattr(runs.subprocess,'run',discover)
    output=tmp_path/'external-output'
    assert validate_output(output,tmp_path)==output.resolve()
    assert len(calls)==2
    assert os.environ['LC_ALL']=='fr_FR.UTF-8' and os.environ['LANGUAGE']=='fr'


@pytest.mark.parametrize('failed_probe',[0,1])
@pytest.mark.parametrize('returncode,diagnostic',[
    (128,"fatal: detected dubious ownership in repository at '/not a git repository/data'\n"),
    (128,'fatal: unrecognized Git discovery failure\n'),
    (1,'fatal: not a git repository (or any of the parent directories): .git\n'),
])
def test_output_rejects_other_git_failures(tmp_path,monkeypatch,failed_probe,returncode,diagnostic):
    from born_ladder.reproduction import runs
    calls=[]
    def discover(argv,**kwargs):
        calls.append(argv)
        if len(calls)-1==failed_probe:
            return subprocess.CompletedProcess(argv,returncode,'',diagnostic)
        return subprocess.CompletedProcess(argv,128,'',
            'fatal: not a git repository (or any of the parent directories): .git\n')
    monkeypatch.setattr(runs.subprocess,'run',discover)
    with pytest.raises(ValueError,match='cannot establish '+('output' if failed_probe==0 else 'caller')+' Git worktree'):
        validate_output(tmp_path/'external-output',tmp_path)
    assert len(calls)==failed_probe+1


def test_smoke_certification_accepts_output_outside_any_git_repository(tmp_path,monkeypatch):
    from born_ladder.reproduction import test_b_smoke
    # Keep test artifacts in the configured pytest scratch directory while
    # imposing the same Git-discovery boundary as an external storage volume.
    monkeypatch.setenv('GIT_CEILING_DIRECTORIES',str(tmp_path.parent))
    assert subprocess.run(['git','-C',str(tmp_path),'rev-parse','--show-toplevel'],
                          capture_output=True).returncode != 0
    root=tmp_path/'external/test-b'
    specs=root/'smoke_specifications';specs.mkdir(parents=True)
    output=root/'certification'
    def reached_science(specifications):
        assert output.is_dir()
        assert specifications==specs
        raise RuntimeError('external output accepted before scientific computation')
    monkeypatch.setattr(test_b_smoke,'science',reached_science)
    with pytest.raises(RuntimeError,match='external output accepted'):
        test_b_smoke.smoke_certification(census=root/'census/eligibility.json',
            output=output,specifications=specs)
    assert validate_output(output,root)==output.resolve()
    # Git-discovery limits must not bypass a known checkout's source protection.
    monkeypatch.setenv('GIT_CEILING_DIRECTORIES',str(REPO))
    with pytest.raises(ValueError,match='Git-ignored'):
        validate_output(REPO/'src/unignored-output',REPO)


def test_resume_checks_artifacts_and_preserves_manifest(tmp_path,fake_runner):
    out=tmp_path/'resume'
    first=launch(out,fake_runner,workers=2)
    assert first['completed']==2 and first['resource_accounting_complete']
    original=(out/'manifest.jsonl').read_bytes()
    rows=Manifest(out).completed()
    assert len(rows)==2
    assert all(not Path(p['path']).is_absolute() for row in rows.values() for p in row['artifacts'])
    assert all(not Path(row['argv'][0]).is_absolute() for row in rows.values())
    second=launch(out,fake_runner,workers=1)
    assert second['launched']==0 and second['skipped_completed']==2
    assert (out/'manifest.jsonl').read_bytes()==original
    victim=out/next(iter(rows.values()))['artifacts'][0]['path']
    victim.write_text('corrupted')
    with pytest.raises(ValueError,match='artifact changed'):
        launch(out,fake_runner)


def test_failed_attempt_is_recorded_and_retry_is_new(tmp_path,fake_runner,monkeypatch):
    monkeypatch.setenv('RUN_TEST_FAIL_ONCE','1')
    out=tmp_path/'retry'
    identifier=RunSpecifications(SPECS).grid('worked-cases')[0].id
    first=launch(out,fake_runner,only=[identifier])
    assert first['failed']==1
    before=(out/'manifest.jsonl').read_bytes()
    second=launch(out,fake_runner,only=[identifier])
    assert second['completed']==1
    assert (out/'manifest.jsonl').read_bytes().startswith(before)
    rows=Manifest(out).rows
    assert [(r['attempt'],r['status'],r['exit_code']) for r in rows if r['event']=='finished']==[
        (1,'failed',7),(2,'completed',0)]
    failed=next(r for r in rows if r.get('status')=='failed')
    cell=failed['exports']['configurations'][0]
    assert cell['legacy_export_status']=='incomplete'
    assert 'failed' in cell['export_status_reason'] and cell['suppression_note'] is None
    assert all((out/r['directory']).exists() for r in rows)


def test_export_suppressions_are_explicit(tmp_path,fake_runner):
    # Successful completion AND an observed early-return guard establish a
    # suppression. A missing header alone does not establish it.
    fake_runner.write_text(fake_runner.read_text().split("config=value")[0]+'''
print("KEY_100_DYN cell=empty")
print("KEY_100_MACRO seed=840007 scale=32 cell=empty level=L0 macro_n=1 frob=0.0")
''')
    out=tmp_path/'suppression'
    result=launch(out,fake_runner,only=[RunSpecifications(SPECS).grid('worked-cases')[0].id])
    assert result['completed']==1
    row=next(iter(Manifest(out).completed().values()))
    cell=row['exports']['configurations'][0]
    assert cell['legacy_export_status']=='suppressed'
    assert not cell['header'] and not cell['paths']
    assert cell['suppression_note']
    assert cell['guard_evidence'][0]['macro_n']==1
    assert cell['guard_evidence'][0]['line']==2
    assert 'successful invocation' in cell['export_status_reason']


@pytest.mark.parametrize('other_record', ['',
    'KEY_100_MACRO seed=840007 scale=32 cell=empty level=L0 macro_n=2 frob=0.0',
    'KEY_100_MACRO seed=840007 scale=32 cell=other level=L0 macro_n=1 frob=0.0'])
def test_completed_missing_export_without_matching_guard_is_unknown(tmp_path,fake_runner,other_record):
    fake_runner.write_text(fake_runner.read_text().split("config=value")[0]+
                          'print("KEY_100_DYN cell=empty")\n'+f'print({other_record!r})\n')
    out=tmp_path/'unknown-export'
    result=launch(out,fake_runner,only=[RunSpecifications(SPECS).grid('worked-cases')[0].id])
    assert result['completed']==1
    row=next(iter(Manifest(out).completed().values()))
    cell=next(c for c in row['exports']['configurations'] if c['configuration']=='empty')
    assert cell['legacy_export_status']=='unknown'
    assert 'no runner guard evidence' in cell['export_status_reason']
    assert cell['guard_evidence']==[] and cell['suppression_note'] is None


def test_concurrent_coordinators_and_changed_contract_are_rejected(tmp_path,fake_runner):
    out=tmp_path/'contract'
    with exclusive_output(out):
        with pytest.raises(ValueError,match='owns this output'):
            launch(out,fake_runner)
    launch(out,fake_runner)
    with pytest.raises(ValueError,match='different grid'):
        launch(out,fake_runner,capture=False)


def test_timeout_attempt_is_kept(tmp_path,fake_runner,monkeypatch):
    monkeypatch.setenv('RUN_TEST_DELAY','2')
    out=tmp_path/'timeout'
    identifier=RunSpecifications(SPECS).grid('worked-cases')[0].id
    result=launch(out,fake_runner,only=[identifier],timeout=.1)
    assert result['failed']==1
    finished=[r for r in Manifest(out).rows if r['event']=='finished']
    assert finished[0]['status']=='timeout'
    assert finished[0]['artifacts']
    cell=finished[0]['exports']['configurations'][0]
    assert cell['legacy_export_status']=='incomplete'
    assert 'timeout' in cell['export_status_reason'] and cell['suppression_note'] is None


def test_unrecorded_directory_and_dangling_start_resume(tmp_path,fake_runner):
    out=tmp_path/'orphan'
    jobs=RunSpecifications(SPECS).grid('worked-cases')
    unrecorded=out/'invocations'/jobs[0].id/'attempt_0001'
    unrecorded.mkdir(parents=True)
    (unrecorded/'partial.txt').write_text('unfinished I/O, not a scientific result')
    manifest=Manifest(out)
    manifest.append({'event':'started','invocation_id':jobs[1].id,'attempt':1,
                     'directory':str(Path('invocations')/jobs[1].id/'attempt_0001'),'argv':[]})
    original=(out/'manifest.jsonl').read_bytes()
    result=launch(out,fake_runner,workers=2)
    assert result['completed']==2
    assert (out/'manifest.jsonl').read_bytes().startswith(original)
    assert (unrecorded/'partial.txt').read_text().startswith('unfinished I/O')
    rows=Manifest(out).rows
    abandoned=[r for r in rows if r['event']=='abandoned']
    assert {r['status'] for r in abandoned}=={'unrecorded_attempt_directory','interrupted_coordinator'}
    assert all(r['exit_code'] is None and r['cpu_user_seconds'] is None for r in abandoned)
    assert {r['attempt'] for r in rows if r['event']=='finished'}=={2}


def test_inventory_mismatch_prevents_launch(tmp_path,fake_runner):
    fake_runner.write_text('#!'+sys.executable+'\nprint("not-the-registered-inventory")\n')
    out=tmp_path/'wrong-inventory'
    with pytest.raises(ValueError,match='inventory differs'):
        launch(out,fake_runner)
    assert not out.exists()


def test_sigterm_resumes_without_overwriting_attempt(tmp_path,fake_runner):
    out=tmp_path/'signal'
    identifier=RunSpecifications(SPECS).grid('worked-cases')[0].id
    cmd=[sys.executable,'-m','born_ladder','reproduce','runs','--grid','worked-cases',
         '--output',str(out),'--specifications',str(SPECS),'--runner',str(fake_runner),'--only',identifier]
    env={**os.environ,'RUN_TEST_DELAY':'10'}
    with (tmp_path/'interrupt.log').open('w') as log:
        process=subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+10
            stdout=out/'invocations'/identifier/'attempt_0001'/'stdout.bin'
            while not stdout.exists() or b'KEY_100_DYN' not in stdout.read_bytes():
                assert process.poll() is None and time.monotonic()<deadline
                time.sleep(.02)
            process.send_signal(signal.SIGTERM)
            assert process.wait(timeout=10)==1
        finally:
            if process.poll() is None:process.kill();process.wait()
    rows=Manifest(out).rows
    assert rows[-1]['event']=='finished' and rows[-1]['status']=='interrupted'
    cell=rows[-1]['exports']['configurations'][0]
    assert cell['legacy_export_status']=='incomplete'
    assert 'interrupted' in cell['export_status_reason'] and cell['suppression_note'] is None
    original=(out/'manifest.jsonl').read_bytes()
    result=launch(out,fake_runner,only=[identifier])
    assert result['completed']==1
    assert (out/'manifest.jsonl').read_bytes().startswith(original)
    assert Manifest(out).rows[-1]['attempt']==2


def test_capture_module_has_no_rng_or_sampling_calls():
    text=(REPO/'vendor/pica/crates/runner/src/full_capture.rs').read_text()
    assert 'use rand' not in text and '.sample' not in text and 'sample_trajectory(' not in text
    assert 'sampled_paths: &[Vec<usize>]' in text
    source=(REPO/'vendor/pica/crates/runner/src/main.rs').read_text()
    assert source.index('full_capture::paths') > source.index('let sampled_trajs: Vec<Vec<usize>> = starts')


def test_p1_data_nodes_skip_absent_prerequisites(tmp_path):
    # Set an existing bundle to pass the general data gate, then leave each
    # additional prerequisite absent. No scientific test body should execute.
    bundle=tmp_path/'bundle.json';bundle.write_text('{}')
    env={**os.environ,'BORN_LADDER_DATA':str(bundle)}
    for name in ('E2E_P1_COHORT_OUTPUT','E2E_P1_HISTORICAL_ROOT'):
        env.pop(name,None)
    env['PYTEST_ADDOPTS']='-o cache_dir='+str(tmp_path/'child-cache')+' --basetemp '+str(tmp_path/'child-tmp')
    nodes=['test_historical_loader_seed_and_full_fit','test_complete_cohort_reconstruction',
           'test_readable_values_equal_retained_original_specifications']
    script = ('import importlib.util,sys,pytest; original=importlib.util.find_spec; '
              'importlib.util.find_spec=lambda name,*a,**k: None if name in {"torch","scipy"} else original(name,*a,**k); '
              'sys.exit(pytest.main(sys.argv[1:]))')
    run=subprocess.run([sys.executable,'-c',script,'-q','-rs',
                        *(str(REPO/'tests/born_ladder/test_e2e_p1.py')+'::'+name for name in nodes)],
                       cwd=REPO,env=env,capture_output=True,text=True)
    # Explicitly simulate an absent fitting extra even on a fitting-enabled host.
    assert run.returncode==0,run.stdout+run.stderr
    assert 'E2E_P1_COHORT_OUTPUT' in run.stdout and 'E2E_P1_HISTORICAL_ROOT' in run.stdout
    assert '3 skipped' in run.stdout and 'fitting extra required' in run.stdout
