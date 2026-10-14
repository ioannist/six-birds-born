import BornCalculus.B05Exact
import BornCalculus.B04Witness
import BornCalculus.QuadraticBounds

namespace BornCalculus
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0

structure RayEnsemble where
 weight : Fin 2 → ℝ
 ray : Fin 2 → ℝ
 nonnegative : ∀ a, 0 ≤ weight a
 normalized : (∑ a, weight a) = 1

noncomputable def ensembleDensity (E : RayEnsemble) : M2 :=
 ∑ a, E.weight a • chartDensity b04S (E.ray a)

noncomputable def b05Source (side : Fin 2) : RayEnsemble :=
 ⟨fun a => (b05WeightQ side a : ℝ), fun a => (b05RayQ side a : ℝ),
  fun a => by
   change (0 : ℝ) ≤ (b05WeightQ side a : ℝ)
   exact_mod_cast (b05_weightsQ side).1 a,
  by
   change (∑ a : Fin 2, (b05WeightQ side a : ℝ)) = 1
   exact_mod_cast (b05_weightsQ side).2⟩

noncomputable def b05Gate (t : ℝ) (i : Fin 32) : ℝ :=
 if b04Joint i = 0 then (1+t*b04W i)^2 else 0
noncomputable def b05FirstMass (t : ℝ) : ℝ :=
 (∑ i : Fin 32, b05Gate t i)/(32+b04S*t^2)
noncomputable def b05CompletionUpdate (t : ℝ) : Fin 32 → ℝ := b04Kᵀ *ᵥ b05Gate t
noncomputable def b05Read (t : ℝ) : ℝ :=
 ((b05MomentsQ 0 : ℝ)+(b05MomentsQ 1 : ℝ)*t+(b05MomentsQ 2 : ℝ)*t^2)/(32+b04S*t^2)
noncomputable def b05CompletionWord (t : ℝ) : ℝ :=
 b05FirstMass t*b05Read (b04Chart (b05CompletionUpdate t))
noncomputable def ensembleWord (E : RayEnsemble) : ℝ :=
 ∑ a, E.weight a*b05CompletionWord (E.ray a)
noncomputable def b05Post (side atom : Fin 2) : Fin 32 → ℝ :=
 fun i => (b05PostQ side atom i : ℝ)

private theorem b05_cast_linear (a lo hi : ℚ) :
 linearLower (a : ℝ) (lo : ℝ) (hi : ℝ) = (linearLowerQ a lo hi : ℝ) := by
 by_cases h : 0 ≤ a
 · have hr : (0 : ℝ) ≤ (a : ℝ) := by exact_mod_cast h
   simp [linearLower,linearLowerQ,h,hr]
 · have hr : ¬(0 : ℝ) ≤ (a : ℝ) := by exact_mod_cast h
   simp [linearLower,linearLowerQ,h,hr]

private theorem b05_cast_linearRoot (a lo hi : Fin 32 → ℚ) (i : Fin 32) :
 lowerLinearRoot (fun j => (a j : ℝ)) (fun j => (lo j : ℝ)) (fun j => (hi j : ℝ)) i =
   (lowerLinearRootQ a lo hi i : ℝ) := by
 by_cases h : 0 ≤ a i
 · have hr : (0 : ℝ) ≤ (a i : ℝ) := by exact_mod_cast h
   simp [lowerLinearRoot, lowerLinearRootQ, h, hr]
 · have hr : ¬(0 : ℝ) ≤ (a i : ℝ) := by exact_mod_cast h
   simp [lowerLinearRoot, lowerLinearRootQ, h, hr]

theorem b05_post_chart_bounds (e side : Fin 2) :
 (b05LowerQ e side : ℝ) ≤ b04Chart (b05Post e side) ∧
   b04Chart (b05Post e side) ≤ (b05UpperQ e side : ℝ) := by
 have hq := b05_root_squaresQ e side
 have hb : ∀ i, (0 : ℝ) ≤ (b05LoQ e side i : ℝ) ∧ 0 ≤ (b05HiQ e side i : ℝ) ∧
   (b05LoQ e side i : ℝ)^2 ≤ b05Post e side i ∧
   b05Post e side i ≤ (b05HiQ e side i : ℝ)^2 := by
   intro i
   dsimp [b05Post]
   exact_mod_cast hq.1 i
 have hs : (0 : ℝ) < ∑ i : Fin 32, (b05LoQ e side i : ℝ) := by exact_mod_cast hq.2
 have hl : (0 : ℝ) ≤ ∑ i : Fin 32, lowerLinearRoot
   (fun i => (32/b04S)*b04W i-(b05LowerQ e side : ℝ))
   (fun i => (b05LoQ e side i : ℝ)) (fun i => (b05HiQ e side i : ℝ)) i := by
   have he : (∑ i : Fin 32, lowerLinearRoot
     (fun i => (32/b04S)*b04W i-(b05LowerQ e side : ℝ))
     (fun i => (b05LoQ e side i : ℝ)) (fun i => (b05HiQ e side i : ℝ)) i) =
     (∑ i : Fin 32, lowerLinearRootQ
       (fun i => (32/b04SQ)*b04WQ i-b05LowerQ e side)
       (b05LoQ e side) (b05HiQ e side) i : ℚ) := by
     rw [Rat.cast_sum]
     apply Finset.sum_congr rfl
     intro i _
     simpa [b04W,b04S] using b05_cast_linearRoot
       (fun i => (32/b04SQ)*b04WQ i-b05LowerQ e side) (b05LoQ e side) (b05HiQ e side) i
   rw [he]
   exact_mod_cast b05_chart_lower_checkQ e side
 have hu : (0 : ℝ) ≤ ∑ i : Fin 32, lowerLinearRoot
   (fun i => (b05UpperQ e side : ℝ)-(32/b04S)*b04W i)
   (fun i => (b05LoQ e side i : ℝ)) (fun i => (b05HiQ e side i : ℝ)) i := by
   have he : (∑ i : Fin 32, lowerLinearRoot
     (fun i => (b05UpperQ e side : ℝ)-(32/b04S)*b04W i)
     (fun i => (b05LoQ e side i : ℝ)) (fun i => (b05HiQ e side i : ℝ)) i) =
     (∑ i : Fin 32, lowerLinearRootQ
       (fun i => b05UpperQ e side-(32/b04SQ)*b04WQ i)
       (b05LoQ e side) (b05HiQ e side) i : ℚ) := by
     rw [Rat.cast_sum]
     apply Finset.sum_congr rfl
     intro i _
     simpa [b04W,b04S] using b05_cast_linearRoot
       (fun i => b05UpperQ e side-(32/b04SQ)*b04WQ i) (b05LoQ e side) (b05HiQ e side) i
   rw [he]
   exact_mod_cast b05_chart_upper_checkQ e side
 exact rootChart_bounds b04W (b05Post e side)
   (fun i => (b05LoQ e side i : ℝ)) (fun i => (b05HiQ e side i : ℝ))
   b04S (b05LowerQ e side : ℝ) (b05UpperQ e side : ℝ) hb hs hl hu


theorem b05_mass_certificate (side atom : Fin 2) :
 b05FirstMass (b05RayQ side atom : ℝ) = (b05MassQ side atom : ℝ) := by
 have h := (b05_sourcesQ side atom).2.2
 have hc := congrArg (fun q : ℚ => (q : ℝ)) h
 simpa [b05FirstMass,b05Gate,b05GateQ,b04S,b04W,apply_ite] using hc.symm

theorem b05_update_certificate (side atom : Fin 2) :
 b05CompletionUpdate (b05RayQ side atom : ℝ) = b05Post side atom := by
 funext j
 have h := congrArg (fun p : Fin 32 → ℚ => (p j : ℝ)) (b05_post_stepQ side atom)
 simpa [b05CompletionUpdate,b05Gate,b05GateQ,b04K,b04W,b05Post,mulVec,dotProduct,
   transpose_apply,apply_ite] using h.symm

theorem b05_density_barycenter (side : Fin 2) :
 ensembleDensity (b05Source side) = fun i j => (b05BarycenterQ i j : ℝ) := by
 ext i j
 have h := congrArg (fun R : Matrix (Fin 2) (Fin 2) ℚ => (R i j : ℝ)) (b05_barycenterQ side)
 fin_cases i <;> fin_cases j <;>
   simpa [ensembleDensity,b05Source,chartDensity,b05ChartDensityQ,b04S,
     Matrix.sum_apply] using h

theorem b05_density_barycenters_equal :
 ensembleDensity (b05Source 0) = ensembleDensity (b05Source 1) := by
 rw [b05_density_barycenter,b05_density_barycenter]

theorem b05_read_bounds (side atom : Fin 2) :
 (b05ReadLowerQ side atom : ℝ) ≤ b05Read (b04Chart (b05Post side atom)) ∧
 b05Read (b04Chart (b05Post side atom)) ≤ (b05ReadUpperQ side atom : ℝ) := by
 have hx := b05_post_chart_bounds side atom
 have hq := b05_square_chart_checkQ side atom
 have hu : (b05UpperQ side atom : ℝ) < 0 := by exact_mod_cast hq.2.1
 have hsl : (b05SqLowerQ side atom : ℝ) = (b05UpperQ side atom : ℝ)^2 := by exact_mod_cast hq.2.2.1
 have hsu : (b05SqUpperQ side atom : ℝ) = (b05LowerQ side atom : ℝ)^2 := by exact_mod_cast hq.2.2.2
 have hlo : (b05SqLowerQ side atom : ℝ) ≤ (b04Chart (b05Post side atom))^2 := by
   rw [hsl]
   nlinarith
 have hhi : (b04Chart (b05Post side atom))^2 ≤ (b05SqUpperQ side atom : ℝ) := by
   rw [hsu]
   nlinarith
 have hl : (0:ℝ) ≤ (b05MomentsQ 0:ℝ)-32*(b05ReadLowerQ side atom:ℝ)+
   linearLower (b05MomentsQ 1:ℝ) (b05LowerQ side atom:ℝ) (b05UpperQ side atom:ℝ)+
   linearLower ((b05MomentsQ 2:ℝ)-b04S*(b05ReadLowerQ side atom:ℝ))
     (b05SqLowerQ side atom:ℝ) (b05SqUpperQ side atom:ℝ) := by
   have h := b05_read_lower_checkQ side atom
   have he := b05_cast_linear (b05MomentsQ 1) (b05LowerQ side atom) (b05UpperQ side atom)
   rw [he,show ((b05MomentsQ 2:ℝ)-b04S*(b05ReadLowerQ side atom:ℝ)) =
     ((b05MomentsQ 2-b04SQ*b05ReadLowerQ side atom:ℚ):ℝ) by simp [b04S],b05_cast_linear]
   exact_mod_cast h
 have hh : (0:ℝ) ≤ 32*(b05ReadUpperQ side atom:ℝ)-(b05MomentsQ 0:ℝ)+
   linearLower (-(b05MomentsQ 1:ℝ)) (b05LowerQ side atom:ℝ) (b05UpperQ side atom:ℝ)+
   linearLower (b04S*(b05ReadUpperQ side atom:ℝ)-(b05MomentsQ 2:ℝ))
     (b05SqLowerQ side atom:ℝ) (b05SqUpperQ side atom:ℝ) := by
   rw [show (-(b05MomentsQ 1:ℝ)) = ((-b05MomentsQ 1:ℚ):ℝ) by simp,b05_cast_linear,
     show b04S*(b05ReadUpperQ side atom:ℝ)-(b05MomentsQ 2:ℝ) =
       ((b04SQ*b05ReadUpperQ side atom-b05MomentsQ 2:ℚ):ℝ) by simp [b04S],b05_cast_linear]
   exact_mod_cast b05_read_upper_checkQ side atom
 exact quadratic_ratio_bounds b04S (b05MomentsQ 0:ℝ) (b05MomentsQ 1:ℝ)
   (b05MomentsQ 2:ℝ) (b04Chart (b05Post side atom)) _ _ _ _ _ _
   b04_s_positive hx.1 hx.2 hlo hhi hl hh

theorem b05_ensemble_word_bounds (side : Fin 2) :
 (∑ a : Fin 2, (b05WeightQ side a:ℝ)*(b05MassQ side a:ℝ)*(b05ReadLowerQ side a:ℝ)) ≤
 ensembleWord (b05Source side) ∧ ensembleWord (b05Source side) ≤
 (∑ a : Fin 2, (b05WeightQ side a:ℝ)*(b05MassQ side a:ℝ)*(b05ReadUpperQ side a:ℝ)) := by
 simp only [ensembleWord,b05Source,b05CompletionWord,b05_mass_certificate,
   b05_update_certificate]
 constructor <;> apply Finset.sum_le_sum
 all_goals
   intro a _
   have hw : (0:ℝ) ≤ (b05WeightQ side a:ℝ) := by exact_mod_cast (b05_weightsQ side).1 a
   have hm : (0:ℝ) < (b05MassQ side a:ℝ) := by exact_mod_cast (b05_sourcesQ side a).2.1
   have hb := b05_read_bounds side a
   first
   | simpa only [mul_assoc] using mul_le_mul_of_nonneg_left hb.1 (mul_nonneg hw hm.le)
   | simpa only [mul_assoc] using mul_le_mul_of_nonneg_left hb.2 (mul_nonneg hw hm.le)

theorem b05_completion_word_strict :
 ensembleWord (b05Source 0) < ensembleWord (b05Source 1) := by
 have h0 := (b05_ensemble_word_bounds 0).2
 have h1 := (b05_ensemble_word_bounds 1).1
 have hq : (∑ a : Fin 2, (b05WeightQ 0 a:ℝ)*(b05MassQ 0 a:ℝ)*(b05ReadUpperQ 0 a:ℝ)) <
   (∑ a : Fin 2, (b05WeightQ 1 a:ℝ)*(b05MassQ 1 a:ℝ)*(b05ReadLowerQ 1 a:ℝ)) := by
   exact_mod_cast b05_word_gapQ
 exact lt_of_le_of_lt h0 (lt_of_lt_of_le hq h1)

/-- The registered completion apparatus has no factor through density
barycenters on normalized two-atom ray ensembles. This is not the adopted
principal-root instrument. -/
theorem b05_completion_density_no_factor :
 ¬ ∃ f : M2 → ℝ, ∀ E : RayEnsemble, ensembleWord E = f (ensembleDensity E) := by
 exact fiber_split_no_factor ensembleDensity ensembleWord (b05Source 0) (b05Source 1)
   b05_density_barycenters_equal b05_completion_word_strict.ne

end BornCalculus
