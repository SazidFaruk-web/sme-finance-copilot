# Test Report

```bash
python -m pytest --cov=sme_copilot --cov-report=term-missing   # Python: 443 tests
node --test tests/ui/*.test.mjs                                 # interface: 19 tests (Node 22.7+)
python -m sme_copilot.cli evidence                              # end-to-end: 35 steps
```

**443 Python tests: 442 pass, 1 skipped · 90% line coverage** ([coverage.txt](coverage.txt), 9,892 statements) ·
**19/19 interface tests pass** · **35/35 end-to-end evidence steps pass.** Run on 2026-10-19. The CLI entry point and
the evidence script are excluded from coverage; the evidence script is exercised by its own run, see
[EXECUTION_EVIDENCE.md](EXECUTION_EVIDENCE.md). The skipped test needs a live local model (`pytest -m slow`).

## Python test suites

| File | Tests | What it proves |
|---|---|---|
| `test_finance_math.py` | 20 | EMI (reducing 1 lakh @12%/12m = 8,884.88), flat EMI, inverse EMI, flat-rate effective APR ≈ 18%, fees in cost of credit, amortisation closes to zero, DSCR, runway, CV, BDT parsing (৳, Bangla digits, brackets) and lakh/intl formatting |
| `test_analysis.py` | 13 | Period resolution; summary, gross/net margin, break-even and margin of safety, AR/AP aging buckets and DSO, payment behaviour, cost drivers vs previous period, change explanation, Eid seasonality detection, lending metrics, all against hand-computed fixtures |
| `test_nl_entry.py` | 32 | Quick entries in English, Bangla and Banglish (amount, direction, category, channel, quantity, counterparty, relative and explicit dates), longest-keyword categorisation, day-first date parsing |
| `test_ingestion.py` | 23 | Ledger, bank statement with preamble, bKash statement (fees, failed rows, encrypted wallet numbers), invoices, XLSX, pasted text, re-import detection, duplicates, anomalies, injection flags, error reporting |
| `test_khata_photo.py` | 27 | Photo import of a handwritten sales book: request shape, Bangla digits, day-total checks, merging overlapping photos, injection handling and the API, with a fake vision provider |
| `test_record_resolver.py` | 18 | Matching typed records to existing customers, items and bills; fast path and review queue (no model) |
| `test_books.py` | 22 | Bookkeeping: customers and suppliers (baki khata), invoices, payments, repeating items |
| `test_stock.py` | 19 | Stock matching, movement signs, linking from records, reversal, status maths, API scoping |
| `test_providers.py` | 28 | Anthropic, OpenAI, Gemini, OpenAI-compatible and Ollama adapters against mocked vendor HTTP (tool calls, structured output, streaming with TTFT, retries vs no-retry on 401), schema inlining, JSON extraction, structured-output retry, emulated tool calling, router fallback, local-only blocking, per-request override, shipped `providers.yaml` validity |
| `test_pii.py` | 5 | Masking and restoring BD phones (+880), wallet/account numbers, NID, TIN, email and cards |
| `test_agent.py` | 26 | Language detection, EN/BN/Banglish answers with zero ungrounded numbers, data entry through chat, viewer denied, refusals without a model call, audit per turn, hallucinated number flagged, invalid tool args fed back and retried, blocked tool audited, untrusted data neutralised, PII masked for external providers |
| `test_language_zh.py` | 23 | Chinese detection (and not from a single character), the model told to answer in Simplified Chinese, Chinese refusals, 8 Chinese fraud/tax/laundering requests refused before any model call, 6 ordinary Chinese questions not refused, offline engine answers Chinese in English (never Bangla), unknown language codes rejected |
| `test_security.py` | 34 | Every tool has a valid tier and schema; role × tier matrix; Tier-2 limits (per-txn, daily cap, balance); blocked tools audited; unknown tool and bad args; **audit tamper detection** and DB triggers; bcrypt, lockout, token revocation; injection scanner positives and benign negatives; guardrail refusals vs legitimate questions |
| `test_security_books.py` | 16 | Bookkeeping security: confirmations and password step-up, sessions and CSRF, cross-business isolation, input and export hardening |
| `test_security_hardening.py` | 8 | Regression tests from the 2026-10-19 review: equal login timing for unknown users, an accountant can neither probe nor cancel the owner's payment, XML-bomb-safe spreadsheets, illustrative tools follow the mode (5 cases) |
| `test_forecast.py` | 19 | Exact projection arithmetic, first negative date and runway, √t band growth, recurring detection, what-if (delay, loan EMI 23,536.74, revenue drop, hiring), scenario validation, invoice-based scheduling, explicit obligations, alert dedupe and dismissal, compliance reminders flagged "verify", digest actions, routing of forecast questions in three languages |
| `test_financing.py` | 15 | Catalog schema and illustrative flags; DSCR-capped offers; hard-rule rejections explained; collateral and women-led rules; invoice-financing advance cap; flat-rate caution; ranking; every product classified; readiness components and tips; financing questions in three languages |
| `test_market.py` | 16 | Price drawer: ordered forecast ranges that widen with the horizon, trend following, baskets and district aliases, nearest fresh area (never a stale series), national fallback, garment note, no forecast far beyond the data, no download in local-only mode or with refresh off, HDX-only hosts (5 cases), broken download rejected and good one stored, endpoint needs login and serves every role, endpoint can be turned off |
| `test_actions.py` | 20 | Reminders, Bangla follow-up drafts, PDF report (hash verified), checklist, obligations feeding the forecast; **human-in-the-loop transfer** (mistyped amount 409, confirm, no replay), accountant cannot move or confirm money, limits and reservations, expiry 410, reject, supplier payment by name, no confirm tool, handler refuses outside confirmation, suspicious text disables money tools, operation-log export, privacy deletion |
| `test_pilot.py` | 18 | Guided tasks: idempotent records and stale previews, credit vs repayment, partial payments, answer revision, collections, loan terms with unknowns, seasonal loans, illustrative tools blocked for the pilot, stock tests, shortfall and paperwork hand-off, tenant/role validation, SMS opt-in, deduplication and retry rules, source changes, backups, encrypted attachments, the model cannot choose unapproved questions |
| `test_guided_home.py` | 7 | Guided Home: complete evidence, persistent reminders and offline help |
| `test_home_layout.py` | 9 | Onboarding and Home layout: registry validation, rule fallback, skip/simplified modes, business scoping |
| `test_api.py` | 17 | Auth required, security headers, chat roundtrip and conversation, unknown profile, fallback attempt recorded, SSE stream, tools endpoint permissions, upload type checks, entry preview, audited edits, viewer cannot read audit, feedback stored masked, login rate limit, dashboard payload, what-if and alert actions, number-style toggle |
| `test_benchmark_and_export.py` | 5 | Golden-set integrity (≥ 40 scenarios, 3 languages, real tools), metric helpers, offline benchmark run with outputs, valid-JSON compaction, fine-tune export selection rules |
| `test_seed_and_ui.py` | 3 | Deterministic seed with its story (duplicate, anomaly, injection row, cash dip), UI served with strict CSP and no `.innerHTML` |

## Interface test suites (Node)

| File | Tests | What it proves |
|---|---|---|
| `auth.test.mjs` | 5 | Every login/signup message exists in English and Bangla with no mixed language; validation; Unicode password length; errors mapped to friendly messages |
| `i18n-zh.test.mjs` | 5 | Chinese login/signup copy complete with no English left; lookups keep whitespace and leave user text alone; templated sentences; copy tables with functions; every dictionary entry contains Chinese |
| `guidance.test.mjs` | 8 | Home's one recommendation and Tasks ordering: cash risk first, reconciliation gaps, reminders, empty businesses, viewer permissions, localisation |
| `pilot.test.mjs` | 1 | Bangla numerals and grouping preserve a reviewable amount |

## Price forecast backtest

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

## End-to-end execution evidence

`python -m sme_copilot.cli evidence`: **35/35 steps pass**, with the operation log exported to
[docs/evidence/](evidence/). See [EXECUTION_EVIDENCE.md](EXECUTION_EVIDENCE.md).
