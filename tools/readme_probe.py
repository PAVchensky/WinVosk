"""The GitHub-facing pages against the rules they are supposed to keep.

Six rules, and every one of them is about something a page can get wrong while
still looking right. None of them needs a microphone, a model, a GUI or a
network, which is what makes this a probe and not a check:

R1  Cyrillic on the English pages is only ever a literal token: a fenced block, a
    table row of input/output pairs, an inline code span quoting what a tool
    printed, or — in the English reference only — a «quoted token». Never a
    control name, never an ordinary English sentence. The Russian guide is
    exempt: it is written in Russian.
R2  Every internal `[..](#anchor)` resolves, in every file, through GitHub's own
    anchor algorithm. The two guides have their own anchors because a heading's
    text is what a slug is made of, so each file is checked against itself.
R3  Every control name the pages quote is a string `winvosk\\text.py` actually
    holds, in the language the page is written in. A renamed label is a
    documentation bug that reads perfectly well, and a control that exists and is
    named nowhere is the same bug the other way round.
R4  The `settings.json` example on both pages carries the language the app really
    ships with, read from `config.LANGUAGE_DEFAULT` rather than repeated here,
    and the English page does not claim the interface ships in Russian.
R5  The corrector rules are stated the right way round. `CUTOFF` is a floor, not a
    ceiling, and the inflection guard is a separate rule — conflating the two
    makes the page describe the opposite of the code, which is how both pages
    came to say that a word *more* than 0.75 similar is left alone.
R6  The two guides hold the same headings, at the same levels, in the same order.
    They are kept in step by section number, and this is what notices when one
    gains a section and the other does not.
R7  Every pinned legacy anchor is still pinned, and none of them duplicates the
    slug of its own heading. A renamed heading used to break every link anyone had
    written to the old name, so the four English anchors that changed are held in
    place by an `<a id="...">` line above the heading — which is invisible, and
    which nothing would complain about losing.

Usage:
    .\\.venv\\Scripts\\python.exe .\\tools\\readme_probe.py
    .\\.venv\\Scripts\\python.exe .\\tools\\readme_probe.py --verbose

Prints `VERDICT: PASS` or `VERDICT: FAIL`, and touches nothing.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from winvosk import config, text  # noqa: E402

README = ROOT / "README.md"
README_RU = ROOT / "README.ru.md"
HOWTO = ROOT / "docs" / "HOWTO.md"

CYRILLIC = re.compile(r"[\u0400-\u04ff]")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
INTERNAL_LINK = re.compile(r"\]\(#([^)]+)\)")
FENCE = re.compile(r"^\s*```")
CODE_SPAN = re.compile(r"`[^`]*`")
TABLE_ROW = re.compile(r"^\s*\|")
QUOTED = re.compile(r"«[^»]*»|\"[^\"]*\"")
# The one Cyrillic string an English page is allowed to carry: the link that hands
# a Russian reader to the Russian guide. It is navigation, not prose, and the
# alternative — an English label on it — hides the fact that the other file is in
# a different language at all.
LANGUAGE_LINK = re.compile(r'<a href="README\.ru\.md">')

# The controls a page is expected to name, so a renamed label cannot pass as
# prose. Both languages are checked: the English page against the English strings
# and the Russian guide against the Russian ones, which is the whole point of
# R3 after the pages were found naming fourteen controls in the wrong language.
EXPECTED: tuple[tuple[str, str], ...] = (
    "tab_dictation",
    "tab_settings",
    "record_hold",
    "button_stop",
    "button_copy",
    "button_clear",
    "button_reset",
    "hotkey_label",
    "option_typing",
    "option_clipboard",
    "option_corrections",
    "button_check_words",
    "option_toggle",
    "option_autostart",
    "option_theme",
    "group_language",
    "tray_stop",
    "tray_show",
    "tray_hide",
    "tray_copy",
    "tray_clear",
    "tray_quit",
)

# Sentences that state the cutoff backwards, in either language. Matched loosely
# on purpose: the failure mode is a plausible rewording, not one exact string.
CUTOFF_WRONG = (
    re.compile(r"more than[^.]{0,40}0\.75[^.]{0,40}left alone", re.IGNORECASE),
    re.compile(r"longer than[^.]{0,40}0\.75[^.]{0,40}similar", re.IGNORECASE),
    re.compile(r"больше чем[^.]{0,40}0\.75[^.]{0,40}не трогается"),
)
CUTOFF_RIGHT = (
    re.compile(r"further than[^.]{0,60}0\.75", re.IGNORECASE),
    re.compile(r"дальше[^.]{0,60}0\.75"),
    re.compile(r"floor,? not a ceiling", re.IGNORECASE),
    re.compile(r"нижняя граница,? а не верхняя"),
)
# The inflection guard is a different rule and has to be stated as one.
INFLECTION_RIGHT = (
    re.compile(r"begins with a listed one", re.IGNORECASE),
    re.compile(r"начинающееся с записи"),
)

SHIPS_RUSSIAN = re.compile(
    r"ships in Russian|поставляется на русском|интерфейс поставляется на русском",
    re.IGNORECASE,
)

# The anchors that used to exist under different heading text, and are held in
# place so a link written against the old name keeps working. Exact set, on
# purpose: adding one is a decision, losing one is a broken external link, and
# R7 is what tells the two apart from a page that merely looks fine.
PINNED: dict[Path, tuple[str, ...]] = {
    README: (
        "settings-every-one-of-them",
        "if-it-recognises-badly",
        "what-it-deliberately-does-not-do",
        "when-something-goes-wrong",
    ),
    README_RU: ("если-чтото-сломалось",),
}
PIN = re.compile(r'^\s*<a id="([^"]+)"></a>\s*$')


def slug(text_line: str) -> str:
    """GitHub's anchor algorithm, close enough to catch a dead link.

    Inline code is unwrapped, the text is lowercased, punctuation is dropped and
    spaces become hyphens. Non-Latin letters are kept, which is what gives the
    Russian guide its own anchors rather than none.
    """
    plain = re.sub(r"`([^`]*)`", r"\1", text_line).strip().lower()
    out: list[str] = []
    for char in plain:
        if char in " \t":
            out.append("-")
        elif char in "`*_~":
            continue
        elif unicodedata.category(char).startswith("P") or char in "()[]{}<>":
            continue
        else:
            out.append(char)
    return "".join(out)


def headings(lines: list[str]) -> list[tuple[int, str]]:
    return [
        (len(match.group(1)), match.group(2))
        for line in lines
        if (match := HEADING.match(line))
    ]


def prose_cyrillic(lines: list[str], allow_quoted: bool) -> list[tuple[int, str]]:
    """Lines with Cyrillic outside every construct allowed to quote a token."""
    fence_open = False
    found: list[tuple[int, str]] = []
    for number, line in enumerate(lines, 1):
        if FENCE.match(line):
            fence_open = not fence_open
            continue
        if fence_open or not CYRILLIC.search(line):
            continue
        if TABLE_ROW.match(line) or CODE_SPAN.search(line):
            continue
        if allow_quoted and QUOTED.search(line):
            continue
        if LANGUAGE_LINK.search(line):
            continue
        found.append((number, line.strip()))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="list the failures")
    args = parser.parse_args(argv)

    failures: list[str] = []
    pages = {
        README: read(README),
        README_RU: read(README_RU),
        HOWTO: read(HOWTO),
    }
    bodies = {path: "\n".join(lines) for path, lines in pages.items()}

    # R1
    for path in (README, HOWTO):
        stray = prose_cyrillic(pages[path], allow_quoted=path is HOWTO)
        for number, line in stray:
            failures.append(f"R1 {path.name}:{number} Cyrillic in prose: {line}")

    # R2
    for path, lines in pages.items():
        anchors = {slug(name) for _, name in headings(lines)}
        for number, line in enumerate(lines, 1):
            for found in INTERNAL_LINK.findall(line):
                if found not in anchors:
                    failures.append(f"R2 {path.name}:{number} dead anchor #{found}")

    # R3
    for key in EXPECTED:
        entry = text.MESSAGES.get(key)
        if entry is None:
            failures.append(f"R3 text.py has no message for {key!r}")
            continue
        for path, code in ((README, "en"), (README_RU, "ru")):
            name = entry.get(code) or ""
            if name and name not in bodies[path]:
                failures.append(
                    f"R3 {path.name} does not name {code} control "
                    f"{key} = {name!r}"
                )

    # R4
    shipped = config.LANGUAGE_DEFAULT
    for path in (README, README_RU):
        if f'"language": "{shipped}"' not in bodies[path]:
            failures.append(
                f'R4 {path.name} settings.json example does not show '
                f'"language": "{shipped}"'
            )
    for path in (README, README_RU):
        if SHIPS_RUSSIAN.search(bodies[path]):
            failures.append(
                f"R4 {path.name} claims the interface ships in Russian; "
                f"config.LANGUAGE_DEFAULT is {shipped!r}"
            )

    # R5
    for path in (README, README_RU):
        body = bodies[path]
        for pattern in CUTOFF_WRONG:
            if pattern.search(body):
                failures.append(
                    f"R5 {path.name} states the cutoff backwards: "
                    f"{pattern.pattern!r}"
                )
        if not any(p.search(body) for p in CUTOFF_RIGHT):
            failures.append(f"R5 {path.name} never says the cutoff is a floor")
        if not any(p.search(body) for p in INFLECTION_RIGHT):
            failures.append(
                f"R5 {path.name} does not state the inflection guard as its own rule"
            )

    # R6
    en_levels = [level for level, _ in headings(pages[README])]
    ru_levels = [level for level, _ in headings(pages[README_RU])]
    if en_levels != ru_levels:
        failures.append(
            f"R6 heading parity: README.md has {len(en_levels)}, "
            f"README.ru.md has {len(ru_levels)}, "
            f"levels {'match' if en_levels == ru_levels else 'differ'}"
        )

    # R7
    for path, expected in PINNED.items():
        lines = pages[path]
        pinned = [match.group(1) for line in lines if (match := PIN.match(line))]
        anchors = [slug(name) for _, name in headings(lines)]
        if tuple(pinned) != expected:
            missing = [name for name in expected if name not in pinned]
            extra = [name for name in pinned if name not in expected]
            detail = []
            if missing:
                detail.append(f"lost {', '.join(missing)}")
            if extra:
                detail.append(f"added {', '.join(extra)}")
            failures.append(
                f"R7 {path.name} pinned anchors: {len(pinned)} found, "
                f"{len(expected)} expected ({'; '.join(detail)})"
            )
        for name in pinned:
            if name in anchors:
                failures.append(
                    f"R7 {path.name} pins #{name}, which its own heading already "
                    f"provides — the pin is noise and will be numbered -1"
                )

    print(f"files         : {', '.join(path.name for path in pages)}")
    for path, lines in pages.items():
        pinned = sum(1 for line in lines if PIN.match(line))
        print(f"{path.name:<15}: {len(headings(lines))} headings, "
              f"{pinned} pinned, {len(lines)} lines")
    print(f"language      : shipped {shipped}")
    print(f"controls      : {len(EXPECTED)} keys, both languages")
    print(f"\nVERDICT: {'PASS' if not failures else f'FAIL ({len(failures)})'}")
    if failures:
        if args.verbose or True:
            for item in failures:
                print(f"  - {item}")
    return 1 if failures else 0


def read(path: Path) -> list[str]:
    if not path.is_file():
        raise SystemExit(f"missing: {path}")
    return path.read_text(encoding="utf-8").splitlines()


if __name__ == "__main__":
    raise SystemExit(main())
