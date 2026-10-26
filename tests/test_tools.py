"""Each tool on real samples: output exists, is valid and actually changed what it claims."""

import shutil
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from mexerica.core import jobs
from mexerica.core.context import OperationError
from mexerica.core.engines import media, subtitles
from mexerica.core.tools import TOOLS, TOOLS_BY_ID, parse_pages, parse_time, tools_for

from . import samples, validate


@pytest.fixture(scope="module")
def sample_files(tmp_path_factory) -> dict[str, Path]:
    return samples.build(tmp_path_factory.mktemp("tool-samples"))


def run(tool_id, sources, tmp_path, **params):
    tool = TOOLS_BY_ID[tool_id]
    merged = {**tool.default_params(), **params}
    return jobs.run_tool(tool, sources, merged, output_dir=str(tmp_path))


def test_tool_catalogue():
    assert len(TOOLS) >= 26
    assert len({tool.id for tool in TOOLS}) == len(TOOLS)


def test_parse_helpers():
    assert parse_time("1:30", label="x") == 90
    assert parse_time("1:02:03", label="x") == 3723
    assert parse_time("2,5", label="x") == 2.5
    assert parse_time("", label="x") is None
    assert parse_pages("1-3, 5", 6) == [0, 1, 2, 4]
    assert parse_pages("4-", 6) == [3, 4, 5]
    with pytest.raises(OperationError):
        parse_pages("7", 6)


def test_tools_for_selection(sample_files):
    image_tools = {tool.id for tool in tools_for([sample_files["png"]])}
    assert {"image-compress", "image-crop", "compress-zip"} <= image_tools
    assert "images-pdf" not in image_tools
    pair = {tool.id for tool in tools_for([sample_files["png"], sample_files["jpg"]])}
    assert "images-pdf" in pair
    mixed = {tool.id for tool in tools_for([sample_files["png"], sample_files["mp3"]])}
    assert mixed == {"compress-zip"}


@pytest.mark.parametrize("key", ["jpg", "png", "webp"])
def test_image_compress(sample_files, tmp_path, key):
    big = tmp_path / f"grande.{key}"
    noise = Image.effect_noise((900, 600), 60).convert("RGB")
    noise.save(big, quality=100) if key != "png" else noise.save(big)
    result = run("image-compress", [big], tmp_path, quality="55")[0]
    assert result.name == f"grande (comprimido).{key}"
    assert result.stat().st_size < big.stat().st_size


@pytest.mark.parametrize(
    ("tool_id", "params", "expected_size"),
    [
        ("image-resize", {"size": "50%"}, (160, 100)),
        ("image-rotate", {"angle": "90"}, (200, 320)),
        ("image-crop", {"ratio": "1:1"}, (200, 200)),
        ("image-crop", {"ratio": "16:9"}, (320, 180)),
        ("image-flip", {"direction": "vertical"}, (320, 200)),
        ("image-grayscale", {}, (320, 200)),
        ("image-strip", {}, (320, 200)),
    ],
)
def test_image_transforms(sample_files, tmp_path, tool_id, params, expected_size):
    result = run(tool_id, [sample_files["png"]], tmp_path, **params)[0]
    with Image.open(result) as image:
        assert image.size == expected_size


def test_image_rotate_is_clockwise(tmp_path):
    source = tmp_path / "seta.png"
    image = Image.new("RGB", (20, 10), "white")
    image.putpixel((0, 0), (255, 0, 0))
    image.save(source)
    result = run("image-rotate", [source], tmp_path, angle="90")[0]
    with Image.open(result) as rotated:
        # Top-left goes to top-right on a clockwise turn.
        assert rotated.getpixel((rotated.width - 1, 0)) == (255, 0, 0)


def test_image_strip_removes_exif(tmp_path):
    source = tmp_path / "foto.jpg"
    image = Image.new("RGB", (40, 40), "blue")
    exif = Image.Exif()
    exif[0x010F] = "CameraMaker"
    image.save(source, exif=exif.tobytes())
    result = run("image-strip", [source], tmp_path)[0]
    with Image.open(result) as clean:
        assert 0x010F not in clean.getexif()


def test_crop_auto_removes_border(tmp_path):
    source = tmp_path / "borda.png"
    image = Image.new("RGB", (100, 80), "white")
    image.paste((0, 0, 0), (20, 10, 70, 60))
    image.save(source)
    result = run("image-crop", [source], tmp_path, ratio="auto")[0]
    with Image.open(result) as cropped:
        assert cropped.size == (50, 50)


def test_images_to_pdf(sample_files, tmp_path):
    result = run("images-pdf", [sample_files["png"], sample_files["jpg"], sample_files["svg"]], tmp_path)[0]
    with pymupdf.open(result) as document:
        assert len(document) == 3


def test_video_trim(sample_files, tmp_path):
    result = run("video-trim", [sample_files["mp4"]], tmp_path, start="0:00.5", end="1.5")[0]
    assert 0.8 <= media.probe(result).duration <= 1.2


def test_video_mute(sample_files, tmp_path):
    result = run("video-mute", [sample_files["mp4"]], tmp_path)[0]
    info = media.probe(result)
    assert info.has_video and not info.has_audio


def test_video_rotate_and_resize(sample_files, tmp_path):
    rotated = media.probe(run("video-rotate", [sample_files["mp4"]], tmp_path, angle="90")[0])
    assert (rotated.width, rotated.height) == (240, 320)
    with pytest.raises(OperationError):
        run("video-resize", [sample_files["mp4"]], tmp_path, resolution="480")


def test_video_compress_and_frames(sample_files, tmp_path):
    source = tmp_path / "grande.mp4"
    media.run_ffmpeg(
        jobs_context(tmp_path),
        ["-f", "lavfi", "-i", "testsrc2=duration=3:size=1280x720:rate=30", "-c:v", "libx264", "-crf", "8", source],
    )
    result = run("video-compress", [source], tmp_path, quality="baixa", resolution="480")[0]
    info = media.probe(result)
    assert info.height == 480 and result.stat().st_size < source.stat().st_size
    frames = run("video-frames", [sample_files["mp4"]], tmp_path, every="1")[0]
    assert frames.is_dir() and len(list(frames.iterdir())) >= 2
    cover = run("video-frames", [sample_files["mp4"]], tmp_path, every="cover")[0]
    assert cover.suffix == ".jpg"


def test_video_merge(sample_files, tmp_path):
    result = run("video-merge", [sample_files["mp4"], sample_files["mkv"], sample_files["gif"]], tmp_path)[0]
    info = media.probe(result)
    assert result.suffix == ".mp4" and info.has_audio
    assert 5.5 <= info.duration <= 6.6


def test_audio_tools(sample_files, tmp_path):
    trimmed = run("audio-trim", [sample_files["mp3"]], tmp_path, start="0.5", end="")[0]
    assert 1.3 <= media.probe(trimmed).duration <= 1.7
    normalized = run("audio-normalize", [sample_files["wav"]], tmp_path)[0]
    validate.check(normalized, "wav")
    merged = run("audio-merge", [sample_files["mp3"], sample_files["flac"]], tmp_path)[0]
    assert 3.8 <= media.probe(merged).duration <= 4.3
    parts = run("audio-split", [sample_files["ogg"]], tmp_path, parts="x2")[0]
    assert len(list(parts.iterdir())) == 2


def test_audio_compress(tmp_path):
    source = tmp_path / "alto.mp3"
    media.run_ffmpeg(
        jobs_context(tmp_path),
        ["-f", "lavfi", "-i", "anoisesrc=duration=4", "-c:a", "libmp3lame", "-b:a", "320k", source],
    )
    result = run("audio-compress", [source], tmp_path, bitrate="64k")[0]
    assert result.stat().st_size < source.stat().st_size / 3


def test_pdf_tools(sample_files, tmp_path):
    pdf = sample_files["pdf"]
    merged = run("pdf-merge", [pdf, pdf], tmp_path)[0]
    with pymupdf.open(merged) as document:
        assert len(document) == 4
    parts = run("pdf-split", [merged], tmp_path, every="1")[0]
    assert sorted(path.name for path in parts.iterdir())[0].endswith("p1.pdf")
    assert len(list(parts.iterdir())) == 4
    extracted = run("pdf-extract", [merged], tmp_path, pages="2-3")[0]
    with pymupdf.open(extracted) as document:
        assert len(document) == 2
    rotated = run("pdf-rotate", [pdf], tmp_path, angle="90")[0]
    with pymupdf.open(rotated) as document:
        assert document[0].rotation == 90


def test_pdf_password_roundtrip(sample_files, tmp_path):
    locked = run("pdf-protect", [sample_files["pdf"]], tmp_path, password="laranja")[0]
    with pymupdf.open(locked) as document:
        assert document.needs_pass
    with pytest.raises(OperationError, match="Senha incorreta"):
        run("pdf-unlock", [locked], tmp_path, password="errada")
    unlocked = run("pdf-unlock", [locked], tmp_path, password="laranja")[0]
    with pymupdf.open(unlocked) as document:
        assert not document.needs_pass and len(document) == 2


def test_pdf_compress(tmp_path):
    source = tmp_path / "fotos.pdf"
    document = pymupdf.open()
    noise = tmp_path / "ruido.png"
    Image.effect_noise((1600, 1600), 80).convert("RGB").save(noise)
    for _ in range(2):
        document.new_page().insert_image(pymupdf.Rect(0, 0, 595, 842), filename=noise)
    document.save(source)
    result = run("pdf-compress", [source], tmp_path, level="screen")[0]
    assert result.stat().st_size < source.stat().st_size


def test_subtitle_shift(sample_files, tmp_path):
    result = run("subtitle-shift", [sample_files["srt"]], tmp_path, offset="-1,5")[0]
    cues = subtitles.parse(result)
    assert cues[0].start == 0 and cues[0].end == 1.0


@pytest.mark.parametrize("key", ["zip", "tar", "tgz", "gz", "7z"])
def test_archive_extract(sample_files, tmp_path, key):
    result = run("archive-extract", [sample_files[key]], tmp_path)[0]
    texts = {path.name for path in result.rglob("*.txt")} | ({result.name} if result.is_file() else set())
    assert texts & {"leia.txt"}


def test_compress_zip_mixed(sample_files, tmp_path):
    folder = tmp_path / "Fotos"
    folder.mkdir()
    shutil.copy(sample_files["png"], folder)
    single = run("compress-zip", [folder], tmp_path)[0]
    assert single.name == "Fotos.zip"
    many = run("compress-zip", [folder, sample_files["mp3"]], tmp_path)[0]
    assert many.name == "Compactado.zip"
    validate.check(many, "zip")


def jobs_context(tmp_path):
    from mexerica.core.context import Context

    return Context(workdir=tmp_path)
