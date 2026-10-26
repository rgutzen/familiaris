"""The healthcheck runs a tier, leaves its result, and the greeting reads it.

The banner is the failure surface the owner chose (dev/checks, decision
dec-68867139): a red tier stays visible until a green run replaces it, and a
tier whose timer stopped shows as stale. The greeting is bash that starts with
every terminal, so it is tested as bash, against status files written by hand.
"""
import os
import pathlib
import subprocess
import sys
import time

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[2]
HEALTHCHECK = ENGINE / "checks/healthcheck.sh"
ALIASES = ENGINE / "host/pazras-aliases.sh"


def banner(data: pathlib.Path) -> str:
    """What `pazras_healthcheck_banner` writes to stderr for this data dir."""
    if not ALIASES.exists():
        pytest.skip("the greeting lives in the user's shell aliases, which the "
                    "classification omits; the tier runs and their status "
                    "files are tested below without it")
    r = subprocess.run(
        ["bash", "-c", f'source "{ALIASES}" >/dev/null 2>&1; '
                       f'PAZRAS_DATA="{data}"; pazras_healthcheck_banner'],
        capture_output=True, text=True, env={**os.environ, "PAZRAS_DATA_DIR": str(data)})
    assert r.returncode == 0, r.stderr
    return r.stderr


def status(data, tier, result, age=0, fail=0, stale_after=86400 * 2):
    d = pathlib.Path(data) / "healthcheck"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{tier}.status").write_text(
        f"tier={tier}\nresult={result}\ntime={int(time.time()) - age}\nfail={fail}\n"
        f"warn=0\nseconds=1\nstale_after={stale_after}\n")


def test_a_green_tier_says_nothing(tmp_path):
    status(tmp_path, "daily", "OK")
    status(tmp_path, "weekly", "WARN")          # a warning is not a failure
    assert banner(tmp_path) == ""


def test_a_tier_that_never_ran_says_nothing(tmp_path):
    assert banner(tmp_path) == ""


def test_a_red_tier_is_named_with_its_command(tmp_path):
    status(tmp_path, "weekly", "FAIL", fail=3)
    out = banner(tmp_path)
    assert "weekly healthcheck: 3 failure(s)" in out
    assert "familiar checks healthcheck --tier weekly" in out


def test_the_next_green_run_clears_it(tmp_path):
    status(tmp_path, "daily", "FAIL", fail=1)
    assert banner(tmp_path) != ""
    status(tmp_path, "daily", "OK")
    assert banner(tmp_path) == ""


def test_a_tier_whose_timer_stopped_is_reported_as_stale(tmp_path):
    status(tmp_path, "daily", "OK", age=86400 * 3, stale_after=86400 * 2)
    out = banner(tmp_path)
    assert "daily healthcheck: last ran 3 d ago" in out and "timer has stopped" in out


def test_two_red_tiers_do_not_hide_each_other(tmp_path):
    status(tmp_path, "daily", "FAIL", fail=1)
    status(tmp_path, "weekly", "FAIL", fail=2)
    out = banner(tmp_path)
    assert "daily healthcheck" in out and "weekly healthcheck" in out


def test_a_damaged_status_file_is_ignored_not_fatal(tmp_path):
    d = tmp_path / "healthcheck"
    d.mkdir()
    (d / "daily.status").write_text("time=soon\nstale_after=never\nresult=FAIL\n")
    assert banner(tmp_path) == ""


def run_hc(data, *args, env=None):
    return subprocess.run(["bash", str(HEALTHCHECK), *args], capture_output=True, text=True,
                          env={**os.environ, "PAZRAS_DATA_DIR": str(data), **(env or {})})


def test_an_unknown_tier_or_flag_is_a_usage_error(tmp_path):
    assert run_hc(tmp_path, "--tier", "hourly").returncode == 2
    assert run_hc(tmp_path, "--nope").returncode == 2


def test_only_runs_one_section_and_leaves_no_result(tmp_path):
    r = run_hc(tmp_path, "--only", "hc-mounts")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "home filesystem usage" in r.stdout and "stow packages" in r.stdout
    assert "bootstrap.sh" not in r.stdout          # the other sections ran nothing
    assert not (tmp_path / "healthcheck").exists()


def test_only_an_id_the_script_does_not_own_is_refused(tmp_path):
    assert run_hc(tmp_path, "--only", "no-such-section").returncode == 2


@pytest.mark.skipif(not (pathlib.Path.home() / ".local/share/mise").exists(),
                    reason="the daily tier calls pi and the harness CLIs")
def test_a_tier_run_writes_its_result_and_notifies_only_on_a_new_red(tmp_path):
    """One real daily run (about 6 s). A first red notifies; a second does not."""
    sent = tmp_path / "sent"
    notify = tmp_path / "notify.sh"
    notify.write_text(f'#!/bin/sh\necho "$@" >> {sent}\n')
    notify.chmod(0o755)
    env = {"HEALTHCHECK_NOTIFY": str(notify)}
    first = run_hc(tmp_path, "--tier", "daily", env=env)
    f = tmp_path / "healthcheck/daily.status"
    assert f.is_file(), first.stdout + first.stderr
    fields = dict(line.split("=", 1) for line in f.read_text().splitlines())
    assert fields["tier"] == "daily" and fields["stale_after"] == "172800"
    assert fields["result"] in ("OK", "WARN", "FAIL")
    if fields["result"] == "FAIL":
        assert sent.read_text().count("healthcheck daily") == 1
        run_hc(tmp_path, "--tier", "daily", env=env)
        assert sent.read_text().count("healthcheck daily") == 1   # standing red: no repeat
    else:
        assert not sent.exists()
