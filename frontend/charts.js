// Tiny dependency-free SVG charts with hover tooltips and a table view.
// Colors come from CSS tokens (--series-1/2, --band, --grid ...) so light/dark mode just works.
const NS = "http://www.w3.org/2000/svg";

function el(tag, attrs = {}, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}
function div(cls, text) {
  const d = document.createElement("div");
  if (cls) d.className = cls;
  if (text !== undefined) d.textContent = text;
  return d;
}

let tip;
function tooltip() {
  if (!tip) { tip = div("tooltip hidden"); document.body.appendChild(tip); }
  return tip;
}
function showTip(evt, title, rows) {
  const t = tooltip();
  t.replaceChildren();
  t.appendChild(div("tt-h", title));
  for (const [k, v] of rows) {
    const r = div("tt-row");
    const a = document.createElement("span"); a.textContent = k;
    const b = document.createElement("b"); b.textContent = v;
    r.append(a, b); t.appendChild(r);
  }
  t.classList.remove("hidden");
  const x = Math.min(evt.clientX + 14, window.innerWidth - t.offsetWidth - 8);
  const y = Math.min(evt.clientY + 14, window.innerHeight - t.offsetHeight - 8);
  t.style.left = x + "px"; t.style.top = y + "px";
}
// Bar corner radius from the active style (--chart-bar-r: 4 = soft corners, 99 = pill ends).
const barR = () => parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--chart-bar-r")) || 4;
function hideTip() { tooltip().classList.add("hidden"); }

function niceTicks(min, max, n = 5) {
  if (min === max) { max = min + 1; }
  const span = max - min;
  const step0 = Math.pow(10, Math.floor(Math.log10(span / n)));
  const err = (span / n) / step0;
  const step = step0 * (err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1);
  const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(+v.toFixed(6));
  return ticks;
}

function legend(items) {
  const l = div("legend");
  for (const it of items) {
    const s = document.createElement("span");
    const i = document.createElement("i");
    if (it.box) i.className = "box";
    i.style.background = it.color;
    if (it.dashed) { i.style.background = "none"; i.style.borderTop = `2px dashed ${it.color}`; i.style.height = "0"; }
    s.append(i, document.createTextNode(it.name));
    l.appendChild(s);
  }
  return l;
}

function tableView(headers, rows) {
  const d = document.createElement("details");
  const s = document.createElement("summary"); s.textContent = "View as table"; s.className = "small";
  d.appendChild(s);
  const wrap = div("scroll"); wrap.style.maxHeight = "220px";
  const t = document.createElement("table"); t.className = "t";
  const hr = document.createElement("tr");
  headers.forEach((h, i) => { const th = document.createElement("th"); th.textContent = h; if (i) th.className = "r"; hr.appendChild(th); });
  t.appendChild(hr);
  for (const r of rows) {
    const tr = document.createElement("tr");
    r.forEach((c, i) => { const td = document.createElement("td"); td.textContent = c; if (i) td.className = "r"; tr.appendChild(td); });
    t.appendChild(tr);
  }
  wrap.appendChild(t); d.appendChild(wrap);
  return d;
}

/**
 * Line chart with optional uncertainty band, threshold line and per-point events.
 * opts: {series:[{name,color,points:[{x,y}],dashed}], band:[{x,lo,hi}], threshold:{value,label}, yfmt, height, events:{x:[..]}}
 */
export function lineChart(opts) {
  const W = 760, H = opts.height || 260, m = { l: 62, r: 16, t: 10, b: 26 };
  const root = div("chart");
  const items = opts.series.map(s => ({ name: s.name, color: s.color, dashed: s.dashed }));
  if (opts.band) items.push({ name: opts.bandLabel || "80% range", color: "var(--band)", box: true });
  if (opts.threshold) items.push({ name: opts.threshold.label, color: "var(--serious)", dashed: true });
  if (opts.series.length > 1 || opts.band || opts.threshold) root.appendChild(legend(items));
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.ariaLabel || "line chart" });
  root.appendChild(svg);
  const xs = opts.series[0].points.map(p => p.x);
  const n = xs.length;
  let ys = opts.series.flatMap(s => s.points.map(p => p.y));
  if (opts.band) ys = ys.concat(opts.band.flatMap(b => [b.lo, b.hi]));
  if (opts.threshold) ys.push(opts.threshold.value);
  ys.push(0);
  const ticks = niceTicks(Math.min(...ys), Math.max(...ys));
  const y0 = ticks[0], y1 = ticks[ticks.length - 1];
  const X = i => m.l + (n <= 1 ? 0 : i * (W - m.l - m.r) / (n - 1));
  const Y = v => m.t + (H - m.t - m.b) * (1 - (v - y0) / (y1 - y0));
  const g = el("g", { class: "axis" }, svg);
  for (const t of ticks) {
    el("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), class: t === 0 ? "baseline" : "gridline" }, g);
    const tx = el("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, g);
    tx.textContent = opts.yfmt ? opts.yfmt(t, true) : t;
  }
  const step = Math.max(1, Math.round(n / 7));
  for (let i = 0; i < n; i += step) {
    const tx = el("text", { x: X(i), y: H - 6, "text-anchor": "middle" }, g);
    tx.textContent = opts.xfmt ? opts.xfmt(xs[i]) : xs[i];
  }
  if (opts.band) {
    const up = opts.band.map((b, i) => `${X(i)},${Y(b.hi)}`);
    const dn = opts.band.map((b, i) => `${X(i)},${Y(b.lo)}`).reverse();
    el("path", { d: `M${up.join("L")}L${dn.join("L")}Z`, fill: "var(--band)", class: "band" }, svg);
  }
  if (opts.threshold) {
    el("line", { x1: m.l, x2: W - m.r, y1: Y(opts.threshold.value), y2: Y(opts.threshold.value),
      stroke: "var(--serious)", "stroke-width": 1.5, "stroke-dasharray": "5 4" }, svg);
  }
  for (const s of opts.series) {
    const d = s.points.map((p, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(p.y).toFixed(1)}`).join("");
    el("path", { d, fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round",
      "stroke-linecap": "round", ...(s.dashed ? { "stroke-dasharray": "6 4" } : {}) }, svg);
  }
  // event markers (days with scheduled items)
  if (opts.events) {
    xs.forEach((x, i) => {
      if (opts.events[x] && opts.events[x].length) {
        el("circle", { cx: X(i), cy: Y(opts.series[0].points[i].y), r: 3.2, fill: "var(--surface-1)",
          stroke: opts.series[0].color, "stroke-width": 1.6 }, svg);
      }
    });
  }
  // hover layer: crosshair + tooltip
  const cross = el("line", { y1: m.t, y2: H - m.b, stroke: "var(--axis)", "stroke-width": 1, visibility: "hidden" }, svg);
  const dots = opts.series.map(s => el("circle", { r: 4.5, fill: s.color, stroke: "var(--surface-1)", "stroke-width": 2,
    visibility: "hidden" }, svg));
  const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, svg);
  hit.addEventListener("mousemove", evt => {
    const r = svg.getBoundingClientRect();
    const px = (evt.clientX - r.left) * W / r.width;
    const i = Math.max(0, Math.min(n - 1, Math.round((px - m.l) / ((W - m.l - m.r) / Math.max(1, n - 1)))));
    cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i)); cross.setAttribute("visibility", "visible");
    const rows = opts.series.map((s, k) => {
      dots[k].setAttribute("cx", X(i)); dots[k].setAttribute("cy", Y(s.points[i].y)); dots[k].setAttribute("visibility", "visible");
      return [s.name, opts.yfmt ? opts.yfmt(s.points[i].y) : s.points[i].y];
    });
    if (opts.band) rows.push([opts.bandLabel || "80% range", `${opts.yfmt(opts.band[i].lo)} – ${opts.yfmt(opts.band[i].hi)}`]);
    for (const ev of (opts.events && opts.events[xs[i]]) || []) rows.push(["•", ev]);
    showTip(evt, opts.xfmtLong ? opts.xfmtLong(xs[i]) : xs[i], rows);
  });
  hit.addEventListener("mouseleave", () => { cross.setAttribute("visibility", "hidden"); dots.forEach(d => d.setAttribute("visibility", "hidden")); hideTip(); });
  root.appendChild(tableView(["Date", ...opts.series.map(s => s.name)],
    xs.map((x, i) => [x, ...opts.series.map(s => opts.yfmt ? opts.yfmt(s.points[i].y) : s.points[i].y)])));
  return root;
}

/** Grouped vertical bars. opts: {categories, series:[{name,color,values}], yfmt, height} */
export function barChart(opts) {
  const W = 760, H = opts.height || 240, m = { l: 62, r: 10, t: 10, b: 26 };
  const root = div("chart");
  root.appendChild(legend(opts.series.map(s => ({ name: s.name, color: s.color, box: true }))));
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.ariaLabel || "bar chart" });
  root.appendChild(svg);
  const all = opts.series.flatMap(s => s.values).concat([0]);
  const ticks = niceTicks(Math.min(...all), Math.max(...all));
  const y0 = ticks[0], y1 = ticks[ticks.length - 1];
  const Y = v => m.t + (H - m.t - m.b) * (1 - (v - y0) / (y1 - y0));
  const g = el("g", { class: "axis" }, svg);
  for (const t of ticks) {
    el("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), class: t === 0 ? "baseline" : "gridline" }, g);
    const tx = el("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, g);
    tx.textContent = opts.yfmt ? opts.yfmt(t, true) : t;
  }
  const n = opts.categories.length, k = opts.series.length;
  const slot = (W - m.l - m.r) / n, gap = 2, bw = Math.max(3, (slot * 0.7 - gap * (k - 1)) / k);
  opts.categories.forEach((c, i) => {
    const x0 = m.l + i * slot + slot * 0.15;
    if (n <= 16 || i % 2 === 0) {
      const tx = el("text", { x: m.l + i * slot + slot / 2, y: H - 6, "text-anchor": "middle" }, g);
      tx.textContent = opts.xfmt ? opts.xfmt(c) : c;
    }
    opts.series.forEach((s, j) => {
      const v = s.values[i];
      const top = Y(Math.max(v, 0)), bot = Y(Math.min(v, 0));
      const h = Math.max(1, bot - top);
      const r = Math.min(barR(), bw / 2, h);
      const x = x0 + j * (bw + gap);
      // rounded data-end anchored to the baseline
      const d = v >= 0
        ? `M${x},${bot}V${top + r}Q${x},${top} ${x + r},${top}H${x + bw - r}Q${x + bw},${top} ${x + bw},${top + r}V${bot}Z`
        : `M${x},${top}V${bot - r}Q${x},${bot} ${x + r},${bot}H${x + bw - r}Q${x + bw},${bot} ${x + bw},${bot - r}V${top}Z`;
      el("path", { d, fill: s.color }, svg);
    });
    const hit = el("rect", { x: m.l + i * slot, y: m.t, width: slot, height: H - m.t - m.b, fill: "transparent" }, svg);
    hit.addEventListener("mousemove", evt => showTip(evt, opts.xfmtLong ? opts.xfmtLong(c) : c,
      opts.series.map(s => [s.name, opts.yfmt ? opts.yfmt(s.values[i]) : s.values[i]]).concat(opts.extraRows ? opts.extraRows(i) : [])));
    hit.addEventListener("mouseleave", hideTip);
  });
  root.appendChild(tableView(["", ...opts.series.map(s => s.name)],
    opts.categories.map((c, i) => [c, ...opts.series.map(s => opts.yfmt ? opts.yfmt(s.values[i]) : s.values[i])])));
  return root;
}

/** Horizontal bars, single series (magnitude), direct value labels. items: [{label, value, sub}] */
export function hbarChart(items, { fmt, color = "var(--series-1)" } = {}) {
  const root = div("chart");
  const max = Math.max(1, ...items.map(i => i.value));
  const W = 760, rowH = 30, H = items.length * rowH + 4, lw = 170, vw = 150;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "horizontal bar chart" });
  items.forEach((it, i) => {
    const y = i * rowH + 6;
    const t = el("text", { x: 0, y: y + 13, class: "lbl" }, svg); t.textContent = it.label;
    const w = Math.max(2, (W - lw - vw) * it.value / max);
    const r = Math.min(barR(), w / 2, 8);
    el("path", { d: `M${lw},${y}H${lw + w - r}Q${lw + w},${y} ${lw + w},${y + r}V${y + 16 - r}Q${lw + w},${y + 16} ${lw + w - r},${y + 16}H${lw}Z`, fill: color }, svg);
    const v = el("text", { x: lw + w + 8, y: y + 13, class: "lbl" }, svg); v.textContent = fmt ? fmt(it.value) : it.value;
    const hit = el("rect", { x: 0, y: y - 4, width: W, height: rowH, fill: "transparent" }, svg);
    hit.addEventListener("mousemove", evt => showTip(evt, it.label, [["Amount", fmt ? fmt(it.value) : it.value], ...(it.sub || [])]));
    hit.addEventListener("mouseleave", hideTip);
  });
  root.appendChild(svg);
  return root;
}
