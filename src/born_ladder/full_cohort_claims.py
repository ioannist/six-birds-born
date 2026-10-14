"""Public full-cohort checks; historical trust anchors remain a separate lane."""
from collections import Counter
from fractions import Fraction as Q
import json
import hashlib
import math
from pathlib import Path
import tempfile
import subprocess

from .archive import Archive, safe_name, sha
from .reproduction.census import read, verify_artifacts
from .reproduction.census_comparison import Comparison, validate_new_case
from .reproduction.census_case_validation import RetainedInputs, bind_inputs, expected_strictness, audit_original, remove_costs

IDS = frozenset(('P03','P10','P11','P13','B08','B09','B10','B13'))
COUNT = 2122


def require_equal(group, actual, expected):
    c=Comparison(project_bindings=False);c.compare(group,actual,expected)
    require_agreement(c,group)


def require_agreement(c, label):
    if not c.result()['overall_agreement']:
        errors=[{'group':k,**d} for k,g in c.groups.items() for d in g['differences']]
        raise ValueError(label+' differs: '+json.dumps(errors[:3],default=str))


class Inputs:
    """A full regenerated bundle or explicit completed census-stage directory.

    Bundle roots are relocatable. Only components used by this claim are
    opened; Test B data is not a dependency of a census verification.
    """
    def __init__(self, data, *, attachments=False):
        path=Path(data).resolve(strict=True);self.bundle=None;self.units=None;self.lean=None
        if path.is_dir() and (path/'bundle.json').is_file():path=path/'bundle.json'
        if path.is_file():
            doc=read(path)
            if doc.get('schema')!='born_regenerated_bundle_v1' or doc.get('profile')!='regenerated':
                raise ValueError('full-cohort claims require a regenerated bundle or census-stage directory; historical 120-case bundles cannot certify them')
            if doc.get('reduced') is not False:raise ValueError('reduced bundle cannot certify the 2,122-case registry')
            if set(doc['roots'])!=set(doc['files']):raise ValueError('bundle component inventories differ')
            roots={k:(path.parent/doc['roots'][k]).resolve(strict=True) for k in
                   ('census','cross_term_units','lean',*(['attachments'] if attachments else []))}
            from .reproduction.regenerated_bundle import safe
            for component,root in roots.items():
                if not doc['files'][component]:raise ValueError('empty full-cohort bundle component')
                for name,digest in doc['files'][component].items():
                    if sha(safe(root,name))!=digest:raise ValueError('regenerated bundle commitment differs: '+component+'/'+name)
            self.census=roots['census'];self.units=roots['cross_term_units']
            self.attachments=roots.get('attachments');self.bundle=path;self.lean=roots['lean']
        else:
            self.census=path/'census' if (path/'census/complete.json').is_file() else path
            self.attachments=(path/'attachments') if self.census!=path else path.parent/'attachments'
            for candidate in (path/'units/cross-term',path.parent/'units/cross-term'):
                if candidate.is_dir():self.units=candidate;break
        self.seal=read(self.census/'complete.json')
        summary=self.seal['summary']
        if self.seal.get('status')!='PASS' or summary.get('completion_status')!='PASS':
            raise ValueError('full census construction is incomplete')
        if type(summary.get('selected_count')) is not int or summary['selected_count']!=COUNT:
            raise ValueError('full-cohort claim requires exactly 2,122 contexts')
        verify_artifacts(self.census,self.seal['artifacts'])
        self.source=RetainedInputs(self.census)
        if self.units is not None:
            # Relocate the scientific view, without rewriting a sealed plan.
            for name in self.source.files:
                if name not in self.source.commitments:
                    self.source.files[name]=str(self.units/safe_name(name))
            self.source.archive=Archive({'schema':'born_structural_input_view_v1',
                'root':str(self.census),'files':self.source.files})
        base=self.census/safe_name(summary['summary_directory'])
        self.completed=read(base/'structural_completion_results.json')
        self.originals=read(base/'original_implementation_results.json')
        self.pairs=read(base/'maximal_gap_witnesses.json')
        self.outcomes=read(base/'robust_bound_outcomes.json')
        self.inventory=list(self.source.inventory.values())
        ids=[r['unit_id'] for r in self.inventory]
        if len(ids)!=COUNT or len(set(ids))!=COUNT:raise ValueError('full census membership differs')
        for table in (self.completed,self.originals):
            require_equal('ordered census summary identities',
                [[r['unit_id'],r['index']] for r in table],[[uid,i] for i,uid in enumerate(ids)])
        self.directories=[self.census/safe_name(r['context_directory']) for r in self.completed]
        for entry,original,directory in zip(self.completed,self.originals,self.directories):
            stored=read(directory/'original_implementation.json')
            require_equal('original summary/file binding',original,
                          {'index':entry['index'],'unit_id':entry['unit_id'],**stored})
            require_equal('original outcome schema',sorted(stored),
                          sorted(['status','correspondence_status','C_premises','classification','origin']))
            premise=stored['C_premises'];status=premise.get('status')
            if type(status) is not str or status not in ('PASS','FAILED'):raise ValueError('original premise status invalid')
            require_equal('original premise schema',sorted(premise),
                          ['status'] if status=='PASS' else ['error','error_type','status'])
            if status=='FAILED' and any(type(premise[k]) is not str for k in ('error','error_type')):
                raise ValueError('original native exception representation invalid')
            coordinate=stored['correspondence_status']
            if type(coordinate) is not str or coordinate not in ('PASS','FAILED'):raise ValueError('original coordinate status invalid')
            require_equal('original disposition',[stored['status'],stored['classification']],
                ['PASS' if coordinate==status=='PASS' else 'FAILED',
                 'extra SVD-coordinate requirement' if coordinate=='FAILED' else
                 'symbolic implementation failure' if status=='FAILED' else 'completed original implementation'])

    def source_units(self):
        if self.units is not None:return self.units
        name=self.inventory[0]['kind_records'][0]['path']
        path=self.source.path(name)
        return path.parents[len(Path(name).parts)-1]


def exact_frame(context):
    """Recompute every stored exact frame field from the source-bound mode.

    This is a frame audit, not the complete numerical-certificate audit of P03.
    Compare canonical rational strings and JSON types without coercing values.
    """
    v=list(map(Q,context['born']['sym_eigvec_basis'][0]));n=len(v)
    mean=sum(v)/n;w=[x-mean for x in v];s=sum(x*x for x in w)
    if n!=32 or s<=0:raise ValueError('invalid centered nonzero source frame')
    denominator=math.lcm(*(x.denominator for x in w))
    z=[int(x*denominator) for x in w];squared=sum(x*x for x in z)
    return {'w':list(map(str,w)), 's':str(s),
            'G':[['32','0'],['0',str(s)]],
            'P':[[str(Q(squared+n*a*b,n*squared)) for b in z] for a in z]}


def check_exact_frame(context, index):
    require_equal('case '+str(index)+' complete exact frame',context['exact'],exact_frame(context))


def checked_rows(inputs, lean_root):
    """Audit complete exact frames; bind labels and witnesses to Lean literals."""
    from .reproduction.lean_inputs import full_census_records, full_shard_text, full_cohort_inputs_text
    # Reject scientific frame corruption before expensive proof rendering.
    # Subsequent source joins bind this mode to its retained acquisition.
    for entry,directory in zip(inputs.completed,inputs.directories):
        check_exact_frame(read(directory/'CONTEXT.json'),entry['index'])
    print('verified complete exact frame records:',COUNT,flush=True)
    rows,pairs=full_census_records(inputs.census)
    root=Path(lean_root)/'BornCalculus/Census'
    manifest=read(root/'input_manifest.json')
    require_equal('full Lean ordered identities',manifest['ordered_unit_ids'],[r['unit_id'] for r in rows])
    require_equal('full Lean case count',manifest['cases'],COUNT)
    for shard,start in enumerate(range(0,COUNT,8)):
        actual=(root/f'Shard{shard:03d}.lean').read_bytes()
        chunk=rows[start:start+8]
        candidates=[full_shard_text(chunk,shard,array_vectors=arrays).encode() for arrays in (False,True)]
        if actual not in candidates:raise ValueError('full Lean shard input differs: '+str(shard))
    if (root/'FullInputs.lean').read_text()!=full_cohort_inputs_text(rows):
        raise ValueError('full Lean cohort assembly differs')
    first_nonzero=0
    for index,(row,entry,directory,frame) in enumerate(zip(inputs.inventory,inputs.completed,inputs.directories,rows)):
        context=read(directory/'CONTEXT.json');cert=read(directory/'structural_completion_certificate.json')
        c=Comparison(project_bindings=False);bind_inputs(c,context,row,inputs.source)
        require_agreement(c,'case '+str(entry['index']))
        c.compare('complete completion row',entry,
            {'index':index,'unit_id':row['unit_id'],'status':'PASS','context_directory':entry['context_directory']})
        c.compare('completion identity',[cert['index'],cert['unit_id'],cert['overall_status'],cert['failures']],
                  [index,row['unit_id'],'PASS',[]])
        w=[Q(z,frame['D']) for z in frame['z']];s=Q(frame['S'],frame['D']**2)
        witness={'pair':[frame['i'],frame['j']],'context':'raw_by_state','atom':0,
                 'visited':sum(31-a for a in range(frame['i']))+frame['j']-frame['i']}
        c.compare('complete exact strictness witness',remove_costs(cert['certificates']['strictness']),
                  expected_strictness(context,{'w':list(map(str,w)),'s':str(s),'witness':witness}))
        require_agreement(c,'case '+str(index))
        first_nonzero+=frame['i']!=0
        if (index+1)%500==0:print('bound retained source inputs and witnesses:',index+1,flush=True)
    require_equal('nonzero first witness indices',first_nonzero,25)
    return rows,pairs


def atom_totals(inputs):
    from .reproduction.census_extension import atom_classes
    totals=Counter();cases=0
    for directory in inputs.directories:
        context=read(directory/'CONTEXT.json');cert=read(directory/'structural_completion_certificate.json')
        classes=atom_classes(context,cert)
        require_equal('complete atom classifications',read(directory/'atom_classes.json'),classes)
        atoms=classes['atoms'];singular=[a for a in atoms if a['class']=='singular']
        cases+=bool(singular)
        totals.update(active=len(atoms),positive=len(atoms)-len(singular),singular=len(singular),
                      singleton=sum(a['singleton'] for a in singular),nonsingleton=sum(not a['singleton'] for a in singular))
    actual={**totals,'singular_contexts':cases}
    require_equal('full-cohort atom counts',actual,
                  {'active':17008,'positive':16693,'singular':315,'singleton':283,'nonsingleton':32,'singular_contexts':272})
    return actual


def bound_checks(inputs,pairs):
    from .reproduction.census_extension import robust_outcomes
    expected=robust_outcomes(pairs);require_equal('complete bound outcomes',inputs.outcomes,expected)
    require_equal('registered and retrospective bound counts',
        [expected[k] for k in ('registered_pass','registered_fail','amended_pass','amended_fail','minimum_cases')],
        [2005,117,2122,0,[425]])
    if not expected['minimum_interval']['verified']:raise ValueError('minimum interval does not enclose the exact minimum')
    return {'registered_3_over_20':[2005,117],'uniform_bound':'1/25',
            'minimum_enclosure':['0.0438357','0.0438358'],'minimum_cases':[425],
            'maximized_statistic':'raw-label-zero trace gap',
            'pair_eligibility':'equal labels in raw, package and joint maps',
            'per_case_witnesses':[{**pair,'unit_id':row['unit_id']} for pair,row in zip(pairs,inputs.inventory)]}


def original_diagnostics(inputs):
    """Native constructor replay and original outcome audit, not new history."""
    from .snapshot.g2a import _oriented_basis
    totals=Counter();qualified=0
    for index,(entry,original,directory) in enumerate(zip(inputs.completed,inputs.originals,inputs.directories)):
        context=read(directory/'CONTEXT.json');cert=read(directory/'structural_completion_certificate.json')
        rebuilt=_oriented_basis(context['born']);stored=context['archived_unit_structural']['raw']['basis_and_projector_inputs']
        c=Comparison(project_bindings=False);c.compare('native_constructor',rebuilt,stored)
        maximum=max((Q(d['absolute_difference']) for g in c.groups.values() for d in g['differences']
                     if d['absolute_difference'] is not None),default=Q(0))
        bit=c.result()['overall_agreement'];numeric=cert['certificates']['correspondence'];checks=Comparison(project_bindings=False)
        checks.compare('constructor diagnostic',[numeric['constructor_literal_bit_equality_status'],numeric['constructor_maximum_difference']],
                       ['PASS' if bit else 'FAILED',str(maximum)])
        native={'status':'PASS','constructor_maximum_difference':str(maximum),'threshold_exact':'1/1000000000000'}
        fields=audit_original(checks,directory,entry,original,native,Q(context['exact']['s']),inputs.source)
        require_agreement(checks,'original implementation '+str(index));qualified+=bool(fields)
        totals.update(overall_pass=original['status']=='PASS',coordinate_pass=original['correspondence_status']=='PASS',
                      symbolic_pass=original['C_premises']['status']=='PASS',bit_pass=bit)
    require_equal('original implementation counts',dict(totals),
                  {'overall_pass':1115,'coordinate_pass':2078,'symbolic_pass':1141,'bit_pass':27})
    return {'overall':[1115,1007],'coordinate':[2078,44],'symbolic':[1141,981],'bit_equality':[27,2095],
            'qualified_native_failure_events':qualified,
            'boundary':'Recorded symbolic failure events/errors remain bound, typed and disposition-checked; acquisition SymPy/GMP exception truth is not independently replayed. Successful payloads and native constructor values are replayed.'}


def attachments_check(inputs):
    from .reproduction.attachment_comparison import attachment_index,validate_attachment,audit_summaries,compare_summary_rows
    root=inputs.attachments;seal=read(root/'complete.json');verify_artifacts(root,seal['artifacts'])
    base=root/safe_name(seal['summary']['directory']);rows=read(base/'attachments.json')
    ids=[r['unit_id'] for r in inputs.inventory];indexed=attachment_index(rows,ids,'full attachments')
    hashes={};units=inputs.source_units()
    for inventory,entry,original,directory in zip(inputs.inventory,inputs.completed,inputs.originals,inputs.directories):
        for view in ('raw','pkg'):
            result=validate_attachment(indexed[(inventory['unit_id'],view)],inventory,entry,original,directory,units,hashes)
            if not result['independent_validation']['overall_agreement']:raise ValueError('attachment source/value binding differs: '+inventory['unit_id']+'/'+view)
    c=Comparison(project_bindings=False)
    compare_summary_rows(c,'full type-7 summaries',audit_summaries(rows,COUNT),read(base/'descriptive_summaries.json'))
    require_agreement(c,'full descriptive summaries')
    require_equal('attachment counts',[len(rows),seal['summary']['contexts']],[4244,COUNT])
    return {'contexts':COUNT,'records':4244,'type_7_summaries':58,'rescored':False}


def inventory_check(inputs):
    from . import metadata
    # Re-select by rank from the entire committed unit stream, not only the
    # rows the producer included in its selected inventory.
    unit_path=inputs.source.path(inputs.inventory[0]['kind_records'][0]['path'])
    inputs.source.verify(unit_path,inputs.inventory[0]['kind_records'][0]['file_sha256'])
    seen={};counts=Counter();kinds={}
    with unit_path.open() as f:
        for line in f:
            unit=metadata.metadata(line,{'unit_id','kind_cell_id','basis_and_projector_inputs'})
            uid=unit['unit_id'];basis=unit['basis_and_projector_inputs'];rank=basis['effective_rank'] if basis else None
            if uid in seen:
                if seen[uid]!=rank:raise ValueError('raw/package ranks differ')
            else:seen[uid]=rank;counts[str(rank)]+=1
            kinds.setdefault(uid,set()).add(unit['kind_cell_id'])
    if any(values!={hashlib.sha256((uid+kind).encode()).hexdigest() for kind in ('raw','pkg')}
           for uid,values in kinds.items()):raise ValueError('complete unit pairing differs')
    selected={uid for uid,rank in seen.items() if type(rank) is int and rank==2}
    require_equal('entire rank-two cohort',sorted(selected),sorted(inputs.source.inventory))
    require_equal('complete collection count',len(seen),11177)
    require_equal('rank distribution',dict(counts),{'2':2122,'3':2818,'4':3292,'5':2623,'6':242,'None':80})
    return {'collection':11177,'rank_two':COUNT,'availability_subselection':False,'rank_counts':dict(counts)}


def maps_check(inputs):
    """Replay the shipped exports from the already source-bound retained K."""
    from .reproduction.map_replay import build_replayer,replay_input,compare_replay
    source_root=Path.cwd().resolve()
    if not (source_root/'vendor/pica').is_dir():raise ValueError('P03 map replay requires running from the public source checkout with vendor/pica')
    scratch=source_root/'scratch/registry_full_cohort';scratch.mkdir(parents=True,exist_ok=True)
    binary,build=build_replayer(source_root,scratch/'map_build')
    with tempfile.TemporaryDirectory(dir=scratch,prefix='maps-') as temporary:
        directory=Path(temporary);cases=[]
        for index,(row,path) in enumerate(zip(inputs.inventory,inputs.directories)):
            cases.append(replay_input(read(path/'CONTEXT.json'),index,row['unit_id'],{'kernel_exponent':1,'source_binding_checked':True}))
        input_file=directory/'inputs.jsonl'
        with input_file.open('w') as stream:
            for case in cases:stream.write(json.dumps(case,allow_nan=False,separators=(',',':'))+'\n')
        output=directory/'replayed.jsonl'
        with output.open('w') as stream:
            subprocess.run([str(binary),str(input_file)],stdout=stream,check=True)
        actual=list(map(json.loads,output.read_text().splitlines()))
        if len(actual)!=COUNT:raise ValueError('public map replay population incomplete')
        checks=[compare_replay(case,result) for case,result in zip(cases,actual)]
        failed=[check for check in checks if check['status']!='PASS']
        if failed:raise ValueError('public K map replay differs: '+json.dumps(failed[:1]))
    return {'raw':COUNT,'package':COUNT,'joint':COUNT,'stationary_and_vectors_exact':True,
            'public_source_and_binary_commitments':build}


def numerical_audit(inputs,entry,original,directory,inventory):
    audit=validate_new_case(directory,entry,original,inventory=inventory,inputs=inputs.source)
    # The earlier comparison validates physical addresses in its original run.
    # A portable input may relocate that exact same case. Only the two storage
    # addresses change; independently recomputed frame/certificate hashes and
    # every scientific scalar still go through the strict auditor unchanged.
    fields={'/C_premises/six_state_certificate':'six_state_exact_completion.json',
            '/carrier/uniform_proof_binding/frame_context':'CONTEXT.json'}
    group=audit['independent_validation']['field_groups']['complete_scientific_certificate_groups']
    retained=[];relocated=[]
    for difference in group['differences']:
        suffix=fields.get(difference['field']);value=difference['generated']
        relative=Path(entry['context_directory'])/suffix if suffix else None
        if suffix and type(value) is str and Path(value).parts[-len(relative.parts):]==relative.parts:
            group['exact']+=1;relocated.append(difference)
        else:retained.append(difference)
    group['differences']=retained
    audit['independent_validation']['overall_agreement']=all(
        value['compared']==value['exact'] for value in audit['independent_validation']['field_groups'].values())
    audit['relocated_storage_addresses']=relocated
    return audit


def endpoint_subset(audit,endpoints):
    names=['BornCalculus.'+e for e in endpoints]
    if not set(names)<=set(audit['dependencies']):raise ValueError('claim endpoints absent from fresh Lean audit')
    return {**audit,'dependencies':{n:audit['dependencies'][n] for n in names},'declarations':len(names),
            'fresh_inventory_declarations':audit['declarations'],'kernel_graph_scope':'complete fresh source inventory'}


def bundle_lean_check(inputs,root):
    """Bind receipt coverage to fresh kernel evidence in the bundle's project.

    The shipped audit harness runs read-only; even a retained /mnt input tree
    receives no caches, logs, manifests or build writes.
    """
    from .reproduction.lean_comparison import driver,readonly_kernel_check,axiom_sets
    root=Path(root);coverage=read(root/'formal_coverage.json')
    require_equal('regenerated Lean coverage',
        [coverage['status'],coverage['build_status'],coverage['census_cases'],coverage['full_cohort_inputs']],
        ['APPLICABLE','BUILT_AND_AUDITED',COUNT,True])
    audit=read(root/safe_name(coverage['audit_receipt']))
    build=read(root/safe_name(coverage['build_receipt']))
    require_equal('regenerated Lean receipt disposition',[build['status'],audit['status'],audit['fresh'],audit['forbidden']],
                  ['PASS','PASS',True,{}])
    rows=driver().inventory(root)
    require_equal('regenerated Lean inventory',sorted(audit['dependencies']),sorted(row['name'] for row in rows))
    workspace=Path('scratch/registry_full_cohort/kernel_checks');workspace.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=workspace) as temporary:
        fresh=readonly_kernel_check(root,rows,temporary)
    require_equal('regenerated Lean fresh axiom sets',axiom_sets(audit),axiom_sets(fresh))
    return {**fresh,'fresh':True,'project':str(root.resolve())}


def verify(identifier, data, lean_root, *, certificate_output=None):
    if certificate_output is not None and identifier!='P13':
        raise ValueError('--certificate-output is supported only by P13')
    inputs=Inputs(data,attachments=identifier=='P11')
    lean_root=inputs.lean or lean_root
    rows,pairs=checked_rows(inputs,lean_root)
    fresh=bundle_lean_check(inputs,lean_root) if inputs.bundle else None
    result={'contexts':COUNT,'nonzero_first_indices':25,'exact_full_Lean_input_binding':True}
    if identifier=='P03':
        qualified=0
        for index,(entry,original,directory,inventory) in enumerate(zip(inputs.completed,inputs.originals,inputs.directories,inputs.inventory)):
            audit=numerical_audit(inputs,entry,original,directory,inventory)
            if not audit['independent_validation']['overall_agreement']:raise ValueError('full scientific certificate audit failed at '+str(index))
            qualified+=bool(audit['validation_coverage']['unchecked_scientific_fields'])
            if index%100==0:print('verified full numerical certificate',index,flush=True)
        result.update(numerical_cases=COUNT,qualified_native_failure_events=qualified,
                      floating_envelope='conditional arithmetic premises, not unconditional platform accuracy')
        result['public_K_map_replay']=maps_check(inputs)
    elif identifier=='P11':result.update(attachments_check(inputs))
    elif identifier=='P13':result.update(bound_checks(inputs,pairs))
    elif identifier=='B09':result.update(original_diagnostics(inputs))
    elif identifier=='B10':result.update(atom_totals(inputs))
    elif identifier=='B13':result.update(inventory_check(inputs))
    from .__main__ import REGISTRY,audit_endpoints,LEAN_SCOPE
    endpoints=REGISTRY[identifier][2]
    if endpoints:
        result['axiom_audit']=endpoint_subset(fresh,endpoints) if fresh else audit_endpoints(lean_root,endpoints)
        result['Lean_scope']=LEAN_SCOPE[identifier]
    result['validation_coverage']={'source_joins_and_complete_exact_frames':COUNT,
        'literal_and_witness_binding':COUNT,'complete_numerical_certificate_audit':identifier=='P03',
        'other_records':'Claim-specific checks below; complete-record numerical validation is P03, not implied by literal/witness binding.'}
    if fresh:result['regenerated_Lean_project_audit']=fresh
    result['boundary']='Archive/execution identity, native source formation and complete-record binding are external to Lean; Python verifies the retained commitments and source joins. No history reconstruction, finite precision/access guarantee, fresh experiment or induced dynamics.'
    if certificate_output is not None:
        output=Path(certificate_output);output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    return result
