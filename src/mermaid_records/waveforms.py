"""Recursive waveform discovery and lazy ObsPy reads."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
import warnings

MSEED_EXTENSIONS = {".mseed", ".miniseed", ".msd"}
SAC_EXTENSIONS = {".sac"}
WAVEFORM_EXTENSIONS = MSEED_EXTENSIONS | SAC_EXTENSIONS


@dataclass(frozen=True)
class WaveformPair:
    """Likely mSEED/SAC pair sharing a filename base."""

    key: str
    mseed_path: Path | None = None
    sac_path: Path | None = None


def waveform_key(filename: str | Path) -> str:
    """Return the shared SAC/mSEED basename key for a path or catalog filename."""

    path = Path(filename)
    suffix = path.suffix.lower()
    if suffix in WAVEFORM_EXTENSIONS:
        return path.name[: -len(path.suffix)]
    return path.name


def iter_waveform_files(root: str | Path) -> Iterator[Path]:
    """Yield likely waveform files recursively under root."""

    base = Path(root).expanduser()
    if not base.exists():
        return
    for path in base.rglob("*"):
        if path.is_file() and path.suffix.lower() in WAVEFORM_EXTENSIONS:
            yield path


def iter_waveform_pairs(root: str | Path) -> Iterator[WaveformPair]:
    """Yield likely SAC/mSEED pairs discovered recursively under root."""

    by_key: dict[str, dict[str, Path]] = defaultdict(dict)
    for path in iter_waveform_files(root):
        kind = "mseed" if path.suffix.lower() in MSEED_EXTENSIONS else "sac"
        by_key[waveform_key(path)][kind] = path
    for key, paths in by_key.items():
        yield WaveformPair(key=key, mseed_path=paths.get("mseed"), sac_path=paths.get("sac"))


class WaveformIndex:
    """Index waveform pairs by filename base without reading waveform contents."""

    def __init__(self, pairs: dict[str, list[WaveformPair]] | None = None) -> None:
        self._pairs = pairs or {}

    @classmethod
    def from_root(cls, root: str | Path | None) -> "WaveformIndex":
        if root is None:
            return cls()
        pairs: dict[str, list[WaveformPair]] = defaultdict(list)
        for pair in iter_waveform_pairs(root):
            pairs[pair.key].append(pair)
        return cls(dict(pairs))

    def pair_for_filename(self, filename: str | Path) -> tuple[WaveformPair | None, str]:
        key = waveform_key(filename)
        matches = self._pairs.get(key, [])
        if not matches:
            return None, f"no waveform pair found for {key}"
        if len(matches) > 1:
            return None, f"ambiguous waveform pair for {key}: {len(matches)} matches"
        return matches[0], ""


class ObsPyWaveformCache:
    """Lazy, path-keyed ObsPy stream cache."""

    def __init__(self, index: WaveformIndex) -> None:
        self.index = index
        self._streams: dict[Path, Any] = {}
        self.read_count = 0

    @staticmethod
    def obspy_available() -> bool:
        try:
            import obspy  # noqa: F401
        except ImportError:
            return False
        return True

    def read_stream(self, path: Path, *, format_name: str) -> Any:
        """Read a waveform once with ObsPy and return the cached Stream."""

        resolved = path.expanduser().resolve()
        if resolved not in self._streams:
            from obspy import read

            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="Sample spacing read from SAC file.*",
                    category=UserWarning,
                )
                self._streams[resolved] = read(str(resolved), format=format_name, headonly=True)
            self.read_count += 1
        return self._streams[resolved]

    def read_mseed_for_filename(self, filename: str | Path) -> tuple[Path | None, Any | None, str]:
        pair, message = self.index.pair_for_filename(filename)
        if pair is None:
            return None, None, message
        if pair.mseed_path is None:
            return None, None, f"no mSEED file found for {waveform_key(filename)}"
        try:
            return pair.mseed_path, self.read_stream(pair.mseed_path, format_name="MSEED"), ""
        except Exception as exc:  # pragma: no cover - exercised with real malformed files.
            return pair.mseed_path, None, f"failed to read mSEED: {exc}"

    def read_sac_for_filename(self, filename: str | Path) -> tuple[Path | None, Any | None, str]:
        pair, message = self.index.pair_for_filename(filename)
        if pair is None:
            return None, None, message
        if pair.sac_path is None:
            return None, None, f"no SAC file found for {waveform_key(filename)}"
        try:
            return pair.sac_path, self.read_stream(pair.sac_path, format_name="SAC"), ""
        except Exception as exc:  # pragma: no cover - exercised with real malformed files.
            return pair.sac_path, None, f"failed to read SAC: {exc}"

    def sncl_for_filename(self, filename: str | Path) -> str:
        """Return Station.Network.Location.Channel from the matching mSEED header."""

        _, stream, message = self.read_mseed_for_filename(filename)
        if stream is None or message:
            return ""
        trace = primary_trace(stream)
        if trace is None:
            return ""
        stats = trace.stats
        return f"{stats.station}.{stats.network}.{stats.location}.{stats.channel}"


def primary_trace(stream: Any) -> Any | None:
    """Return the only trace in a Stream, or None if it is ambiguous."""

    if len(stream) != 1:
        return None
    return stream[0]
