from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from mermaid_catalogs.catalog import (
    assemble_catalog,
    assemble_catalog_with_provenance,
    build_catalog_row,
    write_catalog,
    write_provenance,
)
from mermaid_catalogs.models import (
    CATALOG_COLUMNS,
    DIAGNOSTIC_COLUMNS,
    PROVENANCE_COLUMNS,
    aic_time,
    cfneic_timestamp,
    stdp_from_stel,
    updated_tres,
)
from mermaid_catalogs.parsers import parse_cfneic_line, read_cfneic, read_origins, read_tomocat
from mermaid_catalogs.verify import verify_sources, write_diagnostics
from mermaid_catalogs.waveforms import ObsPyWaveformCache, WaveformIndex, iter_waveform_pairs

FIXTURES = Path(__file__).parent / "fixtures" / "catalog"


def test_cfneic_timestamp_construction() -> None:
    assert cfneic_timestamp("2018", "187", "01", "40", "05", "789").isoformat() == (
        "2018-07-06T01:40:05.789000+00:00"
    )


def test_stdp_from_stel() -> None:
    assert stdp_from_stel("-1512") == Decimal("1512")


def test_tobs_preserves_aic_utc_worked_example() -> None:
    old_aic = aic_time("2018-07-06T01:40:04.61", "658.77")
    new_aic = aic_time(cfneic_timestamp("2018", "187", "01", "40", "05", "789"), "657.59")
    assert abs((old_aic - new_aic).total_seconds()) <= 0.002


def test_updated_tres_uses_cfneic_tobs_and_tomocat_1d_travtime() -> None:
    assert updated_tres("657.59", "659.48") == Decimal("-1.89")


def test_assemble_catalog_and_origin_mapping() -> None:
    tomocat_rows = read_tomocat(FIXTURES / "tomocat_sample.txt")
    cfneic_rows = read_cfneic(FIXTURES / "out.cfneic_trig_sample")
    origin_rows = read_origins(FIXTURES / "out.cfneic_trig_sample.origin")

    rows = assemble_catalog(tomocat_rows, cfneic_rows, origin_rows)

    assert len(rows) == 2
    first = rows[0].as_dict()
    assert first["evtime"] == "2018-07-06T01:40:05.789"
    assert first["stdp"] == "1512"
    assert first["tobs"] == "657.59"
    assert first["tres"] == "-1.89"
    assert first["evcat"] == "ISC"
    assert first["evid"] == "612281237"
    assert rows[1].as_dict()["tres"] == "-1.10"


def test_parser_handles_concatenated_stel_and_slowness() -> None:
    cfneic_rows = read_cfneic(FIXTURES / "out.cfneic_int_sample")

    assert cfneic_rows[0].stel == "-1518"
    assert cfneic_rows[0].p == "-0.085"


def test_parser_ignores_trailing_cfneic_text_annotation() -> None:
    row = parse_cfneic_line(
        "2019 108 07 27 22 990 -177.288 -15.746 419.8 9.9 9.1 4.2 "
        "190.0 P0006 178.386 -14.671 4.311 77.89 0.03 44.88 105 2703 "
        "-1508 0.085 2.58 2.57 -0.00 0.00 0.19 -0.0052 mis"
    )

    assert row.locnerr == "-0.0052"


def test_parser_handles_concatenated_stel_slowness_with_trailing_annotation() -> None:
    row = parse_cfneic_line(
        "2018 231 00 47 34 210 -178.112 -18.215 596.6 6.9 4.8 5.3 "
        "134.4 P0006 -179.710 -13.859 4.595 87.97 0.03 28.40 85 2137 "
        "-1492-0.068 2.79 2.08 -0.29 0.19 0.39 -0.0249 mis"
    )

    assert row.stel == "-1492"
    assert row.p == "-0.068"
    assert row.locnerr == "-0.0249"


def test_output_column_order(tmp_path: Path) -> None:
    tomocat = read_tomocat(FIXTURES / "tomocat_sample.txt")[1]
    cfneic = read_cfneic(FIXTURES / "out.cfneic_trig_sample")[0]
    origin = read_origins(FIXTURES / "out.cfneic_trig_sample.origin")[0]
    row = build_catalog_row(tomocat, cfneic, origin)
    output = tmp_path / "catalog.tsv"

    write_catalog([row], output)

    header = output.read_text(encoding="utf-8").splitlines()[0].split("\t")
    assert tuple(header) == CATALOG_COLUMNS


def test_golden_catalog_output(tmp_path: Path) -> None:
    rows = assemble_catalog(
        read_tomocat(FIXTURES / "tomocat_sample.txt"),
        read_cfneic(FIXTURES / "out.cfneic_trig_sample"),
        read_origins(FIXTURES / "out.cfneic_trig_sample.origin"),
    )
    output = tmp_path / "catalog.tsv"

    write_catalog(rows, output)

    assert output.read_text(encoding="utf-8") == (
        FIXTURES / "expected_catalog_trig.tsv"
    ).read_text(encoding="utf-8")


def test_provenance_sidecar_output(tmp_path: Path) -> None:
    _, provenance = assemble_catalog_with_provenance(
        read_tomocat(FIXTURES / "tomocat_sample.txt"),
        read_cfneic(FIXTURES / "out.cfneic_trig_sample"),
        read_origins(FIXTURES / "out.cfneic_trig_sample.origin"),
    )
    output = tmp_path / "provenance.tsv"

    write_provenance(provenance, output)

    lines = output.read_text(encoding="utf-8").splitlines()
    assert tuple(lines[0].split("\t")) == PROVENANCE_COLUMNS
    assert lines[1].split("\t")[3] == "20180706T014928.06_5B3F1904.MER.DET.WLT5.sac"
    assert lines[1].split("\t")[8:] == ["1", "1"]


def test_diagnostics_writer_and_source_verify(tmp_path: Path) -> None:
    diagnostics = verify_sources(
        input_root=FIXTURES,
        tomocat_path=FIXTURES / "tomocat_sample.txt",
        cfneic_paths=[FIXTURES / "out.cfneic_trig_sample"],
        origin_paths=[FIXTURES / "out.cfneic_trig_sample.origin"],
    )
    output = tmp_path / "diagnostics.tsv"

    write_diagnostics(diagnostics, output)

    lines = output.read_text(encoding="utf-8").splitlines()
    assert tuple(lines[0].split("\t")) == DIAGNOSTIC_COLUMNS
    assert len(diagnostics) == 20
    assert [row.status for row in diagnostics if row.check_name == "tobs_arrival_utc_check"] == [
        "ok",
        "ok",
    ]
    assert lines[1].split("\t")[2] == "tobs_arrival_utc_check"


def test_waveform_pair_generator(tmp_path: Path) -> None:
    dive = tmp_path / "serial" / "dive"
    dive.mkdir(parents=True)
    (dive / "event.mseed").write_bytes(b"")
    (dive / "event.sac").write_bytes(b"")

    pairs = list(iter_waveform_pairs(tmp_path))

    assert len(pairs) == 1
    assert pairs[0].key == "event"
    assert pairs[0].mseed_path == dive / "event.mseed"
    assert pairs[0].sac_path == dive / "event.sac"


def _write_waveform_pair(root: Path, filename: str, sttime: str, stlo: str, stla: str, stdp: str) -> None:
    obspy = pytest.importorskip("obspy")
    np = pytest.importorskip("numpy")

    root.mkdir(parents=True, exist_ok=True)
    base = filename.removesuffix(".sac")
    data = np.arange(8, dtype=np.float32)
    mseed_trace = obspy.Trace(data=data.copy())
    mseed_trace.stats.starttime = obspy.UTCDateTime(sttime)
    mseed_trace.stats.network = "MR"
    mseed_trace.stats.station = base.split(".")[1].split("_")[0].removeprefix("5B")[:5] or "MER"
    mseed_trace.stats.location = ""
    mseed_trace.stats.channel = "BHZ"
    obspy.Stream([mseed_trace]).write(str(root / f"{base}.mseed"), format="MSEED")

    sac_trace = obspy.Trace(data=data.copy())
    sac_trace.stats.starttime = obspy.UTCDateTime(sttime)
    sac_trace.stats.sac = {
        "stlo": float(stlo),
        "stla": float(stla),
        "stdp": float(stdp),
    }
    obspy.Stream([sac_trace]).write(str(root / f"{base}.sac"), format="SAC")


def test_obspy_waveform_cache_and_checks(tmp_path: Path) -> None:
    pytest.importorskip("obspy")
    tomocat_rows = read_tomocat(FIXTURES / "tomocat_sample.txt")
    cfneic_rows = read_cfneic(FIXTURES / "out.cfneic_trig_sample")
    waveforms = tmp_path / "waveforms" / "452.020-P-06" / "0002"
    for tomocat, cfneic in zip(tomocat_rows[1:], cfneic_rows):
        _write_waveform_pair(
            waveforms,
            tomocat.filename,
            tomocat.seismogram_time,
            tomocat.stlo,
            tomocat.stla,
            str(stdp_from_stel(cfneic.stel)),
        )

    cache = ObsPyWaveformCache(WaveformIndex.from_root(tmp_path / "waveforms"))
    cache.read_mseed_for_filename(tomocat_rows[1].filename)
    cache.read_mseed_for_filename(tomocat_rows[1].filename)
    assert cache.read_count == 1

    diagnostics = verify_sources(
        input_root=FIXTURES,
        tomocat_path=FIXTURES / "tomocat_sample.txt",
        cfneic_paths=[FIXTURES / "out.cfneic_trig_sample"],
        origin_paths=[FIXTURES / "out.cfneic_trig_sample.origin"],
        waveform_root=tmp_path / "waveforms",
    )
    by_check = {(row.row_index, row.check_name): row for row in diagnostics}

    assert by_check[(1, "sttime_mseed_check")].status == "ok"
    assert by_check[(1, "sncl_mseed_check")].status == "ok"
    assert by_check[(1, "stlo_sac_check")].status == "ok"
    assert by_check[(1, "stla_sac_check")].status == "ok"
    assert by_check[(1, "stdp_sac_check")].status == "ok"
    assert by_check[(1, "gcarc_obspy_check")].status in {"ok", "fail"}
    assert by_check[(1, "phase_taup_check")].status in {"ok", "fail"}
