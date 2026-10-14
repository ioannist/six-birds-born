"""Performance joins only after a sealed structural census; no rescoring."""
from .checkpoints import numeric_plan
from pathlib import Path
import resource
import time

from born_ladder.archive import Archive, put, sha
from born_ladder.attachments import attach
from born_ladder.summaries import summarise
from born_ladder.independent import verify_summaries
from .census import read, verify_artifacts, collection_inputs
from .census_comparison import ordered_identities, validate_status_table
from .stage_environment import stage_identity
from .runs import Manifest, exclusive_output, validate_output
from .units import artifacts, specification_files


def run_attachments(*, census, units, output, specifications='specifications'):
    started,cpu=time.monotonic(),time.process_time()
    specifications=Path(specifications).resolve(strict=True)
    environment=stage_identity(specifications,'verification')
    census,units=Path(census).resolve(strict=True),Path(units).resolve(strict=True)
    output=validate_output(output,specifications.parent)
    if any(output==p or output.is_relative_to(p) or p.is_relative_to(output) for p in (census,units)):
        raise ValueError('attachment outputs must be disjoint from structural and unit inputs')
    seal=read(census/'complete.json')
    if seal['status']!='PASS':raise ValueError('structural census is not complete')
    verify_artifacts(census,seal['artifacts'])
    structural_plan=read(census/('census_amendment_plan.json' if (census/'census_amendment_plan.json').exists() else 'census_plan.json'))
    root,campaign,iv,unit_name,files,commitments,info=collection_inputs(units,structural_plan['evaluation'])
    # Optional logical names were fixed at structural construction. Bind them
    # to this collection by hashes, never reconstruct historical provenance.
    if any(commitments[k]!=structural_plan['input_commitments'][k]
           for k in ('collection','campaign','invocations','units','structural')):
        raise ValueError('attachment units differ from the structurally committed collection')
    files=dict(structural_plan['logical_to_execution_files'])
    rows=read(census/seal['summary']['inventory_directory']/'INVENTORY.json')
    ids=ordered_identities(rows,'structural inventory')
    summary_root=census/seal['summary']['summary_directory']
    completed=read(summary_root/'structural_completion_results.json')
    original=read(summary_root/'original_implementation_results.json')
    validate_status_table(completed,ids,'structural completion')
    validate_status_table(original,ids,'original implementation')
    # Resolve control links relative to each sealed unit stream. No references
    # to archive evaluations or descriptive attachments are needed.
    parent=units/info['path']
    unit_paths={ptr['path'] for row in rows for ptr in row['kind_records']}
    for name in unit_paths:
        actual=Path(files[name])
        if sha(actual)!=commitments['units']:raise ValueError('sealed unit mapping differs')
        for p in parent.iterdir():
            if p.is_file():files[str(Path(name).parent/p.name)]=str(p)
    output.mkdir(parents=True,exist_ok=True)
    with exclusive_output(output):
        plan={'schema':'born_census_attachment_plan_v1','structural_seal_sha256':sha(census/'complete.json'),
            'structural_plan_sha256':sha(census/'census_plan.json'),'input_commitments':commitments,
            'stage_environment':environment,'specifications':specification_files(specifications),
            'source_code':{str(p.relative_to(Path(__file__).resolve().parents[3])):sha(p)
                           for p in sorted(Path(__file__).resolve().parents[1].rglob('*.py'))}}
        plan_path=output/'attachment_plan.json'
        if plan_path.exists():
            if numeric_plan(read(plan_path))!=numeric_plan(plan):raise ValueError('attachment resume commitment differs')
        else:put(plan_path,plan)
        if (output/'complete.json').exists():
            closed=read(output/'complete.json');verify_artifacts(output,closed['artifacts']);return closed['summary']
        manifest=Manifest(output);attached=[]
        sequence=len(list((output/'attempts').glob('attempt_*')))+1
        directory=output/'attempts'/f'attempt_{sequence:04d}';directory.mkdir(parents=True)
        manifest.append({'event':'started','invocation_id':'attachments','directory':str(directory.relative_to(output))})
        try:
            archive=Archive({'schema':'born_structural_input_view_v1','root':str(units),'files':files})
            archive.verified_file_hashes={}
            verified_units={}
            for index,row in enumerate(rows):
                cert=read(census/completed[index]['context_directory']/'structural_completion_certificate.json')
                for ptr in row['kind_records']:
                    if ptr['path'] not in verified_units:
                        verified_units[ptr['path']]=sha(archive.path(ptr['path']))
                    if verified_units[ptr['path']]!=ptr['file_sha256']:
                        raise ValueError('unit file commitment differs')
                    attached.append({**attach(archive,row,ptr,directory/'contexts'/row['unit_id'],cert,index),
                                     'completion_status':cert['overall_status'],
                                     'original_implementation_status':original[index]['status']})
                if index%100==0:print('attached census context',index,flush=True)
            for name,digest in {**verified_units,**archive.verified_file_hashes}.items():
                if sha(archive.path(name))!=digest:raise ValueError('attachment source changed during stage')
            summaries=summarise(attached,len(rows))
            independent=verify_summaries(attached,summaries)
            put(directory/'attachments.json',attached)
            put(directory/'descriptive_summaries.json',summaries)
            put(directory/'independent_summary_check.json',independent)
            summary={'schema':'born_census_attachment_summary_v1','contexts':len(rows),
                'attachment_rows':len(attached),'summary_records':len(summaries),
                'completion_pass':sum(a['completion_status']=='PASS' for a in attached),
                'registered_robust_pass':seal['summary'].get('registered_robust_pass'),
                'registered_robust_fail':seal['summary'].get('registered_robust_fail'),
                'directory':str(directory.relative_to(output)),
                'structural_status_filter':False,'rescored':False,
                'wall_seconds':time.monotonic()-started,'cpu_seconds':time.process_time()-cpu,
                'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'output_bytes':sum(p.stat().st_size for p in directory.rglob('*') if p.is_file()),'failed':0}
            put(directory/'summary.json',summary)
            manifest.append({'event':'finished','invocation_id':'attachments','status':'completed'})
            put(output/'complete.json',{'summary':summary,'artifacts':artifacts(directory,output)})
            return summary
        except BaseException as error:
            manifest.append({'event':'finished','invocation_id':'attachments','status':'failed',
                'directory':str(directory.relative_to(output)),'error':type(error).__name__+': '+str(error)})
            raise
