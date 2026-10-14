"""Optional post-construction comparisons; never called by census production."""
from collections import defaultdict
from fractions import Fraction
import json
import hashlib
from pathlib import Path
import struct
import time

from born_ladder.archive import sha, canonical
from born_ladder.independent import check_context
from born_ladder.independent_trine import check as check_trine
from born_ladder.robust_census import embedded_records, scan, render_pairs, integer_record, scan_records
from .census import read, verify_artifacts
from .comparison_storage import storage_field,emission_names,LOCATION_FIELDS

# Binding locations, generated-container hashes and timing are not scientific
# values. Status, error, witness, rational and every bound remain in scope.
BINDING_FIELDS={'wall_seconds','frame_context','frame_context_sha256',
    'six_state_certificate','six_state_certificate_sha256','context_frame_sha256',
    'uniform_proof_binding','uniform_proofs_hash_binding'}


def scientific(value):
    if isinstance(value,dict):
        return {k:scientific(v) for k,v in value.items() if k not in BINDING_FIELDS}
    if isinstance(value,list):return [scientific(v) for v in value]
    return value


class Comparison:
    def __init__(self, *, project_bindings=True):
        self.project_bindings=project_bindings
        self.groups=defaultdict(lambda:{'compared':0,'exact':0,'maximum_absolute_difference':'0','differences':[]})

    def compare(self,group,a,b,path=''):
        if isinstance(a,dict) and isinstance(b,dict):
            skipped={k for k in set(a)|set(b) if self.project_bindings and (storage_field(group,k,path) or k in BINDING_FIELDS)}
            if set(a)-skipped!=set(b)-skipped:
                self.compare(group,sorted(set(a)-skipped),sorted(set(b)-skipped),path+'/keys')
            for key in sorted((set(a)&set(b))-skipped):
                left,right=a[key],b[key]
                if group=='complete_inventory' and key=='required_emission_families' and path.endswith('/source/invocation'):
                    left,right=emission_names(left),emission_names(right)
                self.compare(group,left,right,path+'/'+key)
            return
        if isinstance(a,list) and isinstance(b,list) and len(a)==len(b):
            for i,(x,y) in enumerate(zip(a,b)):self.compare(group,x,y,path+'/'+str(i))
            return
        row=self.groups[group];row['compared']+=1
        equal=type(a)==type(b) and a==b
        if isinstance(a,float) and isinstance(b,float):equal=struct.pack('!d',a)==struct.pack('!d',b)
        if equal:row['exact']+=1;return
        difference=None
        try:
            if not isinstance(a,bool) and not isinstance(b,bool):difference=abs(Fraction(a)-Fraction(b))
        except (TypeError,ValueError,ZeroDivisionError):pass
        if difference is not None:
            row['maximum_absolute_difference']=str(max(difference,Fraction(row['maximum_absolute_difference'])))
        row['differences'].append({'field':path,'generated':a,'reference':b,
                                   'absolute_difference':str(difference) if difference is not None else None})

    def result(self):
        return {'field_groups':dict(self.groups),
                'overall_agreement':all(g['compared']==g['exact'] for g in self.groups.values())}


def ordered_identities(rows, label):
    """Reject missing, duplicate or malformed identities before any join."""
    if not isinstance(rows, list) or not rows:
        raise ValueError(label+' must be a nonempty census table')
    if any(not isinstance(row, dict) or not isinstance(row.get('unit_id'), str)
           or not row['unit_id'] for row in rows):
        raise ValueError(label+' has a missing or invalid unit identity')
    ids = [row['unit_id'] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError(label+' has duplicate unit identities')
    return ids


def validate_status_table(rows, expected_ids, label):
    ids = ordered_identities(rows, label)
    if ids != expected_ids:
        raise ValueError(label+' completeness or ordered identities differ from inventory')
    if any(type(row.get('index')) is not int or row['index'] != index
           for index, row in enumerate(rows)):
        raise ValueError(label+' indices differ from inventory order')


def compare_completion_row(comparison, row, completion):
    """Fixed complete row coverage; the path is the sole storage projection."""
    expected={'index':completion['index'],'unit_id':completion['unit_id'],
              'status':completion['overall_registered_claim_status']}
    comparison.compare('completion_table_rows',
        {k:v for k,v in row.items() if k!='context_directory'},expected,row['unit_id'])


def historical_projection(inventory, reference):
    """Align retained identities to archive order; retain new production rows."""
    ids=ordered_identities(reference,'reference inventory')
    ordered_identities(inventory,'generated inventory')
    known=set(ids)
    by_id={row['unit_id']:row for row in inventory}
    historical=[by_id[uid] for uid in ids if uid in by_id]
    new=[row for row in inventory if row['unit_id'] not in known]
    return historical,new


def root_membership(context, roots, c):
    """Check the complete passive-union population before checking endpoints."""
    expected_subsets=set()
    for field in ('raw_by_state','package_by_state','joint_by_state'):
        labels=context['lens'][field];unions={frozenset()}
        for label in sorted(set(labels)):
            block=frozenset(i for i,a in enumerate(labels) if a==label)
            unions|={subset|block for subset in unions}
        expected_subsets.update(tuple(sorted(subset)) for subset in unions)
    expected_subsets=[list(subset) for subset in sorted(expected_subsets,key=lambda a:(len(a),a))]
    well_formed=isinstance(roots,list) and all(isinstance(item,dict)
        and isinstance(item.get('subset'),list)
        and all(type(i) is int and 0<=i<32 for i in item['subset']) for item in roots)
    subsets=sorted((item['subset'] for item in roots),key=lambda a:(len(a),a)) if well_formed else roots
    c.compare('principal_root_subset_membership',subsets,expected_subsets)
    return well_formed and subsets==expected_subsets


def validate_new_case(directory, row, original, *, inventory=None, inputs=None):
    """Independent exact checks, with no historical match counter."""
    from .census_case_validation import locate_inputs, bind_inputs, audit_certificate_fields, typed_trine
    from born_ladder.independent import recompute
    began=time.monotonic()
    c=Comparison(project_bindings=False);directory=Path(directory);uid=row['unit_id']
    inputs=inputs or locate_inputs(directory)
    inventory=inventory or inputs.inventory[uid]
    c.compare('complete_completion_row',
              {k:v for k,v in row.items() if k!='context_directory'},
              {'index':inputs.indices[uid],'unit_id':uid,'status':'PASS'})
    c.compare('completion_storage_location_type',type(row.get('context_directory')) is str,True)
    cert=read(directory/'structural_completion_certificate.json')
    c.compare('completion_row_status',row['status'],cert['overall_status'])
    c.compare('certificate_identity',[cert['unit_id'],cert['index']],[uid,row['index']])
    context=read(directory/'CONTEXT.json')
    source=bind_inputs(c,context,inventory,inputs)
    c.compare('context_identity',context['identity']['unit_id'],uid)
    # Root controls cover all distinct unions in each passive partition,
    # including the empty and full subsets. The endpoint checker alone would
    # accept an empty or truncated population, so check membership first.
    roots=read(directory/'instrument_root_controls.json')
    complete_roots=root_membership(context,roots,c)
    recomputed=recompute(context) if complete_roots else None
    check=check_context(directory,'structural_completion_certificate.json',recomputed=recomputed) if complete_roots else {
        'status':'FAILED','reason':'principal-root subset population incomplete or invalid; endpoints not checked'}
    trine_document=read(directory/'six_state_exact_completion.json')
    c.compare('complete_typed_six_state_fields',trine_document,typed_trine(Fraction(context['exact']['s'])))
    typed=c.groups['complete_typed_six_state_fields']
    trine=check_trine(trine_document) if typed['compared']==typed['exact'] else {
        'status':'FAILED','reason':'complete typed six-state expectations differ; no coercing algebra check attempted'}
    c.compare('independent_exact_checks',[check['status'],trine['status']],['PASS','PASS'])
    frame=integer_record(context['exact']['w'],[context['lens'][k] for k in
                       ('raw_by_state','package_by_state','joint_by_state')])
    c.compare('exact_integer_frame',read(directory/'integer_frame.json'),frame)
    robust=scan_records([frame],require_bound=False)
    robust['cases'][0]['case']=row['index']
    robust['minimum_cases']=[row['index']]
    c.compare('maximal_gap_rule_and_certificate',read(directory/'maximal_gap_witness.json'),robust)
    # Independently verify each atom effect and determinant from the frame.
    cp=cert['certificates']['C_premises'];w=list(map(Fraction,context['exact']['w']));s=Fraction(context['exact']['s'])
    atoms=[]
    for field in ('raw_by_state','package_by_state','joint_by_state'):
        for label in sorted(set(context['lens'][field])):
            states=[i for i,a in enumerate(context['lens'][field]) if a==label]
            a=sum((w[i] for i in states),Fraction(0));b=sum((w[i]**2 for i in states),Fraction(0))
            det=len(states)*b-a*a
            atoms.append({'context':field,'atom':label,'states':states,
                'effect_exact':[[str(Fraction(len(states),32)),str(a/32)],[str(a/s),str(b/s)]],
                'Gram_det_exact':str(det),'positive':det>0})
    c.compare('atom_classification',cp['atom_certificates'],atoms)
    c.compare('atom_counts',[cp[k] for k in ('atom_count','strict_positive_atom_count','zero_atom_count','negative_atom_count')],
              [len(atoms),sum(a['positive'] for a in atoms),sum(Fraction(a['Gram_det_exact'])==0 for a in atoms),sum(Fraction(a['Gram_det_exact'])<0 for a in atoms)])
    from .census_writers.certificates import registered_correspondence
    # Completion requires the scientific gates, even when both the table and
    # overall disposition have been changed together. Robust 3/20 shortfalls
    # are separately recorded by the exact scan above and do not gate this.
    expected_statuses={name:check['status'] for name in
        ('kernel','carrier','strictness','factorization_controls','diagnostics')}
    expected_statuses['correspondence']='PASS' if registered_correspondence(cert['certificates']['correspondence']) else 'FAILED'
    expected_statuses['C_premises']='PASS' if check['status']==trine['status']=='PASS' and all(
        Fraction(a['Gram_det_exact'])>=0 for a in atoms) else 'FAILED'
    c.compare('scientific_certificate_statuses',
              {name:value.get('status') for name,value in cert['certificates'].items()},expected_statuses)
    completion='PASS' if all(status=='PASS' for status in expected_statuses.values()) else 'FAILED'
    c.compare('recomputed_completion_disposition',
              [row.get('status'),cert.get('overall_status'),cert.get('failures')],[completion,completion,[]])
    coverage={'unchecked_scientific_fields':['complete certificate audit blocked by incomplete root population']}
    if complete_roots:
        coverage=audit_certificate_fields(c,directory,row,cert,context,source,recomputed,atoms,
                                        roots,trine_document,inputs,original)
    return {'unit_id':uid,'generated_index':row['index'],'context_directory':str(directory),
            'completion_status':row['status'],'original_implementation':original,
            'disposition':'NEW_RESULT_NO_ARCHIVED_COUNTERPART',
            'historical_matches':0,'independent_validation':c.result(),
            'checks':{'context':check,'trine':trine},'validation_coverage':coverage,
            'validation_wall_seconds':time.monotonic()-began,
            'scope':'new certificates independently checked; no claim of historical reproduction'}


def compare_census(generated,reference,*,lean_root=None,comparison=None):
    generated,reference=Path(generated),Path(reference)
    project=(lambda value:value) if comparison is not None else scientific
    seal=read(generated/'complete.json');verify_artifacts(generated,seal['artifacts'])
    summary=seal['summary'];inv_root=generated/summary['inventory_directory']
    inventory=read(inv_root/'INVENTORY.json');expected=read(reference/'INVENTORY.json')
    inventory_ids=ordered_identities(inventory, 'generated inventory')
    expected_ids=ordered_identities(expected, 'reference inventory')
    comparison=Comparison() if comparison is None else comparison
    historical,new_inventory=historical_projection(inventory,expected)
    comparison.compare('membership_and_order',[r['unit_id'] for r in historical],expected_ids)
    expected_by_id={row['unit_id']:row for row in expected}
    for row in historical:
        comparison.compare('complete_inventory',row,expected_by_id[row['unit_id']],row['unit_id'])
    completed=read(generated/summary['summary_directory']/'structural_completion_results.json')
    originals=read(generated/summary['summary_directory']/'original_implementation_results.json')
    expected_originals=read(reference/'structural_results.json')
    validate_status_table(completed, inventory_ids, 'completion table')
    validate_status_table(originals, inventory_ids, 'original implementation table')
    validate_status_table(expected_originals, expected_ids, 'reference original table')
    by_id={r['unit_id']:r for r in completed}
    original_by_id={r['unit_id']:r for r in originals}
    historical_indices={uid:i for i,uid in enumerate(expected_ids)}
    position_map=[{'unit_id':row['unit_id'],'generated_index':inventory_ids.index(row['unit_id']),
                   'historical_index':historical_indices[row['unit_id']]} for row in historical]
    # Universal premise fields are retained in every successful original
    # certificate. Use that independent schema for originally aborted cases;
    # frame-dependent atoms/counts below come from the archived frame/completion.
    template=next((r['certificates']['C_premises'] for r in expected_originals
                   if r['certificates']['C_premises']['status']=='PASS'),None)
    if template is None:raise ValueError('reference has no complete premise schema')
    independent=[];integer_frames=[];robust_rows=[];unavailable=[];unpaired_roots=[]
    for row in historical:
        uid=row['unit_id'];historic_index=historical_indices[uid]
        original={**original_by_id[uid],'index':historic_index}
        directory=generated/by_id[uid]['context_directory'];old=reference/'contexts'/uid
        certificate=read(directory/'structural_completion_certificate.json')
        archived=read(old/'certificates.json')
        # These hashes bind different serialized provenance envelopes. Audit
        # each against its own inventory rather than claiming cross-container
        # equality or ignoring the computed digest's integrity.
        comparison.compare('certificate_provenance_digest_integrity',
            [certificate.get('key_sha256'),archived.get('key_sha256')],
            [hashlib.sha256(canonical(row['provenance_key'])).hexdigest(),
             hashlib.sha256(canonical(expected_by_id[uid]['provenance_key'])).hexdigest()],uid)
        completion=read(old/'structural_completion.json')
        comparison.compare('certificate_cohort_index',certificate['index'],by_id[uid]['index'],uid)
        certificate={**certificate,'index':historic_index}
        compare_completion_row(comparison,{**by_id[uid],'index':historic_index},completion)
        old_cp=archived['certificates']['C_premises']
        original_expected={'index':completion['index'],'unit_id':uid,'status':archived['overall_status'],
            'correspondence_status':archived['certificates']['correspondence']['status'],
            'C_premises':{k:old_cp[k] for k in ('status','error_type','error') if k in old_cp},
            'classification':'extra SVD-coordinate requirement' if archived['certificates']['correspondence']['status']=='FAILED' else
                'symbolic implementation failure' if old_cp['status']!='PASS' else 'completed original implementation',
            'origin':'re-executed original implementation checks on explicit construction inputs; not copied historical verdicts'}
        comparison.compare('complete_original_status_rows',original,original_expected,uid)
        comparison.compare('complete_certificate_top_fields',
            {k:v for k,v in certificate.items() if k!='certificates'},
            {**{k:v for k,v in archived.items() if k!='certificates'},
             'overall_status':completion['overall_registered_claim_status'],'failures':[]},uid)
        comparison.compare('certificate_groups',sorted(certificate['certificates']),sorted(archived['certificates']),uid)
        comparison.compare('exact_context',read(directory/'CONTEXT.json'),read(old/'CONTEXT.json'),uid)
        for name in ('kernel','carrier','strictness','factorization_controls','diagnostics'):
            comparison.compare(name,project(certificate['certificates'][name]),project(archived['certificates'][name]),uid)
        old_numeric={**archived['certificates']['correspondence'],'status':completion['registered_numerical_gate_status']}
        comparison.compare('numerical_certificate_ranges_and_fields',project(certificate['certificates']['correspondence']),project(old_numeric),uid)
        comparison.compare('original_implementation_statuses',
            [original['status'],original['correspondence_status'],original['C_premises']['status']],
            [archived['overall_status'],archived['certificates']['correspondence']['status'],archived['certificates']['C_premises']['status']],uid)
        if original['C_premises']['status']!='PASS':
            comparison.compare('original_symbolic_errors',
                {k:original['C_premises'][k] for k in ('error_type','error')},
                {k:archived['certificates']['C_premises'][k] for k in ('error_type','error')},uid)
        cp=certificate['certificates']['C_premises']
        # Validate scientific schemas before indexing any required nested
        # field. Otherwise a removed field would raise KeyError before it was
        # recorded as a scientific failure by the full-comparison wrapper.
        comparison.compare('complete_premise_schema',sorted(scientific(cp)),sorted(scientific(template)),uid)
        if archived['certificates']['C_premises']['status']=='PASS':
            comparison.compare('original_successful_premise_fields',project(cp),project(archived['certificates']['C_premises']),uid)
        for index,atom in enumerate(cp.get('atom_certificates',[])):
            comparison.compare('complete_atom_schema',sorted(atom),
                ['Gram_det_exact','atom','context','effect_exact','positive','states'],uid+'/'+str(index))
        comparison.compare('completion_status_and_atom_counts',
            [certificate['overall_status'],cp['status']]+[cp[k] for k in ('atom_count','strict_positive_atom_count','zero_atom_count','negative_atom_count')],
            [completion['overall_registered_claim_status'],completion['C_premise_status']]+[completion[k] for k in ('atom_count','strict_positive_atom_count','zero_atom_count','negative_atom_count')],uid)
        comparison.compare('completed_atom_classification',
            [{k:a[k] for k in ('context','atom','Gram_det_exact','positive')} for a in cp['atom_certificates']],completion['atoms'],uid)
        old_context=read(old/'CONTEXT.json');w=list(map(Fraction,old_context['exact']['w']));s=Fraction(old_context['exact']['s'])
        expected_atoms=[]
        # The failed original symbolic checks did not write effect/root files.
        # Effects can nevertheless be checked independently from their archived
        # frame/subset definition; label that reference honestly.
        for atom in cp['atom_certificates']:
            indices=[i for i,label in enumerate(old_context['lens'][atom['context']]) if label==atom['atom']]
            a=sum((w[i] for i in indices),Fraction(0));b=sum((w[i]**2 for i in indices),Fraction(0))
            effect=[[str(Fraction(len(indices),32)),str(a/32)],[str(a/s),str(b/s)]]
            determinant=len(indices)*b-a*a
            expected_atoms.append({'context':atom['context'],'atom':atom['atom'],'states':indices,
                'effect_exact':effect,'Gram_det_exact':str(determinant),'positive':determinant>0})
            comparison.compare('atom_effects_independently_from_archived_frame',
                [atom['states'],atom['effect_exact']],[indices,effect],uid+'/'+atom['context']+'/'+str(atom['atom']))
        if archived['certificates']['C_premises']['status']!='PASS':
            expected_cp={**template,'status':completion['C_premise_status'],'atom_certificates':expected_atoms,
                **{k:completion[k] for k in ('atom_count','strict_positive_atom_count','zero_atom_count','negative_atom_count')},
                'invertible_atom_no_sharp_grouping_corollary':'PASS' if all(a['positive'] for a in expected_atoms) else
                    'UNPROVED, strict positivity premise missing; full-domain C unaffected'}
            comparison.compare('complete_aborted_original_premise_fields',project(cp),project(expected_cp),uid)
        for file,group in [('six_state_exact_completion.json','exact_quadratic_ring_completion'),
                           ('instrument_root_controls.json','principal_root_intervals'),
                           ('landed_own_input_prediction.json','own_input_prediction')]:
            if not (directory/file).is_file():
                raise ValueError('missing required regenerated certificate: '+str(directory/file))
            if not (old/file).exists():
                if file=='instrument_root_controls.json':
                    root_audit=Comparison(project_bindings=False)
                    context=read(directory/'CONTEXT.json');roots=read(directory/file)
                    complete_roots=root_membership(context,roots,root_audit)
                    if complete_roots:
                        from born_ladder.independent import verify_root_certificate
                        from .census_case_validation import principal
                        w=list(map(Fraction,context['exact']['w']));s=Fraction(context['exact']['s'])
                        for record in roots:
                            root_audit.compare('principal_root_record_schema',sorted(record),['root_certificate','subset'])
                            S=record['subset'];a=sum((w[i] for i in S),Fraction(0));b=sum(w[i]**2 for i in S)
                            effect=[[Fraction(len(S),32),a/32],[a/s,b/s]]
                            verify_root_certificate(effect,record['root_certificate'])
                            _,expected_root=principal(effect)
                            root_audit.compare('complete_principal_root_fields',record['root_certificate'],expected_root,str(S))
                    unpaired_roots.append({'unit_id':uid,'generated_index':by_id[uid]['index'],'historical_index':historic_index,
                        'file':file,'disposition':'INDEPENDENTLY_VALIDATED_NO_ARCHIVED_COUNTERPART',
                        'historical_matches':0,'independent_validation':root_audit.result(),
                        'scope':'complete subset membership and principal endpoints checked; no historical endpoint match claimed'})
                    continue
                unavailable.append({'unit_id':uid,'file':file,
                    'disposition':'NO_ARCHIVED_COUNTERPART',
                    'generated_output_present':(directory/file).is_file(),
                    'paper_value_dependency':{'status':'ASSESS_IN_PAPER_STAGE',
                        'reason':'global report checks selected ledger sources and explicit bindings for a direct dependency on this absent file',
                        'scope':'root validity supports instrument premises; generated endpoints independently checked, historical endpoint reproduction remains unclaimed'},
                    'reason':'original symbolic step aborted before writing this file; completion recorded a finite root-sum status but no serialized root intervals',
                    'new_certificate':'independently verified from exact archived frame, without a stored-interval equality claim'})
                continue
            comparison.compare(group,read(directory/file),read(old/file),uid)
        symbolic=old/'six_state_certificate.json'
        # Original symbolic certificate spelling follows its literal certificate path.
        if archived['certificates']['C_premises']['status']=='PASS':
            name=Path(archived['certificates']['C_premises']['six_state_certificate']).name
            symbolic=old/name
            comparison.compare('original_symbolic_witness',read(directory/'six_state_symbolic_original.json'),read(symbolic),uid)
        check={'context':uid,**check_context(directory,'structural_completion_certificate.json'),
               'trine':check_trine(read(directory/'six_state_exact_completion.json'))}
        comparison.compare('independent_exact_check_statuses',[check['status'],check['trine']['status']],['PASS','PASS'],uid)
        independent.append(check)
        integer_frames.append(read(directory/'integer_frame.json'))
        rows=read(directory/'maximal_gap_witness.json')['cases']
        comparison.compare('maximal_gap_cohort_index',[r['case'] for r in rows],[by_id[uid]['index']],uid)
        robust_rows.extend({**r,'case':historic_index} for r in rows)
    from .census_case_validation import RetainedInputs
    validation_began=time.monotonic();inputs=RetainedInputs(generated) if new_inventory else None
    new_results=[]
    for row in new_inventory:
        uid=row['unit_id']
        try:
            result=validate_new_case(generated/by_id[uid]['context_directory'],by_id[uid],original_by_id[uid],inventory=row,inputs=inputs)
        except (ValueError,KeyError,FileNotFoundError,AssertionError,ArithmeticError,TypeError,IndexError) as error:
            result={'unit_id':uid,'disposition':'NEW_RESULT_NO_ARCHIVED_COUNTERPART',
                'historical_matches':0,'independent_validation':{'overall_agreement':False,'reason':str(error)},
                'validation_coverage':{'unchecked_scientific_fields':['audit aborted: '+str(error)]},
                'scope':'new-case validation incomplete or failed; no historical match claimed'}
        new_results.append(result)
        if len(new_results)%100==0:print('independently validated added census cases',len(new_results),'of',len(new_inventory),flush=True)
    validation_seconds=time.monotonic()-validation_began
    if lean_root:
        embedded=embedded_records(lean_root)
        comparison.compare('all_embedded_integer_frame_fields',integer_frames,embedded)
        robust=scan(lean_root)
        comparison.compare('maximal_gap_pairs_and_exact_gaps',robust_rows,robust['cases'])
        pairs=(Path(lean_root)/'BornCalculus/CensusRobustInputs.lean').read_text()
        comparison.compare('maximal_gap_lean_pair_table',render_pairs(robust_rows),pairs)
    result=comparison.result()
    historical_agreement=result['overall_agreement']
    new_agreement=all(r['independent_validation']['overall_agreement'] for r in new_results)
    unpaired_agreement=all(r['independent_validation']['overall_agreement'] for r in unpaired_roots)
    result['overall_agreement']=historical_agreement and new_agreement and unpaired_agreement
    result.update({'historical_compared_fields_agreement':historical_agreement,'contexts':len(inventory),'generated_seal_sha256':sha(generated/'complete.json'),
                   'reference_inventory_sha256':sha(reference/'INVENTORY.json'),
                   'independent_contexts':independent,'excluded_binding_fields':sorted(BINDING_FIELDS|LOCATION_FIELDS),
                   'unavailable_stored_reference_files':unavailable,
                   'historical_outputs_without_archived_counterpart':unpaired_roots,
                   'independent_historical_output_validation_agreement':unpaired_agreement,
                   'historical_contexts_compared':len(historical),
                   'historical_required_contexts':len(expected),
                   'cohort_position_projection':position_map,
                   'new_results_without_archived_counterpart':new_results,
                   'new_contexts':len(new_results),'new_historical_matches':0,
                   'new_case_validation_agreement':new_agreement,
                   'added_case_validation_wall_seconds':validation_seconds,
                   'reference_opened_only_after_generated_seal':True})
    return result
