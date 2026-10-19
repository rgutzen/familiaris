"""profile.py: which file wins, what the environment overrides, and that a
broken profile is reported rather than raised."""
import pathlib
import subprocess

import pytest

from lib import _miniyaml, profile, roots

GOOD = """\
version: 1
install: /opt/fam
para_root: /srv/para
areas:
  A_Work:
    code: A
    tag: work
    description: Paid work
storage:
  archive_mount: ~/disk
models:
  embed: nomic-embed-text
"""


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("PAZRAS_PROFILE", "PARA_ROOT", "PAZRAS_INSTALL"):
        monkeypatch.delenv(key, raising=False)


def _config(tmp_path, **files):
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    return tmp_path


def test_the_instance_file_beats_the_example(tmp_path):
    cfg = _config(tmp_path, **{profile.NAME: GOOD, profile.EXAMPLE: "version: 1\n"})
    p = profile.resolve(cfg)
    assert p.source == cfg / profile.NAME
    assert p.install == pathlib.Path("/opt/fam")
    assert p.para_root == pathlib.Path("/srv/para")
    assert p.areas["A_Work"]["code"] == "A"
    assert p.storage["archive_mount"] == str(pathlib.Path.home() / "disk")
    assert p.problems == []


def test_a_fresh_clone_runs_on_the_example(tmp_path):
    cfg = _config(tmp_path, **{profile.EXAMPLE: GOOD})
    assert profile.resolve(cfg).source == cfg / profile.EXAMPLE


def test_the_environment_beats_the_file(tmp_path, monkeypatch):
    cfg = _config(tmp_path, **{profile.NAME: GOOD})
    monkeypatch.setenv("PARA_ROOT", str(tmp_path / "scratch"))
    monkeypatch.setenv("PAZRAS_INSTALL", str(tmp_path / "inst"))
    p = profile.resolve(cfg)
    assert p.para_root == tmp_path / "scratch"
    assert p.install == tmp_path / "inst"


def test_pazras_profile_names_the_file(tmp_path, monkeypatch):
    other = tmp_path / "elsewhere.yaml"
    other.write_text(GOOD)
    monkeypatch.setenv("PAZRAS_PROFILE", str(other))
    assert profile.resolve(tmp_path).source == other


@pytest.mark.parametrize("text, needle", [
    ("areas: [a, b]\n", "areas"),
    ("colour: blue\n", "unknown key"),
    ("areas:\n  A_X:\n    code: A\n", "missing tag, description"),
    ("areas:\n  A_X:\n    code: A\n    tag: x\n    description: x\n"
     "  B_Y:\n    code: A\n    tag: y\n    description: y\n", "already used"),
])
def test_a_broken_profile_is_reported_not_raised(tmp_path, text, needle):
    p = profile.resolve(_config(tmp_path, **{profile.NAME: text}))
    assert any(needle in problem for problem in p.problems), p.problems
    # The defaults stand, so the guard that imports roots keeps working.
    assert p.install == pathlib.Path(profile.DEFAULT_INSTALL).expanduser()
    assert p.areas == {}


def test_both_shipped_profiles_parse_clean():
    for name in (profile.NAME, profile.EXAMPLE):
        path = roots.CONFIG / name
        if not path.exists():           # the instance file does not travel
            continue
        assert profile._validate(_miniyaml.load(path.read_text())) == [], name


def test_the_shell_reads_the_same_areas(tmp_path):
    cfg = _config(tmp_path, **{profile.NAME: GOOD})
    script = profile.shell(profile.resolve(cfg), "structure")
    out = subprocess.run(["bash", "-c", script + 'echo "${AREAS[A_Work]}|$PAZRAS_STORAGE_ARCHIVE_MOUNT"'],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == f"work:Paid work:A|{pathlib.Path.home() / 'disk'}"


# ── the identity, and what a placeholder is (P2) ────────────────────────────

MENTION = """\
version: 1
identity:
  name: %s
  handle: %s
"""


def test_the_identity_is_name_words_then_the_handle(tmp_path):
    p = profile.resolve(_config(tmp_path, **{
        profile.NAME: MENTION % ("Zaphod Beeblebrox", "zaphod42")}))
    assert profile.identity_words(p) == ["Zaphod", "Beeblebrox", "zaphod42"]


def test_the_examples_own_values_name_nobody(tmp_path):
    """The reader that searches for the identity must be able to tell the
    shipped example from a person: `Your Name` is a caption, and a search for
    `Name` matches the inside of every identifier in the tree."""
    text = MENTION % ("Your Name", "your-handle")
    p = profile.resolve(_config(tmp_path, **{profile.NAME: text,
                                            profile.EXAMPLE: text}))
    assert profile.identity_words(p) == []


def test_a_value_is_dropped_on_its_own(tmp_path):
    """Per value, not per file: an install that edited the name is searched
    for by name, even while it still carries the example's handle."""
    example = MENTION % ("Your Name", "your-handle")
    p = profile.resolve(_config(tmp_path, **{
        profile.NAME: MENTION % ("Zaphod", "your-handle"),
        profile.EXAMPLE: example}))
    assert profile.identity_words(p) == ["Zaphod"]


def test_the_placeholder_is_read_from_the_example_beside_the_profile(tmp_path):
    """Not from a copy of today's wording: an install whose example says
    something else is judged against ITS OWN example file."""
    p = profile.resolve(_config(tmp_path, **{
        profile.NAME: MENTION % ("Your Name", "your-handle"),
        profile.EXAMPLE: MENTION % ("Trillian Astra", "trillian")}))
    assert profile.identity_words(p) == ["Your", "Name", "your-handle"]


def test_no_profile_at_all_has_no_identity():
    assert profile.identity_words(profile.resolve(pathlib.Path("/nonexistent"))) == []
