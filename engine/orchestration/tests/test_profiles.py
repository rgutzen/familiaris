"""profiles: the resolver. Environments are dicts and PAZRAS_DATA_DIR is a tmp path, so no
test reads a real key, a real login or the real approvals log."""
import json

import pytest

from orchestration import models, profiles

SECRET = "sk-super-secret-value"


def env(tmp_path, **kw):
    return {"PAZRAS_DATA_DIR": str(tmp_path), **kw}


def test_default_profile_is_private():
    assert profiles.active({}) == "private"
    assert profiles.active({"PI_PROFILE": ""}) == "private"
    assert profiles.active({"PI_PROFILE": "work"}) == "work"


def test_undeclared_profile_names_the_declared_ones():
    with pytest.raises(profiles.ProfileError) as e:
        profiles.active({"PI_PROFILE": "nope"})
    assert "private" in str(e.value) and "work" in str(e.value)


def test_key_present_resolves_with_privacy_class(tmp_path):
    r = profiles.resolve("deepseek-flash", "private", env(tmp_path, DEEPSEEK_API_KEY=SECRET))
    assert r.available and r.provider == "deepseek" and r.privacy == "CN-undisclosed"
    assert SECRET not in r.line()
    assert r.line().startswith("deepseek-flash -> deepseek/deepseek-flash (profile private")


def test_key_absent_names_the_variable(tmp_path):
    r = profiles.resolve("deepseek-flash", "private", env(tmp_path))
    assert not r.available and "DEEPSEEK_API_KEY" in r.reason
    r = profiles.resolve("deepseek-flash", "private", env(tmp_path, DEEPSEEK_API_KEY=" "))
    assert not r.available


def test_alias_resolves(tmp_path):
    r = profiles.resolve("deepseek-v4-flash", "private", env(tmp_path, DEEPSEEK_API_KEY="x"))
    assert r.available and r.model == "deepseek-flash"


def test_local_and_eu_classes(tmp_path):
    cat = models.load()
    ollama = next(e for e in cat["models"] if e["vendor"] == "ollama")
    assert profiles.resolve(ollama["id"], "private", env(tmp_path)).privacy == "local"
    r = profiles.resolve("mistral-small-2603", "private", env(tmp_path, MISTRAL_API_KEY="x"))
    assert r.privacy == "EU-no-training"


def test_work_has_no_cloud_model_available(tmp_path):
    e = env(tmp_path, DEEPSEEK_API_KEY=SECRET)   # a personal key must not leak across
    cat = models.load()
    for m in cat["models"]:
        r = profiles.resolve(m["id"], "work", e, cat=cat)
        if m["vendor"] in ("deepseek", "mistral", "typesafe"):
            assert not r.available, m["id"]
    r = profiles.resolve("mistral-small-2603", "work", e)
    assert not r.available and "MISTRAL_API_KEY_WORK" in r.reason


def test_login_file_checked_for_presence(tmp_path, monkeypatch):
    cfg = profiles.load()
    cfg["profiles"]["private"]["vendors"]["anthropic"]["login"] = str(tmp_path / "creds.json")
    r = profiles.resolve("claude-haiku-5-5", "private", env(tmp_path), cfg=cfg)
    assert not r.available and "creds.json" in r.reason
    (tmp_path / "creds.json").write_text(SECRET)
    r = profiles.resolve("claude-haiku-5-5", "private", env(tmp_path), cfg=cfg)
    assert r.available and SECRET not in r.line()


def test_jurisdiction_narrowed(tmp_path):
    cfg = profiles.load()
    cfg["profiles"]["private"]["jurisdictions"] = ["local", "EU"]
    r = profiles.resolve("deepseek-flash", "private", env(tmp_path, DEEPSEEK_API_KEY="x"), cfg=cfg)
    assert not r.available and "CN" in r.reason


def test_typesafe_is_not_served_by_pi(tmp_path):
    cat = models.load()
    ts = next(e for e in cat["models"] if e["vendor"] == "typesafe")
    r = profiles.resolve(ts["id"], "private", env(tmp_path), cat=cat)
    assert not r.available and "pi does not serve" in r.reason


def test_without_approval_never_falls_through(tmp_path):
    r = profiles.resolve("deepseek-flash", "work", env(tmp_path, DEEPSEEK_API_KEY="x"))
    assert not r.available
    assert not (tmp_path / profiles.APPROVALS).exists()


def test_approval_borrows_names_pool_and_logs_one_line(tmp_path):
    e = env(tmp_path, DEEPSEEK_API_KEY=SECRET)
    r = profiles.resolve("deepseek-flash", "work", e, approve="client doc is public")
    assert r.available and r.provider == "deepseek"
    assert "pool usd via profile private" in r.line()
    assert SECRET not in r.line()
    lines = (tmp_path / profiles.APPROVALS).read_text().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert {"ts", "model", "profile", "borrowed", "provider", "reason"} <= row.keys()
    assert (row["model"], row["profile"], row["borrowed"]) == ("deepseek-flash", "work", "private")
    assert SECRET not in lines[0]


def test_approval_without_a_lender_stays_unavailable_and_unlogged(tmp_path):
    r = profiles.resolve("deepseek-flash", "work", env(tmp_path), approve="why")
    assert not r.available and "no other declared profile" in r.reason
    assert not (tmp_path / profiles.APPROVALS).exists()


def test_available_model_needs_no_approval_and_logs_nothing(tmp_path):
    profiles.resolve("deepseek-flash", "private", env(tmp_path, DEEPSEEK_API_KEY="x"), approve="why")
    assert not (tmp_path / profiles.APPROVALS).exists()


def test_candidate_refused_even_with_approval(tmp_path):
    r = profiles.resolve("claude-fable-5-1", "private", env(tmp_path), approve="why")
    assert not r.available and r.reason == "a candidate, not callable"
    assert not (tmp_path / profiles.APPROVALS).exists()


def test_unknown_id_and_blank_reason_are_errors(tmp_path):
    with pytest.raises(profiles.ProfileError):
        profiles.resolve("no-such-model", "private", env(tmp_path))
    with pytest.raises(profiles.ProfileError):
        profiles.resolve("deepseek-flash", "work", env(tmp_path), approve="  ")


def test_providers_follow_the_profile():
    assert profiles.providers("private")["deepseek"] == "deepseek"
    assert profiles.providers("work")["deepseek"] == "deepseek-work"


def test_check_compares_under_the_active_profiles_provider():
    pi = "provider  model  context  max-out  thinking  images\n"
    c = {"stale_after_days": "60", "models": [{
        "id": "deepseek-flash", "vendor": "deepseek", "context": "1000000"}]}
    rep = models.compare(c, models.parse_pi_table(pi), [], profiles.providers("work"))
    assert any("deepseek-work" in f.message for f in rep.findings) and rep.skipped == 1


# --- the account a job bills (dev/schedule wave 2) ------------------------------

def test_the_declared_profile_is_read_from_the_record_never_the_process(monkeypatch):
    monkeypatch.setenv("PI_PROFILE", "work")
    assert profiles.declared({}) == profiles.load()["default"], (
        "a record without the field is read as the default, not as the caller's shell")
    assert profiles.declared({"profile": "work"}) == "work"
    with pytest.raises(profiles.ProfileError) as e:
        profiles.declared({"profile": "nope"})
    assert "private" in str(e.value)


def test_the_account_environment_keeps_the_primary_home_implicit():
    assert profiles.account_env("private")["CLAUDE_CONFIG_DIR"] is None, (
        "pi-profile measured: pointing CLAUDE_CONFIG_DIR at ~/.claude makes Claude "
        "look for a login that is not there")
    work = profiles.account_env("work")
    assert work["PI_PROFILE"] == "work"
    assert work["CLAUDE_CONFIG_DIR"].endswith(".claude-work")
    assert work["DEEPSEEK_API_KEY"] is None, "the personal key is unset, not read"
    assert "DEEPSEEK_API_KEY" not in profiles.account_env("private")


def test_the_marker_is_read_upward_and_never_invents_a_profile(tmp_path):
    tree = tmp_path / "a" / "b" / "repo"
    tree.mkdir(parents=True)
    assert profiles.marker(tree) == ("", None)
    (tmp_path / "a" / ".pi-profile").write_text("work\n")
    name, path = profiles.marker(tree)
    assert name == "work" and path == tmp_path / "a" / ".pi-profile"
    assert profiles.marker(tmp_path / "elsewhere") == ("", None)


# ── 15a: a spent quota window is unavailable ─────────────────────────────────
def _login(tmp_path):
    """A cfg whose Claude login is a file under tmp_path, so the window is the only
    thing that can make the model unavailable."""
    cfg = profiles.load()
    cfg["profiles"]["private"]["vendors"]["anthropic"]["login"] = str(tmp_path / "creds.json")
    (tmp_path / "creds.json").write_text(SECRET)
    return cfg


def test_a_spent_window_makes_a_quota_model_unavailable(tmp_path):
    cfg = _login(tmp_path)
    r = profiles.resolve("claude-haiku-5-5", "private", env(tmp_path), cfg=cfg, window=0.99)
    assert not r.available
    assert "window is spent" in r.reason and "0.99" in r.reason
    assert not (tmp_path / profiles.APPROVALS).exists()


def test_a_window_below_the_threshold_still_runs(tmp_path):
    cfg = _login(tmp_path)
    for reading in (0.0, 0.5, 0.97):
        r = profiles.resolve("claude-haiku-5-5", "private", env(tmp_path), cfg=cfg, window=reading)
        assert r.available, reading


def test_no_reading_is_never_a_block(tmp_path):
    cfg = _login(tmp_path)
    r = profiles.resolve("claude-haiku-5-5", "private", env(tmp_path), cfg=cfg, window=None)
    assert r.available


def test_a_usd_pool_model_ignores_the_window(tmp_path):
    r = profiles.resolve("deepseek-flash", "private",
                         env(tmp_path, DEEPSEEK_API_KEY=SECRET), window=1.0)
    assert r.available


def test_the_threshold_is_read_from_the_config(tmp_path):
    cfg = _login(tmp_path)
    cfg["window_closed_at"] = "1.01"          # never reached
    r = profiles.resolve("claude-haiku-5-5", "private", env(tmp_path), cfg=cfg, window=0.99)
    assert r.available


def test_the_window_is_probed_once_per_interval(tmp_path, monkeypatch):
    from orchestration import price
    calls = []

    def fake(env=None):
        calls.append(1)
        return 0.99

    monkeypatch.setattr(price, "live_quota", fake)
    profiles._ROOM.clear()
    cfg = _login(tmp_path)
    e = env(tmp_path)
    for _ in range(3):
        r = profiles.resolve("claude-haiku-5-5", "private", e, cfg=cfg)
        assert not r.available
    assert len(calls) == 1
    profiles._ROOM.clear()


def test_a_model_beyond_the_active_profile_is_not_gated_by_its_window(tmp_path, monkeypatch):
    """`live_quota` reads the ACTIVE account, so a resolve for another profile must
    not read the wrong one's window -- it reads none."""
    from orchestration import price

    def boom(env=None):                      # never called
        raise AssertionError("probed a non-active profile")

    monkeypatch.setattr(price, "live_quota", boom)
    profiles._ROOM.clear()
    r = profiles.resolve("mistral-small-2603", "work",
                         env(tmp_path, MISTRAL_API_KEY_WORK=SECRET))
    assert r.available
