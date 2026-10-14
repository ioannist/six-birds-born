# Reproduction

Run from the public repository root with the non-editable installation and
PYTHONPATH unset. The [README quick start](../README.md#quick-start) gives the
complete clone-to-smoke-to-no-data-verification order and measured costs.
`DATA_OUT` denotes the output root defined there; the replay example below
requires a completed full census and original worked-case output, not a fresh
clone or reduced smoke cohort.

The exact retained-matrix map replay is available separately from construction:

```sh
.venv/bin/python -m born_ladder reproduce replay-maps \
  --census "$DATA_OUT/full/census" \
  --original-context "$DATA_OUT/full/worked/original/CONTEXT.json" \
  --output "$DATA_OUT/map-replay" \
  --build-directory "$DATA_OUT/map-replay-build"
```

This reads the completed census and its sealed exponent-one K adapters, then
recomputes stationary estimates, emitted vectors and raw/package/joint maps
using the shipped Rust routines. It compiles offline against `vendor/pica`
(Rust and cached Cargo dependencies are required), with float round-trip JSON
parsing. No sampler runs. The public sidecar's private `context_maps` body is
copied unchanged with a read-only wrapper, extending the historical 120-case
`arch_probe`/`join_probe` method. Packaging consumes the recomputed raw map.
Every labelled state is compared exactly; a mismatch exits nonzero and records
its case, map and differing states in the attempt's `checks.json` and
`summary.json`. Stationary and emitted-vector comparisons use binary64 bits.
The original fixture is checked by identity (EXP-112/loo_A25/seed 910000).
Inputs remain read-only; attempts and the optional reusable Rust build go into
the specified output directories. `--source-root` selects a public checkout
when invoking from another directory; the default is the invocation checkout
(root working directory), independent of the Python installation path.

## Paper-number check and full replication

The public number map, [specifications/paper_numbers.json](../specifications/paper_numbers.json),
contains explicit selectors, display formats and rounding directions. It has no
historical paths, ledger values or runtime dependency on internal ledger/alias
files. The check uses the same value extractors and decimal renderer as the
optional archive comparison. Census and attachment summaries are recomputed from
this run's committed records; canonical diagonal losses use the public constructor
in its pinned corrective-evaluation environment and exact dyadic type-seven
quantiles. Population endpoints come from the committed completed evaluations;
this command does not repeat their bootstrap inference. The full pipeline's
regenerated verifications bind the Lean inputs and recompute inference for the
earlier evaluations. The separate corrective evaluation computes its own
inference; this number check validates its committed output and registered cohort
without recomputing that inference.

Run from the checkout root, with the documented non-editable installation:

```sh
source env.sh
# Measured full-run configuration: 64 cores, 128 threads.
make replicate DATA_OUT="${DATA_OUT:?Source env.sh or set DATA_OUT}" WORKERS=48 LEAN_JOBS=4
```

The target runs full production, the separate registered corrective evaluation
(named `v25`), then the paper-number check. Producer commands validate and reuse
completed stages on rerun; the paper display map is excluded from scientific
input-plan equality, just like interface examples. The final command runs again,
recomputes values from the completed outputs and writes new reports comparing
them with the paper's displayed values. Make exports `LEAN_JOBS` to the pipeline's
Make subprocess, so the requested job count is effective.
No retained archive, ledger or aliases are production or paper-number inputs.

For smaller machines, start with `WORKERS=1 LEAN_JOBS=1`; increase these counts
when cores and RAM permit. This preserves the full experimental design but takes
longer. Fewer workers do not remove the memory needs of serial inference and a
single Lean process. With `LEAN_JOBS=1` the measured build took **about 3 h
8 min** with peak **about 18 GB**; the number check peaked at **about 23.2 GB (21.6 GiB)**,
and population-inference verification with 48 workers reached
**23.1 GiB (about 24.8 GB)** of process-tree proportional set size, sampled every **30 s**,
with no swap used. Allow headroom. The reported timings used the stated parallelism.

The full run regenerates 14 of the 17 evidence-dependent claims plus P01 and P02;
B01, B11 and B12 remain historical-only (retained role records, historical
executable/source correspondence and selected-case return attachment). In
`verification_report.json`, `/status` is `COMPLETE`,
`/checks/<group>/claim_receipts/<ID>/status` is `VERIFIED` for all 16 claims,
and `/formal_endpoints/status` is `BUILT_AND_AUDITED`. Smoke uses
`REDUCED_NONCONFIRMATORY` at those claim/group status paths and
`NOT_APPLICABLE` at the formal status path;
`/checks/test_b/claim_receipts/TB01/checks/category` is `OUT_OF_ELIGIBLE_SCOPE`.

The pipeline caps census workers at 8 and evaluation/verification workers at 64;
acquisition, units and locked-test work use the requested worker count. Worked
cases and attachments run without a worker pool; bootstrap arithmetic is not
made parallel by that flag. Corrective-evaluation acquisition/construction use
workers, but its inference is serial. Lean jobs are controlled separately.
Worker count may change on resume; evaluation admission-pool size is recorded
as execution metadata, excluded from numerical plan equality. Run only one
process per output root. If reuse is refused, inspect the logs and restore
matching inputs/environment or choose a fresh output root. Do not bypass
commitments. Preserved attempt directories may be referenced by completion
markers and journals: retain them while using or resuming the root; there is
no automatic safe-pruning facility. For unattended execution use tmux or the
README's nohup command; combined progress goes to `replicate.log`, with full
stage logs in `full/logs/`. After a nonzero exit, fix the cause and rerun the
same command. The 117 registered-bound shortfalls and the locked-test negative
verdict are expected scientific outcomes and do not make commands fail.

After those outputs exist, the last step can be run independently:

```sh
.venv/bin/python -m born_ladder reproduce paper-numbers \
  --run "${DATA_OUT:?Source env.sh or set DATA_OUT}/full" --v25-output "$DATA_OUT/v25" \
  --paper paper/main.tex --output "$DATA_OUT/paper-numbers"
```

Success prints **`358/358 paper numbers reproduced`**. Inspect
`$DATA_OUT/paper-numbers/report.md` for the comparison table. Both reports give
typeset and regenerated displays, full-precision values and match status;
`report.json` additionally records sources and aggregation. The Markdown report
lists results first, settings second and non-numerical macros last. The empty `.runs.lock` is a
persistent advisory lock preventing simultaneous writers; retain it, since
unlinking a lock file can break that protection. The 45 fixed program
settings and arithmetic constants are checked against their literal public
sources. The 40 symbol/layout/figure/metadata macros are separately classified; their numerical
result-macro references are checked, but figure coordinates and literal labels
are not. A mismatch or missing extractor/value exits nonzero. Omitting
`--v25-output` marks corrective-evaluation values not regenerated and points to
`reproduce v25`; it cannot produce a successful full check. `--number-map` selects
an alternative map for diagnostics; missing, duplicate or unclassified entries
fail coverage rather than disappearing.
The first real-output measurement took **1,970.75 s (32 min 50.75 s)**,
with 358/358 regenerated results and 45/45 settings matching; it read the
completed full and corrective trees without rerunning the experiments. The
final non-editable installed-package check, with PYTHONPATH unset, took
**1,484.82 s (24 min 44.82 s)** and matched all 358 results and 45 settings;
40 symbol/layout/figure/metadata macros were separately accounted for. Its
full-precision result values agreed exactly with the first run. An independent
installed-mode rerun at revision 4942042dd, with PYTHONPATH unset, took **25 min
39 s**, peak RSS **22,685,396 KiB (about 23.2 GB)**, with 358/358 results and 45/45
settings matching. The archive comparison was running concurrently on that host;
these are post-run check measurements, not experiment runtimes. Allow memory
headroom above the check's measured peak.

Before long extraction the number check provisions or validates the
corrective-evaluation environment (`predictive_v25`) in an isolated runtime check.
On first use provisioning accesses the network, **about 0.3 GB**. Offline,
include the platform-compatible wheels required by
[its lock](../specifications/environments/predictive_v25.lock) in
`BORN_LADDER_WHEELHOUSE`, as well as the locks for other stages. Previously
published environments are reused rather than reinstalled.

Maintainers can regenerate the committed map with
`tools/generate_paper_number_map.py --ledger LEDGER --aliases ALIASES --paper paper/main.tex --output specifications/paper_numbers.json`.
Those explicit migration inputs are not needed by readers or by the command.
The generator stores bindings, not expected result values; all 45 setting
bindings are checked against their public sources during migration.

## Environment and builds

Building the paper requires TeX Live with the `quantumarticle` class, the
standard LaTeX packages used by the manuscript, BibTeX and `latexmk`. Run
`make paper` from the repository root; the PDF and auxiliary files are written
to the ignored `paper/build/` directory.

The Python package supports Python ≥3.11. Full replication requires
**CPython 3.12.3 exactly**; its historical production stages refuse other patch
releases. Use Linux x86_64 with x86-64-v3 (AVX2/FMA) support. The base
`requirements.lock` uses NumPy **2.4.4**;
predictive construction is automatically routed to **2.5.2**. Another version can
change a literal constructor bit-equality diagnostic even when its projector
correspondence remains valid. The lock also supplies pytest 9.0.3, SymPy 1.14.0,
mpmath 1.3.0 and packaging/build dependencies. Torch is not required.

Ubuntu 24.04's `python3.12` is 3.12.3; the README's apt-get line is for that
release. On other Linux systems, install uv without editing startup files,
add its explicit `~/.local/bin` install directory to this session's PATH, then
install the exact Python version. See [official installer options](https://docs.astral.sh/uv/reference/installer/):

```sh
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$HOME/.local/bin" UV_NO_MODIFY_PATH=1 sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.12.3 --no-bin
"$(uv python find 3.12.3)" -m venv .venv
```

Run the `find` command before `.venv` exists; afterwards it may select that
project environment. Then omit the venv-creation line below and use the same
lock/package installation. A default `uv python install` also installs
`python3.12` into `~/.local/bin`; `--no-bin` avoids that side effect, or
`UV_PYTHON_BIN_DIR` selects a different executable directory. These options are
in [uv's command reference](https://docs.astral.sh/uv/reference/cli/#uv-python-install).

The independent fresh-clone test found that copied managed interpreters from uv
failed their relative shared-library lookup. Managed creation now uses POSIX
symlinks, preserving the interpreter's install location. Under the existing
provisioning lock, a retry clears only the unfinished interpreter tree and
`pyvenv.cfg` when `stage_ready.json` is absent; it preserves the lock file.
Published environments with matching profile and lock hashes are reused
unchanged. Rerun the failed command to repair an unfinished environment;
do not delete published environments. Offline regressions reproduce the location-dependent loader failure and
exercise recovery. The independent fresh-clone uv retest passed setup, tests,
smoke, the full number check and recovery of an interrupted environment. The
latest test measurement and its conditions are recorded below.

Source [env.sh](../env.sh) in every new Bash shell from the checkout. It restores
PATH for Cargo/elan, the default Rust pin, PYTHONNOUSERSITE and the unset
PYTHONPATH; output and environment-cache defaults live in `scratch/`. Existing
output/cache/toolchain choices are preserved; empty output/cache values fail
clearly. The Python router also rejects an explicitly empty
`BORN_LADDER_ENV_ROOT`; unset it to use the default cache. Set external paths
before sourcing. Install the lock, then the package
itself:

```sh
source env.sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps .
# Populate Cargo dependencies first; the tests include offline Rust replay:
make rust rust-test-b
make test
```

For offline installation, add `--no-index --find-links "$WHEELHOUSE"` to the
lock installation, and `--no-index` to package installation. The wheel directory
must contain wheel files matching `requirements.lock` for all ten packages on
the intended platform; replace any mismatching files with the corresponding
official PyPI wheels, since `--require-hashes` rejects other builds. The
default tests use small non-empirical fixtures, require no Lean build, and exclude
historical tests. Formal command checks run under `make verify` after `make lean`.
The first standalone paper-number check also provisions `predictive_v25`
(**about 0.3 GB**); offline wheelhouses must include its separate lock, not only
`requirements.lock`. Keep the uv interpreter's install directory: its POSIX
managed environments link back to it.

Lean is **v4.28.0**, Mathlib **v4.28.0**, resolved commit
`8f9d9cff6bd728b17a24e163c9402775d9e6a365`. Put elan's bin directory on PATH;
run `make lean`, then `make lean-audit` and `make verify` (all 14 no-data claims).
Elan selects the pin from `lean_born/lean-toolchain` and installs it on demand
if absent; no separate `elan toolchain install` step is needed. Offline users
must pre-provision it. Both Lean targets stop with a named missing-tool error
if elan or lake is absent; source `env.sh` before retrying. `make lean` first runs
`lake exe cache get`
in the Lean project to fetch prebuilt artifacts for the pinned Mathlib revision,
then builds the project. If the cache cannot be fetched it prints a fallback
message and builds from source. Use `make lean LEAN_CACHE=0` to skip the fetch
for an already populated offline cache. An offline build requires the toolchain,
Mathlib packages and compiled dependencies to be pre-provisioned. Do not update
the lock. A compatible dependency cache may be copied from a previously built
package at these same pins (set `LEAN_DEPS` to its `.lake` directory):

```sh
mkdir -p lean_born/.lake
cp -a "$LEAN_DEPS/packages" lean_born/.lake/
make lean LEAN_CACHE=0
make lean-audit
```

Lean progress displays memory in **GiB**, while the documented budget uses
**GB**. Three measured four-job builds peaked at **about 40–42 GB** across the
Lean processes: **39.78 GB** in the earlier fresh clone, **about 42 GB** in full
production and **41.42 GB** in the latest warmed-cache clone. With one job,
347/347 fresh modules passed, `max_lean_processes: 1`, build-tool wall time
**11,261.8 s (about 3 h 8 min)**, and whole Make invocation **11,342 s** including
Mathlib clone/cache setup. `peak_tree_rss_bytes` was **18,124,869,632** (about
**18.1 GB**); the log showed **16.88 GiB**. Independent summed-RSS sampling gave
**18.17 GB** and the cgroup peak **18.09 GB**. That one-job run reused Mathlib
cache on a shared host with load average **7–13**. Allow OS/other-process
headroom; fewer workers do not remove serial-inference memory needs.

The audit retains its one-line JSON stdout receipt and adds a short stderr
summary: `Lean audit: PASS, 5058 declarations, axioms Classical.choice, Quot.sound, propext; forbidden: none`.
The pipeline's receipt parser ignores non-JSON lines in its combined log; other
JSON consumers of stdout see the same receipt. Errors still exit nonzero.

Copy dependency packages only, not another project's `.lake/build`: the local
BornCalculus modules must be rebuilt. [Lean coverage](../lean_born/COVERAGE.md) gives the theorem scopes.

`make rust` builds the runner in release mode using `vendor/pica/Cargo.lock`.
The local toolchain is Rust/Cargo 1.93.1; offline builds additionally require a
populated Cargo dependency cache. Use
`rustup toolchain install 1.93.1 --no-self-update` to avoid updating rustup
itself; both Rust Make targets check for rustup and cargo and name missing tools.
Rust compiler warnings are expected. `CARGO_HOME` may point to an explicit local
cache containing the locked registry packages; run `CARGO_NET_OFFLINE=true make
rust` to prohibit network access. The executable is written to
`vendor/pica/target/release/runner`. Building does not run an experiment.

### System prerequisites and measured resource budget

Use git, curl, GNU make, `python3.12-venv`, a system C linker (e.g.
`build-essential`), GNU `/usr/bin/time`, rustup/Rust
1.93.1, and elan/Lean v4.28.0. Ensure `$HOME/.cargo/bin` and `$HOME/.elan/bin`
are on PATH. Online provisioning uses PyPI, download.pytorch.org for CPU fitting
wheels, GitHub for Mathlib plus eight pinned dependencies, the Mathlib cache
server (8,010 files in the measured clone), and Cargo's locked registry crates.
Populate those caches in advance for offline use. TeX Live/quantumarticle,
BibTeX and latexmk are needed only for the optional paper.

Earlier independent fresh-clone measurement, **2026-10-13**, on Linux x86_64 AVX2/FMA
(CPU model not recorded for this test), load average **5–37**: non-editable
install with PYTHONPATH unset, fresh managed environments and caches, one
BLAS/OpenMP thread per numerical process. Install **17 s**; both Rust builds
**46 s**; serial `make test` **4 min 45 s** (665 passed, 13 skipped, 133
historical-data tests deselected); four-worker smoke **10 min 23 s**; fresh
Lean **59 min 24 s** at four jobs, **347/347** fresh modules, peak **39.78 GB**,
including about **2.4 min** of Mathlib cache fetch. Audit **2 min 42 s**, 5,058
declarations, peak **7.5 GB**; serial `make verify` **16 min 20 s**, 14/14 PASS,
peak **6.9 GB**. The test folder occupied **14 GB**, including `.lake` **9.9 GB**,
managed environments **1.5 GB** and smoke output **0.16 GB**. Its setup tally
reported approximately **17.9 GB**, including `~/.elan` **2.6 GB**, `~/.rustup`
**1.3 GB** and a **0.4 GB** Mathlib download-cache allowance. That download
cache is at `~/.cache/mathlib`, outside the checkout, rather than inside the
test folder; the latest warmed-cache test reused **1.6 GB** there. Include this
external cache in disk accounting. Budget **at least 20 GB plus headroom**,
and RAM above the measured **about 40–42 GB** peak at four jobs, plus the OS
and other processes. The default is two Lean jobs, not an 8 GiB memory guarantee.
The smoke command is silent, then emits one long JSON summary line; progress
is in `$DATA_OUT/smoke-all/logs/`.

The earlier system-Python fresh-clone test measured `make test` at **5 min 38 s**,
with **728 passed, 12 skipped, 133 deselected**, on Ubuntu 24.04 / CPython
3.12.3 with load average **12–13**, warm pip/Cargo/Mathlib caches and existing
rustup/elan toolchains. This is separate from the earlier cold-cache measurement
above. The latest uv-route fresh-clone test, **2026-10-14**, measured `make test`
at **5 min 33 s**, with **741 passed, 12 skipped, 133 deselected**. It used warm
pip/Cargo caches; managed-environment wheels were fetched from the network.
Counts change as tests are added.

`make test` provisions a managed verification environment from the network;
offline, supply `BORN_LADDER_WHEELHOUSE` as described below. The measured skips
were optional fitting-package and explicitly selected managed-interpreter checks,
plus the formerly opt-in installed-path check (now automatic);
historical-data tests are deselected. Ordinary subprocesses exercise the selected
installed package. Environment-bridge tests deliberately pass the imported
package's path or a synthetic package. `PYTHONPATH="$PWD/src"` explicitly selects
source mode; the installed-path check otherwise runs automatically, or can use
`BORN_INSTALLED_CHECK_PYTHON` to select an installed interpreter from source mode.
See [Measured full-profile segments and storage](#measured-full-profile-segments-and-storage) for
completed stage times and output/cache storage, and its ordered
[full replication sequence](../README.md#replicate-the-paper). Its resumed
segments are not one uninterrupted run or a measured from-scratch total.

Build `make rust` **before** `make rust-test-b` on a fresh Cargo cache (or run
`make rust rust-test-b`). The second target builds offline.

## Local evidence contract

### Full-cohort public registry

P03, P10, P11, P13, B08, B09, B10 and B13 now require the whole 2,122-case
census. Use a separate variable from the historical evidence bundle:

```sh
export BORN_LADDER_ENV_ROOT="$PWD/scratch/environments"
export BORN_FULL_DATA="$DATA_OUT/full"  # completed full-cohort stage tree
.venv/bin/python -m born_ladder verify P10 --data "$BORN_FULL_DATA"
.venv/bin/python -m born_ladder verify P13 --data "$BORN_FULL_DATA" \
  --certificate-output scratch/verify/P13.json
```

The stage-directory alternative needs `census/complete.json`, its entire
committed inventory, summaries, 2,122 context directories and exponent-one K
adapters, plus the immutable source files named by `census_plan.json`.
P11 additionally needs sibling `attachments/complete.json` and its committed
4,244 source-row copies and descriptive summaries. These stage outputs are
verification inputs, not a frozen historical trust anchor. Original/completion
status and robust-threshold verdict remain separate. The registered 3/20
result is 2,005 pass / 117 shortfalls; the retrospective uniform bound is 1/25.

With the completed full pipeline's Test B and bundle stages, the same
commands accept the generated `bundle/bundle.json` or its containing directory:

```sh
export BORN_FULL_DATA="$DATA_OUT/full/bundle"  # directory containing bundle.json
.venv/bin/python -m born_ladder verify B10 --data "$BORN_FULL_DATA"
```

The `born_regenerated_bundle_v1` roots resolve relative to the manifest. Census
verification opens and checks the census and cross-term unit components;
P11 also checks attachments. The cross-term unit component already contains
the captured stdout and attempt records used by the census. They must travel
with the bundle. These roots relocate the source view without changing sealed
file contents or scientific hashes. The Lean component is also required and bound to its rendered full-cohort
inputs, compiled modules and fresh audit receipts. Unrelated bundle components
need not be opened for a census claim. Historical 120-case claim bundles cannot
certify these eight current full-cohort IDs. Reduced bundles cannot certify these full-cohort claims; regenerated verification can perform explicitly nonconfirmatory reduced checks. `--profile regenerated` supports both full
verification on full inputs and those reduced checks on reduced inputs.
Historical input adapters and Fin 120 Lean declarations remain available as
historical evidence.

A fresh clone has no private data: install the pinned Python requirements and
package above, initialize the shipped Rust source, and build the merged Lean
project with its 266 census shards, General and Boundaries packages (`make lean`).
The verification audit requires current compiled artifacts and refuses stale
ones. General P01/P02 and new P14/B15/B16 need no retained data. For the eight
census IDs, obtain the full stage outputs and their source captures, or reproduce
the full pipeline using the public stage commands and take its regenerated
bundle. To relocate stage outputs before a bundle exists, place the immutable
unit tree at `units/cross-term` beside `census`; otherwise their original sealed
source mapping must still be readable. No toy fixture or historical bundle can
substitute for missing full-cohort inputs.

P03 additionally executes the public retained-K map replay. Run from the public
checkout root with `vendor/pica`, Rust/Cargo and the locked Cargo dependencies
available offline. Its build and temporary replay files stay in
`scratch/registry_full_cohort`. All three maps, stationary estimates and emitted
vectors compare exactly; a mismatch fails. Numerical envelopes retain their
conditional arithmetic/platform premises. B09 replays native constructor and
successful symbolic diagnostics. Acquisition-environment symbolic exception
events remain explicitly qualified and bound to the original outcome records;
the repaired exact mathematical certificates are checked separately.

Archive/execution identity and complete-record/source-export binding are outside
Lean. Python checks retained commitments and joins; it supplies no universal
native formation, historical source-build, access-cost, history-reconstruction,
perturbation-stability or induced-dynamics theorem. Descriptive attachments are
checked without rescoring or fresh statistical confirmation.

[Claims](claims.md) distinguishes recomputation from historical attachment.
The eight current census IDs use `--data "$BORN_FULL_DATA"` as specified above:
a completed full-cohort stage tree or full regenerated bundle. Other historical
data IDs use `--data "$BORN_DATA_BUNDLE"`, a file or directory containing
`bundle.json`, with their separately supplied retained inputs.

### Historical bundle schema records

The following `born_claim_bundle_v1` contract documents the retained historical
schema. Its census roles are **historical records, not current dispatch inputs**
for P03, P10, P11, P13, B08, B09, B10 or B13. Retaining those roles does not make
the old 120-case bundle satisfy the current full-cohort requirements. The
non-census historical data IDs below still use their listed roles; current
census verification follows the full-cohort section, including its Lean and
attachment requirements.

```json
{"schema":"born_claim_bundle_v1","roots":{"archive":"relative-storage-root"},
 "files":{"archive/input.json":"SHA-256"},
 "claims":{"ID":{"input_role":"archive/input.json"}}}
```

Relative roots resolve beside the bundle. The package's `evidence_anchor.json`
pins the digest of `schema`, `files`, `claims` and sorted root names in canonical
ASCII JSON. Only root *locations* may change. Every listed file is hash-verified
before claim dispatch; paths escaping a root and rehashed replacement bundles
are rejected. An independently supplied manifest cannot authorize new evidence.

| Historical schema records / remaining historical IDs | Retained input roles in `claims.ID` |
|---|---|
| Retired census roles: P03/P10/P11/B08/B09/B10 | `original`, `completed`, `contexts` prefix; P03 adds `formula`; P11 adds `attachments`, `summaries`, and raw/package original row files |
| P12 | `source_root`; `g2a`, `g2c`, each with `units`, `evaluation`, `verification`; separate `--historical-root` |
| B01 | `component_roles`, `provenance` |
| B04 | `context`, `amplitude_certificate`, `joined_certificate` |
| B05/B06 | `context`, `certificate` |
| B07 | `context` |
| B11 | `receipt`, `binary` |
| B12 | `raw`, `pkg`, `opening`, `join` |
| Retired census roles: B13 | `inventory`, `selection`, `census_inventory`, `source_root` |
| TB01 | `receipt`, `receipt_sha256`, `sealed_root`, `opened_root`, `certification_root` |
| Optional regression tests | `fixtures.paths`: three archived regression inputs |

These historical file roles refer to entries in `files`; root roles refer to
`roots`. They do not replace the full-cohort stage/bundle inputs. P12's
historical bundle has a separately pinned `manifest.json` with schema
`born_snapshot_historical_inputs_v1`, `files`, `commit_files`, and `tags`.
Preserved specifications, source identities, completion-writer bytes and tag
objects are explicit inputs, not private Git lookups. Compressed population
archives require `zstd`; signed historical receipts require `ssh-keygen`.
TB01's score receipt binds the already-opened records, prediction and margin
seals, and certification rows transitively. No fresh test opening is performed.

## Outputs

`.venv/bin/python -m born_ladder verify --list` lists the claim registry. Each verification
prints `PASS` or `FAIL` with its scope; failure exits nonzero. `make verify`
checks the 14 claims requiring no local data after the Lean build. `make
lean-audit` emits the declaration and axiom audit; only `propext`,
`Classical.choice`, and `Quot.sound` are permitted. `make test-data
BORN_LADDER_DATA="$BORN_DATA_BUNDLE"` runs the optional historical regressions.
For TB01, successful verification reproduces a negative experimental result.

### Fitting dependencies for end-to-end production

The restored Test B fitting library is optional. For the reproducible
CPython 3.12/Linux x86_64 fitting stack, install the CPU-only, hash-locked
`requirements-fitting.lock`, then install this package with
`--no-build-isolation --no-deps`. The automatic production commands do this
in their managed fitting environment. The optional extra can also be installed
with `pip install --extra-index-url https://download.pytorch.org/whl/cpu '.[fit]'`;
use the lock for exact version/build pins. The lock uses Torch 2.13.0+cpu,
NumPy 2.4.4 and SciPy 1.17.1, and includes every dependency. It does not install
CUDA libraries or require a GPU. The retained fits used CPU operations in a
CUDA-bearing Torch distribution. The CPU-only stack reproduced all fifteen
full-budget model/selector records of the checked Test B case byte for
byte in four spawned workers. This check covers one rank-two context with its
historical `::h8` framing.

Set `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
NUMEXPR_NUM_THREADS=1` before Python starts. The estimator requires Torch's
intra-operation threads to be one at import and never resizes a running pool.
Keep the full historical loader's context,
including the selected reading interval suffix (`::h8` in the original worked case): this
string seeds the starts. The recovered scientific libraries and specifications
are documented in [the reproduction package](../src/born_ladder/reproduction/README.md)
and [the public specifications](../specifications/README.md). The public run/capture launcher is available below. Unit collection, census
coordination, population inference and record-test coordination are implemented
in the public stages below; run capture alone is not the complete experiment.


## Public stochastic-program runs and capture

After `make rust` and package installation, use:

```sh
.venv/bin/python -m born_ladder reproduce runs --grid smoke --output scratch/new_data/smoke --workers 4
make reproduce-g2a PYTHON=.venv/bin/python OUTPUT=/path/to/data/g2a WORKERS=8
make reproduce-g2c PYTHON=.venv/bin/python OUTPUT=/path/to/data/g2c WORKERS=8
make reproduce-test-b PYTHON=.venv/bin/python OUTPUT=/path/to/data/test_b_kernels WORKERS=8
make reproduce-worked-cases PYTHON=.venv/bin/python OUTPUT=/path/to/data/worked WORKERS=2
```

The commands read `specifications/runs.json` and its registered specification
references. The live runner's EXP-112 configuration inventory must equal the
registered list. Acquisition uses v8 for G2a and v21 for G2c; later v23/v24
inference amendments do not replace G2c's source RNG identity. The smoke grid
uses the full scale and horizon; it is a diagnostic subset, not a population
reproduction. GNU `/usr/bin/time` is required (the `time` package on Debian/
Ubuntu). The coordinator uses only standard-library process/thread facilities
and requires no fitting extra.

`--output` must be outside version control: an external directory or a Git-ignored
path under this checkout. `--plan` prints the grid and selected IDs without
starting dynamics; `--only ID` is repeatable. `--workers N` controls process
concurrency. The per-process OMP, OpenBLAS, MKL, Rayon, NumExpr and vecLib thread
settings come from the run policy and are pinned to one. The default dedicated
per-invocation timeout is 1,800 seconds; `--timeout` can change the operational
limit without changing any scientific parameter. Timed-out invocations remain
recorded and are not treated as scientific exclusions.

Output layout:

```text
runset.json                          immutable grid / runner / scientific-input binding
manifest.jsonl                       append-only started / finished / abandoned attempt events
invocations/<id>/attempt_0001/
  stdout.bin                         unchanged runner stream, including structural end record
  stderr.txt
  resources.txt                      GNU time user/system CPU and peak RSS (KiB)
  headers/*.audit.jsonl               existing header: final K and raw/package/joint maps
  headers/*.record.jsonl              existing record-header metadata
  capture/*.kernel.json              supplemental final K, active lag and horizon
  capture/*.paths.json                complete already sampled discovery trajectories and starts
```

Manifest artifact paths and argv paths are relative to the output root. Each
finished attempt records exit code, wall time, CPU time, peak RSS, byte count,
artifact SHA-256 values and per-configuration export disposition. CPU accounting
unavailable after a forced interruption is explicitly `null`, not estimated.
The final summary reports actual mean busy cores as child CPU seconds divided
by batch wall time, not as the requested worker count.

Repeat the same command to resume. A completed attempt is skipped only after
checking its artifact hashes. Failed, timed-out and interrupted attempts are
kept and retried in a new numbered directory. A start left by a terminated
coordinator receives an explicit abandoned disposition. A single coordinator
owns an output root at a time. Changed grid, capture policy, binary or scientific
inputs require a new root; worker count and the selected invocation subset may
change. A malformed/incomplete manifest record fails clearly rather than being
silently discarded.

`--capture off` omits the supplemental kernel/path files. The runner's
`--full-path-capture-dir` flag is default-off and only serializes existing values;
it does not sample or consume RNG. Header sidecars remain enabled by the
launcher. Captured final matrices can exist for configurations with no legacy
export. Historical selection can be reconstructed separately; the current
amended census uses every context meeting its complete-evidence rank-two
predicate, rather than restricting it to legacy exports. Never substitute discovery paths for the separately seeded record-test
samples. The Test B command below produces calibration/train-validation samples after the
recipe census and synthetic certification; real locked-test sampling remains locked-test
and follows prediction commitment.

<a id="optional-p1-historical-acceptance-nodes"></a>

## Optional historical acceptance nodes

Without `BORN_LADDER_DATA`, historical nodes skip. Additional absent prerequisites
also produce an explicit skip reason, even when the bundle is supplied:

- Full fit: the `fit` extra (SciPy and Torch); install the historical fitting
  lock described above before running it.
- Cohort reconstruction: `E2E_P1_COHORT_OUTPUT`, a fresh output directory, and
  the full retained source/capture tree under the bundle's `repo` root.
- Original-spec comparison: `E2E_P1_HISTORICAL_ROOT`, an existing preserved
  historical-input directory.

Run each named node explicitly:

```sh
export BORN_LADDER_DATA=/path/to/local_bundle.json
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 .venv/bin/python -m pytest -q -rs tests/born_ladder/test_e2e_p1.py::test_historical_loader_seed_and_full_fit
E2E_P1_COHORT_OUTPUT=/path/to/new/cohort_check .venv/bin/python -m pytest -q -rs tests/born_ladder/test_e2e_p1.py::test_complete_cohort_reconstruction
E2E_P1_HISTORICAL_ROOT=/path/to/historical_inputs .venv/bin/python -m pytest -q -rs tests/born_ladder/test_e2e_p1.py::test_readable_values_equal_retained_original_specifications
```

A malformed present input or a failed scientific comparison remains a failure;
the prerequisite gate does not turn disagreements into skips.


<a id="predictive-unit-construction-and-structural-collection-p2b"></a>

## Predictive unit construction and structural collection

After capture completes, construct units without opening the retained evaluation
archive:

```sh
.venv/bin/python -m born_ladder reproduce units --grid competitor --runs "$DATA_OUT/runs/g2a" --output "$DATA_OUT/units/g2a" --workers 32
.venv/bin/python -m born_ladder reproduce units --grid cross-term --runs "$DATA_OUT/runs/g2c" --output "$DATA_OUT/units/g2c" --workers 32
make reproduce-units UNIT_GRID=cross-term RUNS="$DATA_OUT/runs/g2c" OUTPUT="$DATA_OUT/units/g2c" WORKERS=32
```

`--output` is required, external to Git or Git-ignored, and disjoint from input
roots. The public `specifications/units.json` maps versions through
`specifications/amendments.json`: competitor science uses v8; cross-term science
uses effective v24 with the unchanged v21 identity/RNG namespace. Structural
output schemas and historical transport basenames are published inline in the
readable version files. They are data-format contracts, not permission to open
historical review or launch records. All scientific functions are shared with
`born_ladder.snapshot`. No population bootstrap, randomization test, Holm
adjustment or population verdict is calculated by this stage.

The declared diagnostic subset uses both worked cases and the complete EXP-105
invocation at the eighth cross-term seed. Produce its captures and units with:

```sh
.venv/bin/python -m born_ladder reproduce runs --grid worked-cases --output "$DATA_OUT/runs/worked" --workers 2
.venv/bin/python -m born_ladder reproduce runs --grid g2c --only EXP-105__all__s840008__n32 --output "$DATA_OUT/runs/named-subset" --workers 1
.venv/bin/python -m born_ladder reproduce units --grid smoke --runs "$DATA_OUT/runs/worked" --runs "$DATA_OUT/runs/named-subset" --output "$DATA_OUT/units/smoke" --workers 5
```

Repeated `--runs` supplies disjoint capture sets. The smoke profile has two
competitor invocations and three cross-term invocations; its seeds and membership
are diagnostic and establish no registered population result. Partial registered
grids enumerate every missing invocation and return nonzero, rather than silently
using a smaller population. Actual input execution failures remain incomplete
inputs; construction and control failures have retained findings and dispositions.

Output layout:

```text
unit_plan.json                      immutable code/spec/grid/input-plan binding
manifest.jsonl                      append-only attempts and collection events
invocations/<evaluation>__<id>/attempt_0001/
  stdout.bin                        committed original capture bytes
  <sha256>.attempt.json              committed original attempt metadata
  invocation.json
  structural.jsonl                  independently reconstructed, runner-checked
  runner_structural.json
  units.jsonl                       paired canonical raw/package records
  admission.jsonl                   eligibility/exclusion/nondegeneracy/ties
  controls.jsonl                     cross-term registered controls
  rotation_evidence.json             all registered rotation replicate evidence
  segment_census.json                partial/complete export guard dispositions
  package_reconstruction.jsonl       raw-only package reconstructions
  failure.json                      present on an input/construction failure
collections/collection_0001/<evaluation>/
  campaign.json                     relative stdout/attempt/structural bindings
  invocation_manifest.json
  structural_manifest.jsonl
  rb1v2_g2a_units.jsonl              competitor stream
  rb1v2_g2c_v23_units.jsonl          effective cross-term stream
  rb1v2_g2c_v23_controls.jsonl
  rb1v2_g2c_v23_pkg_reconstruction.jsonl
  admission.jsonl
  source_dispositions.jsonl
```

The control link in each aggregate unit binds the closed aggregate control file;
each invocation's own link binds its local closed control file. Historical
basenames containing `v23` are retained by the effective v24 serialization
contract. Cross-term/CB2 structural unit bindings include the JSONL final LF; the
competitor v8 binding and independent runner wrapper hash without LF. Canonical unit ordering follows
the historical builders, irrespective of worker completion order.

Repeat the command to resume. Completed unit artifacts and input bindings must
match their hashes. Failed or abandoned attempts are kept; new attempts use new
directories. Graceful interruption stops scheduling and closes in-flight work;
forced termination leaves retained attempts to be marked abandoned on resume.
Every new collection has a new numbered directory; earlier collections are not
rewritten. Use the latest *complete* collection's `campaign.json`,
`invocation_manifest.json` and cross-term unit file as census inputs, with the unit
output root as their common input root. The census still applies the original kernel
availability rule; extra capture does not turn a higher-power propagator into
an original one-step-kernel artifact.

Process workers pin numerical threads to one. Per-invocation CPU/wall time and
worker peak RSS are recorded; RSS is the process high-water mark through that
invocation, not a simultaneous total or a fresh per-job peak. The final summary
separates attempt output bytes from closed collection bytes.

Retained captures can be adapted explicitly to the same public command without
reading scientific result rows. Supply a root containing `capture_index.json`
with schema `born_unit_capture_index_v1` and an `invocations` list. Each entry has
`invocation` (experiment, config_or_null, seed, scale and optional historical
invocation metadata), `execution_status`, `stdout_path`, `stdout_sha256`,
`attempt_path`, and `attempt_sha256`. Paths are relative children of that supplied
root; stdout and attempt bytes must have the declared hashes. Preserve actual
historical metadata rather than inventing new execution receipts. Original
metadata bytes can contain old recorded locations; these are retained provenance
and are never followed by the coordinator. No private Git or internal ledger is
read at runtime.

Optional post-write comparison accepts explicit JSONL reference files:

```sh
.venv/bin/python -m born_ladder reproduce compare-units --generated "$DATA_OUT/units/g2a/collections/collection_0001/competitor/rb1v2_g2a_units.jsonl" --reference /path/to/reference_units.jsonl
```

It reports membership/order, exact identity/label/count/disposition comparisons,
IEEE-754 binary64 equality (including signed zero), and every maximum absolute
float difference without tolerance-based acceptance. Provenance bindings are
reported separately. Compressed retained artifacts may be opened through the
existing public archive reader and passed as the comparison API's reference
iterator, after regeneration has closed its outputs.

The initial unit construction comparison under NumPy 2.4.4 generated all 10,988 competitor
rows and 22,354 cross-term rows, with matching membership, order, labels, counts,
eligibility and exclusions but different basis-dependent values and two changed
tie flags. Repeating the complete construction under the historically recorded
CPython 3.12.3 / NumPy 2.5.2 / bundled OpenBLAS 0.3.34.0.0 stack, with one numerical
thread per process, reproduced both canonical unit streams and the cross-term
control stream byte for byte. All admission fields, including those tie flags,
matched. No archived basis or loss was a construction input. This establishes
unit-value reproduction on retained captures; it does not establish
basis-independent diagonal comparisons or reproduce population statistics.

The CLI selects separate numerical profiles automatically: predictive unit
construction uses NumPy 2.5.2 / bundled OpenBLAS 0.3.34.0.0; verification and
census construction use NumPy 2.4.4 / bundled OpenBLAS 0.3.31.188.0. Readable
profiles and hash-locked wheels are in `specifications/environments/`. Each
scientific entry point checks interpreter version, platform, NumPy and native
library hashes, effective backend and one thread per process. OpenBLAS is
restricted to Haswell; higher NumPy vector dispatch is disabled. The public
package accepts both stage NumPy versions; the stage locks select the version.

A matching current interpreter is reused. Otherwise the same command creates
and validates a managed virtual environment, then re-executes transparently.
The default cache is `$XDG_CACHE_HOME/born-ladder/environments` when
`XDG_CACHE_HOME` is set, otherwise `~/.cache/born-ladder/environments`. Set
`BORN_LADDER_ENV_ROOT` to override either location. For offline provisioning set
`BORN_LADDER_WHEELHOUSE` to one or more wheel directories separated by `:` on
Linux. They must contain every wheel in the two stage locks. No archived data,
private Git history or review receipt is used for provisioning. An already
selected managed runtime that fails validation is refused before construction.
Concurrent provisioning is locked; interrupted installation can be retried.

The symbolic diagnostic needs SymPy 1.14.0 with GMP ground types. The archived
thirteen errors explicitly name `mpz`; without GMP these checks succeed instead.
The verification/census profile additionally pins gmpy2 2.3.1 and its native
libraries. This profile reproduces the original statuses and successful
symbolic certificates; the retained census records do **not** independently
attest the historical gmpy2 version. Completed certificates use exact Fraction
and quadratic-ring arithmetic, independent of this failing symbolic path.

The matched interpreter/backend identities are required for reproducing the
retained implementation-dependent bases; a version string alone is not a
portable bitwise guarantee. The immutable unit plan now binds the interpreter,
NumPy version, loaded NumPy/BLAS/LAPACK library hashes, CPU features, requested
thread policy and effective OpenBLAS pools. A resume with a different or formerly
unbound runtime fails before changing the manifest. Use a new output root when
changing environments. The current identity probe supports Linux/OpenBLAS and
fails explicitly on an unidentified backend. The optional comparator's overall
agreement and CLI success require both exact scientific fields and row order.

In the initial NumPy 2.4.4 run on the measured host, with one numerical thread
per process and 32 workers,
full competitor construction took approximately 37 seconds and 404 worker CPU
seconds; full cross-term construction, including all registered per-unit
controls, took approximately 40 minutes and 70,416 worker CPU seconds. Worker
RSS high-water marks were about 48 MiB and 165 MiB respectively. Attempt files
plus one closed collection occupied approximately 1.51 GB and 3.56 GB; retained
input capture storage is additional. These are host measurements, not promised
runtimes or simultaneous-memory measurements.

The named fresh-input check can be run after producing the diagnostic subset:

```sh
E2E_P2B_COLLECTION="$DATA_OUT/units/smoke" .venv/bin/python -m pytest -q tests/born_ladder/test_e2e_p2b.py::test_fresh_collection_has_independent_laws_and_census_inputs
```

It checks the reconstructed laws against independent arithmetic, both historical
structural-hash conventions, and direct consumption by the public census
inventory writer. It skips with a reason when `E2E_P2B_COLLECTION` is absent.


<a id="census-structural-construction-p3a"></a>

## Census structural construction

From full captures and their closed unit collection:

```sh
.venv/bin/python -m born_ladder reproduce census --units "$DATA_OUT/units/g2c" --runs "$DATA_OUT/runs/g2c" --output "$DATA_OUT/census" --workers 8
make reproduce-census UNITS="$DATA_OUT/units/g2c" RUNS="$DATA_OUT/runs/g2c" OUTPUT="$DATA_OUT/census" WORKERS=8
```

For the declared diagnostic subset, replace the unit root with the smoke root
and repeat `--runs` for the worked-case and named-family capture roots. The
constructor reads the cross-term collection by default (`--evaluation competitor`
is also supported). It selects the latest **closed** unit collection and reports
whether that source collection covers its declared invocation list. The census
worker cap is eight. Output must be external or Git-ignored and disjoint from
all inputs. Repeat the same command to resume: input/code/specification/runtime
changes or altered completed artifacts are refused. Interrupted inventory and
context attempts remain; a new attempt never overwrites them.

Selection is CB2's conjunction: state count 32, effective rank two, source span
available, an actual exponent-one matrix, and a verified immutable raw/package
join. Higher matrix powers cannot supply a missing matrix. Cases are ordered by
the SHA-256 of the complete canonical provenance key and then the unit identifier.
`specifications/census.json` states the rules. Native final-matrix captures
can supply a previously missing matrix. Their exact JSON field bytes are wrapped
in a tagged I/O envelope for the recovered constructor; the envelope's exponent
metadata describes K itself and is **not** a historical sequential observation.
This extra capture can enlarge a fresh available cohort. The command reports
all available cases; it does not silently choose the historical 120 or assert
that a larger cohort reproduces its membership.

Logical source names are selection identities, while actual paths and attempt
records describe execution. For relocated retained captures use
`--logical-sources <correspondence.json>` if the original logical names are to
be preserved. The readable `born_census_logical_sources_v1` contract has
`logical_units_path`, `logical_structural_path`, and a `captures` list with
`invocation_id`, `logical_stdout_path`, `stdout_sha256` and
`attempt_record_sha256`. Extract names from the actual acquisition bindings;
never invent a historical execution. Names must be relative, cover exactly the
closed collection, and match current capture/attempt bytes. The input file is
hashed in the stage plan. Without it the public collection's own relative names
are used. The checked logical-to-execution map is written separately from the
unchanged complete selection keys. No reviewed inventory is a production input.

Output layout:

```text
census_plan.json                     immutable inputs/code/spec/runtime identity
inventory_attempts/attempt_0001/inventory/
  RETURN_CARRIER_INVENTORY.json      every paired context and availability
  INVENTORY.json                    ordered available cases
  INPUT_CORRESPONDENCE.json          logical names, actual locations, byte hashes
inventory_complete.json             committed structural inventory
kernel_adapters/                     unchanged native matrix bytes in I/O envelopes
manifest.jsonl                      append-only context attempts/dispositions
construction_attempts/<unit>/attempt_0001/contexts/<unit>/
  CONTEXT.json                      exact frame and structural source fields
  structural_completion_certificate.json
  original_implementation.json      extra-coordinate and symbolic statuses
  six_state_symbolic_original.json  only when the symbolic check completed
  six_state_exact_completion.json   exact quadratic-ring certificate
  instrument_root_controls.json     rational principal-root enclosures
  integer_frame.json                integer point-readout inputs
  maximal_gap_witness.json           exhaustive maximizer, lexicographic ties
summaries/summary_0001/              ordered status tables and maximal-gap rows
complete.json                       whole-output structural commitment
```

The lexicographic witness is computed by the recovered anonymous-record search;
the maximal-gap witness uses the same exact IntegerFrame readout as public P13.
The `3/20` bound is **checked**, not assumed for fresh inputs. All active atoms
receive exact effects, Gram determinants and positive/singular classes. Original
SVD-coordinate requirements and GMP symbolic overflows remain separate from the
registered projector/own-input gates and exact completion. Performance fields,
reviewed certificates and scratch proof notes are not read. No new Lean audit
or performance summary is claimed here; those are produced by the Lean-input and population-evaluation stages.

Optional comparison opens a reference only after construction has closed:

```sh
.venv/bin/python -m born_ladder reproduce compare-census --generated "$DATA_OUT/census" --reference "$REFERENCE_CENSUS" --lean-root lean_born > census_comparison.json
```

The comparison checks full membership/order, complete keys, exact frames,
lexicographic witnesses, maximal-gap pairs and all embedded integer fields,
atom classes, every stored numeric range and original/completed statuses. Exact
binary64 equality is required; differences are reported with no acceptance
tolerance. Only explicitly named timing/output-location/proof-file bindings are
excluded. The thirteen original symbolic failures have no stored root-control
files; their newly computed bounds are independently verified and listed as
unavailable for stored-bound comparison. This is disclosed, not called equality.

Named data acceptance (optional retained inputs):

```sh
BORN_LADDER_DATA="$RETAINED_BUNDLE" E2E_P3A_OUTPUT="$DATA_OUT/census" E2E_P3A_REFERENCE="$REFERENCE_CENSUS" .venv/bin/python -m pytest -q tests/born_ladder/test_e2e_p3a.py::test_complete_retained_structural_comparison
```

This node skips clearly if either prerequisite is absent. The optional named
symbolic-backend check uses `E2E_P3A_VERIFICATION_PYTHON=<managed-bin/python>` and
`test_original_gmp_overflow_and_exact_completion`; it needs no retained data.

<a id="population-inference-and-census-attachments-p4"></a>

## Population inference and census attachments

After complete unit construction, run the two historical registered evaluations:

```sh
.venv/bin/python -m born_ladder reproduce evaluation --evaluation competitor --units "$DATA_OUT/units/g2a" --output "$DATA_OUT/evaluation/g2a"
.venv/bin/python -m born_ladder reproduce evaluation --evaluation cross-term --units "$DATA_OUT/units/g2c" --output "$DATA_OUT/evaluation/g2c" --workers 32
```

Equivalent targets are `make reproduce-evaluation EVALUATION=competitor
UNITS="$DATA_OUT/units/g2a" OUTPUT="$DATA_OUT/evaluation/g2a"` and the corresponding
`EVALUATION=cross-term` command. Each command automatically selects the existing
hash-locked predictive environment. The actual computing process checks its
loaded NumPy/BLAS/LAPACK libraries, dispatch and thread policy after scientific
imports. The immutable plan binds the interpreter, native libraries, source,
readable contracts and complete ordered input collection. Incomplete campaigns
are refused; diagnostic subsets do not produce registered population verdicts.
Failed/interrupted attempts remain in the journal and retries create new attempt
directories; a completed, hash-checked seal is reused.

The kernels use the original RNG identities, hierarchy and weights, 20,000
whole-seed bootstrap replicates, BCa jackknife, complete sign enumeration, Holm,
registered sensitivities and decision tables. The competitor kernel preserves
v8 floating signed-sum enumeration; cross-term v24 uses the exact-dyadic integer
counting helper. Both enumerate every assignment of the twenty signs. Historical
reproduction does not replace v8 tail arithmetic with the prospective v25 rule.
The cross-term computation uses v24 with v21 acquisition/RNG identity. Its sealed
rotation evidence is reconstructed and checked before population inference;
`--workers` parallelizes only the unchanged independent per-unit rotation
reconstruction, with a post-import runtime check inside every worker and
input-hash-bound results. The default is one worker; the example requests
thirty-two. Bootstrap and sign calculations retain their registered order and
streams. Excluded rows' deliberately nulled control inputs are recovered from their
sealed stdout by the same unit constructor. No reference evaluation is opened.
Serviceability is stored in its historical positive-benefit orientation,
`2*TV(L_full)-TV(q_full)`; the paper's `S₂` is its negative, with interval endpoints
negated in reverse order.

After the structural census is sealed, attach its unit performance records:

```sh
.venv/bin/python -m born_ladder reproduce census-attachments --census "$DATA_OUT/census" --units "$DATA_OUT/units/g2c" --output "$DATA_OUT/census-performance"
make reproduce-census-attachments CENSUS="$DATA_OUT/census" UNITS="$DATA_OUT/units/g2c" OUTPUT="$DATA_OUT/census-performance"
```

This is a separate verification-environment stage. It verifies the structural
seal and ordered original/completed status tables, binds the identical closed
unit collection, joins both label maps by their full provenance key, copies
original JSON fields and checks control links. It does not rescore. The
`descriptive_summaries.json` file uses exact rational representations of the
stored binary64 losses and type-seven quantiles, retaining the historical
eligibility denominators and every case independently of structural status.
An independent rational-quantile checker validates the summaries. Original
implementation failures remain distinguished from completed structural gates.

Outputs are in append-only `attempts/attempt_NNNN/` directories, with an immutable
stage plan, journal and `complete.json` output commitments. The evaluation
artifact contains every bootstrap replicate, jackknife value, sensitivity, RNG
audit, tail, endpoint and verdict; its summary reports wall/CPU time, peak RSS
and output bytes. The retained archive is an optional **post-production**
comparison input, never an inference or attachment prerequisite. For a retained
evaluation comparison use the public command:

```sh
.venv/bin/python -m born_ladder reproduce compare-evaluation --generated "$DATA_OUT/evaluation/g2a/attempts/attempt_0001/evaluation.json" --reference "$REFERENCE_EVALUATION"
```

It compares full arrays and
binary64 bytes, without a tolerance. Archive packaging and old launch receipts
are reported separately from scientific fields.

The historical diagonal comparator is reproduced here, including its degenerate
SVD basis dependence. This command does not run the corrective v25 evaluation or
change the historical cohort, resampling budget or verdict.

The retained-input full-contract measurements for population evaluation were 1,263.745 wall seconds
and 1,263.493 CPU seconds for the competitor evaluation, and 1,613.087 wall
seconds and 29,924.909 summed CPU seconds for cross-term inference with thirty-two
admission workers. Process peak RSS was 28.8 GiB and 37.0 GiB respectively; allow
roughly forty GiB RAM plus operating-system headroom. Pretty-printed full
outputs were about 4.25 GB and 6.03 GB. Worker RSS includes shared fork pages;
these figures do not claim an aggregate physical-memory peak. Census attachments
took 192.674 wall seconds, 191.678 CPU seconds and 0.149 GiB peak RSS. These are
measurements on the retained full cohorts with every registered resample kept,
not fresh full-profile reproduction estimates.

Optional population evaluation data nodes require the normal data-marker prerequisites
(`BORN_LADDER_DATA` and `-m data`). Set `E2E_P4_OUTPUT`/`E2E_P4_REFERENCE` for a
full evaluation comparison; `E2E_P4_ATTACHMENTS`/`E2E_P4_CENSUS_REFERENCE` for the
complete scientific attachment comparison. The serial-versus-parallel admission
node uses `E2E_P4_UNITS` and must run in the checked predictive profile. Each skips
with a specific reason when its prerequisites are absent. Production profiles do
not install pytest; install that test-only dependency in a separate environment
using the same public predictive lock when running the latter node.

## Corrective v25 evaluation

The freeze is the git commit of the specification and the code. After that
commit, run both registered campaigns and their unit construction/inference:

```sh
.venv/bin/python -m born_ladder reproduce v25 --output "$DATA_OUT/v25" --workers 16
```

The command builds the runner if absent, resumes interrupted stages, and ends
with verdicts.csv, verdicts.md and verdicts.json. Seeds and numerical contracts
come only from specifications/predictive_v25.json. The canonical diagonal is
primary; orientation sensitivity and the fresh historical SVD reference are
descriptive only. Registered inference uses 20,000 bootstrap replicates and
exact-integer sign tails with the fixed Holm families and outcome table.

`--workers` controls both runner invocations and unit-construction invocations.
Unit workers use the same bounded spawn scheduler as the historical unit stage,
with one native thread per process and a computing-runtime check in each worker.
Scientific rows are collected in registered grid order, independently of worker
completion order. Completed invocation directories are reused; unclosed or
partially written attempts are preserved and rebuilt in a new attempt directory.
An unterminated final journal record is preserved under `journal_recovery/`
before resuming. Population bootstrap streams and statistics are unchanged;
the existing population kernels remain serial.

The individual stage also supports parallel construction:

```sh
.venv/bin/python -m born_ladder reproduce v25-construct --evaluation competitor --runs "$DATA_OUT/v25/competitor/runs" --output "$DATA_OUT/v25/competitor/units" --workers 16
```

Use CPython 3.12. Automatic stage routing provisions the pinned NumPy 2.5.2,
SciPy 1.18.1 and symbolic stack; the actual computing process checks versions
and one-thread Haswell OpenBLAS dispatch. See
[environment instructions](../specifications/environments/README_V25.md).
There is no seed-scan, attestation, native-hash, second-CPU or freeze-bundle gate.
Historical stages retain their original environments and contracts.

For a new synthetic pipeline, without reserved seeds or retained scores:

```sh
.venv/bin/python -m born_ladder reproduce v25 --output "$DATA_OUT/v25-synthetic" --workers 4 --synthetic
```

Only synthetic mode permits a reduced --replicates count. Per-invocation
journals and scientific artifact checks detect corrupted outputs on resume.
Targeted checks are tests/born_ladder/test_v25.py; V25_TEST_PYTHON selects the
managed interpreter for computing-process version/thread tests. The production
lock does not include pytest. The completed registered output was written from
2026-10-07 19:44 to 2026-10-08 02:22 UTC, about 6.6 h including at least one
resume, and occupied 49.6 GB. These are measurements of that resumed output,
not an uninterrupted-run timing.


<a id="worked-case-certificates-and-eight-lean-inputs-p3bp3c"></a>

<a id="worked-case-certificates-and-full-cohort-lean-inputs-p3bp3c"></a>

## Worked-case certificates and full-cohort Lean inputs

These stages use captures and the completed structural census. They do
not read a retained certificate, performance attachment, private Git history,
proof scratch note, or reviewed-output directory to manufacture an output.
`specifications/worked_cases.json` states the worked-case contexts, source
ensemble charts, exact-arithmetic precision and registered finite family. Run
seeds and configurations resolve through the existing `runs.json` grid.

```sh
.venv/bin/python -m born_ladder reproduce runs --grid worked-cases --output "$DATA_OUT/runs/worked" --workers 2
.venv/bin/python -m born_ladder reproduce worked-cases --runs "$DATA_OUT/runs/worked" --output "$DATA_OUT/worked-certificates"
make reproduce-worked-case-certificates RUNS="$DATA_OUT/runs/worked" OUTPUT="$DATA_OUT/worked-certificates"
```

Repeat `--runs` if the two worked cases are in separate capture roots. Each must
have exactly one successful matching capture, including the final-matrix and
audit-header exports. The source/matrix/maps are joined on the actual run
identity; the emitted preparation is replayed with the original sequential
binary64 operation order. There is no row normalization. The exact arithmetic
then treats emitted binary64 entries as dyadic rationals.

The `original/` directory contains `CONTEXT.json` and `certificates.json`:
K and K² encoder-only and augmented-description pairs; their source and
successor/root enclosures; the equal-barycenter two-read word; the twelve
registered programs, seventy-two word occurrences and every test-tagged
subset effect; the finite non-density parameter and proper-event bound; the
raw-one/package-zero order word in both orders; and the numerical fields needed
by B04–B07 Lean inputs. `selected/` contains the exact frame, all labelled
effects, point strictness witness, carrier premises and quadratic-ring six-state
certificate, and RI numerical input fields. Successful outputs are deterministic. Interrupted writes use a
temporary file; reruns check numerical outputs before reusing them. Resource
measurements go into separate `cost_NNNN.json` files. No sampling, fitting or
population inference occurs in this stage.

```sh
.venv/bin/python -m born_ladder reproduce lean-inputs --census "$DATA_OUT/census" --worked-cases "$DATA_OUT/worked-certificates" --output "$DATA_OUT/lean-rendered"
make reproduce-lean-inputs CENSUS="$DATA_OUT/census" WORKED_CASES="$DATA_OUT/worked-certificates" OUTPUT="$DATA_OUT/lean-rendered"
make lean LEAN_ROOT="$DATA_OUT/lean-rendered"
make lean-audit LEAN_ROOT="$DATA_OUT/lean-rendered"
```

`lean-inputs` rechecks the exact worked-case equations and inequalities, census
order/completeness, scaled integer frames, lexicographic point witnesses,
atom determinants, principal-root bounds, six-state premises and maximal-gap pairs. For the registered 2,122-case full cohort it renders 266 shards and
`FullInputs`, `FullWitness`, `AuditFull`, alongside `RIInputs` and `B04Inputs`
through `B07Inputs`. The complete fresh declaration inventory is audited.
Historical Fin 120 endpoints remain available as historical evidence; they are
not the full-profile census criterion. Reduced/other cohorts receive all exact
checks and explicit formal NOT_APPLICABLE, without a substitute confirmatory
proof. A full-profile 2,122-case run requires full-cohort build/audit coverage.
Fresh maximal-gap certificates record the registered 3/20 outcome separately
from the retrospective 1/25 bound. No reviewed certificate is a construction
input.

For applicable registered inputs, the output is an isolated Lean project with public proof sources copied from
`lean_born` (override with `--lean-root`). Existing `.lake/packages` are shared
and existing build artifacts are copied into the output if available, so this
uses the standard local build. Compilation writes its own copied build cache.
If dependencies have not been installed yet, follow the ordinary Lean setup
above; Lake resolves the public pinned dependencies. Nothing overwrites the
repository's full-cohort or worked input modules. `make lean` and `make lean-audit` accept
`LEAN_ROOT` for this purpose; default behavior is unchanged. The audit accepts
only `propext`, `Classical.choice`, and `Quot.sound`.

The entry point succeeds after checking other cohorts, but does not render
substitute census proof inputs. The top-level command reads the formal-coverage
report: it builds and audits matching registered inputs, and continues the
numerical pipeline with an explicit limit for all other cohorts. There are no extra attestation, seed-scan, or
hash-binding gates on these stages. The arithmetic is integer/Fraction/isqrt;
it does not use an SVD, BLAS, or platform floating-point square roots for exact
certificates and needs no additional numerical environment.

An optional comparison runs only after certificates have been written:

```sh
.venv/bin/python -m born_ladder reproduce compare-worked-cases --generated "$DATA_OUT/worked-certificates" --reference "$REFERENCE_WORKED" > worked_comparison.json
```

The supplied reference root contains the retained `amp1`, `amp1b`, `E1`, `E2`,
`E3`, and `RI` records, plus the release completion's
`non_trace_rederivation.json`. These can be copied or linked under that root;
there is no implicit private location. Comparison covers exact values, every
interval endpoint, ordered pairs/words/events/counts and scientific flags.
Binary64 values must agree bit for bit, and rational/algebraic content must
agree exactly; differences are reported without a numerical tolerance.
Historical symbolic six-state matrices are parsed in a bounded exact grammar
and compared in the same quadratic ring, not approximately evaluated.
Only timings, storage/process bindings and narrative prose are excluded.

Portable targeted checks:

```sh
.venv/bin/python -m pytest -q -m 'not data' tests/born_ladder/test_e2e_p3bc.py
```

Optional complete retained comparison (skips with a clear reason when the
three stage/reference roots are not supplied):

```sh
BORN_LADDER_DATA="$RETAINED_BUNDLE" E2E_P3BC_WORKED_OUTPUT="$DATA_OUT/worked-certificates" E2E_P3BC_REFERENCE="$REFERENCE_WORKED" E2E_P3BC_LEAN_OUTPUT="$DATA_OUT/lean-rendered" .venv/bin/python -m pytest -q tests/born_ladder/test_e2e_p3bc.py::test_complete_worked_case_reference_and_eight_modules
```


<a id="test-b-production-through-prediction-commitment-p5"></a>

## Test B production through prediction commitment

From the capture `test-b` kernel grid, run:

```sh
make rust rust-test-b
.venv/bin/python -m born_ladder reproduce test-b --runs "$DATA_OUT/runs/test-b" --output "$DATA_OUT/test_b" --workers 16
make reproduce-test-b-production RUNS="$DATA_OUT/runs/test-b" OUTPUT="$DATA_OUT/test_b" WORKERS=16
```

The stages, in order, are `census`, `certify`, `sample`, `fit`, `commit`.
`--stage NAME` runs one stage in the same root; sampling constructs a missing
census but still requires completed synthetic certification. Repeat the same
input/output/subset options to resume; the worker count may change. Public
captures and specifications are the only acquisition inputs. `--headers DIR`
is an alternative explicit captured-header input (not a discovery-path or
calibration archive); only each file's first line is consumed. The full grid
requires its complete 140 internal-kernel header set at scale 32/seed 910000.
Named-family internal configurations remain distinct kernel objects. A smoke
capture root accounts explicitly for invocations outside the Test B kernel grid.

Recipes, closure values, lags and eligibility reuse the recovered v6 constructor.
Original header bytes determine recipe order and the sampler's SHA-256 RNG
domains. The separate `test-b-sampler` binary reads those matrices and maps and
calls the original Rust v6 train/validation sampler. It never reruns dynamics or
spectral construction, consumes no extra random draws, and exposes no locked-test
option. Outputs include independent 8192-reading calibration for all 60 recipes
and 32 65-state paths per declared training/validation cell. Audit micro states
and model-visible records stay separate; only filtered records reach fitting.
The historical `::h<h_c>` context suffix is retained in every fit and refit.

Registered certification uses all 200 fidelity cases, all four 100-case classical
families and their pooled false-square checks, the 100 split-state controls and
100 complete-incidence census-matched pseudo-campaigns. It retains the registered
96 starts, 200 warm/500 polish budgets, five outer refits, 200000 inference draws,
thresholds and failure dispositions. It stops at any failed scientific gate;
it does not change counts, seeds or thresholds to obtain a pass. The real fit
stage uses every eligible context/model dimension, the training-selected primary
starts, validation selectors, training-optimized diagonal and temporal rivals,
and all five isolated two-block folds for margins. Commitment includes 22 actual
full relabel refits per context/model dimension, all 1000 descriptive training
block audits, allowlist rejection and the unchanged structural-erasure omission.
It writes `prediction_seal_manifest.json` for locked scoring; it opens no real locked-test
paths or held-out closure census during these stages. `verify TB01` continues to
import only score-only modules and needs no fitting extra.

The `test_b_fitting` profile automatically uses CPython 3.12.3, NumPy 2.4.4,
SciPy 1.17.1 and **Torch 2.13.0+cpu** (the CPU-only distribution),
with one native thread and Haswell OpenBLAS dispatch. The recovered historical NumPy/
Torch versions were recovered; SciPy 1.17.1 is the measured matching stack,
not an asserted original complete environment record. The checking process
imports the scientific stack first, then verifies versions and the effective
NumPy/SciPy/Torch thread settings. Scientific workers use `spawn`, inherit the
thread environment before importing Torch, and check their own loaded runtime
before computing. Fit settings, including declared smoke budgets and configured
certificate paths, are passed explicitly. No worker resizes an inherited
Torch/OpenMP pool. The shared census router exposes only `born_ladder`, keeping caller
dependencies out of the managed interpreter. No interpreter/native-library hash,
code-freeze receipt, hardware attestation or seed scan is required. Numerical
version/backend changes refuse a resume.

To provision offline, set `BORN_LADDER_ENV_ROOT` to a cache outside Git or under
`scratch/`, and `BORN_LADDER_WHEELHOUSE` to one or more platform-compatible wheel
directories separated by the OS path separator. Supply all packages and
transitive dependencies from `specifications/environments/test_b_fitting.lock`.
The hashed fitting lock pins the `+cpu` build from the PyTorch CPU index, with
no CUDA, NVIDIA or Triton dependencies. Provisioning requires hashes and starts
with an empty environment; a CUDA build is refused. Without a wheelhouse, the
router uses pip's public indexes. Alternatively install
`requirements-fitting.lock` in a dedicated environment and install this package
without replacing those numerical pins. Keep fitting dependencies out of the
score-only verification environment.

Interrupted work is preserved in numbered attempts. Only completed sampling and
fit results are reused; partial fit directories move to `incomplete/` before
reconstruction. The coordinator publishes filtered data atomically and orders
all fit/fold/control aggregation deterministically. Input changes and corrupt
completed numeric checkpoints refuse reuse. Saved hashes in recipe/RNG identities,
record allowlists and prediction commitments protect numerical data; there are
no historical process-binding prerequisites.

A declared reduced check is:

```sh
.venv/bin/python -m born_ladder reproduce test-b-certify-smoke --census "$DATA_OUT/test_b/census/eligibility.json" --output "$DATA_OUT/test_b-synthetic" --workers 8
.venv/bin/python -m born_ladder reproduce test-b --runs "$DATA_OUT/runs/test-b" --output "$DATA_OUT/test_b-subset" --smoke --only EXP-112:loo_A5 --workers 8
```

The synthetic check retains full per-fit and bootstrap budgets but reduces
classical/pseudo incidence to one example/model dimension, separately records
all gates and exercises positive/negative decision boundaries. Every reduced
output is `SMOKE_NONCONFIRMATORY`; it cannot authorize the registered real test.
Subsets and smoke mode must be declared from the first command in their root.
The successful resumed Test B segment took about **55 h**, including **53.3 h**
recorded certification. See the measured segment table below; no registered
budget is reduced.

Targeted production tests need the fitting stack and the compiled public sampler:

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 RAYON_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 .venv/bin/python -m pytest -q tests/born_ladder/test_e2e_p5.py
```

They skip clearly when the optional fitting packages or sampler binary are absent.
All fixtures are generated synthetically inside the test output directory; no
private archive, runtime Git history or locked real test is required.

<a id="complete-production-and-regenerated-verification-p6p7"></a>

## Complete production and regenerated verification

Use CPython 3.12.3 on the documented Linux x86-64 numerical profile; install the
base lock and package following the README, and run `make rust rust-test-b`.
All stage-specific environments are automatically provisioned/routed. An offline
wheelhouse must contain the official wheels from the predictive, verification
and fitting locks; fitting uses the CPU-only Torch wheel and its dependencies.
Do not install fitting dependencies into the base verification environment.

```sh
export LEAN_JOBS=4  # inherited by make lean; default is two
.venv/bin/python -m born_ladder reproduce all --output "$DATA_OUT/full" --workers 48
.venv/bin/python -m born_ladder reproduce all --profile smoke --output "$DATA_OUT/smoke" --workers 4
```

The full command orders captures, units, structural census, worked-case
certificates, attachments and population inference, full-cohort and worked-input
rendering, Lean build/audit, Test B certification/training/commitment, locked
opening and scoring, and regenerated bundle verification. The full profile
requires registered ordered inputs and full formal coverage; other cohorts
receive exact case checks with formal coverage not applicable. Each stage writes its own logs and
recoverable attempts. `verification_report.json` is the final execution report;
it does not assert agreement with historical outcomes. The immutable prediction
and margin files are verified before locked sampling; missing, changed or
incomplete commitments refuse opening. Full Test B requires its complete 8/6/6
incidence and successful registered synthetic certification. No review receipt,
attestation, private-history lookup or source-hash approval is required.

Standalone locked-test and bundle commands:

```sh
.venv/bin/python -m born_ladder reproduce test-b-locked --predictions "$DATA_OUT/test-b" --output "$DATA_OUT/locked" --workers 16
.venv/bin/python -m born_ladder reproduce bundle --pipeline "$DATA_OUT/full" --output "$DATA_OUT/full/bundle"
.venv/bin/python -m born_ladder verify TB01 --profile regenerated --data "$DATA_OUT/full/bundle"
```

Locked samples replay only captured kernel/header bytes, using the original
Test B RNG domains: blocks 910036–910055, recipes 48–59, 32 paths per cell and
64 transitions. Train/validation header parity is checked before opening; no
calibration is repeated and no model is refitted. Interrupted attempts are kept
and deterministically replayed in a new directory; complete attempts are checked
and reused. A concurrent opening is refused by the output lock. Scoring reuses
the registered likelihood flooring/normalization, paired block contrasts,
200,000-draw centred bootstrap, Holm, inverted bounds and verdict predicate.
The regenerated checker also independently reconstructs available context
scores and full-incidence inference; it accepts whichever numerical outcome the
new run establishes, rather than demanding the historical negative result.

`born_regenerated_bundle_v1` stores relative component roots and numerical file
inventories. It cannot be read as an anchored historical `born_claim_bundle_v1`.
Regenerated claim IDs denote checks on **this run's** constructions and numerical
outputs. Historical-only role/executable/return evidence is explicitly not
applicable. Full population verification reruns inference from the included
unit collections, with unchanged RNG and resample counts; this adds approximately
another inference pass to the full command. Historical `verify` remains the
default and is unchanged. Formal/control IDs continue to use the existing Lean
verification commands; regenerated numerical verification does not replace them.

`verify --workers N` accepts a positive integer, default **1**; only regenerated
P12 uses it. Use `verify P12 --profile regenerated --data "$DATA_OUT/full/bundle"
--workers 48`: the final resumed full-profile invocation measured P12 at **46 min** with
**23.1 GiB (about 24.8 GB)** peak process-tree proportional set size, sampled
every **30 s**, with no swap used, versus a separate **9.0 h** serial measurement. All
**16** verifications together took **1 h 49 min**. These were on the shared
64-core/128-thread AMD Threadripper PRO 3995WX described in the README
(load average 70–180), not an unloaded-machine guarantee.
The flag reuses the evaluation stage's parallel certified rotation checks in
fresh spawned workers whose heaps do not inherit the verifier's results;
inference values and RNG streams stay unchanged. `reproduce all` passes its
worker count to verification, capped at **64**. Other claims ignore the flag.

The smoke contract is `specifications/reproduction_smoke.json`. It has a separate
end-to-end capture grid aligned with the unit construction smoke grid, reduced synthetic
population-kernel vectors/replicates, reduced Test B optimizer and control
budgets, and a smaller census. Every exact census and worked-case certificate
is checked. Formal coverage is "not applicable to this cohort"; no substitute
input modules or full-cohort theorem endpoints are built in this reduced profile.
Real sample designs and locked-score
200,000-draw inference are retained. Reduced gate failures are reported as
nonconfirmatory outcomes, never recast as a registered pass. Full-cohort
admission, population sensitivities, full synthetic certification and all
registered refits must still run under `--profile full`.

Optional read-path diagnostics:

```sh
export BORN_LADDER_READ_AUDIT="$DATA_OUT/python_reads.jsonl"
.venv/bin/python -m born_ladder reproduce all --profile smoke --output "$DATA_OUT/smoke" --workers 4
```

This diagnostic logs Python file reads and child argv/cwd in every routed CLI
process, without changing RNG or numerical computation. It is not a native
syscall trace; the Rust/C/native-library reads are outside its coverage. It is
not an acquisition or verification gate.

### Earlier reduced-profile measurement

An earlier engineering version took **22.23 min** with four requested workers,
**1.44 busy cores** on average and **0.239 GB** output. Its already provisioned
managed environments used **5.480 GB**, and the Lean dependency cache **7.148 GB**
(regular-file apparent sizes). It compiled eight reduced Lean input modules,
a route since replaced by exact all-case checks and explicit formal
NOT_APPLICABLE coverage. Installation and Rust builds were outside that timing.
These figures describe that retired reduced route, not the current smoke
profile. The current fresh-clone measurement is **10 min 23 s**, with no Lean
build, as reported above. Neither measurement is a full-scale scientific result.

<a id="complete-post-run-archive-comparison-p8"></a>

## Complete post-run archive comparison

Keep the optional historical archive out of every production command. After the
full pipeline finishes, obtain the separately supplied retained reference,
ledger and aliases. The current manuscript is shipped as `paper/main.tex`;
use it when its definitions are the intended comparison target, or supply the
specific historical manuscript revision paired with the reference/ledger.
Set explicit paths:

```sh
export REFERENCE=/path/to/reference.json
export PAPER_LEDGER=/path/to/numbers.json
export PAPER_ALIASES=/path/to/aliases.json
export PAPER_MANUSCRIPT="$PWD/paper/main.tex"  # or the required historical revision
export V25_OUTPUT="$DATA_OUT/v25"  # completed registered reproduce v25 output
```

Compare the closed outputs:

```sh
.venv/bin/python -m born_ladder reproduce compare \
  --run "$DATA_OUT/full" --archive "$REFERENCE" --output "$DATA_OUT/comparison" \
  --ledger "$PAPER_LEDGER" --aliases "$PAPER_ALIASES" --paper "$PAPER_MANUSCRIPT" \
  --v25-output "$V25_OUTPUT"
```

`--v25-output "$V25_OUTPUT"` resolves the corrective paper quantities
from a completed registered `reproduce v25` run. Without it those quantities
remain explicitly UNRESOLVED, with a pointer to that command. The two selected
RI canonical contrasts use the public v25 canonical routine on the joined full-profile
worked fixture and its attachments; they are not fresh v25 population records.
With this option, comparison checks the locked NumPy/SymPy/mpmath base before
starting expensive stages. Install `requirements.lock` in the comparison's base
environment first; the stored v25 runtime is checked against its registered root
plan, not substituted with the comparison process's runtime. The v25 reader
requires exhaustive artifact bindings, sealed source collections, the complete
registered grids, paired unit identities and registered population headers.

The completed comparison with `--v25-output` returned protocol
**PASS** and reported results reproduced **PASS**. All **18** stages passed,
with worked **PASS_WITH_DECLARED_LIMITS**: **958,438,725** values compared,
all exact, maximum absolute difference **0**. The paper stage checked **358 result quantities** at
full precision, in displayed form and against the manuscript's definitions:
**1,477 comparisons**, all exact, none unavailable. The **45** fixed program
settings and arithmetic constants are recorded as settings. Figure coordinates
and literal labels are not compared. Comparison took
**83 min**, peak RSS **21.7 GiB**, on the shared host described in the README.
Within the declared scope this establishes exact output agreement; it does not
certify the historical executable or its correspondence with the public source.
B01, B11 and B12 retain their historical-only status in regenerated verification.

The **120** historical census cases are compared directly; **2,002** added
cases, **4,004** added attachment results, **4,314** added Lean declarations and
**13** historical-case outputs without archived counterparts are independently
validated, with zero historical-match credit. Storage/process projections and
retired documentary dispositions are named. The worked stage's method limits
and unresolved generated-H boundary remain visible; no extension is claimed.
The historical-profile pipeline does not generate the corrective v25 cohort:
`reproduce v25` supplies the separate registered output consumed by comparison.

Recorded hashes of relabel-refit checkpoints and prediction seals bind their
local files before strict scientific comparison. Only each checkpoint's own
`wall_seconds` or each seal's `path` is projected. Retired manager approvals and
specification quotations are named documentary dispositions with zero scientific
match credit. The allowlist reports admitted recipes/blocks and its own committed
record-manifest hash.

On a no-op Lean build, the producing build and audit receipts remain
byte-identical only when `build_audit_pair.json` verifies both receipt hashes,
current sources, build configuration, active toolchain executables/shared
libraries, compiled artifacts (including dependencies), and the checkout's audit implementation.
The pair is published after the build and fresh audit both succeed and is
invalidated before rebuilding. An interrupted audit, missing pair or changed
binding requires a real local rebuild and audit; a no-op cannot replace them.
Numerical resume equality excludes documentation `*.example.json` hashes, including in older plans; changed
scientific specification files still block resume.

`--archive` accepts retained data through a reference manifest following
`specifications/reproduction_reference.example.json`. A wrapper manifest can
use `historical_bundle` to supply the old claim bundle and its chunked compressed
predictive artifacts, then add relocated capture indexes,
worked-case references, `lean_audit` and mandatory `lean_historical_sources`.
The latter names an independently retained historical Lean source tree, not
`lean_born` from the current checkout. Supply its 53 historical mathematical
source files and `lakefile.toml`, `lake-manifest.json`, `lean-toolchain`, matching
the 744-declaration historical audit. For example,
`"lean_historical_sources": "retained/lean-historical-sources"` resolves below
the manifest's named `retained` root. Missing selection is UNRESOLVED; substituting
the current larger source inventory fails historical-source validation.
A bare historical bundle lacking the historical source selector/audit cannot
resolve the Lean stage; add them in the wrapper manifest. The example manifest
contains paths, not reference data. A fresh clone ships
production code and the manifest schema, but not the large retained archive.
The retained data are available from the author on request (see the README's
optional archive-comparison section); request the reference manifest, retained historical Lean
tree/audit and ledger/aliases with them. Those reference and ledger/alias inputs
are supplied separately, not assumed to exist in private paper-preparation
paths in a clone. The shipped `paper/main.tex` is the current manuscript; request
an earlier manuscript only when comparison requires that historical revision. No retained values are needed for production itself.
Paths are relative to named roots in that manifest. The historical worked-case reference has the retained
`amp1`, `amp1b`, `E1`, `E2`, `E3` and `RI` certificate directories; the generated
worked-case layout is different. Supply the independent non-density certificate
as `non_trace_reference`. A `captures` entry accepts a capture directory or the
explicit retained `capture_index.json` layout. Reference data are read only;
comparison output must be separate from production and reference products.

Each invocation writes a new `attempts/attempt_NNNN/` containing `report.json`,
`report.md`, `stages.csv`, `fields.csv`, per-stage reports and JSONL files of
**every** difference, including accepted floating differences and named storage
projections. There are separate verdicts for numerical protocol execution and
historical-result reproduction. A negative scientific verdict does not by
itself mean the protocol failed. Exit zero requires successful execution plus
reproduction, or a successful reduced run explicitly marked `NOT_COMPARABLE`.
A partial run, missing reference or unavailable stored quantity is unresolved;
a scientific mismatch outside the fixed rule fails reproduction. Completed
captures can be compared while later production stages remain unfinished.

The fixed rules are readable in `specifications/reproduction_comparison.json`:
cohort membership, ordered within-record data, decisions, exact certificates,
source binary64 inputs and saved
RNG/index arrays are exact; computed floats additionally admit the plan's
absolute-plus-relative `1e-12` rule only with unchanged decisions and paper
formatting. All unit fields, both historical population objects and saved
sensitivities/draws, census/worked certificates, historical Lean preservation
and the fresh full-project audit, and Test B recipes/samples/fits/refits/
margins/predictions/
locked inference are covered. Full primary predictive bootstrap vectors must
contain 20,000 entries; the three locked index arrays must have their registered
200,000-by-20 incidence. Initial Lean provenance headers and explicitly named
process fields are reported separately. Prediction sealing paths/digests are
storage metadata; their actual numerical payloads are compared independently.
Records are matched by unit/case/record identity when serialization order can
legitimately differ; archived census indices map to current indices through
that identity. Storage paths, offsets, line/file hashes and process metadata
are named projections, while decoded inputs/results remain compared.

Lean comparison has two separate obligations. All **744 historical declarations**
must remain, with statements preserved through all **53 retained mathematical
source bodies** after the initial-header projection and with unchanged
**transitive axiom sets compared as unordered sets**; build configuration also
matches. The archived audit does not itself contain statement types or a complete
proof dependency graph. Separately, the complete fresh inventory of **5,058
declarations** must match fresh build/audit membership and current compiled
source traces, including the **4,314 additions**, with no transitive
axioms outside `Classical.choice`, `Quot.sound`, `propext`. Fresh receipt metadata
and full-cohort coverage are validated separately from historical equality.
The additions receive **zero historical matches**. A fresh full-project audit
alone cannot establish preservation of the historical source statements.

No sampling, fitting or population inference is performed by this command.
Large historical evaluation JSON objects are loaded for complete comparison;
allow substantial memory (two objects plus parsing overhead), rather than
assuming the small smoke memory footprint applies.

The full historical profile produces v8/v24, not corrective v25. Corrective-only
macros in the current manuscript cannot be certified by this historical run;
they are listed explicitly as unavailable unless an appropriate independent
regenerated field binding is supplied. Formal/source-setting documentary
quantities are separately identified; applicable formal quantities and census
counts are extracted from the generated certificates/audit when available.
The thirteen originally aborted census root-control files have no serialized
historical counterpart. They receive complete independent membership/endpoint
validation, with zero historical matches; no historical endpoint equality is
claimed. That declared absence alone does not block the census stage. Neither limitation is hidden by substituting
archive values into generated outputs.

The display comparison reads the actual literal result-macro definitions in the
supplied manuscript. Duplicate, missing or overridden definitions fail; both
ledger and regenerated outward-rounded displays must equal those definitions.
Historical approval/ruling/reference fields in the erasure control are named
as documentary-only. Its scientific NOT_COMPUTED disposition remains compared;
quantitative diagnostic counts/memberships are compared when present on both
sides, otherwise explicitly unresolved, never called documentary or matched.

Coverage distinguishes historical matches, independent validation, differences,
missing regenerated products and missing archived counterparts. Added census
cases and attachments, the thirteen historical-case root controls without
archived files, and added Lean declarations can resolve through their required
independent checks, with **zero historical matches**. Unavailable required
evidence remains UNRESOLVED; scientific contradictions fail. Worked semantic
checks and named method/boundary qualifications can resolve as
**PASS_WITH_DECLARED_LIMITS** without literal-match credit for retained methods.
The generated-H extension/classification boundary remains visible and unresolved
mathematically. Missing production products still report "Comparison incomplete:
regenerated outputs are missing." No archive value is substituted for a missing
generated value. The root-control gaps also identify any direct paper-value
reliance on absent endpoints; no selected ledger value is extracted from the
thirteen absent historical root-control files.

### Full rank-two census amendment and recovery

The owner adopted the full fixed rank-two population in
[`census_amendment.md`](../specifications/census_amendment.md): all 2,122 contexts
in the 11,177-context collection. The original `census.json` and its 3/20
registration remain unchanged. The earlier 120-case matrix-retained subset and
its certificates remain historical evidence. Availability now checks complete
evidence; it does not select a smaller population.

Census completion and the robust-threshold result have distinct fields. A
construction can complete while its maximal gap fails registered 3/20. The
full-cohort result is 2,005 passes and 117 shortfalls at 3/20, and 2,122 passes at
the retrospectively adopted 1/25. External exhaustive arithmetic encloses the
minimum maximal gap in [0.0438357, 0.0438358]. Missing inputs, invalid certificates
and incomplete construction still block completion and return nonzero.

From the repository root, use the documented non-editable base installation
and select the output root of the **existing** full run. Online managed
environment provisioning requires no private cache and happens automatically:

```sh
unset PYTHONPATH
export DATA_OUT=/path/to/existing/output-parent  # contains the existing full/ run
export BORN_LADDER_ENV_ROOT="$PWD/scratch/environments"
unset BORN_LADDER_WHEELHOUSE  # online: pinned public package indexes
mkdir -p "$PWD/scratch/recovery-tmp"
export TMPDIR="$PWD/scratch/recovery-tmp"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m born_ladder reproduce all \
  --profile full --workers 1 --output "$DATA_OUT/full"
```

For an offline recovery, set `BORN_LADDER_WHEELHOUSE` to **your own** complete
wheel directories matching the public stage locks (colon-separated if needed),
and pre-provision the pinned Rust/Cargo and Lean dependencies described above.
No author-specific repository-local environment or wheel cache is distributed
or required. Keep the existing run root and its immutable source
captures readable; cache provisioning is separate from redoing scientific stages.

`reproduce all` invokes the census with `--apply-amendment`. Earlier runs and
units use their existing checked resume paths. The census hash-checks every
recoverable attempt and exact completion gate, then appends corrected
completion dispositions, a new summary and a seal; it preserves the old plan,
attempts, registered robust outcomes and failed summary. No missing-input or
invalid-certificate failure is reclassified. The amendment has its own plan
receipt, and only adapter storage locations may differ in a copied census.

To restart only the census and its dependent numerical evidence before running
the already available renderer/build/audit, use these stage commands:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m born_ladder reproduce census \
  --units "$DATA_OUT/full/units/cross-term" \
  --runs "$DATA_OUT/full/runs/cross-term" \
  --output "$DATA_OUT/full/census" --workers 1 --apply-amendment
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m born_ladder reproduce census-attachments \
  --census "$DATA_OUT/full/census" \
  --units "$DATA_OUT/full/units/cross-term" \
  --output "$DATA_OUT/full/attachments"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m born_ladder reproduce verify-census \
  --census "$DATA_OUT/full/census" \
  --output "$DATA_OUT/full/census_external_verification.json"
```

These commands use the existing `$DATA_OUT/full` run root and read its completed
runs/units. `verify-census` is numerical-only: its legacy
`formal_certification: PENDING_SEPARATE_LEAN_PACKET` field says that this command
has not performed a Lean audit; it does **not** mean the renderer or proofs
are missing at HEAD. The full-cohort renderer, 266 shards, FullInputs,
FullWitness and AuditFull are already integrated. Run them explicitly:

```sh
.venv/bin/python -m born_ladder reproduce lean-inputs \
  --census "$DATA_OUT/full/census" --worked-cases "$DATA_OUT/full/worked" \
  --output "$DATA_OUT/full/lean" --lean-root lean_born
make lean LEAN_ROOT="$DATA_OUT/full/lean"
make lean-audit LEAN_ROOT="$DATA_OUT/full/lean"
```

These require the completed worked-case outputs. The same renderer/build/audit
steps are available automatically by resuming `reproduce all` above, which also
records pipeline coverage and resumes remaining stages. For the fixed full
cohort, formal verification refuses NOT_APPLICABLE coverage. The renderer and
proofs are available at HEAD; completed runs/units need not be redone.

Existing `CONTEXT.json`, `structural_completion_certificate.json` (including
both indices in `strictness.pair`), `integer_frame.json`, and the v1 registered
`maximal_gap_witness.json` stay in their current formats. New supplemental
`atom_classes.json` uses `born_census_atom_classes_v1`: it records constant-block
classes, traces, singleton size, and exact nonzero/nonprojectivity checks.
Summary `robust_bound_outcomes.json` uses `born_census_bound_outcomes_v1`, retaining
the registered and amended verdict for every maximal-gap pair. Attachments
separately record `completion_status` and `original_implementation_status`;
`structural_overall_status` describes completion. The extracted witness dictionary
adds `i` alongside `j`, enabling the renderer to supply I(c) and J(c).


### Full-cohort registry inputs and regenerated verification

P03, P10, P11, P13, B08, B09, B10 and B13 require the full 2,122-case
census. The historical `$BORN_DATA_BUNDLE` cannot certify these rows. A fresh
clone needs the pinned Python stage environments, Rust public export routines,
and the pinned Lean toolchain/dependencies. Run `reproduce all --profile full`
to generate the source records, census, attachments, Lean project, build/audit
receipts and regenerated bundle. Verification uses that bundle's `lean` root,
not a separately built checkout. Completed stages resume under the same output
root; earlier runs and units need not be repeated.

```sh
.venv/bin/python -m born_ladder verify P13 --profile regenerated --data "$DATA_OUT/full/bundle" \
  --certificate-output "$DATA_OUT/P13_receipt.json"
```

As an alternative to the completed regenerated bundle, a full census and its
retained source records can be checked directly without Test B or the bundle:

```sh
.venv/bin/python -m born_ladder verify P13 --data "$DATA_OUT/full" \
  --lean-root "$DATA_OUT/full/lean" --certificate-output "$DATA_OUT/P13_receipt.json"
```

This standalone directory lane needs its explicitly supplied Lean project built
first. P11 additionally needs the sibling attachments. A census-component
regenerated bundle can omit unrelated Test B/evaluation components, but must
include `census`, `cross_term_units`, `lean`, and (for P11) `attachments`, each
with file commitments. Its Lean root must include the rendered input manifest,
full shards, `formal_coverage.json`, build and fresh audit receipts, and current
compiled modules/dependencies. Verification re-renders the census inputs and
rechecks kernel evidence read-only; neither a stale receipt nor a different
rendered project is accepted. An explicit `--lean-root` cannot override this
bundle binding.

All eight IDs check source joins and the complete exact frame object (w, s, G,
P) using typed canonical rational values. The common literal/witness binding
is narrower than complete numerical-certificate validation: P03 runs the latter
and public map replay. Other IDs run their own documented checks. Native
symbolic exception truth and archive/execution identity remain external.

`reproduce all` runs every named claim's checker before recording it in a
`VERIFIED` group receipt. Smoke groups instead record
`REDUCED_NONCONFIRMATORY`, list reduced check IDs, and have no verified full
claim IDs. Reduced bundles cannot certify these full-cohort claims; regenerated
verification can perform explicitly nonconfirmatory reduced checks.
P13's saved receipt includes all 2,122 exact maximal pairs, their unit identities,
three-map labels and exact readouts/gaps, plus its axiom audit.


## Detailed grids, stage commands and retained evidence

These standalone commands use their own output layouts. They are optional
diagnostics; `make replicate` below produces all paper-number inputs without an
archive. Historical verification commands in this section still require the
separately supplied retained evidence.

### Standalone runner grids

Build with `make rust`, then launch a declared grid through the installed package.
These standalone examples populate `DATA_OUT/runs` and `DATA_OUT/units`; the
one-command full pipeline has its own `DATA_OUT/full/pipeline.json` layout:

```sh
export DATA_OUT="$PWD/scratch/reproduction"
.venv/bin/python -m born_ladder reproduce runs --grid smoke --output "$DATA_OUT/runs/smoke" --workers 4
.venv/bin/python -m born_ladder reproduce runs --grid g2a --output "$DATA_OUT/runs/g2a" --workers 8
.venv/bin/python -m born_ladder reproduce runs --grid g2c --output "$DATA_OUT/runs/g2c" --workers 8
.venv/bin/python -m born_ladder reproduce runs --grid test-b --output "$DATA_OUT/runs/test-b" --workers 8
.venv/bin/python -m born_ladder reproduce runs --grid worked-cases --output "$DATA_OUT/runs/worked" --workers 2
```

`--output` is required: use an external directory or a Git-ignored directory
such as `scratch/new_data/`. The launcher requires GNU `/usr/bin/time` for
resource accounting and pins numerical-library threads to one per process.
Repeating a command resumes its grid: completed attempts are hash-checked and
skipped; incomplete or failed attempts receive new directories. To inspect a
grid without launching it, add `--plan`. `--only <invocation-id>` selects a
registered invocation for diagnosis without redefining its parameters.

| Grid | Specification and invocations |
|---|---|
| `g2a` | v8 competitor campaign: EXP-112, all 69 configurations including the empty control, seeds 810001–810020; 1,380 invocations |
| `g2c` | v21 acquisition campaign: the 69 EXP-112 configurations and EXP-102–107 with no configuration filter, seeds 840001–840020; 1,500 invocations |
| `test-b` | That 75-invocation experiment/configuration grid, using the Test B contract's kernel seed 910000 |
| `worked-cases` | Selected worked case A13_A11/840007 and original worked case loo_A25/910000 |
| `smoke` | Both worked cases and an empty-control invocation; unchanged scale and horizon |
| `benchmark` | A declared throughput subset: 26 systematic configurations and all six named families; its sampling weights are not those of an evaluation population |

All grids are read from [specifications/runs.json](../specifications/runs.json)
and its registered-version references; the runtime has no second seed or
configuration schedule. All use scale 32 and the runner's unchanged 64,000-step
horizon. Each named-family invocation executes its internal configurations.
Makefile alternatives are `make reproduce-g2a OUTPUT=... WORKERS=...`,
`reproduce-g2c`, `reproduce-test-b`, `reproduce-worked-cases` and
`reproduce-smoke`; `make reproduce-runs GRID=... OUTPUT=... WORKERS=...`
also accepts the benchmark grid.

Each output root contains `runset.json` and an append-only `manifest.jsonl`.
Every attempt retains runner stdout/stderr, final-matrix/map header sidecars,
CPU/wall-time and peak-memory accounting, and the full discovery paths already
sampled by the runner. Supplemental capture also keeps final matrices when a
legacy export is suppressed. Legacy guard outcomes are recorded separately:
extra capture must not redefine census availability. Full paths are copied
without extra RNG calls or dispatch changes; they are distinct from Test B's
later training, validation and locked-test samples. `--capture off` disables
only this supplemental capture. See [reproduction](reproduction.md) for
schemas, resume behavior and optional historical comparisons.

### Standalone construction and verification

| Data component | Public code and remaining inputs or gaps |
|---|---|
| Census construction and numerical certificates | `.venv/bin/python -m born_ladder reproduce census --units "$DATA_OUT/units/g2c" --runs "$DATA_OUT/runs/g2c" --output "$DATA_OUT/census" --workers 8`. Uses closed unit/structural manifests and captures only; original implementation diagnostics and completed certificates are separate. Performance attachments are a separate stage; worked-case certificates and complete Lean rendering are available below. |
| Competitor and cross-term unit construction | `.venv/bin/python -m born_ladder reproduce units --grid competitor --runs "$DATA_OUT/runs/g2a" --output "$DATA_OUT/units/g2a" --workers 32` and the same command with `--grid cross-term --runs "$DATA_OUT/runs/g2c" --output "$DATA_OUT/units/g2c"`. The public coordinator constructs paired raw/package units, all predictor/competitor losses, structural joins, registered controls, eligibility, planned exclusions and nondegeneracy/tie flags from run captures and `specifications/`. Append-only attempts and closed collections provide the census's structural inputs. It reads no archived unit or population result. Population inference is a separate public stage below; `verify P12` continues to replay archived laws/losses and hash-bind archived population statistics. |
| Worked-case certificates | `.venv/bin/python -m born_ladder reproduce worked-cases --runs "$DATA_OUT/runs/worked" --output "$DATA_OUT/worked-certificates"`. Reads the two successful captures and `specifications/worked_cases.json`; produces original-case K/K² pairs, the ensemble two-read certificate, all finite-family words/events and its non-density witness, the order witness, and the selected-case exact frame/strictness/six-state certificates. No archive or performance attachment is a construction input. |
| Full-cohort and worked Lean inputs | `.venv/bin/python -m born_ladder reproduce lean-inputs --census "$DATA_OUT/census" --worked-cases "$DATA_OUT/worked-certificates" --output "$DATA_OUT/lean-rendered"`, then `make lean LEAN_ROOT="$DATA_OUT/lean-rendered"` and `make lean-audit LEAN_ROOT="$DATA_OUT/lean-rendered"`. Checks every case's numerical certificate equations. Matching registered ordered inputs render the 266 full-cohort shards, full witness/audit modules, RI and B04–B07 modules into an isolated public Lean project; other cohorts report formal coverage as not applicable, without trimming or building substitute proof inputs. Run the build/audit only when `formal_coverage.json` reports `APPLICABLE`. The original Lean source files stay unchanged; an existing local Lake cache is reused when available. |
| Test B preparations, calibration and paths | `reproduce test-b --runs ROOT --output ROOT --workers N` reads the captured kernel grid, enumerates the 60 recipes, recomputes the reading-interval census and runs the synthetic certification chain before sampling independent calibration and train/validation paths directly from the captured matrices with the Rust sampler. |
| Test B fits and committed predictions | The same command fits every family and selector, the five outer folds and margins, the optimized diagonal and order rivals, then makes all 22 literal relabel refits per context/model dimension and the training-only audit. It commits predictions and stops before real locked-test sampling. `verify TB01` stays score-only; new locked sampling/scoring uses `reproduce test-b-locked --predictions ROOT --output ROOT --workers N`, which refuses uncommitted predictions or margins. |
| Verification bundle | The hash-anchored `born_claim_bundle_v1` manifest and its data are supplied separately. `reproduce bundle --pipeline ROOT --output ROOT` assembles the separate regenerated profile; the one-command pipeline does this automatically. `src/born_ladder/evidence_anchor.json` accepts the retained evidence contract; a newly generated manifest cannot substitute new results. Root locations can be changed to relocate the same bytes, as described in [reproduction](reproduction.md). |

The unit stage reproduces both complete retained unit streams and the cross-term
control stream byte for byte under the recorded predictive stack: CPython 3.12.3,
NumPy 2.5.2 with bundled OpenBLAS 0.3.34.0.0, and one numerical thread per process.
The default NumPy 2.4.4 verification/census environment selects different valid
SVD bases and changes basis-dependent diagonal predictions. The CLI automatically provisions and routes to the correct
hash-locked stage environment; see the
[unit-stage environment and comparison notes](reproduction.md#predictive-unit-construction-and-structural-collection).
Population statistics can now be reproduced from complete closed unit collections using the commands below.

Construct the structural census directly from closed unit collections and run
captures, without reviewed certificates, performance attachments or proof scratch
notes:

```sh
.venv/bin/python -m born_ladder reproduce census --units "$DATA_OUT/units/g2c" --runs "$DATA_OUT/runs/g2c" --output "$DATA_OUT/census" --workers 8
make reproduce-census UNITS="$DATA_OUT/units/g2c" RUNS="$DATA_OUT/runs/g2c" OUTPUT="$DATA_OUT/census" WORKERS=8
```

The command inventories every paired context, applies the registered availability
predicate and complete-key order, then computes exact frames, both point-witness
rules, atom classes and correspondence certificates. Original extra-coordinate
and symbolic implementation checks have their own output; completion does not
rename their failures. It resumes completed, hash-checked cases. The available
count is reported, not assumed to be the historical count: new full-matrix
captures can make additional rank-two contexts available. Reconstructing the
earlier selection order from retained captures additionally uses a hash-checked
logical-source-name correspondence from their actual acquisition manifest, as
explained in [reproduction](reproduction.md#census-structural-construction).
Lean input rendering/auditing remains downstream. Performance attachments are produced after the structural seal using the command below.

Run historical population inference and attach the census performance records:

```sh
.venv/bin/python -m born_ladder reproduce evaluation --evaluation competitor --units "$DATA_OUT/units/g2a" --output "$DATA_OUT/evaluation/g2a"
.venv/bin/python -m born_ladder reproduce evaluation --evaluation cross-term --units "$DATA_OUT/units/g2c" --output "$DATA_OUT/evaluation/g2c" --workers 32
.venv/bin/python -m born_ladder reproduce census-attachments --census "$DATA_OUT/census" --units "$DATA_OUT/units/g2c" --output "$DATA_OUT/census-performance"
```

These commands consume only earlier-stage outputs and public specifications.
They retain the full registered resampling budgets, RNG domains, sensitivities
and verdicts, and automatically check the computing environment. Attachments
copy recorded losses and compute exact-rational descriptive quantiles after
checking the structural commitment; they do not rescore or filter structural
failures. See [the population evaluation contract](reproduction.md#population-inference-and-census-attachments)
for append-only/resume behavior, serviceability sign and the historical sign-tail
arithmetic. Historical SVD comparators remain historical; the corrective v25
evaluation is not run by these commands.

The corrective v25 evaluation runs captures, unit construction and inference
through one resumable command after its specification/code commit:

```sh
.venv/bin/python -m born_ladder reproduce v25 --output "$DATA_OUT/v25" --workers 16
# Synthetic end-to-end check, without registered acquisition:
.venv/bin/python -m born_ladder reproduce v25 --output "$DATA_OUT/v25-synthetic" --workers 4 --synthetic
```

It writes verdict tables for both evaluations. Automatic routing uses the
pinned versions and one-thread backend; there are no separate process freeze
gates. See [reproduction instructions](reproduction.md#corrective-v25-evaluation)
and [runtime instructions](../specifications/environments/README_V25.md).

Produce Test B through its pre-test prediction commitment:

```sh
make rust rust-test-b
.venv/bin/python -m born_ladder reproduce test-b --runs "$DATA_OUT/runs/test-b" --output "$DATA_OUT/test_b" --workers 16
# Stage-by-stage, same inputs/root/options: --stage census|certify|sample|fit|commit
```

Automatic routing provisions **Torch 2.13.0+cpu**, with no CUDA/NVIDIA/Triton
dependencies, and the pinned NumPy/SciPy fitting stack from
[the hashed Test B environment lock](../specifications/environments/test_b_fitting.lock).
Fitting workers start fresh with `spawn`, one OpenMP/Torch thread and a runtime
check in each worker; they do not inherit or resize a running native pool.
No source receipts, attestations or extra scans are required. Numeric inputs and
completed checkpoints are checked on resume; interrupted attempts are preserved
and redone. The independent synthetic gate must pass before real train/validation
sampling. An explicitly reduced `--smoke` run cannot certify the registered test.
See [the Test B instructions](reproduction.md#test-b-production-through-prediction-commitment)
for synthetic conformance, subsets, offline environments and the locked-test boundary.

With the full-cohort bundle/stage outputs for P03, and the retained bundle
plus P12 historical-input directory for historical P12/TB01 verification:

```sh
export BORN_FULL_DATA="$DATA_OUT/full/bundle"  # regenerated bundle directory; or "$DATA_OUT/full"
export BORN_LADDER_DATA=/path/to/historical/bundle.json
.venv/bin/python -m born_ladder verify P03 --data "$BORN_FULL_DATA"
.venv/bin/python -m born_ladder verify P12 --data "$BORN_LADDER_DATA" --historical-root /path/to/historical_inputs
.venv/bin/python -m born_ladder verify TB01 --data "$BORN_LADDER_DATA"
```

The CLI requires explicit `--data`; `BORN_LADDER_DATA` is the variable used by
the optional test lane and may be passed as above. These are verification
commands, not data-production commands. Census
selection/binding and witness checks additionally use B13, P10 and P13
([all claims](claims.md)); their Lean endpoints require the Lean build.

Measured retained sizes, using decimal GB: the bundle's 395 directly listed
files total **4.092 GB** (two cross-term files, **3.463 GB**, plus **0.629 GB**
of other files). The larger derived archive is **146.859 GB (136.773 GiB)**,
often reported by `du -sh` as `137G`. The Test B data tree is **4.636 GB
(4.317 GiB)**, reported as `4.4G`, with **0.727 GB** of certification files in
a separate tree. The bundle tally counts only its directly listed files;
archive-root checks also follow original source files. TB01's transitive receipt
lists **4.032 GB** of inputs across the Test B trees, additional to the bundle's
directly listed files. These
figures describe retained file lengths, not a disk-budget promise for new runs.

The public source is at
[github.com/ioannist/six-birds-born](https://github.com/ioannist/six-birds-born).
It can produce **new stochastic-program runs**. The retained data came from a
historical build whose correspondence with this source is not certified. The
completed comparison measured exact agreement within the declared scope
above; it does not certify that historical executable or its correspondence
with the source. The public Rust routines reproduce the raw labels, package
labels and emitted vectors exactly from the retained final matrices on the
checked census and original worked-case inputs. This record-layer replay does
not certify the historical run that produced each matrix.

Worked-case certificate and formal-input reproduction is documented in
[the worked-case and Lean-input instructions](reproduction.md#worked-case-certificates-and-full-cohort-lean-inputs).
The historical byte/scientific comparison is optional and follows construction;
new captures may produce a different cohort. All exact certificates are
checked; the current full-profile claim requires the registered ordered 2,122
cases and full-cohort formal certification. Only reduced/other cohorts receive
formal NOT_APPLICABLE; that cannot certify a full-profile claim.

The rank-two census has an owner-approved [full-cohort amendment](../specifications/census_amendment.md):
all 2,122 rank-two contexts in the fixed 11,177-context collection. The historical
120 cases remain archived evidence. Completed construction and scientific bound
outcomes are recorded separately: registered 3/20 holds in 2,005 contexts and
falls short in 117; the retrospective uniform bound is 1/25. The [reproduction
instructions](reproduction.md#full-rank-two-census-amendment-and-recovery)
give public online/offline recovery commands that reuse completed runs, units
and census constructions without private caches. The full-cohort renderer and
proofs are available at HEAD. Full-cohort Lean certification is merged and required by the full profile;
`NOT_APPLICABLE` cannot complete that requirement.


## Measured full-profile segments and storage

**Measured full-profile segments, October 2026.** The host was a shared
**64-core AMD Threadripper PRO 3995WX (128 threads)**, with other-project load
averages **70–180**. Test B and the verifications used **48 workers**; Lean used
**four jobs**. These measurements come from several invocations of `reproduce all`
on the same output root, with resumes between them. They are **not one
uninterrupted run or a measured from-scratch total**.

| Invocation / measurement | Stage | Measured wall time / resources |
|---|---|---|
| First invocation, 2026-10-08, fresh runs | Runs; units | about 37 min; 46 min |
| First invocation, 2026-10-08 | Census | about 4.7 h |
| First invocation, 2026-10-08 | Worked cases and attachments | about 2 min |
| First invocation, 2026-10-08 | Both population evaluations | about 49 min |
| Successful resumed Test B segment, 2026-10-09–11 | Segment total | about 55 h |
| Same Test B segment | Certification | 53.3 h as recorded, including 38.1 h of pseudo-campaigns; 100 campaigns at about 21–24 min each |
| Same Test B segment | Sampling; fits; seal | about 2 min; 22 min; 78 min (440 relabel refits: about 77 min) |
| Same Test B segment | Locked scoring | 116 s |
| Final resumed invocation, 2026-10-13 | Earlier-stage re-checks | about 8 min |
| Same final resumed invocation | Producing Lean build and fresh audit | forced local build, Mathlib cache kept; 347 modules, 57 min, peak about 42 GB across Lean processes; fresh axiom audit of 5,058 declarations |
| Same final resumed invocation | Seal re-check; locked; bundle | about 24 s; 1.9 min; 1.3 min |
| Same final resumed invocation | All 16 verifications | 1 h 49 min; P12: 46 min at 48 workers, peak process-tree proportional set size 23.1 GiB (about 24.8 GB), sampled every 30 s, no swap used (separate serial P12 measurement: 9.0 h) |
| Same final resumed invocation | Invocation total | 3.0 h, resuming the existing output root |
| Completed archive comparison with `--v25-output` | `reproduce compare` | 83 min; peak RSS 21.7 GiB |
| Separate registered `reproduce v25` output | 2026-10-07 19:44 to 2026-10-08 02:22 UTC | about 6.6 h including at least one resume; 49.6 GB |

Output figures below are **decimal GB, apparent size**, after the final resumed invocation. The
full output root also retains preserved earlier attempts; these figures are not
a minimum fresh-run footprint.

| Full-profile output component | GB |
|---|---:|
| Runs | 1.16 |
| Units | 5.09 |
| Census | 2.64 |
| Evaluations | 10.28 |
| Attachments | 0.55 |
| Worked cases | 0.01 |
| Test B | 3.76 |
| Locked | 1.09 |
| Lean | 3.18 (0.14 without the `.lake` build cache) |
| Bundle manifest | 0.02 |
| Total | approximately 27.8 |

A read-only cache size check on this host, 2026-10-13 (decimal GB, apparent
size), measured **1.48 GB** for the current revision's `predictive`,
`test_b_fitting` and `verification` environments, plus **0.33 GB** for
`predictive_v25`, under `~/.cache/born-ladder/environments`; older revisions'
environments are excluded. The Lean v4.28.0 toolchain used **2.72 GB** in
`~/.elan`, and Lean dependency packages **7.15 GB** in
`lean_born/.lake/packages`. Cache locations may be overridden as described above.
The separate v25 output and these caches are additional to the full-profile
output tally.
