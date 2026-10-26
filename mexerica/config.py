"""User settings in ~/.config/mexerica/config.json, shared with the GNOME Shell extension."""

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

MODIFIERS = ("shift", "control", "alt")
WHEELS = ("convert", "tools", "actions")


def config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "mexerica" / "config.json"


@dataclass
class Config:
    # Which key, held while dragging, opens each wheel.
    wheel_keys: dict = field(
        default_factory=lambda: {"convert": "shift", "tools": "control", "actions": "alt"}
    )
    output_dir: str = ""  # empty: next to the original file
    open_folder_after: bool = False
    notify: bool = True
    terminal: str = ""  # empty: detect
    last_params: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Config":
        try:
            data = json.loads(config_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        config = cls()
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        keys = {**cls().wheel_keys, **(config.wheel_keys or {})}
        config.wheel_keys = {wheel: keys[wheel] for wheel in WHEELS}
        return config

    def save(self) -> None:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def wheel_for_key(self, modifier: str) -> str | None:
        for wheel, key in self.wheel_keys.items():
            if key == modifier:
                return wheel
        return None
