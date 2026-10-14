"""Paper quantities from this run's committed census and attachment records.

Ledger paths are provenance, never inputs here. Canonical scoring runs in the
public predictive_v25 environment, with the registered rounding contract.
"""
from collections import Counter
from fractions import Fraction as Q
import hashlib
import json
import math
from pathlib import Path
import re

from born_ladder.summaries import quantiles, summarise
from .census_extension import atom_classes, diagnostic_counts, robust_outcomes


CENSUS_NAMES=set('StateCount CensusCases WitnessCount ArchiveCases RankTwoCases RankThreeCases RankFourCases RankFiveCases RankSixCases ActiveAtoms PositiveAtoms SingularAtoms SingularCases SmallestGap LargestGap LabelMaps NumericalPass RegisteredPass OriginalPass OriginalFail OriginalNumericalPass OriginalSymbolicPass CompletedSymbolicPass OriginalNumericalFail OriginalSymbolicFail BitPass BitFail OriginalFailBoth OriginalSymbolicOnlyFail SingularSingletons SingularNonsingletons RegisteredRobustPass RegisteredRobustFail AmendedRobustPass AmendedRobustFail LexicographicNonzeroFirst LexicographicRoundedEqual RobustGapBound RegisteredRobustGapBound RobustGapMinimumLower RobustGapMinimumUpper SelectedCaseIndex'.split())
QUANTILE_NAMES={'Min':'min','LowerQuartile':'q1','Median':'median','UpperQuartile':'q3','Max':'max'}
MODELS={'Own':'L_full','Small':'q_lambda_1_16','Next':'q_lambda_1_8','Full':'q_full',
        'Clipped':'L_clipped_linear','Diag':'q_diag','HistDiag':'q_diag','Uniform':'L_uniform'}


def binding(entry,name):
    if entry.get('evidence_type')!='full_cohort_external_exact_check':return None
    if name in CENSUS_NAMES or re.fullmatch(r'Certificate(?:Projector|Fixed|Floating)(?:Min|Max)',name):
        return {'macro':name,'view':'census','file':'full_cohort','pointer':'/'+name}
    if name.startswith('ConfigCases'):
        import ast
        source=entry.get('source','')
        if '#configuration ' not in source:return None
        key=ast.literal_eval(source.split('#configuration ',1)[1])
        if type(key) is not tuple or len(key)!=2 or any(type(x) is not str for x in key):raise ValueError('invalid paper configuration identity')
        escape=lambda x:x.replace('~','~0').replace('/','~1')
        return {'macro':name,'view':'census','file':'configuration_counts','pointer':'/'+escape(key[0])+'/'+escape(key[1])}
    match=re.fullmatch(r'(CanonicalDiag|Own|Small|Next|Full|Clipped|HistDiag|Diag|Uniform)(Raw|Pkg)(Min|LowerQuartile|Median|UpperQuartile|Max)',name)
    if match:
        model,view,stat=match.groups()
        return {'macro':name,'view':'canonical_census' if model=='CanonicalDiag' else 'census_attachments',
                'map':'raw' if view=='Raw' else 'pkg','stat':QUANTILE_NAMES[stat],
                **({'model':MODELS[model]} if model!='CanonicalDiag' else {})}
    if name=='CensusAttachmentRows':return {'macro':name,'view':'census_attachments','pointer':'/rows'}
    return None


class Committed:
    def __init__(self, root):
        self.root=Path(root)
        self.seal=json.loads((self.root/'complete.json').read_bytes())
        if self.seal.get('status') not in (None,'PASS'):
            raise ValueError('paper inputs are not complete')
        self.bindings={item['path']:item for item in self.seal['artifacts']}
        if len(self.bindings)!=len(self.seal['artifacts']):raise ValueError('duplicate paper input binding')

    def read(self, relative):
        relative=Path(relative)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('paper input escapes committed root')
        path=self.root/relative
        if not path.resolve().is_relative_to(self.root.resolve()):raise ValueError('paper input symlink escapes root')
        binding=self.bindings[relative.as_posix()]
        data=path.read_bytes()
        if len(data)!=binding['bytes'] or hashlib.sha256(data).hexdigest()!=binding['sha256']:
            raise ValueError('committed paper input changed: '+str(path))
        return json.loads(data)


def census_quantities(root, *, worked=None, specifications='specifications'):
    source=Committed(root);root=source.root;summary=source.seal['summary']
    base=Path(summary['summary_directory']);inv=Path(summary['inventory_directory'])
    completed=source.read(base/'structural_completion_results.json')
    original=source.read(base/'original_implementation_results.json')
    inventory=source.read(inv/'INVENTORY.json')
    if not completed or [r['unit_id'] for r in completed]!=[r['unit_id'] for r in inventory] or [r['unit_id'] for r in completed]!=[r['unit_id'] for r in original]:
        raise ValueError('paper census table identities/order differ')
    if len({r['unit_id'] for r in completed})!=len(completed):raise ValueError('duplicate paper census identity')
    carrier=source.read(inv/'RETURN_CARRIER_INVENTORY.json')
    ranks=Counter(str(r['retained_rank']) for r in carrier['rows'])
    if dict(ranks)!=carrier['rank_counts'] or len(carrier['rows'])!=carrier['paired_unit_contexts']:
        raise ValueError('paper full collection rank inventory differs')
    n=len(completed)
    values={'CensusCases':n,'ArchiveCases':len(carrier['rows']),**{'Rank'+word+'Cases':ranks[str(rank)] for rank,word in enumerate(('Two','Three','Four','Five','Six'),2)}}
    counts=diagnostic_counts(original)
    for name,key in [('OriginalNumericalPass','original_numerical_pass'),('OriginalNumericalFail','original_numerical_fail'),
                     ('OriginalSymbolicPass','original_symbolic_pass'),('OriginalSymbolicFail','original_symbolic_fail'),
                     ('OriginalFailBoth','original_fail_both'),('OriginalSymbolicOnlyFail','original_symbolic_only_fail')]:values[name]=counts[key]
    values.update(OriginalPass=sum(r['status']=='PASS' for r in original),OriginalFail=sum(r['status']!='PASS' for r in original))
    totals=Counter();gaps=[];extrema={key:[] for key in ('Projector','Fixed','Floating')};sizes=set();maps=set()
    results=[];completion=[]
    for index,(entry,old) in enumerate(zip(completed,original,strict=True)):
        if entry['index']!=index:raise ValueError('paper census indices differ')
        directory=Path(entry['context_directory']);context=source.read(directory/'CONTEXT.json')
        cert=source.read(directory/'structural_completion_certificate.json');cs=cert['certificates'];cp=cs['C_premises'];co=cs['correspondence']
        if cert['index']!=index or cert['unit_id']!=entry['unit_id']:raise ValueError('paper certificate identity differs')
        native=source.read(directory/'original_implementation.json')
        if any(native[k]!=old[k] for k in ('status','C_premises','correspondence_status')):raise ValueError('paper native outcome table differs')
        sizes.add(len(context['born']['p_theory']));maps.add(len(context['lens']))
        classes=atom_classes(context,cert)
        if source.read(directory/'atom_classes.json')!=classes:raise ValueError('paper atom classes differ')
        singular=[a for a in classes['atoms'] if a['class']=='singular']
        totals.update(ActiveAtoms=len(classes['atoms']),PositiveAtoms=len(classes['atoms'])-len(singular),SingularAtoms=len(singular),
                      SingularCases=int(bool(singular)),SingularSingletons=sum(a['singleton'] for a in singular),
                      SingularNonsingletons=sum(not a['singleton'] for a in singular))
        readout=cs['strictness']['first_separating_readout'];gaps.append(abs(Q(readout['difference_exact'])))
        totals.update(WitnessCount=int(cs['strictness']['status']=='PASS'),NumericalPass=int(co['status']=='PASS'),
                      RegisteredPass=int(cert['overall_status']=='PASS'),CompletedSymbolicPass=int(cp['status']=='PASS'),
                      BitPass=int(co['constructor_literal_bit_equality_status']=='PASS'),
                      LexicographicNonzeroFirst=int(cs['strictness']['pair'][0]!=0),
                      LexicographicRoundedEqual=int(float(Q(readout['left_exact']))==float(Q(readout['right_exact']))))
        extrema['Projector'].append(Q(co['uniform_projector_TV_bound_exact']))
        extrema['Fixed'].append(Q(co['own_input_exact_source_vs_landed_maximum_error']))
        extrema['Floating'].append(Q(co['uniform_floating_envelope']['total_with_projector_TV_exact']))
        # These views serve scalar ledger aggregations, not complete-record
        # comparison; release bulky density and constructor-difference tables.
        results.append({'overall_status':old['status'],'certificates':{
            **{k:v for k,v in cs.items() if k not in ('strictness','C_premises','correspondence')},
            'C_premises':{k:v for k,v in cp.items() if k!='atom_certificates'},
            'strictness':{k:cs['strictness'][k] for k in ('status','pair','first_separating_readout')},
            'correspondence':{**{k:v for k,v in co.items() if k!='constructor_differences'},'status':old['correspondence_status']}}})
        completion.append({'overall_registered_claim_status':cert['overall_status'],'registered_numerical_gate_status':co['status'],
                           'C_premise_status':cp['status'],'original_C_premise_status':old['C_premises']['status'],
                           'literal_constructor_claim':co['constructor_literal_bit_equality_status'],
                           **{k:cp[k] for k in ('atom_count','strict_positive_atom_count','zero_atom_count')}})
    if len(sizes)!=1 or len(maps)!=1:raise ValueError('paper state/map dimensions are not uniform')
    values.update(totals);values.update(StateCount=sizes.pop(),LabelMaps=maps.pop(),BitFail=n-totals['BitPass'],SmallestGap=str(min(gaps)),LargestGap=str(max(gaps)))
    for name,series in extrema.items():
        values['Certificate'+name+'Min']=str(min(series));values['Certificate'+name+'Max']=str(max(series))
    pairs=source.read(base/'maximal_gap_witnesses.json');outcomes=robust_outcomes(pairs)
    if source.read(base/'robust_bound_outcomes.json')!=outcomes or len(pairs)!=n:raise ValueError('paper robust outcomes differ')
    minimum=Q(outcomes['minimum_maximum_gap_exact']);scale=10**7
    lower=Q(math.floor(minimum*scale),scale);upper=Q(math.ceil(minimum*scale),scale)
    values.update(RegisteredRobustPass=outcomes['registered_pass'],RegisteredRobustFail=outcomes['registered_fail'],
                  AmendedRobustPass=outcomes['amended_pass'],AmendedRobustFail=outcomes['amended_fail'],
                  RobustGapBound=outcomes['amended_bound_exact'],RobustGapMinimumLower=str(lower),RobustGapMinimumUpper=str(upper))
    spec=Path(specifications)/'census.json';protocol=json.loads(spec.read_bytes())
    bound=re.search(r'Check (\d+/\d+)',protocol['maximal_gap_witness'])
    if bound is None:raise ValueError('registered robust bound is not declared in census specification')
    values['RegisteredRobustGapBound']=str(Q(bound[1]))
    if worked is not None:
        identity=json.loads((Path(worked)/'selected/CONTEXT.json').read_bytes())['identity']
        key={'experiment':identity['exp'],'config_or_null':identity['config'],'seed':identity['seed'],
             'scale':identity['scale'],'resolution':identity['k'],'step':identity['step_index']}
        selected=[i for i,row in enumerate(inventory) if all(row['provenance_key'][k]==v for k,v in key.items())]
        if len(selected)!=1:raise ValueError('selected paper fixture has no unique full-census join')
        values['SelectedCaseIndex']=selected[0]
    configurations={}
    for row in inventory:
        key=row['provenance_key'];experiment=key['experiment'];name=key['audit_metadata']['config_name']
        configs=configurations.setdefault(experiment,{});configs[name]=configs.get(name,0)+1
    provenance={'sources':[str(root/'complete.json'),str(root/inv/'INVENTORY.json'),str(root/inv/'RETURN_CARRIER_INVENTORY.json'),
                           str(root/base/'structural_completion_results.json'),str(root/base/'original_implementation_results.json'),
                           str(root/base/'maximal_gap_witnesses.json'),str(root/base/'robust_bound_outcomes.json')],
                'context_records':[str(root/r['context_directory']) for r in completed],
                'context_record_files':['CONTEXT.json','structural_completion_certificate.json','original_implementation.json','atom_classes.json'],
                'aggregation':'all ordered completed cases; typed status counts; exact atom classes; exact rational readout/correspondence extrema; registered maximal-gap outcomes',
                'specification':str(spec)}
    if worked is not None:provenance['selected_identity_source']=str(Path(worked)/'selected/CONTEXT.json')
    return {'full_cohort':values,'configuration_counts':configurations,'structural_results.json':results,
            'structural_completion_results.json':completion,'inventory':summary,
            'INVENTORY.json':[{**r,'audit_metadata':r['provenance_key']['audit_metadata']} for r in inventory],
            'robust':{'minimum_maximum_gap_exact':outcomes['minimum_maximum_gap_exact'],'bound_exact':outcomes['amended_bound_exact']},
            'provenance':provenance}


def attachment_quantities(root):
    source=Committed(root);directory=Path(source.seal['summary']['directory'])
    attached=source.read(directory/'attachments.json')
    keys=[(r['unit_id'],r['view']) for r in attached]
    if len(set(keys))!=len(keys):raise ValueError('duplicate paper attachment identity')
    raw={uid for uid,view in keys if view=='raw'};pkg={uid for uid,view in keys if view=='pkg'}
    if raw!=pkg or len(keys)!=2*len(raw):raise ValueError('paper attachment view membership differs')
    summaries=summarise(attached,len(raw))
    if source.read(directory/'descriptive_summaries.json')!=summaries:raise ValueError('paper attachment summaries differ from exact dyadic type-seven recomputation')
    return {'rows':len(attached),'records':summaries,
            'provenance':{'sources':[str(source.root/directory/'attachments.json'),str(source.root/directory/'descriptive_summaries.json')],
                          'aggregation':'born_ladder.summaries.summarise: registered eligibility, no structural filtering; exact dyadic type-seven quantiles'}}


def canonical_quantities(census,attachments,specifications):
    import numpy as np
    from .v25.canonical import construct
    from .stage_environment import check_current,profile_path
    runtime=check_current(json.loads(profile_path(specifications,'predictive_v25').read_bytes()))
    c=Committed(census);a=Committed(attachments)
    base=Path(c.seal['summary']['summary_directory']);rows=c.read(base/'structural_completion_results.json')
    directory=Path(a.seal['summary']['directory'])
    refinement=tuple(json.loads((Path(specifications)/'predictive_v25.json').read_bytes())['scientific']['canonical_diagonal']['rounding']['refinement_bits'])
    losses={'raw':[],'pkg':[]};sources=[str(Path(specifications)/'predictive_v25.json')];seen=set();certificates=[]
    for i,entry in enumerate(rows):
        uid=entry['unit_id']
        if uid in seen or entry['index']!=i:raise ValueError('canonical paper cohort identity/order differs')
        seen.add(uid);context=c.read(Path(entry['context_directory'])/'CONTEXT.json')
        cert=construct(context['born']['sym_eigvec_basis'],context['born']['p_theory'],refinement=refinement)
        if cert['status']!='certified' or cert['rank']!=2:raise ValueError('canonical paper construction is unresolved or not rank two')
        certificates.append({'unit_id':uid,'input_sha256':cert['input_sha256'],'bits':cert['bits']})
        sources.append(str(c.root/entry['context_directory']/'CONTEXT.json'))
        for view in losses:
            file=directory/'contexts'/uid/(view+'_original.jsonl');row=a.read(file)
            if row['unit_id']!=uid or row['total_count']!=sum(row['integer_counts']):raise ValueError('canonical paper attachment identity/counts differ')
            empirical=row['unrounded_y_raw' if view=='raw' else 'unrounded_y_pkg']
            if empirical!=[x/row['total_count'] for x in row['integer_counts']]:raise ValueError('canonical paper empirical law differs')
            matrix=row['M_raw_or_content_hash' if view=='raw' else 'M_pkg_or_content_hash']
            mapped=(np.asarray(matrix)@np.asarray(cert['q_diag_canonical'])).tolist()
            losses[view].append(.5*math.fsum(abs(x-y) for x,y in zip(mapped,empirical,strict=True)))
            sources.append(str(a.root/file))
        if i%100==0:
            import sys
            print('canonical paper context',i,flush=True,file=sys.stderr)
    return {'summaries':{view:quantiles(v) for view,v in losses.items()},
            'provenance':{'sources':sources,'aggregation':'all completed census cases, no status filtering; public v25 canonical.construct with registered refinement; binary64 NumPy M @ q; 0.5 * math.fsum(abs(mapped-empirical)); exact dyadic type-seven quantiles',
                          'runtime':runtime,'refinement_bits':list(refinement),'certificates':certificates}}
