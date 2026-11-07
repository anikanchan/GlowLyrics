# Copyright © 2026 Tirhut LLC. All rights reserved.
"""Platform window tweaks for the lyrics bar and edge glow.

macOS
  * show on every desktop (Space) and on top of full-screen apps
  * never hide when another app is active
  * optionally appear on the lock screen: while the screen is locked the windows
    are raised above the lock screen (they stay click-through / view-only)
Windows
  * periodically re-assert "always on top" so full-screen browser videos
    don't permanently cover the glow
"""
import ctypes
import logging
import sys

log = logging.getLogger("glowlyrics")
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")

# ---------------------------------------------------------------------------- macOS
_objc = None
if IS_MAC:
    try:
        import objc as _objc  # PyObjC
        from Foundation import NSDistributedNotificationCenter, NSObject
    except Exception as e:  # pragma: no cover
        log.warning("PyObjC not available (%s); Mac window extras disabled", e)
        _objc = None

# NSWindowCollectionBehavior flags
_CAN_JOIN_ALL_SPACES = 1 << 0
_STATIONARY = 1 << 4
_IGNORES_CYCLE = 1 << 6
_FULLSCREEN_AUXILIARY = 1 << 8
_NS_STATUS_WINDOW_LEVEL = 25          # above normal & floating windows, below menus
_shield_level = None


def _shielding_level():
    """Window level of the lock screen (CGShieldingWindowLevel)."""
    global _shield_level
    if _shield_level is None:
        try:
            cg = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
            cg.CGShieldingWindowLevel.restype = ctypes.c_int32
            _shield_level = int(cg.CGShieldingWindowLevel())
        except Exception:
            _shield_level = 2147483628
    return _shield_level


def _nswindow(widget):
    try:
        view = _objc.objc_object(c_void_p=int(widget.winId()))
        return view.window()
    except Exception:
        return None


def available():
    return (IS_MAC and _objc is not None) or IS_WIN


def lock_screen_supported():
    return IS_MAC and _objc is not None


def configure(widgets, locked=False, lock_screen=True):
    """Apply platform window behaviour to the given (shown) widgets."""
    if IS_MAC and _objc is not None:
        level = _shielding_level() + 1 if (locked and lock_screen) else _NS_STATUS_WINDOW_LEVEL
        for w in widgets:
            if not w.isVisible():
                continue
            win = _nswindow(w)
            if win is None:
                continue
            for call in (
                lambda: win.setCollectionBehavior_(_CAN_JOIN_ALL_SPACES | _STATIONARY |
                                                   _IGNORES_CYCLE | _FULLSCREEN_AUXILIARY),
                lambda: win.setHidesOnDeactivate_(False),
                lambda: win.setCanBecomeVisibleWithoutLogin_(bool(lock_screen)),
                lambda: win.level() != level and win.setLevel_(level),
                lambda: locked and lock_screen and win.orderFrontRegardless(),
            ):
                try:
                    call()
                except Exception as e:  # pragma: no cover
                    log.debug("mac window tweak failed: %s", e)
    elif IS_WIN:
        try:
            user32 = ctypes.windll.user32
            HWND_TOPMOST = -1
            SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
            for w in widgets:
                if w.isVisible():
                    user32.SetWindowPos(int(w.winId()), HWND_TOPMOST, 0, 0, 0, 0,
                                        SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
        except Exception as e:  # pragma: no cover
            log.debug("topmost failed: %s", e)


# ---------------------------------------------------------------------------- lock watcher
class LockWatcher:
    """Calls on_change(locked: bool) when the Mac screen is locked or unlocked."""

    def __init__(self, on_change):
        self.locked = False
        self._on_change = on_change
        self._observer = None
        if not (IS_MAC and _objc is not None):
            return
        try:
            self._observer = _make_observer(self._set)
            center = NSDistributedNotificationCenter.defaultCenter()
            center.addObserver_selector_name_object_(self._observer, "locked:",
                                                     "com.apple.screenIsLocked", None)
            center.addObserver_selector_name_object_(self._observer, "unlocked:",
                                                     "com.apple.screenIsUnlocked", None)
        except Exception as e:  # pragma: no cover
            log.warning("lock watcher unavailable: %s", e)
            self._observer = None

    def _set(self, locked):
        if locked != self.locked:
            self.locked = locked
            try:
                self._on_change(locked)
            except Exception as e:  # pragma: no cover
                log.debug("lock callback failed: %s", e)

    def close(self):
        if self._observer is not None:
            try:
                NSDistributedNotificationCenter.defaultCenter().removeObserver_(self._observer)
            except Exception:
                pass
            self._observer = None


_Observer = None


def _make_observer(callback):
    global _Observer
    if _Observer is None:
        class GlowLyricsLockObserver(NSObject):  # noqa: N801 (Objective-C class name)
            def initWithCallback_(self, cb):
                self = _objc.super(GlowLyricsLockObserver, self).init()
                if self is None:
                    return None
                self._cb = cb
                return self

            def locked_(self, note):
                self._cb(True)

            def unlocked_(self, note):
                self._cb(False)

        _Observer = GlowLyricsLockObserver
    return _Observer.alloc().initWithCallback_(callback)
