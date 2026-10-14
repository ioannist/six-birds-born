"""Fresh-shell defaults, empty-output guards and clear Lean tool errors."""
import os
from pathlib import Path
import re
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[2]


def shell(tmp_path,extra=None):
    env={'HOME':str(tmp_path),'PATH':'/usr/bin:/bin','PYTHONPATH':'must-be-unset',**(extra or {})}
    return subprocess.run(['/bin/bash','-c',
        'source "$1" || exit; source "$1" || exit; '
        'printf "%s\\n" "$PATH" "$RUSTUP_TOOLCHAIN" "$PYTHONNOUSERSITE" '
        '"${PYTHONPATH-unset}" "$DATA_OUT" "$BORN_LADDER_ENV_ROOT"',
        'bash',str(ROOT/'env.sh')],cwd=tmp_path,env=env,text=True,capture_output=True)


def test_fresh_shell_restores_pins_paths_and_checkout_defaults(tmp_path):
    result=shell(tmp_path);assert result.returncode==0,result.stderr
    path,rust,user_site,pythonpath,data,cache=result.stdout.splitlines()
    assert path.split(':').count(str(tmp_path/'.cargo/bin'))==1
    assert path.split(':').count(str(tmp_path/'.elan/bin'))==1
    assert (rust,user_site,pythonpath)==('1.93.1','1','unset')
    assert data==str(ROOT/'scratch/reproduction')
    assert cache==str(ROOT/'scratch/environments')


def test_shell_preserves_explicit_output_cache_and_toolchain(tmp_path):
    result=shell(tmp_path,{'DATA_OUT':str(tmp_path/'data'),'BORN_LADDER_ENV_ROOT':str(tmp_path/'cache'),
                           'RUSTUP_TOOLCHAIN':'explicit-toolchain'})
    assert result.returncode==0,result.stderr
    values=result.stdout.splitlines()
    assert values[1]=='explicit-toolchain'
    assert values[-2:]==[str(tmp_path/'data'),str(tmp_path/'cache')]


@pytest.mark.parametrize('name',['DATA_OUT','BORN_LADDER_ENV_ROOT'])
def test_shell_rejects_explicitly_empty_paths(tmp_path,name):
    result=shell(tmp_path,{name:''})
    assert result.returncode!=0 and 'must be nonempty' in result.stderr


@pytest.mark.parametrize('target',['lean','lean-audit'])
@pytest.mark.parametrize('present,missing',[(None,'elan'),('elan','lake')])
def test_make_reports_missing_lean_tool_before_cache_fallback(tmp_path,target,present,missing):
    if present:
        script=tmp_path/present;script.write_text('#!/bin/sh\nexit 0\n');script.chmod(0o755)
    result=subprocess.run(['/usr/bin/make',target,'LEAN_ROOT='+str(tmp_path/'lean')],cwd=ROOT,
        env={**os.environ,'PATH':str(tmp_path)},text=True,capture_output=True)
    assert result.returncode!=0
    assert 'Missing required tool: '+missing in result.stderr
    assert 'falling back' not in result.stdout+result.stderr


@pytest.mark.parametrize('target',['rust','rust-test-b'])
@pytest.mark.parametrize('present,missing',[(None,'rustup'),('rustup','cargo')])
def test_make_reports_missing_rust_tool_before_build(tmp_path,target,present,missing):
    if present:
        script=tmp_path/present;script.write_text('#!/bin/sh\nexit 0\n');script.chmod(0o755)
    result=subprocess.run(['/usr/bin/make',target],cwd=ROOT,
        env={**os.environ,'PATH':str(tmp_path)},text=True,capture_output=True)
    assert result.returncode!=0
    assert 'Missing required tool: '+missing in result.stderr
    assert 'cargo build' not in result.stdout


def test_replicate_rejects_empty_output_before_starting_pipeline():
    result=subprocess.run(['make','replicate','DATA_OUT='],cwd=ROOT,text=True,capture_output=True)
    assert result.returncode!=0 and 'DATA_OUT=' in result.stdout
    assert 'reproduce all' not in result.stdout


def documented_commands():
    readme=(ROOT/'README.md').read_text()
    guide=(ROOT/'docs/reproduction.md').read_text()
    blocks=lambda text:re.findall(r'```sh\n(.*?)```',text,re.S)
    smoke=next(b for b in blocks(readme) if 'reproduce all --profile smoke' in b)
    smoke_table=next(c for c in re.findall(r'`([^`]+)`',readme)
                     if 'reproduce all --profile smoke' in c)
    paper=lambda text:next(b for b in blocks(text) if 'reproduce paper-numbers' in b)
    replicate=lambda text:next(line for line in text.splitlines()
                              if line.startswith('make replicate DATA_OUT='))
    unattended=next(b for b in blocks(readme) if 'nohup make replicate' in b)
    mkdir=unattended.splitlines()[0]
    nohup='\n'.join(unattended.splitlines()[1:])
    return [smoke_table,smoke,paper(readme),paper(guide),replicate(readme),replicate(guide),mkdir,nohup]


@pytest.mark.parametrize('command',documented_commands(),ids=[
    'smoke-table','smoke-block','paper-readme','paper-guide',
    'replicate-readme','replicate-guide','unattended-mkdir','unattended-nohup'])
@pytest.mark.parametrize('empty',[True,False],ids=['empty-output','valid-output'])
def test_interactive_bash_guards_the_producer_command(tmp_path,command,empty):
    # Interactive Bash survives an expansion error. Only a guard within this
    # command's own arguments/redirection can prevent the producer from running.
    stub=tmp_path/'stub';stub.mkdir()
    python=tmp_path/'.venv/bin/python';python.parent.mkdir(parents=True)
    for path in [python,*(stub/name for name in ('make','mkdir','nohup'))]:
        path.write_text('#!/bin/sh\nprintf "called\\n" >> "$STUB_LOG"\n')
        path.chmod(0o755)
    output=tmp_path/'data';output.mkdir()
    log=tmp_path/'calls.log'
    result=subprocess.run(['/bin/bash','--noprofile','--norc','-i'],
        input=command+'\nwait\nprintf "SHELL_SURVIVED\\n"\nexit\n',
        cwd=tmp_path,env={**os.environ,'PATH':str(stub),'STUB_LOG':str(log),
                          'HOME':str(tmp_path),'HISTFILE':str(tmp_path/'history'),
                          'DATA_OUT':'' if empty else str(output)},
        text=True,capture_output=True,timeout=10)
    assert 'SHELL_SURVIVED' in result.stdout,result.stderr
    if empty:
        assert 'Source env.sh or set DATA_OUT' in result.stderr
        assert not log.exists(),result.stdout+result.stderr
    else:
        assert result.returncode==0,result.stderr
        assert log.read_text()=='called\n'


def test_documentation_contains_no_standalone_output_guards():
    for name in ('README.md','docs/reproduction.md'):
        assert ': "${DATA_OUT:?' not in (ROOT/name).read_text()
