import { localDrafts, saveLocal, removeLocal, numericInput } from "./pilot-store.js?v=14";

// Unsubmitted edits survive language changes in memory. Explicit offline drafts use IndexedDB.
const edits = new Map();
const WORDS = {
  manageable: ["Looks manageable under these assumptions", "এই অনুমান অনুযায়ী সামলানো সম্ভব মনে হচ্ছে"],
  tight: ["Repayments look too tight", "কিস্তি দিতে টান পড়তে পারে"],
  need_information: ["We need more information", "আরও কিছু তথ্য দরকার"],
  test_small: ["Start with a small test", "ছোট করে পরীক্ষা করুন"], wait: ["Keep essential money safe", "জরুরি টাকাটা হাতে রাখুন"],
  shortfall: ["There is a gap to plan for", "টাকার ঘাটতি মেটানোর পরিকল্পনা দরকার"], covered: ["This payment fits the amounts entered", "দেওয়া তথ্য অনুযায়ী পেমেন্টের টাকা আছে"],
  check_records: ["Your counted money differs from the records", "হাতে থাকা টাকা হিসাবের সঙ্গে মিলছে না"],
  recorded: ["Your money matches the records", "টাকা হিসাবের সঙ্গে মিলেছে"], review_record: ["Ready for your review", "আপনার যাচাইয়ের জন্য প্রস্তুত"],
  resolve_dispute: ["Check the bill together first", "আগে একসঙ্গে বিল যাচাই করুন"], prepare_message: ["Prepare a polite follow-up", "বাকি মনে করানোর বার্তা লিখুন"],
  verify_requirements: ["Prepare, then verify the requirements", "প্রস্তুতি নিয়ে শর্তগুলো যাচাই করুন"],
  active: ["In progress", "চলছে"], paused: ["Saved for later", "পরে করার জন্য রাখা"], completed: ["Action saved", "কাজ সেভ হয়েছে"],
  prepared: ["Prepared", "প্রস্তুত"], submitted: ["Submitted", "দাখিল করা হয়েছে"], accepted: ["Accepted / completed", "গৃহীত / সম্পন্ন"],
  needs_review: ["Needs verification", "যাচাই দরকার"], reviewed: ["Reviewed", "পর্যালোচিত"], changed: ["Source changed", "উৎস বদলেছে"], unavailable: ["Source unavailable", "উৎস পাওয়া যাচ্ছে না"],
  queued: ["Waiting to send", "পাঠানোর অপেক্ষায়"], retry: ["Will retry", "আবার চেষ্টা হবে"], sending: ["Sending", "পাঠানো হচ্ছে"],
  missed: ["The selected sending time was missed", "বাছাই করা সময়ে পাঠানো যায়নি"],
  delivered: ["Delivery confirmed", "পৌঁছানো নিশ্চিত"], unknown: ["Delivery needs checking", "পৌঁছেছে কি না যাচাই দরকার"], failed: ["Not delivered", "পৌঁছায়নি"], blocked: ["Provider setup needed", "সেবার সেটআপ দরকার"], cancelled: ["Cancelled", "বাতিল"],
};
const METRICS = {
  amount: ["Amount", "পরিমাণ"], recorded_cash: ["Recorded money", "হিসাবের টাকা"], counted_cash: ["Counted money", "গুনে পাওয়া টাকা"], difference: ["Difference", "পার্থক্য"],
  outstanding: ["Still owed", "এখনও বাকি"], available_after_commitments: ["Available after essentials", "জরুরি খরচের পর থাকবে"], needed: ["Payment needed", "দিতে হবে"], gap_now: ["Gap today", "এখন ঘাটতি"], gap_if_collected: ["Gap if customers pay", "ক্রেতারা টাকা দিলে ঘাটতি"],
  net_received: ["Money you receive", "হাতে পাবেন"], total_repaid: ["Total to repay", "মোট ফেরত দিতে হবে"], cost: ["Total financing cost", "ঋণের মোট খরচ"], usual_minimum: ["Lowest money: usual sales", "স্বাভাবিক বিক্রিতে সর্বনিম্ন টাকা"], slow_minimum: ["Lowest money: slower sales", "কম বিক্রিতে সর্বনিম্ন টাকা"], reserve: ["Money to keep safe", "হাতে রাখতে হবে"],
  needed_now: ["Money needed now", "এখন টাকা লাগবে"], cash_left: ["Money left", "হাতে থাকবে"], per_item: ["Earnings per item before fixed costs", "স্থায়ী খরচের আগে প্রতি পণ্যে আয়"], break_even_units: ["Items to cover extra fixed costs", "বাড়তি স্থায়ী খরচ তুলতে বিক্রি দরকার"], expected_contribution: ["Earnings if expected items sell", "আশামতো পণ্য বিক্রি হলে আয়"], slow_contribution: ["Earnings if half as many sell", "অর্ধেক পণ্য বিক্রি হলে আয়"], unsold_items: ["Items left in the slower case", "কম বিক্রির ক্ষেত্রে অবিক্রীত পণ্য"], collection_days: ["Days until customers pay", "ক্রেতার টাকা পেতে দিন লাগবে"],
};

export async function renderPilot(host, ctx, initialKind = "") {
  const { h, api, S } = ctx;
  const bn = S.ui === "bn", say = (en, bangla) => bn ? bangla : en;
  const txt = x => typeof x === "object" && x ? x[S.ui] || x.en || "" : String(x ?? "");
  const word = code => WORDS[code] ? say(...WORDS[code]) : say("Saved", "সেভ হয়েছে");
  const number = n => new Intl.NumberFormat(bn ? "bn-BD" : "en-BD", { maximumFractionDigits: 2 }).format(n);
  const taka = n => n == null ? say("Not known", "জানা নেই") : "৳" + number(n);
  const ownerKey = `${S.user.business_id}:${S.user.username}:`;
  const sameOwner = () => S.user && ownerKey === `${S.user.business_id}:${S.user.username}:`;
  const saveForOwner = (id, value) => { if (!sameOwner()) throw new Error("Session changed"); return saveLocal(id, value); };
  let current, editing = "", choicePage = 0, busy = false, catalog;
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const shell = h("div", { class: "pilot-page" });
  const message = h("p", { class: "pilot-status", role: "status", "aria-live": "polite" });
  const body = h("div", {});
  shell.append(h("a", { href: "#more", class: "text-link" }, say("← More", "← আরও")), body, message);
  host.replaceChildren(shell);
  const button = (label, fn, primary = false) => h("button", { type: "button", "aria-label": label, class: "btn" + (primary ? " primary" : ""), onclick: () => guard(fn) }, label);
  const link = (label, href) => h("a", { class: "text-link", href }, label);
  const errorText = e => {
    const errors = {
      conflict: ["This task changed. Reload it before continuing.", "কাজটি বদলেছে। আবার খুলে এগিয়ে যান।"], records_changed: ["Your records changed. Review the updated comparison first.", "হিসাব বদলেছে। নতুন তুলনা আগে দেখুন।"],
      need_information: ["Fill in the missing information before saving this action.", "কাজ সেভ করার আগে বাকি তথ্য দিন।"], invalid_number: ["Enter a valid amount or whole quantity.", "সঠিক পরিমাণ বা পূর্ণ সংখ্যা দিন।"], invalid_date: ["Check the date and try again.", "তারিখ যাচাই করে আবার চেষ্টা করুন।"], invalid_phone: ["Enter your Bangladesh mobile number.", "আপনার বাংলাদেশের মোবাইল নম্বর দিন।"],
      purchase_too_tight: ["Even this batch leaves too little for essentials. Try supplier terms or wait.", "এই ছোট চালানেও জরুরি টাকা কম পড়বে। সরবরাহকারীর শর্ত নিয়ে কথা বলুন বা অপেক্ষা করুন।"],
      different_accounts: ["Choose a different receiving account.", "টাকা পাওয়ার জন্য আলাদা হিসাব বাছুন।"], submission_reference: ["Add the receipt or acknowledgement reference.", "রসিদ বা প্রাপ্তিস্বীকারের নম্বর লিখুন।"],
      invoice_unavailable: ["This bill is no longer available. Check your records.", "এই বিলটি এখন নেই। হিসাব দেখুন।"], finish_questions: ["Answer the remaining questions first.", "আগে বাকি প্রশ্নের উত্তর দিন।"],
    };
    return errors[e.code] ? say(...errors[e.code]) : e.status === 403 ? say("Only the owner can confirm this action.", "শুধু মালিক এই কাজ নিশ্চিত করতে পারেন।") : say("Couldn't save. Check your connection and try again. Your input is still here.", "সেভ হয়নি। সংযোগ দেখে আবার চেষ্টা করুন। আপনার লেখা রাখা আছে।");
  };
  async function guard(fn) {
    if (busy) return;
    busy = true; shell.setAttribute("aria-busy", "true"); message.textContent = "";
    try { await fn(); } catch (e) { message.textContent = errorText(e); }
    finally { busy = false; shell.removeAttribute("aria-busy"); }
  }
  async function remember(c) {
    current = c;
    try { await saveForOwner(`case-${c.id}`, { case: c }); } catch { /* server save succeeded; local cache may be unavailable */ }
  }
  async function loadCase(id) {
    try { await remember(await api(`/api/pilot/cases/${id}`)); }
    catch (e) {
      if (e.status) throw e;
      current = (await localDrafts()).find(r => r.id === `case-${id}`)?.value.case;
      if (!current) throw e;
      message.textContent = say("Offline copy. Connect to refresh records and confirm actions.", "অফলাইন কপি। নতুন হিসাব দেখতে ও কাজ নিশ্চিত করতে সংযোগ দিন।");
    }
    drawCase();
  }
  async function start(kind) {
    const c = await api("/api/pilot/cases", { body: { kind, language: S.ui, request_key: crypto.randomUUID() } });
    location.hash = `#chat?case=${c.id}`;
  }
  function heading(title, sub) { body.replaceChildren(h("h1", { tabindex: "-1" }, title), sub ? h("p", { class: "pilot-intro" }, sub) : null); }
  function choices(items, choose, page = 0) {
    const box = h("div", { class: "pilot-choices" });
    for (const x of items.slice(page * 3, page * 3 + 3)) box.append(button(txt(x.label || x.title), () => choose(x)));
    if (!items.length) box.append(h("p", {}, say("No matching records yet.", "এখনও কোনো মিল থাকা হিসাব নেই।")), link(say("View records", "হিসাব দেখুন"), "#data"));
    if (items.length > 3) {
      const nav = h("div", { class: "pilot-inline" });
      if (page > 0) nav.append(button(say("Previous choices", "আগের বিকল্প"), () => box.replaceWith(choices(items, choose, page - 1))));
      if ((page + 1) * 3 < items.length) nav.append(button(say("More choices", "আরও বিকল্প"), () => box.replaceWith(choices(items, choose, page + 1))));
      box.append(nav);
    }
    return box;
  }
  async function landing() {
    heading(say("What would help today?", "আজ কোন কাজে সাহায্য চান?"), say("Choose one thing. We’ll work through it together.", "একটি কাজ বাছুন। ধাপে ধাপে এগিয়ে যাব।"));
    if (S.user.max_tier >= 1) body.append(choices(catalog.workflows, x => start(x.id)));
    const rows = await api("/api/pilot/cases");
    if (rows.length) {
      const list = h("div", { class: "pilot-saved" }, h("h2", {}, say("Pick up where you left off", "যেখান থেকে বাকি ছিল")));
      let shown = 0;
      const more = button(say("Show more", "আরও দেখুন"), append);
      function append() {
        rows.slice(shown, shown + 5).forEach(c => list.insertBefore(h("a", { class: "pilot-saved-row", href: `#chat?case=${c.id}` }, h("strong", {}, txt(c.title)), h("span", {}, word(c.status))), more));
        shown += 5; more.hidden = shown >= rows.length;
      }
      list.append(more); append(); body.append(list);
    }
    body.append(h("div", { class: "pilot-links" }, link(say("Saved on this device", "এই ডিভাইসে রাখা"), "#chat?tab=offline"), link(say("Documents", "কাগজপত্র"), "#chat?tab=documents"), S.user.role === "owner" ? link(say("Reminder settings", "রিমাইন্ডার সেটিংস"), "#chat?tab=notifications") : null, link(say("Get human help", "মানুষের সাহায্য নিন"), "#chat?tab=help")));
    const unusual = h("details", { class: "pilot-help" }, h("summary", {}, say("Something else?", "অন্য কিছু?")));
    const note = h("textarea", { rows: 2, maxlength: 500, "aria-label": say("Describe the problem", "সমস্যাটি বলুন") });
    unusual.append(h("p", {}, say("Describe it in your own words, including Banglish. We’ll suggest a starting task.", "নিজের ভাষায় বা বাংলিশে বলুন। শুরু করার জন্য একটি কাজ দেখাব।")), note, button(say("Find a starting point", "কোথা থেকে শুরু করব"), async () => {
      const res = await api("/api/pilot/suggest", { body: { text: note.value, language: S.ui } });
      unusual.append(choices(catalog.workflows.filter(x => res.kinds.includes(x.id)), x => start(x.id)));
    })); body.append(unusual);
  }
  function answerValue(q) {
    const v = current.answers[q.id];
    if (v == null) return say("Not known yet", "এখনও জানা নেই");
    if (q.type === "choice") return txt(q.options.find(x => x.value === String(v))?.label || v);
    if (q.type === "schedule") return `${number(v.length)} ${say("dated payments", "তারিখসহ পেমেন্ট")}`;
    return q.type === "money" ? taka(v) : q.type === "number" ? number(v) : String(v);
  }
  function answersPanel(open = false) {
    return h("details", { class: "pilot-answers", open }, h("summary", {}, say("Review or change my answers", "উত্তর দেখুন বা বদলান")),
      current.questions.filter(q => q.id in current.answers).map(q => h("div", { class: "pilot-answer" }, h("div", {}, h("span", {}, txt(q.label)), h("strong", {}, answerValue(q))), current.status !== "completed" && S.user.max_tier >= 1 ? button(say("Edit", "বদলান"), () => { editing = q.id; drawCase(); }) : null)));
  }
  async function control(action) {
    await remember(await api(`/api/pilot/cases/${current.id}/control`, { body: { version: current.version, action } }));
    if (action === "pause") location.hash = "#tasks"; else drawCase();
  }
  async function saveAnswer(q, value) {
    const key = ownerKey + current.id + ":" + q.id;
    const pending = { version: current.version, question_id: q.id, value, language: S.ui };
    try {
      const c = await api(`/api/pilot/cases/${current.id}/answer`, { body: pending });
      await remember(c); await removeLocal(`pending-${current.id}`).catch(() => {}); edits.delete(key); editing = ""; drawCase();
    } catch (e) {
      if (e.status) throw e;
      await saveForOwner(`pending-${current.id}`, { case_id: current.id, answer: pending });
      message.textContent = say("Saved on this device only. Reconnect, then open Saved on this device to send it for review.", "শুধু এই ডিভাইসে রাখা হয়েছে। সংযোগ ফিরলে ‘এই ডিভাইসে রাখা’ থেকে যাচাইয়ের জন্য পাঠান।");
    }
  }
  function scheduleInput(q, value, rememberEdit) {
    let payments = Array.isArray(value) ? value.map(p => ({ ...p })) : [];
    const box = h("div", { class: "pilot-schedule" });
    const rows = h("div", {});
    function draw() {
      rows.replaceChildren(...payments.map((p, i) => {
        const date = h("input", { type: "date", value: p.date, required: true, "aria-label": say("Payment date", "পেমেন্টের তারিখ"), oninput: e => { p.date = e.target.value; rememberEdit(payments); } });
        const amount = h("input", { inputmode: "decimal", value: p.amount, required: true, "aria-label": say("Payment amount", "পেমেন্টের টাকা"), oninput: e => { p.amount = numericInput(e.target.value); rememberEdit(payments); } });
        return h("div", { class: "pilot-payment" }, date, amount, button(say("Remove", "বাদ দিন"), () => { payments.splice(i, 1); rememberEdit(payments); draw(); }));
      }));
    }
    box.append(h("p", { class: "muted" }, say("Enter actual dates and amounts, including the last large payment. An empty list means no payments.", "শেষের বড় কিস্তিসহ আসল তারিখ ও টাকা লিখুন। ফাঁকা তালিকা মানে কোনো পেমেন্ট নেই।")), rows,
      button(say("Add a payment", "একটি পেমেন্ট যোগ"), () => { if (payments.length < 600) payments.push({ date: catalog.today, amount: "" }); rememberEdit(payments); draw(); }));
    const repeated = h("details", {}, h("summary", {}, say("Add equal instalments", "সমান কিস্তি যোগ করুন")));
    const first = h("input", { type: "date", value: catalog.today, "aria-label": say("First date", "প্রথম তারিখ") });
    const amount = h("input", { inputmode: "decimal", placeholder: say("Each amount", "প্রতি কিস্তির টাকা"), "aria-label": say("Each amount", "প্রতি কিস্তির টাকা") });
    const count = h("input", { inputmode: "numeric", placeholder: say("How many?", "কতটি?"), "aria-label": say("How many?", "কতটি?") });
    const frequency = h("select", { "aria-label": say("Frequency", "কত দিন পর") }, h("option", { value: "7" }, say("Weekly", "সাপ্তাহিক")), h("option", { value: "month" }, say("Monthly", "মাসিক")));
    repeated.append(h("div", { class: "pilot-schedule-fields" }, first, amount, count, frequency), button(say("Add and review dates", "যোগ করে তারিখ দেখুন"), () => {
      const n = Number(numericInput(count.value)), amt = Number(numericInput(amount.value));
      if (!first.value || !Number.isInteger(n) || n < 1 || n > 360 || !Number.isFinite(amt) || amt <= 0 || payments.length + n > 600) { const e = new Error(); e.code = "invalid_number"; throw e; }
      const base = new Date(first.value + "T12:00:00Z");
      for (let i = 0; i < n; i++) {
        const d = new Date(base);
        if (frequency.value === "month") { d.setUTCDate(1); d.setUTCMonth(d.getUTCMonth() + i); const last = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate(); d.setUTCDate(Math.min(last, base.getUTCDate())); }
        else d.setUTCDate(d.getUTCDate() + 7 * i);
        payments.push({ date: d.toISOString().slice(0, 10), amount: amt });
      }
      rememberEdit(payments); draw();
    })); box.append(repeated); draw();
    return { element: box, value: () => payments.map(p => ({ date: p.date, amount: numericInput(p.amount) })) };
  }
  function question(q) {
    const key = ownerKey + current.id + ":" + q.id;
    const value = edits.has(key) ? edits.get(key) : current.answers[q.id] ?? "";
    const panel = h("section", { class: "pilot-card", "aria-labelledby": "pilot-question" }, h("span", { class: "eyebrow" }, say("One step at a time", "একবারে একটি ধাপ")), h("h2", { id: "pilot-question", tabindex: "-1" }, txt(q.label)));
    if (q.why) panel.append(h("details", {}, h("summary", {}, say("Why this question?", "এই প্রশ্ন কেন?")), h("p", {}, txt(q.why))));
    if (q.type === "choice") panel.append(choices(q.options, o => saveAnswer(q, o.value), choicePage));
    else {
      let input, getValue;
      const form = h("form", { class: "pilot-form", onsubmit: e => { e.preventDefault(); guard(() => saveAnswer(q, getValue())); } });
      if (q.type === "schedule") {
        const s = scheduleInput(q, value, v => edits.set(key, v)); input = s.element; getValue = s.value;
      } else {
        input = h(q.type === "text" ? "textarea" : "input", { id: "pilot-input", type: q.type === "date" ? "date" : "text", rows: q.type === "text" ? 3 : null,
          inputmode: ["money", "number"].includes(q.type) ? "decimal" : null, required: true, maxlength: q.type === "text" ? 2000 : 32,
          value, "aria-labelledby": "pilot-question", oninput: e => edits.set(key, e.target.value) });
        if (q.type === "text") input.value = value;
        getValue = () => input.value;
      }
      form.append(input);
      if (q.type === "date" && q.id === "date") form.append(button(say("Use today", "আজকের তারিখ"), () => { input.value = catalog.today; edits.set(key, input.value); }));
      if (q.suggestion != null) form.append(h("div", { class: "pilot-fact" }, h("p", {}, say("Your records show ", "হিসাবে আছে ") + taka(q.suggestion)), button(say("Use this amount", "এই পরিমাণ ব্যবহার"), () => { input.value = q.suggestion; edits.set(key, input.value); }), h("small", {}, say("Check cash, bank and wallets. This is not a live balance.", "নগদ, ব্যাংক ও ওয়ালেট মিলিয়ে দেখুন। এটি সরাসরি ব্যাংকের ব্যালেন্স নয়।"))));
      if (q.type === "text" && (window.SpeechRecognition || window.webkitSpeechRecognition)) form.append(button(say("Use voice", "কথা বলে লিখুন"), () => {
        if (!navigator.onLine) { message.textContent = say("Voice may need a connection. You can type instead.", "কথা লিখতে সংযোগ লাগতে পারে। টাইপ করতে পারেন।"); return; }
        const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)(); recognition.lang = bn ? "bn-BD" : "en-US";
        recognition.onresult = e => { input.value = e.results[0][0].transcript; edits.set(key, input.value); message.textContent = say("Check names, amounts and dates before continuing.", "এগোনোর আগে নাম, টাকা ও তারিখ মিলিয়ে নিন।"); };
        recognition.onerror = () => { message.textContent = say("Voice was unavailable. Please type your answer.", "কথা লেখা যায়নি। উত্তর টাইপ করুন।"); };
        recognition.start();
      }));
      form.append(h("button", { type: "submit", class: "btn primary" }, say("Continue", "পরের ধাপ"))); panel.append(form);
    }
    panel.append(h("div", { class: "pilot-inline" }, button(say("I don’t know", "জানি না"), () => saveAnswer(q, null)), button(say("Do this later", "পরে করব"), () => control("pause"))));
    return panel;
  }
  function results(result) {
    const box = h("section", { class: "pilot-card" }, h("h2", {}, word(result.status)));
    const entries = Object.entries(result.metrics || {});
    const metric = ([key, v]) => h("div", { class: "pilot-metric" }, h("span", {}, say(...(METRICS[key] || [key, key]))), h("strong", {}, ["break_even_units", "unsold_items", "collection_days"].includes(key) ? v == null ? "—" : number(v) : taka(v)));
    box.append(h("div", { class: "pilot-metrics" }, entries.slice(0, 3).map(metric)));
    if (entries.length > 3) box.append(h("details", {}, h("summary", {}, say("Show calculation", "হিসাব দেখুন")), h("div", { class: "pilot-metrics" }, entries.slice(3).map(metric))));
    if (current.kind === "loan") {
      if (result.slow) box.append(h("p", {}, say("In the slower case, the lowest money is ", "কম বিক্রির হিসাবে সর্বনিম্ন টাকা ") + taka(result.slow.minimum) + say(" on ", " তারিখ ") + result.slow.minimum_date + say(". You wanted to keep ", "। হাতে রাখতে চেয়েছেন ") + taka(result.metrics.reserve) + "."));
      box.append(h("p", { class: "pilot-note" }, say("A cash scenario, not loan approval. A pilot reviewer must check your quote and timing before you decide.", "এটি টাকার সম্ভাব্য চিত্র, ঋণের অনুমোদন নয়। সিদ্ধান্তের আগে পাইলট পর্যালোচককে প্রস্তাব ও সময় যাচাই করতে হবে।")));
      const detail = h("details", {}, h("summary", {}, say("Why? See payment dates", "কেন? কিস্তির তারিখ দেখুন")), h("p", {}, say("Each 30-day period’s essential costs and existing debt are reserved upfront. Steady receipts are spread across days; uneven receipts use your dates. The slower case uses your lower sales estimate and delays receipts by seven days. These are scenarios, not predictions.", "প্রতি ৩০ দিনের জরুরি খরচ ও পুরোনো ঋণের টাকা শুরুতেই আলাদা রাখা হয়েছে। নিয়মিত আয় দিনে ভাগ করা; অনিয়মিত আয় আপনার তারিখে ধরা। কম বিক্রির হিসাবে আপনার কম আয়ের অনুমান ও সাত দিন দেরিতে টাকা পাওয়া ধরা হয়েছে। এগুলো সম্ভাব্য চিত্র, ভবিষ্যদ্বাণী নয়।")));
      (result.schedule || []).forEach(p => detail.append(h("div", { class: "pilot-answer" }, h("span", {}, p.date), h("strong", {}, taka(p.amount))))); box.append(detail);
    }
    if (current.kind === "stock") box.append(h("p", { class: "pilot-note" }, say("The slower case sells half your expected quantity. Unsold stock produces no cash in this scenario. Confirm existing bills before choosing a budget.", "কম বিক্রির হিসাবে আপনার অনুমানের অর্ধেক পণ্য বিক্রি হয়। অবিক্রীত পণ্য থেকে টাকা ধরা হয়নি। বাজেট বাছার আগে বর্তমান বিল মিলিয়ে নিন।")));
    if (result.status === "need_information") box.append(h("p", {}, say("Unknown amounts are not treated as zero. Review your answers below.", "অজানা টাকাকে শূন্য ধরা হয়নি। নিচের উত্তরগুলো দেখুন।")));
    if (result.checklist) box.append(h("details", {}, h("summary", {}, say("My preparation checklist", "আমার প্রস্তুতির তালিকা")), h("ul", {}, result.checklist.map(x => h("li", {}, h("strong", {}, txt(x.label)), h("p", {}, txt(x.detail)))))));
    if (current.kind === "record" && ["sale", "purchase"].includes(current.answers.record_type)) box.append(h("p", { class: "pilot-note" }, say("Daily totals are fine. Product profit needs item quantities and costs in Stock. A stock purchase is not the cost of stock already sold.", "দিনের মোট হিসাব রাখা যায়। পণ্যের লাভ জানতে স্টকে পরিমাণ ও খরচ দিতে হবে। পণ্য কেনা আর বিক্রি হওয়া পণ্যের খরচ এক নয়।")));
    return box;
  }
  function sourcePanel(kind) {
    const sourceList = catalog.sources.filter(s => kind === "loan" ? s.kind === "funding" : s.id === current?.answers.topic);
    const panel = h("details", { class: "pilot-sources" }, h("summary", {}, kind === "loan" ? say("Where could I enquire?", "কোথায় খোঁজ নিতে পারি?") : say("Requirements and submission help", "শর্ত ও দাখিলের সহায়তা")));
    panel.append(h("p", {}, say("These are enquiry routes. Eligibility, terms, required documents and deadlines need review for your business. No funding is guaranteed.", "এগুলো খোঁজ নেওয়ার পথ। আপনার ব্যবসার যোগ্যতা, শর্ত, কাগজপত্র ও শেষ তারিখ যাচাই করতে হবে। অর্থ পাওয়ার নিশ্চয়তা নয়।")));
    let offset = 0; const rows = h("div", {});
    const draw = () => { rows.replaceChildren(...sourceList.slice(offset, offset + 3).map(s => h("article", { class: "pilot-source" }, h("h3", {}, txt(s.title)), h("p", {}, s.authority), h("span", { class: "chip" }, word(s.status)), h("p", {}, txt(s.destination || s.audience)), s.documents ? h("p", {}, txt(s.documents)) : null, h("a", { href: s.url, target: "_blank", rel: "noopener noreferrer" }, say("Open official source", "সরকারি বা প্রতিষ্ঠানের উৎস দেখুন"))))); };
    draw(); panel.append(rows);
    if (sourceList.length > 3) panel.append(button(say("Other sources", "অন্য উৎস"), () => { offset = (offset + 3) % sourceList.length; draw(); }));
    return panel;
  }
  function drawCase() {
    heading(txt(current.title), current.status === "completed" ? say("Saved. You remain in control of the next step.", "সেভ হয়েছে। পরের পদক্ষেপ আপনার সিদ্ধান্ত।") : say("Your progress is saved as you go.", "এগোনোর সঙ্গে সঙ্গে উত্তর সেভ হয়।"));
    body.append(h("div", { class: "pilot-inline" }, h("span", { class: "chip" }, word(current.status)), link(say("All saved tasks", "সব সেভ করা কাজ"), "#chat")));
    if (current.status === "completed") {
      if (current.stale) body.append(h("p", { class: "notice" }, say("Records or sources have changed since this action was saved. Start a fresh check before relying on the comparison.", "কাজ সেভ হওয়ার পর হিসাব বা উৎস বদলেছে। তুলনার উপর নির্ভর করার আগে নতুন করে যাচাই করুন।")), button(say("Start a fresh check", "নতুন করে যাচাই"), () => start(current.kind)));
      body.append(results(current.result), answersPanel(), documents(current.documents));
      if (current.kind === "record" && current.result.status === "check_records") body.append(link(say("Review and correct records", "হিসাব দেখে ঠিক করুন"), "#data?tools=all"));
      if (current.result.human_review === "pending") body.append(h("p", { class: "notice" }, say("Waiting for pilot reviewer. Preparing this task does not submit an application or accept a loan.", "পাইলট পর্যালোচকের অপেক্ষায়। এই কাজ প্রস্তুত করলে আবেদন দাখিল বা ঋণ গ্রহণ হয় না।")));
      if (current.result.test_quantity) body.append(stockOutcome());
      if (current.result.effects?.alert_id && S.user.max_tier >= 1) body.append(reminderControls(current.result.effects.alert_id));
      if (current.kind === "shortfall" && current.result.action === "collect") body.append(link(say("Choose a customer payment to follow up", "কোন ক্রেতার বাকি চাইবেন বাছুন"), "#chat?start=collect"));
      if (["loan", "paperwork"].includes(current.kind)) body.append(sourcePanel(current.kind));
      if (current.kind === "loan") body.append(link(say("Compare saved quotes", "সেভ করা প্রস্তাব তুলনা"), "#chat?tab=compare"));
      return;
    }
    if (S.user.max_tier < 1) { body.append(answersPanel(true)); return; }
    if (current.status === "paused") { body.append(button(say("Continue this task", "এই কাজ চালিয়ে যান"), () => control("continue"), true), answersPanel()); return; }
    if (current.checkpoint_due && !editing) {
      body.append(h("section", { class: "pilot-card" }, h("h2", {}, say("A good place to pause", "এখানে একটু বিরতি নিতে পারেন")), h("p", {}, say("Six answers saved. Review what we know, then choose whether to go deeper.", "ছয়টি উত্তর রাখা হয়েছে। তথ্য দেখে চাইলে আরও এগিয়ে যান।")), answersPanel(true), h("div", { class: "pilot-inline" }, button(say("Continue deeper", "আরও এগিয়ে যান"), () => control("continue"), true), button(say("Save for later", "পরে করার জন্য রাখুন"), () => control("pause"))))); return;
    }
    const q = editing ? current.questions.find(x => x.id === editing) : current.next_question;
    if (q) { const panel = question(q); body.append(panel, answersPanel()); requestAnimationFrame(() => { if (panel.isConnected) panel.querySelector("h2").focus({ preventScroll: true }); }); return; }
    body.append(results(current.result));
    const preview = current.preview;
    if (preview?.token) {
      const panel = h("section", { class: "pilot-card pilot-review" }, h("h2", {}, say("Review the action", "কাজটি যাচাই করুন")));
      panel.append(h("p", {}, txt(current.options.find(o => o.id === preview.action)?.label)), preview.reminder_date ? h("p", {}, say("Reminder: ", "রিমাইন্ডার: ") + preview.reminder_date) : null);
      if (preview.test_quantity) panel.append(h("p", {}, `${number(preview.test_quantity)} ${say("items", "পণ্য")} · ${taka(preview.test_budget)}`));
      if (preview.body) {
        const draft = h("textarea", { rows: 9, "aria-label": say("Editable draft", "বদলানো যাবে এমন খসড়া") }); draft.value = edits.get(ownerKey + current.id + ":document") ?? preview.body;
        draft.oninput = () => { edits.set(ownerKey + current.id + ":document", draft.value); confirm.disabled = draft.value !== preview.body; };
        panel.append(h("p", {}, preview.destination), draft, button(say("Update preview", "খসড়া হালনাগাদ"), () => makePreview(preview.action, draft.value)));
      }
      const confirm = button(say("Confirm and save", "নিশ্চিত করে সেভ"), async () => {
        await remember(await api(`/api/pilot/cases/${current.id}/confirm`, { body: { version: current.version, token: preview.token } })); drawCase();
      }, true);
      confirm.disabled = S.user.role !== "owner" || !navigator.onLine || (preview.body && (edits.get(ownerKey + current.id + ":document") ?? preview.body) !== preview.body);
      panel.append(h("p", { class: "pilot-note" }, say("This saves the action and its reminder. Messages, payments and applications are not sent automatically.", "কাজ ও রিমাইন্ডার সেভ হবে। বার্তা, টাকা বা আবেদন নিজে থেকে পাঠানো হবে না।")), confirm); body.append(panel);
    } else body.append(choices(current.options, o => makePreview(o.id)));
    body.append(answersPanel(), documents(current.documents));
    if (["loan", "paperwork"].includes(current.kind)) body.append(sourcePanel(current.kind));
    if (current.kind === "shortfall") body.append(link(say("Explore a real loan quote", "আসল ঋণের প্রস্তাব যাচাই"), "#chat?start=loan"));
  }
  async function makePreview(action, text) {
    await remember(await api(`/api/pilot/cases/${current.id}/preview`, { body: { version: current.version, action, language: S.ui, text } })); drawCase();
  }
  function documents(docs) {
    const panel = h("details", { class: "pilot-documents", open: docs.length > 0 }, h("summary", {}, say("Documents and receipts", "কাগজপত্র ও রসিদ")));
    for (const d of docs) {
      const card = h("article", { class: "pilot-source" }, h("h3", {}, d.name), h("span", { class: "chip" }, word(d.stage)), link(say("Download", "ডাউনলোড"), `/api/pilot/documents/${d.id}/download`));
      if (!d.attachment) {
        const text = h("textarea", { rows: 6, readonly: d.stage !== "prepared" || S.user.role !== "owner", "aria-label": say("Document text", "কাগজের লেখা") }); text.value = edits.get(ownerKey + "doc:" + d.id) ?? d.body;
        text.oninput = () => edits.set(ownerKey + "doc:" + d.id, text.value); card.append(text);
        if (S.user.role === "owner" && d.stage === "prepared") card.append(button(say("Save edits", "পরিবর্তন সেভ"), async () => { await api(`/api/pilot/documents/${d.id}`, { method: "PATCH", body: { body: text.value } }); await loadCase(current.id); }));
        card.append(button(say("Print / save PDF", "প্রিন্ট / পিডিএফ রাখুন"), () => {
          const print = h("div", { id: "pilot-print" }, h("h1", {}, d.name), h("pre", {}, text.value)); document.body.append(print); window.print(); print.remove();
        }));
      }
      if (d.reference) card.append(h("p", {}, say("Reference: ", "নম্বর: ") + d.reference));
      if (S.user.role === "owner" && d.stage !== "accepted" && !d.attachment) {
        const ref = h("input", { placeholder: say("Receipt / acknowledgement reference", "রসিদ / প্রাপ্তিস্বীকার নম্বর"), "aria-label": say("Receipt reference", "রসিদের নম্বর"), maxlength: 180 });
        card.append(ref, button(d.stage === "prepared" ? say("I have submitted it", "আমি দাখিল করেছি") : say("It was accepted / completed", "গৃহীত / সম্পন্ন হয়েছে"), async () => { await api(`/api/pilot/documents/${d.id}`, { method: "PATCH", body: { stage: d.stage === "prepared" ? "submitted" : "accepted", reference: ref.value } }); await loadCase(current.id); }));
      } panel.append(card);
    }
    if (S.user.max_tier >= 1) {
      const file = h("input", { type: "file", accept: "application/pdf,image/png,image/jpeg", "aria-label": say("Add a quote or receipt, up to 5 MB", "প্রস্তাব বা রসিদ যোগ করুন, সর্বোচ্চ ৫ এমবি") });
      panel.append(h("label", { class: "field" }, say("Add a quote, receipt or document (PDF or photo, up to 5 MB)", "প্রস্তাব, রসিদ বা কাগজ যোগ করুন (পিডিএফ বা ছবি, সর্বোচ্চ ৫ এমবি)"), file), button(say("Save attachment", "কাগজ সেভ"), async () => {
        if (!file.files[0]) return;
        const form = new FormData(); form.append("file", file.files[0]); await api(`/api/pilot/cases/${current.id}/attachments`, { body: form }); await loadCase(current.id);
      }));
    } return panel;
  }
  function reminderControls(alert) {
    const box = h("details", {}, h("summary", {}, say("Change reminder", "রিমাইন্ডার বদলান")));
    const date = h("input", { type: "date", min: catalog.today, "aria-label": say("New reminder date", "নতুন রিমাইন্ডারের তারিখ") });
    box.append(date, button(say("Snooze / change date", "পরে দিন / তারিখ বদলান"), async () => { await api(`/api/pilot/reminders/${alert}`, { method: "PATCH", body: { due_date: date.value } }); message.textContent = say("Reminder changed.", "রিমাইন্ডার বদলেছে।"); }), button(say("Task finished — stop reminders", "কাজ শেষ — রিমাইন্ডার বন্ধ"), async () => { await api(`/api/pilot/reminders/${alert}`, { method: "PATCH", body: { complete: true } }); box.remove(); })); return box;
  }
  function stockOutcome() {
    const r = current.result, panel = h("details", {}, h("summary", {}, say("Review the product test", "পণ্যের পরীক্ষার ফল দেখুন")), h("p", {}, `${number(r.test_quantity)} ${say("items planned", "পণ্যের পরিকল্পনা")} · ${taka(r.test_budget)}`));
    const units = h("input", { inputmode: "numeric", value: r.outcome?.units_sold ?? "", "aria-label": say("Items sold", "বিক্রি হয়েছে") });
    const received = h("input", { inputmode: "decimal", value: r.outcome?.money_received ?? "", "aria-label": say("Money received", "টাকা পেয়েছেন") });
    panel.append(h("label", { class: "field" }, say("Items actually sold", "আসলে বিক্রি হয়েছে"), units), h("label", { class: "field" }, say("Money actually received", "আসলে টাকা পেয়েছেন"), received), button(say("Save outcome", "ফল সেভ করুন"), async () => { await remember(await api(`/api/pilot/cases/${current.id}/outcome`, { body: { units_sold: Number(numericInput(units.value)), money_received: Number(numericInput(received.value)) } })); drawCase(); })); return panel;
  }
  async function notifications() {
    const p = await api("/api/pilot/notifications");
    heading(say("Reminders that suit you", "আপনার সুবিধামতো রিমাইন্ডার"), say("In-app reminders stay available. Choose whether important dates may also reach your phone.", "অ্যাপের রিমাইন্ডার থাকবে। জরুরি তারিখ ফোনেও মনে করিয়ে দেব কি না বাছুন।"));
    const phone = h("input", { type: "tel", value: p.phone, autocomplete: "tel", "aria-label": say("Your mobile number", "আপনার মোবাইল নম্বর") });
    const consent = h("input", { type: "checkbox", checked: p.consent });
    const hour = h("select", { "aria-label": say("Time in Bangladesh", "বাংলাদেশের সময়") }, Array.from({ length: 15 }, (_, i) => h("option", { value: i + 7, selected: p.send_hour === i + 7 }, `${number(i + 7)}:00`)));
    body.append(h("section", { class: "pilot-card" }, h("label", { class: "field" }, say("Your mobile number", "আপনার মোবাইল নম্বর"), phone), h("label", { class: "pilot-checkbox" }, consent, say("Send me important deadline reminders by SMS", "জরুরি তারিখ এসএমএসে মনে করিয়ে দিন")), h("label", { class: "field" }, say("Preferred time (Bangladesh)", "সুবিধার সময় (বাংলাদেশ)"), hour), h("p", {}, say("At most one grouped SMS a day. Amounts and customer names stay out of messages. Uncheck this box to unsubscribe.", "দিনে সর্বোচ্চ একটি একসঙ্গে দেওয়া এসএমএস। টাকার পরিমাণ ও ক্রেতার নাম থাকবে না। বন্ধ করতে টিক তুলে দিন।")), button(say("Save preferences", "পছন্দ সেভ"), async () => { await api("/api/pilot/notifications", { method: "PUT", body: { phone: phone.value, consent: consent.checked, send_hour: Number(hour.value), language: S.ui } }); await notifications(); message.textContent = say("Preferences saved.", "পছন্দ সেভ হয়েছে।"); }, true), h("p", { class: "pilot-note" }, p.configured && p.verified ? say("Provider is configured and your number is verified. Delivery is tracked separately.", "সেবা প্রস্তুত ও নম্বর যাচাই করা। পৌঁছানো আলাদাভাবে দেখা হয়।") : say("SMS is not active until provider setup and phone ownership verification are complete. Your pilot facilitator can help.", "সেবার সেটআপ ও নম্বরের মালিকানা যাচাই শেষ না হওয়া পর্যন্ত এসএমএস চালু হবে না। পাইলট সহায়তাকারী সাহায্য করবেন।"))));
    if (p.deliveries.length) body.append(h("details", {}, h("summary", {}, say("Delivery history", "পৌঁছানোর ইতিহাস")), p.deliveries.map(d => h("p", {}, d.date + " · " + (d.status === "accepted" ? say("Provider accepted; delivery unconfirmed", "সেবা গ্রহণ করেছে; পৌঁছানো নিশ্চিত নয়") : word(d.status))))));
  }
  async function offline() {
    heading(say("Saved on this device", "এই ডিভাইসে রাখা"), say("Drafts are not business records until you reconnect, review and confirm. Signing out removes this device’s copies.", "সংযোগ দিয়ে যাচাই ও নিশ্চিত করার আগে খসড়া ব্যবসার হিসাব নয়। লগ আউট করলে এই ডিভাইসের কপি মুছে যাবে।"));
    const local = await localDrafts();
    for (const row of local.filter(x => !x.id.startsWith("case-"))) {
      body.append(h("article", { class: "pilot-card" }, h("h2", {}, row.value.note || say("An answer waiting to sync", "সার্ভারে পাঠানোর অপেক্ষায় উত্তর")), h("p", {}, say("Saved locally", "ডিভাইসে সেভ")), button(say("Send for review", "যাচাইয়ের জন্য পাঠান"), async () => {
        const d = row.value;
        if (d.answer) { await api(`/api/pilot/cases/${d.case_id}/answer`, { body: d.answer }); await removeLocal(row.id); location.hash = `#chat?case=${d.case_id}`; }
        else {
          let c = await api("/api/pilot/cases", { body: { kind: "record", language: S.ui, request_key: row.id } });
          for (const [question_id, value] of Object.entries({ record_type: d.kind, date: d.date, amount: d.amount, description: d.note })) {
            if (c.answers[question_id] == null) c = await api(`/api/pilot/cases/${c.id}/answer`, { body: { version: c.version, question_id, value, language: S.ui } });
          }
          await removeLocal(row.id); location.hash = `#chat?case=${c.id}`;
        }
      }, true), button(say("Delete local draft", "ডিভাইসের খসড়া মুছুন"), async () => { await removeLocal(row.id); await offline(); })));
    }
    for (const row of local.filter(x => x.id.startsWith("case-"))) body.append(link(txt(row.value.case.title), `#chat?case=${row.value.case.id}`));
    const note = h("textarea", { rows: 2, required: true, maxlength: 500, "aria-label": say("What happened?", "কী হয়েছে?") });
    const amount = h("input", { required: true, inputmode: "decimal", "aria-label": say("Amount", "টাকা") });
    const date = h("input", { required: true, type: "date", value: S.user.as_of || new Date().toLocaleDateString("en-CA"), "aria-label": say("Date", "তারিখ") });
    const kind = h("select", { "aria-label": say("Kind of record", "হিসাবের ধরন") }, [["sale", "Sale", "বিক্রি"], ["expense", "Expense", "খরচ"], ["purchase", "Stock purchase", "পণ্য কেনা"]].map(([v, en, bangla]) => h("option", { value: v }, say(en, bangla))));
    body.append(h("form", { class: "pilot-card pilot-form", onsubmit: e => { e.preventDefault(); guard(async () => {
      if (!Number.isFinite(Number(numericInput(amount.value))) || Number(numericInput(amount.value)) <= 0) { const e = new Error(); e.code = "invalid_number"; throw e; }
      await saveForOwner(crypto.randomUUID(), { kind: kind.value, amount: numericInput(amount.value), date: date.value, note: note.value }); await offline();
    }); } }, h("h2", {}, say("Keep a quick record draft", "ছোট হিসাবের খসড়া রাখুন")), kind, h("label", { class: "field" }, say("What happened?", "কী হয়েছে?"), note), h("label", { class: "field" }, say("Amount", "টাকা"), amount), h("label", { class: "field" }, say("Date", "তারিখ"), date), h("button", { type: "submit", class: "btn primary" }, say("Save on this device", "এই ডিভাইসে রাখুন"))));
  }
  async function allDocuments() {
    heading(say("Your documents", "আপনার কাগজপত্র"), say("Prepared, submitted and completed are separate steps.", "প্রস্তুত, দাখিল ও সম্পন্ন আলাদা ধাপ।"));
    const list = await api("/api/pilot/documents");
    if (!list.length) body.append(link(say("Prepare business paperwork", "ব্যবসার কাগজপত্র তৈরি"), "#chat?start=paperwork"));
    for (const d of list) body.append(h("a", { class: "pilot-saved-row", href: `#chat?case=${d.case_id}` }, h("strong", {}, d.name), h("span", {}, word(d.stage))));
  }
  async function compareQuotes() {
    heading(say("Compare your actual quotes", "আপনার আসল প্রস্তাব তুলনা করুন"), say("Compare money received, repayments and dates. Lender eligibility is separate from affordability.", "হাতে পাওয়া টাকা, কিস্তি ও তারিখ তুলনা করুন। ঋণ পাওয়ার যোগ্যতা ও শোধ করার সামর্থ্য আলাদা।"));
    const quotes = (await api("/api/pilot/cases")).filter(c => c.kind === "loan" && c.status === "completed" && c.result.metrics?.total_repaid != null);
    if (quotes.length < 2) { body.append(h("p", {}, say("Save two complete quotes first.", "আগে দুটি সম্পূর্ণ প্রস্তাব সেভ করুন।")), button(say("Check another quote", "আরেকটি প্রস্তাব যাচাই"), () => start("loan"), true)); return; }
    const choices = await Promise.all(quotes.map(c => api(`/api/pilot/cases/${c.id}`)));
    const selects = [0, 1].map((n) => h("select", { "aria-label": say(`Quote ${n + 1}`, `প্রস্তাব ${number(n + 1)}`) }, choices.map((c, i) => h("option", { value: c.id, selected: i === n }, `${c.answers.lender} · ${taka(c.answers.principal)} · ${c.result.confirmed_on}`))));
    const comparison = h("div", { class: "pilot-comparison" });
    const draw = () => {
      const selected = [...new Set(selects.map(s => Number(s.value)))].map(id => choices.find(c => c.id === id));
      comparison.replaceChildren(...selected.map(c => h("article", { class: "pilot-card" }, h("h2", {}, c.answers.lender), h("p", { class: "notice" }, c.stale ? say("Outdated — check again", "পুরোনো — আবার যাচাই করুন") : word(c.result.status)),
        h("div", { class: "pilot-metrics" }, ["net_received", "total_repaid", "cost", "slow_minimum"].map(key => h("div", { class: "pilot-metric" }, h("span", {}, say(...METRICS[key])), h("strong", {}, taka(c.result.metrics[key]))))),
        h("p", {}, say("Last payment: ", "শেষ কিস্তি: ") + c.result.end_date), h("p", {}, say("Security / guarantee: ", "জামানত / গ্যারান্টি: ") + c.answers.security), link(say("Review dates and assumptions", "তারিখ ও অনুমান দেখুন"), `#chat?case=${c.id}`))));
    };
    selects.forEach(s => s.onchange = draw); body.append(h("div", { class: "pilot-schedule-fields" }, selects), comparison); draw();
  }
  function help() {
    heading(say("You can ask a person", "মানুষের সাহায্য নিতে পারেন"), say("Ask your pilot facilitator to review missing records, a loan quote or paperwork with you.", "বাকি তথ্য, ঋণের প্রস্তাব বা কাগজপত্র পাইলট সহায়তাকারীকে সঙ্গে নিয়ে দেখুন।"));
    body.append(h("section", { class: "pilot-card" }, h("h2", {}, say("Pilot support", "পাইলট সহায়তা")), h("p", {}, catalog.help_contact || say("A support contact has not been set up yet. Ask the person who invited you to the pilot.", "সহায়তার যোগাযোগ এখনও দেওয়া হয়নি। যিনি পাইলটে আমন্ত্রণ করেছেন তাঁকে জানান।")), h("p", { class: "pilot-note" }, say("Only share documents you choose. The app does not send your records to lenders or advisers automatically.", "আপনি চাইলে তবেই কাগজ শেয়ার করুন। অ্যাপ নিজে থেকে ঋণদাতা বা উপদেষ্টাকে হিসাব পাঠায় না।"))));
  }
  await guard(async () => {
    if (params.get("tab") === "offline") return offline();
    try { catalog = await api("/api/pilot/catalog"); } catch (e) {
      if (e.status) throw e;
      catalog = { today: new Date().toISOString().slice(0, 10), sources: [] };
      if (!params.get("case")) return offline();
    }
    if (params.get("case")) return loadCase(Number(params.get("case")));
    if (params.get("tab") === "notifications") return notifications();
    if (params.get("tab") === "documents") return allDocuments();
    if (params.get("tab") === "compare") return compareQuotes();
    if (params.get("tab") === "help") return help();
    if (initialKind || params.get("start")) return start(initialKind || params.get("start"));
    return landing();
  });
}
