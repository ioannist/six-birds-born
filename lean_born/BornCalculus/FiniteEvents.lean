import BornCalculus.Programs

namespace BornCalculus
open scoped BigOperators

instance outcomesDecidableEq (P : List KrausTest) : DecidableEq (Outcomes P) := by
 induction P with
 | nil => exact inferInstanceAs (DecidableEq Unit)
 | cons C P ih =>
   letI : DecidableEq (Outcomes P) := ih
   exact inferInstanceAs (DecidableEq (Fin C.arity × Outcomes P))

/-- Every subset of the declared word domain is an event. -/
theorem program_event_count (P : List KrausTest) :
 Fintype.card (Finset (Outcomes P)) = 2 ^ Fintype.card (Outcomes P) :=
 Fintype.card_finset

theorem proper_finset_count {α : Type*} [Fintype α] [Nonempty α]
 [Fintype {s : Finset α // s.Nonempty ∧ s ≠ Finset.univ}] :
 Fintype.card {s : Finset α // s.Nonempty ∧ s ≠ Finset.univ} =
   2 ^ Fintype.card α - 2 := by
 classical
 let endpoints : Finset (Finset α) := {∅, Finset.univ}
 have hne : (∅ : Finset α) ≠ Finset.univ := by
   obtain ⟨x⟩ := ‹Nonempty α›
   intro he
   have hx : x ∈ (∅ : Finset α) := he.symm ▸ Finset.mem_univ x
   simpa using hx
 have he : ∀ s : Finset α,
   s ∈ (Finset.univ \ endpoints) ↔ s.Nonempty ∧ s ≠ Finset.univ := by
   intro s
   simp [endpoints, Finset.nonempty_iff_ne_empty]
 rw [Fintype.card_of_subtype (Finset.univ \ endpoints) he]
 rw [Finset.card_sdiff]
 simp [endpoints, hne, Fintype.card_finset]

end BornCalculus
