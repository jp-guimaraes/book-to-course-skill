#!/usr/bin/env python3
"""Validate the lesson JSON files and bundle them into course/data.js.

Usage:  build_course.py COURSE_DIR [--single-file OUT.html] [--force]

Reads   content/course.json, content/<chapter-id>/chapter.json, content/<chapter-id>/*.json (lessons, sorted by file name),
        exercises/<dir>/exercise.json (+ starter/test/_solution files)
Writes  course/data.js   (only when there are no errors, unless --force)
        optionally one self-contained HTML file (--single-file) to preview or share without the folder

Prints errors (must fix), warnings (should look at) and a theory-vs-practice balance table per chapter.
"""
import argparse
import datetime
import json
import math
import os
import re
import shlex
import sys

from ui_langs import ui_lang_packs, ui_strings

BLOCK_REQ = {
    "text": ["md"], "callout": ["md"], "code": ["code"], "stepper": ["steps"], "reveal": ["prompt", "md"],
    "from_book": ["md"], "table": ["headers", "rows"], "flow": ["nodes"], "svg": ["svg"], "quiz": ["questions"],
    "exercise": ["title", "goal"], "flashcards": ["cards"], "summary": ["points"], "derivation": ["steps"],
}
REL_RE = re.compile(r"^[^\n]{1,12}$")
CALLOUTS = {"tip", "note", "warning", "analogy", "key", "example"}
ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
EX_MINUTES = {"easy": 8, "medium": 15, "hard": 25}
MATH_SPAN = re.compile(r"\$\$.+?\$\$|(?<!\\)\$\S.*?(?<!\\)\$(?!\d)", re.S)
LATEX_ENV_RE = re.compile(r"\\(begin|end)\{([A-Za-z]+)\}")
LATEX_CMD_RE = re.compile(r"\\([A-Za-z]+)")
CTRL_CHARS = (("\x08", "b"), ("\x0c", "f"), ("\x09", "t"))
BACKTICK_SPAN = re.compile(r"`[^`]+`")
# fields that hold code, raw values or bookkeeping, never author-facing prose/markdown —
# skipped when linting LaTeX so e.g. a bash `$HOME` or a gofmt tab isn't read as broken math
NON_PROSE_KEYS = {
    "code", "output", "solution", "input", "command", "command_display", "lang", "language",
    "id", "type", "file", "exercise_dir", "kind", "difficulty", "answer", "placeholder",
    "pages", "sections", "chapter", "svg", "highlight",
    # derivation: bare LaTeX (no $ delimiters) — linted directly with bare=True instead
    "lhs", "rhs", "rel", "result",
}


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def err(self, where, msg):
        self.errors.append("%s: %s" % (where, msg))

    def warn(self, where, msg):
        self.warnings.append("%s: %s" % (where, msg))


def wc(s):
    # a $formula$ counts as one word — LaTeX source (\frac{a}{b} = 3 "words") would
    # otherwise skew the 220-word warning and the theory-minutes estimate
    return len(re.findall(r"\w+", MATH_SPAN.sub(" formula ", s or ""), re.UNICODE))


def load_math_cmds(root):
    """Read assets/app.js's MATH-CMDS span so the lint allowlist can never drift from the renderer."""
    try:
        with open(os.path.join(root, "assets", "app.js"), encoding="utf-8") as f:
            app_js = f.read()
    except OSError:
        return None
    m = re.search(r"/\* MATH-CMDS-START \*/(.*?)/\* MATH-CMDS-END \*/", app_js, re.S)
    if not m:
        return None
    names = set()
    for lit in re.findall(r'"([^"]*)"', m.group(1)):
        names.update(lit.split())
    return names


def _lint_formula(rep, body, where, cmds):
    if cmds is None:
        return
    depth = 0
    for ch in body:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                rep.err(where, "formula has an extra '}' — braces are unbalanced")
                return
    if depth != 0:
        rep.err(where, "formula has %d unclosed '{'" % depth)
    left, right = body.count("\\left"), body.count("\\right")
    if left != right:
        rep.err(where, "\\left and \\right are unbalanced (%d \\left, %d \\right)" % (left, right))
    envs = LATEX_ENV_RE.findall(body)
    stack = []
    for kind, name in envs:
        if kind == "begin":
            stack.append(name)
        elif not stack or stack.pop() != name:
            rep.err(where, "\\end{%s} does not match the corresponding \\begin" % name)
            return
    if stack:
        rep.err(where, "\\begin{%s} has no matching \\end" % stack[-1])
    names = set(m.group(1) for m in LATEX_CMD_RE.finditer(body)) | set(n for _, n in envs)
    unknown = sorted(names - cmds - {"limits", "nolimits"})
    if unknown:
        rep.err(where, "unsupported LaTeX command(s) \\%s — see references/math.md for the supported subset" % ", \\".join(unknown))


def lint_latex(rep, src, where, bare=False):
    if not src:
        return
    # backtick code wins over math in inline() too, so `$HOME` or `` `$x` `` must not be
    # read as a dollar/formula here — the control-char check must also skip code's own tabs
    body = src if bare else BACKTICK_SPAN.sub(" ", src)
    for ch, name in CTRL_CHARS:
        if ch in body:
            rep.err(where, "contains a literal \\%s control character — write it as \\\\%s in the JSON string" % (name, name))
    if bare:
        _lint_formula(rep, body, where, rep.math_cmds)
        return
    if len(re.findall(r"(?<!\\)\$", body)) % 2:
        rep.err(where, "odd number of '$' — unbalanced math delimiter (escape a literal dollar sign as \\$)")
    for m in MATH_SPAN.finditer(body):
        _lint_formula(rep, m.group(0).strip("$"), where, rep.math_cmds)
    # currency check only outside already-matched math spans, or "$3 \cdot x$" would self-flag
    outside_math = MATH_SPAN.sub(" ", body)
    for m in re.finditer(r"(?<!\\)\$(\d[\d.,]*)\s", outside_math):
        rep.warn(where, "'$%s' looks like a currency amount, not math — escape it as \\$ if that's intended" % m.group(1))


def check_text(b, where, rep):
    """Lint LaTeX in prose/markdown fields only — never in code, output, or bookkeeping fields."""
    def walk(x, key=None):
        if isinstance(x, str):
            if key not in NON_PROSE_KEYS:
                lint_latex(rep, x, where)
        elif isinstance(x, dict):
            for k, v in x.items():
                walk(v, k)
        elif isinstance(x, list):
            for v in x:
                walk(v, key)
    walk(b)


def load_json(path, rep):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except ValueError as e:
        rep.err(os.path.relpath(path), "invalid JSON — %s" % e)
    except OSError as e:
        rep.err(os.path.relpath(path), str(e))
    return None


def as_list(x):
    if x is None:
        return []
    return list(x) if isinstance(x, (list, tuple)) else [x]


def check_question(q, where, rep, test_mode):
    if not isinstance(q, dict):
        rep.err(where, "question must be an object")
        return
    q.setdefault("type", "single")
    t = q["type"]
    if not str(q.get("q", "")).strip():
        rep.err(where, "question has no `q` text")
    if t == "single":
        o, a = q.get("options"), q.get("answer")
        if not (isinstance(o, list) and len(o) >= 2):
            rep.err(where, "single: need `options` (≥2)")
        elif not (isinstance(a, int) and not isinstance(a, bool) and 0 <= a < len(o)):
            rep.err(where, "single: `answer` must be the index (0-based) of the correct option")
        elif len(o) > 6:
            rep.warn(where, "more than 6 options is a lot")
    elif t == "multi":
        o, a = q.get("options"), q.get("answer")
        if not (isinstance(o, list) and len(o) >= 3):
            rep.err(where, "multi: need `options` (≥3)")
        elif not (isinstance(a, list) and a and all(isinstance(i, int) and 0 <= i < len(o) for i in a)):
            rep.err(where, "multi: `answer` must be a non-empty list of valid indices")
        elif len(a) == len(o):
            rep.warn(where, "multi: every option is correct — likely a mistake")
    elif t == "truefalse":
        if not isinstance(q.get("answer"), bool):
            rep.err(where, "truefalse: `answer` must be true or false")
    elif t == "fill":
        a = q.get("answer")
        if not (isinstance(a, str) and a.strip()) and not (isinstance(a, list) and a and all(isinstance(x, str) and x.strip() for x in a)):
            rep.err(where, "fill: `answer` must be a string or a list of accepted strings")
    elif t == "order":
        it = q.get("items")
        if not (isinstance(it, list) and len(it) >= 2):
            rep.err(where, "order: `items` must list the steps in the CORRECT order (≥2); the page shuffles them")
    else:
        rep.err(where, "unknown question type '%s' (single, multi, truefalse, fill, order)" % t)
    if not q.get("explanation"):
        rep.warn(where, "no `explanation` — learners learn most from the 'why'")
    if "hint" in q:
        q["hints"] = as_list(q.pop("hint")) + as_list(q.get("hints"))
    q["hints"] = [h for h in as_list(q.get("hints")) if h]
    if not q["hints"]:
        rep.warn(where, "no hint")


def read_text_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def embed_exercise(b, root, where, rep):
    """Resolve exercise_dir → files, command, etc. Mutates block b."""
    d = b.get("exercise_dir")
    if not d:
        b["mode"] = "selfcheck"
        if not b.get("examples") and not b.get("checklist"):
            rep.warn(where, "selfcheck exercise without `examples` or `checklist` — learner can't verify the result")
        if not (b.get("solution") or b.get("solution_explain")):
            rep.warn(where, "no `solution`")
        for k in ("hints",):
            b[k] = [h for h in as_list(b.get(k)) if h]
        return
    b["mode"] = "tests"
    ex_dir = os.path.join(root, "exercises", d)
    cfg = load_json(os.path.join(ex_dir, "exercise.json"), rep) if os.path.isdir(ex_dir) else None
    if cfg is None:
        if not os.path.isdir(ex_dir):
            rep.err(where, "exercise_dir 'exercises/%s' does not exist" % d)
        return
    cmd = cfg.get("command")
    if not (isinstance(cmd, list) and cmd and all(isinstance(c, str) for c in cmd)):
        rep.err(where, "exercises/%s/exercise.json needs `command` as a list, e.g. [\"go\",\"test\",\"-count=1\",\"./...\"]" % d)
        return
    b["dir"] = d
    b["command_display"] = " ".join(shlex.quote(c) for c in cmd)
    b.setdefault("language", cfg.get("language", ""))
    tests = as_list(cfg.get("tests"))
    all_files = []
    for base, dirs, files in os.walk(ex_dir):
        dirs[:] = [x for x in dirs if not x.startswith((".", "_")) and x not in ("__pycache__", "node_modules", "vendor")]
        for fn in files:
            rel = os.path.relpath(os.path.join(base, fn), ex_dir).replace(os.sep, "/")
            if rel != "exercise.json" and not fn.startswith(".") and not fn.endswith(".pyc"):
                all_files.append(rel)
    starter = as_list(cfg.get("starter")) or [f for f in all_files if f not in tests and not f.lower().startswith("readme")]
    if not tests:
        rep.err(where, "exercise.json lists no `tests` files")
    files = {"starter": [], "tests": [], "solution": []}
    for key, names in (("starter", starter), ("tests", tests)):
        for rel in names:
            txt = read_text_file(os.path.join(ex_dir, rel))
            if txt is None:
                rep.err(where, "exercises/%s/%s is missing or not text" % (d, rel))
            else:
                files[key].append({"path": rel, "content": txt})
    sol_dir = os.path.join(ex_dir, "_solution")
    if os.path.isdir(sol_dir):
        for base, _, fs in os.walk(sol_dir):
            for fn in sorted(fs):
                full = os.path.join(base, fn)
                txt = read_text_file(full)
                if txt is not None:
                    files["solution"].append({"path": os.path.relpath(full, sol_dir).replace(os.sep, "/"), "content": txt})
    if not files["solution"]:
        rep.err(where, "exercises/%s/_solution/ is empty — put the reference solution there (files overlay the starter files)" % d)
    b["files"] = files
    b["hints"] = [h for h in as_list(b.get("hints")) if h]
    if not b["hints"]:
        rep.warn(where, "exercise has no hints")
    if not b.get("examples") and not b.get("behavior"):
        rep.warn(where, "describe what the program must do (`behavior`) and/or give `examples` of input → output")


def check_block(b, where, lesson, ids, rep, counters):
    if not isinstance(b, dict) or "type" not in b:
        rep.err(where, "block must be an object with a `type`")
        return
    t = b["type"]
    if t not in BLOCK_REQ:
        rep.err(where, "unknown block type '%s' (valid: %s)" % (t, ", ".join(sorted(BLOCK_REQ))))
        return
    for k in BLOCK_REQ[t]:
        if b.get(k) in (None, "", []):
            rep.err(where, "%s block needs `%s`" % (t, k))
            return
    check_text(b, where, rep)
    if t in ("quiz", "exercise", "flashcards"):
        counters[t] = counters.get(t, 0) + 1
        if not b.get("id"):
            b["id"] = "%s-%s%d" % (lesson["id"], t, counters[t])
        if not ID_RE.match(str(b["id"])):
            rep.err(where, "block id '%s' may only contain letters, digits, - and _" % b["id"])
        if b["id"] in ids:
            rep.err(where, "duplicate block id '%s' (ids must be unique across the whole course — progress is stored by id)" % b["id"])
        ids.add(b["id"])
    if t == "callout" and b.get("kind", "note") not in CALLOUTS:
        rep.err(where, "callout kind must be one of %s" % ", ".join(sorted(CALLOUTS)))
    if t == "text" and wc(b["md"]) > 220:
        rep.warn(where, "text block has %d words — split it, add an example or a stepper (beginners lose focus after ~150 words)" % wc(b["md"]))
    if t == "from_book" and wc(b["md"]) > 120:
        rep.warn(where, "from_book excerpt is %d words — keep quotes short (≲100) and paraphrase the rest" % wc(b["md"]))
    if t == "stepper":
        if not all(isinstance(s, dict) and (s.get("md") or s.get("code")) for s in b["steps"]):
            rep.err(where, "every stepper step needs `md` and/or `code`")
    if t == "flow" and (len(b["nodes"]) < 2 or not all(isinstance(n, dict) and n.get("label") for n in b["nodes"])):
        rep.err(where, "flow needs ≥2 nodes, each with a `label` (and ideally `detail`)")
    if t == "table":
        n = len(b["headers"])
        if any(len(r) != n for r in b["rows"]):
            rep.err(where, "table rows must have as many cells as headers (%d)" % n)
    if t == "flashcards":
        if not all(isinstance(c, dict) and c.get("front") and c.get("back") for c in b["cards"]):
            rep.err(where, "each flashcard needs `front` and `back`")
    if t == "svg" and "<svg" not in b["svg"]:
        rep.err(where, "svg block must contain an <svg> element")
    if t == "quiz":
        if lesson.get("kind") == "test":
            b["mode"] = "test"
        for i, q in enumerate(b["questions"]):
            check_question(q, "%s q%d" % (where, i + 1), rep, b.get("mode") == "test")
        ps = b.get("pass_score")
        if ps is not None and not (isinstance(ps, (int, float)) and 0 < ps <= 1):
            rep.err(where, "pass_score must be between 0 and 1")
    if t == "exercise":
        if b.get("difficulty") and b["difficulty"] not in EX_MINUTES:
            rep.err(where, "difficulty must be easy, medium or hard")
        embed_exercise(b, rep.root, where, rep)
    if t == "derivation":
        steps = b["steps"]
        if not isinstance(steps, list) or len(steps) < 2:
            rep.err(where, "derivation needs at least 2 steps")
        else:
            if len(steps) > 8:
                rep.warn(where, "derivation has %d steps — more than ~8 is hard to follow in one block" % len(steps))
            for i, s in enumerate(steps):
                sw = "%s step %d" % (where, i + 1)
                if not isinstance(s, dict) or not str(s.get("rhs", "")).strip():
                    rep.err(sw, "needs `rhs`")
                    continue
                if not s.get("why"):
                    rep.warn(sw, "no `why` — say what algebraic move this step makes")
                rel = s.get("rel", b.get("rel", "="))
                if not isinstance(rel, str) or not REL_RE.match(rel):
                    rep.err(sw, "`rel` must be a short (≤12 char) relation symbol like = or \\le")
                    rel = None
                # lhs/rhs/rel are LaTeX source but authors (LLMs especially) will sometimes write
                # a bare JSON number ("rhs": 4) — stringify before lint_latex, which indexes into
                # the value expecting a string and otherwise raises a TypeError on an int/float
                lhs = s.get("lhs")
                lint_latex(rep, "" if lhs is None else str(lhs), sw + " lhs", bare=True)
                if rel is not None:
                    lint_latex(rep, rel, sw + " rel", bare=True)
                lint_latex(rep, str(s["rhs"]), sw + " rhs", bare=True)
        if b.get("result"):
            lint_latex(rep, str(b["result"]), where + " result", bare=True)


def lesson_minutes(les):
    theory = practice = 0.0
    for b in les["blocks"]:
        t = b.get("type")
        if t in ("text", "callout", "from_book", "reveal"):
            theory += wc(b.get("md")) / 130.0
        elif t == "stepper":
            theory += sum(wc(s.get("md")) for s in b["steps"]) / 130.0 + 0.6 * len(b["steps"])
        elif t == "flow":
            theory += 0.8 + sum(wc(n.get("detail")) for n in b["nodes"]) / 130.0
        elif t in ("code", "table", "svg"):
            theory += 0.7
        elif t == "quiz":
            practice += 0.8 * len(b["questions"])
        elif t == "exercise":
            practice += b.get("minutes") or EX_MINUTES.get(b.get("difficulty") or "medium", 15)
        elif t == "flashcards":
            practice += 0.3 * len(b["cards"])
        elif t == "derivation":
            theory += sum(wc(s.get("why")) for s in b.get("steps", []) if isinstance(s, dict)) / 130.0 + 0.5 * len(b.get("steps", []))
    return theory, practice


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("course_dir")
    ap.add_argument("--single-file", metavar="OUT.html")
    ap.add_argument("--force", action="store_true", help="write data.js even if there are errors")
    a = ap.parse_args()
    root = os.path.abspath(a.course_dir)
    rep = Report()
    rep.root = root
    rep.math_cmds = load_math_cmds(root)
    content = os.path.join(root, "content")
    meta = load_json(os.path.join(content, "course.json"), rep) or {}
    for k in ("id", "title"):
        if not meta.get(k):
            rep.err("content/course.json", "missing `%s`" % k)
    meta.setdefault("ui_lang", "pl")
    meta.setdefault("language", meta["ui_lang"])
    packs = ui_lang_packs()
    ui, missing = ui_strings(meta["ui_lang"])
    if meta["ui_lang"] not in packs:
        rep.warn("content/course.json", "ui_lang '%s' has no matching player UI pack (have: %s) — buttons and "
                  "labels will show in English while your lesson content stays in '%s'" % (
                      meta["ui_lang"], ", ".join(sorted(packs)), meta["ui_lang"]))
    elif missing:
        rep.warn("content/course.json", "UI pack '%s' lacks %d key(s), shown in English: %s" % (
            meta["ui_lang"], len(missing), ", ".join(missing)))
    if not meta.get("description"):
        rep.warn("content/course.json", "no `description` — one or two friendly sentences for the home page")

    chapters, lessons, glossary, ids = [], {}, [], set()
    lesson_ids = set()
    chapter_dirs = sorted(d for d in os.listdir(content) if os.path.isdir(os.path.join(content, d))) if os.path.isdir(content) else []
    chapter_meta = {}
    for d in chapter_dirs:
        cm = load_json(os.path.join(content, d, "chapter.json"), rep) if os.path.exists(os.path.join(content, d, "chapter.json")) else {}
        chapter_meta[d] = cm or {}
    chapter_dirs.sort(key=lambda d: (chapter_meta[d].get("order", 10 ** 6), d))

    balance = []
    for d in chapter_dirs:
        cm = chapter_meta[d]
        files = sorted(f for f in os.listdir(os.path.join(content, d)) if f.endswith(".json") and f != "chapter.json")
        if not files:
            continue
        if not cm.get("title"):
            rep.err("content/%s/chapter.json" % d, "missing `title`")
        ch = {"id": d, "title": cm.get("title", d), "summary": cm.get("summary", ""), "goals": as_list(cm.get("goals")), "lessons": []}
        th = pr = 0.0
        has_test = has_ex = False
        for fn in files:
            where = "content/%s/%s" % (d, fn)
            les = load_json(os.path.join(content, d, fn), rep)
            if not isinstance(les, dict):
                continue
            les.setdefault("id", "%s-%s" % (d, os.path.splitext(fn)[0]))
            les["chapter"] = d
            if not ID_RE.match(les["id"]):
                rep.err(where, "lesson id '%s' may only contain letters, digits, - and _" % les["id"])
            if les["id"] in lesson_ids:
                rep.err(where, "duplicate lesson id '%s'" % les["id"])
            lesson_ids.add(les["id"])
            if not les.get("title"):
                rep.err(where, "missing `title`")
            if not isinstance(les.get("blocks"), list) or not les["blocks"]:
                rep.err(where, "`blocks` must be a non-empty list")
                continue
            les.setdefault("kind", "lesson")
            counters = {}
            for i, b in enumerate(les["blocks"]):
                check_block(b, "%s block %d" % (where, i + 1), les, ids, rep, counters)
            types = [b.get("type") for b in les["blocks"] if isinstance(b, dict)]
            if les["kind"] == "test":
                has_test = True
                if "quiz" not in types:
                    rep.err(where, "a test lesson needs a `quiz` block")
                elif sum(len(b["questions"]) for b in les["blocks"] if b.get("type") == "quiz") < 6:
                    rep.warn(where, "a chapter test should have ≥6 questions")
            else:
                if "summary" not in types:
                    rep.warn(where, "no `summary` block at the end")
                if "quiz" not in types and "exercise" not in types:
                    rep.warn(where, "lesson has no practice (quiz or exercise)")
                if types and types[0] not in ("text", "callout"):
                    rep.warn(where, "start with a short `text`/`callout` that says what the learner will be able to do after the lesson")
            if "exercise" in types:
                has_ex = True
            for tm in as_list(les.get("terms")):
                if isinstance(tm, dict) and tm.get("term") and tm.get("def"):
                    glossary.append({"term": tm["term"], "def": tm["def"], "lesson": les["id"]})
                else:
                    rep.err(where, "each term needs `term` and `def`")
            try:
                t_min, p_min = lesson_minutes(les)
            except (KeyError, TypeError, AttributeError) as e:
                t_min, p_min = 0.0, 0.0
                rep.warn(where, "could not estimate minutes (%s) — minutes will show as 0" % e)
            les.setdefault("minutes", max(5, int(round((t_min + p_min) / 5.0)) * 5))
            th += t_min
            pr += p_min
            lessons[les["id"]] = les
            ch["lessons"].append(les["id"])
        if not has_test:
            rep.warn("content/%s" % d, "chapter has no test lesson (kind: \"test\")")
        if not has_ex:
            rep.warn("content/%s" % d, "chapter has no exercise")
        share = pr / (th + pr) if th + pr else 0
        balance.append((d, len(ch["lessons"]), th, pr, share))
        if th + pr > 0 and not (0.30 <= share <= 0.70):
            rep.warn("content/%s" % d, "practice share is %d%% — aim for roughly 35–60%% so theory and practice stay balanced" % round(100 * share))
        chapters.append(ch)

    if not chapters:
        rep.err("content/", "no lessons found (expected content/<chapter-id>/NN-name.json)")
    # dedupe glossary (first definition wins)
    seen, gl = set(), []
    for g in glossary:
        k = g["term"].strip().lower()
        if k in seen:
            continue
        seen.add(k)
        gl.append(g)

    print("Chapters: %d   Lessons: %d   Glossary terms: %d" % (len(chapters), len(lessons), len(gl)))
    print("\n%-14s %7s %9s %10s %9s" % ("chapter", "lessons", "theory", "practice", "practice%"))
    for d, n, th, pr, sh in balance:
        print("%-14s %7d %7d m %8d m %8d%%" % (d, n, round(th), round(pr), round(100 * sh)))
    if rep.warnings:
        print("\nWARNINGS (%d):" % len(rep.warnings))
        for w in rep.warnings[:80]:
            print("  ·", w)
        if len(rep.warnings) > 80:
            print("  … and %d more" % (len(rep.warnings) - 80))
    if rep.errors:
        print("\nERRORS (%d):" % len(rep.errors))
        for e in rep.errors:
            print("  ✗", e)
        if not a.force:
            print("\ndata.js NOT written. Fix the errors and run again.")
            sys.exit(1)

    data = {"meta": dict(meta, built_at=datetime.datetime.now().astimezone().isoformat(timespec="seconds"), version=1),
            "ui": ui, "chapters": chapters, "lessons": lessons, "glossary": gl}
    js = "window.COURSE = " + json.dumps(data, ensure_ascii=False).replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029") + ";\n"
    os.makedirs(os.path.join(root, "course"), exist_ok=True)
    with open(os.path.join(root, "course", "data.js"), "w", encoding="utf-8") as f:
        f.write(js)
    print("\nWrote course/data.js (%d KB)" % (len(js) // 1024))

    sp = os.path.join(root, ".build", "state.json")
    if os.path.exists(sp):
        st = json.load(open(sp, encoding="utf-8"))
        for c in st["chapters"]:
            built = next((len(ch["lessons"]) for ch in chapters if ch["id"] == c["id"]), None)
            if built is not None:
                c["lessons_built"] = built
        with open(sp, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)

    if a.single_file:
        html = open(os.path.join(root, "index.html"), encoding="utf-8").read()
        css = open(os.path.join(root, "assets", "style.css"), encoding="utf-8").read()
        app = open(os.path.join(root, "assets", "app.js"), encoding="utf-8").read()
        html = html.replace('<link rel="stylesheet" href="assets/style.css">', "<style>\n%s\n</style>" % css)
        html = html.replace('<script src="course/data.js"></script>', "<script>\n%s</script>" % js)
        html = html.replace('<script src="assets/app.js"></script>', "<script>\n%s\n</script>" % app.replace("</script", "<\\/script"))
        with open(a.single_file, "w", encoding="utf-8") as f:
            f.write(html)
        print("Wrote single-file page:", a.single_file, "(progress is kept in the browser only; exercise test buttons need serve.py)")


if __name__ == "__main__":
    main()
