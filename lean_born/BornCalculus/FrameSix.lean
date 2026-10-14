import BornCalculus.Frame
namespace BornCalculus
open Matrix
open scoped MatrixOrder BigOperators
set_option maxHeartbeats 0

structure SixStateGFrameLaws (g₀ g₁ : ℝ) : Prop where
 density : ∀ i : Fin 6, GIsDensity g₀ g₁ (fromOrth g₀ g₁ (sixState i))
 effect : ∀ i : Fin 6, GIsEffect g₀ g₁ (fromOrth g₀ g₁ (sixState i))
 projector : ∀ i : Fin 6, fromOrth g₀ g₁ (sixState i)*fromOrth g₀ g₁ (sixState i)=fromOrth g₀ g₁ (sixState i)
 pairs : ∀ i : Fin 3,
   (1/2 : ℝ) • (fromOrth g₀ g₁ (sharp i)+fromOrth g₀ g₁ (1-sharp i))=fromOrth g₀ g₁ halfUnit
 positive_trine : (1/3 : ℝ) • (∑ i : Fin 3, fromOrth g₀ g₁ (sharp i))=fromOrth g₀ g₁ halfUnit
 negative_trine : (1/3 : ℝ) • (∑ i : Fin 3, fromOrth g₀ g₁ (1-sharp i))=fromOrth g₀ g₁ halfUnit
 table : ∀ (i : Fin 6) (j : Fin 3),
   pairing (fromOrth g₀ g₁ (sixState i)) (fromOrth g₀ g₁ (sharp j))=sixTable i j

theorem six_state_g_transfer (g₀ g₁ : ℝ) (h₀ : 0<g₀) (h₁ : 0<g₁) : SixStateGFrameLaws g₀ g₁ := by
 have h := frame_coordinate_transfer g₀ g₁ h₀ h₁
 have hinj : Function.Injective (toOrth g₀ g₁) := by
   intro A B he; simpa [h.inverse_left] using congrArg (fromOrth g₀ g₁) he
 refine ⟨?_,?_,?_,?_,?_,?_,?_⟩
 · intro i
   rw [h.density_domain,h.inverse_right]
   exact six_states_density_and_projector.density i
 · intro i
   rw [h.effect_domain,h.inverse_right]
   have hd := six_states_density_and_projector.density i
   have hp := six_states_density_and_projector.projector i
   refine ⟨hd.1,?_⟩
   apply real_projector_psd
   · simpa [Matrix.conjTranspose_eq_transpose_of_trivial] using hd.1.isHermitian.eq
   · noncomm_ring [hp]
 · intro i
   apply hinj
   simp only [h.multiplication,h.inverse_right,six_states_density_and_projector.projector]
 · intro i
   apply hinj
   simp only [h.scalar,h.addition,h.inverse_right]
   exact six_state_five_mixtures.pairs i
 · apply hinj
   simp only [Fin.sum_univ_three,h.scalar,h.addition,h.inverse_right]
   exact six_state_five_mixtures.positive_trine
 · apply hinj
   simp only [Fin.sum_univ_three,h.scalar,h.addition,h.inverse_right]
   exact six_state_five_mixtures.negative_trine
 · intro i j
   rw [←h.trace_pairing,h.inverse_right,h.inverse_right]
   exact six_state_probability_table i j
end BornCalculus
