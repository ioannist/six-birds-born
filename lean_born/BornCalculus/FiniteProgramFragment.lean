import BornCalculus.FiniteFragment
import BornCalculus.Programs
import BornCalculus.Frame

namespace BornCalculus
open Matrix
open scoped MatrixOrder BigOperators

/-- The actual strictness premise of the finite-fragment construction. -/
def InvertibleProgram (P : List KrausTest) : Prop :=
 ∀ C ∈ P, ∀ i : Fin C.arity, IsUnit (C.kraus i)

theorem wordMatrix_isUnit (P : List KrausTest) (hP : InvertibleProgram P)
 (w : Outcomes P) : IsUnit (wordMatrix P w) := by
 induction P with
 | nil => exact isUnit_one
 | cons C P ih =>
   rcases w with ⟨i, w⟩
   exact (ih (fun D hD => hP D (List.mem_cons_of_mem _ hD)) w).mul
     (hP C List.mem_cons_self i)

theorem wordEffect_posDef (P : List KrausTest) (hP : InvertibleProgram P)
 (w : Outcomes P) : (wordEffect P w).PosDef := by
 have hm := wordMatrix_isUnit P hP w
 simpa only [wordEffect, Matrix.conjTranspose_eq_transpose_of_trivial] using
   Matrix.PosDef.conjTranspose_mul_self (wordMatrix P w)
     (Matrix.mulVec_injective_iff_isUnit.mpr hm)

theorem groupedEffect_posDef (P : List KrausTest) (hP : InvertibleProgram P)
 (s : Finset (Outcomes P)) (hs : s.Nonempty) : (groupedEffect P s).PosDef :=
 Matrix.posDef_sum hs (fun w _ => wordEffect_posDef P hP w)

/-- Every nonempty proper grouping is strictly between zero and identity.
The complement is the sum of the omitted word effects, not a normalization
of selected posteriors or a newly chosen root of a grouped effect. -/
theorem groupedEffect_strict_interior (P : List KrausTest) (hP : InvertibleProgram P)
 (s : Finset (Outcomes P)) (hs : s.Nonempty) (ho : ∃ w, w ∉ s) :
 (groupedEffect P s).PosDef ∧ (1 - groupedEffect P s).PosDef := by
 classical
 refine ⟨groupedEffect_posDef P hP s hs, ?_⟩
 have hsum : groupedEffect P (Finset.univ \ s) + groupedEffect P s = 1 := by
   unfold groupedEffect
   rw [Finset.sum_sdiff (Finset.subset_univ s)]
   exact program_effects_sum P
 have he : 1 - groupedEffect P s = groupedEffect P (Finset.univ \ s) := by
   rw [← hsum]
   abel
 rw [he]
 apply groupedEffect_posDef P hP
 obtain ⟨w, hw⟩ := ho
 exact ⟨w, by simp [hw]⟩

theorem groupedEffect_diagonal_interior (P : List KrausTest) (hP : InvertibleProgram P)
 (s : Finset (Outcomes P)) (hs : s.Nonempty) (ho : ∃ w, w ∉ s) :
 0 < groupedEffect P s 0 0 ∧ groupedEffect P s 0 0 < 1 := by
 have hp := groupedEffect_strict_interior P hP s hs ho
 have hc : 0 < (1 - groupedEffect P s) 0 0 := hp.2.diag_pos
 have hc' : 0 < 1 - groupedEffect P s 0 0 := by simpa using hc
 exact ⟨hp.1.diag_pos, by linarith⟩

structure InteriorProgramEvent where
 program : List KrausTest
 selected : Finset (Outcomes program)
 invertible : InvertibleProgram program
 nonempty : selected.Nonempty
 omitted : ∃ w, w ∉ selected

noncomputable def interiorEventEffect (e : InteriorProgramEvent) : M2 :=
 groupedEffect e.program e.selected

/-- The finite-interior argument applies uniformly to any finite collection
of actual word groupings of complete invertible Kraus programs. Empty/unit
groupings are endpoints with values zero/one. No infinite generated algebra
or common perturbation for an infinite collection is asserted. -/
theorem finite_program_fragment_non_density {ι : Type*} [Fintype ι]
 (events : ι → InteriorProgramEvent) :
 ∃ ε : ℝ, 0 < ε ∧ ¬ IsDensity (fragmentWitness ε) ∧
   trace (fragmentWitness ε) = 1 ∧
   ∀ i, 0 < pairing (fragmentWitness ε) (interiorEventEffect (events i)) ∧
     pairing (fragmentWitness ε) (interiorEventEffect (events i)) < 1 := by
 classical
 let s : Finset M2 := Finset.univ.image (fun i => interiorEventEffect (events i))
 have hs : ∀ E ∈ s, 0 < E 0 0 ∧ E 0 0 < 1 := by
   intro E hE
   obtain ⟨i, _, rfl⟩ := Finset.mem_image.mp hE
   exact groupedEffect_diagonal_interior _ (events i).invertible _
     (events i).nonempty (events i).omitted
 obtain ⟨ε, hε, hnot, htrace, hval⟩ := finite_fragment_non_density s hs
 refine ⟨ε, hε, hnot, htrace, ?_⟩
 intro i
 exact hval _ (Finset.mem_image.mpr ⟨i, Finset.mem_univ i, rfl⟩)

/-- The strict PSD-effect premise supplies invertibility of the chosen
principal-root Kraus matrices; it is not an extra instrument assumption. -/
theorem luedersFamily_invertible (n : ℕ) (E : Fin n → Effect)
 (hn : ∑ i, (E i).val = 1) (hE : ∀ i, (E i).val.PosDef) (i : Fin n) :
 IsUnit ((luedersFamily n E hn).kraus i) := by
 exact (CFC.isUnit_sqrt_iff (E i).val (hE i).posSemidef.nonneg).mpr (hE i).isUnit

theorem luedersFamily_invertible_of_det (n : ℕ) (E : Fin n → Effect)
 (hn : ∑ i, (E i).val = 1) (hE : ∀ i, (E i).val.det ≠ 0) (i : Fin n) :
 IsUnit ((luedersFamily n E hn).kraus i) := by
 exact (CFC.isUnit_sqrt_iff (E i).val (E i).property.1.nonneg).mpr
   ((Matrix.isUnit_iff_isUnit_det _).mpr (isUnit_iff_ne_zero.mpr (hE i)))

theorem toOrth_isUnit_iff (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁)
 (A : M2) : IsUnit (toOrth g₀ g₁ A) ↔ IsUnit A := by
 have hf := frame_coordinate_transfer g₀ g₁ h₀ h₁
 have hSi : IsUnit (frameSi g₀ g₁) := by
   rw [← hf.S_inverse]
   exact Matrix.isUnit_nonsing_inv_iff.mpr hf.S_invertible
 constructor
 · intro ha
   have hh := (hSi.mul ha).mul hf.S_invertible
   change IsUnit (fromOrth g₀ g₁ (toOrth g₀ g₁ A)) at hh
   simpa only [hf.inverse_left] using hh
 · intro ha
   exact (hf.S_invertible.mul ha).mul hSi

/-- Nonzero determinant of an admitted G-positive effect suffices for the
principal G-root's invertibility, exactly as in the concrete B06 check. -/
theorem g_root_invertible_of_det (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁)
 (E : M2) (hE : GPositive g₀ g₁ E) (hd : E.det ≠ 0) :
 IsUnit (gRoot g₀ g₁ E) := by
 have hf := frame_coordinate_transfer g₀ g₁ h₀ h₁
 have he : IsUnit E :=
   (Matrix.isUnit_iff_isUnit_det _).mpr (isUnit_iff_ne_zero.mpr hd)
 have ho : IsUnit (toOrth g₀ g₁ E) := (toOrth_isUnit_iff g₀ g₁ h₀ h₁ E).mpr he
 have hr : IsUnit (CFC.sqrt (toOrth g₀ g₁ E)) :=
   (CFC.isUnit_sqrt_iff _ ((hf.positive E).mp hE).nonneg).mpr ho
 apply (toOrth_isUnit_iff g₀ g₁ h₀ h₁ _).mp
 simpa only [hf.principal_roots] using hr

theorem fragmentWitness_frame_invariant (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁)
 (ε : ℝ) : toOrth g₀ g₁ (fragmentWitness ε) = fragmentWitness ε := by
 have hs₀ := (Real.sqrt_pos.mpr h₀).ne'
 have hs₁ := (Real.sqrt_pos.mpr h₁).ne'
 ext a b
 fin_cases a <;> fin_cases b <;>
   simp [toOrth, frameS, frameSi, fragmentWitness, mul_apply, Fin.sum_univ_two] <;>
   field_simp

theorem fragmentWitness_g_not_density (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁)
 (ε : ℝ) (hε : 0 < ε) : ¬ GIsDensity g₀ g₁ (fragmentWitness ε) := by
 intro hd
 have hr := (frame_coordinate_transfer g₀ g₁ h₀ h₁).density_domain _ |>.mp hd
 rw [fragmentWitness_frame_invariant g₀ g₁ h₀ h₁] at hr
 exact fragmentWitness_not_density ε hε hr

theorem fragmentWitness_frame_pairing (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁)
 (ε : ℝ) (E : M2) :
 pairing (fragmentWitness ε) (fromOrth g₀ g₁ E) = pairing (fragmentWitness ε) E := by
 have hf := frame_coordinate_transfer g₀ g₁ h₀ h₁
 have he := hf.trace_pairing (fragmentWitness ε) (fromOrth g₀ g₁ E)
 rw [fragmentWitness_frame_invariant g₀ g₁ h₀ h₁, hf.inverse_right] at he
 exact he.symm

noncomputable def gInteriorEventEffect (g₀ g₁ : ℝ) (e : InteriorProgramEvent) : M2 :=
 fromOrth g₀ g₁ (interiorEventEffect e)

/-- Positive diagonal coordinates require no new strictness assumption and
preserve the same non-density witness and every finite-fragment valuation. -/
theorem finite_g_program_fragment_non_density {ι : Type*} [Fintype ι]
 (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁) (events : ι → InteriorProgramEvent) :
 ∃ ε : ℝ, 0 < ε ∧ ¬ GIsDensity g₀ g₁ (fragmentWitness ε) ∧
   trace (fragmentWitness ε) = 1 ∧
   ∀ i, 0 < pairing (fragmentWitness ε) (gInteriorEventEffect g₀ g₁ (events i)) ∧
     pairing (fragmentWitness ε) (gInteriorEventEffect g₀ g₁ (events i)) < 1 := by
 obtain ⟨ε, hε, _, htrace, hval⟩ := finite_program_fragment_non_density events
 refine ⟨ε, hε, fragmentWitness_g_not_density g₀ g₁ h₀ h₁ ε hε, htrace, ?_⟩
 intro i
 simpa only [gInteriorEventEffect, fragmentWitness_frame_pairing g₀ g₁ h₀ h₁]
   using hval i

/-- The strict-program event domain is inhabited by a concrete complete
two-outcome test. The branch products, selected event and omitted event are
all supplied; consistency is not left to an abstract instrument hypothesis. -/
theorem interiorProgramEvent_inhabited : Nonempty InteriorProgramEvent := by
 let t : ℝ := Real.sqrt (1 / 2)
 have ht : t * t = (1 / 2 : ℝ) := Real.mul_self_sqrt (by norm_num)
 let A : M2 := t • 1
 have ha : IsUnit A := by
   apply (Matrix.isUnit_iff_isUnit_det _).mpr
   apply isUnit_iff_ne_zero.mpr
   have hd : A.det = (1 / 2 : ℝ) := by
     simpa [A, Matrix.det_fin_two, pow_two] using ht
   rw [hd]
   norm_num
 have hc : ∑ i : Fin 2, Aᵀ * A = 1 := by
   rw [Fin.sum_univ_two]
   ext a b
   fin_cases a <;> fin_cases b <;>
     simp [A, ht] <;> norm_num
 let C : KrausTest := ⟨2, fun _ => A, hc⟩
 have hi : InvertibleProgram [C] := by
   intro D hD i
   have he : D = C := List.mem_singleton.mp hD
   subst D
   exact ha
 let w : Outcomes [C] := (0, ())
 let s : Finset (Outcomes [C]) := {w}
 refine ⟨⟨[C], s, hi, Finset.singleton_nonempty w, ?_⟩⟩
 refine ⟨(1, ()), ?_⟩
 intro hm
 have he : ((1, ()) : Outcomes [C]) = w := Finset.mem_singleton.mp hm
 have hh := congrArg (fun x : Outcomes [C] => x.1.val) he
 norm_num [w, C] at hh

end BornCalculus
