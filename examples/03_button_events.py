#!/usr/bin/env python3
"""Button events: press, release, click, double-click, long-press.

Every gesture flashes a different LED colour and prints to the console.
Long-press exits the program.

    python3 examples/03_button_events.py
"""
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from whisplaykit import Whisplay     # noqa: E402

done = threading.Event()   # set by the handler worker to end the script

with Whisplay(backlight=40) as board:
    led = board.led
    btn = board.button

    # Handlers run on the button thread - keep them short and defer any
    # slow work (like drawing) with a queue/flag if you build a real UI.
    btn.on_press(lambda: led.set("white"))
    btn.on_release(lambda: led.off())
    btn.on_click(lambda: led.blink("green", times=2, on_time=0.1, off_time=0.1))
    btn.on_double_click(lambda: led.blink("cyan", times=3, on_time=0.1,
                                          off_time=0.1))
    btn.on_long_press(lambda: (print("long press -> exit"), done.set()))

    btn.on_press(lambda: print("press"))
    btn.on_release(lambda: print("release"))
    btn.on_click(lambda: print("click"))
    btn.on_double_click(lambda: print("double click"))

    print("Try: tap / double tap / hold. Hold exits.")
    done.wait()
