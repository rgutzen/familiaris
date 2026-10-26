---
title: Voice
summary: Two local speech services — text in, text out — the `say` client, and the numbers they run at
origin: authored
authority: agent
trust: trusted
last_verified: 2026-10-25
verified_log: [2026-10-25]
use_count: 0
last_used:
promoted_from: []
source: file:~/.local/lib/voice-tts/voice-tts.py
supersedes:
superseded_by: []
contradicts: []
related: [pi, ollama-local, phone-relay, herdr-cli]
tags: [voice, tts, stt, kokoro, systemd, stow]
triggers: [tts, text-to-speech, say, kokoro, voice output, speak, speech, speech speed, piper, voice-tts, voice-stt, dictation, spoken reply, read aloud, audio, microphone]
scope: []
area: [B]
stability: evolving
---

# Voice

Two services, one direction each, both **local, CPU-only, and reachable only on
this machine or the home LAN**. Neither is a cloud fallback: no request leaves
the box.

| Direction | Service | Port | Bind | Model | Unit |
|---|---|---|---|---|---|
| in | `voice-stt.py` | 8000 | `0.0.0.0` (phone) | faster-whisper `large-v3-turbo` int8 | `voice-stt.service` |
| out | `voice-tts.py` | 8001 | `127.0.0.1` | Kokoro-82M ONNX, 54 voices | `voice-tts.service` |

Both speak the OpenAI audio contract (`POST /v1/audio/transcriptions`,
`POST /v1/audio/speech`, `GET /v1/models`) behind `Authorization: Bearer` with a
file-sourced token. The STT half is a prototype (`06_SYSTEM/dev/capture/`); the
TTS half is deployed from dotfiles.

## Layout

```
~/.local/lib/voice-tts/voice-tts.py        server (stdlib http.server, no framework)
~/.local/bin/say                            client: markdown stripping, sentence streaming
~/.local/bin/speak-selection                selection bind: speak, or stop what is speaking
~/.local/bin/voice-record                   dictation bind: stop, then `voxtype record toggle`
~/.config/voice-tts/config                  url, voice, speed, preroll — stowed, non-sensitive
~/.config/pazras/voice-tts.env              VOICE_TTS_TOKEN, mode 600 — never in git
~/.local/share/voice-tts/{venv,models}      kokoro-onnx + 338 MB of weights
dotfiles/shared/voice-tts/                  the stow package (config, unit, scripts)
dotfiles/shared/wireplumber/…               keeps a Bluetooth sink awake for 30 s
```

Nothing under `~/02_AREAS/B_Tech/tts/` is runtime: that directory holds the
shootout that chose the model (`shootout/results.md`).

## Using it

```bash
say "The tests pass and the diff is small."
cat note.md | say                 # code fences, tables, links and URLs are dropped
say --file journal.md             # long-form
say -c                            # clipboard
say --voices                      # the 54 Kokoro ids
say --speed 1.4 "One-off faster."  # overrides the config
say --out /tmp/x.wav --no-play    # file, no playback
say --stop                        # silence a run; exit 1 if nothing was playing
```

Two bindings drive it (`wayland/hypr/bindings.lua`):

| Key | Runs | Does |
|---|---|---|
| `SUPER ALT L` | `speak-selection` | speaks the selection — primary, or the clipboard when the app publishes none; the same key stops playback |
| `SUPER SHIFT L` | `voice-record` | stops playback, then toggles dictation |

Stopping first is not politeness: a microphone that records the voice it is
replacing transcribes the machine.

Defaults come from `~/.config/voice-tts/config` (`voice = af_heart`,
`speed = 1.2`). Speed is a time-stretch of the same waveform, so raising it costs
nothing in synthesis: 1.0 reads as recorded, 1.2 exists because 1.0 loses a
listener's attention before it loses intelligibility — and a long reply at 1.0 is
a trap. `VOICE_TTS_URL`, `VOICE_TTS_VOICE` and `VOICE_TTS_SPEED` free variables
win over the file; flags win over both.

Raw HTTP, for any OpenAI SDK client:

```bash
curl -s localhost:8001/v1/audio/speech -H "Authorization: Bearer $VOICE_TTS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"input":"Hello.","voice":"af_heart","response_format":"wav"}' -o hello.wav
```

## Measured on this machine (Ryzen AI 9 HX 370, CPU only)

| Fact | Number |
|---|---|
| Kokoro-82M throughput | 4.1x realtime (RTF 0.245), flat from 13 to 807 chars |
| first word of a sentence | 470–720 ms end to end through HTTP |
| steady-state latency | bounded by how long the listener listens, not by synthesis |
| core cost | **one core**; pinned 1 vs 24 CPUs: 4.64x vs 4.38x — the model is serial-bound |
| resident memory | 713 MB (ONNX arena, not returned to the OS) |
| alternatives rejected | Piper 41x but flat prosody · Supertonic-3 no streaming API · Pocket 4.1x + clones, kept as the fallback if a cloned voice is ever wanted |

The sentence, not the utterance, is the unit of latency. `say` splits, requests
in order on a thread, and plays as each arrives, so the second sentence is
synthesised while the first is still in the ears.

## Traps

- **`:8000` is taken by the STT service.** TTS sits on `:8001`; anything bound
  to 8000 that is not `voice-stt` is a conflict.
- **The token is not in the config.** `~/.config/voice-tts/config` is stowed and
  public; `VOICE_TTS_TOKEN` lives in `~/.config/pazras/voice-tts.env` (600).
  `say` reads both.
- **Bind is `127.0.0.1`.** The STT service exposes itself because a phone asks
  it; nothing asks TTS over LAN yet. Change `--host` in the unit when something
  does.
- **The first sound after a quiet spell loses its opening.** The A2DP transport
  is closed when the bluez node suspends, and the headset needs a restart that
  swallows the first fraction of a second. Three levers, in order: WirePlumber
  keeps a Bluetooth sink for 30 s after playback (`shared/wireplumber`), `say`
  wakes the sink *before* synthesising so the wake hides behind the service's
  ~0.5 s, and a cold first sentence is padded with `preroll` (default 300 ms).
  Playback wall time equals audio duration either way — the graph consumes the
  samples it loses, so nothing in PipeWire reports the loss; only an ear does.
- **`pw-cat` needs `--raw`.** Without it, `-` is parsed as a filename through
  libsndfile and playback fails with "Format not recognised".
- **The selection bind reads primary first, the clipboard second.** Toolkits
  differ: a terminal with copy-on-select publishes a primary selection, while
  several apps set only the clipboard. There is no freshness signal, so a
  primary selection set once keeps winning until another client takes it —
  if the wrong text is spoken, copy something new.
- **Spoken form is not written form.** `say` strips code fences, table rows,
  links and URLs, and turns em dashes into pauses, but it will still read a file
  path or an identifier literally. Text meant for the ear has to be written for
  the ear — see `dev/voice-out/PLAN.md`.
- **Kokoro voice ids encode language** in the first letter (`af_*` en-US,
  `bm_*` en-GB, `jf_*` ja, `zf_*` cmn …); `say` and the server derive `lang`
  from it.

## The phone

GrapheneOS with no Play services, so the engine is a sideloaded app with no
network in the synthesis path: **HayaiTTS** (GPL-3.0, sherpa-onnx, universal APK
from its GitHub releases), set as *Settings → System → Languages & input →
Text-to-speech output*.

| Piece | Value |
|---|---|
| model | `kokoro-multi-lang-v1_0` — same family as this machine |
| speaker | `af_heart` (id 3) — same voice |
| speed | Studio `1.2` **×** the system speech-rate slider; they multiply, so leave the slider at 1.0 |
| clamp | 2000 characters per request (`HayaiTtsService.MAX_TEXT_LENGTH`), silently truncated |

Three ways text reaches the ear, with one trap each:

| Route | Speaks with | Trap |
|---|---|---|
| an app's own read-aloud, through the system engine | `af_heart` | the app must have one |
| text selection → *Speak with HayaiTTS* | **Piper Amy** | `SpeakSelectionActivity` hard-codes `en_US-amy-low`; the voice choice is ignored |
| Termux `~/bin/psay` | `af_heart` | needs Termux plus the Termux:API app |

`psay` is the phone's `say`: strips markdown, splits sentences, chunks below the
clamp, one engine call per sentence. Source:
`02_AREAS/B_Tech/tts/phone-ref/psay`.

```bash
psay "text"                       # argument
cat note.md | psay                # a file
termux-clipboard-get | psay       # the SUPER+ALT+L of this phone
```

No stop exists: `termux-tts-speak` blocks until the utterance finishes and
killing the script does not reliably silence the engine.

## What is not built

Invocation from chat, from a screen selection, and from the phone. Design and
open questions: `06_SYSTEM/dev/voice-out/PLAN.md`.
