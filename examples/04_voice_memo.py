#!/usr/bin/env python3
"""Voice memo: hold the button to record, release to hear it back.

Long-press exits. Screen, LED, button, mic and speaker all work together.

    python3 examples/04_voice_memo.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from whisplaykit import Whisplay     # noqa: E402
from whisplaykit.audio import audio_available  # noqa: E402

MEMO_PATH = os.path.expanduser("~/whisplay_memo.wav")
EXIT_AFTER = 0  # use a flag instead of closing inside a handler


def show_idle(board):
    d = board.display
    d.clear("#101830")
    d.text_centered("VOICE MEMO", 40, size=22, color="cyan", bold=True)
    d.text_centered("hold to record", 120, size=18)
    d.text_centered("long press to exit", 240, size=13, color="gray")
    d.refresh()


def main():
    if not audio_available():
        print("Whisplay sound card not found - install the driver first:")
        print("  https://github.com/PiSugar/Whisplay (install_driver.sh)")
        sys.exit(1)

    with Whisplay(backlight=70) as board:
        board.speaker.set_volume(70)
        board.mic.set_gain(50)
        exit_requested = []
        board.button.on_long_press(lambda: exit_requested.append(True))
        show_idle(board)
        print("Hold the Whisplay button to record. Long press exits.")

        while not exit_requested:
            if not board.button.wait_for_press(timeout=0.2):
                continue
            if exit_requested:
                break

            # --- recording phase -------------------------------------
            board.led.set("red")
            d = board.display
            d.clear("#301010")
            d.text_centered("RECORDING", 40, size=22, color="red", bold=True)
            path = board.mic.start_recording(MEMO_PATH)
            started = time.monotonic()
            while board.button.is_pressed:
                elapsed = time.monotonic() - started
                d.rectangle(60, 120, 180, 150, fill_color="#301010")
                d.text_centered(f"{elapsed:4.1f}s", 124, size=22)
                d.refresh()
                time.sleep(0.1)  # 10 fps UI is plenty here
            board.mic.stop_recording()

            # --- playback phase --------------------------------------
            board.led.set("green")
            d.clear("#103010")
            d.text_centered("PLAYING BACK", 40, size=20, color="green",
                            bold=True)
            d.refresh()
            board.speaker.play(path)      # blocking playback
            time.sleep(0.3)
            board.led.off()
            show_idle(board)

        print("bye!")


if __name__ == "__main__":
    main()
