# Copyright © 2026 Tirhut LLC. All rights reserved.
"""Settings window."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QFontComboBox,
                               QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QPushButton, QSlider, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from . import COPYRIGHT, __version__
from .config import COLOR_MODES, GLOW_ANIMATIONS, STYLES
from .system import open_folder


class SettingsWindow(QWidget):
    def __init__(self, ctrl):
        super().__init__(None)
        self.ctrl = ctrl
        self.cfg = ctrl.cfg
        self.setWindowTitle("GlowLyrics Settings")
        self.setWindowIcon(ctrl.icon)
        self.resize(560, 600)
        lay = QVBoxLayout(self)

        self.now = QLabel()
        self.now.setWordWrap(True)
        self.now.setStyleSheet("padding:10px;border-radius:10px;background:rgba(127,127,127,0.12);")
        lay.addWidget(self.now)

        tabs = QTabWidget()
        tabs.addTab(self._lyrics_tab(), "Lyrics")
        tabs.addTab(self._glow_tab(), "Glow")
        tabs.addTab(self._colors_tab(), "Colors")
        tabs.addTab(self._stage_tab(), "Stage")
        tabs.addTab(self._about_tab(), "About")
        lay.addWidget(tabs)

        row = QHBoxLayout()
        b_stage = QPushButton("Open Stage (full screen)")
        b_stage.clicked.connect(lambda: ctrl.open_stage())
        b_hide = QPushButton("Hide to tray" if ctrl.tray else "Close")
        b_hide.clicked.connect(self.close)
        b_quit = QPushButton("Quit")
        b_quit.clicked.connect(ctrl.quit)
        row.addWidget(b_stage)
        row.addStretch()
        row.addWidget(b_hide)
        row.addWidget(b_quit)
        lay.addLayout(row)

    # ------------------------------------------------------------ widgets bound to config
    def check(self, key, text):
        w = QCheckBox(text)
        w.setChecked(bool(self.cfg[key]))
        w.toggled.connect(lambda v: self.cfg.set(key, bool(v)))
        self.cfg.changed.connect(lambda k: k == key and w.setChecked(bool(self.cfg[key])))
        return w

    def combo(self, key, items):
        w = QComboBox()
        w.addItems(items)
        if self.cfg[key] in items:
            w.setCurrentText(self.cfg[key])
        w.currentTextChanged.connect(lambda v: self.cfg.set(key, v))
        self.cfg.changed.connect(lambda k: k == key and w.setCurrentText(self.cfg[key]))
        return w

    def slider(self, key, lo, hi, scale=1.0, suffix=""):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(int(round(self.cfg[key] * scale)))
        lab = QLabel()
        lab.setMinimumWidth(52)

        def upd(v):
            lab.setText(f"{v}{suffix}")
            self.cfg.set(key, v / scale if scale != 1.0 else int(v))
        s.valueChanged.connect(upd)
        lab.setText(f"{s.value()}{suffix}")
        self.cfg.changed.connect(lambda k: k == key and s.setValue(int(round(self.cfg[key] * scale))))
        h.addWidget(s)
        h.addWidget(lab)
        return box

    def color_btn(self, key, label):
        b = QPushButton(label)

        def paint():
            c = self.cfg[key]
            txt = "#000" if QColor(c).lightnessF() > 0.6 else "#fff"
            b.setStyleSheet(f"background:{c};color:{txt};padding:6px;border-radius:6px;")

        def pick():
            c = QColorDialog.getColor(QColor(self.cfg[key]), self, label)
            if c.isValid():
                self.cfg.set(key, c.name())
                if self.cfg["color_mode"] != "Manual":
                    self.cfg.set("color_mode", "Manual")
        b.clicked.connect(pick)
        self.cfg.changed.connect(lambda k: k == key and paint())
        paint()
        return b

    # ------------------------------------------------------------ tabs
    def _lyrics_tab(self):
        w = QWidget()
        f = QFormLayout(w)
        f.addRow(self.check("show_lyrics", "Show floating lyrics"))
        f.addRow("Style", self.combo("lyrics_style", STYLES))
        style_help = QLabel("Karaoke: classic lines · Pop: one word at a time · Lens: fisheye "
                            "scroll · Wall: 3D drifting stack · Visual: emoji beside words")
        style_help.setWordWrap(True)
        style_help.setStyleSheet("color:gray;font-size:11px;")
        f.addRow("", style_help)
        fc = QFontComboBox()
        if self.cfg["font_family"]:
            fc.setCurrentFont(QFont(self.cfg["font_family"]))
        else:
            from PySide6.QtWidgets import QApplication
            fc.setCurrentFont(QApplication.font())
        fc.currentFontChanged.connect(lambda font: self.cfg.set("font_family", font.family()))
        f.addRow("Font", fc)
        f.addRow("Text size", self.slider("font_size", 14, 96, suffix=" px"))
        f.addRow("Background", self.slider("overlay_bg", 0, 100, scale=100, suffix="%"))
        f.addRow(self.check("overlay_locked", "Lock position (click-through)"))
        f.addRow(self.check("hide_when_idle", "Hide when nothing is playing"))
        off = QSpinBox()
        off.setRange(-5000, 5000)
        off.setSingleStep(100)
        off.setSuffix(" ms")
        off.setValue(int(self.cfg["offset_ms"]))
        off.valueChanged.connect(lambda v: self.cfg.set("offset_ms", int(v)))
        self.cfg.changed.connect(lambda k: k == "offset_ms" and off.setValue(int(self.cfg["offset_ms"])))
        f.addRow("Timing offset", off)
        tip = QLabel("Positive = lyrics later. Drag the lyrics bar to move it, drag the corner to "
                     "resize, scroll to change size, double-click for Stage, right-click for menu.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:gray;font-size:11px;")
        f.addRow(tip)
        b = QPushButton("Open local lyrics folder (.lrc files)")
        b.clicked.connect(lambda: open_folder(self.ctrl.local_dir))
        f.addRow(b)
        return w

    def _glow_tab(self):
        w = QWidget()
        f = QFormLayout(w)
        f.addRow(self.check("glow_enabled", "Show edge glow"))
        f.addRow(self.check("glow_only_playing", "Only while music is playing"))
        f.addRow("Animation", self.combo("glow_animation", GLOW_ANIMATIONS))
        f.addRow("Thickness", self.slider("glow_thickness", 1, 40, suffix=" px"))
        f.addRow("Glow spread", self.slider("glow_spread", 0, 260, suffix=" px"))
        f.addRow("Brightness", self.slider("glow_intensity", 10, 100, scale=100, suffix="%"))
        edges = QWidget()
        g = QHBoxLayout(edges)
        g.setContentsMargins(0, 0, 0, 0)
        for e in ("top", "bottom", "left", "right"):
            cb = QCheckBox(e.capitalize())
            cb.setChecked(e in self.cfg["glow_edges"])

            def tog(v, e=e):
                cur = [x for x in self.cfg["glow_edges"] if x != e]
                if v:
                    cur.append(e)
                self.cfg.set("glow_edges", cur)
            cb.toggled.connect(tog)
            g.addWidget(cb)
        f.addRow("Edges", edges)
        scr = QComboBox()
        for i, s in enumerate(QGuiApplication.screens()):
            scr.addItem(f"{i + 1}: {s.name()} ({s.geometry().width()}×{s.geometry().height()})")
        scr.setCurrentIndex(min(self.cfg["glow_screen"], scr.count() - 1))
        scr.currentIndexChanged.connect(lambda i: self.cfg.set("glow_screen", i))
        f.addRow("Display", scr)
        self.audio_lab = QLabel()
        self.audio_lab.setWordWrap(True)
        self.audio_lab.setStyleSheet("color:gray;font-size:11px;")
        f.addRow("Beat sync", self.audio_lab)
        return w

    def _colors_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        f = QFormLayout()
        f.addRow("Color source", self.combo("color_mode", COLOR_MODES))
        help_ = QLabel("Album art: colours follow the cover of each song. Screen colors: sampled "
                       "from what's on your display. Manual: pick your own below.")
        help_.setWordWrap(True)
        help_.setStyleSheet("color:gray;font-size:11px;")
        f.addRow("", help_)
        v.addLayout(f)
        box = QGroupBox("Manual colours")
        g = QGridLayout(box)
        g.addWidget(self.color_btn("color_glow1", "Glow primary"), 0, 0)
        g.addWidget(self.color_btn("color_glow2", "Glow secondary"), 0, 1)
        g.addWidget(self.color_btn("color_lyric", "Lyric text"), 1, 0)
        g.addWidget(self.color_btn("color_highlight", "Highlight"), 1, 1)
        g.addWidget(self.color_btn("color_secondary", "Other lines"), 2, 0)
        cp = QPushButton("Copy current song's colours")
        cp.clicked.connect(self.ctrl.copy_palette_to_manual)
        g.addWidget(cp, 2, 1)
        v.addWidget(box)
        v.addStretch()
        return w

    def _stage_tab(self):
        w = QWidget()
        f = QFormLayout(w)
        intro = QLabel("Stage is a full-screen lyrics view with the album art, a clock and a "
                       "now-playing card — like lyrics on a lock screen. Press any key or click to exit.")
        intro.setWordWrap(True)
        f.addRow(intro)
        f.addRow(self.check("stage_idle_enabled", "Open Stage automatically when I'm away"))
        mins = QSpinBox()
        mins.setRange(1, 120)
        mins.setSuffix(" min idle")
        mins.setValue(int(self.cfg["stage_idle_minutes"]))
        mins.valueChanged.connect(lambda val: self.cfg.set("stage_idle_minutes", int(val)))
        f.addRow("After", mins)
        f.addRow(self.check("stage_clock", "Show clock and date"))
        f.addRow(self.check("keep_awake", "Keep display awake while music plays"))
        from . import window_tweaks
        lock = self.check("lock_screen", "Show lyrics and glow on the lock screen (Mac)")
        if not window_tweaks.lock_screen_supported():
            lock.setEnabled(False)
            lock.setToolTip("Only available on macOS. Windows doesn't allow apps on the lock screen.")
        f.addRow(lock)
        note = QLabel("The lyrics bar and glow always stay on top of other apps, on every "
                      "desktop and over full-screen apps.")
        note.setWordWrap(True)
        note.setStyleSheet("color:gray;font-size:11px;")
        f.addRow(note)
        return w

    def _about_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        lab = QLabel(
            f"<h3>GlowLyrics {__version__}</h3>"
            "<p>Word-by-word synced lyrics plus a screen-edge glow that follows your music's "
            "album colours and beat.</p>"
            "<p><b>Music sources:</b> Windows: Spotify, Apple Music, browsers and any app in the "
            "Windows media controls. macOS: Spotify and Apple Music. Linux: any MPRIS player "
            "(needs <i>playerctl</i>).</p>"
            "<p><b>Lyrics:</b> LRCLIB (free community database) or your own .lrc files.</p>"
            "<p><b>Album art:</b> from your player, or the iTunes Search API.</p>"
            "<p>Idea by Shriyans Raut.</p>"
            f"<p style='color:gray'>{COPYRIGHT}</p>")
        lab.setWordWrap(True)
        lab.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(lab)
        v.addWidget(self.check("demo", "Demo mode (built-in test song)"))
        row = QHBoxLayout()
        b1 = QPushButton("Clear lyrics cache")
        b1.clicked.connect(self.ctrl.clear_cache)
        b2 = QPushButton("Open settings folder")
        from .system import app_dir
        b2.clicked.connect(lambda: open_folder(app_dir()))
        row.addWidget(b1)
        row.addWidget(b2)
        v.addLayout(row)
        row2 = QHBoxLayout()
        from .legal import show_document
        b3 = QPushButton("License Agreement")
        b3.clicked.connect(lambda: show_document(self, "GlowLyrics License Agreement", "LICENSE.txt"))
        b4 = QPushButton("Third-party notices")
        b4.clicked.connect(lambda: show_document(self, "Third-party notices", "THIRD-PARTY-NOTICES.txt"))
        b5 = QPushButton("Open-source licenses")
        b5.clicked.connect(lambda: show_document(self, "Open-source licenses", "THIRD-PARTY-LICENSES.txt"))
        row2.addWidget(b3)
        row2.addWidget(b4)
        row2.addWidget(b5)
        v.addLayout(row2)
        v.addStretch()
        return w

    def refresh(self):
        c = self.ctrl
        np = c.np
        if np.title:
            state = "▶ Playing" if np.playing else "⏸ Paused"
            lyr = c.status_text or (f"Lyrics: {c.lyrics.source}" if c.lyrics else "")
            self.now.setText(f"<b>{state}:</b> {np.title} — {np.artist}<br>"
                             f"<span style='color:gray'>{lyr}</span>")
        else:
            self.now.setText("<b>Nothing playing.</b> Start a song in Spotify, Apple Music or your "
                             "browser.<br><span style='color:gray'>" + (c.problem or "") + "</span>")
        self.audio_lab.setText(c.audio.status if not c.cfg["demo"] else "Demo mode: simulated beat")

    def closeEvent(self, e):
        if not self.ctrl.tray:
            self.ctrl.quit()
        super().closeEvent(e)
