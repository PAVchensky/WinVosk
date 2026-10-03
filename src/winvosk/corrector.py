"""Replacing what the model heard with the user's own words, when they are close.

The small Russian model knows words like «дропбокс» — the vocabulary probe proves
that — and still prefers a different word or a different split for the same
sound. That is an ambiguity, not a gap, and a grammar cannot fix it: a grammar
is a hard restriction, so the decoder would only ever emit the listed words.

Nothing inside the vosk 0.3.45 API can bias a single word either: `SetWords`
takes a boolean and enables word timestamps, and there is no boosting call at
all. So the correction happens after the decode, on the finished utterance and
only there. Measured cost is about 1 ms for a twelve word phrase, against the
20 ms the typer already pauses after every revision, and it runs in the
recogniser worker thread, never in the PortAudio callback.

A split is the same kind of ambiguity, and it needs one step of its own. The
model gives «друг бокс» for «дропбокс»: two tokens where one entry is, so no
token can ever match it, and a 0.333 and a 0.667 are both below the cutoff.
Neighbouring tokens are therefore glued without a space and compared as one
word: 0.75, which is exactly the cutoff, and the pair is replaced. Only forward
order, only when both halves are at least JOIN_MIN letters, and the same
inflection guard as a single word — «с» + «воих» never becomes «своих».

What stays broken: a split into three tokens. For «йо цун фэнь» the first pair
scores 0.714 and is left alone, the second scores 0.875 and fires, and the
result is «йо йоцунфэнь» — recognisable, but not what was meant. Widening the
glue to three tokens is the fix for that, and it is deliberately not done until
a real word needs it.

Partial results are left alone on purpose. They are typed as they arrive and the
final utterance is diffed against them, so correcting only the finished text
costs a few Backspaces at worst and keeps what is on screen stable while the
model is still thinking.
"""

from __future__ import annotations

import difflib
import logging

log = logging.getLogger(__name__)

# Where the cutoff sits, and why. Measured on this machine, not guessed:
# a dropped letter scores about 0.93 and a wrong consonant about 0.80, so 0.85
# fixes the first class and misses the second, which is the class users notice.
# 0.75 catches both. What it costs: over 138 real words from logs\*.txt, nothing
# was replaced at 0.70, and against a 500 word list of random tokens the false
# replacement rate is about 0.03%. It is a constant, not a setting, because the
# answer depends on the machine and the word list rather than on the user.
CUTOFF = 0.75

# Below this a word carries too little to compare safely, and short words are
# where a wrong correction is most likely to be invisible and most annoying.
MIN_LENGTH = 4

# How long each half of a glued pair has to be. Three is the point where the
# Russian case that matters is closed: «с» + «воих» must not become a listed
# «своих», and no pair that does reach the cutoff is shorter than that. What it
# costs: over the 138 neighbouring pairs in logs\*.txt, nothing was glued and
# no line changed.
JOIN_MIN = 3


def _closest(word: str, words: list[str], cutoff: float) -> str | None:
    """The listed word `word` should become, or None to leave it alone.

    One place for the three ways a comparison ends without a replacement: no
    match at all, an exact hit, and a word that begins with the listed one. The
    last is an inflection — «дропбоксы» for «дропбокс» — and Russian inflects
    heavily, so folding it back to the bare form would be wrong more often
    than right. Add the forms you actually say to the list instead.
    """
    close = difflib.get_close_matches(word, words, n=1, cutoff=cutoff)
    if not close:
        return None
    if close[0] == word or word.startswith(close[0]):
        return None
    return close[0]


def correct(text: str, words: list[str], cutoff: float = CUTOFF) -> tuple[str, list[tuple[str, str]]]:
    """The text with close matches replaced, and every replacement made.

    One pass over the tokens, left to right, and the longest match wins: two
    neighbours are tried as one glued word first, then the token on its own. A
    pair that fires takes both tokens with it, which is the stronger signal —
    two words of the utterance agree with one entry — so it is not held back
    for a correction the second token might have had. Forward order only, so
    «бокс друг» is left as it is.
    """
    if not text or not words:
        return text, []
    tokens = text.split()
    if not tokens:
        return text, []
    replacements: list[tuple[str, str]] = []
    fixed: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        following = tokens[index + 1] if index + 1 < len(tokens) else ""
        glued = ""
        if len(token) >= JOIN_MIN and len(following) >= JOIN_MIN:
            glued = _closest(token + following, words, cutoff)
        if glued:
            replacements.append((f"{token} {following}", glued))
            fixed.append(glued)
            index += 2
            continue
        if len(token) >= MIN_LENGTH:
            close = _closest(token, words, cutoff)
            if close:
                replacements.append((token, close))
                token = close
        fixed.append(token)
        index += 1
    return " ".join(fixed), replacements


def describe(replacements: list[tuple[str, str]]) -> str:
    """One log line's worth of what was corrected: `дропбок -> дропбокс`.

    A glued pair keeps its space, so a split reads as `друг бокс -> дропбокс`
    and the log says in one glance that the model split the word.
    """
    return ", ".join(f"{heard} -> {word}" for heard, word in replacements)