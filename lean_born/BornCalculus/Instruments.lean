import BornCalculus.Definitions

namespace BornCalculus
open Matrix
open scoped MatrixOrder BigOperators Kronecker
set_option maxHeartbeats 0

structure KrausTest where
 arity : ℕ
 kraus : Fin arity → M2
 complete : ∑ i, (kraus i)ᵀ * kraus i = 1

def branch (A R : M2) : M2 := A * R * Aᵀ
def branchMass (A R : M2) : ℝ := Matrix.trace (branch A R)

theorem branch_psd (A R : M2) (hR : R.PosSemidef) : (branch A R).PosSemidef := by
 simpa [branch,Matrix.conjTranspose_eq_transpose_of_trivial] using hR.mul_mul_conjTranspose_same A

theorem principal_root_exists_unique (E : M2) (hE : E.PosSemidef) :
 ∃! A : M2, A.PosSemidef ∧ A*A=E := by
 refine ⟨CFC.sqrt E,⟨(CFC.sqrt_nonneg E).posSemidef,CFC.sqrt_mul_sqrt_self E hE.nonneg⟩,?_⟩
 intro B hB
 apply (CFC.sq_eq_sq_iff B (CFC.sqrt E) hB.1.nonneg (CFC.sqrt_nonneg E)).mp
 simp only [pow_two,hB.2,CFC.sqrt_mul_sqrt_self E hE.nonneg]

theorem psd_trace_zero_iff (R : M2) (hR : R.PosSemidef) : Matrix.trace R = 0 ↔ R = 0 := by
 refine ⟨fun h ↦ ?_,fun h ↦ by simp [h]⟩
 have hS : (CFC.sqrt R).PosSemidef := (CFC.sqrt_nonneg R).posSemidef
 have hSS : (CFC.sqrt R)ᴴ * CFC.sqrt R = R := by
  rw [hS.isHermitian.eq,CFC.sqrt_mul_sqrt_self R hR.nonneg]
 have hz : CFC.sqrt R=0 := Matrix.trace_conjTranspose_mul_self_eq_zero_iff.mp (hSS.symm ▸ h)
 rw [← CFC.sqrt_mul_sqrt_self R hR.nonneg,hz,mul_zero]

theorem branch_mass_nonnegative (A : M2) (R : Density) : 0 ≤ branchMass A R.val :=
 (branch_psd A R.val R.property.1).trace_nonneg

theorem branch_mass_pairing (A R : M2) : branchMass A R=pairing R (Aᵀ*A) := by
 unfold branchMass branch pairing
 calc
  Matrix.trace (A*R*Aᵀ)=Matrix.trace (Aᵀ*(A*R)) := Matrix.trace_mul_comm _ _
  _=Matrix.trace ((Aᵀ*A)*R) := by rw [Matrix.mul_assoc]
  _=Matrix.trace (R*(Aᵀ*A)) := Matrix.trace_mul_comm _ _

theorem kraus_mass_sum (C : KrausTest) (R : Density) : ∑ i, branchMass (C.kraus i) R.val=1 := by
 simp_rw [branch_mass_pairing,pairing]
 rw [← Matrix.trace_sum,← Matrix.mul_sum,C.complete,Matrix.mul_one]
 exact R.property.2

theorem normalized_branch_density (A : M2) (R : Density) (h : 0 < branchMass A R.val) :
 IsDensity ((branchMass A R.val)⁻¹ • branch A R.val) := by
 constructor
 · exact (branch_psd A R.val R.property.1).smul (inv_nonneg.mpr h.le)
 · rw [Matrix.trace_smul]; change (branchMass A R.val)⁻¹ * branchMass A R.val=1
   exact inv_mul_cancel₀ h.ne'

theorem zero_mass_branch (A : M2) (R : Density) (h : branchMass A R.val=0) : branch A R.val=0 :=
 (psd_trace_zero_iff _ (branch_psd A R.val R.property.1)).mp h

noncomputable def posterior (A : M2) (R : Density) : Option Density :=
 if h : 0 < branchMass A R.val then some ⟨_,normalized_branch_density A R h⟩ else none

theorem posterior_positive (A : M2) (R : Density) (h : 0 < branchMass A R.val) :
 posterior A R=some ⟨_,normalized_branch_density A R h⟩ := by simp [posterior,h]
theorem posterior_zero (A : M2) (R : Density) (h : branchMass A R.val=0) : posterior A R=none := by simp [posterior,h]

theorem forgotten_density (C : KrausTest) (R : Density) : IsDensity (∑ i, branch (C.kraus i) R.val) := by
 constructor
 · exact Matrix.posSemidef_sum Finset.univ (fun i _ ↦ branch_psd _ _ R.property.1)
 · rw [Matrix.trace_sum]; exact kraus_mass_sum C R

theorem branch_add (A R Q : M2) : branch A (R+Q)=branch A R+branch A Q := by simp [branch,Matrix.mul_add,Matrix.add_mul]
theorem branch_smul (A R : M2) (t : ℝ) : branch A (t • R)=t • branch A R := by simp [branch,Matrix.mul_smul,Matrix.smul_mul]

/- Real complete positivity: arbitrary finite ancilla, no complex-domain claim. -/
theorem real_kraus_complete_positivity (d : ℕ) (A : M2)
 (X : Matrix (Fin 2 × Fin d) (Fin 2 × Fin d) ℝ) (hX : X.PosSemidef) :
 ((A ⊗ₖ (1 : Matrix (Fin d) (Fin d) ℝ)) * X * (A ⊗ₖ (1 : Matrix (Fin d) (Fin d) ℝ))ᵀ).PosSemidef := by
 simpa only [Matrix.conjTranspose_eq_transpose_of_trivial] using hX.mul_mul_conjTranspose_same (A ⊗ₖ 1)

theorem real_kraus_sum_complete_positivity {ι : Type*} [Fintype ι]
 (d : ℕ) (A : ι → M2) (X : Matrix (Fin 2 × Fin d) (Fin 2 × Fin d) ℝ) (hX : X.PosSemidef) :
 (∑ i, (A i ⊗ₖ (1 : Matrix (Fin d) (Fin d) ℝ))*X*(A i ⊗ₖ (1 : Matrix (Fin d) (Fin d) ℝ))ᵀ).PosSemidef :=
 Matrix.posSemidef_sum Finset.univ (fun i _ ↦ real_kraus_complete_positivity d (A i) X hX)

noncomputable def luedersBinary (E : Effect) : KrausTest where
 arity := 2
 kraus := ![CFC.sqrt E.val,CFC.sqrt (1-E.val)]
 complete := by
  rw [Fin.sum_univ_two]
  simp only [Matrix.cons_val_zero,Matrix.cons_val_one,Matrix.head_cons]
  have h0 := (CFC.sqrt_nonneg E.val).posSemidef.isHermitian
  have h1 := (CFC.sqrt_nonneg (1-E.val)).posSemidef.isHermitian
  have ht0 : (CFC.sqrt E.val)ᵀ=CFC.sqrt E.val := by simpa [Matrix.conjTranspose_eq_transpose_of_trivial] using h0.eq
  have ht1 : (CFC.sqrt (1-E.val))ᵀ=CFC.sqrt (1-E.val) := by simpa [Matrix.conjTranspose_eq_transpose_of_trivial] using h1.eq
  rw [ht0,ht1,CFC.sqrt_mul_sqrt_self E.val E.property.1.nonneg,CFC.sqrt_mul_sqrt_self (1-E.val) E.property.2.nonneg]
  abel

noncomputable def luedersFamily (n : ℕ) (E : Fin n → Effect) (h : ∑ i, (E i).val=1) : KrausTest where
 arity := n
 kraus i := CFC.sqrt (E i).val
 complete := by
  convert h using 1
  apply Finset.sum_congr rfl; intro i _
  have ht : (CFC.sqrt (E i).val)ᵀ=CFC.sqrt (E i).val := by
   simpa [Matrix.conjTranspose_eq_transpose_of_trivial] using (CFC.sqrt_nonneg (E i).val).posSemidef.isHermitian.eq
  rw [ht,CFC.sqrt_mul_sqrt_self (E i).val (E i).property.1.nonneg]
end BornCalculus
