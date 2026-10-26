"""Text documents: LibreOffice for layout-faithful formats, pandoc for markup formats."""

import shutil
from pathlib import Path

import pypandoc

from ..context import Context
from . import office

PANDOC = pypandoc.get_pandoc_path()

TARGETS = ["docx", "odt", "pdf", "md", "txt", "epub", "html", "rtf"]
SOURCES = ["docx", "doc", "odt", "pages", "md", "txt", "epub", "rtf"]
CONVERSIONS = {source: [target for target in TARGETS if target != source] for source in SOURCES}

LIBREOFFICE_READS = {"docx", "doc", "odt", "pages", "txt", "rtf"}
LIBREOFFICE_WRITES = {"docx", "odt", "pdf", "rtf"}
PANDOC_READERS = {"docx": "docx", "odt": "odt", "md": "markdown", "epub": "epub", "rtf": "rtf"}
PANDOC_WRITERS = {
    "md": ["-t", "gfm", "--wrap=none"],
    "txt": ["-t", "plain", "--wrap=none"],
    "epub": ["-t", "epub3"],
    "html": ["-t", "html5", "--standalone", "--embed-resources"],
    "docx": ["-t", "docx"],
    "odt": ["-t", "odt"],
    "rtf": ["-t", "rtf", "--standalone"],
}


def pandoc(ctx: Context, source: Path, reader: str, target: str, title: str) -> list[Path]:
    """Runs pandoc in its own folder; images extracted for Markdown travel with the file."""
    folder = ctx.subdir(f"pandoc-{target}")
    out = folder / f"{source.stem}.{target}"
    args = [PANDOC, "-f", reader, *PANDOC_WRITERS[target], "-o", out.name]
    if target in ("epub", "html"):
        args += ["--metadata", f"title={title}"]
    if target == "md":
        args += ["--extract-media=."]
    args.append(source.resolve())
    ctx.run(args, cwd=folder, timeout=600, error_message="O pandoc não conseguiu converter o documento")
    produced = [out]
    media = folder / "media"
    if media.is_dir():
        produced.append(media)
    return produced


def convert(source: Path, source_key: str, target: str, ctx: Context) -> list[Path]:
    title = source.stem
    if target in LIBREOFFICE_WRITES and source_key in LIBREOFFICE_READS:
        return [office.lo_convert_one(ctx, source, target)]
    if source_key == "txt" and target == "md":
        out = ctx.workdir / f"{source.stem}.md"
        shutil.copyfile(source, out)
        return [out]
    if source_key in PANDOC_READERS and target in PANDOC_WRITERS:
        return pandoc(ctx, source, PANDOC_READERS[source_key], target, title)
    if source_key in LIBREOFFICE_READS:
        # doc, pages and txt reach pandoc through an intermediate DOCX.
        docx = office.lo_convert_one(ctx, source, "docx")
        return pandoc(ctx, docx, "docx", target, title)
    # md and epub reach PDF through an intermediate DOCX.
    docx = pandoc(ctx, source, PANDOC_READERS[source_key], "docx", title)[0]
    return [office.lo_convert_one(ctx, docx, target)]
