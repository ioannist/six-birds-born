"""CB2 structural reconstruction from explicit prior-stage data.

Selection keys name logical input identities; actual storage locations are a
separate checked mapping. No review/launch receipt or ledger is opened.
"""
import collections,json,time
from pathlib import Path
from .cb2_parser import *


def rebuild_inventory(*, archive_root, campaign_path, invocation_path,
                      unit_logical_path, output_dir, historical_inputs=False,
                      absolute_source_prefix=None, input_files=None,
                      kernel_sources=None):
    archive_root=Path(archive_root).resolve(strict=True)
    output_dir=Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=False)
    def rel(name):
        p=Path(name)
        if p.is_absolute():
            prefix=Path(absolute_source_prefix) if absolute_source_prefix else archive_root
            p=p.relative_to(prefix)
        if '..' in p.parts:
            raise ValueError('logical path escapes input root')
        return str(p)
    def actual(name):
        name=rel(name)
        p=Path(input_files[name]) if input_files is not None else archive_root/name
        # A caller-supplied archive may use storage symlinks; logical identities
        # remain the verified file bytes, not assertions of a new execution.
        return p
    def out(name,value):
        if Path(name).name!=name:raise ValueError('output must be a basename')
        with (output_dir/name).open('x') as f:
            json.dump(value,f,sort_keys=True,indent=2);f.write('\n')
    verified={}
    def verify(name,digest):
        name=rel(name)
        if name not in verified:
            if sha(actual(name))!=digest:raise ValueError('input hash differs: '+name)
            verified[name]=digest
        elif verified[name]!=digest:raise ValueError('conflicting input commitment')
        return name
    c=json.loads(Path(campaign_path).read_bytes())
    inv=json.loads(Path(invocation_path).read_bytes())
    inv={row['invocation_id']:row for row in inv}
    sp=verify(c['structural_manifest']['path'],c['structural_manifest']['sha256'])
    structural={}
    with actual(sp).open() as stream:
        for line in stream:
            row=json.loads(line)
            for u in row['units']:
                structural[(row['invocation_id'],u['runner_context_id'])]={**u,'row_sha256_with_LF':digest_bytes(line.encode())}
    # Units are scientific producer output, not the old pre-run/review register.
    unit_logical_path=rel(unit_logical_path)
    verified[unit_logical_path]=sha(actual(unit_logical_path))
    t=time.monotonic()
    source={}; exponent_counts=collections.Counter();source_records=[];kernel_fields_found=[]
    for bn,b in enumerate(c['stdout_execution_bindings']):
        p=verify(b['stdout_path'],b['stdout_sha256'])
        attempt_path = str(Path(p).parent/(b['attempt_record_sha256']+'.attempt.json'))
        verify(attempt_path,b['attempt_record_sha256']); assert b['invocation_id'] in attempt_path
        iv=inv[b['invocation_id']];pending=[];seq={}; offset=0
        with actual(p).open('rb') as f:
            for ln,raw in enumerate(f,1):
                if b' ' not in raw:offset+=len(raw);continue
                tag,payload=raw.split(b' ',1);s=payload.decode().strip(); ptr={'path':p,'file_sha256':b['stdout_sha256'],'line':ln,'byte_offset':offset,'payload_sha256':digest_bytes(payload.rstrip(b'\n'))}
                if tag==b'KEY_BORN_PROBE_JSON':
                    y=metadata(s,BORN_KEYS);pending.append((y,ptr,refs(s,BORN_KEYS)));assert y['seed']==iv['seed'] and y['scale']==iv['scale']
                elif tag==b'KEY_SEQUENTIAL_PROBE_JSON':
                    y=metadata(s,SEQ_KEYS);ex=y['tau']-y['t_mid'];exponent_counts[ex]+=1
                    rr=refs(s,{'propagator_mid_to_final'}); pr={**ptr,**rr['propagator_mid_to_final'],'exponent':ex,'source_semantics':'native evolve(point, tau-t_mid) per row'}
                    if ex==1:
                        a=metadata(s,{'propagator_mid_to_final'})['propagator_mid_to_final'];assert len(a)==iv['scale'] and all(len(row)==iv['scale'] for row in a)
                        pr['matrix_shape']=[iv['scale'],iv['scale']]
                    seq[(y['cell'],y['step_index'],y['k'])]=pr
                elif tag==b'KEY_AUDIT_JSON':
                    au=metadata(s,AUDIT_KEYS); ar=refs(s,KERNEL_KEYS)
                    for field,r in ar.items():kernel_fields_found.append({**ptr,'field':field,**r})
                    for y,bptr,br in pending:
                        key=(b['invocation_id'],y['cell'],y['step_index'],y['k']);assert key not in source
                        assert au['seed']==y['seed'] and au['n']==y['scale']
                        assert au.get('config_name')==y['cell'],(au,y['cell'])
                        pr=seq.get((y['cell'],y['step_index'],y['k']))
                        kernel={'status':'AVAILABLE','artifact':pr,'operation':'K','availability_reason':'existing one-step native propagator bytes'} if pr and pr['exponent']==1 else {'status':'MISSING','reason':'no actual K artifact in immutable joined capture; higher powers cannot supply K','existing_propagator':pr}
                        if ar:
                            assert len(ar)==1; field,fr=next(iter(ar.items()));kernel={'status':'AVAILABLE','operation':'K','artifact':{**ptr,'field':field,**fr}}
                        if kernel['status']=='MISSING' and kernel_sources is not None:
                            capture=kernel_sources.get((b['invocation_id'],y['cell']))
                            if capture is not None:
                                verify(capture['path'],capture['file_sha256'])
                                kernel={'status':'AVAILABLE','operation':'K','artifact':capture,
                                        'availability_reason':'P2a full final-matrix capture at exponent one'}
                        # Structural lens labels and source-mode values are preparation/apparatus data only.
                        q=sorted(set(zip(y['partition'],y['packaging']))); labels=[q.index(pair) for pair in zip(y['partition'],y['packaging'])]
                        sr={'born':bptr,'source_span':{'constant_column':'all ones on ordered micro support','spectral_mode_count':len(y['sym_eigvec_basis']),'mode_shapes':[len(v) for v in y['sym_eigvec_basis']],'mode_input':br['sym_eigvec_basis']},'lenses':{'raw_map':y['partition'],'package_map':y['packaging'],'joint_atoms':[list(v) for v in q],'joint_map':labels,'input_refs':{k:br[k] for k in ['partition','packaging']}},'preparation':{'starts':y['starts'],'tau':y['tau'],'exact_preparation_coefficients':'unrounded_p_full in paired unit, input field hash bound there'},'audit':{'metadata':au,'artifact':ptr},'kernel':kernel,'attempt_path':attempt_path,'attempt_record_sha256':b['attempt_record_sha256'],'invocation':iv}
                        source[key]=sr
                    pending=[];seq={}
                offset+=len(raw)
        assert not pending
        if bn%200==0:print('source captures',bn+1,flush=True)
    out('source_metadata_cache.json',[{'join_key':list(k),'source':v} for k,v in source.items()])
    up=Path(unit_logical_path);pairs={};unit_lines=0;offset=0
    for ln,raw in enumerate(actual(str(up)).open('rb'),1):
        s=raw.decode().strip();u=metadata(s,UNIT_KEYS);uid=u['unit_id'];st=structural[(u['invocation_id'],u['context'])];key=(u['invocation_id'],st['config_id'],u['step'],u['resolution']);src=source[key]
        assert st['partition_id']==u['partition'] and st['resolution']==u['resolution'];assert src['attempt_record_sha256']==u['attempt_record_sha256'];assert u['structural_manifest_sha256']==st['row_sha256_with_LF']
        br=u['basis_and_projector_inputs']; rank=br['effective_rank'] if br is not None else None
        n=len(u['ordered_state_labels'] if u['ordered_state_labels'] is not None else st['ordered_state_labels']);assert n==u['scale']==src['invocation']['scale']
        fields=refs(s,UNIT_KEYS|{'unrounded_p_full'})
        kinds=[k for k in ['raw','pkg'] if digest_bytes((uid+k).encode())==u['kind_cell_id']];assert len(kinds)==1
        pointer={'kind':kinds[0],'path':str(up),'file_sha256':verified[str(up)],'line':ln,'byte_offset':offset,'line_sha256':digest_bytes(raw.rstrip(b'\n')),'kind_cell_id':u['kind_cell_id'],'fields':fields}
        # Compare actual raw/package source incidence, including empty rows where unit builder omitted matrices.
        if u['M_raw_or_content_hash'] is not None:
            for field,mapkey,prefix in [('M_raw_or_content_hash','raw_map','group_'),('M_pkg_or_content_hash','package_map','package_')]:
                expected=[[float(prefix+str(v)==ol) for v in src['lenses'][mapkey]] for ol in u['ordered_union_outcome_labels']]
                assert u[field]==expected,(uid,field)
        if uid in pairs:
            row=pairs[uid];assert len(row['kind_records'])==1;assert row['retained_rank']==rank
            assert row['provenance_key']['context']==u['context']; row['kind_records'].append(pointer)
        else:
            pk={k:u[k] for k in ['unit_id','invocation_id','source','experiment','config_or_null','seed','scale','resolution','context','partition','step','structural_manifest_sha256','attempt_record_sha256','ordered_state_labels','ordered_union_outcome_labels','raw_pkg_pairing_key']}
            pk.update({'actual_source_cell':st['config_id'],'stdout_sha256':src['born']['file_sha256'],'born_line':src['born']['line'],'audit_metadata':src['audit']['metadata'],'source_span_input':src['source_span'],'lens_inputs':src['lenses']['input_refs'],'kernel':src['kernel'],'basis_projector_field_sha256':fields['basis_and_projector_inputs']['field_sha256'],'preparation_input_sha256':fields['unrounded_p_full']['field_sha256'],'preparation':src['preparation']})
            pairs[uid]={'unit_id':uid,'n':n,'retained_rank':rank,'original_columns':br['n_cols_original'] if br else None,'source_span_available':src['source_span']['spectral_mode_count']>=1 and all(v==n for v in src['source_span']['mode_shapes']),'source':src,'lenses':src['lenses'],'kernel':src['kernel'],'basis_projector_inputs':{'artifact':fields['basis_and_projector_inputs'],'interpretation':'retained rank and original column count from landed construction; no gate outcomes'},'provenance_key':pk,'immutable_join_verified':True,'kind_records':[pointer]}
        offset+=len(raw);unit_lines+=1
        if ln%4000==0:print('unit structural rows',ln,flush=True)
    rows=list(pairs.values());assert all(len(r['kind_records'])==2 for r in rows);assert len(rows)==len(structural)
    counts=collections.Counter(r['kernel']['status'] for r in rows);ranks=collections.Counter(str(r['retained_rank']) for r in rows)
    result={'schema':'CB2_metadata_inventory_v1','units_path':str(up),'unit_rows':unit_lines,'paired_unit_contexts':len(rows),'invocations':len(inv),'rank_counts':dict(ranks),'kernel_availability':dict(counts),'propagator_exponent_counts':dict(sorted(exponent_counts.items())),'source_search_scope':'all supplied committed captures; structural Born/Sequential/Audit joins only','performance_fields_decoded_for_inventory':[],'historical_results_already_opened':False,'retained_capture_inputs':historical_inputs,'source_files':verified,'rows':rows}

    out('RETURN_CARRIER_INVENTORY.json',result)
    ordered=sorted((r for r in rows if r['n']==32 and r['retained_rank']==2
                    and r['source_span_available'] and r['kernel']['status']=='AVAILABLE'
                    and r['immutable_join_verified']),
                   key=lambda r:(digest_bytes(canonical(r['provenance_key'])),r['unit_id']))
    out('INVENTORY.json',ordered)
    if not historical_inputs and len(ordered)!=ranks.get('2',0):
        raise ValueError('rank-two cohort incomplete: missing matrix, source span, dimension or immutable join')
    correspondence=[]
    for name,digest in sorted(verified.items()):
        correspondence.append({'logical_path':name,'actual_location':str(actual(name).resolve()),
                               'sha256':digest,'origin':'retained input' if historical_inputs else 'new execution'})
    out('INPUT_CORRESPONDENCE.json',correspondence)
    return {'paired_contexts':len(rows),'rank_counts':dict(ranks),'selected_count':len(ordered),
            'ordered_key_sha256':digest_bytes(canonical([r['provenance_key'] for r in ordered])),
            'wall_seconds':time.monotonic()-t}
