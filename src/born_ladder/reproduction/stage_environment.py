"""Automatic stage routing before scientific imports.

Historical predictive/census profiles retain their binary checks. Version-based
profiles check the actual numerical stack without executable/library hash gates.
"""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import venv
import fcntl


def profile_path(specifications, name):
    if name not in ('predictive', 'verification', 'predictive_v25', 'test_b_fitting'):
        raise ValueError('unknown numerical stage profile: ' + name)
    return Path(specifications).resolve()/'environments'/(name+'.json')


def validate_runtime(profile, runtime):
    """Fail closed; no input data, optimizer or constructor is used here."""
    checks = {'NumPy': (runtime['numpy_version'], profile['numpy_version']),
              'machine': (runtime['machine'], profile['machine']),
              'byte order': (runtime['byte_order'], profile['byte_order']),
              'BLAS/LAPACK libraries': (runtime['libraries'], profile['libraries']),
              'BLAS/LAPACK build': (runtime['blas_lapack_build'], profile['blas_lapack_build']),
              'thread policy': (runtime['thread_policy'], profile['thread_environment'])}
    pools = [{k:v for k,v in p.items() if k!='num_threads'} for p in runtime['effective_thread_pools']]
    checks['effective backend'] = (pools, profile['thread_pools'])
    for label,(actual,expected) in checks.items():
        if actual != expected:
            raise ValueError(f'{profile["profile"]} environment mismatch: {label}; '
                             'use the public CLI for automatic stage routing')
    if not pools or any(p['num_threads'] != profile['threads'] for p in runtime['effective_thread_pools']):
        raise ValueError('stage environment mismatch: effective thread count')
    if not runtime.get('numpy_cpu_features',{}).get('X86_V3',False):
        raise ValueError('stage environment requires the x86-64-v3 instruction set')
    # Environment text cannot disable dispatch in an already loaded NumPy.
    # Require the actual feature flags, including explicit false values.
    disabled = profile['dispatch_environment']['NPY_DISABLE_CPU_FEATURES'].split(',')
    features = runtime.get('numpy_cpu_features', {})
    if any(features.get(name) is not False for name in disabled):
        raise ValueError('stage environment mismatch: effective NumPy CPU dispatch; '
                         're-execute with the stage dispatch policy before importing NumPy')


def base_matches(profile):
    version = platform.python_version()
    expected = profile['python_version']
    return (platform.python_implementation() == profile['python_implementation']
            and (version.startswith(expected + '.') if profile['profile'] == 'predictive_v25' else version == expected))


def check_current(profile):
    if profile['profile'] == 'test_b_fitting':
        from .test_b_runtime import check_runtime
        return check_runtime(profile)
    if profile['profile'] == 'predictive_v25':
        from .v25.runtime import check_actual_worker
        return check_actual_worker(profile)
    if not base_matches(profile):
        raise ValueError('stage environment requires '+profile['python_implementation']+' '+profile['python_version'])
    from .numerical_runtime import probe_current_runtime
    runtime = probe_current_runtime()
    validate_runtime(profile, runtime)
    for distribution in ('sympy','mpmath'):
        if importlib.metadata.version(distribution) != profile[distribution+'_version']:
            raise ValueError('stage environment mismatch: '+distribution)
    if 'gmpy2_version' in profile:
        import gmpy2
        import sympy
        if (importlib.metadata.version('gmpy2')!=profile['gmpy2_version']
                or sympy.external.gmpy.GROUND_TYPES!=profile['symbolic_ground_types']):
            raise ValueError('stage environment mismatch: symbolic integer backend')
        root=Path(gmpy2.__file__).resolve().parent.parent
        for entry in profile['gmpy2_libraries']:
            if hashlib.sha256((root/entry['name']).read_bytes()).hexdigest()!=entry['sha256']:
                raise ValueError('stage environment mismatch: symbolic backend library')
    return runtime


def stage_identity(specifications, name):
    """Bind the symbolic stack as well as NumPy in a census resume plan."""
    path=profile_path(specifications,name)
    profile=json.loads(path.read_bytes())
    check_current(profile)
    lock=path.parent/profile['lock']
    if name not in ('predictive_v25', 'test_b_fitting') and hashlib.sha256(lock.read_bytes()).hexdigest()!=profile['lock_sha256']:
        raise ValueError('stage environment lock commitment differs')
    return {'profile':name,'profile_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'lock_sha256':hashlib.sha256(lock.read_bytes()).hexdigest(),
            'symbolic_packages':{key:importlib.metadata.version(key) for key in ('sympy','mpmath','gmpy2')
                                 if key+'_version' in profile},
            'symbolic_ground_types':profile.get('symbolic_ground_types'),
            'symbolic_libraries':profile.get('gmpy2_libraries',[])}


def environment_root():
    """Explicit stage root, then XDG cache root, then the home default."""
    override=os.environ.get('BORN_LADDER_ENV_ROOT')
    if override is not None:
        if not override:
            raise ValueError('BORN_LADDER_ENV_ROOT must be nonempty; unset it to use the default cache')
        return Path(override).expanduser()
    cache=os.environ.get('XDG_CACHE_HOME')
    return (Path(cache).expanduser() if cache else Path.home()/'.cache')/'born-ladder/environments'


def ensure_environment(name, specifications, argv, *, check_only=False):
    """Use a matching current runtime or provision/re-exec a managed one.

    BORN_LADDER_WHEELHOUSE is an optional os.pathsep-separated offline wheel
    directory list. With no wheelhouse pip uses its configured public index.
    The guarded child refuses a mismatch instead of routing recursively.
    check_only validates the managed child's runtime without running a command;
    a matching current runtime still returns None.
    """
    cache = environment_root()
    path = profile_path(specifications,name)
    profile = json.loads(path.read_bytes())
    lock = path.parent/profile['lock']
    if name not in ('predictive_v25', 'test_b_fitting') and hashlib.sha256(lock.read_bytes()).hexdigest()!=profile['lock_sha256']:
        raise ValueError('stage environment lock commitment differs')
    for key,value in {**profile['thread_environment'],**profile['dispatch_environment']}.items():
        os.environ[key] = value
    active = os.environ.get('BORN_LADDER_STAGE_PROFILE')
    try:
        check_current(profile)
        return None
    except (ValueError, ImportError, importlib.metadata.PackageNotFoundError) as error:
        if active:
            raise ValueError('selected stage runtime refused: '+str(error)) from error
    if not base_matches(profile):
        raise ValueError('automatic stage provisioning requires CPython '+profile['python_version']+
                         '; create the documented base Python environment first')
    identity = hashlib.sha256(path.read_bytes()+lock.read_bytes()).hexdigest()[:16]
    target = cache/(name+'-'+identity)
    python = target/'bin/python'
    ready = target/'stage_ready.json'
    expected_ready={'profile_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'lock_sha256':hashlib.sha256(lock.read_bytes()).hexdigest()}
    target.mkdir(parents=True,exist_ok=True)
    with (target/'.provision.lock').open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX)
        if ready.exists() and json.loads(ready.read_bytes())!=expected_ready:
            raise ValueError('managed environment publication differs')
        if not ready.exists():
            # A published environment is immutable. Remove only an unfinished
            # interpreter tree, preserving the lock inode held by this process.
            # Existing copied binaries prevent venv from installing symlinks.
            for name_in_tree in ('bin','Scripts','lib64','lib','Lib','include','Include','pyvenv.cfg'):
                item=target/name_in_tree
                if item.is_symlink() or item.is_file():item.unlink()
                elif item.exists():shutil.rmtree(item)
            # POSIX interpreters with $ORIGIN-relative shared libraries must
            # execute at their install location, as with python -m venv.
            venv.EnvBuilder(with_pip=True,symlinks=(os.name!='nt')).create(target)
            command = [str(python),'-m','pip','install','--only-binary=:all:',
                       '-r',str(lock),'--no-cache-dir']
            if name != 'predictive_v25': command.append('--require-hashes')
            if os.environ.get('BORN_LADDER_WHEELHOUSE'):
                command.append('--no-index')
                for directory in os.environ['BORN_LADDER_WHEELHOUSE'].split(os.pathsep):
                    command.extend(['--find-links',directory])
            try:subprocess.run(command,check=True,stdout=sys.stderr)
            except subprocess.CalledProcessError as error:
                raise ValueError('stage environment provisioning failed; inspect pip output and the documented wheelhouse option') from error
            ready.write_text(json.dumps(expected_ready,indent=2)+'\n')
    environment = {**os.environ,'BORN_LADDER_STAGE_PROFILE':name,'PYTHONNOUSERSITE':'1'}
    # Expose only our package, never the caller's site-packages/dependencies.
    # A per-launch bridge also avoids changing another running child's code
    # when concurrent callers use different checkouts or installed releases.
    environment['PYTHONSAFEPATH'] = '1'
    with tempfile.TemporaryDirectory(prefix='package-bridge-', dir=target) as directory:
        bridge = Path(directory)
        (bridge/'born_ladder').symlink_to(Path(__file__).resolve().parents[1],
                                        target_is_directory=True)
        environment['PYTHONPATH'] = str(bridge)
        print(f'Using managed {name} environment: {python}',file=sys.stderr,flush=True)
        if check_only:
            command=[str(python),'-c',
                     'import sys; from born_ladder.reproduction.stage_environment import stage_identity; '
                     'stage_identity(sys.argv[1], sys.argv[2])',str(specifications),name]
        else:
            command=[str(python),'-m','born_ladder',*argv]
        return subprocess.run(command,env=environment).returncode


def preflight_environment(name, specifications):
    """Provision/check in a fresh child without changing the caller's runtime."""
    script=('import sys; from born_ladder.reproduction.stage_environment import ensure_environment; '
            'result=ensure_environment(sys.argv[1],sys.argv[2],[],check_only=True); '
            'sys.exit(0 if result is None else result)')
    environment=dict(os.environ)
    environment.pop('BORN_LADDER_STAGE_PROFILE',None)
    command=[sys.executable,'-c',script,name,str(Path(specifications).resolve(strict=True))]
    result=subprocess.run(command,env=environment,stdout=sys.stderr)
    if result.returncode:
        raise ValueError(name+' environment preflight failed; inspect the provisioning/runtime diagnostics')
