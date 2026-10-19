# Security review — 19 October 2026

Reviewed commit `3775064` with a clean application working tree. **Seven application vulnerabilities were reproduced in isolated databases.** Two are high priority because they bypass controls protecting real financial records. There is also an optional Docker deployment exposure and an outdated package installer. All findings below remain **open**; this review does not change application behavior.

The previous security assessment describes intended controls. Its statements about payment permissions, deletion protection, read-only viewers, and replay prevention need the qualifications in this review.

## Scope and evidence

- Reviewed FastAPI authentication, cookies/CSRF, roles, business scoping, record mutations, confirmation execution, uploads/downloads, telemetry, frontend storage/rendering, launch scripts and Docker configuration.
- Ran the existing security, bookkeeping security, security hardening, PII, actions, pilot and API suites: **118 passed**.
- Ran seven bounded vulnerability probes: **7 reproduced successfully**. These tests assert vulnerable behavior, not secure acceptance criteria. All writes used temporary test databases and synthetic data. No real payment, SMS or external model call was made.
- Audited **56 installed Python distributions** with `pip-audit`. Six distinct advisories were reported for `pip==25.0.1`; raw output contained twelve entries because of duplicates. No other installed distribution was flagged in this scan.
- A limited tracked-file scan found no private-key blocks or matching common cloud/GitHub token patterns. `.env` is untracked. This is not a complete secrets/history audit.
- No TCP listeners on ports 8000, 8002 or 11434 were observed during the review. Docker exposure below is a configuration finding, not proof of a currently exposed server.

Run the deliberately separate audit probes from the repository root:

```powershell
.venv/Scripts/python.exe -m pytest -p tests.conftest docs/security-review/probes_2026_10_19.py -o addopts= -q
```

The probe filename intentionally does not match ordinary pytest discovery. After fixing a finding, reverse its vulnerable assertions into secure expectations and add them to the normal regression suite. Local raw audit output is under ignored `data/security-review/`.

## Application findings

### SEC-01 — High: quick entry bypasses invoice-payment authorization and password checks

**Code:** `sme_copilot/agent/tools_analysis.py:242`, compared with `sme_copilot/api/routes_books.py:279`.

The normal invoice-payment endpoint requires an owner and a password for amounts at or above the configured threshold. The `add_transaction` tool is available to accountants. Its customer-payment branch directly calls `apply_payment` when the caller supplies `confirmed=true`, without either check.

**Reproduced:** An accountant's attempt to record a 60,000 taka payment through `/api/books/invoices/{id}/payments` returned 403. An owner's password-less request also returned 403. The accountant then posted `Received 60000 from Audit Customer` with `confirmed=true` to `/api/data/entry`, received 200, and changed the invoice's amount paid to 60,000. This changes real bookkeeping records; it does not transfer bank funds.

**Fix:** Put invoice-payment authorization and step-up checks in a shared mutation service used by every entry path. A model-supplied boolean must not substitute for authenticated owner confirmation. Reject lower-role writes before creating either a payment or transaction.

### SEC-02 — High: alternate deletion endpoint bypasses protection and corrupts payment records

**Code:** `sme_copilot/api/routes_data.py:162`, compared with `sme_copilot/api/routes_books.py:446`.

`DELETE /api/data/transactions/{id}` only checks business, tier and source (`manual`/`nl`). It has no password threshold, invoice-payment guard, time limit for undo, or restorable trash. The main bookkeeping deletion route has those payment/step-up protections.

**Reproduced:** The main route refused deletion of an invoice-payment cash row with 409. The alternate route returned 200, deleted that cash row, and left the invoice marked 60,000 taka paid and its `InvoicePayment` pointing to the missing transaction. A separate 60,000 taka manual record required a password on the main route but was deleted without one on the alternate route. An accountant also meets the alternate route's tier requirement.

**Impact:** Financial reports and customer balances disagree; protected records can be removed through a less protected route. The dangling integer reference can also collide with a later reused SQLite transaction ID.

**Fix:** Remove or delegate the alternate route to a single guarded deletion service. Keep invoice-payment cash rows protected and use an explicit reversal workflow when correcting a payment. Preserve recovery and audit behavior consistently.

### SEC-03 — Medium: overlapping confirmations execute a pending action more than once

**Code:** `sme_copilot/agent/executor.py:254`, `sme_copilot/agent/tools_actions.py:327`, `sme_copilot/models.py:252`.

Confirmation reads `status == pending`, executes and commits the handler, then changes the pending status. There is no atomic claim of the pending action and no uniqueness constraint on `SandboxTransfer.pending_action_id`.

**Reproduced:** Two independent sessions read the same pending action before either completes. Both confirmations then returned `ok`, producing two transfer rows for the same pending-action ID. This models an overlapping-request interleaving deterministically; the review did not perform a live HTTP load attack. Existing replay tests cover a later sequential retry, which does not cover this window.

**Impact:** Duplicate sandbox transfers and ledger records. Transfers are simulated today, so this is not evidence of duplicate real bank transfers.

**Fix:** Atomically change pending to executing with a conditional update before side effects; execute and finalize in one transaction; enforce a unique idempotency key on the resulting effect. Serialize account balance/limit checks as needed. Concurrent confirmations must return the existing result or a conflict.

### SEC-04 — Medium: a read-only viewer can reject an owner's pending action

**Code:** `sme_copilot/api/routes_actions.py:98`, `sme_copilot/agent/executor.py:317`.

The reject endpoint requires only authentication. Its handler checks business and status but not role or action tier.

**Reproduced:** An owner prepared a 1,000 taka sandbox transfer. A viewer in the same business posted to `/api/actions/{id}/reject`, received 200, and changed the request to rejected. Pending action IDs are available to that viewer through the pending list.

**Fix:** Enforce rejection permissions server-side, including owner-only rejection of Tier-2 actions. Read-only users must not change workflow state.

### SEC-05 — Medium: passwords are silently truncated to 72 UTF-8 bytes

**Code:** `sme_copilot/security/auth.py:24` and `:31`; request schemas accept up to 200 characters.

Both hashing and verification use `password.encode('utf-8')[:72]`. Distinct accepted passwords sharing that prefix authenticate as the same password. Multibyte Bangla text reaches the byte boundary sooner than ASCII.

**Reproduced:** A password with 72 ASCII prefix characters and a real suffix authenticated with a different suffix. The same happened after a prefix of 24 three-byte Bangla characters. An attacker still needs the correct prefix; this is not an arbitrary-password login bypass.

**Fix:** Use a password-hashing scheme supporting the full accepted input, such as Argon2id, with explicit hash versioning and migration on successful legacy login. If retaining raw bcrypt temporarily, reject overlong UTF-8 inputs explicitly and plan migration for existing accounts instead of silently changing their verification semantics.

### SEC-06 — Medium: feedback can overwrite another business's training correction

**Code:** `sme_copilot/api/routes_core.py:208`, `sme_copilot/telemetry/interactions.py:57`, `sme_copilot/telemetry/export.py`.

Feedback accepts an arbitrary interaction ID without checking that it belongs to the caller. Feedback records lack business/user ownership; the export process uses the latest feedback for an ID and treats its correction as the training answer.

**Reproduced:** Business A created a chat turn. A viewer belonging to business B submitted a correction using A's interaction ID. The endpoint returned 200 and the training export included the injected correction as the target answer.

**Precondition:** The other business's interaction ID must be known; this review did not find a cross-business endpoint exposing those IDs or demonstrate guessing them. The reproduced impact is training-data integrity, not disclosure of another owner's records.

**Fix:** Resolve interaction ownership through its stored conversation/user and business before accepting feedback. Scope stored feedback and export joins by that ownership, reject nonexistent IDs, and retain provenance and review status for training corrections.

### SEC-07 — Low: non-finite confirmation amount bypasses amount retyping

**Code:** `sme_copilot/api/schemas.py:59`, `sme_copilot/agent/executor.py:283`.

`confirm_amount` accepts the string `NaN` as a float. Comparing `abs(NaN - expected) > 0.005` is false, so the mismatch check is skipped.

**Reproduced:** An authenticated owner confirmed a 1,000 taka pending transfer by sending `{"confirm_amount":"NaN"}`. The response was 200 and the action executed.

**Scope:** This bypasses amount retyping only. Owner authorization and the password requirement for larger transfers still apply.

**Fix:** Reject non-finite values in the schema and confirmation service; validate positive finite amounts before comparison, preferably with decimal monetary values.

## Deployment and dependencies

### SEC-08 — Medium, conditional: optional Docker LLM publishes an unauthenticated API on all host interfaces

**Code:** `docker-compose.yml`, `ollama.ports`, mapping `11434:11434`.

The website mapping is explicitly loopback-bound, but enabling the `local-llm` profile publishes Ollama on all host interfaces. Its local API requires no authentication. Anyone who can reach that host port can bypass the website's authentication and rate limits to use the model server. This is conditional on enabling the profile and network/firewall reachability. The separate Windows launcher uses loopback; this review did not observe a running model listener. [Ollama authentication documentation](https://docs.ollama.com/api/authentication)

**Fix:** Remove host publishing when only the app container needs access, or bind `127.0.0.1:11434:11434`. A shared remote deployment needs authenticated access, TLS, request limits and an explicit network allow-list.

### DEP-01 — Installed pip has known installation-time advisories

Installed version: `25.0.1`. Interpreter: Python `3.12.10`. Deduplicated scanner results:

| Advisory | Fixed pip version reported |
|---|---|
| CVE-2025-8869 | 25.3 |
| CVE-2026-1703 | 26.0 |
| CVE-2026-3219 | 26.1 |
| CVE-2026-6357 | 26.1 |
| CVE-2026-8643 | 26.1.2 |
| CVE-2026-13346 | 26.2 |

These require package-installation/download conditions, not normal app requests. CVE-2025-8869's vulnerable fallback is not used on this Python version with PEP 706 support. The other entries need their own malicious archive/index conditions; no package-install exploit was attempted. Upgrade the project installer to at least 26.2 (26.2.1 is published), then rerun the audit. [pip release notes](https://pip.pypa.io/en/stable/news/), [wheel path traversal advisory](https://github.com/advisories/GHSA-6vgw-5pg2-w6jp), [entry-point advisory](https://github.com/advisories/GHSA-wf93-45jw-7689), [index URL advisory](https://github.com/advisories/GHSA-qwm4-qh6w-59xr)

No other installed Python distribution was flagged by this advisory snapshot. Optional forecast/model environments, container OS packages and browser components were not dependency-audited. The scanner ran in a temporary tool environment; the project environment was not upgraded.

## Additional hardening to validate

- Upload size checks happen after multipart parsing. CSV parsing pads every row to the largest width, and Excel parsing has no explicit expanded archive/cell limit. Add ingress body limits, row/column/cell budgets and archive expansion limits. XML entity protection does not impose those resource limits. No exhaustion attack was run.
- Each streaming chat creates a daemon thread with no global/per-owner concurrency cap or cancellation of work on disconnect. Request-rate limits alone do not bound simultaneous model jobs. Test bounded queues and cancellation with a fake slow provider before load testing a shared model.
- Login lockout exists, but password rechecks on confirmation/deletion do not share that account lockout. Add an account-scoped limiter for step-up verification.

## Remediation order and limits

1. Fix SEC-01 and SEC-02 together through shared bookkeeping authorization/mutation services.
2. Fix SEC-03, SEC-04 and SEC-07 in the action state machine, including concurrent confirmation tests.
3. Migrate password handling, scope feedback ownership, close the optional model port and update pip.
4. Add bounded resource tests and rerun the full application/security suites after fixes.

Existing tests passed for CSRF, authentication/session revocation, several business-isolation checks, blocked money tools, audited operations and other covered controls. Passing those tests does not clear the newly reproduced paths. This was a source review and isolated local test exercise, not an independent penetration test of a deployed production system. No live cloud model, SMS provider, reverse proxy, firewall, TLS deployment or complete Git history was assessed.
