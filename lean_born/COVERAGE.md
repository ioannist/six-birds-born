# Formal coverage

The package proves statements about real 2×2 matrices, densities, effects and
complete finite Kraus instruments. `G` denotes a positive diagonal frame metric;
transfer theorems relate this frame to orthonormal coordinates. The table names
principal exported declarations, all in the `BornCalculus` namespace. Supporting
definitions and bridges are included in the declaration/axiom audit.

| Target | Statement and exact scope | Principal exports | Source |
|---|---|---|---|
| T1 | Every positive normalized finitely additive valuation on the **full real 2×2 effect interval** has a unique real density trace representation. Does not classify the restricted generated fragment or complex densities. | `full_interval_trace_unique`, `trace_valuation_laws`, `effects_separate_densities` | [Valuations](BornCalculus/Valuations.lean) |
| T2 | No finite simplex with positive additive full-interval response valuations represents every real density/effect pairing. Preparation weights need not be affine. Unrestricted contextual interpreters are outside this obstruction. | `pure_state_extremality`, `finite_simplex_matrix_realization`, `no_finite_simplex_model` | [FiniteSimplex](BornCalculus/FiniteSimplex.lean) |
| T3 instruments | Principal roots exist uniquely for PSD effects; each real Kraus branch is completely positive. Complete tests preserve total mass; positive branches normalize, zero branches have no posterior. | `principal_root_exists_unique`, `real_kraus_complete_positivity`, `normalized_branch_density`, `posterior_zero`, `forgotten_density` | [Instruments](BornCalculus/Instruments.lean) |
| P04 executable root formula | **Orthonormal coordinates:** for a positive semidefinite real 2×2 input C, the zero/nonzero radical formula `(C+sqrt(det C)I)/sqrt(tr C+2sqrt(det C))` equals its principal square root (PrincipalFormula.lean:17, :58). The scalar-root certificate additionally selects a nonnegative determinant radical and a positive denominator radical; it proves the resulting matrix is PSD, squares to C and equals its principal root. **Metric coordinates:** for each positive diagonal G, the same formula equals the principal G-root when C is G-positive (PrincipalFormula.lean:98–99). Ordinary positive semidefiniteness of the coordinate matrix C is not the hypothesis of this metric statement. Uniqueness is supplied by the separate principal-root theorem. Under the G-positive premise, the two-sided multiplication used by Python is the metric-adjoint Kraus branch. Covers nonzero singular effects; rational interval algorithms remain separately checked. | `principal_formula_certificate`, `principalRadical_eq_sqrt`, `g_principalRadical_eq_root`, `g_principalRadical_branch_correspondence` | [PrincipalFormula](BornCalculus/PrincipalFormula.lean) |
| T3 programs | All finite non-adaptive lists of complete tests normalize, compose and obey visibility/forgetting laws. Joint normalized composition requires positive joint mass, with prefix positivity derived internally. No autonomous evolution is included. | `program_mass_sum`, `word_probability_pairing`, `word_branch_concat`, `grouping_then_suffix`, `joint_normalized_posteriors`, `density_sufficiency`, `visibility_mass_sum` | [Programs](BornCalculus/Programs.lean) |
| P06/B02 comparator | Independently defined product-accumulator and sequential-state interpreters agree for every finite complete Kraus program and density. The resulting simplex laws, stochastic transitions at positive nodes, posteriors, zero branches, composition and visibility grouping are proved uniformly, including positive diagonal G transfer. Tree size depends on the program; no uniform finite-state cap is imposed. Python descriptor parsing, protocol ledgers and packaging remain executable controls. | `simplex_state_preservation`, `simplex_probability_laws`, `simplex_transition_laws`, `simplex_posterior_preservation`, `simplex_zero_branch`, `simplex_conditional_mass`, `simplex_forgetting_preservation`, `g_simplex_state_preservation` | [Comparator](BornCalculus/Comparator.lean) |
| P06 visible events and packaging | A finite event descends through its declared visibility map iff its predicate is constant on fibers. Event images and unnormalized matrix-law pushforwards are idempotent under an idempotent visibility projection. The law projection preserves total state and PSD, and the typed package preserves its public ledger literally. Applies to the declared finite test domain; parser/serialization and their connection to that domain remain implementation controls. | `event_descends_iff_saturated`, `event_projection_idempotent`, `visibilityPushforward_idempotent`, `visibilityPushforward_sum`, `packageVisibility_idempotent`, `packageVisibility_ledger` | [Visibility](BornCalculus/Visibility.lean) |
| B06 uniform finite-fragment argument | Any finite family of nonempty proper word groupings from complete invertible Kraus programs has a common non-PSD trace-one perturbation positive on every event. Nonzero determinants of admitted effects imply invertibility of their principal roots; the selected and omitted word sums are strictly positive. A nonzero three-effect coordinate determinant excludes every density representation, including G coordinates. The next row discharges these premises for the embedded original fixture; archived numerical bounds remain Python checks. No generated-H classification is proved. | `finite_fragment_non_density`, `groupedEffect_strict_interior`, `finite_program_fragment_non_density`, `g_root_invertible_of_det`, `finite_g_program_fragment_non_density`, `g_finite_fragment_no_density_representation` | [FiniteFragment](BornCalculus/FiniteFragment.lean), [FiniteProgramFragment](BornCalculus/FiniteProgramFragment.lean), [FiniteFragmentFrame](BornCalculus/FiniteFragmentFrame.lean) |
| B06 concrete original fixture | Exact atomic tables for EXP-112/loo_A25 have eight G-positive effects, nonzero determinants and three complete lenses. All 12 one/two-command programs are complete and invertible. Their 2,340 registered event occurrences (2,316 proper groupings) admit one trace-one non-density valuation, positive on every proper event, with no G-density representation on the full registered family. The basis effects are proved to be registered events. Epsilon is obtained from the finite theorem, not imported from an archived bound. Input/program binding is external; no generated-H result. | `b06_event_count`, `b06_proper_event_count`, `b06_basis_event_effect`, `b06_non_trace_finite_fragment` | [B06Inputs](BornCalculus/B06Inputs.lean), [B06Atomic](BornCalculus/B06Atomic.lean), [B06Witness](BornCalculus/B06Witness.lean) |
| B04 concrete original no-lift | Full retained EXP-112/loo_A25 kernel, centered frame and four source pairs are embedded. Kernel reduction checks the exact rational simplex/fiber laws, both applications for K², root squares and signed chart bounds. Real root bounds certify different successor charts. The injective chart-to-G-density map excludes every density factor for K/K², including the two witnesses with all three passive record marginals equal. The retained coefficients are interpreted exactly; no row normalization, RI transfer or induced-closure premise. Archive binding remains external. | `b04_initial_chart_zero`, `b04_joined_view_equal`, `b04_future_is_kernel_update`, `b04_successor_charts_differ`, `b04_density_no_lift`, `b04_joined_density_no_lift` | [B04Inputs](BornCalculus/B04Inputs.lean), [B04Exact](BornCalculus/B04Exact.lean), [B04Witness](BornCalculus/B04Witness.lean), [RootChart](BornCalculus/RootChart.lean) |
| B05 concrete completion boundary | Original EXP-112/loo_A25: normalized nonnegative two-atom ray ensembles have equal exact G-density barycenters and identical instantaneous reads for every finite lens. Their joint-0/K/joint-0 completion probabilities differ, so no arbitrary density factor exists for this word on normalized two-atom ensembles. The admitted simplex preparation formulas encode to the registered rays; this is algebraic realization, not native reachability. All ensemble densities and word probabilities have their proper domains; positive kernel row masses certify positive-branch successors and conditioning agrees with the homogeneous formula. The full two-stage test normalizes for every finite lens. Kernel-checked rational root, chart and quadratic-readout inequalities certify the strict split. Archive binding and finer archived bounds remain external; this is not the principal-root instrument. | `b05_density_barycenters_equal`, `b05_completion_word_strict`, `b05_completion_density_no_factor`, `b05_sources_reachable`, `ensembleDensity_domain`, `ensembleWord_bounds`, `b05_lens_domain`, `b05_instantaneous_pairing`, `b05_all_lens_first_reads_equal` | [B05Exact](BornCalculus/B05Exact.lean), [B05Witness](BornCalculus/B05Witness.lean), [B05Semantics](BornCalculus/B05Semantics.lean), [B05Pairing](BornCalculus/B05Pairing.lean), [QuadraticBounds](BornCalculus/QuadraticBounds.lean) |
| T4 | The specified six-state/three-test table has no finite representation satisfying its preparation-mixture equivalences and response conditions. Outcome determinism is derived where needed. | `finite_six_no_go`, `finite_table_bridge`, `finite_table_representation_impossible` | [FiniteSix](BornCalculus/FiniteSix.lean) |
| T5 | The corresponding obstruction holds on a measurable probability space under the stated mixture and perfect-discrimination conditions. Finiteness of the hidden space is not assumed. | `measurable_six_no_go`, `measurable_table_bridge`, `measurable_table_representation_impossible` | [MeasurableSix](BornCalculus/MeasurableSix.lean) |
| T6a | The real trine six states satisfy the density/projector, five-mixture and probability-table identities; transfer supplies their premises in every positive diagonal G frame. These are adopted external preparations/tests, not a reachability theorem. | `six_states_density_and_projector`, `six_state_five_mixtures`, `six_state_probability_table`, `six_state_g_transfer` | [SixStates](BornCalculus/SixStates.lean), [FrameSix](BornCalculus/FrameSix.lean) |
| T6b | Embedded EXP-112/A13_A11, seed 840007, k=2, step 0: δ₁/δ₃ have equal three initial record marginals but different encoded raw-zero readouts. The encoder is total on `Simplex32`, with PSD trace-one output. Fixed public fields are identical. This is one initial-interface witness, not a history or census theorem. | `riAmplitudeDen_positive`, `riUpperDensity_psd_trace`, `ri_initial_records_equal`, `ri_initial_readout_ne`, `ri_initial_no_factor`, `ri_joined_state_no_factor`, `ri_trace_readout` | [RIExact](BornCalculus/RIExact.lean), [RIWitness](BornCalculus/RIWitness.lean), [RIInputs](BornCalculus/RIInputs.lean) |
| P01/P02 embedded parent readouts | Every finite lens on the embedded 32-state carrier has positive effects summing to riP and is a coarsening of its 32 micro parent effects. Trace readouts hold on every Simplex32 input; all raw/package/joint atoms are exported together. The exact 2×2 G-density, parent/lens coefficients, encoder chart and equality of micro/coordinate pairings are proved. The micro POVM unit is riP; the coordinate unit is I2. Python separately checks implementation coefficient parity. | `ri_lens_parent_coarsening`, `ri_all_lens_trace_readouts`, `riCoordinateDensity_domain`, `riCoordinateEffect_domain`, `riCoordinateEffect_coefficients`, `riFrameBasis_projection`, `riCoordinateDensity_chart`, `ri_all_lens_coordinate_readouts` | [RIParents](BornCalculus/RIParents.lean), [RICoordinates](BornCalculus/RICoordinates.lean) |
| P10/B08 complete initial census | All 120 ordered retained frames have integer-certified centered coordinates and positive squared norm. Generic parent/lens domains, point encodings and trace pairing establish equal anonymous initial records, unequal G-densities and distinct raw-zero readouts. No scalar factor through the old view exists with any fixed public fields. Earlier `(0,k)` candidates fail the record or density condition; named point receipts separate the witnesses. Every package/joint label is retained, including four-label maps. Archive/full-record/value binding is external; no history, finite-precision acquisition or native-formation claim. | `frame_encoding_domain`, `frame_lens_domain`, `integer_frame_point_read`, `census_initial_records_equal`, `census_initial_densities_ne`, `census_initial_readouts_ne`, `census_initial_no_factor`, `census_earlier_point_rejected`, `census_point_receipts_separate` | [CenteredFrame](BornCalculus/CenteredFrame.lean), [IntegerFrame](BornCalculus/IntegerFrame.lean), [CensusInputs](BornCalculus/CensusInputs.lean), [CensusExact](BornCalculus/CensusExact.lean), [CensusWitness](BornCalculus/CensusWitness.lean) |
| B10 complete atom census | Generic Gram variance and determinant/trace formulas apply to every centered frame. The 120-context census has 1,006 active atoms; coordinate witnesses certify positive determinant for every nonsingleton group. Exactly 27 active atoms in 20 contexts are singular singletons with trace in (0,1), hence nonzero and nonprojective. Empty padded labels have zero effects and are excluded from these counts. Input/selector/determinant-table binding is external; strict positivity is not asserted for all atoms. | `frame_lens_variance`, `frame_lens_det_positive`, `integer_lens_determinant`, `census_atom_domain`, `census_atom_singular_iff_singleton`, `census_singular_atom_count`, `census_singular_context_count`, `census_singleton_nonzero_nonprojector` | [FrameAtoms](BornCalculus/FrameAtoms.lean), [CensusAtomExact](BornCalculus/CensusAtomExact.lean), [CensusAtomWitness](BornCalculus/CensusAtomWitness.lean) |
| B07 original order disturbance | Original EXP-112/loo_A25, initial G-density diag(1,0): the raw1/package0 and package0/raw1 principal-root words have different probabilities. Generic metric-adjoint and principal-root-square identities reduce each word effect to a two-sided root sandwich. A linear-radical scalar formula and exact rational square/linear inequalities certify disjoint probability bounds. Input binding is external. Disturbance alone gives no contextuality, incompatibility or native-realization conclusion. | `principal_two_read_effect`, `principal_two_read_formula`, `linear_radical_ratio_bounds`, `b07_initial_domain`, `b07_probability_formula`, `b07_probability_bounds`, `b07_order_disturbance` | [OrderFormula](BornCalculus/OrderFormula.lean), [B07Exact](BornCalculus/B07Exact.lean), [B07Witness](BornCalculus/B07Witness.lean) |
| §0.3 | Positive diagonal G coordinates preserve density/effect domains, adjoints, pairing, branches and the applications of T1–T5. The metric hypotheses are explicit. | `frame_coordinate_transfer`, `g_frame_transfer`, `g_full_interval_trace_unique`, `g_no_finite_simplex_model`, `g_branch_correspondence`, `g_program_normalization`, `g_finite_six_no_go`, `g_measurable_six_no_go` | [Frame](BornCalculus/Frame.lean), [FrameApplications](BornCalculus/FrameApplications.lean) |
| P13 robust initial census | For every embedded census case, the supplemental point pair has identical labels under raw, package and joint maps, equal anonymous initial label laws, and absolute raw-label-zero trace-pairing gap at least 3/20. Integer cross-multiplication and positive denominators prove the bound by kernel reduction. The public Python verifier selects the maximum gap over i < j sharing all three labels, with lexicographic ties, and checks equality with the embedded pair table; Lean certifies the chosen pairs and bound, not maximality. Original P10 pairs are unchanged. External P10 archive/extraction/full-record binding remains separate; no finite-sample access, perturbation stability or induced-dynamics conclusion. | `census_robust_pair_checks`, `census_robust_gap_check`, `census_robust_records_equal`, `census_robust_readout_gap`, `census_robust_witness` | [CensusRobustInputs](BornCalculus/CensusRobustInputs.lean), [CensusRobustWitness](BornCalculus/CensusRobustWitness.lean) |

## Rebuild and audit

Lean v4.28.0 and Mathlib v4.28.0 are pinned by the toolchain and lockfile. From the
repository root, with elan on PATH:

```sh
make lean
make lean-audit
.venv/bin/python lean_born/tools/audit_declarations.py inventory
```

The inventory enumerates exported declarations and source locations. The audit
checks compiled declarations and prints their axiom dependencies; only
`propext`, `Classical.choice` and `Quot.sound` are allowed. Offline builds require
pre-provisioned dependencies; see [reproduction](../docs/reproduction.md).
The optional command

```sh
.venv/bin/python lean_born/tools/check_embedding.py --evidence "$RI_EVIDENCE"
```

checks three original input commitments against the embedded constants; it
requires local evidence and is separate from proof checking.

The separate B06 command

```sh
.venv/bin/python lean_born/tools/check_fragment_embedding.py --data "$BORN_DATA_BUNDLE"
```

checks the two retained original-fixture commitments, independently extracts
the eight effects/metric, and compares the Python and Lean program registration.
The public B06 verification command also performs this binding check. It is
external provenance/extraction evidence, not a Lean cryptographic proof.

The separate B04 command

```sh
.venv/bin/python lean_born/tools/check_transport_embedding.py --data "$BORN_DATA_BUNDLE"
```

checks the original context and two retained fiber-certificate commitments.
Independent rational loops extract the metric, all 1,024 kernel entries, initial
pairs, exact successors, passive labels and 40-bit root certificates. The public
B04 command performs this comparison before its mathematical checks and endpoint
audit. No cryptographic theorem is attributed to Lean.

The B05 command

```sh
.venv/bin/python lean_born/tools/check_completion_embedding.py --data "$BORN_DATA_BUNDLE"
```

checks the context and completion-certificate commitments, the frozen shared
B04 parameter file, and independently extracted scalar and vector quantities.
It binds all four rays/weights, filtered kernel successors, 64-bit root bounds,
48-bit chart bounds and 40-bit readout bounds. The public B05 command performs
this check before recomputation and endpoint auditing. The shared constants are
also compared with their independent context extraction.

The census command

```sh
.venv/bin/python lean_born/tools/check_census_embedding.py --data "$BORN_DATA_BUNDLE" --claim P10
```

also supports `--claim B08` and `--claim B10`. For B10 it additionally binds
the group coordinate witnesses and verifies the retained determinant table. It pins both ordered manifests and all 120 context
files, independently extracts scaled integer frames and labels, compares the
embedded table, and checks the retained density/readout values and complete old
records. Both public commands perform this binding before recomputation and
endpoint auditing. The byte commitments and record serialization are external
evidence rather than cryptographic Lean theorems.

The B07 command

```sh
.venv/bin/python lean_born/tools/check_order_embedding.py --data "$BORN_DATA_BUNDLE"
```

binds the original context, frozen shared effect table and independently
extracted scalar coefficients, 64-bit radical bounds and 40-bit probability
bounds. The public command performs this binding before recomputation and its
Lean endpoint audit.

## Boundaries

P01's formal encoder and P02's parent/readout theorems use the embedded RI
projector. RIWitness proves the raw-zero witness; RIParents covers every atom of all three registered lenses. RICoordinates proves their
exact 2×2 G-frame coefficient and encoder bridge. Their verification commands
also check Python implementation coefficient parity.
[Claims](../docs/claims.md) specifies that separation for every public ID.

Not formalized: the other numerical/experimental census certificates, source/build provenance,
cryptographic commitments, numerical accuracy premises, empirical statistics,
Test B inference, acquisition costs, native formation, original-kernel induced
closure, useful return, or promotion. A construction theorem does not establish
that the stochastic substrate produces the adopted measurement rule.

## Additional proof and implementation coverage

The formal scope includes the uniform product/sequential comparator, visibility
and packaging laws, principal-root formulas, and finite-fragment perturbation.
Concrete proofs cover all RI parent/lens readouts, original-kernel no-lift
witnesses, the sequential-density boundary, the finite-fragment non-trace
valuation and order disturbance. The census embeddings cover initial-record
strictness in all 120 contexts and the classification of 1,006 inherited atoms.
Archive bindings and finer numerical enclosures remain executable checks.

The Python implementation enforces the following checks:

- The independent root verifier checks the principal branch and denominator bounds.
- The comparator retains rational point roots and exact selective masses.
- Matrix enclosure checks reject unequal dimensions.
- Parent certificates bind the projector to its declared rank-two frame.
- Sequential-density checks reject empty or negatively weighted ensembles.
- No-lift checks require full carrier-dimensional preparation vectors.
- Root-certificate checks remain active under optimized Python.
- Transport rejects truncated vectors and undeclared kernel powers.
- Commuting updates and uniform encodings retain exact zero branch support.
- Frame and command checks enforce complete tests under optimized Python.
- Command admission enforces the declared principal-root rule.
- The independent six-state verifier retains all checks under optimized Python.
- Vector normalization rejects nonpositive mass under optimized Python.
- Dependencies are pinned to official PyPI wheels by version and hash.

The earlier validation comprised 736 audited Lean declarations, 84 default
tests, ten retained-data tests and all 27 claim commands then registered. P13
adds eight declarations, checked by its targeted axiom audit and verification
command; the current inventory has 744 entries and the registry 28 commands.
The suite counts remain those of the earlier validation, pending the manager's
authoritative run. The theorem scopes and external bindings above delimit
these counts; they do not establish native formation, useful return, promotion
or physical realization.
