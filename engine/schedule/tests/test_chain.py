"""chains (dev/schedule 1f): the next run knows what the last one did.

The tests drive real runs (`cmd_run` with a fake driver) in a real git
repository, because the properties are about the record and the tree: ticks
gained and commits made are MEASURED, the carry-over block reaches the next
run's prompt, a handoff is read once, and the chain ends or pauses by rule.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from schedule import chain, dispatch, sessions


@pytest.fixture(autouse=True)
def _vendor_keys(monkeypatch):
    for var in ("DEEPSEEK_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.setenv(var, "test-placeholder")
    # No probe call from a test: the window's reset line is the probe's business.
    monkeypatch.setattr(sessions, "_window_reset", lambda decl, env: "")


ITEM = """- [{mark}] **{id} · {title}.** do it
  touches: notes/{id}.md
  depends: —
  model: {model}
  verify: true
{extra}"""


def specs_text(*items):
    return "# Track t\n\nThe preamble.\n\n" + "\n".join(
        ITEM.format(mark="x" if done else " ", id=i, title=f"item {i}", model=model,
                    extra=extra) for i, done, model, extra in items)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@example.invalid")
    git(r, "config", "user.name", "t")
    (r / "SPECS.md").write_text(specs_text(("1a", False, "claude-opus-5-5", ""),
                                           ("1b", False, "claude-opus-5-5", "")))
    git(r, "add", "-A")
    git(r, "commit", "-qm", "init")
    return r


@pytest.fixture
def env(tmp_path):
    return {"PAZRAS_DATA_DIR": str(tmp_path / "data"),
            "PAZRAS_SESSION_UNITS": str(tmp_path / "units")}


def add_chain(env, repo, name="ch", ask=("--specs", "SPECS.md", "--all")):
    a = sessions._parser().parse_args(
        ["add", "--name", name, "--ready", "--chain", "until-done", *ask,
         "--model", "deepseek-flash", "--cwd", str(repo)])
    assert sessions.cmd_add(a, env=env) == 0
    d = sessions.session_dir(name, env)
    return d, json.loads((d / "schedule.json").read_text())


def tick_item(repo, item, *, others=()):
    """What an agent does for one item: the work, the tick, a commit."""
    (repo / "notes").mkdir(exist_ok=True)
    (repo / "notes" / f"{item}.md").write_text("done\n")
    text = (repo / "SPECS.md").read_text().replace(f"- [ ] **{item} ·", f"- [x] **{item} ·")
    (repo / "SPECS.md").write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", f"t: {item}")


def run_with(env, name, work, prompts=None):
    def driver(argv, prompt, *, cwd, log, **kw):
        if prompts is not None:
            prompts.append(prompt)
        work()
        return {"exit": 0}
    return sessions.cmd_run(sessions._parser().parse_args(["run", name]), env=env,
                            driver=driver, dirty=[], run=lambda *a, **k: None)


def events_of(d, kind):
    return [e for e in sessions.read_events(d) if e.get("event") == kind]


# --- a chain from start to done ---------------------------------------------------

def test_a_chain_carries_over_measures_progress_and_ends_itself(env, repo):
    d, decl = add_chain(env, repo)
    prompts = []

    def first():
        tick_item(repo, "1a")
        (d / chain.HANDOFF).write_text("1b is next; mind the fixture.\n")

    assert run_with(env, "ch", first, prompts) == 0
    link = events_of(d, "chain")[-1]
    assert link["state"] == "continue" and link["progress"]["ticks"] == ["1a"]
    assert len(link["progress"]["commits"]) == 1 and link["progress"]["handoff"] is True
    assert "Carry-over" not in prompts[0], "a chain's first run has nothing to carry"
    assert dispatch.next_due(json.loads((d / "schedule.json").read_text()),
                             sessions.read_events(d), sessions.now_local())[0] is not None

    assert run_with(env, "ch", lambda: tick_item(repo, "1b"), prompts) == 0
    second = prompts[1]
    assert "## Carry-over from the previous run" in second
    assert "**Ended by:** completed" in second and "SPECS ticked:** 1a" in second
    assert "t: 1a" in second, "the previous run's commits, from git"
    assert "1b is next; mind the fixture." in second, "its handoff"
    assert not (d / chain.HANDOFF).exists() and list(d.glob("handoff-*.md")), "read once"
    assert str(d / chain.HANDOFF) in second, "the header names where to write the next one"

    decl = json.loads((d / "schedule.json").read_text())
    assert decl["ended"] and events_of(d, "chain")[-1]["state"] == "done"
    assert "no open SPECS item" in events_of(d, "ended")[-1]["why"]
    assert dispatch.next_due(decl, sessions.read_events(d), sessions.now_local())[0] is None
    assert sessions._state(decl, sessions.read_events(d), sessions.now_local())["state"] == "ended"


# --- pauses -----------------------------------------------------------------------

def test_two_runs_without_progress_pause_the_chain_until_resumed(env, repo, capsys):
    d, decl = add_chain(env, repo)
    run_with(env, "ch", lambda: None)
    assert events_of(d, "chain")[-1]["state"] == "continue"
    run_with(env, "ch", lambda: None)
    assert events_of(d, "chain")[-1]["state"] == "stalled"
    assert events_of(d, "paused")[-1]["state"] == "stalled"
    when, why = dispatch.next_due(decl, sessions.read_events(d), sessions.now_local())
    assert when is None and "paused" in why
    assert sessions._state(decl, sessions.read_events(d), sessions.now_local())["state"] == "paused"
    assert sessions.cmd_resume(sessions._parser().parse_args(["resume", "ch"]), env=env) == 0
    assert dispatch.next_due(decl, sessions.read_events(d), sessions.now_local())[0] is not None


def test_editing_the_asks_source_also_clears_a_pause(env, repo):
    d, decl = add_chain(env, repo)
    run_with(env, "ch", lambda: None)
    run_with(env, "ch", lambda: None)
    assert chain.paused(sessions.read_events(d), sessions._ask_sha(decl))
    (repo / "SPECS.md").write_text((repo / "SPECS.md").read_text() + "\nA note from the user.\n")
    assert chain.paused(sessions.read_events(d), sessions._ask_sha(decl)) == ""


def test_a_ticked_item_that_asks_for_review_pauses_the_chain(env, repo):
    (repo / "SPECS.md").write_text(specs_text(("1a", False, "claude-opus-5-5", "  review: yes\n"),
                                              ("1b", False, "claude-opus-5-5", "")))
    git(repo, "commit", "-qam", "review on 1a")
    d, _ = add_chain(env, repo)
    run_with(env, "ch", lambda: tick_item(repo, "1a"))
    paused = events_of(d, "paused")[-1]
    assert paused["state"] == "review" and "1a" in paused["why"]


def test_only_the_users_items_left_is_blocked_not_stalled(env, repo):
    (repo / "SPECS.md").write_text(specs_text(("1a", False, "claude-opus-5-5", ""),
                                              ("1e", False, "user", "")))
    git(repo, "commit", "-qam", "a user item")
    d, _ = add_chain(env, repo)
    run_with(env, "ch", lambda: tick_item(repo, "1a"))
    paused = events_of(d, "paused")[-1]
    assert paused["state"] == "blocked" and "1e" in paused["why"]


def test_a_prompt_chain_ends_and_blocks_by_its_front_matter(env, repo):
    (repo / "ASK.md").write_text("---\nstatus: open\n---\n# Do the thing\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "ask")
    d, _ = add_chain(env, repo, name="pc", ask=("--prompt", "ASK.md"))

    def block():
        (repo / "ASK.md").write_text("---\nstatus: blocked\n---\n# Do the thing\n")

    run_with(env, "pc", block)
    assert events_of(d, "paused")[-1]["state"] == "blocked"
    sessions.cmd_resume(sessions._parser().parse_args(["resume", "pc"]), env=env)
    run_with(env, "pc", lambda: (repo / "ASK.md").write_text("---\nstatus: done\n---\n"))
    assert events_of(d, "ended")[-1]["why"] == "chain done: the prompt says status: done"


def test_a_refused_window_is_a_hold_and_never_counts_toward_a_stall(env, repo):
    d, decl = add_chain(env, repo)
    history = [{"event": "chain", "refused": True, "progress": {"any": False}},
               {"event": "chain", "refused": True, "progress": {"any": False}}]
    snap = chain.snapshot(decl, d)
    progress = {"ticks": [], "commits": [], "handoff": False, "status_changed": False,
                "status": "", "any": False}
    assert chain.outcome(decl, progress, snap, history, stall_after=2)[0] == "continue"
    assert chain.outcome(decl, progress, snap, [{"event": "chain", "progress": {"any": False}}],
                         stall_after=2)[0] == "stalled"


# --- the pieces ---------------------------------------------------------------------

def test_how_a_run_ended_is_named():
    assert chain.ended_why({"exit": 0}) == "completed"
    assert chain.ended_why({"exit": 1, "window_refused": True}) == "the window refused it"
    assert chain.ended_why({"exit": 0, "checkpoint_stop": "user_active: pi"}).startswith(
        "a stop condition")
    assert chain.ended_why({"exit": 124}) == "the timeout"
    assert chain.ended_why({"exit": 130, "interrupted": True}) == "interrupted by the backstop"
    assert chain.ended_why(None, {"error": "boom"}).startswith("crashed")


def test_the_final_report_is_the_last_assistant_text_in_the_transcript(tmp_path):
    t = tmp_path / "s.jsonl"
    rows = [{"type": "message", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "first"}]}},
            {"type": "message", "message": {"role": "user", "content": "ok"}},
            {"type": "message", "message": {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "hm"}, {"type": "toolCall"}]}},
            {"type": "message", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "Done: 1a ticked."}]}}]
    t.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    assert chain.final_report(t) == "Done: 1a ticked."
    assert chain.final_report(tmp_path / "missing.jsonl") == ""


def test_front_matter_status_is_read_only_from_the_front_matter():
    assert chain.front_status("---\ntitle: x\nstatus: Done\n---\nbody") == "done"
    assert chain.front_status("# no front matter\nstatus: done\n") == ""


def test_a_pause_notification_carries_its_approve_command(env, repo, told):
    add_chain(env, repo)
    run_with(env, "ch", lambda: None)
    run_with(env, "ch", lambda: None)
    texts = [t[2] for t in told if t[0] == "desktop"]
    assert any("/approve ch" in t for t in texts), texts
