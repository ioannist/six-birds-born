"""Public command documentation must agree with the executable registry."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
import re

from born_ladder.__main__ import REGISTRY

ROOT = Path(__file__).resolve().parents[2]


def test_claim_reference_matches_registry():
    text = (ROOT / 'docs/claims.md').read_text()
    rows = re.findall(r'^\| ((?:P|B)\d\d|TB01) \| ([^|]+) \| ([^|]+) \| `([^`]+)` \|', text, re.M)
    assert len(rows) == len(REGISTRY) == 31
    assert {row[0] for row in rows} == set(REGISTRY)
    for identifier, statement, kind, command in rows:
        title, lane, endpoints = REGISTRY[identifier]
        assert statement.strip() == title
        expected = f'.venv/bin/python -m born_ladder verify {identifier}'
        if lane == 'data':
            from born_ladder.full_cohort_claims import IDS
            expected += ' --data "$BORN_FULL_DATA"' if identifier in IDS else ' --data "$BORN_DATA_BUNDLE"'
            assert kind.strip() == (('Machine-checked Lean + data-dependent' if identifier in IDS else 'Lean + data-dependent') if endpoints else 'Data-dependent')
        if identifier == 'P12':
            expected += ' --historical-root "$BORN_HISTORICAL_ROOT"'
        assert command == expected


def markdown_anchors(text):
    # GitHub heading slugs plus explicit compatibility anchors. Fenced code
    # comments are not headings. Repeated headings acquire numeric suffixes.
    text=re.sub(r'^```.*?^```[^\n]*$', '', text, flags=re.M|re.S)
    anchors=set(re.findall(r'<a\s+id="([^"]+)"',text))
    counts={}
    for title in re.findall(r'^#{1,6} (.+)$',text,re.M):
        slug=re.sub(r'[^\w\- ]','',title.lower()).replace(' ','-')
        number=counts.get(slug,0);counts[slug]=number+1
        anchors.add(slug+('-'+str(number) if number else ''))
    return anchors


def test_public_document_links_resolve():
    from urllib.parse import unquote
    paths = [ROOT / 'README.md', *(ROOT / 'docs').glob('*.md'),
             ROOT / 'lean_born/COVERAGE.md', ROOT / 'src/born_ladder/snapshot/README.md',
             ROOT / 'tests/born_ladder/fixtures/README.md']
    for path in paths:
        for link in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            if not re.match(r'https?://', link):
                filename,_,fragment=unquote(link).partition('#')
                target=(path.parent/filename) if filename else path
                assert target.exists(), (path, link)
                if fragment and target.suffix=='.md':
                    assert fragment in markdown_anchors(target.read_text()), (path,link)
        assert not any('/' + segment + '/' in path.read_text() for segment in ('home', 'mnt'))


def test_reproduce_help_describes_full_cohort_lean_inputs():
    result=subprocess.run([sys.executable,'-m','born_ladder','reproduce','--help'],
                          cwd=ROOT,capture_output=True,text=True,check=True)
    assert '266 census shards' in ' '.join(result.stdout.split())
    assert 'eight exact Lean input modules' not in result.stdout


def test_coverage_names_exported_declarations():
    tool = ROOT / 'lean_born/tools/audit_declarations.py'
    spec = importlib.util.spec_from_file_location('public_audit', tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = {row['name'].removeprefix('BornCalculus.') for row in module.inventory(ROOT / 'lean_born')}
    text = (ROOT / 'lean_born/COVERAGE.md').read_text()
    table = text.split('## Rebuild')[0]
    endpoints = re.findall(r'`([a-z][A-Za-z0-9_]+)`', table)
    assert len(endpoints) >= 40
    assert set(endpoints) <= names


def test_documented_inventory_command():
    result = subprocess.run([sys.executable, 'lean_born/tools/audit_declarations.py', 'inventory'],
                            cwd=ROOT, capture_output=True, text=True, check=True)
    declarations = json.loads(result.stdout)
    assert len(declarations) >= 250
    assert 'BornCalculus.joint_normalized_posteriors' in {d['name'] for d in declarations}
