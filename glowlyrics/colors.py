# Copyright © 2026 Tirhut LLC. All rights reserved.
"""Album art fetching and colour palette extraction."""
import colorsys
import io
import logging
import urllib.parse

import requests
from PIL import Image, ImageDraw, ImageFilter

log = logging.getLogger("glowlyrics")


def fetch_art(np, http=None):
    """Return album art bytes for a NowPlaying, or None."""
    if np.art_bytes:
        return np.art_bytes
    http = http or requests
    url = np.art_url
    if url and url.startswith("file://"):
        try:
            with open(urllib.parse.unquote(url[7:]), "rb") as f:
                return f.read()
        except Exception:
            url = None
    if url and url.startswith("http"):
        try:
            r = http.get(url, timeout=8)
            if r.ok and r.content:
                return r.content
        except Exception:
            pass
    # Fallback: iTunes Search API (free, no key)
    from .lyrics import clean_track
    t, a = clean_track(np.title, np.artist)
    if not t:
        return None
    try:
        r = http.get("https://itunes.apple.com/search",
                     params={"term": f"{a} {t}", "entity": "song", "limit": 5}, timeout=8)
        results = r.json().get("results", []) if r.ok else []
        pick = None
        for res in results:
            if a and a.lower() in (res.get("artistName") or "").lower():
                pick = res
                break
        pick = pick or (results[0] if results else None)
        if pick and pick.get("artworkUrl100"):
            big = pick["artworkUrl100"].replace("100x100", "600x600")
            r2 = http.get(big, timeout=8)
            if r2.ok:
                return r2.content
    except Exception as e:
        log.debug("itunes art failed: %s", e)
    return None


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def _vivid(rgb, min_s=0.5, min_v=0.9):
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    s = max(s, min_s) if s > 0.06 else s
    v = max(v, min_v)
    return tuple(c * 255 for c in colorsys.hsv_to_rgb(h, s, v))


def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def extract_palette(img_bytes):
    """Returns dict of hex colours: glow1, glow2, lyric, highlight, secondary."""
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    except Exception:
        return None
    im.thumbnail((96, 96))
    q = im.quantize(colors=10, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    colors = q.getcolors() or []
    total = sum(c for c, _ in colors) or 1
    cands = []
    for count, idx in colors:
        rgb = tuple(pal[idx * 3: idx * 3 + 3])
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
        score = (count / total) ** 0.6 * (0.15 + s) * (0.15 + v)
        if v < 0.12:
            score *= 0.2
        cands.append((score, rgb, h, s, v))
    if not cands:
        return None
    cands.sort(reverse=True)
    primary = cands[0]
    secondary = None
    for c in cands[1:]:
        dh = min(abs(c[2] - primary[2]), 1 - abs(c[2] - primary[2]))
        if (dh > 0.07 and c[3] > 0.15) or abs(c[4] - primary[4]) > 0.35:
            secondary = c
            break
    p_rgb = primary[1]
    if secondary:
        s_rgb = secondary[1]
    else:  # derive a neighbour hue
        h, s, v = primary[2], primary[3], primary[4]
        s_rgb = tuple(c * 255 for c in colorsys.hsv_to_rgb((h + 0.09) % 1, max(s, 0.5), max(v, 0.8)))
    g1, g2 = _vivid(p_rgb), _vivid(s_rgb)
    highlight = _vivid(p_rgb, 0.45, 1.0)
    lyric = _mix((255, 255, 255), g1, 0.08)
    secondary_txt = _mix((165, 170, 185), g2, 0.25)
    return {"glow1": _hex(g1), "glow2": _hex(g2), "lyric": _hex(lyric),
            "highlight": _hex(highlight), "secondary": _hex(secondary_txt)}


def blurred_background(img_bytes, size=(480, 300)):
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    except Exception:
        return None
    w, h = im.size
    tw, th = size
    scale = max(tw / w, th / h)
    im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    left, top = (im.width - tw) // 2, (im.height - th) // 2
    im = im.crop((left, top, left + tw, top + th)).filter(ImageFilter.GaussianBlur(28))
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def demo_art():
    """Generated cover for demo mode."""
    size = 400
    im = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(im)
    for y in range(size):
        t = y / size
        d.line([(0, y), (size, y)], fill=(int(255 * (1 - t) + 60 * t), int(40 + 30 * t), int(120 + 135 * t)))
    d.ellipse((90, 90, 310, 310), outline=(255, 210, 63), width=14)
    d.ellipse((170, 170, 230, 230), fill=(255, 210, 63))
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()
