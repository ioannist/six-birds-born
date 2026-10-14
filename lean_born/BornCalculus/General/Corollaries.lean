import BornCalculus.General.Inherited

namespace BornCalculus.General
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0
variable {n : ℕ}

theorem orth_effect_coordinates (F : CenteredFrame n) (S : Finset (Fin n)) :
    toOrth n F.s (effect F S) =
      !![(S.card:ℝ)/(n:ℝ),(∑ i ∈ S, F.w i)/(Real.sqrt (n:ℝ)*Real.sqrt F.s);
        (∑ i ∈ S, F.w i)/(Real.sqrt (n:ℝ)*Real.sqrt F.s),(∑ i ∈ S, (F.w i)^2)/F.s] := by
  have hn := (Real.sqrt_pos.mpr (size_positive F)).ne'
  have hs := (Real.sqrt_pos.mpr F.positive).ne'
  have hnn := Real.sq_sqrt (size_positive F).le
  have hss := Real.sq_sqrt F.positive.le
  rw [effect_coordinates]
  ext a b
  fin_cases a <;> fin_cases b <;>
    simp [toOrth,frameS,frameSi,mul_apply,Fin.sum_univ_two]
  all_goals
    field_simp [hn,hs,(size_positive F).ne',F.positive.ne']
    <;> simp [hnn,hss]
    <;> ring_nf
    <;> simp

theorem encoder_mixing_counterexample (F : CenteredFrame n) :
    ∃ p q : Simplex n, encoding F (mixedPreparation p q (1/2) (by norm_num) (by norm_num)) ≠
      (1/2:ℝ) • encoding F p + (1/2:ℝ) • encoding F q := by
  obtain ⟨lo,hi,_,_,hneg,hpos⟩ := extrema_straddle_zero F
  have hne : encoding F (point lo) ≠ encoding F (point hi) :=
    mt (point_encoding_eq_iff F lo hi).mp (ne_of_lt (hneg.trans hpos))
  refine ⟨point lo,point hi,?_⟩
  convert encoding_non_affine F (point lo) (point hi) hne (1/2) (by norm_num) (by norm_num) using 1
  norm_num

theorem frame32_all_set_trace (F : CenteredFrame32) (p : Simplex32) (S : Finset (Fin 32)) :
    projectedSquare (of32 F) p S = pairing (frameEncoding F p) (∑ i ∈ S, frameParent F i) :=
  projected_square_trace (of32 F) p S

theorem frame32_point_encoding_eq_iff (F : CenteredFrame32) (i j : Fin 32) :
    frameEncoding F (simplexPoint i) = frameEncoding F (simplexPoint j) ↔ F.w i = F.w j :=
  point_encoding_eq_iff (of32 F) i j

end BornCalculus.General
