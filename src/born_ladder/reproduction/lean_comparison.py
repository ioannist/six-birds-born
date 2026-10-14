"""Historical Lean subset equality and independent full-source audit coverage.

No build or write takes place in either input tree. Historical statements are
bound by retained source bodies; the archive contains only transitive axiom
sets, not statement types or a complete dependency graph.
"""
from collections import Counter
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile

ALLOWED = {'Classical.choice', 'Quot.sound', 'propext'}
SCOPE = 'recursive public source declarations; private/compiler helpers traversed transitively'


def read(path):
    return json.loads(Path(path).read_text())


def initial_header(text):
    # Project only initial comments/blank lines, including Lean's nested blocks.
    at = 0
    while at < len(text):
        blank = re.match(r'[ \t\r]*\n', text[at:])
        if blank:
            at += blank.end()
        elif text.startswith('--', at):
            end = text.find('\n', at)
            at = len(text) if end < 0 else end + 1
        elif text.startswith('/-', at):
            depth = 1
            end = at + 2
            while depth and end < len(text):
                if text.startswith('/-', end): depth += 1; end += 2
                elif text.startswith('-/', end): depth -= 1; end += 2
                else: end += 1
            if depth: raise ValueError('unterminated initial Lean header')
            at = end
            # A newline following the block is part of the initial header.
            whitespace = re.match(r'[ \t\r]*\n', text[at:])
            if whitespace: at += whitespace.end()
        else:
            break
    return text[at:], text[:at]


def driver(lean_root=None):
    """Load checkout tools, independent of the Python installation location.

    Commands run from the repository root; an explicit Lean project may supply
    its own tools. Packaged Python code is not a parent of the public checkout.
    """
    root = Path(lean_root).resolve() if lean_root is not None else Path.cwd()/'lean_born'
    path = root/'tools/audit_declarations.py'
    if not path.is_file():
        raise FileNotFoundError('Lean audit tools unavailable: run from the repository root or supply a Lean project: '+str(path))
    spec = importlib.util.spec_from_file_location('born_comparison_lean_auditor', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def log_receipt(path, key):
    candidates = []
    for line in Path(path).read_text().splitlines():
        try: document = json.loads(line)
        except ValueError: continue
        if isinstance(document, dict) and key in document: candidates.append(document)
    if not candidates: raise FileNotFoundError('complete Lean receipt not present in ' + str(path))
    if key=='modules':
        producing=[r for r in candidates if r.get('fresh_modules',0)>0]
        if producing:candidates=producing
    return candidates[-1]


def axiom_sets(document):
    dependencies = document['dependencies']
    if type(dependencies) is not dict: raise ValueError('invalid Lean dependency mapping')
    result = {}
    for name, axioms in dependencies.items():
        if type(name) is not str or type(axioms) is not list or any(type(a) is not str for a in axioms):
            raise ValueError('invalid transitive axiom set for ' + str(name))
        if len(axioms) != len(set(axioms)): raise ValueError('duplicate axiom for ' + name)
        result[name] = sorted(axioms)
    return result


def readonly_kernel_check(target, rows, workspace):
    """Use shipped inventory/audit and Lake text hashes, with stdin only.

    Lean reads the retained compiled modules, traverses all transitive helpers,
    and hashes every public source (including the audit harness). It emits no
    compiled artifacts; its manifest and process output live in the comparison
    directory. No Lake build/cache command is run on the retained input tree.
    """
    target = Path(target).resolve()
    paths = [target/'BornCalculus.lean', *sorted((target/'BornCalculus').rglob('*.lean'))]
    environment = dict(os.environ)
    libraries = [p/'.lake/build/lib/lean' for p in sorted((target/'.lake/packages').iterdir()) if p.is_dir()]
    environment['LEAN_PATH'] = os.pathsep.join(str(p) for p in [*libraries, target/'.lake/build/lib/lean'])
    with tempfile.TemporaryDirectory(prefix='lean-readonly-', dir=workspace) as temporary:
        manifest = Path(temporary)/'inventory.json'
        manifest.write_text(json.dumps(rows))
        expressions = ',\n'.join(json.dumps(str(path)) for path in paths)
        source = ('import Lake\nimport BornCalculus.Audit\n'
                  '#eval show IO Unit from do\n let paths : Array String := #[' + expressions + ']\n'
                  ' for path in paths do\n'
                  '  let h ← Lake.computeTextFileHash path\n'
                  '  IO.println (Lean.Json.compress (Lean.toJson (path, h.toString)))\n'
                  '#audit_declarations ' + json.dumps(str(manifest)) + '\n')
        process = subprocess.run(['lean', '-j1', '--stdin'], input=source, text=True,
                                 capture_output=True, cwd=target, env=environment)
        transcript = process.stdout + process.stderr
        (Path(workspace)/'lean_readonly_kernel.log').write_text(transcript)
        if process.returncode:
            errors = '\n'.join(line for line in transcript.splitlines() if 'error:' in line)
            raise ValueError('read-only fresh kernel check failed: ' + (errors or transcript[:6000]))
        hashes = {}
        for line in process.stdout.splitlines():
            try: value = json.loads(line)
            except ValueError: continue
            if isinstance(value, list) and len(value) == 2 and all(type(x) is str for x in value):
                hashes[value[0]] = value[1]
        result = driver().verify(process.stdout, [row['name'] for row in rows])
        if set(hashes) != {str(p) for p in paths}: raise ValueError('incomplete current Lean source hashes')
        for path in paths:
            relative = path.relative_to(target)
            tracefile = target/'.lake/build/lib/lean'/relative.with_suffix('.trace')
            if not tracefile.is_file(): raise ValueError('missing compiled Lean source trace: ' + relative.as_posix())
            trace = read(tracefile)
            # Cached build traces may retain the original checkout's source
            # caption. Bind the complete module-relative identity and content
            # hash, rather than treating an absolute storage address as science.
            source_inputs = [v for k, v in trace['inputs']
                             if type(k) is str and k.endswith('/' + relative.as_posix())]
            if source_inputs != [hashes[str(path)]]:
                raise ValueError('stale compiled Lean source: ' + relative.as_posix())
        return {**result, 'source_hashes_checked': len(paths), 'read_only': True}


def _compare_lean(comparison, *, target, historical_sources, audit, historical_audit,
                 coverage, build, workspace, fresh_check=readonly_kernel_check):
    c = comparison
    target, historical_sources = Path(target), Path(historical_sources)
    auditor = driver()
    historical_rows = auditor.inventory(historical_sources)
    fresh_rows = auditor.inventory(target)
    old = axiom_sets(historical_audit)
    new = axiom_sets(audit)
    expected_audit_keys = {'allowed_axioms','breakdown','declarations','dependencies','forbidden','fresh',
                           'inventory_scope','kernel_graph','ledger','macros','measurement','status'}
    c.compare('fresh_Lean_receipt_schema', sorted(audit), sorted(expected_audit_keys))
    c.compare('historical_Lean_audit_status', historical_audit['status'], 'PASS')
    c.compare('historical_Lean_audit_count', historical_audit['declarations'], len(old))
    historical_names = set(old)
    inventory_names = {row['name'] for row in fresh_rows}
    c.compare('historical_source_inventory', sorted({row['name'] for row in historical_rows}), sorted(old))
    source_files = sorted(p.relative_to(historical_sources).as_posix()
                          for p in (historical_sources/'BornCalculus').rglob('*.lean')
                          if p.relative_to(historical_sources).as_posix() not in auditor.AUDIT_ONLY)
    for name in source_files:
        expected, eh = initial_header((historical_sources/name).read_bytes().decode('utf-8'))
        c.compare('historical_Lean_source_membership', (target/name).is_file(), True, name)
        if not (target/name).is_file(): continue
        actual, ah = initial_header((target/name).read_bytes().decode('utf-8'))
        c.compare('historical_Lean_statement_sources', actual, expected, name)
        if ah != eh: c.record('header_projection', name, ah, eh, 'initial provenance comment header only', True)
    for name in ('lakefile.toml', 'lake-manifest.json', 'lean-toolchain'):
        c.compare('historical_Lean_build_configuration', (target/name).read_bytes().decode('utf-8'), (historical_sources/name).read_bytes().decode('utf-8'), name)
    c.compare('historical_Lean_declaration_membership', sorted(historical_names & set(new)), sorted(historical_names))
    for name in sorted(historical_names & set(new)):
        c.compare('historical_Lean_transitive_axiom_sets', new[name], old[name], name)
    # Additions have independent checks only, never archive equality credit.
    added = sorted(set(new)-historical_names)
    c.compare('fresh_Lean_inventory_membership', sorted(new), sorted(inventory_names))
    for name in added:
        c.compare('added_Lean_allowed_transitive_axioms', sorted(set(new[name])-ALLOWED), [], name)
    c.compare('fresh_Lean_audit_status', audit['status'], 'PASS')
    c.compare('fresh_Lean_audit_freshness', audit.get('fresh'), True)
    c.compare('fresh_Lean_allowlist', sorted(audit['allowed_axioms']), sorted(ALLOWED))
    c.compare('fresh_Lean_forbidden', audit['forbidden'], {})
    c.compare('fresh_Lean_declaration_count', audit['declarations'], len(fresh_rows))
    c.compare('fresh_Lean_scope', audit['inventory_scope'], SCOPE)
    expected_breakdown = {
        'kind': dict(Counter(r['kind'] for r in fresh_rows)),
        'directory': dict(Counter(str(Path(r['file']).parent) for r in fresh_rows)),
        'namespace': dict(Counter('.'.join(r['components'][:-1]) for r in fresh_rows)),
    }
    c.compare('fresh_Lean_breakdown', audit['breakdown'], expected_breakdown)
    c.compare('fresh_Lean_ledger', audit['ledger'], {'LeanDeclarationsAudited':len(fresh_rows), 'evidence_type':'audit_metadata'})
    c.compare('fresh_Lean_macros', audit['macros'], {'LeanDeclarations':len(fresh_rows)})
    c.compare('fresh_Lean_build_status', build['status'], 'PASS')
    module_files = [target/'BornCalculus.lean', *sorted((target/'BornCalculus').rglob('*.lean'))]
    c.compare('fresh_Lean_build_modules', build['modules'], len(module_files))
    if type(build['fresh_modules']) is not int or not 0 <= build['fresh_modules'] <= len(module_files):
        raise ValueError('invalid fresh Lean build module count')
    c.compare('formal_coverage_status', coverage['status'], 'APPLICABLE')
    c.compare('formal_coverage_build_status', coverage['build_status'], 'BUILT_AND_AUDITED')
    c.compare('formal_full_cohort', coverage['full_cohort_inputs'], True)
    c.compare('formal_census_cases', coverage['census_cases'], 2122)
    c.compare('formal_exact_cases', coverage['exact_certificate_cases_checked'], 2122)
    c.compare('formal_worked_cases', coverage['worked_certificates_checked'], True)
    c.compare('formal_build_targets', coverage['required_build_targets'],
              ['BornCalculus.Census.FullWitness','BornCalculus.Census.AuditFull'])
    # The registered 3/20 shortfalls are outcomes, not execution failures.
    c.compare('formal_registered_shortfalls', coverage['registered_gap_bound_failures'], 117)
    c.compare('formal_registered_bound', coverage['registered_gap_bound_satisfied'], False)
    c.compare('fresh_Lean_kernel_metadata_schema', sorted(audit['kernel_graph']),
              ['dependency_edges','reachable_constants','traversal_ms'])
    for metric in ('reachable_constants', 'dependency_edges', 'traversal_ms'):
        value = audit['kernel_graph'][metric]
        if type(value) is not int or value < (0 if metric == 'traversal_ms' else 1):
            raise ValueError('invalid kernel graph metadata: ' + metric)
    for document in (audit, build):
        measurement = document.get('measurement', document)
        if document is audit:
            c.compare('fresh_Lean_measurement_schema', sorted(measurement),
                      ['max_lean_processes','max_processes','peak_tree_rss_bytes','sample_interval_seconds','wall_seconds'])
        for key in ('wall_seconds', 'peak_tree_rss_bytes', 'max_processes', 'max_lean_processes', 'sample_interval_seconds'):
            value = measurement[key]
            if type(value) not in (int,float) or not math.isfinite(value) or value <= 0:
                raise ValueError('invalid Lean receipt measurement: ' + key)
    fresh = fresh_check(target, fresh_rows, workspace)
    c.compare('fresh_kernel_replay_status', fresh['status'], 'PASS')
    c.compare('fresh_kernel_replay_axiom_sets', axiom_sets(fresh), new)
    for metric in ('reachable_constants', 'dependency_edges'):
        c.compare('fresh_kernel_graph_coverage', fresh['kernel_graph'][metric], audit['kernel_graph'][metric])
    return {'audit':audit, 'historical_declarations':len(old), 'historical_source_files':len(source_files),
            'added_declarations':len(added), 'historical_matches_for_added_declarations':0,
            'fresh_source_inventory_declarations':len(fresh_rows), 'fresh_validation':fresh,
            'historical_equality_scope':'retained source statements and unordered transitive axiom sets; archive has no complete dependency graph',
            'receipt_metadata_validation':'separate from historical equality',
            'historical_fields_compared':sum(v['compared'] for k,v in c.groups.items() if k.startswith('historical_')),
            'historical_fields_exact':sum(v['exact'] for k,v in c.groups.items() if k.startswith('historical_')),
            'fresh_validation_fields_checked':sum(v['compared'] for k,v in c.groups.items() if not k.startswith('historical_')),
            'historical_source_root':str(historical_sources)}


def compare_lean(comparison, **arguments):
    # Receipt metadata such as breakdown.directory is meaningful coverage here,
    # not a filesystem location. Disable the generic storage/process projection.
    projected = comparison.projection
    comparison.projection = False
    try:
        return _compare_lean(comparison, **arguments)
    finally:
        comparison.projection = projected
