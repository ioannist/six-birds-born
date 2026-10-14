"""Specification-driven public runner orchestration; no scientific sampling.

The append-only manifest keeps every attempt. Per-attempt artifacts are never
replaced; resume accepts only completed attempts whose committed bytes remain
intact. Legacy exports and supplemental capture availability are separate.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time

from .specification import PublicSpecification

THREAD_VARIABLES = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                    'RAYON_NUM_THREADS', 'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


@dataclass(frozen=True)
class Invocation:
    experiment: str
    configuration: str | None
    seed: int
    scale: int

    @property
    def id(self):
        config = self.configuration if self.configuration is not None else 'all'
        return f'{self.experiment}__{config}__s{self.seed}__n{self.scale}'

    def arguments(self):
        args = ['--exp', self.experiment, '--seed', str(self.seed), '--scale', str(self.scale)]
        if self.configuration is not None:
            args += ['--config', self.configuration]
        return args


class RunSpecifications:
    def __init__(self, directory):
        self.directory = Path(directory).resolve(strict=True)
        self.document = json.loads((self.directory/'runs.json').read_text())
        if self.document['schema'] != 'born_run_grids_v1':
            raise ValueError('unsupported run grid specification')
        self.policy = self.document['runner_policy']
        self.cache = {}
        self.active = set()
        self.files = {'runs.json'}

    def scientific(self, version):
        manifest = json.loads((self.directory/'predictive.json').read_text())
        entry = manifest['versions'][version]
        index = json.loads((self.directory/entry['section_index']).read_text())
        self.files.update({'predictive.json', entry['section_index'], index['main_file']})
        self.files.update(row['file'] for row in index['sections'])
        return PublicSpecification(self.directory, version)

    def grid(self, name):
        if name in self.cache:
            return self.cache[name]
        if name in ('v25-competitor', 'v25-cross-term'):
            from .v25.specification import Specification
            specification = Specification(self.directory)
            definition = specification.grid(name.removeprefix('v25-'))
            self.files.add('predictive_v25.json')
            jobs = [Invocation(experiment, configuration, seed, definition['scale'])
                    for seed in definition['seeds'] for experiment in definition['experiments']
                    for configuration in (specification.science['acquisition']['configuration_labels']
                                          if experiment == 'EXP-112' else [None])]
            self.cache[name] = jobs
            return jobs
        if name in self.active:
            raise ValueError('cyclic run grid reference: '+name)
        self.active.add(name)
        try:
            definition = self.document['grids'][name]
            kind = definition['kind']
            if kind == 'predictive':
                spec = self.scientific(definition['version'])
                campaign = spec.get(definition['campaign_pointer'])
                configurations = spec.get('/grid/labels')
                jobs = [Invocation(exp, config, seed, scale)
                        for seed in campaign['seeds'] for scale in campaign['scales']
                        for exp in campaign['experiments']
                        for config in (configurations if exp == 'EXP-112' else [None])]
            elif kind == 'test_b':
                contract = json.loads((self.directory/definition['contract']).read_text())
                self.files.add(definition['contract'])
                jobs = list(dict.fromkeys(Invocation(j.experiment, j.configuration,
                            contract['kernel_seed'], contract['scale'])
                            for j in self.grid(definition['campaign_grid'])))
            elif kind == 'worked_cases':
                jobs = []
                for case in definition['cases']:
                    matches = [j for j in self.grid(case['grid'])
                               if j.experiment == case['experiment']
                               and j.configuration == case['configuration']
                               and ('seed' not in case or j.seed == case['seed'])]
                    if len(matches) != 1:
                        raise ValueError('worked-case selection is not unique: '+case['name'])
                    jobs.extend(matches)
            elif kind == 'subset':
                jobs = [j for grid in definition['include_grids'] for j in self.grid(grid)]
                for selection in definition['selections']:
                    source = self.grid(selection['grid'])
                    seeds = list(dict.fromkeys(j.seed for j in source))
                    seed = seeds[selection['seed_index']]
                    selected = [j for j in source if j.seed == seed
                                and j.experiment in selection['experiments']
                                and j.configuration in selection['configurations']]
                    if not selected:
                        raise ValueError('empty diagnostic run selection')
                    jobs.extend(selected)
                jobs = list(dict.fromkeys(jobs))
            else:
                raise ValueError('unsupported run grid kind: '+kind)
            if len({j.id for j in jobs}) != len(jobs):
                raise ValueError('duplicate invocation identity')
            for j in jobs:
                if not re.fullmatch(r'[A-Za-z0-9_-]+', j.experiment) or (
                        j.configuration is not None and not re.fullmatch(r'[A-Za-z0-9_-]+', j.configuration)):
                    raise ValueError('unsafe experiment/configuration name')
            self.cache[name] = jobs
            return jobs
        finally:
            self.active.discard(name)


def validate_output(path, repository):
    """An external directory or a Git-ignored directory, never public sources."""
    output = Path(path).resolve()
    repository = Path(repository).resolve()
    git_env = {**os.environ, 'LC_ALL': 'C', 'LANGUAGE': 'C'}

    def no_worktree(result):
        return (
            result.returncode == 128
            and result.stderr.startswith(
                'fatal: not a git repository (or any '
            )
        )

    # The specification directory may be an explicit external copy. Locate
    # the output's actual worktree rather than trusting its caller's anchor.
    ancestor = output
    while not ancestor.is_dir():
        ancestor = ancestor.parent
    worktree = subprocess.run(['git', '-C', str(ancestor), 'rev-parse', '--show-toplevel'],
                             capture_output=True, text=True, env=git_env)
    if worktree.returncode != 0:
        if not no_worktree(worktree):
            raise ValueError('cannot establish output Git worktree: '+worktree.stderr.strip())
        # A copied specification directory is not necessarily a worktree.
        # A real caller checkout still protects its public sources even when
        # the output's parent traversal is limited by GIT_CEILING_DIRECTORIES.
        worktree = subprocess.run(['git', '-C', str(repository), 'rev-parse', '--show-toplevel'],
                                 capture_output=True, text=True, env=git_env)
        if worktree.returncode != 0:
            if no_worktree(worktree):
                return output
            raise ValueError('cannot establish caller Git worktree: '+worktree.stderr.strip())
    repository = Path(worktree.stdout.strip()).resolve()
    if output == repository:
        raise ValueError('--output must be outside Git (external or Git-ignored)')
    if output.is_relative_to(repository):
        probe = output/'.born-output-probe'
        checked = subprocess.run(['git', '-C', str(repository), 'check-ignore', '-q', str(probe)],
                                 capture_output=True)
        if checked.returncode != 0:
            raise ValueError('--output inside the repository must be Git-ignored; use scratch/ or an external root')
    return output


class Manifest:
    def __init__(self, output):
        self.output = Path(output)
        self.path = self.output/'manifest.jsonl'
        self.lock = threading.Lock()
        self.rows = []
        if self.path.exists():
            with self.path.open('rb') as stream:
                for line in stream:
                    if not line.endswith(b'\n'):
                        raise ValueError('incomplete manifest record; preserve it and inspect before resuming')
                    self.rows.append(json.loads(line))

    def append(self, row):
        raw = encoded(row)
        with self.lock:
            with self.path.open('ab', buffering=0) as stream:
                stream.write(raw)
                os.fsync(stream.fileno())
            self.rows.append(row)

    def completed(self):
        result = {}
        for row in self.rows:
            if row['event'] == 'finished' and row['status'] == 'completed':
                result[row['invocation_id']] = row
        for row in result.values():
            for item in row['artifacts']:
                path = self.output/item['path']
                if not path.is_file() or path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
                    raise ValueError('completed invocation artifact changed: '+item['path'])
        return result

    def next_attempt(self, identifier):
        recorded = [r['attempt'] for r in self.rows if r['invocation_id'] == identifier]
        # A coordinator can die after mkdir but before the started record.
        # Preserve that directory rather than attempting to reuse its name.
        recorded += [int(p.name.removeprefix('attempt_'))
                     for p in (self.output/'invocations'/identifier).glob('attempt_*')
                     if p.is_dir() and re.fullmatch(r'attempt_[0-9]+',p.name)]
        return max(recorded, default=0)+1


@contextmanager
def exclusive_output(output):
    output.mkdir(parents=True, exist_ok=True)
    with (output/'.runs.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('another run command owns this output root') from error
        yield


def export_inventory(directory, execution_status):
    """Separate observed exports, unfinished execution and evidenced guards.

    KEY_100_MACRO with macro_n < 2 records the early return before the
    sidecar writer in run_exp_100_single. Absence alone proves no guard.
    """
    cells = {}
    guards = {}
    counts = {'born': 0, 'sequential': 0, 'discovery': 0, 'structural': 0}
    for number,line in enumerate((directory/'stdout.bin').read_text().splitlines(), 1):
        if line.startswith('KEY_100_DYN '):
            match = re.search(r'\bcell=(.*?) enabled=', line) or re.search(r'\bcell=([^ ]+)', line)
            config = match.group(1)
            cells.setdefault(config, {'configuration': config, 'header': False,
                             'final_kernel': False, 'paths': False, 'born_contexts': 0})
        if line.startswith('KEY_100_MACRO '):
            match = re.search(r'\bcell=(.*?) level=L0 macro_n=([0-9]+)\b', line)
            if match and int(match.group(2)) < 2:
                config = match.group(1)
                cells.setdefault(config, {'configuration': config, 'header': False,
                                 'final_kernel': False, 'paths': False, 'born_contexts': 0})
                guards.setdefault(config, []).append({
                    'source': 'stdout.bin', 'line': number, 'record': line,
                    'guard': 'macro_n < 2', 'macro_n': int(match.group(2))})
        for prefix,key in [('KEY_BORN_PROBE_JSON ', 'born'),
                           ('KEY_SEQUENTIAL_PROBE_JSON ', 'sequential'),
                           ('KEY_DISCOVERY_GRADE_JSON ', 'discovery'),
                           ('RB1_STRUCTURAL_END_JSON:', 'structural')]:
            if line.startswith(prefix):
                counts[key] += 1
                if key == 'born':
                    value = json.loads(line[len(prefix):])
                    config = value['config_id'] if 'config_id' in value else value.get('cell', value.get('config'))
                    if config is not None:
                        cells.setdefault(config, {'configuration': config, 'header': False,
                                         'final_kernel': False, 'paths': False, 'born_contexts': 0})['born_contexts'] += 1
    for pattern,key in [('headers/*.audit.jsonl','header'),('capture/*.kernel.json','final_kernel'),
                        ('capture/*.paths.json','paths')]:
        for file in directory.glob(pattern):
            with file.open() as stream:
                value = json.loads(stream.readline())
            config = value['config']
            cells.setdefault(config, {'configuration': config, 'header': False,
                             'final_kernel': False, 'paths': False, 'born_contexts': 0})[key] = True
    for cell in cells.values():
        cell['guard_evidence'] = guards.get(cell['configuration'], [])
        if cell['header']:
            status, reason = 'exported', 'header observed'
        elif execution_status != 'completed':
            status, reason = 'incomplete', f'header missing; invocation execution status is {execution_status}'
        elif cell['guard_evidence']:
            status, reason = 'suppressed', 'successful invocation; KEY_100_MACRO establishes the macro_n < 2 early-return guard'
        else:
            status, reason = 'unknown', 'header missing after successful invocation; no runner guard evidence establishes suppression'
        cell['legacy_export_status'] = status
        cell['export_status_reason'] = reason
        cell['suppression_note'] = reason if status == 'suppressed' else None
    return {'payload_counts': counts, 'configurations': list(cells.values())}


def resources(path):
    if path.exists():
        for line in reversed(path.read_text().splitlines()):
            try:
                return json.loads(line)
            except ValueError:
                pass
    return {'cpu_user_seconds': None, 'cpu_system_seconds': None, 'peak_rss_kib': None}


def run_one(job, output, runner, specs, capture, timeout, manifest, stop):
    attempt = manifest.next_attempt(job.id)
    relative = Path('invocations')/job.id/f'attempt_{attempt:04d}'
    directory = output/relative
    directory.mkdir(parents=True, exist_ok=False)
    argv = [os.path.relpath(runner, output), *job.arguments(),
            '--test-b-sidecar-dir', str(relative/'headers'), '--test-b-sidecar-phase', specs.policy['header_phase']]
    if capture:
        argv += ['--full-path-capture-dir', str(relative/'capture')]
    environment = {name:str(specs.policy['threads_per_process']) for name in THREAD_VARIABLES}
    env = os.environ.copy(); env.update(environment)
    base = {'invocation_id': job.id, 'attempt': attempt, 'directory': str(relative),
            'argv': argv, 'environment': environment}
    manifest.append({**base, 'event': 'started'})
    began = time.monotonic()
    format_string = '{"cpu_user_seconds":%U,"cpu_system_seconds":%S,"peak_rss_kib":%M}'
    command = ['/usr/bin/time', '-f', format_string, '-o', str(relative/'resources.txt'), '--', *argv]
    status = 'failed'; code = None
    try:
        with (directory/'stdout.bin').open('wb') as stdout, (directory/'stderr.txt').open('wb') as stderr:
            process = subprocess.Popen(command, cwd=output, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
            while process.poll() is None:
                if stop.is_set() or time.monotonic()-began >= timeout:
                    status = 'interrupted' if stop.is_set() else 'timeout'
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL); process.wait()
                    break
                time.sleep(.05)
            code = process.returncode
            if status not in ('interrupted','timeout'):
                status = 'completed' if code == 0 else 'failed'
    except OSError as error:
        (directory/'launch_error.txt').write_text(str(error)+'\n')
    artifacts = [{'path':str(p.relative_to(output)), 'bytes':p.stat().st_size, 'sha256':digest(p)}
                 for p in sorted(directory.rglob('*')) if p.is_file()]
    try:
        exports = export_inventory(directory, status)
    except (OSError,ValueError,KeyError,AttributeError) as error:
        exports = {'error':str(error)}
        if status == 'completed':status = 'invalid_capture'
    result = {**base, 'event':'finished', 'status':status, 'exit_code':code,
              'wall_seconds':time.monotonic()-began, **resources(directory/'resources.txt'),
              'output_bytes':sum(p['bytes'] for p in artifacts), 'artifacts':artifacts, 'exports':exports}
    manifest.append(result)
    print(json.dumps({'invocation':job.id,'status':status,'wall_seconds':result['wall_seconds']},sort_keys=True),flush=True)
    return result


def run_grid(*, grid, output, specifications='specifications', runner='vendor/pica/target/release/runner',
             workers=1, capture=None, only=(), plan_only=False, timeout=None):
    if grid.startswith('v25-'):
        from .v25.specification import Specification
    specs = RunSpecifications(specifications)
    jobs = specs.grid(grid)
    if workers < 1:
        raise ValueError('--workers must be positive')
    repository = specs.directory.parent
    output = validate_output(output, repository)
    runner = Path(runner).resolve(strict=True)
    if not Path('/usr/bin/time').is_file():
        raise ValueError('GNU /usr/bin/time is required for per-invocation CPU and peak-memory accounting')
    capture = specs.policy['capture_default']=='on' if capture is None else capture
    timeout = specs.policy['timeout_seconds'] if timeout is None else timeout
    if timeout <= 0:
        raise ValueError('--timeout must be positive')
    selected = [j for j in jobs if not only or j.id in only]
    if only and set(only)-{j.id for j in jobs}:
        raise ValueError('--only names an invocation outside this grid')
    # Check the public live inventory, without historical source/build receipts.
    env = {**os.environ, **{name:str(specs.policy['threads_per_process']) for name in THREAD_VARIABLES}}
    inventory = subprocess.run([str(runner),'--list-configs','EXP-112'],env=env,
                               capture_output=True,timeout=timeout)
    expected = (Specification(specifications).science['acquisition']['configuration_labels'] if grid.startswith('v25-')
                else specs.scientific(specs.document['grids']['g2a']['version']).get('/grid/labels'))
    if inventory.returncode or inventory.stderr or inventory.stdout.decode().splitlines()!=expected:
        raise ValueError('live runner EXP-112 inventory differs from the registered configurations')
    plan = {'schema':'born_run_plan_v1','grid':grid,'capture':capture,
            'runner':{'path':os.path.relpath(runner,output),'sha256':digest(runner)},
            'live_inventory_stdout_sha256':hashlib.sha256(inventory.stdout).hexdigest(),
            'specifications':[{ 'path':str(p.relative_to(specs.directory)), 'sha256':digest(p)}
                              for p in (specs.directory/name for name in sorted(specs.files))],
            'invocations':[{'id':j.id,**asdict(j)} for j in jobs]}
    if grid.startswith('v25-'): plan['v25_scientific_digest'] = Specification(specifications).digest
    if plan_only:
        return {**plan,'selected':[j.id for j in selected]}
    with exclusive_output(output):
        plan_file = output/'runset.json'
        if plan_file.exists():
            if json.loads(plan_file.read_text()) != plan:
                raise ValueError('output root is bound to a different grid, capture setting, runner or specifications')
        else:
            with plan_file.open('xb') as stream:
                stream.write(json.dumps(plan,indent=2,sort_keys=True).encode()+b'\n')
        manifest = Manifest(output)
        completed = manifest.completed()
        known = {(r['invocation_id'],r['attempt']) for r in manifest.rows}
        for job in jobs:
            for directory in sorted((output/'invocations'/job.id).glob('attempt_*')):
                if not directory.is_dir() or not re.fullmatch(r'attempt_[0-9]+',directory.name):
                    continue
                attempt = int(directory.name.removeprefix('attempt_'))
                if (job.id,attempt) not in known:
                    manifest.append({'event':'abandoned','status':'unrecorded_attempt_directory',
                        'invocation_id':job.id,'attempt':attempt,'directory':str(directory.relative_to(output)),
                        'argv':None,'exit_code':None,'wall_seconds':None,
                        'cpu_user_seconds':None,'cpu_system_seconds':None,'peak_rss_kib':None})
        # A terminated coordinator can leave a start without a finish. Preserve
        # its files and record that disposition before allocating a new attempt.
        finished = {(r['invocation_id'],r['attempt']) for r in manifest.rows if r['event'] != 'started'}
        for row in list(manifest.rows):
            if row['event']=='started' and (row['invocation_id'],row['attempt']) not in finished:
                manifest.append({**row,'event':'abandoned','status':'interrupted_coordinator',
                    'exit_code':None,'wall_seconds':None,'cpu_user_seconds':None,
                    'cpu_system_seconds':None,'peak_rss_kib':None})
        pending = [j for j in selected if j.id not in completed]
        stop = threading.Event()
        previous = {}
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGINT, signal.SIGTERM):
                previous[sig] = signal.signal(sig, lambda *_:stop.set())
        began = time.monotonic(); results = []
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {}
                # Bounded scheduling keeps an interruption from starting the
                # rest of a large registered grid.
                queue = iter(pending)
                for _ in range(workers):
                    job = next(queue,None)
                    if job is not None:
                        futures[pool.submit(run_one,job,output,runner,specs,capture,timeout,manifest,stop)] = job
                while futures:
                    future = next(as_completed(futures))
                    futures.pop(future)
                    results.append(future.result())
                    if not stop.is_set():
                        job = next(queue,None)
                        if job is not None:
                            futures[pool.submit(run_one,job,output,runner,specs,capture,timeout,manifest,stop)] = job
        finally:
            for sig,handler in previous.items():signal.signal(sig,handler)
        wall = time.monotonic()-began
        cpu = sum((r['cpu_user_seconds'] or 0)+(r['cpu_system_seconds'] or 0) for r in results)
        summary = {'schema':'born_run_summary_v1','grid':grid,'planned':len(jobs),'selected':len(selected),
                   'skipped_completed':len(selected)-len(pending),'launched':len(results),
                   'completed':sum(r['status']=='completed' for r in results),
                   'failed':sum(r['status']!='completed' for r in results),
                   'unlaunched':len(pending)-len(results),'workers':workers,'wall_seconds':wall,
                   'cpu_seconds':cpu,'mean_busy_cores':cpu/wall if wall else 0,
                   'output_bytes':sum(r['output_bytes'] for r in results),
                   'peak_rss_kib_per_invocation':max((r['peak_rss_kib'] or 0 for r in results),default=0),
                   'resource_accounting_complete':all(r['cpu_user_seconds'] is not None for r in results)}
        return summary
