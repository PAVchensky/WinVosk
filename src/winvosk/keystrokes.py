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
from collections.abc import Callable

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
user32.GetKeyboardLayout.argtypes = [wt.DWORD]
user32.GetKeyboardLayout.restype = wt.HANDLE
user32.LoadKeyboardLayoutW.argtypes = [wt.LPCWSTR, wt.DWORD]
user32.LoadKeyboardLayoutW.restype = wt.HANDLE
user32.ActivateKeyboardLayout.argtypes = [wt.HANDLE, wt.DWORD]
user32.ActivateKeyboardLayout.restype = wt.HANDLE
user32.PostMessageW.argtypes = [wt.HWND, ctypes.c_uint, ctypes.c_ulonglong,
                                ctypes.c_longlong]
user32.PostMessageW.restype = wt.BOOL

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.GetCurrentThreadId.restype = wt.DWORD
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


# How long to let the shell finish a layout change before typing at it, and
# before restoring it. The request itself is posted rather than sent, so it is
# handled on the target's own thread some time after it is queued; measured with
# tools\layout_probe.py, a tenth of a second was not enough for the request to
# show up in `GetKeyboardLayout` and four was comfortable.
LAYOUT_SETTLE = 0.4
LAYOUT_RESTORE_SETTLE = 0.15

WM_INPUTLANGCHANGEREQUEST = 0x0050


class LayoutGuard:
    """Lend the foreground window a keyboard layout for the length of a recording.

    The characters this module sends are `KEYEVENTF_UNICODE`, so the layout of
    the target cannot change what they become. It matters anyway, because a
    keyboard hook on the chain is looking at layouts rather than at codepoints:
    a layout switcher with auto-replace on rewrites what it believes was typed,
    and on the machine this was found on it turned `содержать одинаковые данные`
    into `содержат?D>D>/Bd.bm й данное` while the log recorded every character
    sent as correct Cyrillic. Borrowing a layout for the length of a sentence
    takes the trigger away without touching a single character.

    Three things make it safe rather than clever:

    - The original layout is read from the target thread and posted back to the
      same window afterwards, so whatever the user had is what they get. Two
      toggles would also restore any starting state; this restores the exact one.
    - Nothing is switched unless a layout was named, so a machine with no
      switcher and no setting never sees its layout move.
    - `release` is idempotent and is called from the shutdown path as well as
      the stop path, because a layout left in English is a user's morning
      surprise rather than a log line.
    """

    def __init__(self, layout: "Callable[[], str]") -> None:
        # A callable and not a string, so the setting is read when a recording
        # starts rather than when the process did: every other setting in this
        # application is read from disk on use, and this one is the only value
        # the guard holds on to.
        self._read_layout = layout
        self._window = 0
        self._previous = 0

    @property
    def is_armed(self) -> bool:
        """Whether a layout is configured at all. Empty means never touch it."""
        try:
            return bool(str(self._read_layout() or "").strip())
        except Exception:
            log.exception("the dictation layout setting could not be read")
            return False

    @property
    def is_held(self) -> bool:
        return bool(self._window)

    def engage(self) -> bool:
        """Ask the foreground window for the configured layout, and keep the old.

        False when nothing was switched, which is the ordinary case: no layout
        configured, the panel rather than a target in front, the target already
        on that layout, or the shell declining the request. None of those are
        errors, so none of them are logged as one.
        """
        if not self.is_armed or self._window:
            return False
        name = str(self._read_layout() or "").strip()
        window = int(user32.GetForegroundWindow() or 0)
        if not window or not foreign_in_front():
            return False
        thread = user32.GetWindowThreadProcessId(window, None)
        previous = int(user32.GetKeyboardLayout(thread) or 0)
        wanted = self._load(name)
        if not wanted or wanted == previous:
            return False
        # `LoadKeyboardLayoutW` also activates the layout for the *calling*
        # thread as a side effect. This process has no text of its own except
        # the hotkey capture field, so it is put back rather than left changed.
        own = int(user32.GetKeyboardLayout(kernel32.GetCurrentThreadId()) or 0)
        if not self._post(window, wanted):
            user32.ActivateKeyboardLayout(own, 0) if own else None
            return False
        time.sleep(LAYOUT_SETTLE)
        if int(user32.GetKeyboardLayout(thread) or 0) != wanted:
            # The shell did not take it. Forget the window so `release` cannot
            # post a layout change that was never ours to undo.
            user32.ActivateKeyboardLayout(own, 0) if own else None
            log.info("the layout did not change to %s, leaving it alone", name)
            return False
        if own:
            user32.ActivateKeyboardLayout(own, 0)
        self._window = window
        self._previous = previous
        log.info("layout %s borrowed for the recording, 0x%08X put back afterwards",
                 name, previous)
        return True

    def release(self) -> bool:
        """Put the remembered layout back on the window it was taken from."""
        window, previous = self._window, self._previous
        self._window = self._previous = 0
        if not window or not previous:
            return False
        ok = self._post(window, previous)
        time.sleep(LAYOUT_RESTORE_SETTLE)
        log.info("layout put back on 0x%08X%s", window, "" if ok else " (refused)")
        return ok

    @staticmethod
    def _load(name: str) -> int:
        return int(user32.LoadKeyboardLayoutW(name, 1) or 0)

    @staticmethod
    def _post(window: int, hkl: int) -> bool:
        return bool(user32.PostMessageW(
            window, WM_INPUTLANGCHANGEREQUEST, 0, hkl))


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

        The separating space belongs to `boundary` and to nothing else. Adding
        it to every fragment put a space inside any word the model went on to
        extend, so every such extension had to erase that space again before
        typing the rest of the word. On the sentence from the bug report,
        arriving the way a recogniser sends it, word by word:

            before   'полный '  'список '  'ии '  'браузер '
                     then Backspace x1, because 'браузер' became
                     'браузерных' and the fragment's trailing space was
                     standing in the middle of it
                     then Backspace x1 again for 'ней' -> 'нейросетей'

            after    'полный'  ' список'  ' ии'  ' браузер'
                     then no Backspace at all: 2 down to 0, and the screen
                     ends on exactly the same text

        One letter at a time, where the model revises nearly every fragment, is
        24 Backspaces down to 12 on «полный список». What is left is a genuine
        rewrite, where the model took a word back, which no rule can avoid.

        That matters beyond tidiness. A Backspace is the one keystroke here that
        is not sent as `KEYEVENTF_UNICODE`: it goes out as a real `VK_BACK`, so
        it is the one event on the chain a keyboard hook can act on by layout.
        A keyboard layout switcher that swallows it leaves the space standing
        where the word grew, which is how `ии` turns into `и и` on screen while
        the transcript stays correct. Fewer Backspaces is fewer chances for that.
        """
        core = text.strip()
        wanted = f"{core} " if boundary and core else core
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
            # What was on the screen, what it should read, and what moved. The
            # counts alone cannot explain a bug report: a line that came out as
            # gibberish is either a mangled `tail` or a swallowed Backspace, and
            # only the text says which. An erase that reaches back to the first
            # character means the model rewrote the whole utterance, which is the
            # widest window we ever hand a keyboard hook, so it is worth seeing.
            log.info(
                "text %r was %r: erased %d, typed %r",
                wanted, self._printed, to_erase, tail,
            )
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
