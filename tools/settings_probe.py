"""Headless regression probe for the settings file and the hotkey capture.

Everything here is pure logic: no Tk, no microphone, no model load and no real
hook, so it runs unattended in a fraction of a second. The filesystem cases
point `settings.SETTINGS_FILE` at a temporary directory, so the probe never
touches the machine's real settings.json and leaves nothing behind.

Run it from the project root:

    .\\.venv\\Scripts\\python.exe .\\tools\\settings_probe.py
"""

import ctypes
import logging
import queue
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

from winvosk import config, hotkey, settings, text

VK_ESCAPE = 0x1B
VK_F5 = 0x74

# name_for(vk) for one virtual key code per family the settings tab can record.
NAMED_CASES = [
    (0x5B, "win"), (0x5C, "win"), (0x11, "ctrl"), (0xA3, "ctrl"),
    (0x12, "alt"), (0xA5, "alt"), (0x10, "shift"), (0xA1, "shift"),
    (0x41, "a"), (0x5A, "z"), (0x37, "7"), (0x27, "right"), (VK_F5, "f5"),
    (VK_ESCAPE, "escape"),
]

UNNAMED_CASES = [0x07, 0x0A, 0x1A, 0xA6, 0xFF]

MODIFIERS = ("ctrl", "alt", "shift", "win")


class StubPanel:
    """Stands in for the Tk panel so `_poll_capture` can run without Tk."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def set_hotkey(self, label: str) -> None:
        self.calls.append(f"set_hotkey({label!r})")

    def show_capture(self) -> None:
        self.calls.append("show_capture()")

    def set_hotkey_hint(self, message: str, error: bool = False) -> None:
        self.calls.append(f"set_hotkey_hint({message!r}, error={error})")


class StubTray:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def notify(self, message: str, title: str = "") -> None:
        self.calls.append(f"notify({message!r})")


def fresh_listener() -> hotkey.HotkeyListener:
    """A listener that is never started: the hook thread is not needed here."""
    return hotkey.HotkeyListener(config.HOTKEYS, on_press=lambda: None,
                                 on_release=lambda: None)


def feed(listener: hotkey.HotkeyListener, vk: int, message: int) -> None:
    """One swallowed key, exactly as the hook callback would pass it on."""
    with listener._lock:
        listener._capture_key(vk, message)


def case_names() -> bool:
    print("\ncase 1: name_for names every key the capture can be given", flush=True)
    ok = True
    for vk, expected in NAMED_CASES:
        got = hotkey.name_for(vk)
        print(f"  name_for(0x{vk:02X}) = {got!r:10s} expected {expected!r}", flush=True)
        ok = ok and got == expected
    for vk in UNNAMED_CASES:
        got = hotkey.name_for(vk)
        print(f"  name_for(0x{vk:02X}) = {got!r:10s} expected None", flush=True)
        ok = ok and got is None
    return ok


def case_round_trip() -> bool:
    print("\ncase 2: every emitted name round trips through _keys_for and parse",
          flush=True)
    names = [name for _, name in NAMED_CASES]
    accepted = True
    for name in names:
        try:
            keys = hotkey._keys_for(name)
            print(f"  _keys_for({name!r}) = {sorted(hex(k) for k in keys)}", flush=True)
        except hotkey.HotkeyError as exc:
            print(f"  _keys_for({name!r}) REFUSED: {exc}", flush=True)
            accepted = False
    print(f"  _keys_for accepted every emitted name: {accepted}", flush=True)

    built = True
    for name in names:
        if name in MODIFIERS:
            continue  # a modifier alone is not a combination, by design
        for modifier in MODIFIERS:
            spec = f"{modifier}+{name}"
            try:
                main, mods = hotkey.parse(spec)
            except hotkey.HotkeyError as exc:
                print(f"  parse({spec!r}) REFUSED: {exc}", flush=True)
                built = False
                continue
            if name != "escape" and hotkey._NAMED.get(name) == VK_ESCAPE:
                built = False  # escape is reserved for cancelling, see _capture_key
    print(f"  parse accepted every spec name_for can build: {built}", flush=True)

    # The name a key is folded onto must reproduce the very key code it came
    # from, or a recorded combination would silently stop matching.
    folded = True
    for vk, name in NAMED_CASES:
        if vk in (0x11, 0xA3, 0x12, 0xA5, 0x10, 0xA1, 0x5B, 0x5C):
            continue  # modifiers are a set of codes on purpose
        if vk not in hotkey._keys_for(name):
            print(f"  {name!r} does not contain 0x{vk:02X}", flush=True)
            folded = False
    print(f"  every name maps back onto its own key code: {folded}", flush=True)
    return accepted and built and folded


def case_capture_rules() -> bool:
    print("\ncase 3: capture rules, reachable without a real hook", flush=True)
    listener = fresh_listener()
    listener.start_capture()
    print(f"  capturing after start_capture: {listener.is_capturing}", flush=True)

    for vk in (0x11, 0x12, 0x10, 0x5B):
        feed(listener, vk, hotkey.WM_KEYDOWN)
    still_held = listener.poll_capture()
    print(f"  modifiers alone, still held, give no result: {still_held!r}",
          flush=True)
    ok = still_held is None
    for vk in (0x11, 0x12, 0x10, 0x5B):
        feed(listener, vk, hotkey.WM_KEYUP)  # released, so none of them is held now
    only_modifiers = listener.poll_capture()
    print(f"  released, it says why: {only_modifiers!r}", flush=True)
    ok = (ok and only_modifiers is not None and only_modifiers[0] == "invalid"
          and only_modifiers[1] == text.t("capture_needs_main_key"))

    # Which release fires it matters: letting go of one modifier while another
    # is still down is not the end of anything.
    listener.start_capture()
    for vk in (0x11, 0x10):
        feed(listener, vk, hotkey.WM_KEYDOWN)
    feed(listener, 0x10, hotkey.WM_KEYUP)   # shift up, ctrl still held
    partial = listener.poll_capture()
    feed(listener, 0x11, hotkey.WM_KEYUP)   # now the last one goes
    finished = listener.poll_capture()
    print(f"  one modifier still held: {partial!r}, then {finished!r}", flush=True)
    ok = (ok and partial is None and finished is not None
          and finished[0] == "invalid")

    # A result already reached must survive the releases that follow it, or
    # `ctrl+shift+b` would be lost on the way up. The app ends the capture the
    # moment it takes the result, so model that rather than pretending the hook
    # ignores the releases.
    listener.start_capture()
    for vk in (0x5B, 0x11, 0x10):
        feed(listener, vk, hotkey.WM_KEYDOWN)
    feed(listener, 0x42, hotkey.WM_KEYDOWN)
    spec = listener.poll_capture()
    print(f"  win+ctrl+shift+b is recorded as {spec!r}", flush=True)
    ok = ok and spec == ("ok", "ctrl+shift+win+b")
    listener.stop_capture()
    for vk in (0x11, 0x10, 0x5B):
        feed(listener, vk, hotkey.WM_KEYUP)
    after = listener.poll_capture()
    print(f"  the releases after it add nothing: {after!r}", flush=True)
    ok = ok and after is None

    listener.start_capture()
    feed(listener, 0x42, hotkey.WM_KEYDOWN)  # B with no modifier held
    refused = listener.poll_capture()
    print(f"  a bare main key is refused: {refused!r}", flush=True)
    ok = ok and refused is not None and refused[0] == "invalid"

    listener.start_capture()
    feed(listener, 0x07, hotkey.WM_KEYDOWN)  # no name_for, cannot become a spec
    unnamed = listener.poll_capture()
    print(f"  an unnamed key is refused: {unnamed!r}", flush=True)
    ok = ok and unnamed is not None and unnamed[0] == "invalid"

    listener.start_capture()
    feed(listener, VK_ESCAPE, hotkey.WM_KEYDOWN)
    cancelled = listener.poll_capture()
    print(f"  escape cancels: {cancelled!r}", flush=True)
    ok = ok and cancelled == ("cancel", "")

    listener.stop_capture()
    print(f"  stop_capture turns capturing off: {not listener.is_capturing}",
          flush=True)
    return ok and not listener.is_capturing


def case_settings_load(work: Path, results: list[bool]) -> None:
    print("\ncase 4: settings.load falls back to the defaults", flush=True)
    original = settings.SETTINGS_FILE
    target = work / "settings.json"
    settings.SETTINGS_FILE = target
    try:
        def check(label: str, payload, expected: dict, expected_specs: list[str]) -> None:
            if payload is None:
                target.unlink(missing_ok=True)
            else:
                target.write_text(payload, encoding="utf-8")
            got = settings.load()
            specs = settings.hotkeys()
            ok = got == expected and specs == expected_specs
            print(f"  {label:34s} load={got!r:24s} hotkeys={specs!r:32s} {ok}",
                  flush=True)
            results.append(ok)

        check("missing file", None, {}, list(config.HOTKEYS))
        check("malformed json", "{not json", {}, list(config.HOTKEYS))
        check("a json array", '["win+ctrl+right"]', {}, list(config.HOTKEYS))
        check("a non-string element",
              '{"hotkeys": ["win+ctrl+right", 5]}', {"hotkeys": ["win+ctrl+right", 5]},
              list(config.HOTKEYS))
        check("an empty list", '{"hotkeys": []}', {"hotkeys": []},
              list(config.HOTKEYS))
        check("a json scalar", "17", {}, list(config.HOTKEYS))
        check("a valid list", '{"hotkeys": ["win+shift+f5"]}',
              {"hotkeys": ["win+shift+f5"]}, ["win+shift+f5"])
        results.append(settings.hotkeys() is not config.HOTKEYS)
        print(f"  the default list is copied, never shared: "
              f"{results[-1]}", flush=True)

        # Notepad and PowerShell save with a byte order mark, and plain utf-8
        # reading would keep it as a character and cost every setting at once.
        target.write_bytes(
            b"\xef\xbb\xbf" + '{"hotkeys": ["ctrl+alt+p"]}'.encode("utf-8")
        )
        got = settings.load()
        specs = settings.hotkeys()
        ok = got == {"hotkeys": ["ctrl+alt+p"]} and specs == ["ctrl+alt+p"]
        print(f"  a byte order mark costs nothing: load={got!r} hotkeys={specs!r} {ok}",
              flush=True)
        results.append(ok)
    finally:
        settings.SETTINGS_FILE = original


def case_settings_save(work: Path, results: list[bool]) -> None:
    print("\ncase 5: save then load, and no temp file left behind", flush=True)
    original = settings.SETTINGS_FILE
    target = work / "settings.json"
    temp = work / (target.name + settings.TEMP_SUFFIX)
    settings.SETTINGS_FILE = target
    try:
        target.unlink(missing_ok=True)
        temp.unlink(missing_ok=True)
        written = settings.save({"hotkeys": ["ctrl+alt+z"]})
        loaded = settings.load()
        specs = settings.hotkeys()
        print(f"  save returned {written}, load returned {loaded!r}", flush=True)
        ok = written and loaded == {"hotkeys": ["ctrl+alt+z"]}
        ok = ok and specs == ["ctrl+alt+z"]
        ok = ok and not temp.exists()
        print(f"  {target.name}{settings.TEMP_SUFFIX} left behind: {temp.exists()}",
              flush=True)
        print(f"  store_hotkeys keeps the other keys: "
              f"{settings.store_hotkeys(['win+f5']) and settings.load()}",
              flush=True)
        results.append(ok)
    finally:
        settings.SETTINGS_FILE = original


def case_flags(work: Path, results: list[bool]) -> None:
    print("\ncase 6: the switches read back and fall back to the defaults",
          flush=True)
    original = settings.SETTINGS_FILE
    target = work / "settings.json"
    settings.SETTINGS_FILE = target
    try:
        def read(payload: str | None, label: str, live: bool, clip: bool,
                 correct: bool, toggle: bool, log: bool, history: bool) -> bool:
            if payload is None:
                target.unlink(missing_ok=True)
            else:
                target.write_text(payload, encoding="utf-8")
            got_live = settings.live_typing()
            got_clip = settings.copy_to_clipboard()
            got_correct = settings.correct_words()
            got_toggle = settings.toggle_recording()
            got_log = settings.logging_enabled()
            got_history = settings.history_enabled()
            ok = (got_live == live and got_clip == clip and got_correct == correct
                  and got_toggle == toggle and got_log == log
                  and got_history == history)
            print(f"  {label:28s} live={got_live!s:5s} clip={got_clip!s:5s} "
                  f"correct={got_correct!s:5s} toggle={got_toggle!s:5s} "
                  f"log={got_log!s:5s} history={got_history!s:5s} {ok}",
                  flush=True)
            return ok

        defaults = (config.LIVE_TYPE_DEFAULT, config.CLIPBOARD_DEFAULT,
                    config.CORRECT_WORDS_DEFAULT, config.TOGGLE_DEFAULT,
                    config.LOG_WRITE_DEFAULT, config.HISTORY_WRITE_DEFAULT)
        ok = read(None, "missing file", *defaults)
        ok = ok and read(
            '{"live_typing": false, "copy_to_clipboard": true, '
            '"correct_words": false, "toggle_recording": true, '
            '"write_log": false, "write_history": false}', "all stored",
            False, True, False, True, False, False)
        ok = ok and read('{"live_typing": "yes"}', "a string instead of a bool",
                         *defaults)
        ok = ok and read('{"copy_to_clipboard": 1}', "a number instead of a bool",
                         *defaults)
        ok = ok and read('{"correct_words": null}', "null instead of a bool",
                         *defaults)
        ok = ok and read('{"toggle_recording": "on"}', "a string for the mode too",
                         *defaults)
        ok = ok and read('{"write_log": "yes"}', "a string for the log switch",
                         *defaults)
        ok = ok and read('{"write_history": 0}', "a number for the history",
                         *defaults)
        results.append(ok)

        target.unlink(missing_ok=True)
        stored = settings.store_live_typing(False)
        kept = settings.store_copy_to_clipboard(True)
        corrected = settings.store_correct_words(False)
        toggled = settings.store_toggle_recording(True)
        logged = settings.store_logging_enabled(False)
        kept_history = settings.store_history_enabled(False)
        print(f"  stored: live_typing={settings.live_typing()} "
              f"copy_to_clipboard={settings.copy_to_clipboard()} "
              f"correct_words={settings.correct_words()} "
              f"toggle_recording={settings.toggle_recording()} "
              f"write_log={settings.logging_enabled()} "
              f"write_history={settings.history_enabled()}", flush=True)
        ok = stored and kept and corrected and toggled and logged and kept_history
        ok = ok and settings.live_typing() is False
        ok = ok and settings.copy_to_clipboard() is True
        ok = ok and settings.correct_words() is False
        ok = ok and settings.toggle_recording() is True
        ok = ok and settings.logging_enabled() is False
        ok = ok and settings.history_enabled() is False
        # A switch must never disturb the hotkey list stored beside it.
        settings.store_hotkeys(["win+shift+f5"])
        settings.store_correct_words(True)
        print(f"  the hotkey list survives a switch write: {settings.hotkeys()}",
              flush=True)
        results.append(ok and settings.hotkeys() == ["win+shift+f5"])
    finally:
        settings.SETTINGS_FILE = original


def case_input_device(work: Path, results: list[bool]) -> None:
    """The recording device key: a name, or nothing at all.

    Case 6 covers the six switches. This one covers the tenth key, and it is the
    only key in the file that is allowed to hold null as a value rather than only
    when it is absent — "the system default" is a choice the user makes and it
    has to be told apart from a file that has never heard of the setting.
    """
    print("\ncase 12: the recording device is a name, or the system default",
          flush=True)
    original = settings.SETTINGS_FILE
    target = work / "settings.json"
    settings.SETTINGS_FILE = target
    try:
        def read(payload: str | None, label: str, wanted: str | None) -> bool:
            if payload is None:
                target.unlink(missing_ok=True)
            else:
                target.write_text(payload, encoding="utf-8")
            got = settings.input_device()
            ok = got == wanted
            print(f"  {label:34s} -> {got!r:28s} {ok}", flush=True)
            return ok

        name = "Conexant HD Audio capture (MME)"
        ok = read(None, "missing file", None)
        ok = ok and read("{}", "a file without the key", None)
        ok = ok and read('{"input_device": null}', "explicitly the default", None)
        ok = ok and read(f'{{"input_device": "{name}"}}', "a stored name", name)
        # Surrounding space is the one repair worth making: a name pasted out of
        # the Windows dialog brings its own padding, and it would then match no
        # device at all.
        ok = ok and read(f'{{"input_device": "  {name}  "}}', "padded, as pasted",
                         name)
        ok = ok and read('{"input_device": 6}', "a number, not a name", None)
        ok = ok and read('{"input_device": ""}', "an empty string", None)
        ok = ok and read('{"input_device": ["a"]}', "a list", None)
        results.append(ok)

        target.unlink(missing_ok=True)
        stored = settings.store_input_device(name)
        print(f"  stored a name: {settings.input_device()!r}", flush=True)
        ok = stored and settings.input_device() == name
        cleared = settings.store_input_device(None)
        print(f"  stored the default: {settings.input_device()!r} "
              f"and the file says {settings.load().get('input_device')!r}",
              flush=True)
        # The key stays in the file as null rather than being removed: a null is
        # an answer, and a file written by a later version is read the same way.
        ok = ok and cleared and settings.input_device() is None
        ok = ok and "input_device" in settings.load()
        refused = settings.store_input_device(7)
        print(f"  a number is refused: {not refused} "
              f"and the file still says {settings.input_device()!r}", flush=True)
        results.append(ok and refused is False)
    finally:
        settings.SETTINGS_FILE = original


def case_log_verbose(work: Path, results: list[bool]) -> None:
    """The log switch, proved on the handler rather than on the switch.

    A switch that reads back correctly and changes nothing is the failure this
    case exists for, so it watches the file: what lands in it with the switch on,
    what does not with it off, and what a handler this module did not attach
    keeps doing either way.
    """
    print("\ncase 11: the log switch re-levels the file and nothing else",
          flush=True)
    from logging.handlers import RotatingFileHandler

    ok = config.file_level(True) == logging.INFO
    ok = ok and config.file_level(False) == logging.WARNING
    print(f"  file_level(True)={config.file_level(True)} "
          f"file_level(False)={config.file_level(False)} {ok}", flush=True)

    target = work / "verbose.log"
    root = logging.getLogger()
    kept = root.level
    stream = logging.StreamHandler()
    stream.setLevel(logging.INFO)
    file_handler = RotatingFileHandler(
        target, maxBytes=config.LOG_MAX_BYTES, backupCount=1, encoding="utf-8"
    )
    file_handler.setLevel(config.file_level(True))
    root.addHandler(stream)
    root.addHandler(file_handler)
    root.setLevel(logging.INFO)
    try:
        def lines() -> int:
            """How many lines the file holds, flushed and counted."""
            for handler in root.handlers:
                handler.flush()
            if not target.exists():
                return 0
            return len(target.read_text(encoding="utf-8").splitlines())

        marker = logging.getLogger("winvosk.probe")
        marker.info("with the switch on")
        wrote_info = lines()
        print(f"  INFO reached the file with the switch on: "
              f"{wrote_info > 0} ({wrote_info} line(s))", flush=True)
        ok = ok and wrote_info > 0

        changed = config.set_log_verbose(False)
        marker.info("dropped while the switch is off")
        marker.warning("kept while the switch is off")
        wrote = lines()
        body = target.read_text(encoding="utf-8")
        print(f"  set_log_verbose(False)={changed}, level={logging.getLevelName(file_handler.level)},"
              f" INFO dropped={'dropped while' not in body}, "
              f"WARNING kept={'kept while' in body} {wrote}", flush=True)
        ok = ok and changed and file_handler.level == logging.WARNING
        ok = ok and "dropped while" not in body and "kept while" in body

        # The root level and another handler are none of this switch's business:
        # the console flags and this probe keep logging at INFO either way.
        untouched = root.level == logging.INFO and stream.level == logging.INFO
        print(f"  root level {logging.getLevelName(root.level)}, "
              f"another handler {logging.getLevelName(stream.level)} "
              f"{untouched}", flush=True)
        ok = ok and untouched

        back = config.set_log_verbose(True)
        marker.info("written again after switching back on")
        body = target.read_text(encoding="utf-8")
        print(f"  set_log_verbose(True)={back}, level={logging.getLevelName(file_handler.level)},"
              f" INFO back={'written again' in body}", flush=True)
        ok = ok and back and file_handler.level == logging.INFO
        ok = ok and "written again" in body
    finally:
        root.removeHandler(file_handler)
        root.removeHandler(stream)
        file_handler.close()
        root.setLevel(kept)
    results.append(ok)


def case_toggle_mode(results: list[bool]) -> None:
    print("\ncase 8: the recording mode, and what it does to the hook", flush=True)
    import run

    original = settings.SETTINGS_FILE
    work = Path(tempfile.mkdtemp(prefix="winvosk_toggle_probe_"))
    target = work / "settings.json"
    settings.SETTINGS_FILE = target
    try:
        def build(mode: bool, label: str) -> bool:
            """Install a hook and report whether it was built push to talk.

            `start` is the only thing stubbed, because a real hook needs a
            desktop this session does not have; what is under test is which
            callbacks the listener was handed.
            """
            target.unlink(missing_ok=True)
            settings.store_toggle_recording(mode)
            app = run.App.__new__(run.App)
            app._hotkey = None
            app._commands = queue.Queue()
            app._hotkeys = tuple(config.HOTKEYS)
            app._recording = False
            made: dict[str, object] = {}
            real_start = hotkey.HotkeyListener.start

            def fake_start(self):
                made["listener"] = self
                return True

            hotkey.HotkeyListener.start = fake_start
            try:
                app._install_hotkey(tuple(config.HOTKEYS))
            finally:
                hotkey.HotkeyListener.start = real_start
            built = made.get("listener")
            ok = built is not None and built.is_push_to_talk is not mode
            print(f"  {label:28s} toggle={mode!s:5s} "
                  f"push_to_talk={built.is_push_to_talk!s:5s} {ok}", flush=True)
            return ok

        ok = build(False, "push to talk (the default)")
        ok = ok and build(True, "toggle")

        # One press has to mean "start", then "stop", with no release in between.
        # The decision belongs to the queue drainer, so it is driven through
        # `_handle_command` rather than through the callback the hook would call.
        def commands_for(mode: bool, presses: int) -> list[str]:
            target.unlink(missing_ok=True)
            settings.store_toggle_recording(mode)
            app = run.App.__new__(run.App)
            app._commands = queue.Queue()
            app._recording = False
            # `_hotkey_pressed` borrows the keyboard layout before it puts the
            # start on the queue, so the guard is part of what a press has to
            # have. Disarmed here, which is the empty default: a temporary
            # settings file names no layout, so nothing is ever touched.
            app._layout = run.keystrokes.LayoutGuard(lambda: "")
            seen: list[str] = []
            for _ in range(presses):
                app._handle_command("hotkey_press")
                # `_hotkey_pressed` puts its decision on the same queue, so
                # drain what it produced and let the next press see the state
                # that decision implies. That is what the real pump does.
                while not app._commands.empty():
                    queued = app._commands.get_nowait()
                    seen.append(queued)
                    app._recording = queued == "press"
            return seen

        first = commands_for(True, 1)
        second = commands_for(True, 2)
        third = commands_for(False, 1)
        print(f"  toggle, one press   -> {first}", flush=True)
        print(f"  toggle, two presses -> {second}", flush=True)
        print(f"  push to talk        -> {third}", flush=True)
        ok = ok and first == ["press"]
        ok = ok and second == ["press", "stop_recording"]
        ok = ok and third == ["press"]
        results.append(ok)
    finally:
        settings.SETTINGS_FILE = original
        shutil.rmtree(work, ignore_errors=True)


def case_blocking(results: list[bool]) -> None:
    print("\ncase 9: which keys the hook swallows, and which it passes on",
          flush=True)
    events: list[str] = []
    listener = hotkey.HotkeyListener(
        ("ctrl+menu",),
        on_press=lambda: events.append("press"),
        on_release=lambda: events.append("release"),
    )

    def feed(vk: int, message: int) -> int:
        """One key event through the real hook callback, as Windows calls it.

        The callback is what decides whether the event is swallowed, and it only
        reads `vkCode` out of the struct, so a fabricated one is enough to drive
        it with no keyboard and no desktop. The address goes in as a plain
        integer, which is what `CallNextHookEx` and `ctypes.cast` both take on
        the pass-through path.
        """
        data = hotkey._KeyboardHookStruct()
        data.vkCode = vk
        return listener._on_event(
            hotkey.HC_ACTION, message, ctypes.addressof(data)
        )

    VK_LCTRL, VK_MENU, VK_X = 0xA2, 0x5D, 0x58
    ok = True

    # The combination, and the auto repeat Windows sends while it is held. The
    # repeat is the whole point: the app never saw the first keydown, so a repeat
    # that gets through opens the context menu even though the press was eaten.
    events.clear()
    steps = [
        ("ctrl down", feed(VK_LCTRL, hotkey.WM_KEYDOWN), 0, "modifier reaches"),
        ("menu down", feed(VK_MENU, hotkey.WM_KEYDOWN), 1, "eaten, press"),
        ("menu repeat", feed(VK_MENU, hotkey.WM_KEYDOWN), 1, "eaten too"),
        ("menu repeat", feed(VK_MENU, hotkey.WM_KEYDOWN), 1, "and again"),
        ("menu up", feed(VK_MENU, hotkey.WM_KEYUP), 1, "eaten, release"),
        ("ctrl up", feed(VK_LCTRL, hotkey.WM_KEYUP), 0, "modifier reaches"),
    ]
    for label, got, want, why in steps:
        good = got == want
        ok = ok and good
        print(f"  {label:12s} -> {got} want {want} ({why}) {good}", flush=True)
    time.sleep(0.2)
    print(f"  callbacks: {events}", flush=True)
    ok = ok and events == ["press", "release"]

    # Held down, the combination still matches, so a naive "swallow on any match"
    # fix would eat every other key too. Only the blocked key itself is swallowed.
    events.clear()
    held = [
        ("ctrl down", feed(VK_LCTRL, hotkey.WM_KEYDOWN), 0),
        ("menu down", feed(VK_MENU, hotkey.WM_KEYDOWN), 1),
        ("x down", feed(VK_X, hotkey.WM_KEYDOWN), 0),
        ("x up", feed(VK_X, hotkey.WM_KEYUP), 0),
        ("y down", feed(0x59, hotkey.WM_KEYDOWN), 0),
        ("y up", feed(0x59, hotkey.WM_KEYUP), 0),
        ("menu up", feed(VK_MENU, hotkey.WM_KEYUP), 1),
        ("ctrl up", feed(VK_LCTRL, hotkey.WM_KEYUP), 0),
    ]
    for label, got, want in held:
        good = got == want
        ok = ok and good
        print(f"  held, {label:12s} -> {got} want {want} {good}", flush=True)

    # With no modifier held the Menu key is nobody's combination, so it has to
    # keep working as the context menu key it is.
    alone = [
        ("menu down", feed(VK_MENU, hotkey.WM_KEYDOWN), 0),
        ("menu up", feed(VK_MENU, hotkey.WM_KEYUP), 0),
    ]
    for label, got, want in alone:
        good = got == want
        ok = ok and good
        print(f"  alone, {label:10s} -> {got} want {want} {good}", flush=True)

    listener.stop()
    results.append(ok)


def case_partial_hotkeys(work: Path, results: list[bool]) -> None:
    print("\ncase 10: one bad combination does not cost the good ones", flush=True)
    original = settings.SETTINGS_FILE
    target = work / "hotkeys.json"
    settings.SETTINGS_FILE = target
    try:
        def read(payload: str, label: str, want: list[str],
                 want_rejected: list[str]) -> bool:
            target.write_text(payload, encoding="utf-8")
            got = settings.hotkeys()
            rejected = [spec for spec, _ in settings.rejected_hotkeys()]
            ok = got == want and rejected == want_rejected
            print(f"  {label:34s} hotkeys={got} rejected={rejected} {ok}",
                  flush=True)
            return ok

        ok = read('{"hotkeys": ["ctrl+apps", "ctrl+menu"]}', "apps for the Menu key",
                  ["ctrl+apps", "ctrl+menu"], [])
        ok = ok and read('{"hotkeys": ["win+f5", "ctrl+нет", "alt+win"]}',
                        "a typo in the middle", ["win+f5", "alt+win"], ["ctrl+нет"])
        ok = ok and read('{"hotkeys": ["shift"]}', "one unusable entry alone",
                         list(config.HOTKEYS), ["shift"])
        ok = ok and read('{"hotkeys": ["no+such", "also+bad"]}',
                        "nothing usable left", list(config.HOTKEYS),
                        ["no+such", "also+bad"])
        ok = ok and read('{"hotkeys": ["ctrl+context_menu"]}', "context_menu alias",
                         ["ctrl+context_menu"], [])
        # The name a recorded combination gets must stay stable, or a spec the
        # capture wrote would change meaning the next time it was read.
        alias = hotkey.name_for(0x5D)
        print(f"  name_for(0x5D) is still {alias!r} for every alias", flush=True)
        results.append(ok and alias == "menu")
    finally:
        settings.SETTINGS_FILE = original


def case_capture_is_released(results: list[bool]) -> None:
    print("\ncase 7: leaving the capture hands the keyboard back", flush=True)
    import run  # imports Tk, pystray and vosk as modules, but builds no window

    for label, refuse_write in (("after escape", False), ("after a refused write", True)):
        listener = fresh_listener()
        app = run.App.__new__(run.App)
        app._hotkey = listener
        app._hotkeys = tuple(config.HOTKEYS)
        app._panel = StubPanel()
        app._tray = StubTray()
        app._recording = False
        saved = settings.store_hotkeys
        if refuse_write:
            settings.store_hotkeys = lambda specs: False
        try:
            listener.start_capture()
            if refuse_write:
                for vk in (0x11, 0x5B):
                    feed(listener, vk, hotkey.WM_KEYDOWN)
                feed(listener, 0x42, hotkey.WM_KEYDOWN)
            else:
                feed(listener, VK_ESCAPE, hotkey.WM_KEYDOWN)
            app._poll_capture()
            released = not listener.is_capturing
            print(f"  {label:22s} capturing={listener.is_capturing} "
                  f"panel={app._panel.calls} tray={app._tray.calls}", flush=True)
            results.append(released)
        finally:
            settings.store_hotkeys = saved

    # A refusal is the one outcome that re-arms on purpose, so `capturing` stays
    # True here. What still has to hold is that the keyboard is the capture's to
    # swallow and the reason was published, and that only the hook can end it.
    listener = fresh_listener()
    app = run.App.__new__(run.App)
    app._hotkey = listener
    app._hotkeys = tuple(config.HOTKEYS)
    app._panel = StubPanel()
    app._tray = StubTray()
    app._recording = False
    listener.start_capture()
    for vk in (0x11, 0x10):
        feed(listener, vk, hotkey.WM_KEYDOWN)
    for vk in (0x11, 0x10):
        feed(listener, vk, hotkey.WM_KEYUP)
    app._poll_capture()
    shown = any("hint" in call for call in app._panel.calls)
    print(f"  {'after modifiers only':22s} capturing={listener.is_capturing} "
          f"(re-armed on purpose, reason shown: {shown}) "
          f"panel={app._panel.calls}", flush=True)
    results.append(listener.is_capturing and shown)
    listener.stop_capture()
    results.append(not listener.is_capturing)


def main() -> None:
    results: list[bool] = []
    results.append(case_names())
    results.append(case_round_trip())
    results.append(case_capture_rules())
    work = Path(tempfile.mkdtemp(prefix="winvosk_settings_probe_"))
    try:
        case_settings_load(work, results)
        case_settings_save(work, results)
        case_flags(work, results)
        case_input_device(work, results)
        case_log_verbose(work, results)
        case_partial_hotkeys(work, results)
    finally:
        settings.SETTINGS_FILE = config.BASE_DIR / "settings.json"
        shutil.rmtree(work, ignore_errors=True)
    case_toggle_mode(results)
    case_capture_is_released(results)
    case_blocking(results)
    passed = all(results)
    print(f"\n{sum(results)}/{len(results)} check group(s) passed", flush=True)
    print(f"VERDICT: {'PASS' if passed else 'FAIL'}", flush=True)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()