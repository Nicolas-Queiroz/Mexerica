"""Checks that an output file really is a readable file of the expected format."""

import csv
import tarfile
import zipfile
from pathlib import Path

import pymupdf
from PIL import Image

from mexerica.core.engines import media

ZIP_BASED = {"docx", "xlsx", "pptx", "odt", "ods", "odp", "epub", "zip"}


def files_in(result: Path) -> list[Path]:
    if result.is_dir():
        return sorted(path for path in result.rglob("*") if path.is_file())
    return [result]


def check(result: Path, target: str) -> None:
    files = files_in(result)
    assert files, f"{result} is empty"
    main = [path for path in files if path.suffix.lower().lstrip(".") in (target, "gz", "md")] or files
    for path in main:
        assert path.stat().st_size > 0, f"{path} is empty"
        check_file(path, target)


def check_file(path: Path, target: str) -> None:
    if target in ("jpg", "png", "webp", "heic", "tiff", "avif", "bmp"):
        with Image.open(path) as image:
            image.load()
            assert image.width > 0
    elif target == "pdf":
        with pymupdf.open(path) as document:
            assert len(document) >= 1
    elif target in media.AUDIO:
        info = media.probe(path)
        assert info.has_audio and info.duration > 0.5, f"{path}: {info}"
    elif target in media.VIDEO:
        info = media.probe(path)
        assert info.has_video and info.duration > 0.5, f"{path}: {info}"
    elif target in ZIP_BASED:
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            assert archive.namelist()
    elif target in ("tar", "tgz"):
        with tarfile.open(path) as archive:
            assert archive.getnames()
    elif target == "7z":
        assert path.read_bytes()[:2] == b"7z"
    elif target in ("csv", "tsv"):
        with path.open(encoding="utf-8") as handle:
            rows = list(csv.reader(handle, delimiter="," if target == "csv" else "\t"))
        assert rows and len(rows[0]) >= 1
    elif target in ("md", "txt", "html", "srt", "vtt", "rtf"):
        text = path.read_text(encoding="utf-8", errors="replace")
        assert text.strip(), f"{path} has no text"
        if target == "vtt":
            assert text.startswith("WEBVTT")
        if target == "rtf":
            assert text.startswith("{\\rtf")
    else:
        raise AssertionError(f"no validator for {target}")
