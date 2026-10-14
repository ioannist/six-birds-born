"""V25 routing onto shared historical hierarchy, BCa and sensitivity helpers."""
import copy
from fractions import Fraction
from types import SimpleNamespace
from born_ladder.reproduction.specification import PublicSpecification
from born_ladder.snapshot import g2a, g2c_evaluate as g2c
from born_ladder.snapshot.statistics_helpers import _conditional_sign_counts
from born_ladder.snapshot.rng import RNGStream
from .specification import digest


def inherited_contract(spec,evaluation,replicates=None):
    from born_ladder.reproduction.evaluation import PopulationSpecification
    public=PopulationSpecification(spec.directory,evaluation)
    contract=copy.deepcopy(g2c._contract(public) if evaluation=='cross-term' else g2a._contract(public))
    rng=contract['rng']; rng['framing']['master_prefix']=spec.science['rng']['master_prefix']
    if evaluation=='competitor':
        inference=contract['inference']
    else:
        inference={'bootstrap':contract['bootstrap'],'bca':contract['bca'],
                   'multiplicity':contract['multiplicity'],'conditional_sign_randomization':{'seed_blocks':20}}
    if replicates is not None:
        if type(replicates) is not int or not 1<=replicates<=20000: raise ValueError('invalid synthetic replicate count')
        inference['bootstrap']['replicates']=replicates
    else: inference['bootstrap']['replicates']=spec.science['inference']['bootstrap']['replicates']
    family=spec.science['inference']['multiplicity'][evaluation.replace('-','_')]
    inference['multiplicity']['endpoint_ledgers']['g2a']=family['bca_endpoints']
    if evaluation=='cross-term': contract['bootstrap']=inference['bootstrap']
    if evaluation=='cross-term': contract['rng_version']=spec.science['rng']['master_prefix']
    return contract,inference


def derive(spec,evaluation):
    def key(algorithm,fields):
        if algorithm!='bootstrap' or fields['stage_id']!='v25-'+evaluation:
            raise ValueError('v25 bootstrap stage/domain differs')
        return spec.bootstrap_key(evaluation,fields['statistic_id'],fields['replicate_index'])
    return key


def membership(spec,evaluation,row,*,seeds,groups,replicate):
    """Explicit seventeen-row domain ledger; deterministic/reuse do not draw."""
    name=row['name']; statistic=row['statistic_id']
    if statistic in ('NONE','REUSE primary'): return {'mode':statistic,'name':name}
    stream=RNGStream(spec.bootstrap_key(evaluation,statistic,replicate)); result={}
    sample_seeds=lambda:[stream.unbiased_index(len(seeds)) for _ in seeds]
    if name in ('primary TV and Brier','primary TV','brier_complete_ranking'):
        result['seeds']=sample_seeds()
    elif name=='config_only_superpopulation':
        result['groups']=[stream.unbiased_index(len(groups)) for _ in groups]
    elif name=='hierarchical_seed_config_superpopulation':
        result['seeds']=sample_seeds()
        result['groups']=[[stream.unbiased_index(len(groups)) for _ in groups] for _ in seeds]
    elif name=='two_way_pigeonhole_seed_by_config':
        result['seeds']=sample_seeds(); result['groups']=[stream.unbiased_index(len(groups)) for _ in groups]
    elif name=='config/experiment-only superpopulation':
        result['groups']={source:[stream.unbiased_index(len(groups[source])) for _ in groups[source]] for source in ('EXP-112','G2x')}
    elif name=='hierarchical seed then config/experiment superpopulation':
        result['seeds']=sample_seeds()
        result['groups']={source:[[stream.unbiased_index(len(groups[source])) for _ in groups[source]] for _ in seeds] for source in ('EXP-112','G2x')}
    elif name=='two-way pigeonhole seed by config/experiment':
        result['seeds']=sample_seeds()
        result['groups']={source:[stream.unbiased_index(len(groups[source])) for _ in groups[source]] for source in ('EXP-112','G2x')}
    else: raise ValueError('unimplemented registered domain row: '+name)
    return {'mode':'draw','name':name,'statistic_id':statistic,'indices':result,
            'counter':stream.counter,'remaining_words':len(stream._buffer)}


def joint_verdict(spec,*,control=False,unresolved=False,reversal=False,failure=False,all_pass=True,infrastructure=None):
    if infrastructure: return {'status':'INCONCLUSIVE_INFRASTRUCTURE','reason':infrastructure}
    keys={'control_failure':control,'unresolved_evidence':unresolved,
          'named_sensitivity_reversal':reversal,'established_endpoint_failure':failure}
    if any(type(x) is not bool for x in keys.values()): raise ValueError('Boolean verdict flags required')
    rows=[row for row in spec.science['outcomes']['joint_decision_table'] if all(row[k]==v for k,v in keys.items())]
    if len(rows)!=1: raise ValueError('decision cube not complete/unique')
    status=rows[0]['joint_status']
    if status=='PASS_IF_ALL_REQUIRED_ENDPOINTS_PASS_ELSE_INCONCLUSIVE': status='PASS' if all_pass else 'INCONCLUSIVE'
    return {'status':status,'flags':keys,'all_required_pass':all_pass}


def dependency_states(spec,endpoint,states):
    rows=[row for row in spec.science['outcomes']['endpoint_control_dependencies'] if row['endpoint']==endpoint]
    if len(rows)!=1: raise ValueError('endpoint dependency absent')
    dependencies=rows[0]['controls']
    selected={name:states.get(name,'missing') for name in dependencies}
    return {'states':selected,'control_failure':any(x=='fail' for x in selected.values()),
            'unresolved':any(x not in ('pass','fail') for x in selected.values())}


def endpoint_status(item,margin,*,service=False):
    if item.get('control_failure'): return 'CONTROL_FAILURE'
    if item.get('unresolved') or item.get('bca_simultaneous_lower') is None or item.get('bca_simultaneous_upper') is None:
        return 'UNRESOLVED'
    lower,upper=item['bca_simultaneous_lower'],item['bca_simultaneous_upper']
    if service:
        # infer positive benefit -S2; printed S2 negates/reverses this interval.
        if lower>=0: return 'SENSITIVITY_REVERSAL' if item.get('sensitivity_reversal') else 'PASS'
        if upper<0: return 'FAIL'
    else:
        if upper<=margin: return 'FAIL'
        if lower>margin and item['holm_adjusted_p']<=0.05:
            return 'SENSITIVITY_REVERSAL' if item.get('sensitivity_reversal') else 'PASS'
    return 'NEUTRAL'


def sign_counter_cache():
    cached={}
    def p(values):
        key=tuple(float(x) for x in values)
        if key not in cached: cached[key]=_conditional_sign_counts(key)
        two,one,total=cached[key]; return two/total,one/total
    return cached,p


def competitor(spec,records,*,seeds,configs,replicates=None):
    contract,inference=inherited_contract(spec,'competitor',replicates)
    rules=spec.science['evaluations']['competitor']['competitors_in_registered_order']
    tail_cache,tail=sign_counter_cache(); results={}; key=derive(spec,'competitor')
    definitions=[(kind,rule,'D__'+rule+'_minus_q_full',1.0) for kind in ('raw','package') for rule in rules]
    definitions += [(kind,None,'S2__q_full_minus_2xL_full',-1.0) for kind in ('raw','package')]
    for kind,rule,field,orientation in definitions:
        contrast_id=rule if rule else 'serviceability_factor_two'; identifier=kind+'::'+contrast_id
        selected=[row for row in records if row['kind']==kind and row['eligibility']]
        dependency='serviceability S_2, each map' if rule is None else ('canonical advantage, each map in either evaluation' if rule=='q_diag_canonical' else 'non-diagonal competitor advantage, each map')
        states={name: ('fail' if any(row['controls'].get(name)=='fail' for row in selected) else
                       'pass' if selected and all(row['controls'].get(name)=='pass' for row in selected) else 'missing') for name in ('I','A','F','C')}
        states.update(T='pass',S='pass')
        deps=dependency_states(spec,dependency,states)
        if deps['control_failure'] or deps['unresolved'] or any(row['pairwise_contrast'].get(field) is None for row in selected):
            results[identifier]={'point_estimate':None,'control_failure':deps['control_failure'],'unresolved':True,
                                 'rule':rule,'kind':kind,'conditional_one_sided_p':1.0,'dependencies':deps}
            continue
        values,brier,counts=g2a._hierarchical_values(selected,field,factor2=2.0)
        if list(sorted(values))!=list(seeds) or any(set(values[seed])!=set(configs) for seed in seeds):
            raise ValueError('competitor complete seed/config cohort differs')
        vector=tuple(g2a._mean([values[seed][config] for config in configs])*orientation for seed in seeds)
        two,one=tail(vector)
        boot=g2a._bootstrap_result(vector,stage_id='v25-competitor',statistic_id=identifier,inference=inference,
                   derive_key=key,rng_contract=contract['rng'],attested_json_sha256=spec.digest)
        atoms=g2a._sensitivity_atoms(g2a._mean(vector),values,brier,orientation=orientation,seeds=seeds,configs=configs)
        sensitive=g2a._sensitivity_results(stage_id='v25-competitor',statistic_id=identifier,primary_bootstrap=boot,
                   atoms=atoms,values=values,brier=brier,orientation=orientation,seeds=seeds,configs=configs,
                   inference=inference,derive_key=key,rng_contract=contract['rng'],attested_json_sha256=spec.digest,sign_p=tail)
        reversal=any(g2a._mean(vector)*x<0 for xs in atoms.values() for x in xs)
        results[identifier]={'rule':rule,'kind':kind,'point_estimate':g2a._mean(vector),'seed_values':vector,
                   'conditional_one_sided_p':one,'conditional_two_sided_p':two,'exact_sign_counts':tail_cache[vector],
                   **boot,'sensitivity_atoms':atoms,'sensitivities':sensitive,'sensitivity_reversal':reversal,
                   'hierarchy_counts':counts,'dependencies':deps}
        brier_vector=tuple(g2a._mean([brier[seed][config] for config in configs])*orientation for seed in seeds)
        sensitive['brier_complete_ranking']['exact_sign_counts']=tail_cache[brier_vector]
        # Save indices by replaying the same audited stream (no alternate sampling).
        for name,detail in [('primary TV',boot),*[(n,d) for n,d in sensitive.items() if 'rng_audit' in d and n!='seed_only_fixed_census']]:
            template=next(row for row in spec.domains if row['evaluation']=='competitor' and row['name']==name)
            detail['saved_membership']=[membership(spec,'competitor',{**template,'statistic_id':audit['statistic_id'] if 'statistic_id' in audit else
                     (identifier if name=='primary TV' else identifier+'::sensitivity::'+name)},seeds=seeds,groups=configs,replicate=k)
                     for k,audit in enumerate(detail['rng_audit'])]
            if name=='primary TV': results[identifier]['saved_membership']=detail['saved_membership']
    return finalize(spec,'competitor',results,replicates)


def cross_term(spec,records,controls,*,seeds,replicates=None):
    contract,inference=inherited_contract(spec,'cross-term',replicates); key=derive(spec,'cross-term')
    placeholder=SimpleNamespace(attestation=SimpleNamespace(json_sha256=spec.digest))
    selected=[row for row in records if row['eligibility']]
    control_failed=any(row['controls'].get(name)=='fail' for row in selected for name in ('I','A','F','C'))
    control_missing=not selected or any(row['controls'].get(name)!='pass' for row in selected for name in ('I','A','F','C'))
    if control_missing:
        return finalize(spec,'cross-term',{kind:{'kind':kind,'rule':'q_diag_canonical','point_estimate':None,
                'unresolved':True,'control_failure':control_failed,'conditional_one_sided_p':1.0,
                'reason':'required shared input/full/canonical controls unavailable'} for kind in ('raw','package')},replicates)
    dtv,witnesses,support,structural,hierarchy=g2c._source_seed_values(records,controls,metric='dtv',seeds=seeds,diagonal_label='q_diag_canonical')
    brier,bw,bs,bstruct,bh=g2c._source_seed_values(records,controls,metric='brier',seeds=seeds,diagonal_label='q_diag_canonical')
    if support!=bs or structural!=bstruct: raise ValueError('cross-term metric support differs')
    if any(support[source]['raw'][seed]!=support[source]['pkg'][seed] for source in ('EXP-112','G2x') for seed in seeds):
        raise ValueError('cross-term raw/package support differs')
    vectors={}; laws={}
    for kind in ('raw','pkg'):
        for name,values in [('tv',dtv),('brier',brier)]:
            vector=g2c._combined_seed_vector(values,kind=kind,seeds=seeds)
            if vector is None: return finalize(spec,'cross-term',{k:{'point_estimate':None,'unresolved':True,'conditional_one_sided_p':1.0,'kind':k} for k in ('raw','package')},replicates)
            vectors[kind+'::'+name]=vector
    law_record=next(row for row in selected if isinstance(row.get('brier_score'),dict) and row['brier_score'])
    for law in sorted(law_record['brier_score']):
        values=g2c._source_seed_values(records,controls,metric='brier_law:'+law,seeds=seeds,diagonal_label='q_diag_canonical')[0]
        laws[law]=values
        for kind in ('raw','pkg'): vectors[kind+'::law::'+law]=g2c._combined_seed_vector(values,kind=kind,seeds=seeds)
    paired=g2c._paired_bootstrap_results(placeholder,vectors,inference=inference,contract=contract,derive_key=key,stage_id='v25-cross-term')
    cache={}; results={}
    for kind,public_kind in [('raw','raw'),('pkg','package')]:
        vector=tuple(vectors[kind+'::tv']); two,one,total=_conditional_sign_counts(vector)
        ranking={'laws':{law:{'point_estimate':g2a._mean(vectors[kind+'::law::'+law]),**paired[kind+'::law::'+law]} for law in laws}}
        ranking['ordered_best_to_worst']=sorted(laws,key=lambda law:(ranking['laws'][law]['point_estimate'],law))
        ranking['paired_membership_statistic_id']='paired_kinds_sources_metrics'
        sensitive,reversal,non_evaluable=g2c._sensitivities(dtv,brier,kind=kind,seeds=seeds,primary=g2a._mean(vector),
                    primary_bootstrap=paired[kind+'::tv'],brier_bootstrap=paired[kind+'::brier'],brier_ranking=ranking,
                    scheduled=support,contract=contract,derive_key=key,spec=placeholder,paired_membership_cache=cache,stage_id='v25-cross-term')
        control_states={name: 'fail' if any(row['controls'].get(name)=='fail' for row in selected) else
                        'pass' if all(row['controls'].get(name)=='pass' for row in selected) else 'missing' for name in ('I','A','F','C')}
        control_states.update(T='pass',S='missing' if non_evaluable else 'pass')
        deps=dependency_states(spec,'canonical advantage, each map in either evaluation',control_states)
        results[public_kind]={'kind':public_kind,'rule':'q_diag_canonical','point_estimate':g2a._mean(vector),
              'seed_values':vector,'exact_sign_counts':[two,one,total],'conditional_one_sided_p':one/total,
              'conditional_two_sided_p':two/total,**paired[kind+'::tv'],'sensitivities':sensitive,
              'sensitivity_reversal':reversal,'unresolved':non_evaluable or deps['unresolved'],
              'control_failure':deps['control_failure'],'dependencies':deps}
    return finalize(spec,'cross-term',results,replicates)


def finalize(spec,evaluation,results,replicates):
    expected=spec.science['inference']['multiplicity'][evaluation.replace('-','_')]['holm_members']
    if len(results)!=expected: raise ValueError('fixed Holm family size differs')
    adjusted=g2a._holm({name:row['conditional_one_sided_p'] for name,row in results.items()})
    gate=spec.science['evaluations']['cross_term']['margin']; margin=Fraction(gate['numerator'],gate['denominator']) if evaluation=='cross-term' else 0
    for name,row in results.items():
        row['holm_adjusted_p']=adjusted[name]
        row['local_status']=endpoint_status(row,margin,service=(evaluation=='competitor' and row.get('rule') is None))
        if evaluation=='competitor' and row.get('rule') is None and row.get('point_estimate') is not None:
            row['printed_serviceability']={'point':-row['point_estimate'],
                  'lower':None if row['bca_simultaneous_upper'] is None else -row['bca_simultaneous_upper'],
                  'upper':None if row['bca_simultaneous_lower'] is None else -row['bca_simultaneous_lower']}
    joint=joint_verdict(spec,control=any(row.get('control_failure',False) for row in results.values()),
          unresolved=any(row['local_status'] in ('UNRESOLVED','NEUTRAL') for row in results.values()),
          reversal=any(row.get('sensitivity_reversal',False) for row in results.values()),
          failure=any(row['local_status']=='FAIL' for row in results.values()),
          all_pass=all(row['local_status']=='PASS' for row in results.values()))
    return {'schema':'born_v25_population_v1','evaluation':evaluation,'scientific_digest':spec.digest,
            'mode':'registered' if replicates is None else 'synthetic-reduced',
            'bootstrap_replicates':20000 if replicates is None else replicates,
            'family':spec.science['inference']['multiplicity'][evaluation.replace('-','_')],
            'margin':gate if evaluation=='cross-term' else {'numerator':0,'denominator':1},
            'statistics':results,'joint':joint,
            'paper_values':{name:{
                  **({'point':row['printed_serviceability']['point'],'lower':row['printed_serviceability']['lower'],
                      'upper':row['printed_serviceability']['upper']} if row.get('printed_serviceability') else
                     {'point':row.get('point_estimate'),'lower':row.get('bca_simultaneous_lower'),
                      'upper':row.get('bca_simultaneous_upper')}),
                  'formula':'ell(q_full)-2*ell(p)' if evaluation=='competitor' and row.get('rule') is None
                      else 'ell('+str(row.get('rule'))+')-ell(q_full)',
                  'status':row['local_status']} for name,row in results.items()}}
