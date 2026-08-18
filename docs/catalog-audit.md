# mermaid-catalogs scientific workflow audit

**Audit date:** 2026-08-14  
**Scope:** Deep read-only audit of the repository at `dc42a64`.

## Executive summary

**Assessment: CANNOT ESTABLISH EQUIVALENCE** (moderate confidence).

`mermaid-catalogs` is a focused, provenance-oriented merger of already-produced cfneic rows. It is not an implementation of the legacy cfneic catalog-correction workflow. The repository contains no legacy cfneic source or executable, no versioned legacy input corpus (such as `neic.csv`, `ehb.hdf`, or GeoCSV), and no legacy-versus-modern expected-output corpus. Consequently, it cannot establish that it preserves all legacy scientific behavior.

The core merger preserves picked AIC-arrival UTC and is deterministic for fixed, ordered text inputs. However, its association join can select an incorrect reviewed tomocat row when candidates are ambiguous, and its catalog rows frequently combine final event metadata with historical geometry and residual quantities that are not mutually self-consistent.

## Priority checklist

These items are intentionally unchecked. Check an item only after its decision or implementation has been independently reviewed.

- [ ] **HIGH — Protect the reviewed association.** Replace nearest-AIC-time selection with a durable reviewed-association key, or fail explicitly on an ambiguous candidate set.
- [ ] **HIGH — Decide the final-product scientific contract.** State whether the output is a historical merged record or a self-consistent final-event catalog. Do not let users infer the latter from current column names.
- [ ] **HIGH — Obtain legacy evidence before claiming equivalence.** Preserve a versioned cfneic executable/source and representative legacy input/output corpus.
- [ ] **MEDIUM — Preserve preliminary and final provenance.** Retain original association/event identifiers, critical preliminary metadata, source snapshots or checksums, and matching evidence.
- [ ] **MEDIUM — Specify source precedence.** Document and test ISC, NEIC, EHB, and no-match/conflict policy at the correction stage.
- [ ] **MEDIUM — Make waveform lookup safe.** Detect duplicate waveform basenames rather than silently choosing a filesystem-order-dependent file.
- [ ] **MEDIUM — Add focused scientific regression tests.** Prioritize the proposed tests below.
- [ ] **LOW — Decide verification exit semantics.** Keep diagnostic-only behavior if desired, but provide a clear nonzero/strict option for automated workflows.

## Evidence and verification performed

- Read all tracked source, tests, fixtures, documentation, configuration, and reachable Git history. That history contains only the catalog scaffold and its rename; it has no legacy cfneic implementation.
- Read `docs/Simon+2021.pdf` and `docs/Nolet+2024.pdf`.
- Ran `.venv/bin/python -m pytest`: **16 passed**.
- Ran the fixture CLI build and compared it byte-for-byte with `tests/fixtures/catalog/expected_catalog_trig.tsv`: **identical**.
- Ran fixture verification with ObsPy/TauP. Both rows passed AIC-UTC preservation but failed `gcarc` and TauP-residual diagnostics.
- Inspected pre-existing ignored full-catalog diagnostic artifacts under `sandbox/`. They are evidence of a prior run, not a versioned canonical fixture.

## Reconstructed workflow

```text
reviewed tomocat.txt ──┐
                       ├─ station + preserved AIC UTC join ──> catalog.tsv
out.cfneic_int/trig ───┤                                      └─ provenance.tsv (optional)
.origin sidecars ──────┘
waveforms (optional) ───── basename lookup ──> sncl + diagnostics
```

The public CLI is `mermaid-catalogs catalog build` and `mermaid-catalogs catalog verify` (`src/mermaid_catalogs/cli.py`). Default inputs are `tomocat.txt`, then existing `out.cfneic_int` and `out.cfneic_trig`, with same-name `.origin` files.

For each cfneic row, the implementation pairs cfneic and origin rows by position; restricts tomocat candidates to exact `kstnm` equality; compares preserved AIC UTC (`event_time + observed travel time`); chooses the nearest unused tomocat candidate within 0.02 s; then writes selected cfneic values, selected tomocat values, and final ISC/NEIC provenance.

This is not an independently evaluated authority hierarchy: cfneic is accepted as the final metadata authority and the origin sidecar is accepted as the final catalog authority.

## Legacy behavioral contract reconstructed from available evidence

The Simon reference documents a two-stage association workflow: automated preliminary matching queries global catalogs, predicts phase arrivals with ak135, and presents candidates; then a researcher manually reviews whether and which event/phase is associated. The reviewed association is therefore the scientific decision that must remain fixed.

Preliminary metadata came from preferred IRIS/NEIC/PDE records and was explicitly understood to be subject to later updates, particularly ISC. tomocat residual is observed AIC travel time minus predicted ak135 travel time, with historic tabular values rounded to 0.01 s.

Repository documentation infers cfneic postconditions: it replaces event metadata with final ISC/NEIC origins, adjusts `tobs` to preserve AIC UTC, and emits trajectory/localization quantities. The actual legacy policies for catalog selection, tolerance, ties, EHB handling, duplicate events, and recomputation are **unknown** from this repository.

## Modern behavioral contract

The modern code is a first-pass merger, consistent with the policy in `docs/catalog.md`: copy selected source values, derive only documented fields, and report independent discrepancies rather than silently replace values.

| Output values | Source / transformation |
| --- | --- |
| `sttime`, `stlo`, `stla`, `phase` | tomocat |
| `evtime`, `evlo`, `evla`, `evdp`, `evmag`, `ocdp`, `gcarc`, `tobs`, `snr`, trajectory/error values | cfneic |
| `stdp` | `-cfneic.stel` |
| `slow`, `surftime`, `tobserr`, `dtheta`, `locerr` | cfneic `p`, `tasc`, `stder`, `angle`, `locnerr` |
| `tres` | `cfneic.tobs - tomocat.1D_TRAVTIME` |
| `evcat`, `evid` | positional cfneic `.origin` sidecar |
| `sncl` | optional mSEED header lookup |

The parser expects exactly 39 whitespace-separated tomocat fields and 30 cfneic fields. It supports one known malformed cfneic representation where `stel` and `p` are concatenated, and permits nonnumeric trailing annotations.

## Findings

### HIGH — ambiguous join can alter a reviewed association

**Evidence:** `match_tomocat_row` in `src/mermaid_catalogs/catalog.py` matches only `kstnm` and AIC UTC. Among candidates within tolerance it chooses the smallest difference; equal differences retain the first input row. Preliminary NEIC/IRIS IDs, source filename, phase, and the explicit review decision are not keys.

**Why it matters:** Two reviewed detections from one instrument can have the same or near-identical AIC UTC. Metadata from one reviewed association can then attach to another cfneic row. The code is not querying a new earthquake, but it can substitute the reviewed record used for phase/station/prediction/provenance-facing values.

**Status:** Untested. `used_ids` ensures a tomocat row is consumed once; the pre-existing full provenance sidecar has 7,068 distinct tomocat source lines for 7,068 output rows. That does not prove correct identity under ambiguity.

### HIGH — final-row geometry and residual values are often inconsistent

**Fixture evidence:**

| Fixture row | `gcarc` disagreement | TauP residual disagreement |
| --- | ---: | ---: |
| 1 | 0.261845° | 2.879577 s |
| 2 | 0.254375° | 2.845429 s |

**Full prior-run diagnostic evidence:** 7,068 data rows.

| Check | OK | Fail | Failure range |
| --- | ---: | ---: | --- |
| `gcarc_obspy_check` | 2,093 | 4,975 | 0.010003–0.356057° |
| `tres_taup_check` | 4,592 | 2,476 | 0–12.700449 s |
| `slow_taup_check` | 6,773 | 295 | 0–0.250685 s/km |

**Cause:** `gcarc` comes from cfneic while station coordinates come from tomocat. `tres` combines final-origin `tobs` with historic tomocat 1-D predicted travel time. This is documented historical-preservation behavior, not an accidental recomputation error.

**Why it matters:** A user interpreting a row as one final event/station solution can calculate incompatible geometry and travel-time quantities. This matters for downstream location and tomography work.

**Status:** Explicitly detected by diagnostics but not asserted as a scientific contract in tests. The product decision is required: retain and label historical quantities, or separately compute final geometry/predictions/residuals.

### HIGH — equivalence to cfneic cannot be established

No legacy cfneic source, executable, test, production-equivalent fixture, or expected output is tracked or reachable in normal Git history. The repository does not ingest `neic.csv`, `ehb.hdf`, GeoCSV, or raw authoritative catalog products. It therefore cannot demonstrate event matching, source precedence, or corrections performed by cfneic.

### MEDIUM — provenance cannot reconstruct both sides of the correction

The main output preserves only final `evcat`/`evid`. It drops filename, preliminary event time/location/depth/magnitude, preliminary event IDs, IRIS ID, magnitude type, reviewer, alternate travel-time model values, and actual matching evidence. The optional sidecar stores only absolute source paths and line numbers; it does not store source records or checksums.

This is sufficient for local inspection while exact inputs remain in place, but not for durable scientific provenance or relocation of a catalog build.

### MEDIUM — authority-source coverage is restricted

`parse_origin_line` accepts only `ISC` and `NEIC`. That matches current documentation but cannot encode EHB or another authority. There is no precedence, conflict-resolution, or no-authoritative-match policy because correction is out of scope.

### MEDIUM — missing and malformed values have no defined scientific policy

Structural field count is validated, but numerical and timestamp semantics are mostly deferred. `NaN`, empty values, malformed timestamps, and invalid depth/magnitude can fail during later Decimal/datetime conversion rather than at a clear source-validation boundary. Python datetime parsing does not support ISO leap-second `:60`.

### MEDIUM — duplicate waveform basenames are silently overwritten

`iter_waveform_pairs` stores one mSEED and SAC path per basename. If multiple paths share a basename, later recursive traversal wins. The later `len(matches) > 1` check cannot detect that construction. This can change with filesystem traversal order and affects optional SNCL and diagnostics.

### LOW — verification does not fail the CLI

`catalog verify` writes diagnostics and returns zero even with failures. Documentation specifies diagnostics-only behavior, so this is intentional rather than a defect. It remains risky for unattended quality control if callers do not inspect the sidecar.

## Edge-case coverage matrix

| Edge case | Audit assessment |
| --- | --- |
| Exact authoritative counterpart | Implicitly covered by fixture |
| Slight final origin-time shift | Explicitly tested through AIC UTC preservation |
| Final location/depth shift | Copied; scientifically untested |
| Multiple plausible authoritative matches | Unknown; not implemented here |
| Multiple plausible tomocat matches | Apparently mishandled; nearest/order-dependent |
| No tomocat match | Informative error; untested |
| Missing/duplicate final IDs | No uniqueness/blank validation; untested |
| ISC/NEIC conflict | Unknown; no correction logic |
| EHB source | Unsupported by origin parser |
| Different magnitude type | Discarded |
| Missing depth/magnitude | Unknown; no semantic null policy |
| Malformed timestamps/leap seconds | Untested; leap seconds unsupported |
| Date boundaries | Only implicit datetime handling |
| Instrument naming inconsistency | Exact `kstnm` equality; otherwise no match |
| Missing GeoCSV fields/historical variants | Unsupported |
| Null/NaN values | Untested |
| Duplicate detections | One-to-one consumption exists; identity ambiguity remains |
| Multiple MERMAIDs per earthquake | Supported in principle; fixture repeats an ISC ID |
| DET vs REQ | Not interpreted; filename only supports lookup/provenance |
| Floating-point/timestamp rounding | Narrowly tested; no boundary/property tests |
| Duplicate waveform basename | Apparently mishandled |

## Test audit and proposed regression tests

The existing suite tests timestamps, mapping names, sign conversion, AIC preservation, one golden output, parser quirks, sidecar headers, and basic ObsPy integration. It validates the scaffold, not legacy equivalence. All origin fixture rows are ISC. The ObsPy test accepts either `ok` or `fail` for geometry and phase, so it does not state the intended scientific outcome.

1. **Ambiguous association rejection** — *unit*: same station and two tomocat rows within tolerance. Expected: ambiguity error, never arbitrary selection. Protects `match_tomocat_row`.
2. **Explicit reviewed identity preservation** — *integration/regression*: competing candidates plus a reviewed association key. Expected: only the reviewed record joins the final correction.
3. **Final-row geometry contract** — *regression*: corrected-event fixture. Expected: historical values are explicitly labelled, or separately recomputed final values exist.
4. **Origin source and ID policy** — *parser/integration*: NEIC, blank ID, duplicate ID, EHB, unsupported catalog labels.
5. **Tolerance boundaries and ties** — *unit*: 0.019999, 0.020000, and 0.020001 s; equal candidates; reordered input.
6. **Timestamp property tests** — *unit/property-style*: leap year, Julian-day rollover, timezone input, malformed values, microsecond-half rounding, and an explicit leap-second policy.
7. **Null and NaN handling** — *integration*: each absent scientific value must preserve a defined null or raise an actionable source error.
8. **Duplicate waveform basename** — *unit*: same basename in two directories. Expected: ambiguity, never last-file-wins.
9. **Legacy equivalence corpus** — *regression*: versioned legacy inputs, cfneic outputs, sidecars, and expected merged output.

## Determinism and reproducibility

For fixed ordered text inputs the main output is deterministic; the fixture build matched byte-for-byte. Default cfneic ordering is explicitly `out.cfneic_int` then `out.cfneic_trig`.

Risks remain: tomocat input order selects tied candidates; waveform traversal is unsorted and overwrites duplicate basenames; provenance embeds machine-specific absolute paths; diagnostic results depend on installed ObsPy/TauP versions.

## Questions not answerable from this repository

- How does legacy cfneic choose among ISC, NEIC, EHB, and conflicting results?
- What exact IDs/tolerances bind a reviewed association to a corrected event?
- Does cfneic recompute geometry, phase, predicted travel time, residual, and slowness after correction?
- Which full-catalog diagnostic discrepancies are expected source behavior rather than upstream errors?
- Is the durable product intended to be a historical merged record or a self-consistent final scientific catalog?

## Repository references

- `docs/catalog.md` — declared modern output contract.
- `docs/tomocat-cfneic_mapping.txt` — source field mapping and AIC-time rule.
- `docs/Simon+2021.pdf` — preliminary matching, human review, residual semantics, and preliminary metadata context.
- `docs/Nolet+2024.pdf` — trajectory/localization-error quantities.
- `sandbox/real_catalog*.tsv` — ignored prior-run artifacts used only for the aggregate diagnostic evidence above.
