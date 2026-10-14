"""Stage-by-stage end-to-end driver; each numerical child routes itself.

No archive comparisons, old roots or private process records enter production.
"""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from .runs import validate_output, exclusive_output
from born_ladder.archive import put, sha


def lean_pair_inputs(directory):
    """Content bindings for the actual Make build/audit, including dependencies."""
    directory=Path(directory)
    required=[directory/name for name in ('BornCalculus.lean','lakefile.toml','lake-manifest.json','lean-toolchain')]
    if any(not p.is_file() for p in required):raise ValueError('missing Lean build configuration')
    sources=sorted(p for p in (directory/'BornCalculus').rglob('*') if p.is_file())
    builds=[directory/'.lake/build']
    packages=directory/'.lake/packages'
    if packages.is_dir():builds.extend(p/'.lake/build' for p in sorted(packages.iterdir()) if p.is_dir())
    artifacts=sorted(p for build in builds for p in build.rglob('*') if p.is_file())
    if not sources or not artifacts:raise ValueError('missing Lean sources or compiled artifacts')
    # Make executes the checkout tool, not the renderer's copied tools directory.
    tool=Path.cwd()/'lean_born/tools/audit_declarations.py'
    # Resolve the executable selected by elan (including explicit overrides).
    with subprocess.Popen(['elan','which','lean'],cwd=directory,stdout=subprocess.PIPE,stderr=subprocess.PIPE) as child:
        stdout,stderr=child.communicate()
        if child.returncode:raise ValueError('cannot bind active Lean toolchain: '+stderr.decode())
    toolchain=Path(stdout.decode().strip()).resolve(strict=True)
    toolchain_root=toolchain.parent.parent
    toolchain_files=[toolchain.parent/name for name in ('lean','lake')]
    toolchain_files.extend(sorted((toolchain_root/'lib/lean').glob('*.so')))
    return {'sources_and_configuration':{p.relative_to(directory).as_posix():sha(p) for p in required+sources},
            'compiled_artifacts':{p.relative_to(directory).as_posix():sha(p) for p in artifacts},
            'audit_implementation':sha(tool),'make_configuration':sha(Path.cwd()/'Makefile'),
            'toolchain_binaries':{p.relative_to(toolchain_root).as_posix():sha(p) for p in toolchain_files}}


def lean_pair_commitment(directory):
    directory=Path(directory)
    return {'schema':'born_lean_build_audit_pair_v1','inputs':lean_pair_inputs(directory),
            'receipts':{name:sha(directory/name) for name in ('build_receipt.json','audit_receipt.json')}}


def run_lean_step(*, lean_directory, logs, render, require_full_cohort=False):
    """Execute only the renderer/build/fresh-audit part of the pipeline.

    Input applicability stays APPLICABLE for existing consumers; successful
    build_status is persisted only after both Make targets succeed. A failed
    render or resumed build cannot retain an earlier BUILT_AND_AUDITED disposition.
    """
    directory=Path(lean_directory);logs=Path(logs);logs.mkdir(parents=True,exist_ok=True)
    path=directory/'formal_coverage.json'
    retained_build=directory/'build_receipt.json';retained_audit=directory/'audit_receipt.json'
    old_build=json.loads(retained_build.read_bytes()) if retained_build.is_file() else None
    old_audit=json.loads(retained_audit.read_bytes()) if retained_audit.is_file() else None
    pair_path=directory/'build_audit_pair.json'
    pair_bytes=pair_path.read_bytes() if pair_path.is_file() else None
    def positive_measurements(receipt):
        return isinstance(receipt,dict) and all(type(receipt.get(k)) in (int,float) and math.isfinite(receipt[k]) and receipt[k]>0
                   for k in ('wall_seconds','peak_tree_rss_bytes','max_processes','max_lean_processes','sample_interval_seconds'))
    def real_build(receipt):
        return (isinstance(receipt,dict) and receipt.get('status')=='PASS'
            and type(receipt.get('modules')) is int
            and type(receipt.get('fresh_modules')) is int and 0<receipt['fresh_modules']<=receipt.get('modules',0)
            and positive_measurements(receipt))
    # Invalidate saved success before the renderer can fail, retaining input fields.
    if path.exists():
        previous=json.loads(path.read_bytes())
        previous['build_status']='PENDING_BUILD_AND_AUDIT'
        for key in ('build_receipt','audit_receipt'):
            previous.pop(key,None)
        path.write_text(json.dumps(previous,sort_keys=True,indent=2)+'\n')
    render()
    coverage=json.loads(path.read_bytes())
    if require_full_cohort and coverage.get('census_cases')==2122 and coverage['status']!='APPLICABLE':
        raise ValueError('full 2122-case cohort requires Lean certification; NOT_APPLICABLE does not satisfy the census amendment')
    if coverage['status']!='APPLICABLE':
        coverage['build_status']='NOT_APPLICABLE'
        return coverage
    coverage['build_status']='PENDING_BUILD_AND_AUDIT'
    for key in ('build_receipt','audit_receipt'):
        coverage.pop(key,None)
    path.write_text(json.dumps(coverage,sort_keys=True,indent=2)+'\n')
    try:
        verified_pair=pair_bytes is not None and json.loads(pair_bytes)==lean_pair_commitment(directory)
    except (OSError,ValueError):
        verified_pair=False
    # Invalidate before any producing build. Receipts publish only after audit.
    pair_path.unlink(missing_ok=True)
    pending={}
    for target in ('lean','lean-audit'):
        logpath=logs/f'{target}.log'
        offset=logpath.stat().st_size if logpath.exists() else 0
        with logpath.open('ab') as log:
            subprocess.run(['make',target,'LEAN_ROOT='+str(directory)],check=True,stdout=log,stderr=subprocess.STDOUT)
        # Use only this invocation's output, never a previous successful log.
        with logpath.open('rb') as log:
            log.seek(offset);fresh=log.read().decode()
        receipts=[]
        for line in fresh.splitlines():
            try:record=json.loads(line)
            except ValueError:continue
            if isinstance(record,dict) and record.get('status')=='PASS':receipts.append(record)
        if receipts:
            receipt=receipts[-1]
            if target=='lean' and receipt.get('fresh_modules')==0:
                if (verified_pair and real_build(old_build) and old_build['modules']==receipt['modules']
                        and old_audit and old_audit.get('status')=='PASS'
                        and old_audit.get('fresh') is True and old_audit.get('forbidden')=={}
                        and positive_measurements(old_audit.get('measurement',{}))
                        and json.loads(pair_bytes)==lean_pair_commitment(directory)):
                    # Lake checked that nothing needs rebuilding. Keep the
                    # producing build and its audit, including their measurements.
                    pair_path.write_bytes(pair_bytes)
                    coverage.update(build_status='BUILT_AND_AUDITED',
                                    build_receipt=retained_build.name,audit_receipt=retained_audit.name)
                    path.write_text(json.dumps(coverage,sort_keys=True,indent=2)+'\n')
                    return coverage
                raise ValueError('no producing Lean build/audit receipts; force a real local Lean rebuild')
            if target=='lean' and coverage.get('full_cohort_inputs') and not real_build(receipt):
                raise ValueError('invalid measurement from a producing Lean build')
            if target=='lean-audit' and (receipt.get('fresh') is not True or receipt.get('forbidden')!={}
                    or not positive_measurements(receipt.get('measurement',{}))):
                raise ValueError('Lean pipeline requires a fresh clean axiom audit')
            name='build_receipt' if target=='lean' else 'audit_receipt'
            pending[name]=receipt
            if target=='lean':built_inputs=lean_pair_inputs(directory)
            coverage[name]=f'{name}.json'
        elif coverage.get('full_cohort_inputs'):
            raise ValueError('full-census Lean step did not emit a '+target+' receipt')
    if pending:
        if set(pending)!={'build_receipt','audit_receipt'} or not real_build(pending['build_receipt']):
            raise ValueError('no valid producing Lean build/audit pair')
        # Hash inputs before publishing; an interrupted publication has no pair.
        inputs=lean_pair_inputs(directory)
        if inputs!=built_inputs:raise ValueError('Lean sources, artifacts or audit implementation changed during audit')
        for name,receipt in pending.items():
            destination=directory/f'{name}.json';temporary=destination.with_suffix('.json.pending')
            temporary.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
            temporary.replace(destination)
        pair={'schema':'born_lean_build_audit_pair_v1','inputs':inputs,
              'receipts':{name:sha(directory/name) for name in ('build_receipt.json','audit_receipt.json')}}
        temporary=pair_path.with_suffix('.json.pending')
        temporary.write_text(json.dumps(pair,sort_keys=True,indent=2)+'\n');temporary.replace(pair_path)

    coverage['build_status']='BUILT_AND_AUDITED'
    path.write_text(json.dumps(coverage,sort_keys=True,indent=2)+'\n')
    return coverage


def run_all(*,output,workers=1,profile='full',specifications='specifications'):
    if workers<1:raise ValueError('workers must be positive')
    specs=Path(specifications).resolve(strict=True);root=validate_output(output,Path.cwd());root.mkdir(parents=True,exist_ok=True)
    if profile not in ('full','smoke'):raise ValueError('unknown pipeline profile')
    components={'worked':'worked','census':'census','attachments':'attachments',
        'competitor_evaluation':'evaluation/competitor','cross_term_evaluation':'evaluation/cross-term',
        'test_b':'test-b','locked':'locked','lean':'lean',
        'competitor_units':'units/competitor' if profile=='full' else 'units/smoke',
        'cross_term_units':'units/cross-term' if profile=='full' else 'units/smoke'}
    plan={'schema':'born_reproduction_pipeline_v1','profile':profile,'components':components}
    old=root/'pipeline.json'
    if old.exists():
        saved=json.loads(old.read_bytes())
        if saved['profile']!=profile or any(plan['components'].get(k)!=v for k,v in saved['components'].items()):
            raise ValueError('pipeline profile changed on resume')
    if not old.exists():put(old,plan)
    elif saved!=plan:old.write_text(json.dumps(plan,indent=2,sort_keys=True)+'\n')
    start=time.monotonic();commands=[]
    def cli(*args):
        command=[sys.executable,'-m','born_ladder','reproduce',*map(str,args)]
        commands.append(command);sequence=len(commands);logs=root/'logs';logs.mkdir(exist_ok=True)
        with (logs/f'{sequence:02d}_{args[0]}.log').open('ab') as log:
            log.write(('\nCOMMAND '+json.dumps(command)+'\n').encode());log.flush()
            result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:raise RuntimeError(f'stage {args[0]} failed; see {logs/f"{sequence:02d}_{args[0]}.log"}')
    specargs=('--specifications',specs)
    with exclusive_output(root):
        if profile=='full':
            for grid,label in (('g2a','competitor'),('g2c','cross-term'),('worked-cases','worked'),('test-b','test-b')):
                cli('runs','--grid',grid,'--output',root/'runs'/label,'--workers',workers,*specargs)
            for evaluation in ('competitor','cross-term'):
                cli('units','--grid',evaluation,'--runs',root/'runs'/evaluation,'--output',root/'units'/evaluation,'--workers',workers,*specargs)
            units=root/'units/cross-term';captures=root/'runs/cross-term'
        else:
            cli('runs','--grid',json.loads((specs/'reproduction_smoke.json').read_bytes())['runner_grid'],'--output',root/'runs/smoke','--workers',workers,*specargs)
            cli('units','--grid','smoke','--runs',root/'runs/smoke','--output',root/'units/smoke','--workers',workers,*specargs)
            units=root/'units/smoke';captures=root/'runs/smoke'
        cli('census','--units',units,'--runs',captures,'--output',root/'census','--workers',min(workers,8),'--apply-amendment',*specargs)
        cli('worked-cases','--runs',root/'runs'/('worked' if profile=='full' else 'smoke'),'--output',root/'worked',*specargs)
        cli('census-attachments','--census',root/'census','--units',units,'--output',root/'attachments',*specargs)
        for evaluation in ('competitor','cross-term'):
            if profile=='full':
                cli('evaluation','--evaluation',evaluation,'--units',root/'units'/evaluation,'--output',root/'evaluation'/evaluation,'--workers',min(workers,64),*specargs)
            else:
                cli('smoke-stage','--task','population','--evaluation',evaluation,'--pipeline',root,'--output',root/'evaluation'/evaluation,'--workers',workers,*specargs)
        def render_lean():
            if profile=='full':
                cli('lean-inputs','--census',root/'census','--worked-cases',root/'worked','--output',root/'lean')
            else:
                cli('smoke-stage','--task','lean','--pipeline',root,'--output',root/'lean','--workers',workers,*specargs)
        coverage=run_lean_step(lean_directory=root/'lean',logs=root/'logs',render=render_lean,
                               require_full_cohort=profile=='full')
        if profile=='full':
            cli('test-b','--runs',root/'runs/test-b','--output',root/'test-b','--workers',workers,*specargs)
        else:
            cli('smoke-stage','--task','test-b','--pipeline',root,'--output',root/'test-b','--workers',workers,*specargs)
        cli('test-b-locked','--predictions',root/'test-b','--output',root/'locked','--workers',workers,
            *(('--smoke',) if profile=='smoke' else ()),*specargs)
        cli('bundle','--pipeline',root,'--output',root/'bundle')
        from .regenerated_bundle import GROUPS,HISTORICAL_ONLY,group_receipt
        results={}
        # Run checks in isolated computing environments. Historical-only records
        # are dispositions, never a substitute for a new scientific result.
        for group,ids in GROUPS.items():
            receipts={}
            for identifier in ids:
                command=[sys.executable,'-m','born_ladder','verify',identifier,'--profile','regenerated',
                         '--data',str(root/'bundle'),'--lean-root',str(root/'lean'),
                         '--workers',str(min(workers,64))]
                commands.append(command)
                path=root/'logs'/f'verify_{group}_{identifier}.log'
                with path.open('wb') as log:
                    result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
                if result.returncode:raise RuntimeError('regenerated verification failed: '+identifier)
                prefix='PASS '+identifier+': '
                lines=[line[len(prefix):] for line in path.read_text().splitlines() if line.startswith(prefix)]
                if len(lines)!=1:raise ValueError('missing claim-specific verification receipt: '+identifier)
                receipts[identifier]=json.loads(lines[0])
            results[group]=group_receipt(ids,receipts,reduced=profile=='smoke')
        report={'schema':'born_regenerated_verification_report_v1','status':'COMPLETE','profile':profile,
            'historical_claims_asserted':False,'checks':results,'historical_only':HISTORICAL_ONLY,
            'wall_seconds_this_invocation':time.monotonic()-start,'commands':commands,
            'formal_endpoints':{**coverage,
               'status':coverage['build_status'],
               'scope':'full public proof tree on registered rendered inputs' if coverage['status']=='APPLICABLE' else 'not applicable to this cohort'}}
        reports=root/'verification_reports';reports.mkdir(exist_ok=True)
        put(reports/f'report_{len(list(reports.glob("report_*.json")))+1:04d}.json',report)
        (root/'verification_report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report
