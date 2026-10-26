"""What each wheel offers for a selection, and the config shared with the Shell extension."""

import json
from pathlib import Path

from mexerica.config import Config, config_path
from mexerica.ui.model import describe, options_for


def touch(folder: Path, name: str) -> Path:
    path = folder / name
    path.write_bytes(b"x")
    return path


def test_convert_wheel_for_one_image(tmp_path):
    options = options_for([touch(tmp_path, "a.png")], "convert")
    assert [option.id for option in options] == ["jpg", "webp", "heic", "tiff", "avif", "bmp", "pdf"]
    assert options[0].title == "Converter para JPG"


def test_tools_wheel_depends_on_selection(tmp_path):
    single = {option.id for option in options_for([touch(tmp_path, "a.pdf")], "tools")}
    assert "pdf-merge" not in single and "pdf-compress" in single
    pair = {option.id for option in options_for([touch(tmp_path, "a.pdf"), touch(tmp_path, "b.pdf")], "tools")}
    assert "pdf-merge" in pair


def test_actions_wheel_accepts_folders_and_mixed(tmp_path):
    folder = tmp_path / "pasta"
    folder.mkdir()
    selection = [folder, touch(tmp_path, "x.mp3")]
    assert len(options_for(selection, "actions")) == 6
    assert options_for(selection, "convert") == []
    assert [option.id for option in options_for(selection, "tools")] == ["compress-zip"]


def test_describe(tmp_path):
    assert describe([]) == "Solte arquivos aqui"
    assert describe([touch(tmp_path, "nota.pdf")]) == "nota.pdf"
    assert describe([touch(tmp_path, "a.pdf"), touch(tmp_path, "b.pdf")]) == "2 PDF"
    assert describe([touch(tmp_path, "a.pdf"), touch(tmp_path, "b.mp3")]) == "2 itens"


def test_config_roundtrip_and_extension_format(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config = Config.load()
    assert config.wheel_keys == {"convert": "shift", "tools": "control", "actions": "alt"}
    config.wheel_keys = {"convert": "alt", "tools": "control", "actions": "shift"}
    config.save()
    # The Shell extension reads wheel_keys straight from this JSON.
    assert json.loads(config_path().read_text())["wheel_keys"]["convert"] == "alt"
    assert Config.load().wheel_for_key("shift") == "actions"
