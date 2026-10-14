import BornCalculus.RICoordinates

namespace BornCalculus
open scoped BigOperators
set_option maxHeartbeats 0

noncomputable def rootChart (w : Fin 32 → ℝ) (s : ℝ) (p : Fin 32 → ℝ) : ℝ :=
 (32/s) * (∑ i, w i * Real.sqrt (p i)) / (∑ i, Real.sqrt (p i))

noncomputable def lowerLinearRoot (a lo hi : Fin 32 → ℝ) (i : Fin 32) : ℝ :=
 if 0 ≤ a i then a i * lo i else a i * hi i

theorem sqrt_bounds_of_squared_bounds (p lo hi : ℝ)
 (hl : 0 ≤ lo) (hu : 0 ≤ hi) (hlo : lo^2 ≤ p) (hhi : p ≤ hi^2) :
 lo ≤ Real.sqrt p ∧ Real.sqrt p ≤ hi := by
 have hp : 0 ≤ p := (sq_nonneg lo).trans hlo
 have hs : (Real.sqrt p)^2 = p := Real.sq_sqrt hp
 exact ⟨(sq_le_sq₀ hl (Real.sqrt_nonneg p)).mp (by rw [hs]; exact hlo),
   (sq_le_sq₀ (Real.sqrt_nonneg p) hu).mp (by rw [hs]; exact hhi)⟩

theorem lower_linear_root_sum (a p lo hi : Fin 32 → ℝ)
 (hb : ∀ i, lo i ≤ Real.sqrt (p i) ∧ Real.sqrt (p i) ≤ hi i) :
 (∑ i, lowerLinearRoot a lo hi i) ≤ ∑ i, a i * Real.sqrt (p i) := by
 apply Finset.sum_le_sum
 intro i _
 by_cases ha : 0 ≤ a i
 · simpa only [lowerLinearRoot, if_pos ha] using mul_le_mul_of_nonneg_left (hb i).1 ha
 · simpa only [lowerLinearRoot, if_neg ha] using
     mul_le_mul_of_nonpos_left (hb i).2 (le_of_not_ge ha)

/-- Exact rational checks of the scalar-root squares and two signed linear
forms certify a chart enclosure. No floating-point evaluation is a premise. -/
theorem rootChart_bounds (w p lo hi : Fin 32 → ℝ) (s L U : ℝ)
 (hb : ∀ i, 0 ≤ lo i ∧ 0 ≤ hi i ∧ (lo i)^2 ≤ p i ∧ p i ≤ (hi i)^2)
 (hpos : 0 < ∑ i, lo i)
 (hl : 0 ≤ ∑ i, lowerLinearRoot (fun i => (32/s)*w i-L) lo hi i)
 (hu : 0 ≤ ∑ i, lowerLinearRoot (fun i => U-(32/s)*w i) lo hi i) :
 L ≤ rootChart w s p ∧ rootChart w s p ≤ U := by
 have hroots : ∀ i, lo i ≤ Real.sqrt (p i) ∧ Real.sqrt (p i) ≤ hi i := by
   intro i
   exact sqrt_bounds_of_squared_bounds _ _ _ (hb i).1 (hb i).2.1 (hb i).2.2.1 (hb i).2.2.2
 have hs : 0 < ∑ i, Real.sqrt (p i) := hpos.trans_le
   (Finset.sum_le_sum (fun i _ => (hroots i).1))
 have hleft := hl.trans (lower_linear_root_sum (fun i => (32/s)*w i-L) p lo hi hroots)
 have hright := hu.trans (lower_linear_root_sum (fun i => U-(32/s)*w i) p lo hi hroots)
 simp only [sub_mul, Finset.sum_sub_distrib, ← Finset.mul_sum] at hleft hright
 simp_rw [mul_assoc] at hleft hright
 rw [← Finset.mul_sum] at hleft hright
 constructor
 · exact (le_div_iff₀ hs).mpr (by linarith)
 · exact (div_le_iff₀ hs).mpr (by linarith)

theorem rootChart_of_relative_roots (w r p : Fin 32 → ℝ) (s pivot : ℝ)
 (hp : 0 < pivot) (hr : ∀ i, 0 ≤ r i ∧ (r i)^2 = p i/pivot)
 (hs : 0 < ∑ i, r i) :
 rootChart w s p = (32/s) * (∑ i, w i * r i) / (∑ i, r i) := by
 have hc : Real.sqrt pivot ≠ 0 := (Real.sqrt_pos.mpr hp).ne'
 have hroot (i : Fin 32) : Real.sqrt (p i) = Real.sqrt pivot * r i := by
   have hpi : 0 ≤ p i := by
     have h := sq_nonneg (r i)
     rw [(hr i).2] at h
     have hn := mul_nonneg h hp.le
     simpa only [div_mul_cancel₀ _ hp.ne'] using hn
   have he : pivot * (p i/pivot) = p i := by field_simp
   calc
     Real.sqrt (p i) = Real.sqrt pivot * Real.sqrt (p i/pivot) := by rw [← Real.sqrt_mul hp.le, he]
     _ = Real.sqrt pivot * r i := by rw [← (hr i).2, Real.sqrt_sq (hr i).1]
 have hsum : (∑ i, Real.sqrt (p i)) = Real.sqrt pivot * (∑ i, r i) := by
   rw [Finset.mul_sum]
   exact Finset.sum_congr rfl (fun i _ => hroot i)
 have hweighted : (∑ i, w i * Real.sqrt (p i)) = Real.sqrt pivot * (∑ i, w i*r i) := by
   rw [Finset.mul_sum]
   apply Finset.sum_congr rfl
   intro i _
   rw [hroot i]
   ring
 rw [rootChart, hsum, hweighted]
 field_simp

theorem fiber_split_no_factor {α β γ : Type*} (view : α → β) (read : α → γ)
 (p q : α) (he : view p = view q) (hs : read p ≠ read q) :
 ¬ ∃ f : β → γ, ∀ x, read x = f (view x) := by
 rintro ⟨f,hf⟩
 exact hs ((hf p).trans ((congrArg f he).trans (hf q).symm))

open Matrix
noncomputable def chartDensity (s t : ℝ) : M2 :=
 (32+s*t^2)⁻¹ • !![32,s*t;32*t,s*t^2]
theorem chartDensity_recover (s t : ℝ) (hs : 0 < s) :
 (chartDensity s t) 1 0 / (chartDensity s t) 0 0 = t := by
 have hd : (32:ℝ)+s*t^2 ≠ 0 := (add_pos_of_pos_of_nonneg (by norm_num) (mul_nonneg hs.le (sq_nonneg t))).ne'
 simp [chartDensity]
 field_simp
theorem chartDensity_injective (s : ℝ) (hs : 0 < s) : Function.Injective (chartDensity s) := by
 intro a b he
 have h := congrArg (fun R : M2 => R 1 0 / R 0 0) he
 simpa only [chartDensity_recover s a hs,chartDensity_recover s b hs] using h


theorem chartDensity_metric (s t : ℝ) :
 frameG 32 s * chartDensity s t =
   (32+s*t^2)⁻¹ • Matrix.vecMulVec ![32,s*t] ![32,s*t] := by
 ext a b
 fin_cases a <;> fin_cases b <;>
   simp [frameG,chartDensity,Matrix.vecMulVec,mul_apply,Fin.sum_univ_two,pow_two] <;> ring

theorem chartDensity_domain (s t : ℝ) (hs : 0 < s) :
 GIsDensity 32 s (chartDensity s t) := by
 have hd : 0 < (32:ℝ)+s*t^2 :=
   add_pos_of_pos_of_nonneg (by norm_num) (mul_nonneg hs.le (sq_nonneg t))
 refine ⟨?_,?_⟩
 · rw [GPositive,chartDensity_metric]
   have hp := Matrix.posSemidef_vecMulVec_self_star (![32,s*t] : Fin 2 → ℝ)
   simpa only [star_trivial] using hp.smul (inv_nonneg.mpr hd.le)
 · have ht : trace (chartDensity s t) = (32+s*t^2)⁻¹ * (32+s*t^2) := by
     simp [chartDensity,trace,Fin.sum_univ_two]
     ring
   rw [ht]
   exact inv_mul_cancel₀ hd.ne'

end BornCalculus
