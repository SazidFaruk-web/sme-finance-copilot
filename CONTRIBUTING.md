# Contributing

Read [AGENTS.md](AGENTS.md) and [the design principles](docs/DESIGN_PRINCIPLES.md) before implementing a feature. These apply to AI agents and human contributors. Our primary user runs a small business and has no finance training; start with their next useful action and reveal details only when needed.

The agreed [Bangladesh pilot plan and source register](docs/PRODUCT_PLAN_BD.md) define the six guided workflows and operating requirements. Preserve versioned previews, idempotent confirmation, business scoping and the distinction between local drafts and confirmed records. Do not enable illustrative lending terms or generic regulatory deadlines for real owners. New question IDs need bilingual copy and deterministic validation; models may select approved IDs, never execute UI or financial actions. Bump the application/service-worker asset version together when changing cached frontend files.

Keep the plain HTML/CSS/ES-module frontend and offline behavior. Use server calculations for financial facts and preserve role permissions, previews, and confirmation checks. Do not commit business data, secrets, or runtime screenshots.

Use an isolated database for development checks. Run the relevant Python tests with `.venv/Scripts/python -m pytest` and the guidance tests with `node --experimental-default-type=module --test tests/ui/guidance.test.mjs`. For UI changes, verify Home's two-card limit and page tabs (including deep links and browser Back). Also inspect desktop and mobile layouts, English/Bangla, dark theme, keyboard focus, empty/error states, and read-only access. See the design document for the full acceptance criteria.
