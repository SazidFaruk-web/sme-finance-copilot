// Home price drawer: public market prices near the business and where they may go next month.
// It starts minimised to an edge tab, so Home keeps its two cards; the owner opens it when they want it.
// Every number comes from /api/market/prices (public WFP data and a forecasting model). Data is inserted as
// text, never markup. Direction is always written in words with a sign, never by colour or arrow alone.

const KEY = "market_drawer";  // "open" | "closed" in this browser; default closed
const FIRST_BATCH = 5;

const COPY = {
  en: {
    tab: "Prices", open: "Open market prices", close: "Minimise market prices", title: "Market prices near you",
    intro: "Public prices of items your kind of business buys or sells, and where they may go next month.",
    loading: "Loading prices…", error: "Prices couldn't load. Your records are not affected.", retry: "Try again",
    empty: "No public prices are available for your kind of business yet.", more: "Show more", less: "Show fewer",
    district: "district", division: "division", national: "Bangladesh average", markets: n => `${n} market${n === 1 ? "" : "s"}`,
    up: (p, m) => `Likely up about ${p} by ${m}`, down: (p, m) => `Likely down about ${p} by ${m}`,
    steady: m => `Likely to stay about the same through ${m}`, unsure: (lo, hi) => `Hard to call: could move between ${lo} and ${hi}`,
    upUnsure: (lo, hi, m) => `Likely up by ${m}, but hard to say how much: ${lo} to ${hi}`,
    downUnsure: (lo, hi, m) => `Likely down by ${m}, but hard to say how much: ${lo} to ${hi}`,
    range: (lo, hi) => `Could be ${lo} to ${hi}.`, noForecast: "Not enough recent data to forecast.",
    details: "Details", lastMonth: "Compared with the month before", lastYear: "Compared with a year earlier",
    twoYears: "Last 2 years", expected: m => `Expected in ${m}`, area: "Prices from", observed: "Price recorded",
    sure: "How sure is this?",
    model: e => `Forecast by ${e}, an AI time-series model running on this server, from up to 3 years of monthly prices.`,
    stat: "Forecast by a statistical estimate from up to 3 years of monthly prices (the AI model isn't installed on this server).",
    tested: "Tested on 170 past price series, the range held the real price about 8 times in 10. Prices often stay the same, so treat this as a guide, not a promise.",
    source: (m) => `Source: World Food Programme market prices (HDX, CC BY-IGO). Latest data: ${m}. These are market averages, not live shop prices.`,
    sourceLink: "Open the source",
  },
  bn: {
    tab: "বাজারদর", open: "বাজারদর খুলুন", close: "বাজারদর ছোট করুন", title: "আপনার এলাকার বাজারদর",
    intro: "আপনার ধরনের ব্যবসা যে পণ্য কেনে বা বেচে, তার প্রকাশিত দাম এবং আগামী মাসে দাম কোন দিকে যেতে পারে।",
    loading: "দাম আনা হচ্ছে…", error: "দাম আনা যায়নি। আপনার হিসাবে কোনো প্রভাব পড়েনি।", retry: "আবার চেষ্টা",
    empty: "আপনার ধরনের ব্যবসার জন্য এখনও প্রকাশিত দাম পাওয়া যায়নি।", more: "আরও দেখুন", less: "কম দেখুন",
    district: "জেলা", division: "বিভাগ", national: "বাংলাদেশের গড়", markets: n => `${n}টি বাজার`,
    up: (p, m) => `${m}-এর মধ্যে প্রায় ${p} বাড়তে পারে`, down: (p, m) => `${m}-এর মধ্যে প্রায় ${p} কমতে পারে`,
    steady: m => `${m} পর্যন্ত দাম প্রায় একই থাকতে পারে`, unsure: (lo, hi) => `বলা কঠিন: ${lo} থেকে ${hi} পর্যন্ত বদলাতে পারে`,
    upUnsure: (lo, hi, m) => `${m}-এর মধ্যে দাম বাড়তে পারে, তবে কতটা তা বলা কঠিন: ${lo} থেকে ${hi}`,
    downUnsure: (lo, hi, m) => `${m}-এর মধ্যে দাম কমতে পারে, তবে কতটা তা বলা কঠিন: ${lo} থেকে ${hi}`,
    range: (lo, hi) => `${lo} থেকে ${hi} হতে পারে।`, noForecast: "পূর্বাভাসের জন্য যথেষ্ট সাম্প্রতিক তথ্য নেই।",
    details: "বিস্তারিত", lastMonth: "আগের মাসের তুলনায়", lastYear: "এক বছর আগের তুলনায়",
    twoYears: "গত ২ বছর", expected: m => `${m}-এ সম্ভাব্য দাম`, area: "দামের এলাকা", observed: "দাম লেখা হয়েছে",
    sure: "এটা কতটা নিশ্চিত?",
    model: e => `${e} দিয়ে পূর্বাভাস। এটি এই সার্ভারে চলা একটি এআই টাইম-সিরিজ মডেল, যা ৩ বছর পর্যন্ত মাসিক দাম দেখে।`,
    stat: "৩ বছর পর্যন্ত মাসিক দাম থেকে পরিসংখ্যানভিত্তিক অনুমান (এই সার্ভারে এআই মডেল বসানো নেই)।",
    tested: "আগের ১৭০টি দামের ধারায় পরীক্ষায়, প্রতি ১০ বারে প্রায় ৮ বার আসল দাম এই সীমার মধ্যে ছিল। দাম প্রায়ই একই থাকে, তাই এটিকে নিশ্চয়তা নয়, দিকনির্দেশনা হিসেবে দেখুন।",
    source: (m) => `উৎস: বিশ্ব খাদ্য কর্মসূচির (WFP) বাজারদর (HDX, CC BY-IGO)। সর্বশেষ তথ্য: ${m}। এগুলো বাজারের গড় দাম, দোকানের সরাসরি দাম নয়।`,
    sourceLink: "উৎস দেখুন",
  },
  zh: {
    tab: "市场价", open: "打开市场价格", close: "收起市场价格", title: "您附近的市场价格",
    intro: "与您这类生意相关的商品的公开价格，以及下个月可能的走势。",
    loading: "正在加载价格……", error: "价格无法加载。您的记录不受影响。", retry: "重试",
    empty: "目前还没有适合您这类生意的公开价格。", more: "显示更多", less: "收起",
    district: "县", division: "专区", national: "孟加拉国平均", markets: n => `${n} 个市场`,
    up: (p, m) => `到${m}可能上涨约 ${p}`, down: (p, m) => `到${m}可能下跌约 ${p}`,
    steady: m => `到${m}可能基本持平`, unsure: (lo, hi) => `难以判断：可能在 ${lo} 到 ${hi} 之间变动`,
    upUnsure: (lo, hi, m) => `到${m}可能上涨，但幅度难以判断：${lo} 到 ${hi}`,
    downUnsure: (lo, hi, m) => `到${m}可能下跌，但幅度难以判断：${lo} 到 ${hi}`,
    range: (lo, hi) => `可能在 ${lo} 到 ${hi} 之间。`, noForecast: "近期数据不足，无法预测。",
    details: "详情", lastMonth: "与上个月相比", lastYear: "与一年前相比",
    twoYears: "过去 2 年", expected: m => `${m}预计价格`, area: "价格来源地区", observed: "价格记录时间",
    sure: "这个预测有多可靠？",
    model: e => `由 ${e} 预测。这是在本服务器上运行的 AI 时间序列模型，参考最多 3 年的月度价格。`,
    stat: "根据最多 3 年的月度价格做出的统计估计（本服务器未安装 AI 模型）。",
    tested: "在 170 组历史价格上测试时，实际价格大约每 10 次中有 8 次落在这个范围内。价格经常保持不变，请把它当作参考，而不是保证。",
    source: (m) => `来源：世界粮食计划署（WFP）市场价格（HDX，CC BY-IGO）。最新数据：${m}。这些是市场平均价，不是商店的实时价格。`,
    sourceLink: "打开来源",
  },
};

const LOCALES = { bn: "bn-BD", zh: "zh-CN" };

function svgEl(tag, attrs, ...kids) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  kids.forEach(k => el.appendChild(k));
  return el;
}

function trendIcon() {
  return svgEl("svg", { viewBox: "0 0 24 24", width: "20", height: "20", fill: "none", stroke: "currentColor",
    "stroke-width": "1.8", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" },
  svgEl("path", { d: "M3 17l6-6 4 4 8-8M15 7h6v6" }));
}

function sparkline(points) {
  const values = points.map(p => p[1]);
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const w = 240, ht = 48, step = values.length > 1 ? w / (values.length - 1) : w;
  const d = values.map((v, i) => `${i ? "L" : "M"}${(i * step).toFixed(1)},${(ht - 4 - ((v - min) / span) * (ht - 8)).toFixed(1)}`).join(" ");
  return svgEl("svg", { class: "market-spark", viewBox: `0 0 ${w} ${ht}`, preserveAspectRatio: "none", "aria-hidden": "true", focusable: "false" },
    svgEl("path", { d, fill: "none", stroke: "currentColor", "stroke-width": "2", "vector-effect": "non-scaling-stroke" }));
}

export function createMarketDrawer({ h, api, S }) {
  let open = false, data = null, failed = false, loading = false, showAll = false, root = null, disabled = false;
  let entering = false;  // slide in only when the owner opens it, not on every redraw
  const c = () => COPY[S.ui] || COPY.en;
  const locale = () => LOCALES[S.ui] || "en-GB";
  const num = (v, digits = 2) => new Intl.NumberFormat(locale(), { maximumFractionDigits: digits }).format(v);
  const taka = v => "৳" + num(v);
  const pct = v => (v > 0 ? "+" : v < 0 ? "−" : "") + num(Math.abs(v), 1) + "%";
  const month = (ym, long = false) => {
    const [y, m] = ym.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, 15)).toLocaleDateString(locale(), { month: long ? "long" : "short", year: "numeric", timeZone: "UTC" });
  };
  const label = x => (x && (x[S.ui] || x.en)) || "";
  const remember = v => { try { localStorage.setItem(KEY, v ? "open" : "closed"); } catch { /* private mode */ } };
  const wasOpen = () => { try { return localStorage.getItem(KEY) === "open"; } catch { return false; } };

  function outlook(item) {
    const f = item.forecast, t = c();
    if (!f) return { text: t.noForecast, tone: "flat", sign: "" };
    const m = month(f.month, true);
    if (f.uncertain) {  // a wide range can still agree on the direction; say so instead of "hard to call"
      const [lo, hi] = [pct(f.low_pct), pct(f.high_pct)];
      if (f.low_pct > 0) return { text: t.upUnsure(lo, hi, m), tone: "up", sign: "↑" };
      if (f.high_pct < 0) return { text: t.downUnsure(lo, hi, m), tone: "down", sign: "↓" };
      return { text: t.unsure(lo, hi), tone: "flat", sign: "↕" };
    }
    if (Math.abs(f.change_pct) < 2) return { text: t.steady(m), tone: "flat", sign: "→", range: t.range(pct(f.low_pct), pct(f.high_pct)) };
    const up = f.change_pct > 0;
    return { text: (up ? t.up : t.down)(pct(Math.abs(f.change_pct)).replace(/^[+−]/, ""), m), tone: up ? "up" : "down",
      sign: up ? "↑" : "↓", range: t.range(pct(f.low_pct), pct(f.high_pct)) };
  }

  function areaText(a) {
    const t = c();
    const where = a.level === "national" ? t.national : `${a.name} ${t[a.level]}`;
    return `${where} · ${t.markets(a.markets)}`;
  }

  function row(item) {
    const t = c(), o = outlook(item), id = `market-${item.id.replace(/[^a-z0-9]/gi, "-")}`;
    const detail = h("div", { class: "market-detail", id, hidden: true },
      item.history?.length > 2 ? h("figure", { class: "market-chart" }, sparkline(item.history),
        h("figcaption", { class: "market-meta" }, `${t.twoYears}: ${taka(Math.min(...item.history.map(p => p[1])))} – ${taka(Math.max(...item.history.map(p => p[1])))}`)) : null,
      h("dl", { class: "market-facts" },
        item.change_1m_pct != null ? [h("dt", {}, t.lastMonth), h("dd", {}, pct(item.change_1m_pct))] : null,
        item.change_12m_pct != null ? [h("dt", {}, t.lastYear), h("dd", {}, pct(item.change_12m_pct))] : null,
        item.forecast ? [h("dt", {}, t.expected(month(item.forecast.month, true))), h("dd", {}, taka(item.forecast.price))] : null,
        [h("dt", {}, t.area), h("dd", {}, areaText(item.area))],
        [h("dt", {}, t.observed), h("dd", {}, month(item.observed, true))]));
    const toggle = h("button", { class: "market-row", type: "button", "aria-expanded": "false", "aria-controls": id,
      onclick: e => { const on = detail.hidden; detail.hidden = !on; e.currentTarget.setAttribute("aria-expanded", String(on)); } },
      h("span", { class: "market-name" }, label(item.label)),
      h("span", { class: "market-price" }, taka(item.price), h("small", {}, ` ${label(item.unit)} · ${month(item.observed)}`)),
      h("span", { class: `market-outlook tone-${o.tone}` }, h("span", { "aria-hidden": "true" }, o.sign), " ", o.text),
      o.range ? h("span", { class: "market-range" }, o.range) : null);
    return h("li", { class: "market-item" }, toggle, detail);
  }

  function body() {
    const t = c();
    if (loading && !data) return h("p", { class: "market-status", role: "status" }, t.loading);
    if (failed && !data) return h("div", { class: "market-status", role: "alert" }, h("p", {}, t.error),
      h("button", { class: "btn", type: "button", onclick: load }, t.retry));
    if (!data?.items?.length) return h("p", { class: "market-status" }, t.empty);
    const items = showAll ? data.items : data.items.slice(0, FIRST_BATCH);
    const note = data.note ? h("p", { class: "market-note" }, label(data.note)) : null;
    const more = data.items.length > FIRST_BATCH ? h("button", { class: "text-link market-more", type: "button",
      onclick: () => { showAll = !showAll; draw("market-more"); }, id: "market-more" }, showAll ? t.less : t.more) : null;
    const engine = data.engine.kind === "model" ? t.model(data.engine.name) : t.stat;
    const how = h("details", { class: "market-how" }, h("summary", {}, t.sure),
      h("p", {}, engine), h("p", {}, t.tested),
      h("p", {}, t.source(month(data.latest_observation, true)), " ",
        h("a", { href: data.source.url, target: "_blank", rel: "noopener noreferrer" }, t.sourceLink)));
    return [note, h("ul", { class: "market-list" }, items.map(row)), more, how];
  }

  function draw(focusId) {
    if (!root) return;
    const t = c();
    root.classList.toggle("open", open);
    const tab = h("button", { class: "market-tab", type: "button", "aria-expanded": String(open), "aria-controls": "market-panel",
      "aria-label": open ? t.close : t.open, onclick: () => setOpen(!open, true) }, trendIcon(), h("span", {}, t.tab));
    const panel = h("aside", { class: entering ? "market-panel entering" : "market-panel", id: "market-panel", "aria-labelledby": "market-title", hidden: !open },
      h("header", { class: "market-head" },
        h("h2", { id: "market-title", tabindex: "-1" }, t.title),
        h("button", { class: "market-close", type: "button", "aria-label": t.close, onclick: () => setOpen(false, true) }, "✕")),
      h("p", { class: "market-intro" }, t.intro), body());
    root.replaceChildren(tab, panel);
    entering = false;
    if (focusId) root.querySelector(`#${focusId}`)?.focus();
  }

  async function load() {
    if (loading) return;
    loading = true; failed = false; draw();
    try { data = await api("/api/market/prices"); }
    catch (e) {
      if (e.status === 404) { disabled = true; loading = false; root?.remove(); root = null; return; }  // turned off on this server
      failed = true;
    }
    loading = false; draw();
  }

  function setOpen(v, byUser = false) {
    entering = v && !open && byUser;
    open = v;
    if (byUser) remember(v);
    if (open && !data && !loading) load();
    draw(byUser ? (open ? "market-title" : null) : null);
    if (byUser && !open) root?.querySelector(".market-tab")?.focus();
  }

  const onKey = e => { if (e.key === "Escape" && open) setOpen(false, true); };

  return {
    mount() {
      if (root || disabled) return;
      root = h("div", { class: "market-drawer", "data-i18n-skip": "" });
      document.body.appendChild(root);
      document.addEventListener("keydown", onKey);
      setOpen(wasOpen());
    },
    unmount() {
      document.removeEventListener("keydown", onKey);
      root?.remove(); root = null;
    },
    redraw() { draw(); },
  };
}
