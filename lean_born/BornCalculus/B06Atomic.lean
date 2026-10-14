import BornCalculus.B06Inputs
import BornCalculus.SmallMatrices
import BornCalculus.PrincipalFormula
import BornCalculus.FiniteFragmentFrame

namespace BornCalculus
open Matrix
open scoped MatrixOrder BigOperators
set_option maxHeartbeats 0

noncomputable def b06S : ℝ := (b06SQ : ℝ)
noncomputable def b06Raw (i : Fin 2) : M2 := fun a b => (b06RawQ i a b : ℝ)
noncomputable def b06Package (i : Fin 3) : M2 := fun a b => (b06PackageQ i a b : ℝ)
noncomputable def b06Joint (i : Fin 3) : M2 := fun a b => (b06JointQ i a b : ℝ)

theorem b06_s_positiveQ : 0 < b06SQ := by norm_num [b06SQ]
theorem b06_s_positive : 0 < b06S := by
 change (0 : ℝ) < (b06SQ : ℝ)
 exact_mod_cast b06_s_positiveQ

def B06ScalarChecks (C : Matrix (Fin 2) (Fin 2) ℚ) : Prop :=
 (32 : ℚ)*C 0 1 = b06SQ*C 1 0 ∧ 0 < C 0 0 ∧ 0 < C.det

theorem b06_raw_checksQ (i : Fin 2) : B06ScalarChecks (b06RawQ i) := by
 fin_cases i <;> norm_num [B06ScalarChecks, b06RawQ, b06SQ, Matrix.det_fin_two]
theorem b06_package_checksQ (i : Fin 3) : B06ScalarChecks (b06PackageQ i) := by
 fin_cases i <;> norm_num [B06ScalarChecks, b06PackageQ, b06SQ, Matrix.det_fin_two]
theorem b06_joint_checksQ (i : Fin 3) : B06ScalarChecks (b06JointQ i) := by
 fin_cases i <;> norm_num [B06ScalarChecks, b06JointQ, b06SQ, Matrix.det_fin_two]

theorem b06_raw_sumQ : (∑ i : Fin 2, b06RawQ i) = 1 := by
 ext a b
 fin_cases a <;> fin_cases b <;> norm_num [b06RawQ, Fin.sum_univ_two]
theorem b06_package_sumQ : (∑ i : Fin 3, b06PackageQ i) = 1 := by
 ext a b
 fin_cases a <;> fin_cases b <;> norm_num [b06PackageQ, Fin.sum_univ_succ]
theorem b06_joint_sumQ : (∑ i : Fin 3, b06JointQ i) = 1 := by
 ext a b
 fin_cases a <;> fin_cases b <;> norm_num [b06JointQ, Fin.sum_univ_succ]

noncomputable def b06CastMatrix (C : Matrix (Fin 2) (Fin 2) ℚ) : M2 :=
 fun a b => (C a b : ℝ)

private theorem b06_cast_det (C : Matrix (Fin 2) (Fin 2) ℚ) :
 (b06CastMatrix C).det = (C.det : ℝ) := by
 simp [b06CastMatrix, Matrix.det_fin_two]

private theorem b06_cast_checks (C : Matrix (Fin 2) (Fin 2) ℚ)
 (hc : B06ScalarChecks C) :
 GPositive 32 b06S (b06CastMatrix C) ∧
   0 < (b06CastMatrix C).det := by
 have hs : (32 : ℝ)*(C 0 1 : ℝ) = b06S*(C 1 0 : ℝ) := by
   change (32 : ℝ)*(C 0 1 : ℝ) = (b06SQ : ℝ)*(C 1 0 : ℝ)
   exact_mod_cast hc.1
 have ha : (0 : ℝ) < (C 0 0 : ℝ) := by exact_mod_cast hc.2.1
 have hd : (0 : ℝ) < (b06CastMatrix C).det := by
   rw [b06_cast_det]
   exact_mod_cast hc.2.2
 exact ⟨g_positive_of_two_checks 32 b06S (by norm_num) b06_s_positive _ hs ha hd, hd⟩

theorem b06_raw_positive (i : Fin 2) : GPositive 32 b06S (b06Raw i) :=
 (b06_cast_checks _ (b06_raw_checksQ i)).1
theorem b06_package_positive (i : Fin 3) : GPositive 32 b06S (b06Package i) :=
 (b06_cast_checks _ (b06_package_checksQ i)).1
theorem b06_joint_positive (i : Fin 3) : GPositive 32 b06S (b06Joint i) :=
 (b06_cast_checks _ (b06_joint_checksQ i)).1

theorem b06_raw_det_positive (i : Fin 2) : 0 < (b06Raw i).det :=
 (b06_cast_checks _ (b06_raw_checksQ i)).2
theorem b06_package_det_positive (i : Fin 3) : 0 < (b06Package i).det :=
 (b06_cast_checks _ (b06_package_checksQ i)).2
theorem b06_joint_det_positive (i : Fin 3) : 0 < (b06Joint i).det :=
 (b06_cast_checks _ (b06_joint_checksQ i)).2

theorem b06_raw_sum : (∑ i : Fin 2, b06Raw i) = 1 := by
 ext a b
 have h := congrArg (fun C : Matrix (Fin 2) (Fin 2) ℚ => C a b) b06_raw_sumQ
 simp only [Matrix.sum_apply, Matrix.one_apply, b06Raw] at h ⊢
 simpa only [Rat.cast_sum, apply_ite, Rat.cast_one, Rat.cast_zero] using
   congrArg (fun q : ℚ => (q : ℝ)) h
theorem b06_package_sum : (∑ i : Fin 3, b06Package i) = 1 := by
 ext a b
 have h := congrArg (fun C : Matrix (Fin 2) (Fin 2) ℚ => C a b) b06_package_sumQ
 simp only [Matrix.sum_apply, Matrix.one_apply, b06Package] at h ⊢
 simpa only [Rat.cast_sum, apply_ite, Rat.cast_one, Rat.cast_zero] using
   congrArg (fun q : ℚ => (q : ℝ)) h
theorem b06_joint_sum : (∑ i : Fin 3, b06Joint i) = 1 := by
 ext a b
 have h := congrArg (fun C : Matrix (Fin 2) (Fin 2) ℚ => C a b) b06_joint_sumQ
 simp only [Matrix.sum_apply, Matrix.one_apply, b06Joint] at h ⊢
 simpa only [Rat.cast_sum, apply_ite, Rat.cast_one, Rat.cast_zero] using
   congrArg (fun q : ℚ => (q : ℝ)) h

noncomputable def b06RawEffect (i : Fin 2) : GEffect 32 b06S :=
 ⟨b06Raw i, complete_g_effect_domains _ _ _ b06_raw_positive b06_raw_sum i⟩
noncomputable def b06PackageEffect (i : Fin 3) : GEffect 32 b06S :=
 ⟨b06Package i, complete_g_effect_domains _ _ _ b06_package_positive b06_package_sum i⟩
noncomputable def b06JointEffect (i : Fin 3) : GEffect 32 b06S :=
 ⟨b06Joint i, complete_g_effect_domains _ _ _ b06_joint_positive b06_joint_sum i⟩

noncomputable def b06BasisEffect : Fin 3 → GEffect 32 b06S :=
 ![⟨1, complete_g_effect_domains 32 b06S (fun _ : Unit => 1)
   (by intro _; exact (frame_coordinate_transfer 32 b06S (by norm_num) b06_s_positive).positive 1 |>.mpr (by
     rw [(frame_coordinate_transfer 32 b06S (by norm_num) b06_s_positive).unit]
     exact Matrix.PosSemidef.one)) (by simp) ()⟩,
   b06JointEffect 0, b06JointEffect 1]

theorem b06_basis_det_nonzero : (fragmentBasisMatrix (fun i => (b06BasisEffect i).val)).det ≠ 0 := by
 norm_num [fragmentBasisMatrix, b06BasisEffect, b06JointEffect, b06Joint, b06JointQ,
   Matrix.det_fin_three, Matrix.cons_val_two, Matrix.head_cons, Matrix.tail_cons]

end BornCalculus
