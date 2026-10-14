"""Exact retained-K replay through the shipped Rust exports, without a sampler.

Promotes the historical arch_probe/join_probe approach to a public command.
The private runner context_maps body is compiled unchanged with a read-only
wrapper appended, and calls the public spectral and sector-packaging routines.
"""
import json
import os
from pathlib import Path
import struct
import subprocess
import time

from born_ladder.archive import Archive, put, safe_name, sha
from .runs import exclusive_output, validate_output

FIELDS = {'raw': 'raw_by_state', 'package': 'package_by_state', 'joint': 'joint_by_state'}
ASSETS = Path(__file__).with_name('map_replay_assets')


def read(path):
    return json.loads(Path(path).read_text())


def build_replayer(source_root, directory):
    """Compile the historical wrapper against actual public sources, offline."""
    source_root = Path(source_root).resolve()
    directory = validate_output(directory, source_root)
    public = source_root/'vendor/pica'
    directory.mkdir(parents=True, exist_ok=True)
    with exclusive_output(directory):
        crate = directory/'crate'; (crate/'src').mkdir(parents=True, exist_ok=True)
        sidecar = public/'crates/runner/src/test_b_sidecar.rs'
        (crate/'src/public_sidecar.rs').write_bytes(sidecar.read_bytes() + (ASSETS/'sidecar_wrapper.rs').read_bytes())
        (crate/'src/main.rs').write_bytes((ASSETS/'main.rs').read_bytes())
        manifest = ('[package]\nname = "born_map_replay"\nversion = "0.1.0"\nedition = "2021"\n'
                    '[workspace]\n[dependencies]\n')
        for name, folder in [('six_dynamics', 'dynamics'), ('six_primitives_core', 'six_primitives_core')]:
            manifest += f'{name} = {{ path = {json.dumps(str(public/"crates"/folder))} }}\n'
        manifest += ('serde = { version = "1", features = ["derive"] }\n'
                     'serde_json = { version = "1", features = ["float_roundtrip"] }\n'
                     'rand = "0.8"\nrand_chacha = "0.3"\nsha2 = "0.10"\n')
        (crate/'Cargo.toml').write_text(manifest)
        # Seed dependency versions from the shipped lock; Cargo removes unused
        # workspace packages and adds this read-only driver without fetching.
        if not (crate/'Cargo.lock').exists():
            (crate/'Cargo.lock').write_bytes((public/'Cargo.lock').read_bytes())
        command = ['cargo', 'build', '--offline', '--release', '--manifest-path', str(crate/'Cargo.toml'),
                   '--target-dir', str(directory/'target')]
        with (directory/'build.log').open('w') as log:
            subprocess.run(command, check=True, stdout=log, stderr=log)
    binary = directory/'target/release/born_map_replay'
    # Bind the whole scientific Rust source, not just the wrapper or executable.
    files = sorted((public/'crates/dynamics').rglob('*.rs')) + sorted((public/'crates/six_primitives_core').rglob('*.rs'))
    files += [sidecar, public/'Cargo.lock', public/'Cargo.toml',
              public/'crates/dynamics/Cargo.toml', public/'crates/six_primitives_core/Cargo.toml']
    return binary, {'command': command, 'binary_sha256': sha(binary),
                    'cargo_lock_sha256': sha(crate/'Cargo.lock'),
                    'rustc': subprocess.check_output(['rustc', '--version'], text=True).strip(),
                    'cargo': subprocess.check_output(['cargo', '--version'], text=True).strip(),
                    'rustflags': os.environ.get('RUSTFLAGS'),
                    'source_sha256': {str(p.relative_to(source_root)): sha(p) for p in files},
                    'driver_sha256': {name: sha(ASSETS/name) for name in ('main.rs', 'sidecar_wrapper.rs')},
                    'float_roundtrip': True, 'public_sidecar_body_unchanged': True}


def census_inputs(root):
    """Bind each replay K to the sealed exponent-one native-field adapter."""
    root = Path(root).resolve(); seal = read(root/'complete.json')
    summary = seal['summary']
    if seal['status'] != 'PASS' or summary.get('completion_status') != 'PASS':
        raise ValueError('census construction incomplete')
    commitments = {a['path']: a['sha256'] for a in seal['artifacts']}

    def bound(name):
        name = str(safe_name(name)); path = root/name
        if name not in commitments or sha(path) != commitments[name]:
            raise ValueError('missing or invalid replay input commitment: '+name)
        return read(path), commitments[name]

    inventory, inventory_hash = bound(str(Path(summary['inventory_directory'])/'INVENTORY.json'))
    completed, completion_hash = bound(str(Path(summary['summary_directory'])/'structural_completion_results.json'))
    if not inventory or len(inventory) != len(completed) or len(inventory) != summary['selected_count']:
        raise ValueError('incomplete census membership')
    # Historical retained matrices can point directly into captured stdout;
    # added matrices use the census-local K adapters. The sealed logical view
    # resolves both without changing their field/file commitments.
    execution_files = {}
    if 'census_plan.json' in commitments:
        plan, _ = bound('census_plan.json')
        execution_files.update(plan['logical_to_execution_files'])
    rows = []; seen = set()
    for index, (row, entry) in enumerate(zip(inventory, completed)):
        uid = row['unit_id']
        if uid in seen or entry['unit_id'] != uid or entry['index'] != index or entry['status'] != 'PASS':
            raise ValueError('invalid census identity/order/status')
        seen.add(uid)
        name = str(Path(entry['context_directory'])/'CONTEXT.json')
        context, context_hash = bound(name)
        if context['identity']['unit_id'] != uid:
            raise ValueError('context identity differs')
        pointer = row['kernel']['artifact']
        if row['kernel']['operation'] != 'K' or pointer['exponent'] != 1 or pointer != row['provenance_key']['kernel']['artifact']:
            raise ValueError('replay requires retained K at exponent one')
        # The adapter's payload/field checks are the same historical Archive
        # reader, not a matrix reconstruction or power inversion.
        native_name = str(safe_name(pointer['path']))
        if native_name in commitments:
            if commitments[native_name] != pointer['file_sha256']:
                raise ValueError('sealed native K file commitment differs')
            native_path = root/native_name
        elif native_name in execution_files:
            native_path = Path(execution_files[native_name])
        else:
            raise ValueError('native K storage correspondence missing')
        archive = Archive({'schema': 'born_structural_input_view_v1', 'root': str(root),
                           'files': {native_name: str(native_path)}})
        if archive.structural(row) != context['kernel']:
            raise ValueError('sealed native K differs from context K')
        for short, field in FIELDS.items():
            if context['lens'][field] != row['lenses'][short+'_map']:
                raise ValueError('inventory/context map differs')
        rows.append(replay_input(context, index, uid, {'context': str(root/name),
                    'context_sha256': context_hash, 'kernel_pointer': pointer,
                    'native_kernel_source': str(native_path)}))
    return rows, {'census': str(root), 'complete_sha256': sha(root/'complete.json'),
                  'inventory_sha256': inventory_hash, 'completion_table_sha256': completion_hash,
                  'sealed_inputs_checked': True}


def replay_input(context, index, uid, receipt):
    born = context['born']; k = born['k']; n = len(context['kernel'])
    if type(k) is not int or k < 2 or any(len(r) != n for r in context['kernel']):
        raise ValueError('invalid matrix/resolution')
    resolution = context['identity'].get('resolution', context['identity'].get('k'))
    if resolution != k:
        raise ValueError('identity/emitted resolution differs')
    maps = {name: context['lens'][field] for name, field in FIELDS.items()}
    if maps['raw'] != born['partition'] or maps['package'] != born['packaging']:
        raise ValueError('context/emitted maps differ')
    if any(len(v) != n or any(type(label) is not int or label < 0 for label in v) for v in maps.values()):
        raise ValueError('invalid retained label map')
    return {'index': index, 'unit_id': uid, 'identity': context['identity'], 'kernel': context['kernel'],
            'k': k, 'retained_maps': maps, 'retained_pi': born['pi'],
            'retained_vectors': born['sym_eigvec_basis'], 'input_receipt': receipt}


def float_bits(vector):
    return [struct.pack('>d', v).hex() for v in vector]


def compare_replay(case, replay):
    """Exact labelled-state comparisons; retain every mismatch, without remapping."""
    if (case['index'], case['unit_id']) != (replay['index'], replay['unit_id']):
        raise ValueError('replayer identity/order differs')
    n = len(case['kernel']); differences = []; matched = {}
    for name in FIELDS:
        actual = replay['maps'][name]; expected = case['retained_maps'][name]
        if len(actual) != n:
            raise ValueError('incomplete recomputed map')
        mismatch = [{'state': i, 'retained': b, 'recomputed': a, 'absolute_difference': abs(a-b)}
                    for i, (a, b) in enumerate(zip(actual, expected)) if a != b]
        matched[name] = not mismatch
        if mismatch:
            differences.append({'map': name, 'differing_states': mismatch})
    diagnostic = {'stationary_exact': replay['stationary_bits'] == float_bits(case['retained_pi']),
                  'observable_pi_exact': replay['observable_pi_bits'] == replay['stationary_bits'],
                  'emitted_vectors_exact': replay['emitted_vector_bits'] == [float_bits(v) for v in case['retained_vectors']]}
    return {'index': case['index'], 'unit_id': case['unit_id'], 'identity': case['identity'],
            'input_receipt': case['input_receipt'], 'maps_exact': matched, 'differences': differences,
            'fallback': replay['fallback'], 'emitted_vector_count': len(replay['emitted_vector_bits']),
            'diagnostics': diagnostic,
            'status': 'PASS' if all(matched.values()) and all(diagnostic.values()) else 'FAIL'}


def run_map_replay(*, census, original_context, output, source_root=None, build_directory=None):
    start = time.monotonic()
    # Rust/specification inputs belong to the public checkout, not site-packages.
    source_root = Path(source_root or Path.cwd()).resolve()
    output = validate_output(output, source_root)
    # Explicit commands only read the census/worked inputs. Refuse output or
    # build paths within either input tree, even if Git-ignored or external.
    original_context = Path(original_context).resolve(); census = Path(census).resolve()
    build_directory = Path(build_directory or output/'build').resolve()
    for target in (output, build_directory):
        for input_root in (census, original_context.parent):
            if target == input_root or target.is_relative_to(input_root):
                raise ValueError('replay output/build must be outside input trees')
    with exclusive_output(output):
        attempt = output/f'attempt_{1+len(list(output.glob("attempt_*"))):04d}'
        attempt.mkdir()
        cases, inputs = census_inputs(census)
        cohort_count = len(cases)
        original = read(original_context)
        wanted = {'exp': 'EXP-112', 'config': 'loo_A25', 'seed': 910000, 'scale': 32, 'k': 2, 'step_index': 0}
        if original['identity'] != wanted:
            raise ValueError('expected original worked case EXP-112/loo_A25/910000, not selected census fixture')
        cases.append(replay_input(original, 'original', 'original-worked-case',
                     {'context': str(original_context), 'context_sha256': sha(original_context), 'kernel_exponent': 1}))
        with (attempt/'inputs.jsonl').open('x') as stream:
            for case in cases:
                stream.write(json.dumps(case, allow_nan=False, separators=(',', ':'))+'\n')
        prepared = time.monotonic()
        binary, build = build_replayer(source_root, build_directory)
        built = time.monotonic()
        with (attempt/'recomputed.jsonl').open('xb') as out, (attempt/'replay.stderr').open('xb') as err:
            subprocess.run([str(binary), str(attempt/'inputs.jsonl')], stdout=out, stderr=err, check=True)
        replayed = time.monotonic()
        results = list(map(json.loads, (attempt/'recomputed.jsonl').read_text().splitlines()))
        if len(results) != len(cases):
            raise ValueError('incomplete executable replay')
        checks = [compare_replay(case, result) for case, result in zip(cases, results)]
        cohort = checks[:cohort_count]
        summary = {'schema': 'born_retained_K_map_replay_v1',
                   'status': 'PASS' if all(c['status'] == 'PASS' for c in checks) else 'FAIL',
                   'contexts': cohort_count,
                   'matched_per_map': {name: sum(c['maps_exact'][name] for c in cohort) for name in FIELDS},
                   'fallback_contexts': sum(c['fallback'] for c in cohort),
                   'diagnostics_matched': {name: sum(c['diagnostics'][name] for c in cohort) for name in cohort[0]['diagnostics']},
                   'original_worked_case': checks[-1],
                   'mismatches': [c for c in checks if c['status'] != 'PASS'],
                   'inputs': inputs, 'build': build, 'attempt': str(attempt),
                   'wall_seconds': time.monotonic()-start,
                   'input_wall_seconds': prepared-start, 'build_wall_seconds': built-prepared,
                   'executable_wall_seconds': replayed-built,
                   'no_matrix_normalization_or_power_inversion': True,
                   'comparison': 'exact integer labels per state; exact binary64 stationary and emitted vectors'}
        put(attempt/'checks.json', checks)
        put(attempt/'summary.json', summary)
        print(json.dumps({key: summary[key] for key in ('status', 'contexts', 'matched_per_map', 'wall_seconds')}), flush=True)
        return summary
