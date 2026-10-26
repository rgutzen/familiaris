"""eval -- option 0's evaluation set: fourteen tasks, each with a verifier that judges.

WHY A SET AND NOT A BENCHMARK. Decision 1 adopts a strategy only where the
evidence shows it works *on this workload*, so the tasks are this repository's
own history (`dev/orchestration/PLAN.md` §Option 0): SWE-bench's construction
applied at home -- a real task, a known good end state, and a command that
judges. A verifier that cannot tell the end state from the start state judges
nothing, so 4a's exit is that every verifier FAILS on the base alone and
PASSES on the base with the task's change applied. `--validate` is that test.

THE TASKS ARE CONTENT. Each is a directory under `dev/orchestration/tasks/`
holding `task.yaml` (read by `_miniyaml`, every value a string), `prompt.md`
(exactly what the agent under test receives) and its key files. What a task
must declare, which kinds and arms exist, which arms a kind runs and how many
tasks of each kind the set holds are in `tasks/tasks.yaml`, not here: a field
or an arm added there is required here without a code change.

THE KEY NEVER ENTERS THE WORK TREE. A verifier runs from the work tree's root
with `$TASK_DIR` pointing back at the task directory, which is where the key
and any scorer live. `--validate` also refuses a task whose base already
contains the task directory, because from then on the answer ships with the
question.

WHAT "THE CHANGE" IS. A coding task's change is the reference commit's diff on
top of its base (`git diff <base> <reference>`; several references, comma
separated, are applied one commit diff at a time, which skips commits that
landed between them). Any other task's change is its key copied in as the
answer file the prompt names. Applied with `git apply` to a `git archive`
extraction, never a worktree: a worktree keeps the later commits reachable
through `git log --all` (4b).

`isolate` (4b) BUILDS THE START STATE. It is the archive
extracted into a fresh repository with the base as its one commit, or an empty
repository for a task declared `tree: empty` (a batch task whose base tree
carries its own answer key: the folder a leaf sits in is its subject, and a
journal entry's frontmatter holds its tags). Nothing of the source repository is
copied, so the future is not in the tree; symlinks leaving the tree are deleted.
`materialise` is `isolate` plus the change, for `--validate`.

`--run` (4c) IS THE RUNNER: it builds each cell's isolated tree, runs that
arm's process in it, judges it with the task's verifier, and appends one JSON
object per line to `~/.local/share/pazras/orchestration-eval.jsonl`. The arms,
the row, and where each number comes from are below, at the section that builds
them; `--dry-run` prints every cell's command line, model, tree and estimated
cost and spawns nothing, which is the item's own exit.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import fnmatch
import hashlib
import json
import os
import pathlib
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid

from harness import jev
from harness import pi_call
from lib import _miniyaml, roots
from orchestration import dispatch, jevlog, models, profiles, selection as selection_mod, specs, waves

TASKS = roots.DEV / "orchestration" / "tasks"
SET = "tasks.yaml"
_SHA = re.compile(r"^[0-9a-f]{40}$")
VERIFY_TIMEOUT = 900                    # seconds; the slowest verify runs a test suite


class TaskError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class Task:
    id: str
    kind: str
    title: str
    base: str
    reference: tuple                     # coding: commit shas; else: one key file name
    scope: tuple
    verify: str
    arms: tuple
    dir: pathlib.Path
    answer: str = ""                     # non-coding: the file the agent writes
    tree: str = "base"                   # base | empty
    task_class: str = "unknown"          # the Loom's class for this kind (selection.yaml)

    def key_paths(self) -> list:
        return [] if self.kind == "coding" else [self.dir / r for r in self.reference]


def _split(value: str) -> tuple:
    return tuple(v.strip() for v in value.split(",") if v.strip())


def load_set(root: pathlib.Path = TASKS) -> dict:
    data = _miniyaml.load((root / SET).read_text(encoding="utf-8"))
    for key in ("fields", "kinds", "arms"):
        if not data.get(key):
            raise TaskError(f"{root / SET}: `{key}:` is missing or empty")
    return data


def load_task(d: pathlib.Path, spec: dict) -> Task:
    """One task directory, checked against the set's declaration."""
    path = d / "task.yaml"
    try:
        raw = _miniyaml.load(path.read_text(encoding="utf-8"))
    except (OSError, _miniyaml.YamlError) as e:
        raise TaskError(f"{path}: {e}") from None
    missing = [f for f in spec["fields"] if not (raw.get(f) or "").strip()]
    kinds = spec["kinds"]
    kind = (raw.get("kind") or "").strip()
    if kind and kind in kinds:
        missing += [f for f in (kinds[kind] or {}).get("fields") or []
                    if not (raw.get(f) or "").strip()]
    if missing:
        raise TaskError(f"{path}: missing field(s): {', '.join(missing)}")
    if kind not in kinds:
        raise TaskError(f"{path}: kind {kind!r}; known: {', '.join(kinds)}")
    if raw["id"] != d.name:
        raise TaskError(f"{path}: id {raw['id']!r} is not its directory's name {d.name!r}")
    base = raw["base"].strip()
    refs = _split(raw["reference"])
    for sha in (base,) + (refs if kind == "coding" else ()):
        if not _SHA.match(sha):
            raise TaskError(f"{path}: {sha!r} is not a full commit sha")
    arms = _split(raw["arms"])
    allowed = set(_split((kinds[kind] or {}).get("arms") or ""))
    unknown = [a for a in arms if a not in spec["arms"]]
    if unknown:
        raise TaskError(f"{path}: unknown arm(s) {', '.join(unknown)}")
    if set(arms) != allowed:
        raise TaskError(f"{path}: arms {', '.join(arms)}; a {kind} task runs "
                        f"{', '.join(sorted(allowed))}")
    tree = (raw.get("tree") or "base").strip()
    if tree not in ("base", "empty"):
        raise TaskError(f"{path}: tree {tree!r}; base or empty")
    if not (d / "prompt.md").is_file():
        raise TaskError(f"{d}: no prompt.md")
    return Task(id=raw["id"], kind=kind, title=raw["title"], base=base,
                reference=refs, scope=_split(raw["scope"]), verify=raw["verify"].strip(),
                arms=arms, dir=d, answer=(raw.get("answer") or "").strip(), tree=tree,
                task_class=((kinds[kind] or {}).get("class") or "unknown").strip())


def load(root: pathlib.Path = TASKS) -> list:
    """Every task under `root`, in id order. A malformed one raises: a set
    that skips a broken task reports a smaller set as complete.

    A directory holding `questions.yaml` is a CALIBRATION task (12c): it is run by
    `--calibrate` on one model id at a time, not as a cell of the set, so it is
    skipped here by the file it holds rather than by its name -- the file is what
    makes it one, and a missing `task.yaml` under any other name is still a
    failure.
    """
    spec = load_set(root)
    return [load_task(d, spec) for d in sorted(root.iterdir())
            if d.is_dir() and not d.name.startswith("_")
            and not (d / "questions.yaml").is_file()]


def composition(tasks: list, spec: dict) -> list:
    """What differs from the declared number of tasks per kind."""
    out = []
    for kind, decl in spec["kinds"].items():
        want = int((decl or {}).get("count") or 0)
        have = sum(t.kind == kind for t in tasks)
        if want != have:
            out.append(f"{kind}: {have} task(s), the set declares {want}")
    return out


# --- git ---------------------------------------------------------------------

def _git(*args, repo: pathlib.Path = roots.REPO, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(("git", "-C", str(repo)) + args, capture_output=True, **kw)


def has_commit(sha: str, repo: pathlib.Path = roots.REPO) -> bool:
    return _git("cat-file", "-e", f"{sha}^{{commit}}", repo=repo).returncode == 0


def key_exists(t: Task, repo: pathlib.Path = roots.REPO) -> bool:
    if t.kind == "coding":
        return bool(t.reference) and all(has_commit(r, repo) for r in t.reference)
    return all(p.is_file() for p in t.key_paths())


def change_diffs(t: Task, repo: pathlib.Path = roots.REPO) -> list:
    """The patches that turn the base into the reference state, in order."""
    if len(t.reference) == 1:
        pairs = [(t.base, t.reference[0])]
    else:
        pairs = [(f"{r}^", r) for r in t.reference]
    out = []
    for a, b in pairs:
        p = _git("diff", "--binary", "--full-index", "-M", a, b, repo=repo)
        if p.returncode:
            raise TaskError(f"{t.id}: git diff {a} {b}: {p.stderr.decode().strip()}")
        out.append(p.stdout)
    return out


_IDENT = {"GIT_AUTHOR_NAME": "eval", "GIT_AUTHOR_EMAIL": "eval@localhost",
          "GIT_COMMITTER_NAME": "eval", "GIT_COMMITTER_EMAIL": "eval@localhost",
          "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000",
          "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000"}
_SNAPSHOT = "base snapshot"             # no sha in it: the message must not point back at the source


def _clean_env() -> dict:
    """The environment of every git call in an isolated tree: nothing of the
    caller's git (GIT_DIR, hooks, user config, signing) reaches it, and the
    identity and dates are fixed, so one tree gives one commit sha."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(_IDENT, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
               GIT_CONFIG_NOSYSTEM="1")
    return env


def shipped_dir(t: Task, repo: pathlib.Path = roots.REPO):
    """The task directory's path in the repo if the base already contains it
    (the key would ship with the question), else None. The leak guard."""
    try:
        rel = t.dir.resolve().relative_to(repo.resolve())
    except ValueError:
        return None                     # a task kept outside the repository cannot ship in it
    if _git("cat-file", "-e", f"{t.base}:{rel.as_posix()}", repo=repo).returncode == 0:
        return rel
    return None


# The base snapshot's own pointers to the live checkout. `AGENTS.md`,
# `CLAUDE.md` and `CONTEXT.md` name real paths under $HOME and tell an agent to
# read them, so an arm that follows them leaves the tree and reads the CURRENT
# repository -- the future the isolation exists to hide, and for a task whose key
# lives in this repo, the answer. Measured 2026-10-14: the reference arm wrote its
# answer into this repository twice, and its second run "verified" the first run's
# leftover instead of doing the task. TRADE-OFF, recorded rather than hidden: the
# base commit contains these files, so deleting them makes a cell's environment
# slightly poorer than the run it replays; the pointer-rewriting version (keep the
# file, point it at the tree) is 8f's better fix when a task needs the conventions.
POINTERS = ("AGENTS.md", "CLAUDE.md", "CONTEXT.md")


def strip_pointers(dest: pathlib.Path) -> list:
    """Delete the snapshot's pointers to the live checkout; return what went."""
    gone = []
    for name in POINTERS:
        p = dest / name
        if p.is_file() and not p.is_symlink():
            p.unlink()
            gone.append(name)
    return gone


def neutralise_links(dest: pathlib.Path) -> list:
    """Delete every symlink under `dest` that leaves it (absolute target, `..`
    past the root, or through another link out); return their relative paths.
    A link that stays inside, dangling or not, is kept: it reaches nothing of
    the host. Deleted, not rewritten: a link the agent must not follow has no
    faithful stand-in, and the base commit then records the deletion."""
    root, gone = dest.resolve(), []
    for dirpath, dirs, files in os.walk(root):          # os.walk does not descend into links
        for name in dirs + files:
            p = pathlib.Path(dirpath, name)
            if p.is_symlink() and (os.path.isabs(os.readlink(p))
                                   or not p.resolve().is_relative_to(root)):
                p.unlink()
                gone.append(p.relative_to(root).as_posix())
    return sorted(gone)


def isolate(t: Task, dest: pathlib.Path, repo: pathlib.Path = roots.REPO) -> tuple:
    """A repository at `dest` whose only history is the task's base snapshot.

    `git archive <base>` is extracted into `dest` (nothing, for `tree: empty`),
    escaping symlinks are deleted (`neutralise_links`), the snapshot's pointers to
    the live checkout are deleted (`strip_pointers`), and `git init` + one commit
    records the tree. Nothing of `repo` is copied: no later commit, ref,
    reflog, remote or object, so `git log --all`, `rev-list --all` and
    `cat-file` of the reference see nothing past the base. The commit's identity
    and dates are fixed, so one base gives one sha. `dest` must be absent or
    empty and outside `repo`. Returns (commit sha, deleted links)."""
    dest = pathlib.Path(dest)
    if dest.resolve().is_relative_to(repo.resolve()):
        raise TaskError(f"{t.id}: {dest} is inside the source repository")
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        raise TaskError(f"{t.id}: {dest} exists and is not an empty directory")
    if t.tree == "base" and (rel := shipped_dir(t, repo)) is not None:
        raise TaskError(f"{t.id}: the base already contains {rel}: the key ships with the question")
    dest.mkdir(parents=True, exist_ok=True)
    links, stripped = [], []
    if t.tree == "base":
        arc = subprocess.run(("git", "-C", str(repo), "archive", t.base), capture_output=True)
        if arc.returncode:
            raise TaskError(f"{t.id}: git archive {t.base[:12]}: {arc.stderr.decode().strip()}")
        subprocess.run(("tar", "-x", "--no-same-owner", "-C", str(dest)), input=arc.stdout, check=True)
        links = neutralise_links(dest)
        stripped = strip_pointers(dest)
    env = _clean_env()
    steps = (("init", "-q", "--template=", "-b", "main"),
             ("add", "-A", "-f"),           # -f: a tracked file a .gitignore pattern matches is still base
             ("-c", "core.logAllRefUpdates=false", "-c", "commit.gpgsign=false",
              "commit", "-q", "--allow-empty", "--no-verify", "-m", _SNAPSHOT))
    for args in steps:
        p = subprocess.run(("git", "-C", str(dest)) + args, capture_output=True, env=env)
        if p.returncode:
            raise TaskError(f"{t.id}: git {args[0]}: {p.stderr.decode().strip()[:400]}")
    sha = subprocess.run(("git", "-C", str(dest), "rev-parse", "HEAD"), capture_output=True,
                         env=env, text=True, check=True).stdout.strip()
    return sha, links + [f"{n} (a pointer to the live checkout)" for n in stripped]


def materialise(t: Task, dest: pathlib.Path, change: bool,
                repo: pathlib.Path = roots.REPO) -> None:
    """The work tree a run starts from: `isolate`, and with `change`, the
    task's change applied on top, uncommitted."""
    isolate(t, dest, repo)
    if not change:
        return
    if t.kind == "coding":
        for diff in change_diffs(t, repo):
            p = subprocess.run(("git", "apply", "--binary", "--whitespace=nowarn"),
                               cwd=dest, input=diff, capture_output=True)
            if p.returncode:
                raise TaskError(f"{t.id}: git apply: {p.stderr.decode().strip()[:400]}")
    else:
        target = dest / t.answer
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(t.key_paths()[0], target)


def verify(t: Task, tree: pathlib.Path, timeout: int = VERIFY_TIMEOUT) -> tuple:
    """(exit code, last lines of output) of the task's verify, run from `tree`."""
    env = dict(os.environ, TASK_DIR=str(t.dir))
    try:
        p = subprocess.run(("bash", "-c", t.verify), cwd=tree, env=env,
                           capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s"
    tail = (p.stdout + p.stderr).strip().splitlines()[-3:]
    return p.returncode, " | ".join(tail)


def validate(t: Task, repo: pathlib.Path = roots.REPO, keep: bool = False) -> dict:
    """The exit condition for one task: verify fails without the change and
    passes with it. Each side runs in its own fresh tree."""
    rel = shipped_dir(t, repo)
    if rel is not None:
        return {"id": t.id, "ok": False, "without": None, "with": None,
                "note": f"the base already contains {rel}: the key ships with the question"}
    row = {"id": t.id}
    for side, change in (("without", False), ("with", True)):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix=f"eval-{t.id}-{side}-"))
        try:
            materialise(t, tmp, change, repo)
            row[side], row[f"{side}_out"] = verify(t, tmp)
        except (TaskError, subprocess.CalledProcessError) as e:
            row[side], row[f"{side}_out"] = None, str(e)
        finally:
            if not keep:
                shutil.rmtree(tmp, ignore_errors=True)
    row["ok"] = row["without"] not in (0, None) and row["with"] == 0
    return row


# --- the runner and the arms (4c) --------------------------------------------

ARMS = ("baseline", "dispatch", "bindings", "jev", "reference", "model")
DEFAULT_MODEL = "claude-opus-5-5"       # decision 23: what pi runs when nothing assigns otherwise
REFERENCE_AGENT = "orchestrator"        # 4d: `opencode agent list` names it primary
RESULTS = "orchestration-eval.jsonl"
WORKDIR = pathlib.Path(tempfile.gettempdir()) / "familiar-eval"
SESSION_ROOT = pathlib.Path.home() / ".pi" / "agent" / "sessions"
OPENCODE_DB = pathlib.Path.home() / ".local" / "share" / "opencode" / "opencode.db"
OPENCODE_TUNING = pathlib.Path.home() / ".config" / "opencode" / "oh-my-opencode-slim.json"
POOLS = ("input", "output", "cache_write", "cache_read")
CHARS_PER_TOKEN = 4                     # the same rough rate dispatch's estimate uses
AGENT_TIMEOUT = 5400                    # 90 min; the first reference cell is 4e's to time
FENCE = "```"

# One row's keys, in this order. Uniform on purpose: a row whose shape depends on
# the arm cannot be read as a column, and 4e's adoption rule reads columns.
ROW_KEYS = ("ts", "task", "kind", "arm", "model", "pi_model", "ran_model", "effort",
            "repo_touched", "attempt",
            "tree", "session_dir", "commands", "items", "verifier", "usage",
            "session_logs", "tools", "wall_seconds", "outside_scope", "paths_digest",
            "rework", "verifies", "note")


class RunnerError(ValueError):
    """The plan cannot be built: no such arm, a model the profile cannot serve,
    an item the user owns, a batch prompt Jev cannot be asked. Refused before
    anything is built or spawned."""


@dataclasses.dataclass(frozen=True)
class Arm:
    """One arm: what runs, and where its model comes from.

    THE ONLY DIFFERENCES. Each arm differs from the baseline in one thing -- a
    model, an environment variable, or the process itself -- because an arm that
    changed two would not say which one did the work.

      runs    pi | jev | opencode
      model   ``default``: the arm's one model, the session default (decision 23),
              for the whole prompt; ``item``: one command per item, each with the
              model dispatch's rules assign that item -- dispatch's own mode, and
              the multi-item steps are the only tasks where it can split;
              ``override``: the catalogue id ``--model`` names, for the whole
              prompt -- the measurement arm (2026-10-23), one difference from the
              baseline and a model that need not be in any tier
      env     extra environment variables; PI_BINDINGS is the bindings arm's
              entire difference from the baseline (6b), so the variable is the
              arm, and the row records it
      agent   the opencode agent the reference arm names
    """
    name: str
    runs: str
    model: str
    env: tuple = ()
    agent: str = ""


ARMS_DEF = {
    "baseline": Arm("baseline", "pi", "default"),
    "dispatch": Arm("dispatch", "pi", "item"),
    "bindings": Arm("bindings", "pi", "default", (("PI_BINDINGS", "1"),)),
    "jev": Arm("jev", "jev", "jev"),
    "reference": Arm("reference", "opencode", "default", agent=REFERENCE_AGENT),
    # NOT IN ANY KIND'S `arms:`. A cell that needs a flag must not be planned by a
    # bare `--run`, so this one is selected by naming a model (see `cells`).
    "model": Arm("model", "pi", "override"),
}


@dataclasses.dataclass(frozen=True)
class Command:
    """One process the cell runs, or -- the jev arm -- the calls it makes. The
    cell may hold several: the dispatch arm runs one per item."""
    item: str                       # the item this command carries; "" = the whole prompt
    model: str                      # the catalogue id
    argv: tuple = ()
    env: tuple = ()
    pi_model: str = ""              # `<provider>/<id>` as pi receives it
    effort: str = ""                # the level the class's tier runs at (decision 28)
    how: str = ""                   # how the model was chosen
    source: str = ""                # declared | default | item | reference
    wave: int = 0
    prompt_arg: int = 0             # which argv entry carries the prompt
    prompt_cat: str = ""            # what a shell line reads the prompt from
    prompt_file: str = ""           # the stitched prompt the live run writes, "" = none
    calls: tuple = ()               # jev: (document id, state bytes)


@dataclasses.dataclass
class Cell:
    """One task on one arm in one isolated tree: the unit PLAN §Option 0 counts
    fifty of, and the unit one row records."""
    task: Task
    arm: str
    tree: pathlib.Path
    sessions: pathlib.Path
    commands: tuple = ()
    attempt: int = 1
    note: str = ""

    @property
    def title(self) -> str:
        return f"eval {self.task.id} {self.arm} #{self.attempt}"


@dataclasses.dataclass
class World:
    """What every cell's plan reads: the catalogue, the capability map, dispatch's
    rules and the item contract, loaded once for fifty cells. Handed in whole so a
    test can hand over its own and never touch the machine's state."""
    cat: dict
    caps: dict
    rules: dict
    contract: dict
    profile: str = ""
    selection: dict = dataclasses.field(default_factory=dict)
    override: str = ""            # the model arm's model, from `--model`

    @classmethod
    def load(cls, env=os.environ) -> World:
        caps = models.load_capabilities()
        return cls(models.load(), caps, dispatch.load_config(caps),
                   specs.load_contract(), profiles.active(env),
                   selection_mod.with_needs(selection_mod.load(), caps))

    def pi_model(self, model_id: str) -> str:
        """`<provider>/<id>` for pi, or a refusal naming the reason: a model the
        active profile cannot serve is not silently swapped for another (26)."""
        res = profiles.resolve(model_id, self.profile)
        if not res.available:
            raise RunnerError(f"{model_id}: unavailable in profile {self.profile}: {res.reason}")
        return f"{res.provider}/{res.model}"


# --- the plan ----------------------------------------------------------------

def _prompt(t: Task) -> str:
    return (t.dir / "prompt.md").read_text(encoding="utf-8")


def prompt_parts(text: str, items: list) -> tuple:
    """(the preamble, {item id: the item's own text}). An item runs from its
    checkbox to the next checkbox or the next line that is not indented -- the
    span rule `specs.parse` reads its fields by -- so the dispatch arm carries the
    item's own prose and fields and nothing of its neighbours'."""
    lines = text.splitlines()
    starts = [it.line for it in items]
    out = {}
    for n, it in enumerate(items):
        end = (starts[n + 1] - 1) if n + 1 < len(starts) else len(lines)
        j = it.line                              # 0-based: the line after the checkbox
        while j < end and (not lines[j].strip() or lines[j][:1] in " \t"):
            j += 1
        block = lines[it.line - 1:j]
        while block and not block[-1].strip():
            block.pop()
        out[it.id] = "\n".join(block)
    return "\n".join(lines[:items[0].line - 1]), out


def build_fields(t: Task, it) -> tuple:
    """(the item's fields, ``declared`` or ``default``). PLAN §Dispatch's table
    puts an item nobody assigned on the main agent's frontier model, and 4a's note
    says the single-item prompts come from pre-contract files that carry no fields
    at all, so what is missing is built from task.yaml: `touches:` from the task's
    `scope:`, `verify:` from its `verify:`, `depends:` none, `model:` the session
    default (decision 23). A field the prompt declares is never overwritten."""
    fields = {k: v for k, v in it.fields.items() if (v or "").strip()}
    source = "declared" if fields.get("model") else "default"
    for key, value in (("touches", ", ".join(t.scope)), ("depends", "—"),
                       ("verify", t.verify), ("model", DEFAULT_MODEL)):
        fields.setdefault(key, value)
    return fields, source


def item_order(items: list) -> tuple:
    """(the items with their wave, in run order, and a note). dispatch's table is
    built on the waves, so the runner reads them from the same place
    (`waves.build`). A `depends:` on an id outside this task's own items is
    satisfied outside it -- a later step of the same track -- so it is pruned and
    named; a cycle among the items keeps file order and says so rather than
    guessing."""
    ids = {it.id for it in items}
    outside, pruned = [], []
    for it in items:
        deps = [d for d in _split(it.fields.get("depends") or "") if d not in ("—", "-")]
        keep = [d for d in deps if d in ids]
        outside += [d for d in deps if d not in ids]
        pruned.append(dataclasses.replace(it, fields={**it.fields,
                                                     "depends": ", ".join(keep) or "—"}))
    try:
        built = waves.build(pruned)
    except waves.DependencyError as e:
        return [(it, 1) for it in items], f"file order ({e})"
    out = [(it, n) for n, wave in enumerate(built, 1) for it in wave]
    note = f"{len(built)} wave(s)"
    if outside:
        note += f", {len(outside)} dependency(ies) outside this task: {', '.join(sorted(set(outside)))}"
    return out, note


def item_plan(t: Task, w: World) -> tuple:
    """(the plan, the ordered items, a note): one entry per item of the task's
    prompt, with the model dispatch's OFFLINE rules assign it.

    `dispatch.audit` is called with `Answers()` -- every probe unknown, which is
    what `dispatch <SPECS.md> --dry-run` computes without Jev -- and dispatch's own
    rule is that unknown is never evidence for moving an item, so the declared
    model stands. The arm therefore applies the DECLARATION, not a Jev-routed
    assignment: rule-only dispatch is computed offline for free (PLAN §Dispatch),
    and a live dispatch that probes and moves an item is the named alternative,
    never something this runner invents. A prompt that is not a SPECS item at all
    -- the retrieval, web and batch tasks -- has no declaration to apply, so its
    single entry is the session default and the cell then matches the baseline's:
    the dry run prints that, so the coincidence is visible rather than counted as
    an arm effect."""
    parsed = specs.parse(_prompt(t), set(w.contract["fields"]))
    items, sources = [], {}
    for it in parsed:
        fields, source = build_fields(t, it)
        if source == "default" and w.selection:
            # Nobody declared a model: the class's first tier is the
            # pre-selection (selection.yaml, decision 27). This is what makes the
            # dispatch arm differ from the baseline without editing a prompt.
            tier, idx, why = selection_mod.pick(w.selection, t.task_class, None)
            ids, note = selection_mod.cheapest(w.cat, w.caps, tier, w.rules["rules"])
            if ids:
                fields = dict(fields, model=ids[0])
                source = f"default ({t.task_class} tier {idx + 1})"
                sources[it.id] = source
        sources[it.id] = source
        items.append(dataclasses.replace(it, fields=fields))
    if not items:
        model, how = DEFAULT_MODEL, "default: the prompt is not a SPECS item, so no planner assigned a model"
        if w.selection:
            tier, idx, _ = selection_mod.pick(w.selection, t.task_class, None)
            ids, _note = selection_mod.cheapest(w.cat, w.caps, tier, w.rules["rules"])
            if ids:
                model = ids[0]
                how = (f"no declaration (not a SPECS item): {t.task_class} tier {idx + 1} "
                       f"-> {model}")
        return [{"id": t.id, "model": model, "wave": 1, "source": "default",
                 "effort": class_effort(t, w), "how": how}], [], "no item in the prompt"
    ordered, note = item_order(items)
    plan = []
    level = class_effort(t, w)
    for it, wave in ordered:
        row = dispatch.audit(it, dispatch.Answers(), w.cat, w.caps, w.rules,
                             w.contract.get("user_model", "user"))
        if row.verdict == "user":
            raise RunnerError(f"{t.id}: item {it.id} is `model: user`; the runner has no arm for it")
        why = ("declared" if sources[it.id] == "declared"
               else "no model declared, so the session default" if sources[it.id] == "default"
               else f"no declaration, so the class's pre-selection ({sources[it.id]})")
        plan.append({"id": it.id, "model": row.suggested or it.fields["model"], "wave": wave,
                     "source": sources[it.id], "effort": level,
                     "how": f"{why}: dispatch {row.verdict} ({row.reason})"})
    return plan, [it for it, _ in ordered], note


def class_effort(t: Task, w: World) -> str:
    """The level this task's class runs at, from its tier (decision 28). The level
    follows the CLASS, not the model's chooser: nobody declares one in a SPECS.md,
    and it is the cheapest thing to change, so it belongs to the class's policy."""
    if not w.selection:
        return ""
    tier, _idx, _why = selection_mod.pick(w.selection, t.task_class, None)
    return selection_mod.effort_of(tier)


def _fenced_block(lines: list, start: int) -> str:
    """The text of the fence opening at `start`, or ''."""
    body = []
    for line in lines[start + 1:]:
        if line.startswith(FENCE):
            return "\n".join(body)
        body.append(line)
    return ""


_DOC = re.compile(r"^### (\S+)\s*$")
_OPTION = re.compile(r"^- `([^`]+)`\s*(?:—|:)?\s*(.*)$")


def jev_plan(t: Task) -> tuple:
    """(the documents, the options, the instructions) a batch prompt holds.

    The assignee is asked the question the baseline agent was asked, out of the
    prompt itself: `state` is the document's own text, exactly as the prompt
    fences it, and `criteria` is the prompt's own option list (a subject with its
    falsifier, or a tag set). The instructions are quoted from the prompt where it
    states them (the blockquote under "The instructions each label follows") and
    otherwise assembled from its title and its "How to answer" section -- the one
    place this module writes prose, and it writes none of its own."""
    lines = _prompt(t).splitlines()
    docs, opts, quotes, title, howto = [], [], [], "", []
    section, fence, i = "", False, 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(FENCE):                  # a document is inside its fence
            if not fence and docs and docs[-1][1] is None:
                docs[-1] = (docs[-1][0], _fenced_block(lines, i))
            fence = not fence
            i += 1
            continue
        if fence:                                   # a document's own `## ...` is not a section
            i += 1
            continue
        if (m := _DOC.match(line)):
            docs.append((m.group(1), None))
        elif line.startswith("## "):
            section = line[3:].strip()
        elif line.startswith("# ") and not title:
            title = line[2:].strip()
        elif line.startswith("> "):
            quotes.append(line[2:].strip())
        elif section.lower().startswith("how to answer") and line.strip():
            howto.append(line.strip())
        if (m := _OPTION.match(line)):
            opts.append((m.group(1), " ".join(m.group(2).split())))
        i += 1
    if not docs:
        raise RunnerError(f"{t.id}: no `### <id>` document in the prompt: Jev cannot be asked")
    if len(opts) < 2:
        raise RunnerError(f"{t.id}: the prompt lists {len(opts)} option(s): Jev cannot choose")
    instructions = " ".join(quotes)
    if not instructions:
        instructions = " ".join([title] + howto)
    return [(i, s or "") for i, s in docs], dict(opts), " ".join(instructions.split())


def session_id(t: Task, arm: str, attempt: int, item: str = "") -> str:
    """The cell's pi session id: one per command, deterministic, so a rerun of the
    same cell is the same handle and the log can be found by name."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL,
                          f"familiar/orchestration/eval/{t.id}/{arm}/{attempt}/{item or 'all'}"))


def opencode_model(path: pathlib.Path | None = None) -> str:
    """The model opencode's `orchestrator` runs, from the plugin's tuning file:
    `preset:` names a preset, `presets.<preset>.orchestrator.model` names the model
    (a list picks the first). '' when the file or the entry is missing -- the arm
    runs either way, and the row's `ran_model` carries what actually answered."""
    try:
        data = json.loads(pathlib.Path(path or OPENCODE_TUNING).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    entry = ((data.get("presets") or {}).get(data.get("preset")) or {}).get(REFERENCE_AGENT)
    model = (entry or {}).get("model")
    if isinstance(model, list):
        model = model[0] if model else ""
    return model if isinstance(model, str) else ""


def cell_paths(workdir, t: Task, arm: str, attempt: int) -> tuple:
    """(the tree, the session directory). The sessions sit beside the tree, not in
    it: a log inside the work tree would be an out-of-scope file the agent never
    wrote."""
    base = pathlib.Path(workdir) / t.id / f"{arm}-{attempt}"
    return base / "tree", base / "sessions"


def pi_argv(prompt: str, pi_model: str, sessions: pathlib.Path, sid: str,
            effort: str = "") -> tuple:
    """The one-shot pi command. `--no-approve` matches pi-agent's: an unattended
    run cannot answer a trust prompt. `--session-dir` is what keeps the session log
    beside the tree and findable afterwards. `--thinking` is the level the class's
    tier runs at (decision 28): the cheapest dial, and the child's own log records
    it, so the cost of a level is attributable."""
    return tuple(pi_call.argv(prompt, approve=False, session=pi_call.Session(sessions, sid),
                              model=pi_model, thinking=effort or None))


def opencode_argv(prompt: str, title: str, tree=None, agent: str = REFERENCE_AGENT) -> tuple:
    """The reference arm: opencode's own orchestrator agent (decision 5). `--title`
    is the cell's name, which is how its row is found in opencode's store.

    `--dir` names the workspace EXPLICITLY, which the process's cwd alone does not
    do: opencode's client hands the directory to its server, and without the flag
    the agent's idea of where it works can be the directory the client was started
    from -- the reason the pilot's first reference cells answered from this
    repository, and then the reason two empty-tree cells left no answer file at
    all (measured 2026-10-14)."""
    out = ["opencode", "run", "--agent", agent, "--title", title]
    if tree is not None:
        out += ["--dir", str(tree)]
    return tuple(out + [prompt])


def plan_cell(t: Task, arm: str, *, workdir=WORKDIR, attempt: int = 1,
              w: World | None = None) -> Cell:
    """The cell as it WOULD run: the tree path, the commands, the models. It reads
    files and computes paths; it creates nothing and runs nothing."""
    if arm not in ARMS_DEF:
        raise RunnerError(f"unknown arm {arm!r}; known: {', '.join(ARMS)}")
    a = ARMS_DEF[arm]
    w = w or World.load()
    tree, sessions = cell_paths(workdir, t, arm, attempt)
    prompt = _prompt(t)
    whole = str(t.dir / "prompt.md")
    commands, note = [], ""
    if a.runs == "pi" and a.model != "item":
        level = class_effort(t, w)
        model_id, source = DEFAULT_MODEL, "default"
        how = "default: the session default (decision 23), one session for the whole prompt"
        if a.model == "override":
            if not w.override:
                raise RunnerError("the model arm runs a named model: pass --model <catalogue id>")
            model_id, source = w.override, "override"
            how = (f"override: {model_id}, one session for the whole prompt -- the model "
                   f"the run names, not the class's tier, so a comparison has one difference")
        argv = pi_argv(prompt, w.pi_model(model_id), sessions,
                       session_id(t, arm, attempt), level)
        commands.append(Command(
            item="", model=model_id, argv=argv, env=a.env, pi_model=argv[4],
            effort=level, source=source, prompt_arg=2, prompt_cat=whole,
            how=how + (" with " + ", ".join(f"{k}={v}" for k, v in a.env) if a.env else "")))
    elif a.runs == "pi":
        plan, items, note = item_plan(t, w)
        preamble, blocks = prompt_parts(prompt, items) if items else ("", {})
        for entry in plan:
            item = entry["id"] if items else ""
            body = prompt
            stitched = ""
            if items:
                body = f"{preamble}\n{blocks[item]}\n"
                stitched = f"prompt-{item}.txt"
            argv = pi_argv(body, w.pi_model(entry["model"]), sessions,
                           session_id(t, arm, attempt, item))
            commands.append(Command(
                item=item, model=entry["model"], argv=argv, env=a.env,
                pi_model=argv[4], effort=entry.get("effort") or "",
                how=entry["how"], source=entry["source"],
                wave=entry.get("wave", 0), prompt_arg=2,
                prompt_cat=str(sessions / stitched) if stitched else whole,
                prompt_file=stitched))
    elif a.runs == "jev":
        docs, opts, _instructions = jev_plan(t)
        calls = tuple((i, len(s)) for i, s in docs)
        commands.append(Command(
            item="", model=jev.MODEL, calls=calls, source="item",
            how=f"one choice question per document, {len(opts)} option(s)"))
        note = f"{len(docs)} document(s) in {len(opts)} option(s)"
    else:
        model = opencode_model()
        argv = opencode_argv(prompt, f"eval {t.id} {arm} #{attempt}", sessions.parent / "tree",
                             a.agent or REFERENCE_AGENT)
        commands.append(Command(
            item="", model=model, argv=argv, pi_model="", source="default",
            how=f"opencode's own: agent {a.agent or REFERENCE_AGENT}"
                + (f" (preset model {model})" if model else ""), prompt_arg=6,
            prompt_cat=whole))
    if arm == "dispatch" and any(c.source == "default" for c in commands):
        note = ((note + "; ") if note else "") + \
               "no item declares a model: this command is the baseline's"
    return Cell(t, arm, tree, sessions, tuple(commands), attempt, note)


def cells(tasks: list, arms=None, with_model: bool = False) -> list:
    """(task, arm) for every cell, in task order and then the task's own arm order
    -- the order `tasks.yaml` declares, which is the order PLAN counts in. `arms`
    restricts the set and names an unknown arm rather than quietly planning a
    smaller run.

    THE MODEL ARM IS THE SET'S ONLY MEASUREMENT ARM (2026-10-23), and it is
    selected by NAMING A MODEL, never by a bare `--run`: no kind declares it, so
    `--run` alone plans the fifty cells it always did, `--model X` plans one cell
    per task on X, and `--model X --arms baseline,model` plans both. It exists
    because a model cannot be placed in a tier by a set whose dispatch arm runs
    the tiers: that loop is circular, and this arm is how it is broken."""
    want = set(_split(arms)) if arms else None
    if want:
        unknown = sorted(want - set(ARMS))
        if unknown:
            raise RunnerError(f"unknown arm(s): {', '.join(unknown)}; known: {', '.join(ARMS)}")
    elif with_model:
        want = {"model"}                 # naming a model and nothing else measures it
    if want and "model" in want and not with_model:
        raise RunnerError("the model arm runs a named model: pass --model <catalogue id>")
    out = [(t, a) for t in tasks for a in t.arms if want is None or a in want]
    if want and "model" in want:
        out += [(t, "model") for t in tasks]
    return out


def cell_composition(cell_list: list) -> dict:
    """{arm: how many cells it holds}, arms with no cell left out of the count
    rather than of the print."""
    out = {a: 0 for a in ARMS}
    for _, arm in cell_list:
        out[arm] = out.get(arm, 0) + 1
    return out


# --- the measurements --------------------------------------------------------

def catalogue_price(model_id: str, cat: dict | None = None) -> dict:
    """{'in': $/Mtok, 'out': $/Mtok, 'cache_hit': $/Mtok or ''} for a catalogue
    id, or {} for an id the catalogue does not hold (an opencode model id, say).
    The catalogue's own cost block is the only price table here."""
    cat = cat if cat is not None else models.load()
    _, entry = profiles.find(cat, model_id)
    cost = (entry or {}).get("cost") or {}
    return dict(cost) if cost else {}


def cost(pools: dict, price: dict) -> tuple:
    """(the cell's $, the frontier pools' $) at the catalogue's peak rates:
    `price.cost`, the one place a rate is multiplied (14c), whose docstring holds
    the pool rules."""
    from orchestration import price as _price                        # noqa: PLC0415
    return _price.cost(price, pools)


def estimate(prompt_bytes: int, price: dict) -> tuple:
    """(input tokens at ~4 chars a token, $ at the catalogue's input rate). Output
    is not estimated: nothing here knows how long an answer will be, and a guessed
    one would be read as a measured one."""
    from orchestration import price as _price                        # noqa: PLC0415
    tokens = prompt_bytes // CHARS_PER_TOKEN
    return tokens, _price.cost(price, {"input": tokens})[0]


def _entries(path: pathlib.Path):
    """The JSON objects of one session log, in order; a line that is not an object
    is skipped, because the log is append-only and a torn last line is its normal
    state."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in text.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict):
            yield e


def _session_cwd(path: pathlib.Path) -> str:
    for e in _entries(path):
        if e.get("type") == "session":
            return str(e.get("cwd") or "")
    return ""


def session_logs(sessions: pathlib.Path, *, tree=None, since: float = 0.0) -> list:
    """The pi session logs this cell wrote. `--session-dir` is the runner's, and a
    pi that ignores it writes under `~/.pi/agent/sessions/<cwd>/`, so that tree is
    searched too -- by the tree the log itself names, so a run happening at the same
    time is never summed into this row."""
    found = sorted(sessions.glob("**/*.jsonl")) if sessions.is_dir() else []
    if found or tree is None:
        return found
    want = str(pathlib.Path(tree).resolve())
    for path in sorted(SESSION_ROOT.glob("**/*.jsonl")):
        try:
            if since and path.stat().st_mtime < since:
                continue
        except OSError:
            continue
        if _session_cwd(path) == want:
            found.append(path)
    return found


def read_usage(paths) -> dict:
    """The pools one cell's pi sessions billed. pi writes `input`, `output`,
    `cacheRead` and `cacheWrite` per assistant message, and the row keeps them
    apart because PLAN's token rule and the bill are not the same sum."""
    pools = {k: 0 for k in POOLS}
    for path in paths:
        for e in _entries(path):
            message = e.get("message") if e.get("type") == "message" else None
            u = message.get("usage") if isinstance(message, dict) else None
            if not isinstance(u, dict):
                continue
            for key, field in (("input", "input"), ("output", "output"),
                               ("cache_write", "cacheWrite"), ("cache_read", "cacheRead")):
                try:
                    pools[key] += int(u.get(field) or 0)
                except (TypeError, ValueError):
                    continue
    return pools


def log_model(paths) -> str:
    """`provider/modelId` of the last `model_change` -- the model that actually
    ran, which is not always the model that was asked for: a bridge, a fallback or
    another agent's session is visible here and nowhere else."""
    model = ""
    for path in paths:
        for e in _entries(path):
            if e.get("type") == "model_change":
                model = f"{e.get('provider')}/{e.get('modelId')}"
    return model


def log_tools(paths) -> list:
    """Every tool name the sessions called. This is how two arms are told apart in
    one log: the bindings arm calls `bound_read`/`bound_explore` where the baseline
    calls `read`/`grep` (6b), and the reference arm's own store names its agent."""
    out = set()
    for path in paths:
        for e in _entries(path):
            message = e.get("message") if e.get("type") == "message" else None
            content = message.get("content") if isinstance(message, dict) else None
            for part in content if isinstance(content, list) else []:
                if isinstance(part, dict) and part.get("type") == "toolCall" and part.get("name"):
                    out.add(str(part["name"]))
    return sorted(out)


def opencode_usage(title: str, db: pathlib.Path | None = None) -> dict:
    """The reference arm's usage, from opencode's own SQLite store: the session row
    named by `--title`, whose token columns are the same four pools as pi's. It also
    carries the `agent` and `model` that answered, which is how that arm's row is
    told apart -- and its `cost`, which is opencode's own number and is therefore
    NOT the row's $: the catalogue's price is, so every arm is priced the same way.
    Returns {} when the store, the table or the row is missing."""
    path = pathlib.Path(db or OPENCODE_DB)
    if not path.is_file():
        return {}
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = con.execute(
                "select model, agent, tokens_input, tokens_output, tokens_cache_write, "
                "tokens_cache_read from session where title = ? "
                "order by time_created desc limit 1", (title,)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return {}
    if not row:
        return {}
    model, agent, i, o, w, r = row
    return {"model": model or "", "agent": agent or "",
            "pools": {"input": int(i or 0), "output": int(o or 0),
                      "cache_write": int(w or 0), "cache_read": int(r or 0)}}


def in_scope(path: str, scope) -> bool:
    """Whether a path the tree reports is one the task declared it may write. A
    scope entry covers a directory below it (`engine/x` covers `engine/x/y.py`), a
    `/**` suffix, and a glob (`engine/orchestration/tests/**`, `config/checks/**`)."""
    p = path.removeprefix("./")
    for entry in scope:
        e = (entry or "").strip().removeprefix("./")
        if not e:
            continue
        if p == e:
            return True
        wild = any(c in e for c in "*?[")
        if e.endswith("/**") and p.startswith(e[:-3].rstrip("/") + "/"):
            return True
        if wild and fnmatch.fnmatch(p, e):
            return True
        if not wild and p.startswith(e.rstrip("/") + "/"):
            return True
    return False


def git_paths(tree: pathlib.Path) -> list:
    """Every path `git status --porcelain -uall` reports in the tree: modified
    tracked files and untracked ones. A rename reports its new path; a file the
    tree's own .gitignore hides is not reported, and is therefore not counted
    against the agent (the base's rules, not the runner's, decide that)."""
    p = subprocess.run(("git", "-C", str(tree), "status", "--porcelain", "-uall"),
                       capture_output=True, text=True, check=False)
    if p.returncode:
        return []
    out = []
    for line in p.stdout.splitlines():
        rest = line[3:] if len(line) > 3 else ""
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        rest = rest.strip()
        if rest.startswith('"') and rest.endswith('"'):
            rest = rest[1:-1]
        if rest:
            out.append(rest)
    return sorted(set(out))


def touched(tree: pathlib.Path, scope) -> dict:
    """What the agent wrote, against the task's declared scope:
    {"changed": [...], "outside": [...], "digest": "sha256:...", "n": N}.
    The digest is over the changed paths, so two runs that touched the same files
    carry the same one whatever order git lists them in."""
    changed = git_paths(tree)
    return {"changed": changed,
            "outside": [p for p in changed if not in_scope(p, scope)],
            "digest": "sha256:" + hashlib.sha256("\n".join(changed).encode()).hexdigest()[:16],
            "n": len(changed)}


def rework(verifies: list) -> int:
    """How much the cell had to redo, from [(verifier exit code, tree digest)] in
    order: the verifier runs after the FIRST non-pass, or -- when it passed first --
    1 if the tree changed after that pass. PLAN §Option 0's row: rework needed after
    a pass counts against the arm, so a run that passed and kept writing is not the
    same run as one that stopped."""
    if not verifies:
        return 0
    code, digest = verifies[0]
    if code != 0:
        return sum(1 for c, _ in verifies[1:])
    return 1 if any(d != digest for _, d in verifies[1:]) else 0


def make_row(task: Task, arm: str, *, model: str, pi_model: str = "", ran_model: str = "",
             effort: str = "", attempt: int = 1, repo_touched=(), tree="", session_dir="", commands=(), items=(),
             verifier=None, pools=None, price=None, logs=(), tools=(), wall_seconds=0.0,
             footprint=None, rework_n: int = 0, verifies=(), note: str = "",
             usage_source: str = "", ts: str = "") -> dict:
    """One row, keyed in ROW_KEYS' order. Every arm writes every key: a row whose
    shape depends on the arm cannot be read as a column.

    `model` is what the runner asked for, `pi_model` what pi received, and
    `ran_model` what the session log or opencode's store says answered -- three
    different facts, and a disagreement between the last two is a finding, not a
    detail."""
    pools = {k: int((pools or {}).get(k, 0)) for k in POOLS}
    footprint = footprint or {"changed": [], "outside": [], "digest": "", "n": 0}
    usd, usd_frontier = cost(pools, price or {})
    if pools["input"] and not price:
        unpriced = f"no catalogue price for {model}: the $ is 0, the tokens are not"
        note = "; ".join(n for n in [note, unpriced] if n)
    verifier = dict(verifier or {"exit": None, "pass": False, "tail": ""})
    out = {
        "ts": ts or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "task": task.id,
        "kind": task.kind,
        "arm": arm,
        "model": model,
        "pi_model": pi_model,
        "ran_model": ran_model,
        "effort": effort,
        "repo_touched": list(repo_touched),
        "attempt": attempt,
        "tree": str(tree),
        "session_dir": str(session_dir),
        "commands": [list(x.argv) for x in commands],
        "items": list(items),
        "verifier": {"exit": verifier.get("exit"), "pass": bool(verifier.get("pass")),
                     "tail": verifier.get("tail", "")},
        "usage": {**pools, "frontier": sum(pools[k] for k in ("input", "output", "cache_write")),
                  "usd": usd, "usd_frontier": usd_frontier, "priced": bool(price),
                  "source": usage_source},
        "session_logs": [str(p) for p in logs],
        "tools": list(tools),
        "wall_seconds": round(float(wall_seconds), 1),
        "outside_scope": list(footprint.get("outside", [])),
        "paths_digest": footprint.get("digest", ""),
        "rework": int(rework_n),
        "verifies": list(verifies),
        "note": note,
    }
    assert tuple(out) == ROW_KEYS, "the row's keys are ROW_KEYS, in that order"
    return out


def append_row(row: dict, path: pathlib.Path | None = None) -> pathlib.Path:
    """Append one row to the results file, one JSON object per line. The file is
    append-only and lives under `PAZRAS_DATA_DIR` like the approvals log: a rerun
    adds rows with a new attempt number rather than rewriting a verdict."""
    p = pathlib.Path(path) if path else profiles.data_dir() / RESULTS
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return p


# --- running a cell ----------------------------------------------------------

def mask_paths() -> list:
    """What a cell may not see of the LIVE checkout (item 8f), derived from the
    roots so no path is spelled twice:
      `.git`            every commit, including the future and the reference solutions
      `dev/`            the evaluation set itself: the task keys and every prompt
      `memory/journal/` the dated records a labelling task's key is drawn from
    Reads of the rest of the repository stay possible and are therefore SYMMETRIC
    across arms: the live `engine/`, `config/` and knowledge are the same for every
    cell, while the three above are the ones that answer a task."""
    return [git_dir(), roots.DEV, roots.JOURNAL]


def git_dir(repo: pathlib.Path = roots.REPO) -> pathlib.Path:
    """The directory that holds the commits. In a worktree `.git` is a FILE naming
    `<main>/.git/worktrees/<name>`, and bwrap cannot lay a tmpfs over a file; the
    history lives in the common directory two levels up, so that is what is masked
    (and `mask_argv` binds /dev/null over the pointer file)."""
    dot = repo / ".git"
    if not dot.is_file():
        return dot
    line = dot.read_text(encoding="utf-8").strip()
    gitdir = pathlib.Path(line.partition("gitdir:")[2].strip())
    if not gitdir.is_absolute():
        gitdir = (repo / gitdir).resolve()
    common = gitdir / "commondir"
    if common.is_file():
        return (gitdir / common.read_text(encoding="utf-8").strip()).resolve()
    return gitdir


def readonly_paths() -> list:
    """What a cell may READ but not write OUTSIDE the checkout (8f, its second
    half): the machine's compiled boundaries. A cell's tree sits at its BASE
    commit, and that commit's `boundaries-compile` writes these by absolute path,
    so a cell that runs it without `--check` replaces the machine's boundaries with
    the base's, which are weaker. Measured twice: 2026-10-14 23:39, and 2026-10-15
    02:26 (`ontology-o2a-stems`, dispatch arm, 3.6 h until a recompile). Hiding
    them would leave the cell's own harness with no boundary configuration, so
    they are bound read-only; `--ro-bind-try` because hermes may be absent. The
    paths come from the compiler's own module, so they are spelled once."""
    from boundaries import _boundaries
    return [_boundaries.PI_PERMISSION_CONFIG, _boundaries.HERMES_MEMORY]


def mask_argv(argv, cwd, *, repo: pathlib.Path = roots.REPO,
              wrap: str | None = None) -> list:
    """`argv` under the boundary that makes an escaped agent harmless: the live
    checkout read-only, with the three paths above emptied, and everything else
    (the harnesses in $HOME, the tree in /tmp) untouched. A cell that follows a
    pointer into the repository then finds neither the future nor a place to
    write, which is what made the reference arm's pilot rows invalid.

    `wrap` is the bubblewrap binary; `None` looks it up, and an absent bwrap
    returns the argv unchanged so a machine without it still runs (and the guard
    in `run_cell` reports what moved)."""
    exe = wrap if wrap is not None else shutil.which("bwrap")
    if not exe:
        return list(argv)
    out = [exe, "--dev-bind", "/", "/", "--ro-bind", str(repo), str(repo)]
    for path in mask_paths():
        out += ["--tmpfs", str(path)]
    if (repo / ".git").is_file():                   # a worktree's pointer to the history
        out += ["--ro-bind", "/dev/null", str(repo / ".git")]
    for path in readonly_paths():
        out += ["--ro-bind-try", str(path), str(path)]
    return out + ["--chdir", str(cwd)] + [str(a) for a in argv]


def _spawn(argv, cwd, env, timeout: int = AGENT_TIMEOUT) -> subprocess.CompletedProcess:
    """The one place a cell starts a process, so a test can replace it and the
    runner keeps its hands off a real harness. Every process runs under
    `mask_argv`, so the isolation is a property of the seam, not of each arm.

    A `pi` arm starts through `pi_call` (pi.md §Starting a pi process), which owns stdin and
    the environment; `mask_argv` is its `wrap`. The reference arm is opencode, not
    pi, and keeps this direct spawn. A timeout is re-raised as `TimeoutExpired`,
    the form `run_command` reports."""
    if argv and argv[0] == pi_call.PI:
        r = pi_call.spawn(argv, cwd=cwd, env=env, timeout=timeout, wrap=mask_argv)
        if r.timed_out:
            raise subprocess.TimeoutExpired(argv, timeout)
        return r
    return subprocess.run(mask_argv(argv, cwd), cwd=str(cwd), env=dict(env), check=False,
                          capture_output=True, text=True, timeout=timeout,
                          stdin=subprocess.DEVNULL)


def _env(extra) -> dict:
    env = dict(os.environ)
    env.update(extra or {})
    return env


def run_command(c: Cell, cmd: Command, spawn=_spawn, env=None) -> str:
    """One command of one cell: a stitched prompt is written where the plan said
    (outside the tree), then the process runs with the tree as its cwd. A non-zero
    exit is a note, never an exception: the verifier is what judges the cell."""
    argv = list(cmd.argv)
    if cmd.prompt_file:
        path = c.sessions / cmd.prompt_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(argv[cmd.prompt_arg], encoding="utf-8")
    try:
        p = spawn(argv, c.tree, _env(env if env is not None else cmd.env))
    except subprocess.TimeoutExpired:
        return f"{cmd.item or cmd.model}: timeout after {AGENT_TIMEOUT}s"
    except OSError as e:
        return f"{cmd.item or cmd.model}: {e}"
    # The arm's own output is kept whatever the exit code: for a pi arm the
    # session log is the transcript, but opencode's is not written to the cell,
    # and a reference cell that failed with no output is unattributable.
    if p.stdout or p.stderr:
        name = (cmd.item or "prompt") + ".out"
        (c.sessions / name).write_text((p.stdout or "") + (p.stderr or ""), encoding="utf-8")
    if p.returncode:
        tail = (p.stderr or p.stdout or "").strip().splitlines()[-2:]
        return f"{cmd.item or cmd.model}: exit {p.returncode} ({' | '.join(tail)[:200]})"
    if ARMS_DEF[c.arm].runs == "opencode":
        last = [ln for ln in (p.stdout or "").strip().splitlines() if ln.strip()][-1:]
        return (f"{cmd.model}: exit 0; last line: {last[0][:160]}" if last else "")
    return ""


def jev_run(c: Cell, out=print) -> tuple:
    """The jev arm: one `jev.ask` per document, its answer written to the task's
    answer file. One call carries one document's state, so there is no mapping to
    get wrong (the shape `recommend` uses), and `criteria` is the prompt's own
    option list, so the assignee is asked the question the baseline agent was.
    Returns (pools, what answered, note)."""
    docs, opts, instructions = jev_plan(c.task)
    question = {"answer": {"type": "choice", "instructions": instructions,
                           "criteria": opts}}
    pools, rows, failures, model = {k: 0 for k in POOLS}, [], [], ""
    qhash = dispatch.probes_hash(question)
    for doc_id, state in docs:
        try:
            resp = jev.ask(state, question)
        except jev.JevError as e:
            failures.append(f"{doc_id}: {e.kind}")
            if e.fatal:
                break
            continue
        model = model or str(resp.get("model") or "")
        jevlog.record("eval", f"{c.task.id}:{c.arm}-{c.attempt}#{doc_id}", qhash, resp)
        u = resp.get("usage") or {}
        for key, field in (("input", "input_tokens"), ("output", "output_tokens")):
            try:
                pools[key] += int(u.get(field) or 0)
            except (TypeError, ValueError):
                continue
        got = (resp.get("answers") or {}).get("answer")
        choice = jev.answer_fields(got).get("choice") if isinstance(got, dict) else None
        if choice not in opts:
            failures.append(f"{doc_id}: no usable answer")
            continue
        rows.append((doc_id, choice))
    target = c.tree / c.task.answer
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(f"{i}\t{v}\n" for i, v in rows), encoding="utf-8")
    note = f"{len(rows)} of {len(docs)} document(s) answered"
    if failures:
        note += "; " + ", ".join(failures[:6]) + ("..." if len(failures) > 6 else "")
    return pools, model or jev.MODEL, note


def repo_state(repo: pathlib.Path) -> list:
    """The repository under test as `git status --porcelain` sees it. The eval's
    isolation keeps the FUTURE out of the cell's tree, but nothing keeps the cell
    out of the REPOSITORY: the tree's `AGENTS.md`/`CLAUDE.md`/`CONTEXT.md` are the
    real ones and name real paths, so an agent that follows them can read and write
    the live checkout (measured 2026-10-14: the reference arm wrote its answer.md
    into this repository). The guard is a comparison, not a wall: a cell that moves
    the repository is flagged in its row."""
    p = subprocess.run(("git", "-C", str(repo), "status", "--porcelain"),
                       capture_output=True, text=True)
    return sorted(p.stdout.splitlines()) if p.returncode == 0 else []


def run_cell(c: Cell, *, rounds: int = 1, repo: pathlib.Path = roots.REPO,
             w: World | None = None, spawn=_spawn, keep: bool = False) -> dict:
    """Run one cell and return its row.

    The order is the one the measurements need: the tree is isolated, the arm's
    commands run in order, the tree's footprint is taken BEFORE the verifier (so
    the verifier's own caches are not charged to the agent), the verifier judges
    it, and any further round repeats that on the same tree -- which is what
    `rework` counts. The verifier runs once per round, and the row records every
    round's exit in `verifies` and the last one as the cell's result."""
    w = w or World.load()
    tree, sessions = c.tree, c.sessions
    started = time.monotonic()
    stamp = started - 1.0                     # session-log fallback: before, not after, the run
    if tree.exists() and not keep:
        shutil.rmtree(tree)
    sessions.mkdir(parents=True, exist_ok=True)
    isolate(c.task, tree, repo)
    notes, verifies, footprint = [], [], {}
    repo_before = repo_state(repo)
    jev_result = None
    for _ in range(max(1, rounds)):
        for cmd in c.commands:
            if cmd.argv:
                if (problem := run_command(c, cmd, spawn=spawn)):
                    notes.append(problem)
            elif ARMS_DEF[c.arm].runs == "jev":
                # The jev arm has no argv -- it calls Jev in-process -- and that
                # call WRITES the task's answer file, so it is a step like any
                # other: it runs here, before the footprint and the verifier. It
                # used to run after the verifier, which judged an empty tree on
                # every jev cell (found by the 2026-10-14 pilot).
                jev_result = jev_run(c)
        footprint = touched(tree, c.task.scope)
        code, tail = verify(c.task, tree)
        verifies.append((code, footprint["digest"]))
    repo_touched = [l for l in repo_state(repo) if l not in repo_before]
    if repo_touched:
        notes.append(f"the cell moved the repository under test: "
                     f"{', '.join(repo_touched[:3])}")
    arm, cmds = ARMS_DEF[c.arm], c.commands
    model = cmds[0].model if cmds else ""
    pi_model = next((x.pi_model for x in cmds if x.pi_model), "")
    pools, ran, logs, source = None, "", [], ""
    if arm.runs == "jev":
        if jev_result is None:                  # no step ran: named, not silent
            jev_result = jev_run(c)
            notes.append("the jev step ran after the verifier: no command carried it")
        pools, ran, note = jev_result
        notes.append(note)
        source = "jev-response"
    elif arm.runs == "opencode":
        got = opencode_usage(c.title)
        pools, ran = got.get("pools"), got.get("model", "")
        source = "opencode-db" if pools else ""
        if not pools:
            notes.append(f"no opencode session row titled {c.title!r}: usage not read")
    else:
        logs = session_logs(sessions, tree=tree, since=stamp)
        pools, ran = read_usage(logs), log_model(logs)
        source = "session-log" if logs else ""
        if not logs:
            notes.append("no session log found: usage not read")
    price = catalogue_price(model, w.cat)
    return make_row(
        c.task, c.arm, model=model, pi_model=pi_model, ran_model=ran,
        effort=next((x.effort for x in cmds if x.effort), ""),
        attempt=c.attempt, tree=tree, session_dir=sessions, repo_touched=repo_touched,
        commands=cmds,
        items=[{"id": x.item or c.task.id, "model": x.model, "wave": x.wave,
                "source": x.source, "effort": x.effort} for x in cmds],
        verifier={"exit": code, "pass": code == 0, "tail": tail},
        pools=pools, price=price, logs=logs, tools=log_tools(logs) if logs else [],
        wall_seconds=time.monotonic() - started, footprint=footprint,
        rework_n=rework(verifies), verifies=[v[0] for v in verifies],
        usage_source=source, note="; ".join(n for n in [c.note, *notes] if n))


# --- the dry run and the command ---------------------------------------------

def shell_line(cmd: Command) -> str:
    """The command as a line a shell would accept, with the prompt read from the
    file the live run's copy or the task holds: the runner never goes through a
    shell, and a plan line that pasted a 67 KB prompt would be unreadable."""
    if not cmd.argv:
        return "(no process: `jev.ask` is called in-process)"
    parts = []
    for n, arg in enumerate(cmd.argv):
        parts.append(f'"$(cat {cmd.prompt_cat})"' if n == cmd.prompt_arg else shlex.quote(str(arg)))
    prefix = " ".join(f"{k}={v}" for k, v in cmd.env)
    return (prefix + " " if prefix else "") + " ".join(parts)


def plan_lines(c: Cell, w: World, out=print) -> None:
    """One cell's plan: what would run, where, in which model, at what price."""
    for cmd in c.commands:
        head = f"  {cmd.item or 'prompt':<10} {cmd.model or 'opencode default':<20}"
        if cmd.pi_model:
            head += f" -> {cmd.pi_model}"
        out(head)
        if cmd.how:
            out(f"    why     {cmd.how}")
        out(f"    cmd     {shell_line(cmd)}")
        if cmd.prompt_file:
            out(f"    writes  {c.sessions / cmd.prompt_file} = prompt.md preamble + item {cmd.item}")
        price = catalogue_price(cmd.model, w.cat)
        if cmd.calls:
            tokens, usd = estimate(sum(n for _, n in cmd.calls), price)
            out(f"    calls   {len(cmd.calls)} x jev.ask, one document each; "
                f"{tokens} input tokens, ${usd:.6f} in-only")
        elif cmd.argv:
            size = sum(len(a) for a in cmd.argv[:cmd.prompt_arg + 1])
            tokens, usd = estimate(size, price)
            out(f"    est     ~{size} B of prompt, {tokens} input tokens"
                + (f", ${usd:.6f} in-only at ${price.get('in')}/Mtok (output not estimated)"
                   if price else ", no catalogue price: no estimate"))
    out(f"    tree    {c.tree}")
    out(f"    session {c.sessions}")
    if c.note:
        out(f"    note    {c.note}")


def run(cell_list: list, *, workdir=WORKDIR, attempt: int = 1, rounds: int = 1,
        dry_run: bool = False, results=None, repo: pathlib.Path = roots.REPO,
        keep: bool = False, out=print, err=None, w: World | None = None,
        override: str = "") -> int:
    """Plan every cell, print it (--dry-run) or run it and append its row.

    `--dry-run` is 4c's own exit: it must be runnable in a fresh checkout with no
    keys, no network and no harness on PATH, so it spawns nothing and writes
    nothing. Without it the cells really run -- one run per cell, which is 4e's to
    invoke."""
    err = err or (lambda s: print(s, file=sys.stderr))
    if not cell_list:
        err("eval --run: no cell selected")
        return 2
    try:
        w = w or World.load()
        if override and not w.override:
            w = dataclasses.replace(w, override=override)
        plans = [plan_cell(t, a, workdir=workdir, attempt=attempt, w=w) for t, a in cell_list]
    except (RunnerError, profiles.ProfileError, OSError, _miniyaml.YamlError,
            dispatch.ConfigError) as e:
        err(f"eval --run: {e}")
        return 2
    count = cell_composition(cell_list)
    tasks = len({t.id for t, _ in cell_list})
    if dry_run:
        out(f"eval --run --dry-run: {len(plans)} cell(s) from {tasks} task(s); "
            + ", ".join(f"{a} {n}" for a, n in count.items() if n))
        out("no call is made, nothing is spawned, nothing is written; the tree and "
            "session paths are what a live run would use")
        out("under " + ("bubblewrap: the live checkout read-only, with "
                        + ", ".join((roots.rel(p) if p.is_relative_to(roots.REPO) else str(p)) for p in mask_paths()) + " emptied"
                        if shutil.which("bwrap") else
                        "NO bubblewrap on this machine: the isolation is the tree's "
                        "git only, and a cell can read and write the live checkout"))
        for c in plans:
            out("")
            out(f"{c.task.id}  {c.arm}  #{c.attempt}")
            plan_lines(c, w, out)
        return 0
    rows, failed = [], 0
    for c in plans:
        try:
            row = run_cell(c, rounds=rounds, repo=repo, w=w, keep=keep)
        except (TaskError, OSError) as e:              # one bad cell is not the run
            err(f"eval --run: {c.task.id} {c.arm}: {e}")
            failed += 1
            continue
        append_row(row, results)
        rows.append(row)
        failed += not row["verifier"]["pass"]
        out(f"{row['task']:<32} {row['arm']:<10} {'PASS' if row['verifier']['pass'] else 'FAIL'}"
            f"  {row['usage']['frontier']:>8} frontier  ${row['usage']['usd']:.4f}"
            f"  {row['wall_seconds']:>7}s  rework {row['rework']}"
            + (f"  {row['note']}" if row["note"] else ""))
    passed = sum(bool(r["verifier"]["pass"]) for r in rows)
    out(f"eval --run: {len(rows)} cell(s) run, {passed} passed, {failed} failed or refused; "
        f"rows appended to {results or profiles.data_dir() / RESULTS}")
    return 1 if failed else 0


# --- 12c: the reader's calibration --------------------------------------------
#
# WHICH READER IS A QUESTION ABOUT TOKENS WRITTEN PER VERIFIED QUOTE. The child's
# wall clock is output-bound rather than prefill-bound (1.3-4.0 s to the first
# token, then 5-8.5 k output tokens at 145-200 tok/s), so a model that answers the
# same eight questions in fewer, better-cited lines wins on every axis that
# matters. This measures the role's own failure -- a wrong `path:line` -- and
# nothing else: no judge model, no Elo, no preference.
#
# ONE TASK, ONE MODEL PER RUN. `dev/orchestration/tasks/read-large-context/` holds
# `prompt.md` (the fixed eight questions and the exact reply shape) and
# `questions.yaml` (the id each line must start with and the string its quoted
# passage must carry -- never read by the child). `--calibrate --model <id>` runs
# that prompt through `pi-agent` with the role's own body (5a's `explore`), three
# times by default, and takes the three numbers from the run itself:
#   verified  the `ref+quote` check `bindings.py` runs, applied to each answer line:
#             the quote is at the line named, +-2, in the file the line names
#   correct   the same line also carries the asked fact (the key's string)
#   seconds   wall clock of `pi-agent`, so the child's own spawn is included
#   dollars   the child log's pools at the catalogue's list price, as 4c prices a
#             cell -- not the vendor's invoice
# A model that names a path:line the checker rejects scores zero for that question
# however plausible its prose: that IS the failure the role has.
#
# WHAT LEAVES THE RUN. One row per attempt in `<PAZRAS_DATA_DIR>/calibration.jsonl`
# (13b's recommendation reads it), and the table that goes into the record. The
# rows have no parent transcript of their own: `pi-agent` writes them into the
# delegation log like any other delegation, and the session-end hook closes them.

CALIBRATION = "read-large-context"      # the task directory `--calibrate` reads
CALIBRATION_LOG = "calibration.jsonl"   # one row per attempt, read by 13b


@dataclasses.dataclass(frozen=True)
class Key:
    """One asked question: the id its answer line starts with, and the string a
    right answer quotes."""
    qid: str
    key: str


def load_calibration(d: pathlib.Path) -> tuple:
    """(the prompt, the key, the documents) of a calibration task directory."""
    prompt = (d / "prompt.md").read_text(encoding="utf-8").strip()
    raw = _miniyaml.load((d / "questions.yaml").read_text(encoding="utf-8"))
    key = tuple(Key(qid=str(q["id"]).strip(), key=str(q["key"]).strip())
                for q in raw.get("questions") or [])
    docs = tuple(str(x).strip() for x in raw.get("docs") or [])
    if not prompt or not key:
        raise TaskError(f"{d}: a calibration task needs prompt.md and questions")
    return prompt, key, docs


def _plain(s: str) -> str:
    return " ".join(s.split())


def asked(prompt: str, key) -> list:
    """The ids the prompt does not ask. A key for a question nobody was asked
    scores nothing but reads like a reader's failure."""
    return [k.qid for k in key if not re.search(rf"\b{k.qid}\b", prompt)]


def score(answer: str, root: pathlib.Path, key) -> dict:
    """Score one answer against the key: verified quotes, correct facts, and the
    ids that failed one of the two.

    A line counts only if it BOTH names a `path:line` whose quote the checker
    verifies (`bindings.verify`, the contract `bindings.py` enforces on a real
    child) AND carries the fact the question asked for: a well-quoted sentence
    that answers the neighbouring question is exactly the error a smaller reader
    makes, and the checker alone cannot see it.
    """
    from orchestration import bindings
    lines = {}
    for line in answer.splitlines():
        m = re.match(r"\s*Q(\d+)\b", line)
        if m:
            lines.setdefault(f"Q{int(m.group(1))}", line)
    verified = correct = 0
    wrong, quoted_wrong = [], []
    for k in key:
        line = lines.get(k.qid)
        ok = bool(line) and bindings.verify("ref+quote", line, root).ok
        if ok:
            verified += 1
            if _plain(k.key) in _plain(line):
                correct += 1
            else:
                quoted_wrong.append(k.qid)
        else:
            wrong.append(k.qid)
    return {"verified": verified, "correct": correct, "total": len(key),
            "unverified": wrong, "misquoted": quoted_wrong}


def _attempt(argv: list, timeout: float, env) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          env=env, timeout=timeout + 120)


def touched_key(child: pathlib.Path | None, d: pathlib.Path) -> bool:
    """Whether the child read the key's own file.

    The child runs in the repository, so `questions.yaml` is one `read` away. The
    prompt says to use nothing else, but a measurement that is not checked is a
    measurement of good faith: this scans the child's tool calls for the key file
    and the run records the answer. Nothing is sandboxed for one child, so the
    honest thing is to report it rather than to hide it.
    """
    if child is None:
        return False
    needle = str(d / "questions.yaml")
    for e in _entries(child):
        m = e.get("message") if e.get("type") == "message" else None
        if not isinstance(m, dict) or m.get("role") != "assistant":
            continue
        for block in m.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "toolCall":
                if needle in json.dumps(block.get("arguments"), ensure_ascii=False):
                    return True
    return False


def child_pools(stderr: str) -> tuple:
    """(the child's log, its pools) from `pi-agent`'s join mark on stderr."""
    from orchestration import log as delegations
    m = delegations.MARK.search(stderr or "")
    if not m:
        return None, {}
    path = pathlib.Path(m.group("session"))
    return (path, read_usage([path])) if path.is_file() else (None, {})


def calibrate(d: pathlib.Path, model: str, effort: str = "", attempts: int = 3, *,
              repo: pathlib.Path = roots.REPO, role: str = "explore",
              timeout: float = 900.0, env=None, path: pathlib.Path | None = None,
              out=print, err=None) -> int:
    """Run the task's prompt `attempts` times on one model id and print the table.

    Exit: 0 when every attempt produced an answer, 1 when an attempt failed to run
    (a model the profile cannot serve, a timeout), 2 on a usage error. A failed
    attempt is still a row -- refusing to price it would hide it.
    """
    err = err or (lambda s: print(s, file=sys.stderr))
    try:
        prompt, key, docs = load_calibration(d)
    except (OSError, TaskError, _miniyaml.YamlError) as e:
        err(f"eval --calibrate: {e}")
        return 2
    missing = asked(prompt, key)
    if missing:
        err(f"eval --calibrate: {d}: the prompt does not ask {', '.join(missing)}")
        return 2
    cat = models.load()
    price = catalogue_price(model, cat)
    sizes = [(x, (repo / x).stat().st_size) for x in docs if (repo / x).is_file()]
    read_bytes = sum(n for _x, n in sizes)
    out(f"calibration -- {d.name}, {len(key)} question(s), "
        f"{read_bytes / 1024:.0f} KB to read"
        + (f" in {len(sizes)} record(s)" if sizes else ""))
    out(f"  model {model} at {effort or '(the role\'s own level)'}, "
        f"{attempts} attempt(s)"
        + ("" if price else "  [no catalogue price: the $ stays 0]"))
    out(f"    {'#':>2}  {'verified':>8}  {'correct':>7}  {'seconds':>7}  {'usd':>9}  wrong")
    rows, failed = [], 0
    # `--no-log`: a calibration attempt measures the reader, it is not a delegation
    # a trigger caused, and a line for it would enter 5d's uptake denominator.
    argv = [*bindings_agent(), role, prompt, "--model", model, "--cwd", str(repo),
            "--no-log"]
    if effort:
        argv += ["--effort", effort]
    for n in range(1, attempts + 1):
        started = time.monotonic()
        try:
            proc = _attempt(argv, timeout, env if env is not None else None)
        except subprocess.TimeoutExpired:
            proc, code = None, None
        seconds = round(time.monotonic() - started, 1)
        answer = (proc.stdout if proc else "") or ""
        child, pools = child_pools(proc.stderr if proc else "")
        usd = cost(pools, price)[0] if pools else 0.0
        s = score(answer, repo, key)
        ran = proc is not None and proc.returncode == 0
        row = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               "task": d.name, "model": model, "effort": effort, "attempt": n,
               "seconds": seconds, "usd": usd, "exit": proc.returncode if proc else None,
               "ran": ran, "child_log": str(child) if child else None, "answer": answer,
               "key_read": touched_key(child, d), **s}
        rows.append(row)
        failed += not ran
        # An attempt that never ran has no rate, and printing 0/8 would read as a
        # reader that failed every question. The reason goes in its place.
        wrong = ("did not run: " + _reason(proc)) if not ran else \
            ", ".join(s["unverified"] + s["misquoted"]) or "-"
        shown = ("  -/-      -/-   " if not ran else
                 f"{s['verified']}/{s['total']:<6}  {s['correct']}/{s['total']:<5}")
        out(f"    {n:>2}  {shown}  {seconds:>7.1f}  {('$%.4f' % usd):>9}  {wrong}"
            + ("  READ THE KEY" if row["key_read"] and ran else ""))
    if rows:
        written = append_calibration(rows, path)
        scored = [r for r in rows if r.get("ran")]
        if any(r["key_read"] for r in rows):
            err(f"  warning: {sum(r['key_read'] for r in rows)} attempt(s) read "
                f"{d / 'questions.yaml'}: their score is not a reading score")
        if not scored:
            out(f"  summary  {model} at {effort or '-'}: did not run "
                f"({len(rows)} attempt(s)); see the reason above")
        else:
            out(f"  summary  {model} at {effort or '-'}: verified "
                f"{_median([r['verified'] for r in scored])}/{len(key)} (median), "
                f"{_median([r['seconds'] for r in scored]):.1f} s, "
                f"${_median([r['usd'] for r in scored]):.4f} per read over "
                f"{len(scored)} attempt(s)"
                + ("" if len(scored) == len(rows) else
                   f"; {len(rows) - len(scored)} of {len(rows)} did not run")
                + (f"; rows appended to {written}" if written else ""))
    return 1 if failed else 0


def _median(values: list):
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


BENIGN = ("No project session found", "pi-agent: skipping")


def _reason(proc) -> str:
    """The last line of a failed child's stderr that names something.

    Last, not first: pi writes warnings before the failure, and the vendor's own
    sentence is the one worth reading. pi's two harmless lines are skipped so a
    `skipping <file>: no frontmatter` warning cannot stand in for a 429.
    """
    lines = [x.strip() for x in (proc.stderr or "").splitlines() if x.strip()] if proc else []
    named = [x for x in lines if not any(b in x for b in BENIGN)]
    return named[-1][:160] if named else "no stderr"


def bindings_agent() -> list:
    """`pi-agent`'s argv, through the same resolution `bindings.py` uses."""
    from orchestration import bindings
    return bindings.pi_agent()


def append_calibration(rows: list, path: pathlib.Path | None = None) -> pathlib.Path:
    """One row per attempt, appended to `<data>/calibration.jsonl` (13b's input)."""
    path = path or profiles.data_dir() / CALIBRATION_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    return path


def calibration_rows(path: pathlib.Path | None = None) -> list:
    """Every attempt recorded so far, in the order they ran."""
    path = path or profiles.data_dir() / CALIBRATION_LOG
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


# --- output ------------------------------------------------------------------

def list_rows(tasks: list, repo: pathlib.Path = roots.REPO) -> list:
    rows = [("id", "kind", "base", "arms", "scope", "key")]
    for t in tasks:
        scope = ", ".join(t.scope)
        rows.append((t.id, t.kind, t.base[:7], ",".join(t.arms),
                     scope if len(scope) <= 60 else scope[:57] + "...",
                     "yes" if key_exists(t, repo) else "NO"))
    return rows


def _table(rows: list) -> str:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows)


def _side(code) -> str:
    return "ERROR" if code is None else ("PASS" if code == 0 else f"FAIL({code})")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="familiar orchestration eval",
                                 description="The evaluation set: list it, validate its "
                                             "verifiers, or run its cells.")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true",
                      help="one row per task: id, kind, base, arms, scope, key present")
    mode.add_argument("--isolate", metavar=("ID", "DEST"), nargs=2,
                      help="build the task's isolated start repository at DEST (prefer a path under /tmp)")
    mode.add_argument("--validate", metavar="ID", nargs="?", const="all",
                      help="verify fails on the base alone and passes with the change (default: all)")
    mode.add_argument("--run", action="store_true",
                      help="run each cell: the arm in an isolated tree, judged by the task's verifier")
    mode.add_argument("--calibrate", action="store_true",
                      help="run the reader calibration task on one model id (12c)")
    ap.add_argument("--tasks-dir", type=pathlib.Path, default=TASKS,
                    help="where the task directories are (tests use a tmp tree)")
    ap.add_argument("--repo", type=pathlib.Path, default=roots.REPO,
                    help="the repository the bases and references are in")
    ap.add_argument("--keep", action="store_true", help="keep the work trees, for debugging")
    ap.add_argument("-v", "--verbose", action="store_true", help="print each verify's last lines")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --run: print every cell's command line, model, tree and "
                         "estimated cost, and spawn nothing")
    ap.add_argument("--tasks", default="all",
                    help="--run: all, or a comma-separated list of task ids")
    ap.add_argument("--arms", default="",
                    help="--run: a comma-separated subset of " + ", ".join(ARMS))
    ap.add_argument("--workdir", type=pathlib.Path, default=WORKDIR,
                    help="--run: where the isolated trees and session logs are built")
    ap.add_argument("--attempt", type=int, default=1,
                    help="--run: the attempt number each row carries (4e's rerun)")
    ap.add_argument("--rounds", type=int, default=1,
                    help="--run: how many times the cell's commands run; more than one is rework")
    ap.add_argument("--results", type=pathlib.Path,
                    help=f"--run: where the rows are appended (default {RESULTS} under PAZRAS_DATA_DIR)")
    ap.add_argument("--model",
                    help="--calibrate: the catalogue id to measure; --run: the model "
                         "the `model` arm runs (one cell per task, the class's effort)")
    ap.add_argument("--effort", default="",
                    help="--calibrate: the thinking level, default the role's own")
    ap.add_argument("--attempts", type=int, default=3,
                    help="--calibrate: how many times to run the prompt (default 3)")
    ap.add_argument("--role", default="explore",
                    help="--calibrate: the pi-agent role whose body the child gets "
                         "(default explore, 5a's read-only reader)")
    ap.add_argument("--calibration", type=pathlib.Path,
                    help=f"--calibrate: the task directory (default <tasks-dir>/{CALIBRATION})")
    args = ap.parse_args(argv)
    if args.dry_run and not args.run:
        print("eval: --dry-run applies to --run", file=sys.stderr)
        return 2
    if args.calibrate:
        if not args.model:
            print("eval --calibrate: --model names the model to measure", file=sys.stderr)
            return 2
        if args.attempts < 1:
            print("eval --calibrate: --attempts needs a count of at least 1", file=sys.stderr)
            return 2
        return calibrate(args.calibration or args.tasks_dir / CALIBRATION, args.model,
                         args.effort, args.attempts, repo=args.repo, role=args.role)
    try:
        spec = load_set(args.tasks_dir)
        tasks = load(args.tasks_dir)
    except (OSError, TaskError, _miniyaml.YamlError) as e:
        print(f"eval: {e}", file=sys.stderr)
        return 2
    if args.list:
        print(_table(list_rows(tasks, args.repo)))
        gaps = composition(tasks, spec)
        print(f"eval: {len(tasks)} task(s)" + ("; " + "; ".join(gaps) if gaps else ""))
        return 1 if gaps or not all(key_exists(t, args.repo) for t in tasks) else 0
    if args.isolate:
        tid, dest = args.isolate
        found = [t for t in tasks if t.id == tid]
        if not found:
            print(f"eval: no task {tid!r}", file=sys.stderr)
            return 2
        try:
            sha, links = isolate(found[0], pathlib.Path(dest), args.repo)
        except TaskError as e:
            print(f"eval: {e}", file=sys.stderr)
            return 1
        print(f"eval --isolate: {tid} at {dest}, one commit {sha[:12]}"
              + (f", {len(links)} escaping symlink(s) deleted: {', '.join(links)}" if links else ""))
        return 0
    if args.run:
        chosen = tasks if args.tasks == "all" else [t for t in tasks if t.id in set(_split(args.tasks))]
        missing = sorted(set(_split(args.tasks)) - {t.id for t in tasks}) if args.tasks != "all" else []
        if not chosen or missing:
            print(f"eval: no task {', '.join(missing) or args.tasks!r}", file=sys.stderr)
            return 2
        try:
            return run(cells(chosen, args.arms, with_model=bool(args.model)),
                       workdir=args.workdir, attempt=args.attempt,
                       rounds=args.rounds, dry_run=args.dry_run, results=args.results,
                       repo=args.repo, keep=args.keep, override=args.model or "")
        except RunnerError as e:
            print(f"eval --run: {e}", file=sys.stderr)
            return 2
    chosen = tasks if args.validate == "all" else [t for t in tasks if t.id == args.validate]
    if not chosen:
        print(f"eval: no task {args.validate!r}", file=sys.stderr)
        return 2
    rows, bad = [("id", "without change", "with change", "exit met")], 0
    for t in chosen:
        r = validate(t, args.repo, args.keep)
        bad += not r["ok"]
        rows.append((t.id, _side(r["without"]), _side(r["with"]), "yes" if r["ok"] else "NO"))
        if args.verbose or not r["ok"]:
            for side in ("without", "with"):
                if r.get(f"{side}_out"):
                    print(f"  {t.id} {side}: {r[f'{side}_out']}", file=sys.stderr)
            if r.get("note"):
                print(f"  {t.id}: {r['note']}", file=sys.stderr)
    print(_table(rows))
    print(f"eval --validate: {len(chosen)} task(s), {len(chosen) - bad} met, {bad} not met")
    return 1 if bad else 0
