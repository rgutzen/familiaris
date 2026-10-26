"""The data root is read from `lib/roots`, so every reader honours `$PAZRAS_DATA_DIR`.

`context/cli.py`'s predecessor spelled `~/.local/share/pazras` without the override: no verb
of its read `inv.base` yet, so nothing failed, and the first one that did would have
written past a test's or a relocated machine's data root (fixed 2026-10-20)."""
import importlib.machinery
import pathlib
import sys

ENGINE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ENGINE))
from lib import roots  # noqa: E402


def test_the_override_wins_and_an_empty_one_does_not(tmp_path):
    assert roots.data_root({"PAZRAS_DATA_DIR": str(tmp_path)}) == tmp_path
    default = pathlib.Path(roots.DATA_DEFAULT).expanduser()
    assert roots.data_root({"PAZRAS_DATA_DIR": ""}) == default
    assert roots.data_root({}) == default


def _front():
    """`engine/familiar` has no `.py` extension; load it as a module."""
    import importlib.util
    spec = importlib.util.spec_from_loader(
        "familiar_front_door",
        importlib.machinery.SourceFileLoader("familiar_front_door", str(ENGINE / "familiar")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _base_seen(monkeypatch, tmp_path) -> pathlib.Path:
    """Run `familiar context tree` with the verb replaced by a probe that
    records the `inv.base` it was handed."""
    import context.cli as ctx
    monkeypatch.setenv("PAZRAS_DATA_DIR", str(tmp_path))
    seen = {}
    monkeypatch.setattr(ctx, "cmd_tree", lambda inv: seen.setdefault("base", inv.base) and 0)
    _front().main(["context", "tree"])
    return pathlib.Path(seen["base"])


def test_familiar_context_honours_the_override(monkeypatch, tmp_path):
    assert _base_seen(monkeypatch, tmp_path) == tmp_path
