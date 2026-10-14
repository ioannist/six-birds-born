import BornCalculus.FrameSix
import BornCalculus.FiniteSimplex
import BornCalculus.MeasurableSix
import BornCalculus.Programs
namespace BornCalculus
open Matrix MeasureTheory
open scoped MatrixOrder BigOperators
set_option maxHeartbeats 0

noncomputable def gDensityEquiv (g₀ g₁ : ℝ) (h₀ : 0<g₀) (h₁ : 0<g₁) : GDensity g₀ g₁ ≃ Density :=
 Classical.choose (frame_coordinate_transfer g₀ g₁ h₀ h₁).density_bijection
noncomputable def gEffectEquiv (g₀ g₁ : ℝ) (h₀ : 0<g₀) (h₁ : 0<g₁) : GEffect g₀ g₁ ≃ Effect :=
 Classical.choose (frame_coordinate_transfer g₀ g₁ h₀ h₁).effect_bijection
theorem gDensityEquiv_val (g₀ g₁ : ℝ) (h₀ : 0<g₀) (h₁ : 0<g₁) (R : GDensity g₀ g₁) :
 (gDensityEquiv g₀ g₁ h₀ h₁ R).val=toOrth g₀ g₁ R.val :=
 Classical.choose_spec (frame_coordinate_transfer g₀ g₁ h₀ h₁).density_bijection R
theorem gEffectEquiv_val (g₀ g₁ : ℝ) (h₀ : 0<g₀) (h₁ : 0<g₁) (E : GEffect g₀ g₁) :
 (gEffectEquiv g₀ g₁ h₀ h₁ E).val=toOrth g₀ g₁ E.val :=
 Classical.choose_spec (frame_coordinate_transfer g₀ g₁ h₀ h₁).effect_bijection E

noncomputable def gUnitEffect (g₀ g₁ : ℝ) (h₀ : 0<g₀) (h₁ : 0<g₁) : GEffect g₀ g₁ :=
 ⟨1,(frame_coordinate_transfer g₀ g₁ h₀ h₁).effect_domain 1 |>.mpr (by
   rw [(frame_coordinate_transfer g₀ g₁ h₀ h₁).unit]; exact unitEffect.property)⟩
structure GValuation (g₀ g₁ : ℝ) (h₀ : 0<g₀) (h₁ : 0<g₁) where
 value : GEffect g₀ g₁ → ℝ
 nonnegative : ∀ E, 0≤value E
 normalized : value (gUnitEffect g₀ g₁ h₀ h₁)=1
 additive : ∀ E F H, H.val=E.val+F.val → value H=value E+value F

noncomputable def gValuationToOrth {g₀ g₁ : ℝ} {h₀ : 0<g₀} {h₁ : 0<g₁}
 (v : GValuation g₀ g₁ h₀ h₁) : Valuation where
 value E := v.value ((gEffectEquiv g₀ g₁ h₀ h₁).symm E)
 nonnegative E := v.nonnegative _
 normalized := by
   have he : gEffectEquiv g₀ g₁ h₀ h₁ (gUnitEffect g₀ g₁ h₀ h₁)=unitEffect := by
     apply Subtype.ext
     rw [gEffectEquiv_val]
     exact (frame_coordinate_transfer g₀ g₁ h₀ h₁).unit
   rw [←he,Equiv.symm_apply_apply]
   exact v.normalized
 additive E F H hh := by
   apply v.additive
   have h := frame_coordinate_transfer g₀ g₁ h₀ h₁
   apply (show Function.Injective (toOrth g₀ g₁) from by
     intro A B he; simpa [h.inverse_left] using congrArg (fromOrth g₀ g₁) he)
   rw [h.addition,←gEffectEquiv_val g₀ g₁ h₀ h₁ _,←gEffectEquiv_val g₀ g₁ h₀ h₁ _,←gEffectEquiv_val g₀ g₁ h₀ h₁ _]
   simpa using hh

theorem g_full_interval_trace_unique {g₀ g₁ : ℝ} {h₀ : 0<g₀} {h₁ : 0<g₁}
 (v : GValuation g₀ g₁ h₀ h₁) :
 ∃! R : GDensity g₀ g₁, ∀ E : GEffect g₀ g₁, v.value E=pairing R.val E.val := by
 let D := gDensityEquiv g₀ g₁ h₀ h₁
 let F := gEffectEquiv g₀ g₁ h₀ h₁
 have ht := (frame_coordinate_transfer g₀ g₁ h₀ h₁).trace_pairing
 obtain ⟨R,hr,hu⟩ := full_interval_trace_unique (gValuationToOrth v)
 refine ⟨D.symm R,?_,?_⟩
 · intro E
   have he := hr (F E)
   change v.value (F.symm (F E))=pairing R.val (F E).val at he
   rw [Equiv.symm_apply_apply] at he
   have hd : R.val=toOrth g₀ g₁ (D.symm R).val := by
     simpa [D] using (gDensityEquiv_val g₀ g₁ h₀ h₁ (D.symm R))
   rw [hd,gEffectEquiv_val,ht] at he
   exact he
 · intro Q hQ
   have hqr : D Q=R := hu (D Q) (by
     intro E
     have hh := hQ (F.symm E)
     have hd := gDensityEquiv_val g₀ g₁ h₀ h₁ Q
     have hf := gEffectEquiv_val g₀ g₁ h₀ h₁ (F.symm E)
     change (D Q).val=toOrth g₀ g₁ Q.val at hd
     change (F (F.symm E)).val=toOrth g₀ g₁ (F.symm E).val at hf
     rw [Equiv.apply_symm_apply] at hf
     change v.value (F.symm E)=pairing (D Q).val E.val
     rw [hd,hf,ht]
     exact hh)
   exact D.injective (by rw [hqr,Equiv.apply_symm_apply])

structure GFiniteSimplexModel (g₀ g₁ : ℝ) (h₀ : 0<g₀) (h₁ : 0<g₁) (N : ℕ) where
 response : Fin N → GValuation g₀ g₁ h₀ h₁
 weight : GDensity g₀ g₁ → Fin N → ℝ
 nonnegative : ∀ R i, 0≤weight R i
 normalized : ∀ R, ∑ i,weight R i=1
 reproduces : ∀ (R : GDensity g₀ g₁) (E : GEffect g₀ g₁),
   ∑ i,weight R i*(response i).value E=pairing R.val E.val

theorem g_no_finite_simplex_model (g₀ g₁ : ℝ) (h₀ : 0<g₀) (h₁ : 0<g₁)
 (N : ℕ) (M : GFiniteSimplexModel g₀ g₁ h₀ h₁ N) : False := by
 let D:=gDensityEquiv g₀ g₁ h₀ h₁
 let F:=gEffectEquiv g₀ g₁ h₀ h₁
 apply no_finite_simplex_model N
 refine ⟨fun i => gValuationToOrth (M.response i),fun R => M.weight (D.symm R),
   fun R i => M.nonnegative _ _,fun R => M.normalized _,?_⟩
 intro R E
 have hh := M.reproduces (D.symm R) (F.symm E)
 have hd := gDensityEquiv_val g₀ g₁ h₀ h₁ (D.symm R)
 have hf := gEffectEquiv_val g₀ g₁ h₀ h₁ (F.symm E)
 change (D (D.symm R)).val=toOrth g₀ g₁ (D.symm R).val at hd
 change (F (F.symm E)).val=toOrth g₀ g₁ (F.symm E).val at hf
 rw [Equiv.apply_symm_apply] at hd hf
 change (∑ i, M.weight (D.symm R) i*(M.response i).value (F.symm E))=pairing R.val E.val
 rw [hd,hf,(frame_coordinate_transfer g₀ g₁ h₀ h₁).trace_pairing]
 exact hh

structure GKrausTest (g₀ g₁ : ℝ) where
 arity : ℕ
 kraus : Fin arity → M2
 complete : ∑ i,gAdjoint g₀ g₁ (kraus i)*kraus i=1
noncomputable def gKrausToOrth {g₀ g₁ : ℝ} (h₀ : 0<g₀) (h₁ : 0<g₁)
 (C : GKrausTest g₀ g₁) : KrausTest where
 arity := C.arity
 kraus i := toOrth g₀ g₁ (C.kraus i)
 complete := by
   have h := frame_coordinate_transfer g₀ g₁ h₀ h₁
   have hsum : ∀ f : Fin C.arity → M2,
     toOrth g₀ g₁ (∑ i,f i)=∑ i,toOrth g₀ g₁ (f i) := by
     intro f; simp [toOrth,Matrix.mul_sum,Matrix.sum_mul]
   simp only [←h.adjoint,←h.multiplication,←hsum,C.complete,h.unit]

/-- The metric adjoint, rather than entrywise transpose, is used on G. -/
theorem g_branch_correspondence (g₀ g₁ : ℝ) (h₀ : 0<g₀) (h₁ : 0<g₁) (A R : M2) :
 toOrth g₀ g₁ (A*R*gAdjoint g₀ g₁ A)=branch (toOrth g₀ g₁ A) (toOrth g₀ g₁ R) := by
 have h:=frame_coordinate_transfer g₀ g₁ h₀ h₁
 rw [h.multiplication,h.multiplication,h.adjoint]
 rfl

theorem g_program_normalization (g₀ g₁ : ℝ) (h₀ : 0<g₀) (h₁ : 0<g₁)
 (P : List (GKrausTest g₀ g₁)) (R : GDensity g₀ g₁) :
 ∑ w : Outcomes (P.map (gKrausToOrth h₀ h₁)),
   wordMass (P.map (gKrausToOrth h₀ h₁)) w (gDensityEquiv g₀ g₁ h₀ h₁ R).val=1 :=
 program_mass_sum _ _

/-- T4/T5 distribution hypotheses are coordinate-free. Frame-table premises
 are supplied separately by six_state_g_transfer, not assumed as new axioms. -/
theorem g_finite_six_no_go {Λ : Type*} [Fintype Λ] (M : FiniteSixModel Λ) : False := finite_six_no_go M
theorem g_measurable_six_no_go {Ω : Type*} [MeasurableSpace Ω] (M : MeasurableSixModel Ω) : False := measurable_six_no_go M


noncomputable def gTraceValuation (g₀ g₁ : ℝ) (h₀ : 0<g₀) (h₁ : 0<g₁)
 (R : GDensity g₀ g₁) : GValuation g₀ g₁ h₀ h₁ where
 value E := pairing R.val E.val
 nonnegative E := by
   rw [←(frame_coordinate_transfer g₀ g₁ h₀ h₁).trace_pairing]
   exact trace_pairing_nonnegative _ _
     ((frame_coordinate_transfer g₀ g₁ h₀ h₁).density_domain R.val |>.mp R.property).1
     ((frame_coordinate_transfer g₀ g₁ h₀ h₁).effect_domain E.val |>.mp E.property).1
 normalized := by simpa [pairing,gUnitEffect] using R.property.2
 additive E F H h := by simp [pairing,h,Matrix.mul_add,Matrix.trace_add]

theorem g_branch_closure (g₀ g₁ : ℝ) (h₀ : 0<g₀) (h₁ : 0<g₁)
 (A : M2) (R : GDensity g₀ g₁) : GPositive g₀ g₁ (A*R.val*gAdjoint g₀ g₁ A) := by
 have h:=frame_coordinate_transfer g₀ g₁ h₀ h₁
 rw [h.positive,g_branch_correspondence g₀ g₁ h₀ h₁]
 exact branch_psd _ _ ((h.density_domain R.val).mp R.property).1

/-- Conclusions 1–5 are the enumerated metric/coordinate laws. Conclusion 6
 explicitly records the proved T1–T5 applications; none is supplied by hypothesis. -/
structure FrameTransferLaws (g₀ g₁ : ℝ) : Prop extends FrameCoordinateLaws g₀ g₁ where
 T1 : ∀ (h₀ : 0<g₀) (h₁ : 0<g₁) (v : GValuation g₀ g₁ h₀ h₁),
   ∃! R : GDensity g₀ g₁, ∀ E : GEffect g₀ g₁,v.value E=pairing R.val E.val
 T2 : ∀ (h₀ : 0<g₀) (h₁ : 0<g₁) (N : ℕ),GFiniteSimplexModel g₀ g₁ h₀ h₁ N → False
 T3_branch : ∀ (h₀ : 0<g₀) (h₁ : 0<g₁) (A : M2) (R : GDensity g₀ g₁),
   GPositive g₀ g₁ (A*R.val*gAdjoint g₀ g₁ A)
 T3_program : ∀ (h₀ : 0<g₀) (h₁ : 0<g₁) (P : List (GKrausTest g₀ g₁)) (R : GDensity g₀ g₁),
   ∑ w : Outcomes (P.map (gKrausToOrth h₀ h₁)),wordMass (P.map (gKrausToOrth h₀ h₁)) w
     (gDensityEquiv g₀ g₁ h₀ h₁ R).val=1
 T4 : ∀ {Λ : Type*} [Fintype Λ],FiniteSixModel Λ → False
 T5 : ∀ {Ω : Type*} [MeasurableSpace Ω],MeasurableSixModel Ω → False

theorem g_frame_transfer (g₀ g₁ : ℝ) (h₀ : 0<g₀) (h₁ : 0<g₁) : FrameTransferLaws g₀ g₁ where
 toFrameCoordinateLaws := frame_coordinate_transfer g₀ g₁ h₀ h₁
 T1 _ _ := g_full_interval_trace_unique
 T2 h₀ h₁ N := g_no_finite_simplex_model g₀ g₁ h₀ h₁ N
 T3_branch h₀ h₁ A R := g_branch_closure g₀ g₁ h₀ h₁ A R
 T3_program h₀ h₁ P R := g_program_normalization g₀ g₁ h₀ h₁ P R
 T4 := finite_six_no_go
 T5 := measurable_six_no_go
end BornCalculus
