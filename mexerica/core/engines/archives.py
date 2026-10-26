"""ZIP, TAR, TAR.GZ and 7Z; RAR and 7Z are read through the 7z command."""

import gzip
import shutil
import tarfile
import zipfile
from pathlib import Path

from ..context import Context, OperationError
from ..formats import split_extension

SEVEN_ZIP = shutil.which("7z") or shutil.which("7zz") or shutil.which("7za")

WRITABLE = ["zip", "tar", "tgz", "7z"]
CONVERSIONS = {
    "zip": ["tar", "tgz", "7z"],
    "tar": ["zip", "tgz", "7z"],
    "tgz": ["zip", "tar", "7z"],
    "7z": ["zip", "tar", "tgz"],
    "rar": ["zip", "tar", "tgz", "7z"],
}
EXTENSIONS = {"zip": "zip", "tar": "tar", "tgz": "tar.gz", "7z": "7z"}
EXTRACTABLE = ["zip", "tar", "tgz", "gz", "rar", "7z"]


def _inside(base: Path, target: Path) -> bool:
    return base.resolve() in (target.resolve(), *target.resolve().parents)


def extract(ctx: Context, source: Path, source_key: str, dest: Path) -> Path:
    """Extracts safely: entries escaping the destination are refused."""
    dest.mkdir(parents=True, exist_ok=True)
    try:
        if source_key == "zip":
            with zipfile.ZipFile(source) as archive:
                for member in archive.infolist():
                    if not _inside(dest, dest / member.filename):
                        raise OperationError(f"Entrada insegura no ZIP: {member.filename}")
                archive.extractall(dest)
        elif source_key in ("tar", "tgz"):
            with tarfile.open(source) as archive:
                archive.extractall(dest, filter="data")
        elif source_key == "gz":
            stem, _ext = split_extension(source)
            with gzip.open(source, "rb") as packed, (dest / stem).open("wb") as unpacked:
                shutil.copyfileobj(packed, unpacked)
        else:
            if not SEVEN_ZIP:
                raise OperationError("Instale o 7-Zip (pacote 7zip) para abrir arquivos RAR e 7Z.")
            ctx.run(
                [SEVEN_ZIP, "x", "-y", "-p", f"-o{dest}", source],
                error_message="Não foi possível extrair o arquivo (senha ou arquivo corrompido?)",
            )
    except (zipfile.BadZipFile, tarfile.TarError, gzip.BadGzipFile, EOFError) as error:
        raise OperationError(f"Arquivo compactado corrompido: {error}") from error
    except RuntimeError as error:
        raise OperationError(f"Não foi possível extrair: {error}") from error
    return dest


def pack(ctx: Context, items: list[Path], out: Path, target: str) -> Path:
    """Packs files and folders, each at the root of the archive under its own name."""
    if target == "zip":
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for item in items:
                ctx.check_cancelled()
                if item.is_dir():
                    archive.write(item, item.name)
                    for path in sorted(item.rglob("*")):
                        archive.write(path, Path(item.name) / path.relative_to(item))
                else:
                    archive.write(item, item.name)
    elif target in ("tar", "tgz"):
        with tarfile.open(out, "w:gz" if target == "tgz" else "w") as archive:
            for item in items:
                archive.add(item, item.name)
    else:
        if not SEVEN_ZIP:
            raise OperationError("Instale o 7-Zip (pacote 7zip) para criar arquivos 7Z.")
        ctx.run([SEVEN_ZIP, "a", "-y", out, *[item.name for item in items]], cwd=items[0].parent)
    return out


def convert(source: Path, source_key: str, target: str, ctx: Context) -> list[Path]:
    contents = extract(ctx, source, source_key, ctx.subdir("extracted"))
    ctx.progress(0.5)
    stem, _ext = split_extension(source)
    out = ctx.workdir / f"{stem}.{EXTENSIONS[target]}"
    items = sorted(contents.iterdir())
    if not items:
        raise OperationError("O arquivo compactado está vazio.")
    pack(ctx, items, out, target)
    return [out]
