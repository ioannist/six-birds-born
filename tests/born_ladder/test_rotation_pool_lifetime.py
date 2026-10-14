"""Small real spawn pools: clean worker heaps and creator-death cleanup."""
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from born_ladder.reproduction import rotation_admission as R


def _probe_worker(directory,parent_pid):
    # Exercise the production lifetime initializer, without a numerical profile.
    R.initialize=lambda specifications:None
    R._initialize_pool(directory,parent_pid)
    record={'pid':os.getpid(),'parent':os.getppid(),
            'inherited_heap':hasattr(R,'_probe_parent_heap')}
    (Path(directory)/f'worker_{os.getpid()}.json').write_text(json.dumps(record))


def _probe_rotation(task):
    source,control,detail=task
    time.sleep(source.get('delay',0))
    return source['kind_cell_id'],R.fingerprint('probe',source,control,detail),{'checked':True}


def _run_pool(directory,delay):
    R._initialize_pool=_probe_worker
    R.reconstruct=_probe_rotation
    # This sentinel exists only in the creator, and would be inherited by fork.
    R._probe_parent_heap=bytearray(8*1024*1024)
    sources=[{'kind_cell_id':str(i),'delay':delay} for i in range(32)]
    controls=[{'kind_cell_id':str(i)} for i in range(32)]
    details={str(i):{'gap':0.125} for i in range(32)}
    checked=R.parallel_rotations(directory,sources,controls,details,2)
    for source,control in zip(sources,controls):
        assert checked(SimpleNamespace(scientific_rng_identity='probe'),source,control,
                       details[source['kind_cell_id']])=={'checked':True}


def _kill_probe(directory,signum):
    # A separate test supervisor adopts and reaps grandchildren, avoiding PID 1
    # zombies even if the regression fails. Do not change pytest's own process.
    libc=ctypes.CDLL(None,use_errno=True)
    assert libc.prctl(36,1,0,0,0)==0  # PR_SET_CHILD_SUBREAPER
    module_dir=str(Path(__file__).parent)
    code=f'import sys; sys.path.insert(0,{module_dir!r}); import test_rotation_pool_lifetime as T; T._run_pool({directory!r},30)'
    parent=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    workers=set()
    try:
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            files=list(Path(directory).glob('worker_*.json'))
            if len(files)==2:break
            if parent.poll() is not None:raise AssertionError('pool creator exited before workers started')
            time.sleep(.05)
        assert len(files)==2,'two pool workers did not start'
        records=[json.loads(p.read_text()) for p in files]
        workers={r['pid'] for r in records}
        assert all(r['parent']==parent.pid and not r['inherited_heap'] for r in records)
        parent.send_signal(signum);parent.wait(timeout=5)
        assert parent.returncode==-signum
        exited={};deadline=time.monotonic()+8
        while workers and time.monotonic()<deadline:
            for pid in list(workers):
                done,status=os.waitpid(pid,os.WNOHANG)
                if done:
                    exited[pid]=os.waitstatus_to_exitcode(status);workers.remove(pid)
            if workers:time.sleep(.05)
        assert not workers,'rotation workers outlived their killed creator'
        assert set(exited.values())=={-signal.SIGKILL}
        return {'workers':len(exited),'exit_codes':list(exited.values())}
    finally:
        if parent.poll() is None:parent.kill()
        parent.wait(timeout=5)
        for p in Path(directory).glob('worker_*.json'):
            pid=json.loads(p.read_text())['pid']
            try:
                done,_=os.waitpid(pid,os.WNOHANG)
                if not done:
                    os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
            except ChildProcessError:pass
        # The spawn resource tracker exits when its worker/creator pipes close.
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            try:
                done,_=os.waitpid(-1,os.WNOHANG)
                if not done:time.sleep(.05)
            except ChildProcessError:break


def _subprocess_code(expression):
    return f'import sys; sys.path.insert(0,{str(Path(__file__).parent)!r}); import test_rotation_pool_lifetime as T; {expression}'


@pytest.mark.skipif(sys.platform!='linux',reason='production pool lifetime uses Linux prctl')
@pytest.mark.parametrize('signum',[signal.SIGTERM,signal.SIGKILL])
def test_rotation_workers_exit_when_creator_is_killed(tmp_path,signum):
    code=_subprocess_code(f'print(T.json.dumps(T._kill_probe({str(tmp_path)!r},{signum})))')
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=35)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)=={'workers':2,'exit_codes':[-signal.SIGKILL]*2}


def test_spawn_pool_does_not_inherit_parent_heap(tmp_path):
    result=subprocess.run([sys.executable,'-c',_subprocess_code(f'T._run_pool({str(tmp_path)!r},0)')],
                          capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    workers=[json.loads(p.read_text()) for p in tmp_path.glob('worker_*.json')]
    assert len(workers)==2 and all(not r['inherited_heap'] for r in workers)


def test_parent_death_before_initializer_exits_instead_of_becoming_orphan():
    result=subprocess.run([sys.executable,'-c',
        'from born_ladder.reproduction.rotation_admission import _bind_parent_lifetime; '
        '_bind_parent_lifetime(-1); raise AssertionError("must exit before initialization")'],
        capture_output=True,text=True,timeout=10)
    assert result.returncode==1 and not result.stderr
