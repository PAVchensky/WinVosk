"""Headless probe for the message table and the language switch.

Two things can rot quietly in a translation layer and neither shows up at
runtime: a key that one language has and the other has not, and a label written
straight into a widget instead of into `winvosk/text.py`. Both are checked here
by reading the source rather than by running the app, so no GUI, model or
microphone is involved.

Run it from the project root:

    .\\.venv\\Scripts\\python.exe .\\tools\\lang_probe.py
"""

import ast
import logging
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

from winvosk import config, settings, text

CYRILLIC = tuple(range(0x0400, 0x0500))
ALLOWED = ROOT / "src" / "winvosk" / "text.py"


def case_every_language() -> bool:
    print("\ncase 1: every key has both languages, and neither is empty", flush=True)
    ok = True
    for key, entry in sorted(text.MESSAGES.items()):
        missing = [code for code in text.LANGUAGES if not entry.get(code, "").strip()]
        extra = [code for code in entry if code not in text.LANGUAGES]
        if missing or extra:
            ok = False
        print(f"  {key:28s} ru={bool(entry.get('ru'))!s:5s} en={bool(entry.get('en'))!s:5s}"
              f" {missing or ''}{' extra:' + str(extra) if extra else ''}", flush=True)
    return ok


def case_placeholders() -> bool:
    print("\ncase 2: the languages format the same placeholders", flush=True)
    ok = True
    import string

    for key, entry in sorted(text.MESSAGES.items()):
        fields = {}
        for code in text.LANGUAGES:
            pattern = entry.get(code, "")
            found = {name for _, name, _, _ in string.Formatter().parse(pattern) if name}
            fields[code] = found
        same = fields["ru"] == fields["en"]
        if not same:
            ok = False
        if fields["ru"] or not same:
            print(f"  {key:28s} {sorted(fields['ru'])} vs {sorted(fields['en'])} {same}",
                  flush=True)
    return ok


def case_no_stray_literals() -> bool:
    print("\ncase 3: no Cyrillic string literal outside text.py", flush=True)
    offenders: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        if "__pycache__" in path.parts or path == ALLOWED:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc is not None and node.body:
                    docstrings.add(id(node.body[0].value))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docstrings:
                continue
            if any(CYRILLIC[0] <= ord(char) <= CYRILLIC[-1] for char in node.value):
                offenders.append(f"{path.name}:{node.lineno}: {node.value[:40]!r}")
    for line in offenders:
        print(f"  {line}", flush=True)
    print(f"  {len(offenders)} stray literal(s)", flush=True)
    return not offenders


def case_language_setting() -> bool:
    print("\ncase 4: the stored language, and what an unusable one costs", flush=True)
    original = settings.SETTINGS_FILE
    with tempfile.TemporaryDirectory(prefix="winvosk_lang_probe_") as work:
        target = Path(work) / "settings.json"
        settings.SETTINGS_FILE = target
        try:
            ok = True
            for payload, label, expected in (
                (None, "missing file", config.LANGUAGE_DEFAULT),
                ('{"language": "en"}', "english", "en"),
                ('{"language": "ru"}', "russian", "ru"),
                ('{"language": "de"}', "a language we do not have", config.LANGUAGE_DEFAULT),
                ('{"language": 7}', "a number", config.LANGUAGE_DEFAULT),
                ('{"language": null}', "null", config.LANGUAGE_DEFAULT),
            ):
                if payload is None:
                    target.unlink(missing_ok=True)
                else:
                    target.write_text(payload, encoding="utf-8")
                got = settings.language()
                good = got == expected
                ok = ok and good
                print(f"  {label:28s} -> {got!r} expected {expected!r} {good}", flush=True)
            stored = settings.store_language("en")
            print(f"  store_language('en') -> {stored}, reads back "
                  f"{settings.language()!r}", flush=True)
            ok = ok and stored and settings.language() == "en"
            refused = settings.store_language("de")
            print(f"  store_language('de') -> {refused}, still "
                  f"{settings.language()!r}", flush=True)
            ok = ok and not refused and settings.language() == "en"
        finally:
            settings.SETTINGS_FILE = original
    return ok


def case_switching() -> bool:
    print("\ncase 5: switching really changes what `t` answers", flush=True)
    saved = text.language()
    try:
        ok = True
        for code in text.LANGUAGES:
            changed = text.set_language(code)
            sample = text.t("button_stop")
            print(f"  {code}: button_stop = {sample!r} {changed and bool(sample)}",
                  flush=True)
            ok = ok and changed and text.language() == code and sample
        refused = text.set_language("de")
        print(f"  an unknown code is refused: {not refused}, kept "
              f"{text.language()!r}", flush=True)
        ok = ok and not refused and text.language() == "en"
        missing = text.t("no_such_key_at_all")
        print(f"  an unknown key returns itself, not a crash: {missing!r}", flush=True)
        ok = ok and missing == "no_such_key_at_all"
    finally:
        text.set_language(saved)
    return ok


def main() -> None:
    results = [
        case_every_language(),
        case_placeholders(),
        case_no_stray_literals(),
        case_language_setting(),
        case_switching(),
    ]
    print(f"\n{sum(results)}/{len(results)} check group(s) passed", flush=True)
    print(f"VERDICT: {'PASS' if all(results) else 'FAIL'}", flush=True)
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()