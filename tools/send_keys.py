"""Send a keystroke combination through SendInput (verification helper)."""

import ctypes
import ctypes.wintypes as wt
import sys
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)
_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1


class KI(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", _PTR)]


class MI(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", _PTR)]


class HI(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class U(ctypes.Union):
    _fields_ = [("ki", KI), ("mi", MI), ("hi", HI)]


class IN(ctypes.Structure):
    _anonymous_ = ("p",)
    _fields_ = [("type", wt.DWORD), ("p", U)]


assert ctypes.sizeof(IN) == 40, ctypes.sizeof(IN)
user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(IN), ctypes.c_int]
user32.SendInput.restype = wt.UINT

COMBOS = {
    "win+ctrl+right": [0x5B, 0x11, 0x27],
    "win+ctrl+left": [0x5B, 0x11, 0x25],
    "alt+win": [0x12, 0x5B],
    "ctrl+alt+v": [0x11, 0x12, 0x56],
    "win": [0x5B],
    "alt": [0x12],
}


def tap(keys, hold=0.06):
    down = (IN * len(keys))()
    for index, vk in enumerate(keys):
        down[index].type = INPUT_KEYBOARD
        down[index].ki = KI(vk, 0, 0, 0, 0)
    sent_down = user32.SendInput(len(keys), down, ctypes.sizeof(IN))
    time.sleep(hold)
    up = (IN * len(keys))()
    for index, vk in enumerate(keys):
        up[index].type = INPUT_KEYBOARD
        up[index].ki = KI(vk, 0, KEYEVENTF_KEYUP, 0, 0)
    sent_up = user32.SendInput(len(keys), up, ctypes.sizeof(IN))
    return sent_down, sent_up


if __name__ == "__main__":
    keys = COMBOS.get(sys.argv[1])
    if keys is None:
        raise SystemExit(f"unknown combination: {sys.argv[1]}")
    print("sent", sys.argv[1], tap(keys), "err", ctypes.get_last_error())
