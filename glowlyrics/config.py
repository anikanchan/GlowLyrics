# Copyright © 2026 Tirhut LLC. All rights reserved.
"""Persistent settings stored as JSON in the user's app-data folder."""
import copy
import json
import os

from PySide6.QtCore import QObject, QTimer, Signal

from .system import app_dir

STYLES = ["Karaoke", "Pop", "Lens", "Wall", "Visual"]
COLOR_MODES = ["Album art", "Screen colors", "Manual"]
GLOW_ANIMATIONS = ["Beat", "Idle glow"]

DEFAULTS = {
    # Lyrics
    "show_lyrics": True,
    "lyrics_style": "Karaoke",
    "font_family": "",
    "font_size": 34,
    "overlay_bg": 0.35,
    "overlay_locked": False,
    "overlay_geometry": None,
    "offset_ms": 0,            # positive = lyrics later
    "hide_when_idle": True,
    # Glow
    "glow_enabled": True,
    "glow_edges": ["top", "bottom", "left", "right"],
    "glow_thickness": 6,
    "glow_spread": 70,
    "glow_intensity": 0.9,
    "glow_animation": "Beat",
    "glow_only_playing": True,
    "glow_screen": 0,
    # Colors
    "color_mode": "Album art",
    "color_glow1": "#ff3d7f",
    "color_glow2": "#7a5cff",
    "color_lyric": "#ffffff",
    "color_highlight": "#ffd23f",
    "color_secondary": "#9aa0b4",
    # Stage (full-screen lyrics)
    "stage_idle_enabled": False,
    "stage_idle_minutes": 5,
    "stage_clock": True,
    "keep_awake": True,
    "lock_screen": True,
    "mac_audio_explained": False,       # Mac: show lyrics + glow on the lock screen
    # Misc
    "demo": False,
    "first_run": True,
    "license_accepted": "",
}


class Config(QObject):
    changed = Signal(str)

    def __init__(self, reset=False):
        super().__init__()
        self.path = os.path.join(app_dir(), "settings.json")
        self.data = copy.deepcopy(DEFAULTS)
        if not reset and os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                for k, v in saved.items():
                    if k in DEFAULTS:
                        self.data[k] = v
            except Exception:
                pass
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(700)
        self._timer.timeout.connect(self.save)

    def __getitem__(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        if self.data.get(key) == value:
            return
        self.data[key] = value
        self._timer.start()
        self.changed.emit(key)

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            pass
