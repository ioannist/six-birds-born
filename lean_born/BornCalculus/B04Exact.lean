import BornCalculus.B04Inputs

namespace BornCalculus
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0
set_option maxRecDepth 100000

/-- Computable rational form of the signed root bound.
All finite checks below use kernel reduction, not native evaluation. -/
def lowerLinearRootQ (a lo hi : Fin 32 → ℚ) (i : Fin 32) : ℚ :=
 if 0 ≤ a i then a i * lo i else a i * hi i

theorem b04_s_positiveQ : 0 < b04SQ := by decide +kernel

theorem b04_frame_checksQ : (∑ i : Fin 32, b04WQ i) = 0 ∧
 (∑ i : Fin 32, (b04WQ i)^2) = b04SQ := by decide +kernel

theorem b04_initial_simplexQ (e : Fin 4) (side : Fin 2) :
 (∑ i : Fin 32, b04PQ e side i) = 1 ∧ ∀ i, 0 ≤ b04PQ e side i := by
 decide +kernel +revert

theorem b04_relative_rootsQ (e : Fin 4) (side : Fin 2) :
 0 < b04PQ e side 0 ∧
 (∀ i, 0 ≤ b04RootsQ e side i ∧ (b04RootsQ e side i)^2 = b04PQ e side i / b04PQ e side 0) ∧
 0 < (∑ i : Fin 32, b04RootsQ e side i) ∧
 (∑ i : Fin 32, b04WQ i * b04RootsQ e side i) = 0 := by
 decide +kernel +revert

/-- The first exact retained-kernel application is checked componentwise. -/
theorem b04_mid_stepQ (e : Fin 4) (side : Fin 2) :
 b04MidQ e side = b04KQᵀ *ᵥ b04PQ e side := by
 decide +kernel +revert

/-- K2 means two exact applications of the same retained coefficient
matrix; no independently supplied successor or normalized-row kernel. -/
theorem b04_future_stepQ (e : Fin 4) (side : Fin 2) :
 b04FutureQ e side =
   if e.val % 2 = 0 then b04MidQ e side else b04KQᵀ *ᵥ b04MidQ e side := by
 decide +kernel +revert

theorem b04_root_squaresQ (e : Fin 4) (side : Fin 2) :
 (∀ i, 0 ≤ b04LoQ e side i ∧ 0 ≤ b04HiQ e side i ∧
   (b04LoQ e side i)^2 ≤ b04FutureQ e side i ∧
   b04FutureQ e side i ≤ (b04HiQ e side i)^2) ∧
 0 < (∑ i : Fin 32, b04LoQ e side i) := by
 decide +kernel +revert

theorem b04_chart_lower_checkQ (e : Fin 4) (side : Fin 2) :
 0 ≤ ∑ i : Fin 32, lowerLinearRootQ
   (fun i => (32/b04SQ)*b04WQ i-b04LowerQ e side)
   (b04LoQ e side) (b04HiQ e side) i := by
 decide +kernel +revert

theorem b04_chart_upper_checkQ (e : Fin 4) (side : Fin 2) :
 0 ≤ ∑ i : Fin 32, lowerLinearRootQ
   (fun i => b04UpperQ e side-(32/b04SQ)*b04WQ i)
   (b04LoQ e side) (b04HiQ e side) i := by
 decide +kernel +revert

theorem b04_chart_nonoverlapQ (e : Fin 4) :
 b04UpperQ e 0 < b04LowerQ e 1 ∨ b04UpperQ e 1 < b04LowerQ e 0 := by
 decide +kernel +revert

def recordMarginalQ (q : Fin 32 → Fin 3) (p : Fin 32 → ℚ) (j : Fin 3) : ℚ :=
 ∑ i : Fin 32, if q i = j then p i else 0

theorem b04_joined_record_equalQ (e : Fin 2) :
 (∀ j, recordMarginalQ b04Raw (b04PQ ⟨e.val+2,by omega⟩ 0) j =
   recordMarginalQ b04Raw (b04PQ ⟨e.val+2,by omega⟩ 1) j) ∧
 (∀ j, recordMarginalQ b04Package (b04PQ ⟨e.val+2,by omega⟩ 0) j =
   recordMarginalQ b04Package (b04PQ ⟨e.val+2,by omega⟩ 1) j) ∧
 (∀ j, recordMarginalQ b04Joint (b04PQ ⟨e.val+2,by omega⟩ 0) j =
   recordMarginalQ b04Joint (b04PQ ⟨e.val+2,by omega⟩ 1) j) := by
 decide +kernel +revert

end BornCalculus
