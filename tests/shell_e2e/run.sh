#!/bin/bash
# End-to-end test of the drag gesture: a throwaway headless GNOME Shell with the extension,
# the app in background mode, a drag source, and synthetic input. Touches nothing of the
# real session: own D-Bus, runtime dir, data/config dirs and in-memory GSettings.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PY="$REPO/.venv/bin/python"

if [ "${1:-}" != "--inner" ]; then
  WORK="$(mktemp -d)"
  # The document portal leaves a FUSE mount in the runtime dir; unmount before deleting.
  trap 'fusermount3 -u "$WORK/run/doc" 2>/dev/null; fusermount -u "$WORK/run/doc" 2>/dev/null; rm -rf "$WORK"' EXIT
  mkdir -p "$WORK/run" "$WORK/data/gnome-shell/extensions" "$WORK/config" "$WORK/files"
  chmod 700 "$WORK/run"
  cp -r "$REPO/gnome-extension/mexerica@nicolas-queiroz.github.io" "$HERE/testkit@mexerica.local" \
    "$WORK/data/gnome-shell/extensions/"
  XDG_RUNTIME_DIR="$WORK/run" XDG_DATA_HOME="$WORK/data" XDG_CONFIG_HOME="$WORK/config" \
    GSETTINGS_BACKEND=memory dbus-run-session -- "$0" --inner "$WORK" 2> "$WORK/stderr.log"
  status=$?
  [ $status -ne 0 ] && tail -20 "$WORK/stderr.log"
  exit $status
fi

WORK="$2"
cd "$WORK"
export WAYLAND_DISPLAY=mexerica-e2e GDK_BACKEND=wayland PYTHONPATH="$REPO"
shell_eval() {
  gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell \
    --method org.gnome.Shell.Eval "$1" > /dev/null
}
enable() {
  gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell \
    --method org.gnome.Shell.Extensions.EnableExtension "$1" > /dev/null
}

gnome-shell --headless --wayland --no-x11 --virtual-monitor 1280x800 \
  --wayland-display="$WAYLAND_DISPLAY" > shell.log 2>&1 &
SHELL_PID=$!
for _ in $(seq 1 60); do
  gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell \
    --method org.gnome.Shell.Extensions.ListExtensions > /dev/null 2>&1 && break
  sleep 0.5
done
enable testkit@mexerica.local
enable mexerica@nicolas-queiroz.github.io
sleep 1
# The overview and the distro welcome dialog grab the pointer at first login.
shell_eval "Main.overview.hide()"
sleep 1
shell_eval "global.stage.get_grab_actor()?.close?.()"
sleep 1

"$PY" -c "from PIL import Image; Image.new('RGB', (320, 200), 'orange').save('files/foto.png')"
MEXERICA_DEBUG=1 "$PY" -m mexerica --background > app.log 2>&1 &
APP_PID=$!
"$PY" "$HERE/dragsource.py" "$WORK/files/foto.png" > source.log 2>&1 &
SOURCE_PID=$!
sleep 5

failures=0
check() {
  local name="$1" expected="$2"
  if [ -e "files/$expected" ]; then
    echo "PASS  $name → $expected"
  else
    echo "FAIL  $name: files/$expected não apareceu"; failures=$((failures + 1))
  fi
}
# PNG wheels: convert has 7 options (JPG on top), tools has 8 (Preto e branco at 135°).
"$PY" "$HERE/input.py" drag 0 -140 shift
check "Shift + soltar no topo (Converter → JPG)" "foto.jpg"
"$PY" "$HERE/input.py" drag -101 101 control
check "Ctrl + soltar embaixo à esquerda (Ferramentas → Preto e branco)" "foto (pb).png"
before=$(ls files | wc -l)
"$PY" "$HERE/input.py" drag -500 300 shift
if [ "$(ls files | wc -l)" -eq "$before" ] && grep -q "action hide-wheel" app.log; then
  echo "PASS  Shift + soltar fora da roda: nada é feito e a roda some"
else
  echo "FAIL  soltar fora da roda gerou arquivo ou não escondeu a roda"; failures=$((failures + 1))
fi
"$PY" "$HERE/input.py" keys "$WORK/files/foto.png" Right Return
check "mexerica --wheel + → + Enter (caminho do Nautilus/F4)" "foto.webp"

if [ $failures -ne 0 ]; then
  echo "--- app.log"; grep "\[mexerica\]" app.log
  echo "--- shell.log"; grep -iE "mexerica|JS ERROR" shell.log | tail -10
fi
kill $SOURCE_PID $APP_PID $SHELL_PID 2>/dev/null
sleep 1
kill -9 $SOURCE_PID $APP_PID $SHELL_PID 2>/dev/null
echo "$failures falha(s)"
exit $failures
