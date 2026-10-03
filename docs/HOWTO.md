# WinVosk

Offline Russian dictation for Windows. Hold a combination, speak, let go. The
words are typed straight into the window in front, at the caret, as they are
recognised. Nothing leaves the machine.

## Upstream

This project is a fork of [alphacep/vosk-api](https://github.com/alphacep/vosk-api)
— the Vosk Speech Recognition Toolkit by AlphaCephei, Apache-2.0. The `vosk`
package installed in `.venv` is the Python binding published from that
repository's `python\` directory, and it brings the prebuilt Kaldi decoder and
its native libraries with it.

Everything else here is original work: `src\winvosk\`, `src\run.py` and
`tools\` are not part of upstream, nothing from upstream is vendored or patched,
and the models in `models\` are the ones vosk publishes. Decoder questions go
to upstream, dictation behaviour questions go here.

## Usage

Start it with `WinVosk.bat`, or let Windows start it on login.

| Action | How |
| --- | --- |
| Dictate | hold `Win + Ctrl + Right` **or** `Alt + Win` and speak; let go to stop |
| Dictate, if **Переключать запись** is on | press the combination once to start, once more to stop |
| Dictate with the mouse | hold the **Удерживайте** button in the panel |
| End it without letting go | **Стоп** in the panel, or tray → **Остановить запись** |
| Copy the result | the **Копировать** button or the tray menu |
| Open the panel | left click the tray icon, or tray → **Показать панель** |
| Hide the panel | tray → **Скрыть панель**, or just close the window — it goes to the tray |
| Change the hotkey | panel → **Настройки** tab, see [Settings](#settings) |
| Record on press instead of hold | panel → **Настройки** → **Переключать запись** |
| Type or not, clipboard, autostart | panel → **Настройки** tab, see [Settings](#куда-попадает-текст) |
| Teach it your own words | put them in `phrases.txt`, see [Custom vocabulary](#custom-vocabulary) |
| Quit | tray menu → **Выход** |

Recording runs for exactly as long as the keys are held, which is the shipped
default: release and the session closes, the text is written to
`logs\YYYY-MM-DD.txt`, and the caret is left where the last word landed. Hold
again for the next sentence.

**Переключать запись** in the settings tab replaces that with a toggle: one
press starts, the next one stops. See [Recording mode](#recording-mode) for
what it costs and how it is built.

A session is cut off after `MAX_SESSION_SECONDS` (180 s by default). That is a
rare safety net while the mode is push to talk, and the thing that ends a
recording in toggle mode when the second press never comes.

`Win + Ctrl + Right` lets you keep `Win` and `Ctrl` down and tap the arrow for
each sentence. `Alt + Win` is two keys, so both have to be released between
sentences: the combination completes on the second key, and there is no third
key to hold.

### Recording mode

**Переключать запись** (off by default) chooses how one press of the
combination is read.

| | Push to talk (default) | Toggle |
| --- | --- | --- |
| press | start | start |
| release | stop | nothing, the keys are ignored |
| press again | start a new session | stop |
| ends a session that nobody can end by pressing again | — | **Стоп** on the panel, **Остановить запись** in the tray, or the 180 s ceiling |

The mode is not a flag inside the hook. `HotkeyListener` takes both `on_press`
and `on_release`, and push to talk *is* the presence of `on_release`: the hook
has to see the main key's keyup to end the session. So `App._install_hotkey`
reads `settings.toggle_recording()` and builds the listener with `on_release=None`
or not at all. A listener told about the mode in a flag could be told it is push
to talk and behave otherwise.

Which of start or stop a press means is decided in `App._hotkey_pressed`, on
the pump thread, not in the hook callback: the callback runs on the hook thread
and would read a `_recording` that has not caught up with the first press yet, so
a quick second press could be taken for another start.

What a toggle gives up is the reason push to talk exists. A held session ends by
letting go, and a release that never arrives cannot happen; a toggle ends by
pressing again, and a press that never arrives leaves the microphone open. The
three ways out that remain are **Стоп** in the panel, **Остановить запись** in
the tray — both enabled for as long as the recording runs — and
`MAX_SESSION_SECONDS`, which is why that constant stops being a belt-and-braces
limit the moment toggle mode is possible. The hint under the switch names all
three, and `TOGGLE_DEFAULT` is `False`: a mode that can only be left by pressing
the same key again is not a safe thing to ship as the default.

Changing the switch rewrites the hook rather than flipping something inside it:
`_set_toggle` stores the value and reinstalls the listener, and a write that
failed puts the checkbox, the record button and the footer back to what is
really in effect.

### Ending a recording early

**Стоп** in the panel and **Остановить запись** in the tray menu finish a
recording that was started by holding the hotkey, without releasing the keys.
That is what a long sentence needs: stop the microphone, let the tail be typed
and written, and keep holding. Releasing the keys afterwards changes nothing —
an already stopped recording ignores its own release.

Both controls are greyed out when nothing is recording, so pressing one by
accident does nothing. A stop ends the session exactly as a release does: the
tail is typed, the text goes to `logs\YYYY-MM-DD.txt`, and the next press of the
hotkey starts a fresh one.

In **Переключать запись** mode they matter more rather than less, because that
is the mode where a press can be missed — see
[Recording mode](#recording-mode). They stay enabled for the whole recording,
and the release of the hotkey is ignored entirely in that mode.

### The recording chip

While a recording runs, a dark chip sits horizontally centred on the work area,
16 px above the taskbar: eleven thin pink bars across a 20 px field at the top,
and the elapsed time as `M:SS` centred underneath. It is 87x35 — one canvas
carrying canvas rectangles for the bars over a single cached image for the
plate, drawn at `_PLATE_SCALE` times the size and folded back down, so there is
no image file on disk and no new dependency. Its position comes from the real
work area rather than from the screen size, so it stays correct with the taskbar
on any edge or auto-hidden, and it is well clear of the panel's own bottom right
corner.

The bars are an animation, not a reading. The microphone really is measured:
the engine splits every half second of audio into sixteen sub-frames, takes the
loudest sample of each and buffers the results, and the chip takes one level
every 30 ms. The number is then thrown away. The level is gated into sound or
silence and used only to decide how lively the row is, so the chip shows that
something is being said without ever claiming to show how loudly it is said.
Below the gate every bar settles onto the same small height; above it they jump
about, never together, because each has its own rate and phase.

The row is shaped like a bell. Every bar straddles the vertical centre of the
field and grows upward and downward at once, in three bands of one pink ramp —
a darker core with brighter bands towards its two outer edges, so the ramp
reads the same whichever way it is read. The middle bars reach furthest and the
outer ones least, in the proportion 5.00, 6.76, 11.00, 15.24, 17.00, 15.24,
11.00, 6.76, 5.00, which tapers outward with no visible step between neighbours
and leaves headroom, so no bar reaches the edge of the field even at full
drive. The wobble is scaled to each bar's own share of that shape, plus a
fraction of a pixel of texture, so a short outer bar travels a short distance
and a tall middle bar a long one and the bell survives the movement. A wobble of
one fixed size would scramble it instead. The amplitudes are also kept small
enough that two neighbours pulled to opposite extremes can close the gap between
them but never cross it. Falling back to the idle height takes about a second.

The rounded corners are genuinely antialiased, because Tk does not draw them.
The plate is rendered whole by Pillow at four times the size and brought back
down with a box average, which blends the boundary into pixels, and everything
outside the rounded shape is left in one colour used nowhere else. That colour
is declared transparent to the window manager, so it is cut out as a clean hole
and the blends along its rim read as a smooth edge. Square corners are one
constant away — `CORNER` at 0 in `src\winvosk\overlay.py`. The pixels
outside the rounded shape stay transparent to clicks, so a click just beyond
the edge falls through to whatever is under the chip.

Pillow is the one call on the run-time path, so it is not allowed to be able to
stop the app. If the plate cannot be drawn, the chip writes a single `ERROR`
line to `logs\app.log` and lays the same plate on from canvas rectangles
instead: square and hard-edged, and nothing else about it changes.

The clock still moves once a second; the bars move about thirty times a
second. Nothing in the audio path changed to get that: `SAMPLE_RATE` is 16000
and `BLOCK_SIZE` is 8000 in `src\winvosk\config.py`, so the decoder
still gets the same half second blocks, and the level measurement only reads
them alongside. Dictation latency and partial results are unaffected.

The chip exists because the panel is in the tray most of the time: a recording
started by the hotkey would otherwise leave no trace at all that the microphone
is live. It **never takes focus** — the window carries the Windows
`WS_EX_NOACTIVATE` style, applied before the first show and again on every
mapping, because Tk rewrites the extended style each time the window is mapped.
The operating system itself then refuses to activate it. Dictated characters
therefore still land in whatever window was in front, which is the entire point
of it.

### The tray icon and the window

- **left click** — opens the panel and gives it the focus
- **right click** — opens the menu

It is a single click that opens the panel, not a double click, and the shipped
behaviour is worth stating precisely. **Показать панель** is the tray menu's
default item, and pystray's Windows backend activates the default item on
`WM_LBUTTONUP`, that is, on button *release*. There is no `WM_LBUTTONDBLCLK`
handling anywhere in that backend, so there is no double click message to react
to. A double click works too, but only because its trailing button-up fires the
same action a second time — it is a superset of what a single click does, not a
separate gesture.

Opening the window is the one thing that deliberately takes the focus, because a
tray click is a deliberate act. The hotkey never does this. If the panel is left
in front while you keep dictating, live typing is held back rather than typed
anywhere: the words reach the panel and the diary, but not your document. Close
the panel before you continue.

**The panel starts unmapped and stays that way.** `Panel.__init__` calls
`withdraw()` on the root before a single widget is built, so the window is never
mapped: nothing flashes on the way in, and a start that took the focus would send
the dictated words into the panel rather than into your document. A tray click is
therefore the only way to see it, which is the honest one anyway — the icon is
there. Closing the window puts it back in the tray, which is what it has always
done.

Two consequences worth knowing. The recording chip is a `Toplevel` of that
withdrawn root and **maps on its own**, so a recording still shows its chip while
the panel is in the tray; `--check-bundle` asserts exactly that. And a modal
dialog whose parent is withdrawn comes up behind whatever else is in front, or
not at all, so `show_words_report` passes `parent` only while the panel is up —
the own-word check is most often run from the tray.

## Layout

Every command in this file is relative to the project root, and every path in
the tree is derived at runtime, so the checkout can be moved anywhere without
editing a single file.

```
Vosk\                             the checkout folder, the project itself is WinVosk
├── .venv\                     Python 3.14.2 virtual environment
├── models\                    vosk models, one directory each
├── src\
│   ├── run.py                 entry point
│   └── winvosk\
│       ├── config.py          paths, model resolution, logging
│       ├── recognizer.py      vosk model + microphone stream + worker thread
│       ├── hotkey.py          global hotkey via a low level keyboard hook
│       ├── keystrokes.py      text typed with KEYEVENTF_UNICODE keystrokes
│       ├── vocabulary.py      phrase file loader and vocabulary check
│       ├── panel.py           always-on-top Tk panel, two tabs
│       ├── overlay.py         recording chip: eleven bars over an elapsed clock
│       ├── settings.py        settings.json: hotkey, switches, atomic write
│       ├── corrector.py       own-word correction after the decode
│       ├── text.py            every user visible string, ru and en
│       ├── tray.py            pystray icon and menu
│       ├── autostart.py       HKCU\...\Run entry
│       ├── diary.py           dated history under logs\
│       └── file_transcribe.py fallback: media file to text, plus --self-test
├── tools\
│   ├── cleanup.py            kills leftover targets and the app
│   ├── send_keys.py          sends a real key combination
│   ├── hold_keys.py          holds a combination down for N seconds
│   ├── edit_target.py        native EDIT control used as a typing target
│   ├── hook_probe.py         checks which combinations the hook fires on
│   ├── hold_probe.py         push to talk behaviour of the hotkey
│   ├── typing_probe.py       end to end typing assertion
│   ├── settings_probe.py     headless check of settings.json and the capture
│   ├── correct_probe.py      headless check of the own-word correction rules
│   ├── lang_probe.py        headless check of the message table and the language
│   ├── build_exe.py          builds dist\WinVosk\, see below
├── phrases.txt               optional list of your own words, see below
├── settings.json             written by the Настройки tab, see below
├── WinVosk.bat               launcher, resolves everything from %~dp0
├── WinVosk.spec              PyInstaller build definition
├── AGENTS.md                 notes for agents working in this repository
├── README.md                 the main page and the user guide
├── project.md                project context
├── opencode.json             agent configuration for this project
├── logs\                      app.log plus a dated dictation history
├── tmp\                       model archive, converted wav files
├── build\                    WinVosk.ico and the PyInstaller work folder
├── dist\WinVosk\             the built application, see below
└── docs\HOWTO.md              this file
```

The app locates itself through `config.BASE_DIR`, derived from `__file__`;
`WinVosk.bat` uses `%~dp0`; the `tools\` probes insert `src` resolved from
their own `__file__`. Nothing in the tree contains an absolute path. The
checkout currently sits in `D:\AI\Vosk`, which is what `--diagnose` reports on
its `base dir` line, and that is the only place the current location matters.

`settings.json` is the one file here that is machine state rather than part of
the checkout: it is ignored by git and can be deleted freely, which costs the
default hotkey and the default states of the three switches, nothing else.

## Model

`models\vosk-model-small-ru-0.22` (44 MB) ships with the app. Any Kaldi model
dropped into `models\` is picked up automatically, so a larger and more accurate
one, **or one in another language**, needs no code change.

`config.resolve_model` takes `MODEL_NAME` outright when it is there, so the
shipped setup can never change under you. Failing that it takes the first model
directory that carries an `am` subdirectory, Russian ones sorted first — which is
why a Russian model left behind wins over an English one. Keep exactly one model
in `models\` if you dictate in another language, and confirm what was loaded with
the `model` line of `--diagnose`.

The Russian test is `config.is_russian_model`, which compares whole hyphen
separated tokens rather than a substring. The older glob, `vosk-model*ru*`,
matched `vosk-model-small-uz-0.22` as well, and would have handed Uzbek to a
Russian UI.

The own-word correction is pure `difflib` over tokens and knows nothing about
Russian, so it runs on any model — but `phrases.txt` has to be written in the
language being dictated, or it finds nothing to correct. The same goes for
`--vocab-check`: it asks the loaded model, so its verdicts follow the model, not
the interface language.

Install a different model:

```powershell
curl.exe -L -o .\tmp\m.zip https://huggingface.co/rhasspy/vosk-models/resolve/main/ru/vosk-model-small-ru-0.22.zip
Expand-Archive .\tmp\m.zip .\models -Force
```

The official host `alphacephei.com` throttles large downloads heavily from
some networks, which is why the Hugging Face mirror is used. The full table of
the 26 languages Vosk publishes a model for, with model names and sizes, is in
`README.md` § Models and languages.

## Transcribing files

```powershell
.\.venv\Scripts\python.exe .\src\winvosk\file_transcribe.py call.mp3
.\.venv\Scripts\python.exe .\src\winvosk\file_transcribe.py meeting.mkv -o meeting.txt
.\.venv\Scripts\python.exe .\src\winvosk\file_transcribe.py --self-test
```
Anything ffmpeg understands works. It is converted to 16 kHz mono PCM first.

## Building WinVosk.exe

```powershell
.\.venv\Scripts\python.exe .\tools\build_exe.py
```

One folder rather than one file:

```
dist\WinVosk\
├── WinVosk.exe          the application, no console
├── _internal\           Python, Tk, Vosk + Kaldi, PortAudio, Pillow   (79 MB)
├── models\              the copied model                              (87 MB)
├── logs\                app.log, report.txt, the dated history
└── phrases.txt  settings.json
```

Start it by double clicking `WinVosk.exe`, or from a shell:

```powershell
.\dist\WinVosk\WinVosk.exe --diagnose
.\dist\WinVosk\WinVosk.exe --check-bundle
```

What the build does: draws the tray glyph into `build\WinVosk.ico`, so the exe
carries the same icon and no image file has to be kept in the tree; runs
PyInstaller over `WinVosk.spec`; prunes `_internal\`; then copies `models\` and
`phrases.txt` next to the exe.

`WinVosk.spec` is where the collection decisions live. `vosk` and `sounddevice`
are taken with `collect_dynamic_libs` and `collect_data_files`, because both
carry native libraries an import analysis would not find, but **not** with
`collect_all`: that also returns every submodule, and `vosk.transcriber` is a
streaming client for a server this app never runs. Naming it pulled `websockets`,
`socks` and then the whole TLS stack in behind it. `vosk.vosk_cffi` is the one
module added by hand, because it builds its bindings through cffi rather than
importing them.

### Pruning `_internal`

The build then deletes what the app cannot reach, from the `PRUNE` table in
`tools\build_exe.py`. Each entry carries the reason, and **a pattern that
matches nothing is reported rather than ignored** — that is the whole point: an
upstream rename that leaves a dead file in place, or that stops being dead, has
to show up in the build log.

Measured on this project, from the first build to the pruned one:

| | files | size |
| --- | --- | --- |
| before | 1014 | 91.2 MB |
| after | 358 | 79.4 MB |

What went, and why it was safe:

- **609 files, 1.1 MB — Tcl's `tzdata`.** Only `clock` with an explicit zone
  reads it. The panel shows no clock: the chip's `M:SS` is counted in Python from
  `perf_counter`. This is the single biggest file-count win in the folder and the
  only prune with any real risk, which is why check 6 exists.
- **2.5 MB — Pillow's `_imagingft`, `_imagingcms`, `_imagingmath`.** Nothing
  draws text through Pillow (the chip's plate and the tray glyph are `ImageDraw`
  calls on sRGB literals), and ICC profiles and `ImageMath.eval` are never
  reached. `_imaging` and `_imagingtk` stay: the chip needs both.
- **9.8 MB — Pillow's AVIF and WebP codecs**, kept out by `excludes` rather than
  by the prune table. `PIL.Image.init()` imports its plugins in a
  `try/except ImportError`, so a missing plugin is skipped rather than fatal.
- **`websockets`, `socks`, `setuptools`, every `*.dist-info`.** Nothing in the
  chain reads `importlib.metadata` — every `__version__` is a literal in its own
  module — so the wheel metadata is dead weight.

`_tk_data\msgs` (Tcl's localised strings) and `_tk_data\encoding` (what `ttk`
reads its themes through) are kept, and so is `tcl8\8.6`; `tcl8\8.4` and
`tcl8\8.5` go, because `tcl86t.dll` loads only the `init.tcl` of its own version
and that file says `package require -exact Tcl 8.6.15`.

### Why nothing is packed

`_internal` holds no Python at all: the stdlib is already in `base_library.zip`
and every other module is in the compressed `PYZ` embedded in the exe. What is
left is binaries and data, and neither can be archived:

- **A `.pyd` or `.dll` must be a real file.** The Windows loader opens it by
  path; there is no in-exe filesystem it can be reached through.
- **Tcl's script library must be a real tree.** Tk resolves its library through
  the filesystem and would need `zipfs` mounted before it could look inside an
  archive.

So the only packing lever left is compression rather than packing: `upx=True`
would take roughly 25 MB out of `_internal` and is deliberately **off**, because
it costs startup time on every launch and packed DLLs draw AV heuristics on a
downloaded exe. `onefile` would give one file and is refused for the same
reason plus one: a single exe unpacks the model and the native libraries into a
temporary directory on every launch.

### Checking a build

`--check-bundle` builds the **real** `Panel` rather than a couple of loose
widgets, so the whole widget tree, the tray-only start up and the chip are all
covered: it reports the Tcl patch level, the resolved `ttk` theme, that the
window was never mapped, that a tray click brings the panel up, and that the chip
maps with its antialiased Pillow plate while the panel is in the tray. It is the
only check that can notice a prune having gone one step too far, because
`import tkinter` succeeds long before the first `ttk` widget asks for its theme,
and `from PIL import Image` succeeds before the first `ImageTk.PhotoImage` asks
for the extension.

The Pillow part is asserted on `_photo`, not on a mapped window: the chip falls
back to canvas rectangles when Pillow cannot draw its plate, so a chip that came
up with square corners would otherwise pass. It opens no microphone, so it runs on
a machine with no input at all.

Measured, by deleting one file at a time from a built bundle and re-running it:

| Removed | What `--check-bundle` said |
| --- | --- |
| `_tk_data\ttk\defaults.tcl` | `TclError: couldn't read file ... ttk/defaults.tcl`, non-zero exit |
| `PIL\_imaging.cp314-win_amd64.pyd` | no report at all — `tray.py` imports Pillow at module level, so the bundle cannot start |

Which is the point: a prune that took too much shows up as a failure with a
reason, never as a silently degraded build.

Three things to know:

- **The folder is the application.** `config.BASE_DIR` is the folder the exe is
  in, so `models\`, `logs\`, `settings.json` and `phrases.txt` are read and
  written there, exactly as in the checkout. Copy the whole folder anywhere and
  nothing inside it needs editing — but do not put it under `Program Files`,
  because the app writes its log and its settings next to itself.
- **A windowless exe has nowhere to print.** `--diagnose`, `--autostart`,
  `--vocab-check` and `--check-bundle` write their report to `logs\report.txt`
  and show it in a message box. From the source checkout the same flags still
  print to the terminal.
- **The `.venv` and `WinVosk.bat` are only for building and for development.**
  The exe needs neither of them, but it also cannot be changed from them: any
  change goes into the source and is rebuilt.

## Maintenance

```powershell
.\.venv\Scripts\python.exe .\src\run.py --diagnose
.\.venv\Scripts\python.exe .\src\run.py --autostart on
.\.venv\Scripts\python.exe .\src\run.py --autostart off
Get-Content .\logs\app.log -Tail 40
```

`--diagnose` reports the Python build, whether this is a bundle, the resolved
model, the autostart state, the hotkeys actually in effect, whether live typing
and the clipboard switch are on, which device the microphone will be opened on,
where the settings file is, the typing delay, the session limit and every input
device PortAudio can see. Its `base dir` line is the quick confirmation that the
app resolved the checkout it is supposed to be in — or the folder the exe is in
— and its `hotkeys` line is the quick confirmation of what the panel's
**Настройки** tab actually produced: the two can disagree, and when they do the
file on disk is the winner and the panel is showing a rollback.

`records from` is worth reading when dictation does not start. PortAudio's own
default can name no device at all on some machines, in which case it answers
`paNoDevice` and the app picks the device its host API does name instead.

## Verification helpers

Always run `cleanup.py` first. A leftover target from an earlier run keeps the
foreground, and the Windows Search panel refuses to give it up at all, so both
have to be out of the way before a probe can assert on focus.

```powershell
.\.venv\Scripts\python.exe .\tools\cleanup.py

# push to talk: one press, one release, auto repeat ignored
.\.venv\Scripts\python.exe .\tools\hold_probe.py

# which combinations the hook fires on
.\.venv\Scripts\python.exe .\tools\hook_probe.py 30
.\.venv\Scripts\python.exe .\tools\send_keys.py alt+win
.\.venv\Scripts\python.exe .\tools\send_keys.py win+ctrl+right

# typing lands at the caret, corrections are erased, existing text survives
.\.venv\Scripts\python.exe .\tools\typing_probe.py

# settings file and hotkey capture: no GUI, no microphone, no model load
.\.venv\Scripts\python.exe .\tools\settings_probe.py

# own-word correction rules: no model, no microphone, no GUI
.\.venv\Scripts\python.exe .\tools\correct_probe.py

# message table and the language switch: no GUI, no microphone, no model
.\.venv\Scripts\python.exe .\tools\lang_probe.py

# which of your own words the model can hear
.\.venv\Scripts\python.exe .\src\run.py --vocab-check
```

`hold_probe.py` holds a combination for two and a half seconds and asserts that
exactly one press and one release came out, that the release followed the
press, and that the operating system key repeat did not fire extra presses.
`typing_probe.py` opens a native EDIT control with the caret at offset 0,
drives the real `Typer` with a sequence of recogniser updates including a
revision, and prints `VERDICT: PASS` when the text was typed at the caret, the
correction was applied with Backspace and the original content survived.

Three probes are pure logic: they need no keyboard, no microphone, no model and
no GUI, and they run unattended in a fraction of a second. `settings_probe.py`,
`correct_probe.py` and `lang_probe.py` print `VERDICT: PASS` or `VERDICT: FAIL`.

`settings_probe.py` checks the hotkey plumbing and the file: that every key the
capture can be given has a name and that the name round trips through the
parser, the capture rules (a bare main key is refused, `Escape` cancels, a
modifier alone is not a combination), the `settings.json` fallbacks for a missing,
malformed, wrongly shaped or unusable file, a byte order mark, the three switches
and their fallbacks for a value that is not `true` or `false`, the atomic write
leaving no temp file behind, that a switch write never disturbs the hotkey list
beside it, and that leaving the capture hands the keyboard back. Its filesystem
cases point the module at a temporary directory, so it never touches the real
`settings.json`.

`correct_probe.py` covers the own-word correction: what is heard becoming what
you wrote, the cutoff boundary in both directions, inflections left alone, the
glue that puts a word the model split back together and the cases it must
refuse, the empty and whitespace-only inputs, that the app corrects a finished
utterance and never a partial, and the cost against `TYPE_DELAY`.

`lang_probe.py` reads the source instead of running it, which is the only way to
catch a translation slipping sideways: every key has both languages, both format
the same placeholders, and **no string literal containing Cyrillic exists outside
`winvosk\text.py`** — so a new label cannot appear in one language only. It also
covers the stored language, an unusable code, and that switching really changes
what is answered.

## Settings

The panel has two tabs. **Диктовка** is the transcription itself, unchanged.
**Настройки** holds the combination that starts a recording, three switches — where
the text goes, whether it also lands in the clipboard, whether your own words are
corrected — whether Windows starts the app, and the language. Everything on that
tab is written at once, on the click, and is in force immediately.

### Куда попадает текст

Four switches, and they are independent of each other:

| Switch | Meaning | Default |
| --- | --- | --- |
| **Печатать в активное окно** | the recognised words are typed at the caret of whatever window was in front, as they are recognised | on |
| **Сразу копировать в буфер** | every finished session is also copied to the clipboard | off |
| **Исправлять свои слова** | a word the model heard as something close to one of yours is replaced by yours | on |
| **Автозапуск с Windows** | the app starts at login, with no console and no panel | off |

**Печать в активное окно** off means nothing is typed anywhere: the session is
recognised, shown in the panel and written to `logs\YYYY-MM-DD.txt`, and the
**Копировать** button is how you get it out. Turn it on to have the words land
in the document directly.

**Сразу копировать в буфер** overwrites whatever was in the clipboard after
every session, so it is worth leaving off unless something else in your workflow
wants the recognised text there. Copying out is not how the text is inserted —
the words still arrive as keystrokes — so the clipboard is only ever read from
by other programs.

**Исправлять свои слова** works from the words in `phrases.txt` and is described
in [Custom vocabulary](#custom-vocabulary). It works on finished phrases only,
not on the half recognised text, and every replacement is written to
`logs\app.log`. The **Проверить свои слова** button under it asks the loaded model
which of those words it can hear — see
[Check what the model hears](#check-what-the-model-hears).

**Автозапуск с Windows** writes `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\WinVosk`
pointing at `pythonw.exe` and `src\run.py`, so there is no console window and
the panel stays in the tray. It is per user, needs no administrator rights, and
can also be set from a shell:

```powershell
.\.venv\Scripts\python.exe .\src\run.py --autostart on
.\.venv\Scripts\python.exe .\src\run.py --autostart status
.\.venv\Scripts\python.exe .\src\run.py --autostart off
```

A switch that cannot be saved puts itself back where it was and says why under
the switches: a failed write leaves the previous value on the disk, and a failed
registry write is reported with the checkbox restored to what the Run key really
holds. The switch is never left showing something that is not in effect.

### Язык / Language

**Русский** and **English**, chosen with two buttons, and applied at once: the
panel, the tray menu, the notifications, the capture reasons and the window title
all repaint in the new language without a restart and without losing anything —
the text in the box, the recording state and the switch positions stay exactly
as they were.

The choice is remembered in `settings.json`, so it survives a restart, and the
language you pick is also the one `--diagnose`, `--autostart` and `--vocab-check`
answer in. Each language is named in its own script, so the buttons read
`Русский` and `English` whichever one is active.

An unknown code in `settings.json` costs one `WARNING` line and the default,
Russian — never an untranslated panel.

Two things the language does **not** cover, and both are deliberate: your own
word list in `phrases.txt` and the diary, because those are your data and your
language, not the interface's. The `—` and `·` in the footer stay as they are.

### Dictation hotkey

Click the field and the app switches its low level keyboard hook into capture
mode. The field then reads `Нажмите клавиши…`, with `Esc — отмена` underneath.
Press the modifiers and then the key: the combination is validated, saved on its
own and taken into use immediately — no restart, and the footer under the panel
and the tray header both follow the new value. Press **Escape** to cancel, and
the previous combination stays exactly as it was.

While the capture is live the hook swallows **every** keystroke in the system,
so nothing reaches Windows at all: a bare `Win` cannot open the Start menu,
`Win+D` cannot minimise everything, and the keys you are recording cannot start
a recording by accident. That is deliberate, and it has a cost — for the few
seconds the capture is live the keyboard is inert.

Two kinds of input are refused, each with the reason shown under the field:

- a main key with no modifier held —
  `нужна клавиша при модификаторе: Ctrl, Alt, Shift или Win`. Hold, say, `Ctrl`,
  then press `F5`.
- a key that cannot be named, such as one of the media or browser keys —
  `нажмите обычную клавишу`.

After a refusal the capture stays live, so the next attempt needs no second
click. **Escape** is reserved for cancelling and can therefore never become the
main key of a combination. **Сбросить** forgets the stored value and brings back
the two shipped defaults, `win+ctrl+right` and `alt+win`.

A captured combination replaces the whole list: after a change the app holds one
combination, and the field, the footer and the tray header show it alone.
**Сбросить** is how the pair comes back.

### Where the settings are stored

In `settings.json` in the project root, six keys:

```json
{
  "hotkeys": [
    "win+ctrl+shift+f5"
  ],
  "live_typing": true,
  "copy_to_clipboard": false,
  "correct_words": true,
  "toggle_recording": false,
  "language": "ru"
}
```

It is machine state rather than part of the checkout: it is listed in
`.gitignore` and can be deleted freely, which costs the default hotkey and the
default states of the switches and nothing else. It is written atomically — the
content goes to a sibling temp file and is then moved into place, which is atomic
on Windows — so a crash or a full disk leaves either the previous file or no
file, never half of one.

Nothing about that file can stop the app from starting:

- a missing, unreadable, malformed or wrongly shaped file costs one `WARNING`
  line in `logs\app.log`, and the shipped defaults are used
- a byte order mark costs nothing: Notepad and PowerShell save the file with one,
  and it is read with `utf-8-sig` rather than looking like broken JSON
- every stored combination is parsed before it is handed to the hook, so an
  unusable entry cannot raise at startup under `pythonw.exe` where nobody would
  see the traceback. It costs **only itself**: the others stay in effect and the
  dropped one is named in the panel hint and in a tray notification on every
  start, because a file meant to be edited by hand should not lose a working
  hotkey over one typo in silence
- the Menu key is accepted as `menu`, `apps` or `context_menu`, so a hand written
  `settings.json` does not trip over which of the three names is the real one.
  A recorded combination is always written as `menu`: `name_for` sorts the
  aliases and answers the last, which is the one people search for
- a switch that is anything but `true` or `false` — `1`, `"yes"`, `null` — falls
  back to its default instead of being read as truthy or falsy at random
- a `language` that is not `ru` or `en` falls back to Russian rather than leaving
  the interface untranslated
- if a newly captured combination fails to register, the previous one is put
  back, the panel and a tray notification say so, and the app stays usable
- if the write itself fails, the panel keeps showing the value that is really in
  effect

### Other settings

Everything else is a constant in `src\winvosk\config.py`:

| Setting | Meaning |
| --- | --- |
| `HOTKEYS` | the shipped default combinations, `("win+ctrl+right", "alt+win")`; `settings.json` overrides them |
| `MODEL_NAME` | preferred model directory |
| `MIC_DEVICE` | PortAudio input index, `None` for the system default |
| `LIVE_TYPE_DEFAULT` | initial state of **Печатать в активное окно**, `True` |
| `CLIPBOARD_DEFAULT` | initial state of **Сразу копировать в буфер**, `False` |
| `TOGGLE_DEFAULT` | initial state of **Переключать запись**, `False` |
| `TYPE_DELAY` | pause after each revision, in seconds |
| `MAX_SESSION_SECONDS` | ceiling on one session; rare in push to talk, load-bearing in toggle |
| PHRASES_FILE | the own-word list: `--vocab-check` and the correction pass |
| LANGUAGE_DEFAULT | interface language when `settings.json` says nothing, `text.DEFAULT_LANGUAGE` |

`HOTKEYS` is a tuple, so several combinations can share one hook, and the tray
header shows them joined by `или`. Each accepts `win`, `ctrl`, `alt`, `shift`
(with optional `l`/`r` side prefixes), named keys such as `right`, `f1`..`f24`,
`home`, `end`, `space`, and latin letters or digits. The main key is the last
part. Examples: `("alt+win",)`, `("win+ctrl+right", "ctrl+alt+v",
"ctrl+shift+f9")`, `("ctrl+menu",)`.

A combination has to end on a key that is **not** a modifier, and the capture
says so rather than swallowing the attempt: `parse` takes the last part as the
main key, so `ctrl+shift` would be read as main=`shift`, modifiers=`ctrl` and
would block Shift itself for as long as the app runs. The hook needs a main key
to complete on, and only the main key is ever blocked.

The hotkey recorded from the panel is always written in a fixed order
(`ctrl`, `alt`, `shift`, `win`, then the main key), so the same combination
always produces the same string, and left and right variants are folded onto
the generic name — a combination recorded with the left `Ctrl` keeps working if
you later press the right one.

## Custom vocabulary

`phrases.txt` in the project root is your own word list, and it does two jobs:
it tells you which of those words the model can hear, and it corrects the ones
it hears wrong. One word or phrase per line, no punctuation, `#` starts a
comment.

### Check what the model hears

The **Проверить свои слова** button under **Исправлять свои слова** in the
**Настройки** tab, or from a shell:

```powershell
.\.venv\Scripts\python.exe .\src\run.py --vocab-check
```

```
phrases file: <project>\phrases.txt  (7 phrase(s))
heard by the model : 7
  ok      телеграм
  ok      дропбокс
  ok      фейсбук
unknown to the model: 0
```

The button and the flag print the same report, because both go through
`vocabulary.report_lines`. The button asks the **already loaded** model:
`App._check_words` puts the phrases on the engine's own queue, the worker thread
runs `vocabulary.split_by_model` and answers with a `vocab` event, and the panel
shows it in a dialog. Loading a second `vosk.Model` would cost the model's whole
memory again for nothing, and it also keeps the check off the Tk thread, which
would otherwise freeze the panel for a second or two.

The check works by building a throwaway recogniser with your phrases and
reading vosk's own log, which lists every word it has to ignore. The model's
vocabulary lives inside the decoding graph, so there is no word list on disk to
read; vosk tells us instead.

### Correct what it hears wrong

A word marked `ok` can still be misheard: the model knows «дропбокс» and prefers
a different word for the same sound. That is an ambiguity, not a gap, and it is
fixed after the decode rather than inside it — **Исправлять свои слова** in the
**Настройки** tab, on by default.

Put the words you say in `phrases.txt` and every finished phrase has each of its
words compared with them:

| Heard | Corrected to | Why |
| --- | --- | --- |
| `дропбок` | `дропбокс` | a dropped letter, 0.93 similar |
| `топбокс` | `дропбокс` | a wrong consonant, 0.80 similar |
| `друг бокс` | `дропбокс` | split across a space, 0.75 once glued |
| `дропбокс` | unchanged | exact |
| `дропбоксы` | unchanged | an inflection of your own word, not a mistake |
| `бокс друг` | unchanged | the glue only runs forwards |
| `молоко` | unchanged | nothing near the list |

A word the model knows can also come out as two words: `друг бокс` instead of
`дропбокс`. Neither half is close enough to anything in the list — 0.33 and 0.67
— so both are left as they are unless neighbouring words are glued together and
compared as one. `друг` + `бокс` scores exactly the cutoff, so the pair is
replaced and the log reads `друг бокс -> дропбокс`. The glue runs forwards only,
takes two tokens at a time, and needs at least three letters in each half, so
`с` + `воих` never becomes a listed `своих`. A word split into *three* tokens is
out of reach: for `йо цун фэнь` the first pair scores 0.71 and is left alone, the
second scores 0.88 and fires, giving `йо йоцунфэнь` — recognisable, but not what
was meant.

What it deliberately does not touch: the half recognised text, so what is on
screen stays stable while the model is still thinking; words shorter than four
letters, where a wrong correction is easy to miss; and anything longer than
about 0.75 similar, which covers «подбоксник» and «дропбоксник» next to
«дропбокс». The threshold is `CUTOFF` in `src\winvosk\corrector.py`. Measured
on this machine: over the 138 neighbouring word pairs in `logs\*.txt`, nothing
was glued and no line changed, and against a 500 word list of random tokens the
false replacement rate is about 0.03%.

Two things to know. Russian inflects heavily, so add the forms you actually say
(`дропбоксы`, `фейсбука`) rather than expecting one entry to cover them — a
longer word that begins with a listed one is always left alone, and a form you
add is what makes its own split work: with `дропбоксы` in the list, a heard
`друг боксы` glues to 0.78 and is corrected too. And every replacement is
written to `logs\app.log` as
`corrected 1 word(s): дропбок -> дропбокс`, so you can see whether it is
helping or getting in the way.

Run the probe after editing the list or the rules:

```powershell
.\.venv\Scripts\python.exe .\tools\correct_probe.py
```

It needs no model, no microphone and no GUI, prints the table above with the
real numbers, and reports `VERDICT: PASS` or `VERDICT: FAIL`.

### What can and cannot be done here

`phrases.txt` does **not** change how the model decodes. That is deliberate.

Passing a phrase list to `KaldiRecognizer` switches the decoder to a limited
vocabulary: it will only ever produce those phrases. Measured on this machine
with the same audio, free decoding gives

```
родион потапыч высчитывал каждый новый вершок углублении и давно определил про себя
```

and the same audio with a three phrase grammar gives the empty string. It is a
hard restriction, not a bias, so using it would break free dictation.

Nor can a single word be pushed inside the decoder. In vosk 0.3.45 `SetWords`
takes a boolean and switches on word timestamps — the full C API was checked,
and there is no boosting call at all. The correction above is therefore the
available route.

Words marked `MISSING` can only be added offline, by rebuilding the language
model: vosk downloads a `*-compile` variant of the model, the words go into
`db/extra.txt`, and `compile-graph.sh` regenerates `graph/Gr.fst` and
`graph/HCLr.fst`, which replace the originals. That needs a Kaldi build with
`irstlm`, `opengrm`, `srilm` and `phonetisaurus`, and the guides for it target
Ubuntu. It is not something this app can do on Windows on demand.

Practical options while that is out of reach:

- Rewrite the word so it is close to something the model knows, for example
  "фейсбук" instead of "фейсбук мессенджер". Recognised forms show in the panel
  and in `logs\YYYY-MM-DD.txt`, so it is visible what it actually heard.
- Use a larger model. `vosk-model-ru-0.10` and the 0.42 large model cover more
  vocabulary and are far more accurate, at the cost of RAM and startup time.
Drop one into `models\` and it is picked up automatically.

## How the text is inserted

The clipboard is never used to insert text and no focus is stolen. Every
fragment is sent to Windows as `KEYEVENTF_UNICODE` keystrokes, which is
independent of the active keyboard layout and goes to whatever control currently
has the caret. Russian text comes out correctly even with a Latin layout
selected.

Copying out is a separate, optional step: the **Сразу копировать в буфер**
switch and the **Копировать** button read the finished text into the clipboard
for other programs to pick up. Neither ever puts anything into a window, so
nothing here depends on focus, and a switch that fails leaves the previous state
in place.

Vosk revises its own output while an utterance is still open, so each update is
applied as a diff: the shared prefix is kept, the differing tail is erased with
Backspace and retyped. Without that the screen would show duplicated and
half-corrected words. After a finished utterance the prefix is reset, so the
next fragment is typed after what is already there.

Two guard rails:

- If the foreground window belongs to this app, nothing is typed and the
  pending prefix is dropped. Clicking the panel while dictating cannot make the
  app type into itself.
- Nothing is inserted into a target the app did not choose. There is no target
  to choose, which is the point: whatever you were typing into when the hotkey
  fired keeps receiving the keys.

## Why the hotkey is hand written

The `keyboard` package cannot be used for global hotkeys on Windows. Version
0.13.5 and current master both contain

```python
while not GetMessage(msg, 0, 0, 0):
    TranslateMessage(msg)
    DispatchMessage(msg)
```

in `keyboard/_winkeyboard.py:563`. `GetMessage` returns a positive value when a
message was retrieved, so the loop body never runs, the thread never pumps the
message queue and the `WH_KEYBOARD_LL` hook never fires. Confirmed on this
machine: even a plain `F12` hotkey was never delivered. `hotkey.py` therefore
implements the hook directly with ctypes.

Only the main key is blocked in the hook, so modifiers always reach the
foreground application and can never be left stuck down. Blocking the main key
is what stops Windows from acting on the combination itself. The one exception is
the hotkey capture in the **Настройки** tab, where the same hook swallows every
key instead of just the main one — see [Settings](#dictation-hotkey).

### What blocks, and what only repeats away

Blocking a main key is not enough on its own, and the reason is the operating
system's auto repeat. A key held down for about half a second starts producing
`WM_KEYDOWN` again and again. The first one is swallowed, so the application
never learns the key went down at all — and then a repeat arrives that it does
receive, which is a keydown out of nowhere. `Ctrl + Menu` opened the context menu
exactly that way: WinVosk recorded, and the menu came up anyway, because the
user was holding the keys for the whole sentence, which is what push to talk is.

`_blocked` is what keeps this from firing the callback twice, and it was already
doing that. It was not applied to the swallow, so every repeat went through to
Windows. Holding `Win + Ctrl + Right` had the same shape: the repeats of `→`
moved the caret in whatever you were typing into. `_on_event` now swallows a
keydown whose `vk` is already in `_blocked`.

The test is deliberately on the key, not on the match. While `ctrl + menu` is
held, `_match()` keeps returning `menu` for **every** other key pressed beside
it, because the combination is still satisfied; swallowing on that would eat the
user's typing and make the machine unusable. Only the blocked key is ours.

`tools\hook_probe.py` shows the whole thing live, one line per key event, marked
`BLOCKED` or `passed`. Run it with WinVosk not running, press the combination,
and a context menu that appears has a `passed` line above it naming the key that
got through:

```powershell
.\.venv\Scripts\python.exe .\tools\hook_probe.py --specs ctrl+menu 20
```

## Caveats

- Vosk emits a stream of lowercase words. There is no punctuation and no
  capitalisation. A trailing space is added after each finished utterance, so
  words do not run together.
- Two key combinations such as `alt+win` complete on the second key, so both
  have to be released between sentences. Use `win+ctrl+right` if you want to
  keep the modifiers down between phrases.
- The small model is noticeably weaker on noisy or telephone audio. Install a
  bigger model into `models\` for that.
- Each correction costs a Backspace per changed character, so the target
  application's undo stack sees the revisions. Raise `TYPE_DELAY` if an
  application cannot keep up.
- The bars of the recording chip are an animation, not a level meter. The level
  is gated into sound or silence, and below the gate every bar settles onto the
  same small height, so a pause in speech and a silent microphone look alike.
  Check the input device with `--diagnose` rather than reading the chip.
- `Win + Ctrl + Left/Right` is the Windows virtual desktop shortcut. The app
  takes over the Right half of it, because the low level hook runs before the
  shell sees the keys. Use a different combination if desktop switching is
  needed; the Left arrow is left alone.
- Only the main key of your combination is blocked, so the modifiers always
  reach Windows. A combination that Windows acts on through its modifiers alone
  — a bare `Win`, for instance — cannot be neutralised this way, and a captured
  combination that shadows an existing Windows shortcut takes that shortcut away
  from you while the app is running. Pick something Windows does not use.
- `Escape` is reserved as the cancel key of the capture, so it can never become
  the main key of a recorded combination.
- While the capture is live the whole keyboard is swallowed system wide. That is
  how `Win` can be recorded at all, but it means no application receives
  anything until the capture ends. `Escape` ends it; quitting the app ends it
  too.
- **Стоп** and **Остановить запись** end the recording without waiting for the
  keys to be released, so a long sentence need not be cut off mid-word. They are
  greyed out when nothing is recording. In **Переключать запись** mode they are
  the way out of a recording whose second press never comes, the 180 s ceiling
  being the other.
- Left clicking the tray icon opens the panel *and focuses it*. That is the one
  place the app takes the focus away from your document, and it happens in the
  middle of a dictation if you click while holding the hotkey. If any window of
  this app is in front while a recording is live, live typing is held back: the
  words reach the panel and `logs\YYYY-MM-DD.txt`, but not your document.
- `Alt + Win` is not bound by Windows, so it costs nothing.
- The keyboard hook only sees input from processes running at the same
  elevation level. Launch the app the same way as the other programs.
- If the Windows Search panel is open it holds the foreground. Press Escape
  first.