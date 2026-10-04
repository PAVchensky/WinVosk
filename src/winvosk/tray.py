"""System tray icon and its menu."""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable

import pystray
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import config, text, theme

log = logging.getLogger(__name__)

# How long to wait for `Shell_NotifyIcon` before calling the tray dead, and how
# often to look. The call itself lands in a thread of pystray's own, on the far
# side of a window class registration and two hidden windows, so it is not
# immediate: measured on this machine, a second. Five covers a loaded machine
# without turning a slow tray into a hang.
TRAY_READY_TIMEOUT = 5.0
TRAY_POLL_INTERVAL = 0.05

# What to do when that wait runs out. The first `Shell_NotifyIcon` is refused
# while the shell is still coming up, and pystray only re-adds on
# `WM_TASKBARCREATED` — that is an Explorer that restarted, not a shell that was
# never ready, so nothing upstream retries the first refusal. A dead tray is the
# one failure that leaves the panel unreachable, because the tray is the only
# way in. Measured on the machine this was found on: two starts in a row were
# refused the icon and a third took it seconds later, which is a shell being
# slow and not a shell that refuses.
#
# The retry runs on a thread of its own rather than on the startup path. Waiting
# a minute for the icon with the panel's own thread blocked would be a worse
# failure than a missing icon, and the hotkey works either way.
TRAY_RETRY_INTERVAL = 0.5
TRAY_RETRY_SECONDS = 60.0

# Drawn four times the requested size and folded down with BOX, the same rule the
# chip's plate and every card in the panel follow: an average of each block is
# the only filter that cannot overshoot, and a glyph on a saturated field is the
# worst case for a filter that does.
_SUPERSAMPLE = 4


def make_icon(
    recording: bool = False, size: int = 64,
    palette: theme.Palette | None = None,
) -> Image.Image:
    """Draw a microphone glyph so no binary asset has to be shipped.

    A rounded plate in the theme's accent, or in its danger while a recording
    runs, with a soft top-to-bottom gradient and a highlight along the top edge:
    at 16 px in the notification area a flat fill reads as a coloured square, and
    the gradient is what makes it read as a lit surface instead. Idle and
    recording differ in colour alone, so the shape stays a microphone and the
    state is carried by hue rather than by a second drawing.
    """
    colours = theme.palette() if palette is None else palette
    scale = size / 64
    step = _SUPERSAMPLE
    big = max(1, int(round(size * step)))
    plate = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(plate)

    top = theme.rgb(
        colours.tray_active_bg if recording else colours.tray_idle_bg
    )
    bottom = tuple(
        max(0, min(255, channel - 38)) for channel in top
    )
    body = Image.new("RGB", (big, big), bottom)
    shade = ImageDraw.Draw(body)
    for row in range(big):
        ratio = row / max(1, big - 1)
        shade.line(
            (0, row, big, row),
            fill=tuple(
                round(top[channel] + (bottom[channel] - top[channel]) * ratio)
                for channel in range(3)
            ),
        )
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, big - 1, big - 1), radius=int(14 * scale * step), fill=255
    )
    plate.paste(body, (0, 0), mask)

    # A highlight along the top edge, faded out by the middle: what makes a
    # rounded plate look like a surface with a light on it rather than a shape.
    gloss = Image.new("L", (big, big), 0)
    ImageDraw.Draw(gloss).ellipse(
        (-big // 3, -int(big * 0.62), big + big // 3, int(big * 0.52)), fill=64
    )
    gloss = gloss.filter(ImageFilter.GaussianBlur(big * 0.05))
    plate.paste(
        Image.new("RGBA", (big, big), (255, 255, 255, 255)), (0, 0),
        ImageChops.multiply(gloss, mask),
    )

    foreground = theme.rgb(
        colours.tray_active_fg if recording else colours.tray_idle_fg
    )
    _microphone(draw, big, scale, step, foreground)
    return plate.resize((size, size), Image.Resampling.BOX)


def _microphone(draw: ImageDraw.ImageDraw, size: int, scale: float, step: int,
                colour: tuple[int, int, int]) -> None:
    """The glyph: a capsule, the arc under it, the stem and the base."""
    at = lambda v: int(round(v * scale * step))  # noqa: E731 - a local unit helper
    width = max(1, int(round(3 * scale * step)))
    draw.rounded_rectangle(
        (at(26), at(12), at(38), at(34)), radius=at(6), fill=colour
    )
    draw.arc(
        (at(20), at(26), at(44), at(50)), start=0, end=180, fill=colour,
        width=width,
    )
    draw.line((at(32), at(50), at(32), at(44)), fill=colour, width=width)
    draw.line((at(24), at(54), at(40), at(54)), fill=colour, width=width)


class TrayIcon:
    def __init__(
        self,
        commands: queue.Queue,
        is_panel_visible: Callable[[], bool],
        is_recording: Callable[[], bool] = lambda: False,
        hotkey_label: str | None = None,
        is_toggle: Callable[[], bool] = lambda: False,
        palette: theme.Palette | None = None,
    ) -> None:
        self._commands = commands
        self._is_panel_visible = is_panel_visible
        self._is_recording = is_recording
        self._is_toggle = is_toggle
        self._hotkey_label = config.hotkey_label() if hotkey_label is None else hotkey_label
        self._palette = palette
        self._stopped = False
        self._recording_image = make_icon(True, palette=palette)
        self._idle_image = make_icon(False, palette=palette)
        self._icon = pystray.Icon(
            "winvosk", self._idle_image, config.APP_NAME, menu=self._menu()
        )

    def set_theme(self, name: str) -> None:
        """Redraw both icons in another theme, and put up the idle one.

        The tray icon follows the panel's theme rather than keeping its own, so
        a dark panel does not sit next to a light-blue microphone. Idle and
        recording are both drawn up front, because the notification area keeps a
        reference to the bitmap it was given and swapping one in later means
        asking the shell to redraw on every state change.
        """
        self._palette = theme.palette(name)
        self._recording_image = make_icon(True, palette=self._palette)
        self._idle_image = make_icon(False, palette=self._palette)
        try:
            self._icon.icon = self._recording_image if self._is_recording() else self._idle_image
            self._icon.update_menu()
        except Exception:
            log.exception("could not refresh the tray icon")

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

        A missing icon is a warning, not a fatal error, and not the end of it
        either: `_keep_asking` keeps watching in the background, because the
        alternative is an app with no way into its own panel. pystray answers
        `WM_TASKBARCREATED` for an Explorer that restarts under a live icon; this
        covers a setup thread that simply has not got there yet.
        """
        self._icon.run_detached()
        if self._await_visible(TRAY_READY_TIMEOUT):
            log.info("tray icon started")
            return True
        log.warning(
            "tray icon did not appear within %.1fs: the panel cannot be reached "
            "from the tray yet. Still watching for it in the background for "
            "%.0fs.", TRAY_READY_TIMEOUT, TRAY_RETRY_SECONDS,
        )
        threading.Thread(
            target=self._keep_asking, name="tray-watch", daemon=True
        ).start()
        return False

    def _await_visible(self, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.visible:
                return True
            time.sleep(TRAY_POLL_INTERVAL)
        return False

    def _keep_asking(self) -> None:
        """Watch for the icon for as long as it takes, on a thread of its own.

        It only watches. Asking for it again — `visible = False` then `True`,
        which is the only way to make pystray issue a second `NIM_ADD` — would be
        a worse answer than this one, because pystray sets `visible` from its own
        side of the call and never learns whether the shell took the icon. A
        forced re-add would therefore report "the icon appeared" on the first
        attempt whether or not the notification area has it, which is the one
        thing this log line exists to say. So the answer stays the only honest
        one available from inside the process, and it is simply waited for.
        """
        deadline = time.monotonic() + TRAY_RETRY_SECONDS
        while not self._stopped and time.monotonic() < deadline:
            time.sleep(TRAY_RETRY_INTERVAL)
            if self.visible:
                log.info("tray icon appeared late, after the first refusal")
                return
        if not self._stopped:
            log.error(
                "the tray icon never appeared in %.0fs, so the panel cannot be "
                "reached from the tray. Start the app again once Explorer has "
                "settled, or run it from a shortcut rather than straight out of "
                "an archive.", TRAY_RETRY_SECONDS,
            )

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
        self._stopped = True
        try:
            self._icon.stop()
        except Exception:
            log.exception("could not stop the tray icon")
