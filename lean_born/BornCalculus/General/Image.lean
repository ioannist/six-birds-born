import BornCalculus.General.Records

namespace BornCalculus.General
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0
variable {n : ℕ}

theorem simplex_square_sum_positive (a : Simplex n) : 0 < ∑ i, (a.val i)^2 := by
  have hi : ∃ i, 0 < a.val i := by
    by_contra h
    push_neg at h
    have hz := Finset.sum_nonpos (fun i (_ : i ∈ Finset.univ) => h i)
    rw [a.property.2] at hz
    norm_num at hz
  obtain ⟨i,hi⟩ := hi
  exact Finset.sum_pos' (fun j _ => sq_nonneg _) ⟨i,Finset.mem_univ i,sq_pos_of_pos hi⟩

/-- Inverse to the normalized-root weights used by the encoder. -/
noncomputable def squarePreparation (a : Simplex n) : Simplex n :=
  ⟨fun i => (a.val i)^2/(∑ j, (a.val j)^2),
    ⟨fun i => div_nonneg (sq_nonneg _) (simplex_square_sum_positive a).le,
      by rw [←Finset.sum_div]; exact div_self (simplex_square_sum_positive a).ne'⟩⟩

theorem square_preparation_chart (F : CenteredFrame n) (a : Simplex n) :
    rootChart F (squarePreparation a) = ((n:ℝ)/F.s)*(∑ i, F.w i*a.val i) := by
  have hd := (Real.sqrt_pos.mpr (simplex_square_sum_positive a)).ne'
  have hr (i : Fin n) : Real.sqrt ((squarePreparation a).val i) =
      a.val i / Real.sqrt (∑ j, (a.val j)^2) := by
    change Real.sqrt ((a.val i)^2/(∑ j, (a.val j)^2)) = _
    rw [Real.sqrt_div (sq_nonneg _),Real.sqrt_sq (a.property.1 i)]
  unfold rootChart
  simp_rw [hr,←mul_div_assoc]
  rw [←Finset.sum_div,←Finset.sum_div,a.property.2]
  field_simp

theorem root_chart_bounds (F : CenteredFrame n) (p : Simplex n) (lo hi : ℝ)
    (hl : ∀ i, lo ≤ F.w i) (hu : ∀ i, F.w i ≤ hi) :
    ((n:ℝ)/F.s)*lo ≤ rootChart F p ∧ rootChart F p ≤ ((n:ℝ)/F.s)*hi := by
  have hs := sqrt_sum_positive p
  have hc := div_pos (size_positive F) F.positive
  have hlower : lo*(∑ i, Real.sqrt (p.val i)) ≤ ∑ i, F.w i*Real.sqrt (p.val i) := by
    rw [Finset.mul_sum]
    exact Finset.sum_le_sum (fun i _ => mul_le_mul_of_nonneg_right (hl i) (Real.sqrt_nonneg _))
  have hupper : (∑ i, F.w i*Real.sqrt (p.val i)) ≤ hi*(∑ i, Real.sqrt (p.val i)) := by
    rw [Finset.mul_sum]
    exact Finset.sum_le_sum (fun i _ => mul_le_mul_of_nonneg_right (hu i) (Real.sqrt_nonneg _))
  unfold rootChart
  constructor
  · apply (le_div_iff₀ hs).mpr
    nlinarith [mul_le_mul_of_nonneg_left hlower hc.le]
  · apply (div_le_iff₀ hs).mpr
    nlinarith [mul_le_mul_of_nonneg_left hupper hc.le]

theorem weighted_value_realization (F : CenteredFrame n) (i j : Fin n) (x : ℝ)
    (hij : F.w i < F.w j) (hx : F.w i ≤ x ∧ x ≤ F.w j) :
    ∃ a : Simplex n, (∑ k, F.w k*a.val k) = x := by
  classical
  have hne : i ≠ j := by intro h; subst j; exact lt_irrefl _ hij
  let c := (F.w j-x)/(F.w j-F.w i)
  let d := (x-F.w i)/(F.w j-F.w i)
  have hden := sub_pos.mpr hij
  have hc : 0 ≤ c := div_nonneg (sub_nonneg.mpr hx.2) hden.le
  have hd : 0 ≤ d := div_nonneg (sub_nonneg.mpr hx.1) hden.le
  have hcd : c+d = 1 := by dsimp [c,d]; field_simp [hden.ne']; ring
  let a : Simplex n := ⟨fun k => (if k = i then c else 0)+(if k = j then d else 0),
    ⟨fun k => add_nonneg (by split_ifs <;> positivity) (by split_ifs <;> positivity),
      by simp [Finset.sum_add_distrib,hcd]⟩⟩
  refine ⟨a,?_⟩
  change (∑ k, F.w k*((if k = i then c else 0)+(if k = j then d else 0))) = x
  simp only [mul_add,Finset.sum_add_distrib]
  have he (l : Fin n) (t : ℝ) : (∑ k, F.w k*(if k = l then t else 0)) = F.w l*t := by
    simp [mul_ite]
  rw [he,he]
  dsimp [c,d]
  field_simp
  ring

/-- Exact image interval, with indices attaining the minimum and maximum.
    The endpoint attainment hypotheses identify extrema, not extra substrate
    assumptions. Existence of such indices follows from finiteness. -/
theorem root_chart_range (F : CenteredFrame n) (lo hi : Fin n)
    (hl : ∀ i, F.w lo ≤ F.w i) (hu : ∀ i, F.w i ≤ F.w hi)
    (hlt : F.w lo < F.w hi) (t : ℝ) :
    (∃ p : Simplex n, rootChart F p = t) ↔
      ((n:ℝ)/F.s)*F.w lo ≤ t ∧ t ≤ ((n:ℝ)/F.s)*F.w hi := by
  have hc := div_pos (size_positive F) F.positive
  constructor
  · rintro ⟨p,rfl⟩; exact root_chart_bounds F p _ _ hl hu
  · intro ht
    have hx : F.w lo ≤ t/((n:ℝ)/F.s) ∧ t/((n:ℝ)/F.s) ≤ F.w hi :=
      ⟨(le_div_iff₀ hc).mpr (by nlinarith [ht.1]),
        (div_le_iff₀ hc).mpr (by nlinarith [ht.2])⟩
    obtain ⟨a,ha⟩ := weighted_value_realization F lo hi _ hlt hx
    refine ⟨squarePreparation a,?_⟩
    rw [square_preparation_chart,ha]
    exact mul_div_cancel₀ t hc.ne'

noncomputable def mixedPreparation (p q : Simplex n) (θ : ℝ) (h₀ : 0 ≤ θ) (h₁ : θ ≤ 1) : Simplex n :=
  ⟨fun i => θ*p.val i+(1-θ)*q.val i,
    ⟨fun i => add_nonneg (mul_nonneg h₀ (p.property.1 i))
      (mul_nonneg (sub_nonneg.mpr h₁) (q.property.1 i)),by
        rw [Finset.sum_add_distrib,←Finset.mul_sum,←Finset.mul_sum,p.property.2,q.property.2]
        ring⟩⟩

theorem encoding_non_affine (F : CenteredFrame n) (p q : Simplex n)
    (hpq : encoding F p ≠ encoding F q) (θ : ℝ) (h₀ : 0 < θ) (h₁ : θ < 1) :
    encoding F (mixedPreparation p q θ h₀.le h₁.le) ≠
      θ • encoding F p + (1-θ) • encoding F q := by
  intro he
  have h := frame_coordinate_transfer n F.s (size_positive F) F.positive
  let D (r : Simplex n) : Density :=
    ⟨toOrth n F.s (encoding F r),(h.density_domain _).mp (encoding_domain F r)⟩
  let r := mixedPreparation p q θ h₀.le h₁.le
  have hm : (D r).val = ∑ i : Fin 2, (![θ,1-θ] i) • (![D p,D q] i).val := by
    change toOrth n F.s (encoding F r) = _
    rw [he,h.addition,h.scalar,h.scalar]
    simp [D,Fin.sum_univ_two]
  have hp : (D r).val*(D r).val = (D r).val := by
    change toOrth n F.s (encoding F r)*toOrth n F.s (encoding F r) = _
    rw [←h.multiplication,encoding_pure]
  have hn : ∀ i : Fin 2, 0 ≤ ![θ,1-θ] i := by intro i; fin_cases i <;> simp <;> linarith
  have hs : (∑ i : Fin 2, ![θ,1-θ] i) = 1 := by simp [Fin.sum_univ_two]
  have hx := pure_state_extremality (D r) (![D p,D q]) (![θ,1-θ]) hn hs hp hm
  have heq : D p = D q := (hx 0 (by simpa using h₀)).trans (hx 1 (by simp; linarith)).symm
  have ht := congrArg (fun R : Density => fromOrth n F.s R.val) heq
  exact hpq (by simpa only [D,h.inverse_left] using ht)

theorem extrema_straddle_zero (F : CenteredFrame n) :
    ∃ lo hi : Fin n, (∀ i, F.w lo ≤ F.w i) ∧ (∀ i, F.w i ≤ F.w hi) ∧
      F.w lo < 0 ∧ 0 < F.w hi := by
  classical
  have hn : 0 < n := by have := F.size; omega
  let i : Fin n := ⟨0,hn⟩
  have hs : (Finset.univ : Finset (Fin n)).Nonempty := ⟨i,Finset.mem_univ i⟩
  obtain ⟨lo,_,hl⟩ := Finset.exists_min_image Finset.univ F.w hs
  obtain ⟨hi,_,hu⟩ := Finset.exists_max_image Finset.univ F.w hs
  have hl' : ∀ i, F.w lo ≤ F.w i := fun i => hl i (Finset.mem_univ i)
  have hu' : ∀ i, F.w i ≤ F.w hi := fun i => hu i (Finset.mem_univ i)
  have neg : F.w lo < 0 := by
    by_contra h
    have hpos : ∀ i, 0 ≤ F.w i := fun i => (le_of_not_gt h).trans (hl' i)
    have hall := (Finset.sum_eq_zero_iff_of_nonneg (fun i _ => hpos i)).mp F.centered
    have hz : (∑ i, (F.w i)^2) = 0 := by simp [hall]
    rw [F.squared] at hz
    exact F.positive.ne' hz
  have pos : 0 < F.w hi := by
    by_contra h
    have hneg : ∀ i, F.w i ≤ 0 := fun i => (hu' i).trans (le_of_not_gt h)
    have hall := (Finset.sum_eq_zero_iff_of_nonpos (fun i _ => hneg i)).mp F.centered
    have hz : (∑ i, (F.w i)^2) = 0 := by simp [hall]
    rw [F.squared] at hz
    exact F.positive.ne' hz
  exact ⟨lo,hi,hl',hu',neg,pos⟩

/-- General-n exact range without additional extremum hypotheses. -/
theorem encoder_chart_exact_range (F : CenteredFrame n) :
    ∃ lo hi : Fin n, (∀ i, F.w lo ≤ F.w i) ∧ (∀ i, F.w i ≤ F.w hi) ∧
      F.w lo < 0 ∧ 0 < F.w hi ∧
      ∀ t : ℝ, (∃ p : Simplex n, rootChart F p = t) ↔
        ((n:ℝ)/F.s)*F.w lo ≤ t ∧ t ≤ ((n:ℝ)/F.s)*F.w hi := by
  obtain ⟨lo,hi,hl,hu,hneg,hpos⟩ := extrema_straddle_zero F
  exact ⟨lo,hi,hl,hu,hneg,hpos,root_chart_range F lo hi hl hu (hneg.trans hpos)⟩

noncomputable def uniform (F : CenteredFrame n) : Simplex n :=
  ⟨fun _ => 1/(n:ℝ),⟨fun _ => (one_div_pos.mpr (size_positive F)).le,by
    simp [(size_positive F).ne']⟩⟩
theorem uniform_chart (F : CenteredFrame n) : rootChart F (uniform F) = 0 := by
  simp [rootChart,uniform,←Finset.sum_mul,F.centered]
theorem uniform_encoding (F : CenteredFrame n) : encoding F (uniform F) = !![1,0;0,0] := by
  rw [encoding,uniform_chart]
  ext a b
  fin_cases a <;> fin_cases b <;> simp [chartDensity,(size_positive F).ne']
theorem encoding_omits_orthogonal (F : CenteredFrame n) (p : Simplex n) :
    encoding F p ≠ (!![0,0;0,1] : M2) := by
  intro h
  have he := congrArg (fun A : M2 => A 0 0) h
  have hd : 0 < (n:ℝ)+F.s*(rootChart F p)^2 :=
    add_pos_of_pos_of_nonneg (size_positive F) (mul_nonneg F.positive.le (sq_nonneg _))
  have hp : 0 < (encoding F p) 0 0 := by
    simp only [encoding,chartDensity,Matrix.smul_apply,smul_eq_mul]
    exact mul_pos (inv_pos.mpr hd) (size_positive F)
  simp at he
  exact hp.ne' he

end BornCalculus.General
