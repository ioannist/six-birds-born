import BornCalculus.General.Frame

namespace BornCalculus.General
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0
variable {n : ℕ}

theorem effect_coordinates (F : CenteredFrame n) (S : Finset (Fin n)) :
    effect F S = !![(S.card:ℝ)/(n:ℝ), (∑ i ∈ S, F.w i)/(n:ℝ);
      (∑ i ∈ S, F.w i)/F.s, (∑ i ∈ S, (F.w i)^2)/F.s] := by
  ext a b
  fin_cases a <;> fin_cases b <;>
    simp [effect,parent,Matrix.sum_apply,div_eq_mul_inv,←Finset.sum_mul]

theorem variance_identity {α : Type*} (S : Finset α) (w : α → ℝ) :
    (∑ i ∈ S, ∑ j ∈ S, (w i-w j)^2) =
      2*((S.card:ℝ)*(∑ i ∈ S, (w i)^2)-(∑ i ∈ S, w i)^2) := by
  simp_rw [sub_sq]
  simp only [Finset.sum_add_distrib,Finset.sum_sub_distrib,Finset.sum_const,nsmul_eq_mul,
    ←Finset.mul_sum,←Finset.sum_mul]
  ring

theorem effect_determinant (F : CenteredFrame n) (S : Finset (Fin n)) :
    (effect F S).det = ((S.card:ℝ)*(∑ i ∈ S, (F.w i)^2)-(∑ i ∈ S, F.w i)^2)/((n:ℝ)*F.s) := by
  rw [effect_coordinates,Matrix.det_fin_two]
  simp
  field_simp [(size_positive F).ne',F.positive.ne']

theorem effect_determinant_variance (F : CenteredFrame n) (S : Finset (Fin n)) :
    (effect F S).det = (∑ i ∈ S, ∑ j ∈ S, (F.w i-F.w j)^2)/(2*(n:ℝ)*F.s) := by
  rw [variance_identity,effect_determinant]
  ring

theorem effect_determinant_nonnegative (F : CenteredFrame n) (S : Finset (Fin n)) :
    0 ≤ (effect F S).det := by
  rw [effect_determinant_variance]
  exact div_nonneg (Finset.sum_nonneg (fun i _ => Finset.sum_nonneg (fun j _ => sq_nonneg _)))
    (by have := size_positive F; have := F.positive; positivity)

/-- Includes the empty block, where pairwise constancy is vacuous. -/
theorem effect_singular_iff_constant (F : CenteredFrame n) (S : Finset (Fin n)) :
    (effect F S).det = 0 ↔ ∀ i ∈ S, ∀ j ∈ S, F.w i = F.w j := by
  rw [effect_determinant_variance,div_eq_zero_iff]
  have hd : (2*(n:ℝ)*F.s) ≠ 0 := by
    have := (size_positive F).ne'; have := F.positive.ne'; positivity
  simp only [hd,or_false]
  rw [Finset.sum_eq_zero_iff_of_nonneg (fun i _ => Finset.sum_nonneg (fun j _ => sq_nonneg _))]
  simp_rw [Finset.sum_eq_zero_iff_of_nonneg (fun j _ => sq_nonneg _),sq_eq_zero_iff,sub_eq_zero]

theorem active_effect_singular_iff (F : CenteredFrame n) (S : Finset (Fin n)) (hS : S.Nonempty) :
    (effect F S).det = 0 ↔ ∃ c : ℝ, ∀ i ∈ S, F.w i = c := by
  rw [effect_singular_iff_constant]
  constructor
  · intro h
    obtain ⟨j,hj⟩ := hS
    exact ⟨F.w j,fun i hi => h i hi j hj⟩
  · rintro ⟨c,h⟩ i hi j hj
    exact (h i hi).trans (h j hj).symm

theorem lens_singular_iff_constant {L : Type*} [Fintype L] [DecidableEq L]
    (F : CenteredFrame n) (q : Fin n → L) (a : L) :
    (lens F q a).det = 0 ↔ ∀ i j, q i = a → q j = a → F.w i = F.w j := by
  rw [lens_effect,effect_singular_iff_constant]
  simp only [Finset.mem_filter,Finset.mem_univ,true_and]
  constructor
  · intro h i j hi hj; exact h i hi j hj
  · intro h i hi j hj; exact h i j hi hj

theorem parent_singular_nonzero (F : CenteredFrame n) (i : Fin n) :
    (parent F i).det = 0 ∧ parent F i ≠ 0 := by
  constructor
  · rw [←effect_singleton F i,effect_singular_iff_constant]
    simp
  · intro h
    have he := congrArg (fun A : M2 => A 0 0) h
    simp [parent,(size_positive F).ne'] at he

/-- No singleton assumption: the already existing 32-state effects satisfy the
    same exact equality criterion. -/
theorem frame32_lens_singular_iff {m : ℕ} (F : CenteredFrame32)
    (q : Fin 32 → Fin m) (a : Fin m) :
    (frameLens F q a).det = 0 ↔ ∀ i j, q i = a → q j = a → F.w i = F.w j := by
  exact lens_singular_iff_constant (of32 F) q a

theorem det_toOrth (F : CenteredFrame n) (A : M2) :
    (toOrth n F.s A).det = A.det := by
  have hn := (Real.sqrt_pos.mpr (size_positive F)).ne'
  have hs := (Real.sqrt_pos.mpr F.positive).ne'
  simp [toOrth,Matrix.det_mul,frameS,frameSi,Matrix.det_fin_two]
  field_simp

theorem orth_effect_determinant_variance (F : CenteredFrame n) (S : Finset (Fin n)) :
    (toOrth n F.s (effect F S)).det =
      (∑ i ∈ S, ∑ j ∈ S, (F.w i-F.w j)^2)/(2*(n:ℝ)*F.s) := by
  rw [det_toOrth,effect_determinant_variance]
theorem orth_effect_singular_iff_constant (F : CenteredFrame n) (S : Finset (Fin n)) :
    (toOrth n F.s (effect F S)).det = 0 ↔ ∀ i ∈ S, ∀ j ∈ S, F.w i = F.w j := by
  rw [det_toOrth,effect_singular_iff_constant]

end BornCalculus.General
