"""Spawn-only Test B pools; propagate scientific settings, never native pools."""
from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing
import os
from pathlib import Path


def initialize(settings, initializer, initargs):
    # The environment is inherited before Python/scientific imports. Configure
    # only Python state here; never resize an existing Torch/OpenMP pool.
    from . import estimators as E, cert_v6 as C
    for name,value in settings['fit'].items():
        setattr(E,name,value)
    for name,value in settings['defaults'].items():
        getattr(E,name).__defaults__=value
    C.WORKERS=settings['workers']
    if settings['census'] is not None:
        C.configure(output=Path(settings['output']),census=Path(settings['census']))
    from born_ladder.reproduction.test_b_runtime import check_runtime
    check_runtime(settings['profile'])
    if initializer is not None:
        initializer(*initargs)


def process_pool(max_workers=None, *, initializer=None, initargs=(), **kwargs):
    """Same executor API, with a fresh checked computing runtime per worker."""
    from . import estimators as E, cert_v6 as C
    profile=json.loads(Path(os.environ.get('BORN_LADDER_TEST_B_PROFILE',
        'specifications/environments/test_b_fitting.json')).read_bytes())
    for key,value in {**profile['thread_environment'],**profile['dispatch_environment']}.items():
        os.environ[key]=value
    settings={'profile':profile,'output':str(C.ROOT) if C.ROOT is not None else None,
              'census':str(C.CENSUS) if C.CENSUS is not None else None,'workers':C.WORKERS,
              'fit':{name:getattr(E,name) for name in ('V5_STARTS','V5_WARM_ITER','V5_POLISH_ITER','CHECKPOINTS')},
              'defaults':{name:getattr(E,name).__defaults__ for name in ('fit_model','fit_family','fit_diagonal')}}
    kwargs['mp_context']=multiprocessing.get_context('spawn')
    return ProcessPoolExecutor(max_workers=max_workers,initializer=initialize,
        initargs=(settings,initializer,initargs),**kwargs)
