# Assumptions

Decisions taken without explicit confirmation. Each one is easy to revisit.

## Environment and stack
1. **No cloud LLM API keys were available while building.** I tested every cloud adapter (Anthropic, OpenAI,
   Gemini, OpenAI-compatible) against mocked HTTP that reproduces each vendor's documented wire format. Local
   models were run live through llama.cpp (see 36-40). Run `python -m sme_copilot.cli models` and the benchmark
   with a real key to confirm the cloud path.
2. **Offline "rules" provider.** A deterministic intent engine implements the same
   `LLMProvider` interface, so the whole agent loop (tool selection → permission check →
   execution → answer) runs with no model. It is the last link of every fallback chain and the benchmark
   baseline, and it answers (clearly labelled as a fallback) when the chosen model is unavailable.
3. **Raw `httpx` instead of vendor SDKs.** This keeps the install small, puts all five
   vendors behind one transport that tests can mock, and avoids SDK version drift.
4. **Python 3.11+.** I developed on 3.14; the Docker image uses 3.12.
5. **No frontend build step.** The UI is plain HTML/JS with hand-written SVG charts, so it
   works offline (no CDN) and needs no Node toolchain.
6. **SQLite by default.** SQLAlchemy keeps Postgres one `DATABASE_URL` change away.

## Pricing and model names
7. Model IDs for OpenAI, Gemini, Groq, OpenRouter, DeepSeek and the local models in
   `config/providers.yaml` are reasonable defaults that you can edit. Claude IDs are
   `claude-sonnet-5-5` / `claude-haiku-5-5`.
8. Per-token prices in `providers.yaml` are **illustrative placeholders** used only for
   benchmark cost estimates. Verify them against vendor price pages before quoting.

## Data protection
9. Bangladesh mobile numbers are `01[3-9]` + 8 digits locally, or `+880 1[3-9]…` internationally.
   PII masking also covers emails, card numbers, labelled NID/TIN/account/wallet numbers and
   any bare 9–18 digit run. This errs toward over-masking: a very large amount written
   without separators (≥ 9 digits, i.e. ≥ 10 crore taka) would be masked too.

## Finance math
10. **Cash basis.** Purchases of stock/raw material in a period are treated as COGS, since SMEs
    rarely keep inventory valuations. Gross margin is therefore a cash-basis approximation.
11. **Net operating margin** excludes loan repayments (we cannot split principal and interest
    from a single repayment line), equipment purchases and owner drawings. These are reported
    separately in the `excluded` block of every profitability result.
12. **Uncategorized outflows** count as variable operating cost (the conservative choice).
13. **`last_N_months`** means the N most recent *complete* calendar months, so comparisons
    are like-for-like.
14. **Money** is stored as NUMERIC(14,2) and handled as float rounded to 2 dp, which is enough
    for SME-scale BDT amounts.
15. **Liquid balance** = opening balance + all inflows − all outflows across cash, bank and wallets.

## Language and ingestion
16. Latin "nagad" means the Nagad wallet; Bangla "নগদ" means cash.
17. Bangladesh dates are parsed day-first (`dd/mm/yyyy`).
18. Wallet statements often put the counterparty's phone number in the name column. Such
    values go into the encrypted `account_ref` field, and the visible name becomes
    `acct *******1234`.
19. Festival dates in `config/calendar_bd.yaml` are approximate (lunar). They are only used to
    *explain* patterns in the user's own data, and are marked for verification.

## Agent, security and actions
20. **Roles.** Three roles: owner (Tier ≤ 2), accountant (Tier ≤ 1) and viewer (Tier 0). Only the owner can
    confirm money movement or delete data.
21. **Money is sandbox only.** The sandbox account starts with ৳5,00,000. Limits are ৳2,00,000 per
    transaction and ৳5,00,000 per day (env-configurable). Pending requests reserve their amount against both
    the daily cap and the balance. "Today" for the cap uses Asia/Dhaka time (UTC+6, no DST).
22. **Confirmation** requires re-typing the exact amount within 10 minutes. This deliberate friction stands in
    for step-up authentication; MFA is on the roadmap (see SECURITY_ASSESSMENT R5).
23. **Reminders are not sent.** They go to a simulated outbox, and follow-ups are saved as drafts for the owner
    to approve. No SMS or WhatsApp provider is integrated.
24. **Customer-facing text comes from deterministic templates** (English and Bangla), not free LLM text, so
    tone and facts stay controlled.
25. **The audit log keeps masked data after a deletion request.** It stores PII-masked inputs only, and
    keeping it proves the deletion happened. Everything else for that business is deleted.
26. **Demo logins are shown on the login page only when `APP_ENV=demo`.**

## Forecasting and financing
27. Forecast uncertainty uses weekly (not daily) net-cash-flow volatility. Lumpy purchases and collections
    partly offset within a week, so daily volatility overstates the range.
28. New credit sales are collected after the business's median invoice-to-payment time, measured from its own
    paid invoices.
29. Invoices more than 90 days overdue are counted at 50% in the forecast (collection risk).
30. **The financing catalog describes product *types* with illustrative figures.** It covers bank term and
    working capital, CMSME refinance, women entrepreneur, credit guarantee, NBFI lease, MFI, MFS nano,
    supplier credit, invoice financing and start-up fund. No figure describes a specific lender, and every item
    is `verified: false` until the operator verifies it.
31. Affordability uses each product's mid-point rate; the DSCR minimums in the catalog are illustrative.

## Demo persona and evidence
32. *Nusrat Trims & Accessories*, its customers and its suppliers are fictional. Seed data is generated
    deterministically relative to the as-of date, so alerts are always current. The evidence run pins
    2026-10-14.
33. The demo default model is cloud Claude; without an API key the offline rules engine answers instead and the UI
    labels every such reply as a fallback. Real LLMs plug in
    through the same interface.

## Local models (measured on an AMD RX 9060 XT 16 GB, Ryzen 7 3700X, 16 GB RAM, Windows 10)
36. **Default local model: Gemma 4 12B instruct Q4_K_M with its MTP draft head; backup: Qwen3-14B Q4_K_M.**
    Five models were run through the 48-scenario golden set with ground truth computed by the app's own tools
    (`benchmarks/results/local_models.md`). They were ranked by accuracy first (numeric accuracy, hallucinated
    numbers, tool-call success), then speed. Gemma had the best numbers (93% numeric, 6% hallucination), the best
    Bangla/Banglish language match (95%), and was faster (12 s median) and smaller (8 GB VRAM) than the
    Qwen3-14B (86% numeric, 8% hallucination, 18 s, 13 GB). Qwen3.5-9B was faster but less accurate. gpt-oss-20b
    and Granite 4.2 8B were fast but invented figures in 35-40% of answers, which is disqualifying for a finance app.
37. **A local model never falls back to a cloud model.** The local profile exists for privacy, so its fallback
    chain contains only local profiles and the offline rules engine. Every fallback is shown in the UI and API.
38. **The demo default is cloud Claude** (`default_profile` in `config/providers.yaml`) because judges will not
    have this GPU. Change that one line to `local-llamacpp` for a private, offline install.
39. **No fine-tuning.** LoRA on a 12-14B model needs more than 16 GB VRAM in bf16, and 4-bit QLoRA
    (bitsandbytes) has no ROCm build for Windows. The gains came from prompt structure (a static, cacheable
    system prompt), smaller tool results, a Bangladesh finance glossary, MTP speculative decoding and token
    streaming instead.
40. **llama.cpp settings differ per model on this Vulkan build.** Flash attention made Qwen3.5/Qwen3 prompt
    processing ~3x slower, so they run with `-fa off`. Gemma uses sliding-window attention and only reuses its
    prompt cache with `-fa on`. `scripts/start_local_llm.bat` applies the right flags per model.

## Not verified in this build environment
34. **Docker was not available on the development machine.** The Dockerfile and docker-compose.yml follow
    standard practice but have not been built here. Run `docker compose up --build` once to confirm.
35. **No live cloud LLM calls were made** (no API keys on the build machine). The cloud adapters are tested
    against mocked vendor responses. The local llama.cpp path was measured live (see 36-40). Run
    `python -m sme_copilot.cli bench --profiles claude-sonnet` with a key to measure the cloud default.
