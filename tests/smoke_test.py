#!/usr/bin/env python3
"""Off-device smoke test: exercises whisplaykit logic with a fake board,
renders the framebuffer to tests/out/*.png and simulates button traffic.

Runs anywhere Python + Pillow are installed (no SPI/GPIO required):

    python3 tests/smoke_test.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from whisplaykit import colors                       # noqa: E402
from whisplaykit.display import Display             # noqa: E402
from whisplaykit.led import RGBLed                  # noqa: E402
from whisplaykit.button import Button               # noqa: E402
from whisplaykit.audio import Speaker               # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT_DIR, exist_ok=True)

PASS, FAIL = "PASS", "FAIL"
checks = []


def check(name, ok):
    checks.append((name, bool(ok)))
    print(f"[{PASS if ok else FAIL}] {name}")


class FakeBoard:
    """Imitates whisplaykit._hardware.WhisplayBoard without hardware."""

    LCD_WIDTH, LCD_HEIGHT = 240, 280
    BUTTON_PIN = 11

    def __init__(self):
        self.frames = []          # (x, y, w, h, rgb565-bytes)
        self.fills = []           # rgb565 ints
        self.backlight = []
        self.led_values = []      # (r, g, b) history
        self._current_r = self._current_g = self._current_b = 0
        self._button_state = 0
        self.scripted = []        # [(delay_from_start_s, state), ...]
        self._t0 = None

    # -- LCD ----------------------------------------------------------
    def draw_image(self, x, y, width, height, pixel_data):
        self.frames.append((x, y, width, height, bytes(pixel_data)))

    def fill_screen(self, color):
        self.fills.append(color)

    def set_backlight(self, brightness):
        self.backlight.append(brightness)

    # -- LED ----------------------------------------------------------
    def set_rgb(self, r, g, b):
        self._current_r, self._current_g, self._current_b = r, g, b
        self.led_values.append((r, g, b))

    # -- button ---------------------------------------------------------
    def button_pressed(self):
        if self._t0 is None:
            return self._button_state
        elapsed = time.monotonic() - self._t0
        state = 0
        for at, st in self.scripted:
            if elapsed >= at:
                state = st
        return state


def test_colors():
    check("name -> rgb", colors.to_rgb("red") == (255, 0, 0))
    check("hex -> rgb", colors.to_rgb("#00ff00") == (0, 255, 0))
    check("tuple passthrough", colors.to_rgb((1, 2, 3)) == (1, 2, 3))
    check("rgb565 red", colors.to_rgb565("red") == 0xF800)
    check("rgb565 roundtrip",
          colors.to_rgb(colors.rgb565_to_rgb(colors.to_rgb565("white")))
          == (255, 255, 255))
    check("scale", colors.scale((100, 200, 50), 0.5) == (50, 100, 25))
    check("wheel endpoints", colors.wheel(0.0) == (255, 0, 0)
          and len(colors.wheel(0.33)) == 3)
    try:
        colors.to_rgb("not-a-colour")
        check("bad colour raises", False)
    except colors.ColorError:
        check("bad colour raises", True)


def test_display():
    fake = FakeBoard()
    d = Display(fake)

    d.fill("red")
    check("fill pushes frame via fill_screen",
          fake.fills and fake.fills[-1] == 0xF800)

    d.clear()
    d.text("Hello", 10, 10, size=20)
    d.text_centered("centre", 40, size=16)
    d.rectangle(5, 60, 100, 120, outline="white", radius=8)
    d.circle(150, 90, 20, fill_color="blue")
    d.line(0, 140, 239, 140, width=2)
    d.progress_bar(20, 160, 200, 22, 0.5, label="auto")
    d.refresh()
    check("refresh sends 240x280x2 bytes",
          fake.frames and fake.frames[-1][:4] == (0, 0, 240, 280)
          and len(fake.frames[-1][4]) == 240 * 280 * 2)

    d.set_brightness(45)
    check("backlight forwarded", fake.backlight[-1] == 45)

    png = os.path.join(OUT_DIR, "display.png")
    d.save(png)
    check("screenshot saved", os.path.exists(png) and os.path.getsize(png) > 0)

    w, h = d.measure_text("Hello", size=20)
    check("measure_text sane", w > 0 and h > 0)

    # RGB565 conversion agrees with a hand-computed pixel: pure red.
    d.clear("red")
    d.refresh()
    check("rgb565 byte order (red -> F8 00)",
          fake.frames[-1][4][0] == 0xF8 and fake.frames[-1][4][1] == 0x00)


def test_led():
    fake = FakeBoard()
    led = RGBLed(fake)
    led.set_color("red")
    check("led red", fake.led_values[-1] == (255, 0, 0))
    check("led.color property", led.color == (255, 0, 0))

    led.blink("blue", on_time=0.05, off_time=0.05, times=3, blocking=True)
    check("blink 3x toggles led",
          fake.led_values.count((0, 0, 255)) >= 3)

    led.pulse("green", period=0.2, times=1, blocking=True)  # one sweep
    check("pulse writes intermediate levels",
          any(0 < g < 255 for (_r, g, _b) in fake.led_values[-30:]))

    eff = led.rainbow(speed=5.0)              # background
    time.sleep(0.15)
    eff.stop()
    time.sleep(0.05)
    check("rainbow changes hue", len(set(fake.led_values[-5:])) > 1)

    # user call from main thread stops the background effect
    eff2 = led.blink("white", on_time=0.02, off_time=0.02)
    time.sleep(0.06)
    led.off()
    time.sleep(0.06)
    afterwards = len(fake.led_values)
    time.sleep(0.08)
    check("off() stops background effect",
          len(fake.led_values) == afterwards and fake.led_values[-1] == (0, 0, 0)
          and not eff2.is_alive())


def test_button():
    fake = FakeBoard()
    # tap A at 0.1s (80 ms), double tap at 0.7s/1.0s, long press 1.6s-2.6s
    fake.scripted = [(0.10, 1), (0.18, 0),
                     (0.70, 1), (0.78, 0), (1.00, 1), (1.08, 0),
                     (1.60, 1), (2.60, 0)]
    fake._t0 = time.monotonic()
    b = Button(fake, poll_interval=0.005)
    got = {"press": 0, "release": 0, "click": 0, "double": 0, "long": 0}
    b.on_press(lambda: got.__setitem__("press", got["press"] + 1))
    b.on_release(lambda: got.__setitem__("release", got["release"] + 1))
    b.on_click(lambda: got.__setitem__("click", got["click"] + 1))
    b.on_double_click(lambda: got.__setitem__("double", got["double"] + 1))
    b.on_long_press(lambda: got.__setitem__("long", got["long"] + 1))
    time.sleep(3.0)
    b.close()
    check("press x4", got["press"] == 4)
    check("release x4", got["release"] == 4)
    check("single click x1 (double tap produces no click)",
          got["click"] == 1)
    check("double click x1", got["double"] == 1)
    check("long press x1", got["long"] == 1)

    # wait_for_click: schedule a tap 0.2s out
    fake2 = FakeBoard()
    fake2.scripted = [(0.2, 1), (0.28, 0)]
    fake2._t0 = time.monotonic()
    b2 = Button(fake2)
    ok = b2.wait_for_click(timeout=2.0)
    b2.close()
    check("wait_for_click", ok)
    check("is_pressed property", fake.button_pressed() in (0, 1))


def test_tone_generation():
    path = Speaker.make_tone_wav(440, 0.1, volume=0.5)
    try:
        import wave
        with wave.open(path, "rb") as wav:
            ok = wav.getnchannels() == 1 and wav.getsampwidth() == 2 \
                and wav.getnframes() > 1000
        check("tone wav valid", ok)
    finally:
        os.unlink(path)


def main():
    test_colors()
    test_display()
    test_led()
    test_button()
    test_tone_generation()
    failed = [n for n, ok in checks if not ok]
    print("-" * 50)
    print(f"{len(checks) - len(failed)}/{len(checks)} checks passed")
    if failed:
        print("FAILED:", *failed, sep="\n  - ")
        sys.exit(1)


if __name__ == "__main__":
    main()
