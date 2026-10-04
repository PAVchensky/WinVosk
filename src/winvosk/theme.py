"""Design tokens, and the Pillow painting behind them.

Tk draws no rounded corner, no soft shadow and no gradient, so every shape that
has one is painted here and handed to Tk as an ordinary image. Three things come
out of this module:

  * `Palette` — the colours, one immutable record per theme, so no widget writes
    a hex literal of its own and the two themes cannot drift apart.
  * `ui()` and `mono()` — the font families resolved against the fonts this
    machine actually has, at the sizes the design uses, with the line height set.
  * `surface()` — the one painter: a rounded rectangle, optionally with a hairline
    border and an optional soft shadow, drawn supersampled and folded back down.

The colour a shape sits on is passed in as `matte` and painted into the image
rather than left transparent. Tk on Windows has no per-pixel alpha for a widget
background and the panel window is opaque, so a transparent margin would come out
as a black or a white rectangle. Painting the parent's own colour into that
margin is what makes a rounded corner and a soft shadow blend into the panel: the
same trick `overlay.py` uses with its colour key, run in reverse.

Nothing here knows what a button is. The widgets are in `widgets.py`, the colours
they use are here, and the strings they show are in `text.py`.

Every length in this module is a design token in logical pixels. `px()` turns one
into physical pixels, so a 12 px radius is 12 px on a 96 dpi screen and 16 px on
a 150% one, and the panel's proportions hold either way.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from functools import lru_cache
from tkinter import ttk

from PIL import Image, ImageDraw, ImageFilter

from . import config

log = logging.getLogger(__name__)

# The theme names live in `config`, not here, and that direction matters.
# `config` and `settings` are imported by every console path — `--diagnose`,
# `--vocab-check`, `file_transcribe --self-test` and the headless probes — none of
# which opens a window. If the default theme were defined here, `config` would
# have to import this module to name it, and this module imports `tkinter` at the
# top. A bundle missing a Tcl script or `_tkinter.pyd` would then fail on the
# import inside `--diagnose`, which is the one command that exists to tell you the
# bundle is broken.
THEMES = config.THEMES
DEFAULT_THEME = config.THEME_DEFAULT

# Spacing. One scale, used everywhere: the gap between two things is one of these
# and never a number typed on the spot, which is most of what keeps the rhythm
# even. The brief asked for 16-24 px between blocks, which is SPACE_MD..SPACE_XL.
SPACE_XS = 4
SPACE_SM = 8
SPACE = 12
SPACE_MD = 16
SPACE_LG = 20
SPACE_XL = 24
SPACE_2XL = 32

# Radii, in logical pixels: 12 px for a card, 8 px for a control, as asked.
RADIUS_CARD = 12
RADIUS_CONTROL = 8

# Line height as a multiple of the font size, the way a stylesheet states it.
# Applied to every multi-line label, which is where the airy look either happens
# or does not.
LINE_HEIGHT = 1.5

# Card shadows. One blur and one alpha for the whole design; the colour comes
# from the palette, because a black shadow on a dark panel is invisible and a
# warm one on a light panel looks like a stain.
SHADOW_BLUR = 10
SHADOW_ALPHA_LIGHT = 40
SHADOW_ALPHA_DARK = 96

# Shapes are drawn at this multiple of their size and folded back down. Four is
# enough for a corner that has to look round rather than merely round-ish, and
# BOX brings it back as an exact average of each block, which is the filter that
# cannot overshoot. LANCZOS rings on a high contrast edge like this one and pulls
# the fill towards whatever the margin was painted, which is how a soft shadow
# picks up a coloured rim.
SUPERSAMPLE = 4


# The tray icon's own two colours, shared by both themes on purpose. A taskbar
# icon is the one piece of this interface that is not on top of our own background:
# it sits on whatever the taskbar and the wallpaper are, in whatever light or dark
# the machine is set to, next to icons that are all their own colours. An accent
# plate looks like an app button; a dark one reads as a microphone on any taskbar,
# in either system theme, and it is what this icon has always been.
_TRAY_IDLE = "#2F3640"
_TRAY_ACTIVE = "#B0231F"


@dataclass(frozen=True)
class Palette:
    """Every colour the interface uses, for one theme.

    Frozen and complete on purpose: a widget that needs a colour that is not here
    is a widget that has grown a shade of its own, and the two themes stop being
    one design. `shadow` is the one non-hex value, because a shadow is a colour
    and an alpha and the two have to travel together.
    """

    name: str
    bg: str
    surface: str
    surface_alt: str
    surface_hover: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    text_subtle: str
    accent: str
    accent_hover: str
    accent_press: str
    accent_soft: str
    accent_on: str
    success: str
    danger: str
    danger_soft: str
    shadow: tuple[int, int, int, int]
    chip_surface: str
    chip_border: str
    chip_glow: str
    chip_bar_low: str
    chip_bar_mid: str
    chip_bar_high: str
    chip_clock: str
    tray_idle_bg: str
    tray_idle_fg: str
    tray_active_bg: str
    tray_active_fg: str


# The light theme is the one the brief describes: a light grey page, white cards,
# an indigo accent. The dark one is the same design with the roles inverted and
# the accent lifted one step, because #6366F1 on #0B0D12 is legible and
# #818CF8 on #FFFFFF is not.
LIGHT = Palette(
    name="light",
    bg="#F9FAFB",
    surface="#FFFFFF",
    surface_alt="#F3F4F6",
    surface_hover="#F1F3F9",
    border="#E7E9EF",
    border_strong="#D3D8E3",
    text="#111827",
    text_muted="#5B6472",
    text_subtle="#8C95A5",
    accent="#6366F1",
    accent_hover="#4F46E5",
    accent_press="#4338CA",
    accent_soft="#EEF0FF",
    accent_on="#FFFFFF",
    success="#0E9F6E",
    danger="#DC2626",
    danger_soft="#FEF2F2",
    shadow=(17, 24, 39, SHADOW_ALPHA_LIGHT),
    chip_surface="#FFFFFF",
    chip_border="#E7E9EF",
    chip_glow="#C7D2FE",
    chip_bar_low="#A5B4FC",
    chip_bar_mid="#818CF8",
    chip_bar_high="#6366F1",
    chip_clock="#5B6472",
    tray_idle_bg=_TRAY_IDLE,
    tray_idle_fg="#FFFFFF",
    tray_active_bg=_TRAY_ACTIVE,
    tray_active_fg="#FFFFFF",
)

DARK = Palette(
    name="dark",
    bg="#0B0D12",
    surface="#151A24",
    surface_alt="#1E2532",
    surface_hover="#242C3B",
    border="#2A3242",
    border_strong="#3A4457",
    text="#E7EAF2",
    text_muted="#9AA4B8",
    text_subtle="#6C7689",
    accent="#818CF8",
    accent_hover="#6366F1",
    accent_press="#4F46E5",
    accent_soft="#1D2138",
    accent_on="#0B0D12",
    success="#34D399",
    danger="#F87171",
    danger_soft="#2A1618",
    shadow=(0, 0, 0, SHADOW_ALPHA_DARK),
    chip_surface="#1B2130",
    chip_border="#2E3648",
    chip_glow="#4F46E5",
    chip_bar_low="#4F46E5",
    chip_bar_mid="#6366F1",
    chip_bar_high="#818CF8",
    chip_clock="#A5B4FC",
    tray_idle_bg=_TRAY_IDLE,
    tray_idle_fg="#FFFFFF",
    tray_active_bg=_TRAY_ACTIVE,
    tray_active_fg="#FFFFFF",
)

PALETTES = {"light": LIGHT, "dark": DARK}


@lru_cache(maxsize=len(THEMES) + 1)
def palette(name: str = DEFAULT_THEME) -> Palette:
    """The colours for `name`, or the default theme's when it is not one of ours.

    Cached, so this is free to call from a paint path. An unknown name is a
    broken `settings.json`, which is worth a warning and never worth an
    exception: the panel has to come up in some colour.
    """
    found = PALETTES.get(name)
    if found is None:
        log.warning("%r is not a theme this app has, using %r", name, DEFAULT_THEME)
        return PALETTES[DEFAULT_THEME]
    return found


def is_dark(name: str = DEFAULT_THEME) -> bool:
    return palette(name).name == DARK.name


# Fonts. Inter is asked for first because the brief asks for it, and it is
# usually not installed; "Segoe UI Variable Text" is what Windows 11 ships as its
# system-ui, and it is the closest thing to Inter that is actually there.
_UI_STACK = ("Inter", "Segoe UI Variable Text", "Segoe UI", "Tahoma", "Arial")
_MONO_STACK = ("Cascadia Mono", "Cascadia Code", "Consolas", "Courier New")

_dpi = 96.0
_scale = 1.0
_ui_family = "Segoe UI"
_mono_family = "Consolas"


def bind(root: tk.Misc) -> None:
    """Resolve the families and the display scale against a real interpreter.

    Called once, right after the root exists and before a single widget is built,
    because both answers come from Tk: the family list is what the machine has
    installed, and `winfo_fpixels` is the real dpi rather than an assumption.

    The scale is `dpi / 96`, not `dpi / 72`. The second one is points to pixels,
    which is the wrong question here: a design token is a pixel, the way a
    stylesheet means it, and a 12 px radius has to stay 12 px on a 96 dpi screen
    rather than become 16. Points only enter where a font asks for them, and
    `points()` is where that conversion lives.
    """
    global _dpi, _scale, _ui_family, _mono_family
    try:
        _dpi = float(root.winfo_fpixels("1i")) or 96.0
    except (tk.TclError, ValueError, TypeError):
        log.debug("no dpi from Tk, assuming 96", exc_info=True)
        _dpi = 96.0
    _scale = max(1.0, _dpi / 96.0)
    try:
        available = {name.casefold(): name for name in tkfont.families(root)}
    except tk.TclError:
        log.debug("no font list from Tk, using the fallbacks", exc_info=True)
        available = {}
    _ui_family = _pick(_UI_STACK, available, "Segoe UI")
    _mono_family = _pick(_MONO_STACK, available, "Consolas")
    reset()
    log.info(
        "typeface %r, monospace %r, %.0f dpi, display scale %.2f",
        _ui_family, _mono_family, _dpi, _scale,
    )


def _pick(stack: tuple[str, ...], available: dict[str, str], fallback: str) -> str:
    """The first family of `stack` this machine has, by name then by prefix."""
    for name in stack:
        hit = available.get(name.casefold())
        if hit:
            return hit
    # Segoe UI arrives as two families on Windows 11, "Text" and "Display", and
    # which of them is registered varies by build, so a prefix match comes second.
    for name in stack:
        head = name.casefold().split(" ")[0:2]
        prefix = " ".join(head)
        for folded, real in available.items():
            if folded.startswith(prefix):
                return real
    return fallback


def px(value: float) -> int:
    """One design token, in physical pixels.

    For an image size, a canvas coordinate or a pad. Tk's own `padx`/`pady`
    options take the token unchanged, because they are already in pixels.
    """
    return max(1, int(round(value * _scale)))


def scale() -> float:
    return _scale


def points(size: float) -> int:
    """A size in design pixels as the point size Tk wants for a font.

    Tk takes a font's size in points and the platform renders it at
    `points * dpi / 72` pixels, while the design counts in pixels. Dividing by 96
    rather than by the live dpi is deliberate: the process is per-monitor aware,
    so a dpi-aware Tk already renders the same point size at more pixels on a
    scaled display, and the two multiplications cancel. A 15 px face is 11 pt on
    every display, and measures 15 px at 96 dpi and 22 px at 144.

    Rounded, because this Tk build takes an integer point size and says so. The
    coarsest it can be is two thirds of a pixel, which is below the difference
    between the four sizes the type scale actually uses.
    """
    return max(1, round(size * 72.0 / 96.0))


@lru_cache(maxsize=128)
def ui(size: int = 13, weight: str = "normal") -> tkfont.Font:
    """The interface face at `size` design pixels.

    Cached, because a font is a Tcl object and making a hundred of them is a
    hundred round trips into the interpreter for no gain. There is no `leading`
    argument because Tk has nowhere to put one: a font's line spacing is the
    face's own, and `widgets.Paragraph` is what reaches a stylesheet's
    line-height, through the only option that can.
    """
    return tkfont.Font(family=_ui_family, size=points(size), weight=weight)


@lru_cache(maxsize=64)
def mono(size: int = 15) -> tkfont.Font:
    """The monospace face, for a hotkey combination and for the transcript.

    A combination has to be readable key by key and the transcript is machine
    output, so both stay monospaced whatever the interface face turns out to be.
    """
    return tkfont.Font(family=_mono_family, size=points(size))


def leading(font: tkfont.Font, size: int, multiple: float = LINE_HEIGHT) -> int:
    """How much air to add per line to reach `multiple` of the font size.

    Tk puts a font's own line spacing between two lines of a `Text` widget and
    offers no way to change it, so 1.5 is reached by adding the difference as
    `spacing3`. Returns a whole number of pixels, never a negative one: a face
    whose natural spacing is already looser than the design asks for is left
    alone rather than squeezed.
    """
    return max(0, px(size * multiple) - font.metrics("linespace"))


def measure(font: tkfont.Font, sample: str) -> int:
    """How wide `sample` is in pixels, which is how a button finds its own size."""
    return font.measure(sample)


def line_height(font: tkfont.Font) -> int:
    return font.metrics("linespace")


def reset() -> None:
    """Drop the cached fonts and painted surfaces.

    Called when the interpreter changes and when the root is destroyed: a
    `tkfont.Font` and an `ImageTk.PhotoImage` both belong to the interpreter that
    made them, and reaching into either after it is gone raises rather than
    draws nothing.
    """
    ui.cache_clear()
    mono.cache_clear()
    _paint.cache_clear()


# The shape. `shadow` is the palette's own tuple, so the colour and the alpha
# travel together and a widget cannot ask for a black shadow on a dark panel by
# forgetting to pass one.


def shadow_margin(shadow: tuple[str, int, int] | None = None) -> int:
    """How much room a shadow needs on each side of the shape it belongs to.

    The blur is spread over roughly `blur * 0.6 * 2` pixels of falloff, so this
    is a touch under the tail and clips nothing anyone can see: a shadow that
    faded to exactly nothing at the edge of its own box would show its seam.
    """
    return 0 if shadow is None else px(SHADOW_BLUR)


def rgb(colour: str) -> tuple[int, int, int]:
    """One `#rrggbb` string as a Pillow triple."""
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)


@lru_cache(maxsize=512)
def _paint(
    width: int, height: int, radius: int, fill: str, matte: str,
    border: str | None, border_width: int,
    shadow: tuple[str, int, int] | None, supersample: int,
) -> Image.Image:
    scale = supersample
    margin = shadow_margin(shadow)
    size = ((width + margin * 2) * scale, (height + margin * 2) * scale)
    image = Image.new("RGB", size, rgb(matte))
    box = (
        margin * scale, margin * scale,
        size[0] - margin * scale - 1, size[1] - margin * scale - 1,
    )
    corner = max(0, radius) * scale
    if shadow is not None:
        colour, blur, alpha = shadow
        mask = Image.new("L", size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(box, radius=corner, fill=alpha)
        mask = mask.filter(ImageFilter.GaussianBlur(blur * scale * 0.6))
        image = Image.composite(
            Image.new("RGB", size, rgb(colour)), image, mask
        )
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(box, radius=corner, fill=rgb(fill))
    if border is not None:
        draw.rounded_rectangle(
            box, radius=corner, outline=rgb(border),
            width=max(1, border_width * scale),
        )
    return image.resize(
        (width + margin * 2, height + margin * 2), Image.Resampling.BOX
    )


def surface(
    width: int, height: int, radius: int, fill: str, *,
    matte: str, border: str | None = None, border_width: int = 1,
    shadow: tuple[str, int, int] | None = None, supersample: int = SUPERSAMPLE,
) -> Image.Image:
    """A rounded rectangle, `width` x `height` plus whatever room a shadow needs.

    The returned image is `width + 2*margin` across, so a caller that lays it down
    as a background has to inset its content by `shadow_margin()` as well. Cached,
    and the caller must not draw on the result: these images are shared between
    every widget of the same size, and one of them scribbling on it changes the
    lot.
    """
    return _paint(
        max(1, int(width)), max(1, int(height)), int(radius), fill, matte,
        border, int(border_width), shadow, int(supersample),
    )


def card_shadow(palette_: Palette, *, raised: bool = False) -> tuple[str, int, int]:
    """The palette's shadow in the shape `surface()` wants it: hex, blur, alpha.

    The palette keeps the colour as four channels because that is how a shadow is
    written down; a painted shadow wants it as the same `#rrggbb` every other
    colour here is, so it is put back together here and nowhere else.
    """
    red, green, blue, alpha = palette_.shadow
    colour = f"#{red:02x}{green:02x}{blue:02x}"
    return colour, theme_blur(), min(255, alpha + (24 if raised else 0))


def theme_blur() -> int:
    return px(SHADOW_BLUR)


# The window itself. Tk can round the contents of a window but not its frame, so
# the panel's own corners come from DWM, which has done it since Windows 11. On
# anything older the call fails and the window keeps its square corners, which is
# why `dress_window()` reports rather than raises.
_DWM_WINDOW_CORNER_PREFERENCE = 33
_DWM_BORDER_COLOR = 34
_DWM_USE_IMMERSIVE_DARK_MODE = 20
_DWM_CORNER_ROUND = 2


def colour_ref(colour: str) -> int:
    """One `#rrggbb` string as the `COLORREF` DWM wants: 0x00bbggrr."""
    red, green, blue = rgb(colour)
    return (blue << 16) | (green << 8) | red


def _dwm_attribute(hwnd: int, attribute: int, value: int) -> bool:
    try:
        dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
    except (OSError, AttributeError):
        log.debug("no dwmapi on this machine", exc_info=True)
        return False
    payload = ctypes.c_int(value)
    return bool(dwm.DwmSetWindowAttribute(
        ctypes.c_void_p(hwnd), ctypes.c_int(attribute),
        ctypes.byref(payload), ctypes.sizeof(payload),
    ))


def dress_window(window: tk.Misc, colours: Palette) -> bool:
    """Hand the window itself to the design: rounded corners, no border, dark bar.

    Windows rounds a top level window itself, clipping whatever the app paints to
    the rounded region. That is the only way to get a real radius on the panel: a
    window with square corners around round contents reads as a mistake, and a
    `tk.Frame` cannot clip its children. The border goes at the same time,
    because the hairline Windows draws is exactly the hard edge this design
    replaced with a shadow, and the title bar is asked for the dark mode so a dark
    panel is not framed by a white bar.

    False means the platform said no — Windows 10, a build without one of the
    attributes, or a window that is not mapped yet. Nothing is logged as an
    error: an absent attribute is a fact about the machine, not a fault in the
    application.
    """
    try:
        hwnd = int(window.wm_frame(), 16)
    except (AttributeError, ValueError, tk.TclError):
        return False
    if not hwnd:
        return False
    ok = _dwm_attribute(hwnd, _DWM_WINDOW_CORNER_PREFERENCE, _DWM_CORNER_ROUND)
    ok = _dwm_attribute(hwnd, _DWM_BORDER_COLOR, colour_ref(colours.border)) and ok
    # Best effort, and deliberately not part of the answer: DWM refuses this one
    # with an error when asked for light mode, because light is what a window gets
    # by default and there is nothing to turn off. A refusal here is the theme
    # already being right, so folding it into the result would report every light
    # window as a failure.
    _dwm_attribute(
        hwnd, _DWM_USE_IMMERSIVE_DARK_MODE, 1 if colours.name == DARK.name else 0
    )
    return ok


# A window that must never be brought into the focus: the recording chip and the
# toast both appear over whatever the user is typing into, and a window that takes
# the focus while a fragment is being dictated is a fragment that lands in the
# wrong place. `WS_EX_NOACTIVATE` is the operating system refusing to activate it,
# which is stronger than anything the app can do about it afterwards.
_GWL_EXSTYLE = -20
_WS_EX_NOACTIVATE = 0x08000000
_WS_EX_TOOLWINDOW = 0x00000080


def forbid_activation(window: tk.Misc | None) -> bool:
    """Ask Windows for a window that can never be brought into the focus.

    False means there was no frame handle to dress: a window that is not mapped
    yet, or one whose `wm_frame` is not a handle. That is a fact about the
    moment, not a fault, so nothing is logged as an error.

    Like `dress_window`, this has to be applied again after every map.
    `deiconify` resets the extended style, so a window dressed once comes back
    activatable the next time it is shown — which is the whole life of a toast.
    """
    if window is None:
        return False
    try:
        hwnd = int(window.wm_frame(), 16)
    except (AttributeError, ValueError, tk.TclError):
        return False
    if not hwnd:
        return False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetWindowLongPtrW.argtypes = [
            ctypes.c_void_p, ctypes.c_int]
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    except (OSError, AttributeError):
        log.debug("no user32 on this machine", exc_info=True)
        return False
    style = user32.GetWindowLongPtrW(ctypes.c_void_p(hwnd), _GWL_EXSTYLE)
    user32.SetWindowLongPtrW(
        ctypes.c_void_p(hwnd), _GWL_EXSTYLE,
        style | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW,
    )
    return True


def enable_dpi_awareness() -> bool:
    """Tell Windows the process is per-monitor DPI aware, before any window.

    Tk is DPI unaware by default, so Windows scales the finished window afterwards
    and every rounded corner and every soft shadow is resampled a second time,
    which is precisely where softness goes: a 4x supersampled edge blurred once
    more by the compositor is the difference between a card and a smudge.

    Must run before the first Tk window exists. After that the call fails, the old
    behaviour stands, and that is logged rather than raised — a panel that came up
    slightly soft beats a panel that did not come up.
    """
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        try:
            # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2, as -4.
            if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                return True
        except AttributeError:
            pass
        try:
            shcore = ctypes.WinDLL("shcore", use_last_error=True)
            if shcore.SetProcessDpiAwareness(2) == 0:  # PROCESS_PER_MONITOR_DPI_AWARE
                return True
        except (OSError, AttributeError):
            pass
        return bool(user32.SetProcessDPIAware())
    except Exception:
        log.debug("could not raise the DPI awareness", exc_info=True)
        return False


# Whatever ttk is left touching. The panel is built entirely from `widgets.py`
# now — its own cards, buttons, switches, tabs, scrollbars — but `run.py
# --check-bundle` proves the Tcl script library is whole by asking a `ttk` widget
# for its theme, and a bundle can be missing a Tcl script while every console
# flag still works. So the theme still has to resolve, on a machine with no
# microphone and no console.


def apply(root: tk.Misc, colours: Palette) -> ttk.Style:
    """Push the palette into Tk itself: the root background and the `ttk` theme.

    `clam` rather than the platform default, because it is the one theme whose
    colours are all settable and it is what `--check-bundle` will ask for. Nothing
    in the panel is drawn by it any more.
    """
    root.configure(bg=colours.bg)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        log.debug("no clam theme, keeping %s", style.theme_use(), exc_info=True)
    style.configure(
        ".", background=colours.bg, foreground=colours.text,
        fieldbackground=colours.surface, bordercolor=colours.border,
        borderwidth=0, focuscolor=colours.bg,
    )
    return style
