import BornCalculus.General.Trace

namespace BornCalculus.General
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0
variable {n : ℕ}

noncomputable def kappa (F : CenteredFrame n) (R : GDensity n F.s) (i : Fin n) : ℝ :=
  pairing R.val (parent F i)

theorem kappa_simplex (F : CenteredFrame n) (R : GDensity n F.s) :
    (∀ i, 0 ≤ kappa F R i) ∧ ∑ i, kappa F R i = 1 := by
  have h := frame_coordinate_transfer n F.s (size_positive F) F.positive
  constructor
  · intro i
    rw [kappa,←h.trace_pairing]
    exact trace_pairing_nonnegative _ _ ((h.positive _).mp R.property.1)
      ((h.positive _).mp (parent_positive F i))
  · simp only [kappa,pairing,←Matrix.trace_sum,←Matrix.mul_sum,parent_sum,Matrix.mul_one]
    exact R.property.2

theorem effect_statistics (F : CenteredFrame n) (R : GDensity n F.s) (S : Finset (Fin n)) :
    pairing R.val (effect F S) = ∑ i ∈ S, kappa F R i := by
  simp [effect,kappa,pairing,Matrix.mul_sum,Matrix.trace_sum]
theorem lens_statistics {L : Type*} [Fintype L] [DecidableEq L]
    (F : CenteredFrame n) (R : GDensity n F.s) (q : Fin n → L) (a : L) :
    pairing R.val (lens F q a) = ∑ i, if q i = a then kappa F R i else 0 := by
  rw [lens_effect,effect_statistics,Finset.sum_filter]
theorem encoded_statistics (F : CenteredFrame n) (p : Simplex n) (i : Fin n) :
    kappa F ⟨encoding F p,encoding_domain F p⟩ i = projectedSquare F p {i} := by
  rw [projected_square_trace,effect_singleton]; rfl

/-- The paper's orthonormal densities have the same n-point model. -/
theorem orth_n_point_model (F : CenteredFrame n) (R : Density) :
    (∀ i, 0 ≤ pairing R.val (toOrth n F.s (parent F i))) ∧
    (∑ i, pairing R.val (toOrth n F.s (parent F i))) = 1 ∧
    ∀ S : Finset (Fin n), pairing R.val (toOrth n F.s (effect F S)) =
      ∑ i ∈ S, pairing R.val (toOrth n F.s (parent F i)) := by
  have h := frame_coordinate_transfer n F.s (size_positive F) F.positive
  have hd : GIsDensity n F.s (fromOrth n F.s R.val) :=
    (h.density_domain _).mpr (by rw [h.inverse_right]; exact R.property)
  let Q : GDensity n F.s := ⟨fromOrth n F.s R.val,hd⟩
  have he (E : M2) : pairing R.val (toOrth n F.s E) = pairing Q.val E := by
    change pairing R.val (toOrth n F.s E) = pairing (fromOrth n F.s R.val) E
    rw [←h.trace_pairing (fromOrth n F.s R.val) E,h.inverse_right]
  simp_rw [he]
  exact ⟨(kappa_simplex F Q).1,(kappa_simplex F Q).2,effect_statistics F Q⟩

end BornCalculus.General
