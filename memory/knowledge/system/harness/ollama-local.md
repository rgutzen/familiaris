---
title: ollama local
summary: Local-model work on the 890M iGPU — models, VRAM, what actually runs
origin: derived             # promoted from a .lore.md store (D2->D3)
authority: agent
trust: trusted
last_verified: 2026-08-29
use_count: 5
last_used: 2026-10-12
promoted_from: []
source:
supersedes:
related: [memory-architecture, journal-index, context-budget]
tags: [ollama, gpu, vram, local-llm]
scope: []
area: [B]
stability: evolving         # mixed rates: the hardware facts are stable, the price table is volatile
verified_log: [2026-08-29]
---

# ollama local

Local LLM inference on this machine — no discrete GPU; AMD Ryzen AI 9 HX 370,
Radeon 890M iGPU, 61 GB RAM. Local models are slow; prefer small models and
trimmed toolsets.

## Hardware reality

- Vulkan (llama.cpp) on the 890M: ~146 t/s prompt, ~9.9 t/s generation.
  ROCm (gfx1150) is slower for generation (~4.8 t/s) even though faster for
  prompt (~207 t/s). Use Vulkan.
- ROCm/HIP on gfx1150 is ~60% slower than Vulkan overall: pp512 370 vs 150
tok/s, tg128 23 vs 18 (lemonade-sdk/llamacpp-rocm#57, ROCm 7.2). AMD's GPU/OS
matrix (ROCm 7.14) excludes gfx1150; hipMalloc allocates dedicated VRAM only
(~48GB) → 94 graph splits + 400ms sched_reserve delays, while Vulkan's
HOST_VISIBLE_BIT spans VRAM+GTT (~88GB). LM Studio's ROCm engine logs
'No compatible ROCm GPUs found' then silently falls back to Vulkan — silent
degradation, not a hard error. Fix: Vulkan (default); Ollama with
OLLAMA_IGPU_ENABLE=1; BIOS UMA frame buffer = Fixed, not Dynamic (#11451).
- Memory bandwidth (~90 GB/s) is the bottleneck; 64GB RAM handles ~30B Q4_K_M,
  96GB for 70B. Set BIOS iGPU memory to minimum and use Variable Graphics
  Memory (VGM) up to ~75% of system RAM.

## Security

Ollama port 11434 must be exposed only within the Tailscale mesh, never bound
to 0.0.0.0 or public. This applies to all local LLM inference services.

## Model tiers by VRAM (mid-2026, EUR)

| VRAM | Model | Notes |
|---|---|---|
| 24 GB | Qwen2.5-Coder 32B Q4_K_M (~20 GB) | used RTX 3090 (€800–1k), replace thermal pads |
| 48 GB | Qwen3-Coder-Next 80B/3B MoE Q4_K_M | dual 3090 (€1.6–2k) or RTX 5090 |
| 128 GB unified | 70B Q4 / 123B Q4 | Strix Halo laptop (~€3.3k) or DGX Spark |
| 192 GB+ | DeepSeek V3 671B IQ2_XXS | Mac M4 Ultra (~€7k) |

Used 3090 prices rising (+36% over 180 days). No >24GB consumer GPU under
€1.5k new in the next 12–18 months.

## Embeddings (M4 journal index)

`nomic-embed-text` is the default for `familiar knowledge journal index`
([[journal-index]]) — small (~137M params),
CPU-friendly, no VRAM pressure. Pull it once: `ollama pull nomic-embed-text`.
Override with `PAZRAS_EMBED_MODEL` if a different embedding model is
preferred; the index auto-rebuilds fully if the recorded model changes.
Calls go to `127.0.0.1:11434` by default (override `PAZRAS_OLLAMA_URL`) —
consistent with the Security rule above, since this is a local loopback call,
never the Tailscale-exposed address.

## Traps

- llama.cpp Vulkan MoE full-GPU offload (`-ngl 99`) on gfx1150 can corrupt output
  (Gemma-4-26B-A4B; temp-0 byte-identical loops/garbled prefix, fused MMVQ decode
  kernel; #27007, same class #24311/#25777). `--n-cpu-moe 99` is byte-correct
  ~19 t/s (vs ~38 full-GPU); `GGML_VK_DISABLE_MMVQ=1` removes loops. mmproj/vision
  balloon GTT ~33 GB → system OOM (#27146). Temp-0 smoke-test QAT/MoE GGUFs.
- Qwen3.5/3.6/3.8 use Gated DeltaNet (GDN) hybrid linear attention and inherit
  the OPEN llama.cpp Vulkan decode collapse (~4 t/s RADV; no fix since Aug
  2026). HF reuses `qwen3_5` for 3.6/3.8, so model_type cannot tell them apart.
  Interactive gfx1150 use must stay pre-Qwen3.5 standard attention:
  Qwen3-30B-A3B-Thinking-2507, Qwen3-Coder-30B-A3B, Qwen3-32B, QwQ-32B, R1
  distills. Qwen3.8-27B is headless CPU-only (~2–4 t/s).
- Measured Vulkan lineup (Ryzen AI 9 HX 370 / 890M / 64GB, Q4_K_M unless noted):
  Qwen3-1.7B (1.1GB, ~60–100) autocomplete; Qwen3-8B (5GB, ~20–25) daily driver;
  Qwen3-30B-A3B-Thinking-2507 (18.56GB, ~20–25) reasoning daily driver;
  Qwen3-Coder-30B-A3B coding twin; DeepSeek-R1-Distill-Qwen-14B (8.99GB,
  ~10–14) lightweight fallback; gemma-4-12b-it QAT (6.72GB, ~10–14) with MMVQ
  caveat. Headless overnight: Qwen3.8-27B UD-Q4_K_M (16.46GB) CPU ~2–4. Exclude
  interactive: all Qwen3.5/3.6/3.8 and Gemma-4-26B-A4B full-GPU. Speed anchors:
  7–8B ≈20–25, 14B ≈10–14, dense 27–32B ≈5–8, 70B ≈2–4 tok/s.
- AMD XDNA2 NPU (~50 TOPS) inference is nascent (Aug 2026): only AMD's own
  stack works — ROCm/FastFlowLM + lemonade-sdk/lemonade (hybrid NPU+iGPU), plus
  ONNX Runtime GenAI with Quark quantization. No upstream llama.cpp/Ollama/vLLM/
  LM Studio NPU path on Linux. Kernel 6.6+ amdxdna, /dev/accel/accel0, NPU FW
  1.1.2.64. Measured: Qwen3-0.6B ≈94 tok/s, Llama-3.2-1B ≈62, Qwen3.5-2B ≈26→17
  (32k), Qwen3-8B ≈11. Verdict: experiment only.
- Used RTX 3090: replace thermal pads (junction 100–110°C → 78–88°C) and
  VRAM-stress with a 20+ min 30B+ LLM load — gaming benchmarks miss weak banks.
- NVLink on consumer GeForce does **not** pool VRAM; use `--tensor-split`.
- ROCm on RDNA3 silently falls back bf16→FP32 on many operators.
- DeepSeek V4 Flash needs a custom llama.cpp fork (antirez ds4) or vLLM ≥0.7.0.
