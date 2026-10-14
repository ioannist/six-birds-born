import BornCalculus.General.Basis

namespace BornCalculus.General
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0
variable {n : ℕ}

noncomputable def coefficients (F : CenteredFrame n) (p : Simplex n) : Fin 2 → ℝ :=
  (basis F)ᵀ *ᵥ (fun i => Real.sqrt (p.val i))

theorem coefficients_formula (F : CenteredFrame n) (p : Simplex n) :
    coefficients F p = ![(∑ i, Real.sqrt (p.val i))/Real.sqrt (n:ℝ),
      (∑ i, F.w i*Real.sqrt (p.val i))/Real.sqrt F.s] := by
  ext a
  fin_cases a
  · simp [coefficients,basis,mulVec,dotProduct,transpose_apply,div_eq_mul_inv,
      mul_comm,←Finset.mul_sum]
  · simp [coefficients,basis,mulVec,dotProduct,transpose_apply,div_mul_eq_mul_div,
      ←Finset.sum_div]

theorem coefficients_ne_zero (F : CenteredFrame n) (p : Simplex n) : coefficients F p ≠ 0 := by
  intro h
  have hp : 0 < (coefficients F p) 0 := by
    rw [coefficients_formula]
    exact div_pos (sqrt_sum_positive p) (Real.sqrt_pos.mpr (size_positive F))
  have hz := congrFun h 0
  exact hp.ne' hz

theorem normalized_coordinates (F : CenteredFrame n) (A H : ℝ) (hA : 0 < A) :
    toOrth n F.s (chartDensity n F.s (((n:ℝ)/F.s)*H/A)) =
      (A^2/(n:ℝ)+H^2/F.s)⁻¹ •
        vecMulVec ![A/Real.sqrt (n:ℝ),H/Real.sqrt F.s]
          ![A/Real.sqrt (n:ℝ),H/Real.sqrt F.s] := by
  have hn := (Real.sqrt_pos.mpr (size_positive F)).ne'
  have hs := (Real.sqrt_pos.mpr F.positive).ne'
  have hnn := Real.sq_sqrt (size_positive F).le
  have hss := Real.sq_sqrt F.positive.le
  have hd : A^2/(n:ℝ)+H^2/F.s ≠ 0 :=
    (add_pos_of_pos_of_nonneg (div_pos (sq_pos_of_pos hA) (size_positive F))
      (div_nonneg (sq_nonneg H) F.positive.le)).ne'
  have ht : (n:ℝ)+F.s*(((n:ℝ)/F.s)*H/A)^2 ≠ 0 :=
    (add_pos_of_pos_of_nonneg (size_positive F) (mul_nonneg F.positive.le (sq_nonneg _))).ne'
  ext a b
  fin_cases a <;> fin_cases b <;>
    simp [toOrth,frameS,frameSi,chartDensity,vecMulVec,mul_apply,Fin.sum_univ_two]
  all_goals
    field_simp [hn,hs,hA.ne',hd,ht,(size_positive F).ne',F.positive.ne']
    ring_nf
    simp only [hnn,hss]
    <;> ring

/-- Exactly the encoder definition in the paper: normalize Bᵀ sqrt(p), then
    take its rank-one projector, expressed using squared norm. -/
theorem encoding_normalized_projection (F : CenteredFrame n) (p : Simplex n) :
    toOrth n F.s (encoding F p) =
      ((coefficients F p) ⬝ᵥ (coefficients F p))⁻¹ •
        vecMulVec (coefficients F p) (coefficients F p) := by
  rw [encoding,rootChart,normalized_coordinates F _ _ (sqrt_sum_positive p),coefficients_formula]
  congr 2
  simp [dotProduct,Fin.sum_univ_two,←pow_two,div_pow,
    Real.sq_sqrt (size_positive F).le,Real.sq_sqrt F.positive.le]

end BornCalculus.General
