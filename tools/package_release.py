"""Stage the release archive from a built folder.

`build_exe.py` produces the right thing for this machine: the exe, the model,
and your own `phrases.txt` beside it. That is exactly what must not be handed to
anybody else, and the log directory fills up with whatever was dictated. So this
step takes `dist\\WinVosk\\`, copies it aside, and takes the personal parts out:

- `phrases.txt` is removed and `phrases.example.txt` is shipped instead,
- `logs\\` is emptied, and the build machine's own `settings.json` is dropped and
  replaced with one generated from the defaults, so the keys are discoverable
  without shipping anybody's choices,
- the license texts are added, because the bundle ships Apache-2.0 code, the GCC
  runtime and the PyInstaller bootloader,
- a `README.txt` says what to do after unpacking.

Then it zips the result and prints the SHA-256. The archive keeps the model: a
downloaded model is 45 MB and the point of a release is that it runs.

It refuses to finish if anything personal survived, so a leak cannot pass
quietly. Run it after `build_exe.py`:

    .\\.venv\\Scripts\\python.exe .\\tools\\package_release.py
"""

from __future__ import annotations

import hashlib

import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

BUILT = ROOT / "dist" / "WinVosk"

# Anything that is the user's and not the project's. `phrases.txt` is the word
# list, `logs\` is the dictated history, `settings.json` is this machine's hotkey.
# The settings file is not only dropped from the archive, it is *generated* by the
# application on the first run — see `settings.ensure_file` — so there is nothing
# to keep in step here and nothing in it for a user to decide what to do with.
PERSONAL_NAMES = ("phrases.txt", "settings.json", "settings.json.tmp")
PERSONAL_DIRS = ("logs",)

SHIPPED_NAMES = ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md")

README_TEXT = """WinVosk {version} — offline dictation and voice-to-text for Windows
{underline}

1. Unpack the whole folder. WinVosk.exe reads the model and writes its log next
   to itself, so it has to be started from inside this folder.

2. Start WinVosk.exe. A tray icon appears. A first run may make Windows
   SmartScreen complain about an unsigned download; it is unsigned.

3. Hold Win+Ctrl+Right or Alt+Win, speak, let go. The words are typed where your
   caret was. Recording lasts exactly as long as you hold the keys. The settings
   tab can turn that into a toggle - press the combination once to start, once
   more to stop - and it is off by default.

4. The language is the model's choice. This archive ships the small Russian
   model; any other model from https://alphacephei.com/vosk/models dropped into
   the models folder is picked up automatically, and the publisher lists models
   for 32 languages.

5. Your own words go in phrases.txt — copy phrases.example.txt and fill it in.
   The file is not shipped, because it is yours.

6. There is no settings.json in the archive, and that is deliberate: the first
   run writes one next to this exe with every setting in it and its default, and
   the panel writes to it from then on. Nothing in it needs changing — it is a
   list of what *can* be changed. Two keys are worth knowing about, because they
   are about other programs rather than about this one.

   "dictate_layout" lends the window you are typing in an English keyboard layout
   for the length of a recording and puts yours back afterwards, which stops
   layout switchers from rewriting the words as they arrive. It is written as
   "00000409", English, and an empty string is how you switch it off.

   "switcher_key" is a combination, "ctrl+shift+f10" by way of example, pressed
   once before a recording and once after it to ask a keyboard layout switcher
   such as Punto Switcher to stop rewriting your words. It is written empty,
   because there is no right default — it has to be the combination your own
   switcher answers — so no keys are pressed until you name one.

Recognition is local. The application opens no network connection at all: no
account, no update check, no analytics. The only files it writes are logs\\ and
phrases.txt on your own disk, and settings.json when you change something.

Full guide and screenshots: the project page. Licenses for everything in this
folder are in licenses\\, and NOTICE says what is whose.
"""


def _version() -> str:
    from winvosk import config

    return config.VERSION


def _clear(folder: Path) -> None:
    """Empty a folder that will not delete, and say so rather than failing.

    Reported because a folder that survives here is also a folder the next run
    has to clear again, and it is worth knowing it is there.
    """
    survivors = []
    for path in sorted(folder.rglob("*"), reverse=True):
        try:
            path.rmdir() if path.is_dir() else path.unlink()
        except OSError:
            survivors.append(path)
    if survivors:
        print(f"  warning: {len(survivors)} item(s) in {folder.name} are in use "
              f"and stay: {survivors[0].relative_to(folder)}"
              f"{' and more' if len(survivors) > 1 else ''}")
    print(f"  warning: {folder.name} itself could not be removed; the release "
          f"was staged into it anyway. Close anything running from it and delete "
          f"it before the next build.")


def stage(version: str) -> Path:
    """A copy of the built folder with nothing personal left in it."""
    if not (BUILT / "WinVosk.exe").exists():
        raise SystemExit(
            f"{BUILT} does not look like a build: no WinVosk.exe. "
            "Run tools\\build_exe.py first."
        )
    staged = ROOT / "dist" / f"WinVosk-{version}-win64"
    if staged.exists():
        try:
            shutil.rmtree(staged)
        except OSError as exc:
            # A folder nothing can delete is normal on Windows for a few minutes
            # after 172 MB have been copied into it: an indexer or a scanner holds
            # a handle on the directory itself, which stops the final `rmdir`
            # while every file inside goes quietly. Blocking a release on that is
            # worse than the leftover, so the folder is emptied where it can be
            # and the copy goes on top. Anything of the previous build that could
            # reach the user is caught below by the same check that refuses an
            # archive with anything personal in it.
            _clear(staged)
    shutil.copytree(BUILT, staged, dirs_exist_ok=True)

    for name in PERSONAL_NAMES:
        (staged / name).unlink(missing_ok=True)
    for name in PERSONAL_DIRS:
        directory = staged / name
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True, exist_ok=True)

    for name in SHIPPED_NAMES:
        source = ROOT / name
        if not source.exists():
            raise SystemExit(f"{source} is missing, the release cannot ship.")
        shutil.copy2(source, staged / name)
    shutil.copytree(ROOT / "licenses", staged / "licenses", dirs_exist_ok=True)
    example = ROOT / "phrases.example.txt"
    if example.exists():
        shutil.copy2(example, staged / "phrases.example.txt")

    # No settings file here on purpose. It used to be generated into the archive so
    # the keys were discoverable without opening the panel, and that meant two
    # copies of the schema to keep in step — this file and `settings.defaults` —
    # and a `settings.json` for a user to wonder about before they had changed
    # anything. The application writes it on its first run now, next to the exe,
    # from `settings.defaults()`, which is the only place the list exists.
    print("  settings    : not shipped; the first run writes one next to the exe")

    underline = "=" * len(f"WinVosk {version} — offline dictation and voice-to-text for Windows")
    (staged / "README.txt").write_text(
        README_TEXT.format(version=version, underline=underline), encoding="utf-8"
    )
    return staged


def audit(staged: Path) -> None:
    """Refuse to ship a word list, a log, or somebody else's settings.

    A name check is enough again, and it is enough *because* the release no longer
    writes a `settings.json` at all: the application generates one on its first
    run, so there is no legitimate copy of that name in an archive and any file
    found here is this machine's — its hotkeys, its theme, its recording device.
    When the archive did ship a pristine one, a name check could not tell the two
    apart and the bytes had to be compared, which was the whole reason this
    function grew a branch.
    """
    problems = []
    for path in staged.rglob("*"):
        if path.is_dir():
            continue
        name = path.name.lower()
        if name in PERSONAL_NAMES or name.startswith("app.log"):
            problems.append(path.relative_to(staged))
        elif path.suffix in {".txt", ".log"} and path.parent.name == "logs":
            problems.append(path.relative_to(staged))
    if problems:
        for path in problems:
            print(f"  personal file survived: {path}")
        raise SystemExit("the archive still holds the user's own files.")


def compress(staged: Path) -> tuple[Path, str]:
    # Built by hand, not with `with_suffix`: the folder name ends in `0.1.0`,
    # and pathlib would read `.0-win64` as a suffix and drop it.
    archive = staged.parent / f"{staged.name}.zip"
    archive.unlink(missing_ok=True)
    digest = hashlib.sha256()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for path in sorted(staged.rglob("*")):
            if path.is_file():
                zipped.write(path, Path(staged.name) / path.relative_to(staged))
    with archive.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return archive, digest.hexdigest()


def report(staged: Path, archive: Path, sha: str) -> None:
    total = sum(path.stat().st_size for path in staged.rglob("*") if path.is_file())
    exe = staged / "WinVosk.exe"
    licenses = len(list((staged / "licenses").glob("*")))
    models = [path.name for path in (staged / "models").iterdir() if path.is_dir()]
    print(f"\nfolder      : {staged}")
    print(f"exe         : {exe.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"with model  : {total / 1024 / 1024:.1f} MB")
    print(f"model       : {', '.join(models) or 'none, the app will not start'}")
    print(f"licenses    : {licenses} text(s)")
    print(f"word list   : {'phrases.example.txt, no phrases.txt' if (staged / 'phrases.example.txt').exists() else 'missing'}")
    print(f"archive     : {archive.name} "
          f"({archive.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"sha256      : {sha}")
    print("\nUpload that archive to the GitHub release. Do not upload the folder.")


def main() -> int:
    version = _version()
    staged = stage(version)
    audit(staged)
    archive, sha = compress(staged)
    report(staged, archive, sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())