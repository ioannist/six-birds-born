"""Digest/location and documentary differences never mask scientific changes."""
import io
import json
import math

import pytest
from born_ladder.archive import sha
from born_ladder.reproduction.comparison_policy import PolicyComparison
from born_ladder.reproduction.full_comparison import compare_file
from born_ladder.reproduction.comparison_bindings import documentary


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data))


@pytest.mark.parametrize('kind',['checkpoint','prediction','manifest'])
@pytest.mark.parametrize('mutation',[None,'value','float-bit','extra-key','false-digest'])
def test_bound_digests_compare_strict_content_after_named_projection(tmp_path,kind,mutation):
    documents=[];roots=[tmp_path/'new',tmp_path/'old'];files=[]
    for i,root in enumerate(roots):
        if kind=='checkpoint':
            name='controls/full_relabel_refits/case.json';container=root/'controls/relabeling_literal.json'
            payload={'wall_seconds':100+i,'error':0.125};field='checkpoint_sha256'
        elif kind=='prediction':
            name='fits/original/case/predictions.json.seal.json';container=root/'fits/original/case/result.json'
            payload={'path':str(root/'fits/original/case/predictions.json'),'bytes':7,'sha256':'numeric commitment','error':0.125};field='files'
        else:
            name='record_view/manifest.json';container=root/'controls/allowlist.json'
            payload={'path':str(root/'record_view'),'allowed_files':['case'],'error':0.125};field=None
        if i==0:
            if mutation=='value':payload['error']=.25
            elif mutation=='float-bit':payload['error']=math.nextafter(.125,math.inf)
            elif mutation=='extra-key':payload['unexpected']=True
        target=root/name;write(target,payload);digest=sha(target)
        if mutation=='false-digest' and i==0:digest='bad local commitment'
        document={field:{name:digest}} if field else {'manifest_sha256':digest}
        write(container,document);files.append(container)
    c=PolicyComparison(io.StringIO())
    if mutation=='false-digest':
        with pytest.raises(ValueError,match='recorded digest'):compare_file(c,'fits_selectors_predictions_margins',*files)
    else:
        compare_file(c,'fits_selectors_predictions_margins',*files)
        assert c.result()['overall_agreement']==(mutation is None)


def test_locked_documentary_keys_have_named_dispositions_not_matches(tmp_path):
    old={'status':'NOT_COMPUTED','manager_approval':True,'manager_ruling':'retained','spec_quote':'quote','spec_reference':'section'}
    new={'status':'NOT_COMPUTED'}
    files=[tmp_path/'new/verdict.json',tmp_path/'old/verdict.json']
    for path,row in zip(files,(new,old)):write(path,{'descriptive_controls':{'erasure':row}})
    c=PolicyComparison(io.StringIO());compare_file(c,'locked_scoring_and_verdict',*files)
    assert c.result()['overall_agreement']
    assert len(c.documentary_fields)==4 and all(r['historical_matches']==0 for r in c.documentary_fields)
    write(files[0],{'descriptive_controls':{'erasure':{**new,'unexpected_scientific':1}}})
    c=PolicyComparison(io.StringIO());compare_file(c,'locked_scoring_and_verdict',*files)
    assert not c.result()['overall_agreement']


def test_prediction_control_approval_is_named_but_rules_remain_scientific():
    c=PolicyComparison(io.StringIO())
    a,b=documentary(c,{'tolerance':1e-9},{'tolerance':1e-9,'manager_approval':True},
                    {'manager_approval'},'control_rules')
    c.compare('control_rules',a,b)
    assert c.result()['overall_agreement'] and c.documentary_fields[0]['historical_matches']==0
    c.compare('control_rules',{'tolerance':1.},b)
    assert not c.result()['overall_agreement']
