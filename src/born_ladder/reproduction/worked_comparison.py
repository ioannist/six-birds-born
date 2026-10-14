"""Optional exact post-construction comparison; never a production input.

Criteria: ordered identities/words/counts/booleans and exact rational values
must agree; binary64 fields must agree bit for bit. Every interval endpoint is
compared, with differences reported (not accepted behind a tolerance). Process
receipts, timings and narrative prose are not scientific comparison fields.
"""
import ast
from fractions import Fraction as Q
from pathlib import Path

from born_ladder import arithmetic as A
from .worked_cases import read, frame
from .census_comparison import Comparison
from .embedding import transport, ensemble, fragment, order, ri as R


def fields(reference, names):
    """Fixed representation adapter. Never take coverage from generated keys."""
    return {k:reference[k] for k in names}


PAIR_FIELDS=('left','right','coordinate_barycenter','full_barycenter_original_parity','first_read_all_lenses_equal')
EVENT_FIELDS=('atomic_word_count','atomic_words','complete_test_count','equal_barycenter_control_exact','event_count','events','families')
NON_DENSITY_FIELDS=('coordinate_determinant_exact','epsilon_exact','events','generated_H',
    'minimum_valuation_margin_exact','non_trace_proof','proper_groupings_checked','trace_one_witness','witness_determinant_exact')
CARRIER_FIELDS=('K_max_row_mass_error','K_no_row_normalization','K_row_masses','P_symmetric_idempotent_constant',
    'atom_positivity','distinct_mode_values','exact_source_rank','landed_retained_rank','mean','parent_sum_exact_I','s','trace_check_preparations')
ATOM_WORD_FIELDS=('M','contexts','determinant_effect_exact','effect_G_adjoint_M_times_M','outcomes','test_id')
EVENT_ROW_FIELDS=('contexts','effect','id','mask','public_word_subset','test_id')
FAMILY_ROW_FIELDS=('contexts','id','identity_enclosed','subset_count','sum_word_effects','words')
STRICT_FIELDS=('density_separation','every_old_field_equal','left_density','left_old_view','old_field_matches',
    'p','p_prime','point_indices','readout_splits','right_density','right_old_view')


def algebraic_states(expressions,radicand):
    """Parse historical Matrix/rational/sqrt notation without eval or SymPy.

    Re-express each positive radical in the generated Q[sqrt(d)] ring. The
    ratio of historical and generated radicands must have an exact rational
    square root; an approximate equivalence cannot pass this comparison.
    """
    d=Q(radicand)
    def scalar(node):
        if isinstance(node,ast.Constant) and type(node.value) is int:return A.Quad(node.value,0,d)
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
            value=scalar(node.operand);return -value if isinstance(node.op,ast.USub) else value
        if isinstance(node,ast.BinOp):
            left,right=scalar(node.left),scalar(node.right)
            if isinstance(node.op,ast.Add):return left+right
            if isinstance(node.op,ast.Sub):return left-right
            if isinstance(node.op,ast.Mult):return left*right
            if isinstance(node.op,ast.Div) and right.b==0 and right.a:return left*(1/right.a)
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='sqrt' and len(node.args)==1 and not node.keywords:
            arg=scalar(node.args[0])
            if arg.b==0:
                ratio=A.exact_sqrt(arg.a/d)
                if ratio is not None:return A.Quad(0,ratio,d)
        raise ValueError('unsupported historical exact scalar expression')
    states=[]
    for expression in expressions:
        node=ast.parse(expression,mode='eval').body
        if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Name) or node.func.id!='Matrix' or len(node.args)!=1 or node.keywords:
            raise ValueError('unsupported historical state notation')
        rows=node.args[0]
        if not isinstance(rows,ast.List) or len(rows.elts)!=2:raise ValueError('historical state shape')
        matrix=[]
        for row in rows.elts:
            if not isinstance(row,ast.List) or len(row.elts)!=2:raise ValueError('historical state shape')
            matrix.append([scalar(x) for x in row.elts])
        states.append(A.dump(matrix))
    return states


def reference_certificates(reference, *, non_trace=None):
    """Translate retained representations to the complete public schema.

    Coverage is independent of the generated object. Extra scientific keys in
    either public certificate fail whole-object comparison. Newly explicit
    algebraic fields (parent, effects, program inventory, frame) are checked
    against the retained source, never filled from the regenerated certificate.
    No sampling, loss computation or population inference is performed.
    """
    from born_ladder.claim_checks import parent_certificate
    from born_ladder.instruments import Instrument, tests, FIELDS
    reference=Path(reference)
    old=read(reference/'amp1/context_inputs.json');selected=read(reference/'RI/CONTEXT.json')
    amplitude=read(reference/'amp1/induced_certificate.json');joined=read(reference/'amp1b/joined_certificate.json')
    e=read(reference/'E1/D_certificate.json');family=read(reference/'E2/C_certificate.json')
    basis=read(reference/'E3/C1_certificate.json');strict=read(reference/'RI/initial_strictness_certificate.json')
    carrier=read(reference/'RI/B_certificate.json');six=read(reference/'RI/six_state_certificate.json')
    nontrace=Path(non_trace) if non_trace is not None else reference/'non_trace_rederivation.json'
    finite=fields(read(nontrace),NON_DENSITY_FIELDS)
    contexts={};models={}
    for name,x in (('original',old),('selected',selected)):
        w,s,P,K=frame(x);models[name]=Instrument(x,w,s,P,K)
        b=x['born'];identity=x['identity']
        contexts[name]={'identity':{'exp':identity.get('exp',identity.get('experiment')),
            'config':b['cell'],'seed':b['seed'],'scale':b['scale'],'k':b['k'],'step_index':b['step_index']},
            'kernel':x['kernel'],'born':b,'lens':fields(x['lens'],FIELDS),
            'exact':{'w':A.qserial(w),'s':str(s),'projector':A.qserial(P)}}
    m=models['original']
    events=fields(family,EVENT_FIELDS)
    for key,names in (('atomic_words',ATOM_WORD_FIELDS),('events',EVENT_ROW_FIELDS),('families',FAMILY_ROW_FIELDS)):
        events[key]=[fields(row,names) for row in family[key]]
    original={'amplitude':amplitude,'joined':joined,
        'ensemble':{'checked_words':e['checked_words'],'witness':e['witness'],'pair_certificate':fields(e['pair_certificate'],PAIR_FIELDS)},
        'finite_events':events,
        'finite_family':{'basis_exact':basis['basis_exact'],'non_density':finite,
            'parent':parent_certificate(m),
            'atomic_effects':{f:[A.qserial(m.C[S]) for S in part.values()] for f,part in m.parts.items()},
            'programs':[{'contexts':list(cs),'words':[list(word) for word in words],'events':1<<len(words)} for cs,words in tests(m)]},
        'order':read(reference/'E2/D_certificate.json')['uniform_witness'],
        'lean_certificates':{'B04':A.qserial(transport.extract(old,amplitude,joined)),
            'B05':A.qserial(ensemble.extract(old,e)),'B06':A.qserial(fragment.extract(old,basis)),
            'B07':A.qserial(order.extract(old))}}
    # Context hashing names changed in P3b. The six execution coordinates are
    # fixed, not selected by the generated object's identity keys.
    strict_projection=fields(strict,('pairs_tested','certificate'))
    import copy
    strict_projection=copy.deepcopy(strict_projection)
    strict_projection['certificate']=fields(strict_projection['certificate'],STRICT_FIELDS)
    aliases={'exp':'experiment','config':'actual_source_cell','k':'resolution','step_index':'step'}
    for side in ('left_old_view','right_old_view'):
        identity=strict['certificate'][side]['context']
        strict_projection['certificate'][side]['context']={key:identity[aliases.get(key,key)]
            for key in ('exp','config','seed','scale','k','step_index')}
    exact=A.certify_G(selected['exact']['s'])
    # Its archived verdict must agree too, not merely the transformed table.
    if six['status']!='PROVED UNDER ADOPTED MODEL':
        raise ValueError('archived six-state verdict differs from the registered adopted-model result')
    selected_cert={'parent':parent_certificate(models['selected']),
        'carrier':fields(carrier,CARRIER_FIELDS),'strictness':strict_projection,'six_state':exact,
        'lean_certificates':{'RI':A.qserial(R.extract(selected,strict))}}
    return contexts,{'original':original,'selected':selected_cert},six


# These paths contain explanations, not numbers or verdict flags. All other
# nested fields (including boundary statuses and masses) are scientific.
ORDER_NARRATIVE_PATHS={
    ('canonical_pairs','*','scope'), ('context_pairs','*','other_pairs'),
    ('passive_disturbance','*','comparison'),
    ('atomic_fragment_boundary','proof'),
    ('atomic_fragment_boundary','coarse_complement'),
    ('operator_quotient_boundary','proof_of_operator_equality'),
    ('operator_quotient_boundary','partial_sum_ambiguity'),
    ('admitted_fragment_scope','complement'),
    ('admitted_fragment_scope','partial_sum'),
    ('admitted_fragment_scope','global_operator_quotient'),
    ('admitted_fragment_scope','algebra_scope'), ('wall_seconds',),
}


def order_scientific(value, path=()):
    if isinstance(value,dict):
        return {k:order_scientific(v,path+(k,)) for k,v in value.items()
                if path+(k,) not in ORDER_NARRATIVE_PATHS}
    if isinstance(value,list):return [order_scientific(v,path+('*',)) for v in value]
    return value


def compare_order_diagnostics(c, generated, reference):
    c.compare('worked_order_diagnostics',order_scientific(generated),order_scientific(reference))
    if hasattr(c,'documentary_fields'):
        def visit(value,path=()):
            if isinstance(value,dict):
                for key,item in value.items():
                    here=path+(key,)
                    if here in ORDER_NARRATIVE_PATHS and key!='wall_seconds':
                        row={'field':'E2/D_certificate.json/'+'/'.join(here),
                             'reference':item,'disposition':'HISTORICAL_DOCUMENTARY_ONLY',
                             'reason':'explanation only; all adjacent quantitative and verdict fields compared'}
                        c.documentary_fields.append(row)
                    else:visit(item,here)
            elif isinstance(value,list):
                for item in value:visit(item,path+('*',))
        visit(reference)


def compare_worked_cases(generated,reference,*,comparison=None,non_trace=None,source_runs=None,
                         specifications='specifications',lean_root=None):
    generated,reference=Path(generated),Path(reference)
    c=Comparison() if comparison is None else comparison
    contexts,expected,six=reference_certificates(reference,non_trace=non_trace)
    for name in ('original','selected'):
        c.compare(name+'_complete_context',read(generated/name/'CONTEXT.json'),contexts[name])
        c.compare(name+'_complete_certificate',read(generated/name/'certificates.json'),expected[name])
    diagnostic=generated/'original/order_diagnostics.json'
    if diagnostic.is_file():
        compare_order_diagnostics(c,read(diagnostic),read(reference/'E2/D_certificate.json'))
    else:
        c.compare('worked_order_diagnostics_presence',False,True)
    # Independently compare the transformed six-state fields with the historic
    # symbolic representation. The adapter's complete expected object above
    # also catches absent/extra fields, status and explanatory scope changes.
    exact=expected['selected']['six_state']
    c.compare('RI_six_states',exact['states_and_sharp_yes_effects'],algebraic_states(six['G_states'],exact['exact_radicand']))
    orth=A.certify_G(Q(32))
    c.compare('RI_six_orthonormal_states',orth['states_and_sharp_yes_effects'],algebraic_states(six['ortho_states'],orth['exact_radicand']))
    rational_table=lambda table:[[str(Q(v)) for v in row] for row in table]
    for name,x,y in [('metric',exact['G'],six['G']),('s',contexts['selected']['exact']['s'],six['s']),
        ('table',rational_table(exact['YES_table_exact']),rational_table(six['YES_table'])),
        ('mixtures',exact['five_mixture_identities'],six['mixtures']),
        ('projector_roots',exact['projector_roots'],six['principal_roots_are_projectors']),
        ('conjugacy',exact['all_projectors_trace1_idempotent_G_adjoint'],six['projectivity_trace_G_adjoint_conjugacy'])]:
        c.compare('RI_six_'+name,x,y)
    import itertools
    c.compare('RI_six_boolean_values',sorted({2*sum(row) for row in itertools.product((0,1),repeat=3)}),six['measure_proof_parity_values'])
    c.compare('RI_six_contradiction',len(exact['YES_table_exact'][0]),six['contradiction_value'])
    c.compare('RI_six_commands',['BIN(Pa)','BIN(Pb)','BIN(Pc)'],six['test_commands'])
    qualifications=[]
    if comparison is not None:
        qualifications=reference_only_fields(c,reference,generated,source_runs,specifications,lean_root) or []
    result=c.result()
    result['worked_qualifications']=qualifications
    result['declared_limits']=[r for r in qualifications if r['disposition'] not in ('SEMANTIC_PASS','FAIL','UNRESOLVED')]
    result['resolved_with_declared_limits']=bool(qualifications) and all(r['status']=='PASS' for r in qualifications)
    result['generated_H_boundary']='UNRESOLVED; no extension claimed'
    validation_groups={k:v for k,v in result['field_groups'].items() if k.startswith(('worked_semantic_','worked_qualification_')) or k=='source_scientific_inputs'}
    result['worked_validation_coverage']={'independent_validation_checks':sum(v['compared'] for v in validation_groups.values()),
        'historical_literal_checks':sum(v['compared'] for k,v in result['field_groups'].items() if k not in validation_groups),
        'qualifications':len(qualifications),'qualification_historical_matches':0,
        'documentary_method_historical_matches':0,
        'scope':'semantic and schema checks are validations; method/boundary items are named dispositions, not historical matches'}
    result['event_admission_scope_mapping']={'historical_label':'conditional analytic event admission under the adopted density model',
        'regenerated_scope':'adopted density model; fixed complete tests and their explicit subsets',
        'events_mapped':len(expected['original']['finite_events']['events']),
        'justification':'each numerical event, word membership, effect and test inventory is compared; admission labels refer to this same adopted model, not to physical realization or newly proved historical explanations'}
    result['criteria']=('supplied complete P8 policy; exact values plus fixed computed-float rule' if comparison is not None
                        else 'exact identities/order/counts/booleans/rationals/endpoints; bitwise binary64; no tolerance')
    result['representation_adapter']='fixed complete public certificate schema; reference-source algebraic checks for newly explicit fields; no generated-key projections'
    return result


def reference_only_fields(c,root,generated=None,source_runs=None,specifications='specifications',lean_root=None):
    """Name every retained field outside the public representation adapter.

    Historical analytic prose is documentary. A quantitative diagnostic or
    verdict with no literal field receives a checked semantic qualification.
    Unknown keys are scientific and fail rather than being silently projected.
    """
    schemas={
        'E1/D_certificate.json':(set(('checked_words','witness','pair_certificate')),set(('E0_examples','actual_sequential_argument','arithmetic','initial_passive_valuation','other_words','reason','stop')),set(('status',))),
        'E2/C_certificate.json':(set(EVENT_FIELDS),set(('full_selective_bridges_not_quotiented','no_full_operator_interval_admission','old_E1_witness_preserved_sha256','uniform_equal_density_word_invariance','wall_seconds')),set(('status',))),
        'E3/C1_certificate.json':(set(('basis_exact','coordinate_determinant_exact')),set(('basis_effects','coordinate_basis','generated_extension_obligation','non_trace_existence_proof','trace_states_on_R_and_H','wall_seconds')),set(('informational_complete_exact','status_current','status_generated','vertices_enumerated'))),
        'E2/D_certificate.json':(set(('uniform_witness','admitted_fragment_scope','atomic_fragment_boundary','no_contextuality_incompatibility_or_quantum_specificity_inference','operator_quotient_boundary','wall_seconds','canonical_equal_count','canonical_pairs','canonical_unequal_count','coarse_fine_forgetting','context_pairs','passive_disturbance','status','unresolved_count')),set(),set()),
        'RI/B_certificate.json':(set(CARRIER_FIELDS),set(('frame_covariance_proof','uniform_trace_proof')),set(('lens_frame_unit_joins','status'))),
        'RI/initial_strictness_certificate.json':(set(('certificate','pairs_tested')),set(('no_native_preparation_claim','old_seed910000_witnesses_transferred','scope','search_class')),set(('status',))),
        'RI/six_state_certificate.json':(set(('G','G_states','YES_table','contradiction_value','measure_proof_parity_values','mixtures','ortho_states','principal_roots_are_projectors','projectivity_trace_G_adjoint_conjugacy','s','status','test_commands')),set(('domain',)),set(('orthonormal_and_G_routes_independent',))),
    }
    def record(path,value,disposition):
        row={'field':path,'reference':value,'generated':None,'disposition':disposition,
             'reason':'retained analytical narrative' if disposition=='HISTORICAL_DOCUMENTARY_ONLY' else
                      'retained diagnostic/verdict has no literal public certificate counterpart; mathematical adapter checks do not assert this field was regenerated'}
        (c.documentary_fields if disposition=='HISTORICAL_DOCUMENTARY_ONLY' else c.unresolved_reference_fields).append(row)
        c.record(disposition,path,None,value,disposition,disposition=='HISTORICAL_DOCUMENTARY_ONLY')
    def inspect(path,value,used,docs,unresolved):
        c.compare('archive_scientific_key_coverage',sorted(set(value)-used-docs-unresolved),[],path)
        for key in sorted(set(value)&docs):record(path+'/'+key,value[key],'HISTORICAL_DOCUMENTARY_ONLY')
        # The fixed twelve qualifications are checked below. Unknown fields fail.
    for path,(used,docs,unresolved) in schemas.items():inspect(path,read(root/path),used,docs,unresolved)
    pair=read(root/'E1/D_certificate.json')['pair_certificate']
    inspect('E1/pair_certificate',pair,set(PAIR_FIELDS),{'original_certificate_sha256','reachability'},{'status'})
    strict=read(root/'RI/initial_strictness_certificate.json')['certificate']
    inspect('RI/strictness/certificate',strict,set(STRICT_FIELDS),{'upper_access'},{'status'})
    family=read(root/'E2/C_certificate.json')
    for key,names,docs,unresolved in (
        ('atomic_words',ATOM_WORD_FIELDS,{'uniform_density_valuation'},set()),
        ('families',FAMILY_ROW_FIELDS,{'predicates','proof'},set()),
        ('events',EVENT_ROW_FIELDS,{'conjuncts'},set())):
        for index,row in enumerate(family[key]):
            if key=='events':
                c.compare('event_admission_scope_mapping',row['status'],
                    'conditional analytic event admission under the adopted density model',str(index))
                # These are actual memberships, not process prose.
                c.compare('event_bridge_memberships',row['bridge']['P'],
                    {'context_sequence':row['contexts'],'word_subset':row['public_word_subset']},str(index))
                record('E2/events/'+str(index)+'/bridge',
                       {k:v for k,v in row['bridge'].items() if k!='P'},'HISTORICAL_DOCUMENTARY_ONLY')
            inspect('E2/'+key+'/'+str(index),row,set(names)|({'bridge','status'} if key=='events' else set()),docs,unresolved)

    from .worked_qualifications import retained_values,semantic_evidence,qualify
    if generated is None:raise FileNotFoundError('semantic qualifications require regenerated worked evidence')
    evidence=semantic_evidence(c,generated,source_runs=source_runs,
                    specifications=specifications,lean_root=lean_root)
    if evidence['basis']['status']=='PASS':
        c.compare('worked_semantic_basis',read(root/'E3/C1_certificate.json')['coordinate_determinant_exact'],
                  evidence['basis']['checks']['coordinate_determinant_exact'],'retained_coordinate_determinant_exact')
        if c.groups['worked_semantic_basis']['failed']:evidence['basis']['status']='FAIL'
    rows=qualify(c,retained_values(root),evidence)
    for row in rows:
        if row['status']=='UNRESOLVED':c.unresolved_reference_fields.append(row)
        elif row['disposition']!='SEMANTIC_PASS' and row['status']=='PASS':c.documentary_fields.append(row)
        c.record('worked_qualification_dispositions',row['field'],row['semantic_checks'],row['reference'],
                 row['disposition'],row['status']=='PASS')
    return rows
