import BornCalculus.RootChart
import BornCalculus.B04Exact

namespace BornCalculus
open Matrix
open scoped BigOperators
set_option maxHeartbeats 0

noncomputable def b04S : ℝ := (b04SQ : ℝ)
theorem b04_s_positive : 0 < b04S := by
 dsimp [b04S]
 exact_mod_cast b04_s_positiveQ

noncomputable def b04W (i : Fin 32) : ℝ := (b04WQ i : ℝ)
noncomputable def b04K : Matrix (Fin 32) (Fin 32) ℝ := fun i j => (b04KQ i j : ℝ)
noncomputable def b04Source (e : Fin 4) (side : Fin 2) : Simplex32 :=
 ⟨fun i => (b04PQ e side i : ℝ), ⟨fun i => by
   change (0 : ℝ) ≤ (b04PQ e side i : ℝ)
   exact_mod_cast (b04_initial_simplexQ e side).2 i,
   by
     change (∑ i : Fin 32, (b04PQ e side i : ℝ)) = 1
     exact_mod_cast (b04_initial_simplexQ e side).1⟩⟩
noncomputable def b04Mid (e : Fin 4) (side : Fin 2) : Fin 32 → ℝ :=
 fun i => (b04MidQ e side i : ℝ)
noncomputable def b04Future (e : Fin 4) (side : Fin 2) : Fin 32 → ℝ :=
 fun i => (b04FutureQ e side i : ℝ)
noncomputable def b04Chart (p : Fin 32 → ℝ) : ℝ := rootChart b04W b04S p
noncomputable def b04Update (e : Fin 4) (p : Fin 32 → ℝ) : Fin 32 → ℝ :=
 if e.val % 2 = 0 then b04Kᵀ *ᵥ p else b04Kᵀ *ᵥ (b04Kᵀ *ᵥ p)

private theorem b04_cast_linearRoot (a lo hi : Fin 32 → ℚ) (i : Fin 32) :
 lowerLinearRoot (fun j => (a j : ℝ)) (fun j => (lo j : ℝ)) (fun j => (hi j : ℝ)) i =
   (lowerLinearRootQ a lo hi i : ℝ) := by
 by_cases h : 0 ≤ a i
 · have hr : (0 : ℝ) ≤ (a i : ℝ) := by exact_mod_cast h
   simp [lowerLinearRoot, lowerLinearRootQ, h, hr]
 · have hr : ¬(0 : ℝ) ≤ (a i : ℝ) := by exact_mod_cast h
   simp [lowerLinearRoot, lowerLinearRootQ, h, hr]

theorem b04_initial_chart_zero (e : Fin 4) (side : Fin 2) :
 b04Chart (b04Source e side).val = 0 := by
 have hq := b04_relative_rootsQ e side
 have hp : (0 : ℝ) < (b04PQ e side 0 : ℝ) := by exact_mod_cast hq.1
 have hr : ∀ i : Fin 32, (0 : ℝ) ≤ (b04RootsQ e side i : ℝ) ∧
   (b04RootsQ e side i : ℝ)^2 = (b04PQ e side i : ℝ)/(b04PQ e side 0 : ℝ) := by
   intro i
   exact_mod_cast hq.2.1 i
 have hs : (0 : ℝ) < ∑ i : Fin 32, (b04RootsQ e side i : ℝ) := by exact_mod_cast hq.2.2.1
 have hw : (∑ i : Fin 32, b04W i * (b04RootsQ e side i : ℝ)) = 0 := by
   dsimp [b04W]
   exact_mod_cast hq.2.2.2
 change rootChart b04W b04S (fun i => (b04PQ e side i : ℝ)) = 0
 rw [rootChart_of_relative_roots b04W
   (fun i => (b04RootsQ e side i : ℝ)) _ b04S (b04PQ e side 0 : ℝ) hp hr hs, hw]
 simp

theorem b04_mid_is_kernel_update (e : Fin 4) (side : Fin 2) :
 b04Mid e side = b04Kᵀ *ᵥ (b04Source e side).val := by
 funext j
 have h := congrArg (fun v : Fin 32 → ℚ => (v j : ℝ)) (b04_mid_stepQ e side)
 simpa [b04Mid, b04K, b04Source, mulVec, dotProduct, transpose_apply] using h

theorem b04_future_is_kernel_update (e : Fin 4) (side : Fin 2) :
 b04Future e side = b04Update e (b04Source e side).val := by
 unfold b04Update
 rw [← b04_mid_is_kernel_update e side]
 funext j
 have h := congrArg (fun v : Fin 32 → ℚ => (v j : ℝ)) (b04_future_stepQ e side)
 by_cases he : e.val % 2 = 0 <;>
   simpa [b04Future,b04Mid,b04K,mulVec,dotProduct,transpose_apply,he] using h

theorem b04_future_chart_bounds (e : Fin 4) (side : Fin 2) :
 (b04LowerQ e side : ℝ) ≤ b04Chart (b04Future e side) ∧
   b04Chart (b04Future e side) ≤ (b04UpperQ e side : ℝ) := by
 have hq := b04_root_squaresQ e side
 have hb : ∀ i, (0 : ℝ) ≤ (b04LoQ e side i : ℝ) ∧ 0 ≤ (b04HiQ e side i : ℝ) ∧
   (b04LoQ e side i : ℝ)^2 ≤ b04Future e side i ∧
   b04Future e side i ≤ (b04HiQ e side i : ℝ)^2 := by
   intro i
   dsimp [b04Future]
   exact_mod_cast hq.1 i
 have hs : (0 : ℝ) < ∑ i : Fin 32, (b04LoQ e side i : ℝ) := by exact_mod_cast hq.2
 have hl : (0 : ℝ) ≤ ∑ i : Fin 32, lowerLinearRoot
   (fun i => (32/b04S)*b04W i-(b04LowerQ e side : ℝ))
   (fun i => (b04LoQ e side i : ℝ)) (fun i => (b04HiQ e side i : ℝ)) i := by
   have he : (∑ i : Fin 32, lowerLinearRoot
     (fun i => (32/b04S)*b04W i-(b04LowerQ e side : ℝ))
     (fun i => (b04LoQ e side i : ℝ)) (fun i => (b04HiQ e side i : ℝ)) i) =
     (∑ i : Fin 32, lowerLinearRootQ
       (fun i => (32/b04SQ)*b04WQ i-b04LowerQ e side)
       (b04LoQ e side) (b04HiQ e side) i : ℚ) := by
     rw [Rat.cast_sum]
     apply Finset.sum_congr rfl
     intro i _
     simpa [b04W,b04S] using b04_cast_linearRoot
       (fun i => (32/b04SQ)*b04WQ i-b04LowerQ e side) (b04LoQ e side) (b04HiQ e side) i
   rw [he]
   exact_mod_cast b04_chart_lower_checkQ e side
 have hu : (0 : ℝ) ≤ ∑ i : Fin 32, lowerLinearRoot
   (fun i => (b04UpperQ e side : ℝ)-(32/b04S)*b04W i)
   (fun i => (b04LoQ e side i : ℝ)) (fun i => (b04HiQ e side i : ℝ)) i := by
   have he : (∑ i : Fin 32, lowerLinearRoot
     (fun i => (b04UpperQ e side : ℝ)-(32/b04S)*b04W i)
     (fun i => (b04LoQ e side i : ℝ)) (fun i => (b04HiQ e side i : ℝ)) i) =
     (∑ i : Fin 32, lowerLinearRootQ
       (fun i => b04UpperQ e side-(32/b04SQ)*b04WQ i)
       (b04LoQ e side) (b04HiQ e side) i : ℚ) := by
     rw [Rat.cast_sum]
     apply Finset.sum_congr rfl
     intro i _
     simpa [b04W,b04S] using b04_cast_linearRoot
       (fun i => b04UpperQ e side-(32/b04SQ)*b04WQ i) (b04LoQ e side) (b04HiQ e side) i
   rw [he]
   exact_mod_cast b04_chart_upper_checkQ e side
 exact rootChart_bounds b04W (b04Future e side)
   (fun i => (b04LoQ e side i : ℝ)) (fun i => (b04HiQ e side i : ℝ))
   b04S (b04LowerQ e side : ℝ) (b04UpperQ e side : ℝ) hb hs hl hu

theorem b04_successor_charts_differ (e : Fin 4) :
 b04Chart (b04Update e (b04Source e 0).val) ≠
   b04Chart (b04Update e (b04Source e 1).val) := by
 rw [← b04_future_is_kernel_update, ← b04_future_is_kernel_update]
 have h0 := b04_future_chart_bounds e 0
 have h1 := b04_future_chart_bounds e 1
 have hn : (b04UpperQ e 0 : ℝ) < (b04LowerQ e 1 : ℝ) ∨
   (b04UpperQ e 1 : ℝ) < (b04LowerQ e 0 : ℝ) := by exact_mod_cast b04_chart_nonoverlapQ e
 rcases hn with hn | hn <;> intro he <;> linarith

theorem b04_encoder_no_lift (e : Fin 4) :
 ¬ ∃ f : ℝ → ℝ, ∀ p : Simplex32,
   b04Chart (b04Update e p.val) = f (b04Chart p.val) := by
 exact fiber_split_no_factor (fun p : Simplex32 => b04Chart p.val)
   (fun p : Simplex32 => b04Chart (b04Update e p.val))
   (b04Source e 0) (b04Source e 1)
   (by
     change b04Chart (b04Source e 0).val = b04Chart (b04Source e 1).val
     rw [b04_initial_chart_zero,b04_initial_chart_zero]) (b04_successor_charts_differ e)

def b04Lens : Fin 3 → Fin 32 → Fin 3 := ![b04Raw,b04Package,b04Joint]
noncomputable def b04PassiveRecord (p : Simplex32) : Fin 3 → Fin 3 → ℝ :=
 fun f j => ∑ i : Fin 32, if b04Lens f i = j then p.val i else 0
noncomputable def b04JoinedView (p : Simplex32) := (b04Chart p.val,b04PassiveRecord p)

theorem b04_joined_records_equal (e : Fin 2) :
 b04PassiveRecord (b04Source ⟨e.val+2,by omega⟩ 0) =
   b04PassiveRecord (b04Source ⟨e.val+2,by omega⟩ 1) := by
 have hq := b04_joined_record_equalQ e
 funext f j
 fin_cases f
 · have h := congrArg (fun q : ℚ => (q : ℝ)) (hq.1 j)
   simpa [b04PassiveRecord,b04Lens,b04Source,recordMarginalQ,apply_ite] using h
 · have h := congrArg (fun q : ℚ => (q : ℝ)) (hq.2.1 j)
   simpa [b04PassiveRecord,b04Lens,b04Source,recordMarginalQ,apply_ite] using h
 · have h := congrArg (fun q : ℚ => (q : ℝ)) (hq.2.2 j)
   simpa [b04PassiveRecord,b04Lens,b04Source,recordMarginalQ,apply_ite,
     Matrix.cons_val_two,Matrix.head_cons,Matrix.tail_cons] using h

theorem b04_joined_view_equal (e : Fin 2) :
 b04JoinedView (b04Source ⟨e.val+2,by omega⟩ 0) =
   b04JoinedView (b04Source ⟨e.val+2,by omega⟩ 1) := by
 simp only [b04JoinedView,b04_initial_chart_zero,b04_joined_records_equal]

/-- Both registered joined-state witnesses keep the three passive marginal
laws as well as the encoded chart. Fixed context fields remain parameters;
no history reconstruction or native formation is asserted. -/
theorem b04_joined_no_lift (e : Fin 2) :
 ¬ ∃ f : ℝ × (Fin 3 → Fin 3 → ℝ) → ℝ, ∀ p : Simplex32,
   b04Chart (b04Update ⟨e.val+2,by omega⟩ p.val) = f (b04JoinedView p) := by
 exact fiber_split_no_factor b04JoinedView
   (fun p : Simplex32 => b04Chart (b04Update ⟨e.val+2,by omega⟩ p.val))
   (b04Source ⟨e.val+2,by omega⟩ 0) (b04Source ⟨e.val+2,by omega⟩ 1)
   (b04_joined_view_equal e) (b04_successor_charts_differ _)


noncomputable def b04Density (p : Fin 32 → ℝ) : M2 :=
 chartDensity b04S (b04Chart p)

theorem b04_density_domain (p : Fin 32 → ℝ) : GIsDensity 32 b04S (b04Density p) :=
 chartDensity_domain b04S (b04Chart p) b04_s_positive

theorem b04_density_no_lift (e : Fin 4) :
 ¬ ∃ f : M2 → M2, ∀ p : Simplex32,
   b04Density (b04Update e p.val) = f (b04Density p.val) := by
 apply fiber_split_no_factor (fun p : Simplex32 => b04Density p.val)
   (fun p : Simplex32 => b04Density (b04Update e p.val))
   (b04Source e 0) (b04Source e 1)
 · simp only [b04Density,b04_initial_chart_zero]
 · intro he
   exact b04_successor_charts_differ e
     (chartDensity_injective b04S b04_s_positive he)

noncomputable def b04JoinedDensityView (p : Simplex32) :=
 (b04Density p.val,b04PassiveRecord p)

theorem b04_joined_density_no_lift (e : Fin 2) :
 ¬ ∃ f : M2 × (Fin 3 → Fin 3 → ℝ) → M2, ∀ p : Simplex32,
   b04Density (b04Update ⟨e.val+2,by omega⟩ p.val) = f (b04JoinedDensityView p) := by
 apply fiber_split_no_factor b04JoinedDensityView
   (fun p : Simplex32 => b04Density (b04Update ⟨e.val+2,by omega⟩ p.val))
   (b04Source ⟨e.val+2,by omega⟩ 0) (b04Source ⟨e.val+2,by omega⟩ 1)
 · simp only [b04JoinedDensityView,b04Density,b04_initial_chart_zero,
     b04_joined_records_equal]
 · intro he
   exact b04_successor_charts_differ _
     (chartDensity_injective b04S b04_s_positive he)

end BornCalculus
