# Third party notices

WinVosk itself is original work under the Apache License 2.0 (`LICENSE`,
`NOTICE`). Everything below is someone else's, reached either through
`pip install` or by being collected into the binary build. Full texts are in
`licenses/`; this file exists so you can see, in one place, what is here and why
it is allowed.

## Installed Python packages

| Package | Version | License | Used for | Text |
| --- | --- | --- | --- | --- |
| vosk | 0.3.45 | Apache-2.0 | the recogniser, the Kaldi decoder | `licenses/apache-2.0.txt` |
| sounddevice | 0.5.6 | MIT | microphone capture | `licenses/sounddevice-LICENSE.txt` |
| pystray | 0.19.5 | LGPL-3.0 | the tray icon and its menu | `licenses/pystray-COPYING.txt`, `licenses/pystray-COPYING.LGPL.txt` |
| Pillow | 12.3.0 | MIT-CMU | the generated tray icon | `licenses/pillow-LICENSE.txt` |
| pyperclip | 1.11.0 | BSD | copying text out, never in | `licenses/pyperclip-LICENSE.txt`, `licenses/pyperclip-AUTHORS.txt` |
| pyinstaller | 6.22.3 | GPL-2.0-or-later with a bundling exception | building `WinVosk.exe` | `licenses/pyinstaller-COPYING.txt` |
| pyinstaller-hooks-contrib | 2026.8 | GPL-2.0-or-later with a bundling exception | build hooks | `licenses/pyinstaller-hooks-contrib-LICENSE.txt` |
| altgraph | 0.17.5 | MIT | build time only | `licenses/altgraph-LICENSE.txt` |
| pefile | 2024.8.26 | MIT | build time only | `licenses/pefile-LICENSE.txt` |
| pywin32-ctypes | 0.2.3 | PSF-2.0 | `ctypes` shims for Windows APIs | `licenses/pywin32-ctypes-LICENSE.txt` |

The `vosk` wheel declares `License: UNKNOWN` in its metadata and ships no
license file. Its classifier says Apache, and the project it is built from,
`alphacep/vosk-api`, is Apache-2.0, so that is the license used here and
`NOTICE` credits it explicitly.

## Bundled typefaces

| Family | Version | License | Used for | Text |
| --- | --- | --- | --- | --- |
| Space Grotesk | 2.000 | SIL OFL 1.1 | the panel's text, labels and buttons | `fonts/SpaceGrotesk-OFL.txt`, `licenses/spacegrotesk-OFL.txt` |
| JetBrains Mono | 2.304 | SIL OFL 1.1 | the model name, the timers, the monospace readouts | `fonts/JetBrainsMono-OFL.txt`, `licenses/jetbrainsmono-OFL.txt` |

Both are redistributed unmodified, in the three weights the panel uses
(Regular, Medium, Bold), and `theme.load_fonts` registers them with the running
process only through `AddFontResourceExW(FR_PRIVATE)` — nothing is installed into
Windows and no font is registered for any other program. They travel in the
bundle as `fonts\` next to the exe rather than inside `_internal\`, because the OFL
asks for the licence to travel with the font and `config.FONTS_DIR` is the folder
the app already reads its own files from. The author lists are
`fonts/SpaceGrotesk-AUTHORS.txt` and `fonts/JetBrainsMono-AUTHORS.txt`.

The versions above are the version strings in the files themselves (OpenType name
ID 5), not the names of the folders they were downloaded under.

## Inside `WinVosk.exe`

| Component | License | Notes |
| --- | --- | --- |
| `libvosk.dll` | Apache-2.0 | Kaldi and OpenFst linked in statically |
| `libstdc++-6.dll`, `libgcc_s_seh-1.dll`, `libwinpthread-1.dll` | GPL-3.0 with the GCC Runtime Library Exception | `licenses/gcc-runtime-library-exception.txt` |
| `_sounddevice_data\portaudio.dll` | MIT | PortAudio |
| `python314.dll`, the interpreter | PSF License | `licenses/python-LICENSE.txt` |
| `tcl86t.dll`, `tk86t.dll` | Tcl/Tk terms | `licenses/tcl-tk-license.terms` |
| PyInstaller bootloader | GPL-2.0-or-later with a bundling exception | `licenses/pyinstaller-COPYING.txt` |

CLDR data is inside `libvosk.dll` under the Unicode License v3 (`Unicode-3.0`);
it is attribution only, with no source to ship.

## Speech model

`models\vosk-model-small-ru-0.22` is published by Alpha Cephei Inc at
<https://alphacephei.com/vosk/models>, where it is listed under the Apache
License 2.0, and is redistributed here unmodified. The archive contains no
license file of its own.

That page is also the place to check before shipping a different model: several
of them are published under AGPL or CC-BY-NC-SA, which do not allow the kind of
redistribution a release archive does. Models marked Apache 2.0, MIT or LGPL can
go in; the others must not.

## Checked on

2026-10-02, Windows x64, Python 3.14.2, from the versions installed by
`requirements.txt` and the resulting `dist\WinVosk\` folder.