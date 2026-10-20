// Goal roadmaps: the owner says what they are saving for, and the app lays out the months.
// Twelve reviewed layouts live here. The server picks which one fits the shape of the plan and
// supplies every figure; this file only draws. No amount is calculated in the browser.
const NS = "http://www.w3.org/2000/svg";
const svg = (tag, attrs = {}, ...kids) => {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v);
  for (const c of kids.flat()) if (c) e.appendChild(c);
  return e;
};

const EXAMPLES = [
  ["A commercial oven, about 2.5 lakh", "একটা বাণিজ্যিক ওভেন, প্রায় ২.৫ লাখ", "一台商用烤箱，约 25 万"],
  ["A deep freezer", "একটা ডিপ ফ্রিজার", "一台冷柜"],
  ["A delivery van within 2 years", "দুই বছরের মধ্যে একটা ডেলিভারি ভ্যান", "两年内买一辆送货车"],
  ["A place of my own", "নিজের একটা জায়গা", "属于自己的店面"],
];

const WATCHOUTS = {
  price_is_an_estimate: ["This price is an estimate, not a quote. A real quote will move the dates.",
    "এই দাম একটি অনুমান, প্রস্তাব নয়। আসল দাম পেলে তারিখ বদলাবে।", "这个价格是估算，不是报价。拿到实际报价后日期会变。"],
  price_unknown: ["We do not know what this costs yet. Add the price to get real dates.",
    "এর দাম এখনও জানা নেই। সঠিক তারিখ পেতে দামটি লিখুন।", "目前还不知道价格。填写价格后才能得到真实日期。"],
  short_history: ["Your records cover only a short time, so the monthly figure may change as more go in.",
    "আপনার হিসাব অল্প সময়ের, তাই আরও হিসাব জমলে মাসিক অঙ্ক বদলাতে পারে。", "您的记录时间还短，随着记录增加，每月金额可能变化。"],
  bills_first: ["You have bills due that are larger than a usual month's spare money. Clear those first.",
    "সাধারণ মাসের বাড়তি টাকার চেয়ে বেশি বিল বাকি আছে। আগে সেগুলো মেটান।", "您有一些账单超过了平常一个月的余钱。请先结清。"],
  quiet_months: ["Some months in this plan are quiet ones for you. They ask for less, on purpose.",
    "পরিকল্পনার কিছু মাস আপনার কম বিক্রির সময়। সেখানে ইচ্ছে করেই কম চাওয়া হয়েছে।", "计划中有几个月是您的淡季，因此特意要求存得少一些。"],
  reserve_kept: ["Money for a quiet month stays untouched. Only spare money above it is used.",
    "খারাপ মাসের জন্য রাখা টাকায় হাত দেওয়া হয়নি। শুধু তার বাইরের বাড়তি টাকা ধরা হয়েছে।", "应急备用金不动用，只使用超出部分的余钱。"],
  quote_before_borrowing: ["Nothing is borrowed here. Get written quotes and compare the total repayable.",
    "এখানে কোনো ঋণ নেওয়া হয়নি। লিখিত প্রস্তাব নিয়ে মোট ফেরতযোগ্য টাকা তুলনা করুন।", "此处并未借款。请取得书面报价并比较应还总额。"],
  some_months_lost_money: ["In at least one recorded month you spent more than came in. Keep that in mind.",
    "অন্তত একটি মাসে আয়ের চেয়ে খরচ বেশি হয়েছে। এটি মাথায় রাখুন।", "至少有一个月的支出超过了收入，请留意。"],
};

const REASONS = {
  no_price: ["We need a price before a plan can have dates.", "তারিখ ঠিক করতে আগে দাম দরকার।", "需要先有价格才能定出日期。"],
  no_surplus: ["Your records do not yet show money left over at the end of a month.",
    "আপনার হিসাবে এখনও মাস শেষে টাকা বাঁচে বলে দেখা যাচ্ছে না।", "您的记录还没有显示月底有结余。"],
  saving_alone_too_slow: ["Saving on its own does not reach this price by your date.",
    "শুধু সঞ্চয়ে আপনার তারিখের মধ্যে এই দাম উঠছে না।", "仅靠储蓄无法在您的期限内凑足。"],
  out_of_reach: ["On today's records, saving does not reach this price in a workable time.",
    "আজকের হিসাবে সঞ্চয় করে যুক্তিসঙ্গত সময়ে এই দাম ওঠে না।", "按目前的记录，储蓄无法在合理时间内达到这个价格。"],
  repayment_too_large: ["The amount left over would need a loan your records could not comfortably repay.",
    "বাকি টাকার জন্য এমন ঋণ লাগবে যা আপনার হিসাব অনুযায়ী স্বচ্ছন্দে শোধ করা কঠিন।", "剩余金额所需的贷款，按您的记录难以从容偿还。"],
};

const KIND_WORDS = {
  start: ["Start", "শুরু", "起步"], save: ["Save", "জমান", "储蓄"], borrow: ["Borrow", "ঋণ", "借款"],
  buy: ["Buy", "কিনুন", "购买"], repay: ["Repay", "শোধ", "还款"], review: ["Review", "পর্যালোচনা", "复查"],
};

const SEASON_WORDS = {
  peak: ["Busy season", "ব্যস্ত মৌসুম", "旺季"], low: ["Quiet season", "কম বিক্রির সময়", "淡季"],
  normal: ["Ordinary months", "সাধারণ মাস", "普通月份"],
};

export function roadmapHelpers(ctx) {
  const { S } = ctx;
  const say = (en, bn, zh) => S.ui === "bn" ? bn : S.ui === "zh" ? zh : en;
  const pick = row => row ? say(row[0], row[1], row[2]) : "";
  const locale = S.ui === "bn" ? "bn-BD" : S.ui === "zh" ? "zh-CN" : "en-GB";
  const monthLabel = (key, long = false) => {
    if (!key) return "";
    const d = new Date(key + "-01T12:00:00Z");
    return new Intl.DateTimeFormat(locale, { month: long ? "long" : "short", year: "numeric", timeZone: "UTC" }).format(d);
  };
  const monthShort = key => {
    if (!key) return "";
    const d = new Date(key + "-01T12:00:00Z");
    return new Intl.DateTimeFormat(locale, { month: "short", timeZone: "UTC" }).format(d);
  };
  const span = (from, to) => from === to ? monthLabel(from) : `${monthLabel(from)} – ${monthLabel(to)}`;
  return { say, pick, monthLabel, monthShort, span };
}

// --------------------------------------------------------------------------- shared pieces
function ring(fraction, { size = 128, stroke = 12, label = "", caption = "" } = {}) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r, filled = Math.max(0, Math.min(1, fraction));
  return svg("svg", { class: "rm-ring", viewBox: `0 0 ${size} ${size}`, width: size, height: size, "aria-hidden": "true" },
    svg("circle", { class: "rm-ring-track", cx: size / 2, cy: size / 2, r, "stroke-width": stroke, fill: "none" }),
    svg("circle", { class: "rm-ring-fill", cx: size / 2, cy: size / 2, r, "stroke-width": stroke, fill: "none",
      "stroke-dasharray": `${c * filled} ${c}`, "stroke-linecap": "round",
      transform: `rotate(-90 ${size / 2} ${size / 2})` }),
    label ? svg("text", { class: "rm-ring-label", x: size / 2, y: size / 2 - 2, "text-anchor": "middle" }, document.createTextNode(label)) : null,
    caption ? svg("text", { class: "rm-ring-caption", x: size / 2, y: size / 2 + 16, "text-anchor": "middle" }, document.createTextNode(caption)) : null);
}

function phaseActions(ctx, phase) {
  const { h } = ctx;
  if (!phase.actions?.length) return null;
  return h("ul", { class: "rm-actions" }, phase.actions.map(a => h("li", {}, a)));
}

function amountLine(ctx, phase) {
  const { h, money } = ctx;
  const { say } = roadmapHelpers(ctx);
  if (!phase.amount) return null;
  return h("p", { class: "rm-amount" }, money(phase.amount),
    phase.amount_kind === "monthly" ? h("span", { class: "rm-amount-unit" }, " " + say("a month", "প্রতি মাসে", "每月")) : null);
}

// --------------------------------------------------------------------------- the twelve layouts
// Every one of these receives the same plan and draws the same figures a different way.
const LAYOUTS = {
  // 1 ---------------------------------------------------------------- already affordable
  "quick-win"(ctx, plan) {
    const { h, money } = ctx;
    const { say, monthLabel } = roadmapHelpers(ctx);
    const step = plan.phases.find(p => p.kind === "buy") || plan.phases[0];
    return h("div", { class: "rm-quickwin" },
      h("div", { class: "rm-quickwin-mark", "aria-hidden": "true" },
        svg("svg", { viewBox: "0 0 48 48" }, svg("path", { d: "M10 25l10 10 18-22", fill: "none", "stroke-width": "4", "stroke-linecap": "round", "stroke-linejoin": "round" }))),
      h("div", {},
        h("p", { class: "rm-quickwin-lead" }, say("You can do this now", "এখনই সম্ভব", "现在就可以")),
        h("p", { class: "rm-quickwin-figure" }, money(plan.target)),
        h("p", { class: "rm-quickwin-when" }, say("Ready from ", "প্রস্তুত ", "最早可于 ") + monthLabel(plan.buy_month, true)),
        step?.summary ? h("p", { class: "rm-quickwin-text" }, step.summary) : null,
        phaseActions(ctx, step || {})));
  },

  // 2 ---------------------------------------------------------------- two months, two cards
  "two-step"(ctx, plan) {
    const { h, money } = ctx;
    const { span } = roadmapHelpers(ctx);
    const row = h("div", { class: "rm-twostep" });
    plan.phases.forEach((p, i) => {
      if (i) row.append(h("span", { class: "rm-twostep-link", "aria-hidden": "true" }, "→"));
      row.append(h("article", { class: `rm-twostep-card rm-kind-${p.kind}` },
        h("span", { class: "rm-chip" }, span(p.from_month, p.to_month)),
        h("h3", {}, p.title), amountLine(ctx, p),
        h("p", {}, p.summary), phaseActions(ctx, p)));
    });
    return row;
  },

  // 3 ---------------------------------------------------------------- short vertical stepper
  stepper(ctx, plan) {
    const { h } = ctx;
    const { span } = roadmapHelpers(ctx);
    return h("ol", { class: "rm-stepper" }, plan.phases.map(p =>
      h("li", { class: `rm-step rm-kind-${p.kind}` },
        h("span", { class: "rm-step-dot", "aria-hidden": "true" }, String(p.index)),
        h("div", { class: "rm-step-body" },
          h("span", { class: "rm-chip" }, span(p.from_month, p.to_month)),
          h("h3", {}, p.title), amountLine(ctx, p), h("p", {}, p.summary), phaseActions(ctx, p)))));
  },

  // 4 ---------------------------------------------------------------- months sized by the owner's own season
  "season-bars"(ctx, plan) {
    const { h, money } = ctx;
    const { say, monthShort, span } = roadmapHelpers(ctx);
    const months = plan.month_plan || [];
    const peak = Math.max(1, ...months.map(m => m.amount));
    const chart = h("div", { class: "rm-bars", role: "img",
      "aria-label": say("How much to put aside each month", "প্রতি মাসে কত আলাদা রাখতে হবে", "每月需要留出的金额") });
    for (const m of months) {
      chart.append(h("div", { class: `rm-bar rm-season-${m.season}` },
        h("span", { class: "rm-bar-value" }, money(m.amount, true)),
        h("span", { class: "rm-bar-fill", style: `height:${Math.max(6, (m.amount / peak) * 100)}%` }),
        h("span", { class: "rm-bar-month" }, monthShort(m.month)),
        m.season !== "normal" ? h("span", { class: "rm-bar-tag" }, m.season === "peak"
          ? say("busy", "ব্যস্ত", "旺") : say("quiet", "কম", "淡")) : null));
    }
    const key = h("p", { class: "rm-bars-key" },
      ["peak", "normal", "low"].map(k => h("span", { class: `rm-key rm-season-${k}` },
        h("i", { "aria-hidden": "true" }), say(...SEASON_WORDS[k]))));
    const cards = h("div", { class: "rm-cards" }, plan.phases.map(p =>
      h("article", { class: `rm-card rm-kind-${p.kind}` },
        h("span", { class: "rm-chip" }, span(p.from_month, p.to_month)),
        h("h3", {}, p.title), amountLine(ctx, p), h("p", {}, p.summary), phaseActions(ctx, p))));
    return h("div", {}, h("div", { class: "rm-bars-wrap" }, chart), key, cards);
  },

  // 5 ---------------------------------------------------------------- cumulative staircase
  staircase(ctx, plan) {
    const { h, money } = ctx;
    const { say, monthShort, span } = roadmapHelpers(ctx);
    const months = plan.month_plan || [];
    const steps = h("div", { class: "rm-stair", role: "img",
      "aria-label": say("Money set aside, building up month by month", "মাসে মাসে জমা টাকা বাড়ছে", "逐月累积的储蓄") });
    for (const m of months) {
      steps.append(h("div", { class: "rm-stair-step", style: `height:${Math.max(10, m.share * 100)}%` },
        h("span", { class: "rm-stair-total" }, money(m.cumulative, true)),
        h("span", { class: "rm-stair-month" }, monthShort(m.month))));
    }
    steps.append(h("div", { class: "rm-stair-goal" }, h("span", {}, say("Goal", "লক্ষ্য", "目标")), h("b", {}, money(plan.target, true))));
    return h("div", {}, h("div", { class: "rm-stair-wrap" }, steps),
      h("div", { class: "rm-cards" }, plan.phases.map(p =>
        h("article", { class: `rm-card rm-kind-${p.kind}` },
          h("span", { class: "rm-chip" }, span(p.from_month, p.to_month)),
          h("h3", {}, p.title), amountLine(ctx, p), h("p", {}, p.summary), phaseActions(ctx, p)))));
  },

  // 6 ---------------------------------------------------------------- a year, read as quarters
  "quarter-grid"(ctx, plan) {
    const { h, money } = ctx;
    const { say, monthLabel, monthShort } = roadmapHelpers(ctx);
    const months = plan.month_plan || [];
    const groups = [];
    for (let i = 0; i < months.length; i += 3) groups.push(months.slice(i, i + 3));
    const grid = h("div", { class: "rm-quarters" });
    groups.forEach((group, i) => {
      const total = group.reduce((s, m) => s + m.amount, 0);
      grid.append(h("article", { class: "rm-quarter" },
        h("header", {}, h("span", { class: "rm-quarter-no" }, say("Step ", "ধাপ ", "第 ") + (i + 1)),
          h("b", {}, money(total))),
        h("ul", {}, group.map(m => h("li", {},
          h("span", { class: `rm-dot rm-season-${m.season}`, "aria-hidden": "true" }),
          h("span", {}, monthShort(m.month)),
          m.season !== "normal" ? h("em", { class: "rm-quarter-season" }, m.season === "peak"
            ? say("busy", "ব্যস্ত", "旺") : say("quiet", "কম", "淡")) : null,
          h("b", {}, money(m.amount))))),
        h("footer", {}, say("Total so far ", "এ পর্যন্ত মোট ", "累计 ") + money(group[group.length - 1].cumulative))));
    });
    const last = plan.phases[plan.phases.length - 1];
    return h("div", {}, grid, last?.kind === "buy"
      ? h("p", { class: "rm-finish" }, say("Buy it in ", "কিনুন ", "购买时间：") + monthLabel(last.from_month, true)) : null);
  },

  // 7 ---------------------------------------------------------------- save, then decide about the rest
  "split-rail"(ctx, plan) {
    const { h, money } = ctx;
    const { say, span } = roadmapHelpers(ctx);
    const own = plan.from_cash_now + plan.from_savings, borrow = plan.to_borrow;
    const total = Math.max(1, own + borrow);
    const rail = h("div", { class: "rm-rail", role: "img",
      "aria-label": say("How much comes from your own money and how much would be borrowed",
        "কত টাকা নিজের আর কত ঋণ করতে হবে", "多少来自自有资金，多少需要借入") },
      h("div", { class: "rm-rail-own", style: `flex:${own}` },
        h("span", {}, say("Your own money", "নিজের টাকা", "自有资金")), h("b", {}, money(own))),
      h("span", { class: "rm-rail-join", "aria-hidden": "true" }),
      h("div", { class: "rm-rail-borrow", style: `flex:${borrow}` },
        h("span", {}, say("Still to find", "এখনও বাকি", "尚需筹集")), h("b", {}, money(borrow))));
    const columns = h("div", { class: "rm-rail-columns" },
      h("section", {}, h("h3", { class: "rm-rail-head" }, say("What you save", "যা আপনি জমাবেন", "您要储蓄的部分")),
        plan.phases.filter(p => ["start", "save"].includes(p.kind)).map(p =>
          h("article", { class: `rm-card rm-kind-${p.kind}` },
            h("span", { class: "rm-chip" }, span(p.from_month, p.to_month)),
            h("h4", {}, p.title), amountLine(ctx, p), h("p", {}, p.summary), phaseActions(ctx, p)))),
      h("section", {}, h("h3", { class: "rm-rail-head rm-rail-head-alt" }, say("What you would decide later", "পরে যা সিদ্ধান্ত নেবেন", "之后再决定的部分")),
        plan.phases.filter(p => ["borrow", "buy", "repay"].includes(p.kind)).map(p =>
          h("article", { class: `rm-card rm-kind-${p.kind}` },
            h("span", { class: "rm-chip" }, span(p.from_month, p.to_month)),
            h("h4", {}, p.title), amountLine(ctx, p), h("p", {}, p.summary), phaseActions(ctx, p)))));
    const note = plan.repay_months ? h("p", { class: "rm-note" },
      say(`Your records could carry about ${money(plan.repay_capacity)} a month, which would take about ${plan.repay_months} months. A lender decides their own terms.`,
        `আপনার হিসাব অনুযায়ী মাসে প্রায় ${money(plan.repay_capacity)} দেওয়া সম্ভব, তাতে প্রায় ${plan.repay_months} মাস লাগবে। শর্ত ঋণদাতা ঠিক করবেন।`,
        `按您的记录，每月约可负担 ${money(plan.repay_capacity)}，需要约 ${plan.repay_months} 个月。具体条件由放款方决定。`)) : null;
    const illustrative = plan.illustrative_finance ? h("details", { class: "rm-illustrative" },
      h("summary", {}, say("Illustrative repayment (demo only)", "উদাহরণ হিসেবে কিস্তি (শুধু ডেমো)", "示例还款（仅演示）")),
      h("p", {}, money(plan.illustrative_finance.monthly_low) + " – " + money(plan.illustrative_finance.monthly_high) + " "
        + say("a month, at placeholder rates. Not a lender's offer.", "প্রতি মাসে, উদাহরণের সুদহারে। কোনো ঋণদাতার প্রস্তাব নয়।", "每月，按占位利率计算。并非放款方报价。"))) : null;
    return h("div", {}, rail, note, columns, illustrative);
  },

  // 8 ---------------------------------------------------------------- more than a year, read as years
  "year-bands"(ctx, plan) {
    const { h, money } = ctx;
    const { say, monthShort, monthLabel } = roadmapHelpers(ctx);
    const months = plan.month_plan || [];
    const peak = Math.max(1, ...months.map(m => m.amount));
    const years = [...new Set(months.map(m => m.month.slice(0, 4)))];
    const wrap = h("div", { class: "rm-years" });
    for (const year of years) {
      const rows = months.filter(m => m.month.startsWith(year));
      const total = rows.reduce((s, m) => s + m.amount, 0);
      wrap.append(h("section", { class: "rm-year" },
        h("header", {}, h("h3", {}, year), h("b", {}, money(total)),
          h("span", { class: "rm-year-count" }, rows.length + " " + say("months", "মাস", "个月"))),
        h("div", { class: "rm-year-cells" }, Array.from({ length: 12 }, (_, i) => {
          const key = `${year}-${String(i + 1).padStart(2, "0")}`;
          const m = rows.find(r => r.month === key);
          if (!m) return h("span", { class: "rm-cell rm-cell-off", "aria-hidden": "true" },
            h("i", {}), h("em", {}, monthShort(key)));
          return h("span", { class: `rm-cell rm-season-${m.season}`,
            style: `--fill:${Math.round((m.amount / peak) * 100)}%`,
            title: `${monthLabel(m.month)} · ${money(m.amount)}` },
            h("i", { "aria-hidden": "true" }), h("em", {}, monthShort(m.month)));
        }))));
    }
    return h("div", {}, wrap,
      h("div", { class: "rm-cards" }, plan.phases.map(p =>
        h("article", { class: `rm-card rm-kind-${p.kind}` },
          h("span", { class: "rm-chip" }, p.from_month === p.to_month ? monthLabel(p.from_month)
            : `${monthLabel(p.from_month)} – ${monthLabel(p.to_month)}`),
          h("h3", {}, p.title), amountLine(ctx, p), h("p", {}, p.summary), phaseActions(ctx, p)))));
  },

  // 9 ---------------------------------------------------------------- the plan needs both levers
  "two-track"(ctx, plan, facts) {
    const { h, money } = ctx;
    const { say, span } = roadmapHelpers(ctx);
    const tracks = h("div", { class: "rm-tracks" },
      h("section", { class: "rm-track rm-track-in" },
        h("h3", {}, say("Bring more money in", "আয় বাড়ান", "增加收入")),
        h("p", {}, say("This plan asks for nearly everything your records leave over, so it only holds if money in grows.",
          "আপনার হিসাবে যা বাঁচে প্রায় পুরোটাই এই পরিকল্পনায় লাগছে, তাই আয় না বাড়লে এটি টিকবে না।",
          "这个计划几乎用掉了您记录中全部的结余，因此只有收入增加才能维持。")),
        h("ul", { class: "rm-actions" },
          h("li", {}, say("Collect what customers already owe you", "ক্রেতাদের কাছে পাওনা টাকা আদায় করুন", "先收回客户欠款")
            + (facts?.owed_to_you ? ` (${money(facts.owed_to_you)})` : "")),
          h("li", {}, say("Push the busy months harder rather than every month equally",
            "প্রতি মাসে সমান নয়, ব্যস্ত মাসগুলোতেই বেশি চেষ্টা করুন", "重点冲刺旺季，而不是每月平均用力")))),
      h("section", { class: "rm-track rm-track-out" },
        h("h3", {}, say("Keep money out steady", "খরচ স্থির রাখুন", "控制支出")),
        h("p", {}, say("Every taka of new regular spending pushes the date back.",
          "নতুন প্রতিটি নিয়মিত খরচ তারিখটিকে পিছিয়ে দেয়।", "每增加一笔固定开支，日期就往后推。")),
        h("ul", { class: "rm-actions" },
          h("li", {}, say("Hold off on any other new monthly cost until this is done",
            "এটি শেষ না হওয়া পর্যন্ত নতুন মাসিক খরচ এড়িয়ে চলুন", "在完成之前，先不要新增月度开支")),
          h("li", {}, say("Record everything, so the plan stays honest",
            "সব কিছু লিখে রাখুন, যাতে পরিকল্পনা সঠিক থাকে", "坚持记账，计划才站得住")))));
    return h("div", {}, tracks,
      h("div", { class: "rm-cards" }, plan.phases.map(p =>
        h("article", { class: `rm-card rm-kind-${p.kind}` },
          h("span", { class: "rm-chip" }, span(p.from_month, p.to_month)),
          h("h3", {}, p.title), amountLine(ctx, p), h("p", {}, p.summary), phaseActions(ctx, p)))));
  },

  // 10 --------------------------------------------------------------- the owner set a date
  "milestone-arc"(ctx, plan) {
    const { h, money } = ctx;
    const { say, monthLabel, span } = roadmapHelpers(ctx);
    const points = plan.phases;
    const width = 760, height = 190, pad = 54;
    const x = i => pad + (i * (width - pad * 2)) / Math.max(1, points.length - 1);
    const y = i => height - 44 - Math.sin((i / Math.max(1, points.length - 1)) * Math.PI) * 74;
    const path = points.map((_, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(i).toFixed(1)}`).join(" ");
    const art = svg("svg", { class: "rm-arc", viewBox: `0 0 ${width} ${height}`, "aria-hidden": "true" },
      svg("path", { class: "rm-arc-line", d: path, fill: "none" }),
      ...points.map((p, i) => svg("g", { class: `rm-arc-point rm-kind-${p.kind}` },
        svg("circle", { cx: x(i), cy: y(i), r: 17 }),
        svg("text", { x: x(i), y: y(i) + 5, "text-anchor": "middle" }, document.createTextNode(String(p.index))),
        svg("text", { class: "rm-arc-when", x: x(i), y: height - 14, "text-anchor": "middle" },
          document.createTextNode(monthLabel(p.from_month))))));
    return h("div", {}, h("div", { class: "rm-arc-wrap" }, art),
      h("p", { class: "rm-arc-target" }, say("Target date ", "লক্ষ্য তারিখ ", "目标日期 ") + monthLabel(plan.buy_month, true)),
      h("div", { class: "rm-cards" }, points.map(p =>
        h("article", { class: `rm-card rm-kind-${p.kind}` },
          h("span", { class: "rm-chip" }, span(p.from_month, p.to_month)),
          h("h3", {}, h("span", { class: "rm-card-no" }, p.index), p.title),
          amountLine(ctx, p), h("p", {}, p.summary), phaseActions(ctx, p)))));
  },

  // 11 --------------------------------------------------------------- most of it is already there
  "runway-gauge"(ctx, plan) {
    const { h, money } = ctx;
    const { say, monthLabel, span } = roadmapHelpers(ctx);
    const have = plan.from_cash_now, left = Math.max(0, plan.target - have);
    const gauge = h("div", { class: "rm-gauge" },
      ring(have / Math.max(1, plan.target), { size: 180, stroke: 18,
        label: Math.round((have / Math.max(1, plan.target)) * 100) + "%",
        caption: say("already there", "ইতিমধ্যে আছে", "已具备") }),
      h("dl", { class: "rm-gauge-figures" },
        h("div", {}, h("dt", {}, say("You have now", "এখন আছে", "现有")), h("dd", {}, money(have))),
        h("div", {}, h("dt", {}, say("Still to save", "আরও জমাতে হবে", "还需储蓄")), h("dd", {}, money(left))),
        h("div", {}, h("dt", {}, say("Months to go", "বাকি মাস", "剩余月数")), h("dd", {}, String(plan.months_needed)))));
    return h("div", {}, gauge,
      h("p", { class: "rm-finish" }, say("On track for ", "লক্ষ্য ", "预计 ") + monthLabel(plan.buy_month, true)),
      h("ol", { class: "rm-stepper rm-stepper-tight" }, plan.phases.map(p =>
        h("li", { class: `rm-step rm-kind-${p.kind}` },
          h("span", { class: "rm-step-dot", "aria-hidden": "true" }, String(p.index)),
          h("div", { class: "rm-step-body" },
            h("span", { class: "rm-chip" }, span(p.from_month, p.to_month)),
            h("h3", {}, p.title), amountLine(ctx, p), h("p", {}, p.summary))))));
  },

  // 12 --------------------------------------------------------------- not reachable, and why
  "gap-review"(ctx, plan) {
    const { h, money } = ctx;
    const { say, monthLabel } = roadmapHelpers(ctx);
    const reach = plan.from_cash_now + plan.from_savings;
    const bar = h("div", { class: "rm-gap" },
      h("div", { class: "rm-gap-bar" },
        h("span", { class: "rm-gap-reach", style: `width:${Math.min(100, (reach / Math.max(1, plan.target)) * 100)}%` })),
      h("div", { class: "rm-gap-labels" },
        h("span", {}, say("Saving would reach ", "সঞ্চয়ে পৌঁছাবে ", "储蓄可达 "), h("b", {}, money(reach))),
        h("span", {}, say("The price is ", "দাম ", "价格为 "), h("b", {}, money(plan.target)))));
    const needed = plan.required_monthly ? h("div", { class: "rm-gap-needed" },
      h("div", {}, h("dt", {}, say("To reach it in two years you would need", "দুই বছরে পৌঁছাতে দরকার", "两年内达成需要")),
        h("dd", {}, money(plan.required_monthly) + " "
          + say("a month", "প্রতি মাসে", "每月"))),
      h("div", {}, h("dt", {}, say("Your records leave over", "আপনার হিসাবে বাঁচে", "您的记录结余")),
        h("dd", {}, money(plan.monthly_amount))),
      h("div", {}, h("dt", {}, say("The difference to close", "যে ফারাক মেটাতে হবে", "需要弥补的差额")),
        h("dd", { class: "rm-gap-short" }, money(plan.monthly_gap) + " "
          + say("a month", "প্রতি মাসে", "每月")))) : null;
    const options = h("div", { class: "rm-options" },
      h("article", {}, h("h3", {}, say("Aim at something smaller first", "আগে ছোট কিছু লক্ষ্য করুন", "先瞄准小一些的目标")),
        h("p", {}, say("A smaller version of the same thing, or a used one, may do the same job and is reachable.",
          "একই কাজের ছোট বা ব্যবহৃত জিনিস নাগালের মধ্যে থাকতে পারে।", "同类的小型或二手设备也许够用，而且够得着。"))),
      h("article", {}, h("h3", {}, say("Grow what is left over each month", "মাসে যা বাঁচে তা বাড়ান", "提高每月结余")),
        h("p", {}, say("Collecting overdue money and holding costs steady both move this date closer.",
          "বাকি টাকা আদায় ও খরচ স্থির রাখলে তারিখ এগিয়ে আসবে।", "收回逾期欠款并稳住成本，都能让日期提前。"))),
      h("article", {}, h("h3", {}, say("Come back with more records", "আরও হিসাব নিয়ে ফিরে আসুন", "积累更多记录后再来")),
        h("p", {}, say("A few more recorded months may show a stronger pattern than today's figures can.",
          "আরও কয়েক মাসের হিসাব আজকের চেয়ে ভালো চিত্র দিতে পারে।", "再记录几个月，也许会显示出更好的情况。"))));
    const steps = h("ol", { class: "rm-stepper rm-stepper-tight" }, plan.phases.map(p =>
      h("li", { class: `rm-step rm-kind-${p.kind}` },
        h("span", { class: "rm-step-dot", "aria-hidden": "true" }, String(p.index)),
        h("div", { class: "rm-step-body" },
          h("span", { class: "rm-chip" }, p.kind === "review"
            ? say("Look again in ", "আবার দেখুন ", "复查时间 ") + monthLabel(p.from_month, true)
            : monthLabel(p.from_month) + (p.to_month !== p.from_month ? " – " + monthLabel(p.to_month) : "")),
          h("h3", {}, p.title), amountLine(ctx, p), h("p", {}, p.summary)))));
    return h("div", {}, bar, needed, steps, options);
  },
};

export function drawRoadmap(ctx, data) {
  const { h } = ctx;
  const plan = data.plan || {};
  const layout = LAYOUTS[plan.template] || LAYOUTS.stepper;
  const body = h("div", { class: `rm-layout rm-layout-${plan.template || "stepper"}` });
  body.append(layout(ctx, plan, data.facts));
  return body;
}

export { WATCHOUTS, REASONS, KIND_WORDS, EXAMPLES, ring };
