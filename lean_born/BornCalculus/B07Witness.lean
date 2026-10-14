import BornCalculus.B07Exact
import BornCalculus.B06Atomic
import BornCalculus.OrderFormula

namespace BornCalculus
open Matrix
set_option maxHeartbeats 0

noncomputable def b07C (o : Fin 2) : M2 := fun i j => (b07CQ o i j:ℝ)
noncomputable def b07D (o : Fin 2) : M2 := fun i j => (b07DQ o i j:ℝ)
noncomputable def b07Initial : M2 := !![1,0;0,0]
noncomputable def b07Word (o : Fin 2) : M2 := principalRadical (b07D o)*principalRadical (b07C o)
noncomputable def b07Probability (o : Fin 2) : ℝ :=
 pairing b07Initial (gAdjoint 32 b06S (b07Word o)*b07Word o)

theorem b07_initial_domain : GIsDensity 32 b06S b07Initial := by
 have he : b07Initial = chartDensity b06S 0 := by simp [b07Initial,chartDensity]
 rw [he]
 exact chartDensity_domain b06S 0 b06_s_positive

theorem b07_effect_domains (o : Fin 2) :
 GPositive 32 b06S (b07C o) ∧ GPositive 32 b06S (b07D o) := by
 fin_cases o
 · exact ⟨b06_raw_positive 1,b06_package_positive 0⟩
 · exact ⟨b06_package_positive 0,b06_raw_positive 1⟩

theorem b07_coefficients (o : Fin 2) :
 (b07TraceQ o:ℝ) = trace (b07C o) ∧ (b07DetQ o:ℝ) = (b07C o).det ∧
 (b07ConstantQ o:ℝ) = orderConstant (b07C o) (b07D o) ∧
 (b07LinearQ o:ℝ) = orderLinear (b07C o) (b07D o) := by
 have h := b07_coefficient_checks o
 refine ⟨?_,?_,?_,?_⟩
 · have hc := congrArg (fun q : ℚ => (q:ℝ)) h.2.2.1
   simpa [b07C,trace,Fin.sum_univ_two] using hc
 · have hc := congrArg (fun q : ℚ => (q:ℝ)) h.2.2.2.1
   simpa [b07C,Matrix.det_fin_two] using hc
 · have hc := congrArg (fun q : ℚ => (q:ℝ)) h.2.2.2.2.1
   simpa [b07C,b07D,orderConstant,Matrix.det_fin_two,mul_apply,Fin.sum_univ_two] using hc
 · have hc := congrArg (fun q : ℚ => (q:ℝ)) h.2.2.2.2.2
   simpa [b07C,b07D,orderLinear,mul_apply,Fin.sum_univ_two] using hc

theorem b07_probability_formula (o : Fin 2) : b07Probability o = orderRootValue (b07C o) (b07D o) := by
 have hc := b07_coefficients o
 have ht : 0 < trace (b07C o) := by rw [←hc.1]; exact_mod_cast (b07_coefficient_checks o).1
 have hd : 0 ≤ (b07C o).det := by rw [←hc.2.1]; exact_mod_cast (b07_coefficient_checks o).2.1.le
 rw [b07Probability,b07Word,principal_two_read_effect 32 b06S (by norm_num) b06_s_positive
   (b07C o) (b07D o) (b07_effect_domains o).1 (b07_effect_domains o).2]
 have he (M : M2) : pairing b07Initial M = M 0 0 := by
   simp [pairing,b07Initial,trace,mul_apply,Matrix.vecMul,dotProduct,Fin.sum_univ_two]
 rw [he,principal_two_read_formula _ _ ht hd]

private theorem b07_cast_linear (a lo hi : ℚ) :
 linearLower (a:ℝ) (lo:ℝ) (hi:ℝ) = (linearLowerQ a lo hi:ℝ) := by
 by_cases h : 0 ≤ a
 · have hr : (0:ℝ) ≤ (a:ℝ) := by exact_mod_cast h
   simp [linearLower,linearLowerQ,h,hr]
 · have hr : ¬(0:ℝ) ≤ (a:ℝ) := by exact_mod_cast h
   simp [linearLower,linearLowerQ,h,hr]

theorem b07_probability_bounds (o : Fin 2) :
 (b07LowerQ o:ℝ) ≤ b07Probability o ∧ b07Probability o ≤ (b07UpperQ o:ℝ) := by
 have hc := b07_coefficients o
 have ht : (0:ℝ) < (b07TraceQ o:ℝ) := by exact_mod_cast (b07_coefficient_checks o).1
 have hr := b07_root_checks o
 have hb : (b07LoQ o:ℝ) ≤ Real.sqrt (b07DetQ o:ℝ) ∧
   Real.sqrt (b07DetQ o:ℝ) ≤ (b07HiQ o:ℝ) := by
   apply sqrt_bounds_of_squared_bounds
   · exact_mod_cast hr.1
   · exact_mod_cast hr.2.1
   · exact_mod_cast hr.2.2.1
   · exact_mod_cast hr.2.2.2
 have hl : (0:ℝ) ≤ (b07ConstantQ o:ℝ)-(b07LowerQ o:ℝ)*(b07TraceQ o:ℝ)+
   linearLower ((b07LinearQ o:ℝ)-2*(b07LowerQ o:ℝ)) (b07LoQ o:ℝ) (b07HiQ o:ℝ) := by
   rw [show ((b07LinearQ o:ℝ)-2*(b07LowerQ o:ℝ)) =
     ((b07LinearQ o-2*b07LowerQ o:ℚ):ℝ) by simp,b07_cast_linear]
   exact_mod_cast (b07_bound_checks o).1
 have hu : (0:ℝ) ≤ (b07UpperQ o:ℝ)*(b07TraceQ o:ℝ)-(b07ConstantQ o:ℝ)+
   linearLower (2*(b07UpperQ o:ℝ)-(b07LinearQ o:ℝ)) (b07LoQ o:ℝ) (b07HiQ o:ℝ) := by
   rw [show (2*(b07UpperQ o:ℝ)-(b07LinearQ o:ℝ)) =
     ((2*b07UpperQ o-b07LinearQ o:ℚ):ℝ) by simp,b07_cast_linear]
   exact_mod_cast (b07_bound_checks o).2
 rw [b07_probability_formula,orderRootValue,←hc.1,←hc.2.1,←hc.2.2.1,←hc.2.2.2]
 exact linear_radical_ratio_bounds _ _ _ _ _ _ _ _ ht (Real.sqrt_nonneg _) hb.1 hb.2 hl hu

/-- The registered principal-root words give unequal laws under order
reversal. Disturbance alone proves neither contextuality nor incompatibility. -/
theorem b07_order_disturbance : b07Probability 0 ≠ b07Probability 1 := by
 have h0 := b07_probability_bounds 0
 have h1 := b07_probability_bounds 1
 have hg : (b07UpperQ 0:ℝ) < (b07LowerQ 1:ℝ) ∨ (b07UpperQ 1:ℝ) < (b07LowerQ 0:ℝ) := by
   exact_mod_cast b07_order_gap
 rcases hg with h | h <;> intro he <;> linarith

end BornCalculus
