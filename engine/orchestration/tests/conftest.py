"""Put `engine/` on the path so tests import the packages the way the entry
points do (`from orchestration import specs`)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import pytest


@pytest.fixture(autouse=True)
def _private_data_dir(tmp_path, monkeypatch):
    """No test writes the machine's data directory: `jevlog` appends there on
    every stubbed Jev answer, and `labels.verify` reads it."""
    monkeypatch.setenv("PAZRAS_DATA_DIR", str(tmp_path / "pazras-data"))


@pytest.fixture(autouse=True)
def _no_quota_probe(monkeypatch):
    """No test asks the live Claude usage probe (14d): a pick made in a test has no
    reading, which is weight 1, decision 24."""
    from orchestration import price
    monkeypatch.setattr(price, "live_quota", lambda env=None: None)
