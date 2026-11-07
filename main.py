#!/usr/bin/env python3
# Copyright © 2026 Tirhut LLC. All rights reserved.
"""GlowLyrics launcher.

    python main.py            start normally
    python main.py --demo     start with the built-in demo song
    python main.py --reset    reset all settings
"""
import argparse
import logging
import os
import sys


def main():
    ap = argparse.ArgumentParser(description="GlowLyrics - synced lyrics + music-reactive edge glow")
    ap.add_argument("--demo", action="store_true", help="play the built-in demo song")
    ap.add_argument("--reset", action="store_true", help="reset settings to defaults")
    ap.add_argument("--debug", action="store_true", help="verbose logging")
    args, _unknown = ap.parse_known_args()  # macOS may pass -psn_* args
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 is not installed. Run:  pip install -r requirements.txt")
        sys.exit(1)

    if sys.platform.startswith("win"):
        try:  # own taskbar identity + crisp text on high-DPI screens
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GlowLyrics.App")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("GlowLyrics")
    app.setQuitOnLastWindowClosed(False)

    from glowlyrics.config import Config
    from glowlyrics.controller import Controller

    cfg = Config(reset=args.reset)
    if args.demo:
        cfg.set("demo", True)
    from glowlyrics.legal import ensure_accepted
    if not ensure_accepted(cfg):
        sys.exit(0)
    ctrl = Controller(cfg)  # noqa: F841 (kept alive)
    sys.exit(app.exec())


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
