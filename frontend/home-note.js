// Home's occasional note (owner decision 2026-10-19): one short line under the two Home cards, about one app open in
// ten, gone after 10 seconds. It says something unusual in the owner's records (from /api/home/insights, every number
// calculated on the server), and each note is shown at most 3 times. With nothing new, it shows a business tip.
// Text is inserted as text, never markup.

const EVERY = 10, SHOW_MS = 10000, MAX_VIEWS = 3;

const COPY = {
  en: {
    by: "AI Assistant · from your records", byTip: "AI Assistant · business tip", close: "Hide this note",
    good: "Good news", warn: "Heads up", reminder: "Reminder", tip: "Tip for today",
    bill_overdue: p => `${p.name} (${p.money(p.amount)}) was due ${p.months === 1 ? "last month" : `${p.months} months ago`}. Paying it soon avoids late fees.`,
    bill_soon: p => `${p.name} (${p.money(p.amount)}) is due on ${p.date(p.due)}.`,
    overspend: p => `This month ${p.money(p.out)} went out but only ${p.money(p.in)} came in: ${p.money(p.gap)} more than you earned. Check the biggest costs in Money.`,
    owed: p => `Customers are late paying you ${p.money(p.owed)}, more than came in this month. Collecting some of it would help.`,
    sales_up: p => `Recorded sales after refunds are ${p.pct}% higher than the same days last month (${p.money(p.now)} against ${p.money(p.before)}).`,
    sales_down: p => `Recorded sales after refunds are ${p.pct}% lower than the same days last month (${p.money(p.now)} against ${p.money(p.before)}). Worth checking why.`,
    tips: [
      "Write down every sale the same day. Small amounts add up and are the easiest to forget.",
      "Keep the shop's money and your family's money separate, even if it is only two boxes.",
      "Before giving goods on credit (baki), agree on the date the customer will pay.",
      "Check which products sell fastest each month and keep those in stock first.",
      "Keep enough money aside for rent and salaries before buying new stock.",
      "A polite reminder a day after the due date gets more customers to pay than waiting a month.",
      "Buying a little less, more often, can keep more cash free for surprises.",
      "Compare your prices with the market once a month. The Prices tab helps.",
      "Little drops of water make the mighty ocean: small daily savings become real capital.",
      "Thank your regular customers. A returning customer costs less than finding a new one.",
      "Count your cash at the end of each day and compare it with your records.",
      "Plan for Eid and other busy seasons a month early, so stock and cash are ready.",
    ],
  },
  bn: {
    by: "এআই সহকারী · আপনার হিসাব থেকে", byTip: "এআই সহকারী · ব্যবসার পরামর্শ", close: "নোটটি লুকান",
    good: "সুখবর", warn: "খেয়াল করুন", reminder: "মনে করিয়ে দিচ্ছি", tip: "আজকের পরামর্শ",
    bill_overdue: p => `${p.name} (${p.money(p.amount)}) ${p.months === 1 ? "গত মাসে" : `${p.months} মাস আগে`} দেওয়ার কথা ছিল। দ্রুত দিলে বিলম্ব ফি এড়ানো যাবে।`,
    bill_soon: p => `${p.name} (${p.money(p.amount)}) দেওয়ার তারিখ ${p.date(p.due)}।`,
    overspend: p => `এই মাসে ${p.money(p.out)} খরচ হয়েছে, কিন্তু এসেছে মাত্র ${p.money(p.in)}: আয়ের চেয়ে ${p.money(p.gap)} বেশি। "টাকা" পাতায় বড় খরচগুলো দেখুন।`,
    owed: p => `ক্রেতাদের কাছে ${p.money(p.owed)} বকেয়া, যা এই মাসের আয়ের চেয়েও বেশি। কিছুটা আদায় করলে উপকার হবে।`,
    sales_up: p => `ফেরত বাদ দিয়ে হিসাবের বিক্রি গত মাসের একই দিনগুলোর তুলনায় ${p.pct}% বেশি (${p.money(p.now)}, আগে ছিল ${p.money(p.before)})।`,
    sales_down: p => `ফেরত বাদ দিয়ে হিসাবের বিক্রি গত মাসের একই দিনগুলোর তুলনায় ${p.pct}% কম (${p.money(p.now)}, আগে ছিল ${p.money(p.before)})। কারণটা দেখে নিন।`,
    tips: [
      "প্রতিটি বিক্রি সেদিনই লিখে রাখুন। ছোট অঙ্কগুলোই সবচেয়ে বেশি ভুলে যাওয়া হয়।",
      "দোকানের টাকা আর সংসারের টাকা আলাদা রাখুন, দুটি আলাদা বাক্সে হলেও।",
      "বাকিতে মাল দেওয়ার আগে ক্রেতার সঙ্গে টাকা দেওয়ার তারিখ ঠিক করে নিন।",
      "প্রতি মাসে কোন পণ্য সবচেয়ে দ্রুত বিক্রি হয় দেখুন, সেগুলো আগে মজুত রাখুন।",
      "নতুন মাল কেনার আগে ভাড়া ও বেতনের টাকা আলাদা করে রাখুন।",
      "তারিখ পার হওয়ার পরদিন ভদ্রভাবে মনে করিয়ে দিলে এক মাস অপেক্ষার চেয়ে বেশি টাকা আদায় হয়।",
      "একবারে বেশি না কিনে অল্প অল্প করে কিনলে হঠাৎ দরকারের জন্য নগদ টাকা থাকে।",
      "মাসে একবার বাজারদরের সঙ্গে নিজের দাম মিলিয়ে নিন। \"বাজারদর\" ট্যাব সাহায্য করবে।",
      "বিন্দু বিন্দু জলে সিন্ধু হয়: প্রতিদিনের ছোট সঞ্চয়ই একদিন পুঁজি হয়।",
      "নিয়মিত ক্রেতাদের ধন্যবাদ দিন। পুরনো ক্রেতা ধরে রাখা নতুন ক্রেতা খোঁজার চেয়ে সহজ।",
      "প্রতিদিন শেষে নগদ টাকা গুনে হিসাবের সঙ্গে মিলিয়ে নিন।",
      "ঈদ ও ব্যস্ত মৌসুমের জন্য এক মাস আগে থেকেই মাল ও টাকার পরিকল্পনা করুন।",
    ],
  },
  zh: {
    by: "AI 助手 · 来自您的记录", byTip: "AI 助手 · 经营小贴士", close: "隐藏此提示",
    good: "好消息", warn: "请注意", reminder: "提醒", tip: "今日小贴士",
    bill_overdue: p => `${p.name}（${p.money(p.amount)}）${p.months === 1 ? "上个月" : `${p.months} 个月前`}就该支付了。尽快支付可避免滞纳金。`,
    bill_soon: p => `${p.name}（${p.money(p.amount)}）将于 ${p.date(p.due)} 到期。`,
    overspend: p => `本月支出 ${p.money(p.out)}，收入只有 ${p.money(p.in)}：比收入多花了 ${p.money(p.gap)}。请在“资金”中查看最大的开支。`,
    owed: p => `客户逾期未付 ${p.money(p.owed)}，比本月收入还多。收回一部分会有帮助。`,
    sales_up: p => `扣除退款后的记录销售额比上月同期高 ${p.pct}%（${p.money(p.now)}，上月同期 ${p.money(p.before)}）。`,
    sales_down: p => `扣除退款后的记录销售额比上月同期低 ${p.pct}%（${p.money(p.now)}，上月同期 ${p.money(p.before)}）。值得查一查原因。`,
    tips: [
      "每笔销售当天就记下来。小金额最容易被忘记。",
      "把店里的钱和家里的钱分开，哪怕只是两个盒子。",
      "赊账之前，先和客户约定付款日期。",
      "每月看看哪些商品卖得最快，优先备货。",
      "进新货之前，先留出房租和工资。",
      "到期第二天礼貌提醒，比等一个月更容易收回钱。",
      "少量多次进货，能留出更多现金应对意外。",
      "每月把自己的价格和市场价比较一次，“市场价”标签可以帮忙。",
      "积少成多：每天的小额储蓄会变成真正的本钱。",
      "感谢老顾客。留住老顾客比找新顾客更省力。",
      "每天结束时清点现金，并与记录核对。",
      "提前一个月为开斋节等旺季准备货物和资金。",
    ],
  },
};

const read = k => { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch { return null; } };
const write = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } };
let checked = false;  // once per page load: "opening the app", not every return to Home

export async function maybeShowHomeNote({ h, api, S, money, view, force = false }) {
  if (checked && !force) return;
  checked = true;
  const user = S.user.username, opensKey = "app_opens:" + user, seenKey = "note_seen:" + user;
  const opens = (read(opensKey) || 0) + 1;
  write(opensKey, opens);
  if (!force && opens % EVERY !== 0) return;
  const t = COPY[S.ui] || COPY.en, seen = read(seenKey) || {};
  let pick = null;
  try {
    const { items } = await api("/api/home/insights");
    pick = items.find(x => (seen[x.id] || 0) < MAX_VIEWS && t[x.key]);
  } catch { /* a failed note never matters: fall back to a tip */ }
  if (!pick) {
    let fresh = t.tips.map((_, i) => i).filter(i => (seen["tip:" + i] || 0) < MAX_VIEWS);
    if (!fresh.length) { t.tips.forEach((_, i) => delete seen["tip:" + i]); fresh = t.tips.map((_, i) => i); }
    const i = fresh[Math.floor(Math.random() * fresh.length)];
    pick = { id: "tip:" + i, kind: "tip", tip: t.tips[i] };
  }
  if (!view.isConnected) return;  // the owner already left Home
  seen[pick.id] = (seen[pick.id] || 0) + 1;
  write(seenKey, seen);
  const date = iso => new Date(iso + "T12:00:00Z").toLocaleDateString({ bn: "bn-BD", zh: "zh-CN" }[S.ui] || "en-GB", { day: "numeric", month: "long", timeZone: "UTC" });
  const text = pick.tip || t[pick.key]({ ...pick.params, money, date });
  const note = h("aside", { class: `home-note kind-${pick.kind}`, role: "status", "aria-live": "polite", "data-i18n-skip": "" },
    h("div", { class: "home-note-copy" },
      h("p", { class: "home-note-head" }, h("b", {}, t[pick.kind]), h("span", {}, " · " + (pick.kind === "tip" ? t.byTip : t.by))),
      h("p", { class: "home-note-text" }, text)),
    h("button", { class: "home-note-close", type: "button", "aria-label": t.close, title: t.close, onclick: () => hide() }, "×"));
  let timer = null;
  const hide = () => { clearTimeout(timer); note.classList.add("leaving"); setTimeout(() => note.remove(), 300); };
  view.appendChild(note);
  timer = setTimeout(hide, SHOW_MS);
}
