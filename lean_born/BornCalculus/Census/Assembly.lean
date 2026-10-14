import BornCalculus.Census.Certificate
import Mathlib.Logic.Equiv.Fin.Basic

namespace BornCalculus.Census
open scoped BigOperators
set_option maxHeartbeats 0

/-- A shard's counts are theorems about its certified cases, not supplied totals. -/
structure CertifiedShard (n : ℕ) where
 cases : Fin n → CertifiedCase
 active : ℕ
 positive : ℕ
 singular : ℕ
 contexts : ℕ
 active_total : (∑ c, (cases c).raw.activeCount) = active
 positive_total : (∑ c, (cases c).raw.positiveCount) = positive
 singular_total : (∑ c, (cases c).raw.singularCount) = singular
 contexts_total : (∑ c, (cases c).raw.singularContext) = contexts

/-- The row-major shard order followed by its tail is bijective with the full
ordered finite cohort, including empty-shard boundary cases. -/
def cohortPartition (groups size tail : ℕ) :
 (Fin groups × Fin size) ⊕ Fin tail ≃ Fin (groups*size+tail) :=
 (Equiv.sumCongr finProdFinEquiv (Equiv.refl (Fin tail))).trans finSumFinEquiv

theorem sum_through_partition {α : Type*} (groups size tail : ℕ)
 (choose : (Fin groups × Fin size) ⊕ Fin tail → α) (weight : α → ℕ) :
 (∑ c : Fin (groups*size+tail), weight (choose ((cohortPartition groups size tail).symm c))) =
 (∑ s : Fin groups, ∑ i : Fin size, weight (choose (.inl (s,i)))) +
 (∑ i : Fin tail, weight (choose (.inr i))) := by
 rw [←(cohortPartition groups size tail).sum_comp
   (fun c => weight (choose ((cohortPartition groups size tail).symm c))),
   Fintype.sum_sum_type]
 simp only [Equiv.symm_apply_apply]
 rw [Fintype.sum_prod_type]

end BornCalculus.Census
