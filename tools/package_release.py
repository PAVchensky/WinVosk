"""Stage the release archive from a built folder.

`build_exe.py` produces the right thing for this machine: the exe, the model,
and your own `phrases.txt` beside it. That is exactly what must not be handed to
anybody else, and the log directory fills up with whatever was dictated. So this
step takes `dist\\WinVosk\\`, copies it aside, and takes the personal parts out:

- `phrases.txt` is removed and `phrases.example.txt` is shipped instead,
- `logs\\` is emptied, and any `settings.json` left in the folder is dropped,
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
   for two dozen languages.

5. Your own words go in phrases.txt — copy phrases.example.txt and fill it in.
   The file is not shipped, because it is yours.

Recognition is local. The application opens no network connection at all: no
account, no update check, no analytics. The only files it writes are logs\\,
settings.json and phrases.txt on your own disk.

Full guide and screenshots: the project page. Licenses for everything in this
folder are in licenses\\, and NOTICE says what is whose.
"""


def _version() -> str:
    from winvosk import config

    return config.VERSION


def stage(version: str) -> Path:
    """A copy of the built folder with nothing personal left in it."""
    if not (BUILT / "WinVosk.exe").exists():
        raise SystemExit(
            f"{BUILT} does not look like a build: no WinVosk.exe. "
            "Run tools\\build_exe.py first."
        )
    staged = ROOT / "dist" / f"WinVosk-{version}-win64"
    if staged.exists():
        shutil.rmtree(staged)
    shutil.copytree(BUILT, staged)

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

    underline = "=" * len(f"WinVosk {version} — offline dictation and voice-to-text for Windows")
    (staged / "README.txt").write_text(
        README_TEXT.format(version=version, underline=underline), encoding="utf-8"
    )
    return staged


def audit(staged: Path) -> None:
    """Refuse to ship a word list or a log."""
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