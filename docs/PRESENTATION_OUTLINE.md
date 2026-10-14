# Presentation Outline (≤ 10 minutes, 12 slides)

Weighting reminder: **Task completion 40% · Security & compliance 30% · Innovation & interaction 30%.**
Spend time accordingly: about 4 minutes on what it *does*, 3 on how it stays *safe*, and 3 on what is *new
and local*.

| # | Slide | Time | Content | Criterion |
|---|---|---|---|---|
| 1 | **Title**: SME Finance Copilot | 0:20 | One line: "An AI finance copilot that does the work for Bangladesh's small businesses, in Bangla, Banglish or English, safely." Team, Topic E. | – |
| 2 | **The problem** | 0:45 | Bangladesh SMEs (shops, garment subcontractors, traders) run on notebooks, bank and bKash statements. They are profitable on paper but cash-poor because buyers pay late. Credit exists (bank SME loans, CMSME refinance schemes, MFIs, MFS nano-loans), but owners can't tell what they qualify for or what it really costs. Show the persona: Nusrat, accessories trader, ৳13.8 lakh stuck in receivables. | Innovation (local relevance) |
| 3 | **What it does**: one screen | 0:40 | Four capabilities: analyse, forecast and alert, match financing, take action. Dashboard screenshot. | Task completion |
| 4 | **Live demo** (or video) | 2:30 | Follow [DEMO_SCRIPT.md](DEMO_SCRIPT.md): forecast dip and trace, what-if, Bangla/Banglish chat, financing with reasons, PDF, reminder, confirmed sandbox transfer. | Task completion |
| 5 | **Task completion evidence** | 0:40 | 33-step scripted run, 33/33 pass; operation-log excerpt (`pending → confirmed`, `blocked`, `rejected`); PDF thumbnail; 32 tools; actions logged with actor, inputs, result and confirmation. | Task completion |
| 6 | **Numbers you can trust** | 0:35 | "The LLM never does math": deterministic tools with traces (formula, steps, source rows), numeric grounding check flags any unverified number, forecast with an 80% band. Screenshot of *Show calculation*. | Task completion · Innovation |
| 7 | **Permission tiers** | 0:45 | Tier 0/1/2/3 table; owner, accountant and viewer; one enforcement choke point in code; Tier-2 human-in-the-loop (re-typed amount, limits, daily cap, reservations, expiry, no replay); Tier 3 blocked and audited. | Security |
| 8 | **Threats we tested** | 0:45 | Prompt injection in a bKash row and in chat (flagged, neutralised, money tools disabled); fraud and tax-evasion refusals in three languages; hash-chained audit with tamper detection; PII masking before cloud LLMs plus local-only mode; field encryption; data deletion. Top residual risks: no MFA yet, cloud models see figures when chosen. | Security & compliance |
| 9 | **Compliance awareness** | 0:25 | VAT (Mushak), e-TIN, trade licence, KYC/AML, CMSME schemes as configurable rule files, all flagged "verify". Financing catalog illustrative with `source_url` and `last_verified_date`. Never stated as fact. | Compliance · Responsible AI |
| 10 | **Model-agnostic and measurable** | 0:45 | One provider interface: Claude, OpenAI, Gemini, OpenRouter, Groq, DeepSeek, Ollama, vLLM, llama.cpp, plus an offline engine; live dropdown; router and fallback. Benchmark: 48 BD scenarios measuring latency, TTFT, cost, tool success, numeric accuracy, financing correctness, hallucination, refusals, Bangla quality. Show the chart and offline baseline row. Interaction log feeds a fine-tune export. | Innovation |
| 11 | **Engineering quality** | 0:25 | 219 tests, 91% coverage; Docker one-command demo; works fully offline; no frontend build; SQLite → Postgres via one URL. | Task completion |
| 12 | **Impact and next steps** | 0:30 | Pilot with 20 Dhaka traders; verified lender catalog with partner banks/MFIs; WhatsApp/Telegram adapter; MFA and step-up auth before any real payment rail; local 7B fine-tune from consented, masked feedback. Close with the one-liner. | Innovation |

**Speaker tips**
- Open the demo already logged in, on the dashboard, with the model dropdown visible.
- If the network is down, nothing changes: the demo runs offline.
- Have [EXECUTION_EVIDENCE.md](EXECUTION_EVIDENCE.md) and [SECURITY_ASSESSMENT.md](SECURITY_ASSESSMENT.md) open
  in tabs for Q&A.
