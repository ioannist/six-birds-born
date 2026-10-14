import BornCalculus.CenteredFrame

namespace BornCalculus
open Matrix
open scoped BigOperators

/-- The domain is exactly the image, so no inhabitedness assumption on the
output or extension to unencoded states is hidden in the criterion. -/
theorem factor_on_image_iff {α β γ : Type*} (view : α → β) (read : α → γ) :
 (∃ f : Set.range view → γ, ∀ x, read x = f ⟨view x, ⟨x,rfl⟩⟩) ↔
 (∀ x y, view x = view y → read x = read y) := by
 classical
 constructor
 · rintro ⟨f,hf⟩ x y he
   rw [hf x,hf y]
   congr 1
   exact Subtype.ext he
 · intro h
   let pick (b : Set.range view) : α := Classical.choose b.property
   have hp (b : Set.range view) : view (pick b) = b.val := Classical.choose_spec b.property
   refine ⟨fun b => read (pick b), ?_⟩
   intro x
   exact h x (pick ⟨view x,⟨x,rfl⟩⟩) (hp ⟨view x,⟨x,rfl⟩⟩).symm

theorem frame_lift_iff (F : CenteredFrame32) (T : Simplex32 → Simplex32) :
 (∃ f : Set.range (frameEncoding F) → M2, ∀ p,
   frameEncoding F (T p) = f ⟨frameEncoding F p,⟨p,rfl⟩⟩) ↔
 (∀ p q, frameEncoding F p = frameEncoding F q →
   frameEncoding F (T p) = frameEncoding F (T q)) :=
 factor_on_image_iff (frameEncoding F) (fun p => frameEncoding F (T p))

theorem frame_augmented_lift_iff {β : Type*} (F : CenteredFrame32)
 (rec : Simplex32 → β) (T : Simplex32 → Simplex32) :
 (∃ f : Set.range (fun p => (rec p,frameEncoding F p)) → M2, ∀ p,
   frameEncoding F (T p) = f ⟨(rec p,frameEncoding F p),⟨p,rfl⟩⟩) ↔
 (∀ p q, rec p = rec q → frameEncoding F p = frameEncoding F q →
   frameEncoding F (T p) = frameEncoding F (T q)) := by
 rw [factor_on_image_iff]
 simp only [Prod.mk.injEq, and_imp]

/-- Row-vector convention p K, implemented as K transpose times p. -/
noncomputable def normalizedKernel32 (K : Matrix (Fin 32) (Fin 32) ℝ)
 (p : Simplex32) : Fin 32 → ℝ :=
 fun j => (Kᵀ *ᵥ p.val) j / (∑ i, (Kᵀ *ᵥ p.val) i)

theorem normalizedKernel32_identity (p : Simplex32) :
 normalizedKernel32 1 p = p.val := by
 funext i
 simp [normalizedKernel32, p.property.2]

theorem normalizedKernel32_identical_rows (r : Fin 32 → ℝ) (p : Simplex32) :
 normalizedKernel32 (fun _ j => r j) p = fun j => r j / (∑ i, r i) := by
 have hu : (fun _ j => r j : Matrix (Fin 32) (Fin 32) ℝ)ᵀ *ᵥ p.val = r := by
   funext j
   simp [mulVec, dotProduct, transpose_apply, ← Finset.mul_sum, p.property.2]
 unfold normalizedKernel32
 rw [hu]

theorem normalized_identical_row_simplex (r : Fin 32 → ℝ)
 (hr : ∀ i, 0 ≤ r i) (hs : 0 < ∑ i, r i) :
 (∀ j, 0 ≤ r j / (∑ i, r i)) ∧ (∑ j, r j / (∑ i, r i)) = 1 := by
 exact ⟨fun j => div_nonneg (hr j) hs.le, by rw [← Finset.sum_div,div_self hs.ne']⟩

theorem frame_identity_matrix_lift (F : CenteredFrame32) :
 ∃ f : Set.range (frameEncoding F) → M2, ∀ p : Simplex32,
 chartDensity F.s (rootChart F.w F.s (normalizedKernel32 1 p)) =
   f ⟨frameEncoding F p,⟨p,rfl⟩⟩ := by
 refine ⟨Subtype.val, ?_⟩
 intro p
 rw [normalizedKernel32_identity]
 rfl

theorem frame_identical_rows_lift (F : CenteredFrame32) (r : Fin 32 → ℝ)
 (hr : ∀ i, 0 ≤ r i) (hs : 0 < ∑ i, r i) :
 ∃ f : Set.range (frameEncoding F) → M2, ∀ p : Simplex32,
 chartDensity F.s (rootChart F.w F.s (normalizedKernel32 (fun _ j => r j) p)) =
   f ⟨frameEncoding F p,⟨p,rfl⟩⟩ := by
 let q : Simplex32 := ⟨fun j => r j / (∑ i, r i), normalized_identical_row_simplex r hr hs⟩
 refine ⟨fun _ => frameEncoding F q, ?_⟩
 intro p
 rw [normalizedKernel32_identical_rows]
 rfl

/-- The normalized trivial examples hold in arbitrary finite dimension,
before applying the general image factorization criterion. -/
theorem normalized_identity_general {α : Type*} [Fintype α] [DecidableEq α]
 (p : α → ℝ) (hp : ∑ i, p i = 1) :
 (fun j => ((1 : Matrix α α ℝ)ᵀ *ᵥ p) j / (∑ i, ((1 : Matrix α α ℝ)ᵀ *ᵥ p) i)) = p := by
 funext j
 simp [hp]

theorem normalized_identical_rows_general {α : Type*} [Fintype α]
 (p r : α → ℝ) (hp : ∑ i, p i = 1) :
 (fun j => ((fun _ j => r j : Matrix α α ℝ)ᵀ *ᵥ p) j /
   (∑ i, ((fun _ j => r j : Matrix α α ℝ)ᵀ *ᵥ p) i)) =
   (fun j => r j / (∑ i, r i)) := by
 have hu : (fun _ j => r j : Matrix α α ℝ)ᵀ *ᵥ p = r := by
   funext j
   simp [mulVec,dotProduct,transpose_apply,← Finset.mul_sum,hp]
 rw [hu]

#print axioms normalized_identity_general
#print axioms normalized_identical_rows_general

#print axioms factor_on_image_iff
#print axioms frame_lift_iff
#print axioms frame_augmented_lift_iff
#print axioms normalizedKernel32_identity
#print axioms normalizedKernel32_identical_rows
#print axioms normalized_identical_row_simplex
#print axioms frame_identity_matrix_lift
#print axioms frame_identical_rows_lift
end BornCalculus
