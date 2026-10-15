// SME Finance Copilot - single-page UI. Plain ES modules, no build step, works offline.
// Security: every piece of data is inserted with textContent (never innerHTML), so text from
// uploaded files or model output cannot inject markup. The session token is an HttpOnly cookie the page
// cannot read; writes carry the X-CSRF-Token header (double-submit), which other sites cannot forge.
// and is sent as a Bearer header (no cookies -> no CSRF surface).
import { barChart, hbarChart, lineChart } from "./charts.js?v=9";

// ------------------------------------------------------------------ i18n (UI chrome)
const T = {
  en: { dashboard: "Dashboard", chat: "Copilot", data: "Data", stock: "Stock", financing: "Financing", actions: "Actions",
    parties: "Customers & suppliers", s_parties: "Baki khata", invoices: "Invoices", reports: "Reports", profit_m: "Profit this month", costs_m: "Expenses by category (this month)", aging_t: "Customers owe you, by how late",
    audit: "Audit log", settings: "Privacy & settings", logout: "Log out", model: "Model", ask: "Ask in English, বাংলা or Banglish…",
    send: "Send", cash: "Cash balance", income_m: "Income this month", expense_m: "Expenses this month",
    net_last: "Net cash flow last month", gm: "Gross margin (3m)", ar_over: "Overdue from customers",
    fmin: "Lowest balance, next 30 days", runway: "Runway", forecast: "90-day cash-flow forecast",
    monthly: "Income vs expenses (12 months)", costs: "Where the money goes (last 3 months)", alerts: "Needs attention",
    howcalc: "How is this calculated?", whatif: "What-if simulator", run: "Run", login: "Log in",
    // preferences
    prefs: "Preferences", language: "Language", theme: "Theme", th_system: "Same as device", th_light: "Light", th_dark: "Dark",
    mode: "Interface", mode_simple: "Simple", mode_advanced: "Advanced", numbers: "Number format",
    mode_hint: "Simple shows only the essentials in large, plain language. Advanced shows every chart, calculation and tool.",
    all_settings: "All settings", settings_btn: "Settings", account: "Account", signed_in_as: "Signed in as",
    // simple mode
    s_home: "Home", s_ask: "Ask", s_add: "Add record", s_loans: "Loans", hello: "Hello",
    s_cash_now: "Money you have now", s_in: "Money in this month", s_out: "Money out this month", s_owed: "Customers owe you (late)",
    s_ok: "Your cash looks fine for the next 30 days.", s_low: "Cash may run short around", s_lowest: "Lowest expected balance in 30 days:",
    s_next90: "Your cash over the next 90 days", s_todo: "To do", s_nothing: "Nothing urgent. 👍", s_confirm: "Waiting for your OK",
    s_add_title: "Write what happened, in any language", s_add_ph: "e.g. sold 12 shirts for 6000 taka cash · দোকান ভাড়া ১৫০০০ দিলাম",
    s_save: "Save", s_saved: "Saved ✓", s_upload_title: "Or upload a file (sales, expenses, bank, bKash…)", s_upload: "Upload",
    s_recent: "Recent records", s_score: "Your loan-readiness score", s_improve: "How to improve", s_best: "Best options for you",
    s_amount: "How much do you need? (৳)", s_find: "Find loans", s_per_month: "per month", s_months: "months",
    s_pdf: "Make loan report (PDF)", s_dismiss: "Hide", s_ask_ph: "Ask anything about your business…",
    s_switch: "Want charts and details? Switch to Advanced in Settings.",
    // styles + dashboard sections
    style: "Style", st_general: "General", st_green: "Green", st_blue: "Blue", theme_note: "Light/Dark applies to the General style.",
    search_ph: "Search records…", range: "Date range", welcome: "Welcome back", sec_work: "What's working", sec_alerts: "Alerts",
    sec_recs: "Recommendations", qa: "Quick actions", pa: "Pending actions", tip: "Tip",
    home_layout: "Business & home layout", change_layout: "Change layout", account: "Account", show_me: "Show me", got_it: "Got it" },
  bn: { dashboard: "ড্যাশবোর্ড", chat: "কোপাইলট", data: "তথ্য", stock: "স্টক", financing: "অর্থায়ন", actions: "কাজসমূহ",
    parties: "ক্রেতা ও সরবরাহকারী", s_parties: "বাকি খাতা", invoices: "ইনভয়েস", reports: "রিপোর্ট", profit_m: "এই মাসের লাভ", costs_m: "খরচ ক্যাটাগরি অনুযায়ী (এই মাস)", aging_t: "ক্রেতাদের বকেয়া, কত দেরি",
    audit: "অডিট লগ", settings: "গোপনীয়তা ও সেটিংস", logout: "লগ আউট", model: "মডেল", ask: "ইংরেজি, বাংলা বা বাংলিশে প্রশ্ন করুন…",
    send: "পাঠান", cash: "নগদ ব্যালেন্স", income_m: "এই মাসের আয়", expense_m: "এই মাসের খরচ",
    net_last: "গত মাসের নিট নগদ প্রবাহ", gm: "গ্রস মার্জিন (৩ মাস)", ar_over: "ক্রেতাদের মেয়াদোত্তীর্ণ পাওনা",
    fmin: "আগামী ৩০ দিনে সর্বনিম্ন ব্যালেন্স", runway: "নগদ কতদিন চলবে", forecast: "৯০ দিনের নগদ প্রবাহ পূর্বাভাস",
    monthly: "আয় বনাম খরচ (১২ মাস)", costs: "টাকা কোথায় যাচ্ছে (৩ মাস)", alerts: "মনোযোগ দরকার",
    howcalc: "কীভাবে হিসাব হলো?", whatif: "'যদি' সিমুলেটর", run: "চালান", login: "লগ ইন",
    prefs: "পছন্দসমূহ", language: "ভাষা", theme: "থিম", th_system: "ডিভাইসের মতো", th_light: "লাইট", th_dark: "ডার্ক",
    mode: "ইন্টারফেস", mode_simple: "সহজ", mode_advanced: "অ্যাডভান্সড", numbers: "সংখ্যার ধরন",
    mode_hint: "সহজ মোডে শুধু জরুরি তথ্য বড় ও সহজ ভাষায় দেখায়। অ্যাডভান্সড মোডে সব চার্ট, হিসাব ও টুল দেখায়।",
    all_settings: "সব সেটিংস", settings_btn: "সেটিংস", account: "অ্যাকাউন্ট", signed_in_as: "লগ ইন করা আছেন",
    s_home: "হোম", s_ask: "জিজ্ঞাসা", s_add: "হিসাব যোগ", s_loans: "ঋণ", hello: "হ্যালো",
    s_cash_now: "এখন আপনার কাছে আছে", s_in: "এই মাসে এসেছে", s_out: "এই মাসে গেছে", s_owed: "ক্রেতাদের বকেয়া (দেরি)",
    s_ok: "আগামী ৩০ দিন আপনার নগদ ঠিক আছে।", s_low: "নগদ কম পড়তে পারে প্রায়", s_lowest: "৩০ দিনে সর্বনিম্ন আনুমানিক ব্যালেন্স:",
    s_next90: "আগামী ৯০ দিনে আপনার নগদ", s_todo: "করণীয়", s_nothing: "জরুরি কিছু নেই। 👍", s_confirm: "আপনার অনুমোদনের অপেক্ষায়",
    s_add_title: "কী হলো লিখুন, যেকোনো ভাষায়", s_add_ph: "যেমন: ১২টা শার্ট বিক্রি ৬০০০ টাকা নগদ · dokan bhara 15000 dilam",
    s_save: "সংরক্ষণ", s_saved: "সংরক্ষিত ✓", s_upload_title: "অথবা ফাইল আপলোড করুন (বিক্রি, খরচ, ব্যাংক, বিকাশ…)", s_upload: "আপলোড",
    s_recent: "সাম্প্রতিক হিসাব", s_score: "আপনার ঋণ-প্রস্তুতি স্কোর", s_improve: "কীভাবে বাড়াবেন", s_best: "আপনার জন্য সেরা বিকল্প",
    s_amount: "কত টাকা দরকার? (৳)", s_find: "ঋণ খুঁজুন", s_per_month: "প্রতি মাসে", s_months: "মাস",
    s_pdf: "ঋণ রিপোর্ট বানান (PDF)", s_dismiss: "লুকান", s_ask_ph: "আপনার ব্যবসা নিয়ে যেকোনো প্রশ্ন করুন…",
    s_switch: "চার্ট ও বিস্তারিত চান? সেটিংসে অ্যাডভান্সড চালু করুন।",
    style: "স্টাইল", st_general: "সাধারণ", st_green: "সবুজ", st_blue: "নীল", theme_note: "লাইট/ডার্ক শুধু সাধারণ স্টাইলে কাজ করে।",
    search_ph: "হিসাব খুঁজুন…", range: "সময়সীমা", welcome: "আবার স্বাগতম", sec_work: "যা ভালো চলছে", sec_alerts: "সতর্কতা",
    sec_recs: "পরামর্শ", qa: "দ্রুত কাজ", pa: "বাকি কাজ", tip: "টিপস",
    home_layout: "ব্যবসা ও হোম লেআউট", change_layout: "লেআউট বদলান", account: "অ্যাকাউন্ট", show_me: "দেখান", got_it: "বুঝেছি" },
};
const pref = (k, d) => { try { return localStorage.getItem(k) || d; } catch { return d; } };
const savePref = (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } };
const S = {
  user: null, models: null, profile: pref("profile", ""),
  ui: pref("ui_lang", "en"), style: "lakh", conv: null, health: {},
  theme: pref("theme", "system"),          // system | light | dark
  mode: pref("ui_mode", "advanced"),       // simple | advanced
  look: "general",                         // Settings > Style: general | green | blue (per user, set after login)
  counts: { overdue: 0, low_stock: 0, recurring_due: 0 },
  home: null, reg: null,                   // home_prefs (widgets, nav, style) + widget/nav registry from the server
};
const t = k => (T[S.ui] && T[S.ui][k]) || T.en[k] || k;
function applyPrefs() {
  const root = document.documentElement;
  root.dataset.style = S.look;
  const theme = S.look === "general" ? S.theme : "light";  // Green and Blue are light-only styles
  if (theme === "system") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", theme);
  root.lang = S.ui === "bn" ? "bn" : "en";
  document.body.classList.toggle("simple", S.mode === "simple");
}
applyPrefs();

// ------------------------------------------------------------------ helpers
function h(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2), v);
    else if (k === "class") e.className = v;
    else if (k === "style") e.style.cssText = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) {
    if (c === null || c === undefined || c === false) continue;
    e.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return e;
}
const $ = sel => document.querySelector(sel);
const hashParam = k => new URLSearchParams(location.hash.split("?")[1] || "").get(k);

function groupLakh(intStr) {
  if (intStr.length <= 3) return intStr;
  let head = intStr.slice(0, -3); const tail = intStr.slice(-3); const parts = [];
  while (head.length > 2) { parts.unshift(head.slice(-2)); head = head.slice(0, -2); }
  if (head) parts.unshift(head);
  return parts.join(",") + "," + tail;
}
function money(v, short = false) {
  if (v === null || v === undefined || isNaN(v)) return "–";
  const neg = v < 0; const a = Math.abs(v);
  if (short) {
    if (a >= 1e7) return (neg ? "-" : "") + "৳" + (a / 1e7).toFixed(1) + (S.style === "lakh" ? " Cr" : "0M");
    if (a >= 1e5 && S.style === "lakh") return (neg ? "-" : "") + "৳" + (a / 1e5).toFixed(1) + "L";
    if (a >= 1e6) return (neg ? "-" : "") + "৳" + (a / 1e6).toFixed(1) + "M";
    if (a >= 1e3) return (neg ? "-" : "") + "৳" + (a / 1e3).toFixed(0) + "k";
  }
  const s = Math.round(a).toString();
  return (neg ? "-" : "") + "৳" + (S.style === "lakh" ? groupLakh(s) : Number(s).toLocaleString("en-US"));
}
// Dashboard numbers count up once per session; skipped when the user prefers reduced motion.
function countUp(root) {
  if (S.counted || !window.matchMedia("(prefers-reduced-motion: no-preference)").matches) return;
  S.counted = true;
  root.querySelectorAll("[data-count]").forEach(el => {
    const end = +el.dataset.count; if (!isFinite(end) || !end) return;
    const t0 = performance.now(), dur = 700;
    const step = now => { const k = Math.min(1, (now - t0) / dur); el.textContent = money(end * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  });
}
const pct = v => (v === null || v === undefined) ? "–" : `${v}%`;
const fmtDate = s => { const d = new Date(s + "T00:00:00"); return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" }); };

function toast(msg, tone = "", ms = 3500) {
  if (typeof tone === "number") { ms = tone; tone = ""; }
  const el = h("div", { class: "toast" + (tone ? " " + tone : ""), role: "status" }, msg);
  animatedRemove(el);
  document.body.appendChild(el); setTimeout(() => el.remove(), ms);
}
// el.remove() plays the element's leave animation first (class "closing"), then removes it.
function animatedRemove(el, ms = 200) {
  el.remove = () => {
    if (el.classList.contains("closing")) return;
    el.classList.add("closing");
    setTimeout(() => Element.prototype.remove.call(el), motionOK() ? ms : 120);  // reduced motion: short fade only
  };
  return el;
}
function restartAnim(el, cls) { if (!el) return; el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls); }

function modal(title, body, actions = []) {
  const bg = animatedRemove(h("div", { class: "modal-bg", onclick: e => { if (e.target === bg) bg.remove(); } }));
  const close = h("button", { class: "btn ghost", onclick: () => bg.remove(), "aria-label": "Close" }, "✕");
  bg.appendChild(h("div", { class: "modal", role: "dialog", "aria-modal": "true" },
    h("div", { class: "row" }, h("h2", { class: "grow", style: "margin:0" }, title), close), body,
    actions.length ? h("div", { class: "row", style: "justify-content:flex-end;margin-top:14px" }, actions) : null));
  document.body.appendChild(bg);
  return bg;
}

const csrf = () => decodeURIComponent((document.cookie.match(/(?:^|; )smec_csrf=([^;]*)/) || [])[1] || "");
const motionOK = () => window.matchMedia("(prefers-reduced-motion: no-preference)").matches;
// Confirm popup for every high-risk action: shows exactly what will happen. Resolves {password, card, bg}
// on Confirm (caller closes it or plays successPop), or null on Cancel (logged to the audit trail when
// `action` is given; proposals use /reject instead).
function confirmDialog({ title, rows = [], preview, note, confirmLabel = "Confirm", danger = false, action, password = false }) {
  return new Promise(resolve => {
    const pw = password ? h("input", { type: "password", placeholder: "Your password", autocomplete: "current-password" }) : null;
    let settled = false;
    const finish = val => {
      if (settled) return; settled = true;
      if (val === null && action) api("/api/actions/cancelled", { body: { action, summary: rows.map(r => r.join(": ")).join(" · ").slice(0, 300) } }).catch(() => {});
      resolve(val);
    };
    const cancel = () => { bg.remove(); finish(null); };
    const ok = h("button", { class: "btn " + (danger ? "danger" : "primary"), onclick: () => {
      if (pw && !pw.value) { pw.focus(); return; }
      finish({ password: pw ? pw.value : undefined, card, bg });
    } }, confirmLabel);
    const card = h("div", { class: "pop-card", role: "dialog", "aria-modal": "true", "aria-label": title },
      h("h2", {}, title),
      rows.length ? h("dl", { class: "pop-rows" }, rows.flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)])) : null,
      preview ? h("div", { class: "pop-preview" }, h("div", { class: "small muted" }, "Message preview"), h("p", {}, preview)) : null,
      note ? h("p", { class: "hint" }, note) : null,
      pw ? h("label", { class: "field" }, "Re-enter your password (large amount)", pw) : null,
      h("div", { class: "row pop-actions" }, h("button", { class: "btn ghost", onclick: cancel }, "Cancel"), ok));
    const bg = animatedRemove(h("div", { class: "modal-bg pop-bg", onclick: e => { if (e.target === bg) cancel(); } }, card), 220);
    bg.addEventListener("keydown", e => { if (e.key === "Escape") cancel(); });
    document.body.appendChild(bg); (pw || ok).focus();
  });
}
function checkMark() {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg"); svg.setAttribute("viewBox", "0 0 52 52"); svg.setAttribute("class", "check-svg");
  const c = document.createElementNS(ns, "circle"); c.setAttribute("cx", "26"); c.setAttribute("cy", "26"); c.setAttribute("r", "24");
  const p = document.createElementNS(ns, "path"); p.setAttribute("d", "M15 27 l7 7 l15 -16");
  svg.append(c, p); return svg;
}
// Success: a check draws inside the card, then the card shrinks away into a toast.
function successPop(card, bg, msg) {
  card.replaceChildren(h("div", { class: "check-wrap" }, checkMark()), h("p", { class: "pop-done" }, msg));
  card.classList.add("done");
  const m = motionOK();
  setTimeout(() => { card.classList.add("to-toast"); setTimeout(() => { Element.prototype.remove.call(bg); toast(msg, "ok"); }, m ? 260 : 0); }, m ? 750 : 0);
}
function markRow(host, text) {
  if (!host) return;
  const row = host.querySelector(".row:last-child") || host;
  row.replaceChildren(h("span", { class: "chip ok sent-chip" }, text));
  restartAnim(host, "flash");
}

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const method = opts.method || (opts.body ? "POST" : "GET");
  if (method !== "GET") headers["X-CSRF-Token"] = csrf();
  let body = opts.body;
  if (body && !(body instanceof FormData) && typeof body !== "string") { headers["Content-Type"] = "application/json"; body = JSON.stringify(body); }
  const r = await fetch(path, { method, headers, body, credentials: "same-origin" });
  if (r.status === 401 && path !== "/api/auth/login") { logout(true); throw new Error("Session expired"); }
  if (!r.ok) {
    let msg = r.statusText, code = "";
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : (j.detail && j.detail.message) || JSON.stringify(j.detail); code = (j.detail && j.detail.code) || ""; } catch { /* ignore */ }
    const err = new Error(msg); err.code = code; throw err;
  }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("application/json") ? r.json() : r;
}
async function download(path, filename) {
  const r = await api(path);
  const blob = await r.blob();
  const a = h("a", { href: URL.createObjectURL(blob), download: filename });
  document.body.appendChild(a); a.click(); a.remove();
}

// ------------------------------------------------------------------ trace / explainability
function traceView(tr, title) {
  if (!tr) return h("div", { class: "muted small" }, "No calculation trace.");
  const box = h("div", { class: "trace" });
  if (title) box.appendChild(h("div", { style: "font-weight:600" }, title));
  if (tr.formula) box.appendChild(h("div", {}, h("code", {}, tr.formula)));
  if (tr.period) box.appendChild(h("div", { class: "muted small" }, "Period: " + tr.period));
  if (tr.steps && tr.steps.length) {
    const tb = h("table", { class: "t" }, h("tr", {}, h("th", {}, "Step"), h("th", { class: "r" }, "Value"), h("th", {}, "How")));
    for (const s of tr.steps) {
      const v = typeof s.value === "number" ? (Math.abs(s.value) >= 100 ? money(s.value) : String(+s.value.toFixed(4))) : (s.value ?? "–");
      tb.appendChild(h("tr", {}, h("td", {}, s.label), h("td", { class: "r" }, v), h("td", { class: "muted" }, s.expression || "")));
    }
    box.appendChild(tb);
  }
  if (tr.row_count) {
    const link = h("button", { class: "btn ghost sm", onclick: () => showRows(tr) }, `View the ${tr.row_count} ${tr.row_table || "transactions"} rows used`);
    box.appendChild(h("div", { class: "row", style: "margin-top:4px" }, link));
  }
  if (tr.sources && tr.sources.length) box.appendChild(h("div", { class: "small muted" }, "Sources: " + tr.sources.join("; ")));
  if (tr.assumptions && tr.assumptions.length) box.appendChild(h("ul", { class: "small muted" }, tr.assumptions.map(a => h("li", {}, a))));
  return box;
}
async function showRows(tr) {
  if (tr.row_table === "invoices") {
    const inv = await api("/api/data/invoices");
    const ids = new Set(tr.row_ids);
    const rows = inv.filter(i => ids.has(i.id));
    modal(`Invoices used (${tr.row_count})`, h("div", { class: "scroll" }, h("table", { class: "t" },
      h("tr", {}, ["Invoice", "Counterparty", "Due", "Amount", "Paid", "Source row"].map(x => h("th", {}, x))),
      rows.map(i => h("tr", {}, h("td", {}, i.invoice_no), h("td", {}, i.counterparty), h("td", {}, i.due_date),
        h("td", { class: "r" }, money(i.amount)), h("td", { class: "r" }, money(i.amount_paid)), h("td", {}, `${i.source} #${i.source_row ?? "–"}`))))));
    return;
  }
  const d = await api(`/api/data/transactions?ids=${tr.row_ids.slice(0, 200).join(",")}&limit=200`);
  const note = tr.row_count > tr.row_ids.length ? h("p", { class: "small muted" }, `Showing ${tr.row_ids.length} of ${tr.row_count} rows.`) : null;
  modal(`Rows used (${tr.row_count})`, h("div", {}, note, txnTable(d.rows, false)));
}

function txnTable(rows, editable, categories = [], onChange) {
  const actions = editable && onChange;
  const tb = h("table", { class: "t txn" }, h("thead", {}, h("tr", {}, ["Date", "Description / party", "Category", "Amount", "Flags", "Source", actions ? "" : null]
    .filter(x => x !== null).map((x, i) => h("th", { class: i === 3 ? "r" : "" }, x)))));
  const body = h("tbody", {});
  for (const r of rows) {
    const cat = editable ? h("select", { "aria-label": "Category", onchange: async e => {
      try { await api(`/api/data/transactions/${r.id}`, { method: "PATCH", body: { category: e.target.value } }); toast("Category updated", "ok"); } catch (err) { toast(err.message, "bad"); }
    } }, categories.map(c => h("option", { value: c, selected: c === r.category }, c.replace(/_/g, " ")))) : h("span", { class: "chip cat cat-" + catTone(r.category) }, r.category.replace(/_/g, " "));
    const tr = h("tr", { class: S.flashId === r.id ? "flash" : "" },
      h("td", { class: "num nowrap" }, r.date),
      h("td", {}, r.description || "", r.counterparty ? h("div", { class: "small muted" }, r.counterparty) : null,
        r.anomaly_reason ? h("div", { class: "small warn-text" }, "⚠ " + r.anomaly_reason) : null),
      h("td", {}, cat),
      h("td", { class: "r amt " + (r.direction === "in" ? "in" : "out") }, (r.direction === "in" ? "+" : "−") + money(r.amount).replace("-", "")),
      h("td", {}, (r.flags || []).map(f => h("span", { class: "chip flag " + (f === "injection_suspect" ? "bad" : "warn"), title: f }, f.replace(/_/g, " ")))),
      h("td", { class: "small muted" }, `${r.source}${r.source_row ? " #" + r.source_row : ""}`),
      actions ? h("td", { class: "row-actions" },
        h("button", { class: "btn ghost sm", title: "Edit", "aria-label": "Edit", onclick: () => editTxn(r, onChange) }, "✎"),
        h("button", { class: "btn ghost sm danger-text", title: "Delete", "aria-label": "Delete", onclick: e => deleteTxn(r, onChange, e.target.closest("tr")) }, "🗑")) : null);
    body.appendChild(tr);
  }
  if (rows.some(r => r.id === S.flashId)) S.flashId = null;
  tb.appendChild(body);
  return h("div", { class: "scroll sticky-head" }, tb);
}
// One colour family per category behaviour, used for chips on every page.
const CAT_TONE = { sales: "in", other_income: "in", purchase_returns: "in", loan_received: "fin", owner_capital: "fin",
  inventory: "stock", loan_repayment: "fin", equipment: "fin", owner_drawings: "fin", rent: "fixed", salary: "fixed",
  utilities: "fixed", maintenance: "fixed", tax_vat: "fixed" };
const catTone = c => CAT_TONE[c] || (c === "uncategorized" ? "none" : "var");

function editTxn(r, onDone) {
  const date = h("input", { type: "date", value: r.date });
  const amount = h("input", { type: "number", value: r.amount, min: 0, step: "any" });
  const dir = h("select", {}, [["in", "Money in"], ["out", "Money out"]].map(([k, l]) => h("option", { value: k, selected: k === r.direction }, l)));
  const desc = h("input", { type: "text", value: r.description || "" });
  const party = h("input", { type: "text", value: r.counterparty || "" });
  const err = h("div", { class: "small", style: "color:var(--critical)" });
  const m = modal("Edit record", h("div", { class: "grid", style: "gap:10px" },
    h("div", { class: "grid g-2e" }, h("label", { class: "field" }, "Date", date), h("label", { class: "field" }, "Amount ৳", amount)),
    h("label", { class: "field" }, "Money in or out", dir),
    h("label", { class: "field" }, "Description", desc), h("label", { class: "field" }, "Customer / supplier", party, h("span", { class: "hint" }, "Optional")), err),
    [h("button", { class: "btn primary", onclick: async () => {
      const body = {};
      if (date.value !== r.date) body.txn_date = date.value;
      if (+amount.value !== r.amount) body.amount = +amount.value;
      if (dir.value !== r.direction) body.direction = dir.value;
      if (desc.value !== (r.description || "")) body.description = desc.value;
      if (party.value !== (r.counterparty || "")) body.counterparty = party.value;
      if (!Object.keys(body).length) return m.remove();
      try { await api(`/api/data/transactions/${r.id}`, { method: "PATCH", body }); m.remove(); S.flashId = r.id; toast("Saved (change is in the audit log)", "ok"); onDone(); } catch (e) { err.textContent = e.message; }
    } }, "Save changes")]);
}
async function deleteTxn(r, onDone, tr) {
  const ok = await confirmDialog({ title: "Delete this record?", action: "delete_transaction", danger: true, confirmLabel: "Delete",
    rows: [["Date", r.date], ["What", r.description || r.category], ["Amount", (r.direction === "in" ? "+" : "−") + money(r.amount).replace("-", "")]],
    note: "You can undo this right after.", password: S.stepUp && r.amount >= S.stepUp });
  if (!ok) return;
  ok.bg.remove();
  try {
    const d = await api(`/api/books/transactions/${r.id}`, { method: "DELETE", body: { password: ok.password } });
    if (tr && motionOK()) { tr.classList.add("leaving"); await new Promise(res => setTimeout(res, 220)); }
    onDone();
    toast(h("span", {}, `Deleted ${money(r.amount)} · ${r.description || r.category}. `,
      h("button", { class: "btn sm", onclick: async e => { e.target.closest(".toast").remove();
        try { const x = await api(`/api/books/transactions/restore/${d.trash_id}`, { method: "POST" }); S.flashId = x.restored; toast("Restored", "ok"); onDone(); } catch (err) { toast(err.message, "bad"); } } }, "Undo")), "", 8000);
  } catch (e) { toast(e.message, "bad"); }
}

// ------------------------------------------------------------------ login
async function renderLogin(err, startTab = "login") {
  try { S.health = await (await fetch("/api/health")).json(); } catch { S.health = {}; }
  const canSignup = S.health.allow_signup !== false;
  const msg = h("div", { class: "small", style: "color:var(--critical);min-height:18px" }, err || "");
  const field = (label, input, hint) => h("label", { class: "field" }, label, input, hint ? h("span", { class: "hint" }, hint) : null);
  // Log in
  const u = h("input", { type: "text", placeholder: "username", autocomplete: "username", value: S.health.demo_users ? "nusrat" : "" });
  const p = h("input", { type: "password", placeholder: "password", autocomplete: "current-password" });
  const loginForm = h("form", { class: "grid", style: "gap:10px", onsubmit: async e => {
    e.preventDefault();
    try { await api("/api/auth/login", { body: { username: u.value, password: p.value } }); sessionStorage.removeItem("token"); boot(); }
    catch (ex) { msg.textContent = ex.message; }
  } }, field("Username", u), field("Password", p), h("button", { class: "btn primary", type: "submit" }, t("login")));
  // Create account: a new business with you as the owner; the setup wizard follows.
  const biz = h("input", { type: "text", placeholder: "e.g. Rina Beauty Salon", maxlength: 120, autocomplete: "organization" });
  const name = h("input", { type: "text", placeholder: "Your name", maxlength: 120, autocomplete: "name" });
  const nu = h("input", { type: "text", placeholder: "letters, numbers, . _ -", maxlength: 40, autocomplete: "username" });
  const np = h("input", { type: "password", minlength: 8, autocomplete: "new-password" });
  const np2 = h("input", { type: "password", minlength: 8, autocomplete: "new-password" });
  const signupForm = h("form", { class: "grid", style: "gap:10px", onsubmit: async e => {
    e.preventDefault();
    if (np.value !== np2.value) { msg.textContent = "The two passwords are different."; return; }
    try { await api("/api/auth/signup", { body: { business_name: biz.value, full_name: name.value, username: nu.value, password: np.value } }); boot(); }
    catch (ex) { msg.textContent = ex.message; }
  } }, field("Business name", biz), field("Your name", name), field("Username", nu, "You will use this to log in."),
    field("Password", np, "At least 8 characters."), field("Password again", np2), h("button", { class: "btn primary", type: "submit" }, "Create account"));
  const body = h("div", {});
  const tabs = h("div", { class: "tabs", role: "tablist" }, [["login", t("login")], ["signup", "Create account"]].map(([k, l]) =>
    h("button", { type: "button", role: "tab", class: k === startTab ? "active" : "", onclick: e => show(k, e.currentTarget) }, l)));
  const show = (k, btn) => {
    tabs.querySelectorAll("button").forEach(x => { x.classList.toggle("active", x === btn); x.setAttribute("aria-selected", String(x === btn)); });
    msg.textContent = ""; body.replaceChildren(k === "login" ? loginForm : signupForm, msg);
    (k === "login" ? (u.value ? p : u) : biz).focus();
  };
  const demo = S.health.demo_users ? h("div", { class: "notice", style: "margin-top:12px" },
    h("div", { style: "font-weight:600" }, "Demo logins (demo deployment only)"),
    S.health.demo_users.map(d => h("div", { class: "row small" }, h("span", { class: "chip" }, d.role),
      h("button", { class: "btn ghost sm", type: "button", onclick: () => { show("login", tabs.firstChild); u.value = d.username; p.value = d.password; } }, `${d.username} / ${d.password}`)))) : null;
  $("#root").replaceChildren(h("div", { class: "login" }, h("div", { class: "card" },
    h("h1", {}, "SME Finance Copilot"),
    h("p", { class: "muted" }, "Cash flow, analysis and financing for Bangladesh small businesses. ব্যবসার হিসাব, নগদ প্রবাহ ও ঋণ সহায়ক।"),
    canSignup ? tabs : null, body, demo,
    h("p", { class: "small muted", style: "margin-top:12px" }, "Decision support only - not licensed financial advice."))));
  show(canSignup ? startTab : "login", [...tabs.children].find(x => x.classList.contains("active")) || tabs.firstChild);
}
function logout(expired) {
  if (!expired) fetch("/api/auth/logout", { method: "POST", headers: { "X-CSRF-Token": csrf() }, credentials: "same-origin" });
  sessionStorage.removeItem("token"); renderLogin(expired ? "Please log in again." : "");
}

// ------------------------------------------------------------------ shell
const ROUTES = ["dashboard", "chat", "data", "invoices", "parties", "reports", "stock", "financing", "actions", "audit", "settings"];
const SIMPLE_ROUTES = ["dashboard", "chat", "data", "parties", "financing", "settings"];
const SIMPLE_LABELS = { dashboard: "s_home", chat: "s_ask", data: "s_add", parties: "s_parties", financing: "s_loans", settings: "settings_btn" };
const ICONS = { dashboard: "▦", chat: "✦", data: "⇪", invoices: "≣", parties: "☺", reports: "◔", stock: "▤", financing: "৳", actions: "✓", audit: "⛓", settings: "⚙" };
const routes = () => (S.mode === "simple" ? SIMPLE_ROUTES : ROUTES)
  .filter(r => !S.home || S.home.nav.includes(r) || r === "dashboard" || r === "settings");
const showWidget = id => !S.home || S.home.widgets.includes(id);

// Re-render everything after a preference change (language, theme, mode).
function setPref(key, value) {
  S[key] = value;
  savePref(key === "look" ? `ui_style:${S.user ? S.user.username : ""}` : { ui: "ui_lang", theme: "theme", mode: "ui_mode" }[key], value);
  if (key === "look" && S.home && S.home.exists) api("/api/home/prefs", { body: { style: value } }).then(r => { S.home = r; }).catch(() => {});
  applyPrefs();
  if (S.user) { renderShell(); route(); }
}

// Language / theme / interface / number format controls, shared by the ⚙ menu and the Settings page.
function prefControls() {
  const sel = (value, options, onchange) => h("select", { onchange: e => onchange(e.target.value) },
    options.map(([v, l]) => h("option", { value: v, selected: v === value }, l)));
  const field = (label, control) => h("label", { class: "field" }, label, control);
  const theme = sel(S.theme, [["system", t("th_system")], ["light", "☀ " + t("th_light")], ["dark", "☾ " + t("th_dark")]], v => setPref("theme", v));
  if (S.look !== "general") { theme.disabled = true; theme.title = t("theme_note"); }
  return [
    field(t("style"), sel(S.look, [["general", t("st_general")], ["green", t("st_green")], ["blue", t("st_blue")]], v => setPref("look", v))),
    field(t("language"), sel(S.ui, [["en", "English"], ["bn", "বাংলা"]], v => setPref("ui", v))),
    field(t("theme"), theme),
    field(t("mode"), sel(S.mode, [["simple", t("mode_simple")], ["advanced", t("mode_advanced")]], v => setPref("mode", v))),
    field(t("numbers"), sel(S.style, [["lakh", "৳1,00,000 (lakh)"], ["intl", "৳100,000"]], async v => {
      S.style = v; try { await api("/api/settings", { method: "PATCH", body: { number_style: v } }); } catch { /* viewer */ } route();
    })),
  ];
}

function settingsMenu() {
  const wrap = h("div", { class: "menu-wrap" });
  const panel = h("div", { class: "menu hidden", role: "menu" });
  const close = () => { panel.classList.add("hidden"); document.removeEventListener("click", outside); };
  const outside = e => { if (!wrap.contains(e.target)) close(); };
  const btn = h("button", { class: "btn sm", "aria-haspopup": "true", title: t("settings"), onclick: () => {
    if (!panel.classList.contains("hidden")) return close();
    panel.replaceChildren(
      h("div", { class: "small muted" }, `${t("signed_in_as")} `, h("b", {}, S.user.full_name || S.user.username), ` · ${S.user.role}`),
      h("div", { class: "grid", style: "gap:10px;margin:10px 0" }, prefControls()),
      h("div", { class: "row" },
        h("a", { class: "btn sm grow", href: "#settings", onclick: close }, t("all_settings")),
        h("button", { class: "btn sm danger", onclick: () => { close(); logout(false); } }, "⎋ " + t("logout"))));
    panel.classList.remove("hidden");
    setTimeout(() => document.addEventListener("click", outside));
  } }, "⚙ ", t("settings_btn"));
  wrap.append(btn, panel);
  return wrap;
}

// Avatar button: who is signed in, a link to settings, and log out.
function accountMenu(name) {
  const wrap = h("div", { class: "menu-wrap" });
  const panel = h("div", { class: "menu account-menu hidden", role: "menu" });
  const close = () => { panel.classList.add("hidden"); document.removeEventListener("click", outside); };
  const outside = e => { if (!wrap.contains(e.target)) close(); };
  const btn = h("button", { class: "avatar", "aria-haspopup": "true", title: `${name} · ${S.user.role}`, "aria-label": `${t("account")}: ${name}`, onclick: () => {
    if (!panel.classList.contains("hidden")) return close();
    panel.replaceChildren(h("div", { class: "row" }, h("span", { class: "avatar", "aria-hidden": "true" }, btn.textContent),
        h("div", {}, h("b", {}, name), h("div", { class: "small muted" }, `${S.user.username} · ${S.user.role} · ${S.user.business_name || ""}`))),
      h("div", { class: "grid", style: "gap:6px;margin-top:12px" },
        h("a", { class: "btn sm", href: "#settings", onclick: close }, "⚙ " + t("all_settings")),
        h("button", { class: "btn sm danger", onclick: () => { close(); logout(false); } }, "⎋ " + t("logout"))));
    panel.classList.remove("hidden");
    setTimeout(() => document.addEventListener("click", outside));
  } }, name.split(/\s+/).map(w => w[0]).join("").slice(0, 2).toUpperCase());
  wrap.append(btn, panel);
  return wrap;
}

async function boot() {
  try {
    const me = await fetch("/api/auth/me", { credentials: "same-origin" });  // cookie session, if any
    if (!me.ok) return renderLogin();
    S.user = await me.json();
    S.look = pref("ui_style:" + S.user.username, "general"); applyPrefs();
    S.models = await api("/api/models");
    const st = await api("/api/settings"); S.style = st.number_style; S.stepUp = st.step_up_amount;
    [S.home, S.reg] = await Promise.all([api("/api/home/prefs"), api("/api/home/registry")]);
    if (S.home.exists) { S.look = S.home.style; savePref("ui_style:" + S.user.username, S.look); applyPrefs(); }
  } catch { return; }
  if (!S.profile || !S.models.profiles.some(p => p.name === S.profile)) S.profile = S.models.default;
  renderShell();
  window.onhashchange = route;
  route();
  if (!S.home.exists) openWizard(true);
  else maybeShowTip();
}

let pendingCount = 0;
function renderShell() {
  const simple = S.mode === "simple";
  const nav = h("nav", { class: "nav", "aria-label": "Main" }, routes().filter(r => r !== "audit" || S.user.max_tier >= 1)
    .map(r => h("a", { href: "#" + r, id: "nav-" + r }, h("span", { "aria-hidden": "true" }, ICONS[r]), t(simple ? SIMPLE_LABELS[r] : r),
      r === "actions" ? h("span", { class: "badge hidden", id: "pend-badge" }, "0") : null,
      r === "invoices" || r === "stock" ? h("span", { class: "badge hidden", id: "badge-" + r }, "0") : null)));
  const name = S.user.full_name || S.user.username;
  const search = simple ? null : h("input", { type: "search", class: "top-search", placeholder: t("search_ph"), "aria-label": t("search_ph"),
    onkeydown: e => { if (e.key === "Enter" && e.target.value.trim()) location.hash = "#data?q=" + encodeURIComponent(e.target.value.trim()); } });
  const range = simple ? null : h("select", { "aria-label": t("range"), onchange: e => { const p = e.target.value; e.target.selectedIndex = 0; if (p) location.hash = "#reports?period=" + p; } },
    [["", "▦ " + t("range")], ["month", "This month"], ["last_month", "Last month"], ["quarter", "This quarter"], ["year", "This year"]].map(([v, l]) => h("option", { value: v }, l)));
  const avatar = accountMenu(name);
  const modelSel = h("select", { id: "model-select", title: "Switch the LLM per request (providers.yaml)", onchange: e => { S.profile = e.target.value; savePref("profile", S.profile); } },
    S.models.profiles.map(p => h("option", { value: p.name, selected: p.name === S.profile, disabled: !p.available },
      `${p.label}${p.external ? " ☁" : " ⌂"}${p.available ? "" : " (" + p.reason + ")"}`)));
  const privacy = h("span", { class: "chip", title: "PII (phones, account numbers, NID/TIN) is masked before any external model call" },
    S.models.local_only_mode ? "⌂ Local-only mode" : (S.models.mask_pii ? "🔒 PII masked for cloud models" : "PII masking OFF"));
  $("#root").replaceChildren(h("div", { class: "app" },
    h("aside", { class: "sidebar" }, h("div", { class: "brand" }, "SME Finance Copilot", h("span", {}, "Bangladesh · Topic E")), nav,
      h("div", { class: "foot" }, "Decision support, not licensed financial advice. Financing data is illustrative.")),
    h("div", { class: "main" },
      h("header", { class: "topbar" }, h("span", { class: "biz", id: "biz-name" }, S.user.business_name || "…"),
        simple ? null : h("span", { class: "chip", id: "asof" }, S.user.as_of ? "as of " + S.user.as_of : ""), search,
        h("span", { class: "grow" }), range, simple ? null : privacy, simple ? null : h("label", { class: "row small" }, t("model"), modelSel),
        settingsMenu(), avatar),
      h("main", { class: "view", id: "view" }))));
  refreshPending();
}
async function refreshPending() {
  try {
    const p = await api("/api/actions/pending");
    pendingCount = p.filter(x => x.status === "pending").length;
    const b = $("#pend-badge"); if (b) { b.textContent = pendingCount; b.classList.toggle("hidden", !pendingCount); }
  } catch { /* ignore */ }
  loadCounts();
}
// Counts for the sidebar badges and the "Pending actions" cards: overdue invoices, low stock, repeating items due.
async function loadCounts() {
  const [inv, st, rec] = await Promise.all([api("/api/books/invoices?status=overdue").catch(() => []),
    api("/api/stock").catch(() => ({ items: [] })), api("/api/books/recurring").catch(() => ({ due_count: 0 }))]);
  S.counts = { overdue: inv.length, low_stock: (st.items || []).filter(i => i.status !== "ok").length, recurring_due: rec.due_count || 0 };
  for (const [r, n] of [["invoices", S.counts.overdue], ["stock", S.counts.low_stock]]) {
    const b = $("#badge-" + r); if (b) { b.textContent = n; b.classList.toggle("hidden", !n); }
  }
  return S.counts;
}
function route() {
  const r = (location.hash || "#dashboard").slice(1).split("?")[0];
  const name = routes().includes(r) ? r : "dashboard";
  document.querySelectorAll(".nav a").forEach(a => a.classList.toggle("active", a.id === "nav-" + name));
  const v = $("#view"); v.replaceChildren(h("div", { class: "skeleton-block" }, h("span", { class: "skeleton-line" }), h("span", { class: "skeleton-line short" })));
  restartAnim(v, "route-enter");
  const views = S.mode === "simple"
    ? { dashboard: viewSimpleHome, chat: viewChat, data: viewSimpleData, parties: viewParties, financing: viewSimpleFinancing, settings: viewSimpleSettings }
    : { dashboard: viewDashboard, chat: viewChat, data: viewData, invoices: viewInvoices, parties: viewParties, reports: viewReports, stock: viewStock, financing: viewFinancing, actions: viewActions,
      audit: viewAudit, settings: viewSettings };
  views[name](v).catch(e => v.replaceChildren(h("div", { class: "notice warn" }, "Error: " + e.message)));
}

// ------------------------------------------------------------------ invoices
const STATUS_TONE = { draft: "", sent: "info", partial: "warn", paid: "ok", overdue: "bad", written_off: "" };
const statusBadge = s => h("span", { class: "chip status-" + s + " " + (STATUS_TONE[s] || "") }, s.replace("_", " "));
const today = () => new Date().toISOString().slice(0, 10);

async function viewInvoices(v) {
  let status = "";
  const canW = S.user.max_tier >= 1;
  const body = h("div", {});
  const filters = h("div", { class: "tabs" }, [["", "All"], ["draft", "Draft"], ["sent", "Sent"], ["partial", "Partly paid"], ["overdue", "Overdue"], ["paid", "Paid"]]
    .map(([k, l], i) => h("button", { class: i ? "" : "active", onclick: e => { filters.querySelectorAll("button").forEach(b => b.classList.remove("active")); e.target.classList.add("active"); status = k; load(); } }, l)));
  async function load() {
    const rows = await api(`/api/books/invoices${status ? "?status=" + status : ""}`);
    if (!rows.length) { body.replaceChildren(emptyState("No invoices here yet.", canW ? "New invoice" : null, () => invoiceForm(load))); return; }
    body.replaceChildren(h("div", { class: "card" }, h("div", { class: "scroll" }, h("table", { class: "t" },
      h("tr", {}, ["No.", "Type", "Customer / supplier", "Date", "Due", "Total", "Balance", "Status", ""].map((x, i) => h("th", { class: i === 5 || i === 6 ? "r" : "" }, x))),
      rows.map(i => h("tr", {},
        h("td", {}, i.invoice_no || "#" + i.id), h("td", { class: "small muted" }, i.kind === "receivable" ? "sale" : "bill"),
        h("td", {}, i.counterparty), h("td", { class: "num" }, i.issue_date), h("td", { class: "num" }, i.due_date, i.days_overdue ? h("div", { class: "small", style: "color:var(--critical)" }, `${i.days_overdue} days late`) : null),
        h("td", { class: "r" }, money(i.amount)), h("td", { class: "r", style: "font-weight:600" }, money(i.outstanding)), h("td", {}, statusBadge(i.status)),
        h("td", { class: "row-actions" },
          canW && i.status === "draft" ? h("button", { class: "btn sm primary", onclick: async () => {
            const ok = await confirmDialog({ title: "Mark as sent?", action: "send_invoice", confirmLabel: "Mark sent",
              rows: [["Invoice", i.invoice_no], ["Customer", i.counterparty], ["Amount", money(i.amount)], ["Due", i.due_date]],
              note: "This only changes the status. Nothing is emailed or texted - share the PDF yourself." });
            if (!ok) return;
            try { await api(`/api/books/invoices/${i.id}/send`, { method: "POST" }); successPop(ok.card, ok.bg, "Marked as sent"); load(); } catch (e) { ok.bg.remove(); toast(e.message, "bad"); } } }, "Mark sent") : null,
          canW && i.outstanding > 0 && i.status !== "draft" ? h("button", { class: "btn sm primary", onclick: () => paymentForm(i, load) }, "Record payment") : null,
          h("button", { class: "btn ghost sm", onclick: () => download(`/api/books/invoices/${i.id}/pdf`, `invoice_${i.invoice_no || i.id}.pdf`).catch(e => toast(e.message, "bad")) }, "PDF"))))))));
  }
  v.replaceChildren(h("div", { class: "row" }, h("h1", { class: "grow" }, t("invoices")),
    canW ? h("button", { class: "btn primary", onclick: () => invoiceForm(load) }, "+ New invoice") : null), filters, body);
  await load();
}

function invoiceForm(onDone) {
  const kind = h("select", {}, h("option", { value: "receivable" }, "Sale to a customer"), h("option", { value: "payable" }, "Bill from a supplier"));
  const party = h("input", { type: "text", placeholder: "Name" });
  const issue = h("input", { type: "date", value: today() });
  const due = h("input", { type: "date" });
  const notes = h("input", { type: "text", placeholder: "Optional note printed on the invoice" });
  const send = h("input", { type: "checkbox" });
  const lines = h("div", { class: "grid", style: "gap:6px" });
  const total = h("b", { class: "num" }, money(0));
  const recalc = () => { let s = 0; lines.querySelectorAll(".inv-line").forEach(r => { const [, q, rt] = r.querySelectorAll("input"); s += (+q.value || 0) * (+rt.value || 0); }); total.textContent = money(s); };
  const addLine = () => lines.appendChild(h("div", { class: "row inv-line" },
    h("input", { type: "text", placeholder: "Item or service", class: "grow" }),
    h("input", { type: "number", value: 1, min: 0, step: "any", style: "width:80px", oninput: recalc, "aria-label": "Quantity" }),
    h("input", { type: "number", placeholder: "Rate ৳", min: 0, step: "any", style: "width:120px", oninput: recalc, "aria-label": "Rate" })));
  addLine();
  const err = h("div", { class: "small", style: "color:var(--critical)" });
  const m = modal("New invoice", h("div", { class: "grid", style: "gap:10px" },
    h("div", { class: "grid g-2e" }, h("label", { class: "field" }, "Type", kind), h("label", { class: "field" }, "Customer / supplier", party)),
    h("div", { class: "grid g-2e" }, h("label", { class: "field" }, "Invoice date", issue), h("label", { class: "field" }, "Due date", due, h("span", { class: "hint" }, "Leave empty for 30 days"))),
    h("div", {}, h("div", { class: "small muted" }, "Items (quantity × rate)"), lines, h("button", { class: "btn ghost sm", onclick: addLine }, "+ Add item")),
    h("label", { class: "field" }, "Note", notes),
    h("label", { class: "row small" }, send, "Mark as sent now (otherwise saved as a draft)"),
    h("div", { class: "row" }, h("span", { class: "grow" }, "Total ", total), err)),
    [h("button", { class: "btn primary", onclick: async () => {
      const ls = [...lines.querySelectorAll(".inv-line")].map(r => { const [d, q, rt] = r.querySelectorAll("input"); return { description: d.value.trim(), quantity: +q.value || 1, rate: +rt.value || 0 }; }).filter(l => l.description);
      try {
        await api("/api/books/invoices", { body: { kind: kind.value, counterparty: party.value, issue_date: issue.value || null, due_date: due.value || null, notes: notes.value, send: send.checked, lines: ls } });
        m.remove(); toast("Invoice saved", "ok"); onDone && onDone();
      } catch (e) { err.textContent = e.message; }
    } }, "Save invoice")]);
  party.focus();
}

function paymentForm(inv, onDone) {
  const amt = h("input", { type: "number", value: inv.outstanding, min: 0, step: "any" });
  const date = h("input", { type: "date", value: today() });
  const ch = h("select", {}, ["cash", "bank", "bkash", "nagad", "rocket", "card"].map(c => h("option", { value: c }, c)));
  const err = h("div", { class: "small", style: "color:var(--critical)" });
  const m = modal(`Record payment · ${inv.invoice_no}`, h("div", { class: "grid", style: "gap:10px" },
    h("p", { class: "small muted", style: "margin:0" }, `${inv.counterparty} · balance due ${money(inv.outstanding)}. Enter less for a partial payment. This only records a payment that already happened.`),
    h("div", { class: "grid g-2e" }, h("label", { class: "field" }, "Amount ৳", amt), h("label", { class: "field" }, "Date", date)),
    h("label", { class: "field" }, "Paid by", ch), err),
    [h("button", { class: "btn primary", onclick: async () => {
      const ok = await confirmDialog({ title: "Record this payment?", action: "record_invoice_payment", confirmLabel: "Record payment",
        rows: [[inv.kind === "payable" ? "Paid to" : "Received from", inv.counterparty], ["Invoice", inv.invoice_no], ["Amount", money(+amt.value)], ["Paid by", ch.value], ["Date", date.value]],
        note: "This only records a payment that already happened. No money is moved.", password: S.stepUp && +amt.value >= S.stepUp });
      if (!ok) return;
      try { const r = await api(`/api/books/invoices/${inv.id}/payments`, { body: { amount: +amt.value, paid_on: date.value || null, channel: ch.value, password: ok.password } });
        m.remove(); successPop(ok.card, ok.bg, r.status === "paid" ? "Paid in full ✓" : `Partial payment saved · ${money(r.outstanding)} still due`); onDone && onDone(); } catch (e) { ok.bg.remove(); err.textContent = e.message; }
    } }, "Save payment")]);
  amt.focus();
}

// ------------------------------------------------------------------ reports
async function viewReports(v) {
  let kind = "pnl";
  const period = h("select", {}, [["month", "This month"], ["last_month", "Last month"], ["quarter", "This quarter"], ["year", "This year"], ["custom", "Custom dates"]]
    .map(([k, l]) => h("option", { value: k }, l)));
  const start = h("input", { type: "date", class: "hidden", "aria-label": "Start date" });
  const end = h("input", { type: "date", class: "hidden", "aria-label": "End date", value: today() });
  const party = h("select", { class: "hidden" }, h("option", { value: "receivable" }, "Customers owe me"), h("option", { value: "payable" }, "I owe suppliers"));
  const out = h("div", {});
  const qs = fmt => `/api/books/reports/${kind}?period=${period.value}${period.value === "custom" ? `&start=${start.value}&end=${end.value}` : ""}&party=${party.value}&fmt=${fmt}`;
  const sync = () => { const c = period.value === "custom" && kind !== "aging"; start.classList.toggle("hidden", !c); end.classList.toggle("hidden", !c);
    period.classList.toggle("hidden", kind === "aging"); party.classList.toggle("hidden", kind !== "aging"); };
  async function load() {
    sync();
    if (period.value === "custom" && kind !== "aging" && !(start.value && end.value)) { out.replaceChildren(h("div", { class: "muted" }, "Pick a start and end date.")); return; }
    let r;
    try { r = await api(qs("json")); } catch (e) { out.replaceChildren(h("div", { class: "notice warn" }, e.message)); return; }
    const bold = new Set(r.bold_rows);
    const table = h("table", { class: "t report" }, h("tr", {}, r.header.map((x, i) => h("th", { class: r.money_cols.includes(i) ? "r" : "" }, x))),
      r.rows.map((row, ri) => h("tr", { class: bold.has(ri) ? "total" : "" }, row.map((c, i) => r.money_cols.includes(i)
        ? h("td", { class: "r " + (c < 0 ? "neg" : c > 0 && bold.has(ri) && kind !== "aging" ? "pos" : "") }, money(c)) : h("td", {}, c)))));
    const chart = r.chart ? hbarChart(Object.entries(r.chart).map(([label, value]) => ({ label, value })), { fmt: x => money(x) }) : null;
    out.replaceChildren(h("div", { class: "card" },
      h("div", { class: "row" }, h("h2", { class: "grow" }, `${r.title} · ${r.period}`),
        h("button", { class: "btn ghost sm", onclick: () => download(qs("csv"), `${kind}.csv`).catch(e => toast(e.message, "bad")) }, "⇩ CSV"),
        h("button", { class: "btn primary sm", onclick: () => download(qs("pdf"), `${kind}.pdf`).catch(e => toast(e.message, "bad")) }, "⇩ PDF")),
      chart, h("div", { class: "scroll" }, table), r.notes.map(n => h("div", { class: "small muted" }, n))));
  }
  const bar = h("div", { class: "tabs" }, [["pnl", "Profit & loss"], ["cashflow", "Cash flow"], ["aging", "Who owes, how late"]].map(([k, l], i) =>
    h("button", { class: i ? "" : "active", onclick: e => { bar.querySelectorAll("button").forEach(b => b.classList.remove("active")); e.target.classList.add("active"); kind = k; load(); } }, l)));
  [period, start, end, party].forEach(x => x.addEventListener("change", load));
  if (hashParam("period")) period.value = hashParam("period");
  v.replaceChildren(h("h1", {}, t("reports")), bar, h("div", { class: "row", style: "margin-bottom:12px" }, period, start, end, party), out);
  await load();
}

// ------------------------------------------------------------------ customers & suppliers (baki ledger)
async function viewParties(v) {
  let kind = "customer";
  const body = h("div", {});
  const bar = h("div", { class: "tabs" }, [["customer", "Customers (they owe you)"], ["supplier", "Suppliers (you owe them)"]].map(([k, l], i) =>
    h("button", { class: i ? "" : "active", onclick: e => { bar.querySelectorAll("button").forEach(b => b.classList.remove("active")); e.target.classList.add("active"); kind = k; load(); } }, l)));
  async function load() {
    const d = await api(`/api/books/parties?kind=${kind}`);
    if (!d.rows.length) { body.replaceChildren(emptyState(kind === "customer" ? "No customer invoices yet." : "No supplier bills yet.")); return; }
    body.replaceChildren(
      h("div", { class: "grid g-kpi", style: "margin-bottom:16px" },
        h("div", { class: "card kpi" }, h("div", { class: "label" }, "Total balance"), h("div", { class: "value num" }, money(d.total_balance))),
        h("div", { class: "card kpi" }, h("div", { class: "label" }, "Overdue"), h("div", { class: "value num", style: d.total_overdue > 0 ? "color:var(--critical)" : "" }, money(d.total_overdue)))),
      h("div", { class: "card" }, h("div", { class: "scroll" }, h("table", { class: "t" },
        h("tr", {}, ["Name", "Invoices", "Billed", "Paid", "Balance", "Overdue", "Last activity"].map((x, i) => h("th", { class: i && i < 6 ? "r" : "" }, x))),
        d.rows.map(p => h("tr", {},
          h("td", {}, h("button", { class: "btn ghost", onclick: () => showLedger(p.name, kind) }, p.name)),
          h("td", { class: "r" }, p.invoices), h("td", { class: "r" }, money(p.invoiced)), h("td", { class: "r" }, money(p.paid)),
          h("td", { class: "r", style: "font-weight:600" }, money(p.balance)),
          h("td", { class: "r", style: p.overdue > 0 ? "color:var(--critical)" : "" }, money(p.overdue)),
          h("td", { class: "small muted" }, p.last_date || "–")))))));
  }
  v.replaceChildren(h("h1", {}, t(S.mode === "simple" ? "s_parties" : "parties")),
    h("p", { class: "small muted" }, "Click a name to see every invoice and payment with the running balance."), bar, body);
  await load();
}
async function showLedger(name, kind) {
  const d = await api(`/api/books/parties/ledger?kind=${kind}&name=${encodeURIComponent(name)}`);
  modal(`${name} · balance ${money(d.balance)}`, h("div", { class: "scroll" }, h("table", { class: "t" },
    h("tr", {}, ["Date", "Entry", "Ref", "Billed", "Paid", "Balance"].map((x, i) => h("th", { class: i > 2 ? "r" : "" }, x))),
    d.lines.map(l => h("tr", {}, h("td", { class: "num" }, l.date), h("td", {}, l.type, l.note ? h("div", { class: "small muted" }, l.note) : null), h("td", {}, l.ref),
      h("td", { class: "r" }, l.debit ? money(l.debit) : ""), h("td", { class: "r", style: "color:var(--good-text)" }, l.credit ? money(l.credit) : ""),
      h("td", { class: "r", style: "font-weight:600" }, money(l.balance)))))));
}
function emptyState(line, btnLabel, onclick) {
  return h("div", { class: "card empty" }, h("div", { class: "empty-ico", "aria-hidden": "true" }, "○"), h("p", {}, line),
    btnLabel ? h("button", { class: "btn primary", onclick }, btnLabel) : null);
}

// ------------------------------------------------------------------ stock
async function viewStock(v) {
  const owner = S.user.role === "owner";
  const body = h("div", {});
  const BADGE = { out: ["bad", "Out"], low: ["warn", "Low"], ok: ["ok", "OK"] };
  const form = async (title, fields, path, mk) => {
    const vals = {}; for (const [k, label, dflt] of fields) { const x = prompt(`${title}: ${label}`, dflt ?? ""); if (x === null) return; vals[k] = x; }
    try { await api(path, { body: mk(vals) }); load(); } catch (e) { toast(e.message, "bad"); }
  };
  const num = x => (x === "" || x == null ? 0 : Number(x));
  async function load() {
    const { items } = await api("/api/stock");
    const bar = h("div", { class: "row", style: "margin-bottom:12px" },
      h("button", { class: "btn primary", disabled: !owner, title: owner ? "" : "Owner only", onclick: () => form("New item", [["name", "Name"], ["unit", "Unit", "pcs"], ["opening_qty", "Opening quantity", "0"], ["reorder_level", "Reorder level", "0"], ["cost_price", "Cost price ৳", "0"], ["aliases", "Other names (comma separated)"]], "/api/items",
        x => ({ name: x.name, unit: x.unit || "pcs", opening_qty: num(x.opening_qty), reorder_level: num(x.reorder_level), cost_price: num(x.cost_price), aliases: x.aliases.split(",").map(a => a.trim()).filter(Boolean) })) }, "Add item"),
      h("button", { class: "btn ghost", disabled: !owner || !items.length, onclick: () => {
        const name = prompt("Adjust which item? " + items.map(i => i.name).join(", ")); const it = items.find(i => i.name.toLowerCase() === (name || "").trim().toLowerCase()); if (!it) return;
        form("Adjust " + it.name, [["q", "Change (+ adds, − removes)"], ["r", "Reason", "count correction"]], "/api/stock/adjust", x => ({ item_id: it.id, qty_change: Number(x.q), reason: (x.r || "adjust").slice(0, 30) })); } }, "Adjust"),
      h("button", { class: "btn ghost", onclick: () => download("/api/stock/export", "stock.xlsx").catch(e => toast(e.message, "bad")) }, "Export Excel"));
    body.replaceChildren(bar, items.length
      ? h("table", { class: "t" }, h("tr", {}, ["Item", "Sold 30d", "Remaining", "Days left", "Status"].map(x => h("th", {}, x))),
        items.map(i => h("tr", {}, h("td", {}, i.name), h("td", { class: "r" }, i.sold_30d), h("td", { class: "r" }, `${i.qty} ${i.unit}`),
          h("td", { class: "r" }, i.days_left ?? "–"), h("td", {}, h("span", { class: "chip " + BADGE[i.status][0] }, BADGE[i.status][1])))))
      : emptyState("No items yet. Add your products to track how much is left.", owner ? "Add item" : null, () => bar.firstChild.click()));
  }
  v.replaceChildren(h("h1", {}, t("stock")), body);
  await load();
}

// ------------------------------------------------------------------ dashboard
// One KPI card for every style: title, big number, arrow link and delta chip; Blue also shows an icon chip and a thin
// progress bar (hidden by CSS in the other styles).
function kpiCard({ label, value, sub, tone = "", count, delta, color = "blue", icon = "৳", bar, barTitle, href, info }) {
  return h("div", { class: "card kpi" + (tone ? " tone-" + tone : ""), "data-c": color },
    h("div", { class: "label" }, h("span", { class: "kpi-ico", "aria-hidden": "true" }, icon), h("span", {}, label), info || null),
    h("div", { class: "kpi-main" }, h("div", { class: "value num", "data-count": count }, value),
      href ? h("a", { class: "kpi-arrow", href, title: label, "aria-label": label }, "↗") : h("span", { class: "kpi-arrow", "aria-hidden": "true" }, "↗")),
    delta || sub ? h("div", { class: "kpi-foot" }, delta || null, sub ? h("span", { class: "sub" }, sub) : null) : null,
    bar === undefined || bar === null ? null : h("div", { class: "kpi-bar", title: barTitle || "" },
      h("i", { style: `width:${Math.max(0, Math.min(100, Math.round(bar)))}%` })));
}
// Delta chip: arrow follows the sign, colour follows whether that change is good.
function deltaChip(now, prev, goodUp = true, title = "vs last month") {
  if (!prev || now === null || now === undefined) return null;
  const p = Math.round((now - prev) / Math.abs(prev) * 100);
  return h("span", { class: "delta " + (!p ? "flat" : (p > 0) === goodUp ? "good" : "bad"), title }, (p > 0 ? "▲ " : p < 0 ? "▼ " : "") + Math.abs(p) + "%");
}
// This month vs last month, compared at the same pace (a half-finished month is scaled to a full one).
function monthPace(d) {
  const asof = new Date(d.as_of + "T00:00:00");
  const frac = asof.getDate() / new Date(asof.getFullYear(), asof.getMonth() + 1, 0).getDate();
  const lm = new Date(asof.getFullYear(), asof.getMonth() - 1, 1);
  const key = `${lm.getFullYear()}-${String(lm.getMonth() + 1).padStart(2, "0")}`;
  return { frac, last: d.monthly.find(m => m.month === key) || null };
}
function heroBanner(d) {
  const k = d.kpis, first = (S.user.full_name || S.user.username).split(" ")[0];
  const tile = (label, v) => h("div", { class: "hero-tile" }, h("span", { class: "small" }, label), h("b", {}, money(v)));
  return h("section", { class: "hero-banner", "aria-label": t("welcome") }, h("h1", {}, `${t("welcome")}, ${first}`),
    h("p", {}, `${d.business.name} · as of ${fmtDate(d.as_of)}`),
    h("div", { class: "hero-tiles" }, tile(t("s_cash_now"), k.cash_balance), tile(t("s_in"), k.income_this_month),
      tile(t("s_out"), k.expense_this_month), tile(t("s_owed"), k.receivables_outstanding)));
}
function quickActions(d) {
  const w = canWrite();
  const rem = d.alerts.map(a => a.data && a.data.suggested_tool).find(st => st && st.name === "create_payment_reminder");
  const tile = (ico, label, sub, onclick, disabled) => h("button", { class: "qa-tile", onclick, disabled },
    h("span", { class: "qa-ico", "aria-hidden": "true" }, ico), label, h("span", { class: "small" }, sub));
  return h("section", { "aria-label": t("qa"), style: "margin-top:16px" }, h("h2", {}, t("qa")), h("div", { class: "qa-grid" },
    tile("✎", "Add record", "Sale, expense or payment", () => { location.hash = "#data"; }, !w),
    tile("≣", "New invoice", "Bill a customer", () => invoiceForm(() => { location.hash = "#invoices"; }), !w),
    tile("✉", "Send reminder", rem ? "To the customer who is most late" : "See who owes you", e => rem ? runTool(rem.name, rem.args) : (location.hash = "#parties"), !w && !!rem),
    tile("৳", "Find loans", "Matched to your numbers", () => { location.hash = "#financing"; })));
}
function pendingActions(c) {
  const card = (n, label, href, tone) => h("a", { class: `pa-card t-${tone}${n ? "" : " zero"}`, href },
    h("span", { class: "count num" }, n), h("span", { class: "grow" }, label), h("span", { "aria-hidden": "true" }, "›"));
  return h("section", { "aria-label": t("pa"), style: "margin-top:16px" }, h("h2", {}, t("pa")), h("div", { class: "pa-grid" },
    card(c.overdue, "Overdue invoices", "#invoices", "bad"), card(c.low_stock, "Items low on stock", "#stock", "warn"),
    card(c.recurring_due, "Repeating items due", "#data?tab=repeating", "info")));
}
// What's working (positive signals from the KPIs), Needs attention (critical alerts), Alerts (the rest),
// Recommendations (the digest's suggested actions).
function insightSections(d, recsP) {
  const k = d.kpis, f = d.forecast, { frac, last } = monthPace(d);
  const good = [];
  if (last && last.income && k.income_this_month / frac > last.income) good.push(["Sales are ahead of last month's pace", `${money(k.income_this_month)} so far this month`]);
  if (k.profit_this_month > 0) good.push(["Profitable this month", `${money(k.profit_this_month)} after costs`]);
  if (k.gross_margin_3m !== null && k.gross_margin_3m >= 20) good.push([`Healthy gross margin: ${pct(k.gross_margin_3m)}`, "Average of the last 3 months"]);
  if (k.forecast_min_30d >= f.threshold) good.push(["Cash stays above your safety level", `Lowest in 30 days: ${money(k.forecast_min_30d)}`]);
  if (!k.receivables_overdue) good.push(["No customer is late paying", "Nothing overdue right now"]);
  if (k.runway_months === null) good.push(["Not burning cash", "More money is coming in than going out"]);
  const crit = d.alerts.filter(a => a.severity === "critical"), rest = d.alerts.filter(a => a.severity !== "critical");
  const sec = (cls, title, items, empty) => h("div", { class: "card sec-card " + cls }, h("h2", {}, title),
    items.length ? items : h("p", { class: "muted small" }, empty));
  const recCard = h("div", { class: "card sec-card s-rec" }, h("h2", {}, t("sec_recs")),
    h("div", { class: "skeleton-block" }, h("span", { class: "skeleton-line" }), h("span", { class: "skeleton-line short" })));
  const out = h("div", { class: "grid g-4s", style: "margin-top:16px" },
    sec("s-good", t("sec_work"), good.map(([a, b]) => h("div", { class: "sec-item" }, h("b", {}, "✓ " + a), h("span", { class: "muted" }, b))),
      "Keep recording sales and costs to see what is going well."),
    sec("s-attn", t("alerts"), crit.map(alertItem), "Nothing urgent. 👍"),
    sec("s-alert", t("sec_alerts"), rest.map(alertItem), "No alerts."),
    recCard);
  recsP.then(recs => recCard.replaceWith(sec("s-rec", t("sec_recs"), recs.map(r => h("div", { class: "sec-item" }, h("b", {}, r.title),
    h("span", { class: "muted" }, r.reason), h("div", { style: "margin-top:4px" }, h("button", { class: "btn sm primary", onclick: () => runTool(r.tool, r.args) }, "Do it")))),
    "No recommendations right now.")));
  return out;
}
function tipCard() {
  return h("div", { class: "card tip-card" }, h("h2", {}, "💡 " + t("tip")),
    h("p", { class: "small" }, "Lenders look at regular records. Recording every sale and uploading bank or bKash statements raises your loan-readiness score."),
    h("a", { class: "btn sm", href: "#financing" }, "Check my loan readiness"));
}

async function viewDashboard(v) {
  const d = await api("/api/dashboard");
  // After the dashboard, not alongside it: both refresh the alert table, and running them together races.
  const recs = showWidget("todo_actions") ? api("/api/digest?period=weekly").then(x => x.actions || []).catch(() => []) : null;
  $("#biz-name").textContent = d.business.name;
  $("#asof").textContent = "as of " + d.as_of;
  const k = d.kpis, { frac, last } = monthPace(d);
  const info = (label, key) => key && d.kpi_traces[key] ? h("button", { class: "btn ghost sm", title: t("howcalc"), "aria-label": t("howcalc"),
    onclick: () => modal(label, traceView(d.kpi_traces[key])) }, "ⓘ") : null;
  const paceTitle = "pace vs last month (this month so far, scaled to a full month)";
  const kpis = h("div", { class: "grid g-kpi" },
    kpiCard({ label: t("cash"), value: money(k.cash_balance), count: k.cash_balance, tone: k.cash_balance < 0 ? "bad" : "", color: "blue", icon: "৳",
      info: info(t("cash"), "cash_balance"), sub: `${t("net_last")}: ${money(k.net_last_month)}`, href: "#reports",
      delta: deltaChip(k.cash_balance, k.cash_balance - k.income_this_month + k.expense_this_month, true, "vs start of this month"),
      bar: k.cash_balance > 0 ? Math.max(0, k.forecast_min_30d) / k.cash_balance * 100 : 0, barTitle: "Share of today's cash still there at the 30-day low" }),
    kpiCard({ label: t("income_m"), value: money(k.income_this_month), count: k.income_this_month, tone: "in", color: "green", icon: "↓",
      info: info(t("income_m"), "income_this_month"), href: "#data", delta: last ? deltaChip(k.income_this_month / frac, last.income, true, paceTitle) : null,
      bar: last && last.income ? k.income_this_month / last.income * 100 : null, barTitle: "Share of last month's sales reached" }),
    kpiCard({ label: t("expense_m"), value: money(k.expense_this_month), count: k.expense_this_month, tone: "out", color: "orange", icon: "↑",
      href: "#reports", delta: last ? deltaChip(k.expense_this_month / frac, last.expense, false, paceTitle) : null,
      bar: k.income_this_month ? k.expense_this_month / k.income_this_month * 100 : null, barTitle: "Expenses as a share of income this month" }),
    kpiCard({ label: t("ar_over"), value: money(k.receivables_overdue), count: k.receivables_overdue, tone: k.receivables_overdue > 0 ? "bad" : "in",
      color: "purple", icon: "⏱", info: info(t("ar_over"), "receivables"), sub: `outstanding ${money(k.receivables_outstanding)}`, href: "#parties",
      bar: k.receivables_outstanding ? k.receivables_overdue / k.receivables_outstanding * 100 : 0, barTitle: "Share of what customers owe that is late" }));
  const kpis2 = h("div", { class: "grid g-kpi", style: "margin-top:16px" },
    kpiCard({ label: t("fmin"), value: money(k.forecast_min_30d), tone: k.forecast_min_30d < 0 ? "bad" : k.forecast_min_30d < d.forecast.threshold ? "warn" : "",
      color: "teal", icon: "◔", sub: d.forecast.first_negative_date ? `⚠ below zero around ${d.forecast.first_negative_date}` : "estimate" }),
    kpiCard({ label: t("profit_m"), value: money(k.profit_this_month), count: k.profit_this_month, tone: k.profit_this_month < 0 ? "bad" : "in", color: "green",
      icon: "＋", info: info(t("profit_m"), "profit_this_month"), sub: "sales - costs, before loans & owner drawings" }),
    kpiCard({ label: t("gm"), value: pct(k.gross_margin_3m), color: "amber", icon: "%", info: info(t("gm"), "margins"),
      sub: `net operating margin ${pct(k.net_margin_3m)}`, bar: k.gross_margin_3m }),
    kpiCard({ label: t("runway"), value: k.runway_months === null ? "not burning cash" : `${k.runway_months} months`, color: "blue", icon: "⧗",
      tone: k.runway_months !== null && k.runway_months < 3 ? "warn" : "", sub: "at current average net cash flow" }));

  // forecast chart
  const series = d.forecast.series;
  const events = {}; series.forEach(p => { if (p.events.length) events[p.date] = p.events; });
  const fcChart = lineChart({ series: [{ name: "Forecast balance", color: "var(--series-1)", points: series.map(p => ({ x: p.date, y: p.balance })) }],
    band: series.map(p => ({ x: p.date, lo: p.low, hi: p.high })), threshold: { value: d.forecast.threshold, label: `Safety level ${money(d.forecast.threshold)}` },
    events, yfmt: (v, axis) => money(v, axis), xfmt: fmtDate, xfmtLong: s => new Date(s).toDateString(), ariaLabel: "90 day cash flow forecast" });
  const fcCard = h("div", { class: "card" }, h("div", { class: "row" }, h("h2", { class: "grow" }, t("forecast")),
    h("button", { class: "btn ghost sm", onclick: async () => modal("Forecast model", traceView((await api("/api/forecast?horizon=90")).trace)) }, t("howcalc"))),
    fcChart, h("div", { class: "small muted" }, d.forecast.notes.join(" ")));

  // monthly + costs
  const months = d.monthly.slice(-12);
  const mChart = barChart({ categories: months.map(m => m.month), series: [
    { name: "Income", color: "var(--series-1)", values: months.map(m => m.income) },
    { name: "Expenses", color: "var(--series-2)", values: months.map(m => m.expense) }],
    yfmt: (v, axis) => money(v, axis), xfmt: m => new Date(m + "-01").toLocaleDateString("en-GB", { month: "short" }),
    xfmtLong: m => new Date(m + "-01").toLocaleDateString("en-GB", { month: "long", year: "numeric" }),
    extraRows: i => [["Net", money(months[i].net)]] });
  const costs = hbarChart(d.expense_breakdown.map(c => ({ label: c.category.replace(/_/g, " "), value: c.amount,
    sub: [["Share", c.share_pct + "%"], ["Previous period", money(c.previous_amount)]] })), { fmt: v => money(v) });

  const ag = d.receivables_aging || {};
  const agingChart = hbarChart([["Not yet due", "not_due"], ["0-30 days late", "0-30"], ["31-60 days late", "31-60"], ["61+ days late", "61+"]]
    .map(([label, key]) => ({ label, value: ag[key] || 0 })), { fmt: x => money(x), color: "var(--serious)" });
  const costsM = d.expense_this_month.length ? hbarChart(d.expense_this_month.map(c => ({ label: c.category.replace(/_/g, " "), value: c.amount,
    sub: [["Share", c.share_pct + "%"]] })), { fmt: x => money(x) }) : h("div", { class: "muted" }, "No expenses recorded this month yet.");
  const pending = pendingActions(S.counts);
  // Widget registry (home_prefs.widgets, in the user's order): KPI cards first, then the blocks.
  const [ck, ik, ek, ok] = kpis.children, [fk, pk, gk, rk] = kpis2.children;
  const KPI = { cash_now: [ck], money_in_out: [ik, ek], receivables_aging: [ok], profit_month: [pk, gk], cash_forecast: [fk, rk] };
  const half = el => ({ half: el }), card = (title, body) => h("div", { class: "card" }, h("h2", {}, title), body);
  const BLOCKS = {
    todo_actions: () => [quickActions(d), pending, insightSections(d, recs)],
    cash_forecast: () => [h("div", { style: "margin-top:16px" }, fcCard), whatIfCard(series)],
    money_in_out: () => [half(card(t("monthly"), mChart))],
    expenses_by_category: () => [half(card(t("costs_m"), costsM)), half(card(t("costs"), costs))],
    receivables_aging: () => [half(h("div", { class: "card" }, h("div", { class: "row" }, h("h2", { class: "grow" }, t("aging_t")),
      h("a", { href: "#reports", class: "link small" }, "Full report →")), agingChart))],
    ...ASYNC_WIDGETS,
  };
  const order = S.home ? S.home.widgets : Object.keys(BLOCKS);
  const kpiCards = order.flatMap(id => KPI[id] || []);
  v.replaceChildren(heroBanner(d), kpiCards.length ? h("div", { class: "grid g-kpi" }, kpiCards) : "",
    ...layoutBlocks([...order.flatMap(id => BLOCKS[id] ? BLOCKS[id]() : []), half(tipCard())]));
  countUp(v);
  if (showWidget("todo_actions")) loadCounts().then(c => pending.replaceWith(pendingActions(c))).catch(() => {});
}
// Full-width blocks as they are; consecutive half-width cards paired in two-column grids.
function layoutBlocks(items) {
  const out = [];
  for (const it of items) {
    if (it && it.half) {
      const last = out[out.length - 1];
      if (last && last.classList.contains("g-2e") && last.children.length < 2) last.appendChild(it.half);
      else out.push(h("div", { class: "grid g-2e", style: "margin-top:16px" }, it.half));
    } else if (it) out.push(it);
  }
  return out;
}
// Widgets that load their own data (existing endpoints); each shows a skeleton until it arrives.
function asyncCard(title, route, load) {
  const body = h("div", { class: "skeleton-block" }, h("span", { class: "skeleton-line" }), h("span", { class: "skeleton-line short" }));
  const link = route && routes().includes(route.split("?")[0]) ? h("a", { href: "#" + route, class: "link small" }, "Open →") : null;
  const el = h("div", { class: "card" }, h("div", { class: "row" }, h("h2", { class: "grow" }, title), link), body);
  load().then(x => body.replaceWith(x)).catch(e => body.replaceWith(h("div", { class: "muted small" }, e.message)));
  return { half: el };
}
const recRow = (title, sub, right) => h("div", { class: "rec" }, h("div", { class: "grow" }, h("div", {}, title), sub ? h("div", { class: "small muted" }, sub) : null), right);
const listOrEmpty = (rows, empty) => rows.length ? h("div", {}, rows) : h("p", { class: "muted small" }, empty);
const ASYNC_WIDGETS = {
  stock_alerts: () => [asyncCard("Stock running low", "stock", async () => {
    const { items } = await api("/api/stock");
    return listOrEmpty(items.filter(i => i.status !== "ok").slice(0, 6).map(i => recRow(i.name, `${i.qty} ${i.unit} left${i.days_left != null ? ` · about ${i.days_left} days` : ""}`,
      h("span", { class: "chip " + (i.status === "out" ? "bad" : "warn") }, i.status === "out" ? "Out" : "Low"))), "All items have enough stock.");
  })],
  loan_readiness: () => [asyncCard(t("s_score"), "financing", async () => {
    const rd = (await api("/api/tools/loan_readiness_score", { body: { args: {} } })).data;
    return h("div", {}, h("div", { class: "row" }, h("span", { class: "gauge num" }, rd.score), h("span", { class: "muted" }, `/ 100 · ${rd.band.replace(/_/g, " ")}`)),
      h("div", { class: "bar-track", style: "margin:8px 0" }, h("div", { class: "bar-fill", style: `width:${rd.score}%` })),
      h("ul", { class: "small" }, rd.top_tips.slice(0, 2).map(x => h("li", {}, x))));
  })],
  top_customers: () => [asyncCard("Top customers", "parties", async () => {
    const d = await api("/api/books/parties?kind=customer");
    return listOrEmpty([...d.rows].sort((a, b) => b.invoiced - a.invoiced).slice(0, 5).map(p => recRow(p.name, `billed ${money(p.invoiced)}`,
      h("span", { class: "num", style: p.overdue > 0 ? "color:var(--out);font-weight:600" : "font-weight:600" }, money(p.balance)))), "No customer invoices yet.");
  })],
  recent_records: () => [asyncCard(t("s_recent"), "data", async () => {
    const d = await api("/api/data/transactions?limit=6");
    return listOrEmpty(d.rows.map(r => recRow(r.description || r.counterparty || r.category.replace(/_/g, " "), `${fmtDate(r.date)} · ${r.category.replace(/_/g, " ")}`,
      h("span", { class: "num " + (r.direction === "in" ? "amt-in" : "amt-out"), style: "font-weight:650" }, (r.direction === "in" ? "+" : "−") + money(r.amount).replace("-", "")))), "No records yet.");
  })],
  invoices_due: () => [asyncCard("Invoices due", "invoices", async () => {
    const rows = (await api("/api/books/invoices?kind=receivable")).filter(i => i.outstanding > 0 && i.status !== "draft").sort((a, b) => a.due_date.localeCompare(b.due_date));
    return listOrEmpty(rows.slice(0, 6).map(i => recRow(`${i.counterparty} · ${i.invoice_no || "#" + i.id}`, `due ${i.due_date}`,
      h("span", { class: "row" }, h("b", { class: "num" }, money(i.outstanding)), statusBadge(i.status)))), "No invoices waiting for payment.");
  })],
  recurring_due: () => [asyncCard("Repeating items due", "data?tab=repeating", async () => {
    const d = await api("/api/books/recurring");
    return listOrEmpty(d.rows.filter(r => r.active).sort((a, b) => a.next_due.localeCompare(b.next_due)).slice(0, 6).map(r => recRow(r.name, `next ${r.next_due} · ${r.frequency}`,
      h("span", { class: "row" }, h("b", { class: "num" }, money(r.amount)), r.due_now ? h("span", { class: "chip warn" }, "due") : null))), "Nothing repeating yet.");
  })],
};

function alertItem(a) {
  const st = a.data && a.data.suggested_tool;
  return h("div", { class: "alert-item sev-" + a.severity },
    h("div", { class: "row" }, h("span", { class: "sev " + a.severity }, a.severity), a.due_date ? h("span", { class: "small muted" }, a.due_date) : null),
    h("div", { class: "title" }, a.title), h("div", { class: "msg" }, a.message),
    h("div", { class: "row", style: "margin-top:4px" },
      st ? h("button", { class: "btn sm primary", onclick: e => runTool(st.name, st.args, e.target.closest(".alert-item")) }, st.name === "create_payment_reminder" ? "Send reminder" : st.name === "pay_supplier_invoice" ? "Pay (sandbox)" : "Do it") : null,
      a.kind === "overdue_invoice" ? h("button", { class: "btn ghost sm", onclick: () => runTool("draft_invoice_followup", { invoice_id: a.data.invoice_id }) }, "Draft follow-up") : null,
      h("button", { class: "btn ghost sm", onclick: async e => { await api(`/api/alerts/${a.id}/dismissed`, { method: "POST" }); e.target.closest(".alert-item").remove(); } }, "Dismiss")));
}

async function runTool(name, args, host) {
  try {
    const out = await api(`/api/tools/${name}`, { body: { args } });
    if (out.status === "pending_confirmation") {
      if (out.tier >= 2) { confirmModal({ id: out.pending_action_id, ...out.data, tool: name }); return; }
      await proposeAndConfirm({ id: out.pending_action_id, tool: name, ...out.data }, host); return;
    }
    const d = out.data || {};
    const body = h("div", {}, d.message ? h("pre", { style: "white-space:pre-wrap" }, d.message) : null,
      d.body ? h("div", {}, h("div", { style: "font-weight:600" }, d.subject), h("pre", { style: "white-space:pre-wrap" }, d.body)) : null,
      d.download_url ? h("button", { class: "btn primary", onclick: () => download(d.download_url, d.filename) }, "Download PDF") : null,
      h("div", { class: "small muted" }, `Recorded in the operation log (${name}, tier ${out.tier}).`));
    modal("Done ✓", body);
  } catch (e) { toast(e.message, "bad"); }
}

function whatIfCard(baseSeries) {
  const kind = h("select", {}, [["delay_receivable", "A customer pays late"], ["loan", "Take a loan"], ["revenue_change", "Sales change %"],
    ["expense_change", "New monthly cost (e.g. hire)"], ["one_off", "One-off payment"]].map(([v, l]) => h("option", { value: v }, l)));
  const f1 = h("input", { type: "text", value: "biggest", style: "width:140px" });
  const f2 = h("input", { type: "number", value: "20", style: "width:120px" });
  const f3 = h("input", { type: "number", value: "12", style: "width:80px" });
  const f4 = h("input", { type: "number", value: "24", style: "width:80px" });
  const l1 = h("span", { class: "small" }), l2 = h("span", { class: "small" }), l3 = h("span", { class: "small" }), l4 = h("span", { class: "small" });
  const out = h("div", { style: "margin-top:10px" });
  const sync = () => {
    const k = kind.value;
    const cfg = { delay_receivable: ["Customer", "Days late", null, null], loan: [null, "Amount ৳", "Rate %", "Months"],
      revenue_change: [null, "Change %", null, null], expense_change: ["Category", "৳ / month", null, null], one_off: [null, "Amount ৳", "In days", null] }[k];
    [[l1, f1], [l2, f2], [l3, f3], [l4, f4]].forEach(([l, f], i) => { l.textContent = cfg[i] || ""; l.classList.toggle("hidden", !cfg[i]); f.classList.toggle("hidden", !cfg[i]); });
    if (k === "loan") { f2.value = 500000; } else if (k === "revenue_change") { f2.value = -20; } else if (k === "expense_change") { f1.value = "salary"; f2.value = 15000; } else if (k === "one_off") { f2.value = 150000; f3.value = 10; } else { f1.value = "biggest"; f2.value = 20; }
  };
  kind.addEventListener("change", sync);
  const run = async () => {
    const k = kind.value; const sc = { kind: k };
    if (k === "delay_receivable") Object.assign(sc, { customer: f1.value, days: +f2.value });
    if (k === "loan") Object.assign(sc, { amount: +f2.value, annual_rate_pct: +f3.value, months: +f4.value });
    if (k === "revenue_change") sc.pct = +f2.value;
    if (k === "expense_change") Object.assign(sc, { category: f1.value, monthly_amount: +f2.value });
    if (k === "one_off") Object.assign(sc, { amount: +f2.value, start_in_days: +f3.value, direction: "out" });
    try {
      const r = await api("/api/whatif", { body: { scenarios: [sc], horizon_days: 90 } });
      const chart = lineChart({ series: [
        { name: "Current forecast", color: "var(--series-1)", points: r.baseline_series.map(p => ({ x: p.date, y: p.balance })) },
        { name: "Scenario", color: "var(--series-2)", dashed: true, points: r.scenario_series.map(p => ({ x: p.date, y: p.balance })) }],
        yfmt: (v, axis) => money(v, axis), xfmt: fmtDate, height: 220, ariaLabel: "what-if comparison" });
      out.replaceChildren(h("ul", { class: "plain" }, r.explanation.map(x => h("li", {}, x))), chart,
        h("button", { class: "btn ghost sm", onclick: () => modal("What-if calculation", traceView(r.trace)) }, t("howcalc")));
    } catch (e) { out.replaceChildren(h("div", { class: "notice warn" }, e.message)); }
  };
  sync();
  return h("div", { class: "card", style: "margin-top:16px" }, h("h2", {}, t("whatif")),
    h("div", { class: "row" }, kind, l1, f1, l2, f2, l3, f3, l4, f4, h("button", { class: "btn primary", onclick: run }, t("run"))), out);
}

// ------------------------------------------------------------------ chat
const SUGGESTIONS = [
  "What needs my attention this week?", "How did I do last month and why did it change?",
  "What if my biggest customer pays 20 days late?", "Which loans fit me for 5 lakh to buy winter stock?",
  "গত ৩ মাসে আমার লাভ কত?", "amar loan readiness score koto?", "Send a payment reminder to Karim Knit",
  "sold 40 zippers for 3200 taka cash", "Transfer 25000 to Dhaka Zipper House for stock", "Make me a fake invoice for the bank",
];

const SIMPLE_SUGGESTIONS = {
  en: ["What needs my attention this week?", "How much profit did I make last month?", "Which loans fit me?", "Send a payment reminder to Karim Knit"],
  bn: ["এই সপ্তাহে কী নিয়ে ভাবা দরকার?", "গত মাসে লাভ কত হলো?", "আমার জন্য কোন ঋণ ভালো?", "করিম নিটকে পেমেন্টের রিমাইন্ডার পাঠাও"],
};

async function viewChat(v) {
  const log = h("div", { class: "log", id: "chatlog", "aria-live": "polite" });
  const input = h("input", { type: "text", placeholder: t("ask"), "aria-label": "Message", maxlength: 2000 });
  const send = async text => {
    text = (text ?? input.value).trim(); if (!text) return;
    input.value = "";
    log.appendChild(h("div", { class: "msg user" }, text));
    const bot = h("div", { class: "msg bot" }, h("div", { class: "typing" }, "Thinking…"));
    log.appendChild(bot); log.scrollTop = log.scrollHeight;
    try { await streamChat(text, bot, log); } catch (e) { bot.replaceChildren(h("div", { class: "notice warn" }, e.message)); }
  };
  input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
  const mic = voiceButton(input, send);
  if (S.mode === "simple") {
    input.placeholder = t("s_ask_ph");
    const chips = h("div", { class: "row", style: "margin-top:10px" }, SIMPLE_SUGGESTIONS[S.ui === "bn" ? "bn" : "en"]
      .map(s => h("button", { class: "btn sm", onclick: () => send(s) }, s)));
    v.replaceChildren(h("div", { class: "chat chat-simple" }, h("div", { class: "card panel" }, log, chips,
      h("div", { class: "composer" }, input, mic, h("button", { class: "btn primary", onclick: () => send() }, t("send"))))));
    log.appendChild(h("div", { class: "msg bot" }, h("div", { class: "text" }, S.ui === "bn"
      ? "আসসালামু আলাইকুম! আপনার ব্যবসার বিক্রি, খরচ, নগদ বা ঋণ নিয়ে যেকোনো প্রশ্ন করুন।"
      : "Assalamu alaikum! Ask me anything about your sales, costs, cash or loans.")));
    input.focus();
    return;
  }
  const panel = h("div", { class: "card panel" }, log,
    h("div", { class: "composer" }, input, mic, h("button", { class: "btn primary", onclick: () => send() }, t("send"))));
  const side = h("div", { class: "card suggest" }, h("h2", {}, "Try"), SUGGESTIONS.map(s => h("button", { class: "btn sm", onclick: () => send(s) }, s)),
    h("p", { class: "small muted" }, "Every number comes from a deterministic tool - open “Show calculation” under any answer. Money moves only in the sandbox and only after you confirm."));
  v.replaceChildren(h("div", { class: "chat" }, panel, side));
  log.appendChild(h("div", { class: "msg bot" }, h("div", { class: "text" },
    "Assalamu alaikum! I'm your finance copilot. Ask about sales, costs, cash flow, loans - in English, বাংলা or Banglish. I can also record entries, draft reminders and prepare loan reports.")));
  input.focus();
}

function voiceButton(input, send) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return h("button", { class: "btn", disabled: true, title: "Voice input not supported in this browser" }, "🎤");
  const b = h("button", { class: "btn mic", title: "Voice input (uses the browser's speech service)" }, "🎤");
  let rec = null;
  b.addEventListener("click", () => {
    if (rec) { rec.stop(); return; }
    rec = new SR(); rec.lang = S.ui === "bn" ? "bn-BD" : "en-US"; rec.interimResults = false;
    rec.onresult = e => { input.value = e.results[0][0].transcript; send(); };
    rec.onend = () => { rec = null; b.classList.remove("on"); };
    b.classList.add("on"); rec.start();
  });
  return b;
}

async function streamChat(text, bot, log) {
  const r = await fetch("/api/chat/stream", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
    body: JSON.stringify({ message: text, conversation_id: S.conv, profile: S.profile || null }) });
  if (r.status === 401) { logout(true); return; }
  if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
  const reader = r.body.getReader(); const dec = new TextDecoder();
  let buf = ""; const textEl = h("div", { class: "text" }); const progress = h("div", { class: "meta" });
  bot.replaceChildren(progress, textEl);
  for (;;) {
    const { value, done } = await reader.read(); if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
      const ev = (chunk.match(/^event: (.*)$/m) || [])[1]; const data = (chunk.match(/^data: (.*)$/m) || [])[1];
      if (!ev || !data) continue;
      const p = JSON.parse(data);
      if (ev === "tool") { if (S.mode !== "simple") progress.appendChild(toolChip(p)); }
      else if (ev === "delta") { textEl.textContent += p.text; log.scrollTop = log.scrollHeight; }
      else if (ev === "done") renderBotMessage(bot, p, text);
      else if (ev === "error") bot.replaceChildren(h("div", { class: "notice warn" }, p.detail));
    }
  }
  log.scrollTop = log.scrollHeight;
}

function toolChip(tc) {
  const cls = tc.status === "ok" ? "ok" : tc.status === "pending_confirmation" ? "pend" : "bad";
  return h("span", { class: `chip tier${tc.tier ?? 0} ${cls}`, title: tc.message || "" }, `${tc.tool} · T${tc.tier ?? "?"} · ${tc.status.replace("_", " ")}`);
}

function renderBotMessage(bot, d, question) {
  S.conv = d.conversation_id;
  const meta = h("div", { class: "meta" }, d.tool_calls.map(toolChip),
    h("span", { class: `chip${d.fallback ? " bad" : ""}`, title: (d.attempts || []).map(a => `${a.profile}: ${a.ok ? "ok" : a.error}`).join("\n") },
      `${d.profile || "no model"} · ${d.language}`),
    d.fallback ? h("span", { class: "chip bad" }, `fallback: ${d.profile || "none"}`) : null,
    d.latency_ms ? h("span", { class: "chip" }, `${Math.round(d.latency_ms)} ms`) : null,
    d.refused ? h("span", { class: "chip bad" }, "refused (policy)") : null);
  const parts = [];
  if (S.mode === "simple") {  // plain answer + anything that needs the owner's action; details stay in Advanced
    parts.push(h("div", { class: "text" }, d.reply));
    for (const pa of d.pending_actions || []) parts.push(confirmCard(pa));
    bot.replaceChildren(...parts);
    if ((d.pending_actions || []).length) refreshPending();
    return;
  }
  if (d.fallback) parts.push(h("div", { class: "notice warn small", style: "margin-bottom:6px" },
    `⚠ ${d.requested_profile} did not answer${d.profile ? `; this reply is from ${d.profile}` : ""}. Reason: ${d.fallback_reason}`));
  parts.push(h("div", { class: "text" }, d.reply), meta);
  if (d.ungrounded_numbers && d.ungrounded_numbers.length) parts.push(h("div", { class: "notice warn small", style: "margin-top:6px" },
    `⚠ Could not verify these numbers against your data: ${d.ungrounded_numbers.join(", ")}. Treat them with caution.`));
  for (const pa of d.pending_actions || []) parts.push(confirmCard(pa));
  if (d.traces && d.traces.length) {
    const det = h("details", {}, h("summary", {}, `Show calculation (${d.traces.length})`), d.traces.map(tr => traceView(tr, tr.tool)));
    parts.push(det);
  }
  if (d.disclaimer) parts.push(h("div", { class: "small muted", style: "margin-top:6px" }, "ℹ " + d.disclaimer));
  parts.push(feedbackRow(d.interaction_id));
  bot.replaceChildren(...parts);
  if ((d.pending_actions || []).length) refreshPending();
}

function feedbackRow(id) {
  const corr = h("input", { type: "text", placeholder: "What should the answer have been? (optional)", class: "grow hidden" });
  const sendFb = async rating => {
    try { await api("/api/feedback", { body: { interaction_id: id, rating, correction: corr.value || null } }); row.replaceChildren(h("span", { class: "small muted" }, "Thanks - feedback saved for evaluation.")); } catch (e) { toast(e.message, "bad"); }
  };
  const row = h("div", { class: "row", style: "margin-top:6px" },
    h("button", { class: "btn ghost sm", title: "Helpful", onclick: () => sendFb("up") }, "👍"),
    h("button", { class: "btn ghost sm", title: "Not helpful", onclick: () => { if (corr.classList.contains("hidden")) { corr.classList.remove("hidden"); corr.focus(); } else sendFb("down"); } }, "👎"), corr);
  corr.addEventListener("keydown", e => { if (e.key === "Enter") sendFb("down"); });
  return row;
}

// ------------------------------------------------------------------ human-in-the-loop confirmation
// Reminders and loan reports are only PROPOSED by the copilot or a button; nothing happens until this click.
async function proposeAndConfirm(pa, host) {
  const reminder = pa.tool === "create_payment_reminder";
  const ok = await confirmDialog({ title: reminder ? "Send this reminder?" : "Create the loan report?",
    rows: reminder ? [["To", pa.recipient], ["Amount due", money(pa.amount)]] : [], preview: pa.preview || null,
    note: pa.summary, confirmLabel: reminder ? "Send reminder" : "Create report" });
  if (!ok) { api(`/api/actions/${pa.id}/reject`, { method: "POST" }).catch(() => {}); refreshPending(); return null; }
  try {
    const r = await api(`/api/actions/${pa.id}/confirm`, { body: {} });
    if (r.status !== "ok") throw new Error(r.message || r.status);
    successPop(ok.card, ok.bg, reminder ? `Reminder sent to ${pa.recipient} (sandbox outbox)` : "Loan report ready ✓");
    if (reminder) markRow(host, "✓ Reminder sent");
    else if (r.data && r.data.download_url) setTimeout(() => toast(h("span", {}, "Loan report ready. ",
      h("button", { class: "btn sm", onclick: () => download(r.data.download_url, r.data.filename) }, "Download PDF")), "ok", 9000), 1100);
    refreshPending(); return r;
  } catch (e) { ok.bg.remove(); toast(e.message, "bad"); return null; }
}
function proposalCard(pa) {
  const card = h("div", { class: "confirm-card proposal" },
    h("div", { class: "small", style: "font-weight:600" }, "Waiting for your OK - nothing happens until you confirm"),
    h("div", {}, pa.summary || ""), pa.preview ? h("div", { class: "pop-preview" }, h("p", {}, pa.preview)) : null,
    h("div", { class: "row", style: "margin-top:8px" },
      h("button", { class: "btn primary", onclick: async () => {
        try { const r = await api(`/api/actions/${pa.id}/confirm`, { body: {} }); if (r.status !== "ok") throw new Error(r.message || r.status);
          card.replaceChildren(h("div", { class: "row" }, h("div", { class: "check-wrap sm" }, checkMark()), h("b", {}, pa.tool === "create_payment_reminder" ? "Reminder sent (sandbox outbox)" : "Done")),
            r.data && r.data.download_url ? h("button", { class: "btn sm", onclick: () => download(r.data.download_url, r.data.filename) }, "Download PDF") : null);
          refreshPending(); } catch (e) { toast(e.message, "bad"); }
      } }, pa.tool === "create_payment_reminder" ? "Send reminder" : "Confirm"),
      h("button", { class: "btn ghost", onclick: async () => { try { await api(`/api/actions/${pa.id}/reject`, { method: "POST" }); card.replaceChildren(h("div", { class: "muted" }, "Cancelled - nothing was done.")); refreshPending(); } catch (e) { toast(e.message, "bad"); } } }, "Cancel")));
  return card;
}
function confirmCard(pa) {
  if ((pa.tier ?? 2) < 2) return proposalCard(pa);
  const pw = S.stepUp && pa.amount >= S.stepUp ? h("input", { type: "password", placeholder: "Your password (large amount)", style: "width:200px" }) : null;
  const amt = h("input", { type: "number", placeholder: "Re-type the amount", style: "width:170px" });
  const status = h("div", { class: "small" });
  const card = h("div", { class: "confirm-card" },
    h("div", { class: "small", style: "font-weight:600;color:var(--serious)" }, "SANDBOX payment - needs your confirmation"),
    h("div", { class: "amt num" }, money(pa.amount)), h("div", {}, pa.summary || ""),
    h("div", { class: "small muted" }, `Recipient: ${pa.recipient || "–"} · expires ${pa.expires_at ? new Date(pa.expires_at + "Z").toLocaleTimeString() : ""}`),
    h("div", { class: "row", style: "margin-top:8px" }, amt, pw,
      h("button", { class: "btn primary", onclick: async () => {
        try {
          const r = await api(`/api/actions/${pa.id}/confirm`, { body: { confirm_amount: +amt.value, password: pw ? pw.value : undefined } });
          const d = r.data; card.replaceChildren(h("div", { style: "color:var(--good-text);font-weight:600" }, `✓ Executed in sandbox: ${money(d.amount)} to ${d.recipient_name}`),
            h("div", { class: "small muted" }, `Sandbox balance ${money(d.balance_before)} → ${money(d.balance_after)} · logged with confirmation status "confirmed"`));
          refreshPending();
        } catch (e) { status.textContent = "✕ " + e.message; status.style.color = "var(--critical)"; }
      } }, "Confirm"),
      h("button", { class: "btn", onclick: async () => { try { await api(`/api/actions/${pa.id}/reject`, { method: "POST" }); card.replaceChildren(h("div", { class: "muted" }, "Rejected - nothing was sent.")); refreshPending(); } catch (e) { toast(e.message, "bad"); } } }, "Reject")),
    status);
  if (S.user.role !== "owner") card.appendChild(h("div", { class: "small muted" }, "Only the owner can confirm money movements."));
  return card;
}
function confirmModal(pa) { const m = modal("Confirm sandbox payment", confirmCard(pa)); return m; }

// Recurring rent / salary / bills (become transactions) and recurring customer invoices (become drafts).
function recurringPane(canWrite) {
  const pane = h("div", {});
  const OUT_CATS = ["rent", "salary", "utilities", "loan_repayment", "tax_vat", "maintenance", "transport", "marketing", "misc_expense"];
  async function load() {
    const d = await api("/api/books/recurring");
    const post = h("button", { class: "btn primary", disabled: !canWrite || !d.due_count, onclick: async () => {
      const due = d.rows.filter(r => r.due_now);
      const ok = await confirmDialog({ title: `Post ${due.length} due item(s)?`, action: "post_recurring", confirmLabel: "Post now",
        rows: due.slice(0, 6).map(r => [r.name, `${money(r.amount)} · ${r.type === "invoice" ? "draft invoice" : "expense"} · ${r.next_due}`]),
        note: "Missed dates are caught up too. Expenses become records; invoices become drafts." });
      if (!ok) return; ok.bg.remove();
      try { const r = await api("/api/books/recurring/post-due", { method: "POST" });
        toast(`Posted ${r.transactions} record(s) and ${r.invoices} draft invoice(s)`, "ok"); load(); } catch (e) { toast(e.message, "bad"); } } },
      d.due_count ? `Post ${d.due_count} due item(s)` : "Nothing due");
    const list = d.rows.length ? h("div", { class: "scroll" }, h("table", { class: "t" },
      h("tr", {}, ["What", "Type", "Amount", "Repeats", "Next date", ""].map((x, i) => h("th", { class: i === 2 ? "r" : "" }, x))),
      d.rows.map(r => h("tr", { class: r.active ? "" : "muted" },
        h("td", {}, r.name, r.description && r.description !== r.name ? h("div", { class: "small muted" }, r.description) : null),
        h("td", {}, r.type === "invoice" ? h("span", { class: "chip info" }, "invoice") : h("span", { class: "chip cat cat-" + catTone(r.category) }, r.category.replace(/_/g, " "))),
        h("td", { class: "r" }, money(r.amount)), h("td", {}, r.frequency),
        h("td", { class: "num" }, r.active ? r.next_due : "stopped", r.due_now ? h("span", { class: "chip warn", style: "margin-left:6px" }, "due") : null),
        h("td", {}, canWrite && r.active ? h("a", { href: "#", class: "link small", onclick: async e => { e.preventDefault();
          await api(`/api/books/recurring/${r.type}/${r.id}/stop`, { method: "POST" }).catch(err => toast(err.message, "bad")); load(); } }, "Stop") : null)))))
      : emptyState("No repeating items yet. Add rent, salary or a monthly customer bill.", canWrite ? "Add repeating item" : null, () => recurringForm(load));
    pane.replaceChildren(h("div", { class: "card" },
      h("div", { class: "row" }, h("h2", { class: "grow" }, "Repeating items"), canWrite && d.rows.length ? h("a", { href: "#", class: "link", onclick: e => { e.preventDefault(); recurringForm(load); } }, "+ Add repeating item") : null, post),
      h("p", { class: "hint" }, "Expenses become records on their date. Customer invoices are created as drafts for you to check and send."), list));
  }
  function recurringForm(onDone) {
    const type = h("select", {}, h("option", { value: "expense" }, "Expense I pay (rent, salary…)"), h("option", { value: "invoice" }, "Invoice I send to a customer"));
    const name = h("input", { type: "text", placeholder: "e.g. Shop rent" });
    const cat = h("select", {}, OUT_CATS.map(c => h("option", { value: c }, c.replace(/_/g, " "))));
    const desc = h("input", { type: "text", placeholder: "Line on the invoice, e.g. Monthly service" });
    const amount = h("input", { type: "number", min: 0, step: "any" });
    const freq = h("select", {}, ["monthly", "quarterly", "yearly"].map(f => h("option", { value: f }, f)));
    const next = h("input", { type: "date", value: today() });
    const dueDays = h("input", { type: "number", value: 30, min: 0 });
    const catF = h("label", { class: "field" }, "Category", cat), descF = h("label", { class: "field hidden" }, "Invoice line", desc), dueF = h("label", { class: "field hidden" }, "Customer pays within (days)", dueDays);
    const nameF = h("label", { class: "field" }, "Name", name);
    type.addEventListener("change", () => { const inv = type.value === "invoice"; catF.classList.toggle("hidden", inv); descF.classList.toggle("hidden", !inv); dueF.classList.toggle("hidden", !inv);
      nameF.firstChild.textContent = inv ? "Customer" : "Name"; name.placeholder = inv ? "Customer name" : "e.g. Shop rent"; });
    const err = h("div", { class: "small", style: "color:var(--critical)" });
    const m = modal("Add repeating item", h("div", { class: "grid", style: "gap:10px" }, h("label", { class: "field" }, "Type", type), nameF, catF, descF,
      h("div", { class: "grid g-2e" }, h("label", { class: "field" }, "Amount ৳", amount), h("label", { class: "field" }, "Repeats", freq)),
      h("label", { class: "field" }, "First / next date", next, h("span", { class: "hint" }, "Items on or before today are posted when you press Post.")), dueF, err),
      [h("button", { class: "btn primary", onclick: async () => {
        try { await api("/api/books/recurring", { body: { type: type.value, name: name.value, category: cat.value, description: desc.value, amount: +amount.value, frequency: freq.value, next_due: next.value, due_days: +dueDays.value } });
          m.remove(); toast("Saved", "ok"); onDone(); } catch (e) { err.textContent = e.message; } } }, "Save")]);
    name.focus();
  }
  return { pane, load };
}

// ------------------------------------------------------------------ data
// Tabs: Add (quick entry first, then file upload / paste) | Import history | Transactions (search, filters, edit, delete+undo).
async function viewData(v) {
  const canWrite = S.user.max_tier >= 1;
  const file = h("input", { type: "file", accept: ".csv,.tsv,.txt,.xlsx,.xls" });
  const dtype = h("select", {}, ["auto", "sales", "expenses", "bank", "wallet", "invoices", "ledger"].map(x => h("option", { value: x }, x)));
  const result = h("div", {});
  const showReport = r => result.replaceChildren(h("div", { class: "notice", style: "margin-top:10px" },
    r.already_imported ? "This exact file was imported before - skipped." :
      `Imported ${r.imported} of ${r.rows_total} rows as “${r.doc_type}”. Duplicates flagged: ${r.duplicates.length}. Anomalies: ${r.anomalies.length}. Suspicious text (possible prompt injection) flagged: ${r.injection_flags.length}. Errors: ${r.errors.length}.`,
    r.errors.length ? h("ul", { class: "small" }, r.errors.slice(0, 8).map(e => h("li", {}, `row ${e.row}: ${e.reason}`))) : null,
    r.injection_flags.length ? h("ul", { class: "small", style: "color:var(--critical)" }, r.injection_flags.map(e => h("li", {}, `row ${e.row}: “${e.text}” - treated as data, never as instructions`))) : null));
  const showError = e => { result.replaceChildren(h("div", { class: "notice warn", style: "margin-top:10px" }, `Not imported: ${e.message}`)); toast(e.message, "bad"); };
  const confirmImport = (what, rows) => confirmDialog({ title: `Import ${what}?`, action: "import_file", confirmLabel: "Import",
    rows, note: "Rows are added to your records. Duplicates and suspicious text are flagged, never run as instructions." });
  const upload = h("button", { class: "btn primary", disabled: !canWrite, onclick: async () => {
    if (!file.files[0]) return toast("Choose a file first", "warn");
    const ok = await confirmImport("this file", [["File", file.files[0].name], ["Type", dtype.value], ["Size", `${Math.ceil(file.files[0].size / 1024)} KB`]]);
    if (!ok) return; ok.bg.remove();
    const fd = new FormData(); fd.append("file", file.files[0]); fd.append("doc_type", dtype.value);
    try { showReport(await api("/api/data/upload", { body: fd })); toast("File imported", "ok"); } catch (e) { showError(e); }
  } }, "Upload");
  const paste = h("textarea", { placeholder: "Paste CSV text here (Date, Description, Amount, …)" });
  const pasteBtn = h("a", { href: "#", class: "link", onclick: async e => { e.preventDefault(); if (!canWrite || !paste.value.trim()) return;
    const ok = await confirmImport("pasted text", [["Lines", String(paste.value.trim().split("\n").length)], ["Type", dtype.value]]);
    if (!ok) return; ok.bg.remove();
    try { showReport(await api("/api/data/paste", { body: { text: paste.value, doc_type: dtype.value } })); toast("Pasted rows imported", "ok"); } catch (err) { showError(err); } } }, "Import pasted text");

  const entry = h("input", { type: "text", placeholder: "e.g. sold 12 shirts for 6000 taka cash · dokan bhara 15000 dilam · ১২টা শার্ট বিক্রি ৬০০০ টাকা", class: "grow big-input", disabled: !canWrite });
  const preview = h("div", { class: "small muted", style: "min-height:20px;margin-top:6px" });
  let timer;
  entry.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(async () => {
    if (!entry.value.trim()) { preview.textContent = ""; return; }
    const p = await api("/api/data/entry/preview", { body: { text: entry.value } });
    preview.textContent = p.amount ? `→ ${p.direction === "in" ? "Income" : p.direction === "out" ? "Expense" : "?"} ${money(p.amount)} · ${p.category} · ${p.channel} · ${p.txn_date}${p.counterparty ? " · " + p.counterparty : ""}${p.quantity ? ` · qty ${p.quantity} ${p.item}` : ""} (confidence ${Math.round(p.confidence * 100)}%)` : `Missing: ${p.missing.join(", ")}`;
  }, 250); });
  const record = h("button", { class: "btn primary", disabled: !canWrite, onclick: async () => {
    if (!entry.value.trim()) return;
    const btn = record; btn.classList.add("loading"); btn.disabled = true; preview.replaceChildren(h("span", { class: "skeleton-line" }));
    try { const r = await api("/api/data/entry", { body: { text: entry.value } });
      toast(r.data.recorded ? "Recorded ✓" : `Not recorded: ${r.data.missing?.join(", ") || r.data.duplicate_warning || r.data.preview || ""}`, r.data.recorded ? "ok" : "warn");
      preview.textContent = "";
      if (r.data.recorded) { S.flashId = r.data.transaction_id; entry.value = ""; }
      if (r.data.stock && r.data.stock.ask_item) askWhichItem(r.data.stock, preview);
    } catch (e) { preview.textContent = ""; toast(e.message, "bad"); }
    finally { btn.classList.remove("loading"); btn.disabled = false; }
  } }, "Record");
  entry.addEventListener("keydown", e => { if (e.key === "Enter") record.click(); });

  // Transactions tab
  const qInput = h("input", { type: "search", placeholder: "Search description, party, reference…", class: "grow", "aria-label": "Search" });
  const from = h("input", { type: "date", "aria-label": "From date" }), to = h("input", { type: "date", "aria-label": "To date" });
  const dir = h("select", { "aria-label": "Money in or out" }, [["", "In and out"], ["in", "Money in"], ["out", "Money out"]].map(([k, l]) => h("option", { value: k }, l)));
  const cat = h("select", { "aria-label": "Category" }, h("option", { value: "" }, "All categories"));
  const flaggedOnly = h("input", { type: "checkbox" });
  const tableWrap = h("div", {});
  let cats = [];
  async function loadTxns() {
    const p = new URLSearchParams({ limit: 300 });
    if (qInput.value.trim()) p.set("q", qInput.value.trim());
    if (from.value) p.set("start", from.value); if (to.value) p.set("end", to.value);
    if (dir.value) p.set("direction", dir.value); if (cat.value) p.set("category", cat.value);
    if (flaggedOnly.checked) p.set("flagged", "true");
    const d = await api(`/api/data/transactions?${p}`);
    if (!cats.length) { cats = d.categories; cat.append(...cats.map(c => h("option", { value: c }, c.replace(/_/g, " ")))); }
    tableWrap.replaceChildren(d.rows.length ? txnTable(d.rows, canWrite, cats, loadTxns)
      : emptyState(p.size > 1 ? "No records match these filters." : "No records yet. Add your first one.", "Add a record", () => tabBtns[0].click()));
  }
  let qt; qInput.addEventListener("input", () => { clearTimeout(qt); qt = setTimeout(loadTxns, 250); });
  [from, to, dir, cat, flaggedOnly].forEach(x => x.addEventListener("change", loadTxns));

  const rec = recurringPane(canWrite);
  const imports = h("div", {});
  async function loadImports() {
    const im = await api("/api/data/imports");
    imports.replaceChildren(im.length ? h("div", { class: "scroll" }, h("table", { class: "t" }, h("tr", {}, ["File", "Type", "Rows", "Imported", "Dup.", "Anom.", "Inj.", "By"].map((x, i) => h("th", { class: i > 1 && i < 7 ? "r" : "" }, x))),
      im.map(b => h("tr", {}, h("td", {}, b.filename), h("td", {}, b.doc_type), h("td", { class: "r" }, b.rows_total), h("td", { class: "r" }, b.imported), h("td", { class: "r" }, b.duplicates), h("td", { class: "r" }, b.anomalies), h("td", { class: "r" }, b.injection_flags), h("td", {}, b.created_by)))))
      : emptyState("No files imported yet.", "Upload a file", () => tabBtns[0].click()));
  }

  const panes = [
    h("div", {},
      h("div", { class: "card hero-card" }, h("h2", {}, "Quick entry"), h("p", { class: "hint" }, "Write what happened in English, বাংলা or Banglish. We read the amount, type and category for you."),
        h("div", { class: "row" }, entry, record), preview),
      h("div", { class: "card", style: "margin-top:16px" }, h("h2", {}, "Upload a file"),
        h("p", { class: "hint" }, "Sales, expenses, bank or bKash/Nagad/Rocket statements, invoices (.csv, .xlsx)."),
        h("div", { class: "row" }, file, h("label", { class: "row small" }, "Type", dtype), upload),
        h("details", { style: "margin-top:10px" }, h("summary", { class: "link" }, "…or paste text"), paste, h("div", { style: "margin-top:6px" }, pasteBtn)), result)),
    h("div", { class: "card" }, h("h2", {}, "Import history"), imports),
    h("div", { class: "card" }, h("div", { class: "row filters" }, qInput, from, to, dir, cat,
      h("label", { class: "row small" }, flaggedOnly, "Only flagged")), tableWrap),
    rec.pane,
  ];
  const loaders = [async () => {}, loadImports, loadTxns, rec.load];
  const body = h("div", {});
  const show = i => { tabBtns.forEach((b, j) => b.classList.toggle("active", i === j)); body.replaceChildren(panes[i]); loaders[i]().catch(e => toast(e.message, "bad")); };
  const tabBtns = ["Add", "Import history", "Transactions", "Repeating"].map((n, i) => h("button", { onclick: () => show(i) }, n));
  v.replaceChildren(...[
    h("h1", {}, t("data")),
    !canWrite ? h("div", { class: "notice" }, "Your role is read-only (Tier 0): uploads and entries are disabled.") : null,
    h("div", { class: "tabs" }, tabBtns), body,
  ].filter(Boolean));
  const q = hashParam("q");
  if (q) qInput.value = q;
  show(q ? 2 : hashParam("tab") === "repeating" ? 3 : 0);
}

// ------------------------------------------------------------------ financing
async function viewFinancing(v) {
  const amount = h("input", { type: "number", value: 500000, style: "width:150px" });
  const purpose = h("select", {}, ["working_capital", "inventory", "seasonal", "equipment", "expansion", "receivables_gap"].map(x => h("option", { value: x }, x.replace("_", " "))));
  const tenure = h("input", { type: "number", value: 24, style: "width:80px" });
  const res = h("div", {});
  const run = async () => {
    res.replaceChildren(h("div", { class: "muted" }, "Matching…"));
    const out = await api("/api/tools/match_financing", { body: { args: { amount: +amount.value || null, purpose: purpose.value, tenure_months: +tenure.value || null } } });
    renderMatches(res, out.data);
  };
  const rd = (await api("/api/tools/loan_readiness_score", { body: { args: {} } })).data;
  const readiness = h("div", { class: "card" }, h("div", { class: "row" }, h("h2", { class: "grow" }, "Loan-readiness score"),
    h("button", { class: "btn ghost sm", onclick: () => modal("Readiness calculation", traceView(rd.trace)) }, t("howcalc"))),
    h("div", { class: "row" }, h("span", { class: "gauge num" }, `${rd.score}`), h("span", { class: "muted" }, `/ 100 · ${rd.band.replace("_", " ")}`)),
    rd.components.map(c => h("div", { style: "margin:6px 0" }, h("div", { class: "row small" }, h("span", { class: "grow" }, c.name), h("span", { class: "num" }, `${c.points}/${c.max_points}`)),
      h("div", { class: "bar-track" }, h("div", { class: "bar-fill", style: `width:${100 * c.points / c.max_points}%` })), h("div", { class: "small muted" }, c.value))),
    h("h3", {}, "How to improve"), h("ul", { class: "small" }, rd.top_tips.map(x => h("li", {}, x))), h("div", { class: "small muted" }, rd.disclaimer));
  const actions = h("div", { class: "row", style: "margin-top:10px" },
    h("button", { class: "btn ghost", disabled: S.user.max_tier < 1, onclick: () => runTool("generate_loan_report", { amount: +amount.value || null, purpose: purpose.value }) }, "Generate loan-readiness PDF"),
    h("button", { class: "btn ghost", disabled: S.user.max_tier < 1, onclick: () => runTool("prepare_loan_checklist", { amount: +amount.value || null }) }, "Prepare application checklist"));
  v.replaceChildren(h("h1", {}, t("financing")),
    h("div", { class: "notice warn", style: "margin:8px 0 16px" }, h("span", { class: "illus" }, "Illustrative"), " Catalog terms are placeholders until verified with each lender. Matching uses your real numbers (revenue, stability, DSCR, age, documents, collateral). Approval is never guaranteed."),
    h("div", { class: "grid g-2" }, h("div", { class: "card" }, h("h2", {}, "Find financing options"),
      h("div", { class: "row" }, h("label", { class: "field" }, "Amount ৳", amount), h("label", { class: "field" }, "Purpose", purpose), h("label", { class: "field" }, "Months", tenure),
        h("button", { class: "btn primary", style: "align-self:flex-end", onclick: run }, "Match")), actions, res), readiness));
  run();
}

function renderMatches(el, d) {
  const offer = m => {
    const c = m.cost_mid || {};
    return h("div", { class: "offer" },
      h("div", { class: "row" }, h("b", { class: "grow" }, m.name), h("span", { class: "illus" }, m.verify_label), h("span", { class: "chip" }, `fit ${m.score}`)),
      h("div", { class: "row small", style: "margin:6px 0" },
        h("span", {}, "Offer ", h("b", { class: "num" }, money(m.offered_amount))),
        h("span", {}, `EMI ${money(m.cost_low?.emi)}–${money(m.cost_high?.emi)} / month for ${m.tenure_months} mo`),
        h("span", {}, `Total cost of credit ~${money(c.total_cost_of_credit)} (APR ~${c.effective_apr_pct}%)`),
        m.dscr_after ? h("span", {}, `DSCR after loan ${m.dscr_after} (min ${m.min_dscr})`) : null),
      h("ul", { class: "plain" }, m.reasons.map(r => h("li", { class: "ok-li" }, r)), m.cautions.map(r => h("li", { class: "warn-li" }, r))),
      h("div", { class: "small muted" }, `Collateral: ${m.collateral} · ~${m.speed_days} days · source to verify: ${m.source_url || "lender"}`));
  };
  el.replaceChildren(h("p", { class: "small muted" }, `${d.amount_basis}. ${d.recommendations.length} option(s) fit, ${d.rejected.length} don't.`),
    ...d.recommendations.map(offer),
    h("h3", {}, "Not a fit right now (and why)"),
    h("ul", { class: "plain" }, d.rejected.map(m => h("li", { class: "no-li" }, h("b", {}, m.name + ": "), m.reasons.join("; ")))),
    h("button", { class: "btn ghost sm", onclick: () => modal("Matching calculation", traceView(d.trace)) }, t("howcalc")),
    h("div", { class: "small muted" }, d.disclaimer));
}

// ------------------------------------------------------------------ actions
async function viewActions(v) {
  const tabs = ["Confirmations", "Outbox (reminders)", "Drafts", "Reports", "Sandbox account"];
  const body = h("div", {});
  const bar = h("div", { class: "tabs" }, tabs.map((n, i) => h("button", { class: i ? "" : "active", onclick: e => { bar.querySelectorAll("button").forEach(b => b.classList.remove("active")); e.target.classList.add("active"); show(i); } }, n)));
  async function show(i) {
    body.replaceChildren(h("div", { class: "muted" }, "Loading…"));
    if (i === 0) {
      const p = await api("/api/actions/pending");
      body.replaceChildren(p.length ? h("div", {}, p.map(x => x.status === "pending" ? confirmCard(x) :
        h("div", { class: "alert-item" }, h("div", { class: "row" }, h("span", { class: "chip " + (x.status === "confirmed" ? "ok" : "bad") }, x.status), h("b", {}, money(x.amount)), h("span", {}, x.summary)),
          h("div", { class: "small muted" }, `${x.tool} · created ${x.created_at} · decided ${x.decided_at || "–"} by ${x.decided_by || "–"}${x.result && x.result.reason ? " · " + x.result.reason : ""}`))))
        : emptyState("No money requests yet. Ask the copilot, e.g. “Transfer 25000 to Dhaka Zipper House”.", "Open Copilot", () => { location.hash = "#chat"; }));
    } else if (i === 1) {
      const r = await api("/api/reminders");
      body.replaceChildren(h("div", { class: "notice small" }, "Simulated outbox: messages are queued, not sent to real phones."),
        h("table", { class: "t" }, h("tr", {}, ["Send on", "To", "Channel", "Amount", "Message", "Status"].map(x => h("th", {}, x))),
          r.map(x => h("tr", {}, h("td", {}, x.remind_on), h("td", {}, x.counterparty), h("td", {}, x.channel), h("td", { class: "r" }, money(x.amount)), h("td", { class: "small" }, x.message), h("td", {}, x.status)))));
    } else if (i === 2) {
      const r = await api("/api/drafts");
      body.replaceChildren(...(r.length ? r : [null]).map(d => !d ? emptyState("No drafts yet. The copilot can write a payment reminder for you.", "Open Copilot", () => { location.hash = "#chat"; }) : h("div", { class: "card", style: "margin-bottom:10px" },
        h("div", { class: "row" }, h("b", { class: "grow" }, d.subject), h("span", { class: "chip" }, `${d.kind} · ${d.language} · ${d.status}`)),
        h("pre", { style: "white-space:pre-wrap;font:inherit" }, d.body),
        S.user.max_tier >= 1 ? h("div", { class: "row" }, h("button", { class: "btn sm primary", onclick: async () => { await api(`/api/drafts/${d.id}`, { method: "PATCH", body: { status: "approved" } }); show(2); } }, "Approve"),
          h("button", { class: "btn ghost sm", onclick: () => navigator.clipboard.writeText(d.body).then(() => toast("Copied", "ok")) }, "Copy"),
          h("button", { class: "btn ghost sm", onclick: async () => { await api(`/api/drafts/${d.id}`, { method: "PATCH", body: { status: "discarded" } }); show(2); } }, "Discard")) : null)));
    } else if (i === 3) {
      const r = await api("/api/reports");
      body.replaceChildren(h("table", { class: "t" }, h("tr", {}, ["Created", "File", "SHA-256", ""].map(x => h("th", {}, x))),
        r.map(x => h("tr", {}, h("td", {}, x.created_at), h("td", {}, x.filename), h("td", { class: "small muted" }, x.sha256.slice(0, 16) + "…"),
          h("td", {}, h("button", { class: "btn sm", onclick: () => download(x.download_url, x.filename) }, "Download"))))),
        S.user.max_tier >= 1 ? h("button", { class: "btn primary", style: "margin-top:10px", onclick: () => runTool("generate_loan_report", {}) }, "Generate new report") : null);
    } else {
      const s = await api("/api/sandbox");
      body.replaceChildren(h("div", { class: "grid g-kpi" },
        h("div", { class: "card kpi" }, h("div", { class: "label" }, s.account.name), h("div", { class: "value num" }, money(s.account.balance)), h("div", { class: "sub" }, s.account.account_no)),
        h("div", { class: "card kpi" }, h("div", { class: "label" }, "Per-transaction limit"), h("div", { class: "value num" }, money(s.limits.per_transaction))),
        h("div", { class: "card kpi" }, h("div", { class: "label" }, "Daily cap"), h("div", { class: "value num" }, money(s.limits.daily_cap)), h("div", { class: "sub" }, `used/reserved today ${money(s.limits.used_or_reserved_today)}`)),
        h("div", { class: "card kpi" }, h("div", { class: "label" }, "Confirmation window"), h("div", { class: "value num" }, `${s.limits.confirmation_ttl_minutes} min`))),
        h("h3", {}, "Executed sandbox transfers"),
        h("table", { class: "t" }, h("tr", {}, ["When", "To", "Account", "Amount", "Purpose", "Balance after", "Request"].map(x => h("th", {}, x))),
          s.transfers.map(x => h("tr", {}, h("td", {}, x.executed_at || "–"), h("td", {}, x.recipient), h("td", {}, x.account || "–"), h("td", { class: "r" }, money(x.amount)), h("td", {}, x.purpose), h("td", { class: "r" }, money(x.balance_after)), h("td", {}, "#" + x.pending_action_id)))));
    }
  }
  v.replaceChildren(h("h1", {}, t("actions")), bar, body);
  show(0);
}

// ------------------------------------------------------------------ audit
async function viewAudit(v) {
  const verify = h("span", {});
  const doVerify = async () => { const r = await api("/api/audit/verify"); verify.replaceChildren(h("span", { class: "chip " + (r.ok ? "ok" : "bad") }, r.ok ? `✓ hash chain intact (${r.events} events)` : `✕ chain broken at #${r.broken_at_id}: ${r.reason}`)); };
  const kind = h("select", {}, ["operation log", "all events"].map(x => h("option", {}, x)));
  const table = h("div", { class: "scroll", style: "max-height:65vh" });
  const load = async () => {
    const rows = kind.value === "operation log" ? await api("/api/oplog?limit=300") : await api("/api/audit?limit=300");
    table.replaceChildren(h("table", { class: "t" }, h("tr", {}, ["#", "Time (UTC)", "Actor", "Type", "Action", "Tier", "Confirmation", "Inputs → result", "Hash"].map(x => h("th", {}, x))),
      rows.map(e => h("tr", {}, h("td", {}, e.id), h("td", { class: "small num" }, e.ts.replace("T", " ").slice(0, 19)), h("td", {}, `${e.actor} (${e.actor_role || "-"})`),
        h("td", {}, e.event_type), h("td", {}, e.action), h("td", {}, e.tier ?? "–"),
        h("td", {}, h("span", { class: "chip " + ({ confirmed: "ok", blocked: "bad", rejected: "bad", pending: "pend", expired: "bad" }[e.confirmation_status] || "") }, e.confirmation_status)),
        h("td", { class: "small" }, h("code", {}, JSON.stringify(e.inputs).slice(0, 140)), h("div", { class: "muted" }, JSON.stringify(e.result).slice(0, 160))),
        h("td", { class: "small muted", title: e.hash }, e.hash.slice(0, 10) + "…")))));
  };
  kind.addEventListener("change", load);
  v.replaceChildren(h("h1", {}, t("audit")),
    h("p", { class: "muted small" }, "Append-only and hash-chained: each entry stores the previous entry's hash; edits or deletions break the chain. Inputs are PII-masked."),
    h("div", { class: "row", style: "margin-bottom:10px" }, kind, h("button", { class: "btn", onclick: doVerify }, "Verify chain"), verify, h("span", { class: "grow" }),
      h("button", { class: "btn", onclick: () => download("/api/oplog/export?fmt=csv", "operation_log.csv") }, "Export CSV"),
      h("button", { class: "btn", onclick: () => download("/api/oplog/export?fmt=jsonl", "operation_log.jsonl") }, "Export JSONL")),
    h("div", { class: "card" }, table));
  await load(); doVerify();
}

// ------------------------------------------------------------------ settings / privacy
async function viewSettings(v) {
  const st = await api("/api/settings");
  const thr = h("input", { type: "number", value: st.low_balance_threshold, style: "width:160px" });
  const comp = await api("/api/compliance");
  const pw = h("input", { type: "password", placeholder: "your password" });
  const phrase = h("input", { type: "text", placeholder: "type: DELETE MY DATA" });
  const isOwner = S.user.role === "owner";
  v.replaceChildren(h("h1", {}, t("settings")), prefsCard(), homeLayoutCard(), await privacyCard(),
    h("div", { class: "grid g-2e", style: "margin-top:16px" },
      h("div", { class: "card" }, h("h2", {}, "Alerts"), h("label", { class: "field" }, "Low-balance safety level (৳)", thr,
          h("span", { class: "hint" }, "We warn you when cash is expected to drop below this amount.")),
        h("button", { class: "btn primary", style: "margin-top:8px", disabled: S.user.max_tier < 1, onclick: async () => { await api("/api/settings", { method: "PATCH", body: { low_balance_threshold: +thr.value } }); toast("Saved", "ok"); } }, "Save"),
        h("h2", { style: "margin-top:16px" }, "Data protection"),
        h("ul", { class: "small" },
          h("li", {}, `PII masking before cloud models: ${S.models.mask_pii ? "ON" : "OFF"}`),
          h("li", {}, `Local-only mode (no data leaves this machine): ${S.models.local_only_mode ? "ON" : "OFF"} - set LOCAL_ONLY_MODE=true`),
          h("li", {}, "Account/wallet numbers, phones, TIN and trade licence are encrypted at rest (Fernet)."),
          h("li", {}, "Every agent decision and action is in the hash-chained audit log."))),
      h("div", { class: "card" }, h("h2", {}, "Your data"),
        h("button", { class: "btn primary", disabled: !isOwner, onclick: () => download("/api/privacy/export", "my_business_data.json") }, "Export my data (JSON)"),
        h("h3", {}, "Delete all business data"),
        h("p", { class: "small muted" }, "Removes transactions, invoices, drafts, reports, chats and the interaction dataset lines for this business and deactivates its accounts. The masked audit log is kept to prove the deletion happened."),
        h("div", { class: "row" }, pw, phrase, h("button", { class: "btn danger", disabled: !isOwner, onclick: async () => {
          try { const r = await api("/api/privacy/delete", { body: { password: pw.value, confirm: phrase.value } }); toast("Deleted: " + JSON.stringify(r.rows_deleted)); logout(true); } catch (e) { toast(e.message, "bad"); }
        } }, "Delete")), !isOwner ? h("div", { class: "small muted" }, "Owner only.") : null)),
    h("div", { class: "card", style: "margin-top:16px" }, h("h2", {}, "Bangladesh compliance awareness"),
      h("p", { class: "small muted" }, comp.disclaimer),
      comp.rules.map(r => h("div", { class: "alert-item" }, h("div", { class: "row" }, h("b", { class: "grow" }, r.title), r.applies_to_you ? h("span", { class: "chip" }, "applies to you") : null, h("span", { class: "illus" }, r.verify_label)),
        h("div", { class: "msg" }, r.summary), r.source_url ? h("div", { class: "small muted" }, "Check: " + r.source_url) : null))));
}

async function privacyCard() {
  const recent = await api("/api/privacy/recent").catch(() => []);
  const m = S.models || { profiles: [] };
  const prof = m.profiles.find(p => p.name === S.profile) || {};
  const local = m.local_only_mode || !prof.external;
  return h("div", { class: "card privacy-card", style: "margin-top:16px" }, h("h2", {}, "What this app can see"),
    h("ul", { class: "plain see-list" },
      h("li", { class: "ok-li" }, "Only what you type or upload here: records, files and invoices."),
      h("li", { class: "no-li" }, "No access to your contacts, email, SMS, camera, other files or other apps."),
      h("li", { class: "ok-li" }, "Reminders and payments are drafts or sandbox only. Nothing is sent to real phones, email or banks."),
      h("li", { class: local ? "ok-li" : "warn-li" }, local
        ? `AI model "${prof.label || S.profile}" runs on this computer, so your data stays here.`
        : `AI model "${prof.label || S.profile}" is a cloud model: questions go to it with phone and account numbers masked.`)),
    h("div", { class: "row small" }, h("span", { class: "chip " + (local ? "ok" : "warn") }, local ? "⌂ Local model" : "☁ Cloud model"),
      m.local_only_mode ? h("span", { class: "chip ok" }, "Local-only mode ON") : null,
      h("span", { class: "chip " + (m.mask_pii ? "ok" : "warn") }, m.mask_pii ? "PII masking ON" : "PII masking OFF")),
    h("h3", {}, "Last 5 things that happened"),
    recent.length ? h("ul", { class: "plain small" }, recent.map(e => h("li", {}, h("span", { class: "num muted" }, e.ts.replace("T", " ") + "  "),
      `${e.actor} · ${e.action.replace(/_/g, " ")}`, e.confirmation !== "not_required" ? h("span", { class: "chip", style: "margin-left:6px" }, e.confirmation) : null)))
      : h("p", { class: "muted small" }, "Nothing yet."));
}

function prefsCard() {
  return h("div", { class: "card", style: "margin-top:12px" },
    h("div", { class: "row" }, h("h2", { class: "grow" }, t("prefs")),
      h("span", { class: "small muted" }, `${t("signed_in_as")} ${S.user.full_name || S.user.username} · ${S.user.role}`),
      h("button", { class: "btn danger", onclick: () => logout(false) }, "⎋ " + t("logout"))),
    h("div", { class: "grid prefs-grid" }, prefControls()),
    h("p", { class: "small muted", style: "margin:10px 0 0" }, t("mode_hint")));
}

// ------------------------------------------------------------------ simple mode
// Same API, same safety rules (confirmations, tiers); fewer numbers, bigger type, plain words.
const canWrite = () => S.user.max_tier >= 1;

async function viewSimpleHome(v) {
  const [d, pend] = await Promise.all([api("/api/dashboard"), api("/api/actions/pending").catch(() => [])]);
  $("#biz-name").textContent = d.business.name;
  const k = d.kpis, f = d.forecast;
  const first = (S.user.full_name || S.user.username).split(" ")[0];
  const status = f.first_negative_date || k.forecast_min_30d < f.threshold
    ? h("div", { class: "status bad" }, "⚠ ", f.first_negative_date ? `${t("s_low")} ${fmtDate(f.first_negative_date)}. ` : "",
      `${t("s_lowest")} `, h("b", { class: "num" }, money(k.forecast_min_30d)))
    : h("div", { class: "status good" }, "✓ ", t("s_ok"));
  const tile = (label, value, tone, n, color, icon) => kpiCard({ label, value: money(value), tone, count: n, color, icon });
  const waiting = pend.filter(x => x.status === "pending");
  const todo = d.alerts.slice(0, 5).map(a => {
    const st = a.data && a.data.suggested_tool;
    return h("div", { class: "alert-item sev-" + a.severity },
      h("div", { class: "title" }, h("span", { class: "sev " + a.severity }), " ", a.title),
      h("div", { class: "msg" }, a.message),
      h("div", { class: "row", style: "margin-top:6px" },
        st && canWrite() ? h("button", { class: "btn primary", onclick: e => runTool(st.name, st.args, e.target.closest(".alert-item")) },
          st.name === "create_payment_reminder" ? "Send reminder" : st.name === "pay_supplier_invoice" ? "Pay (sandbox)" : "Do it") : null,
        h("button", { class: "btn ghost", onclick: async e => { await api(`/api/alerts/${a.id}/dismissed`, { method: "POST" }); e.target.closest(".alert-item").remove(); } }, t("s_dismiss"))));
  });
  const chart = lineChart({ series: [{ name: t("s_next90"), color: "var(--series-1)", points: f.series.map(p => ({ x: p.date, y: p.balance })) }],
    threshold: { value: f.threshold, label: money(f.threshold) }, yfmt: (x, axis) => money(x, axis), xfmt: fmtDate, height: 220, ariaLabel: t("s_next90") });
  v.replaceChildren(
    heroBanner(d), h("h1", { class: "hello-h1" }, `${t("hello")}, ${first} 👋`), status,
    h("div", { class: "grid g-kpi", style: "margin-top:16px" },
      showWidget("cash_now") ? tile(t("s_cash_now"), k.cash_balance, k.cash_balance < 0 ? "bad" : "", k.cash_balance, "blue", "৳") : null,
      showWidget("money_in_out") ? tile(t("s_in"), k.income_this_month, "in", k.income_this_month, "green", "↓") : null,
      showWidget("money_in_out") ? tile(t("s_out"), k.expense_this_month, "out", k.expense_this_month, "orange", "↑") : null,
      showWidget("receivables_aging") ? tile(t("s_owed"), k.receivables_overdue, k.receivables_overdue > 0 ? "bad" : "in", k.receivables_overdue, "purple", "⏱") : null),
    waiting.length ? h("div", { class: "card", style: "margin-top:16px" }, h("h2", {}, `${t("s_confirm")} (${waiting.length})`), waiting.map(confirmCard)) : "",
    ...layoutBlocks([
      showWidget("todo_actions") ? { half: h("div", { class: "card" }, h("h2", {}, t("s_todo")), todo.length ? todo : h("div", { class: "empty" }, h("p", {}, t("s_nothing")))) } : null,
      showWidget("cash_forecast") ? { half: h("div", { class: "card" }, h("h2", {}, t("s_next90")), chart) } : null,
      ...Object.keys(ASYNC_WIDGETS).filter(id => S.home && S.home.widgets.includes(id)).flatMap(id => ASYNC_WIDGETS[id]())]),
    quickEntryCard(),
    h("p", { class: "small muted", style: "margin-top:16px" }, t("s_switch")));
  countUp(v);
}

// Shown after a record that could not be linked to an item (no match / no quantity). Never guesses.
function askWhichItem(st, host) {
  const sel = h("select", {}, h("option", { value: "" }, "Which item?"), (st.items || []).map(i => h("option", { value: i.id }, i.name)), h("option", { value: "new" }, "+ New item"));
  const qty = st.quantity ? null : h("input", { type: "number", min: "0", step: "any", placeholder: "Qty", style: "width:80px" });
  const done = () => host.replaceChildren();
  const link = async id => { try { await api("/api/stock/link", { body: { transaction_id: st.transaction_id, item_id: Number(id), quantity: qty && qty.value ? Number(qty.value) : undefined } }); toast("Stock updated"); done(); } catch (e) { toast(e.message, "bad"); } };
  sel.addEventListener("change", async () => {
    if (!sel.value) return;
    if (sel.value !== "new") return link(sel.value);
    const name = prompt("New item name", st.suggested_name || ""); if (!name) { sel.value = ""; return; }
    try { const r = await api("/api/items", { body: { name } }); link(r.id); } catch (e) { toast(e.message, "bad"); sel.value = ""; }
  });
  host.replaceChildren(h("span", { class: "small" }, "Stock: "), sel, qty, h("button", { class: "btn ghost sm", onclick: done }, "Skip"));
}

function quickEntryCard(onSaved) {
  const entry = h("input", { type: "text", class: "grow big-input", placeholder: t("s_add_ph"), disabled: !canWrite() });
  const preview = h("div", { class: "small muted", style: "min-height:20px;margin-top:6px" });
  let timer;
  entry.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(async () => {
    if (!entry.value.trim()) { preview.textContent = ""; return; }
    try {
      const p = await api("/api/data/entry/preview", { body: { text: entry.value } });
      preview.textContent = p.amount ? `→ ${p.direction === "in" ? "＋" : "−"} ${money(p.amount)} · ${p.category.replace(/_/g, " ")}${p.counterparty ? " · " + p.counterparty : ""}` : "…";
    } catch { preview.textContent = ""; }
  }, 250); });
  const saveBtn = h("button", { class: "btn primary", disabled: !canWrite(), onclick: () => save(false) }, t("s_save"));
  const save = async (confirmed = false) => {
    if (!entry.value.trim()) return;
    saveBtn.classList.add("loading"); preview.replaceChildren(h("span", { class: "skeleton-line" }));
    try {
      const r = await api("/api/data/entry", { body: { text: entry.value, confirmed } });
      preview.textContent = "";
      const d = r.data;
      if (d.needs_confirm) {  // uncertain reading: show the preview, do not save yet
        preview.replaceChildren(d.preview + (d.reason ? ` (${d.reason}) ` : " "),
          h("button", { class: "btn primary", onclick: () => save(true) }, t("s_save")),
          h("button", { class: "btn", onclick: () => { preview.textContent = ""; entry.focus(); } }, "Edit"));
        return;
      }
      if (d.manual_form) { toast(d.preview || "Could not read this, please use the form"); return; }
      toast(d.recorded ? t("s_saved") : `Not saved: ${d.missing?.join(", ") || d.duplicate_warning}`, d.recorded ? "ok" : "warn");
      if (d.recorded) {
        const id = d.transaction_id;
        S.flashId = id;
        entry.value = "";
        const undo = h("button", { class: "btn", onclick: async () => { try { await api(`/api/data/transactions/${id}`, { method: "DELETE" }); preview.textContent = ""; if (onSaved) onSaved(); } catch (e) { toast(e.message, "bad"); } } }, "Undo");
        preview.replaceChildren(t("s_saved") + " ", undo);
        if (d.stock && d.stock.ask_item) { const host = h("div", { class: "small", style: "margin-top:6px" }); preview.appendChild(host); askWhichItem(d.stock, host); }
        setTimeout(() => { if (preview.contains(undo)) preview.textContent = ""; }, 6000);
        if (onSaved) onSaved();
      }
    } catch (e) { preview.textContent = ""; toast(e.message, "bad"); }
    finally { saveBtn.classList.remove("loading"); }
  };
  entry.addEventListener("keydown", e => { if (e.key === "Enter") save(false); });
  return h("div", { class: "card hero-card", style: "margin-top:16px" }, h("h2", {}, t("s_add_title")),
    h("div", { class: "row" }, entry, saveBtn), preview);
}

async function viewSimpleData(v) {
  const list = h("div", {});
  const load = async () => {
    const d = await api("/api/data/transactions?limit=15");
    if (!d.rows.length) { list.replaceChildren(h("div", { class: "empty" }, h("p", {}, "No records yet. Write your first one above."))); return; }
    const flash = S.flashId; S.flashId = null;
    list.replaceChildren(...d.rows.map(r => h("div", { class: "rec" + (r.id === flash ? " flash" : "") },
      h("div", { class: "grow" }, h("div", {}, r.description || r.counterparty || r.category.replace(/_/g, " ")),
        h("div", { class: "small muted" }, `${fmtDate(r.date)} · ${r.category.replace(/_/g, " ")}`)),
      h("div", { class: "num " + (r.direction === "in" ? "amt-in" : "amt-out"), style: "font-weight:650" },
        (r.direction === "in" ? "+" : "−") + money(r.amount).replace("-", "")))));
  };
  const file = h("input", { type: "file", accept: ".csv,.tsv,.txt,.xlsx,.xls", disabled: !canWrite() });
  const upload = h("button", { class: "btn", disabled: !canWrite(), onclick: async () => {
    if (!file.files[0]) return toast("Choose a file");
    const ok = await confirmDialog({ title: "Import this file?", action: "import_file", confirmLabel: t("s_upload"),
      rows: [["File", file.files[0].name], ["Size", `${Math.ceil(file.files[0].size / 1024)} KB`]], note: "Rows are added to your records." });
    if (!ok) return; ok.bg.remove();
    const fd = new FormData(); fd.append("file", file.files[0]); fd.append("doc_type", "auto");
    try { const r = await api("/api/data/upload", { body: fd }); toast(r.already_imported ? "Already imported" : `${t("s_saved")} ${r.imported} / ${r.rows_total}`); load(); } catch (e) { toast(e.message, "bad"); }
  } }, t("s_upload"));
  v.replaceChildren(h("h1", {}, t("s_add")), quickEntryCard(load),
    h("div", { class: "card", style: "margin-top:16px" }, h("h2", {}, t("s_upload_title")), h("div", { class: "row" }, file, upload)),
    h("div", { class: "card", style: "margin-top:16px" }, h("h2", {}, t("s_recent")), list));
  await load();
}

async function viewSimpleFinancing(v) {
  const rd = (await api("/api/tools/loan_readiness_score", { body: { args: {} } })).data;
  const amount = h("input", { type: "number", value: 500000, class: "big-input", style: "width:180px" });
  const res = h("div", {});
  const find = async () => {
    res.replaceChildren(h("div", { class: "muted" }, "…"));
    const d = (await api("/api/tools/match_financing", { body: { args: { amount: +amount.value || null, purpose: "working_capital" } } })).data;
    res.replaceChildren(...d.recommendations.slice(0, 3).map(m => h("div", { class: "offer" },
      h("div", { class: "row" }, h("b", { class: "grow" }, m.name), h("span", { class: "illus" }, m.verify_label)),
      h("div", { class: "row", style: "margin-top:6px" }, h("span", { class: "num", style: "font-size:18px;font-weight:650" }, money(m.offered_amount)),
        h("span", { class: "muted" }, `≈ ${money((m.cost_mid || m.cost_low || {}).emi)} ${t("s_per_month")} · ${m.tenure_months} ${t("s_months")}`)))),
      d.recommendations.length ? "" : h("div", { class: "muted" }, "No good fit right now - see the tips to improve."),
      h("p", { class: "small muted" }, d.disclaimer));
  };
  v.replaceChildren(h("h1", {}, t("s_loans")),
    h("div", { class: "grid g-2e", style: "margin-top:12px" },
      h("div", { class: "card" }, h("h2", {}, t("s_score")),
        h("div", { class: "row" }, h("span", { class: "gauge num" }, rd.score), h("span", { class: "muted" }, `/ 100 · ${rd.band.replace(/_/g, " ")}`)),
        h("div", { class: "bar-track", style: "margin:8px 0 12px" }, h("div", { class: "bar-fill", style: `width:${rd.score}%` })),
        h("h3", {}, t("s_improve")), h("ul", {}, rd.top_tips.slice(0, 3).map(x => h("li", {}, x))),
        canWrite() ? h("button", { class: "btn", onclick: () => runTool("generate_loan_report", { amount: +amount.value || null }) }, "📄 " + t("s_pdf")) : null),
      h("div", { class: "card" }, h("h2", {}, t("s_best")),
        h("div", { class: "row" }, h("label", { class: "field" }, t("s_amount"), amount), h("button", { class: "btn primary", style: "align-self:flex-end", onclick: find }, t("s_find"))),
        h("div", { style: "margin-top:12px" }, res))));
  find();
}

async function viewSimpleSettings(v) {
  v.replaceChildren(h("h1", {}, t("settings")), prefsCard(), homeLayoutCard(), await privacyCard());
}

// ------------------------------------------------------------------ first-days tips
const TIPS = {
  dashboard: ["shows your cash, money in and out, and what needs attention today.", "আপনার নগদ, আয়-ব্যয় আর আজ কী দেখা দরকার তা দেখায়।"],
  chat: ["answers any question about your business, in English, বাংলা or Banglish. Try “How much profit last month?”", "ব্যবসা নিয়ে যেকোনো প্রশ্নের উত্তর দেয়, বাংলা বা ইংরেজিতে। যেমন: “গত মাসে লাভ কত?”"],
  data: ["is where you add records: write “sold 12 shirts 6000 cash”, or upload a bank or bKash file.", "এখানে হিসাব যোগ করুন: “১২টা শার্ট বিক্রি ৬০০০ নগদ” লিখুন, বা ব্যাংক/বিকাশ ফাইল আপলোড করুন।"],
  invoices: ["lets you bill a customer and record payments when they pay.", "ক্রেতাকে বিল দিন আর টাকা পেলে পেমেন্ট লিখে রাখুন।"],
  parties: ["shows who owes you and whom you owe, with every payment.", "কে আপনার কাছে বাকি আর আপনি কার কাছে বাকি, সব পেমেন্টসহ দেখায়।"],
  reports: ["gives profit & loss and cash flow for any period, as PDF or CSV.", "যেকোনো সময়ের লাভ-ক্ষতি ও নগদ প্রবাহ, PDF বা CSV হিসেবে।"],
  stock: ["tracks your products so you know what is running low.", "পণ্যের হিসাব রাখে, কোনটা কমে যাচ্ছে জানায়।"],
  financing: ["shows your loan-readiness score and loans that fit your numbers.", "আপনার ঋণ-প্রস্তুতি স্কোর আর আপনার জন্য মানানসই ঋণ দেখায়।"],
  actions: ["is where you approve payments and reminders the copilot prepared.", "কোপাইলটের তৈরি পেমেন্ট ও রিমাইন্ডার এখানে অনুমোদন করুন।"],
  settings: ["lets you change style, language and your home layout any time.", "স্টাইল, ভাষা আর হোম লেআউট যেকোনো সময় বদলান।"],
};
const TIP_DAYS = 3, TIP_CHANCE = 1 / 3;
function maybeShowTip() {
  const created = Date.parse((S.user.created_at || "") + "Z");
  if (!isFinite(created) || Date.now() - created > TIP_DAYS * 864e5 || Math.random() >= TIP_CHANCE) return;
  const key = "tips_seen:" + S.user.username;
  let seen = []; try { seen = JSON.parse(localStorage.getItem(key) || "[]"); } catch { /* private mode */ }
  const pool = routes().filter(r => TIPS[r]);
  const fresh = pool.filter(r => !seen.includes(r));
  const r = (fresh.length ? fresh : pool)[Math.floor(Math.random() * (fresh.length || pool.length))];
  if (!r) return;
  savePref(key, JSON.stringify([...seen.filter(x => x !== r), r]));
  const label = t(S.mode === "simple" ? SIMPLE_LABELS[r] : r);
  const tip = animatedRemove(h("div", { class: "tip-pop", role: "status" },
    h("div", { class: "row" }, h("b", { class: "grow" }, "💡 " + t("tip")), h("button", { class: "btn ghost sm", "aria-label": t("got_it"), onclick: () => tip.remove() }, "✕")),
    h("p", {}, h("span", { class: "tip-route" }, `${ICONS[r]} ${label}`), " ", TIPS[r][S.ui === "bn" ? 1 : 0]),
    h("div", { class: "row", style: "justify-content:flex-end" },
      h("button", { class: "btn ghost sm", onclick: () => tip.remove() }, t("got_it")),
      h("button", { class: "btn primary sm", onclick: () => { tip.remove(); location.hash = "#" + r; } }, t("show_me")))), 240);
  setTimeout(() => { document.body.appendChild(tip); setTimeout(() => tip.remove(), 20000); }, 1200);
}

// ------------------------------------------------------------------ onboarding wizard + home layout settings
function homeLayoutCard() {
  const hp = S.home || { widgets: [] }, bt = hp.business_type || "";
  const type = bt.startsWith("other:") ? bt.slice(6) : (S.reg && S.reg.business_types[bt]) || "Not set yet";
  const mode = { general: "Everything (general home)", simplified: "Simplified", custom: "Custom" }[hp.mode] || "–";
  return h("div", { class: "card", style: "margin-top:16px" },
    h("div", { class: "row" }, h("h2", { class: "grow" }, t("home_layout")), h("button", { class: "btn primary", onclick: () => openWizard(false) }, t("change_layout"))),
    h("p", { class: "small muted", style: "margin:0 0 8px" }, `Business type: ${type} · Layout: ${mode}`),
    h("div", { class: "row" }, hp.widgets.map((w, i) => h("span", { class: "chip" }, `${i + 1}. ${(S.reg && S.reg.widgets[w]) || w}`))),
    h("p", { class: "hint", style: "margin-top:8px" }, "Every change is recorded in the audit log."));
}

const BT_ICONS = { retail: "🛍", garments_trims: "🧵", restaurant_food: "🍲", pharmacy_grocery: "💊", wholesale_trading: "📦", service_salon: "✂", other: "✎" };
// Full-screen wizard: 1) business type, 2) pick a layout (AI-suggested, Simplified or Skip), 3) tick/order widgets + pages.
function openWizard(first) {
  const reg = S.reg, cur = S.home || {};
  const curBt = cur.business_type || "";
  let type = curBt ? curBt.split(":")[0] : "", text = curBt.startsWith("other:") ? curBt.slice(6) : "";
  let pick = null, widgets = [], nav = [], step = 0, reqId = 0;
  const stage = h("div", { class: "wiz-stage", "aria-live": "polite" });
  const dots = [0, 1, 2].map(i => h("li", {}, ["Your business", "Pick a layout", "Fine-tune"][i]));
  const close = () => { document.removeEventListener("keydown", onKey); wiz.remove(); };
  const onKey = e => { if (e.key === "Escape" && !first) close(); };
  const wiz = animatedRemove(h("div", { class: "wizard", role: "dialog", "aria-modal": "true", "aria-label": t("home_layout") },
    h("div", { class: "wiz-card" },
      h("div", { class: "row" }, h("h1", { class: "grow" }, first ? `${t("hello")}, ${(S.user.full_name || S.user.username).split(" ")[0]} 👋` : t("home_layout")),
        first ? null : h("button", { class: "btn ghost", onclick: close, "aria-label": "Close" }, "✕")),
      h("p", { class: "muted", style: "margin-top:0" }, "Let's set up your home screen. You can change this any time in Settings."),
      h("ol", { class: "wiz-steps" }, dots), stage,
      h("p", { class: "small muted wiz-foot" }, `${t("signed_in_as")} ${S.user.full_name || S.user.username} (${S.user.username}) · `,
        h("button", { class: "link", onclick: () => { close(); logout(false); } }, t("logout"))))), 260);
  document.addEventListener("keydown", onKey);
  document.body.appendChild(wiz);

  const save = async (mode, simple) => {
    try {
      S.home = await api("/api/home/prefs", { body: { business_type: type || "other", text, mode, widgets, nav, style: S.look } });
      close();
      if (simple) { S.mode = "simple"; savePref("ui_mode", "simple"); applyPrefs(); }
      renderShell(); route(); toast("Home layout saved", "ok");
    } catch (e) { toast(e.message, "bad"); }
  };
  const nextBtn = (label, onclick, disabled) => h("button", { class: "btn primary", onclick, disabled }, label);
  const backBtn = () => h("button", { class: "btn ghost", onclick: () => go(step - 1) }, "← Back");
  const STEPS = [
    () => {  // 1. business type
      const other = h("input", { type: "text", maxlength: 60, value: text, placeholder: "e.g. mobile phone repair", "aria-label": "Describe your business",
        class: type === "other" ? "" : "hidden", oninput: e => { text = e.target.value; } });
      const next = nextBtn("Next →", () => go(1), !type);
      const chips = Object.entries(reg.business_types).map(([k, label]) => h("button", { class: "bt-chip", "aria-pressed": String(k === type), onclick: e => {
        type = k; chips.forEach(c => c.setAttribute("aria-pressed", String(c === e.currentTarget)));
        other.classList.toggle("hidden", k !== "other"); next.disabled = false; if (k === "other") other.focus();
      } }, h("span", { "aria-hidden": "true" }, BT_ICONS[k] || "•"), label));
      return h("div", {}, h("h2", {}, "What kind of business do you run?"), h("div", { class: "bt-chips", role: "group" }, chips), other,
        h("div", { class: "row wiz-actions" }, h("span", { class: "grow" }), next));
    },
    () => {  // 2. layouts
      const grid = h("div", { class: "lay-grid" }, [0, 1, 2].map(() => h("div", { class: "lay-card skel" },
        h("span", { class: "skeleton-line" }), h("span", { class: "skeleton-line short" }), h("span", { class: "skeleton-line short" }))));
      const label = id => reg.widgets[id] || id;
      const layCard = (name, reason, ws, tag, onclick) => h("button", { class: "lay-card", onclick },
        h("div", { class: "row" }, h("b", { class: "grow" }, name), tag ? h("span", { class: "chip info" }, tag) : null),
        h("p", { class: "small muted" }, reason), h("div", { class: "lay-ws" }, ws.slice(0, 6).map(w => h("span", { class: "chip" }, label(w))),
          ws.length > 6 ? h("span", { class: "chip" }, `+${ws.length - 6}`) : null));
      const fixed = [
        layCard("Simplified", "Just the essentials in large, plain language.", reg.simplified, "Simple", () => choose({ mode: "simplified", widgets: reg.simplified, simple: true, name: "Simplified" })),
        layCard("Skip for now", "The full home screen with every widget.", Object.keys(reg.widgets), null, () => { widgets = Object.keys(reg.widgets); nav = defaultNav(); save("general", false); }),
      ];
      const id = ++reqId;
      api("/api/home/suggest", { body: { business_type: type, text } }).then(r => {
        if (id !== reqId) return;
        grid.replaceChildren(...r.layouts.map(l => layCard(l.name, l.reason, l.widgets, r.source === "rules" ? null : "AI", () => choose({ mode: "custom", widgets: l.widgets, name: l.name }))), ...fixed);
      }).catch(() => grid.replaceChildren(...fixed));
      return h("div", {}, h("h2", {}, "Pick a starting layout"), h("p", { class: "hint" }, "Suggested for your business. You can change the widgets in the next step."),
        grid, h("div", { class: "row wiz-actions" }, backBtn()));
    },
    () => {  // 3. tick/untick + order widgets, choose sidebar pages
      const list = h("ol", { class: "w-list" });
      const draw = () => {
        const all = [...widgets, ...Object.keys(reg.widgets).filter(w => !widgets.includes(w))];
        list.replaceChildren(...all.map(w => {
          const on = widgets.includes(w), i = widgets.indexOf(w);
          const move = d => { const j = i + d; [widgets[i], widgets[j]] = [widgets[j], widgets[i]]; draw(); list.querySelectorAll(".w-row")[j].querySelector(d < 0 ? ".up" : ".down")?.focus(); };
          return h("li", { class: "w-row" + (on ? "" : " off") },
            h("label", { class: "row grow" }, h("input", { type: "checkbox", checked: on, onchange: e => { if (e.target.checked) widgets.push(w); else widgets.splice(i, 1); draw(); } }), reg.widgets[w]),
            h("button", { class: "btn ghost sm up", disabled: !on || i === 0, "aria-label": `Move ${reg.widgets[w]} up`, onclick: () => move(-1) }, "↑"),
            h("button", { class: "btn ghost sm down", disabled: !on || i === widgets.length - 1, "aria-label": `Move ${reg.widgets[w]} down`, onclick: () => move(1) }, "↓"));
        }));
      };
      draw();
      const pages = h("div", { class: "row" }, reg.nav.map(r => h("label", { class: "chip nav-pick" },
        h("input", { type: "checkbox", checked: nav.includes(r), disabled: reg.nav_required.includes(r), onchange: e => {
          nav = e.target.checked ? reg.nav.filter(x => x === r || nav.includes(x)) : nav.filter(x => x !== r); } }), t(r))));
      return h("div", {}, h("h2", {}, pick.name || "Fine-tune your home"), h("p", { class: "hint" }, "Tick the widgets you want on your home screen and move them up or down."),
        list, h("h3", {}, "Pages in the sidebar"), pages,
        h("div", { class: "row wiz-actions" }, backBtn(), h("span", { class: "grow" }), nextBtn("Finish ✓", () => {
          if (!widgets.length) return toast("Pick at least one widget", "warn");
          const same = pick.mode === "simplified" && widgets.join() === reg.simplified.join();
          save(pick.mode === "simplified" && !same ? "custom" : pick.mode, !!pick.simple);
        })));
    },
  ];
  const defaultNav = () => reg.nav.filter(r => r !== "stock" || !reg.service_types.includes(type));  // service types: no Stock page
  const choose = p => {
    pick = p; widgets = p.widgets.slice();
    const sameType = curBt && curBt.split(":")[0] === type;
    nav = sameType && cur.nav ? cur.nav.slice() : defaultNav();
    go(2);
  };
  function go(n) {
    const dir = n >= step ? "fwd" : "back"; step = n;
    dots.forEach((d, i) => { d.classList.toggle("on", i <= n); d.toggleAttribute("aria-current", i === n); });
    const el = STEPS[n](); el.classList.add("wiz-step", "wiz-" + dir);
    stage.replaceChildren(el);
    (el.querySelector("[aria-pressed=true], .lay-card, input, button") || el).focus?.();
  }
  go(0);
}

// ------------------------------------------------------------------ tab bars (every page): sliding ink + panel cross-fade
function placeInk(bar) {
  let ink = bar.querySelector(".tab-ink");
  if (!ink) { ink = h("span", { class: "tab-ink", "aria-hidden": "true" }); bar.appendChild(ink); bar.classList.add("has-ink"); }
  const a = bar.querySelector("button.active");
  ink.style.opacity = a ? "1" : "0";
  if (a) ink.style.transform = `translateX(${a.offsetLeft}px) scaleX(${a.offsetWidth})`;
}
document.addEventListener("click", e => {
  const btn = e.target.closest(".tabs button");
  if (!btn || btn.classList.contains("active")) return;
  const bar = btn.closest(".tabs"), panel = bar.parentElement.lastElementChild;
  if (motionOK() && panel && panel !== bar && panel.offsetHeight) {  // old panel fades out as a ghost copy
    const ghost = panel.cloneNode(true);
    ghost.removeAttribute("id"); ghost.classList.add("panel-ghost"); ghost.setAttribute("aria-hidden", "true");
    ghost.style.top = panel.offsetTop + "px"; ghost.style.left = panel.offsetLeft + "px"; ghost.style.width = panel.offsetWidth + "px";
    panel.before(ghost); setTimeout(() => ghost.remove(), 260);
  }
  setTimeout(() => { placeInk(bar); restartAnim(panel, "panel-enter"); });
}, true);
let inkRaf = 0;
new MutationObserver(() => { cancelAnimationFrame(inkRaf); inkRaf = requestAnimationFrame(() =>
  document.querySelectorAll(".tabs:not(.has-ink)").forEach(placeInk)); }).observe(document.body, { childList: true, subtree: true });
window.addEventListener("resize", () => document.querySelectorAll(".tabs.has-ink").forEach(placeInk));

// ------------------------------------------------------------------ sliding hover highlight
// One pill per container (sidebar, tab bar, menu, table, list) glides to the hovered item: translate + size,
// ease-out. Event delegation, so new pages/rows need no setup.
const GLIDE_ITEMS = ".nav a, .tabs > button, .menu label.field, table.t tr, .rec, .sec-item";
let glideCur = null;
const glideHost = it => it.tagName === "TR" ? (it.closest(".scroll") || it.closest("table").parentElement) : it.parentElement;
function glideOff() {
  const p = glideCur && glideCur.querySelector(":scope > .glide");
  if (p) p.style.opacity = "0";
  glideCur = null;
}
function glideTo(host, it) {
  let pill = host.querySelector(":scope > .glide");
  if (!pill) { pill = h("span", { class: "glide", "aria-hidden": "true" }); host.classList.add("glide-host"); host.prepend(pill); }
  const fresh = glideCur !== host || pill.style.opacity !== "1";  // first hover: appear in place, then glide
  const hr = host.getBoundingClientRect(), ir = it.getBoundingClientRect();
  pill.classList.toggle("jump", fresh);
  pill.style.width = ir.width + "px"; pill.style.height = ir.height + "px";
  pill.style.transform = `translate(${ir.left - hr.left + host.scrollLeft - host.clientLeft}px, ${ir.top - hr.top + host.scrollTop - host.clientTop}px)`;
  pill.style.opacity = "1";
  if (fresh) { void pill.offsetWidth; pill.classList.remove("jump"); }
  glideCur = host;
}
document.addEventListener("pointerover", e => {
  if (e.pointerType === "touch") return;
  const it = e.target.closest && e.target.closest(GLIDE_ITEMS);
  if (!it || (it.tagName === "TR" && it.querySelector("th"))) { if (!(glideCur && glideCur.contains(e.target))) glideOff(); return; }
  const host = glideHost(it);
  if (glideCur && glideCur !== host) glideOff();
  glideTo(host, it);
});
document.addEventListener("pointerleave", glideOff);

// ------------------------------------------------------------------ start
boot().catch(() => renderLogin());
