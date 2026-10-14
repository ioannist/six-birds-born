PYTHON ?= .venv/bin/python
export PYTHONNOUSERSITE := 1
export OPENBLAS_NUM_THREADS := 1
export OMP_NUM_THREADS := 1
export MKL_NUM_THREADS := 1

.PHONY: reproduce-worked-case-certificates reproduce-lean-inputs test test-data lean lean-audit rust verify paper reproduce-runs reproduce-smoke reproduce-g2a reproduce-g2c reproduce-test-b reproduce-worked-cases reproduce-units reproduce-census reproduce-evaluation reproduce-census-attachments reproduce-v25-smoke reproduce-v25-full-synthetic reproduce-v25

LEAN_ROOT ?= lean_born
LEAN_CACHE ?= 1
LEAN_PYTHON ?= python3
# Default two jobs. Earlier fresh-clone four-job build: 59 min 24 s.
# Measured four-job peaks: about 40–42 GB (logs show GiB); allow OS/other-work headroom.
# Use fewer jobs on smaller machines; 8 GiB is not a whole-build memory budget.
LEAN_JOBS ?= 2
export LEAN_JOBS

WORKERS ?= 1
GRID ?= smoke

reproduce-runs:
	@test -n "$(OUTPUT)" || (echo 'OUTPUT=<external or Git-ignored data root> required'; exit 1)
	$(PYTHON) -m born_ladder reproduce runs --grid $(GRID) --output "$(OUTPUT)" --workers $(WORKERS)

reproduce-smoke reproduce-g2a reproduce-g2c reproduce-test-b reproduce-worked-cases:
	$(MAKE) reproduce-runs GRID=$(patsubst reproduce-%,%,$@)

paper:
	cd paper && latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build main.tex

test:
	$(PYTHON) -m pytest -q -m 'not data' tests/born_ladder

test-data:
	@test -n "$(BORN_LADDER_DATA)" || (echo 'BORN_LADDER_DATA=<local claim bundle> required'; exit 1)
	$(PYTHON) -m pytest -q -m data tests/born_ladder

.PHONY: check-lean-tools
check-lean-tools:
	@command -v elan >/dev/null 2>&1 || (echo "Missing required tool: elan. Source env.sh; install elan as described in README.md." >&2; exit 1)
	@command -v lake >/dev/null 2>&1 || (echo "Missing required tool: lake. Source env.sh; install elan as described in README.md." >&2; exit 1)

lean: check-lean-tools
	@if [ "$(LEAN_CACHE)" != "0" ] && [ ! -f "$(LEAN_ROOT)/.lake/packages/mathlib/.lake/build/lib/lean/Mathlib.olean" ]; then cd "$(LEAN_ROOT)" && (lake exe cache get || echo 'Mathlib cache unavailable; falling back to a source build.'); fi
	$(LEAN_PYTHON) lean_born/tools/audit_declarations.py build --lean-root "$(LEAN_ROOT)" --jobs "$(LEAN_JOBS)"

lean-audit: check-lean-tools
	$(LEAN_PYTHON) lean_born/tools/audit_declarations.py audit --lean-root "$(LEAN_ROOT)"

.PHONY: check-rust-tools
check-rust-tools:
	@command -v rustup >/dev/null 2>&1 || (echo "Missing required tool: rustup. Source env.sh; install rustup as described in README.md." >&2; exit 1)
	@command -v cargo >/dev/null 2>&1 || (echo "Missing required tool: cargo. Source env.sh; install rustup as described in README.md." >&2; exit 1)

rust: check-rust-tools
	cd vendor/pica && cargo build --release -p runner --bin runner

verify:
	$(PYTHON) -m born_ladder verify --all-no-data

reproduce-units:
	@test -n "$(OUTPUT)" -a -n "$(RUNS)" || (echo 'OUTPUT=<data-root> RUNS=<P2a-root> required'; exit 1)
	$(PYTHON) -m born_ladder reproduce units --grid $(or $(UNIT_GRID),smoke) --runs "$(RUNS)" --output "$(OUTPUT)" --workers $(WORKERS)

reproduce-census:
	@test -n "$(OUTPUT)" -a -n "$(RUNS)" -a -n "$(UNITS)" || (echo 'OUTPUT=<data-root> RUNS=<P2a-root> UNITS=<P2b-root> required'; exit 1)
	$(PYTHON) -m born_ladder reproduce census --units "$(UNITS)" --runs "$(RUNS)" --output "$(OUTPUT)" --workers $(WORKERS) $(if $(LOGICAL_SOURCES),--logical-sources "$(LOGICAL_SOURCES)")

reproduce-evaluation:
	@test -n "$(OUTPUT)" -a -n "$(UNITS)" -a -n "$(EVALUATION)" || (echo 'OUTPUT=<data-root> UNITS=<P2b-root> EVALUATION=<competitor|cross-term> required'; exit 1)
	$(PYTHON) -m born_ladder reproduce evaluation --evaluation "$(EVALUATION)" --units "$(UNITS)" --output "$(OUTPUT)" --workers $(WORKERS)

reproduce-census-attachments:
	@test -n "$(OUTPUT)" -a -n "$(UNITS)" -a -n "$(CENSUS)" || (echo 'OUTPUT=<data-root> UNITS=<P2b-root> CENSUS=<P3a-root> required'; exit 1)
	$(PYTHON) -m born_ladder reproduce census-attachments --census "$(CENSUS)" --units "$(UNITS)" --output "$(OUTPUT)"

reproduce-v25-smoke reproduce-v25-full-synthetic:
	@test -n "$(OUTPUT)" || (echo 'OUTPUT=<Git-ignored or external data root> required'; exit 1)
	$(PYTHON) -m born_ladder reproduce v25-smoke --output "$(OUTPUT)" $(if $(filter reproduce-v25-full-synthetic,$@),--full-contract)

reproduce-v25:
	@test -n "$(OUTPUT)" || (echo 'OUTPUT=<data root> required'; exit 1)
	$(PYTHON) -m born_ladder reproduce v25 --output "$(OUTPUT)" --workers $(WORKERS)

reproduce-worked-case-certificates:
	@test -n "$(OUTPUT)" -a -n "$(RUNS)" || (echo 'OUTPUT=<data-root> RUNS=<P2a-root> required'; exit 1)
	$(PYTHON) -m born_ladder reproduce worked-cases --runs "$(RUNS)" --output "$(OUTPUT)"

reproduce-lean-inputs:
	@test -n "$(OUTPUT)" -a -n "$(CENSUS)" -a -n "$(WORKED_CASES)" || (echo 'OUTPUT=<rendered-project> CENSUS=<P3a-root> WORKED_CASES=<P3b-root> required'; exit 1)
	$(PYTHON) -m born_ladder reproduce lean-inputs --census "$(CENSUS)" --worked-cases "$(WORKED_CASES)" --output "$(OUTPUT)" --lean-root "$(LEAN_ROOT)"


.PHONY: rust-test-b reproduce-test-b-production
rust-test-b: check-rust-tools
	cargo build --manifest-path vendor/pica/Cargo.toml --offline --release -p test_b_sampler

reproduce-test-b-production:
	@test -n "$(OUTPUT)" -a -n "$(RUNS)" || (echo 'OUTPUT=<data-root> RUNS=<P2a-Test-B-root> required'; exit 1)
	$(PYTHON) -m born_ladder reproduce test-b --runs "$(RUNS)" --output "$(OUTPUT)" --workers $(WORKERS)

# Every historical production stage; output must be explicitly supplied.
.PHONY: reproduce-all reproduce-all-smoke
reproduce-all:
	@test -n "$(OUTPUT)" || (echo 'Set OUTPUT to a data directory'; exit 1)
	$(PYTHON) -m born_ladder reproduce all --output "$(OUTPUT)" --workers $(or $(WORKERS),1)

reproduce-all-smoke:
	@test -n "$(OUTPUT)" || (echo 'Set OUTPUT to a data directory'; exit 1)
	$(PYTHON) -m born_ladder reproduce all --profile smoke --output "$(OUTPUT)" --workers $(or $(WORKERS),1)

# Archive-free replication; every producer verifies completed work on resume.
.PHONY: replicate
replicate:
	@test -n "$(DATA_OUT)" || (echo 'DATA_OUT=<external or Git-ignored data root> required'; exit 1)
	$(PYTHON) -m born_ladder reproduce all --profile full --output "$(DATA_OUT)/full" --workers "$(WORKERS)"
	$(PYTHON) -m born_ladder reproduce v25 --output "$(DATA_OUT)/v25" --workers "$(WORKERS)"
	$(PYTHON) -m born_ladder reproduce paper-numbers --run "$(DATA_OUT)/full" --v25-output "$(DATA_OUT)/v25" --output "$(DATA_OUT)/paper-numbers"
