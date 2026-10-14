"""Small synthetic conformance chain; never certifies registered Test B.

Full 96-start fit budgets and sample designs are retained. Counts and incidence
are deliberately reduced and every result is marked nonconfirmatory.
"""
from born_ladder.record_tests.workers import process_pool as ProcessPoolExecutor
import json
from pathlib import Path
import resource
import time

from .test_b import _json, science
from .runs import exclusive_output, validate_output


def _fidelity(item):
    kind, root, census, specifications = item
    from born_ladder.record_tests import cert_v6 as C
    science(specifications)
    C.configure(output=Path(root),census=Path(census))
    folder=Path(root)/kind;folder.mkdir(exist_ok=True)
    p=C.plant(kind,0);committed=C.draw_digest(p)
    start=time.monotonic();cpu=time.process_time()
    row=C.fidelity_case((0,committed,kind))
    return {**row,'cpu_seconds':time.process_time()-cpu,'wall_seconds':time.monotonic()-start,
            'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def smoke_certification(*, census, output, specifications='specifications', workers=1):
    if workers<1:raise ValueError('--workers must be positive')
    root=validate_output(output,Path(specifications).resolve().parent);root.mkdir(parents=True,exist_ok=True)
    R,C,E,runtime=science(specifications)
    with exclusive_output(root):
        if (root/'smoke_complete.json').exists():
            old=C.canonical_document(root/'smoke_complete.json')
            if old.get('schema')=='test_b_smoke_complete_v2':return old
            (root/'smoke_complete.json').rename(root/'smoke_logic_examples.json')
        census=Path(census).resolve();C.configure(output=root,census=census)
        start=time.monotonic();rows=[]
        pending=[]
        for kind in ('fidelity',*C.FAMILIES):
            file=root/kind/'smoke_result.json'
            if file.exists():rows.append(C.canonical_document(file))
            else:pending.append((kind,str(root),str(census),str(Path(specifications).resolve())))
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for row in pool.map(_fidelity,pending):
                _json(root/row['family']/'smoke_result.json',row);rows.append(row)
        split=C.plant('split_state',0);audit=C.fixed_census(split)
        _json(root/'split_state/smoke_result.json',{'index':0,'C95_train':audit['C95_train'],
            'pass':all(audit['lags'][str(h)]['C95_train']>.01 for h in C.LAGS)})
        # Reconstruct a census-matched pseudo plant, using the real incidence and
        # lag in its record context; no real locked-test path is opened.
        release=json.loads(census.read_bytes());context=release['rank_contexts']['2'][0]
        p=C.G.pseudocampaign_context(0,0,context['m']);d=C.record(p,context['h_c'])
        _json(root/'pseudo_input.json',{'context':d.context,'m':d.m,'h_c':context['h_c'],
            'table_hash':d.table_hash,'draw':C.draw_digest(p)})
        # Boundary truth table calls the actual registered decision helpers.
        # It is a conformance test, not an empirical synthetic-campaign verdict.
        margins={2:.01};negative={2:{'D':0.,'G':0.,'R':0.,'O':0.}}
        positive={'D':.02,'G':.02,'R':0.,'O':.02}
        checks={'fidelity_accept':C.fidelity_pass(200,200,180,180,0,200*E.V5_STARTS),
            'fidelity_reject':not C.fidelity_pass(200,200,179,180,0,200*E.V5_STARTS),
            'no_false_square':C.false_square_pass(negative,margins,{2:False},0.),
            'false_square_reject':not C.false_square_pass(negative,margins,{2:True},0.),
            'split_accept':C.split_pass(95),'split_reject':not C.split_pass(94),
            'pseudo_accept':C.pseudo_pass(100,80,0.),'pseudo_reject':not C.pseudo_pass(100,79,0.),
            'all_rank_controls_accept':C.pseudo_rank_claim(True,True,.02,.01,positive,positive),
            'scope_reject':not C.rank_claim(True,False,.02,.01,positive),
            'signal_reject':not C.rank_claim(True,True,.01,.01,positive),
            'empty_reject':not C.rank_claim(False,True,.02,.01,positive),
            'normalization_gate_fits_finite':all(row['invalid_starts']==0 for row in rows)}
        from .test_b_smoke_controls import control_chain
        controls=control_chain(root,census,specifications,workers)
        result={'schema':'test_b_smoke_complete_v2','status':'SMOKE_NONCONFIRMATORY','smoke_nonconfirmatory':True,
            'runtime':runtime,'workers':workers,'fidelity_examples':rows,'decision_helper_checks':checks,
            'all_decision_checks':all(checks.values()),('full_budget_control_chain' if E.V5_STARTS==96 and E.V5_POLISH_ITER==500 else 'reduced_budget_control_chain'):controls,
            'fit_budgets':{'starts':E.V5_STARTS,'warm_iterations':E.V5_WARM_ITER,'polish_iterations':E.V5_POLISH_ITER},'wall_seconds':time.monotonic()-start,
            'summed_fit_cpu_seconds':sum(row.get('cpu_seconds',0) for row in rows),
            'not_executed':['full 200/100 fidelity populations','100-case pooled false-square populations',
                '100 complete-incidence census-matched campaigns'],
            'locked_real_test_sampled_or_opened':False}
        _json(root/'smoke_complete.json',result);return result
