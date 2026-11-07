# Copyright © 2026 Tirhut LLC. All rights reserved.
"""macOS smoke test (run by CI on a real Mac desktop).

Starts GlowLyrics in demo mode and checks, by asking macOS directly, that:
  * the lyrics bar and glow windows join all desktops and show over full-screen apps
  * they don't hide when another app is active
  * a simulated screen lock lifts them above the lock screen, and unlock lowers them again
Exits non-zero if anything is wrong.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])

from Foundation import NSDistributedNotificationCenter  # noqa: E402

from glowlyrics import window_tweaks as wt  # noqa: E402
from glowlyrics.config import Config  # noqa: E402
from glowlyrics.controller import Controller  # noqa: E402
from glowlyrics.legal import LICENSE_VERSION  # noqa: E402

cfg = Config(reset=True)
cfg.set("license_accepted", LICENSE_VERSION)
cfg.set("first_run", False)
cfg.set("demo", True)
cfg.set("lock_screen", True)
ctrl = Controller(cfg)

failures = []
WANT_BEHAVIOR = (wt._CAN_JOIN_ALL_SPACES | wt._STATIONARY | wt._IGNORES_CYCLE |
                 wt._FULLSCREEN_AUXILIARY)


def windows():
    return [("lyrics bar", ctrl.overlay)] + [(f"glow {e}", w) for e, w in ctrl.glow.strips.items()
                                             if w.isVisible()]


def check(label, want_level):
    for name, w in windows():
        nsw = wt._nswindow(w)
        if nsw is None:
            failures.append(f"{label}: {name}: no native window")
            continue
        beh, lvl, hides = int(nsw.collectionBehavior()), int(nsw.level()), bool(nsw.hidesOnDeactivate())
        print(f"{label:9s} {name:12s} behavior={beh:#06x} level={lvl} hidesOnDeactivate={hides}")
        if beh & WANT_BEHAVIOR != WANT_BEHAVIOR:
            failures.append(f"{label}: {name}: collection behavior {beh:#x}")
        if hides:
            failures.append(f"{label}: {name}: hides on deactivate")
        if lvl != want_level:
            failures.append(f"{label}: {name}: level {lvl}, expected {want_level}")


def post(name):
    NSDistributedNotificationCenter.defaultCenter() \
        .postNotificationName_object_userInfo_deliverImmediately_(name, None, None, True)


def step1():
    if not ctrl.overlay.isVisible() or not ctrl.glow.visible:
        failures.append("lyrics bar or glow not visible in demo mode")
    check("normal", wt._NS_STATUS_WINDOW_LEVEL)
    post("com.apple.screenIsLocked")
    QTimer.singleShot(2000, step2)


def step2():
    if not ctrl.lock.locked:
        failures.append("lock notification not received")
    check("locked", wt._shielding_level() + 1)
    post("com.apple.screenIsUnlocked")
    QTimer.singleShot(2000, step3)


def step3():
    if ctrl.lock.locked:
        failures.append("unlock notification not received")
    check("unlocked", wt._NS_STATUS_WINDOW_LEVEL)
    print("\nRESULT:", "PASS" if not failures else "FAIL")
    for f in failures:
        print("  -", f)
    ctrl.quit()
    app.exit(1 if failures else 0)


QTimer.singleShot(6000, step1)  # let demo playback start and windows appear
QTimer.singleShot(60000, lambda: (print("timeout"), app.exit(2)))
start = time.time()
sys.exit(app.exec())
