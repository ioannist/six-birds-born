import Mathlib.Data.Rat.Lemmas
import Mathlib.Data.Fintype.BigOperators
import Mathlib.Data.Fin.VecNotation
import Mathlib.Algebra.Order.Group.Abs
import Lean.Elab.Tactic.Omega

namespace BornCalculus.Census
open scoped BigOperators
set_option maxHeartbeats 0
set_option maxRecDepth 100000

/-- Exact data for one ordered full-cohort context. All derived fields are
checked below; they do not add scientific assumptions. -/
structure RawCase where
 D : ℤ
 S : ℤ
 z : Fin 32 → ℤ
 labels : Fin 3 → Fin 32 → Fin 4
 I : Fin 32
 J : Fin 32
 m0 : ℤ
 m1 : ℤ
 m2 : ℤ
 robustI : Fin 32
 robustJ : Fin 32
 atomN : Fin 3 → Fin 4 → ℤ
 atomZ : Fin 3 → Fin 4 → ℤ
 atomZZ : Fin 3 → Fin 4 → ℤ
 readN : Fin 32 → ℤ
 readD : Fin 32 → ℤ
 gapN : ℤ
 gapD : ℤ
 low : Fin 64 → Fin 32
 high : Fin 64 → Fin 32

def RawCase.numerator (r : RawCase) (i : Fin 32) : ℤ :=
 r.m0*r.S^2+64*r.S*r.z i*r.m1+1024*(r.z i)^2*r.m2

def RawCase.denominator (r : RawCase) (i : Fin 32) : ℤ :=
 32*r.S*(r.S+32*(r.z i)^2)

def RawCase.det (r : RawCase) (f : Fin 3) (a : Fin 4) : ℤ :=
 r.atomN f a*r.atomZZ f a-(r.atomZ f a)^2

def RawCase.read (r : RawCase) (i : Fin 32) : ℚ := (r.readN i:ℚ)/(r.readD i:ℚ)

def RawCase.crossGap (r : RawCase) (i j : Fin 32) : ℤ :=
 abs (r.readN i*r.readD j-r.readN j*r.readD i)

def RawCase.key (r : RawCase) (i : Fin 32) : Fin 64 :=
 ⟨16*(r.labels 0 i).val+4*(r.labels 1 i).val+(r.labels 2 i).val, by
   have h0 := (r.labels 0 i).isLt
   have h1 := (r.labels 1 i).isLt
   have h2 := (r.labels 2 i).isLt
   omega⟩

def LexBefore (i j k l : Fin 32) : Prop := i < k ∨ (i = k ∧ j < l)
instance (i j k l : Fin 32) : Decidable (LexBefore i j k l) :=
 inferInstanceAs (Decidable (i < k ∨ (i = k ∧ j < l)))

def FrameCheck (r : RawCase) : Prop :=
 0 < r.D ∧ 0 < r.S ∧ (∑ i, r.z i) = 0 ∧ (∑ i, (r.z i)^2) = r.S
instance (r : RawCase) : Decidable (FrameCheck r) := by unfold FrameCheck; infer_instance

def MomentCheck (r : RawCase) : Prop :=
 (∑ k, if r.labels 0 k = 0 then (1:ℤ) else 0) = r.m0 ∧
 (∑ k, if r.labels 0 k = 0 then r.z k else 0) = r.m1 ∧
 (∑ k, if r.labels 0 k = 0 then (r.z k)^2 else 0) = r.m2
instance (r : RawCase) : Decidable (MomentCheck r) := by unfold MomentCheck; infer_instance

def PairCheck (r : RawCase) : Prop :=
 r.I < r.J ∧ r.z r.I ≠ r.z r.J ∧
 (∀ f, r.labels f r.I = r.labels f r.J) ∧
 r.numerator r.I*r.denominator r.J ≠ r.numerator r.J*r.denominator r.I
instance (r : RawCase) : Decidable (PairCheck r) := by unfold PairCheck; infer_instance

def EarlierCheck (r : RawCase) : Prop :=
 ∀ i j, i < j → LexBefore i j r.I r.J →
 (∃ f, r.labels f i ≠ r.labels f j) ∨ r.z i = r.z j
instance (r : RawCase) : Decidable (EarlierCheck r) := by unfold EarlierCheck; infer_instance

def AtomCheck (r : RawCase) : Prop := ∀ f a,
 r.atomN f a = (∑ k, if r.labels f k = a then (1:ℤ) else 0) ∧
 r.atomZ f a = (∑ k, if r.labels f k = a then r.z k else 0) ∧
 r.atomZZ f a = (∑ k, if r.labels f k = a then (r.z k)^2 else 0) ∧
 0 ≤ r.det f a ∧
 (0 < r.atomN f a ∧ r.det f a = 0 →
   0 < r.atomN f a*r.S+32*r.atomZZ f a ∧
   r.atomN f a*r.S+32*r.atomZZ f a < 32*r.S)
instance (r : RawCase) : Decidable (AtomCheck r) := by unfold AtomCheck; infer_instance

def ReadCheck (r : RawCase) : Prop := ∀ i,
 0 < r.readD i ∧ r.readN i*r.denominator i = r.numerator i*r.readD i
instance (r : RawCase) : Decidable (ReadCheck r) := by unfold ReadCheck; infer_instance

def RobustCheck (r : RawCase) : Prop :=
 r.robustI < r.robustJ ∧ (∀ f, r.labels f r.robustI = r.labels f r.robustJ) ∧
 0 < r.gapD ∧
 r.crossGap r.robustI r.robustJ*r.gapD = r.gapN*r.readD r.robustI*r.readD r.robustJ ∧
 r.gapD ≤ 25*r.gapN ∧ 438357*r.gapD ≤ 10000000*r.gapN
instance (r : RawCase) : Decidable (RobustCheck r) := by unfold RobustCheck; infer_instance

def RangeCheck (r : RawCase) : Prop := ∀ i,
 r.readN (r.low (r.key i))*r.readD i ≤ r.readN i*r.readD (r.low (r.key i)) ∧
 r.readN i*r.readD (r.high (r.key i)) ≤ r.readN (r.high (r.key i))*r.readD i ∧
 r.crossGap (r.low (r.key i)) (r.high (r.key i))*r.gapD ≤
   r.gapN*r.readD (r.low (r.key i))*r.readD (r.high (r.key i))
instance (r : RawCase) : Decidable (RangeCheck r) := by unfold RangeCheck; infer_instance

def TieCheck (r : RawCase) : Prop := ∀ i j,
 i < j → LexBefore i j r.robustI r.robustJ → (∀ f, r.labels f i = r.labels f j) →
 r.crossGap i j*r.gapD < r.gapN*r.readD i*r.readD j
instance (r : RawCase) : Decidable (TieCheck r) := by unfold TieCheck; infer_instance

structure CertifiedCase where
 raw : RawCase
 frame : FrameCheck raw
 moments : MomentCheck raw
 pair : PairCheck raw
 earlier : EarlierCheck raw
 atoms : AtomCheck raw
 reads : ReadCheck raw
 robust : RobustCheck raw
 ranges : RangeCheck raw
 earlierMax : TieCheck raw

def RawCase.activeCount (r : RawCase) : ℕ :=
 ∑ f, ∑ a, if 0 < r.atomN f a then 1 else 0

def RawCase.positiveCount (r : RawCase) : ℕ :=
 ∑ f, ∑ a, if 0 < r.atomN f a ∧ 0 < r.det f a then 1 else 0

def RawCase.singularCount (r : RawCase) : ℕ :=
 ∑ f, ∑ a, if 0 < r.atomN f a ∧ r.det f a = 0 then 1 else 0

def RawCase.singularContext (r : RawCase) : ℕ :=
 if ∃ f a, 0 < r.atomN f a ∧ r.det f a = 0 then 1 else 0

end BornCalculus.Census
