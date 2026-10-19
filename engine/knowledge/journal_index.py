"""journal_index -- M4: a local embedding index over journal/ (memory domain
D4). See memory-architecture.md SS Governing rule and SS D4 over `journal/`,
and memory/knowledge/system/knowledge/journal-index.md for the full design.

GOVERNING RULE (memory-architecture.md): markdown is truth, every index is a
derived, disposable cache. This module never reads its own index as ground
truth for anything other than *ranking* candidate chunks -- the result of a
search is always a pointer (path + line range) back into `journal/`, never
a copy of its text presented as current.

WHY NOT knowledge/ OR skills/: those use exact lexical trigger matching
(skill-routing.md SS The trigger index) -- ~40-50 curated documents with a
hand-designed hierarchy beat embeddings there. journal/ is the one domain
that is unbounded, unindexable by hand, and where exact recall (not curated
routing) is the point.

WHY STDLIB ONLY: this runs from a systemd timer (familiar-journal-index.timer)
on whatever `python3` is first on that unit's PATH -- see frontmatter.py's
own note on the same constraint. No numpy, no `requests`: `urllib.request`
for the HTTP call to Ollama, plain lists for the vectors. The corpus is small
(a few hundred KB of journal markdown) so pure-Python cosine similarity is not
a real cost.

THE FACET (O5b). Every chunk carries the `branch` its session ran in, derived
from the entry's own `cwd:` (R1h) -- a pure function of frontmatter already on
disk, so no model and no second corpus. `search()` filters on it BEFORE the
cosine pass: a discrete subset first, vector similarity inside it, and `top`
counts within the subset. The facet is stored, never re-derived at query time
-- a search must answer from the index, not from the tree's current state.

THE SECOND FACET (C2): `touches:`, the subjects a session worked on, written
into the entry by stage 1 (`config/knowledge/facets.yaml`). This module only
READS it, and reads it verbatim: the index mirrors the record, and an
out-of-domain value is `ontology.facet_findings`' finding to report, in the
entry where it was written. Two facets, two sources, one rule -- what is not in
the record is not in the index.

WHY OLLAMA, NOT A DEDICATED EMBEDDING SERVICE: ollama-local.md already
documents this machine's local-inference story (no discrete GPU) and Ollama
is the standing local-model runtime. Adding a second local-model service to
embed a few
hundred KB of text would be a service this design deliberately avoids
(prior-art-memory-systems.md SS Why the recurring rejections: "needs a
running service, which this system deliberately does not have" -- Ollama is
the one exception already paid for elsewhere).
"""
from __future__ import annotations

import collections
import json
import math
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

from knowledge import frontmatter
from lib import invocation
from lib import roots

# The profile's `models.embed` (P1); the environment still wins.
DEFAULT_MODEL = os.environ.get("PAZRAS_EMBED_MODEL",
                               roots.PROFILE.models.get("embed") or "nomic-embed-text")
OLLAMA_URL = os.environ.get("PAZRAS_OLLAMA_URL", "http://127.0.0.1:11434")
INDEX_SUBDIR = "journal-index"
INDEX_FILE = "index.json"
H2_RE = re.compile(r"^## (.+)$")

# -- the branch facet (O5b, from R1h) -----------------------------------------
# Bumped when a CHUNK's shape changes, for the reason the model guard below
# exists and with a sharper edge: a chunk written before this key existed has no
# `branch`, and `c.get("branch") == "system"` over a missing key is False for
# every chunk -- a filter that used to work returns nothing, with no error and
# no traceback. Python treats a missing key as an ordinary absence, so the
# version stamp is what turns that silence into a rebuild. v2 added `branch` and
# `locator`; v3 added `touches`, on the same terms and with the same trap.
SCHEMA = 3

# The three branches are the register's ids, not ours (`config/knowledge/
# subjects.yaml`); the trees they mirror are the PARA ones. `ontology.BRANCHES`
# is the authority and `validate_branch` reads it; `test_journal_index` holds
# these three to it, so a rename in the register fails a test rather than
# quietly producing a fourth value nothing filters on.
SYSTEM, AREAS, PROJECTS = "system", "areas", "projects"
# Not a registered branch: the entries whose `cwd:` maps to nothing (R1h's 24
# ambiguous ones). Kept as a value rather than dropped, because "we could not
# tell" and "there is nothing here" are different answers.
UNKNOWN = "unknown"
BRANCH_VALUES = (SYSTEM, AREAS, PROJECTS, UNKNOWN)

HOME = pathlib.Path.home()
# The three directories that carry a branch, BY NAME, so the same function
# works against a test's `tmp_path` home and against this machine's. `system`
# is read from `roots` -- the install, not this checkout -- because an entry's
# `cwd:` names where the session ran, which is the installed path even when the
# code doing the reading is in a worktree. The PARA pair is the user's layout
# (`config/structure/pazras-master-config.sh`), declared once here.
SYSTEM_DIR = roots.INSTALL.name                   # 06_SYSTEM
PROJECTS_DIR = "01_PROJECTS"
AREAS_DIR = "02_AREAS"


# -- Ollama embedding client -------------------------------------------------
class EmbedError(RuntimeError):
    pass


def _post_json(path: str, body: dict, timeout: int = 120) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL.rstrip("/") + path, data=data,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise EmbedError(
            f"cannot reach Ollama at {OLLAMA_URL} ({exc}). "
            f"Is `ollama serve` running? See ollama-local.md.") from exc
    except TimeoutError as exc:
        raise EmbedError(f"Ollama request to {path} timed out after {timeout}s") from exc


def embed(texts: list[str], model: str = DEFAULT_MODEL) -> list[list[float]]:
    """Embed a batch of texts. Tries the current /api/embed first, falls
    back to the legacy /api/embeddings (one text at a time) for an older
    Ollama build."""
    if not texts:
        return []
    try:
        out = _post_json("/api/embed", {"model": model, "input": texts})
        vecs = out.get("embeddings")
        if vecs and len(vecs) == len(texts):
            return vecs
    except EmbedError:
        raise
    except Exception:
        pass                                   # fall through to legacy path
    vecs = []
    for t in texts:
        out = _post_json("/api/embeddings", {"model": model, "prompt": t})
        v = out.get("embedding")
        if v is None:
            raise EmbedError(
                f"Ollama returned neither 'embeddings' nor 'embedding' for "
                f"model {model!r}. Is it pulled? `ollama pull {model}`.")
        vecs.append(v)
    return vecs


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# -- the branch facet ---------------------------------------------------------
def branch_of_cwd(cwd, home=None) -> tuple[str, str]:
    """`(branch, locator)` for one entry's `cwd:`, or `(unknown, "")`.

    R1h, measured over the corpus: the directory a session ran in is already
    recorded, and it determines the branch without a model. `system` for
    anything under the install, `projects` and `areas` for the two PARA
    directories that carry a branch's name, and the project name or the Area
    letter as the `locator`.

    EVERYTHING ELSE IS `unknown`, never a guess. A bare `~`, a missing `cwd:`,
    a relative spelling, a path outside the home tree, and the worktree
    directory are all the same answer here, because the alternative is a
    heuristic that is right most of the time and silently wrong the rest -- and
    a wrong facet does not fail loudly, it returns the wrong subset.
    """
    base = pathlib.Path(home).expanduser() if home else HOME
    raw = str(cwd or "").strip()
    if not raw or raw in ("~", "~/"):
        return UNKNOWN, ""
    path = pathlib.Path(raw).expanduser()
    if not path.is_absolute():
        return UNKNOWN, ""
    # The three trees are named for the branch they carry, so they are built
    # from `home` rather than read from the module constants: `branch_of_cwd`
    # stays a pure function of its two arguments, which is what lets a test
    # exercise R1h's four classes in `tmp_path`.
    system = base / SYSTEM_DIR
    projects = base / PROJECTS_DIR
    areas = base / AREAS_DIR
    base_parts, parts = base.parts, path.parts
    if parts[:len(base_parts)] != base_parts:
        return UNKNOWN, ""
    rest = parts[len(base_parts):]
    if not rest:
        return UNKNOWN, ""                       # the home directory itself
    if path.is_relative_to(system):
        return SYSTEM, ""
    if path.is_relative_to(projects):
        return PROJECTS, rest[1] if len(rest) > 1 else ""
    if path.is_relative_to(areas):
        # `B_Tech` -> `B`: the register's Areas are the letters (A-P), and the
        # rest of the directory name is the Area's own title, not its id.
        return AREAS, rest[1].split("_")[0] if len(rest) > 1 else ""
    return UNKNOWN, ""


def _branch_order(counts) -> list[tuple[str, int]]:
    """`((branch, n), ...)` in a fixed order, so two runs cannot print the
    same distribution two ways. Anything unregistered sorts last, by name."""
    known = [(b, counts[b]) for b in BRANCH_VALUES if counts.get(b)]
    rest = sorted((b, n) for b, n in counts.items()
                  if n and b not in BRANCH_VALUES)
    return known + rest


def touches_of(raw) -> list[str]:
    """The `touches:` value as the ENTRY spells it: deduped, in order.

    Deliberately not checked against the register. The governing rule above
    says the index mirrors the record, and an out-of-domain subject is
    `ontology.facet_findings`' finding to make -- in the entry, where it was
    written. A second vocabulary rule in this module is exactly how the two
    would come to disagree, and the disagreement would be invisible.

    A single bare value is accepted because `touches: backup` and
    `touches: [backup]` are the same claim, and a hand-writer will type both.
    """
    if isinstance(raw, str):
        raw = [raw] if raw.strip() else []
    if not isinstance(raw, list):
        return []
    return [str(v).strip() for v in dict.fromkeys(raw) if str(v).strip()]


# -- chunking -----------------------------------------------------------------
def chunk_file(text: str) -> list[tuple[str, str, int, int]]:
    """Split on H2 (`## `) headers. Returns (header, chunk_text, start_line,
    end_line), 1-indexed inclusive. A preamble before the first H2 (title +
    any lead-in prose) becomes its own chunk when it holds real content. A
    file with no H2 at all is one chunk.

    Coarse on purpose: journal/CONTEXT.md rule 2 says "read a specific date,
    or grep for a term" -- this index exists to FIND the right entry and line
    range, not to answer questions from chunk text alone.
    """
    lines = text.split("\n")
    headers = [(i, m.group(1)) for i, l in enumerate(lines)
               for m in [H2_RE.match(l)] if m]
    if not headers:
        body = text.strip()
        return [("(whole file)", text, 1, len(lines))] if body else []

    chunks = []
    first_start, _ = headers[0]
    if first_start > 0:
        preamble = "\n".join(lines[:first_start]).strip()
        # More than just the H1 title line is worth its own chunk.
        if len(preamble.splitlines()) > 1:
            chunks.append(("(preamble)", "\n".join(lines[:first_start]), 1, first_start))

    for idx, (start, header) in enumerate(headers):
        end = headers[idx + 1][0] if idx + 1 < len(headers) else len(lines)
        chunks.append((header, "\n".join(lines[start:end]), start + 1, end))
    return chunks


# -- index build/load/save ----------------------------------------------------
def _index_path(base_dir: str) -> str:
    d = os.path.join(base_dir, INDEX_SUBDIR)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, INDEX_FILE)


def _empty(model: str = DEFAULT_MODEL) -> dict:
    """A fresh index. `schema` is stamped here so every write path carries it."""
    return {"schema": SCHEMA, "model": model, "built": None,
            "files": {}, "chunks": []}


def _load(base_dir: str) -> dict:
    p = _index_path(base_dir)
    if not os.path.isfile(p):
        return _empty()
    with open(p, "r") as fh:
        return json.load(fh)


def _save(base_dir: str, idx: dict) -> None:
    p = _index_path(base_dir)
    tmp = p + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(idx, fh)
    os.replace(tmp, p)                          # atomic


def _journal_files(agents_dir: str) -> list[str]:
    """journal/**/*.md except CONTEXT.md routers -- the same SKIP_NAMES
    reasoning tree.py applies to knowledge/skills, for the same reason: a
    router describes the layer, it is not content in it."""
    root = os.path.join(agents_dir, "journal")
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".md") and f != "CONTEXT.md":
                out.append(os.path.relpath(os.path.join(dirpath, f), agents_dir))
    return sorted(out)


def build(agents_dir: str, base_dir: str, model: str = DEFAULT_MODEL,
          force: bool = False, log=print) -> dict:
    """Incremental by default: only files whose mtime changed (or are new)
    are re-chunked and re-embedded; files no longer on disk drop their
    chunks. `force` rebuilds everything from scratch.

    Two mismatches rebuild everything, not just the changed files: a different
    embedding MODEL (whose vectors are not comparable with the stored ones) and
    a different SCHEMA (whose chunks lack a key the filter reads). Both are
    reported before the work starts, because the second one is invisible
    afterwards -- the chunks would look fine and the facet would be empty.
    """
    idx = _empty(model) if force else _load(base_dir)
    if idx.get("model") != model:
        log(f"embedding model changed ({idx.get('model')} -> {model}); forcing full rebuild")
        idx = _empty(model)
    elif idx.get("schema") != SCHEMA:
        log(f"index schema changed ({idx.get('schema')} -> {SCHEMA}); forcing full rebuild")
        idx = _empty(model)

    on_disk = set(_journal_files(agents_dir))
    known = set(idx["files"])

    removed = known - on_disk
    for rel in removed:
        idx["files"].pop(rel, None)
    if removed:
        idx["chunks"] = [c for c in idx["chunks"] if c["path"] not in removed]

    to_embed: list[dict] = []                   # chunk dicts, before embedding
    changed_paths = []
    for rel in sorted(on_disk):
        full = os.path.join(agents_dir, rel)
        try:
            mtime = os.path.getmtime(full)
        except OSError:
            continue
        prev = idx["files"].get(rel, {}).get("mtime")
        if prev == mtime:
            continue
        try:
            with open(full, "r", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            log(f"!! could not read {rel}: {exc}")
            continue
        idx["chunks"] = [c for c in idx["chunks"] if c["path"] != rel]
        # The facet comes from the file's own `cwd:`, parsed from the bytes we
        # just read -- a second read of the same file would be a second answer
        # waiting to disagree with the first.
        parsed = frontmatter.parse(text)
        branch, locator = branch_of_cwd(parsed.get("cwd"))
        touches = touches_of(parsed.get("touches"))
        pieces = chunk_file(text)
        for header, ctext, start, end in pieces:
            to_embed.append({"path": rel, "header": header, "start_line": start,
                             "end_line": end, "text": ctext,
                             "branch": branch, "locator": locator,
                             "touches": touches})
        idx["files"][rel] = {"mtime": mtime, "chunks": len(pieces),
                             "branch": branch, "locator": locator,
                             "touches": touches}
        changed_paths.append(rel)

    if to_embed:
        log(f"embedding {len(to_embed)} chunk(s) from {len(changed_paths)} changed file(s)...")
        vecs = embed([c["text"] for c in to_embed], model)
        for chunk, vec in zip(to_embed, vecs):
            idx["chunks"].append({**chunk, "embedding": vec})

    idx["built"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _save(base_dir, idx)
    chunks = collections.Counter(c.get("branch") or "(none)" for c in idx["chunks"])
    files = collections.Counter(f.get("branch") or "(none)"
                                for f in idx["files"].values())
    tagged = sum(1 for c in idx["chunks"] if c.get("touches"))
    log("  branch: " + " · ".join(f"{b} {n}" for b, n in _branch_order(chunks))
        + f"  ({files.get(UNKNOWN, 0)} file(s) unmapped)")
    log(f"  touches: {tagged} of {len(idx['chunks'])} chunk(s) carry one "
        f"({sum(1 for f in idx['files'].values() if f.get('touches'))} "
        f"file(s))")
    return {"files_changed": len(changed_paths), "files_removed": len(removed),
            "chunks_embedded": len(to_embed), "total_chunks": len(idx["chunks"]),
            "schema": SCHEMA, "branches": dict(chunks),
            "files_unmapped": files.get(UNKNOWN, 0), "touches_chunks": tagged}


def search(agents_dir: str, base_dir: str, query: str, top: int = 8,
           model: str | None = None, branch: str | None = None,
           touches: str | None = None) -> list[dict]:
    """The `top` best chunks, optionally inside one branch and/or one subject.

    THE FILTERS RUN BEFORE THE COSINE PASS, which is the whole point of a
    discrete facet: rank within the subset and take `top` from it. Ranking
    first and discarding the off-facet hits afterwards returns fewer than `top`
    and calls the shortfall a result. With both, the subset is the intersection.

    `None` or `""` means every chunk. A value nothing matches returns `[]`
    without embedding the query -- the caller explains that from `summary()`,
    because "no chunk in this facet" and "no index" need different answers.
    """
    idx = _load(base_dir)
    chunks = idx["chunks"]
    if branch:
        chunks = [c for c in chunks if c.get("branch") == branch]
    if touches:
        chunks = [c for c in chunks if touches in (c.get("touches") or ())]
    if not chunks:
        return []
    qmodel = model or idx.get("model", DEFAULT_MODEL)
    qvec = embed([query], qmodel)[0]
    scored = [(_cosine(qvec, c["embedding"]), c) for c in chunks]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [{"score": s, **{k: v for k, v in c.items() if k != "embedding"}}
            for s, c in scored[:top]]


def summary(base_dir: str) -> dict:
    """The live index's shape, for the two callers that have to EXPLAIN a
    result rather than produce one: a filtered search that found nothing, and
    O5c's comparison, which must quote one index. A chunk written before this
    schema shows up as `(none)` rather than as an absent branch, and
    `touches_chunks` is how a caller tells "this facet has no value for that yet"
    from "the query matched nothing".
    """
    idx = _load(base_dir)
    chunks = idx["chunks"]
    return {"schema": idx.get("schema"), "model": idx.get("model"),
            "built": idx.get("built"), "files": len(idx.get("files", {})),
            "chunks": len(chunks),
            "touches_chunks": sum(1 for c in chunks if c.get("touches")),
            "branches": dict(collections.Counter(c.get("branch") or "(none)"
                                                 for c in chunks))}


def validate_branch(value: str) -> str:
    """A `--branch=` value, held against the register.

    A typo that selects nothing looks EXACTLY like a query with no hits, which
    is the class of failure `invocation` was written to refuse one layer up.
    Imported lazily because the register is a query-path dependency, not a
    build one -- `build()` reads `cwd:`, `touches:` and two constant tables, and
    the systemd unit should not pay for a YAML parse it does not use.

    `unknown` is accepted: it is a real facet value (R1h's ambiguous entries),
    not a registered branch, and asking for it is how a caller inspects them.
    """
    from knowledge import ontology
    allowed = tuple(ontology.BRANCHES) + (UNKNOWN,)
    if value not in allowed:
        raise invocation.UsageError(
            f"--branch={value} is not a branch (branch values: {', '.join(allowed)})")
    return value


def validate_touches(value: str) -> str:
    """A `--touches=` value, held against the same register the entries use."""
    from knowledge import ontology
    if value not in ontology.SUBJECTS:
        raise invocation.UsageError(
            f"--touches={value} is not a subject (subjects: "
            f"{', '.join(ontology.SUBJECTS)})")
    return value


def _no_hits(base_dir: str, branch: str | None, touches: str | None) -> str:
    """What to print when a search returned nothing, saying WHICH nothing."""
    s = summary(base_dir)
    if not s["chunks"]:
        return "no index yet -- run `familiar knowledge journal index` first"
    if touches and not s["touches_chunks"]:
        return (f"no chunk carries `touches:` at all yet ({s['chunks']} chunk(s) "
                f"indexed) -- stage 1 writes it, so it fills forward from the "
                f"first entry distilled after C2")
    shape = " · ".join(f"{b} {n}" for b, n in _branch_order(s["branches"]))
    if branch or touches:
        which = " and ".join(x for x in (f"--branch={branch}" if branch else "",
                                         f"--touches={touches}" if touches else "") if x)
        return (f"no chunk matches {which}; the index holds "
                f"{s['chunks']} chunk(s): {shape}")
    return f"no hits in {s['chunks']} chunk(s): {shape}"


# -- CLI ----------------------------------------------------------------------
SPEC_INDEX = invocation.Spec(name="journal index",
                             usage="journal index [--force] [--model=NAME]",
                             flags=("--force",), options=("--model",))
SPEC_SEARCH = invocation.Spec(name="journal search",
                              usage=("journal search '<query>' [--top=N] "
                                     "[--branch=BRANCH] [--touches=SUBJECT]"),
                              options=("--top", "--branch", "--touches"),
                              positional="the query")


def main(argv, base_dir, agents_dir) -> int:
    """A router, not a leaf: it picks the sub-command, then parses with that
    sub-command's own spec (`invocation.parse` is still the one parser)."""
    sub = argv[0] if argv else ""
    rest = argv[1:]

    if sub == "index":
        inv = invocation.parse(rest, SPEC_INDEX, base_dir, agents_dir)
        if inv.help:
            # `invocation.parse` accepts `--help` for every spec, so a verb that
            # ignores it answers a question with minutes of Ollama -- the trap
            # this module's own handoff names.
            print(f"usage: familiar knowledge {SPEC_INDEX.usage}")
            return 0
        force = inv.has("--force")
        model = inv.get("--model") or DEFAULT_MODEL
        try:
            stats = build(agents_dir, base_dir, model=model, force=force)
        except EmbedError as exc:
            sys.stderr.write(f"[familiar knowledge journal index] {exc}\n")
            return 2
        print(f"journal index: {stats['chunks_embedded']} chunk(s) embedded "
              f"({stats['files_changed']} file(s) changed, "
              f"{stats['files_removed']} removed), "
              f"{stats['total_chunks']} chunk(s) total")
        return 0

    if sub == "search":
        inv = invocation.parse(rest, SPEC_SEARCH, base_dir, agents_dir)
        if inv.help or not inv.rest:
            stream = sys.stdout if inv.help else sys.stderr
            stream.write(f"usage: familiar knowledge {SPEC_SEARCH.usage}\n")
            return 0 if inv.help else 1
        query = inv.rest[0]
        top = inv.integer("--top", 8)
        branch = inv.get("--branch")
        touches = inv.get("--touches")
        try:
            branch = validate_branch(branch) if branch else None
            touches = validate_touches(touches) if touches else None
            hits = search(agents_dir, base_dir, query, top=top, branch=branch,
                          touches=touches)
        except invocation.UsageError as exc:
            sys.stderr.write(f"[familiar knowledge journal search] {exc}\n")
            return 1
        except EmbedError as exc:
            sys.stderr.write(f"[familiar knowledge journal search] {exc}\n")
            return 2
        if not hits:
            print(_no_hits(base_dir, branch, touches))
            return 1
        for h in hits:
            snippet = " ".join(h["text"].split())[:160]
            facet = h.get("branch") or "(none)"
            if h.get("locator"):
                facet += f"/{h['locator']}"
            print(f"{h['score']:.3f}  {h['path']}:{h['start_line']}-{h['end_line']}  "
                  f"{h['header']}   [{facet}]")
            print(f"       {snippet}")
        return 0

    usage = ("usage: familiar knowledge journal <index|search> ...\n"
             "  journal index [--force] [--model=NAME]   (re)build the embedding index\n"
             "  journal search '<query>' [--top=N] [--branch=BRANCH]"
             " [--touches=SUBJECT]   search it\n")
    stream = sys.stdout if sub in ("-h", "--help") else sys.stderr
    stream.write(usage)
    return 0 if sub in ("-h", "--help") else 1
