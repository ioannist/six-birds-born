import BornCalculus.B06Witness
import BornCalculus.B07Witness

namespace BornCalculus
open Matrix
open scoped BigOperators MatrixOrder
set_option maxHeartbeats 0

def channelCQ (i : Fin 5) : Matrix (Fin 2) (Fin 2) ℚ :=
 ![b06RawQ 0,b06RawQ 1,b06PackageQ 0,b06PackageQ 1,b06PackageQ 2] i
noncomputable def channelC (i : Fin 5) : M2 := fun a b => (channelCQ i a b : ℝ)
def channelLoQ : Fin 5 → ℚ :=
 ![(15351861074974269 : ℚ) / 125000000000000000,(169573462381643589 : ℚ) / 1000000000000000000,(69128653004443771 : ℚ) / 1000000000000000000,(169573462381643589 : ℚ) / 1000000000000000000,(20010989165195047 : ℚ) / 500000000000000000]
def channelHiQ : Fin 5 → ℚ :=
 ![(122814888599794153 : ℚ) / 1000000000000000000,(16957346238164359 : ℚ) / 100000000000000000,(17282163251110943 : ℚ) / 250000000000000000,(16957346238164359 : ℚ) / 100000000000000000,(8004395666078019 : ℚ) / 200000000000000000]
def channelLowerQ : Fin 5 → ℚ :=
 ![(85958647 : ℚ) / 100000000,(2562769 : ℚ) / 50000000,(11432359 : ℚ) / 20000000,(2562769 : ℚ) / 50000000,(28507911 : ℚ) / 100000000]
def channelUpperQ : Fin 5 → ℚ :=
 ![(1719173 : ℚ) / 2000000,(5125541 : ℚ) / 100000000,(28580899 : ℚ) / 50000000,(5125541 : ℚ) / 100000000,(14253957 : ℚ) / 50000000]

def channelRatioChecks (i : Fin 5) : Prop :=
 let C := channelCQ i
 let t := trace C
 let d := C.det
 let a := (C 0 0)^2+d
 let b := 2*C 0 0
 let lo := channelLoQ i
 let hi := channelHiQ i
 let L := channelLowerQ i
 let U := channelUpperQ i
 0 < t ∧ 0 ≤ lo ∧ 0 ≤ hi ∧ lo^2 ≤ d ∧ d ≤ hi^2 ∧
 0 ≤ a-L*t+(if 0 ≤ b-2*L then (b-2*L)*lo else (b-2*L)*hi) ∧
 0 ≤ U*t-a+(if 0 ≤ 2*U-b then (2*U-b)*lo else (2*U-b)*hi)

theorem channel_ratio_checks (i : Fin 5) : channelRatioChecks i := by
 fin_cases i <;> norm_num [channelRatioChecks,channelCQ,b06RawQ,b06PackageQ,
   channelLoQ,channelHiQ,channelLowerQ,channelUpperQ,trace,Fin.sum_univ_two,Matrix.det_fin_two,Matrix.cons_val_two,Matrix.cons_val_three,Matrix.cons_val_four,Matrix.head_cons,Matrix.tail_cons]

/-- Branches use exactly the admitted principal G-roots. -/
noncomputable def channelBranch (C R : M2) : M2 :=
 principalRadical C * R * gAdjoint 32 b06S (principalRadical C)
noncomputable def rawForgotten (R : M2) : M2 := ∑ i : Fin 2, channelBranch (b06Raw i) R
noncomputable def packageForgotten (R : M2) : M2 := ∑ i : Fin 3, channelBranch (b06Package i) R

theorem channel_C_positive (i : Fin 5) : GPositive 32 b06S (channelC i) := by
 fin_cases i
 · exact b06_raw_positive 0
 · exact b06_raw_positive 1
 · exact b06_package_positive 0
 · exact b06_package_positive 1
 · exact b06_package_positive 2

theorem channel_branch_formula (i : Fin 5) :
 channelBranch (channelC i) b07Initial 0 0 =
 ((((channelCQ i 0 0)^2+(channelCQ i).det : ℚ) : ℝ) +
   2*(channelCQ i 0 0 : ℝ)*Real.sqrt (channelC i).det) /
   (trace (channelC i)+2*Real.sqrt (channelC i).det) := by
 have hc := channel_ratio_checks i
 have ht : 0 < trace (channelC i) := by
   have h : trace (channelC i) = ((trace (channelCQ i) : ℚ) : ℝ) := by
     simp [channelC,trace,Fin.sum_univ_two]
   rw [h]
   exact_mod_cast hc.1
 -- Determinants are invariant under the change of frame.
 have hd' : 0 ≤ (channelC i).det := by
   have hdet := frame_determinant_invariant 32 b06S (by norm_num) b06_s_positive (channelC i)
   rw [← hdet]
   exact ((frame_coordinate_transfer 32 b06S (by norm_num) b06_s_positive).positive _
     |>.mp (channel_C_positive i)).det_nonneg
 rw [channelBranch,g_principalRadical_selfadjoint 32 b06S (by norm_num) b06_s_positive
   _ (channel_C_positive i),principal_two_read_formula _ _ ht hd']
 simp [orderRootValue,orderConstant,orderLinear,b07Initial,channelC,trace,
   mul_apply,Matrix.vecMul,dotProduct,Fin.sum_univ_two,Matrix.det_fin_two]
 ring

private theorem cast_linearLower (a lo hi : ℚ) :
 linearLower (a:ℝ) (lo:ℝ) (hi:ℝ) =
   ((if 0 ≤ a then a*lo else a*hi : ℚ):ℝ) := by
 by_cases h : 0 ≤ a
 · have hr : (0:ℝ) ≤ (a:ℝ) := by exact_mod_cast h
   simp [linearLower,h,hr]
 · have hr : ¬ (0:ℝ) ≤ (a:ℝ) := by exact_mod_cast h
   simp [linearLower,h,hr]

theorem channel_branch_bounds (i : Fin 5) :
 (channelLowerQ i : ℝ) ≤ channelBranch (channelC i) b07Initial 0 0 ∧
 channelBranch (channelC i) b07Initial 0 0 ≤ (channelUpperQ i : ℝ) := by
 let C := channelCQ i
 let t := trace C
 let d := C.det
 let a := (C 0 0)^2+d
 let b := 2*C 0 0
 have hc := channel_ratio_checks i
 change 0 < t ∧ _ at hc
 have hdet : (channelC i).det = (d:ℝ) := by
   simp [channelC,d,C,Matrix.det_fin_two]
 have htrace : trace (channelC i) = (t:ℝ) := by
   simp [channelC,t,C,trace,Fin.sum_univ_two]
 have hb : (channelLoQ i:ℝ) ≤ Real.sqrt (d:ℝ) ∧
     Real.sqrt (d:ℝ) ≤ (channelHiQ i:ℝ) := by
   apply sqrt_bounds_of_squared_bounds
   · exact_mod_cast hc.2.1
   · exact_mod_cast hc.2.2.1
   · exact_mod_cast hc.2.2.2.1
   · exact_mod_cast hc.2.2.2.2.1
 have ht : (0:ℝ) < (t:ℝ) := by exact_mod_cast hc.1
 have hL : 0 ≤ (a:ℝ)-(channelLowerQ i:ℝ)*(t:ℝ)+
     linearLower ((b:ℝ)-2*(channelLowerQ i:ℝ)) (channelLoQ i:ℝ) (channelHiQ i:ℝ) := by
   rw [show ((b:ℝ)-2*(channelLowerQ i:ℝ)) = ((b-2*channelLowerQ i:ℚ):ℝ) by simp,
     cast_linearLower]
   exact_mod_cast hc.2.2.2.2.2.1
 have hU : 0 ≤ (channelUpperQ i:ℝ)*(t:ℝ)-(a:ℝ)+
     linearLower (2*(channelUpperQ i:ℝ)-(b:ℝ)) (channelLoQ i:ℝ) (channelHiQ i:ℝ) := by
   rw [show (2*(channelUpperQ i:ℝ)-(b:ℝ)) = ((2*channelUpperQ i-b:ℚ):ℝ) by simp,
     cast_linearLower]
   exact_mod_cast hc.2.2.2.2.2.2
 rw [channel_branch_formula,hdet,htrace]
 have hh := linear_radical_ratio_bounds (t:ℝ) (a:ℝ) (b:ℝ) (Real.sqrt (d:ℝ))
   (channelLoQ i:ℝ) (channelHiQ i:ℝ) (channelLowerQ i:ℝ) (channelUpperQ i:ℝ)
   ht (Real.sqrt_nonneg _) hb.1 hb.2 hL hU
 simpa only [a,b,C,Rat.cast_mul,Rat.cast_ofNat] using hh

theorem raw_forgotten_bounds :
 (91084185/100000000 : ℝ) ≤ rawForgotten b07Initial 0 0 ∧
 rawForgotten b07Initial 0 0 ≤ (91084191/100000000 : ℝ) := by
 have h0 := channel_branch_bounds 0
 have h1 := channel_branch_bounds 1
 change (channelLowerQ 0:ℝ) ≤ channelBranch (b06Raw 0) b07Initial 0 0 ∧
   channelBranch (b06Raw 0) b07Initial 0 0 ≤ (channelUpperQ 0:ℝ) at h0
 change (channelLowerQ 1:ℝ) ≤ channelBranch (b06Raw 1) b07Initial 0 0 ∧
   channelBranch (b06Raw 1) b07Initial 0 0 ≤ (channelUpperQ 1:ℝ) at h1
 norm_num [channelLowerQ,channelUpperQ,Matrix.cons_val_two,Matrix.cons_val_three,Matrix.cons_val_four,Matrix.head_cons,Matrix.tail_cons] at h0 h1
 simp only [rawForgotten,Fin.sum_univ_two,Matrix.add_apply]
 constructor <;> linarith

theorem package_forgotten_bounds :
 (90795244/100000000 : ℝ) ≤ packageForgotten b07Initial 0 0 ∧
 packageForgotten b07Initial 0 0 ≤ (90795253/100000000 : ℝ) := by
 have h0 := channel_branch_bounds 2
 have h1 := channel_branch_bounds 3
 have h2 := channel_branch_bounds 4
 change (channelLowerQ 2:ℝ) ≤ channelBranch (b06Package 0) b07Initial 0 0 ∧
   channelBranch (b06Package 0) b07Initial 0 0 ≤ (channelUpperQ 2:ℝ) at h0
 change (channelLowerQ 3:ℝ) ≤ channelBranch (b06Package 1) b07Initial 0 0 ∧
   channelBranch (b06Package 1) b07Initial 0 0 ≤ (channelUpperQ 3:ℝ) at h1
 change (channelLowerQ 4:ℝ) ≤ channelBranch (b06Package 2) b07Initial 0 0 ∧
   channelBranch (b06Package 2) b07Initial 0 0 ≤ (channelUpperQ 4:ℝ) at h2
 norm_num [channelLowerQ,channelUpperQ,Matrix.cons_val_two,Matrix.cons_val_three,Matrix.cons_val_four,Matrix.head_cons,Matrix.tail_cons] at h0 h1 h2
 simp only [packageForgotten,Fin.sum_univ_three,Matrix.add_apply]
 constructor <;> linarith

theorem worked_forgotten_channels_distinct :
 rawForgotten b07Initial ≠ packageForgotten b07Initial ∧
 rawForgotten b07Initial ≠ b07Initial ∧ packageForgotten b07Initial ≠ b07Initial := by
 have hr := raw_forgotten_bounds
 have hp := package_forgotten_bounds
 refine ⟨?_,?_,?_⟩
 · intro he
   have h := congrArg (fun A : M2 => A 0 0) he
   linarith
 · intro he
   have h := congrArg (fun A : M2 => A 0 0) he
   change rawForgotten b07Initial 0 0 = 1 at h
   linarith
 · intro he
   have h := congrArg (fun A : M2 => A 0 0) he
   change packageForgotten b07Initial 0 0 = 1 at h
   linarith

/-- The channels above are exactly the existing Kraus branches after the
established diagonal change of coordinates. -/
theorem channel_branch_toOrth (C R : M2) (hC : GPositive 32 b06S C) :
 toOrth 32 b06S (channelBranch C R) =
 branch (CFC.sqrt (toOrth 32 b06S C)) (toOrth 32 b06S R) := by
 have hf := frame_coordinate_transfer 32 b06S (by norm_num) b06_s_positive
 rw [channelBranch,hf.multiplication,hf.multiplication,hf.adjoint,
   principalRadical_frame_correspondence 32 b06S (by norm_num) b06_s_positive,
   principalRadical_eq_sqrt _ ((hf.positive C).mp hC)]
 rfl

theorem raw_forgotten_existing_test (R : M2) :
 toOrth 32 b06S (rawForgotten R) =
 ∑ i, branch (b06RawTest.kraus i) (toOrth 32 b06S R) := by
 simp only [rawForgotten,toOrth,Matrix.mul_sum,Matrix.sum_mul]
 change (∑ i : Fin 2, toOrth 32 b06S (channelBranch (b06Raw i) R)) = _
 exact Finset.sum_congr rfl (fun i _ => channel_branch_toOrth _ R (b06_raw_positive i))

theorem package_forgotten_existing_test (R : M2) :
 toOrth 32 b06S (packageForgotten R) =
 ∑ i, branch (b06PackageTest.kraus i) (toOrth 32 b06S R) := by
 simp only [packageForgotten,toOrth,Matrix.mul_sum,Matrix.sum_mul]
 change (∑ i : Fin 3, toOrth 32 b06S (channelBranch (b06Package i) R)) = _
 exact Finset.sum_congr rfl (fun i _ => channel_branch_toOrth _ R (b06_package_positive i))

/-- Equal total effects of the actual raw, package, and empty programs,
with three different forgotten outputs on a certified density. -/
theorem worked_equal_effects_unequal_channels :
 let R := toOrth 32 b06S b07Initial
 IsDensity R ∧
 groupedEffect [b06RawTest] Finset.univ = 1 ∧
 groupedEffect [b06PackageTest] Finset.univ = 1 ∧
 groupedEffect [] Finset.univ = 1 ∧
 (∑ i, branch (b06RawTest.kraus i) R) ≠
   (∑ i, branch (b06PackageTest.kraus i) R) ∧
 (∑ i, branch (b06RawTest.kraus i) R) ≠ R ∧
 (∑ i, branch (b06PackageTest.kraus i) R) ≠ R := by
 have hf := frame_coordinate_transfer 32 b06S (by norm_num) b06_s_positive
 have hinj : Function.Injective (toOrth 32 b06S) := by
   intro X Y he
   simpa only [hf.inverse_left] using congrArg (fromOrth 32 b06S) he
 have hd := (hf.density_domain _).mp b07_initial_domain
 have hw := worked_forgotten_channels_distinct
 refine ⟨hd,program_effects_sum _,program_effects_sum _,program_effects_sum _,?_,?_,?_⟩
 · rw [← raw_forgotten_existing_test,← package_forgotten_existing_test]
   exact fun he => hw.1 (hinj he)
 · rw [← raw_forgotten_existing_test]
   exact fun he => hw.2.1 (hinj he)
 · rw [← package_forgotten_existing_test]
   exact fun he => hw.2.2 (hinj he)

theorem empty_program_forgotten (R : M2) :
 (∑ w : Outcomes [], branch (wordMatrix [] w) R) = R := by
 simp [Outcomes,wordMatrix,branch]

#print axioms worked_equal_effects_unequal_channels
#print axioms empty_program_forgotten

#print axioms channel_ratio_checks
#print axioms channel_C_positive
#print axioms channel_branch_formula
#print axioms channel_branch_bounds
#print axioms raw_forgotten_bounds
#print axioms package_forgotten_bounds
#print axioms worked_forgotten_channels_distinct
#print axioms channel_branch_toOrth
#print axioms raw_forgotten_existing_test
#print axioms package_forgotten_existing_test
end BornCalculus
