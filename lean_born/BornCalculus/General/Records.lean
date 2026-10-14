import BornCalculus.General.Frame

namespace BornCalculus.General
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0
variable {n : ℕ}

noncomputable def point (i : Fin n) : Simplex n :=
  ⟨fun k => if k = i then 1 else 0,⟨fun k => by
    change (0:ℝ) ≤ if k = i then 1 else 0
    split_ifs <;> norm_num,by simp⟩⟩
noncomputable def record {L : Type*} [DecidableEq L]
    (q : Fin n → L) (p : Simplex n) (a : L) : ℝ :=
  ∑ i, if q i = a then p.val i else 0
noncomputable def records {ι : Type*} {L : ι → Type*} [∀ f, DecidableEq (L f)]
    (q : ∀ f, Fin n → L f) (p : Simplex n) : ∀ f, L f → ℝ :=
  fun f a => record (q f) p a

theorem point_of32 (i : Fin 32) : point i = simplexPoint i := rfl
theorem record_of32 {m : ℕ} (q : Fin 32 → Fin m) (p : Simplex32) (a : Fin m) :
    record q p a = frameRecord q p a := rfl

theorem point_chart (F : CenteredFrame n) (i : Fin n) :
    rootChart F (point i) = ((n:ℝ)/F.s)*F.w i := by
  classical
  have hr (k : Fin n) : Real.sqrt (if k = i then (1:ℝ) else 0) = if k = i then 1 else 0 := by
    split_ifs <;> norm_num
  unfold rootChart point
  simp_rw [hr]
  simp

theorem chart_density_recover (F : CenteredFrame n) (t : ℝ) :
    (chartDensity n F.s t) 1 0 / (chartDensity n F.s t) 0 0 = t := by
  have hd : (n:ℝ)+F.s*t^2 ≠ 0 :=
    (add_pos_of_pos_of_nonneg (size_positive F) (mul_nonneg F.positive.le (sq_nonneg t))).ne'
  simp [chartDensity]
  field_simp [(size_positive F).ne']
theorem chart_density_injective (F : CenteredFrame n) :
    Function.Injective (chartDensity n F.s) := by
  intro a b h
  have he := congrArg (fun R : M2 => R 1 0 / R 0 0) h
  simpa only [chart_density_recover F a,chart_density_recover F b] using he

theorem point_encoding_eq_iff (F : CenteredFrame n) (i j : Fin n) :
    encoding F (point i) = encoding F (point j) ↔ F.w i = F.w j := by
  simp only [encoding,point_chart]
  constructor
  · intro h
    exact mul_left_cancel₀ (div_ne_zero (size_positive F).ne' F.positive.ne')
      (chart_density_injective F h)
  · intro h; rw [h]

theorem record_point {L : Type*} [DecidableEq L] (q : Fin n → L) (i : Fin n) (a : L) :
    record q (point i) a = if q i = a then 1 else 0 := by
  classical
  unfold record point
  rw [Finset.sum_eq_single i]
  · simp
  · intro k _ hki; simp [hki]
  · simp

/-- No restriction on the number of maps, nor a shared label type. -/
theorem records_points_eq_iff {ι : Type*} {L : ι → Type*} [∀ f, DecidableEq (L f)]
    (q : ∀ f, Fin n → L f) (i j : Fin n) :
    records q (point i) = records q (point j) ↔ ∀ f, q f i = q f j := by
  constructor
  · intro he f
    have h := congrArg (fun v : ∀ f, L f → ℝ => v f (q f i)) he
    by_contra hn
    simp [records,record_point,Ne.symm hn] at h
  · intro h
    funext f a
    simp only [records,record_point,h f]

theorem strict_refinement {ι : Type*} {L : ι → Type*} [∀ f, DecidableEq (L f)]
    (F : CenteredFrame n) (q : ∀ f, Fin n → L f) (i j : Fin n)
    (hq : ∀ f, q f i = q f j) (hw : F.w i ≠ F.w j) :
    records q (point i) = records q (point j) ∧
      encoding F (point i) ≠ encoding F (point j) ∧
      ¬ ∃ g : (∀ f, L f → ℝ) → M2, ∀ p, encoding F p = g (records q p) := by
  have he := (records_points_eq_iff q i j).mpr hq
  have hn := mt (point_encoding_eq_iff F i j).mp hw
  exact ⟨he,hn,fiber_split_no_factor (records q) (encoding F) (point i) (point j) he hn⟩

theorem preparation_factors (F : CenteredFrame n) :
    ∃ g : Simplex n → M2, ∀ p, encoding F p = g p := ⟨encoding F,fun _ => rfl⟩

end BornCalculus.General
