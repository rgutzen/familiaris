"""The model seam: one key, and the default does not leave the machine.

`harness.model.MODEL` is `config/profile.yaml`'s `models.consolidation`, or the
fallback beside it -- and the fallback is what a tree with NO profile runs on,
which is every fresh clone and every scratch run. It ships LOCAL (P5): the
nightly pass reads session transcripts, and a default that posts them to a third
party is disclosure the reader never chose, in a file they may never open.

Two things can move under that decision, so both are held here:

  1. `model.DEFAULT_MODEL` -- the constant. If it changes to a provider's id,
     this fails.
  2. `config/profile.example.yaml`'s `models.consolidation` -- the OTHER shipped
     default, and the one a reader actually runs on. A local constant beside an
     example profile naming a cloud model is the same disclosure with an extra
     step.

"Local" is not decided here: it is `local_providers:` in `config/boundaries/*.yaml`,
the list the guard uses to decide whether a read leaves the machine. The union of
every domain file's list is the vocabulary, so this test moves when the boundary
moves rather than restating it. Where a tree declares none -- the deny-list does
not travel, and a reader may have emptied the list -- the assertion skips rather
than passing, because "no local providers declared" is not evidence of anything.
"""
import pathlib

import pytest

from harness import model
from lib import _miniyaml, roots


def _local_providers() -> list:
    """Every provider the boundaries call local, in file order, deduped."""
    out: list[str] = []
    for path in sorted((roots.CONFIG / "boundaries").glob("*.yaml")):
        if path.name.endswith(".example.yaml"):
            continue          # a template is not an input -- `_boundaries.sources()`
        try:
            cfg = _miniyaml.load(path.read_text()) or {}
        except Exception:     # a file this test cannot read is not this test's subject
            continue
        for prov in (cfg.get("local_providers") or []):
            if prov not in out:
                out.append(prov)
    return out


def _provider(model_id: str) -> str:
    """`ollama/qwen3:4b` -> `ollama`. A bare id has no provider part, and pi
    reads it against whatever is configured -- which is not something this test
    can call local, so it comes back empty and fails the membership check."""
    return model_id.split("/", 1)[0] if "/" in model_id else ""


def test_the_fallback_model_is_local():
    providers = _local_providers()
    if not providers:
        pytest.skip("this tree declares no `local_providers:` in config/boundaries/")
    assert _provider(model.DEFAULT_MODEL) in providers, (
        f"the fallback model {model.DEFAULT_MODEL!r} is not one of "
        f"{providers} -- a tree with no profile would send the night's "
        f"transcripts off the machine")


def test_the_example_profile_ships_the_same_default():
    """The second shipped default, and the one that actually runs."""
    example = roots.CONFIG / "profile.example.yaml"
    if not example.exists():
        pytest.skip("no config/profile.example.yaml in this tree")
    providers = _local_providers()
    if not providers:
        pytest.skip("this tree declares no `local_providers:` in config/boundaries/")
    cfg = _miniyaml.load(example.read_text()) or {}
    chosen = (cfg.get("models") or {}).get("consolidation", "")
    assert chosen, "config/profile.example.yaml names no `models.consolidation`"
    assert _provider(chosen) in providers, (
        f"the example profile's model {chosen!r} is not one of {providers} -- "
        f"the value a reader runs without editing anything")


def test_the_seam_is_the_profile_and_nothing_else():
    """`MODEL` is the profile's value where there is one: the swap must not
    need a code change, which is what "seam" means here."""
    configured = roots.PROFILE.models.get("consolidation")
    if not configured:
        assert model.MODEL == model.DEFAULT_MODEL
    else:
        assert model.MODEL == configured


def test_the_id_is_passed_to_pi_verbatim():
    """Whatever the profile says reaches `--model` unchanged. A seam that
    rewrote the id would be a second place models are named."""
    src = pathlib.Path(model.__file__).read_text()
    assert '"--model", MODEL' in src
