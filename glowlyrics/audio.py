# Copyright © 2026 Tirhut LLC. All rights reserved.
"""Listens to system audio output (loopback, never the microphone) to find the beat."""
import logging
import math
import sys
import threading
import time
import warnings
from collections import deque

log = logging.getLogger("glowlyrics")


class AudioAnalyzer(threading.Thread):
    RATE = 44100
    BLOCK = 1024

    def __init__(self):
        super().__init__(daemon=True)
        self.available = False
        self.status = "Starting audio…"
        self.level = 0.0
        self._beat_time = 0.0
        self._running = True
        self.active = False   # set by the controller; capture stops when False

    def stop(self):
        self._running = False

    def pulse(self):
        """0..1, spikes to 1 on each beat and decays."""
        return math.exp(-(time.monotonic() - self._beat_time) * 5.5)

    def run(self):
        if sys.platform == "darwin":
            self.status = ("Beat sync on macOS needs a loopback device (e.g. BlackHole). "
                           "Using a smooth idle glow instead.")
            return
        try:
            import numpy as np
            import soundcard as sc
        except Exception as e:
            self.status = f"Audio library missing ({e.__class__.__name__}); using idle glow."
            return
        warnings.filterwarnings("ignore")
        while self._running:
            if not self.active:  # nothing needs the beat: don't touch the audio device
                self.level = 0.0
                time.sleep(0.25)
                continue
            try:
                speaker = sc.default_speaker()
                mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
                self.available = True
                self.status = f"Listening to: {speaker.name}"
                self._loop(mic, np)
            except Exception as e:
                self.available = False
                self.status = f"System audio unavailable ({e.__class__.__name__}); using idle glow."
                log.debug("audio error: %s", e)
                for _ in range(50):
                    if not self._running:
                        return
                    time.sleep(0.1)

    def _loop(self, mic, np):
        hist = deque(maxlen=43)  # ~1 second of bass energy
        peak = 1e-3
        window = np.hanning(self.BLOCK)
        last_beat = 0.0
        started = time.monotonic()
        with mic.recorder(samplerate=self.RATE, channels=2, blocksize=self.BLOCK) as rec:
            while self._running and self.active:
                data = rec.record(numframes=self.BLOCK)
                if data is None or len(data) == 0:
                    continue
                mono = data.mean(axis=1) if data.ndim > 1 else data
                if len(mono) < self.BLOCK:
                    mono = np.pad(mono, (0, self.BLOCK - len(mono)))
                mono = mono[: self.BLOCK]
                rms = float(np.sqrt(np.mean(mono ** 2)))
                peak = max(rms, peak * 0.998, 1e-3)
                self.level = self.level * 0.6 + min(1.0, rms / peak) * 0.4
                spec = np.abs(np.fft.rfft(mono * window))
                bass = float(spec[1:7].sum())  # ~40-260 Hz
                avg = (sum(hist) / len(hist)) if hist else bass
                now = time.monotonic()
                if (len(hist) > 10 and bass > avg * 1.45 and bass > 0.5 and
                        now - last_beat > 0.27 and rms > 0.004):
                    last_beat = now
                    self._beat_time = now
                hist.append(bass)
                # stop when no longer needed; periodically re-check default output device
                if not self.active or now - started > 30:
                    return
