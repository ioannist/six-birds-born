import BornCalculus.SixStates

namespace BornCalculus
open scoped BigOperators
set_option maxHeartbeats 0

structure FiniteSixModel (Λ : Type*) [Fintype Λ] where
 base : Λ → ℝ
 plus : Fin 3 → Λ → ℝ
 minus : Fin 3 → Λ → ℝ
 response : Fin 3 → Λ → ℝ
 base_nonnegative : ∀ x, 0 ≤ base x
 plus_nonnegative : ∀ i x, 0 ≤ plus i x
 minus_nonnegative : ∀ i x, 0 ≤ minus i x
 base_normalized : ∑ x, base x = 1
 plus_normalized : ∀ i, ∑ x, plus i x = 1
 minus_normalized : ∀ i, ∑ x, minus i x = 1
 response_nonnegative : ∀ i x, 0 ≤ response i x
 response_le_one : ∀ i x, response i x ≤ 1
 pair : ∀ i x, plus i x + minus i x = 2 * base x
 trine : ∀ x, ∑ i, plus i x = 3 * base x
 perfect_plus : ∀ i, ∑ x, plus i x * response i x = 1
 perfect_minus : ∀ i, ∑ x, minus i x * response i x = 0

theorem finite_six_disjoint {Λ : Type*} [Fintype Λ] (M : FiniteSixModel Λ)
 (i : Fin 3) (x : Λ) : M.plus i x = 0 ∨ M.minus i x = 0 := by
 classical
 have hp : ∑ y, M.plus i y * (1 - M.response i y) = 0 := by
  simp_rw [mul_sub,mul_one]; rw [Finset.sum_sub_distrib,M.plus_normalized,M.perfect_plus]; ring
 have hpn := (Finset.sum_eq_zero_iff_of_nonneg (fun y (_ : y ∈ Finset.univ) ↦
  mul_nonneg (M.plus_nonnegative i y) (sub_nonneg.mpr (M.response_le_one i y)))).mp hp x (Finset.mem_univ x)
 have hmn := (Finset.sum_eq_zero_iff_of_nonneg (fun y (_ : y ∈ Finset.univ) ↦
  mul_nonneg (M.minus_nonnegative i y) (M.response_nonnegative i y))).mp (M.perfect_minus i) x (Finset.mem_univ x)
 rcases mul_eq_zero.mp hpn with hp0|hr
 · exact Or.inl hp0
 · have hr1 : M.response i x = 1 := by linarith
   exact Or.inr (by simpa [hr1] using hmn)

theorem finite_six_binary_ratio {Λ : Type*} [Fintype Λ] (M : FiniteSixModel Λ)
 (x : Λ) (hx : 0 < M.base x) (i : Fin 3) :
 M.plus i x / M.base x = 0 ∨ M.plus i x / M.base x = 2 := by
 rcases finite_six_disjoint M i x with h|h
 · exact Or.inl (by simp [h])
 · right
   have hp := M.pair i x
   rw [h,add_zero] at hp
   rw [hp]; field_simp

theorem finite_six_no_go {Λ : Type*} [Fintype Λ] (M : FiniteSixModel Λ) : False := by
 classical
 have hb : 0 < ∑ x, M.base x := by rw [M.base_normalized]; norm_num
 obtain ⟨x,_,hx⟩ := (Finset.sum_pos_iff_of_nonneg (fun y (_ : y ∈ Finset.univ) ↦ M.base_nonnegative y)).mp hb
 have hp := binary_trine_parity (M.plus 0 x/M.base x) (M.plus 1 x/M.base x) (M.plus 2 x/M.base x)
  (finite_six_binary_ratio M x hx 0) (finite_six_binary_ratio M x hx 1) (finite_six_binary_ratio M x hx 2)
 apply hp
 have ht := M.trine x
 rw [Fin.sum_univ_three] at ht
 rw [← add_div,← add_div,ht]
 field_simp

/- The concrete-table bridge has exactly the table's probabilities plus the
 declared preparation-mixture identities. It assumes no deterministic response. -/
structure FiniteTableRepresentation (Λ : Type*) [Fintype Λ] where
 base : Λ → ℝ
 preparation : Fin 6 → Λ → ℝ
 response : Fin 3 → Λ → ℝ
 base_nonnegative : ∀ x, 0 ≤ base x
 preparation_nonnegative : ∀ i x, 0 ≤ preparation i x
 base_normalized : ∑ x, base x = 1
 preparation_normalized : ∀ i, ∑ x, preparation i x = 1
 response_bounds : ∀ i x, 0 ≤ response i x ∧ response i x ≤ 1
 pair_mixture : ∀ i : Fin 3, ∀ x,
  (1/2 : ℝ) * (preparation ⟨i.val,by omega⟩ x + preparation ⟨i.val+3,by omega⟩ x)=base x
 trine_mixture : ∀ x, (1/3 : ℝ) * (∑ i : Fin 3, preparation ⟨i.val,by omega⟩ x)=base x
 table : ∀ i j, ∑ x, preparation i x * response j x = pairing (sixState i) (sharp j)

def finite_table_bridge {Λ : Type*} [Fintype Λ] (M : FiniteTableRepresentation Λ) : FiniteSixModel Λ where
 base := M.base
 plus i := M.preparation ⟨i.val,by omega⟩
 minus i := M.preparation ⟨i.val+3,by omega⟩
 response := M.response
 base_nonnegative := M.base_nonnegative
 plus_nonnegative i := M.preparation_nonnegative _
 minus_nonnegative i := M.preparation_nonnegative _
 base_normalized := M.base_normalized
 plus_normalized i := M.preparation_normalized _
 minus_normalized i := M.preparation_normalized _
 response_nonnegative i x := (M.response_bounds i x).1
 response_le_one i x := (M.response_bounds i x).2
 pair i x := by have h := M.pair_mixture i x; linarith
 trine x := by have h := M.trine_mixture x; linarith
 perfect_plus i := by
  rw [M.table,six_state_probability_table]; fin_cases i <;> norm_num [sixTable]
 perfect_minus i := by
  rw [M.table,six_state_probability_table]; fin_cases i <;> norm_num [sixTable]

theorem finite_table_representation_impossible {Λ : Type*} [Fintype Λ]
 (M : FiniteTableRepresentation Λ) : False := finite_six_no_go (finite_table_bridge M)
end BornCalculus
