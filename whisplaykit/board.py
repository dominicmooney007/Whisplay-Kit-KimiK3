"""The main entry point: one :class:`Whisplay` object for the whole board.

.. code-block:: python

    from whisplaykit import Whisplay

    with Whisplay() as board:
        board.display.text_centered("Hello!", 130, size=32)
        board.display.refresh()
        board.led.pulse("green")
        board.button.wait_for_press()
"""

from __future__ import annotations

import atexit


class Whisplay:
    """Facade over every Whisplay HAT peripheral.

    Attributes:
        ``display``  - :class:`whisplaykit.display.Display`  (240x280 LCD)
        ``led``      - :class:`whisplaykit.led.RGBLed`       (RGB LED)
        ``button``   - :class:`whisplaykit.button.Button`    (push button)
        ``speaker``  - :class:`whisplaykit.audio.Speaker`
        ``mic``      - :class:`whisplaykit.audio.Microphone`
    """

    #: LCD geometry, exposed for convenience.
    WIDTH = 240
    HEIGHT = 280

    def __init__(self, backlight=70):
        """Open the board.

        :param backlight: initial backlight brightness 0-100 (``None`` to
                          leave it as the driver initialised it).
        """
        self._closed = False
        try:
            from ._hardware import WhisplayBoard
        except ImportError as exc:
            raise RuntimeError(
                "whisplaykit needs the low-level system packages "
                "'python3-spidev' and 'python3-libgpiod'.\n"
                "  sudo apt install python3-spidev python3-libgpiod\n"
                f"(original error: {exc})"
            ) from exc
        try:
            self._board = WhisplayBoard()
        except Exception as exc:
            raise RuntimeError(
                "Could not initialise the Whisplay HAT. Check that:\n"
                "  * this script runs on the Pi/Radxa/Orange Pi with the\n"
                "    Whisplay HAT attached,\n"
                "  * the official driver was installed "
                "(sudo bash install_driver.sh) and the system rebooted,\n"
                "  * the whisplay-daemon service is not holding the hardware\n"
                "    (sudo systemctl stop whisplay-daemon).\n"
                f"(original error: {exc})"
            ) from exc

        from .display import Display
        from .led import RGBLed
        from .button import Button
        from .audio import Speaker, Microphone

        self.display = Display(self._board)
        self.led = RGBLed(self._board)
        self.button = Button(self._board)
        self.speaker = Speaker()
        self.mic = Microphone()

        if backlight is not None:
            self.set_brightness(backlight)
        atexit.register(self._at_exit)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------
    def set_brightness(self, percent):
        """Backlight brightness 0-100 (same as
        ``board.display.set_brightness``)."""
        self._board.set_backlight(int(max(0, min(100, percent))))

    set_backlight = set_brightness

    @property
    def platform(self):
        """Detected platform string, e.g. ``"rpi"``."""
        return self._board.platform

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def close(self):
        """Release all hardware: LED off, SPI/GPIO released, button thread
        stopped. Safe to call more than once."""
        if getattr(self, "_closed", True):
            return
        self._closed = True
        try:
            self.button.close()
        except Exception:
            pass
        try:
            self.led.off()
        except Exception:
            pass
        try:
            self._board.cleanup()
        except Exception:
            pass

    # Familiar alias.
    cleanup = close

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def __del__(self):  # pragma: no cover - interpreter shutdown
        try:
            self.close()
        except Exception:
            pass

    def _at_exit(self):  # pragma: no cover
        if not self._closed:
            self.close()
