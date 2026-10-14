import BornCalculus.General.Frame

namespace BornCalculus.General
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0
variable {n : ℕ}

/-- Orthogonal projector onto span{1,w}, in ambient coordinates. -/
noncomputable def projector (F : CenteredFrame n) : Matrix (Fin n) (Fin n) ℝ :=
  fun i j => 1/(n:ℝ) + F.w i*F.w j/F.s
noncomputable def amplitude (F : CenteredFrame n) (p : Simplex n) : Fin n → ℝ :=
  projector F *ᵥ (fun i => Real.sqrt (p.val i))
noncomputable def projectedSquare (F : CenteredFrame n) (p : Simplex n)
    (S : Finset (Fin n)) : ℝ :=
  (∑ i ∈ S, (amplitude F p i)^2) / (∑ i, (amplitude F p i)^2)

theorem projector_transpose (F : CenteredFrame n) : (projector F)ᵀ = projector F := by
  ext i j; simp [projector]; ring

theorem projector_idempotent (F : CenteredFrame n) : projector F * projector F = projector F := by
  have hn := (size_positive F).ne'
  have hs := F.positive.ne'
  ext i j
  change (∑ k, (1/(n:ℝ)+F.w i*F.w k/F.s)*(1/(n:ℝ)+F.w k*F.w j/F.s)) = _
  calc
    _ = ∑ k, (((n:ℝ)⁻¹)^2 + (F.w i+F.w j)/((n:ℝ)*F.s)*F.w k +
        (F.w i*F.w j)/(F.s^2)*(F.w k)^2) := by
      apply Finset.sum_congr rfl
      intro k _
      field_simp
      ring
    _ = (n:ℝ)*((n:ℝ)⁻¹)^2 + (F.w i+F.w j)/((n:ℝ)*F.s)*(∑ k, F.w k) +
        (F.w i*F.w j)/(F.s^2)*(∑ k, (F.w k)^2) := by
      rw [Finset.sum_add_distrib,Finset.sum_add_distrib,←Finset.mul_sum,←Finset.mul_sum]
      simp
    _ = _ := by rw [F.centered,F.squared]; simp [projector]; field_simp

theorem projector_mulVec (F : CenteredFrame n) (v : Fin n → ℝ) (i : Fin n) :
    (projector F *ᵥ v) i = (∑ j, v j)/(n:ℝ) + F.w i*(∑ j, F.w j*v j)/F.s := by
  change (∑ j, (1/(n:ℝ)+F.w i*F.w j/F.s)*v j) = _
  calc
    _ = ∑ j, (v j/(n:ℝ) + F.w i*(F.w j*v j)/F.s) := by
      apply Finset.sum_congr rfl
      intro j _; ring
    _ = _ := by rw [Finset.sum_add_distrib,←Finset.sum_div,←Finset.sum_div,←Finset.mul_sum]

theorem projector_one (F : CenteredFrame n) : projector F *ᵥ (fun _ => 1) = (fun _ => 1) := by
  funext i
  rw [projector_mulVec]
  simp [F.centered,(size_positive F).ne']
theorem projector_w (F : CenteredFrame n) : projector F *ᵥ F.w = F.w := by
  funext i
  rw [projector_mulVec]
  simp only [←pow_two,F.centered,F.squared,zero_div,zero_add]
  field_simp [F.positive.ne']

theorem amplitude_formula (F : CenteredFrame n) (p : Simplex n) (i : Fin n) :
    amplitude F p i = ((∑ j, Real.sqrt (p.val j))/(n:ℝ))*(1+rootChart F p*F.w i) := by
  rw [amplitude,projector_mulVec]
  unfold rootChart
  field_simp [(sqrt_sum_positive p).ne', (size_positive F).ne', F.positive.ne']

theorem amplitude_norm (F : CenteredFrame n) (p : Simplex n) :
    (∑ i, (amplitude F p i)^2) =
      ((∑ j, Real.sqrt (p.val j))/(n:ℝ))^2*((n:ℝ)+F.s*(rootChart F p)^2) := by
  simp_rw [amplitude_formula,mul_pow]
  rw [←Finset.mul_sum]
  congr 1
  have he (i : Fin n) : (1+rootChart F p*F.w i)^2 =
      1 + 2*rootChart F p*F.w i + (rootChart F p)^2*(F.w i)^2 := by ring
  simp_rw [he]
  rw [Finset.sum_add_distrib,Finset.sum_add_distrib,←Finset.mul_sum,←Finset.mul_sum]
  simp [F.centered,F.squared,mul_comm]

theorem amplitude_norm_positive (F : CenteredFrame n) (p : Simplex n) :
    0 < ∑ i, (amplitude F p i)^2 := by
  rw [amplitude_norm]
  exact mul_pos (sq_pos_of_pos (div_pos (sqrt_sum_positive p) (size_positive F)))
    (add_pos_of_pos_of_nonneg (size_positive F) (mul_nonneg F.positive.le (sq_nonneg _)))

theorem amplitude_ne_zero (F : CenteredFrame n) (p : Simplex n) : amplitude F p ≠ 0 := by
  intro h
  have := amplitude_norm_positive F p
  simp [h] at this

/-- The all-preparation, all-subset projected-square/trace identity. -/
theorem projected_square_trace (F : CenteredFrame n) (p : Simplex n) (S : Finset (Fin n)) :
    projectedSquare F p S = pairing (encoding F p) (effect F S) := by
  rw [encoding,effect_pairing,projectedSquare,amplitude_norm]
  simp_rw [amplitude_formula,mul_pow]
  rw [←Finset.mul_sum,←Finset.sum_div]
  field_simp [(sqrt_sum_positive p).ne', (size_positive F).ne']

/-- Existing transfer gives the same identity in the paper's orthonormal frame. -/
theorem orth_projected_square_trace (F : CenteredFrame n) (p : Simplex n) (S : Finset (Fin n)) :
    projectedSquare F p S =
      pairing (toOrth n F.s (encoding F p)) (toOrth n F.s (effect F S)) := by
  rw [(frame_coordinate_transfer n F.s (size_positive F) F.positive).trace_pairing]
  exact projected_square_trace F p S

def carrier (F : CenteredFrame n) : Submodule ℝ (Fin n → ℝ) :=
  Submodule.span ℝ ({(fun _ => 1),F.w} : Set (Fin n → ℝ))

theorem projector_fixed_iff (F : CenteredFrame n) (v : Fin n → ℝ) :
    projector F *ᵥ v = v ↔ v ∈ carrier F := by
  rw [carrier,Submodule.mem_span_pair]
  constructor
  · intro h
    refine ⟨(∑ j, v j)/(n:ℝ),(∑ j, F.w j*v j)/F.s,?_⟩
    calc
      _ = projector F *ᵥ v := by
        funext i
        rw [projector_mulVec]
        simp only [Pi.add_apply,Pi.smul_apply,smul_eq_mul,mul_one]
        ring
      _ = v := h
  · rintro ⟨a,b,rfl⟩
    rw [Matrix.mulVec_add,Matrix.mulVec_smul,Matrix.mulVec_smul,projector_one,projector_w]

theorem projector_range (F : CenteredFrame n) (v : Fin n → ℝ) : projector F *ᵥ v ∈ carrier F := by
  rw [←projector_fixed_iff,Matrix.mulVec_mulVec,projector_idempotent]

end BornCalculus.General
