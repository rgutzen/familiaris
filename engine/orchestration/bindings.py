"""bindings -- who does a tool's, a command's or a skill's work (decision 17, item 6b).

`config/orchestration/bindings.yaml` is one table for `item: · tool: · command: ·
skill:`, because each asks the same question: who does this? This module reads it
and answers it in three verbs.

`--check` is offline and keyless, like `dispatch --check`: every binding names a
known kind, a declared contract, a callable catalogue id (or `route` with a default
and an answer-to-model map whose every model is callable), a privacy value, and
`fallbacks:` that are callable catalogue ids with no duplicate, no `route` and no
repeat of the `default:`. Availability depends on the profile, so it is never a
`--check` finding. A
binding whose `role:` is not in pi-agent's roster is INACTIVE, reported on its own
line and not a finding: the roles are 5a's to write, and a binding may be declared
before its child exists.

`--resolve <on>` says which model would run, under the active profile, and why.
`run <on> <task>` spawns the child and checks what it returns.

  A BINDING DELEGATES; IT NEVER SWITCHES. The child is `pi-agent <role> --model
  <provider/id>` with its own context. Switching the parent's model would forfeit
  the parent's prompt cache, and on Opus 5.5 a cache read costs 5% of input, so a
  switch repays the whole prefix at full price (PLAN.md §Bindings, rule 1).

  THE PROFILE DECIDES THE PROVIDER. A model resolves through
  `profiles.resolve` under the active profile; an unavailable one is reported with
  the reason and never borrowed (decision 26). The resolved model's privacy class
  must equal the binding's `privacy:` unless that is `any`.

  THE EFFECTIVE CHAIN. A binding resolves through an ordered chain: (1) its
  `model:`, for `model: route` the routed choice; (2) its `default:`, routed
  bindings only; (3) its `fallbacks:`, a comma-separated list of callable
  catalogue ids, in the order written. The first entry AVAILABLE under the active
  profile runs. An entry is unavailable when `profiles.resolve` says so (no key,
  no login file, jurisdiction not allowed, provider none) or when its privacy
  class is not the binding's `privacy:` (unless `any`): it is skipped, with its
  reason. An id met twice in one chain is tried once. The swap is never silent:
  the `binding:` line and `--resolve` name the entry that runs, its place in the
  chain and each reason for each entry skipped before it. A chain with no
  available entry exits 3 and names every entry's reason, one line each. No entry
  borrows another profile (decision 26).

  ROUTING IS DECLARED, NOT GENERAL. `model: route` asks Jev ONE `choice` question
  whose state is the call's task text, with the binding's own wording; the answer
  names a model through `route.models`. The default stands in for the routed model
  when Jev's probability for its answer is below `route_confident_at`, when the call
  fails, or when the answer maps to a model the profile cannot serve.
  Routing sends the task text to Jev, so `--check` refuses a routed binding whose
  privacy is not `any`. The question's wording hash prints with every routed
  resolution, the `dispatch.yaml` pattern: a reworded question is a new population.

  THE CHILD RETURNS SOMETHING VERIFIABLE (rule 2). `ref+quote`: each finding line
  is `path:line` (or `path:a-b`) and a quoted string, and each quote is looked up in
  its file at those lines (+-2, a model's line numbers drift); `ref+quote+defect`
  adds the CLAIM -- `-- <what is wrong>` -- because a citation and a finding are
  otherwise indistinguishable (a review returned four bare citations on
  2026-10-14 and the checker passed them); `extract+url`: each paragraph carries an
  http(s) URL and a quote. `not found` alone is a valid
  answer. `run` prints the child's text, then one `binding:` line with the model,
  how it was chosen and the contract's verdict, and exits 4 when the contract
  fails, so the parent is told not to trust the text rather than left to notice.
  The contract's wording is appended to the child's task, because a role's body
  may predate the contract (`explore.md` asks for prose until 5a rewrites it).

  COMMANDS AND SKILLS (6c). `command:<name>` runs `~/.claude/commands/<name>.md`,
  `skill:<name>` the skill's SKILL.md (a `mode: link` record's body is its
  `upstream_path`). Either way the text is the CHILD'S INSTRUCTIONS, not the
  parent's: `run` writes a one-off role into a temp dir (the bound `role:`'s tools
  and trust rules, then the text, then the binding's `note:`), and points
  `pi-agent` at it through `PI_AGENT_DIR`, so `pi-agent` itself is unchanged. The
  call's arguments are the child's task. The child runs with `--session`, and the
  `binding:` line names the session log and the model its `model_change` records.

EXIT CODES. 0 ok. 1 `--check` findings. 2 usage, an unknown `on`, an unreadable
table. 3 the binding resolved to no available model, or is inactive. 4 the child
ran and its output fails the contract. Otherwise the child's own non-zero code.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from harness import jev
from lib import _miniyaml
from lib import roots
from orchestration import models as models_mod
from orchestration import jevlog, profiles, selection

BINDINGS = roots.SUBAGENTS / "bindings.yaml"
CATALOGUE = roots.SUBAGENTS / "models.yaml"
KINDS = ("item", "tool", "command", "skill", "role")
# Contracts whose text is an INSTRUCTION the child must follow, so it is
# appended to every task. `rewrite` is excluded: its text is the shape `verify`
# checks, and the role body already asks for it.
SHAPE_CONTRACTS = ("ref+quote", "ref+quote+defect", "extract+url", "command+exit")
REQUIRED = ("on", "contract", "role", "model", "privacy")
ROUTE = "route"
ANY = "any"
NOT_FOUND = "not found"
LINE_SLACK = 2
SKILLS = roots.SKILLS
COMMANDS = pathlib.Path.home() / ".claude" / "commands"
SESSION_DIR = pathlib.Path.home() / ".pi/agent/sessions/pi-agent"
# pi-agent's session namespace (engine/orchestration/pi-agent NS): the same handle gives
# the same session id, which is how `run` finds the child's log without a lookup.
PI_AGENT_NS = uuid.UUID("6ba7b812-9dad-11d1-80b4-00c04fd430c8")
CHILD_KINDS = ("command", "skill")
# Kinds whose instructions are read off disk; `role:` reads the roster body (1c).
TEXT_KINDS = CHILD_KINDS + ("role",)


class BindingError(ValueError):
    """An unknown `on` or an unreadable table; the CLI maps it to exit 2."""


def load(path: pathlib.Path = BINDINGS) -> dict:
    return _miniyaml.load(path.read_text(encoding="utf-8"))


def roster(directory: pathlib.Path = roots.SUBAGENTS) -> set:
    """The role names pi-agent can run: one `<name>.md` with frontmatter each."""
    out = set()
    for p in directory.glob("*.md"):
        head = p.read_text(encoding="utf-8").split("---")
        if len(head) < 3:
            continue
        m = re.search(r"^name:\s*(\S+)", head[1], re.M)
        out.add(m.group(1) if m else p.stem)
    return out


def _callable(cat: dict) -> set:
    return {e["id"] for e in cat.get("models") or []}


def route_at(table: dict) -> float:
    """The routing threshold, or `BindingError`. One reader, so a table with the
    key absent, empty (`None`) or non-numeric exits 2 wherever it is used: the
    review role (2026-10-14) found `float(table[...])` raising KeyError/TypeError
    out of `resolve` and past `main`'s handlers, a traceback for a bad table."""
    v = table.get("route_confident_at")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise BindingError(f"route_confident_at: {v!r} is not a number") from None


def check(table: dict, cat: dict, roles: set, *, skills: pathlib.Path | None = None,
          commands: pathlib.Path | None = None) -> tuple[list, list]:
    """(findings, inactive notes). Offline: no key, no network."""
    found, inactive, seen = [], [], {}
    contracts = table.get("contracts") or {}
    ids = _callable(cat)
    try:
        route_at(table)
    except BindingError as e:
        found.append(str(e))
    for n, b in enumerate(table.get("bindings") or [], 1):
        on = b.get("on") or f"#{n}"
        say = lambda msg: found.append(f"{on}: {msg}")  # noqa: E731
        for k in REQUIRED:
            if not b.get(k):
                say(f"{k}: missing")
        kind = on.split(":", 1)[0]
        if ":" not in on or kind not in KINDS:
            say(f"on: want <kind>:<name>, kind one of {', '.join(KINDS)}")
        if on in seen:
            say(f"on: also bound as #{seen[on]}")
        seen.setdefault(on, n)
        if b.get("contract") and b["contract"] not in contracts:
            say(f"contract: {b['contract']!r} is not under contracts:")
        if kind in TEXT_KINDS and ":" in on:
            text = source_text(on, skills=skills, commands=commands)
            if not text:
                say(f"on: no {kind} text for {on.split(':', 1)[1]!r}")
            elif b.get("contract") == "command+exit" and not expected_commands(text):
                # The contract reports the commands a text fences; with none,
                # no reply can keep it, so the binding is refused, not run.
                say("contract: command+exit, but the text fences no command")
        if b.get("note") is not None and not isinstance(b["note"], str):
            say("note: not a string")
        if b.get("scope") is not None and b["scope"] not in ("inherited", "ignored"):
            say(f"scope: {b['scope']!r}; inherited or ignored")
        level = (b.get("effort") or "").strip()
        if level:
            if level not in selection.LEVELS:
                say(f"effort: {level!r} is not one of {', '.join(selection.LEVELS)}")
            else:
                # The level must be servable by EVERY model the chain can reach, or
                # a swap would land on a child that refuses its own level (exit 2).
                for mid in [b.get("model"), b.get("default")] + fallbacks(b):
                    if mid in (None, "", ROUTE):
                        continue
                    why = models_mod.effort_reason(cat, mid, level)
                    if why:
                        say(f"effort: {why}")
        model = b.get("model")
        if model == ROUTE:
            r = b.get("route") or {}
            if not b.get("default"):
                say("default: missing; `model: route` needs one")
            if not r.get("instructions") or not r.get("criteria"):
                say("route: needs instructions: and criteria:")
            answers, models = set(r.get("criteria") or {}), r.get("models") or {}
            if answers != set(models):
                say(f"route: criteria and models name different answers "
                    f"({', '.join(sorted(answers ^ set(models)))})")
            for ans, mid in models.items():
                if mid not in ids:
                    say(f"route.models.{ans}: {mid!r} is not a callable catalogue id")
            if b.get("privacy") not in (None, ANY):
                say("privacy: a routed binding sends the task text to Jev, so it must be `any`")
        elif model and model not in ids:
            say(f"model: {model!r} is not a callable catalogue id")
        elif b.get("route"):
            say("route: given, but model is not `route`")
        if b.get("default") and b["default"] not in ids:
            say(f"default: {b['default']!r} is not a callable catalogue id")
        _check_fallbacks(b, ids, say)
        if kind == "role" and b.get("role") != on.split(":", 1)[-1]:
            # 1c: `on: role:X` READS role X's body and RUNS b["role"]; a mismatch would
            # check one definition and spawn another.
            say(f"role: {b.get('role')!r} must equal {on.split(':', 1)[-1]!r} for this kind")
        if b.get("role") and b["role"] not in roles:
            inactive.append(f"{on}: inactive: role {b['role']!r} is not in pi-agent's roster")
    return found, inactive


def fallbacks(b: dict) -> list[str]:
    """The binding's `fallbacks:` ids in the order written; blanks dropped."""
    v = b.get("fallbacks")
    return [x.strip() for x in v.split(",") if x.strip()] if isinstance(v, str) else []


def _check_fallbacks(b: dict, ids: set, say) -> None:
    v = b.get("fallbacks")
    if v is None:
        return
    if not isinstance(v, str):
        say("fallbacks: not a comma-separated string")
        return
    parts = [x.strip() for x in v.split(",")]
    if not any(parts):
        say("fallbacks: empty")
    elif not all(parts):
        say("fallbacks: an empty entry (stray comma)")
    seen = set()
    for f in filter(None, parts):
        if f == ROUTE:
            say("fallbacks: `route` cannot be a link of a chain")
        elif f not in ids:
            say(f"fallbacks: {f!r} is not a callable catalogue id")
        if f in seen:
            say(f"fallbacks: {f!r} appears twice in the chain")
        seen.add(f)
        if f == b.get("default"):
            say(f"fallbacks: {f!r} is also the default")
        elif f == b.get("model"):
            say(f"fallbacks: {f!r} is also the model")


def find(table: dict, on: str) -> dict:
    for b in table.get("bindings") or []:
        if b.get("on") == on:
            return b
    known = ", ".join(b.get("on", "?") for b in table.get("bindings") or [])
    raise BindingError(f"no binding for {on!r}; bound: {known}")


def question(b: dict) -> dict:
    r = b["route"]
    return {"route": {"type": "choice", "instructions": r["instructions"],
                      "criteria": r["criteria"]}}


def question_hash(b: dict) -> str:
    blob = json.dumps(question(b), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclasses.dataclass
class Choice:
    on: str
    role: str
    contract: str
    model: str = ""                 # the catalogue id that runs
    pi_model: str = ""              # <provider>/<id>, empty when unavailable
    how: str = ""                   # static | route <answer> p=.. | default: <why>
    available: bool = False
    reason: str = ""
    effort: str = ""                # pi's thinking level for the child, when declared
    usage: dict = dataclasses.field(default_factory=dict)   # a routed binding's Jev call
    klass: str = ""                 # the privacy class of the model that runs

    def line(self) -> str:
        if not self.available:
            if "\n" in self.reason:
                return (f"{self.on}: unavailable, no entry of the chain can run:\n"
                        + "\n".join(f"  {r}" for r in self.reason.splitlines()))
            return f"{self.on}: unavailable: {self.reason}"
        level = f"; effort {self.effort}" if self.effort else ""
        return (f"{self.on} -> {self.model} ({self.pi_model}; {self.how}; "
                f"posture {self.klass or '?'}{level}; contract {self.contract})")


def _serve(model_id: str, privacy: str, profile: str, env, cfg, cat) -> tuple[str, str]:
    """(pi model, '') or ('', reason). Never `approve=`: no entry borrows a profile."""
    res = profiles.resolve(model_id, profile, env=env, cfg=cfg, cat=cat)
    if not res.available:
        return "", res.reason
    if privacy != ANY and res.privacy != privacy:
        return "", f"privacy {res.privacy}, the binding wants {privacy}"
    return f"{res.provider}/{res.model}", ""


def resolve(table: dict, on: str, task: str | None = None, *, cwd=None, env=os.environ,
            dry_run: bool = False, cfg: dict | None = None, cat: dict | None = None) -> Choice:
    """Which model runs `on` under the active profile, and why. A routed binding
    asks Jev only with a task and without `dry_run`.

    THE POSTURE RULE (ruled 2026-10-14). The chain is walked in order, and the
    entry that runs is the FIRST AVAILABLE one IN THE PREFERRED POSTURE, where the
    preferred class is the binding's own `privacy:` when it declares one, else the
    calling directory's scope (`selection.yaml`), else the head's own class. Only
    if no entry of that class is available does a different posture run, and the
    line says so. So "same jurisdiction first, then anything allowed" holds, and a
    closed Claude window does not halt the work: the posture is an ORDER, not a
    filter -- only a `privacy:` declaration filters. A binding declared
    `scope: ignored` (a call that reads no local file: a web search, a fetch) skips
    the scope entirely."""
    b = find(table, on)
    cfg = cfg or profiles.load()
    cat = cat or _miniyaml.load(CATALOGUE.read_text(encoding="utf-8"))
    profile = profiles.active(env, cfg)
    c = Choice(on, b["role"], b["contract"], effort=(b.get("effort") or "").strip())
    privacy = b.get("privacy") or ANY
    want = _preferred(b, privacy, cwd)
    if b["model"] != ROUTE:
        head, head_how = b["model"], "static"
    else:
        head, head_how = _route(table, b, task, dry_run, c)
    chain, tried = [(head, "head")], {head}
    later = [(b["default"], "default")] if b["model"] == ROUTE else []
    for mid, kind in later + [(f, "fallback") for f in fallbacks(b)]:
        if mid not in tried:
            tried.add(mid)
            chain.append((mid, kind))
    served, skipped = [], []          # (k, id, kind, pi, class) / (id, reason)
    for k, (mid, kind) in enumerate(chain, 1):
        pi, why = _serve(mid, privacy, profile, env, cfg, cat)
        if why:
            skipped.append((mid, why))
            continue
        served.append((k, mid, kind, pi, _class_of(mid, cat, cfg, profile)))
    pick = next((x for x in served if want and x[4] == want), None) or (served[0] if served else None)
    if pick is not None:
        k, mid, kind, pi, klass = pick
        c.model, c.pi_model, c.klass = mid, pi, klass
        # Entries that WERE available and were passed over for their posture are
        # part of the reason, not only the unavailable ones.
        passed = [(x[1], x[4]) for x in served if x[0] < k and want and x[4] != want]
        c.how = _how(k, kind, head, head_how, skipped, klass, want, len(chain), passed)
        c.available = True
        return c
    c.model, c.how = head, head_how
    c.reason = "\n".join(f"{i}: {r}" for i, r in skipped)
    return c


def _preferred(b: dict, privacy: str, cwd) -> str:
    """The class the chain prefers: the binding's own declaration first, then the
    calling directory's scope, then nothing (the head's class is the fallback)."""
    if privacy != ANY:
        return privacy
    if cwd and (b.get("scope") or "inherited") != "ignored":
        decl = selection.scope_of(selection.load(), cwd)
        if decl.get("privacy"):
            return decl["privacy"]
    return ""


def _class_of(model_id: str, cat: dict, cfg: dict, profile: str) -> str:
    """The class `profiles.resolve` would compute for this model: the entry's
    JURISDICTION plus the VENDOR's training value in this profile (not the
    entry's: a vendor's training posture is per vendor, not per model)."""
    e = next((x for x in cat.get("models") or [] if x.get("id") == model_id), None)
    if e is None:
        return ""
    vendor = ((cfg.get("profiles", {}).get(profile) or {}).get("vendors") or {}).get(
        e.get("vendor"), {})
    training = (vendor.get("training") or {}).get("value", "")
    return profiles.privacy_class(e.get("jurisdiction", ""), training, cfg)


def _how(k: int, kind: str, head: str, head_how: str, skipped: list, klass: str,
         want: str, n: int, passed: list | None = None) -> str:
    # The posture is named only when it is the interesting case: a preference was
    # declared (by the binding or by the calling directory's scope) and the entry
    # that ran is not of that class. Otherwise the line would carry a constant.
    tail = ""
    if want and klass and klass != want:
        tail = f"; posture {klass}, the preferred {want} is unavailable"
    if kind == "head":
        return head_how + tail
    bits = [f"{i} unavailable, {r}" for i, r in skipped]
    bits += [f"{mid} ({klass_}) passed over: the preferred posture is {want}"
             for mid, klass_ in (passed or [])]
    why = "; ".join(bits)
    if kind == "default":
        return f"default: routed model unavailable ({head}: {skipped[0][1] if skipped else ''})" + tail
    return f"fallback {k}/{n}: {why}" + tail


def _route(table: dict, b: dict, task: str | None, dry_run: bool, c: Choice) -> tuple[str, str]:
    default = b["default"]
    at = route_at(table)          # read first: a broken table must cost no call
    tag = f"question {question_hash(b)}"
    if dry_run or not task:
        return default, f"default: route not asked ({'--dry-run' if dry_run else 'no task'}; {tag})"
    try:
        resp = jev.ask(task, question(b))
    except jev.JevError as e:
        return default, f"default: route failed, {e.kind} ({tag})"
    c.usage = resp.get("usage") or {}
    jevlog.record("route", b.get("on") or "", question_hash(b), resp)
    got = (resp.get("answers") or {}).get("route")
    f = jev.answer_fields(got) if isinstance(got, dict) else {}
    ans = f.get("choice")
    p = (f.get("probabilities") or {}).get(ans, f.get("confidence"))
    models = b["route"]["models"]
    if ans not in models or p is None:
        return default, f"default: route gave no usable answer ({tag})"
    if p < at:
        return default, f"default: route {ans} p={p:.2f} < {at:g} ({tag})"
    return models[ans], f"route {ans} p={p:.2f} ({tag})"


# --- a command's or skill's text, and the child that runs it ---------------

def _split(text: str) -> tuple[str, str]:
    """(frontmatter, body); frontmatter is empty when the file has none."""
    if not text.startswith("---"):
        return "", text
    parts = text.split("---", 2)
    return (parts[1], parts[2]) if len(parts) == 3 else ("", text)


def _field(front: str, key: str) -> str:
    m = re.search(rf"^{key}:[ \t]*(.*)$", front, re.M)
    return m.group(1).strip() if m else ""


def source_text(on: str, *, skills: pathlib.Path | None = None,
                commands: pathlib.Path | None = None) -> str:
    """The instructions a `command:` / `skill:` binding runs, or '' when there are
    none. A `mode: link` skill record holds no body: its `upstream_path` does."""
    kind, _, name = on.partition(":")
    if kind == "role":
        # 1c: a `role:` binding runs the roster's own definition, so no temp role is
        # written and `pi-agent <name>` is called as-is.
        f = role_file(name)
        return _split(f.read_text(encoding="utf-8"))[1].strip() if f else ""
    if kind == "command":
        f = (commands or COMMANDS) / f"{name}.md"
        return _split(f.read_text(encoding="utf-8"))[1].strip() if f.is_file() else ""
    if kind != "skill":
        return ""
    found = sorted((skills or SKILLS).glob(f"*/*/{name}/SKILL.md"))
    if not found:
        return ""
    front, body = _split(found[0].read_text(encoding="utf-8"))
    up = _field(front, "upstream_path")
    if _field(front, "mode") == "link" and up:
        f = pathlib.Path(up).expanduser() / "SKILL.md"
        return _split(f.read_text(encoding="utf-8"))[1].strip() if f.is_file() else ""
    return body.strip()


def expected_commands(text: str) -> list[str]:
    """The commands a command's text fences: what a `command+exit` report must cover."""
    out = []
    for block in re.findall(r"```[^\n]*\n(.*?)```", text, re.S):
        out += [_norm(ln) for ln in block.splitlines()
                if ln.strip() and not ln.lstrip().startswith("#")]
    return out


def role_file(role: str, directory: pathlib.Path = roots.SUBAGENTS) -> pathlib.Path | None:
    for p in directory.glob("*.md"):
        front, _ = _split(p.read_text(encoding="utf-8"))
        if (_field(front, "name") or p.stem) == role:
            return p
    return None


def child_role(b: dict, text: str, directory: pathlib.Path) -> str:
    """Write the bound child's role into `directory`; return its name. Tools and
    body come from the binding's `role:`; the command's or skill's text follows."""
    kind, _, name = b["on"].partition(":")
    base = role_file(b["role"])
    front, body = _split(base.read_text(encoding="utf-8"))
    agent = f"bound-{kind}-{name}"
    head = [f"name: {agent}", f"description: {b['on']}, run as a child of {b['role']}"]
    if _field(front, "tools"):
        head.append(f"tools: {_field(front, 'tools')}")
    note = (b.get("note") or "").strip()
    out = (f"---\n" + "\n".join(head) + f"\n---\n\n{body.strip()}\n\n"
           f"# The {kind} you run: {name}\n\n{text}\n" + (f"\n# Limits here\n\n{note}\n" if note else ""))
    (directory / f"{agent}.md").write_text(out, encoding="utf-8")
    return agent


def session_model(agent: str, handle: str, directory: pathlib.Path | None = None) -> tuple[str, str]:
    """(session log path, 'provider/model' of its last `model_change`), '' for each
    that is not found."""
    sid = uuid.uuid5(PI_AGENT_NS, f"{agent}:{handle}")
    logs = sorted((directory or SESSION_DIR).glob(f"*_{sid}.jsonl"))
    if not logs:
        return "", ""
    model = ""
    for line in logs[-1].read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "model_change":
            model = f"{e.get('provider')}/{e.get('modelId')}"
    return str(logs[-1]), model


# --- the contracts -----------------------------------------------------------

REF = re.compile(r"(?P<path>[\w./~+-]+\.\w+|[\w./~+-]+/[\w.+-]+):(?P<a>\d+)(?:-(?P<b>\d+))?")
# A quote may escape its own delimiter (`"a: \\"0.8\\""`): models do, live.
QUOTE = re.compile(r'"((?:[^"\\]|\\.)+)"|`((?:[^`\\]|\\.)+)`|“([^”]+)”')
ESCAPED = re.compile(r'\\(["`\\])')
URL = re.compile(r"https?://\S+")


@dataclasses.dataclass
class Verdict:
    ok: bool
    summary: str
    problems: list = dataclasses.field(default_factory=list)


def _norm(s: str) -> str:
    return " ".join(s.split())


def verify(contract: str, text: str, root: pathlib.Path, expect: list | None = None,
           task: str = "") -> Verdict:
    """Does a child's reply keep its contract? `task` is the call's own text, which
    `rewrite` needs: it looks each `kept:` quote up in the prompt being improved."""
    body = text.strip()
    if contract == "command+exit":
        return _exits(body, expect or [])
    if body.lower().rstrip(".") == NOT_FOUND:
        return Verdict(True, NOT_FOUND)
    if contract == "ref+quote":
        return _refs(body, root)
    if contract == "ref+quote+defect":
        return _refs(body, root, defect=True)
    if contract == "extract+url":
        return _extracts(body)
    if contract == "rewrite":
        return _rewrite(body, task)
    return Verdict(False, f"unknown contract {contract!r}")


DEFECT = re.compile(r"\s+(?:--|—|::)\s+(\S.*)$")


def _refs(body: str, root: pathlib.Path, defect: bool = False) -> Verdict:
    """A finding line: `path:line`, a quote, and (for `ref+quote+defect`) a clause
    after `--` naming what is wrong. The clause is what separates a citation from
    a finding, and only the checker can insist on it."""
    good, problems = 0, []
    for line in body.splitlines():
        m = REF.search(line)
        if not m:
            continue
        rest = line[m.end():]
        if rest[:1] in "`\"" and line[m.start() - 1:m.start()] == rest[:1]:
            rest = rest[1:]                      # the ref's own wrapper, not a quote
        q = QUOTE.search(rest)
        ref = m.group(0)
        if not q:
            problems.append(f"{ref}: no quote")
            continue
        quote = _norm(ESCAPED.sub(r"\1", next(g for g in q.groups() if g)))
        path = pathlib.Path(m.group("path")).expanduser()
        path = path if path.is_absolute() else root / path
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            problems.append(f"{ref}: no such file")
            continue
        a = int(m.group("a"))
        b = int(m.group("b") or a)
        window = _norm(" ".join(lines[max(a - 1 - LINE_SLACK, 0):b + LINE_SLACK]))
        if quote not in window:
            problems.append(f"{ref}: quote not at those lines")
            continue
        if defect and not DEFECT.search(rest):
            problems.append(f"{ref}: no `-- <what is wrong>` clause")
            continue
        good += 1
    total = good + len(problems)
    if total == 0:
        return Verdict(False, "no `path:line` finding", ["the contract wants path:line + quote"])
    return Verdict(not problems, f"{good} of {total} quote(s) verified", problems)


def _exits(body: str, expect: list) -> Verdict:
    """`$ <command>` then its output then `exit <n>`. The shape and the coverage are
    checked, not the truth: nothing here re-runs a command."""
    codes, cur = {}, None
    for line in body.splitlines():
        m = re.match(r"\s*\$\s+(.+?)\s*$", line)
        if m:
            cur = _norm(m.group(1))
            codes.setdefault(cur, None)
            continue
        e = re.match(r"\s*exit\s+(-?\d+)\s*$", line)
        if e and cur is not None and codes[cur] is None:
            codes[cur] = int(e.group(1))
    problems = [f"{c}: no `exit N` line" for c, v in codes.items() if v is None]
    problems += [f"{c}: not reported" for c in expect if c not in codes]
    if not codes:
        return Verdict(False, "no `$ command` line", ["the contract wants `$ cmd` then `exit N`"])
    done = sum(v is not None for v in codes.values())
    bad = [c for c, v in codes.items() if v]
    tail = f"; non-zero: {', '.join(bad)}" if bad else ""
    return Verdict(not problems, f"{done} of {len(codes)} command(s) with an exit code{tail}", problems)


def _extracts(body: str) -> Verdict:
    paras = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    good, problems = 0, []
    for n, p in enumerate(paras, 1):
        has_url, has_quote = bool(URL.search(p)), bool(QUOTE.search(p) or re.search(r"^>", p, re.M))
        if has_url and has_quote:
            good += 1
        elif has_url or has_quote:
            problems.append(f"extract {n}: no {'quote' if has_url else 'URL'}")
    if good + len(problems) == 0:
        return Verdict(False, "no extract", ["the contract wants extracts with their URL"])
    return Verdict(not problems, f"{good} of {good + len(problems)} extract(s) with URL and quote",
                   problems)


# --- rewrite (1b) -------------------------------------------------------------
#
# A prompt improver's reply is prose, so the contract can only check its SHAPE:
# the labelled analysis, one block, the preserved constraints quoted from the task,
# and the self-check. Whether the rewrite is deeper is a reading by a person; the
# measured failure this catches is the one that reading misses -- a rewrite that
# silently drops the constraint the user actually cared about.

REWRITE_LABELS = ("field", "reject", "add", "raw", "check")
REWRITE_ALL = REWRITE_LABELS + ("kept", "self")
REWRITE_WORDS = 240            # the analysis budget the role declares (measured: real
                               # replies ran 133-210; the point is a receipt a person
                               # glances at, not an essay)
REWRITE_QUOTE_WORDS = 2        # a `kept:` quote of one word proves nothing: the task is
REWRITE_QUOTE_CHARS = 10       # full of such words by accident, and `kept: "a"` passed
                               # here. A long single token (a path) is a constraint still.
LABEL_LINE = re.compile(r"^`?\s*(%s)\s*`?\s*:\s*(.*)$" % "|".join(REWRITE_ALL))


def _rewrite(body: str, task: str) -> Verdict:
    """The shape of an improver's reply. Labels are scanned in the body with the
    fenced block REMOVED, and a label owns the lines under it until the next label:
    the measured reply writes `kept:` as a heading and the quotes as bullets."""
    problems = []
    blocks = re.findall(r"```[^\n]*\n(.*?)```", body, re.S)
    if len(blocks) != 1:
        problems.append(f"{len(blocks)} fenced block(s); the rewrite is exactly one")
    elif not blocks[0].strip():
        problems.append("the fenced block is empty")
    head = body.split("```", 1)[0]
    words = len(head.split())
    if words > REWRITE_WORDS:
        problems.append(f"{words} words before the block; at most {REWRITE_WORDS}")
    sections = _sections(re.sub(r"```[^\n]*\n.*?```", "", body, flags=re.S))
    for label in REWRITE_LABELS:
        if not sections.get(label):
            problems.append(f"{label}: missing" if label not in sections
                            else f"{label}: is empty")
    kept = sections.get("kept") or []
    quoted = [ln for ln in kept if _substantial(ln)]
    if _says_none(kept):
        pass                                   # the original carried nothing to keep
    elif "kept" not in sections:
        problems.append("kept: missing; one line per constraint the rewrite preserves, "
                        "or `kept: none`")
    elif not kept:
        problems.append("kept: is empty; name a constraint the rewrite preserves, "
                        "or `kept: none`")
    elif not quoted:
        problems.append("kept: quotes nothing usable; each line quotes the original "
                        "prompt, or says `kept: none`")
    else:
        haystack = _norm(task).lower()
        invented = [ln for ln in quoted if not _quotes_in(ln, haystack)]
        if len(invented) == len(quoted):
            problems.append(f"kept: no line quotes the task; the first is {quoted[0]!r}")
        elif invented:
            problems.append(f"kept: {len(invented)} line(s) quote nothing in the task: "
                            f"{invented[0][:70]!r}")
    kept_note = "kept: none" if _says_none(kept) else f"{len(quoted)} kept line(s)"
    return Verdict(not problems,
                   f"the labelled analysis, one rewrite block, {kept_note}, "
                   f"{words} word(s) before it",
                   problems)


def _sections(body: str) -> dict:
    """`label -> [lines]`: a label's own line, then the lines under it until the next
    label. A label line with nothing after the colon keeps only the lines below it."""
    out, current = {}, None
    for raw in body.splitlines():
        line = raw.strip().lstrip("-*\u2022 ").strip()
        # The label may be wrapped in backticks with the colon INSIDE them -- `kept:`
        # alone, or `field:` systems. Unwrapped first, or the closing backtick became
        # the section's value and a label with no content read as a one-line quote.
        line = re.sub(r"^`\s*([a-z]+)\s*:\s*`", r"\1:", line)
        m = LABEL_LINE.match(line)
        if m:
            current = m.group(1)
            out[current] = [m.group(2).strip()] if m.group(2).strip() else []
            continue
        if current and line:
            out[current].append(line)
    return {k: [x for x in v if x] for k, v in out.items()}


def _quotes(line: str) -> list[str]:
    """Every quoted run in a `kept:` line, in order. The three quote styles are
    scanned INDEPENDENTLY: a stray backtick once swallowed the double-quoted run
    inside it, and a real quote read as absent."""
    runs = []
    for pattern in (r"`([^`]+)`", r"\"([^\"]+)\"", r"\u201c([^\u201d]+)\u201d"):
        runs += [m.group(1).strip() for m in re.finditer(pattern, line)]
    return [r for r in runs if r]


def _usable(q: str) -> bool:
    """A quote long enough to be the constraint rather than a word that happens to be
    in the task. Two words, or one long run: `kept: "a"` and `kept: "the"` pass a
    substring test and mean nothing, a path is one token and means something."""
    return len(q.split()) >= REWRITE_QUOTE_WORDS or len(q) >= REWRITE_QUOTE_CHARS


def _substantial(line: str) -> bool:
    """Whether a `kept:` line quotes anything usable."""
    return any(_usable(q) for q in _quotes(line))


def _says_none(lines: list[str]) -> bool:
    """`kept: none` -- the honest answer for a prompt that carried no constraint.
    Without it the improver had to dress a vacuous quote as a preserved one, and
    the contract's own summary counted it as a kept line."""
    if not lines or any(_quotes(ln) for ln in lines):
        return False
    return re.match(r"^none\b", lines[0].strip().lower()) is not None


def _quotes_in(line: str, haystack: str) -> bool:
    """Whether any usable quoted run occurs in the task, whitespace and case folded."""
    return any(_norm(q).lower() in haystack for q in _quotes(line) if _usable(q))


# --- the child ---------------------------------------------------------------

def pi_agent() -> list[str]:
    found = shutil.which("pi-agent")
    return [found] if found else [sys.executable, str(roots.ENGINE / "orchestration" / "pi-agent")]


def run(table: dict, on: str, task: str, cwd: pathlib.Path, *, env=os.environ,
        timeout: float = 900.0, out=print, err=None) -> int:
    err = err or (lambda s: print(s, file=sys.stderr))
    b = find(table, on)
    kind = on.partition(":")[0]
    if b["role"] not in roster():
        err(f"bindings: {on}: inactive: role {b['role']!r} is not in pi-agent's roster")
        return 3
    text = source_text(on) if kind in TEXT_KINDS else ""
    if kind in TEXT_KINDS and not text:
        err(f"bindings: {on}: inactive: no {kind} text")
        return 3
    c = resolve(table, on, task, cwd=cwd, env=env)
    if not c.available:
        err(f"bindings: {c.line()}")
        return 3
    shape = (table.get("contracts") or {}).get(c.contract, "")
    prompt = task or "Run it now."
    if kind == "role":
        # A roster role carries no session context (`-nc`), so the one thing it cannot
        # guess -- which tree the prompt is about -- is prepended, and nothing else.
        prompt = f"Working directory: {cwd}\n\n{prompt}"
    if c.contract in SHAPE_CONTRACTS:
        prompt += f"\n\nReturn only this: {shape}"
    agent, handle, extra = b["role"], "", {}
    with tempfile.TemporaryDirectory(prefix="bindings-") as tmp:
        if kind in CHILD_KINDS:
            agent = child_role(b, text, pathlib.Path(tmp))
            handle = f"{int(time.time())}-{os.getpid()}"   # one call, one session log
            extra = {"PI_AGENT_DIR": tmp}
        cmd = [*pi_agent(), agent, prompt,
               "--model", c.model, "--cwd", str(cwd), "--timeout", str(timeout)]
        if kind == "role" and c.effort:
            # `--effort` WINS over the role's own level (pi-agent:199), so passing it is
            # what makes the binding's `effort:` the level this call runs at. Without it
            # the `binding:` line names a level the child never applied, and the role
            # file's frontmatter silently governed a call the receipt claims to describe.
            # Only for this kind: a `command:`/`skill:` child's temp role carries no
            # effort at all (`child_role`), so handing those four bindings a real level
            # is a change to their cost, and that is a decision of its own.
            cmd += ["--effort", c.effort]
        if handle:
            cmd += ["--session", handle]
        proc = subprocess.run(cmd, capture_output=True, text=True, env={**env, **extra},
                              stdin=subprocess.DEVNULL)   # see pi-agent: an inherited pipe hangs `pi -p`
    if proc.returncode != 0:
        err(proc.stderr.strip() or f"bindings: child exited {proc.returncode}")
        return proc.returncode
    v = verify(c.contract, proc.stdout, cwd,
               expected_commands(text) if c.contract == "command+exit" else None,
               task=task)
    out(proc.stdout.rstrip())
    out("")
    log = ""
    if handle:
        path, model = session_model(agent, handle)
        log = f"; session {path} names {model}" if path else "; session log not found"
    out(f"binding: {c.line()}; contract {'kept' if v.ok else 'BROKEN'}: {v.summary}{log}")
    for p in v.problems:
        out(f"  {p}")
    return 0 if v.ok else 4


def tools(table: dict, roles: set) -> list[dict]:
    """The active `tool:` bindings, for the pi extension to register."""
    return [{"name": b["on"].split(":", 1)[1], "on": b["on"], "contract": b["contract"],
             "description": (table.get("contracts") or {}).get(b["contract"], "")}
            for b in table.get("bindings") or []
            if b.get("on", "").startswith("tool:") and b.get("role") in roles]


def commands(table: dict, roles: set) -> list[dict]:
    """The active `command:` and `skill:` bindings, for the pi extension to register
    as `/<name>` (a command) and `/bound-<name>` (a skill)."""
    out = []
    for b in table.get("bindings") or []:
        kind, _, name = b.get("on", "").partition(":")
        if kind in CHILD_KINDS and b.get("role") in roles and source_text(b["on"]):
            out.append({"command": name if kind == "command" else f"bound-{name}",
                        "on": b["on"], "contract": b["contract"],
                        "description": f"{b['on']}: runs as a child on {b['model']}"})
    return out


# --- 6d: what the two logs say about the model a binding names ------------------
#
# THE BINDINGS ARE A DECISION MADE ONCE AND NEVER REVISITED. `bindings.yaml` names a
# model per binding from judgement (decision 17), and nothing has ever read the
# record back to ask whether that name is still the one to use. Two logs now exist
# that can answer a narrow version of that question: 3f's `labels.jsonl` (for one
# item: which model ran, whether its verify passed FIRST time) and 5c's
# `delegations.jsonl` (for one delegation: which role, which model, how much it read
# against what it returned). This is the analysis; the nightly pass runs it and the
# proposal lands in its brief (`consolidation/stages/bindings.py`). NOTHING HERE
# WRITES `bindings.yaml` -- an unratified model change is exactly the silent
# downgrade decision 25 forbids.
#
# WHAT COUNTS AS EVIDENCE, and each threshold is a floor on a count, never a score:
#   MIN_LABELS 3    one or two items cannot separate two models; a rate needs a
#                   population, and 3 is the smallest count where one item is a
#                   third rather than the whole answer.
#   MIN_PASS 0.75   a model is judged USEABLE when three of four of its labelled
#                   items pass first time. Below that it is not an alternative.
#   SHARED labels are excluded from the rate and counted for nothing here: a cell
#                   that ran several items shares one verifier (`labels.py`), so
#                   its pass says nothing about the item.
#   THE PRICE IS PART OF THE EVIDENCE, NOT A VETO. The alternative is the judged
#                   model with the LOWEST list price (`cheapest`'s own weights),
#                   ties to the more-labelled one, and the proposal names the ratio
#                   -- including when it is dearer. Refusing a dearer alternative
#                   here would hide exactly the trade a person has to ratify, and
#                   an unjudged model behind a binding is a claim nobody checked.
#   DELEGATIONS are REPORTED BESIDE the rate, never in it: compression measures
#                   bytes read against bytes returned, which is a size, not a
#                   correctness. A role's median compression tells the reader what
#                   the binding was doing; it cannot choose a model.

MIN_LABELS = 3
MIN_PASS = 0.75


def model_of(ran: str) -> str:
    """The catalogue id a label's or a delegation's model names.

    `ran_model` is what pi ran (`deepseek/deepseek-flash`), the catalogue is keyed
    by the vendor's id, so a provider prefix is stripped -- and only that: an id
    that already matches is returned unchanged.
    """
    return ran.split("/", 1)[-1] if ran else ""


def evidence(labels: list, delegations: list, tasks: dict | None = None,
             calibration: list | None = None, classes: dict | None = None,
             cascade: list | None = None) -> dict:
    """{"models": {id: row}, "by_class": {(id, class): row}, "roles": {(role, id): row}}.

    Both logs are read as written, with no join to the catalogue: a model the
    catalogue does not know still has a rate, and the caller can decide whether
    that matters.

    THE GRAIN IS THE ITEM, AS IT IS IN 3f (`labels.report`): only `attempt == 1`
    rows count, because a rerun and a second `verify:` are not new items, and one
    item that was checked twice must not count twice. `deepseek-flash` and
    `deepseek/deepseek-flash` are merged because a binding names a catalogue id.

    BY CLASS (14h). `by_class` keys each row by `labels.class_of` -- the row's
    class, dispatch's probe choice, or the eval task's -- and a proposal reads only
    that table: 6d once proposed a code-review model on 14/17 IMPLEMENTATION items.
    `models` (every class summed) stays for the report's context and decides nothing.
    `by_class` also counts what the router's posterior counts (14f) -- a 12c
    calibration attempt (own, passed when every answer is correct) in `read`, and a
    delegation with `used` in its role's class -- so 6d and 14g read one record.
    """
    from orchestration import labels as _labels                      # noqa: PLC0415
    tasks = tasks if tasks is not None else _labels.eval_task_classes()
    models: dict = {}
    by_class: dict = {}
    for r in labels:
        mid = model_of(str(r.get("ran_model") or ""))
        if not mid or r.get("attempt") != 1:
            continue
        klass = _labels.class_of(r, tasks)
        rows = [models.setdefault(mid, {"labels": 0, "own": 0, "passed": 0})]
        if klass:
            rows.append(by_class.setdefault((mid, klass), {"labels": 0, "own": 0, "passed": 0}))
        for row in rows:
            row["labels"] += 1
            if r.get("verdict") == "own":
                row["own"] += 1
                row["passed"] += 1 if r.get("passed") else 0
    def count(mid: str, klass: str, ok: bool) -> None:
        row = by_class.setdefault((mid, klass), {"labels": 0, "own": 0, "passed": 0})
        row["labels"] += 1
        row["own"] += 1
        row["passed"] += 1 if ok else 0
    for r in calibration or []:
        if r.get("ran") is False or not r.get("total"):
            continue
        from orchestration import posterior as _post                 # noqa: PLC0415
        count(model_of(str(r.get("model") or "")), "read", _post.calibration_ok(r))
    for r in cascade or []:
        if r.get("class"):
            count(model_of(str(r.get("model") or "")), str(r["class"]), bool(r.get("ok")))
    if classes is None:
        from orchestration import costs as _costs                    # noqa: PLC0415
        classes = _costs.role_classes()
    roles: dict = {}
    for r in delegations:
        mid = model_of(str(r.get("model") or ""))
        if not mid:
            continue
        if r.get("used") is not None and str(r.get("role")) in classes:
            count(mid, classes[str(r["role"])], bool(r["used"]))
        row = roles.setdefault((str(r.get("role") or ""), mid),
                               {"calls": 0, "compression": [], "used": 0})
        row["calls"] += 1
        row["used"] += 1 if r.get("used") is True else 0
        if r.get("compression") is not None:
            row["compression"].append(float(r["compression"]))
    for row in roles.values():
        sizes = sorted(row.pop("compression"))
        row["median_compression"] = sizes[len(sizes) // 2] if sizes else None
    return {"models": models, "by_class": by_class, "roles": roles}


def rate(row: dict) -> float:
    """First-pass rate over a model's OWN-verdict labels (0.0 when it has none)."""
    return (row.get("passed", 0) / row["own"]) if row.get("own") else 0.0


def judged(row: dict | None) -> bool:
    """Whether a model's rate is evidence: enough own-verdict labels, above MIN_PASS."""
    return bool(row) and row.get("own", 0) >= MIN_LABELS and rate(row) >= MIN_PASS


def price(cat: dict, model_id: str, usage: dict | None = None, klass: str = "") -> float:
    """A model's $ over the binding's class's reference usage (14c), or 0.0 when it
    is uncatalogued."""
    from orchestration import price as _price, dispatch as _dispatch   # noqa: PLC0415
    if usage is None:
        usage = _price.reference_usage(
            _dispatch.load_config(models_mod.load_capabilities())["rules"], klass)
    return _price.reference(model_id, usage, cat)


def proposal_for(table: dict, cat: dict, ev: dict, classes: dict | None = None) -> tuple:
    """(the proposals, the notes) for every binding whose model its CLASS's record
    judges poorly (14h).

    A binding's class is its role's `class:` (`costs.role_classes`). It is proposed
    for a change only when its model is FAILING in that class -- at least
    MIN_LABELS own-verdict labels there, under MIN_PASS -- and another model IS
    judged in the same class; the alternative is the cheapest judged one at the
    class's reference usage, and the proposal carries both rates and the price
    ratio for the user to ratify. An UNJUDGED model (fewer than MIN_LABELS in its
    class) gets a note, not a proposal: no evidence is a reason to collect some
    (a calibration slot, or the role's `model: class` under 14g's exploration),
    not to swap on another class's numbers. `model: route` is skipped with a note:
    routing decides per call (decision 17).
    """
    if classes is None:
        from orchestration import costs as _costs                    # noqa: PLC0415
        classes = _costs.role_classes()
    by_class, roles = ev["by_class"], ev["roles"]
    proposals, notes = [], []
    for b in active(table):
        on, mid, role = b["on"], str(b.get("model") or "").strip(), b["role"]
        if mid == "route":
            notes.append(f"{on}: `model: route` -- the call decides, nothing to propose")
            continue
        klass = classes.get(role, "")
        if not klass:
            notes.append(f"{on}: role {role} declares no class, so no record judges it")
            continue
        row = by_class.get((mid, klass))
        if judged(row):
            notes.append(f"{on}: {mid} judged in {klass} -- {row['passed']}/{row['own']} "
                         f"first-pass, nothing to propose")
            continue
        own = (row or {}).get("own", 0)
        if own < MIN_LABELS:
            notes.append(f"{on}: {mid} is unjudged in {klass} ({own} own verdict(s)); "
                         f"no proposal -- a calibration slot or `model: class` would collect "
                         f"{klass}'s evidence")
            continue
        better = [(m, r) for (m, k), r in by_class.items()
                  if k == klass and m != mid and judged(r)]
        if not better:
            notes.append(f"{on}: {mid} fails in {klass} ({row['passed']}/{own}), and no "
                         f"model the {klass} record judges is available -- nothing to propose")
            continue
        cap = price(cat, mid, klass=klass)
        alt, alt_row = min(better, key=lambda x: (price(cat, x[0], klass=klass), -x[1]["own"]))
        seen = roles.get((role, alt)) or roles.get((role, mid)) or {}
        to = price(cat, alt, klass=klass)
        proposals.append({
            "on": on, "role": role, "class": klass, "model": mid, "to": alt,
            "labels": {"own": own, "passed": row.get("passed", 0)},
            "alternative": {"own": alt_row["own"], "passed": alt_row["passed"],
                            "rate": round(rate(alt_row), 3)},
            "delegations": {"calls": seen.get("calls", 0),
                            "median_compression": seen.get("median_compression"),
                            "used": seen.get("used", 0)},
            "price": {"model": cap, "to": to, "ratio": round(to / cap, 3) if cap else None},
        })
    return proposals, notes


def active(table: dict) -> list:
    """Every binding row in the table, in declaration order.

    One list under `bindings:`, each row naming its own kind in `on:`
    (`tool:`, `command:`, `skill:`), which is how `tools()` and `commands()`
    read it too.
    """
    return [b for b in (table.get("bindings") or [])
            if isinstance(b, dict) and b.get("on")]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="familiar orchestration bindings",
                                 description="Who does a tool's, command's or skill's work.")
    ap.add_argument("--check", action="store_true", help="validate bindings.yaml, offline")
    ap.add_argument("--resolve", metavar="ON", help="which model runs ON (e.g. tool:explore)")
    ap.add_argument("--task", help="with --resolve: the call's text, so a routed binding asks Jev")
    ap.add_argument("--dry-run", action="store_true", help="with --resolve: never ask Jev")
    ap.add_argument("--tools-json", action="store_true",
                    help="the active tool bindings as JSON (the pi extension reads it)")
    ap.add_argument("--commands-json", action="store_true",
                    help="the active command and skill bindings as JSON (the pi extension reads it)")
    ap.add_argument("verb", nargs="?", choices=["run"], help="run ON TASK: spawn the bound child")
    ap.add_argument("args", nargs="*", help="ON TASK for run")
    ap.add_argument("--cwd", type=pathlib.Path, default=pathlib.Path.cwd())
    ap.add_argument("--timeout", type=float, default=900.0)
    a = ap.parse_args(argv)
    try:
        table = load()
        cat = _miniyaml.load(CATALOGUE.read_text(encoding="utf-8"))
        if a.check:
            found, inactive = check(table, cat, roster())
            for line in found + inactive:
                print(line)
            n = len(table.get("bindings") or [])
            print(f"bindings --check: {n} binding(s), {len(found)} finding(s), "
                  f"{len(inactive)} inactive")
            return 1 if found else 0
        if a.tools_json:
            print(json.dumps(tools(table, roster())))
            return 0
        if a.commands_json:
            print(json.dumps(commands(table, roster())))
            return 0
        if a.resolve:
            c = resolve(table, a.resolve, a.task, dry_run=a.dry_run, cat=cat)
            print(c.line())
            return 0 if c.available else 3
        if a.verb == "run":
            if len(a.args) != 2:
                ap.error("run takes ON TASK")
            return run(table, a.args[0], a.args[1], a.cwd, timeout=a.timeout)
    except (BindingError, profiles.ProfileError, _miniyaml.YamlError, OSError) as e:
        print(f"bindings: {e}", file=sys.stderr)
        return 2
    ap.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
