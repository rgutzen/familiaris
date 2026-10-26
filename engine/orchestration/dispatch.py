"""dispatch -- the enforcement point between planning and implementation.

Three modes, one module, because they read the same SPECS.md, contract and
catalogue.

`--check` (2b) refuses a SPECS.md whose open items lack a contract field or
name a model nobody can call. It is keyless and offline on purpose (no Jev, no
network): the check must run in a gate and in a fresh checkout.

`specs.validate` takes one set of ids. Candidates are passed to it too, so a
candidate is not reported as "unknown"; this module then refuses it with its
own message, since "known but not callable" is a different mistake from a typo.

`--gate` is the same check over every `dev/*/SPECS.md`, so a plate of work
cannot be planned here without becoming dispatchable (2c). Files that predate
the contract are declared under `legacy:` in specs.yaml: they warn, and the
list may only shrink -- a legacy file that now passes must be removed from it.

`dispatch <SPECS.md>` (3c) prints the waves, asks Jev four probes per open
item and prints a table that audits each item's `model:`. It refuses a file
`--check` would refuse, before any money is spent.

  ONE CALL PER ITEM. The four questions share one state, the item's own text
  (its checkbox line, prose and field lines, plus the declared model's name),
  and never the body of a file it names. One call per question would send the
  same state four times. The questions live in `config/orchestration/
  dispatch.yaml` under `probes:`; the code knows only the four keys and what
  each answer feeds, so a rewording is a YAML edit, and the printed hash of
  the `probes:` map says which wording an answer was given under.

  THE AUDIT, in this order, every number from `rules:` and the pre-selections in
  `config/orchestration/selection.yaml` (decision 27, 2026-10-14):
    user      `model: user` is the user's item: not probed, nothing suggested.
    unknown   a probe that did not come back is printed as `unknown` and the
              declaration stands. An unknown is never evidence for moving an
              item; the task class is what picks a tier, so a class nobody could
              name keeps the declaration.
    tier      the class's tiers run from its ordinary case upward; the item gets
              the FIRST tier whose `difficulty_up_to` admits its difficulty (with
              no reading, the first tier: the pre-selection is the baseline),
              raised one step per `band_raise:` answer that fired (an open design
              decision, a verify nobody can judge alone), capped at the last.
    suggest   the suggestion is the CHEAPEST member of that tier: API-equivalent
              list price (decision 24), ties by the measured mean over the class's
              capabilities, then the tier's own order. `agrees` when the
              declaration is the pick or sits in the same tier -- the row then
              names the cheaper member, information rather than a change -- and
              `differs` when it sits outside the tier.

  NO SCORE GATE. A model is never dropped for a missing benchmark, and a score
  never decides membership: it only orders the models inside a tier, because
  `capabilities.yaml` says "No benchmark, no score: unknown, never zero". The
  retired `capability_floor` did the opposite, and with this catalogue it left
  exactly ONE eligible model for `edit` and `test` (the baseline's own) and none
  for `read`, `docs` or `batch`, so the mechanism could suggest nothing at all.
  A tier is a judgement a person writes down; the arithmetic inside it is the
  only part a rule does.

  UNKNOWN IS NEVER EVIDENCE FOR MOVING AN ITEM. A probe answer that did not come
  back (a dry run, a failed call, a key absent from the response) is printed as
  `unknown`. If it is the task class, no tier can be picked and the declaration
  stands; if it is a `band_raise:` answer, it does not raise the tier; if it is
  the difficulty, the class's first tier applies -- the pre-selection, not a
  reading.

  ADVISORY ONLY. A suggestion that differs from the declaration is reported, never
  written: this module opens the SPECS.md read-only. So is a row that agrees while
  a cheaper member of the same tier exists. Neither an audit nor a threshold is
  applied by itself: a strategy becomes this system's default where the evidence
  shows it works (decision 1), which for a threshold means outcome labels behind
  it (3f, n >= 30 per task class).

  MONEY IS NOT SILENT. The estimate (call count, input tokens at ~4 chars a
  token, dollars) is cheap to compute from the payloads, so it prints before the
  first call; the actual `usage` and cost print after. `--dry-run` makes no
  call: the estimate, then the rules-only table with every probe `unknown`.

  THE INDEPENDENCE AUDIT (3d). Items in one wave run in parallel, so each pair
  of them gets one more `noul` call, in file order: "does B need anything A
  produces?" A yes at or above `noul_yes_at` is a SPECIFICATION ERROR, a
  `depends:` the planner missed (MAST's largest failure category), and is
  reported naming both items. It is never applied: no edge is added, no wave is
  reordered, and the exit code stays 0, because a non-zero exit on a finding
  would make the command unusable as the planning step's last check. The
  question lives under `independence:` in dispatch.yaml, outside `probes:`, so
  that adding it does not move the `probes:` hash 3c's calibration pins; it
  prints its own hash. `model: user` items are not probed as items but remain
  pair members, since the user's item can still produce what another needs.
  A wave of n items gives n(n-1)/2 calls. A `JevError` in this phase keeps the
  item table, marks the pair section "not asked" and ends with the error's exit
  code (the reverse of the item rule, where the answers would mix two states of
  one table; here a pair answer is independent of the table). Pair answers
  received before the failure are not printed as findings, and their spend is.
  If the item phase failed, the pair phase is not attempted: the same error
  would recur. Under `--dry-run` the pairs are listed `unknown`.

  THE EGRESS AND PRIVACY LIMIT (3e). The payload is the SPECS.md's own text:
  `item_text` (checkbox line, prose, indented field lines) and the declared
  model's name. No path an item's `touches:` names is opened, so a file body
  cannot reach TypeSafe; a test pins it. The only recipient added is Jev, and
  the same text already went to the session's frontier provider.
  A file may declare two keys at column 0, outside every item's block. They
  are not item fields: `specs.parse` never reads them and the contract in
  specs.yaml does not list them, so `--check` is unchanged. At most one of
  each, anywhere in the file; a second, or an `egress:` other than `cloud`
  (the default) or `none`, exits 2 naming the line, before any call.
    egress: none  no call at all, item or pair. Every answer is `unknown`, so
                  every declaration stands, and the eligible set is the
                  catalogue entries with `jurisdiction: local`.
    privacy: C    limits SUGGESTIONS to models whose computed class is exactly
                  C (`profiles.privacy_class`, the active profile's training
                  value for the vendor, as `profiles.resolve` computes it). No
                  order of classes is defined anywhere: `local`,
                  `EU-no-training`, `CN-undisclosed`, `US-unknown` are distinct
                  and none is "narrower" than another, so this module does not
                  invent one. The spec is never rewritten. A probed item whose
                  declared model is not class C is reported as a finding line,
                  and the declaration stands.

  EXIT CODES. 0 the table printed with probes, or under `--dry-run`. 1 the
  SPECS.md is not dispatchable (a `--check` finding, a dependency cycle). 2 a
  usage error, an unreadable file or config, a bad `egress:`/`privacy:` declaration, or a fatal `JevError` (`no-key`,
  `bad-mode`, `key-rejected`, `invalid-request`: waiting will not fix it). 3 a
  transient `JevError` (`rate-limited`, `overloaded`, `transport`: the next run
  is the retry). These are the `jev` commands' 2 fatal / 3 transient. On any
  `JevError` the run stops calling, prints `dispatch: no probes: <kind>:
  <message>`, and prints the rules-only table: answers received before the
  failure are discarded rather than mixed into a table of a different kind,
  and their spend is still printed.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import itertools
import json
import pathlib
import re
import sys

from harness import jev
from lib import _miniyaml
from lib import roots
from orchestration import jevlog, models, profiles, selection as selection_mod, specs, waves

CATALOGUE = roots.SUBAGENTS / "models.yaml"
CONFIG = roots.SUBAGENTS / "dispatch.yaml"

# Each probe key, the question type its answer is read as. The wording is
# dispatch.yaml's; the role of each answer is this table's.
PROBES = {"difficulty": "score", "task_class": "choice",
          "open_decision": "noul", "verify_alone": "noul"}
# The answers that raise an item one tier, and the text the row prints for each.
BAND_TEXT = {("open_decision", "yes"): "raised: open design decision",
             ("verify_alone", "no"): "raised: verify cannot judge alone"}
CHARS_PER_TOKEN = 4


def catalogue_ids(path: pathlib.Path = CATALOGUE) -> tuple[set, set]:
    """(callable ids, candidate ids) from models.yaml."""
    data = models.load(path)
    ids = lambda key: {m["id"] for m in data.get(key) or []}
    return ids("models"), ids("candidates")


def check(text: str, contract: dict, callable_ids: set, candidate_ids: set):
    """(open item count, findings, in line order)."""
    items = specs.parse(text, set(contract["fields"]))
    findings = specs.validate(items, contract, callable_ids | candidate_ids)
    for it in items:
        model = it.fields.get("model")
        if not it.done and model in candidate_ids and model not in callable_ids:
            findings.append(specs.Finding(
                it.id, "model", f"{model!r} is a candidate, not callable", it.line))
    findings.sort(key=lambda f: f.line)
    return sum(not it.done for it in items), findings


def gate(root: pathlib.Path, contract: dict, callable_ids: set, candidate_ids: set,
         out=print) -> int:
    """Run `check` over every dev/*/SPECS.md under `root`; 1 on any failure.

    Legacy paths are relative to `root`, the same way `dev/*/SPECS.md` is. A
    legacy entry whose file is gone fails, otherwise the list would keep names
    nobody can see and never shrink.
    """
    legacy = contract.get("legacy") or {}
    dev = root / roots.DEV.relative_to(roots.REPO)
    files = sorted(dev.glob("*/SPECS.md"))
    rels = {f: f.relative_to(root).as_posix() for f in files}
    failing = n_legacy = 0
    for f in files:
        rel = rels[f]
        _, findings = check(f.read_text(encoding="utf-8"), contract, callable_ids, candidate_ids)
        if rel in legacy:
            n_legacy += 1
            if findings:
                out(f"legacy: {rel}: {len(findings)} finding(s) -- {legacy[rel]}")
            else:
                failing += 1
                out(f"{rel} is dispatchable now; remove it from legacy: in specs.yaml")
        elif findings:
            failing += 1
            for fd in findings:
                out(f"{rel}: {fd}")
    for rel in sorted(set(legacy) - set(rels.values())):
        failing += 1
        out(f"legacy: {rel} does not exist; remove it from legacy: in specs.yaml")
    out(f"dispatch --gate: {len(files)} file(s), {failing} failing, {n_legacy} legacy")
    return 1 if failing else 0




# --- dispatch <SPECS.md> (3c) ----------------------------------------------

class ConfigError(ValueError):
    """dispatch.yaml does not say what the code needs; refused, never defaulted."""


def load_config(caps: dict, path: pathlib.Path = CONFIG) -> dict:
    """dispatch.yaml, checked: the four probes with their types, the class
    options equal to capabilities.yaml's task classes, and every rule a number."""
    data = _miniyaml.load(path.read_text(encoding="utf-8"))
    probes = data.get("probes") or {}
    if set(probes) != set(PROBES):
        raise ConfigError(f"{path.name}: probes: must be exactly {', '.join(PROBES)}")
    for key, kind in PROBES.items():
        if probes[key].get("type") != kind:
            raise ConfigError(f"{path.name}: probes.{key}: type must be {kind}")
    classes = set(caps.get("task_classes") or {})
    options = set(probes["task_class"].get("criteria") or {})
    if options != classes:
        raise ConfigError(f"{path.name}: probes.task_class options {sorted(options)} "
                          f"are not capabilities.yaml's task classes {sorted(classes)}")
    if len(probes["difficulty"].get("criteria") or []) < 2:
        raise ConfigError(f"{path.name}: probes.difficulty needs two or more levels")
    raw = data.get("rules") or {}
    try:
        rules = {k: float(raw[k]) for k in ("noul_yes_at",)}
        rules["reference_usage"] = {
            str(name): {k: int(v) for k, v in (shape or {}).items()}
            for name, shape in (raw.get("reference_usage") or {}).items()}
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise ConfigError(f"{path.name}: rules: {e}") from None
    try:
        rules["route_floor"] = float(raw.get("route_floor") or 0.5)
        rules["explore_budget"] = float(raw.get("explore_budget") or 0)
        rules["route_live"] = str(raw.get("route_live") or "no")
        rules["cascade"] = dict(part.strip().split("=", 1) for part in
                                str(raw.get("cascade") or "").split(",") if "=" in part)
    except (TypeError, ValueError) as e:
        raise ConfigError(f"{path.name}: rules: {e}") from None
    from orchestration import price as _price                        # noqa: PLC0415
    try:
        rules["quota_steps"] = _price.quota_steps(raw.get("quota_weight") or "else: 1")
    except (ValueError, _price.PriceError) as e:
        raise ConfigError(f"{path.name}: rules.quota_weight: {e}") from None
    usage = rules["reference_usage"]
    if "default" not in usage:
        raise ConfigError(f"{path.name}: rules.reference_usage: needs a `default` shape")
    for name, shape in usage.items():
        if name != "default" and name not in classes:
            raise ConfigError(f"{path.name}: rules.reference_usage.{name}: not a task class")
        if set(shape) - {"input", "cache_write", "cache_read", "output", "prompt"}:
            raise ConfigError(f"{path.name}: rules.reference_usage.{name}: "
                              f"pools are input, cache_write, cache_read, output, prompt")
    raise_ = raw.get("band_raise") or {}
    for key, value in raise_.items():
        if PROBES.get(key) != "noul" or value not in ("yes", "no"):
            raise ConfigError(f"{path.name}: rules.band_raise.{key}: "
                              f"{value!r} is not a noul probe's yes|no")
    rules["band_raise"] = dict(raise_)
    rules["suggest_kinds"] = list(raw.get("suggest_kinds") or [])
    indep = data.get("independence")
    if not isinstance(indep, dict) or indep.get("type") != "noul":
        raise ConfigError(f"{path.name}: independence: must be one question of type noul")
    if not str(indep.get("instructions") or "").strip():
        raise ConfigError(f"{path.name}: independence.instructions: missing")
    if not isinstance(indep.get("criteria"), dict):
        raise ConfigError(f"{path.name}: independence.criteria: missing")
    return {"probes": probes, "rules": rules, "independence": indep}


def probes_hash(probes: dict) -> str:
    """The hash that pins the wording, over the question objects only."""
    return hashlib.sha256(json.dumps(probes, sort_keys=True, ensure_ascii=False)
                          .encode()).hexdigest()[:16]


def item_text(lines: list[str], item: specs.Item) -> str:
    """The item as written: its checkbox line and the indented lines under it,
    by the same span rule `specs.parse` uses."""
    out = [lines[item.line - 1]]
    for line in lines[item.line:]:
        if line.strip() and not line.startswith(" "):
            break
        out.append(line)
    return "\n".join(out).rstrip()


def _entry(cat: dict, model_id: str) -> dict | None:
    return next((e for _, e in models.entries(cat) if e.get("id") == model_id), None)


def state(item: specs.Item, text: str, cat: dict) -> str:
    model = item.fields.get("model", "")
    e = _entry(cat, model)
    named = f"{model} ({e['name']})" if e and e.get("name") else model
    return f"declared model: {named}\n\n{text}"


# --- egress and privacy (3e) ------------------------------------------------

DECLARATION = re.compile(r"^(privacy|egress):(.*)$")
EGRESS_VALUES = ("cloud", "none")


class DeclarationError(ValueError):
    """A second `privacy:`/`egress:` line or a bad `egress:` value."""


def declarations(text: str) -> dict:
    """The `privacy:` and `egress:` lines at column 0, as {key: (value, line)}.

    Indented lines are item fields or prose and never match. A repeat or a bad
    value raises, naming the line, so the run stops before any call.
    """
    found: dict[str, tuple[str, int]] = {}
    for n, line in enumerate(text.splitlines(), 1):
        m = DECLARATION.match(line)
        if not m:
            continue
        key, value = m[1], m[2].strip()
        if key in found:
            raise DeclarationError(f"line {n}: a second `{key}:` (the first is on line "
                                   f"{found[key][1]}); a file declares at most one")
        if key == "egress" and value not in EGRESS_VALUES:
            raise DeclarationError(f"line {n}: egress: {value!r} is not one of "
                                   f"{', '.join(EGRESS_VALUES)}")
        if key == "privacy" and not value:
            raise DeclarationError(f"line {n}: privacy: names no class")
        found[key] = (value, n)
    return found


def model_class(entry: dict, cfg: dict, profile: str) -> str:
    """The entry's privacy class under the active profile, by the function
    `profiles.resolve` uses. A vendor the profile does not declare has no
    training value, which reads as `unknown`."""
    vendor = ((cfg["profiles"][profile].get("vendors") or {}).get(entry.get("vendor")) or {})
    training = (vendor.get("training") or {}).get("value")
    return profiles.privacy_class(entry["jurisdiction"], training, cfg)


def allowed_ids(cat: dict, egress: str, privacy: str | None) -> set | None:
    """Ids a suggestion may name, or None when nothing limits it."""
    if egress == "cloud" and privacy is None:
        return None
    cfg = profiles.load()
    profile = profiles.active(cfg=cfg)
    ids = set()
    for e in cat.get("models") or []:
        if egress == "none" and e.get("jurisdiction") != "local":
            continue
        if privacy is not None and model_class(e, cfg, profile) != privacy:
            continue
        ids.add(e["id"])
    return ids


def privacy_findings(asked: list, cat: dict, privacy: str) -> list[str]:
    cfg = profiles.load()
    profile = profiles.active(cfg=cfg)
    out = []
    for it in asked:
        model = it.fields.get("model", "")
        e = _entry(cat, model)
        got = model_class(e, cfg, profile) if e else "unknown"
        if got != privacy:
            out.append(f"{it.id}: declared model {model} is {got}; "
                       f"the spec declares privacy: {privacy}")
    return out


@dataclasses.dataclass
class Answers:
    """One item's probe answers; None is `unknown`, never a default."""
    difficulty: float | None = None
    task_class: str | None = None
    class_p: float | None = None
    open_decision: float | None = None
    verify_alone: float | None = None


def read_answers(got: dict, probes: dict) -> Answers:
    """The response's `answers` map as numbers. A key that is absent or of the
    wrong type stays None."""
    a = Answers()
    d = got.get("difficulty")
    if isinstance(d, dict) and d.get("type") == "score" and d.get("score") is not None:
        a.difficulty = float(d["score"]) / (len(probes["difficulty"]["criteria"]) - 1)
    c = got.get("task_class")
    if isinstance(c, dict) and c.get("type") == "choice":
        f = jev.answer_fields(c)
        if f.get("choice") in (probes["task_class"].get("criteria") or {}):
            a.task_class = f["choice"]
            a.class_p = (f.get("probabilities") or {}).get(a.task_class, f.get("confidence"))
    for key in ("open_decision", "verify_alone"):
        n = got.get(key)
        if isinstance(n, dict) and n.get("type") == "noul":
            setattr(a, key, jev.answer_fields(n).get("probability"))
    return a


def _yes(p: float | None, at: float) -> str | None:
    return None if p is None else ("yes" if p >= at else "no")


def admissible(cat: dict, caps: dict, selection: dict, task_class: str, rules: dict, *,
               difficulty: float | None = None, raises: int = 0,
               allowed: set | None = None) -> tuple[list, dict, int, str]:
    """(the applicable tier's ids, that tier, its index, why). The tier is the
    judgement, from selection.yaml; the order inside it is the rule: cheapest
    first by API-equivalent list price, ties by the measured mean over the
    class's capabilities, then the tier's own order. Nothing is dropped for a
    missing benchmark; `allowed` (a declared privacy class) drops a model and the
    returned note names it."""
    tier, idx, why = selection_mod.pick(selection, task_class, difficulty, raises)
    ids, note = selection_mod.cheapest(cat, caps, tier, rules, allowed)
    return ids, tier, idx, why + note


@dataclasses.dataclass
class Row:
    item: specs.Item
    answers: Answers | None          # None: not probed (the user's item)
    verdict: str                     # user | stands | agrees | differs
    reason: str
    suggested: str | None = None


def audit(item: specs.Item, a: Answers, cat: dict, caps: dict, cfg: dict,
          user_model: str, allowed: set | None = None, selection: dict | None = None) -> Row:
    rules = cfg["rules"]
    selection = selection if selection is not None else selection_mod.with_needs(
        selection_mod.load(), caps)
    declared = item.fields.get("model", "")
    if declared == user_model:
        return Row(item, None, "user", "the user's to do; not probed, nothing suggested")
    if a == Answers():
        return Row(item, a, "stands", "probes unknown")
    if a.task_class is None:
        return Row(item, a, "stands", "task class unknown, so no tier to read")
    raises, fired = 0, []
    for key, value in rules["band_raise"].items():
        if _yes(getattr(a, key), rules["noul_yes_at"]) == value:
            raises += 1
            fired.append(BAND_TEXT.get((key, value), f"{key} {value}"))
    n_tiers = len(selection_mod.tiers(selection, a.task_class))
    ids, tier, idx, why = admissible(cat, caps, selection, a.task_class, rules,
                                     difficulty=a.difficulty, raises=raises, allowed=allowed)
    if fired:
        why += "; " + "; ".join(fired)
    where = f"tier {idx + 1} of {n_tiers}"
    members = ", ".join(selection_mod.models_of(tier))
    if not ids:
        return Row(item, a, "stands",
                   f"nothing available in {where} ({members}): {selection_mod.reason(tier)} [{why}]")
    best = ids[0]
    if not selection_mod.live(rules):                    # 14g's shadow week
        sh = selection_mod.shadow(cat, caps, tier, rules, allowed)
        if sh and sh.get("pick") != best:
            why += f"; the route would pick {sh['pick']}"
    if best == declared:
        return Row(item, a, "agrees", f"{best}, the cheapest of {where} [{why}]")
    if declared in ids:
        return Row(item, a, "agrees",
                   f"{declared} is in {where}, and {best} is cheaper [{why}]")
    return Row(item, a, "differs",
               f"suggest {best}: the declaration is outside {where} ({members}) [{why}]",
               suggested=best)


def _fmt_p(p: float | None, at: float) -> str:
    return "unknown" if p is None else f"{_yes(p, at)} {p:.2f}"


def table(rows: list[Row], rules: dict) -> list[str]:
    head = ("item", "declared", "difficulty", "class", "open decision", "verify alone", "audit")
    body = []
    for r in rows:
        a = r.answers
        if a is None:
            cells = ["-"] * 4
        else:
            cells = ["unknown" if a.difficulty is None else f"{a.difficulty:.2f}",
                     "unknown" if a.task_class is None else
                     f"{a.task_class} {a.class_p:.2f}" if a.class_p is not None else a.task_class,
                     _fmt_p(a.open_decision, rules["noul_yes_at"]),
                     _fmt_p(a.verify_alone, rules["noul_yes_at"])]
        body.append((r.item.id, r.item.fields.get("model", ""), *cells, f"{r.verdict}: {r.reason}"))
    widths = [max(len(row[i]) for row in [head, *body]) for i in range(len(head) - 1)]
    fmt = lambda row: "  ".join(c.ljust(w) for c, w in zip(row, widths)) + "  " + row[-1]
    return [fmt(head), *map(fmt, body)]


def _estimate(payloads: list) -> int:
    return sum(len(json.dumps(p, ensure_ascii=False)) for p in payloads) // CHARS_PER_TOKEN


PAIR_KEY = "independent"


def pair_state(a_text: str, b_text: str) -> str:
    """The two items as written, A then B in file order."""
    return f"item A:\n{a_text}\n\nitem B:\n{b_text}"


def pair_section(pairs: list, probs: dict, rules: dict, not_asked: str | None,
                 dry_run: bool = False) -> list[str]:
    """The `same-wave pairs:` lines. `probs` maps (A id, B id) to a probability,
    or empty under --dry-run; `not_asked` is the reason a live run carries no
    answers."""
    if not_asked is not None:
        return [f"same-wave pairs: {len(pairs)} pair(s), not asked ({not_asked})"]
    at = rules["noul_yes_at"]
    hits = [k for k, p in probs.items() if p is not None and p >= at]
    head = (f"{len(pairs)} pair(s), {len(hits)} conflict(s)" if not dry_run
            else f"{len(pairs)} pair(s), none asked (--dry-run)")
    lines = [f"same-wave pairs: {head}"]
    for a, b in pairs:
        p = probs.get((a.id, b.id))
        if p is None:
            lines.append(f"  {a.id} x {b.id}  unknown")
        elif p >= at:
            lines.append(f"  {a.id} x {b.id}  YES {p:.2f}  spec error: {b.id} depends on "
                         f"something {a.id} produces and does not say so")
        else:
            lines.append(f"  {a.id} x {b.id}  no {p:.2f}")
    return lines


def run(path: pathlib.Path, *, dry_run: bool = False, out=print, err=None) -> int:
    err = err or (lambda s: print(s, file=sys.stderr))
    try:
        text = path.read_text(encoding="utf-8")
        caps = models.load_capabilities()
        cfg = load_config(caps)
    except (OSError, UnicodeDecodeError, _miniyaml.YamlError, ConfigError) as e:
        err(f"dispatch: {e}")
        return 2
    from orchestration import price as _price                        # noqa: PLC0415
    cfg["rules"] = _price.with_quota(cfg["rules"], probe=not dry_run)   # 14d: a pick made now
    try:
        decl = declarations(text)
    except DeclarationError as e:
        err(f"dispatch: {path}: {e}")
        return 2
    egress = decl["egress"][0] if "egress" in decl else "cloud"
    privacy = decl["privacy"][0] if "privacy" in decl else None
    no_egress = egress == "none"
    contract = specs.load_contract()
    callable_ids, candidate_ids = catalogue_ids()
    _, findings = check(text, contract, callable_ids, candidate_ids)
    if findings:
        for f in findings:
            out(str(f))
        err(f"dispatch: {path} is not dispatchable ({len(findings)} finding(s)); "
            f"see `dispatch --check`")
        return 1
    items = specs.parse(text, set(contract["fields"]))
    try:
        plan = waves.build(items, contract["none"])
    except waves.DependencyError as e:
        err(f"dispatch: {e}")
        return 1
    cat = models.load()
    lines = text.splitlines()
    user_model = contract.get("user_model")
    open_ = [it for it in items if not it.done]

    out(f"dispatch: {path}: {len(open_)} open item(s) in {len(plan)} wave(s)")
    for n, wave in enumerate(plan, 1):
        out(f"  wave {n}: {', '.join(it.id for it in wave)}")

    if decl:
        out("declared: " + ", ".join(f"{k} {decl[k][0]}" for k in ("egress", "privacy") if k in decl))
    allowed = allowed_ids(cat, egress, privacy)

    probes = cfg["probes"]
    asked = [it for it in open_ if it.fields.get("model") != user_model]
    payloads = {it.id: {"state": state(it, item_text(lines, it), cat), "questions": probes}
                for it in asked}
    est = _estimate(list(payloads.values()))
    if no_egress:
        out(f"probes: egress: none, no call made; every answer is unknown "
            f"({len(asked)} item(s), {len(open_) - len(asked)} user item(s) not probed)")
    else:
        out(f"probes: {len(probes)} questions, wording hash {probes_hash(probes)}; "
            f"{len(asked)} call(s) to {jev.MODEL}, ~{est:,} input tokens (estimate, "
            f"~{CHARS_PER_TOKEN} chars/token), ~${jev.cost_usd({'input_tokens': est}):.6f}; "
            f"{len(open_) - len(asked)} user item(s) not probed")

    got: dict[str, Answers] = {}
    usage = {"input_tokens": 0, "output_tokens": 0}
    calls, resolved, failure = 0, set(), None
    if no_egress:
        pass
    elif dry_run:
        out("probes: --dry-run, no call made; every answer is unknown")
    else:
        for it in asked:
            try:
                resp = jev.ask(payloads[it.id]["state"], probes)
            except jev.JevError as e:
                failure = e
                break
            calls += 1
            u = resp.get("usage") or {}
            usage["input_tokens"] += int(u.get("input_tokens", 0))
            usage["output_tokens"] += int(u.get("output_tokens", 0))
            resolved.add(resp.get("model") or "?")
            jevlog.record("dispatch", f"{jevlog.specs_rel(path)}#{it.id}",
                          probes_hash(probes), resp)
            got[it.id] = read_answers(resp.get("answers") or {}, probes)
    if failure is not None:
        err(f"dispatch: no probes: {failure.kind}: {failure}")
        got = {}

    rows = [audit(it, got.get(it.id, Answers()), cat, caps, cfg, user_model, allowed)
            for it in open_]
    out("")
    for line in table(rows, cfg["rules"]):
        out(line)
    out("")
    if privacy is not None:
        found = privacy_findings([r.item for r in rows if r.answers is not None], cat, privacy)
        out(f"privacy: {len(found)} declared model(s) outside privacy: {privacy}; reported, "
            f"not applied")
        for line in found:
            out(line)
        out("")

    pairs = [pr for wave in plan for pr in itertools.combinations(wave, 2)]
    pair_failure, pair_calls, probs = None, 0, {}
    if pairs:
        indep = cfg["independence"]
        texts = {it.id: item_text(lines, it) for it in open_}
        pair_pl = {(a.id, b.id): pair_state(texts[a.id], texts[b.id]) for a, b in pairs}
        pair_est = _estimate([{"state": st, "questions": {PAIR_KEY: indep}}
                              for st in pair_pl.values()])
        not_asked = None
        if no_egress:
            not_asked = "egress: none"
        else:
            out(f"independence: wording hash {probes_hash(indep)}; {len(pairs)} call(s) to "
                f"{jev.MODEL}, ~{pair_est:,} input tokens (estimate), "
                f"~${jev.cost_usd({'input_tokens': pair_est}):.6f}")
        if no_egress or dry_run:
            pass
        elif failure is not None:
            not_asked = f"item probes failed: {failure.kind}"
        else:
            for key, st in pair_pl.items():
                try:
                    resp = jev.ask(st, {PAIR_KEY: indep})
                except jev.JevError as e:
                    pair_failure = e
                    break
                pair_calls += 1
                u = resp.get("usage") or {}
                usage["input_tokens"] += int(u.get("input_tokens", 0))
                usage["output_tokens"] += int(u.get("output_tokens", 0))
                resolved.add(resp.get("model") or "?")
                jevlog.record("pair", f"{jevlog.specs_rel(path)}#{key[0]}+{key[1]}",
                              probes_hash(indep), resp)
                n = (resp.get("answers") or {}).get(PAIR_KEY)
                if isinstance(n, dict) and n.get("type") == "noul":
                    probs[key] = jev.answer_fields(n).get("probability")
            if pair_failure is not None:
                err(f"dispatch: no pair audit: {pair_failure.kind}: {pair_failure}")
                not_asked = pair_failure.kind
        for line in pair_section(pairs, probs, cfg["rules"], not_asked, dry_run):
            out(line)
        out("")
    count = lambda v: sum(r.verdict == v for r in rows)
    mode = ("rules only, egress: none" if no_egress else
            "rules only, --dry-run" if dry_run else
            f"rules only, no probes ({failure.kind})" if failure is not None else "probed")
    out(f"advisory only ({mode}): {count('differs')} suggestion(s) differ from the "
        f"declared model, {count('agrees')} agree, {count('stands')} stand, {count('user')} "
        f"user. Nothing is applied: {path} is unchanged. A threshold here leaves advisory "
        f"only when 3f's outcome labels reach n >= 30 per task class.")
    if not dry_run and not no_egress:
        split = f" ({calls} item, {pair_calls} pair)" if pairs else ""
        out(f"jev: {calls + pair_calls} call(s){split}, {usage['input_tokens']:,} in, "
            f"{usage['output_tokens']:,} out -> ${jev.cost_usd(usage):.6f}"
            + (f" (resolved {', '.join(sorted(resolved))})" if resolved else ""))
    failure = failure or pair_failure
    if failure is not None:
        return 2 if failure.fatal else 3
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="familiar orchestration dispatch",
                                 description="Check a SPECS.md is dispatchable, or dispatch it.")
    ap.add_argument("--check", action="store_true",
                    help="validate every open item against the contract and catalogue")
    ap.add_argument("--gate", action="store_true",
                    help="check every dev/*/SPECS.md; legacy files warn, the rest must pass")
    ap.add_argument("--dry-run", action="store_true",
                    help="dispatch without calling Jev: the estimate and the rules-only table")
    ap.add_argument("--root", type=pathlib.Path, default=roots.REPO,
                    help="repo root --gate reads (default: this repo; tests use a tmp tree)")
    ap.add_argument("specs", type=pathlib.Path, nargs="?",
                    help="the SPECS.md to check (--check) or dispatch")
    args = ap.parse_args(argv)
    if args.gate and (args.check or args.specs):
        print("dispatch: --gate takes no file and excludes --check", file=sys.stderr)
        return 2
    if args.dry_run and (args.check or args.gate):
        print("dispatch: --dry-run applies to dispatching, not to --check or --gate",
              file=sys.stderr)
        return 2
    if args.gate:
        callable_ids, candidate_ids = catalogue_ids()
        return gate(args.root, specs.load_contract(), callable_ids, candidate_ids)
    if args.specs is None:
        print("dispatch: give a SPECS.md (with --check to validate only), or --gate",
              file=sys.stderr)
        return 2
    if not args.check:
        return run(args.specs, dry_run=args.dry_run)
    try:
        text = args.specs.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"dispatch --check: cannot read {args.specs}: {e}", file=sys.stderr)
        return 2
    callable_ids, candidate_ids = catalogue_ids()
    n_open, findings = check(text, specs.load_contract(), callable_ids, candidate_ids)
    for f in findings:
        print(f)
    print(f"dispatch --check: {args.specs}: {n_open} open item(s), {len(findings)} finding(s)")
    return 1 if findings else 0
