import BornCalculus.CenteredFrame

namespace BornCalculus
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0

/-- Distinct points of the existing pure chart have a full-rank proper mixture. -/
theorem chartDensity_mixture_det (s a b θ : ℝ) (hs : 0 < s) :
 (θ • chartDensity s a + (1-θ) • chartDensity s b).det =
 θ*(1-θ)*32*s*(a-b)^2 / ((32+s*a^2)*(32+s*b^2)) := by
 have ha : (32:ℝ)+s*a^2 ≠ 0 := (by positivity : 0 < (32:ℝ)+s*a^2).ne'
 have hb : (32:ℝ)+s*b^2 ≠ 0 := (by positivity : 0 < (32:ℝ)+s*b^2).ne'
 simp [chartDensity, Matrix.det_fin_two]
 field_simp
; ring

theorem chartDensity_det_zero (s t : ℝ) : (chartDensity s t).det = 0 := by
 simp [chartDensity, Matrix.det_fin_two]
 ring

theorem chartDensity_ne_proper_mixture (s a b c θ : ℝ) (hs : 0 < s)
 (hab : a ≠ b) (hθ : 0 < θ) (hθ' : θ < 1) :
 chartDensity s c ≠ θ • chartDensity s a + (1-θ) • chartDensity s b := by
 intro he
 have hd := congrArg Matrix.det he
 rw [chartDensity_det_zero, chartDensity_mixture_det s a b θ hs] at hd
 have hp : 0 < θ*(1-θ)*32*s*(a-b)^2 / ((32+s*a^2)*(32+s*b^2)) := by
   have : 0 < (a-b)^2 := sq_pos_of_ne_zero (sub_ne_zero.mpr hab)
   have hsub : 0 < 1-θ := sub_pos.mpr hθ'
   positivity
 linarith

/-- Stronger than the preparation-mixture assertion: no encoded preparation
can equal a proper mixture of two distinct encoded states. -/
theorem frameEncoding_nonaffine (F : CenteredFrame32) (p q r : Simplex32)
 (hne : frameEncoding F p ≠ frameEncoding F q) (θ : ℝ)
 (hθ : 0 < θ) (hθ' : θ < 1) :
 frameEncoding F r ≠ θ • frameEncoding F p + (1-θ) • frameEncoding F q := by
 apply chartDensity_ne_proper_mixture F.s _ _ _ θ F.positive _ hθ hθ'
 intro he
 apply hne
 simp only [frameEncoding, he]

/-- The orthogonal pure state is absent from every finite chart. -/
theorem chartDensity_ne_orthogonal (s t : ℝ) (hs : 0 < s) :
 chartDensity s t ≠ (!![0,0;0,1] : M2) := by
 intro he
 have h := congrArg (fun A : M2 => A 0 0) he
 have hd : 0 < (32:ℝ)+s*t^2 := by positivity
 have hp : 0 < chartDensity s t 0 0 := by
   simp only [chartDensity, Matrix.smul_apply, smul_eq_mul]
   change 0 < (32+s*t^2)⁻¹ * 32
   positivity
 have hz : chartDensity s t 0 0 = 0 := by simpa using h
 linarith

/-- Squaring and normalizing realizes every probability vector as normalized
square-root weights. This scalar statement has arbitrary finite dimension. -/
theorem normalized_sqrt_weights_surjective {α : Type*} [Fintype α]
 (q : α → ℝ) (hq : ∀ i, 0 ≤ q i) (hqs : ∑ i, q i = 1) :
 ∃ p : α → ℝ, (∀ i, 0 ≤ p i) ∧ (∑ i, p i = 1) ∧
   ∀ i, Real.sqrt (p i) / (∑ j, Real.sqrt (p j)) = q i := by
 classical
 have hex : ∃ i, 0 < q i := by
   by_contra hn
   push_neg at hn
   have h := Finset.sum_nonpos (fun i (_ : i ∈ Finset.univ) => hn i)
   rw [hqs] at h
   norm_num at h
 obtain ⟨i,hpi⟩ := hex
 let D := ∑ j, (q j)^2
 have hD : 0 < D := Finset.sum_pos' (fun j _ => sq_nonneg _) 
   ⟨i, Finset.mem_univ _, sq_pos_of_pos hpi⟩
 let p := fun j => (q j)^2 / D
 have hr (j) : Real.sqrt (p j) = q j / Real.sqrt D := by
   dsimp [p]
   rw [Real.sqrt_div (sq_nonneg _) D, Real.sqrt_sq (hq j)]
 have hs : ∑ j, Real.sqrt (p j) = 1 / Real.sqrt D := by
   simp_rw [hr]
   rw [← Finset.sum_div, hqs]
 refine ⟨p, fun j => div_nonneg (sq_nonneg _) hD.le, ?_, ?_⟩
 · dsimp [p]
   rw [← Finset.sum_div]
   exact div_self hD.ne'
 · intro j
   rw [hr, hs]
   field_simp [(Real.sqrt_pos.mpr hD).ne']

/-- The full scalar image theorem in arbitrary finite dimension. The coefficient
c may be sqrt(n/s), giving exactly the paper's orthonormal chart. -/
theorem finite_sqrt_chart_range {α : Type*} [Fintype α] [DecidableEq α]
 (w : α → ℝ) (c : ℝ) (hc : 0 < c) (lo hi : α)
 (hl : ∀ i, w lo ≤ w i) (hu : ∀ i, w i ≤ w hi) (t : ℝ) :
 (∃ p : {p : α → ℝ // (∀ i, 0 ≤ p i) ∧ ∑ i, p i = 1},
   c * (∑ i, w i * Real.sqrt (p.val i)) / (∑ i, Real.sqrt (p.val i)) = t) ↔
   c*w lo ≤ t ∧ t ≤ c*w hi := by
 classical
 constructor
 · rintro ⟨p, rfl⟩
   have hex : ∃ i, 0 < p.val i := by
     by_contra hn
     push_neg at hn
     have h := Finset.sum_nonpos (fun i (_ : i ∈ Finset.univ) => hn i)
     rw [p.property.2] at h
     norm_num at h
   obtain ⟨i,hpi⟩ := hex
   have hs : 0 < ∑ i, Real.sqrt (p.val i) := Finset.sum_pos' (fun j _ => Real.sqrt_nonneg _)
     ⟨i,Finset.mem_univ i,Real.sqrt_pos.mpr hpi⟩
   have hl' : w lo * (∑ i, Real.sqrt (p.val i)) ≤
       ∑ i, w i * Real.sqrt (p.val i) := by
     rw [Finset.mul_sum]
     exact Finset.sum_le_sum (fun i _ => mul_le_mul_of_nonneg_right (hl i) (Real.sqrt_nonneg _))
   have hu' : (∑ i, w i * Real.sqrt (p.val i)) ≤
       w hi * (∑ i, Real.sqrt (p.val i)) := by
     rw [Finset.mul_sum]
     exact Finset.sum_le_sum (fun i _ => mul_le_mul_of_nonneg_right (hu i) (Real.sqrt_nonneg _))
   constructor
   · apply (le_div_iff₀ hs).mpr
     nlinarith
   · apply (div_le_iff₀ hs).mpr
     nlinarith
 · intro ht
   let x := t / c
   have hx : w lo ≤ x ∧ x ≤ w hi := by
     constructor
     · exact (le_div_iff₀ hc).mpr (by nlinarith [ht.1])
     · exact (div_le_iff₀ hc).mpr (by nlinarith [ht.2])
   by_cases he : w lo = w hi
   · let p : {p : α → ℝ // (∀ i, 0 ≤ p i) ∧ ∑ i, p i = 1} :=
       ⟨fun i => if i = lo then 1 else 0, ⟨fun i => by
         change (0:ℝ) ≤ if i = lo then 1 else 0
         split_ifs <;> norm_num, by simp⟩⟩
     refine ⟨p, ?_⟩
     have ht' : c*w lo = t := by nlinarith [ht.1,ht.2]
     change c*(∑ i, w i * Real.sqrt (if i = lo then 1 else 0)) /
       (∑ i, Real.sqrt (if i = lo then (1:ℝ) else 0)) = t
     have hr (i : α) : Real.sqrt (if i = lo then (1:ℝ) else 0) = if i = lo then 1 else 0 := by
       split_ifs <;> norm_num
     simp_rw [hr]
     simpa using ht'
   have hd : 0 < w hi - w lo := sub_pos.mpr (lt_of_le_of_ne (hl hi) he)
   let a := (w hi-x)/(w hi-w lo)
   have ha : 0 ≤ a := div_nonneg (sub_nonneg.mpr hx.2) hd.le
   have ha' : a ≤ 1 := (div_le_one hd).mpr (by linarith [hx.1])
   let q : α → ℝ := fun i =>
     (if i = lo then a else 0) + (if i = hi then 1-a else 0)
   have hq : ∀ i, 0 ≤ q i := by
     intro i
     dsimp [q]
     split_ifs <;> linarith
   have hqs : ∑ i, q i = 1 := by simp [q, Finset.sum_add_distrib]
   obtain ⟨p, hp, hps, hr⟩ := normalized_sqrt_weights_surjective q hq hqs
   refine ⟨⟨p,hp,hps⟩, ?_⟩
   have hv : (∑ i, w i * Real.sqrt (p i)) / (∑ i, Real.sqrt (p i)) = x := by
     rw [Finset.sum_div]
     simp_rw [mul_div_assoc, hr]
     simp [q, mul_add, Finset.sum_add_distrib]
     dsimp [a]
     field_simp
    ; ring
   change c*(∑ i, w i * Real.sqrt (p i))/(∑ i, Real.sqrt (p i)) = t
   rw [mul_div_assoc, hv]
   dsimp [x]
   field_simp [hc.ne']

/-- Full eta range, expressed using any indices attaining the extrema. -/
theorem frame_rootChart_range (F : CenteredFrame32) (lo hi : Fin 32)
 (hl : ∀ i, F.w lo ≤ F.w i) (hu : ∀ i, F.w i ≤ F.w hi) (t : ℝ) :
 (∃ p : Simplex32, rootChart F.w F.s p.val = t) ↔
   (32/F.s)*F.w lo ≤ t ∧ t ≤ (32/F.s)*F.w hi := by
 exact finite_sqrt_chart_range F.w (32/F.s) (div_pos (by norm_num) F.positive) lo hi hl hu t

theorem frameEncoding_image (F : CenteredFrame32) (lo hi : Fin 32)
 (hl : ∀ i, F.w lo ≤ F.w i) (hu : ∀ i, F.w i ≤ F.w hi) (R : M2) :
 (∃ p : Simplex32, frameEncoding F p = R) ↔
 ∃ t : ℝ, (32/F.s)*F.w lo ≤ t ∧ t ≤ (32/F.s)*F.w hi ∧
   chartDensity F.s t = R := by
 constructor
 · rintro ⟨p, hp⟩
   have ht := (frame_rootChart_range F lo hi hl hu _).mp ⟨p,rfl⟩
   exact ⟨_, ht.1, ht.2, hp⟩
 · rintro ⟨t, ht, ht', hR⟩
   obtain ⟨p,hp⟩ := (frame_rootChart_range F lo hi hl hu t).mpr ⟨ht,ht'⟩
   exact ⟨p, by simpa only [frameEncoding, hp] using hR⟩

theorem chartDensity_pure (s t : ℝ) (hs : 0 < s) :
 chartDensity s t * chartDensity s t = chartDensity s t := by
 have hd : (32:ℝ)+s*t^2 ≠ 0 := (by positivity : 0 < (32:ℝ)+s*t^2).ne'
 ext i j
 fin_cases i <;> fin_cases j <;>
   simp [chartDensity, mul_apply, Fin.sum_univ_two]
   <;> field_simp

theorem frame_extrema_straddle (F : CenteredFrame32) (lo hi : Fin 32)
 (hl : ∀ i, F.w lo ≤ F.w i) (hu : ∀ i, F.w i ≤ F.w hi) :
 F.w lo < 0 ∧ 0 < F.w hi := by
 have hn : ¬ (∀ i, F.w i = 0) := by
   intro hz
   have hs := F.squared
   simp [hz] at hs
   linarith [F.positive]
 constructor
 · by_contra hc
   have hnon : ∀ i, 0 ≤ F.w i := fun i => (le_of_not_gt hc).trans (hl i)
   exact hn (fun i => (Finset.sum_eq_zero_iff_of_nonneg (fun j _ => hnon j)).mp
     F.centered i (Finset.mem_univ i))
 · by_contra hc
   have hnon : ∀ i, 0 ≤ -F.w i := fun i => neg_nonneg.mpr ((hu i).trans (le_of_not_gt hc))
   have hs : (∑ i, -F.w i) = 0 := by rw [Finset.sum_neg_distrib,F.centered,neg_zero]
   apply hn
   intro i
   have hz := (Finset.sum_eq_zero_iff_of_nonneg (fun j _ => hnon j)).mp hs i (Finset.mem_univ i)
   linarith

noncomputable def boundaryUniform : Simplex32 :=
 ⟨fun _ => 1/32, by constructor <;> norm_num⟩

theorem frameEncoding_uniform (F : CenteredFrame32) :
 frameEncoding F boundaryUniform = chartDensity F.s 0 := by
 have hn : (∑ i, F.w i * Real.sqrt (1/32 : ℝ)) = 0 := by
   rw [← Finset.sum_mul, F.centered, zero_mul]
 change chartDensity F.s ((32/F.s)*(∑ i, F.w i * Real.sqrt (1/32 : ℝ)) /
   (∑ _ : Fin 32, Real.sqrt (1/32 : ℝ))) = chartDensity F.s 0
 rw [hn]
 simp

/-- Arbitrary-n version of the paper's chart interval, with its exact
sqrt(n/s) scaling and simplex quantifiers. -/
theorem paper_encoder_chart_range {α : Type*} [Fintype α] [DecidableEq α]
 (w : α → ℝ) (s : ℝ) (hs : 0 < s) (hn : 0 < Fintype.card α) (lo hi : α)
 (hl : ∀ i, w lo ≤ w i) (hu : ∀ i, w i ≤ w hi) (t : ℝ) :
 (∃ p : {p : α → ℝ // (∀ i, 0 ≤ p i) ∧ ∑ i, p i = 1},
   Real.sqrt ((Fintype.card α : ℝ)/s) * (∑ i, w i * Real.sqrt (p.val i)) /
     (∑ i, Real.sqrt (p.val i)) = t) ↔
 Real.sqrt ((Fintype.card α : ℝ)/s)*w lo ≤ t ∧
 t ≤ Real.sqrt ((Fintype.card α : ℝ)/s)*w hi := by
 have hnr : (0:ℝ) < Fintype.card α := by exact_mod_cast hn
 exact finite_sqrt_chart_range w _ (Real.sqrt_pos.mpr (div_pos hnr hs)) lo hi hl hu t

theorem paper_encoder_image {α : Type*} [Fintype α] [DecidableEq α]
 (w : α → ℝ) (s : ℝ) (hs : 0 < s) (hn : 0 < Fintype.card α) (lo hi : α)
 (hl : ∀ i, w lo ≤ w i) (hu : ∀ i, w i ≤ w hi) (R : M2) :
 (∃ p : {p : α → ℝ // (∀ i, 0 ≤ p i) ∧ ∑ i, p i = 1},
   chartDensity 32 (Real.sqrt ((Fintype.card α : ℝ)/s) *
     (∑ i, w i * Real.sqrt (p.val i)) / (∑ i, Real.sqrt (p.val i))) = R) ↔
 ∃ t : ℝ, Real.sqrt ((Fintype.card α : ℝ)/s)*w lo ≤ t ∧
   t ≤ Real.sqrt ((Fintype.card α : ℝ)/s)*w hi ∧ chartDensity 32 t = R := by
 constructor
 · rintro ⟨p,hp⟩
   have ht := (paper_encoder_chart_range w s hs hn lo hi hl hu _).mp ⟨p,rfl⟩
   exact ⟨_,ht.1,ht.2,hp⟩
 · rintro ⟨t,ht,ht',hR⟩
   obtain ⟨p,hp⟩ := (paper_encoder_chart_range w s hs hn lo hi hl hu t).mpr ⟨ht,ht'⟩
   exact ⟨p,by rw [hp]; exact hR⟩

/-- Identify the existing chart with the paper's pure orthonormal density. -/
theorem chartDensity_orthonormal (t : ℝ) :
 chartDensity 32 t = (1+t^2)⁻¹ • (!![1,t;t,t^2] : M2) := by
 have hd : (1:ℝ)+t^2 ≠ 0 := (by positivity : 0 < (1:ℝ)+t^2).ne'
 ext i j
 fin_cases i <;> fin_cases j <;> simp [chartDensity]
   <;> field_simp

/-- Full arbitrary-dimensional non-affinity, retaining the paper's formula
and quantifiers; r may in particular be the preparation mixture. -/
theorem paper_encoder_nonaffine {α : Type*} [Fintype α]
 (w : α → ℝ) (s : ℝ) :
 let enc := fun p : {p : α → ℝ // (∀ i, 0 ≤ p i) ∧ ∑ i, p i = 1} =>
   chartDensity 32 (Real.sqrt ((Fintype.card α : ℝ)/s) *
     (∑ i, w i * Real.sqrt (p.val i)) / (∑ i, Real.sqrt (p.val i)))
 ∀ p q r, enc p ≠ enc q → ∀ θ : ℝ, 0 < θ → θ < 1 →
   enc r ≠ θ • enc p + (1-θ) • enc q := by
 intro enc p q r hne θ hθ hθ'
 apply chartDensity_ne_proper_mixture 32 _ _ _ θ (by norm_num) _ hθ hθ'
 intro he
 exact hne (by dsimp [enc]; rw [he])

theorem centered_extrema_straddle {α : Type*} [Fintype α]
 (w : α → ℝ) (hcenter : ∑ i, w i = 0) (hn : ¬ ∀ i, w i = 0) (lo hi : α)
 (hl : ∀ i, w lo ≤ w i) (hu : ∀ i, w i ≤ w hi) : w lo < 0 ∧ 0 < w hi := by
 classical
 constructor
 · by_contra hc
   have hnon : ∀ i, 0 ≤ w i := fun i => (le_of_not_gt hc).trans (hl i)
   exact hn (fun i => (Finset.sum_eq_zero_iff_of_nonneg (fun j _ => hnon j)).mp
     hcenter i (Finset.mem_univ i))
 · by_contra hc
   have hnon : ∀ i, 0 ≤ -w i := fun i => neg_nonneg.mpr ((hu i).trans (le_of_not_gt hc))
   have hs : (∑ i, -w i) = 0 := by rw [Finset.sum_neg_distrib,hcenter,neg_zero]
   apply hn
   intro i
   have hz := (Finset.sum_eq_zero_iff_of_nonneg (fun j _ => hnon j)).mp hs i (Finset.mem_univ i)
   linarith

theorem paper_encoder_uniform {α : Type*} [Fintype α]
 (w : α → ℝ) (s : ℝ) (hn : 0 < Fintype.card α) (hcenter : ∑ i, w i = 0) :
 ∃ p : {p : α → ℝ // (∀ i, 0 ≤ p i) ∧ ∑ i, p i = 1},
 (∀ i, p.val i = 1/(Fintype.card α : ℝ)) ∧
 chartDensity 32 (Real.sqrt ((Fintype.card α : ℝ)/s) *
   (∑ i, w i * Real.sqrt (p.val i)) / (∑ i, Real.sqrt (p.val i))) = chartDensity 32 0 := by
 have hnr : (0:ℝ) < Fintype.card α := by exact_mod_cast hn
 let p : {p : α → ℝ // (∀ i, 0 ≤ p i) ∧ ∑ i, p i = 1} :=
   ⟨fun _ => 1/(Fintype.card α : ℝ), ⟨fun _ => by positivity, by simp [hnr.ne']⟩⟩
 refine ⟨p,fun _ => rfl,?_⟩
 change chartDensity 32 (Real.sqrt ((Fintype.card α : ℝ)/s) *
   (∑ i, w i * Real.sqrt (1/(Fintype.card α : ℝ))) / _) = chartDensity 32 0
 rw [← Finset.sum_mul,hcenter]
 simp

theorem chartDensity_continuous (s : ℝ) (hs : 0 < s) : Continuous (chartDensity s) := by
 have hd : ∀ x : ℝ, (32+s*x^2) ≠ 0 := fun x =>
   (by positivity : 0 < (32:ℝ)+s*x^2).ne'
 have hden : Continuous (fun x : ℝ => 32+s*x^2) := by fun_prop
 have hinv := hden.inv₀ hd
 apply continuous_pi
 intro i
 apply continuous_pi
 intro j
 fin_cases i <;> fin_cases j
 · change Continuous (fun x : ℝ => (32+s*x^2)⁻¹ * 32)
   fun_prop
 · change Continuous (fun x : ℝ => (32+s*x^2)⁻¹ * (s*x))
   fun_prop
 · change Continuous (fun x : ℝ => (32+s*x^2)⁻¹ * (32*x))
   fun_prop
 · change Continuous (fun x : ℝ => (32+s*x^2)⁻¹ * (s*x^2))
   fun_prop

theorem chartDensity_closed_arc (s a b : ℝ) (hs : 0 < s) :
 IsCompact (chartDensity s '' Set.Icc a b) ∧
 IsClosed (chartDensity s '' Set.Icc a b) ∧ Function.Injective (chartDensity s) := by
 have hc : IsCompact (chartDensity s '' Set.Icc a b) := isCompact_Icc.image (chartDensity_continuous s hs)
 exact ⟨hc,hc.isClosed,chartDensity_injective s hs⟩

theorem chartDensity_orthonormal_domain (t : ℝ) : IsDensity (chartDensity 32 t) := by
 rw [chartDensity_orthonormal]
 have hm : (!![1,t;t,t^2] : M2) = vecMulVec ![1,t] ![1,t] := by
   ext i j
   fin_cases i <;> fin_cases j <;> simp [vecMulVec,pow_two]
 constructor
 · rw [hm]
   have hp := Matrix.posSemidef_vecMulVec_self_star (![1,t] : Fin 2 → ℝ)
   simpa only [star_trivial] using hp.smul (by positivity : 0 ≤ (1+t^2)⁻¹)
 · have hd : (1:ℝ)+t^2 ≠ 0 := (by positivity : 0 < (1:ℝ)+t^2).ne'
   simp [trace,Fin.sum_univ_two]
   field_simp

theorem paper_encoder_not_surjective {α : Type*} [Fintype α]
 (w : α → ℝ) (s : ℝ) :
 ∃ R : Density, ∀ p : {p : α → ℝ // (∀ i, 0 ≤ p i) ∧ ∑ i, p i = 1},
 chartDensity 32 (Real.sqrt ((Fintype.card α : ℝ)/s) *
   (∑ i, w i * Real.sqrt (p.val i)) / (∑ i, Real.sqrt (p.val i))) ≠ R.val := by
 have hd : IsDensity (!![0,0;0,1] : M2) := by
   have he : (!![0,0;0,1] : M2) = sixState 3 := by
     ext i j
     fin_cases i <;> fin_cases j <;>
       norm_num [sixState,Pa,Matrix.cons_val_three,Matrix.head_cons,Matrix.tail_cons]
   rw [he]
   exact six_states_density_and_projector.density 3
 refine ⟨⟨_,hd⟩,?_⟩
 intro p
 exact chartDensity_ne_orthogonal 32 _ (by norm_num)

theorem finite_extrema_exist {α : Type*} [Fintype α] [Nonempty α] (w : α → ℝ) :
 ∃ lo hi : α, (∀ i, w lo ≤ w i) ∧ (∀ i, w i ≤ w hi) := by
 classical
 obtain ⟨lo,_,hl⟩ := Finset.exists_min_image Finset.univ w Finset.univ_nonempty
 obtain ⟨hi,_,hu⟩ := Finset.exists_max_image Finset.univ w Finset.univ_nonempty
 exact ⟨lo,hi,fun i => hl i (Finset.mem_univ i),fun i => hu i (Finset.mem_univ i)⟩

noncomputable def boundaryRIFrame : CenteredFrame32 :=
 ⟨riFrameW,riS,ri_s_positive,riFrameW_centered,riFrameW_norm⟩

theorem ri_frameEncoding_eq (p : Simplex32) :
 frameEncoding boundaryRIFrame p = riCoordinateDensity p := by
 rw [riCoordinateDensity_chart,riFrameLambda_formula]
 rfl

theorem ri_encoder_nonaffine (p q r : Simplex32)
 (hne : riCoordinateDensity p ≠ riCoordinateDensity q) (θ : ℝ)
 (hθ : 0 < θ) (hθ' : θ < 1) :
 riCoordinateDensity r ≠ θ • riCoordinateDensity p + (1-θ) • riCoordinateDensity q := by
 simpa only [ri_frameEncoding_eq] using
   frameEncoding_nonaffine boundaryRIFrame p q r (by simpa only [ri_frameEncoding_eq] using hne) θ hθ hθ'

theorem ri_encoder_image (lo hi : Fin 32)
 (hl : ∀ i, riFrameW lo ≤ riFrameW i) (hu : ∀ i, riFrameW i ≤ riFrameW hi) (R : M2) :
 (∃ p : Simplex32, riCoordinateDensity p = R) ↔
 ∃ t : ℝ, (32/riS)*riFrameW lo ≤ t ∧ t ≤ (32/riS)*riFrameW hi ∧
   chartDensity riS t = R := by
 simpa only [ri_frameEncoding_eq] using frameEncoding_image boundaryRIFrame lo hi hl hu R

#print axioms ri_frameEncoding_eq
#print axioms ri_encoder_nonaffine
#print axioms ri_encoder_image

#print axioms chartDensity_orthonormal_domain
#print axioms paper_encoder_not_surjective
#print axioms finite_extrema_exist

#print axioms paper_encoder_nonaffine
#print axioms centered_extrema_straddle
#print axioms paper_encoder_uniform
#print axioms chartDensity_continuous
#print axioms chartDensity_closed_arc

#print axioms paper_encoder_image
#print axioms chartDensity_orthonormal

#print axioms finite_sqrt_chart_range
#print axioms paper_encoder_chart_range

#print axioms frameEncoding_image
#print axioms chartDensity_pure
#print axioms frame_extrema_straddle
#print axioms frameEncoding_uniform

#print axioms normalized_sqrt_weights_surjective
#print axioms frame_rootChart_range

#print axioms chartDensity_mixture_det
#print axioms chartDensity_det_zero
#print axioms chartDensity_ne_proper_mixture
#print axioms frameEncoding_nonaffine
#print axioms chartDensity_ne_orthogonal
end BornCalculus
