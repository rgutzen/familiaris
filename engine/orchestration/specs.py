"""specs -- read a SPECS.md into items, and check each against the contract.

THE CONTRACT IS CONTENT. `config/orchestration/specs.yaml` names the fields an
open item carries and what each value may be; this module is the binding that
reads it, the same split the ontology registers use. A field added there is
required here without a code change; a field *type* added there is refused
until this module knows how to check it, because a type nobody checks is a
promise nobody keeps.

WHAT IS NOT HERE. Whether a `model:` id exists is a catalogue question, so
`validate` takes the ids as an argument and never reads `models.yaml` itself;
`dispatch.py` joins the two. Waves, probes and Jev are step 3.
"""
from __future__ import annotations

import dataclasses
import pathlib
import re
import sys

from lib import _miniyaml
from lib import roots

CONTRACT = roots.SUBAGENTS / "specs.yaml"

# The types `specs.yaml` may name. Each has a checker in `_check_value`.
TYPES = ("paths", "ids", "model", "command", "flag")

# Every top-level checkbox is an item; only one whose bold head opens with an
# id is a well-formed one. Matching the id in the checkbox pattern instead
# would make an id-less item invisible -- and a check that cannot see an item
# passes it (found 2026-10-13: 37 open items in other tracks, all skipped).
_BOX = re.compile(r"^- \[(?P<mark>[ xX])\] (?P<rest>.*)$")
_HEAD = re.compile(r"^\*\*(?P<id>[A-Z]*\d+[a-z]*) · (?P<title>.*?)\*\*")
_FIELD = re.compile(r"^ {2,}(?P<key>[a-z_]+):\s*(?P<value>.*)$")
_ID = re.compile(r"^[A-Z]*\d+[a-z]*$")


@dataclasses.dataclass
class Item:
    id: str
    title: str
    done: bool
    line: int                                  # 1-based, the checkbox line
    has_id: bool = True                        # False: `id` is "line N", a stand-in
    fields: dict = dataclasses.field(default_factory=dict)
    duplicates: list = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class Finding:
    item: str
    field: str
    message: str
    line: int

    def __str__(self) -> str:
        return f"line {self.line}: item {self.item}: {self.field}: {self.message}"


def load_contract(path: pathlib.Path = CONTRACT) -> dict:
    data = _miniyaml.load(path.read_text(encoding="utf-8"))
    fields = data.get("fields") or {}
    for name, spec in fields.items():
        if spec.get("type") not in TYPES:
            raise ValueError(f"{path}: field {name!r} has type {spec.get('type')!r}; "
                             f"known: {', '.join(TYPES)}")
    return data


def parse(text: str, keys) -> list[Item]:
    """Every checkbox item, with the contract's field lines found under it.

    An item runs from its checkbox to the next checkbox or the next line that
    is not indented (a heading, a table, a paragraph). Only keys the contract
    names are read: prose under an item that happens to start `  note:` is
    prose, not an unknown field.
    """
    items: list[Item] = []
    cur: Item | None = None
    for n, line in enumerate(text.splitlines(), 1):
        box = _BOX.match(line)
        if box:
            head = _HEAD.match(box["rest"])
            done = box["mark"] != " "
            if head:
                cur = Item(head["id"], head["title"].rstrip(" ."), done, n)
            else:
                cur = Item(f"line {n}", box["rest"][:60], done, n, has_id=False)
            items.append(cur)
            continue
        if cur is None:
            continue
        if line.strip() and not line.startswith(" "):
            cur = None
            continue
        f = _FIELD.match(line)
        if f and f["key"] in keys:
            if f["key"] in cur.fields:
                cur.duplicates.append(f["key"])
            cur.fields[f["key"]] = f["value"].strip()
    return items


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _check_value(kind: str, value: str, contract: dict, ids: set, models) -> str | None:
    """None when `value` is a valid `kind`, else what is wrong with it."""
    if kind == "paths":
        return None if _split(value) else "names no path"
    if kind == "ids":
        if value in (contract.get("none") or []):
            return None
        parts = _split(value)
        if not parts:
            return "is empty; write — for none"
        bad = [p for p in parts if not _ID.match(p)]
        if bad:
            return f"{', '.join(bad)} is not an item id"
        missing = [p for p in parts if p not in ids]
        return f"{', '.join(missing)} is not an item in this file" if missing else None
    if kind == "model":
        if value == contract.get("user_model"):
            return None
        if models is None or value in models:
            return None
        return f"{value!r} is not a callable catalogue id or {contract.get('user_model')!r}"
    if kind == "command":
        prefix = contract.get("manual_prefix", "manual:")
        if value.startswith(prefix):
            return None if value[len(prefix):].strip() else "manual: names nothing to read"
        return None if value else "is empty"
    if kind == "flag":
        return None if value in ("yes", "no") else f"{value!r} is not yes or no"
    raise ValueError(kind)


def validate(items: list[Item], contract: dict, models=None) -> list[Finding]:
    """Findings for every open item. `models` is the set of ids `model:` may
    name; None skips that one check (the contract alone, no catalogue)."""
    fields = contract["fields"]
    ids = {it.id for it in items if it.has_id}
    out: list[Finding] = []
    seen: dict[str, int] = {}
    for it in items:
        if not it.has_id:
            if not it.done:
                out.append(Finding(it.id, "id", "no item id; the head must open "
                                   "`**<id> · <title>**`, e.g. **2a · the contract**", it.line))
            continue
        if it.id in seen:
            out.append(Finding(it.id, "id", f"also used on line {seen[it.id]}", it.line))
        seen.setdefault(it.id, it.line)
        if it.done:
            continue
        for key in it.duplicates:
            out.append(Finding(it.id, key, "given twice", it.line))
        for name, spec in fields.items():
            if name not in it.fields:
                if spec.get("required") == "yes":
                    out.append(Finding(it.id, name, "missing", it.line))
                continue
            err = _check_value(spec["type"], it.fields[name], contract, ids, models)
            if err:
                out.append(Finding(it.id, name, err, it.line))
    return out


def explain(contract: dict) -> str:
    item = contract.get("item") or {}
    lines = [f"A SPECS.md item ({CONTRACT.relative_to(roots.REPO)}):",
             f"  open      {item.get('open', '').strip()}  must carry every required field",
             f"  done      {item.get('done', '').strip()}  exempt",
             f"  id        {item.get('id', '')}",
             f"  form      {contract.get('form', '')}",
             "", "fields:"]
    for name, spec in contract["fields"].items():
        req = "required" if spec.get("required") == "yes" else "optional"
        lines.append(f"  {name + ':':<10}{spec.get('type', ''):<9}{req}")
        lines.append(f"  {'':<10}{spec.get('syntax', '')}")
        lines.append(f"  {'':<10}{spec.get('meaning', '')}")
    lines.append("")
    lines.append(f"`depends:` none = {' or '.join(contract.get('none') or [])};  "
                 f"`model:` {contract.get('user_model')} = the user's item;  "
                 f"`verify:` {contract.get('manual_prefix')} = a reading, not a command")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="familiar orchestration specs",
                                 description="The SPECS.md item contract.")
    ap.add_argument("--explain", action="store_true", help="print the contract")
    args = ap.parse_args(argv)
    if not args.explain:
        ap.print_usage(sys.stderr)
        return 1
    print(explain(load_contract()))
    return 0
