"""Entry point: wires the tray, the panel, the hotkey and the engine together."""

from __future__ import annotations

import argparse
import ctypes
import logging
import queue
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from winvosk import (autostart, config, corrector, diary, hotkey, keystrokes,
                      recognizer, settings, text, theme, vocabulary)
from winvosk.panel import Panel
from winvosk.recognizer import DictationEngine, device_name, input_device
from winvosk.tray import TrayIcon

log = logging.getLogger("winvosk.app")


class Session:
    """State of one dictation pass.

    `typed` is what has actually been sent to the keyboard so far, `total` is
    the whole session for the panel and the diary. The two differ while an
    utterance is still open, because the model keeps revising it.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.total = ""
        self.current = ""
        self.live = False
        self.corrections = 0
        self.utterances: list[str] = []
        self.typer = keystrokes.Typer(config.TYPE_DELAY)

    def begin(self, live: bool) -> None:
        self.reset()
        self.live = live
        log.info("session start, live typing %s", live)

    def add_utterance(self, text: str) -> None:
        cleaned = text.strip()
        if cleaned:
            self.utterances.append(cleaned)
            self.total = " ".join(self.utterances)

    def show(self, text: str) -> None:
        self.current = text.strip()

    def finish(self) -> None:
        log.info(
            "session end: %d utterance(s), %d character(s) typed, %d erased, "
            "%d word(s) corrected",
            len(self.utterances), self.typer.typed, self.typer.erased,
            self.corrections,
        )
        self.live = False


class App:
    def __init__(self, commands: queue.Queue, events: queue.Queue) -> None:
        self._commands = commands
        self._events = events
        self._recording = False
        self._closing = False
        self._session = Session()
        # The function, not its result: the guard reads the setting when a
        # recording starts rather than when the process did, like every other
        # setting in this application. Handed the *value* instead, it would hold
        # a string where it expects something to call, `is_armed` would raise
        # `TypeError: 'str' object is not callable`, and the guard would be
        # permanently disarmed no matter what `settings.json` said.
        self._layout = keystrokes.LayoutGuard(settings.dictate_layout)

        model_path = config.resolve_model()
        self._engine = DictationEngine(
            model_path,
            events,
            device=config.MIC_DEVICE or settings.input_device(),
            sample_rate=config.SAMPLE_RATE,
            block_size=config.BLOCK_SIZE,
            show_words=config.SHOW_WORDS,
            max_seconds=config.MAX_SESSION_SECONDS,
        )
        self._panel = Panel(
            commands,
            self._engine.next_level,
            live_typing=settings.live_typing(),
            clipboard=settings.copy_to_clipboard(),
            autostart=autostart.is_enabled(),
            correct_words=settings.correct_words(),
            toggle=settings.toggle_recording(),
            write_history=settings.history_enabled(),
            write_log=settings.logging_enabled(),
            language=settings.language(),
            theme_name=settings.theme_name(),
            devices=self._recording_devices(),
            device=config.MIC_DEVICE or settings.input_device(),
        )
        self._hotkeys: tuple[str, ...] = tuple(config.HOTKEYS)
        self._tray = TrayIcon(
            commands,
            is_panel_visible=lambda: self._panel.visible,
            is_recording=lambda: self._recording,
            hotkey_label=self._hotkey_label,
            is_toggle=settings.toggle_recording,
            palette=theme.palette(settings.theme_name()),
        )
        self._hotkey: hotkey.HotkeyListener | None = None
        self._words: list[str] = vocabulary.own_words(config.PHRASES_FILE)

    @property
    def _hotkey_label(self) -> str:
        return text.t("hotkey_or").join(self._hotkeys)

    @staticmethod
    def _recording_devices() -> list[tuple[str, bool]]:
        """What this machine can record from, as (name, is the system default).

        Asked once at start up and again whenever the device card is opened, and
        never raises: the list fills a group of radio buttons, and a card that
        cannot be built leaves the user with no way to change the device at all.
        """
        return [
            (device.name, device.default) for device in recognizer.input_devices()
        ]

    def _publish_devices(self) -> None:
        self._panel.set_devices(self._recording_devices(), settings.input_device())

    def _corrected(self, text: str) -> str:
        """Swap near misses of the user's words in, on a finished utterance.

        The word list is re-read at the start of every recording, so editing
        `phrases.txt` takes effect on the next sentence without a restart: the
        file is small and hand written, and one read per session costs nothing
        against the 20 ms the typer already pauses after a revision.
        """
        if not text.strip() or not settings.correct_words():
            return text
        fixed, replaced = corrector.correct(text, self._words)
        if replaced:
            self._session.corrections += len(replaced)
            log.info("corrected %d word(s): %s", len(replaced),
                     corrector.describe(replaced))
        return fixed

    def start(self) -> None:
        self._panel.set_word_count(len(self._words))
        self._engine.start_thread()
        self._tray.run()
        self._apply_hotkey(tuple(settings.hotkeys()))
        self._announce_dropped_hotkeys()
        self._panel.schedule(self._pump)

    def _announce_dropped_hotkeys(self) -> None:
        """Say which stored combinations were thrown away, and why.

        They stay in the file — it is the user's, and rewriting it would lose the
        evidence — so this runs on every start, not once. Silently dropping a
        typo would leave the hotkey quietly not being the one that was stored.
        """
        rejected = settings.rejected_hotkeys()
        if not rejected:
            return
        for spec, reason in rejected:
            log.warning("hotkey %s dropped: %s", spec, reason)
        self._panel.set_hotkey_hint(
            text.t("hotkey_dropped", detail=", ".join(spec for spec, _ in rejected)),
            error=True,
        )
        self._tray.notify(
            text.t("hotkey_dropped", detail=", ".join(spec for spec, _ in rejected)),
            f"{config.APP_NAME} {config.VERSION}",
        )

    def _install_hotkey(self, specs: tuple[str, ...]) -> bool:
        """Swap the hook for one on `specs`. False means nothing is installed.

        `on_release` is what makes the listener push to talk, so toggle mode is
        built by leaving it off rather than by a flag the hook has to consult:
        a listener that is told about the mode can only get it wrong, and the
        two behaviours differ in what the hook does with the main key's keyup.
        """
        if self._hotkey is not None:
            self._hotkey.stop()
            self._hotkey = None
        toggle = settings.toggle_recording()
        listener = hotkey.HotkeyListener(
            specs,
            on_press=lambda: self._commands.put("hotkey_press"),
            on_release=None if toggle else lambda: self._commands.put("release"),
        )
        if not listener.start():
            listener.stop()
            return False
        self._hotkey = listener
        self._hotkeys = specs
        log.info("hotkey %s installed, %s", "+".join(specs),
                 "toggle" if toggle else "push to talk")
        return True

    def _apply_hotkey(self, specs: tuple[str, ...]) -> bool:
        """Put `specs` in effect, falling back to the previous ones on failure.

        A combination that cannot be hooked must never leave the app without a
        hotkey, so the old listener is reinstalled and the label follows it.
        Tk thread only: the hook itself never calls back into the panel.
        """
        previous = self._hotkeys
        if self._install_hotkey(specs):
            self._publish_hotkey()
            return True
        log.warning(
            "hotkey %s did not register, going back to %s",
            "+".join(specs), "+".join(previous),
        )
        self._install_hotkey(previous)
        self._publish_hotkey()
        if self._hotkey is None:
            message = text.t("cannot_take_hotkey", label=self._hotkey_label)
            self._panel.set_error(message)
            self._tray.notify(message, text.t("title_error"))
        else:
            message = text.t(
                "cannot_take_hotkey_rollback",
                wanted="+".join(specs), label=self._hotkey_label,
            )
            self._panel.set_status(message)
            self._tray.notify(message, text.t("title_error"))
        return False

    def _publish_hotkey(self) -> None:
        label = self._hotkey_label
        self._panel.set_hotkey(label)
        self._tray.set_hotkey(label)

    def _begin_capture(self) -> None:
        if self._hotkey is None:
            return
        if self._recording:
            # The hook swallows every key while capturing, including the keyup
            # of the hotkey being held, so the engine would wait for its own
            # maximum. End the pass now, the recorder finalises it as usual.
            log.info("recording is running, stopping it before capture")
            self._commands.put("stop_recording")
        self._hotkey.start_capture()
        self._panel.show_capture()

    def _poll_capture(self) -> None:
        result = None if self._hotkey is None else self._hotkey.poll_capture()
        if result is None:
            # The user is still pressing keys, which is the whole point of the
            # capture, so it stays on. This is the only path that returns with
            # capture alive, and it holds no result to act on yet.
            return
        self._end_capture(*result)

    def _stop_capture(self) -> None:
        """The one place where the capture ends. Tk thread only.

        A capturing listener makes the hook swallow every key in the system, so
        a listener left in that state takes the whole keyboard with it: no key
        reaches an application, the dictation hotkey can never fire again and
        the app survives only as a tray icon. Every way out of the capture
        settings goes through here, `_begin_capture` is the only way into it.
        """
        if self._hotkey is not None:
            self._hotkey.stop_capture()

    def _end_capture(self, kind: str, detail: str) -> None:
        """Settle one capture result and hand the keyboard back.

        The keyboard goes back first, before any branch decides what to paint,
        so no outcome can skip it. A refusal is the one case that re-arms, and
        it does so deliberately, after the capture has been dropped.
        """
        self._stop_capture()
        if kind == "cancel":
            self._panel.set_hotkey(self._hotkey_label)
            return
        if kind != "ok":
            log.info("capture refused: %s", detail)
            self._panel.show_capture()
            self._panel.set_hotkey_hint(detail, error=True)
            if self._hotkey is not None:
                self._hotkey.start_capture()
            return
        try:
            hotkey.parse(detail)
        except hotkey.HotkeyError as exc:
            log.warning("captured %r is not a usable hotkey: %s", detail, exc)
            self._panel.show_capture()
            self._panel.set_hotkey_hint(str(exc), error=True)
            if self._hotkey is not None:
                self._hotkey.start_capture()
            return
        if not settings.store_hotkeys([detail]):
            # The disk kept the previous value, so does the panel.
            self._panel.set_hotkey(self._hotkey_label)
            self._panel.set_hotkey_hint(text.t("save_failed"), error=True)
            self._tray.notify(text.t("save_failed"), text.t("title_error"))
            return
        log.info("hotkey changed to %s", detail)
        if self._apply_hotkey((detail,)):
            self._panel.set_hotkey_hint(text.t("saved", detail=detail))
            self._tray.notify(text.t("hotkey_changed", detail=detail))
        else:
            # The rollback reinstalled the previous listener, so the capture is
            # off with it and only the combination to show is in question.
            self._panel.set_hotkey_hint(text.t("cannot_take_hotkey_short"), error=True)

    def _reset_hotkey(self) -> None:
        specs = tuple(settings.reset())
        if tuple(settings.hotkeys()) != specs:
            # The write failed, so the disk still holds the old combination.
            self._panel.set_hotkey(self._hotkey_label)
            self._panel.set_hotkey_hint(text.t("save_failed"), error=True)
            self._tray.notify(text.t("save_failed"), text.t("title_error"))
            return
        if self._apply_hotkey(specs):
            self._panel.set_hotkey_hint(text.t("hotkey_defaults_restored"))
            self._tray.notify(text.t("hotkey_defaults_restored"))

    def _check_words(self) -> None:
        """Run the own-word check from the settings tab, against the live model.

        The engine answers with a `vocab` event, which is where the panel is told
        to show the report, so nothing here waits on the model.
        """
        if not self._engine.is_ready:
            return
        if self._recording:
            # The check shares the worker thread with the audio, so a live
            # recording would have its blocks held up behind a model load.
            self._panel.set_option_hint(text.t("words_check_busy"), error=True)
            return
        phrases = vocabulary.load(config.PHRASES_FILE)
        if not phrases:
            self._panel.set_option_hint(text.t("words_empty_hint"), error=True)
            return
        log.info("own-word check asked for %d phrase(s)", len(phrases))
        self._panel.set_checking_words(True)
        self._engine.check_phrases(phrases)

    def _pump(self) -> None:
        if self._closing:
            return
        try:
            self._drain()
        finally:
            # Last, and in a `finally`. A command that raised must not be able to
            # stop this being scheduled again, because that is not a lost feature:
            # nothing would drain the queues again, so the hotkey would stop
            # starting a recording, the tray would stop opening the panel and the
            # exit would stop working, with the process still holding
            # `Local\WinVoskSingleInstance` so a second copy could not start
            # either. One bad command cost the whole application.
            self._panel.schedule(self._pump)

    def _drain(self) -> None:
        for _ in range(32):
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                break
            self._guarded("command", self._handle_command, command)
        for _ in range(64):
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            self._guarded("event", self._handle_event, event)
        self._guarded("capture", self._poll_capture)

    @staticmethod
    def _guarded(kind: str, action, *args) -> None:
        """Run one queued thing, and let a failure be a failed thing and no more.

        The failure is logged with its traceback, which is the only record of it
        there will ever be: `Panel` routes Tk callback exceptions to the log
        precisely because a windowless bundle has no `stderr` to print one to.
        Swallowing it is not the point — continuing is. A command that cannot be
        carried out should cost the user that command, not the application.

        The arguments are passed through rather than a payload being assumed, so
        a handler that takes none of them — `_poll_capture` — is not handed one.
        """
        try:
            action(*args)
        except Exception:
            log.exception("%s handler failed", kind)

    def _handle_command(self, command) -> None:
        """Run one queued command. A command is a name, or a name with a value.

        A switch in the settings tab carries the value it was just set to, so
        the app decides what to persist and what to show if the write fails.
        """
        name, value = command if isinstance(command, tuple) else (command, None)
        log.info("command: %s", name)
        if name == "hotkey_press":
            self._hotkey_pressed()
        elif name == "press":
            self._engine.start()
        elif name == "release":
            self._engine.stop()
        elif name == "stop_recording":
            self._engine.stop()
        elif name == "capture_hotkey":
            self._begin_capture()
        elif name == "reset_hotkey":
            self._reset_hotkey()
        elif name == "set_toggle":
            self._set_toggle(bool(value))
        elif name == "check_words":
            self._check_words()
        elif name == "set_live_typing":
            self._set_live_typing(bool(value))
        elif name == "set_clipboard":
            self._set_clipboard(bool(value))
        elif name == "set_correct_words":
            self._set_correct_words(bool(value))
        elif name == "set_history":
            self._set_history(bool(value))
        elif name == "set_logging":
            self._set_logging(bool(value))
        elif name == "set_language":
            self._set_language(str(value))
        elif name == "set_autostart":
            self._set_autostart(bool(value))
        elif name == "set_theme":
            self._set_theme(str(value))
        elif name == "set_device":
            self._set_device(value if isinstance(value, str) else None)
        elif name == "copy":
            self._copy(self._session.total or self._panel.text)
        elif name == "copy_history":
            self._copy_history(str(value))
        elif name == "clear":
            self._panel.clear()
            self._session.reset()
        elif name == "show_panel":
            self._panel.present()
        elif name == "hide_panel":
            self._panel.hide()
        elif name == "quit":
            self.quit()

    def _hotkey_pressed(self) -> None:
        """One press of the combination: start it, or stop it if it is running.

        The decision is made here, on the one thread that drains the queue, from
        the state at that moment. Deciding it in the hook callback would read a
        `_recording` that has not caught up with the first press yet, so a quick
        second press could be taken for another start.

        The layout is borrowed here rather than when the engine reports that it
        is listening. That event comes back from the recogniser thread *after* the
        microphone has been opened, so the first fragment could be typed before
        the layout changed — the one fragment this whole mechanism exists to
        protect. The microphone must not open under the layout it was going to
        be fought over in either, so the switch comes first.
        """
        if settings.toggle_recording():
            if not self._recording:
                self._layout.engage()
                self._commands.put("press")
            else:
                self._commands.put("stop_recording")
            return
        self._layout.engage()
        self._commands.put("press")

    def _set_toggle(self, enabled: bool) -> None:
        """Persist the mode and rebuild the hook, or put the switch back.

        The hook is the mode: `on_release` is what makes it push to talk, so a
        change has to reinstall the listener rather than flip a flag somewhere.
        A write that failed leaves the old mode on disk and in the hook, and the
        switch goes back to it.
        """
        if not settings.store_toggle_recording(enabled):
            self._panel.set_toggle(settings.toggle_recording())
            self._option_failed(text.t("save_failed"))
            return
        if self._apply_hotkey(tuple(settings.hotkeys())):
            self._panel.set_toggle(enabled)
            self._tray.refresh()
            self._panel.set_option_hint(
                text.t("toggle_on" if enabled else "toggle_off")
            )
            log.info("recording mode is now %s",
                     "toggle" if enabled else "push to talk")

    def _handle_event(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "ready":
            self._panel.set_ready(event.get("model", ""), event.get("device"))
        elif kind == "fatal":
            self._panel.set_error(str(event.get("message", "")))
            self._tray.notify(str(event.get("message", "")), text.t("title_error"))
        elif kind == "state":
            self._on_state(event)
        elif kind == "partial":
            self._on_partial(event)
        elif kind == "utterance":
            self._on_utterance(event)
        elif kind == "vocab":
            self._panel.show_words_report(
                [str(word) for word in event.get("known", [])],
                [str(word) for word in event.get("missing", [])],
                len(event.get("known", [])) + len(event.get("missing", [])),
            )
        elif kind == "device_error":
            # The microphone could not be opened for that one recording. The
            # engine carries on and the next recording tries again, so this is a
            # message and not a fatal error: a headset asleep in the tray is a
            # normal state of a Windows machine, not a broken app.
            message = str(event.get("message", ""))
            log.warning("input device: %s", message)
            self._panel.set_status(message)
            self._panel.toast(message, error=True)

    def _on_state(self, event: dict) -> None:
        recording = bool(event.get("recording"))
        self._recording = recording
        self._panel.set_recording(recording)
        self._tray.set_recording(recording)
        if recording:
            live = settings.live_typing()
            self._words = vocabulary.own_words(config.PHRASES_FILE)
            self._panel.set_word_count(len(self._words))
            self._session.begin(live)
            if live:
                self._panel.set_status(text.t("recording_live"))
            return
        self._on_stop(event)

    def _on_partial(self, event: dict) -> None:
        """A half finished utterance: revise the words already on screen.

        Left uncorrected on purpose: the model is still changing its mind, so
        correcting here would make the on-screen text jump around for words it
        has not settled on yet. The finished utterance below is corrected, and
        the typer diffs it against whatever partials were typed.
        """
        text = str(event.get("text", ""))
        self._session.show(text)
        self._panel.set_text(self._session.total, text)
        if self._session.live:
            self._session.typer.apply(text)

    def _on_utterance(self, event: dict) -> None:
        """A finished utterance: settle it and start a fresh prefix."""
        text = self._corrected(str(event.get("text", "")))
        self._session.add_utterance(text)
        self._session.show("")
        self._panel.set_text(self._session.total, "")
        if self._session.live:
            self._session.typer.apply(text, boundary=True)

    def _on_stop(self, event: dict) -> None:
        live = self._session.live
        # The tail is typed first and the layout handed back after it, so the
        # last characters of a sentence are typed under the same conditions as
        # every other one of them.
        tail = self._corrected(str(event.get("tail", "")))
        if tail.strip():
            self._session.add_utterance(tail)
            if live:
                self._session.typer.apply(tail, boundary=True)
        self._layout.release()
        self._session.finish()
        text = self._session.total.strip()
        self._panel.set_text(text, "")
        if not text:
            return
        if diary.append(text):
            # Straight on the Tk thread, which is where this runs: `_pump`
            # drains the event queue. A command round-trip would show the new
            # record a frame later for no gain.
            self._panel.reload_history()
        if settings.copy_to_clipboard() and keystrokes.copy_to_clipboard(text):
            self._panel.append_note(
                text.t("note_clipboard_also") if live else text.t("note_clipboard"))

    def _copy(self, text: str) -> None:
        if keystrokes.copy_to_clipboard(text.strip()):
            self._panel.toast(text.t("copied"))
            self._tray.notify(text.t("copied"), config.APP_NAME)
        else:
            self._panel.toast(text.t("nothing_to_copy"), error=True)
            self._tray.notify(text.t("nothing_to_copy"), config.APP_NAME)

    def _copy_history(self, text: str) -> None:
        """Put one record from the history tab on the clipboard, and say so there.

        The same `keystrokes.copy_to_clipboard` the dictation tab uses, because
        copying text out is one operation with one owner: a second path would be
        a second thing to get wrong, and the clipboard is not somewhere this app
        gets to be clever.
        """
        if keystrokes.copy_to_clipboard(text.strip()):
            self._panel.set_history_hint(text.t("copied"))
            self._tray.notify(text.t("copied"), config.APP_NAME)
        else:
            self._panel.set_history_hint(text.t("nothing_to_copy"), error=True)
            self._tray.notify(text.t("nothing_to_copy"), config.APP_NAME)

    def _set_history(self, enabled: bool) -> None:
        """Persist "Keep the history" and put the switch back if the write failed.

        No listener and no registry to rebuild: this switch governs what is
        written from now on, and `diary.append` reads it from the disk for every
        session, so the next one already obeys it.
        """
        if not settings.store_history_enabled(enabled):
            self._panel.set_history_writing(settings.history_enabled())
            self._option_failed(text.t("save_failed"))
            return
        log.info("history %s", "on" if enabled else "off")
        self._panel.set_history_writing(enabled)
        self._panel.set_option_hint(
            text.t("history_on" if enabled else "history_off")
        )

    def _set_logging(self, enabled: bool) -> None:
        """Persist "Write the log file" and re-level the handler that is open.

        The write comes first and the re-level second, so a refused write leaves
        the running process logging exactly what the disk says. `set_log_verbose`
        touching only the file handler is what keeps the console flags and the
        probes logging at INFO either way.
        """
        if not settings.store_logging_enabled(enabled):
            self._panel.set_log_writing(settings.logging_enabled())
            self._option_failed(text.t("save_failed"))
            return
        if not config.set_log_verbose(enabled):
            # No file handler: the app was assembled without one, so the stored
            # value is right and the run cannot honour it. Said out loud rather
            # than left as a switch that appears to do nothing.
            log.warning("no log file handler to re-level")
            self._option_failed(text.t("save_failed"))
            return
        self._panel.set_log_writing(enabled)
        self._panel.set_option_hint(text.t("log_on" if enabled else "log_off"))

    def _set_live_typing(self, enabled: bool) -> None:
        """Persist "Type into the active window" and say what it will do."""
        if not settings.store_live_typing(enabled):
            # The disk kept the old value, so the switch goes back to it.
            self._panel.set_live_typing(settings.live_typing())
            self._option_failed(text.t("save_failed"))
            return
        log.info("live typing %s", "on" if enabled else "off")
        self._panel.set_option_hint(
            text.t("typing_on") if enabled else text.t("typing_off"))

    def _set_clipboard(self, enabled: bool) -> None:
        """Persist "Copy to the clipboard right away"."""
        if not settings.store_copy_to_clipboard(enabled):
            self._panel.set_clipboard(settings.copy_to_clipboard())
            self._option_failed(text.t("save_failed"))
            return
        log.info("copy to clipboard %s", "on" if enabled else "off")
        self._panel.set_option_hint(
            text.t("clipboard_on") if enabled else text.t("clipboard_off")
        )

    def _set_correct_words(self, enabled: bool) -> None:
        """Persist "Correct my own words"."""
        if not settings.store_correct_words(enabled):
            self._panel.set_correct_words(settings.correct_words())
            self._option_failed(text.t("save_failed"))
            return
        log.info("word correction %s", "on" if enabled else "off")
        self._panel.set_option_hint(
            text.t("corrections_on", count=len(self._words)) if enabled
            else text.t("corrections_off"))

    def _set_device(self, name: str | None) -> None:
        """Persist the recording device and hand it to the engine.

        A name and not an index, because an index is a position in a list Windows
        builds per machine and per boot: stored, it points at whatever sits in
        that slot today, which is how a saved microphone becomes a different one
        with no warning. The engine is told rather than rebuilt, so a recording
        already running keeps the device it started with.
        """
        if not settings.store_input_device(name):
            self._publish_devices()
            self._option_failed(text.t("device_failed"))
            return
        self._engine.replace_device(name)
        log.info("recording device is now %r", name or "the system default")
        self._panel.set_option_hint(
            text.t("device_switched", detail=name or text.t("device_auto"))
        )
        self._publish_devices()

    def _set_language(self, code: str) -> None:
        """Persist the interface language and repaint everything in it.

        The app owns the value like every other setting: a failed write leaves
        the disk holding the old language, so the selector goes back to it. The
        switch happens only after the write, because a message translated into a
        language that was never stored would read as a lie on the next start.
        """
        if not settings.store_language(code):
            self._panel.set_language(settings.language())
            self._option_failed(text.t("save_failed"))
            return
        if not self._apply_language(code):
            self._panel.set_language(settings.language())
            return
        log.info("interface language is now %s", code)
        self._panel.set_option_hint(
            text.t("language_saved", name=text.name_of(code)))

    def _apply_language(self, code: str) -> bool:
        """Put `code` in effect for the whole process, window and tray included."""
        self._panel.set_language(code)
        if text.language() != code:
            return False
        self._publish_hotkey()
        self._tray.refresh()
        return True

    def _set_autostart(self, enabled: bool) -> None:
        """Write the HKCU Run entry, and put the switch back if that failed."""
        try:
            autostart.apply(enabled)
        except OSError:
            log.exception("could not change the autostart setting")
            self._panel.set_autostart(autostart.is_enabled())
            self._option_failed(text.t("autostart_failed"))
            return
        message = text.t("autostart_on") if enabled else text.t("autostart_off")
        self._panel.set_option_hint(message)
        self._tray.notify(message, f"{config.APP_NAME} {config.VERSION}")

    def _option_failed(self, message: str) -> None:
        log.warning(message)
        self._panel.set_option_hint(message, error=True)
        self._tray.notify(message, text.t("title_error"))

    def _set_theme(self, name: str) -> None:
        """Persist the interface theme and put it in effect everywhere.

        Same shape as every other switch: the app owns the value, a failed write
        puts the switch back to what is really in effect, and the change only
        happens after the write — a theme that was never stored would be a lie on
        the next start. The tray icon is redrawn too, so the notification area
        does not keep an icon from the palette the panel has just left.
        """
        if not settings.store_theme_name(name):
            self._panel.set_theme(settings.theme_name())
            self._option_failed(text.t("theme_failed"))
            return
        self._panel.set_theme(name)
        if self._panel.theme_name != name:
            self._panel.set_theme(settings.theme_name())
            return
        log.info("interface theme is now %s", name)
        self._tray.set_theme(name)
        self._tray.refresh()
        self._panel.set_option_hint(
            text.t("theme_now", name=theme.theme_names().get(name, name))
        )

    def quit(self) -> None:
        if self._closing:
            return
        self._closing = True
        log.info("shutting down")
        # A layout left in English is a user's next morning rather than a log
        # line, so the shutdown path puts it back even though `_on_stop` already
        # did. `release` is idempotent, so the ordinary case is one no-op.
        self._layout.release()
        self._engine.close()
        self._stop_capture()
        if self._hotkey is not None:
            self._hotkey.stop()
        self._tray.stop()
        self._panel.destroy()

    def run(self) -> None:
        self._panel.mainloop()


def _report(lines: list[str]) -> None:
    """Print a CLI report and, in a windowless bundle, make it visible at all.

    An exe built with `console=False` has no stdout, so `--diagnose` and
    `--autostart` would look like they had done nothing. The same text goes to
    `logs\report.txt` and to a message box, beside the log the app keeps anyway.

    The parameter is `body`, not `text`: `text` is the message module here, and
    shadowing it with a string would turn every message below into a NameError.
    """
    body = "\n".join(lines)
    print(body)
    if not config.FROZEN:
        return
    report = config.LOGS_DIR / "report.txt"
    try:
        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        report.write_text(body + "\n", encoding="utf-8")
        ctypes.windll.user32.MessageBoxW(
            None, body,
            f"{config.APP_NAME} {config.VERSION} — {text.t('report_title')}", 0x40,
        )
    except OSError:
        log.exception("could not write %s", report)


def _autostart_cli(action: str) -> int:
    if action == "status":
        _report([f"autostart: {'on' if autostart.is_enabled() else 'off'}"])
        return 0
    autostart.apply(action == "on")
    _report([f"autostart: {action}"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=config.APP_NAME)
    parser.add_argument(
        "--autostart", choices=("on", "off", "status"), default=None,
        help="manage the Windows startup entry and exit",
    )
    parser.add_argument(
        "--diagnose", action="store_true", help="print an environment report and exit"
    )
    parser.add_argument(
        "--vocab-check", action="store_true",
        help="report which phrases from phrases.txt the model can hear and exit",
    )
    parser.add_argument(
        "--check-bundle", action="store_true",
        help="open the window and draw the chip once, then exit: proves a "
             "PyInstaller bundle still carries its Tcl scripts and its Pillow "
             "extensions, and never opens the microphone",
    )
    args = parser.parse_args(argv)

    config.setup_logging(verbose=settings.logging_enabled())
    # First thing, before any window or report is built: every message comes from
    # `text`, and anything built in the wrong language would have to be rebuilt.
    text.set_language(settings.language())
    if args.autostart:
        return _autostart_cli(args.autostart)
    if args.vocab_check:
        return _vocab_check()
    if args.check_bundle:
        return _check_bundle()
    if args.diagnose:
        return _diagnose()

    if not keystrokes.acquire_single_instance(config.MUTEX_NAME):
        log.warning("another instance is already running")
        return 0

    started = time.perf_counter()
    commands: queue.Queue = queue.Queue()
    events: queue.Queue = queue.Queue()
    try:
        app = App(commands, events)
        log.info("app assembled in %.2fs", time.perf_counter() - started)
        app.start()
        app.run()
    except Exception as exc:
        # Anything escaping here kills the process, and a bundle built with
        # console=False has no stderr for the traceback to reach: the app would
        # be gone with no window, no tray icon and nothing in the log. Catching
        # only FileNotFoundError is what let that happen. Log it, then say so
        # where a person will see it - the log is the diagnostic, and a dialog
        # is the only thing a windowless build can still put on screen.
        log.exception("the app could not start")
        _report([
            f"{config.APP_NAME} {config.VERSION} could not start:",
            f"{type(exc).__name__}: {exc}",
            "",
            f"The full traceback is in {config.LOG_FILE}",
        ])
        return 2
    return 0


def _vocab_check() -> int:
    import vosk

    vosk.SetLogLevel(-1)
    phrases = vocabulary.load(config.PHRASES_FILE)
    if not phrases:
        _report(vocabulary.empty_report_lines(
            config.PHRASES_FILE,
            text.t("vocab_example_1"),
            text.t("vocab_example_2"),
        ))
        return 0
    known, missing = vocabulary.missing_words(config.resolve_model(), phrases)
    _report(vocabulary.report_lines(config.PHRASES_FILE, known, missing))
    return 0


def _check_bundle() -> int:
    """Build the real panel and draw the chip once, then report and exit.

    A bundle can be missing a Tcl script or a Pillow extension while every
    console flag still works: `import tkinter` succeeds long before the first
    `ttk` widget asks for its theme, and `from PIL import Image` succeeds before
    the first `ImageTk.PhotoImage` asks for the extension. Only a recording would
    find out, in front of the user. This finds out in a few seconds, and it never
    opens the microphone, so it runs on a machine with no input at all.

    The real `Panel` is built rather than a couple of loose widgets, so the whole
    widget tree and the tray-only start up are covered: a start that mapped the
    window would take the focus from whatever the user was typing in, and a chip
    that failed to map would leave a recording with no sign that the microphone
    was live.
    """
    lines = [f"{config.APP_NAME}   : {config.VERSION}",
             f"bundle      : {'yes' if config.FROZEN else 'no'}",
             f"base dir    : {config.BASE_DIR}"]
    try:
        import queue as queue_mod

        from winvosk.panel import Panel
        from winvosk.tray import TrayIcon

        # Two devices named here rather than the ones on this machine: the check
        # must not depend on what hardware happens to be plugged in, and the card
        # it draws is the one a user with a microphone sees. The engine is not
        # built, so neither of them is ever opened.
        panel = Panel(
            queue_mod.Queue(), lambda: None,
            devices=(("Check bundle default input", True),
                     ("Check bundle second input", False)),
        )
        root = panel._root
        try:
            lines.append(f"tcl / tk    : {root.tk.call('info', 'patchlevel')}")
            lines.append(f"ttk theme   : {tkinter_style(root)}")
            if panel.visible or root.winfo_ismapped():
                raise AssertionError(
                    "the panel must start in the tray, unmapped and invisible"
                )
            lines.append("start up    : in the tray, window never mapped")
            panel.present()
            root.update_idletasks()
            if not root.winfo_ismapped():
                raise AssertionError("a tray click did not bring the panel up")
            lines.append("tray click  : brings the panel up")
            panel._notebook.select(1)
            for _ in range(4):
                root.update_idletasks()
                root.update()
            lines.append(f"settings tab: {panel.check_settings_reachable()}")
            # Both radio groups on that page — the language and the device — have
            # to show exactly one marked option. A group that marks all of them
            # works and looks wrong, and nothing else here would notice.
            lines.append(f"radios      : {panel.check_radios()}")
            # The history tab is the third page, and the only check that ever
            # looks at it: a tab that cannot be scrolled to its last record looks
            # complete while it is not.
            panel._notebook.select(2)
            for _ in range(4):
                root.update_idletasks()
                root.update()
            lines.append(f"history tab : {panel.check_history_reachable()}")
            panel._notebook.select(0)
            root.update_idletasks()
            panel.hide()
            root.update_idletasks()
            panel._overlay.show()
            for _ in range(12):
                root.update_idletasks()
                root.update()
            chip = panel._overlay._window
            if chip is None or not chip.winfo_ismapped():
                raise AssertionError(
                    "the recording chip did not map while the panel was in the tray"
                )
            # The chip falls back to canvas rectangles when Pillow cannot draw its
            # plate, so a mapped window proves nothing about Pillow on its own.
            # `_photo` is set on the Pillow path and only there.
            if panel._overlay._photo is None:
                raise AssertionError(
                    "the chip fell back to a square plate: Pillow cannot draw the "
                    "antialiased one in this bundle"
                )
            from PIL import Image

            lines.append(
                f"pillow      : {Image.__version__}, antialiased plate "
                f"{chip.winfo_width()}x{chip.winfo_height()}, mapped from the tray"
            )
            panel._overlay.hide()
        finally:
            panel.destroy()
        # The tray itself, last: the panel is the app's only way in, so a bundle
        # whose notification-area icon never appears is a bundle with no user
        # interface at all, and nothing above this line would have noticed.
        tray = TrayIcon(queue_mod.Queue(), lambda: False)
        try:
            if not tray.run():
                raise AssertionError(
                    "Shell_NotifyIcon refused the tray icon: pystray imported and "
                    "the panel built, but no icon reached the notification area"
                )
            lines.append(f"tray icon   : added by Shell_NotifyIcon, visible={tray.visible}")
        finally:
            tray.stop()
    except Exception as exc:
        lines.append(f"GUI         : FAILED — {type(exc).__name__}: {exc}")
        _report(lines)
        return 1
    lines.append("GUI         : ok")
    _report(lines)
    return 0


def tkinter_style(root) -> str:
    """The `ttk` theme in force, which is what proves the script library is whole."""
    from tkinter import ttk

    return ttk.Style(root).theme_use()


def _diagnose() -> int:
    import sounddevice as sd

    # What the engine will actually open: the constant if it says anything, the
    # stored choice otherwise, and the automatic answer when neither does. The
    # point of the line is that it is the truth about this machine, so it cannot
    # report the automatic answer while the settings name a device.
    effective = config.MIC_DEVICE or settings.input_device()
    chosen = config.MIC_DEVICE or (settings.input_device() or "")
    index = input_device(effective)

    lines = [
        f"{config.APP_NAME}   : {config.VERSION}",
        f"python      : {sys.version.split()[0]}  ({sys.executable})",
        f"base dir    : {config.BASE_DIR}",
        f"bundle      : {'yes' if config.FROZEN else 'no'}",
    ]
    try:
        lines.append(f"model       : {config.resolve_model()}")
    except FileNotFoundError as exc:
        lines.append(f"model       : MISSING ({exc})")
    lines += [
        f"autostart   : {'on' if autostart.is_enabled() else 'off'}",
        f"hotkeys     : {text.t('hotkey_or').join(settings.hotkeys())}",
        f"recording   : {'toggle, press again to stop' if settings.toggle_recording() else 'push to talk, hold to talk'}",
        f"live typing : {'on' if settings.live_typing() else 'off'}",
        f"clipboard   : {'on' if settings.copy_to_clipboard() else 'off'}",
        f"language    : {settings.language()} ({text.language()})",
        # The stored theme and the one the process is actually painting in, which
        # are the same thing unless something put a bad value in the file: a
        # mismatch here is why a panel came up in a colour nothing asked for.
        f"theme       : {settings.theme_name()} ({theme.palette(settings.theme_name()).name})",
        f"corrections : {'on' if settings.correct_words() else 'off'}, "
        f"{len(vocabulary.own_words(config.PHRASES_FILE))} own word(s) "
        f"from {config.PHRASES_FILE.name}",
        # The stored value and what the process actually opened the file at,
        # which differ only if a handler was attached before the switch was read.
        f"history     : {'on' if settings.history_enabled() else 'off'}, "
        f"{len(diary.recent())} recent record(s) in {config.LOGS_DIR}",
        f"log file    : {config.LOG_FILE} "
        f"({'everything' if settings.logging_enabled() else 'errors only'})",
        f"settings    : {settings.SETTINGS_FILE}",
        f"insertion   : simulated keystrokes, delay {config.TYPE_DELAY}s",
        # Said here because it is a setting whose absence looks identical to a
        # setting that is not working: an empty value means the layout is never
        # touched, and a filled one is the only evidence the feature is armed.
        f"dictation   : layout {settings.dictate_layout() or 'untouched'}"
        f" while recording",
        f"max session : {config.MAX_SESSION_SECONDS:.0f}s",
        f"records from: {device_name(index)} [{index}] "
        f"({chosen or 'the system default'}; "
        f"PortAudio default input {sd.default.device[1]})",
        "input devices:",
    ]
    for index, device in enumerate(sd.query_devices()):
        if device["max_input_channels"] > 0:
            lines.append(
                f"  [{index:2d}] {device['name']} "
                f"channels={device['max_input_channels']} "
                f"rate={int(device['default_samplerate'])}"
            )
    _report(lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
