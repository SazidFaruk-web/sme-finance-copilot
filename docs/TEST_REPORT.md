# Test Report

```bash
python -m pytest -m "not slow" -o addopts= -q --cov=sme_copilot --cov-report=term-missing
node --test tests/ui/*.test.mjs
# With the isolated review server running on port 8002:
node tests/browser/voice.mjs
```

Verified on **2026-10-19** after the update fixes: **487 Python tests passed, 1 skipped,
5 deselected; 90% line coverage** ([coverage.txt](coverage.txt), 10,575 statements).
**22/22 interface tests passed.** The focused browser check passed at a 360px viewport:
speech stays editable, no request is made before Send, Send makes one request, the new
voice module is cached, and the app reloads offline without JavaScript errors.

Cloud model calls and shared-model failures were mocked in regression tests; these
results do not establish live model availability or SMS delivery. The CLI entry point
and evidence script are excluded from coverage. The five slow tests were deselected;
the skipped test requires a live local model. The existing CLI execution evidence and
benchmark results below are historical baselines, not rerun for these fixes.

## Python test suites

| File | What it proves |
|---|---|
| `test_finance_math.py` | EMI (reducing 1 lakh @12%/12m = 8,884.88), flat EMI, inverse EMI, flat-rate effective APR ≈ 18%, fees in cost of credit, amortisation closes to zero, DSCR, runway, CV, BDT parsing (৳, Bangla digits, brackets) and lakh/intl formatting |
| `test_analysis.py` | Period resolution; summary, gross/net margin, break-even and margin of safety, AR/AP aging buckets and DSO, payment behaviour, cost drivers vs previous period, change explanation, Eid seasonality detection, lending metrics, all against hand-computed fixtures |
| `test_nl_entry.py` | Quick entries in English, Bangla and Banglish (amount, direction, category, channel, quantity, counterparty, relative and explicit dates), longest-keyword categorisation, day-first date parsing |
| `test_ingestion.py` | Ledger, bank statement with preamble, bKash statement (fees, failed rows, encrypted wallet numbers), invoices, XLSX, pasted text, re-import detection, duplicates, anomalies, injection flags, error reporting |
| `test_khata_photo.py` | Photo import of a handwritten sales book: request shape, Bangla digits, day-total checks, merging overlapping photos, injection handling and the API, with a fake vision provider |
| `test_record_resolver.py` | Matching typed records to existing customers, items and bills; fast path and review queue (no model) |
| `test_books.py` | Bookkeeping: customers and suppliers (baki khata), invoices, payments, repeating items |
| `test_stock.py` | Stock matching, movement signs, linking from records, reversal, status maths, API scoping |
| `test_providers.py` | Anthropic, OpenAI, Gemini, OpenAI-compatible and Ollama adapters against mocked vendor HTTP (tool calls, structured output, streaming with TTFT, retries vs no-retry on 401), schema inlining, JSON extraction, structured-output retry, emulated tool calling, router fallback, local-only blocking, per-request override, shipped `providers.yaml` validity |
| `test_pii.py` | Masking and restoring BD phones (+880), wallet/account numbers, NID, TIN, email and cards |
| `test_agent.py` | Language detection, EN/BN/Banglish answers with zero ungrounded numbers, data entry through chat, viewer denied, refusals without a model call, audit per turn, hallucinated number flagged, invalid tool args fed back and retried, blocked tool audited, untrusted data neutralised, PII masked for external providers |
| `test_language_zh.py` | Chinese detection (and not from a single character), the model told to answer in Simplified Chinese, Chinese refusals, 8 Chinese fraud/tax/laundering requests refused before any model call, 6 ordinary Chinese questions not refused, offline engine answers Chinese in English (never Bangla), unknown language codes rejected |
| `test_security.py` | Every tool has a valid tier and schema; role × tier matrix; Tier-2 limits (per-txn, daily cap, balance); blocked tools audited; unknown tool and bad args; **audit tamper detection** and DB triggers; bcrypt, lockout, token revocation; injection scanner positives and benign negatives; guardrail refusals vs legitimate questions |
| `test_security_books.py` | Bookkeeping security: confirmations and password step-up, sessions and CSRF, cross-business isolation, input and export hardening |
| `test_security_hardening.py` | Regression tests from the 2026-10-19 review: equal login timing for unknown users, an accountant can neither probe nor cancel the owner's payment, XML-bomb-safe spreadsheets, illustrative tools follow the mode (5 cases) |
| `test_forecast.py` | Exact projection arithmetic, first negative date and runway, √t band growth, recurring detection, what-if (delay, loan EMI 23,536.74, revenue drop, hiring), scenario validation, invoice-based scheduling, explicit obligations, alert dedupe and dismissal, compliance reminders flagged "verify", digest actions, routing of forecast questions in three languages |
| `test_financing.py` | Catalog schema and illustrative flags; DSCR-capped offers; hard-rule rejections explained; collateral and women-led rules; invoice-financing advance cap; flat-rate caution; ranking; every product classified; readiness components and tips; financing questions in three languages |
| `test_market.py` | Price drawer: ordered forecast ranges that widen with the horizon, trend following, baskets and district aliases, nearest fresh area (never a stale series), national fallback, garment note, no forecast far beyond the data, no download in local-only mode or with refresh off, HDX-only hosts (5 cases), broken download rejected and good one stored, endpoint needs login and serves every role, endpoint can be turned off |
| `test_actions.py` | Reminders, Bangla follow-up drafts, PDF report (hash verified), checklist, obligations feeding the forecast; **human-in-the-loop transfer** (mistyped amount 409, confirm, no replay), accountant cannot move or confirm money, limits and reservations, expiry 410, reject, supplier payment by name, no confirm tool, handler refuses outside confirmation, suspicious text disables money tools, operation-log export, privacy deletion |
| `test_pilot.py` | Guided tasks: idempotent records and stale previews, credit vs repayment, partial payments, answer revision, collections, loan terms with unknowns, seasonal loans, illustrative tools blocked for the pilot, stock tests, shortfall and paperwork hand-off, tenant/role validation, SMS opt-in, deduplication and retry rules, source changes, backups, encrypted attachments, the model cannot choose unapproved questions |
| `test_guided_home.py` | Guided Home: complete evidence, persistent reminders and offline help |
| `test_home_layout.py` | Onboarding and Home layout: registry validation, rule fallback, skip/simplified modes, business scoping |
| `test_api.py` | Auth required, security headers, chat roundtrip and conversation, unknown profile, fallback attempt recorded, SSE stream, tools endpoint permissions, upload type checks, entry preview, audited edits, viewer cannot read audit, feedback stored masked, login rate limit, dashboard payload, what-if and alert actions, number-style toggle |
| `test_benchmark_and_export.py` | Golden-set integrity (≥ 40 scenarios, 3 languages, real tools), metric helpers, offline benchmark run with outputs, valid-JSON compaction, fine-tune export selection rules |
| `test_seed_and_ui.py` | Deterministic seed with its story (duplicate, anomaly, injection row, cash dip), UI served with strict CSP and no `.innerHTML` |
| `test_update_regressions.py` | Shared-profile compatibility and offline fallback; date-safe payment amounts and ambiguous-entry rejection; direct-helper PII policy; matching action claims to their tool and state; sales-only Home growth |

## Interface test suites (Node)

| File | Tests | What it proves |
|---|---|---|
| `auth.test.mjs` | 5 | Every login/signup message exists in English and Bangla with no mixed language; validation; Unicode password length; errors mapped to friendly messages |
| `i18n-zh.test.mjs` | 5 | Chinese login/signup copy complete with no English left; lookups keep whitespace and leave user text alone; templated sentences; copy tables with functions; every dictionary entry contains Chinese |
| `guidance.test.mjs` | 8 | Home's one recommendation and Tasks ordering: cash risk first, reconciliation gaps, reminders, empty businesses, viewer permissions, localisation |
| `pilot.test.mjs` | 1 | Bangla numerals and grouping preserve a reviewable amount |
| `voice.test.mjs` | 3 | Speech preserves typed input, never submits, handles recognition errors, and leaves typing available without speech support |

## Price forecast backtest (historical baseline)

`python scripts/backtest_market.py` hides the last 3 months of 170 real WFP market/item series and forecasts them:

| Engine | Median abs. error | Direction right (moves > 2%) | 10-90% range held the real price |
|---|---|---|---|
| No change | 1.98% | n/a | n/a |
| Statistical | 3.19% | 63.5% | 78.2% |
| Chronos-Bolt-small | 2.31% | 57.6% | 79.4% |

## Model benchmark (offline baseline)

`python -m sme_copilot.cli bench --profiles rules-offline` on the 48-scenario golden set
([results](../benchmarks/results/summary.md), [chart](../benchmarks/results/comparison.png)):

| profile | scenarios | latency p50 (ms) | tool-call success | numeric accuracy | financing match | hallucination rate | refusal correct | safety pass | BN/Banglish language match |
|---|---|---|---|---|---|---|---|---|---|
| rules-offline | 48 | 44 | 100% | 100% | 100% | 0% | 100% | 100% | 96% |

Cloud and local LLM profiles are run the same way once API keys or an Ollama model are available, for example
`--profiles rules-offline,claude-sonnet,openai-mini,gemini-flash,local-qwen7b`. Profiles without keys are
skipped and reported, never silently replaced (fallback is disabled in benchmarks).

## End-to-end execution evidence (historical baseline)

`python -m sme_copilot.cli evidence`: **35/35 steps pass**, with the operation log exported to
[docs/evidence/](evidence/). See [EXECUTION_EVIDENCE.md](EXECUTION_EVIDENCE.md).
