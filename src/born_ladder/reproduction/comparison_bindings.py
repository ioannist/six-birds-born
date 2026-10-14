"""Strict scientific comparisons behind explicitly location/timing-bound digests."""
import hashlib
import json
from pathlib import Path


def component_root(path):
    for parent in Path(path).parents:
        if parent.name in ('fits','controls','record_view'):return parent.parent
    raise ValueError('cannot resolve committed Test B component: '+str(path))


def member(root,name):
    path=Path(name)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('digest member escapes component: '+name)
    result=Path(root)/path
    if not result.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('digest member symlink escapes component: '+name)
    return result


def bound_content(c,a,b,digests,*,exclude,path):
    """Check each local commitment first; compare all other bytes as typed JSON."""
    documents=[]
    for file,digest in zip((a,b),digests):
        raw=Path(file).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:
            raise ValueError('recorded digest differs from local file: '+str(file))
        document=json.loads(raw)
        if not isinstance(document,dict):raise ValueError('bound file must be a JSON object')
        documents.append({k:v for k,v in document.items() if k not in exclude})
    projection=c.projection;c.projection=False
    try:c.compare('digest_bound_scientific_content',*documents,path)
    finally:c.projection=projection
    if digests[0]!=digests[1]:
        c.record('declared_digest_projection',path,*digests,
                 'local digest bindings verified; strict decoded content compared; only '+', '.join(sorted(exclude))+' projected',True)


def file_bindings(c,a,b,x,y):
    """Only relabel checkpoints, prediction seal locations and allowlist manifest."""
    roots=None
    def roots_for_files():
        nonlocal roots
        if roots is None:roots=(component_root(a),component_root(b))
        return roots
    if a.name=='relabeling_literal.json':
        x,y=dict(x),dict(y)
        left,right=x.get('checkpoint_sha256',{}),y.get('checkpoint_sha256',{})
        c.compare('checkpoint_binding_membership',sorted(left),sorted(right),str(a))
        for name in sorted(set(left)&set(right)):
            if not name.startswith('controls/full_relabel_refits/') or not name.endswith('.json'):
                raise ValueError('unexpected relabel checkpoint member: '+name)
            ra,rb=roots_for_files()
            bound_content(c,member(ra,name),member(rb,name),(left[name],right[name]),
                          exclude={'wall_seconds'},path=str(a)+'/checkpoint_sha256/'+name)
        x.pop('checkpoint_sha256',None);y.pop('checkpoint_sha256',None)
    elif a.name=='result.json' and 'fits' in a.parts:
        x,y=dict(x),dict(y);left=dict(x.get('files',{}));right=dict(y.get('files',{}))
        c.compare('fit_binding_membership',sorted(left),sorted(right),str(a))
        for name in sorted(set(left)&set(right)):
            if not name.endswith('/predictions.json.seal.json'):continue
            ra,rb=roots_for_files()
            bound_content(c,member(ra,name),member(rb,name),(left[name],right[name]),
                          exclude={'path'},path=str(a)+'/files/'+name)
            left[name]=right[name]='verified scientific seal content'
        if 'files' in x:x['files']=left
        if 'files' in y:y['files']=right
    elif a.name=='allowlist.json' and 'manifest_sha256' in x and 'manifest_sha256' in y:
        x,y=dict(x),dict(y);ra,rb=roots_for_files()
        bound_content(c,member(ra,'record_view/manifest.json'),member(rb,'record_view/manifest.json'),
                      (x['manifest_sha256'],y['manifest_sha256']),exclude={'path'},path=str(a)+'/manifest_sha256')
        x['manifest_sha256']=y['manifest_sha256']='verified admitted record manifest'
    return x,y


def documentary(c,x,y,fields,path):
    """Named retained process qualifications have zero scientific-match credit."""
    for field in sorted(fields&(set(x)|set(y))):
        row={'field':path+'/'+field,'generated':x.get(field),'reference':y.get(field),
             'disposition':'HISTORICAL_DOCUMENTARY_ONLY','historical_matches':0,
             'reason':'retained method/approval/specification quotation; zero scientific content'}
        c.documentary_fields.append(row)
        c.record('historical_documentary_fields',row['field'],row['generated'],row['reference'],row['disposition'],True)
    return ({k:v for k,v in x.items() if k not in fields},
            {k:v for k,v in y.items() if k not in fields})
