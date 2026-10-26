"""'Apoiar com Pix' dialog: QR code, copy-and-paste code and key. Opened only on request."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from .. import donate  # noqa: E402


class DonateDialog(Adw.Dialog):
    def __init__(self):
        super().__init__(title="Apoiar com Pix", content_width=360)
        texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(donate.qr_png()))
        qr = Gtk.Picture.new_for_paintable(texture)
        qr.set_size_request(220, 220)
        qr.set_can_shrink(True)
        qr.set_halign(Gtk.Align.CENTER)
        qr.add_css_class("mexerica-pix-qr")

        intro = Gtk.Label(
            label=(
                "O Mexerica é grátis e de código aberto. Se ele te ajudou, um Pix de qualquer "
                "valor ajuda a manter o projeto. Totalmente opcional."
            ),
            wrap=True,
            justify=Gtk.Justification.CENTER,
        )
        receiver = Gtk.Label(
            label=f"{donate.PIX_RECEIVER} · {donate.PIX_BANK}",
            css_classes=["dim-label", "caption"],
        )
        self.copy_code = Gtk.Button(label="Copiar código Pix (copia e cola)", css_classes=["pill", "suggested-action"])
        self.copy_code.connect("clicked", self._copy, donate.PIX_PAYLOAD, "Código Pix copiado")
        copy_key = Gtk.Button(label="Copiar chave aleatória", css_classes=["pill"])
        copy_key.connect("clicked", self._copy, donate.PIX_KEY, "Chave Pix copiada")

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=14,
            margin_top=12,
            margin_bottom=24,
            margin_start=24,
            margin_end=24,
        )
        for widget in (intro, qr, receiver, self.copy_code, copy_key):
            box.append(widget)
        self.toasts = Adw.ToastOverlay(child=box)
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        view.set_content(self.toasts)
        self.set_child(view)

    def _copy(self, button: Gtk.Button, text: str, message: str) -> None:
        button.get_clipboard().set(text)
        self.toasts.add_toast(Adw.Toast(title=message, timeout=2))
