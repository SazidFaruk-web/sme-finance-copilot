# Design context: a calm guide for running a small business

This is the product design contract for contributors and agents. Read it before designing or changing any feature, UI, AI response, notification, or onboarding flow. The audience and principles below take precedence over a fashionable visual treatment. Keep this document current when an agreed product decision changes.

## Who we are designing for

Our primary user runs a small business in Bangladesh and has little or no financial knowledge. They want to keep their business going, know what to do next, and get help doing it. Do not assume they understand accounting, financial ratios, loan terminology, charts, or software settings. English, Bangla, and Banglish are first-class ways to communicate; the interface is also available in Simplified Chinese. The app must remain useful without an available language model.

Success means the owner can answer, without interpretation:

1. How much money do my records show?
2. What needs my attention next, and why?
3. What exactly should I do, and how?
4. What is coming up, and where will I see my reminder?

## Reference direction

The user supplied two mobile banking mockups: a balance-led home and an overview screen, then the same home in a physical phone mockup. Their useful principles are generous whitespace, a single large balance, warm white surfaces, soft coral accents, rounded cards, restrained green/red money indicators, circular line-icon shortcuts, and short transaction lists. The overview uses rounded bars and clear period controls.

Use this hierarchy and calm visual language as inspiration. Build an original business tool. Phone bezels, textured walls, fabricated balances, fake avatars, banking actions such as Send/Withdraw, and decorative charts do not belong in our app. Avoid the reference's faint small labels and charts that communicate through color alone. The reference is described here so future contributors do not need access to the original chat attachments.

## Information hierarchy and disclosure

- Default to the guided Home, including for first-time visitors. Keep five primary navigation choices: Home, Tasks, Money, Records, and More. Use small sets of page tabs to organize related information.
- **Home has a strict two-card budget: recorded money and one next step.** Include a short greeting, the balance's as-of date and source, one primary action, and an optional “How to do it” disclosure. Home is an entry point, not a dashboard of everything the app can do.
- Do not add secondary recommendations, monthly totals, action shortcuts, recent activity, upcoming payments, reminder lists, approval queues, forecast previews, or duplicate Copilot invitations to Home. Collapsing those feeds on Home still adds choices; give them a destination instead.
- **Agreed exception (owner decision, 2026-10-19): the market price drawer.** Home may show one minimised edge tab, **Prices**, that opens a half-width drawer from the right with public market prices for the owner's kind of business and a one-line next-month outlook. It is not a third card: it starts closed, stays closed until the owner opens it, remembers that choice, and never pushes Home's two cards aside. Each outlook names the month, shows its possible range, and is written in words with a sign (never colour or arrow alone). Prices state their month and source and are labelled as market averages, not live shop prices. Do not add other content to the drawer or other drawers to Home.
- Tasks has separate To do, Reminders, and Coming up tabs. Keep task instructions collapsed until a row is opened. Show a short first batch and let users request more. Keep all issues and reminders retrievable.
- Money has separate This month and Money ahead tabs. Show money in/out together with an explicit month on This month. Forecasts belong only in Money ahead and retain their uncertainty range. Records owns entry and transaction history. More provides Copilot, customers/suppliers, bills, prepared actions, reports, and specialist tools.
- Home's one recommendation has a short reason and one concrete action. Its supporting evidence, instructions, and “Remind me” control are disclosed only when requested. Do not duplicate that action in multiple places on the same screen.
- Rank immediate cash risks, overdue collections, and approaching payments ahead of optional analysis or borrowing. Consider due dates and urgency; do not recommend a loan merely because cash is low.
- Show upcoming reminders separately from things needing action now. A future personal reminder must not displace an urgent business issue.
- Put records, detailed calculations, forecasts, customization, financing, and technical settings behind intentional choices. Do not remove access to useful functionality.
- Use one compact business-type setup with a recommended start. Never require a beginner to choose financial widgets or wait for an AI-generated layout to use the app.

## Guidance and AI behavior

Every recommendation follows **what → why → how → next action**. For example: “Follow up with Karim” → “Their bill is overdue” → “Check the bill, review the reminder, then confirm” → “Review reminder.” Use actual names, amounts, and dates from the business's records.

- Use deterministic tools for amounts, dates, prioritization, and calculations. The model explains and helps the owner; it does not invent evidence or silently make commitments.
- Label Home suggestions as based on recorded information. Do not claim a model generated them when they came from rules. The guidance must still work when the LLM is slow or offline.
- Prefer small, reversible next steps: check a bill, follow up with a customer, review spending, add a missing record. Explain tradeoffs before asking the user to decide.
- Contextual Ask Copilot buttons should prepare a specific question the owner can review and send. Avoid making them start with a blank box or sending messages automatically.
- Acknowledge uncertainty and missing records. An empty business is “Add your first record,” never “Your money is fine.” Forecasts are estimates, not promises or available bank funds.
- Personal reminders must persist on the server and appear when the owner returns. Say that they appear **in the app**; do not imply background push, SMS, email, or customer delivery that does not exist.
- Group notifications and let owners inspect more when ready. Do not interrupt with random tutorials, repeated reassurance, or a wall of alerts.

## Plain language

Use “money in,” “money out,” “customers owe you,” “bills to pay,” “money may run short,” and “next step.” Introduce accounting terms only when needed and explain them next to the term. Prefer short sentences and specific verbs: Add record, Check bill, Review reminder, Ask Copilot. Avoid vague buttons such as Do it, operational logs, tool names, tiers, and model settings in everyday flows.

Localize new guidance and navigation in English and Bangla, and add its Chinese to [frontend/i18n-zh.js](../frontend/i18n-zh.js) (keyed by the English text). Preserve names and original record descriptions. Format taka, dates, and periods clearly. Do not use emoji as the sole action label or money color as the sole meaning.

Authentication uses **one active language at a time**. Provide an explicit English / বাংলা / 中文 selector and remember the selection through login and subsequent visits. Translate the heading, labels, placeholders, instructions, validation, service errors, loading state, demo-role labels, and account-creation flow together. The language selector itself and user-entered names or credentials are exceptions. Never clear a form just because its language changes, and never persist passwords to retain a draft. Keep demo credentials collapsed and omit them outside demo deployments.

## Visual system

- General light theme: warm off-white page `#FAF8F5`, white cards, charcoal `#29292D`, muted text `#69635E`, subtle border `#EAE5DF`.
- Main decorative accent: coral `#EC805B`; accessible action background/text uses darker terracotta `#A84227`. Muted green `#609D85` and red `#B75659` communicate money direction alongside signs and labels.
- Use the existing system font stack with Bengali support; no required remote fonts or images. Body text is at least 15px in guided mode, supporting text normally 13–14px, line-height 1.5 or more. The recorded balance is the only oversized number.
- Use a 4px spacing rhythm, generous 24–32px section spacing, card corners around 20–24px, and rounded but practical controls. Avoid nesting cards inside cards unnecessarily.
- Desktop: a quiet, narrow sidebar and a readable content width; only the balance and next action form Home's main row. Leave the space below empty. Mobile: one column with an accessible bottom navigation. Prioritize reading order over matching desktop composition. Do not fill empty space with optional features.
- Retain readable dark, green, and blue preferences. Use semantic tokens rather than hardcoded light surfaces in components.
- Motion is optional feedback, not content. Honor reduced motion. No compulsory count-up numbers, looping effects, or moving highlights in the guided UI.

## Trust, permissions, and states

- Distinguish recorded cash from live bank balances and show the as-of date. Calculations and source details remain available on demand.
- Label sandbox payments at the decision point. Customer reminders here enter a sandbox outbox; never claim actual delivery. Preview recipient, amount, message, and date before confirmation.
- AI must never bypass write permissions or confirmation rules. Viewers see helpful read-only explanations instead of buttons they cannot use. Money movement requires the owner and existing confirmation checks.
- Loading preserves context; errors explain what failed and offer retry. A secondary feed failing must not erase the balance or prevent adding a record. Disable a submitting button to prevent accidental repeats.
- Empty states explain the first useful action. Save success appears only after the server confirms it. Updates and undo must keep visible records accurate.
- Use semantic headings, labeled inputs, visible keyboard focus, usable dialogs, and tap targets at least 44px. Aim for WCAG AA contrast (4.5:1 for ordinary text). Test at 360px width, desktop width, English/Bangla, dark theme, and reduced motion.

## Contributor review checklist

### Guided tasks and the Bangladesh pilot

The agreed [Bangladesh product plan](PRODUCT_PLAN_BD.md) is shared implementation context. The first audience is small shops and traders in Dhaka South. Copilot opens a functional task, not a chat transcript: establish the goal, confirm facts, ask the next useful question, compare options, prepare an action, and review its outcome.

- Show one question and at most three choices at a time. Prefer amounts, dates, selected records and short checklists. Offer “I don't know” and “Do this later.” Unknown values never silently become zero.
- Reuse known facts as editable suggestions. After six new questions, offer an answer summary and the choice to continue deeper or pause. Preserve input on language switches and provide backtracking and resuming.
- Keep optional text/voice for unusual cases. Speech only fills reviewable input; it cannot trigger a payment, message, application or record confirmation.
- Show at most three leading comparison figures. Put payment schedules, calculations and explanations behind “Why?” or “Show calculation.” Separate lender eligibility from the owner's ability to repay.
- Any relevant answer, record or source change invalidates action previews. Saved comparisons must show when their supporting facts have changed. Only deterministic services calculate money, check applicability, validate dates and enforce permissions.
- The model selects approved task/question IDs. It cannot generate arbitrary executable components or bypass confirmation. Keep a usable rules fallback when the model is unavailable.
- Distinguish **saved on this device**, **synchronised for review**, and **confirmed in records**. No automatic execution when connectivity returns. Never imply live source checks, SMS or speech are available offline.
- Distinguish **Prepared**, **Submitted**, and **Accepted/completed**. Printing a draft does not submit an application. Retain the official form and submission destination when verified.
- Owner SMS is opt-in, generic and grouped at most once daily, with provider setup and number verification. Provider acceptance is not handset delivery; delivery is not task completion. Customer messages remain owner-reviewed drafts.
- Before offering guidance from a regulation or lender product, consult the dated source register and its review state. Unreviewed material is an enquiry route, never a confident rate, deadline or recommendation.
- A human-help route, owner-controlled sharing, exports and recovery are part of the product. Review borrowing and personalised compliance conclusions during the pilot. Do not introduce scores or jargon to conceal missing evidence.

Do not add anything to Home for these capabilities. Put saved tasks in Tasks, calculations in Money, drafts/history in Records and documents/support in More.

Before implementing a feature, write down its audience, single user goal, hierarchy, primary action, data source, empty/error/loading states, and permission/confirmation behavior. Apply the installed MengTo design-first skill where available (see root AGENTS.md); this document remains usable without it.

Before shipping, ask:

- Can a person with no finance training understand the screen and choose a next action?
- Does Home still contain exactly its two essential cards and one primary action, with the price drawer minimised by default? Has supporting information been placed in its own tab instead of adding another choice to Home?
- Are every number, date, recommendation, and success claim supported by actual state?
- Do reminders persist, and is their delivery channel described honestly?
- Can keyboard, mobile, Bangla, read-only, and offline users complete the relevant flow?
- Have changed prioritization/business rules been tested and the rendered layout checked?

Do not add a feature to Home just because it exists. Add it when it helps the owner decide what to do now.
