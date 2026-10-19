"""Put `engine/` on the path so tests import the packages the way the entry
points do (`from knowledge import ontology`). No installed distribution: the
runtime is stdlib-only and started unattended; pytest is a DEVELOPMENT
dependency and nothing under engine/ may import it.
"""
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))


@pytest.fixture(autouse=True)
def _no_inherited_git_env(monkeypatch):
    """Strip GIT_* for every test. Under the pre-commit hook in a LINKED
    WORKTREE git exports an absolute GIT_DIR, and a child `git -C /tmp/...`
    would commit into 06_SYSTEM's own index instead of the throw-away repo."""
    for key in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(key, raising=False)
