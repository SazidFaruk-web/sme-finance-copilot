# SME Finance Copilot: Technical Documentation

FinTechathon 2026, International Track, Topic E (SME Finance Copilot). Target market: Bangladesh SMEs.

## 1. Design principles

1. **The LLM never does arithmetic.** Totals, margins, forecasts, EMI, DSCR, break-even, aging and eligibility
   are computed by deterministic, unit-tested Python. The model only understands the request, chooses tools,
   and explains tool results. Every number shown to the user carries a *trace*: the formula, the steps and the
   source rows.
2. **Security is enforced in code, not in the prompt.** Every tool call, whether it came from an LLM, the
   offline engine or a UI button, passes one pipeline: schema validation, permission tier and role check,
   limits, human confirmation for money, then a hash-chained audit entry.
3. **Works offline, and the model is swappable.** One `LLMProvider` interface covers five vendor adapters plus a
   deterministic offline engine. Models switch per request, with automatic fallback.
4. **Local relevance.** Plain-English interface and replies;
   lakh/crore formatting; bKash, Nagad and Rocket statements; Eid, Pohela Boishakh and harvest seasonality;
   Bangladesh SME financing types; VAT/TIN/trade licence awareness; public market prices near the shop.
5. **Uncertainty is shown, not hidden.** Cash forecasts carry an 80% band and price outlooks a 10-90% range
   whose reliability is measured on real data (section 5.11).

## 2. System architecture

```mermaid
flowchart LR
  subgraph Client["Browser SPA (no build, offline)"]
    UI[Dashboard · Chat · Data · Financing · Actions · Audit]
  end
  UI -- "HTTPS + Bearer token" --> API

  subgraph Server["FastAPI app"]
    MW[Security headers · CORS · Rate limit]
    API[REST + SSE routes] --> AUTH[Auth / RBAC]
    API --> AGENT[Agent orchestrator]
    API --> EXEC
    AGENT --> GUARD[Refusal guardrail]
    AGENT --> ROUTER[Model router + fallback]
    ROUTER --> PII[PII masking vault]
    AGENT --> EXEC[Tool executor]
    EXEC --> PERM[Permission tiers · limits · daily cap]
    EXEC --> TOOLS
    EXEC --> AUDIT[(Hash-chained audit log)]
    subgraph TOOLS["Deterministic tools"]
      ING[Ingestion & NL entry]
      ANA[Analysis]
      FC[Forecast · What-if · Alerts]
      FIN[Financing matcher · Readiness]
      ACT[Sandbox actions · PDF]
      MKT[Market prices · Chronos-Bolt outlook]
    end
    TOOLS --> DB[(SQLite / SQLAlchemy<br/>Fernet-encrypted fields)]
    AGENT --> TEL[Interaction dataset JSONL<br/>PII-masked]
  end

  ROUTER -- external, masked --> CLOUD[Anthropic · OpenAI · Gemini · OpenRouter · Groq · DeepSeek]
  ROUTER -- local --> LOCAL[Ollama · llama.cpp · vLLM]
  ROUTER -- offline --> RULES[Rules engine]
  MKT -- weekly public download, no business data --> HDX[WFP prices on HDX]
```

| Layer | Module | Responsibility |
|---|---|---|
| Presentation | `frontend/` | SPA: guided Home/Tasks/Money/Records, Advanced dashboard, chat with SSE streaming, confirmations, audit viewer, Home price drawer (`market.js`); English only. No `innerHTML`, strict CSP |
| API | `sme_copilot/api/` | Auth, chat, tools, data, insights, actions, privacy; Pydantic request validation |
| Agent | `sme_copilot/agent/` | Language detection, guardrails, model loop, tool registry and executor, numeric grounding, offline intent engine |
| Providers | `sme_copilot/llm_providers/` | Unified interface, 6 adapters, router, structured output and tool-call emulation |
| Domain tools | `tools/`, `forecasting/`, `financing_catalog/`, `sandbox/` | All financial computation and actions |
| Market prices | `market/` | Public WFP price data (bundled snapshot + weekly refresh), nearest-area series, Chronos-Bolt or statistical outlook |
| Security | `sme_copilot/security/` | Auth, permissions, audit chain, PII, crypto, injection defence, refusal guardrails, HTTP hardening |
| Data | `models.py`, `db.py` | 17 tables; append-only audit table protected by SQLite triggers |
| Ops | `benchmarks/`, `telemetry/`, `demo/`, `cli.py` | Benchmark harness, dataset export, seed, scripted evidence |

## 3. Agent loop

```mermaid
sequenceDiagram
  participant U as User
  participant A as Agent
  participant G as Guardrail
  participant R as Router/LLM
  participant X as Executor
  participant P as Permissions
  participant T as Tool
  participant L as Audit log
  U->>A: "What if my biggest customer pays 20 days late?"
  A->>A: detect language (en / bn / banglish), scan for injection
  A->>G: fraud / tax-evasion / fake-document check
  A->>R: system prompt + history + tools (PII masked if external)
  R-->>A: tool_call run_what_if{kind: delay_receivable, days: 20}
  A->>X: execute(tool, args)
  X->>X: Pydantic validation (invalid -> error returned to the model for retry)
  X->>P: tier 0 / role ok?
  X->>T: run deterministic handler
  T-->>X: result + trace (formula, steps, rows)
  X->>L: audit (masked inputs, result summary)
  X-->>A: compact JSON (row ids removed, untrusted strings neutralised)
  A->>R: tool result
  R-->>A: final answer in the user's language
  A->>A: numeric grounding check, disclaimer, traces
  A->>L: agent_decision event
  A-->>U: reply + "show calculation" + confirmations
```

Details:

- **Steps.** At most 6 model calls and 4 tool calls per step. History is capped at 8 messages.
- **Tool calling.** Native tool calling is used where the model supports it. Models flagged `tools: emulated` get
  the tool list in the prompt and must reply with one strict JSON envelope
  (`{"action": "call_tool", ...}` or `{"action": "final", ...}`), which is validated and retried up to twice
  with the error message (`llm_providers/structured.py`).
- **Structured output.** `structured_chat()` uses native JSON mode where available (OpenAI `json_schema`,
  Gemini `responseSchema`, Anthropic forced tool), otherwise prompt-instructed JSON. Every output is parsed
  with a balanced-brace extractor and validated against a Pydantic schema, with retry.
- **Offline engine.** `RulesProvider` implements the same interface. `plan()` maps EN/BN/Banglish keywords
  and regexes to tool calls; `compose()` writes templated answers in the user's language from tool results
  only. It is the default demo model, the last link of every fallback chain, and the benchmark baseline.
- **Numeric grounding.** Every number in the final reply (handling ৳, commas, lakh/crore words, %, Bangla
  digits) must match a number in the tool outputs, allowing for rounding, lakh scaling and ratio-to-percent
  conversion. Unmatched numbers are shown to the user as "could not verify" and counted as hallucinations in
  the benchmark.

## 4. LLM provider abstraction

`LLMProvider.chat(messages, tools, json_schema, temperature, max_tokens)` returns a `ChatResponse` with
content, tool calls, usage, latency and TTFT. Adapters also provide `stream()`, `count_tokens()` and
`estimate_cost()`. Retries use exponential back-off on 408, 409, 429, 5xx and network errors; 4xx auth errors
fail fast.

| Adapter | Wire format | Notes |
|---|---|---|
| `anthropic` | Messages API | Merges consecutive tool results into one user turn; structured output via forced tool |
| `openai` | Chat Completions | `max_completion_tokens`, `json_schema` response format |
| `gemini` | `generateContent` / SSE | Schemas inlined (no `$ref`), `nullable` for optional fields |
| `openai_compatible` | Chat Completions | OpenRouter, Groq, DeepSeek, Together, vLLM, llama.cpp; `json_object` mode |
| `ollama` | OpenAI-compatible `/v1` | Local by default (`external: false`) |
| `rules` | in-process | Deterministic offline engine |

Routing (`providers.yaml → routing`): tasks such as `classification`, `extraction`, `categorization` and
`advisory` can map to different profiles. The fallback chain is tried in order and ends in `rules-offline`.
External profiles are refused when `LOCAL_ONLY_MODE=true`. For external profiles, a per-request `PIIVault`
replaces phones, accounts, NID, TIN, emails and cards with placeholders such as `[PHONE_1]`, and restores
them locally in the reply and in tool arguments.

## 5. Core algorithms

### 5.1 Ingestion (`tools/ingestion.py`)
- CSV, TSV, XLSX or pasted text. The real header row is detected in the first 15 rows, so bank preambles are
  skipped. Columns are mapped through an English and Bangla synonym table (exact matches first, then
  containment).
- Supported layouts: ledger, bank statement (debit/credit), wallet statement (transaction type, fee, status),
  and invoices.
- Wallet types (`Cash In`, `Send Money`, `Payment`, …) map to a direction and category. Fees become separate
  `mobile_fees` rows. Failed rows are skipped and reported.
- Amounts are parsed from `৳1,20,000`, `Tk 500`, `(2,000)` and Bangla digits. Dates are parsed day-first.
- Phone or account numbers found in name columns move into the encrypted `account_ref`, and the display name
  is masked.
- Each row keeps `batch_id` and `source_row` for traceability, and a file is only ever imported once (SHA-256).

### 5.2 Natural-language entry (`tools/nl_entry.py`)
Handles English, Bangla and Banglish: Bangla digits, multipliers (`k`, `hazar`, `হাজার`, `lakh`, `লাখ`,
`crore`) and quantities (`12 shirts`, `১২টা`). Dates and phone numbers are blanked out before amounts are
read. Explicit verbs (`sold`, `paid`, `dilam`, `বিক্রি`) set the direction, and the longest keyword sets the
category. The parser also extracts channel (cash, bKash, Nagad, Rocket, bank, card), relative dates
(`gotokal`, `গতকাল`) and counterparty (`from X`, `X ke`). It returns a confidence score and the list of
missing fields.

### 5.3 Data quality (`tools/quality.py`)
- **Duplicates.** Same direction and amount, and either the same reference, or same date and description, or
  ≤ 1 day apart with ≥ 0.85 description similarity. Detected within a batch and against existing rows,
  bucketed so it stays roughly O(n). Duplicates are flagged and excluded from analysis.
- **Anomalies.** Robust z-score per category, `0.6745·(x−median)/MAD > 3.5` and `x > 2×median`. Sparse
  categories are compared with the overall outflow median (> 5× and > ৳50,000). A first payment to a new
  counterparty in the top 10% of outflows within the last 60 days is also flagged.

### 5.4 Financial analysis (`tools/analysis.py`, `tools/finance_math.py`)
| Metric | Formula |
|---|---|
| Gross margin | (revenue − COGS) / revenue; COGS = stock purchases (cash basis) |
| Net operating margin | (revenue + other income − COGS − variable − fixed) / revenue; loan repayments, capex and drawings reported separately |
| Break-even | monthly fixed costs / (1 − (COGS + variable) / revenue); margin of safety |
| Aging | outstanding = amount − paid; buckets not due / 1–30 / 31–60 / 61–90 / 90+; DSO = outstanding / (90-day sales / 90) |
| Cost drivers | category share and change vs the previous equal-length period |
| Seasonality | month revenue / average; peaks and lows explained with the BD festival calendar; upcoming events with last year's uplift |
| Explain change | per-category and per-customer deltas between periods, written as sentences |
| EMI (reducing) | P·r·(1+r)ⁿ / ((1+r)ⁿ − 1), r = annual/12 |
| EMI (flat) | (P + P·rate·n/12) / n |
| Effective APR | IRR (bisection) of instalments against cash actually received (principal − fees) × 12 |
| DSCR | monthly operating cash flow / monthly debt service |

### 5.5 Cash-flow forecast (`forecasting/forecast.py`)
`balance[t] = balance[t−1] + baseline_in[t] − baseline_out[t] + scheduled[t]`, for 30, 60 or 90 days.
- **Scheduled.** Open receivables arrive on due date + that customer's historical average delay (overdue
  ones within 7–21 days; more than 90 days overdue counted at 50%). Payables leave on their due date.
  Recurring obligations come from explicit entries or are auto-detected from history (≥ 3 of the last 4
  months, amounts within ±35%).
- **Baseline.** Built from the last 90 days. Sales not explained by invoice collections, plus other income.
  New credit-sale collections at the historical rate, but only after the typical issue-to-payment lag. Outflows
  are split into variable (scaling with sales in what-ifs) and fixed/other; categories covered by obligations
  are excluded. A seasonal factor comes from last year's same month.
- **Uncertainty.** 80% band = ±1.28·σ(weekly net cash flow)·√(t/7).
- **Outputs.** Daily series, 30/60/90 summaries, lowest point, first date below zero and below the safety
  level, runway, and the scheduled items list. All are traceable.

### 5.6 What-if (`forecasting/whatif.py`)
Scenarios modify a copy of the forecast inputs. Both versions are projected and compared on end balance,
minimum, first negative date, EMI and explanation sentences. Supported scenarios: a customer (or the biggest
one) paying N days late; a loan with its EMI schedule; sales ±%, with variable costs following; a category cost
± % or a new monthly cost such as hiring; a one-off inflow or outflow.

### 5.7 Alerts and digest (`forecasting/alerts.py`, `digest.py`)
Alert types: low balance or shortfall within 30 days, overdue invoices (critical after 60 days), supplier
bills due, obligations due within 7 days, compliance dates within 10 days (configured and marked "verify"),
unusual payments, category spending spikes (> 1.5× the 3-month average), and seasonal preparation. Alerts
are upserted by dedupe key, auto-resolved when the condition clears, and stay dismissed once dismissed. The
digest adds KPIs and **one-click suggested actions** that call the same audited tools.

### 5.8 Financing matcher (`financing_catalog/`)
The catalog lives in schema-validated YAML (12 product types, every figure illustrative and marked
`verified: false`). For each product:
1. **Hard and soft rules** on the business's real metrics: age, 6-month revenue, revenue CV, months of
   records, trade licence, TIN, bank account, women-led, minimum amount, collateral coverage, and open
   receivables (for invoice financing). Each rule produces a sentence.
2. **Affordability.** The largest principal that keeps DSCR ≥ the product minimum at the mid rate:
   `max EMI = op. cash flow / min DSCR − existing debt service`, inverted through the EMI formula.
3. **Offer** = min(request, product maximum, DSCR capacity, invoice advance, supplier limit). The binding
   constraint is named.
4. **Cost** at the min, mid and max rate: EMI, total repayment, total cost of credit, effective APR.
5. **Fit score** = cost 40 + DSCR headroom 20 + amount fit 20 + speed 10 + no collateral 10, with a 20%
   penalty when the purpose doesn't match.

Every product appears either as a recommendation (with reasons and cautions) or as a rejection (with the
failed rules).

### 5.9 Loan-readiness score
Eight components totalling 100 points: business age 10, record keeping 15, revenue stability 15,
profitability 15, DSCR 15, documentation 15, receivables health 10, collateral 5. Each comes with a
point-valued improvement tip.

### 5.10 Language detection
Replies are English unless `APP_LANGUAGES` switches more languages on (default `en`); detection below only
matters then.
**Chinese** when at least two CJK characters make up ≥ 20% of the letters (so `iPhone 12 价格` counts but a
single character in English text does not). **Bangla** when the share of Bangla script letters and vowel signs
(excluding digits and ৳) among script characters is ≥ 0.3. **Banglish** when Latin text contains Banglish
marker words (`ami`, `koto`, `dilam`, `lagbe`, `tagada`, …). Otherwise **English**. LLM prompts ask for the
detected (or UI-selected) language; the offline templates cover English, Bangla and Banglish, and answer
Chinese in English rather than in Bangla. Bangla uses Bangla digits and lakh grouping.

### 5.11 Market price outlook (`market/`)
The Home price drawer answers "will what I buy or sell cost more next month?" for the owner's kind of business.

1. **Data.** World Food Programme "Bangladesh - Food Prices" (HDX, CC BY-IGO): monthly retail prices of ~60
   everyday items in ~110 markets. A filtered snapshot (2022-01 to 2026-08, 159 KB) is bundled; the server
   refreshes it in the background at most weekly (never in `LOCAL_ONLY_MODE`), over HTTPS from HDX hosts only,
   with a 60 MB cap, and replaces the file atomically only after it parses and has ≥ 1,000 usable rows.
2. **Relevance.** Each business type has a basket (e.g. restaurant: rice, broiler chicken, soybean oil,
   onion, …; pharmacy/grocery: staples plus toothpaste, soap, sanitary pads). Garment/trims businesses are told
   that no public fabric or trims series exists and see running-cost items instead.
3. **Nearest area.** The business's district (with spelling aliases such as Chattogram → Chittagong), else
   its division, else all markets. A series qualifies only with ≥ 12 months in the last 36 and an observation
   within 3 months of the newest data, so a stale district series never wins over a fresh division one.
   Prices are the median across the area's markets per month; gaps of up to 2 months are interpolated.
4. **Forecast.** Target = the next calendar month. Primary engine: Amazon Chronos-Bolt-small (48M parameters,
   Apache-2.0, CPU, safetensors weights) reading up to 36 months and returning the 10th, 50th and 90th
   percentiles. Fallback: damped trend (φ = 0.8 on the last 12 months of log prices) plus a month-of-year
   offset (centred 12-month moving average, shrunk by 0.5), with σ of monthly log changes × √h for the range.
   No forecast more than 6 months past the last observation. A 10-90% spread above 30 points is marked
   uncertain; the drawer then says "hard to call" (or "likely up/down, but hard to say how much" when the
   whole range has one sign).
5. **Measured reliability** (`scripts/backtest_market.py`, 170 market/item series, 3 months held out):

   | Engine | Median abs. error | Direction right (moves > 2%) | 10-90% range held the real price |
   |---|---|---|---|
   | No change | 1.98% | n/a | n/a |
   | Statistical | 3.19% | 63.5% | 78.2% |
   | Chronos-Bolt-small | 2.31% | 57.6% | 79.4% |

   Ranges are well calibrated (ideal 80%), point forecasts do not beat "no change" because prices are sticky,
   so the drawer leads with the range and calls moves under 2% "likely steady". Language models are not used
   for prices: they have no reliable local price history.

### 5.12 Translations (switched off by default)
About 1,180 translations keyed by the English source text, plus patterns for templated sentences. `t()`,
`plain()`, the guided-task helpers, copy tables and server labels (`{en, bn}`) look up Chinese without a
third argument at each call site. While Chinese is active, a MutationObserver translates remaining fixed
English (server report rows, category names) by exact dictionary match; it never touches the owner's input,
their chat messages or the model's reply text. Customer letters and SMS stay in English or Bangla.

## 6. Action layer and human-in-the-loop

```mermaid
stateDiagram-v2
  [*] --> Proposed: LLM / rules / UI proposes a Tier-2 tool
  Proposed --> Denied: role ≠ owner / > per-txn limit / > daily cap / balance − reservations < amount / suspicious input
  Proposed --> Pending: allowed → PendingAction (expires in 10 min), amount reserved
  Pending --> Rejected: owner rejects
  Pending --> Expired: TTL passed
  Pending --> Pending: retyped amount ≠ request (409, audited)
  Pending --> Confirmed: owner re-types exact amount → re-authorise → execute in sandbox
  Confirmed --> [*]: balance debited, transfer + transaction recorded, audit "confirmed"
```

- There is **no tool** for confirming. Confirmation is only possible through
  `POST /api/actions/{id}/confirm`. The confirming user's role is checked **first** (money = owner only), so a
  lower role can neither learn the expected amount nor cancel the owner's request; then the re-typed amount,
  then the password again for payments at or above `STEP_UP_AMOUNT` (৳50,000).
- Tier-2 handlers raise `PermissionError` unless they are running inside `confirm_pending()`, as defence in
  depth.
- Tier-1 actions:
  - `create_payment_reminder` (prepared, then saved to the simulated outbox when confirmed),
  - `draft_invoice_followup` (deterministic EN/BN templates),
  - `generate_loan_report` (reportlab PDF with a forecast chart, SHA-256 recorded),
  - `prepare_loan_checklist`,
  - `add_obligation`, `schedule_alert`, `add_transaction`, `acknowledge_alert`.

## 7. Data model (main tables)

`businesses`, `users`, `auth_sessions` (SHA-256 of tokens), `import_batches`, `transactions` (source batch
and row, flags, encrypted `account_ref`), `invoices` (encrypted phone), `obligations`, `alerts`, `reminders`,
`drafts`, `reports`, `sandbox_accounts`, `sandbox_transfers`, `pending_actions`, `audit_events`
(append-only, hash-chained, no foreign key so it survives data deletion), `conversations`, `chat_messages`.

## 8. API overview

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/login`, `/signup`, `/logout`, `GET /api/auth/me` (HttpOnly session cookie + CSRF header, or Bearer token for API clients) |
| AI Assistant | `POST /api/chat`, `POST /api/chat/stream` (SSE: `tool`, `delta`, `done`), `POST /api/feedback`, `GET /api/models` |
| Tools | `GET /api/tools`, `POST /api/tools/{name}` (same pipeline as the agent) |
| Data | `POST /api/data/upload`, `/paste`, `/entry`, `/entry/preview`; `GET /api/data/transactions` (`?ids=` for trace rows), `PATCH …/{id}`, `GET /api/data/invoices`, `/imports` |
| Insights | `GET /api/dashboard`, `/forecast`, `/alerts`, `/digest`; `POST /api/whatif`, `/alerts/{id}/{action}`; `GET/PATCH /api/settings` |
| Actions | `GET /api/actions/pending`, `POST /api/actions/{id}/confirm`, `/reject`; `GET /api/reminders`, `/drafts`, `/reports`, `/reports/{id}/download`, `/sandbox`, `/obligations`, `/compliance` |
| Audit | `GET /api/audit`, `/audit/verify`, `/oplog`, `/oplog/export?fmt=csv\|jsonl` |
| Privacy | `POST /api/privacy/delete`, `GET /api/privacy/export` |
| Market | `GET /api/market/prices` (any role; public data chosen by the business's district and type) |

Interactive OpenAPI docs are at `/api/docs` (disabled in production).

## 9. Security design (summary)

Full analysis: [SECURITY_ASSESSMENT.md](SECURITY_ASSESSMENT.md).

- **Tiers** 0–3 enforced in `security/permissions.py`, with roles owner (≤ 2), accountant (≤ 1) and viewer (0).
- **Money controls.** Human confirmation with a re-typed amount, per-transaction limit, daily cap including
  reservations, available balance net of pending reservations, 10-minute expiry, no replay, re-authorisation
  at execution time, and sandbox only.
- **Audit.** SHA-256 hash chain over canonical JSON, SQLite triggers blocking UPDATE and DELETE,
  `verify_chain` re-reading storage, and PII masked before storage.
- **Data protection.** PII masking before external LLMs, local-only mode, Fernet field encryption, deletion
  and export endpoints, and a PII-masked interaction dataset.
- **Prompt injection.** Uploaded rows are scanned and flagged. Untrusted strings are neutralised before
  reaching the model. A system-prompt data-not-instructions rule is in place. Tier-3 tools are registered so
  attempts get audited. Suspicious user messages disable Tier-2 tools for that turn.
- **Web.** bcrypt passwords with timing-equalised failures (no username enumeration), opaque tokens in an
  HttpOnly SameSite=Strict cookie (hashed at rest) with a double-submit CSRF header, lockout after 5 failures,
  rate limits, strict CSP, no `innerHTML`, `nosniff`, `X-Frame-Options: DENY`, HSTS over HTTPS, upload type
  and size limits, and XML-bomb-safe spreadsheet parsing (defusedxml). The launchers keep the site on this
  computer unless network sharing is chosen.
- **Responsible AI.** A deterministic refusal guardrail for fraud, fake documents, tax evasion, laundering and
  bribery in English, Bangla, Banglish and Chinese. Disclaimers on advisory output. Forecast bands and "illustrative / verify" labels
  everywhere.

## 10. Quality and evaluation

- **443 automated tests**, 90% line coverage, plus 19 interface tests (Node): finance math against textbook values, analysis against
  hand-computed fixtures, mocked HTTP for every provider, schema tests for every tool, the permission matrix,
  audit tampering, injection and guardrail cases, API, SSE, and end-to-end action flows. See
  [TEST_REPORT.md](TEST_REPORT.md).
- **Benchmark harness** with a 48-scenario golden set; ground truth always comes from the deterministic tools.
  See [benchmarks/results/summary.md](../benchmarks/results/summary.md).
- **Execution evidence**: a scripted 35-step run (35/35 pass) with exported operation logs. See
  [EXECUTION_EVIDENCE.md](EXECUTION_EVIDENCE.md).
