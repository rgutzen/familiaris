"""land -- "Land it" becomes one scheduled session that writes the decisions down (dev/remote R6e).

WHY A MODEL. Stage 4 calls a decision landed when its id appears in a memory
file. WHERE it belongs -- which leaf, which SPECS line, which rationale section
-- is a judgement over the tree, so landing is an agent's job; everything
around it is not. This module is the deterministic part: it collects what the
user said to land, drops what has landed since, writes one prompt, and queues
ONE `--ready` job through the scheduler, which applies its own conditions and
budget. One job per batch, never one per decision: each run pays the session's
fixed cost again.

THE BOOKKEEPING lives in `landing.jsonl` beside the queue: a `land` row per
decision (written by `resolve.apply`), and a `scheduled` row naming the job and
the ids it took. A decision is pending while it has a land row, no scheduled
row, and has not landed. A job that fails leaves its ids un-landed; `land
--retry` puts them back in the next batch.
"""
from __future__ import annotations

import datetime as dt
import subprocess

from consolidation import ledger, resolve
from lib import invocation, roots

SPEC = invocation.Spec(name="land", usage="land [--dry-run] [--retry]",
                       flags=("--dry-run", "--retry"))

PROMPT = """\
# Land {n} decision(s) the user confirmed from the phone

Each decision below was recorded with `familiar consolidation decision` and the
user chose "Land it" in the nightly review. A decision has LANDED when its id
appears in the memory file where a later session will look for it.

For each decision, in order:

1. Find its home: read `{index}` and follow the one leaf it
   names; for a track's decision, the track's `{dev}/<track>/SPECS.md` or
   `PLAN.md`. Prefer an existing leaf over a new one.
2. Add the decision there in the leaf's own voice (`{voice}`),
   one short paragraph, citing the id (`{example}`) so stage 4 sees it landed.
3. Commit that one file: `decisions: land <id> in <file>`.

Do not edit `{user}/**`, `{conventions}/**` or `{boundaries}/**`: those are
directive. `ROADMAP.md` is editable by a session with a human watching and
closed to you, because you have none: give it as a patch in your final message
instead. A decision that belongs there, or that has no clear home, is listed
with the place you would put it -- not invented.

## The decisions
{body}
"""


def _landed(repo, ids: set) -> set:
    """The ids that appear in a memory file outside the reports -- stage 4's rule."""
    found = set()
    agents = repo / roots.rel(roots.MEMORY)
    for f in agents.rglob("*.md"):
        if "/journal/reports/" in f.as_posix():
            continue
        try:
            txt = f.read_text()
        except OSError:
            continue
        found |= {i for i in ids - found if i in txt}
        if found == ids:
            break
    return found


def pending(base, repo, *, retry: bool = False) -> list:
    """Land rows still to schedule, oldest first, one per target."""
    rows = ledger.read(base, resolve.LANDING).rows
    taken = set()
    if not retry:
        for r in rows:
            if r.get("scheduled"):
                taken |= set(r.get("targets") or [])
    want = {}
    for r in rows:
        if r.get("target") and not r.get("scheduled") and r["target"] not in taken:
            want.setdefault(r["target"], r)
    landed = _landed(repo, set(want))
    return [r for t, r in want.items() if t not in landed]


def _text(base, target: str) -> tuple:
    """The decision's full text and context from the ledger (the queue's summary is cut)."""
    for r in ledger.read(base, ledger.DECISIONS).rows:
        if r.get("id") == target:
            return r.get("text", ""), r.get("context", "")
    return "", ""


def prompt(base, rows: list) -> str:
    body = []
    for r in rows:
        text, ctx = _text(base, r["target"])
        body.append(f"\n### {r['target']} ({r['kind']})\n\n{text or r.get('summary', '')}")
        if ctx or r.get("why"):
            body.append(f"\n*Context:* {ctx or r['why']}")
        if r.get("note"):
            body.append(f"\n*The user's note:* {r['note']}")
    return PROMPT.format(n=len(rows), example=rows[0]["target"], body="\n".join(body),
                         index=roots.rel(roots.KNOWLEDGE / "INDEX.md"),
                         dev=roots.rel(roots.DEV),
                         voice=roots.rel(roots.CONVENTIONS / "voice.md"),
                         user=roots.rel(roots.USER),
                         conventions=roots.rel(roots.CONVENTIONS),
                         boundaries=roots.rel(roots.BOUNDARIES))


def _add(argv: list) -> tuple:
    p = subprocess.run(argv, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def schedule(base, repo, *, dry_run: bool = False, retry: bool = False, run=_add) -> str:
    """Queue one landing job for every pending decision; a one-line account."""
    rows = pending(base, repo, retry=retry)
    if not rows:
        return "nothing to land"
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    name = f"land-{stamp}"
    d = base / "landing"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{name}.md"
    path.write_text(prompt(base, rows))
    argv = [str(roots.ENGINE / "familiar"), "schedule", "sessions", "add",
            "--name", name, "--ready", "--prompt", str(path), "--cwd", str(roots.REPO),
            "--commit", "per-item", "--touches",
            f"{roots.rel(roots.MEMORY)}/**,{roots.rel(roots.DEV)}/**"]
    if dry_run:
        argv.append("--dry-run")
    code, out = run(argv)
    if code:
        return f"landing job not scheduled ({out.splitlines()[-1][:160] if out else code})"
    if not dry_run:
        ledger.append(base, resolve.LANDING, {"ts": stamp, "scheduled": name,
                                              "targets": [r["target"] for r in rows]})
    return (f"{'would schedule' if dry_run else 'scheduled'} {name}: "
            f"{len(rows)} decision(s) to land")


def main(inv) -> int:
    msg = schedule(inv.base, inv.agents.parent, dry_run=inv.has("--dry-run"),
                   retry=inv.has("--retry"))
    print(msg)
    return 1 if msg.startswith("landing job not") else 0
