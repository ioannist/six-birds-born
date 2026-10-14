import BornCalculus.RIWitness

namespace BornCalculus
open Matrix
open scoped BigOperators

/-- A parent/coarse effect on the embedded retained subspace. Its unit is riP,
not the identity of the ambient 32-dimensional space. -/
noncomputable def riLensEffect {m : ℕ} (q : Fin 32 → Fin m) (j : Fin m) :
 Matrix (Fin 32) (Fin 32) ℝ :=
 riP * Matrix.diagonal (fun i => if q i = j then 1 else 0) * riP

noncomputable def riLensReadout {m : ℕ} (q : Fin 32 → Fin m) (j : Fin m)
 (p : Simplex32) : ℝ :=
 (∑ i : Fin 32, if q i = j then (riAmplitude p i)^2 else 0) / riAmplitudeDen p

theorem ri_lens_effect_positive {m : ℕ} (q : Fin 32 → Fin m) (j : Fin m) :
 (riLensEffect q j).PosSemidef ∧ (riP - riLensEffect q j).PosSemidef := by
 let D : Matrix (Fin 32) (Fin 32) ℝ :=
   Matrix.diagonal (fun i => if q i = j then 1 else 0)
 have hd : D.PosSemidef := Matrix.PosSemidef.diagonal (by intro i; dsimp; split_ifs <;> norm_num)
 have hc : (1 - D).PosSemidef := by
   have he : (1 : Matrix (Fin 32) (Fin 32) ℝ) - D =
     Matrix.diagonal (fun i => if q i = j then 0 else 1) := by
     ext i k
     by_cases hik : i = k
     · subst k; simp [D]; split_ifs <;> norm_num
     · simp [D, hik]
   rw [he]
   exact Matrix.PosSemidef.diagonal (by intro i; dsimp; split_ifs <;> norm_num)
 have ht : riPᴴ = riP := by
   rw [Matrix.conjTranspose_eq_transpose_of_trivial, riP_transpose]
 constructor
 · simpa only [riLensEffect, ht] using hd.mul_mul_conjTranspose_same riP
 · have he : riP * (1 - D) * riP = riP - riLensEffect q j := by
     simp [Matrix.mul_sub, Matrix.sub_mul, riP_idempotent, riLensEffect, D]
   simpa only [ht, he] using hc.mul_mul_conjTranspose_same riP

theorem ri_lens_effects_sum {m : ℕ} (q : Fin 32 → Fin m) :
 (∑ j : Fin m, riLensEffect q j) = riP := by
 classical
 have hd : (∑ j : Fin m, Matrix.diagonal (fun i : Fin 32 =>
   if q i = j then (1 : ℝ) else 0)) = 1 := by
   ext i k
   by_cases hik : i = k
   · subst k
     simp [Matrix.sum_apply, eq_comm]
   · simp [Matrix.sum_apply, hik]
 simp only [riLensEffect, ← Matrix.sum_mul, ← Matrix.mul_sum, hd,
   Matrix.mul_one, riP_idempotent]

theorem ri_lens_parent_coarsening {m : ℕ} (q : Fin 32 → Fin m) (j : Fin m) :
 riLensEffect q j = ∑ i : Fin 32, if q i = j then riLensEffect id i else 0 := by
 classical
 have hd : Matrix.diagonal (fun k : Fin 32 => if q k = j then (1 : ℝ) else 0) =
   ∑ i : Fin 32, if q i = j then Matrix.diagonal (fun k => if k = i then (1 : ℝ) else 0) else 0 := by
   ext a b
   by_cases hab : a = b
   · subst b
     simp only [Matrix.sum_apply]
     rw [Finset.sum_eq_single a]
     · simp [Matrix.ite_apply, diagonal_apply]
     · intro i _ hia
       simp [Matrix.ite_apply, diagonal_apply, hia, Ne.symm hia]
     · simp
   · simp [Matrix.sum_apply, Matrix.ite_apply, diagonal_apply, hab]
 simp only [riLensEffect, hd, Matrix.mul_sum, Matrix.sum_mul]
 apply Finset.sum_congr rfl
 intro i _
 split_ifs <;> simp

/-- Uniform trace pairing for every atom of every finite lens in the embedded
context. The two other registered lenses are specializations, not new inputs. -/
theorem ri_lens_trace_readout {m : ℕ} (q : Fin 32 → Fin m) (j : Fin m)
 (p : Simplex32) :
 trace (riUpperDensity p * riLensEffect q j) = riLensReadout q j p := by
 let a := riAmplitude p
 have ha : riP *ᵥ a = a := riAmplitude_in_V p
 have hva : a ᵥ* riP = a := by
   rw [← Matrix.mulVec_transpose, riP_transpose]; exact ha
 have hd : riUpperDensity p = (riAmplitudeDen p)⁻¹ • Matrix.vecMulVec a a := by
   ext i k; simp [riUpperDensity, Matrix.vecMulVec, div_eq_mul_inv, a]; ring
 let D : Matrix (Fin 32) (Fin 32) ℝ :=
   Matrix.diagonal (fun i => if q i = j then 1 else 0)
 have hprod : Matrix.vecMulVec a a * (riP * D * riP) =
   Matrix.vecMulVec a ((a ᵥ* D) ᵥ* riP) := by
   rw [← Matrix.mul_assoc, ← Matrix.mul_assoc, Matrix.vecMulVec_mul, hva,
     Matrix.vecMulVec_mul, Matrix.vecMulVec_mul]
 rw [hd]
 change trace (((riAmplitudeDen p)⁻¹ • Matrix.vecMulVec a a) * (riP * D * riP)) = _
 rw [Matrix.smul_mul, Matrix.trace_smul, hprod, Matrix.trace_vecMulVec,
   dotProduct_comm, ← Matrix.dotProduct_mulVec, ha]
 change (riAmplitudeDen p)⁻¹ * ((a ᵥ* D) ⬝ᵥ a) = _
 simp only [dotProduct, D, Matrix.vecMul_diagonal]
 dsimp [riLensReadout]
 rw [Finset.mul_sum, Finset.sum_div]
 apply Finset.sum_congr rfl
 intro i _
 dsimp [a]
 split_ifs <;> simp [div_eq_mul_inv] <;> ring

theorem ri_all_lens_trace_readouts (p : Simplex32) :
 (∀ j : Fin 2, trace (riUpperDensity p * riLensEffect riRaw j) = riLensReadout riRaw j p) ∧
 (∀ j : Fin 3, trace (riUpperDensity p * riLensEffect riPackage j) = riLensReadout riPackage j p) ∧
 (∀ j : Fin 3, trace (riUpperDensity p * riLensEffect riJoint j) = riLensReadout riJoint j p) :=
 ⟨fun j => ri_lens_trace_readout riRaw j p,
   fun j => ri_lens_trace_readout riPackage j p,
   fun j => ri_lens_trace_readout riJoint j p⟩

end BornCalculus
