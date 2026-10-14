# Corrective predictive evaluation v25

The freeze is the git commit of the specification and the code.

The full predictor is compared with the canonical diagonal in a basis fixed
before scoring. The historical SVD diagonal had an arbitrary rotation in a
numerically degenerate singular subspace. Its evidence for this comparison is
superseded and remains disclosed in the chronology. Other historical
comparators retain their scope. The JSON is the complete numerical contract.

## Acquisition

Use the inherited grids, scale 32 and 2000n dispatch steps. The competitor
family uses EXP-112's sixty-nine configurations; cross terms use these plus
EXP-102–107. There are twenty run-seed blocks per campaign:

- Cross-term: s = 1,000,000,000,000 + 1000k, k = 1,...,20.
- Competitor: s = 2,000,000,000,000 + 1000k, k = 1,...,20.

to the best of the author's knowledge, no seeds in these ranges were used before

The earlier consecutive proposals were replaced because they reused historical
discovery-path streams.

The registered path uses s for kernel initialization and dynamics, and
s+50000+j for discovery paths, j=0,...,23. Its distinct identity offsets are
O={0} union {50000,...,50023}. If two identities in a campaign coincide,
1000(k-k')=o'-o. Two path offsets differ by at most 23, so k=k' and o=o'.
A base/path equality is impossible: |1000(k-k')|<=19000 but |o'-o|>=50000.
The campaigns' identity intervals are disjoint; the maximum, 2,000,000,070,023,
is below 2^53 and 2^64. Documented historical registered acquisition bases are
at most 910000, giving direct/path identities at most 960023. Configurations
intentionally share a seed block; kernel initialization and dynamics share s.
This is uniqueness across block indices and distinct offsets, not independence
of every invocation or RNG initialization.

## Predictions and report

Decode emitted binary64 vectors as exact dyadic rationals. Gram–Schmidt keeps
the constant first, then emitted columns in their original order, without
pivoting. Keep a residual only when its squared norm strictly exceeds
max(n,m+1)^2 2^-104 lambda_max(H), where
H=11^T/n+sum_j u_j u_j^T; equality is discarded. Use positive square roots,
certified midpoint rounding and the registered refinement limits. Preserve
rank/span/full-law controls and unresolved dispositions. At rank two this is
the construction's constant/centred-mode basis.

Commit predictions before reading scored endpoints. Report 128 fixed
Gaussian-QR orientations per unit, using the registered 52-bit open-midpoint
uniforms, Box–Muller order, positive QR diagonal, eight-attempt limit and
separate stream domains. Save matrices and missing slots. Include the
historical-stack SVD reference only on fresh/synthetic inputs. This report is
descriptive, outside all Holm families and verdicts. A basis aligned with the
full amplitude makes the full predictor diagonal: no basis-independent
necessity claim follows.

## Inference and outcomes

Keep the equal-weight hierarchies: for cross terms, systematic configurations
have one half and the six named families together have one half. Use 20,000
whole-seed BCa replicates, the registered jackknife, exact-integer 2^20 sign
tails, Holm and fixed sensitivities. Competitor Brier sensitivity tails also
use exact-integer counting. Cross-term bootstrap membership is shared across
maps/sources/metrics; competitor streams are independent by statistic. All
seventeen domain rows, family sizes 24/48 and 2/4, admission/nondegeneracy/tie
rules, endpoint/control dependencies and sixteen joint outcomes are in JSON.
The cross-term margin remains 1/240 on both maps.

Only a cross-term joint pass permits: “on this registered cohort, the full
predictor has lower aggregate empirical-TV loss than the diagonal rule in the
pre-specified constant-first, emitted-order basis, exceeding the registered
margin on both maps.” Report fail and inconclusive outcomes without redesign.

## Run

Use CPython 3.12. Automatic environment routing installs NumPy 2.5.2,
SciPy 1.18.1 and the pinned symbolic stack. NumPy uses OpenBLAS 0.3.34.0.0;
SciPy's pinned wheel supplies its separate backend. Both run one thread with
Haswell dispatch. The computing process checks versions and effective threads.
No seed scan, attestation, second-CPU, native-hash or freeze-bundle gate applies.

```sh
python -m born_ladder reproduce v25 --output ROOT --workers N
```

This builds the runner if absent, runs both grids, commits and constructs units,
then infers and writes verdicts.csv, verdicts.md and verdicts.json. Repeat the
command to resume. For an acquisition-free check, add `--synthetic`; only this
mode accepts a reduced `--replicates` count. No registered seed was executed
while preparing this implementation.
