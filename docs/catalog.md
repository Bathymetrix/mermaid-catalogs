# Output Catalog

This document defines the first-pass merged MERMAID event catalog produced by mermaid-catalogs.

The catalog combines selected values from the legacy tomocat catalog, the cfneic catalog, associated cfneic origin sidecars, and waveform metadata read with ObsPy.

## Design Principle

The main catalog is a provenance-preserving merged product, not a full re-analysis product.

The default rule is:

> Copy selected source-catalog values verbatim into the main output catalog, and perform independent verification separately.

Values should not be silently replaced merely because ObsPy, TauP, or another tool can recompute them to a slightly different decimal precision.

Independent checks should write discrepancies, rounding drift, or verification failures to diagnostics/sidecar outputs. Thresholds are TBD.

Slow or online checks, such as FDSN catalog queries or GEBCO bathymetry lookups, should not run during primary catalog generation. They belong in a separate audit workflow.

## Input Sources

### tomocat

tomocat values, including AIC-derived arrival quantities, are defined in Simon et al. (2020/2021 context), Section S4:

https://doi.org/10.1093/gji/ggab271

These values were derived from preliminary event origins, usually PDE via IRIS.

### cfneic

cfneic values are defined in Nolet et al. (2024). They are derived from finalized origins published in ISC or NEIC catalogs.

The cfneic event metadata are the default source for event origin, event location, depth, magnitude, great-circle distance, slowness, trajectory, and location-error quantities.

### cfneic origin sidecars

Catalog provenance comes from sidecar files associated with the out.cfneic products. These sidecars identify whether the finalized event origin came from ISC or NEIC and provide the corresponding event identifier.

Expected conceptual columns:

`catalog    event_id`

where catalog is one of:

`ISC`, `NEIC`

### Waveforms

ObsPy is used to read waveform files for verification and metadata extraction.

- mSEED is used for SNCL and seismogram timing verification.
- SAC is used for station metadata verification.

Primary catalog writing should proceed line by line. For each row, the relevant ObsPy waveform object should remain open/reused while multiple checks are performed.

## Output Columns

The output catalog columns are:

`sttime sncl evtime evlo evla evdp evmag stlo stla stdp ocdp phase gcarc slow tobs tres surftime snr tobserr d01 d23 dtheta v1 v2 acc b h locerr evcat evid`

A filename or waveform path may be written separately as an internal sidecar rather than leading the scientific catalog.

## Field Definitions

### sttime

Seismogram start time.

- Source: tomocat SEISMOGRAM_TIME
- Units: UTC timestamp
- Output policy: copy from tomocat
- Verification: read corresponding mSEED with ObsPy and confirm Trace.stats.starttime matches within threshold TBD

### sncl

Station-network-channel-location code.

- Source: mSEED header via ObsPy
- Output policy: read from Trace.stats
- Verification: ensure exactly one unambiguous SNCL is associated with the seismogram
- Note: use canonical station-network-location-channel representation unless a different internal convention is explicitly adopted

### evtime

Updated/final event origin time.

- Source: cfneic columns year jd hr mi s ms
- Units: UTC timestamp
- Output policy: construct timestamp from cfneic
- Note: this is event origin time, not seismogram start time

### evlo

Event longitude.

- Source: cfneic evlo
- Units: decimal degrees
- Output policy: copy verbatim from cfneic
- Future audit: optionally query ISC or NEIC/USGS FDSN services using evcat and evid

### evla

Event latitude.

- Source: cfneic evla
- Units: decimal degrees
- Output policy: copy verbatim from cfneic
- Future audit: optionally query ISC or NEIC/USGS FDSN services using evcat and evid

### evdp

Event depth.

- Source: cfneic evdp
- Units: km
- Output policy: copy verbatim from cfneic
- Note: tomocat EVDP is in meters; cfneic evdp is in kilometers

### evmag

Event magnitude.

- Source: cfneic Mw
- Units: magnitude
- Output policy: copy verbatim from cfneic
- Note: cfneic stores Mw if available, otherwise mb, otherwise Ms
- Future note: consider whether a future catalog should preserve magnitude type explicitly

### stlo

Station longitude.

- Source: tomocat STLO
- Units: decimal degrees
- Output policy: copy from tomocat
- Verification: read corresponding SAC file with ObsPy and confirm station longitude in SAC headers matches within threshold TBD

### stla

Station latitude.

- Source: tomocat STLA
- Units: decimal degrees
- Output policy: copy from tomocat
- Verification: read corresponding SAC file with ObsPy and confirm station latitude in SAC headers matches within threshold TBD

### stdp

Station depth.

- Source: cfneic stel, converted by sign
- Units: m
- Sign convention: positive downward
- Output policy:

`stdp = -stel`

- Verification: read corresponding SAC file with ObsPy and confirm SAC.stats.sac.stdp == -cfneic.stel within threshold TBD
- Note: tomocat STDP should also agree

### ocdp

Ocean depth at station location/time of recording.

- Source: cfneic ocdp
- Units: m
- Output policy: copy verbatim from cfneic
- Bathymetry model: GEBCO_2014
- Verification: none during primary generation
- Future audit: investigate GEBCO online lookup/query options
- Note: newer GEBCO versions, such as GEBCO 2019, may differ slightly; verify against the model actually used by cfneic

### phase

Seismic phase label associated with the picked arrival.

- Source: tomocat PHASE
- Output policy: copy from tomocat
- Verification: no direct verification of the label alone
- Indirect verification: use ObsPy/TauP with ak135 and compare phase, geometry, tobs, predicted travel time, and slowness
- Note: discrepancies should be flagged, not automatically corrected

### gcarc

Epicentral / great-circle distance.

- Source: cfneic gcarc
- Units: decimal degrees
- Output policy: copy verbatim from cfneic
- Verification: recompute from evlo, evla, stlo, and stla using ObsPy geodesy; compare within threshold TBD
- Note: do not update harmless small decimal-place differences in the main catalog

### slow

Ray-parameter slowness.

- Source: cfneic p
- Units: s/km
- Sign convention: upgoing phases are negative; downgoing phases are positive
- Output policy: copy verbatim from cfneic
- Verification: compute theoretical slowness using ObsPy/TauP with ak135, event-station geometry, and phase; compare within threshold TBD
- Note: output column intentionally renames cfneic p to slow

### tobs

Observed travel time relative to the updated/final event origin.

- Source: cfneic tobs
- Units: s
- Output policy: copy verbatim from cfneic

Definition:

`AIC_time_UTC = evtime + tobs`

Important: cfneic tobs is not a direct copy of tomocat OBS_TRAVTIME.

cfneic preserves the observed AIC arrival time in UTC while updating the origin time from the preliminary event solution to the finalized ISC/NEIC solution.

Given:

`old_AIC_time = tomocat EVENT_TIME + tomocat OBS_TRAVTIME`

`new_AIC_time = cfneic evtime + cfneic tobs`

then:

`old_AIC_time == new_AIC_time`

and therefore:

`new_tobs = old_event_time + old_tobs - new_event_time`

Verification: confirm the old and new AIC arrival UTC values match within threshold TBD.

### tres

Travel-time residual.

- Source: derived from tomocat and cfneic
- Units: s
- Output policy: preserve the tomocat residual definition, updated to the finalized origin

Definition:

`tres = tobs - 1D_TRAVTIME`

where:

`tobs = cfneic tobs`

`1D_TRAVTIME = tomocat 1D_TRAVTIME`

Equivalently:

`new_tres = old_tres + (new_tobs - old_tobs)`

where:

`old_tres = tomocat 1D_TRES`

`old_tobs = tomocat OBS_TRAVTIME`

`new_tobs = cfneic tobs`

Verification: independently compute a TauP/ak135 predicted travel time using finalized geometry and phase:

`tres_verify = tobs - tpred`

Compare catalog tres against tres_verify within threshold TBD.

Note: the main catalog preserves the historical tomocat residual definition rather than replacing it with a newly computed TauP residual.

### surftime

Time between recording and surfacing.

- Source: cfneic tasc
- Output policy: copy verbatim from cfneic
- Units: hr
- Definition: time between trigger and surfacing, following cfneic `tasc`
- Note: output column intentionally renames cfneic tasc to surftime

### snr

Signal-to-noise ratio.

- Source: cfneic snr
- Units: dimensionless
- Output policy: copy verbatim from cfneic
- Verification: none initially
- Future audit: possible waveform-based recomputation using the original tomocat windowing methodology

### tobserr

Observed travel-time uncertainty estimate.

- Source: cfneic stder
- Units: s
- Output policy: copy verbatim from cfneic
- Provenance: cfneic documents this as the tomocat timing error halved to a 1-sigma value
- Note: output column intentionally renames cfneic stder to tobserr

### d01

Length of previous float trajectory leg.

- Source: cfneic d01
- Units: km
- Output policy: copy verbatim from cfneic
- Definition: see Nolet et al. (2024)

### d23

Length of last/current float trajectory leg.

- Source: cfneic d23
- Units: km
- Output policy: copy verbatim from cfneic
- Definition: see Nolet et al. (2024)

### dtheta

Angle between the two trajectory legs.

- Source: cfneic angle
- Units: degrees
- Output policy: copy verbatim from cfneic
- Note: output column intentionally renames cfneic angle to dtheta
- Definition: see Nolet et al. (2024), Figure 3

### v1

Average velocity over previous trajectory leg.

- Source: cfneic v1
- Units: km/day
- Output policy: copy verbatim from cfneic
- Definition: see Nolet et al. (2024)

### v2

Average velocity over current trajectory leg.

- Source: cfneic v2
- Units: km/day
- Output policy: copy verbatim from cfneic
- Definition: see Nolet et al. (2024)

### acc

Average acceleration over the two trajectory legs.

- Source: cfneic acc
- Units: km/day^2
- Output policy: copy verbatim from cfneic
- Definition: see Nolet et al. (2024)

### b

Location error along the path due to nonzero acceleration.

- Source: cfneic b
- Units: km
- Output policy: copy verbatim from cfneic
- Definition: see Nolet et al. (2024)

### h

Location error due to deviation from a straight-line path.

- Source: cfneic h
- Units: km
- Output policy: copy verbatim from cfneic
- Definition: see Nolet et al. (2024)

### locerr

Equivalent travel-time error associated with location uncertainty.

- Source: cfneic locnerr
- Units: s
- Output policy: copy verbatim from cfneic
- Note: output column intentionally renames cfneic locnerr to locerr
- Definition: sum of dth and dtb in Nolet et al. (2024), equations 16–17

### evcat

Authoritative event catalog used for the finalized origin.

- Source: out.cfneic_[trig|int].origin sidecar
- Values: ISC or NEIC
- Output policy: copy verbatim from sidecar
- Note: this field provides provenance for event metadata copied from cfneic

### evid

Event identifier within the authoritative event catalog.

- Source: out.cfneic_[trig|int].origin sidecar
- Output policy: copy verbatim from sidecar
- Interpretation depends on evcat
- If evcat == ISC, evid is an ISC event identifier
- If evcat == NEIC, evid is a NEIC/USGS event identifier
- Future audit: use with FDSN event services to verify finalized event metadata

## Special Handling Summary

### Direct copies from cfneic

`evlo evla evdp evmag ocdp gcarc slow surftime snr tobserr d01 d23 dtheta v1 v2 acc b h locerr`

with these renames:

`slow <- p`; `surftime <- tasc`; `tobserr <- stder`; `dtheta <- angle`; `locerr <- locnerr`; `stdp <- -stel`

### Direct copies from tomocat

`sttime stlo stla phase`

### Direct reads from waveform metadata

`sncl`

### Derived/updated fields

`evtime tobs tres stdp`

### Provenance fields

`evcat evid`

## Verification / Diagnostics Philosophy

Primary catalog generation should not fail merely because a verification check finds a small discrepancy. Instead, verification results should be written to a diagnostics sidecar.

Possible diagnostic checks include:

`sttime_mseed_check stlo_sac_check stla_sac_check stdp_sac_check gcarc_obspy_check slow_taup_check phase_taup_check tobs_arrival_utc_check tres_taup_check ocdp_gebco_check evmeta_fdsn_check`

The diagnostics sidecar should include at least:

`row_index field check_name source_value computed_value difference threshold status message`

Thresholds are TBD.

## Deferred Questions

- Confirm whether `d01`/`d23` labels should be described as previous/current legs or last/previous legs consistently with cfneic and Nolet et al. (2024).
- Confirm whether sncl should be serialized as Station.Network.Location.Channel or another project-specific ordering.
- Decide whether magnitude type should be preserved in a future column.
- Decide whether filenames belong in a sidecar, an internal mapping file, or an optional final column.
- Decide exact diagnostics sidecar format.
- Investigate GEBCO lookup options, but keep them outside primary catalog generation.
- Consider a future verify-fdsn command for ISC/NEIC metadata audits.
