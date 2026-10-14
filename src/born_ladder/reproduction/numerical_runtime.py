"""Numerical-runtime identity for I/O plans, not a scientific constructor."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from .runs import THREAD_VARIABLES


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def probe_current_runtime():
    """Probe an isolated interpreter after its thread environment is set.

    SVD on a fixed identity loads NumPy's LAPACK backend; no random draws or
    scientific inputs are used. Library locations are diagnostic metadata,
    not artifact references or inputs to later computations.
    """
    import numpy as np
    np.linalg.svd(np.eye(2), full_matrices=False)
    numpy_root = Path(np.__file__).resolve().parent
    roots = (numpy_root, numpy_root.parent/'numpy.libs')
    paths = set()
    maps = Path('/proc/self/maps')
    if not maps.exists():
        raise RuntimeError('numerical runtime identity requires Linux /proc/self/maps')
    for line in maps.read_text().splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) != 6 or not fields[5].startswith('/'):
            continue
        path = Path(fields[5])
        if any(path.is_relative_to(root) for root in roots) and '.so' in path.name:
            paths.add(path)
    libraries, pools = [], []
    for path in sorted(paths):
        libraries.append({'name':path.name, 'sha256':file_sha(path)})
        if 'openblas' not in path.name.lower():
            continue
        library = ctypes.CDLL(str(path))
        pool = {'library':path.name}
        for name, result_type in [('num_threads',ctypes.c_int), ('config',ctypes.c_char_p),
                                  ('corename',ctypes.c_char_p)]:
            candidates = [prefix+'openblas_get_'+name+suffix
                for prefix in ('scipy_', '') for suffix in ('64_', '_64_', '')]
            symbol = next((getattr(library,s) for s in candidates if hasattr(library,s)),None)
            if symbol is None:
                raise RuntimeError('cannot identify OpenBLAS '+name)
            symbol.restype = result_type
            value = symbol()
            pool[name] = value.decode() if isinstance(value,bytes) else value
        pools.append(pool)
    if not libraries or not pools:
        raise RuntimeError('cannot identify the loaded NumPy BLAS/LAPACK runtime')
    from numpy._core import _multiarray_umath
    dependencies = np.__config__.CONFIG['Build Dependencies']
    return {'schema':'born_numerical_runtime_v1',
        'interpreter':{'implementation':platform.python_implementation(),
            'version':sys.version, 'executable_name':Path(sys.executable).resolve().name,
            'executable_sha256':file_sha(Path(sys.executable).resolve()),
            'cache_tag':sys.implementation.cache_tag},
        'numpy_version':np.__version__,
        'machine':platform.machine(), 'byte_order':sys.byteorder,
        'numpy_cpu_features':_multiarray_umath.__cpu_features__,
        'blas_lapack_build':{kind:{key:value for key,value in dependencies[kind].items()
            if key in ('name','version','openblas configuration')} for kind in ('blas','lapack')},
        'libraries':libraries, 'effective_thread_pools':pools,
        'thread_policy':{key:os.environ.get(key) for key in THREAD_VARIABLES}}


def numerical_runtime(threads):
    """Never infer effective threads from an already imported parent NumPy."""
    environment = {**os.environ, **{key:str(threads) for key in THREAD_VARIABLES}}
    completed = subprocess.run([sys.executable, '-m', __name__], env=environment,
        capture_output=True, text=True, check=True)
    result = json.loads(completed.stdout)
    if any(pool['num_threads'] != threads for pool in result['effective_thread_pools']):
        raise ValueError('effective BLAS thread count differs from unit thread policy')
    return result


if __name__ == '__main__':
    print(json.dumps(probe_current_runtime(), sort_keys=True))
