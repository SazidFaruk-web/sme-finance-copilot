# Project instructions

The agreed pilot specification and dated source register are in [docs/PRODUCT_PLAN_BD.md](docs/PRODUCT_PLAN_BD.md). Read it before changing guided workflows, financing, compliance, reminders or offline behaviour. Do not enable illustrative financial/compliance guidance for real owners. Keep source review, SMS provider acceptance, delivery, and owner completion distinct.

## Design-related changes

Before designing or implementing any feature, read [docs/DESIGN_PRINCIPLES.md](docs/DESIGN_PRINCIPLES.md). It is the shared product and design context for every agent and contributor. Design for small-business owners with no finance background: a calm guided Home, one clear next step, plain explanations, persistent in-app reminders, and details on demand. Update that file when the user agrees to a new design principle.

Home has a strict two-card limit: recorded money and one next step, with one primary action. Keep supporting information in its own destination: Tasks (To do / Reminders / Coming up), Money (This month / Money ahead), Records, or More. Do not add feed previews, secondary tasks, shortcuts, or charts to Home, even as collapsed sections. Empty space is intentional.

Authentication shows one active language at a time, selected with English / বাংলা controls. Translate the entire login and account-creation flow, including errors and loading messages. Preserve in-progress input when switching language; never store passwords in browser storage.

The user wants MengTo's design skills used whenever design changes are made in this project.

- Before changing UI/UX, layout, typography, colors, spacing, components, responsive behavior, motion, or visual assets, read and apply `design-first-ui-prompting/SKILL.md` from the installed Codex skills directory.
- For premium, cinematic, or motion-led website work, also read and apply `build-awwwards-quality-sites/SKILL.md` when its trigger fits the request. Use the smallest relevant set of skills.
- Apply the guidance within the existing project stack and the user's requested scope. Preserve the app's usability, accessibility, financial clarity, and offline behavior; choose styles and dependencies that fit those constraints.
- Mention the applied skill in the first design-work update. These design requirements do not apply to unrelated backend or infrastructure changes.

The skills directory is `$CODEX_HOME/skills` when configured, otherwise `C:/Users/siyad/.codex/skills` on this machine.

Installed design skills come from [MengTo/Skills](https://github.com/MengTo/Skills), revision `83a47fee32f0b6349bff1fede99257a5ef03dc93`:

- `agent-skills/ui/design-first-ui-prompting`
- `agent-skills/web-design/build-awwwards-quality-sites`
