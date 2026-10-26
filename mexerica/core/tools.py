"""File tools (compress, trim, crop, split, merge…) offered by the Tools wheel."""

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pymupdf
from PIL import Image, ImageChops, ImageOps

from .context import Context, OperationError
from .engines import archives, images, media, subtitles
from .formats import detect_format, split_extension


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    kind: str = "choice"  # choice | text | password
    default: str = ""
    choices: tuple[tuple[str, str], ...] = ()
    placeholder: str = ""


@dataclass(frozen=True)
class Tool:
    id: str
    label: str
    icon: str
    formats: frozenset[str] | None  # None: any file or folder
    run: Callable[[list[Path], Context], list[Path]]
    params: tuple[Param, ...] = ()
    multi: bool = False
    min_files: int = 1
    suffix: str = ""
    name_from: Callable[[list[Path]], Path] | None = field(default=None, compare=False)

    def applies_to(self, paths: list[Path]) -> bool:
        if len(paths) < self.min_files:
            return False
        if self.formats is None:
            return True
        for path in paths:
            fmt = detect_format(path)
            if fmt is None or fmt.key not in self.formats:
                return False
        return True

    def name_source(self, batch: list[Path]) -> Path:
        return self.name_from(batch) if self.name_from else batch[0]

    def default_params(self) -> dict:
        return {param.key: param.default for param in self.params}


RASTER = frozenset(images.RASTER)
AUDIO = frozenset(media.AUDIO)
VIDEO = frozenset(media.VIDEO)
MOVING = VIDEO - {"gif"}
LOSSY_AUDIO = frozenset({"mp3", "m4a", "ogg", "opus", "wma"})
PDF = frozenset({"pdf"})
ARCHIVES = frozenset(archives.EXTRACTABLE)
SUBTITLES = frozenset({"srt", "vtt"})

ROTATION = Param(
    "angle",
    "Rotação",
    default="90",
    choices=(("90", "90° no sentido horário"), ("270", "90° no sentido anti-horário"), ("180", "180°")),
)
TRIM = (
    Param("start", "Início", "text", "0:00", placeholder="0:00"),
    Param("end", "Fim", "text", "", placeholder="vazio = até o final"),
)


def parse_time(text: str, *, label: str) -> float | None:
    """Accepts 90, 1:30, 1:02:03 and decimal commas; empty means no value."""
    text = (text or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        seconds = 0.0
        for part in text.split(":"):
            seconds = seconds * 60 + float(part)
    except ValueError as error:
        raise OperationError(f"{label} inválido: use segundos ou minutos:segundos (ex.: 1:30).") from error
    if seconds < 0:
        raise OperationError(f"{label} não pode ser negativo.")
    return seconds


def parse_pages(text: str, total: int) -> list[int]:
    """Turns '1-3, 5, 8-' into zero-based page indexes."""
    pages: list[int] = []
    for chunk in (text or "").replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = re.fullmatch(r"(\d*)\s*-\s*(\d*)|(\d+)", chunk)
        if not match:
            raise OperationError(f"Intervalo de páginas inválido: {chunk!r}. Exemplo: 1-3, 5")
        if match.group(3):
            first = last = int(match.group(3))
        else:
            first = int(match.group(1) or 1)
            last = int(match.group(2) or total)
        if first < 1 or last > total or first > last:
            raise OperationError(f"O PDF tem {total} páginas; o intervalo {chunk!r} não existe.")
        pages.extend(range(first - 1, last))
    if not pages:
        raise OperationError("Informe as páginas, por exemplo: 1-3, 5")
    return pages


def _out(ctx: Context, source: Path, ext: str | None = None) -> Path:
    stem, source_ext = split_extension(source)
    return ctx.workdir / f"{stem}.{ext or source_ext.lower()}"


def _key(path: Path) -> str:
    return detect_format(path).key


def _ensure_smaller(result: Path, source: Path, what: str) -> None:
    if result.stat().st_size >= source.stat().st_size:
        raise OperationError(f"{what} já está otimizado: a versão comprimida ficaria maior que o original.")


# Images -------------------------------------------------------------------------------------

IMAGE_LEVELS = (("85", "Alta qualidade"), ("72", "Equilibrado"), ("55", "Máxima compressão"))


def image_compress(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    key = _key(source)
    quality = int(ctx.params["quality"])
    image = images.load(source)
    out = _out(ctx, source)
    exif = images.exif_without_orientation(image)
    if key == "png":
        prepared = images.prepare(image, "png")
        if quality < 85:
            method = Image.Quantize.FASTOCTREE if prepared.mode == "RGBA" else Image.Quantize.MEDIANCUT
            prepared = prepared.quantize(colors=256 if quality >= 72 else 128, method=method)
        prepared.save(out, "PNG", optimize=True)
    elif key == "tiff":
        images.prepare(image, "tiff").save(out, "TIFF", compression="tiff_adobe_deflate")
    else:
        images.save(image, out, key, quality=quality, exif=exif)
    _ensure_smaller(out, source, "A imagem")
    return [out]


def image_transform(operation: Callable[[Image.Image, dict], Image.Image]):
    def run(paths: list[Path], ctx: Context) -> list[Path]:
        source = paths[0]
        key = _key(source)
        image = images.load(source)
        exif = images.exif_without_orientation(image)
        result = operation(image, ctx.params)
        return [images.save(result, _out(ctx, source), key, exif=exif)]

    return run


def _resize(image: Image.Image, params: dict) -> Image.Image:
    value = params["size"]
    if value.endswith("%"):
        factor = int(value[:-1]) / 100
        size = (max(1, round(image.width * factor)), max(1, round(image.height * factor)))
    else:
        longest = int(value)
        if max(image.size) <= longest:
            raise OperationError(f"A imagem já é menor que {longest} px.")
        factor = longest / max(image.size)
        size = (max(1, round(image.width * factor)), max(1, round(image.height * factor)))
    return image.resize(size, Image.Resampling.LANCZOS)


def _rotate(image: Image.Image, params: dict) -> Image.Image:
    angle = int(params["angle"])
    transpose = {90: Image.Transpose.ROTATE_270, 270: Image.Transpose.ROTATE_90, 180: Image.Transpose.ROTATE_180}
    return image.transpose(transpose[angle])


def _flip(image: Image.Image, params: dict) -> Image.Image:
    return ImageOps.mirror(image) if params["direction"] == "horizontal" else ImageOps.flip(image)


def _crop(image: Image.Image, params: dict) -> Image.Image:
    ratio = params["ratio"]
    if ratio == "auto":
        corner = image.convert("RGB").getpixel((0, 0))
        background = Image.new("RGB", image.size, corner)
        difference = ImageChops.difference(image.convert("RGB"), background)
        box = ImageChops.add(difference, difference, 2.0, -12).getbbox()
        if not box or box == (0, 0, image.width, image.height):
            raise OperationError("Não há bordas uniformes para remover.")
        return image.crop(box)
    width_ratio, height_ratio = (int(part) for part in ratio.split(":"))
    target = width_ratio / height_ratio
    if image.width / image.height > target:
        new_width = round(image.height * target)
        left = (image.width - new_width) // 2
        return image.crop((left, 0, left + new_width, image.height))
    new_height = round(image.width / target)
    top = (image.height - new_height) // 2
    return image.crop((0, top, image.width, top + new_height))


def _grayscale(image: Image.Image, params: dict) -> Image.Image:
    if image.mode not in ("RGBA", "LA", "PA"):
        return ImageOps.grayscale(image.convert("RGB"))
    rgba = image.convert("RGBA")
    gray = ImageOps.grayscale(rgba.convert("RGB")).convert("RGBA")
    gray.putalpha(rgba.getchannel("A"))
    return gray


def image_strip(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    key = _key(source)
    image = images.load(source)
    clean = Image.new(image.mode, image.size)
    clean.paste(image)
    if "transparency" in image.info:
        clean.info["transparency"] = image.info["transparency"]
    return [images.save(clean, _out(ctx, source), key)]


def images_to_pdf(paths: list[Path], ctx: Context) -> list[Path]:
    pages = []
    for index, path in enumerate(paths):
        ctx.check_cancelled()
        pages.append(images.prepare(images.load(path), "pdf"))
        ctx.progress((index + 1) / len(paths) * 0.8)
    out = _out(ctx, paths[0], "pdf")
    pages[0].save(out, "PDF", resolution=150.0, save_all=True, append_images=pages[1:])
    return [out]


# Video and audio ----------------------------------------------------------------------------

VIDEO_QUALITY = (("alta", "Alta qualidade"), ("media", "Equilibrado"), ("baixa", "Máxima compressão"))
RESOLUTIONS = (("0", "Manter"), ("1080", "1080p"), ("720", "720p"), ("480", "480p"))


def _scale_filter(info: media.MediaInfo, height: int) -> list[str]:
    """Limits the short side, never upscaling."""
    if not height:
        return []
    if info.width >= info.height:
        return [f"scale=-2:'min({height},ih)'"]
    return [f"scale='min({height},iw)':-2"]


def video_compress(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    info = media.probe(source)
    out = _out(ctx, source)
    filters = _scale_filter(info, int(ctx.params["resolution"]))
    media.encode_video(ctx, source, out, _key(source), info, filters=filters, quality=ctx.params["quality"])
    _ensure_smaller(out, source, "O vídeo")
    return [out]


def _trim_window(ctx: Context, info: media.MediaInfo) -> tuple[float, float]:
    start = parse_time(ctx.params.get("start"), label="Início") or 0.0
    end = parse_time(ctx.params.get("end"), label="Fim") or info.duration
    if info.duration and start >= info.duration:
        raise OperationError(f"O início passa do fim do arquivo ({info.duration:.1f} s).")
    if end <= start:
        raise OperationError("O fim precisa ser depois do início.")
    return start, min(end, info.duration or end)


def video_trim(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    info = media.probe(source)
    start, end = _trim_window(ctx, info)
    out = _out(ctx, source)
    input_args = ["-ss", f"{start:.3f}", "-t", f"{end - start:.3f}"]
    media.encode_video(ctx, source, out, _key(source), info, input_args=input_args, duration=end - start)
    return [out]


def video_mute(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    info = media.probe(source)
    if not info.has_audio:
        raise OperationError("O vídeo já não tem áudio.")
    out = _out(ctx, source)
    media.run_ffmpeg(ctx, ["-i", source, "-map", "0:v:0", "-c:v", "copy", "-an", out], info.duration)
    return [out]


def video_resize(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    info = media.probe(source)
    height = int(ctx.params["resolution"])
    if min(info.width, info.height) <= height:
        raise OperationError(f"O vídeo já tem {min(info.width, info.height)}p ou menos.")
    out = _out(ctx, source)
    media.encode_video(ctx, source, out, _key(source), info, filters=_scale_filter(info, height))
    return [out]


def video_rotate(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    info = media.probe(source)
    rotation = {"90": ["transpose=1"], "270": ["transpose=2"], "180": ["hflip", "vflip"]}
    out = _out(ctx, source)
    media.encode_video(ctx, source, out, _key(source), info, filters=rotation[ctx.params["angle"]])
    return [out]


def video_merge(paths: list[Path], ctx: Context) -> list[Path]:
    """Concatenates clips scaled and padded to the first one's frame size."""
    infos = [media.probe(path) for path in paths]
    first = infos[0]
    target = _key(paths[0])
    width, height = first.width // 2 * 2, first.height // 2 * 2
    fps = first.fps if 1 <= first.fps <= 120 else 30
    with_audio = target != "gif" and any(info.has_audio for info in infos)
    args: list = []
    for path in paths:
        args += ["-i", path]
    chains, labels = [], []
    silence_index = len(paths)
    for index, info in enumerate(infos):
        chains.append(
            f"[{index}:v:0]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p[v{index}]"
        )
        labels.append(f"[v{index}]")
        if with_audio:
            if info.has_audio:
                chains.append(f"[{index}:a:0]aformat=sample_rates=48000:channel_layouts=stereo[a{index}]")
            else:
                args += ["-f", "lavfi", "-t", f"{info.duration:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
                chains.append(f"[{silence_index}:a]anull[a{index}]")
                silence_index += 1
            labels.append(f"[a{index}]")
    chains.append(f"{''.join(labels)}concat=n={len(paths)}:v=1:a={1 if with_audio else 0}[v]" + ("[a]" if with_audio else ""))
    out = _out(ctx, paths[0])
    maps = ["-map", "[v]"] + (["-map", "[a]"] if with_audio else [])
    if target == "gif":
        codec = ["-loop", "0"]
    else:
        codec = media.video_codec_args(target, "alta", with_audio)
    total = sum(info.duration for info in infos)
    media.run_ffmpeg(ctx, [*args, "-filter_complex", ";".join(chains), *maps, *codec, out], total)
    return [out]


def video_frames(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    info = media.probe(source)
    every = ctx.params["every"]
    if every == "cover":
        out = _out(ctx, source, "jpg")
        media.run_ffmpeg(
            ctx, ["-ss", f"{info.duration * 0.1:.3f}", "-i", source, "-frames:v", "1", "-q:v", "2", out]
        )
        return [out]
    folder = ctx.subdir("frames")
    stem, _ext = split_extension(source)
    media.run_ffmpeg(
        ctx,
        ["-i", source, "-vf", f"fps=1/{every}", "-q:v", "2", folder / f"{stem}-%04d.jpg"],
        info.duration,
    )
    frames = sorted(folder.iterdir())
    if not frames:
        raise OperationError("Nenhum quadro foi extraído.")
    return frames


def audio_trim(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    info = media.probe(source)
    start, end = _trim_window(ctx, info)
    out = _out(ctx, source)
    input_args = ["-ss", f"{start:.3f}", "-t", f"{end - start:.3f}"]
    key = _key(source)
    media.encode_audio(ctx, source, out, key, info, input_args=input_args, duration=end - start)
    return [out]


def audio_compress(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    key = _key(source)
    info = media.probe(source)
    bitrate = ctx.params["bitrate"]
    codec = {
        "mp3": "libmp3lame", "m4a": "aac", "ogg": "libvorbis", "opus": "libopus", "wma": "wmav2",
    }[key]
    out = _out(ctx, source)
    media.encode_audio(ctx, source, out, key, info, codec_args=["-c:a", codec, "-b:a", bitrate])
    _ensure_smaller(out, source, "O áudio")
    return [out]


def audio_normalize(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    info = media.probe(source)
    out = _out(ctx, source)
    key = _key(source)
    media.encode_audio(ctx, source, out, key, info, filters=["loudnorm=I=-16:TP=-1.5:LRA=11"])
    return [out]


def audio_merge(paths: list[Path], ctx: Context) -> list[Path]:
    infos = [media.probe(path) for path in paths]
    for path, info in zip(paths, infos, strict=True):
        if not info.has_audio:
            raise OperationError(f"{path.name} não tem áudio.")
    args: list = []
    for path in paths:
        args += ["-i", path]
    chains = [
        f"[{index}:a:0]aformat=sample_rates=48000:channel_layouts=stereo[a{index}]"
        for index in range(len(paths))
    ]
    chains.append("".join(f"[a{index}]" for index in range(len(paths))) + f"concat=n={len(paths)}:v=0:a=1[a]")
    target = _key(paths[0])
    out = _out(ctx, paths[0])
    total = sum(info.duration for info in infos)
    media.run_ffmpeg(
        ctx, [*args, "-filter_complex", ";".join(chains), "-map", "[a]", *media.AUDIO_CODECS[target], out], total
    )
    return [out]


SEGMENT_MUXERS = {
    "mp3": "mp3", "m4a": "ipod", "wav": "wav", "flac": "flac", "ogg": "ogg",
    "opus": "opus", "aiff": "aiff", "wma": "asf",
}


def audio_split(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    key = _key(source)
    info = media.probe(source)
    mode = ctx.params["parts"]
    if mode.startswith("x"):
        seconds = info.duration / int(mode[1:]) + 0.05
    else:
        seconds = int(mode) * 60
        if seconds >= info.duration:
            raise OperationError("O áudio é mais curto que o tamanho de cada parte.")
    folder = ctx.subdir("parts")
    stem, ext = split_extension(source)
    media.run_ffmpeg(
        ctx,
        [
            "-i", source, "-map", "0:a:0", "-vn", *media.AUDIO_CODECS[key],
            "-f", "segment", "-segment_time", f"{seconds:.3f}", "-reset_timestamps", "1",
            "-segment_format", SEGMENT_MUXERS[key], folder / f"{stem}-%02d.{ext.lower()}",
        ],
        info.duration,
    )
    return sorted(folder.iterdir())


# PDF ----------------------------------------------------------------------------------------

GS = shutil.which("gs")


def pdf_compress(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    out = _out(ctx, source)
    if GS:
        ctx.run(
            [
                GS, "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.6", f"-dPDFSETTINGS=/{ctx.params['level']}",
                "-dNOPAUSE", "-dBATCH", "-dQUIET", "-dDetectDuplicateImages=true", f"-sOutputFile={out}", source,
            ],
            error_message="O Ghostscript não conseguiu comprimir o PDF",
        )
    else:
        with _open_pdf(source) as document:
            document.save(out, garbage=4, deflate=True, clean=True)
    _ensure_smaller(out, source, "O PDF")
    return [out]


def _open_pdf(source: Path, password: str | None = None) -> pymupdf.Document:
    try:
        document = pymupdf.open(source)
    except Exception as error:
        raise OperationError(f"PDF inválido: {error}") from error
    if document.needs_pass:
        if not password or not document.authenticate(password):
            document.close()
            raise OperationError("Senha incorreta." if password else "O PDF está protegido por senha.")
    return document


def pdf_merge(paths: list[Path], ctx: Context) -> list[Path]:
    merged = pymupdf.open()
    for index, path in enumerate(paths):
        with _open_pdf(path) as document:
            merged.insert_pdf(document)
        ctx.progress((index + 1) / len(paths))
    out = _out(ctx, paths[0])
    merged.save(out, garbage=3, deflate=True)
    return [out]


def pdf_split(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    stem, _ext = split_extension(source)
    produced = []
    with _open_pdf(source) as document:
        total = len(document)
        if total < 2:
            raise OperationError("O PDF tem uma página só.")
        size = (total + 1) // 2 if ctx.params["every"] == "half" else int(ctx.params["every"])
        for first in range(0, total, size):
            part = pymupdf.open()
            part.insert_pdf(document, from_page=first, to_page=min(first + size, total) - 1)
            last = min(first + size, total)
            label = f"p{first + 1}" if last - first == 1 else f"p{first + 1}-{last}"
            out = ctx.workdir / f"{stem} {label}.pdf"
            part.save(out, garbage=3, deflate=True)
            produced.append(out)
            ctx.progress(last / total)
    return produced


def pdf_extract(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    with _open_pdf(source) as document:
        pages = parse_pages(ctx.params["pages"], len(document))
        document.select(pages)
        out = _out(ctx, source)
        document.save(out, garbage=3, deflate=True)
    return [out]


def pdf_rotate(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    angle = int(ctx.params["angle"])
    with _open_pdf(source) as document:
        for page in document:
            page.set_rotation((page.rotation + angle) % 360)
        out = _out(ctx, source)
        document.save(out, garbage=3, deflate=True)
    return [out]


def pdf_protect(paths: list[Path], ctx: Context) -> list[Path]:
    password = ctx.params.get("password") or ""
    if len(password) < 4:
        raise OperationError("Use uma senha com pelo menos 4 caracteres.")
    source = paths[0]
    with _open_pdf(source) as document:
        out = _out(ctx, source)
        document.save(
            out,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw=password,
            user_pw=password,
            permissions=pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_COPY | pymupdf.PDF_PERM_ACCESSIBILITY,
            garbage=3,
            deflate=True,
        )
    return [out]


def pdf_unlock(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    with _open_pdf(source, ctx.params.get("password")) as document:
        out = _out(ctx, source)
        document.save(out, encryption=pymupdf.PDF_ENCRYPT_NONE, garbage=3, deflate=True)
    return [out]


# Subtitles, archives, anything --------------------------------------------------------------


def subtitle_shift(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    text = (ctx.params.get("offset") or "").strip().replace(",", ".")
    try:
        offset = float(text)
    except ValueError as error:
        raise OperationError("Informe o ajuste em segundos, ex.: 1,5 ou -2") from error
    cues = subtitles.parse(source)
    for cue in cues:
        cue.start += offset
        cue.end += offset
    kept = [cue for cue in cues if cue.end > 0]
    return [subtitles.write(kept, _out(ctx, source), _key(source))]


def archive_extract(paths: list[Path], ctx: Context) -> list[Path]:
    source = paths[0]
    contents = archives.extract(ctx, source, _key(source), ctx.subdir("extracted"))
    items = list(contents.iterdir())
    if not items:
        raise OperationError("O arquivo compactado está vazio.")
    # One top-level folder becomes the result itself instead of a folder inside a folder.
    if len(items) == 1 and items[0].is_dir():
        return [items[0]]
    return [contents]


def compress_zip(paths: list[Path], ctx: Context) -> list[Path]:
    out = ctx.workdir / "compactado.zip"
    return [archives.pack(ctx, paths, out, "zip")]


def _zip_name(batch: list[Path]) -> Path:
    if len(batch) == 1:
        return batch[0]
    return batch[0].parent / "Compactado"


TOOLS: list[Tool] = [
    # images
    Tool("image-compress", "Comprimir", "zoom-out-symbolic", RASTER - {"bmp"}, image_compress,
         (Param("quality", "Nível", default="72", choices=IMAGE_LEVELS),), suffix="comprimido"),
    Tool("image-resize", "Redimensionar", "view-fullscreen-symbolic", RASTER, image_transform(_resize),
         (Param("size", "Tamanho", default="50%", choices=(
             ("75%", "75%"), ("50%", "50%"), ("25%", "25%"), ("3840", "Maior lado 3840 px"),
             ("1920", "Maior lado 1920 px"), ("1280", "Maior lado 1280 px"), ("800", "Maior lado 800 px"),
         )),), suffix="redimensionado"),
    Tool("image-crop", "Recortar", "zoom-fit-best-symbolic", RASTER, image_transform(_crop),
         (Param("ratio", "Formato", default="1:1", choices=(
             ("1:1", "Quadrado 1:1"), ("4:3", "4:3"), ("3:2", "3:2"), ("16:9", "16:9"),
             ("9:16", "Vertical 9:16"), ("4:5", "Retrato 4:5"), ("auto", "Remover bordas"),
         )),), suffix="recortado"),
    Tool("image-rotate", "Girar", "object-rotate-right-symbolic", RASTER, image_transform(_rotate),
         (ROTATION,), suffix="girado"),
    Tool("image-flip", "Espelhar", "object-flip-horizontal-symbolic", RASTER, image_transform(_flip),
         (Param("direction", "Direção", default="horizontal",
                choices=(("horizontal", "Horizontal"), ("vertical", "Vertical"))),), suffix="espelhado"),
    Tool("image-grayscale", "Preto e branco", "color-select-symbolic", RASTER, image_transform(_grayscale),
         suffix="pb"),
    Tool("image-strip", "Remover metadados", "edit-clear-all-symbolic", RASTER, image_strip,
         suffix="sem metadados"),
    Tool("images-pdf", "Juntar em PDF", "x-office-document-symbolic", RASTER | {"svg"}, images_to_pdf,
         multi=True, min_files=2, suffix="juntas"),
    # video
    Tool("video-compress", "Comprimir", "zoom-out-symbolic", VIDEO, video_compress,
         (Param("quality", "Qualidade", default="media", choices=VIDEO_QUALITY),
          Param("resolution", "Resolução", default="0", choices=RESOLUTIONS)), suffix="comprimido"),
    Tool("video-trim", "Cortar trecho", "edit-cut-symbolic", VIDEO, video_trim, TRIM, suffix="trecho"),
    Tool("video-mute", "Remover áudio", "audio-volume-muted-symbolic", MOVING, video_mute,
         suffix="sem áudio"),
    Tool("video-resize", "Redimensionar", "view-fullscreen-symbolic", VIDEO, video_resize,
         (Param("resolution", "Resolução", default="720", choices=RESOLUTIONS[1:] + (("360", "360p"),)),),
         suffix="redimensionado"),
    Tool("video-rotate", "Girar", "object-rotate-right-symbolic", VIDEO, video_rotate, (ROTATION,),
         suffix="girado"),
    Tool("video-merge", "Juntar vídeos", "list-add-symbolic", VIDEO, video_merge, multi=True, min_files=2,
         suffix="juntos"),
    Tool("video-frames", "Extrair quadros", "camera-photo-symbolic", VIDEO, video_frames,
         (Param("every", "Quadros", default="cover", choices=(
             ("cover", "Só a capa"), ("1", "1 por segundo"), ("5", "1 a cada 5 s"), ("10", "1 a cada 10 s"),
         )),), suffix="quadros"),
    # audio
    Tool("audio-trim", "Cortar trecho", "edit-cut-symbolic", AUDIO, audio_trim, TRIM, suffix="trecho"),
    Tool("audio-compress", "Comprimir", "zoom-out-symbolic", LOSSY_AUDIO, audio_compress,
         (Param("bitrate", "Taxa", default="96k",
                choices=(("128k", "128 kbps"), ("96k", "96 kbps"), ("64k", "64 kbps (voz)"))),),
         suffix="comprimido"),
    Tool("audio-normalize", "Normalizar volume", "audio-volume-high-symbolic", AUDIO, audio_normalize,
         suffix="normalizado"),
    Tool("audio-merge", "Juntar áudios", "list-add-symbolic", AUDIO, audio_merge, multi=True, min_files=2,
         suffix="juntos"),
    Tool("audio-split", "Dividir", "edit-cut-symbolic", AUDIO, audio_split,
         (Param("parts", "Partes", default="x2", choices=(
             ("x2", "2 partes iguais"), ("x3", "3 partes iguais"), ("x4", "4 partes iguais"),
             ("1", "A cada 1 minuto"), ("5", "A cada 5 minutos"), ("10", "A cada 10 minutos"),
         )),), suffix="partes"),
    # pdf
    Tool("pdf-compress", "Comprimir", "zoom-out-symbolic", PDF, pdf_compress,
         (Param("level", "Nível", default="ebook", choices=(
             ("printer", "Alta qualidade"), ("ebook", "Equilibrado"), ("screen", "Máxima compressão"),
         )),), suffix="comprimido"),
    Tool("pdf-merge", "Juntar PDFs", "list-add-symbolic", PDF, pdf_merge, multi=True, min_files=2,
         suffix="juntos"),
    Tool("pdf-split", "Dividir", "edit-cut-symbolic", PDF, pdf_split,
         (Param("every", "Dividir", default="1", choices=(
             ("1", "Uma página por arquivo"), ("2", "A cada 2 páginas"), ("5", "A cada 5 páginas"),
             ("10", "A cada 10 páginas"), ("half", "Ao meio"),
         )),), suffix="partes"),
    Tool("pdf-extract", "Extrair páginas", "edit-copy-symbolic", PDF, pdf_extract,
         (Param("pages", "Páginas", "text", "1", placeholder="ex.: 1-3, 5"),), suffix="páginas"),
    Tool("pdf-rotate", "Girar páginas", "object-rotate-right-symbolic", PDF, pdf_rotate, (ROTATION,),
         suffix="girado"),
    Tool("pdf-protect", "Proteger com senha", "channel-secure-symbolic", PDF, pdf_protect,
         (Param("password", "Senha", "password"),), suffix="protegido"),
    Tool("pdf-unlock", "Remover senha", "channel-insecure-symbolic", PDF, pdf_unlock,
         (Param("password", "Senha atual", "password"),), suffix="sem senha"),
    # others
    Tool("subtitle-shift", "Ajustar tempo", "preferences-system-time-symbolic", SUBTITLES, subtitle_shift,
         (Param("offset", "Segundos (+ atrasa, − adianta)", "text", "1", placeholder="ex.: 1,5 ou -2"),),
         suffix="ajustada"),
    Tool("archive-extract", "Extrair", "folder-open-symbolic", ARCHIVES, archive_extract),
    Tool("compress-zip", "Compactar em ZIP", "package-x-generic-symbolic", None, compress_zip, multi=True,
         name_from=_zip_name),
]

TOOLS_BY_ID = {tool.id: tool for tool in TOOLS}


def tools_for(paths: list[Path]) -> list[Tool]:
    return [tool for tool in TOOLS if tool.applies_to(paths)]
