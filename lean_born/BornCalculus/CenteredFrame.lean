import BornCalculus.RootChart
import BornCalculus.SmallMatrices

namespace BornCalculus
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0

/-- Rank-two centered frame on the retained 32-state carrier. No native
formation, history reconstruction, or acquisition assumption is included. -/
structure CenteredFrame32 where
 w : Fin 32 → ℝ
 s : ℝ
 positive : 0 < s
 centered : (∑ i, w i) = 0
 squared : (∑ i, (w i)^2) = s

noncomputable def frameParent (F : CenteredFrame32) (i : Fin 32) : M2 :=
 !![1/32,F.w i/32;F.w i/F.s,(F.w i)^2/F.s]
noncomputable def frameLens {m : ℕ} (F : CenteredFrame32) (q : Fin 32 → Fin m) (j : Fin m) : M2 :=
 ∑ i, if q i = j then frameParent F i else 0
noncomputable def frameEncoding (F : CenteredFrame32) (p : Simplex32) : M2 :=
 chartDensity F.s (rootChart F.w F.s p.val)
noncomputable def framePointChart (F : CenteredFrame32) (i : Fin 32) : ℝ := (32/F.s)*F.w i
noncomputable def framePointRead {m : ℕ} (F : CenteredFrame32) (q : Fin 32 → Fin m) (j : Fin m)
 (i : Fin 32) : ℝ := pairing (chartDensity F.s (framePointChart F i)) (frameLens F q j)

noncomputable def simplexPoint (i : Fin 32) : Simplex32 :=
 ⟨fun k => if k = i then 1 else 0,⟨fun k => by
   change (0:ℝ) ≤ if k = i then 1 else 0
   split_ifs <;> norm_num,by simp⟩⟩

def frameRecord {m : ℕ} (q : Fin 32 → Fin m) (p : Simplex32) (j : Fin m) : ℝ :=
 ∑ i, if q i = j then p.val i else 0
noncomputable def frameOldView {m : ℕ} (q : Fin 3 → Fin 32 → Fin m) (p : Simplex32) : Fin 3 → Fin m → ℝ :=
 fun f j => frameRecord (q f) p j

theorem frame_parent_metric (F : CenteredFrame32) (i : Fin 32) :
 frameG 32 F.s * frameParent F i = vecMulVec ![1,F.w i] ![1,F.w i] := by
 ext a b
 fin_cases a <;> fin_cases b <;>
   simp [frameG,frameParent,vecMulVec,mul_apply,Fin.sum_univ_two] <;> field_simp [F.positive.ne']

theorem frame_parent_positive (F : CenteredFrame32) (i : Fin 32) : GPositive 32 F.s (frameParent F i) := by
 rw [GPositive,frame_parent_metric]
 simpa only [star_trivial] using posSemidef_vecMulVec_self_star (![1,F.w i] : Fin 2 → ℝ)

theorem frame_parent_sum (F : CenteredFrame32) : (∑ i, frameParent F i) = 1 := by
 ext a b
 fin_cases a <;> fin_cases b <;>
   norm_num [frameParent,Matrix.sum_apply,←Finset.sum_div,F.centered,F.squared,F.positive.ne']

theorem frame_lens_positive {m : ℕ} (F : CenteredFrame32) (q : Fin 32 → Fin m) (j : Fin m) :
 GPositive 32 F.s (frameLens F q j) := by
 unfold GPositive frameLens
 rw [Matrix.mul_sum]
 apply Matrix.posSemidef_sum Finset.univ
 intro i _
 by_cases h : q i = j
 · simpa only [if_pos h] using frame_parent_positive F i
 · simp only [if_neg h,Matrix.mul_zero]
   exact Matrix.PosSemidef.zero

theorem frame_lens_sum {m : ℕ} (F : CenteredFrame32) (q : Fin 32 → Fin m) :
 (∑ j, frameLens F q j) = 1 := by
 classical
 unfold frameLens
 rw [Finset.sum_comm]
 simpa [eq_comm] using frame_parent_sum F

theorem frame_lens_domain {m : ℕ} (F : CenteredFrame32) (q : Fin 32 → Fin m) (j : Fin m) :
 GIsEffect 32 F.s (frameLens F q j) :=
 complete_g_effect_domains 32 F.s (frameLens F q) (frame_lens_positive F q) (frame_lens_sum F q) j

theorem frame_encoding_domain (F : CenteredFrame32) (p : Simplex32) :
 GIsDensity 32 F.s (frameEncoding F p) := chartDensity_domain F.s _ F.positive

theorem frame_point_chart (F : CenteredFrame32) (i : Fin 32) :
 rootChart F.w F.s (simplexPoint i).val = framePointChart F i := by
 classical
 have hr (k : Fin 32) : Real.sqrt (if k = i then (1:ℝ) else 0) = if k = i then 1 else 0 := by
   split_ifs <;> norm_num
 change (32/F.s)*(∑ k : Fin 32, F.w k*Real.sqrt (if k = i then 1 else 0))/
   (∑ k : Fin 32, Real.sqrt (if k = i then 1 else 0)) = framePointChart F i
 simp_rw [hr]
 simp [framePointChart]

theorem frame_point_encoding (F : CenteredFrame32) (i : Fin 32) :
 frameEncoding F (simplexPoint i) = chartDensity F.s (framePointChart F i) := by
 rw [frameEncoding,frame_point_chart]

theorem frame_parent_pairing (F : CenteredFrame32) (t : ℝ) (i : Fin 32) :
 pairing (chartDensity F.s t) (frameParent F i) = (1+t*F.w i)^2/(32+F.s*t^2) := by
 have hd : (32:ℝ)+F.s*t^2 ≠ 0 :=
   (add_pos_of_pos_of_nonneg (by norm_num) (mul_nonneg F.positive.le (sq_nonneg t))).ne'
 simp [pairing,chartDensity,frameParent,trace,Fin.sum_univ_two]
 field_simp [F.positive.ne',hd]

theorem frame_lens_pairing {m : ℕ} (F : CenteredFrame32) (q : Fin 32 → Fin m) (j : Fin m) (t : ℝ) :
 pairing (chartDensity F.s t) (frameLens F q j) =
 ∑ i, if q i = j then (1+t*F.w i)^2/(32+F.s*t^2) else 0 := by
 unfold pairing frameLens
 rw [Matrix.mul_sum,Matrix.trace_sum]
 apply Finset.sum_congr rfl
 intro i _
 by_cases h : q i = j
 · simpa only [if_pos h] using frame_parent_pairing F t i
 · simp [h]

theorem frame_record_point {m : ℕ} (q : Fin 32 → Fin m) (i : Fin 32) (j : Fin m) :
 frameRecord q (simplexPoint i) j = if q i = j then 1 else 0 := by
 classical
 unfold frameRecord simplexPoint
 rw [Finset.sum_eq_single i]
 · simp
 · intro k _ hki
   simp [hki]
 · simp

theorem frame_old_points_equal {m : ℕ} (q : Fin 3 → Fin 32 → Fin m) (i j : Fin 32)
 (hq : ∀ f, q f i = q f j) : frameOldView q (simplexPoint i) = frameOldView q (simplexPoint j) := by
 funext f k
 simp only [frameOldView,frame_record_point,hq f]

theorem frame_points_density_ne (F : CenteredFrame32) (i j : Fin 32) (hw : F.w i ≠ F.w j) :
 frameEncoding F (simplexPoint i) ≠ frameEncoding F (simplexPoint j) := by
 rw [frame_point_encoding,frame_point_encoding]
 intro he
 have ht := chartDensity_injective F.s F.positive he
 have hc : (32/F.s : ℝ) ≠ 0 := div_ne_zero (by norm_num) F.positive.ne'
 exact hw (mul_left_cancel₀ hc ht)

/-- Equal anonymous initial record laws do not determine the selected readout.
All other public fields may be any fixed record; this is not a history claim. -/
theorem frame_initial_no_factor {m : ℕ} {β : Type*} (fixed : β) (F : CenteredFrame32)
 (q : Fin 3 → Fin 32 → Fin m) (i j : Fin 32) (f : Fin 3) (a : Fin m)
 (hq : ∀ l, q l i = q l j) (hr : framePointRead F (q f) a i ≠ framePointRead F (q f) a j) :
 ¬ ∃ g : β × (Fin 3 → Fin m → ℝ) → ℝ, ∀ p : Simplex32,
   pairing (frameEncoding F p) (frameLens F (q f) a) = g (fixed,frameOldView q p) := by
 apply fiber_split_no_factor (fun p : Simplex32 => (fixed,frameOldView q p))
   (fun p : Simplex32 => pairing (frameEncoding F p) (frameLens F (q f) a))
   (simplexPoint i) (simplexPoint j)
 · rw [frame_old_points_equal q i j hq]
 · simpa only [frame_point_encoding,framePointRead] using hr


theorem frame_sqrt_sum_positive (p : Simplex32) : 0 < ∑ i, Real.sqrt (p.val i) := by
 classical
 have hi : ∃ i : Fin 32, 0 < p.val i := by
   by_contra h
   push_neg at h
   have hz := Finset.sum_nonpos (fun i (_ : i ∈ Finset.univ) => h i)
   rw [p.property.2] at hz
   norm_num at hz
 obtain ⟨i,hi⟩ := hi
 exact Finset.sum_pos' (fun k _ => Real.sqrt_nonneg _) ⟨i,Finset.mem_univ i,Real.sqrt_pos.mpr hi⟩

theorem frame_old_points_equal_iff {m : ℕ} (q : Fin 3 → Fin 32 → Fin m) (i j : Fin 32) :
 frameOldView q (simplexPoint i) = frameOldView q (simplexPoint j) ↔ ∀ f, q f i = q f j := by
 constructor
 · intro he f
   have h := congrArg (fun v : Fin 3 → Fin m → ℝ => v f (q f i)) he
   by_contra hn
   simp [frameOldView,frame_record_point,Ne.symm hn] at h
 · exact frame_old_points_equal q i j

theorem frame_points_density_eq (F : CenteredFrame32) (i j : Fin 32) (hw : F.w i = F.w j) :
 frameEncoding F (simplexPoint i) = frameEncoding F (simplexPoint j) := by
 rw [frame_point_encoding,frame_point_encoding]
 simp only [framePointChart,hw]

end BornCalculus
