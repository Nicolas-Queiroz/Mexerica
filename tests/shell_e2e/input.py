"""Synthetic input through Mutter's RemoteDesktop API (works in a headless shell).

drag <dx> <dy> <modifier>: press at the screen center, drag, hold the modifier, move by
(dx, dy) and drop. keys <file> <keysym names…>: opens `mexerica --wheel file` and types.
"""

import subprocess
import sys
import time

from gi.repository import Gio, GLib

BUS = Gio.bus_get_sync(Gio.BusType.SESSION)
DEST = "org.gnome.Mutter.RemoteDesktop"
KEYSYMS = {
    "shift": 0xFFE1, "control": 0xFFE3, "alt": 0xFFE9,
    "Right": 0xFF53, "Left": 0xFF51, "Return": 0xFF0D, "Tab": 0xFF09, "Escape": 0xFF1B,
}


def call(path, interface, method, args=None, reply=None):
    return BUS.call_sync(
        DEST, path, interface, method, args, GLib.VariantType(reply) if reply else None,
        Gio.DBusCallFlags.NONE, 5000, None,
    )


SESSION = call("/org/gnome/Mutter/RemoteDesktop", DEST, "CreateSession", reply="(o)").unpack()[0]


def session(method, args=None):
    return call(SESSION, DEST + ".Session", method, args)


def move(dx, dy, steps=1, pause=0.02):
    for _ in range(steps):
        session("NotifyPointerMotionRelative", GLib.Variant("(dd)", (dx / steps, dy / steps)))
        time.sleep(pause)


def button(pressed):
    session("NotifyPointerButton", GLib.Variant("(ib)", (272, pressed)))


def key(name, pressed):
    session("NotifyKeyboardKeysym", GLib.Variant("(ub)", (KEYSYMS[name], pressed)))


def tap(name):
    key(name, True)
    key(name, False)
    time.sleep(0.5)


session("Start")
# A new virtual keyboard spends its first key on the keymap; spend it on something harmless.
tap("alt")
move(-5000, -5000)
move(640, 400, steps=4)
time.sleep(0.5)

if sys.argv[1] == "drag":
    dx, dy, modifier = float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    button(True)
    time.sleep(0.2)
    move(30, 0, steps=10)
    time.sleep(0.6)
    key(modifier, True)
    time.sleep(1.5)
    key(modifier, False)
    move(dx, dy, steps=14, pause=0.04)
    time.sleep(0.6)
    button(False)
else:
    subprocess.Popen([sys.executable, "-m", "mexerica", "--wheel", sys.argv[2]])
    time.sleep(3)
    for name in sys.argv[3:]:
        tap(name)
time.sleep(3)
session("Stop")
