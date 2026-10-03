"""Appends every finished dictation to a dated file under logs/."""

from __future__ import annotations

import logging
from datetime import date, datetime

from . import config

log = logging.getLogger(__name__)


def path_for(day: date | None = None) -> "config.Path":
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return config.LOGS_DIR / f"{(day or date.today()).isoformat()}.txt"


def append(text: str) -> bool:
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
