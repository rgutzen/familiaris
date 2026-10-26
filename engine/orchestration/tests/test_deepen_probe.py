"""The probe's two non-model behaviours: it reads the reply out of the runner's
output, and it fails a fixture whose contract breaks. Nothing here spawns a child."""
import pathlib

from orchestration import deepen_probe, bindings


def test_reply_of_cuts_at_the_binding_line_and_keeps_indented_bullets():
    out = ("field: x\n\n`kept:`\n  - \"a quote\" — why\n\n```\nprompt\n```\n"
           "binding: role:deepen -> deepseek/deepseek-flash; contract kept: ok\n"
           "  contract: something\n")
    reply = deepen_probe.reply_of(out)
    assert reply.startswith("field: x")
    assert "  - \"a quote\"" in reply, "a reply's indented bullets are not the runner's"
    assert "binding:" not in reply


def test_reply_of_handles_output_with_no_binding_line():
    assert deepen_probe.reply_of("a bare reply\n") == "a bare reply"


def test_the_fixtures_are_all_probes_of_the_contract_not_of_a_model():
    names = [f["name"] for f in deepen_probe.FIXTURES]
    assert names == ["vague", "followup", "already-deep"]
    for fx in deepen_probe.FIXTURES:
        assert fx["text"].strip() and fx["expect"], fx["name"]
        # The shape alone is asserted, so no fixture may depend on a file it cannot
        # read: a no-tools child answers "I cannot read files" and tests nothing.
        assert "http://" not in fx["text"] and "~/03_ZETTEL" not in fx["text"], fx["name"]


def test_a_broken_reply_fails_the_fixture(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(deepen_probe, "run_one",
                        lambda fx, free, cwd, t: ("no labels here", bindings.Verdict(
                            False, "0 block(s)", ["field: missing"])))
    rc = deepen_probe.main(["--check"])
    out = capsys.readouterr().out
    assert rc == 3
    assert out.count("FAIL") == len(deepen_probe.FIXTURES)
