#!/bin/bash
# Installs Mexerica for the current user, without sudo:
# virtualenv, launcher, app menu entry, icon, D-Bus service, background autostart,
# GNOME Shell extension and the Nautilus script (F4).
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
APP_ID="io.github.mexerica"
UUID="mexerica@mexerica.github.io"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
BIN="$HOME/.local/bin"
LAUNCHER="$BIN/mexerica"

step() { printf '\n\033[1;33m▸ %s\033[0m\n' "$1"; }

step "Procurando um Python com GTK 4 e libadwaita"
PYTHON=""
for candidate in /usr/bin/python3 /usr/bin/python3.13 /usr/bin/python3.12 /usr/bin/python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c \
    "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1')" 2>/dev/null; then
    PYTHON="$(command -v "$candidate")"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Nenhum Python com GTK 4 + libadwaita. No Debian/Ubuntu: sudo apt install python3-gi gir1.2-adw-1" >&2
  exit 1
fi
echo "$PYTHON"

step "Ambiente virtual e dependências (ffmpeg, pandoc e PyMuPDF vêm pelo pip)"
if [ ! -x "$REPO/.venv/bin/python" ]; then
  "$PYTHON" -m venv --system-site-packages "$REPO/.venv"
fi
"$REPO/.venv/bin/python" -m pip install --quiet --upgrade pip
"$REPO/.venv/bin/python" -m pip install --quiet -e "$REPO"

step "Lançador em $LAUNCHER"
mkdir -p "$BIN"
cat > "$LAUNCHER" <<EOF
#!/bin/sh
exec "$REPO/.venv/bin/python" -m mexerica "\$@"
EOF
chmod +x "$LAUNCHER"

step "Menu de aplicativos, ícone e serviço D-Bus"
mkdir -p "$DATA/applications" "$DATA/dbus-1/services" \
  "$DATA/icons/hicolor/scalable/apps" "$DATA/icons/hicolor/symbolic/apps"
cp "$REPO/mexerica/data/icons/hicolor/scalable/apps/$APP_ID.svg" "$DATA/icons/hicolor/scalable/apps/"
cp "$REPO/mexerica/data/icons/hicolor/symbolic/apps/$APP_ID-symbolic.svg" "$DATA/icons/hicolor/symbolic/apps/"
cat > "$DATA/applications/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Mexerica
GenericName=Conversor de arquivos
Comment=Converta imagens, vídeos, áudios, PDFs e documentos sem enviar nada para a internet
Exec=$LAUNCHER %F
Icon=$APP_ID
Terminal=false
Categories=Utility;GTK;
Keywords=converter;conversor;pdf;imagem;vídeo;áudio;comprimir;
StartupNotify=true
EOF
cat > "$DATA/dbus-1/services/$APP_ID.service" <<EOF
[D-BUS Service]
Name=$APP_ID
Exec=$LAUNCHER --gapplication-service
EOF
command -v update-desktop-database >/dev/null && update-desktop-database "$DATA/applications" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$DATA/icons/hicolor" || true

step "Início automático em segundo plano (a roda abre mais rápido)"
mkdir -p "$CONFIG/autostart"
cat > "$CONFIG/autostart/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Mexerica (segundo plano)
Exec=$LAUNCHER --background
Icon=$APP_ID
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF

step "Extensão do GNOME Shell"
mkdir -p "$DATA/gnome-shell/extensions"
rm -rf "$DATA/gnome-shell/extensions/$UUID"
cp -r "$REPO/gnome-extension/$UUID" "$DATA/gnome-shell/extensions/"
EXTENSION_NOTE=""
if command -v gnome-extensions >/dev/null && gnome-extensions enable "$UUID" 2>/dev/null; then
  EXTENSION_NOTE="ativada"
elif command -v gsettings >/dev/null; then
  # The Shell only discovers new extensions at login; pre-enable it for the next session.
  current="$(gsettings get org.gnome.shell enabled-extensions 2>/dev/null || echo "@as []")"
  if [[ "$current" != *"$UUID"* ]]; then
    if [[ "$current" == "@as []" || "$current" == "[]" ]]; then
      gsettings set org.gnome.shell enabled-extensions "['$UUID']"
    else
      gsettings set org.gnome.shell enabled-extensions "${current%]}, '$UUID']"
    fi
  fi
  EXTENSION_NOTE="instalada — encerre a sessão e entre de novo para o GNOME carregá-la"
fi
echo "$EXTENSION_NOTE"

step "Script do Nautilus (selecione arquivos e pressione F4)"
"$REPO/.venv/bin/python" -c "from mexerica.integration import install_nautilus_script; print(install_nautilus_script('$LAUNCHER'))"

step "Pronto"
cat <<EOF
• Abra o Mexerica pelo menu de aplicativos, ou rode: mexerica
• Arraste um arquivo e segure Shift (converter), Ctrl (ferramentas) ou Alt (ações).
  Isso exige a extensão: $EXTENSION_NOTE
• No Nautilus: selecione arquivos e pressione F4 (feche e reabra o Nautilus antes).
• Pelo terminal: mexerica --list, mexerica foto.heic --to jpg
• Para remover: $REPO/uninstall.sh
EOF
