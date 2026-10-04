"""Build the WinVosk.exe folder: icon, PyInstaller, prune, then the model.

Run it from anywhere; every path is resolved from this file:

    .\\.venv\\Scripts\\python.exe .\\tools\\build_exe.py

The result is `dist\\WinVosk\\` — `WinVosk.exe`, `_internal\\` and the folders the
app reads and writes itself: `models\\`, `logs\\`, `settings.json`,
`phrases.txt`. The folder can be copied anywhere afterwards, and the exe has to
be started from inside it, because `config.BASE_DIR` is the folder the exe is
in.

The prune step is not a nicety. PyInstaller copies whole trees it does not
understand, and what it copied cost 656 files and 12 MB that nothing here can
reach — every Pillow codec, the whole TLS stack behind vosk's unused streaming
client, wheel metadata, two dead Tcl directories and a 609-file timezone
database. See the PRUNE table below for each entry and its reason.

One folder rather than one file on purpose: the model is 87 MB and a single exe
would extract it, the Kaldi libraries and PortAudio into a temporary directory
on every launch. An unsigned exe also trips SmartScreen on a download; a local
folder does not.

After building, check the result — a prune can go one step too far, and only a
real GUI start would notice:

    .\\dist\\WinVosk\\WinVosk.exe --check-bundle
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SPEC = ROOT / "WinVosk.spec"
ICON = ROOT / "build" / "WinVosk.ico"
VERSION_FILE = ROOT / "build" / "WinVosk.version"
DIST = ROOT / "dist" / "WinVosk"
INTERNAL = DIST / "_internal"

ICON_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

# What `_internal` carries that WinVosk cannot reach, and why it is safe to go.
#
# PyInstaller copies whole trees it does not understand: every Pillow codec, the
# whole Tcl script library, the wheel metadata of every dependency. None of that
# is reachable from a panel, a tray glyph and a Kaldi recogniser, and it is most
# of the folder. Each pattern is matched with `Path.glob` against `_internal`,
# and a pattern that matches nothing is reported rather than ignored, so an
# upgrade that renames one of these files cannot quietly leave it in place.
#
# Nothing here is packed away: a `.pyd` or `.dll` has to be a real file for the
# Windows loader, and Tcl has to find its scripts as files on disk.
PRUNE: tuple[tuple[str, str], ...] = (
    # Pillow draws two things: a rounded plate and a tray glyph. Both are sRGB
    # literals drawn with ImageDraw, and neither opens an image file.
    ("PIL/_avif*.pyd", "AVIF codec, nothing opens an AVIF"),
    ("PIL/_webp*.pyd", "WebP codec, nothing opens a WebP"),
    ("PIL/_imagingcms*.pyd", "ICC colour management, the colours are literals"),
    ("PIL/_imagingmath*.pyd", "only ImageMath.eval reaches it"),
    ("PIL/_imagingft*.pyd", "freetype, no text is drawn through Pillow"),
    # `vosk.transcriber` is a client for a vosk-server this app never runs. It
    # used to arrive as a hidden import of the whole vosk package and brought
    # websockets, socks and then the TLS stack with it.
    ("websockets", "vosk.transcriber's streaming client, never used"),
    ("socks", "a websockets dependency, never used"),
    ("setuptools", "pkg_resources leftover of the vosk wheel"),
    ("*.dist-info", "wheel metadata, nothing reads it at run time"),
    # tcl86t.dll reads `tcl8/8.6/init.tcl` and nothing else; `package require
    # -exact Tcl 8.6.15` in it rules the other two directories out.
    ("tcl8/8.4", "Tcl 8.4's init.tcl, only 8.6 is loaded"),
    ("tcl8/8.5", "Tcl 8.5's init.tcl, only 8.6 is loaded"),
    # Tcl's timezone database, 609 files in 30 folders. Only `clock` with an
    # explicit zone reads it, and the panel shows no clock: the chip's M:SS is
    # counted in Python from perf_counter. `msgs` (the localised Tk strings) and
    # `encoding` (what ttk reads its themes through) are kept.
    ("_tcl_data/tzdata", "Tcl's timezone database, only `clock` with a zone reads it"),
)


def write_icon() -> None:
    """The tray draws its glyph in code, so the exe icon is drawn the same way.

    Rendered at 256 px and saved as a multi-size .ico, which is what the shell
    asks for at 16, 24, 32 and 48; the tray icon itself is unaffected.
    """
    from winvosk.tray import make_icon

    ICON.parent.mkdir(parents=True, exist_ok=True)
    make_icon(False, size=256).save(ICON, sizes=ICON_SIZES)
    print(f"icon        : {ICON.relative_to(ROOT)} ({ICON.stat().st_size} bytes)")


def write_version_file() -> str:
    r"""Write the exe's version resource, and return the number it carries.

    Explorer shows this on hover and in the property sheet, and it is the only
    place the release number is visible before the app is started: an exe whose
    Properties tab says nothing cannot be told apart from the build before it.
    That matters here because both the bundle and the archive are copied around
    between machines.

    Written from `config.VERSION` rather than kept as a file in the repository,
    so the number in the property sheet and the number `--diagnose` prints are one
    literal rather than two that can drift. It lands in `build\`, which is
    gitignored and rebuilt, and `WinVosk.spec` names the file rather than holding
    a copy of its contents.
    """
    from winvosk import config

    version = config.VERSION
    numbers = tuple(int(part) for part in version.split("."))
    if len(numbers) != 3:
        raise SystemExit(
            f"VERSION is {version!r}; the resource wants MAJOR.MINOR.PATCH"
        )
    # The fixed part of the resource is four numbers, and the fourth is the
    # zero that says "no private build".
    quad = numbers + (0,)
    text = f'''# Generated by tools\\build_exe.py from config.VERSION = {version}.
# PyInstaller executes this file, which is why it is Python syntax and not INI.
# Do not edit it: change VERSION in src\\winvosk\\config.py and build again.

VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={quad},
    prodvers={quad},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'WinVosk'),
         StringStruct('FileDescription', 'WinVosk - offline dictation for Windows'),
         StringStruct('FileVersion', '{version}'),
         StringStruct('InternalName', 'WinVosk'),
         StringStruct('LegalCopyright', 'Apache-2.0'),
         StringStruct('OriginalFilename', 'WinVosk.exe'),
         StringStruct('ProductName', 'WinVosk'),
         StringStruct('ProductVersion', '{version}.0')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
'''
    VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    VERSION_FILE.write_text(text, encoding="utf-8")
    print(f"version     : {VERSION_FILE.relative_to(ROOT)} "
          f"({config.APP_NAME} {version})")
    return version


def run_pyinstaller() -> None:
    print(f"building    : {SPEC.relative_to(ROOT)}", flush=True)
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC)],
        cwd=ROOT,
    )
    if result.returncode != 0:
        raise SystemExit(f"PyInstaller failed with {result.returncode}")


def prune_internal() -> None:
    """Delete what `_internal` carries that nothing here can reach.

    Runs after PyInstaller and before the user files are copied, and reports
    every pattern that matched nothing: a rename upstream should be a visible
    line in the build log, not a file that quietly stays in the folder.
    """
    if not INTERNAL.is_dir():
        raise SystemExit(f"no bundle to prune: {INTERNAL} is missing")
    before = _folder_size(INTERNAL)
    for pattern, why in PRUNE:
        matched = sorted(INTERNAL.glob(pattern))
        if not matched:
            print(f"  prune  {pattern:24s} matched nothing — {why}")
            continue
        freed = 0
        for path in matched:
            freed += _folder_size(path)
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        print(f"  prune  {pattern:24s} {freed / 1024 / 1024:6.1f} MB  {why}")
    after = _folder_size(INTERNAL)
    print(f"pruned     : {(before - after) / 1024 / 1024:.1f} MB of "
          f"{before / 1024 / 1024:.1f} MB, {after / 1024 / 1024:.1f} MB left")


def _folder_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def copy_user_files() -> None:
    """Put the model and the word list next to the exe, where the app looks."""
    shutil.copytree(ROOT / "models", DIST / "models", dirs_exist_ok=True)
    phrases = ROOT / "phrases.txt"
    if phrases.exists():
        shutil.copy2(phrases, DIST / phrases.name)
    (DIST / "logs").mkdir(exist_ok=True)


def report() -> str:
    """Print what the build produced, and return the version it carries.

    The exe's own version resource is read back from the file rather than echoed
    from the number that was written: a resource PyInstaller silently failed to
    embed is exactly the kind of thing that has to be noticed here rather than
    discovered on somebody else's desktop.
    """
    exe = DIST / "WinVosk.exe"
    total = sum(path.stat().st_size for path in DIST.rglob("*") if path.is_file())
    files = sum(1 for path in DIST.rglob("*") if path.is_file())
    version = _exe_version(exe)
    print(f"\nfolder      : {DIST}")
    print(f"exe         : {exe.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"_internal   : {_folder_size(INTERNAL) / 1024 / 1024:.1f} MB in "
          f"{sum(1 for p in INTERNAL.rglob('*') if p.is_file())} file(s)")
    print(f"with model  : {total / 1024 / 1024:.1f} MB in {files} file(s)")
    print(f"properties  : {version or 'NO VERSION RESOURCE'}")
    print(f"start       : {exe}")
    print(f"check       : {exe} --diagnose")
    return version


def _exe_version(exe: Path) -> str:
    """`FileDescription`, `FileVersion` and `ProductVersion` as Explorer reads them.

    `ctypes` rather than a new dependency: the API is two calls and a walk
    through one structure, and `pefile` would be a pin added to the build for one
    report line. Returns an empty string when the resource is not there.
    """
    import ctypes
    from ctypes import wintypes

    size = wintypes.DWORD(0)
    # No argtypes are declared, so both functions answer with a plain int rather
    # than a ctypes object; `handle` is the size in bytes and is used as one.
    handle = int(ctypes.windll.version.GetFileVersionInfoSizeW(str(exe), ctypes.byref(size)))
    if not handle:
        return ""
    block = ctypes.create_string_buffer(handle)
    if not ctypes.windll.version.GetFileVersionInfoW(str(exe), 0, handle, block):
        return ""
    # Ask for the root, then for the translation PyInstaller wrote: 0409 is
    # en-US and 04B0 is Unicode, which is what `VarStruct('Translation', ...)` says.
    root = ctypes.c_void_p()
    length = wintypes.UINT(0)
    for path in ("\\", "\\VarFileInfo\\Translation"):
        ctypes.windll.version.VerQueryValueW(
            block, ctypes.c_wchar_p(path), ctypes.byref(root), ctypes.byref(length))
    if not root:
        return ""
    pair = ctypes.cast(root, ctypes.POINTER(ctypes.c_ushort * 2)).contents
    table = rf"\StringFileInfo\{pair[0]:04x}{pair[1]:04x}"
    parts = []
    for name in ("FileDescription", "FileVersion", "ProductVersion"):
        root = ctypes.c_void_p()
        ctypes.windll.version.VerQueryValueW(
            block, ctypes.c_wchar_p(f"{table}\\{name}"),
            ctypes.byref(root), ctypes.byref(length))
        parts.append(ctypes.wstring_at(root) if root else "empty")
    return " | ".join(parts)


def main() -> int:
    write_icon()
    version = write_version_file()
    run_pyinstaller()
    prune_internal()
    copy_user_files()
    written = report()
    if not written:
        raise SystemExit(
            "the exe carries no version resource, so it cannot be told apart "
            "from the build before it. Both the bundle and the archive are "
            "copied between machines, and this is the only place the number is "
            "visible before the app runs. The build is not a release."
        )
    if version not in written:
        raise SystemExit(
            f"the exe says {written!r} but VERSION is {version!r}: the version "
            f"resource and the build disagree, so the archive is not a release"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())