"""My Whisper 用户设置持久化（NSUserDefaults）"""

from Foundation import NSUserDefaults

# Carbon modifier constants
CMD_KEY = 0x0100
SHIFT_KEY = 0x0200

DEFAULTS_KEY_KEYCODE = "shortcutKeyCode"
DEFAULTS_KEY_MODIFIERS = "shortcutModifiers"

DEFAULT_KEYCODE = 49  # Space
DEFAULT_MODIFIERS = CMD_KEY | SHIFT_KEY  # ⌘⇧


class Settings:
    def __init__(self):
        self._defaults = NSUserDefaults.standardUserDefaults()
        self._defaults.registerDefaults_({
            DEFAULTS_KEY_KEYCODE: DEFAULT_KEYCODE,
            DEFAULTS_KEY_MODIFIERS: DEFAULT_MODIFIERS,
        })

    @property
    def shortcut_keycode(self) -> int:
        return self._defaults.integerForKey_(DEFAULTS_KEY_KEYCODE)

    @shortcut_keycode.setter
    def shortcut_keycode(self, value: int):
        self._defaults.setInteger_forKey_(value, DEFAULTS_KEY_KEYCODE)

    @property
    def shortcut_modifiers(self) -> int:
        return self._defaults.integerForKey_(DEFAULTS_KEY_MODIFIERS)

    @shortcut_modifiers.setter
    def shortcut_modifiers(self, value: int):
        self._defaults.setInteger_forKey_(value, DEFAULTS_KEY_MODIFIERS)
