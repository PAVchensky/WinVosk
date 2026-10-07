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
# The switcher's own combination is pressed for the same length of time, and a
# switcher still rewriting words is a worse recording than no layout lent at all,
# so it goes first and it comes back last: while the layout is going back, the
# switcher has to be quiet.
mute_at = pressed.find("_switcher.engage()")
check("the switcher is asked to be quiet before the layout is borrowed",
      0 <= mute_at < engage_at if engage_at >= 0 else mute_at >= 0,
      f"mute at {mute_at}, engage at {engage_at}")
check("it is asked before the start is queued too",
      0 <= mute_at < queue_at if queue_at >= 0 else mute_at >= 0)
check("both presses of the hotkey engage it, so toggle mode is covered as well",
      pressed.count("_switcher.engage()") == 2
      and pressed.count("_layout.engage()") == 2)
stop = source.split("def _on_stop")[1].split("\n    def ")[0]
type_at = stop.find("typer.apply(tail")
hand_back_at = stop.find("_release_keyboards()")
check("the tail is typed before the keyboard is handed back",
      0 <= type_at < hand_back_at if hand_back_at >= 0 else type_at >= 0)
# The two guards are released from one place so neither can strand the other,
# each in its own `try`: until 2.1.0 a raising layout release aborted `_on_stop`
# before the switcher was pressed a second time, which left a switcher muted for
# the rest of the session with no way to see it from here.
hand_back = source.split("def _release_keyboards")[1].split("\n    def ")[0]
layout_at = hand_back.find("self._layout.release")
switcher_at = hand_back.find("self._switcher.release")
check("both guards are released there",
      layout_at >= 0 and switcher_at >= 0)
check("the layout goes back before the switcher is asked to speak again",
      0 <= layout_at < switcher_at if switcher_at >= 0 else layout_at >= 0)
check("each is released in a try of its own",
      "for what, release in" in hand_back and hand_back.count("try:") == 1
      and "except Exception" in hand_back and "log.exception" in hand_back)
quit_body = source.split("def quit")[1].split("\n    def ")[0]
check("the shutdown path hands them back too", "_release_keyboards()" in quit_body)
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
# The same mistake, in the same place, for the guard that came with it: handed the
# value, every use raises `TypeError: 'str' object is not callable`.
built = [line for line in source.splitlines()
         if "SwitcherGuard(" in line and "class " not in line]
check("App hands SwitcherGuard the function, not its result",
      bool(built) and all(re.search(r"SwitcherGuard\(settings\.switcher_key\s*\)", line)
                          for line in built),
      f"found: {built}")
switcher = keystrokes.SwitcherGuard(settings.switcher_key)
check("that guard is armed exactly when a combination is configured",
      switcher.is_armed is bool(settings.switcher_key().strip()))

def _target_window(layout: int) -> dict:
    """Start a window on a thread of its own, with `layout` already active.

    Returns a dict with the `user32` it was built against, the window, its thread,
    an `Event` that ends it, and anything that went wrong. The window is never
    shown: only a thread may set its own input locale, and this one pumps its own
    queue, which is all `WM_INPUTLANGCHANGEREQUEST` needs.
    """
    import ctypes
    import threading
    from ctypes import wintypes as wt

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
    # Argtypes as well as the restype: without them the 64-bit lparam arrives as a
    # Python int, the call raises inside the callback, and a callback that raises
    # leaves the window handling nothing at all — while the exception is only ever
    # printed by the interpreter, so the probe looked like it had run.
    user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    user32.GetMessageW.restype = wt.BOOL
    user32.DestroyWindow.argtypes = [wt.HWND]
    user32.GetWindowThreadProcessId.restype = wt.DWORD
    user32.ActivateKeyboardLayout.restype = wt.HANDLE
    user32.LoadKeyboardLayoutW.restype = wt.HANDLE

    state: dict = {"stop": threading.Event(), "errors": [],
                   "ready": threading.Event()}

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
                state["errors"].append("no window in this window station")
                state["ready"].set()
                return
            thread = int(user32.GetWindowThreadProcessId(hwnd, None) or 0)
            # Only a thread may set its own input locale.
            user32.ActivateKeyboardLayout(layout, 0)
            state.update(hwnd=hwnd, thread=thread)
            state["ready"].set()
            while not state["stop"].is_set():
                msg = MSG()
                if not user32.GetMessageW(ctypes.byref(msg), None, 0, 0):
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            user32.DestroyWindow(hwnd)
        except Exception as exc:  # noqa: BLE001
            state["errors"].append(repr(exc))
            state["ready"].set()

    state["worker"] = threading.Thread(target=target, daemon=True)
    state["worker"].start()
    state["ready"].wait(5)
    return state


def _message_experiment() -> list[str]:
    """Move a second thread's layout with the real message, and report it."""
    import ctypes
    import threading
    import time
    from ctypes import wintypes as wt

    lines: list[str] = []
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.ActivateKeyboardLayout.restype = wt.HANDLE
    user32.LoadKeyboardLayoutW.restype = wt.HANDLE
    user32.GetKeyboardLayout.restype = wt.HANDLE

    ru = int(user32.LoadKeyboardLayoutW("00000419", 1) or 0)
    en = int(user32.LoadKeyboardLayoutW("00000409", 1) or 0)
    state = _target_window(ru)
    stop, errors = state["stop"], state["errors"]
    if not state.get("hwnd") or errors:
        stop.set()
        return [f"  skip the machine has no usable window here "
                f"({errors or 'timeout'})"]

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
#
# The armed case pins the refusal to "no foreign window in front", so
# `foreign_in_front` is stubbed rather than left to whatever the machine happens
# to have open. Without that this case read differently on a locked desktop than
# on an unlocked one, and it passed for the wrong reason on both: a session with
# no foreground window refuses for that reason instead of the one asserted, and an
# unlocked one borrows a layout from the console instead of refusing at all.
import io  # noqa: E402

real_foreign = keystrokes.foreign_in_front
for armed, expect in ((False, "none configured"), (True, "not borrowed")):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    keystrokes.log.addHandler(handler)
    keystrokes.foreign_in_front = lambda: False
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
        keystrokes.foreign_in_front = real_foreign
        keystrokes.log.removeHandler(handler)
    said = stream.getvalue()
    check(f"armed={armed}: engage() returns False", result is False)
    check(f"armed={armed}: and says why ({expect})", expect in said)
out.append(f"     said: {said.strip()[:96]}")


def _guard_round_trip() -> list[str]:
    r"""`LayoutGuard.release` with a layout that really was borrowed.

    2.0.0 shipped a `LayoutGuard.release` that read `_request`'s bool as a pair,
    so it raised `TypeError: cannot unpack non-iterable bool object` on **every**
    recording that had borrowed a layout. The layout was never put back, and every
    step of `_on_stop` after it was skipped: no diary record, no final text in the
    panel, no clipboard copy, and the switcher's own key never pressed a second
    time, which would have left a layout switcher switched off for the rest of the
    session.

    Nothing in this file could see it: the refusals in `engage` were checked, the
    message itself was checked against a thread of this process, and the happy
    path — `release` holding a window and a remembered layout — was never executed
    by anything. So it is executed here, in two halves. The first is white box and
    always runs, because the regression is one line of unpacking and a probe that
    can be skipped by a locked desktop is not a probe. The second is the whole
    round trip through `engage`, and it says so when the machine will not lend this
    probe a foreground window.
    """
    import time

    lines: list[str] = []
    # The application's own `user32`, already declared with the restypes these
    # calls need — a second WinDLL here would have to declare them again.
    user32 = keystrokes.user32
    ru = int(user32.LoadKeyboardLayoutW("00000419", 1) or 0)
    en = int(user32.LoadKeyboardLayoutW("00000409", 1) or 0)

    state = _target_window(ru)
    stop, errors = state["stop"], state["errors"]
    if not state.get("hwnd") or errors:
        stop.set()
        return [f"  skip the machine has no usable window here "
                f"({errors or 'timeout'})"]
    hwnd, thread = state["hwnd"], state["thread"]
    lines.append(f"     the probe window is on 0x"
                 f"{int(user32.GetKeyboardLayout(thread) or 0):08X}, "
                 f"put on 0x{en:08X} by hand for the check below")
    user32.ActivateKeyboardLayout(en, 0)
    time.sleep(0.05)

    # `_window` and `_previous` are private, and reaching for them is the point:
    # this is exactly the state `engage` leaves behind, and nothing else builds it.
    guard = keystrokes.LayoutGuard(lambda: "00000419")
    guard._window, guard._previous = hwnd, en
    try:
        handed = guard.release()
        check("release() answers a bool instead of raising",
              isinstance(handed, bool), f"{handed!r}")
        back = int(user32.GetKeyboardLayout(thread) or 0)
        check("and the layout it remembered is the one now back",
              back == en, f"0x{back:08X}, wanted 0x{en:08X}")
        check("nothing is held afterwards", not guard.is_held)
        check("a second release is a no-op", guard.release() is False)
    except Exception as exc:  # noqa: BLE001
        check("release() answers a bool instead of raising", False, repr(exc))
    finally:
        user32.ActivateKeyboardLayout(ru, 0)
        stop.set()

    # The whole way round, through `engage`, which refuses unless a foreign window
    # is in front. The window in front here is whatever the probe was started
    # from — the console — so the console lends it the layout and takes it back.
    real_foreign = keystrokes.foreign_in_front
    keystrokes.foreign_in_front = lambda: True
    front = int(user32.GetForegroundWindow() or 0)
    if not front:
        keystrokes.foreign_in_front = real_foreign
        lines.append("  skip no foreground window here, so engage cannot borrow; "
                     "the check above already ran")
        return lines
    target = int(user32.GetWindowThreadProcessId(front, None) or 0)
    before = int(user32.GetKeyboardLayout(target) or 0)
    wanted = "00000409" if before != en else "00000419"
    guard = keystrokes.LayoutGuard(lambda: wanted)
    try:
        borrowed = guard.engage()
        held = int(user32.GetKeyboardLayout(target) or 0)
        handed = guard.release()
        time.sleep(0.05)
        after = int(user32.GetKeyboardLayout(target) or 0)
    finally:
        keystrokes.foreign_in_front = real_foreign
    lines.append(f"     the foreground window 0x{front:08X} was on 0x{before:08X}")
    check("engage() borrows for a real window", borrowed is True,
          f"borrowed={borrowed}, held=0x{held:08X}")
    if borrowed:
        check("release() puts it back", handed is True and after == before,
              f"0x{after:08X}, wanted 0x{before:08X}")
        check("and nothing is held afterwards", not guard.is_held)
    return lines


out.append("")
out.append("6. the message itself, against a real thread")
# Everything above is bookkeeping. This is the thing the feature rests on: does
# WM_INPUTLANGCHANGEREQUEST actually move a thread's input locale. A second thread
# in this process, with its own queue and its own layout, answers it without a
# microphone, without another machine and without another window — the mechanism
# is per-thread. If it does not move a thread here it will not move Notepad.
out.extend(_message_experiment())

out.append("")
out.append("7. the guard's own round trip, where 2.0.0 raised on every recording")
out.extend(_guard_round_trip())

out.append("")
out.append(f"failures: {failures}")
out.append("PASS" if not failures else "FAIL")

(ROOT / "tmp" / "layoutlive_report.txt").write_text(
    "\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))