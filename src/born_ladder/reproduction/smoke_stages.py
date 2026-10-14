"""Explicit reduced conformance stages. No historical or full-cohort verdicts.

All numerical algorithms are shared. The shipped reduced contract changes only
incidence and work budgets; the registered/full command never imports this file.
"""
from pathlib import Path
import json
import math
import shutil
from born_ladder.archive import put


def population_result(inputs,evaluation,draws):
    import numpy as np
    from born_ladder.snapshot.g2a import _bca_summary,_conditional_sign_p,_holm
    from born_ladder.snapshot.statistics_helpers import _conditional_sign_p_exact
    from .evaluation import PopulationSpecification
    spec=PopulationSpecification('specifications',evaluation)
    inference=spec.get('/inference')
    estimates={};p={}
    for view,values in sorted(inputs.items()):
        x=np.asarray(values,dtype=float)
        # Fixed deterministic reduced membership, shared across the two maps.
        # Draws are shipped in the output for exact reconstruction.
        indices=np.random.default_rng(601).integers(0,len(x),size=(draws,len(x)))
        boot=[float(np.mean(x[ix])) for ix in indices]
        result=_bca_summary(x.tolist(),boot,inference)
        sign=(_conditional_sign_p if evaluation=='competitor' else _conditional_sign_p_exact)(x.tolist())
        p[view]=sign[1]
        estimates[view]={'point':float(np.mean(x)),'bca':result,'sign_two_sided':sign[0],'sign_one_sided':sign[1]}
    return {'schema':'born_reduced_population_kernel_v1','profile':'smoke','evaluation':evaluation,
        'seed_vectors':inputs,'bootstrap_draws':draws,'estimates':estimates,'holm':_holm(p),
        'registered_verdict_issued':False,'disposition':'REDUCED_CONFORMANCE_ONLY',
        'not_executed':['complete registered population admission','registered hierarchy and sensitivities','20000-draw population BCa']}


def population(pipeline,output,evaluation,specifications):
    from .census import collection_inputs
    root,parent,records_path,name,files,*_=collection_inputs(Path(pipeline)/'units/smoke',evaluation)
    rows=[json.loads(line) for line in Path(files[name]).open()]
    values={}
    for kind in ('raw','pkg'):
        group=[r for r in rows if r.get('eligibility') and r.get('_derived_kind',None)==kind]
        if not group:group=[r for r in rows if r.get('eligibility') and r.get('partition')==kind]
        if not group:
            import hashlib
            group=[r for r in rows if r.get('eligibility') and r['kind_cell_id']==hashlib.sha256((r['unit_id']+kind).encode()).hexdigest()]
        if not group:raise ValueError('no reduced eligible '+kind+' units')
        center=sum(r['dtv_loss']['q_diag']-r['dtv_loss']['q_full'] for r in group)/len(group)
        values[kind]=[center+(i-1.5)*.001 for i in range(4)]
    contract=json.loads((Path(specifications)/'reproduction_smoke.json').read_bytes())
    doc=population_result(values,evaluation,contract['population']['bootstrap_draws'])
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    from .test_b import _json
    _json(output/'smoke_inference.json',doc);return doc


def verify_population(doc):
    from born_ladder.record_tests.verify import differences
    expected=population_result(doc['seed_vectors'],doc['evaluation'],doc['bootstrap_draws'])
    # Canonical JSON erases tuple/list representation only, not any numeric bit.
    if json.loads(json.dumps(expected))!=doc:raise ValueError('reduced population kernels differ')
    return True


def lean(pipeline,output):
    from .lean_inputs import run_lean_inputs
    root=Path(pipeline)
    return run_lean_inputs(census=root/'census',worked_cases=root/'worked',
                           output=output,render_registered=False)


def test_b(pipeline,output,specifications,workers):
    from . import test_b as B
    from born_ladder.record_tests import real_v6 as R, cert_v6 as C, estimators as E
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    reduced=json.loads((Path(specifications)/'reproduction_smoke.json').read_bytes())['test_b']
    # Check the computing runtime/registered contract before applying declared
    # reduced optimizer budgets. Their scope is this separate smoke process.
    B.science(specifications)
    overlay=root/'smoke_specifications'
    if not overlay.exists():shutil.copytree(specifications,overlay)
    original=json.loads((Path(specifications)/'test_b.json').read_bytes())
    for key in ('starts','warm_iterations','polish_iterations','checkpoints'):original['fit'][key]=reduced[key]
    contract=overlay/'test_b.json'
    if (root/'setup.json').exists() and json.loads(contract.read_bytes())!=original:
        raise ValueError('reduced fitting budget changed on resume')
    contract.write_text(json.dumps(original,indent=2,sort_keys=True)+'\n')
    E.V5_STARTS=reduced['starts'];E.V5_WARM_ITER=reduced['warm_iterations'];E.V5_POLISH_ITER=reduced['polish_iterations'];E.CHECKPOINTS=tuple(reduced['checkpoints'])
    E.fit_model.__defaults__=(None,E.V5_STARTS,E.V5_POLISH_ITER)
    E.fit_family.__defaults__=(E.V5_STARTS,E.V5_POLISH_ITER)
    E.fit_diagonal.__defaults__=(E.V5_STARTS,E.V5_POLISH_ITER)
    specs=overlay.resolve()
    B.inventory(output=root,runs=Path(pipeline)/'runs/smoke',specifications=specs,smoke=True)
    B.census_stage(root,workers=workers,smoke=True)
    from .test_b_smoke import smoke_certification
    cert=smoke_certification(census=root/'census/eligibility.json',output=root/'certification',specifications=specs,workers=workers)
    B.sample_stage(root,specifications=specs,workers=workers,sampler='vendor/pica/target/release/test-b-sampler',smoke=True,only=[])
    B.fit_stage(root,specifications=specs,workers=workers)
    if (root/'prediction_seal_manifest.json').exists():return C.canonical_document(root/'prediction_seal_manifest.json')
    entries=R.eligible_entries(root,C.canonical_document(root/'setup.json'))
    from born_ladder.record_tests.workers import process_pool as ProcessPoolExecutor
    tasks=[(str(root),e,r,k) for e,r in entries for k in range(reduced['literal_relabels_per_context_dimension'])]
    with ProcessPoolExecutor(max_workers=workers) as pool:refits=list(pool.map(R.literal_relabel_case,tasks))
    B._json(root/'controls/reduced_literal_refits.json',{'profile':'smoke','rows':refits,'required_full_count':22})
    B._json(root/'controls/erasure.json',{'status':'NOT_COMPUTED','diagnostic_only':True,'refits':0,'changes_gate_or_verdict':False})
    # The training audit uses the same helper and bootstrap indices; reduced
    # campaign count is declared and does not satisfy the registered 1000 audit.
    import numpy as np
    margins,_=C.read_sealed_margins(root/'fits/rank_margins.json',R.sha(root/'fits/rank_margins.json'))
    vectors={}
    for rank in (2,3,4):
        contexts=[]
        for entry,r in entries:
            if r!=rank:continue
            letters={x:[] for x in 'DGRO'}
            for fold in range(5):
                doc=C.canonical_document(root/'fits/original'/f'{R.fit_identity(entry)}_r{rank}_fold{fold}'/'outer_contrasts.json')
                for x in letters:letters[x].extend(doc['contrasts'][x])
            contexts.append(letters)
        if contexts:vectors[rank]={x:np.mean([c[x] for c in contexts],axis=0) for x in 'DGRO'}
    with ProcessPoolExecutor(max_workers=workers,initializer=R.training_audit_initialize,initargs=(str(root/'controls/audit_cache'),)) as pool:
        audit=list(pool.map(R.training_audit_case,[(i,vectors,margins) for i in range(reduced['training_audit_draws'])]))
    B._json(root/'controls/reduced_training_audit.json',{'profile':'smoke','rows':audit})
    R.commit_phase(root,'seal',[p for p in (root/'controls').rglob('*') if p.is_file()],
        {'status':'SMOKE_NONCONFIRMATORY','locked_test_sampled_or_opened':False,'reduced_budgets':reduced})
    files={}
    for phase in R.PHASES:
        part=R.verify_phase(root,phase);files.update(part['files']);files[f'{phase}.commit.json']=R.sha(root/f'{phase}.commit.json')
    seal={'schema':'test_b_v6_1_p6_required_seal_v1','spec_sha256':R.SPEC_HASH,'setup_sha256':R.sha(root/'setup.json'),
        'subset_nonconfirmatory':True,'files':files,'rank_context_counts':{str(r):sum(rank==r for _,rank in entries) for r in (2,3,4)},
        'locked_test_sampled_or_opened':False,'mandatory_order_completed':None,'structural_erasure':'NOT_COMPUTED','control_rules':R.CONTROL_RULES}
    B._json(root/'prediction_seal_manifest.json',seal);return seal
