"""Text insertion by simulating keystrokes.

Neither the clipboard nor Ctrl+V is used. The clipboard belongs to the user,
and switching focus to another window is unreliable. Instead each fragment is
typed with KEYEVENTF_UNICODE SendInput events: that is keyboard layout
independent, needs no focus juggling, and lands exactly at the caret of the
window that is in front.

Vosk revises its own output while an utterance is still open, so every update
is applied as a diff against what was already typed: the shared prefix is kept,
the differing tail is erased with Backspace and retyped. Without that, words
get duplicated and corrected in place by the model.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import os
import time

import pyperclip

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_BACK = 0x08

_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class _KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wt.WORD),
        ("wScan", wt.WORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", _PTR),
    ]


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wt.LONG),
        ("dy", wt.LONG),
        ("mouseData", wt.DWORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", _PTR),
    ]


class _HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _InputUnion(ctypes.Union):
    _fields_ = [("ki", _KeyboardInput), ("mi", _MouseInput), ("hi", _HardwareInput)]


class _Input(ctypes.Structure):
    _anonymous_ = ("payload",)
    _fields_ = [("type", wt.DWORD), ("payload", _InputUnion)]


if ctypes.sizeof(_Input) != 40:
    raise RuntimeError(
        f"INPUT structure is {ctypes.sizeof(_Input)} bytes, expected 40 on x64"
    )

user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(_Input), ctypes.c_int]
user32.SendInput.restype = wt.UINT
user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
kernel32.CreateMutexW.restype = wt.HANDLE
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CloseHandle.restype = wt.BOOL

MAX_EVENTS = 512

_ERROR_ALREADY_EXISTS = 183
_instances: list[wt.HANDLE] = []


def acquire_single_instance(name: str) -> bool:
    """True when this process is the only instance, False if one is running."""
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        log.warning("single instance mutex could not be created")
        return True
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _instances.append(handle)
    return True


def _deliver(events: list[_Input]) -> None:
    if not events:
        return
    array = (_Input * len(events))(*events)
    sent = user32.SendInput(len(events), array, ctypes.sizeof(_Input))
    if sent != len(events):
        log.warning("SendInput delivered %d of %d events", sent, len(events))


def _char_events(text: str) -> list[_Input]:
    events: list[_Input] = []
    for offset in range(0, len(text), MAX_EVENTS // 2):
        chunk = text[offset:offset + MAX_EVENTS // 2]
        for code_unit in _utf16_units(chunk):
            down = _Input()
            down.type = INPUT_KEYBOARD
            down.ki = _KeyboardInput(0, code_unit, KEYEVENTF_UNICODE, 0, 0)
            up = _Input()
            up.type = INPUT_KEYBOARD
            up.ki = _KeyboardInput(0, code_unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)
            events.extend((down, up))
    return events


def _utf16_units(text: str) -> list[int]:
    raw = text.encode("utf-16-le")
    return [raw[i] | (raw[i + 1] << 8) for i in range(0, len(raw), 2)]


def press(vk: int, up: bool = False) -> None:
    """Send a single virtual key event, down or up."""
    down = _Input()
    down.type = INPUT_KEYBOARD
    down.ki = _KeyboardInput(vk, 0, 0, 0, 0)
    events = [down]
    if up:
        release = _Input()
        release.type = INPUT_KEYBOARD
        release.ki = _KeyboardInput(vk, 0, KEYEVENTF_KEYUP, 0, 0)
        events.append(release)
    _deliver(events)


def type_text(text: str) -> None:
    """Type text as if it were entered on the keyboard, layout independent."""
    events = _char_events(text)
    for index in range(0, len(events), MAX_EVENTS):
        _deliver(events[index:index + MAX_EVENTS])
    if events:
        log.info("typed %d character(s)", len(text))


def send_backspaces(count: int) -> None:
    """Erase count characters backwards, as the Delete key on Backspace."""
    if count <= 0:
        return
    events: list[_Input] = []
    for _ in range(count):
        down = _Input()
        down.type = INPUT_KEYBOARD
        down.ki = _KeyboardInput(VK_BACK, 0, 0, 0, 0)
        up = _Input()
        up.type = INPUT_KEYBOARD
        up.ki = _KeyboardInput(VK_BACK, 0, KEYEVENTF_KEYUP, 0, 0)
        events.extend((down, up))
    for index in range(0, len(events), MAX_EVENTS):
        _deliver(events[index:index + MAX_EVENTS])
    log.info("erased %d character(s)", count)


def foreign_in_front() -> bool:
    """True when the foreground window belongs to another process."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value != os.getpid()


def copy_to_clipboard(text: str) -> bool:
    if not text:
        return False
    try:
        pyperclip.copy(text)
    except Exception:
        log.exception("clipboard write failed")
        return False
    return True


class Typer:
    """Keeps the screen text in step with the recogniser, fragment by fragment.

    `apply` makes the characters to the right of the caret read exactly as
    `text`, by keeping the common prefix and retyping the rest. Pass
    `boundary=True` for a finished utterance, after which the next fragment
    starts from an empty prefix and is typed after what is already there.
    """

    def __init__(self, delay: float = 0.02) -> None:
        self._printed = ""
        self._delay = delay
        self.typed = 0
        self.erased = 0

    @property
    def printed(self) -> str:
        return self._printed

    def reset(self) -> None:
        self._printed = ""

    def apply(self, text: str, boundary: bool = False) -> bool:
        """Make the caret neighbourhood read exactly `text`, and report change.

        For a finished utterance the text is diffed against the partials that
        were typed for it, and the prefix is reset afterwards so the next
        utterance is typed after what is already on screen.
        """
        wanted = f"{text.strip()} " if text.strip() else ""
        if not foreign_in_front():
            if wanted:
                log.info("own window is in front, fragment held back")
            self._printed = ""
            return False
        changed = False
        if wanted != self._printed:
            common = 0
            limit = min(len(self._printed), len(wanted))
            while common < limit and self._printed[common] == wanted[common]:
                common += 1
            to_erase = len(self._printed) - common
            tail = wanted[common:]
            if to_erase:
                send_backspaces(to_erase)
                self.erased += to_erase
                changed = True
            if tail:
                type_text(tail)
                self.typed += len(tail)
                changed = True
            self._printed = wanted
            if self._delay and changed:
                time.sleep(self._delay)
        if boundary:
            self._printed = ""
        return changed
