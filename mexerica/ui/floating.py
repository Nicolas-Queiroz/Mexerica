"""The Float action: a small shelf that keeps files on screen to drag them out later."""

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango  # noqa: E402

from ..core.formats import CATEGORY_ICONS, detect_format  # noqa: E402

FLOAT_TITLE = "Mexerica Flutuante"


def file_list(paths: list[Path]) -> Gdk.ContentProvider:
    files = [Gio.File.new_for_path(str(path)) for path in paths]
    uris = "".join(f"{file.get_uri()}\r\n" for file in files)
    return Gdk.ContentProvider.new_union(
        [
            Gdk.ContentProvider.new_for_value(GObject.Value(Gdk.FileList, Gdk.FileList.new_from_list(files))),
            Gdk.ContentProvider.new_for_bytes("text/uri-list", GLib.Bytes.new(uris.encode())),
        ]
    )


def _thumbnail(path: Path) -> Gtk.Widget:
    fmt = detect_format(path)
    if fmt and fmt.category == "image" and fmt.key not in ("heic", "avif"):
        try:
            image = Gtk.Image.new_from_paintable(Gdk.Texture.new_from_filename(str(path)))
            image.set_pixel_size(56)
            image.add_css_class("mexerica-thumb")
            return image
        except GLib.Error:
            pass
    icon = "folder-symbolic" if path.is_dir() else CATEGORY_ICONS.get(fmt.category if fmt else "", "text-x-generic-symbolic")
    image = Gtk.Image.new_from_icon_name(icon)
    image.set_pixel_size(32)
    image.set_size_request(56, 56)
    return image


class FloatWindow(Adw.Window):
    """Each item can be dragged out (copy) and the whole set via the header handle."""

    def __init__(self, app: Adw.Application, paths: list[Path]):
        super().__init__(application=app, title=FLOAT_TITLE)
        self.paths = list(paths)
        self.set_default_size(260, -1)
        self.set_resizable(False)
        self.add_css_class("mexerica-float")

        header = Adw.HeaderBar()
        handle = Gtk.Box(spacing=6)
        handle.append(Gtk.Image.new_from_icon_name("view-pin-symbolic"))
        handle.append(Gtk.Label(label=f"{len(paths)} {'item' if len(paths) == 1 else 'itens'}"))
        header.set_title_widget(handle)
        self._drag_source(handle, self.paths)

        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        for path in self.paths:
            row = Gtk.Box(spacing=10, margin_top=6, margin_bottom=6, margin_start=8, margin_end=8)
            row.append(_thumbnail(path))
            label = Gtk.Label(
                label=path.name, xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.MIDDLE, max_width_chars=22
            )
            label.set_tooltip_text(str(path))
            row.append(label)
            self._drag_source(row, [path])
            listbox.append(row)

        hint = Gtk.Label(
            label="Arraste para soltar em outro lugar",
            css_classes=["dim-label", "caption"],
            margin_top=8,
        )
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_start=10, margin_end=10, margin_bottom=10)
        body.append(listbox)
        body.append(hint)
        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(body)
        self.set_content(view)

    @staticmethod
    def _drag_source(widget: Gtk.Widget, paths: list[Path]) -> None:
        source = Gtk.DragSource(actions=Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        source.connect("prepare", lambda *_: file_list(paths))
        widget.add_controller(source)
