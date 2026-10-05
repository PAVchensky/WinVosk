"""Prove the chip takes the theme's colours, and that the settings tab opens at its top.

Two things that cannot be seen from a screenshot of the panel, because the chip is a
second window and the tab's scroll position is a number:

- the chip's plate, bars and clock are the theme's, in every theme, including
  after a theme change under a recording that is already running - and the plate
  is dark in all of them, because a white chip on a white page is invisible;
- a tab that has been scrolled comes back to its first line, and a check that
  walked a page to its end puts it back where it found it.

    python tools\\chip_probe.py
"""

from __future__ import annotations

import queue
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from winvosk import config, overlay, panel as panel_mod, text, theme  # noqa: E402

SAMPLE = [
    ("Цифровое аудио (S/PDIF)", True),
    ("Conexant HD Audio capture", False),
    ("Микрофон (2- HD Audio)", False),
]


def luminance(colour: str) -> float:
    """How bright one of these hex colours is, roughly, on a 0..1 scale."""
    red, green, blue = theme.rgb(colour)
    return (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255


def settle(root, passes=8):
    for _ in range(passes):
        root.update_idletasks()
        root.update()
        time.sleep(0.03)


def check_key() -> list[str]:
    """The transparent key sits on the plate, not a colour of its own.

    The key is what the window manager makes invisible, so it is the one colour
    on the chip that must not show. Derived from the plate's fill, a few steps
    away: the antialiased rim is a blend between the two, and a blend between a
    colour and itself is not a colour anyone can see.
    """
    out = []
    for name in config.THEMES:
        surface, rim, low, mid, high, clock = overlay.chip_colours(name)
        key = overlay.chip_key(name)
        painted = {surface.lower(), rim.lower(), low.lower(), mid.lower(),
                   high.lower(), clock.lower()}
        assert key not in painted, f"{name}: the key {key} is a colour the chip paints"
        plate = theme.rgb(surface)
        steps = theme.rgb(key)
        distance = max(abs(a - b) for a, b in zip(plate, steps))
        assert 0 < distance <= 8, (
            f"{name}: the key {key} is {distance} steps from the plate {surface}, "
            "which is either the same colour or far enough to see"
        )
        out.append(f"ok   {name}: key {key} is {distance} step(s) from the plate {surface}")
    return out


def check_palette() -> list[str]:
    """The ramps are the palettes', the plates are dark, nothing is a stray hex."""
    out = []
    for name in config.THEMES:
        surface, rim, low, mid, high, clock = overlay.chip_colours(name)
        colours = theme.palette(name)
        assert (low, mid, high, clock) == (
            colours.chip_bar_low, colours.chip_bar_mid,
            colours.chip_bar_high, colours.chip_clock,
        ), f"{name}: the ramp is not the palette's"
        assert (surface, rim) == (colours.chip_surface, colours.chip_border), (
            f"{name}: the plate is not the palette's"
        )
        if luminance(surface) > 0.35:
            out.append(f"FAIL {name}: the chip plate {surface} is bright, and it "
                       "floats over whatever the user is typing into")
        else:
            out.append(f"ok   {name}: plate {surface}, bars {low} {mid} {high}, "
                       f"clock {clock}")
    studio = theme.palette("studio")
    assert studio.chip_bar_high == studio.accent, (
        "the studio bars are not the studio accent"
    )
    out.append(f"ok   studio bars are the studio accent {studio.accent}")
    return out


def check_live() -> list[str]:
    """A chip that is on screen carries the palette, and changes with the theme."""
    out = []
    panel = panel_mod.Panel(
        queue.Queue(), lambda: 0.4, live_typing=True, clipboard=False,
        autostart=False, correct_words=True, toggle=False, write_history=True,
        write_log=True, language="ru", theme_name="studio", devices=SAMPLE,
    )
    chip = panel._overlay
    chip.show()
    settle(panel._root)
    canvas = chip._canvas
    first_window = chip._window

    def colours() -> tuple[str, ...]:
        bar = chip._bars[0]
        return tuple(
            canvas.itemcget(item, "fill")
            for item in (bar[0], bar[1], bar[3], chip._clock)
        )

    expected = overlay.chip_colours("studio")
    seen = colours()
    assert seen == (expected[2], expected[3], expected[4], expected[5]), (
        f"a visible chip is not showing the studio palette: {seen} against "
        f"{expected[2:3] + expected[3:4] + expected[4:5] + expected[5:6]}"
    )
    centre = chip._plate.getpixel((overlay.WIDTH // 2, 4))
    assert theme.rgb(expected[0]) == centre, (
        f"the plate is {centre}, not the studio surface {expected[0]}"
    )
    out.append(f"ok   the chip on screen is the studio palette, plate {centre}")

    # The window manager is told a colour, so what it was told is checked rather
    # than what the code meant to tell it.
    live_key = str(chip._window.attributes("-transparentcolor"))
    assert live_key == overlay.chip_key("studio"), (
        f"the window is keyed on {live_key}, not {overlay.chip_key('studio')}"
    )
    out.append(f"ok   and the window is keyed on {live_key}, not a colour of its own")

    # A theme change must reach the chip that is already running, without
    # rebuilding it: a new window would drop the recording it is showing.
    panel.set_theme("dark")
    settle(panel._root)
    assert chip._window is first_window, "the chip window was rebuilt on a theme change"
    expected = overlay.chip_colours("dark")
    seen = colours()
    assert seen == (expected[2], expected[3], expected[4], expected[5]), (
        f"the chip kept the studio ramp after a theme change: {seen}"
    )
    centre = chip._plate.getpixel((overlay.WIDTH // 2, 4))
    assert theme.rgb(expected[0]) == centre, (
        f"the plate is still {centre}, not the dark surface {expected[0]}"
    )
    assert str(chip._window.attributes("-transparentcolor")) == overlay.chip_key("dark"), (
        "the key was not moved with the theme, so the hole would stop being cut"
    )
    out.append(f"ok   set_theme recoloured the running chip in place: {seen}")

    panel.set_theme("light")
    settle(panel._root)
    assert chip._window is first_window, "the chip window was rebuilt on a theme change"
    out.append("ok   and again for the light theme, still the same window")
    chip.destroy()
    out.append("ok   the chip window is gone")
    panel._root.destroy()
    return out


def check_tabs() -> list[str]:
    """A tab comes back to its top, and a check puts the page back where it was."""
    out = []
    panel = panel_mod.Panel(
        queue.Queue(), lambda: 0.4, live_typing=True, clipboard=False,
        autostart=False, correct_words=True, toggle=False, write_history=True,
        write_log=True, language="ru", theme_name="studio", devices=SAMPLE,
    )
    panel.present()
    panel._root.geometry(f"{panel_mod.WIDTH}x{panel_mod.HEIGHT}")
    settle(panel._root)
    page = panel._settings_page
    canvas = page.canvas

    panel._notebook.select(1)
    settle(panel._root)
    assert canvas.yview()[0] == 0.0, f"the settings tab opened at {canvas.yview()[0]}"

    # Down to the end, the way a check or a long read leaves it.
    canvas.yview_moveto(1.0)
    settle(panel._root)
    assert canvas.yview()[0] > 0.0, "the page cannot be scrolled, so this proves nothing"

    panel._notebook.select(0)
    panel._notebook.select(1)
    settle(panel._root)
    assert canvas.yview()[0] == 0.0, (
        f"the settings tab came back at {canvas.yview()[0]}, not at its top"
    )
    out.append("ok   a scrolled settings tab comes back to its first line")

    canvas.yview_moveto(1.0)
    settle(panel._root)
    panel.check_settings_reachable()
    settle(panel._root)
    assert canvas.yview()[0] == 0.0, (
        f"the check left the settings tab at {canvas.yview()[0]}"
    )
    out.append("ok   check_settings_reachable puts the page back where it found it")

    history = panel._history_page.canvas
    panel._notebook.select(2)
    settle(panel._root)
    panel.check_history_reachable()
    settle(panel._root)
    assert history.yview()[0] == 0.0, f"the check left the history tab at {history.yview()[0]}"
    out.append("ok   and the history tab with it")
    panel._root.destroy()
    return out


def main() -> int:
    lines = check_palette() + check_key() + check_live() + check_tabs()
    print("\n".join(lines))
    print(f"\n{len(lines)} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())