"""IDs repeated across the app, the Shell extension and the scripts stay in sync; the Pix code is valid."""

import json
import re
from pathlib import Path

import cv2
import numpy

from mexerica import APP_ID, donate
from mexerica.integration import EXTENSION_UUID

REPO = Path(__file__).resolve().parent.parent
EXTENSION = REPO / "gnome-extension" / EXTENSION_UUID


def test_extension_matches_app():
    metadata = json.loads((EXTENSION / "metadata.json").read_text())
    assert metadata["uuid"] == EXTENSION_UUID
    source = (EXTENSION / "extension.js").read_text()
    assert f"const APP_ID = '{APP_ID}';" in source
    assert f"const OBJECT_PATH = '/{APP_ID.replace('.', '/')}';" in source
    assert metadata["donations"]["custom"] == donate.DONATE_URL


def test_scripts_and_icons_use_the_same_ids():
    for script in ("install.sh", "uninstall.sh"):
        text = (REPO / script).read_text()
        assert f'APP_ID="{APP_ID}"' in text and f'UUID="{EXTENSION_UUID}"' in text
    icons = REPO / "mexerica" / "data" / "icons" / "hicolor"
    assert (icons / "scalable" / "apps" / f"{APP_ID}.svg").is_file()
    assert (icons / "symbolic" / "apps" / f"{APP_ID}-symbolic.svg").is_file()


def test_pix_payload_is_a_valid_static_br_code():
    assert donate.payload_is_valid()
    assert donate.PIX_KEY in donate.PIX_PAYLOAD
    # Static code without amount (no tag 54): the donor types any value.
    assert not re.search(r"5303986540", donate.PIX_PAYLOAD)
    assert not donate.payload_is_valid(donate.PIX_PAYLOAD[:-1] + "0")


def test_pix_qr_decodes_to_the_payload():
    image = cv2.imdecode(numpy.frombuffer(donate.qr_png(), numpy.uint8), cv2.IMREAD_COLOR)
    decoded, _points, _ = cv2.QRCodeDetector().detectAndDecode(image)
    assert decoded == donate.PIX_PAYLOAD


def test_readme_shows_the_same_pix():
    readme = (REPO / "README.md").read_text()
    assert donate.PIX_PAYLOAD in readme and donate.PIX_KEY in readme
    assert "## Apoie com Pix" in readme
