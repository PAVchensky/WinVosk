"""End to end check of live typing into a real foreign window.

Launches edit_target.py, a native EDIT control with the caret at offset 0, and
drives the real Typer with a sequence of recogniser updates, including a
revision that has to be corrected with Backspace. The target announces its own
window handle and mirrors its content to a private file, so several runs can
coexist without tainting each other's state.

Run tools/cleanup.py first, or a leftover target from an earlier run will hold
the focus.
"""

import ctypes
import ctypes.wintypes as wt
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

from winvosk import keystrokes

PREFIX = "СТРОКАДО"
SUFFIX = "СТРОКАПОСЛЕ"

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
user32.FindWindowW.restype = wt.HWND
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, wt.DWORD, ctypes.c_ulonglong]

mirror = Path(__file__).resolve().parent.parent / "tmp" / f"typing_{os.getpid()}.txt"
if mirror.exists():
    mirror.unlink()

proc = subprocess.Popen(
    [sys.executable, str(Path(__file__).with_name("edit_target.py")), str(mirror)],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
)
banner = proc.stdout.readline().strip()
print(banner, flush=True)
hwnd = int(banner.split("hwnd=")[1].split()[0])
target_pid = int(banner.split("pid=")[1])


def read_target(settle=0.3, timeout=6.0):
    """Read the mirror once it has stopped changing."""
    previous = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not mirror.exists():
            time.sleep(settle)
            continue
        raw = mirror.read_text(encoding="utf-8")
        body, _, sel = raw.partition("\n@@SEL@@")
        if previous is not None and (body, sel) == previous:
            return body, sel
        previous = (body, sel)
        time.sleep(settle)
    return previous if previous else ("", "")


WM_CLOSE = 0x0010
VK_ESCAPE = 0x1B
VK_MENU = 0x12
user32.PostMessageW.argtypes = [wt.HWND, ctypes.c_uint, ctypes.c_ulonglong, ctypes.c_longlong]
user32.PostMessageW.restype = wt.BOOL
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.ShowWindow.restype = wt.BOOL
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.AttachThreadInput.restype = wt.BOOL
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
kernel32.GetCurrentThreadId.restype = wt.DWORD
SW_RESTORE = 9


def tap(vk: int) -> None:
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, 2, 0)


def activate(target: int) -> bool:
    """Take the focus, the way a real foreground switch would.

    SetForegroundWindow alone is refused unless the caller owns the current
    foreground or received the last input, so the target thread is attached to
    the foreground thread first, the classic way to pass that check.
    """
    if keystrokes.user32.GetForegroundWindow() == target:
        return True
    user32.ShowWindow(target, SW_RESTORE)
    current = kernel32.GetCurrentThreadId()
    holder = keystrokes.user32.GetForegroundWindow()
    threads = []
    if holder:
        threads.append(user32.GetWindowThreadProcessId(holder, None))
    threads.append(user32.GetWindowThreadProcessId(target, None))
    attached = [
        thread for thread in threads
        if thread and thread != current and user32.AttachThreadInput(current, thread, True)
    ]
    try:
        user32.SetForegroundWindow(target)
    finally:
        for thread in attached:
            user32.AttachThreadInput(current, thread, False)
    return keystrokes.user32.GetForegroundWindow() == target


def dismiss_foreground_holders(attempts=20):
    """Close whatever refuses to give the focus up, such as the Search flyout.

    Alt is tapped before Escape, and the order is load bearing. Tapping Alt puts
    the foreground window into menu mode, and the next keystroke of anything is
    then eaten leaving that mode, so an Escape afterwards is what keeps the first
    character of the first fragment from disappearing and the probe from
    blaming the typer for it. Measured: `[Alt, Escape]` types all nine, the
    reverse order types eight.
    """
    for attempt in range(attempts):
        tap(VK_MENU)
        tap(VK_ESCAPE)
        time.sleep(0.2)
        if activate(hwnd):
            return attempt + 1
        holder = keystrokes.user32.GetForegroundWindow()
        if holder:
            user32.PostMessageW(holder, WM_CLOSE, 0, 0)
        time.sleep(0.3)
    return -1


focus_attempts = dismiss_foreground_holders()
print("focus attempts:", focus_attempts, flush=True)
if keystrokes.user32.GetForegroundWindow() != hwnd:
    holder = keystrokes.user32.GetForegroundWindow()
    title = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(holder, title, 256)
    proc.kill()
    print(f"target never became foreground, held by #{holder} {title.value!r}", flush=True)
    sys.exit(1)
time.sleep(0.4)

body, sel = read_target()
print("foreign_in_front:", keystrokes.foreign_in_front(), flush=True)
print("before:", repr(body), "caret", sel, flush=True)

typer = keystrokes.Typer(delay=0.05)
drift = 0
steps = [
    ("partial", "проверка"),
    ("partial", "проверка вставки"),
    ("partial", "проверка встав"),
    ("utterance", "проверка вставки"),
    ("partial", "по"),
    ("partial", "по курсору"),
    ("utterance", "по курсору"),
    ("partial", "текст"),
    ("utterance", "текст"),
]
for kind, text in steps:
    if keystrokes.user32.GetForegroundWindow() != hwnd:
        drift += 1
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.25)
    typer.apply(text, boundary=(kind == "utterance"))
    body, sel = read_target()
    print(f"  after {kind:9s} {text!r:26s} -> {body!r}", flush=True)

body, sel = read_target()
print("after:", repr(body), flush=True)
print("caret:", sel, flush=True)
print(f"typed {typer.typed} chars, erased {typer.erased}, focus drift {drift}", flush=True)

at_start = body.startswith("проверка вставки по курсору текст")
kept = body.endswith(f"{PREFIX} {SUFFIX}")
print("typed at the caret:", at_start, flush=True)
print("existing text preserved:", kept, flush=True)
print("corrections were erased:", typer.erased > 0, flush=True)
print("no focus was stolen by the typer:", drift == 0, flush=True)
print("VERDICT:", "PASS" if (at_start and kept and typer.erased > 0) else "FAIL", flush=True)

proc.kill()
if mirror.exists():
    mirror.unlink()
