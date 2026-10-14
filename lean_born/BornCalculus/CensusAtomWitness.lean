import BornCalculus.CensusAtomExact
import BornCalculus.CensusWitness
import BornCalculus.FrameAtoms

namespace BornCalculus
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0

noncomputable def censusAtom (c : Fin 120) (f : Fin 3) (a : Fin 4) : M2 :=
 frameLens (censusFrame c) (censusLabels c f) a

theorem census_atom_domain (c : Fin 120) (f : Fin 3) (a : Fin 4) :
 GIsEffect 32 (censusFrame c).s (censusAtom c f a) := frame_lens_domain _ _ _

theorem census_atom_coordinate_ne (c : Fin 120) (f : Fin 3) (a : Fin 4)
 (hc : 1 < atomCard c f a) :
 (censusFrame c).w (atomFirst c f a) ≠ (censusFrame c).w (atomSecond c f a) := by
 change (censusZ c (atomFirst c f a):ℝ)/(censusD c:ℝ) ≠
   (censusZ c (atomSecond c f a):ℝ)/(censusD c:ℝ)
 have hd : (censusD c:ℝ) ≠ 0 := by exact_mod_cast (census_frame_checks c).1.ne'
 intro he
 have h := congrArg (fun t : ℝ => t*(censusD c:ℝ)) he
 simp only [div_mul_cancel₀ _ hd] at h
 exact ((atom_coordinate_checks c f a).2.1 hc).2 (by exact_mod_cast h)

theorem census_atom_multiple_det_positive (c : Fin 120) (f : Fin 3) (a : Fin 4)
 (hc : 1 < atomCard c f a) : 0 < (censusAtom c f a).det := by
 apply frame_lens_det_positive (censusFrame c) (censusLabels c f) a
   (atomFirst c f a) (atomSecond c f a)
 · exact (atom_coordinate_checks c f a).1 (by omega)
 · exact ((atom_coordinate_checks c f a).2.1 hc).1
 · exact census_atom_coordinate_ne c f a hc

theorem census_atom_singleton_matrix (c : Fin 120) (f : Fin 3) (a : Fin 4)
 (hc : atomCard c f a = 1) :
 censusAtom c f a = frameParent (censusFrame c) (atomFirst c f a) := by
 apply frame_lens_singleton
 · exact hc
 · exact (atom_coordinate_checks c f a).1 (by omega)

theorem census_atom_singleton_det_zero (c : Fin 120) (f : Fin 3) (a : Fin 4)
 (hc : atomCard c f a = 1) : (censusAtom c f a).det = 0 := by
 rw [census_atom_singleton_matrix c f a hc]
 exact frame_parent_det_zero _ _

/-- Only active labels count as registered atoms. Unused padded labels give
zero effects but are excluded from the singular-atom census. -/
theorem census_atom_singular_iff_singleton (c : Fin 120) (f : Fin 3) (a : Fin 4) :
 (0 < atomCard c f a ∧ (censusAtom c f a).det = 0) ↔ atomCard c f a = 1 := by
 constructor
 · rintro ⟨hp,hd⟩
   by_contra h
   have hc : 1 < atomCard c f a := by omega
   have hs := census_atom_multiple_det_positive c f a hc
   rw [hd] at hs
   exact (lt_irrefl 0) hs
 · intro hc
   exact ⟨by omega,census_atom_singleton_det_zero c f a hc⟩

theorem census_singular_atom_count :
 (∑ c : Fin 120, ∑ f : Fin 3, ∑ a : Fin 4,
   if 0 < atomCard c f a ∧ (censusAtom c f a).det = 0 then 1 else 0) = (27:ℕ) := by
 classical
 simp_rw [census_atom_singular_iff_singleton]
 exact atom_singleton_count

theorem census_singular_context_count :
 (∑ c : Fin 120, if ∃ f : Fin 3, ∃ a : Fin 4,
   0 < atomCard c f a ∧ (censusAtom c f a).det = 0 then 1 else 0) = (20:ℕ) := by
 classical
 simp_rw [census_atom_singular_iff_singleton]
 exact atom_singleton_context_count

theorem census_singleton_trace_bounds (c : Fin 120) (f : Fin 3) (a : Fin 4)
 (hc : atomCard c f a = 1) : 0 < trace (censusAtom c f a) ∧ trace (censusAtom c f a) < 1 := by
 rw [census_atom_singleton_matrix c f a hc,frame_parent_trace]
 have hd : (censusD c:ℝ) ≠ 0 := by exact_mod_cast (census_frame_checks c).1.ne'
 have hs : (0:ℝ) < (censusS c:ℝ) := by exact_mod_cast (census_frame_checks c).2.1
 have he : ((censusFrame c).w (atomFirst c f a))^2/(censusFrame c).s =
   (censusZ c (atomFirst c f a):ℝ)^2/(censusS c:ℝ) := by
   change ((censusZ c (atomFirst c f a):ℝ)/(censusD c:ℝ))^2/
     ((censusS c:ℝ)/(censusD c:ℝ)^2) = _
   field_simp [hd,hs.ne']
 rw [he]
 have hq : (32:ℝ)*(censusZ c (atomFirst c f a):ℝ)^2 < 31*(censusS c:ℝ) := by
   exact_mod_cast (atom_coordinate_checks c f a).2.2 hc
 constructor
 · exact add_pos_of_pos_of_nonneg (by norm_num) (div_nonneg (sq_nonneg _) hs.le)
 · have hu : (censusZ c (atomFirst c f a):ℝ)^2/(censusS c:ℝ) < 31/32 :=
     (div_lt_iff₀ hs).mpr (by linarith)
   linarith

theorem census_singleton_nonzero_nonprojector (c : Fin 120) (f : Fin 3) (a : Fin 4)
 (hc : atomCard c f a = 1) :
 censusAtom c f a ≠ 0 ∧ censusAtom c f a*censusAtom c f a ≠ censusAtom c f a := by
 have ht := census_singleton_trace_bounds c f a hc
 have hn : censusAtom c f a ≠ 0 := by
   intro h
   rw [h,Matrix.trace_zero] at ht
   exact (lt_irrefl 0) ht.1
 refine ⟨hn,?_⟩
 intro hi
 have he := matrix_singular_idempotent_trace (censusAtom c f a)
   (census_atom_singleton_det_zero c f a hc) hn hi
 rw [he] at ht
 exact (lt_irrefl 1) ht.2

end BornCalculus
