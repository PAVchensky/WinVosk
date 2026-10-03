"""Check that the hotkey behaves as push to talk: one press, one release.

Also covers the case that makes push to talk awkward if it is not handled:
the operating system repeats a held key, and the listener must ignore that.
"""

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

from winvosk import config, hotkey, keystrokes

VK_LWIN = 0x5B
VK_ALT = 0x12
VK_CONTROL = 0x11
VK_RIGHT = 0x27

events: list[tuple[str, float]] = []
start = time.monotonic()


def on_press() -> None:
    events.append(("press", time.monotonic() - start))


def on_release() -> None:
    events.append(("release", time.monotonic() - start))


def key(vk: int, up: bool) -> None:
    keystrokes.press(vk, up)


def main() -> None:
    listener = hotkey.HotkeyListener(config.HOTKEYS, on_press, on_release)
    print(f"specs={listener.specs} active={listener.start()} ptt={listener.is_push_to_talk}", flush=True)
    time.sleep(0.8)

    print("\ncase 1: hold alt+win for 2.5s (auto repeat must not fire)", flush=True)
    key(VK_ALT, False)
    key(VK_LWIN, False)
    time.sleep(2.5)
    key(VK_LWIN, True)
    key(VK_ALT, True)
    time.sleep(0.6)
    print(f"  events so far: {events}", flush=True)
    first_ok = len(events) == 2 and events[0][0] == "press" and events[1][0] == "release"
    held = events[1][1] - events[0][1] if len(events) == 2 else 0.0
    print(f"  exactly one press and one release: {first_ok}", flush=True)
    print(f"  held for {held:.2f}s: {1.8 < held < 3.2}", flush=True)

    print("\ncase 2: win+ctrl held, right tapped twice", flush=True)
    events.clear()
    key(VK_LWIN, False)
    time.sleep(0.15)
    key(VK_CONTROL, False)
    time.sleep(0.15)
    key(VK_RIGHT, False)
    time.sleep(0.5)
    key(VK_RIGHT, True)
    time.sleep(0.3)
    key(VK_RIGHT, False)
    time.sleep(0.5)
    key(VK_RIGHT, True)
    time.sleep(0.3)
    key(VK_CONTROL, True)
    key(VK_LWIN, True)
    time.sleep(0.6)
    print(f"  events: {[e[0] for e in events]}", flush=True)
    second_ok = [e[0] for e in events] == ["press", "release", "press", "release"]

    print("\ncase 3: a two key combination needs a full release", flush=True)
    events.clear()
    key(VK_ALT, False)
    time.sleep(0.15)
    key(VK_LWIN, False)
    time.sleep(0.6)
    key(VK_LWIN, True)
    time.sleep(0.4)
    key(VK_ALT, True)
    time.sleep(0.5)
    print(f"  events: {[e[0] for e in events]}", flush=True)
    third_ok = [e[0] for e in events] == ["press", "release"]

    listener.stop()
    passed = first_ok and second_ok and third_ok and 1.8 < held < 3.2
    print(f"\nVERDICT: {'PASS' if passed else 'FAIL'}", flush=True)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
