"""Carbon 全局快捷键模块 — 通过 ctypes 调用 RegisterEventHotKey"""

import ctypes
import ctypes.util
import logging
import struct

log = logging.getLogger("mywhisper")

# ─── Carbon framework ────────────────────────────────────────────────────────

_carbon_path = ctypes.util.find_library("Carbon")
_carbon = ctypes.cdll.LoadLibrary(_carbon_path)

# ─── Constants ────────────────────────────────────────────────────────────────

# Carbon modifier key masks
CMD_KEY = 0x0100
SHIFT_KEY = 0x0200
OPTION_KEY = 0x0800
CONTROL_KEY = 0x1000

# Carbon event class / kind
kEventClassKeyboard = int.from_bytes(b"keyb", "big")
kEventHotKeyPressed = 5

# OSStatus
noErr = 0

# EventTypeSpec struct: { EventClass (UInt32), EventKind (UInt32) }
class EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]

# EventHotKeyID struct: { signature (OSType/UInt32), id (UInt32) }
class EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]

# Carbon event handler callback type:
#   OSStatus handler(EventHandlerCallRef, EventRef, void *userData)
CarbonEventHandlerProc = ctypes.CFUNCTYPE(
    ctypes.c_int32,   # OSStatus return
    ctypes.c_void_p,  # EventHandlerCallRef
    ctypes.c_void_p,  # EventRef
    ctypes.c_void_p,  # userData
)

# ─── Carbon function prototypes ──────────────────────────────────────────────

_carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
_carbon.GetApplicationEventTarget.argtypes = []

_carbon.InstallEventHandler.restype = ctypes.c_int32
_carbon.InstallEventHandler.argtypes = [
    ctypes.c_void_p,                    # EventTargetRef
    CarbonEventHandlerProc,             # EventHandlerUPP
    ctypes.c_uint32,                    # numTypes
    ctypes.POINTER(EventTypeSpec),      # list
    ctypes.c_void_p,                    # userData
    ctypes.POINTER(ctypes.c_void_p),    # outRef
]

_carbon.RegisterEventHotKey.restype = ctypes.c_int32
_carbon.RegisterEventHotKey.argtypes = [
    ctypes.c_uint32,                    # hotKeyCode
    ctypes.c_uint32,                    # hotKeyModifiers
    EventHotKeyID,                      # hotKeyID
    ctypes.c_void_p,                    # target
    ctypes.c_uint32,                    # options
    ctypes.POINTER(ctypes.c_void_p),    # outRef
]

_carbon.UnregisterEventHotKey.restype = ctypes.c_int32
_carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]

# ─── Keycode → display name ──────────────────────────────────────────────────

KEYCODE_TO_NAME = {
    0: "A", 1: "S", 2: "D", 3: "F", 4: "H", 5: "G", 6: "Z", 7: "X",
    8: "C", 9: "V", 11: "B", 12: "Q", 13: "W", 14: "E", 15: "R",
    16: "Y", 17: "T", 18: "1", 19: "2", 20: "3", 21: "4", 22: "6",
    23: "5", 24: "=", 25: "9", 26: "7", 27: "-", 28: "8", 29: "0",
    30: "]", 31: "O", 32: "U", 33: "[", 34: "I", 35: "P", 36: "Return",
    37: "L", 38: "J", 39: "'", 40: "K", 41: ";", 42: "\\", 43: ",",
    44: "/", 45: "N", 46: "M", 47: ".", 48: "Tab", 49: "Space",
    50: "`", 53: "Esc",
    96: "F5", 97: "F6", 98: "F7", 99: "F3", 100: "F8", 101: "F9",
    103: "F11", 105: "F13", 107: "F14", 109: "F10", 111: "F12",
    113: "F15", 118: "F4", 120: "F2", 122: "F1",
    123: "←", 124: "→", 125: "↓", 126: "↑",
}

# ─── Modifier formatting ─────────────────────────────────────────────────────

_MOD_SYMBOLS = [
    (CONTROL_KEY, "⌃"),
    (OPTION_KEY, "⌥"),
    (SHIFT_KEY, "⇧"),
    (CMD_KEY, "⌘"),
]


def format_shortcut(key_code: int, carbon_modifiers: int) -> str:
    """格式化快捷键为可读字符串，如 ⌘⇧Space"""
    parts = [sym for mask, sym in _MOD_SYMBOLS if carbon_modifiers & mask]
    parts.append(KEYCODE_TO_NAME.get(key_code, f"Key{key_code}"))
    return "".join(parts)


# ─── GlobalHotkey class ──────────────────────────────────────────────────────

class GlobalHotkey:
    """注册/注销 Carbon 全局快捷键"""

    _SIGNATURE = int.from_bytes(b"MWsp", "big")  # My Whisper
    _NEXT_ID = 1

    def __init__(self, callback):
        """callback: 无参函数，快捷键触发时调用"""
        self._callback = callback
        self._hotkey_ref = None
        self._handler_ref = None
        self._handler_proc = None  # prevent GC of the ctypes callback

    def register(self, key_code: int, carbon_modifiers: int) -> bool:
        """注册全局快捷键。返回 True 表示成功。"""
        self.unregister()

        # Install Carbon event handler (only once, but re-install is safe)
        self._handler_proc = CarbonEventHandlerProc(self._on_hotkey_event)

        event_type = EventTypeSpec(kEventClassKeyboard, kEventHotKeyPressed)
        handler_ref = ctypes.c_void_p()
        status = _carbon.InstallEventHandler(
            _carbon.GetApplicationEventTarget(),
            self._handler_proc,
            1,
            ctypes.byref(event_type),
            None,
            ctypes.byref(handler_ref),
        )
        if status != noErr:
            log.error("InstallEventHandler failed: %d", status)
            return False
        self._handler_ref = handler_ref

        # Register the hotkey
        hotkey_id = EventHotKeyID(self._SIGNATURE, GlobalHotkey._NEXT_ID)
        GlobalHotkey._NEXT_ID += 1

        hotkey_ref = ctypes.c_void_p()
        status = _carbon.RegisterEventHotKey(
            key_code,
            carbon_modifiers,
            hotkey_id,
            _carbon.GetApplicationEventTarget(),
            0,
            ctypes.byref(hotkey_ref),
        )
        if status != noErr:
            log.error("RegisterEventHotKey failed: %d (keyCode=%d, mods=0x%x)",
                      status, key_code, carbon_modifiers)
            return False

        self._hotkey_ref = hotkey_ref
        log.info("Global hotkey registered: %s (keyCode=%d, mods=0x%x)",
                 format_shortcut(key_code, carbon_modifiers), key_code, carbon_modifiers)
        return True

    def unregister(self):
        """注销当前全局快捷键"""
        if self._hotkey_ref is not None:
            _carbon.UnregisterEventHotKey(self._hotkey_ref)
            self._hotkey_ref = None
            log.info("Global hotkey unregistered")

    def _on_hotkey_event(self, handler_call_ref, event_ref, user_data):
        """Carbon 事件回调 — 触发时调用 callback"""
        try:
            self._callback()
        except Exception as e:
            log.error("Hotkey callback error: %s", e, exc_info=True)
        return noErr
