from copy import deepcopy
from fractions import Fraction as Q
import pytest
from born_ladder.independent_trine import check
from born_ladder.arithmetic import certify_G

def test_independent_trine_all_fields_and_corruption():
 for s in [Q(32),Q(1,2**2200),Q(5,7)]:
  c=certify_G(s);assert check(c)['probability_entries']==18
  for kind in ['state','effect','table','mixture','metric']:
   bad=deepcopy(c)
   if kind=='state':bad['states_and_sharp_yes_effects'][5][0][0]['rational']='99'
   if kind=='effect':bad['states_and_sharp_yes_effects'][1][0][1]['radical_coefficient']='1/5'
   if kind=='table':bad['YES_table_exact'][0][0]='1/2'
   if kind=='mixture':bad['five_mixture_identities'][4][0][1]='1/4'
   if kind=='metric':bad['G'][0][0]='31'
   with pytest.raises(AssertionError):check(bad)


@pytest.mark.parametrize('path,value',[
 (('five_mixture_identities',0,0,0),0.5),
 (('five_mixture_identities',0,0,0),False),
 (('five_mixture_identities',0,0,1),0.5),
 (('YES_table_exact',0,0),True),
 (('YES_table_exact',0,0),1.0),
 (('G',0,0),32),
 (('states_and_sharp_yes_effects',0,0,0,'rational'),True),
])
def test_independent_trine_rejects_coercing_numeric_representations(path,value):
 c=certify_G(Q(5,7));parent=c
 for key in path[:-1]:parent=parent[key]
 parent[path[-1]]=value
 with pytest.raises(AssertionError):check(c)
