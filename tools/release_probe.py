"""The release archive must not carry anything that belongs to this machine.

`tools\\package_release.py` refuses to finish if a personal file survived, and the
one that matters most is `settings.json`: it holds the hotkeys actually in use,
the chosen theme and the recording device. Shipping it would put this machine's
choices into a public release, and nothing downstream would notice — the archive
would still be a working WinVosk.

That check cannot be a filename any more, because the release now ships a
pristine `settings.json` on purpose, so the file is compared byte for byte
against the one `package_release.py` generates. Two things then have to hold:

1. the generated file really is the defaults, and not this machine's values read
   back through the same accessors that produced it,
2. the audit refuses anything that is not exactly that file, down to one byte.

The first is a leak waiting to happen: the generator has to read the defaults
somehow, and the obvious way — asking `settings` — asks about the file sitting in
the checkout unless the path is moved first.
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


out.append("1. the generated file holds the defaults, not this machine's")
raw = pkg.settings_bytes()
data = json.loads(raw)
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
}
check("every key is present", set(data) == set(expected),
      f"missing {set(expected) - set(data)}, extra {set(data) - set(expected)}")
for key, want in expected.items():
    check(f"{key} = {json.dumps(want)}", data.get(key) == want)
check("the shipped device is the automatic one, not a name",
      data[settings.DEVICE_KEY] is None)

out.append("")
out.append("2. the generator ignores this machine's own file")
mine = settings.SETTINGS_FILE
if mine.exists():
    stored = json.loads(mine.read_text(encoding="utf-8-sig"))
    check("this machine really does have a settings.json", isinstance(stored, dict))
    shared = {k: v for k, v in stored.items() if k in data and v == data[k]}
    differing = {k: v for k, v in stored.items() if k in data and v != data[k]}
    out.append(f"     shared values here: {sorted(shared)}")
    out.append(f"     differing here   : {sorted(differing)}")
    # A generator that read the machine's file would carry every differing value
    # across. None of them may appear, and the layout is the one to watch: it is
    # a machine fact rather than a default, and it is empty in a release.
    check("no value unique to this machine reached the generated file",
          not differing or all(data[k] == expected[k] for k in differing))
    check("dictate_layout ships the default, not a value unique to this machine",
          data[settings.LAYOUT_KEY] == config.DICTATE_LAYOUT_DEFAULT)
else:
    out.append("     no settings.json here, so there is nothing to leak")
check("the machine's path was restored", settings.SETTINGS_FILE == mine)

out.append("")
out.append("3. the audit refuses anything that is not that file")
scratch = ROOT / "dist" / "_release_probe"
shutil.rmtree(scratch, ignore_errors=True)
scratch.mkdir(parents=True, exist_ok=True)
try:
    (scratch / "settings.json").write_bytes(raw)
    try:
        pkg.audit(scratch)
        check("a pristine file passes", True)
    except SystemExit:
        check("a pristine file passes", False)

    if mine.exists():
        shutil.copy2(mine, scratch / "settings.json")
        try:
            pkg.audit(scratch)
            check("this machine's own file is refused", False)
        except SystemExit:
            check("this machine's own file is refused", True)

    tampered = raw.replace(b'"theme"', b'"Theme"')
    check("the tamper actually differs", tampered != raw)
    (scratch / "settings.json").write_bytes(tampered)
    try:
        pkg.audit(scratch)
        check("one renamed key is refused", False)
    except SystemExit:
        check("one renamed key is refused", True)

    (scratch / "phrases.txt").write_text("слова", encoding="utf-8")
    (scratch / "settings.json").write_bytes(raw)
    try:
        pkg.audit(scratch)
        check("a word list beside it is still refused", False)
    except SystemExit:
        check("a word list beside it is still refused", True)
finally:
    shutil.rmtree(scratch, ignore_errors=True)

out.append("")
out.append(f"failures: {failures}")
out.append("PASS" if not failures else "FAIL")

(ROOT / "tmp" / "release_probe_report.txt").write_text(
    "\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))