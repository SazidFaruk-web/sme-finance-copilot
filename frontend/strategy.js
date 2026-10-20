// Strategy uses the existing scoped cases, reviewed actions and offline progress.
import "./strategy-copy.js?v=3";
export async function renderStrategy(host, ctx, renderPilot) {
  const { h, api, S } = ctx;
  const say = (en, bn, zh) => S.ui === "bn" ? bn : S.ui === "zh" ? zh : en;
  const translated = value => value?.[S.ui] || value?.en || "";
  const number = value => new Intl.NumberFormat(S.ui === "bn" ? "bn-BD" : "en-BD", { maximumFractionDigits: 3 }).format(value);
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  if (params.has("case") || params.has("start") || params.has("tab")) return renderPilot(host, ctx, "strategy");
  const copy = {
    seasonal: [
      say("Buy ahead for a season", "মৌসুমের জন্য আগে কিনুন", "为季节提前采购"),
      say("Check whether buying now is worth the storage cost and risk.", "এখন কিনলে সংরক্ষণ খরচ ও ঝুঁকি পুষবে কি না দেখুন।", "考虑储存成本和风险，评估提前采购。"),
    ],
    bulk: [
      say("Compare a bulk purchase", "বেশি পরিমাণে কেনা তুলনা করুন", "比较批量采购"),
      say("A lower price only helps if you can use the stock and protect your cash.", "দাম কম হলেই লাভ নয়—পণ্য ব্যবহার ও জরুরি টাকা রাখতে হবে।", "只有能用完库存并保留必要资金，低价才有价值。"),
    ],
    equipment: [
      say("Add equipment", "নতুন যন্ত্র যোগ করুন", "添置设备"),
      say("See whether extra demand could cover the purchase and running costs.", "বাড়তি চাহিদায় যন্ত্র কেনা ও চালানোর খরচ উঠবে কি না দেখুন।", "看看新增需求能否覆盖购买和运行成本。"),
    ],
  };
  const page = h("div", { class: "strategy-page" });
  const title = h("h1", { tabindex: "-1" }, say("Strategy", "ভবিষ্যৎ পরিকল্পনা", "经营规划"));
  const status = h("p", { role: "status", "aria-live": "polite" });
  page.append(h("span", { class: "eyebrow" }, say("A little further ahead", "একটু দূরের কথা ভাবুন", "为未来做好准备")), title,
    h("p", { class: "strategy-intro" }, say("A few next steps, based on what you sell and your records.", "আপনার ব্যবসা ও হিসাব থেকে পরের কয়েকটি পদক্ষেপ।", "根据您的业务和记录，提供几个下一步建议。")));
  status.textContent = say("Loading your planning options…", "পরিকল্পনার বিকল্প আনা হচ্ছে…", "正在加载规划选项…");
  page.append(status);
  host.replaceChildren(page);
  let context, cases;
  try { [context, cases] = await Promise.all([api("/api/pilot/strategy"), api("/api/pilot/cases")]); }
  catch (e) {
    if (e.status) throw e;
    return renderPilot(host, ctx, "strategy"); // existing owner-scoped offline progress
  }
  status.textContent = "";
  if (context.juice_context) {
    copy.seasonal[1] = say("If you sell mango drinks, check a seasonal pulp purchase, storage life and winter demand.", "আমের পানীয় বিক্রি করলে মৌসুমি পাল্প কেনা, সংরক্ষণকাল ও শীতের চাহিদা যাচাই করুন।", "如果销售芒果饮品，可核实季节性果浆采购、储存期限和冬季需求。");
    copy.bulk[1] = say("If sugar is a regular input, compare a larger order with smaller deliveries.", "নিয়মিত চিনি লাগলে বড় অর্ডারের সঙ্গে ছোট সরবরাহ তুলনা করুন।", "如果经常使用糖，可比较大批采购与分批配送。");
    copy.equipment[1] = say("Would extra freezer space meet real demand and pay for itself?", "বাড়তি ফ্রিজার কি আসল চাহিদা মেটাবে ও খরচ তুলবে?", "增加冰柜容量能满足实际需求并收回成本吗？");
  }
  const suggestions = h("section", { class: "strategy-opportunities", "aria-label": say("Suggested decisions", "প্রস্তাবিত সিদ্ধান্ত", "决策建议") });
  for (const idea of context.suggestions || []) {
    const basis = idea.basis === "records" ? say("From your records", "আপনার হিসাব থেকে", "来自您的记录") : idea.basis === "business_type"
      ? say("For your business type", "আপনার ব্যবসার ধরন অনুযায়ী", "根据您的业务类型") : say("More records needed", "আরও হিসাব দরকার", "需要更多记录");
    const card = h("article", { class: "strategy-recommendation" }, h("span", { class: "eyebrow" }, basis), h("h2", {}, translated(idea.title)), h("p", {}, translated(idea.reason)));
    const why = h("details", {}, h("summary", {}, say("Why this suggestion?", "এই পরামর্শ কেন?", "为什么建议这样做？")), h("p", {}, translated(idea.checks)));
    const facts = h("dl", { class: "strategy-evidence" });
    for (const fact of idea.evidence || []) facts.append(h("div", {}, h("dt", {}, translated(fact.label)), h("dd", {}, typeof fact.value === "number" ? (fact.currency === "BDT" ? "৳" : "") + number(fact.value) + (fact.unit ? " " + fact.unit : "") : fact.value)));
    why.append(facts, h("p", { class: "small muted" }, say("Records as of ", "হিসাবের তারিখ ", "记录截至 ") + idea.as_of));
    if (idea.supporting_records?.length) why.append(h("ul", { class: "strategy-records" }, idea.supporting_records.map(r => h("li", {}, r.date + " · " + (r.quantity < 0 ? say("Return or correction", "ফেরত বা সংশোধন", "退货或更正") : r.kind === "sale" ? say("Sold", "বিক্রি", "售出") : say("Bought", "কেনা", "买入")) + " · " + number(Math.abs(r.quantity)) + (idea.unit ? " " + idea.unit : "")))));
    if (idea.basis === "records") why.append(h("a", { class: "text-link", href: idea.records_href || "#data?tools=all" }, say("View supporting records", "সংশ্লিষ্ট হিসাব দেখুন", "查看相关记录")));
    card.append(why);
    if (idea.case_id) card.append(h("a", { class: "btn", href: `#strategy?case=${idea.case_id}` }, say("Open saved plan", "সেভ করা পরিকল্পনা খুলুন", "打开已保存的计划")));
    else if (idea.href) card.append(h("a", { class: "btn", href: idea.href }, say("Review records", "হিসাব দেখুন", "查看记录")));
    else if (S.user.max_tier >= 1) card.append(h("a", { class: "btn primary", href: `#strategy?start=strategy&suggestion=${encodeURIComponent(idea.id)}` }, say("Review this idea", "পরামর্শটি দেখুন", "查看这个想法")));
    suggestions.append(card);
  }
  page.append(suggestions);
  const manual = h("details", { class: "strategy-manual" }, h("summary", {}, say("Plan something else", "অন্য পরিকল্পনা করুন", "规划其他事项")), h("p", { class: "small muted" }, context.description));
  const grid = h("div", { class: "strategy-ideas" });
  for (const idea of context.ideas) {
    const [label, detail] = copy[idea.id];
    grid.append(h("a", { class: "strategy-idea", href: `#strategy?start=strategy&plan=${idea.id}` },
      h("span", { class: "strategy-idea-title" }, label, h("span", { "aria-hidden": "true" }, "→")), h("p", {}, detail)));
  }
  if (S.user.max_tier >= 1) { manual.append(grid); page.append(manual); }
  else page.append(h("p", {}, say("You can view saved plans. Ask the owner to start a new one.", "সেভ করা পরিকল্পনা দেখতে পারবেন। নতুনটি মালিককে শুরু করতে বলুন।", "您可以查看已保存的计划。请让店主创建新计划。")));
  const rows = cases.filter(c => c.kind === "strategy");
  const saved = h("section", { class: "strategy-saved" }, h("h2", {}, say("Your plans", "আপনার পরিকল্পনা", "您的计划")));
  if (!rows.length) saved.append(h("p", { class: "muted" }, say("A saved plan gives you a place to return, check assumptions and decide.", "সেভ করা পরিকল্পনায় ফিরে অনুমান মিলিয়ে সিদ্ধান্ত নিতে পারবেন।", "保存计划，方便之后核对假设并做出决定。")));
  const list = h("div", {}); let count = 0;
  const more = h("button", { type: "button", class: "btn" }, say("Show more", "আরও দেখুন", "显示更多"));
  function appendRows() {
    for (const c of rows.slice(count, count + 5)) list.append(h("a", { class: "pilot-saved-row", href: `#strategy?case=${c.id}` },
      h("strong", {}, c.item || say("Future plan", "ভবিষ্যৎ পরিকল্পনা", "未来计划")),
      h("span", {}, c.status === "completed" ? say("Saved for review", "পর্যালোচনার জন্য রাখা", "已保存，待审核") : say("Continue", "চালিয়ে যান", "继续"))));
    count += 5; more.hidden = count >= rows.length;
  }
  more.onclick = appendRows; appendRows(); saved.append(list, more); page.append(saved,
    h("p", { class: "small muted" }, say("Plans stay yours. Purchases, loans and messages need your review.", "পরিকল্পনা আপনারই। কেনাকাটা, ঋণ ও বার্তা আগে দেখে নেবেন।", "您掌握决定权。采购、借款和消息都需要您审核。")),
    h("a", { href: "#strategy?tab=offline", class: "text-link" }, say("Saved on this device", "এই ডিভাইসে রাখা", "保存在此设备上")), status);
  title.focus();
}
