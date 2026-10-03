"""Headless probe for the own-word correction pass.

Pure logic: no model, no microphone, no GUI, so it runs unattended in a
fraction of a second. It pins the behaviour that matters — a near miss becomes
the user's word, a word the model split across a space is glued back into it,
and an ordinary word never does — because a correction that replaces a word the
model got right is worse than one that never fires.

Run it from the project root:

    .\\.venv\\Scripts\\python.exe .\\tools\\correct_probe.py
"""

import difflib
import logging
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

from winvosk import config, corrector, settings, vocabulary

WORDS = [
    "дропбокс",
    "фейсбук",
    "телеграм",
    "эмодзи",
    "йоцунфэнь",
]

# heard -> expected, after correction
CASES = [
    ("дропбок", "дропбокс"),                  # a dropped letter, about 0.93
    ("топбокс", "дропбокс"),                  # a wrong consonant, about 0.80
    ("дропбокс", "дропбокс"),                 # already right, must stay
    ("дропбокс сиди", "дропбокс сиди"),       # in the middle of a sentence
    ("положи файл в дропбокс", "положи файл в дропбокс"),
    ("фейсбук мессенджер", "фейсбук мессенджер"),
    ("молоко и хлеб", "молоко и хлеб"),        # nothing near the list
    ("подбоксник", "подбоксник"),             # similar, but its own word
    ("дропбоксы", "дропбоксы"),               # an inflection, not a mistake
    ("в фейсбука", "в фейсбука"),
    ("я присел", "я присел"),                 # short tokens are left alone
    ("друг бокс", "дропбокс"),                # the split, about 0.75 glued
    ("положи это в друг бокс", "положи это в дропбокс"),
    ("дру бокс там лежит", "дропбокс там лежит"),
    ("и друг", "и друг"),                     # two ordinary words, not a split
    ("бокс друг", "бокс друг"),               # glued forward only, never backward
    ("друг боксы", "друг боксы"),             # an inflected split, 0.71, left alone
    ("теле грам", "теле грам"),               # the join lands on the entry itself
]

# What the cutoff buys, at the cost of each rung: a higher one stops catching
# the wrong consonant, a lower one has to keep leaving ordinary words alone.
CUTOFF_TABLE = [
    ("дропбок", 0.75, "дропбокс"),
    ("дропбок", 0.90, "дропбокс"),
    ("топбокс", 0.75, "дропбокс"),
    ("топбокс", 0.85, "топбокс"),
    ("подбоксник", 0.75, "подбоксник"),
    ("подбоксник", 0.60, "подбоксник"),
    ("дропбоксник", 0.85, "дропбоксник"),
    ("дропбоксик", 0.85, "дропбоксик"),
    ("друг бокс", 0.75, "дропбокс"),      # the glue sits on the cutoff
    ("друг бокс", 0.85, "друг бокс"),
    ("друг боксы", 0.70, "дропбокс"),     # 0.71: just under, needs a lower one
    ("друг боксы", 0.75, "друг боксы"),
]

# What the glue between two tokens refuses. The first row is the one JOIN_MIN
# exists for: two letters is not enough of a word, so the pair stays two words
# even though the glued form scores exactly the cutoff.
JOIN_GUARDS = [
    ("др угбокс", "др угбокс"),            # fires only if JOIN_MIN drops to 2
    ("бокс друг", "бокс друг"),            # glued forward only, never backward
    ("друг бокс", "дропбокс"),
    ("друг боксы", "друг боксы"),          # 0.71, an inflected split, left alone
    ("теле грам", "теле грам"),            # the join lands on the entry itself
    ("положи в друг бокс", "положи в дропбокс"),
]


def case_replacements() -> bool:
    print("\ncase 1: what is heard becomes what the user wrote", flush=True)
    ok = True
    for heard, expected in CASES:
        fixed, replaced = corrector.correct(heard, WORDS)
        good = fixed == expected
        ok = ok and good
        detail = ", ".join(f"{a} -> {b}" for a, b in replaced) or "-"
        print(f"  {heard:24s} -> {fixed:24s} {detail:28s} {good}", flush=True)
    return ok


def case_no_false_positives() -> bool:
    print("\ncase 2: an empty list and a wrong cutoff change nothing", flush=True)
    plain = "дропбок в дропбокс"
    empty = corrector.correct(plain, [])
    print(f"  no word list      -> {empty[0]!r}", flush=True)
    text, replaced = empty
    ok = text == plain and not replaced

    text, replaced = corrector.correct(plain, WORDS, cutoff=1.0)
    print(f"  cutoff 1.0        -> {text!r} {replaced}", flush=True)
    ok = ok and text == "дропбок в дропбокс" and replaced == []

    text, _ = corrector.correct(plain, WORDS, cutoff=0.4)
    print(f"  cutoff 0.4        -> {text!r}", flush=True)
    ok = ok and text == "дропбокс в дропбокс"
    return ok


def case_cutoff_boundary() -> bool:
    print("\ncase 3: what each cutoff buys and what it costs", flush=True)
    ok = True
    for heard, cutoff, expected in CUTOFF_TABLE:
        fixed = corrector.correct(heard, WORDS, cutoff=cutoff)[0]
        good = fixed == expected
        ok = ok and good
        print(f"  {heard:12s} at {cutoff:.2f} -> {fixed:12s} expected "
              f"{expected:12s} {good}", flush=True)
    print(f"  the shipped cutoff is {corrector.CUTOFF:.2f}", flush=True)
    return ok and corrector.CUTOFF == 0.75


def case_edge_cases() -> bool:
    print("\ncase 4: empty input and single letters", flush=True)
    ok = True
    for text in ("", "   ", "а", "да нет"):
        fixed, replaced = corrector.correct(text, WORDS)
        good = fixed == text and not replaced
        ok = ok and good
        print(f"  {text!r:12s} -> {fixed!r:12s} {good}", flush=True)
    return ok


def case_join_guards() -> bool:
    print("\ncase 5: what the glue between two tokens refuses", flush=True)
    ok = True
    for heard, expected in JOIN_GUARDS:
        fixed, replaced = corrector.correct(heard, WORDS)
        good = fixed == expected
        ok = ok and good
        detail = ", ".join(f"{a} -> {b}" for a, b in replaced) or "-"
        print(f"  {heard:24s} -> {fixed:24s} {detail:28s} {good}", flush=True)
    score = difflib.SequenceMatcher(None, "другбокс", "дропбокс").ratio()
    print(f"  glued 'другбокс' scores {score:.3f} against a cutoff of "
          f"{corrector.CUTOFF:.2f}, JOIN_MIN is {corrector.JOIN_MIN}", flush=True)
    return ok and corrector.JOIN_MIN == 3 and score >= corrector.CUTOFF


def case_own_words() -> bool:
    print("\ncase 6: phrases.txt gives the corrector only single words", flush=True)
    phrases = vocabulary.load(config.PHRASES_FILE)
    words = vocabulary.own_words(config.PHRASES_FILE)
    print(f"  phrases           : {phrases}", flush=True)
    print(f"  corrector words   : {words}", flush=True)
    ok = all(" " not in word for word in words)
    ok = ok and words == [word for word in phrases if " " not in word]
    print(f"  multi-word entries excluded: {ok}", flush=True)
    return ok


def case_cost() -> bool:
    print("\ncase 7: cost against the 20 ms the typer already pauses", flush=True)
    sentence = "положи все фотографии в дропбокс и отправь их в телеграм"
    reps = 2000
    start = time.perf_counter()
    for _ in range(reps):
        corrector.correct(sentence, WORDS)
    per_call = (time.perf_counter() - start) / reps
    per_sentence = per_call * 1000
    share = per_sentence / (config.TYPE_DELAY * 1000) * 100
    print(f"  {len(sentence.split())} word sentence: {per_sentence:.3f} ms", flush=True)
    print(f"  TYPE_DELAY is {config.TYPE_DELAY * 1000:.0f} ms, "
          f"so one correction is {share:.1f}% of one revision pause", flush=True)
    return per_sentence < 5.0


class StubPanel:
    """Stands in for the Tk panel so the app can be driven without a window."""

    def __init__(self) -> None:
        self.texts: list[tuple[str, str]] = []

    def set_text(self, text: str, partial: str) -> None:
        self.texts.append((text, partial))


def case_app_wiring() -> bool:
    print("\ncase 8: the app corrects the finished utterance, never a partial",
          flush=True)
    import run  # imports Tk, pystray and vosk as modules, but builds no window

    original = settings.SETTINGS_FILE
    with tempfile.TemporaryDirectory(prefix="winvosk_correct_probe_") as work:
        settings.SETTINGS_FILE = Path(work) / "settings.json"
        settings.save({"correct_words": True})
        try:
            app = run.App.__new__(run.App)
            app._session = run.Session()
            app._panel = StubPanel()
            app._words = vocabulary.own_words(config.PHRASES_FILE)
            app._on_partial({"text": "топбокс"})
            after_partial = app._panel.texts[-1]
            app._on_partial({"text": "друг бокс"})
            after_split_partial = app._panel.texts[-1]
            app._on_utterance({"text": "топбокс и дропбок в друг бокс"})
            after_utterance = app._panel.texts[-1]
        finally:
            settings.SETTINGS_FILE = original

    print(f"  partial kept as heard : {after_partial[1]!r}", flush=True)
    print(f"  split partial as heard: {after_split_partial[1]!r}", flush=True)
    print(f"  utterance corrected   : {after_utterance[0]!r}", flush=True)
    print(f"  corrections counted   : {app._session.corrections}", flush=True)
    return (
        after_partial[1] == "топбокс"
        and after_split_partial[1] == "друг бокс"
        and after_utterance[0] == "дропбокс и дропбокс в дропбокс"
        and app._session.corrections == 3
    )


def main() -> None:
    results = [
        case_replacements(),
        case_no_false_positives(),
        case_cutoff_boundary(),
        case_edge_cases(),
        case_join_guards(),
        case_own_words(),
        case_cost(),
        case_app_wiring(),
    ]
    print(f"\n{sum(results)}/{len(results)} check group(s) passed", flush=True)
    print(f"VERDICT: {'PASS' if all(results) else 'FAIL'}", flush=True)
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()