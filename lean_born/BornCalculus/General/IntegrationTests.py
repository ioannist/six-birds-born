"""Regression checks for recursive discovery, receipt integrity and rendered support.
Run: python3 lean_born/BornCalculus/General/IntegrationTests.py
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[2] / 'tools' / 'audit_declarations.py'
spec = importlib.util.spec_from_file_location('integration_audit', TOOL)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditTests(unittest.TestCase):
    def setUp(self):
        # Tests write only to the worktree's ignored local artifact directory.
        scratch = TOOL.parents[1] / '.lake' / 'audit'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.root = Path(self.temp.name)
        (self.root / 'BornCalculus' / 'Nested').mkdir(parents=True)
        (self.root / 'BornCalculus.lean').write_text('')

    def tearDown(self):
        self.temp.cleanup()

    def write(self, text, name='Packet.lean'):
        p = self.root / 'BornCalculus' / 'Nested' / name
        p.write_text(text)
        return p

    def test_scopes_literals_modifiers_and_quoted_names(self):
        self.write('''/- theorem ghost : True := by trivial /- nested -/ -/
namespace BornCalculus.General
section Local
private theorem helper : True := by trivial
noncomputable protected def η' : String := "namespace Wrong\\nend General"
namespace Nested
@[simp] theorem «proof.with.dot» : True := by trivial
end Nested
end Local
end BornCalculus.General
namespace Other
def _root_.outside : Nat := 0
end Other
''')
        rows = audit.inventory(self.root)
        self.assertEqual([r['name'] for r in rows],
                         ["BornCalculus.General.η'", 'BornCalculus.General.Nested.«proof.with.dot»', 'outside'])
        self.assertEqual(rows[1]['components'], ['BornCalculus', 'General', 'Nested', 'proof.with.dot'])
        self.assertEqual(rows[0]['line'], 5)

    def test_audit_filename_cannot_hide_a_public_endpoint(self):
        self.write('namespace BornCalculus.Census\ntheorem endpoint : True := by trivial\nend BornCalculus.Census\n', 'Audit.lean')
        self.assertEqual(audit.inventory(self.root)[0]['name'], 'BornCalculus.Census.endpoint')

    def test_standard_punctuation_suffixes(self):
        self.write('namespace A\ndef lookup? : Nat := 0\ndef get! : Nat := 1\nend A\n')
        self.assertEqual([r['name'] for r in audit.inventory(self.root)], ['A.lookup?', 'A.get!'])

    def test_unsupported_syntax_fails_closed_and_manifest_is_checked(self):
        self.write('namespace BornCalculus\ninstance : Inhabited Nat := ⟨0⟩\nend BornCalculus\n')
        with self.assertRaisesRegex(ValueError, 'anonymous declaration'):
            audit.inventory(self.root)
        manifest = self.root / 'BornCalculus' / 'Nested' / 'audit_manifest.json'
        row = {'name': 'BornCalculus.instInhabitedNat', 'kind': 'instance',
               'file': 'BornCalculus/Nested/Packet.lean', 'line': 2}
        manifest.write_text(json.dumps({'declarations': [row]}))
        self.assertEqual(audit.inventory(self.root)[0]['name'], row['name'])
        row['file'] = '../escape.lean'
        manifest.write_text(json.dumps({'declarations': [row]}))
        with self.assertRaises(ValueError): audit.inventory(self.root)

    def test_duplicate_names_and_broken_scopes_fail(self):
        self.write('namespace A\ndef same : Nat := 0\nend A\n')
        self.write('namespace A\ndef same : Nat := 1\nend A\n', 'Second.lean')
        with self.assertRaisesRegex(ValueError, 'duplicate declaration'): audit.inventory(self.root)
        self.write('namespace A\nend B\n', 'Second.lean')
        with self.assertRaisesRegex(ValueError, 'mismatched end'): audit.inventory(self.root)

    def test_inline_and_initializer_declarations_cannot_escape(self):
        for text in ('namespace A in theorem hidden : True := by trivial\n',
                     'set_option maxHeartbeats 0 in theorem hidden : True := by trivial\n',
                     'initialize hidden : Nat ← pure 0\n'):
            self.write(text)
            with self.assertRaisesRegex(ValueError, 'requires audit_manifest.json'):
                audit.inventory(self.root)

    def test_receipts_reject_missing_extra_duplicate_and_forbidden(self):
        names = ["BornCalculus.η'"]
        def output(deps):
            return 'BORN_AXIOM_AUDIT_JSON ' + json.dumps({'schema': 'born_axiom_dependencies_v2', 'dependencies': deps})
        good = output({names[0]: ['Classical.choice']})
        self.assertEqual(audit.verify(good, names)['dependencies'][names[0]], ['Classical.choice'])
        legacy = f"'{names[0]}' depends on axioms: [Classical.choice]"
        self.assertEqual(audit.verify(legacy, names)['status'], 'PASS')
        for bad in (output({}), output({names[0]: ['sorryAx']}), output({names[0]: [], 'Other': []}),
                    good + '\n' + good, legacy + '\n' + legacy, good + '\nerror: stale'):
            with self.assertRaises(ValueError): audit.verify(bad, names)
        duplicate = '{"schema":"born_axiom_dependencies_v2","dependencies":{"A":[],"A":[]}}'
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            audit.verify('BORN_AXIOM_AUDIT_JSON ' + duplicate, ['A'])

    def test_rendered_prepare_never_overwrites_existing_or_census(self):
        rendered = self.root / 'BornCalculus' / 'General'
        rendered.mkdir()
        retained = rendered / 'Frame.lean'
        retained.write_text('rendered local frame marker\n')
        census = self.root / 'BornCalculus' / 'CensusInputs.lean'
        census.write_text('rendered census marker\n')
        receipt = audit.prepare(self.root)
        self.assertGreater(len(receipt['copied_missing_proof_modules']), 10)
        self.assertEqual(retained.read_text(), 'rendered local frame marker\n')
        self.assertEqual(census.read_text(), 'rendered census marker\n')
        self.assertFalse((self.root / 'BornCalculus' / 'Census').exists())


if __name__ == '__main__':
    unittest.main()
