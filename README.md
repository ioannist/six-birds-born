# Born calculus

Companion code for *An Audited Born Calculus on a Pre-Physical Stochastic
Substrate*, published as a preprint on Zenodo,
[doi:10.5281/zenodo.23261473](https://doi.org/10.5281/zenodo.23261473); this
repository is its code release v1.0. The code runs the stochastic program, constructs exact carriers and effects, checks formal proofs, and
reproduces the paper's numerical experiments. The manuscript is
[paper/main.tex](paper/main.tex). With TeX installed, `make paper` writes
`paper/build/main.pdf`. The current manuscript has sixty-seven pages; the
measured fresh-clone build of an earlier revision took 6 s.

You can generate the results from your own runs and check the numbers printed
in the paper, using only this checkout and your new outputs. Comparison with
the historical archive is a separate, optional step.

The **census** is the collection of 2,122 rank-two cases whose exact
constructions the paper checks. The **locked test** (Test B) tests learned
predictions on held-out records. The **corrective evaluation**, called `v25` in
the commands, separately evaluates the diagonal predictor with corrected rules.
The **smoke profile** runs the pipeline at reduced scale. A **regenerated
verification** checks evidence produced by your run rather than the author's
retained evidence.

## Three ways to replicate

| Level | What it shows | Measured time | Hardware and space | Command after setup |
|---|---|---|---|---|
| Check claims without running the experiment | Tests plus 14 no-data formal/control verifications | Tests: 5 min 33 s; fresh Lean: 59 min 24 s; audit: 2 min 42 s; verification: 16 min 20 s | About 40–42 GB peak RAM at four jobs, plus OS/other-work headroom; at least 20 GB setup disk with headroom | `make test`, `make lean LEAN_JOBS=4`, `make lean-audit`, `make verify` |
| Run at reduced scale | Exercises the pipeline; its numbers are not the paper's | Smoke: 10 min 23 s | Four workers; no Lean build; setup plus about 0.16 GB output | `.venv/bin/python -m born_ladder reproduce all --profile smoke --output "${DATA_OUT:?Source env.sh or set DATA_OUT}/smoke-all" --workers 4` |
| Replicate the paper | Full experiments, corrective evaluation, 16 regenerated verifications and a manuscript number check | About three days summed across measured resumed segments | About 40–42 GB peak RAM at four Lean jobs, plus headroom; at least 100 GB additional disk with headroom | `make replicate DATA_OUT="${DATA_OUT:?Source env.sh or set DATA_OUT}" WORKERS=48 LEAN_JOBS=4` |

These times are measurements, not runtime guarantees. The full-run figures are
resumed segments on a shared machine, not one measured from-scratch total.

## Requirements

Run all commands from the repository root. The pinned production setup needs:

- Linux x86_64 with AVX2/FMA and **CPython 3.12.3 exactly** for full replication.
  Its historical production stages refuse other patch releases.
- Git, curl, GNU make, a C linker, `python3.12-venv` and GNU `/usr/bin/time`.
- **Rust 1.93.1** via rustup, and **Lean v4.28.0** via elan. The setup below
  installs the managers if absent; Lean selects its pin from the checkout.
- Disk and RAM for the level above. Measured setup used approximately **17.9 GB**,
  including **2.6 GB** for Lean and **1.3 GB** for the Rust toolchain. Mathlib
  downloads are cached outside the checkout in `~/.cache/mathlib` (**0.4 GB**
  in that earlier tally; **1.6 GB** in the latest warm-cache test). Include
  this cache when budgeting disk. Allow at
  least **20 GB plus headroom**. Full and corrective outputs measured **27.8 GB**
  and **49.6 GB**, with caches and preserved attempts additional; the extra
  **100 GB** budget is a planning allowance, plus any optional reference archive.
- Network access for locked Python wheels, CPU fitting wheels, Cargo crates,
  Lean dependencies and Mathlib cache. No GPU is required.

On **Ubuntu 24.04**, whose `python3.12` is 3.12.3, install the system packages with:

```sh
sudo apt-get install git curl make python3.12-venv build-essential time
```

Check that `python3.12 --version` reports 3.12.3. On other Linux systems,
install Git, curl, make, a C linker and GNU time using the system package
manager. Install uv without editing shell startup files, then put it on PATH
for this session and install the pinned Python:

```sh
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$HOME/.local/bin" UV_NO_MODIFY_PATH=1 sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.12.3 --no-bin
```

This installs `uv` and `uvx` in `~/.local/bin`; `UV_NO_MODIFY_PATH=1`
prevents startup-file edits. See the [official installer options](https://docs.astral.sh/uv/reference/installer/).

By default uv also puts `python3.12` in `~/.local/bin`; `--no-bin` avoids that
side effect. Alternatively set `UV_PYTHON_BIN_DIR` to a separate executable
directory. See [uv's install options](https://docs.astral.sh/uv/reference/cli/#uv-python-install).
In the setup block below, before `.venv` exists, replace
`python3.12 -m venv .venv` with `"$(uv python find 3.12.3)" -m venv .venv`.
Managed environments now symlink the interpreter on POSIX so uv's relative
shared-library lookup works. Keep the uv interpreter's install directory:
`.venv` and every managed environment created from it link back there.
Interrupted unpublished environments are rebuilt
automatically on retry; published environments are reused unchanged. Optional paper compilation also
needs TeX Live, `quantumarticle`, BibTeX and latexmk. For offline installation,
smaller-memory configurations and download details, see
[environment and builds](docs/reproduction.md#environment-and-builds).

<a id="quick-start"></a>

## Setup

This installs a **non-editable** package. Keep PYTHONPATH unset so commands and
tests use that installation.

```sh
git clone https://github.com/ioannist/six-birds-born.git
cd six-birds-born
source env.sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps .

if ! command -v rustup >/dev/null 2>&1; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain none
fi
if ! command -v elan >/dev/null 2>&1; then
  curl --proto '=https' --tlsv1.2 -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh -s -- -y --default-toolchain none
fi
rustup toolchain install 1.93.1 --no-self-update
make rust rust-test-b
```

In **every new shell**, return to the checkout and run `source env.sh` before
continuing. It restores the tool paths and Rust pin, disables user-site packages,
unsets PYTHONPATH, and defaults output/cache directories to Git-ignored
`scratch/`. To use external storage, set `DATA_OUT` before sourcing it; explicit
output, cache and Rust-toolchain choices are preserved. Empty output/cache
values are rejected. Use the documented Rust pin when setting it yourself.

The measured install took **17 s** and the two Rust builds **46 s**. Build
`rust` before `rust-test-b` on a fresh Cargo cache; the second build is offline.
Rust compiler warnings during these builds are expected. Numerical commands provision their pinned environments automatically.

## Check claims without running the experiment

```sh
make test
make lean LEAN_JOBS=4
make lean-audit
make verify
```

The latest fresh-clone tests took **5 min 33 s** (741 passed, 12 skipped, 133
deselected), using the uv route on 2026-10-14. The earlier four-job Lean build took **59 min 24 s**; three measured
four-job builds peaked at **about 40–42 GB** across the Lean processes. The
earlier audit took **2 min 42 s** and checked **5,058 declarations**; verification
took **16 min 20 s**, with
**14/14 PASS**. [Measurement conditions and expected skips](docs/reproduction.md#system-prerequisites-and-measured-resource-budget)
are recorded in the detailed guide.

Success means `make test` exits zero, the Lean build's final JSON has
`"status": "PASS"`, `make lean-audit` prints `Lean audit: PASS, 5058 declarations`
with the allowed axioms and no forbidden axioms, and `make verify` prints PASS
for all 14 commands. Lean build progress logs display peak memory in **GiB**;
the resource figures above use decimal **GB**. These checks need no experiment
archive. Tests provision a managed verification environment from the network;
[offline wheels and expected skips](docs/reproduction.md#system-prerequisites-and-measured-resource-budget)
are documented separately. Test counts can change as tests are added.

## Run the whole pipeline at reduced scale

The reduced profile is named `smoke`:

```sh
.venv/bin/python -m born_ladder reproduce all --profile smoke \
  --output "${DATA_OUT:?Source env.sh or set DATA_OUT}/smoke-all" --workers 4
```

The measured run took **10 min 23 s**, with four workers and no Lean build.
It is silent until it prints a long JSON summary line; watch stage progress in
`$DATA_OUT/smoke-all/logs/`. At completion,
`$DATA_OUT/smoke-all/verification_report.json` has `/status: COMPLETE`,
`/checks/<group>/status: REDUCED_NONCONFIRMATORY`, and
`/formal_endpoints/status: NOT_APPLICABLE`. The locked-test result at
`/checks/test_b/claim_receipts/TB01/checks/category` is
`OUT_OF_ELIGIBLE_SCOPE`, expected at reduced scale. These are conformance
checks; **smoke cannot certify the paper's numbers or full-cohort claims**.

<a id="producing-the-data"></a>

## Replicate the paper

The full and corrective outputs total **about 77 GB plus caches**. Before
sourcing `env.sh`, point `DATA_OUT` at a large disk if the checkout's disk is
small; its default is `scratch/reproduction` inside the checkout:

```sh
export DATA_OUT=/path/on/large/disk/reproduction
source env.sh
```

The paper uses the full experiment pipeline and a separate corrective evaluation
of the diagonal predictor, named `v25` in the command line. One target runs both,
then checks the manuscript numbers. This example requests the measured
configuration on a 64-core, 128-thread machine:

```sh
make replicate DATA_OUT="${DATA_OUT:?Source env.sh or set DATA_OUT}" WORKERS=48 LEAN_JOBS=4
```

For smaller machines, start with `WORKERS=1 LEAN_JOBS=1`; increase these counts
when cores and RAM permit. This preserves the full experimental design but takes
longer. Fewer workers do not remove the memory needs of serial inference and a
single Lean process. With `LEAN_JOBS=1` the measured build took **about 3 h
8 min** with peak **about 18 GB**. The number check peaked at **about 23.2 GB (21.6 GiB)**.
Population-inference verification with 48 workers reached
**23.1 GiB (about 24.8 GB)** of process-tree proportional set size, sampled every **30 s**,
with no swap used. Allow headroom for the OS and other work. The reported timings used the stated
parallelism.

It runs, in order, `reproduce all --profile full`, `reproduce v25`, and
`reproduce paper-numbers`. The full pipeline builds and audits its own Lean
project and runs **16 claim-specific regenerated verifications**. It ends with
`$DATA_OUT/full/verification_report.json`: `/status: COMPLETE`, all 16
`/checks/<group>/claim_receipts/<ID>/status` values `VERIFIED`, and
`/formal_endpoints/status: BUILT_AND_AUDITED`. The full run regenerates 14 of the
17 evidence-dependent claims plus the no-data claims P01 and P02; B01, B11 and
B12 remain historical-only because they concern retained role records,
historical executable/source correspondence and the historical selected-case
return attachment.

The measured segments sum to **about three days** at the full run's 48-worker
configuration, dominated by locked-test certification. They were resumed
segments, **not a measured from-scratch total**. Budget several days; the
corrective-evaluation timing does not establish a 48-worker runtime. The
[segment table, stage times, storage and caches](docs/reproduction.md#measured-full-profile-segments-and-storage)
give the measurements and their conditions.

`WORKERS` controls acquisition, unit construction and locked-test work; the full
pipeline caps census construction at **8** and population evaluation/verification
at **64**. Population bootstrap arithmetic, attachments and worked-case
construction do not all scale with workers; the corrective evaluation's inference
is serial. `LEAN_JOBS` separately controls the proof build.

Rerun the same command and output root to resume; the worker count may change.
Use **one process per output root**. Producers check completed artifacts and
numerical input plans before reusing them. If reuse is refused, inspect the
stage log and restore the required inputs/environment, or use a new output root;
do not edit commitments to bypass the check. Keep preserved attempts while
resuming or verifying: journals and commitments reference their artifacts, and
there is no automatic safe-pruning command. The final command runs again,
recomputes values from the completed outputs and writes new reports comparing
them with the paper's displayed values.

For an unattended run, use tmux, or, after sourcing `env.sh`:

```sh
mkdir -p "${DATA_OUT:?Source env.sh or set DATA_OUT}"
nohup make replicate DATA_OUT="${DATA_OUT:?Source env.sh or set DATA_OUT}" WORKERS=48 LEAN_JOBS=4 \
  >"${DATA_OUT:?Source env.sh or set DATA_OUT}/replicate.log" 2>&1 &
```

Watch `$DATA_OUT/replicate.log` and `$DATA_OUT/full/logs/`. A nonzero exit calls
for inspecting the log, fixing the cause and rerunning the same command.

The last step is also available independently:

```sh
.venv/bin/python -m born_ladder reproduce paper-numbers \
  --run "${DATA_OUT:?Source env.sh or set DATA_OUT}/full" --v25-output "$DATA_OUT/v25" \
  --paper paper/main.tex --output "$DATA_OUT/paper-numbers"
```

Success prints **`358/358 paper numbers reproduced`**. Inspect
`$DATA_OUT/paper-numbers/report.md` for the comparison table. Both reports give
typeset and regenerated displays, full-precision values and match status;
`report.json` additionally records sources and aggregation. The **45** fixed
settings and arithmetic constants are checked against public source;
symbol/layout macros are classified separately. Figure coordinates and literal
labels are outside this check. No data from the author is needed.
Omitting the corrective output or finding a mismatch exits nonzero. The first
number check provisions or validates the corrective-evaluation Python environment
before long extraction; provisioning uses the network (**about 0.3 GB**);
[offline wheel provisioning](docs/reproduction.md#environment-and-builds) also covers this environment. `report.md` lists results first, then settings,
then non-numerical macros. The empty `.runs.lock` file is the persistent
concurrency lock, not missing report content.

In **117 of the 2,122 cases** the same-label gap falls short of the registered
**3/20** census bound. These shortfalls and the locked test's negative verdict
are expected results; neither makes a command fail. **1/25 is retrospective**.
Lüders tests, all densities and their mixtures, all effects, and additivity are
adopted assumptions. The checks do not show that the stochastic program supplies
these rules. Whether every additive probability assignment on the effect set
generated by the registered word-event effects comes from a density remains
unresolved; see the [declared limits](docs/limitations.md).

## Comparison with the original archive (optional)

Obtain the retained reference data, manifest, ledger/aliases and historical Lean
sources from the author at ioannis@automorph.io on request. The comparison of
record passed all **18 stages** (worked with declared limits): **958,438,725 values**, all exact,
maximum absolute difference **0**; it took **83 min**, peak RSS **21.7 GiB**.
This is exact output agreement within the declared scope; **the historical
executable and its correspondence with the public source are not certified**.
See [archive comparison](docs/reproduction.md#complete-post-run-archive-comparison)
for inputs, the `--v25-output` option and independent-validation boundaries.

## Troubleshooting and further detail

- [Reproduction](docs/reproduction.md): offline setup, environments, stage
  commands, grids, resume/recovery, map replay and detailed measurements.
- [Claims](docs/claims.md): each verification command and its evidence boundary.
- [Limitations](docs/limitations.md): what successful checks establish.
- [Full-census amendment](specifications/census_amendment.md): cohort and bound
  definitions, including the historical 120-case evidence.

## Repository layout and licenses

| Directory | Contents |
|---|---|
| `paper/` | Manuscript and bibliography |
| `src/born_ladder/` | Exact arithmetic, instruments, reproduction and verification CLI |
| `tests/born_ladder/` | Synthetic controls and optional retained-data tests |
| `specifications/` | Public protocols, environment locks and paper number map |
| `lean_born/` | Lean proofs with pinned Mathlib |
| `vendor/pica/` | Stochastic substrate and runner/sampler source |

Code, including `vendor/pica`, is [MIT-licensed](LICENSE). Documentation and the
shipped manuscript use [CC BY 4.0](LICENSE-DOCS). Third-party dependencies retain
their own licenses.
