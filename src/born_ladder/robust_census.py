"""Exact robust point witnesses on the embedded census (no sampling).

Pairs maximize the absolute raw-label-zero trace gap among i < j sharing all
three labels; ties are broken lexicographically. Lean certifies the selected
pairs and the uniform bound, not the optimizing search or archive provenance.
"""
from fractions import Fraction
from pathlib import Path
import hashlib
import re
import math


def embedded_records(lean_root):
    """Parse only the literal tables in CensusInputs.lean, without evaluation."""
    text = (Path(lean_root) / 'BornCalculus/CensusInputs.lean').read_text()
    tables = {}
    for name in ('censusD', 'censusZ', 'censusS', 'censusM0', 'censusM1',
                 'censusM2', 'censusLabels'):
        match = re.search(r'^def ' + name + r'\b[^\n]*\n(.*?)(?=^def |^end )',
                          text, re.M | re.S)
        if match is None:
            raise ValueError('missing embedded table: ' + name)
        rows = re.findall(r'^ \| (\d+|_) => (.+)$', match[1], re.M)
        if [key for key, _ in rows] != [str(i) for i in range(119)] + ['_']:
            raise ValueError('embedded census case order differs: ' + name)
        values = []
        for _, literal in rows:
            if name == 'censusLabels':
                if not re.fullmatch(r'!\[!\[[0-3,]+\],!\[[0-3,]+\],!\[[0-3,]+\]\]', literal):
                    raise ValueError('nonliteral label row')
                value = [list(map(int, v.split(',')))
                         for v in re.findall(r'!\[([0-3,]+)\]', literal)]
                if any(len(q) != 32 for q in value):
                    raise ValueError('embedded label dimension differs')
            else:
                stripped = re.sub(r'\((-?\d+) : ℤ\)', r'\1', literal)
                if name == 'censusZ':
                    if not re.fullmatch(r'!\[-?\d+(?:,-?\d+){31}\]', stripped):
                        raise ValueError('nonliteral centered integer row')
                    value = list(map(int, stripped[2:-1].split(',')))
                else:
                    if not re.fullmatch(r'-?\d+', stripped):
                        raise ValueError('nonliteral scalar row')
                    value = int(stripped)
            values.append(value)
        tables[name] = values
    records = []
    for c in range(120):
        r = {name.removeprefix('census'): values[c] for name, values in tables.items()}
        z, s, labels = r['Z'], r['S'], r['Labels']
        block = [i for i in range(32) if labels[0][i] == 0]
        if not (r['D'] > 0 and s > 0 and sum(z) == 0 and sum(v*v for v in z) == s
                and all(a in (0, 1) for a in labels[0])
                and (len(block), sum(z[i] for i in block), sum(z[i]**2 for i in block))
                == (r['M0'], r['M1'], r['M2'])):
            raise ValueError('embedded frame or raw-zero moments differ')
        records.append(r)
    return records


def point_read(r, i):
    z, s = r['Z'][i], r['S']
    return Fraction(r['M0']*s*s + 64*s*z*r['M1'] + 1024*z*z*r['M2'],
                    32*s*(s + 32*z*z))


def integer_record(w, labels):
    """Exact dyadic/rational frame in the IntegerFrame point-readout chart."""
    w = [Fraction(v) for v in w]
    if len(w)!=32 or sum(w)!=0 or len(labels)!=3 or any(len(q)!=32 for q in labels):
        raise ValueError('invalid centered frame or label dimensions')
    d = math.lcm(*(v.denominator for v in w))
    z = [int(v*d) for v in w]
    s = sum(v*v for v in z)
    if s<=0:
        raise ValueError('zero centered frame')
    block = [i for i in range(32) if labels[0][i]==0]
    return {'D':d,'Z':z,'S':s,'Labels':labels,'M0':len(block),
            'M1':sum(z[i] for i in block),'M2':sum(z[i]**2 for i in block)}


def scan_records(records, *, require_bound=True):
    """Exhaustive rational comparisons, not a statistical recomputation."""
    rows = []
    for c, r in enumerate(records):
        reads = [point_read(r, i) for i in range(32)]
        eligible = [(i, j) for i in range(32) for j in range(i+1, 32)
                    if all(q[i] == q[j] for q in r['Labels'])]
        if not eligible:
            raise ValueError('no same-label point pairs in case ' + str(c))
        # max's first tie is the first pair in this lexicographic enumeration.
        i, j = max(eligible, key=lambda pair: abs(reads[pair[0]] - reads[pair[1]]))
        gap = abs(reads[i] - reads[j])
        if require_bound and gap < Fraction(3, 20):
            raise ValueError('robust bound failed in case ' + str(c))
        rows.append({'case': c, 'i': i, 'j': j,
                     'labels': [q[i] for q in r['Labels']],
                     'eligible_pairs': len(eligible),
                     'left_exact': str(reads[i]), 'right_exact': str(reads[j]),
                     'gap_exact': str(gap)})
    minimum = min(rows, key=lambda row: Fraction(row['gap_exact'])) if rows else None
    return {'schema': 'born_robust_census_v1', 'status': 'PASS' if all(Fraction(r['gap_exact'])>=Fraction(3,20) for r in rows) else 'FAILED', 'contexts': len(rows),
            'selection_rule': 'maximize absolute raw-zero point-readout gap over i < j sharing all three labels; lexicographic ties',
            'bound_exact': '3/20', 'minimum_maximum_gap_exact': minimum['gap_exact'] if minimum else None,
            'minimum_cases': [r['case'] for r in rows if r['gap_exact'] == minimum['gap_exact']] if minimum else [],
            'cases': rows}


def scan(lean_root):
    result = scan_records(embedded_records(lean_root))
    result['embedding_sha256'] = hashlib.sha256((Path(lean_root) / 'BornCalculus/CensusInputs.lean').read_bytes()).hexdigest()
    return result


def render_pairs(rows):
    out = ('import BornCalculus.CensusInputs\n\nnamespace BornCalculus\n\n'
           '/- P13 supplemental witnesses. Maximize the absolute raw-zero readout\n'
           'gap over i < j sharing all three labels; ties lexicographic. The public\n'
           'verifier checks this selection rule. Lean certifies labels and bound. -/\n')
    for name, key in (('censusRobustI', 'i'), ('censusRobustJ', 'j')):
        out += f'def {name} (c : Fin 120) : Fin 32 := match c.val with\n'
        for c, row in enumerate(rows):
            out += f" | {c if c < len(rows)-1 else '_'} => {row[key]}\n"
    return out + '\nend BornCalculus\n'


def check(evidence, lean_root):
    """Bind to P10's existing anchored inputs, then verify the embedded scan."""
    import importlib.util
    root = Path(lean_root).resolve()
    path = root / 'tools/check_census_embedding.py'
    spec = importlib.util.spec_from_file_location('robust_census_binding', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    binding = module.check(evidence, root, claim='P10')
    result = scan(root)
    pairs_path = root / 'BornCalculus/CensusRobustInputs.lean'
    if pairs_path.read_text() != render_pairs(result['cases']):
        raise ValueError('P13 embedded maximizing witness pairs differ')
    source = (root / 'BornCalculus/CensusRobustWitness.lean').read_text()
    if not re.search(r'^def censusRobustBound : ℚ := 3 / 20$', source, re.M):
        raise ValueError('P13 Lean bound definition differs')
    result['pair_embedding_sha256'] = hashlib.sha256(pairs_path.read_bytes()).hexdigest()
    result['binding'] = binding
    result['boundary'] = ('exact embedded inputs only; archive/extraction/full-record binding is external; '
                          'no finite-sample access, perturbation stability or induced-dynamics conclusion')
    return result
