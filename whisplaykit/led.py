"""RGB status LED API for the Whisplay HAT.

The board has one common-anode RGB LED (red pin 22, green pin 18,
blue pin 16) driven by software PWM. All effects that run over time
(:meth:`RGBLed.blink`, :meth:`RGBLed.pulse`, :meth:`RGBLed.rainbow`) run
in a background thread by default and return a handle whose ``stop()``
method ends the effect. Only one effect runs at a time: starting a new
one stops the previous one.
"""

from __future__ import annotations

import math
import threading
import time

from . import colors


class LedEffect(threading.Thread):
    """Background LED effect. Call :meth:`stop` to end it, optionally
    :meth:`join` to wait for the thread."""

    def __init__(self, led):
        super().__init__(daemon=True)
        self._led = led
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    @property
    def stopped(self):
        return self._stop_event.is_set()


class _Blink(LedEffect):
    def __init__(self, led, color, on_time, off_time, times):
        super().__init__(led)
        self._color = color
        self._on = on_time
        self._off = off_time
        self._times = times

    def run(self):
        count = 0
        while not self.stopped:
            self._led._set(self._color)
            if self._stop_event.wait(self._on):
                break
            self._led._set((0, 0, 0))
            if self._stop_event.wait(self._off):
                break
            count += 1
            if self._times is not None and count >= self._times:
                break


class _Pulse(LedEffect):
    """Smooth breathing effect using a sine wave."""

    def __init__(self, led, color, period, times):
        super().__init__(led)
        self._color = colors.to_rgb(color)
        self._period = period
        self._times = times

    def run(self):
        start = time.monotonic()
        while not self.stopped:
            t = time.monotonic() - start
            phase = (t % self._period) / self._period
            level = (1 - math.cos(phase * 2 * math.pi)) / 2  # 0..1..0
            self._led._set(colors.scale(self._color, level))
            if self._times is not None and int(t / self._period) >= self._times:
                break
            self._stop_event.wait(0.02)


class _Rainbow(LedEffect):
    def __init__(self, led, speed, duration):
        super().__init__(led)
        self._speed = speed
        self._duration = duration

    def run(self):
        start = time.monotonic()
        while not self.stopped:
            t = time.monotonic() - start
            if self._duration is not None and t >= self._duration:
                break
            self._led._set(colors.wheel(t * self._speed))
            self._stop_event.wait(0.02)


class RGBLed:
    """Control of the Whisplay RGB LED.

    Created for you by :class:`whisplaykit.Whisplay` as ``board.led``.
    The hardware already handles the LED's active-low wiring, so
    ``set_rgb(255, 0, 0)`` really is full red.
    """

    def __init__(self, board):
        self._board = board
        self._effect = None

    # ------------------------------------------------------------------
    # Basic control
    # ------------------------------------------------------------------
    def set(self, color):
        """Set the LED to any colour spec (name, hex, tuple).
        Stops any running effect."""
        r, g, b = colors.to_rgb(color)
        self.set_rgb(r, g, b)

    # Natural alias: led.set_color("red")
    set_color = set
    # Natural alias: led.on(color="white")
    on = set

    def set_rgb(self, r, g, b):
        """Set the LED channels directly (0-255 each).
        Stops any running effect (when called from your code — a running
        effect may update the LED freely itself)."""
        effect = self._effect
        if effect is not None and threading.current_thread() is not effect:
            self.stop_effect()
        self._board.set_rgb(int(r), int(g), int(b))

    def _set(self, color):
        """Raw write used by effects: never touches the active effect."""
        r, g, b = colors.to_rgb(color)
        self._board.set_rgb(int(r), int(g), int(b))

    def off(self):
        """Turn the LED fully off (and stop any running effect)."""
        self.set_rgb(0, 0, 0)

    @property
    def color(self):
        """Current ``(r, g, b)`` value as last set."""
        return (self._board._current_r, self._board._current_g,
                self._board._current_b)

    # ------------------------------------------------------------------
    # Effects (background threads; pass blocking=True to run inline)
    # ------------------------------------------------------------------
    def blink(self, color="white", on_time=0.2, off_time=0.2, times=None,
              blocking=False) -> LedEffect:
        """Blink ``color``. ``times=None`` blinks forever until
        :meth:`stop_effect` (or another LED call)."""
        self.stop_effect()
        effect = _Blink(self, color, on_time, off_time, times)
        self._run(effect, blocking)
        return effect

    def pulse(self, color="blue", period=1.5, times=None,
              blocking=False) -> LedEffect:
        """Smooth breathing effect. ``times=None`` breathes forever."""
        self.stop_effect()
        effect = _Pulse(self, color, period, times)
        self._run(effect, blocking)
        return effect

    # Alias often used for breathing status lights.
    breathe = pulse

    def rainbow(self, speed=0.15, duration=None, blocking=False) -> LedEffect:
        """Cycle through the colour wheel. ``speed`` is full cycles per
        second, ``duration=None`` runs forever."""
        self.stop_effect()
        effect = _Rainbow(self, speed, duration)
        self._run(effect, blocking)
        return effect

    def stop_effect(self):
        """Stop the currently running effect, if any (LED keeps its last
        colour — call :meth:`off` to also go dark)."""
        effect = self._effect
        self._effect = None
        if effect is not None:
            effect.stop()
            if effect.is_alive() and threading.current_thread() is not effect:
                effect.join(timeout=1.0)

    def _run(self, effect, blocking):
        if blocking:
            self._effect = effect
            effect.run()
            if self._effect is effect:
                self._effect = None
        else:
            self._effect = effect
            effect.start()
