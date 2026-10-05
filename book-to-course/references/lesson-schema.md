# Lesson schema (what `build_course.py` accepts and the player renders)

Contents
- Files and ids
- course.json / chapter.json
- Lesson file
- Text formatting (mini-Markdown)
- Block types: text, callout, code, stepper, derivation, flow, reveal, from_book, table, svg, quiz, exercise, flashcards, summary
- Question types
- Test lessons
- Validation rules the builder enforces

## Files and ids

```
content/course.json
content/ch01/chapter.json
content/ch01/01-intro.json         lessons are ordered by file name → use 01-, 02-, … and 99-test.json for the chapter test
content/ch01/02-variables.json
content/ch01/99-test.json
```
The chapter folder name is the chapter id (use the id from the manifest: `ch01`, `ch02`…) and must match `.build/state.json`
so progress tracking works. Lesson id defaults to `<chapter>-<file name without .json>`; set `"id"` only when needed.
Ids may contain letters, digits, `-` and `_`. Block ids (quiz / exercise / flashcards) must be unique across the whole course.
They are auto-generated when omitted (`<lesson-id>-quiz1`) but **write explicit ids** — progress is stored by id.

## course.json
```json
{ "id": "go-dla-poczatkujacych", "title": "Go dla początkujących", "subtitle": "Od zera do pierwszych programów",
  "description": "Kurs krok po kroku… (1–2 friendly sentences, Markdown allowed)",
  "ui_lang": "pl", "language": "pl", "level": "beginner",
  "source": { "title": "Original book title", "author": "Author", "file": "book.epub" } }
```
`ui_lang` is the language code of the interface strings. The player ships `pl` and `en`; any other code works but shows English buttons and labels (build_course.py warns). To add a language, copy `assets/i18n/en/` to `assets/i18n/<code>/` and translate its `strings.json` (values only — keys stay as they are) and `README.md`. Created by `init_course.py`; you fill `subtitle` and `description`.

## chapter.json
```json
{ "title": "Zmienne i typy", "summary": "One sentence shown on the home page.", "goals": ["Declare variables", "Choose a type"], "order": 2 }
```
`order` is optional (folder names sort naturally).

## Lesson file
```json
{ "title": "Zmienne — pudełka na dane",
  "summary": "One sentence: what the learner will be able to do after this lesson.",
  "minutes": 20,
  "source": { "chapter": "ch02", "sections": ["2.1 Variables", "2.2 Zero values"], "pages": "31-38" },
  "blocks": [ …blocks… ],
  "terms": [ { "term": "zmienna", "def": "nazwane miejsce w pamięci na wartość" } ] }
```
`minutes` is computed if omitted. `source` is optional but helps you (and later you) check coverage. `terms` feed the glossary page
and a "new terms" box at the end of the lesson (first definition of a term wins). `"kind": "test"` makes a chapter test (below).

## Text formatting (used in every `md`, `goal`, `explanation`, `hint`… field)
Paragraphs separated by blank lines; `**bold**`, `*italic*`, `` `code` ``, `[text](https://…)`, `- bullets`, `1. numbered`, `> quote`,
`### small heading`, and fenced code blocks (```go … ```). HTML is escaped, so write plain text. No tables or nested lists inside `md`
(use the `table` block).

Math: `$...$` for inline formulas, `$$...$$` on its own line(s) for display formulas, in any `md`/text field (including
table cells, quiz options, flashcard faces). A literal dollar sign is `\$` (e.g. "it costs \$5"). LaTeX is translated to
MathML by a small built-in subset — see `references/math.md` for exactly which commands are supported. An unsupported
command or unbalanced braces/`$` is a **build error** naming the file, block and the bad command, so a broken formula
never reaches the page; in the rendered page itself (if it somehow gets past the build) it shows as the raw LaTeX source
with a dotted underline instead of blanking the lesson. There is no plot/graph renderer: draw geometry or function graphs
as an `svg`.

## Block types

Every block is `{ "type": "...", … }`. Required fields marked *.

### text — a paragraph or two of explanation
`{ "type": "text", "title": "optional h3", "md": "…"* }` — keep under ~150 words; split or add an example otherwise (the builder warns above 220).

### callout — highlighted aside
`{ "type": "callout", "kind": "tip|note|warning|analogy|key|example", "title": "optional", "md": "…"* }`
Use `analogy` to explain hard ideas with everyday things, `key` for the one sentence to remember, `warning` for common mistakes.

### code — a listing with syntax highlighting
`{ "type": "code", "lang": "go", "file": "main.go", "code": "…"*, "caption": "…", "output": "text the program prints", "output_label": "…", "explain": "md shown below", "title": "optional" }`
Highlighted languages: go, python, js/ts, java/c#/kotlin, c/c++, rust, bash, sql. Others display as plain code.

### stepper — animated step-by-step walkthrough (the main tool for explaining code or a process)
```json
{ "type": "stepper", "title": "Jak działa pętla", "lang": "go", "steps": [
  { "title": "Start", "md": "Explain this step.", "code": "for i := 0; i < 3; i++ {\n    fmt.Println(i)\n}", "highlight": [1], "output": "0" },
  { "title": "Pierwszy obrót", "md": "…", "code": "…same listing…", "highlight": [2], "output": "0\n1" } ] }
```
Each step needs `md` and/or `code`. Repeating the same listing with different `highlight` line numbers (1-based) walks the learner
through it — ideal for tracing execution. Use 3–7 steps.

### derivation — step-by-step algebra (the math equivalent of `stepper`)
```json
{ "type": "derivation", "title": "Solving 2x + 6 = 10", "intro": "optional md", "rel": "=",
  "steps": [
    { "lhs": "2x + 6", "rhs": "10", "why": "The equation from the task." },
    { "lhs": "2x",     "rhs": "4",  "why": "Subtract 6 from both sides." },
    { "rhs": "2",       "why": "Divide both sides by 2." }
  ],
  "result": "x = 2", "note": "optional md shown under the steps" }
```
`lhs`/`rhs`/`rel`/`result` are **bare LaTeX — no `$` delimiters** (they're always treated as math); `why` is a normal md field, so
`$…$` works inside it. `rhs` is required on every step; an omitted `lhs` leaves that cell blank — use it for a continuation line
that keeps working on the previous line's result. `rel` defaults to the block's own `rel` (itself defaulting to `=`); set it per
step for a line that changes relation (e.g. `\le`, `\approx`). One algebraic move per step, ≥2 steps, up to about 8. The learner
steps through like a `stepper` (dots, prev/next) or reveals every line at once with "Show all".

### flow — click-through process diagram
`{ "type": "flow", "title": "…", "nodes": [ { "label": "Kod źródłowy", "detail": "md shown when the node is reached" }, … ] }` (2–7 nodes)

### reveal — "think first" question with a hidden answer
`{ "type": "reveal", "prompt": "What will this print?", "md": "answer + why" }`

### from_book — a short excerpt or listing from the source, labelled "From the book"
`{ "type": "from_book", "source": "ch. 3, p. 41", "md": "short quote (≲100 words)", "code": "optional listing from the book", "lang": "go" }`
Use sparingly: the point is orientation ("this is what the book says / shows"), not reproduction. Quote only short passages and
cite where.

### table
`{ "type": "table", "headers": ["Typ", "Zakres"], "rows": [["`int8`", "-128…127"], …] }` — every row must have as many cells as headers; inline formatting works in cells.

### svg — custom diagram or illustration
`{ "type": "svg", "caption": "…", "svg": "<svg viewBox='0 0 400 200' xmlns='http://www.w3.org/2000/svg'>…</svg>" }`
Use `currentColor` for strokes/text so it works in dark mode; SMIL (`<animate>`) and CSS animations inside the SVG are allowed;
scripts and event handlers are stripped. Prefix any CSS class names you define inside the SVG (they are global).

### quiz — inline practice with immediate feedback
```json
{ "type": "quiz", "id": "ch02-quiz-types", "title": "Szybki quiz", "intro": "optional md",
  "questions": [ …questions… ] }
```
2–5 questions per lesson. Per question the learner can ask for hints, check, retry, and reveal the answer.

### exercise — hands-on task (details in `exercises.md`)
Two modes: **tests** (`exercise_dir`: the learner edits files in `exercises/<dir>/`, unit tests verify them) and **selfcheck**
(no folder; the learner writes/does something and compares with examples and a checklist).
```json
{ "type": "exercise", "id": "ch02-ex-swap", "title": "Zamiana wartości", "difficulty": "easy|medium|hard", "minutes": 10,
  "goal": "md: what to build, one or two sentences",
  "behavior": "md: precise description of what the program/function must do (inputs, outputs, edge cases)",
  "examples": [ { "input": "swap(1, 2)", "output": "2, 1", "note": "optional" } ],
  "hints": ["gentle nudge", "stronger hint", "almost the answer"],
  "exercise_dir": "ch02-swap",                 // tests mode — folder under exercises/
  "checklist": ["…"],                           // selfcheck mode: things the learner verifies
  "solution": "code string",  "solution_lang": "go",   // selfcheck mode (tests mode takes files from exercises/<dir>/_solution/)
  "solution_explain": "md: why this works" }
```

### flashcards — spaced self-test of terms
`{ "type": "flashcards", "id": "ch02-cards", "title": "Fiszki", "cards": [ { "front": "zmienna", "back": "nazwane miejsce w pamięci" }, … ] }` (4–10 cards)

### summary — end of lesson (always include; last block)
`{ "type": "summary", "title": "optional", "points": ["3–5 short takeaways, each a full sentence"] }`

## Question types (inside `quiz.questions`)

Common fields: `q`* (md), `explanation` (md, shown after a correct answer or after "show answer"), `hint` (string) or `hints` (list, revealed one by one), `code` + `lang` (a snippet shown under the question).

| type | fields | notes |
|---|---|---|
| `single` (default) | `options`* (2–6 strings), `answer`* (0-based index) | one correct option |
| `multi` | `options`* (≥3), `answer`* (list of indices) | all-or-nothing |
| `truefalse` | `answer`* (true/false) | statement in `q` |
| `fill` | `answer`* (string or list of accepted strings), `ignore_case` (default true), `placeholder` | short typed answer; case and extra spaces ignored; accept variants (`["x := 1", "x:=1"]`) |
| `order` | `items`* (≥2 strings **in the correct order**) | the page shuffles them; learner reorders with ↑/↓ |

"Find the bug" or "what does this print?" = `single`/`fill` with a `code` snippet.

## Test lessons (chapter test)
`content/<chapter>/99-test.json`:
```json
{ "title": "Test: Zmienne i typy", "kind": "test", "summary": "Sprawdź wiedzę z całego rozdziału.",
  "blocks": [ { "type": "quiz", "id": "ch02-test", "pass_score": 0.7, "questions": [ …8–12 questions… ] } ] }
```
In test mode there is no per-question check: the learner answers everything, presses "Check test", sees the score, and then
each question with the correct answer and explanation. Hints are available while answering. Passing (`pass_score`, default 0.7)
completes the lesson; retries are allowed and the best score is kept. Mix question types and cover every lesson of the chapter.

## What the builder enforces
Errors (no `data.js` until fixed): invalid JSON, unknown block/question type, missing required fields, answers out of range,
duplicate ids, table rows of the wrong width, missing exercise files / `_solution/`, test lesson without a quiz, and for
any `$...$`/`$$...$$` formula: unbalanced `{}`/`$`, unmatched `\left`/`\right` or `\begin`/`\end`, or a command outside the
supported subset (`references/math.md`).
Warnings (read them): text block > 220 words (math formulas count as one word each, not their LaTeX source length),
`from_book` > 120 words, question without explanation or hint, lesson without `summary` or practice, chapter without test
or exercise, practice share outside 30–70%, a `$amount` that looks like currency rather than math (escape it as `\$`).
