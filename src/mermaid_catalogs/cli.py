"""Command-line entry points for mermaid-catalogs."""

from __future__ import annotations

import argparse
from decimal import Decimal
import os
from pathlib import Path
from typing import Sequence

from . import __version__
from .catalog import build_catalog_from_paths
from .verify import verify_sources, write_diagnostics


def _add_catalog_build_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    catalog_parser = subparsers.add_parser("catalog", help="Catalog operations")
    catalog_subparsers = catalog_parser.add_subparsers(dest="catalog_command", required=True)
    build = catalog_subparsers.add_parser("build", help="Build a first-pass merged catalog")
    build.add_argument("--input-root", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    build.add_argument("--tomocat", type=Path, help="Override the default INPUT_ROOT/tomocat.txt path.")
    build.add_argument(
        "--cfneic",
        action="append",
        type=Path,
        help="Specific out.cfneic* file to include. May be repeated.",
    )
    build.add_argument(
        "--origin",
        action="append",
        type=Path,
        help="Origin sidecar paired by position with --cfneic. May be repeated.",
    )
    build.add_argument(
        "--provenance-output",
        type=Path,
        help="Optional internal source-row provenance TSV sidecar.",
    )
    build.add_argument(
        "--waveform-root",
        type=Path,
        help="Optional recursive SAC/mSEED root used to populate sncl.",
    )
    build.add_argument("--aic-tolerance-s", type=float, default=0.02)
    build.set_defaults(func=_run_catalog_build)

    verify = catalog_subparsers.add_parser("verify", help="Write scaffold catalog diagnostics")
    verify.add_argument("--input-root", required=True, type=Path)
    verify.add_argument("--diagnostics", required=True, type=Path)
    verify.add_argument("--tomocat", type=Path, help="Override the default INPUT_ROOT/tomocat.txt path.")
    verify.add_argument(
        "--cfneic",
        action="append",
        type=Path,
        help="Specific out.cfneic* file to include. May be repeated.",
    )
    verify.add_argument(
        "--origin",
        action="append",
        type=Path,
        help="Origin sidecar paired by position with --cfneic. May be repeated.",
    )
    verify.add_argument(
        "--waveform-root",
        type=Path,
        default=Path("~/mermaid/processed_everyone").expanduser(),
        help="Recursive SAC/mSEED root for ObsPy checks.",
    )
    verify.add_argument("--aic-tolerance-s", type=float, default=0.02)
    verify.add_argument("--diagnostic-threshold-s", type=Decimal, default=Decimal("0.02"))
    verify.add_argument("--starttime-threshold-s", type=Decimal, default=Decimal("0.01"))
    verify.add_argument("--coord-threshold-deg", type=Decimal, default=Decimal("0.001"))
    verify.add_argument("--depth-threshold-m", type=Decimal, default=Decimal("0.1"))
    verify.add_argument("--gcarc-threshold-deg", type=Decimal, default=Decimal("0.01"))
    verify.add_argument("--slow-threshold-s-per-km", type=Decimal, default=Decimal("0.01"))
    verify.add_argument("--tres-taup-threshold-s", type=Decimal, default=Decimal("1.0"))
    verify.set_defaults(func=_run_catalog_verify)


def _run_catalog_build(args: argparse.Namespace) -> int:
    rows = build_catalog_from_paths(
        input_root=args.input_root,
        output=args.output,
        tomocat_path=args.tomocat,
        cfneic_paths=args.cfneic,
        origin_paths=args.origin,
        waveform_root=args.waveform_root,
        provenance_output=args.provenance_output,
        aic_tolerance_s=args.aic_tolerance_s,
    )
    print(f"wrote {len(rows)} catalog rows to {args.output}")
    if args.provenance_output is not None:
        print(f"wrote provenance sidecar to {args.provenance_output}")
    return 0


def _run_catalog_verify(args: argparse.Namespace) -> int:
    cache_root = args.diagnostics.parent / "cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_root))
    mpl_cache = args.diagnostics.parent / "matplotlib-cache"
    mpl_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_cache))
    rows = verify_sources(
        input_root=args.input_root,
        tomocat_path=args.tomocat,
        cfneic_paths=args.cfneic,
        origin_paths=args.origin,
        waveform_root=args.waveform_root,
        aic_tolerance_s=args.aic_tolerance_s,
        diagnostic_threshold_s=args.diagnostic_threshold_s,
        starttime_threshold_s=args.starttime_threshold_s,
        coord_threshold_deg=args.coord_threshold_deg,
        depth_threshold_m=args.depth_threshold_m,
        gcarc_threshold_deg=args.gcarc_threshold_deg,
        slow_threshold_s_per_km=args.slow_threshold_s_per_km,
        tres_taup_threshold_s=args.tres_taup_threshold_s,
    )
    write_diagnostics(rows, args.diagnostics)
    failures = sum(row.status == "fail" for row in rows)
    print(f"wrote {len(rows)} diagnostics to {args.diagnostics} ({failures} failures)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mermaid-catalogs")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_catalog_build_parser(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
