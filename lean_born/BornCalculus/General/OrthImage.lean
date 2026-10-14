import BornCalculus.General.Image
import BornCalculus.General.Encoder

namespace BornCalculus.General
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0
variable {n : ℕ}

/-- The t_p of the paper, in the orthonormal frame. -/
noncomputable def orthChart (F : CenteredFrame n) (p : Simplex n) : ℝ :=
  Real.sqrt ((n:ℝ)/F.s)*(∑ i, F.w i*Real.sqrt (p.val i))/(∑ i, Real.sqrt (p.val i))

theorem orth_chart_scale (F : CenteredFrame n) (p : Simplex n) :
    orthChart F p = (Real.sqrt ((n:ℝ)/F.s)/((n:ℝ)/F.s))*rootChart F p := by
  unfold orthChart rootChart
  field_simp [(size_positive F).ne',F.positive.ne']

theorem orth_chart_coefficient_ratio (F : CenteredFrame n) (p : Simplex n) :
    coefficients F p 1 / coefficients F p 0 = orthChart F p := by
  have hn := (Real.sqrt_pos.mpr (size_positive F)).ne'
  have hs := (Real.sqrt_pos.mpr F.positive).ne'
  rw [coefficients_formula]
  simp only [Matrix.cons_val_zero,Matrix.cons_val_one]
  unfold orthChart
  rw [Real.sqrt_div (size_positive F).le]
  field_simp [(sqrt_sum_positive p).ne']

theorem normalized_two_vector (a b : ℝ) (ha : a ≠ 0) :
    (a^2+b^2)⁻¹ • vecMulVec ![a,b] ![a,b] = pureMatrix (b/a) := by
  have hd : a^2+b^2 ≠ 0 := (add_pos_of_pos_of_nonneg (sq_pos_of_ne_zero ha) (sq_nonneg b)).ne'
  have ht : 1+(b/a)^2 ≠ 0 := by positivity
  ext i j
  fin_cases i <;> fin_cases j <;>
    simp [vecMulVec,pureMatrix] <;> field_simp [ha,hd,ht]

theorem orth_encoding_chart (F : CenteredFrame n) (p : Simplex n) :
    toOrth n F.s (encoding F p) = pureMatrix (orthChart F p) := by
  rw [encoding_normalized_projection]
  have h0 : coefficients F p 0 ≠ 0 := by
    rw [coefficients_formula]
    exact div_ne_zero (sqrt_sum_positive p).ne' (Real.sqrt_pos.mpr (size_positive F)).ne'
  have hv : coefficients F p = ![coefficients F p 0,coefficients F p 1] := by
    ext i; fin_cases i <;> rfl
  rw [hv]
  simp only [dotProduct,Fin.sum_univ_two,Matrix.cons_val_zero,Matrix.cons_val_one,←pow_two]
  rw [normalized_two_vector _ _ h0,orth_chart_coefficient_ratio]

theorem orth_encoder_exact_range (F : CenteredFrame n) :
    ∃ lo hi : Fin n, (∀ i, F.w lo ≤ F.w i) ∧ (∀ i, F.w i ≤ F.w hi) ∧
      F.w lo < 0 ∧ 0 < F.w hi ∧
      ∀ t : ℝ, (∃ p : Simplex n, orthChart F p = t) ↔
        Real.sqrt ((n:ℝ)/F.s)*F.w lo ≤ t ∧ t ≤ Real.sqrt ((n:ℝ)/F.s)*F.w hi := by
  obtain ⟨lo,hi,hl,hu,hneg,hpos,hrange⟩ := encoder_chart_exact_range F
  have hc := div_pos (size_positive F) F.positive
  let k := Real.sqrt ((n:ℝ)/F.s)/((n:ℝ)/F.s)
  have hk : 0 < k := div_pos (Real.sqrt_pos.mpr hc) hc
  have hkc : k*((n:ℝ)/F.s) = Real.sqrt ((n:ℝ)/F.s) := div_mul_cancel₀ _ hc.ne'
  refine ⟨lo,hi,hl,hu,hneg,hpos,?_⟩
  intro t
  constructor
  · rintro ⟨p,rfl⟩
    obtain ⟨hlo,hhi⟩ := (hrange (rootChart F p)).mp ⟨p,rfl⟩
    rw [orth_chart_scale]
    change _ ≤ k*rootChart F p ∧ k*rootChart F p ≤ _
    constructor
    · simpa only [←mul_assoc,hkc] using mul_le_mul_of_nonneg_left hlo hk.le
    · simpa only [←mul_assoc,hkc] using mul_le_mul_of_nonneg_left hhi hk.le
  · intro ht
    have hb : ((n:ℝ)/F.s)*F.w lo ≤ t/k ∧ t/k ≤ ((n:ℝ)/F.s)*F.w hi := by
      have he (w : ℝ) : ((n:ℝ)/F.s)*w*k = Real.sqrt ((n:ℝ)/F.s)*w := by
        calc
          _ = (k*((n:ℝ)/F.s))*w := by ring
          _ = _ := by rw [hkc]
      constructor
      · apply (le_div_iff₀ hk).mpr
        rw [he]; exact ht.1
      · apply (div_le_iff₀ hk).mpr
        rw [he]; exact ht.2
    obtain ⟨p,hp⟩ := (hrange (t/k)).mpr hb
    refine ⟨p,?_⟩
    rw [orth_chart_scale,hp]
    exact mul_div_cancel₀ t hk.ne'

theorem orth_encoder_image (F : CenteredFrame n) :
    ∃ lo hi : Fin n, (∀ i, F.w lo ≤ F.w i) ∧ (∀ i, F.w i ≤ F.w hi) ∧
      F.w lo < 0 ∧ 0 < F.w hi ∧
      ∀ R : M2, (∃ p : Simplex n, toOrth n F.s (encoding F p) = R) ↔
        ∃ t : ℝ, Real.sqrt ((n:ℝ)/F.s)*F.w lo ≤ t ∧
          t ≤ Real.sqrt ((n:ℝ)/F.s)*F.w hi ∧ pureMatrix t = R := by
  obtain ⟨lo,hi,hl,hu,hneg,hpos,hr⟩ := orth_encoder_exact_range F
  refine ⟨lo,hi,hl,hu,hneg,hpos,?_⟩
  intro R
  constructor
  · rintro ⟨p,rfl⟩
    exact ⟨orthChart F p,((hr _).mp ⟨p,rfl⟩).1,((hr _).mp ⟨p,rfl⟩).2,
      (orth_encoding_chart F p).symm⟩
  · rintro ⟨t,htl,hth,hR⟩
    obtain ⟨p,hp⟩ := (hr t).mpr ⟨htl,hth⟩
    exact ⟨p,by rw [orth_encoding_chart,hp,hR]⟩

theorem orth_uniform_encoding (F : CenteredFrame n) :
    toOrth n F.s (encoding F (uniform F)) = !![1,0;0,0] := by
  rw [orth_encoding_chart,orth_chart_scale,uniform_chart]
  simp [pureMatrix]

theorem orth_encoding_omits_orthogonal (F : CenteredFrame n) (p : Simplex n) :
    toOrth n F.s (encoding F p) ≠ (!![0,0;0,1] : M2) := by
  rw [orth_encoding_chart]
  intro h
  have he := congrArg (fun A : M2 => A 0 0) h
  simp [pureMatrix] at he
  nlinarith [sq_nonneg (orthChart F p)]

theorem orth_encoding_non_affine (F : CenteredFrame n) (p q : Simplex n)
    (hpq : encoding F p ≠ encoding F q) (θ : ℝ) (h₀ : 0 < θ) (h₁ : θ < 1) :
    toOrth n F.s (encoding F (mixedPreparation p q θ h₀.le h₁.le)) ≠
      θ • toOrth n F.s (encoding F p) + (1-θ) • toOrth n F.s (encoding F q) := by
  have h := frame_coordinate_transfer n F.s (size_positive F) F.positive
  intro he
  rw [←h.scalar,←h.scalar,←h.addition] at he
  have he' := congrArg (fromOrth n F.s) he
  simp only [h.inverse_left] at he'
  exact encoding_non_affine F p q hpq θ h₀ h₁ he'

end BornCalculus.General
