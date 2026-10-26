"""Known file formats, grouped by category, and detection by file name."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileFormat:
    key: str
    label: str
    category: str
    extensions: tuple[str, ...]

    @property
    def extension(self) -> str:
        return self.extensions[0]


CATEGORY_LABELS = {
    "image": "Imagem",
    "audio": "Áudio",
    "video": "Vídeo",
    "pdf": "PDF",
    "document": "Documento",
    "slides": "Apresentação",
    "spreadsheet": "Planilha",
    "subtitle": "Legenda",
    "archive": "Arquivo compactado",
}

CATEGORY_ICONS = {
    "image": "image-x-generic-symbolic",
    "audio": "audio-x-generic-symbolic",
    "video": "video-x-generic-symbolic",
    "pdf": "x-office-document-symbolic",
    "document": "x-office-document-symbolic",
    "slides": "x-office-presentation-symbolic",
    "spreadsheet": "x-office-spreadsheet-symbolic",
    "subtitle": "media-view-subtitles-symbolic",
    "archive": "package-x-generic-symbolic",
}

_FORMATS = [
    FileFormat("jpg", "JPG", "image", ("jpg", "jpeg", "jfif", "jpe")),
    FileFormat("png", "PNG", "image", ("png",)),
    FileFormat("webp", "WebP", "image", ("webp",)),
    FileFormat("heic", "HEIC", "image", ("heic", "heif")),
    FileFormat("tiff", "TIFF", "image", ("tiff", "tif")),
    FileFormat("avif", "AVIF", "image", ("avif",)),
    FileFormat("bmp", "BMP", "image", ("bmp",)),
    FileFormat("svg", "SVG", "image", ("svg",)),
    FileFormat("mp3", "MP3", "audio", ("mp3",)),
    FileFormat("m4a", "M4A", "audio", ("m4a",)),
    FileFormat("wav", "WAV", "audio", ("wav",)),
    FileFormat("flac", "FLAC", "audio", ("flac",)),
    FileFormat("ogg", "OGG", "audio", ("ogg", "oga")),
    FileFormat("opus", "Opus", "audio", ("opus",)),
    FileFormat("aiff", "AIFF", "audio", ("aiff", "aif")),
    FileFormat("wma", "WMA", "audio", ("wma",)),
    FileFormat("mp4", "MP4", "video", ("mp4", "m4v")),
    FileFormat("mov", "MOV", "video", ("mov",)),
    FileFormat("mkv", "MKV", "video", ("mkv",)),
    FileFormat("webm", "WebM", "video", ("webm",)),
    FileFormat("avi", "AVI", "video", ("avi",)),
    FileFormat("wmv", "WMV", "video", ("wmv",)),
    FileFormat("gif", "GIF", "video", ("gif",)),
    FileFormat("pdf", "PDF", "pdf", ("pdf",)),
    FileFormat("docx", "DOCX", "document", ("docx",)),
    FileFormat("doc", "DOC", "document", ("doc",)),
    FileFormat("odt", "ODT", "document", ("odt",)),
    FileFormat("pages", "Pages", "document", ("pages",)),
    FileFormat("md", "Markdown", "document", ("md", "markdown")),
    FileFormat("txt", "TXT", "document", ("txt", "text")),
    FileFormat("epub", "EPUB", "document", ("epub",)),
    FileFormat("rtf", "RTF", "document", ("rtf",)),
    FileFormat("html", "HTML", "document", ("html", "htm")),
    FileFormat("pptx", "PPTX", "slides", ("pptx",)),
    FileFormat("ppt", "PPT", "slides", ("ppt",)),
    FileFormat("odp", "ODP", "slides", ("odp",)),
    FileFormat("key", "Keynote", "slides", ("key",)),
    FileFormat("xlsx", "XLSX", "spreadsheet", ("xlsx",)),
    FileFormat("xls", "XLS", "spreadsheet", ("xls",)),
    FileFormat("ods", "ODS", "spreadsheet", ("ods",)),
    FileFormat("csv", "CSV", "spreadsheet", ("csv",)),
    FileFormat("tsv", "TSV", "spreadsheet", ("tsv", "tab")),
    FileFormat("numbers", "Numbers", "spreadsheet", ("numbers",)),
    FileFormat("srt", "SRT", "subtitle", ("srt",)),
    FileFormat("vtt", "VTT", "subtitle", ("vtt",)),
    FileFormat("zip", "ZIP", "archive", ("zip",)),
    FileFormat("tar", "TAR", "archive", ("tar",)),
    FileFormat("tgz", "TAR.GZ", "archive", ("tar.gz", "tgz")),
    FileFormat("gz", "GZIP", "archive", ("gz",)),
    FileFormat("rar", "RAR", "archive", ("rar",)),
    FileFormat("7z", "7Z", "archive", ("7z",)),
]

FORMATS: dict[str, FileFormat] = {fmt.key: fmt for fmt in _FORMATS}

# Longest extensions first, so "tar.gz" wins over "gz".
_BY_EXTENSION = sorted(
    ((ext, fmt) for fmt in _FORMATS for ext in fmt.extensions),
    key=lambda item: -len(item[0]),
)


def split_extension(path: Path) -> tuple[str, str]:
    """Returns (stem, extension) understanding compound extensions like .tar.gz."""
    name = path.name
    lower = name.lower()
    for ext, _fmt in _BY_EXTENSION:
        if lower.endswith("." + ext) and len(name) > len(ext) + 1:
            return name[: -(len(ext) + 1)], name[-len(ext) :]
    if "." in name.strip("."):
        stem, _, ext = name.rpartition(".")
        return stem, ext
    return name, ""


def detect_format(path: Path) -> FileFormat | None:
    """Identifies the format by extension; folders and unknown files return None."""
    if path.is_dir():
        return None
    lower = path.name.lower()
    for ext, fmt in _BY_EXTENSION:
        if lower.endswith("." + ext):
            return fmt
    return None
