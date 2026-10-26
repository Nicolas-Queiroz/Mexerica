"""What each wheel offers for a selection of files (no GTK here, so it is unit-testable)."""

from dataclasses import dataclass
from pathlib import Path

from ..core import conversions
from ..core.actions import ACTIONS
from ..core.formats import CATEGORY_ICONS, FORMATS, detect_format
from ..core.tools import tools_for

WHEEL_TITLES = {"convert": "Converter", "tools": "Ferramentas", "actions": "Ações"}
WHEEL_ICONS = {
    "convert": "media-playlist-repeat-symbolic",
    "tools": "applications-engineering-symbolic",
    "actions": "view-more-horizontal-symbolic",
}


@dataclass(frozen=True)
class WheelOption:
    kind: str  # convert | tool | action
    id: str
    short: str  # text inside the segment
    title: str  # text in the hub while hovering
    icon: str


def options_for(paths: list[Path], wheel: str) -> list[WheelOption]:
    if not paths:
        return []
    if wheel == "convert":
        return [
            WheelOption(
                "convert",
                target,
                FORMATS[target].label,
                f"Converter para {FORMATS[target].label}",
                CATEGORY_ICONS[FORMATS[target].category],
            )
            for target in conversions.targets_for(paths)
        ]
    if wheel == "tools":
        return [
            WheelOption("tool", tool.id, tool.label, tool.label, tool.icon) for tool in tools_for(paths)
        ]
    return [
        WheelOption("action", action.id, action.label, action.label, action.icon) for action in ACTIONS
    ]


def describe(paths: list[Path]) -> str:
    """Hub caption: the file name, or a count with the shared type."""
    if not paths:
        return "Solte arquivos aqui"
    if len(paths) == 1:
        return paths[0].name
    formats = {detect_format(path).label if detect_format(path) else "itens" for path in paths}
    kind = formats.pop() if len(formats) == 1 else "itens"
    return f"{len(paths)} {kind}"
