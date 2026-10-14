"""Numerical extraction/rendering shared by production and external checks."""
from fractions import Fraction as Q
from fractions import Fraction as F
from pathlib import Path
import json, math
FIELDS=("raw_by_state", "package_by_state", "joint_by_state")

def extract(context,certificate, *, registered=True):
    v=list(map(Q,context['born']['sym_eigvec_basis'][0]))
    if len(v)!=32:raise ValueError('P10 carrier dimension differs')
    w=[a-sum(v)/32 for a in v]
    D=math.lcm(*(a.denominator for a in w));z=[int(a*D) for a in w];S=sum(a*a for a in z)
    labels=[context['lens'][f] for f in FIELDS]
    if S<=0 or any(len(q)!=32 or any(a not in range(4) for a in q) for q in labels):
        raise ValueError('P10 frame/lens domain differs')
    if any(a not in (0,1) for a in labels[0]):raise ValueError('P10 raw alphabet differs')
    i,j=certificate['pair'];read=certificate['first_separating_readout']
    if not 0<=i<j<32 or (registered and (read['context'],read['numeric_atom'])!=('raw_by_state',0)):
        raise ValueError('P10 registered pair/readout differs')
    if not all(q[i]==q[j] for q in labels) or z[i]==z[j]:raise ValueError('P10 initial fiber/density split failed')
    if registered and any(all(q[a]==q[b] for q in labels) and z[a]!=z[b]
           for a in range(i+1) for b in range(a+1,32) if (a,b)<(i,j)):
        raise ValueError('P10 earlier eligible point pair exists')
    if read['context'] not in FIELDS:raise ValueError('census witness context differs')
    block=[k for k in range(32) if labels[FIELDS.index(read['context'])][k]==read['numeric_atom']]
    if not block:raise ValueError('census witness atom is inactive')
    m0,m1,m2=len(block),sum(z[k] for k in block),sum(z[k]**2 for k in block)
    def numerator(k):return m0*S*S+64*S*z[k]*m1+1024*z[k]**2*m2
    def denominator(k):return 32*S*(S+32*z[k]**2)
    left,right=Q(numerator(i),denominator(i)),Q(numerator(j),denominator(j))
    if left==right or (left,right,left-right)!=(Q(read['left_exact']),Q(read['right_exact']),Q(read['difference_exact'])):
        raise ValueError('P10 retained readout values differ')
    def density(k):
        t=S+32*z[k]**2
        return [[Q(S,t),Q(z[k]*S,D*t)],[Q(32*D*z[k],t),Q(32*z[k]**2,t)]]
    if density(i)!=[list(map(Q,row)) for row in certificate['rho_left']] or density(j)!=[list(map(Q,row)) for row in certificate['rho_right']]:
        raise ValueError('P10 retained density values differ')
    visited=sum(31-a for a in range(i))+j-i
    if certificate['pairs_visited']!=visited or certificate['preparations']!={'p':[str(int(k==i)) for k in range(32)],'p_prime':[str(int(k==j)) for k in range(32)]}:
        raise ValueError('P10 point preparation/search order differs')
    old={'context':context['identity'],'preparation_receipt':{'class':'Audit A anonymous simplex mathematical source','recipe_id':None},
         'actual_passive_laws':{f:{str(a):str(int(labels[l][i]==a)) for a in sorted(set(labels[l]))} for l,f in enumerate(FIELDS)},
         't':0,'lag':8,'history_horizons':[0],'coefficient_history_arrays':None,'acquired_passive_prefix':[],
         'commands':[],'acquired_upper_outcomes':[],'status':'PREPARATION_ENTRY','precision':'exact coefficient contract',
         'source_policy':'fixed amended full simplex, no sampled preparation population'}
    if certificate['complete_equal_old_view']!=old:raise ValueError('P10 full anonymous initial record differs')
    if certificate['status']!='PASS' or not all(certificate[k] is True for k in ('all_old_fields_exact_equal','density_exact_inequality','point_identifying_receipt_rejects_witness')):
        raise ValueError('P10 witness status differs')
    return dict(D=D,z=z,S=S,labels=labels,i=i,j=j,m0=m0,m1=m1,m2=m2)

def render(records):
    def numeral(z):return f'({z} : ℤ)'
    def vector(z):return '!['+','.join(numeral(a) for a in z)+']'
    out='import BornCalculus.Definitions\n\nnamespace BornCalculus\n\n'
    out+='/- Exact scaled-integer frames and original ordered P10 witnesses.\nArchive and full-record binding is external, not a Lean cryptographic proof. -/\n'
    for name,key,typ,fmt in [('censusD','D','ℤ',numeral),('censusZ','z','Fin 32 → ℤ',vector),('censusS','S','ℤ',numeral),
                             ('censusJ','j','Fin 32',str),('censusM0','m0','ℤ',numeral),('censusM1','m1','ℤ',numeral),('censusM2','m2','ℤ',numeral)]:
        out+=f'def {name} (c : Fin 120) : {typ} := match c.val with\n'
        for k,row in enumerate(records):out+=' | '+(str(k) if k<len(records)-1 else '_')+' => '+fmt(row[key])+'\n'
    out+='def censusLabels (c : Fin 120) : Fin 3 → Fin 32 → Fin 4 := match c.val with\n'
    for k,row in enumerate(records):
        vec='!['+','.join('!['+','.join(map(str,q))+']' for q in row['labels'])+']'
        out+=' | '+(str(k) if k<len(records)-1 else '_')+' => '+vec+'\n'
    return out+'end BornCalculus\n'

def atom_selectors(records):
    out='import BornCalculus.CensusInputs\n\nnamespace BornCalculus\n\n'
    out+='/- Per-group coordinate witnesses for the B10 rank census. -/\n'
    for name,second in [('atomFirst',False),('atomSecond',True)]:
        out+=f'def {name} (c : Fin 120) : Fin 3 → Fin 4 → Fin 32 := match c.val with\n'
        for k,row in enumerate(records):
            table=[]
            for q in row['labels']:
                indices=[]
                for a in range(4):
                    block=[i for i,v in enumerate(q) if v==a]
                    first=block[0] if block else 0
                    other=next((i for i in block if row['z'][i]!=row['z'][first]),first)
                    if block and first==other and not len(block)*(row['S']+32*row['z'][first]**2)<32*row['S']:
                        raise ValueError('B10 singular projector exception')
                    indices.append(other if second else first)
                table.append('!['+','.join(map(str,indices))+']')
            out+=' | '+(str(k) if k<len(records)-1 else '_')+' => !['+','.join(table)+']\n'
    return out+'end BornCalculus\n'
