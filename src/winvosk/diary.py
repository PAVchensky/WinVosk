r"""The dictation history: one dated file under logs\, and the reader for it.

Two directions, one format. `append` writes `[HH:MM:SS] text` a line at a time
into `logs\<yyyy-mm-dd>.txt`, and `recent` reads those files back newest first.

The switch lives here rather than at the call site in `run.py`: one gate that the
next caller cannot forget is worth more than a `diary` that stays free of
`settings`, and the import is legal because nothing in `settings` imports
`diary`. It governs what is written from now on — files already on disk are
never touched, which is why the history tab keeps showing them while the switch
is off.

Reading is deliberately forgiving, because these files are written by one process
over months and read by another: a line being appended right now has no newline
yet, a hand edited file holds a line that is not a record, and a file from a
machine that was killed mid-write does not decode. Each of those costs the one
line or the one file it broke and never the list.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple

from . import config, settings

log = logging.getLogger(__name__)

# Only the dated files are history. `logs\` also holds `app.log`, its rotated
# copies and `report.txt`, and a glob of `*.txt` would read the last two as if
# they were somebody talking.
RECORD_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}\.txt$")
RECORD_LINE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s*(.*)$")


class Entry(NamedTuple):
    """One finished session, as the history tab shows it.

    `day` and `stamp` are kept apart rather than parsed into one datetime because
    the tab renders them differently: a record from today needs the time alone,
    and one from any other day needs the day as well.
    """

    day: date
    stamp: str
    text: str


def path_for(day: date | None = None) -> Path:
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return config.LOGS_DIR / f"{(day or date.today()).isoformat()}.txt"


def append(text: str) -> bool:
    """Add one finished session to today's file. False means nothing was written.

    Reads the switch from disk rather than taking it as an argument, so a caller
    cannot record a session the user has switched off recording of.
    """
    if not settings.history_enabled():
        log.info("history is off, this session is not recorded")
        return False
    cleaned = text.strip()
    if not cleaned:
        return False
    target = path_for()
    stamp = datetime.now().strftime("%H:%M:%S")
    try:
        with target.open("a", encoding="utf-8") as handle:
            handle.write(f"[{stamp}] {cleaned}\n")
    except OSError:
        log.exception("could not write to %s", target)
        return False
    return True


def recent(limit: int = config.HISTORY_RECENT) -> list[Entry]:
    """The last `limit` records, newest first.

    Files newest-first — the names are ISO dates, so sorting by name is sorting
    by day — and lines last-first within each, so the list comes out in the order
    it is displayed with no reversal at the end. Reading stops at the limit: a
    diary with a year of records must not be read in full to answer a question
    about ten of them.
    """
    if limit <= 0:
        return []
    found: list[Entry] = []
    for path in _record_files():
        for entry in reversed(_read(path)):
            found.append(entry)
            if len(found) >= limit:
                return found
    return found


def _record_files() -> list[Path]:
    r"""The dated files under `logs\`, newest first."""
    try:
        found = [path for path in config.LOGS_DIR.iterdir()
                 if RECORD_NAME.match(path.name)]
    except FileNotFoundError:
        # No `logs\` yet is an ordinary state, not an error: nothing has been
        # recorded and nothing has gone wrong.
        return []
    except OSError:
        log.warning("could not list %s", config.LOGS_DIR, exc_info=True)
        return []
    return sorted(found, key=lambda path: path.name, reverse=True)


def _read(path: Path) -> list[Entry]:
    """Every record in one file, oldest first.

    `utf-8-sig` and `errors="replace"` because the file is the app's own but has
    outlived several editors: a byte order mark must not make the first record
    unreadable, and a stray byte must not cost the file.
    """
    try:
        raw = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        log.warning("could not read %s", path, exc_info=True)
        return []
    try:
        day = date.fromisoformat(path.stem)
    except ValueError:
        # Only reachable if the name matched something `date` will not take, and
        # RECORD_NAME already promised otherwise. Cheap, and it keeps `Entry`
        # from holding a day that does not exist.
        log.warning("%s is not a dated file after all", path.name)
        return []
    entries: list[Entry] = []
    for line in raw.splitlines():
        # A line without a trailing newline is a write in progress, and it is
        # still a record: refusing to show it would hide the newest thing said.
        found = RECORD_LINE.match(line)
        if found is None:
            continue
        said = found.group(2).strip()
        if said:
            entries.append(Entry(day, found.group(1), said))
    return entries