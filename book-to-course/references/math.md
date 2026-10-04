# Math in lessons

Contents
- Writing formulas
- Supported LaTeX subset
- What's out of scope (and what to use instead)
- How failures show up

## Writing formulas

`$...$` for inline math, `$$...$$` on its own line(s) for display math. Both work in any `md`/text field: `text`,
`callout`, `code.explain`, `from_book`, `stepper` steps, `reveal`, `flow` node `detail`, quiz `q`/`explanation`/`intro`,
exercise `goal`/`behavior`/`solution_explain`, and also in plain `inline` fields: table cells, quiz options, flashcard
faces, hints, checklist items, the lesson/chapter summary. A literal dollar sign is `\$` (JSON: `"\\$"`), so "it costs
\$5" stays plain text instead of being read as the start of a formula.

```json
{ "type": "text", "md": "The quadratic formula is $x = \\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}$." }
```

There is no `\(...\)`/`\[...\]` — only `$`/`$$`, to keep JSON escaping down to one rule.

## Supported LaTeX subset

| Category | Commands |
|---|---|
| Atoms | digits, single letters, `+ - = < > / \| ! , ; : . ( ) [ ] \{ \}`, `\cdot \times \div \pm \mp \ast \circ \ne \neq \le \leq \ge \geq \ll \gg \approx \equiv \sim \simeq \cong \propto \infty \partial \nabla \degree` |
| Greek | `\alpha`…`\omega`, `\varepsilon \vartheta \varpi \varrho \varsigma \varphi`, `\Gamma \Delta \Theta \Lambda \Xi \Pi \Sigma \Upsilon \Phi \Psi \Omega` |
| Structure | `{...}`, `^`, `_`, `\frac \dfrac \tfrac \binom`, `\sqrt{}`, `\sqrt[n]{}`, `\left...\right` with `( ) [ ] \{ \} \| \langle \rangle \lfloor \rfloor \lceil \rceil .` |
| Big operators | `\sum \prod \coprod \int \iint \iiint \oint \bigcup \bigcap \bigoplus \lim \limsup \liminf \max \min \sup \inf`, plus `\limits`/`\nolimits` |
| Functions | `\sin \cos \tan \cot \sec \csc \arcsin \arccos \arctan \sinh \cosh \tanh \log \ln \lg \exp \deg \gcd \dim \ker \Pr`, `\operatorname{...}` |
| Arrows/dots | `\to \rightarrow \leftarrow \leftrightarrow \Rightarrow \Leftarrow \Leftrightarrow \implies \iff \mapsto \ldots \cdots \vdots \ddots \dots` |
| Decorations | `\hat \widehat \bar \overline \vec \tilde \widetilde \dot \ddot \overbrace \underbrace \overrightarrow \underline` |
| Matrices/envs | `matrix pmatrix bmatrix Bmatrix vmatrix Vmatrix cases aligned array`, with `&` and `\\` |
| Sets/logic | `\in \notin \ni \subset \subseteq \supset \supseteq \cup \cap \setminus \emptyset \varnothing \forall \exists \nexists \neg \lnot \land \wedge \lor \vee \mid \colon`, `\mathbb{N Z Q R C}` |
| Fonts | `\mathrm \mathbf \mathit \mathbb \mathcal \mathfrak \mathsf \mathtt \boldsymbol` |
| Text/space | `\text{} \textbf{} \textit{}`, `\, \: \; \! \quad \qquad \phantom{}` |
| Misc | `\pmod \bmod` |

Font commands only take a short literal run of characters as their argument (letters/digits, as in `\mathbb{R}`,
`\mathrm{d}`, `\mathbf{v}`) — not a nested sub-expression.

## What's out of scope (and what to use instead)

- Macro definitions (`\newcommand`, `\def`) — write the formula out each time.
- Numbered/multi-equation alignment (`\begin{align}`, `\tag`) — use several `$$...$$` blocks, or `aligned` for a single
  multi-row block without numbering.
- `\substack`, `\genfrac`, `\overset`/`\underset`, `\xrightarrow[]{}`, `\color`, arbitrary `\hspace{}`, sizing commands
  (`\big`/`\Big`/`\bigg` — use `\left...\right` instead), commutative diagrams, `\label`/`\ref`.
- Function/geometry plots — draw them as an `svg` block (see `lesson-schema.md`), not as a formula.

A command outside this subset, or unbalanced `{}`/`$`/`\left`/`\right`/`\begin`/`\end`, is a **build error**: it names
the file, the block and the bad command so you can fix it before it ever reaches a learner.

## How failures show up

If a broken formula somehow reaches the page anyway (it shouldn't — the build should have caught it first), it renders
as the raw LaTeX source with a dotted underline instead of blanking the lesson. Hovering it shows what went wrong. Treat
that as a sign the build step was skipped, not as acceptable output to ship.

The player also detects browsers without MathML support (Chrome/Edge before 109, released January 2023 — also the last
version available on Windows 7/8, so in practice the affected set is very small) and falls back, the first time a
formula actually needs it, to a neutral monospace style for every formula on the page, plus a one-time banner telling
the learner to update their browser. This means an outdated browser degrades to readable LaTeX source instead of
garbled, unstyled glyphs.
