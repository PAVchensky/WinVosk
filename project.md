# WinVosk

## Project Overview

Offline Russian dictation for Windows. Hold a hotkey, speak, release, and the
recognised text is typed at the caret of the window that was in front. Tray
icon, always-on-top panel, nothing leaves the machine.

This is a fork of [alphacep/vosk-api](https://github.com/alphacep/vosk-api)
(Apache-2.0) and a thin application on top of it. The pinned `vosk` 0.3.45
Python binding published from that repository supplies all audio decoding, the
prebuilt Kaldi decoder and the model format. `src\winvosk\`, `src\run.py`
and `tools\` are original work; no upstream file is vendored or patched, so
moving to a newer `vosk` is a version bump, not a merge. Decoder bugs go
upstream, dictation behaviour bugs go here.

## Domain

- Type: Software, local desktop application (Windows, x64)
- Audience: a single user on a private machine; no network calls, no telemetry
- Language of code and artifacts: English. The interface is Russian or English, chosen in the Settings tab; phrases.txt and the diary are the user's own
- Entry points: `WinVosk.bat` (launcher), `src\run.py` (console),
  `pythonw.exe` (windowless, autostart), `dist\WinVosk\WinVosk.exe` (built,
  windowless, same code)

## Stack

- Python 3.14.2 in `.venv\` — never the system interpreter. Rebuilt 2026-10-02
  from `AppData\Local\Python\bin\python.exe` with the pins
  `WinVosk.bat` prints; `vosk` 0.3.45 ships a `cp314` `win_amd64` wheel
- `vosk` 0.3.45 with `models\vosk-model-small-ru-0.22` (44 MB)
- `sounddevice` 0.5.6 capture, `pystray` 0.19.5 tray, `Pillow` 12.3.0 icon,
  `pyperclip` 1.11.0 only for copying text out, never for inserting it
- Windows APIs through `ctypes` only: no `pywin32`, no `keyboard` package
- Text is typed with `KEYEVENTF_UNICODE` keystrokes, never pasted

## Layout

```
config.py          paths, model resolution, VERSION, tunables, logging
recognizer.py      vosk model + microphone stream (opened per recording) + worker thread, and the sub-frame levels the chip animates from
hotkey.py          global push-to-talk hotkey via WH_KEYBOARD_LL (ctypes), plus its capture mode
keystrokes.py      text typed with KEYEVENTF_UNICODE
vocabulary.py      phrases.txt loader and --vocab-check
theme.py           design tokens and the Pillow painter behind them: the palettes, the spacing and type scales, rounded corners, soft shadows, DWM window dressing, DPI awareness
widgets.py         the panel's own widgets, since Tk has neither rounded corners nor soft shadows nor hover: cards, buttons, choices, switch, field, tabs, scrollbar, scroller, transcript, history row
panel.py           always-on-top Tk panel, three tabs; built unmapped and kept in the tray
overlay.py         focusless chip: eleven bars over a clock, antialiased Pillow plate, centred on the work area
settings.py        settings.json: hotkey list, interface language, interface theme, recording device and six on/off switches, atomic write, defaults on anything unusable
corrector.py       own-word correction on finished utterances, difflib, cutoff in one constant, plus the glue that repairs a word the model split across a space
text.py            every user visible string, ru and en, plus the language switch
tray.py            pystray icon and menu
autostart.py       HKCU\...\Run entry
diary.py           dated history under logs\, the switch that gates it, and the reader behind the history tab
file_transcribe.py fallback: media file to text, plus --self-test
run.py             entry point
tools\             verification probes (hold, typing, hook, settings, history, correct, lang, readme, cleanup), build_exe.py, which prunes _internal\ after PyInstaller, package_release.py, which stages the release archive, and make_images.py, which redraws every README screenshot from the live widgets
WinVosk.spec       PyInstaller build definition: one folder, no console
requirements.txt   the five runtime pins, also the ones WinVosk.bat prints
requirements-dev.txt  pyinstaller, needed only to build
phrases.example.txt   the shipped word-list template; phrases.txt itself is personal
NOTICE             what is whose, for Apache-2.0 sections 4(b) and 4(d)
THIRD_PARTY_NOTICES.md  the same, per dependency
licenses\          the license texts themselves, one file per dependency
llms.txt           the short map an agent reads first
```

No absolute path exists in the source tree: `config.BASE_DIR` comes from
`__file__`, `WinVosk.bat` from `%~dp0`, the `tools\` probes from their own
`__file__`. The checkout can move anywhere without an edit; it currently sits at
`D:\AI\Vosk`. A frozen build is the one exception: there `BASE_DIR` is the
folder the exe is in (`sys.frozen`), so `models\`, `logs\`, `settings.json` and
`phrases.txt` are read and written next to it.

`D:\AI\Vosk` is the only checkout: it is what `origin` tracks and what gets
pushed. `D:\AI\WinVosk` is an older tree kept on this machine as a staging area
for release assets and for the SEO documents under `docs\` — its `src\` stopped
on 2026-10-02 and has none of the toggle mode, `--check-bundle` or
`README.ru.md`. Nothing is pushed from it, and its `WinVosk.spec` must never be
copied over this one: it collects `vosk` with `collect_all`, which drags the
whole TLS stack into the bundle. Anything wanted from there is ported here
deliberately; edit it here, because here is the repository.

`settings.json` at the checkout root is the one file that is machine state
rather than part of the checkout: gitignored, atomically written, and read from
disk on every start, so it overrides `config.HOTKEYS` and the shipped switch
defaults and never has to be kept in step with them.

## Commands

Run everything from the project root with the venv interpreter.

```powershell
.\.venv\Scripts\python.exe .\src\run.py                 # start, tray icon
.\.venv\Scripts\python.exe .\src\run.py --diagnose     # model, devices, hotkeys, base dir
.\.venv\Scripts\python.exe .\src\run.py --vocab-check  # which custom words the model hears
.\.venv\Scripts\python.exe .\src\run.py --check-bundle  # Tcl, ttk and Pillow, no microphone
.\.venv\Scripts\python.exe .\src\run.py --autostart on|off
.\.venv\Scripts\python.exe .\src\winvosk\file_transcribe.py call.mp3
.\.venv\Scripts\python.exe .\tools\cleanup.py          # always before a probe
.\.venv\Scripts\python.exe .\tools\hold_probe.py
.\.venv\Scripts\python.exe .\tools\typing_probe.py
.\.venv\Scripts\python.exe .\tools\settings_probe.py   # headless: no GUI, mic or model
.\.venv\Scripts\python.exe .\tools\history_probe.py    # headless: the history reader and its gate
.\.venv\Scripts\python.exe .\tools\correct_probe.py    # headless: correction rules and cost
.\.venv\Scripts\python.exe .\tools\readme_probe.py     # headless: the GitHub-facing pages
.\.venv\Scripts\python.exe .\tools\build_exe.py        # build dist\WinVosk\
```

## Rules

The verification bar, the invariants and the release procedure are **not** repeated
here. They are stated once, in `AGENTS.md`, and a second copy is a second thing to
forget \u2014 the two files did disagree about the heading rule until this was cut:

- `AGENTS.md` \u00a7 Verification \u2014 the six checks every change must clear
- `AGENTS.md` \u00a7 Invariants worth keeping \u2014 each rule with the reason it exists
- `AGENTS.md` \u00a7 Release \u2014 what a release is, and how `VERSION` works

## Documentation

Four tracked documents, one job each. The rules for keeping them in step are in
`AGENTS.md` \u00a7 Documentation.

- `README.md` \u2014 the page GitHub shows, and the user guide, in English
- `README.ru.md` \u2014 the same guide in Russian: same sections in the same order,
  its own anchors
- `docs\HOWTO.md` \u2014 the English reference: internals, layout, probes, caveats
- `llms.txt` \u2014 the short map an agent reads first

Marketing and delivery records are not in the repository. `docs\competitors.md` and
`docs\seo_keywords.md` are local working notes, `docs\instructions\` holds agent
prompts rather than product documentation, and `STAGES.md` is this machine's stage
log.
