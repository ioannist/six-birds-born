"""Adapters from sealed P2a captures; predictions precede the shared P2b scorer."""
import copy
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from born_ladder.reproduction.evaluation import PopulationSpecification
from born_ladder.reproduction.specification import PublicSpecification
from born_ladder.reproduction.units import source_inputs,relative_file
from born_ladder.reproduction.runs import RunSpecifications,Manifest,exclusive_output
from .specification import Specification,canonical_bytes,digest
from .pipeline import begin,write_new,before_publication,descriptive,artifact_bindings,verify_artifacts
from .predictions import predict,commit,read_committed


class FreshNamespace:
    """Keep the public inherited schema, bind every nested RNG source to v25."""
    def namespace(self,spec):
        self.attestation=SimpleNamespace(json_sha256=spec.digest)
        self.scientific_rng_identity=spec.digest
        self.rng_master_prefix=spec.science['rng']['master_prefix']
    def get(self,pointer,expected_type=None):
        if pointer=='/rng/framing/master_prefix':return self.rng_master_prefix
        value=super().get(pointer,expected_type)
        if pointer=='/rng':
            value=copy.deepcopy(value); value['framing']['master_prefix']=self.rng_master_prefix
        if pointer=='/completeness/g2c_v24_sealed_input_route':
            value=copy.deepcopy(value)
            value['source_identity']['companion_sha256']=self.scientific_rng_identity
        return value


class FreshAcquisitionSpecification(FreshNamespace,PublicSpecification):
    def __init__(self,spec):
        super().__init__(spec.directory,'v21')
        self.namespace(spec)


class FreshSpecification(FreshNamespace,PopulationSpecification):
    """Inherit formulas/controls and masks, replace only the RNG namespace.

    Historical campaign metadata is not used as v25 acquisition membership;
    that is checked directly against Specification.grid and the P2a journal.
    """
    def __init__(self,spec,evaluation):
        super().__init__(spec.directory,evaluation)
        self.namespace(spec)
        if evaluation=='cross-term':
            self._g2c_source_spec=FreshAcquisitionSpecification(spec)


def adapt_record(spec,row,prediction,*,evaluation):
    """Keep all original non-diagonal values/controls; add the certified law."""
    import numpy as np
    row=copy.deepcopy(row)
    from born_ladder.snapshot.g2c_evaluate import _record_kind
    from born_ladder.snapshot.g2a import _controls_pass
    kind='raw' if _record_kind(row)=='raw' else 'package'
    row['_derived_kind']='raw' if kind=='raw' else 'pkg'
    certificate=prediction['canonical_certificate']
    row['kind']=kind
    control_flags=row.get('pass_boolean_for_each_residual',{})
    version='v8' if evaluation=='competitor' else 'v24'
    from born_ladder.reproduction.specification import PublicSpecification
    profiles=PublicSpecification(spec.directory,version).get('/completeness/universal_evidence_shapes/stage_profiles')
    profile=profiles['g2a'] if version=='v8' else profiles['g2c']
    inherited_pass=_controls_pass([row],profile)
    controls_pass=inherited_pass and prediction['canonical_controls']['status']=='pass'
    row['controls']={'I':'pass','A':'pass','F':'pass' if inherited_pass else 'fail',
                     'C':'pass' if prediction['canonical_controls']['status']=='pass' else 'missing'}
    if certificate['status']=='certified' and row['eligibility']:
        q=certificate['q_diag_canonical']; labels=prediction['restricted']['labels'][kind]
        outcomes=row['ordered_union_outcome_labels']; map_matrix=row['M_raw_or_content_hash' if kind=='raw' else 'M_pkg_or_content_hash']
        mapped=(np.asarray(map_matrix)@np.asarray(q)).tolist()
        empirical=row['unrounded_y_raw' if kind=='raw' else 'unrounded_y_pkg']
        row['dtv_loss']['q_diag_canonical']=0.5*__import__('math').fsum(abs(a-b) for a,b in zip(mapped,empirical,strict=True))
        row['brier_score']['q_diag_canonical']=__import__('math').fsum((a-b)**2 for a,b in zip(mapped,empirical,strict=True))
        row['pairwise_contrast']['D__q_diag_canonical_minus_q_full']=row['dtv_loss']['q_diag_canonical']-row['dtv_loss']['q_full'] if controls_pass else None
        row['tie_flag']['D__q_diag_canonical_minus_q_full']=abs(row['dtv_loss']['q_diag_canonical']-row['dtv_loss']['q_full'])<=float(spec.science['evaluations']['admission']['tie_threshold'])
        row['state_space_prediction']['q_diag_canonical']=q
    else:
        if isinstance(row.get('pairwise_contrast'),dict):
            row['pairwise_contrast']['D__q_diag_canonical_minus_q_full']=None
    for field in ('dtv_loss','brier_score','state_space_prediction','normalization_mass','law_numerators','predicted_label_distribution'):
        if isinstance(row.get(field),dict): row[field].pop('q_diag',None)
    if isinstance(row.get('pairwise_contrast'),dict):row['pairwise_contrast'].pop('D__q_diag_minus_q_full',None)
    if isinstance(row.get('tie_flag'),dict):row['tie_flag'].pop('D__q_diag_minus_q_full',None)
    row['prediction_commitment_sha256']=digest(prediction)
    row['v25_scientific_digest']=spec.digest
    return row



def structural_invocation(source, job, entry):
    """Separate the stable capture-directory key from the collector identity.

    P2a journals use job.id as their human-readable storage key. Scientific
    structural records use the inherited canonical invocation_id_for helper,
    shared with P2b and the cross-term collector. Keep the former unchanged
    so completed acquisition and unit journals remain resumable.
    """
    from born_ladder.snapshot.completeness import invocation_id_for
    invocation = dict(entry['invocation'])
    expected = {'experiment':job.experiment, 'config_or_null':job.configuration,
                'seed':job.seed, 'scale':job.scale}
    if any(invocation.get(k) != value or type(invocation.get(k)) is not type(value)
           for k, value in expected.items()):
        raise ValueError('capture invocation metadata differs from registered job')
    identity = invocation_id_for(getattr(source, '_g2c_source_spec', source), **expected)
    if 'invocation_id' in invocation and invocation['invocation_id'] != identity:
        raise ValueError('capture structural invocation identity differs')
    invocation['invocation_id'] = identity
    invocation.setdefault('required_emission_families',
        ['KEY_BORN_PROBE_JSON','KEY_DISCOVERY_GRADE_JSON','KEY_AUDIT_JSON'])
    return invocation


def construct_fresh_one(task):
    """One invocation; exactly the same constructor in serial and spawn workers."""
    import os
    import resource
    import time
    from .pipeline import worker_identity
    from born_ladder.snapshot.runner_structural import parse_runner_stdout
    from born_ladder.snapshot.g2a import _raw_segments
    from born_ladder.snapshot.g2c_collector_structural import parse_g2c_raw_segments
    from born_ladder.reproduction.unit_builders import build_invocation
    spec=Specification(task['specifications']);evaluation=task['evaluation']
    source=FreshSpecification(spec,evaluation);job=task['job'];entry=task['input']
    directory=Path(task['directory']);plan={'runtime':task['runtime']}
    started=time.monotonic();cpu=time.process_time()
    try:
        # After scientific imports, in the actual process that computes numbers.
        runtime=worker_identity(spec)
        if runtime!=plan['runtime']:raise ValueError('v25 worker computing runtime differs')
        write_new(directory/'worker_receipt.json',{'pid':os.getpid(),'runtime':runtime,
                  'checked_in_actual_computing_process':True})
        if entry['execution_status']!='completed': raise ValueError('capture execution '+entry['execution_status'])
        stdout_path=relative_file(entry['root'],entry['stdout_path']); stdout=stdout_path.read_bytes()
        if hashlib.sha256(stdout).hexdigest()!=entry['stdout_sha256']: raise ValueError('capture stdout changed')
        invocation=structural_invocation(source,job,entry)
        parsed=parse_runner_stdout(source,stdout)
        if parsed.manifest['invocation_id'] != invocation['invocation_id']:
            raise ValueError('runner and collector invocation identities differ')
        structural={(unit['config_id'],unit['step_id'],unit['resolution']):unit for unit in parsed.manifest['units']}
        if evaluation=='competitor': born=_raw_segments(source,stdout)[0]
        else: born=[row for segment in parse_g2c_raw_segments(source,stdout,invocation) for row in segment.born]
        predictions={}
        for row in born:
            unit=structural[(row['cell'],str(row['step_index']),row['k'])]
            identity=[job.experiment,row['cell'],job.seed,unit['runner_context_id'],row['k'],row['step_index']]
            payload={'identity':identity,'emitted':row['sym_eigvec_basis'],'preparation':row['p_theory'],
                     'labels':{'raw':row['partition'],'package':row['packaging']}}
            target=directory/'predictions'/digest(identity)
            prediction=predict(spec,evaluation,payload,runtime_sha256=digest(plan['runtime'])); commit(target,prediction)
            predictions[(unit['runner_context_id'],row['k'],row['step_index'])]=read_committed(target)[0]
        # The historical scorer/controls cannot access sample rows until
        # every prediction in this invocation has an immutable seal.
        built=build_invocation(source,evaluation,stdout,invocation,entry['attempt_sha256'])
        for name,raw in built.files.items():
            target=directory/'legacy'/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(raw)
        if built.disposition['status'] not in ('completed','complete'):
            raise ValueError('inherited unit/control disposition '+built.disposition['status'])
        old=[json.loads(raw) for raw in built.files['units.jsonl'].splitlines()]
        adapted=[]
        for row in old:
            prediction=predictions[(row['context'],row['resolution'],row['step'])]
            adapted.append(adapt_record(spec,row,prediction,evaluation=evaluation))
        cc=[json.loads(raw) for raw in built.files.get('controls.jsonl',b'').splitlines()]
        write_new(directory/'v25_units.json',adapted); write_new(directory/'v25_controls.json',cc)
        result={'status':'completed','unit_rows':len(adapted)}
    except (ValueError,KeyError,ArithmeticError,RuntimeError) as error:
        result={'status':'failed','unit_rows':0,'reason':str(error)}
    return {**result,'wall_seconds':time.monotonic()-started,
            'cpu_seconds':time.process_time()-cpu,
            'worker_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'worker_pid':os.getpid()}


def construct_fresh(*,runs,output,evaluation,specifications='specifications',workers=1):
    from born_ladder.reproduction.worker_pool import invocation_results, recover_manifest_tail
    from born_ladder.reproduction.units import artifacts
    from born_ladder.reproduction.runs import THREAD_VARIABLES
    import os
    import time
    if workers<1:raise ValueError('--workers must be positive')
    spec=Specification(specifications)
    entries,bindings=source_inputs(runs)
    # Explicit archival capture indexes cannot authorize a prospective run.
    for root in runs:
        root=Path(root)
        plan=json.loads((root/'runset.json').read_bytes())
        if plan.get('v25_scientific_digest')!=spec.digest:
            raise ValueError('capture is not from this v25 scientific specification')
    jobs=RunSpecifications(spec.directory).grid('v25-'+evaluation)
    expected={(j.experiment,j.configuration,j.seed,j.scale) for j in jobs}
    if set(entries)!=expected:raise ValueError('fresh capture invocation cohort incomplete or altered')
    output,plan=begin(spec,output,{'evaluation':evaluation,'captures':bindings})
    with exclusive_output(output):
        recovered=recover_manifest_tail(output)
        manifest=Manifest(output);completed=manifest.completed()
        if recovered:
            manifest.append({'event':'abandoned','status':'incomplete_manifest_tail',
                             'invocation_id':'journal_recovery','attempt':0,'directory':recovered})
        known={(r['invocation_id'],r['attempt']) for r in manifest.rows}
        for job in jobs:
            for directory in sorted((output/'invocations'/job.id).glob('attempt_*')):
                suffix=directory.name.removeprefix('attempt_')
                if directory.is_dir() and suffix.isdigit() and (job.id,int(suffix)) not in known:
                    manifest.append({'event':'abandoned','status':'unrecorded_attempt_directory',
                                     'invocation_id':job.id,'attempt':int(suffix),
                                     'directory':directory.relative_to(output).as_posix()})
        closed={(r['invocation_id'],r['attempt']) for r in manifest.rows if r['event']!='started'}
        for row in list(manifest.rows):
            if row['event']=='started' and (row['invocation_id'],row['attempt']) not in closed:
                manifest.append({**row,'event':'abandoned','status':'interrupted_coordinator'})
        pending=[job for job in jobs if job.id not in completed]
        skipped=len(completed);started=time.monotonic();results=[]
        # The stage router sets dispatch before imports. Children inherit the
        # one-thread policy and must also pass the post-import worker check.
        for name in THREAD_VARIABLES:os.environ[name]='1'
        def prepare(job):
            entry=entries[(job.experiment,job.configuration,job.seed,job.scale)]
            attempt=manifest.next_attempt(job.id)
            directory=output/'invocations'/job.id/('attempt_'+str(attempt).zfill(4))
            directory.mkdir(parents=True,exist_ok=False)
            base={'invocation_id':job.id,'attempt':attempt,'directory':directory.relative_to(output).as_posix()}
            manifest.append({**base,'event':'started'})
            return base,{'job':job,'input':entry,'directory':str(directory),'evaluation':evaluation,
                         'specifications':str(spec.directory),'runtime':plan['runtime']}
        for base,result in invocation_results(pending,workers=workers,prepare=prepare,
                                              construct=construct_fresh_one,
                                              executor_factory=ProcessPoolExecutor):
            items=artifacts(output/base['directory'],output) if result['status']=='completed' else []
            disposition={**base,'event':'finished','status':result['status'],'artifacts':items}
            if result['status']!='completed':disposition['reason']=result.get('reason',result.get('error'))
            # Operational timings/PIDs are separate from sealed scientific rows.
            write_new(output/base['directory']/'cost.json',result)
            manifest.append(disposition);results.append(result)
            if disposition['status']=='completed':completed[base['invocation_id']]=disposition
            print(json.dumps({'invocation':base['invocation_id'],'status':result['status'],
                              'unit_rows':result.get('unit_rows',0)},sort_keys=True),flush=True)
        # Collection order is the registered grid order, never completion order.
        rows=[];controls=[];dispositions=[]
        latest={r['invocation_id']:r for r in manifest.rows if r['event']=='finished'}
        for job in jobs:
            disposition=completed.get(job.id)
            if disposition is not None:
                directory=output/disposition['directory']
                rows.extend(json.loads((directory/'v25_units.json').read_bytes()))
                controls.extend(json.loads((directory/'v25_controls.json').read_bytes()))
            else:
                disposition=latest.get(job.id,{'event':'pending','status':'interrupted',
                                             'invocation_id':job.id})
            dispositions.append(disposition)
        collection={'schema':'born_v25_closed_units_v1','scientific_digest':spec.digest,'evaluation':evaluation,
                    'mode':'fresh','units':rows,'controls':controls,'dispositions':dispositions,
                    'complete':all(row['status']=='completed' for row in dispositions),
                    'manifest_sha256':hashlib.sha256(manifest.path.read_bytes()).hexdigest()}
        before_publication(spec,plan)
        write_new(output/('collection_'+str(len(list(output.glob('collection_*.json')))+1).zfill(4)+'.json'),collection)
        return {'status':'complete' if collection['complete'] else 'incomplete','invocations':len(jobs),'units':len(rows),
                'incomplete':sum(row['status']!='completed' for row in dispositions),
                'launched':len(results),'skipped_completed':skipped,'wall_seconds':time.monotonic()-started,
                'cpu_seconds':sum(r.get('cpu_seconds',0) for r in results),
                'worker_peak_rss_kib':max((r.get('worker_peak_rss_kib',0) for r in results),default=0)}


def infer_fresh(*,units,output,evaluation,specifications='specifications'):
    from .inference import competitor,cross_term
    spec=Specification(specifications)
    collection=json.loads(Path(units).read_bytes())
    if collection['schema']!='born_v25_closed_units_v1' or not collection['complete'] or collection['scientific_digest']!=spec.digest or collection['evaluation']!=evaluation:
        raise ValueError('complete fresh v25 collection required')
    verify_collection(units,collection)
    expected=[job.id for job in RunSpecifications(spec.directory).grid('v25-'+evaluation)]
    if [row['invocation_id'] for row in collection['dispositions']]!=expected or any(row['status']!='completed' for row in collection['dispositions']):
        raise ValueError('fresh cohort/disposition order differs')
    keys=[row['kind_cell_id'] for row in collection['units']]
    if len(set(keys))!=len(keys): raise ValueError('duplicate fresh unit identities')
    output,plan=begin(spec,output,{'units_sha256':hashlib.sha256(Path(units).read_bytes()).hexdigest()})
    with exclusive_output(output):
        if (output/'complete.json').exists():
            seal=json.loads((output/'complete.json').read_bytes())
            directory=output/seal['attempt']; verify_artifacts(directory,seal['artifacts'])
            result=json.loads((directory/'population.json').read_bytes())
            return result['joint']
        attempts=output/'attempts'; attempts.mkdir(exist_ok=True)
        attempt=attempts/('attempt_'+str(len(list(attempts.iterdir()))+1).zfill(4));attempt.mkdir()
        write_new(attempt/'worker_receipt.json',{'pid':__import__('os').getpid(),'runtime':plan['runtime'],
                    'checked_in_actual_computing_process':True})
        rows=collection['units']; seeds=spec.grid(evaluation)['seeds']
        if evaluation=='competitor':
            configs=[x for x in spec.science['acquisition']['configuration_labels'] if x!='empty']
            result=competitor(spec,rows,seeds=seeds,configs=configs)
        else: result=cross_term(spec,rows,collection['controls'],seeds=seeds)
        predictions={}
        root=Path(units).resolve().parent
        for disposition in collection['dispositions']:
            directory=root/disposition['directory']/'predictions'
            sealed={digest(p):p for location in directory.iterdir() for p,_ in [read_committed(location)]}
            for row in rows:
                if row['prediction_commitment_sha256'] in sealed:
                    pred=sealed[row['prediction_commitment_sha256']]
                    if pred['runtime_sha256']!=digest(plan['runtime']):raise ValueError('prediction computing runtime differs')
                    predictions[row['unit_id']]=pred
        control_by_id={r['kind_cell_id']:r for r in collection['controls']}
        descriptive_rows=[{**row,'nondegenerate':control_by_id[row['kind_cell_id']]['nondegenerate']
                           if evaluation=='cross-term' else True} for row in rows]
        configs=[x for x in spec.science['acquisition']['configuration_labels'] if x!='empty']
        description=descriptive(spec,predictions,descriptive_rows,evaluation,seeds,configs)
        before_publication(spec,plan)
        write_new(attempt/'orientation_description.json',description)
        write_new(attempt/'population.json',result); write_new(output/'complete.json',{
                    'attempt':attempt.relative_to(output).as_posix(),'artifacts':artifact_bindings(attempt)})
        return result['joint']


def verify_collection(path,collection):
    """Bind every flattened row/control to ordered hash-sealed invocations."""
    root=Path(path).resolve().parent
    manifest=Manifest(root); completed=manifest.completed()
    if hashlib.sha256(manifest.path.read_bytes()).hexdigest()!=collection['manifest_sha256']:
        raise ValueError('fresh collection journal binding differs')
    reconstructed=[]; controls=[]
    for disposition in collection['dispositions']:
        if completed.get(disposition['invocation_id'])!=disposition:
            raise ValueError('fresh collection disposition differs from seal')
        directory=root/disposition['directory']
        part=json.loads((directory/'v25_units.json').read_bytes())
        reconstructed.extend(part); controls.extend(json.loads((directory/'v25_controls.json').read_bytes()))
        predictions={digest(pred):pred for location in (directory/'predictions').iterdir()
                     for pred,_ in [read_committed(location)]}
        if any(row['prediction_commitment_sha256'] not in predictions for row in part):
            raise ValueError('fresh scored row has no prediction commitment')
    if canonical_bytes(reconstructed)!=canonical_bytes(collection['units']) or canonical_bytes(controls)!=canonical_bytes(collection['controls']):
        raise ValueError('fresh flattened scientific/control stream differs from seals')
    return True
