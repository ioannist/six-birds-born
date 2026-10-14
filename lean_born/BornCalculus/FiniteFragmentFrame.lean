import BornCalculus.FiniteProgramFragment

namespace BornCalculus
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0

/-- Coordinate conjugacy rescales exactly the third basis column. This
connects the concrete G-coordinate determinant criterion to the proved real
symmetric-matrix separation theorem. -/
theorem frame_fragment_basis_matrix (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁)
 (E : Fin 3 → M2) :
 fragmentBasisMatrix (fun i => toOrth g₀ g₁ (E i)) =
   fragmentBasisMatrix E * Matrix.diagonal ![1, 1, Real.sqrt g₀ / Real.sqrt g₁] := by
 have hs₀ := (Real.sqrt_pos.mpr h₀).ne'
 have hs₁ := (Real.sqrt_pos.mpr h₁).ne'
 ext i j
 fin_cases j <;>
   simp [fragmentBasisMatrix, toOrth, frameS, frameSi,
     mul_apply, Fin.sum_univ_two, Fin.sum_univ_three] <;> field_simp

theorem frame_fragment_basis_det (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁)
 (E : Fin 3 → M2) :
 (fragmentBasisMatrix (fun i => toOrth g₀ g₁ (E i))).det =
   (fragmentBasisMatrix E).det * (Real.sqrt g₀ / Real.sqrt g₁) := by
 rw [frame_fragment_basis_matrix g₀ g₁ h₀ h₁, Matrix.det_mul]
 simp [Matrix.det_diagonal, Fin.prod_univ_three]

/-- The same three-effect determinant excludes every G-density. Metric
positivity is required explicitly, and no scalar-separation hypothesis is
substituted for informational completeness. -/
theorem g_finite_fragment_no_density_representation
 (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁)
 (E : Fin 3 → GEffect g₀ g₁) (ε : ℝ) (hε : 0 < ε)
 (hdet : (fragmentBasisMatrix (fun i => (E i).val)).det ≠ 0) :
 ¬ ∃ R : GDensity g₀ g₁, ∀ i,
   pairing R.val (E i).val = pairing (fragmentWitness ε) (E i).val := by
 have hf := frame_coordinate_transfer g₀ g₁ h₀ h₁
 let F : Fin 3 → Effect := fun i =>
   ⟨toOrth g₀ g₁ (E i).val, (hf.effect_domain _).mp (E i).property⟩
 have hF : (fragmentBasisMatrix (fun i => (F i).val)).det ≠ 0 := by
   change (fragmentBasisMatrix (fun i => toOrth g₀ g₁ (E i).val)).det ≠ 0
   rw [frame_fragment_basis_det g₀ g₁ h₀ h₁]
   exact mul_ne_zero hdet
     (div_ne_zero (Real.sqrt_pos.mpr h₀).ne' (Real.sqrt_pos.mpr h₁).ne')
 rintro ⟨R, hR⟩
 apply finite_fragment_no_density_representation F ε hε hF
 refine ⟨⟨toOrth g₀ g₁ R.val, (hf.density_domain _).mp R.property⟩, ?_⟩
 intro i
 change pairing (toOrth g₀ g₁ R.val) (toOrth g₀ g₁ (E i).val) =
   pairing (fragmentWitness ε) (toOrth g₀ g₁ (E i).val)
 have hw := hf.trace_pairing (fragmentWitness ε) (E i).val
 rw [fragmentWitness_frame_invariant g₀ g₁ h₀ h₁] at hw
 rw [hf.trace_pairing, hw]
 exact hR i

end BornCalculus
