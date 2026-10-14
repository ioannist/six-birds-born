# Snapshot verification

This package verifies the archived snapshot construction using explicit inputs.
It has no sampling or campaign-launch interface. `HistoricalInputs` reads a
hash-bound evidence manifest; original source-path keys denote historical
identities, not files to load from the public checkout. Relocating a module
does not turn its current bytes into evidence of historical execution.

The unit-law and loss evaluators preserve the original arithmetic and diagonal
basis semantics. Population statistics are attached from preserved evidence.
See [claims](../../../docs/claims.md) for P12's exact scope and
[reproduction](../../../docs/reproduction.md) for its evidence contract.

Production drivers in `born_ladder.reproduction.predictive` reuse these same
scientific functions. Previously pruned capture/record writers and explicit
output helpers are restored here beside the shared validators. Historical
verification still reads original evidence through `HistoricalInputs`; current
public source bytes do not become evidence of historical execution.
