import BornCalculus.General.Basis
import BornCalculus.General.Determinant
import BornCalculus.FiniteFragment

namespace BornCalculus.General
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0
variable {n : ℕ}

theorem witness_toOrth (F : CenteredFrame n) (ε : ℝ) :
    toOrth n F.s (fragmentWitness ε) = fragmentWitness ε := by
  have hn := (Real.sqrt_pos.mpr (size_positive F)).ne'
  have hs := (Real.sqrt_pos.mpr F.positive).ne'
  ext a b
  fin_cases a <;> fin_cases b <;>
    simp [toOrth,frameS,frameSi,fragmentWitness,mul_apply,Fin.sum_univ_two,
      mul_comm,mul_assoc,hn,hs]

theorem witness_parent_pairing (F : CenteredFrame n) (ε : ℝ) (i : Fin n) :
    pairing (fragmentWitness ε) (parent F i) =
      1/(n:ℝ) + ε*(1/(n:ℝ)-(F.w i)^2/F.s) := by
  rw [fragmentWitness_pairing]; rfl

theorem square_le_norm (F : CenteredFrame n) (i : Fin n) : (F.w i)^2 ≤ F.s := by
  rw [←F.squared]
  exact Finset.single_le_sum (fun j _ => sq_nonneg _) (Finset.mem_univ i)

theorem witness_parent_positive (F : CenteredFrame n) (ε : ℝ)
    (hε : 0 < ε) (hsmall : ε < 1/(n:ℝ)) (i : Fin n) :
    0 < pairing (fragmentWitness ε) (parent F i) := by
  rw [witness_parent_pairing]
  have hb : (F.w i)^2/F.s ≤ 1 := (div_le_one F.positive).mpr (square_le_norm F i)
  have hn : 0 < 1/(n:ℝ) := one_div_pos.mpr (size_positive F)
  have hmul := mul_le_mul_of_nonneg_left hb hε.le
  nlinarith [mul_pos hε hn]

/-- Explicit uniform tolerance: every 0 < ε < 1/n works for every inherited
    nonempty proper set, stronger than mere existence of a small tolerance. -/
theorem witness_all_proper_sets (F : CenteredFrame n) (ε : ℝ)
    (hε : 0 < ε) (hsmall : ε < 1/(n:ℝ)) :
    ∀ S : Finset (Fin n), S.Nonempty → S ≠ Finset.univ →
      0 < pairing (fragmentWitness ε) (effect F S) ∧
        pairing (fragmentWitness ε) (effect F S) < 1 := by
  have hp (S : Finset (Fin n)) (hS : S.Nonempty) :
      0 < pairing (fragmentWitness ε) (effect F S) := by
    unfold pairing effect
    rw [Matrix.mul_sum,Matrix.trace_sum]
    exact Finset.sum_pos (fun i _ => witness_parent_positive F ε hε hsmall i) hS
  intro S hS hproper
  have hc : Sᶜ.Nonempty := by
    apply Finset.nonempty_iff_ne_empty.mpr
    intro h
    exact hproper (by simpa using congrArg (fun T : Finset (Fin n) => Tᶜ) h)
  have ht : pairing (fragmentWitness ε) (effect F S) +
      pairing (fragmentWitness ε) (effect F Sᶜ) = 1 := by
    rw [←(fragmentWitness_valuation_laws ε).2.2,←effect_union F S Sᶜ disjoint_compl_right,
      Finset.union_compl,effect_univ]
    exact (fragmentWitness_valuation_laws ε).2.1
  exact ⟨hp S hS, by have := hp Sᶜ hc; linarith⟩

theorem witness_orth_proper_sets (F : CenteredFrame n) (ε : ℝ)
    (hε : 0 < ε) (hsmall : ε < 1/(n:ℝ)) (S : Finset (Fin n))
    (hS : S.Nonempty) (hproper : S ≠ Finset.univ) :
    0 < pairing (fragmentWitness ε) (toOrth n F.s (effect F S)) ∧
      pairing (fragmentWitness ε) (toOrth n F.s (effect F S)) < 1 := by
  have h := frame_coordinate_transfer n F.s (size_positive F) F.positive
  rw [←witness_toOrth F ε,h.trace_pairing]
  exact witness_all_proper_sets F ε hε hsmall S hS hproper

theorem witness_inherited_entries (F : CenteredFrame n) (ε : ℝ) (S : Finset (Fin n)) :
    pairing (fragmentWitness ε) (toOrth n F.s (effect F S)) =
      (S.card:ℝ)/(n:ℝ) + ε*((S.card:ℝ)/(n:ℝ) - (∑ i ∈ S, (F.w i)^2)/F.s) := by
  have h := frame_coordinate_transfer n F.s (size_positive F) F.positive
  rw [←witness_toOrth F ε,h.trace_pairing,fragmentWitness_pairing,effect_coordinates]
  rfl

theorem witness_set_laws (F : CenteredFrame n) (ε : ℝ) :
    pairing (fragmentWitness ε) (effect F ∅) = 0 ∧
    pairing (fragmentWitness ε) (effect F Finset.univ) = 1 ∧
    ∀ S T : Finset (Fin n), Disjoint S T →
      pairing (fragmentWitness ε) (effect F (S ∪ T)) =
        pairing (fragmentWitness ε) (effect F S) + pairing (fragmentWitness ε) (effect F T) := by
  refine ⟨?_,?_,?_⟩
  · rw [effect_empty]; exact (fragmentWitness_valuation_laws ε).1
  · rw [effect_univ]; exact (fragmentWitness_valuation_laws ε).2.1
  · intro S T h
    rw [effect_union F S T h]
    exact (fragmentWitness_valuation_laws ε).2.2 _ _

theorem witness_linear_relations {α : Type*} [Fintype α]
    (ε : ℝ) (E : α → M2) (c : α → ℝ) (h : ∑ a, c a • E a = 0) :
    ∑ a, c a * pairing (fragmentWitness ε) (E a) = 0 := by
  simpa [pairing,Matrix.mul_sum,Matrix.trace_sum,Matrix.mul_smul,Matrix.trace_smul]
    using congrArg (pairing (fragmentWitness ε)) h

noncomputable def orthParentEffect (F : CenteredFrame n) (i : Fin n) : Effect :=
  ⟨toOrth n F.s (parent F i),
    (frame_coordinate_transfer n F.s (size_positive F) F.positive).effect_domain _ |>.mp
      (by rw [←effect_singleton]; exact effect_domain F {i})⟩

theorem vandermonde_determinant (F : CenteredFrame n) (a : Fin 3 → Fin n) :
    (fragmentBasisMatrix (fun k => (orthParentEffect F (a k)).val)).det =
      2*(F.w (a 1)-F.w (a 0))*(F.w (a 2)-F.w (a 0))*(F.w (a 1)-F.w (a 2)) /
        ((n:ℝ)*F.s*Real.sqrt (n:ℝ)*Real.sqrt F.s) := by
  have hn := (Real.sqrt_pos.mpr (size_positive F)).ne'
  have hs := (Real.sqrt_pos.mpr F.positive).ne'
  have hnn := Real.sq_sqrt (size_positive F).le
  have hss := Real.sq_sqrt F.positive.le
  simp only [orthParentEffect,orth_parent]
  simp [Matrix.det_fin_three,fragmentBasisMatrix,vecMulVec,Matrix.of_apply]
  generalize hr : Real.sqrt (n:ℝ) = r at *
  generalize ht : Real.sqrt F.s = t at *
  rw [←hnn,←hss]
  field_simp
  ring

/-- Three distinct w values derive separation; no separation determinant is
    supplied as a premise. -/
theorem inherited_no_density (F : CenteredFrame n) (ε : ℝ) (hε : 0 < ε)
    (i j k : Fin n) (hij : F.w i ≠ F.w j) (hik : F.w i ≠ F.w k) (hjk : F.w j ≠ F.w k) :
    ¬ ∃ R : Density, ∀ a : Fin n,
      pairing R.val (toOrth n F.s (parent F a)) =
        pairing (fragmentWitness ε) (toOrth n F.s (parent F a)) := by
  let a : Fin 3 → Fin n := ![i,j,k]
  have hd : (fragmentBasisMatrix (fun t => (orthParentEffect F (a t)).val)).det ≠ 0 := by
    rw [vandermonde_determinant]
    simp only [a,Matrix.cons_val_zero,Matrix.cons_val_one,Matrix.cons_val_two]
    exact div_ne_zero
      (mul_ne_zero (mul_ne_zero (mul_ne_zero (by norm_num) (sub_ne_zero.mpr hij.symm))
        (sub_ne_zero.mpr hik.symm)) (sub_ne_zero.mpr hjk))
      (by have := (size_positive F).ne'; have := F.positive.ne'
          have := (Real.sqrt_pos.mpr (size_positive F)).ne'
          have := (Real.sqrt_pos.mpr F.positive).ne'; positivity)
  rintro ⟨R,hR⟩
  exact finite_fragment_no_density_representation (fun t => orthParentEffect F (a t)) ε hε hd
    ⟨R,fun t => hR (a t)⟩

theorem witness_not_positive (ε : ℝ) (hε : 0 < ε) : ¬ (fragmentWitness ε).PosSemidef := by
  intro h
  exact fragmentWitness_not_density ε hε ⟨h,fragmentWitness_trace ε⟩

theorem inherited_indefinite_assignments (F : CenteredFrame n) :
    ∃ δ : ℝ, 0 < δ ∧ ∀ ε : ℝ, 0 < ε → ε < δ →
      (fragmentWitness ε).IsHermitian ∧ trace (fragmentWitness ε) = 1 ∧
      ¬ (fragmentWitness ε).PosSemidef ∧
      (∀ S : Finset (Fin n), S.Nonempty → S ≠ Finset.univ →
        0 < pairing (fragmentWitness ε) (toOrth n F.s (effect F S)) ∧
          pairing (fragmentWitness ε) (toOrth n F.s (effect F S)) < 1) ∧
      (∀ i j k : Fin n, F.w i ≠ F.w j → F.w i ≠ F.w k → F.w j ≠ F.w k →
        ¬ ∃ R : Density, ∀ a : Fin n,
          pairing R.val (toOrth n F.s (parent F a)) =
            pairing (fragmentWitness ε) (toOrth n F.s (parent F a))) := by
  refine ⟨1/(n:ℝ),one_div_pos.mpr (size_positive F),?_⟩
  intro ε hε hsmall
  refine ⟨?_,fragmentWitness_trace ε,witness_not_positive ε hε,?_,?_⟩
  · ext a b
    fin_cases a <;> fin_cases b <;> simp [fragmentWitness,conjTranspose_apply]
  · intro S hS hproper; exact witness_orth_proper_sets F ε hε hsmall S hS hproper
  · intro i j k hij hik hjk; exact inherited_no_density F ε hε i j k hij hik hjk

end BornCalculus.General
