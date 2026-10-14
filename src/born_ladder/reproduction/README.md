# Recovered production libraries (P1)

`specification.PublicSpecification(directory, version, work_root=...)` reads
only the explicitly supplied public specification directory. Its compatibility
`attestation.json_sha256` attribute is a scientific namespace, not an attestation.

`predictive/` contains the recovered campaign and evaluation drivers. They import
the shared unit, structural, control, RNG and inference functions from
`born_ladder.snapshot`; there is one scientific implementation for production
and verification. Private signing, launcher and receipt coordination is omitted; the
public stage coordinators are supplied by subsequent packets. Spec reads of
omitted operational pointers fail instead of finding a private checkout.

`census_writers.build_inventory.rebuild_inventory` reconstructs structural joins
from explicit campaign, invocation, capture and unit inputs. It retains logical
selection identities and publishes their checked storage correspondence.
`census_writers.freeze`, `structural`, `structural_completion` and `certificates`
provide the exact scientific writing operations. Existing reviewed public
attachment/summary implementations are reused.

Test B's recovered numerical workers are in `born_ladder.record_tests`.
`estimators` and its historical P5 loader retain the selected reading interval
in the context string, including `::h8`. The old fixed-root certification driver
is replaced by `cert_v6.configure(output=..., census=...)`. No certification
runs merely by importing a module. Fits require the optional `fit` dependencies.


`runs` is the P2a public coordinator: `python -m born_ladder reproduce runs
--grid smoke --output <data-root> --workers 4`. Its grids and operational policy
come from `specifications/runs.json` and registered-version references. It keeps
per-attempt legacy stdout, sidecar headers and supplemental final-K/path captures
with append-only resource/integrity records. See `docs/reproduction.md` for the
layout and resume rules. Supplemental capture never changes legacy availability
or supplies Test B samples. Unit/structural collection is the P2b `units` coordinator. Later census,
worked-case and population coordinators remain downstream stages.


`units` reads P2a captures (or an explicit relative-path capture index), reuses
`unit_builders` adapters around the existing `snapshot` functions, and publishes
append-only per-invocation evidence plus closed canonical collections. Registered
formulas, control budgets and RNG identities are not duplicated. The optional
`unit_comparison` API/`reproduce compare-units` command reads reference records
only after outputs have been written. It never supplies a construction value.
