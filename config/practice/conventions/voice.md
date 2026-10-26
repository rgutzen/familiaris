# Voice — how this system's prose and documents read

## Scope

This file defines how the agent **writes into the user's system** — commits, leaves, READMEs, design docs.
NOT how to communicate with the user (`collaboration.md` — its §Language rules
govern sentences here too; this file's rules sit above the sentence).
NOT how to write as the user (`../user/user-voice.md`).

## Structure — decided before the first sentence

**One genre per document.** The strongest single separator in the ranking. A
document is a task list, a status board, a router, or a decision record —
not several. A section that does not serve the file's genre belongs in the file
whose genre it is, with a pointer left behind.

**Overview before detail.** Open with the table, the map or the routing rule.
Detail is what a reader descends into, never what they wade through first. Past
roughly 40 unbroken lines a section stops being scannable.

**Length — a soft ceiling of 300 lines.** Past it a document has almost always
taken on a second genre or started restating another file; splitting usually
fixes both — the file-grain form of *sprawl* (§Placement). Exceed it only when
the material genuinely will not divide, and say why in the document.

## Representation — choose the form before the sentence

Prose is the fallback. Pick the form by the shape of the content:

| Content | Form |
|---|---|
| comparison, parallel set of facts | table |
| relation, flow, dependency, decision path | `mermaid` flowchart |
| hierarchy, containment | indented tree, or a nested `mermaid` block |
| sequence | numbered list |
| a concept figure a person outside the session will read — an architecture, a filing decision, a process with hand-offs | `diagram-design` (the skill), drawn as SVG with its HTML source beside it, embedded; the skill's local notes own when it does not apply, and its checks gate the file |
| quantity or share | inline bars in a table (`▇▇▇▇····`); a running series in chat is `asciichartpy.plot([…])`; a leaf gets a `matplotlib` chart, PNG/SVG, embedded |
| one fact, or a nuance that resists a shape | sentence |

**A figure replaces the prose it duplicates.** Delete the paragraph that
described the same structure: a diagram beside its own explanation is the
duplication §Pruning bans. Limits, exceptions and confidence labels stay in
words next to the figure. Past ~15 lines a diagram has become a second
document — split it or drop it; a diagram is not a code listing, so §Never's
~10-line bound does not apply, and §Verification reads it as replacing its prose.

**One source, two renderings.** A `mermaid` block renders in place inside the
vault (`memory/**`), and is the form for a figure that changes with its
register or with every commit — generation keeps it true. An authored concept
figure travels as an exported SVG beside its HTML source (the viewer renders
the SVG; the source is the editable form); a chart computed from numbers stays
a `matplotlib` PNG with the script that drew it next to it — never hand-placed
marks. `termaid file.mmd` renders the same source as terminal text for a chat
reply — under ~30 lines and ~100 columns, and never an image in a reply.

**A shape serves a human reader.** A table costs about what its sentences cost,
and more than a flat list; what it buys is the reader's scan. Give one a human
reader and three or more parallel items — two facts are a sentence.

**Text a model reads is paid every session** — a router, a skill `description:`,
an always-loaded line. Keep it prose there, and a table only when the shape is
a lookup.

House style for a `mermaid` diagram: `flowchart TB`, labelled edges, `class`
for layers. A drawn figure takes its style from the diagram-design skill, not
from here.

## Placement — how the document is reached

A **context pointer** names out-of-context material and encodes the condition
for reaching it — a skill `description:`, a `CONTEXT.md` row, an `AGENTS.md`
line. The *wording* decides when the agent reaches the material, not the target.
A must-have target behind a weak pointer is a variance bug: sharpen the wording
before inlining the material.

Shape every pointer the same way: **front-load the leading word** (triggering
work happens where the agent reads first), **one trigger per branch**, **cut
identity the body already carries**. `memory/skills/TRIGGERS.md` and
`conventions/CONTEXT.md`'s "Load when" column are the models.

Context is **steps** (ordered actions) or **reference** (consulted on demand).
Rank it on a ladder by how immediately it is needed: **in-file step** >
**in-file reference** > **disclosed reference** (a separate file, loaded only
when its pointer fires).

**Progressive disclosure** is the move down that ladder: inline what every
branch needs, disclose what only some branches reach — branching is the test.
**Co-location** is the within-file companion: keep a concept's definition, rules
and caveats under one heading. That is not duplication (one meaning in two
places); it is the opposite of scattering *one* meaning across many.

Every document spends one of two budgets. **Context load** is paid by the agent
on every session — an always-loaded line, a skill description — whether or not
it fires; that is the price behind "every token of irrelevant context dilutes
attention". **Cognitive load** is paid by the human, who is the index; spend it
where judgement matters and remove it where it does not.

**When to split** — by sequence. Split a run of steps where the later steps
tempt the agent to rush the one in front of it; keeping them out of view drives
more legwork on the current task, and merging them back invites premature
completion. Split only when the cut earns it — it spends a budget above.

## Steps and completion criteria

Every step ends on a **completion criterion**, with two properties that make it
a lever:

- **Clarity** — can the agent tell done from not-done? A vague bound invites
  **premature completion**. Defend by sharpening the bound first, local and
  cheap; only hide later steps (across a real hand-off or subagent boundary) if
  the bound is irreducibly fuzzy *and* the rush is observed.
- **Demand** — how much the criterion requires. "Every modified model accounted
  for" forces thorough work where "produce a change list" does not. Not
  step-bound: "every rule applied" binds flat reference the same way "every
  step done" binds a sequence.

The strongest criteria are checkable and exhaustive both.

## Leading words

A **leading word** is a compact, pretrained concept the agent thinks with while
running the document — repeated as a token, never re-explained as a sentence,
so it anchors a whole region of behaviour in the fewest tokens. This repo
already runs on them: "displacement, not truncation" and "an index, not a
store" each retire what would otherwise be a restated paragraph. Coining a new
word costs its full definition every time; reach for an existing one.

**A defined term is not a figure of speech.** A leading word earns its place by
carrying a definition in the file that uses it; the meaning comes from the
definition, never from decoding the image. `collaboration.md` §Language bans the
second kind. The test: can a reader who has not imported the analogy understand
the sentence? If not, it is a metaphor, whatever its label.

**Negation** is the failure beside this lever: prohibition drags the forbidden
behaviour into context and makes it *more* available, not less — *don't think
of an elephant*, and the elephant is all there is. State the positive target
instead, and reserve a ban for a hard guardrail that cannot be phrased
positively, paired with the positive target even then.

## Sentences

Sentence mechanics — length, voice, term consistency, figures, cutting — follow
`collaboration.md` §Language, in documents as in chat. What follows sits above
them: the shape a rule or a claim takes in a document.

**Define by contrast.** The dominant sentence shape: `X, not Y` — name the
plausible wrong reading and close it.

> "Tier by replaceability, **not** size." · "an index, **not** a store" ·
> "Displacement, **not** truncation" · "Areas are **not** exclusive boxes"

**Measure, then claim.** Numbers precede assertions, and their provenance is
stated. A claim with no measurement is marked as such. Correcting an earlier
measurement is done plainly: *"The original check was wrong: `401` matched token counts."*

**Every rule carries its reason, inline.** Stated in the same breath, so the
rule survives being copied elsewhere.

> "Resitc repos live outside the PAZRAS tree: a repo inside its own backup set ingests itself and compounds every run."

**Name the failure the rule prevents.** Prefer a concrete failure mode to a principle: "a cutoff calibrated at 40 leaves guts the tree at 400".

**State limits rather than implying them.** Uncertainty is a section, not a hedge inside a sentence: **Honest limits** · **Accepted cost** · **Known risk, stated up front** · **Still open**. No "might" or "it seems" doing the work a labeled caveat should do.

**State the convention, do not teach it.** Assert what holds. Do not explain a
structure that is self-explanatory, and do not propose a practice nobody asked
for.

## Mechanics

**Point, do not restate.** If another file in this repo already says it, link
that file. A restatement is a second copy that drifts; topical overlap between
two files is the same defect one step earlier. This is the sentence-grain form
of *single source of truth* (§Pruning).

**Exact over abstract.** Exact paths, commands, byte counts and error strings.
Tables wherever there are more than two parallel items. Bold on the single
load-bearing clause of a paragraph, not scattered. Keep a code block under ~10
lines; a longer listing belongs in the file it describes, reached by a pointer.

**Preserve what is quoted.** Code, commands, identifiers, product names,
legal text and required quotations are kept byte-for-byte. Never simplify one
silently; when a rule cannot apply to it, say so.

**Emoji: a closed set encoding one dimension, or none.** Not a count rule. One
set, one meaning per glyph, never decorative, never in a heading, never two
variants of one symbol. Prefer the minimal: `✓` not `✅`; `✗` not `❌`.

**Person — third for the user, imperative for the agent.** These files enter
system prompts, where "I" conventionally denotes the assistant; a file titled
"how to work with me" therefore inverts on read.

- Facts about the user: **"the user"**, or the name. Never "I", "my", "me".
- Instructions to the agent: **imperative** — "Verify before asserting".
- Quoted samples keep their original person. Converting them destroys the
  evidence.

Root files naming the user carry the `USER-` prefix — `../user/user-identity.md`,
`../user/user-voice.md` — so a title cannot be misread as a goal set for the
agent.

**American English.** Apply from here on: `-ize`, `-or`, `-ction`. Earlier
files are mixed; leave them unless editing them for another reason.

## Pruning

- **Single source of truth.** A fact in two leaves means one is stale and
  nobody knows which.
- **The environment is a source of truth too** — `package.json`, config files,
  `--help` output. A document restating it is a **cache**: pay for it only when
  the lookup is genuinely expensive; leave one-command lookups to the
  environment, where they cannot go stale.
- **Relevance decays two ways** — a line that never bore on the task, or one
  that has gone stale as the world changed. Left unpruned, the default fate is
  **sediment** — stale layers nobody dares remove.
- **No-ops.** An instruction the model already obeys by default pays load to
  say nothing; the test is behaviour-versus-default, not reader taste, and is
  settled by running the document. Delete the whole sentence, not a trim.
  Grades leading words too: a word too weak to beat the default (*be
  thorough*) is a no-op — the fix is a stronger word, not a different technique.

## Never

- Decorative emoji in headings. Encoding sets stay.
- Invented examples, sample data, hypothetical users.
- Code blocks over ~10 lines.
- Second-person instruction — "you should…" — in a reference document.
- A claim with no source, no measurement and no stated limit.
- Restating what another file in the repo already says, instead of linking it.
- Closing summaries, sections that restate what the reader just read.

## Verification

**Fails if** a document written under this leaf mixes genres, opens with detail
before its overview, carries a fenced block longer than the prose around it, or
holds a step-shaped and a reference-shaped section on the same rung without a
completion criterion separating them. Also fails if an always-loaded pointer (a
`CONTEXT.md` row, a skill `description:`, a trigger term) restates identity the
target's own heading already carries, or omits the branch condition that should
select it.

**Checks** — the greppable form of the above:

```bash
cd ~/06_SYSTEM
git log --format='%s' | head -20                     # commit subject shape
grep -rc '```' --include='*.md' . | sort -t: -k2 -rn | head   # code-block load
grep -roE '§?(Honest limits|Accepted cost|Still open)' --include='*.md' . | wc -l
grep -c '' memory/skills/TRIGGERS.md                 # trigger count vs "0 ambiguous" claim
```
