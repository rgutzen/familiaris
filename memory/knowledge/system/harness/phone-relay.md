---
title: The phone relay — agent sessions supervised from Telegram
summary: familiar relay: one Telegram poller, a socket sessions ask through, layers, presence, traps
origin: authored
authority: agent
trust: trial
last_verified: 2026-10-21
verified_log: [2026-10-21]
use_count: 2
last_used: 2026-10-21
promoted_from: []
source: 06_SYSTEM/dev/remote/SPECS.md
supersedes:
related: [scheduled-sessions, pi, boundaries, delegation-and-asks]
tags: [relay, telegram, phone, permissions, supervision, presence, audit]
triggers: [phone relay, telegram, answer from the phone, away, permission ask on the phone, ask_user, familiar relay, relay down]
scope: ["06_SYSTEM/engine/relay/**", "06_SYSTEM/config/relay/**"]
area: [B]
stability: evolving
---

# The phone relay — agent sessions supervised from Telegram

`familiar relay` lets the user answer an agent session's questions and
permission asks from the phone. It exists because an unattended session stalls
the moment it needs the user. The plan and the user's five decisions are
`dev/remote/PLAN.md`; the measured end-to-end runs are
`dev/remote/2026-10-21-phase1.md` (scheduled) and `…-phase2.md` (interactive).

```
familiar relay serve | status [--check] | pair | pause | resume | notify | ask | withdraw
```

## Shape

```
phone <-> Telegram <-> familiar-relay.service   (the ONLY getUpdates poller)
                         ^ $XDG_RUNTIME_DIR/familiar-relay.sock (mode 600), JSON lines
          +--------------+--------------------------+
  scheduled run: `pi --mode rpc`;            interactive pi: the familiar-remote
  each dialog becomes a relay ask            extension races each dialog between
  (engine/schedule/rpc.py)                   terminal and phone while the user is away
```

- **Socket verbs:** `ask` (blocks until answered), `withdraw`, `notify`,
  `status`, `pause`, `resume`. **No verb produces an answer:** answers come only
  from the paired owner's Telegram updates.
- **An ask waits indefinitely** (decision 3). Its id is its identity: a client
  that reconnects after a relay restart with the same id gets the same ask, not
  a second message. Open asks persist in `<data>/relay/pending.json`.
- **`notify` degrades:** with no relay, the client fails at once; the caller has
  already written its own record (the scheduler's `notified` event).
- **The unit** is `familiar-relay.service`, stowed from the dotfiles' `systemd`
  package, `Restart=always`. Config: `config/relay/relay.yaml`; the token lives
  in `~/.config/pazras/relay.env` (mode 600, on the no-read list).

## Security layers (none costs a tap, decision 2)

| Layer | Against |
|---|---|
| owner pairing (`familiar relay pair`, `/pair <code>`), every other chat ignored and audited | a stranger finding the bot |
| the token file mode 600 and unreadable to agents | an agent using the token |
| a nonce per ask in the button data; stale, duplicate or foreign taps refused | a replayed tap |
| secrets redacted before sending and in the audit | a key reaching Telegram |
| `redact_after_answer`: the message closes as `[session] rule · answer · time` | a chat history of commands |
| `audit.jsonl`, append-only: ask, sent, answer, withdraw, stale, foreign, pair, notify | not knowing what was approved |
| `/pause` (phone) or `familiar relay pause` (local) | a lost phone |
| Telegram's two-step verification | account takeover |

## Presence (interactive sessions)

The user is away after `away_after` (600 s) without terminal input, while
`hyprlock` runs, or after `/away` from the phone until the next keystroke. While
away, each dialog is sent to the phone as well as shown at the terminal, and the
first answer wins; typing at the terminal withdraws the phone message. A turn
end becomes an `input` ask, and a reply to it is injected as the next
instruction.

## Traps measured, to carry

1. **One poller per bot token** (Telegram answers a second with HTTP 409). Never
   start a second relay, and never test against the real bot while one runs.
2. **`pi -p` cannot be supervised:** every permission ask fails for want of a
   UI. A scheduled run drives `pi --mode rpc`.
3. **The permission prompt draws with `ui.custom` in a terminal**, so it cannot
   be raced. Interactive permission asks go through the `familiar-remote` chain
   link, and the package caps a link's `allow` on `path`/`external_directory`
   to `defer`: such an ask approved on the phone becomes a terminal dialog
   (measured in R3c). **The phone still shows it closed as "Yes".**
4. **Only the directive folders ask for a path** on this machine
   (`"*": "allow"`); a write elsewhere, even outside the repository, raises no
   ask at all.
5. **Telegram's IPv6 route drops connects** (2 of 6, 2026-10-21) while IPv4
   answers. urllib spent its 30 s timeout per address, so asks arrived 31 s
   late; the relay now gives each address 3 s (`CONNECT_TIMEOUT`).
6. **The `ask_user` tool must be registered once:** with the dotfiles' loader
   shim installed, a scheduled run's `-e` of the same file made pi refuse to
   start; the run passes `-e` only when pi would not discover the tool.
7. **A session started before the shims were installed has no phone channel.**
   Extensions load at session start.
8. **A local `relay resume` cannot tell the user from an agent** on the same
   account; a boundaries rule against agents resuming is proposed, not built.
9. **The first long poll returns after `poll_timeout` (50 s)**, so `status`
   reads "last ok never" for up to a minute after a start.

## Verification

```bash
engine/familiar relay status --check            # running, paired, polled recently
python3 -m pytest engine/relay/tests -q
node engine/relay/pi-remote/test-remote.mjs     # the extension's pure parts
```
