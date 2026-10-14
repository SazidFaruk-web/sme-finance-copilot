# SME Finance Copilot

**An AI finance copilot for Bangladesh small and medium businesses.** Built for the 2026 Shenzhen International
FinTech Competition (FinTechathon), International Track, **Topic E: SME Finance Copilot**.

Small shops, garment subcontractors, traders, food businesses and freelancers can upload their sales ledgers,
bank statements and bKash/Nagad/Rocket statements, or simply type *"dokan bhara 15000 dilam"*. The copilot then:

- **analyses the business**: margins, break-even, receivables and payables aging, cost drivers, Eid and
  Pohela Boishakh seasonality, and why the numbers changed;
- **manages cash flow**: 30/60/90-day forecast with an uncertainty band, what-if simulation, and proactive alerts
  for low balance, overdue invoices, rent/salary/EMI/VAT dates and unusual spending;
- **matches financing**: bank, CMSME refinance-scheme, MFI, MFS nano-loan, supplier credit, invoice financing
  and leasing options, evaluated on the business's real numbers (DSCR, revenue stability, age, documents,
  collateral), with EMI and total cost of credit and a plain-language reason for every match and rejection;
- **gets work done**: payment reminders, Bangla/English follow-up letters, a loan-readiness PDF, an
  application checklist, and **sandbox** payments that need the owner's explicit confirmation. Every action
  lands in a hash-chained operation log.

It works in **English, বাংলা and Banglish**, and replies in the language you write in. Every number comes
from deterministic, tested code and can be traced back to the source rows.

> Decision support only, not licensed financial advice. Financing data in this repository is **illustrative**
> and must be verified with each lender. Money moves only inside a simulated sandbox account.

---

## Quick start (offline, no API keys)

Requires Python 3.11+.

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt        # Windows  (Linux/macOS: .venv/bin/pip)
.venv/Scripts/python -m sme_copilot.cli demo              # reset + seed demo data + serve
```

Open <http://127.0.0.1:8000>. Set `APP_ENV=demo` (or copy `.env.example` to `.env`) to have the demo logins
shown on the login page.

| User | Role | Password (demo) | Can do |
|---|---|---|---|
| `nusrat` | owner | `owner-demo-2026` | everything incl. confirming sandbox payments (Tier 0-2) |
| `rafiq` | accountant | `accountant-demo-2026` | analysis, data entry, drafts, reminders, reports (Tier 0-1) |
| `mitu` | viewer | `viewer-demo-2026` | read-only analysis (Tier 0) |

The default model is cloud Claude (`default_profile` in `config/providers.yaml`; set `ANTHROPIC_API_KEY`).
Without a key, the offline `rules-offline` engine answers instead: a deterministic engine that implements the
same provider interface, so the whole product (tool calling and every security control) runs without network
or GPU. Each such reply is labelled as a fallback in the UI. For a private model on your own GPU, see
[Local model](#local-model-private-on-your-gpu).

### Docker (one command)

```bash
docker compose up --build                          # demo on :8000, offline rules engine
docker compose --profile local-llm up --build      # + Ollama with a local 7B model (nothing leaves the machine)
```

With the `local-llm` profile, choose **Local Qwen2.5 7B (Ollama)** in the model dropdown, or set
`LLM_PROFILE=local-qwen7b` and `LOCAL_ONLY_MODE=true` in `.env`. `make demo`, `make test`, `make bench` and
similar targets are in the `Makefile`.

### Deployment

The app is one stateless container plus a data volume (SQLite by default; set `DATABASE_URL` for Postgres).

1. Build and push the image to any container host (Render, Railway, Fly.io, Azure Container Apps, or a VM with Docker).
2. Set `APP_ENV=production`, a real `FIELD_ENCRYPTION_KEY`, and `CORS_ORIGINS=https://your-domain`. In
   production the demo credentials are never shown and the API docs are disabled.
3. Put it behind HTTPS (the platform's TLS or a reverse proxy). HSTS is sent automatically over HTTPS.
4. For a demo deployment, run `python -m sme_copilot.cli seed --reset` once, or use the compose `demo` command.

**Deployment link:** _add the public URL here after deploying._

---

## Environment variables

Secrets come **only** from the environment (`.env` is git-ignored). See [.env.example](.env.example).

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `dev` | `dev` / `demo` (shows demo logins) / `production` (requires encryption key, hides API docs) |
| `FIELD_ENCRYPTION_KEY` | auto dev key | Fernet key for encrypting account numbers, phones, TIN and trade licence at rest |
| `LLM_PROFILE` | – | Overrides `default_profile` in `config/providers.yaml` on this machine |
| `TOOL_RESULT_BUDGET_CHARS` | 5000 | Max size of one tool result as the model sees it (the UI keeps the full data) |
| `PROMPT_VARIANT` | `finance` | `finance` adds a Bangladesh money glossary, a tool map and a Banglish example; `base` leaves it out |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY` | – | Enable the matching cloud profiles |
| `OLLAMA_BASE_URL` | – | Override the Ollama URL (set automatically in docker-compose) |
| `MASK_PII` | `true` | Mask phones, accounts, NID, TIN, emails and cards before any **external** model call |
| `LOCAL_ONLY_MODE` | `false` | Refuse every external model; nothing leaves the machine |
| `SANDBOX_PER_TXN_LIMIT` / `SANDBOX_DAILY_CAP` | 200000 / 500000 | Sandbox money limits (BDT), enforced in code |
| `CONFIRMATION_TTL_MINUTES` | 10 | How long a money request waits for confirmation |
| `SESSION_TTL_MINUTES` | 240 | Login session lifetime |
| `RATE_LIMIT_PER_MINUTE` / `LOGIN_RATE_LIMIT_PER_MINUTE` | 120 / 10 | Per-IP rate limits |
| `CORS_ORIGINS` | localhost | Allowed browser origins |
| `AS_OF_DATE` | today (Asia/Dhaka) | Pin "today" for reproducible demos and benchmarks |
| `DIGEST_SCHEDULER` | `false` | Refresh every business's alerts hourly in the background |
| `DEMO_OWNER_PASSWORD` etc. | see `.env.example` | Passwords for the seeded demo users |

---

## Switching models (no code changes)

All profiles live in [config/providers.yaml](config/providers.yaml). The adapters are Anthropic (Claude), OpenAI,
Google Gemini, any OpenAI-compatible endpoint (OpenRouter, Groq, DeepSeek, Together, vLLM, llama.cpp) and Ollama,
plus the offline `rules` engine.

You can switch the model in four ways:

- **globally**: set `LLM_PROFILE=claude-sonnet` (or any profile name) in `.env`;
- **live, per request**: use the **Model** dropdown in the top bar. Unavailable profiles are greyed out with the reason;
- **API**: `POST /api/chat {"message": "...", "profile": "local-qwen7b"}`;
- **new endpoint**: add a profile block to `providers.yaml`.

Profiles marked `tools: emulated` use strict JSON tool calling with schema validation and retry, for models with
weak native tool use. `routing.enabled: true` sends classification, extraction and categorisation to a cheap or
local model and advisory answers to a stronger one. A failing provider falls back down `fallback_chain`, ending
in `rules-offline`, and the UI shows which model actually answered. Run `python -m sme_copilot.cli models` to see
which profiles are usable.

If the chosen model fails (server down, timeout, bad response), the reply carries `fallback: true`,
`requested_profile` and `fallback_reason` in the API, and the UI shows a red warning naming the model that
actually answered and why. A local model only ever falls back to other local profiles, never to a cloud API.

## Local model (private, on your GPU)

Measured on an AMD RX 9060 XT 16 GB + Ryzen 7 3700X + 16 GB RAM (Windows, llama.cpp Vulkan build). Full numbers:
[benchmarks/results/local_models.md](benchmarks/results/local_models.md), method and decisions:
[docs/overnight_log.md](docs/overnight_log.md).

| | Gemma 4 12B Q4_K_M + MTP (default) | Qwen3-14B Q4_K_M (backup) |
|---|---|---|
| profile | `local-llamacpp` (native tools) | `local-qwen14b` (emulated tools) |
| VRAM | ~8 GB | ~13 GB |
| generation speed | ~38 tok/s | ~20 tok/s |
| median answer time (golden set) | ~12 s, first words after ~4 s (streamed) | ~18 s |
| tool-call success / numeric accuracy | 95% / 93% | 88% / 86% |
| answers with invented numbers | 6% | 8% |
| replies in the user's language (EN, Bangla, Banglish) | 100% | 86% (Bangla/Banglish) |

Before this tuning, the local Qwen3.8 27B ran at ~9 tok/s, spilled out of VRAM, and took ~2 minutes per answer.

1. Get [llama.cpp](https://github.com/ggml-org/llama.cpp/releases) (Windows Vulkan build) and the models:
   [gemma-4-12b-it-Q4_K_M.gguf](https://huggingface.co/unsloth/gemma-4-12b-it-GGUF) +
   [mtp-gemma-4-12B-it-Q8_0.gguf](https://huggingface.co/ggml-org/gemma-4-12B-it-GGUF) (draft head), and optionally
   [Qwen3-14B-Q4_K_M.gguf](https://huggingface.co/Qwen/Qwen3-14B-GGUF).
2. Start the server: `scripts\start_local_llm.bat` (Gemma) or `scripts\start_local_llm.bat qwen14b`. Set
   `LLAMA_DIR` / `MODELS_DIR` if they are not in `D:\llama-vulkan`. On Linux/macOS: `make local-llm`.
3. Pick the profile in the **Model** menu, or set `LLM_PROFILE=local-llamacpp` (and `LOCAL_ONLY_MODE=true`) in `.env`.

Hardware needed: a GPU with at least 10 GB of VRAM for Gemma (14 GB for the Qwen backup), and 16 GB of system RAM.
Answers stream token by token. Tune a weaker machine with `TOOL_RESULT_BUDGET_CHARS` (smaller tool results = faster).

## Tests, coverage, benchmarks, evidence

```bash
python -m pytest                                              # 219 tests
python -m pytest --cov=sme_copilot --cov-report=term-missing  # 91% line coverage (docs/coverage.txt)
python -m sme_copilot.cli bench --profiles rules-offline,claude-sonnet,local-qwen7b   # model comparison
python -m sme_copilot.cli evidence                            # scripted end-to-end run + exported operation logs
python -m sme_copilot.cli verify-audit                        # recompute the audit hash chain
python -m sme_copilot.cli export-finetune --include-unrated   # interaction log -> SFT + preference datasets
```

The benchmark runs a **48-scenario golden set** (English, Bangla, Banglish). It measures latency, time to first
token, tokens per second, estimated cost, tool-call success, numeric accuracy against deterministic ground truth,
financing-match correctness, hallucinated numbers, refusal correctness, safety and language match. Results are
written to `benchmarks/results/` as CSV, Markdown, JSON and a PNG chart. Profiles without keys are skipped.

## Project layout

```
sme_copilot/
  llm_providers/     unified LLMProvider; Anthropic, OpenAI, Gemini, OpenAI-compatible, Ollama, rules; router; JSON-mode fallback
  agent/             orchestrator loop, tool registry (tiers), executor, intent engine, language detection, numeric grounding
  tools/             ingestion (CSV/XLSX/statements), NL entry parser, categoriser, quality checks, analysis, loan math
  forecasting/       cash-flow forecast, what-if engine, alerts, digest
  financing_catalog/ catalog loader (schema-validated YAML), matcher, loan-readiness score
  sandbox/           message templates, PDF loan report
  security/          auth, permissions (tiers), audit chain, PII masking, crypto, injection defence, guardrails, HTTP hardening
  telemetry/         interaction dataset (JSONL, PII-masked), fine-tune export
  benchmarks/        golden set + runner
  demo/              demo persona seed, scripted evidence run
  api/               FastAPI routes
config/              providers.yaml, categories.yaml, calendar_bd.yaml, compliance_bd.yaml, financing/catalog.yaml
frontend/            no-build SPA (HTML + ES modules + SVG charts)
seed/demo/           generated demo source files (same formats a real user uploads)
docs/                technical docs, security assessment, evidence, demo script, presentation outline
tests/               unit, schema, permission, injection, API and end-to-end tests
```

## Submission materials

| Item | Where |
|---|---|
| Technical documentation (architecture, algorithms, security design) | [docs/TECHNICAL_DOCUMENTATION.md](docs/TECHNICAL_DOCUMENTATION.md) |
| Security self-assessment (permission tiers, known risks) | [docs/SECURITY_ASSESSMENT.md](docs/SECURITY_ASSESSMENT.md) |
| Execution evidence (sandbox operation logs) | [docs/EXECUTION_EVIDENCE.md](docs/EXECUTION_EVIDENCE.md), [docs/evidence/](docs/evidence/) |
| Demo script (< 5 min) | [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) |
| Presentation outline (< 10 min) | [docs/PRESENTATION_OUTLINE.md](docs/PRESENTATION_OUTLINE.md) |
| Test report and coverage | [docs/TEST_REPORT.md](docs/TEST_REPORT.md), [docs/coverage.txt](docs/coverage.txt) |
| Model benchmark | [benchmarks/results/summary.md](benchmarks/results/summary.md) |
| Assumptions | [ASSUMPTIONS.md](ASSUMPTIONS.md) |
