#!/usr/bin/env python3
"""Recursive public-source inventory, bounded builds and fresh kernel axiom audit.

Census modules plug in via ordinary named declarations and root imports. Optional
recursive audit_manifest.json files cover anonymous/generated source declarations;
entries use name, kind, file (relative to the Lean root), and line. Private and
compiler-generated auxiliary declarations are traversed as dependencies, but are
not counted as public source commands. inventory remains usable before a build.
"""
from pathlib import Path
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ALLOWED = {'propext', 'Classical.choice', 'Quot.sound'}
KINDS = {'theorem', 'def', 'abbrev', 'structure', 'inductive', 'instance', 'class', 'opaque', 'axiom'}
COMMAND = re.compile(r'^[ \t]*(?:@\[[^\n]*?\]\s*)?(?P<mods>(?:(?:private|protected|noncomputable|unsafe|partial|public|local|scoped)\s+)*)'
                     r'(?P<cmd>namespace|section|end|mutual|theorem|def|abbrev|structure|inductive|instance|class|opaque|axiom|constant|constants|initialize|builtin_initialize|deriving|macro|macro_rules|elab|elab_rules|syntax)\b', re.M)
IDENT = re.compile(r'(?:«[^»]+»|[^\W\d][\w\'!?]*)(?:\.(?:«[^»]+»|[^\W\d][\w\'!?]*))*', re.UNICODE)
# Only the shared implementation harness is outside the mathematical inventory.
# Packet/shard files called Audit are scanned too: a filename cannot hide a proof.
AUDIT_ONLY = {'BornCalculus/Audit.lean'}


def masked_source(text):
    """Remove nested comments and literals, preserving every offset/newline."""
    out = list(text)
    i = 0
    while i < len(text):
        start = i
        if text.startswith('--', i):
            end = text.find('\n', i)
            i = len(text) if end < 0 else end
        elif text.startswith('/-', i):
            depth = 1
            i += 2
            while depth and i < len(text):
                if text.startswith('/-', i): depth += 1; i += 2
                elif text.startswith('-/', i): depth -= 1; i += 2
                else: i += 1
            if depth: raise ValueError('unterminated block comment')
        elif text[i] == '"':
            i += 1
            while i < len(text):
                if text[i] == '\\': i += 2
                elif text[i] == '"': i += 1; break
                else: i += 1
            else: raise ValueError('unterminated string literal')
        elif text[i] == '«':
            end = text.find('»', i)
            if end < 0: raise ValueError('unterminated quoted identifier')
            i = end + 1
            continue
        elif text[i] == "'" and (m := re.match(r"'(?:\\.|[^\\'\n])'", text[i:])):
            i += len(m[0])
        else:
            i += 1
            continue
        for j in range(start, min(i, len(text))):
            if out[j] != '\n': out[j] = ' '
    return ''.join(out)


def components(name):
    if not IDENT.fullmatch(name): raise ValueError(f'invalid Lean declaration name: {name}')
    return [p[1:-1] if p.startswith('«') else p for p in re.findall(r'«[^»]+»|[^.]+', name)]


def _json_unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def source_inventory(path, root, manifests):
    source = masked_source(path.read_text())
    rel = path.relative_to(root).as_posix()
    namespace = []
    scopes = []
    rows = []
    matches = list(COMMAND.finditer(source))
    positions = {match.start('cmd') for match in matches}
    # Reject unsupported inline declaration forms instead of silently skipping
    # them (e.g. `namespace A in theorem ...` or inline `set_option ... in`).
    # Quoted identifiers may contain reserved words and are not command tokens.
    unquoted = re.sub(r'«[^»]*»', lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), source)
    for token in re.finditer(r'(?<!\.)\b(?:theorem|def|abbrev|structure|inductive|instance|class|opaque|axiom|constant|constants|initialize|builtin_initialize)\b', unquoted):
        token_line = source.count('\n', 0, token.start()) + 1
        if token.start() not in positions and not any(r['file'] == rel and r['line'] == token_line for r in manifests):
            raise ValueError(f'{rel}: unsupported inline declaration requires audit_manifest.json')
    for match in matches:
        kind = match['cmd']
        mods = match['mods'].split()
        rest = source[match.end():].lstrip(' \t')
        ident = IDENT.match(rest)
        label = ident[0] if ident else ''
        line = source.count('\n', 0, match.start()) + 1
        if kind in {'namespace', 'section', 'mutual'}:
            scopes.append((kind, label, list(namespace)))
            if kind == 'namespace':
                if not label: raise ValueError(f'{rel}:{line}: unnamed namespace')
                parts = components(label)
                namespace = parts[1:] if parts[0] == '_root_' else namespace + parts
        elif kind == 'end':
            if not scopes: raise ValueError(f'{rel}:{line}: unmatched end')
            _, expected, before = scopes.pop()
            if label and label != expected: raise ValueError(f'{rel}:{line}: mismatched end {label}')
            namespace = before
        elif 'private' in mods:
            continue
        elif kind in KINDS:
            if not label:
                if not any(r['file'] == rel and r['line'] == line for r in manifests):
                    raise ValueError(f'{rel}:{line}: anonymous declaration requires audit_manifest.json')
                continue
            parts = components(label)
            full = parts[1:] if parts[0] == '_root_' else namespace + parts
            name = '.'.join(p if IDENT.fullmatch(p) and '.' not in p else f'«{p}»' for p in full)
            rows.append({'name': name, 'components': full, 'kind': kind, 'file': rel, 'line': line})
        elif not any(r['file'] == rel and r['line'] == line for r in manifests):
            raise ValueError(f'{rel}:{line}: generated declaration syntax requires audit_manifest.json')
    if scopes: raise ValueError(f'{rel}: unclosed namespace/section')
    return rows


def inventory(root):
    root = Path(root).resolve(strict=True)
    manifests = []
    for path in sorted((root / 'BornCalculus').rglob('audit_manifest.json')):
        document = json.loads(path.read_text(), object_pairs_hook=_json_unique)
        for row in document['declarations']:
            row = dict(row)
            file = root / row['file']
            if not file.resolve().is_relative_to(root) or not file.is_file() or file.suffix != '.lean':
                raise ValueError(f'invalid manifest source: {file}')
            if row['kind'] not in KINDS or not isinstance(row['line'], int) or row['line'] < 1:
                raise ValueError(f'invalid manifest declaration: {row}')
            row['components'] = components(row['name'])
            manifests.append(row)
    rows = []
    paths = [root / 'BornCalculus.lean', *sorted((root / 'BornCalculus').rglob('*.lean'))]
    for path in paths:
        if path.is_file() and path.relative_to(root).as_posix() not in AUDIT_ONLY:
            rows.extend(source_inventory(path, root, manifests))
    by_name = {}
    for row in [*rows, *manifests]:
        row['module'] = row['file'].removesuffix('.lean').replace('/', '.')
        if row['name'] in by_name:
            if row != by_name[row['name']]: raise ValueError(f'duplicate declaration: {row["name"]}')
        by_name[row['name']] = row
    if not rows and not manifests: raise ValueError('no BornCalculus declarations at the supplied Lean root')
    return sorted(by_name.values(), key=lambda r: (r['file'], r['line'], r['name']))


def verify(output, names):
    if len(names) != len(set(names)): raise ValueError('duplicate audit declaration')
    receipts = [json.loads(line.split(' ', 1)[1], object_pairs_hook=_json_unique)
                for line in output.splitlines() if line.startswith('BORN_AXIOM_AUDIT_JSON ')]
    if len(receipts) > 1: raise ValueError('multiple fresh audit receipts')
    if receipts:
        if receipts[0].get('schema') != 'born_axiom_dependencies_v2': raise ValueError('unknown audit schema')
        found = receipts[0]['dependencies']
    else:
        found = {}
        for name, payload in re.findall(r"'(.+?)' (does not depend on any axioms|depends on axioms: \[[^\]]*\])", output):
            if name in found: raise ValueError(f'duplicate axiom output: {name}')
            found[name] = [] if payload.startswith('does not') else [x.strip() for x in payload.split('[', 1)[1][:-1].split(',') if x.strip()]
    if any(not isinstance(axs, list) or any(not isinstance(a, str) for a in axs) for axs in found.values()):
        raise ValueError('invalid axiom dependency list')
    missing = sorted(set(names) - found.keys())
    extra = sorted(found.keys() - set(names)) if receipts else []
    forbidden = {name: sorted(set(found[name]) - ALLOWED) for name in names if name in found and set(found[name]) - ALLOWED}
    if missing or extra or forbidden or 'error:' in output:
        raise ValueError(f'axiom audit failed: missing={missing}, extra={extra}, forbidden={forbidden}')
    result = {'status': 'PASS', 'declarations': len(names), 'allowed_axioms': sorted(ALLOWED),
              'dependencies': {name: sorted(found[name]) for name in names}, 'forbidden': forbidden}
    if receipts:
        result['kernel_graph'] = {k: v for k, v in receipts[0].items() if k not in {'schema', 'dependencies'}}
    return result


def _tree_usage(pid):
    # PPid is process-wide. /proc/PID/task/PID/children alone misses subprocesses
    # launched by Lake worker threads and underreports concurrent build memory.
    children = {}
    usage = {}
    for base in Path('/proc').iterdir():
        if not base.name.isdigit(): continue
        try:
            stat = (base / 'stat').read_text()
            end = stat.rindex(')')
            fields = stat[end + 2:].split()
            child = int(base.name)
            children.setdefault(int(fields[1]), []).append(child)
            usage[child] = (int(fields[21]) * os.sysconf('SC_PAGE_SIZE'), stat[stat.index('(') + 1:end] == 'lean')
        except (FileNotFoundError, ProcessLookupError, PermissionError): pass
    pending = [pid]
    rss = count = lean_count = 0
    while pending:
        child = pending.pop()
        if child not in usage: continue
        memory, lean = usage[child]
        rss += memory; count += 1; lean_count += lean
        pending.extend(children.get(child, []))
    return rss, count, lean_count


def run_measured(command, root, text=None, capture=True):
    """Sample aggregate RSS of the command and all descendants every 50 ms."""
    started = time.monotonic()
    workspace = Path(root) / '.lake' / 'audit'
    workspace.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=workspace, mode='w+') as stdout, tempfile.TemporaryFile(dir=workspace, mode='w+') as stderr:
        proc = subprocess.Popen(command, cwd=root, stdin=subprocess.PIPE if text is not None else None,
                                stdout=stdout if capture else None, stderr=stderr if capture else None, text=True)
        if text is not None:
            proc.stdin.write(text)
            proc.stdin.close()
        peak = processes = lean_processes = 0
        while proc.poll() is None:
            rss, count, leans = _tree_usage(proc.pid)
            peak = max(peak, rss); processes = max(processes, count); lean_processes = max(lean_processes, leans)
            time.sleep(0.05)
        stdout.seek(0); stderr.seek(0)
        output = stdout.read() + stderr.read() if capture else ''
    metrics = {'wall_seconds': round(time.monotonic() - started, 3), 'peak_tree_rss_bytes': peak,
               'max_processes': processes, 'max_lean_processes': lean_processes, 'sample_interval_seconds': 0.05}
    if proc.returncode: raise ValueError(f'{command} exited {proc.returncode}: {output[-6000:]}')
    return output, metrics


def prepare(root):
    """Fill renderer-omitted stable proof subdirectories, never census inputs."""
    root = Path(root).resolve(strict=True)
    source = Path(__file__).resolve().parents[1]
    copied = []
    if root != source:
        for packet in ('General', 'Boundaries'):
            for path in sorted((source / 'BornCalculus' / packet).rglob('*.lean')):
                target = root / path.relative_to(source)
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
                    copied.append(target.relative_to(root).as_posix())
    return {'copied_missing_proof_modules': copied}


def build(root, jobs=2):
    if not 1 <= jobs <= 8: raise ValueError('build jobs must be between 1 and 8')
    root = Path(root).resolve(strict=True)
    start = time.monotonic()
    prepared = prepare(root) if (root / 'BornCalculus.lean').exists() else {}
    paths = [root / 'BornCalculus.lean', *sorted((root / 'BornCalculus').rglob('*.lean'))]
    modules = {p.relative_to(root).with_suffix('').as_posix().replace('/', '.'): p for p in paths if p.is_file()}
    if not modules:  # Keep the existing Make/cache smoke contract usable with a stub Lake.
        _, metrics = run_measured(['lake', 'build'], root, capture=False)
        return {**metrics, **prepared}
    # The installed dependency cache is read-only for this campaign. Never
    # launch a dependency source build while scheduling local modules.
    run_measured(['lake', '--quiet', '--no-build', 'build', '@mathlib/Mathlib'], root)
    deps = {m: {i for row in re.findall(r'^\s*(?:public\s+)?import\s+([^\n]+)', masked_source(p.read_text()), re.M)
                for i in row.split() if i in modules} for m, p in modules.items()}
    done, pending = set(), set(modules)
    metrics = {'peak_tree_rss_bytes': 0, 'max_processes': 0, 'max_lean_processes': 0}
    stop = threading.Event()
    def monitor():
        while not stop.is_set():
            memory, processes, leans = _tree_usage(os.getpid())
            for key, value in zip(metrics, (memory, processes, leans)):
                metrics[key] = max(metrics[key], value)
            stop.wait(0.05)
    sampler = threading.Thread(target=monitor, daemon=True)
    sampler.start()
    receipts, active = [], {}
    logdir = root / '.lake' / 'audit' / 'build-logs'
    logdir.mkdir(parents=True, exist_ok=True)
    def compile_one(name):
        output, measured = run_measured(['lake', '--log-level=error', 'build', name], root)
        (logdir / (name + '.log')).write_text(output)
        return {'module': name, **measured,
                'fresh_compile': bool(re.search(r'Built '+re.escape(name)+r' \(', output))}
    last_report = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            while pending or active:
                ready = sorted(m for m in pending if deps[m] <= done)
                for name in ready[:jobs-len(active)]:
                    pending.remove(name)
                    active[pool.submit(compile_one, name)] = name
                if not active:
                    raise ValueError('local module import cycle: ' + ', '.join(sorted(pending)))
                completed, _ = wait(active, timeout=0.5, return_when=FIRST_COMPLETED)
                for future in completed:
                    name = active.pop(future)
                    receipt = future.result()
                    receipts.append(receipt)
                    done.add(name)
                    if receipt['fresh_compile']:
                        print(f'Built {name} ({receipt["wall_seconds"]} s)', flush=True)
                if time.monotonic()-last_report >= 20:
                    print(f'Build progress: {len(done)}/{len(modules)} complete; '
                          f'{len(active)} active; peak {metrics["peak_tree_rss_bytes"]/2**30:.2f} GiB', flush=True)
                    last_report = time.monotonic()
                    (root / '.lake' / 'audit' / 'build-live.json').write_text(json.dumps(
                        {'completed':len(done),'modules':len(modules),'active':sorted(active.values()),**metrics}))
    finally:
        stop.set()
        sampler.join()
    # Default target completion is checked without creating an unbounded build.
    run_measured(['lake', '--quiet', '--no-build', 'build'], root)
    (root / '.lake' / 'audit' / 'build-modules.json').write_text(json.dumps(receipts, sort_keys=True, indent=2)+'\n')
    return {'status': 'PASS', 'modules': len(modules), 'fresh_modules':sum(r['fresh_compile'] for r in receipts),
            'scheduling':'bounded ready-module queue', 'parallelism_limit': jobs,
            'wall_seconds': round(time.monotonic() - start, 3), 'sample_interval_seconds': 0.05, **metrics, **prepared}


def audit(root, declarations=None):
    root = Path(root).resolve(strict=True)
    rows = inventory(root)
    all_names = [row['name'] for row in rows]
    names = all_names if declarations is None else declarations
    if not names or len(set(names)) != len(names) or not set(names) <= set(all_names):
        raise ValueError('duplicate, empty or unknown audit declaration')
    # Fail rather than certify stale artifacts. This checks every module and
    # import trace, including newly added census shards, without rebuilding.
    run_measured(['lake', '--quiet', '--no-build', 'build'], root)
    selected_names = set(names)
    selected = [row for row in rows if row['name'] in selected_names]
    directory = root / '.lake' / 'audit'
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', dir=directory) as manifest:
        json.dump(selected, manifest)
        manifest.flush()
        source = 'import BornCalculus.Audit\n#audit_declarations ' + json.dumps(manifest.name) + '\n'
        output, metrics = run_measured(['lake', 'env', 'lean', '-j1', '--stdin'], root, source)
    result = verify(output, names)
    result['fresh'] = True
    result['inventory_scope'] = 'recursive public source declarations; private/compiler helpers traversed transitively'
    result['breakdown'] = {'kind': dict(sorted(Counter(r['kind'] for r in selected).items())),
                           'directory': dict(sorted(Counter(str(Path(r['file']).parent) for r in selected).items())),
                           'namespace': dict(sorted(Counter('.'.join(r['components'][:-1]) for r in selected).items()))}
    result['measurement'] = metrics
    # Backward-compatible paper ledger source, plus a directly usable ledger ID.
    result['ledger'] = {'LeanDeclarationsAudited': len(names), 'evidence_type': 'audit_metadata'}
    result['macros'] = {'LeanDeclarations': len(names)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['audit', 'verify', 'inventory', 'build', 'prepare'])
    parser.add_argument('--lean-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--declaration', action='append')
    parser.add_argument('--log', type=Path)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    try:
        if args.command == 'inventory': result = inventory(args.lean_root)
        elif args.command == 'audit': result = audit(args.lean_root, args.declaration)
        elif args.command == 'build': result = build(args.lean_root, args.jobs)
        elif args.command == 'prepare': result = prepare(args.lean_root)
        else:
            if args.log is None: parser.error('verify requires --log')
            result = verify(args.log.read_text(), args.declaration or [r['name'] for r in inventory(args.lean_root)])
        print(json.dumps(result, sort_keys=True))
        if args.command == 'audit':
            print(f'Lean audit: {result["status"]}, {result["declarations"]} declarations, '
                  'axioms '+', '.join(result['allowed_axioms'])+'; forbidden: none',
                  file=sys.stderr, flush=True)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f'FAIL: {exc}\n')


if __name__ == '__main__':
    main()
