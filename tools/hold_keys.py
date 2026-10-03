"""Hold a combination down for N seconds, then release it."""

import ctypes
import ctypes.wintypes as wt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from winvosk import keystrokes

COMBOS = {
    "alt+win": [0x12, 0x5B],
    "win+ctrl+right": [0x5B, 0x11, 0x27],
}

if __name__ == "__main__":
    name = sys.argv[1]
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    keys = COMBOS.get(name)
    if keys is None:
        raise SystemExit(f"unknown combination: {name}")
    for vk in keys:
        keystrokes.press(vk, False)
    time.sleep(seconds)
    for vk in reversed(keys):
        keystrokes.press(vk, True)
    print(f"held {name} for {seconds}s", flush=True)
