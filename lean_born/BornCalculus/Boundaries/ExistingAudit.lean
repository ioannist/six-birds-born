import BornCalculus.MeasurableSix
import BornCalculus.B05Pairing
import BornCalculus.B05Semantics
import BornCalculus.B07Witness
import BornCalculus.Visibility

/- Item 4 is already implemented in MeasurableSix: its bridge is a real
constructor with proofs of the scaled mixture identities and the perfect
responses read from the actual six-state table. These endpoints audit it,
plus the exactly worked-case claims of item 6, without duplicating proofs. -/
#print axioms BornCalculus.measurable_table_bridge
#print axioms BornCalculus.measurable_table_representation_impossible
#print axioms BornCalculus.measurable_six_no_go
#print axioms BornCalculus.six_state_probability_table
#print axioms BornCalculus.b05_density_barycenters_equal
#print axioms BornCalculus.b05_all_lens_first_reads_equal
#print axioms BornCalculus.b05_completion_word_strict
#print axioms BornCalculus.b05_completion_density_no_factor
#print axioms BornCalculus.b05_sources_reachable
#print axioms BornCalculus.b07_probability_bounds
#print axioms BornCalculus.b07_order_disturbance
#print axioms BornCalculus.event_descends_iff_saturated
#print axioms BornCalculus.event_projection_idempotent
#print axioms BornCalculus.visibilityPushforward_idempotent
#print axioms BornCalculus.visibilityPushforward_sum
