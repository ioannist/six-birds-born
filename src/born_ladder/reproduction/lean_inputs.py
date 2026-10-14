"""Render all eight formal-input modules from completed scientific certificates.

No retained archive, reviewed-output root, proof note or process receipt is an
input. An isolated Lean project uses the public proof sources and can reuse the
public project's existing Lake packages/build cache without changing them.
"""
from fractions import Fraction as Q
from pathlib import Path
import json
import resource
import shutil
import time

from born_ladder import arithmetic as A
from born_ladder.robust_census import integer_record, scan_records, render_pairs
from .worked_cases import read, write
from .runs import validate_output, exclusive_output
from .embedding import census as C, transport as T, ensemble as E, fragment as F, order as O, ri as R

MODULES=('CensusInputs','CensusAtomInputs','CensusRobustInputs','RIInputs',
         'B04Inputs','B05Inputs','B06Inputs','B07Inputs')


def full_census_records(root, *, expected_count=2122):
    """Validate the ordered exact inputs without relying on producer status.

    The pre-amendment full run has no complete.json and marks the registered
    3/20 scientific FAIL as a failed execution. Its per-context construction
    certificates are nevertheless PASS. Derive paths from immutable unit IDs;
    never omit a context because of the obsolete threshold verdict.
    """
    root = Path(root)
    seal = read(root/'inventory_complete.json')
    inventory = read(root/seal['directory']/'INVENTORY.json')
    completed_seal = root/'complete.json'
    amended = completed_seal.exists()
    if amended:
        complete = read(completed_seal)
        if complete.get('status') != 'PASS' or complete['summary']['selected_count'] != expected_count:
            raise ValueError('full census completion seal differs')
        name = Path(complete['summary']['summary_directory'])
        if name.is_absolute() or '..' in name.parts:
            raise ValueError('full census summary path escapes output')
        summary = root/name
    else:
        # Before amendment, only the original summary is authoritative; never
        # guess that a newer, possibly still-being-written directory is complete.
        summary = root/'summaries/summary_0001'
    completions = read(summary/'structural_completion_results.json')
    robust = read(summary/'maximal_gap_witnesses.json')
    ids = [r['unit_id'] for r in inventory]
    if (len(ids) != expected_count or len(set(ids)) != expected_count
            or ids != [r['unit_id'] for r in completions]
            or len(robust) != expected_count
            or any(r['index'] != i for i, r in enumerate(completions))):
        raise ValueError('full census count/order/identity differs')
    if seal['summary']['selected_count'] != expected_count:
        raise ValueError('full census inventory seal count differs')
    from born_ladder.robust_census import point_read
    rows, pairs = [], []
    for i, uid in enumerate(ids):
        if len(uid) != 64 or any(c not in '0123456789abcdef' for c in uid):
            raise ValueError('invalid census unit identity')
        entry = completions[i]
        name = Path(entry.get('context_directory', f'construction_attempts/{uid}/attempt_0001/contexts/{uid}'))
        if name.is_absolute() or '..' in name.parts:
            raise ValueError('full census context path escapes output')
        if amended and entry['status'] != 'PASS':
            raise ValueError('amended census has incomplete construction')
        directory = root/name
        context = read(directory/'CONTEXT.json')
        cert = read(directory/'structural_completion_certificate.json')
        if (context['identity']['unit_id'] != uid or cert['unit_id'] != uid
                or cert['index'] != i or cert['overall_status'] != 'PASS'
                or cert['failures']):
            raise ValueError('full census construction certificate differs')
        strictness = cert['certificates']['strictness']
        readout = strictness['first_separating_readout']
        if (readout['context'], readout['numeric_atom']) != ('raw_by_state', 0):
            raise ValueError('full census first readout is not raw label zero')
        row = C.extract(context, strictness, registered=False)
        row['i'] = strictness['pair'][0]
        # Recompute the earlier eligible-pair rule rather than trust status.
        if any(all(q[a] == q[b] for q in row['labels'])
               and row['z'][a] != row['z'][b]
               for a in range(32) for b in range(a+1, 32)
               if (a, b) < (row['i'], row['j'])):
            raise ValueError('earlier eligible lexicographic pair exists')
        w = [Q(z, row['D']) for z in row['z']]
        if (w != list(map(Q, context['exact']['w']))
                or Q(row['S'], row['D']**2) != Q(context['exact']['s'])):
            raise ValueError('full census source vector/exact frame differs')
        record = integer_record(context['exact']['w'], row['labels'])
        if record != read(directory/'integer_frame.json'):
            raise ValueError('full census integer frame differs')
        row['reads'] = [point_read(record, k) for k in range(32)]
        atoms, moments = [], []
        for f, labels in zip(C.FIELDS, row['labels']):
            table = []
            for label in range(4):
                block = [k for k, a in enumerate(labels) if a == label]
                n, z, zz = (len(block), sum(row['z'][k] for k in block),
                            sum(row['z'][k]**2 for k in block))
                table.append((n, z, zz))
                if not block:
                    continue
                det = Q(n*zz-z*z, row['D']**2)
                effect = [[Q(n, 32), Q(z, 32*row['D'])],
                          [Q(z*row['D'], row['S']), Q(zz, row['S'])]]
                atoms.append({'context': f, 'atom': label, 'states': block,
                              'Gram_det_exact': str(det),
                              'effect_exact': A.qserial(effect), 'positive': det > 0})
            moments.append(table)
        if atoms != cert['certificates']['C_premises']['atom_certificates']:
            raise ValueError('full census atom certificates differ')
        supplemental = directory/'atom_classes.json'
        if amended or supplemental.exists():
            from .census_extension import atom_classes
            if read(supplemental) != atom_classes(context, cert):
                raise ValueError('full census supplemental atom classes differ')
        row['atoms'] = moments
        local = scan_records([record], require_bound=False)
        local['cases'][0]['case'] = i
        local['minimum_cases'] = [i]
        if local != read(directory/'maximal_gap_witness.json'):
            raise ValueError('full census maximal-gap certificate differs')
        pair = local['cases'][0]
        if pair != robust[i]:
            raise ValueError('full census maximal-gap summary differs')
        row['robust_i'], row['robust_j'] = pair['i'], pair['j']
        row['gap'] = Q(pair['gap_exact'])
        row['unit_id'] = uid
        rows.append(row)
        pairs.append(pair)
    outcomes = summary/'robust_bound_outcomes.json'
    if amended or outcomes.exists():
        from .census_extension import robust_outcomes
        if read(outcomes) != robust_outcomes(pairs):
            raise ValueError('full census supplemental bound outcomes differ')
    return rows, pairs


def full_shard_text(rows, shard, *, array_vectors=False):
    """Small literal modules with kernel-checked, proof-carrying records."""
    def integer(x):
        return f'({x} : ℤ)'
    def vec(xs, fmt=str):
        if array_vectors:
            return f'(fun (k : Fin {len(xs)}) => #['+','.join(fmt(x) for x in xs)+'][k.val]!)'
        return '!['+','.join(fmt(x) for x in xs)+']'
    ns = f'BornCalculus.Census.Shard{shard:03d}'
    out = ['import BornCalculus.Census.Certificate', '', f'namespace {ns}',
           'open BornCalculus.Census', 'open scoped BigOperators',
           'set_option maxHeartbeats 0', 'set_option maxRecDepth 100000', '',
           f'def raw (c : Fin {len(rows)}) : RawCase := match c.val with']
    for k, row in enumerate(rows):
        fields = [integer(row['D']), integer(row['S']), vec(row['z'], integer),
                  vec(row['labels'], vec), str(row['i']), str(row['j']),
                  integer(row['m0']), integer(row['m1']), integer(row['m2']),
                  str(row['robust_i']), str(row['robust_j'])]
        fields += [vec(row['atoms'], lambda table: vec([a[j] for a in table], integer))
                   for j in range(3)]
        fields += [vec([q.numerator for q in row['reads']], integer),
                   vec([q.denominator for q in row['reads']], integer),
                   integer(row['gap'].numerator), integer(row['gap'].denominator)]
        groups = {}
        for i in range(32):
            key = 16*row['labels'][0][i]+4*row['labels'][1][i]+row['labels'][2][i]
            groups.setdefault(key, []).append(i)
        fields += [vec([choose(groups[key], key=lambda i: row['reads'][i]) if key in groups else 0
                        for key in range(64)]) for choose in (min, max)]
        out.append(f" | {k if k < len(rows)-1 else '_'} => ⟨"+',\n   '.join(fields)+'⟩')
    for name, check in [('frame', 'FrameCheck'), ('moments', 'MomentCheck'),
                        ('pair', 'PairCheck'), ('earlier', 'EarlierCheck'),
                        ('atoms', 'AtomCheck'), ('reads', 'ReadCheck'),
                        ('robust', 'RobustCheck'), ('ranges', 'RangeCheck'),
                        ('earlierMax', 'TieCheck')]:
        out += ['', f'theorem {name} (c : Fin {len(rows)}) : {check} (raw c) := by',
                ' decide +kernel +revert']
    out += ['', f'def certified (c : Fin {len(rows)}) : CertifiedCase :=',
            ' ⟨raw c,frame c,moments c,pair c,earlier c,atoms c,reads c,robust c,ranges c,earlierMax c⟩']
    counts = {
        'activeCount': lambda n, z, zz: n > 0,
        'positiveCount': lambda n, z, zz: n > 0 and n*zz-z*z > 0,
        'singularCount': lambda n, z, zz: n > 0 and n*zz-z*z == 0,
    }
    for name, test in counts.items():
        count = sum(test(*a) for r in rows for table in r['atoms'] for a in table)
        out += ['', f'theorem {name}_total :',
                f' (∑ c : Fin {len(rows)}, (raw c).{name}) = {count} := by',
                ' decide +kernel']
    count = sum(any(n > 0 and n*zz-z*z == 0 for table in r['atoms']
                    for n, z, zz in table) for r in rows)
    out += ['', f'theorem singularContext_total :',
            f' (∑ c : Fin {len(rows)}, (raw c).singularContext) = {count} := by',
            ' decide +kernel', '', f'end {ns}', '']
    return '\n'.join(out)


def render_full_census_shards(census, destination, *, shard_size=8, limit=None):
    """Render the whole target cohort; limit is only for scale experiments."""
    rows, pairs = full_census_records(census)
    if limit is not None:
        rows = rows[:limit]
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    sizes = {}
    for shard, start in enumerate(range(0, len(rows), shard_size)):
        name = f'Shard{shard:03d}'
        blob = full_shard_text(rows[start:start+shard_size], shard).encode()
        (destination/(name+'.lean')).write_bytes(blob)
        sizes[name] = len(blob)
    minimum = min(Q(p['gap_exact']) for p in pairs)
    manifest = {
        'schema': 'born_full_census_lean_shards_v1', 'cases': len(rows),
        'source_cases_checked': len(pairs), 'shard_size': shard_size,
        'module_bytes': sizes, 'ordered_unit_ids': [r['unit_id'] for r in rows],
        'registered_3_over_20_failures': sum(Q(p['gap_exact']) < Q(3, 20) for p in pairs),
        'minimum_cases': [p['case'] for p in pairs if Q(p['gap_exact']) == minimum],
        'minimum_gap_exact': str(minimum),
    }
    (destination/'input_manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
    return rows, pairs, sizes


def full_cohort_inputs_text(rows, *, shard_size=8):
    """Combine checked shards by an explicit bijection with Fin 2122."""
    if len(rows) != 2122 or len(rows) % shard_size == 0:
        raise ValueError('full-cohort glue expects 2122 cases and a nonempty tail')
    groups, tail = divmod(len(rows), shard_size)
    out = [f'import BornCalculus.Census.Shard{s:03d}' for s in range(groups+1)]
    out += ['import BornCalculus.Census.Assembly', '', 'namespace BornCalculus.Census',
            'open scoped BigOperators', 'set_option maxHeartbeats 0',
            'set_option maxRecDepth 100000', '',
            f'def shards (s : Fin {groups}) : CertifiedShard {shard_size} := match s.val with']
    for s in range(groups):
        chunk = rows[s*shard_size:(s+1)*shard_size]
        active = sum(n > 0 for r in chunk for table in r['atoms'] for n, z, zz in table)
        positive = sum(n > 0 and n*zz-z*z > 0 for r in chunk for table in r['atoms'] for n, z, zz in table)
        singular = sum(n > 0 and n*zz-z*z == 0 for r in chunk for table in r['atoms'] for n, z, zz in table)
        contexts = sum(any(n > 0 and n*zz-z*z == 0 for table in r['atoms']
                           for n, z, zz in table) for r in chunk)
        ns = f'Shard{s:03d}'
        out += [f" | {s if s < groups-1 else '_'} => ⟨{ns}.certified,{active},{positive},{singular},{contexts},",
                f'   {ns}.activeCount_total,{ns}.positiveCount_total,{ns}.singularCount_total,{ns}.singularContext_total⟩']
    out += ['', f'def partition : (Fin {groups} × Fin {shard_size}) ⊕ Fin {tail} ≃ Fin 2122 :=',
            f' cohortPartition {groups} {shard_size} {tail}', '',
            f'def fromShard : (Fin {groups} × Fin {shard_size}) ⊕ Fin {tail} → CertifiedCase',
            ' | .inl (s,i) => (shards s).cases i',
            f' | .inr i => Shard{groups:03d}.certified i', '',
            'def censusCase (c : Fin 2122) : CertifiedCase := fromShard (partition.symm c)', '',
            'theorem censusCase_partition (x) : censusCase (partition x) = fromShard x := by',
            ' simp only [censusCase,Equiv.symm_apply_apply]', '',
            'theorem sum_cases (weight : CertifiedCase → ℕ) :',
            ' (∑ c : Fin 2122, weight (censusCase c)) =',
            f' (∑ s : Fin {groups}, ∑ i : Fin {shard_size}, weight ((shards s).cases i)) +',
            f' (∑ i : Fin {tail}, weight (Shard{groups:03d}.certified i)) := by',
            f' simpa only [censusCase,partition,fromShard] using sum_through_partition {groups} {shard_size} {tail} fromShard weight']
    for name, field, total in [('activeCount', 'active', 17008), ('positiveCount', 'positive', 16693),
                               ('singularCount', 'singular', 315), ('singularContext', 'contexts', 272)]:
        out += ['', f'theorem census_{name}_total :',
                f' (∑ c : Fin 2122, (censusCase c).raw.{name}) = {total} := by',
                f' rw [sum_cases (fun C => C.raw.{name})]',
                f' have h : (∑ s : Fin {groups}, ∑ i : Fin {shard_size}, ((shards s).cases i).raw.{name}) =',
                f'   ∑ s : Fin {groups}, (shards s).{field} := by',
                '   apply Finset.sum_congr rfl', '   intro s _',
                f'   exact (shards s).{field}_total', ' rw [h]',
                f' change (∑ s : Fin {groups}, (shards s).{field}) +',
                f'   (∑ i : Fin {tail}, (Shard{groups:03d}.raw i).{name}) = {total}',
                f' rw [Shard{groups:03d}.{name}_total]', ' decide +kernel']
    out += ['', 'end BornCalculus.Census', '']
    return '\n'.join(out)


def checked_worked(worked):
    root=Path(worked);original=read(root/'original/CONTEXT.json');cert=read(root/'original/certificates.json')
    selected=read(root/'selected/CONTEXT.json');other=read(root/'selected/certificates.json')
    from .worked_cases import frame, selected_witness, carrier_certificate
    from born_ladder.instruments import Instrument
    # Recheck the equations/inequalities, not a hash or an archive identity.
    derived={'B04':T.extract(original,cert['amplitude'],cert['joined']),
             'B05':E.extract(original,cert['ensemble']),'B06':F.extract(original,cert['finite_family']),'B07':O.extract(original)}
    if A.qserial(derived)!=cert['lean_certificates']:
        raise ValueError('worked-case Lean certificate numerical fields differ')
    for context in (original,selected):
        w,s,P,_=frame(context)
        if context['exact']!={'w':A.qserial(w),'s':str(s),'projector':A.qserial(P)}:
            raise ValueError('worked-case exact frame differs from emitted vector')
    w,s,P,K=frame(selected);m=Instrument(selected,w,s,P,K)
    if A.qserial(selected_witness(m))!=other['strictness'] or read(root/'selected/initial_strictness_certificate.json')!=other['strictness']:
        raise ValueError('selected-case strictness certificate differs')
    if A.certify_G(s)!=other['six_state'] or read(root/'selected/six_state_certificate.json')!=other['six_state']:
        raise ValueError('selected-case six-state premises differ')
    ri_data=R.extract(selected,other['strictness'])
    if A.qserial(ri_data)!=other['lean_certificates']['RI']:raise ValueError('RI Lean certificate numerical fields differ')
    if carrier_certificate(m)!=other['carrier']:
        raise ValueError('selected-case carrier certificate differs')
    return original,cert,derived,ri_data


def census_records(root, *, expected_count=120, registered=True):
    root=Path(root);complete=read(root/'complete.json');summary=complete['summary']
    inventory=read(root/summary['inventory_directory']/'INVENTORY.json')
    completions=read(root/summary['summary_directory']/'structural_completion_results.json')
    robust=read(root/summary['summary_directory']/'maximal_gap_witnesses.json')
    count=len(inventory)
    if expected_count is not None and count!=expected_count:
        raise ValueError(f'census count mismatch: expected {expected_count} cases, found {count}')
    if len(completions)!=count or len(robust)!=count:
        raise ValueError('census inventory/completion/maximal-gap counts differ')
    ids=[r['unit_id'] for r in inventory]
    if len(set(ids))!=count or ids!=[r['unit_id'] for r in completions] or any(r['index']!=i or r['status']!='PASS' for i,r in enumerate(completions)):
        raise ValueError('census completion/order/identity differs')
    records=[];integer=[]
    for i,entry in enumerate(completions):
        path=Path(entry['context_directory'])
        if path.is_absolute() or '..' in path.parts:raise ValueError('census context path escapes output')
        directory=root/path;context=read(directory/'CONTEXT.json');cert=read(directory/'structural_completion_certificate.json')
        if context['identity']['unit_id']!=ids[i]:raise ValueError('census context identity differs')
        row=C.extract(context,cert['certificates']['strictness'],registered=registered);records.append(row)
        from born_ladder.independent import check_context
        check_context(directory,'structural_completion_certificate.json')
        if A.certify_G(Q(context['exact']['s']))!=read(directory/'six_state_exact_completion.json'):
            raise ValueError('census six-state certificate differs')
        record=integer_record(context['exact']['w'],[context['lens'][f] for f in C.FIELDS])
        if record!=read(directory/'integer_frame.json'):
            raise ValueError('census integer frame differs')
        expected_atoms=[]
        for f,labels in zip(C.FIELDS,row['labels']):
            for label in sorted(set(labels)):
                block=[j for j,x in enumerate(labels) if x==label]
                d=Q(len(block)*sum(row['z'][j]**2 for j in block)-sum(row['z'][j] for j in block)**2,row['D']**2)
                effect=[[Q(len(block),32),sum(Q(row['z'][j],row['D']) for j in block)/32],
                        [sum(Q(row['z'][j],row['D']) for j in block)/Q(row['S'],row['D']**2),Q(sum(row['z'][j]**2 for j in block),row['S'])]]
                expected_atoms.append({'context':f,'atom':label,'states':block,'Gram_det_exact':str(d),
                                       'effect_exact':A.qserial(effect),'positive':d>0})
        if expected_atoms!=cert['certificates']['C_premises']['atom_certificates']:
            raise ValueError('census atom certificates differ')
        integer.append(record)
        local=scan_records([record],require_bound=registered);local['cases'][0]['case']=i;local['minimum_cases']=[i]
        if local!=read(directory/'maximal_gap_witness.json'):
            raise ValueError('census maximal-gap certificate differs')
    pairs=scan_records(integer,require_bound=registered)['cases']
    if pairs!=robust:raise ValueError('census maximal-gap table differs')
    return records,pairs


def render_modules(census,worked):
    original,cert,data,ri_data=checked_worked(worked)
    records,pairs=census_records(census)
    return input_texts(records,pairs,original,cert,data,ri_data)


def input_texts(records,pairs,original,cert,data,ri_data):
    """The registered renderer; its templates and bytes are unchanged."""
    return {'CensusInputs':C.render(records),'CensusAtomInputs':C.atom_selectors(records),
            'CensusRobustInputs':render_pairs(pairs),'RIInputs':R.render_checked(ri_data),
            'B04Inputs':T.render_checked(original,data['B04']),
            'B05Inputs':E.render_checked(cert['ensemble'],data['B05']),
            'B06Inputs':F.render_checked(data['B06']),
            'B07Inputs':O.render_checked(data['B07'])}


def project_sources(source,output, *, include_registered_inputs=False, regenerate_full_census=False):
    """Copy public proof sources; reuse local Lake dependencies when available.

    Build artifacts are copied, not linked: compilation of rendered inputs
    cannot overwrite the original project's artifacts. Only public dependency
    packages are shared, as in the standard existing .lake build.
    """
    source=Path(source).resolve(strict=True);output=Path(output).resolve()
    if output==source:raise ValueError('render to a separate Lean project, not the public source root')
    for name in ('lakefile.toml','lake-manifest.json','lean-toolchain','BornCalculus.lean'):
        shutil.copy2(source/name,output/name)
    target=output/'BornCalculus';target.mkdir(exist_ok=True)
    for path in (source/'BornCalculus').rglob('*.lean'):
        relative=path.relative_to(source/'BornCalculus')
        # The pipeline regenerates these literals from its own census. Copying
        # committed data first would reject valid new literals before Lean can
        # check them, and could obscure whether regeneration actually occurred.
        if regenerate_full_census and relative.parts[0]=='Census' and (path.stem.startswith('Shard') or path.stem=='FullInputs'):
            continue
        if include_registered_inputs or len(relative.parts)>1 or path.stem not in MODULES:
            dest_path=target/relative
            dest_path.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,dest_path)
    for path in (source/'BornCalculus').rglob('audit_manifest.json'):
        dest_path=target/path.relative_to(source/'BornCalculus')
        dest_path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,dest_path)
    helpers=source/'BornCalculus/Census'
    if helpers.is_dir():
        dest_helpers=target/'Census'
        dest_helpers.mkdir(exist_ok=True)
        for path in helpers.glob('*.py'):
            shutil.copy2(path,dest_helpers/path.name)
        if include_registered_inputs and (helpers/'input_manifest.json').is_file():
            shutil.copy2(helpers/'input_manifest.json',dest_helpers/'input_manifest.json')
    if (source/'tools').is_dir():
        shutil.copytree(source/'tools',output/'tools',dirs_exist_ok=True)
    cache=source/'.lake';dest=output/'.lake'
    if (cache/'packages').is_dir():
        dest.mkdir(exist_ok=True)
        if not (dest/'packages').exists():(dest/'packages').symlink_to(cache/'packages',target_is_directory=True)
        if (cache/'build').is_dir() and not (dest/'build').exists():
            shutil.copytree(cache/'build',dest/'build')


def run_lean_inputs(*,census,output,worked_cases=None,lean_root=Path('lean_born'),render_registered=True):
    start=time.monotonic();cpu=time.process_time();output=validate_output(output,Path.cwd())
    with exclusive_output(output):
        # Check the entire cohort before deciding formal applicability. Never
        # truncate to 120 or substitute a new Fin count in the proof inputs.
        inventory_seal=Path(census)/'inventory_complete.json'
        full_cohort=inventory_seal.is_file() and read(inventory_seal)['summary']['selected_count']==2122
        if worked_cases is None and not full_cohort:
            raise ValueError('historical eight-module rendering requires worked_cases')
        worked=checked_worked(worked_cases) if worked_cases is not None else None
        if full_cohort:
            records,pairs=full_census_records(census)
        else:
            records,pairs=census_records(census,expected_count=None,registered=False)
        modules={};matches={}
        if full_cohort:
            modules={f'Census/Shard{s:03d}':full_shard_text(records[start:start+8],s)
                     for s,start in enumerate(range(0,len(records),8))}
            modules['Census/FullInputs']=full_cohort_inputs_text(records)
        elif render_registered and len(records)==120:
            try:
                candidate=input_texts(records,pairs,*worked)
            except ValueError:
                # The registered atom-selector hypotheses need not hold on
                # other data; their absence is a formal-coverage limit.
                candidate={}
            matches={name:(Path(lean_root)/'BornCalculus'/(name+'.lean')).read_bytes()==text.encode()
                     for name,text in candidate.items()}
            if candidate and all(matches.values()):
                modules=candidate
        coverage={'schema':'born_cohort_formal_coverage_v1','census_cases':len(records),
                  'exact_certificate_cases_checked':len(records),'worked_certificates_checked':worked is not None,
                  'registered_ordered_inputs_match':bool(modules) and not full_cohort,
                  'full_cohort_inputs':full_cohort,
                  'status':'APPLICABLE' if modules else 'NOT_APPLICABLE',
                  'scope':('full 2122-case sharded census proof inputs' if full_cohort else
                           'registered eight-module proof inputs' if modules else 'not applicable to this cohort'),
                  'reason':None if modules else 'formal coverage requires the complete 2,122-case census, or enabled historical rendering with byte-identical registered ordered 120-case inputs; neither applies to this cohort',
                  'registered_gap_bound_satisfied':all(Q(p['gap_exact'])>=Q(3,20) for p in pairs) if pairs else None}
        if full_cohort:
            coverage['required_build_targets']=['BornCalculus.Census.FullWitness','BornCalculus.Census.AuditFull']
            coverage['exact_certificate_scope']='source frame, lexicographic witness, atoms and maximal point pairs'
            coverage['registered_gap_bound_failures']=sum(Q(p['gap_exact'])<Q(3,20) for p in pairs)
            coverage['committed_census_inputs_byte_identical']=all(
                (Path(lean_root)/'BornCalculus'/(name+'.lean')).is_file() and
                (Path(lean_root)/'BornCalculus'/(name+'.lean')).read_bytes()==text.encode()
                for name,text in modules.items())
        coverage_path=output/'formal_coverage.json'
        if coverage_path.exists():
            # Applicability is immutable scientific input metadata; explanatory
            # wording, build and reference-byte evidence may change on resume.
            operational={'reason','build_status','build_receipt','audit_receipt','committed_census_inputs_byte_identical'}
            before={k:v for k,v in read(coverage_path).items() if k not in operational}
            after={k:v for k,v in coverage.items() if k not in operational}
            if before!=after:raise ValueError('formal coverage inputs changed on resume')
            coverage_path.write_text(json.dumps(coverage,indent=2,sort_keys=True)+'\n')
        else:
            write(coverage_path,coverage)
        if not modules:
            summary={**coverage,'modules':[],
                     'wall_seconds':time.monotonic()-start,'cpu_seconds':time.process_time()-cpu,
                     'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
            attempt=len(list(output.glob('render_cost_*.json')))+1
            write(output/f'render_cost_{attempt:04d}.json',summary)
            return summary
        for name,text in modules.items():
            existing=output/'BornCalculus'/(name+'.lean')
            if existing.exists() and existing.read_bytes()!=text.encode():
                raise ValueError('rendered Lean data differs on resume: '+name)
        if full_cohort:
            project_sources(lean_root,output,include_registered_inputs=True,regenerate_full_census=True)
        else:
            project_sources(lean_root,output)
        sizes={};matches={}
        for name,text in modules.items():
            path=output/'BornCalculus'/(name+'.lean');blob=text.encode()
            if path.exists() and path.read_bytes()!=blob:raise ValueError('rendered Lean data differs on resume: '+name)
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(blob);sizes[name]=len(blob)
            reference=Path(lean_root)/'BornCalculus'/(name+'.lean')
            matches[name]=reference.is_file() and reference.read_bytes()==blob
        if full_cohort:
            assert coverage['committed_census_inputs_byte_identical']==all(matches.values())
            minimum=min(Q(p['gap_exact']) for p in pairs)
            write(output/'BornCalculus/Census/input_manifest.json',{
                'schema':'born_full_census_lean_shards_v1','cases':len(records),
                'source_cases_checked':len(pairs),'shard_size':8,
                'module_bytes':{name.rsplit('/',1)[1]:size for name,size in sizes.items()
                                if name.startswith('Census/Shard')},
                'ordered_unit_ids':[r['unit_id'] for r in records],
                'registered_3_over_20_failures':sum(Q(p['gap_exact'])<Q(3,20) for p in pairs),
                'minimum_cases':[p['case'] for p in pairs if Q(p['gap_exact'])==minimum],
                'minimum_gap_exact':str(minimum)})
        summary={'schema':'born_full_census_lean_inputs_v1' if full_cohort else 'born_eight_lean_inputs_v1',
                 'modules':list(modules),'module_bytes':sizes,
                 'committed_byte_equality':matches,'all_eight_byte_equal':all(matches.values()) if not full_cohort else None,
                 'all_rendered_byte_equal':all(matches.values()),
                 'formal_coverage':coverage,
                 'wall_seconds':time.monotonic()-start,'cpu_seconds':time.process_time()-cpu,
                 'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
        attempt=len(list(output.glob('render_cost_*.json')))+1;write(output/f'render_cost_{attempt:04d}.json',summary)
    return summary
