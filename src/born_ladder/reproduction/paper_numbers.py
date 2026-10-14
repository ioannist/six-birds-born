"""Archive-free paper displays from a completed public reproduction.

The committed map contains selectors and formatting, never expected result
values. The comparison adapter supplies the same extraction and rendering.
"""
from collections import Counter
from fractions import Fraction
import gc
import json
from pathlib import Path
import re
import time

from born_ladder.archive import sha
from . import full_comparison as F
from .runs import validate_output, exclusive_output


def declarations(text):
    """Inventory literal custom command definitions, independent of the map."""
    clean=re.sub(r'(?<!\\)%[^\n]*','',text)
    result={}
    pattern=r'\\(?:newcommand|renewcommand|providecommand|DeclareRobustCommand|DeclareMathOperator|pgfmathsetmacro|pgfmathtruncatemacro|def|gdef|edef|xdef)\*?\s*(?:\{\s*\\([A-Za-z@]+)\s*\}|\\([A-Za-z@]+))'
    for match in re.finditer(pattern,clean):
        name=match[1] or match[2];at=match.end();parameters=[]
        while at<len(clean) and clean[at].isspace():at+=1
        while at<len(clean) and clean[at]=='[':
            end=clean.index(']',at);parameters.append(clean[at+1:end]);at=end+1
            while at<len(clean) and clean[at].isspace():at+=1
        if at>=len(clean) or clean[at]!='{':raise ValueError('unparseable macro: '+name)
        start=at+1;depth=1;at+=1
        while at<len(clean) and depth:
            if clean[at]=='\\':at+=2;continue
            if clean[at]=='{':depth+=1
            elif clean[at]=='}':depth-=1
            at+=1
        if depth:raise ValueError('unbalanced macro: '+name)
        result.setdefault(name,[]).append({'definition':clean[start:at-1],'parameters':parameters})
    # Extended/alias definitions need an explicit parser before they can be
    # accounted for; they cannot introduce a silently skipped numerical macro.
    if re.search(r'\\(?:let|chardef|mathchardef|countdef|dimendef|skipdef|muskipdef|toksdef|font)\s*\\',clean):
        raise ValueError('unsupported primitive macro definition')
    if re.search(r'\\(?:NewDocumentCommand|RenewDocumentCommand|ProvideDocumentCommand|DeclareDocumentCommand|NewExpandableDocumentCommand|RenewExpandableDocumentCommand)',clean):
        raise ValueError('unsupported extended macro definition; coverage cannot be established')
    return result


def classify(paper,number_map):
    if number_map.get('schema')!='born_public_paper_numbers_v1':raise ValueError('unsupported paper number map')
    rows=number_map['macros'];by={r['macro']:r for r in rows}
    if len(by)!=len(rows):raise ValueError('duplicate paper number map entry')
    text=Path(paper).read_text();declared=declarations(text)
    begin='% >>> BEGIN GENERATED RESULT MACROS';end='% <<< END GENERATED RESULT MACROS'
    if text.count(begin)!=1 or text.count(end)!=1:raise ValueError('manuscript result marker pair missing')
    results=declarations(text[text.index(begin):text.index(end)])
    invalid=sorted(name for name in results if by.get(name,{}).get('class') not in ('regenerated','setting'))
    if invalid:raise ValueError('result macro missing or downgraded in paper number map: '+', '.join(invalid))
    missing=set(declared)-set(by);extra=set(by)-set(declared)
    if missing or extra:raise ValueError('paper number map coverage differs: missing '+str(sorted(missing))+'; extra '+str(sorted(extra)))
    numerical={k:r for k,r in by.items() if r['class'] in ('regenerated','setting')}
    used,definitions=F.manuscript_macros(paper,numerical)
    result=[]
    for name,record in declared.items():
        row=by[name]
        if row['class']=='non_numerical':
            if not row.get('source'):raise ValueError('non-numerical macro needs a named source/disposition: '+name)
        elif row['class'] not in ('regenerated','setting'):raise ValueError('unknown paper number class: '+name)
        elif name not in used:raise ValueError('unused numerical map entry: '+name)
        elif len(record)!=1 or record[0]['parameters']:raise ValueError('number macro needs one zero-argument definition: '+name)
        elif not row.get('binding') or not row.get('format'):raise ValueError('missing number extractor/format: '+name)
        if row.get('direction') not in (None,'lower','upper'):raise ValueError('unsupported rounding direction: '+name)
        result.append(row)
    return result,definitions


def setting_value(binding,repository):
    """Check literal public settings; no execution or ledger-source parsing."""
    path=Path(binding['file'])
    if path.is_absolute() or '..' in path.parts:raise ValueError('setting source must be a public relative path')
    path=Path(repository)/path
    if binding['kind']=='json':
        values=[F.pointer(F.read(path),p) for p in binding['pointers']]
    elif binding['kind']=='literal':
        text=path.read_text()
        if 'section' in binding:
            head,tail=binding['section'];parts=text.split(head)
            if len(parts)!=2:raise ValueError('no unique public setting section')
            text=parts[1].split(tail,1)[0]
        values=re.findall(binding['pattern'],text,re.M)
    else:raise ValueError('unsupported setting extractor')
    if not values:raise ValueError('public setting not found: '+str(path))
    values=[Fraction(str(v).replace('_','')) for v in values]
    if len(set(values))!=1:raise ValueError('public setting sources disagree: '+str(path))
    value=values[0]
    if binding.get('transform')=='inverse_power_two':
        if value.denominator!=1:raise ValueError('noninteger power exponent')
        value=Fraction(1,2**value.numerator)
    elif binding.get('transform'):raise ValueError('unsupported setting transform')
    return str(value),{'sources':[str(path)],'sha256':sha(path),'selector':binding,
                       'aggregation':'literal public setting; all matched occurrences agree'}


class RunPopulations(dict):
    """Load each committed population once; do not retain saved bootstrap draws."""
    def __init__(self,root,components):super().__init__();self.root=root;self.components=components
    def __missing__(self,key):
        if key=='lean_audit':value=F.read(self.root/self.components['lean']/'audit_receipt.json')
        else:
            from .census import verify_artifacts
            directory=self.root/self.components[key.replace('-','_')+'_evaluation']
            seal=F.read(directory/'complete.json');verify_artifacts(directory,seal['artifacts'])
            value=F.paper_projection(F.read(F.last_attempt(directory)/'evaluation.json'));gc.collect()
        self[key]=value;return value


def check_numbers(rows,definitions,extract):
    """Typed displays are strict strings; failures and missing values are explicit."""
    checks=[]
    for row in rows:
        name=row['macro'];record={'macro':name,'class':row['class']}
        if row['class']=='non_numerical':
            checks.append({**record,'source':row['source'],'match':True,'status':'NON_NUMERICAL'});continue
        record['typeset_value']=definitions[name]
        try:
            value,source=extract(row)
            displayed=F.render(value,row['format'],row.get('direction'))
            record.update(regenerated_value=displayed,full_precision_value=value,source=source,
                          match=displayed==definitions[name],status='MATCH' if displayed==definitions[name] else 'MISMATCH')
        except (KeyError,ValueError,FileNotFoundError,TypeError) as error:
            record.update(match=False,status='NOT_REGENERATED',reason=str(error))
        checks.append(record)
    return checks


def run_paper_numbers(*,run,output,v25_output=None,paper='paper/main.tex',number_map='specifications/paper_numbers.json',specifications='specifications'):
    start=time.monotonic();root=Path(run).resolve(strict=True)
    out=validate_output(output,Path.cwd());out.mkdir(parents=True,exist_ok=True)
    for source in (root,Path(v25_output).resolve() if v25_output is not None else None):
        if source is not None and (out.is_relative_to(source) or source.is_relative_to(out)):
            raise ValueError('paper-number output must be separate from its input trees')
    with exclusive_output(out):
        report={'schema':'born_paper_numbers_report_v1','run':str(root),'v25_output':str(v25_output) if v25_output is not None else None,
                'paper':str(Path(paper).resolve()),'number_map':str(Path(number_map).resolve()),
                'scope':'literal result macros; fixed settings separately checked; figure coordinates and literal labels are outside this check'}
        try:
            rows,definitions=classify(paper,F.read(number_map))
            pipeline=F.read(root/'pipeline.json');verification=F.read(root/'verification_report.json')
            if pipeline.get('profile')!='full' or verification.get('profile')!='full' or verification.get('status')!='COMPLETE':
                raise ValueError('paper numbers require a completed full-profile run; smoke is nonconfirmatory')
            from .regenerated_bundle import GROUPS
            if set(verification['checks'])!=set(GROUPS) or any(r.get('status')!='VERIFIED' or r.get('claim_ids')!=list(GROUPS[k])
                    or set(r.get('claim_receipts',{}))!=set(GROUPS[k]) for k,r in verification['checks'].items()):
                raise ValueError('run contains incomplete regenerated verification')
            components=pipeline['components']
            if any(Path(p).is_absolute() or '..' in Path(p).parts or not (root/p).resolve().is_relative_to(root) for p in components.values()):
                raise ValueError('pipeline component escapes run')
            from .v25_paper import comparison_preflight
            comparison_preflight()
            if any(r.get('binding',{}).get('view') in ('canonical_census','v25_selected') for r in rows):
                from .stage_environment import preflight_environment
                preflight_environment('predictive_v25',specifications)
            populations=RunPopulations(root,components);views={};evidence={}
            def extract(row):
                if row['class']=='setting':return setting_value(row['binding'],Path.cwd())
                if row['binding'].get('view') in ('v25','v25_selected') and v25_output is None:
                    raise ValueError('not regenerated: supply --v25-output from reproduce v25')
                return F.extract_paper_quantity(row['binding'],row['macro'],root,components,populations,views,evidence,
                                               specifications=specifications,v25=v25_output)
            checks=check_numbers(rows,definitions,extract)
            report.update(checks=checks,regenerated_evidence=evidence,
                paper_sha256=sha(paper),number_map_sha256=sha(number_map),
                class_counts=dict(Counter(r['class'] for r in rows)),
                regenerated_total=sum(r['class']=='regenerated' for r in checks),
                regenerated_matched=sum(r['class']=='regenerated' and r['match'] for r in checks),
                setting_matched=sum(r['class']=='setting' and r['match'] for r in checks),
                status='PASS' if all(r['match'] for r in checks) else 'FAIL')
        except (KeyError,ValueError,FileNotFoundError) as error:
            report.update(status='FAIL',error=str(error),checks=[],regenerated_matched=0,regenerated_total=0)
        report['wall_seconds']=time.monotonic()-start
        report['summary']=str(report['regenerated_matched'])+'/'+str(report['regenerated_total'])+' paper numbers reproduced'
        if report['status']!='PASS':report['summary']+='; FAIL (see report.json)'
        (out/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        lines=['# Paper-number check','',report['summary'],'']
        for title,kind in (('Results','regenerated'),('Settings and arithmetic constants','setting'),
                           ('Non-numerical macros','non_numerical')):
            rows_in_class=[row for row in report['checks'] if row['class']==kind]
            if not rows_in_class:continue
            lines+=['## '+title,'',
                    '| Macro | Typeset value | Regenerated value | Full-precision value | Match |',
                    '|---|---|---|---|---|']
            for row in rows_in_class:
                clean=lambda value:str(value).replace('|',r'\|').replace('\n',' ')
                lines.append('| '+ ' | '.join(clean(row.get(k,'')) for k in ('macro','typeset_value','regenerated_value','full_precision_value','status'))+' |')
                if row.get('reason'):lines.append('\n'+row['macro']+': '+row['reason']+'\n')
            lines.append('')
        if report.get('error'):lines+=['',report['error']]
        (out/'report.md').write_text('\n'.join(lines)+'\n')
        return report
