#!/usr/bin/env python3
"""Find the tools needed to build a self-contained course AppImage, and say exactly what is missing.

Usage:  toolchain.py [--json]

Needed to build (no compiler, no Node/npm):
  * appimagetool                 packs the AppDir into an AppImage (it contains its own mksquashfs)
  * Electron (official build)    the app's engine — Chromium + Node — copied into the AppImage, so the finished app
                                 needs nothing installed on the learner's computer. Accepted as an unpacked folder or as
                                 the release zip (electron-vX.Y.Z-linux-<arch>.zip, e.g. from Downloads or ~/.cache/electron).
  * Noto Color Emoji font        bundled as a fallback — the course UI uses emoji and many distros ship no emoji font.
                                 Taken from this system if installed (identical file), else downloaded (~10 MB, OFL).
  * AppImage runtime file        recommended — without it appimagetool downloads the runtime from GitHub on every build

Exit code 0 = ready to build, 1 = something is missing (the report says what and where to get it).
Searched: PATH, $APPIMAGETOOL / $ELECTRON_DIST / $APPIMAGE_RUNTIME, ~/Applications, ~/.local/bin, ~/bin, the download
folder, ~/.cache/electron and the folder setup_toolchain.py installs into.
"""
import glob
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import zipfile

HOME = os.path.expanduser("~")
# setup_toolchain.py installs here; nothing outside this folder is touched (apart from --install's menu entry).
OWN_DIR = os.environ.get("COURSE_TO_APPIMAGE_HOME") or os.path.join(
    os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local", "share"), "course-to-appimage")
ARCHES = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64", "armv7l": "armhf"}
ELECTRON_ARCH = {"x86_64": "x64", "aarch64": "arm64", "armhf": "armv7l"}
MIN_ELECTRON = 30
TOOL_URL = "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-%s.AppImage"
RUNTIME_URL = "https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-%s"
ELECTRON_RELEASES = "https://github.com/electron/electron/releases/latest"
EMOJI_FONT = "NotoColorEmoji.ttf"
# pinned upstream release; a distro's package of the same version is the identical file
EMOJI_URL = "https://raw.githubusercontent.com/googlefonts/noto-emoji/v2.051/fonts/NotoColorEmoji.ttf"
EMOJI_SHA256 = "72a635cb3d2f3524c51620cdde406b217204e8a6a06c6a096ff8ed4b5fd6e27b"
EMOJI_SIZE = 10673480


def arch():
    return ARCHES.get(platform.machine().lower(), platform.machine().lower())


def _version_key(s):
    return [int(x) for x in re.findall(r"\d+", s)] or [0]


def _download_dirs():
    dirs = [os.path.join(HOME, d) for d in ("Downloads", "Pobrane", "Téléchargements", "Descargas", "Transferências")]
    try:  # localized XDG download dir
        out = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True, text=True, timeout=5).stdout.strip()
        if out and out not in dirs:
            dirs.insert(0, out)
    except (OSError, subprocess.SubprocessError):
        pass
    return dirs


def fuse_ok():
    return bool(shutil.which("fusermount") or shutil.which("fusermount3"))


def tool_env():
    """appimagetool is itself an AppImage — without FUSE it can still run by extracting itself to /tmp."""
    env = dict(os.environ)
    if not fuse_ok():
        env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
    return env


# ---- appimagetool ----------------------------------------------------------------------------------
def _probe(path):
    """(version line, error) — runs `appimagetool --version`."""
    if not os.access(path, os.X_OK):
        return None, "not executable (chmod +x \"%s\")" % path
    try:
        r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=60, env=tool_env())
    except (OSError, subprocess.SubprocessError) as e:
        return None, "does not start: %s" % e
    text = (r.stdout + r.stderr).strip()
    m = re.search(r"appimagetool.*", text)
    if m:
        return m.group(0).strip(), None
    return None, "does not start (exit %d): %s" % (r.returncode, text[-300:] or "no output")


def find_appimagetool():
    """{'path', 'version'} of the first working appimagetool, plus a list of broken candidates."""
    a = arch()
    cands = [os.environ.get("APPIMAGETOOL")]
    for n in ("appimagetool", "appimagetool-%s.AppImage" % a, "appimagetool.AppImage"):
        cands.append(shutil.which(n))
    for d in [OWN_DIR, os.path.join(HOME, "Applications"), os.path.join(HOME, ".local", "bin"), os.path.join(HOME, "bin"),
              "/opt/appimagetool"] + _download_dirs():
        cands += sorted(glob.glob(os.path.join(d, "appimagetool*")), reverse=True)
    seen, broken = [], []
    for c in cands:
        if not c or not os.path.isfile(c) or c.endswith((".zsync", ".sig", ".part")):
            continue
        real = os.path.realpath(c)
        if real in seen:
            continue
        seen.append(real)
        version, err = _probe(c)
        if version:
            return {"path": c, "version": version}, broken
        broken.append({"path": c, "error": err})
    return None, broken


def find_runtime():
    a = arch()
    for c in (os.environ.get("APPIMAGE_RUNTIME"), os.path.join(OWN_DIR, "runtime-" + a),
              *[os.path.join(d, "runtime-" + a) for d in _download_dirs()]):
        # a type2 runtime is a small static ELF (~1 MB)
        if c and os.path.isfile(c) and os.path.getsize(c) > 100000:
            with open(c, "rb") as f:
                if f.read(4) == b"\x7fELF":
                    return c
    return None


# ---- emoji font -----------------------------------------------------------------------------------
def find_emoji_font():
    """A Noto Color Emoji TTF: $COURSE_EMOJI_FONT, the skill's folder, or the system's fonts."""
    cands = [os.environ.get("COURSE_EMOJI_FONT"), os.path.join(OWN_DIR, EMOJI_FONT)]
    for d in ("/usr/share/fonts", "/usr/local/share/fonts", os.path.join(HOME, ".local", "share", "fonts"),
              os.path.join(HOME, ".fonts")):
        cands += sorted(glob.glob(os.path.join(d, "**", EMOJI_FONT), recursive=True))
    for c in cands:
        if c and os.path.isfile(c) and os.path.getsize(c) > 1000000:
            with open(c, "rb") as f:
                if f.read(4) in (b"\x00\x01\x00\x00", b"true", b"OTTO"):
                    return c
    return None


# ---- Electron --------------------------------------------------------------------------------------
def _electron_dir_version(d):
    """Version of an unpacked official Electron build, or None if d is not one."""
    need = ("electron", "resources.pak", "icudtl.dat", "version")
    if not all(os.path.exists(os.path.join(d, n)) for n in need):
        return None
    try:
        return open(os.path.join(d, "version"), encoding="utf-8").read().strip().lstrip("v")
    except OSError:
        return None


def find_electron():
    """Newest usable Electron: {'dir' or 'zip', 'version'}; plus too-old ones found."""
    ea = ELECTRON_ARCH.get(arch())
    found, old = [], []

    def consider(kind, path, version):
        if not version:
            return
        item = {kind: path, "version": version}
        (found if _version_key(version)[0] >= MIN_ELECTRON else old).append(item)

    env_dir = os.environ.get("ELECTRON_DIST")
    if env_dir:
        consider("dir", env_dir, _electron_dir_version(env_dir))
    for d in glob.glob(os.path.join(OWN_DIR, "electron-v*-linux-%s" % ea)):
        consider("dir", d, _electron_dir_version(d))
    zips = []
    for d in [OWN_DIR, os.path.join(HOME, ".cache", "electron")] + _download_dirs():
        zips += glob.glob(os.path.join(d, "electron-v*-linux-%s.zip" % ea))
        zips += glob.glob(os.path.join(d, "*", "electron-v*-linux-%s.zip" % ea))  # ~/.cache/electron/<hash>/…
    for z in zips:
        m = re.search(r"electron-v([\d.]+)-linux-", os.path.basename(z))
        if m and zipfile.is_zipfile(z):
            consider("zip", z, m.group(1))
    if not found:
        return None, old
    # an unpacked folder wins over a zip of the same version (nothing to extract)
    found.sort(key=lambda i: (_version_key(i["version"]), "dir" in i), reverse=True)
    return found[0], old


def extract_zip(path, target):
    """Unzip keeping exec bits and symlinks (zipfile drops both)."""
    os.makedirs(target, exist_ok=True)
    root = os.path.normpath(target)
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            out = os.path.normpath(os.path.join(target, info.filename))
            if not out.startswith(root + os.sep):
                continue
            if info.filename.endswith("/"):
                os.makedirs(out, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(out), exist_ok=True)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                if os.path.lexists(out):
                    os.remove(out)
                os.symlink(z.read(info).decode(), out)
                continue
            with z.open(info) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
            if mode & 0o111:
                os.chmod(out, 0o755)


def electron_dir(item):
    """Folder of the Electron build — unpacks a zip into OWN_DIR once (it is the user's own download; nothing is fetched)."""
    if "dir" in item:
        return item["dir"]
    target = os.path.join(OWN_DIR, "electron-v%s-linux-%s" % (item["version"], ELECTRON_ARCH[arch()]))
    if not _electron_dir_version(target):
        tmp = target + ".part"
        shutil.rmtree(tmp, ignore_errors=True)
        extract_zip(item["zip"], tmp)
        if not _electron_dir_version(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
            sys.exit("ERROR: %s is not an Electron release zip (no electron, resources.pak, version)" % item["zip"])
        shutil.rmtree(target, ignore_errors=True)
        os.rename(tmp, target)
        print("Unpacked %s → %s" % (item["zip"], target))
    return target


# ---- report ----------------------------------------------------------------------------------------
def detect():
    tool, broken = find_appimagetool()
    electron, old_electron = find_electron()
    missing = []
    if not tool:
        missing.append("appimagetool")
    if not electron:
        missing.append("electron")
    emoji = find_emoji_font()
    if not emoji:
        missing.append("emoji-font")
    return {"emoji_font": emoji, "ready": not missing, "missing": missing, "appimagetool": tool, "broken": broken,
            "electron": electron, "old_electron": old_electron, "runtime": find_runtime(), "arch": arch(),
            "supported_arch": arch() in ELECTRON_ARCH, "fuse": fuse_ok(), "install_dir": OWN_DIR}


def install_help(info):
    """Human instructions: what to download and where from."""
    a = info["arch"]
    ea = ELECTRON_ARCH.get(a, "?")
    lines = []
    if "appimagetool" in info["missing"]:
        lines.append("appimagetool (packs the AppImage, ~15 MB, MIT licence):")
        for b in info["broken"]:
            lines.append("  found but unusable: %s — %s" % (b["path"], b["error"]))
        lines.append("  download: %s" % (TOOL_URL % a))
        lines.append("  (releases page: https://github.com/AppImage/appimagetool/releases/tag/continuous)")
        lines.append("  then: chmod +x appimagetool-%s.AppImage and put it on PATH, e.g. as ~/.local/bin/appimagetool" % a)
        lines.append("  or package manager: Arch/CachyOS `yay -S appimagetool-bin` (AUR) · other distros: the download above")
        lines.append("  (somewhere else? set APPIMAGETOOL=/path/to/appimagetool)")
    if "electron" in info["missing"]:
        lines.append("Electron %d+ — the app's engine (Chromium + Node), ~115 MB zip, MIT licence:" % MIN_ELECTRON)
        for o in info["old_electron"]:
            lines.append("  found only too old: %s %s" % (o["version"], o.get("dir") or o.get("zip")))
        lines.append("  download electron-vX.Y.Z-linux-%s.zip (newest stable) from %s" % (ea, ELECTRON_RELEASES))
        lines.append("  and leave it in your Downloads folder (the build finds and unpacks it), or set ELECTRON_DIST to an")
        lines.append("  unpacked copy. Use the official zip — distro packages (e.g. pacman's `electron`) are built against")
        lines.append("  this system's libraries and would not run on other computers.")
    if "emoji-font" in info["missing"]:
        lines.append("Noto Color Emoji font (bundled so emoji show on every computer, ~10 MB, SIL Open Font License):")
        lines.append("  package: Arch/CachyOS `sudo pacman -S noto-fonts-emoji` · Debian/Ubuntu `sudo apt install fonts-noto-color-emoji`"
                     " · Fedora `sudo dnf install google-noto-color-emoji-fonts`")
        lines.append("  or download: %s" % EMOJI_URL)
        lines.append("  and save it as %s (or set COURSE_EMOJI_FONT=/path/to/%s)" % (os.path.join(info["install_dir"], EMOJI_FONT), EMOJI_FONT))
    if not info["runtime"]:
        lines.append("AppImage runtime (recommended, ~1 MB) — otherwise appimagetool fetches it from GitHub at each build:")
        lines.append("  download: %s" % (RUNTIME_URL % a))
        lines.append("  save as %s (or set APPIMAGE_RUNTIME=/path/to/runtime-%s)" % (os.path.join(info["install_dir"], "runtime-" + a), a))
    return lines


def describe(info):
    t, e = info["appimagetool"], info["electron"]
    lines = ["Architecture: " + info["arch"] + ("" if info["supported_arch"] else "  (UNSUPPORTED — Electron has no Linux build for it)"),
             "appimagetool: " + ("OK  %s  (%s)" % (t["path"], t["version"]) if t else "MISSING"),
             "Electron:     " + ("OK  %s  %s" % (e["version"], e.get("dir") or e.get("zip") + "  (zip, unpacked on first build)")
                                 if e else "MISSING"),
             "emoji font:   " + ("OK  %s" % info["emoji_font"] if info["emoji_font"] else "MISSING"),
             "runtime:      " + ("OK  %s" % info["runtime"] if info["runtime"]
                                 else "not found (optional — appimagetool downloads it during the build; needs internet)"),
             "FUSE:         " + ("OK" if info["fuse"] else "fusermount missing — appimagetool and the test run use "
                                 "APPIMAGE_EXTRACT_AND_RUN instead"),
             ""]
    if info["ready"]:
        lines.append("READY — build_appimage.py can build the AppImage.")
    else:
        lines.append("NOT READY — missing: " + ", ".join(info["missing"]))
    help_lines = install_help(info)
    if help_lines:
        lines.append("")
        lines += help_lines
        size = (15 if "appimagetool" in info["missing"] else 0) + (115 if "electron" in info["missing"] else 0) + \
               (10 if "emoji-font" in info["missing"] else 0) + \
               (1 if not info["runtime"] else 0)
        lines.append("")
        lines.append("Automatic alternative (no sudo, installs only into %s; downloads ~%d MB):" % (info["install_dir"], size))
        lines.append("  python3 setup_toolchain.py --download")
    return "\n".join(lines)


def main():
    info = detect()
    if "--json" in sys.argv[1:]:
        info["help"] = install_help(info)
        print(json.dumps(info, indent=2))
    else:
        print(describe(info))
    sys.exit(0 if info["ready"] else 1)


if __name__ == "__main__":
    main()
