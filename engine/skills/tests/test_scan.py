"""The scan ledger: what gates, what is recorded, and what survives a rescan.

The rules under test are the ones that failed review when they were wrong:
`AE` coverage reports and asset-path findings must be recorded but never gate,
and a human disposition must survive a rescan of the same bytes. Both are
cheap to assert here and expensive to notice in production.
"""
import json
import os
import pathlib

import pytest

from skills import scan


def _skill(root: pathlib.Path, subject: str, name: str, *, mode="vendor", upstream=None):
    d = root / "system" / subject / name
    d.mkdir(parents=True)
    fm = [f"name: {name}", "description: does a thing", "origin: imported",
          "trust: trial", "invocation: model", f"mode: {mode}"]
    if upstream:
        fm.append(f"upstream_path: {upstream}")
        fm.append("upstream_pin: org/repo@abc123")
    (d / "SKILL.md").write_text("---\n" + "\n".join(fm) + "\n---\n\n# x\n")
    return d


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    """A skills tree and a ledger path the module will actually write to."""
    root = tmp_path / "skills"
    root.mkdir()
    ledger = root / "_scans.json"
    monkeypatch.setattr(scan, "SKILLS", root)
    monkeypatch.setattr(scan, "LEDGER", ledger)
    return root


def _stub(tmp_path, findings):
    """A scanner that emits one report, so the tests never need the real tool."""
    report = tmp_path / "stub-report.json"
    report.write_text(json.dumps({
        "risk_assessment": {"score": 7, "severity": "LOW",
                            "recommendation": "CAUTION", "max_issue_severity": "MEDIUM"},
        "issues": findings,
        "metadata": {},
    }))
    stub = tmp_path / "skillspector-stub"
    stub.write_text(f"#!/bin/sh\nwhile [ $# -gt 0 ]; do\n"
                    f"  if [ \"$1\" = '--output' ]; then cp {report} \"$2\"; fi\n"
                    f"  shift\ndone\n")
    stub.chmod(0o755)
    return str(stub)


def _finding(fid, severity, file="SKILL.md", line=1, fp="fp1"):
    return {"id": fid, "severity": severity, "category": "c", "pattern": f"{fid} pattern",
            "location": {"file": file, "start_line": line},
            "match_fingerprint": fp, "explanation": "e"}


def test_digest_tracks_content_and_path(tmp_path):
    a = tmp_path / "a"
    (a / "sub").mkdir(parents=True)
    (a / "sub" / "x.md").write_text("one")
    first = scan.digest(a)[0]
    (a / "sub" / "x.md").write_text("two")
    assert scan.digest(a)[0] != first
    (a / "sub" / "x.md").write_text("one")
    assert scan.digest(a)[0] == first
    (a / "sub" / "x.md").rename(a / "sub" / "y.md")
    assert scan.digest(a)[0] != first


def test_ae_and_asset_findings_are_recorded_but_never_gate():
    ae = scan.classify(_finding("AE1", "HIGH", "SKILL.md"), "body")
    assert ae["gates"] is False and "coverage" in ae["gate_excluded"]

    asset = scan.classify(_finding("P2", "CRITICAL", "assets/example.html"), "body")
    assert asset["gates"] is False and "asset" in asset["gate_excluded"]

    # The same finding in the record's own SKILL.md does gate: the path rule is
    # about data files, not about which target was scanned.
    real = scan.classify(_finding("P2", "CRITICAL", "SKILL.md"), "body")
    assert real["gates"] is True


def test_medium_never_gates():
    assert scan.classify(_finding("TR2", "MEDIUM"), "record")["gates"] is False


def test_high_gates_until_dispositioned(tree, tmp_path):
    _skill(tree, "practice", "wizard")
    binary = _stub(tmp_path, [_finding("P1", "HIGH", fp="abc")])
    entry = scan.scan_skill(binary, "system/practice/wizard", {"skills": {}}, llm=False)
    assert entry["gate"] == "blocked"
    assert entry["open_high"] == 1

    entry["record"]["findings"][0].update(disposition="false-positive", reason="negation-blind")
    scan.refresh_gate(entry)
    assert entry["gate"] == "pass"


def test_disposition_survives_rescan_by_fingerprint(tree, tmp_path):
    _skill(tree, "practice", "wizard")
    binary = _stub(tmp_path, [_finding("P1", "HIGH", fp="abc")])
    first = scan.scan_skill(binary, "system/practice/wizard", {"skills": {}}, llm=False)
    first["record"]["findings"][0].update(disposition="accepted", reason="by design",
                                          by="user", at="2026-10-24")
    scan.refresh_gate(first)
    old = {"skills": {"system/practice/wizard": first}}
    again = scan.scan_skill(binary, "system/practice/wizard", old, llm=False)
    assert again["record"]["findings"][0]["disposition"] == "accepted"
    assert again["gate"] == "pass"


def test_body_is_scanned_for_link_skills(tree, tmp_path):
    body = tmp_path / "upstream" / "skill"
    body.mkdir(parents=True)
    (body / "SKILL.md").write_text("body")
    _skill(tree, "practice", "shower", mode="link", upstream=str(body))
    binary = _stub(tmp_path, [_finding("P1", "HIGH", fp="b1")])
    entry = scan.scan_skill(binary, "system/practice/shower", {"skills": {}}, llm=False)
    assert entry["body"]["digest"].startswith("sha256:")
    assert entry["body"]["findings"][0]["target"] == "body"
    assert entry["gate"] == "blocked"


def test_missing_upstream_is_recorded_not_crashed(tree, tmp_path):
    _skill(tree, "practice", "gone", mode="link", upstream=str(tmp_path / "absent"))
    binary = _stub(tmp_path, [])
    entry = scan.scan_skill(binary, "system/practice/gone", {"skills": {}}, llm=False)
    assert entry["body"]["missing"] is True
    assert entry["gate"] == "pass"


def test_check_reports_drift(tree, tmp_path, capsys):
    d = _skill(tree, "practice", "wizard")
    binary = _stub(tmp_path, [])
    entry = scan.scan_skill(binary, "system/practice/wizard", {"skills": {}}, llm=False)
    ledger = {"schema": 3, "skills": {"system/practice/wizard": entry}}
    assert scan.cmd_check(ledger) == 0

    (d / "SKILL.md").write_text("---\nname: wizard\n---\n\nchanged\n")
    assert scan.cmd_check(ledger) == 3
    assert "DRIFT" in capsys.readouterr().out


def test_an_open_high_fails_only_a_trusted_claim(tree, tmp_path):
    _skill(tree, "practice", "wizard")
    binary = _stub(tmp_path, [_finding("P1", "HIGH", fp="abc")])
    entry = scan.scan_skill(binary, "system/practice/wizard", {"skills": {}}, llm=False)
    ledger = {"schema": 3, "skills": {"system/practice/wizard": entry}}
    assert scan.cmd_check(ledger) == 0          # trial: reported, not a failure
    entry["trust"] = "trusted"
    assert scan.cmd_check(ledger) == 1          # the claim is now unsupported


def test_accept_needs_a_unique_fingerprint(tree, tmp_path, capsys):
    _skill(tree, "practice", "wizard")
    binary = _stub(tmp_path, [_finding("P1", "HIGH", fp="abc123"),
                             _finding("P2", "HIGH", fp="abc456")])
    entry = scan.scan_skill(binary, "system/practice/wizard", {"skills": {}}, llm=False)
    scan.save_ledger({"schema": 3, "skills": {"system/practice/wizard": entry}})

    class Args:
        skill = "system/practice/wizard"
        fingerprint = "abc"
        disposition = "accepted"
        reason = "looked"
        by = "user"

    assert scan.cmd_accept(Args) == 2          # two matches: refuse to guess
    Args.fingerprint = "abc456"
    assert scan.cmd_accept(Args) == 0
    saved = json.loads(scan.LEDGER.read_text())
    assert saved["skills"]["system/practice/wizard"]["open_high"] == 1
