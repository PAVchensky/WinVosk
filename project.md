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
- Language of code and artifacts: English. The interface is Russian or English, chosen in Настройки; phrases.txt and the diary are the user's own
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
recognizer.py      vosk model + microphone stream + worker thread, and the sub-frame levels the chip animates from
hotkey.py          global push-to-talk hotkey via WH_KEYBOARD_LL (ctypes), plus its capture mode
keystrokes.py      text typed with KEYEVENTF_UNICODE
vocabulary.py      phrases.txt loader and --vocab-check
theme.py           design tokens and the Pillow painter behind them: the palettes, the spacing and type scales, rounded corners, soft shadows, DWM window dressing, DPI awareness
widgets.py         the panel's own widgets, since Tk has neither rounded corners nor soft shadows nor hover: cards, buttons, choices, switch, field, tabs, scrollbar, scroller, transcript
panel.py           always-on-top Tk panel, two tabs; built unmapped and kept in the tray
overlay.py         focusless chip: eleven bars over a clock, antialiased Pillow plate, centred on the work area
settings.py        settings.json: hotkey list, interface language, interface theme and on/off switches, atomic write, defaults on anything unusable
corrector.py       own-word correction on finished utterances, difflib, cutoff in one constant, plus the glue that repairs a word the model split across a space
text.py            every user visible string, ru and en, plus the language switch
tray.py            pystray icon and menu
autostart.py       HKCU\...\Run entry
diary.py           dated history under logs\
file_transcribe.py fallback: media file to text, plus --self-test
run.py             entry point
tools\             verification probes (hold, typing, hook, settings, correct, lang, readme, cleanup), build_exe.py, which prunes _internal\ after PyInstaller, package_release.py, which stages the release archive, and make_images.py, which redraws every README screenshot from the live widgets
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
.\.venv\Scripts\python.exe .\tools\correct_probe.py    # headless: correction rules and cost
.\.venv\Scripts\python.exe .\tools\readme_probe.py     # headless: the GitHub-facing pages
.\.venv\Scripts\python.exe .\tools\build_exe.py        # build dist\WinVosk\
```

## Verification

The standing bar is the six checks in `AGENTS.md` § Verification:
`compileall`, `--diagnose` (its `base dir` line must be the checkout root, and
its first line the release number), `file_transcribe.py --self-test`,
`cleanup.py` + `hold_probe.py` + `typing_probe.py` (two `VERDICT: PASS`, typing
with `focus drift 0`), one real dictation producing a new
`logs\YYYY-MM-DD.txt` line plus `typed N character(s)` in `logs\app.log`, and
`--check-bundle`, which builds a window, resolves the `ttk` theme and draws the
chip without opening a microphone. A `WARNING`, `ERROR` or `hotkey hook failed`
line in `app.log` means the change is not finished. Checks 4 and 5 need a human
at the keyboard and cannot be automated — an agent session has no foreground
window at all, so `SendInput` injects nothing and the probes cannot pass there.

`tools\settings_probe.py`, `tools\correct_probe.py`, `tools\lang_probe.py` and
`tools\readme_probe.py` are headless checks that are not part of that bar: they
need no GUI, microphone, model load or real hook, print `VERDICT: PASS`/`FAIL`,
and cover the key-name mapping and the spec round trip, the capture rules, the
`settings.json` fallbacks including the switches and a byte order mark, that
leaving the capture hands the keyboard back, the own-word correction rules and
their cost, the message table — including that no string literal containing
Cyrillic exists outside `winvosk\text.py` — and the three GitHub-facing pages:
dead anchors, Cyrillic that escaped into English prose, control names that no
longer match `text.py`, a `settings.json` example that names the wrong shipped
language, the corrector cutoff stated backwards, and heading parity between the
two guides.

## Invariants

Detail and rationale in `AGENTS.md` § Invariants worth keeping. In short:

- never add the `keyboard` package — its Windows backend never delivers hotkeys
- never insert text through the clipboard, and never type into this app's own
  window; copying text out to the clipboard is a separate, optional step
- never take PortAudio's default input device on trust: it answers
  `paNoDevice` on this machine, and the only input device it exposes takes its
  native rate, not 16 kHz — `recognizer.input_device()` resolves the index
- a settings switch is written only by the app, from the value the panel just
  set, and a failed write puts the switch back to what is really in effect
- every user visible string lives in `winvosk\text.py` as a key with both
  languages; a language change repaints the widgets in place and never rebuilds
  the window
- the recording chip is a decorative animation, not a level meter, and it must never
  take focus: a stolen focus sends the dictated words into the chip instead of the user's document
- the hotkey is push to talk, never a toggle; the main key alone is blocked
- while the hotkey capture is live the hook swallows every key system wide, and
  every exit from it must hand the keyboard back
- a stored hotkey is never handed to the hook unparsed, and a failed registration
  rolls back to the previous combination instead of leaving no hotkey at all
- never pass a phrase list to `KaldiRecognizer` during dictation — a grammar is a hard restriction
- the correction pass touches finished utterances only, never partials, and never a
  word that is an inflection of one the user listed
- vosk 0.3.45 has no word boosting: `SetWords` is a boolean for word timestamps,
  so an own-word correction has to happen after the decode
- apply every Vosk revision as a diff against what was already typed
- the `INPUT` struct must stay 40 bytes on x64
- one instance only, enforced by the `Local\WinVoskSingleInstance` mutex
- download models from the HuggingFace mirror; `alphacephei.com` throttles
- a Russian model wins but any Kaldi model is accepted, so the language table in
  `README.md` is real; the `ru` test is a whole hyphen separated token, never a
  substring, which is what keeps `uz` out
- never name a local `text` in a module that imports `winvosk.text`; the shadow
  only bites on an error path, under `pythonw.exe`, in front of nobody
- never collect `vosk` with `collect_all`: `vosk.transcriber` is a server client
  and drags the TLS stack in with it
- a prune pattern in `tools\build_exe.py` that matched nothing is reported, not
  noise, and `--check-bundle` is what proves a prune did not go too far
- nothing in `_internal` can be packed: no `.pyd`/`.dll` can live in an archive
  and Tk finds its scripts as files on disk

## Documentation

- `README.md` — the main page and the user guide: install, unpack, run, every
  setting, `phrases.txt`, poor recognition, the 32 model languages. It is written
  in English and is the page GitHub shows, so it names every control in English
  and carries no Cyrillic outside a fenced block, a table row of input/output
  pairs, or an inline code span quoting what a tool printed
- `README.ru.md` — the same guide in Russian; edited as one document with
  `README.md`, same sections in the same order and the same headings at the same
  levels, each in its own language. A GitHub anchor comes from the heading text, so
  the anchors are per-file and differ between the two: `#установка-и-запуск` here,
  `#install-and-run` there. Keep them in step by section number, not by string.
  `tools\readme_probe.py` is what notices when one file gains a heading and the
  other does not
- `docs\HOWTO.md` — English throughout, Cyrillic only as a quoted control name or
  a quoted token; a Russian heading there is a defect
- `docs\instructions\setup.md` — the install procedure as an ordered sequence,
  with the traps, in the repository and pointed at by `llms.txt`
- `llms.txt` — the short map an agent reads first
- `AGENTS.md` — authoritative agent-facing notes, verification bar, invariants
- `docs\HOWTO.md` — the reference: internals, layout, design rationale, probes
- `project.md` — this file: project context
- `STAGES.md` — stage tracking, local to this checkout and not published
- Project knowledge and decisions live in SynaptoMind, project `Vosk`
  (`local_path` `D:/AI/Vosk`), not in this tree

`STAGES.md`, `history.md` and `MEMORY.MD` are stage/history records: append,
do not rewrite. They are listed in `.gitignore` along with the four
`docs\instructions\` files that are agent prompts rather than product
documentation — `build.md`, `plan.md`, `review.md`, `debug.md` — and with
`docs\stages\`, because they record this machine's delivery process rather
than the product, so they stay out of the published repository while staying on
disk here. `setup.md` is the exception and is tracked. Before 2026-10-02 this
file described an unrelated project
(Teleread, Python 3.4, server `mjd`); that text was stale and has been replaced.