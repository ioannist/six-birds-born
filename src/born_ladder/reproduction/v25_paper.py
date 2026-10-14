"""Explicit registered v25 outputs and the retained RI canonical worked example."""
import gc
import json
import math
from pathlib import Path

from born_ladder.archive import sha


def read(path):
    with Path(path).open() as stream:return json.load(stream)


def comparison_preflight():
    """Fail before a large comparison if the selected canonical base is missing."""
    import importlib
    requirements={'numpy':'2.4.4','sympy':'1.14.0','mpmath':'1.3.0'}
    for name,version in requirements.items():
        try:module=importlib.import_module(name)
        except ImportError as error:
            raise ValueError('comparison dependency missing: '+name+'; install requirements.lock in the comparison environment') from error
        if module.__version__!=version:
            raise ValueError('comparison dependency mismatch: '+name+' requires '+version+'; install requirements.lock')
    return requirements


def completed(root,*,required=()):
    root=Path(root)
    seal=read(root/'complete.json');relative=Path(seal['attempt'])
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('v25 attempt path escapes output')
    directory=root/relative
    if not directory.resolve().is_relative_to(root.resolve()):raise ValueError('v25 attempt symlink escapes output')
    bindings={}
    for item in seal['artifacts']:
        name=Path(item['path'])
        if name.is_absolute() or '..' in name.parts or name.as_posix()!=item['path']:
            raise ValueError('v25 artifact path escapes attempt or is noncanonical')
        if item['path'] in bindings:raise ValueError('duplicate v25 artifact binding')
        bindings[item['path']]=item
        path=directory/name
        if not path.resolve().is_relative_to(directory.resolve()):raise ValueError('v25 artifact symlink escapes attempt')
        if type(item['bytes']) is not int or path.stat().st_size!=item['bytes'] or sha(path)!=item['sha256']:
            raise ValueError('completed v25 artifact changed: '+str(path))
    paths=list(directory.rglob('*'))
    if any(p.is_symlink() and not p.resolve().is_relative_to(directory.resolve()) for p in paths):
        raise ValueError('v25 artifact symlink escapes attempt')
    actual={p.relative_to(directory).as_posix() for p in paths if p.is_file()}
    if set(bindings)!=actual or not set(required)<=set(bindings):
        raise ValueError('v25 artifact membership differs or required consumed artifact is uncommitted')
    return directory


def population_view(root,evaluation,*,specifications='specifications'):
    """Verify registered sources before retaining only compact paper fields."""
    from .v25.specification import Specification,canonical_bytes
    from .v25.fresh import verify_collection
    from .runs import Manifest,RunSpecifications
    root=Path(root);spec=Specification(specifications)
    plan=read(root/'plan.json')
    if (plan.get('schema')!='born_v25_stage_plan_v1' or plan.get('inputs')!={'mode':'registered','workflow':'v25'}
            or plan.get('scientific_digest')!=spec.digest or not isinstance(plan.get('runtime'),dict)):
        raise ValueError('paper comparison requires the registered public reproduce v25 run')
    stage=root/evaluation
    required=('population.json','orientation_description.json') if evaluation=='cross-term' else ('population.json',)
    directory=completed(stage/'evaluation',required=required)
    evaluation_plan=read(stage/'evaluation/plan.json')
    if (evaluation_plan.get('schema')!='born_v25_stage_plan_v1'
            or evaluation_plan.get('scientific_digest')!=spec.digest
            or canonical_bytes(evaluation_plan.get('runtime'))!=canonical_bytes(plan['runtime'])
            or set(evaluation_plan.get('inputs',{}))!={'units_sha256'}):
        raise ValueError('v25 evaluation plan schema, scientific digest or runtime differs')
    expected=[job.id for job in RunSpecifications(spec.directory).grid('v25-'+evaluation)]
    runset=read(stage/'runs/runset.json')
    invocation_ids=[row['id'] for row in runset['invocations']]
    if invocation_ids!=expected or len(set(invocation_ids))!=len(invocation_ids) or set(Manifest(stage/'runs').completed())!=set(expected):
        raise ValueError('v25 registered invocation completion/grid membership differs')
    collections=[p for p in sorted((stage/'units').glob('collection_*.json'))
                 if sha(p)==evaluation_plan['inputs']['units_sha256']]
    # Resumes may publish multiple byte-identical copies of the committed stream.
    if not collections:raise ValueError('v25 evaluation has no committed unit collection')
    collection=read(collections[0])
    if (collection.get('schema')!='born_v25_closed_units_v1' or collection.get('mode')!='fresh'
            or collection.get('complete') is not True or collection.get('scientific_digest')!=spec.digest or collection.get('evaluation')!=evaluation):
        raise ValueError('v25 collection is incomplete or differs from registration')
    if ([row['invocation_id'] for row in collection['dispositions']]!=expected
            or any(row['status']!='completed' for row in collection['dispositions'])):
        raise ValueError('v25 registered cohort/disposition order differs')
    verify_collection(collections[0],collection)
    identities=[row['kind_cell_id'] for row in collection['units']]
    if len(set(identities))!=len(identities):raise ValueError('duplicate v25 unit identities')
    members={kind:{} for kind in ('raw','package')}
    for row in collection['units']:
        if row['kind'] not in members or type(row['eligibility']) is not bool:
            raise ValueError('invalid v25 kind or eligibility')
        group=members[row['kind']]
        if row['unit_id'] in group:raise ValueError('duplicate v25 paired unit identity')
        group[row['unit_id']]=row['eligibility']
    if members['raw']!=members['package']:raise ValueError('v25 paired unit membership/eligibility differs')
    count=sum(members['raw'].values());del collection;gc.collect()
    population=read(directory/'population.json')
    if (population.get('schema')!='born_v25_population_v1' or population.get('evaluation')!=evaluation
            or population.get('scientific_digest')!=spec.digest or population.get('mode')!='registered'
            or type(population.get('bootstrap_replicates')) is not int
            or population['bootstrap_replicates']!=spec.science['inference']['bootstrap']['replicates']):
        raise ValueError('v25 population headers differ from registered evaluation')
    compact={'paper_values':population['paper_values'],'joint':population['joint'],
             'cases':count,'comparisons':sum('serviceability_factor_two' not in k for k in population['paper_values'])}
    compact['minimum_lower']=min(v['lower'] for k,v in compact['paper_values'].items()
                                 if 'serviceability_factor_two' not in k)
    if evaluation=='competitor':compact['configs']=population['statistics']['package::L_clipped_linear']['hierarchy_counts']['configs']
    del population;gc.collect()
    if evaluation=='cross-term':
        compact['invocations']=len(invocation_ids)
        description=read(directory/'orientation_description.json')
        if description['status']!='complete' or description['registered_slots']!=description['complete_slots']:
            raise ValueError('v25 orientation distribution is incomplete')
        compact['orientation']={k:description[k] for k in ('registered_slots','summaries')}
        compact['orientation']['historical_svd']=description['references']['historical_svd']['contrasts']
    compact['provenance']={'sources':[str(root/'plan.json'),str(stage/'evaluation/plan.json'),
        str(stage/'runs/runset.json'),str(stage/'runs/manifest.jsonl'),str(collections[0]),str(directory/'population.json')]+
        ([str(directory/'orientation_description.json')] if evaluation=='cross-term' else []),
        'aggregation':'registered plan/population headers and sealed fresh collection verification; complete registered grids; paired eligible unit identity counts; stored paper_values; minimum simultaneous competitor lower bound; complete orientation summaries'}
    return compact


def selected_canonical(root,components,specifications):
    """This is the retained RI fixture, not a member of the fresh v25 cohort."""
    import numpy as np
    from .v25.canonical import construct
    context=read(root/components['worked']/'selected/CONTEXT.json');identity=context['identity']
    census=root/components['census'];summary=read(census/'complete.json')['summary']
    inventory=read(census/summary['inventory_directory']/'INVENTORY.json')
    wanted={'experiment':identity['exp'],'config_or_null':identity['config'],'seed':identity['seed'],
            'scale':identity['scale'],'resolution':identity['k'],'step':identity['step_index']}
    rows=[r for r in inventory if all(r['provenance_key'][k]==v for k,v in wanted.items())]
    if len(rows)!=1:raise ValueError('selected canonical fixture has no unique source identity join')
    uid=rows[0]['unit_id']
    refinement=tuple(read(Path(specifications)/'predictive_v25.json')['scientific']['canonical_diagonal']['rounding']['refinement_bits'])
    cert=construct(context['born']['sym_eigvec_basis'],context['born']['p_theory'],refinement=refinement)
    if cert['status']!='certified':raise ValueError('selected canonical construction unresolved')
    attachments=root/components['attachments'];directory=attachments/read(attachments/'complete.json')['summary']['directory']
    result={}
    for view in ('raw','pkg'):
        row=read(directory/'contexts'/uid/(view+'_original.jsonl'))
        if row['unit_id']!=uid:raise ValueError('selected canonical attachment identity differs')
        empirical=row['unrounded_y_raw' if view=='raw' else 'unrounded_y_pkg']
        if empirical!=[x/row['total_count'] for x in row['integer_counts']]:raise ValueError('selected empirical law differs')
        matrix=row['M_raw_or_content_hash' if view=='raw' else 'M_pkg_or_content_hash']
        mapped=(np.asarray(matrix)@np.asarray(cert['q_diag_canonical'])).tolist()
        result[view]=.5*math.fsum(abs(a-b) for a,b in zip(mapped,empirical,strict=True))-row['dtv_loss']['q_full']
    return result


def canonical_population(root,components,specifications):
    """Run the public canonical constructor in its pinned, fresh runtime."""
    import os
    import subprocess
    import sys
    command=[sys.executable,'-m','born_ladder','reproduce','paper-canonical',
             '--census',str(root/components['census']),'--attachments',str(root/components['attachments']),
             '--specifications',str(specifications)]
    environment=dict(os.environ)
    environment.pop('BORN_LADDER_STAGE_PROFILE',None)
    # Managed routing sets dispatch before the child's first NumPy import.
    try:child=subprocess.run(command,env=environment,stdout=subprocess.PIPE,text=True,check=True)
    except subprocess.CalledProcessError as error:
        raise ValueError('canonical population construction failed; no verified paper summary (child exit '+str(error.returncode)+')') from error
    return json.loads(child.stdout)


def binding(entry,name):
    if name in ('SelectedDCanonicalRaw','SelectedDCanonicalPkg'):
        return {'macro':name,'view':'v25_selected','pointer':'/'+('raw' if name.endswith('Raw') else 'pkg')}
    source=entry.get('source','');before=source.split('#',1)[0]
    if '/v25/' not in before:return None
    evaluation='competitor' if '/v25/competitor/' in before else 'cross-term'
    if name in ('CorrCompetitorCases','CorrCrossCases'):pointer='/cases'
    elif name=='CorrCrossInvocations':pointer='/invocations'
    elif name=='CorrCompetitorComparisons':pointer='/comparisons'
    elif name=='CorrCompetitorConfigs':pointer='/configs'
    elif name=='CorrCompetitorLower':pointer='/minimum_lower'
    elif name=='OrientationCount':pointer='/orientation/registered_slots'
    elif name.startswith('HistSvd'):pointer='/orientation/historical_svd/'+('raw' if name.endswith('Raw') else 'package')
    elif 'orientation_description.json' in before:
        pointer='/orientation'+source.split('#',1)[1].split(';',1)[0].strip()
    else:pointer=source.split('#',1)[1].split(' [',1)[0].split(';',1)[0].strip()
    return {'macro':name,'view':'v25','evaluation':evaluation,'pointer':pointer}
