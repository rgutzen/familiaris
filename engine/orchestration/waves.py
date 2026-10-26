"""waves -- turn the open items of a SPECS.md into waves of work that may run together.

One entry point, `build(items)`, takes what `specs.parse` returns and gives a
list of waves, each a list of items in file order. Step 3c reads the waves
without parsing again. No model, no network, no clock: the same items always
yield the same waves, because the dispatch table built on them must be
reproducible.

THE RULES
  open     Only open items are scheduled. A `depends:` on a done item is
           satisfied already and adds no wave. A `depends:` on an id that is
           not in the file at all raises `UnknownDependency`, naming the id;
           `specs.validate` refuses the same typo, and this module does not
           trust that it ran first.
  order    Wave n holds the remaining items whose open dependencies all sit in
           waves before n, in file order.
  overlap  Two items overlap when a path of one is covered by a path of the
           other (below). The later item in file order leaves the wave and
           waits for the next one, where it competes again with whatever has
           become ready. Because an item only ever moves later, and its
           dependents are placed after it moves, a split cannot violate
           `depends:`.
  cycle    Raises `CycleError`, naming the items in the order the cycle runs,
           starting at the earliest in the file: `dependency cycle: 3b -> 3d -> 3b`.
           Nothing is dropped and file order is not used as a fallback.

THE PATH MATCHER (`overlaps`) is small on purpose. A `touches:` value is a
comma-separated list; `./` and `~/` prefixes are stripped. Two entries overlap
when
  - they are equal;
  - one is a literal path naming a directory above the other (`engine/x`
    covers `engine/x/y.py` and `engine/x/**`);
  - one is a glob and the other a literal that `fnmatch` matches against it;
  - both are globs and the literal directory prefixes of the two nest (the
    components before the first one holding `* ? [`).
It does not match like a shell: in `fnmatch`, `*` and `**` both cross `/`, so
`engine/*.py` also matches `engine/a/b.py`. Two globs are compared by prefix
only, so `tests/*.py` and `tests/*.md` are reported as overlapping. Every
error therefore errs towards one more wave, never towards a missed collision.
"""
from __future__ import annotations

import fnmatch

from orchestration import specs

_WILD = "*?["


class DependencyError(ValueError):
    """The depends: graph cannot be scheduled."""


class CycleError(DependencyError):
    pass


class UnknownDependency(DependencyError):
    pass


def paths(item: specs.Item) -> list[str]:
    out = []
    for p in specs._split(item.fields.get("touches", "")):
        for lead in ("~/", "./"):
            if p.startswith(lead):
                p = p[len(lead):]
        out.append(p.rstrip("/") or p)
    return out


def _is_glob(p: str) -> bool:
    return any(c in p for c in _WILD)


def _prefix(p: str) -> str:
    keep = []
    for part in p.split("/"):
        if _is_glob(part):
            break
        keep.append(part)
    return "/".join(keep)


def _nests(a: str, b: str) -> bool:
    """True when directory `a` equals or contains `b` (an empty `a` is the root)."""
    return a == "" or b == a or b.startswith(a + "/")


def overlaps(a: str, b: str) -> bool:
    """Whether two `touches:` entries can name the same file; see the docstring."""
    if a == b:
        return True
    ga, gb = _is_glob(a), _is_glob(b)
    if not ga and not gb:
        return _nests(a, b) or _nests(b, a)
    if ga and gb:
        pa, pb = _prefix(a), _prefix(b)
        return _nests(pa, pb) or _nests(pb, pa)
    lit, pat = (b, a) if ga else (a, b)
    return fnmatch.fnmatchcase(lit, pat) or _nests(lit, _prefix(pat))


def collide(x: specs.Item, y: specs.Item) -> bool:
    return any(overlaps(a, b) for a in paths(x) for b in paths(y))


def _deps(item: specs.Item, contract_none) -> list[str]:
    value = item.fields.get("depends", "").strip()
    if not value or value in contract_none:
        return []
    return specs._split(value)


def _cycle(order: list[str], deps: dict[str, list[str]]) -> list[str] | None:
    """The first cycle found walking items in file order, rotated to start at
    its earliest member; None when the graph is acyclic."""
    done: set[str] = set()
    path: list[str] = []

    def visit(node: str) -> list[str] | None:
        if node in path:
            loop = path[path.index(node):]
            k = min(range(len(loop)), key=lambda i: order.index(loop[i]))
            loop = loop[k:] + loop[:k]
            return loop + [loop[0]]
        if node in done:
            return None
        path.append(node)
        for d in deps[node]:
            found = visit(d)
            if found:
                return found
        path.pop()
        done.add(node)
        return None

    for root in order:
        found = visit(root)
        if found:
            return found
    return None


def build(items: list[specs.Item], none=("—", "-")) -> list[list[specs.Item]]:
    """Waves of the open items. Raises `CycleError` or `UnknownDependency`."""
    known = {it.id for it in items}
    open_ = [it for it in items if not it.done]
    deps: dict[str, list[str]] = {}
    for it in open_:
        wanted = _deps(it, none)
        for d in wanted:
            if d not in known:
                raise UnknownDependency(f"item {it.id}: depends on {d}, which is not an item in this file")
        deps[it.id] = [d for d in wanted if d in {o.id for o in open_}]
    cyc = _cycle([it.id for it in open_], deps)
    if cyc:
        raise CycleError("dependency cycle: " + " -> ".join(cyc))

    placed: set[str] = set()
    waiting = list(open_)
    out: list[list[specs.Item]] = []
    while waiting:
        wave: list[specs.Item] = []
        for it in waiting:
            if all(d in placed for d in deps[it.id]) and not any(collide(it, w) for w in wave):
                wave.append(it)
        out.append(wave)
        placed.update(it.id for it in wave)
        waiting = [it for it in waiting if it.id not in placed]
    return out
