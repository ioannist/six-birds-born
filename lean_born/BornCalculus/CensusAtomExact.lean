import BornCalculus.CensusAtomInputs

namespace BornCalculus
open scoped BigOperators
set_option maxHeartbeats 0
set_option maxRecDepth 100000

def atomBlock (c : Fin 120) (f : Fin 3) (a : Fin 4) : Finset (Fin 32) :=
 Finset.univ.filter (fun i => censusLabels c f i = a)
def atomCard (c : Fin 120) (f : Fin 3) (a : Fin 4) : ℕ := (atomBlock c f a).card

theorem atom_coordinate_checks (c : Fin 120) (f : Fin 3) (a : Fin 4) :
 (0 < atomCard c f a → censusLabels c f (atomFirst c f a) = a) ∧
 (1 < atomCard c f a → censusLabels c f (atomSecond c f a) = a ∧
   censusZ c (atomFirst c f a) ≠ censusZ c (atomSecond c f a)) ∧
 (atomCard c f a = 1 → 32*(censusZ c (atomFirst c f a))^2 < 31*censusS c) := by
 decide +kernel +revert

theorem atom_total_count :
 (∑ c : Fin 120, ∑ f : Fin 3, ∑ a : Fin 4, if 0 < atomCard c f a then 1 else 0) = (1006:ℕ) := by
 decide +kernel

theorem atom_singleton_count :
 (∑ c : Fin 120, ∑ f : Fin 3, ∑ a : Fin 4, if atomCard c f a = 1 then 1 else 0) = (27:ℕ) := by
 decide +kernel

theorem atom_singleton_context_count :
 (∑ c : Fin 120, if ∃ f : Fin 3, ∃ a : Fin 4, atomCard c f a = 1 then 1 else 0) = (20:ℕ) := by
 decide +kernel

end BornCalculus
