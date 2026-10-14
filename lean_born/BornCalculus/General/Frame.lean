import BornCalculus.CenteredFrame
import BornCalculus.FiniteSimplex

namespace BornCalculus.General
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0

/-- The same centered metric frame as CenteredFrame32, with arbitrary size. -/
structure CenteredFrame (n : ℕ) where
  w : Fin n → ℝ
  s : ℝ
  size : 2 ≤ n
  positive : 0 < s
  centered : (∑ i, w i) = 0
  squared : (∑ i, (w i)^2) = s

abbrev Simplex (n : ℕ) := {p : Fin n → ℝ // (∀ i, 0 ≤ p i) ∧ ∑ i, p i = 1}
variable {n : ℕ}

theorem size_positive (F : CenteredFrame n) : 0 < (n : ℝ) := by
  exact_mod_cast (by have := F.size; omega : 0 < n)

noncomputable def parent (F : CenteredFrame n) (i : Fin n) : M2 :=
  !![1/(n:ℝ), F.w i/(n:ℝ); F.w i/F.s, (F.w i)^2/F.s]
noncomputable def lens {L : Type*} [Fintype L] [DecidableEq L]
    (F : CenteredFrame n) (q : Fin n → L) (a : L) : M2 :=
  ∑ i, if q i = a then parent F i else 0
noncomputable def effect (F : CenteredFrame n) (S : Finset (Fin n)) : M2 :=
  ∑ i ∈ S, parent F i
noncomputable def chartDensity (n : ℕ) (s t : ℝ) : M2 :=
  ((n:ℝ)+s*t^2)⁻¹ • !![(n:ℝ),s*t;(n:ℝ)*t,s*t^2]
noncomputable def rootChart (F : CenteredFrame n) (p : Simplex n) : ℝ :=
  ((n:ℝ)/F.s) * (∑ i, F.w i * Real.sqrt (p.val i)) / (∑ i, Real.sqrt (p.val i))
noncomputable def encoding (F : CenteredFrame n) (p : Simplex n) : M2 :=
  chartDensity n F.s (rootChart F p)

def of32 (F : CenteredFrame32) : CenteredFrame 32 :=
  ⟨F.w,F.s,by norm_num,F.positive,F.centered,F.squared⟩
theorem parent_of32 (F : CenteredFrame32) (i : Fin 32) :
    parent (of32 F) i = frameParent F i := by rfl
theorem lens_of32 {m : ℕ} (F : CenteredFrame32) (q : Fin 32 → Fin m) (a : Fin m) :
    lens (of32 F) q a = frameLens F q a := by rfl
theorem encoding_of32 (F : CenteredFrame32) (p : Simplex32) :
    encoding (of32 F) p = frameEncoding F p := by rfl

theorem parent_metric (F : CenteredFrame n) (i : Fin n) :
    frameG n F.s * parent F i = vecMulVec ![1,F.w i] ![1,F.w i] := by
  ext a b
  fin_cases a <;> fin_cases b <;>
    simp [frameG,parent,vecMulVec,mul_apply,Fin.sum_univ_two] <;>
    field_simp [F.positive.ne', (size_positive F).ne']

theorem parent_positive (F : CenteredFrame n) (i : Fin n) :
    GPositive n F.s (parent F i) := by
  rw [GPositive,parent_metric]
  simpa only [star_trivial] using posSemidef_vecMulVec_self_star (![1,F.w i] : Fin 2 → ℝ)

theorem parent_sum (F : CenteredFrame n) : (∑ i, parent F i) = 1 := by
  ext a b
  fin_cases a <;> fin_cases b <;>
    simp [parent,Matrix.sum_apply,←Finset.sum_div,F.centered,F.squared,
      F.positive.ne', (size_positive F).ne']

theorem effect_positive (F : CenteredFrame n) (S : Finset (Fin n)) :
    GPositive n F.s (effect F S) := by
  unfold GPositive effect
  rw [Matrix.mul_sum]
  exact Matrix.posSemidef_sum S (fun i _ => parent_positive F i)

theorem effect_empty (F : CenteredFrame n) : effect F ∅ = 0 := by simp [effect]
theorem effect_univ (F : CenteredFrame n) : effect F Finset.univ = 1 := parent_sum F
theorem effect_union (F : CenteredFrame n) (S T : Finset (Fin n)) (h : Disjoint S T) :
    effect F (S ∪ T) = effect F S + effect F T := Finset.sum_union h
theorem effect_compl (F : CenteredFrame n) (S : Finset (Fin n)) :
    effect F Sᶜ = 1 - effect F S := by
  have h := effect_union F S Sᶜ disjoint_compl_right
  rw [Finset.union_compl, effect_univ] at h
  rw [h]; abel
theorem effect_domain (F : CenteredFrame n) (S : Finset (Fin n)) :
    GIsEffect n F.s (effect F S) :=
  ⟨effect_positive F S, by rw [← effect_compl]; exact effect_positive F Sᶜ⟩
theorem effect_singleton (F : CenteredFrame n) (i : Fin n) :
    effect F {i} = parent F i := by simp [effect]

theorem lens_effect {L : Type*} [Fintype L] [DecidableEq L]
    (F : CenteredFrame n) (q : Fin n → L) (a : L) :
    lens F q a = effect F (Finset.univ.filter (fun i => q i = a)) := by
  simp [lens,effect,Finset.sum_filter]
theorem lens_domain {L : Type*} [Fintype L] [DecidableEq L]
    (F : CenteredFrame n) (q : Fin n → L) (a : L) : GIsEffect n F.s (lens F q a) := by
  rw [lens_effect]; exact effect_domain F _
theorem lens_sum {L : Type*} [Fintype L] [DecidableEq L]
    (F : CenteredFrame n) (q : Fin n → L) : (∑ a, lens F q a) = 1 := by
  classical
  unfold lens
  rw [Finset.sum_comm]
  simpa [eq_comm] using parent_sum F

theorem chart_density_domain (F : CenteredFrame n) (t : ℝ) :
    GIsDensity n F.s (chartDensity n F.s t) := by
  have hd : 0 < (n:ℝ)+F.s*t^2 :=
    add_pos_of_pos_of_nonneg (size_positive F) (mul_nonneg F.positive.le (sq_nonneg t))
  have hm : frameG n F.s * chartDensity n F.s t =
      ((n:ℝ)+F.s*t^2)⁻¹ • vecMulVec ![(n:ℝ),F.s*t] ![(n:ℝ),F.s*t] := by
    ext a b
    fin_cases a <;> fin_cases b <;>
      simp [frameG,chartDensity,vecMulVec,mul_apply,Fin.sum_univ_two,pow_two] <;> ring
  refine ⟨?_,?_⟩
  · rw [GPositive,hm]
    simpa only [star_trivial] using
      (Matrix.posSemidef_vecMulVec_self_star (![(n:ℝ),F.s*t] : Fin 2 → ℝ)).smul
        (inv_nonneg.mpr hd.le)
  · simp [chartDensity,trace,Fin.sum_univ_two]
    field_simp

theorem chart_density_pure (F : CenteredFrame n) (t : ℝ) :
    chartDensity n F.s t * chartDensity n F.s t = chartDensity n F.s t := by
  have hd : (n:ℝ)+F.s*t^2 ≠ 0 :=
    (add_pos_of_pos_of_nonneg (size_positive F) (mul_nonneg F.positive.le (sq_nonneg t))).ne'
  ext a b
  fin_cases a <;> fin_cases b <;>
    simp [chartDensity,mul_apply,Fin.sum_univ_two] <;> field_simp

theorem encoding_domain (F : CenteredFrame n) (p : Simplex n) :
    GIsDensity n F.s (encoding F p) := chart_density_domain F _
theorem encoding_pure (F : CenteredFrame n) (p : Simplex n) :
    encoding F p * encoding F p = encoding F p := chart_density_pure F _

theorem sqrt_sum_positive (p : Simplex n) : 0 < ∑ i, Real.sqrt (p.val i) := by
  classical
  have hi : ∃ i : Fin n, 0 < p.val i := by
    by_contra h
    push_neg at h
    have hz := Finset.sum_nonpos (fun i (_ : i ∈ Finset.univ) => h i)
    rw [p.property.2] at hz
    norm_num at hz
  obtain ⟨i,hi⟩ := hi
  exact Finset.sum_pos' (fun k _ => Real.sqrt_nonneg _) ⟨i,Finset.mem_univ i,Real.sqrt_pos.mpr hi⟩

theorem parent_pairing (F : CenteredFrame n) (t : ℝ) (i : Fin n) :
    pairing (chartDensity n F.s t) (parent F i) = (1+t*F.w i)^2/((n:ℝ)+F.s*t^2) := by
  have hd : (n:ℝ)+F.s*t^2 ≠ 0 :=
    (add_pos_of_pos_of_nonneg (size_positive F) (mul_nonneg F.positive.le (sq_nonneg t))).ne'
  simp [pairing,chartDensity,parent,trace,Fin.sum_univ_two]
  field_simp [F.positive.ne', (size_positive F).ne', hd]

theorem effect_pairing (F : CenteredFrame n) (S : Finset (Fin n)) (t : ℝ) :
    pairing (chartDensity n F.s t) (effect F S) =
      ∑ i ∈ S, (1+t*F.w i)^2/((n:ℝ)+F.s*t^2) := by
  simp only [pairing,effect,Matrix.mul_sum,Matrix.trace_sum]
  exact Finset.sum_congr rfl (fun i _ => parent_pairing F t i)

end BornCalculus.General
