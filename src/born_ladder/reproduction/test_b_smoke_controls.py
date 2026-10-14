"""Reduced synthetic incidence with the full registered fit/fold/inference kernels."""
from born_ladder.record_tests.workers import process_pool as ProcessPoolExecutor
from pathlib import Path
import json
import resource
import time

from .test_b import _json, science


def make_plant(kind, context):
    from born_ladder.record_tests import cert_v6 as C
    if kind=='pseudo_smoke':return C.G.pseudocampaign_context(0,0,context['m'])
    return C.plant(kind,0)


def fit_task(item):
    root,census,specifications,kind,context,role=item
    R,C,E,runtime=science(specifications)
    C.configure(output=Path(root),census=Path(census))
    marker=Path(root)/kind/('base_fit.json' if role is None else f'fold_{role}.json')
    if marker.exists():return C.canonical_document(marker)
    p=make_plant(kind,context)
    audit=C.control_census(p,include_test=False)
    h=context['h_c'] if kind=='pseudo_smoke' else audit['selected_h']
    if h is None:return {'kind':kind,'eligible':False,'role':role}
    d=C.record(p,h);began=time.monotonic();cpu=time.process_time()
    value=C.fit_seal_case(p,d,2,kind) if role is None else C.fold_contrast(p,d,h,2,role)
    result={'kind':kind,'role':role,'eligible':True,'h':h,'value':value,
            'wall_seconds':time.monotonic()-began,'cpu_seconds':time.process_time()-cpu,
            'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    _json(marker,result);return result


def expected_contrasts(losses, rank):
    """Name the same paired differences used by the pooled audit aggregator."""
    output={letter:losses[rival]-losses['square']
            for letter,rival in [('D','selected_classical'),('G','diagonal'),('O','selected_order')]}
    output['R']=losses['square']-losses[f'ed{rank}']
    return output


def control_chain(root,census,specifications,workers):
    R,C,E,runtime=science(specifications)
    root=Path(root);census=Path(census).resolve()
    C.configure(output=root,census=census)
    release=json.loads(census.read_bytes())
    # Cost reduction is prospectively mechanical, never selected by model loss.
    context=min(release['rank_contexts']['2'],key=lambda c:(c['m'],c['exp'],c['config'],c['k'],c['step_index']))
    kinds=(*C.FAMILIES,'pseudo_smoke')
    tasks=[(str(root),str(census),str(Path(specifications).resolve()),kind,context,role)
           for kind in kinds for role in (None,0,1,2,3,4)]
    began=time.monotonic();before=resource.getrusage(resource.RUSAGE_CHILDREN);cpu=time.process_time()
    with ProcessPoolExecutor(max_workers=workers) as pool:rows=list(pool.map(fit_task,tasks))
    bs={family:C.V.bootstrap_indices(family,root/'bootstrap_cache') for family in ('primary','reversal','order')}
    results={}
    import numpy as np
    for kind in kinds:
        group=[r for r in rows if r['kind']==kind]
        if not all(r['eligible'] for r in group):results[kind]={'status':'INELIGIBLE'};continue
        base=next(r for r in group if r['role'] is None);folds=[next(r['value'] for r in group if r['role']==f) for f in range(5)]
        path=root/kind/'rank_margins.json'
        if not path.exists():C.seal_rank_margins(path,{0:{'ranks':{'2':{'folds':folds}}}},{2:[0],3:[],4:[]})
        margins,_=C.read_sealed_margins(path,R.sha(path));margin=margins[2]
        p=make_plant(kind,context)
        scored=C.score_sealed_case(p,base['h'],2,kind,base['value'])
        law=scored['law'];signal,_=C.V.signal([law]);audit=C.control_census(p,include_test=True)
        scope=audit['lags'][str(base['h'])]['C95_test']<=.01
        inference={}
        for family,letters in [('primary',('D','G')),('reversal',('R',)),('order',('O',))]:
            blocks={letter+str(rank):(scored['contrasts'][letter] if rank==2 else None) for rank in (2,3,4) for letter in letters}
            limits={key:(.01 if key.startswith('G') else margin) for key in blocks}
            inference[family]=C.V.inference(blocks,limits,family,bs[family])
        bounds={'D':inference['primary']['bounds']['D2'],'G':inference['primary']['bounds']['G2'],
                'R':inference['reversal']['bounds']['R2'],'O':inference['order']['bounds']['O2']}
        expected=expected_contrasts(scored['expected'],2)
        rank_pass=C.rank_claim(True,scope,signal,margin,bounds)
        failed=base['value']['failed_fits']+sum(r[1] for r in folds)
        invalid=base['value']['invalid_starts']+sum(r[2] for r in folds)
        starts=base['value']['start_count']+sum(r[3] for r in folds)
        result={'smoke_nonconfirmatory':True,'reduced_incidence':'one context, model dimension two',
            'margin':margin,'scope':bool(scope),'signal':signal,'expected':expected,
            'bounds':bounds,'inference':inference,'rank_pass':rank_pass,'failed_fits':failed,
            'invalid_starts':invalid,'start_count':starts,
            'false_square_control':C.false_square_pass({2:expected},{2:margin},{2:rank_pass},invalid/starts),
            'pseudo_control':C.pseudo_rank_claim(True,scope,signal,margin,expected,bounds)}
        _json(root/kind/'smoke_control_result.json',result);results[kind]=result
    after=resource.getrusage(resource.RUSAGE_CHILDREN);wall=time.monotonic()-began
    total=time.process_time()-cpu+after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime
    result={'status':'SMOKE_NONCONFIRMATORY','context_selection':context,'controls':results,
            'wall_seconds':wall,'cpu_seconds':total,'busy_cores':total/wall,'workers':workers,
            'full_family_calls':sum(r['eligible'] for r in rows),'task_costs':rows}
    _json(root/'smoke_control_chain.json',result);return result
