"""Location-dependent interpreters, repair and immutable published environments."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

import pytest

from born_ladder.reproduction import stage_environment as E


@pytest.fixture
def managed(tmp_path,monkeypatch):
    specs=tmp_path/'specifications/environments';specs.mkdir(parents=True)
    lock=specs/'verification.lock';lock.write_text('')
    profile=specs/'verification.json'
    profile.write_text(json.dumps({'profile':'verification','lock':lock.name,
        'lock_sha256':hashlib.sha256(lock.read_bytes()).hexdigest(),
        'thread_environment':{},'dispatch_environment':{}}))
    cache=tmp_path/'cache'
    monkeypatch.setenv('BORN_LADDER_ENV_ROOT',str(cache))
    monkeypatch.setenv('BORN_LADDER_WHEELHOUSE',str(tmp_path/'offline'))
    monkeypatch.delenv('BORN_LADDER_STAGE_PROFILE',raising=False)
    monkeypatch.delenv('LD_LIBRARY_PATH',raising=False)
    monkeypatch.setattr(E,'check_current',lambda p:(_ for _ in ()).throw(ValueError('requires managed runtime')))
    monkeypatch.setattr(E,'base_matches',lambda p:True)
    identity=hashlib.sha256(profile.read_bytes()+lock.read_bytes()).hexdigest()[:16]
    target=cache/('verification-'+identity)
    expected={'profile_sha256':hashlib.sha256(profile.read_bytes()).hexdigest(),
              'lock_sha256':hashlib.sha256(lock.read_bytes()).hexdigest()}
    return specs.parent,target,expected


@pytest.fixture
def location_interpreter(tmp_path,monkeypatch):
    # A tiny native surrogate has exactly uv's $ORIGIN-relative loader
    # requirement. It stands in for ensurepip/pip/child work; no network or
    # Python download is involved. A copied binary cannot load its library.
    cc=shutil.which('cc')
    if sys.platform!='linux' or cc is None:pytest.skip('Linux C linker required for $ORIGIN regression')
    install=tmp_path/'install';(install/'bin').mkdir(parents=True);(install/'lib').mkdir()
    library=tmp_path/'library.c';library.write_text('int location_dependency(void) { return 0; }\n')
    program=tmp_path/'interpreter.c'
    program.write_text('int location_dependency(void); int main(void) { return location_dependency(); }\n')
    executable=install/'bin/python3.12'
    subprocess.run([cc,'-shared','-fPIC',str(library),'-o',str(install/'lib/liblocation.so')],check=True)
    subprocess.run([cc,str(program),'-L'+str(install/'lib'),'-llocation',
                    '-Wl,-rpath,$ORIGIN/../lib','-o',str(executable)],check=True)
    assert subprocess.run([str(executable)]).returncode==0
    monkeypatch.setattr(sys,'_base_executable',str(executable))
    return executable


def test_managed_environment_uses_location_preserving_symlinks(managed,location_interpreter):
    specs,target,expected=managed
    with pytest.raises(subprocess.CalledProcessError) as failure:
        venv.EnvBuilder(with_pip=True,symlinks=False).create(target.parent/'copied-control')
    assert failure.value.returncode==127
    assert E.ensure_environment('verification',specs,['--help'])==0
    assert (target/'bin/python').is_symlink()
    assert (target/'bin/python').resolve()==location_interpreter
    assert json.loads((target/'stage_ready.json').read_bytes())==expected


def test_unfinished_copied_environment_is_rebuilt_under_same_lock(managed,location_interpreter,tmp_path):
    specs,target,expected=managed
    with pytest.raises(subprocess.CalledProcessError):
        venv.EnvBuilder(with_pip=True,symlinks=False).create(target)
    stale=target/'lib/stale_package';stale.mkdir(parents=True);(stale/'broken.py').write_text('broken')
    (target/'pyvenv.cfg').write_text('broken configuration')
    outside=tmp_path/'outside';outside.mkdir();(outside/'keep').write_text('keep')
    link=target/'lib64'
    if link.is_symlink():link.unlink()
    link.symlink_to(outside,target_is_directory=True)
    lock=target/'.provision.lock';lock.write_text('same lock inode')
    inode=lock.stat().st_ino
    assert not (target/'stage_ready.json').exists()
    assert E.ensure_environment('verification',specs,['--help'])==0
    assert lock.stat().st_ino==inode and lock.read_text()=='same lock inode'
    assert not stale.exists() and (outside/'keep').read_text()=='keep'
    assert 'broken configuration' not in (target/'pyvenv.cfg').read_text()
    assert (target/'bin/python').resolve()==location_interpreter
    assert json.loads((target/'stage_ready.json').read_bytes())==expected


@pytest.mark.parametrize('symlink',[False,True],ids=['published-copy','published-symlink'])
def test_published_environment_is_reused_without_mutation(managed,monkeypatch,symlink):
    specs,target,expected=managed
    venv.EnvBuilder(with_pip=False,symlinks=symlink).create(target)
    (target/'stage_ready.json').write_text(json.dumps(expected)+'\n')
    files=[target/'stage_ready.json',target/'pyvenv.cfg',target/'bin/python']
    before=[p.read_bytes() for p in files]
    monkeypatch.setattr(E.venv,'EnvBuilder',lambda **kw:pytest.fail('published environment was rebuilt'))
    calls=[]
    monkeypatch.setattr(E.subprocess,'run',lambda cmd,**kw:calls.append(cmd) or subprocess.CompletedProcess(cmd,0))
    assert E.ensure_environment('verification',specs,['--help'])==0
    assert len(calls)==1 and calls[0][0]==str(target/'bin/python') and 'pip' not in calls[0]
    assert [p.read_bytes() for p in files]==before


def test_changed_publication_is_rejected_without_repair(managed,monkeypatch):
    specs,target,expected=managed;target.mkdir(parents=True)
    (target/'stage_ready.json').write_text(json.dumps({**expected,'lock_sha256':'changed'}))
    monkeypatch.setattr(E.venv,'EnvBuilder',lambda **kw:pytest.fail('published environment was rebuilt'))
    with pytest.raises(ValueError,match='publication differs'):
        E.ensure_environment('verification',specs,['--help'])


def test_empty_cache_root_is_rejected_even_when_runtime_matches(managed,monkeypatch):
    specs,_,_=managed;monkeypatch.setenv('BORN_LADDER_ENV_ROOT','')
    monkeypatch.setattr(E,'check_current',lambda p:None)
    with pytest.raises(ValueError,match='must be nonempty'):
        E.ensure_environment('verification',specs,['--help'])


def test_runtime_only_check_reuses_publication_and_checks_child_runtime(managed,monkeypatch):
    specs,target,expected=managed
    venv.EnvBuilder(with_pip=False,symlinks=True).create(target)
    ready=target/'stage_ready.json';ready.write_text(json.dumps(expected))
    before=ready.read_bytes()
    monkeypatch.setattr(E.venv,'EnvBuilder',lambda **kw:pytest.fail('published environment was rebuilt'))
    calls=[]
    monkeypatch.setattr(E.subprocess,'run',lambda cmd,**kw:calls.append(cmd) or subprocess.CompletedProcess(cmd,0))
    assert E.ensure_environment('verification',specs,[],check_only=True)==0
    assert len(calls)==1 and calls[0][:2]==[str(target/'bin/python'),'-c']
    assert 'stage_identity' in calls[0][2] and calls[0][-2:]==[str(specs),'verification']
    assert ready.read_bytes()==before


@pytest.mark.parametrize('exit_code',[0,1])
def test_preflight_runs_in_isolated_child_without_changing_parent(managed,monkeypatch,exit_code):
    specs,_,_=managed
    monkeypatch.setenv('BORN_LADDER_STAGE_PROFILE','predictive')
    monkeypatch.setenv('NPY_DISABLE_CPU_FEATURES','parent-dispatch')
    before=dict(os.environ);calls=[]
    def child(command,**kw):
        calls.append(command)
        assert kw['env'].get('BORN_LADDER_STAGE_PROFILE') is None
        assert kw['env']['NPY_DISABLE_CPU_FEATURES']=='parent-dispatch'
        assert kw['stdout'] is sys.stderr
        return subprocess.CompletedProcess(command,exit_code)
    monkeypatch.setattr(E.subprocess,'run',child)
    if exit_code:
        with pytest.raises(ValueError,match='environment preflight failed'):
            E.preflight_environment('verification',specs)
    else:E.preflight_environment('verification',specs)
    assert len(calls)==1 and 'check_only=True' in calls[0][2]
    assert calls[0][-2:]==['verification',str(specs.resolve())]
    assert dict(os.environ)==before
