import BornCalculus.Instruments

namespace BornCalculus
open Matrix
open scoped MatrixOrder BigOperators
set_option maxHeartbeats 0

def Outcomes : List KrausTest → Type
 | [] => Unit
 | C::P => Fin C.arity × Outcomes P
instance outcomesFintype (P : List KrausTest) : Fintype (Outcomes P) := by
 induction P with
 | nil => exact inferInstanceAs (Fintype Unit)
 | cons C P ih =>
   letI : Fintype (Outcomes P) := ih
   exact inferInstanceAs (Fintype (Fin C.arity × Outcomes P))

def wordMatrix : (P : List KrausTest) → Outcomes P → M2
 | [],_ => 1
 | C::P,(i,w) => wordMatrix P w * C.kraus i
def wordEffect (P : List KrausTest) (w : Outcomes P) : M2 := (wordMatrix P w)ᵀ * wordMatrix P w
def wordMass (P : List KrausTest) (w : Outcomes P) (R : M2) : ℝ := branchMass (wordMatrix P w) R

def appendOutcome : {P Q : List KrausTest} → Outcomes P → Outcomes Q → Outcomes (P++Q)
 | [],_,_,y => y
 | _::_,_,(i,x),y => (i,appendOutcome x y)

theorem wordEffect_cons (C : KrausTest) (P : List KrausTest) (i : Fin C.arity) (w : Outcomes P) :
 wordEffect (C::P) (i,w)=(C.kraus i)ᵀ * wordEffect P w * C.kraus i := by
 simp [wordEffect,wordMatrix,Matrix.transpose_mul,Matrix.mul_assoc]

theorem program_effects_sum (P : List KrausTest) : ∑ w : Outcomes P, wordEffect P w=1 := by
 classical
 induction P with
 | nil => simp [wordEffect,wordMatrix,Outcomes]
 | cons C P ih =>
   change (∑ w : Fin C.arity × Outcomes P, wordEffect (C::P) w)=1
   rw [Fintype.sum_prod_type]
   simp_rw [wordEffect_cons,← Matrix.sum_mul,← Matrix.mul_sum,ih,Matrix.mul_one]
   exact C.complete

theorem word_probability_pairing (P : List KrausTest) (w : Outcomes P) (R : Density) :
 wordMass P w R.val=pairing R.val (wordEffect P w) := branch_mass_pairing _ _

theorem program_mass_sum (P : List KrausTest) (R : Density) : ∑ w : Outcomes P, wordMass P w R.val=1 := by
 simp_rw [word_probability_pairing,pairing]
 rw [← Matrix.trace_sum,← Matrix.mul_sum,program_effects_sum,Matrix.mul_one]
 exact R.property.2

theorem word_concat (P Q : List KrausTest) (x : Outcomes P) (y : Outcomes Q) :
 wordMatrix (P++Q) (appendOutcome x y)=wordMatrix Q y*wordMatrix P x := by
 induction P with
 | nil => simp [appendOutcome,wordMatrix]
 | cons C P ih =>
   rcases x with ⟨i,x⟩
   simpa [appendOutcome,wordMatrix,Matrix.mul_assoc] using congrArg (fun Z ↦ Z*C.kraus i) (ih x)

theorem word_effect_psd (P : List KrausTest) (w : Outcomes P) : (wordEffect P w).PosSemidef := by
 simpa [wordEffect,Matrix.conjTranspose_eq_transpose_of_trivial] using Matrix.posSemidef_conjTranspose_mul_self (wordMatrix P w)

noncomputable def groupedEffect (P : List KrausTest) (s : Finset (Outcomes P)) : M2 := ∑ w ∈ s, wordEffect P w

theorem grouped_effect_is_effect (P : List KrausTest) (s : Finset (Outcomes P)) : IsEffect (groupedEffect P s) := by
 classical
 constructor
 · exact Matrix.posSemidef_sum s (fun w _ ↦ word_effect_psd P w)
 · have hle : groupedEffect P s ≤ ∑ w : Outcomes P, wordEffect P w :=
    Finset.sum_le_sum_of_subset_of_nonneg (Finset.subset_univ s) (fun w _ _ ↦ (word_effect_psd P w).nonneg)
   rw [program_effects_sum] at hle
   exact hle

theorem word_is_effect (P : List KrausTest) (w : Outcomes P) : IsEffect (wordEffect P w) := by
 classical
 simpa [groupedEffect] using grouped_effect_is_effect P {w}

theorem branch_comp (A B R : M2) : branch B (branch A R)=branch (B*A) R := by
 simp [branch,Matrix.transpose_mul,Matrix.mul_assoc]

theorem word_branch_concat (P Q : List KrausTest) (x : Outcomes P) (y : Outcomes Q) (R : M2) :
 branch (wordMatrix (P++Q) (appendOutcome x y)) R=
 branch (wordMatrix Q y) (branch (wordMatrix P x) R) := by rw [word_concat,branch_comp]

noncomputable def normalizedMatrix (A R : M2) : M2 := (branchMass A R)⁻¹ • branch A R

theorem conditional_composition (A B : M2) (R : Density) (h : 0 < branchMass A R.val) :
 branchMass A R.val • branch B (normalizedMatrix A R.val)=branch (B*A) R.val := by
 rw [normalizedMatrix,branch_smul,smul_smul,mul_inv_cancel₀ h.ne',one_smul,branch_comp]

theorem conditional_mass (A B : M2) (R : Density) (h : 0 < branchMass A R.val) :
 branchMass A R.val * branchMass B (normalizedMatrix A R.val)=branchMass (B*A) R.val := by
 simpa [branchMass,Matrix.trace_smul] using congrArg Matrix.trace (conditional_composition A B R h)

theorem joint_normalized_posteriors_of_prefix_positive (A B : M2) (R : Density)
 (hp : 0 < branchMass A R.val) (hj : 0 < branchMass (B*A) R.val) :
 normalizedMatrix B (normalizedMatrix A R.val)=normalizedMatrix (B*A) R.val := by
 have hm := conditional_mass A B R hp
 have hn : branchMass B (normalizedMatrix A R.val)≠0 := by intro hz; rw [hz,mul_zero] at hm; linarith
 have hb := conditional_composition A B R hp
 change (branchMass B (normalizedMatrix A R.val))⁻¹ • branch B (normalizedMatrix A R.val) = (branchMass (B*A) R.val)⁻¹ • branch (B*A) R.val
 rw [← hm,← hb]
 simp [_root_.mul_inv_rev,smul_smul,hp.ne',hn]

/-- Positive joint mass forces positive prefix mass; the exported theorem needs
 only the joint-mass premise. -/
theorem joint_normalized_posteriors (A B : M2) (R : Density)
 (hj : 0 < branchMass (B*A) R.val) :
 normalizedMatrix B (normalizedMatrix A R.val)=normalizedMatrix (B*A) R.val := by
 have hp : 0 < branchMass A R.val := by
   by_contra hnot
   have hz : branchMass A R.val=0 :=
     le_antisymm (le_of_not_gt hnot) (branch_mass_nonnegative A R)
   have hzero := zero_mass_branch A R hz
   have hjzero : branchMass (B*A) R.val=0 := by
     rw [branchMass,←branch_comp,hzero]
     simp [branch]
   rw [hjzero] at hj
   exact (lt_irrefl 0) hj
 exact joint_normalized_posteriors_of_prefix_positive A B R hp hj

noncomputable def groupedBranch (P : List KrausTest) (s : Finset (Outcomes P)) (R : M2) : M2 :=
 ∑ w ∈ s, branch (wordMatrix P w) R

theorem grouping_mass (P : List KrausTest) (s : Finset (Outcomes P)) (R : Density) :
 Matrix.trace (groupedBranch P s R.val)=∑ w ∈ s, wordMass P w R.val := by
 simp [groupedBranch,wordMass,branchMass,Matrix.trace_sum]

theorem grouping_psd (P : List KrausTest) (s : Finset (Outcomes P)) (R : Density) :
 (groupedBranch P s R.val).PosSemidef := Matrix.posSemidef_sum s (fun _ _ ↦ branch_psd _ _ R.property.1)

theorem grouping_then_suffix (P Q : List KrausTest) (s : Finset (Outcomes P)) (y : Outcomes Q) (R : M2) :
 branch (wordMatrix Q y) (groupedBranch P s R)=
 ∑ x ∈ s, branch (wordMatrix (P++Q) (appendOutcome x y)) R := by
 classical
 simp only [groupedBranch,branch,Matrix.mul_sum,Matrix.sum_mul]
 apply Finset.sum_congr rfl; intro x _
 simpa only [branch] using (word_branch_concat P Q x y R).symm

noncomputable def publicBranch {α : Type*} (P : List KrausTest) (visibility : Outcomes P → α)
 (a : α) (R : M2) : M2 := by
 classical
 exact groupedBranch P (Finset.univ.filter (fun w ↦ visibility w=a)) R

theorem visibility_mass {α : Type*} (P : List KrausTest) (visibility : Outcomes P → α)
 (a : α) (R : Density) :
 Matrix.trace (publicBranch P visibility a R.val)=
 (by classical exact ∑ w : Outcomes P, if visibility w=a then wordMass P w R.val else 0) := by
 classical
 simp [publicBranch,grouping_mass,Finset.sum_filter]

theorem density_sufficiency {α : Type*} (P : List KrausTest) (v : Outcomes P → α)
 (a : α) (R Q : Density) (h : R=Q) : publicBranch P v a R.val=publicBranch P v a Q.val := by rw [h]

theorem empty_program_identity (R : M2) (w : Outcomes []) : branch (wordMatrix [] w) R=R := by simp [wordMatrix,branch]

/- Administrative tags emit a public absorbing tag and execute no measurement.
 They are disjoint from KrausTest; invalid commands cannot become instruments. -/
inductive AdminTag | halt | publicFailure deriving DecidableEq
structure AdminState where
 tag : AdminTag
 density : Density
 ledger : List String
def adminStep (S : AdminState) (_ : Option KrausTest) : AdminState := S
theorem admin_absorbing (S : AdminState) (c : Option KrausTest) : adminStep S c=S := rfl


theorem grouped_normalization_density (P : List KrausTest) (s : Finset (Outcomes P))
 (R : Density) (h : 0<Matrix.trace (groupedBranch P s R.val)) :
 IsDensity ((Matrix.trace (groupedBranch P s R.val))⁻¹ • groupedBranch P s R.val) := by
 refine ⟨(grouping_psd P s R).smul (inv_nonneg.mpr h.le),?_⟩
 simp [Matrix.trace_smul,h.ne']

theorem grouped_zero_mass (P : List KrausTest) (s : Finset (Outcomes P))
 (R : Density) (h : Matrix.trace (groupedBranch P s R.val)=0) : groupedBranch P s R.val=0 :=
 (psd_trace_zero_iff _ (grouping_psd P s R)).mp h

theorem program_forgetting_density (P : List KrausTest) (R : Density) :
 IsDensity (groupedBranch P Finset.univ R.val) := by
 refine ⟨grouping_psd P _ R,?_⟩
 rw [grouping_mass]
 exact program_mass_sum P R

theorem visibility_mass_sum {α : Type*} [Fintype α] (P : List KrausTest)
 (v : Outcomes P → α) (R : Density) : ∑ a : α,Matrix.trace (publicBranch P v a R.val)=1 := by
 classical
 simp_rw [visibility_mass]
 rw [Finset.sum_comm]
 simpa using program_mass_sum P R

noncomputable def validateKraus (n : ℕ) (A : Fin n → M2) : Sum AdminTag KrausTest := by
 classical
 exact if h : ∑ i,(A i)ᵀ*A i=1 then .inr ⟨n,A,h⟩ else .inl .publicFailure

theorem invalid_command_failure (n : ℕ) (A : Fin n → M2)
 (h : (∑ i,(A i)ᵀ*A i)≠1) : validateKraus n A=Sum.inl AdminTag.publicFailure := by
 classical
 simp [validateKraus,h]
theorem valid_command_not_coerced (C : KrausTest) : validateKraus C.arity C.kraus=Sum.inr C := by
 classical
 simp [validateKraus,C.complete]
end BornCalculus
