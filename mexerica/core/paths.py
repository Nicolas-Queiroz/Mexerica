"""Where results land: output folder, collision-free names and moving work files."""

import os
import shutil
from pathlib import Path

from .formats import split_extension


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    path = base / "mexerica"
    path.mkdir(parents=True, exist_ok=True)
    return path


def downloads_dir() -> Path:
    try:
        import gi

        gi.require_version("GLib", "2.0")
        from gi.repository import GLib

        folder = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        if folder:
            return Path(folder)
    except (ImportError, ValueError):
        pass
    return Path.home() / "Downloads"


def output_dir_for(source: Path, configured: str | None = None) -> Path:
    """Source folder by default; falls back to Downloads when it is read-only."""
    if configured:
        folder = Path(configured).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    folder = source.parent
    if os.access(folder, os.W_OK):
        return folder
    fallback = downloads_dir()
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def unique_path(path: Path) -> Path:
    """Returns the path itself or a 'name (2).ext' variant that does not exist yet."""
    if not path.exists():
        return path
    stem, ext = split_extension(path)
    suffix = f".{ext}" if ext else ""
    counter = 2
    while True:
        candidate = path.with_name(f"{stem} ({counter}){suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def place_results(
    produced: list[Path],
    source: Path,
    dest_dir: Path,
    *,
    suffix: str = "",
    folder_label: str = "",
) -> list[Path]:
    """Moves engine output to its final place and returns the final paths.

    One file keeps the source name with the new extension; several files go into a folder.
    """
    stem, _ext = split_extension(source) if source.is_file() else (source.name, "")
    tag = f" ({suffix})" if suffix else ""
    if len(produced) == 1 and produced[0].is_file():
        _out_stem, out_ext = split_extension(produced[0])
        name = f"{stem}{tag}.{out_ext}" if out_ext else f"{stem}{tag}"
        final = unique_path(dest_dir / name)
        shutil.move(str(produced[0]), final)
        return [final]
    if len(produced) == 1 and produced[0].is_dir():
        final = unique_path(dest_dir / f"{stem}{tag}")
        shutil.move(str(produced[0]), final)
        return [final]
    label = suffix or folder_label
    folder = unique_path(dest_dir / (f"{stem} ({label})" if label else stem))
    folder.mkdir(parents=True)
    for item in produced:
        shutil.move(str(item), folder / item.name)
    return [folder]
