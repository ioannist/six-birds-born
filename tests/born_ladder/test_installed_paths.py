"""Repository inputs belong to the invocation checkout, not site-packages."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from born_ladder.reproduction import lean_comparison as L, map_replay as M

ROOT=Path(__file__).resolve().parents[2]


def test_lean_driver_uses_cwd_or_explicit_project_not_module_location(tmp_path,monkeypatch):
    monkeypatch.setattr(L,'__file__',str(tmp_path/'venv/lib/python3.12/site-packages/born_ladder/reproduction/lean_comparison.py'))
    assert any(row['name']=='BornCalculus.General.carrier_and_trace' for row in L.driver().inventory(ROOT/'lean_born'))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError,match='run from the repository root'):L.driver()
    assert any(row['name']=='BornCalculus.General.carrier_and_trace' for row in L.driver(ROOT/'lean_born').inventory(ROOT/'lean_born'))


def test_audit_workspace_is_absolute_in_invocation_checkout(tmp_path,monkeypatch):
    import born_ladder.__main__ as C
    project=tmp_path/'lean';(project/'tools').mkdir(parents=True);(project/'tools/audit_declarations.py').write_text('# selected project tools\n')
    monkeypatch.chdir(tmp_path)
    seen=[]
    class Auditor:
        def inventory(self,root):assert root==project;return [{'name':'BornCalculus.endpoint'}]
    monkeypatch.setattr(L,'driver',lambda root:Auditor())
    def check(root,rows,workspace):
        assert Path(workspace).is_absolute()
        assert Path(workspace).is_relative_to(tmp_path/'scratch/registry_full_cohort/kernel_checks')
        seen.append(Path(workspace));return {'status':'PASS'}
    monkeypatch.setattr(L,'readonly_kernel_check',check)
    assert C.audit_endpoints(project,['endpoint'])['fresh'] is True
    assert len(seen)==1 and not seen[0].exists()


def test_map_replay_default_source_root_is_invocation_checkout(tmp_path,monkeypatch):
    monkeypatch.setattr(M,'__file__',str(tmp_path/'venv/lib/python3.12/site-packages/born_ladder/reproduction/map_replay.py'))
    seen=[]
    def validate(output,source_root):seen.append(source_root);raise RuntimeError('root captured before any write')
    monkeypatch.setattr(M,'validate_output',validate)
    with pytest.raises(RuntimeError,match='root captured'):
        M.run_map_replay(census='unused',original_context='unused',output='unused')
    assert seen==[Path.cwd()]
    seen.clear()
    with pytest.raises(RuntimeError,match='root captured'):
        M.run_map_replay(census='unused',original_context='unused',output='unused',source_root=tmp_path)
    assert seen==[tmp_path]


def test_installed_no_data_verification_and_affected_tests():
    """Exercise the installed interpreter automatically, with no source fallback."""
    configured=os.environ.get('BORN_INSTALLED_CHECK_PYTHON')
    if not configured:
        import born_ladder
        if Path(born_ladder.__file__).resolve().is_relative_to(ROOT/'src'):
            pytest.skip('installed-package check; source mode can set BORN_INSTALLED_CHECK_PYTHON')
        configured=sys.executable
    # Resolving a venv's interpreter symlink would invoke the system Python
    # without its installed packages. Preserve the venv launcher path.
    python=Path(configured).absolute();env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1'}
    env.pop('PYTHONPATH',None);env.pop('BORN_INSTALLED_CHECK_PYTHON',None)
    assert 'site-packages' in subprocess.check_output([str(python),'-c','import born_ladder;print(born_ladder.__file__)'],cwd=ROOT,env=env,text=True)
    result=subprocess.run([str(python),'-m','born_ladder','verify','B03'],cwd=ROOT,env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'PASS B03' in result.stdout
    # The affected tests run normally in this installed-mode suite. Do not
    # launch another pytest from a running pytest process.
    code="""from pathlib import Path
from born_ladder.reproduction import lean_comparison, map_replay, runs
assert all('site-packages' in module.__file__ for module in (lean_comparison,map_replay,runs))
assert any(row['name']=='BornCalculus.General.carrier_and_trace'
           for row in lean_comparison.driver().inventory(Path('lean_born')))
"""
    result=subprocess.run([str(python),'-c',code],cwd=ROOT,env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('claim', [False,True])
def test_smoke_comparison_completion_keeps_nonconfirmatory_scope(tmp_path,monkeypatch,claim):
    from born_ladder.reproduction.full_comparison import protocol
    import born_ladder.reproduction.regenerated_bundle as B
    groups={name:{'status':'REDUCED_NONCONFIRMATORY','claim_ids':['P13'] if claim else [],
                  'full_cohort_claim_asserted':claim}
            for name in ('worked','census','attachments','evaluation','test_b')}
    (tmp_path/'verification_report.json').write_text(json.dumps({'status':'COMPLETE','profile':'smoke',
        'checks':groups,'formal_endpoints':{'status':'NOT_APPLICABLE'}}))
    monkeypatch.setattr(B,'Bundle',lambda root:None)
    result=protocol(tmp_path,ROOT/'specifications','smoke')
    assert result['stages']['verification']['status']==('FAIL' if claim else 'PASS')
