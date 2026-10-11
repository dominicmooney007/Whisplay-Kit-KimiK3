"""whisplaykit - an easy-to-use Python API for the PiSugar Whisplay HAT.

Quick start::

    from whisplaykit import Whisplay

    with Whisplay() as board:
        board.display.fill("#101830")
        board.display.text_centered("Hi!", 130, size=32)
        ...
"""

from . import colors
from .board import Whisplay
from .display import Display
from .led import RGBLed, LedEffect
from .button import Button, ButtonError
from .audio import (
    Speaker, Microphone, Playback, AudioError,
    audio_available, find_card, alsa_device,
)

__version__ = "1.0.0"

__all__ = [
    "Whisplay",
    "Display",
    "RGBLed",
    "LedEffect",
    "Button",
    "ButtonError",
    "Speaker",
    "Microphone",
    "Playback",
    "AudioError",
    "audio_available",
    "find_card",
    "alsa_device",
    "colors",
    "__version__",
]

# Screen geometry constants (also available as Whisplay.WIDTH / .HEIGHT).
SCREEN_WIDTH = 240
SCREEN_HEIGHT = 280
