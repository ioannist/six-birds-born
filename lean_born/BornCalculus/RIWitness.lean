import BornCalculus.RIExact
namespace BornCalculus
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0
set_option maxRecDepth 100000

abbrev Simplex32 := {p : Fin 32 → ℝ // (∀ i,0≤p i) ∧ ∑ i,p i=1}
noncomputable def riP : Matrix (Fin 32) (Fin 32) ℝ := fun i j => (riPQ i j : ℝ)
noncomputable def riS : ℝ := (riSQ : ℝ)
theorem ri_s_positive : 0<riS := by
 change 0<(riSQ : ℝ)
 exact_mod_cast ri_s_positiveQ
theorem riP_transpose : riPᵀ=riP := by
 ext i j
 have h := congrArg (fun A : Matrix (Fin 32) (Fin 32) ℚ => A i j) riPQ_transpose
 change (riPQ j i : ℝ)=(riPQ i j : ℝ)
 change riPQ j i=riPQ i j at h
 exact_mod_cast h
theorem riP_idempotent : riP*riP=riP := by
 ext i j
 have h := congrArg (fun A : Matrix (Fin 32) (Fin 32) ℚ => A i j) riPQ_idempotent
 change (∑ k : Fin 32,(riPQ i k : ℝ)*(riPQ k j : ℝ))=(riPQ i j : ℝ)
 simp only [Matrix.mul_apply] at h
 exact_mod_cast h

def riDelta (i : Fin 32) : Simplex32 := ⟨fun j => if j=i then 1 else 0,by
 constructor
 · intro j; dsimp; split_ifs <;> norm_num
 · simp⟩

def recordMarginal {m : ℕ} (q : Fin 32 → Fin m) (p : Simplex32) : Fin m → ℝ :=
 fun j => ∑ i : Fin 32,if q i=j then p.val i else 0

/-- All old coordinates are retained: no public preparation index is introduced.
 The indexed historical G2c unit is a distinct comparison, not this interface. -/
structure RIInitialView where
 raw : Fin 2 → ℝ
 package : Fin 3 → ℝ
 joint : Fin 3 → ℝ
 context : String
 invocationId : String
 unitId : String
 partition : String
 experiment : String
 cell : String
 seed : ℕ
 resolution : ℕ
 scale : ℕ
 time : ℕ
 lag : ℕ
 historyHorizons : List ℕ
 receiptClass : String
 recipeIndex : Option ℕ
 acquiredPassivePrefix : List ℕ
 commands : List String
 acquiredUpperOutcomes : List ℕ
 coefficientHistoryArrays : Option (List ℝ)
 precision : String
 sourcePolicy : String
 stage : String

def riInitialRecordLaw (p : Simplex32) : RIInitialView where
 raw := recordMarginal riRaw p
 package := recordMarginal riPackage p
 joint := recordMarginal riJoint p
 context := "8a7de2a7c0f49c15ab999853f8725411dbc96635624ec9bd4237766ebdcdeb3a"
 invocationId := "639d55dc0d232a83ccb696bdbc24f96ecb5c9cb6974183373d7c2ac35c86a5be"
 unitId := "7556108311046222195906f1c5d983710cbd7a4aeb8f0b21a6753864b1551afe"
 partition := "f47d6b7717804d2e567ff6672e748787da2932a3ce29977f9eaa74fc3fcbed94"
 experiment := "EXP-112"
 cell := "A13_A11"
 seed := 840007
 resolution := 2
 scale := 32
 time := 0
 lag := 8
 historyHorizons := [0]
 receiptClass := "Audit A anonymous simplex mathematical source"
 recipeIndex := none
 acquiredPassivePrefix := []
 commands := []
 acquiredUpperOutcomes := []
 coefficientHistoryArrays := none
 precision := "exact coefficient contract"
 sourcePolicy := "fixed amended full simplex, no sampled preparation population"
 stage := "PREPARATION_ENTRY"
def riInitialRecord (i : Fin 32) := riInitialRecordLaw (riDelta i)

theorem recordMarginal_delta {m : ℕ} (q : Fin 32 → Fin m) (i : Fin 32) :
 recordMarginal q (riDelta i)=fun j => if q i=j then 1 else 0 := by
 funext j
 change (∑ x : Fin 32,if q x=j then (if x=i then 1 else 0) else 0)=(if q i=j then 1 else 0)
 rw [Finset.sum_eq_single i]
 · simp
 · intro b _ hb; simp [hb]
 · simp

theorem ri_initial_records_equal : riInitialRecord 1=riInitialRecord 3 := by
 unfold riInitialRecord riInitialRecordLaw
 simp only [recordMarginal_delta]
 rfl

noncomputable def riAmplitude (p : Simplex32) : Fin 32 → ℝ :=
 riP *ᵥ (fun i => Real.sqrt (p.val i))
noncomputable def riAmplitudeDen (p : Simplex32) : ℝ := ∑ i : Fin 32,(riAmplitude p i)^2
noncomputable def riUpperDensity (p : Simplex32) : Matrix (Fin 32) (Fin 32) ℝ :=
 fun i j => riAmplitude p i*riAmplitude p j/riAmplitudeDen p
noncomputable def riUpperReadout (p : Simplex32) : ℝ :=
 (∑ j : Fin 32,if riRaw j=0 then (riAmplitude p j)^2 else 0)/riAmplitudeDen p
noncomputable def riEncodedReadout (i : Fin 32) : ℝ := (riReadoutQ i : ℝ)

theorem riAmplitude_delta (i : Fin 32) : riAmplitude (riDelta i)=fun j => (riVQ i j : ℝ) := by
 funext j
 change (∑ x : Fin 32, (riPQ j x : ℝ)*Real.sqrt (if x=i then 1 else 0))=(riVQ i j : ℝ)
 rw [Finset.sum_eq_single i]
 · simp [riVQ]
 · intro b _ hb; simp [hb]
 · simp

theorem riAmplitudeDen_delta (i : Fin 32) : riAmplitudeDen (riDelta i)=(riDenQ i : ℝ) := by
 simp only [riAmplitudeDen,riAmplitude_delta,pow_two,riDenQ]
 norm_cast

theorem ri_den_positive (i : Fin 32) : 0<riAmplitudeDen (riDelta i) := by
 rw [riAmplitudeDen_delta]
 exact_mod_cast ri_den_positiveQ i

theorem riUpperReadout_delta (i : Fin 32) : riUpperReadout (riDelta i)=riEncodedReadout i := by
 simp only [riUpperReadout,riAmplitude_delta,riAmplitudeDen_delta,riEncodedReadout,riReadoutQ,pow_two]
 push_cast
 simp only [apply_ite,Rat.cast_mul,Rat.cast_zero]

theorem ri_initial_readout_gap : riEncodedReadout 1-riEncodedReadout 3=(riGapQ : ℝ) := by
 change (riReadoutQ 1 : ℝ)-(riReadoutQ 3 : ℝ)=(riGapQ : ℝ)
 exact_mod_cast ri_gap_exactQ

theorem ri_initial_readout_ne : riEncodedReadout 1≠riEncodedReadout 3 := by
 intro h
 have hz : (riGapQ : ℝ)=0 := ri_initial_readout_gap.symm.trans (sub_eq_zero.mpr h)
 exact ri_gap_nonzeroQ (by exact_mod_cast hz)

theorem ri_initial_encoded_densities_ne : riUpperDensity (riDelta 1)≠riUpperDensity (riDelta 3) := by
 intro h
 apply ri_density_separatedQ
 ext i j
 have hh := congrArg (fun A : Matrix (Fin 32) (Fin 32) ℝ => A i j) h
 simp only [riUpperDensity,riAmplitude_delta,riAmplitudeDen_delta] at hh
 dsimp [riDensityQ]
 exact_mod_cast hh

theorem ri_initial_no_factor :
 ¬ ∃ f : RIInitialView → ℝ, ∀ p : Simplex32,riUpperReadout p=f (riInitialRecordLaw p) := by
 rintro ⟨f,hf⟩
 have h1 := hf (riDelta 1)
 have h3 := hf (riDelta 3)
 rw [riUpperReadout_delta] at h1 h3
 have he : riInitialRecordLaw (riDelta 1)=riInitialRecordLaw (riDelta 3) := ri_initial_records_equal
 rw [he] at h1
 exact ri_initial_readout_ne (h1.trans h3.symm)


theorem riPQ_column_sum (i : Fin 32) : ∑ j : Fin 32,riPQ j i=1 := by
 simp only [riPQ,Finset.sum_add_distrib,←Finset.sum_div,←Finset.sum_mul,ri_centeredQ]
 norm_num

theorem riAmplitude_sum (p : Simplex32) : ∑ i : Fin 32,riAmplitude p i=∑ i : Fin 32,Real.sqrt (p.val i) := by
 simp only [riAmplitude,mulVec,dotProduct]
 rw [Finset.sum_comm]
 have hcol (j : Fin 32) : ∑ i : Fin 32,riP i j=1 := by
   dsimp [riP]; exact_mod_cast riPQ_column_sum j
 simp only [←Finset.sum_mul,hcol,one_mul]

theorem riAmplitudeDen_positive (p : Simplex32) : 0<riAmplitudeDen p := by
 have hp : 0 < ∑ i : Fin 32,p.val i := by rw [p.property.2]; norm_num
 obtain ⟨i,_,hi⟩ := (Finset.sum_pos_iff_of_nonneg (fun i _ => p.property.1 i)).mp hp
 have hs : 0<∑ j : Fin 32,Real.sqrt (p.val j) :=
   (Finset.sum_pos_iff_of_nonneg (fun j _ => Real.sqrt_nonneg _)).mpr
     ⟨i,Finset.mem_univ i,Real.sqrt_pos.mpr hi⟩
 have hn : 0≤riAmplitudeDen p := Finset.sum_nonneg (fun i _ => sq_nonneg _)
 by_contra hh
 have hz : riAmplitudeDen p=0 := le_antisymm (not_lt.mp hh) hn
 have ha := (Finset.sum_eq_zero_iff_of_nonneg (fun i _ => sq_nonneg (riAmplitude p i))).mp hz
 have hall (j : Fin 32) : riAmplitude p j=0 := (sq_eq_zero_iff).mp (ha j (Finset.mem_univ j))
 have ht := riAmplitude_sum p
 simp only [hall,Finset.sum_const_zero] at ht
 linarith

theorem riAmplitude_in_V (p : Simplex32) : riP *ᵥ riAmplitude p=riAmplitude p := by
 simp only [riAmplitude,Matrix.mulVec_mulVec,riP_idempotent]

theorem riUpperDensity_psd_trace (p : Simplex32) :
 (riUpperDensity p).PosSemidef ∧ trace (riUpperDensity p)=1 := by
 have hp : 0<riAmplitudeDen p := riAmplitudeDen_positive p
 have he : riUpperDensity p=(riAmplitudeDen p)⁻¹ • Matrix.vecMulVec (riAmplitude p) (riAmplitude p) := by
   ext i j; simp [riUpperDensity,Matrix.vecMulVec,div_eq_mul_inv]; ring
 refine ⟨?_,?_⟩
 · rw [he]
   have h := Matrix.posSemidef_vecMulVec_self_star (riAmplitude p)
   simpa only [star_trivial] using h.smul (inv_nonneg.mpr hp.le)
 · change (∑ i : Fin 32,riAmplitude p i*riAmplitude p i/riAmplitudeDen p)=1
   rw [←Finset.sum_div]
   simp only [←pow_two]
   change riAmplitudeDen p/riAmplitudeDen p=1
   exact div_self hp.ne'

noncomputable def riAtomicEffect : Matrix (Fin 32) (Fin 32) ℝ :=
 riP * Matrix.diagonal (fun i => if riRaw i=0 then 1 else 0) * riP

theorem ri_trace_readout (p : Simplex32) :
 trace (riUpperDensity p*riAtomicEffect)=riUpperReadout p := by
 let a := riAmplitude p
 have ha : riP *ᵥ a=a := riAmplitude_in_V p
 have hva : a ᵥ* riP=a := by
   rw [←Matrix.mulVec_transpose,riP_transpose]; exact ha
 have hd : riUpperDensity p=(riAmplitudeDen p)⁻¹ • Matrix.vecMulVec a a := by
   ext i j; simp [riUpperDensity,Matrix.vecMulVec,div_eq_mul_inv,a]; ring
 let D : Matrix (Fin 32) (Fin 32) ℝ := Matrix.diagonal (fun i => if riRaw i=0 then 1 else 0)
 have hprod : Matrix.vecMulVec a a * (riP*D*riP)=Matrix.vecMulVec a ((a ᵥ* D) ᵥ* riP) := by
   rw [←Matrix.mul_assoc,←Matrix.mul_assoc,Matrix.vecMulVec_mul,hva,
       Matrix.vecMulVec_mul,Matrix.vecMulVec_mul]
 rw [hd]
 change trace (((riAmplitudeDen p)⁻¹ • Matrix.vecMulVec a a)*(riP*D*riP))=riUpperReadout p
 rw [Matrix.smul_mul,Matrix.trace_smul,hprod,Matrix.trace_vecMulVec,dotProduct_comm,
   ←Matrix.dotProduct_mulVec,ha]
 change (riAmplitudeDen p)⁻¹ * ((a ᵥ* D) ⬝ᵥ a)=riUpperReadout p
 simp only [dotProduct,D,Matrix.vecMul_diagonal]
 dsimp [riUpperReadout]
 rw [Finset.mul_sum,Finset.sum_div]
 apply Finset.sum_congr rfl
 intro i _
 dsimp [a]
 split_ifs <;> simp [div_eq_mul_inv] <;> ring

noncomputable def riJoinedUpper (p : Simplex32) := (riInitialRecordLaw p,riUpperDensity p)
theorem ri_joined_state_no_factor :
 ¬ ∃ f : RIInitialView → RIInitialView × Matrix (Fin 32) (Fin 32) ℝ,
   ∀ p : Simplex32,riJoinedUpper p=f (riInitialRecordLaw p) := by
 rintro ⟨f,hf⟩
 have h1 := hf (riDelta 1)
 have h3 := hf (riDelta 3)
 have he : riInitialRecordLaw (riDelta 1)=riInitialRecordLaw (riDelta 3) := ri_initial_records_equal
 have hj : riJoinedUpper (riDelta 1)=riJoinedUpper (riDelta 3) :=
   h1.trans ((congrArg f he).trans h3.symm)
 exact ri_initial_encoded_densities_ne (congrArg Prod.snd hj)
end BornCalculus
