#!/usr/bin/env python3
"""The measured chart for docs/explanation/orchestration.md.

One figure: what the eval found, as bars. The flow diagrams in that document are
Mermaid blocks, not images — `VISUAL-ARCHITECTURE.md` sets that rule, and it is
the same `voice.md` rule (a relation is a diagram; a quantity is a chart).

Every number is from `dev/orchestration/2026-10-15-eval.md` (the scored table,
item 4e). The PNG is an output — never edit it, and never trust a copy of it that
has no script next to it.

    python3 orchestration-verdicts.py            # writes orchestration-verdicts.png
    python3 orchestration-verdicts.py --ascii    # the same series for a chat reply
"""
from __future__ import annotations

import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                                        # noqa: E402

plt.rcParams["font.family"] = ["Geist", "DejaVu Sans"]

# 06-system skin: the adopted arm is the one accent; rejected arms are muted.
GOOD = "#bf4520"
BAD = "#4f5d75"
INK = "#2d3142"
GREY = "#4f5d75"
PAPER = "#f5f5f5"
HERE = pathlib.Path(__file__).parent

# (arm, median paired cost vs the Opus baseline, passes vs the baseline, colour,
#  the verdict). `None` means the arm's model has no catalogue price, so it
# cannot enter the cost ratio at all — not that it was free.
ARMS = [
    ("dispatch", 0.100, "13 of 14", GOOD, "adopted"),
    ("bindings", 1.008, "5 of 5", BAD, "rejected: the parent rarely calls it"),
    ("jev as assignee", 0.018, "1 of 3", BAD, "rejected: wrong on batch"),
    ("reference\n(oh-my-opencode-slim)", None, "10 of 14", BAD, "rejected: unpriced model"),
]
TEXT_AT = 1.06          # where the verdict column starts, in data units


def verdicts(path):
    fig, ax = plt.subplots(figsize=(7.6, 3.1), dpi=140, facecolor=PAPER)
    ax.set_facecolor(PAPER)
    ys = list(range(len(ARMS)))
    for y, (name, ratio, passes, color, why) in zip(ys, ARMS):
        if ratio is None:
            ax.plot([0], [y], marker="x", color=color, markersize=7, zorder=3)
            ax.text(0.02, y, f"not priceable  ·  {passes}", va="center", ha="left",
                    fontsize=8.0, color=INK, zorder=3)
        else:
            ax.barh(y, ratio, height=0.5, color=color, alpha=0.85)
            inside = ratio > 0.62
            ax.text(ratio - 0.02 if inside else ratio + 0.02, y,
                    f"{ratio:.3f}×  ·  {passes}", va="center",
                    ha="right" if inside else "left", fontsize=8.0,
                    color="white" if inside else INK, zorder=3)
        ax.text(TEXT_AT, y, why, va="center", ha="left", fontsize=7.6, color=GREY)
    ax.axvline(0.84, color=INK, linestyle="--", linewidth=1.0, zorder=2)
    ax.text(0.825, -0.60, "the bar: 0.84×", ha="right", va="center", fontsize=7.6, color=INK)
    ax.set_yticks(ys)
    ax.set_yticklabels([n for n, *_ in ARMS], fontsize=8.2)
    ax.set_ylim(len(ARMS) - 0.45, -0.75)
    ax.set_xlim(0, 1.62)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(["0", "0.25×", "0.5×", "0.75×", "1.0×"], fontsize=7.6)
    ax.set_xlabel("median paired cost against the Opus baseline, per task  ·  "
                  "passes are of the baseline", fontsize=8.2, color=INK)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_title("Four strategies, fourteen replayed tasks, one bar to clear",
                 fontsize=10.5, color=INK, pad=10)
    fig.subplots_adjust(left=0.205, right=0.99, top=0.85, bottom=0.20)
    fig.savefig(path, facecolor=PAPER)
    return path


def ascii_verdicts():
    """The terminal form of the same series."""
    width = 24
    out = []
    for name, ratio, passes, color, why in ARMS:
        flat = name.replace("\n", " ")
        if ratio is None:
            out.append(f"{flat:34} {'—':>{width}}  {passes:>9}  {why}")
        else:
            filled = max(1, round(ratio / 1.05 * width))
            out.append(f"{flat:34} {'▇' * filled}{'·' * (width - filled)} "
                       f"{ratio:5.3f}×  {passes:>9}  {why}")
    out.append(f"{'':34} {'':>{width}}  {'':>9}  the bar is 0.84×")
    return "\n".join(out)


if __name__ == "__main__":
    if "--ascii" in sys.argv:
        print(ascii_verdicts())
    else:
        print("wrote", verdicts(HERE / "orchestration-verdicts.png"))
