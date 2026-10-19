#!/usr/bin/env python3
"""Worst-case token cost of answering one routing question.

The numbers are inputs, not a store: refresh them from `familiar context tree`
(they were measured 2026-10-09) and re-run this file. The PNG is an output —
never edit it, and never trust a copy of it that has no script next to it.

    python3 route-cost-chart.py            # writes route-cost-chart.png
    python3 route-cost-chart.py --ascii    # the same series for a chat reply

Two renderings, one source: `matplotlib` for the vault and the repo docs,
`asciichartpy` for the terminal. This is the pattern `voice.md` §Representation
asks for at document scale.
"""
from __future__ import annotations

import sys
import pathlib

# (label, worst-case tokens) -- from `familiar context tree`, 2026-10-09.
ROUTES = [
    ("the class list (ontology)", 6313),
    ("prose style (voice.md)", 5665),
    ("any fact (knowledge/INDEX.md)", 4108),
    ("which skill fits", 4088),
    ("drafting under your name", 4037),
    ("priorities (user profile)", 3871),
    ("delegating to a local model", 3857),
    ("boundaries", 3693),
    ("code style", 3168),
    ("journal: a past date", 2926),
]


def ascii_chart(routes=ROUTES) -> str:
    """The chat form: an axis-labelled series, ~12 lines."""
    import asciichartpy
    return asciichartpy.plot([v for _, v in routes], {"height": 10, "format": "{:8.0f}"})


def png_chart(path, routes=ROUTES) -> pathlib.Path:
    """The document form: ranked, labelled, one bar per route."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [n for n, _ in routes][::-1]
    values = [v for _, v in routes][::-1]
    fig, ax = plt.subplots(figsize=(7.5, 4), dpi=140)
    ax.barh(labels, values, color="#3b6ea5")
    for y, v in enumerate(values):
        ax.text(v + 60, y, f"{v:,}", va="center", fontsize=7.5)
    ax.set_xlabel("worst-case tokens to answer one routing question", fontsize=8)
    ax.tick_params(labelsize=8)
    ax.set_xlim(0, max(values) * 1.15)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    out = pathlib.Path(path)
    fig.savefig(out)
    return out


if __name__ == "__main__":
    if "--ascii" in sys.argv:
        print(ascii_chart())
    else:
        where = pathlib.Path(__file__).with_name("route-cost-chart.png")
        print("wrote", png_chart(where))
