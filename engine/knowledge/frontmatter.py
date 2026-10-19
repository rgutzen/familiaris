"""frontmatter — read and surgically rewrite the leaf/skill frontmatter dialect.

The dialect (memory/knowledge/_leaf-template.md) is flat `key: value` with
`[a, b]` flow lists, `#` trailing comments, and lists that may wrap across
lines. It is NOT YAML, and there is no PyYAML on this machine -- the pass runs
from a systemd timer and must not depend on an import that can go missing.

WHY WRITES ARE LINE-SURGICAL, NOT A ROUND-TRIP
M1's provenance backfill put resolvable session ids and commit hashes in
trailing `# comments`:

    promoted_from: []   # 06_SYSTEM session 2026-08-29, commit 186c643; no journal entry

A parse-then-reserialise cycle destroys those, and they cannot be
reconstructed. So `set_scalar`/`set_list` locate the physical line span for one
key and replace only the value, leaving key order, comments, blank lines and
every other byte untouched. Everything not named in the edit is copied through.
"""
from __future__ import annotations

import pathlib
import re

from lib import roots

FM_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)
KEY_RE = re.compile(r"^([a-z_]+):(.*)$")

# -- promotion is human-gated (memory/knowledge/system/consolidation/memory-poisoning-posture.md) -----------------------------------
# `trust:` decides whether a claim is read as established or as provisional.
# Every OTHER trust transition this system performs is a DEMOTION -- stage 5d
# marks a superseded leaf `deprecated`, stage 6 proposes one step down -- and a
# demotion is safe to automate because its worst case is a true claim read with
# too much caution. Promotion is the opposite: it takes text no human has
# ratified and re-labels it as ratified, which is exactly the step that turns a
# one-shot injection into a standing belief.
#
# So it is refused HERE, at the single write path every stage goes through,
# rather than asked for in each stage's prose. A stage that tries it raises,
# the per-stage guard in `run` catches it, and the report names the attempt --
# an attempted promotion is a finding, not a silent no-op.
# Detail: memory/knowledge/system/consolidation/memory-poisoning-posture.md.
PROMOTED_TRUST = ("trusted",)


class PromotionRefused(PermissionError):
    """A stage tried to write a `trust:` value only a human may set."""


def split_list(inner: str) -> list[str]:
    """Split a flow-list body on commas, honouring quotes.

    Trigger phrases and scope globs legitimately contain commas; a naive
    `.split(",")` silently shreds them into fragments. (Bug found the hard way
    in M1 -- keep this.)
    """
    items, cur, quote = [], "", ""
    for ch in inner:
        if quote:
            if ch == quote:
                quote = ""
            else:
                cur += ch
        elif ch in "\"'":
            quote = ch
        elif ch == ",":
            items.append(cur)
            cur = ""
        else:
            cur += ch
    items.append(cur)
    return [i.strip() for i in items if i.strip()]


def _logical_lines(fm: str) -> list[tuple[int, int, str]]:
    """(start, end, text) per logical line; a wrapped `[` list is one entry."""
    phys = fm.split("\n")
    out, buf, start = [], "", 0
    for i, line in enumerate(phys):
        if not buf:
            start = i
            buf = line
        else:
            buf = f"{buf} {line.strip()}"
        if buf.count("[") > buf.count("]"):
            continue
        out.append((start, i, buf))
        buf = ""
    if buf:
        out.append((start, len(phys) - 1, buf))
    return out


def parse(text: str) -> dict:
    """Frontmatter as a dict, plus `_body`. `{}` when there is no frontmatter."""
    m = FM_RE.match(text)
    if not m:
        return {}
    out: dict = {"_body": m.group(2)}
    for _s, _e, line in _logical_lines(m.group(1)):
        km = KEY_RE.match(line)
        if not km:
            continue
        k, v = km.group(1), km.group(2)
        v = re.sub(r"\s+#.*$", "", v).strip()          # strip trailing comment
        if v.startswith("[") and v.endswith("]"):
            out[k] = split_list(v[1:-1])
        else:
            out[k] = v
    return out


def read(path: pathlib.Path) -> dict:
    try:
        return parse(path.read_text())
    except OSError:
        return {}


def _fmt_list(values) -> str:
    def q(v: str) -> str:
        return f'"{v}"' if ("," in v or v.strip() != v) else v
    return "[" + ", ".join(q(str(v)) for v in values) + "]"


def fmt_list(values) -> str:
    """Render a list value the way this dialect writes it.

    Public because `consolidate._new_leaf_frontmatter` builds a leaf's
    frontmatter text by hand and must not disagree with the surgical writer
    about quoting -- two renderings of the same list would make an untouched
    field read as an edit.
    """
    return _fmt_list(values)


def set_fields(text: str, updates: dict) -> str:
    """Return `text` with each key in `updates` set, preserving everything else.

    A value of `None` means "leave alone". A list value is rendered as a flow
    list on ONE physical line, collapsing a wrapped one. A key that is absent is
    appended just before the closing `---`, which keeps template order for the
    keys that already exist.
    """
    m = FM_RE.match(text)
    if not m:
        raise ValueError("no frontmatter")
    want = str(updates.get("trust") or "").strip()
    if want in PROMOTED_TRUST:
        raise PromotionRefused(
            f"trust: {want} is human-gated and may not be written by the pass "
            f"({roots.MEMORY_REL}/knowledge/system/consolidation/memory-poisoning-posture.md). Demotions "
            f"and `deprecated` markings are allowed; promotion is not.")
    fm = m.group(1)
    phys = fm.split("\n")
    spans = {}
    for start, end, line in _logical_lines(fm):
        km = KEY_RE.match(line)
        if km:
            spans.setdefault(km.group(1), (start, end))

    # Rewrite existing keys back-to-front so earlier spans stay valid.
    pending = []
    for key, value in updates.items():
        if value is None:
            continue
        rendered = _fmt_list(value) if isinstance(value, (list, tuple)) else str(value)
        if key in spans:
            pending.append((spans[key], key, rendered))
        else:
            phys.append(f"{key}: {rendered}")
    for (start, end), key, rendered in sorted(pending, key=lambda p: -p[0][0]):
        comment = ""
        cm = re.search(r"(\s+#.*)$", phys[end])
        if cm:
            comment = cm.group(1)
        phys[start:end + 1] = [f"{key}: {rendered}{comment}".rstrip()]

    return "---\n" + "\n".join(phys) + "\n---\n" + m.group(2)


def update(path: pathlib.Path, updates: dict, dry_run: bool = False) -> bool:
    """Apply `set_fields` to a file. True if the bytes would change."""
    old = path.read_text()
    new = set_fields(old, updates)
    if new == old:
        return False
    if not dry_run:
        path.write_text(new)
    return True
