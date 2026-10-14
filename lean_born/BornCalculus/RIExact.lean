import BornCalculus.RIInputs
namespace BornCalculus
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0
set_option maxRecDepth 100000

theorem ri_centeredQ : ∑ i : Fin 32, riWQ i=0 := by
 norm_num [riWQ,Fin.sum_univ_succ]
theorem ri_normQ : ∑ i : Fin 32, riWQ i*riWQ i=riSQ := by
 norm_num [riWQ,riSQ,Fin.sum_univ_succ]
theorem ri_s_positiveQ : 0<riSQ := by norm_num [riSQ]
def riPQ : Matrix (Fin 32) (Fin 32) ℚ := fun i j => 1/32+riWQ i*riWQ j/riSQ
theorem riPQ_transpose : riPQᵀ=riPQ := by ext i j; simp [riPQ]; ring

theorem riPQ_idempotent : riPQ*riPQ=riPQ := by
 have hs : riSQ≠0 := ri_s_positiveQ.ne'
 ext i j
 change (∑ k : Fin 32, (1/32+riWQ i*riWQ k/riSQ)*(1/32+riWQ k*riWQ j/riSQ))=1/32+riWQ i*riWQ j/riSQ
 calc
  _ = ∑ k : Fin 32, (1/1024+(riWQ i+riWQ j)/(32*riSQ)*riWQ k+
      (riWQ i*riWQ j)/(riSQ*riSQ)*(riWQ k*riWQ k)) := by
        apply Finset.sum_congr rfl; intro k _; field_simp; ring
  _ = (32:ℚ)*(1/1024)+(riWQ i+riWQ j)/(32*riSQ)*(∑ k : Fin 32,riWQ k)+
      (riWQ i*riWQ j)/(riSQ*riSQ)*(∑ k : Fin 32,riWQ k*riWQ k) := by
        rw [Finset.sum_add_distrib,Finset.sum_add_distrib,←Finset.mul_sum,←Finset.mul_sum]
        simp
  _ = _ := by rw [ri_centeredQ,ri_normQ]; field_simp; ring

def riVQ (i : Fin 32) : Fin 32 → ℚ := fun j => riPQ j i
def riDenQ (i : Fin 32) : ℚ := ∑ j : Fin 32,riVQ i j*riVQ i j

theorem riDenQ_formula (i : Fin 32) : riDenQ i=1/32+riWQ i*riWQ i/riSQ := by
 have h := congrArg (fun A : Matrix (Fin 32) (Fin 32) ℚ => A i i) riPQ_idempotent
 change (∑ j : Fin 32,riPQ i j*riPQ j i)=riPQ i i at h
 have ht (j : Fin 32) : riPQ i j=riPQ j i := by simp [riPQ]; ring
 calc
   riDenQ i = ∑ j : Fin 32,riPQ i j*riPQ j i := by
     apply Finset.sum_congr rfl; intro j _; dsimp [riVQ]; rw [ht]
   _ = _ := h

theorem ri_den_positiveQ (i : Fin 32) : 0<riDenQ i := by
 rw [riDenQ_formula]
 have h := div_nonneg (mul_self_nonneg (riWQ i)) ri_s_positiveQ.le
 linarith

def riDensityQ (i : Fin 32) : Matrix (Fin 32) (Fin 32) ℚ :=
 fun j k => riVQ i j*riVQ i k / riDenQ i
def riReadoutQ (i : Fin 32) : ℚ :=
 (∑ j : Fin 32, if riRaw j=0 then riVQ i j*riVQ i j else 0) / riDenQ i

theorem ri_gap_exactQ : riReadoutQ 1-riReadoutQ 3=riGapQ := by
 simp only [riReadoutQ,riVQ,riPQ,riDenQ_formula]
 dsimp [riWQ,riSQ,riRaw,riGapQ]
 norm_num [Fin.sum_univ_succ]
theorem ri_gap_within_archived_interval : riGapLoQ ≤ riGapQ ∧ riGapQ ≤ riGapHiQ := by
 norm_num [riGapQ,riGapLoQ,riGapHiQ]
theorem ri_gap_nonzeroQ : riGapQ≠0 := by norm_num [riGapQ]

theorem ri_density_separatedQ : riDensityQ 1≠riDensityQ 3 := by
 intro h
 have hm (j : Fin 32) : riDensityQ 1 j j=riDensityQ 3 j j := congrArg (fun A => A j j) h
 have hr : riReadoutQ 1=riReadoutQ 3 := by
   dsimp [riReadoutQ]
   rw [Finset.sum_div,Finset.sum_div]
   apply Finset.sum_congr rfl
   intro j _
   by_cases hj : riRaw j=0
   · simpa [riDensityQ,hj] using hm j
   · simp [hj]
 exact ri_gap_nonzeroQ (ri_gap_exactQ ▸ sub_eq_zero.mpr hr)
end BornCalculus
