#!/bin/bash
# Copyright © 2026 Tirhut LLC. All rights reserved.
# Builds dist/GlowLyrics.app and a shareable dist/GlowLyrics-<ver>-mac-<arch>.dmg
# Usage:  ./build_mac_app.sh
set -e
cd "$(dirname "$0")"
VERSION="${VERSION:-1.0.0}"   # CI passes the version from the git tag
ARCH="$(uname -m)"

command -v python3 >/dev/null 2>&1 || { echo "Python 3.9+ is required (python.org)."; exit 1; }

# (re)install when requirements.txt changed since the last install
if ! cmp -s requirements.txt .venv/installed.ok; then
  echo "==> Setting up Python environment"
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
  cp requirements.txt .venv/installed.ok
fi

echo "==> Installing PyInstaller"
.venv/bin/python -m pip install -q "pyinstaller>=6.3"

echo "==> Making app icon"
rm -rf build/GlowLyrics.iconset build/GlowLyrics.icns
mkdir -p build
QT_QPA_PLATFORM=offscreen .venv/bin/python tools/make_icns.py build/GlowLyrics.iconset
iconutil -c icns build/GlowLyrics.iconset -o build/GlowLyrics.icns

echo "==> Collecting open-source licenses"
.venv/bin/python tools/gen_licenses.py THIRD-PARTY-LICENSES.txt

echo "==> Building GlowLyrics.app"
.venv/bin/python -m PyInstaller --noconfirm --clean --windowed --name GlowLyrics \
  --icon build/GlowLyrics.icns --osx-bundle-identifier com.glowlyrics.app \
  --add-data "LICENSE.txt:." --add-data "THIRD-PARTY-NOTICES.txt:." \
  --add-data "THIRD-PARTY-LICENSES.txt:." main.py

APP="dist/GlowLyrics.app"
PL="$APP/Contents/Info.plist"
pset() {  # key type value
  /usr/libexec/PlistBuddy -c "Set :$1 $3" "$PL" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Add :$1 $2 $3" "$PL"
}
pset LSUIElement bool true                      # menu-bar app, no Dock icon
pset CFBundleShortVersionString string "$VERSION"
pset CFBundleVersion string "$VERSION"
pset CFBundleDisplayName string GlowLyrics
pset LSMinimumSystemVersion string 12.0
pset NSHumanReadableCopyright string "Copyright © 2026 Tirhut LLC. All rights reserved."
pset NSAudioCaptureUsageDescription string "GlowLyrics listens to your Mac's sound output to pulse the glow with the beat. Audio is analysed on your Mac only and never recorded or sent."
pset NSAppleEventsUsageDescription string "GlowLyrics reads the current song and playback position from Spotify and Apple Music."

echo "==> Signing (ad-hoc)"
codesign --force --deep --sign - "$APP"

echo "==> Creating DMG"
rm -rf build/dmg
mkdir -p build/dmg
cp -R "$APP" build/dmg/
ln -s /Applications build/dmg/Applications
cp "tools/READ ME FIRST.txt" LICENSE.txt THIRD-PARTY-NOTICES.txt THIRD-PARTY-LICENSES.txt build/dmg/
DMG="dist/GlowLyrics-$VERSION-mac-$ARCH.dmg"
rm -f "$DMG"
# hdiutil occasionally fails with "Resource busy" right after a build: retry a few times
for attempt in 1 2 3 4 5; do
  hdiutil create -volname GlowLyrics -srcfolder build/dmg -ov -format UDZO "$DMG" >/dev/null && break
  echo "hdiutil busy, retrying ($attempt)..."; sleep 5
done
[ -f "$DMG" ] || { echo "DMG creation failed"; exit 1; }

echo
echo "Done!"
echo "  App: $(pwd)/$APP"
echo "  DMG: $(pwd)/$DMG   <- share this file"
