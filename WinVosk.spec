# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build of WinVosk.

One folder, not one file: the model is 87 MB, and a single exe bundle would
extract the model and the native libraries into a temporary directory on every
launch. The model and `phrases.txt` are copied next to the exe by
`tools\build_exe.py`, which is also what keeps them editable for the user.

`SPECPATH`, `Analysis`, `PYZ`, `EXE` and `COLLECT` are injected by PyInstaller;
this file is only ever run by it, never imported directly.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH).resolve()

# vosk carries the prebuilt Kaldi decoder as native libraries and sounddevice
# carries PortAudio; neither is importable data on its own, so both are
# collected whole rather than left to the hook guessing.
#
# Deliberately not `collect_all`: that also returns every submodule, and
# `vosk.transcriber` is a streaming *client* for a server this app never runs.
# Naming it as a hidden import pulled `websockets` and `socks` into the bundle,
# and through them the whole TLS stack — about 6 MB of `libssl`/`libcrypto` on
# top of what is genuinely reachable. Only the DLLs and the package data are
# taken; PyInstaller finds `vosk/__init__.py` and `vosk.vosk_cffi` on its own
# from `import vosk`, and `requests`, `srt` and `tqdm` are imported there at
# module level, so they still arrive by static analysis.
datas = []
binaries = []
for package in ("vosk", "sounddevice"):
    binaries += collect_dynamic_libs(package)
    datas += collect_data_files(package, include_py_files=False)

# The bundle ships Apache-2.0 code, the GCC runtime and the PyInstaller
# bootloader, so their texts travel with it rather than sitting in the
# repository. `tools\package_release.py` copies the same set into the archive.
for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
    datas.append((str(ROOT / name), "."))
datas.append((str(ROOT / "licenses"), "licenses"))

# `vosk.vosk_cffi` builds its bindings through cffi at import time, so it has to
# be named: nothing imports it by a literal `import`.
hiddenimports = ["vosk.vosk_cffi"]

icon = ROOT / "build" / "WinVosk.ico"

a = Analysis(
    [str(ROOT / "src" / "run.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Nothing here imports these; dropping them keeps the folder smaller.
    excludes=[
        "test", "unittest", "pydoc_data", "lib2to3", "tkinter.test",
        # Pillow's plugin modules are found by `Image.init()` in a try/except
        # ImportError, so a missing one is skipped rather than fatal. Only the
        # codecs the chip and the tray icon can reach are kept; see PRUNE in
        # `tools/build_exe.py` for the binaries that go with them.
        "PIL.AvifImagePlugin", "PIL.JpegImagePlugin", "PIL.Jpeg2KImagePlugin",
        "PIL.WebPImagePlugin", "PIL.TiffImagePlugin", "PIL.GifImagePlugin",
        "PIL.BmpImagePlugin", "PIL.PpmImagePlugin", "PIL.PcxImagePlugin",
        "PIL.SgiImagePlugin", "PIL.SunImagePlugin", "PIL.QoiImagePlugin",
        "PIL.DdsImagePlugin", "PIL.FliImagePlugin", "PIL.MpoImagePlugin",
        "PIL.HtJpegImagePlugin", "PIL.IbmImagePlugin", "PIL.IcoImagePlugin",
        "PIL.PsdImagePlugin", "PIL.TgaImagePlugin", "PIL.EpsImagePlugin",
        "PIL.WmfImagePlugin", "PIL.FpxImagePlugin", "PIL.MicImagePlugin",
        "PIL.FtexImagePlugin", "PIL.HeifImagePlugin",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WinVosk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # no console: the log file is the diagnostic
    disable_windowed_traceback=False,
    icon=str(icon) if icon.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="WinVosk",
)