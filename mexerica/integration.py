"""Desktop integration: GNOME Shell extension state and the Nautilus script with its shortcut."""

import os
import shutil
from pathlib import Path

EXTENSION_UUID = "mexerica@nicolas-queiroz.github.io"
NAUTILUS_SCRIPT_NAME = "Abrir na roda do Mexerica"
NAUTILUS_SHORTCUT = "F4"
EXTENSION_STATES = {
    1: "ativa",
    2: "desativada",
    3: "com erro",
    4: "incompatível com esta versão do GNOME",
    6: "carregada",
    8: "ativando",
}


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def extension_dir() -> Path:
    return data_home() / "gnome-shell" / "extensions" / EXTENSION_UUID


def extension_status() -> tuple[str, bool]:
    """Human status and whether the drag shortcut is working right now."""
    if not extension_dir().is_dir():
        return "não instalada", False
    try:
        import gi

        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib

        info = _shell_extensions().call_sync(
            "GetExtensionInfo", GLib.Variant("(s)", (EXTENSION_UUID,)), Gio.DBusCallFlags.NONE, 2000, None
        ).unpack()[0]
    except Exception:  # noqa: BLE001 - no Shell (other desktop, tests)
        return "instalada (GNOME Shell não encontrado)", False
    if not info:
        return "instalada — encerre a sessão e entre de novo para o GNOME carregá-la", False
    state = int(info.get("state", 0))
    if state == 1:
        return "ativa", True
    if info.get("error"):
        return f"com erro: {info['error']}", False
    return EXTENSION_STATES.get(state, f"estado {state}"), False


def enable_extension() -> None:
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    _shell_extensions().call_sync(
        "EnableExtension", GLib.Variant("(s)", (EXTENSION_UUID,)), Gio.DBusCallFlags.NONE, 5000, None
    )


def _shell_extensions():
    """The Shell's extension manager: interface org.gnome.Shell.Extensions on org.gnome.Shell."""
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio

    return Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SESSION,
        Gio.DBusProxyFlags.DO_NOT_AUTO_START,
        None,
        "org.gnome.Shell",
        "/org/gnome/Shell",
        "org.gnome.Shell.Extensions",
        None,
    )


def nautilus_script() -> Path:
    return data_home() / "nautilus" / "scripts" / NAUTILUS_SCRIPT_NAME


def nautilus_installed() -> bool:
    return nautilus_script().is_file()


def install_nautilus_script(launcher: str | None = None) -> Path:
    """Script under right-click › Scripts, bound to F4 in Nautilus' scripts-accels."""
    launcher = launcher or shutil.which("mexerica") or "mexerica"
    script = nautilus_script()
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "#!/bin/sh\n"
        "# Opens the Mexerica wheel for the files selected in Nautilus.\n"
        f'exec "{launcher}" --wheel "$@"\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    accels = config_home / "nautilus" / "scripts-accels"
    accels.parent.mkdir(parents=True, exist_ok=True)
    lines = accels.read_text(encoding="utf-8").splitlines() if accels.exists() else []
    lines = [line for line in lines if not line.rstrip().endswith(NAUTILUS_SCRIPT_NAME)]
    lines.append(f"{NAUTILUS_SHORTCUT} {NAUTILUS_SCRIPT_NAME}")
    accels.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return script
