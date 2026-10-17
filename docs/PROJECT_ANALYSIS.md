# Project analysis

Reviewed on 17 October 2026. This is an assessment of the working tree, including the existing changes to seven demo seed files. Application code and those seed changes were left untouched.

## Overall assessment

SME Finance Copilot is a substantial functional prototype for Bangladesh SMEs. Its strongest design choice is the separation between language generation and deterministic financial tools. It already supports a broader bookkeeping workflow than the README's primary feature list suggests: customer and supplier ledgers, invoices, partial payments, recurring records, inventory, handwritten ledger transcription, signup, onboarding, and configurable home layouts.

The existing automated suite passes, but several important controls are inconsistent across entry points. In particular, confirmation is not atomic, an older transaction endpoint bypasses newer safeguards, and auxiliary LLM calls do not inherit the main agent's privacy handling. These issues should be fixed before treating the application as ready for production business records. Payment execution remains a sandbox feature.

The codebase contains 82 application Python files, approximately 13,785 application Python lines, 24 ORM tables, 73 HTTP route declarations, and 20 test files. The principal frontend module is 2,059 lines, approximately 170 KB.

## Architecture and data flow

| Layer | Main locations | Responsibility |
|---|---|---|
| Browser | `frontend/app.js`, `charts.js`, `styles.css` | No-build SPA, dashboards, chat streaming, bookkeeping, import review, confirmations, onboarding |
| HTTP API | `sme_copilot/api/` | FastAPI authentication, business scoping, role dependencies, uploads, reports, settings, actions |
| Agent | `sme_copilot/agent/` | Language detection, refusal rules, model/tool loop, permissions, confirmation proposals, numeric checks |
| Providers | `sme_copilot/llm_providers/` | Vendor adapters, OpenAI-compatible endpoints, local models, structured extraction, fallback, offline rules |
| Financial tools | `tools/analysis.py`, `finance_math.py`, `repo.py` | Cash position, profitability, break-even, aging, business metrics, loan costs, source-row traces |
| Data entry | `tools/ingestion.py`, `nl_entry.py`, `record_resolver.py`, `khata_photo.py` | CSV/Excel normalization, multilingual parsing, extracted-field arithmetic, photo review |
| Forecasting | `sme_copilot/forecasting/` | Historical baselines, dated invoices and obligations, scenarios, uncertainty bands, alerts and digest |
| Financing | `sme_copilot/financing_catalog/` | YAML eligibility rules, affordability, cost comparison, ranking and readiness checklist |
| Persistence | `models.py`, `db.py` | SQLAlchemy, default SQLite with WAL and foreign keys, encrypted identifier columns |
| Security and evidence | `security/`, `telemetry/`, `benchmarks/`, `demo/` | Sessions, CSRF, tiers, masking, audit chain, interaction datasets, evaluations and scripted demonstrations |

A normal chat request follows this path:

1. Resolve an authenticated user and their business; load that user's conversation history.
2. Apply deterministic refusal and injection checks.
3. Ask the configured provider to answer or propose tool calls.
4. Validate each tool's arguments and authorize its role/tier. Execute permitted tools or create a pending confirmation.
5. Return tool results to the model, then attach source traces, advisory disclaimers, numeric warnings and pending actions.
6. Save the conversation, append audit events and write a masked interaction record.

The main agent masks messages before external provider calls. Local profiles restrict their fallback chain to local providers. However, the record extraction helper independently invokes the global router; see finding 3.

Uploads normalize rows, preserve batch and source-row references, detect duplicates and anomalies, and scan for injection patterns. Photos follow a separate transcription and review path before the user imports their contents. Bookkeeping payments create matching cash transactions and invoice-payment records. Several direct API writes implement their own controls rather than passing through the agent executor, so shared domain services are especially important.

## Verification performed

The existing virtual environment initially lacked `rapidfuzz`, which is already declared in `requirements.txt`. Installing that dependency allowed collection and execution of the full default suite.

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=sme_copilot --cov-report=term-missing --cov-report=json:data/project-analysis-coverage.json -o cache_dir=data/project-analysis-pytest-cache
```

Result: **367 passed, 1 skipped, 5 deselected in 67.30 seconds**. Coverage was **91.84%, displayed as 92%**, across 8,518 executable statements. The default pytest configuration excludes tests marked `slow`; coverage also excludes the CLI and demo evidence runner.

Both frontend JavaScript files passed `node --check`. This checks syntax, not browser behavior or accessibility.

Additional isolated checks used temporary databases and FastAPI's TestClient. The external-provider check used `httpx.MockTransport`; no financial records or identifiers were sent to a real provider. These checks reproduced findings 1–6 below. They were exploratory checks, not additions to the repository's regression suite.

Docker execution was unavailable because the Docker daemon could not be reached. Container findings below are therefore based on source inspection. Live cloud providers, a live local model, PostgreSQL, and browser interactions were not validated. Existing committed model benchmark results were inspected, not rerun.

## Findings, ordered by priority

### 1. High: one sandbox confirmation can execute twice

Locations: `agent/executor.py:245`, `agent/executor.py:292`, `models.py:252`.

`confirm_pending()` reads a pending action without claiming or locking it. `run_handler()` commits the transfer before the pending action is marked confirmed, and the transfer's `pending_action_id` has no unique constraint. Two overlapping requests can both observe the pending state. A failure between the two commits also leaves an executed request eligible for replay.

Reproduction: preload the same pending action in two independent sessions, then confirm through each session. Both outcomes were `ok`; **two transfer rows referenced the same pending action**. This simulates overlapping request state without requiring nondeterministic thread timing.

Recommended change: claim the pending action through an atomic conditional update, execute the handler and finalize the action within one transaction, and enforce a unique transfer idempotency key at the database layer. Serialize account balance and reservation updates as well. This matters even with one server process because synchronous routes can run concurrently.

### 2. High: the legacy delete endpoint bypasses bookkeeping safeguards

Locations: `api/routes_data.py:162`, compared with `api/routes_books.py:446`.

The bookkeeping delete endpoint protects invoice-payment transactions, requires password reauthentication for large deletions, and retains an undo record. The older `/api/data/transactions/{id}` endpoint accepts manual transactions and does not apply those controls. Invoice payment transactions are created with `source="manual"`.

Reproduction as an accountant:

| Operation | Bookkeeping route | Legacy data route |
|---|---|---|
| Delete a BDT 100,000 manual transaction without a password | 403 | 200 |
| Delete the cash transaction backing an invoice payment | 409 | 200 |

After the second deletion, the invoice still showed BDT 1,000 paid while its matching cash transaction no longer existed. The non-FK payment reference permits that inconsistency to persist.

Recommended change: remove the duplicate implementation or delegate both routes to one transaction deletion service with identical authorization, payment protection, reauthentication, stock reversal, undo and audit behavior.

### 3. High: auxiliary extraction bypasses external-model PII masking

Locations: `tools/record_resolver.py:158`, `agent/tools_analysis.py:250`, compared with `agent/orchestrator.py:71`.

`_llm_extract()` calls the global router with the original text and no privacy transform. Masking currently happens in the main agent's caller, rather than at a boundary shared by all provider calls.

Reproduction: configure a mocked external OpenAI-compatible profile with `MASK_PII=true`, then send a non-fast-path record containing a phone number through `read_record()`. The captured HTTP request contained the **original unmasked phone number**.

The nested extraction also uses the global default profile rather than the profile selected for the outer chat request. A local chat selection therefore does not, by itself, guarantee that a nested extraction stays local when the global default is external. Global `LOCAL_ONLY_MODE=true` still blocks external profiles.

Recommended change: centralize text masking in the routing/provider boundary and propagate the requested profile and privacy policy into auxiliary calls. Preserve reversible placeholders where extracted identifiers are needed. Review the separate photo path explicitly, since text masking cannot remove identifiers embedded in an image.

### 4. High: an extracted credit sale is recorded as cash received

Locations: `tools/record_resolver.py:27`, `tools/record_resolver.py:113`, `agent/tools_analysis.py:244`.

The extraction schema recognizes `payment_method="credit"`, but channel normalization maps it to cash. The transaction handler then creates an inflow and does not create a receivable invoice. The regex fast path can also match a sale without preserving a credit qualifier.

Reproduction: mock a valid extraction for two shirts at BDT 500 each, explicitly marked as sold on credit. Posting through `/api/data/entry` recorded **BDT 1,000 money in, channel cash, with zero invoices**.

This can inflate available cash and distort cash-based reports and forecasts.

Recommended change: represent settlement separately from sale/purchase type. Create an unpaid invoice for a credit sale and a cash transaction when collection occurs, or require the user to resolve the unsupported credit entry before saving it.

### 5. High: privacy deletion does not delete all business data

Locations: `api/routes_actions.py:240`, `api/routes_actions.py:246`, `api/routes_actions.py:290`.

The deletion table list omits `Item`. Stock movements depend on items, so both remain after deletion. The business and user rows are retained, with multiple profile fields left populated. The export endpoint includes only selected business fields, transactions and invoices, omitting inventory and other substantial record types.

Reproduction: create an item and stock adjustment, then complete the owner/password/typed-phrase deletion flow. It returned 200, but **one item and one stock movement remained**.

Recommended change: define a complete data inventory, delete inventory and dependent records, anonymize retained identity fields consistently, and make the export cover the supported record types. Explicitly describe audit retention separately; masking does not remove all names and descriptive text.

### 6. Medium: viewers can reject pending actions

Locations: `api/routes_actions.py:95`, `agent/executor.py:300`.

The rejection endpoint requires authentication but no write tier. Its helper checks the business and pending status but does not authorize the action. Rejection is committed through the audit writer.

Reproduction: a viewer rejected the owner's pending sandbox transfer; the endpoint returned 200 and the stored status became `rejected`. This contradicts the read-only role contract.

Recommended change: authorize rejection according to the pending action's tier, with explicit rules for who may cancel another user's proposal.

### 7. High for the advertised Docker demo: seed writes target a root-owned directory

Locations: `Dockerfile:14`, `Dockerfile:18`, `docker-compose.yml:23`, `demo/seed.py:274`, `cli.py:32`.

The image copies seed files as root, grants the application user ownership only of `/app/data`, then runs as that user. Compose invokes `demo`, which loads the seed with `write=True` and rewrites `/app/seed/demo/*`. With the declared image permissions, those writes are expected to fail.

Separately, the compose command resets the default SQLite database on every container start. Once the permission problem is resolved, restarting this demo configuration discards data entered since the previous seed. The source comment acknowledges the reset, but the persistent volume can still suggest durability to a reader following the deployment instructions.

Recommended change: seed from memory without rewriting packaged files, or write generated examples under the data directory. Make destructive demo reset an explicit operation and use `serve` for persistent deployments. Validate the built image when Docker is available.

### 8. Medium: persistence and scale assumptions need an explicit operating boundary

Locations: `db.py:48`, `security/audit.py:48`, `security/http.py:39`, `api/routes_core.py:207`, `requirements.txt`.

Schema initialization uses `create_all()` with no migration history. It creates missing tables but does not provide upgrades for changed columns or constraints. PostgreSQL is advertised as a URL change, but the requirements do not include a PostgreSQL driver, and append-only triggers are installed only for SQLite.

Rate limits, audit serialization, caches and background scheduling are process-local. The SSE endpoint creates a thread per chat and has no disconnect-driven cancellation. A timed-out record extraction future also continues running in its single-worker pool, potentially delaying later entries.

Recommended change: add versioned migrations, document and test supported database backends, and keep an explicit single-instance operating model until shared rate limiting, scheduling, database concurrency controls and bounded/cancellable model work are implemented.

## Financial and AI design assessment

The financial implementation is deliberately transparent. Loan math, profitability, affordability and scenarios are code-driven, with explainability traces and hand-computed test fixtures. Financing products and compliance rules are clearly marked illustrative or unverified. These are useful foundations.

Important practical limits remain:

- Profitability treats inventory purchases as COGS. This is a documented cash-basis approximation; the existence of stock quantities does not provide inventory valuation or accrual accounting.
- Money calculations use floats with rounding and SQL `NUMERIC` storage configured to return floats. Consistent decimal arithmetic would make rounding policy easier to enforce as bookkeeping expands.
- Forecast invoice-collection history comes from aggregate `Invoice.amount_paid` and the final `paid_date`, rather than dated `InvoicePayment` rows. Partial collections and payments spread across the lookback boundary can therefore distort the baseline and collection lag.
- Stock's recent sales use movement creation timestamps, rather than transaction dates. Entering old transactions today can make historical sales appear recent in days-of-stock calculations.
- The forecast's nominal 80% range is a volatility heuristic. No rolling backtest establishing 80% empirical coverage was found.
- Numeric grounding tests number presence, rounding and scaling, rather than whether a number supports the sentence's actual claim. It ignores several small integers and common constants. It is a warning mechanism, not a proof of correctness.
- Benchmark ground truth calls the same financial tools used by the agent. This measures tool selection and answer fidelity; independent financial correctness still depends on separate mathematical and accounting fixtures.

The committed final local-model golden report records 48 scenarios, 95% tool success, 93% numeric accuracy and a 6% numeric hallucination signal. Its stress report records 44 scenarios and a 9% hallucination signal. These are recorded results from the repository, not fresh measurements from this review. The baseline rules engine's strong score is useful for repeatability but should not be interpreted as general language understanding.

## Frontend, maintainability and documentation

The frontend avoids dynamic HTML insertion, uses an explicit DOM helper and has no CDN dependency. Browser authentication now uses HttpOnly session cookies, strict SameSite settings and a CSRF token for writes; bearer tokens remain available for API clients. This is stronger than the older security document's description of sessionStorage-only bearer authentication.

Most frontend behavior lives in one module, with repeated request/render patterns and both simplified and full workflows. Splitting it by feature would make state management and authorization-dependent UI behavior easier to review. Existing frontend tests mostly check static serving and source properties; they do not establish that login, invoice payment, import review, chat streaming and confirmation work in a browser. Bangla names and descriptions also need export verification because PDFs use built-in Helvetica fonts.

Documentation has drifted from implementation: the README reports 219 tests and 91% coverage, while this run found 367 passing default tests and 92% coverage. The security assessment also predates cookies, signup and password step-up. Environment examples omit settings such as `COOKIE_SECURE`, `ALLOW_SIGNUP`, `STEP_UP_AMOUNT` and `REMINDER_DAILY_LIMIT`. The README's PostgreSQL and stateless deployment language needs qualification.

Dependencies have minimum versions but no reproducible lock or hashes. No tracked CI workflow was found. A useful baseline would run the default Python suite, JavaScript syntax checks and dependency checks, then build and smoke-test the actual non-root container.

## Recommended implementation order

1. Make confirmations and account updates atomic and idempotent; add a regression reproducing two overlapping sessions.
2. Consolidate transaction mutation logic and close the legacy deletion bypass; test every supported route against the same invariants.
3. Put privacy policy at the shared model boundary and propagate it through nested extraction.
4. Fix credit settlement semantics and cover credit sales, purchases and later payments with accounting invariants.
5. Complete deletion/export coverage and apply pending-action authorization consistently.
6. Repair and smoke-test Docker startup, separate reset from serving, and introduce schema migrations.
7. Add browser workflow tests, forecast backtests and payment-history fixtures, then update documentation and split the largest modules.

The application has enough implemented functionality and test infrastructure to support focused hardening. The highest-value next work is to enforce the existing contracts consistently across all entry points.
