---
title: Boundaries — one config, three harnesses
summary: Why the read/write boundary rules exist, how they compile, what they miss
origin: authored
authority: agent
trust: trusted
last_verified: 2026-08-31
use_count: 10
last_used: 2026-10-11
promoted_from: []
source:
supersedes:
related: [memory-mechanisms, memory-architecture, claude-code, opencode, hermes, mcp-servers, memory-poisoning-posture, pi]
tags: [boundaries, enforcement, hooks, privacy, guard]
scope: []
area: [B]
stability: stable
verified_log: [2026-08-31]
---

# Boundaries — one config, three harnesses

What agents may not touch is declared once, in `../../../../config/boundaries/read-write.yaml`, and
compiled outward to every harness. This leaf says how that works, what is
genuinely enforced, and — the part that matters — what is not.

Read [[memory-mechanisms]] first for the level 1–4 table. Everything below is
an application of it: **a rule at level 2 stops a call; a rule at level 4 asks
politely.** The whole point of compiling is that both come from the same line.

## Why a config, and not prose

Before 2026-08-31 the one enforced boundary was written five times: in
`../../../../config/practice/user/user-identity.md`, in `MEMORY.md`, in [[memory-architecture]], in
[[memory-mechanisms]], and in the Python of the boundary guard (named `zettel-guard` until 2026-08-31).
When the rule changed from no-write to no-read, four of the five were updated
and `../../../../config/practice/user/user-identity.md` was not — so for a full day agents were told to read the vault by
the file they load first, while a hook denied every attempt.

A rule written five times drifts. A rule compiled from one file cannot.

## The pieces

| Path | What it is | Who writes it |
|---|---|---|
| `../../../../config/boundaries/read-write.yaml` | the rules — paths, modes, reasons | **human only** |
| `engine/boundaries/_miniyaml.py` | restricted YAML reader, stdlib only | agent |
| `engine/boundaries/_boundaries.py` | load + validate + path matching, shared | agent |
| `engine/boundaries/compile.py` | the compiler, three emitters | agent |
| `engine/boundaries/guard.py` | Claude Code `PreToolUse` hook — **level 2** | agent |
| `engine/boundaries/opencode-plugin/` | opencode plugin — **level 2** | agent |
| `engine/boundaries/pi-guard/` | Pi extension — **level 2** | agent |
| `config/boundaries/boundaries.json` | compiled rules, both guards read it | **generated** |
| `../../../../config/boundaries/read-write.md` | prose restatement — **level 4** | **generated** |

```bash
boundaries-compile                       # regenerate every target
boundaries-compile --check               # exit 1 if stale — pre-commit hook
boundaries-compile --explain PATH --model local|remote
python3 engine/boundaries/test_guard.py            # 47 cases
node engine/boundaries/opencode-plugin/test-plugin.mjs    # 18 cases
```

## Modes

| Mode | Denies | Note |
|---|---|---|
| `no-read-write` | reads and writes | the strictest; D1 uses it |
| `no-read` | reads only | writes still allowed |
| `no-write` | writes, deletes, moves | **reads stay allowed, deliberately** |
| `no-push` | `git push`, rebase, `--amend`, `filter-*` | commit and branch stay free |

## Decisions — how hard a rule bites

`mode:` says which operations a rule covers. `decision:` says what happens when
one matches. They are orthogonal, and conflating them produced a real bug.

| Decision | Claude Code | Effect |
|---|---|---|
| `deny` *(default)* | `permissionDecision: "deny"` | refused; the agent cannot proceed |
| `ask` | `permissionDecision: "ask"` | the user is prompted and decides |

**Why `ask` exists.** The `no-push` rule's own reason said *"ask before
pushing"*, but it compiled to a hard deny. On 2026-08-31 the user instructed a
push, the agent had explicit authorization, and the guard refused anyway — the
rule could not be satisfied by the thing it asked for. A boundary an agent can
never satisfy stops reading as a boundary and starts reading as noise, which
weakens every other rule in the file.

Use `ask` only where the reason genuinely is *the user decides*. A rule
protecting against disclosure or data loss should stay `deny`: the point there
is that no answer in the moment makes it safe.

**Honest limit — opencode.** Its plugin channel is a thrown exception, which
aborts the call; there is no confirmation prompt. An `ask` rule therefore
degrades to a refusal there, and the message says so and names Claude Code as
the place the prompt exists. Letting it through silently would be the worse
failure: a rule that is enforced in one harness and absent in another is how
the D1 drift happened.

`no-write` is the mode that forced a design decision. For `no-read` rules the
guard denies *any* Bash reference to the path — a false positive costs one
question to the user, a false negative costs an irreversible disclosure. Doing
the same for `no-write` would deny `restic check`, which makes a backup rule
that protects nothing. So Bash commands get a write-classifier (redirects whose
target resolves under the path, plus a mutating-verb list) and that half is
weaker. The asymmetry is deliberate and is why the modes are separate.

## The `models:` axis

`local` means inference runs on this machine (Ollama). `remote` means the tool
result is transmitted to a third party and may be retained.

These are not the same boundary. `~/04_RESOURCES/Personal-Documents` holds
personal information: a local model reading it is a file read; a remote model
reading it is disclosure, and irreversible. Collapsing the axis forces a choice
between over-restricting local models and under-restricting remote ones.

(`~/06_SYSTEM/Metadata` carried a rule of this shape until 2026-09-29, when the
directory was retired. The example above is its replacement, not a second rule
replacing it — the shape is what this section is about.)

This is also where the old `../../../../config/practice/user/user-identity.md` §Values line *"Local-first for anything
personal"* went. It was a preference with no path attached; here it is
`models: remote` on named paths, which is enforceable.

**How each harness resolves the live model:**

- **Claude Code** — the `PreToolUse` payload carries **no** model field
  (verified 2026-08-31 by dumping one; the fields are `session_id`,
  `transcript_path`, `cwd`, `prompt_id`, `permission_mode`, `effort`,
  `hook_event_name`, `tool_name`, `tool_input`, `tool_use_id`). It does carry
  `transcript_path`, and every assistant record in that JSONL has
  `message.model`. `wards` reads the last 64 KB and takes the newest.
  This is better than the static per-harness assumption the design assumed it
  would need.
- **opencode** — `tool.execute.before` has no model either, but `chat.params`
  does. The plugin records provider id per `sessionID` there and reads it back.
- Both fail to `remote`, the class more rules apply to. An unresolvable model
  is guarded, not waved through.

## Per-harness status

### Claude Code — enforced, level 2

`engine/boundaries/guard.py`, wired as a `PreToolUse` hook in
`~/.claude/settings.json` (a symlink into the public `dotfiles` repo — edit the
source there, never the symlink) matching
`Read|Edit|Write|NotebookEdit|Glob|Grep|Bash`.

A denial was observed live for **each** of the four modes on 2026-08-31, each
quoting its rule's own `reason:`.

Hatch: `touch ~/.claude/guard.disabled`, re-arm by removing it. The
older `~/.claude/zettel-guard.disabled` is still honoured for one cycle so an
existing hatch does not silently stop working. The guard is
`engine/boundaries/guard.py`; `pazras-guard` beside it is a symlink kept for one
cycle, while the harness configs that name the old path are updated, then
delete.

### opencode — enforced, level 2

`ROADMAP.md` recorded opencode's plugin-hook event names as unverified. They
are now verified against `@opencode-ai/plugin@1.18.18`'s `Hooks` interface at
`~/.config/opencode/node_modules/@opencode-ai/plugin/dist/index.d.ts`:

- `tool.execute.before(input: {tool, sessionID, callID}, output: {args})` —
  fires before every tool call. **Throwing from it is the deny channel.**
- `permission.ask(input: Permission, output: {status: "ask"|"deny"|"allow"})` —
  an explicit deny channel, but it only fires when a permission is actually
  asked, so it depends on permission config. Not used; noted as the fallback.
- `chat.params` — the model, for the `models:` axis.

**Do not install it through `plugin:`.** That array takes npm package names.
A bare local name makes opencode create `~/.cache/opencode/packages/<name>/`,
fail to fetch it from npm, **start anyway with no error logged**, and never run
the plugin — verified by watching `git push` succeed with the plugin
"installed". A symlink into `~/.config/opencode/node_modules/` does not help
either. Full write-up in [[opencode]].

What works is the plugin directory: `~/.config/opencode/plugin/*.js`, holding a
one-line re-export shim so the real source stays version-controlled here:

```js
export { FamiliarBoundaries } from "/home/<user>/06_SYSTEM/engine/boundaries/opencode-plugin/index.js";
```

Denials observed live 2026-08-31 on 'deepseek/deepseek-v4-flash': the bash half
(`no-push` on `git push --dry-run`, with `git status` passing as a control) and
the tool-path half (`no-read` on `read.filePath` into a `models: remote` path). The `local` side of the axis is covered by the
unit tests, not yet by a live local-model run.

**Test a denial inside the worktree.** `opencode run` auto-rejects permission
prompts non-interactively, so a read outside the worktree is refused as
`external_directory` before any plugin hook sees it. The first attempt here was
inconclusive for exactly that reason.

Hatch: `touch ~/.config/opencode/guard.disabled` (the Pi extension reads
`~/.pi/agent/guard.disabled`; all three harnesses use the same file name).

**Installed by stow, not by hand.** Three loader shims live in the dotfiles'
`ai` stow package — one for opencode, two for Pi — so a new machine gets them
from `bootstrap.sh`. They were hand-installed until 2026-10-13, and the leaf said
the reason was the machine-absolute path they hold — but the four other harness
configs in that repo name `/home/<user>/06_SYSTEM/...` already, and a shim whose
absence is invisible is worse than a path that is public. Stowing also brings
them under the healthcheck's stow audit: `bootstrap.sh --dry-run` reports a
missing one, and `--fix` restows.

If you must install one by hand (a machine without the dotfiles), the shim is
one re-export:

```bash
mkdir -p ~/.config/opencode/plugin
printf 'export { FamiliarBoundaries } from "%s/engine/boundaries/opencode-plugin/index.js";\n' \
  "$HOME/06_SYSTEM" > ~/.config/opencode/plugin/familiar-boundaries.js
```

### hermes — advisory only, level 4, with a level-2 hook available

**hermes has a blocking hook surface; this system does not use it yet.** The
2026-08-31 verdict "there is no hook surface" was wrong when written:
`agent/shell_hooks.py` (upstream since 2026-04-20) reads a `hooks:` block from
`config.yaml`, and this machine's own `config.yaml` now uses it for
`on_session_end` capture. Verified 2026-10-09 by reading
`~/.hermes/hermes-agent/agent/shell_hooks.py` and `model_tools.py`:

- **`pre_tool_call`** fires once per tool call, before it runs; the hooks are
  registered from the CLI and the gateway entry points alike.
- **A hook blocks** by exiting 2, or by printing `{"decision": "block",
  "reason": …}` — the Claude Code shape. `{"action": "block", "message": …}`
  also works.
- **stdin** is `{hook_event_name, tool_name, tool_input, session_id, cwd, extra}`.
- **Fail-open by default.** A crash or timeout allows the call;
  `fail_closed: true` on the entry reverses that.

`engine/boundaries/guard.py` speaks hermes's dialect since 2026-10-09
(`dev/hermes-guard/` H1–H2): a payload with `hook_event_name: pre_tool_call` is
translated to the Claude Code tool whose rules apply (`read_file`→`Read`,
`write_file`→`Write`, `patch`→`Edit` including V4A headers, `search_files`→
`Grep`/`Glob`, `terminal` and `execute_code`→the Bash scan), and a denial
returns exit 2 with `{"decision": "block"}`. `ask` becomes a block: hermes has
no confirm. **It is not wired into `config.yaml` yet** (H3), so hermes is still
level 4.

Until that ships, hermes gets generated prose, and the generated text **says it
is advisory**, so an agent reading it knows the rule is not backed by a guard.
It goes into `~/.hermes/memories/MEMORY.md` between
`<!-- BEGIN GENERATED boundaries -->` markers — that file plus
`../../../../config/practice/user/user-identity.md` are the only things hermes
loads (`hermes-agent/agent/system_prompt.py`), so an extra file would be inert.
Watch the 2,200-char cap in `config.yaml` §memory.

**`HERMES_WRITE_SAFE_ROOT`** is a supported env-var **allowlist** of write
roots: set it, and every write outside those roots is denied. It cannot express
"deny this one path" — it is the complement — so it is not used here.

**The gateway socket is not an interception point.** `~/.hermes/gateway.sock`
and `mcp_serve.py` expose messaging conversations to MCP clients
(`conversations_list`, `messages_send`, …); tool calls do not transit them.
Read 2026-10-09.

## Honest limits

State these rather than implying the loop is airtight.

- **A guard is not a sandbox.** The tool-path checks are airtight; the Bash
  scanning is best-effort against **drift**, not against an adversary. An agent
  set on routing around it can encode a path. This raises the cost of drift; it
  does not defeat an attacker.
- **MCP tools are not covered.** `PATH_FIELDS` and the opencode `TOOLS` map
  cover built-in tools. MCP tools take arbitrary input shapes and no check here
  sees them.
- **Subagents** inherit the harness hook, so Claude Code subagents are covered;
  anything that shells out to another agent binary is not.
- **The Bash write-classifier is coarse.** `rm /tmp/x && ls <protected>` is
  denied. Erring toward denial is the intended direction.
- **A stale compile cannot enforce the wrong rules.** `wards` checks the
  compiled JSON's `source_sha256` against the live YAML and re-parses the YAML
  itself on a mismatch, warning on stderr. It never denies everything because a
  compile was forgotten. The opencode plugin has no such check — it reads the
  compiled JSON only, which is why `--check` belongs in a pre-commit hook.
- **The rule set will be incomplete.** That is fine. One file that is
  incomplete beats five files that disagree.
- **The JS guards fail open on a missing rules file.** R2e (2026-10-07) moved
  the compiled JSON to `config/boundaries/` and the opencode plugin and the Pi
  guard kept reading its pre-R2e location; from 2026-10-07 to 2026-10-11
  neither enforced any rule, and nothing reported it. The retired-path check
  missed it because the JS joined the path from two pieces, so the full
  literal never appeared in the file. Both suites
  (`checks.py --run manual`: `pi-guard-node`, `opencode-plugin-node`) showed
  it, but they run in no automatic gate. The path is now a `roots-twin` of
  `BOUNDARIES_JSON`, so `test_roots.py` (pre-commit) fails on the next move.

## Verification

```bash
engine/boundaries/compile.py --check          # all targets in sync
python3 engine/boundaries/test_guard.py        # Claude Code guard
node engine/boundaries/opencode-plugin/test-plugin.mjs
grep -n wards ~/.claude/settings.json       # hook is wired
grep -n BEGIN.GENERATED ~/.hermes/memories/MEMORY.md
```

To check a specific path without guessing:

```bash
boundaries-compile --explain ~/some/path --model remote
```

Live denials, not just unit tests, are what count. Attempt one crossing per
mode in a real session and read the message back — if it does not name the rule
and say what to do instead, the `reason:`/`instead:` fields need work, not the
code.

## opencode's level depends on its version, not only its mode

**Verified 2026-09-01, re-verified 2026-10-09 with the opposite result.** On
2026-09-01, under `opencode run` (the non-interactive one-shot runner), a
plugin's module loaded and its factory ran, and then **no hook fired**. On
2026-10-09, opencode 1.18.23, the same probe saw `event`, `chat.params` and
`tool.execute.before` fire, and a throw from `tool.execute.before` denied the
read. Details and the probe: [[opencode]].

| opencode mode | Enforcement |
|---|---|
| interactive TUI | **level 2** — `tool.execute.before` denies, verified 2026-08-31 |
| `opencode run`, 1.18.23 | **level 2** — the hook fires and a throw denies, verified with a probe plugin 2026-10-09 |
| `opencode run`, the 2026-09-01 version | level 4 — the plugin loaded, no hook ran |

The familiar plugin itself has not been observed denying under `opencode run`;
the probe proves the hook, and the plugin is that hook. An opencode upgrade can
reverse this again without any visible sign, so re-run the probe in [[opencode]]
after one.

This is the level table from [[memory-mechanisms]] biting a second time. The
first lesson was that the same rule is enforcement in one harness and a request
in another; the second is that it can differ **between two modes, and two
versions, of one harness**. Never state a harness's level without naming the
mode and the version it was verified on.

## Verified guard behaviour (2026-08-31)

- **`no-push` is the rule that produced the `decision:` axis.** Its prose said
  *"ask before pushing"* while it compiled to a hard deny, so on 2026-08-31 the
  user authorised a push and the guard refused anyway — a rule that cannot be
  satisfied by the thing it asks for. `decision: ask` exists because of it; see
  §Decisions above.
- Claude Code's `PreToolUse` payload carries **no model field**, but carries
  `transcript_path`, and every assistant record there has `message.model`. The
  guard tails the transcript to resolve the *live* model and fails safe to
  `remote` (one ~64 KB read). Neither fallback the handoff proposed was needed.
- **`2>&1` is an fd duplication, not a write.** The write-classifier asks
  whether the redirect *target* resolves under the protected path, not whether
  any `>` is present. A persisted shell cwd caused a second false positive —
  re-run classifier checks with absolute paths.
- **opencode:** installing a plugin by bare npm name in the `plugin:` array
  fails silently (empty install dirs, no fetch, no log, guard not loaded). The
  working mechanism is `~/.config/opencode/plugin/*.js`. opencode's own
  `external_directory` permission fires *before* plugin hooks, so test denials
  on paths inside the worktree.
- **hermes has no hook surface** — `~/.hermes/hooks/` is empty and there is no
  `hooks:` config key. `file_safety.py` hardcodes a few write denials, and
  `HERMES_WRITE_SAFE_ROOT` is a write *allowlist*, too coarse to express "deny
  one path". hermes enforcement is advisory only.
- **Stale-compile safety:** the guard checks the compiled JSON's
  `source_sha256` against the live YAML and re-parses the YAML itself on
  mismatch. A stale compile never enforces wrong rules and never causes a
  denial storm.

- **Cloud distillation is a second disclosure channel the guard cannot see.**
  The consolidation pass does not read a protected path; it reads a staged
  transcript of a session that was *working* there, and sends that to a remote
  model. `../../../../engine/consolidation/stages/replay.py` therefore derives its exclusion list from the
  compiled rules rather than keeping its own, and fails closed.
