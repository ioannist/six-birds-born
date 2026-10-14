import BornCalculus.RIParents
import BornCalculus.Frame

namespace BornCalculus
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0

/- Exact coordinates of the embedded retained carrier in the basis (1,w).
The metric is diag(32,riS). No additional projector or preparation is imported. -/
noncomputable def riFrameW (i : Fin 32) : ℝ := (riWQ i : ℝ)

theorem riFrameW_centered : (∑ i : Fin 32, riFrameW i) = 0 := by
 dsimp [riFrameW]
 exact_mod_cast ri_centeredQ

theorem riFrameW_norm : (∑ i : Fin 32, (riFrameW i)^2) = riS := by
 simp only [riFrameW, riS, pow_two]
 exact_mod_cast ri_normQ

theorem riP_frame_formula (i j : Fin 32) :
 riP i j = 1 / 32 + riFrameW i * riFrameW j / riS := by
 simp [riP, riPQ, riFrameW, riS]

noncomputable def riFrameA (p : Simplex32) : ℝ :=
 (∑ i : Fin 32, Real.sqrt (p.val i)) / 32
noncomputable def riFrameB (p : Simplex32) : ℝ :=
 (∑ i : Fin 32, riFrameW i * Real.sqrt (p.val i)) / riS
noncomputable def riFrameDen (p : Simplex32) : ℝ :=
 32 * (riFrameA p)^2 + riS * (riFrameB p)^2

theorem riAmplitude_frame_formula (p : Simplex32) (i : Fin 32) :
 riAmplitude p i = riFrameA p + riFrameB p * riFrameW i := by
 simp only [riAmplitude, mulVec, dotProduct, riP_frame_formula]
 calc
   (∑ k : Fin 32, (1 / 32 + riFrameW i * riFrameW k / riS) * Real.sqrt (p.val k)) =
     ∑ k : Fin 32, (1 / 32 * Real.sqrt (p.val k) +
       (riFrameW i / riS) * (riFrameW k * Real.sqrt (p.val k))) := by
       apply Finset.sum_congr rfl
       intro k _
       ring
   _ = riFrameA p + riFrameB p * riFrameW i := by
       rw [Finset.sum_add_distrib, ← Finset.mul_sum, ← Finset.mul_sum]
       dsimp [riFrameA, riFrameB]
       ring

theorem riFrameDen_eq (p : Simplex32) : riFrameDen p = riAmplitudeDen p := by
 simp only [riAmplitudeDen, riAmplitude_frame_formula]
 calc
   riFrameDen p = (∑ i : Fin 32, (riFrameA p)^2) +
     (2 * riFrameA p * riFrameB p) * (∑ i : Fin 32, riFrameW i) +
     (riFrameB p)^2 * (∑ i : Fin 32, (riFrameW i)^2) := by
       simp [riFrameDen, riFrameW_centered, riFrameW_norm]
       ring
   _ = ∑ i : Fin 32, (riFrameA p + riFrameB p * riFrameW i)^2 := by
       rw [Finset.mul_sum, Finset.mul_sum, ← Finset.sum_add_distrib,
         ← Finset.sum_add_distrib]
       apply Finset.sum_congr rfl
       intro i _
       ring

theorem riFrameDen_positive (p : Simplex32) : 0 < riFrameDen p := by
 rw [riFrameDen_eq]
 exact riAmplitudeDen_positive p

noncomputable def riCoordinateDensity (p : Simplex32) : M2 :=
 (riFrameDen p)⁻¹ •
   !![32 * (riFrameA p)^2, riS * riFrameA p * riFrameB p;
      32 * riFrameA p * riFrameB p, riS * (riFrameB p)^2]

noncomputable def riParentCoordinate (i : Fin 32) : M2 :=
 !![1 / 32, riFrameW i / 32;
    riFrameW i / riS, (riFrameW i)^2 / riS]

noncomputable def riCoordinateEffect {m : ℕ} (q : Fin 32 → Fin m) (j : Fin m) : M2 :=
 ∑ i : Fin 32, if q i = j then riParentCoordinate i else 0

theorem riParentCoordinate_metric (i : Fin 32) :
 frameG 32 riS * riParentCoordinate i =
   Matrix.vecMulVec ![1, riFrameW i] ![1, riFrameW i] := by
 have hs : riS ≠ 0 := ri_s_positive.ne'
 ext a b
 fin_cases a <;> fin_cases b <;>
   simp [frameG, riParentCoordinate, Matrix.vecMulVec, mul_apply,
     Fin.sum_univ_two, pow_two] <;> field_simp

theorem riParentCoordinate_positive (i : Fin 32) : GPositive 32 riS (riParentCoordinate i) := by
 rw [GPositive, riParentCoordinate_metric]
 simpa only [star_trivial] using
   Matrix.posSemidef_vecMulVec_self_star (![1, riFrameW i] : Fin 2 → ℝ)

theorem riParentCoordinate_sum : (∑ i : Fin 32, riParentCoordinate i) = 1 := by
 have hs : riS ≠ 0 := ri_s_positive.ne'
 ext a b
 fin_cases a <;> fin_cases b <;>
   simp [Matrix.sum_apply, riParentCoordinate, ← Finset.sum_div,
     riFrameW_centered, riFrameW_norm, hs]

theorem riCoordinateEffect_positive {m : ℕ} (q : Fin 32 → Fin m) (j : Fin m) :
 GPositive 32 riS (riCoordinateEffect q j) := by
 unfold GPositive riCoordinateEffect
 rw [Matrix.mul_sum]
 apply Matrix.posSemidef_sum Finset.univ
 intro i _
 split_ifs
 · exact riParentCoordinate_positive i
 · simpa using (Matrix.PosSemidef.zero : (0 : M2).PosSemidef)

theorem riCoordinateEffect_domain {m : ℕ} (q : Fin 32 → Fin m) (j : Fin m) :
 GIsEffect 32 riS (riCoordinateEffect q j) := by
 refine ⟨riCoordinateEffect_positive q j, ?_⟩
 have hc : 1 - riCoordinateEffect q j =
   ∑ i : Fin 32, if q i = j then 0 else riParentCoordinate i := by
   rw [← riParentCoordinate_sum]
   simp only [riCoordinateEffect, ← Finset.sum_sub_distrib]
   apply Finset.sum_congr rfl
   intro i _
   split_ifs <;> simp
 rw [hc]
 unfold GPositive
 rw [Matrix.mul_sum]
 apply Matrix.posSemidef_sum Finset.univ
 intro i _
 split_ifs
 · simpa using (Matrix.PosSemidef.zero : (0 : M2).PosSemidef)
 · exact riParentCoordinate_positive i

theorem riCoordinateEffect_sum {m : ℕ} (q : Fin 32 → Fin m) :
 (∑ j : Fin m, riCoordinateEffect q j) = 1 := by
 classical
 unfold riCoordinateEffect
 rw [Finset.sum_comm]
 simpa [eq_comm] using riParentCoordinate_sum

theorem riCoordinateDensity_metric (p : Simplex32) :
 frameG 32 riS * riCoordinateDensity p =
   (riFrameDen p)⁻¹ • Matrix.vecMulVec
     ![32 * riFrameA p, riS * riFrameB p]
     ![32 * riFrameA p, riS * riFrameB p] := by
 ext a b
 fin_cases a <;> fin_cases b <;>
   simp [frameG, riCoordinateDensity, Matrix.vecMulVec, mul_apply,
     Fin.sum_univ_two, pow_two] <;> ring

theorem riCoordinateDensity_domain (p : Simplex32) :
 GIsDensity 32 riS (riCoordinateDensity p) := by
 refine ⟨?_, ?_⟩
 · rw [GPositive, riCoordinateDensity_metric]
   have hp := Matrix.posSemidef_vecMulVec_self_star
     (![32 * riFrameA p, riS * riFrameB p] : Fin 2 → ℝ)
   simpa only [star_trivial] using hp.smul (inv_nonneg.mpr (riFrameDen_positive p).le)
 · have ht : trace (riCoordinateDensity p) = (riFrameDen p)⁻¹ * riFrameDen p := by
     simp [riCoordinateDensity, trace, Fin.sum_univ_two, riFrameDen]
     ring
   rw [ht]
   exact inv_mul_cancel₀ (riFrameDen_positive p).ne'

theorem riParentCoordinate_pairing (p : Simplex32) (i : Fin 32) :
 pairing (riCoordinateDensity p) (riParentCoordinate i) =
   (riFrameA p + riFrameB p * riFrameW i)^2 / riFrameDen p := by
 have hs := ri_s_positive.ne'
 have hd := (riFrameDen_positive p).ne'
 simp [pairing, riCoordinateDensity, riParentCoordinate, trace, Fin.sum_univ_two]
 field_simp

/-- The explicit 2x2 G-coordinate construction has exactly the micro-space
readout for every simplex input and every finite lens in the embedded context. -/
theorem ri_coordinate_trace_readout {m : ℕ} (q : Fin 32 → Fin m) (j : Fin m)
 (p : Simplex32) :
 pairing (riCoordinateDensity p) (riCoordinateEffect q j) = riLensReadout q j p := by
 simp only [riCoordinateEffect, pairing, Matrix.mul_sum, Matrix.trace_sum,
   riLensReadout, Finset.sum_div, riAmplitude_frame_formula, ← riFrameDen_eq]
 apply Finset.sum_congr rfl
 intro i _
 by_cases hi : q i = j
 · simp only [hi, if_pos]
   exact riParentCoordinate_pairing p i
 · simp [hi]

theorem ri_coordinate_micro_pairing {m : ℕ} (q : Fin 32 → Fin m) (j : Fin m)
 (p : Simplex32) :
 pairing (riCoordinateDensity p) (riCoordinateEffect q j) =
   trace (riUpperDensity p * riLensEffect q j) := by
 rw [ri_coordinate_trace_readout, ri_lens_trace_readout]

theorem riCoordinateEffect_coefficients {m : ℕ} (q : Fin 32 → Fin m) (j : Fin m) :
 riCoordinateEffect q j =
   !![(∑ i : Fin 32, if q i = j then (1 : ℝ) else 0) / 32,
      (∑ i : Fin 32, if q i = j then riFrameW i else 0) / 32;
      (∑ i : Fin 32, if q i = j then riFrameW i else 0) / riS,
      (∑ i : Fin 32, if q i = j then (riFrameW i)^2 else 0) / riS] := by
 have hc (d : ℝ) (f : Fin 32 → ℝ) :
   (∑ i : Fin 32, if q i = j then f i / d else 0) =
     (∑ i : Fin 32, if q i = j then f i else 0) / d := by
   rw [Finset.sum_div]
   apply Finset.sum_congr rfl
   intro i _
   split_ifs <;> simp
 ext a b
 fin_cases a <;> fin_cases b <;>
   simp only [riCoordinateEffect, Matrix.sum_apply, Matrix.ite_apply,
     riParentCoordinate, Matrix.zero_apply] <;> exact hc _ _

theorem riFrameA_positive (p : Simplex32) : 0 < riFrameA p := by
 have hp : 0 < ∑ i : Fin 32, p.val i := by rw [p.property.2]; norm_num
 obtain ⟨i, _, hi⟩ :=
   (Finset.sum_pos_iff_of_nonneg (fun i _ => p.property.1 i)).mp hp
 have hr : 0 < ∑ k : Fin 32, Real.sqrt (p.val k) :=
   (Finset.sum_pos_iff_of_nonneg (fun k _ => Real.sqrt_nonneg _)).mpr
     ⟨i, Finset.mem_univ i, Real.sqrt_pos.mpr hi⟩
 exact div_pos hr (by norm_num)

noncomputable def riFrameLambda (p : Simplex32) : ℝ := riFrameB p / riFrameA p

/-- This is the exact chart used by the Python encoded-source interpreter. -/
theorem riFrameLambda_formula (p : Simplex32) :
 riFrameLambda p = (32 / riS) *
   (∑ i : Fin 32, riFrameW i * Real.sqrt (p.val i)) /
   (∑ i : Fin 32, Real.sqrt (p.val i)) := by
 simp [riFrameLambda, riFrameA, riFrameB, div_eq_mul_inv]
 ring

/-- The common square root can be cancelled before numerical evaluation.
When the relative roots are rational, this gives the exact rational chart
used by the executable uniform/point-source controls. -/
theorem riFrameLambda_ratio (p : Simplex32) (j : Fin 32) (hj : 0 < p.val j) :
 riFrameLambda p = (32 / riS) *
   (∑ i : Fin 32, riFrameW i * Real.sqrt (p.val i / p.val j)) /
   (∑ i : Fin 32, Real.sqrt (p.val i / p.val j)) := by
 have hc : Real.sqrt (p.val j) ≠ 0 := (Real.sqrt_pos.mpr hj).ne'
 have hr (i : Fin 32) :
   Real.sqrt (p.val i) = Real.sqrt (p.val j) * Real.sqrt (p.val i / p.val j) := by
   rw [← Real.sqrt_mul hj.le, mul_div_cancel₀ _ hj.ne']
 have hn : (∑ i : Fin 32, Real.sqrt (p.val i)) =
   Real.sqrt (p.val j) * (∑ i : Fin 32, Real.sqrt (p.val i / p.val j)) := by
   rw [Finset.mul_sum]
   exact Finset.sum_congr rfl (fun i _ => hr i)
 have ht : (∑ i : Fin 32, riFrameW i * Real.sqrt (p.val i)) =
   Real.sqrt (p.val j) * (∑ i : Fin 32, riFrameW i * Real.sqrt (p.val i / p.val j)) := by
   rw [Finset.mul_sum]
   apply Finset.sum_congr rfl
   intro i _
   rw [hr i]
   ring
 rw [riFrameLambda_formula, hn, ht]
 field_simp

theorem riCoordinateDensity_chart (p : Simplex32) :
 riCoordinateDensity p =
   (32 + riS * (riFrameLambda p)^2)⁻¹ •
     !![32, riS * riFrameLambda p;
        32 * riFrameLambda p, riS * (riFrameLambda p)^2] := by
 have ha := (riFrameA_positive p).ne'
 have hd := (riFrameDen_positive p).ne'
 have hz : (32 : ℝ) + riS * (riFrameLambda p)^2 ≠ 0 := by
   have hp : 0 < (32 : ℝ) + riS * (riFrameLambda p)^2 :=
     add_pos_of_pos_of_nonneg (by norm_num) (mul_nonneg ri_s_positive.le (sq_nonneg _))
   exact hp.ne'
 ext a b
 fin_cases a <;> fin_cases b <;>
   simp [riCoordinateDensity, riFrameLambda, riFrameDen] <;>
   field_simp

theorem ri_all_lens_coordinate_readouts (p : Simplex32) :
 (∀ j : Fin 2, pairing (riCoordinateDensity p) (riCoordinateEffect riRaw j) = riLensReadout riRaw j p) ∧
 (∀ j : Fin 3, pairing (riCoordinateDensity p) (riCoordinateEffect riPackage j) = riLensReadout riPackage j p) ∧
 (∀ j : Fin 3, pairing (riCoordinateDensity p) (riCoordinateEffect riJoint j) = riLensReadout riJoint j p) :=
 ⟨fun j => ri_coordinate_trace_readout riRaw j p,
   fun j => ri_coordinate_trace_readout riPackage j p,
   fun j => ri_coordinate_trace_readout riJoint j p⟩

theorem ri_coordinate_readouts_sum {m : ℕ} (q : Fin 32 → Fin m) (p : Simplex32) :
 (∑ j : Fin m, pairing (riCoordinateDensity p) (riCoordinateEffect q j)) = 1 := by
 simp only [pairing]
 rw [← Matrix.trace_sum, ← Matrix.mul_sum, riCoordinateEffect_sum, Matrix.mul_one]
 exact (riCoordinateDensity_domain p).2

theorem ri_coordinate_readout_bounds {m : ℕ} (q : Fin 32 → Fin m) (j : Fin m)
 (p : Simplex32) :
 0 ≤ pairing (riCoordinateDensity p) (riCoordinateEffect q j) ∧
   pairing (riCoordinateDensity p) (riCoordinateEffect q j) ≤ 1 := by
 rw [ri_coordinate_trace_readout]
 have hn : 0 ≤ ∑ i : Fin 32, if q i = j then (riAmplitude p i)^2 else 0 := by
   apply Finset.sum_nonneg
   intro i _
   split_ifs
   · exact sq_nonneg _
   · exact le_rfl
 have hb : (∑ i : Fin 32, if q i = j then (riAmplitude p i)^2 else 0) ≤
   riAmplitudeDen p := by
   apply Finset.sum_le_sum
   intro i _
   split_ifs
   · exact le_rfl
   · exact sq_nonneg _
 exact ⟨div_nonneg hn (riAmplitudeDen_positive p).le,
   (div_le_one (riAmplitudeDen_positive p)).mpr hb⟩

noncomputable def riFrameBasis : Matrix (Fin 32) (Fin 2) ℝ :=
 fun i => ![1, riFrameW i]

theorem riFrameBasis_gram : riFrameBasisᵀ * riFrameBasis = frameG 32 riS := by
 have hn : (∑ i : Fin 32, riFrameW i * riFrameW i) = riS :=
   by simpa only [pow_two] using riFrameW_norm
 ext a b
 fin_cases a <;> fin_cases b <;>
   simp [riFrameBasis, frameG, mul_apply, transpose_apply, riFrameW_centered, hn]

/-- This identifies the 2x2 basis with the actual retained micro-space
projector, rather than just matching one scalar probability. -/
theorem riFrameBasis_projection :
 riFrameBasis * Matrix.diagonal ![(1 / 32 : ℝ), riS⁻¹] * riFrameBasisᵀ = riP := by
 ext i j
 simp [riFrameBasis, mul_apply, Fin.sum_univ_two, transpose_apply, riP_frame_formula]
 ring

end BornCalculus
