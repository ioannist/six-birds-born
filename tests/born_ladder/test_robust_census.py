"""P13's exact witnesses, deterministic selection and external input binding."""
from fractions import Fraction as Q
import os
from pathlib import Path
import re
import shutil

import pytest

from born_ladder import robust_census as robust
from born_ladder.__main__ import REGISTRY, LEAN_SCOPE
from born_ladder.claims import Evidence

ROOT = Path(__file__).resolve().parents[2]
LEAN = ROOT / 'lean_born'


def test_p13_registry_endpoints_and_scope():
    title, lane, endpoints = REGISTRY['P13']
    assert title == '2,122 maximal raw-label-zero trace gaps: uniform 1/25 and minimum enclosure'
    assert lane == 'data'
    assert {'Census.census_robust_pair_checks','Census.census_robust_witness',
            'Census.census_maximizes','Census.census_maximizing_ties',
            'Census.census_minimum_isLeast','Census.census_minimum_enclosure'} <= set(endpoints)
    scope = LEAN_SCOPE['P13']
    for qualification in ('all 2,122 frames', 'equal labels in all three maps (raw/package/joint)',
                          'raw-label-zero trace gap >= 1/25', 'maximality',
                          'lexicographic ties', 'Archive/complete-record binding',
                          'registered 3/20', 'no perturbation stability',
                          'finite-sample access', 'induced dynamics'):
        assert qualification in scope


def test_point_read_formula_matches_projected_point_in_one_embedded_case():
    r = robust.embedded_records(LEAN)[0]
    # Independent micro-coordinate definition: project a point mass, normalize
    # its squared amplitudes, then sum over the raw-zero block. This does not
    # repeat the integer numerator/denominator polynomial being tested.
    w = [Q(z, r['D']) for z in r['Z']]
    s = sum(a*a for a in w)
    for i in (0, 1, 2, 31):
        amplitudes = [Q(1, 32) + a*w[i]/s for a in w]
        norm_squared = sum(a*a for a in amplitudes)
        expected = sum(a*a for a, label in zip(amplitudes, r['Labels'][0])
                       if label == 0) / norm_squared
        assert robust.point_read(r, i) == expected


def test_maximizing_scan_breaks_exact_ties_lexicographically(monkeypatch):
    # (0,1) has zero gap. Four later pairs attain the same nonzero maximum;
    # choosing either the first eligible pair or the last maximizing pair fails.
    z = [0, 0, -2, 2] + [0]*28
    labels = [0]*4 + [1]*28
    r = {'Z': z, 'D': 1, 'S': 8, 'M0': 4, 'M1': 0, 'M2': 8,
         'Labels': [labels, labels, [0]*4 + [3]*28]}
    monkeypatch.setattr(robust, 'embedded_records', lambda _: [r])
    result = robust.scan(LEAN)
    row = result['cases'][0]
    assert (row['i'], row['j']) == (0, 2)
    assert Q(row['gap_exact']) == Q(14, 17)
    assert all(Q(robust.point_read(r, i) - robust.point_read(r, j)) in (Q(14, 17), -Q(14, 17))
               for i, j in ((0, 2), (0, 3), (1, 2), (1, 3)))


def test_maximizing_scan_matches_literal_lean_pair_table():
    result = robust.scan(LEAN)
    assert result['contexts'] == 120
    assert result['bound_exact'] == '3/20'
    assert robust.render_pairs(result['cases']) == (LEAN / 'BornCalculus/CensusRobustInputs.lean').read_text()
    records = robust.embedded_records(LEAN)
    for row, record in zip(result['cases'], records):
        i, j = row['i'], row['j']
        assert i < j
        assert all(labels[i] == labels[j] for labels in record['Labels'])
        assert Q(row['gap_exact']) >= Q(3, 20)


@pytest.fixture(scope='module')
def retained_evidence():
    return Evidence(os.environ['BORN_LADDER_DATA'])


@pytest.mark.data
def test_p13_binds_existing_p10_archive_and_lean_pairs(retained_evidence):
    result = robust.check(retained_evidence, LEAN)
    assert result['status'] == result['binding']['status'] == 'PASS'
    assert result['contexts'] == result['binding']['contexts'] == 120
    assert result['binding']['context_commitments'] == 120
    assert result['minimum_cases'] == [109]
    assert all(Q(row['gap_exact']) >= Q(3, 20) for row in result['cases'])
    assert 'external' in result['boundary']


@pytest.mark.data
def test_p13_rejects_corrupted_lean_pair_table(retained_evidence, tmp_path):
    # Retain the actual archive binding and frame input; corrupt just one new
    # pair into (i,i), so the production comparison must reject its zero gap.
    target = tmp_path / 'BornCalculus'
    target.mkdir()
    tools = tmp_path / 'tools'
    tools.mkdir()
    for name in ('CensusInputs.lean', 'CensusRobustInputs.lean', 'CensusRobustWitness.lean'):
        shutil.copyfile(LEAN / 'BornCalculus' / name, target / name)
    shutil.copyfile(LEAN / 'tools/check_census_embedding.py', tools / 'check_census_embedding.py')
    path = target / 'CensusRobustInputs.lean'
    source = path.read_text()
    left = re.search(r'def censusRobustI[^\n]*\n \| 0 => (\d+)', source)
    right = re.search(r'def censusRobustJ[^\n]*\n \| 0 => (\d+)', source)
    assert left and right and left[1] != right[1]
    path.write_text(source[:right.start(1)] + left[1] + source[right.end(1):])
    with pytest.raises(ValueError, match='P13 embedded maximizing witness pairs differ'):
        robust.check(retained_evidence, tmp_path)
