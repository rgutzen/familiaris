"""A deliberately small YAML reader for BOUNDARIES.yaml and the ontology registers.

This is NOT a YAML implementation. It understands exactly the subset that
the boundary registers (`config/boundaries/*.yaml`) use and raises on anything
else, which is the point:
a config that quietly means something other than it looks like is worse than
one that refuses to load.

PROMOTED to `engine/lib/` on 2026-09-30, when `config/knowledge/*.yaml` became
its second caller: one parser for one subset, not two copies that can drift
(the `generated_block.py` precedent). The subset was NOT extended for it --
the register files are constrained to what is read below, and
`engine/knowledge/tests/test_ontology.py` asserts both that every register file
loads here and that this module's surface has not grown.

Supported:  top-level mappings, nested mappings, block sequences of scalars,
            block sequences of mappings, folded (`>`) scalars, `#` comments.
Rejected:   flow collections, anchors, multi-doc, tags, `|` literals, quoting
            subtleties beyond a single surrounding pair.

Why not PyYAML: the Claude Code hook that consumes boundaries data must have no
import that can go missing mid-session, and it is absent from
`~/.local/share/mise/shims/python3` -- the interpreter `familiar-memory.timer`
runs under (measured 2026-09-30). The compiler and the ontology loader parse
YAML; the hook reads the compiled JSON with the stdlib only.
"""
from __future__ import annotations


class YamlError(ValueError):
    pass


def _strip_comment(s: str) -> str:
    out, quote = [], None
    for i, ch in enumerate(s):
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
            out.append(ch)
            continue
        if ch == "#" and (i == 0 or s[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    return v


def _lines(text: str):
    """(indent, content, lineno) for every significant line."""
    out = []
    for n, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YamlError(f"line {n}: tab in indentation")
        out.append((len(raw) - len(raw.lstrip()), raw.strip(), n))
    return out


def _folded(rows, i, indent):
    """Consume a `>` block: lines indented deeper than `indent`, joined."""
    parts = []
    while i < len(rows) and rows[i][0] > indent:
        parts.append(rows[i][1])
        i += 1
    return " ".join(parts), i


def _mapping(rows, i, indent):
    out = {}
    while i < len(rows) and rows[i][0] == indent:
        col, content, n = rows[i]
        if content.startswith("- "):
            break
        if ":" not in content:
            raise YamlError(f"line {n}: expected `key: value`, got {content!r}")
        key, _, rest = content.partition(":")
        key, rest = key.strip(), _strip_comment(rest).strip()
        i += 1
        if rest in (">", ">-"):
            out[key], i = _folded(rows, i, col)
        elif rest == "":
            if i < len(rows) and rows[i][0] > col:
                out[key], i = _value(rows, i, rows[i][0])
            else:
                out[key] = None
        else:
            out[key] = _unquote(rest)
    return out, i


def _sequence(rows, i, indent):
    out = []
    while i < len(rows) and rows[i][0] == indent and rows[i][1].startswith("- "):
        col, content, n = rows[i]
        item = content[2:].strip()
        if ":" in item and not item.startswith(("'", '"')):
            # A mapping whose first key shares the `- ` line. Re-present it at
            # the column the key actually starts in, then parse as a mapping.
            keycol = col + 2
            rows[i] = (keycol, item, n)
            item_map, i = _mapping(rows, i, keycol)
            out.append(item_map)
        else:
            out.append(_unquote(_strip_comment(item)))
            i += 1
    return out, i


def _value(rows, i, indent):
    if rows[i][1].startswith("- "):
        return _sequence(rows, i, indent)
    return _mapping(rows, i, indent)


def load(text: str) -> dict:
    rows = _lines(text)
    if not rows:
        return {}
    value, i = _value(rows, 0, rows[0][0])
    if i != len(rows):
        raise YamlError(f"line {rows[i][2]}: unparsed trailing content {rows[i][1]!r}")
    if not isinstance(value, dict):
        raise YamlError("top level must be a mapping")
    return value
