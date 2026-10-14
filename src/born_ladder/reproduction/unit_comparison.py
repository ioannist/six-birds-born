"""Post-write, streaming comparison of predictive records; no statistics."""
import hashlib
import json
import math
from pathlib import Path
import struct

GROUPS = {
    'provenance':{'attempt_record_sha256','structural_manifest_sha256','applicable_control_record_links'},
    'eligibility_and_dispositions':{'eligibility','exclusion_reason_code','frozen_inclusion_population',
        'tie_flag','pass_boolean_for_each_residual','nondegenerate','pass_boolean_for_each_control','classification'},
    'identities_labels_and_counts':{'unit_id','kind_cell_id','invocation_id','source','experiment','config_or_null',
        'seed','scale','resolution','context','partition','step','trajectory','integer_counts','total_count',
        'ordered_state_labels','ordered_union_outcome_labels','seed_block_key','fixed_census_config_or_experiment_key',
        'source_key','bootstrap_hierarchy_keys','raw_pkg_pairing_key'},
    'basis_and_preparation':{'unrounded_p_full','basis_and_projector_inputs','spectral_coefficients'},
    'empirical_laws_and_incidence':{'M_raw_or_content_hash','M_pkg_or_content_hash','unrounded_y_raw','unrounded_y_pkg'},
    'predictions_and_normalization':{'law_numerators','normalization_mass','state_space_prediction',
        'mapped_outcome_prediction','normalization_mass_q_full_control'},
    'losses_and_contrasts':{'dtv_loss','brier_score','pairwise_contrast','tie_residuals'},
    'residuals_and_tolerances':{'finite_residuals','mass_residuals','parseval_residuals',
        'rotation_residuals','identity_residuals','sequential_residuals','tolerance_for_each_residual'},
}


def record_index(path):
    offsets,order={},[]
    with Path(path).open('rb') as stream:
        while True:
            offset=stream.tell();raw=stream.readline()
            if not raw:break
            row=json.loads(raw);key=row['kind_cell_id']
            if key in offsets:raise ValueError('duplicate regenerated kind_cell_id')
            offsets[key]=offset;order.append(key)
    return offsets,order


def compare_records(generated, reference, *, comparison=None):
    """Reference is an iterable of closed JSONL bytes, opened after generation.

    Float equality means exact IEEE-754 binary64 bytes, including signed zero.
    Every field is covered; mismatches are never accepted using a tolerance.
    """
    generated=Path(generated)
    offsets,generated_order=record_index(generated)
    groups={};fields={};details={};reference_order=[];seen=set();examples=[]
    def counters(table,key):
        return table.setdefault(key,{'records_compared':0,'scalar_values_compared':0,'scalar_values_exact':0,
            'float_values_compared':0,'float_values_binary64_exact':0,'maximum_absolute_difference':0.0,
            'structure_mismatches':0,'maximum_absolute_difference_at':None})
    def walk(left,right,group,field,path):
        if isinstance(left,dict) and isinstance(right,dict):
            if set(left)!=set(right):
                group['structure_mismatches']+=1;field['structure_mismatches']+=1
            for key in sorted(set(left)&set(right)):walk(left[key],right[key],group,field,path+'.'+key)
            return
        if isinstance(left,list) and isinstance(right,list):
            if len(left)!=len(right):
                group['structure_mismatches']+=1;field['structure_mismatches']+=1
            for index,(a,b) in enumerate(zip(left,right)):walk(a,b,group,field,path+f'[{index}]')
            return
        floating=type(left) is float or type(right) is float
        numeric=type(left) in (int,float) and type(right) in (int,float)
        exact=type(left) is type(right) and left==right
        if floating and numeric:
            if not math.isfinite(left) or not math.isfinite(right):
                raise ValueError('nonfinite comparison input')
            bits=struct.pack('<d',left)==struct.pack('<d',right)
            exact=exact and bits
            difference=abs(left-right)
            for row in (group,field):
                row['float_values_compared']+=1;row['float_values_binary64_exact']+=int(bits)
                if difference>row['maximum_absolute_difference']:
                    row['maximum_absolute_difference']=difference
                    row['maximum_absolute_difference_at']={'kind_cell_id':reference_order[-1],'field':path}
        for row in (group,field):
            row['scalar_values_compared']+=1;row['scalar_values_exact']+=int(exact)
        if not exact and len(examples)<20:
            examples.append({'kind_cell_id':reference_order[-1],'field':path,'regenerated':left,'reference':right})
    missing=[]
    with generated.open('rb') as fresh:
        for raw in reference:
            archived=json.loads(raw);key=archived['kind_cell_id']
            if key in seen:raise ValueError('duplicate reference kind_cell_id')
            seen.add(key);reference_order.append(key)
            if key not in offsets:
                missing.append(key);continue
            fresh.seek(offsets[key]);actual=json.loads(fresh.readline())
            if comparison is not None:
                for label,names in GROUPS.items():
                    comparison.compare(label,{k:v for k,v in actual.items() if k in names},
                                       {k:v for k,v in archived.items() if k in names},key)
                known=set().union(*GROUPS.values())
                comparison.compare('other_fields',{k:v for k,v in actual.items() if k not in known},
                                   {k:v for k,v in archived.items() if k not in known},key)
            for name in sorted(set(actual)|set(archived)):
                label=next((g for g,names in GROUPS.items() if name in names),'other_fields')
                group,field=counters(groups,label),counters(fields,name)
                group['records_compared']+=1;field['records_compared']+=1
                if name not in actual or name not in archived:
                    group['structure_mismatches']+=1;field['structure_mismatches']+=1
                else:
                    walk(actual[name],archived[name],group,field,name)
                    if name in ('dtv_loss','brier_score','basis_and_projector_inputs') and isinstance(actual[name],dict) and isinstance(archived[name],dict):
                        for member in sorted(set(actual[name])&set(archived[name])):
                            detail=counters(details,name+'.'+member)
                            detail['records_compared']+=1
                            scratch=counters({},'scratch')
                            walk(actual[name][member],archived[name][member],scratch,detail,name+'.'+member)
    extra=sorted(set(offsets)-seen)
    scientific = {g:row for g,row in groups.items() if g!='provenance'}
    exact_science=not missing and not extra and all(
        row['scalar_values_compared']==row['scalar_values_exact'] and not row['structure_mismatches']
        for row in scientific.values())
    with generated.open('rb') as stream:
        generated_sha=hashlib.file_digest(stream,'sha256').hexdigest()
    order_exact=reference_order==generated_order
    return {'schema':'born_unit_comparison_v1','generated_sha256':generated_sha,
        'reference_rows':len(reference_order),'generated_rows':len(offsets),'matched_rows':len(seen)-len(missing),
        'missing_rows':missing,'extra_rows':extra,'row_order_exact':order_exact,
        'overall_agreement':exact_science and order_exact,
        'scientific_fields_exact':exact_science,'groups':groups,'fields':fields,'details':details,'first_mismatches':examples,
        'criteria':'exact types and identities; binary64 byte comparison; no tolerance-based acceptance'}
