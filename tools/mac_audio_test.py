# Copyright © 2026 Tirhut LLC. All rights reserved.
"""macOS beat-sync check (CI, informational): plays a 120 BPM drum track with `afplay`
and checks that ScreenCaptureKit system-audio capture detects the beats."""
import os
import subprocess
import sys
import tempfile
import time
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])   # needed for the main run loop that delivers callbacks

from glowlyrics.audio import BeatDetector  # noqa: E402
from glowlyrics.mac_audio import AVAILABLE, MacSystemAudio  # noqa: E402

SR, DUR, BPM = 48000, 10, 120
t = np.arange(SR * DUR) / SR
sig = 0.05 * np.sin(2 * np.pi * 440 * t)
for k in range(int(DUR * BPM / 60)):
    s, n = int(k * 60 / BPM * SR), int(0.12 * SR)
    sig[s:s + n] += 0.7 * np.sin(2 * np.pi * 60 * np.arange(n) / SR) * np.exp(-np.arange(n) / SR * 30)
path = os.path.join(tempfile.gettempdir(), "glowlyrics_kicks.wav")
with wave.open(path, "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((np.clip(sig, -1, 1) * 32767).astype(np.int16).tobytes())

print("ScreenCaptureKit available:", AVAILABLE)
det = BeatDetector()
cap = MacSystemAudio(det.feed)
cap.start()
player = {"p": None}


def begin():
    print("capture running:", cap.running, "| error:", cap.error or "-", "| denied:", cap.denied)
    player["p"] = subprocess.Popen(["afplay", path])
    QTimer.singleShot(int(DUR * 1000) + 1500, finish)


def finish():
    cap.stop()
    if player["p"]:
        player["p"].terminate()
    heard = time.monotonic() - det.last_audio < 5 if det.last_audio else False
    print(f"audio heard: {heard} | beats detected: {det.beats} (played {int(DUR * BPM / 60)})")
    ok = cap.error == "" and det.beats >= int(DUR * BPM / 60) * 0.6
    print("BEAT TEST:", "PASS" if ok else "NOT VERIFIED (CI machine may lack audio device or permission)")
    app.exit(0)


QTimer.singleShot(3000, begin)
QTimer.singleShot(40000, lambda: (print("timeout"), app.exit(0)))
sys.exit(app.exec())
