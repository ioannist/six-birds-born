import BornCalculus.Frame

namespace BornCalculus
open Matrix
open scoped MatrixOrder BigOperators
set_option maxHeartbeats 0

/-- The 2x2 Cayley–Hamilton identity used by the executable radical formula. -/
theorem matrix_two_characteristic (C : M2) :
 C * C - (trace C) • C + C.det • (1 : M2) = 0 := by
 ext i j
 fin_cases i <;> fin_cases j <;>
   simp [mul_apply, trace, Fin.sum_univ_two, Matrix.det_fin_two] <;> ring

/-- A square-root certificate must select the positive scalar radicals. Its
matrix root is then PSD and unique, not merely a matrix whose square is C. -/
theorem principal_formula_certificate (C : M2) (hC : C.PosSemidef)
 (D Z : ℝ) (hD : 0 ≤ D) (hZ : 0 < Z)
 (hd : D * D = C.det) (hz : Z * Z = trace C + 2 * D) :
 let A := Z⁻¹ • (C + D • (1 : M2))
 A.PosSemidef ∧ A * A = C ∧ A = CFC.sqrt C := by
 let A := Z⁻¹ • (C + D • (1 : M2))
 have hA : A.PosSemidef :=
   (hC.add (Matrix.PosSemidef.one.smul hD)).smul (inv_nonneg.mpr hZ.le)
 have hchar := matrix_two_characteristic C
 have hrel : C * C + C.det • (1 : M2) = (trace C) • C := by
   apply sub_eq_zero.mp
   convert hchar using 1 <;> abel
 have hnum : (C + D • (1 : M2)) * (C + D • (1 : M2)) = (Z * Z) • C := by
   calc
     (C + D • (1 : M2)) * (C + D • (1 : M2)) =
       (C * C + (D * D) • (1 : M2)) + (2 * D) • C := by
         simp [Matrix.mul_add, Matrix.add_mul, smul_smul]
         module
     _ = (trace C) • C + (2 * D) • C := by rw [hd, hrel]
     _ = (Z * Z) • C := by rw [← add_smul, hz]
 have hs : A * A = C := by
   have hs : Z⁻¹ * (Z⁻¹ * (Z * Z)) = 1 := by field_simp
   simp only [A, Matrix.smul_mul, Matrix.mul_smul, smul_smul, hnum, hs, one_smul]
 have he : A = CFC.sqrt C := by
   apply (CFC.sq_eq_sq_iff A (CFC.sqrt C) hA.nonneg (CFC.sqrt_nonneg C)).mp
   simp only [pow_two, hs, CFC.sqrt_mul_sqrt_self C hC.nonneg]
 exact ⟨hA, hs, he⟩

noncomputable def principalRadical (C : M2) : M2 :=
 if C = 0 then 0 else
   (Real.sqrt (trace C + 2 * Real.sqrt C.det))⁻¹ •
     (C + Real.sqrt C.det • (1 : M2))

theorem psd_trace_positive_of_ne_zero (C : M2) (hC : C.PosSemidef) (hc : C ≠ 0) :
 0 < trace C := by
 have hn := hC.trace_nonneg
 have hz : trace C ≠ 0 := fun h => hc ((psd_trace_zero_iff C hC).mp h)
 exact lt_of_le_of_ne hn (Ne.symm hz)

/-- This is exactly the piecewise zero/nonzero formula implemented by
arithmetic.principal, including singular nonzero effects. -/
theorem principalRadical_eq_sqrt (C : M2) (hC : C.PosSemidef) :
 principalRadical C = CFC.sqrt C := by
 by_cases hc : C = 0
 · subst C
   simp [principalRadical]
 · have ht := psd_trace_positive_of_ne_zero C hC hc
   have hd : 0 ≤ C.det := hC.det_nonneg
   have hz : 0 < trace C + 2 * Real.sqrt C.det :=
     add_pos_of_pos_of_nonneg ht (mul_nonneg (by norm_num) (Real.sqrt_nonneg _))
   have he := principal_formula_certificate C hC (Real.sqrt C.det)
     (Real.sqrt (trace C + 2 * Real.sqrt C.det)) (Real.sqrt_nonneg _)
     (Real.sqrt_pos.mpr hz) (Real.mul_self_sqrt hd) (Real.mul_self_sqrt hz.le)
   simpa only [principalRadical, if_neg hc] using he.2.2

theorem frame_determinant_invariant (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁)
 (C : M2) : (toOrth g₀ g₁ C).det = C.det := by
 have hs₀ := (Real.sqrt_pos.mpr h₀).ne'
 have hs₁ := (Real.sqrt_pos.mpr h₁).ne'
 simp [toOrth, frameS, frameSi, Matrix.det_fin_two]
 field_simp

theorem principalRadical_frame_correspondence (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁)
 (C : M2) :
 toOrth g₀ g₁ (principalRadical C) = principalRadical (toOrth g₀ g₁ C) := by
 have hf := frame_coordinate_transfer g₀ g₁ h₀ h₁
 by_cases hc : C = 0
 · subst C
   simp [principalRadical, toOrth]
 · have ho : toOrth g₀ g₁ C ≠ 0 := by
     intro hz
     have hh := congrArg (fromOrth g₀ g₁) hz
     rw [hf.inverse_left] at hh
     have hzero : fromOrth g₀ g₁ (0 : M2) = 0 := by simp [fromOrth]
     rw [hzero] at hh
     exact hc hh
   simp only [principalRadical, if_neg hc, if_neg ho, hf.scalar,
     hf.addition, hf.unit, hf.trace, frame_determinant_invariant g₀ g₁ h₀ h₁]

/-- The executable scalar formula is the principal G-root on every positive
diagonal metric, not just on the finite numerical controls. -/
theorem g_principalRadical_eq_root (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁)
 (C : M2) (hC : GPositive g₀ g₁ C) : principalRadical C = gRoot g₀ g₁ C := by
 have hf := frame_coordinate_transfer g₀ g₁ h₀ h₁
 have he : toOrth g₀ g₁ (principalRadical C) = toOrth g₀ g₁ (gRoot g₀ g₁ C) := by
   rw [principalRadical_frame_correspondence g₀ g₁ h₀ h₁,
     principalRadical_eq_sqrt _ ((hf.positive C).mp hC), hf.principal_roots]
 simpa only [hf.inverse_left] using congrArg (fromOrth g₀ g₁) he

/-- The two-sided multiplication used by Python is the metric-adjoint Kraus
congruence, because the principal G-root is G-self-adjoint. -/
theorem g_principalRadical_selfadjoint (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁)
 (C : M2) (hC : GPositive g₀ g₁ C) :
 gAdjoint g₀ g₁ (principalRadical C) = principalRadical C := by
 have hf := frame_coordinate_transfer g₀ g₁ h₀ h₁
 apply (hf.selfadjoint _).mpr
 rw [principalRadical_frame_correspondence g₀ g₁ h₀ h₁,
   principalRadical_eq_sqrt _ ((hf.positive C).mp hC)]
 exact (CFC.sqrt_nonneg _).posSemidef.isHermitian

theorem g_principalRadical_branch_correspondence (g₀ g₁ : ℝ)
 (h₀ : 0 < g₀) (h₁ : 0 < g₁) (C R : M2) (hC : GPositive g₀ g₁ C) :
 toOrth g₀ g₁ (principalRadical C * R * principalRadical C) =
   branch (CFC.sqrt (toOrth g₀ g₁ C)) (toOrth g₀ g₁ R) := by
 have hf := frame_coordinate_transfer g₀ g₁ h₀ h₁
 have ht : (CFC.sqrt (toOrth g₀ g₁ C))ᵀ = CFC.sqrt (toOrth g₀ g₁ C) := by
   simpa only [Matrix.conjTranspose_eq_transpose_of_trivial] using
     (CFC.sqrt_nonneg (toOrth g₀ g₁ C)).posSemidef.isHermitian
 rw [hf.multiplication, hf.multiplication,
   principalRadical_frame_correspondence g₀ g₁ h₀ h₁,
   principalRadical_eq_sqrt _ ((hf.positive C).mp hC)]
 simp only [branch, ht]

theorem g_principalRadical_branch_positive (g₀ g₁ : ℝ)
 (h₀ : 0 < g₀) (h₁ : 0 < g₁) (C : M2) (hC : GPositive g₀ g₁ C)
 (R : GDensity g₀ g₁) :
 GPositive g₀ g₁ (principalRadical C * R.val * principalRadical C) := by
 have hf := frame_coordinate_transfer g₀ g₁ h₀ h₁
 rw [hf.positive, g_principalRadical_branch_correspondence g₀ g₁ h₀ h₁ C R.val hC]
 exact branch_psd _ _ ((hf.density_domain R.val).mp R.property).1

theorem principalRadical_commute (C R : M2) (h : C * R = R * C) :
 principalRadical C * R = R * principalRadical C := by
 by_cases hc : C = 0
 · subst C
   simp [principalRadical]
 · simp [principalRadical, hc, Matrix.smul_mul, Matrix.mul_smul,
     Matrix.add_mul, Matrix.mul_add, h]

theorem g_principalRadical_square (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁)
 (C : M2) (hC : GPositive g₀ g₁ C) : principalRadical C * principalRadical C = C := by
 have hf := frame_coordinate_transfer g₀ g₁ h₀ h₁
 have he : toOrth g₀ g₁ (principalRadical C * principalRadical C) = toOrth g₀ g₁ C := by
   rw [hf.multiplication, principalRadical_frame_correspondence g₀ g₁ h₀ h₁,
     principalRadical_eq_sqrt _ ((hf.positive C).mp hC),
     CFC.sqrt_mul_sqrt_self _ ((hf.positive C).mp hC).nonneg]
 simpa only [hf.inverse_left] using congrArg (fromOrth g₀ g₁) he

/-- Commuting rational states can be updated exactly using C*R, even when
the principal root itself has irrational entries. This also certifies the
zero-support cases that interval multiplication alone cannot resolve. -/
theorem g_principalRadical_commuting_branch (g₀ g₁ : ℝ)
 (h₀ : 0 < g₀) (h₁ : 0 < g₁) (C R : M2) (hC : GPositive g₀ g₁ C)
 (h : C * R = R * C) : principalRadical C * R * principalRadical C = C * R := by
 rw [principalRadical_commute C R h, Matrix.mul_assoc,
   g_principalRadical_square g₀ g₁ h₀ h₁ C hC, ← h]

end BornCalculus
