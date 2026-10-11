"""High-level, prototyping-friendly API for the Whisplay 1.69" LCD.

The screen is a 240x280 pixel ST7789 colour LCD driven over SPI. This
module buffers all drawing in an off-screen PIL image: draw as much as you
like, then call :meth:`Display.refresh` to push the frame to the LCD.

Only :meth:`Display.fill` and :meth:`Display.show` update the physical
screen immediately (they refresh for you); every other drawing method is
buffered.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

from . import colors

try:  # Optional speed-up for the RGB -> RGB565 conversion
    import numpy as _np
except Exception:  # pragma: no cover - numpy not installed
    _np = None


_FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]
_FONT_CANDIDATES_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
]


class Display:
    """Buffer-and-refresh drawing API for the 240x280 Whisplay LCD.

    Created for you by :class:`whisplaykit.Whisplay` as ``board.display``.
    """

    WIDTH = 240
    HEIGHT = 280
    #: The panel glass has rounded corners; content within ~20 px of the
    #: short edges may be clipped visually on the top/bottom sides.
    CORNER_RADIUS = 20

    def __init__(self, board):
        self._board = board
        self.image = Image.new("RGB", (self.WIDTH, self.HEIGHT), (0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)
        self._font_cache = {}

    # ------------------------------------------------------------------
    # Framebuffer push / capture
    # ------------------------------------------------------------------
    def refresh(self, x=0, y=0, width=None, height=None):
        """Push the buffered frame (or a sub-rectangle) to the LCD.

        :param x, y: top-left corner of the region to push (default 0, 0)
        :param width, height: region size (default: whole screen)
        """
        width = self.WIDTH - x if width is None else width
        height = self.HEIGHT - y if height is None else height
        region = self.image.crop((x, y, x + width, y + height))
        self._board.draw_image(x, y, width, height, self._to_rgb565(region))

    # Alias that some people find more natural.
    present = refresh

    def show(self, source):
        """Immediately display an image full-screen (refreshes for you).

        :param source: a file path, a PIL ``Image``, or any colour spec
                       (fills the screen with that colour).
        """
        if isinstance(source, Image.Image):
            self.draw_image(source, fit=True)
        else:
            try:  # treat as colour first ("black", "#123456", tuple, ...)
                rgb = colors.to_rgb(source)
            except colors.ColorError:
                self.draw_image(source, fit=True)
            else:
                self.image.paste(rgb, (0, 0, self.WIDTH, self.HEIGHT))
        self.refresh()

    def fill(self, color="black"):
        """Fill the **physical screen** with ``color`` immediately."""
        self.image.paste(colors.to_rgb(color), (0, 0, self.WIDTH, self.HEIGHT))
        self._board.fill_screen(colors.to_rgb565(color))

    def clear(self, color="black"):
        """Clear the off-screen buffer (no refresh; call :meth:`refresh`)."""
        self.image.paste(colors.to_rgb(color), (0, 0, self.WIDTH, self.HEIGHT))

    def save(self, path):
        """Save the current buffer to a PNG/BMP file (handy for debugging,
        also works as a 'screenshot' of what is on the LCD)."""
        self.image.save(path)

    # ------------------------------------------------------------------
    # Backlight
    # ------------------------------------------------------------------
    def set_brightness(self, percent):
        """Set backlight brightness, 0-100. On the original Pi Zero the
        backlight is on/off only (0 = off, anything else = on)."""
        self._board.set_backlight(int(max(0, min(100, percent))))

    # WhisplayBoard naming, kept for discoverability.
    set_backlight = set_brightness

    # ------------------------------------------------------------------
    # Images
    # ------------------------------------------------------------------
    def load_image(self, path, size=None):
        """Load an image file as an RGB PIL Image, optionally resized to
        ``size=(w, h)``."""
        img = Image.open(path).convert("RGB")
        if size is not None:
            img = img.resize(size)
        return img

    def draw_image(self, source, x=0, y=0, size=None, fit=False, refresh=False):
        """Draw an image into the buffer.

        :param source: file path or PIL Image
        :param x, y: top-left position (with ``fit=True`` this is the
                     top-left of the bounding box the image is centred in)
        :param size: force ``(w, h)`` resize
        :param fit: scale to fit the whole screen, preserving aspect ratio
        """
        img = source if isinstance(source, Image.Image) else Image.open(source)
        img = img.convert("RGB")
        if fit:
            bw, bh = (self.WIDTH - x, self.HEIGHT - y)
            img.thumbnail((bw, bh), Image.LANCZOS)
            x = x + (bw - img.width) // 2
            y = y + (bh - img.height) // 2
        elif size is not None:
            img = img.resize(size)
        self.image.paste(img, (int(x), int(y)))
        if refresh:
            self.refresh()

    # ------------------------------------------------------------------
    # Text
    # ------------------------------------------------------------------
    def text(self, content, x, y, size=20, color="white", bold=False,
             font=None, anchor="la", refresh=False):
        """Draw text. ``content`` may contain ``\n`` for multiple lines.

        :param size: approximate pixel height of the font
        :param anchor: PIL anchor, e.g. ``"la"`` (left/ascender, default),
                       ``"mm"`` (middle-middle — great for centring at x, y)
        :param font: path to a .ttf file, or a pre-loaded PIL font
        """
        fnt = self._get_font(size, bold, font)
        xy = (int(x), int(y))
        fill = colors.to_rgb(color)
        if "\n" in str(content):
            self.draw.multiline_text(xy, str(content), font=fnt, fill=fill,
                                     anchor=anchor, align="left")
        else:
            self.draw.text(xy, str(content), font=fnt, fill=fill, anchor=anchor)
        if refresh:
            self.refresh()

    def text_centered(self, content, y, size=20, color="white", bold=False,
                      font=None, refresh=False):
        """Draw text horizontally centred on the screen at row ``y``."""
        self.text(content, self.WIDTH // 2, y, size=size, color=color,
                  bold=bold, font=font, anchor="ma", refresh=refresh)

    def measure_text(self, content, size=20, bold=False, font=None):
        """Return ``(width, height)`` in pixels of ``content`` at ``size``."""
        fnt = self._get_font(size, bold, font)
        left, top, right, bottom = self.draw.textbbox(
            (0, 0), str(content), font=fnt)
        return (right - left, bottom - top)

    # ------------------------------------------------------------------
    # Shapes
    # ------------------------------------------------------------------
    def pixel(self, x, y, color="white", refresh=False):
        """Draw a single pixel."""
        self.draw.point((int(x), int(y)), fill=colors.to_rgb(color))
        if refresh:
            self.refresh()

    def line(self, x0, y0, x1, y1, color="white", width=1, refresh=False):
        """Draw a straight line."""
        self.draw.line((x0, y0, x1, y1), fill=colors.to_rgb(color), width=width)
        if refresh:
            self.refresh()

    def rectangle(self, x0, y0, x1, y1, outline=None, fill_color=None,
                  width=1, radius=0, refresh=False):
        """Draw a rectangle; ``radius`` > 0 gives rounded corners."""
        ol = colors.to_rgb(outline) if outline is not None else None
        fl = colors.to_rgb(fill_color) if fill_color is not None else None
        box = (x0, y0, x1, y1)
        if radius:
            self.draw.rounded_rectangle(box, radius=radius, fill=fl,
                                        outline=ol, width=width)
        else:
            self.draw.rectangle(box, fill=fl, outline=ol, width=width)
        if refresh:
            self.refresh()

    def circle(self, cx, cy, r, outline=None, fill_color=None, width=1,
               refresh=False):
        """Draw a circle centred at (``cx``, ``cy``)."""
        self.ellipse(cx - r, cy - r, cx + r, cy + r, outline=outline,
                     fill_color=fill_color, width=width, refresh=refresh)

    def ellipse(self, x0, y0, x1, y1, outline=None, fill_color=None,
                width=1, refresh=False):
        """Draw an ellipse inside the bounding box."""
        ol = colors.to_rgb(outline) if outline is not None else None
        fl = colors.to_rgb(fill_color) if fill_color is not None else None
        self.draw.ellipse((x0, y0, x1, y1), fill=fl, outline=ol, width=width)
        if refresh:
            self.refresh()

    def progress_bar(self, x, y, width, height, fraction, fill_color="green",
                     background="dark_gray", border="white", label=None,
                     label_size=14, refresh=False):
        """Draw a progress bar for ``fraction`` (0.0 - 1.0).

        :param label: optional text drawn centred on the bar; pass ``"auto"``
                      to show the percentage automatically.
        """
        frac = max(0.0, min(1.0, float(fraction)))
        self.rectangle(x, y, x + width, y + height, outline=border,
                       fill_color=background, radius=height // 2)
        inner_w = int((width - 4) * frac)
        if inner_w > 0:
            self.rectangle(x + 2, y + 2, x + 2 + inner_w, y + height - 2,
                           fill_color=fill_color, radius=max(1, height // 2 - 2))
        if label is not None:
            text = f"{int(frac * 100)}%" if label == "auto" else str(label)
            self.text(text, x + width // 2, y + height // 2, size=label_size,
                      anchor="mm")
        if refresh:
            self.refresh()

    # ------------------------------------------------------------------
    # Raw access for power users
    # ------------------------------------------------------------------
    @property
    def canvas(self):
        """The underlying PIL ``Image`` buffer (draw with PIL directly)."""
        return self.image

    @property
    def size(self):
        """``(240, 280)``"""
        return (self.WIDTH, self.HEIGHT)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _get_font(self, size, bold=False, font=None):
        if isinstance(font, ImageFont.ImageFont):
            return font
        if font is None and size is None:
            return ImageFont.load_default()
        key = (str(font), int(size or 14), bool(bold))
        if key in self._font_cache:
            return self._font_cache[key]
        fnt = self._load_font(int(size or 14), bold, font)
        self._font_cache[key] = fnt
        return fnt

    @staticmethod
    def _load_font(size, bold, font):
        candidates = [font] if font else []
        candidates += (_FONT_CANDIDATES_BOLD if bold else []) + \
            _FONT_CANDIDATES_REGULAR
        for path in candidates:
            if not path or not os.path.exists(path):
                continue
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        try:  # Pillow >= 10 supports scalable default font
            return ImageFont.load_default(size)
        except TypeError:
            return ImageFont.load_default()

    def _to_rgb565(self, img):
        """Convert an RGB PIL image to big-endian RGB565 bytes fast."""
        if _np is not None:
            arr = _np.asarray(img, dtype=_np.uint16)
            packed = ((arr[..., 0] & 0xF8) << 8) | \
                     ((arr[..., 1] & 0xFC) << 3) | (arr[..., 2] >> 3)
            return packed.astype(">u2").tobytes()
        raw = img.tobytes()
        buf = bytearray((len(raw) // 3) * 2)
        j = 0
        for i in range(0, len(raw), 3):
            v = ((raw[i] & 0xF8) << 8) | \
                ((raw[i + 1] & 0xFC) << 3) | (raw[i + 2] >> 3)
            buf[j] = v >> 8
            buf[j + 1] = v & 0xFF
            j += 2
        return bytes(buf)
