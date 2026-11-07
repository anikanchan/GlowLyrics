# GlowLyrics

Word-by-word synced lyrics plus a screen-edge glow that follows your music.
Lyrics light up word by word as they're sung, while a soft glow around the edges of your screen
takes its colours from the album art and moves with the beat. It's a free desktop app
for **Mac and Windows**, written in Python.

**Idea by Shriyans Raut.**

---

## Contents

1. [Features](#features)
2. [Supported music apps](#supported-music-apps)
3. [For users: install the ready-made app](#for-users-install-the-ready-made-app)
4. [For developers: run from source](#for-developers-run-from-source)
5. [Build a shareable app](#build-a-shareable-app)
6. [Using GlowLyrics](#using-glowlyrics)
7. [Your own lyrics files](#your-own-lyrics-files)
8. [Privacy & performance](#privacy--performance)
9. [Troubleshooting](#troubleshooting)
10. [Notes & limitations](#notes--limitations)
11. [Project layout](#project-layout)
12. [License, credits & copyright](#license)

---

## Features

**Lyrics**
- A floating lyrics bar that stays on top of other windows. Each word lights up as it's sung.
- Five styles:
  - **Karaoke:** the current line is large, with the lines before and after it smaller.
  - **Pop:** one word at a time. Each word pops in as it's sung with its own size and tilt,
    the current word sits on a coloured sticker that fills in as it's sung, and earlier words drift up and fade.
  - **Lens:** a fisheye scroll. Lines grow as they reach the centre.
  - **Wall:** the lines stack into a wall that drifts in 3D.
  - **Visual:** emoji appear beside matching words, with a large faint emoji behind the current line.
- **Always on top:** the lyrics bar and glow stay above other apps. On a Mac they also appear on every desktop (Space) and over full-screen apps.
- **Lock screen (Mac):** the lyrics and glow keep showing on your Mac's lock screen. You can turn this off in Settings → Stage.
- **Stage mode:** full-screen lyrics over the blurred album art, with a clock and a now-playing card.
  It can open automatically when you're away from the computer.
- Lyrics come from [LRCLIB](https://lrclib.net), a free community lyrics database, or from your own `.lrc` files.
- A timing offset fixes lyrics that run early or late.

**Glow**
- A soft two-colour glow along the screen edges that slowly rotates.
- Pulses with the beat. It listens to your computer's audio output, never the microphone.
- Adjustable thickness, glow spread, brightness, edges, and display.

**Colours**
- **Album art:** follows each song's cover automatically.
- **Screen colors:** sampled from what's on your display.
- **Manual:** pick your own.

---

## Supported music apps

| OS | Works with |
|---|---|
| **macOS** 12+ | Spotify and Apple Music |
| **Windows** 10/11 | Spotify, Apple Music, web browsers (YouTube, YouTube Music, SoundCloud…), and any app that appears in the Windows media controls |
| Linux (unofficial) | Any MPRIS player, such as Spotify, browsers, or VLC. Needs `playerctl`. |

---

## For users: install the ready-made app

### Mac
1. Download the `.dmg` from the GitHub release (e.g. `GlowLyrics-1.0.0-mac-arm64.dmg`), open it, and drag **GlowLyrics** into **Applications**.
2. Open GlowLyrics from Applications.
3. **If macOS says it can't be opened:** go to **System Settings → Privacy & Security**, scroll down, and click **Open Anyway**.
   You only need to do this once.
4. Read and **Accept** the License Agreement.
5. A **♪** icon appears in the menu bar at the top right. There's no Dock icon.
6. Play a song in Spotify or Apple Music. When macOS asks whether GlowLyrics may control Spotify or Music, click **OK**.

> The Mac app is built for Apple silicon (M1 or newer).

### Windows
1. Download the `.zip` from the GitHub release (e.g. `GlowLyrics-1.0.0-windows-x64.zip`) and unzip it anywhere, for example in Documents.
2. Double-click **GlowLyrics.exe**. If Windows SmartScreen appears, click **More info → Run anyway**.
3. Read and **Accept** the License Agreement.
4. A **♪** icon appears in the system tray at the bottom right. Click `^` if it's hidden.
5. Play a song in Spotify, Apple Music, or your browser.

---

## For developers: run from source

You need **Python 3.9 or newer** from https://www.python.org/downloads/.
On Windows, tick **"Add python.exe to PATH"** during install.

| OS | Command |
|---|---|
| **macOS** | Double-click `run_mac.command`, or in Terminal: `cd ~/Workspace/GlowLyric && ./run_mac.command` |
| **Windows** | Double-click `run_windows.bat` |
| Linux | `./run_linux.sh`. First install `playerctl` and `python3-venv` with your package manager. |

The first run sets up a private `.venv` folder with everything the app needs, which takes 1–2 minutes.
Later runs start right away.

Command-line options for `main.py`:

```
python main.py            start normally
python main.py --demo     play the built-in demo song (no music app needed)
python main.py --reset    reset all settings to defaults
python main.py --debug    verbose logging
```

---

## Build a shareable app

The person you share with doesn't need Python.

### Easiest: let GitHub build it (Mac + Windows at once)
This repository has a GitHub Actions workflow, `.github/workflows/build.yml`, that builds both
apps on GitHub's own Mac and Windows machines. You don't need to build anything yourself.

**Publish a release (no commands needed):**
1. On GitHub, open the repository → **Actions** → **Build GlowLyrics** → **Run workflow**.
2. Type a version such as `1.0.1` and click **Run workflow**.
3. About 5–10 minutes later, the repository's **Releases** page has the new version with:
   - `GlowLyrics-1.0.1-mac-arm64.dmg`
   - `GlowLyrics-1.0.1-windows-x64.zip`

Use a new version number each time (`1.0.2`, `1.1.0`, …). Pushing a tag such as `v1.0.1` from your Mac works too.

**Test build without a release:** do the same but leave the version empty. The files then
appear in that run's **Artifacts** section instead of a release.

> While this repository is private, only people with access to it can download from Releases.
> To share with anyone, download the files and send them directly, or publish releases from a public repository.
> On private repositories, GitHub counts each macOS build minute as 10 minutes of your free Actions allowance.

### Build locally

#### Mac → `.app` + `.dmg`
Run this on a Mac:
```bash
cd ~/Workspace/GlowLyric
./build_mac_app.sh
```
It takes about 3–5 minutes the first time. You get:
- `dist/GlowLyrics.app`: the app.
- `dist/GlowLyrics-1.0.0-mac-arm64.dmg`: **share this file**. It contains the app, an Applications shortcut,
  a READ ME FIRST note, the license, and the third-party notices.

The app has its own icon, runs from the menu bar without a Dock icon, and shows the Tirhut LLC copyright in **Get Info**.

> **Gatekeeper:** the app is ad-hoc signed, not signed with a paid Apple Developer ID, so recipients
> confirm it once in Privacy & Security, as described above. To remove that step, sign and notarize it
> with an Apple Developer account ($99/year).

#### Windows → `.exe`
Run this on a Windows PC:
1. Double-click `run_windows.bat` once to set up Python packages.
2. Double-click `build_windows_exe.bat`.
3. Zip the folder `dist\GlowLyrics` and share it. Recipients run `GlowLyrics.exe` inside.

The `.exe` has the GlowLyrics icon. The license and third-party notices are bundled inside it and also placed next to it.

> Each build only runs on the operating system it was built on. Build the Mac version on a Mac and the Windows version on Windows.

---

## Using GlowLyrics

**Lyrics bar**
- **Move:** drag it.
- **Resize:** drag the bottom-right corner.
- **Text size:** scroll the mouse wheel over it.
- **Stage mode:** double-click it.
- **Menu:** right-click it.
- **Lock position** (menu or Settings): makes the bar click-through so it never gets in the way.

**Menu-bar / tray icon (♪)**
- Turn lyrics and the glow on or off.
- Open Stage, choose the lyrics style and the colour source.
- Adjust timing: **Lyrics later / earlier** in 0.25 s steps.
- Turn Demo mode on, open Settings, or Quit.

**Settings tabs**
- **Lyrics:** style, font, size, background, timing offset, local lyrics folder.
- **Glow:** on/off, beat or idle animation, thickness, spread, brightness, edges, display.
- **Colors:** Album art, Screen colors, or Manual. "Copy current song's colours" saves the current palette as your manual colours.
- **Stage:** auto-open when idle (after X minutes), clock on/off, keep the display awake while music plays, show on the lock screen (Mac).
- **About:** version, credits, copyright, License Agreement, third-party notices, open-source licenses.

**Stage mode:** press any key or click to exit. If it opened automatically, moving the mouse also closes it.

---

## Your own lyrics files

Put `.lrc` files in the lyrics folder (**Settings → Lyrics → Open local lyrics folder**), named
`Artist - Title.lrc` or `Title.lrc`. Local files take priority over online lyrics.
Enhanced LRC with per-word `<mm:ss.xx>` tags is supported and followed exactly.

---

## Privacy & performance

**Privacy**
- No account, no tracking. Nothing is sent to Tirhut LLC.
- To find lyrics and artwork, the song title and artist are sent to LRCLIB and the iTunes Search API.
- Beat detection analyses your computer's audio output on the device only. Audio is never recorded or sent anywhere, and the microphone is never used.

**Performance**
- On a Retina Mac, drawing a frame takes about 4 ms for the glow, 1 ms for the lyrics bar, and 10 ms for Stage mode.
- Animation runs at 30 frames per second only while something is moving. When music is paused or nothing is shown, it drops to about 5 frames per second.
- Beat detection only listens while the beat-synced glow is on screen.
- Memory is capped: images of rendered lyric lines are kept for at most 10 seconds and 24 MB, and the on-disk lyrics cache keeps at most 3,000 songs or 180 days.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| **"Nothing playing" on Mac** | Go to System Settings → Privacy & Security → **Automation** → GlowLyrics, and turn on Spotify and Music. Then quit GlowLyrics and open it again. |
| **Mac: "can't be opened"** | System Settings → Privacy & Security → **Open Anyway**. |
| **No lyrics found** | Not every song has synced lyrics on LRCLIB. Add your own `.lrc` file, or try again later; misses are retried after a day. Settings → About → **Clear lyrics cache** forces a fresh lookup. |
| **Lyrics early or late** | Use the tray menu → Timing, or Settings → Lyrics → Timing offset. Positive values make lyrics appear later. |
| **"Screen colors" shows nothing on Mac** | Give GlowLyrics Screen Recording permission in Privacy & Security. |
| **Lyrics/glow not on the Mac lock screen** | Check Settings → Stage → "Show lyrics and glow on the lock screen". If it's on and they still don't appear, your macOS version may not allow it. |
| **Glow doesn't pulse on Mac** | That's expected; see Notes & limitations below. The glow gently fades in and out instead. |
| **Windows: no beat pulse** | Check that sound is playing through your default output device. |
| **Start over** | Run with `--reset`, or delete the settings folder (Settings → About → Open settings folder). |

---

## Notes & limitations

- **Word timing:** most LRCLIB lyrics are timed line by line, so GlowLyrics spreads each line's words based on natural singing pace. Files with true per-word timing are followed exactly.
- **Lock screen:** on a Mac, the lyrics and glow show on the lock screen; they're view-only and can't be clicked. Anyone near your Mac can see them, so turn this off in Settings → Stage if you'd rather not. Windows doesn't allow apps on its lock screen, so use Stage mode ("open automatically when I'm away") there instead.
- **Beat sync on Mac:** macOS doesn't let apps hear system audio without a loopback driver such as BlackHole, so the glow fades in and out instead of pulsing. Album colours still work.
- **Full-screen apps:** on a Mac, the lyrics and glow show over full-screen apps. On Windows, a full-screen video may cover them for up to 2 seconds before GlowLyrics comes back on top. Exclusive full-screen games can still cover them.
- **Settings location:**
  - Windows: `%APPDATA%\GlowLyrics`
  - macOS: `~/Library/Application Support/GlowLyrics`
  - Linux: `~/.config/glowlyrics`

---

## Project layout

```
main.py                      launcher: license check, then the app
glowlyrics/
  controller.py              connects everything; tray menu, frame timing
  media.py                   what's playing (Windows media API / Mac helper / Linux MPRIS / demo)
  lyrics.py                  LRC parsing, per-word timing, LRCLIB client, disk cache
  colors.py                  album art lookup and colour palette extraction
  audio.py                   system-audio beat detection (Windows / Linux)
  glow.py                    screen-edge glow
  lyrics_view.py             the 5 lyric styles, floating bar, Stage mode, image cache
  emoji_map.py               word → emoji map for the Visual style
  settings_ui.py             settings window
  legal.py                   first-launch License Agreement, legal document viewer
  config.py                  saved settings
  system.py                  keep display awake, idle time, app folders
  window_tweaks.py           on-top behaviour: all desktops, full-screen apps, Mac lock screen
tools/
  make_icns.py               generates the app icon (.iconset for Mac, .ico for Windows)
  gen_licenses.py            collects full open-source license texts at build time
  mac_smoke_test.py          CI check: window behaviour and lock screen on a real Mac
  licenses/                  official LGPL-3.0 / GPL-3.0 texts
  READ ME FIRST.txt          note for Mac users, included in the .dmg
run_mac.command              run from source on Mac
run_windows.bat              run from source on Windows
run_linux.sh                 run from source on Linux
build_mac_app.sh             build GlowLyrics.app + .dmg
build_windows_exe.bat        build GlowLyrics.exe
.github/workflows/build.yml  GitHub Actions: builds Mac .dmg + Windows .zip, publishes releases
requirements.txt             Python packages
LICENSE.txt                  GlowLyrics End User License Agreement
THIRD-PARTY-NOTICES.txt      open-source components and their licenses
```

---

## License

GlowLyrics is proprietary software owned by Tirhut LLC. It's free to use under the
[GlowLyrics License Agreement](LICENSE.txt). Every user accepts it the first time they open the app,
and it can be read anytime in Settings → About. In short:

- Free for personal, non-commercial use. You may share the unmodified official installer for free.
- No selling, modifying, reverse-engineering, or rebranding.
- Provided **"as is"** with no warranty, and Tirhut LLC's liability is limited.
- Lyrics, artwork, and song info come from third parties and belong to their owners.
- Not affiliated with Spotify, Apple, Microsoft, or any music service.

GlowLyrics uses open-source components under their own licenses, including Qt for Python
(PySide6) under the LGPLv3. See [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt). The build
scripts create `THIRD-PARTY-LICENSES.txt` with the full license texts and bundle it with the app.

## Credits

Original idea: **Shriyans Raut**.

## Copyright

Copyright © 2026 Tirhut LLC. All rights reserved.
