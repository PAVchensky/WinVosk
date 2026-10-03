"""Always-on-top panel showing the live transcription.

The window is built unmapped and stays in the tray until the tray icon is
clicked, so the app never takes the focus at start up. Everything below works
the same either way: `show` and `hide` are the only two places that map or unmap
it, and the recording chip is a `Toplevel` of this root, which maps on its own
while the root stays withdrawn.

The look comes from `theme` and `widgets`: a light grey page, white cards with a
soft shadow instead of a border, an indigo accent, one spacing scale and one type
scale. Nothing here writes a colour, a radius or a font of its own — `theme`
owns all three — and nothing here writes a user visible string either: every
label is a key from `winvosk.text`, and every widget that shows one is registered
in `self._messages`. That is what makes `set_language` possible without rebuilding
the window: the widgets stay, the state stays, and only the text is re-painted.

Widgets whose text carries a value — the footer, the window title, the record
button — are refreshed by the setter that owns the value, so the registry holds
only the static ones.

A change of theme is the one thing that does rebuild: `set_theme` throws the page
tree away and builds it again in the new colours, rather than asking twenty
widgets to repaint themselves in a palette they were not built for. The root, the
tray-only start up, the variables and the chip all survive it, and the state is
put back from the attributes this object already holds.
"""

from __future__ import annotations

import logging
import queue
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox

from PIL import ImageTk

from . import config, overlay, text, theme, tray, vocabulary, widgets

log = logging.getLogger(__name__)

# The window size, in design pixels. 720 rather than 600 because the settings tab
# is two columns and a 300 px column is below the point where a hint reads as a
# sentence; the dictation tab uses the extra width for the transcript, which is
# the one thing in it that wants room. 700 tall is what keeps the bottom of the
# settings tab in reach on a normal screen: the two columns come to a little over
# 700 px of content, so what is left over scrolls by about a card, and
# `check_settings_reachable` is what proves the rest of it can be got to. The
# minimum size is the same, so the columns can never be squeezed into a shape
# they were not drawn for.
WIDTH = 720
HEIGHT = 700
MARGIN = 24
POLL_MS = 60

_CAPTURE_PROMPT = "capture_prompt"


class Panel:
    def __init__(
        self,
        commands: queue.Queue,
        next_level: Callable[[], float | None],
        *,
        live_typing: bool = True,
        clipboard: bool = False,
        autostart: bool = False,
        correct_words: bool = True,
        toggle: bool = False,
        language: str = text.DEFAULT_LANGUAGE,
        theme_name: str = theme.DEFAULT_THEME,
    ) -> None:
        # Must happen before there is a window: afterwards Windows refuses, and
        # the panel comes up with every corner resampled a second time.
        theme.enable_dpi_awareness()
        self._commands = commands
        self._text = ""
        self._partial = ""
        # The app lives in the tray: the window is built, and stays unmapped,
        # until the tray is clicked. See the withdraw below.
        self._visible = False
        # One closure per widget that shows a message, so a language change can
        # re-paint them all without rebuilding the window.
        self._messages: list[Callable[[], None]] = []
        self._word_count = 0
        self._capturing = False
        self._hotkey_text = config.hotkey_label()
        self._recording = False
        # Recorded rather than re-read: the button and the footer have to agree
        # with each other between two clicks, and the app re-reads the disk for
        # every decision it actually acts on.
        self._toggle = bool(toggle)
        # The status line is a key rather than a string, so it survives a change
        # of language; a raw message set from the app is shown as it came.
        self._status_key = "status_loading"
        self._status_raw = ""
        self._status_role = "muted"
        self._device = ""
        self._settings_page: widgets.Scroller | None = None
        self._window_icon: list[ImageTk.PhotoImage] = []
        self._icon_theme = ""
        self._theme_name = theme_name if theme_name in theme.THEMES else theme.DEFAULT_THEME
        self._colours = theme.palette(self._theme_name)

        self._root = tk.Tk()
        # Withdrawn before a single widget is built, so the window is never
        # mapped: no flash on the way to the tray, and no chance of taking the
        # focus away from whatever the user was typing in. `tk.Tk()` maps by
        # itself, which is why the tray is the only thing that shows this.
        # The same trick is in `overlay.RecordingOverlay._build`.
        self._root.withdraw()
        # Both of these need the interpreter and neither needs the window, so
        # they go first: a font resolved after the first widget is built is a
        # widget drawn in the fallback face.
        theme.bind(self._root)
        theme.apply(self._root, self._colours)
        self._live_typing = tk.BooleanVar(value=bool(live_typing))
        self._clipboard = tk.BooleanVar(value=bool(clipboard))
        self._autostart = tk.BooleanVar(value=bool(autostart))
        self._correct_words = tk.BooleanVar(value=bool(correct_words))
        self._toggle_var = tk.BooleanVar(value=bool(toggle))
        self._dark_var = tk.BooleanVar(value=theme.is_dark(self._theme_name))
        self._language = tk.StringVar(value=language)
        # The chip's equalizer is fed by the engine, not by the panel: the
        # levels live in the audio thread and are read here, on the Tk thread.
        self._overlay = overlay.RecordingOverlay(self._root, next_level)
        self._root.title(self._title())
        self._root.attributes("-topmost", True)
        self._root.protocol("WM_DELETE_WINDOW", self.hide)
        self._root.bind("<Map>", self._on_map)
        self._place()
        self._dress_window()

        # Everything lives under one frame, so a change of theme can throw that
        # frame away and build another without touching the root.
        self._shell = tk.Frame(
            self._root, bg=self._colours.bg, bd=0, highlightthickness=0
        )
        self._shell.pack(fill="both", expand=True)
        self._build()

    # Construction.

    def _build(self) -> None:
        colours = self._colours
        self._notebook = widgets.Tabs(self._shell, palette=colours)
        self._notebook.pack(fill="both", expand=True)

        dictation = tk.Frame(self._notebook.content, bg=colours.bg, bd=0,
                             highlightthickness=0)
        self._notebook.add(dictation, text=text.t("tab_dictation"), key="tab_dictation")
        self._build_dictation(dictation)

        settings = widgets.Scroller(self._notebook.content, palette=colours)
        self._notebook.add(settings, text=text.t("tab_settings"), key="tab_settings")
        self._settings_page = settings
        self._build_settings(settings)
        settings.bind_wheel()

    def _build_dictation(self, parent: tk.Frame) -> None:
        colours = self._colours
        pad = theme.px(theme.SPACE_XL)

        header = tk.Frame(parent, bg=colours.bg, bd=0, highlightthickness=0)
        header.pack(fill="x", padx=pad, pady=(theme.px(theme.SPACE_MD), 0))
        # Right to left: the model name takes what it needs from the far edge,
        # then the dot, then the status takes the rest of the row. Packed the
        # other way round the status would be laid out while still empty and ask
        # for nothing, and a label never re-asks once it has been given text.
        self._model = tk.Label(
            header, text=config.MODEL_NAME, bg=colours.bg, fg=colours.text_subtle,
            font=theme.mono(widgets.TYPE_TINY), anchor="e",
        )
        self._model.pack(side="right")
        self._dot = widgets.Dot(
            header, palette=colours, colour=colours.text_subtle, bg=colours.bg
        )
        self._dot.pack(side="left", padx=(0, theme.px(theme.SPACE_SM)))
        self._status = widgets.body(
            header, palette=colours, size=widgets.TYPE_BODY, bg=colours.bg
        )
        self._status.pack(side="left", fill="x", expand=True)

        card = widgets.Card(parent, palette=colours)
        card.pack(
            fill="both", expand=True,
            padx=pad, pady=theme.px(theme.SPACE_MD),
        )
        self._box = widgets.CodeBox(
            card.inner, palette=colours, placeholder=text.t("transcript_placeholder")
        )
        self._box.pack(fill="both", expand=True)
        self._messages.append(
            lambda: self._box.set_placeholder(text.t("transcript_placeholder"))
        )

        controls = tk.Frame(parent, bg=colours.bg, bd=0, highlightthickness=0)
        controls.pack(fill="x", padx=pad, pady=(0, theme.px(theme.SPACE_MD)))
        # The record button is the one the panel exists for, so it is the only
        # primary in the row and it goes first: everything else is a quiet
        # consequence of what it does.
        self._record_button = widgets.Button(
            controls, text=text.t("record_hold"), palette=colours,
            variant="primary", size="lg", on_press=self._press,
            on_release=self._release, bg=colours.bg,
        )
        self._record_button.pack(side="left")
        self._stop_button = widgets.Button(
            controls, text=text.t("button_stop"), palette=colours,
            variant="secondary", size="lg", command=self._stop, bg=colours.bg,
        )
        self._stop_button.pack(side="left", padx=(theme.px(theme.SPACE_SM), 0))
        self._stop_button.set_enabled(False)
        self._track(self._stop_button, "button_stop")
        copy_button = widgets.Button(
            controls, text=text.t("button_copy"), palette=colours,
            variant="ghost", size="lg", command=self._copy, bg=colours.bg,
        )
        copy_button.pack(side="left", padx=(theme.px(theme.SPACE_SM), 0))
        self._track(copy_button, "button_copy")
        clear_button = widgets.Button(
            controls, text=text.t("button_clear"), palette=colours,
            variant="ghost", size="lg", command=self._clear, bg=colours.bg,
        )
        clear_button.pack(side="left", padx=(theme.px(theme.SPACE_XS), 0))
        self._track(clear_button, "button_clear")

        self._footer = widgets.caption(
            parent, palette=colours, size=widgets.TYPE_CAPTION, bg=colours.bg
        )
        self._footer.configure(
            text=self._footer_text(self._hotkey_text),
            pady=theme.px(theme.SPACE_MD),
        )
        self._footer.pack(fill="x", padx=pad)
        # The footer carries the combination, so it is repainted from the label
        # in effect rather than from a key.
        self._messages.append(
            lambda: self._footer.configure(text=self._footer_text(self._hotkey_text))
        )

    def _build_settings(self, parent: widgets.Scroller) -> None:
        """Two columns, and one card across the top of both.

        The key gets the full width because its field has to hold a combination
        in monospace next to a Reset button, and neither of those is something to
        squeeze for the sake of a column. Everything below it is a switch and a
        sentence about it, which is exactly what a 320 px column is for, and the
        tab then fits without scrolling at all on a display of any ordinary size.

        The two columns are packed rather than gridded: a grid would tie the two
        sides to one row height and leave a short column with a gap under it, and
        pack lets each side be as tall as its own content.
        """
        colours = self._colours
        body = parent.body
        pad = theme.px(theme.SPACE_XL)
        gap = theme.px(theme.SPACE_LG)
        wrap = self._wrap()
        column = self._column_width()

        intro = widgets.Paragraph(
            body, palette=colours, text=text.t("settings_intro"),
            size=widgets.TYPE_BODY,
            colour=colours.text_muted, bg=colours.bg, width=wrap,
        )
        intro.pack(fill="x", padx=pad, pady=(theme.px(theme.SPACE), 0))
        self._track(intro, "settings_intro")

        # The key, the mode that key works in, and what that mode does: three
        # properties of one thing, so one card.
        # The mode the key works in sits beside the card's title. It belongs to the
        # key — it is a property of how the combination acts, not of where the text
        # goes — and this card is the one thing on the page wide enough to hold
        # both without either of them wrapping into three lines. In a column of
        # its own it cost a hundred and thirty pixels and said the same thing in
        # three.
        def toggle_beside(head: tk.Misc) -> widgets.Choice:
            self._toggle_check = widgets.Choice(
                head, palette=colours, text=text.t("option_toggle"),
                variable=self._toggle_var, command=self._pick_toggle,
                wraplength=wrap,
            )
            return self._toggle_check

        hotkey = self._card(
            body, "hotkey_label", first=True, aside=toggle_beside
        )
        self._track(self._toggle_check, "option_toggle")
        row = tk.Frame(hotkey.inner, bg=colours.surface, bd=0, highlightthickness=0)
        row.pack(fill="x")
        # A field, not an entry: nothing is typed here, the hook captures.
        self._hotkey_field = widgets.Field(
            row, palette=colours, text=self._hotkey_text, command=self._capture_hotkey
        )
        self._hotkey_field.pack(side="left", fill="x", expand=True)
        reset_button = widgets.Button(
            row, text=text.t("button_reset"), palette=colours,
            variant="secondary", command=self._reset_hotkey,
        )
        reset_button.pack(side="left", padx=(theme.px(theme.SPACE_SM), 0))
        self._track(reset_button, "button_reset")
        self._hotkey_hint = self._hint(hotkey.inner, "hint_idle", wrap)
        self._toggle_hint = self._hint(hotkey.inner, "toggle_hint", wrap)

        columns = tk.Frame(body, bg=colours.bg, bd=0, highlightthickness=0)
        columns.pack(fill="x", padx=pad, pady=(theme.px(theme.SPACE), 0))
        left = self._column(columns, padx=(0, gap))
        right = self._column(columns)
        self._right_column = right

        # What the words do when they are recognised, then when the app starts.
        insertion = self._card(left, "group_insertion", first=True)
        self._check(insertion.inner, "option_typing", self._live_typing,
                    "set_live_typing", column)
        self._check(insertion.inner, "option_clipboard", self._clipboard,
                    "set_clipboard", column)
        self._correct_check = self._check(
            insertion.inner, "option_corrections", self._correct_words,
            "set_correct_words", column, top_pad=theme.SPACE_SM,
        )
        self._word_hint = self._hint(insertion.inner, "", column)
        # The check belongs to the switch above it, so it sits right under the
        # hint rather than in a group of its own with nothing else in it.
        self._check_words_button = widgets.Button(
            insertion.inner, text=text.t("button_check_words"), palette=colours,
            variant="secondary", command=self._check_words,
        )
        self._check_words_button.pack(anchor="w", pady=(theme.px(theme.SPACE), 0))
        self._track(self._check_words_button, "button_check_words")

        startup = self._card(left, "group_startup")
        self._check(startup.inner, "option_autostart", self._autostart,
                    "set_autostart", column)
        self._autostart_hint = self._hint(startup.inner, "autostart_hint", column)

        # The two cards that are about this panel rather than about dictation.
        # A switch rather than two radios for the theme: there are two of them and
        # one is what you are looking at now.
        appearance = self._card(right, "group_appearance", first=True)
        theme_row = tk.Frame(
            appearance.inner, bg=colours.surface, bd=0, highlightthickness=0
        )
        theme_row.pack(fill="x")
        self._dark_switch = widgets.Switch(
            theme_row, palette=colours, variable=self._dark_var,
            command=self._pick_theme,
        )
        self._dark_switch.pack(side="left", anchor="n")
        self._dark_label = widgets.body(theme_row, palette=colours)
        self._dark_label.configure(text=text.t("option_theme"))
        self._dark_label.pack(side="left", padx=(theme.px(theme.SPACE), 0))
        self._track(self._dark_label, "option_theme")
        self._theme_hint = self._hint(appearance.inner, "theme_hint", column)

        language = self._card(right, "group_language")
        languages = tk.Frame(
            language.inner, bg=colours.surface, bd=0, highlightthickness=0
        )
        languages.pack(fill="x")
        # Endonyms, so each option reads correctly whichever language is active.
        for code in text.LANGUAGES:
            radio = widgets.Choice(
                languages, palette=colours, kind="radio", text=text.name_of(code),
                variable=self._language, command=self._pick_language, value=code,
            )
            radio.pack(side="left", padx=(0, theme.px(theme.SPACE_LG)))

        # Nothing here until a setting has something to say, and an empty
        # paragraph that reserves a line and two gaps is twenty pixels of the page
        # spent on silence.
        self._options_hint = self._hint(body, "", wrap, bg=colours.bg)
        self._options_hint.pack_configure(padx=pad, pady=0)

    # Small builders, so the settings tab above reads as a list of what is in it.

    def _column(self, parent: tk.Misc, *, padx: int = 0) -> tk.Frame:
        """One half of the settings tab, half as wide as the other by `expand`."""
        column = tk.Frame(
            parent, bg=self._colours.bg, bd=0, highlightthickness=0
        )
        column.pack(
            side="left", fill="both", expand=True, padx=padx,
        )
        return column

    def _card(self, parent: tk.Misc, key: str, padx: int = 0,
              first: bool = False,
              aside: Callable[[tk.Misc], tk.Misc] | None = None) -> widgets.Card:
        """A card with its own title, which a language change repaints in place.

        `first` is the top card of a column, which is already spaced from
        whatever is above the column by the row's own padding: giving it the gap
        as well is twenty pixels of nothing, twice over, and the settings tab has
        six cards.
        """
        card = widgets.Card(
            parent, palette=self._colours, padding=theme.SPACE
        )
        card.pack(
            fill="x", padx=padx,
            pady=(0 if first else theme.px(theme.SPACE), 0),
        )
        # `aside` is a factory rather than a widget because a control can only be
        # given the title row as its real parent once that row exists, and tkinter
        # cannot move a widget into it afterwards. Assigning `widget.master` changes
        # the Python attribute and leaves the widget where it was; `pack(in_=...)`
        # on a widget that nothing manages yet is silently a no-op. Both look like
        # they worked until the next relayout.
        if aside is None:
            title = widgets.heading(card.inner, palette=self._colours)
            title.configure(text=text.t(key))
            title.pack(fill="x", pady=(0, theme.px(theme.SPACE_SM)))
        else:
            head = tk.Frame(card.inner, bg=self._colours.surface, bd=0,
                            highlightthickness=0)
            head.pack(fill="x", pady=(0, theme.px(theme.SPACE_SM)))
            title = widgets.heading(head, palette=self._colours)
            title.configure(text=text.t(key))
            title.pack(side="left")
            aside(head).pack(
                side="right", anchor="n", padx=(theme.px(theme.SPACE_MD), 0)
            )
        self._track(title, key)
        return card

    def check_settings_reachable(self) -> str:
        """Prove that the bottom of the settings tab can be reached, and report how.

        Walks the tab to its end and asks whether the last line of it is inside
        the window. Returns the content height, the viewport and whether it all
        fits; raises `AssertionError` when the bottom of the tab is still off
        screen after scrolling, which is the failure this whole arrangement
        exists to make impossible.

        Called by `run.py --check-bundle`, on the panel being built unmapped in
        the tray: a settings tab that cannot be got to is invisible to every
        console flag and to every probe, and only a real window shows it.
        """
        page = self._settings_page
        if page is None:
            raise AssertionError(
                "the settings tab was never built, so there is nothing to reach"
            )
        canvas = page.canvas
        self._root.update_idletasks()
        region = canvas.bbox("all")
        content = region[3] if region else 0
        viewport = canvas.winfo_height()
        canvas.yview_moveto(1.0)
        self._root.update_idletasks()
        bottom = self._options_hint.winfo_rooty() + self._options_hint.winfo_height()
        edge = canvas.winfo_rooty() + canvas.winfo_height()
        if bottom > edge + 1:
            raise AssertionError(
                f"the bottom of the settings tab is unreachable: the last line "
                f"ends at {bottom} and the page shows up to {edge}"
            )
        return (f"{content}px of settings in a {viewport}px page, "
                f"{'fits' if content <= viewport else 'scrolls'}")

    def _hint(self, parent: tk.Misc, key: str, wrap: int, *, bg: str | None = None):
        """A paragraph under a control: why it is there, or what just happened.

        An empty one is built but not packed, and `set_option_hint` packs it when
        there is finally something to say. A widget that is packed is a line tall
        whether or not it has anything in it.
        """
        hint = widgets.Paragraph(
            parent, palette=self._colours, text=text.t(key) if key else "",
            colour=self._colours.text_subtle, bg=bg, width=wrap,
        )
        hint.show(bool(key))
        if key:
            self._track(hint, key)
        return hint

    def _check(
        self, parent: tk.Misc, key: str, variable: tk.BooleanVar, command: str,
        wrap: int, top_pad: int = 0,
    ) -> widgets.Choice:
        check = widgets.Choice(
            parent, palette=self._colours, text=text.t(key), variable=variable,
            command=lambda: self._toggle(command, variable), wraplength=wrap,
        )
        check.pack(fill="x", pady=(theme.px(top_pad), 0))
        self._track(check, key)
        return check

    def _page_pad(self) -> int:
        """The settings page's own horizontal padding, for a widget added late."""
        return theme.px(theme.SPACE_XL)

    def _wrap(self) -> int:
        """The width a paragraph gets across the whole window, less its own air."""
        inset = theme.px(theme.SPACE_XL) + theme.px(theme.SPACE_MD)
        inset += theme.px(theme.SHADOW_BLUR) + theme.px(theme.SPACE_SM)
        return max(160, WIDTH - inset * 2)

    def _column_width(self) -> int:
        """The width a paragraph gets inside one column of the settings tab.

        Half the window, less the page's own padding, less the gap between the
        columns and less what a card takes off its own content for its padding
        and its shadow. Kept as an arithmetic expression of the same tokens the
        layout is built from, so a change to the window width or to the spacing
        scale moves both at once rather than leaving a number behind.
        """
        gap = theme.px(theme.SPACE_LG)
        inset = theme.px(theme.SPACE_XL) + theme.px(theme.SPACE_MD)
        inset += theme.px(theme.SHADOW_BLUR) + theme.px(theme.SPACE_SM)
        return max(160, (WIDTH - gap) // 2 - inset)

    # Language, theme and state.

    def _track(self, widget: tk.Misc, key: str) -> None:
        """Remember that this widget shows a message, so it can be re-painted."""
        self._messages.append(lambda w=widget, k=key: w.configure(text=text.t(k)))

    def _paint_messages(self) -> None:
        for repaint in self._messages:
            try:
                repaint()
            except tk.TclError:
                log.debug("could not repaint a message", exc_info=True)

    def set_language(self, code: str) -> None:
        """Repaint everything the language switch owns, keeping all state.

        The window is not rebuilt: the caret in the transcript, the recording
        state of the buttons and the chip would all have to be restored by hand,
        and a half restored panel is worse than a stale label.
        """
        if not text.set_language(code):
            self._language.set(text.language())
            return
        self._language.set(code)
        self._paint_messages()
        self._paint_record_button()
        if self._capturing:
            self.show_capture()
        else:
            self.set_hotkey(self._hotkey_text)
        self._hotkey_hint.configure(text=text.t("hint_idle"), fg=self._colours.text_subtle)
        self.set_word_count(self._word_count)
        self._toggle_hint.configure(text=text.t("toggle_hint"))
        self._refresh_status()
        self._root.title(self._title())

    @property
    def visible(self) -> bool:
        return self._visible

    @property
    def text(self) -> str:
        return self._text

    @property
    def theme_name(self) -> str:
        return self._theme_name

    def set_theme(self, name: str) -> None:
        """Rebuild the page tree in `name`, keeping every value that is in effect.

        The one operation here that throws widgets away. Repainting twenty
        widgets into a palette they were not built for would mean a repaint path
        per widget per role; a rebuild is one path, and the state it has to put
        back is already held here as fields. The root, the chip, the variables and
        the tray-only start up are untouched, so the panel does not flash on
        screen and the microphone is not interrupted.
        """
        if name not in theme.THEMES:
            self._dark_var.set(theme.is_dark(self._theme_name))
            return
        if name == self._theme_name:
            self._dark_var.set(theme.is_dark(name))
            return
        self._theme_name = name
        self._colours = theme.palette(name)
        theme.apply(self._root, self._colours)
        theme.reset()
        self._root.configure(bg=self._colours.bg)
        self._shell.destroy()
        self._shell = tk.Frame(
            self._root, bg=self._colours.bg, bd=0, highlightthickness=0
        )
        self._shell.pack(fill="both", expand=True)
        self._build()
        self._restore()
        self._root.title(self._title())
        self._dress_window()

    def _restore(self) -> None:
        """Put back everything a rebuild threw away, from the fields above."""
        self._notebook.select(0)
        self._dark_var.set(theme.is_dark(self._theme_name))
        self._toggle_check.set(self._toggle)
        self._autostart.set(bool(self._autostart.get()))
        self.set_word_count(self._word_count)
        self.set_recording(self._recording)
        self._refresh_status()
        self._render()
        if self._capturing:
            self.show_capture()
        else:
            self.set_hotkey(self._hotkey_text)

    def _pick_theme(self) -> None:
        """Hand the theme to the app, which owns the disk."""
        self._commands.put(
            ("set_theme", theme.DARK.name if self._dark_var.get() else theme.LIGHT.name)
        )

    def _pick_toggle(self) -> None:
        """Hand the mode to the app, which owns the disk and the listener."""
        self._commands.put(("set_toggle", bool(self._toggle_var.get())))

    def set_toggle(self, value: bool) -> None:
        """Put the switch and every label it drives back to what is in effect.

        The record button, the footer and the hint are repainted here rather
        than by the caller, because a mode the app refused to save must not be
        left showing on any of them. The hint always describes what turning the
        checkbox on does, so it does not change its text — only its colour says
        whether it is on.
        """
        self._toggle = bool(value)
        self._toggle_var.set(self._toggle)
        self._toggle_check.set(self._toggle)
        self._paint_record_button()
        self._footer.configure(text=self._footer_text(self._hotkey_text))
        self._toggle_hint.configure(
            fg=self._colours.success if self._toggle else self._colours.text_subtle
        )

    def _toggle(self, command: str, variable: tk.BooleanVar) -> None:
        """Hand a changed switch to the app, which owns the disk and the registry."""
        self._commands.put((command, bool(variable.get())))

    def _footer_text(self, label: str) -> str:
        key = "footer_toggle" if self._toggle else "footer"
        return text.t(key, label=label)

    # Placement.

    def _place(self) -> None:
        """Put the panel in the bottom right corner of the work area.

        The size is asked for in physical pixels, multiplied by the display
        scale: a DPI aware process is given real pixels, so asking for 600 on a
        150% display lands a 900 px window and pushes it off the corner. `wm
        geometry` takes no float either, which is the other half of the same
        mistake.
        """
        ratio = theme.scale()
        width, height = int(round(WIDTH * ratio)), int(round(HEIGHT * ratio))
        screen_w = self._root.winfo_screenwidth()
        screen_h = self._root.winfo_screenheight()
        x = max(0, screen_w - width - int(MARGIN * ratio))
        y = max(0, screen_h - height - int(MARGIN * ratio))
        self._root.geometry(f"{width}x{height}+{x}+{y}")
        self._root.minsize(theme.px(WIDTH), theme.px(HEIGHT))

    def _dress_window(self) -> bool:
        """Everything about the window frame itself, in one place.

        The rounded corners and the dark title bar come from DWM and only exist
        on Windows 11; the icon is drawn by `tray.make_icon`, so the panel and
        the notification area are the same picture rather than the panel wearing
        Tk's feather while the tray wears the microphone.
        """
        self._put_window_icon()
        return theme.dress_window(self._root, self._colours)

    def _on_map(self, event=None) -> None:
        """Put the window attributes back, every time the window comes up.

        Mapping a window resets them. That is the same reason the chip rewrites
        `WS_EX_NOACTIVATE` on every `<Map>`, and it is not a theory: measured here,
        a corner preference written before the first map reads back as "not
        rounded" afterwards, and one written after the map sticks. So this is done
        both before and after, because `<Map>` arrives on a later loop iteration
        than the `deiconify` that caused it and neither call alone is enough.
        """
        if event is not None and event.widget is not self._root:
            return
        self._dress_window()

    def _put_window_icon(self) -> None:
        """The window icon, in the sizes Windows asks a title bar for.

        Tk's own default is the Tcl/Tk feather, which is the one thing about an
        otherwise finished window that still says "sample application". The tray
        already draws a microphone in code, so the panel borrows that rather than
        shipping a second asset — and it follows the theme with it.

        Drawn once per theme, not once per map: five Pillow renders at four times
        the size is real work for an icon that only changes when the colours do.
        The `PhotoImage`s are held on the panel because Tk keeps no reference of
        its own, and a collected one leaves the title bar with no icon and nothing
        in the log to say why.
        """
        if self._icon_theme == self._theme_name and self._window_icon:
            return
        sizes = (16, 24, 32, 48, 64)
        try:
            images = [
                ImageTk.PhotoImage(tray.make_icon(False, size, self._colours))
                for size in sizes
            ]
        except tk.TclError:
            log.debug("could not draw the window icon", exc_info=True)
            return
        self._window_icon = images
        self._icon_theme = self._theme_name
        try:
            self._root.iconphoto(True, *images)
        except tk.TclError:
            log.debug("the window took no icon", exc_info=True)

    # Commands from the panel.

    def _press(self, _event=None) -> None:
        # In toggle mode one press is the whole gesture, so the release has
        # nothing left to do and `_release` stays quiet.
        self._commands.put("hotkey_press" if self._toggle else "press")

    def _release(self, _event=None) -> None:
        if not self._toggle:
            self._commands.put("release")

    def _stop(self) -> None:
        self._commands.put("stop_recording")

    def _copy(self) -> None:
        self._commands.put("copy")

    def _clear(self) -> None:
        self._commands.put("clear")

    def _capture_hotkey(self, _event=None) -> None:
        self._commands.put("capture_hotkey")

    def _reset_hotkey(self) -> None:
        self._commands.put("reset_hotkey")

    def _check_words(self) -> None:
        """Ask the app to run the own-word check. It owns the model and the reply."""
        self._commands.put("check_words")

    def _pick_language(self) -> None:
        self._commands.put(("set_language", self._language.get()))

    # Values the app writes back.

    def set_hotkey(self, label: str) -> str:
        """Publish the combination in effect in the field and in the footer."""
        self._capturing = False
        self._hotkey_text = label
        self._hotkey_field.configure(text=label)
        self._hotkey_field.set_active(False)
        self._footer.configure(text=self._footer_text(label))
        self._hotkey_hint.configure(
            text=text.t("hint_idle"), fg=self._colours.text_subtle
        )
        return label

    def show_capture(self) -> None:
        """The field is waiting for a combination now."""
        self._capturing = True
        self._hotkey_field.configure(text=text.t(_CAPTURE_PROMPT))
        self._hotkey_field.set_active(True)
        self._hotkey_hint.configure(
            text=text.t("hint_escape"), fg=self._colours.text_subtle
        )

    def set_hotkey_hint(self, message: str, error: bool = False) -> None:
        self._hotkey_hint.configure(
            text=message, fg=self._colours.danger if error else self._colours.success
        )

    def set_live_typing(self, value: bool) -> None:
        """Show the switch as the disk and the app actually hold it."""
        self._live_typing.set(bool(value))

    def set_clipboard(self, value: bool) -> None:
        self._clipboard.set(bool(value))

    def set_correct_words(self, value: bool) -> None:
        self._correct_words.set(bool(value))

    def set_autostart(self, value: bool) -> None:
        self._autostart.set(bool(value))

    def set_word_count(self, count: int) -> None:
        """Say how many words the correction pass has to work with."""
        self._word_count = count
        self._correct_check.configure(
            text=text.t("option_corrections" if count else "option_corrections_empty")
        )
        self._word_hint.configure(
            text="" if count else text.t("words_empty_hint")
        )

    def set_checking_words(self, running: bool) -> None:
        """The check owns the model for a couple of seconds, so it is held down."""
        self._check_words_button.set_enabled(not running)
        if running:
            self.set_option_hint(text.t("words_check_hint"))

    def show_words_report(self, known: list[str], missing: list[str],
                          total: int) -> None:
        """The detail behind the one line on the hint, in a window of its own.

        An unowned dialog while the panel is in the tray: a modal window whose
        parent is withdrawn comes up behind whatever else is in front, or not at
        all, and the check is most often run from the tray in the first place.
        """
        self.set_checking_words(False)
        self.set_option_hint(
            text.t("words_check_done", known=len(known), total=total)
        )
        report = "\n".join(
            vocabulary.report_lines(config.PHRASES_FILE, known, missing)
        )
        messagebox.showinfo(
            f"{config.APP_NAME} {config.VERSION} — "
            f"{text.t('report_words_title')}",
            report,
            parent=self._root if self._visible else None,
        )

    def set_option_hint(self, message: str, error: bool = False) -> None:
        self._options_hint.configure(
            text=message, fg=self._colours.danger if error else self._colours.success
        )
        self._options_hint.show(True)
        self._options_hint.pack_configure(padx=self._page_pad())

    # The transcript.

    def set_text(self, text: str, partial: str) -> None:
        self._text = text
        self._partial = partial
        self._render()

    def clear(self) -> None:
        self._text = ""
        self._partial = ""
        self._render()

    def append_note(self, note: str) -> None:
        self._render(extra=note)

    def _render(self, extra: str = "") -> None:
        parts = [self._text]
        if self._partial:
            parts.append(self._partial)
        if extra:
            parts.append(f"\n[{extra}]")
        body = " ".join(part.strip() for part in parts if part and part.strip())
        self._box.render(body)

    # Window state.

    def show(self) -> None:
        self._visible = True
        self._root.deiconify()
        self._root.attributes("-topmost", True)
        self._dress_window()

    def hide(self) -> None:
        self._visible = False
        self._root.withdraw()

    def present(self) -> None:
        """Show the panel and bring it to the front, focus included.

        Used by the tray, where the click is a deliberate act. The hotkey must
        not do this: taking the focus away from the window the user dictated
        into would send the words to the panel instead.
        """
        self.show()
        self._root.lift()
        self._root.focus_force()

    def set_ready(self, model: str, device) -> None:
        self._model.configure(text=f"{model}")
        self._device = str(device)
        self._set_status_key("status_ready", "success")
        self._root.title(self._title())

    def set_recording(self, recording: bool) -> None:
        self._recording = recording
        if recording:
            self._set_status_key("status_recording", "danger")
            self._stop_button.set_enabled(True)
            self._overlay.show()
        else:
            self._set_status_key("status_ready", "success")
            self._stop_button.set_enabled(False)
            self._overlay.hide()
        self._paint_record_button()

    def _paint_record_button(self) -> None:
        """The hold button is the one label that depends on the state as well.

        Repainted on its own so a change of language reaches it: it is neither a
        plain message nor owned by one call, since `set_recording` writes it in
        both directions. While a recording runs it is not disabled but busy: a
        greyed button says "unavailable", and this one is saying "live".
        """
        self._record_button.set_busy(self._recording)
        if self._recording:
            self._record_button.configure(text=text.t("record_running"))
        else:
            self._record_button.configure(
                text=text.t("record_toggle" if self._toggle else "record_hold")
            )

    def set_status(self, message: str) -> None:
        """A status line that comes from the app, shown as it came."""
        self._status_key = ""
        self._status_raw = message
        self._status_role = "danger"
        self._status.configure(text=message, fg=self._colours.danger)
        self._dot.set_colour(self._colours.danger)

    def set_error(self, message: str) -> None:
        self._set_status_key("status_error", "danger")
        self.append_note(message)

    def _set_status_key(self, key: str, role: str) -> None:
        self._status_key = key
        self._status_raw = ""
        self._status_role = role
        self._status.configure(text=text.t(key), fg=self._status_colour(role))
        self._dot.set_colour(self._status_colour(role))

    def _status_colour(self, role: str) -> str:
        return {
            "success": self._colours.success,
            "danger": self._colours.danger,
        }.get(role, self._colours.text_muted)

    def _refresh_status(self) -> None:
        """Put the status line back from the key or the raw message, in its role."""
        if self._status_key:
            self._status.configure(
                text=text.t(self._status_key), fg=self._status_colour(self._status_role)
            )
        elif self._status_raw:
            self._status.configure(
                text=self._status_raw, fg=self._status_colour(self._status_role)
            )
        self._dot.set_colour(self._status_colour(self._status_role))

    def _title(self) -> str:
        """`WinVosk <version>`, plus the device once the engine has named one.

        The release is in the title rather than only in `--diagnose`, because a
        bug report starts with the title of the window that misbehaved.
        """
        name = f"{config.APP_NAME} {config.VERSION}"
        if not self._device:
            return name
        return f"{name} — {text.t('title_input', device=self._device)}"

    # The loop.

    def schedule(self, callback: Callable[[], None]) -> None:
        self._root.after(POLL_MS, callback)

    def mainloop(self) -> None:
        self._root.mainloop()

    def destroy(self) -> None:
        theme.reset()
        try:
            self._overlay.destroy()
        except tk.TclError:
            log.debug("overlay already destroyed", exc_info=True)
        try:
            self._root.destroy()
        except tk.TclError:
            log.debug("panel already destroyed", exc_info=True)
