# Assumptions

Decisions taken without explicit confirmation. Each one is easy to revisit.

## Environment and stack
1. **No LLM API keys or local model runtime were available while building.** I tested every
   provider adapter (Anthropic, OpenAI, Gemini, OpenAI-compatible, Ollama) against mocked HTTP
   that reproduces each vendor's documented wire format, but none has made a live call yet.
   Run `python -m sme_copilot.cli models` and the benchmark with a real key to confirm.
2. **Offline "rules" provider.** A deterministic intent engine implements the same
   `LLMProvider` interface, so the whole agent loop (tool selection → permission check →
   execution → answer) runs with no model. It is the default profile, the last link of every
   fallback chain, and the benchmark baseline. Real LLMs replace it via `LLM_PROFILE`.
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
