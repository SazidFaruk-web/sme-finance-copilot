// The goal planner: one open question, then a dated roadmap drawn by roadmap.js.
// Every figure comes from the server. This file asks, shows and lets the owner adjust.
import { drawRoadmap, roadmapHelpers, ring, WATCHOUTS, REASONS, EXAMPLES } from "./roadmap.js?v=3";

const HORIZONS = [
  [6, "In 6 months", "৬ মাসে", "6 个月内"],
  [12, "In a year", "এক বছরে", "一年内"],
  [24, "In 2 years", "দুই বছরে", "两年内"],
];

function errorText(ctx, e) {
  const { say } = roadmapHelpers(ctx);
  const rows = {
    too_many_goals: ["You have a lot of plans saved. Remove one before adding another.",
      "অনেক পরিকল্পনা সেভ করা আছে। নতুন করার আগে একটি সরান।", "您保存的计划已经很多，请先删除一个。"],
    lookup_unavailable: ["Online price lookup is switched off on this installation.",
      "এই ইনস্টলেশনে অনলাইনে দাম দেখা বন্ধ আছে।", "此安装未启用在线价格查询。"],
    not_found: ["That plan is no longer here.", "পরিকল্পনাটি আর নেই।", "该计划已不存在。"],
  };
  if (rows[e.code]) return say(...rows[e.code]);
  if (e.status === 403) return say("Only the owner can change plans.", "শুধু মালিক পরিকল্পনা বদলাতে পারেন।", "只有店主可以更改计划。");
  return say("That didn't save. Check your connection and try again.",
    "সেভ হয়নি। সংযোগ দেখে আবার চেষ্টা করুন।", "未能保存。请检查网络后重试。");
}

// --------------------------------------------------------------------------- what we already know
function knownStrip(ctx, facts) {
  const { h, money } = ctx;
  const { say } = roadmapHelpers(ctx);
  const rows = [
    [say("Money in, a usual month", "সাধারণ মাসে আয়", "平常一个月的收入"), facts.monthly_in],
    [say("Left over, a usual month", "সাধারণ মাসে যা বাঁচে", "平常一个月的结余"), facts.monthly_surplus],
    [say("Spare money today", "আজ বাড়তি টাকা", "今天的余钱"), facts.spare_cash],
  ];
  return h("section", { class: "gp-known" },
    h("p", { class: "gp-known-lead" },
      say("I will plan with what your records already show:", "আপনার হিসাব যা বলছে তা দিয়েই পরিকল্পনা করব:", "我会用您记录中已有的数据来规划：")),
    h("dl", {}, rows.map(([label, value]) => h("div", {},
      h("dt", {}, label), h("dd", {}, value === null || value === undefined ? "–" : money(value))))),
    h("p", { class: "gp-known-note" }, facts.months_of_history
      ? say(`Based on ${facts.months_of_history} recorded months. Money kept back for a quiet month is left out of the plan.`,
          `${facts.months_of_history} মাসের হিসাবের ভিত্তিতে। খারাপ মাসের জন্য রাখা টাকা পরিকল্পনায় ধরা হয়নি।`,
          `基于 ${facts.months_of_history} 个月的记录。为淡季预留的资金不计入计划。`)
      : say("You have no complete recorded month yet, so the plan will be rough.",
          "এখনও কোনো পূর্ণ মাসের হিসাব নেই, তাই পরিকল্পনাটি আন্দাজে হবে।", "您还没有完整月份的记录，因此计划会比较粗略。")));
}

// --------------------------------------------------------------------------- the one question
export async function renderGoalIntake(host, ctx) {
  const { h, api, S } = ctx;
  const { say } = roadmapHelpers(ctx);
  const page = h("div", { class: "gp-page" });
  const title = h("h1", { tabindex: "-1" }, say("What are you planning for?", "আপনি কীসের পরিকল্পনা করছেন?", "您在为什么做规划？"));
  const status = h("p", { class: "gp-status", role: "status", "aria-live": "polite" });
  const field = h("textarea", { id: "gp-goal", rows: "3", maxlength: "400", class: "gp-input",
    placeholder: say("For example: I want to buy a commercial oven, about 2.5 lakh",
      "যেমন: একটা বাণিজ্যিক ওভেন কিনতে চাই, প্রায় ২.৫ লাখ টাকা", "例如：我想买一台商用烤箱，大约 25 万塔卡") });
  const examples = h("div", { class: "gp-examples" },
    EXAMPLES.map(row => h("button", { type: "button", class: "gp-example",
      onclick: () => { field.value = say(...row); field.focus(); } }, say(...row))));

  let horizon = null;
  const horizonRow = h("div", { class: "gp-horizons", role: "group",
    "aria-label": say("When would you like it by?", "কবের মধ্যে চান?", "希望什么时候实现？") });
  const buttons = HORIZONS.map(([months, en, bn, zh]) => {
    const b = h("button", { type: "button", class: "gp-horizon", "aria-pressed": "false",
      onclick: () => {
        horizon = horizon === months ? null : months;
        buttons.forEach(x => x.setAttribute("aria-pressed", String(+x.dataset.months === horizon)));
      } }, say(en, bn, zh));
    b.dataset.months = months;
    return b;
  });
  horizonRow.append(...buttons);

  const submit = h("button", { type: "button", class: "btn primary gp-submit" },
    say("Make my plan", "আমার পরিকল্পনা তৈরি করুন", "生成我的计划"));
  const form = h("form", { class: "gp-form", onsubmit: e => { e.preventDefault(); submit.click(); } },
    h("label", { class: "gp-label", for: "gp-goal" },
      say("Tell me in your own words — what you want, and the price if you know it.",
        "নিজের ভাষায় বলুন — কী চান, আর দাম জানা থাকলে সেটিও।", "用您自己的话说说——想要什么，知道价格的话也写上。")),
    field, examples,
    h("p", { class: "gp-label gp-label-small" }, say("When would you like it by? (optional)", "কবের মধ্যে চান? (ইচ্ছামতো)", "希望什么时候实现？（可选）")),
    horizonRow, submit, status);

  page.append(h("span", { class: "eyebrow" }, say("Plan something bigger", "বড় কিছুর পরিকল্পনা", "规划更大的目标")),
    title,
    h("p", { class: "gp-intro" }, say("One question. Then a month-by-month plan built from your own records.",
      "একটি প্রশ্ন। তারপর আপনার হিসাব থেকে তৈরি মাসে মাসে পরিকল্পনা।", "只问一个问题，然后根据您的记录生成逐月计划。")),
    form);
  host.replaceChildren(page);
  title.focus();

  let context;
  try { context = await api("/api/strategy/goal-context"); } catch { /* the question still works */ }
  if (context) form.insertBefore(knownStrip(ctx, context.facts), submit);

  submit.onclick = async () => {
    const text = field.value.trim();
    if (text.length < 3) { status.textContent = say("Tell me what you are planning for first.",
      "আগে বলুন কীসের পরিকল্পনা করছেন।", "请先说明您要规划什么。"); field.focus(); return; }
    submit.disabled = true;
    status.textContent = say("Working out your plan…", "আপনার পরিকল্পনা তৈরি হচ্ছে…", "正在制定您的计划…");
    try {
      const created = await api("/api/strategy/goals", { body: { text, request_key: crypto.randomUUID(),
        language: S.ui === "bn" ? "bn" : S.ui === "zh" ? "zh" : "en", ...(horizon ? { horizon_months: horizon } : {}) } });
      location.hash = `#strategy?goal=${created.id}`;
    } catch (e) {
      submit.disabled = false;
      status.textContent = errorText(ctx, e);
    }
  };
}

// --------------------------------------------------------------------------- the plan
function priceBand(ctx, data, change) {
  const { h, money } = ctx;
  const { say } = roadmapHelpers(ctx);
  const price = data.price || {};
  const confirmed = price.source === "owner";
  const band = h("section", { class: "gp-price" + (confirmed ? " gp-price-set" : "") });
  const label = price.label && (price.label[ctx.S.ui] || price.label.en);
  const note = price.note && (price.note[ctx.S.ui] || price.note.en);

  const input = h("input", { type: "number", min: "1", step: "1", inputmode: "numeric", class: "gp-price-input",
    id: "gp-price", value: price.amount ?? "",
    placeholder: say("Price in taka", "দাম, টাকায়", "价格（塔卡）") });
  const save = h("button", { type: "button", class: "btn primary" },
    say("Use this price", "এই দামে চলুন", "使用此价格"));
  save.onclick = () => change({ amount: Number(input.value) || undefined });

  const head = h("div", { class: "gp-price-head" },
    h("div", {},
      h("span", { class: "eyebrow" }, confirmed ? say("The price you gave", "আপনার দেওয়া দাম", "您填写的价格")
        : price.source === "web" ? say("Estimated from public listings", "প্রকাশিত দাম থেকে অনুমান", "根据公开报价估算")
        : price.source === "catalog" ? say("Typical price, to confirm", "সাধারণ দাম, যাচাই করুন", "常见价格，待确认")
        : say("Price needed", "দাম দরকার", "需要价格")),
      h("p", { class: "gp-price-figure" }, price.amount ? money(price.amount) : say("Not known", "জানা নেই", "未知")),
      price.low && price.high && !confirmed
        ? h("p", { class: "gp-price-range" }, money(price.low) + " – " + money(price.high)) : null,
      label ? h("p", { class: "gp-price-label" }, label) : null));
  band.append(head);
  if (note && !confirmed) band.append(h("p", { class: "gp-price-note" }, note));
  if (!confirmed) {
    const controls = h("div", { class: "gp-price-controls" }, input, save);
    if (data.price_lookup_available) {
      const look = h("button", { type: "button", class: "btn" },
        say("Look up a price online", "অনলাইনে দাম দেখুন", "在线查询价格"));
      look.onclick = () => change({ search_price: true });
      controls.append(look);
      band.append(controls, h("p", { class: "gp-price-privacy" },
        say(`Only the words “${data.goal?.item || ""}” are sent to a search engine. Your records never leave this machine.`,
          `শুধু “${data.goal?.item || ""}” কথাটি সার্চ ইঞ্জিনে যাবে। আপনার হিসাব এই যন্ত্র ছাড়বে না।`,
          `只有“${data.goal?.item || ""}”这几个字会发送到搜索引擎。您的记录不会离开本机。`)));
    } else {
      band.append(controls);
    }
  } else {
    const edit = h("button", { type: "button", class: "text-link" }, say("Change the price", "দাম বদলান", "修改价格"));
    edit.onclick = () => { band.classList.remove("gp-price-set"); band.append(h("div", { class: "gp-price-controls" }, input, save)); edit.remove(); input.focus(); };
    band.append(edit);
  }
  return band;
}

function figures(ctx, data) {
  const { h, money } = ctx;
  const { say } = roadmapHelpers(ctx);
  const plan = data.plan || {};
  const rows = [
    [say("Every month", "প্রতি মাসে", "每月"), plan.monthly_amount,
      say("set aside from what your records leave over", "আপনার হিসাবে যা বাঁচে তা থেকে রাখা", "从记录中的结余里留出")],
    [say("From money you have now", "এখনকার টাকা থেকে", "来自现有资金"), plan.from_cash_now,
      say("half of today's spare money; the rest stays available", "আজকের বাড়তি টাকার অর্ধেক; বাকিটা হাতে থাকবে", "今天余钱的一半，其余保持可用")],
    [say("Months to get there", "কত মাস লাগবে", "需要几个月"), plan.months_needed,
      say("at the amounts below", "নিচের অঙ্ক অনুযায়ী", "按下面的金额计算"), true],
  ];
  return h("dl", { class: "gp-figures" }, rows.map(([label, value, hint, plainNumber]) =>
    h("div", {}, h("dt", {}, label),
      h("dd", {}, plainNumber ? String(value ?? "–") : money(value)),
      h("p", {}, hint))));
}

function watchouts(ctx, plan) {
  const { h } = ctx;
  const { say } = roadmapHelpers(ctx);
  const items = (plan.watchouts || []).filter(id => WATCHOUTS[id]);
  if (!items.length) return null;
  return h("details", { class: "gp-watchouts" },
    h("summary", {}, say("What could change this", "কী এটি বদলাতে পারে", "哪些情况会影响计划") + ` (${items.length})`),
    h("ul", {}, items.map(id => h("li", {}, say(...WATCHOUTS[id])))));
}

function controls(ctx, data, change, remove) {
  const { h, money, S } = ctx;
  const { say } = roadmapHelpers(ctx);
  const plan = data.plan || {};
  const box = h("details", { class: "gp-adjust" },
    h("summary", {}, say("Adjust this plan", "পরিকল্পনা বদলান", "调整这个计划")));
  const monthly = h("input", { type: "number", min: "0", step: "100", inputmode: "numeric", id: "gp-monthly",
    value: data.monthly_override ?? plan.monthly_amount ?? "" });
  const monthlySave = h("button", { type: "button", class: "btn" }, say("Use this amount", "এই অঙ্ক ব্যবহার করুন", "使用此金额"));
  monthlySave.onclick = () => change({ monthly_amount: Number(monthly.value) || 0 });
  const horizon = h("select", { id: "gp-horizon" },
    h("option", { value: "" }, say("No fixed date", "নির্দিষ্ট তারিখ নেই", "没有固定日期")),
    HORIZONS.map(([m, en, bn, zh]) => h("option", { value: String(m), selected: data.horizon_months === m }, say(en, bn, zh))));
  horizon.onchange = () => change(horizon.value ? { horizon_months: Number(horizon.value) } : { rebuild: true });

  box.append(
    h("div", { class: "gp-adjust-row" },
      h("label", { for: "gp-monthly" }, say("Put aside each month", "প্রতি মাসে আলাদা রাখব", "每月留出")),
      h("div", { class: "gp-adjust-controls" }, monthly, monthlySave)),
    h("p", { class: "gp-adjust-hint" },
      say(`Your records leave about ${money(data.facts?.monthly_surplus)} over in a usual month. Asking for more than that makes the plan fragile.`,
        `আপনার হিসাবে সাধারণ মাসে প্রায় ${money(data.facts?.monthly_surplus)} বাঁচে। এর বেশি চাইলে পরিকল্পনা ভঙ্গুর হবে।`,
        `您的记录显示平常一个月约结余 ${money(data.facts?.monthly_surplus)}。超过这个数，计划会变得脆弱。`)),
    h("div", { class: "gp-adjust-row" },
      h("label", { for: "gp-horizon" }, say("Want it by", "কবের মধ্যে চাই", "希望何时实现")),
      h("div", { class: "gp-adjust-controls" }, horizon)));
  if (S.user?.role === "owner") {
    const del = h("button", { type: "button", class: "btn gp-remove" }, say("Remove this plan", "পরিকল্পনাটি মুছুন", "删除此计划"));
    del.onclick = remove;
    box.append(del);
  }
  return box;
}

export async function renderGoalPlan(host, ctx, goalId) {
  const { h, api, S, money } = ctx;
  const { say, monthLabel } = roadmapHelpers(ctx);
  const page = h("div", { class: "gp-page gp-plan-page" });
  const status = h("p", { class: "gp-status", role: "status", "aria-live": "polite" },
    say("Opening your plan…", "আপনার পরিকল্পনা খোলা হচ্ছে…", "正在打开您的计划…"));
  page.append(status);
  host.replaceChildren(page);

  let data, busy = false;
  const load = async () => { data = await api(`/api/strategy/goals/${goalId}`); };
  const change = async body => {
    if (busy) return;
    busy = true;
    status.textContent = say("Rebuilding your plan…", "পরিকল্পনা নতুন করে তৈরি হচ্ছে…", "正在重新生成计划…");
    try { data = await api(`/api/strategy/goals/${goalId}`, { method: "PATCH", body }); draw(); }
    catch (e) { status.textContent = errorText(ctx, e); }
    finally { busy = false; }
  };
  const remove = async () => {
    if (!confirm(say("Remove this plan? Your records are not affected.",
      "পরিকল্পনাটি মুছে ফেলবেন? আপনার হিসাব বদলাবে না।", "删除此计划？您的记录不受影响。"))) return;
    try { await api(`/api/strategy/goals/${goalId}`, { method: "DELETE" }); location.hash = "#strategy"; }
    catch (e) { status.textContent = errorText(ctx, e); }
  };

  function draw() {
    const plan = data.plan || {};
    const words = data.narrative || {};
    const reached = plan.target ? plan.from_cash_now / plan.target : 0;
    const head = h("header", { class: `gp-hero gp-hero-${plan.strategy || "save_only"}` },
      h("div", { class: "gp-hero-text" },
        h("span", { class: "eyebrow" }, data.goal?.item || say("Your goal", "আপনার লক্ষ্য", "您的目标")),
        h("h1", { tabindex: "-1" }, words.headline || say("Your plan", "আপনার পরিকল্পনা", "您的计划")),
        h("p", { class: "gp-hero-sub" }, words.subtitle || ""),
        plan.buy_month ? h("p", { class: "gp-hero-when" },
          h("b", {}, monthLabel(plan.buy_month, true)),
          " · ", plan.months_needed === 0 ? say("ready now", "এখনই প্রস্তুত", "现在就可以")
            : say(`${plan.months_needed} months away`, `${plan.months_needed} মাস পরে`, `还有 ${plan.months_needed} 个月`)) : null),
      h("figure", { class: "gp-hero-ring" },
        ring(reached, { size: 150, stroke: 11, label: money(plan.target, true),
          caption: say("the price", "দাম", "价格") }),
        h("figcaption", {}, Math.round(reached * 100) + "% "
          + say("of it is already yours", "ইতিমধ্যেই আপনার", "已经是您的"))));

    const reasons = (plan.reasons || []).filter(id => REASONS[id]);
    const body = h("div", {});
    body.append(head);
    if (data.stale) body.append(h("p", { class: "gp-stale notice warn" },
      say("Your records have changed since this plan was made. Rebuild it to use the latest.",
        "পরিকল্পনাটি তৈরির পর আপনার হিসাব বদলেছে। নতুন করে তৈরি করুন।", "自生成以来您的记录已变化。请重新生成以使用最新数据。"),
      h("button", { type: "button", class: "btn", onclick: () => change({ rebuild: true }) },
        say("Rebuild", "নতুন করে তৈরি", "重新生成"))));
    body.append(priceBand(ctx, data, change));
    if (reasons.length) body.append(h("ul", { class: "gp-reasons" }, reasons.map(id => h("li", {}, say(...REASONS[id])))));
    if (plan.target) body.append(figures(ctx, data), drawRoadmap(ctx, data));
    const extras = h("div", { class: "gp-extras" });
    const w = watchouts(ctx, plan);
    if (w) extras.append(w);
    if (S.user?.max_tier >= 1) extras.append(controls(ctx, data, change, remove));
    body.append(extras,
      h("p", { class: "gp-footnote" },
        say("A plan, not a commitment. Nothing is bought, borrowed or sent. Amounts come from your records; prices and future sales are not guaranteed.",
          "এটি পরিকল্পনা, অঙ্গীকার নয়। কিছু কেনা, ধার করা বা পাঠানো হয়নি। অঙ্কগুলো আপনার হিসাব থেকে; দাম ও ভবিষ্যৎ বিক্রি নিশ্চিত নয়。",
          "这是计划，不是承诺。没有任何购买、借款或发送。金额来自您的记录；价格和未来销售无法保证。")),
      h("p", { class: "gp-written" }, words.written_by === "model"
        ? say("Wording by the local AI Assistant. Every amount and date is calculated by the app.",
            "লেখাটি স্থানীয় এআই সহকারীর। সব অঙ্ক ও তারিখ অ্যাপের হিসাব।", "文字由本地 AI 助手撰写，所有金额和日期由应用计算。")
        : say("Wording from the app's reviewed text. Every amount and date is calculated by the app.",
            "অ্যাপের যাচাই করা লেখা। সব অঙ্ক ও তারিখ অ্যাপের হিসাব।", "文字取自应用的审定文案，所有金额和日期由应用计算。")),
      h("a", { class: "text-link", href: "#strategy" }, say("← All plans", "← সব পরিকল্পনা", "← 所有计划")),
      status);
    page.replaceChildren(body);
    status.textContent = "";
    body.querySelector("h1")?.focus();
  }

  try { await load(); draw(); }
  catch (e) { status.textContent = errorText(ctx, e); page.append(h("a", { class: "text-link", href: "#strategy" },
    say("← All plans", "← সব পরিকল্পনা", "← 所有计划"))); }
}

// --------------------------------------------------------------------------- the Strategy landing block
export async function goalPlannerSection(ctx) {
  const { h, api, S, money } = ctx;
  const { say, monthLabel } = roadmapHelpers(ctx);
  const section = h("section", { class: "gp-entry" });
  const start = h("a", { class: "btn primary", href: "#strategy?goal=new" },
    say("Plan a big purchase", "বড় কেনাকাটার পরিকল্পনা", "规划一笔大额采购"));
  section.append(h("div", { class: "gp-entry-head" },
    h("div", {},
      h("h2", {}, say("Saving towards something big?", "বড় কিছুর জন্য জমাচ্ছেন?", "在为大件存钱吗？")),
      h("p", {}, say("Tell me what you want and I will lay out the months — what to put aside, and when it is yours.",
        "কী চান বলুন, আমি মাসগুলো সাজিয়ে দেব — কত রাখবেন, আর কবে সেটি আপনার হবে।",
        "告诉我您想要什么，我来安排每个月——存多少，以及何时能拥有它。"))),
    S.user?.max_tier >= 1 ? start : null));

  let rows = [];
  try { rows = await api("/api/strategy/goals"); } catch { return section; }
  if (!rows.length) return section;
  const list = h("div", { class: "gp-list" });
  for (const row of rows.slice(0, 6)) {
    list.append(h("a", { class: `gp-list-row${row.feasible === false ? " gp-list-row-blocked" : ""}`,
      href: `#strategy?goal=${row.id}` },
      h("div", {}, h("strong", {}, row.item || say("A plan", "একটি পরিকল্পনা", "一个计划")),
        h("span", { class: "gp-list-head" }, row.headline || "")),
      h("div", { class: "gp-list-meta" },
        h("b", {}, money(row.target)),
        h("span", {}, row.feasible === false ? say("Needs a rethink", "নতুন করে ভাবতে হবে", "需要重新考虑")
          : row.buy_month ? monthLabel(row.buy_month) : say("In progress", "চলছে", "进行中")))));
  }
  section.append(h("h3", { class: "gp-list-title" }, say("Your goals", "আপনার লক্ষ্য", "您的目标")), list);
  return section;
}
