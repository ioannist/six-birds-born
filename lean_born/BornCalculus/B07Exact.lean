import BornCalculus.B07Inputs
import BornCalculus.B05Exact
namespace BornCalculus
open Matrix
set_option maxHeartbeats 0
set_option maxRecDepth 100000

def b07CQ (o : Fin 2) : Matrix (Fin 2) (Fin 2) ℚ := if o = 0 then b06RawQ 1 else b06PackageQ 0
def b07DQ (o : Fin 2) : Matrix (Fin 2) (Fin 2) ℚ := if o = 0 then b06PackageQ 0 else b06RawQ 1

theorem b07_coefficient_checks (o : Fin 2) :
 0 < b07TraceQ o ∧ 0 < b07DetQ o ∧
 b07TraceQ o = trace (b07CQ o) ∧ b07DetQ o = (b07CQ o).det ∧
 b07ConstantQ o = (b07CQ o*b07DQ o*b07CQ o) 0 0+(b07CQ o).det*b07DQ o 0 0 ∧
 b07LinearQ o = (b07DQ o*b07CQ o+b07CQ o*b07DQ o) 0 0 := by decide +kernel +revert

theorem b07_root_checks (o : Fin 2) :
 0 ≤ b07LoQ o ∧ 0 ≤ b07HiQ o ∧ (b07LoQ o)^2 ≤ b07DetQ o ∧ b07DetQ o ≤ (b07HiQ o)^2 := by
 decide +kernel +revert

theorem b07_bound_checks (o : Fin 2) :
 0 ≤ b07ConstantQ o-b07LowerQ o*b07TraceQ o+
   linearLowerQ (b07LinearQ o-2*b07LowerQ o) (b07LoQ o) (b07HiQ o) ∧
 0 ≤ b07UpperQ o*b07TraceQ o-b07ConstantQ o+
   linearLowerQ (2*b07UpperQ o-b07LinearQ o) (b07LoQ o) (b07HiQ o) := by decide +kernel +revert

theorem b07_order_gap : b07UpperQ 0 < b07LowerQ 1 ∨ b07UpperQ 1 < b07LowerQ 0 := by decide +kernel
end BornCalculus
