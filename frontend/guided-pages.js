import { icon } from "./icons.js?v=12";
import { buildGuidance, greetingName, upcomingItems } from "./guidance.js?v=19";
import { zh, zhCopy } from "./i18n-zh.js?v=6";

const COPY = {
  en: {
    greeting: "Hello", intro: "One step at a time.", recorded: "Money in your records", source: "From your entries, not a live bank balance.", asOf: "As of", income: "Money in", expense: "Money out", calc: "How is this worked out?", ask: "Ask AI Assistant", next: "Your next step", how: "How to do it", remind: "Remind me", based: "Based on your records. You choose what happens.", details: "Original details", due: "Due", done: "Mark done", more: "Show more", tasks: "Tasks", taskIntro: "Choose one thing to work on. Open it when you are ready.", todo: "To do", reminders: "Reminders", upcoming: "Coming up", reminderIntro: "Your saved reminders appear here when you return to the app. No phone notifications are sent.", newReminder: "Add reminder", emptyReminders: "No saved reminders yet.", emptyReminderCopy: "Save a task and a date, and find it here when you return.", upcomingIntro: "Expected payments in the next 14 days. These are estimates, not completed payments.", emptyUpcoming: "No upcoming payments in your records.", expectedIn: "Expected money in", expectedOut: "Expected money out", inApp: "In-app reminder", money: "Money", moneyIntro: "Look up the numbers when you need them.", overview: "This month", forecast: "Money ahead", forecastIntro: "An estimate based on your recorded activity. Actual money may be different.", estimate: "Estimated balance", range: "Possible range", emptyForecast: "Add records before using a money forecast.", add: "Add record", readonly: "Read-only access", tabs: "Choose information", noTasks: "No other tasks need attention in the available records.",
  },
  bn: {
    greeting: "স্বাগতম", intro: "একবারে একটি কাজ।", recorded: "আপনার হিসাবে থাকা টাকা", source: "আপনার লেখা হিসাব অনুযায়ী; সরাসরি ব্যাংকের ব্যালেন্স নয়।", asOf: "হিসাবের তারিখ", income: "টাকা এসেছে", expense: "টাকা গেছে", calc: "কীভাবে হিসাব করা হয়েছে?", ask: "এআই সহকারীকে জিজ্ঞাসা", next: "আপনার পরের কাজ", how: "কীভাবে করবেন", remind: "মনে করিয়ে দিন", based: "আপনার হিসাব অনুযায়ী পরামর্শ। সিদ্ধান্ত আপনার।", details: "মূল তথ্য", due: "সময়সীমা", done: "সম্পন্ন", more: "আরও দেখুন", tasks: "কাজ", taskIntro: "একটি কাজ বেছে নিন। সুবিধামতো বিস্তারিত দেখুন।", todo: "করণীয়", reminders: "রিমাইন্ডার", upcoming: "সামনে যা আছে", reminderIntro: "অ্যাপে ফিরলে সেভ করা রিমাইন্ডার এখানে দেখবেন। ফোনে নোটিফিকেশন যাবে না।", newReminder: "রিমাইন্ডার যোগ", emptyReminders: "এখনও কোনো রিমাইন্ডার নেই।", emptyReminderCopy: "কাজ ও তারিখ সেভ করুন। অ্যাপে ফিরলে এখানে পাবেন।", upcomingIntro: "আগামী ১৪ দিনের সম্ভাব্য লেনদেন। এগুলো অনুমান; সম্পন্ন পেমেন্ট নয়।", emptyUpcoming: "আসন্ন কোনো পেমেন্ট হিসাবে নেই।", expectedIn: "টাকা আসার কথা", expectedOut: "টাকা যাওয়ার কথা", inApp: "অ্যাপের রিমাইন্ডার", money: "টাকা", moneyIntro: "দরকার হলে টাকার বিস্তারিত হিসাব দেখুন।", overview: "এই মাসে", forecast: "সামনের টাকার ধারণা", forecastIntro: "আপনার হিসাব অনুযায়ী একটি অনুমান। আসল টাকা ভিন্ন হতে পারে।", estimate: "সম্ভাব্য টাকা", range: "সম্ভাব্য সীমা", emptyForecast: "সামনের টাকার ধারণা পেতে আগে হিসাব যোগ করুন।", add: "হিসাব যোগ", readonly: "শুধু দেখার অনুমতি", tabs: "তথ্য বেছে নিন", noTasks: "বর্তমান হিসাবে অন্য কোনো জরুরি কাজ পাওয়া যায়নি।",
  },
};

COPY.zh = zhCopy(COPY.en);
const say = (S, en, bn) => S.ui === "bn" ? bn : S.ui === "zh" ? zh(en) : en;
const localeOf = S => ({ bn: "bn-BD", zh: "zh-CN" })[S.ui] || "en-GB";

function guideUI(ctx, d) {
  const { h, S, money, fmtDate, canWrite, onAsk, onReminder, onTool, onTrace, onDone, reload } = ctx;
  const c = COPY[S.ui] || COPY.en;
  const g = buildGuidance({ alerts: [...(d.guidance_alerts || d.alerts || []), ...(d.reminders || [])], recordCount: d.record_count || 0, asOf: d.as_of, canWrite: canWrite(), language: S.ui });
  const tomorrow = new Date(d.as_of + "T12:00:00Z"); tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
  const action = task => {
    const a = task.action;
    if (a.tool) return h("button", { class: "btn primary", onclick: e => onTool(a.tool,
      { ...a.args, language: S.ui === "bn" ? "bn" : "en", remind_on: tomorrow.toISOString().slice(0, 10) }, e.currentTarget.parentElement) }, a.label, icon("arrow", 17));
    if (a.href && a.href !== "#chat") return h("a", { class: "btn primary", href: a.href }, a.label, icon("arrow", 17));
    if (a.details) return canWrite() ? doneButton(task.id, true) : null;
    return h("button", { class: "btn primary", onclick: () => onAsk(task.question) }, a.label, icon("arrow", 17));
  };
  const doneButton = (id, primary = false) => h("button", { class: primary ? "btn primary" : "btn", onclick: async e => {
    const button = e.currentTarget; button.disabled = true;
    try { await onDone(id); reload(); } catch { button.disabled = false; }
  } }, icon("check", 16), c.done);
  const taskBody = (task, home = false) => h("div", { class: "task-body" },
    home ? null : h("p", { class: "task-reason" }, task.why),
    task.steps.length ? h("ol", {}, task.steps.map(step => h("li", {}, step))) : null,
    task.source ? h("details", { class: "source-details" }, h("summary", {}, c.details),
      h("div", { class: "source-note" }, h("p", {}, task.source.title), task.source.message ? h("p", {}, task.source.message) : null,
        task.source.due_date ? h("span", {}, `${c.due}: ${fmtDate(task.source.due_date)}`) : null)) : null,
    h("div", { class: "task-detail-actions" }, !home ? action(task) : null,
      canWrite() && task.kind !== "routine" && task.kind !== "custom" ? h("button", { class: "text-link", onclick: () => onReminder(task, d.as_of) }, icon("bell", 16), c.remind) : null));
  const balance = (home = false) => h("section", { class: "balance-panel" + (home ? " home-balance" : ""), "aria-label": c.recorded },
    h("div", { class: "balance-label" }, c.recorded), h("div", { class: "balance-amount num" }, money(d.kpis.cash_balance)),
    h("p", { class: "balance-date" }, `${c.asOf} ${fmtDate(d.as_of)}`), h("p", { class: "balance-source" }, c.source),
    home ? null : h("button", { class: "text-link balance-explain", onclick: () => onTrace(d.kpi_traces.cash_balance, c.calc) }, c.calc));
  return { c, g, action, taskBody, balance, doneButton };
}

// Hash-backed page tabs: links support browser history, deep links, and keyboard navigation.
function pageTabs(h, c, route, selected, options) {
  return h("nav", { class: "page-tabs", "aria-label": c.tabs }, options.map(([id, label]) => h("a", {
    href: `#${route}?tab=${id}`, class: selected === id ? "active" : "", "aria-current": selected === id ? "page" : null,
  }, label)));
}

// Render a small first batch. Remaining rows are created only when explicitly requested.
function pagedList(h, items, render, label, batch = 5) {
  const rows = h("div", { class: "paged-rows" }); let shown = 0;
  const more = h("button", { class: "btn show-more", onclick: () => append(true) }, label);
  function append(focusNew = false) {
    const nodes = items.slice(shown, shown + batch).map(render); shown += nodes.length; rows.append(...nodes);
    more.hidden = shown >= items.length;
    if (focusNew) { const first = nodes[0]?.querySelector("summary, button, a"); first?.focus(); }
  }
  append();
  return h("div", { class: "paged-list" }, rows, more);
}

export async function renderGuidedHome(v, ctx) {
  const { h, api, S } = ctx;
  const d = await api("/api/dashboard");
  const { c, g, action, taskBody, balance } = guideUI(ctx, d);
  const first = greetingName(S.user);
  const task = g.primary;
  // Strict Home budget: one balance, one recommendation, one primary action. No feed previews.
  v.replaceChildren(h("div", { class: "guided-home" },
    h("div", { class: "home-heading" }, h("div", {}, h("h1", {}, `${c.greeting}, ${first}.`), h("p", {}, c.intro))),
    h("div", { class: "home-main-grid" }, balance(true), h("article", { class: "guide-task task-primary" },
      h("div", { class: "eyebrow" }, icon("sun", 16), c.next), h("h2", {}, task.title), h("p", { class: "task-reason" }, task.why),
      h("div", { class: "task-actions" }, action(task)),
      h("details", { class: "task-details" }, h("summary", {}, c.how), taskBody(task, true)),
      h("p", { class: "guide-caption" }, c.based)))));
}

export async function renderGuidedTasks(v, ctx, selected = "todo") {
  const { h, api, fmtDate, money, canWrite, onReminder } = ctx;
  const tab = ["todo", "reminders", "upcoming"].includes(selected) ? selected : "todo";
  const d = await api("/api/dashboard");
  const { c, g, taskBody, doneButton } = guideUI(ctx, d);
  const body = h("section", { class: "tab-content", "aria-label": c[tab] });
  if (tab === "todo") {
    const saved = await api("/api/pilot/cases");
    const active = saved.filter(x => x.status !== "completed");
    if (active.length) body.appendChild(h("div", { class: "pilot-saved" }, h("h2", {}, say(ctx.S, "Continue a saved task", "বাকি থাকা কাজ")),
      pagedList(h, active, x => h("a", { class: "pilot-saved-row", href: `#chat?case=${x.id}` }, x.title[ctx.S.ui] || x.title.en), c.more)));
    body.appendChild(h("a", { class: "text-link", href: "#chat" }, say(ctx.S, "All tasks and reviews", "সব কাজ ও পর্যালোচনা")));
    body.appendChild(pagedList(h, g.tasks, task => h("details", { class: "task-row guide-task" },
      h("summary", {}, h("span", { class: "task-row-icon" }, icon(task.kind === "custom" ? "bell" : "check", 19)),
        h("span", { class: "task-row-copy" }, h("strong", {}, task.title), task.source ? h("span", {}, task.source.title) : null)), taskBody(task)), c.more));
  } else if (tab === "reminders") {
    if (ctx.S.user.role === "owner") body.appendChild(h("a", { class: "text-link", href: "#chat?tab=notifications" }, say(ctx.S, "SMS and reminder settings", "এসএমএস ও রিমাইন্ডার সেটিংস")));
    // Include both future and overdue personal reminders, but never resolved/dismissed entries.
    const reminders = [...new Map([...g.reminders, ...g.tasks.filter(t => t.kind === "custom").map(t => t.source)].map(a => [a.id, a])).values()]
      .sort((a, b) => (a.due_date || "9999").localeCompare(b.due_date || "9999") || a.id - b.id);
    body.appendChild(h("div", { class: "tab-intro" }, h("p", {}, c.reminderIntro), canWrite() ? h("button", { class: "btn primary", onclick: () => onReminder(null, d.as_of) }, icon("plus", 17), c.newReminder) : null));
    body.appendChild(reminders.length ? pagedList(h, reminders, a => h("article", { class: "reminder-row" },
      h("div", { class: "reminder-heading" }, icon("bell", 19), h("div", { class: "record-copy" }, h("strong", {}, a.title), h("span", {}, a.due_date ? fmtDate(a.due_date) : c.inApp)), canWrite() ? doneButton(a.id) : null),
      a.data?.case_id ? h("a", { class: "text-link", href: `#chat?case=${a.data.case_id}` }, say(ctx.S, "Open task / change date", "কাজ খুলুন / তারিখ বদলান")) : null,
      a.message ? h("details", { class: "reminder-note" }, h("summary", {}, c.details), h("p", {}, a.message)) : null), c.more)
      : h("div", { class: "home-panel quiet-empty" }, h("h2", {}, c.emptyReminders), h("p", {}, c.emptyReminderCopy)));
  } else {
    const events = upcomingItems({ scheduled: d.forecast.scheduled_items, reminders: [], asOf: d.as_of, limit: Infinity });
    body.appendChild(h("p", { class: "tab-description" }, c.upcomingIntro));
    body.appendChild(events.length ? pagedList(h, events, x => h("div", { class: "scheduled-row" }, icon("calendar", 20),
      h("div", { class: "record-copy" }, h("strong", {}, x.title), h("span", {}, fmtDate(x.date), " · ", x.amount > 0 ? c.expectedIn : c.expectedOut)),
      h("strong", { class: "num" }, money(Math.abs(x.amount)))), c.more) : h("p", { class: "home-panel quiet-empty" }, c.emptyUpcoming));
  }
  v.replaceChildren(h("div", { class: "guided-page tasks-page" }, h("h1", {}, c.tasks), h("p", { class: "page-intro" }, c.taskIntro),
    pageTabs(h, c, "tasks", tab, [["todo", c.todo], ["reminders", c.reminders], ["upcoming", c.upcoming]]), body));
}

export async function renderGuidedMoney(v, ctx, selected = "overview") {
  const { h, api, S, money, fmtDate, lineChart } = ctx;
  const tab = selected === "forecast" ? "forecast" : "overview";
  const d = await api("/api/dashboard");
  const { c, balance } = guideUI(ctx, d);
  const body = h("section", { class: "tab-content", "aria-label": c[tab] });
  if (tab === "overview") {
    const month = new Date(d.as_of + "T12:00:00Z").toLocaleDateString(localeOf(S), { month: "long", year: "numeric", timeZone: "UTC" });
    const metric = (label, value, direction) => h("div", { class: "money-stat" }, h("span", { class: "stat-label" }, icon(direction, 17), label), h("strong", { class: "num" }, money(value)));
    body.appendChild(h("div", { class: "money-overview" }, balance(), h("section", { class: "home-panel month-panel" }, h("h2", {}, month),
      h("div", { class: "money-pair" }, metric(c.income, d.kpis.income_this_month, "in"), metric(c.expense, d.kpis.expense_this_month, "out")))));
  } else if (!d.record_count) {
    body.appendChild(h("div", { class: "home-panel quiet-empty" }, h("p", {}, c.emptyForecast), canWriteOrReadLink(ctx, c)));
  } else {
    body.appendChild(h("section", { class: "home-panel forecast-panel" }, h("h2", {}, c.forecast), h("p", { class: "tab-description" }, c.forecastIntro),
      lineChart({ series: [{ name: c.estimate, color: "var(--series-1)", points: d.forecast.series.map(p => ({ x: p.date, y: p.balance })) }],
        band: d.forecast.series.map(p => ({ x: p.date, lo: p.low, hi: p.high })), bandLabel: c.range,
        yfmt: (n, axis) => money(n, axis), xfmt: fmtDate, height: 250, ariaLabel: c.forecast })));
  }
  v.replaceChildren(h("div", { class: "guided-page money-page" }, h("h1", {}, c.money), h("p", { class: "page-intro" }, c.moneyIntro),
    pageTabs(h, c, "money", tab, [["overview", c.overview], ["forecast", c.forecast]]), body,
    h("a", { class: "text-link", href: tab === "forecast" ? "#chat?start=shortfall" : "#chat?start=stock" }, tab === "forecast" ? say(S, "Plan an upcoming payment", "একটি পেমেন্টের পরিকল্পনা") : say(S, "Plan a product purchase", "পণ্য কেনার পরিকল্পনা"))));
}

function canWriteOrReadLink(ctx, c) {
  return ctx.h("a", { class: "btn", href: "#data" }, ctx.canWrite() ? c.add : c.recorded);
}
