"""Put `engine/` on the path so tests import the packages the way the entry
points do (`from skills import scan`). No installed distribution: the runtime is
stdlib-only and started unattended; pytest is a DEVELOPMENT dependency and
nothing under engine/ may import it.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
