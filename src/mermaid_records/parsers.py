"""Parsers for legacy tomocat, cfneic, and cfneic origin sidecar rows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable, Iterator

from .models import CfneicRow, OriginRow, TomocatRow

TOMOCAT_FIELD_COUNT = 39
CFNEIC_FIELD_COUNT = 30

_STEL_P_RE = re.compile(r"^([+-]?\d+)([+-]\d+(?:\.\d+)?)$")
_NUMERIC_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][+-]?\d+)?$")


@dataclass(frozen=True)
class RowParseError(ValueError):
    """A parse error with file and line context."""

    path: str
    line_number: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line_number}: {self.message}"


def _iter_data_lines(path: Path) -> Iterator[tuple[int, str]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            yield line_number, stripped


def _split_cfneic_fields(fields: list[str]) -> list[str]:
    if len(fields) >= 23:
        match = _STEL_P_RE.match(fields[22])
        if match:
            fields = fields[:22] + [match.group(1), match.group(2)] + fields[23:]
    if len(fields) > CFNEIC_FIELD_COUNT and all(
        not _NUMERIC_RE.match(field) for field in fields[CFNEIC_FIELD_COUNT:]
    ):
        return fields[:CFNEIC_FIELD_COUNT]
    return fields


def parse_tomocat_line(line: str, *, path: str = "<string>", line_number: int = 1) -> TomocatRow:
    fields = line.split()
    if len(fields) != TOMOCAT_FIELD_COUNT:
        raise RowParseError(path, line_number, f"expected {TOMOCAT_FIELD_COUNT} fields, got {len(fields)}")
    return TomocatRow(
        filename=fields[0],
        event_time=fields[1],
        seismogram_time=fields[7],
        stlo=fields[8],
        stla=fields[9],
        stdp=fields[10],
        phase=fields[37],
        kstnm=fields[36],
        obs_travtime=fields[17],
        travtime_1d=fields[19],
        tres_1d=fields[21],
        raw_fields=tuple(fields),
        source_path=path,
        source_line=line_number,
    )


def parse_cfneic_line(
    line: str,
    *,
    path: str = "<string>",
    line_number: int = 1,
    source_row_index: int = 0,
) -> CfneicRow:
    fields = _split_cfneic_fields(line.split())
    if len(fields) != CFNEIC_FIELD_COUNT:
        raise RowParseError(path, line_number, f"expected {CFNEIC_FIELD_COUNT} fields, got {len(fields)}")
    return CfneicRow(
        year=fields[0],
        jd=fields[1],
        hr=fields[2],
        mi=fields[3],
        s=fields[4],
        ms=fields[5],
        evlo=fields[6],
        evla=fields[7],
        evdp=fields[8],
        d01=fields[9],
        d23=fields[10],
        mw=fields[11],
        angle=fields[12],
        kstnm=fields[13],
        stlo=fields[14],
        stla=fields[15],
        gcarc=fields[16],
        tobs=fields[17],
        stder=fields[18],
        tasc=fields[19],
        snr=fields[20],
        ocdp=fields[21],
        stel=fields[22],
        p=fields[23],
        v1=fields[24],
        v2=fields[25],
        acc=fields[26],
        b=fields[27],
        h=fields[28],
        locnerr=fields[29],
        raw_fields=tuple(fields),
        source_path=path,
        source_line=line_number,
        source_row_index=source_row_index,
    )


def parse_origin_line(
    line: str,
    *,
    path: str = "<string>",
    line_number: int = 1,
    source_row_index: int = 0,
) -> OriginRow:
    fields = line.split()
    if len(fields) != 2:
        raise RowParseError(path, line_number, f"expected 2 fields, got {len(fields)}")
    if fields[0] not in {"ISC", "NEIC"}:
        raise RowParseError(path, line_number, f"unknown event catalog {fields[0]!r}")
    return OriginRow(
        catalog=fields[0],
        event_id=fields[1],
        source_path=path,
        source_line=line_number,
        source_row_index=source_row_index,
    )


def read_tomocat(path: str | Path) -> list[TomocatRow]:
    source = Path(path)
    return [
        parse_tomocat_line(line, path=str(source), line_number=line_number)
        for line_number, line in _iter_data_lines(source)
    ]


def read_cfneic(path: str | Path) -> list[CfneicRow]:
    source = Path(path)
    rows: list[CfneicRow] = []
    for line_number, line in _iter_data_lines(source):
        if line.startswith("year "):
            continue
        rows.append(
            parse_cfneic_line(
                line,
                path=str(source),
                line_number=line_number,
                source_row_index=len(rows) + 1,
            )
        )
    return rows


def read_origins(path: str | Path) -> list[OriginRow]:
    source = Path(path)
    rows: list[OriginRow] = []
    for line_number, line in _iter_data_lines(source):
        if line.lower().startswith("catalog "):
            continue
        rows.append(
            parse_origin_line(
                line,
                path=str(source),
                line_number=line_number,
                source_row_index=len(rows) + 1,
            )
        )
    return rows


def read_many_cfneic(paths: Iterable[str | Path]) -> list[CfneicRow]:
    rows: list[CfneicRow] = []
    for path in paths:
        rows.extend(read_cfneic(path))
    return rows
