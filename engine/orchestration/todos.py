"""todos -- the tracks' checklists, done and open, phone-sized (dev/remote R5d).

`familiar orchestration todos` reads every `dev/*/SPECS.md` under the item
contract (`specs.parse`; a file the contract declares `legacy` is skipped, as
`dispatch --gate` skips it) and prints, per track, done/total and the next open
items, then **what waits on the user**: every open item whose `model:` is the
contract's `user_model`. `todos <track>` lists one track's items with their marks.

It reads; it never ticks. A tick is written where the work was verified (the
contract's rule), not from a phone.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

from lib import roots
from orchestration import specs

NEXT = 3


def tracks(repo: pathlib.Path = roots.REPO) -> dict:
    """{track: [Item]} for every contract-bound SPECS file, by track name."""
    contract = specs.load_contract()
    legacy = set((contract.get("legacy") or {}).keys())
    out = {}
    for path in sorted((repo / "dev").glob("*/SPECS.md")):
        rel = path.relative_to(repo).as_posix()
        if rel in legacy:
            continue
        out[path.parent.name] = specs.parse(path.read_text(encoding="utf-8"),
                                            set(contract["fields"]))
    return out


def _user(item, contract) -> bool:
    return item.fields.get("model", "").strip() == contract.get("user_model", "user")


def summary(all_tracks: dict) -> list:
    contract = specs.load_contract()
    lines, waiting = [], []
    ordered = sorted(all_tracks.items(), key=lambda kv: all(i.done for i in kv[1]))
    for name, items in ordered:
        done = sum(1 for i in items if i.done)
        open_ = [i for i in items if not i.done]
        if not open_:
            lines.append(f"{name}: {done}/{len(items)} done")
            continue
        nxt = ", ".join(f"{i.id} {i.title}"[:60] for i in open_[:NEXT])
        lines.append(f"{name}: {done}/{len(items)} -- next: {nxt}")
        waiting += [f"- {name} {i.id}: {i.title}"[:90] for i in open_ if _user(i, contract)]
    lines.append("")
    lines += (["waiting on you:"] + waiting) if waiting else ["nothing waits on you"]
    return lines


def one(name: str, items: list) -> list:
    contract = specs.load_contract()
    done = sum(1 for i in items if i.done)
    lines = [f"{name}: {done}/{len(items)} done"]
    for i in items:
        mark = "x" if i.done else ("you" if _user(i, contract) else " ")
        lines.append(f"[{mark}] {i.id} {i.title}"[:90])
    return lines


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="familiar orchestration todos",
                                 description="The tracks' SPECS: done, open, and what waits on you.")
    ap.add_argument("track", nargs="?", help="one track's items (a dev/ folder name)")
    args = ap.parse_args(argv)
    all_tracks = tracks()
    if args.track:
        if args.track not in all_tracks:
            print(f"no track {args.track!r}; tracks: {', '.join(all_tracks)}", file=sys.stderr)
            return 2
        print("\n".join(one(args.track, all_tracks[args.track])))
        return 0
    print("\n".join(summary(all_tracks)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
