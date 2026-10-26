"""loadout -- what a harness DECLARES to the model, read from its own session.

THE GAP THIS FILLS. `tree` measures the tree; `harness/route` measure a driven
harness's prefix. Neither answers the question that decided 2026-10-25's trims:
*how many bytes of tool declaration does every request carry?* That number is
not in any config file -- it is the sum of what each extension registered, and
only the session record knows it. On 2026-10-25 it was 19,435 bytes across 11
tools, 61% of the fixed prompt, and it had grown one reasonable-looking tool at
a time.

THE SESSION IS THE SOURCE, NOT A MODEL OF IT. Pi records the assembled prompt
in its session JSONL as system messages: the first carries every `sections`
entry and `toolsAdded` declaration, later ones patch by name (`null` removes)
and list `toolsAdded`/`toolsRemoved`. Replaying those in order yields the
loadout the next request will carry, byte for byte as pi stored it. No harness
is started, no token is spent, nothing is sent anywhere.

WHAT IT IS NOT. The stored declaration is not the provider's wire payload:
pi wraps each tool as `{type, function: {...}}` and may rewrite a schema for
strict sampling, so the wire is a few percent larger than the number here.
Measured 2026-10-25 the caps catch growth of that size only when it comes from
adding or fattening a tool, which is the growth that happens.

ONE BUDGET PER OWNER, NOT ONE TOTAL. A total tells you a session is expensive;
it does not tell you what to change. Tool bytes are an extension set -- disable
one, or prune it (see `engine/context/pi-loadout/`). Section bytes are a
generator output (`familiar context l1`) plus the project's own context files.
Two caps, two fixes.

THE CAP IS POLICY, NOT MEASUREMENT. Set above the measured 2026-10-25 state
with headroom, the way `navigation.BUDGETS` sits above the routing table: it
answers "did something grow without a decision?" and nothing else.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib

from context import tokens

SESSION_ROOT = pathlib.Path.home() / ".pi" / "agent" / "sessions"

# Tokens, per owner, measured with the estimator rather than estimated: pi
# sections 2,919 and tools 1,121 on 2026-10-25 after the trims; tools were
# 5,079 before them. Caps sit ~20-35% above the trimmed state -- enough that a
# description edit does not trip them, tight enough that the MCP gateway coming
# back (+854) or the four web tools returning eagerly (~+2,700) does.
BUDGETS = {"pi": {"sections": 3500, "tools": 1500}}


@dataclasses.dataclass
class Tool:
    name: str
    chars: int
    tokens: int


@dataclasses.dataclass
class Loadout:
    harness: str
    session: str
    cwd: str
    sections: dict            # name -> text
    content: str              # the system message's own content, usually ""
    tools: list               # [Tool], declaration order

    @property
    def section_chars(self) -> int:
        return sum(len(t) for t in self.sections.values()) + len(self.content)

    def section_rows(self) -> list:
        """(name, chars, tokens) per section, tokens counted one section at a
        time. The table prints these rows and sums them, so a reader adding the
        column up gets the total -- counting the concatenation instead moves by
        a token at the joins and makes the table disagree with itself."""
        rows = [(name, len(text), tokens.count(text)) for name, text in self.sections.items()]
        if self.content:
            rows.append(("(content)", len(self.content), tokens.count(self.content)))
        return sorted(rows, key=lambda row: -row[2])

    @property
    def section_tokens(self) -> int:
        return sum(t for _, _, t in self.section_rows())

    @property
    def tool_chars(self) -> int:
        return sum(t.chars for t in self.tools)

    @property
    def tool_tokens(self) -> int:
        return sum(t.tokens for t in self.tools)

    @property
    def total_chars(self) -> int:
        return self.section_chars + self.tool_chars

    @property
    def total_tokens(self) -> int:
        return self.section_tokens + self.tool_tokens


def slug(cwd: str) -> str:
    """Pi's session directory name for a working directory: the leading
    separator dropped, `/`, `\\` and `:` replaced by `-`, wrapped in `--`
    (docs/session-format.md)."""
    inner = str(cwd).lstrip("/")
    for ch in ("/", "\\", ":"):
        inner = inner.replace(ch, "-")
    return f"--{inner}--"


def session_dir(cwd: str, root: pathlib.Path = SESSION_ROOT) -> pathlib.Path:
    return pathlib.Path(root) / slug(cwd)


def newest_session(cwd: str, root: pathlib.Path = SESSION_ROOT) -> pathlib.Path | None:
    """The most recently written session for this cwd, or None. Mtime, not the
    timestamp in the name: a resumed session is appended to."""
    directory = session_dir(cwd, root)
    if not directory.is_dir():
        return None
    files = [p for p in directory.glob("*.jsonl") if p.is_file()]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def read(path: pathlib.Path) -> Loadout:
    """Replay pi's system messages into the loadout they describe.

    A truncated last line is normal (a session being written as this runs), so
    an unparseable line is skipped rather than fatal. Order is pi's:
    `toolsRemoved` before `toolsAdded` within one message, sections overwritten
    by name, `null` deleting one.
    """
    sections: dict = {}
    content: list = []
    tools: dict = {}
    cwd = ""
    for line in pathlib.Path(path).read_text(errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "session":
            cwd = entry.get("cwd", "")
            continue
        if entry.get("type") != "message":
            continue
        message = entry.get("message") or {}
        if message.get("role") != "system":
            continue
        text = message.get("content")
        if isinstance(text, str) and text.strip():
            content.append(text)
        for name, value in (message.get("sections") or {}).items():
            if value is None:
                sections.pop(name, None)
            else:
                sections[name] = value
        for tool in message.get("toolsRemoved") or []:
            tools.pop(tool.get("name"), None)
        for tool in message.get("toolsAdded") or []:
            tools[tool.get("name")] = tool
    return Loadout(
        harness="pi",
        session=str(path),
        cwd=cwd,
        sections=sections,
        content="\n\n".join(content),
        tools=[Tool(name=name, chars=len(json.dumps(tool, ensure_ascii=False)),
                    tokens=tokens.count_json(tool))
               for name, tool in tools.items()],
    )


def check(loadout: Loadout, budgets: dict | None = None) -> list:
    """The caps this loadout breaks, as strings a person can act on. Local,
    no session, no network -- so it is testable with a fixture."""
    caps = (budgets or BUDGETS).get(loadout.harness)
    if not caps:
        return []
    problems = []
    for owner, value in (("sections", loadout.section_tokens), ("tools", loadout.tool_tokens)):
        cap = caps.get(owner)
        if cap is not None and value > cap:
            problems.append(f"{owner}: {value:,} tokens over cap {cap:,}")
    return problems
