"""Identity joins and independent audits for the amended attachment cohort.

Historical comparisons use the shared population only. Full-population
summaries and additional records are audited without claiming archive matches.
"""
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

from born_ladder.archive import canonical, sha
from born_ladder.independent import independent_type7
from born_ladder import metadata
from .census_comparison import Comparison, read, ordered_identities, validate_status_table


def attachment_identity(row):
    uid,view=row.get('unit_id'),row.get('view')
    if not isinstance(uid,str) or not uid or view not in ('raw','pkg'):
        raise ValueError('attachment has missing/invalid unit identity or view')
    return uid,view


def attachment_index(rows, ids, label):
    result={}
    for row in rows:
        key=attachment_identity(row)
        if key in result:raise ValueError(label+' duplicate attachment '+str(key))
        result[key]=row
    expected={(uid,view) for uid in ids for view in ('raw','pkg')}
    if set(result)!=expected:
        raise ValueError(label+' attachment membership incomplete: missing '+str(sorted(expected-set(result)))+
                         '; extra '+str(sorted(set(result)-expected)))
    return result


def audit_summaries(rows, contexts):
    """Reconstruct the fixed descriptive contract using the independent type-7 routine.

    Audit denominators, every eligibility reason/identity, all three finite
    populations, exact quantiles and displays. Never rescore an observation.
    """
    models={'q_full','q_diag','L_clipped_linear','L_uniform','L_full'}
    contrasts=set()
    for row in rows:
        fields=row.get('fields',{})
        for metric in ('brier_score','dtv_loss'):
            value=fields.get(metric,{})
            if isinstance(value,dict):models.update(value)
        value=fields.get('pairwise_contrast',{})
        if isinstance(value,dict):contrasts.update(k for k in value if 'q_diag' in k and 'q_full' in k)
    def quantiles(values):
        exact=independent_type7([float(v) for v in values])
        return {'n':len(values),'exact':exact,
                'display':{k:float(Fraction(v)) for k,v in exact.items()} if exact else None}
    summaries=[]
    for view in ('raw','pkg'):
        selected=[r for r in rows if r['view']==view]
        if len(selected)!=contexts:raise ValueError('summary population does not cover every context')
        for metric,model in ([(m,k) for m in ('brier_score','dtv_loss') for k in sorted(models)]+
                             [('pairwise_contrast',k) for k in sorted(contrasts)]):
            included=[];excluded_values=[];allfinite=[]
            missing=Counter();excluded=Counter();missing_ids=[];excluded_ids=[]
            for row in selected:
                fields=row.get('fields',{});eligible=fields.get('eligibility')
                if eligible is False:
                    excluded[str(fields.get('exclusion_reason_code'))]+=1;excluded_ids.append(row['unit_id'])
                table=fields.get(metric,{})
                value=table.get(model) if isinstance(table,dict) else None
                if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value):
                    reason=('INTEGRITY FAILURE' if row['status']=='INTEGRITY FAILURE' else
                            'MISSING ROW' if not fields else 'ABSENT/NULL/NONFINITE METRIC')
                    missing[reason]+=1;missing_ids.append(row['unit_id']);continue
                allfinite.append(value)
                if eligible is True:included.append(value)
                elif eligible is False:excluded_values.append(value)
                else:missing['ELIGIBILITY MISSING/NULL']+=1;missing_ids.append(row['unit_id'])
            summaries.append({'view':view,'metric':metric,'model_or_recorded_contrast':model,
                'scheduled_contexts':contexts,'historically_eligible_finite_denominator':len(included),
                'quantiles':quantiles(included),'missing_count':sum(missing.values()),'missing_reasons':dict(missing),
                'missing_unit_ids':missing_ids,'excluded_count':sum(excluded.values()),'exclusion_reasons':dict(excluded),
                'excluded_unit_ids':excluded_ids,'excluded_finite_denominator':len(excluded_values),
                'excluded_values_quantiles':quantiles(excluded_values),
                'all_available_finite_quantiles_descriptive_only':quantiles(allfinite),'structural_status_filter':False,
                'contrast_definition':'recorded original field, never recomputed from losses' if metric=='pairwise_contrast' else 'original recorded metric'})
    return summaries


def compare_summary_rows(c, group, actual, expected):
    def index(rows):
        result={}
        for row in rows:
            key=tuple(row[k] for k in ('view','metric','model_or_recorded_contrast'))
            if key in result:raise ValueError('duplicate descriptive summary '+str(key))
            result[key]=row
        return result
    a,b=index(actual),index(expected)
    c.compare(group,sorted(a),sorted(b),'summary_membership')
    for key in sorted(set(a)&set(b)):c.compare(group,a[key],b[key],'/'.join(key))


def validate_attachment(row, inventory, completion, original, directory, units_root, hashes):
    """Bind every field to the retained source row and its own census case.

    Storage metadata is ignored in historical matching but verified here:
    relocation cannot conceal an altered source payload or detached attachment.
    """
    c=Comparison();uid,view=attachment_identity(row)
    pointers={p['kind']:p for p in inventory['kind_records']}
    if set(pointers)!={'raw','pkg'}:raise ValueError('invalid census kind population '+uid)
    ptr=pointers[view];relative=Path(ptr['path']);units_root=Path(units_root).resolve()
    source=(units_root/relative).resolve()
    if relative.is_absolute() or '..' in relative.parts or not source.is_relative_to(units_root):
        raise ValueError('attachment source escapes closed unit collection')
    if source not in hashes:hashes[source]=sha(source)
    c.compare('source_file_integrity',hashes[source],ptr['file_sha256'],uid+'/'+view)
    with source.open('rb') as stream:
        stream.seek(ptr['byte_offset']);raw=stream.readline()
    c.compare('source_line_integrity',hashlib.sha256(raw.rstrip(b'\n')).hexdigest(),ptr['line_sha256'],uid+'/'+view)
    body=raw.decode().rstrip('\n');decoded=json.loads(body)
    structural_keys=metadata.UNIT_KEYS|{'unrounded_p_full','spectral_coefficients'}
    fields={k:v for k,v in decoded.items() if k not in structural_keys}
    key=inventory['provenance_key'];refs=metadata.refs(body,structural_keys)
    # Inventory commits UNIT_KEYS and preparation. Spectral coefficients are
    # structural (excluded from performance) but not a separately committed
    # inventory field; the full source line is still checked above.
    committed={k:v for k,v in refs.items() if k!='spectral_coefficients' or k in ptr['fields']}
    c.compare('source_field_commitments',committed,ptr['fields'],uid+'/'+view)
    c.compare('source_identity',decoded['kind_cell_id'],ptr['kind_cell_id'],uid+'/'+view)
    for name in metadata.UNIT_KEYS & set(key):
        c.compare('source_complete_provenance',decoded.get(name),key[name],uid+'/'+view+'/'+name)
    for name,k in [('basis_and_projector_inputs','basis_projector_field_sha256'),('unrounded_p_full','preparation_input_sha256')]:
        c.compare('source_input_commitments',refs[name]['field_sha256'],key[k],uid+'/'+view+'/'+name)
    for link in fields.get('applicable_control_record_links',[]):
        control=(source.parent/link['path']).resolve()
        if not control.is_relative_to(units_root):raise ValueError('control source escapes unit collection')
        if control not in hashes:hashes[control]=sha(control)
        c.compare('control_source_integrity',hashes[control],link['sha256'],uid+'/'+view+'/'+link['path'])
    cert=read(Path(directory)/'structural_completion_certificate.json')
    nondegeneracy={k:v for k,v in fields.items() if any(t in k.lower() for t in ('degener','energy','nonconstant'))}
    expected={'index':completion['index'],'unit_id':uid,'view':view,'source':ptr,'fields':fields,
        'complete_provenance_key':key,'key_sha256':hashlib.sha256(canonical(key)).hexdigest(),
        'original_row_copy_sha256':hashlib.sha256(raw).hexdigest(),'status':'PASS',
        'completion_status':completion['status'],'structural_overall_status':cert['overall_status'],
        'original_implementation_status':original['status'],'diagnostics':cert['certificates']['diagnostics'],
        'nondegeneracy_record':nondegeneracy or {'status':'MISSING','reason':'No explicit nondegeneracy field in original unit; structural diagnostics are separately reported, no new threshold.'}}
    # Deliberately use a nonprojected group: audit the locator/digests even
    # though they are excluded from historical scientific matching.
    c.compare('independent_attachment_source_and_certificate',row,expected,uid+'/'+view)
    c.compare('completion_binding',[cert.get('unit_id'),cert.get('index'),cert['overall_status']],
              [uid,completion['index'],completion['status']],uid)
    c.compare('census_certificate_provenance_digest_integrity',cert.get('key_sha256'),
              hashlib.sha256(canonical(key)).hexdigest(),uid)
    return {'unit_id':uid,'view':view,'generated_index':row['index'],
            'disposition':'NEW_RESULT_NO_ARCHIVED_COUNTERPART','historical_matches':0,
            'independent_validation':c.result()}


def compare_attachments(generated, reference, census, units_root, comparison):
    generated,reference,census=map(Path,(generated,reference,census));c=comparison
    seal=read(census/'complete.json')['summary']
    inventory=read(census/seal['inventory_directory']/'INVENTORY.json')
    ids=ordered_identities(inventory,'generated inventory');inv={r['unit_id']:r for r in inventory}
    old_inventory=read(reference/'INVENTORY.json');old_ids=ordered_identities(old_inventory,'archived inventory')
    completion=read(census/seal['summary_directory']/'structural_completion_results.json')
    original=read(census/seal['summary_directory']/'original_implementation_results.json')
    validate_status_table(completion,ids,'attachment completion table')
    validate_status_table(original,ids,'attachment original table')
    completion={r['unit_id']:r for r in completion};original={r['unit_id']:r for r in original}
    new_rows=read(generated/'attachments.json');old_rows=read(reference/'attachments.json')
    a=attachment_index(new_rows,ids,'generated');b=attachment_index(old_rows,old_ids,'archived')
    c.compare('attachment_historical_membership',[uid for uid in old_ids if uid in inv],old_ids)
    audit=[];additional=[];hashes={};old_id_set=set(old_ids)
    for row in new_rows:
        uid=row['unit_id'];directory=census/completion[uid]['context_directory']
        result=validate_attachment(row,inv[uid],completion[uid],original[uid],directory,units_root,hashes)
        if uid in old_id_set:result['disposition']='INDEPENDENT_VALIDATION_OF_SHARED_RECORD'
        audit.append(result)
        if uid not in old_id_set:additional.append(result)
    shared=[];mapping=[]
    for old_index,uid in enumerate(old_ids):
        if uid not in inv:continue
        archived_cert=read(reference/'contexts'/uid/'certificates.json')
        archived_completion=read(reference/'contexts'/uid/'structural_completion.json')
        actual_index=completion[uid]['index'];mapping.append({'unit_id':uid,'archived_index':old_index,'generated_index':actual_index})
        for view in ('raw','pkg'):
            actual=a[uid,view];old=b[uid,view]
            # The old field meant the original implementation disposition.
            # Verify it before expanding it to the packet's two dispositions.
            c.compare('archived_attachment_status_binding',old['structural_overall_status'],archived_cert['overall_status'],uid+'/'+view)
            c.compare('archived_attachment_index_binding',old['index'],old_index,uid+'/'+view)
            expected={**old,'index':actual_index,
                'original_implementation_status':old['structural_overall_status'],
                'completion_status':archived_completion['overall_registered_claim_status'],
                'structural_overall_status':archived_completion['overall_registered_claim_status']}
            c.compare('performance_attachments',actual,expected,uid+'/'+view)
            shared.append(actual)
    # Missing/excluded identity lists in summaries inherit attachment storage
    # order. Reaggregate the matched population in the reference's row order.
    shared=[a[attachment_identity(row)] for row in old_rows if row['unit_id'] in inv]
    old_summaries=read(reference/'descriptive_summaries.json');new_summaries=read(generated/'descriptive_summaries.json')
    summary_audit=Comparison()
    compare_summary_rows(summary_audit,'generated_population_summary_validation',new_summaries,audit_summaries(new_rows,len(ids)))
    compare_summary_rows(summary_audit,'archived_population_summary_validation',old_summaries,audit_summaries(old_rows,len(old_ids)))
    if len(shared)==len(old_rows):
        # Same records in archive order; no comparison of 2,122-case quantiles
        # to 120-case quantiles. The full new population is audited above.
        compare_summary_rows(c,'exact_descriptive_quantiles_shared_population',audit_summaries(shared,len(old_ids)),old_summaries)
    valid=all(r['independent_validation']['overall_agreement'] for r in audit) and summary_audit.result()['overall_agreement']
    return {'overall_agreement':c.result()['overall_agreement'] and valid,
        'new_case_validation_agreement':valid,'generated_contexts':len(ids),'archived_contexts':len(old_ids),
        'generated_records':len(a),'archived_records':len(b),'historical_records_compared':len(shared),
        'cohort_position_projection':mapping,
        'status_semantics_adapter':'archive structural_overall_status = original_implementation_status; archive structural_completion.overall_registered_claim_status = completion_status and structural_overall_status',
        'all_record_independent_validations':audit,'summary_independent_validation':summary_audit.result(),
        'summary_population_comparison':{'historical_contexts':len(old_ids),'shared_contexts':len(shared)//2,
            'generated_contexts':len(ids),'generated_full_summary_rows':len(new_summaries),
            'full_generated_summaries_have_archived_cohort_counterpart':set(ids)==set(old_ids),
            'comparison':'shared population only; full generated and archive summaries independently audited'},
        'new_results_without_archived_counterpart':additional,'new_results_historical_matches':0}
