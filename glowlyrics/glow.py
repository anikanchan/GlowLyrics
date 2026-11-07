# Copyright © 2026 Tirhut LLC. All rights reserved.
"""Ambient edge glow: four click-through strips along the screen edges."""
import math
import time

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget

EDGES = ("top", "bottom", "left", "right")


class EdgeStrip(QWidget):
    def __init__(self, glow, edge):
        super().__init__(None)
        self.glow = glow
        self.edge = edge
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                            Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput |
                            Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setWindowTitle("GlowLyrics glow")

    def paintEvent(self, e):
        p = QPainter(self)
        self.glow.paint_strip(self, p)
        p.end()


class GlowOverlay:
    def __init__(self, ctrl):
        self.ctrl = ctrl
        self.strips = {e: EdgeStrip(self, e) for e in EDGES}
        self.screen_rect = QRect()
        self.visible = False
        self.angle = 0.0
        self._last = time.monotonic()
        self.intensity = 0.0
        self.reach = 0.0
        app = QGuiApplication.instance()
        app.screenAdded.connect(lambda *_: self.rebuild())
        app.screenRemoved.connect(lambda *_: self.rebuild())
        app.primaryScreenChanged.connect(lambda *_: self.rebuild())
        self.rebuild()

    def _screen(self):
        screens = QGuiApplication.screens()
        i = self.ctrl.cfg["glow_screen"]
        return screens[i] if 0 <= i < len(screens) else QGuiApplication.primaryScreen()

    def strip_size(self):
        cfg = self.ctrl.cfg
        return int((cfg["glow_thickness"] + cfg["glow_spread"]) * 1.45) + 4

    def rebuild(self):
        g = self._screen().geometry()
        self.screen_rect = g
        s = min(self.strip_size(), g.height() // 3)
        geo = {
            "top": QRect(g.left(), g.top(), g.width(), s),
            "bottom": QRect(g.left(), g.bottom() - s + 1, g.width(), s),
            "left": QRect(g.left(), g.top(), s, g.height()),
            "right": QRect(g.right() - s + 1, g.top(), s, g.height()),
        }
        for e, w in self.strips.items():
            w.setGeometry(geo[e])
        self.set_visible(self.visible, force=True)

    def set_visible(self, on, force=False):
        if on == self.visible and not force:
            return
        self.visible = on
        edges = self.ctrl.cfg["glow_edges"]
        for e, w in self.strips.items():
            if on and e in edges:
                w.show()
                w.raise_()
            else:
                w.hide()

    def raise_all(self):
        for w in self.strips.values():
            if w.isVisible():
                w.raise_()

    def tick(self):
        if not self.visible:
            return
        cfg = self.ctrl.cfg
        now = time.monotonic()
        dt = min(0.1, now - self._last)
        self._last = now
        beat_mode = cfg["glow_animation"] == "Beat"
        pulse, level = self.ctrl.beat_pulse(), self.ctrl.audio_level()
        if beat_mode and self.ctrl.beat_live():
            target_i = 0.55 + 0.45 * pulse + 0.15 * level
            target_r = 0.8 + 0.45 * pulse + 0.15 * level
            speed = 18 + 60 * level + 50 * pulse
        else:
            breathe = (math.sin(now * 1.3) + 1) / 2
            target_i = 0.72 + 0.18 * breathe
            target_r = 0.9 + 0.12 * breathe
            speed = 10
        # fast attack, slower release
        k_i = 0.6 if target_i > self.intensity else min(1.0, dt * 6)
        self.intensity += (target_i - self.intensity) * k_i
        self.reach += (target_r - self.reach) * (0.6 if target_r > self.reach else min(1.0, dt * 5))
        self.angle = (self.angle + speed * dt) % 360
        for e, w in self.strips.items():
            if w.isVisible():
                w.update()

    # The glow is soft, so it is rendered into a small offscreen image (1/DOWNSCALE of
    # the logical size, ignoring Retina scaling) and smoothly stretched onto the strip.
    # This cuts the per-frame painting work by ~20-40x with no visible difference.
    DOWNSCALE = 3

    def paint_strip(self, strip, p):
        r = strip.rect()
        ds = self.DOWNSCALE
        bw, bh = max(1, -(-r.width() // ds)), max(1, -(-r.height() // ds))
        buf = getattr(strip, "_buf", None)
        if buf is None or buf.width() != bw or buf.height() != bh:
            buf = QImage(bw, bh, QImage.Format.Format_ARGB32_Premultiplied)
            strip._buf = buf
        bp = QPainter(buf)
        self._paint_glow(strip, bp, bw, bh, ds)
        bp.end()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(QRectF(r), buf, QRectF(0, 0, r.width() / ds, r.height() / ds))

    def _color_at(self, gx, gy):
        """Colour of the rotating two-colour ring at global point (gx, gy)."""
        sc = self.screen_rect
        ang = math.degrees(math.atan2(-(gy - sc.center().y()), gx - sc.center().x()))
        pos = ((ang - self.angle) / 360.0) % 1.0
        stops = self._stops
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= pos <= p1:
                f = 0.0 if p1 == p0 else (pos - p0) / (p1 - p0)
                return QColor.fromRgbF(c0.redF() + (c1.redF() - c0.redF()) * f,
                                       c0.greenF() + (c1.greenF() - c0.greenF()) * f,
                                       c0.blueF() + (c1.blueF() - c0.blueF()) * f)
        return QColor(stops[0][1])

    def _paint_glow(self, strip, p, bw, bh, ds):
        """Paints one strip into its small buffer (buffer pixels = ds logical pixels)."""
        cfg = self.ctrl.cfg
        cols = self.ctrl.colors
        c1, c2 = cols["glow1"], cols["glow2"]
        self._stops = ((0.0, c1), (0.3, c1), (0.5, c2), (0.8, c1), (0.9, c2), (1.0, c1))
        horizontal = strip.edge in ("top", "bottom")
        n = 24
        # colour varies along the edge: sample the ring at points on the screen edge
        if horizontal:
            gy = strip.y() if strip.edge == "top" else strip.y() + strip.height()
            cg = QLinearGradient(0, 0, bw, 0)
            for i in range(n + 1):
                f = i / n
                cg.setColorAt(f, self._color_at(strip.x() + f * strip.width(), gy))
        else:
            gx = strip.x() if strip.edge == "left" else strip.x() + strip.width()
            cg = QLinearGradient(0, 0, 0, bh)
            for i in range(n + 1):
                f = i / n
                cg.setColorAt(f, self._color_at(gx, strip.y() + f * strip.height()))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(0, 0, bw, bh, cg)
        # alpha falloff from the edge inwards
        inten = max(0.0, min(1.0, self.intensity * cfg["glow_intensity"]))
        thick = cfg["glow_thickness"] * self.reach / ds
        reach = max(1.0, (cfg["glow_thickness"] + cfg["glow_spread"]) * self.reach / ds)
        reach = min(reach, bh if horizontal else bw)
        if strip.edge == "top":
            lg = QLinearGradient(0, 0, 0, reach)
        elif strip.edge == "bottom":
            lg = QLinearGradient(0, bh, 0, bh - reach)
        elif strip.edge == "left":
            lg = QLinearGradient(0, 0, reach, 0)
        else:
            lg = QLinearGradient(bw, 0, bw - reach, 0)
        tf = min(0.9, thick / reach)

        def a(x):
            c = QColor(0, 0, 0)
            c.setAlphaF(max(0.0, min(1.0, x)))
            return c
        lg.setColorAt(0.0, a(inten))
        lg.setColorAt(tf, a(inten * 0.8))
        lg.setColorAt(tf + (1 - tf) * 0.35, a(inten * 0.32))
        lg.setColorAt(tf + (1 - tf) * 0.7, a(inten * 0.08))
        lg.setColorAt(1.0, a(0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        p.fillRect(0, 0, bw, bh, lg)
