"""Numerical extraction/rendering shared by production and external checks."""
from fractions import Fraction as Q
from fractions import Fraction as F
from pathlib import Path
import json, math
FIELDS=("raw_by_state", "package_by_state", "joint_by_state")

def rational(x):
    q = Q(x)
    return f'({q.numerator} : ℚ) / {q.denominator}'

def matrix(C):
    return '!![' + rational(C[0][0]) + ',' + rational(C[0][1]) + ';' + rational(C[1][0]) + ',' + rational(C[1][1]) + ']'

def extract(context, certificate):
    if any(context['identity'].get(k) != v for k,v in {'config':'loo_A25','exp':'EXP-112','k':2,'step_index':0}.items()):
        raise ValueError('B06 original fixture identity differs')
    v = list(map(Q, context['born']['sym_eigvec_basis'][0]))
    n = len(v)
    if n != 32:
        raise ValueError('B06 original carrier dimension differs')
    w = [x - sum(v) / n for x in v]
    s = sum(x*x for x in w)
    if s <= 0:
        raise ValueError('B06 rank-two frame missing')
    families = {}
    for name, field, size in [('b06RawQ','raw_by_state',2),
                              ('b06PackageQ','package_by_state',3),
                              ('b06JointQ','joint_by_state',3)]:
        labels = context['lens'][field]
        if len(labels) != n or sorted(set(labels)) != list(range(size)):
            raise ValueError('B06 registered lens labels differ')
        atoms = []
        for label in range(size):
            S = [i for i, a in enumerate(labels) if a == label]
            atoms.append([[Q(len(S),n),sum(w[i] for i in S)/n],
                          [sum(w[i] for i in S)/s,sum(w[i]**2 for i in S)/s]])
        families[name] = atoms
    basis = [[[Q(1),Q(0)],[Q(0),Q(1)]], *families['b06JointQ'][:2]]
    expected = [[[Q(x) for x in row] for row in C] for C in certificate['basis_exact']]
    if basis != expected:
        raise ValueError('B06 certificate basis is not the extracted apparatus basis')
    if 'atomic_effects' in certificate:
        for name,field in [('b06RawQ','raw_by_state'),('b06PackageQ','package_by_state'),('b06JointQ','joint_by_state')]:
            given=[[[Q(x) for x in row] for row in effect] for effect in certificate['atomic_effects'][field]]
            if given!=families[name]:raise ValueError('B06 atomic certificate differs')
    return s,families


def render_checked(data):
    s,families=data
    out = 'import BornCalculus.Definitions\n\nnamespace BornCalculus\n\n'
    out += '/- Exact atomic effects of the original EXP-112/loo_A25 B06 fixture.\nThe external byte binding is checked by tools/check_fragment_embedding.py. -/\n'
    out += 'def b06SQ : ℚ := ' + rational(s) + '\n'
    for name, atoms in families.items():
        out += f'def {name} : Fin {len(atoms)} → Matrix (Fin 2) (Fin 2) ℚ :=\n !['
        out += ',\n   '.join(matrix(C) for C in atoms) + ']\n'
    return out + '\nend BornCalculus\n'


def render(context,certificate):
    return render_checked(extract(context,certificate))
