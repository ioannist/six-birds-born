# Corrective v25 environment

Start with CPython 3.12 and the installed repository package. The public v25
command automatically provisions its own environment from
`predictive_v25.lock`; other stage environments remain separate.

```sh
python -m born_ladder reproduce v25 --output ROOT --workers N
```

Versions: NumPy 2.5.2 (bundled OpenBLAS 0.3.34.0.0), SciPy 1.18.1,
SymPy 1.14.0 and mpmath 1.3.0. Both NumPy and SciPy OpenBLAS instances use one
thread and Haswell dispatch. The computing process checks those versions and
thread settings. There are no executable/native hash or second-CPU gates.

`BORN_LADDER_ENV_ROOT` changes the managed cache. For offline installation,
`BORN_LADDER_WHEELHOUSE` supplies colon-separated wheel directories containing
the pinned packages. Interrupted installations are retried automatically.
Scientific outputs reject incompatible version/input changes on resume.

For a synthetic check without acquiring any registered seed:

```sh
python -m born_ladder reproduce v25 --output ROOT --workers N --synthetic
```
