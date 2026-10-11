"""Button API for the Whisplay HAT (single push button, physical pin 11).

The button line has an external pull-down on the board: it reads HIGH
while pressed and LOW while released. A background thread polls the line
with debouncing and classifies gestures:

* ``press``        - the moment the button goes down
* ``release``      - the moment the button comes back up
* ``click``        - a press+release quicker than :attr:`long_press_time`
                     (deferred by :attr:`double_click_window` when a
                     double-click handler is registered, so the two are
                     not mixed up)
* ``double_click`` - two clicks within :attr:`double_click_window`
* ``long_press``   - button held for at least :attr:`long_press_time`

Register handlers with ``on_press(fn)`` etc. Handlers are called with no
arguments on the button thread; keep them short (or just set a flag /
post to a queue). Every gesture also has a blocking ``wait_for_*`` helper
for simple scripts.
"""

from __future__ import annotations

import threading
import time


class ButtonError(RuntimeError):
    pass


class Button:
    """The Whisplay push button.

    Created for you by :class:`whisplaykit.Whisplay` as ``board.button``.
    """

    def __init__(self, board, debounce=0.03, double_click_window=0.35,
                 long_press_time=0.8, poll_interval=0.005):
        self._board = board
        # Gesture tuning (tweak after construction if you like):
        self.debounce = debounce                      # seconds
        self.double_click_window = double_click_window  # seconds
        self.long_press_time = long_press_time        # seconds
        self.poll_interval = poll_interval            # seconds

        self._press_cbs = []
        self._release_cbs = []
        self._click_cbs = []
        self._double_cbs = []
        self._long_cbs = []
        self._cb_lock = threading.Lock()

        self._press_event = threading.Event()
        self._release_event = threading.Event()
        self._click_event = threading.Event()
        self._double_event = threading.Event()
        self._long_event = threading.Event()

        try:
            self._state = 1 if board.button_pressed() else 0
        except Exception as exc:  # pragma: no cover - hardware only
            raise ButtonError(
                "Could not read the Whisplay button GPIO - are you running "
                "on a Whisplay-equipped board with the driver installed? "
                f"({exc})"
            ) from exc

        self._running = True
        self._thread = threading.Thread(target=self._monitor, daemon=True,
                                        name="whisplaykit-button")
        self._thread.start()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    @property
    def is_pressed(self) -> bool:
        """True while the button is physically held down."""
        return self._state == 1

    def pressed(self) -> bool:
        """Method alias for :attr:`is_pressed`."""
        return self.is_pressed

    # ------------------------------------------------------------------
    # Handler registration (``fn`` is called with no arguments)
    # ------------------------------------------------------------------
    def on_press(self, fn):
        """Call ``fn()`` each time the button is pressed down."""
        self._add(self._press_cbs, fn)

    def on_release(self, fn):
        """Call ``fn()`` each time the button is released."""
        self._add(self._release_cbs, fn)

    def on_click(self, fn):
        """Call ``fn()`` for a quick press+release (tap)."""
        self._add(self._click_cbs, fn)

    def on_double_click(self, fn):
        """Call ``fn()`` for two taps within :attr:`double_click_window`.
        While a double-click handler exists, single ``click`` events are
        delayed by that window so one tap is never reported as both."""
        self._add(self._double_cbs, fn)

    def on_long_press(self, fn):
        """Call ``fn()`` once when the button has been held for
        :attr:`long_press_time` seconds (a matching release then produces
        no ``click``)."""
        self._add(self._long_cbs, fn)

    def clear_handlers(self, event=None):
        """Remove handlers. ``event`` may be ``"press"``, ``"release"``,
        ``"click"``, ``"double_click"`` or ``"long_press"``; ``None``
        clears everything."""
        with self._cb_lock:
            targets = {
                "press": self._press_cbs, "release": self._release_cbs,
                "click": self._click_cbs, "double_click": self._double_cbs,
                "long_press": self._long_cbs,
            }
            if event is None:
                for lst in targets.values():
                    lst.clear()
            elif event in targets:
                targets[event].clear()
            else:
                raise ValueError(f"Unknown button event {event!r}")

    # ------------------------------------------------------------------
    # Blocking helpers
    # ------------------------------------------------------------------
    def wait_for_press(self, timeout=None) -> bool:
        """Block until the button is pressed. Returns True, or False on
        ``timeout`` (seconds)."""
        return self._wait(self._press_event, timeout)

    def wait_for_release(self, timeout=None) -> bool:
        """Block until the button is released."""
        return self._wait(self._release_event, timeout)

    def wait_for_click(self, timeout=None) -> bool:
        """Block until a tap (quick press+release) happens."""
        return self._wait(self._click_event, timeout)

    def wait_for_double_click(self, timeout=None) -> bool:
        return self._wait(self._double_event, timeout)

    def wait_for_long_press(self, timeout=None) -> bool:
        return self._wait(self._long_event, timeout)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def close(self):
        """Stop the monitoring thread (called by ``Whisplay.close()``)."""
        self._running = False
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _add(self, lst, fn):
        if not callable(fn):
            raise TypeError("button handler must be callable")
        with self._cb_lock:
            lst.append(fn)

    def _fire(self, lst):
        with self._cb_lock:
            callbacks = list(lst)
        for cb in callbacks:
            try:
                cb()
            except Exception as exc:
                print(f"[whisplaykit] button handler error: {exc}")

    @staticmethod
    def _wait(event, timeout):
        event.clear()
        return event.wait(timeout)

    def _read(self):
        return 1 if self._board.button_pressed() else 0

    def _monitor(self):
        last_raw = self._read()
        stable = last_raw
        last_change = time.monotonic()
        press_started = None
        long_fired = False
        pending_click_at = None   # deferred single-click fire time
        double_armed = False      # 2nd press of a possible double-click

        while self._running:
            raw = self._read()
            now = time.monotonic()

            if raw != last_raw:  # contact bounce: restart debounce timer
                last_raw = raw
                last_change = now
            elif raw != stable and (now - last_change) >= self.debounce:
                # Confirmed edge.
                stable = raw
                if stable == 1:
                    press_started = now
                    long_fired = False
                    self._press_event.set()
                    self._fire(self._press_cbs)
                    # A new press before a deferred click fires means this
                    # is the second half of a double-click: cancel the
                    # single click and arm the double test.
                    double_armed = False
                    if self._double_cbs and pending_click_at is not None:
                        pending_click_at = None
                        double_armed = True
                else:
                    press_started = None
                    self._release_event.set()
                    self._fire(self._release_cbs)
                    if not long_fired:
                        if self._double_cbs:
                            if double_armed:
                                double_armed = False
                                self._double_event.set()
                                self._fire(self._double_cbs)
                            else:
                                pending_click_at = now + \
                                    self.double_click_window
                        else:
                            self._click_event.set()
                            self._fire(self._click_cbs)

            # Long-press detection while held.
            if stable == 1 and press_started is not None and not long_fired \
                    and self._long_cbs:
                if now - press_started >= self.long_press_time:
                    long_fired = True
                    self._long_event.set()
                    self._fire(self._long_cbs)

            # Deferred single click (only when a double-click handler waits).
            if pending_click_at is not None and now >= pending_click_at:
                pending_click_at = None
                self._click_event.set()
                self._fire(self._click_cbs)

            time.sleep(self.poll_interval)
