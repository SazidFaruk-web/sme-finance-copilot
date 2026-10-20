---
name: Ascent Copilot project rules
alwaysApply: true
---

You are editing Ascent Copilot: a FastAPI + no-build JS app that helps Bangladesh small businesses with their books, cash flow and loans. Windows 10, PowerShell.

Layout
- sme_copilot/agent: LLM orchestrator loop, prompts.py, tools_*.py (tools the app's AI calls)
- sme_copilot/llm_providers: one LLMProvider interface; adapters per vendor; config/providers.yaml picks the profile
- sme_copilot/tools, forecasting, financing_catalog: deterministic finance logic (all money math lives here, never in the LLM)
- sme_copilot/security: auth, permission tiers, audit hash chain, PII masking. Do not weaken these.
- sme_copilot/api: FastAPI routes (routes_*.py), schemas.py
- frontend/: index.html, app.js, styles.css, charts.js. Plain ES modules, no build step, no frameworks.
- tests/: pytest. config/: YAML. seed/: demo data.

Commands (run from the project root)
- Tests: .venv\Scripts\python.exe -m pytest
- One test file: .venv\Scripts\python.exe -m pytest tests\test_x.py -q
- Run the app: "Start SME Copilot.bat"

How to work
- Read a file before editing it. Make the smallest change that does the job; match the surrounding style.
- Money values are BDT (Tk). Dates use Asia/Dhaka. Users write English, Bangla and Banglish.
- After changing Python, run the related tests. If a test fails, change the code or the test, then run it again.
  Running the same failing test again without editing anything first is pointless.
- Only say "done" when the last test run passed. If it still fails, say so and show the error. Never claim an edit you did not make.
- Floats: compare money with pytest.approx(x, abs=0.01) only if the value is truly within a cent; prefer exact rounded values.
- Never edit .env, .venv, data/, or benchmarks/results/. Never print secrets from .env.
- Keep answers short. Show code changes as edits to files, not long explanations.
