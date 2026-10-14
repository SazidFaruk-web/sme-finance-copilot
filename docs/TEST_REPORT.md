# Test Report

```bash
python -m pytest --cov=sme_copilot --cov-report=term-missing
```

**219 tests pass · 91% line coverage** ([coverage.txt](coverage.txt)). The CLI entry point and the
evidence script are excluded from coverage; the evidence script is exercised by its own run, see
[EXECUTION_EVIDENCE.md](EXECUTION_EVIDENCE.md).

## Test suites

| File | Tests | What it proves |
|---|---|---|
| `test_finance_math.py` | 20 | EMI (reducing 1 lakh @12%/12m = 8,884.88), flat EMI, inverse EMI, flat-rate effective APR ≈ 18%, fees in cost of credit, amortisation closes to zero, DSCR, runway, CV, BDT parsing (৳, Bangla digits, brackets) and lakh/intl formatting |
| `test_analysis.py` | 11 | Period resolution; summary, gross/net margin, break-even and margin of safety, AR/AP aging buckets and DSO, payment behaviour, cost drivers vs previous period, change explanation, Eid seasonality detection, lending metrics, all against hand-computed fixtures |
| `test_nl_entry.py` | 23 | Quick entries in English, Bangla and Banglish (amount, direction, category, channel, quantity, counterparty, relative and explicit dates), longest-keyword categorisation, day-first date parsing |
| `test_ingestion.py` | 13 | Ledger, bank statement with preamble, bKash statement (fees, failed rows, encrypted wallet numbers), invoices, XLSX, pasted text, re-import detection, duplicates, anomalies, injection flags, error reporting |
| `test_providers.py` | 21 | Anthropic, OpenAI, Gemini, OpenAI-compatible and Ollama adapters against mocked vendor HTTP (tool calls, structured output, streaming with TTFT, retries vs no-retry on 401), schema inlining, JSON extraction, structured-output retry, emulated tool calling, router fallback, local-only blocking, per-request override, shipped `providers.yaml` validity |
| `test_pii.py` | 5 | Masking and restoring BD phones (+880), wallet/account numbers, NID, TIN, email and cards |
| `test_agent.py` | 19 | Language detection, EN/BN/Banglish answers with zero ungrounded numbers, data entry through chat, viewer denied, refusals without a model call, audit per turn, hallucinated number flagged, invalid tool args fed back and retried, blocked tool audited, untrusted data neutralised before the model, PII masked for external providers |
| `test_security.py` | 30 | Every tool has a valid tier and schema; role × tier matrix; Tier-2 limits (per-txn, daily cap, balance); blocked tools audited; unknown tool and bad args; **audit tamper detection** and DB triggers; bcrypt, lockout, token revocation; injection scanner positives and benign negatives; guardrail refusals vs legitimate questions |
| `test_forecast.py` | 19 | Exact projection arithmetic, first negative date and runway, √t band growth, recurring detection, what-if (delay, loan EMI 23,536.74, revenue drop, hiring), scenario validation, invoice-based scheduling, explicit obligations, alert dedupe and dismissal, compliance reminders flagged "verify", digest actions, routing of forecast questions in three languages |
| `test_financing.py` | 15 | Catalog schema and illustrative flags; DSCR-capped offers; hard-rule rejections explained; collateral and women-led rules; invoice-financing advance cap; flat-rate caution; ranking; every product classified; readiness components and tips; financing questions in three languages |
| `test_actions.py` | 19 | Reminders, Bangla follow-up drafts, PDF report (hash verified), checklist, obligations feeding the forecast; **human-in-the-loop transfer** (mistyped amount 409, confirm, no replay), accountant cannot move or confirm money, limits and reservations, expiry 410, reject, supplier payment by name, no confirm tool, handler refuses outside confirmation, suspicious text disables money tools, operation-log export, privacy deletion |
| `test_api.py` | 16 | Auth required, security headers, chat roundtrip and conversation, unknown profile, fallback attempt recorded, SSE stream, tools endpoint permissions, upload type checks, entry preview, audited edits, viewer cannot read audit, feedback stored masked, login rate limit, dashboard payload, what-if and alert actions, number-style toggle |
| `test_benchmark_and_export.py` | 5 | Golden-set integrity (≥ 40 scenarios, 3 languages, real tools), metric helpers, offline benchmark run with outputs, valid-JSON compaction, fine-tune export selection rules |
| `test_seed_and_ui.py` | 3 | Deterministic seed with its story (duplicate, anomaly, injection row, cash dip), UI served with strict CSP and no `.innerHTML` |

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

`python -m sme_copilot.cli evidence`: **33/33 steps pass**, with the operation log exported to
[docs/evidence/](evidence/). See [EXECUTION_EVIDENCE.md](EXECUTION_EVIDENCE.md).
