# Troubleshooting course-to-appimage

## Toolchain
- **appimagetool "found but unusable: not executable"** — `chmod +x` the file (downloads from a browser lose the exec bit).
- **appimagetool "does not start"** — it is an AppImage itself. Without FUSE the scripts run it with
  `APPIMAGE_EXTRACT_AND_RUN=1` automatically; if it still fails, the file is probably incomplete — download it again,
  or use `setup_toolchain.py --download` (checksum-verified).
- **Tools in unusual places** — `APPIMAGETOOL=/path/to/appimagetool`, `ELECTRON_DIST=/path/to/unpacked/electron`,
  `APPIMAGE_RUNTIME=/path/to/runtime-<arch>`.
- **Electron reported "too old"** — need 30+; download the newest `electron-vX.Y.Z-linux-<x64|arm64>.zip`.
- **The distro's `electron` package (pacman/apt) is not picked up on purpose** — it uses this system's shared libraries,
  so an AppImage built from it would not run elsewhere. Use the official zip.
- **Electron zip "is not an Electron release zip"** — a different download (e.g. `-debug`, `-symbols`, `chromedriver`);
  take the plain `electron-vX.Y.Z-linux-x64.zip`.
- **`setup_toolchain.py` cannot reach the GitHub API / no checksum** — download by hand from the links `toolchain.py`
  prints. Behind a proxy set `HTTPS_PROXY` first.
- **Emoji font missing** — install the distro's package (`noto-fonts-emoji` / `fonts-noto-color-emoji` /
  `google-noto-color-emoji-fonts`), or let `setup_toolchain.py --download` fetch the pinned upstream file, or set
  `COURSE_EMOJI_FONT=/path/to/NotoColorEmoji.ttf`.
- **Very old appimagetool (AppImageKit, 2020-ish)** — still works, but its built-in runtime needs `libfuse2` on the
  learner's computer. Prefer the current one from github.com/AppImage/appimagetool.

## Build
- **appimagetool tries to download the runtime and fails (offline)** — get the runtime file
  (`setup_toolchain.py --download`, or save `runtime-<arch>` into `~/.local/share/course-to-appimage/`).
- **Self-test FAILED with "Missing X server or $DISPLAY"** — the build ran without a graphical session (SSH, CI). The
  AppImage itself is fine; test it on a desktop.
- **AppImage much larger than ~105 MB + course** — the course folder contains big media next to `index.html`. Everything
  except `content/`, `exercises/` (packed separately, without `_solution/`), `progress/`, `.build/`, `serve.py`, start
  scripts, README and zips is packed.
- **"Starters: N file(s) … were edited"** — someone did exercises inside the course folder. Nothing to fix: the app
  got the original starter code from `course/data.js`, and the folder keeps that person's work.

## Running
- **Double-click does nothing / "permission denied"** — the file lost its exec bit (e-mail, FAT USB stick):
  `chmod +x file.AppImage` or file manager → Properties → "Allow executing as program".
- **"fuse: failed to exec fusermount" / "Cannot mount AppImage"** — install `fuse3` (or `fuse`), or start with
  `./file.AppImage --appimage-extract-and-run`.
- **"error while loading shared libraries: libgtk-3.so.0 / libnss3.so / libasound.so.2"** — a minimal system without a
  desktop. Install the desktop basics, e.g. Debian/Ubuntu `sudo apt install libgtk-3-0 libnss3 libasound2 libgbm1`.
- **"The SUID sandbox helper binary was found, but is not configured correctly" / "No usable sandbox"** — AppRun
  normally avoids this by adding `--no-sandbox` when user namespaces are blocked. If it still appears, start with
  `./file.AppImage --no-sandbox`.
- **Emoji show as empty boxes** — the AppImage brings its own emoji font through fontconfig; this fails only if the
  system has no `/etc/fonts/fonts.conf` (no fontconfig at all — not a desktop system).
- **Blank or flickering window** (some GPU drivers) — start with `--disable-gpu`.
- **"Run tests" says the program is not installed** — the language toolchain is missing, or it is only on the PATH of
  interactive shells. The app adds common places (`~/go/bin`, `/usr/local/go/bin`, `~/.cargo/bin`, `~/.local/bin`, …);
  otherwise start the app from a terminal where the tool works.
- **No icon in the taskbar / generic icon** — before `--install` the desktop doesn't know the app; after installing it
  uses the menu entry's icon.
- **Progress gone** — progress is per app id in `~/.local/share/<app-id>/`; a build with a different `--app-id` starts
  empty. Progress of the folder version (`progress/progress.json`) is separate; to carry it over, copy that file into
  `~/.local/share/<app-id>/progress/`.
