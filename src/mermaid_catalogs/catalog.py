"""First-pass merged MERMAID catalog assembly."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, TextIO

from .models import (
    CATALOG_COLUMNS,
    PROVENANCE_COLUMNS,
    CatalogRow,
    CfneicRow,
    OriginRow,
    ProvenanceRow,
    TomocatRow,
    decimal_text,
    format_utc,
    stdp_from_stel,
    updated_tres,
)
from .parsers import read_cfneic, read_origins, read_tomocat
from .waveforms import ObsPyWaveformCache, WaveformIndex


_CFNEIC_OUTPUT_RENAMES: dict[str, str] = {
    "slow": "p",
    "surftime": "tasc",
    "tobserr": "stder",
    "dtheta": "angle",
    "locerr": "locnerr",
}

_CFNEIC_SIGN_FLIP_RENAMES: dict[str, str] = {
    "stdp": "stel",
}


@dataclass(frozen=True)
class CatalogBuildError(RuntimeError):
    """Raised when source rows cannot be matched into catalog rows."""

    message: str

    def __str__(self) -> str:
        return self.message


def build_catalog_row(tomocat: TomocatRow, cfneic: CfneicRow, origin: OriginRow, sncl: str = "") -> CatalogRow:
    """Build one merged row while preserving source-catalog values where specified."""

    renamed_cfneic = {
        output: getattr(cfneic, source)
        for output, source in _CFNEIC_OUTPUT_RENAMES.items()
    }
    sign_flipped_cfneic = {
        output: decimal_text(stdp_from_stel(getattr(cfneic, source)))
        for output, source in _CFNEIC_SIGN_FLIP_RENAMES.items()
    }
    values = {
        "sttime": tomocat.seismogram_time,
        "sncl": sncl,
        "evtime": cfneic.event_time_text,
        "evlo": cfneic.evlo,
        "evla": cfneic.evla,
        "evdp": cfneic.evdp,
        "evmag": cfneic.mw,
        "stlo": tomocat.stlo,
        "stla": tomocat.stla,
        "ocdp": cfneic.ocdp,
        "phase": tomocat.phase,
        "gcarc": cfneic.gcarc,
        "tobs": cfneic.tobs,
        "tres": str(updated_tres(cfneic.tobs, tomocat.travtime_1d)),
        "snr": cfneic.snr,
        "d01": cfneic.d01,
        "d23": cfneic.d23,
        "v1": cfneic.v1,
        "v2": cfneic.v2,
        "acc": cfneic.acc,
        "b": cfneic.b,
        "h": cfneic.h,
        "evcat": origin.catalog,
        "evid": origin.event_id,
        **renamed_cfneic,
        **sign_flipped_cfneic,
    }
    return CatalogRow(values)


def build_provenance_row(
    row_index: int,
    tomocat: TomocatRow,
    cfneic: CfneicRow,
    origin: OriginRow,
) -> ProvenanceRow:
    """Build one internal source-row provenance sidecar row."""

    return ProvenanceRow(
        row_index=row_index,
        tomocat_path=tomocat.source_path,
        tomocat_line=tomocat.source_line,
        tomocat_filename=tomocat.filename,
        cfneic_path=cfneic.source_path,
        cfneic_line=cfneic.source_line,
        origin_path=origin.source_path,
        origin_line=origin.source_line,
        cfneic_row_index=cfneic.source_row_index,
        origin_row_index=origin.source_row_index,
    )


def _seconds_between(left: datetime, right: datetime) -> float:
    return abs((left - right).total_seconds())


def match_tomocat_row(
    cfneic: CfneicRow,
    candidates: list[TomocatRow],
    used_ids: set[int],
    *,
    tolerance_s: float,
) -> TomocatRow:
    """Find the unused tomocat row preserving the same station and AIC UTC."""

    best: tuple[float, TomocatRow] | None = None
    cfneic_aic = cfneic.aic_time
    for row in candidates:
        row_id = id(row)
        if row_id in used_ids:
            continue
        difference = _seconds_between(cfneic_aic, row.aic_time)
        if difference <= tolerance_s and (best is None or difference < best[0]):
            best = (difference, row)
    if best is None:
        nearest = sorted(
            (
                (_seconds_between(cfneic_aic, row.aic_time), row)
                for row in candidates
                if id(row) not in used_ids
            ),
            key=lambda item: item[0],
        )[:3]
        if nearest:
            nearest_text = "; nearest candidates: " + "; ".join(
                f"{row.filename} line={row.source_line} "
                f"aic_delta_s={difference:.3f} event_time={row.event_time} "
                f"obs_travtime={row.obs_travtime}"
                for difference, row in nearest
            )
        else:
            nearest_text = "; no unused tomocat rows for station"
        raise CatalogBuildError(
            "no tomocat row matched cfneic row "
            f"{cfneic.kstnm} {format_utc(cfneic.event_time)} tobs={cfneic.tobs} "
            f"source={cfneic.source_path}:{cfneic.source_line}"
            f"{nearest_text}"
        )
    used_ids.add(id(best[1]))
    return best[1]


def assemble_catalog_with_provenance(
    tomocat_rows: Iterable[TomocatRow],
    cfneic_rows: Iterable[CfneicRow],
    origin_rows: Iterable[OriginRow],
    *,
    sncl: str = "",
    sncl_resolver: Callable[[TomocatRow], str] | None = None,
    aic_tolerance_s: float = 0.02,
) -> tuple[list[CatalogRow], list[ProvenanceRow]]:
    """Assemble catalog rows and internal provenance by station plus AIC UTC."""

    cfneic_list = list(cfneic_rows)
    origin_list = list(origin_rows)
    if len(cfneic_list) != len(origin_list):
        raise CatalogBuildError(
            f"cfneic/origin row count mismatch: {len(cfneic_list)} cfneic rows, "
            f"{len(origin_list)} origin rows"
        )

    by_station: dict[str, list[TomocatRow]] = defaultdict(list)
    for row in tomocat_rows:
        by_station[row.kstnm].append(row)

    used_ids: set[int] = set()
    output: list[CatalogRow] = []
    provenance: list[ProvenanceRow] = []
    for row_index, (cfneic, origin) in enumerate(zip(cfneic_list, origin_list), start=1):
        tomocat = match_tomocat_row(
            cfneic,
            by_station.get(cfneic.kstnm, []),
            used_ids,
            tolerance_s=aic_tolerance_s,
        )
        row_sncl = sncl_resolver(tomocat) if sncl_resolver is not None else sncl
        output.append(build_catalog_row(tomocat, cfneic, origin, sncl=row_sncl))
        provenance.append(build_provenance_row(row_index, tomocat, cfneic, origin))
    return output, provenance


def assemble_catalog(
    tomocat_rows: Iterable[TomocatRow],
    cfneic_rows: Iterable[CfneicRow],
    origin_rows: Iterable[OriginRow],
    *,
    sncl: str = "",
    sncl_resolver: Callable[[TomocatRow], str] | None = None,
    aic_tolerance_s: float = 0.02,
) -> list[CatalogRow]:
    """Assemble catalog rows by matching station and preserved AIC arrival UTC."""

    rows, _ = assemble_catalog_with_provenance(
        tomocat_rows,
        cfneic_rows,
        origin_rows,
        sncl=sncl,
        sncl_resolver=sncl_resolver,
        aic_tolerance_s=aic_tolerance_s,
    )
    return rows


def default_cfneic_paths(input_root: str | Path) -> list[Path]:
    root = Path(input_root)
    return [path for name in ("out.cfneic_int", "out.cfneic_trig") if (path := root / name).exists()]


def _default_origin_path(cfneic_path: Path) -> Path:
    return cfneic_path.with_name(f"{cfneic_path.name}.origin")


def read_cfneic_with_origins(
    cfneic_paths: Iterable[str | Path],
    origin_paths: Iterable[str | Path] | None = None,
) -> tuple[list[CfneicRow], list[OriginRow]]:
    cfneic_rows: list[CfneicRow] = []
    origin_rows: list[OriginRow] = []
    cfneic_path_list = [Path(path) for path in cfneic_paths]
    origin_path_list = (
        [Path(path) for path in origin_paths]
        if origin_paths is not None
        else [_default_origin_path(path) for path in cfneic_path_list]
    )
    if len(cfneic_path_list) != len(origin_path_list):
        raise CatalogBuildError(
            f"cfneic/origin path count mismatch: {len(cfneic_path_list)} cfneic paths, "
            f"{len(origin_path_list)} origin paths"
        )
    for cfneic_path, origin_path in zip(cfneic_path_list, origin_path_list):
        cfneic_rows.extend(read_cfneic(cfneic_path))
        origin_rows.extend(read_origins(origin_path))
    return cfneic_rows, origin_rows


def write_catalog(rows: Iterable[CatalogRow], output: str | Path | TextIO, *, delimiter: str = "\t") -> None:
    """Write catalog rows as a simple delimited table with the canonical header."""

    close = False
    if hasattr(output, "write"):
        handle = output  # type: ignore[assignment]
    else:
        handle = Path(output).open("w", encoding="utf-8", newline="")
        close = True
    try:
        handle.write(delimiter.join(CATALOG_COLUMNS) + "\n")
        for row in rows:
            handle.write(delimiter.join(row.as_sequence()) + "\n")
    finally:
        if close:
            handle.close()


def write_provenance(
    rows: Iterable[ProvenanceRow],
    output: str | Path | TextIO,
    *,
    delimiter: str = "\t",
) -> None:
    """Write the internal source-row provenance sidecar."""

    close = False
    if hasattr(output, "write"):
        handle = output  # type: ignore[assignment]
    else:
        handle = Path(output).open("w", encoding="utf-8", newline="")
        close = True
    try:
        handle.write(delimiter.join(PROVENANCE_COLUMNS) + "\n")
        for row in rows:
            handle.write(delimiter.join(row.as_sequence()) + "\n")
    finally:
        if close:
            handle.close()


def build_catalog_from_paths(
    *,
    input_root: str | Path,
    output: str | Path,
    tomocat_path: str | Path | None = None,
    cfneic_paths: Iterable[str | Path] | None = None,
    origin_paths: Iterable[str | Path] | None = None,
    waveform_root: str | Path | None = None,
    provenance_output: str | Path | None = None,
    aic_tolerance_s: float = 0.02,
) -> list[CatalogRow]:
    root = Path(input_root)
    tomocat_rows = read_tomocat(tomocat_path if tomocat_path is not None else root / "tomocat.txt")
    chosen_cfneic_paths = list(cfneic_paths) if cfneic_paths is not None else default_cfneic_paths(root)
    cfneic_rows, origin_rows = read_cfneic_with_origins(chosen_cfneic_paths, origin_paths)
    waveform_cache = (
        ObsPyWaveformCache(WaveformIndex.from_root(waveform_root))
        if waveform_root is not None and ObsPyWaveformCache.obspy_available()
        else None
    )
    sncl_resolver = (
        (lambda row: waveform_cache.sncl_for_filename(row.filename))
        if waveform_cache is not None
        else None
    )
    rows, provenance = assemble_catalog_with_provenance(
        tomocat_rows,
        cfneic_rows,
        origin_rows,
        sncl_resolver=sncl_resolver,
        aic_tolerance_s=aic_tolerance_s,
    )
    write_catalog(rows, output)
    if provenance_output is not None:
        write_provenance(provenance, provenance_output)
    return rows
