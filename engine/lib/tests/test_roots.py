"""roots.py and roots.sh declare the same roots, and every root is inside REPO."""
import pathlib
import subprocess

from lib import roots

LIB = pathlib.Path(roots.__file__).resolve().parent


TWINS = {"REPO": "PAZRAS_REPO", "ENGINE": "PAZRAS_ENGINE", "CONFIG": "PAZRAS_CONFIG",
         "MEMORY": "PAZRAS_MEMORY", "DEV": "PAZRAS_DEV",
         "INSTALL": "PAZRAS_INSTALL", "PARA_ROOT": "PARA_ROOT"}


def _shell_roots(env=None) -> dict:
    out = subprocess.run(
        ["bash", "-c", f'source "{LIB}/roots.sh"; printf "%s\\n" '
         + " ".join(f'"${v}"' for v in TWINS.values())],
        capture_output=True, text=True, check=True, env=env).stdout.split("\n")
    return dict(zip(TWINS, out))


def test_the_shell_twin_agrees():
    sh = _shell_roots()
    for name in TWINS:
        assert sh[name] == str(getattr(roots, name)), name


def test_the_environment_moves_the_shell_roots(tmp_path):
    import os
    env = dict(os.environ, PARA_ROOT=str(tmp_path / "para"),
               PAZRAS_INSTALL=str(tmp_path / "install"))
    sh = _shell_roots(env)
    assert sh["PARA_ROOT"] == str(tmp_path / "para")
    assert sh["INSTALL"] == str(tmp_path / "install")


def test_every_named_home_sits_under_a_root():
    tops = (roots.ENGINE, roots.CONFIG, roots.MEMORY, roots.DEV)
    for name in ("LIB", "ROUTER", "JOURNAL", "KNOWLEDGE", "SKILLS", "ONTOLOGY",
                 "BOUNDARIES", "USER", "CONVENTIONS", "SUBAGENTS",
                 "MASTER_CONFIG", "PROFILE_FILE", "PROFILE_EXAMPLE",
                 "VAULT_EXAMPLE", "BOUNDARIES_JSON", "UNITS_STAGING",
                 "PARA_READMES", "BACKUP_EXCLUDES", "MIRROR_EXCLUDES"):
        p = getattr(roots, name)
        assert p == roots.REPO / roots.rel(p), name
        assert any(t in p.parents or p == t for t in tops) or \
            p.parent == roots.REPO, name


def test_tilde_names_the_install(tmp_path, monkeypatch):
    """A controlled install under home: the live one may be anywhere
    (`PAZRAS_INSTALL=/opt/familiaris` is valid), and the case outside home
    is the next test's."""
    monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(roots, "INSTALL", tmp_path / "home" / "06_SYSTEM")
    rel = roots.rel(roots.KNOWLEDGE)
    assert roots.tilde(roots.KNOWLEDGE) == f"~/06_SYSTEM/{rel}"
    assert roots.from_home(roots.KNOWLEDGE) == f"06_SYSTEM/{rel}"


def test_an_install_outside_home_spells_itself_absolutely(tmp_path, monkeypatch):
    """The scratch recipe puts the install outside home, and nothing may raise.

    Measured 2026-10-14, on the published tree with the README's own recipe
    (`HOME=/tmp/h PARA_ROOT=/tmp/p`, install at `/tmp/tut/clone`): `familiar
    context l1` died with `ValueError: '/tmp/tut/clone/memory' is not in the
    subpath of '/tmp/tut/home'`, raised while building BEGIN. The marker is
    written by three modules and the compile step by a fourth, so the recipe in
    the README did not work for any command that generates a block.
    """
    monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(roots, "INSTALL", tmp_path / "elsewhere")
    here = (tmp_path / "elsewhere" / roots.rel(roots.KNOWLEDGE)).as_posix()
    assert roots.tilde(roots.KNOWLEDGE) == here
    assert roots.from_home(roots.KNOWLEDGE) == here


def test_every_js_twin_agrees():
    """A harness plugin's `// roots-twin: NAME` line names roots.NAME's install path."""
    import re
    twin = re.compile(r'"06_SYSTEM/([^"]+)"\)?;?\s*//\s*roots-twin:\s*([A-Z_]+)'
                      r'|`\$\{[^}]+\}/06_SYSTEM/([^`]+)`;?\s*//\s*roots-twin:\s*([A-Z_]+)')
    seen = 0
    for path in roots.ENGINE.rglob("*"):
        if path.suffix not in (".js", ".mjs", ".ts") or "node_modules" in path.parts:
            continue
        for line in path.read_text().splitlines():
            if "roots-twin:" not in line or "roots-twin: DATA_DEFAULT" in line:
                continue
            m = twin.search(line)
            assert m, f"{path}: unparseable roots-twin line: {line!r}"
            value, name = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            assert value == roots.rel(getattr(roots, name)), (path, name, value)
            seen += 1
    assert seen >= 5


def test_every_js_data_root_twin_agrees():
    """A plugin outside Python spells the data root's default on a line tagged
    `// roots-twin: DATA_DEFAULT`, and that spelling is `roots.DATA_DEFAULT`."""
    import re
    twin = re.compile(r'homedir\(\), "([^"]+)"\);?\s*//\s*roots-twin:\s*DATA_DEFAULT')
    seen = 0
    for path in roots.ENGINE.rglob("*"):
        if path.suffix not in (".js", ".mjs", ".ts") or "node_modules" in path.parts:
            continue
        for line in path.read_text().splitlines():
            if "roots-twin: DATA_DEFAULT" in line:
                m = twin.search(line)
                assert m, f"{path}: unparseable data-root twin: {line!r}"
                assert "~/" + m.group(1) == roots.DATA_DEFAULT, (path, m.group(1))
                seen += 1
    assert seen >= 1


def test_the_vault_guard_refuses_only_the_target_nobody_chose(tmp_path, monkeypatch):
    """An explicit PAZRAS_MEMORY_DIR is a decision; the default is the accident.

    The export regenerates a stage tree's leaves with `PAZRAS_MEMORY_DIR` set to
    `{stage}/memory`, which no running tree owns on purpose -- so a guard that
    compared the target against this tree's vault would refuse the one caller
    that must be allowed.
    """
    monkeypatch.delenv(roots.VAULT_ENV, raising=False)
    monkeypatch.setattr(roots, "INSTALL", tmp_path / "elsewhere")
    elsewhere = tmp_path / "elsewhere" / roots.MEMORY_REL

    try:
        roots.guard_vault_write(elsewhere, "test")
    except SystemExit as exc:
        assert "PAZRAS_MEMORY_DIR" in str(exc)
    else:
        raise AssertionError("the unchosen target was not refused")

    monkeypatch.setenv(roots.VAULT_ENV, str(elsewhere))
    roots.guard_vault_write(elsewhere, "test")          # a decision: allowed

    monkeypatch.delenv(roots.VAULT_ENV, raising=False)
    roots.guard_vault_write(roots.MEMORY, "test")       # this tree's own: allowed
