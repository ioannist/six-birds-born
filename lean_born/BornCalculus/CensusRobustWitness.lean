import BornCalculus.CensusWitness
import BornCalculus.CensusRobustInputs

namespace BornCalculus

set_option maxHeartbeats 0
set_option maxRecDepth 100000

/- Uniform bound for the supplemental P13 witnesses, not the original P10 pairs. -/
def censusRobustBound : ℚ := 3 / 20

theorem census_robust_pair_checks (c : Fin 120) :
 (censusRobustI c).val < (censusRobustJ c).val ∧
 (∀ f : Fin 3, censusLabels c f (censusRobustI c) = censusLabels c f (censusRobustJ c)) := by
 decide +kernel +revert

/- Cross-multiplication checks the absolute rational gap without floating point. -/
theorem census_robust_gap_check (c : Fin 120) :
 3 * censusDenominator c (censusRobustI c) * censusDenominator c (censusRobustJ c) ≤
 20 * |censusNumerator c (censusRobustI c) * censusDenominator c (censusRobustJ c) -
       censusNumerator c (censusRobustJ c) * censusDenominator c (censusRobustI c)| := by
 decide +kernel +revert

theorem census_robust_records_equal (c : Fin 120) :
 frameOldView (censusLabels c) (simplexPoint (censusRobustI c)) =
 frameOldView (censusLabels c) (simplexPoint (censusRobustJ c)) :=
 frame_old_points_equal _ _ _ (census_robust_pair_checks c).2

theorem census_robust_readout_gap (c : Fin 120) :
 (3 / 20 : ℝ) ≤
 |framePointRead (censusFrame c) (censusLabels c 0) 0 (censusRobustI c) -
  framePointRead (censusFrame c) (censusLabels c 0) 0 (censusRobustJ c)| := by
 rw [census_point_read_formula, census_point_read_formula]
 have hd (i : Fin 32) : 0 < (censusDenominator c i : ℝ) := by
   have h := integer_read_denominator_positive (censusInteger c) i
   change 0 < censusDenominator c i at h
   exact_mod_cast h
 have hR :
   3 * (censusDenominator c (censusRobustI c) : ℝ) * (censusDenominator c (censusRobustJ c) : ℝ) ≤
   20 * |(censusNumerator c (censusRobustI c) : ℝ) * (censusDenominator c (censusRobustJ c) : ℝ) -
         (censusNumerator c (censusRobustJ c) : ℝ) * (censusDenominator c (censusRobustI c) : ℝ)| := by
   exact_mod_cast census_robust_gap_check c
 have hdiff :
   (censusNumerator c (censusRobustI c) : ℝ) / (censusDenominator c (censusRobustI c) : ℝ) -
   (censusNumerator c (censusRobustJ c) : ℝ) / (censusDenominator c (censusRobustJ c) : ℝ) =
   ((censusNumerator c (censusRobustI c) : ℝ) * (censusDenominator c (censusRobustJ c) : ℝ) -
    (censusNumerator c (censusRobustJ c) : ℝ) * (censusDenominator c (censusRobustI c) : ℝ)) /
   ((censusDenominator c (censusRobustI c) : ℝ) * (censusDenominator c (censusRobustJ c) : ℝ)) := by
   field_simp [(hd (censusRobustI c)).ne', (hd (censusRobustJ c)).ne']
 rw [hdiff, abs_div, abs_of_pos (mul_pos (hd _) (hd _))]
 apply (le_div_iff₀ (mul_pos (hd _) (hd _))).2
 nlinarith only [hR]

/- Exact trace pairings on point preparations; all three label maps agree. -/
theorem census_robust_witness (c : Fin 120) :
 (∀ f : Fin 3, censusLabels c f (censusRobustI c) = censusLabels c f (censusRobustJ c)) ∧
 (3 / 20 : ℝ) ≤
 |pairing (frameEncoding (censusFrame c) (simplexPoint (censusRobustI c)))
          (frameLens (censusFrame c) (censusLabels c 0) 0) -
  pairing (frameEncoding (censusFrame c) (simplexPoint (censusRobustJ c)))
          (frameLens (censusFrame c) (censusLabels c 0) 0)| := by
 refine ⟨(census_robust_pair_checks c).2, ?_⟩
 simpa only [frame_point_encoding, framePointRead] using census_robust_readout_gap c

end BornCalculus
