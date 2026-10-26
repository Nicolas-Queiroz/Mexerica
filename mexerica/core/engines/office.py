"""Headless LibreOffice, with a private profile so an open LibreOffice window does not block it."""

import shutil
import threading
import uuid
from pathlib import Path

from ..context import Context, OperationError
from ..paths import cache_dir

SOFFICE = shutil.which("soffice") or shutil.which("libreoffice")
_LOCK = threading.Lock()

FILTERS = {
    "pdf": "pdf",
    "docx": "docx:MS Word 2007 XML",
    "odt": "odt",
    "rtf": "rtf",
    "txt": "txt:Text (encoded):UTF8",
    "xlsx": "xlsx:Calc MS Excel 2007 XML",
    "ods": "ods",
    "pptx": "pptx:Impress MS PowerPoint 2007 XML",
    "odp": "odp",
}
CSV_EXPORT = "csv:Text - txt - csv (StarCalc):{separator},34,76,1,,0,false,true,false,false,false,-1"


def lo_convert(
    ctx: Context,
    source: Path,
    target: str,
    *,
    filter_name: str | None = None,
    env: dict | None = None,
) -> list[Path]:
    """Converts with soffice --convert-to and returns every file it produced."""
    if not SOFFICE:
        raise OperationError("O LibreOffice não está instalado (pacote libreoffice).")
    outdir = ctx.subdir(f"lo-{uuid.uuid4().hex[:8]}")
    profile = cache_dir() / "libreoffice-profile"
    args = [
        SOFFICE,
        f"-env:UserInstallation={profile.as_uri()}",
        "--headless",
        "--norestore",
        "--nolockcheck",
        "--convert-to",
        filter_name or FILTERS[target],
        "--outdir",
        outdir,
        source,
    ]
    ctx.progress(0.1)
    with _LOCK:
        ctx.run(
            args, timeout=900, env=env, error_message="O LibreOffice não conseguiu converter o arquivo"
        )
    produced = sorted(path for path in outdir.iterdir() if path.is_file())
    if not produced:
        raise OperationError(
            "O LibreOffice não conseguiu abrir o arquivo. Ele pode estar protegido por senha ou corrompido."
        )
    ctx.progress(0.9)
    return produced


def lo_convert_one(ctx: Context, source: Path, target: str) -> Path:
    return lo_convert(ctx, source, target)[0]


def lo_export_csv(ctx: Context, source: Path, separator: str) -> list[Path]:
    """Exports every sheet with raw values (1.25, not the locale's 1,25).

    LibreOffice names the files <file>-<sheet>.csv when there are several sheets.
    """
    code = {",": 44, "\t": 9, ";": 59}[separator]
    # Number formatting follows the process locale, whatever the filter options say.
    return lo_convert(
        ctx,
        source,
        "csv",
        filter_name=CSV_EXPORT.format(separator=code),
        env={"LC_ALL": "C.UTF-8", "LANG": "C.UTF-8"},
    )
