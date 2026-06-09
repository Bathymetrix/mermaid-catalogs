"""Typed records and pure helpers for MERMAID catalog assembly."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping

CATALOG_COLUMNS: tuple[str, ...] = (
    "sttime",
    "sncl",
    "evtime",
    "evlo",
    "evla",
    "evdp",
    "evmag",
    "stlo",
    "stla",
    "stdp",
    "ocdp",
    "phase",
    "gcarc",
    "slow",
    "tobs",
    "tres",
    "surftime",
    "snr",
    "tobserr",
    "d01",
    "d23",
    "dtheta",
    "v1",
    "v2",
    "acc",
    "b",
    "h",
    "locerr",
    "evcat",
    "evid",
)

PROVENANCE_COLUMNS: tuple[str, ...] = (
    "row_index",
    "tomocat_path",
    "tomocat_line",
    "tomocat_filename",
    "cfneic_path",
    "cfneic_line",
    "origin_path",
    "origin_line",
    "cfneic_row_index",
    "origin_row_index",
)

DIAGNOSTIC_COLUMNS: tuple[str, ...] = (
    "row_index",
    "field",
    "check_name",
    "source_value",
    "computed_value",
    "difference",
    "threshold",
    "status",
    "message",
)


@dataclass(frozen=True)
class TomocatRow:
    """Minimal tomocat fields needed by the first-pass catalog scaffold."""

    filename: str
    event_time: str
    seismogram_time: str
    stlo: str
    stla: str
    stdp: str
    phase: str
    kstnm: str
    obs_travtime: str
    travtime_1d: str
    tres_1d: str
    raw_fields: tuple[str, ...]
    source_path: str = ""
    source_line: int = 0

    @property
    def aic_time(self) -> datetime:
        return aic_time(self.event_time, self.obs_travtime)


@dataclass(frozen=True)
class CfneicRow:
    """Minimal cfneic fields needed by the first-pass catalog scaffold."""

    year: str
    jd: str
    hr: str
    mi: str
    s: str
    ms: str
    evlo: str
    evla: str
    evdp: str
    d01: str
    d23: str
    mw: str
    angle: str
    kstnm: str
    stlo: str
    stla: str
    gcarc: str
    tobs: str
    stder: str
    tasc: str
    snr: str
    ocdp: str
    stel: str
    p: str
    v1: str
    v2: str
    acc: str
    b: str
    h: str
    locnerr: str
    raw_fields: tuple[str, ...]
    source_path: str = ""
    source_line: int = 0
    source_row_index: int = 0

    @property
    def event_time(self) -> datetime:
        return cfneic_timestamp(self.year, self.jd, self.hr, self.mi, self.s, self.ms)

    @property
    def event_time_text(self) -> str:
        return format_utc(self.event_time)

    @property
    def aic_time(self) -> datetime:
        return aic_time(self.event_time, self.tobs)


@dataclass(frozen=True)
class OriginRow:
    """Event provenance from an out.cfneic*.origin sidecar row."""

    catalog: str
    event_id: str
    source_path: str = ""
    source_line: int = 0
    source_row_index: int = 0


@dataclass(frozen=True)
class CatalogRow:
    """One first-pass merged MERMAID output catalog row."""

    values: Mapping[str, str]

    def as_dict(self) -> dict[str, str]:
        return {column: self.values.get(column, "") for column in CATALOG_COLUMNS}

    def as_sequence(self) -> tuple[str, ...]:
        row = self.as_dict()
        return tuple(row[column] for column in CATALOG_COLUMNS)


@dataclass(frozen=True)
class DiagnosticRow:
    """One verification/audit diagnostic row."""

    row_index: int
    field: str
    check_name: str
    source_value: str
    computed_value: str
    difference: str
    threshold: str
    status: str
    message: str


@dataclass(frozen=True)
class ProvenanceRow:
    """Internal sidecar mapping a science row back to source rows."""

    row_index: int
    tomocat_path: str
    tomocat_line: int
    tomocat_filename: str
    cfneic_path: str
    cfneic_line: int
    origin_path: str
    origin_line: int
    cfneic_row_index: int
    origin_row_index: int

    def as_sequence(self) -> tuple[str, ...]:
        return (
            str(self.row_index),
            self.tomocat_path,
            str(self.tomocat_line),
            self.tomocat_filename,
            self.cfneic_path,
            str(self.cfneic_line),
            self.origin_path,
            str(self.origin_line),
            str(self.cfneic_row_index),
            str(self.origin_row_index),
        )


def decimal_text(value: Decimal) -> str:
    """Render a Decimal without exponent notation or unnecessary trailing zeros."""

    if value == value.to_integral_value():
        return str(value.quantize(Decimal("1")))
    return format(value.normalize(), "f")


def stdp_from_stel(stel_m: str | Decimal) -> Decimal:
    """Convert cfneic station elevation to positive-down station depth."""

    return -Decimal(str(stel_m))


def updated_tres(cfneic_tobs: str | Decimal, tomocat_1d_travtime: str | Decimal) -> Decimal:
    """Preserve the tomocat residual definition with cfneic's updated tobs."""

    return Decimal(str(cfneic_tobs)) - Decimal(str(tomocat_1d_travtime))


def parse_utc(value: str) -> datetime:
    """Parse a UTC timestamp string without requiring a timezone suffix."""

    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def cfneic_timestamp(
    year: str | int,
    jd: str | int,
    hr: str | int,
    mi: str | int,
    s: str | int,
    ms: str | int,
) -> datetime:
    """Construct a UTC timestamp from cfneic year/julian-day/time columns."""

    start = datetime(int(year), 1, 1, tzinfo=timezone.utc)
    return start + timedelta(
        days=int(jd) - 1,
        hours=int(hr),
        minutes=int(mi),
        seconds=int(s),
        milliseconds=int(ms),
    )


def add_decimal_seconds(dt: datetime, seconds: str | Decimal) -> datetime:
    """Add decimal seconds rounded to the nearest microsecond."""

    decimal_seconds = Decimal(str(seconds))
    microseconds = int((decimal_seconds * Decimal("1000000")).to_integral_value(ROUND_HALF_UP))
    return dt + timedelta(microseconds=microseconds)


def aic_time(event_time: str | datetime, tobs_s: str | Decimal) -> datetime:
    """Compute the observed AIC arrival UTC from event origin time plus tobs."""

    dt = parse_utc(event_time) if isinstance(event_time, str) else event_time
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return add_decimal_seconds(dt.astimezone(timezone.utc), tobs_s)


def format_utc(dt: datetime) -> str:
    """Format UTC timestamps with millisecond precision when possible."""

    dt = dt.astimezone(timezone.utc)
    base = dt.strftime("%Y-%m-%dT%H:%M:%S")
    if dt.microsecond:
        fraction = f"{dt.microsecond:06d}".rstrip("0")
        return f"{base}.{fraction}"
    return base
