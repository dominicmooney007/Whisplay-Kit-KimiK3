#!/usr/bin/env python3
"""RGB LED tour: solid colours, blink, breathing pulse, rainbow.

    python3 examples/02_rgb_led.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from whisplaykit import Whisplay     # noqa: E402
from whisplaykit import colors      # noqa: E402

with Whisplay(backlight=0) as board:    # backlight off: LED is the star
    led = board.led

    # 1. solid colours
    for name in ["red", "green", "blue", "yellow", "cyan", "magenta", "white"]:
        print(f"LED -> {name}")
        led.set_color(name)
        time.sleep(0.6)

    # any format works: hex, tuple, or a name
    led.set("#FF5500")
    time.sleep(0.5)
    led.set_rgb(0, 80, 255)
    time.sleep(0.5)

    # 2. blink - finite run, blocking (script waits for it)
    print("blink x5")
    led.blink("orange", on_time=0.15, off_time=0.15, times=5, blocking=True)

    # 3. breathing pulse in the background; script keeps running
    print("breathing (background, 4 s)")
    led.pulse("blue", period=1.6)
    time.sleep(4)

    # 4. rainbow for 4 seconds, also in the background
    print("rainbow")
    led.rainbow(speed=0.25)
    time.sleep(4)

    led.off()
    print("done")
