"""Global hotkey through a WH_KEYBOARD_LL low level hook.

The `keyboard` package cannot be used for this: version 0.13.5 (and current
master) contains `while not GetMessage(msg, 0, 0, 0)` in
`keyboard/_winkeyboard.py:563`. GetMessage returns a positive value when a
message was retrieved, so that loop body never runs, the message queue is
never pumped and the hook never fires. Verified empirically: even a plain F12
hotkey was never delivered. So the hook is implemented here directly.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import threading
from collections.abc import Iterable

from . import text

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

HC_ACTION = 0
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
WH_KEYBOARD_LL = 13

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C

_MODIFIERS: dict[str, frozenset[int]] = {
    "win": frozenset({VK_LWIN, VK_RWIN}),
    "ctrl": frozenset({VK_CONTROL, 0xA2, 0xA3}),
    "alt": frozenset({VK_MENU, 0xA4, 0xA5}),
    "shift": frozenset({VK_SHIFT, 0xA0, 0xA1}),
    "lwin": frozenset({VK_LWIN}),
    "rwin": frozenset({VK_RWIN}),
    "lctrl": frozenset({VK_CONTROL}),
    "rctrl": frozenset({0xA3}),
    "lalt": frozenset({VK_MENU}),
    "ralt": frozenset({0xA5}),
    "lshift": frozenset({VK_SHIFT}),
    "rshift": frozenset({0xA1}),
}

_NAMED: dict[str, int] = {
    "right": 0x27, "left": 0x25, "up": 0x26, "down": 0x28,
    "home": 0x24, "end": 0x23, "insert": 0x2D, "delete": 0x2E,
    "page_up": 0x21, "pageup": 0x21, "page_down": 0x22, "pagedown": 0x22,
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "esc": 0x1B, "escape": 0x1B, "backspace": 0x08, "caps_lock": 0x14,
    "print_screen": 0x2C, "menu": 0x5D, "pause": 0x13,
    # The Menu key is called both things depending on who is writing it down.
    # `name_for` still answers `menu`, because `_NAMED_BY_VK` sorts by code then
    # name and lets the last one win, so this is only ever accepted on the way in.
    "apps": 0x5D, "context_menu": 0x5D,
    **{f"f{index}": 0x6F + index for index in range(1, 25)},
}

# Fixed order, so the same combination always produces the same spec string.
_MODIFIER_ORDER = ("ctrl", "alt", "shift", "win")

# Left and right variants folded onto the generic name, which is what a
# combination recorded with the left Ctrl has to keep working with.
_GENERIC_MODIFIERS: dict[int, str] = {
    vk: name for name in _MODIFIER_ORDER for vk in _MODIFIERS[name]
}

# Reverse of `_NAMED`. Aliases such as "esc"/"escape" share one code; sorting
# by (code, name) and letting the last one win keeps `name_for` deterministic.
_NAMED_BY_VK: dict[int, str] = {
    vk: name for name, vk in sorted(_NAMED.items(), key=lambda item: (item[1], item[0]))
}

_KEY_DOWN = frozenset({WM_KEYDOWN, WM_SYSKEYDOWN})
_KEY_UP = frozenset({WM_KEYUP, WM_SYSKEYUP})


class _KeyboardHookStruct(ctypes.Structure):
    _fields_ = [
        ("vkCode", wt.DWORD),
        ("scanCode", wt.DWORD),
        ("flags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


_LOW_LEVEL_PROC = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int, wt.WPARAM, wt.LPARAM
)

user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int, _LOW_LEVEL_PROC, wt.HMODULE, wt.DWORD
]
user32.SetWindowsHookExW.restype = wt.HHOOK
user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_long
user32.UnhookWindowsHookEx.argtypes = [wt.HHOOK]
user32.UnhookWindowsHookEx.restype = wt.BOOL
user32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.PostThreadMessageW.restype = wt.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.GetMessageW.restype = wt.LONG
user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HMODULE
kernel32.GetCurrentThreadId.restype = wt.DWORD


class HotkeyError(RuntimeError):
    pass


def _keys_for(part: str) -> frozenset[int]:
    name = part.strip().lower()
    if name in _MODIFIERS:
        return _MODIFIERS[name]
    if name in _NAMED:
        return frozenset({_NAMED[name]})
    if len(name) == 1:
        code = ord(name)
        if 0x61 <= code <= 0x7A:
            return frozenset({code - 0x20})
        if 0x30 <= code <= 0x39 or code in (0x2D, 0x3D, 0x5B, 0x5D, 0x5C, 0x3B, 0x27):
            return frozenset({code})
    raise HotkeyError(
        f"unknown key name: {part!r}. Use a modifier (win, ctrl, alt, shift), "
        f"a named key ({', '.join(sorted(_NAMED)[:8])}, ...) or a latin letter or digit"
    )


def parse(spec: str) -> tuple[frozenset[int], list[frozenset[int]]]:
    """'win+ctrl+right' -> (right virtual keys, [win keys, ctrl keys])."""
    parts = [part for part in spec.lower().split("+") if part.strip()]
    if len(parts) < 2:
        raise HotkeyError(f"need at least a modifier and a key, got {spec!r}")
    *modifiers, main = parts
    return _keys_for(main), [_keys_for(part) for part in modifiers]


def name_for(vk: int) -> str | None:
    """Reverse of `_keys_for`: a virtual key code as a name `parse` accepts.

    Letters arrive as uppercase ASCII and digits as themselves. None is
    returned for a key that cannot be named, and the caller must refuse to
    build a spec out of it rather than store something that will not match.
    """
    if vk in _GENERIC_MODIFIERS:
        return _GENERIC_MODIFIERS[vk]
    if 0x41 <= vk <= 0x5A:
        return chr(vk + 0x20)
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    return _NAMED_BY_VK.get(vk)


class HotkeyListener:
    """Fires when every modifier and the main key of any combination are held.

    Only the main key is blocked in the hook, so the modifiers always reach
    the foreground application and can never be left stuck down. Blocking the
    main key is what keeps Windows from acting on the combination itself.

    With `on_release` given the listener becomes push to talk: the press
    callback runs when the main key goes down and the release callback when it
    comes back up. Auto repeat is ignored, so holding the keys does not fire
    a stream of presses. The modifiers may stay held between pushes, so a
    second press on the main key starts again.

    `start_capture` switches the same hook into recording a new combination,
    where every key is swallowed and no callback runs. See its docstring.
    """

    def __init__(self, specs: str | Iterable[str], on_press, on_release=None) -> None:
        self.specs = (specs,) if isinstance(specs, str) else tuple(specs)
        if not self.specs:
            raise HotkeyError("no hotkey given")
        self._on_press = on_press
        self._on_release = on_release
        self._combos = [parse(spec) for spec in self.specs]
        self._pressed: set[int] = set()
        self._blocked: set[int] = set()
        self._capture = False
        self._capture_modifiers: set[str] = set()
        self._capture_result: tuple[str, str] | None = None
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._handle = None
        self._ready = threading.Event()
        self._proc = _LOW_LEVEL_PROC(self._on_event)

    @property
    def is_active(self) -> bool:
        return self._handle is not None

    @property
    def is_push_to_talk(self) -> bool:
        return self._on_release is not None

    @property
    def is_capturing(self) -> bool:
        return self._capture

    def start_capture(self) -> None:
        """Record a new combination instead of dictating, until told to stop.

        Off by default. While it is on, `_on_event` returns 1 for every key and
        neither callback runs, so a bare Win cannot open the Start menu, Win+D
        cannot minimise everything and the recorded keys cannot start a
        recording. This has to run through the hook rather than a Tk binding:
        Tk only sees keys while its own window has the focus, and never sees
        the Windows key at all, so it could not record `win+ctrl+right`.

        Nothing here touches Tk. The hook thread only writes `_capture_result`
        under the lock, and the Tk thread collects it with `poll_capture`.
        """
        with self._lock:
            self._capture_modifiers.clear()
            self._capture_result = None
            self._capture = True

    def stop_capture(self) -> None:
        with self._lock:
            self._capture = False
            self._capture_modifiers.clear()
            self._capture_result = None

    def poll_capture(self) -> tuple[str, str] | None:
        """Take the capture result and rearm. Tk thread only.

        Returns ("ok", spec) for a usable combination, ("cancel", "") for Esc,
        ("invalid", reason) for something that cannot become a spec, or None
        when the user has not finished yet.
        """
        with self._lock:
            result, self._capture_result = self._capture_result, None
            return result

    def _capture_key(self, vk: int, message: int) -> None:
        """Fold one swallowed key into the capture. Caller holds the lock."""
        if not self._capture:
            # The capture ended the moment its result was taken, and the keys
            # the user lets go of afterwards are not part of anything. Checked
            # here rather than left to the caller, so the state machine is right
            # on its own terms and not only by the way it happens to be reached.
            return
        if self._capture_result is not None:
            return  # already decided, the Tk thread has not picked it up yet
        name = name_for(vk)
        if message in _KEY_UP:
            if name in _MODIFIER_ORDER:
                self._capture_modifiers.discard(name)
                if not self._capture_modifiers:
                    # Everything they pressed was a modifier and all of it is up
                    # again, so that was not a combination. This is the first
                    # moment it can be said: while a key is still held the main
                    # key may still be coming. Saying it here rather than on the
                    # last key down keeps a capture that is still in progress
                    # from being judged by what it has only just started.
                    self._capture_result = (
                        "invalid", text.t("capture_needs_main_key"),
                    )
            return
        if message not in _KEY_DOWN:
            return
        if name is None:
            self._capture_result = ("invalid", text.t("capture_unnamed_key"))
            return
        if vk == _NAMED["esc"]:
            # Reserved for cancelling, so it can never become a main key. The
            # code is compared, not the name: `name_for` picks one alias.
            self._capture_result = ("cancel", "")
            return
        if name in _MODIFIER_ORDER:
            self._capture_modifiers.add(name)
            return
        if not self._capture_modifiers:
            self._capture_result = ("invalid", text.t("capture_needs_modifier"))
            return
        order = [part for part in _MODIFIER_ORDER if part in self._capture_modifiers]
        self._capture_result = ("ok", "+".join([*order, name]))

    def _match(self) -> int | None:
        """The main key of a satisfied combination, or None."""
        for main, modifiers in self._combos:
            if not self._pressed & main:
                continue
            if all(self._pressed & group for group in modifiers):
                return next(iter(main))
        return None

    def _on_event(self, code: int, message: int, event_ptr: int) -> int:
        if code != HC_ACTION:
            return user32.CallNextHookEx(None, code, message, event_ptr)
        try:
            data = ctypes.cast(event_ptr, ctypes.POINTER(_KeyboardHookStruct)).contents
            vk = int(data.vkCode)
            with self._lock:
                if self._capture:
                    self._capture_key(vk, message)
                    return 1  # swallow everything, matched or not
                blocked = False
                action = None
                if message in _KEY_UP:
                    self._pressed.discard(vk)
                    if vk in self._blocked:
                        self._blocked.discard(vk)
                        blocked = True
                        if self._on_release is not None:
                            action = "release"
                elif message in _KEY_DOWN:
                    self._pressed.add(vk)
                    if vk in self._blocked:
                        # Auto repeat of a key this hook is already blocking,
                        # which Windows sends for as long as the key is held.
                        # It has to be swallowed as well: the application never
                        # saw the first keydown, so a repeat that gets through
                        # is a keydown out of nowhere, and that is enough to
                        # open a context menu behind a swallowed press.
                        #
                        # Tested on `vk`, not on "the combination matched": a
                        # held combination still matches for every other key
                        # pressed alongside it, and swallowing on that would eat
                        # the user's typing. Only the blocked key is ours.
                        blocked = True
                    matched = self._match()
                    if matched is not None and matched not in self._blocked:
                        self._blocked.add(matched)
                        blocked = True
                        action = "press"
        except Exception:
            log.exception("hotkey hook failed")
            return user32.CallNextHookEx(None, code, message, event_ptr)
        if blocked:
            if action:
                log.info("hotkey %s", action)
                self._dispatch(action)
            return 1
        return user32.CallNextHookEx(None, code, message, event_ptr)

    def _dispatch(self, action: str) -> None:
        callback = self._on_press if action == "press" else self._on_release
        threading.Thread(
            target=self._run_callback, args=(callback,), name=f"hotkey-{action}", daemon=True
        ).start()

    def _run_callback(self, callback) -> None:
        try:
            callback()
        except Exception:
            log.exception("hotkey callback failed")

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        module = kernel32.GetModuleHandleW(None)
        self._handle = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, module, 0)
        self._ready.set()
        if not self._handle:
            log.error(
                "SetWindowsHookExW failed, error %d", ctypes.get_last_error()
            )
            self._handle = None
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            return
        log.info("hotkey hook active: %s", " / ".join(self.specs))
        message = wt.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

    def start(self, timeout: float = 3.0) -> bool:
        if self._thread is not None:
            return self.is_active
        self._thread = threading.Thread(
            target=self._run, name="hotkey-hook", daemon=True
        )
        self._thread.start()
        self._ready.wait(timeout)
        return self.is_active

    def stop(self) -> None:
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        # The handle is re-read after the join, not taken from before it: when
        # start() timed out, the thread can still reach SetWindowsHookExW after
        # the WM_QUIT decision above was made on a thread id of 0. Unhooking
        # what appeared in the meantime is what keeps a stopped listener from
        # leaving an invisible second hotkey behind. The thread is dropped too,
        # so a stopped instance does not claim to be running.
        if self._handle:
            user32.UnhookWindowsHookEx(self._handle)
            self._handle = None
        self._thread = None
        log.info("hotkey hook removed")
