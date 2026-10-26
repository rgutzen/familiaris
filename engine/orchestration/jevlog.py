"""jevlog -- every Jev answer this track receives, with its probabilities.

WHY. A threshold on a Jev answer can only be fitted from answers whose
probabilities were kept and later joined to an outcome (Zhu et al. 2026,
arXiv 2610.21412: run in shadow mode, fit one threshold per decision point on
the agent's own outcomes; `dev/jev/_refs/2026-10-19_jevagentharness.md`).
Until 2026-10-19 each call site kept the chosen answer and dropped the rest, so
no threshold here could have been fitted. This log is the shadow-mode record.

ONE ROW PER CALL, appended to `<PAZRAS_DATA_DIR>/jev-answers.jsonl`:
  ts, source (dispatch | pair | route | eval), subject (what was asked about:
  `<specs>#<item>`, `<specs>#<a>+<b>`, `<binding>`, `<task>:<arm>-<n>#<doc>`),
  question_hash (the wording, so populations never mix), model, and `answers`:
  the response's answer map verbatim, probabilities included.

Recording never fails the caller: an unwritable log is skipped silently, since
the call it describes has already been paid for and answered.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib

from lib import roots
from orchestration import profiles

LOG_NAME = "jev-answers.jsonl"


def log_path(env=os.environ) -> pathlib.Path:
    return profiles.data_dir(env) / LOG_NAME


def specs_rel(path: pathlib.Path, root: pathlib.Path = roots.REPO) -> str:
    """A SPECS path as labels.py writes it: repo-relative when inside the repo."""
    p = pathlib.Path(path).resolve()
    return str(p.relative_to(root)) if p.is_relative_to(root) else str(path)


def record(source: str, subject: str, question_hash: str, resp: dict,
           path: pathlib.Path | None = None) -> None:
    row = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "source": source, "subject": subject, "question_hash": question_hash,
        "model": str((resp or {}).get("model") or ""),
        "answers": (resp or {}).get("answers") or {},
    }
    target = path or log_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    except OSError:
        pass


def read(path: pathlib.Path | None = None) -> list:
    target = path or log_path()
    if not target.is_file():
        return []
    out = []
    for line in target.read_text(encoding="utf-8").splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if isinstance(o, dict):
            out.append(o)
    return out


def latest(source: str, subject: str, path: pathlib.Path | None = None) -> dict | None:
    """The newest row for one subject, or None."""
    rows = [r for r in read(path) if r.get("source") == source and r.get("subject") == subject]
    return rows[-1] if rows else None
