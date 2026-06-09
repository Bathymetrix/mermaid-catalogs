# mermaid-catalogs

Build and verify first-pass merged MERMAID event catalogs.

This repository currently focuses on the provenance-preserving catalog described
in [docs/catalog.md](docs/catalog.md). The main catalog copies selected source
values wherever possible, derives only the explicitly documented transformed
fields, and writes independent verification results to diagnostics sidecars.

## Install

Use a repo-local virtual environment, matching the other `mermaid-*` packages:

```bash
cd /Users/jdsimon/programs/mermaid-catalogs
/opt/homebrew/bin/python3.14 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

The CLI is:

```bash
.venv/bin/mermaid-catalogs --version
.venv/bin/mermaid-catalogs catalog --help
```

Activation is optional. Calling `.venv/bin/mermaid-catalogs` directly is the
most explicit and reproducible pattern.

## Build A Catalog

Real cfneic/tomocat products currently live under:

```text
/Users/jdsimon/mermaid/cfneic/outputs
```

Waveforms, when available, live recursively under:

```text
/Users/jdsimon/mermaid/processed_everyone
```

Build a catalog and optional provenance sidecar:

```bash
.venv/bin/mermaid-catalogs catalog build \
  --input-root /Users/jdsimon/mermaid/cfneic/outputs \
  --output sandbox/catalog.tsv \
  --provenance-output sandbox/catalog.provenance.tsv \
  --waveform-root /Users/jdsimon/mermaid/processed_everyone
```

The main output columns are fixed by `docs/catalog.md`. The `sncl` column is
filled from mSEED headers when `--waveform-root` is supplied.

## Verify A Catalog Build

Verification writes diagnostics only. It does not mutate or silently replace
main catalog values.

```bash
.venv/bin/mermaid-catalogs catalog verify \
  --input-root /Users/jdsimon/mermaid/cfneic/outputs \
  --diagnostics sandbox/catalog.diagnostics.tsv \
  --waveform-root /Users/jdsimon/mermaid/processed_everyone
```

Implemented diagnostics include:

- preserved AIC arrival UTC
- mSEED start time and SNCL
- SAC station longitude, latitude, and depth
- ObsPy geodesy `gcarc`
- TauP ak135 phase, signed slowness, and residual checks

Diagnostic failures are audit findings, not catalog-generation failures.

## Development

Run tests with:

```bash
.venv/bin/python -m pytest
```

The tests use tiny curated text fixtures under `tests/fixtures/catalog/`. Large
generated files, real catalog outputs, local venvs, and scratch diagnostics
belong under `sandbox/`.

## Public API

The stable contract is the CLI and documented file formats. Internal Python
module paths are not yet a stable public API and may move as MERMAID packages
are consolidated.

