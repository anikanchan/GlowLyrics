# Copyright © 2026 Tirhut LLC. All rights reserved.
"""Listens to the computer's audio output (never the microphone) to find the beat.

  Windows / Linux : loopback capture of the default output device (soundcard)
  macOS 13+       : ScreenCaptureKit system-audio capture (needs one-time permission)

Audio is analysed in memory and immediately discarded.
"""
import logging
import math
import sys
import threading
import time
import warnings
from collections import deque

log = logging.getLogger("glowlyrics")


class BeatDetector:
    """Turns raw mono float samples (any chunk size) into a level and beat times."""

    BLOCK = 1024

    def __init__(self):
        import numpy as np
        self.np = np
        self.window = np.hanning(self.BLOCK)
        self.hist = deque(maxlen=46)        # ~1 s of bass energy
        self.peak = 1e-3
        self.level = 0.0
        self.beat_time = 0.0
        self.beats = 0                      # total beats seen (diagnostics / tests)
        self.last_audio = 0.0               # when non-silent audio last arrived
        self._buf = np.zeros(0, dtype=np.float32)
        self._last_beat = 0.0

    def feed(self, samples):
        np = self.np
        if samples is None or len(samples) == 0:
            return
        self._buf = np.concatenate([self._buf, np.asarray(samples, dtype=np.float32)])
        while len(self._buf) >= self.BLOCK:
            block, self._buf = self._buf[: self.BLOCK], self._buf[self.BLOCK:]
            self._analyse(block)
        if len(self._buf) > self.BLOCK * 8:   # never let a backlog grow
            self._buf = self._buf[-self.BLOCK:]

    def _analyse(self, mono):
        np = self.np
        rms = float(np.sqrt(np.mean(mono ** 2)))
        now = time.monotonic()
        if rms > 0.002:
            self.last_audio = now
        self.peak = max(rms, self.peak * 0.998, 1e-3)
        self.level = self.level * 0.6 + min(1.0, rms / self.peak) * 0.4
        spec = np.abs(np.fft.rfft(mono * self.window))
        bass = float(spec[1:7].sum())      # ~40-280 Hz
        avg = (sum(self.hist) / len(self.hist)) if self.hist else bass
        if (len(self.hist) > 10 and bass > avg * 1.45 and bass > 0.5 and
                now - self._last_beat > 0.27 and rms > 0.004):
            self._last_beat = now
            self.beat_time = now
            self.beats += 1
        self.hist.append(bass)


class AudioAnalyzer(threading.Thread):
    RATE = 44100

    def __init__(self):
        super().__init__(daemon=True)
        self.available = False
        self.status = "Starting audio…"
        self.needs_permission = False      # macOS: Screen & System Audio Recording missing
        self.active = False                # set by the controller; capture stops when False
        self._running = True
        self.det = None

    # --- values read by the glow -------------------------------------------------------
    @property
    def level(self):
        return self.det.level if self.det else 0.0

    def pulse(self):
        """0..1, spikes to 1 on each beat and decays."""
        if not self.det:
            return 0.0
        return math.exp(-(time.monotonic() - self.det.beat_time) * 5.5)

    def hearing_audio(self):
        """True if real (non-silent) audio arrived in the last couple of seconds."""
        return bool(self.det) and time.monotonic() - self.det.last_audio < 2.5

    def stop(self):
        self._running = False

    def run(self):
        try:
            self.det = BeatDetector()
        except Exception as e:
            self.status = f"numpy missing ({e.__class__.__name__}); glow follows the lyrics instead."
            return
        if sys.platform == "darwin":
            self._run_mac()
        else:
            self._run_loopback()

    # --- macOS --------------------------------------------------------------------------
    def _run_mac(self):
        from . import mac_audio
        if not mac_audio.AVAILABLE:
            self.status = ("System-audio capture needs macOS 13 or newer; the glow follows the "
                           "lyrics' rhythm instead.")
            return
        cap = mac_audio.MacSystemAudio(self.det.feed)
        self.status = "Beat sync starts when music plays."
        while self._running:
            if self.active and not cap.running and not cap.denied:
                cap.start()
                for _ in range(30):            # wait for the async start / permission answer
                    time.sleep(0.1)
                    if cap.running or cap.error:
                        break
            elif not self.active and cap.running:
                cap.stop()
            self.available = cap.running
            self.needs_permission = cap.denied
            if cap.denied:
                self.status = mac_audio.PERMISSION_HELP
            elif cap.running:
                self.status = "Listening to system audio (ScreenCaptureKit)."
            elif cap.error:
                self.status = f"System audio unavailable ({cap.error[:80]}); glow follows the lyrics."
            time.sleep(0.25)
        cap.stop()

    # --- Windows / Linux ----------------------------------------------------------------
    def _run_loopback(self):
        try:
            import soundcard as sc
        except Exception as e:
            self.status = f"Audio library missing ({e.__class__.__name__}); glow follows the lyrics."
            return
        warnings.filterwarnings("ignore")
        while self._running:
            if not self.active:  # nothing needs the beat: don't touch the audio device
                time.sleep(0.25)
                continue
            try:
                speaker = sc.default_speaker()
                mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
                self.available = True
                self.status = f"Listening to: {speaker.name}"
                started = time.monotonic()
                with mic.recorder(samplerate=self.RATE, channels=2, blocksize=1024) as rec:
                    while self._running and self.active and time.monotonic() - started < 30:
                        data = rec.record(numframes=1024)
                        if data is not None and len(data):
                            self.det.feed(data.mean(axis=1) if data.ndim > 1 else data)
            except Exception as e:
                self.available = False
                self.status = f"System audio unavailable ({e.__class__.__name__}); glow follows the lyrics."
                log.debug("audio error: %s", e)
                for _ in range(50):
                    if not self._running:
                        return
                    time.sleep(0.1)
