"""Bound local Lean module builds to at most eight external compiler jobs.

The local import DAG is built in order, so each Lake invocation has exactly one
out-of-date local target. Prebuilt external dependencies are checked read-only
before compilation. This also supports the full-census make lean/audit path.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ALLOWED = {'propext', 'Classical.choice', 'Quot.sound'}


def descendants(pid):
    result = {pid}
    try:
        children = set()
        for task in Path(f'/proc/{pid}/task').iterdir():
            try:
                children.update((task/'children').read_text().split())
            except OSError:
                pass
    except OSError:
        children = set()
    for child in children:
        result.update(descendants(int(child)))
    return result


def rss_kib(pid):
    try:
        match = re.search(r'^VmRSS:\s+(\d+)', Path(f'/proc/{pid}/status').read_text(), re.M)
        return int(match[1]) if match else 0
    except OSError:
        return 0


def census_enabled(project):
    coverage = project/'formal_coverage.json'
    if coverage.exists():
        return bool(json.loads(coverage.read_text()).get('full_cohort_inputs'))
    return (project/'BornCalculus/Census/input_manifest.json').is_file()


def inventory(project):
    root = project/'BornCalculus/Census'
    pattern = re.compile(r'^(?:(?:noncomputable|protected)\s+)?(theorem|def|abbrev|structure|inductive)\s+([A-Za-z_][A-Za-z0-9_\'.]*)', re.M)
    rows = []
    for path in sorted(root.glob('*.lean')):
        if path.stem.startswith('Audit'):
            continue
        source = path.read_text()
        ns = re.search(r'^namespace (\S+)', source, re.M)[1]
        for match in pattern.finditer(source):
            rows.append({'name': ns+'.'+match[2], 'kind': match[1],
                         'file': str(path.relative_to(project)),
                         'line': source.count('\n', 0, match.start())+1})
    if len({r['name'] for r in rows}) != len(rows):
        raise ValueError('duplicate census audit declarations')
    return rows


def generate_audit(project):
    rows = inventory(project)
    root = project/'BornCalculus/Census'
    names = [r['name'] for r in rows]
    (root/'AuditFull.lean').write_text('import BornCalculus.Census.FullWitness\n\n'+
        ''.join(f'#check {n}\n#print axioms {n}\n' for n in names))
    (root/'audit_full_names.json').write_text(json.dumps(names, indent=2)+'\n')
    (root/'audit_full_inventory.json').write_text(json.dumps(rows, indent=2)+'\n')
    return names


def verify_axioms(output, names):
    found = {}
    for name, payload in re.findall(r"'([^']+)' (does not depend on any axioms|depends on axioms: \[[^\]]*\])", output):
        found[name] = [] if payload.startswith('does not') else [x.strip() for x in payload.split('[',1)[1][:-1].split(',') if x.strip()]
    missing = sorted(set(names)-found.keys())
    forbidden = {n: sorted(set(found[n])-ALLOWED) for n in names if n in found and set(found[n])-ALLOWED}
    if missing or forbidden or 'error:' in output:
        raise ValueError(f'census audit failed: missing={missing}, forbidden={forbidden}')
    return {'status': 'PASS', 'declarations': len(names), 'allowed_axioms': sorted(ALLOWED),
            'dependencies': {n: found[n] for n in names}}


def modules(project):
    sources = {'.'.join(p.relative_to(project).with_suffix('').parts):p
               for p in project.rglob('*.lean') if '.lake' not in p.relative_to(project).parts
               and (p == project/'BornCalculus.lean' or 'BornCalculus' in p.relative_to(project).parts)}
    imports = {name:set(re.findall(r'^import\s+(\S+)', path.read_text(), re.M)) for name,path in sources.items()}
    return sources, imports


def build(project, roots, jobs, names=None):
    sources, imports = modules(project)
    needed = set()
    def visit(name):
        if name in needed:
            return
        if name not in sources:
            raise ValueError('missing local source '+name)
        needed.add(name)
        for dep in imports[name] & sources.keys():
            visit(dep)
    for name in roots:
        visit(name)
    external = sorted(set().union(*(imports[n]-sources.keys() for n in needed)))
    env = dict(os.environ, LEAN_NUM_THREADS='2')
    core = [n for n in external if n.split('.')[0] in {'Init','Lean','Std'}]
    if core:
        prefix = Path(subprocess.check_output(['lean','--print-prefix'],cwd=project,env=env,text=True).strip())
        for name in core:
            core_path = prefix/'lib/lean'/Path(*name.split('.')).with_suffix('.olean')
            if not core_path.is_file():
                raise ValueError('missing prebuilt toolchain import '+name)
    external = [n for n in external if n not in core]
    # --no-build prevents Lake from mutating/rebuilding shared packages.
    checked = subprocess.run(['lake','--no-build','build',*external], cwd=project,
                             env=env, capture_output=True, text=True)
    if checked.returncode:
        raise RuntimeError('external dependencies are not prebuilt; refusing to rebuild them:\n'+checked.stdout+checked.stderr)
    directory = project/'BornCalculus/Census'
    logs = directory/'project_build_logs'
    logs.mkdir(parents=True, exist_ok=True)
    receipts = []
    pending = set(needed)
    complete = set()
    processes = {}
    futures = {}
    started = time.monotonic()
    peak_rss = 0
    max_active = 0
    last_snapshot = started
    def compile_one(name):
        safe = name.replace('.','_')
        log = logs/(safe+'.log')
        timing = logs/(safe+'.time')
        blob = sources[name].read_bytes()
        begin = time.monotonic()
        with log.open('w') as stream:
            child = subprocess.Popen(['/usr/bin/time','-f','%e %U %S %M %x','-o',str(timing),
                                      'lake','build',name], cwd=project, env=env,
                                     stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            processes[name] = child
            code = child.wait()
        processes.pop(name, None)
        values = timing.read_text().splitlines()[-1].split()
        output = log.read_text()
        return {'module':name,'status':'PASS' if code == 0 else 'FAILED','exit_code':code,
                'wall_seconds':float(values[0]),'user_seconds':float(values[1]),'system_seconds':float(values[2]),
                'peak_rss_kib':int(values[3]),'source_bytes':len(blob),
                'source_sha256':hashlib.sha256(blob).hexdigest(),
                'elapsed_seconds':time.monotonic()-begin,
                'fresh_compile':bool(re.search(r'Built '+re.escape(name)+r' \(',output)),
                'log':str(log.relative_to(project))}
    try:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            while pending or futures:
                ready = sorted(n for n in pending if (imports[n]&needed) <= complete)
                for name in ready[:jobs-len(futures)]:
                    pending.remove(name)
                    futures[pool.submit(compile_one,name)] = name
                    print(json.dumps({'event':'started','module':name}), flush=True)
                if not futures:
                    raise ValueError('cycle in local import DAG')
                finished,_ = wait(futures,timeout=0.5,return_when=FIRST_COMPLETED)
                pids = set()
                for child in list(processes.values()):
                    pids.update(descendants(child.pid))
                peak_rss = max(peak_rss,sum(rss_kib(pid) for pid in pids))
                max_active = max(max_active,len(processes))
                if time.monotonic()-last_snapshot >= 10:
                    (directory/'project_build_live.json').write_text(json.dumps({
                        'status':'RUNNING','roots':roots,'jobs_limit':jobs,
                        'max_active_compilers':max_active,'completed_modules':len(receipts),
                        'wall_seconds':time.monotonic()-started,
                        'peak_aggregate_rss_kib':peak_rss},indent=2)+'\n')
                    last_snapshot = time.monotonic()
                for future in finished:
                    name = futures.pop(future)
                    result = future.result()
                    receipts.append(result)
                    (directory/'project_build_modules.json').write_text(json.dumps(receipts,indent=2)+'\n')
                    print(json.dumps(result),flush=True)
                    if result['exit_code']:
                        raise RuntimeError('module build failed: '+name+'; see '+result['log'])
                    complete.add(name)
    except BaseException:
        for child in list(processes.values()):
            try:
                os.killpg(child.pid,signal.SIGTERM)
            except ProcessLookupError:
                pass
        (directory/'project_build_failed_receipt.json').write_text(json.dumps({
            'status':'FAILED','roots':roots,'jobs_limit':jobs,
            'max_active_compilers':max_active,'completed_modules':len(receipts),
            'wall_seconds':time.monotonic()-started,
            'peak_aggregate_rss_kib':peak_rss},indent=2)+'\n')
        raise
    result = {'status':'PASS','roots':roots,'module_count':len(receipts),'jobs_limit':jobs,
              'max_active_compilers':max_active,'wall_seconds':time.monotonic()-started,
              'peak_aggregate_rss_kib':peak_rss,
              'memory_measurement':'maximum sampled sum of RSS of all build child processes; shared mappings can be counted repeatedly',
              'shard_source_bytes':sum(sources[n].stat().st_size for n in needed if re.fullmatch(r'BornCalculus\.Census\.Shard\d+',n))}
    (directory/'project_build_receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    if names is not None:
        log = logs/'BornCalculus_Census_AuditFull.log'
        audited = verify_axioms(log.read_text(), names)
        (directory/'audit_full.json').write_text(json.dumps(audited,indent=2)+'\n')
        result['axiom_audit'] = {'status':'PASS','declarations':len(names)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lean-root',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--jobs',type=int,default=8)
    parser.add_argument('--audit',action='store_true')
    parser.add_argument('--census-only',action='store_true',
                        help='build/audit only the owned census roots; shared package integration is separate')
    args = parser.parse_args()
    if not 1 <= args.jobs <= 8:
        parser.error('--jobs must be between 1 and 8')
    project = args.lean_root.resolve(strict=True)
    full = census_enabled(project)
    roots = [] if args.census_only else ['BornCalculus']
    names = None
    if full:
        roots.append('BornCalculus.Census.FullWitness')
        if args.audit:
            names = generate_audit(project)
            roots.append('BornCalculus.Census.AuditFull')
    elif args.census_only:
        raise ValueError('census-only verification requires full-cohort inputs')
    result = build(project,roots,args.jobs,names)
    if args.audit and not args.census_only:
        legacy = Path(__file__).resolve().parents[2]/'tools/audit_declarations.py'
        if not legacy.exists():
            # Renderer copies the public tools directory into isolated projects.
            raise ValueError('missing public legacy declaration audit tool')
        spec = importlib.util.spec_from_file_location('legacy_lean_audit',legacy)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result['legacy_audit'] = module.audit(project)
    print(json.dumps(result,sort_keys=True),flush=True)


if __name__ == '__main__':
    main()
