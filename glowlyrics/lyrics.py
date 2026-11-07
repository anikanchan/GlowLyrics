# Copyright © 2026 Tirhut LLC. All rights reserved.
"""Lyrics: LRC parsing, per-word timing, and fetching from LRCLIB (free, no key)."""
import bisect
import glob
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field

import requests

log = logging.getLogger("glowlyrics")
UA = "GlowLyrics/1.0 (desktop lyrics app)"


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Line:
    start: float
    end: float
    text: str
    words: list = field(default_factory=list)

    @property
    def sung_end(self):
        return self.words[-1].end if self.words else self.end


class Lyrics:
    def __init__(self, lines, synced=True, source="", instrumental=False):
        self.lines = [ln for ln in lines if ln.text.strip()]
        self.synced = synced
        self.source = source
        self.instrumental = instrumental
        self._starts = [ln.start for ln in self.lines]

    def index_at(self, t):
        return bisect.bisect_right(self._starts, t) - 1

    def in_gap(self, t, idx):
        """True during intros / long instrumental breaks."""
        if not self.lines:
            return True
        if idx < 0:
            return True
        nxt = self.lines[idx + 1].start if idx + 1 < len(self.lines) else 1e9
        return t > self.lines[idx].sung_end + 1.2 and nxt - t > 2.0


# --------------------------------------------------------------------------- parsing
_TIME = re.compile(r"\[(\d{1,3}):(\d{1,2}(?:[.:]\d{1,3})?)\]")
_WORD = re.compile(r"<(\d{1,3}):(\d{1,2}(?:[.:]\d{1,3})?)>")
_OFFSET = re.compile(r"^\[offset:\s*([+-]?\d+)\s*\]", re.I)


def _ts(m, s):
    return int(m) * 60 + float(s.replace(":", "."))


def _interpolate_words(text, start, end):
    toks = text.split()
    if not toks:
        return []
    avail = max(0.2, end - start)
    est = 0.3 + sum(0.065 * len(w) + 0.12 for w in toks)  # natural singing pace
    span = min(max(est * 1.4, min(avail, est)), avail * 0.97)
    weights = [len(w) + 2 for w in toks]
    total = sum(weights)
    out, t = [], start
    for w, wt in zip(toks, weights):
        d = span * wt / total
        out.append(Word(w, t, t + d))
        t += d
    return out


def _enhanced_words(body, start, end):
    """Parse A2/enhanced LRC: <mm:ss.xx>word <mm:ss.xx>word ..."""
    parts = _WORD.split(body)
    segs = []
    if parts[0].strip():
        segs.append((start, parts[0]))
    for i in range(1, len(parts) - 2, 3):
        segs.append((_ts(parts[i], parts[i + 1]), parts[i + 2]))
    words = []
    for j, (st, txt) in enumerate(segs):
        en = segs[j + 1][0] if j + 1 < len(segs) else end
        if txt.strip():
            words.extend(_interpolate_words(txt, st, max(st + 0.05, en)))
    return words


def parse_lrc(text, duration=0.0, source=""):
    offset = 0.0
    entries = []
    for raw in text.splitlines():
        raw = raw.strip()
        mo = _OFFSET.match(raw)
        if mo:
            offset = int(mo.group(1)) / 1000.0
            continue
        tags, pos = [], 0
        while True:
            m = _TIME.match(raw, pos)
            if not m:
                break
            tags.append(_ts(m.group(1), m.group(2)))
            pos = m.end()
        if not tags:
            continue
        body = raw[pos:]
        for st in tags:
            entries.append((max(0.0, st - offset), body))
    entries.sort(key=lambda e: e[0])
    lines = []
    for i, (st, body) in enumerate(entries):
        nxt = entries[i + 1][0] if i + 1 < len(entries) else (max(duration, st + 6.0))
        clean = re.sub(r"\s+", " ", _WORD.sub("", body)).strip()
        if not clean:
            continue
        if _WORD.search(body):
            words = _enhanced_words(body, st, nxt)
        else:
            words = _interpolate_words(clean, st, nxt)
        lines.append(Line(st, nxt, clean, words))
    return Lyrics(lines, synced=True, source=source)


def plain_to_lyrics(text, duration, source=""):
    rows = [r.strip() for r in text.splitlines() if r.strip()]
    if not rows:
        return None
    duration = duration or 180.0
    a, b = duration * 0.06, duration * 0.94
    step = (b - a) / len(rows)
    lines = []
    for i, r in enumerate(rows):
        st = a + i * step
        lines.append(Line(st, st + step, r, _interpolate_words(r, st, st + step)))
    return Lyrics(lines, synced=False, source=source)


# --------------------------------------------------------------------------- title cleanup
_JUNK = re.compile(
    r"\s*[\(\[][^\)\]]*(feat\.?|ft\.|remaster|version|edit|live|mono|stereo|deluxe|bonus|official|"
    r"lyric|audio|video|visualizer|hd|4k|explicit|clean)[^\)\]]*[\)\]]", re.I)
_DASH_JUNK = re.compile(r"\s+-\s+.*(remaster|version|edit|live|mono|stereo|mix|single).*$", re.I)


def clean_track(title, artist):
    t, a = title or "", artist or ""
    a = re.sub(r"(VEVO|\s*-\s*Topic)$", "", a.strip(), flags=re.I).strip()
    if " - " in t and (not a or t.lower().startswith(a.lower()) or len(a) < 2):
        left, right = t.split(" - ", 1)
        a, t = left.strip(), right.strip()
    t = _DASH_JUNK.sub("", _JUNK.sub("", t)).strip()
    t = re.sub(r"\s*(feat\.?|ft\.)\s.*$", "", t, flags=re.I).strip()
    a_main = re.split(r",|\s&\s|\sfeat\.?\s|\sft\.\s|\sx\s|;", a, flags=re.I)[0].strip()
    return t, a_main


def _safe(s):
    return re.sub(r'[\\/:*?"<>|]+', "", s).strip().lower()


# --------------------------------------------------------------------------- fetcher
class LyricsFetcher:
    API = "https://lrclib.net/api"

    def __init__(self, cache_dir, local_dir):
        self.cache_dir = cache_dir
        self.local_dir = local_dir
        self.http = requests.Session()
        self.http.headers["User-Agent"] = UA

    def prune_cache(self, max_files=3000, max_age_days=180):
        """Keeps the on-disk lyrics cache bounded (oldest entries removed first)."""
        try:
            files = [os.path.join(self.cache_dir, f) for f in os.listdir(self.cache_dir)
                     if f.endswith(".json")]
            files.sort(key=lambda p: os.path.getmtime(p))
            cutoff = time.time() - max_age_days * 86400
            excess = len(files) - max_files
            for i, p in enumerate(files):
                if i < excess or os.path.getmtime(p) < cutoff:
                    os.remove(p)
        except OSError:
            pass

    def get(self, title, artist, album="", duration=0.0):
        if not title:
            return None
        local = self._local(title, artist, duration)
        if local:
            return local
        key = hashlib.sha1(f"{artist}|{title}".lower().encode("utf-8")).hexdigest()
        path = os.path.join(self.cache_dir, key + ".json")
        rec = None
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    rec = json.load(f)
                if not rec.get("synced") and not rec.get("plain") and not rec.get("instrumental") \
                        and time.time() - rec.get("ts", 0) > 86400:
                    rec = None  # retry misses after a day
            except Exception:
                rec = None
        if rec is None:
            rec = self._fetch(title, artist, album, duration)
            if rec is not None:
                rec["ts"] = time.time()
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(rec, f)
                except Exception:
                    pass
        if not rec:
            return None
        if rec.get("instrumental"):
            return Lyrics([], instrumental=True, source="LRCLIB")
        if rec.get("synced"):
            return parse_lrc(rec["synced"], duration, "LRCLIB")
        if rec.get("plain"):
            return plain_to_lyrics(rec["plain"], duration, "LRCLIB (unsynced)")
        return None

    def _local(self, title, artist, duration):
        t, a = _safe(title), _safe(artist)
        ct, ca = clean_track(title, artist)
        wanted = {f"{a} - {t}.lrc", f"{t}.lrc", f"{_safe(ca)} - {_safe(ct)}.lrc", f"{_safe(ct)}.lrc"}
        for p in glob.glob(os.path.join(self.local_dir, "*.lrc")):
            if os.path.basename(p).lower() in wanted:
                try:
                    with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
                        return parse_lrc(f.read(), duration, "Local file")
                except Exception:
                    pass
        return None

    def _req(self, endpoint, params):
        try:
            r = self.http.get(f"{self.API}/{endpoint}", params=params, timeout=8)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            log.debug("lrclib error: %s", e)
            raise
        return None

    def _fetch(self, title, artist, album, duration):
        ct, ca = clean_track(title, artist)
        tries = []
        if duration > 0:
            tries.append({"track_name": title, "artist_name": artist, "album_name": album,
                          "duration": int(round(duration))})
        try:
            for params in tries:
                d = self._req("get", params)
                if d and (d.get("syncedLyrics") or d.get("instrumental")):
                    return self._rec(d)
            best, best_score = None, -1e9
            for q in ({"track_name": ct, "artist_name": ca}, {"q": f"{ca} {ct}"}):
                res = self._req("search", q) or []
                for d in res[:20]:
                    sc = 0.0
                    if d.get("syncedLyrics"):
                        sc += 100
                    elif d.get("plainLyrics"):
                        sc += 20
                    elif d.get("instrumental"):
                        sc += 10
                    if duration and d.get("duration"):
                        sc -= min(60, abs(d["duration"] - duration) * 4)
                    if ca and ca.lower() in (d.get("artistName") or "").lower():
                        sc += 30
                    if ct.lower() == (d.get("trackName") or "").lower():
                        sc += 20
                    if sc > best_score:
                        best, best_score = d, sc
                if best is not None and best.get("syncedLyrics"):
                    break
            return self._rec(best) if best else {"synced": None, "plain": None}
        except Exception:
            return None  # network problem: don't cache

    @staticmethod
    def _rec(d):
        return {"synced": d.get("syncedLyrics"), "plain": d.get("plainLyrics"),
                "instrumental": bool(d.get("instrumental"))}


# --------------------------------------------------------------------------- demo song
DEMO_LRC = """[ti:Neon Afterglow]
[00:03.00]Press play and watch the edges glow
[00:07.20]Every word lights up as it goes
[00:11.40]Colors pulled from the album art
[00:15.60]Beating in time with your heart
[00:20.00]
[00:22.00]City lights and a midnight drive
[00:26.20]Stars and rain make the screen come alive
[00:30.40]Sing it loud under the moon
[00:34.60]Fire and music, dancing in tune
[00:39.00]
[00:41.00]<00:41.00>Oh <00:41.60>oh <00:42.20>let <00:42.60>the <00:43.00>night <00:43.80>shine
[00:45.20]Love is a song and the rhythm is mine
[00:49.40]Hold on tight to the summer sky
[00:53.60]Glow on, glow on, never say goodbye
"""
