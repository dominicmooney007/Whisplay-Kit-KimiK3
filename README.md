# whisplay-kit

An easy-to-use Python API for the **PiSugar Whisplay HAT** — built for rapid
prototyping. One object gives you friendly access to every peripheral on
the board:

| Peripheral | Access point | Hardware |
| --- | --- | --- |
| 1.69" LCD, 240x280 | `board.display` | ST7789 over SPI |
| Push button | `board.button` | pin 11, debounced, with gestures |
| RGB LED | `board.led` | pins 22/18/16, soft-PWM |
| Speaker (1 W, 8 Ω) | `board.speaker` | ES8389 / WM8960 ALSA card |
| Dual microphones | `board.mic` | same ALSA card |

## 60-second quick start

```python
from whisplaykit import Whisplay

with Whisplay() as board:
    board.led.pulse("cyan")                                   # breathing LED
    board.display.fill("#101830")
    board.display.text_centered("Hi!", 40, size=30, bold=True)
    board.display.progress_bar(30, 120, 180, 24, 0.4, label="auto")
    board.display.refresh()                                   # push to LCD

    board.button.on_click(lambda: board.speaker.beep())       # beep on tap

    recording = board.mic.record(duration=3)                  # 3 s to WAV
    board.speaker.play(recording)                             # play it back
```

## Installation

**1. Install the official PiSugar driver once** (enables SPI/I2C/I2S and the
sound card), then reboot:

```bash
git clone https://github.com/PiSugar/Whisplay.git --depth 1
cd Whisplay && sudo bash install_driver.sh && sudo reboot
```

**2. Install system packages and whisplay-kit:**

```bash
# Raspberry Pi OS Trixie (Debian 13) / Bookworm:
sudo apt update
sudo apt install python3-spidev python3-libgpiod python3-pil
sudo apt install python3-numpy mpg123 ffmpeg     # optional: speed + MP3

# Then either use a venv that can see system packages (recommended):
python3 -m venv --system-site-packages ~/whisplay-venv
source ~/whisplay-venv/bin/activate
pip install .

# …or install system-wide (Trixie's Python is "externally managed"):
pip install . --break-system-packages

# …or skip install entirely: the examples run in place from this folder.
```

> ✅ **Raspberry Pi 5:** fully supported. whisplay-kit auto-detects the
> Pi 5's GPIO controller by driver label, which works on both old
> (`gpiochip4`) and current (`gpiochip0`, kernel ≥ 6.6.45 incl. Trixie's
> 6.12) kernels.

**3. Run:**

```bash
python3 examples/01_hello_display.py
```

> ⚠️ If you installed the optional `whisplay-daemon` service it owns the
> screen/LED/button — stop it first: `sudo systemctl stop whisplay-daemon`.

## Documentation

**[guide-pi5.html](guide-pi5.html)** — interactive step-by-step setup guide
for students (Raspberry Pi 5 + Trixie). Open it in any browser — it works
offline, includes copy-buttons for every command and explanations of what
each command does.

**[USER_GUIDE.md](USER_GUIDE.md)** — every function of the board, with
parameters, examples and ready-made recipes.

`tests/smoke_test.py` runs the API against a simulated board (no hardware
needed) and renders the framebuffer to PNG — useful for checking layouts on
your PC before deploying.

## Credits

`whisplaykit/_hardware.py` is adapted from the official
[PiSugar/Whisplay](https://github.com/PiSugar/Whisplay) runtime
(Apache-2.0, see [NOTICE](NOTICE)). Everything else is Apache-2.0 too.
