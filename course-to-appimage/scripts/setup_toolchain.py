#!/usr/bin/env python3
"""Download whatever toolchain.py reports as missing — without sudo, into one folder of the user's home.

Usage:
  setup_toolchain.py --dry-run      # print what would be downloaded, from where, how big — download nothing
  setup_toolchain.py --download     # download + install (only the missing parts)

Installs into ~/.local/share/course-to-appimage; set COURSE_TO_APPIMAGE_HOME to change it
(toolchain.py and build_appimage.py read the same variable, so they find what was installed).

Sources (official only, SHA-256 from the GitHub release metadata verified before anything is kept):
  appimagetool  https://github.com/AppImage/appimagetool/releases/tag/continuous   (~15 MB, MIT)
  Electron      https://github.com/electron/electron/releases/latest               (~115 MB zip, MIT; unpacked here)
  emoji font    Noto Color Emoji v2.051 from github.com/googlefonts/noto-emoji     (~10 MB, OFL; pinned SHA-256)
  runtime       https://github.com/AppImage/type2-runtime/releases/tag/continuous  (~1 MB, MIT)

Only pass --download after the user agreed to the download. Standard library only.
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import toolchain  # noqa: E402

UA = {"User-Agent": "course-to-appimage/1.0", "Accept": "application/vnd.github+json"}
RELEASES = {"appimagetool": "https://api.github.com/repos/AppImage/appimagetool/releases/tags/continuous",
            "electron": "https://api.github.com/repos/electron/electron/releases/latest",
            "runtime": "https://api.github.com/repos/AppImage/type2-runtime/releases/tags/continuous"}


def fetch_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.loads(r.read())


def plan_item(kind, a):
    try:
        rel = fetch_json(RELEASES[kind])
    except OSError as e:
        raise SystemExit("Cannot reach the GitHub API (%s) — download by hand instead (toolchain.py prints the links)." % e)
    if kind == "electron":
        name = "electron-%s-linux-%s.zip" % (rel.get("tag_name", ""), toolchain.ELECTRON_ARCH.get(a, "?"))
    else:
        name = ("appimagetool-%s.AppImage" if kind == "appimagetool" else "runtime-%s") % a
    asset = next((x for x in rel.get("assets", []) if x.get("name") == name), None)
    if not asset:
        raise SystemExit("%s has no %s for architecture %s — download by hand." % (RELEASES[kind], name, a))
    digest = asset.get("digest") or ""
    if not digest.startswith("sha256:"):
        raise SystemExit("GitHub gave no SHA-256 for %s, so it cannot be verified — download it by hand." % name)
    return {"what": kind, "name": name, "url": asset["browser_download_url"], "size": asset["size"],
            "sha256": digest.split(":", 1)[1], "dest": os.path.join(toolchain.OWN_DIR, name)}


def make_plan(info):
    items = []
    if "appimagetool" in info["missing"]:
        items.append(plan_item("appimagetool", info["arch"]))
    if "electron" in info["missing"]:
        items.append(plan_item("electron", info["arch"]))
    if "emoji-font" in info["missing"]:
        items.append({"what": "emoji font", "name": toolchain.EMOJI_FONT, "url": toolchain.EMOJI_URL,
                      "size": toolchain.EMOJI_SIZE, "sha256": toolchain.EMOJI_SHA256,
                      "dest": os.path.join(toolchain.OWN_DIR, toolchain.EMOJI_FONT)})
    if not info["runtime"]:
        items.append(plan_item("runtime", info["arch"]))
    return items


def download(item, tmp):
    dest = os.path.join(tmp, item["name"])
    h = hashlib.sha256()
    done, last = 0, -1
    with urllib.request.urlopen(urllib.request.Request(item["url"], headers={"User-Agent": UA["User-Agent"]}),
                                timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            pct = done * 100 // max(item["size"], 1)
            if pct // 10 != last:
                last = pct // 10
                print("  %s  %d%%" % (item["name"], pct), flush=True)
    if h.hexdigest().lower() != item["sha256"].lower():
        raise SystemExit("Checksum mismatch for %s — download corrupted or tampered with; nothing installed." % item["url"])
    return dest


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--download", action="store_true")
    a = ap.parse_args()
    if not (a.dry_run or a.download):
        ap.error("pass --dry-run (show the plan) or --download (the user agreed to download)")

    info = toolchain.detect()
    plan = make_plan(info)
    if not plan:
        print(toolchain.describe(info))
        print("\nNothing to download.")
        return
    total = sum(i["size"] for i in plan)
    print("Will download (%.1f MB total) into %s:" % (total / 1048576, toolchain.OWN_DIR))
    for i in plan:
        print("  - %-12s %-34s %5.1f MB  %s" % (i["what"], i["name"], i["size"] / 1048576, i["url"]))
    if a.dry_run:
        return

    os.makedirs(toolchain.OWN_DIR, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=toolchain.OWN_DIR) as tmp:
        for item in plan:
            f = download(item, tmp)
            if item["what"] == "electron":
                dest = item["dest"][:-len(".zip")]
                toolchain.electron_dir({"zip": f, "version": item["name"].split("-")[1].lstrip("v")})
                os.remove(f)
            else:
                os.chmod(f, 0o644 if item["what"] == "emoji font" else 0o755)
                os.replace(f, item["dest"])
                dest = item["dest"]
            print("  installed %s → %s" % (item["what"], dest))

    print()
    after = toolchain.detect()
    print(toolchain.describe(after))
    sys.exit(0 if after["ready"] else 1)


if __name__ == "__main__":
    main()
