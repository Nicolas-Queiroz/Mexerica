"""Raster images with Pillow (HEIC through pillow-heif, AVIF native), SVG through MuPDF."""

from pathlib import Path

import pillow_heif
import pymupdf
from PIL import Image, ImageOps

from ..context import Context, OperationError

pillow_heif.register_heif_opener()

RASTER = ["jpg", "png", "webp", "heic", "tiff", "avif", "bmp"]
TARGETS = RASTER + ["pdf"]

CONVERSIONS = {
    source: [target for target in TARGETS if target != source] for source in RASTER
}
CONVERSIONS["svg"] = list(TARGETS)

PIL_FORMATS = {
    "jpg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
    "heic": "HEIF",
    "tiff": "TIFF",
    "avif": "AVIF",
    "bmp": "BMP",
    "pdf": "PDF",
}
SUPPORTS_ALPHA = {"png", "webp", "heic", "tiff", "avif"}
SVG_MIN_SIDE = 1600


def load(path: Path) -> Image.Image:
    """Opens any supported image upright (EXIF orientation applied), first frame only."""
    if path.suffix.lower() == ".svg":
        return _render_svg(path)
    try:
        with Image.open(path) as opened:
            image = ImageOps.exif_transpose(opened)
            image.load()
            return image
    except (OSError, ValueError) as error:
        raise OperationError(f"Não foi possível abrir a imagem: {error}") from error


def _render_svg(path: Path) -> Image.Image:
    try:
        document = pymupdf.open(path)
    except Exception as error:
        raise OperationError(f"SVG inválido: {error}") from error
    with document:
        page = document[0]
        longest = max(page.rect.width, page.rect.height) or 1
        zoom = max(1.0, SVG_MIN_SIDE / longest)
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True)
        return Image.frombytes("RGBA", (pixmap.width, pixmap.height), pixmap.samples)


def prepare(image: Image.Image, target: str) -> Image.Image:
    """Normalizes the color mode for the target format, flattening alpha on white."""
    has_alpha = image.mode in ("RGBA", "LA", "PA") or (
        image.mode == "P" and "transparency" in image.info
    )
    if image.mode.startswith("I;16") or image.mode in ("I", "F"):
        image = ImageOps.autocontrast(image.convert("I").point(lambda v: v / 256).convert("L"))
    if has_alpha:
        rgba = image.convert("RGBA")
        if target in SUPPORTS_ALPHA:
            return rgba
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    if image.mode == "L" and target in ("jpg", "png", "tiff", "bmp", "pdf", "webp"):
        return image
    return image.convert("RGB")


def save(image: Image.Image, out: Path, target: str, quality: int | None = None, exif=None) -> Path:
    """Saves with sensible defaults per format; quality applies to lossy formats."""
    image = prepare(image, target)
    options: dict = {}
    if target == "jpg":
        options = {"quality": quality or 90, "optimize": True, "progressive": True}
    elif target == "webp":
        options = {"quality": quality or 88, "method": 4}
    elif target == "avif":
        options = {"quality": quality or 75}
    elif target == "heic":
        options = {"quality": quality or 82}
    elif target == "png":
        options = {"optimize": True}
    elif target == "tiff":
        options = {"compression": "tiff_lzw"}
    elif target == "pdf":
        options = {"resolution": 150.0}
    if exif and target in ("jpg", "webp", "png", "tiff", "heic", "avif"):
        options["exif"] = exif
    image.save(out, PIL_FORMATS[target], **options)
    return out


def exif_without_orientation(image: Image.Image):
    """EXIF to carry over, with orientation reset because pixels are already upright."""
    exif = image.getexif()
    if not exif:
        return None
    exif[0x0112] = 1
    return exif.tobytes()


def convert(source: Path, source_key: str, target: str, ctx: Context) -> list[Path]:
    image = load(source)
    ctx.progress(0.4)
    out = ctx.workdir / f"{source.stem}.{target}"
    exif = exif_without_orientation(image) if source_key != "svg" else None
    save(image, out, target, exif=exif)
    ctx.progress(1.0)
    return [out]
