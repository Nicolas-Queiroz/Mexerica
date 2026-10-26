"""File actions offered by the Actions wheel; they never convert and accept folders."""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .context import OperationError


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    icon: str


ACTIONS = [
    Action("send", "Enviar ao celular", "phone-symbolic"),
    Action("float", "Flutuar", "view-pin-symbolic"),
    Action("copy", "Copiar", "edit-copy-symbolic"),
    Action("move", "Mover para…", "folder-symbolic"),
    Action("copy-path", "Copiar caminho", "insert-link-symbolic"),
    Action("terminal", "Abrir no terminal", "utilities-terminal-symbolic"),
]
ACTIONS_BY_ID = {action.id: action for action in ACTIONS}

TERMINALS = [
    ("ptyxis", ["--new-window", "--working-directory={dir}"]),
    ("kgx", ["--working-directory={dir}"]),
    ("gnome-terminal", ["--working-directory={dir}"]),
    ("konsole", ["--workdir", "{dir}"]),
    ("xfce4-terminal", ["--working-directory={dir}"]),
    ("tilix", ["--working-directory={dir}"]),
    ("alacritty", ["--working-directory", "{dir}"]),
    ("kitty", ["--directory", "{dir}"]),
    ("wezterm", ["start", "--cwd", "{dir}"]),
    ("xterm", ["-e", "sh", "-c", "cd \"$0\" && exec \"${SHELL:-sh}\"", "{dir}"]),
]


def folder_of(paths: list[Path]) -> Path:
    first = paths[0]
    return first if first.is_dir() else first.parent


def open_terminal(paths: list[Path], preferred: str = "") -> None:
    folder = str(folder_of(paths))
    candidates = [entry for entry in TERMINALS if entry[0] == preferred] + TERMINALS
    for command, args in candidates:
        executable = shutil.which(command)
        if executable:
            subprocess.Popen(
                [executable, *[arg.format(dir=folder) for arg in args]],
                cwd=folder,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
    raise OperationError("Nenhum terminal encontrado.")


def move_to(paths: list[Path], destination: Path) -> list[Path]:
    """Moves without overwriting: an existing name gets a ' (2)' suffix."""
    from .paths import unique_path

    moved = []
    for path in paths:
        if destination == path.parent:
            moved.append(path)
            continue
        if destination.resolve().is_relative_to(path.resolve()):
            raise OperationError(f"Não é possível mover {path.name} para dentro de si mesmo.")
        target = unique_path(destination / path.name)
        shutil.move(str(path), target)
        moved.append(target)
    return moved


def phone_devices() -> list[tuple[str, str]]:
    """Reachable paired KDE Connect devices as (id, name)."""
    executable = shutil.which("kdeconnect-cli")
    if not executable:
        raise OperationError(
            "Instale o KDE Connect (ou o GSConnect) e pareie o celular para enviar arquivos."
        )
    result = subprocess.run(
        [executable, "--list-available", "--id-name-only"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    devices = []
    for line in result.stdout.splitlines():
        device_id, _, name = line.strip().partition(" ")
        if device_id:
            devices.append((device_id, name or device_id))
    return devices


def send_to_phone(paths: list[Path], device_id: str) -> None:
    files = [path for path in paths if path.is_file()]
    if not files:
        raise OperationError("Só dá para enviar arquivos (não pastas) ao celular.")
    for path in files:
        result = subprocess.run(
            ["kdeconnect-cli", "--device", device_id, "--share", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise OperationError(f"O KDE Connect recusou o envio: {result.stderr.strip()}")
