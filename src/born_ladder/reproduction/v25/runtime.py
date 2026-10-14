"""Computing-process version and thread checks for the corrective evaluation."""
import ctypes
import importlib.metadata as md
from pathlib import Path
import platform
import sys


def initialize():
    import numpy as np
    import scipy.linalg
    import scipy.special
    import scipy.stats
    import sympy
    np.linalg.qr(np.eye(2)); scipy.linalg.svd(np.eye(2))


def check_actual_worker(profile):
    initialize()
    if platform.python_implementation() != 'CPython' or sys.version_info[:2] != (3, 12):
        raise ValueError('v25 requires CPython 3.12')
    versions = {name: md.version(name) for name in ('numpy', 'scipy', 'sympy', 'mpmath')}
    for name, version in versions.items():
        if version != profile[name + '_version']:
            raise ValueError('v25 version mismatch: ' + name)
    pools = []
    for row in Path('/proc/self/maps').read_text().splitlines():
        fields = row.split(maxsplit=5)
        if len(fields) != 6 or 'openblas' not in fields[5] or not fields[5].startswith('/'):
            continue
        path = Path(fields[5])
        if any(p['path'] == str(path) for p in pools):
            continue
        library = ctypes.CDLL(str(path)); pool = {'path': str(path)}
        for name, typ in [('num_threads', ctypes.c_int), ('config', ctypes.c_char_p), ('corename', ctypes.c_char_p)]:
            symbols = [prefix + 'openblas_get_' + name + suffix for prefix in ('scipy_', '') for suffix in ('64_', '_64_', '')]
            function = next((getattr(library, s) for s in symbols if hasattr(library, s)), None)
            if function is None:
                raise ValueError('cannot check OpenBLAS version/threads')
            function.restype = typ; value = function()
            pool[name] = value.decode() if isinstance(value, bytes) else value
        pools.append(pool)
    if not pools or not any('OpenBLAS ' + profile['numpy_openblas_version'] + ' ' in p['config'] for p in pools):
        raise ValueError('v25 requires NumPy OpenBLAS ' + profile['numpy_openblas_version'])
    if any(p['num_threads'] != 1 or p['corename'] != 'Haswell' for p in pools):
        raise ValueError('v25 requires one thread and Haswell OpenBLAS dispatch')
    # Paths, executable builds and native object hashes are not resume gates.
    return {'python': 'CPython 3.12', **versions,
            'pools': sorted([{'config': p['config'], 'corename': p['corename'], 'num_threads': p['num_threads']}
                             for p in pools], key=lambda p: p['config'])}
