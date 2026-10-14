import BornCalculus.FrameApplications

namespace BornCalculus
open Matrix
open scoped BigOperators

/- An uncapped tree interpreter. The initial density and complete command list
are public parameters. Nodes retain labelled prefixes and a matrix product;
there is no claim of a single finite hidden space for all programs. The product
accumulator and the successive-state interpreter are defined independently. -/
def simplexProduct : (P : List KrausTest) → Outcomes P → M2 → M2
 | [], _, M => M
 | C :: P, (i, w), M => simplexProduct P w (C.kraus i * M)

def sequentialState : (P : List KrausTest) → Outcomes P → M2 → M2
 | [], _, R => R
 | C :: P, (i, w), R => sequentialState P w (branch (C.kraus i) R)

theorem simplexProduct_eq (P : List KrausTest) (w : Outcomes P) (M : M2) :
 simplexProduct P w M = wordMatrix P w * M := by
 induction P generalizing M with
 | nil => simp [simplexProduct, wordMatrix]
 | cons C P ih =>
   rcases w with ⟨i, w⟩
   simp [simplexProduct, wordMatrix, ih, Matrix.mul_assoc]

theorem sequentialState_eq (P : List KrausTest) (w : Outcomes P) (R : M2) :
 sequentialState P w R = branch (wordMatrix P w) R := by
 induction P generalizing R with
 | nil => simp [sequentialState, wordMatrix, branch]
 | cons C P ih =>
   rcases w with ⟨i, w⟩
   simp only [sequentialState, wordMatrix, ih, branch_comp]

def simplexState (P : List KrausTest) (w : Outcomes P) (R : M2) : M2 :=
 let M := simplexProduct P w 1
 M * R * Mᵀ

def simplexWeight (P : List KrausTest) (w : Outcomes P) (R : M2) : ℝ :=
 trace (simplexState P w R)

theorem simplex_state_preservation (P : List KrausTest) (w : Outcomes P) (R : M2) :
 simplexState P w R = sequentialState P w R := by
 simp [simplexState, simplexProduct_eq, sequentialState_eq, branch]

theorem simplex_weight_preservation (P : List KrausTest) (w : Outcomes P) (R : M2) :
 simplexWeight P w R = wordMass P w R := by
 simp [simplexWeight, simplexState, simplexProduct_eq, wordMass, branchMass, branch]

/-- Each fixed program supplies a genuine finite probability simplex. Its size
depends on the program; T2 imposes a different, uniform finite-vertex model. -/
theorem simplex_probability_laws (P : List KrausTest) (R : Density) :
 (∀ w : Outcomes P, 0 ≤ simplexWeight P w R.val) ∧
 (∑ w : Outcomes P, simplexWeight P w R.val) = 1 := by
 simp only [simplex_weight_preservation]
 exact ⟨fun w => branch_mass_nonnegative _ R, program_mass_sum P R⟩

/-- At a reached positive node the complete next test defines stochastic
outgoing probabilities on its normalized density. -/
theorem simplex_transition_laws (P : List KrausTest) (w : Outcomes P)
 (R : Density) (h : 0 < simplexWeight P w R.val) (C : KrausTest) :
 let Q : Density := ⟨normalizedMatrix (wordMatrix P w) R.val,
   normalized_branch_density _ R (by simpa [simplex_weight_preservation, wordMass] using h)⟩
 (∀ i, 0 ≤ branchMass (C.kraus i) Q.val) ∧
 (∑ i, branchMass (C.kraus i) Q.val) = 1 := by
 exact ⟨fun i => branch_mass_nonnegative _ _, kraus_mass_sum C _⟩

theorem simplex_posterior_preservation (P : List KrausTest) (w : Outcomes P)
 (R : Density) (h : 0 < simplexWeight P w R.val) :
 IsDensity ((simplexWeight P w R.val)⁻¹ • simplexState P w R.val) ∧
 (simplexWeight P w R.val)⁻¹ • simplexState P w R.val =
   normalizedMatrix (wordMatrix P w) R.val := by
 simp only [simplex_weight_preservation, simplex_state_preservation, sequentialState_eq] at h ⊢
 exact ⟨normalized_branch_density _ R h, rfl⟩

theorem simplex_zero_branch (P : List KrausTest) (w : Outcomes P)
 (R : Density) (h : simplexWeight P w R.val = 0) :
 simplexState P w R.val = 0 ∧ posterior (wordMatrix P w) R = none := by
 have hz : branchMass (wordMatrix P w) R.val = 0 :=
   by simpa [simplex_weight_preservation, wordMass] using h
 exact ⟨by rw [simplex_state_preservation, sequentialState_eq]; exact zero_mass_branch _ R hz,
   posterior_zero _ R hz⟩

theorem simplex_composition (P Q : List KrausTest) (x : Outcomes P)
 (y : Outcomes Q) (R : M2) :
 simplexState (P ++ Q) (appendOutcome x y) R =
   sequentialState Q y (simplexState P x R) := by
 simp only [simplex_state_preservation, sequentialState_eq, word_branch_concat]

theorem simplex_conditional_mass (P Q : List KrausTest) (x : Outcomes P)
 (y : Outcomes Q) (R : Density) (h : 0 < simplexWeight P x R.val) :
 simplexWeight P x R.val *
   simplexWeight Q y (normalizedMatrix (wordMatrix P x) R.val) =
   simplexWeight (P ++ Q) (appendOutcome x y) R.val := by
 simp only [simplex_weight_preservation, wordMass, word_concat] at h ⊢
 exact conditional_mass _ _ R h

theorem simplex_joint_posteriors (P Q : List KrausTest) (x : Outcomes P)
 (y : Outcomes Q) (R : Density)
 (h : 0 < simplexWeight (P ++ Q) (appendOutcome x y) R.val) :
 normalizedMatrix (wordMatrix Q y) (normalizedMatrix (wordMatrix P x) R.val) =
   (simplexWeight (P ++ Q) (appendOutcome x y) R.val)⁻¹ •
     simplexState (P ++ Q) (appendOutcome x y) R.val := by
 simp only [simplex_weight_preservation, simplex_state_preservation,
   sequentialState_eq, wordMass, word_concat] at h ⊢
 exact joint_normalized_posteriors _ _ R h

/- Public forgetting groups unnormalized states, including zero states.
It never averages normalized posteriors without their branch weights. -/
noncomputable def simplexPublic {α : Type*} (P : List KrausTest)
 (v : Outcomes P → α) (a : α) (R : M2) : M2 := by
 classical
 exact ∑ w : Outcomes P, if v w = a then simplexState P w R else 0

theorem simplex_forgetting_preservation {α : Type*} (P : List KrausTest)
 (v : Outcomes P → α) (a : α) (R : M2) :
 simplexPublic P v a R = publicBranch P v a R := by
 classical
 simp [simplexPublic, publicBranch, groupedBranch, Finset.sum_filter,
   simplex_state_preservation, sequentialState_eq]

theorem simplex_visibility_normalization {α : Type*} [Fintype α]
 (P : List KrausTest) (v : Outcomes P → α) (R : Density) :
 (∑ a : α, trace (simplexPublic P v a R.val)) = 1 := by
 simp only [simplex_forgetting_preservation]
 exact visibility_mass_sum P v R

/- The same independently stepped interpreter in a positive diagonal metric.
The commands here are in orthonormal coordinates; mapping GKrausTest commands
through gKrausToOrth supplies every admitted G command list. -/
noncomputable def gSequentialState (g₀ g₁ : ℝ) :
 (P : List KrausTest) → Outcomes P → M2 → M2
 | [], _, R => R
 | C :: P, (i, w), R =>
   let A := fromOrth g₀ g₁ (C.kraus i)
   gSequentialState g₀ g₁ P w (A * R * gAdjoint g₀ g₁ A)

theorem g_sequential_correspondence (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁)
 (P : List KrausTest) (w : Outcomes P) (R : M2) :
 toOrth g₀ g₁ (gSequentialState g₀ g₁ P w R) =
   sequentialState P w (toOrth g₀ g₁ R) := by
 have hf := frame_coordinate_transfer g₀ g₁ h₀ h₁
 induction P generalizing R with
 | nil => rfl
 | cons C P ih =>
   rcases w with ⟨i, w⟩
   simp only [gSequentialState, sequentialState, ih,
     g_branch_correspondence g₀ g₁ h₀ h₁, hf.inverse_right]

theorem g_simplex_state_preservation (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁)
 (P : List KrausTest) (w : Outcomes P) (R : M2) :
 fromOrth g₀ g₁ (simplexState P w (toOrth g₀ g₁ R)) =
   gSequentialState g₀ g₁ P w R := by
 have he := g_sequential_correspondence g₀ g₁ h₀ h₁ P w R
 rw [← simplex_state_preservation] at he
 simpa only [(frame_coordinate_transfer g₀ g₁ h₀ h₁).inverse_left]
   using (congrArg (fromOrth g₀ g₁) he).symm

end BornCalculus
