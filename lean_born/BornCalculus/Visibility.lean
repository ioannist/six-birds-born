import BornCalculus.Programs

namespace BornCalculus
open Matrix
open scoped BigOperators

/-- A predicate is visible precisely when it is constant on the declared
visibility fibers. The carrier here is the declared finite test domain. -/
def EventSaturated {α β : Type*} (v : α → β) (s : Finset α) : Prop :=
 ∀ x y, v x = v y → (x ∈ s ↔ y ∈ s)

theorem saturated_event_image {α β : Type*} [DecidableEq β]
 (v : α → β) (s : Finset α) (hs : EventSaturated v s) (x : α) :
 x ∈ s ↔ v x ∈ s.image v := by
 constructor
 · intro hx
   exact Finset.mem_image.mpr ⟨x, hx, rfl⟩
 · intro hx
   obtain ⟨y, hy, he⟩ := Finset.mem_image.mp hx
   exact (hs y x he).mp hy

/-- Hidden predicates have no descended finite event: the saturation
condition is necessary as well as sufficient, not just a refusal convention. -/
theorem event_descends_iff_saturated {α β : Type*} [DecidableEq β]
 (v : α → β) (s : Finset α) :
 (∃ t : Finset β, ∀ x, x ∈ s ↔ v x ∈ t) ↔ EventSaturated v s := by
 constructor
 · rintro ⟨t, ht⟩ x y he
   rw [ht x, ht y, he]
 · intro hs
   exact ⟨s.image v, saturated_event_image v s hs⟩

theorem event_projection_idempotent {α : Type*} [DecidableEq α]
 (v : α → α) (hv : ∀ x, v (v x) = v x) (s : Finset α) :
 (s.image v).image v = s.image v := by
 rw [Finset.image_image]
 congr 1
 funext x
 exact hv x

/-- Coarsening sums unnormalized matrix states, including zero states. -/
noncomputable def visibilityPushforward {α : Type*} [Fintype α]
 (v : α → α) (states : α → M2) (a : α) : M2 := by
 classical
 exact ∑ x : α, (if v x = a then (1 : ℝ) else 0) • states x

theorem visibilityPushforward_idempotent {α : Type*} [Fintype α]
 (v : α → α) (hv : ∀ x, v (v x) = v x) (states : α → M2) :
 visibilityPushforward v (visibilityPushforward v states) = visibilityPushforward v states := by
 classical
 funext a
 simp only [visibilityPushforward, Finset.smul_sum, smul_smul]
 rw [Finset.sum_comm]
 apply Finset.sum_congr rfl
 intro y _
 rw [Finset.sum_eq_single (v y)]
 · simp [hv y]
 · intro x _ hxy
   simp [Ne.symm hxy]
 · simp

theorem visibilityPushforward_sum {α : Type*} [Fintype α]
 (v : α → α) (states : α → M2) :
 (∑ a : α, visibilityPushforward v states a) = ∑ x : α, states x := by
 classical
 simp only [visibilityPushforward]
 rw [Finset.sum_comm]
 apply Finset.sum_congr rfl
 intro x _
 simp

theorem visibilityPushforward_psd {α : Type*} [Fintype α]
 (v : α → α) (states : α → M2) (hs : ∀ x, (states x).PosSemidef) (a : α) :
 (visibilityPushforward v states a).PosSemidef := by
 classical
 apply Matrix.posSemidef_sum Finset.univ
 intro x _
 exact (hs x).smul (by split_ifs <;> norm_num)

structure VisibilityPackage (α σ : Type*) [Fintype α] where
 visibility : α → α
 idempotent : ∀ x, visibility (visibility x) = visibility x
 ledger : σ
 states : α → M2

noncomputable def packageVisibility {α σ : Type*} [Fintype α]
 (p : VisibilityPackage α σ) : VisibilityPackage α σ :=
 {p with states := visibilityPushforward p.visibility p.states}

/-- The mathematical package projection preserves its public ledger and
policy literally and is idempotent on matrix laws. Serialization remains an
executable implementation check, not an assumption in this theorem. -/
theorem packageVisibility_idempotent {α σ : Type*} [Fintype α]
 (p : VisibilityPackage α σ) : packageVisibility (packageVisibility p) = packageVisibility p := by
 cases p with
 | mk v hv ledger states =>
   simp only [packageVisibility, visibilityPushforward_idempotent v hv]

theorem packageVisibility_ledger {α σ : Type*} [Fintype α]
 (p : VisibilityPackage α σ) : (packageVisibility p).ledger = p.ledger := rfl

end BornCalculus
