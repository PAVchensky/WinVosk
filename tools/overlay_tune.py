"""Live tuner for the recording chip: change the numbers, see the chip at once.

The chip's geometry lives in module level constants in
`winvosk/overlay.py`, so changing any of them means editing the source
and restarting the application. That loop is slow, and the result is hard to
judge, because the chip is only on screen while a recording is running. This
tool makes it a single window: every tunable constant is an entry, the preview
is a real `RecordingOverlay`, and a change is on screen within a tick.

The preview is the application's own rendering path, not a copy of it. The
constants are written onto the imported module, the bell shares are recomputed
the way the module computed them at import, and the window is rebuilt through
`RecordingOverlay.show`. What is on screen is therefore what the application
would draw, including the Pillow plate, the five rectangles per bar and the same
`next_level` contract.

Nothing here belongs to the application: no hotkey hook, no microphone unless
the microphone source is picked on purpose, no model load, and the single
instance mutex is not touched. Logging goes to the console only, never to
`logs\\app.log`, because this tool is not part of the verification bar.

Values are read from `overlay.py` with `ast` and can be written back to it, so
the file keeps its own layout and comments. Anything the tool writes there takes
effect in the application only after a restart: a running process has already
imported the module and its constants are read while the chip is built.

Run it from the project root:

    .\\.venv\\Scripts\\python.exe .\\tools\\overlay_tune.py

and the headless half, which checks the geometry arithmetic without a window:

    .\\.venv\\Scripts\\python.exe .\\tools\\overlay_tune.py --self-test
"""

from __future__ import annotations

import ast
import logging
import math
import re
import sys
import threading
import time
import tkinter as tk
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

from winvosk import overlay as ov

SOURCE = Path(ov.__file__).resolve()

# Consolas declares a win ascent of 1901 and a win descent of 483 over an em of
# 2048, so a point size becomes pixels at 96 dpi and then a line box of
# size * 96 / 72 * 2384/2048. The tuner measures the real line box with Tk and
# only uses this factor where there is no interpreter at all, which is the self
# test.
_CLOCK_LINE_FACTOR = 2384 / 2048

_DEBOUNCE_MS = 300
_READOUT_MS = 120


@dataclass(frozen=True)
class Field:
    """One editable constant, and how to read it back out of its entry."""

    attr: str
    kind: str  # int, float, text
    label: str
    group: str
    minimum: float = 0.0
    maximum: float = 0.0

    def parse(self, raw: str) -> int | float | str:
        if self.kind == "text":
            return raw.strip()
        value = float(raw.strip().replace(",", "."))
        if not math.isfinite(value):
            raise ValueError("не конечное число")
        if self.kind == "int" and value != int(value):
            raise ValueError("не целое число")
        number: int | float = int(value) if self.kind == "int" else value
        if number < self.minimum:
            raise ValueError(f"меньше {self.minimum:g}")
        if self.maximum and number > self.maximum:
            raise ValueError(f"больше {self.maximum:g}")
        return number


# The groups are in the order they appear in the window. Everything in the first
# and the last group is read while the chip is being built, so a change there
# rebuilds the preview window; everything between them is read once per painted
# frame, so a change there lands on the next tick with no rebuild at all.
FIELDS: tuple[Field, ...] = (
    Field("WIDTH", "int", "WIDTH", "Геометрия", 8, 4000),
    Field("HEIGHT", "int", "HEIGHT", "Геометрия", 8, 4000),
    Field("BARS", "int", "BARS", "Геометрия", 3, 64),
    Field("BAR_WIDTH", "int", "BAR_WIDTH", "Геометрия", 1, 200),
    Field("BAR_GAP", "int", "BAR_GAP", "Геометрия", 0, 200),
    Field("BAR_TOP", "int", "BAR_TOP", "Геометрия", -200, 2000),
    Field("BAR_FIELD", "int", "BAR_FIELD", "Геометрия", 2, 4000),
    Field("CORNER", "int", "CORNER", "Геометрия", 0, 2000),
    Field("CLOCK_Y", "int", "CLOCK_Y", "Геометрия", -200, 2000),
    Field("MARGIN_ABOVE_TASKBAR", "int", "MARGIN_ABOVE_TASKBAR", "Геометрия", 0, 4000),
    Field("BAR_SPAN_MAX", "float", "BAR_SPAN_MAX", "Амплитуда"),
    Field("BAR_SPAN_MIN", "float", "BAR_SPAN_MIN", "Амплитуда"),
    Field("BAR_IDLE", "float", "BAR_IDLE", "Амплитуда"),
    Field("ATTACK", "float", "ATTACK", "Движение", 0.001, 1.0),
    Field("DECAY", "float", "DECAY", "Движение", 0.001, 1.0),
    Field("GATE", "float", "GATE", "Движение", 0.0, 1.0),
    Field("DRIVE", "float", "DRIVE", "Движение", 0.001, 100.0),
    Field("WOBBLE_REL", "float", "WOBBLE_REL", "Движение", 0.0, 1.0),
    Field("WOBBLE_ABS", "float", "WOBBLE_ABS", "Движение", 0.0, 10.0),
    Field("WOBBLE_STEP", "float", "WOBBLE_STEP", "Движение", 0.0, 10.0),
    Field("PHASE_SPREAD", "float", "PHASE_SPREAD", "Движение", 0.0, 100.0),
    Field("TICK_MS", "int", "TICK_MS", "Движение", 5, 2000),
    Field("_BAR_LOW", "text", "_BAR_LOW", "Вид"),
    Field("_BAR_MID", "text", "_BAR_MID", "Вид"),
    Field("_BAR_HIGH", "text", "_BAR_HIGH", "Вид"),
    Field("_CLOCK", "text", "_CLOCK", "Вид"),
    Field("_BACKGROUND", "text", "_BACKGROUND", "Вид"),
    Field("_BORDER", "text", "_BORDER", "Вид"),
    Field("_CLOCK_FONT", "text", "_CLOCK_FONT (семейство размер)", "Вид"),
    Field("_COLOR_KEY", "text", "_COLOR_KEY", "Вид"),
)

BY_ATTR = {field.attr: field for field in FIELDS}
REBUILD_ATTRS = frozenset(
    field.attr for field in FIELDS if field.group in {"Геометрия", "Вид"}
)
TUNABLE = frozenset(BY_ATTR)


def bell(distance: float) -> float:
    """A smooth bell, 1.0 at the centre bar and 0.0 at the outermost one.

    A copy of the module's own one line bell rather than an import of it, so the
    self test can check the arithmetic without pulling in tkinter and Pillow.
    The two have to stay the same formula; that is the price of a windowless
    check, and the self test is what would notice if they drifted apart.
    """
    return 0.5 * (1.0 + math.cos(math.pi * distance))


def bell_spans(bars: int, span_min: float, span_max: float) -> tuple[float, ...]:
    """The share of the energy each bar may take, exactly as the module makes it."""
    centre = (bars - 1) / 2
    return tuple(
        span_min + (span_max - span_min) * bell(abs(index - centre) / centre)
        for index in range(bars)
    )


def max_half_height(
    bar_idle: float,
    spans: tuple[float, ...],
    wobble_rel: float,
    wobble_abs: float,
) -> float:
    """The tallest a bar can ever get, in pixels above or below the centre line.

    This is the expression `_paint` builds for one bar, taken at its extremes:
    full drive, the centre bar, and the swing at +1 and at -1. A bar only ever
    approaches its goal through a first order lag, so the number is a real
    ceiling and is never passed at run time.
    """
    return max(
        bar_idle + 1.0 * (span * (1.0 + wobble_rel * swing) + wobble_abs * swing)
        for span in spans
        for swing in (step / 50 - 1 for step in range(101))
    )


def read_source(path: Path) -> dict[str, object]:
    """Every tunable constant, read from the file and not from the module.

    The file is the source of truth for what the numbers are, and reading it
    also reports which constants are missing instead of leaving them unset.
    """
    values: dict[str, object] = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id in TUNABLE:
            values[target.id] = ast.literal_eval(node.value)
    return values


def format_literal(value: object) -> str:
    """One constant's value as it should read in the source file."""
    if isinstance(value, bool):
        return repr(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, tuple):
        inner = ", ".join(format_literal(item) for item in value)
        return f"({inner},)" if len(value) == 1 else f"({inner})"
    return repr(str(value))


def split_comment(rhs: str) -> tuple[str, str]:
    """Split a right hand side into the value and a trailing comment.

    Splitting on `#` is wrong here, because a colour is a quoted string that
    starts with one. This walks the characters and only breaks outside quotes.
    """
    quote = ""
    for index, char in enumerate(rhs):
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == "#":
            return rhs[:index], rhs[index:]
    return rhs, ""


def write_source(path: Path, values: dict[str, object]) -> list[str]:
    """Put the tuned values into the module source, keeping its own layout."""
    text = path.read_text(encoding="utf-8")
    written: list[str] = []
    for name, value in values.items():
        match = re.compile(
            rf"^(\s*{re.escape(name)}\s*=\s*)([^\n]*)$", re.MULTILINE
        ).search(text)
        if match is None:
            written.append(f"{name}: НЕ НАЙДЕНО В ФАЙЛЕ, ПРОПУЩЕНО")
            continue
        comment = split_comment(match.group(2))[1]
        literal = format_literal(value)
        line = f"{match.group(1)}{literal}{comment}"
        if line == match.group(0):
            continue
        text = text[: match.start()] + line + text[match.end() :]
        written.append(f"{name} = {literal}")
    path.write_text(text, encoding="utf-8")
    return written


class FakeSpeech:
    """A level source with no microphone behind it, for judging the animation.

    The engine hands the chip one level every 31 ms and None whenever the
    decoder outruns it, so this does both: a shape that rises and falls in
    bursts with real pauses between them, and a None every seventeenth call.
    `GATE`, `DRIVE` and the attack and decay only mean something against
    something that behaves like speech, and a sine wave is not it.
    """

    def __init__(self) -> None:
        self._t0 = time.monotonic()
        self._ticks = 0
        self.mode = "речь"
        self.last: float | None = None

    def next_level(self) -> float | None:
        elapsed = time.monotonic() - self._t0
        self._ticks += 1
        if self.mode == "тишина":
            level = 0.0
        elif self.mode == "ровный":
            level = 0.35
        else:
            level = self._speech(elapsed)
        if self._ticks % 17 == 0:
            self.last = None
            return None
        self.last = level
        return level

    def _speech(self, elapsed: float) -> float:
        """About 2.4 s of syllables, then a pause, over and over.

        The peak sits near 0.55 of full scale, which is where ordinary speech
        lands as a raw PCM peak, so the default `DRIVE` of 3.0 brings the
        animation across its whole range without pinning it at the top.
        """
        phase = elapsed % 3.0
        if phase >= 2.4:
            return 0.0
        syllables = 0.5 - 0.5 * math.cos(2 * math.pi * 3.1 * phase)
        jitter = 0.06 * math.sin(2 * math.pi * 17.0 * elapsed)
        return min(1.0, max(0.0, 0.16 + 0.34 * syllables + jitter))


class Microphone:
    """A real level source, for judging `GATE` and `DRIVE` against real speech.

    Optional, and imported on demand because it pulls in sounddevice and vosk.
    While the application is running it holds the microphone itself, and a second
    stream on the same device either fails or degrades both, so this reports
    that rather than fighting for it.
    """

    def __init__(self) -> None:
        import sounddevice as sd

        from winvosk import config, recognizer

        self._levels_from_block = recognizer.levels_from_block
        self._levels: deque[float] = deque(maxlen=64)
        self._lock = threading.Lock()
        self.last: float | None = None
        self._stream = sd.RawInputStream(
            samplerate=config.SAMPLE_RATE,
            blocksize=config.BLOCK_SIZE,
            device=config.MIC_DEVICE,
            channels=1,
            dtype="int16",
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            logging.debug("microphone status: %s", status)
        with self._lock:
            self._levels.extend(self._levels_from_block(indata))

    def next_level(self) -> float | None:
        with self._lock:
            level = self._levels.popleft() if self._levels else None
        self.last = level
        return level

    def close(self) -> None:
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            logging.debug("cannot close the microphone stream", exc_info=True)


class Tuner:
    """The control window, and the chip preview it drives."""

    def __init__(self, source: FakeSpeech) -> None:
        self._root = tk.Tk()
        self._root.title("Чип записи — настройка")
        self._fake = source
        self._live: Microphone | None = None
        self._vars: dict[str, tk.StringVar] = {}
        self._overlay: ov.RecordingOverlay | None = None
        self._pending: str | None = None
        self._readout: str | None = None
        self._clock_font = tkfont.Font(root=self._root, font=ov._CLOCK_FONT)
        self._errors: list[str] = []
        self._warnings: list[str] = []
        self._defaults = read_source(SOURCE)

        self._at_bottom = tk.BooleanVar(value=True)
        self._build()
        self._apply(initial=True)

    # -- window ------------------------------------------------------------

    def _build(self) -> None:
        self._root.protocol("WM_DELETE_WINDOW", self._close)
        top = ttk.Frame(self._root, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Источник уровня:").pack(side="left")
        self._mode = tk.StringVar(value="речь")
        for mode in ("речь", "тишина", "ровный", "микрофон"):
            ttk.Radiobutton(
                top, text=mode, value=mode, variable=self._mode,
                command=self._switch_source,
            ).pack(side="left", padx=4)
        ttk.Checkbutton(
            top, text="чип внизу экрана, как в приложении",
            variable=self._at_bottom, command=self._place_preview,
        ).pack(side="left", padx=12)

        buttons = ttk.Frame(self._root, padding=(8, 0, 8, 4))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Сброс (из файла)", command=self._reset).pack(side="left")
        ttk.Button(buttons, text="Переставить", command=self._place_preview).pack(side="left", padx=4)
        ttk.Button(
            buttons, text=f"Записать в {SOURCE.name}", command=self._write
        ).pack(side="right")

        grid = ttk.Frame(self._root, padding=8)
        grid.pack(fill="both", expand=True)
        row = 0
        pair = 0
        group = ""
        for field in FIELDS:
            if field.group != group:
                if pair:
                    row, pair = row + 1, 0
                ttk.Label(
                    grid, text=field.group, font=("Segoe UI", 9, "bold")
                ).grid(row=row, column=0, columnspan=4, sticky="w", pady=(8, 2))
                row, group = row + 1, field.group
            if pair == 2:
                row, pair = row + 1, 0
            column = pair * 2
            ttk.Label(grid, text=field.label).grid(
                row=row, column=column, sticky="w", padx=(0, 4)
            )
            self._vars[field.attr] = tk.StringVar(
                value=self._text_of(self._defaults.get(field.attr))
            )
            entry = ttk.Entry(grid, textvariable=self._vars[field.attr], width=11)
            entry.grid(row=row, column=column + 1, sticky="w", padx=(0, 20))
            entry.bind("<KeyRelease>", self._schedule)
            for keys, step in (("<Up>", 1), ("<Down>", -1),
                               ("<Shift-Up>", 5), ("<Shift-Down>", -5)):
                entry.bind(
                    keys, lambda event, f=field, s=step: self._step(f, s)
                )
            pair += 1

        self._line = tk.Label(
            self._root, anchor="w", font=("Consolas", 9), padx=8, pady=4
        )
        self._line.pack(fill="x")
        self._report = tk.Text(self._root, height=8, wrap="word", font=("Consolas", 9))
        self._report.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    @staticmethod
    def _text_of(value: object) -> str:
        if isinstance(value, tuple):
            return " ".join(str(item) for item in value)
        if isinstance(value, float):
            return f"{value:.6g}"
        return "" if value is None else str(value)

    # -- input -------------------------------------------------------------

    def _step(self, field: Field, step: int) -> str:
        """Arrow keys nudge by a pixel, shift by five, which is the point."""
        if field.kind == "text":
            return "break"
        try:
            value = float(field.parse(self._vars[field.attr].get()))
        except ValueError:
            return "break"
        self._vars[field.attr].set(
            str(int(value) + step) if field.kind == "int"
            else f"{value + step:.6g}"
        )
        self._apply()
        return "break"

    def _schedule(self, event=None) -> None:
        if self._pending is not None:
            self._root.after_cancel(self._pending)
        self._pending = self._root.after(_DEBOUNCE_MS, self._apply)

    def _collect(self) -> tuple[dict[str, object], list[str]]:
        """The entries as values, and what could not be read.

        A field that will not parse is left alone rather than replaced by a
        guess, so a half typed number never yanks the preview somewhere else.
        """
        values: dict[str, object] = {}
        errors: list[str] = []
        for field in FIELDS:
            try:
                values[field.attr] = field.parse(self._vars[field.attr].get())
            except ValueError as exc:
                errors.append(f"{field.label}: {exc} — оставлено как было")
        if "BAR_SPAN_MIN" in values and "BAR_SPAN_MAX" in values:
            if float(values["BAR_SPAN_MIN"]) > float(values["BAR_SPAN_MAX"]):
                errors.append("BAR_SPAN_MIN больше BAR_SPAN_MAX — оставлено как было")
                values.pop("BAR_SPAN_MIN")
                values.pop("BAR_SPAN_MAX")
        font = values.get("_CLOCK_FONT")
        if isinstance(font, str):
            parts = font.split()
            try:
                values["_CLOCK_FONT"] = (parts[0], int(parts[1]))
            except (IndexError, ValueError):
                errors.append('_CLOCK_FONT: нужно "семейство размер", например Consolas 9')
                values.pop("_CLOCK_FONT")
        return values, errors

    def _reset(self) -> None:
        for field in FIELDS:
            self._vars[field.attr].set(self._text_of(self._defaults.get(field.attr)))
        self._apply(force_rebuild=True)

    # -- the module under the preview --------------------------------------

    def _apply(
        self, initial: bool = False, force_rebuild: bool = False
    ) -> None:
        self._pending = None
        values, self._errors = self._collect()
        if not values:
            self._refresh_report()
            return
        changed = {
            name for name, value in values.items()
            if getattr(ov, name, None) != value
        }
        for name, value in values.items():
            setattr(ov, name, value)
        if changed & {"BARS", "BAR_SPAN_MIN", "BAR_SPAN_MAX"}:
            self._recompute_bell()
        if initial or changed & {"BAR_TOP", "BAR_FIELD"}:
            self._recompute_mid()
        self._clock_font = tkfont.Font(root=self._root, font=ov._CLOCK_FONT)
        if initial or force_rebuild or changed & REBUILD_ATTRS:
            self._rebuild()
        else:
            self._place_preview()
        self._refresh_report()

    def _recompute_mid(self) -> None:
        """Redo what the module did once, at import, out of BAR_TOP and BAR_FIELD.

        `BAR_MID` is a constant of its own, not a property, so setting the two
        values it was built from leaves it stale and the bars stay where they
        were: the preview would look unchanged after a correct edit.
        """
        ov.BAR_MID = ov.BAR_TOP + ov.BAR_FIELD // 2

    def _recompute_bell(self) -> None:
        """Redo what the module did once, at import, for the new span values."""
        ov._CENTRE = (ov.BARS - 1) / 2
        ov._BELL_SPAN = bell_spans(ov.BARS, ov.BAR_SPAN_MIN, ov.BAR_SPAN_MAX)

    def _rebuild(self) -> None:
        """Throw the preview away and let the module build a new one.

        The window holds the plate, the bars and the clock label, all created
        once with the sizes that were current at that moment, so a change to the
        geometry or to a colour can only land in a fresh window. The elapsed
        seconds are carried across, because otherwise every arrow key press
        would restart the clock and the thing being tuned would stop counting.
        """
        since = self._overlay._since if self._overlay is not None else None
        if self._overlay is not None:
            self._overlay.destroy()
        self._overlay = ov.RecordingOverlay(self._root, self._next_level)
        self._overlay.show()
        if since is not None:
            self._overlay._since = since
        self._place_preview()

    def _next_level(self) -> float | None:
        if self._live is not None:
            return self._live.next_level()
        return self._fake.next_level()

    def _switch_source(self) -> None:
        if self._mode.get() == "микрофон":
            try:
                self._live = Microphone()
            except Exception as exc:
                self._errors.append(f"микрофон недоступен: {exc}")
                self._mode.set("речь")
        elif self._live is not None:
            self._live.close()
            self._live = None

    # -- placement ---------------------------------------------------------

    def _place_preview(self) -> None:
        """Put the preview where the module puts it, or under this window.

        In the bottom position the module's own placement is used, so what the
        tool shows about `MARGIN_ABOVE_TASKBAR` is the real placement. In the
        other position the chip follows this window, because looking at the
        bottom of the screen while typing into a field at the top of it is not
        tuning anything.
        """
        overlay_object = self._overlay
        if overlay_object is None or overlay_object._window is None:
            return
        if self._at_bottom.get():
            overlay_object._place()
            return
        screen = self._root.winfo_screenwidth()
        x = max(0, min(self._root.winfo_rootx(), screen - ov.WIDTH))
        y = (
            self._root.winfo_rooty() + self._root.winfo_height()
            + ov.MARGIN_ABOVE_TASKBAR
        )
        overlay_object._window.geometry(f"{ov.WIDTH}x{ov.HEIGHT}+{x}+{y}")

    # -- reporting ---------------------------------------------------------

    def _refresh_report(self) -> None:
        self._warnings = self._check()
        self._report.configure(state="normal")
        self._report.delete("1.0", "end")
        for line in [*self._errors, *self._warnings]:
            self._report.insert("end", line + "\n")
        if not self._errors and not self._warnings:
            self._report.insert(
                "end", "всё влезает: бары внутри пластины и не заходят на часы\n"
            )
        self._report.configure(state="disabled")

    def _check(self) -> list[str]:
        """The measurements that say whether these numbers make a good chip.

        Each of these fails silently if it is wrong. A canvas clips whatever is
        drawn past its edge without a word, so a bar that does not fit is simply
        a shorter bar and reads as an amplitude setting rather than a mistake,
        and two neighbouring bars that drift into each other just look like a
        slightly fatter bar.
        """
        issues: list[str] = []
        half = max_half_height(
            ov.BAR_IDLE, ov._BELL_SPAN, ov.WOBBLE_REL, ov.WOBBLE_ABS
        )
        clock = self._clock_font.metrics("linespace")
        clock_top = ov.CLOCK_Y - clock / 2
        if ov.BAR_MID - half < 0:
            issues.append(
                f"! бары срезаны сверху на {half - ov.BAR_MID:.1f} px — "
                "уменьшите BAR_TOP или BAR_SPAN_MAX"
            )
        if ov.BAR_MID + half > ov.HEIGHT:
            issues.append(
                f"! бары срезаны снизу на {ov.BAR_MID + half - ov.HEIGHT:.1f} px — "
                "уменьшите BAR_SPAN_MAX"
            )
        if ov.BAR_MID + half > clock_top:
            issues.append(
                f"! бары заходят на часы на {ov.BAR_MID + half - clock_top:.1f} px — "
                "опустите часы или убавьте бары"
            )
        if clock_top < 0 or ov.CLOCK_Y + clock / 2 > ov.HEIGHT:
            issues.append(
                f"! часы {ov._CLOCK_FONT[0]} {ov._CLOCK_FONT[1]} pt занимают "
                f"{clock_top:.1f} .. {ov.CLOCK_Y + clock / 2:.1f} при высоте {ov.HEIGHT}"
            )
        if 2 * half > ov.BAR_FIELD:
            issues.append(
                f"! BAR_FIELD {ov.BAR_FIELD} уже амплитуды {2 * half:.1f} — "
                "бары выходят за зарезервированное поле"
            )
        if ov.BAR_MARGIN < 0:
            issues.append("! ряд шире окна — BAR_MARGIN отрицательный")
        if ov.CORNER > min(ov.WIDTH, ov.HEIGHT) // 2:
            issues.append("! CORNER больше половины — пластина станет пилюлей")
        if ov.BARS % 2 == 0:
            issues.append("! BARS чётное — центральной полосы нет, ряд смещён")
        gap = self._smallest_step()
        if gap is not None:
            crossing = ov.WOBBLE_REL * gap[1] + 2 * ov.WOBBLE_ABS
            if crossing > gap[0]:
                issues.append(
                    f"! соседние бары могут слиться: шаг {gap[0]:.2f} px, "
                    f"колебание забирает {crossing:.2f} px — убавьте WOBBLE_ABS "
                    "или поднимите BAR_SPAN_MIN"
                )
        return issues

    def _smallest_step(self) -> tuple[float, float] | None:
        """The narrowest step between neighbouring bell shares, and that pair.

        The module keeps the wobble amplitudes under the step between two
        neighbouring bars so that bars pulled to opposite extremes cannot cross
        each other. Cut the shares for a short plate and that step shrinks
        faster than the amplitudes do, which is how the row loses its shape.
        """
        spans = list(ov._BELL_SPAN)
        if len(spans) < 2:
            return None
        return min((abs(high - low), low + high) for low, high in zip(spans, spans[1:]))

    def _readout_loop(self) -> None:
        overlay_object = self._overlay
        if overlay_object is not None:
            source = self._live if self._live is not None else self._fake
            level = source.last
            energy = getattr(overlay_object, "_energy", 0.0)
            half = max_half_height(
                ov.BAR_IDLE, ov._BELL_SPAN, ov.WOBBLE_REL, ov.WOBBLE_ABS
            )
            text = (
                f"BAR_MID {ov.BAR_MID} · полувысота {half:.2f} · "
                f"бары {ov.BAR_MID - half:.1f}..{ov.BAR_MID + half:.1f} · "
                f"часы {ov.CLOCK_Y} (строка "
                f"{self._clock_font.metrics('linespace')} px) · "
                f"уровень {'—' if level is None else f'{level:.2f}'} · "
                f"энергия {energy:.2f} · drive {min(1.0, energy * ov.DRIVE):.2f}"
            )
            if text != self._readout:
                self._readout = text
                self._line.configure(text=text)
        self._root.after(_READOUT_MS, self._readout_loop)

    # -- writing back ------------------------------------------------------

    def _write(self) -> None:
        values, errors = self._collect()
        if errors:
            self._errors = errors
            self._refresh_report()
            return
        print(f"записано в {SOURCE}:", flush=True)
        for line in write_source(SOURCE, values) or ["ничего не изменилось"]:
            print(f"  {line}", flush=True)
        print(
            "приложение надо перезапустить: модуль уже импортирован,\n"
            "а его константы читаются при сборке окна чипа",
            flush=True,
        )

    def _close(self) -> None:
        if self._live is not None:
            self._live.close()
        if self._overlay is not None:
            self._overlay.destroy()
        self._root.destroy()

    def run(self) -> None:
        self._root.after(_READOUT_MS, self._readout_loop)
        self._root.mainloop()


def self_test(path: Path, dump: bool = False) -> int:
    """Check the chip's arithmetic against the numbers in the file, no window.

    A missing constant, a row wider than the plate, bars past an edge and a clock
    outside the window are failures. A plate too short for its amplitude, and a
    wobble that can merge two neighbouring bars, are warnings: those are
    judgements about looks, and looks are what the person looking decides.

    Everything printed here stays inside ASCII on purpose. The Windows console
    this tool is launched from is usually on a code page that has no middle dot,
    and a report that comes out as question marks is worse than no report.
    """
    values = read_source(path)
    failures: list[str] = []
    warnings: list[str] = []
    print(f"source   {path}")
    if dump:
        for name in sorted(TUNABLE):
            if name in values:
                print(f"  {name:<24} {format_literal(values[name])}")
    missing = sorted(TUNABLE - set(values))
    if missing:
        print(f"FAIL  нет в файле: {', '.join(missing)}")
        print("VERDICT: FAIL")
        return 1

    bars = int(values["BARS"])
    span_min = float(values["BAR_SPAN_MIN"])
    span_max = float(values["BAR_SPAN_MAX"])
    idle = float(values["BAR_IDLE"])
    width = int(values["WIDTH"])
    height = int(values["HEIGHT"])
    row_width = bars * int(values["BAR_WIDTH"]) + (bars - 1) * int(values["BAR_GAP"])
    margin = (width - row_width) // 2
    mid = int(values["BAR_TOP"]) + int(values["BAR_FIELD"]) // 2
    spans = bell_spans(bars, span_min, span_max)
    half = max_half_height(
        idle, spans, float(values["WOBBLE_REL"]), float(values["WOBBLE_ABS"])
    )
    family, size = values["_CLOCK_FONT"]
    line = int(size) * 96 / 72 * _CLOCK_LINE_FACTOR
    clock_top = int(values["CLOCK_Y"]) - line / 2
    clock_bottom = int(values["CLOCK_Y"]) + line / 2

    print(f"BAR_MID {mid} | ряд {row_width} px | поле {margin} px с каждой стороны")
    print(f"бары    {mid - half:.2f} .. {mid + half:.2f} | потолок {half:.2f} px в каждую сторону")
    print(f"часы    {clock_top:.1f} .. {clock_bottom:.1f} | {family} {size} pt, строка {line:.1f} px")
    print(f"пластина 0 .. {height} | скругление {values['CORNER']}")

    if span_min > span_max:
        failures.append("BAR_SPAN_MIN больше BAR_SPAN_MAX, колокол перевёрнут")
    if margin < 0:
        failures.append(f"ряд шире пластины: {row_width} px в {width} px")
    if mid - half < 0 or mid + half > height:
        failures.append(
            f"бары не влезают: {mid - half:.2f} .. {mid + half:.2f} при высоте {height}"
        )
    if clock_top < 0 or clock_bottom > height:
        failures.append(
            f"часы не влезают: {clock_top:.1f} .. {clock_bottom:.1f} при высоте {height}"
        )
    if mid + half > clock_top:
        warnings.append(f"бары заходят на часы на {mid + half - clock_top:.1f} px")
    if 2 * half > int(values["BAR_FIELD"]):
        warnings.append(
            f"BAR_FIELD {values['BAR_FIELD']} уже амплитуды {2 * half:.1f}"
        )
    if int(values["CORNER"]) > min(width, height) // 2:
        warnings.append("CORNER больше половины высоты, пластина станет пилюлей")
    if bars % 2 == 0:
        warnings.append("BARS чётное, центральной полосы нет")
    step, pair = min(
        (abs(high - low), low + high) for low, high in zip(spans, spans[1:])
    )
    crossing = float(values["WOBBLE_REL"]) * pair + 2 * float(values["WOBBLE_ABS"])
    if crossing > step:
        warnings.append(
            f"колебание {crossing:.2f} px больше шага {step:.2f} px между "
            "соседними барами, на пике они сливаются"
        )
    for line in failures:
        print(f"FAIL  {line}")
    for line in warnings:
        print(f"warn  {line}")
    print("VERDICT: " + ("FAIL" if failures else "PASS"))
    return 1 if failures else 0


def gui_smoke(path: Path) -> int:
    """Drive the whole control window once, then close it, to prove it works.

    Building the preview is the part that can break in ways a windowless check
    cannot see: the entries, the debounce, the rebuild through the module, the
    font measurement and the write back. Each case below is applied for real, so
    a crash in any of them fails here instead of in front of the user. The write
    back runs against a copy, because the point of the tool is to change that
    file deliberately and a smoke test must not do it by accident.

    Run it from the project root:

        .\\.venv\\Scripts\\python.exe .\\tools\\overlay_tune.py --smoke
    """
    import shutil
    import tempfile

    # The 36 px plate the tuner was built for, plus cases that have to be
    # reported rather than silently clipped. `clean` says whether the case is
    # supposed to come back with nothing at all. WOBBLE_ABS is in the 36 px case
    # because the tool refuses it without it: cut the bell shares for a short
    # plate and the step between two neighbouring bars shrinks faster than the
    # wobble does, so at 0.30 the outermost pair can drift into each other.
    cases = (
        ("исходные", {}, True),
        ("36 px", {
            "HEIGHT": "36", "BAR_TOP": "1", "BAR_FIELD": "18",
            "BAR_SPAN_MAX": "5.7", "BAR_SPAN_MIN": "1.2", "BAR_IDLE": "2",
            "CORNER": "12", "CLOCK_Y": "28", "_CLOCK_FONT": "Consolas 9",
            "WOBBLE_ABS": "0.15",
        }, True),
        ("часы уехали наверх", {"CLOCK_Y": "0"}, False),
        ("три барa", {"BARS": "3", "BAR_SPAN_MIN": "2", "BAR_SPAN_MAX": "8"}, True),
        ("поле меньше амплитуды", {"BAR_FIELD": "4"}, False),
    )
    tuner = Tuner(FakeSpeech())
    failures: list[str] = []
    try:
        for name, patch, clean in cases:
            tuner._reset()
            for attr, value in patch.items():
                tuner._vars[attr].set(value)
            tuner._apply(force_rebuild=True)
            found = [*tuner._errors, *tuner._warnings]
            ok = not found if clean else bool(found)
            print(f"{'ok  ' if ok else 'FAIL'} {name}: {len(found)} замечани(й)")
            for line in found:
                print(f"       {line}")
            if not ok:
                failures.append(
                    f"{name}: {'ожидалось без замечаний' if clean else 'ожидалось замечание'}"
                )
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / path.name
            shutil.copy(path, copy)
            before = copy.read_text(encoding="utf-8")
            write_source(copy, {"HEIGHT": 36, "BAR_SPAN_MAX": 5.7, "_BAR_LOW": "#123456"})
            after = copy.read_text(encoding="utf-8")
            reread = read_source(copy)
            for name, expected in (("HEIGHT", 36), ("BAR_SPAN_MAX", 5.7), ("_BAR_LOW", "#123456")):
                if reread.get(name) != expected:
                    failures.append(f"запись {name}: получено {reread.get(name)!r}")
            changed = sum(
                1 for a, b in zip(before.splitlines(), after.splitlines()) if a != b
            )
            same_length = len(before.splitlines()) == len(after.splitlines())
            print(f"ok   запись: {changed} строк изменено, строк столько же: {same_length}")
            if not same_length:
                failures.append("запись изменила число строк в файле")
            if path.read_text(encoding="utf-8") != before:
                failures.append("исходный overlay.py изменён — этого быть не должно")
    finally:
        tuner._close()
    for line in failures:
        print(f"FAIL {line}")
    print("VERDICT: " + ("FAIL" if failures else "PASS"))
    return 1 if failures else 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test(SOURCE, "--dump" in sys.argv)
    if "--smoke" in sys.argv:
        return gui_smoke(SOURCE)
    Tuner(FakeSpeech()).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())