"""Turns a wheel choice into work: conversion jobs, tool jobs (after parameters) or actions."""

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from ..core import actions, jobs  # noqa: E402
from ..core.context import OperationError  # noqa: E402
from ..core.formats import FORMATS  # noqa: E402
from ..core.tools import TOOLS_BY_ID  # noqa: E402
from .floating import FloatWindow, file_list  # noqa: E402
from .model import WheelOption  # noqa: E402
from .params import ask_params  # noqa: E402


class Dispatcher:
    def __init__(self, app):
        self.app = app

    @property
    def config(self):
        return self.app.config

    def perform(self, option: WheelOption, paths: list[Path], parent: Gtk.Widget | None) -> None:
        if not paths:
            return
        if option.kind == "convert":
            for path in paths:
                self._convert(path, option.id)
        elif option.kind == "tool":
            tool = TOOLS_BY_ID[option.id]
            ask_params(parent, tool, self.config, lambda params: self._tool(tool, paths, params))
        else:
            try:
                self._action(option.id, paths, parent)
            except OperationError as error:
                self.app.report_error(str(error))

    def _convert(self, path: Path, target: str) -> None:
        output_dir = self.config.output_dir or None
        self.app.jobs.submit(
            f"{path.name} → {FORMATS[target].label}",
            lambda progress, cancel: jobs.run_conversion(
                path, target, output_dir=output_dir, on_progress=progress, cancel_event=cancel
            ),
        )

    def _tool(self, tool, paths: list[Path], params: dict) -> None:
        output_dir = self.config.output_dir or None
        merged = {**tool.default_params(), **params}
        subject = paths[0].name if len(paths) == 1 else f"{len(paths)} arquivos"
        self.app.jobs.submit(
            f"{tool.label} · {subject}",
            lambda progress, cancel: jobs.run_tool(
                tool, paths, merged, output_dir=output_dir, on_progress=progress, cancel_event=cancel
            ),
        )

    # actions ------------------------------------------------------------------------------

    def _action(self, action_id: str, paths: list[Path], parent) -> None:
        if action_id == "copy":
            self._clipboard(parent).set_content(_copied_files(paths))
            self.app.toast(f"{_count(paths)} copiado(s): cole no gerenciador de arquivos")
        elif action_id == "copy-path":
            self._clipboard(parent).set("\n".join(str(path) for path in paths))
            self.app.toast("Caminho copiado")
        elif action_id == "terminal":
            actions.open_terminal(paths, self.config.terminal)
        elif action_id == "float":
            FloatWindow(self.app, paths).present()
        elif action_id == "move":
            self._choose_folder_and_move(paths, parent)
        elif action_id == "send":
            self._send(paths, parent)

    def _clipboard(self, parent) -> Gdk.Clipboard:
        display = parent.get_display() if parent else Gdk.Display.get_default()
        return display.get_clipboard()

    def _choose_folder_and_move(self, paths: list[Path], parent) -> None:
        dialog = Gtk.FileDialog(title="Mover para…", modal=True)

        def done(dialog, result):
            try:
                folder = dialog.select_folder_finish(result)
            except GLib.Error:
                return
            destination = Path(folder.get_path())
            self.app.jobs.submit(
                f"Mover {_count(paths)} para {destination.name}",
                lambda _progress, _cancel: actions.move_to(paths, destination),
            )

        dialog.select_folder(_window_of(parent), None, done)

    def _send(self, paths: list[Path], parent) -> None:
        devices = actions.phone_devices()
        if not devices:
            raise OperationError(
                "Nenhum celular disponível. Abra o KDE Connect no celular e no computador, na mesma rede."
            )

        def send(device_id: str, name: str) -> None:
            def work(_progress, _cancel) -> list[Path]:
                actions.send_to_phone(paths, device_id)
                return []

            self.app.jobs.submit(f"Enviar {_count(paths)} para {name}", work)

        if len(devices) == 1:
            send(*devices[0])
            return
        dialog = Adw.AlertDialog(heading="Enviar para qual aparelho?")
        dialog.add_response("cancel", "Cancelar")
        for device_id, name in devices:
            dialog.add_response(device_id, name)
        dialog.set_close_response("cancel")
        names = dict(devices)
        dialog.connect("response", lambda _d, response: response in names and send(response, names[response]))
        dialog.present(parent)


def _count(paths: list[Path]) -> str:
    return paths[0].name if len(paths) == 1 else f"{len(paths)} itens"


def _window_of(widget):
    if widget is None:
        return None
    root = widget.get_root()
    return root if isinstance(root, Gtk.Window) else None


def _copied_files(paths: list[Path]) -> Gdk.ContentProvider:
    """File list plus the legacy GNOME format, so Nautilus and other apps can paste."""
    uris = [Gio.File.new_for_path(str(path)).get_uri() for path in paths]
    gnome = ("copy\n" + "\n".join(uris)).encode()
    return Gdk.ContentProvider.new_union(
        [
            file_list(paths),
            Gdk.ContentProvider.new_for_bytes("x-special/gnome-copied-files", GLib.Bytes.new(gnome)),
            Gdk.ContentProvider.new_for_bytes(
                "text/plain;charset=utf-8", GLib.Bytes.new("\n".join(map(str, paths)).encode())
            ),
        ]
    )
