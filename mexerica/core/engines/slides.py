"""Presentations through LibreOffice; slide images are rendered from the exported PDF."""

from pathlib import Path

import pymupdf

from ..context import Context
from . import office
from .pdf import render_pages

SLIDE_IMAGE_DPI = 150

CONVERSIONS = {
    "pptx": ["pdf", "jpg", "png", "odp"],
    "ppt": ["pptx", "pdf", "jpg", "png", "odp"],
    "odp": ["pptx", "pdf", "jpg", "png"],
    "key": ["pptx", "pdf", "jpg", "png", "odp"],
}


def convert(source: Path, source_key: str, target: str, ctx: Context) -> list[Path]:
    if target in ("jpg", "png"):
        pdf = office.lo_convert_one(ctx, source, "pdf")
        with pymupdf.open(pdf) as document:
            return render_pages(ctx, document, target, source.stem, SLIDE_IMAGE_DPI)
    return [office.lo_convert_one(ctx, source, target)]
