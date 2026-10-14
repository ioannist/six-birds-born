"""Pristine-install regressions: routing, prebuilt Lean cache and spawned fits."""
import json
import os
from pathlib import Path
import subprocess

import pytest

from born_ladder.reproduction.stage_environment import environment_root

ROOT=Path(__file__).resolve().parents[2]


def test_stage_cache_honors_xdg_and_explicit_override(monkeypatch,tmp_path):
    monkeypatch.delenv('BORN_LADDER_ENV_ROOT',raising=False)
    monkeypatch.delenv('XDG_CACHE_HOME',raising=False)
    assert environment_root()==Path.home()/'.cache/born-ladder/environments'
    monkeypatch.setenv('XDG_CACHE_HOME',str(tmp_path/'xdg'))
    assert environment_root()==tmp_path/'xdg/born-ladder/environments'
    monkeypatch.setenv('BORN_LADDER_ENV_ROOT',str(tmp_path/'explicit'))
    assert environment_root()==tmp_path/'explicit'
    monkeypatch.setenv('BORN_LADDER_ENV_ROOT','')
    with pytest.raises(ValueError,match='must be nonempty'):
        environment_root()


@pytest.mark.parametrize('cache_result',[0,1])
def test_make_lean_fetches_cache_then_builds_with_fallback(tmp_path,cache_result):
    project=tmp_path/'lean';project.mkdir();binary=tmp_path/'bin';binary.mkdir()
    log=tmp_path/'calls'
    lake=binary/'lake';lake.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_LAKE_LOG"\nif [ "$1" = exe ]; then exit "$TEST_CACHE_RESULT"; fi\n')
    lake.chmod(0o755)
    env={**os.environ,'PATH':str(binary)+os.pathsep+os.environ['PATH'],
         'TEST_LAKE_LOG':str(log),'TEST_CACHE_RESULT':str(cache_result)}
    r=subprocess.run(['make','lean','LEAN_ROOT='+str(project)],cwd=ROOT,env=env,capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    assert log.read_text().splitlines()==['exe cache get','build']
    if cache_result:assert 'falling back to a source build' in r.stdout
    log.unlink()
    r=subprocess.run(['make','lean','LEAN_ROOT='+str(project),'LEAN_CACHE=0'],cwd=ROOT,env=env,capture_output=True,text=True)
    assert r.returncode==0 and log.read_text().splitlines()==['build']


def test_fitting_lock_is_cpu_only_and_hash_locked():
    lock=(ROOT/'specifications/environments/test_b_fitting.lock').read_text()
    assert lock==(ROOT/'requirements-fitting.lock').read_text()
    assert '--extra-index-url https://download.pytorch.org/whl/cpu' in lock
    assert 'torch==2.13.0+cpu --hash=sha256:' in lock
    lines=[line for line in lock.splitlines() if line and not line.startswith(('#','--'))]
    assert all(' --hash=sha256:' in line for line in lines)
    assert not any(word in lock.lower() for word in ('nvidia','triton','cu130','cuda-'))
    profile=json.loads((ROOT/'specifications/environments/test_b_fitting.json').read_bytes())
    assert profile['torch_build']=='2.13.0+cpu'


def test_fitting_pool_spawns_and_preserves_settings(tmp_path,monkeypatch):
    pytest.importorskip('torch');pytest.importorskip('scipy')
    from born_ladder.record_tests import workers as W, estimators as E, cert_v6 as C
    from born_ladder.reproduction import test_b_runtime as T
    monkeypatch.setattr(C,'ROOT',tmp_path)
    monkeypatch.setattr(C,'CENSUS',None)
    monkeypatch.setattr(E,'V5_STARTS',2)
    monkeypatch.setattr(E,'V5_WARM_ITER',2)
    monkeypatch.setattr(E,'V5_POLISH_ITER',4)
    monkeypatch.setattr(E,'CHECKPOINTS',(2,4))
    # Register restorations for the function defaults before exercising init.
    for name in ('fit_model','fit_family','fit_diagonal'):
        monkeypatch.setattr(getattr(E,name),'__defaults__',getattr(E,name).__defaults__)
    captured={}
    monkeypatch.setattr(W,'ProcessPoolExecutor',lambda **kw:captured.update(kw) or captured)
    W.process_pool(max_workers=4)
    assert captured['mp_context'].get_start_method()=='spawn'
    settings,initializer,initargs=captured['initargs']
    assert settings['fit']['V5_STARTS']==2 and settings['fit']['CHECKPOINTS']==(2,4)
    calls=[];monkeypatch.setattr(T,'check_runtime',lambda p:calls.append('checked'))
    W.initialize(settings,lambda x:calls.append(x),('caller initializer',))
    assert calls==['checked','caller initializer'] and E.V5_POLISH_ITER==4
    assert all(os.environ[name]=='1' for name in settings['profile']['thread_environment'])


def test_estimators_do_not_resize_a_loaded_torch_pool():
    import ast
    tree=ast.parse((ROOT/'src/born_ladder/record_tests/estimators.py').read_text())
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
                   and n.func.attr=='set_num_threads' for n in ast.walk(tree))


_FITTING_BARRIER=None


def initialize_worker_check(barrier):
    global _FITTING_BARRIER
    _FITTING_BARRIER=barrier


def fitting_worker_observation(index):
    if _FITTING_BARRIER is not None:
        _FITTING_BARRIER.wait(timeout=90)
    import torch
    from born_ladder.record_tests import estimators as E,cert_v6 as C
    x=torch.tensor([[1.,2.],[3.,4.]],dtype=torch.float64,requires_grad=True)
    value=(x@x.T).square().sum();value.backward()
    return {'index':index,'pid':os.getpid(),'threads':torch.get_num_threads(),
            'cuda':torch.version.cuda,'starts':E.V5_STARTS,'checkpoints':list(E.CHECKPOINTS),
            'output':str(C.ROOT),'census':str(C.CENSUS),
            'loss':float(value.detach()),'gradient':x.grad.tolist()}


def test_actual_cpu_workers_are_fresh_checked_and_numerically_equal(tmp_path,monkeypatch):
    torch=pytest.importorskip('torch')
    if torch.__version__!='2.13.0+cpu':
        pytest.skip('run in the freshly provisioned CPU-only Test B environment')
    from born_ladder.record_tests import workers as W,estimators as E,cert_v6 as C
    census=tmp_path/'census.json';census.write_text('{}')
    monkeypatch.setattr(C,'ROOT',tmp_path)
    monkeypatch.setattr(C,'CENSUS',census)
    monkeypatch.setattr(E,'V5_STARTS',2)
    monkeypatch.setattr(E,'CHECKPOINTS',(2,4))
    # Initialize the parent's autograd pool before creating the worker pool:
    # the old fork setup would inherit precisely this unsafe native state.
    expected=fitting_worker_observation(0)
    import multiprocessing
    barrier=multiprocessing.get_context('spawn').Barrier(4)
    with W.process_pool(max_workers=4,initializer=initialize_worker_check,initargs=(barrier,)) as pool:
        rows=list(pool.map(fitting_worker_observation,range(8)))
    assert len({r['pid'] for r in rows})==4
    assert all(r['pid']!=os.getpid() for r in rows)
    for r in rows:
        assert {k:v for k,v in r.items() if k not in ('index','pid')}=={k:v for k,v in expected.items() if k not in ('index','pid')}
        assert r['threads']==1 and r['cuda'] is None and r['starts']==2
