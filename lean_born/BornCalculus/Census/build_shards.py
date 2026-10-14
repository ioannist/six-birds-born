"""Build the census shards sequentially and retain measured receipts.

Run from any directory. This script never changes or builds dependency sources.
Lake reuses the pinned, prebuilt dependencies. Each invocation builds one census
module; the next starts only after the previous process is terminal.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time


def descendants(pid):
    result = [pid]
    try:
        children = set()
        for task in Path(f'/proc/{pid}/task').iterdir():
            try:
                children.update((task/'children').read_text().split())
            except OSError:
                pass
    except OSError:
        children = []
    for child in children:
        result.extend(descendants(int(child)))
    return result


def rss_kib(pid):
    try:
        match = re.search(r'^VmRSS:\s+(\d+)', Path(f'/proc/{pid}/status').read_text(), re.M)
        return int(match[1]) if match else 0
    except OSError:
        return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--stop', type=int, default=266)
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    project = directory.parents[1]
    report = project.parent/'MATHY_REPORT.md'
    logs = directory/'build_logs'
    logs.mkdir(exist_ok=True)
    receipts_path = directory/'build_receipts.json'
    receipts = json.loads(receipts_path.read_text()) if receipts_path.exists() else []
    for shard in range(args.start, args.stop):
        name = f'BornCalculus.Census.Shard{shard:03d}'
        source = directory/f'Shard{shard:03d}.lean'
        blob = source.read_bytes()
        cases = int(re.search(rb'def raw \(c : Fin (\d+)\)', blob)[1])
        log = logs/f'Shard{shard:03d}.log'
        timing = logs/f'Shard{shard:03d}.time'
        start = time.monotonic()
        print(json.dumps({'event': 'started', 'module': name}), flush=True)
        observed = 0
        with log.open('w') as stream:
            child = subprocess.Popen(['/usr/bin/time', '-f', '%e %U %S %M %x',
                                      '-o', str(timing), 'lake', 'build', name],
                                     cwd=project, stdout=stream, stderr=subprocess.STDOUT)
            while child.poll() is None:
                observed = max(observed, max((rss_kib(pid) for pid in descendants(child.pid)), default=0))
                time.sleep(0.5)
        values = timing.read_text().splitlines()[-1].split()
        receipt = {'module': name, 'cases': cases, 'source_bytes': len(blob),
                   'source_sha256': hashlib.sha256(blob).hexdigest(),
                   'wall_seconds': float(values[0]), 'user_seconds': float(values[1]),
                   'system_seconds': float(values[2]), 'peak_rss_kib': int(values[3]),
                   'observed_peak_rss_kib': observed, 'exit_code': child.returncode,
                   'elapsed_with_monitor_seconds': time.monotonic()-start,
                   'status': 'PASS' if child.returncode == 0 else 'FAILED',
                   'fresh_compile': bool(re.search(r'Built '+re.escape(name)+r' \(', log.read_text()))}
        receipts.append(receipt)
        receipts_path.write_text(json.dumps(receipts, indent=2)+'\n')
        with report.open('a') as stream:
            stream.write(f"\nSequential build receipt: `{name}`, {cases} cases, "
                         f"**{receipt['status']}**, {receipt['wall_seconds']:.2f} s wall, "
                         f"{receipt['peak_rss_kib']:,} KiB peak RSS; "
                         f"source {len(blob):,} bytes; "
                         f"{'fresh compile' if receipt['fresh_compile'] else 'cache replay'}. "
                         f"Receipt/logs: `lean_born/BornCalculus/Census/build_receipts.json`, "
                         f"`build_logs/Shard{shard:03d}.log`.\n")
        print(json.dumps(receipt), flush=True)
        if child.returncode:
            raise SystemExit(child.returncode)
    print(json.dumps({'event': 'terminal', 'status': 'PASS', 'start': args.start,
                      'stop': args.stop}), flush=True)


if __name__ == '__main__':
    main()
