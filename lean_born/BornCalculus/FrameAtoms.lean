import BornCalculus.IntegerFrame
import BornCalculus.PrincipalFormula

namespace BornCalculus
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0

noncomputable def frameBlockCount {m : ℕ} (q : Fin 32 → Fin m) (a : Fin m) : ℝ :=
 ∑ i, if q i = a then 1 else 0
noncomputable def frameBlockSum {m : ℕ} (F : CenteredFrame32) (q : Fin 32 → Fin m) (a : Fin m) : ℝ :=
 ∑ i, if q i = a then F.w i else 0
noncomputable def frameBlockSquare {m : ℕ} (F : CenteredFrame32) (q : Fin 32 → Fin m) (a : Fin m) : ℝ :=
 ∑ i, if q i = a then (F.w i)^2 else 0

theorem frame_lens_coordinates {m : ℕ} (F : CenteredFrame32) (q : Fin 32 → Fin m) (a : Fin m) :
 frameLens F q a = !![frameBlockCount q a/32,frameBlockSum F q a/32;
   frameBlockSum F q a/F.s,frameBlockSquare F q a/F.s] := by
 have hif (f : Fin 32 → ℝ) (d : ℝ) (i : Fin 32) :
   (if q i = a then f i/d else 0) = (if q i = a then f i else 0)/d := by split_ifs <;> simp
 have hsum (f : Fin 32 → ℝ) (d : ℝ) :
   (∑ i : Fin 32, if q i = a then f i/d else 0) = (∑ i : Fin 32, if q i = a then f i else 0)/d := by
   simp_rw [hif]
   rw [←Finset.sum_div]
 have he (i : Fin 32) (r c : Fin 2) :
   (if q i = a then frameParent F i else 0) r c =
   if q i = a then frameParent F i r c else 0 := by
   by_cases h : q i = a <;> simp [h]
 ext r c
 simp only [frameLens,Matrix.sum_apply]
 simp_rw [he]
 fin_cases r <;> fin_cases c
 · simpa [frameParent,frameBlockCount] using hsum (fun _ => 1) 32
 · simpa [frameParent,frameBlockSum] using hsum F.w 32
 · simpa [frameParent,frameBlockSum] using hsum F.w F.s
 · simpa [frameParent,frameBlockSquare] using hsum (fun i => (F.w i)^2) F.s

def integerBlockCount {m : ℕ} (q : Fin 32 → Fin m) (a : Fin m) : ℤ := ∑ i, if q i = a then 1 else 0
def integerBlockSum {m : ℕ} (F : IntegerFrame32) (q : Fin 32 → Fin m) (a : Fin m) : ℤ :=
 ∑ i, if q i = a then F.z i else 0
def integerBlockSquare {m : ℕ} (F : IntegerFrame32) (q : Fin 32 → Fin m) (a : Fin m) : ℤ :=
 ∑ i, if q i = a then (F.z i)^2 else 0
def integerBlockDet {m : ℕ} (F : IntegerFrame32) (q : Fin 32 → Fin m) (a : Fin m) : ℤ :=
 integerBlockCount q a*integerBlockSquare F q a-(integerBlockSum F q a)^2

theorem integer_block_count_cast {m : ℕ} (q : Fin 32 → Fin m) (a : Fin m) :
 frameBlockCount q a = (integerBlockCount q a:ℝ) := by
 simp [frameBlockCount,integerBlockCount,apply_ite]

theorem integer_block_sum_cast {m : ℕ} (F : IntegerFrame32) (q : Fin 32 → Fin m) (a : Fin m) :
 frameBlockSum (integerCentered F) q a = (integerBlockSum F q a:ℝ)/(F.D:ℝ) := by
 have hif (i : Fin 32) : (if q i = a then (F.z i:ℝ)/(F.D:ℝ) else 0) =
   (if q i = a then (F.z i:ℝ) else 0)/(F.D:ℝ) := by split_ifs <;> simp
 simp only [frameBlockSum,integerCentered]
 simp_rw [hif]
 rw [←Finset.sum_div]
 simp [integerBlockSum,apply_ite]

theorem integer_block_square_cast {m : ℕ} (F : IntegerFrame32) (q : Fin 32 → Fin m) (a : Fin m) :
 frameBlockSquare (integerCentered F) q a = (integerBlockSquare F q a:ℝ)/(F.D:ℝ)^2 := by
 have hif (i : Fin 32) : (if q i = a then ((F.z i:ℝ)/(F.D:ℝ))^2 else 0) =
   (if q i = a then (F.z i:ℝ)^2 else 0)/(F.D:ℝ)^2 := by split_ifs <;> simp [div_pow]
 simp only [frameBlockSquare,integerCentered]
 simp_rw [hif]
 rw [←Finset.sum_div]
 simp [integerBlockSquare,apply_ite]

theorem integer_lens_determinant {m : ℕ} (F : IntegerFrame32) (q : Fin 32 → Fin m) (a : Fin m) :
 (frameLens (integerCentered F) q a).det = (integerBlockDet F q a:ℝ)/(32*(F.S:ℝ)) := by
 have hd : (F.D:ℝ) ≠ 0 := by exact_mod_cast F.denominator_positive.ne'
 have hs : (F.S:ℝ) ≠ 0 := by exact_mod_cast F.norm_positive.ne'
 rw [frame_lens_coordinates,Matrix.det_fin_two,integer_block_count_cast,
   integer_block_sum_cast,integer_block_square_cast]
 dsimp only [integerCentered]
 simp [integerBlockDet]
 field_simp [hd,hs] <;> ring

theorem integer_lens_trace {m : ℕ} (F : IntegerFrame32) (q : Fin 32 → Fin m) (a : Fin m) :
 trace (frameLens (integerCentered F) q a) =
   (integerBlockCount q a:ℝ)/32+(integerBlockSquare F q a:ℝ)/(F.S:ℝ) := by
 have hd : (F.D:ℝ) ≠ 0 := by exact_mod_cast F.denominator_positive.ne'
 have hs : (F.S:ℝ) ≠ 0 := by exact_mod_cast F.norm_positive.ne'
 rw [frame_lens_coordinates]
 simp [trace,Fin.sum_univ_two]
 rw [integer_block_count_cast,integer_block_square_cast]
 dsimp only [integerCentered]
 field_simp [hd,hs]

theorem finite_variance_identity (s : Finset (Fin 32)) (x : Fin 32 → ℝ) :
 (∑ i ∈ s, ∑ j ∈ s, (x i-x j)^2) =
 2*((s.card:ℝ)*(∑ i ∈ s, (x i)^2)-(∑ i ∈ s, x i)^2) := by
 simp_rw [sub_sq]
 simp only [Finset.sum_add_distrib,Finset.sum_sub_distrib,Finset.sum_const,nsmul_eq_mul,
   ←Finset.mul_sum,←Finset.sum_mul]
 ring


def frameBlockSet {m : ℕ} (q : Fin 32 → Fin m) (a : Fin m) : Finset (Fin 32) :=
 Finset.univ.filter (fun i => q i = a)

theorem frame_lens_variance {m : ℕ} (F : CenteredFrame32) (q : Fin 32 → Fin m) (a : Fin m) :
 (frameLens F q a).det =
 ((frameBlockSet q a).card*(∑ i ∈ frameBlockSet q a, (F.w i)^2)-
   (∑ i ∈ frameBlockSet q a, F.w i)^2)/(32*F.s) := by
 rw [frame_lens_coordinates,Matrix.det_fin_two]
 have h0 : frameBlockCount q a = ((frameBlockSet q a).card:ℝ) := by
   simp [frameBlockCount,frameBlockSet,Finset.sum_filter]
 have h1 : frameBlockSum F q a = ∑ i ∈ frameBlockSet q a, F.w i := by
   simp [frameBlockSum,frameBlockSet,Finset.sum_filter]
 have h2 : frameBlockSquare F q a = ∑ i ∈ frameBlockSet q a, (F.w i)^2 := by
   simp [frameBlockSquare,frameBlockSet,Finset.sum_filter]
 rw [h0,h1,h2]
 simp
 field_simp [F.positive.ne'] <;> ring

theorem frame_lens_det_positive {m : ℕ} (F : CenteredFrame32) (q : Fin 32 → Fin m) (a : Fin m)
 (i j : Fin 32) (hi : q i = a) (hj : q j = a) (hne : F.w i ≠ F.w j) :
 0 < (frameLens F q a).det := by
 classical
 let b := frameBlockSet q a
 have him : i ∈ b := by simp [b,frameBlockSet,hi]
 have hjm : j ∈ b := by simp [b,frameBlockSet,hj]
 have hinner : 0 < ∑ k ∈ b, (F.w i-F.w k)^2 :=
   Finset.sum_pos' (fun k _ => sq_nonneg _) ⟨j,hjm,sq_pos_of_ne_zero (sub_ne_zero.mpr hne)⟩
 have hp : 0 < ∑ k ∈ b, ∑ l ∈ b, (F.w k-F.w l)^2 :=
   Finset.sum_pos' (fun k _ => Finset.sum_nonneg (fun l _ => sq_nonneg _)) ⟨i,him,hinner⟩
 rw [finite_variance_identity] at hp
 rw [frame_lens_variance]
 apply div_pos _ (mul_pos (by norm_num) F.positive)
 linarith

theorem frame_lens_singleton {m : ℕ} (F : CenteredFrame32) (q : Fin 32 → Fin m) (a : Fin m)
 (i : Fin 32) (hc : (frameBlockSet q a).card = 1) (hi : q i = a) :
 frameLens F q a = frameParent F i := by
 classical
 obtain ⟨k,hk⟩ := Finset.card_eq_one.mp hc
 have him : i ∈ frameBlockSet q a := by simp [frameBlockSet,hi]
 have hik : i = k := by simpa [hk] using him
 rw [←hik] at hk
 unfold frameLens
 rw [←Finset.sum_filter]
 change (∑ k ∈ frameBlockSet q a, frameParent F k) = frameParent F i
 rw [hk,Finset.sum_singleton]

theorem frame_parent_det_zero (F : CenteredFrame32) (i : Fin 32) : (frameParent F i).det = 0 := by
 simp [frameParent,Matrix.det_fin_two]
 field_simp [F.positive.ne'] <;> ring

theorem frame_parent_trace (F : CenteredFrame32) (i : Fin 32) :
 trace (frameParent F i) = 1/32+(F.w i)^2/F.s := by
 simp [frameParent,trace,Fin.sum_univ_two]

theorem matrix_singular_idempotent_trace (C : M2) (hd : C.det = 0) (hn : C ≠ 0)
 (hi : C*C = C) : trace C = 1 := by
 have hc := matrix_two_characteristic C
 rw [hi,hd,zero_smul,add_zero] at hc
 have he : C = (trace C) • C := sub_eq_zero.mp hc
 have hm : (trace C-1) • C = 0 := by
   rw [sub_smul,one_smul,←he,sub_self]
 rcases smul_eq_zero.mp hm with h | h
 · linarith
 · exact (hn h).elim

end BornCalculus
