#!/bin/bash
# Builds the zip uploaded to extensions.gnome.org (dist/<uuid>.shell-extension.zip).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
UUID="mexerica@nicolas-queiroz.github.io"
mkdir -p "$REPO/dist"
gnome-extensions pack "$REPO/gnome-extension/$UUID" --extra-source=LICENSE --out-dir="$REPO/dist" --force
echo "$REPO/dist/$UUID.shell-extension.zip"
