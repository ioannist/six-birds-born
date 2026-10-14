import BornCalculus.B05Inputs
import BornCalculus.B04Exact

namespace BornCalculus
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0
set_option maxRecDepth 100000

def linearLowerQ (a lo hi : ℚ) : ℚ := if 0 ≤ a then a*lo else a*hi

def b05GateQ (t : ℚ) (i : Fin 32) : ℚ :=
 if b04Joint i = 0 then (1+t*b04WQ i)^2 else 0

def b05ChartDensityQ (t : ℚ) : Matrix (Fin 2) (Fin 2) ℚ :=
 (32+b04SQ*t^2)⁻¹ • !![32,b04SQ*t;32*t,b04SQ*t^2]


theorem b05_kernel_nonnegativeQ : ∀ i j : Fin 32, 0 ≤ b04KQ i j := by decide +kernel

theorem b05_kernel_row_massQ : ∀ i : Fin 32, 0 < ∑ j : Fin 32, b04KQ i j := by decide +kernel

/-- All finite checks use trusted kernel reduction, not native evaluation. -/
theorem b05_weightsQ (side : Fin 2) :
 (∀ atom, 0 ≤ b05WeightQ side atom) ∧ (∑ atom : Fin 2, b05WeightQ side atom) = 1 := by
 decide +kernel +revert

theorem b05_sourcesQ (side atom : Fin 2) :
 (∀ i, 0 < 1+b05RayQ side atom*b04WQ i) ∧
 0 < b05MassQ side atom ∧
 b05MassQ side atom = (∑ i : Fin 32, b05GateQ (b05RayQ side atom) i)/(32+b04SQ*(b05RayQ side atom)^2) := by
 decide +kernel +revert

theorem b05_momentsQ :
 b05MomentsQ 0 = (∑ i : Fin 32, if b04Joint i = 0 then (1:ℚ) else 0) ∧
 b05MomentsQ 1 = 2*(∑ i : Fin 32, if b04Joint i = 0 then b04WQ i else 0) ∧
 b05MomentsQ 2 = (∑ i : Fin 32, if b04Joint i = 0 then (b04WQ i)^2 else 0) := by
 decide +kernel

theorem b05_post_stepQ (side atom : Fin 2) :
 b05PostQ side atom = b04KQᵀ *ᵥ b05GateQ (b05RayQ side atom) := by
 decide +kernel +revert

theorem b05_barycenterQ (side : Fin 2) :
 (∑ atom : Fin 2, b05WeightQ side atom • b05ChartDensityQ (b05RayQ side atom)) = b05BarycenterQ := by
 decide +kernel +revert

theorem b05_root_squaresQ (side atom : Fin 2) :
 (∀ i, 0 ≤ b05LoQ side atom i ∧ 0 ≤ b05HiQ side atom i ∧
 (b05LoQ side atom i)^2 ≤ b05PostQ side atom i ∧
 b05PostQ side atom i ≤ (b05HiQ side atom i)^2) ∧
 0 < (∑ i : Fin 32, b05LoQ side atom i) := by
 decide +kernel +revert

theorem b05_chart_lower_checkQ (side atom : Fin 2) :
 0 ≤ ∑ i : Fin 32, lowerLinearRootQ
 (fun i => (32/b04SQ)*b04WQ i-b05LowerQ side atom)
 (b05LoQ side atom) (b05HiQ side atom) i := by
 decide +kernel +revert

theorem b05_chart_upper_checkQ (side atom : Fin 2) :
 0 ≤ ∑ i : Fin 32, lowerLinearRootQ
 (fun i => b05UpperQ side atom-(32/b04SQ)*b04WQ i)
 (b05LoQ side atom) (b05HiQ side atom) i := by
 decide +kernel +revert

theorem b05_square_chart_checkQ (side atom : Fin 2) :
 b05LowerQ side atom ≤ b05UpperQ side atom ∧ b05UpperQ side atom < 0 ∧
 b05SqLowerQ side atom = (b05UpperQ side atom)^2 ∧
 b05SqUpperQ side atom = (b05LowerQ side atom)^2 := by
 decide +kernel +revert

theorem b05_read_lower_checkQ (side atom : Fin 2) :
 0 ≤ b05MomentsQ 0-32*b05ReadLowerQ side atom+
 linearLowerQ (b05MomentsQ 1) (b05LowerQ side atom) (b05UpperQ side atom)+
 linearLowerQ (b05MomentsQ 2-b04SQ*b05ReadLowerQ side atom)
 (b05SqLowerQ side atom) (b05SqUpperQ side atom) := by
 decide +kernel +revert

theorem b05_read_upper_checkQ (side atom : Fin 2) :
 0 ≤ 32*b05ReadUpperQ side atom-b05MomentsQ 0+
 linearLowerQ (-b05MomentsQ 1) (b05LowerQ side atom) (b05UpperQ side atom)+
 linearLowerQ (b04SQ*b05ReadUpperQ side atom-b05MomentsQ 2)
 (b05SqLowerQ side atom) (b05SqUpperQ side atom) := by
 decide +kernel +revert

theorem b05_word_gapQ :
 (∑ atom : Fin 2, b05WeightQ 0 atom*b05MassQ 0 atom*b05ReadUpperQ 0 atom) <
 (∑ atom : Fin 2, b05WeightQ 1 atom*b05MassQ 1 atom*b05ReadLowerQ 1 atom) := by
 decide +kernel

end BornCalculus
