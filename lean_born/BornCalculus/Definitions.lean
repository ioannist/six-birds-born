import Mathlib

namespace BornCalculus
open scoped MatrixOrder
abbrev M2 := Matrix (Fin 2) (Fin 2) ℝ

def IsDensity (R : M2) : Prop := R.PosSemidef ∧ Matrix.trace R = 1
def IsEffect (E : M2) : Prop := E.PosSemidef ∧ (1 - E).PosSemidef
abbrev Density := {R : M2 // IsDensity R}
abbrev Effect := {E : M2 // IsEffect E}
def pairing (R E : M2) : ℝ := Matrix.trace (R * E)
def zeroEffect : Effect := ⟨0, Matrix.PosSemidef.zero, by simpa using (Matrix.PosSemidef.one : (1 : M2).PosSemidef)⟩
def unitEffect : Effect := ⟨1, Matrix.PosSemidef.one, by simpa using (Matrix.PosSemidef.zero : (0 : M2).PosSemidef)⟩

def scaleEffect (t : ℝ) (ht₀ : 0 ≤ t) (ht₁ : t ≤ 1) (E : Effect) : Effect :=
 ⟨t • E.val, E.property.1.smul ht₀, by
   have h := (Matrix.PosSemidef.one : (1 : M2).PosSemidef).smul (sub_nonneg.mpr ht₁)
   have h' := h.add (E.property.2.smul ht₀)
   convert h' using 1 <;> module⟩

structure Valuation where
 value : Effect → ℝ
 nonnegative : ∀ E, 0 ≤ value E
 normalized : value unitEffect = 1
 additive : ∀ E F H : Effect, (H : M2) = (E : M2) + (F : M2) → value H = value E + value F

structure TraceValuationLaws (R : Density) : Prop where
 nonnegative : ∀ E : Effect, 0 ≤ pairing R.val E.val
 normalized : pairing R.val unitEffect.val = 1
 additive : ∀ E F H : Effect, H.val = E.val + F.val → pairing R.val H.val = pairing R.val E.val + pairing R.val F.val

end BornCalculus
