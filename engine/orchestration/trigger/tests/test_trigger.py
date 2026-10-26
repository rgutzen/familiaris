"""trigger (5b): the turn splitter, the two file rules, the byte counter, the fire
boundary, the once-per-turn rule, the `pi-agent/` exclusion, an unreadable log,
and a synthetic tree whose fire rate is an exact number.

WHAT IS PINNED, AND WHY EACH ONE IS WORTH A TEST.
  the splitter   A turn is a user message up to the next one, so the counters are
                 per user prompt and not per assistant response. If this drifts,
                 every number the replay reports drifts with it.
  the two rules  The reading tools' arguments (the item's rule) and the record's
                 bash rule (the deviation, documented in the module docstring) are
                 pinned separately, because the difference between them is a
                 measured 1.9% against 28.7% on the real logs.
  the bytes      `len(text)` of the text blocks, characters rather than UTF-8
                 bytes, which is the record's wording and must not be "fixed".
  the boundary   Exactly 6 files with exactly 80 KB fires; 5 files with 200 KB and
                 6 files with 79 KB do not; a turn that crosses the file floor
                 after its last result never fires. Three tests, because each one
                 removes a different way of being off by one.
  once per turn  One hint per user turn, however far past the floors the turn
                 runs, and one fire in the next turn.
  the exclusion  `pi-agent/` holds children's own logs; a firing session there
                 must not reach the replay.
  the rates      A synthetic tree with 8 turns and 2 fires: 25.0%, in the band,
                 and 1 of the 2 fires invisible to the reading tools alone.

No test reads the real `~/.pi/agent/sessions`: the rate there changes with every
session, so it is printed by the CLI and quoted, never asserted. Everything here
is a tmp tree or a list of entries written by the helpers below.
"""
import json
import os
import pathlib

import pytest

from orchestration import trigger as T

KB = 1024


# --- synthetic logs ---------------------------------------------------------

def user(ts="2026-01-01T00:00:00.000Z"):
    return {"type": "message", "timestamp": ts,
            "message": {"role": "user", "content": [{"type": "text", "text": "go"}]}}


def calls(*pairs):
    """One assistant message carrying tool calls: `calls(("read", {"path": "f"}))`."""
    return {"type": "message", "message": {"role": "assistant", "content": [
        {"type": "toolCall", "name": name, "arguments": arguments}
        for name, arguments in pairs]}}


def out(text, name="read"):
    return {"type": "message", "message": {
        "role": "toolResult", "toolName": name,
        "content": [{"type": "text", "text": text}]}}


def reads(n, first=0):
    return [("read", {"path": f"f{i}.py"}) for i in range(first, first + n)]


def firing_turn(ts="2026-01-01T00:00:00.000Z"):
    """Six distinct files and exactly 80 KB: the boundary, passed."""
    return [user(ts), calls(*reads(6)), out("x" * (80 * KB))]


def quiet_turn(ts, files=5, size=200 * KB):
    """A heavy turn that does not fire: one floor is below, the other far above."""
    return [user(ts), calls(*reads(files)), out("x" * size)]


def filler():
    """Entry types that are not messages: the splitter must ignore all of them."""
    return [{"type": "session", "version": 3, "id": "s"},
            {"type": "model_change", "modelId": "m"},
            {"type": "thinking_level_change", "thinkingLevel": "high"},
            {"type": "context_edit", "name": "c"},
            {"type": "custom", "customType": "web-search-results", "data": {}}]


def write(root, slug, name, entries, mtime=None):
    """Write one session log under `root/<slug>/<name>` and return its path."""
    directory = pathlib.Path(root) / slug
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries),
                    encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


# --- the turn splitter ------------------------------------------------------

def test_trigger_turn_splitter_splits_on_user_messages():
    entries = filler() + [user("T1"), out("a"), user("T2"), out("b"), out("c")]
    turns = list(T.split_turns(entries))
    assert [t.index for t in turns] == [1, 2]
    assert [t.start for t in turns] == ["T1", "T2"]
    assert [t.results for t in turns] == [1, 2]
    assert list(T.split_turns(filler())) == []          # no user message, no turn
    assert list(T.split_turns([user("T1"), out("a")]))[0].bytes == 1


def test_trigger_splitter_drops_unparseable_lines_and_keeps_the_session(tmp_path):
    # A log truncated mid-write is readable up to the truncation, and one bad
    # line must not cost the turns around it.
    entries = filler() + [user("T1"), calls(*reads(2)), out("a")]
    log = tmp_path / "truncated.jsonl"
    log.write_text("".join(json.dumps(e) + "\n" for e in entries) + '{"type":"mess\n',
                   encoding="utf-8")
    turns = T.session_turns(log)
    assert [t.index for t in turns] == [1]
    assert len(turns[0].files) == 2 and turns[0].bytes == 1


# --- the file counter, rule by rule ----------------------------------------

@pytest.mark.parametrize("name,arguments,want", [
    ("read", {"path": "engine/x.py", "offset": 1}, ["engine/x.py"]),
    ("grep", {"pattern": "x", "path": "engine", "glob": "*.py"}, ["engine", "*.py"]),
    ("grep", {"pattern": "x"}, []),                    # no root and no filter named
    ("find", {"pattern": "*.py", "path": "engine"}, ["engine"]),   # never the glob
    ("ls", {"path": "config"}, ["config"]),
    ("ls", {}, []),                                    # absent = the cwd, no file
    ("read", {"path": ""}, []),
    ("read", {"path": None}, []),
    ("read", "not a dict", []),
    ("edit", {"path": "engine/x.py"}, []),              # a write is not a read
    ("bash", {"command": "cat x"}, []),                 # bash has its own rule, below
])
def test_trigger_file_counter_per_tool_name(name, arguments, want):
    assert T.read_paths(name, arguments) == want


@pytest.mark.parametrize("command,want", [
    ("cat engine/x.py", {"engine/x.py"}),
    ("sed -n '1,200p' dev/orchestration/SPECS.md",
     {"dev/orchestration/SPECS.md"}),
    ("sed -i '/\"eval\": \"eval\",/d' engine/x.py", {"engine/x.py"}),
    ("sed -i.bak -n '1,2p' a.md", {"a.md"}),
    ("head -60 engine/orchestration/trigger/__init__.py",
     {"engine/orchestration/trigger/__init__.py"}),
    ("tail -n 5 a.md", {"a.md"}),
    ("cat a.md b.md", {"a.md", "b.md"}),
    ("cat 'a b.md'", {"a b.md"}),
    ("cat a.md | grep x", {"a.md"}),
    ("rg pattern engine/x.py", set()),          # not one of the record's commands
    ("nl -ba a.md", set()),                     # nor this one
    ("echo a.b", set()),                        # not a reading command
    ("notcat a.md", set()),
    ("cat > out.md", set()),                    # a redirect target is a write
    ("cat <<EOF", set()),
    (None, set()),
])
def test_trigger_bash_read_rule_is_the_records(command, want):
    assert T.bash_read_paths(command) == want


# --- bytes ------------------------------------------------------------------

def test_trigger_byte_counter_sums_text_blocks():
    assert T.tool_output_bytes({"content": [{"type": "text", "text": "abc"}]}) == 3
    assert T.tool_output_bytes({"content": [{"type": "text", "text": "ab"},
                                            {"type": "text", "text": "cde"}]}) == 5
    assert T.tool_output_bytes({"content": [{"type": "text", "text": "abc"},
                                            {"type": "image", "data": "zz"}]}) == 3
    assert T.tool_output_bytes({"content": []}) == 0
    assert T.tool_output_bytes({}) == 0
    assert T.tool_output_bytes({"content": "a string"}) == 0
    assert T.tool_output_bytes({"content": [{"type": "text", "text": None}]}) == 0
    # Characters, not UTF-8 bytes: the record says `len(text)`, and a "fix" to
    # encoded bytes would move every floor by the encoding of the log.
    assert T.tool_output_bytes({"content": [{"type": "text", "text": "é"}]}) == 1


# --- the fire boundary ------------------------------------------------------

def test_trigger_fires_at_exactly_six_files_and_eighty_kb():
    entries = [user(), calls(*reads(6)), out("x" * (40 * KB)), out("y" * (40 * KB))]
    turn, = list(T.split_turns(entries))
    assert (len(turn.files), turn.bytes) == (6, 80 * KB)
    assert turn.fired_at == 2                 # the result that crossed both floors
    # At or after the fire: the crossing result and everything after it. The
    # earlier results are already in the parent's transcript, so a delegation
    # cannot keep them out.
    assert turn.bytes_after == 40 * KB


def test_trigger_does_not_fire_at_five_files_two_hundred_kb():
    entries = [user(), calls(*reads(5)), out("x" * (200 * KB))]
    turn, = list(T.split_turns(entries))
    assert (len(turn.files), turn.bytes, turn.fired_at) == (5, 200 * KB, None)
    assert turn.bytes_after == 0


def test_trigger_does_not_fire_at_six_files_seventy_nine_kb():
    entries = [user(), calls(*reads(6)), out("x" * (79 * KB))]
    turn, = list(T.split_turns(entries))
    assert (len(turn.files), turn.bytes, turn.fired_at) == (6, 79 * KB, None)


def test_trigger_does_not_fire_when_the_last_file_arrives_after_the_last_result():
    # The floors are evaluated at each tool result, so a read announced after the
    # final result is a file the parent never paid for and never delegates.
    entries = [user(), calls(*reads(5)), out("x" * (200 * KB)),
               calls(("read", {"path": "late.py"}))]
    turn, = list(T.split_turns(entries))
    assert (len(turn.files), turn.bytes, turn.fired_at) == (6, 200 * KB, None)


def test_trigger_fires_at_the_first_result_that_crosses_both():
    entries = [user(), calls(*reads(6))] + [out("z" * (10 * KB))] * 10
    turn, = list(T.split_turns(entries))
    assert turn.results == 10
    assert turn.fired_at == 8                 # 8 x 10 KB = the 80 KB floor
    assert turn.bytes_after == 3 * 10 * KB


# --- once per turn ----------------------------------------------------------

def test_trigger_fires_once_per_turn_and_again_in_the_next(tmp_path):
    entries = [user("T1"), calls(*reads(6)), out("x" * (80 * KB)),
               out("y" * (200 * KB))]
    entries += [calls(("read", {"path": "f6.py"})), out("z" * (200 * KB))]
    entries += [user("T2"), calls(*reads(6)), out("x" * (80 * KB))]
    first, second = list(T.split_turns(entries))
    assert first.fired_at == 1                # not 2, not 3: once, at the crossing
    assert len(first.files) == 7 and first.bytes == 480 * KB
    assert first.bytes_after == first.bytes   # every byte from the fire onward
    assert second.fired_at == 1
    # One file, one turn, one fire.
    log = tmp_path / "two-turns.jsonl"
    log.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    replay = T.run_replay([log])
    assert (replay.turns, len(replay.fires)) == (2, 2)


# --- the pi-agent/ exclusion ------------------------------------------------

def test_trigger_excludes_pi_agent_subdirectory(tmp_path):
    sessions = tmp_path / "sessions"
    write(sessions, "--home-rg--", "parent.jsonl", firing_turn())
    write(sessions, "pi-agent", "child.jsonl", firing_turn())
    assert [p.name for p in T.recent_logs(10, sessions)] == ["parent.jsonl"]
    replay = T.run_replay(T.recent_logs(10, sessions))
    assert (replay.turns, len(replay.fires)) == (1, 1)
    assert all("pi-agent" not in str(fire.session) for fire in replay.fires)


# --- an unreadable log ------------------------------------------------------

def test_trigger_skips_an_unreadable_log_and_names_it(tmp_path, capsys):
    sessions = tmp_path / "sessions"
    good = write(sessions, "--home-rg--", "good.jsonl", firing_turn())
    broken = sessions / "--home-rg--" / "broken.jsonl"
    broken.mkdir()                                    # a directory named like a log
    missing = sessions / "--tmp--" / "gone.jsonl"     # never written
    replay = T.run_replay([broken, missing, good])
    assert [(p.name, why) for p, why in replay.skipped] == [
        ("broken.jsonl", "Is a directory"),
        ("gone.jsonl", "No such file or directory")]
    assert (replay.turns, len(replay.fires)) == (1, 1)   # the good log still reports

    assert T.main(["--", str(broken), str(missing), str(good)]) == 0
    captured = capsys.readouterr()
    assert "skipped" in captured.out and "broken.jsonl" in captured.out
    assert "broken.jsonl" in captured.err and "gone.jsonl" in captured.err


# --- the synthetic tree, and the exact rate ---------------------------------

def _tree(tmp_path):
    """8 turns, 2 fires: one from read calls, one only the bash rule can see."""
    sessions = tmp_path / "sessions"
    write(sessions, "--home-rg-a--", "a.jsonl",
          firing_turn("T1")
          + [user("T2"),
             calls(("bash", {"command": "cat a.md b.md c.md d.md e.md f.md"})),
             out("x" * (80 * KB), name="bash")], mtime=3000)
    write(sessions, "--home-rg-b--", "b.jsonl",
          quiet_turn("T1") + quiet_turn("T2"), mtime=2000)
    write(sessions, "--home-rg-c--", "c.jsonl",
          [user(f"T{i}") for i in range(1, 5)], mtime=1000)
    return sessions


def test_trigger_replay_over_a_synthetic_tree_reports_an_exact_rate(tmp_path, capsys):
    sessions = _tree(tmp_path)
    replay = T.run_replay(T.recent_logs(10, sessions))
    assert [p.name for p in replay.logs] == ["a.jsonl", "b.jsonl", "c.jsonl"]
    assert replay.turns == 8
    assert len(replay.fires) == 2
    assert replay.rate == 0.25
    assert replay.within_band is True
    # The bash-only fire is invisible to the reading tools alone: the deviation
    # the module docstring measures is visible here too.
    assert replay.fires_tools == 1 and replay.rate_tools == 0.125
    low, high = replay.band
    assert (round(low, 3), round(high, 3)) == (0.216, 0.324)

    assert T.main(["--sessions", str(sessions)]) == 0
    out = capsys.readouterr().out
    assert "turns     8" in out
    assert "fires     2 (25.0% of turns)" in out
    assert "21.6% - 32.4%): YES" in out
    assert "read/grep/find/ls arguments + cat/sed/head/tail inside bash" in out
    assert "the four tools alone fire on 1 (12.5%)" in out
    assert "explore -- pi-agent explore \"<task>\"" in out


def test_trigger_replay_flag_reads_the_n_most_recent_logs(tmp_path):
    sessions = _tree(tmp_path)
    assert [p.name for p in T.recent_logs(2, sessions)] == ["a.jsonl", "b.jsonl"]
    assert T.run_replay(T.recent_logs(2, sessions)).turns == 4


def test_trigger_json_carries_the_same_counts(tmp_path, capsys):
    sessions = _tree(tmp_path)
    assert T.main(["--sessions", str(sessions), "--json"]) == 0
    row = json.loads(capsys.readouterr().out)
    assert set(row) == {
        "sessions", "skipped", "turns", "fires", "rate", "fires_tools_only",
        "rate_tools_only", "bytes_total", "bytes_after", "bytes_share",
        "recorded_rate", "band", "within_band", "role", "command"}
    assert row["turns"] == 8 and row["rate"] == 0.25
    assert row["fires_tools_only"] == 1 and row["rate_tools_only"] == 0.125
    assert row["within_band"] is True and row["band"] == [0.216, 0.324]
    assert row["role"] == "explore"
    assert len(row["fires"]) == 2
    assert len(row["fires"][0]["files"]) == 6
    assert row["fires"][0]["bytes_after"] == 80 * KB


# --- the interface ----------------------------------------------------------

def test_trigger_paths_after_a_double_dash_are_filenames(tmp_path, capsys):
    # A session directory slug starts with `--`, so a path must survive argparse
    # as a filename rather than be read as a flag.
    log = write(tmp_path / "sessions", "--home-rg-06_SYSTEM--", "x.jsonl", firing_turn())
    assert T.main(["--", str(log)]) == 0
    out = capsys.readouterr().out
    assert "turns     1" in out and "fires     1 (100.0% of turns)" in out
    assert "--home-rg-06_SYSTEM--" in out


def test_trigger_usage_errors_exit_2(tmp_path):
    with pytest.raises(SystemExit) as raised:
        T.main(["--replay", "0"])
    assert raised.value.code == 2
    with pytest.raises(SystemExit) as raised:
        T.main(["--nope"])
    assert raised.value.code == 2
    assert T.main(["--sessions", str(tmp_path / "absent")]) == 2


def test_trigger_thresholds_are_the_replayed_parameters():
    assert (T.MIN_FILES, T.MIN_BYTES) == (6, 80 * 1024)
    assert (T.RECORDED_RATE, T.RATE_TOLERANCE) == (0.27, 0.20)
    assert (T.RECORDED_PRECISION, T.RECORDED_RECALL) == (0.84, 0.97)
    assert T.RECORDED_ON == "2026-10-12" and T.RECORDED_SESSIONS == 112
    assert T.DEFAULT_REPLAY == 30
    assert (T.ROLE, T.DELEGATE) == ("explore", 'pi-agent explore "<task>"')
    assert T.FILE_ARGS == {"read": ("path",), "grep": ("path", "glob"),
                           "find": ("path",), "ls": ("path",)}
    assert T.BASH_READ_COMMANDS == ("cat", "sed", "head", "tail")
    assert T.SCRIPT_ARG == {"sed": 1}


def test_trigger_since_counts_only_the_logs_dated_after_the_window(tmp_path):
    """5d's window is 30 fires in normal work, so a fire from the calibration
    session must not count. The date comes from the filename, which sorts."""
    (tmp_path / "slug").mkdir()
    for stamp in ("2026-10-12T09-00-00-000Z", "2026-10-15T09-00-00-000Z", "2026-10-16T09-00-00-000Z"):
        (tmp_path / "slug" / f"{stamp}_aaa.jsonl").write_text("")
    paths = T.recent_logs(10, tmp_path)
    assert [T.log_date(p) for p in paths] == ["2026-10-16", "2026-10-15", "2026-10-12"]
    assert [T.log_date(p) for p in T.since_date(paths, "2026-10-15")] == \
        ["2026-10-16", "2026-10-15"]
    assert T.since_date(paths, "2026-10-17") == []
    # a file whose name does not carry a date is older than any window
    odd = tmp_path / "slug" / "no-date.jsonl"
    odd.write_text("")
    assert T.log_date(odd) == "" and T.since_date([odd], "2026-01-01") == []


# --- the hint's own count (12b) ---------------------------------------------

def hint(text="This turn has read 6 distinct files"):
    return {"type": "custom_message", "customType": T.NUDGE_TYPE, "content": text,
            "display": True, "details": {"files": 6, "bytes": 90 * KB}}


def test_trigger_counts_the_hint_and_whether_a_delegation_followed_it():
    """`acted` is a same-turn relation and an ORDER: a hint a turn answers counts,
    a hint that arrives after the delegation does not, and a delegation with no
    hint is not an acted-on nudge."""
    entries = [user("T1"), calls(*reads(6)), out("x" * (90 * KB)), hint(),
               calls(("bash", {"command": 'pi-agent explore "find it"'}))]
    turn, = list(T.split_turns(entries))
    assert (turn.nudges, turn.acted, turn.delegated) == (1, 1, True)

    entries = [user("T1"), calls(*reads(6)), out("x" * (90 * KB)), hint()]
    turn, = list(T.split_turns(entries))
    assert (turn.nudges, turn.acted, turn.delegated) == (1, 0, False)

    entries = [user("T1"), calls(*reads(6), ("bash", {"command": "pi-agent bash 'x'"})),
               out("x" * (90 * KB)), hint()]
    turn, = list(T.split_turns(entries))
    assert (turn.nudges, turn.acted, turn.delegated) == (1, 0, True)


def test_trigger_another_extension_s_message_is_not_this_hint():
    entries = [user("T1"), calls(*reads(6)), out("x" * (90 * KB)),
               {"type": "custom", "customType": T.NUDGE_TYPE, "data": {}}]
    turn, = list(T.split_turns(entries))
    assert turn.nudges == 0, "only a `custom_message` entry is the sent hint"


def test_trigger_a_bound_tool_call_is_a_delegation():
    assert T.delegating("bound_fetch", {"task": "x"})
    assert T.delegating("bash", {"command": "cd /tmp && pi-agent explore 'x'"})
    assert not T.delegating("bash", {"command": "echo pi-agent-ish"})
    assert not T.delegating("read", {"path": "pi-agent"})
