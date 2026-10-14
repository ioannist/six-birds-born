"""Archive-free number coverage, classification, rendering and CLI controls."""
from collections import Counter
from copy import deepcopy
from fractions import Fraction
import json
import os
from pathlib import Path
import subprocess
import sys
import runpy

import pytest

from born_ladder.__main__ import REGISTRY
from born_ladder.reproduction import paper_numbers as P
from born_ladder.reproduction import full_comparison as F
from born_ladder.reproduction.regenerated_bundle import GROUPS

ROOT=Path(__file__).resolve().parents[2]
MAP=ROOT/'specifications/paper_numbers.json'


def test_calibration_setting_checks_sampling_loop_not_header_metadata(tmp_path):
    document=json.loads(MAP.read_text())
    row=next(r for r in document['macros'] if r['macro']=='CalibrationReadings')
    generator=runpy.run_path(str(ROOT/'tools/generate_paper_number_map.py'))
    assert row['binding']==generator['setting_bindings']()['CalibrationReadings']
    path=tmp_path/row['binding']['file'];path.parent.mkdir(parents=True)
    original=(ROOT/row['binding']['file']).read_text()
    path.write_text(original)
    _,definitions=P.classify(ROOT/'paper/main.tex',document)
    extract=lambda r:P.setting_value(r['binding'],tmp_path)
    assert P.check_numbers([row],definitions,extract)[0]['match'] is True
    assert original.count('for _ in 0..8192 { states.push(v6_start(')==1
    changed=original.replace('for _ in 0..8192 { states.push(v6_start(',
                             'for _ in 0..8191 { states.push(v6_start(')
    assert changed.count('"calibration_draws": 8192')==original.count('"calibration_draws": 8192')
    path.write_text(changed)
    check=P.check_numbers([row],definitions,extract)[0]
    assert check['status']=='MISMATCH' and check['match'] is False
    assert Fraction(check['full_precision_value'])==8191


def test_resume_allows_admission_worker_changes_but_preserves_science():
    from born_ladder.reproduction.checkpoints import numeric_plan
    saved={'admission_workers':48,'scientific_rng_identity':'registered','input_commitments':['sha256']}
    assert numeric_plan(saved)==numeric_plan({**saved,'admission_workers':1})
    assert numeric_plan(saved)!=numeric_plan({**saved,'scientific_rng_identity':'altered'})
    assert numeric_plan(saved)!=numeric_plan({**saved,'input_commitments':['changed']})


def test_committed_map_covers_all_manuscript_macros_without_private_inputs():
    document=json.loads(MAP.read_text());rows,definitions=P.classify(ROOT/'paper/main.tex',document)
    assert Counter(r['class'] for r in rows)=={'regenerated':358,'setting':45,'non_numerical':40}
    assert len(definitions)==403
    assert set(P.declarations((ROOT/'paper/main.tex').read_text()))=={r['macro'] for r in rows}
    assert not any(token in MAP.read_text() for token in ('/mnt/','/home/','docs/internal/','scratch/','ledger','expression'))
    for row in rows:
        assert 'value' not in row and 'expected' not in row
        if row['class']=='setting':
            value,_=P.setting_value(row['binding'],ROOT)
            assert F.render(value,row['format'],row['direction'])==definitions[row['macro']]


@pytest.mark.parametrize('mutation',['missing','duplicate','downgraded','unknown_class'])
def test_map_cannot_hide_a_numerical_result(mutation):
    document=json.loads(MAP.read_text())
    index=next(i for i,r in enumerate(document['macros']) if r['macro']=='CensusCases')
    if mutation=='missing':document['macros'].pop(index)
    elif mutation=='duplicate':document['macros'].append(deepcopy(document['macros'][index]))
    else:document['macros'][index]['class']='non_numerical' if mutation=='downgraded' else 'unclassified'
    with pytest.raises(ValueError):P.classify(ROOT/'paper/main.tex',document)


def test_new_macro_outside_generated_block_cannot_disappear(tmp_path):
    path=tmp_path/'paper.tex';path.write_text((ROOT/'paper/main.tex').read_text()+r'\newcommand{\NewResult}{42}\NewResult{}')
    with pytest.raises(ValueError,match='coverage differs'):P.classify(path,json.loads(MAP.read_text()))


@pytest.mark.parametrize('definition',[r'\def\HiddenNumber{42}',r'\NewDocumentCommand{\HiddenNumber}{}{42}'])
def test_unrecognized_definition_api_cannot_hide_number(tmp_path,definition):
    path=tmp_path/'paper.tex';path.write_text((ROOT/'paper/main.tex').read_text()+definition+r'\HiddenNumber{}')
    with pytest.raises(ValueError):P.classify(path,json.loads(MAP.read_text()))


def test_non_numerical_figure_layout_is_not_claimed_as_a_number_check(tmp_path):
    original=(ROOT/'paper/main.tex').read_text()
    coordinate='rectangle (12.15,-1.4)'
    assert original.count(coordinate)==1
    text=original.replace(coordinate,'rectangle (12.05,-1.4)')
    path=tmp_path/'paper.tex';path.write_text(text)
    rows,_=P.classify(path,json.loads(MAP.read_text()))
    assert next(r for r in rows if r['macro']=='FigArchitecture')['class']=='non_numerical'


def test_outward_displays_share_the_comparison_renderer():
    rows=[{'macro':'Lower','class':'regenerated','format':'dec:2','direction':'lower'},
          {'macro':'Upper','class':'regenerated','format':'dec:2','direction':'upper'},
          {'macro':'Setting','class':'setting','format':'int'},
          {'macro':'Symbol','class':'non_numerical','source':'mathematical symbol'}]
    values={'Lower':'1/3','Upper':'1/3','Setting':32}
    checks=P.check_numbers(rows,{'Lower':'0.33','Upper':'0.34','Setting':'32'},lambda r:(values[r['macro']],{'sources':['fixture']}))
    assert all(r['match'] for r in checks)
    assert checks[-1]['status']=='NON_NUMERICAL'
    checks=P.check_numbers(rows,{'Lower':'0.34','Upper':'0.34','Setting':'32'},lambda r:(values[r['macro']],{}))
    assert checks[0]['status']=='MISMATCH'
    assert checks[0]['full_precision_value']=='1/3'


@pytest.mark.parametrize('value',[True,None,{'not':'numeric'},float('nan')])
def test_invalid_numeric_representation_cannot_pass(value):
    checks=P.check_numbers([{'macro':'Number','class':'regenerated','format':'int'}],{'Number':'1'},lambda r:(value,{}))
    assert not checks[0]['match'] and checks[0]['status']=='NOT_REGENERATED'


@pytest.fixture
def command_inputs(tmp_path):
    run=tmp_path/'run';run.mkdir()
    (run/'pipeline.json').write_text(json.dumps({'profile':'full','components':{}}))
    checks={k:{'status':'VERIFIED','claim_ids':list(ids),'claim_receipts':{i:{'id':i,'status':'VERIFIED'} for i in ids}} for k,ids in GROUPS.items()}
    (run/'verification_report.json').write_text(json.dumps({'status':'COMPLETE','profile':'full','checks':checks}))
    paper=tmp_path/'main.tex';paper.write_text('% >>> BEGIN GENERATED RESULT MACROS\n'+
        r'\newcommand{\Commands}{'+str(len(REGISTRY))+'}\n% <<< END GENERATED RESULT MACROS\n'+r'\Commands{}')
    document={'schema':'born_public_paper_numbers_v1','macros':[{'macro':'Commands','class':'regenerated','format':'int',
        'binding':{'view':'public_registry','pointer':'/commands'}}]}
    mapping=tmp_path/'map.json';mapping.write_text(json.dumps(document))
    return run,paper,mapping,tmp_path


@pytest.mark.parametrize('mutation',['valid','paper_value','missing_map_entry','missing_v25','reduced','empty_verification'])
def test_cli_reports_success_mismatch_and_missing_evidence(command_inputs,mutation):
    run,paper,mapping,tmp=command_inputs
    if mutation=='paper_value':paper.write_text(paper.read_text().replace('{'+str(len(REGISTRY))+'}','{999}'))
    if mutation=='missing_map_entry':mapping.write_text(json.dumps({'schema':'born_public_paper_numbers_v1','macros':[]}))
    if mutation=='missing_v25':
        d=json.loads(mapping.read_text());d['macros'][0]['binding']={'view':'v25','evaluation':'competitor','pointer':'/cases'};mapping.write_text(json.dumps(d))
    if mutation=='reduced':(run/'pipeline.json').write_text(json.dumps({'profile':'smoke','components':{}}))
    if mutation=='empty_verification':(run/'verification_report.json').write_text(json.dumps({'status':'COMPLETE','profile':'full','checks':{}}))
    output=tmp/'report'
    result=subprocess.run([sys.executable,'-m','born_ladder','reproduce','paper-numbers','--run',str(run),
        '--paper',str(paper),'--number-map',str(mapping),'--output',str(output)],cwd=ROOT,
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=60)
    report=json.loads((output/'report.json').read_text())
    assert (result.returncode==0)==(mutation=='valid'),result.stdout+result.stderr
    assert (report['status']=='PASS')==(mutation=='valid')
    if mutation=='valid':assert '1/1 paper numbers reproduced' in result.stdout
    elif mutation=='paper_value':assert report['checks'][0]['status']=='MISMATCH'
    elif mutation=='missing_v25':assert 'reproduce v25' in report['checks'][0]['reason']
    assert (output/'report.md').is_file()


def test_markdown_puts_results_first_and_non_numerical_macros_last(command_inputs):
    run,paper,mapping,tmp=command_inputs
    d=json.loads(mapping.read_text())
    d['macros'].insert(0,{'macro':'Symbol','class':'non_numerical','source':'symbol'})
    d['macros'].insert(1,{'macro':'Setting','class':'setting','format':'int','binding':{
        'kind':'literal','file':'Makefile','pattern':r'^LEAN_JOBS \?= ([0-9]+)'}})
    mapping.write_text(json.dumps(d))
    paper.write_text(paper.read_text()+r'\newcommand{\Symbol}{x}\Symbol{}'+r'\newcommand{\Setting}{2}\Setting{}')
    output=tmp/'report'
    report=P.run_paper_numbers(run=run,paper=paper,number_map=mapping,output=output)
    assert report['status']=='PASS'
    text=(output/'report.md').read_text()
    assert text.index('## Results')<text.index('## Settings and arithmetic constants')<text.index('## Non-numerical macros')
    assert text.index('| Commands |')<text.index('| Setting |')<text.index('| Symbol |')
    # The persistent empty file is the stage lock, not missing report content.
    assert (output/'.runs.lock').is_file() and (output/'.runs.lock').stat().st_size==0


@pytest.mark.parametrize('failure',[False,True],ids=['ready-runtime','provisioning-failure'])
def test_corrective_runtime_is_preflighted_before_population_extraction(command_inputs,monkeypatch,failure):
    from born_ladder.reproduction import stage_environment as S
    run,paper,mapping,tmp=command_inputs
    document=json.loads(mapping.read_text())
    document['macros'][0]['binding']={'view':'canonical_census','map':'raw','stat':'median'}
    mapping.write_text(json.dumps(document))
    calls=[]
    def preflight(name,specifications):
        calls.append('preflight')
        assert name=='predictive_v25' and specifications=='specifications'
        if failure:raise ValueError('predictive_v25 provisioning failed before extraction')
    monkeypatch.setattr(S,'preflight_environment',preflight)
    monkeypatch.setattr(P,'RunPopulations',lambda *a:calls.append('population inputs') or {})
    def extract(*args,**kwargs):
        calls.append('extraction')
        return len(REGISTRY),{'source':'fixture'}
    monkeypatch.setattr(F,'extract_paper_quantity',extract)
    report=P.run_paper_numbers(run=run,paper=paper,number_map=mapping,output=tmp/'result')
    if failure:
        assert calls==['preflight'] and report['status']=='FAIL'
        assert 'before extraction' in report['error']
    else:
        assert calls==['preflight','population inputs','extraction'] and report['status']=='PASS'


def test_structured_and_comparison_bindings_share_extraction(tmp_path):
    doc={'ranks':{'2':{'contexts':[1,2,3]}}};directory=tmp_path/'locked';directory.mkdir()
    (directory/'verdict.json').write_text(json.dumps(doc));views={};evidence={}
    prefix={'component':'locked','file':'verdict.json'}
    old={'expression':'old-reference/verdict.json#/ranks/2/contexts [length]',**prefix}
    new={'aggregate':{'operation':'length','pointer':'/ranks/2/contexts'},**prefix}
    x,_=F.extract_paper_quantity(old,'Count',tmp_path,{'locked':'locked'},{},views,evidence)
    y,_=F.extract_paper_quantity(new,'Count',tmp_path,{'locked':'locked'},{},views,evidence)
    assert x==y==3


def test_replicate_make_orders_resumable_producers_and_passes_lean_jobs(tmp_path):
    output=subprocess.run(['make','-n','replicate','DATA_OUT='+str(tmp_path/'data'),'WORKERS=48','LEAN_JOBS=4'],
        cwd=ROOT,text=True,capture_output=True,check=True).stdout
    assert output.index('reproduce all')<output.index('reproduce v25')<output.index('reproduce paper-numbers')
    assert output.count('--workers "48"')==2
    assert '--v25-output' in output and '--profile full' in output
    # Export is essential: a command-line Make variable otherwise stays hidden
    # from the pipeline's subprocess.run(['make', 'lean', ...]).
    assert 'export LEAN_JOBS' in (ROOT/'Makefile').read_text()


def test_display_map_does_not_invalidate_completed_scientific_plans():
    from born_ladder.reproduction.checkpoints import numeric_plan
    science={'path':'census.json','sha256':'scientific'}
    before={'specifications':[science]}
    after={'specifications':[science,{'path':'paper_numbers.json','sha256':'new display selectors'}]}
    assert numeric_plan(before)==numeric_plan(after)
    changed={'specifications':[{**science,'sha256':'changed scientific setting'}]}
    assert numeric_plan(before)!=numeric_plan(changed)
