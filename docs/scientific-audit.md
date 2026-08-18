# Independent Scientific Audit

**Scope:** read-only review of the repository state at commit `dc42a64`.

**Purpose:** assess whether `mermaid-catalogs` preserves the authoritative
manual MERMAID waveform/event association while incorporating improved event
metadata from published catalogs. This is an independent audit, not a
legacy-equivalence review.

## Overall assessment

**Not ready for a durable scientific data release.** The primary association
invariant is not enforced: finalized metadata can be attached to the wrong
manually reviewed observation. The shipped golden fixture also contains
material geometry and residual diagnostic failures which current tests permit.

The checkboxes below are intentionally unchecked. Check a finding only after
the stated acceptance criteria have been demonstrated on realistic fixtures and
the real catalog build.

## Required scientific invariants

1. The manually reviewed observation/event association is immutable.
2. The reviewed association identity and the authoritative catalog-event
   identity are distinct, durable fields.
3. A correction may update metadata for that associated event, but may never
   silently select a different event.
4. Event, station-at-recording, geometry, prediction, and residual values in a
   row must refer to explicitly identified, mutually consistent solutions.
5. The absolute picked-arrival UTC must be preserved when origin time changes.
6. Published output must contain sufficient provenance to reproduce it from
   immutable inputs.
7. Ambiguity, missing information, and conflicts must fail explicitly or be
   represented as an explicit unresolved state.

## Actual data flow

```text
tomocat reviewed row ── station + AIC UTC ──> cfneic finalized row
       │                                            │
       │                                            └── positional .origin row
       │
       ├── sttime, stlo, stla, phase, 1-D travel time
       └── raw preliminary IDs (not exposed)

cfneic row ──> final event metadata, gcarc, tobs, trajectory fields
origin row ──> evcat, evid
waveform (optional) ──> sncl
```

The primary implementation points are
[`assemble_catalog_with_provenance`][assemble],
[`match_tomocat_row`][match], and
[`build_catalog_row`][build].

[assemble]: ../src/mermaid_catalogs/catalog.py#L165
[match]: ../src/mermaid_catalogs/catalog.py#L119
[build]: ../src/mermaid_catalogs/catalog.py#L51

## Findings to check off

### CRITICAL

- [ ] **C-01 — Matching can silently change the reviewed association.**
  `match_tomocat_row` identifies a row only by matching `kstnm` and AIC UTC
  within 0.02 s. It does not compare a preliminary event ID, finalized event
  ID, filename, phase, source/event distance, or reviewer decision.
  [catalog.py:119-162](../src/mermaid_catalogs/catalog.py#L119).

  **Failure scenario:** two reviewed records from the same instrument have AIC
  picks 10 ms apart. A cfneic row lies 5 ms from both. The first input row wins
  the equal-distance tie, acquiring the other record's final metadata.

  **Acceptance criteria:** preserve a stable reviewed-association key and
  preliminary ID; reject all non-unique mappings; use an auditable mapping
  rather than a nearest-time heuristic.

- [ ] **C-02 — Golden output is geometrically inconsistent with its own
  coordinates.** Independent spherical central-angle calculations on the
  shipped expected output give:

  | Row | Output `gcarc` | Recomputed from output coordinates | Difference |
  |---|---:|---:|---:|
  | 1 | 68.624 deg | 68.885845 deg | 0.261845 deg |
  | 2 | 68.173 deg | 68.427375 deg | 0.254375 deg |

  The verifier independently reports both failures under its 0.01 deg
  threshold, but the test explicitly accepts either `ok` or `fail`.
  [expected fixture](../tests/fixtures/catalog/expected_catalog_trig.tsv),
  [geodesy check](../src/mermaid_catalogs/verify.py#L278),
  [permissive test](../tests/test_catalog.py#L274).

  **Acceptance criteria:** choose and emit a single station-at-recording
  coordinate solution, then recompute/validate `gcarc` against it to a stated
  threshold before release.

### HIGH

- [ ] **H-01 — Geometry-dependent output fields mix source solutions.** The
  output uses tomocat `stlo`/`stla`, but cfneic `gcarc`, slowness, ocean depth,
  trajectory, and location-error terms. No check establishes that those source
  positions are equivalent. [catalog.py:63-88](../src/mermaid_catalogs/catalog.py#L63).

  **Acceptance criteria:** either use the cfneic station position with cfneic
  geometry fields, or retain the tomocat position and recompute all dependent
  fields; record position source and method.

- [ ] **H-02 — The final residual is a mixed-solution legacy quantity.**
  `tres` is implemented as final cfneic `tobs` minus preliminary tomocat
  `1D_TRAVTIME`; no prediction is recomputed after final metadata correction.
  [models.py:229-232](../src/mermaid_catalogs/models.py#L229).

  The fixture's TauP diagnostics differ by 2.879577 s and 2.845429 s. This
  does not alone prove cfneic wrong—its historic prediction may include
  receiver-depth/bathymetry corrections—but proves that an unqualified final
  residual is not reproducible from the output.

  **Acceptance criteria:** either emit a recomputed final-model residual with
  pinned model/correction provenance, or rename it as a legacy residual and
  retain its model, geometry, and correction definition.

- [ ] **H-03 — Authoritative provenance is joined only by position.** Cfneic
  rows and `.origin` rows are concatenated separately and zipped after only a
  count check. A reordered same-length sidecar silently assigns a wrong ISC or
  NEIC ID. [catalog.py:235-255](../src/mermaid_catalogs/catalog.py#L235).

  **Acceptance criteria:** use a sidecar containing a stable per-row key and
  validate that the sidecar event solution agrees with cfneic time/location.

- [ ] **H-04 — Unmatched reviewed observations are silently omitted.** The
  assembler verifies only cfneic/origin count equality. It does not require all
  tomocat reviewed rows to be consumed or reported. [catalog.py:176-201](../src/mermaid_catalogs/catalog.py#L176).

  **Acceptance criteria:** make every reviewed observation end in exactly one
  of: corrected association, explicitly retained preliminary association, or
  explicit unresolved/failure record.

- [ ] **H-05 — Scientific verification is non-gating.** Build does not run
  diagnostics; verify writes failures but always returns exit code 0.
  [cli.py:98-123](../src/mermaid_catalogs/cli.py#L98).

  **Acceptance criteria:** define release-blocking checks and non-blocking
  observations; a release command must fail for unresolved critical/high
  scientific inconsistencies.

### MEDIUM

- [ ] **M-01 — Reviewed identity is not durable.** Tomocat preliminary NEIC
  and IRIS IDs remain only in `raw_fields`; they are not named in the model or
  emitted to the catalog/provenance sidecar.
  [models.py:70-90](../src/mermaid_catalogs/models.py#L70),
  [fixture](../tests/fixtures/catalog/tomocat_sample.txt).

  **Acceptance criteria:** publish both reviewed-association ID and preliminary
  source IDs, separately from authoritative `evcat`/`evid`.

- [ ] **M-02 — Time representation is underspecified.** Naive timestamps are
  silently assumed UTC, output timestamps omit `Z`/`+00:00`, cfneic calendar
  components lack range validation, and matching accepts a binary-float
  tolerance. [models.py:235-292](../src/mermaid_catalogs/models.py#L235),
  [cli.py:45](../src/mermaid_catalogs/cli.py#L45).

  **Acceptance criteria:** require/emit explicit UTC, validate all components,
  define resolution and rounding, and represent tolerance as Decimal or integer
  microseconds.

- [ ] **M-03 — No GeoCSV or positional-metadata provenance is implemented.**
  The package writes TSV only and neither reads nor records GeoCSV identity,
  interpolation method, or position-fix lineage. The literature identifies
  GeoCSV positional metadata as a relevant source for float locations.

  **Acceptance criteria:** either implement/document a versioned GeoCSV
  contract, or explicitly record the alternate position source, timestamps,
  interpolation/extrapolation method, and source hashes.

- [ ] **M-04 — Main output has insufficient durable scientific metadata.** It
  lacks schema version, null convention, units row, source checksums, CLI
  parameters, software/library versions, TauP model data version, and a build
  manifest. [models.py:10-66](../src/mermaid_catalogs/models.py#L10).

  **Acceptance criteria:** publish a versioned schema and machine-readable
  manifest alongside every release.

- [ ] **M-05 — Magnitude type is discarded.** `evmag` can represent Mw, mb,
  or Ms, but output retains only its numeric value.
  [catalog.md:122-130](catalog.md#L122).

  **Acceptance criteria:** add a magnitude-type field or explicitly mark the
  magnitude as heterogeneous and unsuitable for homogeneous use.

### LOW

- [ ] **L-01 — Parser behavior can hide source annotations and defer invalid
  numeric input.** Trailing all-nonnumeric cfneic fields are silently removed;
  most numerical values remain strings until a later calculation.
  [parsers.py:40-49](../src/mermaid_catalogs/parsers.py#L40).

  **Acceptance criteria:** preserve discarded fields in provenance or reject
  undocumented format variants; validate required numerical/scientific ranges
  at parse time.

### INFORMATIONAL

- [ ] **I-01 — Catalog precedence is not implemented in this repository.**
  There is no direct ISC/NEIC/EHB/PDE/USGS query or selection logic. Cfneic and
  its sidecars are trusted as precomputed inputs. This is acceptable only if
  their upstream provenance and selection policy are released with the inputs.

## Time, geometry, phase, and metadata notes

### Time

- Internal AIC calculations use timezone-aware `datetime` plus Decimal seconds
  rounded to microseconds. This is a sound local arithmetic choice.
- The included fixture preserves old/new AIC UTC within 1 ms, passing the
  default 20 ms diagnostic threshold.
- Date boundaries, leap days, invalid Julian days, negative travel times,
  timestamp round-trips, and explicit timezone offsets lack focused tests.

### Geometry

- No latitude, longitude, depth, finite-value, or unit-range validation exists.
- `stdp = -stel` is the only explicit unit/sign conversion.
  [models.py:223-226](../src/mermaid_catalogs/models.py#L223).
- The repository does not establish whether cfneic `gcarc` refers to an
  adjusted/non-emitted position or stale preliminary geometry. That remains an
  upstream scientific unknown, but output self-consistency is still required.

### Phases, travel times, and residuals

- Phase is copied from tomocat.
- TauP verification uses ak135, final output depth, copied `gcarc`, requested
  phase, and the first returned arrival.
  [verify.py:351-438](../src/mermaid_catalogs/verify.py#L351).
- The verification implementation does not establish that the historic cfneic
  prediction uses the same receiver-depth and bathymetry corrections as TauP.

### GeoCSV and waveform metadata

- `sncl` is only populated if the optional waveform root is supplied and there
  is exactly one trace in an unambiguous waveform pair. Otherwise it becomes
  blank. [waveforms.py:137-155](../src/mermaid_catalogs/waveforms.py#L137).
- The waveform discovery traversal is not sorted. Duplicate basename ambiguity
  is detected, but diagnostic ordering can depend on filesystem traversal.
  [waveforms.py:35-54](../src/mermaid_catalogs/waveforms.py#L35).

## Existing-test assessment

| Scientific invariant | Strongest current coverage | Status |
|---|---|---|
| Cfn timestamp construction | One ordinary Julian-day fixture | Partial |
| Preserved AIC UTC | Worked example plus source diagnostic | Good normal case |
| Correct reviewed association | None | Missing |
| Ambiguity/global matching | None | Missing |
| Reviewed-row completeness | None | Missing |
| Sidecar/event consistency | None | Missing |
| Geometry coherence | Test permits a failure | Missing |
| Final residual correctness | Test permits a failure | Missing |
| Unit/sign correctness | One `stel` sign test | Insufficient |
| UTC serialization round-trip | None | Missing |
| Provenance completeness | Column/order only | Insufficient |
| Deterministic output | One golden file | Insufficient |

## Proposed minimal tests

- [ ] **T-01 Ambiguous association:** two same-station reviewed rows within
  20 ms of one cfneic AIC time. Expect an explicit ambiguity error listing both
  reviewed IDs and filenames.
- [ ] **T-02 Greedy-assignment counterexample:** two cfneic rows and two
  reviewed rows for which a local nearest match prevents the only valid second
  match. Expect global unique mapping or failure.
- [ ] **T-03 Reviewed-row completeness:** include a reviewed row with no cfneic
  correction. Expect an explicit unresolved outcome, never omission.
- [ ] **T-04 Sidecar reorder:** swap two same-length `.origin` entries.
  Expect rejection based on stable per-row identity.
- [ ] **T-05 Geometry coherence:** fixture row 1 must either emit `68.885845`
  deg as `gcarc` for its output coordinates or use the coordinates supporting
  the claimed `68.624` deg value.
- [ ] **T-06 Residual provenance:** change final event metadata while holding
  preliminary prediction fixed. Expect a recomputed final residual or an
  explicitly labelled legacy residual with model/geometry metadata.
- [ ] **T-07 Time boundaries:** leap-day, invalid Julian day, midnight,
  negative `tobs`, explicit offset, naive timestamp, and half-microsecond
  rounding fixtures.
- [ ] **T-08 Units and signs:** km/m confusion, `stel` sign, invalid depth,
  antimeridian and polar coordinates.
- [ ] **T-09 Reproducibility:** two builds with pinned inputs, code, CLI flags,
  model/library versions, and different filesystem enumeration. Expect
  byte-identical products and identical manifests.

## Unknowns requiring upstream evidence

- The exact cfneic event-selection and ISC/NEIC precedence policy.
- Whether cfneic `gcarc` intentionally references an adjusted station position
  not emitted by this package.
- The exact prediction model and bathymetry/receiver-depth corrections behind
  cfneic/tomocat historical travel times.
- Whether another release system already treats diagnostics as release-gating.
- The exact GeoCSV sources and interpolation semantics used upstream.

## Recommended next work

1. Define and preserve a first-class reviewed-association record separate from
   authoritative event identity.
2. Replace nearest-time matching with an explicit, unique correction mapping.
3. Define a coherent final geometry solution and regenerate or qualify every
   geometry-dependent quantity.
4. Separate legacy and final-model residual products; include full model and
   correction provenance.
5. Introduce a versioned output schema and reproducibility manifest.
6. Make defined high-severity verification failures release-blocking.
7. Rebuild and independently review the real data product after the above
   invariants and tests are in place.

## Sources inspected

- Repository source, tests, fixtures, documentation, templates, and git history
  through `dc42a64`.
- `docs/Simon+2021.pdf`, especially the manual-review association workflow and
  geometry-specific residual corrections.
- `docs/Nolet+2024.pdf`, especially float positional reconstruction and GeoCSV
  positional metadata context.
