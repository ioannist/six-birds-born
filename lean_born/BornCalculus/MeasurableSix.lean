import BornCalculus.FiniteSix
namespace BornCalculus
open MeasureTheory
open scoped ENNReal BigOperators
set_option maxHeartbeats 0

structure MeasurableSixModel (Ω : Type*) [MeasurableSpace Ω] where
 base : Measure Ω
 plus : Fin 3 → Measure Ω
 minus : Fin 3 → Measure Ω
 response : Fin 3 → Ω → ℝ≥0∞
 base_probability : IsProbabilityMeasure base
 plus_probability : ∀ i, IsProbabilityMeasure (plus i)
 minus_probability : ∀ i, IsProbabilityMeasure (minus i)
 response_measurable : ∀ i, Measurable (response i)
 response_le_one : ∀ i x, response i x ≤ 1
 pair : ∀ i, plus i + minus i = (2 : ℝ≥0∞) • base
 trine : (∑ i, plus i) = (3 : ℝ≥0∞) • base
 perfect_plus : ∀ i, (∫⁻ x, response i x ∂(plus i)) = 1
 perfect_minus : ∀ i, (∫⁻ x, response i x ∂(minus i)) = 0

theorem perfect_discrimination_mutuallySingular {Ω : Type*} [MeasurableSpace Ω]
 (μ ν : Measure Ω) [IsProbabilityMeasure μ] [IsProbabilityMeasure ν]
 (ξ : Ω → ℝ≥0∞) (hξ : Measurable ξ) (hbound : ∀ x, ξ x ≤ 1)
 (hyes : (∫⁻ x, ξ x ∂μ)=1) (hno : (∫⁻ x, ξ x ∂ν)=0) :
 μ.MutuallySingular ν := by
 have hμ : ξ =ᵐ[μ] fun _ => 1 := ae_eq_of_ae_le_of_lintegral_le
   (Filter.Eventually.of_forall hbound) (by rw [hyes]; simp)
   measurable_const.aemeasurable (by simp [hyes])
 have hν : ξ =ᵐ[ν] 0 := (lintegral_eq_zero_iff hξ).mp hno
 refine ⟨{x | ξ x ≠ 1},(hξ (measurableSet_singleton 1)).compl,ae_iff.mp hμ,?_⟩
 have hh : ∀ᵐ x ∂ν, ξ x ≠ 1 := hν.mono (by intro x hx; simp [hx])
 simpa only [Set.compl_setOf,not_not] using (ae_iff.mp hh)

theorem measurable_six_domination {Ω : Type*} [MeasurableSpace Ω]
 (M : MeasurableSixModel Ω) (i : Fin 3) :
 M.plus i ≤ (2 : ℝ≥0∞) • M.base ∧ M.minus i ≤ (2 : ℝ≥0∞) • M.base := by
 rw [←M.pair i]
 exact ⟨Measure.le_add_right le_rfl,Measure.le_add_left le_rfl⟩

theorem measurable_six_ac {Ω : Type*} [MeasurableSpace Ω]
 (M : MeasurableSixModel Ω) (i : Fin 3) : M.plus i ≪ M.base ∧ M.minus i ≪ M.base := by
 have h := measurable_six_domination M i
 have hs : (2 : ℝ≥0∞) • M.base ≪ M.base := Measure.AbsolutelyContinuous.smul_left Measure.AbsolutelyContinuous.rfl _
 exact ⟨h.1.absolutelyContinuous.trans hs,h.2.absolutelyContinuous.trans hs⟩

theorem measurable_six_rn_representation {Ω : Type*} [MeasurableSpace Ω]
 (M : MeasurableSixModel Ω) (i : Fin 3) :
 M.base.withDensity ((M.plus i).rnDeriv M.base)=M.plus i ∧
 M.base.withDensity ((M.minus i).rnDeriv M.base)=M.minus i := by
 letI := M.base_probability
 letI := M.plus_probability i
 letI := M.minus_probability i
 exact ⟨Measure.withDensity_rnDeriv_eq _ _ (measurable_six_ac M i).1,
   Measure.withDensity_rnDeriv_eq _ _ (measurable_six_ac M i).2⟩

theorem measurable_six_rn_pair {Ω : Type*} [MeasurableSpace Ω]
 (M : MeasurableSixModel Ω) (i : Fin 3) :
 ∀ᵐ x ∂M.base, (M.plus i).rnDeriv M.base x+(M.minus i).rnDeriv M.base x=2 := by
 letI := M.base_probability
 letI := M.plus_probability i
 letI := M.minus_probability i
 have h := Measure.rnDeriv_add (M.plus i) (M.minus i) M.base
 have hs := Measure.rnDeriv_smul_left_of_ne_top M.base M.base (r := 2) (by norm_num)
 rw [M.pair i] at h
 filter_upwards [h,hs,Measure.rnDeriv_self M.base] with x hx hsx hself
 simpa [hself] using hx.symm.trans hsx

theorem mutuallySingular_rn_disjoint {Ω : Type*} [MeasurableSpace Ω]
 (β μ ν : Measure Ω) [IsProbabilityMeasure β] [IsProbabilityMeasure μ] [IsProbabilityMeasure ν]
 (hμ : μ ≪ β) (hν : ν ≪ β) (hs : μ.MutuallySingular ν) :
 ∀ᵐ x ∂β, μ.rnDeriv β x=0 ∨ ν.rnDeriv β x=0 := by
 have hrepμ := Measure.withDensity_rnDeriv_eq μ β hμ
 have hrepν := Measure.withDensity_rnDeriv_eq ν β hν
 rcases hs with ⟨s,hs,hnullμ,hnullν⟩
 have hμs : ∀ᵐ x ∂μ, x ∉ s := by
   simpa only [ae_iff,not_not] using hnullμ
 have hνs : ∀ᵐ x ∂ν, x ∈ s := by
   simpa only [ae_iff,Set.compl_setOf] using hnullν
 rw [←hrepμ,ae_withDensity_iff (Measure.measurable_rnDeriv μ β)] at hμs
 rw [←hrepν,ae_withDensity_iff (Measure.measurable_rnDeriv ν β)] at hνs

 filter_upwards [hμs,hνs] with x hx hy
 by_cases hf : μ.rnDeriv β x=0
 · exact Or.inl hf
 · right
   by_contra hg
   exact hx hf (hy hg)

theorem measurable_six_rn_disjoint {Ω : Type*} [MeasurableSpace Ω]
 (M : MeasurableSixModel Ω) (i : Fin 3) :
 ∀ᵐ x ∂M.base, (M.plus i).rnDeriv M.base x=0 ∨ (M.minus i).rnDeriv M.base x=0 := by
 letI := M.base_probability
 letI := M.plus_probability i
 letI := M.minus_probability i
 exact mutuallySingular_rn_disjoint M.base (M.plus i) (M.minus i)
   (measurable_six_ac M i).1 (measurable_six_ac M i).2
   (perfect_discrimination_mutuallySingular _ _ (M.response i) (M.response_measurable i)
     (M.response_le_one i) (M.perfect_plus i) (M.perfect_minus i))

theorem measurable_six_rn_binary {Ω : Type*} [MeasurableSpace Ω]
 (M : MeasurableSixModel Ω) (i : Fin 3) :
 ∀ᵐ x ∂M.base, (M.plus i).rnDeriv M.base x=0 ∨ (M.plus i).rnDeriv M.base x=2 := by
 filter_upwards [measurable_six_rn_pair M i,measurable_six_rn_disjoint M i] with x hx hd
 rcases hd with h | h
 · exact Or.inl h
 · right; simpa [h] using hx

theorem measurable_six_rn_trine {Ω : Type*} [MeasurableSpace Ω]
 (M : MeasurableSixModel Ω) :
 ∀ᵐ x ∂M.base, ∑ i : Fin 3, (M.plus i).rnDeriv M.base x=3 := by
 letI := M.base_probability
 letI (i : Fin 3) : IsProbabilityMeasure (M.plus i) := M.plus_probability i
 have h1 := Measure.rnDeriv_add (M.plus 0) (M.plus 1+M.plus 2) M.base
 have h2 := Measure.rnDeriv_add (M.plus 1) (M.plus 2) M.base
 have hs := Measure.rnDeriv_smul_left_of_ne_top M.base M.base (r := 3) (by norm_num)
 have ht : M.plus 0+(M.plus 1+M.plus 2)=(3 : ℝ≥0∞) • M.base := by
   simpa only [Fin.sum_univ_three,add_assoc] using M.trine
 rw [ht] at h1
 filter_upwards [h1,h2,hs,Measure.rnDeriv_self M.base] with x hx hy hz hw
 simpa [Fin.sum_univ_three,add_assoc,hy,hw] using hx.symm.trans hz

theorem measurable_six_no_go {Ω : Type*} [MeasurableSpace Ω]
 (M : MeasurableSixModel Ω) : False := by
 letI := M.base_probability
 have hf : ∀ᵐ x ∂M.base, False := by
   filter_upwards [measurable_six_rn_binary M 0,measurable_six_rn_binary M 1,
     measurable_six_rn_binary M 2,measurable_six_rn_trine M] with x ha hb hc hs
   simp only [Fin.sum_univ_three] at hs
   rcases ha with ha | ha <;> rcases hb with hb | hb <;> rcases hc with hc | hc <;>
     norm_num [ha,hb,hc] at hs
 have hz : M.base Set.univ=0 := by simpa [ae_iff] using hf
 simpa using hz


/-- Randomization and equal-density preparation identities are explicit,
 not inferred from equality of the operational table. -/
structure MeasurableTableRepresentation (Ω : Type*) [MeasurableSpace Ω] where
 base : Measure Ω
 preparation : Fin 6 → Measure Ω
 response : Fin 3 → Ω → ℝ≥0∞
 base_probability : IsProbabilityMeasure base
 preparation_probability : ∀ i, IsProbabilityMeasure (preparation i)
 response_measurable : ∀ i, Measurable (response i)
 response_le_one : ∀ i x, response i x ≤ 1
 pairs_preserved : ∀ i : Fin 3,
   (1/2 : ℝ≥0∞) • (preparation (Fin.castLE (by omega) i)+preparation ⟨i.val+3,by omega⟩)=base
 trine_preserved : (1/3 : ℝ≥0∞) • (preparation 0+preparation 1+preparation 2)=base
 table : ∀ (i : Fin 6) (j : Fin 3),
   (∫⁻ x, response j x ∂(preparation i))=ENNReal.ofReal (pairing (sixState i) (sharp j))

noncomputable def measurable_table_bridge {Ω : Type*} [MeasurableSpace Ω]
 (M : MeasurableTableRepresentation Ω) : MeasurableSixModel Ω where
 base := M.base
 plus i := M.preparation (Fin.castLE (by omega) i)
 minus i := M.preparation ⟨i.val+3,by omega⟩
 response := M.response
 base_probability := M.base_probability
 plus_probability i := M.preparation_probability _
 minus_probability i := M.preparation_probability _
 response_measurable := M.response_measurable
 response_le_one := M.response_le_one
 pair i := by
   have h := congrArg (fun μ : Measure Ω => (2 : ℝ≥0∞) • μ) (M.pairs_preserved i)
   have hc : (2 : ℝ≥0∞)*2⁻¹=1 := ENNReal.mul_inv_cancel (by norm_num) (by norm_num)
   simpa [smul_smul,hc] using h
 trine := by
   have h := congrArg (fun μ : Measure Ω => (3 : ℝ≥0∞) • μ) M.trine_preserved
   have hc : (3 : ℝ≥0∞)*3⁻¹=1 := ENNReal.mul_inv_cancel (by norm_num) (by norm_num)
   simpa [Fin.sum_univ_three,Fin.castLE,Fin.cast,smul_smul,hc] using h
 perfect_plus i := by
   rw [M.table,six_state_probability_table]
   fin_cases i <;> norm_num [sixTable,Fin.castLE,Fin.cast]
 perfect_minus i := by
   rw [M.table,six_state_probability_table]
   fin_cases i <;> norm_num [sixTable,Fin.castLE,Fin.cast]

theorem measurable_table_representation_impossible {Ω : Type*} [MeasurableSpace Ω]
 (M : MeasurableTableRepresentation Ω) : False :=
 measurable_six_no_go (measurable_table_bridge M)
end BornCalculus
