# Verification references and non-empirical controls

The three small JSON files describe synthetic rational kernels, frames and lenses.
`../synthetic.py` constructs their matrices exactly. They exercise differing
basis coordinates with a valid projector, a very small strictness witness,
large rational trine arithmetic, and preservation of synthetic failure fields.
No observed outcome, fitted loss, archived kernel or eigenvector is copied.
Exact constants for the formal initial-record witness are embedded separately
in `lean_born/BornCalculus/RIInputs.lean`.

Historical archive tests are marked `data` and excluded from `make test`. See
[reproduction](../../../docs/reproduction.md) for the explicit local bundle
contract and [claims](../../../docs/claims.md) for verification scopes.

The complete e2e reference fixtures are retained for useful inspection and tests:

- `e2e_source_equivalence.json`: normalized source AST fingerprints and the
  comparison classification for each definition; `historical_data: false`
  identifies code identities rather than empirical measurements.
- `e2e_spec_value_reference.json`: original and published specification-value
  fingerprints with process-omission notes; `historical_data: false` identifies
  protocol identities rather than empirical measurements.
- `e2e_rng_reference.json`: the retained G2c membership draw, RNG framing audit,
  and Test B bootstrap-prefix arrays and hashes. `historical_data: true`
  identifies their historical reference origin. These are reference random
  draws, not empirical outcome measurements. Tests regenerate and compare
  the bytes directly. The historical `master_key_sha256` audit field contains
  raw key hex; a field note preserves and explains that original spelling.

The fixture-only regression guard allows 256 KiB for these complete references
(about 200 KiB currently). It is not a repository size budget, and useful
reproduction references must not be trimmed to satisfy it.
