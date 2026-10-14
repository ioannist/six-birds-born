import BornCalculus.General.OrthImage
import BornCalculus.General.Statistics
import BornCalculus.General.NonDensity

namespace BornCalculus.General
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0
variable {n : ℕ}

/-- Part 1 of thm:inherited and all parts of prop:trace, in the paper's frame.
    The geometric encoder and compression bridges are proved in Encoder/Basis. -/
theorem carrier_and_trace {L : Type*} [Fintype L] [DecidableEq L]
    (F : CenteredFrame n) (q : Fin n → L) :
    (∀ p : Simplex n, coefficients F p ≠ 0 ∧ IsDensity (toOrth n F.s (encoding F p)) ∧
      toOrth n F.s (encoding F p)*toOrth n F.s (encoding F p) = toOrth n F.s (encoding F p)) ∧
    (∀ a : L, IsEffect (toOrth n F.s (lens F q a))) ∧
    (∑ a : L, toOrth n F.s (lens F q a)) = 1 ∧
    (∀ S : Finset (Fin n), IsEffect (toOrth n F.s (effect F S))) ∧
    (∀ p : Simplex n, ∀ S : Finset (Fin n), projectedSquare F p S =
      pairing (toOrth n F.s (encoding F p)) (toOrth n F.s (effect F S))) := by
  have h := frame_coordinate_transfer n F.s (size_positive F) F.positive
  refine ⟨?_,?_,?_,?_,orth_projected_square_trace F⟩
  · intro p
    refine ⟨coefficients_ne_zero F p,(h.density_domain _).mp (encoding_domain F p),?_⟩
    rw [←h.multiplication,encoding_pure]
  · intro a; exact (h.effect_domain _).mp (lens_domain F q a)
  · have he : (∑ a : L, toOrth n F.s (lens F q a)) = toOrth n F.s (∑ a : L, lens F q a) := by
      simp [toOrth,Matrix.mul_sum,Matrix.sum_mul]
    rw [he,lens_sum,h.unit]
  · intro S; exact (h.effect_domain _).mp (effect_domain F S)

theorem orth_lens_statistics {L : Type*} [Fintype L] [DecidableEq L]
    (F : CenteredFrame n) (R : Density) (q : Fin n → L) (a : L) :
    pairing R.val (toOrth n F.s (lens F q a)) =
      ∑ i, if q i = a then pairing R.val (toOrth n F.s (parent F i)) else 0 := by
  rw [lens_effect,(orth_n_point_model F R).2.2,Finset.sum_filter]

end BornCalculus.General
