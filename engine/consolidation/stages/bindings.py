"""Stage 6c -- the binding proposals: what 3f's labels and 5c's delegations say
about the model a binding names (item 6d), read per class since 14h.

WHY THIS STAGE EXISTS. `bindings.yaml` names a model per binding from judgement
(decision 17), and until now nothing read the record back to ask whether that name
is still the one to use. A binding is a standing claim about which model does a
kind of work; the system now measures both halves of that claim — 3f's labels say
whether an item's verify passed FIRST time, 5c's delegations say what a role read
against what it returned — so a nightly pass can put the two together and raise a
change. It may never make one: an unratified model swap is the silent downgrade
decision 25 forbids, and this stage's entire product is a row in the queue.

PROPOSAL-ONLY, PERMANENTLY. It has no plan/apply shape and writes no file. The
analysis itself lives in `orchestration/bindings.py` (`evidence`,
`proposal_for`), where its tests are -- this module reads two logs, calls it, and
records what comes back. Keeping the arithmetic out of the pass also means the
same function can be run by hand against a synthetic log without a `Pass`.

WHAT IT READS, AND WHAT IT DOES WITH A MISSING LOG. `<PAZRAS_DATA_DIR>/
labels.jsonl` (3f) and `delegations.jsonl` (5c). A machine with neither is not a
failure: the stage says so and returns, because a pass that aborts on a young
tree reports nothing else either.

WHY EVERY BINDING IT LEAVES ALONE IS A NOTE. "No proposal" is the answer a reader
most needs to see: the alternative is a report that looks the same whether the
bindings were checked or skipped. A binding judged at 16 of 19 gets a line saying
so; `model: route` gets a line saying the call decides (decision 17); a binding
whose model has no labels but no judged alternative either gets a line saying
that. Silence is the one thing not allowed.
"""
from __future__ import annotations

import json

from orchestration import bindings, models, profiles

# The stage's own label, in the STAGES table's `6` slot: stage 6 is the
# proposal-only stage, and 6c says which of its generators spoke (`label` is 6b,
# on the precedent stage 5d set).
STAGE = "6c"

# The proposal kind. `queue`/`report` print it as written, and `decide` reads the
# report, so the word is part of what the user types back.
KIND = "binding"

# `ledger.TARGET_KINDS` is ("leaf", "opaque") and a binding is neither a knowledge
# leaf nor a file: `on` is an id (`tool:fetch`). `opaque` is the honest one, and
# its dismissal semantics (time-boxed, since there is no content to hash) are the
# right ones for a proposal that returns when the logs move.
TARGET_KIND = "opaque"


def _rows(path) -> list:
    """One JSON object per line, malformed lines dropped (the logs are appended
    by two writers and a truncated tail is not a reason to skip a night)."""
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def run(ctx) -> bool:
    data = profiles.data_dir()
    labels = _rows(data / "labels.jsonl")
    delegations = _rows(data / "delegations.jsonl")
    if not labels and not delegations:
        ctx.note(STAGE, "no 3f labels and no 5c delegations yet: nothing to read. "
                        "(Seed them with `familiar orchestration labels --seed-eval`, "
                        "and any `pi-agent` call writes a delegation line.)")
        return True
    try:
        table, cat = bindings.load(), models.load()
    except (OSError, ValueError) as e:      # a broken config is the catalogue's finding
        ctx.note(STAGE, f"bindings.yaml or the catalogue could not be read: {e}", "warn")
        return True
    ev = bindings.evidence(labels, delegations, calibration=_rows(data / "calibration.jsonl"),
                           cascade=_rows(data / "cascade.jsonl"))
    proposals, notes = bindings.proposal_for(table, cat, ev)
    for text in notes:
        ctx.note(STAGE, text)
    for p in proposals:
        alt, lbl, seen, price = p["alternative"], p["labels"], p["delegations"], p["price"]
        read = (f"role {p['role']}: {seen['calls']} delegation(s) recorded, median "
                f"compression {seen['median_compression']}"
                if seen["calls"] else f"role {p['role']}: no delegation recorded yet")
        # THE EVIDENCE GOES IN `what`, not only in `why`. `report.py` keeps row
        # text short on purpose and leaves the long `why` to `decide N --why`;
        # a binding's numbers are the decision, so the counts that justify it
        # travel in the row the brief and the report both print.
        counts = (f"{lbl['passed']}/{lbl['own']} in {p['class']} against "
                  f"{alt['passed']}/{alt['own']}, x{price['ratio']} price")
        ctx.propose(
            STAGE, KIND, p["on"],
            f"model {p['model']} -> {p['to']} ({counts})",
            f"3f, class {p['class']} only (14h): {p['model']} passed {lbl['passed']}/"
            f"{lbl['own']} first time; {p['to']} passed {alt['passed']}/{alt['own']} "
            f"({alt['rate']:.0%}). "
            f"5c: {read}. "
            f"Reference cost x{price['ratio']} (${price['model']:.4f} -> ${price['to']:.4f}, 14c). "
            f"Not applied -- this is the user's to ratify.",
            target_kind=TARGET_KIND)
    ctx.note(STAGE, f"{len(labels)} label(s) and {len(delegations)} delegation(s) read: "
                    f"{len(proposals)} binding proposal(s), "
                    f"{len(notes)} binding(s) left as they are")
    return True
