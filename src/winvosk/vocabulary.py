"""Which of the user's own words can the loaded model actually hear?

The second Habr article adds words to a vosk model offline, by rebuilding
Gr.fst and HCLr.fst with a Kaldi build (Linux, srilm, irstlm, phonetisaurus).
That is not something this app can do on the fly, but it still answers a
question: which of your terms does the model already know. Vosk reports the
rest itself, as "Ignoring word missing in vocabulary", while a recogniser is
built with a phrase list, so the answer is read straight from its log.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import tempfile
from pathlib import Path

import vosk

log = logging.getLogger(__name__)

_MISSING = re.compile(r"Ignoring word missing in vocabulary: '([^']+)'")


def load(path: Path) -> list[str]:
    """Read phrases from a plain text file, one per line, # starts a comment."""
    if not path.is_file():
        return []
    phrases: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip().lower()
        if line and line not in phrases:
            phrases.append(line)
    return phrases


def own_words(path: Path) -> list[str]:
    """The single-word entries: what the corrector may replace a token with.

    A multi-word entry exists for `--vocab-check`, which asks vosk about whole
    phrases, and cannot ever match one token of recognised text.
    """
    return [phrase for phrase in load(path) if " " not in phrase]


def _capture_console(function) -> str:
    """Run function with the C level stderr redirected to a temporary file.

    Vosk writes through the native layer, so contextlib.redirect_stderr and a
    pipe would both miss it. Only the file descriptor is replaced here.
    """
    with tempfile.TemporaryFile(mode="w+b") as sink:
        saved = os.dup(2)
        try:
            os.dup2(sink.fileno(), 2)
            function()
        finally:
            os.dup2(saved, 2)
            os.close(saved)
        sink.seek(0)
        return sink.read().decode("utf-8", errors="replace")


def missing_words(model_path: Path, phrases: list[str]) -> tuple[list[str], list[str]]:
    """Split phrases into the ones the model knows and the ones it does not."""
    return split_by_model(vosk.Model(str(model_path)), phrases)


def split_by_model(model, phrases: list[str]) -> tuple[list[str], list[str]]:
    """The same split, against a model that is already loaded.

    Loading a second `vosk.Model` costs the model's whole memory again, so the
    running app asks about its own model through this instead. Only a grammar
    recogniser is built on top of it, which is a few hundred kilobytes.
    """
    if not phrases:
        return [], []
    grammar = json.dumps(phrases, ensure_ascii=False)

    def build() -> None:
        try:
            vosk.KaldiRecognizer(model, 16000, grammar)
        except Exception:
            log.debug("grammar probe failed", exc_info=True)

    output = _capture_console(build)
    rejected = {match.lower() for match in _MISSING.findall(output)}
    known = [phrase for phrase in phrases if phrase not in rejected]
    return known, [phrase for phrase in phrases if phrase in rejected]


def report_lines(path: Path, known: list[str], missing: list[str]) -> list[str]:
    """The own-word report, one source for `--vocab-check` and the panel.

    Kept here rather than in either caller so the console report and the dialog
    cannot drift apart, and so the wording lives next to the check it describes.
    """
    total = len(known) + len(missing)
    lines = [
        f"phrases file: {path}  ({total} phrase(s))",
        f"heard by the model : {len(known)}",
    ]
    lines += [f"  ok      {phrase}" for phrase in known]
    lines.append(f"unknown to the model: {len(missing)}")
    lines += [f"  MISSING {phrase}" for phrase in missing]
    if missing:
        lines += [
            "",
            "Words the model has never heard cannot be fixed at runtime.",
            "They need a language model rebuild, see README.md, section",
            '"Custom vocabulary", which needs a Kaldi build on Linux.',
        ]
    return lines


def empty_report_lines(path: Path, example_1: str, example_2: str) -> list[str]:
    """What to say when there is nothing to check, in the interface language."""
    return [
        f"no phrases in {path}",
        "add one phrase per line, for example:",
        f"    {example_1}",
        f"    {example_2}",
    ]
