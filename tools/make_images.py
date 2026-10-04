"""Regenerate every image the README shows.

Three kinds, and each one is made from the product rather than drawn from memory:
the panel shots are the real Tk window captured with `PrintWindow`, the chip
animation is the real chip — its plate, its bar geometry and its shaping
constants come from `winvosk.overlay` — and the banner is the product's own
palette with its own type.

Nothing here runs on the application's run-time path; this is a maintenance
tool, like `build_exe.py`. Run it from the project root:

    .\\.venv\\Scripts\\python.exe .\\tools\\make_images.py

The panel shots need Tk, which needs a Windows session with a window station —
the same one the app itself needs. `PrintWindow` renders the window without
needing it visible on a screen, so a capture over a remote or a locked desktop
still works. The chip animation is pure Pillow and runs anywhere.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import math
import queue
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image, ImageDraw, ImageFont

from winvosk import config, overlay, panel as panel_mod, text, theme

OUT = ROOT / "docs" / "img"
FONTS = Path(r"C:\Windows\Fonts")

# The chip's colours, read straight off the module so a change in the app reaches
# the images without a second edit here. The chip has fixed colours of its own and
# does not follow the theme; the banner below does, and PALETTE is where it gets
# them.
THEME = "light"
PALETTE = theme.palette(THEME)
BAR_LOW = overlay._rgb(overlay._BAR_LOW)
BAR_MID = overlay._rgb(overlay._BAR_MID)
BAR_HIGH = overlay._rgb(overlay._BAR_HIGH)
CLOCK = overlay._rgb(overlay._CLOCK)

PW_RENDERFULLCONTENT = 0x00000002


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [("bmiHeader", _BitmapInfoHeader), ("bmiColors", wt.DWORD * 3)]


def capture(hwnd: int) -> Image.Image:
    """One window as a Pillow image, rendered by Windows rather than scraped.

    Two ways this can quietly ruin a good README image, both refused here rather
    than caught afterwards. The window can come back flat, when it was never
    painted — caught by the colour count below. And it can come back the right
    colours at the wrong size: measured on a loaded machine, a window that had not
    finished being mapped reported a 160x28 rect and produced a 1 kB PNG of a
    title bar, which passed the colour check and overwrote a good screenshot. So
    the area has to be plausible too, not merely non-zero.
    """
    rect = wt.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise RuntimeError(f"window {hwnd} has no area")
    if width < 400 or height < 300:
        raise RuntimeError(
            f"window {hwnd} reports {width}x{height}, which is not a panel: it "
            f"has not finished being mapped, so this is not a screenshot"
        )
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    window_dc = user32.GetWindowDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not user32.PrintWindow(hwnd, memory_dc, PW_RENDERFULLCONTENT):
            raise RuntimeError(f"PrintWindow failed for {hwnd}")
        info = _BitmapInfo()
        info.bmiHeader.biSize = ctypes.sizeof(_BitmapInfoHeader)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height          # top-down rows
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0
        buffer = ctypes.create_string_buffer(width * height * 4)
        if not gdi32.GetDIBits(memory_dc, bitmap, 0, height, buffer,
                               ctypes.byref(info), 0):
            raise RuntimeError("GetDIBits failed")
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)
    image = Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1)
    # `PrintWindow` returns TRUE and hands back an unpainted bitmap when the
    # window is not composited, which is what a session with no interactive
    # desktop looks like from in here. A flat image is not a screenshot, and
    # saving one over a good one destroys it while the tool reports success, so
    # refuse it here - before any save, not after.
    colours = image.getcolors(maxcolors=1 << 16)
    if colours is not None and len(colours) <= 2:
        raise RuntimeError(
            f"window {hwnd} came back as {len(colours)} flat colour(s): it was "
            f"never painted, so this is not a screenshot"
        )
    return image


def _toplevel(widget) -> int:
    """The HWND of a Tk widget's window, not of the child Tk draws into."""
    child = widget.winfo_id()
    return ctypes.windll.user32.GetParent(child) or child


def _settle(widget) -> None:
    """Let the window finish becoming what it is going to be, then photograph it.

    Several passes, not one. `Panel` writes the window's DWM attributes — rounded
    corners, no system border, the light or dark title bar — from its own `<Map>`
    handler, and DWM repaints the frame a frame later than Tk processes the event.
    One `update()` photographs the default caption instead: measured, the caption
    comes back as a flat (63, 63, 63) whatever theme the panel is in, and only
    after a few passes does it come back as (243, 243, 243) on light and
    (32, 32, 32) on dark. The same applies to the client area, which Tk fills over
    several passes while a card is painting itself.
    """
    for _ in range(6):
        widget.update_idletasks()
        widget.update()
        time.sleep(0.05)


def panel_shots() -> list[Path]:
    """The real panel: dictation, settings and history, in both languages."""
    written = []
    text.set_language("ru")
    panel = panel_mod.Panel(
        queue.Queue(), lambda: 0.3, correct_words=True,
        # Two of the three kinds of device, so the shot shows the card as a user
        # with hardware on this machine sees it: the system default marked, and a
        # second one to choose. Built without them it would say there are no
        # recording devices, which is a fact about this machine and not about the
        # panel.
        devices=(("Digital Audio (S/PDIF)", True),
                 ("Conexant HD Audio capture", False)),
    )
    panel.set_hotkey("Win+Ctrl+Right  /  Alt+Win")
    panel.set_text("перенести файлы в дропбокс и отправить отчёт", "")
    panel.set_status(text.t("status_ready"))
    # Mapped, deliberately: `PrintWindow` hands back an unpainted bitmap for a
    # window that was never shown, which `capture` then refuses — so the panel
    # has to be up for the shot, and the capture is of the window itself either
    # way. The app never does this on its own; `Panel` is built unmapped.
    panel.present()
    _settle(panel._root)
    hwnd = _toplevel(panel._root)

    shot = capture(hwnd).convert("RGB")
    shot.save(OUT / "panel-ru.png")
    written.append(OUT / "panel-ru.png")

    panel._notebook.select(1)
    _settle(panel._root)
    shot = capture(hwnd).convert("RGB")
    shot.save(OUT / "panel-settings.png")
    written.append(OUT / "panel-settings.png")

    # The history tab, which is the third page and the only one the two shots
    # above do not show. Photographed in Russian like the settings tab, because
    # that is the language both guides lead with.
    panel._notebook.select(panel_mod.HISTORY_TAB)
    _settle(panel._root)
    shot = capture(hwnd).convert("RGB")
    shot.save(OUT / "panel-history.png")
    written.append(OUT / "panel-history.png")

    # The language switch repaints in place, so the same window is photographed
    # again rather than a second one built: that is the invariant, and the shot
    # is the evidence. `set_language` is what does it — changing the language
    # module alone would leave the widgets in the old language and the shot would
    # be a half-Russian window pretending otherwise.
    panel.set_language("en")
    panel.set_text("move the files to dropbox and send the report", "")
    panel.set_status(text.t("status_ready"))
    panel.set_hotkey("Win+Ctrl+Right  /  Alt+Win")
    panel._notebook.select(0)
    _settle(panel._root)
    shot = capture(hwnd).convert("RGB")
    shot.save(OUT / "panel-en.png")
    written.append(OUT / "panel-en.png")

    panel._root.destroy()
    return written


def _keyed_to_alpha(image: Image.Image) -> Image.Image:
    """Punch out the colour key, for anything Pillow draws rather than Tk.

    The plate is laid down on `_COLOR_KEY`, because Tk has to be told to make one
    colour transparent and that one is easier to key on. Pillow has no such
    option, so the key goes to alpha here.

    The test is "is this pixel the key, or on the way to it from the plate's own
    outermost colour", and not the equality test alone: resampling blends the key
    into its neighbour, and an equality test leaves a rim of half-keyed pixels
    exactly where the eye notices. So the key is compared against `_BACKGROUND` —
    the outermost layer of the plate, and therefore the only colour the key is
    ever blended into — and a pixel goes when the key is nearer than that is.

    It used to be "is this blue dominant", which was a way of saying the same
    thing for one palette and only that one: the key is `#0000fe`, and it held
    while the bars were pink, where red is the largest channel. It stopped
    holding the moment a theme put indigo bars on the chip, and it punched out
    the two things it was supposed to keep. A test that names the key and the
    colour it blends into does not care what the palette is.
    """
    key = theme.rgb(overlay._COLOR_KEY)
    glow = overlay._rgb(overlay._BACKGROUND)
    rgba = image.convert("RGBA")
    pixels = rgba.load()

    def distance(pixel, other) -> float:
        return sum((a - b) ** 2 for a, b in zip(pixel, other))

    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha = pixels[x, y]
            pixel = (red, green, blue)
            if distance(pixel, key) <= distance(pixel, glow):
                pixels[x, y] = (red, green, blue, 0)
    return rgba



def _chip_frame(heights: list[float], seconds: int, scale: int = 4,
                smooth: bool = False) -> Image.Image:
    """One frame of the chip, in Pillow, from the module's own numbers.

    A bar is five rectangles: a low block on the centre line, a mid and a high
    band on each side of it. That is `_resize` in `overlay.py`, and the halves
    it draws are the ones drawn here, so the picture matches what the chip shows
    on screen at the same heights.

    `smooth` trades the hard pixels of a nearest-neighbour blow-up for a soft
    one, which is what a magnified illustration wants; the animated chip stays on
    the nearest-neighbour fold so a bar never blurs as it grows.

    The colour key is punched to alpha on the way out, so the result carries real
    alpha and the banner pastes it as a mask rather than as a rectangle.
    """
    plate = overlay.build_plate()
    frame = plate.copy()
    draw = ImageDraw.Draw(frame)
    for index, span in enumerate(heights):
        third = span / 3
        for colour, top, bottom in (
            (BAR_LOW, overlay.BAR_MID - third, overlay.BAR_MID + third),
            (BAR_MID, overlay.BAR_MID - 2 * third, overlay.BAR_MID - third),
            (BAR_MID, overlay.BAR_MID + third, overlay.BAR_MID + 2 * third),
            (BAR_HIGH, overlay.BAR_MID - span, overlay.BAR_MID - 2 * third),
            (BAR_HIGH, overlay.BAR_MID + 2 * third, overlay.BAR_MID + span),
        ):
            left, top_y, right, bottom_y = overlay._bar_box(index, top, bottom)
            draw.rectangle(
                (left, top_y, right - 1, bottom_y - 1), fill=colour
            )
    # The clock's point size comes from the module rather than being written here,
    # for the same reason the colours do: a size typed in two places is a size that
    # will be right in one of them.
    clock = ImageFont.truetype(str(FONTS / "consola.ttf"), overlay.CLOCK_SIZE)
    draw.text((overlay.WIDTH // 2, overlay.CLOCK_Y),
              f"{seconds // 60}:{seconds % 60:02d}",
              font=clock, fill=CLOCK, anchor="mm")

    size = (frame.width * scale, frame.height * scale)
    resample = Image.Resampling.LANCZOS if smooth else Image.Resampling.NEAREST
    return _keyed_to_alpha(frame.resize(size, resample))


def chip_animation(frames: int = 24) -> Path:
    """The chip moving the way it moves on speech, as a GIF.

    The shaping is the application's own: the same bell of energy, the same
    wobble, the same attack and decay rates. The level fed in is synthesised, so
    this is the animation drawn from the real code and not a recording of it.
    """
    heights = [float(overlay.BAR_IDLE)] * overlay.BARS
    swings = [overlay._swing(overlay.PHASE_SPREAD * i) for i in range(overlay.BARS)]
    images = []
    phase = 0.0
    for step in range(frames):
        phase += 0.26
        # A level with two bumps and a gap between them: speech is not a
        # uniform hum, and bars that never settle read as broken.
        if step % 12 < 7:
            energy = 0.35 + 0.65 * abs(math.sin(phase * 0.8))
        else:
            energy = 0.06
        drive = min(1.0, energy * overlay.DRIVE)
        for index in range(overlay.BARS):
            goal = (
                overlay.BAR_IDLE
                + drive * (
                    overlay._BELL_SPAN[index] * (1.0 + overlay.WOBBLE_REL * swings[index])
                    + overlay.WOBBLE_ABS * swings[index]
                )
            )
            distance = abs(index - overlay._CENTRE) / overlay._CENTRE
            rate = (
                overlay.ATTACK * (1.0 - 0.04 * distance)
                if goal > heights[index]
                else overlay.DECAY * (1.0 + 0.06 * distance)
            )
            heights[index] += (goal - heights[index]) * rate
        images.append(_chip_frame(heights, step * 5 // 10))
    path = OUT / "chip.gif"
    # A GIF has no alpha channel and one bit of transparency, so each frame is
    # quantised to 255 colours and the punched-out pixels are moved onto the last
    # index, which is then declared transparent. Without this the colour key comes
    # back as a blue rectangle around the chip.
    quantised = []
    for frame in images:
        mask = frame.getchannel("A").point(lambda value: 255 if value < 128 else 0)
        palette = frame.convert("RGB").convert(
            "P", palette=Image.Palette.ADAPTIVE, colors=255
        )
        palette.paste(255, mask)
        palette.info["transparency"] = 255
        quantised.append(palette)
    quantised[0].save(path, save_all=True, append_images=quantised[1:],
                      duration=70, loop=0, optimize=True, transparency=255)
    return path


def _gradient(size: tuple[int, int], top: tuple[int, int, int],
              bottom: tuple[int, int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGB", (1, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        share = y / max(1, height - 1)
        draw.point(
            (0, y),
            fill=tuple(round(a + (b - a) * share) for a, b in zip(top, bottom)),
        )
    return image.resize((width, height))


# The banner's page. A dark hero rather than a screenshot is a deliberate choice
# and stays; what follows from the palette is the accent on it, because a literal
# is how a page ends up advertising a colour the product no longer has anywhere
# in it. Every colour below is one of these two functions of `PALETTE`, so a
# theme change moves the whole banner with it.
_PAGE = (13, 11, 17)


def _tint(colour: tuple[int, int, int], share: float) -> tuple[int, int, int]:
    """`colour` mixed towards white by `share`, 0.0 leaving it alone."""
    return tuple(
        max(0, min(255, round(c + (255 - c) * share))) for c in colour
    )


def _page_tint(share: float) -> tuple[int, int, int]:
    """The page lightened, for text and for the keycaps sitting on it."""
    return _tint(_PAGE, share)


def _keycap(draw: ImageDraw.ImageDraw, x: int, y: int, label: str,
            font: ImageFont.FreeTypeFont, width: int = 46) -> int:
    """One key in the hotkey, drawn as a cap. Returns the width it used.

    Solid fills, not a white at some alpha: `ImageDraw` writes the alpha straight
    into the image instead of blending it, so a translucent fill would drop the
    background and the cap would read as a white blob once the file is saved.
    """
    height = 40
    draw.rounded_rectangle(
        (x, y, x + width, y + height), radius=8,
        fill=_page_tint(0.25), outline=_page_tint(0.55), width=1,
    )
    draw.text((x + width / 2, y + height / 2 + 1), label, font=font,
              fill=_page_tint(0.90), anchor="mm")
    return width


def _chip_card(scale: int = 4, smooth: bool = True) -> Image.Image:
    """The real chip, blown up, as the right half of the banner.

    The plate comes from `overlay.build_plate` and the bars are drawn with the
    module's geometry and ramp, so this is the chip the app shows — a photograph
    of the window itself would come out at 92x40 and lose the rim.

    Four times, not five. The chip's bars are two pixels wide with three of
    white between them, and a fifth of that is eight-pixel bars almost touching:
    on the old dark chip that read as texture, on the light one it reads as a
    barcode. Four leaves sixteen pixels of gap against an eight pixel bar, which
    is what an equalizer looks like rather than what a fence looks like.

    The heights are inside the chip's own range, which the exaggerated set this
    replaces was not: `BAR_SPAN_MAX` is 4.7 over an idle of 3, so the tallest a
    bar ever gets is a half-height of 7.7, and a number twice that reaches past
    the top of the plate and crosses the clock on its way. On a dark chip against
    a dark page that read as energy; on a white plate it read as a mistake.
    """
    return _chip_frame([3.0, 4.6, 6.2, 7.2, 7.6, 7.4, 7.0, 6.2, 5.0, 3.8, 3.0],
                       12, scale=scale, smooth=smooth)


def banner() -> Path:
    """The header image: the product's own colours, type, keycaps and chip."""
    width, height = 1280, 420
    image = _gradient((width, height), _page_tint(0.06), _PAGE).convert("RGBA")
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        (820, -160, 1500, 470), fill=theme.rgb(PALETTE.accent) + (40,)
    )
    from PIL import ImageFilter

    image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(110)))
    draw = ImageDraw.Draw(image, "RGBA")

    wordmark = ImageFont.truetype(str(FONTS / "seguisb.ttf"), 82)
    tagline = ImageFont.truetype(str(FONTS / "segoeui.ttf"), 27)
    hint = ImageFont.truetype(str(FONTS / "segoeui.ttf"), 21)
    fact = ImageFont.truetype(str(FONTS / "seguisb.ttf"), 23)
    key = ImageFont.truetype(str(FONTS / "seguisb.ttf"), 19)
    bullet = ImageFont.truetype(str(FONTS / "segoeui.ttf"), 22)

    draw.text((64, 58), "WinVosk", font=wordmark, fill=_page_tint(1.0))
    draw.text((68, 152), "Offline dictation for Windows.", font=tagline,
              fill=_page_tint(0.92))
    draw.text((68, 188), "Any language. Nothing leaves the machine.",
              font=tagline, fill=_tint(theme.rgb(PALETTE.accent), 0.55))

    # The hotkey, as caps, then what it does.
    x = 68
    for label, cap in (("Win", 58), ("+", 26), ("Ctrl", 62), ("+", 26), ("→", 46)):
        used = _keycap(draw, x, 244, label, key, width=cap)
        x += used + 8
    draw.text((x + 14, 264), "or", font=hint, fill=_page_tint(0.55), anchor="lm")
    x += 66
    for label, cap in (("Alt", 52), ("+", 26), ("Win", 62)):
        used = _keycap(draw, x, 244, label, key, width=cap)
        x += used + 8
    draw.text((68, 308), "hold to speak, release to type at the caret",
              font=hint, fill=_page_tint(0.55))

    facts = (
        "6.0 MB executable",
        "4.6× faster than real time",
        "0 bytes uploaded, ever",
        "any Vosk model, 20+ languages",
    )
    x = 68
    y = 348
    for index, line in enumerate(facts):
        if index == 2:
            x, y = 68, 382
        draw.text((x, y), "•", font=bullet, fill=_tint(theme.rgb(PALETTE.accent), 0.35))
        draw.text((x + 18, y - 4), line, font=fact, fill=_page_tint(0.88))
        x += 18 + draw.textlength(line, font=fact) + 44

    # `paste` with the card as its own mask, not `alpha_composite`: the method
    # form of `alpha_composite` returns None in this Pillow, which would leave
    # the banner as a blank canvas one line later.
    card = _chip_card()
    image.paste(card, (width - card.width - 40, (height - card.height) // 2), card)
    draw = ImageDraw.Draw(image, "RGBA")
    note = ImageFont.truetype(str(FONTS / "segoeui.ttf"), 19)
    draw.text((width - 470 + 70, height - 62),
              "the chip, exactly as it is drawn on screen",
              font=note, fill=_page_tint(0.62), anchor="mm")

    draw.rectangle((0, height - 4, width, height), fill=_tint(theme.rgb(PALETTE.accent), 0.25))
    path = OUT / "banner.png"
    image.convert("RGB").save(path)
    return path


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    written = []
    written.append(banner())
    written.append(chip_animation())
    try:
        written += panel_shots()
    except Exception as exc:                       # no window station, no shots
        print(f"panel shots skipped: {exc}")
    for path in written:
        print(f"written    : {path.relative_to(ROOT)} "
              f"({path.stat().st_size / 1024:.0f} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())