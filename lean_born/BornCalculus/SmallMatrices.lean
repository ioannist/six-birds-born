import BornCalculus.Frame

namespace BornCalculus
open Matrix
open scoped MatrixOrder BigOperators

/-- An explicit LDL factorization proves the strict 2x2 scalar criterion. -/
theorem symmetric_two_posDef (a b d : ℝ) (ha : 0 < a)
 (hd : 0 < a * d - b^2) : (!![a,b;b,d] : M2).PosDef := by
 let L : M2 := !![1,0;b/a,1]
 let D : M2 := Matrix.diagonal ![a,(a*d-b^2)/a]
 have hD : D.PosDef := Matrix.PosDef.diagonal (by
   intro i
   fin_cases i
   · exact ha
   · exact div_pos hd ha)
 have hL : IsUnit L := by
   apply (Matrix.isUnit_iff_isUnit_det _).mpr
   norm_num [L, Matrix.det_fin_two]
 have he : L * D * Lᵀ = (!![a,b;b,d] : M2) := by
   ext i j
   fin_cases i <;> fin_cases j <;>
     simp [L, D, mul_apply, vecMul, dotProduct, transpose_apply, Fin.sum_univ_two] <;>
     field_simp <;> ring
 have hp := hD.mul_mul_conjTranspose_same
   (Matrix.vecMul_injective_iff_isUnit.mpr hL)
 simpa only [Matrix.conjTranspose_eq_transpose_of_trivial, he] using hp

theorem g_positive_of_two_checks (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁)
 (C : M2) (hs : g₀ * C 0 1 = g₁ * C 1 0)
 (ha : 0 < C 0 0) (hd : 0 < C.det) : GPositive g₀ g₁ C := by
 have he : frameG g₀ g₁ * C =
   (!![g₀*C 0 0,g₀*C 0 1;g₀*C 0 1,g₁*C 1 1] : M2) := by
   ext i j
   fin_cases i <;> fin_cases j <;>
     simp [frameG, mul_apply, Fin.sum_univ_two, hs]
 have hdet : 0 < (g₀*C 0 0)*(g₁*C 1 1)-(g₀*C 0 1)^2 := by
   have hpos : 0 < (g₀*g₁)*C.det := mul_pos (mul_pos h₀ h₁) hd
   have heq : (g₀*C 0 0)*(g₁*C 1 1)-(g₀*C 0 1)^2 = (g₀*g₁)*C.det := by
     simp only [Matrix.det_fin_two]
     rw [pow_two]
     calc
       _ = (g₀*C 0 0)*(g₁*C 1 1)-(g₀*C 0 1)*(g₁*C 1 0) := by rw [hs]
       _ = _ := by ring
   rw [heq]
   exact hpos
 rw [GPositive, he]
 exact (symmetric_two_posDef _ _ _ (mul_pos h₀ ha) hdet).posSemidef

theorem complete_g_effect_domains {ι : Type*} [Fintype ι]
 (g₀ g₁ : ℝ) (C : ι → M2)
 (hp : ∀ i, GPositive g₀ g₁ (C i)) (hn : ∑ i, C i = 1) (i : ι) :
 GIsEffect g₀ g₁ (C i) := by
 classical
 refine ⟨hp i, ?_⟩
 have hs : (∑ j ∈ Finset.univ.erase i, C j) + C i = 1 := by
   rw [Finset.sum_erase_add _ _ (Finset.mem_univ i)]
   exact hn
 have he : 1-C i = ∑ j ∈ Finset.univ.erase i, C j := by
   rw [← hs]
   abel
 rw [he]
 unfold GPositive
 rw [Matrix.mul_sum]
 exact Matrix.posSemidef_sum _ (fun j _ => hp j)

end BornCalculus
