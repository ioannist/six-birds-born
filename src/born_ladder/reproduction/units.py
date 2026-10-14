"""Public capture-to-unit coordinator, with no archive-result construction input."""
from __future__ import annotations
from .checkpoints import numeric_plan, scientific_specification_file

from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import time

from born_ladder.snapshot.completeness import invocation_id_for
from born_ladder.snapshot.frozen_spec import canonical_json_bytes
from .runs import Manifest, RunSpecifications, THREAD_VARIABLES, digest, exclusive_output, validate_output
from .specification import PublicSpecification
from .numerical_runtime import numerical_runtime
from .stage_environment import check_current, profile_path
from .worker_pool import invocation_results


def relative_file(root, name):
    name = Path(name)
    if name.is_absolute() or '..' in name.parts:
        raise ValueError('input/output artifact paths must be relative children')
    path = root/name
    if not path.is_file():
        raise ValueError('missing input artifact: '+str(path))
    return path


def write_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def specification_files(directory):
    # Specifications are small enough to commit every public scientific JSON,
    # not private recovery records or README text, to this stage's plan.
    return [{'path':str(p.relative_to(directory)), 'sha256':digest(p)}
            for p in sorted(directory.rglob('*.json'))
            if p.name != 'source_recovery.json' and scientific_specification_file(p.name)]


def source_inputs(roots):
    """Read explicit captures; preserve historical metadata, never fabricate it."""
    available = {}
    commitments = []
    for root in roots:
        root = Path(root).resolve(strict=True)
        if (root/'capture_index.json').exists():
            index = root/'capture_index.json'
            document = json.loads(index.read_bytes())
            if document['schema'] != 'born_unit_capture_index_v1':
                raise ValueError('unsupported explicit capture index')
            rows = document['invocations']
            commitments.append({'type':'explicit_capture_index','sha256':digest(index)})
            for entry in rows:
                entry = dict(entry)
                entry['root'] = str(root)
                key = (entry['invocation']['experiment'], entry['invocation']['config_or_null'],
                       entry['invocation']['seed'], entry['invocation']['scale'])
                if key in available:
                    raise ValueError('duplicate input invocation identity')
                available[key] = entry
        else:
            plan_file = root/'runset.json'
            plan = json.loads(plan_file.read_bytes())
            manifest = Manifest(root)
            manifest.completed()  # Verify completed artifacts, not just stdout.
            latest = {r['invocation_id']:r for r in manifest.rows if r['event']=='finished'}
            commitments.append({'type':'p2a_runset','sha256':digest(plan_file)})
            for job in plan['invocations']:
                row = latest.get(job['id'])
                if row is None:
                    continue
                key = (job['experiment'], job['configuration'], job['seed'], job['scale'])
                entry = {'root':str(root), 'execution_status':row['status'],
                    'invocation':{'experiment':job['experiment'], 'config_or_null':job['configuration'],
                                  'seed':job['seed'], 'scale':job['scale']},
                    'attempt_record':row, 'attempt_sha256':hashlib.sha256(canonical_json_bytes(row)).hexdigest(),
                    'stdout_path':str(Path(row['directory'])/'stdout.bin')}
                artifact = next((a for a in row['artifacts'] if a['path']==entry['stdout_path']),None)
                entry['stdout_sha256'] = None if artifact is None else artifact['sha256']
                if key in available:
                    # Only identical scientific capture/attempt bindings can be
                    # coalesced; differing reruns need an explicit source choice.
                    previous = available[key]
                    if any(previous.get(k)!=entry.get(k) for k in ('stdout_sha256','attempt_sha256','execution_status')):
                        raise ValueError('conflicting input invocation captures')
                available[key] = entry
    return available, commitments


def planned_jobs(directory, grid):
    document = json.loads((directory/'units.json').read_bytes())
    if document['schema'] != 'born_unit_grids_v1':
        raise ValueError('unsupported unit grid')
    run_specs = RunSpecifications(directory)
    definition = document['grids'][grid]
    if grid != 'smoke':
        selected = {definition['evaluation']:run_specs.grid(
                    document['evaluations'][definition['evaluation']]['run_grid'])}
    else:
        jobs = [j for g in definition['include_run_grids'] for j in run_specs.grid(g)]
        for selection in definition['selections']:
            source = run_specs.grid(selection['run_grid'])
            seed = list(dict.fromkeys(j.seed for j in source))[selection['seed_index']]
            chosen = [j for j in source if j.seed==seed and j.experiment==selection['experiment']
                      and j.configuration==selection['configuration']]
            if len(chosen)!=1:
                raise ValueError('smoke capture selection is not unique')
            jobs.extend(chosen)
        selected = {e:[j for j in jobs if e!='competitor' or j.experiment==definition['competitor_experiment']]
                    for e in definition['evaluations']}
    amendments = json.loads((directory/document['amendment_map']).read_bytes())
    result = []
    for evaluation,jobs in selected.items():
        version = amendments['stages'][document['evaluations'][evaluation]['version_stage']]
        spec = PublicSpecification(directory, version)
        source = getattr(spec,'_g2c_source_spec',spec)
        # Preserve the historical canonical stream ordering, independently of
        # completion order or P2a scheduling order.
        if document['evaluations'][evaluation]['unit_order']=='registered_experiment_configuration_seed_scale':
            experiments = list(dict.fromkeys(j.experiment for j in jobs))
            configurations = list(dict.fromkeys(j.configuration for j in jobs))
            seeds = list(dict.fromkeys(j.seed for j in jobs))
            scales = list(dict.fromkeys(j.scale for j in jobs))
            jobs = sorted(jobs,key=lambda j:(experiments.index(j.experiment),
                configurations.index(j.configuration),seeds.index(j.seed),scales.index(j.scale)))
        ordered = []
        for job in jobs:
            identifier = invocation_id_for(source, experiment=job.experiment,
                config_or_null=job.configuration, seed=job.seed, scale=job.scale)
            ordered.append({'invocation_id':evaluation+'__'+identifier, 'evaluation':evaluation,
                'version':version, 'identity':identifier, 'experiment':job.experiment,
                'config_or_null':job.configuration, 'seed':job.seed, 'scale':job.scale})
        if document['evaluations'][evaluation]['unit_order']=='lexicographic_invocation_id':
            ordered.sort(key=lambda job:job['identity'])
        result.extend(ordered)
    return result, document


def check_worker_runtime(task):
    """Validate this computing process after the scientific modules import."""
    profile = json.loads(profile_path(task['specifications'], 'predictive').read_bytes())
    if task['threads'] != profile['threads']:
        raise ValueError('predictive worker thread policy differs from its stage profile')
    runtime = check_current(profile)
    if runtime != task['numerical_runtime']:
        raise ValueError('predictive worker numerical runtime differs from its coordinator plan')
    return runtime


def construct_one(task):
    """One bounded-memory worker; only stdout, metadata and public specs are read."""
    for key in THREAD_VARIABLES:
        os.environ[key] = str(task['threads'])
    from .unit_builders import build_invocation
    started, cpu = time.monotonic(), time.process_time()
    directory = Path(task['directory'])
    entry, job = task['input'], task['job']
    result = {'status':'failed', 'unit_rows':0}
    try:
        check_worker_runtime(task)
        if entry['execution_status']!='completed':
            raise ValueError('input execution is '+entry['execution_status'])
        root = Path(entry['root'])
        stdout_path = relative_file(root, entry['stdout_path'])
        stdout = stdout_path.read_bytes()
        if hashlib.sha256(stdout).hexdigest()!=entry['stdout_sha256']:
            raise ValueError('capture stdout hash differs')
        if 'attempt_path' in entry:
            attempt = relative_file(root, entry['attempt_path']).read_bytes()
        else:
            attempt = canonical_json_bytes(entry['attempt_record'])
        if hashlib.sha256(attempt).hexdigest()!=entry['attempt_sha256']:
            raise ValueError('capture attempt hash differs')
        write_new(directory/'stdout.bin', stdout)
        write_new(directory/(entry['attempt_sha256']+'.attempt.json'),attempt)
        invocation = dict(entry['invocation'])
        if 'invocation_id' in invocation and invocation['invocation_id']!=job['identity']:
            raise ValueError('capture invocation metadata identity differs')
        invocation['invocation_id'] = job['identity']
        invocation.setdefault('required_emission_families',
            ['KEY_BORN_PROBE_JSON','KEY_DISCOVERY_GRADE_JSON','KEY_AUDIT_JSON'])
        spec = PublicSpecification(task['specifications'], job['version'])
        built = build_invocation(spec, job['evaluation'], stdout, invocation, entry['attempt_sha256'])
        for name,raw in built.files.items():
            # Control links retain the registered basename; scope it explicitly
            # to this invocation, then write that same closed byte stream here.
            write_new(directory/name,raw)
        definitions = task['evaluation_definition']
        if definitions.get('controls_file') and 'controls.jsonl' in built.files:
            write_new(directory/definitions['controls_file'],built.files['controls.jsonl'])
        write_new(directory/'invocation.json',canonical_json_bytes(invocation))
        result = built.disposition
    except Exception as error:
        result = {'status':'input_incomplete' if entry['execution_status']!='completed' else 'failed',
                  'unit_rows':0, 'error':type(error).__name__+': '+str(error)}
        write_new(directory/'failure.json',canonical_json_bytes(result))
    return {**result, 'wall_seconds':time.monotonic()-started,
            'cpu_seconds':time.process_time()-cpu,
            'worker_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'worker_pid':os.getpid()}


def artifacts(directory, output):
    return [{'path':str(p.relative_to(output)), 'bytes':p.stat().st_size, 'sha256':digest(p)}
            for p in sorted(directory.rglob('*')) if p.is_file()]


def assemble(output, jobs, completed, sources, document, sequence):
    """Publish a new closed snapshot; never replace an earlier snapshot."""
    destination = output/'collections'/f'collection_{sequence:04d}'
    destination.mkdir(parents=True,exist_ok=False)
    collection = {'schema':'born_unit_collection_v1','evaluations':{}}
    latest = {r['invocation_id']:r for r in Manifest(output).rows if r['event']=='finished'}
    for evaluation,definition in document['evaluations'].items():
        expected = [j for j in jobs if j['evaluation']==evaluation]
        if not expected:
            continue
        selected = [completed[j['invocation_id']] for j in expected if j['invocation_id'] in completed]
        counts = sum(r['unit_rows'] for r in selected)
        products = {'units.jsonl':definition['units_file'], 'structural.jsonl':'structural_manifest.jsonl',
                    'admission.jsonl':'admission.jsonl'}
        if evaluation=='cross-term':
            products.update({'controls.jsonl':definition['controls_file'],
                            'package_reconstruction.jsonl':definition['package_reconstruction_file']})
        parent = destination/evaluation;parent.mkdir()
        bindings,invocations,dispositions = [],[],[]
        for job in expected:
            row = completed.get(job['invocation_id'])
            key = (job['experiment'],job['config_or_null'],job['seed'],job['scale'])
            entry = sources.get(key)
            construction = latest.get(job['invocation_id'])
            dispositions.append({'invocation_id':job['identity'],
                'status':'completed' if row else 'missing_input' if entry is None else
                         'input_'+entry['execution_status'] if entry['execution_status']!='completed' else 'construction_not_completed',
                'construction_status':None if construction is None else construction['status'],
                'attempt_directory':None if construction is None else construction['directory'],
                'reason':None if construction is None else construction.get('error',construction.get('findings'))})
        # Close the entire control stream before binding aggregate unit links.
        ordered_products = sorted(products.items(),key=lambda item:item[0]=='units.jsonl')
        for name,target in ordered_products:
            with (parent/target).open('xb') as stream:
                for row in selected:
                    source = output/row['directory']/name
                    if source.exists():
                        with source.open('rb') as handle:
                            if name=='units.jsonl' and evaluation=='cross-term':
                                control_sha = digest(parent/definition['controls_file'])
                                for line in handle:
                                    unit = json.loads(line)
                                    unit['applicable_control_record_links'] = [{
                                        'path':definition['controls_file'],'sha256':control_sha}]
                                    stream.write(canonical_json_bytes(unit))
                            else:shutil.copyfileobj(handle,stream)
                stream.flush();os.fsync(stream.fileno())
        for row in selected:
            invocation = json.loads((output/row['directory']/'invocation.json').read_bytes())
            invocations.append(invocation)
            bindings.append({'invocation_id':invocation['invocation_id'],
                'stdout_path':str(Path(row['directory'])/'stdout.bin'),
                'stdout_sha256':digest(output/row['directory']/'stdout.bin'),
                'attempt_record_sha256':row['input_binding']['attempt_sha256']})
        write_new(parent/'invocation_manifest.json',canonical_json_bytes(invocations))
        write_new(parent/'source_dispositions.jsonl',b''.join(canonical_json_bytes(d) for d in dispositions))
        structural_path = parent/'structural_manifest.jsonl'
        campaign = {'schema':'born_public_structural_campaign_v1',
            'stdout_execution_bindings':bindings,
            'structural_manifest':{'path':str(structural_path.relative_to(output)),'sha256':digest(structural_path)},
            'invocation_manifest':{'path':str((parent/'invocation_manifest.json').relative_to(output)),
                                  'sha256':digest(parent/'invocation_manifest.json')},
            'expected_invocations':len(expected),'completed_invocations':len(selected),
            'profile':document['grids'][document['_selected_grid']]['profile']}
        write_new(parent/'campaign.json',canonical_json_bytes(campaign))
        collection['evaluations'][evaluation] = {'path':str(parent.relative_to(output)),
            'expected_invocations':len(expected),'completed_invocations':len(selected),'unit_rows':counts,
            'complete':len(selected)==len(expected),'units_file':definition['units_file']}
    write_new(destination/'collection.json',canonical_json_bytes(collection))
    return destination,collection


def run_units(*, grid, runs, output, specifications='specifications', workers=1):
    specifications = Path(specifications).resolve(strict=True)
    jobs,document = planned_jobs(specifications,grid)
    output = validate_output(output,specifications.parent)
    roots = [Path(r).resolve(strict=True) for r in runs]
    if any(output==r or output.is_relative_to(r) or r.is_relative_to(output) for r in roots):
        raise ValueError('unit outputs and capture inputs must be disjoint roots')
    if workers < 1:raise ValueError('--workers must be positive')
    available,commitments = source_inputs(roots)
    code = [{ 'path':'reproduction/'+name,'sha256':digest(Path(__file__).parent/name)}
            for name in ('units.py','unit_builders.py','specification.py','numerical_runtime.py',
                         'stage_environment.py')]
    code += [{'path':'snapshot/'+p.name,'sha256':digest(p)}
             for p in sorted((Path(__file__).parent.parent/'snapshot').glob('*.py'))]
    plan = {'schema':'born_unit_plan_v1','grid':grid,'jobs':jobs,
            'specifications':specification_files(specifications),'code':code,
            'input_plans':commitments,
            'numerical_runtime':numerical_runtime(document['policy']['threads_per_process'])}
    with exclusive_output(output):
        plan_path = output/'unit_plan.json'
        if plan_path.exists():
            previous_plan=json.loads(plan_path.read_bytes())
            if previous_plan.get('numerical_runtime')!=plan['numerical_runtime']:
                raise ValueError('unit output root has a different or unbound numerical runtime; use a new output root')
            if numeric_plan(previous_plan)!=numeric_plan(plan):
                raise ValueError('unit output root has a different grid, code, specifications or input plans')
        else:write_new(plan_path,canonical_json_bytes(plan))
        manifest = Manifest(output)
        completed = manifest.completed()
        # Changed stdout/attempt bindings invalidate resume even if the P2a
        # run plan is unchanged; partial captures may acquire a later attempt.
        pending = []
        for job in jobs:
            key=(job['experiment'],job['config_or_null'],job['seed'],job['scale'])
            entry=available.get(key)
            binding=None if entry is None else {k:entry[k] for k in
                ('stdout_sha256','attempt_sha256','execution_status')}
            if job['invocation_id'] in completed:
                if completed[job['invocation_id']]['input_binding']!=binding:
                    raise ValueError('completed unit input binding changed')
            elif entry is not None:
                pending.append((job,entry,binding))
        input_available = len(pending)+len(completed)
        # A complete closed collection is a stable downstream input. Publishing
        # a new path on every no-op resume would invalidate the census's input
        # identity despite identical science.
        publications=[r for r in manifest.rows if r['event']=='collection']
        if not pending and len(completed)==len(jobs) and publications:
            publication=publications[-1];saved=publication['summary']
            from .evaluation import closed_inputs
            for evaluation in saved['evaluations']:
                closed_inputs(output,evaluation,specifications)
            if publication.get('artifacts'):
                for artifact in publication['artifacts']:
                    if digest(relative_file(output,artifact['path']))!=artifact['sha256']:
                        raise ValueError('completed collection artifact changed')
            return {**saved,'launched':0,'skipped_completed':len(completed),
                    'wall_seconds':0.,'cpu_seconds':0.,'output_bytes':0,'resumed':True}
        known={(r['invocation_id'],r['attempt']) for r in manifest.rows}
        for job in jobs:
            for directory in sorted((output/'invocations'/job['invocation_id']).glob('attempt_*')):
                suffix = directory.name.removeprefix('attempt_')
                if directory.is_dir() and suffix.isdigit() and (job['invocation_id'],int(suffix)) not in known:
                    manifest.append({'event':'abandoned','status':'unrecorded_attempt_directory',
                        'invocation_id':job['invocation_id'],'attempt':int(suffix),
                        'directory':str(directory.relative_to(output))})
        closed={(r['invocation_id'],r['attempt']) for r in manifest.rows if r['event']!='started'}
        for row in list(manifest.rows):
            if row['event']=='started' and (row['invocation_id'],row['attempt']) not in closed:
                manifest.append({**row,'event':'abandoned','status':'interrupted_coordinator'})
        began=time.monotonic();results=[]
        for variable in THREAD_VARIABLES:os.environ[variable]=str(document['policy']['threads_per_process'])
        def prepare(item):
            job,entry,binding=item
            attempt=manifest.next_attempt(job['invocation_id'])
            relative=Path('invocations')/job['invocation_id']/f'attempt_{attempt:04d}'
            directory=output/relative;directory.mkdir(parents=True,exist_ok=False)
            base={'invocation_id':job['invocation_id'],'attempt':attempt,'directory':str(relative),
                  'input_binding':binding,'evaluation':job['evaluation']}
            manifest.append({**base,'event':'started'})
            task={'job':job,'input':entry,'directory':str(directory),'specifications':str(specifications),
                  'threads':document['policy']['threads_per_process'],
                  'numerical_runtime':plan['numerical_runtime'],
                  'evaluation_definition':document['evaluations'][job['evaluation']]}
            return base,task
        for base,result in invocation_results(pending,workers=workers,prepare=prepare,
                construct=construct_one,executor_factory=ProcessPoolExecutor):
            items=artifacts(output/base['directory'],output)
            row={**base,**result,'event':'finished','artifacts':items,
                 'output_bytes':sum(a['bytes'] for a in items)}
            manifest.append(row);results.append(row)
            if row['status']=='completed':completed[row['invocation_id']]=row
            print(json.dumps({'invocation':row['invocation_id'],'status':row['status'],
                              'unit_rows':row['unit_rows']},sort_keys=True),flush=True)
        document['_selected_grid']=grid
        sequence=max([int(p.name.removeprefix('collection_'))
            for p in (output/'collections').glob('collection_*') if p.is_dir()],default=0)+1
        destination,collection=assemble(output,jobs,completed,available,document,sequence)
        wall=time.monotonic()-began
        summary={'schema':'born_unit_summary_v1','grid':grid,'planned':len(jobs),
            'input_available':input_available,'launched':len(results),
            'skipped_completed':len(completed)-sum(r['status']=='completed' for r in results),
            'completed':len(completed),'failed':sum(r['status']!='completed' for r in results),
            'incomplete':len(jobs)-len(completed),'wall_seconds':wall,
            'cpu_seconds':sum(r.get('cpu_seconds',0) for r in results),
            'output_bytes':sum(r['output_bytes'] for r in results),
            'worker_peak_rss_kib':max([r.get('worker_peak_rss_kib',0) for r in results],default=0),
            'collection_bytes':sum(p.stat().st_size for p in destination.rglob('*') if p.is_file()),
            'collection':str(destination.relative_to(output)),'evaluations':collection['evaluations']}
        manifest.append({'event':'collection','invocation_id':'collection','attempt':sequence,
                         'status':'published','summary':summary,'artifacts':artifacts(destination,output)})
        return summary
