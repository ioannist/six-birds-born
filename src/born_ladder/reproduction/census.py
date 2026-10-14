"""Structural-only census production from closed P2a/P2b outputs.

Reference certificates and performance attachments are never production
inputs. Logical identities and execution locations are bound independently.
"""
from .checkpoints import numeric_plan
from concurrent.futures import ProcessPoolExecutor, as_completed
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import resource
import time

from born_ladder.archive import canonical, put, sha
from born_ladder import metadata
from born_ladder.robust_census import integer_record, scan_records
from .numerical_runtime import numerical_runtime
from .stage_environment import stage_identity
from .runs import Manifest, exclusive_output, validate_output, THREAD_VARIABLES
from .units import relative_file, source_inputs, artifacts, specification_files
from .census_extension import atom_classes, robust_outcomes, diagnostic_counts
from .census_writers.build_inventory import rebuild_inventory
from .census_writers.certificates import construct_context
from .census_writers.legacy_trine import witness as symbolic_witness


def read(path):
    return json.loads(Path(path).read_bytes())


def matching_file(root, name, digest):
    path = relative_file(root,name)
    if sha(path)!=digest:
        raise ValueError('census input commitment differs: '+name)
    return path


def collection_inputs(units, evaluation, logical_sources=None):
    """Resolve a closed snapshot, with optional attested logical source names.

    No historical fields are synthesized from current execution metadata. A
    retained logical-name map can come from its actual acquisition manifest;
    every mapped capture/attempt is matched to current P2b bytes by hash.
    """
    units = Path(units).resolve(strict=True)
    collections = sorted((units/'collections').glob('collection_*/collection.json'))
    if not collections:
        raise ValueError('no closed P2b collection under --units')
    collection = collections[-1]
    info = read(collection)['evaluations'][evaluation]
    parent = units/info['path']
    if Path(info['path']).is_absolute() or '..' in Path(info['path']).parts or not parent.is_dir():
        raise ValueError('unsafe or missing closed collection directory')
    campaign = read(parent/'campaign.json')
    if campaign.get('schema')!='born_public_structural_campaign_v1':
        raise ValueError('expected a public P2b structural campaign')
    inv_path = matching_file(units,**{'name':campaign['invocation_manifest']['path'],
                                     'digest':campaign['invocation_manifest']['sha256']})
    structural = matching_file(units,campaign['structural_manifest']['path'],campaign['structural_manifest']['sha256'])
    unit_path = parent/info['units_file']
    names = read(logical_sources) if logical_sources else None
    if names is not None and names.get('schema')!='born_census_logical_sources_v1':
        raise ValueError('unsupported logical-source correspondence')
    supplied = {r['invocation_id']:r for r in names['captures']} if names else {}
    if names and len(supplied)!=len(names['captures']):
        raise ValueError('duplicate logical-source identity')
    if names and set(supplied)!={r['invocation_id'] for r in campaign['stdout_execution_bindings']}:
        raise ValueError('logical correspondence must cover exactly the closed collection')
    files, bindings = {},[]
    for b in campaign['stdout_execution_bindings']:
        actual = relative_file(units,b['stdout_path'])
        attempt = actual.parent/(b['attempt_record_sha256']+'.attempt.json')
        if sha(actual)!=b['stdout_sha256'] or sha(attempt)!=b['attempt_record_sha256']:
            raise ValueError('P2b source capture or attempt changed')
        row = supplied.get(b['invocation_id'])
        if row:
            if any(row[k]!=b[k] for k in ('stdout_sha256','attempt_record_sha256')):
                raise ValueError('logical-source hash differs from P2b capture')
            name = row['logical_stdout_path']
        else:
            name = b['stdout_path']
        if Path(name).is_absolute() or '..' in Path(name).parts or b['invocation_id'] not in name:
            raise ValueError('unsafe or unrelated logical capture name')
        attempt_name = str(Path(name).parent/attempt.name)
        files[name]=str(actual);files[attempt_name]=str(attempt)
        bindings.append({**b,'stdout_path':name})
    logical_units = names['logical_units_path'] if names else str(unit_path.relative_to(units))
    logical_structural = names['logical_structural_path'] if names else campaign['structural_manifest']['path']
    for name in (logical_units,logical_structural):
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('unsafe logical structural path')
    files[logical_units]=str(unit_path);files[logical_structural]=str(structural)
    adapted = {**campaign,'stdout_execution_bindings':bindings,
               'structural_manifest':{'path':logical_structural,'sha256':sha(structural)}}
    commitments={'collection':sha(collection),'campaign':sha(parent/'campaign.json'),
                 'invocations':sha(inv_path),'units':sha(unit_path),'structural':sha(structural),
                 'logical_sources':sha(logical_sources) if logical_sources else None}
    return units,adapted,inv_path,logical_units,files,commitments,info


def capture_kernels(runs, invocations, bindings, files, output):
    """Bind full-capture matrices to the same successful executions as units.

    A tagged JSONL envelope exposes unchanged matrix bytes to the recovered
    constructor. Its synthetic exponent metadata is explicitly an I/O adapter
    for K itself; it is not a historical Sequential-probe observation.
    """
    sources,_=source_inputs(runs)
    for iv in invocations:
        key=tuple(iv[k] for k in ('experiment','config_or_null','seed','scale'))
        entry=sources.get(key)
        if entry is None or entry['execution_status']!='completed':
            raise ValueError('closed unit has no matching completed P2a capture: '+iv['invocation_id'])
        b=next(b for b in bindings if b['invocation_id']==iv['invocation_id'])
        if entry['stdout_sha256']!=b['stdout_sha256'] or entry['attempt_sha256']!=b['attempt_record_sha256']:
            raise ValueError('P2a/P2b execution binding differs: '+iv['invocation_id'])
        matching_file(Path(entry['root']),entry['stdout_path'],entry['stdout_sha256'])
        if 'attempt_path' in entry:
            matching_file(Path(entry['root']),entry['attempt_path'],entry['attempt_sha256'])
    by_key={tuple(iv[k] for k in ('experiment','config_or_null','seed','scale')):iv for iv in invocations}
    kernels={}; input_bindings=[]
    for root in runs:
        root=Path(root).resolve(strict=True)
        if (root/'capture_index.json').exists():
            # Legacy capture indexes may honestly lack native full-capture files.
            continue
        runset=read(root/'runset.json')
        jobs={j['id']:j for j in runset['invocations']}
        for identifier,row in Manifest(root).completed().items():
            job=jobs[identifier]
            key=(job['experiment'],job['configuration'],job['seed'],job['scale'])
            if key not in by_key:
                continue
            iv=by_key[key]
            for artifact in row['artifacts']:
                if not artifact['path'].endswith('.kernel.json'):
                    continue
                path=matching_file(root,artifact['path'],artifact['sha256'])
                body=path.read_text().strip();meta=metadata.metadata(body,{'schema','exp','config','kernel_seed','n'})
                if (meta['schema']!='born_run_kernel_v1' or meta['exp']!=iv['experiment']
                        or meta['kernel_seed']!=iv['seed'] or meta['n']!=iv['scale']):
                    raise ValueError('full kernel capture identity differs')
                if iv['config_or_null'] is not None and meta['config']!=iv['config_or_null']:
                    raise ValueError('full kernel capture configuration differs')
                a=metadata.refs(body,{'kernel'})['kernel'];lo,hi=a['char_range']
                field=body[lo:hi]
                payload='{"tau":1,"t_mid":0,"propagator_mid_to_final":'+field+'}'
                blob=('KEY_SEQUENTIAL_PROBE_JSON '+payload+'\n').encode()
                name='kernel_adapters/'+artifact['sha256']+'.jsonl'
                target=output/name
                if target.exists():
                    if target.read_bytes()!=blob:raise ValueError('kernel adapter changed on resume')
                else:put(target,blob)
                ref=metadata.refs(payload,{'propagator_mid_to_final'})['propagator_mid_to_final']
                pointer={'path':name,'file_sha256':sha(target),'line':1,'byte_offset':0,
                         'payload_sha256':hashlib.sha256(payload.encode()).hexdigest(),**ref,
                         'exponent':1,'matrix_shape':[meta['n'],meta['n']],
                         'source_semantics':'P2a final K, unchanged JSON field bytes; tagged I/O envelope only',
                         'native_capture_sha256':artifact['sha256'],'native_kernel_field_sha256':a['field_sha256']}
                k=(iv['invocation_id'],meta['config'])
                if k in kernels and kernels[k]!=pointer:
                    raise ValueError('conflicting full-matrix captures')
                kernels[k]=pointer;files[name]=str(target)
                input_bindings.append({'invocation_id':iv['invocation_id'],'config':meta['config'],
                    'native_capture_relative_path':artifact['path'],'native_capture_sha256':artifact['sha256'],
                    'kernel_field_sha256':a['field_sha256'],'adapter_path':name,'adapter_sha256':sha(target)})
    return kernels,input_bindings


def original_status(completed, s):
    """Execute the original extra coordinate gate and symbolic implementation."""
    c=completed['certificates']['correspondence']
    correspondence=c['status']
    if Fraction(c['constructor_maximum_difference'])>Fraction(c['threshold_exact']):
        correspondence='FAILED'
    trine=None
    try:
        trine=symbolic_witness(s)[0]
        premise={'status':'PASS'}
    except Exception as error:
        premise={'status':'FAILED','error_type':type(error).__name__,'error':str(error)}
    remaining=[v['status'] for k,v in completed['certificates'].items() if k not in ('C_premises','correspondence')]
    statuses=remaining+[premise['status'],correspondence]
    result={'status':'PASS' if all(x=='PASS' for x in statuses) else 'FAILED',
            'correspondence_status':correspondence,'C_premises':premise,
            'classification':'extra SVD-coordinate requirement' if correspondence=='FAILED' else
                             'symbolic implementation failure' if premise['status']!='PASS' else 'completed original implementation',
            'origin':'re-executed original implementation checks on explicit construction inputs; not copied historical verdicts'}
    return result,trine


def construct_one(task):
    for key in THREAD_VARIABLES:os.environ[key]='1'
    start,cpu=time.monotonic(),time.process_time()
    output=Path(task['output'])
    try:
        result=construct_context(task['index'],task['row'],task['input_view'],output,
                                 task['specifications'],[], 'structural_completion_certificate.json')
        directory=output/'contexts'/task['row']['unit_id']
        if result['overall_status']!='PASS':
            raise ValueError('completed structural certificate failed: '+str(result['failures']))
        context=read(directory/'CONTEXT.json')
        old,trine=original_status(result,Fraction(context['exact']['s']))
        put(directory/'original_implementation.json',old)
        if trine is not None:put(directory/'six_state_symbolic_original.json',trine)
        labels=[context['lens'][k] for k in ('raw_by_state','package_by_state','joint_by_state')]
        record=integer_record(context['exact']['w'],labels)
        robust=scan_records([record],require_bound=False)
        robust['cases'][0]['case']=task['index']
        robust['minimum_cases']=[task['index']]
        put(directory/'maximal_gap_witness.json',robust)
        put(directory/'integer_frame.json',record)
        put(directory/'atom_classes.json',atom_classes(context,result))
        status='completed'
        disposition={'status':status,'completion_status':result['overall_status'],
                     'original_status':old['status'],'original_classification':old['classification'],
                     'robust_status':robust['status'],'context_directory':str(directory.relative_to(output)),
                     'failures':[]}
    except Exception as error:
        disposition={'status':'failed','error':type(error).__name__+': '+str(error)}
        put(output/'failure.json',disposition)
    return {**disposition,'wall_seconds':time.monotonic()-start,'cpu_seconds':time.process_time()-cpu,
            'worker_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def next_attempt(root):
    root.mkdir(parents=True,exist_ok=True)
    n=1
    while (root/f'attempt_{n:04d}').exists():n+=1
    path=root/f'attempt_{n:04d}';path.mkdir()
    return path


def verify_artifacts(output, entries):
    for entry in entries:
        matching_file(output,entry['path'],entry['sha256'])


def amendment_resume_plan(plan):
    """Adapter locations are storage; their committed bytes and keys are fixed."""
    result=numeric_plan(plan)
    result.pop('census_amendment',None)
    result['logical_to_execution_files']={k:(k if k.startswith('kernel_adapters/') else v)
                                         for k,v in result['logical_to_execution_files'].items()}
    return result


def recover_completed_constructions(output, manifest):
    """Append corrected dispositions without overwriting previous evidence."""
    from .census_writers.certificates import registered_correspondence
    latest={r['invocation_id']:r for r in manifest.rows if r['event']=='finished'}
    recovered=0
    for entry in latest.values():
        # Only the old threshold-only failure is recoverable. Actual errors
        # remain failed and will require fresh construction.
        if entry.get('completion_status')!='PASS' or not entry.get('context_directory'):
            continue
        if entry['status']!='completed' and entry.get('failures')!=['maximal-gap bound 3/20 not established']:
            continue
        if entry.get('census_amendment_applied'):continue
        verify_artifacts(output,entry['artifacts'])
        name=Path(entry['directory'])/entry['context_directory']
        if name.is_absolute() or '..' in name.parts:raise ValueError('unsafe recovery context path')
        directory=output/name
        cert=read(directory/'structural_completion_certificate.json')
        if cert['overall_status']!='PASS' or cert['unit_id']!=entry['invocation_id'] or any(c['status']!='PASS' for c in cert['certificates'].values()) or not registered_correspondence(cert['certificates']['correspondence']):
            raise ValueError('invalid completed certificate in amendment resume')
        context=read(directory/'CONTEXT.json')
        frame=integer_record(context['exact']['w'],[context['lens'][f] for f in ('raw_by_state','package_by_state','joint_by_state')])
        if frame!=read(directory/'integer_frame.json'):raise ValueError('recovery integer frame differs')
        robust=scan_records([frame],require_bound=False)
        robust['cases'][0]['case']=cert['index'];robust['minimum_cases']=[cert['index']]
        if robust!=read(directory/'maximal_gap_witness.json'):raise ValueError('recovery maximal-gap certificate differs')
        classes=atom_classes(context,cert)
        target=directory/'atom_classes.json'
        if target.exists():
            if read(target)!=classes:raise ValueError('recovery atom classes differ')
        else:put(target,classes)
        manifest.append({**entry,'status':'completed','failures':[],
                         'census_amendment_applied':True,'reclassified_from_status':entry['status'],
                         'artifacts':artifacts(output/entry['directory'],output)})
        recovered+=1
    return recovered


def run_census(*, units, runs, output, workers=1, specifications='specifications',
               evaluation='cross-term', logical_sources=None, apply_amendment=False):
    started,cpu=time.monotonic(),time.process_time()
    specifications=Path(specifications).resolve(strict=True)
    environment=stage_identity(specifications,'verification')
    output=validate_output(output,specifications.parent)
    units=Path(units).resolve(strict=True);runs=[Path(r).resolve(strict=True) for r in runs]
    if any(output==r or output.is_relative_to(r) or r.is_relative_to(output) for r in [units,*runs]):
        raise ValueError('census outputs and earlier-stage inputs must be disjoint')
    if not 1<=workers<=8:raise ValueError('census worker count must be between 1 and 8')
    output.mkdir(parents=True,exist_ok=True)
    with exclusive_output(output):
        root,campaign,inv_path,unit_name,files,commitments,info=collection_inputs(units,evaluation,logical_sources)
        invocations=read(inv_path)
        kernels,kernel_bindings=capture_kernels(runs,invocations,campaign['stdout_execution_bindings'],files,output)
        runtime=numerical_runtime(1)
        plan={'schema':'born_census_plan_v1','evaluation':evaluation,'input_commitments':commitments,
              'numerical_runtime':runtime,'stage_environment':environment,
              'specifications':specification_files(specifications),
              'source_code':{str(p.relative_to(Path(__file__).resolve().parents[3])):sha(p)
                            for p in sorted(Path(__file__).resolve().parents[1].rglob('*.py'))},
              'capture_bindings':kernel_bindings,'logical_to_execution_files':files,
              'expected_invocations':info['expected_invocations'],'completed_invocations':info['completed_invocations'],
              'no_performance_attachments':True,'no_reviewed_outputs':True,'no_proof_scratch_notes':True}
        amendment=specifications/'census_amendment.md'
        plan['census_amendment']={'path':amendment.name,'sha256':sha(amendment)}
        plan_path=output/'census_plan.json'
        if plan_path.exists():
            previous=read(plan_path)
            if previous['numerical_runtime']!=runtime:
                raise ValueError('census resume numerical runtime differs')
            if numeric_plan(previous)!=numeric_plan(plan):
                if not apply_amendment or previous.get('census_amendment') or amendment_resume_plan(previous)!=amendment_resume_plan(plan):
                    raise ValueError('census resume inputs or specification differ; old census requires --apply-amendment')
                amended_path=output/'census_amendment_plan.json'
                if amended_path.exists():
                    if numeric_plan(read(amended_path))!=numeric_plan(plan):raise ValueError('census amendment plan differs')
                else:put(amended_path,plan)
        else:put(plan_path,plan)
        finished_path=output/'complete.json'
        if finished_path.exists():
            complete=read(finished_path);verify_artifacts(output,complete['artifacts'])
            saved=complete['summary']
            if not info['complete'] or saved['selected_count']!=int(saved['rank_counts'].get('2',0)):
                raise ValueError('historical availability subset cannot satisfy the amended full rank-two census')
            return {**complete['summary'],'resumed':True,'launched':0}
        inventory_seal=output/'inventory_complete.json'
        if inventory_seal.exists():
            sealed=read(inventory_seal);verify_artifacts(output,sealed['artifacts'])
            inventory_root=output/sealed['directory'];inventory_summary=sealed['summary']
        else:
            attempt=next_attempt(output/'inventory_attempts')
            put(attempt/'campaign.json',campaign)
            inventory_root=attempt/'inventory'
            inventory_summary=rebuild_inventory(archive_root=root,campaign_path=attempt/'campaign.json',
                invocation_path=inv_path,unit_logical_path=unit_name,output_dir=inventory_root,
                input_files=files,kernel_sources=kernels,historical_inputs=bool(logical_sources))
            put(inventory_seal,{'directory':str(inventory_root.relative_to(output)),
                'summary':inventory_summary,'artifacts':artifacts(inventory_root,output)})
        rows=read(inventory_root/'INVENTORY.json')
        manifest=Manifest(output)
        recovered=recover_completed_constructions(output,manifest) if apply_amendment else 0
        completed=manifest.completed()
        input_view={'schema':'born_structural_input_view_v1','root':str(root),'files':files}
        tasks=[]
        for index,row in enumerate(rows):
            uid=row['unit_id']
            if uid in completed:continue
            attempt=next_attempt(output/'construction_attempts'/uid)
            task={'index':index,'row':row,'input_view':input_view,'output':str(attempt),'specifications':str(specifications)}
            manifest.append({'event':'started','invocation_id':uid,'directory':str(attempt.relative_to(output))})
            tasks.append(task)
        construction_start=time.monotonic()
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures={pool.submit(construct_one,t):t for t in tasks}
            for future in as_completed(futures):
                task=futures[future];attempt=Path(task['output'])
                try:result=future.result()
                except Exception as error:
                    result={'status':'failed','error':type(error).__name__+': '+str(error)}
                    put(attempt/'failure.json',result)
                manifest.append({'event':'finished','invocation_id':task['row']['unit_id'],
                    'directory':str(attempt.relative_to(output)),**result,'artifacts':artifacts(attempt,output)})
                print('census context',task['index'],task['row']['unit_id'],result['status'],flush=True)
        completed=manifest.completed()
        latest={r['invocation_id']:r for r in manifest.rows if r['event']=='finished'}
        originals,completions,robust_rows=[],[],[]
        for index,row in enumerate(rows):
            uid=row['unit_id'];entry=latest.get(uid)
            directory=(output/entry['directory']/entry['context_directory']) if entry and entry.get('context_directory') else None
            if directory and (directory/'original_implementation.json').exists():
                originals.append({'index':index,'unit_id':uid,**read(directory/'original_implementation.json')})
            else:
                originals.append({'index':index,'unit_id':uid,'status':'NOT RUN',
                    'classification':'prerequisite construction incomplete','disposition':entry})
            if directory and (directory/'maximal_gap_witness.json').exists():
                robust_rows.extend(read(directory/'maximal_gap_witness.json')['cases'])
            if entry and entry['status']=='completed':
                if not directory or not (directory/'maximal_gap_witness.json').is_file() or not (directory/'structural_completion_certificate.json').is_file():
                    raise ValueError('completed census context has incomplete evidence')
                completions.append({'index':index,'unit_id':uid,'status':entry['completion_status'],
                                    'context_directory':str(directory.relative_to(output))})
            else:completions.append({'index':index,'unit_id':uid,'status':'FAILED','disposition':entry})
        if not info['complete'] or len(rows)!=int(inventory_summary['rank_counts'].get('2',0)):
            raise ValueError('full rank-two census requires complete collection and construction inputs')
        sequence=len(list((output/'summaries').glob('summary_*')))+1
        summary_root=output/'summaries'/f'summary_{sequence:04d}'
        summary_root.mkdir(parents=True,exist_ok=False)
        put(summary_root/'original_implementation_results.json',originals)
        put(summary_root/'structural_completion_results.json',completions)
        put(summary_root/'maximal_gap_witnesses.json',robust_rows)
        outcomes=robust_outcomes(robust_rows)
        put(summary_root/'robust_bound_outcomes.json',outcomes)
        summary={**inventory_summary,'completed':len(completed),'failed':len(rows)-len(completed),
                 'execution_status':'PASS' if len(completed)==len(rows) else 'FAILED',
                 'completion_status':'PASS' if len(completed)==len(rows) else 'FAILED',
                 'recovered_constructions':recovered,
                 'registered_robust_pass':outcomes['registered_pass'],'registered_robust_fail':outcomes['registered_fail'],
                 'registered_robust_verdict':outcomes['registered_verdict'],
                 'amended_robust_pass':outcomes['amended_pass'],'amended_robust_fail':outcomes['amended_fail'],
                 'amended_robust_verdict':outcomes['amended_verdict'],
                 **diagnostic_counts(originals),
                 'launched':len(tasks),'inventory_directory':str(inventory_root.relative_to(output)),
                 'summary_directory':str(summary_root.relative_to(output)),
                 'original_pass':sum(r['status']=='PASS' for r in originals),
                 'original_extra_coordinate_failures':sum(r['classification']=='extra SVD-coordinate requirement' for r in originals),
                 'original_symbolic_failures':sum(r['classification']=='symbolic implementation failure' for r in originals),
                 'construction_wall_seconds':time.monotonic()-construction_start,
                 'wall_seconds':time.monotonic()-started,'coordinator_cpu_seconds':time.process_time()-cpu,
                 'construction_cpu_seconds':sum(r.get('cpu_seconds',0) for r in latest.values()),
                 'worker_peak_rss_kib':max((r.get('worker_peak_rss_kib',0) for r in latest.values()),default=0),
                 'coordinator_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                 'output_bytes':sum(p.stat().st_size for p in output.rglob('*') if p.is_file()),
                 'no_performance_fields_decoded':True,'source_collection_complete':info['complete']}
        put(summary_root/'summary.json',summary)
        if not summary['failed']:
            put(finished_path,{'status':'PASS','summary':summary,'artifacts':artifacts(output,output)})
        return summary
