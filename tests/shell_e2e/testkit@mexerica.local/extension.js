// Test-only: lets the harness use org.gnome.Shell.Eval inside the throwaway headless shell.
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

export default class TestKit extends Extension {
    enable() {
        global.context.unsafe_mode = true;
    }

    disable() {
        global.context.unsafe_mode = false;
    }
}
