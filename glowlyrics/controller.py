# Copyright © 2026 Tirhut LLC. All rights reserved.
"""Wires media detection, lyrics, colours, audio and all windows together."""
import logging
import math
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QBuffer, QIODevice, QObject, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QActionGroup, QColor, QFont, QGuiApplication, QIcon,
                           QLinearGradient, QPainter, QPixmap)
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .audio import AudioAnalyzer
from .colors import blurred_background, demo_art, extract_palette, fetch_art
from .config import COLOR_MODES, STYLES
from .glow import GlowOverlay
from .lyrics import DEMO_LRC, LyricsFetcher, parse_lrc
from .lyrics_view import LyricsOverlay, StageWindow
from .media import DemoProvider, MediaWatcher, NowPlaying
from .settings_ui import SettingsWindow
from .system import KeepAwake, idle_seconds, sub_dir
from . import window_tweaks

log = logging.getLogger("glowlyrics")
COLOR_KEYS = ("glow1", "glow2", "lyric", "highlight", "secondary")


def make_icon(c1="#ff3d7f", c2="#7a5cff"):
    pm = QPixmap(128, 128)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, 128, 128)
    g.setColorAt(0, QColor(c1))
    g.setColorAt(1, QColor(c2))
    p.setBrush(g)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(8, 8, 112, 112, 30, 30)
    f = QFont()
    f.setPixelSize(78)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("white"))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "♪")
    p.end()
    return QIcon(pm)


class _Bridge(QObject):
    loaded = Signal(object, object, object, object, object)  # key, lyrics, palette, art, bg


class Controller(QObject):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.np = NowPlaying()
        self.lyrics = None
        self.status_text = ""
        self.problem = ""
        self.art_pixmap = None
        self.bg_pixmap = None
        self.album_palette = None
        self.screen_palette = None
        self._clock_pos = 0.0
        self._clock_stamp = time.monotonic()
        self._playing = False
        self._pending_key = None
        self._pending_count = 0
        self._loaded_key = None
        self._load_gen = 0
        self.stage = None
        self.keep_awake = KeepAwake()
        self._audio_perm_told = False
        self.lock = window_tweaks.LockWatcher(self._on_lock_change)

        self.cache_dir = sub_dir("cache")
        self.local_dir = sub_dir("lyrics")
        self.fetcher = LyricsFetcher(self.cache_dir, self.local_dir)
        self.fetcher.prune_cache()
        # One worker: track loads run one at a time, stale ones are skipped.
        self._loader = ThreadPoolExecutor(max_workers=1, thread_name_prefix="glowlyrics-load")

        self.colors = {k: QColor(self.cfg[f"color_{k}"]) for k in COLOR_KEYS}
        self._target_colors = dict(self.colors)

        self.icon = make_icon()
        QApplication.instance().setWindowIcon(self.icon)

        self.audio = AudioAnalyzer()
        self.audio.start()

        self.bridge = _Bridge()
        self.bridge.loaded.connect(self._on_loaded)

        self.menu = self._build_menu()
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.icon)
            self.tray.setToolTip("GlowLyrics")
            self.tray.setContextMenu(self.menu)
            self.tray.activated.connect(self._tray_activated)
            self.tray.show()

        self.overlay = LyricsOverlay(self)
        self.glow = GlowOverlay(self)
        self.settings = SettingsWindow(self)

        self.watcher = MediaWatcher(cfg)
        self.watcher.updated.connect(self._on_np)
        self.watcher.problem.connect(self._on_problem)
        self.watcher.start()

        cfg.changed.connect(self._on_cfg)
        self._update_target_colors()

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)

        self.slow = QTimer(self)
        self.slow.timeout.connect(self._slow_tick)
        self.slow.start(2000)

        if cfg["first_run"] or not self.tray:
            self.show_settings()
            cfg.set("first_run", False)
            if self.tray:
                self.tray.showMessage("GlowLyrics is running",
                                      "Find it in the system tray / menu bar. Play a song to start.",
                                      self.icon, 6000)

    # ------------------------------------------------------------------ timing
    def raw_position(self):
        return self._clock_pos + ((time.monotonic() - self._clock_stamp) if self._playing else 0.0)

    def position(self):
        return self.raw_position() - self.cfg["offset_ms"] / 1000.0

    def _real_audio(self):
        return self.audio.available and self.audio.hearing_audio()

    def beat_live(self):
        """True when the glow has something to pulse to (real audio or the lyrics' rhythm)."""
        if not self._playing:
            return False
        return self.cfg["demo"] or self._real_audio() or bool(self.lyrics and self.lyrics.lines)

    def beat_pulse(self):
        if self.cfg["demo"]:
            return math.exp(-(self.raw_position() % 0.5) * 6)  # 120 BPM
        if self._real_audio():
            return self.audio.pulse()
        return self._lyrics_pulse()

    def _lyrics_pulse(self):
        """Fallback when system audio isn't available: pulse on each sung word,
        a bigger pulse at the start of each line."""
        lyr = self.lyrics
        if not lyr or not lyr.lines:
            return 0.0
        t = self.position()
        i = lyr.index_at(t)
        if i < 0:
            return 0.0
        line = lyr.lines[i]
        line_age = t - line.start
        word_age = 99.0
        for w in line.words:
            if w.start <= t:
                word_age = t - w.start
            else:
                break
        return max(math.exp(-line_age * 4.0), 0.7 * math.exp(-word_age * 7.0))

    def audio_level(self):
        if self.cfg["demo"]:
            return 0.5 + 0.3 * math.sin(self.raw_position() * 0.7)
        if self._real_audio():
            return self.audio.level
        return 0.35 if self.beat_live() else 0.0

    # ------------------------------------------------------------------ media
    def _on_problem(self, msg):
        self.problem = msg
        if not msg:
            return  # problem resolved
        if self.tray:
            self.tray.showMessage("GlowLyrics needs permission" if "Automation" in msg else "GlowLyrics",
                                  msg, self.icon, 15000)
        if "Automation" in msg:
            self.show_settings()  # shows the fix + a button to open the right settings page

    def _on_np(self, np):
        key = np.key()
        track_changed = key != self.np.key()
        self.np = np
        if not np.title:
            self._playing = False
            self.lyrics = None
            self._loaded_key = None
            self.status_text = ""
            self._pending_key = None
            return
        # resync the local clock only when it drifts, to keep motion smooth
        actual = np.current_position()
        if track_changed or np.playing != self._playing or abs(self.raw_position() - actual) > 0.35:
            self._clock_pos = actual
            self._clock_stamp = time.monotonic()
        self._playing = np.playing
        if track_changed:
            self.lyrics = None
            self.status_text = "Looking for lyrics…"
        # wait until a track is stable for 2 polls before loading (skips, stale artwork)
        if key != self._pending_key:
            self._pending_key, self._pending_count = key, 1
        else:
            self._pending_count += 1
        if self._pending_count == 2 and key != self._loaded_key:
            self._loaded_key = key
            self._start_load(np)

    def _start_load(self, np):
        self._load_gen += 1
        gen = self._load_gen
        key = np.key()

        def work():
            if gen != self._load_gen:
                return  # user already skipped to another song
            lyr = pal = art = bg = None
            try:
                if np.source == "demo":
                    lyr = parse_lrc(DEMO_LRC, DemoProvider.DURATION, "Demo")
                    art = demo_art()
                else:
                    try:
                        lyr = self.fetcher.get(np.title, np.artist, np.album, np.duration)
                    except Exception as e:
                        log.debug("lyrics failed: %s", e)
                    art = fetch_art(np, self.fetcher.http)
                if art:
                    pal = extract_palette(art)
                    bg = blurred_background(art)
            except Exception as e:
                log.exception("load failed: %s", e)
            if gen == self._load_gen:
                self.bridge.loaded.emit(key, lyr, pal, art, bg)

        self._loader.submit(work)

    def _on_loaded(self, key, lyr, pal, art, bg):
        if key != self.np.key():
            return
        self.lyrics = lyr
        if lyr is None:
            self.status_text = "No lyrics found for this song"
        elif lyr.instrumental:
            self.status_text = "Instrumental"
        else:
            self.status_text = ""
        self.album_palette = pal
        self.art_pixmap = self._pix(art)
        self.bg_pixmap = self._pix(bg)
        self._update_target_colors()
        if self.tray:
            self.tray.setToolTip(f"GlowLyrics — {self.np.title} · {self.np.artist}")

    @staticmethod
    def _pix(data):
        if not data:
            return None
        pm = QPixmap()
        return pm if pm.loadFromData(data) else None

    # ------------------------------------------------------------------ colours
    def _update_target_colors(self):
        mode = self.cfg["color_mode"]
        pal = None
        if mode == "Album art":
            pal = self.album_palette
        elif mode == "Screen colors":
            pal = self.screen_palette or self.album_palette
        src = pal or {k: self.cfg[f"color_{k}"] for k in COLOR_KEYS}
        if mode == "Manual":
            src = {k: self.cfg[f"color_{k}"] for k in COLOR_KEYS}
        self._target_colors = {k: QColor(src[k]) for k in COLOR_KEYS}

    def copy_palette_to_manual(self):
        for k in COLOR_KEYS:
            self.cfg.set(f"color_{k}", self.colors[k].name())

    def _sample_screen(self):
        scr = QGuiApplication.primaryScreen()
        g = scr.geometry()
        pm = scr.grabWindow(0, int(g.width() * 0.15), int(g.height() * 0.15),
                            int(g.width() * 0.7), int(g.height() * 0.7))
        if pm.isNull():
            return
        pm = pm.scaled(64, 36)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pm.save(buf, "PNG")
        pal = extract_palette(bytes(buf.data()))
        if pal:
            self.screen_palette = pal
            self._update_target_colors()

    # ------------------------------------------------------------------ loops
    def _tick(self):
        # ease colours toward targets
        for k in COLOR_KEYS:
            a, b = self.colors[k], self._target_colors[k]
            if a != b:
                f = 0.08
                n = QColor.fromRgbF(a.redF() + (b.redF() - a.redF()) * f,
                                    a.greenF() + (b.greenF() - a.greenF()) * f,
                                    a.blueF() + (b.blueF() - a.blueF()) * f)
                if abs(n.red() - b.red()) + abs(n.green() - b.green()) + abs(n.blue() - b.blue()) < 4:
                    n = QColor(b)
                self.colors[k] = n
        cfg = self.cfg
        has_track = bool(self.np.title)
        show_ov = cfg["show_lyrics"] and (has_track or not cfg["hide_when_idle"])
        shown_changed = False
        if show_ov != self.overlay.isVisible():
            self.overlay.setVisible(show_ov)
            shown_changed = True
        if show_ov:
            self.overlay.update()
        glow_on = cfg["glow_enabled"] and (self._playing or not cfg["glow_only_playing"])
        if glow_on != self.glow.visible:
            shown_changed = True
        self.glow.set_visible(glow_on)
        if shown_changed:
            self._apply_window_tweaks()  # newly shown windows: all Spaces / on top
        self.glow.tick()
        if self.stage is not None:
            self.stage.update()
        # Only run at 30 fps while something is actually animating; otherwise ~5 fps.
        animating = self.stage is not None or glow_on or (show_ov and self._playing)
        want = 33 if animating else 200
        if self.timer.interval() != want:
            self.timer.setInterval(want)
        # Beat detection only while the beat-synced glow is on screen.
        want_audio = (glow_on and self._playing and cfg["glow_animation"] == "Beat"
                      and not cfg["demo"])  # demo mode simulates the beat
        if want_audio and sys.platform == "darwin" and not cfg["mac_audio_explained"]:
            cfg.set("mac_audio_explained", True)
            if self.tray:
                self.tray.showMessage(
                    "Beat sync", "To pulse with the beat, macOS will ask to let GlowLyrics capture "
                    "system audio. Sound is analysed on your Mac only and never recorded or sent.",
                    self.icon, 12000)
        self.audio.active = want_audio
        if self.audio.needs_permission and not self._audio_perm_told:
            self._audio_perm_told = True
            if self.tray:
                self.tray.showMessage("Beat sync is off", self.audio.status, self.icon, 15000)

    def _slow_tick(self):
        cfg = self.cfg
        self.keep_awake.set(cfg["keep_awake"] and self._playing)
        self._apply_window_tweaks()  # cheap; re-asserts "on top" (e.g. after full-screen video)
        if cfg["color_mode"] == "Screen colors" and self._playing:
            try:
                self._sample_screen()
            except Exception:
                pass
        if self.settings.isVisible():
            self.settings.refresh()
        # auto Stage when idle
        idle = idle_seconds() if (cfg["stage_idle_enabled"] or (self.stage and self.stage.auto)) else None
        if idle is not None:
            if self.stage is None and self._playing and idle > cfg["stage_idle_minutes"] * 60:
                self.open_stage(auto=True)
            elif self.stage is not None and self.stage.auto and idle < 1.5:
                self.stage.close()

    # ------------------------------------------------------------------ config changes
    def _on_cfg(self, key):
        if key.startswith("color_"):
            self._update_target_colors()
        elif key == "overlay_locked":
            self.overlay.apply_flags()
            self._apply_window_tweaks()
        elif key in ("glow_thickness", "glow_spread", "glow_screen"):
            self.glow.rebuild()
            self._apply_window_tweaks()
        elif key == "glow_edges":
            self.glow.set_visible(self.glow.visible, force=True)
            self._apply_window_tweaks()
        elif key == "lock_screen":
            self._apply_window_tweaks()
        elif key == "demo":
            self.np = NowPlaying()
            self.lyrics = None
            self._loaded_key = None
            self._pending_key = None
        elif key in ("lyrics_style", "show_lyrics", "overlay_locked", "glow_enabled",
                     "glow_animation"):
            pass
        self._sync_menu()

    # ------------------------------------------------------------------ platform window tweaks
    def _apply_window_tweaks(self):
        wins = [self.overlay] + list(self.glow.strips.values())
        window_tweaks.configure(wins, locked=self.lock.locked, lock_screen=self.cfg["lock_screen"])

    def _on_lock_change(self, locked):
        """Mac screen locked/unlocked: lift the lyrics + glow above the lock screen (or back)."""
        if locked and self.stage is not None:
            self.stage.close()  # Stage takes keyboard focus; never put it over the lock screen
        self._apply_window_tweaks()

    # ------------------------------------------------------------------ windows / actions
    def open_stage(self, auto=False):
        if self.stage is not None:
            self.stage.raise_()
            return
        self.stage = StageWindow(self, auto=auto)
        self.stage.closed.connect(self._stage_closed)
        scr = QGuiApplication.screens()
        i = self.cfg["glow_screen"]
        screen = scr[i] if 0 <= i < len(scr) else QGuiApplication.primaryScreen()
        self.stage.setGeometry(screen.geometry())
        self.stage.showFullScreen()
        self.stage.activateWindow()
        self.glow.raise_all()

    def _stage_closed(self):
        if self.stage is not None:
            self.stage.deleteLater()
        self.stage = None

    def show_settings(self):
        self.settings.refresh()
        self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()

    def clear_cache(self):
        shutil.rmtree(self.cache_dir, ignore_errors=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        self._loaded_key = None
        self._pending_key = None

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_settings()

    def quit(self):
        self.timer.stop()
        self.slow.stop()
        self.keep_awake.set(False)
        self.lock.close()
        self.audio.stop()
        self.watcher.stop()
        self._loader.shutdown(wait=False, cancel_futures=True)
        self.cfg.save()
        QApplication.instance().quit()

    def _build_menu(self):
        m = QMenu()
        self._acts = {}

        def toggle(key, text):
            a = QAction(text, m, checkable=True)
            a.setChecked(bool(self.cfg[key]))
            a.toggled.connect(lambda v: self.cfg.set(key, bool(v)))
            m.addAction(a)
            self._acts[key] = a

        toggle("show_lyrics", "Show lyrics")
        toggle("glow_enabled", "Edge glow")
        m.addAction("Open Stage (full screen)", lambda: self.open_stage())
        m.addSeparator()
        sm = m.addMenu("Lyrics style")
        grp = QActionGroup(sm)
        self._style_acts = {}
        for s in STYLES:
            a = QAction(s, sm, checkable=True)
            a.setChecked(self.cfg["lyrics_style"] == s)
            a.triggered.connect(lambda _=False, s=s: self.cfg.set("lyrics_style", s))
            grp.addAction(a)
            sm.addAction(a)
            self._style_acts[s] = a
        cm = m.addMenu("Colors")
        grp2 = QActionGroup(cm)
        self._color_acts = {}
        for s in COLOR_MODES:
            a = QAction(s, cm, checkable=True)
            a.setChecked(self.cfg["color_mode"] == s)
            a.triggered.connect(lambda _=False, s=s: self.cfg.set("color_mode", s))
            grp2.addAction(a)
            cm.addAction(a)
            self._color_acts[s] = a
        tm = m.addMenu("Timing")
        tm.addAction("Lyrics later (+0.25 s)",
                     lambda: self.cfg.set("offset_ms", self.cfg["offset_ms"] + 250))
        tm.addAction("Lyrics earlier (−0.25 s)",
                     lambda: self.cfg.set("offset_ms", self.cfg["offset_ms"] - 250))
        tm.addAction("Reset", lambda: self.cfg.set("offset_ms", 0))
        toggle("overlay_locked", "Lock lyrics position")
        m.addSeparator()
        toggle("demo", "Demo mode")
        m.addAction("Settings…", self.show_settings)
        m.addAction("Quit GlowLyrics", self.quit)
        return m

    def _sync_menu(self):
        for k, a in self._acts.items():
            if a.isChecked() != bool(self.cfg[k]):
                a.blockSignals(True)
                a.setChecked(bool(self.cfg[k]))
                a.blockSignals(False)
        if self.cfg["lyrics_style"] in self._style_acts:
            self._style_acts[self.cfg["lyrics_style"]].setChecked(True)
        if self.cfg["color_mode"] in self._color_acts:
            self._color_acts[self.cfg["color_mode"]].setChecked(True)
