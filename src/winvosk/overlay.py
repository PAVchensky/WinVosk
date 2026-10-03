"""Small always-on-top chip that makes an ongoing recording obvious.

The panel is hidden most of the time, and its status line goes with it, so a
recording started by the hotkey leaves no hint that the microphone is live. The
chip is eleven thin equalizer bars over an elapsed clock. The bars are canvas
rectangles that grow from the middle line of the bar field in both directions;
the rounded plate under them is a Pillow image, antialiased and cached, because
Tk draws no soft edge and a plate assembled from canvas primitives looks stepped.

The microphone level is not displayed. It is gated into silence or sound and
used to drive an animation, so the chip shows that something is being said
without ever claiming to measure how loudly it is said.

It sits horizontally centred at the bottom of the work area, which is where the
eye already goes for a taskbar chip, and it is kept clear of the panel's own
bottom right corner.

It must never take focus. Dictated characters are sent to whatever window is in
front, so a stolen focus would send the words into the chip instead of the
user's document. Hence no focus_force and no grab, and on Windows the window
carries WS_EX_NOACTIVATE so the operating system itself refuses to activate it.
Because the chip belongs to this process, keystrokes.foreign_in_front() reports
False while it is in front, which holds the fragment back instead of typing it
anywhere, so no extra window allowlist is needed here.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import math
import time
import tkinter as tk
from collections.abc import Callable

from PIL import Image, ImageDraw, ImageTk

log = logging.getLogger(__name__)

# Geometry. Eleven 2 px sticks with a 4 px gap take 11*2 + 10*4 = 62 px, which
# leaves a 12 px margin on each side of the 87 px window. The bar field is
# 20 px tall and every bar straddles its middle line, so a bar of half height S
# reaches BAR_MID-S to BAR_MID+S: the tallest spans the whole field and nothing
# can be clipped at any height. The 11 pt clock sits underneath.
WIDTH = 87
HEIGHT = 35
BARS = 11
BAR_WIDTH = 2
BAR_GAP = 4
BAR_MARGIN = (WIDTH - (BARS * BAR_WIDTH + (BARS - 1) * BAR_GAP)) // 2
BAR_TOP = 1
BAR_FIELD = 20
BAR_MID = BAR_TOP + BAR_FIELD // 2
CORNER = 20
CLOCK_Y = 27
TICK_MS = 20
MARGIN_ABOVE_TASKBAR = 5

# Motion. One smoothed energy rises fast and falls slowly, and it is gated: the
# question asked of the microphone is not how loud but whether anything is being
# said at all. Above the gate each bar takes its own share of the energy, scaled
# by the bell profile and swung by its own two-sine wobble, so the eleven jump
# about and never move together. Below the gate the share is zero, every bar
# settles on the same small height, and that is what ends the session.
# ATTACK and DECAY are per tick and the release is two of them in a row, the
# energy's and then the bars', so a loud stretch needs about a second to fall
# back to the idle height: measured 0.99 s to within half a pixel of it. Slower
# than that reads as a stuck bar, faster than that reads as a cut off fall.
ATTACK = 0.55
DECAY = 0.14
GATE = 0.02
# The level is a raw PCM peak, where ordinary speech sits far from full scale.
# The drive is what puts the animation across its whole range, and it is a fixed
# boost rather than a scale: the chip shows that speech is happening, not how
# much of it there is.
DRIVE = 3
BAR_SPAN_MAX = 4.7
BAR_SPAN_MIN = 1
BAR_IDLE = 3
# The wobble is mostly a share of the bar's own height, so a short outer bar
# travels a short distance and a tall centre bar a long one and the bell
# survives the animation instead of being scrambled by it. The absolute part is
# texture for the short bars, and it rides on the drive, so a silent stream
# still lands every bar on BAR_IDLE and no two alike off it. Both are chosen
# against the 1.76 px step between the two outermost bars: pulled against each
# other at opposite extremes they account for WOBBLE_REL * (5.00 + 6.76) +
# 2 * WOBBLE_ABS, which is 1.66 px of that step, so they can close it but never
# cross it.
WOBBLE_REL = 0.09
WOBBLE_ABS = 0.3
# The rate is a shaping knob as well as a matter of taste: the bars reach their
# goal through a one pole lag, so a faster wobble is followed less closely and
# the envelope that is actually reached comes out flatter. Measured over six
# seeded runs, 0.45 instead of 0.35 takes the worst neighbour inversion from
# 0.71 px to 0.42 px at the same amplitudes, and the quietest bar also travels
# further per tick.
WOBBLE_STEP = 0.45
# Phases start spread out, so the row is out of step even on the first frame.
PHASE_SPREAD = 2

# A colour used nowhere else, made transparent by the window manager: whatever
# the plate leaves in it simply is not on the screen, which is how the chip gets
# rounded corners.
_COLOR_KEY = '#0000fe'
_BACKGROUND = '#2b2b2b'
_BORDER = '#454545'
_BAR_LOW = '#7d2f4f'
_BAR_MID = '#c9527f'
_BAR_HIGH = '#ff8ab8'
_CLOCK = '#e9b8cd'
_CLOCK_FONT = ('Consolas', 7)

# Plate layers, outermost first: the fill reaches the antialiased edge so the
# soft boundary blends with the plate itself, the subtle border sits a pixel
# inside it, and the fill returns for everything the border did not cover. The
# colour-key surround is whatever no layer painted. BOX is the filter for an
# exact _PLATE_SCALE fold down: it averages each _PLATE_SCALE squared block and
# nothing else, so the boundary becomes blends that stay inside the range of the
# colours they are made of. LANCZOS rings on this edge instead, because its
# kernel overshoots past a high contrast boundary and pulls the fill a fraction
# of a percent towards the colour key.
_PLATE_SCALE = 4
_PLATE_RESAMPLE = Image.Resampling.BOX
_PLATE_LAYERS = ((0, _BACKGROUND), (1, _BORDER), (2, _BACKGROUND))

user32 = ctypes.WinDLL("user32", use_last_error=True)

_LONG = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = _LONG
user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, _LONG]
user32.SetWindowLongPtrW.restype = _LONG
user32.SystemParametersInfoW.argtypes = [wt.UINT, wt.UINT, ctypes.c_void_p, wt.UINT]
user32.SystemParametersInfoW.restype = wt.BOOL

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
SPI_GETWORKAREA = 0x0030


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", wt.LONG), ("top", wt.LONG),
        ("right", wt.LONG), ("bottom", wt.LONG),
    ]


def _rgb(colour: str) -> tuple[int, int, int]:
    """Turn one of the hex colours above into a Pillow triple."""
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)


def build_plate() -> Image.Image:
    """Render the rounded plate, antialiased, ready for the colour key.

    Tk has no antialiased shape, so a plate drawn from canvas primitives has a
    staircase of hard pixels along its edge. Pillow has no such limit: the
    layers are drawn at _PLATE_SCALE times the size and brought back down with
    _PLATE_RESAMPLE, which averages the boundary into blends. The result is RGB
    with no alpha channel and every pixel outside the rounded shape left in
    _COLOR_KEY, so -transparentcolor cuts a true hole and the blends along its
    rim read as a smooth edge. Set CORNER to 0 and the same code path draws a
    square plate.

    This is the one Pillow call on the run-time path, and it is reached from the
    application's own pump, so RecordingOverlay treats any failure as a reason
    to lay the same plate on without Pillow.
    """
    scale = _PLATE_SCALE
    image = Image.new("RGB", (WIDTH * scale, HEIGHT * scale), _rgb(_COLOR_KEY))
    draw = ImageDraw.Draw(image)
    for inset, fill in _PLATE_LAYERS:
        draw.rounded_rectangle(
            (
                inset * scale, inset * scale,
                (WIDTH - 1 - inset) * scale, (HEIGHT - 1 - inset) * scale,
            ),
            radius=max(0, CORNER - inset) * scale,
            fill=_rgb(fill),
        )
    return image.resize((WIDTH, HEIGHT), _PLATE_RESAMPLE)


def _bell(distance: float) -> float:
    """A smooth bell: 1.0 at the centre bar, 0.0 at the outermost ones."""
    return 0.5 * (1.0 + math.cos(math.pi * distance))


def _swing(phase: float) -> float:
    """The wobble at one phase, folded into -1.0 .. 1.0.

    Two sines at different rates are a smooth pseudo-random signal: no bar
    repeats another's path, none of them stands still, and the sign is which way
    this bar leaves its bell height on this tick.
    """
    return (math.sin(phase) + 0.5 * math.sin(2.7 * phase + 1.3)) / 1.5


# The share of the energy each bar may take, in pixels above the idle height.
# A raised cosine keeps every neighbour close to the next, so the row tapers
# outward with no visible step between bars.
_CENTRE = (BARS - 1) / 2
_BELL_SPAN = tuple(
    BAR_SPAN_MIN + (BAR_SPAN_MAX - BAR_SPAN_MIN) * _bell(
        abs(index - _CENTRE) / _CENTRE
    )
    for index in range(BARS)
)


class RecordingOverlay:
    """A focusless chip: eleven thin equalizer bars over the elapsed seconds.

    `next_level` is the engine's level accessor. It is called once per tick
    from the Tk thread, never from the audio thread, and None means no
    measurement arrived this tick.

    The `Toplevel` is built on the first `show` and reused by every later
    recording, so repeated sessions cannot leak windows or timers. Every method
    must be called from the Tk thread that owns the panel, because the chip is a
    child of the panel's interpreter and never a second interpreter of its own.
    """

    def __init__(
        self, master: tk.Misc, next_level: Callable[[], float | None]
    ) -> None:
        self._master = master
        self._next_level = next_level
        self._window: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None
        self._plate: Image.Image | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._bars: list[list[int]] = []
        self._heights = [float(BAR_IDLE)] * BARS
        self._energy = 0.0
        self._phase = [PHASE_SPREAD * index for index in range(BARS)]
        self._swing = [_swing(phase) for phase in self._phase]
        self._plate_failed = False
        self._clock: int | None = None
        self._timer: str | None = None
        self._shown = False
        self._second = -1
        self._since = 0.0

    def show(self) -> None:
        """Make the chip visible and start the elapsed counter."""
        if self._window is None:
            self._window = self._build()
        self._since = time.monotonic()
        self._second = -1
        self._energy = 0.0
        self._heights = [float(BAR_IDLE)] * BARS
        self._place()
        try:
            self._window.deiconify()
            self._window.attributes("-topmost", True)
        except tk.TclError:
            log.debug("overlay window is gone", exc_info=True)
            self._forget()
            return
        self._shown = True
        self._second = self._paint(None)
        self._arm()

    def hide(self) -> None:
        """Take the chip off the screen without destroying it."""
        self._disarm()
        self._shown = False
        if self._window is None:
            return
        try:
            self._window.withdraw()
        except tk.TclError:
            log.debug("overlay window is gone", exc_info=True)
            self._forget()

    def destroy(self) -> None:
        """Cancel the timer and drop the window for good."""
        self._disarm()
        self._shown = False
        window, self._window = self._window, None
        self._forget()
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                log.debug("overlay window is gone", exc_info=True)

    def _forget(self) -> None:
        """Drop references to a window the platform has already closed."""
        self._window = None
        self._canvas = None
        self._plate = None
        self._photo = None
        self._bars = []
        self._clock = None

    def _build(self) -> tk.Toplevel:
        window = tk.Toplevel(self._master)
        # withdraw first: a window that is never mapped cannot steal the focus
        window.withdraw()
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.attributes("-transparentcolor", _COLOR_KEY)
        window.resizable(False, False)

        canvas = tk.Canvas(
            window, width=WIDTH, height=HEIGHT, bg=_COLOR_KEY,
            highlightthickness=0, borderwidth=0,
        )
        canvas.pack(fill="both", expand=True)
        self._canvas = canvas
        self._put_plate(window, canvas)
        self._draw_bars(canvas)
        self._clock = canvas.create_text(
            WIDTH // 2, CLOCK_Y, text="0:00", fill=_CLOCK, font=_CLOCK_FONT
        )
        # Tk rewrites the extended style every time the window is mapped, so
        # the no-activate bit has to be put back after each map, not once here.
        window.bind("<Map>", self._on_map)
        # Belt and braces are not enough on their own: <Map> arrives on a later
        # loop iteration, while the first deiconify already maps the window. A
        # ShowWindow in between could take the foreground, and then the dictated
        # fragment is dropped instead of typed. A withdrawn window has no
        # chance of being activated, so the style goes on before the first map.
        self._forbid_activation(window)
        return window

    def _put_plate(self, window: tk.Toplevel, canvas: tk.Canvas) -> None:
        """Lay the plate on: the antialiased one, or a square one without Pillow.

        This is the only Pillow call on the run-time path and it is reached from
        the panel's own pump, before the pump has rescheduled itself, so
        anything raised here would leave the application alive on screen and
        dead to every command, event and hotkey. A failed allocation, a broken
        draw and a Pillow too old for Image.Resampling all end up here, and
        none of them is worth more than a square plate: the chip is decoration,
        the application is not. The failure is reported once and never again,
        because the chip is only rebuilt after the window is gone and the second
        report would say nothing the first one did not.

        Only the Pillow work is guarded. Tk failing to put an image on a canvas
        is a Tk failure, and it is left to raise as one.
        """
        try:
            plate = build_plate()
            photo = ImageTk.PhotoImage(plate, master=window)
        except Exception:
            if not self._plate_failed:
                self._plate_failed = True
                log.error(
                    "the chip cannot draw its antialiased plate, using a "
                    "square one instead", exc_info=True,
                )
            self._plate = None
            self._photo = None
            self._draw_square_plate(canvas)
            return
        # The plate never changes, so it is built once and held for the lifetime
        # of the chip: a fresh Pillow image every 30 ms would be work with
        # nothing to show for it. The PhotoImage is held too, because Tk keeps
        # no reference of its own and would otherwise draw nothing.
        self._plate = plate
        self._photo = photo
        canvas.create_image(0, 0, anchor="nw", image=photo)

    def _draw_square_plate(self, canvas: tk.Canvas) -> None:
        """Lay the plate on from canvas rectangles, for when Pillow cannot.

        The same layers in the same order as the Pillow path, so the chip still
        looks like the same chip with a square edge instead of a rounded one.
        Only the antialiasing is missing. Nothing here is mapped yet, so none of
        it can take the focus.
        """
        for inset, fill in _PLATE_LAYERS:
            canvas.create_rectangle(
                inset, inset, WIDTH - 1 - inset, HEIGHT - 1 - inset,
                fill=fill, outline="",
            )

    def _draw_bars(self, canvas: tk.Canvas) -> None:
        """Create the five rectangles one mirrored bar is made of.

        A bar is a low block on the centre line with a mid and a high band on
        each side of it, so the fixed ramp reads the same upwards as downwards.
        The colours are set once and only the coordinates move per frame, so a
        bar keeps its ramp as it grows and shrinks.
        """
        for index in range(BARS):
            left = _bar_left(index)
            right = left + BAR_WIDTH
            self._bars.append([
                canvas.create_rectangle(
                    left, BAR_MID, right, BAR_MID, fill=_BAR_LOW, outline="",
                ),
                canvas.create_rectangle(
                    left, BAR_MID, right, BAR_MID, fill=_BAR_MID, outline="",
                ),
                canvas.create_rectangle(
                    left, BAR_MID, right, BAR_MID, fill=_BAR_MID, outline="",
                ),
                canvas.create_rectangle(
                    left, BAR_MID, right, BAR_MID, fill=_BAR_HIGH, outline="",
                ),
                canvas.create_rectangle(
                    left, BAR_MID, right, BAR_MID, fill=_BAR_HIGH, outline="",
                ),
            ])

    def _on_map(self, event=None) -> None:
        """Keep the chip out of the focus, every time it comes back on screen."""
        if event is not None and event.widget is not self._window:
            return
        self._forbid_activation(self._window)

    def _place(self) -> None:
        """Centre the chip in the work area, just above the taskbar.

        The work area is what is left of the screen once the taskbar and any
        other app bar are subtracted, so this stays correct when the taskbar
        is on another edge, when it is auto-hidden, and when it reserves no
        space at all. The height is never guessed.
        """
        window = self._window
        if window is None:
            return
        area = _Rect()
        if user32.SystemParametersInfoW(
            SPI_GETWORKAREA, 0, ctypes.byref(area), 0
        ):
            left, right, bottom = area.left, area.right, area.bottom
        else:
            log.debug("no work area, falling back to the screen size", exc_info=True)
            left, right = 0, window.winfo_screenwidth()
            bottom = window.winfo_screenheight()
        x = left + max(0, (right - left - WIDTH) // 2)
        y = max(0, bottom - MARGIN_ABOVE_TASKBAR - HEIGHT)
        window.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")

    def _forbid_activation(self, window: tk.Toplevel | None) -> None:
        """Ask Windows for a window that can never be brought into the focus."""
        if window is None:
            return
        try:
            hwnd = int(window.wm_frame(), 16)
        except (ValueError, tk.TclError):
            log.debug("no frame handle for the overlay", exc_info=True)
            return
        if not hwnd:
            return
        style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(
            hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        )

    def _smooth(self, level: float | None) -> None:
        """Fold one measurement into the energy and advance the wobble.

        None means no sub-frame arrived this tick, which happens whenever the
        decoder outruns the animation; the energy then falls back towards
        silence and the followers keep moving, so a gap reads as a gap in the
        sound and never as a stall of the window. The gate is what the animation
        is really built on: not how loud, only whether anything is being said.
        """
        raw = 0.0 if level is None else min(1.0, max(0.0, level))
        self._energy += (raw - self._energy) * (
            ATTACK if raw > self._energy else DECAY
        )
        if self._energy < GATE:
            self._energy = 0.0
        for index in range(BARS):
            # The outer bars turn over more slowly, so the row never pulses as
            # a block. Two sines at different rates are a smooth pseudo-random
            # wobble: no bar repeats another's path and none of them stands
            # still, while the amplitudes stay far under the steps between
            # neighbouring bars.
            self._phase[index] += WOBBLE_STEP * (
                1.0 - 0.45 * abs(index - _CENTRE) / _CENTRE
            )
            self._swing[index] = _swing(self._phase[index])

    def _paint(self, level: float | None) -> int:
        """Move every bar one step towards the animation and redraw the chip.

        Returns the second currently on the clock, which the caller uses to
        rewrite the label only when it really changed.
        """
        canvas = self._canvas
        if canvas is None:
            return self._second
        self._smooth(level)
        # The drive belongs here and nowhere else, so the stored energy stays a
        # plain smoothed microphone level: the gate in _smooth and the release
        # below are both measured on the microphone, not on a boosted copy of it.
        # Clamping it here rather than there also keeps a loud level from
        # running the bars off the field.
        drive = min(1.0, self._energy * DRIVE)
        try:
            for index, bar in enumerate(self._bars):
                # The bell share of the energy, then the wobble as a share of
                # that bar's own height plus its fraction of a pixel of texture.
                # Both parts ride on the drive, so a silent stream lands every
                # bar on BAR_IDLE exactly and the row keeps its shape at any
                # drive, which is the whole point of the bell.
                swing = self._swing[index]
                goal = (
                    BAR_IDLE
                    + drive * (
                        _BELL_SPAN[index] * (1.0 + WOBBLE_REL * swing)
                        + WOBBLE_ABS * swing
                    )
                )
                height = self._heights[index]
                distance = abs(index - _CENTRE) / _CENTRE
                rate = (
                    ATTACK * (1.0 - 0.04 * distance) if goal > height
                    else DECAY * (1.0 + 0.06 * distance)
                )
                height += (goal - height) * rate
                self._heights[index] = height
                self._resize(canvas, bar, index, height)
            seconds = int(time.monotonic() - self._since)
            if seconds != self._second and self._clock is not None:
                self._second = seconds
                canvas.itemconfigure(
                    self._clock, text=f"{seconds // 60}:{seconds % 60:02d}"
                )
        except tk.TclError:
            log.debug("overlay canvas is gone", exc_info=True)
            self._forget()
        return self._second

    def _resize(self, canvas: tk.Canvas, bar: list[int], index: int, span: float) -> None:
        """Mirror one bar around the centre line in its five rectangles.

        `span` is the half height in pixels, so the bar reaches BAR_MID-span to
        BAR_MID+span and is symmetric by construction. The rectangles are split
        into thirds on each side of the centre line, which is what keeps the
        ramp in place: only the two outer edges of the bar travel.
        """
        third = span / 3
        for item, bottom, top in (
            (bar[0], BAR_MID + third, BAR_MID - third),
            (bar[1], BAR_MID - third, BAR_MID - 2 * third),
            (bar[2], BAR_MID + 2 * third, BAR_MID + third),
            (bar[3], BAR_MID - 2 * third, BAR_MID - span),
            (bar[4], BAR_MID + span, BAR_MID + 2 * third),
        ):
            canvas.coords(item, *_bar_box(index, top, bottom))

    def _arm(self) -> None:
        self._disarm()
        if self._window is not None:
            self._timer = self._window.after(TICK_MS, self._tick)

    def _disarm(self) -> None:
        if self._timer is not None and self._window is not None:
            try:
                self._window.after_cancel(self._timer)
            except tk.TclError:
                log.debug("overlay timer is gone", exc_info=True)
        self._timer = None

    def _tick(self) -> None:
        self._timer = None
        self._paint(self._next_level())
        if self._shown:
            self._arm()


def _bar_left(index: int) -> int:
    """Left edge of one bar, by its index in the row."""
    return BAR_MARGIN + index * (BAR_WIDTH + BAR_GAP)


def _bar_box(index: int, top: float, bottom: float) -> tuple[float, float, float, float]:
    """Left and right edge of one bar, by its index in the row."""
    left = _bar_left(index)
    return left, top, left + BAR_WIDTH, bottom
