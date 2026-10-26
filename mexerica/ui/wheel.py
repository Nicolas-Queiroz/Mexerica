"""The radial menu: options around a hub, chosen by hover-and-drop, click or keyboard."""

import math
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Graphene", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Adw, Gdk, GLib, GObject, Graphene, Gtk, Pango, PangoCairo  # noqa: E402

from ..config import WHEELS, Config  # noqa: E402
from .model import WHEEL_ICONS, WHEEL_TITLES, WheelOption, describe, options_for  # noqa: E402

ACCENT = (1.0, 0.478, 0.0)  # tangerine
MODE_KEYS = {
    Gdk.KEY_Shift_L: "shift",
    Gdk.KEY_Shift_R: "shift",
    Gdk.KEY_Control_L: "control",
    Gdk.KEY_Control_R: "control",
    Gdk.KEY_Alt_L: "alt",
    Gdk.KEY_Alt_R: "alt",
}
DWELL_MS = 320
FALLBACK_ICON = "applications-system-symbolic"


def files_from_value(value) -> list[Path]:
    """Local paths from a Gdk.FileList drop value; remote URIs are ignored."""
    if value is None:
        return []
    files = value.get_files() if hasattr(value, "get_files") else list(value)
    return [Path(file.get_path()) for file in files if file.get_path()]


class Wheel(Gtk.Widget):
    __gtype_name__ = "MexericaWheel"
    __gsignals__ = {
        "chosen": (GObject.SignalFlags.RUN_FIRST, None, (object, object)),  # option, paths
        "cancelled": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "dropped-on-hub": (GObject.SignalFlags.RUN_FIRST, None, (object,)),  # paths
        "wheel-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, config: Config, *, max_size: int = 460):
        super().__init__()
        self.config = config
        self.max_size = max_size
        self.paths: list[Path] = []
        self.wheel = "convert"
        self.options: list[WheelOption] = []
        self.active = -1
        self.hover_mode: str | None = None
        self.reveal = 1.0
        self._dwell_source = 0
        self._icon_cache: dict[tuple[str, int], Gtk.IconPaintable] = {}
        self.set_focusable(True)
        self.set_can_focus(True)
        self.add_css_class("mexerica-wheel")
        self._animation = Adw.TimedAnimation.new(
            self, 0.0, 1.0, 190, Adw.CallbackAnimationTarget.new(self._on_reveal_step)
        )
        self._animation.set_easing(Adw.Easing.EASE_OUT_CUBIC)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda _c, x, y: self.point_at(x, y))
        motion.connect("leave", lambda _c: self.point_at(-1, -1))
        self.add_controller(motion)
        click = Gtk.GestureClick()
        click.connect("released", self._on_click)
        self.add_controller(click)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        Adw.StyleManager.get_default().connect("notify::dark", lambda *_: self.queue_draw())

    # state ------------------------------------------------------------------------------

    def set_paths(self, paths: list[Path]) -> None:
        if paths == self.paths:
            return
        self.paths = list(paths)
        self._refresh_options()

    def set_wheel(self, wheel: str) -> None:
        if wheel not in WHEELS or wheel == self.wheel:
            return
        self.wheel = wheel
        self._refresh_options()
        self.emit("wheel-changed", wheel)

    def cycle_wheel(self, step: int = 1) -> None:
        index = WHEELS.index(self.wheel)
        self.set_wheel(WHEELS[(index + step) % len(WHEELS)])

    def _refresh_options(self) -> None:
        self.options = options_for(self.paths, self.wheel)
        self.active = -1 if not self.options else min(max(self.active, -1), len(self.options) - 1)
        self.queue_draw()

    def play_reveal(self) -> None:
        self._animation.reset()
        self._animation.play()

    def _on_reveal_step(self, value: float) -> None:
        self.reveal = value
        self.queue_draw()

    @property
    def active_option(self) -> WheelOption | None:
        return self.options[self.active] if 0 <= self.active < len(self.options) else None

    # geometry ---------------------------------------------------------------------------

    def _geometry(self):
        width, height = self.get_width(), self.get_height()
        size = min(width, height, self.max_size)
        outer = size / 2 - 14
        inner = outer * 0.43
        hub = inner - 7
        return width / 2, height / 2, outer, inner, hub

    def _mode_centers(self):
        cx, cy, _outer, _inner, hub = self._geometry()
        spacing = hub * 0.5
        y = cy + hub * 0.5
        return {wheel: (cx + (index - 1) * spacing, y) for index, wheel in enumerate(WHEELS)}

    def hit(self, x: float, y: float):
        """('segment', index) | ('mode', wheel) | ('hub', None) | ('outside', None)."""
        cx, cy, outer, inner, hub = self._geometry()
        dx, dy = x - cx, y - cy
        distance = math.hypot(dx, dy)
        if distance <= hub:
            radius = hub * 0.2
            for wheel, (mx, my) in self._mode_centers().items():
                if math.hypot(x - mx, y - my) <= radius + 4:
                    return "mode", wheel
            return "hub", None
        if inner - 7 < distance <= outer + 26 and self.options:
            step = 2 * math.pi / len(self.options)
            angle = (math.atan2(dy, dx) + math.pi / 2 + step / 2) % (2 * math.pi)
            return "segment", int(angle // step) % len(self.options)
        return "outside", None

    # pointer, drag and keyboard -----------------------------------------------------------

    def point_at(self, x: float, y: float) -> None:
        kind, value = self.hit(x, y) if x >= 0 else ("outside", None)
        active = value if kind == "segment" else -1
        mode = value if kind == "mode" else None
        if active != self.active:
            self.active = active
            self.queue_draw()
        if mode != self.hover_mode:
            self.hover_mode = mode
            self._restart_dwell()
            self.queue_draw()

    def _restart_dwell(self) -> None:
        if self._dwell_source:
            GLib.source_remove(self._dwell_source)
            self._dwell_source = 0
        if self.hover_mode and self.hover_mode != self.wheel:
            self._dwell_source = GLib.timeout_add(DWELL_MS, self._on_dwell)

    def _on_dwell(self) -> bool:
        self._dwell_source = 0
        if self.hover_mode:
            self.set_wheel(self.hover_mode)
        return GLib.SOURCE_REMOVE

    def drop_at(self, paths: list[Path], x: float, y: float) -> bool:
        if paths:
            self.set_paths(paths)
        kind, value = self.hit(x, y)
        if kind == "segment" and self.options:
            self.emit("chosen", self.options[value], list(self.paths))
            return True
        if kind in ("hub", "mode"):
            self.emit("dropped-on-hub", list(self.paths))
            return True
        return False

    def _on_click(self, gesture, _n_press, x, y) -> None:
        kind, value = self.hit(x, y)
        if kind == "segment" and self.options:
            self.emit("chosen", self.options[value], list(self.paths))
        elif kind == "mode":
            self.set_wheel(value)
        elif kind == "outside":
            self.emit("cancelled")

    def _on_key(self, _controller, keyval, _keycode, state) -> bool:
        count = len(self.options)
        if keyval in MODE_KEYS:
            wheel = self.config.wheel_for_key(MODE_KEYS[keyval])
            if wheel:
                self.set_wheel(wheel)
            return False
        if keyval == Gdk.KEY_Escape:
            self.emit("cancelled")
            return True
        if keyval in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            self.cycle_wheel(-1 if keyval == Gdk.KEY_ISO_Left_Tab else 1)
            return True
        if not count:
            return False
        if keyval in (Gdk.KEY_Right, Gdk.KEY_Down):
            self.active = (self.active + 1) % count
        elif keyval in (Gdk.KEY_Left, Gdk.KEY_Up):
            self.active = (self.active - 1) % count if self.active >= 0 else count - 1
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            if self.active_option:
                self.emit("chosen", self.active_option, list(self.paths))
            return True
        elif Gdk.KEY_1 <= keyval <= Gdk.KEY_9 and keyval - Gdk.KEY_1 < count:
            self.active = keyval - Gdk.KEY_1
            self.emit("chosen", self.active_option, list(self.paths))
            return True
        else:
            return False
        self.queue_draw()
        return True

    # drawing ------------------------------------------------------------------------------

    def do_measure(self, orientation, for_size):
        return 240, self.max_size, -1, -1

    def _palette(self):
        dark = Adw.StyleManager.get_default().get_dark()
        if dark:
            return {
                "disc": (0.13, 0.13, 0.14, 0.98),
                "ring": (1, 1, 1, 0.07),
                "hub": (1, 1, 1, 0.09),
                "text": (0.96, 0.96, 0.96),
                "muted": (0.72, 0.72, 0.74),
                "edge": (1, 1, 1, 0.12),
            }
        return {
            "disc": (0.99, 0.99, 0.99, 0.99),
            "ring": (0, 0, 0, 0.05),
            "hub": (0, 0, 0, 0.06),
            "text": (0.13, 0.13, 0.14),
            "muted": (0.38, 0.38, 0.40),
            "edge": (0, 0, 0, 0.10),
        }

    def do_snapshot(self, snapshot) -> None:
        width, height = self.get_width(), self.get_height()
        if width <= 0 or height <= 0:
            return
        cx, cy, outer, inner, hub = self._geometry()
        scale = 0.86 + 0.14 * self.reveal
        snapshot.save()
        snapshot.push_opacity(self.reveal)
        snapshot.translate(Graphene.Point().init(cx, cy))
        snapshot.scale(scale, scale)
        snapshot.translate(Graphene.Point().init(-cx, -cy))
        cr = snapshot.append_cairo(Graphene.Rect().init(0, 0, width, height))
        palette = self._palette()
        self._draw_disc(cr, cx, cy, outer, palette)
        icon_jobs = self._draw_segments(cr, cx, cy, outer, inner, palette)
        icon_jobs += self._draw_hub(cr, cx, cy, hub, palette)
        for name, x, y, size, color in icon_jobs:
            self._snapshot_icon(snapshot, name, x, y, size, color)
        snapshot.pop()
        snapshot.restore()

    def _draw_disc(self, cr, cx, cy, outer, palette) -> None:
        for spread, alpha in ((12, 0.05), (8, 0.07), (4, 0.10)):
            cr.arc(cx, cy + 3, outer + spread, 0, 2 * math.pi)
            cr.set_source_rgba(0, 0, 0, alpha)
            cr.fill()
        cr.arc(cx, cy, outer + 2, 0, 2 * math.pi)
        cr.set_source_rgba(*palette["disc"])
        cr.fill_preserve()
        cr.set_source_rgba(*palette["edge"])
        cr.set_line_width(1)
        cr.stroke()

    def _draw_segments(self, cr, cx, cy, outer, inner, palette) -> list:
        icons = []
        count = len(self.options)
        if not count:
            return icons
        step = 2 * math.pi / count
        gap_outer = 3 / outer
        gap_inner = 3 / inner
        middle = (outer + inner) / 2
        label_width = min(2 * middle * math.sin(min(step, math.pi) / 2) * 0.95, (outer - inner) * 1.2)
        for index, option in enumerate(self.options):
            center = -math.pi / 2 + index * step
            start, end = center - step / 2, center + step / 2
            active = index == self.active
            cr.new_path()
            if count == 1:
                cr.arc(cx, cy, outer - 4, 0, 2 * math.pi)
                cr.arc_negative(cx, cy, inner, 2 * math.pi, 0)
            else:
                cr.arc(cx, cy, outer - 4, start + gap_outer, end - gap_outer)
                cr.arc_negative(cx, cy, inner, end - gap_inner, start + gap_inner)
            cr.close_path()
            if active:
                cr.set_source_rgba(*ACCENT, 1)
            else:
                cr.set_source_rgba(*palette["ring"])
            cr.fill()
            x = cx + middle * math.cos(center)
            y = cy + middle * math.sin(center)
            color = (1, 1, 1) if active else palette["text"]
            if option.kind == "convert":
                self._text(cr, option.short, x, y, label_width, 13.5, Pango.Weight.BOLD, color, lines=1)
            else:
                icons.append((option.icon, x, y - 13, 22, color))
                self._text(cr, option.short, x, y + 13, label_width, 8.5, Pango.Weight.SEMIBOLD, color, lines=2)
        return icons

    def _draw_hub(self, cr, cx, cy, hub, palette) -> list:
        cr.arc(cx, cy, hub, 0, 2 * math.pi)
        cr.set_source_rgba(*palette["hub"])
        cr.fill()
        title = WHEEL_TITLES[self.wheel].upper()
        self._text(cr, title, cx, cy - hub * 0.52, hub * 1.5, 8.5, Pango.Weight.BOLD, ACCENT, lines=1)
        if self.active_option:
            caption = self.active_option.title
        elif not self.options and self.paths:
            caption = "Nada a fazer com este arquivo aqui"
        else:
            caption = describe(self.paths)
        self._text(cr, caption, cx, cy - hub * 0.12, hub * 1.62, 10.5, Pango.Weight.SEMIBOLD, palette["text"], lines=2)
        icons = []
        radius = hub * 0.2
        for wheel, (mx, my) in self._mode_centers().items():
            selected = wheel == self.wheel
            hovered = wheel == self.hover_mode
            cr.arc(mx, my, radius, 0, 2 * math.pi)
            if selected:
                cr.set_source_rgba(*ACCENT, 1)
            elif hovered:
                cr.set_source_rgba(*ACCENT, 0.35)
            else:
                cr.set_source_rgba(*palette["ring"])
            cr.fill()
            color = (1, 1, 1) if selected else palette["muted"]
            icons.append((WHEEL_ICONS[wheel], mx, my, int(radius * 1.05), color))
        return icons

    def _text(self, cr, text, x, y, width, size, weight, color, *, lines: int) -> None:
        layout = PangoCairo.create_layout(cr)
        font = self.get_pango_context().get_font_description().copy()
        font.set_size(int(size * Pango.SCALE))
        font.set_weight(weight)
        layout.set_font_description(font)
        layout.set_width(int(width * Pango.SCALE))
        layout.set_alignment(Pango.Alignment.CENTER)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_wrap(Pango.WrapMode.WORD)
        layout.set_height(-lines)
        attributes = Pango.AttrList()
        attributes.insert(Pango.attr_insert_hyphens_new(False))
        layout.set_attributes(attributes)
        layout.set_text(text, -1)
        _ink, logical = layout.get_pixel_extents()
        cr.set_source_rgb(*color[:3])
        cr.move_to(x - width / 2, y - logical.height / 2)
        PangoCairo.show_layout(cr, layout)

    def _snapshot_icon(self, snapshot, name, x, y, size, color) -> None:
        key = (name, size)
        paintable = self._icon_cache.get(key)
        if paintable is None:
            theme = Gtk.IconTheme.get_for_display(self.get_display())
            icon = name if theme.has_icon(name) else FALLBACK_ICON
            paintable = theme.lookup_icon(
                icon, None, size, self.get_scale_factor(), Gtk.TextDirection.NONE, Gtk.IconLookupFlags.FORCE_SYMBOLIC
            )
            self._icon_cache[key] = paintable
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = (*color[:3], 1.0)
        snapshot.save()
        snapshot.translate(Graphene.Point().init(x - size / 2, y - size / 2))
        paintable.snapshot_symbolic(snapshot, size, size, [rgba])
        snapshot.restore()


def attach_drop_target(widget: Gtk.Widget, wheel: Wheel, *, on_enter=None, on_leave=None) -> Gtk.DropTarget:
    """Feeds a drag over `widget` (an ancestor of the wheel or the wheel itself) to the wheel."""
    target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
    target.set_preload(True)

    def to_wheel(x, y):
        if widget is wheel:
            return x, y
        point = widget.compute_point(wheel, Graphene.Point().init(x, y))
        return (point[1].x, point[1].y) if point and point[0] else (x, y)

    def enter(_target, x, y):
        if on_enter:
            on_enter()
        wheel.set_paths(files_from_value(target.get_value()))
        wheel.point_at(*to_wheel(x, y))
        return Gdk.DragAction.COPY

    def motion(_target, x, y):
        wheel.point_at(*to_wheel(x, y))
        return Gdk.DragAction.COPY

    def leave(_target):
        wheel.point_at(-1, -1)
        if on_leave:
            on_leave()

    def drop(_target, value, x, y):
        return wheel.drop_at(files_from_value(value), *to_wheel(x, y))

    target.connect("notify::value", lambda *_: wheel.set_paths(files_from_value(target.get_value())))
    target.connect("enter", enter)
    target.connect("motion", motion)
    target.connect("leave", leave)
    target.connect("drop", drop)
    widget.add_controller(target)
    return target
