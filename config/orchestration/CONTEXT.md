# Orchestration — the Loom: which familiar does the work

<!-- Subject `orchestration`, mythic name the Loom. The folder names the subject
     (R1e); the name is the rendering. Falsified when WHO DOES THE WORK changes
     -- which familiar, model, tools and permissions a task is given, and how
     work is split, dispatched and rejoined. Plan: `../../dev/orchestration/`. -->

Definitions live here, one `<name>.md` per agent.

Definitions live here, one `<name>.md` per agent. They are **not injected into
any harness prompt** — same rule as skills, for the same reason: injection cost
is O(roster), routing cost is O(1). Reach them through the wrapper.

```
pi-agent --list                 # the roster: name + one-line description
pi-agent -l -v                  # + model and toolset
pi-agent <name> "<task>"        # run one; --cwd, --timeout, --model, --session
```

`pi-agent` is `engine/harness/pi-agent`; the dotfiles hold only a symlink to it, so it stays on `PATH`.
The roster's directory is `roots.SUBAGENTS` in `../../engine/lib/roots.py`.
Parallel fan-out is shell `&` + `wait`; there is no orchestrator.

## The roster

`pi-agent --list` is the live answer — it reads this directory, so it cannot go
stale. The rows below exist so the tree's own link check can reach each leaf;
adding a definition without a row reports as an orphan (`familiar context links
--check`), which is the reminder, not a second source of truth.

| agent | for |
|---|---|
| `bash.md` | exact commands on the 4B; verified stdout only |
| `explore.md` | cited recon across files on the 30B |

## When delegation is worth it

**Only when the child discards far more than it returns.** The parent pays the
returned summary; the child pays its own floor (1,001 bytes bash-only, 3,425
read-only, measured 2026-09-06) plus everything it reads. Recon across many
files wins. A single mechanical command does not — the parent already has
`bash`, and delegating it buys a second model load to save a few hundred bytes.

## Writing a definition

Frontmatter `name`, `description`, `model`, `tools`; body is the system prompt.

| key | what it decides |
|---|---|
| `tools` | **the cost lever.** The narrowest set that does the job — this, not the prose, is why the bash worker costs 1KB and the explorer 3.4KB |
| `model` | `provider/id`, e.g. `ollama/qwen3:4b-instruct-2507-q4_K_M`. Mechanical work → 4B; anything the parent quotes verbatim → 30B |
| `description` | what the caller matches on. One clause of what it does, one of what it must NOT be used for |

Body rules that earn their place: report only verified output, quote paths and
line numbers, never assert absence without a real `find`/`ls`, say "not handed
that" instead of reconstructing. A small model confabulates under pressure to
answer, and the parent cannot see what the child saw.

## How the child is spawned, and why it is cheap

`pi -p <task> --system-prompt <body> -nc -ns --tools <allowlist> [--model M]`.

| flag | why |
|---|---|
| `--system-prompt` | **replaces** the prompt. `--append-system-prompt` stacks on top of `~/.pi/agent/SYSTEM.md`, which is how `@mjakl/pi-subagent` reached 15,758 bytes per child (removed 2026-09-06) |
| `-nc` | no `AGENTS.md`/`CLAUDE.md` discovery — the child is not working on the project, it is answering one question |
| `-ns` | no skills index |
| extensions **kept** | they cost 0 prompt bytes (measured) and carry `@gotgenes/pi-permission-system`; a bash-capable child with no boundary enforcement is the wrong trade |

Pi has no native subagents by design (`pi/docs/usage.md:309` — "use external
tools"), and no per-agent base-prompt override exists, so the wrapper is the
mechanism, not a workaround for a missing setting.
