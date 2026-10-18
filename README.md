# SME Finance Copilot

**An AI finance copilot for Bangladesh small and medium businesses.** Built for the 2026 Shenzhen International
FinTech Competition (FinTechathon), International Track, **Topic E: SME Finance Copilot**.

The default Home guides owners who have no finance background with just recorded money and one practical next step. Tasks has tabs for To do, Reminders, and Coming up; Money separates monthly totals from forecasts; Records holds entries and history. Other tools remain available through More. Contributors and agents must read the [design principles](docs/DESIGN_PRINCIPLES.md) and [contribution guide](CONTRIBUTING.md) before implementing features.

The **Dhaka South shop/trader pilot** adds six resumable guided tasks: record/check money, collect a customer due, plan a payment, check real loan quotes, test a product and prepare paperwork. Open **More → Ask Copilot**. The flow asks one question at a time and prepares owner-confirmed actions, without a chat transcript. Documents, reminder settings and offline drafts have their own destinations. See the [agreed product plan, source register and operator runbook](docs/PRODUCT_PLAN_BD.md).

Owner SMS has a disabled-by-default provider adapter and an independent persistent worker: `scripts\start_reminder_worker.ps1`. It requires provider onboarding, opt-in and phone verification. In-app reminders work without SMS. The browser can keep local drafts and cached task progress through connection loss; reconnect to review and confirm them. Legacy illustrative financing tools and generic compliance dates are blocked by default. Current operational sources remain marked for human review, and the real-owner pilot study has not yet been conducted.

Small shops, garment subcontractors, traders, food businesses and freelancers can upload their sales ledgers,
bank statements and bKash/Nagad/Rocket statements, or simply type *"dokan bhara 15000 dilam"*. The copilot then:

- **analyses the business**: margins, break-even, receivables and payables aging, cost drivers, Eid and
  Pohela Boishakh seasonality, and why the numbers changed;
- **manages cash flow**: 30/60/90-day forecast with an uncertainty band, what-if simulation, and proactive alerts
  for low balance, overdue invoices, rent/salary/EMI/VAT dates and unusual spending;
- **checks actual financing quotes**: net proceeds, complete repayment schedules, essential costs and a chosen reserve,
  with slower-sales scenarios and separate funding enquiry routes. Legacy illustrative matching is disabled for the pilot;
- **gets work done**: saved tasks, Bangla/English follow-up letters, editable paperwork, product experiments and
  in-app reminders. Owner SMS requires setup and consent; **sandbox** payments need the owner's explicit confirmation. Every action
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

The default model is the independent **shared Ollama server**, used by every website user. Start it once as
described below. Without a running model, the offline `rules-offline` engine answers instead: a deterministic engine that implements the
same provider interface, so the whole product (tool calling and every security control) runs without network
or GPU. Each such reply is labelled as a fallback in the UI. For a private model on your own GPU, see
[Local model](#local-model-private-on-your-gpu).

### Shared model service (Windows)

The website and inference run as separate processes on this computer:

```text
User browsers -> website + API (:8000) -> shared Ollama service (127.0.0.1:11434)
```

Users open the website; their devices need no model installation. Conversations and business permissions
stay in the website backend. Every model request uses the same model endpoint, with request-specific messages.
The browser never contacts Ollama directly. Restarting the website leaves the model service running.

After installing Ollama and pulling `gemma4:12b`, run these independently from the project root:

```powershell
# Once per computer/service restart. Reuses an already-running Ollama instance.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_shared_llm.ps1

# Website only; preserves existing data and listens on the network for other users.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_website.ps1
```

The model script creates a `sme-copilot` alias of `gemma4:12b` with a 16K context, reusing the existing model
files, and keeps it loaded. It probes CUDA on NVIDIA systems and checks that the loaded model allocates GPU
memory. If an existing Ollama daemon cached a failed GPU detection, refresh just the model service with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_shared_llm.ps1 -Restart
```

The restart targets only the Ollama process serving the selected port and its tray supervisor, leaving the
website running. New service instances use flash attention and a Q8 KV cache to reduce context memory use.
Use `-AllowCpu` only when deliberately running without GPU acceleration. Check `nvidia-smi` and
`data/llm.stderr.log` for device memory and the number of layers offloaded. Ollama's `/api/ps` can undercount
GPU memory with speculative models. An 8 GB GPU may keep part of Gemma in system memory; CPU participation
is expected when the complete model, vision projector, draft model and context do not all fit in VRAM.

Ollama schedules requests against the shared model; users can share it even when
hardware capacity requires requests to queue. No process is created per user. See
[Ollama context configuration](https://docs.ollama.com/api/openai-compatibility#setting-the-context-size) and
[request scheduling](https://docs.ollama.com/faq#how-does-ollama-handle-concurrent-requests).

Copy `.env.example` to `.env`, then use:

```dotenv
LLM_PROFILE=shared-llm
LLM_SHARED_ONLY=true
SHARED_LLM_BASE_URL=http://127.0.0.1:11434/v1
SHARED_LLM_MODEL=sme-copilot
LOCAL_ONLY_MODE=true
```

With `LLM_SHARED_ONLY=true`, the server blocks alternate model profiles and the UI uses the shared default.
The offline rules engine remains a labelled fallback if the shared service is unavailable. To restore model
switching, set `LLM_SHARED_ONLY=false`. Restart the website after changing `.env`.

`Start SME Copilot.bat` launches only the website and opens `http://127.0.0.1:8000`; only this computer can reach
it. To show it on phones or other computers on the same Wi-Fi, use `Start SME Copilot (Wi-Fi).bat` instead (or
`scripts\start_website.ps1 -Network`): it prints the address to open on the other device. Windows Firewall must
allow the website port. Ollama stays on loopback; only the website backend needs access to it.

### Docker (one command)

```bash
docker compose up --build                          # demo on :8000, offline rules engine
docker compose --profile local-llm up --build      # + Ollama with a local 7B model (nothing leaves the machine)
```

With the `local-llm` profile, choose **Local Qwen2.5 7B (Ollama)** in the model dropdown, or set
`LLM_PROFILE=local-qwen7b` and `LOCAL_ONLY_MODE=true` in `.env`. `make demo`, `make test`, `make bench` and
similar targets are in the `Makefile`.

For the independent host Ollama service above, use `LLM_PROFILE=shared-llm`; the app container connects to
`http://host.docker.internal:11434/v1`. Override `DOCKER_SHARED_LLM_BASE_URL` for a different host endpoint.
The optional `local-llm` compose profile is unnecessary when the shared host service is already running.

### Deployment

The app is one stateless container plus a data volume (SQLite by default; set `DATABASE_URL` for Postgres).

1. Build and push the image to any container host (Render, Railway, Fly.io, Azure Container Apps, or a VM with Docker).
2. Set `APP_ENV=production`, a real `FIELD_ENCRYPTION_KEY`, and `CORS_ORIGINS=https://your-domain`. In
   production the demo credentials are never shown and the API docs are disabled.
3. Put it behind HTTPS (the platform's TLS or a reverse proxy). HSTS is sent automatically over HTTPS.
4. For a demo deployment, run `python -m sme_copilot.cli seed --reset` once, or use the compose `demo` command.

**Before real owners use it** (security review, October 2026):

- Never run real data with `APP_ENV=demo`: `/api/health` then lists the demo logins, and the demo passwords are
  published in this README. Use `APP_ENV=production`, which also refuses to start without `FIELD_ENCRYPTION_KEY`.
- The launchers and `docker compose` keep the website on this computer by default. `Start SME Copilot (Wi-Fi).bat`
  shares it with the whole network (and, in demo mode, its demo logins); put it behind HTTPS with real passwords
  before sharing real data.
- Set `COOKIE_SECURE=true` behind a TLS proxy, and `ALLOW_SIGNUP=false` for a closed pilot.
- Without `FIELD_ENCRYPTION_KEY` a development key is generated next to the database, so copying the data folder
  copies the key too. Generate a real key (see `.env.example`) and keep it outside the data folder.

**Deployment link:** _add the public URL here after deploying._

---

## Market prices near you (Home price drawer)

Home has a minimised **Prices** tab on its right edge. It opens a half-width drawer with public prices of items
that the owner's kind of business buys or sells, near the business's district, and a one-line outlook for next
month with its possible range. It stays closed until the owner opens it, so Home keeps its two cards.

- **Data:** World Food Programme "Bangladesh - Food Prices" on HDX ([CC BY-IGO](https://data.humdata.org/dataset/wfp-food-prices-for-bangladesh)):
  monthly retail prices of about 60 everyday items (rice, lentils, oils, sugar, onion, potato, eggs, chicken,
  soap, detergent, fuel…) in about 110 markets. The newest month trails today by one to two months, and the drawer
  says which month each price is from. A snapshot (2022 onward) is bundled in `sme_copilot/market/snapshot/` so it
  works offline; the server refreshes it weekly in the background unless `LOCAL_ONLY_MODE` is on. No business data
  is sent.
- **Nearest area:** the business's district, else its division, else the national average, always using a series
  that reaches within three months of the newest data.
- **Forecast:** [Amazon Chronos-Bolt](https://github.com/amazon-science/chronos-forecasting) (`chronos-bolt-small`,
  48M parameters, Apache-2.0) reads up to three years of monthly prices on CPU and returns a median and a 10-90%
  range. Without it, a damped-trend and month-of-year statistical estimate is used. Language models are not used
  for prices: they have no reliable local price history and would invent numbers.
- **How good is it?** `scripts/backtest_market.py` hides the last three months of 170 real market/item series and
  forecasts them. Both engines' 10-90% ranges contained the real price about 8 times in 10 (79% model, 78%
  statistical; ideal 80%). Point forecasts did not beat "no change" (prices are sticky), and the direction of moves
  over 2% was right about 6 times in 10. The drawer therefore leads with the range and says "likely steady" for
  small moves.

Install the model and fetch the newest data once (allowed even in `LOCAL_ONLY_MODE`; after that it runs offline):

```bash
.venv/Scripts/pip install -r requirements-forecast.txt
.venv/Scripts/python -m sme_copilot.cli market --setup
```

`python -m sme_copilot.cli market --district Gazipur --type restaurant_food` prints what the drawer would show.

## Languages

The interface is available in English, বাংলা and 中文 (Simplified Chinese), chosen on the login screen or in the
top bar. Chinese text lives in [frontend/i18n-zh.js](frontend/i18n-zh.js), keyed by the English source text, so
each English/Bangla pair gains Chinese without a third argument at its call site. The Copilot answers in Chinese
when a language model is available; the offline rules engine answers in English. Letters and SMS to customers stay
in English or Bangla because their recipients are in Bangladesh.

---

## Environment variables

Secrets come **only** from the environment (`.env` is git-ignored). See [.env.example](.env.example).

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `dev` | `dev` / `demo` (shows demo logins) / `production` (requires encryption key, hides API docs) |
| `FIELD_ENCRYPTION_KEY` | auto dev key | Fernet key for encrypting account numbers, phones, TIN and trade licence at rest |
| `LLM_PROFILE` | – | Overrides `default_profile` in `config/providers.yaml` on this machine |
| `LLM_SHARED_ONLY` | `false` (`true` in `.env.example`) | All users use the server default; alternative profiles are blocked |
| `SHARED_LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | Shared inference endpoint used by the website backend |
| `SHARED_LLM_MODEL` | `sme-copilot` | Model alias served by the shared Ollama instance |
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
| `MARKET_PRICES_ENABLED` | `true` | Show the Home price drawer |
| `MARKET_REFRESH` / `MARKET_REFRESH_DAYS` | `true` / 7 | Weekly background download of the public WFP prices (never in `LOCAL_ONLY_MODE`) |
| `MARKET_DATA_URL` | HDX | Override the price file location |
| `MARKET_FORECAST_MODEL` | `amazon/chronos-bolt-small` | Price forecasting model; empty = statistical estimate only |

---

## Switching models (no code changes)

When `LLM_SHARED_ONLY=false`, users can switch models as described here. All profiles live in [config/providers.yaml](config/providers.yaml). The adapters are Anthropic (Claude), OpenAI,
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
4. Optional, for **Data → Add → Photo of your khata**: put Gemma 4's vision projector (the `mmproj-*.gguf` file from the
   model's Hugging Face repo) in the models folder as `mmproj-gemma-4-12b-it-f16.gguf` (or set `LLM_MMPROJ`). The start
   script then adds `--mmproj`, and the app sees `vision: true` on the server's `/props`. Without it, photos need a cloud
   model with vision; a local default never sends a photo to the cloud on its own. Details: `scripts\start_local_llm.bat`.

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
| Test report and coverage (443 + 19 tests, 90%) | [docs/TEST_REPORT.md](docs/TEST_REPORT.md), [docs/coverage.txt](docs/coverage.txt) |
| Model benchmark | [benchmarks/results/summary.md](benchmarks/results/summary.md) |
| Assumptions | [ASSUMPTIONS.md](ASSUMPTIONS.md) |
| Third-party licences (data, libraries, models) | [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) |
| Price-forecast backtest | [scripts/backtest_market.py](scripts/backtest_market.py), results in [docs/TEST_REPORT.md](docs/TEST_REPORT.md) |
| Presentation deck and demo video | Submitted with the entry |
