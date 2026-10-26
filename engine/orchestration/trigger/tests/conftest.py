"""Put `engine/` on the path so the tests import the package the way the entry
points do (`from orchestration import trigger`). The sibling suite's conftest is
not an ancestor of this directory, so it must be repeated here."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
