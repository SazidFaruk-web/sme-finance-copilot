# Overnight log: local LLM optimization (branch `model-tuning`)

_Summary goes here when the run is finished._

Hardware: AMD RX 9060 XT 16 GB (Vulkan, llama.cpp build 10930), Ryzen 7 3700X, 16 GB DDR4-3200, Windows 10.
One llama-server on the GPU at a time. Golden set = `sme_copilot/benchmarks/golden.yaml` (48 scenarios: 26 English,
11 Bangla, 11 Banglish), scored against ground truth computed by the app's deterministic tools on a fresh seeded DB.

## Log

### 0. State before the overnight run (commit f31a00d)
- Baseline (Qwen3.8 27B IQ4_XS, `-ngl 999 -c 32768`, defaults): 9.3 tok/s generation, 159 tok/s prompt,
  24.7 s to first tool call, VRAM full (14.8 GB) with spill; ~130 s per chat answer in the UI.
- Found: flash attention on this Vulkan build cuts server prompt speed ~3x (470 vs 1330 tok/s) -> `-fa off`.
- Found and fixed: emulated tool calling sent two system messages (Qwen3.5 template rejects with HTTP 500, so the
  app silently fell back to rules-offline); benchmark financing metric required the catalog's "(scheme-type)" suffix.
- Golden set so far (emulated tools unless noted, `-fa off -c 16384 --reasoning off`):

| model | median latency | tool success | numeric | hallucination | language | financing |
|---|---|---|---|---|---|---|
| Qwen3.5 9B Q5_K_M (native tools) | 8.2 s | 77% | 68% | 15% | 91% | 1/3 |
| Qwen3-14B Q4_K_M | 18.6 s | 91% | 86% | 2% | 77% | 3/3 |

### 1. Phase 1 setup (20:40-20:50)
- Branch `model-tuning` created; checkpoint commit f31a00d (fallback badge, prompt trim, template fix, harness).
- Candidates found on Hugging Face (all ungated, Apache-2.0 / IBM / OpenAI open licences):
  - `unsloth/gemma-4-12b-it-GGUF` Q4_K_M (7.12 GB) + MTP draft head `ggml-org/gemma-4-12B-it-GGUF`
    `mtp-gemma-4-12B-it-Q8_0.gguf` (0.47 GB); llama-server supports `--spec-type draft-mtp`.
  - `ibm-granite/granite-4.2-8b-GGUF` Q5_K_M (6.25 GB), the newest 8B (4.2).
  - `ggml-org/gpt-oss-20b-GGUF` MXFP4 (12.11 GB) + EAGLE3 draft (0.92 GB); `--spec-type draft-eagle3`.
- D: free 117 GB before downloads. Downloading sequentially with resume (curl -C - and 6 attempts each).
- Built `scripts/eval_local_model.py`: golden set against one GGUF on a private port with per-process peak VRAM;
  writes `benchmarks/results/golden/<label>/` and one line per run in `benchmarks/results/golden_summary.jsonl`.
- Phase 2 groundwork committed (537c84e): static system prompt (per-request context moved to the user turn so
  the system+tools prefix stays cached), optional grammar-constrained tool envelope, per-profile request params.

### 2. Qwen golden runs recorded (20:10-20:51, old prompt code)
| run | median latency | tool success | numeric | hallucination | BN/Banglish language | financing |
|---|---|---|---|---|---|---|
| Qwen3.5 9B emulated (1st) | 7.5 s | 77% | 82% | 10% | 64% | 2/3 (rescored) |
| Qwen3.5 9B emulated + language reminder | 8.5 s | 72% | 82% | 21% | 68% | 2/3 (rescored) |
| Qwen3.5 9B native | 8.2 s | 77% | 68% | 15% | 91% | 1/3 (rescored) |
| Qwen3-14B emulated | 18.6 s | 91% | 86% | 2% | 77% | 3/3 (rescored) |
- The 2nd 9B run overlapped with a hung pytest that also hit the server (2 timeouts), so treat it as noisy.
- Most misses on every model are Banglish (answers in Bengali script, misread words like "gato mash").
- Re-running all Qwens under the current code (static prompt) in the GPU queue for a fair Phase 1 ranking.

### 3. Prompt cache check (20:55)
- Static system prompt works: a new question computes only 18-20 new prompt tokens (~130 ms) on the 14B;
  system + tool list come from llama.cpp's cache.
- The remaining big cost is tool output: one forecast result was 3,076 tokens (16 s of prompt processing on
  the 14B). Added a recursive abridger (drops URLs, cost bands, checklists) and a `TOOL_RESULT_BUDGET_CHARS`
  setting to A/B in Phase 2.

### 4. Phase 4 done early (no GPU needed), commit 6a7982e
- `scripts/make_fake_statements.py` writes 12 FAKE files (git-ignored `data/fake_statements/`) + expected.json
  computed with pandas. `scripts/check_fake_uploads.py` uploads each through `POST /api/data/upload` into its
  own fresh copy of the seeded DB and compares stored rows and in/out totals.
- Bugs found and fixed:
  - Empty file -> `IndexError` -> HTTP 500. Now 422 "the file is empty".
  - Header-only file said "could not find a date column. Columns seen: []". Now "no data rows found below the header row".
  - Missing amount column imported 0 rows silently (HTTP 200). Now 422 naming the missing column and the columns seen.
  - Binary garbage now gets "no recognisable table found: expected a header row such as Date, Description, Amount".
  - 60,000-row (3.1 MB) statement took 32 s; categorisation re-ran keyword matching for every row. Memoized: 14.6 s.
- Result: 12/12 pass. Clean CSV, XLSX, Bangla headers + Bangla digits + taka sign, mixed date formats, in-file
  duplicates (10 flagged and excluded), 3 MB file all match the pandas totals to the taka; >5 MB -> 413, PDF -> 415.
- Note: the app does not accept PDF or image statements (by design: CSV/TSV/TXT/XLSX only). Not changed.

### 5. Phase 3 language fix + Phase 2 prep (21:00-21:10)
- Language detection: "next 30 days এর cash flow forecast দেখাও" was classified English (23% Bengali letters).
  Added a word-level rule (>=2 Bengali-script words and >=20% of words => Bangla). JUDGMENT CALL: for mixed
  prompts I treat Bangla grammar words as the deciding signal, so the reply is in Bangla script. Commit 519d453.
- `sme_copilot/benchmarks/stress.yaml`: 44 stress prompts (English, Bangla, Banglish, mixed; Bangla digits, ৳,
  typos, 1-word and long prompts, no-data period, unknown customer, over-limit transfer). Validated in code:
  language detector agrees on 44/44, every ground-truth tool call succeeds and every number path resolves.
- Phase 2 experiment switches (off by default, so Phase 1 runs stay comparable): `PROMPT_VARIANT=finance`
  (Bangladesh glossary + tool map + Banglish example, static so it is cached), `TOOL_RESULT_BUDGET_CHARS`,
  constrained tool envelope (`constrained_tools` + `json_mode: json_schema`), `request_params`.

### 6. Fine-tuning ("train") feasibility: SKIPPED, by design
- Found: system Python 3.12 has `torch 2.12.0+rocm7.14` and sees the GPU (HIP 7.14). So GPU PyTorch works on
  this Windows box.
- Blockers for a LoRA on the models we would actually ship (12-14B):
  - bf16 weights alone are 24-28 GB, more than the 16 GB of VRAM.
  - 4-bit QLoRA needs bitsandbytes, which has no ROCm build for Windows.
  - The llama.cpp builds here have no `llama-finetune`.
- A LoRA would only fit a <=4B model, which is a weaker model than the one being tuned, so no gain for the app.
- Decision: rely on prompt, caching, constrained decoding and tool-output changes instead (Phase 2). If you want
  to try later: Linux + ROCm (or a rented CUDA GPU) with Unsloth QLoRA on the chosen model, then convert to GGUF
  with llama.cpp's `convert_lora_to_gguf.py` and load it via `--lora`.

### 7. Phase 1 golden runs, current code (all `-ngl 99 -c 16384 -fa off --reasoning off`)
| model (tools) | p50 latency | tool ok | valid args | numeric | financing | halluc. | BN/BL lang | VRAM |
|---|---|---|---|---|---|---|---|---|
| Qwen3-14B Q4_K_M (emulated) | 17.6 s | 88% | 95% | 86% | 3/3 | 8% | 86% | 13.1 GB |
| Qwen3-14B Q4_K_M (native) | 17.7 s | 84% | 91% | 79% | 2/3 | 6% | 91% | 13.1 GB |
- The static system prompt (language instruction now next to the user's text) lifted the 14B's Bangla/Banglish
  language match from 77% to 86% with emulated tools, with no other change.
- Downloads: gemma-4-12b Q4_K_M + MTP head done 21:14; granite-4.2-8b in progress.
| Qwen3.5-9B Q5_K_M (emulated) | 8.1 s | 77% | 79% | 71% | 3/3 | 19% | 86% | 6.8 GB |
| Qwen3.5-9B Q5_K_M (native) | 9.8 s | 74% | 84% | 79% | 2/3 | 12% | 77% | 6.8 GB |

### 8. Gemma 4 12B Q4_K_M: llama-server flags (speed harness, app prompt, 3 requests)
| flags | VRAM | prompt tok/s | gen tok/s | cold TTFT | cached TTFT |
|---|---|---|---|---|---|
| `-fa off` (Qwen's best) | 9.6 GB | 164 | 25.3 | 21.4 s | 11.8 s (cache NOT reused) |
| `-fa on -ctk q8_0 -ctv q8_0` | 7.7 GB | 214 | 29.0 | 16.5 s | 0.56 s |
| `-fa off` + MTP draft (`--spec-type draft-mtp -md mtp-...Q8_0.gguf`) | 10.6 GB | 166 | **46.1** | 21.2 s | 11.8 s |
- Opposite of Qwen3.5: Gemma (sliding-window attention) needs FA on, or the prompt cache is not reused.
- MTP speculative decoding: 1.8x generation speed.
- Gemma does NOT follow the emulated JSON tool format: it answers with its own `<|tool_call>call:get_digest{...}`
  syntax, so emulated mode cannot work without constrained decoding. Native mode is the natural fit.
- Stopped the queued FA-off Gemma golden run and requeued Gemma with `-fa on -ctk q8_0 -ctv q8_0` + MTP.
- With `-fa on -ctk q8_0 -ctv q8_0` + MTP together: 8.1 GB, 234 prompt tok/s, 38.3 gen tok/s, cold TTFT 17.2 s,
  cached 0.83 s. Used for the golden runs below.

| model (tools) | p50 latency | tool ok | valid args | numeric | financing | halluc. | BN/BL lang | VRAM |
|---|---|---|---|---|---|---|---|---|
| Gemma 4 12B Q4_K_M + MTP (native) | 12.2 s | 86% | 91% | **93%** | 2/3 | 6% | **95%** | 8.1 GB |
| Gemma 4 12B Q4_K_M + MTP (emulated) | 3.8 s | 9% | 12% | 14% | 0/3 | 4% | 95% | 8.1 GB |
- Gemma emulated is unusable as predicted (29/48 errors: it ignores the JSON format). Native is its mode.

### 9. Granite 4.2 8B Q5_K_M
- Speed (app prompt 4,306 tokens): `-fa off` 397 prompt tok/s, 36.9 gen tok/s, 10.4 GB, cold TTFT 11.4 s;
  `-fa on -ctk q8_0 -ctv q8_0` 435 / 40.3 tok/s, 7.1 GB, 10.4 s. Both reuse the prompt cache (~0.65 s).
| model (tools) | p50 latency | tool ok | valid args | numeric | financing | halluc. | BN/BL lang | VRAM |
|---|---|---|---|---|---|---|---|---|
| Granite 4.2 8B (native) | 15.0 s | 88% | 98% | 50% | 2/3 | **35%** | 100% | 10.5 GB |
| Granite 4.2 8B (emulated) | 15.0 s | 65% | 74% | 54% | 2/3 | 27% | 91% | 10.4 GB |
- Rejected: good tool selection but it rewrites/invents figures (35% of answers contain numbers that are in no
  tool result), which is disqualifying for a finance app.
- All downloads finished 22:34 (gemma, MTP head, granite, gpt-oss-20b MXFP4 12.1 GB, EAGLE3 draft). D: 92 GB free.

### 10. gpt-oss-20b MXFP4 (`-ngl 99 -c 16384`, reasoning_effort=low)
- Loads fully on the GPU (11.4 GB) with 16k context. Speed: 288 prompt tok/s, **72 gen tok/s** (MoE, ~3.6B
  active), cold TTFT 10.3 s, cached 1.1 s, compact prompt (2,641 tokens in its harmony format).
- EAGLE3 draft (`--spec-type draft-eagle3`) made it slower (47 tok/s) and used more memory: dropped.
- Golden (native): p50 **6.9 s**, tool 84%, valid args 95%, numeric 71%, financing 3/3, **hallucination 40%**,
  BN/BL language 82%. Rejected for the same reason as Granite.

### 11. Phase 1 decision: top 2
Ranked by accuracy first (numeric accuracy, hallucination rate, tool success), then speed:
| # | model (mode) | numeric | halluc. | tool ok | BN/BL lang | p50 | VRAM |
|---|---|---|---|---|---|---|---|
| 1 | **Gemma 4 12B Q4_K_M + MTP (native)** | **93%** | **6%** | 86% | **95%** | 12.2 s | 8.1 GB |
| 2 | **Qwen3-14B Q4_K_M (emulated)** | 86% | 8% | **88%** | 86% | 17.6 s | 13.1 GB |
| 3 | Qwen3.5-9B Q5_K_M (native) | 79% | 12% | 74% | 77% | 9.8 s | 6.8 GB |
| 4 | gpt-oss-20b MXFP4 (native) | 71% | 40% | 84% | 82% | 6.9 s | 11.5 GB |
| 5 | Granite 4.2 8B Q5_K_M (native) | 50% | 35% | 88% | 100% | 15.0 s | 10.5 GB |
- **Default: Gemma 4 12B** (best numbers, fewest hallucinations, best Bangla/Banglish, faster than the 14B, and
  only 8 GB of VRAM).
- **Backup: Qwen3-14B** (next-best accuracy, best tool selection, different family; slower).
- The fast-but-wrong models (gpt-oss, Granite) are not offered as a "fast" option: wrong figures are worse than
  slow figures in a finance app. If speed matters more than accuracy, Qwen3.5-9B is the honest fast choice.
