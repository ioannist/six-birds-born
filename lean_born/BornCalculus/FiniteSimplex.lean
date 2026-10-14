import BornCalculus.Valuations
namespace BornCalculus
open Matrix
open scoped MatrixOrder BigOperators
set_option maxHeartbeats 0

structure FiniteSimplexModel (N : ℕ) where
 response : Fin N → Valuation
 weight : Density → Fin N → ℝ
 weight_nonnegative : ∀ R i, 0 ≤ weight R i
 weight_normalized : ∀ R, ∑ i, weight R i = 1
 reproduces : ∀ (R : Density) (E : Effect),
   ∑ i, weight R i * (response i).value E = pairing R.val E.val

theorem density_overlap_le_one (Q R : Density) : pairing Q.val R.val ≤ 1 := by
 have h := trace_pairing_nonnegative Q.val (1-R.val) Q.property.1 (density_is_effect R).2
 simp only [pairing,Matrix.mul_sub,Matrix.mul_one,Matrix.trace_sub,Q.property.2] at h
 change pairing Q.val R.val ≤ 1
 dsimp [pairing]
 linarith

theorem pure_overlap_one (R Q : Density) (hp : R.val*R.val=R.val)
 (h : pairing Q.val R.val=1) : Q=R := by
 have hr : pairing R.val R.val=1 := by simpa [pairing,hp] using R.property.2
 have hq := density_overlap_le_one Q Q
 have hs : (Q.val-R.val)ᴴ=Q.val-R.val := Q.property.1.isHermitian.sub R.property.1.isHermitian
 have hn := (Matrix.posSemidef_conjTranspose_mul_self (Q.val-R.val)).trace_nonneg
 have hz : trace ((Q.val-R.val)ᴴ*(Q.val-R.val))=0 := by
   rw [hs] at hn ⊢
   simp only [Matrix.sub_mul,Matrix.mul_sub,Matrix.trace_sub] at hn ⊢
   have hc := Matrix.trace_mul_comm R.val Q.val
   dsimp [pairing] at hr h hq
   linarith
 apply Subtype.ext
 exact sub_eq_zero.mp (Matrix.trace_conjTranspose_mul_self_eq_zero_iff.mp hz)

/-- Pure-state extremality, with arbitrary finite nonnegative convex weights. -/
theorem pure_state_extremality {ι : Type*} [Fintype ι]
 (R : Density) (Q : ι → Density) (a : ι → ℝ)
 (ha : ∀ i, 0 ≤ a i) (hn : ∑ i, a i=1)
 (hp : R.val*R.val=R.val) (hm : R.val=∑ i, a i • (Q i).val) :
 ∀ i, 0 < a i → Q i=R := by
 classical
 have hr : pairing R.val R.val=1 := by simpa [pairing,hp] using R.property.2
 have he : ∑ i, a i * pairing (Q i).val R.val=1 := by
   simpa [pairing,hm,Matrix.sum_mul,Matrix.trace_sum,Matrix.smul_mul,Matrix.trace_smul] using hr
 have hz : ∑ i, a i * (1-pairing (Q i).val R.val)=0 := by
   simp only [mul_sub,mul_one,Finset.sum_sub_distrib,hn,he,sub_self]
 have hall := (Finset.sum_eq_zero_iff_of_nonneg (fun i _ =>
   mul_nonneg (ha i) (sub_nonneg.mpr (density_overlap_le_one (Q i) R)))).mp hz
 intro i hi
 have hh := hall i (Finset.mem_univ i)
 have hpi : pairing (Q i).val R.val=1 := by
   have hzero := (mul_eq_zero.mp hh).resolve_left hi.ne'
   linarith
 exact pure_overlap_one R (Q i) hp hpi

noncomputable def pureMatrix (t : ℝ) : M2 := (1+t^2)⁻¹ • !![1,t;t,t^2]
theorem pureMatrix_density (t : ℝ) : IsDensity (pureMatrix t) := by
 have hd : 0 < 1+t^2 := by positivity
 let A : M2 := !![1,0;t,0]
 have he : !![(1:ℝ),t;t,t^2]=A*Aᴴ := by
   ext i j; fin_cases i <;> fin_cases j <;>
     simp [A,mul_apply,vecMul,dotProduct,conjTranspose_apply,Fin.sum_univ_two,pow_two]
 refine ⟨?_,?_⟩
 · change ((1+t^2)⁻¹ • (!![1,t;t,t^2] : M2)).PosSemidef
   rw [he]
   exact (Matrix.posSemidef_self_mul_conjTranspose A).smul (by positivity)
 · simp [pureMatrix,trace,Fin.sum_univ_two]
   field_simp
noncomputable def pureDensity (t : ℝ) : Density := ⟨pureMatrix t,pureMatrix_density t⟩
theorem pureDensity_projector (t : ℝ) : (pureDensity t).val*(pureDensity t).val=(pureDensity t).val := by
 have hd : 1+t^2≠0 := by positivity
 ext i j; fin_cases i <;> fin_cases j <;>
   simp [pureDensity,pureMatrix,mul_apply,vecMul,dotProduct,Fin.sum_univ_two] <;>
   field_simp <;> ring

theorem pureDensity_injective : Function.Injective pureDensity := by
 intro t u h
 have h0 := congrArg (fun R : Density => R.val 0 0) h
 have h1 := congrArg (fun R : Density => R.val 0 1) h
 simp [pureDensity,pureMatrix] at h0 h1
 have hd : (1+t^2)⁻¹≠0 := inv_ne_zero (by positivity)
 rw [←h0] at h1
 exact (mul_left_cancel₀ hd h1)

noncomputable def vertexDensity {N : ℕ} (M : FiniteSimplexModel N) (i : Fin N) : Density :=
 Classical.choose (full_interval_trace_unique (M.response i))
theorem vertexDensity_represents {N : ℕ} (M : FiniteSimplexModel N) (i : Fin N) (E : Effect) :
 (M.response i).value E=pairing (vertexDensity M i).val E.val :=
 (Classical.choose_spec (full_interval_trace_unique (M.response i))).1 E

theorem finite_simplex_matrix_realization {N : ℕ} (M : FiniteSimplexModel N) (R : Density) :
 R.val=∑ i, M.weight R i • (vertexDensity M i).val := by
 let Q : Density := ⟨∑ i, M.weight R i • (vertexDensity M i).val,
   Matrix.posSemidef_sum _ (fun i _ => (vertexDensity M i).property.1.smul (M.weight_nonnegative R i)), by
     simp [Matrix.trace_sum,Matrix.trace_smul,(vertexDensity M _).property.2,M.weight_normalized]⟩
 have hq : ∀ E : Effect, pairing Q.val E.val=pairing R.val E.val := by
   intro E
   have hh := M.reproduces R E
   simp only [vertexDensity_represents] at hh
   simpa [Q,pairing,Matrix.sum_mul,Matrix.trace_sum,Matrix.smul_mul,Matrix.trace_smul] using hh
 exact congrArg Subtype.val (effects_separate_densities R Q (fun E => (hq E).symm))

theorem no_finite_simplex_model (N : ℕ) (M : FiniteSimplexModel N) : False := by
 classical
 have hx : ∀ j : Fin (N+1), ∃ i : Fin N, vertexDensity M i=pureDensity (j : ℝ) := by
   intro j
   have hn := M.weight_normalized (pureDensity (j : ℝ))
   have hpos : 0 < ∑ i, M.weight (pureDensity (j : ℝ)) i := by rw [hn]; norm_num
   obtain ⟨i,_,hi⟩ := (Finset.sum_pos_iff_of_nonneg (fun i _ => M.weight_nonnegative _ i)).mp hpos
   exact ⟨i,pure_state_extremality _ (vertexDensity M) (M.weight _) (M.weight_nonnegative _)
     hn (pureDensity_projector _) (finite_simplex_matrix_realization M _) i hi⟩
 choose f hf using hx
 have hinj : Function.Injective f := by
   intro i j hij
   have hh : pureDensity (i : ℝ)=pureDensity (j : ℝ) := (hf i).symm.trans (hij ▸ hf j)
   have he := pureDensity_injective hh
   apply Fin.ext
   exact_mod_cast he
 have hc := Fintype.card_le_of_injective f hinj
 simp only [Fintype.card_fin] at hc
 omega
end BornCalculus
