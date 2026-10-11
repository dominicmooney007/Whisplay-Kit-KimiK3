#!/usr/bin/env python3
"""Hello, Display! - draw text, shapes and a progress bar on the LCD.

Run from the repo checkout (no install needed):
    python3 examples/01_hello_display.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from whisplaykit import Whisplay     # noqa: E402

W, H = Whisplay.WIDTH, Whisplay.HEIGHT  # 240 x 280

with Whisplay(backlight=80) as board:
    d = board.display

    # Paint a dark navy background into the buffer.
    d.clear("#101830")

    # Title, centred near the top (mind the ~20px rounded corners).
    d.text_centered("WHISPLAY", 34, size=26, color="cyan", bold=True)
    d.text_centered("hello display", 64, size=16, color="light_gray")

    # A few shapes.
    d.rectangle(20, 100, 220, 160, outline="white", radius=10)
    d.circle(60, 130, 16, fill_color="red")
    d.circle(120, 130, 16, fill_color="green")
    d.circle(180, 130, 16, fill_color="blue")
    d.line(20, 180, 220, 180, color="gray", width=2)

    # A progress bar with an automatic % label.
    d.progress_bar(30, 200, 180, 24, 0.66, fill_color="orange", label="auto")

    # Push the whole frame to the physical screen in one SPI transfer.
    d.refresh()

    # Blink the LED to celebrate, wait, then dim the backlight.
    board.led.blink("magenta", times=3, blocking=True)
    time.sleep(3)
    d.fill("black")              # immediate full-screen fill
    d.text_centered("bye!", 120, size=28, refresh=True)
    board.set_brightness(20)
    time.sleep(1)

# leaving the `with` block releases GPIO/SPI and turns the LED off
