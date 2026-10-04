"""Headless regression probe for the dictation history: the reader and the gate.

Everything here is pure logic on files in a temporary directory: no Tk, no
microphone, no model load and no real hook, so it runs unattended in a fraction
of a second. `config.LOGS_DIR` and `settings.SETTINGS_FILE` are pointed at that
directory, so the probe never reads or writes the machine's real `logs\\` and
leaves nothing behind.

The cases are the states a diary is actually found in: several days, a record
being written right now, a hand edited line, a file that does not decode, and
the two files that share the folder with it and are not history.

The fixture text is ASCII on purpose. A probe that cannot print the line that
failed is a probe that has to be run twice, and the one thing it does check in
Cyrillic is written with escapes so the comparison cannot depend on how the file
was saved.

Run it from the project root:

    .\\.venv\\Scripts\\python.exe .\\tools\\history_probe.py
"""

import logging
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

from winvosk import config, diary, settings

# Three days of records, oldest first, so every case can say what the answer has
# to be rather than what the reader returned.
DAYS = [date.today() - timedelta(days=2), date.today() - timedelta(days=1),
        date.today()]

# What each of the three files holds, as it is written to disk, and what the
# reader has to make of it. The line without a timestamp is the hand edited one:
# it is in the file and it is not a record.
LINES_OLDEST = ["[08:00:00] first record", "no timestamp on this one",
                "[08:05:00] second record"]
LINES_MIDDLE = ["[09:00:00] third record"]
LINES_NEWEST = ["[10:00:00] fourth record", "[10:01:00] fifth record",
                "[10:02:00] sixth record"]

TEXT_OLDEST = ["first record", "second record"]
TEXT_MIDDLE = ["third record"]
TEXT_NEWEST = ["fourth record", "fifth record", "sixth record"]

# What `recent(50)` has to answer, newest first.
EVERY = TEXT_NEWEST[::-1] + TEXT_MIDDLE + TEXT_OLDEST[::-1]

# The same line as the real app writes it, spelled out rather than pasted in, so
# the round trip through the file is proved without depending on this file's own
# encoding. "четвёртая запись" is the record `append` adds below.
RUSSIAN = "\u0447\u0435\u0442\u0432\u0451\u0440\u0442\u0430\u044f \u0437\u0430\u043f\u0438\u0441\u044c"


def _write(folder: Path, day: date, lines: list[str], *, newline: bool = True,
           bom: bool = False) -> Path:
    """One dated file, exactly as `diary.append` would have left it."""
    target = folder / f"{day.isoformat()}.txt"
    body = "\n".join(lines)
    if newline:
        body += "\n"
    target.write_text(body, encoding="utf-8-sig" if bom else "utf-8")
    return target


def _lay_out(folder: Path) -> None:
    """A diary with everything in it, including everything that is not history.

    Three days, three records on the oldest. That file also carries a line that
    is not a record and a byte order mark, because both are cheap to write by
    hand and neither is worth a day of debugging in the field. `app.log`,
    `app.log.1` and `report.txt` share the folder and must never be read: the
    first of them is the app's own log, and reading it would answer the question
    with lines of somebody else's log.
    """
    folder.mkdir(parents=True, exist_ok=True)
    _write(folder, DAYS[0], LINES_OLDEST, bom=True)
    _write(folder, DAYS[1], LINES_MIDDLE)
    # No trailing newline on the last file: a write that is still in progress.
    _write(folder, DAYS[2], LINES_NEWEST, newline=False)
    (folder / "2020-01-01.txt").write_text("", encoding="utf-8")
    for other in ("app.log", "app.log.1", "report.txt"):
        (folder / other).write_text("[10:00:00] NOT A RECORD\n", encoding="utf-8")


def case_reader(work: Path, results: list[bool]) -> None:
    print("\ncase 1: the reader skips everything that is not a record", flush=True)
    config.LOGS_DIR = work / "logs"
    _lay_out(config.LOGS_DIR)
    entries = diary.recent(50)
    said = [entry.text for entry in entries]
    print(f"  found {len(entries)} record(s): {said}", flush=True)
    days = {entry.day.isoformat() for entry in entries}
    checks = {
        "six records out of seven timed lines": len(entries) == 6,
        "a line with no timestamp is skipped": LINES_OLDEST[1] not in said,
        "a byte order mark costs no record": said[-1] == TEXT_OLDEST[0],
        "an empty dated file contributes nothing": "2020-01-01" not in days,
        "app.log is not a diary": all(
            "NOT A RECORD" not in text for text in said),
    }
    for label, good in checks.items():
        print(f"    {label:42s} {good}", flush=True)
    results.append(all(checks.values()))

    print("\ncase 2: newest first, across days", flush=True)
    stamps = [(entry.day.isoformat(), entry.stamp) for entry in entries]
    print(f"  {stamps}", flush=True)
    ok = stamps == sorted(stamps, reverse=True) and said == EVERY
    print(f"  the order is newest first: {ok}", flush=True)
    results.append(ok)

    print("\ncase 3: the limit stops the read", flush=True)
    ok = True
    for limit, wanted in ((3, EVERY[:3]), (1, EVERY[:1]), (6, EVERY[:6]),
                          (50, EVERY)):
        got = [entry.text for entry in diary.recent(limit)]
        good = got == wanted
        print(f"  recent({limit:2d}) -> {len(got)} record(s), first={got[:1]} "
              f"want {len(wanted)} {good}", flush=True)
        ok = ok and good
    # A limit of nothing is nothing, not everything: a caller that computes a
    # limit and gets zero must not be handed the whole diary.
    empty = diary.recent(0)
    negative = diary.recent(-1)
    print(f"  recent(0) and recent(-1) are empty, not everything: "
          f"{empty == [] and negative == []}", flush=True)
    results.append(ok and empty == [] and negative == [])

    print("\ncase 4: no folder at all is no history, not an error", flush=True)
    config.LOGS_DIR = work / "absent"
    got = diary.recent(10)
    print(f"  recent(10) with no logs\\ : {got}", flush=True)
    results.append(got == [])


def case_gate(work: Path, results: list[bool]) -> None:
    print("\ncase 5: the switch governs what is written, and only that",
          flush=True)
    logs = work / "gate"
    config.LOGS_DIR = logs
    settings.SETTINGS_FILE = work / "gate.json"
    try:
        today = logs / f"{date.today().isoformat()}.txt"
        settings.save({"write_history": False})
        wrote = diary.append("must not reach the file")
        off = not wrote and not today.exists()
        print(f"  switch off: append returned {wrote}, file created "
              f"{today.exists()} {off}", flush=True)

        settings.save({"write_history": True})
        wrote = diary.append("  and this one must  ")
        line = today.read_text(encoding="utf-8").strip()
        on = wrote and line.endswith("and this one must")
        print(f"  switch on : append returned {wrote}, line {line!r} {on}",
              flush=True)

        # Whitespace is not a record, whichever way the switch stands.
        blank = diary.append("   ")
        print(f"  blank text is not a record: {blank is False}", flush=True)
        results.append(off and on and blank is False)

        print("\ncase 6: a record in Russian survives the round trip", flush=True)
        wrote = diary.append(RUSSIAN)
        body = today.read_text(encoding="utf-8")
        kept = RUSSIAN in body
        print(f"  append returned {wrote}, {RUSSIAN!r} is in the file: {kept}",
              flush=True)
        said = [entry.text for entry in diary.recent(10)]
        read_back = said and said[0] == RUSSIAN
        print(f"  and the reader gives it back unchanged: {read_back}",
              flush=True)
        results.append(wrote and kept and read_back)

        print("\ncase 7: the records already on disk survive the switch",
              flush=True)
        settings.save({"write_history": False})
        still = [entry.text for entry in diary.recent(10)]
        print(f"  recent(10) with the switch off: {still[:1]} and "
              f"{len(still)} more {still[:1] == [RUSSIAN]}", flush=True)
        results.append(still[:1] == [RUSSIAN] and len(still) == 2)
    finally:
        settings.SETTINGS_FILE = config.BASE_DIR / "settings.json"


def main() -> None:
    results: list[bool] = []
    original = config.LOGS_DIR
    work = Path(tempfile.mkdtemp(prefix="winvosk_history_probe_"))
    try:
        case_reader(work, results)
        case_gate(work, results)
    finally:
        config.LOGS_DIR = original
        settings.SETTINGS_FILE = config.BASE_DIR / "settings.json"
        shutil.rmtree(work, ignore_errors=True)
    passed = all(results)
    print(f"\n{sum(results)}/{len(results)} check group(s) passed", flush=True)
    print(f"VERDICT: {'PASS' if passed else 'FAIL'}", flush=True)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()