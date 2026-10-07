"""User settings kept in settings.json next to the application.

The file is per-machine state, so it is ignored by git and deleted freely: a
missing or broken file only costs the defaults, never a working application.
The schema is twelve keys: the hotkey list, the interface language, the interface
theme, the recording device, six on/off switches — "Печатать в активное окно",
"Сразу в буфер", "Исправлять свои слова", "Переключать запись", "Писать журнал в
файл" and "Сохранять историю" — and the two keys a keyboard needs: the layout
lends to the window being typed in, `dictate_layout`, and the combination pressed
to quiet a layout switcher, `switcher_key`. Unknown keys are ignored on read so a
file written by a later version still loads, and a value of the wrong shape or one
`hotkey.parse` refuses is replaced by the defaults rather than handed on to the
listener, which would raise and keep the app from starting at all.

Nothing is cached: the effective value is read from the file every time, so the
in-memory state and the disk cannot drift apart even if a save fails.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable
from typing import Any

from . import config, hotkey, text

log = logging.getLogger(__name__)

SETTINGS_FILE = config.BASE_DIR / "settings.json"
TEMP_SUFFIX = ".tmp"
HOTKEY_KEY = "hotkeys"
LIVE_TYPE_KEY = "live_typing"
CLIPBOARD_KEY = "copy_to_clipboard"
CORRECT_KEY = "correct_words"
TOGGLE_KEY = "toggle_recording"
LOG_KEY = "write_log"
HISTORY_KEY = "write_history"
LANGUAGE_KEY = "language"
THEME_KEY = "theme"
DEVICE_KEY = "input_device"
LAYOUT_KEY = "dictate_layout"
SWITCHER_KEY = "switcher_key"


def load() -> dict[str, Any]:
    """The stored mapping, empty when there is nothing usable on disk."""
    try:
        # `utf-8-sig` and not `utf-8`: the file is meant to be edited by hand, and
        # Windows editors — Notepad among them — save it with a byte order mark
        # that plain `utf-8` keeps as a character, which would make the whole file
        # look like malformed JSON and cost every setting at once.
        raw = SETTINGS_FILE.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}
    except OSError:
        log.warning("could not read %s, using the defaults", SETTINGS_FILE, exc_info=True)
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        log.warning("%s is not valid JSON, using the defaults", SETTINGS_FILE)
        return {}
    if not isinstance(data, dict):
        log.warning("%s does not hold an object, using the defaults", SETTINGS_FILE)
        return {}
    return data


def save(data: dict[str, Any]) -> bool:
    """Write the mapping atomically and report whether it reached the disk.

    The content goes to a sibling temp file first and is then moved into place
    with `os.replace`, which is atomic on Windows. A crash or a full disk can
    therefore leave the previous file or no file at all, never half of one.
    """
    temp = SETTINGS_FILE.with_name(SETTINGS_FILE.name + TEMP_SUFFIX)
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp, SETTINGS_FILE)
    except OSError:
        log.exception("could not write %s", SETTINGS_FILE)
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            log.debug("could not remove %s", temp, exc_info=True)
        return False
    log.info("settings written: %s", SETTINGS_FILE)
    return True


def hotkeys() -> list[str]:
    """The stored hotkey list, or `config.HOTKEYS` when nothing usable is stored.

    Shape alone is not enough: `["foo"]` and `["win+нет"]` are lists of non-empty
    strings and still raise inside `HotkeyListener`, which under pythonw.exe
    means an app that never starts and a traceback nobody sees. The file is user
    editable, so every spec is parsed here.

    One unusable entry costs **only that entry**. The file is meant to be edited
    by hand, and a single typo taking the whole list away — silently, back to the
    defaults, with the reason buried in the log — is the worst answer available:
    the hotkey simply stops being the one that was stored, and nothing says so.
    `rejected_hotkeys()` returns what was dropped so the panel can say it out
    loud. When nothing at all survives, the defaults return.
    """
    return _usable_hotkeys()[0]


def rejected_hotkeys() -> list[tuple[str, str]]:
    """The stored combinations that were dropped, with the reason for each."""
    return _usable_hotkeys()[1]


def _usable_hotkeys() -> tuple[list[str], list[tuple[str, str]]]:
    stored = load().get(HOTKEY_KEY)
    if stored is None:
        return list(config.HOTKEYS), []
    if (
        not isinstance(stored, list)
        or not stored
        or not all(isinstance(item, str) and item.strip() for item in stored)
    ):
        log.warning(
            "%s: %r must be a non-empty list of non-empty strings, using the defaults",
            SETTINGS_FILE, HOTKEY_KEY,
        )
        return list(config.HOTKEYS), []
    good: list[str] = []
    rejected: list[tuple[str, str]] = []
    for item in stored:
        spec = item.strip()
        try:
            hotkey.parse(spec)
        except hotkey.HotkeyError as exc:
            log.warning(
                "%s: %r is not a usable hotkey (%s), dropping it", SETTINGS_FILE, spec, exc
            )
            rejected.append((spec, str(exc)))
            continue
        good.append(spec)
    if not good:
        return list(config.HOTKEYS), rejected
    return good, rejected


def store_hotkeys(specs: Iterable[str]) -> bool:
    """Persist the hotkey list. False means the disk still holds the old value."""
    data = load()
    data[HOTKEY_KEY] = [spec.strip() for spec in specs]
    return save(data)


def flag(key: str, default: bool) -> bool:
    """A stored on/off switch, or `default` when nothing usable is stored.

    `1`, `"yes"` and `null` are all rejected: the file is user editable, and a
    switch that reads as truthy in one place and falsy in another is worse than
    the default it replaces.
    """
    value = load().get(key)
    if isinstance(value, bool):
        return value
    if value is not None:
        log.warning(
            "%s: %r must be true or false, using %s",
            SETTINGS_FILE, value, default,
        )
    return default


def store_flag(key: str, value: bool) -> bool:
    """Persist one switch. False means the disk still holds the old value."""
    data = load()
    data[key] = bool(value)
    return save(data)


def defaults() -> dict[str, Any]:
    """Every key, with the value a machine that has never chosen anything gets.

    Two of them are empty rather than filled, and both because the value is a fact
    about *this* machine that the application cannot know:

    - `input_device` is `null`, which is an answer here: the system default. A
      name would be a guess about which microphone this computer has.
    - `switcher_key` is `""`, which is the documented way to switch that feature
      off. There is no sensible default combination — the right one is whatever
      the user's own layout switcher is bound to, and naming one would press it
      at a program that never asked.

    Everything else is the shipped default and is written out rather than left
    absent, because a key that is missing and a key that is set to its default
    read the same to the application but not to a person opening the file: this
    is the list of what can be changed, in one place, with nothing hidden.
    """
    return {
        HOTKEY_KEY: list(config.HOTKEYS),
        LIVE_TYPE_KEY: config.LIVE_TYPE_DEFAULT,
        CLIPBOARD_KEY: config.CLIPBOARD_DEFAULT,
        CORRECT_KEY: config.CORRECT_WORDS_DEFAULT,
        TOGGLE_KEY: config.TOGGLE_DEFAULT,
        LOG_KEY: config.LOG_WRITE_DEFAULT,
        HISTORY_KEY: config.HISTORY_WRITE_DEFAULT,
        LANGUAGE_KEY: config.LANGUAGE_DEFAULT,
        THEME_KEY: config.THEME_DEFAULT,
        DEVICE_KEY: None,
        LAYOUT_KEY: config.DICTATE_LAYOUT_DEFAULT,
        SWITCHER_KEY: config.SWITCHER_KEY_DEFAULT,
    }


def ensure_file() -> bool:
    """Write the defaults out on the first run. True when a file was created.

    Only ever a creation: an existing file is the user's, whatever is in it, and
    is never rewritten here. A file that exists but cannot be parsed is left
    alone too — it was already reported by `load`, and overwriting it would
    destroy whatever the hand edit was reaching for.

    Nothing here reads `load()`, which is the whole care in this function: a
    generator that asked the settings module what it currently holds would read
    the file on disk, so the file that gets created would be seeded from whatever
    was already there. Every value in it comes from `config` instead.
    """
    if SETTINGS_FILE.exists():
        return False
    if not save(defaults()):
        return False
    log.info("first run: %s written with every setting and its default",
             SETTINGS_FILE)
    return True


def defaults_text() -> str:
    """The first-run file as text, which is what `save` writes and nothing else.

    Split out so the byte comparison in `tools\\release_probe.py` is against the
    same string rather than a second `json.dumps` written next to it: `save` opens
    the file in text mode, so on Windows the line endings come out CRLF, and a
    probe that built its expectation with a bare `json.dumps` would be comparing
    two encodings of the same content and failing on every run.
    """
    return json.dumps(defaults(), ensure_ascii=False, indent=2) + "\n"


def live_typing() -> bool:
    """True when the recognised words are typed into the foreground window."""
    return flag(LIVE_TYPE_KEY, config.LIVE_TYPE_DEFAULT)


def store_live_typing(value: bool) -> bool:
    return store_flag(LIVE_TYPE_KEY, value)


def copy_to_clipboard() -> bool:
    """True when every finished session is also copied to the clipboard."""
    return flag(CLIPBOARD_KEY, config.CLIPBOARD_DEFAULT)


def store_copy_to_clipboard(value: bool) -> bool:
    return store_flag(CLIPBOARD_KEY, value)


def correct_words() -> bool:
    """True when near misses of the words in `PHRASES_FILE` are replaced."""
    return flag(CORRECT_KEY, config.CORRECT_WORDS_DEFAULT)


def store_correct_words(value: bool) -> bool:
    return store_flag(CORRECT_KEY, value)


def toggle_recording() -> bool:
    """True when the hotkey toggles a recording instead of recording while held.

    Read from disk on every use like every other switch, so the listener can be
    rebuilt from the value that is really in effect rather than from a copy the
    panel happens to be holding.
    """
    return flag(TOGGLE_KEY, config.TOGGLE_DEFAULT)


def store_toggle_recording(value: bool) -> bool:
    return store_flag(TOGGLE_KEY, value)


def logging_enabled() -> bool:
    """True when the log file keeps INFO as well as warnings and errors.

    Read from disk on every use like every other switch, so the file handler is
    re-levelled from the value that is really in effect rather than from a copy
    the panel happens to be holding.
    """
    return flag(LOG_KEY, config.LOG_WRITE_DEFAULT)


def store_logging_enabled(value: bool) -> bool:
    return store_flag(LOG_KEY, value)


def history_enabled() -> bool:
    r"""True when a finished session is appended to the dated file under logs\.

    This switch governs what is written from now on. Files already on disk are
    never touched, which is why the history tab keeps showing them while the
    switch is off.
    """
    return flag(HISTORY_KEY, config.HISTORY_WRITE_DEFAULT)


def dictate_layout() -> str:
    r"""The keyboard layout to lend the foreground window while dictating.

    `config.DICTATE_LAYOUT_DEFAULT` unless the file says otherwise, and an empty
    string means the layout is never touched at all — that is how the feature is
    switched off. The name is a language id, `00000409` for English or
    `00000419` for Russian, because that is what `LoadKeyboardLayoutW` can be
    trusted to resolve; an alias such as `en-US` is refused rather than silently
    answered with the system default. The layout that was there before is put back
    when the recording ends.

    Read from the file on every use, like every other setting here, so editing
    it takes effect without a restart and the disk and the memory cannot disagree.
    """
    value = load().get(LAYOUT_KEY)
    if isinstance(value, str):
        return value.strip()
    return config.DICTATE_LAYOUT_DEFAULT


def store_history_enabled(value: bool) -> bool:
    return store_flag(HISTORY_KEY, value)


def switcher_key() -> str:
    r"""The combination pressed to quiet a keyboard layout switcher while dictating.

    `config.SWITCHER_KEY_DEFAULT` unless the file says otherwise, and an empty
    string means nothing is ever pressed — the shipped default, because on a
    machine with no switcher there is nothing to ask. `ctrl+shift+f10` is the
    combination Punto Switcher can be told to bind to its own "auto-replace off"
    switch; the spelling is the one `hotkey.parse` takes.

    Read from the file on every use, like every other setting here, so editing it
    takes effect without a restart. Whether the value is a combination this
    application can press is settled by the guard that presses it, once per press,
    where there is a log line to be printed into — the same division of labour as
    `dictate_layout` and `LayoutGuard`.
    """
    stored = load().get(SWITCHER_KEY)
    if stored is None:
        return config.SWITCHER_KEY_DEFAULT
    if isinstance(stored, str):
        return stored.strip()
    log.warning(
        "%s: %r must be a combination such as \"ctrl+shift+f10\" or an empty "
        "string, using %r", SETTINGS_FILE, stored, config.SWITCHER_KEY_DEFAULT,
    )
    return config.SWITCHER_KEY_DEFAULT


def language() -> str:
    """The interface language, or the shipped default when nothing usable is stored.

    Checked against `text.LANGUAGES` rather than accepted as any string: an
    unknown code would leave every message untranslated, and `text.t` falls back
    to the key itself, which is worse than the default it replaces.
    """
    stored = load().get(LANGUAGE_KEY)
    if stored is None:
        return config.LANGUAGE_DEFAULT
    if isinstance(stored, str) and stored in text.LANGUAGES:
        return stored
    log.warning(
        "%s: %r must be one of %s, using %r",
        SETTINGS_FILE, stored, ", ".join(text.LANGUAGES), config.LANGUAGE_DEFAULT,
    )
    return config.LANGUAGE_DEFAULT


def store_language(value: str) -> bool:
    """Persist the interface language. False means the disk still holds the old one."""
    if value not in text.LANGUAGES:
        log.warning("%r is not a language this app has", value)
        return False
    data = load()
    data[LANGUAGE_KEY] = value
    return save(data)


def theme_name() -> str:
    """The interface theme, or the shipped default when nothing usable is stored.

    Checked against `config.THEMES` rather than accepted as any string, for the
    same reason `language()` is checked against `text.LANGUAGES`: an unknown name
    has no palette, so every colour in the panel would have to fall back one at a
    time instead of the design falling back once, here.
    """
    stored = load().get(THEME_KEY)
    if stored is None:
        return config.THEME_DEFAULT
    if isinstance(stored, str) and stored in config.THEMES:
        return stored
    log.warning(
        "%s: %r must be one of %s, using %r",
        SETTINGS_FILE, stored, ", ".join(config.THEMES), config.THEME_DEFAULT,
    )
    return config.THEME_DEFAULT


def store_theme_name(value: str) -> bool:
    """Persist the interface theme. False means the disk kept the old one."""
    if value not in config.THEMES:
        log.warning("%r is not a theme this app has", value)
        return False
    data = load()
    data[THEME_KEY] = value
    return save(data)


def input_device() -> str | None:
    """The stored recording device's name, or None to leave it to the system.

    A name and not an index, because an index is a position in a list PortAudio
    builds per machine and per boot: stored, it is a pointer at whatever sits in
    that slot today, which is how a saved microphone turns into a different one
    without a word of warning. A name that no longer resolves to a device is
    still returned — the engine falls back to the automatic choice and says so in
    the log, which is a recoverable answer, where refusing to store a name that
    exists today would not be.
    """
    stored = load().get(DEVICE_KEY)
    if stored is None:
        return None
    if isinstance(stored, str) and stored.strip():
        return stored.strip()
    log.warning(
        "%s: %r must be the name of a recording device or null, using the "
        "system default", SETTINGS_FILE, stored,
    )
    return None


def store_input_device(value: str | None) -> bool:
    """Persist the recording device. None means the system default.

    False means the disk still holds the old value.
    """
    data = load()
    if value is None:
        data[DEVICE_KEY] = None
    elif isinstance(value, str) and value.strip():
        data[DEVICE_KEY] = value.strip()
    else:
        log.warning("%r is not something this app can record from", value)
        return False
    return save(data)


def reset() -> list[str]:
    """Forget the stored hotkey and go back to `config.HOTKEYS`."""
    data = load()
    data.pop(HOTKEY_KEY, None)
    save(data)
    return list(config.HOTKEYS)
