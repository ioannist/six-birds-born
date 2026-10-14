"""Full-cohort arithmetic checks, separate from historical and Lean coverage."""
from collections import Counter
from fractions import Fraction as Q
from pathlib import Path

from born_ladder.archive import put
from born_ladder.robust_census import integer_record, scan_records

FIELDS = ('raw_by_state', 'package_by_state', 'joint_by_state')


def atom_classes(context, certificate):
    """Recompute constant-block rank and singular nonprojectivity exactly.

    Preserve the original atom_certificates format for existing renderers; this
    supplemental v1 table adds classifications, traces and idempotence checks.
    """
    w = list(map(Q, context['exact']['w'])); s = sum(x*x for x in w)
    if len(w) != 32 or sum(w) != 0 or s <= 0 or s != Q(context['exact']['s']):
        raise ValueError('invalid exact atom frame')
    atoms = []
    expected = []
    for field in FIELDS:
        labels = context['lens'][field]
        for label in sorted(set(labels)):
            block = [i for i, a in enumerate(labels) if a == label]
            a = sum((w[i] for i in block), Q(0)); b = sum(w[i]**2 for i in block)
            d = len(block)*b-a*a
            constant = len({w[i] for i in block}) == 1
            effect = [[Q(len(block),32),a/32],[a/s,b/s]]
            trace = effect[0][0]+effect[1][1]
            square = [[sum(effect[i][k]*effect[k][j] for k in range(2)) for j in range(2)] for i in range(2)]
            if d < 0 or (d == 0) != constant:
                raise ValueError('constant-block determinant equivalence failed')
            if constant and not (0 < trace < 1 and square != effect):
                raise ValueError('singular effect nonzero/nonprojectivity failed')
            expected.append({'context':field,'atom':label,'states':block,
                             'Gram_det_exact':str(d),'effect_exact':[[str(x) for x in row] for row in effect],
                             'positive':d>0})
            atoms.append({'context':field,'atom':label,'states':block,
                          'class':'singular' if constant else 'positive',
                          'constant_block':constant,'singleton':len(block)==1,
                          'Gram_det_exact':str(d),'trace_exact':str(trace),
                          'nonzero':trace>0,'nonprojective':square!=effect})
    cp = certificate['certificates']['C_premises']
    if expected != cp['atom_certificates'] or [cp[k] for k in ('atom_count','strict_positive_atom_count','zero_atom_count','negative_atom_count')] != [len(atoms),sum(a['class']=='positive' for a in atoms),sum(a['class']=='singular' for a in atoms),0]:
        raise ValueError('stored atom effects/counts differ')
    return {'schema':'born_census_atom_classes_v1','criterion':'singular iff w constant on active block',
            'atoms':atoms,'all_singular_nonzero_nonprojective':True}


def robust_outcomes(rows):
    gaps = [Q(r['gap_exact']) for r in rows]
    minimum = min(gaps) if gaps else None
    return {'schema':'born_census_bound_outcomes_v1','contexts':len(rows),
            'registered_bound_exact':'3/20','registered_pass':sum(g>=Q(3,20) for g in gaps),
            'registered_fail':sum(g<Q(3,20) for g in gaps),
            'registered_verdict':'PASS' if gaps and all(g>=Q(3,20) for g in gaps) else 'FAILED',
            'amended_bound_exact':'1/25','amended_pass':sum(g>=Q(1,25) for g in gaps),
            'amended_fail':sum(g<Q(1,25) for g in gaps),
            'amended_verdict':'PASS' if gaps and all(g>=Q(1,25) for g in gaps) else 'FAILED',
            'all_maximal_gaps_positive':bool(gaps) and all(g>0 for g in gaps),
            'minimum_maximum_gap_exact':str(minimum) if minimum is not None else None,
            'minimum_cases':[r['case'] for r,g in zip(rows,gaps) if g==minimum],
            'minimum_interval':{'lower':'0.0438357','upper':'0.0438358',
                'verified':minimum is not None and Q('0.0438357')<=minimum<=Q('0.0438358')},
            'cases':[{**r,'registered_verdict':'PASS' if g>=Q(3,20) else 'FAILED',
                     'amended_verdict':'PASS' if g>=Q(1,25) else 'FAILED'} for r,g in zip(rows,gaps)],
            'execution_status_is_independent':True,'formal_certification':'PENDING_SEPARATE_LEAN_PACKET'}


def diagnostic_counts(originals):
    numerical = [r.get('correspondence_status')=='PASS' for r in originals]
    symbolic = [r.get('C_premises',{}).get('status')=='PASS' for r in originals]
    return {'original_numerical_pass':sum(numerical),'original_numerical_fail':len(originals)-sum(numerical),
            'original_symbolic_pass':sum(symbolic),'original_symbolic_fail':len(originals)-sum(symbolic),
            'original_fail_both':sum(not n and not s for n,s in zip(numerical,symbolic)),
            'original_symbolic_only_fail':sum(n and not s for n,s in zip(numerical,symbolic))}


def verify_census(root, output=None):
    """Independent full-cohort external verification; no Lean coverage claim."""
    from .census import read, verify_artifacts
    from .embedding.census import extract
    from born_ladder.independent import check_context
    from born_ladder.independent_trine import check as check_trine
    root=Path(root);seal=read(root/'complete.json')
    if seal['status']!='PASS':raise ValueError('census incomplete')
    verify_artifacts(root,seal['artifacts'])
    summary=seal['summary'];base=root/summary['summary_directory']
    inventory=read(root/summary['inventory_directory']/'INVENTORY.json')
    completed=read(base/'structural_completion_results.json')
    pairs=read(base/'maximal_gap_witnesses.json')
    if not inventory or len(inventory)!=len(completed) or len(pairs)!=len(inventory):
        raise ValueError('incomplete census tables')
    totals=Counter();singular_cases=0;frames=[];seen=set()
    for i,(row,entry) in enumerate(zip(inventory,completed)):
        uid=row['unit_id'];name=Path(entry['context_directory'])
        if uid in seen or entry['unit_id']!=uid or entry['index']!=i or entry['status']!='PASS' or name.is_absolute() or '..' in name.parts:
            raise ValueError('census identity/order/status differs')
        seen.add(uid);directory=root/name
        context=read(directory/'CONTEXT.json');cert=read(directory/'structural_completion_certificate.json')
        if cert['index']!=i or cert['unit_id']!=uid or cert['overall_status']!='PASS':
            raise ValueError('invalid completion certificate')
        extract(context,cert['certificates']['strictness'])
        check_context(directory,'structural_completion_certificate.json')
        check_trine(read(directory/'six_state_exact_completion.json'))
        classes=atom_classes(context,cert)
        if read(directory/'atom_classes.json')!=classes:raise ValueError('atom classes differ')
        singular=[a for a in classes['atoms'] if a['class']=='singular'];singular_cases+=bool(singular)
        totals.update({'active_atoms':len(classes['atoms']),'singular_atoms':len(singular),
                       'positive_atoms':len(classes['atoms'])-len(singular),
                       'singular_singletons':sum(a['singleton'] for a in singular),
                       'singular_nonsingletons':sum(not a['singleton'] for a in singular)})
        frame=integer_record(context['exact']['w'],[context['lens'][f] for f in FIELDS])
        if frame!=read(directory/'integer_frame.json'):raise ValueError('integer frame differs')
        local=scan_records([frame],require_bound=False);local['cases'][0]['case']=i;local['minimum_cases']=[i]
        if local!=read(directory/'maximal_gap_witness.json'):raise ValueError('maximal-gap certificate differs')
        frames.append(frame)
        if i%100==0:print('verified census context',i,flush=True)
    expected=scan_records(frames,require_bound=False)['cases']
    if expected!=pairs:raise ValueError('maximal-gap summary differs')
    outcomes=robust_outcomes(pairs)
    if read(base/'robust_bound_outcomes.json')!=outcomes:raise ValueError('bound outcomes differ')
    report={'schema':'born_full_census_external_verification_v1','status':'PASS','contexts':len(inventory),
            **totals,'singular_cases':singular_cases,'all_singular_nonzero_nonprojective':True,
            'registered_bound_pass':outcomes['registered_pass'],'registered_bound_fail':outcomes['registered_fail'],
            'amended_bound_pass':outcomes['amended_pass'],'amended_bound_fail':outcomes['amended_fail'],
            'minimum_interval':outcomes['minimum_interval'],'formal_certification':'PENDING_SEPARATE_LEAN_PACKET'}
    if output:put(output,report)
    return report
