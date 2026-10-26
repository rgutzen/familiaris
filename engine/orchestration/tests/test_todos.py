"""The tracks' todos on the phone (dev/remote R5d): read from the SPECS, never ticked."""
from __future__ import annotations

from orchestration import todos

SPECS = """# t

- [x] **1a · done.** x
  touches: a
  depends: —
  model: claude-opus-5-5
  verify: true
- [ ] **1b · the agent's.** x
  touches: b
  depends: 1a
  model: claude-opus-5-5
  verify: true
- [ ] **1c · the user's.** x
  touches: c
  depends: —
  model: user
  verify: manual: a reading
"""


def test_summary_counts_names_next_and_what_waits_on_the_user(tmp_path):
    for name, text in (("alpha", SPECS), ("beta", SPECS.replace("- [ ]", "- [x]"))):
        (tmp_path / "dev" / name).mkdir(parents=True)
        (tmp_path / "dev" / name / "SPECS.md").write_text(text)
    t = todos.tracks(tmp_path)
    lines = todos.summary(t)
    assert lines[0] == "alpha: 1/3 -- next: 1b the agent's, 1c the user's"
    assert "beta: 3/3 done" in lines
    assert lines[-2:] == ["waiting on you:", "- alpha 1c: the user's"]
    assert todos.one("alpha", t["alpha"])[1:] == ["[x] 1a done", "[ ] 1b the agent's",
                                                   "[you] 1c the user's"]
