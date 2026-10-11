"""Speaker and microphone API for the Whisplay HAT.

Audio on Whisplay is a real Linux sound card (ES8389 on new boards,
WM8960 on V1) once the official PiSugar driver is installed. This module
drives it through the standard ALSA command line tools, which keeps
dependencies tiny and behaviour identical to the official examples:

* playback:  ``aplay`` (WAV, always present), ``mpg123`` / ``ffplay``
  (MP3 etc., if installed)
* recording: ``arecord``
* volume:    ``amixer`` (control ``speaker``/``mic`` on the unified
  driver, falling back to legacy WM8960 control names)

The card is addressed by its stable name ``whisplaysound`` so card
index changes between boots do not matter.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import signal
import struct
import subprocess
import tempfile
import time
import wave


class AudioError(RuntimeError):
    """Raised when a playback/recording action cannot be performed."""


# ---------------------------------------------------------------------------
# Sound-card discovery
# ---------------------------------------------------------------------------
def find_card():
    """Return the ALSA card name (``"whisplaysound"`` ...) or ``None``."""
    try:
        with open("/proc/asound/cards", "r", encoding="utf-8") as fp:
            fallback = None
            for line in fp:
                lower = line.lower()
                parts = line.strip().split()
                if not parts or not parts[0].isdigit():
                    continue
                if "whisplaysound" in lower:
                    return "whisplaysound"
                if fallback is None and ("wm8960" in lower or "es8389" in lower):
                    fallback = parts[1].strip("[]:") if len(parts) > 1 else None
            return fallback
    except FileNotFoundError:
        return None


def audio_available() -> bool:
    """True when the Whisplay sound card is present."""
    return find_card() is not None


def alsa_device() -> str:
    """The ``plughw:`` device string used for playback and capture."""
    card = find_card()
    return f"plughw:CARD={card}" if card else "default"


def _run(cmd, env=None):
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


# ---------------------------------------------------------------------------
# Playback handle
# ---------------------------------------------------------------------------
class Playback:
    """Handle returned by non-blocking playback calls."""

    def __init__(self, proc, cleanup_path=None):
        self._proc = proc
        self._cleanup_path = cleanup_path

    @property
    def done(self) -> bool:
        """True when playback has finished."""
        return self._proc.poll() is not None

    def wait(self, timeout=None) -> bool:
        """Block until playback ends. Returns True, or False on timeout."""
        try:
            self._proc.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False
        finally:
            self._cleanup()

    def stop(self):
        """Stop playback immediately."""
        try:
            if self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
        finally:
            self._cleanup()

    def _cleanup(self):
        if self._cleanup_path is not None and self.done:
            _silent_unlink(self._cleanup_path)
            self._cleanup_path = None


# ---------------------------------------------------------------------------
# Speaker
# ---------------------------------------------------------------------------
class Speaker:
    """The onboard 1W speaker (and any PH2.0 external speaker).

    Created for you by :class:`whisplaykit.Whisplay` as ``board.speaker``.
    """

    def __init__(self):
        self._current = None  # active Playback, if any

    # ------------------------------------------------------------------
    # Playing files
    # ------------------------------------------------------------------
    def play(self, path, blocking=True, volume=None):
        """Play an audio file.

        WAV always works. MP3 requires ``mpg123`` (``sudo apt install
        mpg123``) or ``ffmpeg``. Returns ``None`` when ``blocking=True``,
        otherwise a :class:`Playback` handle with ``wait()`` / ``stop()``.

        :param volume: optionally set speaker volume (0-100) just for this
                       playback. The previous volume is restored after.
        """
        if not os.path.exists(path):
            raise AudioError(f"Audio file not found: {path}")
        cmd, env = self._play_cmd(path)
        if volume is not None:
            old = self.get_volume()
            self.set_volume(volume)
            if blocking:
                try:
                    return self._run_blocking(cmd, env)
                finally:
                    if old is not None:
                        self.set_volume(old)
            proc = self._spawn(cmd, env)
            speaker = self

            class _RestoringPlayback(Playback):
                def wait(self, timeout=None):
                    ok = super().wait(timeout)
                    if old is not None:
                        speaker.set_volume(old)
                    return ok

            pb = _RestoringPlayback(proc)
            self._current = pb
            return pb
        if blocking:
            return self._run_blocking(cmd, env)
        self._current = Playback(self._spawn(cmd, env))
        return self._current

    @staticmethod
    def _run_blocking(cmd, env):
        subprocess.run(cmd, capture_output=True, env=env)
        return None

    # ------------------------------------------------------------------
    # Tones
    # ------------------------------------------------------------------
    def play_tone(self, frequency=440, duration=0.3, volume=0.5,
                  sample_rate=22050, blocking=True):
        """Play a sine-wave beep at ``frequency`` Hz for ``duration``
        seconds. ``volume`` is 0.0-1.0 (tone amplitude). The temporary WAV
        file is deleted automatically."""
        path = self.make_tone_wav(frequency, duration, volume, sample_rate)
        if blocking:
            try:
                return self.play(path, blocking=True)
            finally:
                _silent_unlink(path)
        cmd, env = self._play_cmd(path)
        self._current = Playback(self._spawn(cmd, env), cleanup_path=path)
        return self._current

    def beep(self, frequency=1000, duration=0.08, count=1, gap=0.06):
        """Simple blocking beeps — handy for UI feedback."""
        for i in range(count):
            self.play_tone(frequency, duration)
            if i < count - 1:
                time.sleep(gap)

    @staticmethod
    def make_tone_wav(frequency, duration, volume=0.5, sample_rate=22050):
        """Generate a sine WAV file (with anti-click fades) and return its
        path. Useful standalone too."""
        n_frames = int(sample_rate * duration)
        amp = int(32767 * max(0.0, min(1.0, volume)))
        fade = max(1, int(sample_rate * 0.005))  # 5 ms fade in/out
        frames = bytearray()
        for n in range(n_frames):
            gain = min(1.0, n / fade, (n_frames - n) / fade)
            value = int(amp * gain * math.sin(2 * math.pi * frequency * n
                                              / sample_rate))
            frames += struct.pack("<h", value)
        fd, path = tempfile.mkstemp(prefix="whisplaykit_tone_", suffix=".wav")
        with os.fdopen(fd, "wb") as raw:
            with wave.open(raw, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)
                wav.writeframes(bytes(frames))
        return path

    def stop(self):
        """Stop any non-blocking playback started via this object."""
        if self._current is not None:
            self._current.stop()
            self._current = None

    # ------------------------------------------------------------------
    # Volume
    # ------------------------------------------------------------------
    def set_volume(self, percent):
        """Set speaker volume 0-100. Around 70 is a good everyday level;
        higher can distort. Returns True when a mixer control accepted
        the value."""
        return _set_mixer_volume(percent, capture=False)

    def get_volume(self):
        """Current speaker volume 0-100, or ``None`` if not available."""
        return _get_mixer_volume(capture=False)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _play_cmd(self, path):
        dev = alsa_device()
        ext = os.path.splitext(path)[1].lower()
        if ext in (".wav", ".wave", ".voc", ".raw"):
            return ["aplay", "-q", "-D", dev, path], None
        if ext == ".mp3" and shutil.which("mpg123"):
            return ["mpg123", "-q", "-o", "alsa", "-a", dev, path], None
        if shutil.which("ffplay"):
            env = dict(os.environ, AUDIODEV=dev)
            return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
                    path], env
        if ext == ".mp3":
            raise AudioError(
                "MP3 playback needs mpg123 or ffmpeg: "
                "sudo apt install mpg123  (or ffmpeg)")
        raise AudioError(
            f"No player found for {ext or 'this file'}: install ffmpeg "
            "(sudo apt install ffmpeg) or convert to WAV.")

    @staticmethod
    def _spawn(cmd, env):
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, env=env)


# ---------------------------------------------------------------------------
# Microphone
# ---------------------------------------------------------------------------
class Microphone:
    """The Whisplay dual microphones (recorded as one stereo stream).

    Created for you by :class:`whisplaykit.Whisplay` as ``board.mic``.
    Recordings are standard WAV files you can feed to speech-to-text or
    play straight back through :class:`Speaker`.
    """

    DEFAULT_RATE = 16000   # sensible default for speech apps
    DEFAULT_CHANNELS = 2   # Whisplay has two mics (L/R)
    DEFAULT_FORMAT = "S32_LE"

    def __init__(self):
        self._proc = None
        self._path = None

    # ------------------------------------------------------------------
    # Blocking recording
    # ------------------------------------------------------------------
    def record(self, path=None, duration=5, rate=DEFAULT_RATE,
               channels=DEFAULT_CHANNELS):
        """Record ``duration`` seconds to a WAV file and return its path.

        :param path: output file; a temp file is created when omitted.
        """
        path = path or self._temp_wav()
        cmd = self._arecord_cmd(path, rate, channels, duration=duration)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise AudioError(f"arecord failed: {proc.stderr.strip() or proc.returncode}")
        return path

    # ------------------------------------------------------------------
    # Non-blocking recording
    # ------------------------------------------------------------------
    def start_recording(self, path=None, rate=DEFAULT_RATE,
                        channels=DEFAULT_CHANNELS):
        """Start recording in the background; returns the file path.
        Finish with :meth:`stop_recording`."""
        if self._proc is not None:
            raise AudioError("Already recording - call stop_recording() first")
        path = path or self._temp_wav()
        self._proc = subprocess.Popen(
            self._arecord_cmd(path, rate, channels),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._path = path
        return path

    def stop_recording(self):
        """Stop a background recording and return the finished WAV path
        (``None`` if nothing was recording)."""
        proc, path = self._proc, self._path
        self._proc = self._path = None
        if proc is None:
            return None
        if proc.poll() is None:
            # SIGINT lets arecord finalise WAV headers cleanly
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.terminate()
        else:
            proc.wait()
        return path

    @property
    def is_recording(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # ------------------------------------------------------------------
    # Button-driven recording
    # ------------------------------------------------------------------
    def record_while_pressed(self, button, path=None, max_duration=60,
                             rate=DEFAULT_RATE, channels=DEFAULT_CHANNELS):
        """Press-and-hold dictaphone style: starts when the button is
        pressed (waits for it), records while held, stops on release or
        after ``max_duration`` seconds. Returns the WAV path."""
        if not button.is_pressed:
            if not button.wait_for_press():
                return None  # pragma: no cover - wait_for_press blocking
        path = self.start_recording(path, rate=rate, channels=channels)
        started = time.monotonic()
        while button.is_pressed and \
                (time.monotonic() - started) < max_duration:
            time.sleep(0.01)
        self.stop_recording()
        return path

    # ------------------------------------------------------------------
    # Mic gain
    # ------------------------------------------------------------------
    def set_gain(self, percent):
        """Set capture (mic) gain 0-100."""
        return _set_mixer_volume(percent, capture=True)

    def get_gain(self):
        """Current capture gain 0-100, or ``None`` if not available."""
        return _get_mixer_volume(capture=True)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _arecord_cmd(self, path, rate, channels, duration=None):
        cmd = ["arecord", "-q", "-D", alsa_device(),
               "-f", self.DEFAULT_FORMAT, "-r", str(int(rate)),
               "-c", str(int(channels)), "-t", "wav"]
        if duration is not None:
            cmd += ["-d", str(int(math.ceil(duration)))]
        cmd.append(path)
        return cmd

    @staticmethod
    def _temp_wav():
        fd, path = tempfile.mkstemp(prefix="whisplaykit_rec_", suffix=".wav")
        os.close(fd)
        return path


# ---------------------------------------------------------------------------
# Mixer helpers (unified driver names first, legacy WM8960 fallback)
# ---------------------------------------------------------------------------
def _mixer_card():
    return find_card() or "whisplaysound"


def _set_mixer_volume(percent, capture):
    percent = int(max(0, min(100, percent)))
    card = _mixer_card()
    if capture:
        attempts = [
            ["amixer", "-c", card, "cset", "name=mic", str(percent)],
            ["amixer", "-c", card, "sset", "Capture", f"{percent}%"],
        ]
    else:
        attempts = [
            ["amixer", "-c", card, "cset", "name=speaker", str(percent)],
            ["amixer", "-c", card, "sset", "Speaker", f"{percent}%"],
            ["amixer", "-c", card, "sset", "Playback", f"{percent}%"],
        ]
    for cmd in attempts:
        try:
            if _run(cmd).returncode == 0:
                return True
        except FileNotFoundError:
            raise AudioError(
                "amixer not found - install alsa-utils "
                "(sudo apt install alsa-utils)")
    return False


def _get_mixer_volume(capture):
    card = _mixer_card()
    cget_names = ["mic", "Capture"] if capture else ["speaker", "Speaker"]
    sget_name = "Capture" if capture else "Speaker"
    for name in cget_names:
        try:
            out = _run(["amixer", "-c", card, "cget", f"name={name}"])
        except FileNotFoundError:
            return None
        if out.returncode == 0:
            m = re.search(r"values=(\d+)", out.stdout)
            if m:
                return int(m.group(1))
    try:
        out = _run(["amixer", "-c", card, "sget", sget_name])
    except FileNotFoundError:
        return None
    if out.returncode == 0:
        m = re.search(r"\[(\d+)%\]", out.stdout)
        if m:
            return int(m.group(1))
    return None


def _silent_unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass
