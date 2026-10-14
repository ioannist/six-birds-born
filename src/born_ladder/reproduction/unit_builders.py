"""I/O adapters for the single historical scientific implementations.

No population statistics or archived scientific results are construction inputs.
"""
from dataclasses import dataclass

from born_ladder.snapshot.collector_structural import reconstruct_collector_record
from born_ladder.snapshot.errors import IncompleteCampaign
from born_ladder.snapshot.frozen_spec import canonical_json_bytes, sha256_bytes
from born_ladder.snapshot.g2a import _derive_unit_pair, _raw_segments
from born_ladder.snapshot.g2c_collector_structural import (
    parse_g2c_raw_segments, reconstruct_g2c_collector_record,
)
from born_ladder.snapshot.g2c_controls import build_g2c_controls, gradual_underflow_certificate
from born_ladder.snapshot.evidence import g2c_control_input_projection
from born_ladder.snapshot.g2c_units import (
    SealedG2CUnitDrafts, _contract, _pair_and_control_source,
    finalize_g2c_artifacts, require_scientific_g2c_segments,
)
from born_ladder.snapshot.runner_structural import parse_runner_stdout
from born_ladder.snapshot.universal_shapes import canonical_jsonl_bytes, validate_stage_records


@dataclass
class BuiltInvocation:
    structural: dict
    files: dict
    disposition: dict


def build_invocation(spec, evaluation, stdout, invocation, attempt_sha):
    """Reconstruct both channels before deriving paired unit/control records."""
    source = getattr(spec, '_g2c_source_spec', spec)
    runner = parse_runner_stdout(source, stdout)
    reconstruct = (reconstruct_collector_record if evaluation == 'competitor'
                   else reconstruct_g2c_collector_record)
    structural = reconstruct(source, stdout, invocation)
    if structural != runner.manifest:
        raise IncompleteCampaign('runner/collector structural channels differ')
    # v8 binds the manifest without LF; the cross-term/CB2 unit binding hashes
    # its JSONL row with LF. Keep both historical conventions rather than
    # silently giving v8 the later census convention.
    structural_sha = (runner.manifest_sha256 if evaluation == 'competitor'
                      else sha256_bytes(canonical_json_bytes(structural)))
    units = {(u['config_id'], u['step_id'], u['resolution']): u
             for u in structural['units']}
    if len(units) != len(structural['units']):
        raise IncompleteCampaign('duplicate structural unit identity')
    records, control_sources, reconstructions, observed = [], [], [], []
    files = {'structural.jsonl': canonical_json_bytes(structural),
             'runner_structural.json': canonical_json_bytes(runner.record)}
    if evaluation == 'competitor':
        born, discovery, audit = _raw_segments(source, stdout)
        if audit['exp_id']!=invocation['experiment'] or any(
                row['seed']!=invocation['seed'] or row['scale']!=invocation['scale']
                or row['cell']!=invocation['config_or_null'] for row in born):
            raise IncompleteCampaign('capture scientific identity differs from invocation')
        for row in born:
            key = (row['cell'], str(row['step_index']), row['k'])
            records.extend(_derive_unit_pair(source, born=row, discovery=discovery,
                audit=audit, invocation=invocation, structural_unit=units[key],
                structural_manifest_sha256=structural_sha, attempt_record_sha256=attempt_sha))
            observed.append(key)
        validated = validate_stage_records(source, records, stage_profile='g2a',
            expected_structural_manifest_sha256=structural_sha,
            expected_attempt_record_sha256=attempt_sha)
        records = [{k:v for k,v in row.items() if k != '_derived_kind'} for row in validated]
        files['units.jsonl'] = canonical_jsonl_bytes(records)
        controls = []
    else:
        segments = parse_g2c_raw_segments(source, stdout, invocation)
        files['segment_census.json'] = canonical_json_bytes([
            {'configuration': s.label, 'partial_suppressions': list(s.suppressed_pairs),
             'complete_suppression': s.complete_suppression} for s in segments])
        require_scientific_g2c_segments(segments)
        contract = _contract(spec)
        for segment in segments:
            for row in segment.born:
                key = (segment.label, str(row['step_index']), row['k'])
                pair, control_pair, reconstruction = _pair_and_control_source(source,
                    segment=segment, born=row, invocation=invocation,
                    structural_unit=units[key], structural_sha256=structural_sha,
                    runner_sha256=runner.manifest_sha256, attempt_sha256=attempt_sha,
                    contract=contract)
                records.extend(pair); control_sources.extend(control_pair)
                if reconstruction is not None:
                    reconstructions.append(reconstruction)
                observed.append(key)
        drafts = SealedG2CUnitDrafts(tuple(records), tuple(control_sources),
            {r['kind_cell_id']:g2c_control_input_projection(r) for r in control_sources},
            tuple(reconstructions), {invocation['invocation_id']:attempt_sha},
            {invocation['invocation_id']:structural_sha},
            sum(u['kind_availability'] == ['raw', 'pkg'] for u in units.values()))
        with gradual_underflow_certificate():
            built_controls = build_g2c_controls(spec, control_sources)
            files['control_findings.json'] = canonical_json_bytes(list(built_controls.failures))
            files['controls.jsonl'] = canonical_jsonl_bytes(built_controls.records)
            files['rotation_evidence.json'] = canonical_json_bytes(built_controls.rotation_evidence)
            if not built_controls.complete:
                files['draft_units.jsonl'] = canonical_jsonl_bytes(records)
                return BuiltInvocation(structural, files, {
                    'status':'control_failure', 'findings':list(built_controls.failures),
                    'unit_rows':0, 'draft_rows':len(records)})
            final = finalize_g2c_artifacts(spec, drafts,
                control_rows=built_controls.records, rotation_evidence=built_controls.rotation_evidence)
        records, controls = list(final.records), list(final.controls_records)
        files['units.jsonl'] = final.units
        files['package_reconstruction.jsonl'] = final.package_reconstruction
    if observed != list(units):
        raise IncompleteCampaign('derived unit order differs from structural order')
    admissions = []
    for index, row in enumerate(records):
        control = controls[index] if controls else None
        nondegenerate = None if control is None else control['nondegenerate']
        classification = ('planned_exclusion' if not row['eligibility'] else
            'eligible' if control is None else
            'eligible_nondegenerate' if nondegenerate else 'eligible_spectrally_empty')
        admissions.append({
            'unit_id':row['unit_id'], 'kind_cell_id':row['kind_cell_id'],
            'eligibility':row['eligibility'], 'classification':classification,
            'exclusion_reason_code':row['exclusion_reason_code'],
            'nondegenerate':nondegenerate, 'tie_flag':row['tie_flag'],
            'pass_boolean_for_each_residual':row['pass_boolean_for_each_residual'],
            'pass_boolean_for_each_control':None if control is None else control['pass_boolean_for_each_control']})
    files['admission.jsonl'] = canonical_jsonl_bytes(admissions)
    return BuiltInvocation(structural, files, {'status':'completed',
        'unit_rows':len(records), 'paired_contexts':len(structural['units']),
        'eligible_rows':sum(r['eligibility'] for r in records),
        'admission_counts':{label:sum(a['classification']==label for a in admissions)
                            for label in sorted({a['classification'] for a in admissions})}})
