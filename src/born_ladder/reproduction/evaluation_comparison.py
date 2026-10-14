"""Optional exact comparison after inference; never a production input."""
import json
import math
import struct
from collections import defaultdict
from pathlib import Path
from born_ladder.archive import sha

# Launch receipts and archive packaging are not population computations. The
# archived cross-term close-out wrapper adds these to evaluate_g2c_records.
WRAPPER_FIELDS={'provenance','completeness','archive_binding','closeout_protocol',
                'artifact','claim_slots','package_evidence_census'}


def compare_values(left,right):
    groups=defaultdict(lambda:{'compared':0,'exact':0,'floats':0,'floats_exact':0,
        'maximum_absolute_difference':0.0,'structural_mismatches':0,'first_differences':[]})
    def walk(a,b,path,group):
        row=groups[group]
        if isinstance(a,dict) and isinstance(b,dict):
            if set(a)!=set(b):
                row['structural_mismatches']+=1
                if len(row['first_differences'])<10:
                    row['first_differences'].append({'path':path,'missing':sorted(set(b)-set(a)),
                                                    'extra':sorted(set(a)-set(b))})
            for key in sorted(set(a)&set(b)):
                # Give each endpoint its own group; keep its complete
                # bootstrap, jackknife, sensitivities and RNG audit together.
                next_group=key if path in ('','/statistics') else group
                walk(a[key],b[key],path+'/'+key,next_group)
            return
        if isinstance(a,list) and isinstance(b,list):
            if len(a)!=len(b):row['structural_mismatches']+=1
            for index,(x,y) in enumerate(zip(a,b)):walk(x,y,path+'/'+str(index),group)
            return
        equal=type(a)==type(b) and a==b
        if type(a) is float and type(b) is float:
            if not math.isfinite(a) or not math.isfinite(b):raise ValueError('nonfinite comparison operand')
            equal=struct.pack('!d',a)==struct.pack('!d',b)
            row['floats']+=1;row['floats_exact']+=int(equal)
            row['maximum_absolute_difference']=max(row['maximum_absolute_difference'],abs(a-b))
        row['compared']+=1;row['exact']+=int(equal)
        if not equal and len(row['first_differences'])<10:
            row['first_differences'].append({'path':path,'generated':a,'reference':b})
    walk(left,right,'','metadata')
    return {'field_groups':dict(groups),'overall_agreement':all(
        r['compared']==r['exact'] and not r['structural_mismatches'] for r in groups.values())}


def compare_evaluation(generated, reference, *, comparison=None):
    generated,reference=Path(generated),Path(reference)
    with generated.open() as stream:a=json.load(stream)
    with reference.open() as stream:b=json.load(stream)
    a={k:v for k,v in a.items() if k not in WRAPPER_FIELDS}
    b={k:v for k,v in b.items() if k not in WRAPPER_FIELDS}
    result=compare_values(a,b)
    if comparison is not None:
        comparison.compare("population",a,b)
        result["p8_assessment"]=comparison.result()
    result.update({'generated_sha256':sha(generated),'reference_sha256':sha(reference),
        'excluded_wrapper_fields':sorted(WRAPPER_FIELDS),
        'criteria':'complete ordered arrays, exact JSON types and binary64 bytes; no tolerance acceptance'})
    return result
