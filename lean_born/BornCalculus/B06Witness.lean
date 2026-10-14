import BornCalculus.B06Atomic
import BornCalculus.FiniteEvents

namespace BornCalculus
open Matrix
open scoped MatrixOrder BigOperators
set_option maxHeartbeats 0

noncomputable def b06RawOrthEffect (i : Fin 2) : Effect :=
 ⟨toOrth 32 b06S (b06Raw i),
   (frame_coordinate_transfer 32 b06S (by norm_num) b06_s_positive).effect_domain _ |>.mp
     (b06RawEffect i).property⟩
noncomputable def b06PackageOrthEffect (i : Fin 3) : Effect :=
 ⟨toOrth 32 b06S (b06Package i),
   (frame_coordinate_transfer 32 b06S (by norm_num) b06_s_positive).effect_domain _ |>.mp
     (b06PackageEffect i).property⟩
noncomputable def b06JointOrthEffect (i : Fin 3) : Effect :=
 ⟨toOrth 32 b06S (b06Joint i),
   (frame_coordinate_transfer 32 b06S (by norm_num) b06_s_positive).effect_domain _ |>.mp
     (b06JointEffect i).property⟩

theorem b06RawOrth_sum : (∑ i : Fin 2, (b06RawOrthEffect i).val) = 1 := by
 simp only [b06RawOrthEffect]
 calc
   (∑ i : Fin 2, toOrth 32 b06S (b06Raw i)) = toOrth 32 b06S (∑ i : Fin 2, b06Raw i) := by
     simp only [toOrth, Matrix.mul_sum, Matrix.sum_mul]
   _ = 1 := by rw [b06_raw_sum, (frame_coordinate_transfer 32 b06S (by norm_num) b06_s_positive).unit]
theorem b06PackageOrth_sum : (∑ i : Fin 3, (b06PackageOrthEffect i).val) = 1 := by
 simp only [b06PackageOrthEffect]
 calc
   (∑ i : Fin 3, toOrth 32 b06S (b06Package i)) = toOrth 32 b06S (∑ i : Fin 3, b06Package i) := by
     simp only [toOrth, Matrix.mul_sum, Matrix.sum_mul]
   _ = 1 := by rw [b06_package_sum, (frame_coordinate_transfer 32 b06S (by norm_num) b06_s_positive).unit]
theorem b06JointOrth_sum : (∑ i : Fin 3, (b06JointOrthEffect i).val) = 1 := by
 simp only [b06JointOrthEffect]
 calc
   (∑ i : Fin 3, toOrth 32 b06S (b06Joint i)) = toOrth 32 b06S (∑ i : Fin 3, b06Joint i) := by
     simp only [toOrth, Matrix.mul_sum, Matrix.sum_mul]
   _ = 1 := by rw [b06_joint_sum, (frame_coordinate_transfer 32 b06S (by norm_num) b06_s_positive).unit]

noncomputable def b06RawTest : KrausTest := luedersFamily 2 b06RawOrthEffect b06RawOrth_sum
noncomputable def b06PackageTest : KrausTest := luedersFamily 3 b06PackageOrthEffect b06PackageOrth_sum
noncomputable def b06JointTest : KrausTest := luedersFamily 3 b06JointOrthEffect b06JointOrth_sum

theorem b06RawTest_invertible (i : Fin b06RawTest.arity) : IsUnit (b06RawTest.kraus i) := by
 apply luedersFamily_invertible_of_det
 intro j
 change (toOrth 32 b06S (b06Raw j)).det ≠ 0
 rw [frame_determinant_invariant 32 b06S (by norm_num) b06_s_positive]
 exact (b06_raw_det_positive j).ne'
theorem b06PackageTest_invertible (i : Fin b06PackageTest.arity) : IsUnit (b06PackageTest.kraus i) := by
 apply luedersFamily_invertible_of_det
 intro j
 change (toOrth 32 b06S (b06Package j)).det ≠ 0
 rw [frame_determinant_invariant 32 b06S (by norm_num) b06_s_positive]
 exact (b06_package_det_positive j).ne'
theorem b06JointTest_invertible (i : Fin b06JointTest.arity) : IsUnit (b06JointTest.kraus i) := by
 apply luedersFamily_invertible_of_det
 intro j
 change (toOrth 32 b06S (b06Joint j)).det ≠ 0
 rw [frame_determinant_invariant 32 b06S (by norm_num) b06_s_positive]
 exact (b06_joint_det_positive j).ne'

/- Exactly the registration in instruments.tests: three one-command tests
and all nine ordered two-command words; neither adaptive nor native steps. -/
noncomputable def b06Programs (i : Fin 12) : List KrausTest := match i.val with
 | 0 => [b06RawTest]
 | 1 => [b06PackageTest]
 | 2 => [b06JointTest]
 | 3 => [b06RawTest,b06RawTest]
 | 4 => [b06RawTest,b06PackageTest]
 | 5 => [b06RawTest,b06JointTest]
 | 6 => [b06PackageTest,b06RawTest]
 | 7 => [b06PackageTest,b06PackageTest]
 | 8 => [b06PackageTest,b06JointTest]
 | 9 => [b06JointTest,b06RawTest]
 | 10 => [b06JointTest,b06PackageTest]
 | _ => [b06JointTest,b06JointTest]

theorem b06_programs_invertible (i : Fin 12) : InvertibleProgram (b06Programs i) := by
 have hall : ∀ C ∈ [b06RawTest,b06PackageTest,b06JointTest], ∀ j, IsUnit (C.kraus j) := by
   intro C hC j
   simp at hC
   rcases hC with rfl | rfl | rfl
   · exact b06RawTest_invertible j
   · exact b06PackageTest_invertible j
   · exact b06JointTest_invertible j
 intro C hC j
 apply hall C _ j
 fin_cases i <;> simp [b06Programs] at hC <;> aesop

def b06OutcomeCount : Fin 12 → ℕ := ![2,3,3,4,6,6,6,9,9,6,9,9]
theorem b06_outcome_count (i : Fin 12) : Fintype.card (Outcomes (b06Programs i)) = b06OutcomeCount i := by
 fin_cases i <;> norm_num [b06Programs, b06OutcomeCount, Outcomes,
   b06RawTest, b06PackageTest, b06JointTest, luedersFamily]

abbrev B06Event := Σ i : Fin 12, Finset (Outcomes (b06Programs i))
noncomputable instance b06EventFintype : Fintype B06Event := by classical infer_instance

theorem b06_event_count : Fintype.card B06Event = 2340 := by
 classical
 rw [Fintype.card_sigma]
 simp only [program_event_count, b06_outcome_count]
 norm_num [b06OutcomeCount, Fin.sum_univ_succ]

abbrev B06ProperEvent := Σ i : Fin 12,
 {s : Finset (Outcomes (b06Programs i)) // s.Nonempty ∧ s ≠ Finset.univ}
noncomputable instance b06ProperEventFintype : Fintype B06ProperEvent := by classical infer_instance

theorem b06_outcomes_nonempty (i : Fin 12) : Nonempty (Outcomes (b06Programs i)) := by
 apply Fintype.card_pos_iff.mp
 rw [b06_outcome_count]
 fin_cases i <;> norm_num [b06OutcomeCount]

theorem b06_proper_event_count : Fintype.card B06ProperEvent = 2316 := by
 classical
 rw [Fintype.card_sigma]
 have hc (i : Fin 12) :
   Fintype.card {s : Finset (Outcomes (b06Programs i)) // s.Nonempty ∧ s ≠ Finset.univ} =
     2 ^ b06OutcomeCount i - 2 := by
   letI := b06_outcomes_nonempty i
   rw [proper_finset_count, b06_outcome_count]
 simp_rw [hc]
 norm_num [b06OutcomeCount, Fin.sum_univ_succ]

noncomputable def b06InteriorEvent (e : B06ProperEvent) : InteriorProgramEvent where
 program := b06Programs e.1
 selected := e.2.val
 invertible := b06_programs_invertible e.1
 nonempty := e.2.property.1
 omitted := by
   classical
   by_contra hn
   push_neg at hn
   have he : e.2.val = Finset.univ := Finset.eq_univ_of_forall hn
   exact e.2.property.2 he

noncomputable def b06EventEffect (e : B06Event) : M2 :=
 fromOrth 32 b06S (groupedEffect (b06Programs e.1) e.2)

theorem b06_event_effect_domain (e : B06Event) : GIsEffect 32 b06S (b06EventEffect e) := by
 have hf := frame_coordinate_transfer 32 b06S (by norm_num) b06_s_positive
 apply (hf.effect_domain _).mpr
 rw [b06EventEffect, hf.inverse_right]
 exact grouped_effect_is_effect _ _

/-- A concrete common non-density witness exists for all 2,316 proper
registered events. Its epsilon is constructed by the finite theorem, not
imported from a numerical attachment. -/
theorem b06_concrete_finite_witness :
 ∃ ε : ℝ, 0 < ε ∧ ¬ GIsDensity 32 b06S (fragmentWitness ε) ∧
   trace (fragmentWitness ε) = 1 ∧
   ∀ e : B06ProperEvent,
     0 < pairing (fragmentWitness ε) (b06EventEffect ⟨e.1,e.2.val⟩) ∧
     pairing (fragmentWitness ε) (b06EventEffect ⟨e.1,e.2.val⟩) < 1 := by
 exact finite_g_program_fragment_non_density 32 b06S (by norm_num) b06_s_positive b06InteriorEvent

theorem b06_event_empty (i : Fin 12) : b06EventEffect ⟨i,∅⟩ = 0 := by
 simp [b06EventEffect, groupedEffect, fromOrth]

theorem b06_event_unit (i : Fin 12) : b06EventEffect ⟨i,Finset.univ⟩ = 1 := by
 have hs : groupedEffect (b06Programs i) Finset.univ = 1 := program_effects_sum _
 have hf := frame_coordinate_transfer 32 b06S (by norm_num) b06_s_positive
 have hu : fromOrth 32 b06S (1 : M2) = 1 := by
   have h := hf.inverse_left (1 : M2)
   rw [hf.unit] at h
   exact h
 simpa only [b06EventEffect, hs] using hu

/-- Includes all registered endpoints, not merely the proper event subtype. -/
theorem b06_all_event_witness :
 ∃ ε : ℝ, 0 < ε ∧ ¬ GIsDensity 32 b06S (fragmentWitness ε) ∧
   trace (fragmentWitness ε) = 1 ∧
   ∀ e : B06Event, 0 ≤ pairing (fragmentWitness ε) (b06EventEffect e) ∧
     pairing (fragmentWitness ε) (b06EventEffect e) ≤ 1 := by
 classical
 obtain ⟨ε,hε,hnot,htr,hproper⟩ := b06_concrete_finite_witness
 refine ⟨ε,hε,hnot,htr,?_⟩
 intro e
 by_cases he : e.2 = ∅
 · rcases e with ⟨i,s⟩
   change s = ∅ at he
   subst s
   simp [b06_event_empty, pairing]
 by_cases hu : e.2 = Finset.univ
 · rcases e with ⟨i,s⟩
   change s = Finset.univ at hu
   subst s
   simp [b06_event_unit, pairing, htr]
 let p : B06ProperEvent := ⟨e.1,⟨e.2,Finset.nonempty_iff_ne_empty.mpr he,hu⟩⟩
 exact ⟨(hproper p).1.le,(hproper p).2.le⟩

theorem lueders_single_word_effect (n : ℕ) (E : Fin n → Effect)
 (hn : ∑ i, (E i).val = 1) (i : Fin n) :
 wordEffect [luedersFamily n E hn] (i,()) = (E i).val := by
 have ht : (CFC.sqrt (E i).val)ᵀ = CFC.sqrt (E i).val := by
   simpa only [Matrix.conjTranspose_eq_transpose_of_trivial] using
     (CFC.sqrt_nonneg (E i).val).posSemidef.isHermitian
 simp only [wordEffect, wordMatrix, luedersFamily, Matrix.one_mul, ht,
   CFC.sqrt_mul_sqrt_self _ (E i).property.1.nonneg]

noncomputable def b06BasisEvent (i : Fin 3) : B06Event := match i.val with
 | 0 => ⟨2,Finset.univ⟩
 | 1 => ⟨2,{((0 : Fin 3),())}⟩
 | _ => ⟨2,{((1 : Fin 3),())}⟩

theorem b06_basis_event_effect (i : Fin 3) :
 b06EventEffect (b06BasisEvent i) = (b06BasisEffect i).val := by
 have hf := frame_coordinate_transfer 32 b06S (by norm_num) b06_s_positive
 fin_cases i
 · change b06EventEffect ⟨2,Finset.univ⟩ = 1
   exact b06_event_unit 2
 · change fromOrth 32 b06S (groupedEffect [b06JointTest] {((0 : Fin 3),())}) = b06Joint 0
   simp only [groupedEffect, Finset.sum_singleton]
   rw [show wordEffect [b06JointTest] ((0 : Fin 3),()) = toOrth 32 b06S (b06Joint 0) from
     lueders_single_word_effect 3 b06JointOrthEffect b06JointOrth_sum 0]
   exact hf.inverse_left _
 · change fromOrth 32 b06S (groupedEffect [b06JointTest] {((1 : Fin 3),())}) = b06Joint 1
   simp only [groupedEffect, Finset.sum_singleton]
   rw [show wordEffect [b06JointTest] ((1 : Fin 3),()) = toOrth 32 b06S (b06Joint 1) from
     lueders_single_word_effect 3 b06JointOrthEffect b06JointOrth_sum 1]
   exact hf.inverse_left _

/-- The three independently checked basis effects really are registered
events, so every density representation of all 2,340 values is excluded. -/
theorem b06_no_density_representation (ε : ℝ) (hε : 0 < ε) :
 ¬ ∃ R : GDensity 32 b06S, ∀ e : B06Event,
   pairing R.val (b06EventEffect e) = pairing (fragmentWitness ε) (b06EventEffect e) := by
 rintro ⟨R,hR⟩
 apply g_finite_fragment_no_density_representation 32 b06S (by norm_num) b06_s_positive
   b06BasisEffect ε hε b06_basis_det_nonzero
 refine ⟨R,?_⟩
 intro i
 simpa only [b06_basis_event_effect] using hR (b06BasisEvent i)

/-- Concrete finite-fragment non-trace representation obstruction. This is
an existence theorem, not a proof of the archived numerical epsilon, and it
asserts no valuation on the generated sub-effect-algebra H. -/
theorem b06_non_trace_finite_fragment :
 ∃ ε : ℝ, 0 < ε ∧ ¬ GIsDensity 32 b06S (fragmentWitness ε) ∧
   trace (fragmentWitness ε) = 1 ∧
   (∀ e : B06Event, 0 ≤ pairing (fragmentWitness ε) (b06EventEffect e) ∧
     pairing (fragmentWitness ε) (b06EventEffect e) ≤ 1) ∧
   ¬ ∃ R : GDensity 32 b06S, ∀ e : B06Event,
     pairing R.val (b06EventEffect e) = pairing (fragmentWitness ε) (b06EventEffect e) := by
 obtain ⟨ε,hε,hnot,htr,hval⟩ := b06_all_event_witness
 exact ⟨ε,hε,hnot,htr,hval,b06_no_density_representation ε hε⟩

end BornCalculus
