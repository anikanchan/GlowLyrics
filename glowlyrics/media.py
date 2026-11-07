# Copyright © 2026 Tirhut LLC. All rights reserved.
"""Detects what's playing (title, artist, position) on Windows, macOS and Linux."""
import asyncio
import json
import logging
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from PySide6.QtCore import QThread, Signal

log = logging.getLogger("glowlyrics")


@dataclass
class NowPlaying:
    title: str = ""
    artist: str = ""
    album: str = ""
    duration: float = 0.0
    position: float = 0.0
    playing: bool = False
    art_bytes: bytes = None
    art_url: str = None
    source: str = ""
    stamp: float = field(default_factory=time.monotonic)

    def key(self):
        return (self.title.strip().lower(), self.artist.strip().lower())

    def current_position(self):
        return self.position + ((time.monotonic() - self.stamp) if self.playing else 0.0)


def _num(v):
    try:
        return float(str(v).strip().replace(",", "."))
    except Exception:
        return 0.0


def _secs(v):
    """Convert a WinRT TimeSpan (timedelta / int ticks / struct) to seconds."""
    if v is None:
        return 0.0
    if hasattr(v, "total_seconds"):
        return v.total_seconds()
    if hasattr(v, "duration"):
        return v.duration / 1e7
    try:
        return float(v) / 1e7
    except Exception:
        return 0.0


# --------------------------------------------------------------------------- Windows
class WindowsProvider:
    """Uses Windows' media session API - works with Spotify, Apple Music,
    browsers (YouTube, etc.), and most players that show in the volume flyout."""

    PREFERRED = ("spotify", "applemusic", "apple music", "itunes", "zunemusic", "musicbee",
                 "foobar", "aimp", "tidal", "deezer", "vlc", "chrome", "msedge", "firefox", "opera")

    def __init__(self):
        try:
            from winrt.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as M,
                GlobalSystemMediaTransportControlsSessionPlaybackStatus as S)
            self.ns = "winrt"
        except ImportError:
            from winsdk.windows.media.control import (  # older package name
                GlobalSystemMediaTransportControlsSessionManager as M,
                GlobalSystemMediaTransportControlsSessionPlaybackStatus as S)
            self.ns = "winsdk"
        self.M, self.S = M, S
        self.loop = asyncio.new_event_loop()
        self.manager = None
        self._seen_key = None
        self._art_key = None
        self._art = None

    def poll(self):
        return self.loop.run_until_complete(self._poll())

    async def _poll(self):
        if self.manager is None:
            self.manager = await self.M.request_async()
        sessions = list(self.manager.get_sessions())
        if not sessions:
            return NowPlaying()

        def score(s):
            sc = 0
            try:
                if s.get_playback_info().playback_status == self.S.PLAYING:
                    sc += 100
            except Exception:
                pass
            app = (s.source_app_user_model_id or "").lower()
            for i, k in enumerate(self.PREFERRED):
                if k in app:
                    sc += 50 - i
                    break
            return sc

        s = max(sessions, key=score)
        props = await s.try_get_media_properties_async()
        info = s.get_playback_info()
        tl = s.get_timeline_properties()
        playing = info.playback_status == self.S.PLAYING
        dur = max(0.0, _secs(tl.end_time) - _secs(tl.start_time))
        pos = _secs(tl.position)
        if playing:
            lu = getattr(tl, "last_updated_time", None)
            if isinstance(lu, datetime):
                if lu.tzinfo is None:
                    lu = lu.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - lu).total_seconds()
                if 0 <= age < 3600:
                    pos += age
        if dur > 0:
            pos = min(pos, dur)
        np = NowPlaying(title=props.title or "",
                        artist=props.artist or getattr(props, "album_artist", "") or "",
                        album=props.album_title or "", duration=dur, position=max(0.0, pos),
                        playing=playing, source=s.source_app_user_model_id or "windows")
        key = np.key()
        # Read artwork on the 2nd poll of a track so we don't get the previous song's art.
        if key == self._seen_key and key != self._art_key:
            self._art_key = key
            self._art = None
            if props.thumbnail is not None:
                try:
                    self._art = await self._read_thumb(props.thumbnail)
                except Exception as e:  # pragma: no cover
                    log.debug("thumbnail read failed: %s", e)
        self._seen_key = key
        np.art_bytes = self._art if self._art_key == key else None
        return np

    async def _read_thumb(self, ref):
        if self.ns == "winrt":
            from winrt.windows.storage.streams import Buffer, DataReader, InputStreamOptions
        else:
            from winsdk.windows.storage.streams import Buffer, DataReader, InputStreamOptions
        stream = await ref.open_read_async()
        size = int(stream.size)
        if size <= 0 or size > 20_000_000:
            return None
        buf = Buffer(size)
        await stream.read_async(buf, size, InputStreamOptions.READ_AHEAD)
        for conv in (bytes, lambda b: bytes(memoryview(b))):
            try:
                data = conv(buf)
                if data:
                    return data[: buf.length]
            except TypeError:
                pass
        reader = DataReader.from_buffer(buf)
        data = bytearray(buf.length)
        reader.read_bytes(data)
        return bytes(data)


# --------------------------------------------------------------------------- macOS
# One long-running JavaScript-for-Automation helper reports the player state twice a
# second, instead of launching a new `osascript` process every poll (much cheaper).
# If GlowLyrics exits, writing to the closed pipe fails and the helper ends too.
_JXA_LOOP = r"""
ObjC.import('Foundation');
var out = $.NSFileHandle.fileHandleWithStandardOutput;
function emit(s) {
  out.writeData($.NSString.alloc.initWithUTF8String(s + "\n").dataUsingEncoding($.NSUTF8StringEncoding));
}
function info(name) {
  try {
    var app = Application(name);
    if (!app.running()) return null;
    var st = app.playerState();
    if (st === "stopped") return null;
    var t = app.currentTrack;
    var r = {player: name, state: st, title: t.name(), artist: t.artist(), album: t.album(),
             position: app.playerPosition(), duration: t.duration()};
    if (name === "Spotify") { r.duration = r.duration / 1000; try { r.art = t.artworkUrl(); } catch (e) {} }
    return r;
  } catch (e) { return null; }
}
while (true) {
  var a = info("Spotify"), b = info("Music");
  var pick = (a && a.state === "playing") ? a : (b && b.state === "playing") ? b : (a || b);
  emit(JSON.stringify(pick));
  delay(0.5);
}
"""


_JXA_ONCE = _JXA_LOOP.split("while (true)")[0].replace(
    "ObjC.import('Foundation');", "") + """
var a = info("Spotify"), b = info("Music");
var pick = (a && a.state === "playing") ? a : (b && b.state === "playing") ? b : (a || b);
JSON.stringify(pick);
"""


class MacProvider:
    """Reads Spotify / Apple Music (macOS asks once for Automation permission)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._line = None
        self._line_time = 0.0
        self._proc = None
        self._started = 0.0
        self._restarts = 0
        self._fallback = False
        self._start()

    def _poll_once(self):
        out = subprocess.run(["osascript", "-l", "JavaScript", "-e", _JXA_ONCE],
                             capture_output=True, text=True, timeout=4).stdout.strip()
        with self._lock:
            self._line, self._line_time = out, time.monotonic()
        return self._parse(out, self._line_time)

    def _start(self):
        self._started = time.monotonic()
        self._proc = subprocess.Popen(["osascript", "-l", "JavaScript", "-e", _JXA_LOOP],
                                      stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, text=True, bufsize=1)
        threading.Thread(target=self._reader, args=(self._proc,), daemon=True).start()

    def _reader(self, proc):
        try:
            for line in proc.stdout:
                with self._lock:
                    self._line = line.strip()
                    self._line_time = time.monotonic()
        except Exception:
            pass

    def poll(self):
        if self._fallback:
            return self._poll_once()
        if self._proc.poll() is not None and time.monotonic() - self._started > 3:
            self._restarts += 1
            if self._restarts >= 3 and self._line is None:
                self._fallback = True  # helper can't run here: use one-shot polling
                return self._poll_once()
            self._start()  # helper ended (e.g. permission dialog dismissed): restart
        with self._lock:
            line, when = self._line, self._line_time
        if time.monotonic() - when > 5:
            return NowPlaying()
        return self._parse(line, when)

    @staticmethod
    def _parse(line, when):
        if not line or line == "null":
            return NowPlaying()
        d = json.loads(line)
        return NowPlaying(title=d.get("title") or "", artist=d.get("artist") or "",
                          album=d.get("album") or "", duration=_num(d.get("duration")),
                          position=_num(d.get("position")), playing=d.get("state") == "playing",
                          art_url=d.get("art") or None, source=d.get("player", "mac"),
                          stamp=when)

    def close(self):
        try:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
        except Exception:
            pass


# --------------------------------------------------------------------------- Linux
class LinuxProvider:
    """Uses MPRIS through `playerctl` (install it with your package manager)."""

    FMT = "{{playerName}}\t{{status}}\t{{title}}\t{{artist}}\t{{album}}\t{{position}}\t{{mpris:length}}\t{{mpris:artUrl}}"

    def poll(self):
        out = subprocess.run(["playerctl", "-a", "metadata", "--format", self.FMT],
                             capture_output=True, text=True, timeout=3).stdout
        best, best_score = None, -1
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) < 8:
                continue
            name, status, title, artist, album, pos, length, art = parts[:8]
            sc = (100 if status == "Playing" else 0) + (10 if "spotify" in name.lower() else 0)
            if title and sc > best_score:
                best_score = sc
                best = NowPlaying(title=title, artist=artist, album=album,
                                  position=_num(pos) / 1e6, duration=_num(length) / 1e6,
                                  playing=status == "Playing", art_url=art or None, source=name)
        return best or NowPlaying()


# --------------------------------------------------------------------------- Demo
class DemoProvider:
    TITLE, ARTIST, ALBUM, DURATION = "Neon Afterglow", "GlowLyrics Demo", "Demo Sessions", 62.0

    def __init__(self):
        self.start = time.monotonic()

    def poll(self):
        pos = (time.monotonic() - self.start) % self.DURATION
        return NowPlaying(title=self.TITLE, artist=self.ARTIST, album=self.ALBUM,
                          duration=self.DURATION, position=pos, playing=True, source="demo")


def make_provider():
    try:
        if sys.platform.startswith("win"):
            return WindowsProvider()
        if sys.platform == "darwin":
            return MacProvider()
        return LinuxProvider()
    except Exception as e:
        log.warning("Media detection unavailable: %s", e)
        return None


class MediaWatcher(QThread):
    updated = Signal(object)
    problem = Signal(str)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self._stop = False

    def stop(self):
        self._stop = True
        self.wait(3000)

    def run(self):
        provider = make_provider()  # created in this thread (needed for WinRT COM)
        if provider is None:
            self.problem.emit("Media detection isn't available on this system. "
                              "See README for requirements. Demo mode still works.")
        demo = DemoProvider()
        errors = 0
        while not self._stop:
            try:
                if self.cfg["demo"]:
                    np = demo.poll()
                elif provider is not None:
                    np = provider.poll()
                else:
                    np = NowPlaying()
                errors = 0
            except FileNotFoundError:
                np = NowPlaying()
                if errors == 0:
                    self.problem.emit("Couldn't find 'playerctl'. Install it to detect music on Linux.")
                errors += 1
            except Exception as e:
                log.debug("poll failed: %s", e)
                np = NowPlaying()
                errors += 1
                if errors % 20 == 0 and not isinstance(provider, DemoProvider):
                    if provider is not None and hasattr(provider, "close"):
                        provider.close()
                    provider = make_provider()
            self.updated.emit(np)
            for _ in range(5):
                if self._stop:
                    break
                self.msleep(100)
        if provider is not None and hasattr(provider, "close"):
            provider.close()
