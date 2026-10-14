import BornCalculus.Instruments
import BornCalculus.SixStates
namespace BornCalculus
open Matrix
open scoped MatrixOrder BigOperators
set_option maxHeartbeats 0

theorem valuation_zero (v : Valuation) : v.value zeroEffect = 0 := by
 have h := v.additive zeroEffect zeroEffect zeroEffect (by simp [Matrix.vecMul, dotProduct,zeroEffect])
 linarith

theorem valuation_mono (v : Valuation) (E F : Effect)
 (h : (F.val - E.val).PosSemidef) : v.value E ≤ v.value F := by
 let D : Effect := ⟨F.val - E.val, h, by
   have hh := F.property.2.add E.property.1
   convert hh using 1 <;> module⟩
 have hh := v.additive E D F (by dsimp [Matrix.vecMul, dotProduct,D]; module)
 have hd := v.nonnegative D
 linarith

theorem valuation_le_one (v : Valuation) (E : Effect) : v.value E ≤ 1 := by
 simpa [Matrix.vecMul, dotProduct,v.normalized] using valuation_mono v E unitEffect E.property.2

theorem scaled_mono (v : Valuation) (E : Effect) (a b : ℝ)
 (ha : 0 ≤ a) (hb : 0 ≤ b) (ha1 : a ≤ 1) (hb1 : b ≤ 1) (hab : a ≤ b) :
 v.value (scaleEffect a ha ha1 E) ≤ v.value (scaleEffect b hb hb1 E) := by
 apply valuation_mono
 change (b • E.val - a • E.val).PosSemidef
 convert E.property.1.smul (sub_nonneg.mpr hab) using 1 <;> module

private theorem valuation_nat_fraction (v : Valuation) (E : Effect)
 (d : ℕ) (hd : 0 < d) : ∀ n : ℕ, n ≤ d →
 ∀ (h0 : 0 ≤ (n : ℝ) / d) (h1 : (n : ℝ) / d ≤ 1),
 v.value (scaleEffect ((n : ℝ) / d) h0 h1 E) =
 (n : ℝ) * v.value (scaleEffect ((1 : ℝ) / d) (by positivity)
   (by exact (div_le_one (by positivity)).mpr (by exact_mod_cast hd)) E) := by
 intro n
 induction n with
 | zero =>
   intro hn h0 h1
   have he : scaleEffect ((↑(0 : ℕ) : ℝ) / d) h0 h1 E = zeroEffect := by
     apply Subtype.ext; simp [Matrix.vecMul, dotProduct,scaleEffect, zeroEffect]
   rw [he, valuation_zero]; simp
 | succ n ih =>
   intro hn h0 h1
   have hn' : n ≤ d := (Nat.le_succ n).trans hn
   have hn0 : 0 ≤ (n : ℝ) / d := by positivity
   have hn1 : (n : ℝ) / d ≤ 1 := (div_le_one (by positivity)).mpr (by exact_mod_cast hn')
   have hd1 : (1 : ℝ) / d ≤ 1 := (div_le_one (by positivity)).mpr (by exact_mod_cast hd)
   have hh := v.additive (scaleEffect ((n : ℝ) / d) hn0 hn1 E)
     (scaleEffect ((1 : ℝ) / d) (by positivity) hd1 E)
     (scaleEffect ((n.succ : ℝ) / d) h0 h1 E) (by
       dsimp [Matrix.vecMul, dotProduct,scaleEffect]; rw [Nat.cast_succ, add_div, add_smul])
   rw [hh, ih hn' hn0 hn1]
   simp only [Nat.cast_add, Nat.cast_one]
   ring

private theorem valuation_nat_fraction_value (v : Valuation) (E : Effect)
 (d n : ℕ) (hd : 0 < d) (hn : n ≤ d)
 (h0 : 0 ≤ (n : ℝ) / d) (h1 : (n : ℝ) / d ≤ 1) :
 v.value (scaleEffect ((n : ℝ) / d) h0 h1 E) = ((n : ℝ) / d) * v.value E := by
 have hd0 : (d : ℝ) ≠ 0 := by exact_mod_cast hd.ne'
 have hdd := valuation_nat_fraction v E d hd d le_rfl (by positivity) (by simp [Matrix.vecMul, dotProduct,hd0])
 have he : scaleEffect ((d : ℝ) / d) (by positivity) (by simp [Matrix.vecMul, dotProduct,hd0]) E = E := by
   apply Subtype.ext; simp [Matrix.vecMul, dotProduct,scaleEffect, hd0]
 rw [he] at hdd
 rw [valuation_nat_fraction v E d hd n hn h0 h1]
 rw [hdd]
 field_simp
 <;> ring

private theorem valuation_rat_scale (v : Valuation) (E : Effect) (q : ℚ)
 (h0 : 0 ≤ (q : ℝ)) (h1 : (q : ℝ) ≤ 1) :
 v.value (scaleEffect (q : ℝ) h0 h1 E) = (q : ℝ) * v.value E := by
 have hq0 : 0 ≤ q := by exact_mod_cast h0
 have hnum : 0 ≤ q.num := Rat.num_nonneg.mpr hq0
 have hq : (q : ℝ) = (q.num.toNat : ℝ) / q.den := by
   have hh : (q.num.toNat : ℝ) = (q.num : ℝ) := by
     exact_mod_cast Int.toNat_of_nonneg hnum
   rw [hh]
   exact Rat.cast_def q
 have hn : q.num.toNat ≤ q.den := by
   have hden : (0 : ℝ) < q.den := by exact_mod_cast q.pos
   rw [hq, div_le_one hden] at h1
   exact_mod_cast h1
 have h00 : 0 ≤ (q.num.toNat : ℝ) / q.den := by positivity
 have h11 : (q.num.toNat : ℝ) / q.den ≤ 1 := by simpa only [← hq] using h1
 have hs : scaleEffect (q : ℝ) h0 h1 E = scaleEffect ((q.num.toNat : ℝ) / q.den) h00 h11 E := by
   apply Subtype.ext; dsimp [Matrix.vecMul, dotProduct,scaleEffect]; rw [hq]
 rw [hs, valuation_nat_fraction_value v E q.den q.num.toNat q.pos hn h00 h11, ← hq]

theorem valuation_scale (v : Valuation) (E : Effect) (t : ℝ)
 (ht₀ : 0 ≤ t) (ht₁ : t ≤ 1) :
 v.value (scaleEffect t ht₀ ht₁ E) = t * v.value E := by
 have hV := v.nonnegative E
 have hb := scaled_mono v E t 1 ht₀ (by norm_num) ht₁ (by norm_num) ht₁
 have he : scaleEffect 1 (by norm_num) (by norm_num) E = E := by
   apply Subtype.ext; simp [Matrix.vecMul, dotProduct,scaleEffect]
 rw [he] at hb
 have hv0 := v.nonnegative (scaleEffect t ht₀ ht₁ E)
 by_cases hz : v.value E = 0
 · rw [hz] at hb ⊢; nlinarith
 have hpos : 0 < v.value E := lt_of_le_of_ne hV (Ne.symm hz)
 apply le_antisymm
 · by_contra hh
   have hh' : t < v.value (scaleEffect t ht₀ ht₁ E) / v.value E :=
     (lt_div_iff₀ hpos).mpr (lt_of_not_ge hh)
   obtain ⟨q, hq0, hq1⟩ := exists_rat_btwn hh'
   have q0 : 0 ≤ (q : ℝ) := ht₀.trans hq0.le
   have q1 : (q : ℝ) ≤ 1 := hq1.le.trans ((div_le_one hpos).mpr hb)
   have hm := scaled_mono v E t q ht₀ q0 ht₁ q1 hq0.le
   rw [valuation_rat_scale v E q q0 q1] at hm
   have hq' := (lt_div_iff₀ hpos).mp hq1
   linarith
 · by_contra hh
   have hh' : v.value (scaleEffect t ht₀ ht₁ E) / v.value E < t :=
     (div_lt_iff₀ hpos).mpr (lt_of_not_ge hh)
   obtain ⟨q, hq0, hq1⟩ := exists_rat_btwn hh'
   have q0 : 0 ≤ (q : ℝ) := (div_nonneg hv0 hV).trans hq0.le
   have q1 : (q : ℝ) ≤ 1 := hq1.le.trans ht₁
   have hm := scaled_mono v E q t q0 ht₀ q1 ht₁ hq1.le
   rw [valuation_rat_scale v E q q0 q1] at hm
   have hq' := (div_lt_iff₀ hpos).mp hq0
   linarith



theorem psd_scale_to_effect (X : M2) (hX : X.PosSemidef) :
 ∃ c : ℝ, 0 < c ∧ IsEffect (c⁻¹ • X) := by
 let c : ℝ := Matrix.trace X + 1
 have hc : 0 < c := by dsimp [Matrix.vecMul, dotProduct,c]; have := hX.trace_nonneg; linarith
 let J : M2 := !![0,-1;1,0]
 have hs : X 1 0 = X 0 1 := by
   have h := congrArg (fun A : M2 => A 0 1) hX.isHermitian
   simpa [Matrix.vecMul, dotProduct,conjTranspose_apply] using h
 have he : (trace X) • (1 : M2) - X = J*X*Jᴴ := by
   ext i j; fin_cases i <;> fin_cases j <;>
     simp [Matrix.vecMul, dotProduct,J,trace,mul_apply,conjTranspose_apply,Fin.sum_univ_two,hs] <;> ring
 have hb : (c • (1 : M2) - X).PosSemidef := by
   have hh := (hX.mul_mul_conjTranspose_same J).add Matrix.PosSemidef.one
   rw [←he] at hh
   convert hh using 1 <;> dsimp [Matrix.vecMul, dotProduct,c] <;> module
 refine ⟨c, hc, hX.smul (inv_nonneg.mpr hc.le), ?_⟩
 have hh := hb.smul (inv_nonneg.mpr hc.le)
 convert hh using 1
 simp [Matrix.vecMul, dotProduct,smul_sub, smul_smul, hc.ne']

noncomputable def coneScale (X : M2) (hX : X.PosSemidef) : ℝ :=
 Classical.choose (psd_scale_to_effect X hX)
theorem coneScale_pos (X : M2) (hX : X.PosSemidef) : 0 < coneScale X hX :=
 (Classical.choose_spec (psd_scale_to_effect X hX)).1
noncomputable def coneEffect (X : M2) (hX : X.PosSemidef) : Effect :=
 ⟨(coneScale X hX)⁻¹ • X, (Classical.choose_spec (psd_scale_to_effect X hX)).2⟩
noncomputable def coneValue (v : Valuation) (X : M2) (hX : X.PosSemidef) : ℝ :=
 coneScale X hX * v.value (coneEffect X hX)

theorem cone_scale_independent (v : Valuation) (X : M2) (hX : X.PosSemidef)
 (a b : ℝ) (ha : 0 < a) (hb : 0 < b)
 (hA : IsEffect (a⁻¹ • X)) (hB : IsEffect (b⁻¹ • X)) :
 a * v.value ⟨a⁻¹ • X,hA⟩ = b * v.value ⟨b⁻¹ • X,hB⟩ := by
 have step : ∀ a b : ℝ, ∀ (ha : 0 < a) (hb : 0 < b), a ≤ b →
   ∀ (hA : IsEffect (a⁻¹ • X)) (hB : IsEffect (b⁻¹ • X)),
   a * v.value ⟨a⁻¹ • X,hA⟩ = b * v.value ⟨b⁻¹ • X,hB⟩ := by
   intro a b ha hb hab hA hB
   have hr0 : 0 ≤ a / b := by positivity
   have hr1 : a / b ≤ 1 := (div_le_one hb).mpr hab
   have he : scaleEffect (a/b) hr0 hr1 ⟨a⁻¹ • X,hA⟩ = ⟨b⁻¹ • X,hB⟩ := by
     apply Subtype.ext
     dsimp [Matrix.vecMul, dotProduct,scaleEffect]
     rw [smul_smul]
     congr 1
     field_simp
   have hh := valuation_scale v ⟨a⁻¹ • X,hA⟩ (a/b) hr0 hr1
   rw [he] at hh
   rw [hh]; field_simp
 rcases le_total a b with hab | hba
 · exact step a b ha hb hab hA hB
 · exact (step b a hb ha hba hB hA).symm

theorem cone_at_scale (v : Valuation) (X : M2) (hX : X.PosSemidef)
 (c : ℝ) (hc : 0 < c) (hE : IsEffect (c⁻¹ • X)) :
 coneValue v X hX = c * v.value ⟨c⁻¹ • X,hE⟩ :=
 cone_scale_independent v X hX _ c (coneScale_pos X hX) hc (coneEffect X hX).property hE

theorem cone_on_effect (v : Valuation) (E : Effect) :
 coneValue v E.val E.property.1 = v.value E := by
 have hE : IsEffect ((1 : ℝ)⁻¹ • E.val) := by simpa using E.property
 have hh := cone_at_scale v E.val E.property.1 1 (by norm_num) hE
 simpa using hh

theorem cone_nonnegative (v : Valuation) (X : M2) (hX : X.PosSemidef) :
 0 ≤ coneValue v X hX :=
 mul_nonneg (coneScale_pos X hX).le (v.nonnegative _)

theorem cone_add (v : Valuation) (X Y : M2) (hX : X.PosSemidef) (hY : Y.PosSemidef) :
 coneValue v (X+Y) (hX.add hY) = coneValue v X hX + coneValue v Y hY := by
 obtain ⟨c,hc,hZ⟩ := psd_scale_to_effect (X+Y) (hX.add hY)
 have hA : IsEffect (c⁻¹ • X) := ⟨hX.smul (by positivity), by
   have hh := hZ.2.add (hY.smul (by positivity : 0 ≤ c⁻¹))
   convert hh using 1 <;> module⟩
 have hB : IsEffect (c⁻¹ • Y) := ⟨hY.smul (by positivity), by
   have hh := hZ.2.add (hX.smul (by positivity : 0 ≤ c⁻¹))
   convert hh using 1 <;> module⟩
 rw [cone_at_scale v _ _ c hc hZ, cone_at_scale v _ _ c hc hA,
   cone_at_scale v _ _ c hc hB]
 rw [v.additive ⟨_,hA⟩ ⟨_,hB⟩ ⟨_,hZ⟩ (by dsimp; module)]
 ring

theorem cone_smul (v : Valuation) (X : M2) (hX : X.PosSemidef) (t : ℝ) (ht : 0 ≤ t) :
 coneValue v (t • X) (hX.smul ht) = t * coneValue v X hX := by
 by_cases hz : t = 0
 · subst t
   have hh := cone_on_effect v zeroEffect
   rw [valuation_zero] at hh
   simpa only [zeroEffect,zero_smul,zero_mul] using hh

 have hp : 0 < t := lt_of_le_of_ne ht (Ne.symm hz)
 let c := coneScale X hX
 have hc : 0 < c := coneScale_pos X hX
 have heq : (t*c)⁻¹ • (t • X) = c⁻¹ • X := by
   rw [smul_smul]; congr 1; field_simp
 have hE : IsEffect ((t*c)⁻¹ • (t • X)) := by
   rw [heq]; exact (coneEffect X hX).property
 rw [cone_at_scale v _ _ (t*c) (mul_pos hp hc) hE]
 have hh : (⟨(t*c)⁻¹ • (t • X),hE⟩ : Effect) = coneEffect X hX := by
   apply Subtype.ext; exact heq
 rw [hh]; dsimp [Matrix.vecMul, dotProduct,coneValue,c]; ring



def complementEffect (E : Effect) : Effect := ⟨1-E.val,E.property.2, by simpa using E.property.1⟩
theorem valuation_complement (v : Valuation) (E : Effect) :
 v.value (complementEffect E) = 1 - v.value E := by
 have h := v.additive E (complementEffect E) unitEffect (by dsimp [Matrix.vecMul, dotProduct,complementEffect,unitEffect]; module)
 rw [v.normalized] at h
 linarith

noncomputable def basisPlus : M2 := !![1/2,1/2;1/2,1/2]
theorem basisPlus_effect : IsEffect basisPlus := by
 have hs : basisPlusᵀ = basisPlus := by ext i j; fin_cases i <;> fin_cases j <;> norm_num [basisPlus,transpose_apply]
 have hsq : basisPlus * basisPlus = basisPlus := by ext i j; fin_cases i <;> fin_cases j <;> norm_num [basisPlus,mul_apply,Fin.sum_univ_two]
 have hp := real_projector_psd basisPlus hs hsq
 refine ⟨hp,?_⟩
 apply real_projector_psd
 · simp [Matrix.vecMul, dotProduct,transpose_sub,hs]
 · noncomm_ring [hsq]
noncomputable def basisEffect0 : Effect := ⟨Pa,(six_states_density_and_projector.sharp_effect 0)⟩
noncomputable def basisEffectPlus : Effect := ⟨basisPlus,basisPlus_effect⟩

noncomputable def representingMatrix (v : Valuation) : M2 :=
 !![v.value basisEffect0, v.value basisEffectPlus - 1/2;
    v.value basisEffectPlus - 1/2, 1-v.value basisEffect0]

theorem cone_congr (v : Valuation) (X Y : M2) (hX : X.PosSemidef) (hY : Y.PosSemidef)
 (h : X = Y) : coneValue v X hX = coneValue v Y hY := by subst Y; rfl

theorem cone_coordinate_formula (v : Valuation) (X : M2) (hX : X.PosSemidef) :
 coneValue v X hX = X 0 0 * v.value basisEffect0 +
 X 1 1 * (1-v.value basisEffect0) + 2 * X 0 1 * (v.value basisEffectPlus-1/2) := by
 have ha : 0 ≤ X 0 0 := hX.diag_nonneg
 have hd : 0 ≤ X 1 1 := hX.diag_nonneg
 have hs : X 1 0 = X 0 1 := by
   have h := congrArg (fun A : M2 => A 0 1) hX.isHermitian
   simpa [Matrix.vecMul, dotProduct,conjTranspose_apply] using h
 have hI := (Matrix.PosSemidef.one : (1 : M2).PosSemidef)
 have h0 := basisEffect0.property.1
 have h1 := (complementEffect basisEffect0).property.1
 have hplus := basisEffectPlus.property.1
 have hminus := (complementEffect basisEffectPlus).property.1
 have hvI : coneValue v 1 hI = 1 := by
   have hh := cone_on_effect v unitEffect
   rw [v.normalized] at hh
   exact hh
 by_cases hb : 0 ≤ X 0 1
 · have h2 : 0 ≤ 2 * X 0 1 := by positivity
   have he : X + (X 0 1) • (1 : M2) =
     ((X 0 0) • basisEffect0.val + (X 1 1) • (complementEffect basisEffect0).val) +
     (2*X 0 1) • basisEffectPlus.val := by
     ext i j; fin_cases i <;> fin_cases j <;>
       simp [Matrix.vecMul, dotProduct,basisEffect0,Pa,complementEffect,basisEffectPlus,basisPlus,hs] <;> ring
   have hh := cone_congr v _ _ (hX.add (hI.smul hb))
     ((h0.smul ha).add (h1.smul hd) |>.add (hplus.smul h2)) he
   rw [cone_add v X _ hX (hI.smul hb),
     cone_add v _ _ ((h0.smul ha).add (h1.smul hd)) (hplus.smul h2),
     cone_add v _ _ (h0.smul ha) (h1.smul hd),
     cone_smul v 1 hI _ hb,cone_smul v basisEffect0.val h0 _ ha,
     cone_smul v (complementEffect basisEffect0).val h1 _ hd,
     cone_smul v basisEffectPlus.val hplus _ h2,
     hvI,cone_on_effect v basisEffect0,cone_on_effect v (complementEffect basisEffect0),
     cone_on_effect v basisEffectPlus,valuation_complement] at hh
   linarith only [hh]

 · have hb' : 0 ≤ -(X 0 1) := by linarith
   have h2 : 0 ≤ -2 * X 0 1 := by nlinarith
   have he : X + (-(X 0 1)) • (1 : M2) =
     ((X 0 0) • basisEffect0.val + (X 1 1) • (complementEffect basisEffect0).val) +
     (-2*X 0 1) • (complementEffect basisEffectPlus).val := by
     ext i j; fin_cases i <;> fin_cases j <;>
       simp [Matrix.vecMul, dotProduct,basisEffect0,Pa,complementEffect,basisEffectPlus,basisPlus,hs] <;> ring
   have hh := cone_congr v _ _ (hX.add (hI.smul hb'))
     ((h0.smul ha).add (h1.smul hd) |>.add (hminus.smul h2)) he
   rw [cone_add v X _ hX (hI.smul hb'),
     cone_add v _ _ ((h0.smul ha).add (h1.smul hd)) (hminus.smul h2),
     cone_add v _ _ (h0.smul ha) (h1.smul hd),
     cone_smul v 1 hI _ hb',cone_smul v basisEffect0.val h0 _ ha,
     cone_smul v (complementEffect basisEffect0).val h1 _ hd,
     cone_smul v (complementEffect basisEffectPlus).val hminus _ h2,
     hvI,cone_on_effect v basisEffect0,cone_on_effect v (complementEffect basisEffect0),
     cone_on_effect v (complementEffect basisEffectPlus),valuation_complement,
     valuation_complement] at hh
   linarith only [hh]

theorem cone_trace_representation (v : Valuation) (X : M2) (hX : X.PosSemidef) :
 coneValue v X hX = pairing (representingMatrix v) X := by
 rw [cone_coordinate_formula]
 have hs : X 1 0 = X 0 1 := by
   have h := congrArg (fun A : M2 => A 0 1) hX.isHermitian
   simpa [Matrix.vecMul, dotProduct,conjTranspose_apply] using h
 simp [Matrix.vecMul, dotProduct,pairing,representingMatrix,trace,mul_apply,Fin.sum_univ_two,hs]
 ring

theorem representingMatrix_density (v : Valuation) : IsDensity (representingMatrix v) := by
 refine ⟨?_,?_⟩
 · rw [Matrix.posSemidef_iff_dotProduct_mulVec]
   refine ⟨?_,?_⟩
   · ext i j; fin_cases i <;> fin_cases j <;> simp [Matrix.vecMul, dotProduct,representingMatrix,conjTranspose_apply]
   · intro x
     let A : M2 := fun i j => if j = 0 then x i else 0
     have hp := Matrix.posSemidef_self_mul_conjTranspose A
     have hn := cone_nonnegative v _ hp
     rw [cone_trace_representation] at hn
     convert hn using 1 <;>
       simp [Matrix.vecMul,dotProduct,A,pairing,representingMatrix,trace,mul_apply,conjTranspose_apply,mulVec,Fin.sum_univ_two] <;> ring
 · simp [Matrix.vecMul, dotProduct,representingMatrix,trace,Fin.sum_univ_two]

theorem trace_pairing_nonnegative (R E : M2) (hR : R.PosSemidef) (hE : E.PosSemidef) :
 0 ≤ pairing R E := by
 let A := CFC.sqrt R
 have ha := (CFC.sqrt_nonneg R).posSemidef
 have hs : Aᵀ = A := by simpa [Matrix.vecMul, dotProduct,Matrix.conjTranspose_eq_transpose_of_trivial] using ha.isHermitian
 have hsq : A*A = R := CFC.sqrt_mul_sqrt_self R hR.nonneg
 have hp := hE.mul_mul_conjTranspose_same A
 have ht := hp.trace_nonneg
 have he : pairing R E = trace (A * E * Aᵀ) := by
   dsimp [Matrix.vecMul, dotProduct,pairing]
   rw [←hsq,hs]
   calc
     trace (A*A*E) = trace (A*(A*E)) := by rw [Matrix.mul_assoc]
     _ = trace (A*E*A) := Matrix.trace_mul_comm _ _
 rw [Matrix.conjTranspose_eq_transpose_of_trivial,←he] at ht

 exact ht

theorem trace_valuation_laws (R : Density) : TraceValuationLaws R := by
 constructor
 · intro E; exact trace_pairing_nonnegative _ _ R.property.1 E.property.1
 · simpa [Matrix.vecMul, dotProduct,pairing,unitEffect] using R.property.2
 · intro E F H h; simp [Matrix.vecMul, dotProduct,pairing,h,Matrix.mul_add,Matrix.trace_add]
noncomputable def traceValuation (R : Density) : Valuation where
 value E := pairing R.val E.val
 nonnegative := (trace_valuation_laws R).nonnegative
 normalized := (trace_valuation_laws R).normalized
 additive := (trace_valuation_laws R).additive

theorem density_is_effect (R : Density) : IsEffect R.val := by
 refine ⟨R.property.1,?_⟩
 let J : M2 := !![0,-1;1,0]
 have hs : R.val 1 0 = R.val 0 1 := by
   have h := congrArg (fun A : M2 => A 0 1) R.property.1.isHermitian
   simpa [Matrix.vecMul, dotProduct,conjTranspose_apply] using h
 have ht : R.val 0 0 + R.val 1 1 = 1 := by
   simpa [Matrix.vecMul, dotProduct,trace,Fin.sum_univ_two] using R.property.2
 have hp := R.property.1.mul_mul_conjTranspose_same J
 convert hp using 1
 ext i j; fin_cases i <;> fin_cases j <;>
   simp [Matrix.vecMul, dotProduct,J,mul_apply,conjTranspose_apply,Fin.sum_univ_two,hs] <;> linarith

theorem effects_separate_densities (R Q : Density)
 (h : ∀ E : Effect, pairing R.val E.val = pairing Q.val E.val) : R = Q := by
 have hr := h ⟨R.val,density_is_effect R⟩
 have hq := h ⟨Q.val,density_is_effect Q⟩
 have hs : (R.val-Q.val)ᴴ = R.val-Q.val := R.property.1.isHermitian.sub Q.property.1.isHermitian
 have hz : trace ((R.val-Q.val)ᴴ * (R.val-Q.val)) = 0 := by
   rw [hs]
   simp only [pairing] at hr hq
   simp [Matrix.vecMul, dotProduct,Matrix.sub_mul,Matrix.mul_sub,Matrix.trace_sub]
   have hc := Matrix.trace_mul_comm R.val Q.val
   linarith
 have hh := Matrix.trace_conjTranspose_mul_self_eq_zero_iff.mp hz
 apply Subtype.ext
 exact sub_eq_zero.mp hh

theorem full_interval_trace_unique (v : Valuation) :
 ∃! R : Density, ∀ E : Effect, v.value E = pairing R.val E.val := by
 let R : Density := ⟨representingMatrix v,representingMatrix_density v⟩
 have hr : ∀ E : Effect, v.value E = pairing R.val E.val := by
   intro E
   rw [←cone_on_effect v E]
   exact cone_trace_representation v E.val E.property.1
 refine ⟨R,hr,?_⟩
 intro Q hQ
 exact effects_separate_densities Q R (fun E => (hQ E).symm.trans (hr E))


theorem six_states_effect (i : Fin 6) : IsEffect (sixState i) :=
 density_is_effect ⟨sixState i,six_states_density_and_projector.density i⟩
end BornCalculus
