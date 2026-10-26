"""scout -- item 13a: a nomination when the model chart moves, and nothing more.

WHY A SCOUT AND NOT A DECISION. The chart (`paraplouis/llm-pareto-frontier`,
`data/synthesized_data.js`: LM Arena Elo with style control, OpenRouter price,
`cheapest_provider`) ranks CHAT PREFERENCE. It is cheap, public and refreshed
daily, so it can say "this model may be worth measuring"; it cannot say "this
model reads better", because the failure this system's reader has is a wrong
`path:line`, which a preference vote does not see. So the chart nominates
(13a) and the reader calibration (12c, `eval --calibrate`) recommends (13b).
Neither stage adds a provider: that stays the user's decision, taken on a
proposal that carries both numbers.

TWO MARGINS, BOTH POLICY, BOTH IN `selection.yaml` (`nominate:`), each with its
reason written beside it: at least +20 Elo at no more than 1.5x the blended
price, or within 5 Elo at no more than half the price. The gap between them is
deliberate -- +6 to +19 Elo at half price is neither a better model nor a
cheaper one, and the chart's own confidence interval is about 10 Elo, so a rule
that read it as either would be reading noise.

THE COMPARISON IS THE CLASS'S FIRST TIER, because that is the model a class runs
on its ordinary case (no difficulty reading). Its rated members are the
incumbents: for `read`, `claude-haiku-5-5` and `mistral-small-2603` have no
chart entry, so `read` is judged against `deepseek-flash` alone. A candidate
that beats only an ESCALATED tier (read tier 2 is Sonnet at 1475 for $4.00
blended) is not nominated: replacing an escalated member is a different
decision, and this stage's output would otherwise be dominated by it. The chart
does rate `claude-sonnet-5.5-xhigh` and `Claude Opus 5.5 (High)`, so in practice
today `edit` (Sonnet, deepseek-flash), `test`/`docs` (Sonnet) and `unknown`
(Opus) are all judged too.

BOTH PRICES COME FROM THE CHART (`(3 x input + output) / 4`, per Mtok, the
blend the chart's own frontier is drawn against), so a comparison is like for
like even when the catalogue's list price disagrees with the host's cheapest.

THE HOST DECIDES THE JURISDICTION, NOT THE DEVELOPER: `cheapest_provider` is
where the tokens would actually go. The mapping host -> jurisdiction is policy
in the same block, and a host nobody has ruled on is REPORTED, never guessed:
a nomination a profile cannot legally use is worse than no nomination.

WHAT A MODEL WITHOUT AN `arena:` NAME GETS. A line in the report and no
comparison: the chart's `deepseek-v4.1-flash-max` is this catalogue's
`deepseek-flash`, but a rule that guessed that from the strings would also
guess `claude-haiku-4-5-20251001` is `claude-haiku-5-5`, and it is not.

THE SCOUT NOMINATES A CALIBRATION SLOT AND RECOMMENDS NOTHING (14h). 13b let the
calibration recommend a nomination by its own two-number rule (rate, then wall
clock), and reported an "inversion" when two members disagreed with the pick;
14g's router now decides from expected cost per verified result, so a second
judge here would be a second answer to one question. Every nomination is one of:
  slot      no calibration run exists for the candidate at this class's effort --
            the report prints the command that would produce one, after the steps
            that must come first (a key, the catalogue row)
  measured  the run exists; it is evidence the router (14g) weighs through the
            posterior and the token model, and the scout says no more
The chart's Elo and price stay inside the chart's own comparison: they choose
which model is worth a slot, and decide nothing about a pick.

DISMISSALS. `--dismiss CLASS MODEL [MEMBER]` records the margin as it stands
today in `<PAZRAS_DATA_DIR>/scout-dismissals.jsonl`; the nomination is then not
raised again until its margin GROWS -- more Elo than when it was dismissed by
the policy's `reopen_elo`, or cheaper by `reopen_price` of the ratio -- because
a "no" to a nomination is a no to that comparison, not to the model forever.
`--check` exits 1 only for a nomination that is new since the last run (state in
`scout-last.json`), so a nightly report can surface it and a quiet night stays
quiet.

EXIT CODES. 0 read. 1 `--check` with a new nomination, or an `arena:` name the
chart no longer holds (14b). 2 a usage error, an
unreadable chart, a missing policy block, or a `--dismiss` that names nothing.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import pathlib
import sys
import urllib.error
import urllib.request

from lib import roots
from orchestration import models, profiles, selection

URL = ("https://raw.githubusercontent.com/paraplouis/llm-pareto-frontier/"
       "main/data/synthesized_data.js")
CACHE = "pareto-frontier.js"          # the last chart read, under PAZRAS_DATA_DIR
STATE = "scout-last.json"             # the last run's nomination keys, for --check
DISMISSALS = "scout-dismissals.jsonl"  # a "no" per (class, model, member)
DEFAULT_TIMEOUT = 60


class ScoutError(RuntimeError):
    """An unreadable chart, a missing policy block, or a dismissal that names
    nothing; the CLI maps it to exit 2."""


@dataclasses.dataclass(frozen=True)
class Rated:
    """One chart row: a model name, its Elo, its blended price and its host."""
    name: str
    elo: int
    blended: float
    host: str
    organization: str

    def line(self) -> dict:
        return {"name": self.name, "elo": self.elo, "blended": round(self.blended, 4),
                "host": self.host, "organization": self.organization}


@dataclasses.dataclass(frozen=True)
class Nom:
    """One nomination: a chart model that beats a class's incumbent by a margin."""
    task_class: str
    model: str                       # the chart's name for the candidate
    member: str                      # the catalogue id it beats
    member_name: str                 # the chart's name for that member
    elo: int
    member_elo: int
    price: float
    member_price: float
    host: str
    jurisdiction: str
    catalogue_id: str = ""           # the id this chart name already is, or ""

    @property
    def elo_delta(self) -> int:
        return self.elo - self.member_elo

    @property
    def price_ratio(self) -> float:
        return self.price / self.member_price if self.member_price else 0.0

    @property
    def key(self) -> str:
        return f"{self.task_class}|{self.model}|{self.member}"

    def line(self) -> dict:
        return {"class": self.task_class, "model": self.model, "member": self.member,
                "member_name": self.member_name, "elo": self.elo,
                "member_elo": self.member_elo, "elo_delta": self.elo_delta,
                "price": round(self.price, 4), "member_price": round(self.member_price, 4),
                "price_ratio": round(self.price_ratio, 4), "host": self.host,
                "jurisdiction": self.jurisdiction}


# --- the chart ---------------------------------------------------------------

def parse(text: str) -> tuple[list, str]:
    """(the chart's rows, its `dataLastUpdated`).

    The file is a JavaScript module holding one JSON array and a few scalar
    exports; the array is JSON, so it is parsed rather than evaluated, and a row
    that is not a mapping with a name, an Elo and both prices is dropped (a
    chart entry without a price cannot be compared like for like).
    """
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        raise ScoutError("the chart holds no array")
    try:
        raw = json.loads(text[start:end + 1])
    except ValueError as e:
        raise ScoutError(f"the chart's array is not JSON: {e}") from None
    updated = ""
    for key in ("dataLastUpdated", "lastUpdated", "updated"):
        at = text.find(f"{key} = \"")
        if at >= 0:
            updated = text[at + len(key) + 4:text.find('"', at + len(key) + 5)]
            break
    rows = []
    for r in raw:
        if not isinstance(r, dict) or not r.get("model"):
            continue
        try:
            rows.append(Rated(name=str(r["model"]).strip(), elo=int(r["elo"]),
                              blended=(3 * float(r["input_price"])
                                       + float(r["output_price"])) / 4,
                              host=str(r.get("cheapest_provider") or "").strip(),
                              organization=str(r.get("organization") or "").strip()))
        except (KeyError, TypeError, ValueError):
            continue
    if not rows:
        raise ScoutError("the chart holds no row with a name, an Elo and both prices")
    return rows, updated


def fetch(url: str = URL, cache: pathlib.Path | None = None,
          timeout: float = DEFAULT_TIMEOUT) -> tuple[str, str]:
    """(the chart's text, where it came from). The cache is the fallback.

    A nightly run that cannot reach GitHub must not report "no nomination": it
    reports the chart it read and its date, and the caller prints that date, so a
    stale chart is visible rather than silent.
    """
    cache = cache or profiles.data_dir() / CACHE
    request = urllib.request.Request(url, headers={"User-Agent": "familiar-scout/1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
        if len(text) > 1000:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(text, encoding="utf-8")
            return text, url
        raise ScoutError("the chart's response was too short to be the chart")
    except (OSError, ValueError, urllib.error.URLError) as e:
        if cache.is_file():
            return cache.read_text(encoding="utf-8"), f"{cache} (fetch failed: {e})"
        raise ScoutError(f"the chart could not be read: {e}") from None


def load(data: pathlib.Path | None = None, url: str = URL,
         cache: pathlib.Path | None = None, timeout: float = DEFAULT_TIMEOUT) -> tuple:
    """(rows, the chart's date, where it came from). `--data` reads a pinned file."""
    if data is not None:
        return (*parse(pathlib.Path(data).read_text(encoding="utf-8")),
                str(data))
    text, source = fetch(url, cache, timeout)
    rows, updated = parse(text)
    return rows, updated, source


# --- the policy ---------------------------------------------------------------

def policy(sel: dict) -> dict:
    """`selection.yaml`'s `nominate:` block, with its margins as numbers.

    No defaults: a margin this module invented would be a decision nobody wrote
    down, and the block carries the reason for each one beside it.
    """
    block = sel.get("nominate") or {}
    if not block:
        raise ScoutError(f"{selection.SELECTION}: no `nominate:` block")
    out = {"hosts": {}}
    for key, want in (("elo_margin", int), ("price_cap", float), ("close_elo", int),
                      ("half_price", float), ("reopen_elo", int), ("reopen_price", float)):
        if block.get(key) is None:
            raise ScoutError(f"{selection.SELECTION}: nominate.{key} is missing")
        try:
            out[key] = want(float(block[key]))
        except (TypeError, ValueError):
            raise ScoutError(f"{selection.SELECTION}: nominate.{key} is not a number") from None
    for host, jurisdiction in (block.get("hosts") or {}).items():
        out["hosts"][str(host).strip().casefold()] = str(jurisdiction).strip()
    if not out["hosts"]:
        raise ScoutError(f"{selection.SELECTION}: nominate.hosts is empty")
    return out


def jurisdiction(host: str, pol: dict) -> str | None:
    """The jurisdiction a host's tokens go to, or None when nobody has ruled.

    The chart writes a mirror or a reseller with a leading `~` (`~Anthropic`);
    that is the same jurisdiction as the vendor's own route, so the marker is
    stripped and nothing else is.
    """
    return pol["hosts"].get(host.lstrip("~").strip().casefold())


def dominates(candidate: Rated, member: Rated, pol: dict) -> bool:
    """The two-clause margin, as the policy block states it."""
    delta = candidate.elo - member.elo
    if delta >= pol["elo_margin"] and candidate.blended <= pol["price_cap"] * member.blended:
        return True
    return (abs(delta) <= pol["close_elo"]
            and candidate.blended <= pol["half_price"] * member.blended)


# --- the incumbents ----------------------------------------------------------

DEFAULT_LEVEL = "default"     # the `arena:` key of a model without effort levels


def arena_names(cat: dict) -> tuple[dict, list]:
    """({catalogue id: {level: chart name or None}}, the ids with no `arena:`).

    `arena:` is the only bridge between this catalogue and the chart, one key per
    effort level (14b); `~` is a level the chart does not rate. A model without
    the key is reported; nothing here matches on a name's shape.
    """
    by_id, missing = {}, []
    for section in ("models", "candidates"):
        for e in cat.get(section) or []:
            mid = str(e.get("id") or "").strip()
            block = e.get("arena")
            if mid and isinstance(block, dict) and block:
                by_id[mid] = {str(k): _rated(v) for k, v in block.items()}
            elif mid:
                missing.append(mid)
    return by_id, missing


def _rated(value) -> str | None:
    """A level's chart name, or None for `~`. The catalogue's loader keeps every
    value a string, so `~` arrives as the string, not as YAML's null."""
    text = "" if value is None else str(value).strip()
    return None if text in ("", "~", "null") else text


def chart_name(names: dict, mid: str, level: str) -> tuple[str | None, str]:
    """(the chart name for this model AT THIS LEVEL, or None, and why not).

    A model without levels has only `default`, which answers for any tier
    effort (the vendor has no knob to turn). A model with levels answers only
    for the level asked: judging it at another one would compare a different
    token bill.
    """
    block = names.get(mid)
    if not block:
        return None, "no `arena:` name"
    if set(block) == {DEFAULT_LEVEL}:
        level = DEFAULT_LEVEL
    if level not in block:
        return None, f"no `arena:` key for `{level}`"
    if block[level] is None:
        rated_at = [k for k, v in block.items() if v]
        return None, (f"unrated at `{level}`"
                      + (f" (the chart rates {', '.join(rated_at)})" if rated_at else ""))
    return block[level], ""


def chart_ids(names: dict) -> dict:
    """{chart name: catalogue id} over every mapped level: what tells a
    candidate row that it is already one of ours."""
    return {chart: mid for mid, block in names.items() for chart in block.values() if chart}


def stale(names: dict, rated: dict) -> list:
    """The mapped names the chart no longer holds, as `id@level -> name`.

    The chart renames rows (2026-10-20 turned every slug into a display name),
    and a stale mapping would otherwise read as "unrated" and quietly drop the
    member from every comparison.
    """
    return [f"{mid}@{level} -> {chart!r}" for mid, block in sorted(names.items())
            for level, chart in block.items() if chart and chart not in rated]


def incumbents(sel: dict, names: dict, rated: dict) -> tuple[dict, list]:
    """({class: [(catalogue id, Rated)]}, the tier members the chart does not rate).

    EVERY TIER, ruled by the user on 2026-10-21. Each class's nomination targets
    are all of its rated members, so an escalated tier can be beaten too -- the
    chart rates `claude-sonnet-5.5-xhigh` and `Claude Opus 5.5 (High)`, and a
    cheap reader that matches them at a tenth of the price is a real finding for
    the tier that runs on hard work, not noise.

    AT THE LEVEL THE TIER RUNS (14b): a member is looked up at `effort_of(tier,
    mid)`, so `deepseek-flash` at `low` is unrated while the chart rates only its
    `max`. A member appears once per (id, chart row), so two tiers that run it at
    two rated levels are two targets, and the same level twice is one.
    """
    members, unrated = {}, []
    for name in selection.classes(sel):
        found, seen = [], set()
        for tier in selection.tiers(sel, name):
            for mid in selection.models_of(tier):
                level = selection.effort_of(tier, mid) or DEFAULT_LEVEL
                chart, why = chart_name(names, mid, level)
                if (mid, chart or level) in seen:
                    continue
                seen.add((mid, chart or level))
                if chart and chart in rated:
                    found.append((mid, rated[chart]))
                else:
                    unrated.append(f"{mid} ({why or f'{chart!r} is not in the chart'})")
        members[name] = found
    return members, unrated


def nominations(rows: list, members: dict, pol: dict,
                allowed: set | None = None) -> tuple[list, list]:
    """(the nominations, the hosts nobody has ruled on).

    A candidate seen from two classes, or against two members of one class, is
    two nominations -- the comparison is what a person reads, and the same model
    beating Sonnet for `docs` and for `test` is two decisions.
    """
    out, unknown = [], {}
    for task_class, found in members.items():
        for mid, member in found:
            for r in rows:
                if r.name == member.name:
                    continue
                if not dominates(r, member, pol):
                    continue
                where = jurisdiction(r.host, pol)
                if where is None:
                    unknown.setdefault(r.host, set()).add(r.name)
                    continue
                if allowed is not None and where not in allowed:
                    continue
                out.append(Nom(task_class=task_class, model=r.name, member=mid,
                               member_name=member.name, elo=r.elo, member_elo=member.elo,
                               price=r.blended, member_price=member.blended,
                               host=r.host, jurisdiction=where))
    out.sort(key=lambda n: (list(members).index(n.task_class), n.price_ratio, -n.elo_delta))
    return out, sorted((h, sorted(m)) for h, m in unknown.items())


# --- dismissals and state ----------------------------------------------------

def dismissals_path() -> pathlib.Path:
    return profiles.data_dir() / DISMISSALS


def read_dismissals(path: pathlib.Path | None = None) -> dict:
    """{(class, model, member): the margin when it was dismissed}."""
    path = path or dismissals_path()
    out = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("model"):
            out[(row.get("class"), row.get("model"), row.get("member"))] = row
    return out


def grew(nom: Nom, was: dict, pol: dict) -> bool:
    """Whether a dismissed nomination's margin has grown enough to raise again."""
    return (nom.elo_delta >= int(was.get("elo_delta") or 0) + pol["reopen_elo"]
            or nom.price_ratio <= float(was.get("price_ratio") or 0) * (1 - pol["reopen_price"]))


def dismiss(nom: Nom, path: pathlib.Path | None = None) -> pathlib.Path:
    path = path or dismissals_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(nom.line(), ts=datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds")), sort_keys=True) + "\n")
    return path


def state_path() -> pathlib.Path:
    return profiles.data_dir() / STATE


def read_state(path: pathlib.Path | None = None) -> set:
    path = path or state_path()
    if not path.is_file():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).get("keys") or [])
    except (ValueError, AttributeError):
        return set()


def write_state(keys: list, path: pathlib.Path | None = None) -> None:
    path = path or state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"at": datetime.datetime.now(datetime.timezone.utc)
                                .isoformat(timespec="seconds"), "keys": keys}, indent=2),
                    encoding="utf-8")


# --- 13b: the calibration decides ---------------------------------------------

def variants(rows: list) -> dict:
    """{(model, effort): the attempt medians} from `eval --calibrate`'s rows.

    Only attempts that RAN count: a model that answered 429 or ran out of quota
    has no reading, and averaging a zero in would read as a bad reader.
    """
    import statistics
    by = {}
    for r in rows:
        if not r.get("ran", True):
            continue
        by.setdefault((str(r.get("model")), str(r.get("effort") or "")), []).append(r)
    out = {}
    for key, got in by.items():
        total = max(int(g.get("total") or 0) for g in got) or 1
        out[key] = {"attempts": len(got),
                    "rate": statistics.median([int(g.get("verified") or 0) / total
                                               for g in got]),
                    "seconds": statistics.median([float(g.get("seconds") or 0) for g in got]),
                    "usd": statistics.median([float(g.get("usd") or 0) for g in got])}
    return out


def status(nom: Nom, measured: dict, effort: str, model_id: str, pol: dict) -> dict:
    """What a nomination is now: a calibration SLOT to fill, or MEASURED (14h)."""
    if not model_id:
        return {"status": "slot", "command": "",
                "why": "no catalogue row yet, so no run can measure it"}
    got = measured.get((model_id, effort))
    if got is None:
        return {"status": "slot", "why": "no calibration run for this model at "
                f"`{effort or 'the default level'}`",
                "command": (f"familiar orchestration eval --calibrate --model {model_id} "
                            f"--effort {effort or 'low'} --attempts 3")}
    return {"status": "measured", "command": "",
            "why": (f"{got['attempts']} run(s), {got['rate']:.0%} verified; the router "
                    f"(14g) weighs it -- `familiar orchestration posterior --class "
                    f"{nom.task_class}`")}


# --- the report --------------------------------------------------------------

def adoption(nom: Nom, cat: dict, cfg: dict, known_as: dict) -> str:
    """What adopting this nomination would take, in the order it would be done.

    Three cases, and they are different amounts of work: a model this catalogue
    already holds needs a tier edit and nothing else; a model whose vendor the
    profile already bills needs a catalogue row; anything else needs a new account.
    """
    catalogued = known_as.get(nom.model) or (nom.model if nom.model in
                                             {str(e.get("id")) for s in ("models", "candidates")
                                              for e in cat.get(s) or []} else "")
    if catalogued:
        sel = selection.load()
        named = (nom.task_class in selection.classes(sel)
                 and any(catalogued == mid
                         for tier in selection.tiers(sel, nom.task_class)
                         for mid in selection.models_of(tier)))
        if named:
            return (f"already catalogued as {catalogued} and named in {nom.task_class}'s "
                    f"tiers: nothing to add, 14g's router ranks it")
        return (f"already catalogued as {catalogued}: a tier edit for {nom.task_class} in "
                f"selection.yaml, the user's to approve")
    vendor = nom.host.lstrip("~").strip().casefold().replace(" ", "")
    vendors = {k.casefold(): k for k in ((cfg.get("profiles") or {}).get(profiles.active())
                                        or {}).get("vendors") or {}}
    if vendor in vendors:
        return (f"a models.yaml row (the profile already carries a {vendors[vendor]} "
                f"credential) and profiles.yaml's privacy fields for the account")
    return (f"a key for {nom.host}, profiles.yaml's provider/key_env/privacy fields, "
            f"and a models.yaml row")


def report(noms: list, dismissed: list, unknown: list, unrated: list, members: dict,
           updated: str, source: str, cat: dict, cfg: dict, cal: dict = None,
           verdicts: list = None, out=print) -> None:
    out(f"scout -- the chart of {updated or '(no date in the file)'}, {source}")
    judged = "; ".join(f"{c}: {', '.join(m for m, _r in found) or '-'}"
                       for c, found in members.items())
    out(f"  judged    {judged}")
    if unrated:
        out(f"  unrated   {'; '.join(sorted(set(unrated)))} -- not judged")
    if unknown:
        out("  unknown   host(s) with no jurisdiction in selection.yaml, so never nominated: "
            + ", ".join(f"{h} ({len(m)})" for h, m in unknown))
    if not noms:
        out("  nominate  none -- no model beats an incumbent by a margin")
    else:
        classes = sorted({n.task_class for n in noms}, key=lambda c: list(members).index(c))
        out(f"  nominate  {len(noms)} line(s) in {len(classes)} class(es)")
        for n in noms:
            sign = "+" if n.elo_delta >= 0 else ""
            out(f"    {n.task_class:<8} {n.model} beats {n.member}: {sign}{n.elo_delta} Elo, "
                f"x{n.price_ratio:.2f} the price (${n.price:.3f} vs ${n.member_price:.3f}); "
                f"{n.host} ({n.jurisdiction})")
        known_as = members_names(members)
        out("  adoption")
        seen = set()
        for n in noms:
            if n.model in seen:
                continue
            seen.add(n.model)
            out(f"    {n.model:<24} {adoption(n, cat, cfg, known_as)}")
    if dismissed:
        out(f"  dismissed {len(dismissed)} nomination(s) still hold: "
            + ", ".join(f"{n.task_class} {n.model}" for n in dismissed))
    if cal is None:
        return
    if cal:
        for (model, effort), got in sorted(cal.items()):
            out(f"  calibrated {model} at {effort or 'the default level'}: "
                f"{got['attempts']} attempt(s), {got['rate']:.0%} verified, "
                f"{got['seconds']:.1f} s, ${got['usd']:.4f} per read")
    else:
        out("  calibrated none -- `familiar orchestration eval --calibrate --model <id>"
            " --attempts 3` writes the rows this stage reads")
    grouped = {}
    for v in verdicts or []:
        if v["status"] == "slot":
            key = (v["model"], v["why"], v["command"])
            grouped.setdefault(key, []).append(v["class"])
    for (model, why, command), classes in grouped.items():
        out(f"  slot      {model} ({', '.join(sorted(set(classes)))}): {why}")
        if command:
            out(f"            {command}")
    for v in verdicts or []:
        if v["status"] == "measured":
            out(f"  measured  {v['model']} ({v['class']}): {v['why']}")
    if not verdicts:
        out("  slot      none -- no nomination to calibrate")


def members_names(members: dict) -> dict:
    """{chart name: catalogue id} over the judged members."""
    return {r.name: mid for _c, found in members.items() for mid, r in found}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="familiar orchestration scout",
        description="Nominate a model the chart puts ahead of a class's incumbent by "
                    "a margin, for 12c to measure.")
    ap.add_argument("--data", type=pathlib.Path, metavar="FILE",
                    help=f"read a pinned chart file instead of {URL}")
    ap.add_argument("--url", default=URL, help=f"where the chart lives (default {URL})")
    ap.add_argument("--cache", type=pathlib.Path,
                    help=f"the last chart read, used when the fetch fails "
                         f"(default {CACHE} in the data directory)")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, metavar="SECONDS")
    ap.add_argument("--profile", help="the billing profile whose jurisdictions apply "
                                      "(default PI_PROFILE, else `private`)")
    ap.add_argument("--dismiss", nargs="+", metavar="ARG",
                    help="CLASS MODEL [MEMBER]: record this nomination as declined")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 when a nomination is new since the last run")
    ap.add_argument("--json", action="store_true", help="one JSON object instead of the report")
    args = ap.parse_args(argv)
    try:
        pol = policy(selection.load())
        cat = models.load()
        cfg = profiles.load()
    except (OSError, ScoutError, selection.SelectionError) as e:
        print(f"scout: {e}", file=sys.stderr)
        return 2
    acting = args.profile or profiles.active()
    allowed = set(((cfg.get("profiles") or {}).get(acting) or {}).get("jurisdictions") or [])
    if not allowed:
        print(f"scout: no profile {acting!r} in profiles.yaml", file=sys.stderr)
        return 2
    try:
        rows, updated, source = load(args.data, args.url, args.cache, args.timeout)
    except (OSError, ScoutError) as e:
        print(f"scout: {e}", file=sys.stderr)
        return 2
    rated = {r.name: r for r in rows}
    names, no_arena = arena_names(cat)
    members, unrated = incumbents(selection.load(), names, rated)
    noms, unknown = nominations(rows, members, pol, allowed)
    from orchestration import eval as eval_mod
    measured = variants(eval_mod.calibration_rows())
    known_as = chart_ids(names)
    gone = stale(names, rated)
    verdicts = []
    for n in noms:
        model_id = known_as.get(n.model, "")
        tier = selection.tiers(selection.load(), n.task_class)[0]
        # Like for like: the member's own level is what runs, so the candidate is
        # measured at it. A candidate measured at another level is still a slot,
        # not a comparison across levels.
        verdicts.append(dict(status(n, measured, selection.effort_of(tier, n.member),
                                    model_id, pol), **{k: v for k, v in n.line().items()
                                                       if k != "member"}))
    was = read_dismissals()
    still, dismissed = [], []
    for n in noms:
        record = was.get((n.task_class, n.model, n.member))
        if record is not None and not grew(n, record, pol):
            dismissed.append(n)
        else:
            still.append(n)
    if args.dismiss:
        if len(args.dismiss) not in (2, 3):
            print("scout: --dismiss wants CLASS MODEL [MEMBER]", file=sys.stderr)
            return 2
        wanted = [n for n in noms if n.task_class == args.dismiss[0]
                  and n.model == args.dismiss[1]
                  and (len(args.dismiss) == 2 or n.member == args.dismiss[2])]
        if not wanted:
            print(f"scout: no nomination to dismiss for {' '.join(args.dismiss)}",
                  file=sys.stderr)
            return 2
        for n in wanted:
            dismiss(n)
        print(f"scout: {len(wanted)} dismissal(s) recorded in {dismissals_path()}",
              file=sys.stderr)
    # No previous run means nothing is "new since" it: the first run writes the
    # baseline and stays quiet, so a nightly `--check` cannot fail on installation.
    previous = read_state() if state_path().is_file() else None
    new = [n for n in still if previous is not None and n.key not in previous]
    if args.json:
        print(json.dumps({
            "source": source, "chart_updated": updated, "rated": len(rows),
            "profile": acting, "jurisdictions": sorted(allowed),
            "judged": {c: [m for m, _r in found] for c, found in members.items()},
            "unrated": sorted(set(unrated)), "no_arena": no_arena, "stale": gone,
            "unknown_hosts": [{"host": h, "models": m} for h, m in unknown],
            "nominations": [n.line() for n in still],
            "dismissed": [n.line() for n in dismissed],
            "calibration": [{"model": m, "effort": e, **got}
                            for (m, e), got in measured.items()],
            "verdicts": verdicts,
            "new": [n.key for n in new],
        }, indent=2))
    else:
        report(still, dismissed, unknown, unrated, members, updated, source, cat, cfg,
               measured, verdicts)
        for n in new:
            print(f"  NEW       {n.task_class} {n.model} beats {n.member}")
        for g in gone:
            print(f"  STALE     arena: {g} -- the chart no longer holds this name")
    write_state([n.key for n in still])
    return 1 if args.check and (new or gone) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
