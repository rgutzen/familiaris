# Add a harness

A harness is a program that reads this tree: Claude Code, `pi`, `hermes`,
`opencode`. Adding one is an entry point rather than a migration, because
everything the system knows lives in files a harness reads. It is still a code
change, and this page is mostly the list of files — the surfaces are yielded from
code, so a fifth harness cannot be a configuration edit.

Read the whole page before starting: three of the six steps are separate
mechanisms, and only the first can be checked without the harness installed.

## 1 · The always-on payload — `engine/context/l1.py`

This is the file the task turns on. `targets()` yields `(label, path, desired
text, spliced)` for every harness surface, and each surface has a path constant
above it:

```console
$ grep -n "CLAUDE_ENTRY = \|OPENCODE_CONFIG = \|PI_AGENTS = \|PI_SYSTEM = \|^def targets" engine/context/l1.py
65:CLAUDE_ENTRY = Path.home() / ".claude" / "CLAUDE.md"
66:OPENCODE_CONFIG = Path.home() / ".config" / "opencode" / "opencode.json"
71:PI_AGENTS = Path.home() / ".pi" / "agent" / "AGENTS.md"
78:PI_SYSTEM = Path.home() / ".pi" / "agent" / "SYSTEM.md"
183:def targets(agents: Path):
```

A new harness is one constant beside those and one `yield` in `targets()`. Both
halves were executed against a scratch copy of this tree — the patch adds
`.stub/AGENTS.md`, and the compiler picks it up like any other surface:

```console
$ python3 engine/familiar context l1 --check

4 target(s) stale. Run: familiar context l1
  STALE  claude     /tmp/guise/home/.claude/CLAUDE.md
  STALE  opencode   /tmp/guise/home/.config/opencode/opencode.json
  STALE  pi-system  /tmp/guise/home/.pi/agent/SYSTEM.md
  STALE  stub       /tmp/guise/home/.stub/AGENTS.md
  skip   hermes    no harness surface for always-on (sanitizer blocks it)
```

`hermes` is skipped, not forgotten: its memory store runs a threat scan over
`MEMORY.md` and replaces entries that match, so a generated block never reaches
its prompt. That is a fix in hermes' own assembly path and not in this compiler —
the reason is in `l1.py`'s docstring, and a harness with the same behaviour is a
skip here too.

Two properties of this compiler to keep: a surface is written only when the
harness's config *directory* exists, so a harness nobody installed is reported
`absent` rather than invented, and the block is spliced between markers rather
than appended, so running it twice rewrites the same bytes.

## 2 · The audit — `engine/context/harnesses.py`

`familiar context harness` drives every harness once against a stub recorder and
reports what each one actually sent. A new harness joins that roster, and needs a
driver that speaks its own conventions:

```console
$ grep -n "^ALL\|^ADAPTERS" -A 1 engine/context/harnesses.py
66:ALL = ("claude", "opencode", "codex", "pi", "hermes")
67-
--
411:ADAPTERS = {"claude": run_claude, "opencode": run_opencode,
412:            "codex": run_codex, "pi": run_pi, "hermes": run_hermes}
```

The drivers differ because the harnesses do: one is run headless with a flag,
another reads a base URL from its own config and needs that directory copied
rather than symlinked, a third reports its prompt size as a number rather than
sending anything. This step was **not executed**, and cannot be: it needs the
program, and no such program exists on this machine for a fifth harness.

## 3 · Enforcement — `engine/boundaries/guard.py`, or the advisory

A harness that can refuse a tool call gets boundaries enforced: `guard.py` reads
`config/boundaries/boundaries.json`, judges the payload, and answers in the
asking harness's dialect. A harness without such a surface gets the advisory
instead — `engine/boundaries/compile.py` yields one target per harness surface,
which is where the hermes memory block comes from.

Both are code, and both are in the same file you edit in step 1's neighbourhood.
What has to hold either way: the rules live in `config/boundaries/`, and the new
surface states them or enforces them, never re-invents them.

## 4 · Capture — `engine/context/capture.py` and an extractor

A harness that should feed the journal needs two things: a hook that calls
`familiar context capture --harness=<name> --event=<event>`, and an extractor
that turns that harness's transcript into the session record the consolidation
pass reads. `hermes_extract.py` and `opencode_extract.py` are the two shipped
examples, and they differ exactly as much as the transcript formats do — one
keeps a tool's name and drops its arguments, which the replay stage then has to
tolerate.

## 5 · Say what it is — a leaf, and the count

`memory/knowledge/system/harness/` holds one leaf per harness: its hooks, its
skills mechanism, its settings, its traps. `docs/explanation/lore/harness.md`
names the set, and `familiar context harness` is what keeps the claims honest —
a leaf that has not been measured is a description of a program rather than a
fact about one.

## 6 · Verify

```console
$ python3 engine/familiar context l1 --check     # the payload, for every surface
$ python3 engine/familiar context harness        # each harness, driven once
$ python3 engine/checks/checks.py --run pre-commit
```

The first of these was run on the patched scratch tree: the new surface is
reported and then written. The gate runs 25 checks on this tree and was green
here; it was not run against a fifth harness, because there is no fifth harness
to run it against.

## What this is not

**Not a configuration change.** The surfaces are Python tuples in `l1.py` and
`harnesses.py`; there is no list of harnesses in `config/` to extend. A harness
is code because the differences between harnesses are code — a base-URL override
here, a copied config directory there.

**The roster's fifth name is audited, not wired.** `ALL` and `ADAPTERS` carry
`codex`, because `familiar context harness` measures it, and its leaf records
exactly that: no always-on surface, no boundary hook, no capture
(`memory/knowledge/system/harness/codex.md`). Being in the audit roster is a
weaker claim than being an entry point, and the two lists are allowed to
disagree — this page is about the second one.

## Read next

- [the Guises](../explanation/lore/harness.md) — why the harness is replaceable
  and the tree is not
- `engine/context/l1.py` — the compiler, including why hermes is skipped
- `memory/knowledge/system/harness/mcp-servers.md` — the retrieval wiring every
  harness shares, and the one that is per harness
