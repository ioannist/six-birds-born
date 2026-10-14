"""Fixed P8 comparison rules. No sampling, fitting or population inference.

Every difference is streamed to JSONL, including accepted numerical differences.
Storage provenance is separately enumerated, never rewritten to old provenance.
"""
from collections import defaultdict
from decimal import Decimal, localcontext, ROUND_HALF_EVEN, ROUND_FLOOR, ROUND_CEILING
from fractions import Fraction
import json
import math
import re
import struct
from .comparison_storage import storage_field,emission_names

# Explicit storage/process projection. Data identities, header hashes, table
# hashes, selected starts, decisions and all numerical certificate fields remain.
PROCESS_FIELDS = frozenset(('wall_seconds','cpu_seconds','elapsed_seconds','peak_rss_kib',
    'worker_seconds','coordinator_cpu_seconds','worker_peak_rss_kib','wall_seconds_this_invocation',
    'output_bytes','host','pid','worker_pid','git_sha','source_git_commit','runner_sha256','compiler','hostname','runtime','numerical_runtime','stage_environment',
    'source_code','code','argv','command','commands','directory','context_directory',
    'frame_context','frame_context_sha256','six_state_certificate','six_state_certificate_sha256',
    'context_frame_sha256','uniform_proof_binding','uniform_proofs_hash_binding',
    'attempt_record_sha256','structural_manifest_sha256','applicable_control_record_links',
    'setup_sha256','p6_setup_sha256','seal_driver_sha256','p5_seal_sha256','p5_controls_sha256','sealed_margin_sha256',
    'prediction_sha256','prediction_sha256s','fit_rows_sha256','margin_sha256',
    'prediction_commitment','archive_binding','closeout_protocol',
    'checkpoint_root','checkpoint_dir'))
STRICT_FLOAT_GROUPS=frozenset(('source_scientific_inputs','exact_context','original_kernel',
    'paper_full_precision',
    'digest_bound_scientific_content',
    'original_born','selected_kernel','selected_born',
    'original_complete_context','selected_complete_context',
    'empirical_laws_and_incidence','rng_and_draws','sampled_sequences'))


def render(value, rule='sig:4', direction=None):
    """The ledger's decimal formatting, from its full precision value."""
    if rule=='text':return str(value)
    f=Fraction(str(value));rounding={'lower':ROUND_FLOOR,'upper':ROUND_CEILING}.get(direction,ROUND_HALF_EVEN)
    if rule=='frac':return r'\tfrac{'+str(f.numerator)+'}{'+str(f.denominator)+'}'
    if rule in ('int','int:thin'):
        if f.denominator!=1:raise ValueError('noninteger paper value')
        return format(f.numerator,',').replace(',',r'\,' if rule=='int:thin' else '{,}')
    if rule=='powtwo':
        if f<=0 or f.numerator&(f.numerator-1) or f.denominator&(f.denominator-1):raise ValueError('not a power of two')
        return '2^{'+str(f.numerator.bit_length()-f.denominator.bit_length())+'}'
    with localcontext() as c:
        c.prec=max(100,len(str(abs(f.numerator)))+len(str(f.denominator))+20)
        d=Decimal(f.numerator)/Decimal(f.denominator)
        if rule=='pow10':return '10^{'+str(abs(d).adjusted())+'}'
        kind,digits=rule.split(':');digits=int(digits)
        if kind=='dec':return format(d.quantize(Decimal(1).scaleb(-digits),rounding=rounding),f'.{digits}f')
        if kind!='sig':raise ValueError('unsupported paper format '+rule)
        if not d:return '0'
        v=d.quantize(Decimal(1).scaleb(d.adjusted()-digits+1),rounding=rounding)
        if Decimal('0.0001')<=abs(d)<Decimal('10000'):return format(v,'f')
        exponent=v.adjusted();return format(v.scaleb(-exponent),'f')+r'\times 10^{'+str(exponent)+'}'


class PolicyComparison:
    def __init__(self, stream, *, projection=True):
        self.stream=stream;self.projection=projection
        self.documentary_fields=[];self.unresolved_diagnostics=[];self.unresolved_reference_fields=[]
        self.groups=defaultdict(lambda:{'compared':0,'exact':0,'accepted':0,'failed':0,
            'floats':0,'floats_binary64_exact':0,'maximum_absolute_difference':0.,
            'maximum_signed_difference':None,'minimum_signed_difference':None,'process_differences':0})

    def record(self, group, path, a, b, rule, accepted, difference=None):
        exact_difference={}
        numeric=lambda v:type(v) is int or isinstance(v,str) and re.fullmatch(r'-?\d+(?:/[1-9]\d*)?',v)
        if difference is None and numeric(a) and numeric(b):
            delta=Fraction(a)-Fraction(b)
            exact_difference={'signed_difference_exact':str(delta),'absolute_difference_exact':str(abs(delta))}
        self.stream.write(json.dumps({'group':group,'path':path,'generated':a,'reference':b,
            'rule':rule,'accepted':accepted,'signed_difference':difference,
            'absolute_difference':abs(difference) if difference is not None else None,
            **exact_difference},allow_nan=False)+'\n')

    def compare(self, group, a, b, path=''):
        row=self.groups[group]
        if isinstance(a,dict) and isinstance(b,dict):
            projected=lambda k:self.projection and (k in PROCESS_FIELDS or storage_field(group,k,path))
            missing=sorted(set(b)-set(a));extra=sorted(set(a)-set(b))
            scientific_missing=[k for k in missing if not projected(k)]
            scientific_extra=[k for k in extra if not projected(k)]
            if scientific_missing or scientific_extra:
                row['compared']+=1;row['failed']+=1
                self.record(group,path,{'extra':scientific_extra},{'missing':scientific_missing},'exact key sets',False)
            for k in sorted(set(a)|set(b)):
                p=path+'/'+k
                if projected(k):
                    if k not in a or k not in b or a[k]!=b[k]:
                        rule='storage-only projection; decoded scientific inputs/results remain compared' if storage_field(group,k,path) else 'process-only projection'
                        row['process_differences']+=1;self.record(group,p,a.get(k),b.get(k),rule,True)
                elif group=='complete_inventory' and k=='required_emission_families' and path.endswith('/source/invocation') and k in a and k in b:
                    left,right=emission_names(a[k]),emission_names(b[k])
                    if left!=a[k] or right!=b[k]:self.record(group,p,a[k],b[k],'documented capture tag/name aliases; membership/order retained',True)
                    self.compare(group,left,right,p)
                elif k in a and k in b:self.compare(group,a[k],b[k],p)
            return
        if isinstance(a,(list,tuple)) and isinstance(b,(list,tuple)):
            if type(a) is not type(b):
                row['compared']+=1;row['failed']+=1
                self.record(group,path,type(a).__name__,type(b).__name__,'exact sequence representation',False)
            if len(a)!=len(b):
                row['compared']+=1;row['failed']+=1
                self.record(group,path,len(a),len(b),'exact ordered length',False)
            for i,(x,y) in enumerate(zip(a,b)):self.compare(group,x,y,path+'/'+str(i))
            return
        row['compared']+=1
        equal=type(a) is type(b) and a==b
        floating=type(a) is float and type(b) is float
        difference=None;rule='exact types/values'
        if floating:
            if not math.isfinite(a) or not math.isfinite(b):raise ValueError('nonfinite comparison input at '+path)
            equal=struct.pack('!d',a)==struct.pack('!d',b);difference=a-b
            row['floats']+=1;row['floats_binary64_exact']+=int(equal)
            row['maximum_absolute_difference']=max(row['maximum_absolute_difference'],abs(difference))
            row['maximum_signed_difference']=difference if row['maximum_signed_difference'] is None else max(row['maximum_signed_difference'],difference)
            row['minimum_signed_difference']=difference if row['minimum_signed_difference'] is None else min(row['minimum_signed_difference'],difference)
            strict=group in STRICT_FLOAT_GROUPS or any(x in path.lower() for x in ('rng_audit','membership','randomization','sign_assignment','draw_indices','bootstrap_indices','sampled_states','sampled_labels','resampled_indices','unrounded_p_full','sym_eigvec_basis','p_theory','/kernel'))
            rule='binary64 bytes' if strict else 'abs(new-old) <= 1e-12 + 1e-12*abs(old)'
            accepted=equal or (not strict and abs(difference)<=1e-12+1e-12*abs(b))
        else:accepted=equal
        row['exact']+=int(equal);row['accepted']+=int(accepted);row['failed']+=int(not accepted)
        if not equal:self.record(group,path,a,b,rule,accepted,difference)

    def result(self):
        return {'field_groups':dict(self.groups),'overall_agreement':bool(self.groups) and all(not g['failed'] for g in self.groups.values()),
                'all_scientific_values_exact':bool(self.groups) and all(g['compared']==g['exact'] for g in self.groups.values())}
