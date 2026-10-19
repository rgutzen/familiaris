"""The provider selector: a name resolves, a partial adapter is refused.

`engine/backup/remotes/select.sh` is sourced by the two things that move bytes
off this machine — `familiar backup sync` (through `structure/pazras.sh`) and
`engine/backup/mirror.sh`. It is bash, so this drives it the way
`test_roots.py` drives `roots.sh`: a subprocess per case, with the directories
and the selection moved into a tmp tree.

What it holds, and why each case is here rather than discovered in a timer at
04:30:

  * the shipped template is a COMPLETE adapter — all five functions — because
    it is the file an install copies;
  * an adapter missing a function is refused, and the message NAMES it;
  * a name is a filename stem: a separator or `..` resolves to nothing, so a
    profile cannot source a file outside the two directories;
  * the install's directory is searched FIRST, so an install can override the
    shipped `example.sh` without editing the engine;
  * `remote_prepare` gives a caller name and root only when the adapter is
    usable, and leaves both empty otherwise — an install with no provider must
    never read a stale name from the attempt before it.
"""
import pathlib
import subprocess

from lib import roots

SELECT = pathlib.Path(roots.__file__).resolve().parent.parent / "backup" / "remotes" / "select.sh"

FULL = """\
remote_name() { printf '%s' fixture; }
remote_root() { printf '%s' /remote-root; }
remote_available() { return 0; }
remote_upload() { :; }
remote_delete() { :; }
"""


def _run(script: str, *, remote: str = "example", install: pathlib.Path | None = None,
         shipped: pathlib.Path | None = None) -> subprocess.CompletedProcess:
    """Source the selector with the environment a profile would give it."""
    import os
    env = dict(os.environ,
               PAZRAS_STORAGE_REMOTE=remote,
               PAZRAS_REMOTE_DIR=str(shipped if shipped else SELECT.parent),
               PAZRAS_REMOTE_CONFIG_DIR=str(install) if install else "")
    return subprocess.run(["bash", "-c", f"source {SELECT}\n{script}"],
                          capture_output=True, text=True, env=env)


# ── the shipped template ─────────────────────────────────────────────────────

def test_the_shipped_example_is_a_complete_adapter():
    r = _run("remote_load && echo loaded || echo refused")
    assert r.returncode == 0, r.stderr
    assert "loaded" in r.stdout, r.stderr


def test_the_example_names_itself_and_reaches_nothing():
    """`remote_name` is for log lines; `remote_available` must be honest, and
    for a template with no client there is nothing honest to say but "no"."""
    r = _run("remote_load || exit 9; remote_name; echo; remote_available "
             "&& echo available || echo unavailable")
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["example", "unavailable"], r.stdout


def test_every_function_in_the_api_is_defined_by_the_template():
    r = _run('remote_load || exit 9; '
             'for fn in "${REMOTE_API[@]}"; do '
             'declare -F "$fn" >/dev/null || echo "missing $fn"; done; echo done')
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "done", r.stdout


# ── refusals, each with the name it must print ───────────────────────────────

def test_an_adapter_missing_a_function_is_refused_by_name(tmp_path):
    (tmp_path / "half.sh").write_text("remote_name() { :; }\nremote_root() { :; }\n")
    r = _run("remote_load", remote="half", shipped=tmp_path)
    assert r.returncode != 0
    assert "remote_upload" in r.stderr and "remote_delete" in r.stderr, r.stderr


def test_a_name_that_is_not_a_stem_resolves_to_nothing(tmp_path):
    (tmp_path / "example.sh").write_text(FULL)
    for name in ("../../etc/passwd", "sub/dir", ".."):
        r = _run("remote_path; remote_load", remote=name, shipped=tmp_path)
        assert r.returncode != 0, f"{name!r} was accepted"
        assert "no adapter" in r.stderr or "remote:" in r.stderr, r.stderr


def test_an_empty_or_unset_selection_falls_back_to_the_template(tmp_path):
    """`storage.remote:` missing is not an error: the profile's default is the
    template, which loads and reaches nothing. The distinction matters because
    a broken install and an unconfigured one must not look the same."""
    (tmp_path / "example.sh").write_text(FULL)
    for name in ("", "example"):
        r = _run("remote_load && echo loaded", remote=name, shipped=tmp_path)
        assert r.stdout.strip() == "loaded", (name, r.stderr)


def test_an_unknown_name_says_where_it_looked(tmp_path):
    r = _run("remote_load", remote="nowhere", shipped=tmp_path)
    assert r.returncode != 0
    assert str(tmp_path) in r.stderr, r.stderr


# ── selection order ──────────────────────────────────────────────────────────

def test_the_installs_directory_wins(tmp_path):
    """Both roots hold an `example.sh`; the profile must get the install's."""
    install = tmp_path / "install"
    shipped = tmp_path / "shipped"
    install.mkdir()
    shipped.mkdir()
    (install / "example.sh").write_text(FULL.replace("fixture", "from-install"))
    (shipped / "example.sh").write_text(FULL.replace("fixture", "from-engine"))
    r = _run("remote_load; remote_name", install=install, shipped=shipped)
    assert r.stdout.strip() == "from-install", r.stdout


def test_the_shipped_directory_is_the_fallback(tmp_path):
    shipped = tmp_path / "shipped"
    shipped.mkdir()
    (shipped / "example.sh").write_text(FULL.replace("fixture", "from-engine"))
    r = _run("remote_load; remote_name", install=tmp_path / "absent", shipped=shipped)
    assert r.stdout.strip() == "from-engine", r.stdout


# ── what a caller reads afterwards ───────────────────────────────────────────

def test_prepare_fills_name_and_root_when_usable(tmp_path):
    (tmp_path / "ok.sh").write_text(FULL)
    r = _run('remote_prepare && echo "$REMOTE_NAME|$REMOTE_ROOT"', remote="ok",
             shipped=tmp_path)
    assert r.stdout.strip() == "fixture|/remote-root", r.stdout


def test_prepare_leaves_both_empty_when_unusable(tmp_path):
    (tmp_path / "nope.sh").write_text(FULL.replace("return 0", "return 1"))
    r = _run('remote_prepare; echo "name=[$REMOTE_NAME] root=[$REMOTE_ROOT]"',
             remote="nope", shipped=tmp_path)
    assert r.stdout.strip() == "name=[] root=[]", r.stdout


def test_prepare_does_not_leak_a_previous_selection(tmp_path):
    """The prefix of `$REMOTE_API` where the interface says, but the case is
    the empty string: a failed attempt must not leave the last one's name."""
    (tmp_path / "ok.sh").write_text(FULL)
    (tmp_path / "nope.sh").write_text(FULL.replace("return 0", "return 1"))
    script = ('remote_prepare >/dev/null 2>&1; '
              'PAZRAS_STORAGE_REMOTE=nope remote_prepare >/dev/null 2>&1; '
              'echo "[$REMOTE_NAME][$REMOTE_ROOT]"')
    r = _run(script, remote="ok", shipped=tmp_path)
    assert r.stdout.strip() == "[][]", r.stdout
