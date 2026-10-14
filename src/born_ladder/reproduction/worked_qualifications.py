"""Semantic obligations for retained worked qualifications (Eddy round 8).

These are validation checks, not literal historical matches. Method and
boundary declarations have explicit dispositions and zero reproduction credit.
"""
from fractions import Fraction as Q
import hashlib
import json
from pathlib import Path

from born_ladder import arithmetic as A
from born_ladder.claim_checks import parent_certificate, non_trace_fragment
from born_ladder.instruments import Instrument, FIELDS, tests
from .worked_cases import read, frame, captured_context, carrier_certificate, selected_witness
from .worked_science import barycenter, density, finite_certificate, sequential_certificate
from born_ladder.transport import Transport


# Fixed retained schema: equality includes types, even for documentary flags.
QUALIFICATIONS = (
    ('E1/D_certificate.json/status', 'DENSITY-BASED SEQUENTIAL VALUATION REFUTED', 'SEMANTIC_PASS'),
    ('E2/C_certificate.json/status', 'CONDITIONAL ANALYTIC EVENT ADMISSION / UNIFORM SEQUENTIAL DENSITY VALUATION BY CONSTRUCTION', 'SEMANTIC_PASS'),
    ('E3/C1_certificate.json/informational_complete_exact', True, 'SEMANTIC_PASS'),
    ('E3/C1_certificate.json/status_current', 'FINITE POLYTOPE CHARACTERIZATION; NON-TRACE STATES EXIST (GEOMETRIC PROOF)', 'NON_TRACE_EXISTENCE_REPRODUCED; POLYTOPE_CHARACTERIZATION_RETAINED'),
    ('E3/C1_certificate.json/status_generated', 'UNRESOLVED: all-state extension/classification theorem missing', 'DECLARED_BOUNDARY_UNCHANGED'),
    ('E3/C1_certificate.json/vertices_enumerated', False, 'HISTORICAL_METHOD_ONLY'),
    ('RI/B_certificate.json/lens_frame_unit_joins', True, 'SEMANTIC_PASS'),
    ('RI/B_certificate.json/status', 'PASS', 'SEMANTIC_PASS'),
    ('RI/initial_strictness_certificate.json/status', 'CERTIFIED STRICT REFINEMENT', 'SEMANTIC_PASS'),
    ('RI/six_state_certificate.json/orthonormal_and_G_routes_independent', True, 'HISTORICAL_METHOD_QUALIFICATION; ROUTE_AGREEMENT_RECHECKED'),
    ('E1/pair_certificate/status', 'EXACT EQUALITY AND REACHABILITY', 'SEMANTIC_PASS'),
    ('RI/strictness/certificate/status', 'CERTIFIED STRICT REFINEMENT', 'SEMANTIC_PASS'),
)


def retained_values(reference):
    out = {}
    for path, _, _ in QUALIFICATIONS:
        if path.startswith('E1/pair_certificate/'):
            value = read(Path(reference)/'E1/D_certificate.json')['pair_certificate']['status']
        elif path.startswith('RI/strictness/certificate/'):
            value = read(Path(reference)/'RI/initial_strictness_certificate.json')['certificate']['status']
        else:
            file, key = path.rsplit('/', 1)
            document = read(Path(reference)/file)
            if key not in document:continue
            value = document[key]
        out[path] = value
    return out


def pair_checks(context, pair):
    """Exact mathematical preparation reachability, never native formation."""
    w, s, P, _ = frame(context)
    ensembles = []
    for side in ('left', 'right'):
        rows = pair[side]
        if not isinstance(rows, list) or len(rows) != 2 or any(
                not isinstance(row, list) or len(row) != 2 or
                any(type(x) is not str or str(Q(x)) != x for x in row) for row in rows):
            raise ValueError('ensemble requires canonical exact coordinate/weight strings')
        ens = [(Q(l), Q(weight)) for l, weight in rows]
        if any(weight <= 0 for _, weight in ens) or sum(z for _, z in ens) != 1:
            raise ValueError('ensemble weights are not positive normalized')
        for l, _ in ens:
            a = [1+l*x for x in w]
            if min(a) <= 0:
                raise ValueError('non-positive 1 + lambda*w')
            den = 32+s*l*l
            p = [x*x/den for x in a]
            if sum(p) != 1 or A.mv(P, a) != a:
                raise ValueError('preparation is not normalized or not in the retained frame')
            if density(w, l) != [[a0*a1*g/(32+s*l*l) for a1,g in zip((Q(1),l),(Q(32),s))]
                                for a0 in (Q(1),l)]:
                raise ValueError('preparation does not encode the stated ray')
        ensembles.append(ens)
    left, right = [barycenter(w, ens) for ens in ensembles]
    if left != right or A.qserial(left) != pair['coordinate_barycenter']:
        raise ValueError('ensemble barycenter differs')
    if type(pair['full_barycenter_original_parity']) is not bool or not pair['full_barycenter_original_parity']:
        raise ValueError('barycenter parity is not true')
    m = Instrument(context, w, s, P, frame(context)[3])
    for part in m.parts.values():
        for block in part.values():
            reads = [sum(z*A.trace(A.matmul(density(w,l),m.C[block])) for l,z in ens) for ens in ensembles]
            if reads[0] != reads[1]:raise ValueError('initial lens reads differ')
    if type(pair['first_read_all_lenses_equal']) is not bool or not pair['first_read_all_lenses_equal']:
        raise ValueError('initial-read parity is not true')
    return {'ensembles': ensembles, 'barycenter': A.qserial(left),
            'minimum_positive_root': str(min(1+l*x for ens in ensembles for l,_ in ens for x in w)),
            'preparations_normalized': True, 'exact_equal_barycenters': True, 'initial_reads_equal': True}


def basis_determinant(context, basis):
    w,s,P,K = frame(context);m=Instrument(context,w,s,P,K)
    bound=[A.eye(),m.C[m.parts['joint_by_state'][0]],m.C[m.parts['joint_by_state'][1]]]
    if basis != A.qserial(bound):raise ValueError('basis is not source-bound (including exact representation)')
    a,b,c=[[E[0][0],E[1][1],E[0][1]] for E in bound]
    determinant=a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])
    if not determinant:raise ValueError('zero coordinate determinant')
    return str(determinant)


def check_program_proofs(lean_root):
    """Applicable uniform proofs; fresh kernel/source audit is the Lean stage.

    The local receipt/membership checks cannot substitute for that stage.
    """
    root=Path(lean_root);build=read(root/'build_receipt.json');audit=read(root/'audit_receipt.json')
    names=('program_effects_sum','program_mass_sum','word_effect_psd','grouped_effect_is_effect',
           'grouping_mass','grouping_psd','density_sufficiency')
    if build.get('status')!='PASS' or audit.get('status')!='PASS' or audit.get('fresh') is not True or audit.get('forbidden')!={}:
        raise ValueError('uniform-program build/audit receipt is invalid')
    for name in names:
        axioms=audit['dependencies'].get('BornCalculus.'+name)
        if axioms is None:raise KeyError('required uniform-program proof: '+name)
        if not isinstance(axioms,list) or not set(axioms)<={'Classical.choice','Quot.sound','propext'}:
            raise ValueError('uniform-program proof uses forbidden axioms')
    return {'endpoints':['BornCalculus.'+n for n in names],
            'fresh_kernel_source_validation_dependency':'lean comparison stage',
            'scope':'adopted density model; fixed 12 complete tests, 72 words, 2340 subsets; no generated-H or native admission'}


def semantic_evidence(c, generated, *, source_runs=None, specifications='specifications', lean_root=None):
    """Evaluate each independent obligation once, with failures kept local."""
    generated=Path(generated);contexts={name:read(generated/name/'CONTEXT.json') for name in ('original','selected')}
    certs={name:read(generated/name/'certificates.json') for name in contexts}
    contract=read(Path(specifications)/'worked_cases.json');evidence={}
    failures=lambda:sum(row.get('failed',len(row.get('differences',[]))) for row in c.groups.values())
    def run(name, fn):
        before=failures()
        try:
            value=fn();evidence[name]={'status':'PASS','checks':value}
            if failures()>before:evidence[name]['status']='FAIL'
        except (FileNotFoundError,KeyError) as e:
            evidence[name]={'status':'UNRESOLVED','reason':str(e)}
        except (ValueError,TypeError,IndexError,ZeroDivisionError,AssertionError,ArithmeticError) as e:
            evidence[name]={'status':'FAIL','reason':str(e)}
        if evidence[name]['status']=='FAIL':c.compare('worked_semantic_'+name,False,True,str(evidence[name].get('reason','semantic values differ')))
        return evidence[name]
    original=contexts['original'];selected=contexts['selected'];o=certs['original'];s=certs['selected']
    def compare(group,a,b):c.compare('worked_semantic_'+group,a,b)
    def pair():
        value=pair_checks(original,o['ensemble']['pair_certificate'])
        charts=[[str(l) for l,_ in ens] for ens in value['ensembles']]
        compare('pair',charts,contract['ensemble_frame_charts'])
        return {k:v for k,v in value.items() if k!='ensembles'}
    run('pair',pair)
    def completion():
        w,ss,P,K=frame(original);t=Transport(original,w,ss,P,K)
        recomputed=sequential_certificate(t,contract['ensemble_frame_charts'])
        compare('completion',o['ensemble'],recomputed)
        witness=o['ensemble']['witness'];gap=witness['left_minus_right']
        if not (Q(gap['lo'])>0 or Q(gap['hi'])<0):raise ValueError('completion-word gap is not certified nonzero')
        return {'word':witness['word'],'gap':gap,'scope':'registered E1 completion apparatus; not the adopted principal-root instrument'}
    run('completion',completion)
    def basis():
        det=basis_determinant(original,o['finite_family']['basis_exact'])
        compare('basis',o['finite_family']['non_density']['coordinate_determinant_exact'],det)
        return {'coordinate_determinant_exact':det,'informational_complete_exact':True}
    run('basis',basis)
    def finite():
        w,ss,P,K=frame(original);m=Instrument(original,w,ss,P,K)
        pairs=pair_checks(original,o['ensemble']['pair_certificate'])['ensembles']
        recomputed=finite_certificate(m,pairs)
        compare('finite',o['finite_events'],recomputed)
        compare('finite',o['finite_family']['parent'],parent_certificate(m))
        programs=[{'contexts':list(cs),'words':[list(word) for word in words],'events':1<<len(words)} for cs,words in tests(m)]
        compare('finite',o['finite_family']['programs'],programs)
        return {'tests':len(programs),'words':recomputed['atomic_word_count'],'subsets':recomputed['event_count'],
                'positive_effects_complete_normalized_additive':True,'uniform_program_proofs':check_program_proofs(lean_root or generated.parent/'lean')}
    run('finite',finite)
    def non_density():
        w,ss,P,K=frame(original);m=Instrument(original,w,ss,P,K)
        recomputed=non_trace_fragment(m,o['finite_family']['basis_exact'])
        compare('non_density',o['finite_family']['non_density'],recomputed)
        return recomputed
    run('non_density',non_density)
    def joins():
        paths=source_runs if source_runs is not None else [generated.parent/'runs/worked']
        captured=captured_context(paths,contract['contexts']['selected'],specifications,contract['capture_grid'])
        w,ss,P,_=frame(captured);captured['exact']={'w':A.qserial(w),'s':str(ss),'projector':A.qserial(P)}
        # This strict-float group binds ALL emitted fields, K, ordered support,
        # resolution, frame and maps. A carrier calculation alone cannot pass.
        c.compare('source_scientific_inputs',selected,captured,'captured_execution_join')
        return {'execution':captured['identity'],'source_runs':[str(p) for p in paths],
                'captured_K_mode_ordered_support_maps_and_preparation':True}
    run('joins',joins)
    def carrier():
        w,ss,P,K=frame(selected);m=Instrument(selected,w,ss,P,K)
        recomputed=carrier_certificate(m);compare('carrier',s['carrier'],recomputed)
        compare('carrier',s['parent'],parent_certificate(m))
        return {'rank':recomputed['exact_source_rank'],'scope':'adopted carrier/input result; no native-formation promotion'}
    run('carrier',carrier)
    def strictness():
        w,ss,P,K=frame(selected);m=Instrument(selected,w,ss,P,K)
        recomputed=A.qserial(selected_witness(m));compare('strictness',s['strictness'],recomputed)
        witness=recomputed['certificate']
        if witness['left_old_view']!=witness['right_old_view'] or not witness['density_separation'] or not witness['readout_splits']:
            raise ValueError('registered strict refinement not established')
        return {'witness_id':hashlib.sha256(json.dumps(recomputed,sort_keys=True).encode()).hexdigest(),
                'point_indices':witness['point_indices'],'equal_complete_supplied_old_views':True,
                'unequal_densities_and_separating_readouts':True,'independent_experiments':1}
    run('strictness',strictness)
    routes={name:row for name,row in c.groups.items() if name.startswith('RI_six_')}
    evidence['routes']={'status':'PASS' if routes and not any(row.get('failed',len(row.get('differences',[]))) for row in routes.values()) else 'UNRESOLVED' if not routes else 'FAIL',
        'checks':{'route_agreement_groups':list(routes),'method_independence_reproduced':False,
                  'scope':'state, YES-table, mixture and conjugacy agreement; no separate regenerated constructions credited'}}
    return evidence


ROW_DEPENDENCIES=(('pair','completion'),('finite',),('basis',),('basis','non_density'),('non_density',),(),
                  ('joins',),('joins','carrier'),('strictness',),('routes',),('pair',),('strictness',))


def qualify(c, values, evidence):
    rows=[]
    for index,((path,expected,disposition),dependencies) in enumerate(zip(QUALIFICATIONS,ROW_DEPENDENCIES),1):
        present=path in values
        if present:c.compare('worked_qualification_schema',values[path],expected,path)
        correct=present and type(values[path]) is type(expected) and values[path]==expected
        checks={name:evidence[name] for name in dependencies}
        status=('FAIL' if present and not correct or any(x['status']=='FAIL' for x in checks.values()) else
                'UNRESOLVED' if not present or any(x['status']=='UNRESOLVED' for x in checks.values()) else 'PASS')
        rows.append({'row':index,'field':path,'reference':values.get(path),'status':status,
                     'disposition':disposition if status=='PASS' else status,
                     'semantic_checks':checks,'historical_matches':0,
                     'reason':'semantic validation or retained method/boundary disposition; no literal counterpart match credited'})
        if index==6:rows[-1]['regenerated_method_scope']='finite source-bound basis and non-density witness; no vertex enumeration performed or credited'
        if index==4:rows[-1]['retained_characterization_scope']='existence and density exclusion rechecked; complete polytope characterization retained, not credited as reproduced'
        if index==5:rows[-1]['mathematical_boundary']='UNRESOLVED; no extension to generated H claimed'
    return rows
