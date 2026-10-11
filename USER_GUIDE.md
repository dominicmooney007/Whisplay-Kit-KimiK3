# whisplay-kit User Guide

Complete function reference and cookbook for the PiSugar Whisplay HAT:
**LCD screen · push button · speaker · microphone · RGB LED**.

- [1. Setup](#1-setup) (incl. [Pi 5 / Trixie compatibility](#14-compatibility-notes-incl-pi-5--trixie))
- [2. Core concepts](#2-core-concepts)
- [3. The `Whisplay` object](#3-the-whisplay-object)
- [4. Screen — `board.display`](#4-screen--boarddisplay)
- [5. RGB LED — `board.led`](#5-rgb-led--boardled)
- [6. Button — `board.button`](#6-button--boardbutton)
- [7. Speaker — `board.speaker`](#7-speaker--boardspeaker)
- [8. Microphone — `board.mic`](#8-microphone--boardmic)
- [9. Colours — `whisplaykit.colors`](#9-colours--whisplaykitcolors)
- [10. Cookbook](#10-cookbook)
- [11. Troubleshooting](#11-troubleshooting)
- [12. Hardware reference](#12-hardware-reference)

---

## 1. Setup

### 1.1 Hardware

Whisplay HAT on a Raspberry Pi (any 40-pin model — Pi Zero / Zero 2 W /
Pi 5), Radxa ZERO 3W, Radxa Cubie A7Z or Orange Pi Zero 2W/3W.

- Align the HAT on the 40-pin header (button on the USB-port side).
- The screen glass is fragile: hold the PCB edges when mounting.
- **Do not press the button on Radxa Cubie A7Z / Orange Pi Zero 3W with
  Whisplay V1** — the button circuit carries 5 V and pressing it can
  power-cut the board. (Safe on Raspberry Pi, Radxa ZERO 3W, and with
  Whisplay V2 hardware.)

### 1.2 Drivers (once per SD card)

```bash
git clone https://github.com/PiSugar/Whisplay.git --depth 1
cd Whisplay
sudo bash install_driver.sh
sudo reboot
```

This enables SPI (screen) and I2C+I2S (audio codec) and installs the
`whisplaysound` ALSA card. Verify after reboot:

```bash
aplay -l          # should list card 'whisplaysound'
```

### 1.3 Python side

```bash
sudo apt install python3-spidev python3-libgpiod python3-pil
sudo apt install python3-numpy        # optional: ~2x faster refresh
sudo apt install mpg123 ffmpeg        # optional: MP3 / other formats

cd whisplay-kit
python3 -m venv --system-site-packages ~/whisplay-venv   # recommended
source ~/whisplay-venv/bin/activate
pip install .
# or system-wide: pip install . --break-system-packages
```

### 1.4 Compatibility notes (incl. Pi 5 + Trixie)

| System | Status |
| --- | --- |
| Raspberry Pi 5 + Raspberry Pi OS **Trixie** (Debian 13, Python 3.13, gpiod 2.2, kernel 6.12) | ✅ supported |
| Raspberry Pi 5 / 4 / 3 + Bookworm (gpiod 1.6) | ✅ supported |
| Pi Zero / Zero 2 W | ✅ supported (original Zero: backlight is on/off only) |
| Radxa ZERO 3W, Radxa Cubie A7Z (V2 HAT only), Orange Pi Zero 2W/3W | ✅ supported via upstream pin maps |

Pi 5 specifics, all handled automatically by whisplay-kit:

- **GPIO chip**: Pi 5 exposes the 40-pin header through `pinctrl-rp1`.
  On kernels < 6.6.45 it was `gpiochip4`; on current kernels (including
  all Trixie releases) the DT alias makes it `gpiochip0`. whisplay-kit
  detects the chip by its driver label, so both vintages work — the
  upstream driver hardcodes gpiochip4 and breaks on new kernels.
- **libgpiod**: Trixie ships the v2 API (`python3-libgpiod` 2.2.x);
  Bookworm ships v1 (1.6.x). Both are supported transparently.
- **Audio**: use PiSugar's current v3+ `install_driver.sh`; the
  `whisplay-soundcard` overlay then auto-loads from the HAT EEPROM at boot.
- **pip on Trixie**: Python 3.13 is externally-managed (PEP 668) — use a
  `--system-site-packages` venv (above) or `--break-system-packages`.

If GPIO fails with permission errors, add yourself to the gpio group
and re-login: `sudo usermod -aG gpio $USER`.

### 1.5 First run

```bash
python3 examples/01_hello_display.py   # screen demo
python3 examples/02_rgb_led.py         # LED demo
python3 examples/03_button_events.py   # button demo
python3 examples/04_voice_memo.py      # mic + speaker demo
```

---

## 2. Core concepts

### 2.1 Draw, then refresh

All screen drawing happens in an off-screen buffer. Nothing appears on the
LCD until you call `board.display.refresh()`:

```python
d = board.display
d.clear("#101830")            # buffer only
d.text("Temp: 21°C", 20, 30)  # buffer only
d.refresh()                   # ONE SPI transfer -> screen updates
```

Two exceptions update the physical screen immediately, for convenience:

- `display.fill(color)` — instant solid screen
- `display.show(image_or_color)` — instant full-screen image

### 2.2 Colours everywhere

Every `color=` argument accepts:

| Format | Example |
| --- | --- |
| name | `"red"`, `"sky_blue"`, `"dark_gray"` |
| hex string | `"#ff8800"` |
| (r, g, b) tuple | `(255, 136, 0)` |
| RGB565 int | `0xFC00` |

See the full name list in `whisplaykit/colors.py` (`colors.NAMED`).

### 2.3 Screen geometry

- 240 x 280 pixels, origin top-left, y grows downward.
- The panel glass is rounded: keep critical content away from ~20 px at the
  top/bottom edges (`Display.CORNER_RADIUS`).
- A full-screen `refresh()` takes ~25-60 ms (numpy makes it faster);
  `refresh(x, y, w, h)` can push just a sub-rectangle for snappier UIs.

### 2.4 Threads & callbacks

- Button handlers run on the button thread. Keep them short: set flags,
  append to a list/queue, or call quick actions (LED flash, beep). Do
  heavy redrawing in your main loop.
- LED effects (`blink`, `pulse`, `rainbow`) run in background threads;
  stop them with `board.led.stop_effect()` or any new LED call.
- `speaker.play(..., blocking=False)` returns a `Playback` handle.

### 2.5 Cleaning up

Use `with` — it releases GPIO/SPI, stops threads and turns the LED off:

```python
with Whisplay() as board:
    ...
```

or call `board.close()` yourself (Ctrl+C is fine too: an `atexit` hook
backstops you).

---

## 3. The `Whisplay` object

```python
from whisplaykit import Whisplay

board = Whisplay(backlight=70)   # brightness 0-100, or None to keep default
```

| Attribute | Type | What it controls |
| --- | --- | --- |
| `board.display` | `Display` | LCD screen & backlight buffer |
| `board.led` | `RGBLed` | RGB indicator LED |
| `board.button` | `Button` | push button + gestures |
| `board.speaker` | `Speaker` | audio playback & volume |
| `board.mic` | `Microphone` | recording & mic gain |

Class constants: `Whisplay.WIDTH` (240), `Whisplay.HEIGHT` (280).

Methods on `Whisplay` itself:

| Method | Description |
| --- | --- |
| `set_brightness(percent)` | Backlight 0-100 (alias `set_backlight`). |
| `close()` / `cleanup()` | Release all hardware. Idempotent. |
| `platform` (property) | `"rpi"`, `"radxa"` or `"orangepi"`. |
| context manager | `with Whisplay() as board:` |

---

## 4. Screen — `board.display`

### Frame control

#### `refresh(x=0, y=0, width=None, height=None)`
Push the buffer (or a sub-rectangle) to the LCD. Alias: `present()`.

```python
d.refresh()                    # whole screen
d.refresh(0, 100, 240, 60)     # only a band — much faster for small updates
```

#### `show(source)`
Immediately display `source` full-screen: a colour spec, an image path, or
a PIL Image. Refreshes for you.

```python
d.show("black")
d.show("boot.png")
d.show(d.load_image("cover.jpg"))
```

#### `fill(color="black")`
Instant solid-colour screen (immediate; also clears the buffer).

#### `clear(color="black")`
Clear only the off-screen buffer — pair with your own `refresh()`.

#### `save(path)`
Save the current buffer to a PNG/BMP file. Double as a screenshot, and it
works off-device when you test layouts from a PC.

#### `set_brightness(percent)` / `set_backlight(percent)`
Backlight 0-100. On the original Pi Zero (not Zero 2 W) the backlight is
on/off only: 0 = off, anything else = on.

```python
d.set_brightness(30)   # dim for battery saving
d.set_brightness(0)    # screen off, board still running
```

#### Properties
`d.size` -> `(240, 280)` · `d.canvas` -> the raw PIL `Image` ·
`d.draw` -> the PIL `ImageDraw` (direct PIL access) ·
constants `Display.WIDTH/HEIGHT/CORNER_RADIUS`.

### Text

#### `text(content, x, y, size=20, color="white", bold=False, font=None, anchor="la", refresh=False)`
Draw text; `\n` works for multiple lines.
`anchor` is the PIL anchor: `"la"` = left/top (default), `"mm"` =
centre-centre (handy: `d.text("42", 120, 140, anchor="mm")`).
`font` accepts a .ttf path or a pre-loaded PIL font.

#### `text_centered(content, y, size=20, color="white", bold=False, font=None, refresh=False)`
Horizontally centred text at row `y`.

#### `measure_text(content, size=20, bold=False, font=None)` -> `(w, h)`
Pixel size of a string before you draw it.

Every drawing method takes keyword `refresh=True` to push immediately.

### Images

#### `load_image(path, size=None)` -> PIL Image
Load (and optionally resize to `(w, h)`) an image file.

#### `draw_image(source, x=0, y=0, size=None, fit=False, refresh=False)`
Draw an image (path or PIL Image) into the buffer.
`size=(w, h)` forces a resize; `fit=True` scales to the screen keeping
aspect ratio and centres it.

```python
d.draw_image("icon.png", 20, 60)
d.draw_image("photo.jpg", fit=True, refresh=True)
```

Pixel speed tip: 240x280 JPG decodes fast enough on a Pi Zero 2 for
photo-frame style apps; prefer pre-resized PNGs for UI icons.

### Shapes

All of these take `refresh=False` as the final keyword.

- `pixel(x, y, color="white")`
- `line(x0, y0, x1, y1, color="white", width=1)`
- `rectangle(x0, y0, x1, y1, outline=None, fill_color=None, width=1, radius=0)`
  — `radius > 0` draws rounded corners.
- `circle(cx, cy, r, outline=None, fill_color=None, width=1)`
- `ellipse(x0, y0, x1, y1, outline=None, fill_color=None, width=1)`

### Widgets

#### `progress_bar(x, y, width, height, fraction, fill_color="green", background="dark_gray", border="white", label=None, label_size=14, refresh=False)`
`fraction` is 0.0-1.0. `label="auto"` prints the percentage; any other
string is drawn verbatim.

```python
d.progress_bar(20, 200, 200, 26, 0.67, label="auto")
```

### Example: complete screen

```python
with Whisplay() as board:
    d = board.display
    d.clear("#101830")
    d.text_centered("STATUS", 30, size=24, bold=True, color="cyan")
    d.rectangle(15, 70, 225, 130, outline="gray", radius=8)
    d.text("Mic: ready", 25, 85, size=16)
    d.text("WiFi: home-net", 25, 107, size=16)
    d.progress_bar(20, 150, 200, 22, 0.4, label="battery 40%")
    d.refresh()
```

---

## 5. RGB LED — `board.led`

One common-anode RGB LED, software PWM (the driver handles the active-low
wiring — what you set is what you see).

### Steady light

#### `set(color)` — aliases: `set_color(color)`, `on(color)`
```python
board.led.set_color("lime")
board.led.set("#FF8800")
board.led.on((0, 40, 0))          # dim green
```
Any of these stops a running effect.

#### `set_rgb(r, g, b)`
Direct channel control, 0-255 each.

#### `off()`
Turn fully off (stops effects too).

#### `color` (property)
The current `(r, g, b)` tuple.

### Effects

All effects return a handle with `.stop()` and run in the background
unless `blocking=True` is passed (blocking calls wait until `times` /
`duration` elapse — **never** call infinite effects with `blocking=True`).

#### `blink(color="white", on_time=0.2, off_time=0.2, times=None, blocking=False)`
```python
board.led.blink("red", times=3)                  # 3 flashes, background
board.led.blink("red", times=3, blocking=True)   # 3 flashes, waits
board.led.blink("cyan", on_time=0.5)             # until stop_effect()
```

#### `pulse(color="blue", period=1.5, times=None, blocking=False)` — alias `breathe`
Smooth sine-wave "breathing". Classic idle/standby indicator.

#### `rainbow(speed=0.15, duration=None, blocking=False)`
Cycle the colour wheel; `speed` is cycles per second,
`duration` in seconds (None = forever).

#### `stop_effect()`
Stop the running effect; the LED keeps its last colour.

```python
board.led.pulse("navy", period=3.0)   # calm idle glow
...
board.led.off()                       # done
```

---

## 6. Button — `board.button`

Single click-type push button (external pull-down: HIGH = pressed).
5 ms polling + 30 ms debounce + gesture classification, all built in.

### Instant state & blocking waits

| Call | Description |
| --- | --- |
| `button.is_pressed` (property) | True while held. Also: `button.pressed()`. |
| `button.wait_for_press(timeout=None)` | Block until a press; True/False on timeout. |
| `button.wait_for_release(timeout=None)` | Block until a release. |
| `button.wait_for_click(timeout=None)` | Block until a tap completes. |
| `button.wait_for_double_click(timeout=None)` | Block until a double tap. |
| `button.wait_for_long_press(timeout=None)` | Block until a long press. |

```python
print("press the button!")
if board.button.wait_for_press(timeout=5):
    print("pressed")
else:
    print("too slow")
```

### Event handlers

Register any number of handlers per gesture; they are called **with no
arguments** on the button thread.

| Registration | Gesture fires when... |
| --- | --- |
| `on_press(fn)` | the button goes down |
| `on_release(fn)` | the button comes up |
| `on_click(fn)` | tap: press+release shorter than `long_press_time` |
| `on_double_click(fn)` | two taps within `double_click_window` |
| `on_long_press(fn)` | the button has been held for `long_press_time` |

```python
board.button.on_click(lambda: print("tap"))
board.button.on_double_click(lambda: board.speaker.beep(1500))
board.button.on_long_press(lambda: board.led.blink("red"))
```

Notes:

- A long press does **not** also produce a `click` on release.
- When a double-click handler exists, `click` is deferred by
  `double_click_window` so a tap that turns out to be a double tap is
  never reported twice (fires `double_click` only).
- Handlers run on the button thread — keep them quick. Post to a
  `queue.Queue` or set a flag for UI work; see the cookbook.

#### `clear_handlers(event=None)`
Remove handlers for `"press"`, `"release"`, `"click"`, `"double_click"`
or `"long_press"`; `None` removes all.

### Tuning (attributes)

```python
board.button.debounce = 0.03            # s  (bounce filter)
board.button.double_click_window = 0.35 # s  (max gap between taps)
board.button.long_press_time = 0.8      # s  (hold threshold)
board.button.poll_interval = 0.005      # s  (GPIO polling rate)
```

---

## 7. Speaker — `board.speaker`

Drives the onboard 1 W / 8 Ω speaker (and the PH2.0 external-speaker
header) through the `whisplaysound` ALSA card. Uses `aplay` for WAV;
MP3 and friends need `mpg123` or `ffmpeg` installed.

### Playing audio

#### `play(path, blocking=True, volume=None)`
Play a file. Blocking by default (returns `None`); with
`blocking=False` returns a **`Playback`** handle:

```python
pb = board.speaker.play("intro.wav", blocking=False)
pb.wait()          # block until done (optional timeout=seconds -> bool)
pb.done            # finished?
pb.stop()          # stop now
```

`volume=` temporarily sets the speaker volume for this playback and
restores the previous level afterwards.

Supported: `.wav` out of the box; `.mp3` via `sudo apt install mpg123`
(or ffmpeg); anything else via ffmpeg's `ffplay`.

#### `stop()`
Stop the current non-blocking playback.

### Tones & beeps — no audio files needed

#### `play_tone(frequency=440, duration=0.3, volume=0.5, sample_rate=22050, blocking=True)`
Sine-wave tone; `volume` is amplitude 0.0-1.0. Built-in anti-click fades.

```python
board.speaker.play_tone(880, 0.2)          # chime
```

#### `beep(frequency=1000, duration=0.08, count=1, gap=0.06)`
Blocking beeps for UI feedback.

```python
board.speaker.beep(count=2)                # double "bip"
```

#### `Speaker.make_tone_wav(frequency, duration, ...) -> path`
Static helper that just writes the WAV file (useful for building jingles).

### Volume

#### `set_volume(percent)` / `get_volume()`
0-100. ~70 is a sensible everyday level; higher can distort.
Works with both the unified ES8389 driver (`speaker` control) and the
legacy WM8960 driver (`Speaker`/`Playback`).

```python
board.speaker.set_volume(70)
print(board.speaker.get_volume())
```

---

## 8. Microphone — `board.mic`

The two on-board MEMS microphones are one stereo capture device. All
recordings are plain WAV files.

Defaults: `rate=16000` Hz, `channels=2`, format `S32_LE` (what the
official examples use; the mixer gain `mic` defaults to 50 - raise it if
recordings are quiet).

### Recording

#### `record(path=None, duration=5, rate=16000, channels=2) -> path`
Blocking timed recording; returns the WAV path (a temp file if omitted).

```python
clip = board.mic.record(duration=3)
board.speaker.play(clip)
```

#### `start_recording(path=None, rate=16000, channels=2) -> path`
Start in the background; finish with `stop_recording()` (which returns
the path). `is_recording` (property) tells you the state.

```python
board.mic.start_recording("memo.wav")
board.button.wait_for_release()
wav_path = board.mic.stop_recording()
```

#### `record_while_pressed(button, path=None, max_duration=60, ...) -> path`
Press-and-hold dictaphone mode: records while the button is held, stops
on release (or after `max_duration`). Waits for the initial press.

### Gain

#### `set_gain(percent)` / `get_gain()`
Capture gain 0-100 (`mic` control on the unified driver, legacy
`Capture` fallback).

---

## 9. Colours — `whisplaykit.colors`

```python
from whisplaykit import colors
```

| Function | Description |
| --- | --- |
| `colors.NAMED` | dict of ~30 name -> (r,g,b) colours |
| `colors.to_rgb(c)` | normalise any colour spec to (r, g, b) |
| `colors.to_rgb565(c)` | convert to a 16-bit RGB565 int |
| `colors.rgb565_to_rgb(v)` | RGB565 -> (r, g, b) |
| `colors.scale(c, f)` | multiply brightness by factor f |
| `colors.wheel(t)` | rainbow colour at position 0.0-1.0 |

Shortcuts: `colors.RED`, `colors.GREEN`, ... are the plain name strings.

---

## 10. Cookbook

### 10.1 Boot splash → idle screen

```python
with Whisplay(backlight=80) as board:
    board.display.show("logo.png")
    board.led.rainbow(duration=2, blocking=True)
    board.display.fill("black")
    board.display.text_centered("Ready", 130, size=26, refresh=True)
    board.led.pulse("green", period=2.5)
    board.button.wait_for_long_press()     # hold to shut the app down
```

### 10.2 Volume knob (tap = louder, double tap = quieter, hold = mute)

```python
import threading
with Whisplay() as board:
    vol = threading.Event()
    def show():
        v = board.speaker.get_volume() or 0
        board.display.clear(); board.display.progress_bar(
            20, 130, 200, 24, v / 100, label="auto", refresh=True)
    board.button.on_click(lambda: (board.speaker.set_volume(
        min(100, (board.speaker.get_volume() or 0) + 10)), show()))
    board.button.on_double_click(lambda: (board.speaker.set_volume(
        max(0, (board.speaker.get_volume() or 0) - 10)), show()))
    board.button.on_long_press(lambda: (board.speaker.set_volume(0), show()))
    show(); vol.wait()
```

### 10.3 Push-to-talk voice assistant skeleton

```python
with Whisplay() as board:
    while True:
        board.led.pulse("navy")                                # idle
        board.button.wait_for_press()
        board.led.set("red"); board.speaker.beep(660)          # "listening"
        wav = board.mic.start_recording()
        board.button.wait_for_release()
        board.mic.stop_recording()
        board.led.set("purple")                                # "thinking"
        # ... send `wav` to your STT / LLM, get `reply.wav` ...
        board.led.set("green")
        board.speaker.play("reply.wav")
```

### 10.4 Level meter UI loop (partial refresh)

```python
import random, time
with Whisplay() as board:
    d = board.display
    while not board.button.wait_for_long_press(timeout=0.05):
        level = random.random()           # replace with real audio level
        d.rectangle(20, 120, 220, 150, fill_color="black")   # erase bar
        d.progress_bar(20, 120, 200, 30, level, label="auto")
        d.refresh(20, 115, 200, 40)       # push only the bar region
        time.sleep(0.05)
```

### 10.5 Status LED conventions (suggested)

| State | LED |
| --- | --- |
| idle | `pulse("navy", period=3)` |
| listening/recording | solid red |
| thinking/working | `pulse("purple", period=0.7)` |
| success/done | solid green 1 s, then off |
| error | `blink("red", times=3)` |

### 10.6 Playing video

For MP4 on the LCD, decode with ffmpeg and push frames:

```python
# concept: ffmpeg -i clip.mp4 -f rawvideo -pix_fmt rgb565 -s 240x280 -
# then board.display or board._board.draw_image the frames.
```

(The official `example/play_mp4.py` shows a full implementation to copy.)
Keep clips short — SPI is fine for UI, not a GPU.

### 10.7 Developing the UI on your PC (no board attached)

`tests/smoke_test.py` contains a `FakeBoard` you can reuse: construct
`Display(FakeBoard())`, draw, and `save("layout.png")`. All colours,
text layout and shapes behave identically.

---

## 11. Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| `RuntimeError: ... python3-spidev ...` on import | `sudo apt install python3-spidev python3-libgpiod` |
| `RuntimeError: Could not initialise the Whisplay HAT` | Driver not installed/rebooted; HAT not seated; or **whisplay-daemon is holding the hardware**: `sudo systemctl stop whisplay-daemon` |
| Screen shows garbage / stays black | Reboot after `install_driver.sh`; check SPI enabled; backlight `set_brightness` |
| No sound | `aplay -l` must list `whisplaysound`; raise volume `board.speaker.set_volume(70)`; check PiSugar power switch (`AUTO` off — I2C conflict) |
| MP3 errors | `sudo apt install mpg123` (or ffmpeg) |
| Recording is silent | `board.mic.set_gain(70)`+; test with `arecord -D plughw:whisplaysound,0 -f S32_LE -r 16000 -c 2 t.wav` |
| Clicks at tone start/end | Built-in 5 ms fades should prevent this; reduce `volume` amplitude |
| LED colours look wrong/inverted | Never drive pins 16/18/22 manually — always use `board.led` |
| App freezes on exit | Call `board.close()` / use `with`; don't block the button thread in handlers |

Log of the driver state if things get weird: `dmesg | grep -i wm8960` /
`dmesg | grep -i es8389`, and for the daemon `journalctl -u whisplay-daemon`.

---

## 12. Hardware reference

| Function | 40-pin physical pin | Notes |
| --- | --- | --- |
| LCD (ST7789, 240x280) | SPI: MOSI 19, CLK 23, CS 24, DC 13, RST 7 | backlight pin 15, active-low |
| Button | 11 | external pull-down, **pressed = HIGH** |
| RGB LED | R 22, G 18, B 16 | common anode (active-low), soft-PWM |
| Audio codec | I2C 3/5 + I2S 35/38/40 | ES8389 (V2) or WM8960 (V1), card `whisplaysound` |
| Power | 5 V pins 2, 4 | speaker amp supply |

Mixer controls (unified driver): `speaker` 0-100 playback,
`mic` 0-100 capture. Legacy WM8960 mixer: `Speaker`, `Playback`,
`Capture` — the API falls back automatically.

---

Questions this guide doesn't answer? The
[official Whisplay driver repo](https://github.com/PiSugar/Whisplay) and
[PiSugar docs](https://docs.pisugar.com/docs/product-wiki/whisplay/overview)
cover kernel-driver details and the daemon service.
