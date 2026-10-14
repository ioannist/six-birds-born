import BornCalculus.CensusInputs

namespace BornCalculus
open scoped BigOperators
set_option maxHeartbeats 0
set_option maxRecDepth 100000

def censusNumerator (c : Fin 120) (i : Fin 32) : ℤ :=
 censusM0 c*(censusS c)^2+64*censusS c*censusZ c i*censusM1 c+
 1024*(censusZ c i)^2*censusM2 c

def censusDenominator (c : Fin 120) (i : Fin 32) : ℤ :=
 32*censusS c*(censusS c+32*(censusZ c i)^2)

theorem census_frame_checks (c : Fin 120) :
 0 < censusD c ∧ 0 < censusS c ∧ (∑ i : Fin 32, censusZ c i) = 0 ∧
 (∑ i : Fin 32, (censusZ c i)^2) = censusS c := by
 decide +kernel +revert

theorem census_pair_checks (c : Fin 120) :
 0 < (censusJ c).val ∧ censusZ c 0 ≠ censusZ c (censusJ c) ∧
 (∀ f : Fin 3, censusLabels c f 0 = censusLabels c f (censusJ c)) := by
 decide +kernel +revert

theorem census_earlier_checks (c : Fin 120) (k : Fin 32)
 (hk : 0 < k.val ∧ k.val < (censusJ c).val) :
 (∃ f : Fin 3, censusLabels c f 0 ≠ censusLabels c f k) ∨ censusZ c 0 = censusZ c k := by
 decide +kernel +revert

theorem census_moment_checks (c : Fin 120) :
 (∑ k : Fin 32, if censusLabels c 0 k = 0 then (1:ℤ) else 0) = censusM0 c ∧
 (∑ k : Fin 32, if censusLabels c 0 k = 0 then censusZ c k else 0) = censusM1 c ∧
 (∑ k : Fin 32, if censusLabels c 0 k = 0 then (censusZ c k)^2 else 0) = censusM2 c := by
 decide +kernel +revert

theorem census_readout_gap (c : Fin 120) :
 censusNumerator c 0*censusDenominator c (censusJ c) ≠
 censusNumerator c (censusJ c)*censusDenominator c 0 := by
 decide +kernel +revert

end BornCalculus
