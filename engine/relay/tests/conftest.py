"""Put `engine/` on the path, and hand every relay test a fake Bot API."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from relay_fakes import FakeBot  # noqa: E402


@pytest.fixture
def bot():
    return FakeBot()
