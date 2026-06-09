"""Verification hooks for MERMAID catalog diagnostics.

These checks report diagnostics only. They never mutate main catalog values.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Iterable, TextIO

from .catalog import assemble_catalog_with_provenance, default_cfneic_paths, read_cfneic_with_origins
from .models import DIAGNOSTIC_COLUMNS, CatalogRow, CfneicRow, DiagnosticRow, TomocatRow, aic_time
from .parsers import read_tomocat
from .waveforms import ObsPyWaveformCache, WaveformIndex, primary_trace

DEFAULT_STARTTIME_THRESHOLD_S = Decimal("0.01")
DEFAULT_COORD_THRESHOLD_DEG = Decimal("0.001")
DEFAULT_DEPTH_THRESHOLD_M = Decimal("0.1")
DEFAULT_GCARC_THRESHOLD_DEG = Decimal("0.01")
DEFAULT_SLOW_THRESHOLD_S_PER_KM = Decimal("0.01")
DEFAULT_TRES_TAUP_THRESHOLD_S = Decimal("1.0")


def _skipped(row_index: int, field: str, check_name: str, message: str) -> DiagnosticRow:
    return DiagnosticRow(
        row_index=row_index,
        field=field,
        check_name=check_name,
        source_value="",
        computed_value="",
        difference="",
        threshold="",
        status="skipped",
        message=message,
    )


def _diagnostic(
    row_index: int,
    field: str,
    check_name: str,
    source_value: str,
    computed_value: str,
    difference: str,
    threshold: str,
    status: str,
    message: str,
) -> DiagnosticRow:
    return DiagnosticRow(
        row_index=row_index,
        field=field,
        check_name=check_name,
        source_value=source_value,
        computed_value=computed_value,
        difference=difference,
        threshold=threshold,
        status=status,
        message=message,
    )


def _obspy_available() -> bool:
    return ObsPyWaveformCache.obspy_available()


def _numeric_check(
    row_index: int,
    field: str,
    check_name: str,
    source_value: str,
    computed_value: str | Decimal | float,
    threshold: Decimal,
    message: str,
) -> DiagnosticRow:
    try:
        source = Decimal(str(source_value))
        computed = Decimal(str(computed_value))
        difference = abs(source - computed)
    except Exception as exc:
        return _diagnostic(
            row_index,
            field,
            check_name,
            str(source_value),
            str(computed_value),
            "",
            str(threshold),
            "fail",
            f"{message}: could not compare numeric values ({exc})",
        )
    status = "ok" if difference <= threshold else "fail"
    return _diagnostic(
        row_index,
        field,
        check_name,
        str(source_value),
        str(computed_value),
        str(difference),
        str(threshold),
        status,
        message,
    )


def _stream_error(
    row_index: int,
    field: str,
    check_name: str,
    message: str,
    *,
    status: str = "skipped",
) -> DiagnosticRow:
    return _diagnostic(row_index, field, check_name, "", "", "", "", status, message)


def check_mseed_starttime(
    row_index: int,
    catalog_row: CatalogRow,
    stream: object | None,
    message: str = "",
    *,
    threshold_s: Decimal = DEFAULT_STARTTIME_THRESHOLD_S,
) -> DiagnosticRow:
    if stream is None:
        return _stream_error(
            row_index,
            "sttime",
            "sttime_mseed_check",
            message or "no mSEED stream supplied",
        )
    if not _obspy_available():
        return _skipped(row_index, "sttime", "sttime_mseed_check", "ObsPy is not installed")
    trace = primary_trace(stream)
    if trace is None:
        return _stream_error(
            row_index,
            "sttime",
            "sttime_mseed_check",
            "mSEED stream must contain exactly one trace",
            status="fail",
        )
    try:
        from obspy import UTCDateTime

        source = catalog_row.as_dict()["sttime"]
        computed_time = trace.stats.starttime
        difference = Decimal(str(abs(computed_time - UTCDateTime(source))))
    except Exception as exc:
        return _stream_error(
            row_index,
            "sttime",
            "sttime_mseed_check",
            f"failed to compare mSEED starttime: {exc}",
            status="fail",
        )
    status = "ok" if difference <= threshold_s else "fail"
    return _diagnostic(
        row_index,
        "sttime",
        "sttime_mseed_check",
        source,
        computed_time.isoformat(),
        str(difference),
        str(threshold_s),
        status,
        "mSEED Trace.stats.starttime check",
    )


def check_mseed_sncl(row_index: int, catalog_row: CatalogRow, stream: object | None, message: str = "") -> DiagnosticRow:
    if stream is None:
        return _stream_error(row_index, "sncl", "sncl_mseed_check", message or "no mSEED stream supplied")
    if not _obspy_available():
        return _skipped(row_index, "sncl", "sncl_mseed_check", "ObsPy is not installed")
    trace = primary_trace(stream)
    if trace is None:
        return _stream_error(
            row_index,
            "sncl",
            "sncl_mseed_check",
            "mSEED stream must contain exactly one trace",
            status="fail",
        )
    stats = trace.stats
    computed = f"{stats.station}.{stats.network}.{stats.location}.{stats.channel}"
    source = catalog_row.as_dict()["sncl"]
    if not source:
        return _diagnostic(
            row_index,
            "sncl",
            "sncl_mseed_check",
            source,
            computed,
            "",
            "",
            "skipped",
            "catalog sncl is blank; computed SNCL recorded for review",
        )
    status = "ok" if source == computed else "fail"
    return _diagnostic(
        row_index,
        "sncl",
        "sncl_mseed_check",
        source,
        computed,
        "",
        "",
        status,
        "mSEED SNCL check",
    )


def _sac_value(stream: object | None, field: str) -> tuple[str | None, str]:
    if stream is None:
        return None, "no SAC stream supplied"
    trace = primary_trace(stream)
    if trace is None:
        return None, "SAC stream must contain exactly one trace"
    sac = getattr(trace.stats, "sac", None)
    if sac is None:
        return None, "SAC headers are missing"
    value = sac.get(field)
    if value is None or str(value) == "-12345.0":
        return None, f"SAC header {field} is missing"
    return str(value), ""


def check_sac_station_metadata(
    row_index: int,
    catalog_row: CatalogRow,
    stream: object | None,
    message: str = "",
    *,
    coord_threshold_deg: Decimal = DEFAULT_COORD_THRESHOLD_DEG,
    depth_threshold_m: Decimal = DEFAULT_DEPTH_THRESHOLD_M,
) -> list[DiagnosticRow]:
    if stream is None:
        return [
            _stream_error(row_index, "stlo", "stlo_sac_check", message or "no SAC stream supplied"),
            _stream_error(row_index, "stla", "stla_sac_check", message or "no SAC stream supplied"),
            _stream_error(row_index, "stdp", "stdp_sac_check", message or "no SAC stream supplied"),
        ]
    if not _obspy_available():
        return [
            _skipped(row_index, "stlo", "stlo_sac_check", "ObsPy is not installed"),
            _skipped(row_index, "stla", "stla_sac_check", "ObsPy is not installed"),
            _skipped(row_index, "stdp", "stdp_sac_check", "ObsPy is not installed"),
        ]
    row = catalog_row.as_dict()
    checks = [
        ("stlo", "stlo_sac_check", "stlo", coord_threshold_deg, "SAC station longitude check"),
        ("stla", "stla_sac_check", "stla", coord_threshold_deg, "SAC station latitude check"),
        ("stdp", "stdp_sac_check", "stdp", depth_threshold_m, "SAC station depth check"),
    ]
    diagnostics: list[DiagnosticRow] = []
    for catalog_field, check_name, sac_field, threshold, check_message in checks:
        computed, error = _sac_value(stream, sac_field)
        if computed is None:
            diagnostics.append(
                _stream_error(row_index, catalog_field, check_name, error, status="fail")
            )
            continue
        diagnostics.append(
            _numeric_check(
                row_index,
                catalog_field,
                check_name,
                row[catalog_field],
                computed,
                threshold,
                check_message,
            )
        )
    return diagnostics


def check_gcarc_obspy(
    row_index: int,
    catalog_row: CatalogRow,
    *,
    threshold_deg: Decimal = DEFAULT_GCARC_THRESHOLD_DEG,
) -> DiagnosticRow:
    if not _obspy_available():
        return _skipped(row_index, "gcarc", "gcarc_obspy_check", "ObsPy is not installed")
    row = catalog_row.as_dict()
    try:
        from obspy.geodetics import locations2degrees

        computed = locations2degrees(
            float(row["evla"]),
            float(row["evlo"]),
            float(row["stla"]),
            float(row["stlo"]),
        )
    except Exception as exc:
        return _stream_error(
            row_index,
            "gcarc",
            "gcarc_obspy_check",
            f"failed to compute ObsPy gcarc: {exc}",
            status="fail",
        )
    return _numeric_check(
        row_index,
        "gcarc",
        "gcarc_obspy_check",
        row["gcarc"],
        f"{computed:.6f}",
        threshold_deg,
        "ObsPy geodesy locations2degrees check",
    )


def _arrival_slowness_s_per_km(arrival: object) -> float:
    from obspy.geodetics import degrees2kilometers

    ray_param_sec_degree = float(arrival.ray_param_sec_degree)
    slowness = ray_param_sec_degree / degrees2kilometers(1.0)
    phase = getattr(arrival, "name", "")
    sign = -1.0 if phase[:1].islower() else 1.0
    return sign * abs(slowness)


def _no_taup_arrival(row_index: int, phase: str) -> list[DiagnosticRow]:
    return [
        _stream_error(
            row_index,
            "phase",
            "phase_taup_check",
            f"TauP ak135 returned no arrival for phase {phase}",
            status="fail",
        ),
        _stream_error(
            row_index,
            "slow",
            "slow_taup_check",
            f"TauP ak135 returned no arrival for phase {phase}",
            status="fail",
        ),
        _stream_error(
            row_index,
            "tres",
            "tres_taup_check",
            f"TauP ak135 returned no arrival for phase {phase}",
            status="fail",
        ),
    ]


def check_taup_ak135(
    row_index: int,
    catalog_row: CatalogRow,
    model: object | None = None,
    *,
    slow_threshold_s_per_km: Decimal = DEFAULT_SLOW_THRESHOLD_S_PER_KM,
    tres_threshold_s: Decimal = DEFAULT_TRES_TAUP_THRESHOLD_S,
) -> list[DiagnosticRow]:
    if not _obspy_available():
        return [
            _skipped(row_index, "phase", "phase_taup_check", "ObsPy is not installed"),
            _skipped(row_index, "slow", "slow_taup_check", "ObsPy is not installed"),
            _skipped(row_index, "tres", "tres_taup_check", "ObsPy is not installed"),
        ]
    row = catalog_row.as_dict()
    phase = row["phase"]
    try:
        if model is None:
            from obspy.taup import TauPyModel

            model = TauPyModel(model="ak135")
        arrivals = model.get_travel_times(
            source_depth_in_km=float(row["evdp"]),
            distance_in_degree=float(row["gcarc"]),
            phase_list=[phase],
        )
    except Exception as exc:
        return [
            _stream_error(
                row_index,
                "phase",
                "phase_taup_check",
                f"failed to compute TauP ak135 diagnostics: {exc}",
                status="fail",
            ),
            _stream_error(
                row_index,
                "slow",
                "slow_taup_check",
                f"failed to compute TauP ak135 diagnostics: {exc}",
                status="fail",
            ),
            _stream_error(
                row_index,
                "tres",
                "tres_taup_check",
                f"failed to compute TauP ak135 diagnostics: {exc}",
                status="fail",
            ),
        ]
    if not arrivals:
        return _no_taup_arrival(row_index, phase)

    arrival = arrivals[0]
    computed_phase = arrival.name
    computed_slow = _arrival_slowness_s_per_km(arrival)
    computed_tres = float(row["tobs"]) - float(arrival.time)
    return [
        _diagnostic(
            row_index,
            "phase",
            "phase_taup_check",
            phase,
            computed_phase,
            "",
            "",
            "ok" if phase == computed_phase else "fail",
            "TauP ak135 first matching phase check",
        ),
        _numeric_check(
            row_index,
            "slow",
            "slow_taup_check",
            row["slow"],
            f"{computed_slow:.6f}",
            slow_threshold_s_per_km,
            "TauP ak135 signed slowness check",
        ),
        _numeric_check(
            row_index,
            "tres",
            "tres_taup_check",
            row["tres"],
            f"{computed_tres:.6f}",
            tres_threshold_s,
            "TauP ak135 residual check",
        ),
    ]


def check_preserved_aic_utc(
    row_index: int,
    tomocat: TomocatRow,
    cfneic: CfneicRow,
    *,
    threshold_s: Decimal = Decimal("0.02"),
) -> DiagnosticRow:
    """Confirm tomocat and cfneic preserve the same picked arrival UTC."""

    old_aic = aic_time(tomocat.event_time, tomocat.obs_travtime)
    new_aic = aic_time(cfneic.event_time, cfneic.tobs)
    difference = Decimal(str(abs((old_aic - new_aic).total_seconds())))
    status = "ok" if difference <= threshold_s else "fail"
    return DiagnosticRow(
        row_index=row_index,
        field="tobs",
        check_name="tobs_arrival_utc_check",
        source_value=old_aic.isoformat(),
        computed_value=new_aic.isoformat(),
        difference=str(difference),
        threshold=str(threshold_s),
        status=status,
        message="preserved AIC UTC check",
    )


def write_diagnostics(
    rows: Iterable[DiagnosticRow],
    output: str | Path | TextIO,
    *,
    delimiter: str = "\t",
) -> None:
    """Write diagnostic rows as a simple delimited table."""

    close = False
    if hasattr(output, "write"):
        handle = output  # type: ignore[assignment]
    else:
        handle = Path(output).open("w", encoding="utf-8", newline="")
        close = True
    try:
        handle.write(delimiter.join(DIAGNOSTIC_COLUMNS) + "\n")
        for row in rows:
            handle.write(
                delimiter.join(
                    (
                        str(row.row_index),
                        row.field,
                        row.check_name,
                        row.source_value,
                        row.computed_value,
                        row.difference,
                        row.threshold,
                        row.status,
                        row.message,
                    )
                )
                + "\n"
            )
    finally:
        if close:
            handle.close()


def verify_sources(
    *,
    input_root: str | Path,
    tomocat_path: str | Path | None = None,
    cfneic_paths: Iterable[str | Path] | None = None,
    origin_paths: Iterable[str | Path] | None = None,
    waveform_root: str | Path | None = None,
    aic_tolerance_s: float = 0.02,
    diagnostic_threshold_s: Decimal = Decimal("0.02"),
    starttime_threshold_s: Decimal = DEFAULT_STARTTIME_THRESHOLD_S,
    coord_threshold_deg: Decimal = DEFAULT_COORD_THRESHOLD_DEG,
    depth_threshold_m: Decimal = DEFAULT_DEPTH_THRESHOLD_M,
    gcarc_threshold_deg: Decimal = DEFAULT_GCARC_THRESHOLD_DEG,
    slow_threshold_s_per_km: Decimal = DEFAULT_SLOW_THRESHOLD_S_PER_KM,
    tres_taup_threshold_s: Decimal = DEFAULT_TRES_TAUP_THRESHOLD_S,
) -> list[DiagnosticRow]:
    """Run source-based scaffold diagnostics without changing catalog values."""

    root = Path(input_root)
    tomocat_rows = read_tomocat(tomocat_path if tomocat_path is not None else root / "tomocat.txt")
    chosen_cfneic_paths = list(cfneic_paths) if cfneic_paths is not None else default_cfneic_paths(root)
    cfneic_rows, origin_rows = read_cfneic_with_origins(chosen_cfneic_paths, origin_paths)
    waveform_cache = (
        ObsPyWaveformCache(WaveformIndex.from_root(waveform_root))
        if waveform_root is not None
        else None
    )
    sncl_resolver = (
        (lambda row: waveform_cache.sncl_for_filename(row.filename))
        if waveform_cache is not None and ObsPyWaveformCache.obspy_available()
        else None
    )
    catalog_rows, provenance = assemble_catalog_with_provenance(
        tomocat_rows,
        cfneic_rows,
        origin_rows,
        sncl_resolver=sncl_resolver,
        aic_tolerance_s=aic_tolerance_s,
    )

    tomocat_by_source = {(row.source_path, row.source_line): row for row in tomocat_rows}
    cfneic_by_source = {(row.source_path, row.source_line): row for row in cfneic_rows}
    taup_model = None
    taup_model_error = ""
    if _obspy_available():
        try:
            from obspy.taup import TauPyModel

            taup_model = TauPyModel(model="ak135")
        except Exception as exc:  # pragma: no cover - depends on local ObsPy install.
            taup_model_error = f"failed to initialize TauP ak135: {exc}"

    diagnostics: list[DiagnosticRow] = []
    for catalog_row, source in zip(catalog_rows, provenance):
        tomocat = tomocat_by_source[(source.tomocat_path, source.tomocat_line)]
        cfneic = cfneic_by_source[(source.cfneic_path, source.cfneic_line)]
        diagnostics.append(
            check_preserved_aic_utc(
                source.row_index,
                tomocat,
                cfneic,
                threshold_s=diagnostic_threshold_s,
            )
        )
        mseed_stream = None
        mseed_message = "no waveform root supplied"
        sac_stream = None
        sac_message = "no waveform root supplied"
        if waveform_cache is not None and ObsPyWaveformCache.obspy_available():
            _, mseed_stream, mseed_message = waveform_cache.read_mseed_for_filename(tomocat.filename)
            _, sac_stream, sac_message = waveform_cache.read_sac_for_filename(tomocat.filename)

        diagnostics.append(
            check_mseed_starttime(
                source.row_index,
                catalog_row,
                mseed_stream,
                mseed_message,
                threshold_s=starttime_threshold_s,
            )
        )
        diagnostics.append(check_mseed_sncl(source.row_index, catalog_row, mseed_stream, mseed_message))
        diagnostics.extend(
            check_sac_station_metadata(
                source.row_index,
                catalog_row,
                sac_stream,
                sac_message,
                coord_threshold_deg=coord_threshold_deg,
                depth_threshold_m=depth_threshold_m,
            )
        )
        diagnostics.append(
            check_gcarc_obspy(source.row_index, catalog_row, threshold_deg=gcarc_threshold_deg)
        )
        if taup_model_error:
            diagnostics.extend(
                [
                    _stream_error(
                        source.row_index,
                        "phase",
                        "phase_taup_check",
                        taup_model_error,
                        status="fail",
                    ),
                    _stream_error(
                        source.row_index,
                        "slow",
                        "slow_taup_check",
                        taup_model_error,
                        status="fail",
                    ),
                    _stream_error(
                        source.row_index,
                        "tres",
                        "tres_taup_check",
                        taup_model_error,
                        status="fail",
                    ),
                ]
            )
        else:
            diagnostics.extend(
                check_taup_ak135(
                    source.row_index,
                    catalog_row,
                    taup_model,
                    slow_threshold_s_per_km=slow_threshold_s_per_km,
                    tres_threshold_s=tres_taup_threshold_s,
                )
            )
    return diagnostics
