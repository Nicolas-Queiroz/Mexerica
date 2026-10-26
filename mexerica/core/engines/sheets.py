"""Spreadsheets: LibreOffice for workbooks, the csv module and openpyxl for delimited text."""

import csv
from pathlib import Path

from ..context import Context, OperationError
from . import office
from .pdf import as_cell

CONVERSIONS = {
    "xlsx": ["ods", "csv", "tsv", "pdf"],
    "xls": ["xlsx", "ods", "csv", "tsv", "pdf"],
    "ods": ["xlsx", "csv", "tsv", "pdf"],
    "csv": ["xlsx", "ods", "tsv", "pdf"],
    "tsv": ["xlsx", "ods", "csv", "pdf"],
    "numbers": ["xlsx", "ods", "csv", "tsv", "pdf"],
}
SEPARATORS = {"csv": ",", "tsv": "\t"}


def read_text(source: Path) -> str:
    raw = source.read_bytes()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise OperationError("Não foi possível identificar a codificação do arquivo.")


def read_rows(source: Path, source_key: str) -> tuple[list[list[str]], str]:
    """Rows of a delimited file; CSV separator is sniffed among , ; | and tab."""
    text = read_text(source)
    if source_key == "tsv":
        delimiter = "\t"
    else:
        try:
            delimiter = csv.Sniffer().sniff(text[:20000], delimiters=",;|\t").delimiter
        except csv.Error:
            delimiter = ","
    return list(csv.reader(text.splitlines(), delimiter=delimiter)), delimiter


def write_xlsx(rows: list[list[str]], out: Path, title: str) -> Path:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title[:31] or "Planilha"
    for row in rows:
        sheet.append([as_cell(cell) for cell in row])
    workbook.save(out)
    return out


def write_delimited(rows: list[list[str]], out: Path, delimiter: str) -> Path:
    with out.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle, delimiter=delimiter).writerows(rows)
    return out


def convert(source: Path, source_key: str, target: str, ctx: Context) -> list[Path]:
    stem = source.stem
    if source_key in SEPARATORS:
        rows, _delimiter = read_rows(source, source_key)
        if target in SEPARATORS:
            return [write_delimited(rows, ctx.workdir / f"{stem}.{target}", SEPARATORS[target])]
        xlsx = write_xlsx(rows, ctx.subdir("xlsx") / f"{stem}.xlsx", stem)
        if target == "xlsx":
            return [xlsx]
        return [office.lo_convert_one(ctx, xlsx, target)]
    if target in SEPARATORS:
        produced = office.lo_export_csv(ctx, source, SEPARATORS[target])
        renamed = []
        for path in produced:
            final = path.with_suffix(f".{target}")
            path.rename(final)
            renamed.append(final)
        return renamed
    return [office.lo_convert_one(ctx, source, target)]
