import BornCalculus.Instruments
import BornCalculus.SixStates

namespace BornCalculus
open Matrix
open scoped MatrixOrder BigOperators
set_option maxHeartbeats 0
noncomputable def frameS (g₀ g₁ : ℝ) : M2 := Matrix.diagonal ![Real.sqrt g₀,Real.sqrt g₁]
noncomputable def frameSi (g₀ g₁ : ℝ) : M2 := Matrix.diagonal ![(Real.sqrt g₀)⁻¹,(Real.sqrt g₁)⁻¹]
noncomputable def frameG (g₀ g₁ : ℝ) : M2 := Matrix.diagonal ![g₀,g₁]
noncomputable def toOrth (g₀ g₁ : ℝ) (A : M2) : M2 := frameS g₀ g₁*A*frameSi g₀ g₁
noncomputable def fromOrth (g₀ g₁ : ℝ) (A : M2) : M2 := frameSi g₀ g₁*A*frameS g₀ g₁
noncomputable def gAdjoint (g₀ g₁ : ℝ) (A : M2) : M2 := (frameG g₀ g₁)⁻¹*Aᵀ*frameG g₀ g₁
/- Metric positivity independently uses the quadratic form and symmetry of GA,
 not the definition of toOrth or any valuation/representation theorem. -/
def GPositive (g₀ g₁ : ℝ) (A : M2) : Prop := (frameG g₀ g₁*A).PosSemidef
def GIsDensity (g₀ g₁ : ℝ) (A : M2) : Prop := GPositive g₀ g₁ A ∧ Matrix.trace A=1
def GIsEffect (g₀ g₁ : ℝ) (A : M2) : Prop := GPositive g₀ g₁ A ∧ GPositive g₀ g₁ (1-A)
abbrev GDensity (g₀ g₁ : ℝ) := {A : M2 // GIsDensity g₀ g₁ A}
abbrev GEffect (g₀ g₁ : ℝ) := {A : M2 // GIsEffect g₀ g₁ A}
noncomputable def gRoot (g₀ g₁ : ℝ) (A : M2) : M2 := fromOrth g₀ g₁ (CFC.sqrt (toOrth g₀ g₁ A))

private theorem frame_inverse (g₀ g₁ : ℝ) (h₀ : 0<g₀) (h₁ : 0<g₁) :
 frameS g₀ g₁*frameSi g₀ g₁=1 ∧ frameSi g₀ g₁*frameS g₀ g₁=1 := by
 have h0 : Real.sqrt g₀≠0 := (Real.sqrt_pos.2 h₀).ne'
 have h1 : Real.sqrt g₁≠0 := (Real.sqrt_pos.2 h₁).ne'
 constructor <;> ext i j <;> fin_cases i <;> fin_cases j <;>
 simp [frameS,frameSi,Matrix.mul_apply,Fin.sum_univ_two,h0,h1]
private theorem frame_metric (g₀ g₁ : ℝ) (h₀ : 0<g₀) (h₁ : 0<g₁) :
 frameG g₀ g₁=(frameS g₀ g₁)ᵀ*frameS g₀ g₁ := by
 ext i j; fin_cases i <;> fin_cases j <;>
 simp [frameG,frameS,Matrix.mul_apply,Fin.sum_univ_two,Real.mul_self_sqrt h₀.le,Real.mul_self_sqrt h₁.le]
private theorem frame_symm (g₀ g₁ : ℝ) :
 (frameS g₀ g₁)ᵀ=frameS g₀ g₁ ∧ (frameSi g₀ g₁)ᵀ=frameSi g₀ g₁ := by
 constructor <;> simp [frameS,frameSi]

private theorem conjugate_mul (S T A B : M2) (h : T*S=1) :
 S*(A*B)*T=(S*A*T)*(S*B*T) := by
 calc
  S*(A*B)*T=(S*A)*1*(B*T) := by noncomm_ring
  _=(S*A)*(T*S)*(B*T) := by rw [h]
  _=(S*A*T)*(S*B*T) := by noncomm_ring
private theorem conjugate_inverse (S T A : M2) (h : S*T=1) : S*(T*A*S)*T=A := by
 calc
  S*(T*A*S)*T=(S*T)*A*(S*T) := by noncomm_ring
  _=A := by rw [h]; simp
private theorem conjugate_trace (S T A : M2) (h : T*S=1) : Matrix.trace (S*A*T)=Matrix.trace A := by
 calc
  Matrix.trace (S*A*T)=Matrix.trace (T*(S*A)) := Matrix.trace_mul_comm _ _
  _=Matrix.trace ((T*S)*A) := by rw [Matrix.mul_assoc]
  _=Matrix.trace A := by rw [h]; simp

structure FrameCoordinateLaws (g₀ g₁ : ℝ) : Prop where
 S_invertible : IsUnit (frameS g₀ g₁)
 S_inverse : (frameS g₀ g₁)⁻¹=frameSi g₀ g₁
 metric : frameG g₀ g₁=(frameS g₀ g₁)ᵀ*frameS g₀ g₁
 adjoint : ∀ A, toOrth g₀ g₁ (gAdjoint g₀ g₁ A)=(toOrth g₀ g₁ A)ᵀ
 selfadjoint : ∀ A, gAdjoint g₀ g₁ A=A ↔ (toOrth g₀ g₁ A).IsHermitian
 quadratic_form : ∀ A, GPositive g₀ g₁ A ↔
  gAdjoint g₀ g₁ A=A ∧ ∀ x : Fin 2 → ℝ, 0 ≤ x ⬝ᵥ ((frameG g₀ g₁*A) *ᵥ x)
 positive : ∀ A, GPositive g₀ g₁ A ↔ (toOrth g₀ g₁ A).PosSemidef
 density_domain : ∀ A, GIsDensity g₀ g₁ A ↔ IsDensity (toOrth g₀ g₁ A)
 effect_domain : ∀ A, GIsEffect g₀ g₁ A ↔ IsEffect (toOrth g₀ g₁ A)
 inverse_left : ∀ A, fromOrth g₀ g₁ (toOrth g₀ g₁ A)=A
 inverse_right : ∀ A, toOrth g₀ g₁ (fromOrth g₀ g₁ A)=A
 density_bijection : ∃ e : GDensity g₀ g₁ ≃ Density, ∀ R, (e R).val=toOrth g₀ g₁ R.val
 effect_bijection : ∃ e : GEffect g₀ g₁ ≃ Effect, ∀ E, (e E).val=toOrth g₀ g₁ E.val
 multiplication : ∀ A B, toOrth g₀ g₁ (A*B)=toOrth g₀ g₁ A*toOrth g₀ g₁ B
 addition : ∀ A B, toOrth g₀ g₁ (A+B)=toOrth g₀ g₁ A+toOrth g₀ g₁ B
 scalar : ∀ (t : ℝ) A, toOrth g₀ g₁ (t • A)=t • toOrth g₀ g₁ A
 unit : toOrth g₀ g₁ 1=1
 trace : ∀ A, Matrix.trace (toOrth g₀ g₁ A)=Matrix.trace A
 trace_pairing : ∀ R E, pairing (toOrth g₀ g₁ R) (toOrth g₀ g₁ E)=pairing R E
 principal_roots : ∀ A, toOrth g₀ g₁ (gRoot g₀ g₁ A)=CFC.sqrt (toOrth g₀ g₁ A)
 principal_root_characterization : ∀ E, GPositive g₀ g₁ E →
  ∃! A, GPositive g₀ g₁ A ∧ A*A=E

theorem frame_coordinate_transfer (g₀ g₁ : ℝ) (h₀ : 0<g₀) (h₁ : 0<g₁) : FrameCoordinateLaws g₀ g₁ := by
 let S:=frameS g₀ g₁; let T:=frameSi g₀ g₁; let G:=frameG g₀ g₁
 have hST : S*T=1 := (frame_inverse g₀ g₁ h₀ h₁).1
 have hTS : T*S=1 := (frame_inverse g₀ g₁ h₀ h₁).2
 have hs : Sᵀ=S := (frame_symm g₀ g₁).1
 have ht : Tᵀ=T := (frame_symm g₀ g₁).2
 have hg : G=S*S := by change frameG g₀ g₁ = S*S; rw [frame_metric g₀ g₁ h₀ h₁]; change Sᵀ*S=S*S; rw [hs]
 have hgi : G⁻¹=T*T := Matrix.inv_eq_left_inv (by rw [hg]; calc
   (T*T)*(S*S)=T*(T*S)*S := by noncomm_ring
   _=1 := by rw [hTS]; simpa using hTS)
 have hi A : fromOrth g₀ g₁ (toOrth g₀ g₁ A)=A := conjugate_inverse T S A hTS
 have hir A : toOrth g₀ g₁ (fromOrth g₀ g₁ A)=A := conjugate_inverse S T A hST
 have hm A B : toOrth g₀ g₁ (A*B)=toOrth g₀ g₁ A*toOrth g₀ g₁ B := conjugate_mul S T A B hTS
 have hadd A B : toOrth g₀ g₁ (A+B)=toOrth g₀ g₁ A+toOrth g₀ g₁ B := by simp [toOrth,Matrix.mul_add,Matrix.add_mul]
 have hunit : toOrth g₀ g₁ 1=1 := by simpa [toOrth] using hST
 have hsub A B : toOrth g₀ g₁ (A-B)=toOrth g₀ g₁ A-toOrth g₀ g₁ B := by simp [toOrth,Matrix.mul_sub,Matrix.sub_mul]
 have htrace A : Matrix.trace (toOrth g₀ g₁ A)=Matrix.trace A := conjugate_trace S T A hTS
 have hd A : toOrth g₀ g₁ (gAdjoint g₀ g₁ A)=(toOrth g₀ g₁ A)ᵀ := by
  change S*(G⁻¹*Aᵀ*G)*T=(S*A*T)ᵀ
  rw [hgi,hg]
  calc
   S*((T*T)*Aᵀ*(S*S))*T=(S*T)*T*Aᵀ*S*(S*T) := by noncomm_ring
   _=(S*A*T)ᵀ := by rw [hST]; simp [Matrix.transpose_mul,hs,ht,Matrix.mul_assoc]
 have hsa A : gAdjoint g₀ g₁ A=A ↔ (toOrth g₀ g₁ A).IsHermitian := by
  rw [Matrix.IsHermitian,Matrix.conjTranspose_eq_transpose_of_trivial,← hd]
  constructor
  · intro h; rw [h]
  · intro h; simpa [hi] using congrArg (fromOrth g₀ g₁) h
 have hpos A : GPositive g₀ g₁ A ↔ (toOrth g₀ g₁ A).PosSemidef := by
  have he : T*(G*A)*Tᵀ=toOrth g₀ g₁ A := by
   rw [ht,hg]; change T*((S*S)*A)*T=S*A*T
   calc
    T*((S*S)*A)*T=(T*S)*S*A*T := by noncomm_ring
    _=S*A*T := by rw [hTS]; simp
  have he' : S*(toOrth g₀ g₁ A)*Sᵀ=G*A := by
   rw [hs,hg]; change S*(S*A*T)*S=(S*S)*A
   calc
    S*(S*A*T)*S=S*S*A*(T*S) := by noncomm_ring
    _=(S*S)*A := by rw [hTS]; simp
  constructor
  · intro hp; have hh := hp.mul_mul_conjTranspose_same T; change (T*(G*A)*Tᴴ).PosSemidef at hh; simpa only [Matrix.conjTranspose_eq_transpose_of_trivial,he] using hh
  · intro hp; simpa [Matrix.conjTranspose_eq_transpose_of_trivial,he'] using hp.mul_mul_conjTranspose_same S
 have hdens A : GIsDensity g₀ g₁ A ↔ IsDensity (toOrth g₀ g₁ A) := by simp [GIsDensity,IsDensity,hpos,htrace]
 have heff A : GIsEffect g₀ g₁ A ↔ IsEffect (toOrth g₀ g₁ A) := by simp [GIsEffect,IsEffect,hpos,hsub,hunit]
 have hbij (D D' : M2 → Prop) (hh : ∀ A, D A ↔ D' (toOrth g₀ g₁ A)) :
  ∃ e : {A // D A} ≃ {A // D' A}, ∀ A, (e A).val=toOrth g₀ g₁ A.val := by
  let e : {A // D A} ≃ {A // D' A} := {
   toFun := fun A ↦ ⟨toOrth g₀ g₁ A.val,(hh A.val).mp A.property⟩
   invFun := fun A ↦ ⟨fromOrth g₀ g₁ A.val,(hh _).mpr (by simpa [hir] using A.property)⟩
   left_inv := fun A ↦ Subtype.ext (hi A.val)
   right_inv := fun A ↦ Subtype.ext (hir A.val) }
  exact ⟨e,fun _ ↦ rfl⟩
 refine ⟨?_,Matrix.inv_eq_left_inv hTS,frame_metric g₀ g₁ h₀ h₁,hd,hsa,?_,hpos,hdens,heff,hi,hir,hbij _ _ hdens,hbij _ _ heff,hm,hadd,?_,hunit,htrace,?_,?_,?_⟩
 · exact ⟨⟨S,T,hST,hTS⟩,rfl⟩
 · intro A
   have had : (G*A).IsHermitian ↔ gAdjoint g₀ g₁ A=A := by
    rw [Matrix.IsHermitian,Matrix.conjTranspose_eq_transpose_of_trivial,Matrix.transpose_mul]
    have hgt : Gᵀ=G := by rw [hg,Matrix.transpose_mul,hs]
    rw [hgt]
    constructor
    · intro h; change G⁻¹*Aᵀ*G=A
      rw [Matrix.mul_assoc,h]; rw [hgi,hg]
      calc (T*T)*((S*S)*A)=T*(T*S)*S*A := by noncomm_ring
           _=A := by rw [hTS]; simp [hTS]
    · intro h
      have hx := congrArg (fun B ↦ G*B) h
      change G*(G⁻¹*Aᵀ*G)=G*A at hx
      rw [hgi,hg] at hx
      have he : (S*S)*((T*T)*Aᵀ*(S*S))=Aᵀ*(S*S) := by
       calc (S*S)*((T*T)*Aᵀ*(S*S))=S*(S*T)*T*Aᵀ*(S*S) := by noncomm_ring
            _=Aᵀ*(S*S) := by rw [hST]; simp [hST]
      rw [he] at hx
      simpa only [← hg] using hx
   change (G*A).PosSemidef ↔ _
   rw [Matrix.posSemidef_iff_dotProduct_mulVec,had]
   simp only [star_trivial]
   rfl
 · intro t A; simp [toOrth]
 · intro R E; rw [pairing,← hm,htrace]; rfl
 · intro A; exact hir _
 · intro E hE
   obtain ⟨A,hA,hu⟩ := principal_root_exists_unique _ ((hpos E).mp hE)
   refine ⟨fromOrth g₀ g₁ A,⟨(hpos _).mpr (by simpa [hir] using hA.1),?_⟩,?_⟩
   · apply_fun toOrth g₀ g₁ using (fun X Y h ↦ by simpa [hi] using congrArg (fromOrth g₀ g₁) h)
     rw [hm,hir,hA.2]
   · intro B hB
     have he := hu (toOrth g₀ g₁ B) ⟨(hpos B).mp hB.1,by rw [← hm,hB.2]⟩
     simpa [hi] using congrArg (fromOrth g₀ g₁) he
end BornCalculus
