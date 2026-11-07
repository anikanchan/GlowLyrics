#!/bin/bash
# Copyright © 2026 Tirhut LLC. All rights reserved.
# Double-click to run GlowLyrics on macOS.
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.9+ is required. Install it from https://www.python.org/downloads/"
  read -r -p "Press Enter to close"
  exit 1
fi
if [ ! -f .venv/installed.ok ]; then
  echo "First run - installing GlowLyrics. This takes a minute or two..."
  python3 -m venv .venv && \
  .venv/bin/python -m pip install --upgrade pip && \
  .venv/bin/python -m pip install -r requirements.txt && \
  touch .venv/installed.ok || { echo "Setup failed."; read -r -p "Press Enter to close"; exit 1; }
fi
nohup .venv/bin/python main.py "$@" >/dev/null 2>&1 &
echo "GlowLyrics started - look for the ♪ icon in the menu bar. You can close this window."
