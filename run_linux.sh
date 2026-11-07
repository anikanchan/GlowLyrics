#!/bin/bash
# Copyright © 2026 Tirhut LLC. All rights reserved.
# Run GlowLyrics on Linux. Needs python3, python3-venv and playerctl.
cd "$(dirname "$0")" || exit 1
command -v playerctl >/dev/null 2>&1 || echo "Tip: install 'playerctl' so GlowLyrics can see what's playing."
# (re)install when requirements.txt changed since the last install
if ! cmp -s requirements.txt .venv/installed.ok; then
  echo "Installing/updating GlowLyrics components..."
  python3 -m venv .venv && \
  .venv/bin/python -m pip install --upgrade pip && \
  .venv/bin/python -m pip install -r requirements.txt && \
  cp requirements.txt .venv/installed.ok || { echo "Setup failed."; exit 1; }
fi
exec .venv/bin/python main.py "$@"
