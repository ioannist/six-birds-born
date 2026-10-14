import BornCalculus.Census.Certificate
import BornCalculus.FrameAtoms

namespace BornCalculus.Census
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0

noncomputable def CertifiedCase.integer (C : CertifiedCase) : IntegerFrame32 :=
 ⟨C.raw.z,C.raw.D,C.raw.S,C.frame.1,C.frame.2.1,C.frame.2.2.1,C.frame.2.2.2⟩
noncomputable def CertifiedCase.frameData (C : CertifiedCase) : CenteredFrame32 :=
 integerCentered C.integer
noncomputable def CertifiedCase.atom (C : CertifiedCase) (f : Fin 3) (a : Fin 4) : M2 :=
 frameLens C.frameData (C.raw.labels f) a

/-- Constant on the entire labelled block, including every nonsingleton block. -/
theorem frame_det_zero_iff_constant {m : ℕ} (F : CenteredFrame32)
 (q : Fin 32 → Fin m) (a : Fin m) :
 (frameLens F q a).det = 0 ↔ ∀ i j, q i = a → q j = a → F.w i = F.w j := by
 constructor
 · intro hd i j hi hj
   by_contra hn
   have hp := frame_lens_det_positive F q a i j hi hj hn
   rw [hd] at hp
   exact (lt_irrefl 0) hp
 · intro hc
   have hz : (∑ i ∈ frameBlockSet q a, ∑ j ∈ frameBlockSet q a,
     (F.w i-F.w j)^2) = 0 := by
     apply Finset.sum_eq_zero
     intro i hi
     apply Finset.sum_eq_zero
     intro j hj
     have hei : q i = a := (Finset.mem_filter.mp hi).2
     have hej : q j = a := (Finset.mem_filter.mp hj).2
     rw [hc i j hei hej,sub_self,zero_pow (by decide)]
   rw [finite_variance_identity] at hz
   rw [frame_lens_variance]
   have hn : (frameBlockSet q a).card*(∑ i ∈ frameBlockSet q a, (F.w i)^2)-
     (∑ i ∈ frameBlockSet q a, F.w i)^2 = 0 := by linarith
   rw [hn,zero_div]

theorem CertifiedCase.records_equal (C : CertifiedCase) :
 frameOldView C.raw.labels (simplexPoint C.raw.I) =
 frameOldView C.raw.labels (simplexPoint C.raw.J) :=
 frame_old_points_equal _ _ _ C.pair.2.2.1

theorem CertifiedCase.coordinates_ne (C : CertifiedCase) :
 C.frameData.w C.raw.I ≠ C.frameData.w C.raw.J := by
 change (C.raw.z C.raw.I:ℝ)/(C.raw.D:ℝ) ≠ (C.raw.z C.raw.J:ℝ)/(C.raw.D:ℝ)
 have hd : (C.raw.D:ℝ) ≠ 0 := by exact_mod_cast C.frame.1.ne'
 intro he
 have h := congrArg (fun x : ℝ => x*(C.raw.D:ℝ)) he
 simp only [div_mul_cancel₀ _ hd] at h
 exact C.pair.2.1 (by exact_mod_cast h)

theorem CertifiedCase.densities_ne (C : CertifiedCase) :
 frameEncoding C.frameData (simplexPoint C.raw.I) ≠
 frameEncoding C.frameData (simplexPoint C.raw.J) :=
 frame_points_density_ne _ _ _ C.coordinates_ne

theorem CertifiedCase.point_read_formula (C : CertifiedCase) (i : Fin 32) :
 framePointRead C.frameData (C.raw.labels 0) 0 i =
 (C.raw.numerator i:ℝ)/(C.raw.denominator i:ℝ) := by
 simpa only [CertifiedCase.frameData,CertifiedCase.integer,integerReadNumerator,
   integerReadDenominator,RawCase.numerator,RawCase.denominator] using
   integer_frame_point_read C.integer (C.raw.labels 0) i
     C.raw.m0 C.raw.m1 C.raw.m2 C.moments.1 C.moments.2.1 C.moments.2.2

theorem CertifiedCase.point_read_reduced (C : CertifiedCase) (i : Fin 32) :
 framePointRead C.frameData (C.raw.labels 0) 0 i =
 (C.raw.readN i:ℝ)/(C.raw.readD i:ℝ) := by
 rw [C.point_read_formula]
 have hd : (C.raw.denominator i:ℝ) ≠ 0 := by
   have h := integer_read_denominator_positive C.integer i
   change 0 < C.raw.denominator i at h
   exact_mod_cast h.ne'
 have hr : (C.raw.readD i:ℝ) ≠ 0 := by exact_mod_cast (C.reads i).1.ne'
 apply (div_eq_div_iff hd hr).mpr
 exact_mod_cast (C.reads i).2.symm

theorem CertifiedCase.read_real (C : CertifiedCase) (i : Fin 32) :
 framePointRead C.frameData (C.raw.labels 0) 0 i = (C.raw.read i:ℝ) := by
 rw [C.point_read_reduced]
 simp only [RawCase.read,Rat.cast_div,Rat.cast_intCast]

theorem CertifiedCase.point_gap_formula (C : CertifiedCase) (i j : Fin 32) :
 |framePointRead C.frameData (C.raw.labels 0) 0 i -
  framePointRead C.frameData (C.raw.labels 0) 0 j| =
 (C.raw.crossGap i j:ℝ)/((C.raw.readD i:ℝ)*(C.raw.readD j:ℝ)) := by
 rw [C.point_read_reduced,C.point_read_reduced]
 have hd (k : Fin 32) : (0:ℝ) < (C.raw.readD k:ℝ) := by exact_mod_cast (C.reads k).1
 have he : (C.raw.readN i:ℝ)/(C.raw.readD i:ℝ)-(C.raw.readN j:ℝ)/(C.raw.readD j:ℝ) =
 ((C.raw.readN i:ℝ)*(C.raw.readD j:ℝ)-(C.raw.readN j:ℝ)*(C.raw.readD i:ℝ))/
 ((C.raw.readD i:ℝ)*(C.raw.readD j:ℝ)) := by field_simp [(hd i).ne',(hd j).ne']
 rw [he,abs_div,abs_of_pos (mul_pos (hd i) (hd j))]
 simp only [RawCase.crossGap,Int.cast_abs,Int.cast_sub,Int.cast_mul]

theorem CertifiedCase.robust_gap_formula (C : CertifiedCase) :
 |framePointRead C.frameData (C.raw.labels 0) 0 C.raw.robustI -
  framePointRead C.frameData (C.raw.labels 0) 0 C.raw.robustJ| =
 (C.raw.gapN:ℝ)/(C.raw.gapD:ℝ) := by
 rw [C.point_gap_formula]
 have hd (k : Fin 32) : (C.raw.readD k:ℝ) ≠ 0 := by exact_mod_cast (C.reads k).1.ne'
 have hg : (C.raw.gapD:ℝ) ≠ 0 := by exact_mod_cast C.robust.2.2.1.ne'
 apply (div_eq_div_iff (mul_ne_zero (hd _) (hd _)) hg).mpr
 have h : (C.raw.crossGap C.raw.robustI C.raw.robustJ:ℝ)*(C.raw.gapD:ℝ) =
   (C.raw.gapN:ℝ)*(C.raw.readD C.raw.robustI:ℝ)*(C.raw.readD C.raw.robustJ:ℝ) := by
   exact_mod_cast C.robust.2.2.2.1
 simpa only [mul_assoc] using h

theorem CertifiedCase.readouts_ne (C : CertifiedCase) :
 framePointRead C.frameData (C.raw.labels 0) 0 C.raw.I ≠
 framePointRead C.frameData (C.raw.labels 0) 0 C.raw.J := by
 rw [C.point_read_formula,C.point_read_formula]
 have hd (i : Fin 32) : (C.raw.denominator i:ℝ) ≠ 0 := by
   have h := integer_read_denominator_positive C.integer i
   change 0 < C.raw.denominator i at h
   exact_mod_cast h.ne'
 intro he
 have h := (div_eq_div_iff (hd _) (hd _)).mp he
 exact C.pair.2.2.2 (by exact_mod_cast h)

theorem CertifiedCase.no_factor {β : Type*} (fixed : β) (C : CertifiedCase) :
 ¬ ∃ g : β × (Fin 3 → Fin 4 → ℝ) → ℝ, ∀ p : Simplex32,
   pairing (frameEncoding C.frameData p) (frameLens C.frameData (C.raw.labels 0) 0) =
   g (fixed,frameOldView C.raw.labels p) :=
 frame_initial_no_factor fixed C.frameData C.raw.labels C.raw.I C.raw.J 0 0
   C.pair.2.2.1 C.readouts_ne

theorem CertifiedCase.earlier_pair_rejected (C : CertifiedCase) (i j : Fin 32)
 (hij : i < j) (he : LexBefore i j C.raw.I C.raw.J) :
 frameOldView C.raw.labels (simplexPoint i) ≠ frameOldView C.raw.labels (simplexPoint j) ∨
 frameEncoding C.frameData (simplexPoint i) = frameEncoding C.frameData (simplexPoint j) := by
 rcases C.earlier i j hij he with ⟨f,hf⟩ | hw
 · left
   intro hv
   exact hf ((frame_old_points_equal_iff _ _ _).mp hv f)
 · right
   apply frame_points_density_eq
   change (C.raw.z i:ℝ)/(C.raw.D:ℝ) = (C.raw.z j:ℝ)/(C.raw.D:ℝ)
   rw [hw]

theorem CertifiedCase.point_receipts_separate (C : CertifiedCase) :
 (C.raw.I,frameOldView C.raw.labels (simplexPoint C.raw.I)) ≠
 (C.raw.J,frameOldView C.raw.labels (simplexPoint C.raw.J)) := by
 intro he
 have h := congrArg (fun p : Fin 32 × (Fin 3 → Fin 4 → ℝ) => p.1) he
 exact (ne_of_lt C.pair.1) h

theorem CertifiedCase.robust_records_equal (C : CertifiedCase) :
 frameOldView C.raw.labels (simplexPoint C.raw.robustI) =
 frameOldView C.raw.labels (simplexPoint C.raw.robustJ) :=
 frame_old_points_equal _ _ _ C.robust.2.1

theorem CertifiedCase.robust_gap (C : CertifiedCase) :
 (1/25 : ℝ) ≤ |framePointRead C.frameData (C.raw.labels 0) 0 C.raw.robustI -
 framePointRead C.frameData (C.raw.labels 0) 0 C.raw.robustJ| := by
 rw [C.robust_gap_formula]
 have hg : (0:ℝ) < (C.raw.gapD:ℝ) := by exact_mod_cast C.robust.2.2.1
 apply (le_div_iff₀ hg).mpr
 have h : (C.raw.gapD:ℝ) ≤ 25*(C.raw.gapN:ℝ) := by exact_mod_cast C.robust.2.2.2.2.1
 linarith

theorem CertifiedCase.maximum_lower (C : CertifiedCase) :
 (438357/10000000 : ℝ) ≤ |framePointRead C.frameData (C.raw.labels 0) 0 C.raw.robustI -
 framePointRead C.frameData (C.raw.labels 0) 0 C.raw.robustJ| := by
 rw [C.robust_gap_formula]
 have hg : (0:ℝ) < (C.raw.gapD:ℝ) := by exact_mod_cast C.robust.2.2.1
 apply (le_div_iff₀ hg).mpr
 have h : 438357*(C.raw.gapD:ℝ) ≤ 10000000*(C.raw.gapN:ℝ) := by
   exact_mod_cast C.robust.2.2.2.2.2
 linarith

theorem CertifiedCase.range_bounds (C : CertifiedCase) (i : Fin 32) :
 framePointRead C.frameData (C.raw.labels 0) 0 (C.raw.low (C.raw.key i)) ≤
   framePointRead C.frameData (C.raw.labels 0) 0 i ∧
 framePointRead C.frameData (C.raw.labels 0) 0 i ≤
   framePointRead C.frameData (C.raw.labels 0) 0 (C.raw.high (C.raw.key i)) ∧
 |framePointRead C.frameData (C.raw.labels 0) 0 (C.raw.low (C.raw.key i)) -
  framePointRead C.frameData (C.raw.labels 0) 0 (C.raw.high (C.raw.key i))| ≤
 |framePointRead C.frameData (C.raw.labels 0) 0 C.raw.robustI -
  framePointRead C.frameData (C.raw.labels 0) 0 C.raw.robustJ| := by
 have hd (k : Fin 32) : (0:ℝ) < (C.raw.readD k:ℝ) := by exact_mod_cast (C.reads k).1
 have hg : (0:ℝ) < (C.raw.gapD:ℝ) := by exact_mod_cast C.robust.2.2.1
 refine ⟨?_,?_,?_⟩
 · rw [C.point_read_reduced,C.point_read_reduced]
   apply (div_le_div_iff₀ (hd _) (hd i)).mpr
   exact_mod_cast (C.ranges i).1
 · rw [C.point_read_reduced,C.point_read_reduced]
   apply (div_le_div_iff₀ (hd i) (hd _)).mpr
   exact_mod_cast (C.ranges i).2.1
 · rw [C.point_gap_formula,C.robust_gap_formula]
   apply (div_le_div_iff₀ (mul_pos (hd _) (hd _)) hg).mpr
   have h : (C.raw.crossGap (C.raw.low (C.raw.key i)) (C.raw.high (C.raw.key i)):ℝ)*(C.raw.gapD:ℝ) ≤
     (C.raw.gapN:ℝ)*(C.raw.readD (C.raw.low (C.raw.key i)):ℝ)*(C.raw.readD (C.raw.high (C.raw.key i)):ℝ) := by
     exact_mod_cast (C.ranges i).2.2
   simpa only [mul_assoc] using h

theorem CertifiedCase.maximizes (C : CertifiedCase) (i j : Fin 32)
 (hij : i < j) (hq : ∀ f, C.raw.labels f i = C.raw.labels f j) :
 |framePointRead C.frameData (C.raw.labels 0) 0 i -
  framePointRead C.frameData (C.raw.labels 0) 0 j| ≤
 |framePointRead C.frameData (C.raw.labels 0) 0 C.raw.robustI -
  framePointRead C.frameData (C.raw.labels 0) 0 C.raw.robustJ| := by
 have _ := hij
 have hi := C.range_bounds i
 have hj := C.range_bounds j
 have hk : C.raw.key i = C.raw.key j := by
   apply Fin.ext
   simp only [RawCase.key,hq 0,hq 1,hq 2]
 rw [←hk] at hj
 have hab : |framePointRead C.frameData (C.raw.labels 0) 0 (C.raw.low (C.raw.key i)) -
   framePointRead C.frameData (C.raw.labels 0) 0 (C.raw.high (C.raw.key i))| =
   framePointRead C.frameData (C.raw.labels 0) 0 (C.raw.high (C.raw.key i)) -
   framePointRead C.frameData (C.raw.labels 0) 0 (C.raw.low (C.raw.key i)) := by
   rw [abs_of_nonpos (sub_nonpos.mpr (le_trans hi.1 hi.2.1))]
   ring
 rw [hab] at hi
 apply abs_sub_le_iff.mpr
 constructor <;> linarith [hi.1,hi.2.1,hi.2.2,hj.1,hj.2.1]

theorem CertifiedCase.maximizing_ties (C : CertifiedCase) (i j : Fin 32)
 (hij : i < j) (hq : ∀ f, C.raw.labels f i = C.raw.labels f j)
 (he : |framePointRead C.frameData (C.raw.labels 0) 0 i -
  framePointRead C.frameData (C.raw.labels 0) 0 j| =
 |framePointRead C.frameData (C.raw.labels 0) 0 C.raw.robustI -
  framePointRead C.frameData (C.raw.labels 0) 0 C.raw.robustJ|) :
 ¬ LexBefore i j C.raw.robustI C.raw.robustJ := by
 rw [C.point_gap_formula,C.robust_gap_formula] at he
 have hd (k : Fin 32) : (C.raw.readD k:ℝ) ≠ 0 := by exact_mod_cast (C.reads k).1.ne'
 have hg : (C.raw.gapD:ℝ) ≠ 0 := by exact_mod_cast C.robust.2.2.1.ne'
 have h := (div_eq_div_iff (mul_ne_zero (hd i) (hd j)) hg).mp he
 have h' : (C.raw.crossGap i j:ℝ)*(C.raw.gapD:ℝ) =
   (C.raw.gapN:ℝ)*(C.raw.readD i:ℝ)*(C.raw.readD j:ℝ) := by
   simpa only [mul_assoc] using h
 intro hb
 have heZ : C.raw.crossGap i j*C.raw.gapD = C.raw.gapN*C.raw.readD i*C.raw.readD j := by
   exact_mod_cast h'
 exact (ne_of_lt (C.earlierMax i j hij hb hq)) heZ

theorem CertifiedCase.atom_det_formula (C : CertifiedCase) (f : Fin 3) (a : Fin 4) :
 (C.atom f a).det = (C.raw.det f a:ℝ)/(32*(C.raw.S:ℝ)) := by
 have h0 : integerBlockCount (C.raw.labels f) a = C.raw.atomN f a := (C.atoms f a).1.symm
 have h1 : integerBlockSum C.integer (C.raw.labels f) a = C.raw.atomZ f a := (C.atoms f a).2.1.symm
 have h2 : integerBlockSquare C.integer (C.raw.labels f) a = C.raw.atomZZ f a := (C.atoms f a).2.2.1.symm
 rw [CertifiedCase.atom,CertifiedCase.frameData,integer_lens_determinant]
 rw [integerBlockDet,h0,h1,h2]
 rfl

theorem CertifiedCase.atom_trace_formula (C : CertifiedCase) (f : Fin 3) (a : Fin 4) :
 trace (C.atom f a) = (C.raw.atomN f a:ℝ)/32+(C.raw.atomZZ f a:ℝ)/(C.raw.S:ℝ) := by
 have h0 : integerBlockCount (C.raw.labels f) a = C.raw.atomN f a := (C.atoms f a).1.symm
 have h2 : integerBlockSquare C.integer (C.raw.labels f) a = C.raw.atomZZ f a := (C.atoms f a).2.2.1.symm
 rw [CertifiedCase.atom,CertifiedCase.frameData,integer_lens_trace]
 rw [h0,h2]
 rfl

theorem CertifiedCase.atom_domain (C : CertifiedCase) (f : Fin 3) (a : Fin 4) :
 GIsEffect 32 C.frameData.s (C.atom f a) := frame_lens_domain _ _ _

theorem CertifiedCase.atomN_eq_card (C : CertifiedCase) (f : Fin 3) (a : Fin 4) :
 C.raw.atomN f a = ((frameBlockSet (C.raw.labels f) a).card:ℤ) := by
 rw [(C.atoms f a).1]
 simp [frameBlockSet]

theorem CertifiedCase.atom_active_iff (C : CertifiedCase) (f : Fin 3) (a : Fin 4) :
 0 < C.raw.atomN f a ↔ 0 < (frameBlockSet (C.raw.labels f) a).card := by
 rw [C.atomN_eq_card]
 exact_mod_cast (Iff.rfl : 0 < (frameBlockSet (C.raw.labels f) a).card ↔
   0 < (frameBlockSet (C.raw.labels f) a).card)

theorem CertifiedCase.atom_positive_iff_integer (C : CertifiedCase) (f : Fin 3) (a : Fin 4) :
 0 < (C.atom f a).det ↔ 0 < C.raw.det f a := by
 rw [C.atom_det_formula]
 have hs : (0:ℝ) < (C.raw.S:ℝ) := by exact_mod_cast C.frame.2.1
 rw [div_pos_iff_of_pos_right (mul_pos (by norm_num) hs)]
 exact_mod_cast (Iff.rfl : 0 < C.raw.det f a ↔ 0 < C.raw.det f a)

theorem CertifiedCase.atom_nonnegative (C : CertifiedCase) (f : Fin 3) (a : Fin 4) :
 0 ≤ (C.atom f a).det := by
 rw [C.atom_det_formula]
 apply div_nonneg
 · exact_mod_cast (C.atoms f a).2.2.2.1
 · have hs : (0:ℝ) < (C.raw.S:ℝ) := by exact_mod_cast C.frame.2.1
   positivity

theorem CertifiedCase.atom_singular_iff_integer (C : CertifiedCase) (f : Fin 3) (a : Fin 4) :
 (C.atom f a).det = 0 ↔ C.raw.det f a = 0 := by
 rw [C.atom_det_formula]
 have hs : (C.raw.S:ℝ) ≠ 0 := by exact_mod_cast C.frame.2.1.ne'
 rw [div_eq_zero_iff,or_iff_left (mul_ne_zero (by norm_num) hs)]
 exact_mod_cast (Iff.rfl : C.raw.det f a = 0 ↔ C.raw.det f a = 0)

theorem CertifiedCase.atom_singular_iff_constant (C : CertifiedCase) (f : Fin 3) (a : Fin 4) :
 (C.atom f a).det = 0 ↔ ∀ i j, C.raw.labels f i = a → C.raw.labels f j = a →
 C.frameData.w i = C.frameData.w j := frame_det_zero_iff_constant _ _ _

theorem CertifiedCase.singular_trace_bounds (C : CertifiedCase) (f : Fin 3) (a : Fin 4)
 (ha : 0 < C.raw.atomN f a) (hd : (C.atom f a).det = 0) :
 0 < trace (C.atom f a) ∧ trace (C.atom f a) < 1 := by
 have hi := (C.atom_singular_iff_integer f a).mp hd
 have ht := (C.atoms f a).2.2.2.2 ⟨ha,hi⟩
 have hs : (0:ℝ) < (C.raw.S:ℝ) := by exact_mod_cast C.frame.2.1
 have hlo : (0:ℝ) < (C.raw.atomN f a:ℝ)*(C.raw.S:ℝ)+32*(C.raw.atomZZ f a:ℝ) := by
   exact_mod_cast ht.1
 have hhi : (C.raw.atomN f a:ℝ)*(C.raw.S:ℝ)+32*(C.raw.atomZZ f a:ℝ) < 32*(C.raw.S:ℝ) := by
   exact_mod_cast ht.2
 rw [C.atom_trace_formula]
 have he : (C.raw.atomN f a:ℝ)/32+(C.raw.atomZZ f a:ℝ)/(C.raw.S:ℝ) =
 ((C.raw.atomN f a:ℝ)*(C.raw.S:ℝ)+32*(C.raw.atomZZ f a:ℝ))/(32*(C.raw.S:ℝ)) := by
   field_simp
 constructor
 · rw [he]; exact div_pos hlo (mul_pos (by norm_num) hs)
 · rw [he]; apply (div_lt_one (mul_pos (by norm_num) hs)).mpr hhi

theorem CertifiedCase.singular_nonzero_nonprojector (C : CertifiedCase) (f : Fin 3) (a : Fin 4)
 (ha : 0 < C.raw.atomN f a) (hd : (C.atom f a).det = 0) :
 C.atom f a ≠ 0 ∧ C.atom f a*C.atom f a ≠ C.atom f a := by
 have ht := C.singular_trace_bounds f a ha hd
 have hn : C.atom f a ≠ 0 := by
   intro h
   rw [h,Matrix.trace_zero] at ht
   exact (lt_irrefl 0) ht.1
 refine ⟨hn,?_⟩
 intro hi
 have he := matrix_singular_idempotent_trace (C.atom f a) hd hn hi
 rw [he] at ht
 exact (lt_irrefl 1) ht.2

end BornCalculus.Census
