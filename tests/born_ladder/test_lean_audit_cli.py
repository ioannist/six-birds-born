"""Readable audit summary must not change the JSON stdout interface."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest


@pytest.fixture
def driver():
    path=Path(__file__).resolve().parents[2]/'lean_born/tools/audit_declarations.py'
    spec=importlib.util.spec_from_file_location('audit_cli',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_audit_summary_is_stderr_and_stdout_remains_one_json_receipt(driver,monkeypatch,capsys):
    receipt={'status':'PASS','declarations':5058,'allowed_axioms':sorted(driver.ALLOWED),'forbidden':{}}
    monkeypatch.setattr(driver,'audit',lambda *args:receipt)
    monkeypatch.setattr(sys,'argv',['audit_declarations.py','audit'])
    driver.main();out=capsys.readouterr()
    assert json.loads(out.out)==receipt and len(out.out.splitlines())==1
    assert 'Lean audit: PASS, 5058 declarations' in out.err
    assert 'Classical.choice, Quot.sound, propext; forbidden: none' in out.err


def test_audit_failure_has_no_success_summary(driver,monkeypatch,capsys):
    monkeypatch.setattr(driver,'audit',lambda *args:(_ for _ in ()).throw(ValueError('forbidden axiom')))
    monkeypatch.setattr(sys,'argv',['audit_declarations.py','audit'])
    with pytest.raises(SystemExit) as error:driver.main()
    assert error.value.code==1
    out=capsys.readouterr()
    assert 'FAIL: forbidden axiom' in out.err and 'Lean audit: PASS' not in out.err
