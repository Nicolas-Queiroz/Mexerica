"""The GTK application: single instance, D-Bus actions for the Shell extension, notifications."""

import argparse
import logging
import os
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, APP_NAME, VERSION, WEBSITE  # noqa: E402
from .config import Config  # noqa: E402
from .ui.dispatch import Dispatcher  # noqa: E402
from .ui.jobs import JobManager  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"
log = logging.getLogger("mexerica")
SHORTCUTS_HELP = (
    "Arrastando um arquivo (com a extensão do GNOME):\n"
    "  segure Shift — Converter · Ctrl — Ferramentas · Alt — Ações\n"
    "  (as teclas mudam nas Preferências)\n\n"
    "Na janela do Mexerica ou no Nautilus (F4):\n"
    "  Enter — abrir a roda · ← → — escolher · Enter — aplicar\n"
    "  Tab — próxima roda · Shift/Ctrl/Alt — ir para a roda da tecla\n"
    "  1–9 — aplicar a opção de número correspondente · Esc — fechar"
)


class MexericaApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.config = Config.load()
        self.jobs = JobManager()
        self.dispatcher = Dispatcher(self)
        self.main_window = None
        self.wheel_window = None
        self._held = False
        self.jobs.connect("job-finished", self._on_job_finished)
        self.jobs.connect("job-started", self._on_job_started)

    # lifecycle ------------------------------------------------------------------------------

    def do_startup(self):
        Adw.Application.do_startup(self)
        if self.get_flags() & Gio.ApplicationFlags.IS_SERVICE:
            # Started by D-Bus for the Shell extension: stay resident for the next drag.
            self.stay_in_background()
        display = Gdk.Display.get_default()
        if display:
            css = Gtk.CssProvider()
            css.load_from_path(str(DATA_DIR / "style.css"))
            Gtk.StyleContext.add_provider_for_display(display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            Gtk.IconTheme.get_for_display(display).add_search_path(str(DATA_DIR / "icons"))
        Gtk.Window.set_default_icon_name(APP_ID)
        self._add_action("preferences", self._show_preferences)
        self._add_action("about", self._show_about)
        self._add_action("donate", self._show_donate)
        self._add_action("shortcuts", self._show_shortcuts)
        self._add_action("quit", lambda *_: self.quit())
        self._add_action("show-wheel", lambda _a, value: self.show_wheel_for_drag(value.get_string()), "s")
        self._add_action("switch-wheel", lambda _a, value: self._switch_wheel(value.get_string()), "s")
        self._add_action("hide-wheel", lambda *_: self._hide_drag_wheel())
        self._add_action("wheel-for", lambda _a, value: self.show_wheel_for_files([Path(p) for p in value.unpack()]), "as")
        self._add_action("open-path", lambda _a, value: self.open_path(Path(value.get_string())), "s")
        self._add_action("show-in-folder", lambda _a, value: self.show_in_folder(Path(value.get_string())), "s")
        self.set_accels_for_action("app.quit", ["<Control>q"])
        self.set_accels_for_action("app.preferences", ["<Control>comma"])

    def _add_action(self, name, callback, parameter_type: str | None = None) -> None:
        action = Gio.SimpleAction.new(name, GLib.VariantType.new(parameter_type) if parameter_type else None)

        def activate(action, value):
            log.debug("action %s %s", name, value.unpack() if value is not None else "")
            callback(action, value)

        action.connect("activate", activate)
        self.add_action(action)

    def do_command_line(self, command_line):
        parser = argparse.ArgumentParser(prog="mexerica", add_help=False)
        parser.add_argument("--wheel", action="store_true")
        parser.add_argument("--background", action="store_true")
        parser.add_argument("files", nargs="*")
        args, _unknown = parser.parse_known_args(command_line.get_arguments()[1:])
        cwd = Path(command_line.get_cwd() or ".")
        paths = [(cwd / name).resolve() if not Path(name).is_absolute() else Path(name) for name in args.files]
        paths = [path for path in paths if path.exists()]
        if args.background:
            self.stay_in_background()
        elif args.wheel and paths:
            self.show_wheel_for_files(paths)
        else:
            self.open_main(paths)
        return 0

    def stay_in_background(self) -> None:
        """Keeps the process alive without windows, so the Shell extension gets a fast wheel."""
        if not self._held:
            self._held = True
            self.hold()

    # windows --------------------------------------------------------------------------------

    def open_main(self, paths: list[Path] | None = None) -> None:
        from .ui.window import MainWindow

        if self.main_window is None:
            self.main_window = MainWindow(self)
            self.main_window.connect("close-request", self._on_main_closed)
        self.main_window.present()
        if paths:
            self.main_window.set_selection(paths)

    def _on_main_closed(self, _window) -> bool:
        self.main_window = None
        return False

    def _wheel_window(self):
        from .ui.wheel_window import WheelWindow

        if self.wheel_window is None:
            self.wheel_window = WheelWindow(self)
        return self.wheel_window

    def show_wheel_for_drag(self, wheel: str) -> None:
        self._wheel_window().show_for_drag(wheel)

    def show_wheel_for_files(self, paths: list[Path]) -> None:
        self._wheel_window().show_for_files(paths)

    def _switch_wheel(self, wheel: str) -> None:
        if self.wheel_window and self.wheel_window.get_visible():
            self.wheel_window.wheel.set_wheel(wheel)

    def _hide_drag_wheel(self) -> None:
        if self.wheel_window and not self.wheel_window.keyboard_mode:
            self.wheel_window.dismiss()

    def _show_preferences(self, *_args) -> None:
        from .ui.preferences import PreferencesDialog

        PreferencesDialog(self.config).present(self.get_active_window())

    def _show_about(self, *_args) -> None:
        about = Adw.AboutDialog(
            application_name=APP_NAME,
            application_icon=APP_ID,
            version=VERSION,
            comments="Conversor de arquivos offline: arraste, segure uma tecla e solte na roda.",
            license_type=Gtk.License.AGPL_3_0,
            developer_name="Nicolas Queiroz",
            copyright="© 2026 Nicolas Queiroz",
            website=WEBSITE,
            issue_url=f"{WEBSITE}/issues",
        )
        about.add_link("Apoiar com Pix", f"{WEBSITE}#apoie-com-pix")
        about.present(self.get_active_window())

    def _show_donate(self, *_args) -> None:
        from .ui.donate import DonateDialog

        DonateDialog().present(self.get_active_window())

    def _show_shortcuts(self, *_args) -> None:
        dialog = Adw.AlertDialog(heading="Atalhos de teclado", body=SHORTCUTS_HELP)
        dialog.add_response("ok", "OK")
        dialog.present(self.get_active_window())

    # feedback -------------------------------------------------------------------------------

    def toast(self, message: str) -> None:
        if self.main_window and self.main_window.is_active():
            self.main_window.toast(message)
        else:
            self._notify("mexerica-info", APP_NAME, message)

    def report_error(self, message: str) -> None:
        if self.main_window and self.main_window.is_active():
            dialog = Adw.AlertDialog(heading="Não deu certo", body=message)
            dialog.add_response("ok", "OK")
            dialog.present(self.main_window)
        else:
            self._notify("mexerica-error", "Não deu certo", message)

    def _notify(self, notification_id: str, title: str, body: str, result: Path | None = None) -> None:
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        if result:
            target = GLib.Variant("s", str(result))
            notification.set_default_action_and_target("app.show-in-folder", target)
            notification.add_button_with_target("Abrir", "app.open-path", target)
            notification.add_button_with_target("Mostrar na pasta", "app.show-in-folder", target)
        self.send_notification(notification_id, notification)

    def _on_job_started(self, _manager, _job) -> None:
        self.hold()

    def _on_job_finished(self, _manager, job) -> None:
        self.release()
        log.debug("job %s: %s %s %s", job.title, job.state, [str(p) for p in job.results], job.error)
        if job.state == "cancelled":
            return
        main_visible = self.main_window is not None and self.main_window.is_active()
        if job.state == "failed":
            if not main_visible:
                self._notify(f"job-{id(job)}", "Não deu certo", f"{job.title}\n{job.error}")
            return
        if job.results and self.config.open_folder_after:
            self.show_in_folder(job.results[0])
        if self.config.notify and not main_visible:
            body = "\n".join(path.name for path in job.results[:4]) or job.title
            self._notify(f"job-{id(job)}", "Pronto", body, job.results[0] if job.results else None)

    def open_path(self, path: Path) -> None:
        Gtk.FileLauncher.new(Gio.File.new_for_path(str(path))).launch(self.get_active_window(), None, None)

    def show_in_folder(self, path: Path) -> None:
        Gtk.FileLauncher.new(Gio.File.new_for_path(str(path))).open_containing_folder(
            self.get_active_window(), None, None
        )


def run(argv: list[str] | None = None) -> int:
    logging.basicConfig(format="[%(name)s] %(message)s")
    if os.environ.get("MEXERICA_DEBUG"):
        log.setLevel(logging.DEBUG)
    return MexericaApp().run(argv if argv is not None else sys.argv)
