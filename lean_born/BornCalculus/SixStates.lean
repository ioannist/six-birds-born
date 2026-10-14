import BornCalculus.Definitions

namespace BornCalculus
open Matrix
open scoped MatrixOrder
set_option maxHeartbeats 0
noncomputable def Pa : M2 := !![1, 0; 0, 0]
noncomputable def Pb : M2 := !![1/4, Real.sqrt 3/4; Real.sqrt 3/4, 3/4]
noncomputable def Pc : M2 := !![1/4, -Real.sqrt 3/4; -Real.sqrt 3/4, 3/4]
noncomputable def sharp : Fin 3 → M2 := ![Pa, Pb, Pc]
noncomputable def sixState : Fin 6 → M2 := ![Pa, Pb, Pc, 1-Pa, 1-Pb, 1-Pc]
noncomputable def halfUnit : M2 := (1/2 : ℝ) • 1

theorem sqrt_three_positive : 0 < Real.sqrt (3 : ℝ) := Real.sqrt_pos.2 (by norm_num)
theorem sqrt_three_square : Real.sqrt (3 : ℝ) * Real.sqrt 3 = 3 := Real.mul_self_sqrt (by norm_num)

private theorem sharp_symm (i : Fin 3) : (sharp i)ᵀ = sharp i := by
 fin_cases i <;> ext a b <;> fin_cases a <;> fin_cases b <;> simp [sharp,Pa,Pb,Pc]
private theorem sharp_sq (i : Fin 3) : sharp i * sharp i = sharp i := by
 have h := sqrt_three_square
 fin_cases i <;> ext a b <;> fin_cases a <;> fin_cases b <;>
  simp [sharp,Pa,Pb,Pc,Matrix.mul_apply,Fin.sum_univ_two] <;> nlinarith
private theorem sharp_trace (i : Fin 3) : Matrix.trace (sharp i) = 1 := by
 fin_cases i <;> norm_num [sharp,Pa,Pb,Pc,Matrix.trace,Fin.sum_univ_two]

theorem real_projector_psd (A : M2) (hsym : Aᵀ=A) (hsq : A*A=A) : A.PosSemidef := by
 have h := Matrix.posSemidef_conjTranspose_mul_self A
 simpa only [Matrix.conjTranspose_eq_transpose_of_trivial,hsym,hsq] using h

structure SixStateDomainLaws : Prop where
 density : ∀ i : Fin 6, IsDensity (sixState i)
 projector : ∀ i : Fin 6, sixState i * sixState i = sixState i
 sharp_effect : ∀ i : Fin 3, IsEffect (sharp i)
 effect : ∀ i : Fin 6, IsEffect (sixState i)

theorem six_states_density_and_projector : SixStateDomainLaws := by
 have hc (i : Fin 3) : (1-sharp i)*(1-sharp i)=1-sharp i := by
  noncomm_ring [sharp_sq i]
 have hcSym (i : Fin 3) : (1-sharp i)ᵀ=1-sharp i := by simp [sharp_symm]
 have hct (i : Fin 3) : Matrix.trace (1-sharp i)=1 := by
  rw [Matrix.trace_sub,sharp_trace]; norm_num [Matrix.trace,Fin.sum_univ_two]
 have hp (i : Fin 3) := real_projector_psd (sharp i) (sharp_symm i) (sharp_sq i)
 have hcp (i : Fin 3) := real_projector_psd (1-sharp i) (hcSym i) (hc i)
 constructor
 · intro i; fin_cases i <;> constructor
   all_goals first | exact hp 0 | exact hp 1 | exact hp 2 | exact hcp 0 | exact hcp 1 | exact hcp 2 | exact sharp_trace 0 | exact sharp_trace 1 | exact sharp_trace 2 | exact hct 0 | exact hct 1 | exact hct 2
 · intro i; fin_cases i
   all_goals first | exact sharp_sq 0 | exact sharp_sq 1 | exact sharp_sq 2 | exact hc 0 | exact hc 1 | exact hc 2
 · intro i; exact ⟨hp i,hcp i⟩
 · intro i; fin_cases i <;> dsimp [IsEffect,sixState]
   all_goals first
    | exact ⟨hp 0,hcp 0⟩
    | exact ⟨hp 1,hcp 1⟩
    | exact ⟨hp 2,hcp 2⟩
    | exact ⟨hcp 0,by simpa using hp 0⟩
    | exact ⟨hcp 1,by simpa using hp 1⟩
    | exact ⟨hcp 2,by simpa using hp 2⟩

structure FiveMixtureIdentities : Prop where
 pairs : ∀ i : Fin 3, (1/2 : ℝ) • (sharp i + (1-sharp i)) = halfUnit
 positive_trine : (1/3 : ℝ) • (Pa+Pb+Pc)=halfUnit
 negative_trine : (1/3 : ℝ) • ((1-Pa)+(1-Pb)+(1-Pc))=halfUnit

theorem six_state_five_mixtures : FiveMixtureIdentities := by
 constructor
 · intro i; simp [halfUnit]
 · ext a b; fin_cases a <;> fin_cases b <;> norm_num [Pa,Pb,Pc,halfUnit] <;> ring
 · ext a b; fin_cases a <;> fin_cases b <;> norm_num [Pa,Pb,Pc,halfUnit] <;> ring

noncomputable def sixTable : Fin 6 → Fin 3 → ℝ :=
 ![![1,1/4,1/4],![1/4,1,1/4],![1/4,1/4,1],![0,3/4,3/4],![3/4,0,3/4],![3/4,3/4,0]]
def SixStateTableIdentity : Prop := ∀ i j, pairing (sixState i) (sharp j)=sixTable i j

theorem six_state_probability_table : SixStateTableIdentity := by
 have h := sqrt_three_square
 intro i j; fin_cases i <;> fin_cases j <;>
  simp [sixState,sharp,Pa,Pb,Pc,pairing,sixTable,Matrix.trace,Matrix.mul_apply,Fin.sum_univ_two] <;> nlinarith

theorem binary_trine_parity (a b c : ℝ)
 (ha : a=0 ∨ a=2) (hb : b=0 ∨ b=2) (hc : c=0 ∨ c=2) : a+b+c≠3 := by
 rcases ha with rfl|rfl <;> rcases hb with rfl|rfl <;> rcases hc with rfl|rfl <;> norm_num
end BornCalculus
