"""Borderless transparent window holding the wheel, placed under the pointer by the Shell extension."""

import logging
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .wheel import Wheel, attach_drop_target  # noqa: E402

log = logging.getLogger("mexerica")
WHEEL_TITLE = "Mexerica Roda"
WHEEL_SIZE = 440


class WheelWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(application=app, title=WHEEL_TITLE, decorated=False, resizable=False)
        self.app = app
        self.keyboard_mode = False
        self.set_default_size(WHEEL_SIZE, WHEEL_SIZE)
        self.remove_css_class("background")
        self.add_css_class("mexerica-overlay")
        self.wheel = Wheel(app.config, max_size=WHEEL_SIZE)
        self.set_child(self.wheel)
        attach_drop_target(self.wheel, self.wheel)
        self.wheel.connect("chosen", self._on_chosen)
        self.wheel.connect("cancelled", lambda *_: self.dismiss())
        self.wheel.connect("dropped-on-hub", self._on_dropped_on_hub)
        self.connect("notify::is-active", self._on_active_changed)
        self.connect("close-request", self._on_close_request)

    def show_for_drag(self, wheel: str) -> None:
        """Drag in progress elsewhere: files arrive when the pointer enters the wheel."""
        self.keyboard_mode = False
        self.wheel.set_paths([])
        self.wheel.set_wheel(wheel)
        self._present()

    def show_for_files(self, paths: list[Path], wheel: str = "convert") -> None:
        self.keyboard_mode = True
        self.wheel.set_paths(paths)
        self.wheel.set_wheel(wheel)
        self.wheel.active = 0 if self.wheel.options else -1
        self._present()

    def _present(self) -> None:
        self.present()
        self.wheel.grab_focus()
        self.wheel.play_reveal()

    def dismiss(self) -> None:
        self.keyboard_mode = False
        self.set_visible(False)

    def _on_chosen(self, _wheel, option, paths) -> None:
        log.debug("wheel chose %s:%s for %s", option.kind, option.id, [str(path) for path in paths])
        self.dismiss()
        # Defer so the drop finishes before a parameter dialog opens.
        GLib.idle_add(self._perform, option, paths)

    def _perform(self, option, paths) -> bool:
        self.app.dispatcher.perform(option, paths, None)
        return GLib.SOURCE_REMOVE

    def _on_dropped_on_hub(self, _wheel, paths) -> None:
        self.dismiss()
        self.app.open_main(paths)

    def _on_active_changed(self, *_args) -> None:
        # A wheel opened from the keyboard closes when the user clicks elsewhere.
        if self.keyboard_mode and not self.is_active() and self.get_visible():
            GLib.timeout_add(150, self._dismiss_if_inactive)

    def _dismiss_if_inactive(self) -> bool:
        if not self.is_active():
            self.dismiss()
        return GLib.SOURCE_REMOVE

    def _on_close_request(self, *_args) -> bool:
        self.dismiss()
        return True
