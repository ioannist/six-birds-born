# Registered specifications

| Stage / version | Readable specification | Where to find the scientific settings |
| --- | --- | --- |
| Competitor-family acquisition and evaluation, v8 | [predictive_v8.json](predictive_v8.json) | `grid` (configurations), `competitor_family_campaign` (experiments, seeds, scales), `observation_maps`, `thresholds`, `estimands`, `inference` (bootstrap and randomization budgets), `rng` |
| Cross-term acquisition, v21 | [predictive_v21.json](predictive_v21.json) | `grid`, `cross_term_campaign`, `observation_maps`, `thresholds`, `estimands`, `inference`, `rng` |
| Prior cross-term evaluation contract, v23 | [predictive_v23.json](predictive_v23.json) | Same named fields, plus the version's section index for the exact controls and certificates |
| Effective cross-term evaluation contract, v24 | [predictive_v24.json](predictive_v24.json) | Same named fields; the amended numerical certificate is in its section index |
| Record-only test, v6 / v6.1 | [test_b.json](test_b.json), [test_b_v6.md](test_b_v6.md), [test_b_v6_1.md](test_b_v6_1.md) | Kernel seed and scale, recipes, calibration draws, lags, eligibility threshold, fitting starts/iterations, bootstrap budget, and effective controls |

[amendments.json](amendments.json) says which version governs each stage and
which amendments apply. The Test B protocols adapt the historical storage path
only: supply an `OUTPUT_ROOT` outside Git. No scientific constant changes.

Each `predictive_v*_sections.json` maps the original scientific JSON pointers
to descriptive, pretty-printed files in `shared_sections/`. The loader resolves
these references transparently and checks their scientific-value hashes. Open
[shared_sections/index.json](shared_sections/index.json) to see **every section,
all versions sharing it, and each pointer**. Complete scientific sections are shipped as plain JSON, without size-based
splitting. Only sections with byte-identical readable JSON are shared; the
catalog includes byte hashes. Expanded symbolic-expression tables remain
inline in their complete derivation sections. No table is compressed or
replaced by a runtime enumeration. The top-level version files keep the grids,
seeds, thresholds and inference budgets inline.

[predictive.json](predictive.json) selects the version files and documents each
original registered specification digest as a fixed `scientific_rng_identity`.
These original digests remain RNG domain constants; they are not hashes or
attestations of the adapted public files. Tests check the published scientific
values and retained reference draws. G2c keeps the v21 source RNG identity while
v24 governs the effective evaluation contract.

[source_recovery.json](source_recovery.json) records original module names and
hashes, public destinations and adaptation classifications. Process receipts,
review bindings and private recovery paths are not runtime inputs. This directory
contains specifications, not the experimental archive. Stage orchestration is
being completed in the downstream reproduction packets.

[runs.json](runs.json) declares the public acquisition grids, worked cases, smoke
and throughput subsets. It references the version files above rather than
copying their complete schedules. Run `python -m born_ladder reproduce runs
--grid smoke --output <external-or-Git-ignored-root> --workers 4` after `make rust`.


`units.json` defines P2b's registered competitor/cross-term grids and the declared
worked-case/named-family diagnostic subset by references to `runs.json` and the
amendment map. It also states canonical record ordering and LF hash conventions.
The version files include the original structural-output schema and the small
transport metadata required by the historical unit functions. No receipt or
review document is required to load or run them.


`census.json` documents structural availability, full-key ordering, both exact
witness rules and the distinction between original implementation checks and
completion. `environments/predictive.{json,lock}` and
`environments/verification.{json,lock}` pin the two stage stacks, library bytes
and thread/dispatch policy. The CLI provisions and routes these automatically;
see `docs/reproduction.md`. The GMP-backed symbolic diagnostic is included to
replay the original overflow statuses, independently of exact completion.
