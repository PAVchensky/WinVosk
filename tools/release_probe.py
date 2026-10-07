"""The settings file is created by the application, not shipped in the archive.

`tools\\package_release.py` refuses to finish if a personal file survived, and the
one that matters most is `settings.json`: it holds the hotkeys actually in use,
the chosen theme and the recording device. Shipping it would put this machine's
choices into a public release, and nothing downstream would notice — the archive
would still be a working WinVosk.

Since 2.1.2 there is no settings file in the archive at all. The application
writes one on its first run, next to the exe, from `settings.defaults()`. That
moves the risk rather than removing it, and this probe covers where it moved:

1. `defaults()` is the whole list of keys, and every value in it is a default —
   it must not read the file that it is about to write, or a machine that already
   had one would seed a fresh copy with its own hotkeys;
2. `ensure_file()` creates it once and never touches an existing one, including a
   broken one that `load()` has already reported;
3. the two keys whose value is a fact about the machine come out empty, because a
   guessed microphone name and a guessed switcher combination are worse than none;
4. the audit refuses any `settings.json` by name again, which is only safe
   because the archive cannot contain a legitimate one.

The first is the leak waiting to happen: `defaults()` could easily have been built
by asking the accessors, and every one of those answers "what is in the file".
"""

import importlib.util
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

spec = importlib.util.spec_from_file_location(
    "package_release", ROOT / "tools" / "package_release.py")
pkg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pkg)

from winvosk import config, settings  # noqa: E402

out = []
failures = 0


def check(name, condition, note=""):
    global failures
    failures += 0 if condition else 1
    tail = f"   ({note})" if note else ""
    out.append(f"  {'ok  ' if condition else 'FAIL'} {name}{tail}")


out.append("1. the defaults are every key, and every value is a default")
data = settings.defaults()
# The bytes the application actually puts on disk. `save` opens the file in text
# mode, so on Windows the newlines come out CRLF; the translation is done here so
# the comparison is against what is really there rather than against a second
# `json.dumps` that happens to differ only in its line endings.
raw = settings.defaults_text().replace("\n", "\r\n").encode("utf-8")
check("it is valid UTF-8 JSON", isinstance(data, dict))
out.append(f"     {len(raw)} bytes, {len(data)} keys")

expected = {
    settings.HOTKEY_KEY: list(config.HOTKEYS),
    settings.LIVE_TYPE_KEY: config.LIVE_TYPE_DEFAULT,
    settings.CLIPBOARD_KEY: config.CLIPBOARD_DEFAULT,
    settings.CORRECT_KEY: config.CORRECT_WORDS_DEFAULT,
    settings.TOGGLE_KEY: config.TOGGLE_DEFAULT,
    settings.LOG_KEY: config.LOG_WRITE_DEFAULT,
    settings.HISTORY_KEY: config.HISTORY_WRITE_DEFAULT,
    settings.LANGUAGE_KEY: config.LANGUAGE_DEFAULT,
    settings.THEME_KEY: config.THEME_DEFAULT,
    settings.DEVICE_KEY: None,
    settings.LAYOUT_KEY: config.DICTATE_LAYOUT_DEFAULT,
    settings.SWITCHER_KEY: config.SWITCHER_KEY_DEFAULT,
}
check("every key is present", set(data) == set(expected),
      f"missing {set(expected) - set(data)}, extra {set(data) - set(expected)}")
for key, want in expected.items():
    check(f"{key} = {json.dumps(want)}", data.get(key) == want)

out.append("")
out.append("2. the defaults do not come from this machine's own file")
mine = settings.SETTINGS_FILE
if mine.exists():
    stored = json.loads(mine.read_text(encoding="utf-8-sig"))
    check("this machine really does have a settings.json", isinstance(stored, dict))
    shared = {k: v for k, v in stored.items() if k in data and v == data[k]}
    differing = {k: v for k, v in stored.items() if k in data and v != data[k]}
    out.append(f"     shared values here: {sorted(shared)}")
    out.append(f"     differing here   : {sorted(differing)}")
    check("no value unique to this machine is in the defaults",
          all(data[k] == expected[k] for k in differing),
          "a generator built from the accessors would carry these across")
else:
    out.append("     no settings.json here, so there is nothing to leak")
check("the two machine facts are empty rather than guessed",
      data[settings.DEVICE_KEY] is None
      and data[settings.SWITCHER_KEY] == config.SWITCHER_KEY_DEFAULT == "")

out.append("")
out.append("3. ensure_file creates it once and never touches an existing one")
scratch = ROOT / "dist" / "_release_probe_settings"
shutil.rmtree(scratch, ignore_errors=True)
scratch.mkdir(parents=True, exist_ok=True)
target = scratch / "settings.json"
real, settings.SETTINGS_FILE = settings.SETTINGS_FILE, target
try:
    made = settings.ensure_file()
    check("a first run creates the file", made and target.exists())
    check("and it is the defaults, byte for byte",
          target.read_bytes() == raw,
          f"{len(target.read_bytes())} bytes on disk, {len(raw)} expected")
    check("and it parses as what it claims to be",
          json.loads(target.read_text(encoding="utf-8")) == expected)

    # A second run must not rewrite it, and must not cost anything either.
    check("a second run creates nothing", settings.ensure_file() is False)

    # The file a user edited is theirs, whatever is in it.
    hand_edited = '{"hotkeys": ["ctrl+alt+p"], "switcher_key": "ctrl+shift+f10"}'
    target.write_text(hand_edited, encoding="utf-8")
    check("a hand edited file is left exactly as it is",
          settings.ensure_file() is False
          and target.read_text(encoding="utf-8") == hand_edited)
    check("and the application reads the user's own values out of it",
          settings.hotkeys() == ["ctrl+alt+p"]
          and settings.switcher_key() == "ctrl+shift+f10")

    # A file that cannot be parsed has already been reported by `load()`;
    # overwriting it here would destroy whatever the edit was reaching for.
    target.write_text("not json at all", encoding="utf-8")
    check("a broken file is not overwritten",
          settings.ensure_file() is False
          and target.read_text(encoding="utf-8") == "not json at all")

    # And the defaults read back through the accessors, which is the round trip a
    # first run actually performs.
    target.unlink(missing_ok=True)
    settings.ensure_file()
    check("every default reads back as itself through the accessors",
          settings.hotkeys() == list(config.HOTKEYS)
          and settings.live_typing() == config.LIVE_TYPE_DEFAULT
          and settings.copy_to_clipboard() == config.CLIPBOARD_DEFAULT
          and settings.correct_words() == config.CORRECT_WORDS_DEFAULT
          and settings.toggle_recording() == config.TOGGLE_DEFAULT
          and settings.logging_enabled() == config.LOG_WRITE_DEFAULT
          and settings.history_enabled() == config.HISTORY_WRITE_DEFAULT
          and settings.language() == config.LANGUAGE_DEFAULT
          and settings.theme_name() == config.THEME_DEFAULT
          and settings.input_device() is None
          and settings.dictate_layout() == config.DICTATE_LAYOUT_DEFAULT
          and settings.switcher_key() == config.SWITCHER_KEY_DEFAULT)
finally:
    settings.SETTINGS_FILE = real
    shutil.rmtree(scratch, ignore_errors=True)
check("the machine's path was restored", settings.SETTINGS_FILE == mine)

out.append("")
out.append("4. the audit refuses a settings.json by name, as it always did")
out.append("     safe now only because the archive ships no settings.json at all")
if mine.exists():
    staging = ROOT / "dist" / "_release_probe"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    try:
        (staging / "settings.json").write_bytes(raw)
        try:
            pkg.audit(staging)
            check("even a pristine-looking one is refused", False)
        except SystemExit:
            check("even a pristine-looking one is refused", True)

        shutil.copy2(mine, staging / "settings.json")
        try:
            pkg.audit(staging)
            check("this machine's own file is refused", False)
        except SystemExit:
            check("this machine's own file is refused", True)

        (staging / "settings.json").unlink()
        (staging / "phrases.txt").write_text("слова", encoding="utf-8")
        try:
            pkg.audit(staging)
            check("a word list is refused", False)
        except SystemExit:
            check("a word list is refused", True)

        (staging / "phrases.txt").unlink()
        (staging / "logs").mkdir()
        (staging / "logs" / "2026-10-06.txt").write_text("слова", encoding="utf-8")
        try:
            pkg.audit(staging)
            check("a dictated history is refused", False)
        except SystemExit:
            check("a dictated history is refused", True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    check("the archive ships no settings file of its own",
          not hasattr(pkg, "settings_bytes"))

out.append("")
out.append(f"failures: {failures}")
out.append("PASS" if not failures else "FAIL")

(ROOT / "tmp" / "release_probe_report.txt").write_text(
    "\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))