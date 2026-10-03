"""Watch the hotkey hook swallow keys, live.

Answers the question `--diagnose` cannot: when you press a combination, which
keys actually arrive from your keyboard, and which of them the hook eats. That
is the difference between "the hook is not installed", "the combination does not
match what your keyboard sends", and "the key got through anyway".

Run it with WinVosk **not** running, so there is only one hook on the chain:

    .\\.venv\\Scripts\\python.exe .\\tools\\hook_probe.py
    .\\.venv\\Scripts\\python.exe .\\tools\\hook_probe.py --specs ctrl+menu 20
    .\\.venv\\Scripts\\python.exe .\\tools\\hook_probe.py --specs win+ctrl+right 30

Every key event is printed as it happens, marked `BLOCKED` when the hook took it
and `passed` when it went on to Windows, so a context menu that appears has a
line above it naming the key that caused it.

Only the main key of a combination is ever blocked, and only while the
combination is held. The modifiers reach Windows on purpose, so they can never
be left stuck down. What this proves is that the main key does not get through.
"""

import ctypes
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from winvosk import config, hotkey

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

MESSAGES = {
    hotkey.WM_KEYDOWN: "down",
    hotkey.WM_KEYUP: "up",
    hotkey.WM_SYSKEYDOWN: "sysdown",
    hotkey.WM_SYSKEYUP: "sysup",
}

COUNTED: dict[str, int] = {"blocked": 0, "passed": 0}


class Watched(hotkey.HotkeyListener):
    """The listener, with every key event printed as the hook decides it.

    A subclass rather than a wrapper around `_on_event`: the ctypes callback is
    built from the bound method during `__init__`, so anything attached to the
    instance afterwards would never be called.
    """

    def _on_event(self, code, message, event_ptr):
        result = super()._on_event(code, message, event_ptr)
        if code != hotkey.HC_ACTION:
            return result
        vk = int(ctypes.cast(event_ptr, ctypes.POINTER(
            hotkey._KeyboardHookStruct)).contents.vkCode)
        name = hotkey.name_for(vk)
        blocked = result != 0
        COUNTED["blocked" if blocked else "passed"] += 1
        label = name or f"0x{vk:02X}"
        print(f"  {label:8s} 0x{vk:02X} {MESSAGES.get(message, hex(message)):7s} "
              f"{'BLOCKED' if blocked else 'passed '}", flush=True)
        return result


def read_args() -> tuple[tuple[str, ...], float, bool]:
    """`--specs` replaces `config.HOTKEYS`; a bare number is the run length."""
    specs: list[str] = []
    length: float | None = None
    wait_for_key = False
    rest = sys.argv[1:]
    index = 0
    while index < len(rest):
        item = rest[index]
        if item == "--specs":
            index += 1
            while index < len(rest):
                candidate = rest[index]
                if candidate.startswith("-"):
                    break
                try:                       # a bare number is the run length
                    float(candidate)
                    break
                except ValueError:
                    pass
                specs.append(candidate)
                index += 1
            continue
        if item in ("--wait", "-w"):
            wait_for_key = True
        else:
            try:
                length = float(item)
            except ValueError:
                raise SystemExit(f"do not understand {item!r}")
        index += 1
    return (tuple(specs) or tuple(config.HOTKEYS)), (length or 0.0), wait_for_key


def main() -> None:
    specs, length, wait_for_key = read_args()
    mains = []
    for spec in specs:
        main_keys, modifiers = hotkey.parse(spec)     # refuse loudly, not half work
        mains.append(f"{spec} -> {','.join(hex(v) for v in main_keys)}")
        print(f"spec    : {spec:24s} modifiers "
              f"{[','.join(hex(v) for v in g) for g in modifiers]}")
    print(f"\nmain key blocked while held: {'; '.join(mains)}")
    print("modifiers always pass through, so they cannot be left stuck down.\n")

    start = time.monotonic()
    fired: list[float] = []
    listener = Watched(specs, on_press=lambda: fired.append(
        time.monotonic() - start))

    if not listener.start():
        raise SystemExit("the hook did not install, nothing to watch")
    print(f"hook    : installed. press the combination now.\n")

    limit = start + length if length else None
    if wait_for_key and not length:
        print("no run length given, press Ctrl+C when finished.", flush=True)
    try:
        while limit is None or time.monotonic() < limit:
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\ninterrupted")
    listener.stop()

    print(f"\ncombination fired {len(fired)} time(s)"
          f" at {[f'{t:.2f}s' for t in fired]}")
    print(f"key events: {COUNTED['blocked']} blocked, {COUNTED['passed']} passed")
    print("\nA context menu that opens while you hold the combination means a "
          "`passed` line\nfor the main key right above it. That is the key that "
          "got through, and it is\na bug worth reporting with this output.")


if __name__ == "__main__":
    main()