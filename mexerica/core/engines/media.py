"""Audio and video through the static ffmpeg build shipped by imageio-ffmpeg."""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg

from ..context import Context, OperationError

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

AUDIO = ["mp3", "m4a", "wav", "flac", "ogg", "opus", "aiff", "wma"]
VIDEO = ["mp4", "mov", "mkv", "webm", "avi", "wmv", "gif"]
AUDIO_FROM_VIDEO = ["mp3", "m4a"]

CONVERSIONS = {source: [target for target in AUDIO if target != source] for source in AUDIO}
CONVERSIONS.update(
    {
        source: [target for target in VIDEO if target != source] + AUDIO_FROM_VIDEO
        for source in VIDEO
        if source != "gif"
    }
)
CONVERSIONS["gif"] = [target for target in VIDEO if target != "gif"]

AUDIO_CODECS = {
    "mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
    "m4a": ["-c:a", "aac", "-b:a", "192k"],
    "wav": ["-c:a", "pcm_s16le"],
    "flac": ["-c:a", "flac"],
    "ogg": ["-c:a", "libvorbis", "-q:a", "5"],
    "opus": ["-c:a", "libopus", "-b:a", "128k"],
    "aiff": ["-c:a", "pcm_s16be"],
    "wma": ["-c:a", "wmav2", "-b:a", "192k"],
}

_H264 = ["-c:v", "libx264", "-preset", "medium", "-crf", "{crf}", "-pix_fmt", "yuv420p"]
VIDEO_CODECS = {
    "mp4": (_H264 + ["-movflags", "+faststart"], ["-c:a", "aac", "-b:a", "160k"]),
    "mov": (_H264 + ["-movflags", "+faststart"], ["-c:a", "aac", "-b:a", "160k"]),
    "mkv": (_H264, ["-c:a", "aac", "-b:a", "160k"]),
    "webm": (
        [
            "-c:v", "libvpx-vp9", "-crf", "{vp9_crf}", "-b:v", "0", "-row-mt", "1",
            "-deadline", "good", "-cpu-used", "4", "-pix_fmt", "yuv420p",
        ],
        ["-c:a", "libopus", "-b:a", "128k"],
    ),
    "avi": (["-c:v", "mpeg4", "-q:v", "{qscale}"], ["-c:a", "libmp3lame", "-q:a", "4"]),
    "wmv": (["-c:v", "wmv2", "-q:v", "{qscale}"], ["-c:a", "wmav2", "-b:a", "160k"]),
}
QUALITY = {
    "alta": {"crf": 23, "vp9_crf": 32, "qscale": 4},
    "media": {"crf": 28, "vp9_crf": 38, "qscale": 8},
    "baixa": {"crf": 32, "vp9_crf": 44, "qscale": 14},
}
EVEN_SIZE = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
GIF_FILTER = (
    "fps={fps},scale='min({width},iw)':-1:flags=lanczos,split[a][b];"
    "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4"
)


@dataclass
class MediaInfo:
    duration: float
    has_video: bool
    has_audio: bool
    width: int
    height: int
    fps: float


def probe(path: Path) -> MediaInfo:
    """Reads duration and streams from ffmpeg's banner (no ffprobe in the static build)."""
    result = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        errors="replace",
        stdin=subprocess.DEVNULL,
    )
    banner = result.stderr
    if "Invalid data found" in banner or "No such file" in banner:
        raise OperationError("O arquivo de mídia está corrompido ou não é suportado.")
    duration = 0.0
    match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", banner)
    if match:
        hours, minutes, seconds = match.groups()
        duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    video_lines = [
        line for line in banner.splitlines()
        if "Video:" in line and "attached pic" not in line
    ]
    width = height = 0
    fps = 0.0
    if video_lines:
        size = re.search(r", (\d{2,5})x(\d{2,5})", video_lines[0])
        if size:
            width, height = int(size.group(1)), int(size.group(2))
        rate = re.search(r"([\d.]+) (?:fps|tbr)", video_lines[0])
        if rate:
            fps = float(rate.group(1))
    return MediaInfo(
        duration=duration,
        has_video=bool(video_lines),
        has_audio="Audio:" in banner,
        width=width,
        height=height,
        fps=fps,
    )


def run_ffmpeg(ctx: Context, args: list, duration: float = 0.0) -> None:
    """Runs ffmpeg reporting progress from its machine-readable -progress output."""

    def on_line(line: str) -> None:
        if duration and line.startswith("out_time_us="):
            try:
                ctx.progress(int(line.split("=", 1)[1]) / 1_000_000 / duration)
            except ValueError:
                pass

    ctx.run(
        [FFMPEG, "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", *args],
        on_line=on_line,
        error_message="O ffmpeg não conseguiu processar o arquivo",
    )


def video_codec_args(target: str, quality: str = "alta", with_audio: bool = True) -> list[str]:
    values = QUALITY[quality]
    video_args, audio_args = VIDEO_CODECS[target]
    return [arg.format(**values) for arg in video_args] + (audio_args if with_audio else [])


def encode_video(
    ctx: Context,
    source: Path,
    out: Path,
    target: str,
    info: MediaInfo,
    *,
    filters: list[str] | None = None,
    quality: str = "alta",
    input_args: list[str] | None = None,
    keep_audio: bool = True,
    duration: float | None = None,
) -> Path:
    """Re-encodes video into the target container with the first video and audio streams."""
    chain = list(filters or [])
    if target == "gif":
        width = 640 if quality == "alta" else 480
        fps = 12 if quality == "alta" else 10
        gif = GIF_FILTER.format(fps=fps, width=width)
        vf = ",".join(chain + [gif]) if chain else gif
        args = [*(input_args or []), "-i", source, "-map", "0:v:0", "-vf", vf, "-loop", "0", out]
    else:
        chain.append(EVEN_SIZE)
        with_audio = keep_audio and info.has_audio
        audio_map = ["-map", "0:a:0"] if with_audio else ["-an"]
        args = [
            *(input_args or []), "-i", source, "-map", "0:v:0", *audio_map,
            "-vf", ",".join(chain), *video_codec_args(target, quality, with_audio),
            "-map_metadata", "0", out,
        ]
    run_ffmpeg(ctx, args, duration if duration is not None else info.duration)
    return out


def encode_audio(
    ctx: Context,
    source: Path,
    out: Path,
    target: str,
    info: MediaInfo,
    *,
    filters: list[str] | None = None,
    codec_args: list[str] | None = None,
    input_args: list[str] | None = None,
    duration: float | None = None,
) -> Path:
    if not info.has_audio:
        raise OperationError("O arquivo não tem faixa de áudio.")
    args = [*(input_args or []), "-i", source, "-map", "0:a:0", "-vn", "-map_metadata", "0"]
    if filters:
        args += ["-af", ",".join(filters)]
    args += [*(codec_args or AUDIO_CODECS[target]), out]
    run_ffmpeg(ctx, args, duration if duration is not None else info.duration)
    return out


def convert(source: Path, source_key: str, target: str, ctx: Context) -> list[Path]:
    info = probe(source)
    out = ctx.workdir / f"{source.stem}.{target}"
    if target in AUDIO:
        return [encode_audio(ctx, source, out, target, info)]
    if not info.has_video:
        raise OperationError("O arquivo não tem faixa de vídeo.")
    return [encode_video(ctx, source, out, target, info)]
