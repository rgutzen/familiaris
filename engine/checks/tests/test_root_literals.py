"""root_literals: what reads as a spelled root, and what does not (R2a)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import root_literals as rl  # noqa: E402

PAT = rl._pattern()


def _py(tmp_path, src):
    p = tmp_path / "m.py"
    p.write_text(src)
    return [n for n, _ in rl._python(p, PAT)]


def _sh(tmp_path, src):
    p = tmp_path / "s.sh"
    p.write_text(src)
    return [n for n, _ in rl._shell(p, PAT)]


def test_a_root_as_a_path_segment_is_found(tmp_path):
    src = 'A = REPO / "memory"\nB = "memory/knowledge"\nC = "~/06_SYSTEM/engine"\n'
    assert _py(tmp_path, src) == [1, 2, 3]


def test_prose_and_docstrings_are_not(tmp_path):
    src = ('"""memory/ in a docstring."""\n'
           'X = "the master config"\nY = "subagents/x"\n'
           'Z = "memory/x"  # not-a-root: a recorded cwd\n')
    assert _py(tmp_path, src) == []


def test_shell_reads_words_not_comments(tmp_path):
    src = ('# memory/ in a comment\n'
           'local s="$HOME/06_SYSTEM/engine"\n'
           'echo "edit the config"\n')
    assert _sh(tmp_path, src) == [2]


def test_the_engine_is_clean():
    assert list(rl.findings()) == []


def test_an_f_string_is_read_too(tmp_path):
    """Python 3.12+ tokenizes an f-string as START/MIDDLE/END, not STRING.
    The gate read STRING alone until 2026-10-07 and missed 26 findings --
    one of them the glob `checks.py --audit` walks."""
    src = 'G = f"engine/**/{pattern}"\nR = f"memory/{rel}"\nOK = f"{E}/agents"\n'
    assert _py(tmp_path, src) == [1, 2]


def test_a_bare_root_word_is_read_only_on_a_path_shaped_line(tmp_path):
    """`config` is a verb name in engine/familiar and a subject id; only
    `REPO / "config"` uses it as a root."""
    src = ('V = "config"\nD = {"config": 1}\nP = REPO / "config"\n'
           'Q = os.path.join(HERE, "memory")\n')
    assert _py(tmp_path, src) == [3, 4]
