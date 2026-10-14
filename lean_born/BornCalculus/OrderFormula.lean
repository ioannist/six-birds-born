import BornCalculus.PrincipalFormula
import BornCalculus.QuadraticBounds

namespace BornCalculus
open Matrix
set_option maxHeartbeats 0

noncomputable def orderConstant (C D : M2) : ℝ := (C*D*C) 0 0+C.det*D 0 0
noncomputable def orderLinear (C D : M2) : ℝ := (D*C+C*D) 0 0
noncomputable def orderRootValue (C D : M2) : ℝ :=
 (orderConstant C D+orderLinear C D*Real.sqrt C.det)/(trace C+2*Real.sqrt C.det)

/-- The two-read probability on the first coordinate state is a scalar
linear-radical quotient; no matrix-root approximation is assumed. -/
theorem principal_two_read_formula (C D : M2) (ht : 0 < trace C) (hd : 0 ≤ C.det) :
 (principalRadical C*D*principalRadical C) 0 0 = orderRootValue C D := by
 have hc : C ≠ 0 := by intro h; simp [h] at ht
 let d := Real.sqrt C.det
 let z := Real.sqrt (trace C+2*d)
 have hp : 0 < trace C+2*d := add_pos_of_pos_of_nonneg ht (by positivity)
 have hd2 : d^2 = C.det := Real.sq_sqrt hd
 have hz2 : z*z = trace C+2*d := Real.mul_self_sqrt hp.le
 have he : (C+d • (1:M2))*D*(C+d • (1:M2)) =
   C*D*C+d • (D*C+C*D)+d^2 • D := by
   simp [Matrix.mul_add,Matrix.add_mul,Matrix.smul_mul,Matrix.mul_smul,smul_smul,pow_two]
   module
 have hi : z⁻¹*z⁻¹ = (trace C+2*d)⁻¹ := by rw [←mul_inv,hz2]
 simp only [principalRadical,if_neg hc]
 change ((z⁻¹ • (C+d • (1:M2)))*D*(z⁻¹ • (C+d • (1:M2)))) 0 0 = orderRootValue C D
 simp only [Matrix.smul_mul,Matrix.mul_smul,smul_smul]
 rw [he,hi]
 simp [orderRootValue,orderConstant,orderLinear,hd2,d]
 ring

theorem gAdjoint_product (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁) (A B : M2) :
 gAdjoint g₀ g₁ (A*B) = gAdjoint g₀ g₁ B*gAdjoint g₀ g₁ A := by
 have hf := frame_coordinate_transfer g₀ g₁ h₀ h₁
 have he : toOrth g₀ g₁ (gAdjoint g₀ g₁ (A*B)) =
   toOrth g₀ g₁ (gAdjoint g₀ g₁ B*gAdjoint g₀ g₁ A) := by
   rw [hf.adjoint,hf.multiplication,hf.multiplication,hf.adjoint,hf.adjoint,Matrix.transpose_mul]
 simpa only [hf.inverse_left] using congrArg (fromOrth g₀ g₁) he

theorem principal_two_read_effect (g₀ g₁ : ℝ) (h₀ : 0 < g₀) (h₁ : 0 < g₁)
 (C D : M2) (hC : GPositive g₀ g₁ C) (hD : GPositive g₀ g₁ D) :
 gAdjoint g₀ g₁ (principalRadical D*principalRadical C)*
   (principalRadical D*principalRadical C) = principalRadical C*D*principalRadical C := by
 rw [gAdjoint_product g₀ g₁ h₀ h₁,
   g_principalRadical_selfadjoint g₀ g₁ h₀ h₁ D hD,
   g_principalRadical_selfadjoint g₀ g₁ h₀ h₁ C hC]
 calc
   (principalRadical C*principalRadical D)*(principalRadical D*principalRadical C) =
     principalRadical C*(principalRadical D*principalRadical D)*principalRadical C := by noncomm_ring
   _ = _ := by rw [g_principalRadical_square g₀ g₁ h₀ h₁ D hD]

theorem linear_radical_ratio_bounds (t a b d lo hi L U : ℝ)
 (ht : 0 < t) (hd : 0 ≤ d) (hl : lo ≤ d) (hu : d ≤ hi)
 (hL : 0 ≤ a-L*t+linearLower (b-2*L) lo hi)
 (hU : 0 ≤ U*t-a+linearLower (2*U-b) lo hi) :
 L ≤ (a+b*d)/(t+2*d) ∧ (a+b*d)/(t+2*d) ≤ U := by
 have hp : 0 < t+2*d := add_pos_of_pos_of_nonneg ht (by positivity)
 have h1 := linearLower_le (b-2*L) lo hi d hl hu
 have h2 := linearLower_le (2*U-b) lo hi d hl hu
 constructor
 · apply (le_div_iff₀ hp).mpr
   nlinarith
 · apply (div_le_iff₀ hp).mpr
   nlinarith

end BornCalculus
