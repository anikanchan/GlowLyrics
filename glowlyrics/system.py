# Copyright © 2026 Tirhut LLC. All rights reserved.
"""OS helpers: config folder, keep-display-awake, user idle time."""
import ctypes
import os
import re
import subprocess
import sys

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


def app_dir() -> str:
    if IS_WIN:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "GlowLyrics")
    elif IS_MAC:
        path = os.path.expanduser("~/Library/Application Support/GlowLyrics")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        path = os.path.join(base, "glowlyrics")
    os.makedirs(path, exist_ok=True)
    return path


def sub_dir(name: str) -> str:
    path = os.path.join(app_dir(), name)
    os.makedirs(path, exist_ok=True)
    return path


def open_folder(path: str):
    try:
        if IS_WIN:
            os.startfile(path)  # noqa
        elif IS_MAC:
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


class KeepAwake:
    """Stops the display from sleeping while music is playing."""

    def __init__(self):
        self.active = False
        self._proc = None

    def set(self, on: bool):
        if on == self.active:
            return
        self.active = on
        try:
            if IS_WIN:
                ES_CONTINUOUS, ES_DISPLAY_REQUIRED, ES_SYSTEM_REQUIRED = 0x80000000, 0x2, 0x1
                flags = ES_CONTINUOUS | (ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED if on else 0)
                ctypes.windll.kernel32.SetThreadExecutionState(flags)
            elif IS_MAC:
                if on:
                    self._proc = subprocess.Popen(["caffeinate", "-d", "-w", str(os.getpid())])
                elif self._proc:
                    self._proc.terminate()
                    self._proc = None
            elif IS_LINUX:
                pass  # most desktops respect media players' own inhibit
        except Exception:
            pass


_cg = None


def _mac_idle():
    global _cg
    try:
        if _cg is None:
            _cg = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
            fn = _cg.CGEventSourceSecondsSinceLastEventType
            fn.restype = ctypes.c_double
            fn.argtypes = [ctypes.c_int32, ctypes.c_uint32]
        # kCGEventSourceStateHIDSystemState = 1, kCGAnyInputEventType = ~0
        return float(_cg.CGEventSourceSecondsSinceLastEventType(1, 0xFFFFFFFF))
    except Exception:
        return None


def idle_seconds():
    """Seconds since the last keyboard/mouse input, or None if unknown."""
    try:
        if IS_WIN:
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                ticks = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
                return ((ticks - lii.dwTime) & 0xFFFFFFFF) / 1000.0
        elif IS_MAC:
            fast = _mac_idle()  # CoreGraphics: instant, no subprocess
            if fast is not None:
                return fast
            out = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True,
                                 text=True, timeout=2).stdout
            m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
            if m:
                return int(m.group(1)) / 1e9
        else:
            out = subprocess.run(["xprintidle"], capture_output=True, text=True, timeout=2).stdout
            return int(out.strip()) / 1000.0
    except Exception:
        return None
    return None
