#!/usr/bin/env python3
"""Build a self-contained Linux AppImage (an Electron WebView wrapper) from a course made by book-to-course.

Usage:  build_appimage.py COURSE_DIR [--out DIR] [--app-id ID] [--name NAME] [--version X] [--install]
        build_appimage.py COURSE_DIR --uninstall

  COURSE_DIR   the course folder (has index.html, assets/, course/data.js)
  --out        where the build lives (default: <COURSE_DIR>-appimage, next to the course)
  --app-id     reverse-DNS id, e.g. pl.example.gocourse (default: derived from the course id; remembered in <out>/appimage.json).
               It names the learner's data folder ~/.local/share/<app-id> — changing it later starts with empty progress.
  --name       name in the window title and the application menu (default: course title)
  --install    also copy the AppImage to ~/Applications and add it to the application menu (no sudo)
  --uninstall  remove that menu entry, icon and ~/Applications copy (the learner's progress is kept)

The AppImage carries everything: the official Electron build (Chromium + Node), a small main.js that does what the
course's serve.py does (progress file, "Run tests"), the course and an icon. The learner's computer needs nothing installed.
Nothing is compiled; unused Chromium translations are left out (en-US + the course language are kept).
Every build bumps the version in <out>/appimage.json; once installed with --install, later builds refresh the installed copy.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import toolchain  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")
HOME = os.path.expanduser("~")
DATA_HOME = os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local", "share")
APPS_DIR = os.path.join(HOME, "Applications")
# what the page needs is index.html, assets/ and course/ (main.js replaces serve.py);
# exercises/ goes in separately as the seed of the learner's writable copy
SKIP_TOP = {"content", "exercises", "progress", ".build", ".git", "serve.py", "start.sh", "start.bat", "README.md",
            "__pycache__", "node_modules", "android"}
# not needed inside the app: the setuid sandbox helper (an AppImage can't carry setuid; AppRun handles it),
# Electron's demo app; locales are filtered separately
ELECTRON_SKIP = {"chrome-sandbox", "default_app.asar"}
LOCALES = {"pl": ["pl"], "pt": ["pt-BR", "pt-PT"], "en": ["en-GB"], "de": ["de"], "es": ["es", "es-419"], "fr": ["fr"]}
SEED_IGNORE = shutil.ignore_patterns("_solution", "__pycache__", ".*", "*.pyc", "node_modules", "target", "bin", "obj")
ICON_COLORS = ["#1E6FD9", "#0F8B8D", "#2E7D32", "#6A4FB6", "#C2185B", "#D84315", "#5D4037", "#37474F", "#00838F", "#AD1457"]
ACTION_NAME = {"pl": "Otwórz folder ćwiczeń", "pt": "Abrir pasta de exercícios", "en": "Open exercises folder"}
ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 108 108" width="256" height="256">
  <rect x="4" y="4" width="100" height="100" rx="22" fill="{color}"/>
  <g transform="translate(54 55) scale(1.45) translate(-54 -55)" fill="#ffffff">
    <path d="M54,38 C47,33 38,32 30,33 L30,73 C38,72 47,73 54,78 Z"/>
    <path fill-opacity="0.82" d="M54,38 C61,33 70,32 78,33 L78,73 C70,72 61,73 54,78 Z"/>
  </g>
</svg>
"""


def die(msg):
    sys.exit("ERROR: " + msg)


def ascii_slug(s):
    s = s.replace("ł", "l").replace("Ł", "L")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def default_app_id(course_id):
    seg = ascii_slug(course_id)[:40].strip("_") or "course"
    return "net.booktocourse." + ("c_" + seg if seg[0].isdigit() else seg)


def valid_app_id(p):
    parts = p.split(".")
    return len(parts) >= 2 and all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", x) for x in parts) and len(p) <= 255


def course_meta(course):
    meta = {}
    cj = os.path.join(course, "content", "course.json")
    if os.path.exists(cj):
        try:
            meta = json.load(open(cj, encoding="utf-8"))
        except ValueError:
            pass
    if not meta.get("title"):  # learner package without content/ — read it from data.js
        try:
            txt = open(os.path.join(course, "course", "data.js"), encoding="utf-8").read(200000)
            m = re.search(r'"meta"\s*:\s*(\{[^{}]*\})', txt)
            if m:
                for k, v in json.loads(m.group(1)).items():
                    meta.setdefault(k, v)
        except (OSError, ValueError):
            pass
    name = os.path.basename(course.rstrip(os.sep))
    meta.setdefault("id", ascii_slug(name) or "course")
    meta.setdefault("title", name)
    return meta


def one_line(s):
    return " ".join(str(s).split())


def desktop_entry(cfg, meta, exec_cmd, has_exercises):
    lines = ["[Desktop Entry]", "Type=Application", "Name=" + one_line(cfg["name"]),
             "Comment=" + one_line(meta.get("subtitle") or meta.get("description") or cfg["name"])[:200],
             "Exec=%s" % exec_cmd, "Icon=" + cfg["app_id"], "Terminal=false", "Categories=Education;",
             "StartupWMClass=" + cfg["app_id"], "X-AppImage-Version=" + cfg["version"]]
    if has_exercises:
        lines += ["Actions=exercises;", "", "[Desktop Action exercises]",
                  "Name=" + ACTION_NAME.get(meta.get("ui_lang"), ACTION_NAME["en"]), "Exec=%s --open-exercises" % exec_cmd]
    return "\n".join(lines) + "\n"


def stage_course(course, out, dst):
    n = size = 0
    out_real = os.path.realpath(out)
    os.makedirs(dst)
    for entry in sorted(os.listdir(course)):
        src = os.path.join(course, entry)
        if entry in SKIP_TOP or entry.startswith(".") or entry.endswith(".zip") or os.path.realpath(src) == out_real:
            continue
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dst, entry), ignore=shutil.ignore_patterns("__pycache__", ".*", "*.pyc", "*.tmp"))
        else:
            shutil.copy2(src, os.path.join(dst, entry))
    for base, _, files in os.walk(dst):
        for f in files:
            n += 1
            size += os.path.getsize(os.path.join(base, f))
    return n, size


def starters_from_data(course):
    """{exercise dir: [(path, content)]} — the starter files as compiled into course/data.js (what the page shows as
    "start files"). The exercises/ folder of a course someone has been learning from holds their own edits instead."""
    try:
        txt = open(os.path.join(course, "course", "data.js"), encoding="utf-8").read()
        data = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
    except (OSError, ValueError):
        return {}
    out = {}
    for les in (data.get("lessons") or {}).values():
        for b in les.get("blocks") or []:
            files = (b.get("files") or {}).get("starter") if isinstance(b, dict) and b.get("type") == "exercise" else None
            if files and b.get("dir"):
                out[b["dir"]] = [(f["path"], f["content"]) for f in files if isinstance(f.get("content"), str)]
    return out


def seed_exercises(course, dst):
    """Copy exercises/ (tests, exercise.json, …; no _solution/) and put back the original starter files.
    Returns the starter files that differed in the course folder."""
    shutil.copytree(os.path.join(course, "exercises"), dst, ignore=SEED_IGNORE)
    restored = []
    for d, files in starters_from_data(course).items():
        if not os.path.isdir(os.path.join(dst, d)):
            continue
        for rel, content in files:
            target = os.path.normpath(os.path.join(dst, d, rel))
            if not target.startswith(os.path.join(dst, d) + os.sep):
                continue
            old = open(target, encoding="utf-8", errors="replace").read() if os.path.exists(target) else None
            if old != content:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "w", encoding="utf-8") as f:
                    f.write(content)
                restored.append("%s/%s" % (d, rel))
    return restored


def install_paths(cfg):
    return {"desktop": os.path.join(DATA_HOME, "applications", cfg["app_id"] + ".desktop"),
            "icon": os.path.join(DATA_HOME, "icons", "hicolor", "scalable", "apps", cfg["app_id"] + ".svg")}


def refresh_menu():
    # no gtk-update-icon-cache: a cache file in ~/.local/share/icons/hicolor makes GTK ignore icons added later
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", "-q", os.path.join(DATA_HOME, "applications")], capture_output=True)


def install(cfg, meta, appimage, has_exercises):
    os.makedirs(APPS_DIR, exist_ok=True)
    target = os.path.join(APPS_DIR, os.path.basename(appimage))
    tmp = target + ".part"
    shutil.copyfile(appimage, tmp)
    os.chmod(tmp, 0o755)
    os.replace(tmp, target)  # atomic, so a running copy of the old version is not corrupted
    p = install_paths(cfg)
    os.makedirs(os.path.dirname(p["desktop"]), exist_ok=True)
    os.makedirs(os.path.dirname(p["icon"]), exist_ok=True)
    with open(p["desktop"], "w", encoding="utf-8") as f:
        f.write(desktop_entry(cfg, meta, '"%s"' % target.replace("\\", "\\\\").replace('"', '\\"')
                              .replace("`", "\\`").replace("$", "\\$"), has_exercises))
    with open(p["icon"], "w", encoding="utf-8") as f:
        f.write(ICON_SVG.format(color=cfg["icon_color"]))
    refresh_menu()
    cfg["installed"] = target
    return target, p


def uninstall(out):
    cfg_path = os.path.join(out, "appimage.json")
    if not os.path.exists(cfg_path):
        die("no %s — nothing was built from this course here, so nothing to uninstall" % cfg_path)
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    removed = []
    for path in [cfg.get("installed")] + list(install_paths(cfg).values()):
        if path and os.path.exists(path):
            os.remove(path)
            removed.append(path)
    refresh_menu()
    cfg.pop("installed", None)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("Removed:\n  " + "\n  ".join(removed) if removed else "Nothing installed.")
    print("Progress kept in " + os.path.join(DATA_HOME, cfg["app_id"]) + " (delete that folder to erase it).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("course_dir")
    ap.add_argument("--out")
    ap.add_argument("--app-id")
    ap.add_argument("--name")
    ap.add_argument("--version")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    a = ap.parse_args()

    course = os.path.abspath(a.course_dir).rstrip(os.sep)
    out = os.path.abspath(a.out or course + "-appimage")
    if a.uninstall:
        return uninstall(out)
    for need in ("index.html", os.path.join("course", "data.js"), os.path.join("assets", "app.js")):
        if not os.path.exists(os.path.join(course, need)):
            die("%s has no %s — is this a book-to-course course? (run build_course.py first if data.js is missing)" % (course, need))

    info = toolchain.detect()
    if not info["ready"]:
        print(toolchain.describe(info))
        sys.exit(1)
    arch = info["arch"]
    electron = toolchain.electron_dir(info["electron"])
    meta = course_meta(course)
    os.makedirs(out, exist_ok=True)

    # ---- appimage.json: identity that must stay stable between builds -------------------------
    cfg_path = os.path.join(out, "appimage.json")
    cfg = json.load(open(cfg_path, encoding="utf-8")) if os.path.exists(cfg_path) else {}
    if a.app_id and cfg.get("app_id") and a.app_id != cfg["app_id"]:
        print("NOTE: app id changes %s → %s. Progress is kept per app id, so the app starts with empty progress "
              "(the old one stays in %s)." % (cfg["app_id"], a.app_id, os.path.join(DATA_HOME, cfg["app_id"])))
    cfg["app_id"] = a.app_id or cfg.get("app_id") or default_app_id(meta["id"])
    if not valid_app_id(cfg["app_id"]):
        die("invalid app id %r — use something like pl.example.gocourse (letters/digits/_, at least two parts)" % cfg["app_id"])
    cfg["name"] = a.name or cfg.get("name") or meta["title"]
    cfg["build"] = int(cfg.get("build", 0)) + 1
    cfg["version"] = a.version or "1.0.%d" % cfg["build"]
    cfg.setdefault("icon_color", ICON_COLORS[int(hashlib.sha1(meta["id"].encode()).hexdigest(), 16) % len(ICON_COLORS)])

    # ---- stage the AppDir ---------------------------------------------------------------------
    build = os.path.join(out, "build")
    shutil.rmtree(build, ignore_errors=True)
    appdir = os.path.join(build, "AppDir")
    lib = os.path.join(appdir, "usr", "lib", "course-app")
    keep_locales = {"en-US"} | set(LOCALES.get(meta.get("ui_lang"), [meta.get("ui_lang") or "en-US"]))
    shutil.copytree(electron, lib, symlinks=True, ignore=lambda d, names: [
        n for n in names if n in ELECTRON_SKIP or (os.path.basename(d) == "locales" and n.endswith(".pak")
                                                    and n[:-4] not in keep_locales)])
    os.rename(os.path.join(lib, "electron"), os.path.join(lib, "course-app"))
    app_dir = os.path.join(lib, "resources", "app")
    nfiles, nbytes = stage_course(course, out, os.path.join(app_dir, "course"))
    ex_src = os.path.join(course, "exercises")
    has_exercises = os.path.isdir(ex_src) and any(os.path.isdir(os.path.join(ex_src, d)) for d in os.listdir(ex_src))
    restored = seed_exercises(course, os.path.join(app_dir, "exercises")) if has_exercises else []
    shutil.copy2(os.path.join(ASSETS, "app", "main.js"), app_dir)
    fc = os.path.join(appdir, "usr", "share", "course-app", "fontconfig")
    os.makedirs(os.path.join(fc, "fonts"))
    shutil.copy2(os.path.join(ASSETS, "fonts", "fonts.conf"), fc)
    shutil.copyfile(info["emoji_font"], os.path.join(fc, "fonts", toolchain.EMOJI_FONT))
    shutil.copy2(os.path.join(ASSETS, "fonts", "LICENSE-NotoColorEmoji.txt"), os.path.join(fc, "fonts"))
    package = {"name": cfg["app_id"], "productName": cfg["name"], "version": cfg["version"], "main": "main.js",
               "desktopName": cfg["app_id"] + ".desktop", "private": True}  # desktopName → Wayland app id = menu entry
    icon = ICON_SVG.format(color=cfg["icon_color"])
    entry = desktop_entry(cfg, meta, "AppRun", has_exercises)
    files = ((os.path.join(app_dir, "package.json"), json.dumps(package, indent=2, ensure_ascii=False)),
             (os.path.join(app_dir, "app.json"), json.dumps({"app_id": cfg["app_id"], "name": cfg["name"],
                                                              "course_id": meta["id"], "version": cfg["version"],
                                                              "ui_lang": meta.get("ui_lang") or "en"},
                                                             indent=2, ensure_ascii=False)),
             (os.path.join(appdir, cfg["app_id"] + ".svg"), icon),
             (os.path.join(appdir, ".DirIcon"), icon),
             (os.path.join(appdir, "usr", "share", "icons", "hicolor", "scalable", "apps", cfg["app_id"] + ".svg"), icon),
             (os.path.join(appdir, cfg["app_id"] + ".desktop"), entry),
             (os.path.join(appdir, "usr", "share", "applications", cfg["app_id"] + ".desktop"), entry))
    for path, text in files:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    shutil.copy2(os.path.join(ASSETS, "appdir", "AppRun"), os.path.join(appdir, "AppRun"))
    os.chmod(os.path.join(appdir, "AppRun"), 0o755)

    # ---- pack ---------------------------------------------------------------------------------
    appimage = os.path.join(out, "%s-%s.AppImage" % (ascii_slug(meta["id"]).replace("_", "-") or "course", arch))
    cmd = [info["appimagetool"]["path"], "--no-appstream"]
    if info["runtime"]:
        cmd += ["--runtime-file", info["runtime"]]
    cmd += [appdir, appimage + ".part"]
    env = toolchain.tool_env()
    env["ARCH"] = arch  # set explicitly: Electron ships several ELF files and the guess must not depend on them
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(appimage + ".part"):
        die("appimagetool failed (exit %d):\n  %s\n%s%s" % (r.returncode, " ".join(cmd), r.stdout[-3000:], r.stderr[-3000:]))
    os.chmod(appimage + ".part", 0o755)
    os.replace(appimage + ".part", appimage)
    shutil.rmtree(build, ignore_errors=True)

    # ---- smoke test: does Electron in the AppImage start and run main.js? ----------------------
    env = dict(os.environ)
    if not info["fuse"]:
        env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
    try:
        s = subprocess.run([appimage, "--paths"], capture_output=True, text=True, timeout=90, env=env)
        check = "OK (Electron starts, main.js runs)" if s.returncode == 0 and "progress:" in s.stdout else \
            "FAILED (exit %d): %s" % (s.returncode, (s.stdout + s.stderr).strip()[-800:])
    except (OSError, subprocess.SubprocessError) as e:
        check = "FAILED: %s" % e

    installed = None
    if a.install or (cfg.get("installed") and os.path.exists(cfg["installed"])):
        installed, ipaths = install(cfg, meta, appimage, has_exercises)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print("AppImage:  %s  (%.1f MB)" % (appimage, os.path.getsize(appimage) / 1048576))
    print("App:       %s  ·  %s  ·  version %s  ·  %s" % (cfg["name"], cfg["app_id"], cfg["version"], arch))
    print("Course:    %d files, %d KB%s" % (nfiles, nbytes // 1024, "  + code exercises" if has_exercises else ""))
    print("Data:      %s  (progress%s; kept across updates)" % (os.path.join(DATA_HOME, cfg["app_id"]),
                                                                 " and exercises" if has_exercises else ""))
    print("Engine:    Electron %s (Chromium + Node, bundled; locales: %s)" % (info["electron"]["version"], ", ".join(sorted(keep_locales))))
    print("Self-test: " + check)
    if not info["runtime"]:
        print("Note:      runtime fetched by appimagetool from GitHub (setup_toolchain.py --download keeps a local copy).")
    if installed:
        print("Installed: %s\n           menu entry %s" % (installed, ipaths["desktop"]))
    if restored:
        print("Starters:  %d file(s) in the course's exercises/ were edited (someone worked there: %s); the app got the "
              "original starter code from course/data.js instead. The course folder is untouched."
              % (len(restored), ", ".join(restored[:5]) + (" …" if len(restored) > 5 else "")))

if __name__ == "__main__":
    main()
