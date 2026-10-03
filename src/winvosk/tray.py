"""System tray icon and its menu."""

from __future__ import annotations

import logging
import queue
import time
from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw

from . import config, text

log = logging.getLogger(__name__)

_IDLE_BG = (52, 58, 64, 255)
_IDLE_FG = (228, 232, 236, 255)
_ACTIVE_BG = (176, 42, 48, 255)
_ACTIVE_FG = (255, 236, 236, 255)

# How long to wait for `Shell_NotifyIcon` before calling the tray dead, and how
# often to look. The call itself lands in a thread of pystray's own, on the far
# side of a window class registration and two hidden windows, so it is not
# immediate: measured on this machine, a second. Five covers a loaded machine
# without turning a slow tray into a hang.
TRAY_READY_TIMEOUT = 5.0
TRAY_POLL_INTERVAL = 0.05


def make_icon(recording: bool = False, size: int = 64) -> Image.Image:
    """Draw a microphone glyph so no binary asset has to be shipped."""
    background = _ACTIVE_BG if recording else _IDLE_BG
    foreground = _ACTIVE_FG if recording else _IDLE_FG
    scale = size / 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    box = (int(2 * scale), int(2 * scale), int(62 * scale), int(62 * scale))
    draw.rounded_rectangle(box, radius=int(14 * scale), fill=background)
    draw.rounded_rectangle(
        (int(26 * scale), int(12 * scale), int(38 * scale), int(34 * scale)),
        radius=int(6 * scale),
        fill=foreground,
    )
    draw.arc(
        (int(20 * scale), int(26 * scale), int(44 * scale), int(50 * scale)),
        start=0,
        end=180,
        fill=foreground,
        width=max(1, int(3 * scale)),
    )
    width = max(1, int(3 * scale))
    draw.line(
        (int(32 * scale), int(50 * scale), int(32 * scale), int(44 * scale)),
        fill=foreground,
        width=width,
    )
    draw.line(
        (int(24 * scale), int(54 * scale), int(40 * scale), int(54 * scale)),
        fill=foreground,
        width=width,
    )
    return image


class TrayIcon:
    def __init__(
        self,
        commands: queue.Queue,
        is_panel_visible: Callable[[], bool],
        is_recording: Callable[[], bool] = lambda: False,
        hotkey_label: str | None = None,
        is_toggle: Callable[[], bool] = lambda: False,
    ) -> None:
        self._commands = commands
        self._is_panel_visible = is_panel_visible
        self._is_recording = is_recording
        self._is_toggle = is_toggle
        self._hotkey_label = config.hotkey_label() if hotkey_label is None else hotkey_label
        self._icon = pystray.Icon(
            "winvosk", make_icon(False), config.APP_NAME, menu=self._menu()
        )
        self._recording_image = make_icon(True)
        self._idle_image = make_icon(False)

    def _menu(self) -> pystray.Menu:
        # Every label is a callable, so update_menu() repaints the whole menu in
        # the current language; `refresh()` is called when that language changes.
        return pystray.Menu(
            # A callable, so update_menu() repaints the label on every change.
            # Push to talk and toggle are told apart here rather than by two
            # items: the header is a hint, not a control.
            pystray.MenuItem(
                lambda item: text.t(
                    "tray_toggle" if self._is_toggle() else "tray_hold",
                    label=self._hotkey_label,
                ),
                None,
                enabled=False,
            ),
            pystray.MenuItem(
                lambda item: text.t("tray_stop"),
                lambda icon, item: self._commands.put("stop_recording"),
                enabled=lambda item: self._is_recording(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: text.t("tray_show"),
                lambda icon, item: self._commands.put("show_panel"),
                default=True,
            ),
            pystray.MenuItem(
                lambda item: text.t("tray_hide"),
                lambda icon, item: self._commands.put("hide_panel"),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: text.t("tray_copy"),
                lambda icon, item: self._commands.put("copy"),
            ),
            pystray.MenuItem(
                lambda item: text.t("tray_clear"),
                lambda icon, item: self._commands.put("clear"),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: text.t("tray_quit"),
                lambda icon, item: self._commands.put("quit"),
            ),
        )

    def run(self) -> bool:
        """Put the icon up, and say whether it actually arrived.

        `run_detached` returns as soon as it has started a thread, so logging
        straight after it says nothing: `Shell_NotifyIcon` still has to run, and
        pystray reports a refusal to a logger that has no handler and, in a
        windowless bundle, no stderr to fall back on. A dead tray is the worst
        failure this app has — the panel lives in the tray, so there would be no
        way in at all — which is why it is waited for and logged rather than
        assumed.

        A missing icon is a warning, not a fatal error. pystray answers
        `WM_TASKBARCREATED`, so an icon lost to an Explorer restart comes back on
        its own, and killing the app over it would turn a transient into an
        outage.
        """
        self._icon.run_detached()
        deadline = time.monotonic() + TRAY_READY_TIMEOUT
        while time.monotonic() < deadline:
            if self.visible:
                log.info("tray icon started")
                return True
            time.sleep(TRAY_POLL_INTERVAL)
        log.warning(
            "tray icon did not appear within %.1fs: Shell_NotifyIcon never "
            "accepted it, so the panel cannot be reached from the tray",
            TRAY_READY_TIMEOUT,
        )
        return False

    @property
    def visible(self) -> bool:
        """Whether the notification area holds the icon right now.

        `pystray.Icon.visible` is set once its own setup thread has asked the
        shell to add the icon, so this is the only honest answer available from
        inside the process. It is also what a build check can assert on.
        """
        return bool(self._icon.visible)

    def set_recording(self, recording: bool) -> None:
        try:
            self._icon.icon = self._recording_image if recording else self._idle_image
            self._icon.update_menu()
        except Exception:
            log.exception("could not refresh the tray icon")

    def set_hotkey(self, label: str) -> None:
        """Repaint the disabled header with the combination now in effect."""
        self._hotkey_label = label
        self.refresh()

    def refresh(self) -> None:
        """Repaint every label, after a change of language or of state."""
        try:
            self._icon.update_menu()
        except Exception:
            log.exception("could not refresh the tray menu")

    def notify(self, message: str, title: str = config.APP_NAME) -> None:
        try:
            self._icon.notify(message, title)
        except Exception:
            log.debug("tray notification unavailable", exc_info=True)

    def stop(self) -> None:
        try:
            self._icon.stop()
        except Exception:
            log.exception("could not stop the tray icon")
