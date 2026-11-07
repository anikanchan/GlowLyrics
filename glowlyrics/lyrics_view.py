# Copyright © 2026 Tirhut LLC. All rights reserved.
"""Lyrics rendering (4 styles), the floating overlay window, and full-screen Stage mode."""
import bisect
import math
import time
from collections import OrderedDict

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QGuiApplication, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap, QTransform)
from PySide6.QtWidgets import QApplication, QSizeGrip, QWidget

from .emoji_map import emoji_for

EMOJI_FAMILIES = ["Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", "Twemoji"]
EMOJI_PEN = QColor(0, 0, 0)


def _alpha(c, a):
    c = QColor(c)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


class PixmapCache:
    """Cache of rendered images. Entries not used for `ttl` seconds are dropped (so memory
    tracks what's on screen), and a hard byte cap evicts least-recently-used first."""

    def __init__(self, max_bytes, ttl=10.0):
        self.max_bytes = max_bytes
        self.ttl = ttl
        self.bytes = 0
        self._d = OrderedDict()   # key -> (pixmap, last_used)
        self._last_prune = 0.0

    @staticmethod
    def _size(pm):
        return pm.width() * pm.height() * 4

    def get(self, key):
        hit = self._d.get(key)
        if hit is None:
            return None
        self._d[key] = (hit[0], time.monotonic())
        self._d.move_to_end(key)
        return hit[0]

    def put(self, key, pm):
        old = self._d.pop(key, None)
        if old is not None:
            self.bytes -= self._size(old[0])
        self._d[key] = (pm, time.monotonic())
        self.bytes += self._size(pm)
        while self.bytes > self.max_bytes and len(self._d) > 1:
            _, (ev, _) = self._d.popitem(last=False)
            self.bytes -= self._size(ev)

    def prune(self):
        """Drop entries unused for `ttl` seconds (cheap; runs at most once a second)."""
        now = time.monotonic()
        if now - self._last_prune < 1.0:
            return
        self._last_prune = now
        while self._d:
            key, (pm, used) = next(iter(self._d.items()))
            if now - used < self.ttl:
                break
            del self._d[key]
            self.bytes -= self._size(pm)

    def clear(self):
        self._d.clear()
        self.bytes = 0


class LyricsRenderer:
    """Draws lyrics. Large text is expensive to rasterise (especially on Retina, where it
    is too big for Qt's glyph cache), so each line is rendered once into an image and
    reused every frame; the karaoke sweep is done by clipping a highlighted copy."""

    CACHE_BYTES = 24 * 1024 * 1024

    def __init__(self, ctrl):
        self.ctrl = ctrl
        self.scroll = None
        self._last = time.monotonic()
        self._fonts = {}
        self._layouts = {}
        self._lyrics_ref = None
        self.cache = PixmapCache(self.CACHE_BYTES)
        self._pop_words = None
        self._pop_scroll = None

    # ---------------------------------------------------------------- helpers
    def font(self, px, bold=True):
        fam = self.ctrl.cfg["font_family"] or QApplication.font().family()
        key = (fam, int(px), bold)
        f = self._fonts.get(key)
        if f is None:
            if len(self._fonts) > 300:
                self._fonts.clear()
            f = QFont(fam)
            f.setPixelSize(max(6, int(px)))
            f.setWeight(QFont.Weight.Bold if bold else QFont.Weight.DemiBold)
            self._fonts[key] = f
        return f

    def emoji_font(self, px):
        key = ("emoji", int(px))
        f = self._fonts.get(key)
        if f is None:
            f = QFont()
            f.setFamilies(EMOJI_FAMILIES)
            f.setPixelSize(max(6, int(px)))
            self._fonts[key] = f
        return f

    def layout(self, line, font, max_w, emoji=False):
        """Word-wrap a line. Returns (rows, line_height, ascent);
        rows = [(row_width, [(word, x, width, emoji_or_None)])]."""
        key = (id(line), font.pixelSize(), font.family(), int(max_w), emoji)
        hit = self._layouts.get(key)
        if hit:
            return hit
        fm = QFontMetricsF(font)
        space = fm.horizontalAdvance(" ")
        e_w = fm.height() * 1.1
        rows, cur, x = [], [], 0.0
        for w in line.words:
            ww = fm.horizontalAdvance(w.text)
            e = emoji_for(w.text) if emoji else None
            total = ww + (e_w if e else 0)
            if cur and x + total > max_w:
                rows.append((x - space, cur))
                cur, x = [], 0.0
            cur.append((w, x, ww, e))
            x += total + space
        if cur:
            rows.append((x - space, cur))
        res = (rows, fm.height() * 1.08, fm.ascent())
        if len(self._layouts) > 400:
            self._layouts.clear()
        self._layouts[key] = res
        return res

    def fit_font(self, line, px, max_w, bold=True):
        f = self.font(px, bold)
        w = QFontMetricsF(f).horizontalAdvance(line.text)
        if w > max_w > 0:
            f = self.font(max(8, px * max_w / w), bold)
        return f

    def _block(self, line, font, max_w, emoji, color, emoji_op, dpr):
        """Image of a whole (wrapped, centred) line in one colour. Cached."""
        rows, lh, asc = self.layout(line, font, max_w, emoji)
        # Quantise the colour so the ~1 s colour fade between songs reuses a few images
        # instead of creating a new one every frame.
        c = QColor(color)
        color = QColor((c.red() >> 3) << 3, (c.green() >> 3) << 3, (c.blue() >> 3) << 3,
                       (c.alpha() >> 3) << 3 | 7)
        key = (id(line), font.family(), font.pixelSize(), font.weight(), int(max_w), emoji,
               color.rgba(), emoji_op, round(dpr, 2))
        pm = self.cache.get(key)
        if pm is not None:
            return pm
        pad = lh * 0.2
        bw = max((rw for rw, _ in rows), default=1.0)
        w, h = bw + 2 * pad, len(rows) * lh + 2 * pad
        pm = QPixmap(max(1, math.ceil(w * dpr)), max(1, math.ceil(h * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        q.setFont(font)
        q.setPen(QColor(color))
        y = pad
        for row_w, items in rows:
            x0 = pad + (bw - row_w) / 2
            for wd, x, ww, e in items:
                q.drawText(QPointF(x0 + x, y + asc), wd.text)
                if e:
                    self._draw_emoji(q, e, x0 + x + ww, y, lh, emoji_op)
                    q.setFont(font)
            y += lh
        q.end()
        self.cache.put(key, pm)
        return pm

    def line_height(self, line, font, max_w, emoji=False):
        rows, lh, _ = self.layout(line, font, max_w, emoji)
        return len(rows) * lh

    def draw_line(self, p, line, font, max_w, emoji, cx, top, t, colors, opacity, active):
        """Draw a wrapped line centred on cx with its top at `top`. Returns its height.
        active=True highlights words as they are sung (karaoke sweep)."""
        rows, lh, asc = self.layout(line, font, max_w, emoji)
        dpr = p.device().devicePixelRatioF() if p.device() else 1.0
        pad = lh * 0.2
        bw = max((rw for rw, _ in rows), default=1.0)
        origin = QPointF(cx - bw / 2 - pad, top - pad)
        old_op = p.opacity()
        if not active:
            p.setOpacity(old_op * max(0.0, min(1.0, opacity)))
            p.drawPixmap(origin, self._block(line, font, max_w, emoji, colors["secondary"], 0.5, dpr))
            p.setOpacity(old_op)
            return len(rows) * lh
        base = self._block(line, font, max_w, emoji, _alpha(colors["lyric"], 0.92), 0.35, dpr)
        hl = self._block(line, font, max_w, emoji, colors["highlight"], 1.0, dpr)
        p.setOpacity(old_op * max(0.0, min(1.0, opacity)))
        p.drawPixmap(origin, base)
        y = top
        e_w = lh * 1.05
        for row_w, items in rows:
            x0 = cx - row_w / 2
            sung_end = None
            active_word = None
            for wd, x, ww, e in items:
                prog = max(0.0, min(1.0, (t - wd.start) / max(0.05, wd.end - wd.start)))
                if prog <= 0:
                    break
                if prog >= 1:
                    sung_end = x + ww + (e_w if e else 0) + 2
                else:
                    sung_end = x + ww * prog
                    active_word = (x, ww, prog)
            if sung_end is not None:
                p.save()
                p.setClipRect(QRectF(x0 - pad, y - pad * 0.5, sung_end + pad, lh + pad),
                              Qt.ClipOperation.IntersectClip)
                p.drawPixmap(origin, hl)
                p.restore()
            if active_word is not None:  # soft glow around the word being sung
                ax, aw, prog = active_word
                p.save()
                p.setClipRect(QRectF(x0 + ax - 4, y - 4, aw + 8, lh + 8), Qt.ClipOperation.IntersectClip)
                p.setOpacity(p.opacity() * 0.22 * (1 - prog))
                for dx, dy in ((-1.5, 0), (1.5, 0), (0, -1.5), (0, 1.5)):
                    p.drawPixmap(origin + QPointF(dx, dy), hl)
                p.restore()
            y += lh
        p.setOpacity(old_op)
        return len(rows) * lh

    def _draw_emoji(self, p, e, x, y, lh, opacity):
        p.save()
        p.setOpacity(p.opacity() * max(0.0, min(1.0, opacity)))
        # Colour emoji ignore the pen, but Qt keeps a separate glyph cache per pen colour.
        # A fixed pen stops those caches piling up as album colours change (memory leak).
        p.setPen(EMOJI_PEN)
        p.setFont(self.emoji_font(lh * 0.62))
        p.drawText(QRectF(x + lh * 0.08, y, lh * 1.0, lh), Qt.AlignmentFlag.AlignCenter, e)
        p.restore()

    def big_emoji(self, p, rect, emo, px, opacity):
        dpr = p.device().devicePixelRatioF() if p.device() else 1.0
        key = ("big-emoji", emo, int(px), round(dpr, 2))
        pm = self.cache.get(key)
        if pm is None:
            side = int(px * 1.4)
            pm = QPixmap(max(1, int(side * dpr)), max(1, int(side * dpr)))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            q.setPen(EMOJI_PEN)
            q.setFont(self.emoji_font(px))
            q.drawText(QRectF(0, 0, side, side), Qt.AlignmentFlag.AlignCenter, emo)
            q.end()
            self.cache.put(key, pm)
        side = pm.width() / dpr
        p.save()
        p.setOpacity(opacity)
        p.drawPixmap(QPointF(rect.center().x() - side / 2, rect.center().y() - side / 2), pm)
        p.restore()

    def draw_dots(self, p, cx, cy, size, colors, opacity=1.0):
        now = time.monotonic()
        r = size * 0.13
        for i in range(3):
            ph = (math.sin(now * 3.2 - i * 0.7) + 1) / 2
            p.setBrush(_alpha(colors["highlight"], opacity * (0.35 + 0.65 * ph)))
            p.setPen(Qt.PenStyle.NoPen)
            rr = r * (0.8 + 0.4 * ph)
            p.drawEllipse(QPointF(cx + (i - 1) * r * 3.4, cy), rr, rr)

    # ---------------------------------------------------------------- entry
    def paint(self, p, rect, size):
        c = self.ctrl
        now = time.monotonic()
        dt = min(0.1, now - self._last)
        self._last = now
        lyr = c.lyrics
        if lyr is not self._lyrics_ref:
            self._lyrics_ref = lyr
            self._layouts.clear()
            self.cache.clear()
            self.scroll = None
            self._pop_words = None
            self._pop_scroll = None
        self.cache.prune()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if lyr is None or not lyr.lines:
            self._message(p, rect, size)
            return
        t = c.position()
        idx = lyr.index_at(t)
        target = float(idx)
        if self.scroll is None or abs(target - self.scroll) > 6:
            self.scroll = target
        else:
            self.scroll += (target - self.scroll) * min(1.0, dt * 9)
        style = c.cfg["lyrics_style"]
        p.save()
        p.setClipRect(rect)
        if style == "Pop":
            self._pop(p, rect, size, t, idx, lyr)
        elif style == "Lens":
            self._lens(p, rect, size, t, idx, lyr)
        elif style == "Wall":
            self._wall(p, rect, size, t, idx, lyr)
        else:
            self._karaoke(p, rect, size, t, idx, lyr, visual=(style == "Visual"))
        p.restore()
        if not lyr.synced:
            p.setFont(self.font(max(10, size * 0.32), False))
            p.setPen(_alpha(c.colors["secondary"], 0.7))
            p.drawText(rect.adjusted(0, 0, -4, 0),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                       "unsynced lyrics · approximate timing")

    def _message(self, p, rect, size):
        c = self.ctrl
        np = c.np
        cols = c.colors
        title = np.title or "Nothing playing"
        if np.title:
            sub = c.status_text or np.artist
        else:
            sub = c.status_text or "Play a song in Spotify, Apple Music or your browser"
        p.setFont(self.font(size * 0.8))
        p.setPen(_alpha(cols["lyric"], 0.95))
        fm = QFontMetricsF(p.font())
        cy = rect.center().y()
        if np.title and c.lyrics is not None and c.lyrics.instrumental:
            sub = "Instrumental ♪"
        p.drawText(QRectF(rect.left(), cy - fm.height(), rect.width(), fm.height()),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                   fm.elidedText(title, Qt.TextElideMode.ElideRight, rect.width()))
        p.setFont(self.font(size * 0.45, False))
        p.setPen(_alpha(cols["secondary"], 0.9))
        fm2 = QFontMetricsF(p.font())
        p.drawText(QRectF(rect.left(), cy + 4, rect.width(), fm2.height() * 2.2),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                   sub)

    # ---------------------------------------------------------------- styles
    def _karaoke(self, p, rect, size, t, idx, lyr, visual=False):
        cols = self.ctrl.colors
        maxw = rect.width() * 0.96
        big = self.font(size)
        small = self.font(size * 0.6)
        cx = rect.center().x()
        gap = lyr.in_gap(t, idx)
        spacing = size * 0.35
        shift = (idx - self.scroll) * size * 1.2
        cy = rect.center().y() + shift

        if visual and not gap and idx >= 0:  # large faint emoji behind the line
            emo = None
            for w in lyr.lines[idx].words:
                if t >= w.start and emoji_for(w.text):
                    emo = emoji_for(w.text)
            if emo:
                self.big_emoji(p, rect, emo, min(rect.height() * 0.8, size * 4), 0.16)

        if gap:
            block_h = size * 0.9
            top_c = cy - block_h / 2
            self.draw_dots(p, cx, cy, size, cols)
            prev_i, next_i = idx, idx + 1
        else:
            block_h = self.line_height(lyr.lines[idx], big, maxw, visual)
            top_c = cy - block_h / 2
            self.draw_line(p, lyr.lines[idx], big, maxw, visual, cx, top_c, t, cols, 1.0, True)
            prev_i, next_i = idx - 1, idx + 1

        half = rect.height() / 2 + size
        y = top_c - spacing
        i = prev_i
        while i >= 0:
            h = self.line_height(lyr.lines[i], small, maxw, visual)
            y -= h
            if y + h < rect.top():
                break
            dist = abs((y + h / 2) - rect.center().y())
            self.draw_line(p, lyr.lines[i], small, maxw, visual, cx, y, t, cols,
                           max(0.0, 0.75 - dist / half * 0.6), False)
            y -= spacing
            i -= 1
        y = top_c + block_h + spacing
        i = next_i
        while 0 <= i < len(lyr.lines):
            if y > rect.bottom():
                break
            h = self.line_height(lyr.lines[i], small, maxw, visual)
            dist = abs((y + h / 2) - rect.center().y())
            self.draw_line(p, lyr.lines[i], small, maxw, visual, cx, y, t, cols,
                           max(0.0, 0.85 - dist / half * 0.6), False)
            y += h + spacing
            i += 1

    # ---------------------------------------------------------------- Pop style
    POP_HISTORY = 5          # sung words kept on screen above the current one
    POP_IN = 0.22            # seconds for a word's pop-in animation

    def _word_pixmap(self, text, font, color, dpr):
        """Single word rendered once; reused every frame (cheap to rotate/scale)."""
        c = QColor(color)
        key = ("pop-word", text, font.family(), font.pixelSize(), font.italic(), font.weight(),
               (c.red() >> 3, c.green() >> 3, c.blue() >> 3), round(dpr, 2))
        pm = self.cache.get(key)
        if pm is not None:
            return pm
        fm = QFontMetricsF(font)
        pad = fm.height() * 0.15
        w, h = fm.horizontalAdvance(text) + 2 * pad + fm.height() * 0.1, fm.height() + 2 * pad
        pm = QPixmap(max(1, math.ceil(w * dpr)), max(1, math.ceil(h * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        q.setFont(font)
        q.setPen(c)
        q.drawText(QPointF(pad, pad + fm.ascent()), text)
        q.end()
        self.cache.put(key, pm)
        return pm

    def _emoji_pixmap(self, emo, px, dpr):
        key = ("pop-emoji", emo, int(px), round(dpr, 2))
        pm = self.cache.get(key)
        if pm is None:
            side = px * 1.3
            pm = QPixmap(max(1, int(side * dpr)), max(1, int(side * dpr)))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            q.setPen(EMOJI_PEN)
            q.setFont(self.emoji_font(px))
            q.drawText(QRectF(0, 0, side, side), Qt.AlignmentFlag.AlignCenter, emo)
            q.end()
            self.cache.put(key, pm)
        return pm

    @staticmethod
    def _pop_look(k):
        """A stable, varied look for word #k (size, tilt, offset, italic), so the same
        word always looks the same while the column feels hand-placed."""
        h = (k * 2654435761) & 0xFFFFFFFF
        size = (0.82, 1.0, 1.0, 1.18, 1.38)[h % 5]
        tilt = ((h >> 3) % 11 - 5) * 1.1            # -5.5 .. +5.5 degrees
        shift = ((h >> 7) % 9 - 4) / 4.0            # -1 .. +1 (fraction of max offset)
        italic = (h >> 11) % 4 == 0
        return size, tilt, shift, italic

    @staticmethod
    def _ease_out_back(x):
        c1 = 1.70158
        c3 = c1 + 1
        return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2

    def _pop(self, p, rect, size, t, idx, lyr):
        """One word at a time: each sung word pops in, the current one sits on a
        coloured sticker that wipes in as it's sung, earlier words drift up and fade."""
        cols = self.ctrl.colors
        if self._pop_words is None:
            self._pop_words = [w for ln in lyr.lines for w in ln.words]
            self._pop_starts = [w.start for w in self._pop_words]
        words = self._pop_words
        if not words:
            return
        wi = bisect.bisect_right(self._pop_starts, t) - 1
        now = time.monotonic()
        dt = min(0.1, now - getattr(self, "_pop_last", now))
        self._pop_last = now
        if self._pop_scroll is None or abs(wi - self._pop_scroll) > 8:
            self._pop_scroll = float(wi)
        else:
            self._pop_scroll += (wi - self._pop_scroll) * min(1.0, dt * 12)

        dpr = p.device().devicePixelRatioF() if p.device() else 1.0
        base = min(size * 1.55, rect.height() * 0.30)
        slot = base * 1.02                       # vertical distance between stacked words
        cx, cy = rect.center().x(), rect.center().y() + base * 0.35
        max_shift = min(rect.width() * 0.16, base * 2.2)
        gap = lyr.in_gap(t, idx)

        if gap:
            self.draw_dots(p, cx, cy, size, cols)

        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        lo = max(0, wi - self.POP_HISTORY)
        for k in range(lo, wi + 1):
            w = words[k]
            age_words = wi - k                    # 0 = current word
            sz, tilt, shift, italic = self._pop_look(k)
            px = base * sz
            f = QFont(self.font(px))
            f.setItalic(italic)
            # vertical position: the column slides up as new words arrive
            y = cy - (self._pop_scroll - k) * slot - (base * 0.35 if gap else 0)
            if y < rect.top() - px or y > rect.bottom() + px:
                continue
            fade = max(0.0, 1.0 - age_words * 0.2)
            if gap:
                fade *= 0.45
            shrink = 1.0 - min(0.25, age_words * 0.05)
            # pop-in: overshoot scale + quick fade-in
            a = (t - w.start) / self.POP_IN
            pop = self._ease_out_back(max(0.0, min(1.0, a))) if a < 1 else 1.0
            op = fade * max(0.0, min(1.0, a * 2.0))
            if op <= 0.01:
                continue
            current = age_words == 0 and not gap
            text_color = cols["lyric"] if current else cols["highlight"]
            pm = self._word_pixmap(w.text, f, text_color, dpr)
            pw, ph = pm.width() / dpr, pm.height() / dpr
            emo = emoji_for(w.text)
            p.save()
            p.translate(cx + shift * max_shift, y)
            p.rotate(tilt)
            sc = max(0.05, pop * shrink)
            p.scale(sc, sc)
            p.setOpacity(op)
            if current:
                # sticker box that wipes in while the word is sung
                prog = max(0.0, min(1.0, (t - w.start) / max(0.08, w.end - w.start)))
                box = QRectF(-pw / 2, -ph / 2 + ph * 0.08, pw, ph * 0.86)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(_alpha(cols["highlight"], 0.28))
                p.drawRoundedRect(box, ph * 0.12, ph * 0.12)
                p.setBrush(_alpha(cols["highlight"], 0.92))
                p.drawRoundedRect(QRectF(box.left(), box.top(), max(1.0, box.width() * prog),
                                         box.height()), ph * 0.12, ph * 0.12)
            p.drawPixmap(QPointF(-pw / 2, -ph / 2), pm)
            if emo:
                ep = self._emoji_pixmap(emo, px * 0.62, dpr)
                ew = ep.width() / dpr
                p.drawPixmap(QPointF(pw / 2 + px * 0.05, -ew / 2), ep)
            p.restore()

    def _lens(self, p, rect, size, t, idx, lyr):
        """Fisheye-like list: lines magnify as they approach the centre.
        Each line is rendered once at full size and scaled, so scrolling stays cheap."""
        cols = self.ctrl.colors
        cx, cy = rect.center().x(), rect.center().y()
        maxw = rect.width() * 0.95
        a = 0.28
        gap = lyr.in_gap(t, idx)
        n = len(lyr.lines)
        base = int(self.scroll)
        if gap:
            self.draw_dots(p, cx, cy + size * 1.1 * math.asinh(math.sqrt(a) * (idx + 0.5 - self.scroll)) / math.sqrt(a), size * 0.8, cols)
        for i in range(max(0, base - 8), min(n, base + 9)):
            d = i - self.scroll
            sc = 1.0 / math.sqrt(1 + a * d * d)
            y = cy + size * 1.1 * math.asinh(math.sqrt(a) * d) / math.sqrt(a)
            if gap:
                y += size * 0.45 * (1 if i > idx else -1)
            line = lyr.lines[i]
            op = max(0.0, 1.0 - abs(d) * 0.16)
            f = self.fit_font(line, size, maxw)
            h = self.line_height(line, f, 1e9)
            p.save()
            p.translate(cx, y)
            p.scale(sc, sc)
            if i == idx and not gap:
                self.draw_line(p, line, f, 1e9, False, 0, -h / 2, t, cols, op, True)
            else:
                self.draw_line(p, line, f, 1e9, False, 0, -h / 2, t, cols, op * 0.85, False)
            p.restore()

    def _wall(self, p, rect, size, t, idx, lyr):
        """Lines stack into a wall that drifts in 3D."""
        cols = self.ctrl.colors
        now = time.monotonic()
        gap = lyr.in_gap(t, idx)
        p.translate(rect.center())
        tr = QTransform()
        tr.rotate(math.sin(now * 0.33) * 22, Qt.Axis.YAxis)
        tr.rotate(math.sin(now * 0.21 + 1.0) * 9, Qt.Axis.XAxis)
        p.setTransform(tr, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        maxw = rect.width() * 0.8
        shift = (idx - self.scroll) * size * 1.1
        if gap:
            self.draw_dots(p, 0, shift, size, cols)
            top = shift - size * 0.5
            start_prev = idx
        else:
            f = self.font(size * 1.05)
            h = self.line_height(lyr.lines[idx], f, maxw)
            top = shift - h / 2
            self.draw_line(p, lyr.lines[idx], f, maxw, False, 0, top, t, cols, 1.0, True)
            start_prev = idx - 1
            if idx + 1 < len(lyr.lines):
                fn = self.font(size * 0.55)
                self.draw_line(p, lyr.lines[idx + 1], fn, maxw, False, 0, top + h + size * 0.35,
                               t, cols, 0.45, False)
        y = top - size * 0.2
        for k in range(0, 7):
            i = start_prev - k
            if i < 0:
                break
            f = self.font(size * (0.75 * (0.86 ** k)))
            h = self.line_height(lyr.lines[i], f, maxw)
            y -= h
            self.draw_line(p, lyr.lines[i], f, maxw, False, 0, y, t, cols, max(0.0, 0.8 - k * 0.12), False)
            y -= size * 0.12


# ============================================================================ windows
class LyricsOverlay(QWidget):
    """Floating, draggable, always-on-top lyrics bar."""

    def __init__(self, ctrl):
        super().__init__(None)
        self.ctrl = ctrl
        self.renderer = LyricsRenderer(ctrl)
        self._drag = None
        self._hover = False
        self.setWindowTitle("GlowLyrics")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.grip = QSizeGrip(self)
        self.grip.resize(18, 18)
        self._save_timer = QTimer(self, singleShot=True, interval=500, timeout=self._save_geom)
        self.apply_flags()
        g = ctrl.cfg["overlay_geometry"]
        scr = QGuiApplication.primaryScreen().availableGeometry()
        if g and len(g) == 4 and any(s.availableGeometry().intersects(QRect(*g))
                                     for s in QGuiApplication.screens()):
            self.setGeometry(QRect(*g))
        else:
            w, h = int(scr.width() * 0.6), 230
            self.setGeometry(scr.center().x() - w // 2, scr.bottom() - h - 60, w, h)

    def apply_flags(self):
        locked = self.ctrl.cfg["overlay_locked"]
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                 Qt.WindowType.Tool)
        if locked:
            flags |= Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus
        vis = self.isVisible()
        self.setWindowFlags(flags)
        self.grip.setVisible(not locked)
        if vis:
            self.show()

    def resizeEvent(self, e):
        self.grip.move(self.width() - self.grip.width() - 4, self.height() - self.grip.height() - 4)
        self._save_timer.start()

    def moveEvent(self, e):
        self._save_timer.start()

    def _save_geom(self):
        g = self.geometry()
        self.ctrl.cfg.set("overlay_geometry", [g.x(), g.y(), g.width(), g.height()])

    def enterEvent(self, e):
        self._hover = True

    def leaveEvent(self, e):
        self._hover = False

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None

    def mouseDoubleClickEvent(self, e):
        self.ctrl.open_stage()

    def wheelEvent(self, e):
        step = 2 if e.angleDelta().y() > 0 else -2
        self.ctrl.cfg.set("font_size", max(14, min(96, self.ctrl.cfg["font_size"] + step)))

    def contextMenuEvent(self, e):
        self.ctrl.menu.popup(e.globalPos())

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        bg = self.ctrl.cfg["overlay_bg"]
        if bg > 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(10, 10, 16, int(255 * bg)))
            p.drawRoundedRect(r, 22, 22)
        if self._hover and not self.ctrl.cfg["overlay_locked"]:
            p.setPen(QPen(_alpha(self.ctrl.colors["highlight"], 0.5), 1.5, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, 22, 22)
        size = self.ctrl.cfg["font_size"]
        self.renderer.paint(p, self.rect().adjusted(18, 10, -18, -10), size)
        p.end()


class StageWindow(QWidget):
    """Full-screen lyrics with album-art backdrop, clock and a now-playing card.
    (A cross-platform stand-in for lock-screen lyrics.)"""
    closed = Signal()

    def __init__(self, ctrl, auto=False):
        super().__init__(None)
        self.ctrl = ctrl
        self.auto = auto
        self.renderer = LyricsRenderer(ctrl)
        self._first_mouse = None
        self._bg = None
        self._bg_key = None
        self._clock_pm = None
        self._clock_key = None
        self.setWindowTitle("GlowLyrics Stage")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.BlankCursor)

    def _background(self):
        """Album-art backdrop + dark tint, rendered once per size/artwork and reused."""
        c = self.ctrl
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr, c.bg_pixmap.cacheKey() if c.bg_pixmap else 0)
        if self._bg_key == key and self._bg is not None:
            return self._bg
        W, H = self.width(), self.height()
        pm_out = QPixmap(int(W * dpr), int(H * dpr))
        pm_out.setDevicePixelRatio(dpr)
        pm_out.fill(QColor(6, 6, 10))
        p = QPainter(pm_out)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if c.bg_pixmap is not None and not c.bg_pixmap.isNull():
            pm = c.bg_pixmap
            sc = max(W / pm.width(), H / pm.height())
            tw, th = pm.width() * sc, pm.height() * sc
            p.drawPixmap(QRectF((W - tw) / 2, (H - th) / 2, tw, th), pm, QRectF(pm.rect()))
        grad = QLinearGradient(0, 0, 0, H)
        grad.setColorAt(0, QColor(0, 0, 0, 120))
        grad.setColorAt(0.5, QColor(0, 0, 0, 150))
        grad.setColorAt(1, QColor(0, 0, 0, 200))
        p.fillRect(QRectF(0, 0, W, H), grad)
        p.end()
        self._bg, self._bg_key = pm_out, key
        return pm_out

    def _clock(self, W, H):
        """Clock + date image; re-rendered only when the minute changes."""
        from PySide6.QtCore import QDate, QTime
        text = QTime.currentTime().toString("h:mm")
        date = QDate.currentDate().toString("dddd, MMMM d")
        dpr = self.devicePixelRatioF()
        key = (text, date, W, H, dpr, self.ctrl.cfg["font_family"])
        if self._clock_key == key:
            return self._clock_pm
        pm = QPixmap(int(W * dpr), int(H * 0.22 * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        fam = self.ctrl.cfg["font_family"] or QApplication.font().family()
        f = QFont(fam)
        f.setPixelSize(int(H * 0.11))
        f.setWeight(QFont.Weight.Light)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 230))
        p.drawText(QRectF(0, H * 0.04, W, H * 0.13), Qt.AlignmentFlag.AlignCenter, text)
        f2 = QFont(fam)
        f2.setPixelSize(int(H * 0.026))
        f2.setWeight(QFont.Weight.Medium)
        p.setFont(f2)
        p.setPen(QColor(255, 255, 255, 190))
        p.drawText(QRectF(0, H * 0.165, W, H * 0.04), Qt.AlignmentFlag.AlignCenter, date)
        p.end()
        self._clock_pm, self._clock_key = pm, key
        return pm

    def keyPressEvent(self, e):
        self.close()

    def mousePressEvent(self, e):
        self.close()

    def mouseMoveEvent(self, e):
        pos = e.globalPosition().toPoint()
        if self._first_mouse is None:
            self._first_mouse = pos
        elif (pos - self._first_mouse).manhattanLength() > 25:
            if self.auto:
                self.close()
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def closeEvent(self, e):
        self.closed.emit()
        super().closeEvent(e)

    def paintEvent(self, e):
        c = self.ctrl
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        R = QRectF(self.rect())
        W, H = R.width(), R.height()
        p.drawPixmap(0, 0, self._background())

        top_pad = 0.0
        if c.cfg["stage_clock"]:
            p.drawPixmap(0, 0, self._clock(W, H))
            top_pad = H * 0.2
        size = min(H / 11.0, W / 20.0)
        lyr_rect = QRect(int(W * 0.06), int(top_pad + H * 0.03), int(W * 0.88),
                         int(H * 0.78 - top_pad))
        self.renderer.paint(p, lyr_rect, size)
        self._card(p, W, H)
        p.end()

    def _card(self, p, W, H):
        c = self.ctrl
        np = c.np
        if not np.title:
            return
        cw, ch = min(520.0, W * 0.4), 112.0
        x, y = 40.0, H - ch - 40
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, cw, ch), 26, 26)
        p.fillPath(path, QColor(255, 255, 255, 34))
        p.setPen(QPen(QColor(255, 255, 255, 70), 1))
        p.drawPath(path)
        art = 80.0
        if c.art_pixmap is not None and not c.art_pixmap.isNull():
            ap = QPainterPath()
            ap.addRoundedRect(QRectF(x + 16, y + 16, art, art), 14, 14)
            p.save()
            p.setClipPath(ap)
            p.drawPixmap(QRectF(x + 16, y + 16, art, art), c.art_pixmap, QRectF(c.art_pixmap.rect()))
            p.restore()
        tx = x + 16 + art + 16
        tw = cw - (tx - x) - 20
        fam = c.cfg["font_family"] or QApplication.font().family()
        f = QFont(fam)
        f.setPixelSize(19)
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255))
        fm = QFontMetricsF(f)
        p.drawText(QPointF(tx, y + 40), fm.elidedText(np.title, Qt.TextElideMode.ElideRight, tw))
        f.setPixelSize(15)
        f.setWeight(QFont.Weight.Normal)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 190))
        fm = QFontMetricsF(f)
        p.drawText(QPointF(tx, y + 62), fm.elidedText(np.artist, Qt.TextElideMode.ElideRight, tw))
        if np.duration > 0:
            prog = max(0.0, min(1.0, c.raw_position() / np.duration))
            by = y + 82
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 60))
            p.drawRoundedRect(QRectF(tx, by, tw, 5), 2.5, 2.5)
            p.setBrush(c.colors["highlight"])
            p.drawRoundedRect(QRectF(tx, by, tw * prog, 5), 2.5, 2.5)
            f.setPixelSize(12)
            p.setFont(f)
            p.setPen(QColor(255, 255, 255, 160))

            def mmss(s):
                s = int(max(0, s))
                return f"{s // 60}:{s % 60:02d}"
            p.drawText(QPointF(tx, by + 20), mmss(c.raw_position()))
            r = mmss(np.duration)
            p.drawText(QPointF(tx + tw - QFontMetricsF(f).horizontalAdvance(r), by + 20), r)
