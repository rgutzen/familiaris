---
title: Journal index — M4 retrieval
summary: The journal's shape, the M4 embedding index over it, and its two facets
origin: authored
authority: agent
trust: trial
last_verified: 2026-10-25
verified_log: [2026-10-25, 2026-10-09, 2026-09-01]
use_count: 11
last_used: 2026-10-15
promoted_from: []           # built 2026-09-01, ROADMAP.md M4
source:
supersedes:
related: [memory-architecture, ollama-local, skill-routing, prior-art-memory-systems, consolidation-cycle, scheduled-processes, knowledge-index, mcp-servers, memory-poisoning-posture]
tags: [journal, embeddings, retrieval, m4, ollama]
scope: ["06_SYSTEM/memory/journal/**"]
area: [B]
stability: evolving
---

# Journal index — M4 retrieval

The local embedding index over `journal/` that `memory-architecture.md` §D4
names but leaves unbuilt through M0–M3: memory domain D4, writer = machine,
decay = disposable, rebuildable from markdown. This is what makes exact recall
over an unbounded, hand-unindexable journal practical without bulk-loading it
(`journal/CONTEXT.md` rule 2: "never bulk-load — read a specific date, or grep
for a term"). A search result is a pointer (path + line range) back into the
journal, never a copy of its text — the governing rule
(`memory-architecture.md`: "markdown is truth, every index is a derived,
disposable cache") applies here exactly as it does to the skill routers.

## Why embeddings here and nowhere else in D3

[[skill-routing]] and `knowledge-vs-skills.md` settle this for `knowledge/`
and `skills/`: ~40–50 curated documents with declared `triggers:` — exact
lexical matching wins, no model needed. `journal/` is the opposite shape:
unbounded, one entry per session, no curated vocabulary. That is the D4 case
ROADMAP.md's M4 entry describes, and [[prior-art-memory-systems]] §4 records
the fallback if embeddings ever prove too slow on this CPU-only machine:
locality-sensitive hashing over sparse lexical features (Dasgupta et al.,
*Science* 2017) — noted, not adopted, because plain lexical search is simpler
at today's journal scale (17 entries, 168 KB, 2026-09-01) and CPU embeddings
have not yet been shown to be too slow.

## Mechanism

`engine/knowledge/journal_index.py`, wired as
`familiar knowledge journal index` / `familiar knowledge journal search`.

- **Embeds via Ollama** ([[ollama-local]] — the standing local-model runtime
  this machine already runs; no discrete GPU, so a small embedding model on
  CPU, not a generative reranker — ROADMAP.md M4 is explicit: "embeddings
  only, no generative reranker"). Default model
  `nomic-embed-text` (override: `PAZRAS_EMBED_MODEL`); default endpoint
  `http://127.0.0.1:11434` (override: `PAZRAS_OLLAMA_URL`). Pulled, verified
  with `ollama list` on 2026-10-25.
- **Chunks by H2 (`## `) header**, one chunk per section, plus a preamble
  chunk when real content precedes the first header. Coarse on purpose — this
  finds the right entry and line range, not a sub-paragraph fact; the point is
  "which entry talks about X", not "what exactly did it say" (read the file
  for that, per journal rule 2).
- **Incremental.** The index (`~/.local/share/pazras/journal-index/index.json`
  — outside git, like every other `PAZRAS_DATA_DIR` cache) stores each source
  file's mtime; a rebuild only re-chunks and re-embeds files whose mtime
  changed, and drops chunks for files removed from disk. `--force` rebuilds
  everything (also triggered automatically if the embedding model or the
  schema changes). The build log says what "changed" means: `474 changed
  file(s) (471 new, 3 modified)`. A model or schema rebuild announces itself
  with `forcing full rebuild` on the line before.
- **Small batches, saved as it goes** (`BATCH_CHUNKS` 32, `BATCH_CHARS`
  100,000, a save at least every 60 s). A file is recorded as indexed, with
  its mtime, only once every chunk of it is embedded; a run that dies keeps the
  files it finished and the next run starts at the one in flight.
- **Chunks are capped at 8,000 chars** (`MAX_CHUNK_CHARS`), stored and sent.
  `nomic-embed-text` reads 2,048 tokens and Ollama truncates the rest silently,
  so 8,000 chars — ~2,000 tokens of English — is about what the model takes
  anyway. A chunk longer than that keeps its opening and loses its tail: the
  measured price of keeping a 1 MB section out of the request body. A hit's
  `start_line`–`end_line` still span the whole section. Chunks written before
  the cap keep their full text until a `--force` run — 64 of them, 2.3 MB, on
  2026-10-25 — and their vectors are unchanged, so that rebuild is only worth
  it when the stale text is in the way.
- **Pure-Python cosine similarity**, no numpy — stdlib only, same constraint
  `frontmatter.py` states for the same reason: a systemd-timer script must not
  depend on an import that can go missing from whatever `python3` is first on
  that unit's `PATH`.
- **Scope:** `journal/**/*.md` except `CONTEXT.md` routers — includes
  `journal/reports/*.md` (the nightly-pass reports are dated journal content
  too), excludes only the layer-describing router file, mirroring
  `~/06_SYSTEM/engine/knowledge/tree.py`'s `SKIP_NAMES` reasoning for `knowledge/`/`skills/`.

## The facets (O5b, C2)

Two discrete facets, filtered BEFORE the cosine pass so `top` counts inside the
subset, each stored on the chunk and never re-derived at query time — a search
answers from the index, not from the tree's current state.

**`branch`, from each entry's own `cwd:`** (R1h) — a pure function of
frontmatter, no model. `system` for anything under the install, `projects` and
`areas` for the two PARA directories that carry a branch's name, plus the
project name or the Area letter as a `locator` beside it. Everything else — a
bare `~`, a missing `cwd:`, a worktree, `/tmp` — is `unknown`, and is never
guessed: a facet that is wrong does not fail loudly, it returns the wrong
subset.

**`touches`, from each entry's own frontmatter, written by stage 1.** After
distilling a transcript, stage 1 reads the files its tool calls named
(`pointers.touched_paths` in `engine/context/pointers.py`), maps them through
each subject's `places:` (`ontology.subject_at` in `engine/knowledge/ontology.py`)
and writes the result into the entry. The index only
READS it, verbatim: an out-of-domain value is `ontology.facet_findings`'
finding to make, in the entry where it was written, and a second vocabulary
rule here is how the two would come to disagree.

`journal search '<query>' --branch=BRANCH [--touches=SUBJECT]` takes either or
both; a value outside `system|areas|projects|unknown` or outside the thirteen
subjects is a usage error, not an empty page, and the MCP tool takes the same
arguments.

### What each one measures, 2026-10-09

Over 271 entries and 38 reports (1,514 chunks): **system 793 · areas 96 ·
projects 268 · unknown 357**. The entries split 245 mapped to 26 `unknown`;
the reports carry no `cwd:` at all, so every report chunk lands in `unknown`
too.

**`touches` is 0 of 1,514 chunks, and that is the design rather than a
failure.** The field is written at distill time, so it fills forward from the
first entry distilled after C2 — the newest entry predates the field, and the
sessions that would carry it are still staged. Two consequences worth stating:
a `--touches=` search says *"no chunk carries `touches:` at all yet"* rather
than "no hits", and the historical corpus is **not** backfilled. It could be —
a git rename table recovers 116 of the 271 entries — but the journal is
append-only and rule 1 forbids rewriting an entry, and a machine-derived field
added afterwards is still a rewrite. The facet fills forward; the entries stay
the record of what was known when they were written.

**Coverage of the writer, measured over the 314 staged transcripts:** 130 name
a file in this system, 8 map to subjects (the ones from 2026-10-07 onward,
which spell paths in the current layout), and a session that has any names
between one and eight subjects. Two harnesses yield nothing at all —
`opencode_extract` and `hermes_extract` keep the tool NAME and drop the
arguments at staging — so "named no path" and "was never recorded" are
indistinguishable from the entry, which is why stage 1 reports the count.

The facet is stamped with a `SCHEMA` version on the index. A chunk written
before a key existed has no value for it, and a filter over a missing key
returns ZERO hits with no error — so a schema mismatch forces a full rebuild
exactly as a changed embedding model does. That is the one trap here, and the
version stamp is what turns its silence into a rebuild.

### Does the branch facet pay? Measured, it does not (O5c)

Eleven questions from real sessions, pre-registered in `d66d27e` before any
search, with the asker's own branch and an answer key of acceptable sources.
The metric is correct answers per 1,000 reader tokens down to the first correct
source; a miss costs all 8 results. The bar was ≥ 1.10 × baseline with at most
one question lost.

| run | corpus | baseline | strict (`--branch`) | tolerant (branch ∪ `unknown`) |
|---|---|---|---|---|
| 1–2, 2026-10-12 | 301 entries, `6ff053c0d2520973` | 1.346 | 1.030 (0.765 ×, lost q11) | 1.415 (1.051 ×) |
| 3, 2026-10-13 | 330 entries, `00eb240cf75b8a30` | 1.228 | 0.936 (0.762 ×, lost q11) | 1.259 (1.025 ×) |

**Neither arm meets the bar.** In 8 of 11 questions the facet changes nothing:
a query that names its topic already lands in that topic's branch. The strict
loss is q11, whose 16 sources all started at `~` and are therefore `unknown`.
So `--branch=` stays as an affordance, and the claim that *the branch is the
facet* has no evidence at this size; re-measure at about twice the corpus.
`touches` was not compared, because too few entries carried it.

*How a miss is read (user, 2026-10-12):* a miss is evidence about where the
structure files things, not a reason to loosen the ontology. Runner, answer
key and runs: `../consolidation/_data/o5c-*`; `python3 o5c-retrieval.py
--report` prints every run.

## Retrieval as a real tool (L1)

`journal_search` is exposed to all four harnesses as one MCP tool
(`pazras-memory-mcp`), alongside a boundary-checked `grep`. Mechanism, boundary
enforcement and per-harness wiring: [[mcp-servers]]. This module's
`search()` function is unchanged by that — the server is a thin wrapper.

## Failure handling

`_post_json` separates three outcomes, because the remedies differ:

| Class | Cause | Message starts | Index build |
|---|---|---|---|
| `OllamaUnreachable` | no HTTP answer: refused, DNS, timeout, a socket closed unanswered | `cannot reach Ollama ... Is ollama serve running?` | stops, progress saved |
| `OllamaHTTPError`, status in {400, 413, 422, 500} | the server refused this request | `Ollama at … answered /api/embed with HTTP 400 Bad Request: <body>` | the batch is halved until the chunk is alone; that chunk is skipped and logged (`!! skipped path:lines`) |
| `OllamaHTTPError`, any other status (404 model not pulled, 401, 503) | the server, not the request | same, with the body | stops, progress saved |

Five chunks skipped in a row stop the run: that is a refusing server, not bad
chunks. A file with a skipped chunk is left unrecorded, so the next run retries
it; the run still exits 0 and the `!!` lines are in the unit's journal
(`journalctl --user -u familiar-journal-index`). Exit code 2 is only for a stop.

**The 2026-10-24 incident.** The unit failed on 10-24 and 10-25 with "cannot
reach Ollama (HTTP Error 400)". Both statements were wrong:

- *The index was not invalidated.* 388 of its 391 recorded mtimes still matched
  the live journal. The 474 "changed" files were 471 new entries and 3 edits:
  commit `4457f8d` (nightly consolidation 2026-10-23, stage 1 replay) added 470
  entries to `journal/2026/10/` at once, 391 → 862 files. A backlog that size
  is a real 2,281-chunk build, not a cache miss.
- *Ollama was reachable.* One `/api/embed` request carrying 2,281 chunks
  (4.7 MB) ran 85 s and returned HTTP 400, body `Post
  "http://127.0.0.1:…/tokenize": … connection reset by peer`. Two chunks of
  1.1 MB each (the `Warnings` section of `reports/2026-10-23_consolidation{,.full}.md`)
  caused it: each embeds alone in 0.5 s, and the same 2,281 chunks capped at
  8,000 chars each pass in 84 s. The old code raised `HTTPError`, a subclass
  of `URLError`, as "cannot reach", and saved only after the whole batch, so
  each day began again at zero.

**Run it from the install.** The index keys files by path inside `memory/` and
compares mtimes. A git checkout sets every mtime to the checkout time, so
indexing a worktree's `memory/` against the live index re-embeds every file. To
test a change, point the worktree's code at the install's journal and a copy of
the index: `PAZRAS_MEMORY_DIR=~/06_SYSTEM/memory PAZRAS_DATA_DIR=/tmp/x
./engine/familiar knowledge journal index`. Measured on 2026-10-25: on a copy,
2,281 chunks in 3 min 24 s with three checkpoint saves; then the live unit,
2,281 chunks from 474 changed files in **92 s**, no chunk skipped,
`Result=success`, 4,200 chunks total, and the run 15 s later embedding 0. So
the daily timer is incremental again, and the copy run's 3 min 24 s was the
pessimistic number (a cold `/tmp` copy, not the install's own page cache). The
data root keeps the name `pazras` because it is the state of
one PAZRAS tree; the naming decision (`24e792a`, ratified 2026-10-13) renames
the software to Familiaris and leaves paths and `PAZRAS_*` variable names
alone.

## Scheduling

`familiar-journal-index.timer`, daily, incremental — see
[[scheduled-processes]]. Deliberately its **own** unit, not folded into the
nightly consolidation pass ([[consolidation-cycle]]'s 9 stages are D3-only:
git-committing, tree-scoring machinery that does not fit a disposable,
non-git-tracked D4 cache with a different writer/decay model — see
`memory-architecture.md`'s four-domain table).

## Verification

```bash
ollama list | grep nomic-embed-text                 # model pulled?
~/06_SYSTEM/engine/familiar knowledge journal index
~/06_SYSTEM/engine/familiar knowledge journal search "some phrase from a real entry"
cat ~/.local/share/pazras/journal-index/index.json | python3 -c \
  'import json,sys; d=json.load(sys.stdin); print(len(d["chunks"]), "chunks,", len(d["files"]), "files")'
```

Primary decay signal is **disuse of the mechanism itself**, not staleness of
any one chunk — the index rebuilds from markdown on every run, so a stale
chunk cannot outlive the next `journal index`. If `use_count` stays at 0 for
weeks, that says search is not being reached for, not that the index is wrong.
