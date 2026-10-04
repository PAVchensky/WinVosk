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
from collections.abc import Callable, Sequence
from datetime import date
from tkinter import messagebox

from PIL import ImageTk

from . import config, diary, overlay, text, theme, tray, vocabulary, widgets

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
# The smallest the window is allowed to get, in design pixels. Below this the two
# columns of the settings tab stop being side by side and the transcript stops
# being readable, and `Paragraph` starts wrapping at a width a sentence does not
# fit in. The window is resizable above it, and every width-dependent thing on
# the page is measured at `<Configure>` rather than from `WIDTH`.
MIN_WIDTH = 560
MIN_HEIGHT = 460
MARGIN = 24
POLL_MS = 60
# The history tab is last, always: it is the one tab that is read rather than
# acted in, and a user who came for dictation has to find the record button where
# it has always been. `Tabs` is told this index on every selection, so the order
# is a named thing rather than a number typed twice.
HISTORY_TAB = 2

_CAPTURE_PROMPT = "capture_prompt"


def _walk(widget: tk.Misc):
    """Every widget under `widget`, the whole way down.

    An explicit stack rather than recursion, so a deep page cannot exhaust it.
    It reaches everything a `pack`ed tree holds, and a widget `place`d or `grid`ded
    as well — but not one embedded in a canvas with `create_window`, which is not
    in anybody's child list. The radio groups are inside cards, so they are found;
    a group that ever moves into a canvas would have to be looked for directly.
    """
    pending = list(widget.winfo_children())
    while pending:
        child = pending.pop()
        yield child
        pending.extend(child.winfo_children())


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
        write_history: bool = True,
        write_log: bool = True,
        language: str = text.DEFAULT_LANGUAGE,
        theme_name: str = theme.DEFAULT_THEME,
        devices: Sequence[tuple[str, bool]] = (),
        device: str | None = None,
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
        # What this machine can record from, as (name, is the system default).
        # The panel is told rather than asked: a card that listed devices would
        # have to import `sounddevice` to find them, and this module is imported
        # by `--check-bundle` on a machine with no audio hardware at all.
        self._devices = list(devices)
        self._device_choice = device
        self._device_box: tk.Frame | None = None
        self._toast: widgets.Toast | None = None
        self._settings_page: widgets.Scroller | None = None
        # What the rows on the history tab were last built from, so a look at the
        # tab that finds nothing new does not throw ten rows away and build ten
        # more. None until they exist.
        self._history_shown: tuple[diary.Entry, ...] | None = None
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
        # What this machine is left with, rather than how the words behave: the
        # history tab says so on its own page, because that is where the
        # consequence of the first one is visible.
        self._write_history = tk.BooleanVar(value=bool(write_history))
        self._write_log = tk.BooleanVar(value=bool(write_log))
        self._dark_var = tk.BooleanVar(value=theme.is_dark(self._theme_name))
        self._language = tk.StringVar(value=language)
        self._device_var = tk.StringVar(value=device or "")
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
        self._notebook = widgets.Tabs(
            self._shell, palette=colours, on_select=self._on_tab)
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

        # Added last and never reordered: see `HISTORY_TAB`.
        history = widgets.Scroller(self._notebook.content, palette=colours)
        self._notebook.add(history, text=text.t("tab_history"), key="tab_history")
        self._history_page = history
        self._build_history(history)
        history.bind_wheel()
        # The rows frame above is new and empty, so the cache of what it was last
        # built from has to go with it: left in place it would tell `reload_history`
        # that the list on screen is already right, which it is not.
        self._history_shown = None
        self.reload_history()

    def _on_tab(self, index: int) -> None:
        """Fill the history tab from the disk when it is looked at.

        The panel spends most of its life on the dictation tab while records are
        being written, so a tab filled once would show the state of the moment it
        was opened rather than what has been said since.
        """
        if index == HISTORY_TAB:
            self.reload_history()

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
        """One card across the top of the page, then a grid of six under it.

        The key gets the full width because its field has to hold a combination
        in monospace next to a Reset button, and neither of those is something to
        squeeze for the sake of a column.

        The six below it are a grid and not two packed columns, which is the whole
        of what was wrong with this tab: packed, each side was as tall as its own
        content, so one column ended in the middle of the page and the other ran
        on past it, and the eye had three different bottoms to line up. In a grid
        a row is as tall as its tallest cell and both of its cards are stretched
        to that height, so the page has one rhythm and a card's own content stays
        at the top of the space it is given.
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

        grid = tk.Frame(body, bg=colours.bg, bd=0, highlightthickness=0)
        grid.pack(fill="x", padx=pad, pady=(theme.px(theme.SPACE), 0))
        # `uniform` is what makes the columns the same width rather than the same
        # weight: two cells that each ask for less than half the page would
        # otherwise end up different sizes, which is the fault the packed columns
        # had.
        grid.grid_columnconfigure(0, weight=1, uniform="settings")
        grid.grid_columnconfigure(1, weight=1, uniform="settings")

        # What the words do when they are recognised, then when the app starts.
        insertion = self._card(grid, "group_insertion", cell=(0, 0))
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

        # Where the words come from. The options are the names Windows gives the
        # hardware, so this is the one card on the page whose contents this module
        # cannot write down: it is filled from outside, in `set_devices`.
        device = self._card(grid, "group_input", cell=(0, 1))
        self._device_box = tk.Frame(
            device.inner, bg=colours.surface, bd=0, highlightthickness=0
        )
        self._device_box.pack(fill="x")
        self._device_hint = self._hint(device.inner, "device_hint", column)

        startup = self._card(grid, "group_startup", cell=(1, 0))
        self._check(startup.inner, "option_autostart", self._autostart,
                    "set_autostart", column)
        self._autostart_hint = self._hint(startup.inner, "autostart_hint", column)

# The two cards that are about this panel rather than about dictation.
        language = self._card(grid, "group_language", cell=(1, 1))
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

        # A switch rather than two radios for the theme: there are two of them and
        # one is what you are looking at now.
        appearance = self._card(grid, "group_appearance", cell=(2, 0))
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

        # Two switches, one card: they are two answers to the same question,
        # which is how much of this machine the app leaves a trace on.
        records = self._card(grid, "group_records", cell=(2, 1))
        self._check(records.inner, "option_history", self._write_history,
                    "set_history", column)
        self._hint(records.inner, "history_switch_hint", column)
        self._check(records.inner, "option_log", self._write_log,
                    "set_logging", column, top_pad=theme.SPACE_SM)
        self._hint(records.inner, "log_switch_hint", column)

        # Nothing here until a setting has something to say, and an empty
        # paragraph that reserves a line and two gaps is twenty pixels of the page
        # spent on silence.
        self._options_hint = self._hint(body, "", wrap, bg=colours.bg)
        self._options_hint.pack_configure(padx=pad, pady=0)

        self.set_devices(self._devices, self._device_choice)

    def set_devices(
        self, devices: Sequence[tuple[str, bool]], selected: str | None
    ) -> None:
        """Fill the device card with what this machine can record from.

        `devices` is (name, is the system default) per device, `selected` is the
        name in effect or None for the system default. Filled from outside rather
        than asked for, so this module never imports `sounddevice`:
        `--check-bundle` runs on a machine with no audio hardware at all and must
        not fail on an import.

        The names are what Windows calls the hardware and do not translate, so
        this is also the one card a change of language rebuilds rather than
        repaints.
        """
        self._devices = list(devices)
        self._device_choice = selected
        if self._device_box is None:
            return
        for child in self._device_box.winfo_children():
            child.destroy()
        known = {name for name, _ in self._devices}
        if selected and selected not in known:
            # Stored, and gone. The engine falls back to the automatic choice and
            # says so in the log; the switch goes back to that rather than
            # pretending a device that is not there is in effect.
            log.info("the stored recording device %r is not connected", selected)
            self._device_choice = None
        self._device_var.set(self._device_choice or "")
        self._device_box.pack(fill="x")
        if not self._devices:
            empty = widgets.Paragraph(
                self._device_box, palette=self._colours,
                text=text.t("device_none"), size=widgets.TYPE_CAPTION,
                colour=self._colours.text_subtle, bg=self._colours.surface,
                width=max(160, self._column_width()),
            )
            # Packed here rather than beside the box so that filling the card a
            # second time — a change of language, a change of theme — finds it
            # among the children it destroys rather than stacking a second one
            # under it.
            empty.pack(fill="x", anchor="w")
            return
        options: list[tuple[str, str]] = [("", text.t("device_auto"))]
        options += [
            (name, f"{name}{text.t('device_default_mark')}" if is_default else name)
            for name, is_default in self._devices
        ]
        wraplength = max(160, self._column_width())
        for value, label in options:
            radio = widgets.Choice(
                self._device_box, palette=self._colours, kind="radio", text=label,
                variable=self._device_var, command=self._pick_device, value=value,
                wraplength=wraplength,
            )
            radio.pack(fill="x", pady=(0, theme.px(theme.SPACE_XS)))

    def _pick_device(self) -> None:
        """Hand the chosen device to the app, which owns the disk and the engine."""
        chosen = self._device_var.get()
        self._commands.put(("set_device", chosen or None))

    def _build_history(self, parent: widgets.Scroller) -> None:
        """The tab as three lines of prose and a list of records.

        A scroller rather than a frame, because ten records that each wrap to
        three lines are taller than the window and a record that cannot be got to
        is the same failure the settings tab already had once.
        """
        colours = self._colours
        body = parent.body
        pad = self._page_pad()
        wrap = self._wrap()

        self._history_caption = widgets.caption(
            body, palette=colours, size=widgets.TYPE_CAPTION, bg=colours.bg
        )
        self._history_caption.configure(text=text.t("history_caption"))
        self._history_caption.pack(fill="x", padx=pad,
                                   pady=(theme.px(theme.SPACE), 0))
        self._track(self._history_caption, "history_caption")

        # Starts out saying what the double-click does, and is repainted with what
        # happened when one is made. Nothing else on the page says it.
        self._history_hint = self._hint(body, "history_hint", wrap, bg=colours.bg)
        self._history_hint.pack_configure(padx=pad, pady=0)
        # While the switch is off this is the truth about the list above it.
        self._history_note = self._hint(body, "history_off_note", wrap, bg=colours.bg)
        self._history_note.pack_configure(padx=pad, pady=0)
        self._history_note.show(not self._write_history.get())

        self._history_card = widgets.Card(body, palette=colours)
        self._history_rows = tk.Frame(
            self._history_card.inner, bg=colours.surface, bd=0,
            highlightthickness=0,
        )
        self._history_rows.pack(fill="both", expand=True)

        self._history_empty = widgets.Paragraph(
            body, palette=colours, text=text.t("history_empty"),
            colour=colours.text_subtle, bg=colours.bg, width=wrap,
        )
        self._history_empty.pack(fill="x", padx=pad,
                                 pady=(theme.px(theme.SPACE), 0))
        self._track(self._history_empty, "history_empty")

    def reload_history(self, *, force: bool = False) -> None:
        """Fill the tab from what is on disk right now.

        The rows are thrown away and built again rather than updated in place:
        the list is ten rows long, it is rebuilt a few times an hour, and a
        record that changed is a different record rather than an edited one.

        But not when the ten rows would be the same ten rows. The tab is filled at
        start up, on every look at it and after every finished sentence, and
        three of those four find nothing new — the panel had a working list on
        screen and threw it away to build the same thing again, each row a frame,
        a paragraph and a text widget of its own. The entries are therefore
        compared first, and `force` is there for the one caller that has to redraw
        the same list for another reason: the recording switch moving changes what
        the note under it says, and nothing in the diary.
        """
        entries = diary.recent()
        shown = tuple(entries)
        if shown == self._history_shown and not force:
            return
        self._history_shown = shown
        for child in self._history_rows.winfo_children():
            child.destroy()
        today = date.today()
        # A bare time is a lie after midnight, so anything that is not from today
        # carries its day as well. The stamps are built first because the column
        # they sit in is as wide as the widest of them.
        stamps = [entry.stamp if entry.day == today
                  else f"{entry.day:%d.%m} {entry.stamp}" for entry in entries]
        stamp_font = theme.mono(widgets.TYPE_TINY)
        stamp_width = max(
            (theme.measure(stamp_font, stamp) for stamp in stamps), default=0
        ) + theme.px(theme.SPACE_XS)
        for position, entry in enumerate(entries):
            if position:
                # A hairline between records. Rows are read one at a time and a
                # wrapped record is three lines tall, so without it the list is
                # a wall of prose with times in it.
                widgets.rule(self._history_rows, palette=self._colours).pack(
                    fill="x", padx=self._page_pad())
            widgets.HistoryRow(
                self._history_rows, palette=self._colours, stamp=stamps[position],
                body=entry.text, width=self._wrap() - stamp_width,
                stamp_width=stamp_width,
                command=lambda said=entry.text: self._commands.put(
                    ("copy_history", said)),
            ).pack(fill="x")
        # The rows did not exist when the page bound its wheel, and a `Text` in a
        # row would otherwise scroll its own three lines instead of the page.
        self._history_page.bind_wheel_below(self._history_rows)
        if entries:
            self._history_card.pack(fill="x", padx=self._page_pad(),
                                    pady=theme.px(theme.SPACE))
        else:
            self._history_card.pack_forget()
        # `show`, and then nothing. `pack_configure` on a paragraph that `show` has
        # just taken out of the layout **packs it again** — and it packs it with
        # whatever width it happens to have at that moment, which is the width of
        # its longest word rather than the width of the page. That is the second
        # half of the vertical text on this tab, and the half that survived the
        # width guards: the empty state and the recording-off note both reappear,
        # one letter per line, in the middle of a list that has records in it. The
        # padding they need was given when they were built.
        self._history_empty.show(not entries)
        self._history_note.show(not self._write_history.get())

    # Small builders, so the settings tab above reads as a list of what is in it.

    def _card(self, parent: tk.Misc, key: str, padx: int = 0,
              first: bool = False,
              aside: Callable[[tk.Misc], tk.Misc] | None = None,
              cell: tuple[int, int] | None = None) -> widgets.Card:
        """A card with its own title, which a language change repaints in place.

        `first` is the top card of a packed run, which is already spaced from
        whatever is above it by the row's own padding: giving it the gap as well
        is twenty pixels of nothing, and the settings tab has six cards.

        `cell` is (row, column) in a `grid` instead, where the row is as tall as
        its tallest cell and both cards are stretched to it — which is the whole
        reason the six cards are in a grid rather than in two packed columns.
        """
        card = widgets.Card(
            parent, palette=self._colours, padding=theme.SPACE
        )
        if cell is None:
            card.pack(
                fill="x", padx=padx,
                pady=(0 if first else theme.px(theme.SPACE), 0),
            )
        else:
            row, column = cell
            card.grid(
                row=row, column=column, sticky="nsew",
                padx=((0, theme.px(theme.SPACE_SM)) if column == 0 else (0, 0)),
                pady=(0, theme.px(theme.SPACE)),
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

    def check_radios(self) -> str:
        """Prove that one and only one option in each radio group is marked.

        A group is a variable and a list of codes, and a radio paints its mark
        from whether the variable holds **its own** code. Painting from whether
        the variable is simply true marks every radio in the group at once,
        because every code is a non-empty string — which is how the language pair
        came up with English and Русский both filled in and neither of them
        chosen. Nothing else on the page can see that: the variable holds exactly
        one value whatever the marks say, so the panel worked and looked wrong.

        Called by `run.py --check-bundle`, because the only other way to find out
        is to look at it.
        """
        groups: dict[int, list[widgets.Choice]] = {}
        for choice in _walk(self._shell):
            if isinstance(choice, widgets.Choice) and choice.is_radio:
                groups.setdefault(id(choice.variable), []).append(choice)
        if not groups:
            raise AssertionError("no radio group was built at all")
        for choices in groups.values():
            marked = [choice for choice in choices if choice.is_marked]
            if len(marked) != 1:
                names = ", ".join(
                    f"{choice.value!r}{'*' if choice.is_marked else ''}"
                    for choice in choices
                )
                raise AssertionError(
                    f"a radio group has {len(marked)} option(s) marked instead of "
                    f"one: {names}"
                )
        return f"{len(groups)} group(s), one option marked in each"

    def check_history_reachable(self) -> str:
        """Prove the last record on the history tab can be got to, and report how.

        The same walk `check_settings_reachable` does, on the other scrolling
        page: scroll to the end and ask whether the last thing on it is inside
        the window. A tab of records that cannot be scrolled to its last record
        is worse than an empty one, because it looks complete.

        Called by `run.py --check-bundle`, which is the only check that opens a
        third tab at all.
        """
        page = self._history_page
        if page is None:
            raise AssertionError(
                "the history tab was never built, so there is nothing to reach"
            )
        canvas = page.canvas
        self._root.update_idletasks()
        region = canvas.bbox("all")
        content = region[3] if region else 0
        viewport = canvas.winfo_height()
        canvas.yview_moveto(1.0)
        self._root.update_idletasks()
        rows = [child for child in self._history_rows.winfo_children()
                if isinstance(child, widgets.HistoryRow)]
        # The empty state and the list take each other's place, and an unpacked
        # widget still answers with a position — which is why this picks the one
        # that is actually on the page.
        last = rows[-1] if rows else self._history_empty
        bottom = last.winfo_rooty() + last.winfo_height()
        edge = canvas.winfo_rooty() + canvas.winfo_height()
        if bottom > edge + 1:
            raise AssertionError(
                f"the last record is unreachable: the list ends at {bottom} and "
                f"the page shows up to {edge}"
            )
        return (f"{len(rows)} record(s), {content}px in a {viewport}px page, "
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
        # The strip is built inside `Tabs` and never handed out, so it repaints
        # itself from the keys it was added with.
        self._notebook.repaint_labels()
        self._paint_record_button()
        # The device card is built from strings rather than keys, because the
        # labels are the names Windows gives the hardware. Those do not translate,
        # so there is nothing to repaint and only the option list is rebuilt.
        self.set_devices(self._devices, self._device_choice)
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
        if self._toast is not None:
            try:
                self._toast.destroy()
            except tk.TclError:
                log.debug("the toast is already gone", exc_info=True)
            self._toast = None
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
        # The rows were built in the palette this rebuild has just thrown away.
        self.reload_history()
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

        `minsize` is the size the layout was drawn for and no more, so the window
        can be resized in every direction but never squeezed into a shape the two
        columns of settings were not drawn for. It used to be the full design
        size, which is the same number the geometry already asks for - and a
        minimum equal to the current size is a window that cannot be resized at
        all, by the mouse or by the system, which is what it was.
        """
        ratio = theme.scale()
        width, height = int(round(WIDTH * ratio)), int(round(HEIGHT * ratio))
        screen_w = self._root.winfo_screenwidth()
        screen_h = self._root.winfo_screenheight()
        x = max(0, screen_w - width - int(MARGIN * ratio))
        y = max(0, screen_h - height - int(MARGIN * ratio))
        self._root.geometry(f"{width}x{height}+{x}+{y}")
        self._root.minsize(theme.px(MIN_WIDTH), theme.px(MIN_HEIGHT))

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

    def set_history_writing(self, value: bool) -> None:
        """Show the switch as the disk holds it, and say so where it shows.

        The history tab is told as well as the switch, because a user who turns
        recording off and finds nothing new on the history tab has to be able to
        read that it was asked for.
        """
        self._write_history.set(bool(value))
        self._history_note.show(not self._write_history.get())
        # The list itself has not changed, so it is not rebuilt — but the note
        # under it has, and that is what this call is for.
        self.reload_history(force=True)

    def set_log_writing(self, value: bool) -> None:
        self._write_log.set(bool(value))

    def set_history_hint(self, message: str, error: bool = False) -> None:
        """What happened on the history tab, said on the history tab.

        Its own hint rather than `set_option_hint`: that one is a widget on the
        settings page, and a message posted to a tab nobody is looking at is a
        message nobody reads.

        And a toast as well as the line, because the line is at the top of a list
        the reader has usually scrolled down: a double-click that copied a record
        two thirds of the way down the page put its answer off the top of the
        screen, and the tray balloon is the one notification Windows has taught
        everyone to dismiss without reading.
        """
        self._history_hint.configure(
            text=message,
            fg=self._colours.danger if error else self._colours.success,
        )
        self.toast(message, error=error)

    def toast(self, message: str, *, error: bool = False) -> None:
        """Say `message` over the panel for a moment, then take it away.

        Built on first use and thrown away with the panel. A change of theme
        rebuilds it, because a toast is drawn entirely from the palette and a card
        left in the colours of the theme that has just been switched off would be
        the one window on screen that does not match.
        """
        if not message:
            return
        if self._toast is None:
            self._toast = widgets.Toast(self._root, palette=self._colours)
        self._toast.show(message, error=error)

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
        """The engine is up: name the model, and say the device only in the log.

        The device used to be part of the window title. It is not a window's
        business: the name Windows gives an input is long, differs per machine
        and changes with the sound mapper, so a title built from it was a
        different string on every start. It is on the settings tab, where the
        choice is made, and here in the log, where a fault is looked for.
        """
        self._model.configure(text=f"{model}")
        log.info("engine ready: %s on %r", model, device)
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
        """`WinVosk <version>`, and the version is the whole of it.

        The release is in the title rather than only in `--diagnose`, because a
        bug report starts with the title of the window that misbehaved. The device
        that is recording is not in it: the name Windows gives an input is long,
        differs per machine, and changes with whatever the sound mapper feels like
        doing, so a title built from it was a different string on every start. The
        device is on the settings tab, where a choice is made, and in the log,
        where a fault is looked for.
        """
        return f"{config.APP_NAME} {config.VERSION}"

    # The loop.

    def schedule(self, callback: Callable[[], None]) -> None:
        self._root.after(POLL_MS, callback)

    def mainloop(self) -> None:
        self._root.mainloop()

    def destroy(self) -> None:
        theme.reset()
        if self._toast is not None:
            try:
                self._toast.destroy()
            except tk.TclError:
                log.debug("the toast is already gone", exc_info=True)
            self._toast = None
        try:
            self._overlay.destroy()
        except tk.TclError:
            log.debug("overlay already destroyed", exc_info=True)
        try:
            self._root.destroy()
        except tk.TclError:
            log.debug("panel already destroyed", exc_info=True)
