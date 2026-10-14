#!/usr/bin/env python3
"""Maintainer migration: explicit ledger/aliases in, public selectors out.

Readers need only the committed output; no ledger is loaded by paper-numbers.
Run from the checkout with the installed public package.
"""
import argparse
import json
from pathlib import Path
import re

from born_ladder.reproduction.full_comparison import automatic_paper_binding,manuscript_macros
from born_ladder.reproduction.paper_numbers import declarations,setting_value


def explicit_binding(binding):
    row={k:v for k,v in binding.items() if k!='macro'}
    source=row.pop('expression',None)
    if source:
        field=source.split('#',1)[1].split(';',1)[0].strip()
        pointer=field.split(' [',1)[0]
        if row.get('public_spec'):
            match=re.fullmatch(r'(.+)/items\[id=([^]]+)\](.*)',pointer)
            row['selection']=({'pointer':match[1]+'/items','id':match[2],'value_pointer':match[3]}
                              if match else {'pointer':pointer,'operation':'identity_count' if '[SeedCount]' in field else 'identity'})
        elif '[length]' in field:row['aggregate']={'operation':'length','pointer':pointer}
        elif '[object key]' in field:
            parent,key=pointer.rsplit('/',1);row['aggregate']={'operation':'object_key','pointer':parent,'key':key}
        else:row['pointer']=pointer
    return row


def literal(file,pattern,*,section=None,transform=None):
    return {'kind':'literal','file':file,'pattern':pattern,**({'section':section} if section else {}),**({'transform':transform} if transform else {})}


def setting_bindings():
    runner='vendor/pica/crates/runner/src/main.rs';spectral='vendor/pica/crates/dynamics/src/spectral.rs'
    body=['fn run_exp_100_single(', '\nfn '];numeric=r'([0-9.eE_+-]+)'
    result={}
    for name,key in [('TrajectoryWeight','p_traj'),('RewriteWeight','p_p1'),('GateWeight','p_p2'),('LensWeight','p_p4'),('PackagingWeight','p_p5'),('BudgetWeight','p_p6'),('RunProtocolCycle','protocol_cycle_len'),('RunClusters','n_clusters'),('RewriteStrength','p1_strength'),('TauAlpha','tau_alpha')]:
        result[name]=literal(runner,r'\b'+key+r':\s*'+numeric+r'\s*,',section=body)
    for name,key in [('RunHorizon','total_steps'),('RunObservation','obs_interval')]:
        result[name]=literal(runner,r'\b'+key+r':\s*n\s*\*\s*'+numeric,section=body)
    result['RunBudgetRate']=literal(runner,r'budget_rate:\s*ln_n\s*\*\s*'+numeric,section=body)
    result['EntropyFloorFraction']=literal(runner,r'min_row_entropy:\s*'+numeric+r'\s*\*\s*ln_n',section=body)
    result.update({
        'InitialWeightFloor':literal('vendor/pica/crates/six_primitives_core/src/substrate.rs',r'rng\.gen::<f64>\(\)\s*\+\s*'+numeric,section=['pub fn random(', '\n    pub fn ']),
        'CostCutoff':literal('vendor/pica/crates/dynamics/src/drive.rs',r'if [pq] >\s*'+numeric),
        'CostPenalty':literal('vendor/pica/crates/dynamics/src/drive.rs',r'cost \+= p \*\s*'+numeric),
        'StationaryTolerance':literal(spectral,r'kernel\.stationary\(10000,\s*'+numeric+r'\)'),
        'StationaryMaxIterations':literal(spectral,r'kernel\.stationary\('+numeric+r',\s*1e-12\)'),
        'FallbackThreshold':literal(spectral,r'if pi\[i\] >\s*'+numeric),
        'GoldenStep':literal(spectral,r'let phi =\s*'+numeric),
        'StartOffset':literal(spectral,r'i as f64 \* phi \+\s*'+numeric),
        'FallbackMaxIterations':literal(spectral,r'for _ in 0\.\.([0-9]+) \{',section=['pub fn top_eigenvectors(', '\npub fn ']),
        'NormFloor':literal(spectral,r'if (?:norm|new_norm) <\s*'+numeric),
        'RowMassFloor':literal('vendor/pica/crates/dynamics/src/pica/p5_cells.rs',r'if row_sum >\s*'+numeric),
        'TauCap':literal('vendor/pica/crates/dynamics/src/observe.rs',r'\.floor\(\)\.min\('+numeric+r'\)'),
        'GapFloor':literal('vendor/pica/crates/dynamics/src/observe.rs',r'if gap <=\s*'+numeric),
        'SeedOffset':literal(runner,r'seed \+\s*'+numeric+r'\s*\+ idx as u64'),
        'JacobiRotationFactor':literal(spectral,r'for _ in 0\.\.([0-9]+) \* n \* n'),
        'JacobiTolerance':literal(spectral,r'if max_val <\s*'+numeric),
        'LagTolerance':literal('vendor/pica/crates/dynamics/src/pica/p3_cells.rs',r'if d1 >\s*'+numeric),
        'LensHysteresis':literal('vendor/pica/crates/dynamics/src/pica/lens_cells.rs',r'\(current_score - best_score\) / current_score >\s*'+numeric),
        'UnitRoundoff':literal('src/born_ladder/certificates.py',r'\bu=Q\(1,2\*\*([0-9]+)\)',transform='inverse_power_two'),
        'SmallestSubnormal':literal('src/born_ladder/certificates.py',r'\beta=Q\(1,2\*\*([0-9]+)\)',transform='inverse_power_two'),
        'EnvelopeSumIndex':literal('src/born_ladder/certificates.py',r'eps=.*?gamma\(([0-9]+)\)'),
        'EnvelopeMassIndex':literal('src/born_ladder/certificates.py',r'envelope=.*?gamma\(([0-9]+)\)'),
        'EnvelopeDotUnderflow':literal('src/born_ladder/certificates.py',r'\+([0-9]+)\*eta;normlo'),
        'EnvelopeMassUnderflow':literal('src/born_ladder/certificates.py',r'\+([0-9]+)\*eta/'),
        'TieThreshold':literal('src/born_ladder/snapshot/g2c_controls.py',r'"tie":\s*'+numeric),
        'NondegeneracyThreshold':literal('src/born_ladder/snapshot/g2c_controls.py',r'"coefficient":\s*'+numeric),
        'CalibrationReadings':literal(
            'vendor/pica/crates/runner/src/test_b_sidecar.rs',
            r'for _ in 0\.\.([0-9]+)\s*\{\s*states\.push\(v6_start\(',
            section=['fn write_v6_contexts(', '\nfn '],
        ),
        'ProbabilityFloor':literal('src/born_ladder/record_tests/scorer.py',r'^FLOOR =\s*'+numeric),
    })
    prefix='/scientific/acquisition/seed_design/campaigns/'
    for name,paths in [('CorrCrossSeedBase',[prefix+'cross-term/base']),('CorrCompSeedBase',[prefix+'competitor/base']),('CorrSeedSpacing',[prefix+'cross-term/spacing',prefix+'competitor/spacing'])]:
        result[name]={'kind':'json','file':'specifications/predictive_v25.json','pointers':paths}
    return result


def generate(ledger,aliases,paper):
    entries={e['id']:e for e in ledger['entries']};used,_=manuscript_macros(paper,{a['macro']:a for a in aliases})
    settings=setting_bindings();rows=[];declared=declarations(Path(paper).read_text())
    for alias in aliases:
        name=alias['macro']
        if name not in used:continue
        entry=entries[alias['id']];binding=automatic_paper_binding(entry,name)
        direction=alias.get('direction') or entry.get('rounding_direction') or ('lower' if 'outward lower' in entry.get('rounding_rule','') else 'upper' if 'outward upper' in entry.get('rounding_rule','') else None)
        row={'macro':name,'class':'regenerated' if binding else 'setting','format':alias['format'],'direction':direction,
             'binding':explicit_binding(binding) if binding else settings[name]}
        if not binding:
            # Confirm migration chose the actual public setting, not a stale
            # private source line. Expected values are not saved in the map.
            from fractions import Fraction
            try:actual,_=setting_value(row['binding'],Path.cwd())
            except ValueError as error:raise ValueError(name+': '+str(error)) from error
            if Fraction(actual)!=Fraction(str(entry['value'])):raise ValueError('setting migration differs: '+name)
        rows.append(row)
    non_numerical={'MarkManuscriptCitation','qedsymbol','X','simplex','ones','States','Effects','rec','dTV','fraw','fpkg','fjnt','test','prog','arraystretch','tr','Sym','FigArchitecture','FigCardItem','FigEncoderCircle','FigThreeDescriptions','RepositoryURL','ReleaseTag','thetable','caption@documentclass','ManuscriptHasCitations','EncoderTMin','EncoderTMax','EncoderArcStart','EncoderArcEnd','px','pz','labelvalue','witnessvalue','shape','zerox','zeroz','twox','twoz','DraftBuildDate','lastrow'}
    for name,record in declared.items():
        if name not in used:
            if name not in non_numerical:raise ValueError('new macro needs explicit classification: '+name)
            rows.append({'macro':name,'class':'non_numerical',
                'source':'manuscript symbol, layout, figure, citation or release metadata command; result-macro references are checked; coordinates and literal figure labels are not'})
    return {'schema':'born_public_paper_numbers_v1','generated_by':'tools/generate_paper_number_map.py',
            'scope':'used result macros; explicit public selectors and display rules, no expected result values',
            'macros':rows}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('ledger','aliases','paper','output'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();value=generate(json.loads(args.ledger.read_text()),json.loads(args.aliases.read_text()),args.paper)
    args.output.write_text(json.dumps(value,indent=2)+'\n')


if __name__=='__main__':main()
