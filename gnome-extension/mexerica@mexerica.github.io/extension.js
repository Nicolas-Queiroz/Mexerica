// Opens the Mexerica wheel under the pointer when a modifier is held during a file drag.
//
// The Shell sees every Wayland drag (Meta.Dnd) and the seat's modifier state; the app cannot.
// The wheel itself is a normal app window: the extension only asks the app to show it, then
// moves it under the pointer and keeps it above, so the drop lands on the wheel.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const APP_ID = 'io.github.mexerica';
const OBJECT_PATH = '/io/github/mexerica';
const WHEEL_TITLE = 'Mexerica Roda';
const FLOAT_TITLE = 'Mexerica Flutuante';
const POLL_MS = 50;
const HIDE_DELAY_MS = 400;
const DEFAULT_KEYS = {convert: 'shift', tools: 'control', actions: 'alt'};
const MASKS = {
    shift: Clutter.ModifierType.SHIFT_MASK,
    control: Clutter.ModifierType.CONTROL_MASK,
    alt: Clutter.ModifierType.MOD1_MASK,
};

export default class MexericaExtension extends Extension {
    enable() {
        this._configFile = Gio.File.new_for_path(
            GLib.build_filenamev([GLib.get_user_config_dir(), 'mexerica', 'config.json']));
        this._keys = this._loadKeys();
        this._dragging = false;
        this._shownWheel = null;
        this._anchor = null;
        this._pollId = 0;
        this._hideId = 0;

        this._dnd = global.backend.get_dnd();
        this._dndIds = [
            this._dnd.connect('dnd-enter', () => this._onDragBegin()),
            this._dnd.connect('dnd-leave', () => this._onDragEnd()),
        ];
        this._windowCreatedId = global.display.connect(
            'window-created', (_display, window) => this._onWindowCreated(window));

        this._configMonitor = this._configFile.monitor_file(Gio.FileMonitorFlags.NONE, null);
        this._configMonitorId = this._configMonitor.connect('changed', () => {
            this._keys = this._loadKeys();
        });
    }

    disable() {
        this._stopPolling();
        if (this._hideId) {
            GLib.source_remove(this._hideId);
            this._hideId = 0;
        }
        for (const id of this._dndIds)
            this._dnd.disconnect(id);
        this._dndIds = [];
        this._dnd = null;
        global.display.disconnect(this._windowCreatedId);
        this._configMonitor.disconnect(this._configMonitorId);
        this._configMonitor.cancel();
        this._configMonitor = null;
        this._configFile = null;
    }

    _loadKeys() {
        try {
            const [ok, bytes] = GLib.file_get_contents(this._configFile.get_path());
            if (ok) {
                const config = JSON.parse(new TextDecoder().decode(bytes));
                return {...DEFAULT_KEYS, ...(config.wheel_keys ?? {})};
            }
        } catch (_error) {
            // No config yet: defaults.
        }
        return {...DEFAULT_KEYS};
    }

    _onDragBegin() {
        if (this._hideId) {
            GLib.source_remove(this._hideId);
            this._hideId = 0;
        }
        this._dragging = true;
        this._shownWheel = null;
        this._anchor = null;
        this._stopPolling();
        // Modifier changes produce no drag event, so they are polled while the drag lasts.
        this._pollId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, POLL_MS, () => this._poll());
    }

    _poll() {
        if (!this._dragging) {
            this._pollId = 0;
            return GLib.SOURCE_REMOVE;
        }
        const [x, y, mods] = global.get_pointer();
        const wheel = this._wheelFor(mods);
        if (wheel && wheel !== this._shownWheel) {
            if (this._shownWheel) {
                this._activate('switch-wheel', wheel);
            } else {
                this._anchor = [x, y];
                this._activate('show-wheel', wheel);
            }
            this._shownWheel = wheel;
        }
        return GLib.SOURCE_CONTINUE;
    }

    _wheelFor(mods) {
        for (const [wheel, key] of Object.entries(this._keys)) {
            if (MASKS[key] && (mods & MASKS[key]))
                return wheel;
        }
        return null;
    }

    _onDragEnd() {
        this._dragging = false;
        this._stopPolling();
        if (this._shownWheel) {
            // A drop on the wheel is handled (and the wheel hidden) by the app first;
            // this only clears a wheel the user dropped somewhere else.
            this._hideId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, HIDE_DELAY_MS, () => {
                this._hideId = 0;
                this._activate('hide-wheel');
                return GLib.SOURCE_REMOVE;
            });
        }
        this._shownWheel = null;
    }

    _stopPolling() {
        if (this._pollId) {
            GLib.source_remove(this._pollId);
            this._pollId = 0;
        }
    }

    _activate(name, parameter) {
        const parameters = parameter === undefined ? [] : [new GLib.Variant('s', parameter)];
        Gio.DBus.session.call(
            APP_ID, OBJECT_PATH, 'org.gtk.Actions', 'Activate',
            new GLib.Variant('(sava{sv})', [name, parameters, {}]),
            null, Gio.DBusCallFlags.NONE, -1, null,
            (connection, result) => {
                try {
                    connection.call_finish(result);
                } catch (error) {
                    console.warn(`Mexerica: ${name} falhou: ${error.message}`);
                }
            });
    }

    _onWindowCreated(window) {
        // On Wayland the title and app id arrive after creation; act once the window shows.
        const id = window.connect('shown', () => {
            window.disconnect(id);
            this._arrange(window);
        });
    }

    _arrange(window) {
        if (window.get_wm_class() !== APP_ID && window.get_gtk_application_id() !== APP_ID)
            return;
        const title = window.get_title();
        if (title === WHEEL_TITLE) {
            const [pointerX, pointerY] = global.get_pointer();
            const [x, y] = this._anchor ?? [pointerX, pointerY];
            const rect = window.get_frame_rect();
            const monitor = global.display.get_current_monitor();
            const area = global.workspace_manager.get_active_workspace().get_work_area_for_monitor(monitor);
            const left = Math.min(Math.max(x - rect.width / 2, area.x), area.x + area.width - rect.width);
            const top = Math.min(Math.max(y - rect.height / 2, area.y), area.y + area.height - rect.height);
            window.move_frame(true, Math.round(left), Math.round(top));
            window.make_above();
            Main.activateWindow(window);
        } else if (title === FLOAT_TITLE) {
            window.make_above();
            window.stick();
        }
    }
}
