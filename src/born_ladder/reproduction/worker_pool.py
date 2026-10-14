"""Bounded invocation scheduling shared by historical and corrective builders.

Only the coordinator prepares attempts and journals results. Workers own
disjoint directories; publication order is determined by the calling collector.
"""
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
import os
from pathlib import Path
import signal
import sys


def compute_invocation(construct, task):
    # The public CLI already permits arbitrarily long exact-rational strings.
    # Spawn starts a fresh interpreter and does not inherit that Python setting.
    sys.set_int_max_str_digits(0)
    return construct(task)


def recover_manifest_tail(output):
    """Preserve and discard only an unterminated final journal record.

    Call under the output lock. A complete record's bytes never change; an
    invocation whose completion was interrupted is reconstructed in a new attempt.
    Complete malformed records still fail normal Manifest validation.
    """
    root=Path(output);path=root/'manifest.jsonl'
    if not path.exists():return None
    raw=path.read_bytes()
    if not raw or raw.endswith(b'\n'):return None
    offset=raw.rfind(b'\n')+1
    recovery=root/'journal_recovery';recovery.mkdir(exist_ok=True)
    target=recovery/f'tail_{len(list(recovery.glob("tail_*.bin")))+1:04d}.bin'
    with target.open('xb') as stream:
        stream.write(raw[offset:]);stream.flush();os.fsync(stream.fileno())
    with path.open('r+b') as stream:
        stream.truncate(offset);stream.flush();os.fsync(stream.fileno())
    return target.relative_to(root).as_posix()


def invocation_results(pending, *, workers, prepare, construct,
                       executor_factory=ProcessPoolExecutor):
    """Yield completed attempts, submitting at most ``workers`` at a time.

    SIGINT/SIGTERM stops further submissions. In-flight work is drained when
    possible; a forced kill leaves unclosed attempts for the next coordinator.
    Yield before replacing a worker so the caller can durably journal its result.
    """
    if workers < 1:
        raise ValueError('--workers must be positive')
    stop = False
    def stopped(*_):
        nonlocal stop
        stop = True
    previous = {sig: signal.signal(sig, stopped) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        if workers == 1:
            for item in pending:
                if stop: break
                base, task = prepare(item)
                try:
                    result = compute_invocation(construct, task)
                except Exception as error:
                    result = {'status': 'failed', 'unit_rows': 0,
                              'error': type(error).__name__ + ': ' + str(error)}
                yield base, result
            return
        with executor_factory(max_workers=workers, mp_context=multiprocessing.get_context('spawn')) as pool:
            queue = iter(pending); futures = {}
            def submit(item):
                base, task = prepare(item)
                futures[pool.submit(compute_invocation, construct, task)] = base
            for _ in range(workers):
                if stop: break
                item = next(queue, None)
                if item is not None: submit(item)
            while futures:
                future = next(as_completed(futures)); base = futures.pop(future)
                try:
                    result = future.result()
                except Exception as error:
                    result = {'status': 'failed', 'unit_rows': 0,
                              'error': type(error).__name__ + ': ' + str(error)}
                yield base, result
                if not stop:
                    item = next(queue, None)
                    if item is not None: submit(item)
    finally:
        for sig, handler in previous.items(): signal.signal(sig, handler)
