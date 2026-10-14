import BornCalculus.B06Witness

namespace BornCalculus
open Matrix
open scoped BigOperators

/-- Moving towards epsilon zero preserves strict interior values. -/
theorem fragmentWitness_smaller (E : M2) (δ ε : ℝ)
 (hbase : 0 < E 0 0 ∧ E 0 0 < 1)
 (hδ : 0 < pairing (fragmentWitness δ) E ∧ pairing (fragmentWitness δ) E < 1)
 (hε : 0 ≤ ε) (hle : ε ≤ δ) :
 0 < pairing (fragmentWitness ε) E ∧ pairing (fragmentWitness ε) E < 1 := by
 rw [fragmentWitness_pairing] at hδ ⊢
 by_cases hd : 0 ≤ E 0 0-E 1 1
 · have hm := mul_le_mul_of_nonneg_right hle hd
   have hp := mul_nonneg hε hd
   constructor <;> linarith [hbase.1,hδ.2]
 · have hd' := le_of_not_ge hd
   have hm := mul_le_mul_of_nonpos_right hle hd'
   have hp := mul_nonpos_of_nonneg_of_nonpos hε hd'
   constructor <;> linarith [hbase.2,hδ.1]

theorem finite_fragment_all_small (s : Finset M2)
 (hs : ∀ E ∈ s, 0 < E 0 0 ∧ E 0 0 < 1) :
 ∃ δ : ℝ, 0 < δ ∧ ∀ ε : ℝ, 0 < ε → ε ≤ δ →
   ¬ IsDensity (fragmentWitness ε) ∧ trace (fragmentWitness ε) = 1 ∧
   ∀ E ∈ s, 0 < pairing (fragmentWitness ε) E ∧
     pairing (fragmentWitness ε) E < 1 := by
 obtain ⟨δ,hδ,_,_,hv⟩ := finite_fragment_non_density s hs
 exact ⟨δ,hδ,fun ε hε hle => ⟨fragmentWitness_not_density ε hε,
   fragmentWitness_trace ε,fun E hE => fragmentWitness_smaller E δ ε (hs E hE) (hv E hE) hε.le hle⟩⟩

theorem finite_program_fragment_all_small {ι : Type*} [Fintype ι]
 (events : ι → InteriorProgramEvent) :
 ∃ δ : ℝ, 0 < δ ∧ ∀ ε : ℝ, 0 < ε → ε ≤ δ →
   ¬ IsDensity (fragmentWitness ε) ∧ trace (fragmentWitness ε) = 1 ∧
   ∀ i, 0 < pairing (fragmentWitness ε) (interiorEventEffect (events i)) ∧
     pairing (fragmentWitness ε) (interiorEventEffect (events i)) < 1 := by
 classical
 let s : Finset M2 := Finset.univ.image (fun i => interiorEventEffect (events i))
 have hs : ∀ E ∈ s, 0 < E 0 0 ∧ E 0 0 < 1 := by
   intro E hE
   obtain ⟨i,_,rfl⟩ := Finset.mem_image.mp hE
   exact groupedEffect_diagonal_interior _ (events i).invertible _
     (events i).nonempty (events i).omitted
 obtain ⟨δ,hδ,hv⟩ := finite_fragment_all_small s hs
 refine ⟨δ,hδ,?_⟩
 intro ε hε hle
 obtain ⟨hn,ht,hp⟩ := hv ε hε hle
 exact ⟨hn,ht,fun i => hp _ (Finset.mem_image.mpr ⟨i,Finset.mem_univ i,rfl⟩)⟩

/-- All positive parameters up to one bound work on the actual registered
family, including endpoints, all proper events, and nonrepresentation. -/
theorem b06_all_small_non_density :
 ∃ δ : ℝ, 0 < δ ∧ ∀ ε : ℝ, 0 < ε → ε ≤ δ →
   ¬ GIsDensity 32 b06S (fragmentWitness ε) ∧
   trace (fragmentWitness ε) = 1 ∧
   (∀ e : B06ProperEvent,
     0 < pairing (fragmentWitness ε) (b06EventEffect ⟨e.1,e.2.val⟩) ∧
     pairing (fragmentWitness ε) (b06EventEffect ⟨e.1,e.2.val⟩) < 1) ∧
   (∀ e : B06Event, 0 ≤ pairing (fragmentWitness ε) (b06EventEffect e) ∧
     pairing (fragmentWitness ε) (b06EventEffect e) ≤ 1) ∧
   ¬ ∃ R : GDensity 32 b06S, ∀ e : B06Event,
     pairing R.val (b06EventEffect e) = pairing (fragmentWitness ε) (b06EventEffect e) := by
 classical
 obtain ⟨δ,hδ,hv⟩ := finite_program_fragment_all_small b06InteriorEvent
 refine ⟨δ,hδ,?_⟩
 intro ε hε hle
 obtain ⟨_,ht,hp⟩ := hv ε hε hle
 have hproper (e : B06ProperEvent) :
     0 < pairing (fragmentWitness ε) (b06EventEffect ⟨e.1,e.2.val⟩) ∧
     pairing (fragmentWitness ε) (b06EventEffect ⟨e.1,e.2.val⟩) < 1 := by
   simpa only [b06EventEffect,fragmentWitness_frame_pairing 32 b06S (by norm_num) b06_s_positive,
     interiorEventEffect,b06InteriorEvent] using hp e
 refine ⟨fragmentWitness_g_not_density 32 b06S (by norm_num) b06_s_positive ε hε,
   ht,hproper,?_,b06_no_density_representation ε hε⟩
 intro e
 by_cases he : e.2 = ∅
 · rcases e with ⟨i,s⟩
   change s = ∅ at he
   subst s
   simp [b06_event_empty,pairing]
 by_cases hu : e.2 = Finset.univ
 · rcases e with ⟨i,s⟩
   change s = Finset.univ at hu
   subst s
   simp [b06_event_unit,pairing,ht]
 let p : B06ProperEvent := ⟨e.1,⟨e.2,Finset.nonempty_iff_ne_empty.mpr he,hu⟩⟩
 exact ⟨(hproper p).1.le,(hproper p).2.le⟩

theorem b06_assignment_endpoints (ε : ℝ) (i : Fin 12) :
 pairing (fragmentWitness ε) (b06EventEffect ⟨i,∅⟩) = 0 ∧
 pairing (fragmentWitness ε) (b06EventEffect ⟨i,Finset.univ⟩) = 1 := by
 simp [b06_event_empty,b06_event_unit,pairing,fragmentWitness_trace]

theorem b06_assignment_additive (ε : ℝ) (i : Fin 12)
 (s t : Finset (Outcomes (b06Programs i))) (hst : Disjoint s t) :
 pairing (fragmentWitness ε) (b06EventEffect ⟨i,s ∪ t⟩) =
 pairing (fragmentWitness ε) (b06EventEffect ⟨i,s⟩) +
 pairing (fragmentWitness ε) (b06EventEffect ⟨i,t⟩) := by
 unfold b06EventEffect groupedEffect
 rw [Finset.sum_union hst]
 simp [fromOrth,Matrix.mul_add,Matrix.add_mul,pairing,Matrix.trace_add]

#print axioms fragmentWitness_smaller
#print axioms finite_fragment_all_small
#print axioms finite_program_fragment_all_small
#print axioms b06_all_small_non_density
#print axioms b06_assignment_endpoints
#print axioms b06_assignment_additive
end BornCalculus
