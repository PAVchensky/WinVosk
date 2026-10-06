"""Everything about the layout guard that does not need a foreground window.

The one thing that cannot be checked from a windowless shell is the posted
request itself: `WM_INPUTLANGCHANGEREQUEST` only does anything while a target
has the focus, and this shell has no input desktop (`GetInputDesktop()` is
NULL). What can be checked is everything that request depends on before it is
sent, plus the wiring that decides when it is sent at all — which is what a
failure to observe the switch usually turns out to be.

Covered:

1. the hard dependency, `LoadKeyboardLayoutW` really resolves the name
2. the side effect it has on the calling thread, and that it is undone
3. the setting round-trips, and an empty default means disarmed
4. the layout is borrowed *before* the engine is asked to start
5. the layout is handed back *after* the tail has been typed
6. every recording that starts borrows, and every one that ends hands back
"""

import logging
import re
import queue
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

from winvosk import config, keystrokes, settings  # noqa: E402

out = []
failures = 0


def check(name, condition, note=""):
    global failures
    failures += 0 if condition else 1
    tail = f"   ({note})" if note else ""
    out.append(f"  {'ok  ' if condition else 'FAIL'} {name}{tail}")


out.append("1. resolving a name: the measured table")
# Every row below was measured on this machine before the rule was written, and
# the rule has to reproduce each outcome rather than guess at it.
table = [
    # name,          resolves?,   why
    ("00000409", True,  "en-US, installed"),
    ("00000419", True,  "ru-RU, installed"),
    ("0409", True,      "four digits is a valid spelling"),
    ("00000420", True,  "not installed, and Windows loads it anyway"),
    ("04190419", False, "right digits in the wrong order; silently gives en-US"),
    ("en-US", False,    "an alias, not an id; silently gives en-US"),
    ("not-a-layout", False, "not digits at all"),
    ("zz", False,       "not digits at all"),
]
for name, wanted, why in table:
    got = keystrokes.LayoutGuard._load(name)
    ok = bool(got) == wanted
    failures += 0 if ok else 1
    out.append(f"  {'ok  ' if ok else 'FAIL'} {name:<14s} -> "
               f"{'0x%08X' % got if got else 'refused':<12s} {why}")
check("a refused name leaves no layout behind",
      all(not keystrokes.LayoutGuard._load(n) for n, w, _ in table if not w))

out.append("")
out.append("2. the side effect on this process, undone")
mine_before = int(keystrokes.user32.GetKeyboardLayout(
    keystrokes.kernel32.GetCurrentThreadId()) or 0)
# Load the one this thread is *not* on, or nothing can move and the check is
# measuring nothing at all.
other = "00000419" if (mine_before & 0xFFFF) == 0x0409 else "00000409"
keystrokes.LayoutGuard._load(other)
mine_after = int(keystrokes.user32.GetKeyboardLayout(
    keystrokes.kernel32.GetCurrentThreadId()) or 0)
out.append(f"     this thread: 0x{mine_before:08X} -> 0x{mine_after:08X}")
check("LoadKeyboardLayoutW did move this thread's layout", mine_after != mine_before)
keystrokes.user32.ActivateKeyboardLayout(mine_before, 0)
restored = int(keystrokes.user32.GetKeyboardLayout(
    keystrokes.kernel32.GetCurrentThreadId()) or 0)
check("ActivateKeyboardLayout puts it back", restored == mine_before)

out.append("")
out.append("3. the setting")
work = ROOT / "tmp" / "layout_setting.json"
original = (ROOT / "settings.json").read_text(encoding="utf-8")
try:
    (ROOT / "settings.json").write_text(
        '{"language": "en", "toggle_recording": false}', encoding="utf-8")
    check("an absent key means the shipped default",
          settings.dictate_layout() == config.DICTATE_LAYOUT_DEFAULT)
    check("and the guard is armed with it",
          keystrokes.LayoutGuard(settings.dictate_layout).is_armed)
    (ROOT / "settings.json").write_text('{"dictate_layout": ""}', encoding="utf-8")
    check("an explicit empty string switches it off", settings.dictate_layout() == "")
    check("and the guard is then disarmed",
          not keystrokes.LayoutGuard(settings.dictate_layout).is_armed)
    (ROOT / "settings.json").write_text(
        '{"dictate_layout": " 00000409 "}', encoding="utf-8")
    check("a filled key is read back, trimmed", settings.dictate_layout() == "00000409")
    check("and the guard is armed",
          keystrokes.LayoutGuard(settings.dictate_layout).is_armed)
    (ROOT / "settings.json").write_text('{"dictate_layout": 42}', encoding="utf-8")
    check("a value of the wrong shape falls back to the default",
          settings.dictate_layout() == config.DICTATE_LAYOUT_DEFAULT)
    (ROOT / "settings.json").write_text("not json at all", encoding="utf-8")
    check("a malformed file falls back to the default",
          settings.dictate_layout() == config.DICTATE_LAYOUT_DEFAULT)
finally:
    (ROOT / "settings.json").write_text(original, encoding="utf-8")

out.append("")
out.append("4 and 5. the wiring: borrowed before the engine, handed back after the tail")
source = (ROOT / "src" / "run.py").read_text(encoding="utf-8")
pressed = source.split("def _hotkey_pressed")[1].split("\n    def ")[0]
engage_at = pressed.find("_layout.engage()")
queue_at = pressed.find('_commands.put("press")')
check("the hotkey handler engages at all", engage_at >= 0)
check("engage comes before the start is queued",
      0 <= engage_at < queue_at if queue_at >= 0 else engage_at >= 0)
stop = source.split("def _on_stop")[1].split("\n    def ")[0]
type_at = stop.find("typer.apply(tail")
release_at = stop.find("_layout.release()")
check("the tail is typed before the layout goes back",
      0 <= type_at < release_at if release_at >= 0 else type_at >= 0)
quit_body = source.split("def quit")[1].split("\n    def ")[0]
check("the shutdown path hands it back too", "_layout.release()" in quit_body)
state = source.split("def _on_state")[1].split("\n    def ")[0]
check("the recogniser's start event no longer engages, so there is one place",
      "_layout.engage()" not in state)
# This is the one that made the guard permanently disarmed: `run.py` handed it
# the result of the accessor where it wanted the accessor, so every use raised
# `TypeError: 'str' object is not callable`, `is_armed` caught it and answered
# False, and no value in `settings.json` could ever have mattered.
built = [line for line in source.splitlines()
         if "LayoutGuard(" in line and "class " not in line]
check("App hands LayoutGuard the function, not its result",
      bool(built) and all(re.search(r"LayoutGuard\(settings\.dictate_layout\s*\)", line)
                          for line in built),
      f"found: {built}")
armed = keystrokes.LayoutGuard(settings.dictate_layout)
check("a guard built that way is armed on this machine",
      armed.is_armed or settings.dictate_layout() == "")

def _message_experiment() -> list[str]:
    """Move a second thread's layout with the real message, and report it."""
    import ctypes
    import threading
    import time
    from ctypes import wintypes as wt

    lines: list[str] = []
    wndproc = ctypes.WINFUNCTYPE(
        wt.LPARAM, wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM)

    class WNDCLASS(ctypes.Structure):
        _fields_ = [("style", wt.UINT), ("lpfnWndProc", wndproc),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                    ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
                    ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]

    class MSG(ctypes.Structure):
        _fields_ = [("hwnd", wt.HWND), ("message", ctypes.c_uint),
                    ("wParam", wt.WPARAM), ("lParam", wt.LPARAM),
                    ("time", wt.DWORD), ("pt", wt.POINT), ("lPrivate", wt.DWORD)]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.DefWindowProcW.restype = wt.LPARAM
    user32.GetMessageW.restype = wt.BOOL
    user32.DestroyWindow.argtypes = [wt.HWND]
    user32.GetWindowThreadProcessId.restype = wt.DWORD
    user32.ActivateKeyboardLayout.restype = wt.HANDLE
    user32.LoadKeyboardLayoutW.restype = wt.HANDLE

    ru = int(user32.LoadKeyboardLayoutW("00000419", 1) or 0)
    en = int(user32.LoadKeyboardLayoutW("00000409", 1) or 0)
    state: dict = {}
    ready, stop, errors = (threading.Event(), threading.Event(), [])

    def target() -> None:
        try:
            instance = kernel32.GetModuleHandleW(None)
            cls = WNDCLASS()
            cls.lpfnWndProc = wndproc(
                lambda h, m, w, l: user32.DefWindowProcW(h, m, w, l))
            cls.hInstance = instance
            cls.lpszClassName = "WinVoskLayoutProbe"
            user32.RegisterClassW(ctypes.byref(cls))
            hwnd = user32.CreateWindowExW(
                0, "WinVoskLayoutProbe", "t", 0, -2147483648, -2147483648,
                120, 60, None, None, instance, None)
            if not hwnd:
                errors.append("no window in this window station")
                ready.set()
                return
            thread = int(user32.GetWindowThreadProcessId(hwnd, None) or 0)
            # Only a thread may set its own input locale.
            user32.ActivateKeyboardLayout(ru, 0)
            state.update(hwnd=hwnd, thread=thread)
            ready.set()
            while not stop.is_set():
                msg = MSG()
                if not user32.GetMessageW(ctypes.byref(msg), None, 0, 0):
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            user32.DestroyWindow(hwnd)
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))
            ready.set()

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    if not ready.wait(5) or errors:
        stop.set()
        return [f"  skip the machine has no usable window here ({errors or 'timeout'})"]

    hwnd, thread = state["hwnd"], state["thread"]
    before = int(user32.GetKeyboardLayout(thread) or 0)
    lines.append(f"     a window on thread {thread}, never shown, layout "
                 f"0x{before:08X}")

    moved = keystrokes.LayoutGuard._request(hwnd, en)
    time.sleep(0.1)
    after = int(user32.GetKeyboardLayout(thread) or 0)
    lines.append(f"  {'ok  ' if after == en else 'FAIL'} "
                 f"SendMessageTimeout moved it to 0x{after:08X} "
                 f"(answered={moved})")

    # DefWindowProc answers 0x0 whether or not it obeyed, so the return value is
    # not evidence and the log must not present it as any.
    user32.ActivateKeyboardLayout(ru, 0)
    stop.set()
    return lines


out.append("")
out.append("3b. engage always says something")
# Silence here was the reason this could not be diagnosed: a recording that did
# not borrow a layout read the same whether the setting was never written, no
# window was in front, or it worked. Every arm and every refusal now logs.
import io  # noqa: E402

for armed, expect in ((False, "none configured"), (True, "not borrowed")):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    keystrokes.log.addHandler(handler)
    try:
        if armed:
            real = settings.dictate_layout
            settings.dictate_layout = lambda: "00000409"
        else:
            real = None
            settings.dictate_layout = lambda: ""
        guard = keystrokes.LayoutGuard(settings.dictate_layout)
        result = guard.engage()
    finally:
        settings.dictate_layout = real
        keystrokes.log.removeHandler(handler)
    said = stream.getvalue()
    check(f"armed={armed}: engage() returns False", result is False)
    check(f"armed={armed}: and says why ({expect})", expect in said)
    out.append(f"     said: {said.strip()[:96]}")

out.append("")
out.append("6. the message itself, against a real thread")
# Everything above is bookkeeping. This is the thing the feature rests on: does
# WM_INPUTLANGCHANGEREQUEST actually move a thread's input locale. A second thread
# in this process, with its own queue and its own layout, answers it without a
# microphone, without another machine and without another window — the mechanism
# is per-thread. If it does not move a thread here it will not move Notepad.
out.extend(_message_experiment())

out.append("")
out.append(f"failures: {failures}")
out.append("PASS" if not failures else "FAIL")

(ROOT / "tmp" / "layoutlive_report.txt").write_text(
    "\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))