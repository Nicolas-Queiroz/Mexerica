"""Main window: drop stage with the wheel, the current selection and the job list."""

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, GObject, Gtk, Pango  # noqa: E402

from .. import APP_ID  # noqa: E402
from ..core import conversions  # noqa: E402
from ..core.actions import ACTIONS  # noqa: E402
from ..core.formats import CATEGORY_ICONS, detect_format  # noqa: E402
from ..core.tools import TOOLS  # noqa: E402
from .jobs import JobItem  # noqa: E402
from .model import describe  # noqa: E402
from .wheel import Wheel, attach_drop_target  # noqa: E402

MENU = """
<interface>
  <menu id="menu">
    <section>
      <item><attribute name="label">Preferências</attribute><attribute name="action">app.preferences</attribute></item>
      <item><attribute name="label">Atalhos de teclado</attribute><attribute name="action">app.shortcuts</attribute></item>
      <item><attribute name="label">Sobre o Mexerica</attribute><attribute name="action">app.about</attribute></item>
    </section>
  </menu>
</interface>
"""


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Mexerica")
        self.app = app
        self.selection: list[Path] = []
        self.keyboard_wheel = False
        self.set_default_size(720, 680)
        self.set_size_request(380, 520)

        header = Adw.HeaderBar()
        open_button = Gtk.Button(icon_name="document-open-symbolic", tooltip_text="Escolher arquivos")
        open_button.connect("clicked", lambda *_: self.choose_files())
        header.pack_start(open_button)
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", tooltip_text="Menu principal")
        menu_button.set_menu_model(Gtk.Builder.new_from_string(MENU, -1).get_object("menu"))
        header.pack_end(menu_button)

        self.toasts = Adw.ToastOverlay()
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(self._build_stage())
        body.append(self._build_selection_bar())
        body.append(self._build_jobs())
        footer = Gtk.Label(
            label=(
                f"{conversions.total_conversions()} conversões · {len(TOOLS)} ferramentas · "
                f"{len(ACTIONS)} ações · tudo no seu computador"
            ),
            css_classes=["dim-label", "caption"],
            margin_bottom=10,
            margin_top=4,
        )
        body.append(footer)
        self.toasts.set_child(body)

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(self.toasts)
        self.set_content(view)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

    # layout -------------------------------------------------------------------------------

    def _build_stage(self) -> Gtk.Widget:
        self.stage = Gtk.Overlay(vexpand=True, css_classes=["mexerica-stage"])
        self.hint = hint = Adw.StatusPage(
            icon_name=APP_ID,
            title="Arraste arquivos para cá",
            description=(
                "Solte sobre a opção da roda: converter, ferramentas ou ações.\n"
                "Passe o ponteiro nos botões do centro para trocar de roda."
            ),
        )
        choose = Gtk.Button(label="Escolher arquivos…", halign=Gtk.Align.CENTER, css_classes=["pill", "suggested-action"])
        choose.connect("clicked", lambda *_: self.choose_files())
        hint.set_child(choose)
        self.stage.set_child(hint)

        self.wheel = Wheel(self.app.config, max_size=430)
        self.wheel.set_visible(False)
        self.wheel.set_halign(Gtk.Align.FILL)
        self.wheel.set_valign(Gtk.Align.FILL)
        self.wheel.connect("chosen", self._on_chosen)
        self.wheel.connect("cancelled", lambda *_: self.hide_wheel())
        self.wheel.connect("dropped-on-hub", lambda _w, paths: (self.set_selection(paths), self.hide_wheel()))
        self.stage.add_overlay(self.wheel)
        attach_drop_target(self.stage, self.wheel, on_enter=self._on_drag_enter, on_leave=self._on_drag_leave)
        return self.stage

    def _build_selection_bar(self) -> Gtk.Widget:
        self.selection_bar = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_UP)
        box = Gtk.Box(spacing=8, margin_start=16, margin_end=16, margin_bottom=8, css_classes=["card", "mexerica-selection"])
        self.selection_icon = Gtk.Image.new_from_icon_name("text-x-generic-symbolic")
        self.selection_icon.set_margin_start(12)
        box.append(self.selection_icon)
        self.selection_label = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.MIDDLE, margin_top=10, margin_bottom=10)
        box.append(self.selection_label)
        self.wheel_button = Gtk.Button(label="Abrir roda", tooltip_text="Enter", css_classes=["suggested-action"], valign=Gtk.Align.CENTER)
        self.wheel_button.connect("clicked", lambda *_: self.show_keyboard_wheel())
        box.append(self.wheel_button)
        clear = Gtk.Button(icon_name="edit-clear-symbolic", tooltip_text="Limpar seleção", css_classes=["flat"], valign=Gtk.Align.CENTER, margin_end=6)
        clear.connect("clicked", lambda *_: self.set_selection([]))
        box.append(clear)
        self.selection_bar.set_child(box)
        return self.selection_bar

    def _build_jobs(self) -> Gtk.Widget:
        self.jobs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_start=16, margin_end=16, spacing=6)
        top = Gtk.Box()
        top.append(Gtk.Label(label="Tarefas", xalign=0, hexpand=True, css_classes=["heading"]))
        clear = Gtk.Button(label="Limpar concluídas", css_classes=["flat"])
        clear.connect("clicked", lambda *_: self.app.jobs.clear_finished())
        top.append(clear)
        self.jobs_box.append(top)
        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        listbox.bind_model(self.app.jobs.store, lambda job: JobRow(job, self))
        scroller = Gtk.ScrolledWindow(propagate_natural_height=True, max_content_height=230, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(listbox)
        self.jobs_box.append(scroller)
        store = self.app.jobs.store
        store.connect("items-changed", lambda *_: self.jobs_box.set_visible(store.get_n_items() > 0))
        self.jobs_box.set_visible(store.get_n_items() > 0)
        return self.jobs_box

    # selection and wheel ----------------------------------------------------------------

    def set_selection(self, paths: list[Path]) -> None:
        self.selection = list(paths)
        self.selection_label.set_label(describe(self.selection) if self.selection else "")
        self.selection_bar.set_reveal_child(bool(self.selection))
        if self.selection:
            fmt = detect_format(self.selection[0])
            icon = CATEGORY_ICONS.get(fmt.category) if fmt and len(self.selection) == 1 else None
            self.selection_icon.set_from_icon_name(icon or "edit-select-all-symbolic")
            # Enter on the selection opens the wheel, like Enter on a file.
            self.wheel_button.grab_focus()

    def show_keyboard_wheel(self, wheel: str | None = None) -> None:
        if not self.selection:
            self.choose_files()
            return
        self.keyboard_wheel = True
        self.wheel.set_paths(self.selection)
        if wheel:
            self.wheel.set_wheel(wheel)
        self.wheel.active = 0 if self.wheel.options else -1
        self._reveal_wheel()
        self.wheel.grab_focus()

    def _reveal_wheel(self) -> None:
        self.hint.set_opacity(0.0)
        if not self.wheel.get_visible():
            self.wheel.set_visible(True)
            self.wheel.play_reveal()

    def hide_wheel(self) -> None:
        self.keyboard_wheel = False
        self.wheel.set_visible(False)
        self.hint.set_opacity(1.0)
        if self.selection:
            self.wheel_button.grab_focus()

    def _on_drag_enter(self) -> None:
        if not self.keyboard_wheel:
            self.wheel.set_wheel("convert")
        self._reveal_wheel()

    def _on_drag_leave(self) -> None:
        if not self.keyboard_wheel:
            # Leave fires right before drop too; give the drop a moment to land.
            GLib.timeout_add(120, self._hide_after_leave)

    def _hide_after_leave(self) -> bool:
        if not self.keyboard_wheel:
            self.hide_wheel()
        return GLib.SOURCE_REMOVE

    def _on_chosen(self, _wheel, option, paths) -> None:
        self.hide_wheel()
        self.app.dispatcher.perform(option, paths, self)

    def _on_key(self, _controller, keyval, _keycode, _state) -> bool:
        if self.wheel.get_visible():
            if keyval == Gdk.KEY_Escape:
                self.hide_wheel()
                return True
            return False
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and self.selection:
            self.show_keyboard_wheel()
            return True
        return False

    def choose_files(self) -> None:
        dialog = Gtk.FileDialog(title="Escolher arquivos", modal=True)

        def done(dialog, result):
            try:
                files = dialog.open_multiple_finish(result)
            except GLib.Error:
                return
            paths = [Path(file.get_path()) for file in files if file.get_path()]
            if paths:
                self.set_selection(paths)
                self.show_keyboard_wheel()

        dialog.open_multiple(self, None, done)

    def toast(self, message: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=message, timeout=3))


class JobRow(Adw.ActionRow):
    def __init__(self, job: JobItem, window: MainWindow):
        super().__init__(title_lines=1, subtitle_lines=2)
        self.job = job
        self.window = window
        job.bind_property("title", self, "title", GObject.BindingFlags.SYNC_CREATE)
        job.bind_property("status", self, "subtitle", GObject.BindingFlags.SYNC_CREATE)
        self.set_title_selectable(False)
        self.icon = Gtk.Image()
        self.add_prefix(self.icon)
        self.progress = Gtk.ProgressBar(valign=Gtk.Align.CENTER, width_request=90)
        job.bind_property("progress", self.progress, "fraction", GObject.BindingFlags.SYNC_CREATE)
        self.cancel = Gtk.Button(icon_name="process-stop-symbolic", tooltip_text="Cancelar", valign=Gtk.Align.CENTER, css_classes=["flat"])
        self.cancel.connect("clicked", lambda *_: job.cancel())
        self.open = Gtk.Button(label="Abrir", valign=Gtk.Align.CENTER, css_classes=["flat"])
        self.open.connect("clicked", lambda *_: self.window.app.open_path(job.results[0]))
        self.folder = Gtk.Button(icon_name="folder-open-symbolic", tooltip_text="Mostrar na pasta", valign=Gtk.Align.CENTER, css_classes=["flat"])
        self.folder.connect("clicked", lambda *_: self.window.app.show_in_folder(job.results[0]))
        self.details = Gtk.Button(icon_name="dialog-information-symbolic", tooltip_text="Detalhes do erro", valign=Gtk.Align.CENTER, css_classes=["flat"])
        self.details.connect("clicked", lambda *_: self._show_error())
        for widget in (self.progress, self.cancel, self.open, self.folder, self.details):
            self.add_suffix(widget)
        job.connect("notify::state", lambda *_: self._sync())
        self._sync()

    def _sync(self) -> None:
        state = self.job.state
        running = state in ("queued", "running")
        self.progress.set_visible(running)
        self.cancel.set_visible(running)
        has_results = state == "done" and bool(self.job.results)
        self.open.set_visible(has_results)
        self.folder.set_visible(has_results)
        self.details.set_visible(state == "failed")
        icon = {
            "queued": "content-loading-symbolic",
            "running": "emblem-synchronizing-symbolic",
            "done": "object-select-symbolic",
            "failed": "dialog-error-symbolic",
            "cancelled": "action-unavailable-symbolic",
        }[state]
        self.icon.set_from_icon_name(icon)
        for css in ("success", "error"):
            self.icon.remove_css_class(css)
        if state == "done":
            self.icon.add_css_class("success")
        elif state == "failed":
            self.icon.add_css_class("error")

    def _show_error(self) -> None:
        dialog = Adw.AlertDialog(heading="Não deu certo", body=self.job.error)
        dialog.add_response("ok", "OK")
        dialog.present(self.window)
