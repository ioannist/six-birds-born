import BornCalculus.General.Trace

namespace BornCalculus.General
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0
variable {n : ℕ}

/-- The isometry B of the paper, with columns 1/sqrt(n) and w/sqrt(s). -/
noncomputable def basis (F : CenteredFrame n) : Matrix (Fin n) (Fin 2) ℝ :=
  fun i => ![(Real.sqrt (n:ℝ))⁻¹,F.w i/Real.sqrt F.s]

theorem basis_isometry (F : CenteredFrame n) : (basis F)ᵀ * basis F = 1 := by
  have hn := (Real.sqrt_pos.mpr (size_positive F)).ne'
  have hs := (Real.sqrt_pos.mpr F.positive).ne'
  have hnn := Real.sq_sqrt (size_positive F).le
  have hss := Real.sq_sqrt F.positive.le
  ext a b
  fin_cases a <;> fin_cases b
  · simp [basis,mul_apply,transpose_apply,←pow_two,hnn,(size_positive F).ne']
  · simp [basis,mul_apply,transpose_apply,div_eq_mul_inv,←Finset.sum_mul,
      ←Finset.mul_sum,F.centered]
  · simp [basis,mul_apply,transpose_apply,div_eq_mul_inv,←Finset.sum_mul,F.centered]
  · simp [basis,mul_apply,transpose_apply,←pow_two,div_pow,←Finset.sum_div,
      F.squared,hss,F.positive.ne']

theorem basis_projector (F : CenteredFrame n) : basis F * (basis F)ᵀ = projector F := by
  have hn := (Real.sqrt_pos.mpr (size_positive F)).ne'
  have hs := (Real.sqrt_pos.mpr F.positive).ne'
  have hnn := Real.sq_sqrt (size_positive F).le
  have hss := Real.sq_sqrt F.positive.le
  ext i j
  simp [basis,projector,mul_apply,Fin.sum_univ_two,transpose_apply]
  field_simp [hn,hs,(size_positive F).ne',F.positive.ne']
  simp only [hnn,hss]
  ring

/-- Coordinate compatibility: the general parent is exactly the compression
    of the singleton coordinate projector in the paper's orthonormal frame. -/
theorem orth_parent (F : CenteredFrame n) (i : Fin n) :
    toOrth n F.s (parent F i) =
      vecMulVec (![(Real.sqrt (n:ℝ))⁻¹,F.w i/Real.sqrt F.s])
        (![(Real.sqrt (n:ℝ))⁻¹,F.w i/Real.sqrt F.s]) := by
  have hn := (Real.sqrt_pos.mpr (size_positive F)).ne'
  have hs := (Real.sqrt_pos.mpr F.positive).ne'
  have hnn := Real.sq_sqrt (size_positive F).le
  have hss := Real.sq_sqrt F.positive.le
  ext a b
  fin_cases a <;> fin_cases b <;>
    simp [toOrth,frameS,frameSi,parent,mul_apply,Fin.sum_univ_two,vecMulVec]
  all_goals
    field_simp [hn,hs,(size_positive F).ne',F.positive.ne']
    simp [hnn,hss]
    <;> ring_nf
    <;> simp

theorem orth_effect_compression (F : CenteredFrame n) (S : Finset (Fin n)) :
    toOrth n F.s (effect F S) =
      (basis F)ᵀ * Matrix.diagonal (fun i => if i ∈ S then (1:ℝ) else 0) * basis F := by
  have he : toOrth n F.s (effect F S) = ∑ i ∈ S, toOrth n F.s (parent F i) := by
    simp [effect,toOrth,Matrix.mul_sum,Matrix.sum_mul]
  rw [he]
  simp_rw [orth_parent]
  ext a b
  simp only [Matrix.sum_apply,vecMulVec,Matrix.of_apply]
  rw [Matrix.mul_apply]
  simp only [Matrix.mul_diagonal,Matrix.transpose_apply]
  have hif (i : Fin n) :
      basis F i a*(if i ∈ S then (1:ℝ) else 0)*basis F i b =
        if i ∈ S then basis F i a*basis F i b else 0 := by split_ifs <;> simp
  simp_rw [hif]
  rw [←Finset.sum_filter]
  simp [basis]

end BornCalculus.General
