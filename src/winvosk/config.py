"""Runtime configuration, model resolution and logging setup."""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import text

log = logging.getLogger(__name__)

APP_NAME = "WinVosk"

# The release this build is. Bumped for every release, and the only place the
# number is written: `--diagnose` prints it, the panel shows it in its title and
# `winvosk.__version__` derives from it, so a bug report can be tied to a build
# without anyone reading a file.
VERSION = "1.2"

# True inside a PyInstaller bundle, where the modules sit in `_internal\` and
# `__file__` no longer points at the folder the user keeps their files in.
FROZEN = getattr(sys, "frozen", False)


def _base_dir() -> Path:
    r"""The checkout root, or the folder holding the exe once it is frozen.

    Everything the app reads or writes — `models\`, `logs\`, `settings.json`,
    `phrases.txt` — is resolved from this one value, so a bundle and a source
    checkout keep the same layout and the same rules.
    """
    if FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


BASE_DIR = _base_dir()
SRC_DIR = BASE_DIR / "src"
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"
TMP_DIR = BASE_DIR / "tmp"
VENV_SCRIPTS = BASE_DIR / ".venv" / "Scripts"
PYTHONW = VENV_SCRIPTS / "pythonw.exe"
RUN_SCRIPT = SRC_DIR / "run.py"

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "WinVosk"
MUTEX_NAME = "Local\\WinVoskSingleInstance"

MODEL_NAME = "vosk-model-small-ru-0.22"
SAMPLE_RATE = 16000
BLOCK_SIZE = 8000
MIC_DEVICE: int | None = None
SHOW_WORDS = False

HOTKEYS: tuple[str, ...] = ("win+ctrl+right", "alt+win")
# "Печатать в активное окно": words are typed at the caret while speaking.
LIVE_TYPE_DEFAULT = True
# "Переключать запись": the hotkey starts a recording and stops it, instead of
# recording only while it is held. Off by default, which is push to talk.
TOGGLE_DEFAULT = False
# "Сразу в буфер": the finished text is also copied to the clipboard.
CLIPBOARD_DEFAULT = False
# "Исправлять свои слова": near misses of the words in PHRASES_FILE are fixed.
CORRECT_WORDS_DEFAULT = True
# The interface language, `text.LANGUAGES`, Russian unless the user says otherwise.
LANGUAGE_DEFAULT = text.DEFAULT_LANGUAGE
TYPE_DELAY = 0.02
MAX_SESSION_SECONDS = 180.0
PHRASES_FILE = BASE_DIR / "phrases.txt"

LOG_FILE = LOGS_DIR / "app.log"
LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUPS = 3


def hotkey_label() -> str:
    return text.t("hotkey_or").join(HOTKEYS)


def is_russian_model(path: Path) -> bool:
    """Whether a model directory name carries the `ru` language code.

    Compared as a whole hyphen separated token, never as a substring: `uz` and
    `ru` differ by one letter, and a glob on `*ru*` cannot tell «uz» from «ru».
    """
    return "ru" in path.name.split("-")


def model_candidates() -> list[Path]:
    """Every Kaldi model in MODELS_DIR, Russian first, then the rest by name.

    A directory counts as a model when it holds the `am` directory every
    compiled Kaldi graph has, which is the same test the preferred name gets.
    """
    found = [
        path for path in MODELS_DIR.glob("vosk-model*") if (path / "am").is_dir()
    ]
    return sorted(found, key=lambda path: (not is_russian_model(path), path.name))


def resolve_model() -> Path:
    r"""Return the directory of the vosk model to decode with.

    Russian is preferred and `MODEL_NAME` wins outright when it is there, so the
    shipped setup behaves exactly as it always has. Any other Kaldi model is
    accepted as a fallback rather than refused: the decoder does not care about
    the language, and dropping a model the user downloaded into `models\` is a
    worse answer than loading it and saying which one it is.
    """
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    preferred = MODELS_DIR / MODEL_NAME
    if (preferred / "am").is_dir():
        return preferred
    candidates = model_candidates()
    if not candidates:
        raise FileNotFoundError(
            f"No vosk model found in {MODELS_DIR}. "
            f"Expected a directory named {MODEL_NAME} or any other vosk-model* "
            f"directory holding an 'am' subdirectory."
        )
    chosen = candidates[0]
    log.info(
        "model %s is not installed, using %s instead", MODEL_NAME, chosen.name
    )
    return chosen


def setup_logging(level: int = logging.INFO) -> None:
    """Attach a rotating file handler once, so errors survive pythonw.exe."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return
    handler = RotatingFileHandler(
        LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-7s [%(threadName)-12s] %(name)s: %(message)s"
        )
    )
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    _log_thread_exceptions()


def _log_thread_exceptions() -> None:
    """Send an unhandled exception in any thread to the log, not to stderr.

    A crash on the main thread is at least a non-zero exit code; one on a worker
    thread is not, and Python reports it through `sys.stderr`. Under
    `pythonw.exe`, and in a bundle built with `console=False`, `sys.stderr` is
    `None`, so the report goes nowhere and the process carries on looking
    healthy. That is how a tray icon could vanish - pystray adds the icon from
    a thread of its own - with nothing in the log to say why.
    """
    def report(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit:
            return
        log.error("unhandled exception in thread %s", args.thread.name,
                  exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    threading.excepthook = report
