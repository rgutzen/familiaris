"""profiles -- which account serves a catalogue model, and what it may see of the data.

`config/orchestration/profiles.yaml` holds what depends on the ACCOUNT, not the model
(decisions 19, 25, 26): the pi provider id, the key variable or login file, and the
privacy settings. The user's `pi-<profile>` wrappers set `PI_PROFILE` and unset the
personal keys that have a `<KEY>_<PROFILE>` twin, so the orchestrator never chooses an
account; it reads the one the process already runs under.

`resolve` answers one question: does this profile serve this model? It checks that a
key variable is SET or a login file EXISTS, never its value, so no secret enters a
message. A vendor without a key is unavailable, never borrowed (decision 26). The one
way past is `approve=REASON`: an unavailable model resolves through ANOTHER declared
profile that has it, the billing pool is named, and the approval is appended to
`orchestration-approvals.jsonl`. A candidate is never callable, so never approvable.
Borrowing sees keys through `env`, so a key the active profile's wrapper unset is
invisible; a Claude login file is visible.

15a (2026-10-24) adds a FIFTH reason a model is unavailable: a `pool: quota` model
whose account has spent its window. It is an availability fact, not a price signal
(14d's weight still prices a nearly-full window and lets it run), and it is what a
binding's `fallbacks:` were written for -- before it, a spent Claude window reached
pi and failed there, naming no model. The threshold is `window_closed_at` in
profiles.yaml; the reading is `price.live_quota()`, memoized per account for the
probe's own 15 s. No reading, no block.
"""
from __future__ import annotations

import dataclasses
import datetime
import json
import os
import pathlib
import time

from lib import _miniyaml
from lib import roots

PROFILES = roots.SUBAGENTS / "profiles.yaml"
CATALOGUE = roots.SUBAGENTS / "models.yaml"
APPROVALS = "orchestration-approvals.jsonl"
_UNSET = object()                # `resolve(window=...)` means "probe it" (15a)


class ProfileError(ValueError):
    """A bad profile name or model id; the CLI maps it to exit 2."""


@dataclasses.dataclass
class Resolution:
    model: str
    profile: str                    # the active profile
    provider: str = ""
    available: bool = False
    reason: str = ""
    privacy: str = ""
    pool: str = ""                  # set only when borrowed: `usd via profile private`

    def line(self) -> str:
        if not self.available:
            return f"{self.model}: unavailable in profile {self.profile}: {self.reason}"
        tail = f", pool {self.pool}" if self.pool else ""
        return (f"{self.model} -> {self.provider}/{self.model} "
                f"(profile {self.profile}, privacy {self.privacy}{tail})")


def load(path: pathlib.Path = PROFILES) -> dict:
    return _miniyaml.load(path.read_text(encoding="utf-8"))


def active(env=os.environ, cfg: dict | None = None) -> str:
    cfg = cfg or load()
    name = (env.get("PI_PROFILE") or "").strip() or cfg["default"]
    if name not in cfg["profiles"]:
        raise ProfileError(f"undeclared profile {name!r}; declared: {', '.join(cfg['profiles'])}")
    return name


def declared(decl: dict, cfg: dict | None = None) -> str:
    """The profile a RECORD declares (2a). A record written before the field
    existed reads as the config default: the record is a declaration the engine
    must not rewrite, so the fallback is a reading rule, not a migration."""
    cfg = cfg or load()
    name = str(decl.get("profile") or "").strip() or cfg["default"]
    if name not in cfg["profiles"]:
        raise ProfileError(f"undeclared profile {name!r}; declared: {', '.join(cfg['profiles'])}")
    return name


def home_claude() -> pathlib.Path:
    """The primary Claude home, which stays IMPLICIT (see `account_env`)."""
    return pathlib.Path.home() / ".claude"


def account_env(profile: str, cfg: dict | None = None) -> dict:
    """What a pi child needs to spend THIS profile's account, as an env overlay
    (a value of None means "unset"). Derived from the profile's declaration
    only -- no secret is read, only paths.

    * `PI_PROFILE` -- the engine reads it back through `active`.
    * `CLAUDE_CONFIG_DIR`, from the login's directory, and UNSET when that is
      `~/.claude`: `pi-profile` measured that pointing the variable at the
      primary home makes Claude look for a login that is not there.
    * the personal twin of every `<KEY>_<PROFILE>` the profile declares, unset --
      the wrapper's rule, so a personal key cannot reach a company call.
    """
    cfg = cfg or load()
    if profile not in cfg["profiles"]:
        raise ProfileError(f"undeclared profile {profile!r}; declared: {', '.join(cfg['profiles'])}")
    env = {"PI_PROFILE": profile}
    for vendor in (cfg["profiles"][profile].get("vendors") or {}).values():
        login = str(vendor.get("login") or "")
        if login:
            home = pathlib.Path(os.path.expanduser(login)).parent
            env["CLAUDE_CONFIG_DIR"] = None if home == home_claude() else str(home)
        key = str(vendor.get("key_env") or "")
        suffix = f"_{profile.upper()}"
        if key.endswith(suffix) and len(key) > len(suffix):
            env[key[:-len(suffix)]] = None
    return env


def with_account(env, profile: str, cfg: dict | None = None) -> dict:
    """A FULL environment for `profile`: `env` with the overlay applied, a None
    value removing the key. A copy, so the caller's environment never changes.

    Use this, not `account_env` alone, wherever the value is handed to
    `subprocess`/`pi_call`: those take an environment, not a patch of one
    (`pi_call.env_for(base=...)` replaces it -- measured 2026-10-22, an overlay
    passed straight through starts `pi` with no PATH)."""
    out = dict(env)
    for k, v in account_env(profile, cfg).items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = v
    return out


def marker(cwd) -> tuple:
    """(profile, the marker's path) for the nearest `.pi-profile` at or above
    `cwd`, or ("", None). This is the dotfiles' `pi()` rule, read ONLY to check a
    declaration against the work tree (2d): it never chooses a profile, because
    a job whose cwd sits outside a marker would then bill personal silently."""
    path = pathlib.Path(os.path.expanduser(str(cwd)))
    if not path.is_absolute():
        path = path.resolve()
    for d in (path, *path.parents):
        f = d / ".pi-profile"
        try:
            text = f.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        name = text.split("\n", 1)[0].strip()
        if name:
            return name, f
    return "", None


def providers(profile: str, cfg: dict | None = None) -> dict:
    """vendor -> pi provider id for one profile (`none` kept); models --check uses it."""
    cfg = cfg or load()
    return {v: d.get("provider", "none") for v, d in cfg["profiles"][profile]["vendors"].items()}


def find(cat: dict, model_id: str):
    """(section, entry) matching an id or an alias, or (None, None)."""
    for section in ("models", "candidates"):
        for e in cat.get(section) or []:
            aliases = [a.strip() for a in (e.get("aliases") or "").split(",")]
            if model_id == e.get("id") or model_id in aliases:
                return section, e
    return None, None


def privacy_class(jurisdiction: str, training: str, cfg: dict) -> str:
    rules = cfg["privacy_class"]
    if jurisdiction == "local":
        return rules["local"]
    token = (training or "unknown").split(" — ")[0].strip()
    return f"{jurisdiction}-{rules['suffix'].get(token, rules['suffix']['unknown'])}"


def _own(entry: dict, profile: str, cfg: dict, env, window: float | None = None) -> Resolution:
    """The model under ONE profile, no borrowing."""
    r = Resolution(entry["id"], profile)
    p = cfg["profiles"][profile]
    vendor = (p.get("vendors") or {}).get(entry["vendor"])
    if vendor is None:
        r.reason = f"vendor {entry['vendor']} is not declared in the profile"
        return r
    r.provider = vendor.get("provider", "none")
    r.privacy = privacy_class(entry["jurisdiction"], _dig(vendor, "training", "value"), cfg)
    if entry["jurisdiction"] not in (p.get("jurisdictions") or []):
        r.reason = f"jurisdiction {entry['jurisdiction']} is not allowed in the profile"
    elif r.provider == "none":
        r.reason = f"pi does not serve {entry['vendor']}" + (
            f" ({vendor['note']})" if vendor.get("note") else "")
    elif vendor.get("key_env") and not (env.get(vendor["key_env"]) or "").strip():
        r.reason = f"{vendor['key_env']} is not set"
    elif vendor.get("login") and not pathlib.Path(vendor["login"]).expanduser().is_file():
        r.reason = f"{vendor['login']} does not exist"
    elif (spent := _spent(entry, cfg, window)):
        r.reason = spent
    else:
        r.available = True
    return r


# ── 15a: a spent window is unavailable, not merely dear ─────────────────────
# The quota pool was priced (14d) but never gated, so a binding's `fallbacks:`
# could only fire on a missing key: a spent Claude window reached pi and failed
# there, naming no model, instead of swapping to the entry the binding declared.
# The threshold is `window_closed_at` in profiles.yaml because `dispatch` imports
# THIS module and the reverse import would be a cycle.
WINDOW_CLOSED_AT = 0.98          # read from the config; this is only the fallback
WINDOW_TTL = 15.0                # the schedule track's own probe_interval
_ROOM: dict = {}                 # profile -> (monotonic, reading)


def _window(profile: str, env, now: float | None = None) -> float | None:
    """The fuller Claude window's fraction for ONE account, memoized for the
    probe's own interval -- `resolve` is called once per chain entry, and a
    probe per entry would put a subprocess on every binding call."""
    now = time.monotonic() if now is None else now
    kept = _ROOM.get(profile)
    if kept is not None and now - kept[0] < WINDOW_TTL:
        return kept[1]
    try:
        from orchestration import price                     # noqa: PLC0415 -- see WINDOW_CLOSED_AT
        reading = price.live_quota(env)
    except Exception:                                       # noqa: BLE001 -- a resolve must not die on a probe
        reading = None
    _ROOM[profile] = (now, reading)
    return reading


def _spent(entry: dict, cfg: dict, window: float | None) -> str:
    """Why a `pool: quota` model is out of room, or "" -- no reading is no block.

    Only the QUOTA pool is gated. A `usd` model has no window to spend and a
    `free` one has no bill, so neither is ever skipped for this reason."""
    if window is None or entry.get("pool") != "quota":
        return ""
    closed_at = float(cfg.get("window_closed_at") or WINDOW_CLOSED_AT)
    if window < closed_at:
        return ""
    return (f"its quota window is spent: the fuller Claude window reads {window:.2f}, "
            f"closed at {closed_at:.2f}")


def _dig(d, *path):
    for k in path:
        d = d.get(k) if isinstance(d, dict) else None
    return d


def data_dir(env=os.environ) -> pathlib.Path:
    return roots.data_root(env)


def resolve(model_id: str, profile: str, env=os.environ, approve: str | None = None,
            cfg: dict | None = None, cat: dict | None = None,
            window: float | None | object = _UNSET) -> Resolution:
    """Does `profile` serve `model_id`? `window` overrides the live reading (15a):
    `_UNSET` probes the active account, a float is a reading, `None` is no reading.
    Only the ACTIVE profile's account is probed -- `live_quota` reads that one."""
    cfg = cfg or load()
    cat = cat or _miniyaml.load(CATALOGUE.read_text(encoding="utf-8"))
    if profile not in cfg["profiles"]:
        raise ProfileError(f"undeclared profile {profile!r}; declared: {', '.join(cfg['profiles'])}")
    if approve is not None and not approve.strip():
        raise ProfileError("--approve needs a reason")
    section, entry = find(cat, model_id)
    if entry is None:
        raise ProfileError(f"unknown model id {model_id!r}: not in models: or candidates:")
    if section == "candidates":
        return Resolution(entry["id"], profile, reason="a candidate, not callable")
    reading = window
    if reading is _UNSET:
        reading = _window(profile, env) if profile == active(env, cfg) else None
    own = _own(entry, profile, cfg, env, window=reading)
    if own.available or approve is None:
        return own
    for other in cfg["profiles"]:
        alt = _own(entry, other, cfg, env) if other != profile else None
        if alt and alt.available:
            _log(entry["id"], profile, other, alt.provider, approve, env)
            return dataclasses.replace(alt, profile=profile,
                                       pool=f"{entry['pool']} via profile {other}")
    own.reason += "; no other declared profile has it available"
    return own


def _log(model: str, active_: str, borrowed: str, provider: str, reason: str, env) -> None:
    path = data_dir(env) / APPROVALS
    path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(ts=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               model=model, profile=active_, borrowed=borrowed, provider=provider, reason=reason)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
