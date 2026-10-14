"""Public claim verification with explicit, read-only historical evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

# Registry: ID -> short claim, lane, Lean endpoints (where applicable).
REGISTRY = {
    'P01': ('embedded RI total carrier and exact rank-two parent construction', 'lean', ('riAmplitudeDen_positive', 'riUpperDensity_psd_trace','riCoordinateDensity_domain','riCoordinateEffect_domain','riCoordinateEffect_sum','riFrameBasis_projection')),
    'P02': ('RI all-three-lens Lean pairing and exact parent POVM/readout checks', 'lean', ('ri_all_lens_coordinate_readouts','ri_coordinate_micro_pairing','riCoordinateEffect_coefficients','riCoordinateDensity_chart','riFrameLambda_formula','ri_lens_parent_coarsening','frame_coordinate_transfer')),
    'P03': ('120-context numerical correspondence', 'data', ()),
    'P04': ('principal-root density instrument', 'lean', ('principal_root_exists_unique','g_principalRadical_eq_root','g_principalRadical_branch_correspondence','real_kraus_complete_positivity', 'normalized_branch_density', 'posterior_zero', 'forgotten_density')),
    'P05': ('finite non-adaptive program calculus', 'lean', ('program_mass_sum', 'word_probability_pairing', 'joint_normalized_posteriors', 'density_sufficiency', 'visibility_mass_sum')),
    'P06': ('typed event/package construction and independent law preservation', 'control', ('simplex_state_preservation','simplex_composition','simplex_forgetting_preservation','simplex_visibility_normalization','g_simplex_state_preservation','event_descends_iff_saturated','event_projection_idempotent','packageVisibility_idempotent','packageVisibility_ledger')),
    'P07': ('full real effect-interval trace valuation', 'lean', ('full_interval_trace_unique', 'g_full_interval_trace_unique')),
    'P08': ('finite-simplex representation obstruction', 'lean', ('no_finite_simplex_model', 'g_no_finite_simplex_model')),
    'P09': ('six-state measurable representation obstruction', 'lean', ('measurable_table_representation_impossible', 'g_measurable_six_no_go')),
    'P10': ('120 anonymous-initial strictness witnesses', 'data', ('census_initial_records_equal','census_initial_densities_ne','census_initial_readouts_ne','census_initial_no_factor','census_earlier_point_rejected','census_point_receipts_separate')),
    'P11': ('120-context descriptive attachments', 'data', ()),
    'P12': ('recomputed G2a/G2c unit laws/losses; hash-bound population attachments', 'data', ()),
    'P13': ('120 same-label point witnesses with raw-zero trace gap at least 3/20', 'data', ('census_robust_pair_checks','census_robust_records_equal','census_robust_readout_gap','census_robust_witness')),
    'B01': ('hash-bound production/import role boundary', 'data', ()),
    'B02': ('access-matched simplex interpreter: laws, composition and forgetting', 'control', ('simplex_state_preservation','simplex_probability_laws','simplex_transition_laws','simplex_posterior_preservation','simplex_zero_branch','simplex_conditional_mass','simplex_joint_posteriors','simplex_forgetting_preservation','g_simplex_state_preservation')),
    'B03': ('public-preparation factorization control', 'control', ()),
    'B04': ('original-fixture K/K2 no-lift witnesses', 'data', ('b04_initial_chart_zero','b04_joined_view_equal','b04_future_is_kernel_update','b04_density_no_lift','b04_joined_density_no_lift')),
    'B05': ('completion sequential-density obstruction', 'data', ('b05_density_barycenters_equal','b05_completion_word_strict','b05_completion_density_no_factor','b05_sources_reachable','b05_all_lens_first_reads_equal','b05_completion_update_domain','b05_conditioned_push_encoding','b05_completion_test_sum','b05_registered_completion_atom','ensembleWord_bounds','ensembleDensity_domain')),
    'B06': ('non-trace valuation on finite fragment; generated-H unresolved', 'data', ('b06_event_count','b06_proper_event_count','b06_non_trace_finite_fragment','fragmentWitness_valuation_laws')),
    'B07': ('registered order disturbance', 'data', ('b07_initial_domain','b07_effect_domains','b07_probability_formula','b07_probability_bounds','b07_order_disturbance')),
    'B08': ('ideal-precision access boundary', 'data', ('census_initial_records_equal','census_initial_densities_ne','census_initial_readouts_ne','census_initial_no_factor','census_point_receipts_separate')),
    'B09': ('hash-bound literal constructor failure preservation', 'data', ()),
    'B10': ('inherited-atom zero-determinant exceptions', 'data', ('census_atom_domain','census_atom_singular_iff_singleton','census_singular_atom_count','census_singular_context_count','census_singleton_nonzero_nonprojector')),
    'B11': ('historical executable/source-build boundary', 'data', ()),
    'B12': ('selected RI historical return attachment', 'data', ()),
    'B13': ('archive subset 120 of 2,122 rank-two contexts', 'data', ()),
    'B14': ('limits of formation, return and promotion', 'control', ()),
    'TB01': ('learned record-square informative negative', 'data', ()),
}


# Exact formal domains, NOT an assertion that an endpoint covers a whole
# empirical/interface claim. Broader parent identities are checked below.
LEAN_SCOPE = {
    'P01': 'Lean: embedded RI projector on Simplex32; nonzero amplitude denominator, PSD trace-one micro density, exact rank-two G-density and parent effects normalized to I2; basis projection equals retained-space unit riP, not arbitrary projectors',
    'P02': 'Lean: embedded RI all-three-lens readouts and coarsening of the 32 micro parent effects, with retained-space unit riP; exact 2x2 frame coefficients, encoder chart and micro/coordinate pairing bridge are proved; Python checks implementation coefficient parity',
    'P04': 'Lean: real 2x2 PSD principal root, exact executable radical formula including zero/singular cases, G-frame branch correspondence and Kraus congruence CP; positive-mass normalized posterior, zero posterior, forgetting for a complete KrausTest',
    'P05': 'Lean: arbitrary finite lists of complete real 2x2 KrausTest commands, every density and every visibility projection; joint posterior assumes positive JOINT mass',
    'P06': 'Lean: independently defined product-accumulator and sequential interpreters agree uniformly on every finite complete KrausTest list, composition and visibility grouping, with G transfer; visible event descent is equivalent to saturation and finite event/law packaging is idempotent with its ledger preserved; Python parser and serialization remain controls',
    'P07': 'Lean: normalized positive finitely additive valuation on the FULL real 2x2 effect interval, unique real density; positive-diagonal G transfer; not the finite/generated fragment',
    'P08': 'Lean: no FiniteSimplexModel with positive additive full-interval response valuations reproducing every real density/effect; positive-diagonal G transfer, not all unrestricted stochastic interpreters',
    'P09': 'Lean: measurable six-state table under the registered mixture-equivalence/perfect-response premises and G transfer; imported external domain, not native reachability',
    'B02': 'Lean: uncapped tree product interpreter preserves states, normalized laws, stochastic transitions, positive posteriors, zero branches, conditional composition and forgetting uniformly, with G transfer; Python descriptor/ledger implementation checked on finite controls',
    'B07': 'Lean: original EXP-112/loo_A25 raw1/package0 and package0/raw1 principal-root word probabilities are unequal; exact word-effect and scalar-radical bridges, certified rational bounds; no contextuality, incompatibility or native-realization inference',
    'B10': 'Lean: all 120 embedded frames, 1006 active atoms; exactly 27 zero-determinant singleton atoms across 20 contexts, nonzero and nonprojective, all other active atoms have positive determinant; padded empty labels are excluded; no blanket strict positivity',
    'P10': 'Lean: all 120 ordered embedded census frames; exact anonymous initial-record equality, unequal G-densities and raw-zero trace readouts, no factor with arbitrary fixed public fields, earlier pair rejection and named-point receipt separation; no history or finite-acquisition conclusion',
    'P13': 'Lean: all 120 embedded census frames, selected point pairs with equal raw/package/joint labels and absolute raw-zero trace gap >= 3/20; Python exhaustively checks maximizing pairs with lexicographic ties; external archive/record binding uses the existing P10 contract; no perturbation stability, finite-sample access or induced dynamics',
    'B08': 'Lean: all 120 ideal coefficient census witnesses, exact old views/densities/nonzero trace gaps and anonymous-view no-factor; identifying point receipts separate; no finite precision, acquisition cost or history reconstruction',
    'B05': 'Lean: original EXP-112/loo_A25 normalized two-atom ray ensembles with equal G-density barycenters and all-lens first reads; exact ray-preparation encoding, normalized completion tests and positive-branch update domains; unequal registered joint-0/K/joint-0 completion probabilities exclude a density factor; separate from the principal-root instrument, no native realization',
    'B04': 'Lean: original EXP-112/loo_A25 retained kernel, four exact K/K2 fiber pairs and certified successor chart splits; no density factor, including the two joined-record witnesses; no transfer to RI or native induced closure',
    'B06': 'Lean: embedded original EXP-112/loo_A25 fixture, eight admitted atomic effects, all 12 registered programs, 2340 event occurrences and 2316 proper groupings; strict interior of proper word groupings gives a common non-density trace-one valuation and the registered basis excludes every G-density; archived numeric epsilon remains Python checked; generated-H UNRESOLVED',
}

# Historical Fin 120 declarations and input checkers remain available. Public
# census IDs now use the separately certified full cohort and its data lane.
REGISTRY.update({
    'P03':('2,122-context numerical correspondence','data',()),
    'P10':('2,122 generalized anonymous-initial strictness witnesses','data',tuple('Census.'+n for n in (
        'census_frame_checks','census_centered_nonzero_rational','census_pair_checks','census_initial_records_equal',
        'census_initial_densities_ne','census_initial_readouts_ne','census_initial_no_factor',
        'census_earlier_pair_rejected','census_point_receipts_separate'))),
    'P11':('2,122-context descriptive attachments','data',()),
    'P13':('2,122 maximal raw-label-zero trace gaps: uniform 1/25 and minimum enclosure','data',tuple('Census.'+n for n in (
        'census_robust_pair_checks','census_robust_records_equal','census_robust_witness','census_maximizes',
        'census_maximizing_ties','census_minimum_isLeast','census_minimum_enclosure','census_minimum_candidate_upper'))),
    'B08':('2,122-context ideal-precision access boundary','data',tuple('Census.'+n for n in (
        'census_initial_records_equal','census_initial_densities_ne','census_initial_readouts_ne',
        'census_initial_no_factor','census_point_receipts_separate'))),
    'B09':('2,122-context original-implementation diagnostics','data',()),
    'B10':('2,122-context constant-block singular atom classification','data',tuple('Census.'+n for n in (
        'census_atom_domain','census_atom_singular_iff_constant','census_atom_nonnegative',
        'census_active_atom_count','census_positive_atom_count','census_singular_atom_count',
        'census_singular_context_count','census_singular_trace_bounds','census_singular_nonzero_nonprojector'))),
    'B13':('whole rank-two cohort: 2,122 of 11,177 contexts','data',()),
    'P14':('general encoder image and non-affinity','lean',(
        'General.orth_chart_coefficient_ratio','General.orth_encoding_chart','General.orth_encoder_exact_range',
        'General.orth_encoder_image','General.orth_uniform_encoding','General.orth_encoding_omits_orthogonal',
        'General.orth_encoding_non_affine','General.encoder_mixing_counterexample',
        'paper_encoder_image','paper_encoder_nonaffine','frameEncoding_image','frameEncoding_nonaffine',
        'chartDensity_continuous','chartDensity_closed_arc')),
    'B15':('general inherited assignments without a density','lean',(
        'General.inherited_indefinite_assignments','General.orth_effect_coordinates','General.witness_inherited_entries',
        'General.vandermonde_determinant','General.inherited_no_density','General.witness_set_laws',
        'General.witness_linear_relations','General.witness_orth_proper_sets','General.witness_not_positive','fragmentWitness_trace')),
    'B16':('fibre criterion for a lift on the actual image','lean',(
        'factor_on_image_iff','frame_lift_iff','frame_augmented_lift_iff','normalized_identity_general',
        'normalized_identical_rows_general','frame_identity_matrix_lift','frame_identical_rows_lift')),
})
REGISTRY['P01']=('general carrier and trace identity; embedded RI instance','lean',
    REGISTRY['P01'][2]+('General.carrier_and_trace','General.encoding_normalized_projection',
        'General.orth_effect_compression','General.projector_fixed_iff','General.frame32_all_set_trace'))
REGISTRY['P02']=('general single-test finite-state model; embedded RI instance','lean',
    REGISTRY['P02'][2]+('General.orth_n_point_model','General.orth_lens_statistics','General.encoded_statistics'))
LEAN_SCOPE.update({
    'P10':'Lean: all 2,122 exact frames; earliest (I(c),J(c)), equal three-map anonymous initial records, density/readout splits, no factor with arbitrary fixed public fields, earlier-pair rejection and point-receipt separation. Python checks complete source-derived exact frames and source joins, and binds literals/witnesses; P03 separately audits complete numerical certificates; I != 0 in 25 cases. No history reconstruction or finite acquisition claim.',
    'B08':'Lean: all 2,122 ideal coefficient witnesses and anonymous-view no-factor; identifying point receipts separate. Python checks complete source-derived exact frames and source joins and binds literals/witnesses; P03 separately audits complete numerical certificates. No finite precision, acquisition cost or history reconstruction.',
    'P13':'Lean: all 2,122 frames, equal labels in all three maps (raw/package/joint), raw-label-zero trace gap >= 1/25, maximality with lexicographic ties, actual minimum in [0.0438357,0.0438358]; case 425 supplies the upper witness. Python exhaustively recomputes pairs and registered 3/20 outcomes: 2,005 pass, 117 shortfalls. Archive/complete-record binding is external to Lean; no perturbation stability, finite-sample access or induced dynamics.',
    'B10':'Lean: 17,008 active atoms, 16,693 positive, 315 singular in 272 contexts; singular iff w is constant on the active block. All active singular effects have trace in (0,1), are nonzero and nonprojective. Python checks 283 singletons and 32 nonsingletons. Padded labels/adopted outcomes/sharp generated effects are excluded.',
    'P14':'Lean: arbitrary centered nonzero finite frames, exact orthonormal chart/range, closed pure-state arc, attained extrema, interior uniform state, omitted orthogonal density, and non-affinity for proper mixtures of distinct encodings; existing 32-state/RI bridges. No native realization or archive binding theorem.',
    'B15':'Lean: n >= 2, centered nonzero frames (sum w = 0, s = sum w^2 > 0), every 0 < epsilon < 1/n gives an inherited symmetric trace-one non-PSD assignment with strict bounds for nonempty proper subsets, normalized additive laws and linear-relation preservation; three distinct w values exclude every density representation. Archive-specific numeric margins and generated/sequential fragments remain separate.',
    'B16':'Lean: arbitrary views/readouts factor on the actual image iff fibre-constant; encoder and augmented-description instances for arbitrary simplex self-maps, plus identity/identical-row normalization examples. No continuity, affinity, efficiency or induced native K/F lift is inferred.',
})
LEAN_SCOPE['P01']='Lean: general n >= 2 centered nonzero frames, total pure density encoding, positive normalized inherited tests, common parent/coarsening and projected-square trace identity; geometric/compression bridges. '+LEAN_SCOPE['P01']
LEAN_SCOPE['P02']='Lean: every density on a general centered frame has one normalized nonnegative n-point singleton law, with inherited-label pushforwards and encoded projected-square statistics; no sequential model follows. '+LEAN_SCOPE['P02']


def audit_endpoints(root, endpoints):
    root=Path(root).resolve();tool=root/'tools/audit_declarations.py'
    if not tool.is_file():
        raise ValueError('Lean sources/tools required: supply --lean-root <lean_born>; run lake build there offline first')
    from .reproduction.lean_comparison import driver,readonly_kernel_check
    import tempfile
    names={'BornCalculus.'+endpoint for endpoint in endpoints}
    rows=[row for row in driver(root).inventory(root) if row['name'] in names]
    if {row['name'] for row in rows}!=names:raise ValueError('Lean endpoint absent from supplied project')
    workspace=(Path.cwd()/'scratch/registry_full_cohort/kernel_checks').resolve();workspace.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=workspace) as temporary:
        receipt=readonly_kernel_check(root,rows,temporary)
    return {**receipt,'fresh':True}



def verify_claim(identifier, *, data=None, historical_root=None, lean_root='lean_born', certificate_output=None):
    from .claims import Evidence, analytic_control, historical_claim
    if certificate_output is not None and identifier != 'P13':
        raise ValueError('--certificate-output is supported only by P13')
    title, lane, endpoints = REGISTRY[identifier]
    if lane == 'data':
        from .full_cohort_claims import IDS,verify as verify_full
        if data is None:
            if identifier in IDS:
                raise ValueError(f'{identifier} requires --data <full regenerated bundle or completed 2,122-case census-stage directory>; see docs/reproduction.md')
            raise ValueError(f'{identifier} requires --data <local born_claim_bundle_v1 bundle>; see docs/reproduction.md for its input contract')
        if identifier in IDS:
            return json.dumps(verify_full(identifier,data,lean_root,certificate_output=certificate_output),sort_keys=True)
        evidence=Evidence(data)
        if identifier == 'P13':
            from .robust_census import check
            from fractions import Fraction
            import importlib.util
            receipt=check(evidence,lean_root)
            # Audit every new declaration, including the literal pair tables.
            audit_path=Path(lean_root).resolve()/'tools/audit_declarations.py'
            spec=importlib.util.spec_from_file_location('robust_census_audit',audit_path)
            auditor=importlib.util.module_from_spec(spec);spec.loader.exec_module(auditor)
            names=[r['name'].removeprefix('BornCalculus.') for r in auditor.inventory(lean_root)
                   if r['file'] in ('BornCalculus/CensusRobustInputs.lean','BornCalculus/CensusRobustWitness.lean')]
            receipt['axiom_audit']=audit_endpoints(lean_root,names)
            gap=Fraction(receipt['minimum_maximum_gap_exact']);scale=10**12
            lo=gap.numerator*scale//gap.denominator
            hi=-(-gap.numerator*scale//gap.denominator)
            decimal=lambda n: str(n//scale)+'.'+str(n%scale).zfill(12)
            receipt['minimum_maximum_gap_enclosure']=[decimal(lo),decimal(hi)]
            receipt['proof_sha256']=hashlib.sha256((Path(lean_root)/'BornCalculus/CensusRobustWitness.lean').read_bytes()).hexdigest()
            if certificate_output is not None:
                output=Path(certificate_output);output.parent.mkdir(parents=True,exist_ok=True)
                output.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
            return (f"recomputed {receipt['contexts']} exact maximizing same-label point pairs; "
                    f"bound 3/20; minimum of per-case maxima in [{decimal(lo)}, {decimal(hi)}], "
                    f"zero-based cases {receipt['minimum_cases']}; {LEAN_SCOPE[identifier]}; "
                    f"{len(names)} declarations audited, allowed axioms only")
        embedding=None
        if identifier in ('P10','B08','B10','B04','B05','B06','B07'):
            import importlib.util
            checker={'P10':'check_census_embedding.py','B08':'check_census_embedding.py','B10':'check_census_embedding.py','B04':'check_transport_embedding.py','B05':'check_completion_embedding.py','B06':'check_fragment_embedding.py','B07':'check_order_embedding.py'}[identifier]
            path=Path(lean_root).resolve()/'tools'/checker
            if not path.is_file():raise ValueError(f'{identifier} exact embedding checker missing from supplied Lean root')
            spec=importlib.util.spec_from_file_location('born_claim_embedding',path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            embedding=module.check(evidence,lean_root,claim=identifier) if identifier in ('P10','B08','B10') else module.check(evidence,lean_root)
        summary=historical_claim(identifier, evidence, historical_root)
        if embedding:
            count,description={'P10':('contexts',' exact census contexts'),'B08':('contexts',' exact census contexts'),'B10':('contexts',' exact census contexts'),'B04':('fiber_pairs',' exact fiber pairs'),'B05':('atoms',' exact ensemble atoms'),'B06':('atomic_effects',' exact atomic effects'),'B07':('word_orders',' certified word orders')}[identifier]
            count=embedding[count]
            summary+='; original fixture embedding bound, '+str(count)+description
        if endpoints:
            audit_endpoints(lean_root,endpoints)
            summary+='; '+LEAN_SCOPE[identifier]+'; allowed axioms only'
        return summary
    if lane == 'control':
        summary=analytic_control(identifier,lean_root)
        if endpoints:
            audit_endpoints(lean_root,endpoints)
            summary+='; '+LEAN_SCOPE[identifier]+'; allowed axioms only'
        return summary
    root = Path(lean_root).resolve()
    audit_endpoints(root,endpoints)
    extra=''
    if identifier in ('P01','P02'):
        from .claim_checks import embedded_carrier, parent_certificate
        certificate=parent_certificate(embedded_carrier(root))
        extra=f"; Python exact uniform quadratic-form/parent certificate: {certificate['parents']} parents, {certificate['coarse_atoms']} atoms, all three lenses"
    return f'{LEAN_SCOPE[identifier]}; {len(endpoints)} formal endpoints, allowed axioms only; construction theorem, no formation claim{extra}'


def main(argv=None):
    from .reproduction.read_audit import install
    install()
    sys.set_int_max_str_digits(0)
    parser = argparse.ArgumentParser(prog='python -m born_ladder')
    sub = parser.add_subparsers(dest='command', required=True)
    verify = sub.add_parser('verify', help='verify one public claim, or list its explicit input needs')
    verify.add_argument('id', nargs='?', choices=REGISTRY)
    verify.add_argument('--list', action='store_true')
    verify.add_argument('--all-no-data', action='store_true')
    verify.add_argument('--data', type=Path)
    verify.add_argument('--profile', choices=('historical','regenerated'), default='historical')
    verify.add_argument('--historical-root', type=Path)
    verify.add_argument('--lean-root', type=Path, default=Path('lean_born'))
    verify.add_argument('--workers', type=int, default=1, help='positive worker count for regenerated P12 rotation checks; default 1, other claims ignore it')
    verify.add_argument('--certificate-output', type=Path, help='P13 only: write the exact per-case witness and axiom-audit receipt')
    archive = sub.add_parser('verify-archive')
    archive.add_argument('--root', required=True); archive.add_argument('--manifest', required=True)
    regen = sub.add_parser('regenerate-census')
    for name in ('repository', 'inventory', 'reviewed-root', 'output', 'formula'):
        regen.add_argument('--' + name, required=True)
    regen.add_argument('--proof', action='append', required=True)
    regen.add_argument('--workers', type=int, default=8); regen.add_argument('--historical-root')
    construct = sub.add_parser('construct')
    for name in ('repository', 'context-metadata', 'output', 'formula'):
        construct.add_argument('--' + name, required=True)
    construct.add_argument('--proof', action='append', default=[])
    reproduce = sub.add_parser('reproduce', help='public end-to-end production stages')
    stages = reproduce.add_subparsers(dest='stage', required=True)
    runs = stages.add_parser('runs', help='specification-driven runner grids with capture and resume')
    runs.add_argument('--grid', required=True)
    runs.add_argument('--output', type=Path, required=True)
    runs.add_argument('--workers', type=int, default=1)
    runs.add_argument('--specifications', type=Path, default=Path('specifications'))
    runs.add_argument('--runner', type=Path, default=Path('vendor/pica/target/release/runner'))
    runs.add_argument('--capture', choices=('on','off'))
    runs.add_argument('--only', action='append', default=[], help='one invocation ID from the declared grid; repeatable')
    runs.add_argument('--plan', action='store_true', help='print the complete plan without running')
    runs.add_argument('--timeout', type=float, help='per-invocation wall-time limit; default from specifications/runs.json')
    v25_smoke = stages.add_parser('v25-smoke', help='synthetic-only corrective pipeline, never reserved seeds or retained scores')
    v25_smoke.add_argument('--output', type=Path, required=True)
    v25_smoke.add_argument('--specifications', type=Path, default=Path('specifications'))
    v25_smoke.add_argument('--replicates', type=int, default=200, help='explicit synthetic reduction, not registered inference')
    v25_smoke.add_argument('--full-contract', action='store_true', help='20000 replicates and full sign enumeration on synthetic data')
    v25 = stages.add_parser('v25', help='whole corrective evaluation: runs, units, population verdicts; resumable')
    v25.add_argument('--output', type=Path, required=True)
    v25.add_argument('--workers', type=int, default=1)
    v25.add_argument('--specifications', type=Path, default=Path('specifications'))
    v25.add_argument('--synthetic', action='store_true', help='synthetic acquisition substitute; no registered seeds or retained scores')
    v25.add_argument('--replicates', type=int, default=200, help='synthetic bootstrap count only; registered run always uses 20000')
    paper_canonical = stages.add_parser('paper-canonical', help='read-only full-census canonical paper summaries; no population inference')
    paper_canonical.add_argument('--census',type=Path,required=True)
    paper_canonical.add_argument('--attachments',type=Path,required=True)
    paper_canonical.add_argument('--specifications',type=Path,default=Path('specifications'))
    paper_numbers = stages.add_parser('paper-numbers', help='check manuscript number macros against your completed full and corrective runs')
    paper_numbers.add_argument('--run',type=Path,required=True)
    paper_numbers.add_argument('--v25-output',type=Path,help='completed registered corrective evaluation; required to reproduce its numbers')
    paper_numbers.add_argument('--paper',type=Path,default=Path('paper/main.tex'))
    paper_numbers.add_argument('--output',type=Path,required=True)
    paper_numbers.add_argument('--number-map',type=Path,default=Path('specifications/paper_numbers.json'))
    paper_numbers.add_argument('--specifications',type=Path,default=Path('specifications'))
    for name in ('v25-construct','v25-evaluation'):
        stage = stages.add_parser(name, help='fresh v25 stage; historical inputs refused')
        stage.add_argument('--evaluation', choices=('competitor','cross-term'), required=True)
        stage.add_argument('--output', type=Path, required=True)
        stage.add_argument('--specifications', type=Path, default=Path('specifications'))
        if name=='v25-construct':
            stage.add_argument('--runs', type=Path, action='append', required=True)
            stage.add_argument('--workers', type=int, default=1)
        else: stage.add_argument('--units', type=Path, required=True, help='sealed fresh v25 collection JSON')
    smoke_stage = stages.add_parser('smoke-stage', help='declared reduced conformance stage; no registered verdict')
    smoke_stage.add_argument('--task', choices=('population','lean','test-b'), required=True)
    smoke_stage.add_argument('--pipeline', type=Path, required=True)
    smoke_stage.add_argument('--output', type=Path, required=True)
    smoke_stage.add_argument('--workers', type=int, default=1)
    smoke_stage.add_argument('--evaluation', choices=('competitor','cross-term'))
    smoke_stage.add_argument('--specifications', type=Path, default=Path('specifications'))
    entire = stages.add_parser('all', help='every production stage through regenerated verification; resumable')
    entire.add_argument('--output', type=Path, required=True)
    entire.add_argument('--workers', type=int, default=1)
    entire.add_argument('--profile', choices=('full','smoke'), default='full')
    entire.add_argument('--specifications', type=Path, default=Path('specifications'))
    locked = stages.add_parser('test-b-locked', help='committed Test B predictions to locked samples and verdict')
    locked.add_argument('--predictions', type=Path, required=True)
    locked.add_argument('--output', type=Path, required=True)
    locked.add_argument('--workers', type=int, default=1)
    locked.add_argument('--specifications', type=Path, default=Path('specifications'))
    locked.add_argument('--smoke', action='store_true')
    locked.add_argument('--sampler', type=Path, default=Path('vendor/pica/target/release/test-b-sampler'))
    bundle = stages.add_parser('bundle', help='assemble a separate regenerated verification bundle')
    bundle.add_argument('--pipeline', type=Path, required=True)
    bundle.add_argument('--output', type=Path, required=True)
    test_b = stages.add_parser('test-b', help='Test B kernels to committed predictions; no locked-test opening')
    test_b.add_argument('--stage', dest='production_stage', choices=('all','census','certify','sample','fit','commit'), default='all')
    sources = test_b.add_mutually_exclusive_group(required=True)
    sources.add_argument('--runs', type=Path, help='P2a Test B kernel capture root')
    sources.add_argument('--headers', type=Path, help='explicit captured audit-header directory')
    test_b.add_argument('--output', type=Path, required=True)
    test_b.add_argument('--workers', type=int, default=1)
    test_b.add_argument('--specifications', type=Path, default=Path('specifications'))
    test_b.add_argument('--smoke', action='store_true', help='reduced nonconfirmatory pipeline, never certifies registered Test B')
    test_b.add_argument('--only', action='append', default=[], help='explicit EXP:configuration kernel subset; nonconfirmatory')
    test_b.add_argument('--sampler', type=Path, default=Path('vendor/pica/target/release/test-b-sampler'))
    test_b_smoke = stages.add_parser('test-b-certify-smoke', help='small synthetic certification conformance, no real test paths')
    test_b_smoke.add_argument('--census', type=Path, required=True)
    test_b_smoke.add_argument('--output', type=Path, required=True)
    test_b_smoke.add_argument('--workers', type=int, default=1)
    test_b_smoke.add_argument('--specifications', type=Path, default=Path('specifications'))
    units = stages.add_parser('units', help='construct predictive units and census structural inputs from captures')
    units.add_argument('--grid', choices=('competitor','cross-term','smoke'), required=True)
    units.add_argument('--runs', type=Path, action='append', required=True,
                       help='P2a output root or explicit capture-index root; repeat for a diagnostic subset')
    units.add_argument('--output', type=Path, required=True)
    units.add_argument('--workers', type=int, default=1)
    units.add_argument('--specifications', type=Path, default=Path('specifications'))
    whole_comparison = stages.add_parser('compare', help='complete post-run archive comparison under fixed P8 rules')
    whole_comparison.add_argument('--run', type=Path, required=True)
    whole_comparison.add_argument('--archive', type=Path, required=True)
    whole_comparison.add_argument('--output', type=Path, required=True)
    whole_comparison.add_argument('--specifications', type=Path, default=Path('specifications'))
    whole_comparison.add_argument('--ledger', type=Path)
    whole_comparison.add_argument('--aliases', type=Path)
    whole_comparison.add_argument('--paper', type=Path, help='compare aliases actually used in this manuscript; generated definitions excluded')
    whole_comparison.add_argument('--v25-output', type=Path, help='completed registered reproduce v25 output for corrective paper quantities')
    population_comparison = stages.add_parser('compare-evaluation', help='optional exact post-inference archive comparison')
    population_comparison.add_argument('--generated', type=Path, required=True)
    population_comparison.add_argument('--reference', type=Path, required=True)
    evaluation = stages.add_parser('evaluation', help='registered population inference from a closed unit collection')
    evaluation.add_argument('--evaluation', choices=('competitor','cross-term'), required=True)
    evaluation.add_argument('--units', type=Path, required=True)
    evaluation.add_argument('--output', type=Path, required=True)
    evaluation.add_argument('--workers', type=int, default=1, help='parallel certified rotation admission; inference streams unchanged')
    evaluation.add_argument('--specifications', type=Path, default=Path('specifications'))
    attachments = stages.add_parser('census-attachments', help='performance joins after structural census commitment')
    attachments.add_argument('--census', type=Path, required=True)
    attachments.add_argument('--units', type=Path, required=True)
    attachments.add_argument('--output', type=Path, required=True)
    attachments.add_argument('--specifications', type=Path, default=Path('specifications'))
    census = stages.add_parser('census', help='structural-only census from closed units and run captures')
    census.add_argument('--units', type=Path, required=True)
    census.add_argument('--runs', type=Path, action='append', required=True)
    census.add_argument('--output', type=Path, required=True)
    census.add_argument('--workers', type=int, default=1)
    census.add_argument('--specifications', type=Path, default=Path('specifications'))
    census.add_argument('--evaluation', choices=('cross-term','competitor'), default='cross-term')
    census.add_argument('--logical-sources', type=Path, help='optional checked acquisition logical-name correspondence')
    census.add_argument('--apply-amendment', action='store_true', help='hash-check and reuse pre-amendment completed census constructions')
    census_verify = stages.add_parser('verify-census', help='independent exact census checks, with separate bound outcomes')
    census_verify.add_argument('--census', type=Path, required=True)
    census_verify.add_argument('--output', type=Path, required=True)
    census_verify.add_argument('--specifications', type=Path, default=Path('specifications'))
    replay_maps = stages.add_parser('replay-maps', help='exact spectral/sector/joint replay of retained exponent-one K')
    replay_maps.add_argument('--census', type=Path, required=True)
    replay_maps.add_argument('--original-context', type=Path, required=True)
    replay_maps.add_argument('--output', type=Path, required=True)
    replay_maps.add_argument('--source-root', type=Path, help='public source checkout containing vendor/pica')
    replay_maps.add_argument('--build-directory', type=Path, help='optional reusable offline Rust build, outside input trees')
    worked_comparison = stages.add_parser('compare-worked-cases', help='optional exact post-construction comparison with retained scientific records')
    worked_comparison.add_argument('--generated', type=Path, required=True)
    worked_comparison.add_argument('--reference', type=Path, required=True)
    worked = stages.add_parser('worked-cases', aliases=['worked-case-certificates'], help='exact worked-case certificates from captures')
    worked.add_argument('--runs', type=Path, action='append', required=True)
    worked.add_argument('--output', type=Path, required=True)
    worked.add_argument('--specifications', type=Path, default=Path('specifications'))
    lean_inputs = stages.add_parser('lean-inputs', help='render full-cohort exact Lean inputs (266 census shards) and worked-case inputs')
    lean_inputs.add_argument('--census', type=Path, required=True)
    lean_inputs.add_argument('--worked-cases', type=Path, required=True)
    lean_inputs.add_argument('--output', type=Path, required=True)
    lean_inputs.add_argument('--lean-root', type=Path, default=Path('lean_born'), help='public Lean project whose proofs and local Lake cache are reused')
    comparison = stages.add_parser('compare-units', help='compare closed regenerated JSONL with optional reference rows')
    comparison.add_argument('--generated', type=Path, required=True)
    comparison.add_argument('--reference', type=Path, required=True)
    census_comparison = stages.add_parser('compare-census', help='post-construction structural comparison only')
    census_comparison.add_argument('--generated',type=Path,required=True)
    census_comparison.add_argument('--reference',type=Path,required=True)
    census_comparison.add_argument('--lean-root',type=Path)
    args = parser.parse_args(argv)
    if args.command=='verify' and args.workers<1:
        parser.error('--workers must be positive')
    try:
        if (args.command=='reproduce' and (args.stage in ('test-b','test-b-certify-smoke','test-b-locked') or (args.stage=='smoke-stage' and args.task=='test-b'))
            or args.command=='verify' and args.profile=='regenerated' and args.id=='TB01'):
            from .reproduction.stage_environment import ensure_environment
            routed = ensure_environment('test_b_fitting', getattr(args,'specifications',Path('specifications')), sys.argv[1:] if argv is None else argv)
            if routed is not None:return routed
        if args.command=='reproduce' and args.stage=='smoke-stage' and args.task in ('population','lean'):
            from .reproduction.stage_environment import ensure_environment
            routed=ensure_environment('predictive' if args.task=='population' else 'verification',args.specifications,sys.argv[1:] if argv is None else argv)
            if routed is not None:return routed
        if args.command=='verify' and args.profile=='regenerated' and args.id not in ('TB01',None):
            from .reproduction.stage_environment import ensure_environment
            routed=ensure_environment('predictive' if args.id=='P12' else 'verification',Path('specifications'),sys.argv[1:] if argv is None else argv)
            if routed is not None:return routed
        if ((args.command=='reproduce' and (args.stage in ('units','census','verify-census','evaluation','census-attachments','v25','v25-smoke','v25-construct','v25-evaluation','paper-canonical')
                or (args.stage=='runs' and args.grid.startswith('v25-') and not args.plan)))
                or (args.command=='verify' and not args.list and args.profile=='historical')
                or args.command in ('construct','regenerate-census')):
            from .reproduction.stage_environment import ensure_environment
            profile=('predictive_v25' if args.command=='reproduce' and ((args.stage in ('v25','paper-canonical') or args.stage.startswith('v25-')) or (args.stage=='runs' and args.grid.startswith('v25-'))) else
                     'predictive' if args.command=='reproduce' and args.stage in ('units','evaluation') else 'verification')
            routed=ensure_environment(profile,getattr(args,'specifications',Path('specifications')),
                                      sys.argv[1:] if argv is None else argv)
            if routed is not None:return routed
        if args.command == 'reproduce':
            if args.stage=='paper-numbers':
                from .reproduction.paper_numbers import run_paper_numbers
                result=run_paper_numbers(run=args.run,v25_output=args.v25_output,paper=args.paper,
                    output=args.output,number_map=args.number_map,specifications=args.specifications)
                print(result['summary'])
                if result.get('error'):print(result['error'],file=sys.stderr)
                return 0 if result['status']=='PASS' else 1
            if args.stage=='paper-canonical':
                from .reproduction.paper_census import canonical_quantities
                result=canonical_quantities(args.census,args.attachments,args.specifications)
                print(json.dumps(result,sort_keys=True))
                return 0
            if args.stage=='compare':
                from .reproduction.full_comparison import run_comparison
                result=run_comparison(run=args.run,archive=args.archive,output=args.output,
                    specifications=args.specifications,ledger=args.ledger,aliases=args.aliases,paper=args.paper,v25=args.v25_output)
                print(json.dumps(result,sort_keys=True))
                return 0 if result['protocol_executed_successfully']=='PASS' and result['reported_results_reproduced'] in ('PASS','NOT_COMPARABLE') else 1
            elif args.stage=='smoke-stage':
                from . import reproduction
                from .reproduction import smoke_stages as S
                if args.task=='population':result=S.population(args.pipeline,args.output,args.evaluation,args.specifications)
                elif args.task=='lean':result=S.lean(args.pipeline,args.output)
                else:result=S.test_b(args.pipeline,args.output,args.specifications,args.workers)
                print(json.dumps(result,sort_keys=True));return 0
            if args.stage=='all':
                from .reproduction.pipeline import run_all
                result=run_all(output=args.output,workers=args.workers,profile=args.profile,specifications=args.specifications)
                print(json.dumps(result,sort_keys=True));return 0
            if args.stage=='test-b-locked':
                from .reproduction.locked_test import run_locked
                result=run_locked(predictions=args.predictions,output=args.output,workers=args.workers,
                    specifications=args.specifications,sampler=args.sampler,smoke=args.smoke)
                print(json.dumps(result,sort_keys=True));return 0
            if args.stage=='bundle':
                from .reproduction.regenerated_bundle import assemble
                result=assemble(args.pipeline,args.output)
                print(json.dumps(result,sort_keys=True));return 0
            if args.stage=='test-b':
                from .reproduction.test_b import run_test_b
                result=run_test_b(output=args.output,stage=args.production_stage,
                                 runs=args.runs,headers=args.headers,specifications=args.specifications,
                                 workers=args.workers,smoke=args.smoke,only=args.only,sampler=args.sampler)
                print(json.dumps(result,sort_keys=True))
                return 0
            elif args.stage=='test-b-certify-smoke':
                from .reproduction.test_b_smoke import smoke_certification
                result=smoke_certification(census=args.census,output=args.output,
                    specifications=args.specifications,workers=args.workers)
                print(json.dumps(result,sort_keys=True))
                return 0
            elif args.stage=='compare-worked-cases':
                from .reproduction.worked_comparison import compare_worked_cases
                result=compare_worked_cases(args.generated,args.reference)
                print(json.dumps(result,sort_keys=True))
                return int(not result['overall_agreement'])
            elif args.stage in ('worked-cases','worked-case-certificates'):
                from .reproduction.worked_cases import run_worked_cases
                result=run_worked_cases(runs=args.runs,output=args.output,specifications=args.specifications)
            elif args.stage=='lean-inputs':
                from .reproduction.lean_inputs import run_lean_inputs
                result=run_lean_inputs(census=args.census,worked_cases=args.worked_cases,output=args.output,lean_root=args.lean_root)
            elif args.stage=='v25-smoke':
                from .reproduction.v25.pipeline import smoke
                result=smoke(output=args.output,specifications=args.specifications,
                             replicates=None if args.full_contract else args.replicates)
                print(json.dumps(result,sort_keys=True))
                return 0
            elif args.stage=='v25':
                from .reproduction.v25.workflow import run
                if not args.synthetic and args.replicates != 200:
                    raise ValueError('--replicates may be changed only with --synthetic')
                result=run(output=args.output,workers=args.workers,specifications=args.specifications,
                           synthetic=args.synthetic,replicates=args.replicates)
            elif args.stage=='v25-construct':
                from .reproduction.v25.fresh import construct_fresh
                result=construct_fresh(runs=args.runs,output=args.output,evaluation=args.evaluation,
                                       specifications=args.specifications,workers=args.workers)
            elif args.stage=='v25-evaluation':
                from .reproduction.v25.fresh import infer_fresh
                result=infer_fresh(units=args.units,output=args.output,evaluation=args.evaluation,
                                  specifications=args.specifications)
            elif args.stage=='compare-census':
                from .reproduction.census_comparison import compare_census
                result=compare_census(args.generated,args.reference,lean_root=args.lean_root)
                print(json.dumps(result,sort_keys=True))
                return int(not result['overall_agreement'])
            elif args.stage == 'compare-evaluation':
                from .reproduction.evaluation_comparison import compare_evaluation
                result=compare_evaluation(args.generated,args.reference)
                print(json.dumps(result,sort_keys=True))
                return int(not result['overall_agreement'])
            elif args.stage == 'compare-units':
                from .reproduction.unit_comparison import compare_records
                with args.reference.open('rb') as reference:
                    result = compare_records(args.generated, reference)
                print(json.dumps(result,sort_keys=True))
                return int(not result['overall_agreement'])
            elif args.stage == 'evaluation':
                from .reproduction.evaluation import run_evaluation
                result=run_evaluation(evaluation=args.evaluation,units=args.units,
                    output=args.output,specifications=args.specifications,workers=args.workers)
            elif args.stage == 'census-attachments':
                from .reproduction.census_attachments import run_attachments
                result=run_attachments(census=args.census,units=args.units,
                    output=args.output,specifications=args.specifications)
            elif args.stage == 'units':
                from .reproduction.units import run_units
                result = run_units(grid=args.grid, runs=args.runs, output=args.output,
                                   workers=args.workers, specifications=args.specifications)
            elif args.stage == 'verify-census':
                from .reproduction.census_extension import verify_census
                result=verify_census(args.census,args.output)
            elif args.stage == 'replay-maps':
                from .reproduction.map_replay import run_map_replay
                result=run_map_replay(census=args.census,original_context=args.original_context,
                    output=args.output,source_root=args.source_root,build_directory=args.build_directory)
                print(json.dumps(result,sort_keys=True))
                return int(result['status']!='PASS')
            elif args.stage == 'census':
                from .reproduction.census import run_census
                result=run_census(units=args.units,runs=args.runs,output=args.output,
                    workers=args.workers,specifications=args.specifications,evaluation=args.evaluation,
                    logical_sources=args.logical_sources,apply_amendment=args.apply_amendment)
            else:
                from .reproduction.runs import run_grid
                result = run_grid(grid=args.grid, output=args.output, workers=args.workers,
                                  specifications=args.specifications, runner=args.runner,
                                  capture=None if args.capture is None else args.capture=='on',
                                  only=args.only, plan_only=args.plan, timeout=args.timeout)
            print(json.dumps(result,sort_keys=True))
            return int(bool(result.get('failed') or result.get('unlaunched') or result.get('incomplete')))
        if args.command == 'verify':
            if sum((args.list, args.all_no_data, args.id is not None)) != 1:
                parser.error('choose one ID, --list, or --all-no-data')
            if args.list:
                for identifier, (title, lane, _) in REGISTRY.items():
                    need = ' --historical-root <RB1 evidence>' if identifier == 'P12' else ''
                    from .full_cohort_claims import IDS
                    contract='full regenerated bundle or census-stage directory' if identifier in IDS else 'anchored local bundle'
                    print(f'{identifier} [{lane}] {title}' + ('; --data <'+contract+'>' + need if lane == 'data' else '') + ('; '+LEAN_SCOPE[identifier] if identifier in LEAN_SCOPE else ''))
                return 0
            ids = [args.id] if args.id else [i for i, (_, lane, _) in REGISTRY.items() if lane != 'data']
            failed = False
            for identifier in ids:
                try:
                    if args.profile=='regenerated':
                        if args.data is None:raise ValueError('regenerated verification requires --data')
                        from .reproduction.regenerated_bundle import verify as verify_regenerated
                        summary=json.dumps(verify_regenerated(identifier,args.data,lean_root=args.lean_root,certificate_output=args.certificate_output,workers=args.workers),sort_keys=True)
                    else: summary = verify_claim(identifier, data=args.data, historical_root=args.historical_root, lean_root=args.lean_root, certificate_output=args.certificate_output)
                    print(f'PASS {identifier}: {summary}', flush=True)
                except (ValueError, OSError, KeyError, AssertionError, ZeroDivisionError, RuntimeError) as exc:
                    failed = True; print(f'FAIL {identifier}: {exc}', file=sys.stderr)
            return int(failed)
        if args.command == 'verify-archive':
            from .archive import verify_files
            manifest = json.loads(Path(args.manifest).read_text())
            print(json.dumps({'status': 'PASS', 'verified_files': verify_files(args.root, manifest.get('files', manifest.get('outputs', {})))}))
        elif args.command == 'construct':
            from .certificates import construct_context
            print(json.dumps(construct_context(0, json.loads(Path(args.context_metadata).read_text()), args.repository, args.output, args.formula, args.proof), default=str))
        else:
            from .census import regenerate
            result = regenerate(args.repository, args.inventory, args.reviewed_root, args.output, args.formula, args.proof, args.workers, historical_root=args.historical_root)
            print(json.dumps({k: v for k, v in result.items() if k != 'per_context'}, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, AssertionError, RuntimeError) as exc:
        print(f'FAIL: {exc}', file=sys.stderr); return 1


if __name__ == '__main__':
    raise SystemExit(main())
