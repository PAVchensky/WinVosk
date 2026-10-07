r"""Measure whether a keyboard hook behind ours sees keys we inject.

`switcher_key` presses a combination so a layout switcher stops rewriting what is
typed, and swallows the six events so no window ever sees them. The swallow is
what makes that safe, and it is also what makes it useless in one of the two
possible orders: Windows calls the most recently installed low level hook first,
so if the switcher's hook was installed *after* ours, our own hook eats the burst
before the switcher does. Measured on this machine, that is exactly what happened
— `punto.exe` had been up since 10:04 and WinVosk was restarted at 16:42 — and the
feature was a no-op that `app.log` described as a success.

Nothing at run time can tell the two orders apart, so this probe measures them.
It installs a real `WH_KEYBOARD_LL` hook, which puts it first in the chain, and
sends the combination **without swallowing anything**, recording for each event
what `CallNextHookEx` returned. A non-zero return means a hook behind this one
claimed the event: the switcher is reachable and the order is against us. All
zeros mean nobody behind claimed them, which does *not* prove the switcher ignored
them — a hotkey handler may act without swallowing — so the last word is what the
switcher's own window shows.

**Run it with WinVosk closed** (`tools\cleanup.py` first). A running WinVosk has
its own hook in the chain, and its `return 0` for an untagged event would be read
here as "nothing behind us claimed it". The probe warns if it finds WinVosk alive.

**It really does press the keys**, which is what makes it a measurement: a context
menu may open in whatever window has the focus. Run it from a Notepad window.

    .\.venv\Scripts\python.exe .\tools\switcher_probe.py [combination]

The default combination is `ctrl+shift+f10`, which is what this machine's Punto
Switcher has bound to its auto-replace switch. Two transports are sent, because a
hook that watches the key events may read virtual key codes, scan codes or
`LLKHF_INJECTED`, and a program that ignores one is not evidence about the others.

The report goes to `tmp\switcher_report.txt`. Exit code is 0 when the measurement
itself worked — injecting and observing — and 1 when it did not, because a
measurement that silently measured nothing is worse than none.
"""

import ctypes
import sys
import threading
import time
from ctypes import wintypes as wt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from winvosk import config, hotkey, keystrokes  # noqa: E402

ROOT = config.BASE_DIR
REPORT = ROOT / "tmp" / "switcher_report.txt"
SPEC = sys.argv[1] if len(sys.argv) > 1 else "ctrl+shift+f10"

# KBDLLHOOKSTRUCT.flags
LLKHF_EXTENDED = 0x01
LLKHF_LOWER_IL_INJECTED = 0x02
LLKHF_UPPER_IL_INJECTED = 0x04
LLKHF_INJECTED = 0x10

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

SYNCHRONIZE = 0x00100000
MUTEX_NAME = config.MUTEX_NAME

keystrokes.kernel32.OpenMutexW.argtypes = [wt.DWORD, wt.BOOL, wt.LPCWSTR]
keystrokes.kernel32.OpenMutexW.restype = wt.HANDLE

# Virtual key code to (scan code, extended), for the transports below. Only what a
# combination is likely to be made of; anything missing skips that transport rather
# than guessing a scan code and pressing the wrong key at somebody.
SCAN_CODES: dict[int, tuple[int, bool]] = {
    0x10: (0x2A, False),   # shift
    0x11: (0x1D, False),   # control, generic = left
    0x12: (0x38, False),   # alt
    0x5B: (0x5B, True),    # left win
    0x5C: (0x5C, True),    # right win
    0xA0: (0x38, True),    # left shift as a code
    0xA1: (0x38, True),    # right shift
    0xA2: (0x1D, True),    # left control
    0xA3: (0x1D, True),    # right control
    0xA4: (0x38, True),    # left alt
    0xA5: (0x38, True),    # right alt
    0x20: (0x39, False),   # space
    0x0D: (0x1C, False),   # enter
    0x1B: (0x01, False),   # escape
    0x2E: (0x53, True),    # delete
    0x25: (0x4B, True),    # left
    0x26: (0x48, True),    # up
    0x27: (0x4D, True),    # right
    0x28: (0x50, True),    # down
}
# F1 is 0x3B and the rest count on from there; F6 upwards carry the E0 prefix.
for _index in range(1, 13):
    SCAN_CODES[0x6F + _index] = (0x3A + _index, _index > 5)
# Letters are their own scan code in upper case, digits are 0x02 upwards.
for _code in range(0x30, 0x3A):
    SCAN_CODES[_code] = (0x02 + _code - 0x30, False)
for _code in range(0x41, 0x5B):
    SCAN_CODES[_code] = (_code, False)

MESSAGE_NAMES = {
    hotkey.WM_KEYDOWN: "down",
    hotkey.WM_KEYUP: "up",
    hotkey.WM_SYSKEYDOWN: "sysdown",
    hotkey.WM_SYSKEYUP: "sysup",
}


def winvosk_running() -> bool:
    """Whether another WinVosk holds the single-instance mutex.

    Its hook would sit between this one and the switcher and answer `0` for an
    event it does not own, which this probe would read as silence from behind.
    """
    handle = keystrokes.kernel32.OpenMutexW(SYNCHRONIZE, False, MUTEX_NAME)
    if not handle:
        return False
    keystrokes.kernel32.CloseHandle(handle)
    return True


class Watcher:
    """A hook that records every event and swallows nothing at all."""

    def __init__(self) -> None:
        self.events: list[tuple[int, int, int, int, int]] = []
        self._handle = None
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._proc = hotkey._LOW_LEVEL_PROC(self._on_event)

    def _on_event(self, code: int, message: int, event_ptr: int) -> int:
        if code != hotkey.HC_ACTION:
            return hotkey.user32.CallNextHookEx(None, code, message, event_ptr)
        data = ctypes.cast(
            event_ptr, ctypes.POINTER(hotkey._KeyboardHookStruct)).contents
        nxt = hotkey.user32.CallNextHookEx(None, code, message, event_ptr)
        # Recorded before anything else can change it, and the chain's own answer
        # is the whole point: a non-zero value here means a hook behind this one
        # claimed the event rather than letting it through. `dwExtraInfo` is kept
        # because an event this probe did not send is somebody else's, and its
        # marker is the only thing that says whose.
        self.events.append((int(data.vkCode), int(message), int(data.flags),
                            int(data.dwExtraInfo or 0), int(nxt)))
        return nxt

    def _run(self) -> None:
        self._thread_id = hotkey.kernel32.GetCurrentThreadId()
        module = hotkey.kernel32.GetModuleHandleW(None)
        self._handle = hotkey.user32.SetWindowsHookExW(
            hotkey.WH_KEYBOARD_LL, self._proc, module, 0)
        self._ready.set()
        message = wt.MSG()
        while hotkey.user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            hotkey.user32.TranslateMessage(ctypes.byref(message))
            hotkey.user32.DispatchMessageW(ctypes.byref(message))

    def start(self, timeout: float = 3.0) -> bool:
        self._thread = threading.Thread(target=self._run, name="switcher-probe",
                                        daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        return bool(self._handle)

    def stop(self) -> None:
        if self._handle:
            hotkey.user32.UnhookWindowsHookEx(self._handle)
            self._handle = None
        if self._thread_id:
            # The message goes to the thread that installed the hook, not to this
            # one: `WM_QUIT` posted anywhere else leaves that thread pumping for
            # ever, and the probe would not exit.
            hotkey.user32.PostThreadMessageW(self._thread_id, hotkey.WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2.0)


def events_for(keys: list[int], *, scancodes: bool) -> list:
    """The six events of a combination, modifiers down then all of them up."""
    built = []
    for vk in keys:
        built.append(_event(vk, 0, scancodes))
    for vk in reversed(keys):
        built.append(_event(vk, KEYEVENTF_KEYUP, scancodes))
    return built


def _event(vk: int, flags: int, scancodes: bool) -> "keystrokes._Input":
    scan, extended = 0, 0
    if scancodes:
        code = SCAN_CODES.get(vk)
        if code is None:
            raise KeyError(vk)
        scan = code[0]
        flags |= KEYEVENTF_SCANCODE
        if code[1]:
            flags |= KEYEVENTF_EXTENDEDKEY
    event = keystrokes._Input()
    event.type = keystrokes.INPUT_KEYBOARD
    # `dwExtraInfo` is left at zero on purpose. `SYNTHETIC_TAG` would identify the
    # burst to this application's own hook, and part of what is being measured is
    # whether a hook behind us reacts to a burst that carries nothing marking it.
    event.ki = keystrokes._KeyboardInput(0 if scancodes else vk, scan, flags, 0, 0)
    return event


def describe(flags: int) -> str:
    parts = []
    if flags & LLKHF_EXTENDED:
        parts.append("extended")
    if flags & LLKHF_LOWER_IL_INJECTED:
        parts.append("lower-il-injected")
    if flags & LLKHF_UPPER_IL_INJECTED:
        parts.append("upper-il-injected")
    if flags & LLKHF_INJECTED:
        parts.append("INJECTED")
    return ",".join(parts) or "physical"


def main() -> int:
    lines: list[str] = []

    def say(text: str = "") -> None:
        lines.append(text)
        print(text, flush=True)

    say(f"combination : {SPEC}")
    try:
        keys = hotkey.sequence(SPEC)
    except hotkey.HotkeyError as exc:
        say(f"refused     : {exc}")
        return _finish(lines, False, "the combination could not be read")
    say(f"codes       : {[f'0x{vk:02X}' for vk in keys]}")

    if winvosk_running():
        # Not fatal: WinVosk only swallows events that carry SYNTHETIC_TAG or that
        # are its own hotkey, so an untagged burst passes through it. But if the
        # order is such that it answers first, the zeros below are its answer and
        # not the switcher's, and there is no way to tell the two apart from here.
        say("warning     : WinVosk is running. Run tools\\cleanup.py first; its hook "
            "answers 0 for these events and a silence behind it is then ambiguous.")

    foreground = int(keystrokes.user32.GetForegroundWindow() or 0)
    say(f"foreground  : 0x{foreground:08X}"
        + ("" if foreground else "   (nothing — this session has no input yet)"))

    watcher = Watcher()
    if not watcher.start():
        say("hook        : SetWindowsHookExW failed, nothing was measured")
        return _finish(lines, False, "the hook could not be installed")
    say("hook        : installed, and it is the most recent one, so it is called "
        "first and the chain's answer is visible from here")
    say("foreground window may show a context menu: this probe swallows nothing")

    measured = {}
    try:
        for name, scancodes in (("virtual key codes", False),
                                ("scan codes", True)):
            try:
                batch = events_for(keys, scancodes=scancodes)
            except KeyError as exc:
                say(f"{name:12s}: skipped, no scan code is known for 0x{exc.args[0]:02X}")
                continue
            watcher.events.clear()
            array = (keystrokes._Input * len(batch))(*batch)
            sent = keystrokes.user32.SendInput(
                len(batch), array, ctypes.sizeof(keystrokes._Input))
            say("")
            say(f"{name}: SendInput delivered {sent} of {len(batch)}"
                + ("" if sent == len(batch) else "   (refused — no input here)"))
            if sent != len(batch) or not watcher.events:
                measured[name] = []
                if not watcher.events:
                    say(f"{name:12s}: our hook saw nothing at all, so nothing "
                        f"behind it was asked")
                continue
            time.sleep(0.4)
            seen = list(watcher.events)
            measured[name] = seen
            ours = [row for row in seen if row[3] == 0]
            foreign = [row for row in seen if row[3] != 0]
            said = {MESSAGE_NAMES.get(msg, hex(msg)) for _, msg, _, _, _ in seen}
            say(f"{name:12s}: our hook saw {len(seen)} event(s): {sorted(said)}")
            for vk, message, flags, extra, nxt in seen:
                mark = "   (ours)" if extra == 0 else (
                    f"   <- injected by another process, dwExtraInfo=0x{extra:016X}")
                say(f"    vk=0x{vk:02X} {MESSAGE_NAMES.get(message, hex(message)):7s} "
                    f"flags=0x{flags:04X} [{describe(flags)}] "
                    f"next={nxt}"
                    f"{'   <- a hook behind us claimed it' if nxt else ''}{mark}")
            if len(seen) != len(ours):
                # Six events went out and more came back. A hook behind this one
                # answered the combination by injecting its own keys — the only
                # trace of an action that still returns 0.
                say(f"{name:12s}: {len(seen)} came back for 6 sent, "
                    f"{len(foreign)} of them not ours")
            else:
                say(f"{name:12s}: exactly our own six came back, nothing reacted")
    finally:
        watcher.stop()

    claimed = {name: [row for row in rows if row[4]] for name, rows in measured.items()}
    answered = {
        name: [row for row in rows if row[3] != 0]
        for name, rows in measured.items()
    }
    said = {name: [row for row in rows if row[4]] for name, rows in measured.items()}
    any_claimed = any(said.values())
    any_answered = any(answered.values())
    say("")
    if not any(measured) or all(not rows for rows in measured.values()):
        verdict = (
            "nothing was measured: SendInput refused or our hook saw no events. "
            "That is what a locked or input-less session looks like — unlock it and "
            "run this again from a console."
        )
        return _finish(lines, False, verdict)
    if any_claimed:
        verdict = (
            "a hook behind this one claims injected keys, so the switcher IS reachable "
            "by pressing the combination — and it is behind us, which is the order in "
            "which swallowing the burst starves it. Pressing without swallowing works "
            "here; swallowing does not."
        )
    elif any_answered:
        verdict = (
            "no hook behind us swallowed anything, but something answered: extra "
            "injected events came back for the six we sent, which is what a hook "
            "acts rather than blocks. The switcher is reachable, it is behind us, "
            "and swallowing the burst starves it — so it must be pressed without "
            "being swallowed."
        )
    else:
        verdict = (
            "nothing behind this one touched the events: not one came back that was "
            "not ours. That is not proof the switcher ignored them — it may need the "
            "foreground to be an editing window, or a real key rather than an "
            "injected one — but it is not reacting to this. Compare the switcher's "
            "own window before and after pressing the combination by hand."
        )
    return _finish(lines, True, verdict)


def _finish(lines: list[str], measured: bool, verdict: str) -> int:
    print("", flush=True)
    print(f"verdict     : {verdict}", flush=True)
    lines += ["", f"verdict     : {verdict}"]
    try:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"report      : {REPORT}", flush=True)
    except OSError as exc:
        print(f"report      : could not be written, {exc}", flush=True)
    print("", flush=True)
    print("now look at the switcher's own window: did the run change it, and does "
          "pressing the combination by hand?", flush=True)
    return 0 if measured else 1


if __name__ == "__main__":
    raise SystemExit(main())