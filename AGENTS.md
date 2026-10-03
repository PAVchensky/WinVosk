# WinVosk

Offline Russian dictation for Windows. Global hotkey, tray icon, always-on-top
panel, and the recognised text is typed into the window you were typing in.
Nothing leaves the machine.

Checkout root: `D:\AI\Vosk`. Nothing in the project hardcodes it, so a move
needs no edit: `config.BASE_DIR` is derived from `__file__`, `WinVosk.bat`
from `%~dp0`, the `tools\` probes from their own `__file__`, and every command
below is relative. Run them from the project root.

It is the only checkout, and `origin` is `PAVchensky/WinVosk` on it.
`D:\AI\WinVosk` is an older tree on this machine, kept only as a staging area for
release assets and for the SEO documents under `docs\`: its `src\` stopped on
2026-10-02, so it has none of the toggle mode, `--check-bundle` or `README.ru.md`,
and its history is unrelated. Never push from it, and never copy its
`WinVosk.spec` over this one — it collects `vosk` with `collect_all`. Anything
wanted from there is ported here deliberately; edit it here, because here is the
repository.

## Release

`VERSION` in `src\winvosk\config.py` is the single source of the release number,
currently **1.1**. It is not a comment and not a tag nobody reads: `--diagnose`
prints it on its first line, the panel puts it in the window title, and the
own-word report and the frozen `--diagnose` dialog carry it.
`winvosk\__init__.py` derives `__version__` from it rather than repeating it —
a second literal there already disagreed with this one, in a different format.

**Bump it with every release.** `1.0` → `1.1` for added or changed behaviour,
`2.0` when something a user depends on changes or is removed. A patch release
gets `1.0.1` only for a fix that changes no behaviour a user can observe.

A release is: `VERSION` bumped, all six checks in § Verification green, the
bundle rebuilt with `tools\build_exe.py`, the archive staged with
`tools\package_release.py`, and `README.md` checked for anything the change made
untrue. There is no separate changelog file; `history.md` and `STAGES.md` are
append-only records and are not the release notes.

`package_release.py` is what makes the archive the README tells a user to
download. It takes `dist\WinVosk\` and removes what is the user's — `phrases.txt`,
`settings.json`, `logs\` — adds `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`,
`licenses\` and `phrases.example.txt`, then prints the SHA-256. It refuses to
finish if anything personal survived, so never hand it a `dist\` you built from
a folder you meant to keep private. `phrases.txt` itself is not in the
repository at all: the shipped template is `phrases.example.txt`.

## Documentation

Three documents, and they do different jobs. Do not merge them and do not let
them drift apart.

- **`README.md`** — the main page and the user guide, in English: install,
  unpack, run, every setting, `phrases.txt`, what to do when recognition is poor,
  and the table of every language Vosk publishes a model for. Written for someone
  who has never seen the source.
- **`README.ru.md`** — the same guide in Russian. **The two are edited as one
  document**: same headings in the same order, in English, with the Russian text
  on the line under each. That is deliberate, because a GitHub anchor is derived
  from the heading text, so a translated heading breaks every cross-link into the
  other file. Same rule for the tables and the numbered sections. When you change
  one, change the other in the same commit, or one of them is a lie.
- **`docs\HOWTO.md`** — the reference, in English: internals, layout, why each
  design decision was taken, the verification helpers, the caveats.
- **`llms.txt`** and **`docs\instructions\setup.md`** — the short map an agent
  reads first, and the install procedure behind it as an ordered sequence with
  the traps. Both point at `README.md`, this file and `project.md` rather than
  repeating them.

`AGENTS.md` is agent-facing and `project.md` is project context; neither is a
user guide. When a change makes a statement in any of them untrue, fix the
statement in the same change — a documented promise that no longer holds is the
defect, not the doc.

## Upstream

This is a fork of [alphacep/vosk-api](https://github.com/alphacep/vosk-api) —
the Vosk Speech Recognition Toolkit by AlphaCephei, Apache-2.0. All audio
decoding comes from there: the pinned `vosk` 0.3.45 is the Python binding
published out of that repository's `python\` directory and carries the prebuilt
Kaldi decoder with its native libraries. Upstream also owns the model format
and the `KaldiRecognizer` behaviour that several invariants below depend on.

The fork is a thin application on top of it. `src\winvosk\`, `src\run.py`
and `tools\` are original work, no upstream file is vendored, and nothing in
upstream is patched in place, so moving to a new `vosk` is a version bump rather
than a merge. Report decoder bugs upstream and application bugs here.

## Stack

Python 3.14.2 in `D:\AI\Vosk\.venv` (not the system interpreter). `vosk` 0.3.45
with `models\vosk-model-small-ru-0.22`, `sounddevice` 0.5.6 for capture,
`pystray` 0.19.5 for the tray, `Pillow` 12.3.0 for the generated icon,
`pyperclip` 1.11.0 for copying text out. Those five pins are the ones
`WinVosk.bat` prints when the venv is missing; `vosk` 0.3.45 publishes a
`cp314` `win_amd64` wheel, so nothing has to be built. Windows APIs are called
through `ctypes` only, so no `pywin32` and no `keyboard` package. Recognised
text is typed into the active window with `KEYEVENTF_UNICODE` keystrokes rather
than pasted.

Run everything with the venv interpreter:
`.\.venv\Scripts\python.exe .\src\run.py`.
There is a console build (`python.exe`) and a windowless one (`pythonw.exe`).
`WinVosk.bat` launches it relative to itself, so the launcher survives a
move without an edit.

Paths inside the app are derived from `__file__` in `config.py`
(`BASE_DIR = Path(__file__).resolve().parents[2]`), and the `tools\` probes
insert `<project>\src` resolved from their own location. There is no absolute
path in the source tree at all, so the checkout can live anywhere.

The built bundle is the one exception: `tools\build_exe.py` drives PyInstaller
over `WinVosk.spec` into `dist\WinVosk\`, and `config.FROZEN` makes `BASE_DIR`
the folder the exe is in, so `models\`, `logs\`, `settings.json` and
`phrases.txt` live beside the exe. A windowless exe has no stdout, so
`--diagnose`, `--autostart`, `--vocab-check` and `--check-bundle` write
`logs\report.txt` and show a message box instead of printing.

## Verification

Every change must clear all six checks before it is considered done, from the
project root.

```powershell
# 1. syntax and imports
.\.venv\Scripts\python.exe -m compileall -q .\src

# 2. model and device report
.\.venv\Scripts\python.exe .\src\run.py --diagnose

# 3. recogniser pipeline on known input, no microphone involved
.\.venv\Scripts\python.exe .\src\winvosk\file_transcribe.py --self-test

# 4. push to talk, then typing at the caret
.\.venv\Scripts\python.exe .\tools\cleanup.py
.\.venv\Scripts\python.exe .\tools\hold_probe.py
.\.venv\Scripts\python.exe .\tools\typing_probe.py

# 5. real speech end to end, then read the result
#    hold alt+win, speak, let go
Get-Content .\logs\app.log -Tail 20
Get-Content .\logs\<yyyy-mm-dd>.txt -Encoding UTF8 -Tail 5

# 6. the GUI path a console check cannot reach: Tcl, ttk and Pillow
.\.venv\Scripts\python.exe .\src\run.py --check-bundle
```

Check 2 must print a `base dir` line that is the checkout root, currently
`base dir    : D:\AI\Vosk`; anything else means the app resolved paths somewhere
else and the rest of the bar is meaningless. Its first line must be
`WinVosk   : 1.1`, which is the cheap way to notice that `VERSION` was not bumped.

Check 3 must print an empty string for silence, never raise. Check 4 must print
`VERDICT: PASS` twice: once for the hotkey, once for typing, the latter with
`focus drift 0`. Check 5 must produce a new diary line containing the words that
were spoken, and the log must show `typed N character(s)`. A clean `app.log` is
part of the bar: `WARNING`, `ERROR` or any `hotkey hook failed` line means the
change is not finished.

Check 6 builds the real panel, resolves the `ttk` theme, checks that the window
was never mapped at start up, that a tray click brings it up, and that the chip
maps with its Pillow plate while the panel is in the tray, then reports. It is in
the bar rather than optional because a bundle can be missing a Tcl script or a
Pillow extension while every console flag still works: `import tkinter` succeeds
long before the first `ttk` widget asks for its theme, and `from PIL import Image`
succeeds before the first `ImageTk.PhotoImage` asks for the extension. Only a
recording would find out, in front of the user. It opens no microphone, so it also
runs on a machine with no input at all. Run it after any change to `WinVosk.spec`,
`tools\build_exe.py`, `overlay.py`, `tray.py` or `panel.py`, and against the
built exe as well as the checkout.

A plain `pythonw.exe` launch has no console, so the log file is the only
diagnostic. Never trust a silent start.

`tools\settings_probe.py` is a sixth check that is not part of the bar: it is
headless, needs no GUI, microphone, model or real hook, and covers the
`settings.json` keys, the switches and the hotkey capture. Run it after any
change to `settings.py`, `panel.py` or the settings part of `run.py`.
`tools\correct_probe.py` is the seventh, same shape: it covers the own-word
correction rules, the cutoff boundary and the cost, plus the wiring in `run.py`
that keeps the correction off the partials. Run it after touching `corrector.py`,
`phrases.txt` or the correction part of `run.py`.
`tools\lang_probe.py` is the eighth: it reads the source instead of running it,
and covers the message table and the language switch. Run it after any change to
`text.py`, `settings.py`, `panel.py`, `tray.py` or the message part of `run.py`.

## Invariants worth keeping

- **Never add the `keyboard` package.** Its Windows backend never delivers hotkeys.
  See the "Why the hotkey is hand written" section of `docs/HOWTO.md`.
- **Never trust PortAudio's default input device.** On this machine
  `Pa_GetDefaultInputDevice()` answers `paNoDevice` even though Windows does
  have a microphone, so `device=None` raises `Error querying device -1` and the
  engine never opens. `recognizer.input_device()` resolves the index from the
  host API instead, and `--diagnose` prints the `records from` line that proves
  which device a run will actually use. The one input device WDM-KS exposes
  takes only its native rate, so a 16 kHz request fails there too; that is a
  machine fact, not something the app can talk its way out of.
- **Never insert text through the clipboard.** Typing with `KEYEVENTF_UNICODE`
  is layout independent, needs no focus switching, and cannot paste into the
  wrong window. `SetForegroundWindow` is refused for a process that neither
  owns the foreground nor received the last input, so focus based insertion is
  unreliable by design. Copying the recognised text *out* to the clipboard is a
  separate, optional step and is never how anything is inserted.
- **The hotkey records while it is held by default, and toggles only when asked.**
  `HotkeyListener` takes both `on_press` and `on_release`; the main key must be
  blocked from keydown until its keyup or key repeat turns one hold into a stream
  of presses. Push to talk and toggle are not a flag inside the hook: they are the
  presence or absence of `on_release`, so `App._install_hotkey` reads
  `settings.toggle_recording()` and builds the listener accordingly. Deciding the
  mode inside the hook would leave a listener that can be told it is push to talk
  and behave otherwise.
- **In toggle mode the decision is made on the pump thread, never in the hook.**
  `App._hotkey_pressed` reads `_recording` at handling time, because the callback
  runs on the hook thread and would see a state that has not caught up with the
  first press — a quick second press would be taken for another start.
- **A missed release is why push to talk exists, so toggle mode needs a ceiling.**
  `MAX_SESSION_SECONDS` (180 s) is no longer a belt-and-braces limit but the thing
  that stops a recording nobody can end, because a toggle is ended by a second
  press rather than by letting go. **Стоп** on the panel and **Остановить запись**
  in the tray are the other two ways out and stay enabled for the whole session.
  The `hotkey_hint` under the switch has to say so; a mode that can only be left
  by pressing the same key again is not a safe default, which is why
  `config.TOGGLE_DEFAULT` is `False`.
- **Never pass a phrase list to `KaldiRecognizer` during dictation.** A grammar
  is a hard vocabulary restriction, not a bias: measured on this machine, the
  same audio that yields a full sentence in free decoding yields the empty
  string with a three phrase grammar. `--vocab-check` is the safe way to
  consult a word list.
- **Never correct a partial.** `corrector.correct` runs on finished utterances
  and on the tail only, because partials are typed as they arrive and the
  finished text is diffed against them; correcting both would make the screen
  jump around for words the model has not settled on. Every replacement is
  logged, and a token that begins with a listed word is never touched, so an
  inflection of the user's own word survives.
- **Two tokens are one word to the corrector, not two.** The model knows
  «дропбокс» and still splits it: «друг бокс», where no single token can match
  any entry. `corrector.correct` therefore glues neighbouring tokens and
  compares the pair, forward only and only when both halves are at least
  `JOIN_MIN` letters, which is what keeps `с` + `воих` from becoming a listed
  `своих`. A split into three tokens is not handled on purpose: «йо цун фэнь»
  would come out as «йо цунфэнь», so widening the glue needs a real word first.
- **Vosk revises its own output.** `Result()` and `PartialResult()` both report
  the whole open utterance, and the model changes its mind mid sentence. Every
  update must be applied as a diff against what was typed, or the screen fills
  with duplicated and half corrected words. After a finished utterance the
  prefix resets.
- **Never type into this app's own window.** `foreign_in_front()` gates all
  typing, and a held fragment is dropped rather than carried over.
- **The `INPUT` struct must be 40 bytes on x64.** The union has to include a
  full `MOUSEINPUT`; a 24 byte padding makes `SendInput` fail with a silent
  return of 0, which looks like a focus problem rather than a struct problem.
  `keystrokes.py` asserts the size at import time.
- **Block only the main key** in the hook. Modifiers must reach the foreground
  application or they stick down and break typing everywhere else. Held keys
  must not re-fire: check that the main key is not already in the blocked set.
- **The auto repeat of a blocked key has to be blocked too.** `_blocked` stops a
  held key from firing the callback again, but on its own it let every repeat
  through to Windows: the application never saw the first keydown, so a repeat is
  a keydown out of nowhere, and `Ctrl + Menu` opened a context menu behind a
  swallowed press. `_on_event` now swallows when the repeated key is the blocked
  one. It must test `vk in self._blocked`, **not** "the combination matched":
  a held combination still matches for every other key pressed beside it, so the
  second form would eat the user's typing. `settings_probe.py` case 9 drives
  `_on_event` with fabricated structs and pins both halves.
- **Never leave a bad combination taking the good ones with it.** One unusable
  entry in `settings.json` is dropped by itself and named in the panel hint and
  the tray, every start — the file is meant to be edited by hand, and silently
  reverting the whole list to the defaults left the hotkey quietly not being the
  one that was stored. `menu`, `apps` and `context_menu` all name 0x5D, so a
  typo in the key's name is not the reason a combination cannot be parsed.
- **The panel must not take focus** when a hotkey fires from another
  application, otherwise the words are typed into the panel.
- **A settings switch is written only by the app**, from the value the panel just
  set, and a failed write puts the switch back to what is really in effect. The
  panel owns no state: `settings.py` is read from disk on every use, so what the
  checkbox shows and what the app acts on cannot drift apart.
- **Every user visible string lives in `winvosk/text.py`** as a key with both
  languages, and nothing else may hold one: `tools\lang_probe.py` fails on any
  Cyrillic string literal elsewhere. A language change repaints widgets in place,
  never by rebuilding the window — the caret, the recording state and the chip
  would all have to be restored by hand.
- **Only one instance may run.** Enforced by the `Local\WinVoskSingleInstance`
  mutex, because two instances fight over the microphone. A venv launch shows
  two processes in the task manager; that is the launcher shim, not a bug.
- **The panel starts unmapped and the tray is the only way in.** `Panel.__init__`
  withdraws the root before building a widget, because a start that mapped the
  window would flash and would take the focus from whatever the user was typing
  into — the dictated words would land in the panel. A `Toplevel` of a withdrawn
  root still maps, which is what lets the chip show while the panel is in the
  tray, and check 6 asserts it. A modal dialog gets `parent` only while the panel
  is up, because a dialog parented to a withdrawn window comes up behind
  everything else or not at all.
- **The Windows Search panel holds the foreground** and refuses to give it up.
  Verification probes must close it, and `cleanup.py` must run first or a
  leftover target keeps the focus. `cleanup.py` matches only python processes
  whose command line holds the target script, because matching a bare name also
  kills the shell that launched the probe.
- **Download models from the HuggingFace mirror.** `alphacephei.com` throttles
  large files to unusable speed on this network.
- **A Russian model always wins, but any model is better than none.**
  `config.resolve_model` takes `MODEL_NAME` outright, then any other model
  carrying an `am` directory, Russian ones sorted first. Never glob a model on a
  language substring: `vosk-model*ru*` also matches `vosk-model-small-uz-0.22`,
  which is why `config.is_russian_model` compares whole hyphen separated tokens.
  The decoder does not care about the language, and the corrector is pure
  difflib over tokens, so a non-Russian model works — but `phrases.txt` then has
  to be in that language or the correction finds nothing.
- **Never name a local `text` in a module that imports `winvosk.text`.** It
  shadows the module for the whole function, and the shadow only bites on an
  error path: `recognizer._run` had `text = data.get("text", "")` in its decode
  loop and `text.t("engine_failed")` in its startup `except`, so a microphone
  that would not open raised `UnboundLocalError` instead of reporting itself —
  under `pythonw.exe`, in front of nobody.
- **Never collect `vosk` with `collect_all`.** It returns every submodule, and
  `vosk.transcriber` is a client for a vosk-server this app never runs; naming
  it as a hidden import dragged `websockets`, `socks` and then the whole TLS
  stack into the bundle. `WinVosk.spec` takes `collect_dynamic_libs` and
  `collect_data_files` and adds only `vosk.vosk_cffi` by hand.
- **A prune pattern that matched nothing is a finding, not noise.**
  `tools\build_exe.py` prints it on purpose: an upstream rename that leaves a
  dead `_imagingft.pyd` or a live `tzdata` in place has to be visible in the
  build log. After touching `PRUNE`, `excludes` or the spec, rebuild and run
  check 6 against the built exe, not only against the checkout.
- **What cannot be packed, and why.** No `.pyd` or `.dll` can go into an archive:
  the Windows loader opens them by path. Pure Python already is packed — the
  stdlib into `base_library.zip` and every other module into the `PYZ` inside
  the exe, which is why `_internal` holds only binaries and data. Tcl's script
  library is the one large tree left, and Tk finds it as files on disk. So the
  lever is pruning, not packing; `upx=True` would trade startup time and AV
  heuristics for about 25 MB and is deliberately off.
