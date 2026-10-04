# History tab and the two write switches

Spec, not an implementation. Nothing in `src\` has been touched; this file is the
only thing written, and it is written to be argued with.

## Goal

Two on/off switches in the Settings tab — one for the log file, one for the
dictation history — and a third panel tab that lists the recent history and
copies a record to the clipboard.

## Decisions taken

| Question | Answer |
|---|---|
| What «Логи» off does | `app.log` keeps `WARNING` and `ERROR`, drops `INFO`. The file is still written, so a crash under `pythonw.exe` still leaves a trace. |
| Where the history window is | A third tab in the panel, next to «Диктовка» and «Настройки». |
| What the list holds | The last 10 records, across all days. |
| What can be copied | One record, by double-clicking its row. |
| What «История» off does | New records are not written. Files already on disk stay and stay visible. |

## What is not in this change

- No pruning of `logs\`. The diary has grown forever and this change only makes
  it visible. A retention switch is a separate decision.
- No "copy all", no "copy one day", no export. One record is the whole feature.
- No search, no filter, no edit, no delete. A history you can change is not a
  history.
- `WinVosk.spec` and `tools\build_exe.py` are untouched: no new module is added,
  `diary` / `settings` / `panel` / `widgets` are already collected.

## 1. The log switch

`settings.json` key `write_log`, default **on** (`config.LOG_WRITE_DEFAULT`).
Read by `settings.logging_enabled()`, written by `store_logging_enabled()`.

`config.setup_logging()` gains a `verbose` keyword and splits two levels that are
currently one:

- the **root** logger stays at `INFO`, so records are still generated and
  third-party loggers behave exactly as before;
- the **handler** level is `INFO` when the switch is on and `WARNING` when it is
  off.

Filtering at the handler rather than at the root is the whole point: the
suppression has to be a property of the file, not of the process. A `--diagnose`
run and a probe still get their `INFO` lines, and `WARNING` still reaches the
file under `pythonw.exe`.

`config.set_log_verbose(verbose) -> bool` walks the root handlers and re-levels
the `RotatingFileHandler` ones, so flipping the switch takes effect at once —
`RotatingFileHandler` is a `FileHandler`, and `FileHandler.setLevel` exists
precisely for this. No restart, no rebuild.

`main()` calls `config.setup_logging(verbose=settings.logging_enabled())`. That is
the one place the order matters: the file is attached before anything can log,
and the level it is attached at comes from the same `settings.json` every other
switch reads. `settings.load()` may emit a `WARNING` in the microseconds before
the handler exists; that goes to `logging.lastResort`, which opens `os.devnull`
when `sys.stderr` is `None`, so a `pythonw.exe` start is not affected.

`--diagnose` gains one line under `log file`:

```
log detail  : full | errors only
```

## 2. The history switch

`settings.json` key `write_history`, default **on**
(`config.HISTORY_WRITE_DEFAULT`), read by `settings.history_enabled()`, written
by `store_history_enabled()`.

The gate goes **inside** `diary.append()`, not at the call site in
`run.py:498`. One gate that cannot be forgotten by the next caller is worth more
here than one that keeps `diary` free of `settings`; the import is legal
(`settings` imports `config`, `hotkey`, `text` — never `diary`).

```python
def append(text: str) -> bool:
    if not settings.history_enabled():
        log.info("history is off, this session is not recorded")
        return False
    ...
```

`run.py` needs no change on this path. It already ignores the return value.

## 3. Reading the history back — `diary.py`

The reader belongs in `diary.py`, which already owns the format. `project.md`
gets one changed line instead of a new module in the layout.

```python
RECORD_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}\.txt$")
RECORD_LINE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s*(.*)$")

class Entry(NamedTuple):
    day: date
    stamp: str          # "14:22:05"
    text: str

def recent(limit: int = config.HISTORY_RECENT) -> list[Entry]: ...
```

Rules, each of which is a way the naive version breaks on real files:

- **Only dated files.** `RECORD_NAME` filters `app.log`, `app.log.1`,
  `report.txt` and anything else that happens to be sitting in `logs\`. Sorted
  by name descending, which is chronological because the names are ISO dates.
- **Newest first.** Files newest-first, lines within a file last-first, and the
  list is not reversed: the top row is the most recent thing that was said.
- **Stop at the limit.** Collect until `limit`, then stop reading — a diary with
  a year of records must not be read to answer a question about ten of them.
- **A line being appended right now.** `splitlines()` yields a last line with no
  newline; it is used as it stands. Refusing to show a record because the writer
  has not closed the line yet would be the wrong answer.
- **Junk is skipped, not fatal.** A line that is not `RECORD_LINE`, a file that
  cannot be decoded, a file that cannot be read — each costs that line or that
  file, logged at `WARNING`, and the rest of the list stands.
- **No `theme`, no `tkinter`.** `diary` is imported by the headless probes, so
  the reader is plain text in, plain objects out.

`config.HISTORY_RECENT = 10` sits next to `MAX_SESSION_SECONDS`, so the "last
ten" is one named constant rather than a literal in the panel, the reader and the
documentation.

## 4. The third tab

**Order is fixed: «Диктовка», «Настройки», «История» — the history tab is last.**
It is the one tab that is read rather than acted in, so it sits after the two
that are worked in, and a user who comes to the panel for dictation finds the
record button where it has always been. `Tabs.add` is called in that order and
nothing reorders it afterwards; `_restore()` must `select(0)` rather than leave
the index it found, so a theme change cannot leave the panel on the history tab.

There is **no tray menu item** for it. The tray carries what has to be reachable
with the panel closed — start, stop, show, copy, quit — and the history needs the
panel anyway, because the tab is inside the panel. A menu entry that only opens a
window which then has to be navigated to is one more step for one fewer click.

`Panel._build()` adds a `widgets.Scroller` with key `tab_history`, so ten rows
that wrap to three lines each still scroll on a short screen. `WIDTH` and
`HEIGHT` do not change: three tab labels fit in 720 px, and the settings tab
already scrolls.

Layout, top to bottom, all of it out of `theme` and `widgets`:

- `history_caption` — a `widgets.caption`, «Последние записи» / «Recent records».
- `history_hint` — one line, «Двойной щелчок по строке копирует её в буфер» /
  «Double-click a row to copy it». The feature is invisible without it.
- `history_off_note` — shown **only** while the switch is off, in `text_muted`:
  new records are not being written, the ones below are what is already on disk.
- one `widgets.Card` holding the rows, separated by `widgets.rule`;
- `history_empty` — a `Paragraph` in place of the card when there is nothing.

### The row

`widgets.HistoryRow(tk.Frame)` — a new widget, because no existing one is a
selectable multi-part row:

| part | widget | roles |
|---|---|---|
| stamp column | `Frame` of a fixed pixel width | `surface` → `surface_hover` on `<Enter>` |
| stamp | `Label`, `theme.mono(TYPE_TINY)` | `text_subtle` |
| text | wrapped `Paragraph` | `text` |

The stamp column is a **frame**, not a label with a width: `-width` on a `tk.Label`
counts characters, and 92 characters is 726 pixels, which is how the first build
of this row let one column eat the whole card and left every record broken one
word per line. On a frame the same option is a screen distance. The panel passes
the width of the widest stamp it is about to render, because most rows carry a
bare time and only the older ones carry a day.

Bindings: `<Enter>` / `<Leave>` for the hover and `<Double-Button-1>` to copy, on
the row, the column, the stamp, the paragraph **and** the paragraph's inner `Text`
— Tk does not deliver an event to an ancestor of the widget under the pointer, and
the pointer is over that `Text`. `Paragraph.text_widget()` hands it out for the
same reason `CodeBox.text_widget()` already did.

There is no selection state and a single click does nothing. Double-click, not
single: a click that silently replaces the clipboard is the kind of surprise that
costs a user the contents of what they were about to paste, and the hover already
says the row is live.

### Refreshing

The tab is populated at build time, and again on every arrival, because the panel
spends most of its life on the dictation tab while records are being written:

1. `Tabs` gains an optional `on_select` callback, fired from `Tabs.select()`.
   `Panel._on_tab` reloads when the index is the history tab. `Tabs` is a custom
   widget, so this is one call in one method — there is no `<<NotebookTabSelected>>`
   to bind to. The callback fires on the first `add` as well, so it has to put up
   with being called before the other pages exist.
2. `App._on_stop`, after a successful `diary.append`, calls
   `self._panel.reload_history()`. It already runs on the Tk thread — it is
   handling an event off `self._events` in `_pump` — so this needs no queue
   round-trip.
3. `Panel._restore()` reloads too, or a theme change would leave the tab empty
   until it was reselected.

`Scroller.bind_wheel_below` is the fourth piece and was not in the first draft of
this spec: the rows do not exist when the page binds its wheel, and the `Text`
inside a row would scroll its own three lines instead of the page. The same method
made `_bind_below` walk the whole subtree rather than one level, which also fixes
the wheel over the deepest control on the settings tab.

### Copying

One path, the one that already exists. The row puts
`("copy_history", text)` on the command queue; `App._handle_command` routes it to
`App._copy_history(text)`, which calls `keystrokes.copy_to_clipboard` — the same
function `App._copy` uses — then sets `Panel.set_history_hint` **and** the tray
notification. `nothing_to_copy` on failure, in `danger`.

The hint paragraph on the history tab is not `set_option_hint`: that one lives on
the settings page and is a different widget in a different tab.

## 5. The Settings tab

A third card in the right column, after «Оформление» and «Язык»:

- `group_records` — «Запись» / «Records»
- `option_history` — «Сохранять историю» / «Keep the history`
- `history_switch_hint` — where it goes and what is in it
- `option_log` — «Писать журнал в файл» / «Write the log file»
- `log_switch_hint` — **and that errors are written either way**

Two switches, one card: they are two answers to the same question, which is how
much of this machine the app leaves a trace on.

`App._set_history` and `App._set_logging` follow the shape of every other switch
in `run.py` — write first, roll the switch back on a failed write, say what
changed in `set_option_hint`, and for the log also call `config.set_log_verbose`
and re-level the live handler. A switch that shows "on" while the disk holds
"off" is the defect this file exists to prevent.

The settings page grows by about 120 px and keeps scrolling.
`check_settings_reachable` is the thing that proves the bottom is still
reachable, and it is in the bar.

## 6. `text.py`

Ten new keys, `ru` and `en`, no exceptions:

| key | ru | en |
|---|---|---|
| `tab_history` | История | History |
| `group_records` | Запись | Records |
| `option_history` | Сохранять историю | Keep the history |
| `history_switch_hint` | Every finished session is appended to the file for its day; what is already there stays | то же на английском |
| `option_log` | Писать журнал в файл | Write the log file |
| `log_switch_hint` | Выключено — в журнал попадают только ошибки; он всё равно нужен | Off — only errors reach the log, and it is still what a crash has to be found from |
| `history_caption` | Последние записи | Recent records |
| `history_hint` | Двойной щелчок по строке копирует её в буфер | Double-click a row to copy it |
| `history_off_note` | Новые записи не сохраняются. Ниже — то, что уже записано. | New records are not being saved. Below is what is already there. |
| `history_empty` | Записей пока нет | No records yet |
| `history_on` | История сохраняется | The history is being saved |
| `history_off` | История выключена — новые записи не сохраняются | History is off — new records will not be saved |
| `log_on` | В журнал пишется всё | The log keeps everything |
| `log_off` | В журнал пишутся только ошибки | The log keeps errors only |

**Fourteen, not ten.** The first draft of this table listed ten; the four
`on`/`off` lines are what the app says in the hint under the switches after a
change, and they were missing from the count.

`copied` and `nothing_to_copy` already exist and are reused for the tray
notification. `save_failed` is reused for a failed write of either switch, the
same way `live_typing` and `correct_words` reuse it.

`tab_history` must be registered in `self._messages` like the other two tab
labels, or the tab strip keeps its old language after a switch — `Tabs.add`
already stores the key, so this is one line in `_build`.

## 7. Probes

### `tools\settings_probe.py` (extended, case 6 and one new case)

- both new keys: read back, wrong type rejected, string `"yes"` rejected, the
  default used when the key is absent, and the other keys surviving the write
  (case 6 already proves that for the existing four);
- a new case for `config.set_log_verbose`: attach the handler in a temp
  `LOG_FILE`, assert the handler level is `INFO`, flip it, assert `WARNING`, and
  assert a `log.info()` after the flip produced no file growth while a
  `log.warning()` did.

### `tools\history_probe.py` (new, headless)

Rebinds `config.LOGS_DIR` to a temp folder — the same trick `settings_probe.py`
uses on `settings.SETTINGS_FILE` — and lays down the cases that matter:

- three dated files, so the answer crosses a day boundary;
- a line with no newline at the end, as a writer mid-append leaves it;
- a junk line, a BOM, and an empty file;
- `app.log` and `report.txt` sitting in the same folder, which must not be read;
- `recent(3)` returning the newest three, newest first, in the right order;
- `recent(50)` returning everything, and `recent(0)` returning nothing;
- `append()` with the switch off returning `False` and creating no file, and
  with it on creating one.

Prints `VERDICT: PASS` / `FAIL` in the shape of the other probes.

### `AGENTS.md` § Verification

The tenth probe gets a paragraph next to the ninth: what it covers, that it
needs no GUI, microphone, model or real hook, and when to run it — after any
change to `diary.py`, `settings.py` or the history part of `run.py`.

## 8. Documentation

| file | what changes |
|---|---|
| `README.md`, `README.ru.md` | Two rows in the settings table, a short «History» section: the tab, the `[HH:MM:SS] text` format, the last ten, double-click to copy, and that switching it off stops new records. **Both in the same commit** — `readme_probe.py` fails on heading parity, and one of the two files being a lie is the defect. |
| `docs\HOWTO.md` | § Settings gains both switches; a new § on the history tab: the format, the reader's rules and why each is there, newest-first, the ten, why double-click; § Layout gains the `diary.py` and `panel.py` lines; § Verification helpers gains `history_probe.py`. |
| `project.md` | `diary.py` — "dated history under logs\" and the reader; `settings.py` — four switches become six, seven keys become nine; `panel.py` — two tabs become three; `config.py` — the two new tunables; Commands gains the probe. |
| `AGENTS.md` | § Release — the version; § Verification — the tenth probe; the invariant "a plain `pythonw.exe` launch has no console, so the log file is the only diagnostic" gains a rider: this is why the log switch drops `INFO` and not the file. |
| `docs\img\*.png` | Regenerated by `tools\make_images.py`, which also learned to photograph the history tab: the tab strip gains a label and the settings screenshot gains the new card. |
| `llms.txt` | No change. It points at the other four files and repeats none of their content. |

### What the build found that the spec did not say

- **The tab strip never repainted on a language change.** `Tabs.repaint_labels`
  was a stub whose docstring said «nothing to do», and nothing ever called
  `tab(frame, text=...)`. Adding a third tab meant adding a third key to a table
  nothing read, so the stub is now the real thing and `Panel.set_language` calls
  it. All three labels follow the switch now; before, none of them did.
- **A `tk.Label`'s `width` is in characters.** The first row built with
  `width=theme.measure(...)` asked for 92 characters — 726 pixels — and squeezed
  the text column to 44 px. Found by reading the screenshot the build had just
  produced, not by a test: every probe passed with it broken. The column is a
  `Frame` now, which takes a screen distance.

## 9. Version

**`1.6.3` → `1.7.0`, decided.** The change adds behaviour and adds keys; every
existing `settings.json` keeps loading and every existing default keeps its
meaning, which is the MINOR clause. `AGENTS.md` § Release also lists «`settings.json`
keys» under MAJOR, and read literally that would be 2.0.0 — the MINOR reading
wins here because nothing a user depends on stops working.

`config.VERSION` in `src\winvosk\config.py` is the only place the number is
written: `--diagnose` prints it on its first line and the panel puts it in the
window title, so `--check-bundle` and check 2 both fail loudly if it is missed.
`winvosk\__init__.py` derives from it and must not be touched.

## 10. Verification

The six checks, unchanged, from the project root, plus:

```powershell
.\.venv\Scripts\python.exe .\tools\settings_probe.py    # the two new switches, the handler level
.\.venv\Scripts\python.exe .\tools\history_probe.py     # the reader, and the gate on append
.\.venv\Scripts\python.exe .\tools\lang_probe.py        # ten new keys in both languages
.\.venv\Scripts\python.exe .\tools\readme_probe.py      # both READMEs, both new switches documented
```

`--check-bundle` gains two lines: `panel._notebook.select(2)`, then the history
tab is asserted to render (rows or the empty state, and the last row reachable
after scrolling). It is the only check that sees a third tab at all, and a tab
that cannot be scrolled to its end is the failure this project has already paid
for once on the settings tab.

Then, by hand, in this order — the order is the point:

1. Dictate one sentence. Open the history tab: the record is there, with today's
   date form.
2. Double-click it. The clipboard holds the sentence, and nothing else.
3. Switch «Сохранять историю» off. Dictate again. The tab still shows the first
   record and says new ones are not saved. `logs\` gains no new line.
4. Switch it back on. Dictate again. The record appears without reselecting the
   tab.
5. Switch «Писать журнал в файл» off. Dictate again. `app.log` does not grow by
   an `INFO` line. `Get-Content .\logs\app.log -Tail 20` still shows the last
   session's `typed N character(s)` line from before the switch.
6. Restart. `settings.json` shows `"write_log": false` and `"write_history":
   true`; the app comes up exactly as it was left.

## 11. Risks

- **The settings page grows.** ~120 px of scroll that did not exist. The
  reachability check covers it, but the panel is one card taller to scroll and
  that is a real cost on a 1366×768 screen.
- **`logging.lastResort` before the handler exists.** Covered in §1; the one
  thing to verify is that `--diagnose` under `pythonw.exe` still opens its
  message box, which is the only evidence a windowless build ever produces.
- **The diary grows without bound** and this change is what makes that visible
  to the user. Worth a retention switch next; deliberately not here.
- **A third tab changes every screenshot** in both READMEs. If they are not
  regenerated in the same commit, the pages show a panel that no longer exists.