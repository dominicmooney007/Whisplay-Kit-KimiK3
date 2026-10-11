"""Colour helpers for whisplaykit.

Every whisplaykit method that takes a ``color`` argument accepts any of:

* a colour name string: ``"red"``, ``"sky_blue"``, ... (see :data:`NAMED`)
* a hex string: ``"#ff8800"`` or ``"ff8800"``
* an ``(r, g, b)`` tuple with 0-255 components
* an RGB565 integer (``0xF800`` style) for raw screen operations
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Named colours (r, g, b)
# ---------------------------------------------------------------------------
NAMED = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "orange": (255, 165, 0),
    "purple": (128, 0, 128),
    "pink": (255, 105, 180),
    "lime": (50, 205, 50),
    "teal": (0, 128, 128),
    "navy": (0, 0, 128),
    "maroon": (128, 0, 0),
    "olive": (128, 128, 0),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
    "silver": (192, 192, 192),
    "dark_gray": (64, 64, 64),
    "dark_grey": (64, 64, 64),
    "light_gray": (211, 211, 211),
    "light_grey": (211, 211, 211),
    "brown": (165, 42, 42),
    "gold": (255, 215, 0),
    "sky_blue": (135, 206, 235),
    "forest_green": (34, 139, 34),
    "crimson": (220, 20, 60),
    "violet": (238, 130, 238),
    "indigo": (75, 0, 130),
    "coral": (255, 127, 80),
    "salmon": (250, 128, 114),
    "turquoise": (64, 224, 208),
    "off": (0, 0, 0),
}

#: Convenient aliases a quick prototype often reaches for.
BLACK = "black"
WHITE = "white"
RED = "red"
GREEN = "green"
BLUE = "blue"
YELLOW = "yellow"
CYAN = "cyan"
MAGENTA = "magenta"
ORANGE = "orange"


class ColorError(ValueError):
    """Raised when a colour specification cannot be understood."""


def to_rgb(color) -> tuple:
    """Normalise any accepted colour spec to an ``(r, g, b)`` 0-255 tuple."""
    if isinstance(color, str):
        key = color.strip().lower().replace(" ", "_")
        if key in NAMED:
            return NAMED[key]
        hexpart = key.lstrip("#")
        if len(hexpart) == 6:
            try:
                return (
                    int(hexpart[0:2], 16),
                    int(hexpart[2:4], 16),
                    int(hexpart[4:6], 16),
                )
            except ValueError:
                pass
        raise ColorError(
            f"Unknown colour {color!r}. Use a name from colors.NAMED, "
            "'#rrggbb', an (r, g, b) tuple or an RGB565 int."
        )
    if isinstance(color, (tuple, list)) and len(color) == 3:
        r, g, b = (int(c) for c in color)
        for c in (r, g, b):
            if not 0 <= c <= 255:
                raise ColorError(f"Component out of range 0-255 in {color!r}")
        return (r, g, b)
    if isinstance(color, int):
        if not 0 <= color <= 0xFFFF:
            raise ColorError(f"RGB565 int out of range: {color!r}")
        return rgb565_to_rgb(color)
    raise ColorError(f"Cannot interpret colour {color!r}")


def to_rgb565(color) -> int:
    """Convert any accepted colour spec to a 16-bit RGB565 integer."""
    r, g, b = to_rgb(color)
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def rgb565_to_rgb(value: int) -> tuple:
    """Convert a 16-bit RGB565 integer back to an ``(r, g, b)`` tuple."""
    r = (value >> 11) & 0x1F
    g = (value >> 5) & 0x3F
    b = value & 0x1F
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))


def scale(color, factor: float):
    """Scale the brightness of a colour by ``factor`` (0.0 - 1.0+)."""
    r, g, b = to_rgb(color)
    f = max(0.0, float(factor))
    return (min(255, int(r * f)), min(255, int(g * f)), min(255, int(b * f)))


def wheel(position: float) -> tuple:
    """Rainbow colour from ``position`` 0.0-1.0 (hue around the wheel).

    Useful for LED and screen effects without importing colorsys yourself.
    """
    import colorsys

    h = float(position) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
    return (int(r * 255), int(g * 255), int(b * 255))
