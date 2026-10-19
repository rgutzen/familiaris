"""The Jev client: transport, status classes, and the key file (item 2a).

No network. Every test stubs `urllib` at `urlopen`, so the status handling is
exercised without a key and without a live endpoint -- including the failures,
which are the ones that matter: this runs unattended.
"""
import io
import json
import os
import pathlib
import stat
import urllib.error

import pytest

from harness import jev

KEY = "jv_live_test_key_not_real"


def _key_file(tmp_path, body="TYPESAFE_API_KEY=jv_live_x\n", mode=0o600):
    p = tmp_path / "jev.env"
    p.write_text(body)
    os.chmod(p, mode)
    return p


class _Resp(io.BytesIO):
    """Minimal context-manager response, as urlopen returns."""
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, *a):
        return super().read(*a)


def _stub(monkeypatch, *, status=200, body=None, raises=None):
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req)
        if raises is not None:
            raise raises
        if status != 200:
            raise urllib.error.HTTPError(req.full_url, status, "err", {},
                                         _Resp(json.dumps(body or {}).encode()))
        return _Resp(json.dumps(body or {}).encode())

    monkeypatch.setattr(jev.urllib.request, "urlopen", fake_urlopen)
    return calls


# ── the happy path ───────────────────────────────────────────────────────────

def test_ask_posts_state_model_and_questions(monkeypatch):
    calls = _stub(monkeypatch, body={"model": "jev-1.13.0",
                                     "answers": {"q1": {"type": "noul", "noul": 0.9}},
                                     "usage": {"input_tokens": 10, "output_tokens": 2}})
    out = jev.ask("some state", {"q1": {"type": "noul", "instructions": "?"}}, key=KEY)
    assert out["answers"]["q1"]["noul"] == 0.9
    sent = json.loads(calls[0].data)
    assert sent["state"] == "some state"
    assert sent["model"] == jev.MODEL
    assert sent["questions"]["q1"]["type"] == "noul"


def test_the_pinned_model_id_is_sent_not_the_alias(monkeypatch):
    """A floated alias makes logged probabilities uninterpretable through time."""
    calls = _stub(monkeypatch, body={"answers": {"q": {"type": "noul", "noul": 0.5}}})
    jev.ask("s", {"q": {"type": "noul", "instructions": "?"}}, key=KEY)
    assert json.loads(calls[0].data)["model"] == "jev-1.13.0"
    assert "latest" not in json.dumps(json.loads(calls[0].data))


def test_the_bearer_header_carries_the_key(monkeypatch):
    calls = _stub(monkeypatch, body={"answers": {"q": {"type": "noul", "noul": 0.5}}})
    jev.ask("s", {"q": {"type": "noul", "instructions": "?"}}, key=KEY)
    assert calls[0].get_header("Authorization") == f"Bearer {KEY}"


def test_an_empty_question_map_is_refused_before_the_call(monkeypatch):
    """Fatal, because it is a programming error: a caller that built no
    questions will build none tomorrow either."""
    calls = _stub(monkeypatch, body={"answers": {}})
    with pytest.raises(jev.JevError) as exc:
        jev.ask("s", {}, key=KEY)
    assert exc.value.kind == "invalid-request" and exc.value.fatal
    assert not calls, "an empty map must not reach the network"


# ── the status classes (the spec's exit criterion) ───────────────────────────

@pytest.mark.parametrize("status,kind,fatal", [
    (401, "key-rejected", True),
    (422, "invalid-request", True),
    (429, "rate-limited", False),
    (529, "overloaded", False),
])
def test_each_status_class_becomes_a_named_error(monkeypatch, status, kind, fatal):
    """401/422 are fatal because no amount of waiting fixes a bad key or a
    malformed schema; 429/529 are not, because the next pass is the retry."""
    _stub(monkeypatch, status=status, body={"detail": "x"})
    with pytest.raises(jev.JevError) as exc:
        jev.ask("s", {"q": {"type": "noul", "instructions": "?"}}, key=KEY)
    assert exc.value.kind == kind
    assert exc.value.fatal is fatal


def test_a_429_names_the_retry_happening_elsewhere(monkeypatch):
    """No retry loop: the next pass is the retry, and the message says so."""
    _stub(monkeypatch, status=429, body={})
    with pytest.raises(jev.JevError) as exc:
        jev.ask("s", {"q": {"type": "noul", "instructions": "?"}}, key=KEY)
    assert "next pass" in str(exc.value)


def test_an_unexpected_status_is_transport_and_not_fatal(monkeypatch):
    _stub(monkeypatch, status=500, body={})
    with pytest.raises(jev.JevError) as exc:
        jev.ask("s", {"q": {"type": "noul", "instructions": "?"}}, key=KEY)
    assert exc.value.kind == "transport" and not exc.value.fatal


def test_an_unreachable_endpoint_is_a_named_transport_error(monkeypatch):
    _stub(monkeypatch, raises=urllib.error.URLError("no route to host"))
    with pytest.raises(jev.JevError) as exc:
        jev.ask("s", {"q": {"type": "noul", "instructions": "?"}}, key=KEY)
    assert exc.value.kind == "transport"


def test_a_non_json_body_is_a_bad_response_not_a_crash(monkeypatch):
    def fake(req, timeout=None):
        return _Resp(b"<html>gateway</html>")
    monkeypatch.setattr(jev.urllib.request, "urlopen", fake)
    with pytest.raises(jev.JevError) as exc:
        jev.ask("s", {"q": {"type": "noul", "instructions": "?"}}, key=KEY)
    assert exc.value.kind == "bad-response"


def test_a_response_without_an_answers_map_is_refused(monkeypatch):
    """Silence must not read as 'answered': a caller recording an answer nobody
    made is worse than a caller recording a failure."""
    _stub(monkeypatch, body={"model": "jev-1.13.0"})
    with pytest.raises(jev.JevError) as exc:
        jev.ask("s", {"q": {"type": "noul", "instructions": "?"}}, key=KEY)
    assert exc.value.kind == "bad-response"


# ── the key file ─────────────────────────────────────────────────────────────

def test_load_key_reads_the_variable(tmp_path):
    assert jev.load_key(_key_file(tmp_path)) == "jv_live_x"


def test_load_key_strips_quotes_and_ignores_comments_and_blanks(tmp_path):
    p = _key_file(tmp_path, body='# a comment\n\nTYPESAFE_API_KEY="jv_live_q"\n')
    assert jev.load_key(p) == "jv_live_q"


def test_a_world_readable_key_is_refused_rather_than_used(tmp_path):
    """The mode IS the protection. A 644 key is already exposed, and reporting
    success while using it would hide that."""
    p = _key_file(tmp_path, mode=0o644)
    with pytest.raises(jev.JevError) as exc:
        jev.load_key(p)
    assert exc.value.kind == "bad-mode" and exc.value.fatal
    assert "chmod 600" in str(exc.value)


def test_a_group_readable_key_is_refused(tmp_path):
    p = _key_file(tmp_path, mode=0o640)
    with pytest.raises(jev.JevError):
        jev.load_key(p)


def test_an_absent_key_file_names_where_to_put_it(tmp_path):
    with pytest.raises(jev.JevError) as exc:
        jev.load_key(tmp_path / "nope.env")
    assert exc.value.kind == "no-key" and exc.value.fatal
    assert "0b" in str(exc.value)


def test_a_key_file_without_the_variable_is_refused(tmp_path):
    p = _key_file(tmp_path, body="SOMETHING_ELSE=1\n")
    with pytest.raises(jev.JevError) as exc:
        jev.load_key(p)
    assert exc.value.kind == "no-key"


def test_an_empty_key_is_refused(tmp_path):
    p = _key_file(tmp_path, body="TYPESAFE_API_KEY=\n")
    with pytest.raises(jev.JevError):
        jev.load_key(p)


def test_the_default_key_path_is_outside_every_repository():
    """Step 0b's exit criterion, asserted rather than eyeballed: the credential
    must not sit in a git worktree, or `git add -A` could commit it."""
    p = jev.KEY_PATH
    assert p.name == "jev.env" and p.parent.name == "pazras"
    parts = p.parts
    assert not any((pathlib.Path(*parts[:i]) / ".git").exists()
                   for i in range(1, len(parts) + 1)), \
        f"{p} is inside a git worktree"


# ── the live check's shape (2b closes 0d) ────────────────────────────────────

def test_models_hits_the_models_endpoint(monkeypatch):
    calls = _stub(monkeypatch, body={"data": [{"id": "jev-1.13.0"}]})
    out = jev.models(key=KEY)
    assert calls[0].full_url == jev.MODELS_ENDPOINT
    assert out["data"][0]["id"] == "jev-1.13.0"


# ── the recordable answer shape ──────────────────────────────────────────────

def test_a_noul_answer_records_no_confidence():
    """The correction this track made to its own record: a noul returns one
    number. Writing a confidence there would be inventing one."""
    got = jev.answer_fields({"type": "noul", "noul": 0.91})
    assert got["probability"] == 0.91
    assert got["confidence"] is None
    assert got["probabilities"] is None


def test_a_choice_answer_records_probabilities_and_confidence():
    got = jev.answer_fields({"type": "choice", "choice": "a",
                             "probabilities": {"a": 0.7, "b": 0.3},
                             "confidence": 0.8})
    assert got["choice"] == "a" and got["confidence"] == 0.8
    assert got["probabilities"] == {"a": 0.7, "b": 0.3}


def test_a_score_answer_records_the_score_and_distribution():
    got = jev.answer_fields({"type": "score", "score": 1.4,
                             "probabilities": {"0": 0.1, "1": 0.4, "2": 0.5},
                             "confidence": 0.6})
    assert got["score"] == 1.4 and got["confidence"] == 0.6


# ── cost ─────────────────────────────────────────────────────────────────────

def test_cost_counts_input_tokens_only():
    """Output is free; multiplying output_tokens by the rate overstates cost."""
    assert jev.cost_usd({"input_tokens": 1_000_000, "output_tokens": 5_000_000}) == 0.042


def test_cost_of_a_missing_usage_is_zero_not_an_error():
    assert jev.cost_usd({}) == 0.0
