# Writing the course: pedagogy for complete beginners

Contents
- The reader you are writing for
- Anatomy of a lesson
- Explaining things simply (rules and before/after)
- Using the interactive blocks well
- Balancing theory and practice
- Quizzes, hints, tests
- Coverage and faithfulness to the book
- Tone and language (Polish/English)
- Self-review checklist

## The reader you are writing for
A motivated adult who has never studied this subject. They read on a phone or laptop in 15–25 minute sessions, get stuck
without anyone to ask, and quit when a lesson feels like a wall of text or when something is used before it is explained.
Everything below follows from that: **small steps, nothing unexplained, constant doing, quick wins.**

## Anatomy of a lesson (15–25 minutes)
1. **Hook + goal** (`text`, 2–4 sentences): what they will be able to *do* after this lesson, and why it matters in plain terms.
2. **Intuition** (`callout` kind `analogy`): an everyday comparison before any jargon.
3. **Core idea in small pieces**: `text` blocks ≤150 words, each with ONE idea; follow each idea with a tiny example (`code`).
4. **Walk through** (`stepper` or `flow`) for anything that happens over time — code execution, a request travelling, an algorithm.
5. **Check yourself early** (`reveal` or a 2–3 question `quiz`) right after the core idea, not only at the end.
6. **Edge/pitfall** (`callout` kind `warning`): the typical mistake and how it looks.
7. **Practice** (`exercise` or a longer `quiz`): apply the idea once on their own. First exercise in a chapter is easy.
8. **Wrap-up** (`summary`, 3–5 points) + `terms` for the glossary.
Not every lesson needs every part, but never ship a lesson with only text, and never end without `summary`.

## Explaining things simply
- **Define before use.** The first time a term appears, explain it in the same sentence or the sentence after. If the book uses a term that was never introduced, introduce it (and add it to `terms`).
- **Concrete → abstract.** Show an example, then name the rule. ("Look at this: … This pattern is called a *slice*.")
- **One idea per block.** If a block needs "and also", it's two blocks.
- **Short sentences, active voice, everyday words.** Prefer "the computer remembers the value" to "the value is persisted in memory". Keep the book's official term, but explain it once in plain words.
- **Show the invisible.** Beginners can't see what the machine does. Use a `stepper` to trace code line by line with the changing values in the `output` or `md`; use `flow` for pipelines; draw memory/boxes/arrows with `svg` when a picture is worth 100 words.
- **Analogies with limits.** Say where the analogy breaks ("unlike a real box, a variable can't hold two things at once").
- **Anticipate the "why".** One sentence on why something exists removes a lot of confusion ("Go makes you handle errors explicitly so a failure can't hide").
- **Worked example → partly filled → their own.** The first time a skill appears, do it for them; next, give a `fill` question or an exercise with a hint; then a free exercise.
- **Normalize confusion.** "Most people find this confusing at first" is true and kind. Never write "obviously", "simply", "just", "as you know".

Before / after (a text block):
- Before: *"A goroutine is a lightweight thread managed by the Go runtime, multiplexed onto OS threads."* — three undefined terms.
- After: *"Sometimes you want your program to do two things at once — for example, download a file and keep the screen responsive. In Go you start the second job with the word `go`. Go calls such a job a **goroutine**. Think of it as hiring a helper who works alongside you."* then a 3-line code example, then a stepper showing both running.

## Using the interactive blocks well
- `stepper`: 3–7 steps; same listing repeated with different `highlight`; each step says what *changes* and why.
- `flow`: processes with ≤7 stages; the `detail` of each node says what happens there.
- `reveal`: "what do you think happens?" prediction questions — prediction before explanation is one of the strongest learning moves.
- `callout key`: at most one per lesson — the sentence they must remember.
- `from_book`: orientation only (a short quote or a listing with page reference). Everything else is your own explanation.
- `flashcards`: terms and definitions, commands, short facts — not whole concepts. 4–10 cards, in lessons that introduce vocabulary.
- Math (`$...$`/`$$...$$`, see `references/math.md`): write the formula once, then name every symbol in it (a `table` works
  well for this) before using it again. A `stepper` can trace a worked example number by number, the same way it traces code.
- Animations are built in (blocks fade in, steppers slide, flows pulse); don't add decoration that doesn't teach something.

## Balancing theory and practice
Target 35–60% practice by time (`build_course.py` prints it per chapter). Per lesson: roughly 5–7 minutes of reading/watching for
every 8–12 minutes of doing. Per chapter: 3–5 lessons + a test; at least one real exercise (programming books: 2–4, ending with a small
"mini-project" that combines the chapter's ideas). If the book is dense theory (e.g. algorithms, law, history), practice means
prediction questions, classification tasks (`order`, `multi`), applying a rule to a new case, and self-check exercises — not more reading.
For math books specifically: `numeric` questions (not `fill`) whenever the answer is a number — it accepts `0.5`/`0,5`/`1/2` and
a `tolerance` instead of demanding one exact string — `order` of the steps in a proof or derivation, and `reveal` predictions
("what does this simplify to?") before showing the next line.

## Quizzes, hints, tests
**Questions**
- Test understanding, not recall of wording: "what does this code print?", "which line is wrong?", "which tool fits this situation?".
- Wrong options are plausible misconceptions (off-by-one, confusing `=` and `==`), never silly or trick-worded.
- No "all of the above"/"none of the above". Keep options similar in length so the answer doesn't give itself away.
- The `explanation` says **why the right answer is right and why the most tempting wrong one is wrong** — this is where learning happens.
- Mix types: `single` for concepts, `multi` for "which are true", `fill` for syntax/commands, `order` for processes, `truefalse` for quick misconceptions, code snippets for tracing.

**Hints** (1–3 per question/exercise), increasing in strength: (1) re-aim attention ("look at what `i` is on the second pass"), (2) name the concept or tool ("this is a job for `range`"), (3) nearly the answer without giving it away. Hints must never be the explanation itself.

**Chapter tests**: 8–12 questions covering every lesson in the chapter, roughly 60% understanding/application, 40% recall; ≥3 question types; `pass_score` 0.7. They are checked at the end with full explanations, so write explanations as if each were a mini-lesson.

## Coverage and faithfulness to the book
- Keep the book's order and its definitions of terms unless the order is a real obstacle for beginners (then say so in `plan.md`).
- Every substantial section of the source maps to some lesson (see the coverage map in `.build/plan.md`). If you skip or merge something deliberately, note why.
- Preserve the book's examples where they teach well (your own rewrite of the code with the book's scenario); add *more* examples where beginners need them.
- Don't invent facts the book doesn't support; if you add background to make a step understandable, keep it minimal and general.
- Quotes: a short excerpt with page/section reference at most; otherwise paraphrase.
- Never leave out the hard parts. Slow down there: more steps, an extra analogy, an extra worked example.

## Tone and language
- Warm, direct, respectful; "you". In Polish prefer forms that don't assume the learner's gender where easy (e.g. "uruchom program", "możesz sprawdzić") — avoid past-tense gendered forms like "napisałeś/napisałaś" (the player's own messages already do).
- Keep consistent translations of technical terms across the course; record them with `course_state.py DIR note "slice = wycinek (tablicy)"`.
- Code, identifiers, commands and error messages stay in the original language; explain them in the course language.
- Emoji: only in callout/UI contexts the player already provides; don't sprinkle them in text.

## Self-review checklist (before marking a chapter done)
- [ ] Could someone with zero background follow every lesson? Is any term used before it is defined?
- [ ] No text block over ~150 words; each lesson has an analogy or concrete example and at least one trace/diagram where something *happens*.
- [ ] Every lesson ends with `summary`; every quiz question has a hint and an explanation.
- [ ] Practice share looks right; the chapter has a test and ≥1 exercise; first exercise is easy.
- [ ] All sections of the source chapter are covered (or consciously merged).
- [ ] Explicit unique ids on every quiz/exercise/flashcards block.
- [ ] `build_course.py` clean, `verify_exercises.py` all OK.
