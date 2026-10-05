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
currently **1.9.1**. It is not a comment and not a tag nobody reads: `--diagnose`
prints it on its first line, the panel puts it in the window title, and the
own-word report and the frozen `--diagnose` dialog carry it.
`winvosk\__init__.py` derives `__version__` from it rather than repeating it —
a second literal there already disagreed with this one, in a different format.

**The scheme is `MAJOR.MINOR.PATCH` and all three parts are always written.** A
two part number sorts wrongly in a release list and has nowhere to put a patch.
**Bump it with every release:**

- **PATCH** — a fix that changes nothing a user can observe. `1.6.3` → `1.6.4`.
- **MINOR** — behaviour added, or behaviour changed in a way that is still
backwards compatible. `1.6.4` → `1.7.0`. **Adding `settings.json` keys is
MINOR**, provided every existing file still loads and every existing default
keeps its meaning; the MAJOR wording below is about keys that change or go
away. 1.7.0 was chosen this way for `write_log` and `write_history`, and 1.8.0
for `input_device` plus the recording device card.
- **MAJOR** — something a user depends on changes or is removed: `settings.json`
  keys, a hotkey default, a switch that stops existing, the insertion method.
  `1.7.0` → `2.0.0`.

A documentation-only change does not warrant a release of its own; it rides along
with whatever code change it documents. That is why the number is not bumped for
every commit, only per release.

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

Four tracked documents, and they do different jobs. Do not merge them and do not
let them drift apart. Anything not in this list is not a document of the product:
marketing notes and this machine's delivery records are local and gitignored.

- **`README.md`** — the main page and the user guide, in English: install,
  unpack, run, every setting, `phrases.txt`, what to do when recognition is poor,
  and the table of every language Vosk publishes a model for. Written for someone
  who has never seen the source.
- **`README.ru.md`** — the same guide in Russian. **The two are edited as one
  document**: the same sections in the same order and the same headings at the
  same levels, each written in its own language. A GitHub anchor is derived from
  the heading text, so the anchors are per-file and differ between the two —
  `#install-and-run` there, `#установка-и-запуск` here — and every internal link
  is recomputed for the file it lives in. Keep them in step by section number, not
  by string; `tools\readme_probe.py` is what notices when one file gains a section
  and the other does not. Same rule for the tables and the numbered sections. When
  you change one, change the other in the same commit, or one of them is a lie.
  **A renamed heading keeps its old anchor** in an `<a id="...">` line above it,
  because links to a README outlive the text they were written against; there are
  four of them and `readme_probe.py` fails if one is lost.
- **`docs\HOWTO.md`** — the reference, in English: internals, layout, why each
  design decision was taken, the verification helpers, the caveats.
- **`llms.txt`** — the short map an agent reads first: what the project is and
  which of the other three files to open. It points rather than repeats, because a
  copy of the verification commands here is a copy that can go stale.

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
`WinVosk   : 1.9.1`, which is the cheap way to notice that `VERSION` was not bumped.

Check 3 must print an empty string for silence, never raise. Check 4 must print
`VERDICT: PASS` twice: once for the hotkey, once for typing, the latter with
`focus drift 0`. Check 5 must produce a new diary line containing the words that
were spoken, and the log must show `typed N character(s)`. A clean `app.log` is
part of the bar: `WARNING`, `ERROR` or any `hotkey hook failed` line means the
change is not finished.

Check 6 builds the real panel, resolves the `ttk` theme, checks that the window
was never mapped at start up, that a tray click brings it up, that the bottom of
the settings tab is reachable, that exactly one option in each radio group is
marked, that the history tab renders and its last record
can be scrolled to, that the chip maps
with its Pillow plate while the panel is in the tray, and that `Shell_NotifyIcon`
accepts the notification-area icon, then reports. It is in
the bar rather than optional because a bundle can be missing a Tcl script or a
Pillow extension while every console flag still works: `import tkinter` succeeds
long before the first `ttk` widget asks for its theme, and `from PIL import Image`
succeeds before the first `ImageTk.PhotoImage` asks for the extension. Only a
recording would find out, in front of the user. It opens no microphone, so it also
runs on a machine with no input at all. Run it after any change to `WinVosk.spec`,
`tools\build_exe.py`, `overlay.py`, `tray.py` or `panel.py`, and against the
built exe as well as the checkout.

The tray icon is the one part of check 6 that was missing until the 1.2 release, and
it is
the part that cannot be reached any other way: `pystray.Icon.run_detached()` only
starts a thread, the icon is added from a thread of pystray's own, and the panel
lives in the tray — so a bundle whose icon never arrives has no user interface at
all, while `import pystray` and every console flag report success. `tray.run()`
therefore waits for `TrayIcon.visible` and logs a **warning** if it never arrives,
and check 6 fails on it. Under `console=False` that warning is the only evidence
there will be: see the next invariant.

**Never force the tray icon back.** `pystray.Icon.visible` is set from pystray's
own side of `Shell_NotifyIcon`, and it is never told whether the shell took it,
so the only way to make pystray issue a second `NIM_ADD` — `visible = False` then
`True` — reports success on its first attempt whether or not the notification area
has the icon. Wait for `visible` instead, on a daemon thread that `stop()` ends:
`WM_TASKBARCREATED` covers an Explorer that restarts under a live icon, and the
case it does not cover is a shell that was not ready when the icon first asked.
Measured on a test machine: two starts in a row refused the icon and a third took
it seconds later, and those two starts had no way into the panel at all.

A plain `pythonw.exe` launch has no console, so the log file is the only
diagnostic. Never trust a silent start. This is also why **Write the log file**
off drops `INFO` at the *handler* and never stops the file: `config.file_level`
is the whole switch, the root logger stays at `INFO` so the console flags and the
probes are unaffected, and a run that cannot write a diagnostic line at all is
worse than a noisy one.

`tools\settings_probe.py` is a sixth check that is not part of the bar: it is
headless, needs no GUI, microphone, model or real hook, and covers the
`settings.json` keys — including the recording device, which is a name or an
explicit `null` and refuses a number — the switches and the hotkey capture. Run it
after any change to `settings.py`, `panel.py` or the settings part of `run.py`.
`tools\history_probe.py` is the tenth: same shape, and it covers the history
reader and the switch that gates it — several days read back newest first, a
hand edited line, a byte order mark, a write still in progress, the files in
`logs\` that are not history, the limit, a missing folder, a record in Cyrillic
round-tripped, and `append` obeying the switch. Run it after any change to
`diary.py` or to the history part of `run.py`.
`tools\correct_probe.py` is the seventh, same shape: it covers the own-word
correction rules, the cutoff boundary and the cost, plus the wiring in `run.py`
that keeps the correction off the partials. Run it after touching `corrector.py`,
`phrases.txt` or the correction part of `run.py`.
`tools\lang_probe.py` is the eighth: it reads the source instead of running it,
and covers the message table and the language switch. Run it after any change to
`text.py`, `settings.py`, `panel.py`, `tray.py` or the message part of `run.py`.
`tools\readme_probe.py` is the ninth, same shape again, and covers the three
GitHub-facing pages: dead anchors in each file, Cyrillic that escaped into English
prose, control names that no longer match `text.py`, a `settings.json` example
naming the wrong shipped language, the corrector cutoff stated backwards, and
heading parity between the two guides, and — since the 1.8 release — every local
image a page points at existing and being non-empty. That last rule earned its
place by finding a screenshot that both guides embedded and nobody had committed,
which the other seven could not see: R2 stops at the `#` of an anchor and nothing
else looks at a file. It is the only thing standing between a
plausible sentence and a documented lie - the page once claimed the interface
ships in Russian, and once said a word *more* than 0.75 similar is left alone,
which is the opposite of what `corrector.CUTOFF` does. Run it after any change to
`README.md`, `README.ru.md`, `docs\HOWTO.md`, `text.py`, `corrector.py` or
`config.LANGUAGE_DEFAULT`.
`tools\chip_probe.py` is the eleventh: it needs a Tk window but no keyboard, no
microphone and no model, and it covers the chip and the tab scroll — that the bar
ramp, the clock and the plate are the `chip_*` roles of the current
`theme.Palette` in every theme, that the plate stays dark in all of them, that the
transparent key is a few steps from the plate's fill and is not a colour the chip
paints, that the window really is keyed on it, that `set_theme` recolours a chip
that is already on screen without rebuilding the window under a running recording,
and that a scrolled settings or history tab comes back to its first line and that
`check_*_reachable` puts each page back where it found it. Run it after any change
to `overlay.py`, to the `chip_*` roles in `theme.py`, to `Scroller`, or to the
tab selection in `panel.py`.

## Invariants worth keeping

- **`config` and `settings` never import `theme`.** `theme` imports `tkinter` at
  the top; `config` and `settings` are imported by every console path
  (`--diagnose`, `--vocab-check`, `file_transcribe --self-test`, and the headless
  probes, none of which opens a window). The dependency runs the other way —
  `theme` reads `config.THEMES` and `config.THEME_DEFAULT`, which is why the
  theme names are plain strings in `config`. Inverted, a bundle missing a Tcl
  script or `_tkinter.pyd` would fail on the import inside `--diagnose`, which is
  the one command whose whole job is to say the bundle is broken.
- **No colour, radius, shadow or font is written outside `theme.py` and
  `widgets.py`.** Tk draws no rounded corner and no soft shadow, so every such
  shape is a Pillow image made by `theme.surface()`, and a widget that needs a
  new shade asks the palette for one by role rather than holding a hex literal.
  A literal in a widget is how the two themes stop being one design. The same
  goes for type: sizes are the four steps in `widgets.TYPE_*`, and the family is
  resolved once in `theme.bind`.
- **The window's DWM attributes are written after the map, not before.**
  `deiconify` resets them — measured: a corner preference written before the
  first map reads back as "not rounded" afterwards, and one written after it
  sticks. `Panel._on_map` re-dresses the window every time, for the same reason
  `overlay.py` puts `WS_EX_NOACTIVATE` back every time. `tk.Tk()` also hands out
  a different `wm_frame()` handle before and after its first map, so a
  before-the-map call looks like it worked.
- **A `tk.Variable`'s trace is removed when its widget is.** The variables belong
  to the panel and outlive a theme change, which is the point of them; a trace
  left behind fires into a destroyed canvas, and because that happens inside a Tk
  callback the exception is printed and swallowed rather than raised. The
  symptom is a panel that no longer repaints with a clean `app.log`. See
  `widgets.Choice._forget`.
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
- **Never hold the microphone open while idle.** The stream is opened by
  `_open_stream` when a recording starts and closed by `_close_stream` when it
  stops, never at start up: an app that lives in the notification area between
  sentences and holds the device for the whole of its life is listed by Windows
  as using the microphone for as long as it runs, which is unexplainable to a
  user and refused to every other program. The **model** stays loaded, because
  that is the expensive part; opening a stream costs tens of milliseconds.
- **Never store a PortAudio device index.** An index is a position in a list
  Windows builds per machine, per host API and per boot, so a stored one is a
  pointer at whatever sits in that slot today. `settings.json` holds the device
  **name**, `input_device()` matches it case-insensitively and falls back to the
  automatic choice with a warning, and `Panel.set_devices` puts the switch back on
  that fallback rather than marking a device that is not there.
- **Never mark a radio from whether its variable is true.** Every code in a radio
  group is a non-empty string, so truthiness marks all of them at once and the
  language pair came up with both ends filled in and neither chosen — with the
  variable holding one value throughout, so nothing else could see it. Paint from
  whether the variable holds **this** widget's code (`Choice._is_on`), and let
  `Panel.check_radios`, which `--check-bundle` runs, keep it that way.
- **Never lay a page out from a width an unmapped window reports.** A window that
  has never been shown is 1 px wide, and `Scroller` copies the canvas width into
  the body frame: every paragraph on the page then breaks one word per line, and
  a history tab arrives as a column of single letters down the bottom. Both ends
  guard the width rather than the page — `Scroller._on_canvas` ignores a canvas
  under 2 px, `Paragraph._on_frame` ignores a frame under `MIN_PIXELS`. The real
  width arrives with the `<Configure>` that comes with the map.
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
- **The separating space belongs to the boundary, never to a fragment.**
  `Typer.apply` adds it only when `boundary=True`. Adding it to every fragment
  put a space inside any word the model went on to extend, so each extension had
  to erase that space again — a Backspace per grown word, for nothing. Measured
  over the sentence from the bug report: 2 Backspaces down to 0 word by word,
  24 down to 12 one letter at a time, and the text on screen is identical
  either way. This is not only tidiness. **A Backspace is the one keystroke here
  that is not sent as `KEYEVENTF_UNICODE`** — it goes out as a real `VK_BACK`,
  so it is the one event on the chain a keyboard hook can act on by layout. A
  layout switcher that swallows it leaves the space standing where the word
  grew, which is how `ии` came out as `и и` while the transcript stayed correct.
  Every Backspace that remains is a genuine rewrite.
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
  would all have to be restored by hand. The interface starts in **English**
  (`text.DEFAULT_LANGUAGE`, listed first in `LANGUAGES`) with Russian one click
  away: the shipped model is Russian, but the panel is read by whoever installed
  it, and a language switch is hardest to find in a language you cannot read.
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
- **The settings tab must fit the window or scroll, never clip.** A `Frame` inside a
  `ttk.Notebook` is laid out at its full requested height and simply runs off the
  bottom of the window, so everything below the fold is never drawn and cannot be
  clicked — and nothing in the app reads it back, so every check passed while
  **Автозапуск с Windows** and the whole **Язык** group sat 200 px under the edge
  of a 440 px window. `Panel._settings_page` puts the frame on a canvas with a
  scrollbar, `_bind_wheel` binds the wheel on the page and its widgets rather than
  with `bind_all` (which would also fire over the chip), `_toggle_scrollbar` shows
  the scrollbar only while there is something to scroll to, and `_place` clamps the
  window to the display so it can never be taller than the screen.
  `Panel.check_settings_reachable` scrolls the tab to its end and asserts the last
  line is on screen, and check 6 runs it, so the next label added there cannot go
  missing this way.
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
- **Never prune a Pillow plugin that a plugin you keep imports.** This cost
  1.1 its tray icon. `Image.init()` imports every plugin by name inside
  `try/except ImportError` and says nothing when one is missing, so the module
  is simply never registered and the failure surfaces much later as
  `KeyError: 'ICO'` from `Image.save` — or not at all. `pystray` serialises the
  tray glyph through `pystray._util.serialized_image(image, 'ICO')`, and
  `IcoImagePlugin` imports `BmpImagePlugin` at module level; 1.1 excluded both,
  because nothing else in the app touches an image file at run time. The build
  itself could not have caught it: `tools\build_exe.py` draws the exe icon with
  `make_icon(...).save(ICON, sizes=...)` on the build machine, where the plugin
  is present. Before excluding a module, check what the modules you are keeping
  import from it.
- **An exception on a worker thread must reach the log.** Python reports those
  through `threading.excepthook`, which writes to `sys.stderr` — and under
  `pythonw.exe`, or any bundle built with `console=False`, `sys.stderr` is `None`.
  The process then carries on looking healthy while a thread is dead.
  `config.setup_logging()` installs an excepthook that logs instead, which is how
  the missing tray plugin became a `logs\app.log` entry at all. `main()` catches
  `Exception` around assembly, `start()` and the main loop for the same reason:
  a windowless app that dies at start up must leave a traceback in the log and a
  dialog on screen, never just vanish.
- **What cannot be packed, and why.** No `.pyd` or `.dll` can go into an archive:
  the Windows loader opens them by path. Pure Python already is packed — the
  stdlib into `base_library.zip` and every other module into the `PYZ` inside
  the exe, which is why `_internal` holds only binaries and data. Tcl's script
  library is the one large tree left, and Tk finds it as files on disk. So the
  lever is pruning, not packing; `upx=True` would trade startup time and AV
  heuristics for about 25 MB and is deliberately off.
