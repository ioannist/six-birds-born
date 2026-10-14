import BornCalculus.Census.FullInputs
import BornCalculus.Census.Semantics

namespace BornCalculus.Census
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0
set_option maxRecDepth 100000

def censusI (c : Fin 2122) : Fin 32 := (censusCase c).raw.I
def censusJ (c : Fin 2122) : Fin 32 := (censusCase c).raw.J
def censusLabels (c : Fin 2122) := (censusCase c).raw.labels
def censusRobustI (c : Fin 2122) : Fin 32 := (censusCase c).raw.robustI
def censusRobustJ (c : Fin 2122) : Fin 32 := (censusCase c).raw.robustJ
noncomputable def censusFrame (c : Fin 2122) := (censusCase c).frameData
noncomputable def censusAtom (c : Fin 2122) (f : Fin 3) (a : Fin 4) := (censusCase c).atom f a

theorem census_pair_checks (c : Fin 2122) :
 censusI c < censusJ c ∧
 (censusCase c).raw.z (censusI c) ≠ (censusCase c).raw.z (censusJ c) ∧
 (∀ f : Fin 3, censusLabels c f (censusI c) = censusLabels c f (censusJ c)) :=
 ⟨(censusCase c).pair.1,(censusCase c).pair.2.1,(censusCase c).pair.2.2.1⟩

theorem census_robust_pair_checks (c : Fin 2122) :
 censusRobustI c < censusRobustJ c ∧
 (∀ f : Fin 3, censusLabels c f (censusRobustI c) = censusLabels c f (censusRobustJ c)) :=
 ⟨(censusCase c).robust.1,(censusCase c).robust.2.1⟩

theorem census_frame_checks (c : Fin 2122) :
 0 < (censusCase c).raw.D ∧ 0 < (censusCase c).raw.S ∧
 (∑ i : Fin 32, (censusCase c).raw.z i) = 0 ∧
 (∑ i : Fin 32, ((censusCase c).raw.z i)^2) = (censusCase c).raw.S :=
 (censusCase c).frame

theorem census_centered_nonzero_rational (c : Fin 2122) :
 (∑ i, (censusFrame c).w i) = 0 ∧ 0 < (censusFrame c).s ∧
 (∑ i, ((censusFrame c).w i)^2) = (censusFrame c).s ∧
 (∃ i, (censusFrame c).w i ≠ 0) ∧
 (∃ q : ℚ, (censusFrame c).s = (q:ℝ)) ∧
 (∀ i, ∃ q : ℚ, (censusFrame c).w i = (q:ℝ)) := by
 refine ⟨(censusFrame c).centered,(censusFrame c).positive,(censusFrame c).squared,?_,?_,?_⟩
 · by_contra h
   push_neg at h
   have hs := (censusFrame c).squared
   simp [h] at hs
   have hp := (censusFrame c).positive
   rw [←hs] at hp
   exact (lt_irrefl (0:ℝ)) hp
 · refine ⟨((censusCase c).raw.S:ℚ)/((censusCase c).raw.D:ℚ)^2,?_⟩
   push_cast
   rfl
 · intro i
   refine ⟨((censusCase c).raw.z i:ℚ)/((censusCase c).raw.D:ℚ),?_⟩
   push_cast
   rfl

theorem census_initial_records_equal (c : Fin 2122) :
 frameOldView (censusLabels c) (simplexPoint (censusI c)) =
 frameOldView (censusLabels c) (simplexPoint (censusJ c)) := (censusCase c).records_equal

theorem census_initial_densities_ne (c : Fin 2122) :
 frameEncoding (censusFrame c) (simplexPoint (censusI c)) ≠
 frameEncoding (censusFrame c) (simplexPoint (censusJ c)) := (censusCase c).densities_ne

theorem census_initial_readouts_ne (c : Fin 2122) :
 pairing (frameEncoding (censusFrame c) (simplexPoint (censusI c)))
   (frameLens (censusFrame c) (censusLabels c 0) 0) ≠
 pairing (frameEncoding (censusFrame c) (simplexPoint (censusJ c)))
   (frameLens (censusFrame c) (censusLabels c 0) 0) := by
 simpa only [frame_point_encoding,framePointRead] using (censusCase c).readouts_ne

theorem census_initial_no_factor {β : Type*} (fixed : β) (c : Fin 2122) :
 ¬ ∃ g : β × (Fin 3 → Fin 4 → ℝ) → ℝ, ∀ p : Simplex32,
   pairing (frameEncoding (censusFrame c) p) (frameLens (censusFrame c) (censusLabels c 0) 0) =
   g (fixed,frameOldView (censusLabels c) p) := (censusCase c).no_factor fixed

theorem census_earlier_pair_rejected (c : Fin 2122) (i j : Fin 32)
 (hij : i < j) (he : LexBefore i j (censusI c) (censusJ c)) :
 frameOldView (censusLabels c) (simplexPoint i) ≠ frameOldView (censusLabels c) (simplexPoint j) ∨
 frameEncoding (censusFrame c) (simplexPoint i) = frameEncoding (censusFrame c) (simplexPoint j) :=
 (censusCase c).earlier_pair_rejected i j hij he

theorem census_point_receipts_separate (c : Fin 2122) :
 (censusI c,frameOldView (censusLabels c) (simplexPoint (censusI c))) ≠
 (censusJ c,frameOldView (censusLabels c) (simplexPoint (censusJ c))) :=
 (censusCase c).point_receipts_separate

theorem census_robust_records_equal (c : Fin 2122) :
 frameOldView (censusLabels c) (simplexPoint (censusRobustI c)) =
 frameOldView (censusLabels c) (simplexPoint (censusRobustJ c)) := (censusCase c).robust_records_equal

theorem census_robust_witness (c : Fin 2122) :
 (∀ f : Fin 3, censusLabels c f (censusRobustI c) = censusLabels c f (censusRobustJ c)) ∧
 (1/25 : ℝ) ≤
 |pairing (frameEncoding (censusFrame c) (simplexPoint (censusRobustI c)))
   (frameLens (censusFrame c) (censusLabels c 0) 0) -
 pairing (frameEncoding (censusFrame c) (simplexPoint (censusRobustJ c)))
   (frameLens (censusFrame c) (censusLabels c 0) 0)| := by
 refine ⟨(censusCase c).robust.2.1,?_⟩
 simpa only [frame_point_encoding,framePointRead] using (censusCase c).robust_gap

noncomputable def pointGap (c : Fin 2122) (i j : Fin 32) : ℝ :=
 |pairing (frameEncoding (censusFrame c) (simplexPoint i))
   (frameLens (censusFrame c) (censusLabels c 0) 0) -
 pairing (frameEncoding (censusFrame c) (simplexPoint j))
   (frameLens (censusFrame c) (censusLabels c 0) 0)|
noncomputable def maximumGap (c : Fin 2122) : ℝ := pointGap c (censusRobustI c) (censusRobustJ c)

theorem census_maximizes (c : Fin 2122) (i j : Fin 32) (hij : i < j)
 (hq : ∀ f : Fin 3, censusLabels c f i = censusLabels c f j) :
 pointGap c i j ≤ maximumGap c := by
 simpa only [pointGap,maximumGap,frame_point_encoding,framePointRead] using
   (censusCase c).maximizes i j hij hq

theorem census_maximizing_ties (c : Fin 2122) (i j : Fin 32) (hij : i < j)
 (hq : ∀ f : Fin 3, censusLabels c f i = censusLabels c f j)
 (he : pointGap c i j = maximumGap c) :
 ¬ LexBefore i j (censusRobustI c) (censusRobustJ c) := by
 apply (censusCase c).maximizing_ties i j hij hq
 simpa only [pointGap,maximumGap,frame_point_encoding,framePointRead] using he

theorem census_maximum_lower (c : Fin 2122) : (438357/10000000 : ℝ) ≤ maximumGap c := by
 simpa only [pointGap,maximumGap,frame_point_encoding,framePointRead] using
   (censusCase c).maximum_lower

theorem census_minimum_candidate_upper_check :
 10000000*(censusCase 425).raw.gapN ≤ 438358*(censusCase 425).raw.gapD := by
 decide +kernel

theorem census_minimum_candidate_upper : maximumGap 425 ≤ (438358/10000000 : ℝ) := by
 rw [maximumGap,pointGap,frame_point_encoding,frame_point_encoding]
 change |framePointRead (censusCase 425).frameData ((censusCase 425).raw.labels 0) 0 (censusCase 425).raw.robustI -
   framePointRead (censusCase 425).frameData ((censusCase 425).raw.labels 0) 0 (censusCase 425).raw.robustJ| ≤ _
 rw [(censusCase 425).robust_gap_formula]
 have hg : (0:ℝ) < ((censusCase 425).raw.gapD:ℝ) := by exact_mod_cast (censusCase 425).robust.2.2.1
 apply (div_le_iff₀ hg).mpr
 have h : 10000000*((censusCase 425).raw.gapN:ℝ) ≤
   438358*((censusCase 425).raw.gapD:ℝ) := by exact_mod_cast census_minimum_candidate_upper_check
 linarith

noncomputable def maximumGapSet : Finset ℝ := Finset.univ.image maximumGap

theorem maximumGapSet_nonempty : maximumGapSet.Nonempty := by
 classical
 exact ⟨maximumGap 0, Finset.mem_image.mpr ⟨0,Finset.mem_univ 0,rfl⟩⟩

noncomputable def minimumMaximumGap : ℝ := maximumGapSet.min' maximumGapSet_nonempty

theorem census_minimum_isLeast : IsLeast (Set.range maximumGap) minimumMaximumGap := by
 classical
 have hm := Finset.min'_mem maximumGapSet maximumGapSet_nonempty
 obtain ⟨c,_,hc⟩ := Finset.mem_image.mp hm
 refine ⟨⟨c,hc⟩,?_⟩
 rintro _ ⟨c,rfl⟩
 exact Finset.min'_le maximumGapSet (maximumGap c) (Finset.mem_image.mpr ⟨c,Finset.mem_univ c,rfl⟩)

theorem census_minimum_enclosure :
 (438357/10000000 : ℝ) ≤ minimumMaximumGap ∧ minimumMaximumGap ≤ (438358/10000000 : ℝ) := by
 classical
 constructor
 · apply Finset.le_min'
   intro g hg
   obtain ⟨c,_,rfl⟩ := Finset.mem_image.mp hg
   exact census_maximum_lower c
 · exact le_trans ((census_minimum_isLeast).2 ⟨425,rfl⟩) census_minimum_candidate_upper

theorem census_atom_domain (c : Fin 2122) (f : Fin 3) (a : Fin 4) :
 GIsEffect 32 (censusFrame c).s (censusAtom c f a) := (censusCase c).atom_domain f a

theorem census_atom_active_iff (c : Fin 2122) (f : Fin 3) (a : Fin 4) :
 0 < (censusCase c).raw.atomN f a ↔ 0 < (frameBlockSet (censusLabels c f) a).card :=
 (censusCase c).atom_active_iff f a

theorem census_atom_singular_iff_integer (c : Fin 2122) (f : Fin 3) (a : Fin 4) :
 (censusAtom c f a).det = 0 ↔ (censusCase c).raw.det f a = 0 :=
 (censusCase c).atom_singular_iff_integer f a

theorem census_atom_positive_iff_integer (c : Fin 2122) (f : Fin 3) (a : Fin 4) :
 0 < (censusAtom c f a).det ↔ 0 < (censusCase c).raw.det f a :=
 (censusCase c).atom_positive_iff_integer f a

theorem census_atom_singular_iff_constant (c : Fin 2122) (f : Fin 3) (a : Fin 4) :
 (0 < (frameBlockSet (censusLabels c f) a).card ∧ (censusAtom c f a).det = 0) ↔
 (0 < (frameBlockSet (censusLabels c f) a).card ∧
   ∀ i j, censusLabels c f i = a → censusLabels c f j = a →
   (censusFrame c).w i = (censusFrame c).w j) := by
 simp only [censusAtom,censusLabels,censusFrame,
   (censusCase c).atom_singular_iff_constant f a]

theorem census_atom_nonnegative (c : Fin 2122) (f : Fin 3) (a : Fin 4) :
 0 ≤ (censusAtom c f a).det := (censusCase c).atom_nonnegative f a

theorem census_singular_trace_bounds (c : Fin 2122) (f : Fin 3) (a : Fin 4)
 (ha : 0 < (frameBlockSet (censusLabels c f) a).card) (hd : (censusAtom c f a).det = 0) :
 0 < trace (censusAtom c f a) ∧ trace (censusAtom c f a) < 1 :=
 (censusCase c).singular_trace_bounds f a ((census_atom_active_iff c f a).mpr ha) hd

theorem census_singular_nonzero_nonprojector (c : Fin 2122) (f : Fin 3) (a : Fin 4)
 (ha : 0 < (frameBlockSet (censusLabels c f) a).card) (hd : (censusAtom c f a).det = 0) :
 censusAtom c f a ≠ 0 ∧ censusAtom c f a*censusAtom c f a ≠ censusAtom c f a :=
 (censusCase c).singular_nonzero_nonprojector f a ((census_atom_active_iff c f a).mpr ha) hd

theorem census_active_atom_count :
 (∑ c : Fin 2122, ∑ f : Fin 3, ∑ a : Fin 4,
   if 0 < (frameBlockSet (censusLabels c f) a).card then 1 else 0) = (17008:ℕ) := by
 classical
 simp_rw [←census_atom_active_iff]
 exact census_activeCount_total

theorem census_positive_atom_count :
 (∑ c : Fin 2122, ∑ f : Fin 3, ∑ a : Fin 4,
   if 0 < (frameBlockSet (censusLabels c f) a).card ∧ 0 < (censusAtom c f a).det then 1 else 0) = (16693:ℕ) := by
 classical
 simp_rw [←census_atom_active_iff,census_atom_positive_iff_integer]
 exact census_positiveCount_total

theorem census_singular_atom_count :
 (∑ c : Fin 2122, ∑ f : Fin 3, ∑ a : Fin 4,
   if 0 < (frameBlockSet (censusLabels c f) a).card ∧ (censusAtom c f a).det = 0 then 1 else 0) = (315:ℕ) := by
 classical
 simp_rw [←census_atom_active_iff,census_atom_singular_iff_integer]
 exact census_singularCount_total

theorem census_singular_context_count :
 (∑ c : Fin 2122, if ∃ f : Fin 3, ∃ a : Fin 4,
   0 < (frameBlockSet (censusLabels c f) a).card ∧ (censusAtom c f a).det = 0 then 1 else 0) = (272:ℕ) := by
 classical
 simp_rw [←census_atom_active_iff,census_atom_singular_iff_integer]
 exact census_singularContext_total

end BornCalculus.Census
