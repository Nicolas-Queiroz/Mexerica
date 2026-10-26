"""Fullscreen window whose whole surface drags one file: stands in for Nautilus."""

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GObject, Gtk  # noqa: E402

PATH = sys.argv[1]


def prepare(*_args):
    files = Gdk.FileList.new_from_list([Gio.File.new_for_path(PATH)])
    return Gdk.ContentProvider.new_for_value(GObject.Value(Gdk.FileList, files))


def activate(app):
    window = Gtk.ApplicationWindow(application=app, title="Fonte")
    label = Gtk.Label(label="ARRASTE", hexpand=True, vexpand=True)
    source = Gtk.DragSource(actions=Gdk.DragAction.COPY)
    source.connect("prepare", prepare)
    source.connect("drag-begin", lambda *_: print("source: drag-begin", flush=True))
    source.connect("drag-end", lambda *_: print("source: drag-end", flush=True))
    label.add_controller(source)
    window.set_child(label)
    window.fullscreen()
    window.present()


app = Gtk.Application(application_id="test.mexerica.dragsource")
app.connect("activate", activate)
app.run([])
