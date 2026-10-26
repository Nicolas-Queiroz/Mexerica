"""Preferences: keys for each wheel, where results go, notifications and integrations."""

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from .. import integration  # noqa: E402
from ..config import MODIFIERS, WHEELS, Config  # noqa: E402
from ..core.actions import TERMINALS  # noqa: E402
from .model import WHEEL_TITLES  # noqa: E402

KEY_LABELS = {"shift": "Shift", "control": "Ctrl", "alt": "Alt"}


class PreferencesDialog(Adw.PreferencesDialog):
    def __init__(self, config: Config):
        super().__init__(title="Preferências", search_enabled=False)
        self.config = config
        self.add(self._general_page())
        self.add(self._integration_page())

    # general ------------------------------------------------------------------------------

    def _general_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title="Geral", icon_name="preferences-system-symbolic")

        keys = Adw.PreferencesGroup(
            title="Teclas ao arrastar",
            description="Segure a tecla enquanto arrasta um arquivo para abrir a roda correspondente.",
        )
        self.key_rows = {}
        for wheel in WHEELS:
            row = Adw.ComboRow(title=WHEEL_TITLES[wheel])
            row.set_model(Gtk.StringList.new([KEY_LABELS[key] for key in MODIFIERS]))
            row.set_selected(MODIFIERS.index(self.config.wheel_keys[wheel]))
            row.connect("notify::selected", self._on_key_changed, wheel)
            self.key_rows[wheel] = row
            keys.add(row)
        page.add(keys)

        results = Adw.PreferencesGroup(title="Resultados")
        self.same_folder = Adw.SwitchRow(
            title="Salvar ao lado do original", subtitle="Desligado: tudo vai para a pasta escolhida abaixo"
        )
        self.same_folder.set_active(not self.config.output_dir)
        self.same_folder.connect("notify::active", self._on_same_folder)
        results.add(self.same_folder)
        self.folder_row = Adw.ActionRow(title="Pasta de saída")
        choose = Gtk.Button(label="Escolher…", valign=Gtk.Align.CENTER)
        choose.connect("clicked", self._choose_folder)
        self.folder_row.add_suffix(choose)
        self._sync_folder_row()
        results.add(self.folder_row)
        notify = Adw.SwitchRow(title="Avisar quando terminar", active=self.config.notify)
        notify.connect("notify::active", lambda row, _p: self._set("notify", row.get_active()))
        results.add(notify)
        open_after = Adw.SwitchRow(title="Abrir a pasta ao terminar", active=self.config.open_folder_after)
        open_after.connect("notify::active", lambda row, _p: self._set("open_folder_after", row.get_active()))
        results.add(open_after)
        page.add(results)

        terminal_group = Adw.PreferencesGroup(title="Ação Abrir no terminal")
        names = ["Detectar automaticamente"] + [name for name, _args in TERMINALS]
        terminal = Adw.ComboRow(title="Terminal")
        terminal.set_model(Gtk.StringList.new(names))
        terminal.set_selected(names.index(self.config.terminal) if self.config.terminal in names else 0)
        terminal.connect(
            "notify::selected",
            lambda row, _p: self._set("terminal", "" if row.get_selected() == 0 else names[row.get_selected()]),
        )
        terminal_group.add(terminal)
        page.add(terminal_group)
        return page

    def _set(self, key: str, value) -> None:
        setattr(self.config, key, value)
        self.config.save()

    def _on_key_changed(self, row, _pspec, wheel: str) -> None:
        key = MODIFIERS[row.get_selected()]
        previous = self.config.wheel_keys[wheel]
        # Keys are unique: the wheel that had this key takes the freed one.
        for other, other_key in self.config.wheel_keys.items():
            if other != wheel and other_key == key:
                self.config.wheel_keys[other] = previous
                other_row = self.key_rows[other]
                other_row.handler_block_by_func(self._on_key_changed)
                other_row.set_selected(MODIFIERS.index(previous))
                other_row.handler_unblock_by_func(self._on_key_changed)
        self.config.wheel_keys[wheel] = key
        self.config.save()

    def _on_same_folder(self, row, _pspec) -> None:
        if row.get_active():
            self._set("output_dir", "")
        elif not self.config.output_dir:
            from ..core.paths import downloads_dir

            self._set("output_dir", str(downloads_dir()))
        self._sync_folder_row()

    def _sync_folder_row(self) -> None:
        self.folder_row.set_sensitive(bool(self.config.output_dir))
        self.folder_row.set_subtitle(self.config.output_dir or "Mesma pasta do arquivo original")

    def _choose_folder(self, _button) -> None:
        dialog = Gtk.FileDialog(title="Pasta de saída", modal=True)

        def done(dialog, result):
            try:
                folder = dialog.select_folder_finish(result)
            except GLib.Error:
                return
            self._set("output_dir", folder.get_path())
            self.same_folder.set_active(False)
            self._sync_folder_row()

        root = self.get_root()
        dialog.select_folder(root if isinstance(root, Gtk.Window) else None, None, done)

    # integration --------------------------------------------------------------------------

    def _integration_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title="Integração", icon_name="applications-system-symbolic")
        shell = Adw.PreferencesGroup(
            title="Extensão do GNOME Shell",
            description=(
                "Detecta o arrasto em qualquer janela e abre a roda sob o ponteiro quando você segura a tecla. "
                "Sem ela, solte os arquivos na janela do Mexerica."
            ),
        )
        status, working = integration.extension_status()
        self.extension_row = Adw.ActionRow(title="Situação", subtitle=status)
        if not working and integration.extension_dir().is_dir():
            enable = Gtk.Button(label="Ativar", valign=Gtk.Align.CENTER)
            enable.connect("clicked", self._enable_extension)
            self.extension_row.add_suffix(enable)
        shell.add(self.extension_row)
        page.add(shell)

        nautilus = Adw.PreferencesGroup(
            title="Arquivos (Nautilus)",
            description=(
                f"Selecione arquivos e pressione {integration.NAUTILUS_SHORTCUT}, ou clique com o botão direito › "
                f"Scripts › {integration.NAUTILUS_SCRIPT_NAME}."
            ),
        )
        row = Adw.ActionRow(
            title="Script do Nautilus",
            subtitle="instalado" if integration.nautilus_installed() else "não instalado",
        )
        install = Gtk.Button(label="Reinstalar" if integration.nautilus_installed() else "Instalar", valign=Gtk.Align.CENTER)
        install.connect("clicked", lambda button: self._install_nautilus(row, button))
        row.add_suffix(install)
        nautilus.add(row)
        page.add(nautilus)
        return page

    def _enable_extension(self, button) -> None:
        try:
            integration.enable_extension()
        except GLib.Error as error:
            self.add_toast(Adw.Toast(title=f"Não foi possível ativar: {error.message}"))
            return
        status, _working = integration.extension_status()
        self.extension_row.set_subtitle(status)
        button.set_visible(False)

    def _install_nautilus(self, row, button) -> None:
        script = integration.install_nautilus_script()
        row.set_subtitle(f"instalado em {Path(script).parent}")
        button.set_label("Reinstalar")
        self.add_toast(Adw.Toast(title="Pronto. Reabra o Nautilus para o atalho valer."))
