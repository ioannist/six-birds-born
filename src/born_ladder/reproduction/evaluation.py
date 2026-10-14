"""Public population inference from committed unit collections.

Historical specification digests remain RNG inputs. Reference evaluations are
never read here. The scientific kernels are shared with historical verification.
"""
from .checkpoints import numeric_plan
import json
from pathlib import Path
import resource
import time

from born_ladder.archive import put, sha
from born_ladder.snapshot.g2a import evaluate_g2a_records
from born_ladder.snapshot.g2c_evaluate import evaluate_g2c_records
from born_ladder.snapshot.g2c_controls import gradual_underflow_certificate
from born_ladder.snapshot.evidence import g2c_control_input_projection, _g2c_exact_projection_equal
from born_ladder.snapshot.universal_shapes import validate_stage_records
from .census import collection_inputs, matching_file, read, verify_artifacts
from .numerical_runtime import probe_current_runtime
from .stage_environment import stage_identity
from .specification import PublicSpecification
from .runs import Manifest, exclusive_output, validate_output
from .units import artifacts, relative_file, specification_files


class PopulationSpecification(PublicSpecification):
    """Resolve public I/O names without inventing historical process receipts."""
    def __init__(self, directory, evaluation):
        entry=read(Path(directory)/'evaluations.json')[evaluation]
        self.entry=entry
        super().__init__(directory,entry['computation_version'])

    def get(self, pointer, expected_type=None):
        if pointer=='/artifact_paths/artifacts/g2a':
            return list(self.entry['artifacts'])
        if pointer=='/provenance':
            # The population body does not use this old launch-receipt schema.
            # Actual input/runtime commitments are supplied to the public plan.
            return {}
        return super().get(pointer,expected_type)


def jsonl(path):
    with Path(path).open('rb') as stream:
        return [json.loads(line) for line in stream]


def validate_control_stream(path, directories):
    """Bind the closed control stream to the ordered sealed attempt products."""
    expected=[]
    for directory in directories:expected.extend(jsonl(directory/'controls.jsonl'))
    if not _g2c_exact_projection_equal(expected,jsonl(path)):
        raise ValueError('closed control stream differs from ordered attempt products')
    return sha(path)


def closed_inputs(units, evaluation, specifications):
    root,campaign,inv_path,unit_name,files,commitments,info=collection_inputs(units,evaluation)
    if not info['complete'] or info['completed_invocations']!=info['expected_invocations']:
        raise ValueError('population inference requires a complete registered P2b collection')
    parent=root/info['path']
    dispositions=jsonl(parent/'source_dispositions.jsonl')
    if (len(dispositions)!=info['expected_invocations']
            or len({r['invocation_id'] for r in dispositions})!=len(dispositions)
            or any(r['status']!='completed' for r in dispositions)):
        raise ValueError('missing, duplicate or incomplete invocation dispositions')
    invocations=read(inv_path)
    if len({r['invocation_id'] for r in invocations})!=len(invocations) or len(invocations)!=len(dispositions):
        raise ValueError('invocation membership is incomplete or duplicated')
    if [r['invocation_id'] for r in dispositions]!=[r['invocation_id'] for r in invocations]:
        raise ValueError('ordered invocation dispositions differ from closed collection')
    finished=Manifest(root).completed()
    selected=[]
    for invocation in invocations:
        identifier=invocation['invocation_id']
        row=finished.get(evaluation+"__"+identifier)
        if row is None:raise ValueError('missing completed construction attempt: '+identifier)
        verify_artifacts(root,row['artifacts'])
        directory=root/row['directory']
        if not directory.resolve().is_relative_to(root) or not directory.is_dir():
            raise ValueError('unsafe attempt directory')
        if read(directory/'invocation.json')!=invocation:
            raise ValueError('construction invocation differs from closed collection')
        selected.append(directory)
    # The closed stream must be the ordered, unmodified products of those attempts.
    records=[]; structural={};attempts={}
    for directory in selected:
        rows=jsonl(directory/'units.jsonl')
        records.extend(rows)
        for row in rows:
            structural[row['invocation_id']]=row['structural_manifest_sha256']
            attempts[row['invocation_id']]=row['attempt_record_sha256']
    aggregate=jsonl(files[unit_name])
    if evaluation=='cross-term':
        definition=read(Path(specifications)/'units.json')['evaluations'][evaluation]
        controls=parent/definition['controls_file']
        control_sha=validate_control_stream(controls,selected)
        for row in records:
            row['applicable_control_record_links']=[{'path':definition['controls_file'],'sha256':control_sha}]
    if not _g2c_exact_projection_equal(records,aggregate) or len(records)!=info['unit_rows']:
        raise ValueError('closed unit stream differs from ordered attempt products')
    if len({r['kind_cell_id'] for r in records})!=len(records):
        raise ValueError('duplicate unit identity')
    commitments={**commitments,'construction_manifest':sha(root/'manifest.jsonl')}
    return root,parent,records,selected,structural,attempts,commitments,info


def cross_term_inputs(spec, records, directories):
    """Load sealed evidence; reconstruct only excluded rows' nulled inputs.

    Eligible rows already carry the complete input projection. Excluded rows
    deliberately null it; their source is rebuilt by the unchanged P2b source
    constructor, from sealed stdout, before downstream validation.
    """
    from born_ladder.snapshot.g2c_units import _contract, _pair_and_control_source
    from born_ladder.snapshot.g2c_collector_structural import parse_g2c_raw_segments
    from born_ladder.snapshot.runner_structural import parse_runner_stdout
    controls=[];rotations={};sources={}
    for row in records:
        if row['eligibility']:
            sources[row['kind_cell_id']]=g2c_control_input_projection(row)
    source_spec=spec._g2c_source_spec
    contract=_contract(spec)
    for directory in directories:
        controls.extend(jsonl(directory/'controls.jsonl'))
        evidence=read(directory/'rotation_evidence.json')
        if set(evidence)&set(rotations):raise ValueError('duplicate rotation evidence')
        rotations.update(evidence)
        excluded=[row for row in jsonl(directory/'units.jsonl') if not row['eligibility']]
        if not excluded:continue
        invocation=read(directory/'invocation.json')
        stdout=(directory/'stdout.bin').read_bytes()
        runner=parse_runner_stdout(source_spec,stdout)
        structural=jsonl(directory/'structural.jsonl')[0]
        units={(u['config_id'],u['step_id'],u['resolution']):u for u in structural['units']}
        segments=parse_g2c_raw_segments(source_spec,stdout,invocation)
        for segment in segments:
            for born in segment.born:
                key=(segment.label,str(born['step_index']),born['k'])
                _,pairs,_=_pair_and_control_source(source_spec,segment=segment,born=born,
                    invocation=invocation,structural_unit=units[key],
                    structural_sha256=excluded[0]['structural_manifest_sha256'],
                    runner_sha256=runner.manifest_sha256,
                    attempt_sha256=excluded[0]['attempt_record_sha256'],contract=contract)
                for row in pairs:
                    if row['kind_cell_id'] in sources:raise ValueError('duplicate control source')
                    sources[row['kind_cell_id']]=g2c_control_input_projection(row)
    ordered=[sources[row['kind_cell_id']] for row in records]
    projections={row['kind_cell_id']:row for row in ordered}
    return controls,rotations,ordered,projections


def run_evaluation(*, evaluation, units, output, specifications='specifications', workers=1):
    started,cpu=time.monotonic(),time.process_time()
    if not 1<=workers<=64:raise ValueError('inference admission workers must be between 1 and 64')
    specifications=Path(specifications).resolve(strict=True)
    # Scientific imports above have run in this very computing process.
    environment=stage_identity(specifications,'predictive')
    runtime=probe_current_runtime()
    units=Path(units).resolve(strict=True)
    output=validate_output(output,specifications.parent)
    if output==units or output.is_relative_to(units) or units.is_relative_to(output):
        raise ValueError('inference output must be disjoint from unit inputs')
    output.mkdir(parents=True,exist_ok=True)
    with exclusive_output(output):
        root,parent,records,directories,structural,attempts,commitments,info=closed_inputs(units,evaluation,specifications)
        spec=PopulationSpecification(specifications,evaluation)
        plan={'schema':'born_public_evaluation_plan_v1','evaluation':evaluation,
            'input_commitments':commitments,'stage_environment':environment,'numerical_runtime':runtime,
            'specifications':specification_files(specifications),
            'source_code':{str(p.relative_to(Path(__file__).resolve().parents[3])):sha(p)
                           for p in sorted(Path(__file__).resolve().parents[1].rglob('*.py'))},
            'scientific_rng_identity':spec.scientific_rng_identity,
            'acquisition_rng_identity':getattr(spec,'_g2c_source_spec',spec).scientific_rng_identity,
            'admission_workers':workers}
        if (output/'evaluation_plan.json').exists():
            if numeric_plan(read(output/'evaluation_plan.json'))!=numeric_plan(plan):raise ValueError('inference resume input/runtime/code commitment differs')
        else:put(output/'evaluation_plan.json',plan)
        if (output/'complete.json').exists():
            seal=read(output/'complete.json');verify_artifacts(output,seal['artifacts']);return seal['summary']
        sequence=len(list((output/'attempts').glob('attempt_*')))+1
        directory=output/'attempts'/f'attempt_{sequence:04d}';directory.mkdir(parents=True)
        manifest=Manifest(output);manifest.append({'event':'started','invocation_id':evaluation,
            'directory':str(directory.relative_to(output))})
        try:
            if evaluation=='competitor':
                validated=validate_stage_records(spec,records,stage_profile='g2a',
                    expected_structural_manifest_sha256=structural,expected_attempt_record_sha256=attempts)
                result=evaluate_g2a_records(spec,validated,provenance={'public_input_commitments':commitments},
                    completeness={'public_collection_complete':True,'invocations':info['completed_invocations']})
            else:
                controls,rotations,sources,projections=cross_term_inputs(spec,records,directories)
                rotation_validator=None
                if workers>1:
                    from .rotation_admission import parallel_rotations
                    rotation_validator=parallel_rotations(specifications,sources,controls,rotations,workers)
                # The original evaluator reconstructs and checks all sixteen
                # certified rotations at its consumer boundary before inference.
                with gradual_underflow_certificate():
                    result=evaluate_g2c_records(spec,records,controls,rotation_evidence=rotations,
                        control_sources=sources,control_input_projections=projections,rotation_validator=rotation_validator)
            put(directory/'evaluation.json',result)
            admission=[{k:row[k] for k in ('kind_cell_id','unit_id','seed','seed_block_key',
                'bootstrap_hierarchy_keys','eligibility','exclusion_reason_code','tie_flag')} for row in records]
            put(directory/'admission.json',admission)
            summary={'schema':'born_public_evaluation_summary_v1','evaluation':evaluation,
                'unit_rows':len(records),'eligible_rows':sum(r['eligibility'] for r in records),
                'seed_membership':sorted({r['seed'] for r in records}),
                'registered_verdict':result['status'],'evaluation_path':str((directory/'evaluation.json').relative_to(output)),
                'wall_seconds':time.monotonic()-started,
                'cpu_seconds':time.process_time()-cpu+resource.getrusage(resource.RUSAGE_CHILDREN).ru_utime+resource.getrusage(resource.RUSAGE_CHILDREN).ru_stime,
                'coordinator_cpu_seconds':time.process_time()-cpu,
                'worker_peak_rss_kib':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
                'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'output_bytes':sum(p.stat().st_size for p in directory.rglob('*') if p.is_file()),'failed':0}
            put(directory/'summary.json',summary)
            manifest.append({'event':'finished','invocation_id':evaluation,'status':'completed',
                'directory':str(directory.relative_to(output))})
            put(output/'complete.json',{'summary':summary,'artifacts':artifacts(directory,output)})
            return summary
        except BaseException as error:
            manifest.append({'event':'finished','invocation_id':evaluation,'status':'failed',
                'directory':str(directory.relative_to(output)),'error':type(error).__name__+': '+str(error)})
            raise
