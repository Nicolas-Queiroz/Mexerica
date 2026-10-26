"""SRT and WebVTT subtitles, parsed and written in pure Python."""

import re
from dataclasses import dataclass
from pathlib import Path

from ..context import Context, OperationError
from .sheets import read_text

CONVERSIONS = {"srt": ["vtt", "txt"], "vtt": ["srt", "txt"]}

_TIMING = re.compile(
    r"(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{1,3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{1,3})"
)


@dataclass
class Cue:
    start: float
    end: float
    text: str


def _seconds(hours, minutes, seconds, millis) -> float:
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(millis.ljust(3, "0")) / 1000


def parse(source: Path) -> list[Cue]:
    """Reads SRT or VTT cues, skipping VTT headers, NOTE and STYLE blocks."""
    text = read_text(source).replace("\r\n", "\n").replace("\r", "\n")
    cues = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line for line in block.strip("\n").split("\n")]
        for index, line in enumerate(lines):
            match = _TIMING.search(line)
            if match:
                groups = match.groups()
                body = "\n".join(lines[index + 1 :]).strip()
                cues.append(Cue(_seconds(*groups[:4]), _seconds(*groups[4:]), body))
                break
    if not cues:
        raise OperationError("Nenhuma legenda encontrada no arquivo.")
    return cues


def _timestamp(value: float, separator: str) -> str:
    value = max(0.0, value)
    millis = round(value * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    seconds, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{millis:03d}"


def write(cues: list[Cue], out: Path, target: str) -> Path:
    if target == "txt":
        content = "\n".join(re.sub(r"<[^>]+>", "", cue.text) for cue in cues) + "\n"
    elif target == "vtt":
        blocks = [
            f"{_timestamp(cue.start, '.')} --> {_timestamp(cue.end, '.')}\n{cue.text}" for cue in cues
        ]
        content = "WEBVTT\n\n" + "\n\n".join(blocks) + "\n"
    else:
        blocks = [
            f"{number}\n{_timestamp(cue.start, ',')} --> {_timestamp(cue.end, ',')}\n{cue.text}"
            for number, cue in enumerate(cues, start=1)
        ]
        content = "\n\n".join(blocks) + "\n"
    out.write_text(content, encoding="utf-8")
    return out


def convert(source: Path, source_key: str, target: str, ctx: Context) -> list[Path]:
    return [write(parse(source), ctx.workdir / f"{source.stem}.{target}", target)]
