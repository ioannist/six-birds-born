import BornCalculus.B05Witness

namespace BornCalculus
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0

/-- The centered frame checks are exact, including the squared norm. -/
theorem b05_frame_real : (∑ i : Fin 32, b04W i) = 0 ∧
 (∑ i : Fin 32, (b04W i)^2) = b04S := by
 dsimp [b04W,b04S]
 exact_mod_cast b04_frame_checksQ

theorem b05_amplitude_sum (t : ℝ) : (∑ i : Fin 32, (1+t*b04W i)) = 32 := by
 rw [Finset.sum_add_distrib,←Finset.mul_sum,b05_frame_real.1]
 simp

theorem b05_amplitude_norm (t : ℝ) :
 (∑ i : Fin 32, (1+t*b04W i)^2) = 32+b04S*t^2 := by
 have he (i : Fin 32) : (1+t*b04W i)^2 = 1+(2*t)*b04W i+t^2*(b04W i)^2 := by ring
 simp_rw [he]
 rw [Finset.sum_add_distrib,Finset.sum_add_distrib,←Finset.mul_sum,←Finset.mul_sum,
   b05_frame_real.1,b05_frame_real.2]
 simp
 ring

theorem b05_ray_den_positive (t : ℝ) : 0 < (32:ℝ)+b04S*t^2 :=
 add_pos_of_pos_of_nonneg (by norm_num) (mul_nonneg b04_s_positive.le (sq_nonneg t))

theorem b05_gate_moment_polynomial (t : ℝ) :
 (∑ i : Fin 32, b05Gate t i) =
 (b05MomentsQ 0:ℝ)+(b05MomentsQ 1:ℝ)*t+(b05MomentsQ 2:ℝ)*t^2 := by
 have hq := b05_momentsQ
 have h0 : (b05MomentsQ 0:ℝ) = ∑ i : Fin 32, if b04Joint i = 0 then (1:ℝ) else 0 := by
   have h := congrArg (fun q : ℚ => (q:ℝ)) hq.1
   simpa [apply_ite] using h
 have h1 : (b05MomentsQ 1:ℝ) = 2*(∑ i : Fin 32, if b04Joint i = 0 then b04W i else 0) := by
   have h := congrArg (fun q : ℚ => (q:ℝ)) hq.2.1
   simpa [b04W,apply_ite] using h
 have h2 : (b05MomentsQ 2:ℝ) = ∑ i : Fin 32, if b04Joint i = 0 then (b04W i)^2 else 0 := by
   have h := congrArg (fun q : ℚ => (q:ℝ)) hq.2.2
   simpa [b04W,apply_ite] using h
 have he (i : Fin 32) : b05Gate t i =
   (if b04Joint i = 0 then (1:ℝ) else 0)+
   (2*t)*(if b04Joint i = 0 then b04W i else 0)+
   t^2*(if b04Joint i = 0 then (b04W i)^2 else 0) := by
   by_cases hi : b04Joint i = 0 <;> simp [b05Gate,hi] <;> ring
 simp_rw [he]
 rw [Finset.sum_add_distrib,Finset.sum_add_distrib,←Finset.mul_sum,←Finset.mul_sum,
   ←h0,←h2,h1]
 ring

theorem b05_read_eq_gate_mass (t : ℝ) : b05Read t = b05FirstMass t := by
 rw [b05Read,b05FirstMass,b05_gate_moment_polynomial]

theorem b05_first_mass_bounds (t : ℝ) : 0 ≤ b05FirstMass t ∧ b05FirstMass t ≤ 1 := by
 have hd := b05_ray_den_positive t
 have hn : ∀ i, 0 ≤ b05Gate t i := by
   intro i
   by_cases hi : b04Joint i = 0 <;> simp [b05Gate,hi,sq_nonneg]
 have hl : ∀ i, b05Gate t i ≤ (1+t*b04W i)^2 := by
   intro i
   by_cases hi : b04Joint i = 0 <;> simp [b05Gate,hi,sq_nonneg]
 have hsum : (∑ i : Fin 32, b05Gate t i) ≤ 32+b04S*t^2 := by
   rw [←b05_amplitude_norm t]
   exact Finset.sum_le_sum (fun i _ => hl i)
 constructor
 · exact div_nonneg (Finset.sum_nonneg (fun i _ => hn i)) hd.le
 · exact (div_le_one hd).mpr hsum

theorem b05_completion_word_bounds (t : ℝ) :
 0 ≤ b05CompletionWord t ∧ b05CompletionWord t ≤ 1 := by
 have hm := b05_first_mass_bounds t
 have hr := b05_first_mass_bounds (b04Chart (b05CompletionUpdate t))
 rw [b05CompletionWord,b05_read_eq_gate_mass]
 constructor
 · exact mul_nonneg hm.1 hr.1
 · calc
     b05FirstMass t*b05FirstMass (b04Chart (b05CompletionUpdate t)) ≤ b05FirstMass t*1 :=
       mul_le_mul_of_nonneg_left hr.2 hm.1
     _ ≤ 1 := by simpa using hm.2

theorem ensembleWord_bounds (E : RayEnsemble) : 0 ≤ ensembleWord E ∧ ensembleWord E ≤ 1 := by
 constructor
 · apply Finset.sum_nonneg
   intro a _
   exact mul_nonneg (E.nonnegative a) (b05_completion_word_bounds (E.ray a)).1
 · calc
     ensembleWord E ≤ ∑ a, E.weight a := by
       apply Finset.sum_le_sum
       intro a _
       simpa only [mul_one] using mul_le_mul_of_nonneg_left
         (b05_completion_word_bounds (E.ray a)).2 (E.nonnegative a)
     _ = 1 := E.normalized

noncomputable def b05RayPreparation (t : ℝ) : Simplex32 :=
 ⟨fun i => (1+t*b04W i)^2/(32+b04S*t^2),⟨fun i => by
   exact div_nonneg (sq_nonneg _) (b05_ray_den_positive t).le,
   by
     change (∑ i : Fin 32, (1+t*b04W i)^2/(32+b04S*t^2)) = 1
     rw [←Finset.sum_div,b05_amplitude_norm]
     exact div_self (b05_ray_den_positive t).ne'⟩⟩

theorem b05_ray_encoder (t : ℝ) (hp : ∀ i, 0 ≤ 1+t*b04W i) :
 b04Chart (b05RayPreparation t).val = t := by
 have hd := b05_ray_den_positive t
 have hi : 0 < (32+b04S*t^2)⁻¹ := inv_pos.mpr hd
 have hr : ∀ i : Fin 32, 0 ≤ 1+t*b04W i ∧
   (1+t*b04W i)^2 = ((1+t*b04W i)^2/(32+b04S*t^2))/((32+b04S*t^2)⁻¹) := by
   intro i
   refine ⟨hp i,?_⟩
   simp only [div_inv_eq_mul,div_mul_cancel₀ _ hd.ne']
 have hs : 0 < ∑ i : Fin 32, (1+t*b04W i) := by rw [b05_amplitude_sum]; norm_num
 have hw : (∑ i : Fin 32, b04W i*(1+t*b04W i)) = t*b04S := by
   have he (i : Fin 32) : b04W i*(1+t*b04W i) = b04W i+t*(b04W i)^2 := by ring
   simp_rw [he]
   rw [Finset.sum_add_distrib,←Finset.mul_sum,b05_frame_real.1,b05_frame_real.2]
   simp
 change rootChart b04W b04S (fun i => (1+t*b04W i)^2/(32+b04S*t^2)) = t
 rw [rootChart_of_relative_roots b04W (fun i => 1+t*b04W i) _ b04S _ hi hr hs,
   hw,b05_amplitude_sum]
 field_simp [b04_s_positive.ne']

theorem b05_sources_reachable (side atom : Fin 2) :
 b04Density (b05RayPreparation (b05RayQ side atom:ℝ)).val =
 chartDensity b04S (b05RayQ side atom:ℝ) := by
 rw [b04Density,b05_ray_encoder]
 intro i
 have h : (0:ℝ) < 1+(b05RayQ side atom:ℝ)*b04W i := by
   dsimp [b04W]
   exact_mod_cast (b05_sourcesQ side atom).1 i
 exact h.le


theorem ensembleDensity_domain (E : RayEnsemble) : GIsDensity 32 b04S (ensembleDensity E) := by
 refine ⟨?_,?_⟩
 · unfold GPositive ensembleDensity
   rw [Matrix.mul_sum]
   apply Matrix.posSemidef_sum
   intro a _
   rw [Matrix.mul_smul]
   exact (chartDensity_domain b04S (E.ray a) b04_s_positive).1.smul (E.nonnegative a)
 · unfold ensembleDensity
   rw [Matrix.trace_sum]
   have he (a : Fin 2) : trace (E.weight a • chartDensity b04S (E.ray a)) = E.weight a := by
     rw [Matrix.trace_smul,(chartDensity_domain b04S (E.ray a) b04_s_positive).2]
     simp
   simp_rw [he]
   exact E.normalized


theorem b05_gate_nonnegative (t : ℝ) (i : Fin 32) : 0 ≤ b05Gate t i := by
 by_cases h : b04Joint i = 0 <;> simp [b05Gate,h,sq_nonneg]

theorem b05_kernel_nonnegative (i j : Fin 32) : 0 ≤ b04K i j := by
 dsimp [b04K]
 exact_mod_cast b05_kernel_nonnegativeQ i j

theorem b05_kernel_row_mass (i : Fin 32) : 0 < ∑ j : Fin 32, b04K i j := by
 dsimp [b04K]
 exact_mod_cast b05_kernel_row_massQ i

theorem b05_completion_update_nonnegative (t : ℝ) (j : Fin 32) :
 0 ≤ b05CompletionUpdate t j := by
 simp only [b05CompletionUpdate,mulVec,dotProduct,transpose_apply]
 exact Finset.sum_nonneg (fun i _ => mul_nonneg (b05_kernel_nonnegative i j) (b05_gate_nonnegative t i))

theorem b05_completion_update_sum (t : ℝ) :
 (∑ j : Fin 32, b05CompletionUpdate t j) =
   ∑ i : Fin 32, b05Gate t i*(∑ j : Fin 32, b04K i j) := by
 simp only [b05CompletionUpdate,mulVec,dotProduct,transpose_apply]
 rw [Finset.sum_comm]
 apply Finset.sum_congr rfl
 intro i _
 rw [←Finset.sum_mul]
 ring

/-- Every positive first-read branch has a nonzero nonnegative successor,
so the homogeneous root chart uses its proper domain. -/
theorem b05_completion_update_domain (t : ℝ) (hm : 0 < b05FirstMass t) :
 (∀ j, 0 ≤ b05CompletionUpdate t j) ∧
 0 < ∑ j : Fin 32, Real.sqrt (b05CompletionUpdate t j) := by
 classical
 have hd := b05_ray_den_positive t
 have hg : 0 < ∑ i : Fin 32, b05Gate t i := by
   have h := mul_pos hm hd
   simpa only [b05FirstMass,div_mul_cancel₀ _ hd.ne'] using h
 have hi : ∃ i : Fin 32, 0 < b05Gate t i := by
   by_contra h
   push_neg at h
   exact (not_le_of_gt hg) (Finset.sum_nonpos (fun i _ => h i))
 obtain ⟨i,hi⟩ := hi
 have hsum : 0 < ∑ j : Fin 32, b05CompletionUpdate t j := by
   rw [b05_completion_update_sum]
   apply Finset.sum_pos'
   · intro k _
     exact mul_nonneg (b05_gate_nonnegative t k) (b05_kernel_row_mass k).le
   · exact ⟨i,Finset.mem_univ i,mul_pos hi (b05_kernel_row_mass i)⟩
 have hj : ∃ j : Fin 32, 0 < b05CompletionUpdate t j := by
   by_contra h
   push_neg at h
   exact (not_le_of_gt hsum) (Finset.sum_nonpos (fun j _ => h j))
 obtain ⟨j,hj⟩ := hj
 refine ⟨b05_completion_update_nonnegative t,?_⟩
 apply Finset.sum_pos'
 · intro k _
   exact Real.sqrt_nonneg _
 · exact ⟨j,Finset.mem_univ j,Real.sqrt_pos.mpr hj⟩


/-- Positive scalar normalization cancels in the encoded root chart. -/
theorem b05_chart_scale (p : Fin 32 → ℝ) (c : ℝ) (hc : 0 < c) :
 b04Chart (fun i => c*p i) = b04Chart p := by
 have hr (i : Fin 32) : Real.sqrt (c*p i) = Real.sqrt c*Real.sqrt (p i) :=
   Real.sqrt_mul hc.le _
 have hs : (∑ i : Fin 32, Real.sqrt (c*p i)) =
   Real.sqrt c*(∑ i : Fin 32, Real.sqrt (p i)) := by
   simp_rw [hr]
   rw [Finset.mul_sum]
 have ht : (∑ i : Fin 32, b04W i*Real.sqrt (c*p i)) =
   Real.sqrt c*(∑ i : Fin 32, b04W i*Real.sqrt (p i)) := by
   simp_rw [hr]
   rw [Finset.mul_sum]
   apply Finset.sum_congr rfl
   intro i _
   ring
 have hcr : Real.sqrt c ≠ 0 := (Real.sqrt_pos.mpr hc).ne'
 unfold b04Chart rootChart
 rw [hs,ht]
 by_cases hz : (∑ i : Fin 32, Real.sqrt (p i)) = 0
 · simp [hz]
 · field_simp [hcr,hz]

/-- Conditioning the admitted micro preparation before the retained kernel
has the same encoded successor as the homogeneous completion formula. -/
theorem b05_conditioned_push_encoding (t : ℝ) (hm : 0 < b05FirstMass t) :
 b04Chart (b04Kᵀ *ᵥ (fun i => b05Gate t i/((32+b04S*t^2)*b05FirstMass t))) =
 b04Chart (b05CompletionUpdate t) := by
 have hd : 0 < (32+b04S*t^2)*b05FirstMass t := mul_pos (b05_ray_den_positive t) hm
 have he : (fun i => b05Gate t i/((32+b04S*t^2)*b05FirstMass t)) =
   ((32+b04S*t^2)*b05FirstMass t)⁻¹ • b05Gate t := by
   funext i
   simp only [Pi.smul_apply,smul_eq_mul,div_eq_mul_inv,mul_comm]
 rw [he,Matrix.mulVec_smul]
 exact b05_chart_scale (b05CompletionUpdate t) _ (inv_pos.mpr hd)


noncomputable def b05ConditionedPreparation (t : ℝ) (hm : 0 < b05FirstMass t) : Simplex32 :=
 ⟨fun i => b05Gate t i/((32+b04S*t^2)*b05FirstMass t),⟨fun i => by
   exact div_nonneg (b05_gate_nonnegative t i) (mul_pos (b05_ray_den_positive t) hm).le,
   by
     change (∑ i : Fin 32, b05Gate t i/((32+b04S*t^2)*b05FirstMass t)) = 1
     rw [←Finset.sum_div]
     have he : (32+b04S*t^2)*b05FirstMass t = ∑ i : Fin 32, b05Gate t i := by
       rw [mul_comm,b05FirstMass,div_mul_cancel₀ _ (b05_ray_den_positive t).ne']
     rw [←he]
     exact div_self (mul_pos (b05_ray_den_positive t) hm).ne'⟩⟩

end BornCalculus
