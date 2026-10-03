"""The panel's own widgets: cards, buttons, switches, choices, tabs, a scroller.

Tk's stock widgets are square, hard edged, and cannot be told to change colour
when the pointer arrives, which is the whole of what a modern panel is made of.
So each widget here is either a `tk.Canvas` that paints itself from `theme` and
repaints on `<Enter>`, `<Leave>`, `<ButtonPress-1>`, `<ButtonRelease-1>`,
`<FocusIn>` and `<FocusOut>`, or a `tk.Frame` that lays a painted label behind its
children.

Two rules hold across all of them, because `panel.py` and `panel.set_language`
depend on both:

  * `configure(text=...)` means the visible label, whatever the widget is made
    of. A language change is a repaint of the widgets that are already there, and
    it never rebuilds the window, so every widget has to answer to the same
    option name a `tk.Button` would.
  * `configure(state="disabled")` takes the widget out of the click path and
    paints it from the disabled roles. Canvas has a `state` option of its own, so
    the interception has to happen before the call reaches Tk.

Sizes are design tokens multiplied by `theme.px()`, and a widget that carries a
label measures it, so a button is exactly as wide as its own text and a longer
translation makes the button longer rather than clipping it.
"""

from __future__ import annotations

import logging
import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable

from PIL import ImageTk

from . import theme

log = logging.getLogger(__name__)

CHECK_BOX = 20
CHECK_STROKE = 2
CHECK_RADIUS = 6
SWITCH_WIDTH = 40
SWITCH_HEIGHT = 22
SWITCH_KNOB = 18
DOT = 8

# The type scale, in design pixels like every other length here. A body of 13 px
# and a caption of 12 px are two steps, not a family: this panel has four sizes
# in it and a fifth would be a decision nobody made on purpose.
TYPE_HEADING = 16
TYPE_BODY = 13
TYPE_CAPTION = 12
TYPE_MONO = 15
TYPE_TINY = 11


class _Textual:
    """`configure(text=...)` and `cget("text")` on anything, as a mix-in.

    Panel registers a closure per widget that shows a message and calls
    `configure(text=...)` on it when the language changes, so this is the one
    option name that must mean the same thing everywhere.
    """

    def configure(self, cnf=None, **kw):  # noqa: D102 - see the class docstring
        if cnf is None and "text" in kw:
            self._set_text(kw.pop("text"))  # type: ignore[attr-defined]
            if not kw:
                return None
        elif isinstance(cnf, dict) and "text" in cnf:
            options = dict(cnf)
            self._set_text(options.pop("text"))  # type: ignore[attr-defined]
            if not options and not kw:
                return None
            cnf = options or None
        return super().configure(cnf, **kw)  # type: ignore[misc]

    def cget(self, key):  # noqa: D102
        if key == "text":
            return self._get_text()  # type: ignore[attr-defined]
        return super().cget(key)  # type: ignore[misc]

    def _set_text(self, value: str) -> None:
        raise NotImplementedError

    def _get_text(self) -> str:
        return ""


# Cards.


class Card(tk.Frame):
    """A rounded surface with a soft shadow instead of a border.

    The shadow has to be painted, because the hairline it replaces cannot be: a
    one pixel line is the thing this design is leaving behind. Tk cannot blend
    two widgets, so the shadow is baked into an image laid under the content, and
    the panel's own colour is painted into that image's margin — which is what
    makes the rounded corner and the shadow disappear into the panel instead of
    showing up as a rectangle.

    The margin is the frame's own `padx`/`pady`, so the frame still reports the
    size the content needs, and the plate is `place`d at a negative offset so it
    bleeds out over the margin. A frame does not clip its children, so the bleed
    is drawn; and because the plate is placed rather than packed, laying it down
    cannot change the size the frame asks for, so repainting on `<Configure>`
    cannot loop.
    """

    def __init__(
        self, master: tk.Misc, *, palette: theme.Palette,
        padding: int = theme.SPACE_MD, radius: int = theme.RADIUS_CARD,
        shadow: bool = True, bg: str | None = None,
    ) -> None:
        self._palette = palette
        self._matte = bg or palette.bg
        self._radius = radius
        self._shadow = shadow
        self._margin = theme.shadow_margin(theme.card_shadow(palette) if shadow else None)
        super().__init__(
            master, bg=self._matte, bd=0, highlightthickness=0,
            padx=padding + self._margin, pady=padding + self._margin,
        )
        self._plate: ImageTk.PhotoImage | None = None
        self._backdrop = tk.Label(self, bd=0, bg=self._matte, highlightthickness=0)
        self._backdrop.place(
            x=-self._margin, y=-self._margin, relwidth=1, relheight=1,
            width=self._margin * 2, height=self._margin * 2,
        )
        self.inner = tk.Frame(self, bg=palette.surface, bd=0, highlightthickness=0)
        self.inner.pack(fill="both", expand=True)
        self._painted: tuple[int, int] | None = None
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        size = (event.width, event.height)
        if size == self._painted or min(size) <= 0:
            return
        self._painted = size
        image = theme.surface(
            size[0] - self._margin * 2, size[1] - self._margin * 2,
            theme.px(self._radius), self._palette.surface, matte=self._matte,
            shadow=theme.card_shadow(self._palette) if self._shadow else None,
        )
        try:
            self._plate = ImageTk.PhotoImage(image, master=self)
            self._backdrop.configure(image=self._plate)
        except tk.TclError:
            log.debug("card backdrop is gone", exc_info=True)


# Buttons.


class Button(_Textual, tk.Canvas):
    """A rounded button with a hover plate, a pressed plate and a focus ring.

    `variant` picks the palette roles rather than a colour, so the two themes stay
    one design:

      * `primary` fills with the accent and carries a shadow — one per panel, for
        the one action the panel exists for.
      * `secondary` is a surface with a hairline, for the buttons beside it.
      * `ghost` is nothing at all until the pointer arrives, for a row of three.
      * `danger` is the soft danger fill the record button takes while it runs.

    `hold=True` makes the button a press-and-hold control rather than a click one:
    `on_press` fires on `<ButtonPress-1>` and `on_release` on `<ButtonRelease-1>`
    wherever the pointer went. That is the record button, and it cannot be driven
    from the keyboard — which is what the global hotkey is for, and what the old
    `tk.Button` arrangement did too.
    """

    HEIGHTS = {"sm": 32, "md": 38, "lg": 44}
    PADDING = {"sm": 12, "md": 16, "lg": 20}
    MIN_WIDTH = 64

    def __init__(
        self, master: tk.Misc, *, text: str = "", palette: theme.Palette,
        command: Callable[[], None] | None = None,
        on_press: Callable[[], None] | None = None,
        on_release: Callable[[], None] | None = None,
        variant: str = "ghost", size: str = "md", font: tkfont.Font | None = None,
        bg: str | None = None,
    ) -> None:
        self._palette = palette
        self._variant = variant
        self._size = size
        self._label = text
        self._font = font or theme.ui(TYPE_BODY)
        self._command = command
        self._on_press = on_press
        self._on_release = on_release
        self._enabled = True
        self._busy = False
        self._hover = False
        self._down = False
        self._inside = False
        self._plate: ImageTk.PhotoImage | None = None
        height = theme.px(self.HEIGHTS[size])
        super().__init__(
            master, height=height, width=self._natural_width(), bd=0,
            relief="flat", takefocus=0, bg=bg or palette.surface, cursor="hand2",
        )
        # The focus ring is drawn by `_paint`, so Tk's own highlight is only
        # asked for while the button has the keyboard focus: the padding it
        # reserves is the ring's inset.
        self.configure(
            highlightthickness=theme.px(2), highlightbackground=palette.bg,
            highlightcolor=palette.bg,
        )
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<FocusIn>", lambda _e: self._paint())
        self.bind("<FocusOut>", lambda _e: self._paint())
        self.bind("<Return>", self._activate)
        self.bind("<space>", self._activate)
        # Repaint when the widget is actually given its size: the first paint
        # happens before `pack`, so it draws at the width the label measures to
        # and every later layout would leave the plate at the wrong size.
        self.bind("<Configure>", lambda _e: self._paint())
        self._paint()

    # The label, and the width that follows it.

    def _natural_width(self) -> int:
        pad = theme.px(self.PADDING[self._size])
        return max(theme.px(self.MIN_WIDTH), theme.measure(self._font, self._label) + pad * 2)

    def _set_text(self, value: str) -> None:
        self._label = value
        self.configure(width=self._natural_width())
        self._paint()

    def _get_text(self) -> str:
        return self._label

    # State.

    def set_enabled(self, enabled: bool) -> None:
        """Take the button out of the click path and paint it disabled."""
        self._enabled = bool(enabled)
        self._busy = False
        self._down = False
        self.configure(cursor="hand2" if enabled else "")
        self._paint()

    def set_busy(self, busy: bool) -> None:
        """The third state: it takes no clicks but says what it is doing.

        A disabled button reads as unavailable, and the record button while a
        recording runs is not unavailable — it is live. So it keeps its accent,
        takes the danger fill, and refuses the click that the release would
        otherwise turn into a stop.
        """
        self._busy = bool(busy)
        self._enabled = not self._busy
        self._down = False
        self._paint()

    def _enter(self, _event=None) -> None:
        self._hover = True
        self._inside = True
        self._paint()

    def _leave(self, _event=None) -> None:
        self._hover = False
        self._inside = False
        self._down = False
        self._paint()

    def _press(self, _event=None) -> None:
        self.focus_set()
        if not self._enabled:
            return
        self._down = True
        self._paint()
        if self._on_press is not None:
            self._on_press()

    def _release(self, _event=None) -> None:
        was_down, self._down = self._down, False
        if self._on_release is not None:
            if was_down:
                self._on_release()
        elif self._enabled and was_down and self._inside:
            self._activate(None)
        self._paint()

    def _activate(self, _event=None) -> str | None:
        if self._enabled and self._command is not None and self._on_press is None:
            self._command()
        return "break"

    # Painting.

    def _roles(self) -> tuple[str, str, str | None, tuple[str, int, int] | None]:
        """Fill, foreground, hairline and shadow for the current state.

        One place decides what a button looks like, which is what keeps a disabled
        button from being a differently coloured live one.
        """
        p = self._palette
        pressed = self._down and self._enabled
        if self._busy:
            return p.danger_soft, p.danger, p.danger, None
        if not self._enabled:
            return (
                (p.surface_alt if self._variant != "ghost" else p.bg),
                p.text_subtle, None, None,
            )
        if self._variant == "primary":
            fill = p.accent_press if pressed else (
                p.accent_hover if self._hover else p.accent
            )
            return fill, p.accent_on, None, theme.card_shadow(p, raised=pressed)
        if self._variant == "secondary":
            fill = p.surface_alt if (pressed or self._hover) else p.surface
            return fill, p.text, p.border, None
        if self._variant == "danger":
            fill = p.danger if pressed else (
                p.danger_soft if self._hover else p.bg
            )
            return fill, (p.danger_soft if pressed else p.danger), p.danger, None
        fill = p.surface_hover if pressed else (
            p.surface_alt if self._hover else p.bg
        )
        return fill, (p.text if self._hover else p.text_muted), None, None

    def _paint(self) -> None:
        fill, foreground, border, shadow = self._roles()
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        if width <= 1 or height <= 1:
            width, height = self._natural_width(), theme.px(self.HEIGHTS[self._size])
        try:
            self._plate = ImageTk.PhotoImage(
                theme.surface(
                    width, height, theme.px(theme.RADIUS_CONTROL), fill,
                    matte=self["bg"], border=border, border_width=theme.px(1),
                    shadow=shadow,
                ),
                master=self,
            )
        except tk.TclError:
            log.debug("button plate is gone", exc_info=True)
            return
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=self._plate)
        if self.focus_get() is self:
            inset = theme.px(2)
            ring = ImageTk.PhotoImage(
                theme.surface(
                    width - inset * 2, height - inset * 2,
                    theme.px(theme.RADIUS_CONTROL) - inset, self["bg"],
                    matte=self["bg"], border=self._palette.accent,
                    border_width=theme.px(2),
                ),
                master=self,
            )
            self._plate = ring
            self.create_image(inset, inset, anchor="nw", image=ring)
        self.create_text(
            width // 2, height // 2, text=self._label, font=self._font,
            fill=foreground, anchor="center",
        )


# Choices: a checkbox and a radio, sharing everything but the mark.


class Choice(_Textual, tk.Frame):
    """A 20 px rounded box with its label beside it, or a radio dot.

    The mark is a canvas, because it has to repaint on hover and on a change of
    value. The label stays a `tk.Label`, because a long option has to wrap — and
    a canvas does not wrap, it clips or overflows, and either one turns a settings
    tab into a wall. `wraplength` is therefore a real argument here rather than
    something worked out from the parent, exactly as it was on the `tk.Checkbutton`
    this replaces.

    The value goes through a `tk.Variable` and the widget only traces it, so
    `set()` from the application and a click from the user arrive by the same
    road and a program-driven update never fires the command.
    """

    def __init__(
        self, master: tk.Misc, *, palette: theme.Palette, kind: str = "check",
        text: str = "", variable: tk.Variable | None = None,
        command: Callable[[], None] | None = None,
        font: tkfont.Font | None = None, wraplength: int = 0, value: str = "",
        bg: str | None = None,
    ) -> None:
        self._palette = palette
        self._kind = kind
        self._label = text
        # What a radio puts into the variable when it is clicked. A checkbox has
        # none: it flips whatever is there.
        self._value = value
        self._font = font or theme.ui(TYPE_BODY)
        self._command = command
        self._hover = False
        self._matte = bg or palette.surface
        super().__init__(
            master, bg=self._matte, bd=0, highlightthickness=0, cursor="hand2"
        )
        side = theme.px(CHECK_BOX)
        self._box = tk.Canvas(
            self, width=side, height=side, bd=0, highlightthickness=0,
            bg=self._matte, cursor="hand2",
        )
        # Sit the box on the first line's optical centre rather than its top:
        # 1.5 line height leaves the first baseline well below the frame's top.
        self._box.pack(
            side="left", anchor="n", padx=(0, theme.px(theme.SPACE)),
            pady=(max(0, theme.line_height(self._font) // 2 - side // 2), 0),
        )
        self._text = tk.Label(
            self, text=text, font=self._font, bg=self._matte, fg=palette.text,
            anchor="w", justify="left", wraplength=wraplength or 0,
        )
        self._text.pack(side="left", anchor="n", fill="x", expand=True)
        for widget in (self._box, self._text, self):
            widget.bind("<Button-1>", self._toggle)
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)
        self._variable = variable
        self._trace: str | None = None
        if variable is not None:
            self._trace = variable.trace_add("write", lambda *_: self._paint())
            self.bind("<Destroy>", self._forget)
        self._plate: ImageTk.PhotoImage | None = None
        self._paint()

    def _forget(self, _event=None) -> None:
        """Let go of the variable when this widget is destroyed.

        The variable belongs to the panel and outlives a theme change, which is
        the whole point of it. A trace left behind fires into a canvas that is no
        longer there, and Tk answers that from inside a callback, where an
        exception is printed and swallowed rather than raised: the panel would
        carry on with a settings tab that no longer repaints and nothing in
        `app.log` to say why.
        """
        if self._trace is not None and self._variable is not None:
            try:
                self._variable.trace_remove("write", self._trace)
            except tk.TclError:
                log.debug("choice trace is gone", exc_info=True)
            self._trace = None

    def _enter(self, _event=None) -> None:
        self._hover = True
        self._paint()

    def _leave(self, _event=None) -> None:
        self._hover = False
        self._paint()

    def _toggle(self, _event=None) -> None:
        if self._variable is None:
            return
        self.focus_set()
        if self._kind == "radio":
            self._variable.set(self._value)
        else:
            self._variable.set(not self._variable.get())
        if self._command is not None:
            self._command()

    def _set_text(self, value: str) -> None:
        self._label = value
        self._text.configure(text=value)

    def _get_text(self) -> str:
        return self._label

    @property
    def value(self) -> str:
        """The code a radio stands for, or the variable's own text for a box."""
        if self._kind == "radio":
            return self._value
        return str(self._variable.get()) if self._variable is not None else ""

    def set(self, value) -> None:
        """Put the mark where `value` says, without firing the command."""
        if self._kind == "radio":
            self._value = str(value)
        if self._variable is not None:
            self._variable.set(value)

    def _paint(self) -> None:
        p = self._palette
        on = bool(self._variable.get()) if self._variable is not None else False
        side = theme.px(CHECK_BOX)
        radius = theme.px(side // 2 if self._kind == "radio" else CHECK_RADIUS)
        fill = p.accent if on else p.surface
        border = p.accent if (on or self._hover) else p.border_strong
        try:
            self._plate = ImageTk.PhotoImage(
                theme.surface(
                    side, side, radius, fill, matte=self._matte, border=border,
                    border_width=theme.px(CHECK_STROKE if on or self._hover else 1),
                ),
                master=self._box,
            )
        except tk.TclError:
            log.debug("choice plate is gone", exc_info=True)
            return
        self._box.delete("all")
        self._box.create_image(0, 0, anchor="nw", image=self._plate)
        if not on:
            return
        if self._kind == "radio":
            pad = side * 0.3
            self._box.create_oval(
                pad, pad, side - pad - 1, side - pad - 1,
                fill=p.accent_on, outline="",
            )
            return
        stroke = theme.px(CHECK_STROKE)
        self._box.create_line(
            side * 0.24, side * 0.52, side * 0.43, side * 0.71,
            fill=p.accent_on, width=stroke, capstyle="round",
        )
        self._box.create_line(
            side * 0.43, side * 0.71, side * 0.76, side * 0.29,
            fill=p.accent_on, width=stroke, capstyle="round",
        )


class Switch(tk.Canvas):
    """An on/off pill: the track is the value, the knob is the only thing that moves."""

    def __init__(
        self, master: tk.Misc, *, palette: theme.Palette,
        variable: tk.BooleanVar | None = None,
        command: Callable[[], None] | None = None, bg: str | None = None,
    ) -> None:
        self._palette = palette
        self._variable = variable
        self._command = command
        self._enabled = True
        self._trace: str | None = None
        self._plate: ImageTk.PhotoImage | None = None
        super().__init__(
            master, width=theme.px(SWITCH_WIDTH), height=theme.px(SWITCH_HEIGHT),
            bd=0, highlightthickness=0, bg=bg or palette.surface, cursor="hand2",
        )
        self.bind("<Button-1>", self._toggle)
        self.bind("<FocusIn>", lambda _e: self._paint())
        self.bind("<FocusOut>", lambda _e: self._paint())
        if variable is not None:
            self._trace = variable.trace_add("write", lambda *_: self._paint())
            self.bind("<Destroy>", self._forget)
        self._paint()

    def _forget(self, _event=None) -> None:
        """Drop the variable's trace on the way out. See `Choice._forget`."""
        if self._trace is not None and self._variable is not None:
            try:
                self._variable.trace_remove("write", self._trace)
            except tk.TclError:
                log.debug("switch trace is gone", exc_info=True)
            self._trace = None

    def _toggle(self, _event=None) -> None:
        if self._variable is None or not self._enabled:
            return
        self.focus_set()
        self._variable.set(not self._variable.get())
        if self._command is not None:
            self._command()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self.configure(cursor="hand2" if enabled else "")
        self._paint()

    def set(self, value: bool) -> None:
        if self._variable is not None:
            self._variable.set(bool(value))

    def _paint(self) -> None:
        p = self._palette
        on = bool(self._variable.get()) if self._variable is not None else False
        width, height = theme.px(SWITCH_WIDTH), theme.px(SWITCH_HEIGHT)
        knob = theme.px(SWITCH_KNOB)
        track = (p.accent if on else p.border) if self._enabled else p.surface_alt
        try:
            self._plate = ImageTk.PhotoImage(
                theme.surface(width, height, height // 2, track, matte=self["bg"]),
                master=self,
            )
        except tk.TclError:
            log.debug("switch plate is gone", exc_info=True)
            return
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=self._plate)
        inset = (height - knob) // 2
        centre_x = (width - knob - inset) if on else inset
        # A canvas oval's second pair is the last pixel, not the one past it, so
        # the corner is written as `+ knob - 1`: without it the knob sits flush
        # against the end of the track on one side and inset on the other.
        self.create_oval(
            centre_x, inset, centre_x + knob - 1, inset + knob - 1,
            fill=p.surface if self._enabled else p.bg,
            outline=p.accent if (on and self.focus_get() is self) else "",
            width=theme.px(2),
        )


class Dot(tk.Canvas):
    """A small filled circle, for a status that should be seen before it is read."""

    def __init__(self, master: tk.Misc, *, palette: theme.Palette,
                 colour: str, bg: str | None = None) -> None:
        self._palette = palette
        self._colour = colour
        size = theme.px(DOT)
        super().__init__(
            master, width=size, height=size, bd=0, highlightthickness=0,
            bg=bg or palette.surface,
        )
        self._paint()
        self.bind("<Configure>", lambda _e: self._paint())

    def set_colour(self, colour: str) -> None:
        self._colour = colour
        self._paint()

    def _paint(self) -> None:
        self.delete("all")
        self.create_oval(
            0, 0, self.winfo_width() - 1, self.winfo_height() - 1,
            fill=self._colour, outline="",
        )


class Field(_Textual, tk.Canvas):
    """A read-only field that shows the hotkey combination and asks for a click.

    An input is the one place a hairline border is right rather than a shadow:
    the brief is "soft shadows instead of hard borders", and a field has to read
    as something to be typed into, which is what a border says. The border goes
    to the accent on hover and while a capture is live, so the field itself is the
    progress indicator.
    """

    HEIGHT = 44
    PADDING = 14

    def __init__(
        self, master: tk.Misc, *, palette: theme.Palette, text: str = "",
        command: Callable[[], None] | None = None, bg: str | None = None,
    ) -> None:
        self._palette = palette
        self._label = text
        self._font = theme.mono(TYPE_MONO)
        self._command = command
        self._active = False
        self._plate: ImageTk.PhotoImage | None = None
        super().__init__(
            master, height=theme.px(self.HEIGHT),
            width=self._natural_width(), bd=0, highlightthickness=0,
            bg=bg or palette.surface, cursor="hand2",
        )
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda _e: self._paint())
        self.bind("<Leave>", lambda _e: self._paint())
        self.bind("<Configure>", lambda _e: self._paint())
        self._paint()

    def _natural_width(self) -> int:
        pad = theme.px(self.PADDING) * 2
        return max(theme.px(180), theme.measure(self._font, self._label) + pad)

    def _set_text(self, value: str) -> None:
        self._label = value
        self.configure(width=self._natural_width())
        self._paint()

    def _get_text(self) -> str:
        return self._label

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self.configure(cursor="watch" if active else "hand2")
        self._paint()

    def _click(self, _event=None) -> None:
        self.focus_set()
        if self._command is not None:
            self._command()

    def _paint(self) -> None:
        p = self._palette
        border = p.accent if (self._active or self.focus_get() is self) else p.border
        width = max(1, self.winfo_width()) or self._natural_width()
        height = max(1, self.winfo_height()) or theme.px(self.HEIGHT)
        try:
            self._plate = ImageTk.PhotoImage(
                theme.surface(
                    width, height, theme.px(theme.RADIUS_CONTROL), p.surface_alt,
                    matte=self["bg"], border=border, border_width=theme.px(1),
                ),
                master=self,
            )
        except tk.TclError:
            log.debug("field plate is gone", exc_info=True)
            return
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=self._plate)
        self.create_text(
            theme.px(self.PADDING), height // 2, text=self._label, font=self._font,
            fill=p.text, anchor="w",
        )


# Wrapped prose.


class Paragraph(_Textual, tk.Frame):
    """A wrapped paragraph at a real line height, and nothing else.

    A `tk.Label` cannot do the height. Tk offers no line-height option anywhere:
    the space between two lines of a label is the font's own line spacing and
    there is no knob for it, so `line-height: 1.5` is unreachable from one. A
    `tk.Text` is, through `spacing1` and `spacing3`, which put air above the
    first line and below every one of them — the standard way to reach a
    stylesheet's leading in Tk.

    The line breaks are made here rather than left to the widget. `Text` wraps on
    its own, but what it decides is not what `font.measure` says, and the
    difference shows as the last word of a paragraph sitting half-drawn at the
    right edge. Breaking the lines from the same measurement the height is
    computed from means the two cannot disagree, and means this widget's height
    is the height it will be rather than the height it hoped for.
    """

    def __init__(
        self, master: tk.Misc, *, palette: theme.Palette, text: str = "",
        size: int = TYPE_CAPTION, colour: str | None = None, bg: str | None = None,
        leading: float = theme.LINE_HEIGHT, width: int = 0,
    ) -> None:
        self._palette = palette
        self._body = text
        self._size = size
        self._font = theme.ui(size)
        self._pixels = max(1, width)
        self._lines: list[str] = []
        super().__init__(master, bg=bg or palette.surface, bd=0, highlightthickness=0)
        air = theme.leading(self._font, size, leading)
        self._text = tk.Text(
            self, wrap="char", width=1, height=1, bd=0, highlightthickness=0,
            relief="flat", bg=bg or palette.surface,
            fg=colour or palette.text_subtle, font=self._font, padx=0, pady=0,
            spacing1=air, spacing3=air, insertwidth=0, cursor="arrow",
            state="disabled", takefocus=0,
        )
        self._text.pack(fill="both", expand=True)
        self.bind("<Configure>", self._on_frame)
        self._apply()

    def _on_frame(self, event: tk.Event) -> None:
        """Re-break the lines when the width really changed.

        Both the break points and the height follow the width, so a frame that is
        laid out twice at two widths has to be re-broken; one that is not does
        not, because rewriting the text on every `<Configure>` would put the
        widget into a loop with its own geometry.
        """
        if event.widget is not self or abs(event.width - self._pixels) <= 1:
            return
        self._pixels = event.width
        self._apply()

    def _break_lines(self) -> list[str]:
        """The paragraph as lines that each fit `self._pixels`."""
        words = self._body.split()
        if not words:
            return []
        limit = self._pixels
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if self._font.measure(candidate) <= limit:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _apply(self) -> None:
        self._lines = self._break_lines()
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        if self._lines:
            self._text.insert("1.0", "\n".join(self._lines))
        self._text.configure(
            state="disabled", height=max(1, len(self._lines))
        )

    def _set_text(self, value: str) -> None:
        self._body = value
        self._apply()

    def _get_text(self) -> str:
        return self._body

    def show(self, wanted: bool) -> None:
        """Give the paragraph a place in the layout, or take it out of it.

        An empty paragraph is still a widget, and a widget that is packed is
        still a line tall: a hint reserved for a message that has not arrived is
        height the page cannot use. On the settings tab that is the difference
        between fitting and scrolling.
        """
        if wanted and not self._body:
            wanted = False
        if wanted == bool(self.winfo_manager()):
            return
        if wanted:
            self.pack(fill="x", anchor="w", pady=(theme.px(theme.SPACE_XS), 0))
        else:
            self.pack_forget()

    def set_colour(self, colour: str) -> None:
        """Recolour the prose, which is how a hint says ok or failed."""
        self._text.configure(fg=colour)

    def configure(self, cnf=None, **kw):
        """Swallow `fg` before the mix-in sees it.

        A paragraph is a frame around a text widget, but every caller here writes
        `configure(text=..., fg=...)` because that is what a label takes, and
        keeping one call shape for every widget is the point of the registry in
        `panel.py`. So `fg` is taken as the text widget's colour rather than
        passed on to a frame that has no such option.
        """
        if "fg" in kw:
            self.set_colour(kw.pop("fg"))
            if not kw and cnf is None:
                return None
        elif isinstance(cnf, dict) and "fg" in cnf:
            options = dict(cnf)
            self.set_colour(options.pop("fg"))
            if not options:
                cnf = None
                if not kw:
                    return None
        return super().configure(cnf, **kw)


# Tabs.


class TabLabel(_Textual, tk.Canvas):
    """One pill in the tab strip: quiet until hovered, a raised card when selected."""

    HEIGHT = 34
    PADDING = 14

    def __init__(self, master: tk.Misc, *, palette: theme.Palette, text: str = "",
                 command: Callable[[], None] | None = None) -> None:
        self._palette = palette
        self._label = text
        self._font = theme.ui(TYPE_BODY, "bold")
        self._command = command
        self._hover = False
        self._selected = False
        self._plate: ImageTk.PhotoImage | None = None
        super().__init__(
            master, height=theme.px(self.HEIGHT), width=self._natural_width(),
            bd=0, highlightthickness=0, bg=palette.bg, cursor="hand2",
        )
        self.bind("<Enter>", lambda _e: self._enter())
        self.bind("<Leave>", lambda _e: self._leave())
        self.bind("<Button-1>", lambda _e: self._click())
        self.bind("<Configure>", lambda _e: self._paint())
        self._paint()

    def _natural_width(self) -> int:
        pad = theme.px(self.PADDING) * 2
        return theme.measure(self._font, self._label) + pad

    def _set_text(self, value: str) -> None:
        self._label = value
        self.configure(width=self._natural_width())
        self._paint()

    def _get_text(self) -> str:
        return self._label

    def select(self) -> None:
        self._selected = True
        self._paint()

    def deselect(self) -> None:
        self._selected = False
        self._paint()

    def _enter(self) -> None:
        self._hover = True
        self._paint()

    def _leave(self) -> None:
        self._hover = False
        self._paint()

    def _click(self) -> None:
        if self._command is not None:
            self._command()

    def _paint(self) -> None:
        p = self._palette
        if self._selected:
            fill, foreground, shadow = p.surface, p.text, theme.card_shadow(p)
        elif self._hover:
            fill, foreground, shadow = p.surface_alt, p.text, None
        else:
            fill, foreground, shadow = p.bg, p.text_muted, None
        width = max(1, self.winfo_width()) or self._natural_width()
        height = max(1, self.winfo_height()) or theme.px(self.HEIGHT)
        try:
            self._plate = ImageTk.PhotoImage(
                theme.surface(
                    width, height, theme.px(theme.RADIUS_CONTROL), fill,
                    matte=self["bg"], shadow=shadow,
                ),
                master=self,
            )
        except tk.TclError:
            log.debug("tab plate is gone", exc_info=True)
            return
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=self._plate)
        self.create_text(
            width // 2, height // 2, text=self._label, font=self._font,
            fill=foreground, anchor="center",
        )


class Tabs(tk.Frame):
    """A tab strip over one content area, in place of `ttk.Notebook`.

    `ttk.Notebook` draws its own strip with the platform's own metrics and the
    platform's own colours, and that is the one part of the old panel that could
    not be restyled without shipping a theme file. This draws the strip itself.

    `add`, `tab` and `select` keep the names and the shapes `ttk` gave them, so
    `panel.py` reads like the code it replaces and `tools/make_images.py`, which
    reaches into `panel._notebook.select(1)`, keeps working. A page is created
    with `parent=tabs.content`, because `place` cannot re-parent a widget the way
    `ttk.Notebook.add` does.
    """

    def __init__(self, master: tk.Misc, *, palette: theme.Palette) -> None:
        self._palette = palette
        self._pages: list[tk.Frame] = []
        self._labels: list[TabLabel] = []
        self._keys: list[str] = []
        self._current = 0
        super().__init__(master, bg=palette.bg, bd=0, highlightthickness=0)
        strip = tk.Frame(self, bg=palette.bg, bd=0, highlightthickness=0)
        strip.pack(fill="x", padx=theme.px(theme.SPACE), pady=(theme.px(theme.SPACE), 0))
        self.content = tk.Frame(self, bg=palette.bg, bd=0, highlightthickness=0)
        self.content.pack(fill="both", expand=True)

    def add(self, frame: tk.Frame, text: str = "", key: str = "") -> None:
        """Register a page. `key` is the message key, for a language change."""
        index = len(self._pages)
        self._pages.append(frame)
        self._keys.append(key)
        label = TabLabel(
            self._strip(), palette=self._palette, text=text,
            command=lambda: self.select(index),
        )
        label.pack(side="left", padx=(0, theme.px(theme.SPACE_XS)))
        self._labels.append(label)
        if index == 0:
            self.select(0)

    def tab(self, frame: tk.Frame, text: str | None = None) -> dict[str, str]:
        """Read or write one page's label, the way `ttk.Notebook.tab` does."""
        index = self._pages.index(frame)
        if text is not None:
            self._labels[index].configure(text=text)
        return {"text": self._labels[index].cget("text")}

    def select(self, index: int | tk.Frame) -> None:
        """Bring one page forward, hiding the others."""
        if isinstance(index, tk.Frame):
            index = self._pages.index(index)
        self._current = max(0, min(index, len(self._pages) - 1))
        for position, page in enumerate(self._pages):
            if position == self._current:
                page.pack(fill="both", expand=True)
                self._labels[position].select()
            else:
                page.pack_forget()
                self._labels[position].deselect()

    @property
    def index(self) -> int:
        return self._current

    def _strip(self) -> tk.Misc:
        """The frame the pills live in: the first child, the one packed `fill=x`."""
        for child in self.winfo_children():
            if isinstance(child, tk.Frame) and child is not self.content:
                return child
        return self  # pragma: no cover - the strip is built in __init__

    def repaint_labels(self) -> None:
        """Nothing to do: `tab(frame, text=...)` is what a language change calls."""


# The transcript.


class Scrollbar(tk.Canvas):
    """A slim rounded thumb on a track that is only there when it is needed.

    `ttk` cannot do this. A ttk scrollbar's width comes from the element image
    its theme ships, and `style.configure(width=...)` is not an option it reads —
    on this build the thinnest it will agree to is one pixel, which is no scrollbar
    at all. It is also the only square, hard-edged thing a design like this would
    have left in.

    Everything here is drawn rather than themed, so it is the same shape as every
    other edge in the panel. The bar unpacks itself when the content fits, which
    is what keeps a thumb the length of its own track off a transcript that needs
    no scrolling.
    """

    WIDTH = 10
    THUMB = 6

    def __init__(self, master: tk.Misc, *, palette: theme.Palette,
                 command: Callable[[str, str], None] | None = None,
                 bg: str | None = None) -> None:
        self._palette = palette
        self._command = command
        self._first, self._last = "0.0", "1.0"
        self._drag_from: float | None = None
        self._drag_offset = 0.0
        self._wanted = False
        self._shown = False
        super().__init__(
            master, width=theme.px(self.WIDTH), bd=0, highlightthickness=0,
            bg=bg or palette.bg, cursor="hand2", takefocus=0,
        )
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Configure>", lambda _e: self._paint())

    def set(self, first: str, last: str) -> None:
        """Where the view is. Called by the widget being scrolled, not by us."""
        self._first, self._last = first, last
        self._wanted = not (first == "0.0" and last == "1.0")
        if self._wanted != self._shown:
            self._shown = self._wanted
            if self._wanted:
                self.pack(side="right", fill="y")
            else:
                self.pack_forget()
        self._paint()

    def _span(self) -> tuple[float, float] | None:
        """The thumb's top and bottom, or None when there is nothing to show."""
        if not self._wanted:
            return None
        track = max(1, self.winfo_height() - theme.px(self.THUMB))
        try:
            first, last = float(self._first), float(self._last)
        except ValueError:
            return None
        return track * first, track * first + max(
            theme.px(self.THUMB), track * (last - first)
        )

    def _paint(self) -> None:
        self.delete("all")
        span = self._span()
        if span is None or self.winfo_height() <= 1:
            return
        top, bottom = span
        self.create_oval(
            0, top, theme.px(self.THUMB) - 1, bottom,
            fill=self._palette.border_strong, outline="",
        )

    def _press(self, event: tk.Event) -> None:
        span = self._span()
        if span is None or self._command is None:
            return
        top, bottom = span
        self.focus_set()
        if not top <= event.y <= bottom:
            self._page(1 if event.y < top else -1)
            return
        self._drag_from = event.y
        self._drag_offset = event.y - top

    def _drag(self, event: tk.Event) -> None:
        span = self._span()
        if span is None or self._drag_from is None or self._command is None:
            return
        track = max(1, self.winfo_height() - theme.px(self.THUMB))
        self._command("moveto", max(0.0, min(1.0, (event.y - self._drag_offset) / track)))

    def _release(self, _event=None) -> None:
        self._drag_from = None

    def _page(self, direction: int) -> None:
        if self._command is None:
            return
        self._command("scroll", direction)


class CodeBox(tk.Frame):
    """The transcription surface: a padded `tk.Text` inside a card.

    No border of its own and no classic scrollbar — the card's shadow is the
    edge, and the bar is a thumb on the surface with no arrows, from the layout
    `theme.apply` builds. Both dimensions are asked for as one character and one
    line: a `Text` defaults to eighty columns, which is a request wide enough to
    squeeze the card that holds it, and this one is the widget that expands, so
    the card takes the space from the window instead.

    The bar unpacks itself while the text fits, which is what keeps a thumb the
    length of its own track off a transcript that needs no scrolling.
    """

    def __init__(self, master: tk.Misc, *, palette: theme.Palette,
                 placeholder: str = "", size: int = TYPE_MONO) -> None:
        self._palette = palette
        super().__init__(master, bg=palette.surface, bd=0, highlightthickness=0)
        pad = theme.px(theme.SPACE_MD)
        self._text = tk.Text(
            self, wrap="word", width=1, height=1, bd=0, highlightthickness=0,
            relief="flat", bg=palette.surface, fg=palette.text,
            font=theme.mono(size),
            insertbackground=palette.accent, selectbackground=palette.accent_soft,
            selectforeground=palette.text, padx=pad, pady=theme.px(theme.SPACE),
            spacing1=0, spacing3=0, cursor="arrow",
            highlightcolor=palette.accent, state="disabled", takefocus=0,
        )
        self._bar = Scrollbar(self, palette=palette, command=self._scroll_by)
        self._text.configure(yscrollcommand=self._bar.set)
        self._text.pack(side="left", fill="both", expand=True)
        self._placeholder = tk.Label(
            self, text=placeholder, font=theme.mono(size), bg=palette.surface,
            fg=palette.text_subtle, anchor="w", justify="left",
        )
        self._placeholder_body = placeholder

    @property
    def text_widget(self) -> tk.Text:
        return self._text

    def set_placeholder(self, value: str) -> None:
        self._placeholder_body = value
        if not self._text.get("1.0", "end-1c").strip():
            self._placeholder.configure(text=value)

    def render(self, body: str) -> None:
        """Replace the whole transcript. One call, so the state cannot drift."""
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        if body:
            self._text.insert("1.0", body)
            self._text.configure(state="disabled")
            self._text.see("end")
        else:
            self._text.configure(state="disabled")
        if body.strip():
            self._placeholder.place_forget()
        else:
            self._placeholder.configure(text=self._placeholder_body)
            self._placeholder.place(
                x=theme.px(theme.SPACE_MD), y=theme.px(theme.SPACE), anchor="nw"
            )

    def _scroll_by(self, what: str, amount: float = 0.0) -> None:
        """A click or a drag on the bar, turned into the widget's own scroll."""
        if what == "moveto":
            self._text.yview_moveto(amount)
        elif what == "scroll":
            self._text.yview_scroll(int(amount), "pages")


# Scrolling.


class Scroller(tk.Frame):
    """A vertical scroll region with the same arrowless bar, for the settings tab.

    A canvas rather than a listbox, because the content is real widgets — cards,
    switches, a field — and a listbox would hold none of them. The wheel is bound
    over the whole subtree after the content is built, because Tk delivers a
    wheel event to the widget under the pointer and a frame is not that widget
    once there are thirty children in it.

    `yview_scroll` moves by the canvas's own scroll increment, set to one design
    space unit, so a notch is the same distance in both themes and at any scale.
    """

    def __init__(self, master: tk.Misc, *, palette: theme.Palette) -> None:
        self._palette = palette
        super().__init__(master, bg=palette.bg, bd=0, highlightthickness=0)
        self.canvas = tk.Canvas(
            self, bg=palette.bg, bd=0, highlightthickness=0,
            yscrollincrement=theme.px(theme.SPACE),
        )
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar = Scrollbar(self, palette=palette, command=self._scroll_by)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.body = tk.Frame(self.canvas, bg=palette.bg, bd=0, highlightthickness=0)
        self._window = self.canvas.create_window(
            (0, 0), window=self.body, anchor="nw"
        )
        self.body.bind("<Configure>", self._on_body)
        self.canvas.bind("<Configure>", self._on_canvas)

    def _on_body(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def _scroll_by(self, what: str, amount: float = 0.0) -> None:
        if what == "moveto":
            self.canvas.yview_moveto(amount)
        elif what == "scroll":
            self.canvas.yview_scroll(int(amount), "pages")

    def bind_wheel(self) -> None:
        """Bind the wheel over the whole page, whatever is under the pointer.

        Two things this has to get right, and neither is obvious. Tk sends the
        event to the widget under the pointer and then, if nothing handled it, to
        that widget's class — and a `Text` widget's class handles it, scrolling
        itself. So every widget in the page gets a binding of its own, not only
        the ones with no scrolling of their own, or a wheel over any paragraph
        scrolls that one-line paragraph instead of the page.

        And the content is not in the canvas's child list at all: `body` is put
        there with `create_window`, and a widget embedded that way does not appear
        in `winfo_children()`. Walking the canvas finds nothing, which is exactly
        why the settings page could not be scrolled by wheel at all.
        """
        for widget in (self, self.canvas, self.body):
            widget.bind("<MouseWheel>", self._on_wheel)
        self._bind_below(self.body)

    def _bind_below(self, widget: tk.Misc) -> None:
        for child in widget.winfo_children():
            child.bind("<MouseWheel>", self._on_wheel)
            self._bind_below(child)

    def _on_wheel(self, event: tk.Event) -> str:
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"


# Small text helpers, so a label's font and colour are never written twice.


def heading(
    master: tk.Misc, *, palette: theme.Palette, size: int = TYPE_HEADING,
    bg: str | None = None,
) -> tk.Label:
    return tk.Label(
        master, text="", font=theme.ui(size, "bold"), bg=bg or palette.surface,
        fg=palette.text, anchor="w", justify="left",
    )


def body(
    master: tk.Misc, *, palette: theme.Palette, size: int = TYPE_BODY,
    muted: bool = False, bg: str | None = None,
) -> tk.Label:
    return tk.Label(
        master, text="", font=theme.ui(size), bg=bg or palette.surface,
        fg=palette.text_muted if muted else palette.text, anchor="w", justify="left",
    )


def caption(
    master: tk.Misc, *, palette: theme.Palette, size: int = TYPE_CAPTION,
    bg: str | None = None,
) -> tk.Label:
    return tk.Label(
        master, text="", font=theme.ui(size), bg=bg or palette.surface,
        fg=palette.text_subtle, anchor="w", justify="left",
    )


def rule(master: tk.Misc, *, palette: theme.Palette, bg: str | None = None) -> tk.Frame:
    """A hairline. The one hard edge left in the design, and it earns it."""
    return tk.Frame(
        master, height=max(1, int(theme.px(1))), bg=bg or palette.border,
        bd=0, highlightthickness=0,
    )
