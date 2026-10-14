import BornCalculus.B05Semantics
import BornCalculus.SmallMatrices

namespace BornCalculus
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0

noncomputable def b05Parent (i : Fin 32) : M2 :=
 !![1/32,b04W i/32;b04W i/b04S,(b04W i)^2/b04S]

noncomputable def b05LensEffect {m : ℕ} (q : Fin 32 → Fin m) (j : Fin m) : M2 :=
 ∑ i, if q i = j then b05Parent i else 0

theorem b05_parent_metric (i : Fin 32) :
 frameG 32 b04S * b05Parent i = Matrix.vecMulVec ![1,b04W i] ![1,b04W i] := by
 have hs := b04_s_positive.ne'
 ext a b
 fin_cases a <;> fin_cases b <;>
   simp [frameG,b05Parent,Matrix.vecMulVec,mul_apply,Fin.sum_univ_two] <;>
   field_simp [hs]

theorem b05_parent_positive (i : Fin 32) : GPositive 32 b04S (b05Parent i) := by
 rw [GPositive,b05_parent_metric]
 simpa only [star_trivial] using Matrix.posSemidef_vecMulVec_self_star
   (![1,b04W i] : Fin 2 → ℝ)

theorem b05_parent_sum : (∑ i : Fin 32, b05Parent i) = 1 := by
 have hs := b04_s_positive.ne'
 ext a b
 fin_cases a <;> fin_cases b <;>
   norm_num [b05Parent,Matrix.sum_apply,←Finset.sum_div,b05_frame_real.1,b05_frame_real.2,hs]

theorem b05_lens_positive {m : ℕ} (q : Fin 32 → Fin m) (j : Fin m) :
 GPositive 32 b04S (b05LensEffect q j) := by
 unfold GPositive b05LensEffect
 rw [Matrix.mul_sum]
 apply Matrix.posSemidef_sum Finset.univ
 intro i _
 by_cases h : q i = j
 · simpa only [if_pos h] using b05_parent_positive i
 · simp only [if_neg h,Matrix.mul_zero]
   exact Matrix.PosSemidef.zero

theorem b05_lens_sum {m : ℕ} (q : Fin 32 → Fin m) :
 (∑ j, b05LensEffect q j) = 1 := by
 classical
 unfold b05LensEffect
 rw [Finset.sum_comm]
 simpa [eq_comm] using b05_parent_sum

theorem b05_lens_domain {m : ℕ} (q : Fin 32 → Fin m) (j : Fin m) :
 GIsEffect 32 b04S (b05LensEffect q j) :=
 complete_g_effect_domains 32 b04S (b05LensEffect q) (b05_lens_positive q) (b05_lens_sum q) j

theorem b05_parent_pairing (t : ℝ) (i : Fin 32) :
 pairing (chartDensity b04S t) (b05Parent i) =
   (1+t*b04W i)^2/(32+b04S*t^2) := by
 have hs := b04_s_positive.ne'
 have hd := (b05_ray_den_positive t).ne'
 simp [pairing,chartDensity,b05Parent,trace,Fin.sum_univ_two]
 field_simp [hs,hd]

theorem b05_lens_pairing {m : ℕ} (q : Fin 32 → Fin m) (j : Fin m) (t : ℝ) :
 pairing (chartDensity b04S t) (b05LensEffect q j) =
   ∑ i, if q i = j then (b05RayPreparation t).val i else 0 := by
 unfold pairing b05LensEffect
 rw [Matrix.mul_sum,Matrix.trace_sum]
 apply Finset.sum_congr rfl
 intro i _
 by_cases h : q i = j
 · simpa only [if_pos h,b05RayPreparation] using b05_parent_pairing t i
 · simp [h]

theorem b05_instantaneous_pairing (t : ℝ) :
 b05Read t = pairing (chartDensity b04S t) (b05LensEffect b04Joint 0) := by
 rw [b05_read_eq_gate_mass,b05_lens_pairing,b05FirstMass]
 rw [Finset.sum_div]
 apply Finset.sum_congr rfl
 intro i _
 by_cases h : b04Joint i = 0 <;> simp [b05Gate,b05RayPreparation,h]

theorem ensemble_instantaneous_pairing {m : ℕ} (q : Fin 32 → Fin m) (j : Fin m)
 (E : RayEnsemble) :
 (∑ a, E.weight a*pairing (chartDensity b04S (E.ray a)) (b05LensEffect q j)) =
 pairing (ensembleDensity E) (b05LensEffect q j) := by
 unfold pairing ensembleDensity
 rw [Matrix.sum_mul,Matrix.trace_sum]
 apply Finset.sum_congr rfl
 intro a _
 simp only [Matrix.smul_mul,Matrix.trace_smul,smul_eq_mul]

theorem b05_all_lens_first_reads_equal {m : ℕ} (q : Fin 32 → Fin m) (j : Fin m) :
 (∑ a, (b05Source 0).weight a*pairing (chartDensity b04S ((b05Source 0).ray a)) (b05LensEffect q j)) =
 (∑ a, (b05Source 1).weight a*pairing (chartDensity b04S ((b05Source 1).ray a)) (b05LensEffect q j)) := by
 rw [ensemble_instantaneous_pairing,ensemble_instantaneous_pairing,b05_density_barycenters_equal]


theorem b05_lens_read_sum {m : ℕ} (q : Fin 32 → Fin m) (t : ℝ) :
 (∑ j, pairing (chartDensity b04S t) (b05LensEffect q j)) = 1 := by
 simp only [pairing]
 rw [←Matrix.trace_sum,←Matrix.mul_sum,b05_lens_sum,Matrix.mul_one]
 exact (chartDensity_domain b04S t b04_s_positive).2

noncomputable def b05CompletionAtom {m : ℕ} (q : Fin 32 → Fin m) (g j : Fin m) (t : ℝ) : ℝ :=
 pairing (chartDensity b04S t) (b05LensEffect q g) *
 pairing (chartDensity b04S (b04Chart (b04Kᵀ *ᵥ
   (fun i => if q i = g then (1+t*b04W i)^2 else 0)))) (b05LensEffect q j)

theorem b05_completion_test_sum {m : ℕ} (q : Fin 32 → Fin m) (t : ℝ) :
 (∑ g, ∑ j, b05CompletionAtom q g j t) = 1 := by
 simp only [b05CompletionAtom,←Finset.mul_sum,b05_lens_read_sum,mul_one]

theorem b05_completion_atom_nonnegative {m : ℕ} (q : Fin 32 → Fin m) (g j : Fin m) (t : ℝ) :
 0 ≤ b05CompletionAtom q g j t := by
 have hp (k : Fin m) (x : ℝ) : 0 ≤ pairing (chartDensity b04S x) (b05LensEffect q k) := by
   rw [b05_lens_pairing]
   apply Finset.sum_nonneg
   intro i _
   by_cases h : q i = k
   · simpa only [if_pos h] using (b05RayPreparation x).property.1 i
   · simp only [if_neg h,le_refl]
 exact mul_nonneg (hp g t) (hp j _)

theorem b05_registered_completion_atom (t : ℝ) :
 b05CompletionWord t = b05CompletionAtom b04Joint 0 0 t := by
 rw [b05CompletionWord,←b05_read_eq_gate_mass t,b05_instantaneous_pairing,
   b05_instantaneous_pairing]
 rfl

end BornCalculus
