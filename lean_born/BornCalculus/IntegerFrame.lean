import BornCalculus.CenteredFrame

namespace BornCalculus
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0

/-- Exact dyadic frames are represented by arbitrary-precision integers.
This is an arithmetic representation, not an added physical premise. -/
structure IntegerFrame32 where
 z : Fin 32 → ℤ
 D : ℤ
 S : ℤ
 denominator_positive : 0 < D
 norm_positive : 0 < S
 centered : (∑ i, z i) = 0
 squared : (∑ i, (z i)^2) = S

noncomputable def integerCentered (F : IntegerFrame32) : CenteredFrame32 :=
 ⟨fun i => (F.z i:ℝ)/(F.D:ℝ),(F.S:ℝ)/(F.D:ℝ)^2,
  by
   have hs : (0:ℝ) < (F.S:ℝ) := by exact_mod_cast F.norm_positive
   have hd : (0:ℝ) < (F.D:ℝ) := by exact_mod_cast F.denominator_positive
   exact div_pos hs (sq_pos_of_pos hd),
  by
   change (∑ i : Fin 32, (F.z i:ℝ)/(F.D:ℝ)) = 0
   rw [←Finset.sum_div]
   have hc : (∑ i : Fin 32, (F.z i:ℝ)) = 0 := by exact_mod_cast F.centered
   rw [hc,zero_div],
  by
   change (∑ i : Fin 32, ((F.z i:ℝ)/(F.D:ℝ))^2) = (F.S:ℝ)/(F.D:ℝ)^2
   simp_rw [div_pow]
   rw [←Finset.sum_div]
   have hs : (∑ i : Fin 32, (F.z i:ℝ)^2) = (F.S:ℝ) := by exact_mod_cast F.squared
   rw [hs]⟩

def integerReadNumerator (F : IntegerFrame32) (m0 m1 m2 : ℤ) (i : Fin 32) : ℤ :=
 m0*F.S^2+64*F.S*F.z i*m1+1024*(F.z i)^2*m2

def integerReadDenominator (F : IntegerFrame32) (i : Fin 32) : ℤ :=
 32*F.S*(F.S+32*(F.z i)^2)

theorem integer_read_denominator_positive (F : IntegerFrame32) (i : Fin 32) :
 0 < integerReadDenominator F i := by
 unfold integerReadDenominator
 have hs := F.norm_positive
 positivity

theorem integer_point_probability (F : IntegerFrame32) (i k : Fin 32) :
 (1+framePointChart (integerCentered F) i*(integerCentered F).w k)^2/
   (32+(integerCentered F).s*(framePointChart (integerCentered F) i)^2) =
 ((F.S:ℝ)+32*(F.z i:ℝ)*(F.z k:ℝ))^2/
   (32*(F.S:ℝ)*((F.S:ℝ)+32*(F.z i:ℝ)^2)) := by
 have hd : (F.D:ℝ) ≠ 0 := by exact_mod_cast F.denominator_positive.ne'
 have hs : (F.S:ℝ) ≠ 0 := by exact_mod_cast F.norm_positive.ne'
 have hspos : (0:ℝ) < (F.S:ℝ) := by exact_mod_cast F.norm_positive
 have hp : (F.S:ℝ)+32*(F.z i:ℝ)^2 ≠ 0 :=
   (add_pos_of_pos_of_nonneg hspos (by positivity)).ne'
 dsimp [framePointChart,integerCentered]
 field_simp [hd,hs,hp]

theorem integer_frame_point_read (F : IntegerFrame32) (q : Fin 32 → Fin 4) (i : Fin 32)
 (m0 m1 m2 : ℤ)
 (h0 : (∑ k : Fin 32, if q k = 0 then (1:ℤ) else 0) = m0)
 (h1 : (∑ k : Fin 32, if q k = 0 then F.z k else 0) = m1)
 (h2 : (∑ k : Fin 32, if q k = 0 then (F.z k)^2 else 0) = m2) :
 framePointRead (integerCentered F) q 0 i =
 (integerReadNumerator F m0 m1 m2 i:ℝ)/(integerReadDenominator F i:ℝ) := by
 rw [framePointRead,frame_lens_pairing]
 simp_rw [integer_point_probability]
 have he (k : Fin 32) :
 (if q k = 0 then ((F.S:ℝ)+32*(F.z i:ℝ)*(F.z k:ℝ))^2 else 0) =
 (if q k = 0 then (1:ℝ) else 0)*(F.S:ℝ)^2+
 (64*(F.S:ℝ)*(F.z i:ℝ))*(if q k = 0 then (F.z k:ℝ) else 0)+
 (1024*(F.z i:ℝ)^2)*(if q k = 0 then (F.z k:ℝ)^2 else 0) := by
   split_ifs <;> ring
 have hh0 : (∑ k : Fin 32, if q k = 0 then (1:ℝ) else 0) = (m0:ℝ) := by exact_mod_cast h0
 have hh1 : (∑ k : Fin 32, if q k = 0 then (F.z k:ℝ) else 0) = (m1:ℝ) := by exact_mod_cast h1
 have hh2 : (∑ k : Fin 32, if q k = 0 then (F.z k:ℝ)^2 else 0) = (m2:ℝ) := by exact_mod_cast h2
 have hif (k : Fin 32) :
 (if q k = 0 then ((F.S:ℝ)+32*(F.z i:ℝ)*(F.z k:ℝ))^2/
   (32*(F.S:ℝ)*((F.S:ℝ)+32*(F.z i:ℝ)^2)) else 0) =
 (if q k = 0 then ((F.S:ℝ)+32*(F.z i:ℝ)*(F.z k:ℝ))^2 else 0)/
   (32*(F.S:ℝ)*((F.S:ℝ)+32*(F.z i:ℝ)^2)) := by split_ifs <;> simp
 simp_rw [hif]
 rw [←Finset.sum_div]
 simp_rw [he]
 rw [Finset.sum_add_distrib,Finset.sum_add_distrib,←Finset.sum_mul,
   ←Finset.mul_sum,←Finset.mul_sum,hh0,hh1,hh2]
 simp [integerReadNumerator,integerReadDenominator]

end BornCalculus
