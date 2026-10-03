"""Always-on-top Tk panel showing the live transcription.

The window is built unmapped and stays in the tray until the tray icon is
clicked, so the app never takes the focus at start up. Everything below works
the same either way: `show` and `hide` are the only two places that map or
unmap it, and the recording chip is a `Toplevel` of this root, which maps on
its own while the root stays withdrawn.

Every visible string is a key from `winvosk.text`, and every widget that shows
one is registered in `self._messages`. That is what makes `set_language` possible
without rebuilding the window: the widgets stay, the state stays, and only the
text is re-painted. Widgets whose text carries a value — the footer, the window
title, the record button — are refreshed by the setter that owns the value, so
the registry holds only the static ones.
"""

from __future__ import annotations

import logging
import queue
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, scrolledtext, ttk

from . import config, overlay, text, vocabulary

log = logging.getLogger(__name__)

WIDTH = 560
HEIGHT = 440
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
    ) -> None:
        self._commands = commands
        self._text = ""
        self._partial = ""
        # The app lives in the tray: the window is built, and stays unmapped,
        # until the tray is clicked. See the withdraw below.
        self._visible = False
        # One closure per widget that shows a message, so a language change can
        # re-paint them all without rebuilding the window.
        self._repaint: list[Callable[[], None]] = []
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
        self._status_color = "#1f7a34"
        self._device = ""

        self._root = tk.Tk()
        # Withdrawn before a single widget is built, so the window is never
        # mapped: no flash on the way to the tray, and no chance of taking the
        # focus away from whatever the user was typing in. `tk.Tk()` maps by
        # itself, which is why the tray is the only thing that shows this.
        # The same trick is in `overlay.RecordingOverlay._build`.
        self._root.withdraw()
        self._live_typing = tk.BooleanVar(value=bool(live_typing))
        self._clipboard = tk.BooleanVar(value=bool(clipboard))
        self._autostart = tk.BooleanVar(value=bool(autostart))
        self._correct_words = tk.BooleanVar(value=bool(correct_words))
        self._toggle_var = tk.BooleanVar(value=bool(toggle))
        self._language = tk.StringVar(value=language)
        # The chip's equalizer is fed by the engine, not by the panel: the
        # levels live in the audio thread and are read here, on the Tk thread.
        self._overlay = overlay.RecordingOverlay(self._root, next_level)
        self._root.title(self._title())
        self._root.attributes("-topmost", True)
        self._root.protocol("WM_DELETE_WINDOW", self.hide)
        self._place()

        # Two tabs: the dictation itself and the settings that shape it.
        self._notebook = ttk.Notebook(self._root)
        self._notebook.pack(fill="both", expand=True)
        body = tk.Frame(self._notebook)
        self._notebook.add(body, text=text.t("tab_dictation"))
        self._track_tab(body, "tab_dictation")
        settings = tk.Frame(self._notebook, padx=16, pady=16)
        self._notebook.add(settings, text=text.t("tab_settings"))
        self._track_tab(settings, "tab_settings")

        header = tk.Frame(body, padx=12, pady=10)
        header.pack(fill="x")
        self._status = tk.Label(
            header, text=text.t("status_loading"), anchor="w",
            font=("Segoe UI", 11, "bold"),
        )
        self._status.pack(side="left")
        self._model = tk.Label(
            header, text=config.MODEL_NAME, anchor="e", fg="#777777",
            font=("Segoe UI", 8),
        )
        self._model.pack(side="right")

        self._box = scrolledtext.ScrolledText(
            body, wrap="word", height=12, font=("Consolas", 12),
            relief="solid", borderwidth=1, padx=8, pady=8,
        )
        self._box.pack(fill="both", expand=True, padx=12, pady=10)
        self._box.configure(state="disabled")

        controls = tk.Frame(body, padx=12)
        controls.pack(fill="x")
        self._record_button = tk.Button(
            controls, text=text.t("record_hold"), width=12, font=("Segoe UI", 10),
        )
        self._record_button.bind("<ButtonPress-1>", self._press)
        self._record_button.bind("<ButtonRelease-1>", self._release)
        self._record_button.bind("<Leave>", self._release)
        self._record_button.pack(side="left")
        self._stop_button = tk.Button(
            controls, text=text.t("button_stop"), width=9, font=("Segoe UI", 10),
            state="disabled", command=self._stop,
        )
        self._stop_button.pack(side="left", padx=6)
        self._track(self._stop_button, "button_stop")
        copy_button = tk.Button(
            controls, text=text.t("button_copy"), width=10, command=self._copy
        )
        copy_button.pack(side="left", padx=6)
        self._track(copy_button, "button_copy")
        clear_button = tk.Button(
            controls, text=text.t("button_clear"), width=9, command=self._clear
        )
        clear_button.pack(side="left")
        self._track(clear_button, "button_clear")

        self._footer = tk.Label(
            body, text=self._footer_text(config.hotkey_label()),
            fg="#777777", font=("Segoe UI", 8), padx=12, pady=10,
        )
        self._footer.pack(fill="x")
        # The footer carries the combination, so it is repainted from the label
        # in effect rather than from a key.
        self._repaint.append(
            lambda: self._footer.configure(text=self._footer_text(self._hotkey_text))
        )

        intro = tk.Label(
            settings, text=text.t("settings_intro"),
            font=("Segoe UI", 9), anchor="w", justify="left",
        )
        intro.pack(fill="x")
        self._track(intro, "settings_intro")
        hotkey_title = tk.Label(
            settings, text=text.t("hotkey_label"), font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        hotkey_title.pack(fill="x", pady=(14, 4))
        self._track(hotkey_title, "hotkey_label")

        hotkey_row = tk.Frame(settings)
        hotkey_row.pack(fill="x")
        # A label, not an entry: nothing is typed here, the hook captures.
        self._hotkey_field = tk.Label(
            hotkey_row, text=config.hotkey_label(), bg="#ffffff", relief="solid",
            borderwidth=1, padx=10, pady=6, font=("Consolas", 12), anchor="w",
        )
        self._hotkey_field.pack(side="left")
        self._hotkey_field.bind("<ButtonPress-1>", self._capture_hotkey)
        reset_button = tk.Button(
            hotkey_row, text=text.t("button_reset"), width=10,
            command=self._reset_hotkey,
        )
        reset_button.pack(side="left", padx=8)
        self._track(reset_button, "button_reset")

        self._hotkey_hint = tk.Label(
            settings, text=text.t("hint_idle"), fg="#777777", font=("Segoe UI", 8),
            anchor="w", justify="left",
        )
        self._hotkey_hint.pack(fill="x", pady=(10, 0))

        # It belongs to the key above it rather than to the switches below: this
        # is a property of how the combination acts, not of where the text goes.
        self._toggle_check = tk.Checkbutton(
            settings, text=text.t("option_toggle"), variable=self._toggle_var,
            command=self._pick_toggle,
        )
        self._toggle_check.pack(anchor="w", pady=(14, 0))
        self._track(self._toggle_check, "option_toggle")
        self._toggle_hint = tk.Label(
            settings, text=text.t("toggle_hint"), fg="#777777",
            font=("Segoe UI", 8), anchor="w", justify="left", wraplength=WIDTH - 32,
        )
        self._toggle_hint.pack(fill="x", pady=(4, 0))

        self._build_options(settings)

    def _build_options(self, parent: tk.Misc) -> None:
        """The switches that decide where the text goes, when it starts, its language."""
        insertion = self._frame(parent, "group_insertion")
        self._check(insertion, "option_typing", self._live_typing, "set_live_typing")
        self._check(insertion, "option_clipboard", self._clipboard, "set_clipboard")
        self._correct_check = self._check(
            insertion, "option_corrections", self._correct_words,
            "set_correct_words", top_pad=4,
        )
        self._word_hint = tk.Label(
            insertion, text="", fg="#777777", font=("Segoe UI", 8), anchor="w",
        )
        self._word_hint.pack(anchor="w")
        # The check belongs to the switch above it, so it sits right under the
        # hint rather than in a group of its own with nothing else in it.
        self._check_words_button = tk.Button(
            insertion, text=text.t("button_check_words"), width=22,
            command=self._check_words,
        )
        self._check_words_button.pack(anchor="w", pady=(8, 0))
        self._track(self._check_words_button, "button_check_words")

        startup = self._frame(parent, "group_startup")
        self._check(startup, "option_autostart", self._autostart, "set_autostart")
        autostart_hint = tk.Label(
            startup, text=text.t("autostart_hint"), fg="#777777",
            font=("Segoe UI", 8), anchor="w",
        )
        autostart_hint.pack(anchor="w", pady=(4, 0))
        self._track(autostart_hint, "autostart_hint")

        language_group = self._frame(parent, "group_language")
        # Endonyms, so each option reads correctly whichever language is active.
        for index, code in enumerate(text.LANGUAGES):
            radio = tk.Radiobutton(
                language_group, text=text.name_of(code), value=code,
                variable=self._language, command=self._pick_language,
            )
            radio.pack(anchor="w", side="left", padx=(0, 16) if index == 0 else 0)

        self._options_hint = tk.Label(
            parent, text="", fg="#777777", font=("Segoe UI", 8), anchor="w",
            justify="left",
        )
        self._options_hint.pack(fill="x", pady=(10, 0))

    def _frame(self, parent: tk.Misc, key: str) -> tk.LabelFrame:
        """A group box that keeps its own title on a language change."""
        frame = tk.LabelFrame(
            parent, text=text.t(key), padx=12, pady=10,
            font=("Segoe UI", 9, "bold"),
        )
        frame.pack(fill="x", pady=(20, 0))
        self._track(frame, key)
        return frame

    def _check(self, parent: tk.Misc, key: str, variable: tk.Variable,
               command: str, top_pad: int = 0) -> tk.Checkbutton:
        check = tk.Checkbutton(
            parent, text=text.t(key), variable=variable,
            command=lambda: self._toggle(command, variable),
        )
        check.pack(anchor="w", pady=(top_pad, 0))
        self._track(check, key)
        return check

    def _pick_language(self) -> None:
        self._commands.put(("set_language", self._language.get()))

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
        self._paint_record_button()
        self._footer.configure(text=self._footer_text(self._hotkey_text))
        self._toggle_hint.configure(
            text=text.t("toggle_hint"),
            fg="#1f7a34" if self._toggle else "#777777",
        )

    def _footer_text(self, label: str) -> str:
        key = "footer_toggle" if self._toggle else "footer"
        return text.t(key, label=label)

    def _track(self, widget: tk.Misc, key: str) -> None:
        """Remember that this widget shows a message, so it can be re-painted."""
        self._repaint.append(lambda w=widget, k=key: w.configure(text=text.t(k)))

    def _track_tab(self, frame: tk.Misc, key: str) -> None:
        self._repaint.append(
            lambda f=frame, k=key: self._notebook.tab(f, text=text.t(k))
        )

    def _paint_messages(self) -> None:
        for repaint in self._repaint:
            try:
                repaint()
            except tk.TclError:
                log.debug("could not repaint a message", exc_info=True)

    def set_language(self, code: str) -> None:
        """Repaint everything the language switch owns, keeping all state.

        The window is not rebuilt: the caret in the text box, the recording
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
        self._hotkey_hint.configure(text=text.t("hint_idle"), fg="#777777")
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

    def _toggle(self, command: str, variable: tk.BooleanVar) -> None:
        """Hand a changed switch to the app, which owns the disk and the registry."""
        self._commands.put((command, bool(variable.get())))

    def _place(self) -> None:
        screen_w = self._root.winfo_screenwidth()
        screen_h = self._root.winfo_screenheight()
        x = max(0, screen_w - WIDTH - MARGIN)
        y = max(0, screen_h - HEIGHT - MARGIN)
        self._root.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")
        self._root.minsize(360, 260)

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

    def set_hotkey(self, label: str) -> str:
        """Publish the combination in effect in the field and in the footer."""
        self._capturing = False
        self._hotkey_text = label
        self._hotkey_field.configure(text=label)
        self._footer.configure(text=self._footer_text(label))
        self._hotkey_hint.configure(text=text.t("hint_idle"), fg="#777777")
        return label

    def show_capture(self) -> None:
        """The field is waiting for a combination now."""
        self._capturing = True
        self._hotkey_field.configure(text=text.t(_CAPTURE_PROMPT))
        self._hotkey_hint.configure(text=text.t("hint_escape"), fg="#777777")

    def set_hotkey_hint(self, message: str, error: bool = False) -> None:
        self._hotkey_hint.configure(text=message, fg="#b02a30" if error else "#1f7a34")

    def set_live_typing(self, value: bool) -> None:
        """Show the switch as the disk and the app actually hold it."""
        self._live_typing.set(bool(value))

    def set_clipboard(self, value: bool) -> None:
        self._clipboard.set(bool(value))

    def set_correct_words(self, value: bool) -> None:
        self._correct_words.set(bool(value))

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
        self._check_words_button.configure(
            state="disabled" if running else "normal"
        )
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
        body = "\n".join(
            vocabulary.report_lines(config.PHRASES_FILE, known, missing)
        )
        messagebox.showinfo(
            f"{config.APP_NAME} {config.VERSION} — "
            f"{text.t('report_words_title')}",
            body,
            parent=self._root if self._visible else None,
        )

    def set_autostart(self, value: bool) -> None:
        self._autostart.set(bool(value))

    def set_option_hint(self, message: str, error: bool = False) -> None:
        self._options_hint.configure(text=message, fg="#b02a30" if error else "#1f7a34")

    def show(self) -> None:
        self._visible = True
        self._root.deiconify()
        self._root.attributes("-topmost", True)

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
        self._set_status_key("status_ready", "#1f7a34")
        self._root.title(self._title())

    def set_recording(self, recording: bool) -> None:
        self._recording = recording
        if recording:
            self._set_status_key("status_recording", "#b02a30")
            self._stop_button.configure(state="normal")
            self._overlay.show()
        else:
            self._set_status_key("status_ready", "#1f7a34")
            self._stop_button.configure(state="disabled")
            self._overlay.hide()
        self._paint_record_button()

    def _paint_record_button(self) -> None:
        """The hold button is the one label that depends on the state as well.

        Repainted on its own so a change of language reaches it: it is neither a
        plain message nor owned by one call, since `set_recording` writes it in
        both directions.
        """
        if self._recording:
            self._record_button.configure(
                text=text.t("record_running"), bg="#f3d6d6",
                activebackground="#f3d6d6", state="disabled",
            )
        else:
            self._record_button.configure(
                text=text.t("record_toggle" if self._toggle else "record_hold"),
                bg="SystemButtonFace", activebackground="SystemButtonFace",
                state="normal",
            )

    def set_status(self, message: str) -> None:
        """A status line that comes from the app, shown as it came."""
        self._status_key = ""
        self._status_raw = message
        self._status_color = "#b02a30"
        self._status.configure(text=message, fg=self._status_color)

    def set_error(self, message: str) -> None:
        self._set_status_key("status_error", "#b02a30")
        self.append_note(message)

    def _set_status_key(self, key: str, color: str) -> None:
        self._status_key = key
        self._status_raw = ""
        self._status_color = color
        self._status.configure(text=text.t(key), fg=color)

    def _refresh_status(self) -> None:
        if self._status_key:
            self._status.configure(text=text.t(self._status_key), fg=self._status_color)
        elif self._status_raw:
            self._status.configure(text=self._status_raw, fg=self._status_color)

    def _title(self) -> str:
        """`WinVosk <version>`, plus the device once the engine has named one.

        The release is in the title rather than only in `--diagnose`, because a
        bug report starts with the title of the window that misbehaved.
        """
        name = f"{config.APP_NAME} {config.VERSION}"
        if not self._device:
            return name
        return f"{name} — {text.t('title_input', device=self._device)}"

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
        self._box.configure(state="normal")
        self._box.delete("1.0", "end")
        if body:
            self._box.insert("1.0", body)
        self._box.configure(state="disabled")
        self._box.see("end")

    def schedule(self, callback: Callable[[], None]) -> None:
        self._root.after(POLL_MS, callback)

    def mainloop(self) -> None:
        self._root.mainloop()

    def destroy(self) -> None:
        try:
            self._overlay.destroy()
        except tk.TclError:
            log.debug("overlay already destroyed", exc_info=True)
        try:
            self._root.destroy()
        except tk.TclError:
            log.debug("panel already destroyed", exc_info=True)
