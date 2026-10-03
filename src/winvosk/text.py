"""Every string the user sees, in one table.

Two reasons for this to exist. The obvious one is translation: the panel, the
tray, the notifications and the capture hints all come from here, so the language
switch has one thing to change. The less obvious one is that a string is a key:
a widget that shows one can be re-painted after the language changes, which is
what `Panel.set_language` does, and the probe can prove that no language is
missing an entry.

The table is the only place Russian or English UI text is allowed to live. That
is not a style rule for its own sake: `tools/lang_probe.py` walks the source
tree and fails on any Cyrillic string literal outside this file, so a new label
cannot quietly appear in one language only.

Formatting is `str.format` with named placeholders, and a key that no language
has falls back to Russian and then to the key itself rather than raising: a
missing translation must never take the application down.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# English is the default: the shipped model is Russian, but the interface is
# read by whoever installed it, and the first thing a new user has to find is
# the language switch — which is a great deal harder to find in a language they
# cannot read. Russian is one click away and stays one click away.
DEFAULT_LANGUAGE = "en"
# The default first: the selector lists them in this order, so the one that is
# already active is the leftmost button.
LANGUAGES = ("en", "ru")

# Each language names itself in its own script, so the selector reads correctly
# whichever language is active.
LANGUAGE_NAMES = {"ru": "Русский", "en": "English"}

MESSAGES: dict[str, dict[str, str]] = {
    # panel: tabs, status, buttons
    "tab_dictation": {"ru": "Диктовка", "en": "Dictation"},
    "tab_settings": {"ru": "Настройки", "en": "Settings"},
    "status_loading": {"ru": "Загрузка модели...", "en": "Loading the model..."},
    "status_ready": {"ru": "Готов", "en": "Ready"},
    "status_recording": {"ru": "Идёт запись", "en": "Recording"},
    "status_error": {"ru": "Ошибка", "en": "Error"},
    "record_hold": {"ru": "Удерживайте", "en": "Hold"},
    "record_toggle": {"ru": "Начать запись", "en": "Start"},
    "record_running": {"ru": "Идёт…", "en": "Recording…"},
    "button_stop": {"ru": "Стоп", "en": "Stop"},
    "button_copy": {"ru": "Копировать", "en": "Copy"},
    "button_clear": {"ru": "Очистить", "en": "Clear"},
    "button_reset": {"ru": "Сбросить", "en": "Reset"},
    "transcript_placeholder": {
        "ru": "Здесь появится распознанный текст",
        "en": "Recognised text appears here",
    },
    "footer": {
        "ru": "Удерживайте {label} и говорите   ·   закрыть окно = свернуть в трей",
        "en": "Hold {label} and speak   ·   closing the window hides it to the tray",
    },
    "footer_toggle": {
        "ru": "Нажмите {label} и говорите, нажмите ещё раз — стоп   ·   закрыть окно "
              "= свернуть в трей",
        "en": "Press {label} and speak, press again to stop   ·   closing the "
              "window hides it to the tray",
    },
    "title_input": {"ru": "вход: {device}", "en": "input: {device}"},
    "hotkey_or": {"ru": "  или  ", "en": "  or  "},

    # panel: the settings tab
    "settings_intro": {
        "ru": "Диктовка включается удержанием: зажмите сочетание, говорите, "
              "отпустите. Клавиши пишутся в то окно, которое было впереди.",
        "en": "Dictation is push to talk: hold the combination, speak, release. "
              "The words are typed into whatever window was in front.",
    },
    "hotkey_label": {"ru": "Клавиша начала записи", "en": "Dictation key"},
    "capture_prompt": {"ru": "Нажмите клавиши…", "en": "Press the keys…"},
    "hint_escape": {"ru": "Esc — отмена", "en": "Esc — cancel"},
    "hint_idle": {
        "ru": "Нажмите на поле и запишите сочетание",
        "en": "Click the field and press the combination",
    },
    "group_insertion": {"ru": "Куда попадает текст", "en": "Where the text goes"},
    "group_startup": {"ru": "Запуск", "en": "Startup"},
    "group_language": {"ru": "Язык", "en": "Language"},
    "group_appearance": {"ru": "Оформление", "en": "Appearance"},
    "group_words": {"ru": "Свои слова", "en": "Your own words"},
    "option_typing": {
        "ru": "Печатать в активное окно",
        "en": "Type into the active window",
    },
    "option_clipboard": {
        "ru": "Сразу копировать в буфер",
        "en": "Copy to the clipboard right away",
    },
    "option_corrections": {
        "ru": "Исправлять свои слова",
        "en": "Correct my own words",
    },
    "option_corrections_empty": {
        "ru": "Исправлять свои слова (список пуст)",
        "en": "Correct my own words (list is empty)",
    },
    "words_empty_hint": {
        "ru": "Добавьте слова в phrases.txt, по одному в строке",
        "en": "Add words to phrases.txt, one per line",
    },
    "option_autostart": {"ru": "Автозапуск с Windows", "en": "Start with Windows"},
    "option_theme": {"ru": "Тёмная тема", "en": "Dark theme"},
    "theme_hint": {
        "ru": "Тёмная — для ночной работы, светлая — для дневной. Настройка "
              "сохраняется рядом с программой",
        "en": "Dark for the night, light for the day. The setting is kept next "
              "to the program",
    },
    "theme_on": {"ru": "Тёмная тема включена", "en": "Dark theme is on"},
    "theme_off": {"ru": "Включена светлая тема", "en": "Light theme is on"},
    "option_toggle": {"ru": "Переключать запись", "en": "Toggle recording"},
    "toggle_hint": {
        "ru": "Нажали — пишет, нажали ещё раз — стоп. Страховка: «Стоп» на панели, "
              "меню трее и потолок в 3 минуты на сессию",
        "en": "Press to start, press again to stop. Safety net: «Stop» in the panel, "
              "the tray menu, and a 3 minute ceiling per session",
    },
    "autostart_hint": {
        "ru": "Запускать вместе с Windows, без окна и без панели",
        "en": "Starts at login, with no console and no panel",
    },
    "language_ru": {"ru": "Русский", "en": "Русский"},
    "language_en": {"ru": "English", "en": "English"},

    # the own-word check, from the settings tab
    "button_check_words": {
        "ru": "Проверить свои слова",
        "en": "Check my own words",
    },
    "words_check_hint": {
        "ru": "Проверяю по модели — это занимает пару секунд",
        "en": "Asking the model — this takes a couple of seconds",
    },
    "words_check_done": {
        "ru": "Модель знает {known} из {total}",
        "en": "The model knows {known} of {total}",
    },
    "words_check_busy": {
        "ru": "Сначала закончите запись",
        "en": "Finish the recording first",
    },
    "report_words_title": {"ru": "свои слова", "en": "your own words"},

    # messages the app posts back to the panel and the tray
    "recording_live": {
        "ru": "Запись — печатаю по мере",
        "en": "Recording — typing as it goes",
    },
    "note_clipboard": {"ru": "текст в буфере", "en": "text in the clipboard"},
    "note_clipboard_also": {
        "ru": "текст также в буфере",
        "en": "text also in the clipboard",
    },
    "copied": {"ru": "Скопировано", "en": "Copied"},
    "nothing_to_copy": {"ru": "Нечего копировать", "en": "Nothing to copy"},
    "saved": {"ru": "Сохранено: {detail}", "en": "Saved: {detail}"},
    "hotkey_changed": {"ru": "Сочетание клавиш: {detail}", "en": "Keys: {detail}"},
    "cannot_take_hotkey": {"ru": "Не удалось занять {label}", "en": "Could not hook {label}"},
    "cannot_take_hotkey_rollback": {
        "ru": "Не удалось занять {wanted} — вернулось {label}",
        "en": "Could not hook {wanted} — back to {label}",
    },
    "cannot_take_hotkey_short": {
        "ru": "Не удалось занять сочетание",
        "en": "Could not hook that combination",
    },
    "hotkey_defaults_restored": {
        "ru": "Вернулись сочетания по умолчанию",
        "en": "Default combinations restored",
    },
    "hotkey_dropped": {
        "ru": "Не годное сочетание отброшено: {detail}",
        "en": "An unusable combination was dropped: {detail}",
    },
    "save_failed": {
        "ru": "Не удалось сохранить настройку",
        "en": "Could not save the setting",
    },
    "theme_failed": {
        "ru": "Не удалось сохранить тему",
        "en": "Could not save the theme",
    },
    "autostart_failed": {
        "ru": "Не удалось изменить автозапуск",
        "en": "Could not change the startup entry",
    },
    "autostart_on": {"ru": "Автозапуск включён", "en": "Startup entry enabled"},
    "autostart_off": {"ru": "Автозапуск выключен", "en": "Startup entry disabled"},
    "typing_on": {
        "ru": "Печать в активное окно включена",
        "en": "Typing into the active window is on",
    },
    "typing_off": {
        "ru": "Печать выключена — текст остаётся в панели и дневнике",
        "en": "Typing is off — the text stays in the panel and the diary",
    },
    "toggle_on": {
        "ru": "Режим переключения: нажали — пишет, нажали ещё — стоп",
        "en": "Toggle mode: press to start, press again to stop",
    },
    "toggle_off": {
        "ru": "Режим удержания: держите клавиши и говорите",
        "en": "Push to talk: hold the keys and speak",
    },
    "clipboard_on": {
        "ru": "Готовый текст копируется в буфер",
        "en": "Every finished session also goes to the clipboard",
    },
    "clipboard_off": {"ru": "Буфер не трогаем", "en": "The clipboard is left alone"},
    "corrections_on": {
        "ru": "Исправляю {count} слов из phrases.txt",
        "en": "Correcting {count} word(s) from phrases.txt",
    },
    "corrections_off": {
        "ru": "Слова из phrases.txt не исправляю",
        "en": "Words from phrases.txt are left as heard",
    },
    "language_saved": {
        "ru": "Язык интерфейса: {name}",
        "en": "Interface language: {name}",
    },
    "report_title": {"ru": "отчёт", "en": "report"},
    "title_error": {"ru": "Ошибка", "en": "Error"},

    # the capture reasons, from hotkey.py
    "capture_needs_modifier": {
        "ru": "нужна клавиша при модификаторе: Ctrl, Alt, Shift или Win",
        "en": "press a key with a modifier held: Ctrl, Alt, Shift or Win",
    },
    "capture_needs_main_key": {
        "ru": "нужна ещё и обычная клавиша — например Ctrl+Shift+Space",
        "en": "needs an ordinary key as well, for example Ctrl+Shift+Space",
    },
    "capture_unnamed_key": {
        "ru": "нажмите обычную клавишу",
        "en": "press an ordinary key",
    },

    # the engine, when the microphone will not open
    "engine_failed": {
        "ru": "Не удалось запустить распознавание: {error}",
        "en": "Could not start recognition: {error}",
    },

    # tray
    "tray_hold": {"ru": "Удерживайте {label}", "en": "Hold {label}"},
    "tray_toggle": {"ru": "Нажмите {label} — запись", "en": "Press {label} to record"},
    "tray_stop": {"ru": "Остановить запись", "en": "Stop recording"},
    "tray_show": {"ru": "Показать панель", "en": "Show the panel"},
    "tray_hide": {"ru": "Скрыть панель", "en": "Hide the panel"},
    "tray_copy": {"ru": "Скопировать текст", "en": "Copy the text"},
    "tray_clear": {"ru": "Очистить", "en": "Clear"},
    "tray_quit": {"ru": "Выход", "en": "Quit"},

    # --vocab-check, which is a console report in the language of the app
    "vocab_example_1": {"ru": "телеграм", "en": "telegram"},
    "vocab_example_2": {"ru": "йоцунфэнь", "en": "yozunfeng"},
}

_language = DEFAULT_LANGUAGE


def language() -> str:
    """The language every `t` call is answered in."""
    return _language


def set_language(code: str) -> bool:
    """Switch the language for this process. False means the code is unknown."""
    global _language
    if code not in LANGUAGES:
        log.warning("%r is not a language this app has, keeping %s", code, _language)
        return False
    _language = code
    return True


def name_of(code: str) -> str:
    """The language's name in its own script, for the selector and the hint."""
    return LANGUAGE_NAMES.get(code, code)


def t(key: str, **kwargs) -> str:
    """The message for `key` in the current language, with placeholders filled."""
    entry = MESSAGES.get(key)
    if entry is None:
        log.warning("no message for %r", key)
        return key
    text = entry.get(_language) or entry.get(DEFAULT_LANGUAGE) or key
    return text.format(**kwargs) if kwargs else text