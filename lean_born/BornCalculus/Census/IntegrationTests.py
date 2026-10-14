"""Lean census integration regressions; run with the verification dependencies."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from born_ladder.reproduction import lean_inputs as L, pipeline as P

ROOT=Path(__file__).resolve().parents[3]


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        directory=ROOT/'.lake/audit/integration3-tests';directory.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=directory)
        self.base=Path(self.temp.name);self.lean=self.base/'lean';self.logs=self.base/'logs'
        self.lean.mkdir()
    def tearDown(self):self.temp.cleanup()
    def render(self):
        (self.lean/'formal_coverage.json').write_text(json.dumps({
            'status':'APPLICABLE','census_cases':2122,'full_cohort_inputs':True,
            'required_build_targets':['BornCalculus.Census.FullWitness','BornCalculus.Census.AuditFull']}))
    def child(self,argv,**kwargs):
        if argv[1]=='lean':record={'status':'PASS','modules':347}
        else:record={'status':'PASS','fresh':True,'declarations':5058,'forbidden':{}}
        kwargs['stdout'].write((json.dumps(record)+'\n').encode())
        return subprocess.CompletedProcess(argv,0)
    def test_promotion_requires_both_fresh_receipts(self):
        with patch.object(P.subprocess,'run',side_effect=self.child) as child:
            result=P.run_lean_step(lean_directory=self.lean,logs=self.logs,render=self.render,require_full_cohort=True)
        self.assertEqual([call.args[0][1] for call in child.call_args_list],['lean','lean-audit'])
        self.assertEqual(result['status'],'APPLICABLE')
        self.assertEqual(result['build_status'],'BUILT_AND_AUDITED')
        self.assertEqual(json.loads((self.lean/'formal_coverage.json').read_text())['build_status'],'BUILT_AND_AUDITED')
    def test_failure_does_not_reuse_successful_old_logs(self):
        self.logs.mkdir();(self.logs/'lean-audit.log').write_text(json.dumps({'status':'PASS','fresh':True})+'\n')
        def fail(argv,**kwargs):
            if argv[1]=='lean-audit':raise subprocess.CalledProcessError(1,argv)
            return self.child(argv,**kwargs)
        with patch.object(P.subprocess,'run',side_effect=fail):
            with self.assertRaises(subprocess.CalledProcessError):
                P.run_lean_step(lean_directory=self.lean,logs=self.logs,render=self.render,require_full_cohort=True)
        self.assertEqual(json.loads((self.lean/'formal_coverage.json').read_text())['build_status'],'PENDING_BUILD_AND_AUDIT')
    def test_failed_render_invalidates_success_before_renderer_runs(self):
        self.render()
        path=self.lean/'formal_coverage.json'
        inputs=json.loads(path.read_text())
        path.write_text(json.dumps({**inputs,'build_status':'BUILT_AND_AUDITED',
                                   'build_receipt':'old-build.json','audit_receipt':'old-audit.json'}))
        expected={**inputs,'build_status':'PENDING_BUILD_AND_AUDIT'}
        def fail_render():
            self.assertEqual(json.loads(path.read_text()),expected)
            raise RuntimeError('renderer failed')
        with patch.object(P.subprocess,'run') as child:
            with self.assertRaisesRegex(RuntimeError,'renderer failed'):
                P.run_lean_step(lean_directory=self.lean,logs=self.logs,
                                render=fail_render,require_full_cohort=True)
        child.assert_not_called()
        self.assertEqual(json.loads(path.read_text()),expected)
    def test_missing_or_nonfresh_audit_receipt_is_rejected(self):
        for record in ({'status':'PASS','fresh':False},{'status':'PASS','fresh':True,'forbidden':{'bad':['sorryAx']}}):
            def child(argv,**kwargs):
                if argv[1]=='lean':return self.child(argv,**kwargs)
                kwargs['stdout'].write((json.dumps(record)+'\n').encode());return subprocess.CompletedProcess(argv,0)
            with patch.object(P.subprocess,'run',side_effect=child):
                with self.assertRaises(ValueError):
                    P.run_lean_step(lean_directory=self.lean,logs=self.logs,render=self.render,require_full_cohort=True)
    def test_renderer_regenerates_literals_and_copies_manifest(self):
        source=self.base/'source';(source/'BornCalculus/Census').mkdir(parents=True)
        for name in ('lakefile.toml','lake-manifest.json','lean-toolchain','BornCalculus.lean'):(source/name).write_text('fixture')
        for name in ('Shard000','FullInputs','Certificate'):(source/'BornCalculus/Census'/f'{name}.lean').write_text(name)
        (source/'BornCalculus/Census/audit_manifest.json').write_text('{"declarations":[]}')
        L.project_sources(source,self.lean,include_registered_inputs=True,regenerate_full_census=True)
        self.assertTrue((self.lean/'BornCalculus/Census/Certificate.lean').exists())
        self.assertTrue((self.lean/'BornCalculus/Census/audit_manifest.json').exists())
        self.assertFalse((self.lean/'BornCalculus/Census/Shard000.lean').exists())
        self.assertFalse((self.lean/'BornCalculus/Census/FullInputs.lean').exists())
        other=self.base/'legacy';other.mkdir();L.project_sources(source,other)
        self.assertTrue((other/'BornCalculus/Census/Shard000.lean').exists())
        self.assertTrue((other/'BornCalculus/Census/FullInputs.lean').exists())

    def test_renderer_resume_resets_build_state_and_rejects_changed_inputs(self):
        census=self.base/'census';census.mkdir()
        with patch.object(L,'checked_worked',return_value=()), \
             patch.object(L,'census_records',return_value=([{'unit_id':'fixture'}],[])):
            def render():
                return L.run_lean_inputs(census=census,output=self.lean,
                                         worked_cases=self.base/'worked',render_registered=False)
            render()
            path=self.lean/'formal_coverage.json'
            coverage=json.loads(path.read_text())
            coverage.update(build_status='BUILT_AND_AUDITED',build_receipt='old.json',audit_receipt='old.json')
            path.write_text(json.dumps(coverage))
            render()
            resumed=json.loads(path.read_text())
            self.assertNotIn('build_status',resumed)
            self.assertNotIn('audit_receipt',resumed)
            resumed['census_cases']=2
            path.write_text(json.dumps(resumed))
            with self.assertRaisesRegex(ValueError,'formal coverage inputs changed on resume'):
                render()


if __name__=='__main__':unittest.main()
