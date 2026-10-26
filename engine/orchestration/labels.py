"""labels -- one outcome label per SPECS item (item 3f, option C, the user's 2026-10-15).

WHY. 3c's thresholds (when Jev's suggestion may override a declared model), the
catalogue's `pass_rate` per class (decision 21) and 6d's binding proposals all need
the same fact: for one item, which model was declared, which was suggested, which
ran, what it cost, and whether its `verify:` passed the FIRST time. Until >= 30
items carry that, every threshold stays advisory.

THE GRAIN IS THE ITEM (option C). Two sources write the same row shape to
`<PAZRAS_DATA_DIR>/labels.jsonl`:
  eval    4e's rows, seeded once (`--seed-eval`): every coding cell of the
          baseline and dispatch arms, one label per item it ran. A cell that ran
          several items shares one verifier, so its labels carry
          `verdict: shared` -- usable for cost, not for a per-item pass rate.
          An eval rerun is an independent run, not a retry, so its label has
          `attempt: 1` and `rerun: <the row's attempt>`.
  verify  live work: `familiar orchestration verify <SPECS.md> <id>` runs the
          item's own `verify:` command and appends a label with its attempt
          number, so "passed first time" is a count rather than a recollection.
          A `manual:` verify cannot be run and is refused (exit 2).

THE ROW: ts, source, specs, item, declared, suggested, ran_model, effort, usage
(pools + frontier), attempt, passed, first_pass, verdict (own|shared), session,
probes_hash, probes. `suggested` is null until a dispatch audit is joined; the probe
wording `573fa7aa191cd6b0` (3c) is the baseline a suggestion is valid under.
`probes` (2026-10-19) is the item's newest dispatch answers from `jevlog`, with
their probabilities and their own wording hash, or null when the item was never
probed: the join a fitted threshold needs (`jevlog`'s docstring says why).

THE REPORT (`--report`) prints the distribution before anything moves: labels by
source and verdict, first-pass rate per ran model, and whether the >= 30 bar is
met. Nothing here writes `models.yaml`; a `pass_rate` is proposed from the report,
never applied by it.

EXIT CODES. 0 done (verify: the verify passed). 1 the verify failed. 2 usage, an
unknown item, or a manual verify.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import os
import pathlib
import subprocess
import sys

from lib import roots
from orchestration import jevlog, profiles, specs
from orchestration.eval import POOLS, log_model, read_usage

LABELS_NAME = "labels.jsonl"
EVAL_ROWS = "orchestration-eval.jsonl"
PROBES_HASH = "573fa7aa191cd6b0"
THRESHOLD_N = 30
SESSIONS = pathlib.Path.home() / ".pi/agent/sessions"


def labels_path(env=os.environ) -> pathlib.Path:
    return profiles.data_dir(env) / LABELS_NAME


def read(path: pathlib.Path) -> list:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if isinstance(o, dict):
            out.append(o)
    return out


def append(rows: list, path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")


def _pools(usage: dict) -> dict:
    p = {k: int((usage or {}).get(k, 0)) for k in POOLS}
    p["frontier"] = sum(p[k] for k in POOLS if k != "cache_read")
    return p


def label(*, source, specs_path, item, declared, ran_model, effort, usage, attempt,
          passed, verdict, session="", suggested=None, ts=None, rerun=None,
          probes=None, task_class="") -> dict:
    return {
        "rerun": rerun,
        "ts": ts or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "source": source, "specs": specs_path, "item": item,
        "declared": declared, "suggested": suggested, "ran_model": ran_model,
        "effort": effort or "", "usage": _pools(usage), "attempt": attempt,
        "passed": bool(passed), "first_pass": bool(passed) and attempt == 1,
        "verdict": verdict, "session": session, "probes_hash": PROBES_HASH,
        "probes": probes, "class": task_class or class_of({"probes": probes}),
    }


# --- 14f: the class a label belongs to -----------------------------------------

def class_of(row: dict, tasks: dict | None = None) -> str:
    """The class a label's evidence counts for, or '' when nothing says.

    In order: the row's own `class` (written since 14f); the class dispatch's
    probe chose for the item (`probes.answers.task_class.choice`, the same answer
    the router acted on); for an eval label, the eval task's kind's class
    (`eval:<task>:<arm>`). Read at the time of use rather than rewritten into the
    log, so the 65 rows written before 14f keep their bytes. A row none of the
    three can place is UNCLASSED and enters no class's evidence -- crossing classes
    is what 14f exists to stop.
    """
    if row.get("class"):
        return str(row["class"])
    answers = ((row.get("probes") or {}).get("answers") or {})
    choice = (answers.get("task_class") or {}).get("choice")
    if choice:
        return str(choice)
    spec = str(row.get("specs") or "")
    if spec.startswith("eval:"):
        if tasks is None:
            tasks = eval_task_classes()
        return tasks.get(spec.split(":")[1], "")
    return ""


def eval_task_classes() -> dict:
    """{eval task id: its class}, or {} when the task set cannot be read."""
    from orchestration import eval as eval_mod                       # noqa: PLC0415
    try:
        return {t.id: t.task_class for t in eval_mod.load()}
    except Exception:                       # noqa: BLE001 -- a broken task is eval's finding
        return {}


# --- the eval seed -----------------------------------------------------------

def from_eval(rows: list) -> list:
    """One label per item per coding cell of the baseline, dispatch and model arms.
    The baseline ran every item on its one model; the dispatch arm's items say what
    each was given and whether it was declared; the model arm (2026-10-23) is one
    whole-prompt cell on the model `--model` named, so its single item carries it."""
    out = []
    for r in rows:
        if r.get("kind") != "coding" or r.get("arm") not in ("baseline", "dispatch", "model"):
            continue
        items = r.get("items") or []
        if not items:
            continue
        shared = "shared" if len(items) > 1 else "own"
        for it in items:
            declared = it.get("model") if it.get("source") == "declared" else None
            ran = (r.get("ran_model") or it.get("model")
                   if r["arm"] in ("baseline", "model") or len(items) == 1
                   else it.get("model"))
            out.append(label(
                source="eval", specs_path=f"eval:{r['task']}:{r['arm']}", item=it.get("id"),
                declared=declared, ran_model=ran, effort=it.get("effort") or r.get("effort"),
                usage=r.get("usage") if len(items) == 1 else {}, attempt=1,
                rerun=r.get("attempt", 1),
                passed=(r.get("verifier") or {}).get("pass"), verdict=shared, ts=r.get("ts")))
    return out


def _eval_key(row: dict) -> tuple:
    """What makes one eval label the same label: the cell it came from, its item
    and the row's timestamp. A rerun has a new ts, so it is a new label; a second
    seed over the same rows has none."""
    return (str(row.get("specs") or row.get("specs_path") or ""), str(row.get("item") or ""),
            str(row.get("ts") or ""))


def seed(rows_path: pathlib.Path, path: pathlib.Path) -> int:
    """Seed the rows not yet labelled, and only those.

    ONE-SHOT WAS TOO STRICT (changed 2026-10-23): the rule exists so a second seed
    does not double every label, but a run that adds cells -- the model arm
    measuring a new model -- would have written rows nothing could ever read. The
    key is (cell, item, ts), so the same rows seed nothing and new cells append.
    """
    have = {_eval_key(r) for r in read(path) if r.get("source") == "eval"}
    new = [l for l in from_eval(read(rows_path)) if _eval_key(l) not in have]
    append(new, path)
    return len(new)


# --- the live source -----------------------------------------------------------

def newest_session(root: pathlib.Path = SESSIONS):
    found = [p for p in root.glob("*/*.jsonl") if p.parent.name != "pi-agent"]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def verify(specs_file: pathlib.Path, item_id: str, *, path: pathlib.Path, ran=None,
           session=None, cwd: pathlib.Path = roots.REPO, run=subprocess.run, out=print,
           effort: str = "", task_class: str = "", ladder=None,
           answers_log: pathlib.Path | None = None) -> int:
    text = specs_file.read_text(encoding="utf-8")
    items = {i.id: i for i in specs.parse(text, ("verify", "model", "touches", "depends"))}
    it = items.get(item_id)
    if it is None:
        out(f"verify: no item {item_id!r} in {specs_file}")
        return 2
    cmd = it.fields.get("verify", "")
    if not cmd or cmd.startswith("manual"):
        out(f"verify: {item_id}: the verify is {cmd or 'missing'!r} and cannot be run; "
            f"no label is written")
        return 2
    rel = str(specs_file.resolve().relative_to(cwd)) if specs_file.resolve().is_relative_to(cwd) \
        else str(specs_file)
    attempt = 1 + sum(1 for r in read(path)
                      if r.get("source") == "verify" and r.get("specs") == rel and r.get("item") == item_id)
    p = run(["bash", "-c", cmd], cwd=str(cwd), capture_output=True, text=True)
    sess = pathlib.Path(session) if session else newest_session()
    usage = read_usage([sess]) if sess else {}
    ran_model = ran or (log_model([sess]) if sess else "")
    declared = it.fields.get("model") or None
    probed = jevlog.latest("dispatch", f"{rel}#{item_id}", answers_log)
    probes = None if probed is None else {k: probed.get(k) for k in ("ts", "question_hash", "answers")}
    append([label(source="verify", specs_path=rel, item=item_id,
                  declared=None if declared == "user" else declared,
                  ran_model=ran_model, effort=effort, usage=usage, attempt=attempt,
                  passed=p.returncode == 0, verdict="own", session=str(sess or ""),
                  probes=probes, task_class=task_class)], path)
    tail = (p.stdout + p.stderr).strip().splitlines()[-3:]
    for line in tail:
        out(f"  {line}")
    out(f"verify: {rel} {item_id} attempt {attempt}: {'PASS' if p.returncode == 0 else 'FAIL'} "
        f"(exit {p.returncode}); ran {ran_model or '?'}; label -> {path}")
    if p.returncode != 0:                      # 8b: the verifier is the detector
        out((ladder or _ladder)(history_of(read(path), rel, item_id), task_class or "unknown"))
    return 0 if p.returncode == 0 else 1


def history_of(rows: list, rel: str, item_id: str) -> list:
    from orchestration import escalation                              # noqa: PLC0415
    return escalation.history(rows, rel, item_id)


def _ladder(hist: list, task_class: str) -> str:
    from orchestration import escalation, selection as sel_mod        # noqa: PLC0415
    sel = sel_mod.with_needs(sel_mod.load(), sel_mod._caps())
    return escalation.render(escalation.next_step(
        hist, task_class=task_class, cat=sel_mod._cat(), sel=sel,
        caps=sel_mod._caps(), rules=sel_mod._rules()))


# --- the distribution ----------------------------------------------------------

def report(rows: list, out=print) -> dict:
    items = {(r["specs"], r["item"]) for r in rows}
    own = [r for r in rows if r["verdict"] == "own"]
    by_src = collections.Counter((r["source"], r["verdict"]) for r in rows)
    firsts = collections.defaultdict(list)
    for r in own:
        if r["attempt"] == 1:
            firsts[r["ran_model"] or "?"].append(r["passed"])
    disagree = sum(1 for r in rows if r.get("declared") and r.get("suggested")
                   and r["declared"] != r["suggested"])
    met = len({(r["specs"], r["item"]) for r in own}) >= THRESHOLD_N
    out(f"labels -- {len(rows)} label(s) over {len(items)} item-run key(s)")
    out("  sources    " + ", ".join(f"{s}/{v} {n}" for (s, v), n in sorted(by_src.items())))
    out("  first try  (own verdicts only; a shared verifier says nothing per item)")
    for m, xs in sorted(firsts.items()):
        out(f"    {m:36} {sum(xs)}/{len(xs)} passed first time")
    out(f"  declared vs suggested  {disagree} disagreement(s); "
        f"{sum(1 for r in rows if r.get('suggested'))} label(s) carry a suggestion")
    out(f"  bar        {len({(r['specs'], r['item']) for r in own})} own-verdict item(s) of "
        f"{THRESHOLD_N}: " + ("met -- a threshold may now be proposed from this table"
                              if met else "not met -- every threshold stays advisory"))
    tasks = eval_task_classes()
    by_class = collections.Counter(class_of(r, tasks) or "unclassed" for r in rows)
    out("  class      " + ", ".join(f"{k} {n}" for k, n in sorted(by_class.items()))
        + "  (14f: a label counts only for its own class)")
    unplaced = sorted({f"{r['specs']}#{r['item']}" for r in rows if not class_of(r, tasks)})
    if unplaced:
        out(f"  unclassed  {len(unplaced)} item(s), no probe answer and no class: "
            + ", ".join(unplaced))
    return {"labels": len(rows), "met": met, "classes": dict(by_class)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="familiar orchestration labels",
                                 description="Per-item outcome labels (3f): seed from 4e, "
                                             "print the distribution.")
    ap.add_argument("--seed-eval", action="store_true", help="seed once from 4e's rows")
    ap.add_argument("--report", action="store_true", help="the distribution (default)")
    ap.add_argument("--labels", type=pathlib.Path, default=None)
    ap.add_argument("--rows", type=pathlib.Path, default=None)
    args = ap.parse_args(argv)
    path = args.labels or labels_path()
    if args.seed_eval:
        n = seed(args.rows or profiles.data_dir() / EVAL_ROWS, path)
        print(f"labels: {n} eval label(s) seeded" if n else "labels: already seeded; nothing written")
    report(read(path))
    return 0


def verify_main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="familiar orchestration verify",
                                 description="Run one item's verify: and label the outcome (3f).")
    ap.add_argument("specs_file", type=pathlib.Path)
    ap.add_argument("item")
    ap.add_argument("--ran", help="the model that did the work (default: the newest pi session's)")
    ap.add_argument("--session", help="the session log to read usage and model from")
    ap.add_argument("--effort", default="", help="the effort level the work ran at")
    ap.add_argument("--class", dest="task_class", default="",
                    help="the item's class, for the escalation ladder (default: unknown)")
    ap.add_argument("--labels", type=pathlib.Path, default=None)
    args = ap.parse_args(argv)
    if not args.specs_file.is_file():
        print(f"verify: no file {args.specs_file}", file=sys.stderr)
        return 2
    return verify(args.specs_file, args.item, path=args.labels or labels_path(),
                  ran=args.ran, session=args.session, effort=args.effort,
                  task_class=args.task_class)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
