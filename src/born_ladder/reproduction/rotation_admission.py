"""Parallel scheduling of the single historical rotation reconstruction.

Certificates are computed, never accepted merely because a source says pass.
The callback binds every returned result to the exact inputs it checked.
"""
from concurrent.futures import ProcessPoolExecutor
import ctypes
import hashlib
import multiprocessing
import os
import signal
from born_ladder.archive import canonical
from born_ladder.snapshot.g2c_controls import (
    validate_g2c_v22_rotation_evidence, gradual_underflow_certificate,
)
from .stage_environment import stage_identity

_SPEC=None


def fingerprint(identity,source,control,detail):
    return hashlib.sha256(canonical([identity,source,control,detail])).hexdigest()


def initialize(specifications):
    global _SPEC
    from .evaluation import PopulationSpecification
    # These scientific imports happened in the computing worker itself.
    stage_identity(specifications,'predictive')
    _SPEC=PopulationSpecification(specifications,'cross-term')


def _bind_parent_lifetime(parent_pid):
    """Linux: kill this worker if its creator dies, including SIGKILL.

    Check after arming as well: the creator may die before prctl is called,
    when the kernel would otherwise have no future parent death to signal.
    """
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(1,signal.SIGKILL,0,0,0)!=0:  # PR_SET_PDEATHSIG
        error=ctypes.get_errno()
        raise OSError(error,os.strerror(error))
    if os.getppid()!=parent_pid:
        os._exit(1)


def _initialize_pool(specifications,parent_pid):
    _bind_parent_lifetime(parent_pid)
    initialize(specifications)


def reconstruct(task):
    source,control,detail=task
    with gradual_underflow_certificate():
        result=validate_g2c_v22_rotation_evidence(_SPEC,source,control,detail)
    return (source['kind_cell_id'],fingerprint(_SPEC.scientific_rng_identity,source,control,detail),result)


class CheckedRotations:
    def __init__(self,results):
        self.results={key:(digest,value) for key,digest,value in results}
        if len(self.results)!=len(results):raise ValueError('duplicate reconstructed rotation identity')

    def __call__(self,spec,source,control,detail,*,implementation_manifest_path=None):
        if implementation_manifest_path is not None:
            raise ValueError('public scheduling does not consume historical implementation receipts')
        digest,value=self.results[source['kind_cell_id']]
        if fingerprint(spec.scientific_rng_identity,source,control,detail)!=digest:
            raise ValueError('reconstructed rotation input binding differs')
        return value


def parallel_rotations(specifications,sources,controls,rotations,workers):
    by_id={r['kind_cell_id']:r for r in controls}
    tasks=[(source,by_id[source['kind_cell_id']],rotations[source['kind_cell_id']]) for source in sources]
    # Fresh interpreters never inherit the parent's population results or GC
    # heap. Each worker still checks its loaded runtime; BLAS stays at one thread.
    with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn'),
            initializer=_initialize_pool,initargs=(str(specifications),os.getpid())) as pool:
        results=list(pool.map(reconstruct,tasks,chunksize=16))
    return CheckedRotations(results)
