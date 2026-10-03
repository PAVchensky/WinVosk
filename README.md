<p align="center">
  <img src="docs/img/WinVosk_banner.png" alt="WinVosk — offline dictation for Windows" width="720">
</p>

# WinVosk

Offline dictation for Windows. Hold a key combination, speak, let go — and the
recognised text is typed straight into the window you were typing in, at the
caret, in Russian or English.

Nothing leaves the machine. There is no account, no telemetry and no network
call of any kind: the speech model runs locally, on the CPU, through the
[Vosk](https://github.com/alphacep/vosk-api) decoder.

```
Python 3.14 · vosk 0.3.45 · Vosk models for 26 languages
Windows x64 · no installer · no admin rights · one folder
```

**Read this in Russian: [README.ru.md](README.ru.md)**

- **Push to talk by default, toggle if you prefer.** Recording lasts exactly as
  long as you hold the keys — or one press starts it and the next one stops it,
  if you turn on **Переключать запись**. See
  [Recording mode](#recording-mode).
- **Layout independent.** Text is typed as `KEYEVENTF_UNICODE` keystrokes, so
  Russian comes out right with a Latin layout selected. The clipboard is never
  used to insert anything.
- **Your own words.** A plain text list fixes the words the model keeps
  mishearing — see [Custom vocabulary](#custom-vocabulary-phrasestxt).
- **No console, ever.** Tray icon, panel, chip. `--diagnose` writes a report you
  can read in Notepad if you ever need one.

---

## Contents

1. [Install and run](#install-and-run)
2. [How to dictate](#how-to-dictate)
3. [The panel and the tray](#the-panel-and-the-tray)
4. [Settings, every one of them](#settings-every-one-of-them)
5. [Custom vocabulary (`phrases.txt`)](#custom-vocabulary-phrasestxt)
6. [If it recognises badly](#if-it-recognises-badly)
7. [Models and languages](#models-and-languages)
8. [What it deliberately does not do](#what-it-deliberately-does-not-do)
9. [Files and folders](#files-and-folders)
10. [When something goes wrong](#when-something-goes-wrong)
11. [Building from source](#building-from-source)
12. [Upstream](#upstream)

---

## Install and run

### The ready-made folder

Download the archive and **unpack it**. Do not run the exe from inside the zip:
Windows cannot read `_internal\` from an archive, and the app would die on a
missing file with nothing to show for it.

1. Unpack `WinVosk-1.1.zip` into any folder you can write to — the Desktop, a
   folder in `D:\`, anywhere. **Not** under `C:\Program Files`: the app writes
   its log and its settings next to itself, and that folder is read-only without
   administrator rights.
2. Double-click `WinVosk.exe`.
3. Look for the microphone icon in the tray, next to the clock. It may be under
   the `^` arrow.

That is the whole installation. There is nothing to register, nothing to install
into the system and no service to stop.

The folder you unpacked **is** the application. It can be moved, renamed or put
on a USB stick at any time — copy the whole folder, and nothing inside it needs
editing.

```
WinVosk\
├── WinVosk.exe          the application
├── _internal\           Python, Tcl/Tk, Vosk + Kaldi, PortAudio, Pillow
├── models\              the speech model
├── logs\                app.log and the dated dictation history
├── phrases.txt          your own word list
└── settings.json        written by the app on the first change
```

### It starts in the tray

The app **always starts in the tray**: no panel appears, nothing flashes, and the
focus is not taken from whatever you were typing in. All that appears is the
microphone icon next to the clock.

Open the panel with a left click on the tray icon, or from the tray menu (right
click) → **Show the panel**. Closing the window puts it back in the tray rather
than quitting.

### Start it automatically at login

Open the panel → **Настройки** → tick **Автозапуск с Windows**. That writes one
`HKCU\...\CurrentVersion\Run` value, per user, no administrator rights, no
startup folder, no scheduled task. Untick it to remove it.

### Running it from the source checkout

If you have the source tree rather than the built folder:

```powershell
.\WinVosk.bat
```

The launcher finds the virtual environment next to itself, so it works from any
working directory. The equivalent is

```powershell
.\.venv\Scripts\python.exe .\src\run.py
```

Use `pythonw.exe` instead of `python.exe` for a start with no console window.

---

## How to dictate

| I want to | Do this |
| --- | --- |
| Dictate a sentence | hold `Win + Ctrl + Right` **or** `Alt + Win`, speak, let go |
| Dictate, if **Переключать запись** is on | press the combination once to start, once more to stop |
| Dictate with the mouse | hold the **Удерживайте** button in the panel |
| Dictate several sentences with one hand | keep `Win` and `Ctrl` down and tap `→` once per sentence |
| Finish a long sentence without letting go | **Стоп** in the panel, or tray → **Остановить запись** |
| Stop everything | release the keys; tray → **Выход** quits |
| Get the text out | **Копировать** in the panel, or tray → **Скопировать текст** |
| Open the panel | left-click the tray icon |
| Put the panel away | close the window — it goes to the tray, it does not quit |

Two shipped combinations, and both are push to talk:

- `Alt + Win` — two keys, both must be released between sentences.
- `Win + Ctrl + Right` — the combination completes on the arrow, so you can keep
  the modifiers down and tap the arrow for each sentence.

While a recording runs, a small dark chip sits in the middle of the screen with
nine bars and an elapsed timer. It never takes the focus, so the words still go
into your document and not into the chip.

**You can change the combination** in **Настройки**; see
[Settings](#settings-every-one-of-them).

### Recording mode

Recording lasts exactly as long as you hold the keys, and that is the shipped
default: release, and the session closes, the text goes to
`logs\YYYY-MM-DD.txt`, and the caret is left where the last word landed.

**Переключать запись** in the **Настройки** tab replaces that with a toggle.

| | Hold (default) | Toggle |
| --- | --- | --- |
| press | start | start |
| release | stop | nothing — the keys are ignored |
| press again | start a new sentence | stop |
| Finish a sentence a second press never comes for | release the keys | **Стоп** in the panel, **Остановить запись** in the tray, or the three-minute ceiling |

A held session ends by letting go, and a key release that never arrives cannot
happen. A toggle ends by pressing again, and a press that never arrives would
leave the microphone open — so in that mode **Стоп**, the tray menu and the
three-minute ceiling are what stop a recording. All three stay available for as
long as it runs. That is why the switch is off by default.

A session is cut off after three minutes either way, so nothing can record
forever.

---

## The panel and the tray

The panel has two tabs.

**Диктовка** — the recognised text as it arrives, with the model name in the
corner, the hold button, **Стоп**, **Копировать** and **Очистить**, and the hotkey
in the footer. This tab does nothing configurable; it is the transcript.

**Настройки** — everything you can change. See below.

The tray icon is the app's real home:

| Action | Result |
| --- | --- |
| left click | open the panel and focus it |
| right click | the menu: hold-to-dictate hint, stop, show/hide panel, copy, clear, quit |

Note that a left click **takes the focus** — that is deliberate, you asked for the
panel. If the panel is left in front while you dictate, live typing is held back
rather than typed into the panel: the words still reach the panel and the diary,
but not your document. Close the panel before you carry on.

---

## Settings, every one of them

Everything below is on the **Настройки** tab. A change is saved the moment you
make it and is in force immediately — no restart. If a setting cannot be saved,
the checkbox goes back to what is really in effect and tells you why, rather
than lying.

### Where the text goes

| Setting | What it does | Default |
| --- | --- | --- |
| **Печатать в активное окно** | types the recognised words at the caret of whatever window was in front, as they are recognised | **on** |
| **Сразу копировать в буфер** | also copies each finished session to the clipboard | **off** |
| **Исправлять свои слова** | replaces a near miss of one of your own words with your word | **on** |

**Печатать в активное окно** off means nothing is typed anywhere: the session is
still recognised, still shown in the panel and still written to
`logs\YYYY-MM-DD.txt`, and **Копировать** is how you get it out.

**Сразу копировать в буфер** overwrites the clipboard after every session, which
is worth leaving off unless something else in your workflow wants the text there.
It is a one-way operation: other programs read from the clipboard, and this app
still inserts text as keystrokes.

**Исправлять свои слова** works from the words in `phrases.txt` — see
[Custom vocabulary](#custom-vocabulary-phrasestxt). It works on finished phrases
only, never on the half-heard text, and every replacement is written to
`logs\app.log` so you can see whether it is helping.

### Checking your own words

The **Проверить свои слова** button under that checkbox asks the model which of
your words it can hear at all. It takes about a second and works from the tray —
the panel does not have to be open. The detail is in
[Custom vocabulary](#custom-vocabulary-phrasestxt).

### Startup

**Автозапуск с Windows** — start at login, with no console and no panel. The
equivalent from a shell:

```powershell
.\.venv\Scripts\python.exe .\src\run.py --autostart on
.\.venv\Scripts\python.exe .\src\run.py --autostart status
.\.venv\Scripts\python.exe .\src\run.py --autostart off
```

### Language

**Русский** and **English**, applied at once. The panel, the tray menu, the
notifications and the reports all repaint in the new language without a restart
and without losing the text in the box, the recording state or the switch
positions.

The choice is remembered in `settings.json`.

Note that this is the **interface** language only. It has nothing to do with the
language being dictated — see [Models and languages](#models-and-languages).

### Dictation key

Click the field and press the combination you want. It is validated, saved and
taken into use immediately. `Esc` cancels.

Three things are refused, each with the reason shown under the field:

- a main key with no modifier — hold `Ctrl`, then press `F5`;
- modifiers and nothing else — press `Ctrl + Shift`, let go, and it says a normal
  key is needed as well. A combination has to end on a key that is not a
  modifier, because that is the key the hook blocks and the key whose release
  ends a held recording;
- a key that cannot be named, such as a media or browser key.

While the capture is live the hook swallows **every** keystroke in the system, so
`Win` cannot open the Start menu and `Win + D` cannot minimise everything. That is
deliberate — it is the only way `Win` itself can be recorded — but it means the
keyboard is inert for those few seconds. `Esc` ends it; quitting the app ends it
too.

**Сбросить** forgets your combination and brings back the two shipped defaults.

A combination you wrote into `settings.json` by hand and got wrong is not
taken out quietly either: the broken entry is dropped, the ones that work stay in
effect, and the panel and the tray name what was dropped and why. The Menu key is
accepted as `menu`, `apps` or `context_menu`, so a typo in the key's name is not
what makes a combination unusable.

Escape is reserved as the cancel key, so it can never become the main key of a
recorded combination.

### What gets blocked

Taking the shortcut away from Windows **is what the hotkey does**. While WinVosk
is running, your combination does not reach the system, so `Ctrl + Menu` cannot
open a context menu behind a recording and `Win + Ctrl + →` cannot switch
desktops.

Only the **last** key of your combination is taken, and only while you are holding
it. The modifiers always reach Windows on purpose — blocking one would leave it
stuck down and break typing everywhere else. So a plain `Menu` with no Ctrl still
opens the menu as usual.

Windows repeats a key you hold, and the repeats are swallowed too. That matters
more than it sounds: push to talk means holding the keys for a whole sentence, and
an earlier version let the repeats through. The application never saw the first
press, so a repeat arriving on its own opened the menu anyway.

Two things no hotkey can take back: a combination made **only** of modifiers,
such as a bare `Win`, which has no last key to block — the capture refuses it and
tells you why; and `Ctrl + Alt + Del`, which Windows routes past every user-mode
hook by design.

### Checking it yourself

```powershell
.\.venv\Scripts\python.exe .\tools\hook_probe.py --specs ctrl+menu 20
```

Run it with WinVosk closed, press the combination, and every key is printed as
the hook decides it: `BLOCKED` was taken, `passed` reached Windows. If a context
menu appears, the line above it names the key that got through.

### Where the settings live

`settings.json`, next to the exe (or in the checkout root):

```json
{
  "hotkeys": ["win+ctrl+right", "alt+win"],
  "live_typing": true,
  "copy_to_clipboard": false,
  "correct_words": true,
  "toggle_recording": false,
  "language": "ru"
}
```

Nothing in that file can stop the app from starting. A missing, malformed or
wrongly shaped file costs one line in `logs\app.log` and the defaults are used;
a byte order mark (Notepad and PowerShell both add one) is read correctly; a
combination that cannot be parsed costs only itself rather than crashing under
`pythonw.exe` where nobody would see the traceback. **Сбросить** and
deleting the file both restore the defaults.

### Settings that are not switches

These live in `src\winvosk\config.py` and need an editor:

| Constant | Meaning |
| --- | --- |
| `MODEL_NAME` | the preferred model directory |
| `MIC_DEVICE` | PortAudio input index; `None` for the system default |
| `TYPE_DELAY` | pause after each revision, in seconds — raise it if a target application cannot keep up |
| `MAX_SESSION_SECONDS` | ceiling on one session; rare while holding, load-bearing in toggle mode |
| `SHOW_WORDS` | log word timings instead of just the text |

---

## Custom vocabulary (`phrases.txt`)

`phrases.txt`, next to the exe, is your own word list. One word or phrase per
line, no punctuation, `#` starts a comment:

```
телеграм
фейсбук
дропбокс
проверка связи
```

It does two jobs, and they are worth separating because they answer different
questions.

### 1. Which of your words can the model hear?

Press **Проверить свои слова** under **Исправлять свои слова** in
**Настройки**. A window opens listing every phrase with a verdict:

```
phrases file: D:\AI\Vosk\phrases.txt  (7 phrase(s))
heard by the model : 6
  ok      телеграм
  ok      фейсбук
  ok      дропбокс
  MISSING йоцунфэнь
unknown to the model: 1
```

It takes about a second. The same check from a shell, if you prefer:

```powershell
.\.venv\Scripts\python.exe .\src\run.py --vocab-check
```

**ok** means the word is in the model's vocabulary. **MISSING** means it is not,
and no amount of configuration will change that at run time — see
[If it recognises badly](#if-it-recognises-badly).

The check builds a throwaway recogniser from your phrases and reads vosk's own
log, which lists every word it has to ignore. The model's vocabulary lives inside
the compiled decoding graph, so there is no word list on disk to read; vosk tells
us instead.

### 2. Which of your words does it hear *wrong*?

**ok** does not mean the word comes out right. The model knows «дропбокс» and
still prefers a different word for the same sound. That is an ambiguity, not a
gap, and it is fixed **after** the decode rather than inside it:

| It heard | You get | Why |
| --- | --- | --- |
| `дропбок` | `дропбокс` | a dropped letter, 0.93 similar |
| `топбокс` | `дропбокс` | a wrong consonant, 0.80 similar |
| `друг бокс` | `дропбокс` | split across a space, glued back first |
| `дропбокс` | unchanged | exact |
| `дропбоксы` | unchanged | an inflection of your own word, not a mistake |
| `бокс друг` | unchanged | the glue only runs forwards |
| `молоко` | unchanged | nothing near the list |

Rules worth knowing before you fill the file in:

- **Words shorter than four letters are never touched.** A wrong correction on a
  short word is easy to miss and annoying to find.
- **Anything more than about 0.75 similar is left alone.** That is what keeps
  «подбоксник» and «дропбоксник» intact next to «дропбокс».
- **Add the forms you actually say.** Russian inflects heavily: add `дропбоксы`
  and `фейсбука` as their own lines rather than expecting one entry to cover them.
- **Only finished phrases are corrected**, never the half-heard text, so the
  screen does not jump around for words the model has not settled on.
- **Every replacement is logged**: `corrected 1 word(s): дропбок -> дропбокс` in
  `logs\app.log`. If the list is getting in the way, that line is where you will
  see it.

Measured on the machine this was written on: against 500 random words the false
replacement rate is about 0.03 %, and over 138 neighbouring word pairs in a real
diary nothing was changed at all.

### Words marked MISSING

A word the model has never heard cannot be added at run time. Doing it properly
means rebuilding the language model: download the `*-compile` variant of the
model, put the words in `db/extra.txt`, and regenerate `graph/Gr.fst` and
`graph/HCLr.fst` with `compile-graph.sh`. That needs a Kaldi build with `irstlm`,
`opengrm`, `srilm` and `phonetisaurus`, and the guides for it target Ubuntu. It
is not something this app can do on Windows on demand.

Practical answers while that is out of reach, in the order worth trying:

1. **Rewrite the word** so it sounds like something the model knows — «фейсбук»
   instead of «фейсбук мессенджер».
2. **Try a bigger model.** See [Models and languages](#models-and-languages).
3. **Leave it.** Recognised forms show in the panel and in
   `logs\YYYY-MM-DD.txt`, so it is always visible what it actually heard.

---

## If it recognises badly

Work down this list; it is ordered by how often each cause turns out to be the
real one.

### Nothing is typed at all

1. **The panel is in front.** If any window of this app is in front while a
   recording is live, live typing is held back on purpose. Close the panel.
2. **The app is not running.** Look for the tray icon; a second launch does
   nothing at all, because only one instance is allowed.
3. **The combination did not change.** Only the main key is blocked, so
   `Win + Ctrl + Right` works but a combination Windows acts on through its
   modifiers alone — a bare `Win`, for instance — cannot be neutralised and will
   never reach the app.
4. **The Windows Search panel is open.** It holds the foreground and refuses to
   give it up. Press `Esc` first.

### It types, but the wrong words

1. **It is not your terminology.** That is what `phrases.txt` is for. Add the
   words, press **Проверить свои слова**, read the verdict.
2. **The small model.** `vosk-model-small-ru-0.22` is 44 MB and noticeably weaker
   on noisy or telephone audio. A bigger model in `models\` fixes most of it.
3. **It is genuinely noisy.** The chip animates for anything above a gate, so a
   quiet speaker and a silent microphone look the same on it. Check with
   `--diagnose` (`records from`), not with the chip.
4. **You are holding too long.** The model revises an open utterance, and the
   more it has to reconsider, the more the text jumps. Let go between sentences.

### Words run together or the punctuation is wrong

Expected. Vosk emits a stream of lowercase words with no punctuation and no
capitalisation. A space is added after each finished utterance so words do not
run together, but nothing else is added. Type your own capitals and punctuation
afterwards, or dictate a line at a time.

### Recognised words are wrong in a way that looks like a bug

Two known shapes, both upstream behaviour rather than a fault here:

- **A word split in two**: «друг бокс» instead of «дропбокс». The corrector glues
  neighbouring tokens and compares the pair, which fixes this. A word split into
  *three* tokens is out of reach — «йо цун фэнь» comes out as «йо цунфэнь».
- **The same audio gives a different result twice.** Free decoding is a search,
  not a lookup; the acoustic score of two similar words is close.

### The microphone is not the one I want

```powershell
.\.venv\Scripts\python.exe .\src\run.py --diagnose
```

Read two lines:

- `records from` — the device a recording will actually open. PortAudio's own
  default can name no device at all on some machines, in which case the app
  resolves the index from the host API instead. This line is the truth.
- `input devices:` — every device PortAudio can see, with its channel count and
  its **native** sample rate.

That last part matters: a device that only accepts 44100 Hz cannot record at the
16000 Hz the decoder wants, and PortAudio refuses the stream outright
(`Invalid device`). There is no setting that fixes that — it is a property of the
driver. Check the native rate before blaming the app.

---

## Models and languages

WinVosk ships with **Russian** (`vosk-model-small-ru-0.22`, 44 MB). Vosk
publishes models for **26 languages**, and any of them can be dropped into
`models\` — the app finds it by itself, no configuration and no code change.

### How to install another one

1. Pick a model from the table below.
2. Download it from the **Hugging Face mirror** — the official host
   `alphacephei.com` throttles large files to unusable speed on many networks:

   ```
   https://huggingface.co/rhasspy/vosk-models/resolve/main/<code>/<model>.zip
   ```

   For example English, the small one:

   ```powershell
   curl.exe -L -o .\tmp\en.zip https://huggingface.co/rhasspy/vosk-models/resolve/main/en/vosk-model-small-en-us-0.15.zip
   Expand-Archive .\tmp\en.zip .\models -Force
   ```

3. Restart the app.

**Keep exactly one model in `models\`.** If several are there, the shipped
Russian one wins; to dictate in another language, delete or rename the Russian
folder first. This is deliberate: the shipped setup must never change under you.

Confirm what was picked up with `--diagnose`, whose `model` line is the truth.

### The list

Main languages first. Sizes are the download (`.zip`), not the unpacked model.

**Main**

| Language | Code | Model | Zip |
| --- | --- | --- | --- |
| Russian | `ru` | `vosk-model-small-ru-0.22` | 44 MB |
| English | `en` | `vosk-model-small-en-us-0.15` | 39 MB |
| English, large | `en` | `vosk-model-en-us-0.22-lgraph` | 125 MB |
| Ukrainian | `uk` | `vosk-model-small-uk-v3-small` | 137 MB |
| German | `de` | `vosk-model-small-de-0.15` | 44 MB |
| French | `fr` | `vosk-model-small-fr-0.22` | 40 MB |
| Spanish | `es` | `vosk-model-small-es-0.42` | 38 MB |
| Italian | `it` | `vosk-model-small-it-0.22` | 47 MB |
| Portuguese | `pt` | `vosk-model-small-pt-0.3` | 31 MB |

**Also widely spoken**

| Language | Code | Model | Zip |
| --- | --- | --- | --- |
| Polish | `pl` | `vosk-model-small-pl-0.22` | 51 MB |
| Turkish | `tr` | `vosk-model-small-tr-0.3` | 35 MB |
| Dutch | `nl` | `vosk-model-small-nl-0.22` | 39 MB |
| Dutch, large | `nl` | `vosk-model-nl-spraakherkenning-0.6-lgraph` | 101 MB |
| Czech | `cs` | `vosk-model-small-cs-0.4-rhasspy` | 44 MB |
| Swedish | `sv` | `vosk-model-sv-rhasspy-0.15` | 290 MB |
| Uzbek | `uz` | `vosk-model-small-uz-0.22` | 49 MB |
| Persian | `fa` | `vosk-model-small-fa-0.5` | 59 MB |
| Arabic | `ar` | `vosk-model-ar-mgb2-0.4` | 318 MB |
| Vietnamese | `vi` | `vosk-model-small-vn-0.4` | 32 MB |
| Vietnamese | `vi` | `vosk-model-vn-0.4` | 71 MB |

**The rest**

| Language | Code | Model | Zip |
| --- | --- | --- | --- |
| Chinese | `zh` | `vosk-model-small-cn-0.22` | 42 MB |
| Japanese | `ja` | `vosk-model-small-ja-0.22` | 47 MB |
| Korean | `ko` | `vosk-model-small-ko-0.22` | 83 MB |
| Hindi | `hi` | `vosk-model-small-hi-0.22` | 42 MB |
| Catalan | `ca` | `vosk-model-small-ca-0.4` | 41 MB |
| Esperanto | `eo` | `vosk-model-small-eo-0.42` | 42 MB |
| Breton | `br` | `vosk-model-br-0.8` | 78 MB |
| Tagalog | `tl` | `vosk-model-tl-ph-generic-0.6` | 314 MB |

Notes:

- **`small` vs `lgraph`.** A `lgraph` model replaces the static grammar with a
  dynamic one: much better accuracy, several times the RAM and a slower start.
  Both are listed above where Vosk publishes both; the large one is usually worth
  it on a machine with 8 GB or more.
- **A model decides the language, not the interface.** The panel and the tray are
  Russian or English either way — see
  [Language](#language) in the settings section.
- **Your word list follows the model.** `phrases.txt` is a list of words *in the
  language being dictated*. An English model with a Russian word list will simply
  find nothing to correct.
- **A bigger model is not automatically better on a noisy microphone.** It is
  slower and it holds more RAM; the gain is in vocabulary and accuracy on clean
  speech.
- **No Belarusian, Serbian, Croatian, Slovak, Hebrew or Thai models exist** in
  the Vosk model set. `be`, `sr`, `hr`, `sk`, `he`, `th` are simply not there —
  a limitation of the upstream models, not of this app.

---

## What it deliberately does not do

- **Your hotkey takes its combination away from Windows while the app
  runs.** That is the point: it is what stops the shortcut from firing behind
  WinVosk. Only the last key is taken — the modifiers always reach Windows, so
  they can never be left stuck down.
- **No punctuation or capitals.** See
  [Words run together](#words-run-together-or-the-punctuation-is-wrong).
- **No speaker diarisation.** One voice, one stream.
- **No phrase list fed to the decoder.** Passing your words to the recogniser as
  a grammar is a *hard* restriction, not a bias: measured here, the same audio
  that yields a full sentence in free decoding yields the **empty string** with a
  three phrase grammar. That is why correction happens after the decode.
- **No clipboard insertion.** Ever. Text is typed as keystrokes.
- **No background booster.** Vosk 0.3.45 has no word boosting — `SetWords` is a
  boolean for word timestamps, and the full C API has no boosting call — so an
  own-word correction has to happen after the decode.
- **No streaming to a server.** The app opens a microphone and decodes locally.
  Nothing is uploaded, because there is no upload path in it.

---

## Files and folders

| Path | What it is | Safe to delete? |
| --- | --- | --- |
| `WinVosk.exe` | the application | no |
| `_internal\` | Python, Tcl/Tk, the Kaldi decoder, PortAudio, Pillow | no |
| `models\<model>\` | the speech model | yes — put another one back |
| `logs\app.log` | diagnostics, rotated at 2 MB × 3 | yes |
| `logs\YYYY-MM-DD.txt` | the dictation diary, one file per day | yes, it is only a copy |
| `phrases.txt` | your own word list | yes — the app ships a commented template |
| `settings.json` | your settings | yes — costs the defaults only |

There are no absolute paths anywhere in the tree, so the folder can live
anywhere. The app finds itself through `__file__` in the source checkout and
through the exe's own folder once it is built.

### The diary

Every finished session is appended to `logs\YYYY-MM-DD.txt` in UTF-8, whether or
not anything was typed. It is a plain text file — open it in Notepad. It is not
required by anything and can be deleted freely.

---

## When something goes wrong

```powershell
.\WinVosk.exe --diagnose
```

The report covers the version, the resolved folder, the model, the autostart
state, the hotkeys actually in effect, every switch, the settings file, the
typing delay, the session limit, the log path, the device the microphone will
open, and every input device PortAudio can see.

Two lines are worth reading twice:

- `base dir` — the folder the app resolved. It must be the folder the exe is in.
  If it is not, everything else on the report is about a different installation.
- `records from` — the device a recording will actually use.

A windowless build cannot print, so the same report is written to
`logs\report.txt` and shown in a message box.

**The log is the diagnostic.** `logs\app.log` records every session, every
setting change, every hotkey change and every correction:

```powershell
Get-Content .\logs\app.log -Tail 40
```

A healthy log has no `WARNING` and no `ERROR`. If you report a problem, the last
30 lines of this file are the most useful thing you can attach.

More detail on the internals, the verification probes and the design decisions is
in [`docs/HOWTO.md`](docs/HOWTO.md).

---

## Building from source

Needs Python 3.14 and the five pinned packages. From the project root:

```powershell
.\.venv\Scripts\python.exe -m pip install vosk==0.3.45 sounddevice==0.5.6 `
    pystray==0.19.5 Pillow==12.3.0 pyperclip==1.11.0
.\.venv\Scripts\python.exe .\tools\build_exe.py
```

That writes `dist\WinVosk\` — one folder, no console, with the model copied next
to the exe. `WinVosk.spec` keeps vosk's unused streaming client out of the bundle
in the first place; `build_exe.py` then prunes `_internal\` of what is left that
the app cannot reach — unused Pillow codecs, wheel metadata, two dead Tcl
directories and Tcl's 609-file timezone database — and reports every pattern
that matched nothing, so an upstream rename cannot pass unnoticed.

Check a build without starting it:

```powershell
.\dist\WinVosk\WinVosk.exe --check-bundle
```

It builds the real panel, resolves the `ttk` theme, raises the chip out of the
tray with its antialiased Pillow plate, and reports. It never opens the
microphone, so it runs on a machine with no input at all — and it is the only
check that would notice a bundle missing a Tcl script or a Pillow extension.

---

## Upstream

WinVosk is a fork of [alphacep/vosk-api](https://github.com/alphacep/vosk-api),
the Vosk Speech Recognition Toolkit by AlphaCephei, Apache-2.0. The `vosk`
package supplies all audio decoding, the prebuilt Kaldi decoder and the model
format.

Everything else — `src\winvosk\`, `src\run.py`, `tools\` — is original work. No
upstream file is vendored or patched, so moving to a newer `vosk` is a version
bump rather than a merge. **Decoder questions go upstream; dictation behaviour
questions go here.**

The models are the ones Vosk publishes and carry their own licences.

- User guide and internals: [`docs/HOWTO.md`](docs/HOWTO.md)
- Notes for agents and contributors: [`AGENTS.md`](AGENTS.md)
- Project context: [`project.md`](project.md)