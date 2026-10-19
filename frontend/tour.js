// First-visit guided tour (owner decision 2026-10-19): small pop-ups that point at each tab and the main settings.
// It starts once for a new account after the business-type question, can be skipped at any step (Skip, Esc), and
// can be replayed from Settings. Steps whose target is not on screen (other mode, phone layout) are left out.
// Text is inserted as text, never markup.

const COPY = {
  en: {
    step: (i, n) => `Step ${i} of ${n}`, next: "Next", back: "Back", skip: "Skip tour", done: "Finish",
    welcome: ["Welcome! Here's a quick tour", "We'll show you each tab in about a minute. You can skip at any time."],
    dashboard: ["Home", "Your recorded money and one next step for today. Start here every day."],
    chat: ["AI Assistant", "Ask about your business in plain words. It can prepare reminders and reports; nothing is sent until you confirm."],
    tasks: ["Tasks", "Your to-do list, reminders and what is coming up, kept in one place."],
    money: ["Money", "This month's money in and out, and an estimate of the months ahead."],
    data: ["Records", "Add a sale or expense by typing, for example “sold 2 cakes 900 cash”, or upload a bank or bKash file."],
    more: ["More", "Customers who owe you, bills, reports and the other tools."],
    invoices: ["Invoices", "Bill a customer and record their payments."],
    parties: ["Customers & suppliers", "Who owes you, and whom you owe."],
    financing: ["Financing", "Check loan quotes against what your business can repay."],
    actions: ["Actions", "Approve the payments and reminders the AI Assistant prepared."],
    settings: ["Privacy & settings", "Language, light or dark look, and Simple or Advanced view."],
    prices: ["Market prices", "Public prices for things your business buys, picked by the AI Assistant, and where they may go next month. Add or remove items any time."],
    language: ["Language", "Switch the app language at any time."],
    account: ["Your account", "Open Settings to change the look, switch between Simple and Advanced, take this tour again, or sign out."],
    end: ["You're ready", "Add your first record to get started. You can replay this tour from Settings."],
  },
  bn: {
    step: (i, n) => `ধাপ ${i}/${n}`, next: "পরের ধাপ", back: "আগের ধাপ", skip: "ট্যুর বাদ দিন", done: "শেষ",
    welcome: ["স্বাগতম! চলুন অ্যাপটি ঘুরে দেখি", "এক মিনিটে প্রতিটি ট্যাব দেখিয়ে দেব। যেকোনো সময় বাদ দিতে পারবেন।"],
    dashboard: ["হোম", "আপনার হিসাবে থাকা টাকা আর আজকের একটি করণীয়। প্রতিদিন এখান থেকে শুরু করুন।"],
    chat: ["এআই সহকারী", "বাংলা, ইংরেজি বা বাংলিশে ব্যবসা নিয়ে প্রশ্ন করুন। এটি রিমাইন্ডার ও রিপোর্ট তৈরি করে দেয়; আপনি নিশ্চিত না করা পর্যন্ত কিছু পাঠানো হয় না।"],
    tasks: ["কাজ", "আপনার করণীয়, রিমাইন্ডার আর আসন্ন কাজ এক জায়গায়।"],
    money: ["টাকা", "এই মাসের আয়-ব্যয় আর সামনের মাসগুলোর অনুমান।"],
    data: ["হিসাব", "লিখে বিক্রি বা খরচ যোগ করুন, যেমন “২টা কেক বিক্রি ৯০০ নগদ”, অথবা ব্যাংক/বিকাশ ফাইল আপলোড করুন।"],
    more: ["আরও", "বাকি খাতা, বিল, রিপোর্ট আর অন্যান্য সুবিধা।"],
    invoices: ["বিল", "ক্রেতাকে বিল দিন আর তার পেমেন্ট লিখে রাখুন।"],
    parties: ["ক্রেতা ও সরবরাহকারী", "কে আপনার কাছে বাকি, আর আপনি কার কাছে বাকি।"],
    financing: ["অর্থায়ন", "আপনার ব্যবসা কতটা শোধ করতে পারবে, তার সঙ্গে ঋণের প্রস্তাব মিলিয়ে দেখুন।"],
    actions: ["কাজের অনুমোদন", "এআই সহকারীর তৈরি পেমেন্ট ও রিমাইন্ডার এখানে অনুমোদন করুন।"],
    settings: ["গোপনীয়তা ও সেটিংস", "ভাষা, হালকা বা গাঢ় রং, আর সহজ বা অ্যাডভান্সড ভিউ।"],
    prices: ["বাজারদর", "আপনার ব্যবসা যা কেনে তার প্রকাশিত দাম, এআই সহকারী বেছে দিয়েছে, আর আগামী মাসে দাম কোন দিকে যেতে পারে। যেকোনো সময় পণ্য যোগ বা বাদ দিন।"],
    language: ["ভাষা", "যেকোনো সময় English, বাংলা আর 中文-এর মধ্যে বদলান।"],
    account: ["আপনার অ্যাকাউন্ট", "সেটিংসে গিয়ে রং বদলান, সহজ/অ্যাডভান্সড ভিউ বেছে নিন, ট্যুরটি আবার দেখুন, অথবা লগ আউট করুন।"],
    end: ["আপনি প্রস্তুত", "প্রথম হিসাবটি যোগ করে শুরু করুন। সেটিংস থেকে ট্যুরটি আবার দেখতে পারবেন।"],
  },
  zh: {
    step: (i, n) => `第 ${i} 步，共 ${n} 步`, next: "下一步", back: "上一步", skip: "跳过导览", done: "完成",
    welcome: ["欢迎！先快速看一圈", "大约一分钟带您认识每个页面。随时可以跳过。"],
    dashboard: ["首页", "您记录的资金和今天的一个下一步。每天从这里开始。"],
    chat: ["AI 助手", "用英语、孟加拉语或 Banglish 询问您的生意。它可以准备提醒和报告；在您确认之前不会发送任何内容。"],
    tasks: ["任务", "待办事项、提醒和即将到来的事情都在这里。"],
    money: ["资金", "本月的收入和支出，以及未来几个月的估计。"],
    data: ["记录", "直接输入即可添加销售或支出，例如“卖了 2 个蛋糕 900 现金”，或上传银行/bKash 文件。"],
    more: ["更多", "欠款客户、账单、报告和其他工具。"],
    invoices: ["发票", "给客户开账单并记录付款。"],
    parties: ["客户和供应商", "谁欠您钱，您欠谁钱。"],
    financing: ["融资", "把贷款报价和您的还款能力放在一起比较。"],
    actions: ["待批准操作", "批准 AI 助手准备的付款和提醒。"],
    settings: ["隐私和设置", "语言、浅色或深色外观，以及简洁或高级视图。"],
    prices: ["市场价格", "由 AI 助手挑选的、与您生意相关的商品公开价格，以及下个月可能的走势。可随时添加或移除商品。"],
    language: ["语言", "随时在 English、বাংলা 和中文之间切换。"],
    account: ["您的账户", "打开设置可更改外观、切换简洁/高级视图、重新观看本导览或退出登录。"],
    end: ["准备就绪", "添加第一条记录即可开始。可以在设置中重新观看本导览。"],
  },
};

// [copy key, CSS selector]; null selector = a centred card with no pointer.
const STEPS = [
  ["welcome", null],
  ["dashboard", "#nav-dashboard"], ["chat", "#nav-chat"], ["tasks", "#nav-tasks"], ["money", "#nav-money"],
  ["data", "#nav-data"], ["invoices", "#nav-invoices"], ["parties", "#nav-parties"], ["financing", "#nav-financing"],
  ["actions", "#nav-actions"], ["more", "#nav-more"], ["settings", "#nav-settings"],
  ["prices", ".market-tab"], ["language", ".language-toggle"], ["account", ".topbar .avatar"],
  ["end", null],
];

const doneKey = user => "tour_done:" + user;
export function tourDone(user) { try { return localStorage.getItem(doneKey(user)) === "1"; } catch { return true; } }
const markDone = user => { try { localStorage.setItem(doneKey(user), "1"); } catch { /* private mode */ } };

const visible = el => { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };

export function startTour({ h, lang, user, onEnd }) {
  document.querySelector(".tour")?.remove();
  const t = COPY[lang] || COPY.en;
  const steps = STEPS.filter(([, sel]) => !sel || visible(document.querySelector(sel)));
  let i = 0, target = null;
  const before = document.activeElement;

  const ring = h("div", { class: "tour-ring", "aria-hidden": "true" });
  const title = h("h2", { id: "tour-title", class: "tour-title" });
  const text = h("p", { id: "tour-text", class: "tour-text" });
  const count = h("span", { class: "tour-count" });
  const back = h("button", { type: "button", class: "btn sm tour-back", onclick: () => go(i - 1) }, t.back);
  const next = h("button", { type: "button", class: "btn sm primary tour-next", onclick: () => go(i + 1) }, t.next);
  const skip = h("button", { type: "button", class: "text-link tour-skip", onclick: () => end() }, t.skip);
  const card = h("div", { class: "tour-card", role: "dialog", "aria-modal": "false", "aria-labelledby": "tour-title", "aria-describedby": "tour-text", tabindex: "-1" },
    h("div", { class: "tour-top" }, count, skip), title, text, h("div", { class: "tour-actions" }, back, next));
  const root = h("div", { class: "tour", "data-i18n-skip": "" }, ring, card);

  function place() {
    const gap = 14, vw = window.innerWidth, vh = window.innerHeight;
    card.style.left = card.style.top = ""; card.removeAttribute("data-side");
    if (!target) { ring.hidden = true; card.classList.add("centred"); return; }
    card.classList.remove("centred");
    const r = target.getBoundingClientRect();
    ring.hidden = false;
    Object.assign(ring.style, { left: `${r.left - 6}px`, top: `${r.top - 6}px`, width: `${r.width + 12}px`, height: `${r.height + 12}px` });
    const cw = card.offsetWidth, ch = card.offsetHeight;
    // Prefer the side with the most room: right of a sidebar item, left of the price tab, below the top bar, above the phone nav.
    const room = { right: vw - r.right, left: r.left, below: vh - r.bottom, above: r.top };
    const side = room.right >= cw + gap * 2 ? "right" : room.left >= cw + gap * 2 ? "left" : room.below >= ch + gap * 2 ? "below" : "above";
    let x = side === "right" ? r.right + gap : side === "left" ? r.left - cw - gap : r.left + r.width / 2 - cw / 2;
    let y = side === "below" ? r.bottom + gap : side === "above" ? r.top - ch - gap : r.top + r.height / 2 - ch / 2;
    x = Math.max(12, Math.min(x, vw - cw - 12)); y = Math.max(12, Math.min(y, vh - ch - 12));
    card.dataset.side = side;
    card.style.left = `${x}px`; card.style.top = `${y}px`;
  }

  function go(n) {
    if (n < 0) return;
    if (n >= steps.length) return end();
    i = n;
    const [key, sel] = steps[i];
    target = sel ? document.querySelector(sel) : null;
    target?.scrollIntoView?.({ block: "nearest" });
    title.textContent = t[key][0]; text.textContent = t[key][1];
    count.textContent = t.step(i + 1, steps.length);
    back.hidden = i === 0;
    next.textContent = i === steps.length - 1 ? t.done : t.next;
    skip.hidden = i === steps.length - 1;
    place();
    card.focus({ preventScroll: true });
  }

  function end() {
    markDone(user);
    window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true);
    document.removeEventListener("keydown", onKey);
    root.remove();
    if (before && document.contains(before)) before.focus?.();
    onEnd?.();
  }

  const onKey = e => {
    if (e.key === "Escape") { e.preventDefault(); end(); }
    else if (e.key === "ArrowRight" && document.activeElement?.closest(".tour")) go(i + 1);
    else if (e.key === "ArrowLeft" && document.activeElement?.closest(".tour")) go(i - 1);
  };
  window.addEventListener("resize", place); window.addEventListener("scroll", place, true);
  document.addEventListener("keydown", onKey);
  document.body.appendChild(root);
  go(0);
}
