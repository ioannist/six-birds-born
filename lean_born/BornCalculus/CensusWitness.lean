import BornCalculus.CensusExact
import BornCalculus.IntegerFrame

namespace BornCalculus
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0

noncomputable def censusInteger (c : Fin 120) : IntegerFrame32 :=
 ⟨censusZ c,censusD c,censusS c,(census_frame_checks c).1,(census_frame_checks c).2.1,
   (census_frame_checks c).2.2.1,(census_frame_checks c).2.2.2⟩
noncomputable def censusFrame (c : Fin 120) : CenteredFrame32 := integerCentered (censusInteger c)

theorem census_initial_records_equal (c : Fin 120) :
 frameOldView (censusLabels c) (simplexPoint 0) =
 frameOldView (censusLabels c) (simplexPoint (censusJ c)) :=
 frame_old_points_equal _ _ _ (census_pair_checks c).2.2

theorem census_frame_coordinates_ne (c : Fin 120) :
 (censusFrame c).w 0 ≠ (censusFrame c).w (censusJ c) := by
 change (censusZ c 0:ℝ)/(censusD c:ℝ) ≠ (censusZ c (censusJ c):ℝ)/(censusD c:ℝ)
 have hd : (censusD c:ℝ) ≠ 0 := by exact_mod_cast (census_frame_checks c).1.ne'
 intro he
 have h := congrArg (fun x : ℝ => x*(censusD c:ℝ)) he
 simp only [div_mul_cancel₀ _ hd] at h
 exact (census_pair_checks c).2.1 (by exact_mod_cast h)

theorem census_initial_densities_ne (c : Fin 120) :
 frameEncoding (censusFrame c) (simplexPoint 0) ≠
 frameEncoding (censusFrame c) (simplexPoint (censusJ c)) :=
 frame_points_density_ne _ _ _ (census_frame_coordinates_ne c)

theorem census_point_read_formula (c : Fin 120) (i : Fin 32) :
 framePointRead (censusFrame c) (censusLabels c 0) 0 i =
 (censusNumerator c i:ℝ)/(censusDenominator c i:ℝ) := by
 have h := census_moment_checks c
 simpa only [censusFrame,censusInteger,integerReadNumerator,integerReadDenominator,
   censusNumerator,censusDenominator] using
   integer_frame_point_read (censusInteger c) (censusLabels c 0) i
     (censusM0 c) (censusM1 c) (censusM2 c) h.1 h.2.1 h.2.2

theorem census_initial_readouts_ne (c : Fin 120) :
 framePointRead (censusFrame c) (censusLabels c 0) 0 0 ≠
 framePointRead (censusFrame c) (censusLabels c 0) 0 (censusJ c) := by
 rw [census_point_read_formula,census_point_read_formula]
 have hd (i : Fin 32) : (censusDenominator c i:ℝ) ≠ 0 := by
   have h := integer_read_denominator_positive (censusInteger c) i
   change 0 < censusDenominator c i at h
   exact_mod_cast h.ne'
 intro he
 have h := (div_eq_div_iff (hd 0) (hd (censusJ c))).mp he
 exact census_readout_gap c (by exact_mod_cast h)

/-- All 120 registered anonymous initial-view strictness witnesses, with any
fixed public context/precision/time fields. No history or finite-cost claim. -/
theorem census_initial_no_factor {β : Type*} (fixed : β) (c : Fin 120) :
 ¬ ∃ g : β × (Fin 3 → Fin 4 → ℝ) → ℝ, ∀ p : Simplex32,
   pairing (frameEncoding (censusFrame c) p) (frameLens (censusFrame c) (censusLabels c 0) 0) =
   g (fixed,frameOldView (censusLabels c) p) :=
 frame_initial_no_factor fixed (censusFrame c) (censusLabels c) 0 (censusJ c) 0 0
   (census_pair_checks c).2.2 (census_initial_readouts_ne c)

/-- Earlier candidates fail the identical-record or unequal-density test.
The chosen pair is therefore the first possible separating point pair in the
registered lexicographic search; raw atom 0 separates immediately. -/
theorem census_earlier_point_rejected (c : Fin 120) (k : Fin 32)
 (hk : 0 < k.val ∧ k.val < (censusJ c).val) :
 frameOldView (censusLabels c) (simplexPoint 0) ≠ frameOldView (censusLabels c) (simplexPoint k) ∨
 frameEncoding (censusFrame c) (simplexPoint 0) = frameEncoding (censusFrame c) (simplexPoint k) := by
 rcases census_earlier_checks c k hk with ⟨f,hf⟩ | he
 · left
   intro hv
   exact hf ((frame_old_points_equal_iff _ _ _).mp hv f)
 · right
   apply frame_points_density_eq
   change (censusZ c 0:ℝ)/(censusD c:ℝ) = (censusZ c k:ℝ)/(censusD c:ℝ)
   rw [he]

theorem census_point_receipts_separate (c : Fin 120) :
 ((0:Fin 32),frameOldView (censusLabels c) (simplexPoint 0)) ≠
 (censusJ c,frameOldView (censusLabels c) (simplexPoint (censusJ c))) := by
 intro he
 have h := congrArg (fun p : Fin 32 × (Fin 3 → Fin 4 → ℝ) => p.1.val) he
 have hp := (census_pair_checks c).1
 simp only [Prod.fst] at h
 omega

end BornCalculus
