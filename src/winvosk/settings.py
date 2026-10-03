"""User settings kept in settings.json next to the application.

The file is per-machine state, so it is ignored by git and deleted freely: a
missing or broken file only costs the defaults, never a working application.
The schema is six keys: the hotkey list, the interface language and four on/off
switches — "Печатать в активное окно", "Сразу в буфер", "Исправлять свои слова"
and "Переключать запись". Unknown keys are ignored on read so a file written by a
later version still loads, and a value of the wrong shape or one `hotkey.parse`
refuses is replaced by the defaults rather than handed on to the listener, which
would raise and keep the app from starting at all.

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
LANGUAGE_KEY = "language"


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


def reset() -> list[str]:
    """Forget the stored hotkey and go back to `config.HOTKEYS`."""
    data = load()
    data.pop(HOTKEY_KEY, None)
    save(data)
    return list(config.HOTKEYS)
