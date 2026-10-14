"""Matching Test B CPU fitting versions, checked after scientific imports."""
import ctypes
from pathlib import Path
import os
import platform


def check_runtime(profile):
    import numpy as np
    import scipy
    import torch
    from born_ladder.record_tests import estimators  # loads optimizer libraries
    np.linalg.qr(np.eye(2))
    pools=[]
    for line in Path('/proc/self/maps').read_text().splitlines():
        parts=line.split(maxsplit=5)
        if len(parts)!=6 or not parts[5].startswith('/') or 'openblas' not in parts[5].lower():continue
        path=parts[5]
        if any(row['library']==Path(path).name for row in pools):continue
        library=ctypes.CDLL(path);row={'library':Path(path).name}
        for field,kind in [('num_threads',ctypes.c_int),('corename',ctypes.c_char_p)]:
            symbol=next((getattr(library,n) for n in [prefix+'openblas_get_'+field+suffix for prefix in ('scipy_','') for suffix in ('64_','_64_','')] if hasattr(library,n)),None)
            if symbol is None:raise ValueError('unrecognized Test B OpenBLAS backend')
            symbol.restype=kind;value=symbol();row[field]=value.decode() if isinstance(value,bytes) else value
        pools.append(row)
    actual = {'python': platform.python_version(), 'numpy': np.__version__,
              'scipy': scipy.__version__, 'torch': torch.__version__,
              'torch_threads': torch.get_num_threads(),
              'blas_versions': {'numpy': np.__config__.CONFIG['Build Dependencies']['blas']['version'],
                                'scipy': scipy.__config__.CONFIG['Build Dependencies']['blas']['version']}}
    for name, expected in profile['versions'].items():
        value = actual[name]
        if (value.split('+')[0] if name == 'torch' else value) != expected:
            raise ValueError(f'Test B fitting environment mismatch: {name}={value}; use automatic stage routing')
    if actual['torch']!=profile['torch_build']:
        raise ValueError('Test B Torch build mismatch; use the pinned CPU-only fitting lock')
    if torch.version.cuda is not None:
        raise ValueError('Test B requires the CPU-only Torch distribution')
    if actual['torch_threads'] != 1 or actual['blas_versions'] != profile['blas_versions']:
        raise ValueError('Test B fitting backend/thread mismatch')
    if len(pools)<2 or any(row['num_threads']!=1 or row['corename']!='Haswell' for row in pools):
        raise ValueError('Test B effective backend/thread mismatch; re-execute before imports')
    if any(os.environ.get(k) != v for k,v in profile['thread_environment'].items()):
        raise ValueError('Test B fitting thread policy mismatch; re-execute before imports')
    return actual
