"""Asks a tool's parameters in a small dialog, remembering the last values used."""

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from ..config import Config  # noqa: E402
from ..core.tools import Tool  # noqa: E402


def ask_params(parent: Gtk.Widget | None, tool: Tool, config: Config, on_ready: Callable[[dict], None]) -> None:
    """Calls on_ready(params) right away for tools without parameters."""
    if not tool.params:
        on_ready({})
        return
    remembered = config.last_params.get(tool.id, {})
    group = Adw.PreferencesGroup()
    readers = {}
    for param in tool.params:
        value = remembered.get(param.key, param.default) if param.kind != "password" else ""
        if param.kind == "choice":
            row = Adw.ComboRow(title=param.label)
            row.set_model(Gtk.StringList.new([label for _value, label in param.choices]))
            values = [choice for choice, _label in param.choices]
            row.set_selected(values.index(value) if value in values else 0)
            readers[param.key] = lambda row=row, values=values: values[row.get_selected()]
        elif param.kind == "password":
            row = Adw.PasswordEntryRow(title=param.label)
            readers[param.key] = row.get_text
        else:
            row = Adw.EntryRow(title=param.label, text=str(value))
            readers[param.key] = row.get_text
        group.add(row)
        if param.placeholder and param.kind != "choice":
            hint = Gtk.Label(label=param.placeholder, css_classes=["dim-label", "caption"], xalign=0)
            row.add_suffix(hint)

    dialog = Adw.AlertDialog(heading=tool.label)
    dialog.set_extra_child(group)
    dialog.add_response("cancel", "Cancelar")
    dialog.add_response("run", "Aplicar")
    dialog.set_response_appearance("run", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("run")
    dialog.set_close_response("cancel")

    def on_response(_dialog, response):
        if response != "run":
            return
        params = {key: read() for key, read in readers.items()}
        config.last_params[tool.id] = {
            key: value for key, value in params.items()
            if next(p for p in tool.params if p.key == key).kind != "password"
        }
        config.save()
        on_ready(params)

    dialog.connect("response", on_response)
    dialog.present(parent)
