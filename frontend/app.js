// SME Finance Copilot - single-page UI. Plain ES modules, no build step, works offline.
// Security: every piece of data is inserted with textContent (never innerHTML), so text from
// uploaded files or model output cannot inject markup. The session token lives in sessionStorage
// and is sent as a Bearer header (no cookies -> no CSRF surface).
import { barChart, hbarChart, lineChart } from "./charts.js";

// ------------------------------------------------------------------ i18n (UI chrome)
const T = {
  en: { dashboard: "Dashboard", chat: "Copilot", data: "Data", stock: "Stock", financing: "Financing", actions: "Actions",
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
    s_switch: "Want charts and details? Switch to Advanced in Settings." },
  bn: { dashboard: "ড্যাশবোর্ড", chat: "কোপাইলট", data: "তথ্য", stock: "স্টক", financing: "অর্থায়ন", actions: "কাজসমূহ",
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
    s_switch: "চার্ট ও বিস্তারিত চান? সেটিংসে অ্যাডভান্সড চালু করুন।" },
};
const pref = (k, d) => { try { return localStorage.getItem(k) || d; } catch { return d; } };
const savePref = (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } };
const S = {
  token: sessionStorage.getItem("token") || "",
  user: null, models: null, profile: pref("profile", ""),
  ui: pref("ui_lang", "en"), style: "lakh", conv: null, health: {},
  theme: pref("theme", "system"),          // system | light | dark
  mode: pref("ui_mode", "advanced"),       // simple | advanced
};
const t = k => (T[S.ui] && T[S.ui][k]) || T.en[k] || k;
function applyPrefs() {
  const root = document.documentElement;
  if (S.theme === "system") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", S.theme);
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
const pct = v => (v === null || v === undefined) ? "–" : `${v}%`;
const fmtDate = s => { const d = new Date(s + "T00:00:00"); return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" }); };

function toast(msg, ms = 3500) {
  const el = h("div", { class: "toast", role: "status" }, msg);
  document.body.appendChild(el); setTimeout(() => el.remove(), ms);
}
function modal(title, body, actions = []) {
  const bg = h("div", { class: "modal-bg", onclick: e => { if (e.target === bg) bg.remove(); } });
  const close = h("button", { class: "btn ghost", onclick: () => bg.remove(), "aria-label": "Close" }, "✕");
  bg.appendChild(h("div", { class: "modal", role: "dialog", "aria-modal": "true" },
    h("div", { class: "row" }, h("h2", { class: "grow", style: "margin:0" }, title), close), body,
    actions.length ? h("div", { class: "row", style: "justify-content:flex-end;margin-top:14px" }, actions) : null));
  document.body.appendChild(bg);
  return bg;
}

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (S.token) headers.Authorization = `Bearer ${S.token}`;
  let body = opts.body;
  if (body && !(body instanceof FormData) && typeof body !== "string") { headers["Content-Type"] = "application/json"; body = JSON.stringify(body); }
  const r = await fetch(path, { method: opts.method || (body ? "POST" : "GET"), headers, body });
  if (r.status === 401 && path !== "/api/auth/login") { logout(true); throw new Error("Session expired"); }
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : (j.detail && j.detail.message) || JSON.stringify(j.detail); } catch { /* ignore */ }
    throw new Error(msg);
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

function txnTable(rows, editable, categories = []) {
  const tb = h("table", { class: "t" }, h("tr", {}, ["Date", "Description / party", "Category", "Amount", "Flags", "Source"].map((x, i) => h("th", { class: i === 3 ? "r" : "" }, x))));
  for (const r of rows) {
    const cat = editable ? h("select", { onchange: async e => {
      try { await api(`/api/data/transactions/${r.id}`, { method: "PATCH", body: { category: e.target.value } }); toast("Category updated (audited)"); } catch (err) { toast(err.message); }
    } }, categories.map(c => h("option", { value: c, selected: c === r.category }, c))) : r.category;
    tb.appendChild(h("tr", {},
      h("td", { class: "num" }, r.date),
      h("td", {}, r.description || "", r.counterparty ? h("div", { class: "small muted" }, r.counterparty) : null,
        r.anomaly_reason ? h("div", { class: "small", style: "color:#b87d00" }, "⚠ " + r.anomaly_reason) : null),
      h("td", {}, cat),
      h("td", { class: "r", style: r.direction === "in" ? "color:var(--good-text)" : "" }, (r.direction === "in" ? "+" : "−") + money(r.amount).replace("-", "")),
      h("td", {}, (r.flags || []).map(f => h("span", { class: "chip " + (f === "injection_suspect" ? "bad" : "pend"), title: f }, f.replace("_", " ")))),
      h("td", { class: "small muted" }, `${r.source}${r.source_row ? " #" + r.source_row : ""}`)));
  }
  return h("div", { class: "scroll" }, tb);
}

// ------------------------------------------------------------------ login
async function renderLogin(err) {
  try { S.health = await (await fetch("/api/health")).json(); } catch { S.health = {}; }
  const u = h("input", { type: "text", placeholder: "username", autocomplete: "username", value: "nusrat" });
  const p = h("input", { type: "password", placeholder: "password", autocomplete: "current-password" });
  const msg = h("div", { class: "small", style: "color:var(--critical);min-height:18px" }, err || "");
  const submit = async e => {
    e.preventDefault();
    try {
      const r = await api("/api/auth/login", { body: { username: u.value, password: p.value } });
      S.token = r.token; sessionStorage.setItem("token", r.token); S.user = r.user; boot();
    } catch (ex) { msg.textContent = ex.message; }
  };
  const demo = S.health.demo_users ? h("div", { class: "notice", style: "margin-top:12px" },
    h("div", { style: "font-weight:600" }, "Demo logins (demo deployment only)"),
    S.health.demo_users.map(d => h("div", { class: "row small" }, h("span", { class: "chip" }, d.role),
      h("button", { class: "btn ghost sm", type: "button", onclick: () => { u.value = d.username; p.value = d.password; } }, `${d.username} / ${d.password}`)))) : null;
  $("#root").replaceChildren(h("div", { class: "login" }, h("div", { class: "card" },
    h("h1", {}, "SME Finance Copilot"),
    h("p", { class: "muted" }, "Cash flow, analysis and financing for Bangladesh small businesses. ব্যবসার হিসাব, নগদ প্রবাহ ও ঋণ সহায়ক।"),
    h("form", { onsubmit: submit, class: "grid", style: "gap:10px" },
      h("label", { class: "field" }, "Username", u), h("label", { class: "field" }, "Password", p), msg,
      h("button", { class: "btn primary", type: "submit" }, t("login"))),
    demo,
    h("p", { class: "small muted", style: "margin-top:12px" }, "Decision support only - not licensed financial advice."))));
  p.focus();
}
function logout(expired) {
  if (!expired && S.token) fetch("/api/auth/logout", { method: "POST", headers: { Authorization: `Bearer ${S.token}` } });
  S.token = ""; sessionStorage.removeItem("token"); renderLogin(expired ? "Please log in again." : "");
}

// ------------------------------------------------------------------ shell
const ROUTES = ["dashboard", "chat", "data", "stock", "financing", "actions", "audit", "settings"];
const SIMPLE_ROUTES = ["dashboard", "chat", "data", "financing", "settings"];
const SIMPLE_LABELS = { dashboard: "s_home", chat: "s_ask", data: "s_add", financing: "s_loans", settings: "settings_btn" };
const ICONS = { dashboard: "▦", chat: "✦", data: "⇪", stock: "▤", financing: "৳", actions: "✓", audit: "⛓", settings: "⚙" };
const routes = () => S.mode === "simple" ? SIMPLE_ROUTES : ROUTES;

// Re-render everything after a preference change (language, theme, mode).
function setPref(key, value) {
  S[key] = value;
  savePref({ ui: "ui_lang", theme: "theme", mode: "ui_mode" }[key], value);
  applyPrefs();
  if (S.user) { renderShell(); route(); }
}

// Language / theme / interface / number format controls, shared by the ⚙ menu and the Settings page.
function prefControls() {
  const sel = (value, options, onchange) => h("select", { onchange: e => onchange(e.target.value) },
    options.map(([v, l]) => h("option", { value: v, selected: v === value }, l)));
  const field = (label, control) => h("label", { class: "field" }, label, control);
  return [
    field(t("language"), sel(S.ui, [["en", "English"], ["bn", "বাংলা"]], v => setPref("ui", v))),
    field(t("theme"), sel(S.theme, [["system", t("th_system")], ["light", "☀ " + t("th_light")], ["dark", "☾ " + t("th_dark")]], v => setPref("theme", v))),
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

async function boot() {
  try {
    S.user = await api("/api/auth/me");
    S.models = await api("/api/models");
    const st = await api("/api/settings"); S.style = st.number_style;
  } catch { return; }
  if (!S.profile || !S.models.profiles.some(p => p.name === S.profile)) S.profile = S.models.default;
  renderShell();
  window.onhashchange = route;
  route();
}

let pendingCount = 0;
function renderShell() {
  const simple = S.mode === "simple";
  const nav = h("nav", { class: "nav", "aria-label": "Main" }, routes().filter(r => r !== "audit" || S.user.max_tier >= 1)
    .map(r => h("a", { href: "#" + r, id: "nav-" + r }, h("span", { "aria-hidden": "true" }, ICONS[r]), t(simple ? SIMPLE_LABELS[r] : r),
      r === "actions" ? h("span", { class: "badge hidden", id: "pend-badge" }, "0") : null)));
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
        simple ? null : h("span", { class: "chip", id: "asof" }, S.user.as_of ? "as of " + S.user.as_of : ""),
        h("span", { class: "grow" }), simple ? null : privacy, simple ? null : h("label", { class: "row small" }, t("model"), modelSel),
        simple ? null : h("span", { class: "chip", title: "Role-based permissions" }, `${S.user.full_name || S.user.username} · ${S.user.role}`),
        settingsMenu()),
      h("main", { class: "view", id: "view" }))));
  refreshPending();
}
async function refreshPending() {
  try {
    const p = await api("/api/actions/pending");
    pendingCount = p.filter(x => x.status === "pending").length;
    const b = $("#pend-badge"); if (b) { b.textContent = pendingCount; b.classList.toggle("hidden", !pendingCount); }
  } catch { /* ignore */ }
}
function route() {
  const r = (location.hash || "#dashboard").slice(1).split("?")[0];
  const name = routes().includes(r) ? r : "dashboard";
  document.querySelectorAll(".nav a").forEach(a => a.classList.toggle("active", a.id === "nav-" + name));
  const v = $("#view"); v.replaceChildren(h("div", { class: "muted" }, "Loading…"));
  const views = S.mode === "simple"
    ? { dashboard: viewSimpleHome, chat: viewChat, data: viewSimpleData, financing: viewSimpleFinancing, settings: viewSimpleSettings }
    : { dashboard: viewDashboard, chat: viewChat, data: viewData, stock: viewStock, financing: viewFinancing, actions: viewActions,
      audit: viewAudit, settings: viewSettings };
  views[name](v).catch(e => v.replaceChildren(h("div", { class: "notice warn" }, "Error: " + e.message)));
}

// ------------------------------------------------------------------ stock
async function viewStock(v) {
  const owner = S.user.role === "owner";
  const body = h("div", {});
  const BADGE = { out: ["bad", "Out"], low: ["warn", "Low"], ok: ["ok", "OK"] };
  const form = async (title, fields, path, mk) => {
    const vals = {}; for (const [k, label, dflt] of fields) { const x = prompt(`${title}: ${label}`, dflt ?? ""); if (x === null) return; vals[k] = x; }
    try { await api(path, { body: mk(vals) }); load(); } catch (e) { toast(e.message); }
  };
  const num = x => (x === "" || x == null ? 0 : Number(x));
  async function load() {
    const { items } = await api("/api/stock");
    const bar = h("div", { class: "row", style: "margin-bottom:12px" },
      h("button", { class: "btn primary", disabled: !owner, title: owner ? "" : "Owner only", onclick: () => form("New item", [["name", "Name"], ["unit", "Unit", "pcs"], ["opening_qty", "Opening quantity", "0"], ["reorder_level", "Reorder level", "0"], ["cost_price", "Cost price ৳", "0"], ["aliases", "Other names (comma separated)"]], "/api/items",
        x => ({ name: x.name, unit: x.unit || "pcs", opening_qty: num(x.opening_qty), reorder_level: num(x.reorder_level), cost_price: num(x.cost_price), aliases: x.aliases.split(",").map(a => a.trim()).filter(Boolean) })) }, "Add item"),
      h("button", { class: "btn", disabled: !owner || !items.length, onclick: () => {
        const name = prompt("Adjust which item? " + items.map(i => i.name).join(", ")); const it = items.find(i => i.name.toLowerCase() === (name || "").trim().toLowerCase()); if (!it) return;
        form("Adjust " + it.name, [["q", "Change (+ adds, − removes)"], ["r", "Reason", "count correction"]], "/api/stock/adjust", x => ({ item_id: it.id, qty_change: Number(x.q), reason: (x.r || "adjust").slice(0, 30) })); } }, "Adjust"),
      h("button", { class: "btn", onclick: () => download("/api/stock/export", "stock.xlsx").catch(e => toast(e.message)) }, "Export Excel"));
    body.replaceChildren(bar, items.length
      ? h("table", { class: "t" }, h("tr", {}, ["Item", "Sold 30d", "Remaining", "Days left", "Status"].map(x => h("th", {}, x))),
        items.map(i => h("tr", {}, h("td", {}, i.name), h("td", { class: "r" }, i.sold_30d), h("td", { class: "r" }, `${i.qty} ${i.unit}`),
          h("td", { class: "r" }, i.days_left ?? "–"), h("td", {}, h("span", { class: "chip " + BADGE[i.status][0] }, BADGE[i.status][1])))))
      : h("div", { class: "card" }, h("p", { class: "muted" }, "No items yet. Add your products to track how much is left."),
        h("button", { class: "btn primary", disabled: !owner, onclick: () => bar.firstChild.click() }, "Add item")));
  }
  v.replaceChildren(h("h1", {}, t("stock")), body);
  await load();
}

// ------------------------------------------------------------------ dashboard
async function viewDashboard(v) {
  const d = await api("/api/dashboard");
  $("#biz-name").textContent = d.business.name;
  $("#asof").textContent = "as of " + d.as_of;
  const k = d.kpis;
  const kpi = (label, value, sub, traceKey) => h("div", { class: "card kpi" },
    h("div", { class: "label" }, label, traceKey && d.kpi_traces[traceKey] ? h("button", { class: "btn ghost sm", title: t("howcalc"),
      onclick: () => modal(label, traceView(d.kpi_traces[traceKey])) }, "ⓘ") : null),
    h("div", { class: "value num" }, value), sub ? h("div", { class: "sub" }, sub) : null);
  const kpis = h("div", { class: "grid g-kpi" },
    kpi(t("cash"), money(k.cash_balance), "opening balance + recorded flows", "cash_balance"),
    kpi(t("income_m"), money(k.income_this_month), `expenses ${money(k.expense_this_month)}`, "income_this_month"),
    kpi(t("gm"), pct(k.gross_margin_3m), `net operating margin ${pct(k.net_margin_3m)}`, "margins"),
    kpi(t("ar_over"), money(k.receivables_overdue), `outstanding ${money(k.receivables_outstanding)}`, "receivables"));
  const minTone = k.forecast_min_30d < 0 ? "color:var(--critical)" : "";
  const kpis2 = h("div", { class: "grid g-kpi", style: "margin-top:16px" },
    h("div", { class: "card kpi" }, h("div", { class: "label" }, t("fmin")), h("div", { class: "value num", style: minTone }, money(k.forecast_min_30d)),
      h("div", { class: "sub" }, d.forecast.first_negative_date ? `⚠ below zero around ${d.forecast.first_negative_date}` : "estimate")),
    kpi(t("net_last"), money(k.net_last_month)),
    kpi(t("runway"), k.runway_months === null ? "not burning cash" : `${k.runway_months} months`, "at current average net cash flow"),
    kpi(t("expense_m"), money(k.expense_this_month)));

  // forecast chart
  const series = d.forecast.series;
  const events = {}; series.forEach(p => { if (p.events.length) events[p.date] = p.events; });
  const fcChart = lineChart({ series: [{ name: "Forecast balance", color: "var(--series-1)", points: series.map(p => ({ x: p.date, y: p.balance })) }],
    band: series.map(p => ({ x: p.date, lo: p.low, hi: p.high })), threshold: { value: d.forecast.threshold, label: `Safety level ${money(d.forecast.threshold)}` },
    events, yfmt: (v, axis) => money(v, axis), xfmt: fmtDate, xfmtLong: s => new Date(s).toDateString(), ariaLabel: "90 day cash flow forecast" });
  const fcCard = h("div", { class: "card" }, h("div", { class: "row" }, h("h2", { class: "grow" }, t("forecast")),
    h("button", { class: "btn ghost sm", onclick: async () => modal("Forecast model", traceView((await api("/api/forecast?horizon=90")).trace)) }, t("howcalc"))),
    fcChart, h("div", { class: "small muted" }, d.forecast.notes.join(" ")));

  // alerts
  const alertsCard = h("div", { class: "card" }, h("h2", {}, t("alerts")),
    d.alerts.length ? d.alerts.map(a => alertItem(a)) : h("div", { class: "muted" }, "Nothing urgent."));

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

  v.replaceChildren(kpis, kpis2,
    h("div", { class: "grid g-2", style: "margin-top:16px" }, fcCard, alertsCard),
    whatIfCard(series),
    h("div", { class: "grid g-2e", style: "margin-top:16px" }, h("div", { class: "card" }, h("h2", {}, t("monthly")), mChart),
      h("div", { class: "card" }, h("h2", {}, t("costs")), costs)));
}

function alertItem(a) {
  const st = a.data && a.data.suggested_tool;
  return h("div", { class: "alert-item" },
    h("div", { class: "row" }, h("span", { class: "sev " + a.severity }, a.severity), a.due_date ? h("span", { class: "small muted" }, a.due_date) : null),
    h("div", { class: "title" }, a.title), h("div", { class: "msg" }, a.message),
    h("div", { class: "row", style: "margin-top:4px" },
      st ? h("button", { class: "btn sm primary", onclick: () => runTool(st.name, st.args) }, st.name === "create_payment_reminder" ? "Send reminder" : st.name === "pay_supplier_invoice" ? "Pay (sandbox)" : "Do it") : null,
      a.kind === "overdue_invoice" ? h("button", { class: "btn sm", onclick: () => runTool("draft_invoice_followup", { invoice_id: a.data.invoice_id }) }, "Draft follow-up") : null,
      h("button", { class: "btn ghost sm", onclick: async e => { await api(`/api/alerts/${a.id}/dismissed`, { method: "POST" }); e.target.closest(".alert-item").remove(); } }, "Dismiss")));
}

async function runTool(name, args) {
  try {
    const out = await api(`/api/tools/${name}`, { body: { args } });
    if (out.status === "pending_confirmation") { confirmModal({ id: out.pending_action_id, ...out.data, tool: name }); return; }
    const d = out.data || {};
    const body = h("div", {}, d.message ? h("pre", { style: "white-space:pre-wrap" }, d.message) : null,
      d.body ? h("div", {}, h("div", { style: "font-weight:600" }, d.subject), h("pre", { style: "white-space:pre-wrap" }, d.body)) : null,
      d.download_url ? h("button", { class: "btn primary", onclick: () => download(d.download_url, d.filename) }, "Download PDF") : null,
      h("div", { class: "small muted" }, `Recorded in the operation log (${name}, tier ${out.tier}).`));
    modal("Done ✓", body);
  } catch (e) { toast(e.message); }
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
  const r = await fetch("/api/chat/stream", { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${S.token}` },
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
    try { await api("/api/feedback", { body: { interaction_id: id, rating, correction: corr.value || null } }); row.replaceChildren(h("span", { class: "small muted" }, "Thanks - feedback saved for evaluation.")); } catch (e) { toast(e.message); }
  };
  const row = h("div", { class: "row", style: "margin-top:6px" },
    h("button", { class: "btn ghost sm", title: "Helpful", onclick: () => sendFb("up") }, "👍"),
    h("button", { class: "btn ghost sm", title: "Not helpful", onclick: () => { if (corr.classList.contains("hidden")) { corr.classList.remove("hidden"); corr.focus(); } else sendFb("down"); } }, "👎"), corr);
  corr.addEventListener("keydown", e => { if (e.key === "Enter") sendFb("down"); });
  return row;
}

// ------------------------------------------------------------------ human-in-the-loop confirmation
function confirmCard(pa) {
  const amt = h("input", { type: "number", placeholder: "Re-type the amount", style: "width:170px" });
  const status = h("div", { class: "small" });
  const card = h("div", { class: "confirm-card" },
    h("div", { class: "small", style: "font-weight:600;color:var(--serious)" }, "SANDBOX payment - needs your confirmation"),
    h("div", { class: "amt num" }, money(pa.amount)), h("div", {}, pa.summary || ""),
    h("div", { class: "small muted" }, `Recipient: ${pa.recipient || "–"} · expires ${pa.expires_at ? new Date(pa.expires_at + "Z").toLocaleTimeString() : ""}`),
    h("div", { class: "row", style: "margin-top:8px" }, amt,
      h("button", { class: "btn primary", onclick: async () => {
        try {
          const r = await api(`/api/actions/${pa.id}/confirm`, { body: { confirm_amount: +amt.value } });
          const d = r.data; card.replaceChildren(h("div", { style: "color:var(--good-text);font-weight:600" }, `✓ Executed in sandbox: ${money(d.amount)} to ${d.recipient_name}`),
            h("div", { class: "small muted" }, `Sandbox balance ${money(d.balance_before)} → ${money(d.balance_after)} · logged with confirmation status "confirmed"`));
          refreshPending();
        } catch (e) { status.textContent = "✕ " + e.message; status.style.color = "var(--critical)"; }
      } }, "Confirm"),
      h("button", { class: "btn", onclick: async () => { try { await api(`/api/actions/${pa.id}/reject`, { method: "POST" }); card.replaceChildren(h("div", { class: "muted" }, "Rejected - nothing was sent.")); refreshPending(); } catch (e) { toast(e.message); } } }, "Reject")),
    status);
  if (S.user.role !== "owner") card.appendChild(h("div", { class: "small muted" }, "Only the owner can confirm money movements."));
  return card;
}
function confirmModal(pa) { const m = modal("Confirm sandbox payment", confirmCard(pa)); return m; }

// ------------------------------------------------------------------ data
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
  const showError = e => { result.replaceChildren(h("div", { class: "notice warn", style: "margin-top:10px" }, `Not imported: ${e.message}`)); toast(e.message); };
  const upload = h("button", { class: "btn primary", disabled: !canWrite, onclick: async () => {
    if (!file.files[0]) return toast("Choose a file");
    const fd = new FormData(); fd.append("file", file.files[0]); fd.append("doc_type", dtype.value);
    try { showReport(await api("/api/data/upload", { body: fd })); loadTxns(); } catch (e) { showError(e); }
  } }, "Upload");
  const paste = h("textarea", { placeholder: "Paste CSV text here (Date, Description, Amount, …)" });
  const pasteBtn = h("button", { class: "btn", disabled: !canWrite, onclick: async () => { try { showReport(await api("/api/data/paste", { body: { text: paste.value, doc_type: dtype.value } })); loadTxns(); } catch (e) { showError(e); } } }, "Import pasted text");

  const entry = h("input", { type: "text", placeholder: "e.g. sold 12 shirts for 6000 taka cash · dokan bhara 15000 dilam · ১২টা শার্ট বিক্রি ৬০০০ টাকা", class: "grow" });
  const preview = h("div", { class: "small muted", style: "min-height:20px" });
  let timer;
  entry.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(async () => {
    if (!entry.value.trim()) { preview.textContent = ""; return; }
    const p = await api("/api/data/entry/preview", { body: { text: entry.value } });
    preview.textContent = p.amount ? `→ ${p.direction === "in" ? "Income" : p.direction === "out" ? "Expense" : "?"} ${money(p.amount)} · ${p.category} · ${p.channel} · ${p.txn_date}${p.counterparty ? " · " + p.counterparty : ""}${p.quantity ? ` · qty ${p.quantity} ${p.item}` : ""} (confidence ${Math.round(p.confidence * 100)}%)` : `Missing: ${p.missing.join(", ")}`;
  }, 250); });
  const record = h("button", { class: "btn primary", disabled: !canWrite, onclick: async () => {
    try { const r = await api("/api/data/entry", { body: { text: entry.value } }); toast(r.data.recorded ? "Recorded ✓" : `Not recorded: ${r.data.missing?.join(", ") || r.data.duplicate_warning}`); entry.value = ""; preview.textContent = ""; if (r.data.stock && r.data.stock.ask_item) askWhichItem(r.data.stock, preview); loadTxns(); } catch (e) { toast(e.message); }
  } }, "Record");

  const flaggedOnly = h("input", { type: "checkbox" });
  const tableWrap = h("div", {});
  const imports = h("div", {});
  async function loadTxns() {
    const d = await api(`/api/data/transactions?limit=200${flaggedOnly.checked ? "&flagged=true" : ""}`);
    tableWrap.replaceChildren(txnTable(d.rows, canWrite, d.categories));
    const im = await api("/api/data/imports");
    imports.replaceChildren(h("table", { class: "t" }, h("tr", {}, ["File", "Type", "Rows", "Imported", "Dup.", "Anom.", "Inj.", "By"].map(x => h("th", {}, x))),
      im.map(b => h("tr", {}, h("td", {}, b.filename), h("td", {}, b.doc_type), h("td", {}, b.rows_total), h("td", {}, b.imported), h("td", {}, b.duplicates), h("td", {}, b.anomalies), h("td", {}, b.injection_flags), h("td", {}, b.created_by)))));
  }
  flaggedOnly.addEventListener("change", loadTxns);
  v.replaceChildren(
    h("h1", {}, t("data")),
    !canWrite ? h("div", { class: "notice" }, "Your role is read-only (Tier 0): uploads and entries are disabled.") : null,
    h("div", { class: "grid g-2e", style: "margin-top:12px" },
      h("div", { class: "card" }, h("h2", {}, "Upload sales, expenses, bank or bKash/Nagad/Rocket statements, invoices"),
        h("div", { class: "row" }, file, dtype, upload), h("h3", {}, "…or paste"), paste, h("div", { class: "row", style: "margin-top:6px" }, pasteBtn), result),
      h("div", { class: "card" }, h("h2", {}, "Quick entry (English / বাংলা / Banglish)"), h("div", { class: "row" }, entry, record), preview,
        h("h3", {}, "Import history"), imports)),
    h("div", { class: "card", style: "margin-top:16px" }, h("div", { class: "row" }, h("h2", { class: "grow" }, "Transactions"),
      h("label", { class: "row small" }, flaggedOnly, "Only flagged (duplicates / anomalies)")), tableWrap));
  await loadTxns();
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
    h("button", { class: "btn", disabled: S.user.max_tier < 1, onclick: () => runTool("generate_loan_report", { amount: +amount.value || null, purpose: purpose.value }) }, "Generate loan-readiness PDF"),
    h("button", { class: "btn", disabled: S.user.max_tier < 1, onclick: () => runTool("prepare_loan_checklist", { amount: +amount.value || null }) }, "Prepare application checklist"));
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
        : h("div", { class: "muted" }, "No money requests yet. Ask the copilot e.g. “Transfer 25000 to Dhaka Zipper House”."));
    } else if (i === 1) {
      const r = await api("/api/reminders");
      body.replaceChildren(h("div", { class: "notice small" }, "Simulated outbox: messages are queued, not sent to real phones."),
        h("table", { class: "t" }, h("tr", {}, ["Send on", "To", "Channel", "Amount", "Message", "Status"].map(x => h("th", {}, x))),
          r.map(x => h("tr", {}, h("td", {}, x.remind_on), h("td", {}, x.counterparty), h("td", {}, x.channel), h("td", { class: "r" }, money(x.amount)), h("td", { class: "small" }, x.message), h("td", {}, x.status)))));
    } else if (i === 2) {
      const r = await api("/api/drafts");
      body.replaceChildren(...(r.length ? r : [null]).map(d => !d ? h("div", { class: "muted" }, "No drafts yet.") : h("div", { class: "card", style: "margin-bottom:10px" },
        h("div", { class: "row" }, h("b", { class: "grow" }, d.subject), h("span", { class: "chip" }, `${d.kind} · ${d.language} · ${d.status}`)),
        h("pre", { style: "white-space:pre-wrap;font:inherit" }, d.body),
        S.user.max_tier >= 1 ? h("div", { class: "row" }, h("button", { class: "btn sm", onclick: async () => { await api(`/api/drafts/${d.id}`, { method: "PATCH", body: { status: "approved" } }); show(2); } }, "Approve"),
          h("button", { class: "btn sm", onclick: () => navigator.clipboard.writeText(d.body).then(() => toast("Copied")) }, "Copy"),
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
  v.replaceChildren(h("h1", {}, t("settings")), prefsCard(),
    h("div", { class: "grid g-2e", style: "margin-top:16px" },
      h("div", { class: "card" }, h("h2", {}, "Alerts"), h("label", { class: "field" }, "Low-balance safety level (৳)", thr),
        h("button", { class: "btn", style: "margin-top:8px", disabled: S.user.max_tier < 1, onclick: async () => { await api("/api/settings", { method: "PATCH", body: { low_balance_threshold: +thr.value } }); toast("Saved"); } }, "Save"),
        h("h2", { style: "margin-top:16px" }, "Data protection"),
        h("ul", { class: "small" },
          h("li", {}, `PII masking before cloud models: ${S.models.mask_pii ? "ON" : "OFF"}`),
          h("li", {}, `Local-only mode (no data leaves this machine): ${S.models.local_only_mode ? "ON" : "OFF"} - set LOCAL_ONLY_MODE=true`),
          h("li", {}, "Account/wallet numbers, phones, TIN and trade licence are encrypted at rest (Fernet)."),
          h("li", {}, "Every agent decision and action is in the hash-chained audit log."))),
      h("div", { class: "card" }, h("h2", {}, "Your data"),
        h("button", { class: "btn", disabled: !isOwner, onclick: () => download("/api/privacy/export", "my_business_data.json") }, "Export my data (JSON)"),
        h("h3", {}, "Delete all business data"),
        h("p", { class: "small muted" }, "Removes transactions, invoices, drafts, reports, chats and the interaction dataset lines for this business and deactivates its accounts. The masked audit log is kept to prove the deletion happened."),
        h("div", { class: "row" }, pw, phrase, h("button", { class: "btn danger", disabled: !isOwner, onclick: async () => {
          try { const r = await api("/api/privacy/delete", { body: { password: pw.value, confirm: phrase.value } }); toast("Deleted: " + JSON.stringify(r.rows_deleted)); logout(true); } catch (e) { toast(e.message); }
        } }, "Delete")), !isOwner ? h("div", { class: "small muted" }, "Owner only.") : null)),
    h("div", { class: "card", style: "margin-top:16px" }, h("h2", {}, "Bangladesh compliance awareness"),
      h("p", { class: "small muted" }, comp.disclaimer),
      comp.rules.map(r => h("div", { class: "alert-item" }, h("div", { class: "row" }, h("b", { class: "grow" }, r.title), r.applies_to_you ? h("span", { class: "chip" }, "applies to you") : null, h("span", { class: "illus" }, r.verify_label)),
        h("div", { class: "msg" }, r.summary), r.source_url ? h("div", { class: "small muted" }, "Check: " + r.source_url) : null))));
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
  const tile = (label, value, tone) => h("div", { class: "card kpi" }, h("div", { class: "label" }, label),
    h("div", { class: "value num", style: tone || "" }, value));
  const waiting = pend.filter(x => x.status === "pending");
  const todo = d.alerts.slice(0, 5).map(a => {
    const st = a.data && a.data.suggested_tool;
    return h("div", { class: "alert-item" },
      h("div", { class: "title" }, h("span", { class: "sev " + a.severity }), " ", a.title),
      h("div", { class: "msg" }, a.message),
      h("div", { class: "row", style: "margin-top:6px" },
        st && canWrite() ? h("button", { class: "btn primary", onclick: () => runTool(st.name, st.args) },
          st.name === "create_payment_reminder" ? "Send reminder" : st.name === "pay_supplier_invoice" ? "Pay (sandbox)" : "Do it") : null,
        h("button", { class: "btn ghost", onclick: async e => { await api(`/api/alerts/${a.id}/dismissed`, { method: "POST" }); e.target.closest(".alert-item").remove(); } }, t("s_dismiss"))));
  });
  const chart = lineChart({ series: [{ name: t("s_next90"), color: "var(--series-1)", points: f.series.map(p => ({ x: p.date, y: p.balance })) }],
    threshold: { value: f.threshold, label: money(f.threshold) }, yfmt: (x, axis) => money(x, axis), xfmt: fmtDate, height: 220, ariaLabel: t("s_next90") });
  v.replaceChildren(
    h("h1", {}, `${t("hello")}, ${first} 👋`), status,
    h("div", { class: "grid g-kpi", style: "margin-top:16px" },
      tile(t("s_cash_now"), money(k.cash_balance)),
      tile(t("s_in"), money(k.income_this_month), "color:var(--good-text)"),
      tile(t("s_out"), money(k.expense_this_month)),
      tile(t("s_owed"), money(k.receivables_overdue), k.receivables_overdue > 0 ? "color:var(--critical)" : "")),
    waiting.length ? h("div", { class: "card", style: "margin-top:16px" }, h("h2", {}, `${t("s_confirm")} (${waiting.length})`), waiting.map(confirmCard)) : "",
    h("div", { class: "grid g-2e", style: "margin-top:16px" },
      h("div", { class: "card" }, h("h2", {}, t("s_todo")), todo.length ? todo : h("div", { class: "muted" }, t("s_nothing"))),
      h("div", { class: "card" }, h("h2", {}, t("s_next90")), chart)),
    quickEntryCard(),
    h("p", { class: "small muted", style: "margin-top:16px" }, t("s_switch")));
}

// Shown after a record that could not be linked to an item (no match / no quantity). Never guesses.
function askWhichItem(st, host) {
  const sel = h("select", {}, h("option", { value: "" }, "Which item?"), (st.items || []).map(i => h("option", { value: i.id }, i.name)), h("option", { value: "new" }, "+ New item"));
  const qty = st.quantity ? null : h("input", { type: "number", min: "0", step: "any", placeholder: "Qty", style: "width:80px" });
  const done = () => host.replaceChildren();
  const link = async id => { try { await api("/api/stock/link", { body: { transaction_id: st.transaction_id, item_id: Number(id), quantity: qty && qty.value ? Number(qty.value) : undefined } }); toast("Stock updated"); done(); } catch (e) { toast(e.message); } };
  sel.addEventListener("change", async () => {
    if (!sel.value) return;
    if (sel.value !== "new") return link(sel.value);
    const name = prompt("New item name", st.suggested_name || ""); if (!name) { sel.value = ""; return; }
    try { const r = await api("/api/items", { body: { name } }); link(r.id); } catch (e) { toast(e.message); sel.value = ""; }
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
  const save = async (confirmed = false) => {
    if (!entry.value.trim()) return;
    try {
      const r = await api("/api/data/entry", { body: { text: entry.value, confirmed } });
      const d = r.data;
      if (d.needs_confirm) {  // uncertain reading: show the preview, do not save yet
        preview.replaceChildren(d.preview + (d.reason ? ` (${d.reason}) ` : " "),
          h("button", { class: "btn primary", onclick: () => save(true) }, t("s_save")),
          h("button", { class: "btn", onclick: () => { preview.textContent = ""; entry.focus(); } }, "Edit"));
        return;
      }
      if (d.manual_form) { toast(d.preview || "Could not read this, please use the form"); return; }
      toast(d.recorded ? t("s_saved") : `Not saved: ${d.missing?.join(", ") || d.duplicate_warning}`);
      if (d.recorded) {
        const id = d.transaction_id;
        entry.value = "";
        const undo = h("button", { class: "btn", onclick: async () => { try { await api(`/api/data/transactions/${id}`, { method: "DELETE" }); preview.textContent = ""; if (onSaved) onSaved(); } catch (e) { toast(e.message); } } }, "Undo");
        preview.replaceChildren(t("s_saved") + " ", undo);
        if (d.stock && d.stock.ask_item) { const host = h("div", { class: "small", style: "margin-top:6px" }); preview.appendChild(host); askWhichItem(d.stock, host); }
        setTimeout(() => { if (preview.contains(undo)) preview.textContent = ""; }, 6000);
        if (onSaved) onSaved();
      }
    } catch (e) { toast(e.message); }
  };
  entry.addEventListener("keydown", e => { if (e.key === "Enter") save(false); });
  return h("div", { class: "card", style: "margin-top:16px" }, h("h2", {}, t("s_add_title")),
    h("div", { class: "row" }, entry, h("button", { class: "btn primary", disabled: !canWrite(), onclick: () => save(false) }, t("s_save"))), preview);
}

async function viewSimpleData(v) {
  const list = h("div", {});
  const load = async () => {
    const d = await api("/api/data/transactions?limit=15");
    list.replaceChildren(...d.rows.map(r => h("div", { class: "rec" },
      h("div", { class: "grow" }, h("div", {}, r.description || r.counterparty || r.category.replace(/_/g, " ")),
        h("div", { class: "small muted" }, `${fmtDate(r.date)} · ${r.category.replace(/_/g, " ")}`)),
      h("div", { class: "num", style: `font-weight:650;${r.direction === "in" ? "color:var(--good-text)" : ""}` },
        (r.direction === "in" ? "+" : "−") + money(r.amount).replace("-", "")))));
  };
  const file = h("input", { type: "file", accept: ".csv,.tsv,.txt,.xlsx,.xls", disabled: !canWrite() });
  const upload = h("button", { class: "btn", disabled: !canWrite(), onclick: async () => {
    if (!file.files[0]) return toast("Choose a file");
    const fd = new FormData(); fd.append("file", file.files[0]); fd.append("doc_type", "auto");
    try { const r = await api("/api/data/upload", { body: fd }); toast(r.already_imported ? "Already imported" : `${t("s_saved")} ${r.imported} / ${r.rows_total}`); load(); } catch (e) { toast(e.message); }
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
  v.replaceChildren(h("h1", {}, t("settings")), prefsCard());
}

// ------------------------------------------------------------------ start
if (S.token) boot().catch(() => renderLogin()); else renderLogin();
