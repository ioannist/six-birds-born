"""Regression checks for scientific shortfalls and checked amendment resume."""
import copy
import json
from fractions import Fraction as Q
from pathlib import Path

import pytest

from born_ladder.archive import put
from born_ladder.robust_census import integer_record, scan_records
from born_ladder.reproduction.census_extension import atom_classes, robust_outcomes, diagnostic_counts
from born_ladder.reproduction.census import recover_completed_constructions, amendment_resume_plan
from born_ladder.reproduction.runs import Manifest
from born_ladder.reproduction.units import artifacts


def case():
    w=[Q(i)-Q(31,2) for i in range(32)];s=sum(x*x for x in w)
    labels=[[int(i>=16) for i in range(32)],[i%2 for i in range(32)],
            [2*int(i>=16)+i%2 for i in range(32)]]
    context={'exact':{'w':list(map(str,w)),'s':str(s)},
             'lens':dict(zip(('raw_by_state','package_by_state','joint_by_state'),labels))}
    atoms=[]
    for field,lab in context['lens'].items():
        for label in sorted(set(lab)):
            block=[i for i,a in enumerate(lab) if a==label]
            a=sum(w[i] for i in block);b=sum(w[i]**2 for i in block)
            det=len(block)*b-a*a
            atoms.append({'context':field,'atom':label,'states':block,'Gram_det_exact':str(det),
                          'effect_exact':[[str(Q(len(block),32)),str(a/32)],[str(a/s),str(b/s)]],'positive':det>0})
    cert={'overall_status':'PASS','unit_id':'synthetic','index':0,'certificates':{
        'C_premises':{'status':'PASS','atom_certificates':atoms,'atom_count':len(atoms),
                      'strict_positive_atom_count':sum(a['positive'] for a in atoms),
                      'zero_atom_count':sum(not a['positive'] for a in atoms),'negative_atom_count':0},
        'correspondence':{'status':'PASS','constructor_categorical_shape_parity':True,'rounded_nonvanishing':True,
                          **{k:'0' for k in ('native_preparation_replay_maximum_error_exact','uniform_projector_TV_bound_exact',
                             'own_input_exact_source_vs_landed_maximum_error','own_input_rounded_evaluation_error','native_numpy_vs_landed_fsum_maximum_error')}}}}
    return context,cert


def test_registered_shortfall_is_separate_from_amended_bound():
    result=robust_outcomes([{'case':0,'gap_exact':'1/10'},{'case':1,'gap_exact':'1/5'}])
    assert result['registered_verdict']=='FAILED' and (result['registered_pass'],result['registered_fail'])==(1,1)
    assert result['amended_verdict']=='PASS' and result['amended_pass']==2
    assert result['cases'][0]['registered_verdict']=='FAILED'


def test_non_singleton_constant_atom_is_singular_nonprojective():
    context,cert=case()
    # Two identical w-values in one block of a centered, nonconstant frame.
    context['exact']['w']=['0','0','-1','1']+['0']*28;context['exact']['s']='2'
    context['lens']={f:[0,0]+[1]*30 for f in context['lens']}
    atoms=[]
    for field in context['lens']:
        atoms.extend([{'context':field,'atom':0,'states':[0,1],'Gram_det_exact':'0',
                      'effect_exact':[['1/16','0'],['0','0']],'positive':False},
                     {'context':field,'atom':1,'states':list(range(2,32)),'Gram_det_exact':'60',
                      'effect_exact':[['15/16','0'],['0','1']],'positive':True}])
    cert['certificates']['C_premises'].update(atom_certificates=atoms,atom_count=6,
        strict_positive_atom_count=3,zero_atom_count=3)
    result=atom_classes(context,cert)
    singular=[a for a in result['atoms'] if a['class']=='singular']
    assert len(singular)==3 and all(not a['singleton'] and a['nonzero'] and a['nonprojective'] for a in singular)
    bad=copy.deepcopy(cert);bad['certificates']['C_premises']['atom_certificates'][0]['positive']=True
    with pytest.raises(ValueError,match='stored atom'):atom_classes(context,bad)


def test_symbolic_failure_overlap_is_not_priority_count():
    rows=[{'correspondence_status':n,'C_premises':{'status':s}} for n,s in
          [('PASS','PASS'),('FAILED','FAILED'),('PASS','FAILED'),('FAILED','PASS')]]
    result=diagnostic_counts(rows)
    assert result['original_symbolic_fail']==2 and result['original_symbolic_only_fail']==1 and result['original_fail_both']==1


def recovery(root):
    context,cert=case();directory=root/'attempt/contexts/synthetic';directory.mkdir(parents=True)
    frame=integer_record(context['exact']['w'],list(context['lens'].values()))
    for name,data in [('CONTEXT.json',context),('structural_completion_certificate.json',cert),
                      ('integer_frame.json',frame),('maximal_gap_witness.json',scan_records([frame],require_bound=False))]:
        put(directory/name,data)
    manifest=Manifest(root)
    manifest.append({'event':'finished','invocation_id':'synthetic','status':'failed',
        'completion_status':'PASS','directory':'attempt','context_directory':'contexts/synthetic',
        'failures':['maximal-gap bound 3/20 not established'],'artifacts':artifacts(root/'attempt',root)})
    return manifest,directory


def test_recovery_preserves_evidence_and_is_idempotent(tmp_path):
    manifest,directory=recovery(tmp_path);before=manifest.path.read_bytes()
    assert recover_completed_constructions(tmp_path,manifest)==1
    assert manifest.path.read_bytes().startswith(before) and len(manifest.completed())==1
    assert recover_completed_constructions(tmp_path,manifest)==0
    assert (directory/'atom_classes.json').exists()


def test_corrupt_recovery_artifact_blocks(tmp_path):
    manifest,directory=recovery(tmp_path)
    (directory/'integer_frame.json').write_text('{}')
    with pytest.raises(ValueError):recover_completed_constructions(tmp_path,manifest)
    assert not manifest.completed()


def test_actual_failure_is_not_reclassified(tmp_path):
    manifest,_=recovery(tmp_path);manifest.rows[0]['failures']=['invalid certificate']
    assert recover_completed_constructions(tmp_path,manifest)==0


def test_resume_projection_only_ignores_adapter_location_and_amendment():
    old={'logical_to_execution_files':{'kernel_adapters/a':'old/a','units':'same'},'specifications':['same']}
    new={**old,'logical_to_execution_files':{'kernel_adapters/a':'new/a','units':'same'},'census_amendment':{'sha256':'a'}}
    assert amendment_resume_plan(old)==amendment_resume_plan(new)
    new['specifications']=['changed']
    assert amendment_resume_plan(old)!=amendment_resume_plan(new)


def test_constructor_shortfall_remains_completed(tmp_path,monkeypatch):
    from born_ladder.reproduction import census as C
    context,cert=case()
    def construct(index,row,input_view,output,*args):
        directory=Path(output)/'contexts'/row['unit_id'];directory.mkdir(parents=True)
        put(directory/'CONTEXT.json',context)
        return cert
    monkeypatch.setattr(C,'construct_context',construct)
    monkeypatch.setattr(C,'original_status',lambda *a:({'status':'PASS','classification':'synthetic'},None))
    monkeypatch.setattr(C,'scan_records',lambda *a,**k:{'status':'FAILED','cases':[{'case':0,'gap_exact':'1/10'}]})
    result=C.construct_one({'index':0,'row':{'unit_id':'synthetic'},'input_view':{},'output':str(tmp_path),'specifications':'unused'})
    assert result['status']=='completed' and result['completion_status']=='PASS' and result['robust_status']=='FAILED'
    assert result['failures']==[]


@pytest.mark.parametrize('failed,exit_status',[(0,0),(1,1)])
def test_cli_exit_depends_on_completion_not_threshold(monkeypatch,failed,exit_status):
    from born_ladder.__main__ import main
    from born_ladder.reproduction import census,stage_environment
    monkeypatch.setattr(stage_environment,'ensure_environment',lambda *a:None)
    monkeypatch.setattr(census,'run_census',lambda **k:{'failed':failed,'registered_robust_fail':117,'registered_robust_verdict':'FAILED'})
    assert main(['reproduce','census','--units','unused','--runs','unused','--output','unused'])==exit_status


@pytest.mark.parametrize('scale',[Q(1),Q(1,2**1074)])
def test_independent_gram_contraction_matches_expanded_product(scale):
    from born_ladder.independent import recompute
    w=[x*scale for x in (-3,-1,1,3)];s=sum(x*x for x in w);n=4
    projector=[[Q(1,n)+a*b/s for b in w] for a in w]
    context={'born':{'sym_eigvec_basis':[list(map(str,w))],'starts':list(range(n)),'tau':0,'p_theory':[1/n]*n},
        'kernel':[[float(i==j) for j in range(n)] for i in range(n)],
        'lens':{f:[0,0,1,1] for f in ('raw_by_state','package_by_state','joint_by_state')},
        'archived_unit_structural':{'raw':{'basis_and_projector_inputs':{'projector':[[float(x) for x in row] for row in projector]}}}}
    result=recompute(context)
    assert result['P']==[[str(x) for x in row] for row in projector]
    assert all(sum(projector[i][k]*projector[k][j] for k in range(n))==projector[i][j] for i in range(n) for j in range(n))


def test_full_cohort_pipeline_cannot_accept_not_applicable(tmp_path,monkeypatch):
    import subprocess
    from born_ladder.reproduction import pipeline as P
    monkeypatch.setattr(P,'validate_output',lambda path,*a:Path(path))
    def child(argv,**kwargs):
        if 'lean-inputs' in argv:
            directory=tmp_path/'lean';directory.mkdir()
            (directory/'formal_coverage.json').write_text(json.dumps({'status':'NOT_APPLICABLE','census_cases':2122}))
        return subprocess.CompletedProcess(argv,0)
    monkeypatch.setattr(P.subprocess,'run',child)
    with pytest.raises(ValueError,match='requires Lean certification'):
        P.run_all(output=tmp_path,profile='full',specifications=Path(__file__).resolve().parents[2]/'specifications')
