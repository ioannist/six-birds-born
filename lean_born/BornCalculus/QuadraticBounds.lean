import BornCalculus.RootChart
namespace BornCalculus
set_option maxHeartbeats 0
noncomputable def linearLower (a lo hi : ℝ) : ℝ := if 0 ≤ a then a*lo else a*hi
theorem linearLower_le (a lo hi x : ℝ) (hl : lo ≤ x) (hu : x ≤ hi) :
 linearLower a lo hi ≤ a*x := by
 by_cases ha : 0 ≤ a
 · simpa only [linearLower,if_pos ha] using mul_le_mul_of_nonneg_left hl ha
 · simpa only [linearLower,if_neg ha] using mul_le_mul_of_nonpos_left hu (le_of_not_ge ha)
theorem quadratic_ratio_bounds (s a b c x L U sqL sqU P Q : ℝ)
 (hs : 0 < s) (hxL : L ≤ x) (hxU : x ≤ U) (hsqL : sqL ≤ x^2) (hsqU : x^2 ≤ sqU)
 (hl : 0 ≤ a-32*P+linearLower b L U+linearLower (c-s*P) sqL sqU)
 (hu : 0 ≤ 32*Q-a+linearLower (-b) L U+linearLower (s*Q-c) sqL sqU) :
 P ≤ (a+b*x+c*x^2)/(32+s*x^2) ∧ (a+b*x+c*x^2)/(32+s*x^2) ≤ Q := by
 have hd : 0 < (32:ℝ)+s*x^2 := add_pos_of_pos_of_nonneg (by norm_num) (mul_nonneg hs.le (sq_nonneg x))
 have h1 := linearLower_le b L U x hxL hxU
 have h2 := linearLower_le (c-s*P) sqL sqU (x^2) hsqL hsqU
 have h3 := linearLower_le (-b) L U x hxL hxU
 have h4 := linearLower_le (s*Q-c) sqL sqU (x^2) hsqL hsqU
 constructor
 · apply (le_div_iff₀ hd).mpr
   nlinarith
 · apply (div_le_iff₀ hd).mpr
   nlinarith
end BornCalculus
