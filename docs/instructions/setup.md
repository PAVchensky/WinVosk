# Setting up WinVosk

An install procedure for a person or an agent. Work through it in order, and do
not skip the verification at the end: a silent start looks identical to a
working one unless you read the log.

## 1. Requirements

- Windows x64.
- Python 3.14. The virtual environment must be built from it; the pins in
  `requirements.txt` resolve to wheels for this interpreter.
- About 90 MB of free space for the virtual environment and the model.

## 2. Virtual environment, from the repository root

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If `WinVosk.bat` prints "Virtual environment is missing", it names the five pins
it expects; they are exactly the ones in `requirements.txt`. Do not install a
newer or a looser version of `vosk` to "fix" something: the recogniser contract
this app is built on — `Result()` and `PartialResult()` reporting the whole open
utterance, and `SetWords` being a boolean for timestamps — is what 0.3.45 does.

## 3. Speech model

`models\` ships empty, and the app starts without one — it will simply refuse to
open the microphone and log that no model was found. Download the small Russian
model (45 MB, Apache 2.0), which is what this repository is verified against:

```powershell
New-Item -ItemType Directory -Path .\tmp -Force | Out-Null
curl.exe -L -o .\tmp\m.zip https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip
# if that host throttles, use the mirror that serves the same archive:
# curl.exe -L -o .\tmp\m.zip https://huggingface.co/rhasspy/vosk-models/resolve/main/ru/vosk-model-small-ru-0.22.zip
Expand-Archive .\tmp\m.zip .\models -Force
```

The language is the model's choice, not the app's. Any Kaldi model dropped into
`models\` is picked up automatically and nothing has to be configured, so
switching language is unpacking a different folder. The catch is the vocabulary:
the **small** models have a dynamic one, which is what makes `phrases.txt` work,
while the **big** models are fixed and more accurate — take a small model unless
you need the accuracy.

<https://alphacephei.com/vosk/models> is the authoritative list: every model, its
size, its error rate and its license. Check the license there before
redistributing a model.

## 4. Start it

```powershell
.\WinVosk.bat
```

That launches `pythonw.exe`, so there is no console and **no visible output**.
The log file is the only diagnostic: `logs\app.log`. If the tray icon does not
appear, read that file before concluding anything.

To watch it work instead, run the console build:

```powershell
.\.venv\Scripts\python.exe .\src\run.py
```

## 5. Verify

```powershell
.\.venv\Scripts\python.exe -m compileall -q .\src
.\.venv\Scripts\python.exe .\src\run.py --diagnose
.\.venv\Scripts\python.exe .\src\winvosk\file_transcribe.py --self-test
.\.venv\Scripts\python.exe .\tools\correct_probe.py
.\.venv\Scripts\python.exe .\tools\lang_probe.py
```

Read `--diagnose` carefully:

- `base dir` must be this checkout root. Anything else means the app resolved its
  paths somewhere unexpected and the rest of the report is meaningless.
- `records from` is the input device index a real run will use. It is resolved
  from the host API on purpose: PortAudio's default input device answers
  `paNoDevice` on some machines even when a microphone exists, and the one
  device it exposes may take only its native rate rather than 16 kHz.

The probes must end in `VERDICT: PASS`. Then dictate something with a person at
the keyboard: hold the hotkey, speak, let go, and confirm a new line in
`logs\YYYY-MM-DD.txt` plus `typed N character(s)` in `logs\app.log`. A
`WARNING`, an `ERROR` or a `hotkey hook failed` line means it is not finished.

## Traps

- **Do not install the `keyboard` package.** Its Windows backend does not deliver
  global hotkeys. The hook in `src\winvosk\hotkey.py` is hand written for this
  reason; the reasoning is in `docs/HOWTO.md`.
- **Do not insert text through the clipboard.** Text is typed with
  `KEYEVENTF_UNICODE`. Copying the result out is a separate, optional step.
- **Do not register a phrase list with `KaldiRecognizer` during dictation.** A
  grammar is a hard vocabulary restriction, not a bias; it makes free dictation
  return empty. `--vocab-check` is the safe way to consult a word list.
- **Only one instance may run.** Two of them fight over the microphone; the
  single-instance mutex is what stops it. A venv launch shows two processes, and
  that is the launcher, not two instances.
- **The panel and the recording chip must never take focus**, or the dictated
  words are typed into the app instead of the document.
- **In a frozen build, start `WinVosk.exe` from inside its folder.** It reads the
  model, the settings and the word list from the folder the exe is in.

## Own words

```powershell
Copy-Item .\phrases.example.txt .\phrases.txt   # then edit phrases.txt
.\.venv\Scripts\python.exe .\src\run.py --vocab-check
```

`phrases.txt` is personal and is not in the repository; `phrases.example.txt` is
the shipped example. `--vocab-check` reports which of your words the loaded
model can actually hear.

## Building and releasing

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe .\tools\build_exe.py        # dist\WinVosk\
.\.venv\Scripts\python.exe .\tools\package_release.py   # the release zip
```

`build_exe.py` puts the model and your own `phrases.txt` next to the exe, which
is what you want locally. `package_release.py` produces the archive meant for
other people: it removes `phrases.txt` and the log, adds `licenses\`, adds
`phrases.example.txt`, and prints the SHA-256 of the result. The license texts
must be in the archive, because the build ships Apache-2.0 code, the GCC runtime
and the PyInstaller bootloader.

## Documentation

- `README.md` — overview, install, model, verification.
- `docs\HOWTO.md` — the complete user guide.
- `AGENTS.md` — the verification bar and the invariants. Read it before changing
  code.