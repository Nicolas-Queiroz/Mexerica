#!/bin/bash
# Removes everything install.sh put in the home folder (the project folder stays).
set -uo pipefail

APP_ID="io.github.Nicolas_Queiroz.Mexerica"
UUID="mexerica@nicolas-queiroz.github.io"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
SCRIPT_NAME="Abrir na roda do Mexerica"

command -v gnome-extensions >/dev/null && gnome-extensions disable "$UUID" 2>/dev/null
if command -v gsettings >/dev/null; then
  current="$(gsettings get org.gnome.shell enabled-extensions 2>/dev/null || true)"
  if [[ "$current" == *"$UUID"* ]]; then
    cleaned="$(echo "$current" | sed -E "s/, *'$UUID'//; s/'$UUID', *//; s/'$UUID'//")"
    gsettings set org.gnome.shell enabled-extensions "$cleaned"
  fi
fi
pkill -f "python -m mexerica" 2>/dev/null

rm -f "$HOME/.local/bin/mexerica" \
  "$DATA/applications/$APP_ID.desktop" \
  "$DATA/dbus-1/services/$APP_ID.service" \
  "$DATA/icons/hicolor/scalable/apps/$APP_ID.svg" \
  "$DATA/icons/hicolor/symbolic/apps/$APP_ID-symbolic.svg" \
  "$CONFIG/autostart/$APP_ID.desktop" \
  "$DATA/nautilus/scripts/$SCRIPT_NAME"
rm -rf "$DATA/gnome-shell/extensions/$UUID"
# Leftovers of 0.1.0, installed as io.github.mexerica / mexerica@mexerica.github.io.
rm -rf "$DATA/gnome-shell/extensions/mexerica@mexerica.github.io"
rm -f "$DATA/applications/io.github.mexerica.desktop" "$DATA/dbus-1/services/io.github.mexerica.service" \
  "$CONFIG/autostart/io.github.mexerica.desktop" "$DATA/icons/hicolor/scalable/apps/io.github.mexerica.svg"
if [ -f "$CONFIG/nautilus/scripts-accels" ]; then
  sed -i "/ $SCRIPT_NAME\$/d" "$CONFIG/nautilus/scripts-accels"
fi
echo "Mexerica removido. Suas preferências ficam em $CONFIG/mexerica (apague se quiser)."
