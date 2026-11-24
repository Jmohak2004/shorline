// Shorline dashboard. No dependencies; every chart is hand-built SVG.
// All untrusted strings (addresses, labels) are inserted with textContent.

import { checkT, texToT1, shardOf } from "./addr.js";

const DATA = "data/";
const SVGNS = "http://www.w3.org/2000/svg";
const EXPLORER = "https://mainnet.zcashexplorer.app";

const FATES = [
  { id: "exposed", key: "exposed_zat", name: "Exposed", color: "--exp", on: "--on-exp", icon: "critical",
    desc: "Transparent ZEC whose public key or redeem script is already on-chain. A discrete-log-breaking adversary could forge spends of it." },
  { id: "hash", key: "hash_protected_zat", name: "Hash-protected", color: "--hash", on: "--on-hash", icon: "warning",
    desc: "At t1 addresses never spent from. Shor's algorithm can't reach it until the owner spends. Recoverable after Q-Day only if a ZIP 2007 circuit ships." },
  { id: "unknown", key: "unknown_zat", name: "Unknown P2SH", color: "--unk", on: "--on-unk", icon: "unknown",
    desc: "At t3 addresses whose redeem script has never been revealed. It cannot be classified from public data." },
  { id: "stranded", key: "stranded_zat", name: "Stranded", color: "--str", on: "--on-str", icon: "serious",
    desc: "In the Sprout, Sapling and Orchard pools. Inaccessible once those protocols are disabled, unless migrated to Ironwood first (ZIP 2005)." },
  { id: "lockbox", key: "lockbox_zat", name: "Lockbox", color: "--lock", on: "--on-lock", icon: "lock",
    desc: "The NU6 deferred dev-fund lockbox. It is a consensus-held balance that only a network upgrade can release, so there is no key to steal." },
  { id: "recoverable", key: "recoverable_zat", name: "Recoverable", color: "--rec", on: "--on-rec", icon: "good",
    desc: "In Ironwood notes, which are built to be recoverable through a future post-quantum Recovery Protocol (ZIP 2005)." },
];

const CAT_INFO = [
  { id: "p2pkh_hidden", label: "P2PKH, key never revealed", zip: "Recoverable in principle (needs ZIP 2007 circuit)", fate: "hash" },
  { id: "p2pkh_exposed", label: "P2PKH, key revealed", zip: "Not recoverable: key exposed", fate: "exposed" },
  { id: "p2sh_unseen", label: "P2SH, script never revealed", zip: "Unknown from public data", fate: "unknown" },
  { id: "p2sh_seen", label: "P2SH, script revealed", zip: "Not recoverable: script seen", fate: "exposed" },
  { id: "p2pk", label: "P2PK (key in output)", zip: "Out of scope: key in output", fate: "exposed" },
  { id: "bare_multisig", label: "Bare multisig", zip: "Out of scope: keys in output", fate: "exposed" },
  { id: "nulldata", label: "OP_RETURN with value", zip: "Unspendable", fate: null },
  { id: "nonstandard", label: "Non-standard scripts", zip: "Other", fate: null },
];

const ICONS = {
  critical: '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
  warning: '<path d="M12 3.5L2.8 19.5h18.4L12 3.5z"/><path d="M12 10v4.2M12 17h.01"/>',
  serious: '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5M12 16.5h.01"/>',
  good: '<circle cx="12" cy="12" r="9"/><path d="M8 12.3l2.7 2.7L16.2 9.4"/>',
  unknown: '<circle cx="12" cy="12" r="9"/><path d="M9.6 9.3a2.5 2.5 0 1 1 3.6 2.2c-.8.4-1.2 1-1.2 1.8v.4M12 16.8h.01"/>',
  lock: '<rect x="5" y="10.5" width="14" height="9.5" rx="2"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5"/>',
};

// ---------------------------------------------------------------- helpers
const $ = (s) => document.querySelector(s);
const fmtInt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const fmt2 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtMonth = new Intl.DateTimeFormat("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
const fmtDay = new Intl.DateTimeFormat("en-US", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

const toZec = (zat) => zat / 1e8;
function compact(v) {
  const a = Math.abs(v);
  if (a >= 999.5e3) return (v / 1e6).toFixed(a >= 9.995e6 ? 1 : 2) + "M";
  if (a >= 999.95) return (v / 1e3).toFixed(a >= 99.95e3 ? 0 : 1) + "K";
  if (a >= 100) return v.toFixed(0);
  return v.toFixed(a >= 10 ? 1 : 2);
}
const zecCompact = (zat) => compact(toZec(zat));
const zecFull = (zat) => fmtInt.format(Math.round(toZec(zat)));
const zecExact = (zat) => {
  const s = String(zat).padStart(9, "0");
  return fmtInt.format(Number(s.slice(0, -8))) + "." + s.slice(-8);
};
const pct = (part, whole) => (whole > 0 ? (100 * part) / whole : 0);
const pctStr = (p) => (p >= 10 ? p.toFixed(1) : p >= 1 ? p.toFixed(1) : p.toFixed(2)) + "%";
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function h(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === "class") n.className = v;
    else if (k === "style") n.style.cssText = v;
    else n.setAttribute(k, v);
  }
  for (const c of children) if (c != null) n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return n;
}
function s(tag, attrs = {}, parent) {
  const n = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v);
  if (parent) parent.append(n);
  return n;
}
function icon(name) {
  const svg = document.createElementNS(SVGNS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icon");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = ICONS[name]; // static, trusted markup
  return svg;
}
const swatch = (colorVar) => h("span", { class: "swatch", style: `background:var(${colorVar})` });
const lineKey = (colorVar) => h("span", { class: "line-key", style: `background:var(${colorVar})` });

function table(columns, rows) {
  const t = h("table", { class: "data" });
  const thead = h("thead");
  const tr = h("tr");
  for (const c of columns) tr.append(h("th", { class: c.num ? "num" : null, scope: "col" }, c.label));
  thead.append(tr);
  t.append(thead);
  const tb = h("tbody");
  for (const r of rows) {
    const row = h("tr");
    columns.forEach((c, i) => {
      const v = r[i];
      row.append(v instanceof Node ? h("td", { class: c.cls || (c.num ? "num" : null) }, v) : h("td", { class: c.cls || (c.num ? "num" : null) }, v ?? ""));
    });
    tb.append(row);
  }
  t.append(tb);
  return t;
}

// Height -> unix time, interpolated from the time series.
let HT = [];
function timeAt(height) {
  if (!HT.length) return 0;
  let lo = 0, hi = HT.length - 1;
  if (height <= HT[0][0]) return HT[0][1];
  if (height >= HT[hi][0]) return HT[hi][1] + (height - HT[hi][0]) * 75;
  while (hi - lo > 1) {
    const m = (lo + hi) >> 1;
    if (HT[m][0] <= height) lo = m; else hi = m;
  }
  const [h0, t0] = HT[lo], [h1, t1] = HT[hi];
  return t0 + ((height - h0) / (h1 - h0)) * (t1 - t0);
}
const dateOfHeight = (height) => fmtMonth.format(new Date(timeAt(height) * 1000));

// ---------------------------------------------------------------- tooltip
const tip = $("#tooltip");
function showTip(clientX, clientY, title, rows) {
  tip.replaceChildren();
  if (title) tip.append(h("div", { class: "tt-title" }, title));
  for (const r of rows) {
    tip.append(h("div", { class: "tt-row" }, r.color ? h("span", { class: "k", style: `background:var(${r.color})` }) : null, h("span", { class: "v" }, r.value), h("span", { class: "n" }, r.name)));
  }
  tip.classList.add("show");
  const pad = 14;
  const w = tip.offsetWidth, ht = tip.offsetHeight;
  let x = clientX + pad, y = clientY + pad;
  if (x + w > window.innerWidth - 8) x = clientX - w - pad;
  if (y + ht > window.innerHeight - 8) y = clientY - ht - pad;
  tip.style.left = Math.max(8, x) + "px";
  tip.style.top = Math.max(8, y) + "px";
}
const hideTip = () => tip.classList.remove("show");
function anchorTip(el, title, rows) {
  const r = el.getBoundingClientRect();
  showTip(r.left + r.width / 2, r.top, title, rows);
}

// ---------------------------------------------------------------- charts
function niceTicks(max, count = 4) {
  if (max <= 0) return [0];
  const raw = max / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((st) => st >= raw);
  const ticks = [];
  for (let v = 0; v <= max + step * 0.001; v += step) ticks.push(v);
  if (ticks[ticks.length - 1] < max) ticks.push(ticks[ticks.length - 1] + step);
  return ticks;
}

function lineChart(container, { series, xs, annotations = [], height = 340 }) {
  container.replaceChildren();
  const W = Math.max(300, container.clientWidth);
  const narrow = W < 560;
  const m = { l: 48, r: narrow ? 16 : 132, t: 26, b: 30 };
  const H = height;
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img", "aria-label": "Line chart of transparent ZEC by quantum exposure over time" }, container);
  const x0 = xs[0], x1 = xs[xs.length - 1];
  const maxY = Math.max(...series.flatMap((se) => se.values));
  const ticks = niceTicks(maxY, 4);
  const yMax = ticks[ticks.length - 1];
  const X = (t) => m.l + ((t - x0) / (x1 - x0)) * (W - m.l - m.r);
  const Y = (v) => H - m.b - (v / yMax) * (H - m.t - m.b);
  for (const tv of ticks) {
    s("line", { class: tv === 0 ? "baseline" : "gridline", x1: m.l, x2: W - m.r, y1: Y(tv), y2: Y(tv) }, svg);
    const tx = s("text", { x: m.l - 8, y: Y(tv) + 4, "text-anchor": "end" }, svg);
    tx.textContent = tv === 0 ? "0" : compact(tv);
  }
  const y0 = new Date(x0 * 1000).getUTCFullYear(), y1 = new Date(x1 * 1000).getUTCFullYear();
  const yearStep = narrow ? 2 : 1;
  for (let y = y0 + 1; y <= y1; y += yearStep) {
    const t = Date.UTC(y, 0, 1) / 1000;
    if (t < x0 || t > x1) continue;
    const tx = s("text", { x: X(t), y: H - m.b + 18, "text-anchor": "middle" }, svg);
    tx.textContent = String(y);
  }
  for (const a of annotations) {
    if (a.t < x0 || a.t > x1) continue;
    const g = s("g", { class: "annot" }, svg);
    s("line", { x1: X(a.t), x2: X(a.t), y1: m.t - 6, y2: H - m.b }, g);
    if (!narrow) {
      const tx = s("text", { x: X(a.t) + 4, y: m.t - 10 }, g);
      tx.textContent = a.label;
    }
  }
  for (const se of series) {
    let d = "";
    se.values.forEach((v, i) => { d += (i ? "L" : "M") + X(xs[i]).toFixed(1) + " " + Y(v).toFixed(1); });
    s("path", { class: "series", d, stroke: `var(${se.color})` }, svg);
  }
  // End markers and direct labels (with leader lines when labels must move apart).
  const last = xs.length - 1;
  const ends = series.map((se) => ({ se, y: Y(se.values[last]), ly: Y(se.values[last]) }));
  for (const e of ends) {
    s("circle", { cx: X(xs[last]), cy: e.y, r: 4, fill: `var(${e.se.color})`, stroke: "var(--surface)", "stroke-width": 2 }, svg);
  }
  if (!narrow) {
    ends.sort((a, b) => a.y - b.y);
    const gap = 30;
    for (let i = 1; i < ends.length; i++) if (ends[i].ly - ends[i - 1].ly < gap) ends[i].ly = ends[i - 1].ly + gap;
    const overflow = ends.length ? ends[ends.length - 1].ly - (H - m.b) : 0;
    if (overflow > 0) for (const e of ends) e.ly -= overflow;
    for (const e of ends) {
      const lx = X(xs[last]) + 12;
      if (Math.abs(e.ly - e.y) > 2) s("line", { class: "leader", x1: X(xs[last]) + 5, y1: e.y, x2: lx - 2, y2: e.ly }, svg);
      const t1 = s("text", { class: "endlabel", x: lx, y: e.ly - 2 }, svg);
      t1.textContent = e.se.name;
      const t2 = s("text", { class: "endvalue", x: lx, y: e.ly + 13 }, svg);
      t2.textContent = compact(e.se.values[last]) + " ZEC";
    }
  }
  // Crosshair layer: snaps to the nearest sample; keyboard arrows move it.
  const cross = s("line", { class: "crosshair", y1: m.t, y2: H - m.b, visibility: "hidden" }, svg);
  const dots = series.map((se) => s("circle", { r: 4, fill: `var(${se.color})`, stroke: "var(--surface)", "stroke-width": 2, visibility: "hidden" }, svg));
  const hit = s("rect", { class: "hit", x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, tabindex: 0, "aria-label": "Chart readout. Use left and right arrow keys to move through time." }, svg);
  let idx = last;
  const showAt = (i, cx, cy) => {
    idx = Math.max(0, Math.min(last, i));
    const xx = X(xs[idx]);
    cross.setAttribute("x1", xx); cross.setAttribute("x2", xx); cross.setAttribute("visibility", "visible");
    series.forEach((se, k) => { dots[k].setAttribute("cx", xx); dots[k].setAttribute("cy", Y(se.values[idx])); dots[k].setAttribute("visibility", "visible"); });
    const rows = series.map((se) => ({ color: se.color, value: fmtInt.format(Math.round(se.values[idx])) + " ZEC", name: se.name }));
    const title = fmtDay.format(new Date(xs[idx] * 1000)) + (series.heights ? ` · block ${fmtInt.format(series.heights[idx])}` : "");
    if (cx == null) { const r = svg.getBoundingClientRect(); cx = r.left + (xx / W) * r.width; cy = r.top + m.t; }
    showTip(cx, cy, title, rows);
  };
  const nearest = (evt) => {
    const r = svg.getBoundingClientRect();
    const t = x0 + (((evt.clientX - r.left) / r.width) * W - m.l) / (W - m.l - m.r) * (x1 - x0);
    let lo = 0, hi = last;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (xs[mid] <= t) lo = mid; else hi = mid; }
    return t - xs[lo] < xs[hi] - t ? lo : hi;
  };
  const hideAll = () => { cross.setAttribute("visibility", "hidden"); dots.forEach((d) => d.setAttribute("visibility", "hidden")); hideTip(); };
  hit.addEventListener("pointermove", (e) => showAt(nearest(e), e.clientX, e.clientY));
  hit.addEventListener("pointerleave", hideAll);
  hit.addEventListener("focus", () => showAt(idx));
  hit.addEventListener("blur", hideAll);
  hit.addEventListener("keydown", (e) => {
    const step = e.shiftKey ? 50 : 5;
    if (e.key === "ArrowLeft") { e.preventDefault(); showAt(idx - step); }
    if (e.key === "ArrowRight") { e.preventDefault(); showAt(idx + step); }
  });
}

function columnChart(container, { cats, series, height = 250, label = "Column chart", fmt = (v) => compact(v) + " ZEC" }) {
  container.replaceChildren();
  const W = Math.max(280, container.clientWidth);
  const m = { l: 44, r: 8, t: 22, b: 28 };
  const H = height;
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img", "aria-label": label }, container);
  const maxV = Math.max(1e-9, ...series.flatMap((se) => se.values));
  const ticks = niceTicks(maxV, 4);
  const yMax = ticks[ticks.length - 1];
  const Y = (v) => H - m.b - (v / yMax) * (H - m.t - m.b);
  for (const tv of ticks) {
    s("line", { class: tv === 0 ? "baseline" : "gridline", x1: m.l, x2: W - m.r, y1: Y(tv), y2: Y(tv) }, svg);
    const tx = s("text", { x: m.l - 8, y: Y(tv) + 4, "text-anchor": "end" }, svg);
    tx.textContent = tv === 0 ? "0" : compact(tv);
  }
  const band = (W - m.l - m.r) / cats.length;
  const barW = Math.min(24, (band * 0.62 - 2 * (series.length - 1)) / series.length);
  const groupW = series.length * barW + 2 * (series.length - 1);
  // Label only the single largest value (selective direct labelling).
  let best = { v: -1 };
  series.forEach((se, k) => se.values.forEach((v, i) => { if (v > best.v) best = { v, i, k }; }));
  cats.forEach((c, i) => {
    const cx = m.l + band * i + band / 2;
    const tx = s("text", { x: cx, y: H - m.b + 18, "text-anchor": "middle" }, svg);
    tx.textContent = c;
    series.forEach((se, k) => {
      const v = se.values[i];
      const x = cx - groupW / 2 + k * (barW + 2);
      const y = Y(v), base = Y(0);
      const hgt = base - y;
      if (hgt <= 0.5) return;
      const r = Math.min(4, hgt, barW / 2);
      const d = `M${x} ${base}V${y + r}Q${x} ${y} ${x + r} ${y}H${x + barW - r}Q${x + barW} ${y} ${x + barW} ${y + r}V${base}Z`;
      const p = s("path", { class: "bar", d, fill: `var(${se.color})`, tabindex: 0, "aria-label": `${c}, ${se.name}: ${fmt(v)}` }, svg);
      const rows = [{ color: se.color, value: fmt(v), name: se.name }];
      p.addEventListener("pointermove", (e) => showTip(e.clientX, e.clientY, c, rows));
      p.addEventListener("pointerleave", hideTip);
      p.addEventListener("focus", () => anchorTip(p, c, rows));
      p.addEventListener("blur", hideTip);
      if (best.i === i && best.k === k) {
        const lt = s("text", { x: x + barW / 2, y: y - 6, "text-anchor": "middle", class: "endvalue" }, svg);
        lt.textContent = fmt(v);
      }
    });
  });
}

// ---------------------------------------------------------------- sections
function renderHero(S, Y, SALT) {
  const R = S.risk;
  const total = R.total_zat;
  $("#hero-number").replaceChildren(document.createTextNode(zecCompact(R.exposed_zat)), h("span", { class: "unit" }, "ZEC"));
  const cap = $("#hero-caption");
  const indirect = (Y && Y.revealed_zat ? Y.revealed_zat : 0) + (SALT && SALT.matched_zat ? SALT.matched_zat : 0);
  cap.replaceChildren(
    h("strong", {}, `${pctStr(pct(R.exposed_zat, total))} of all ZEC`),
    ` (${zecFull(R.exposed_zat)} ZEC) sits at transparent addresses whose public keys are already on the blockchain. An adversary who can compute discrete logarithms, such as a large quantum computer running Shor's algorithm, could forge spends of it.`,
    indirect ? ` Another ${zecFull(indirect)} ZEC looks safe on-chain, but its keys leaked indirectly through the Ycash fork or reused multisig templates.` : null
  );
  const tiles = $("#tiles");
  tiles.replaceChildren();
  for (const id of ["stranded", "hash", "unknown", "recoverable"]) {
    const f = FATES.find((x) => x.id === id);
    const v = R[f.key];
    tiles.append(
      h("div", { class: "tile" },
        h("div", { class: "label" }, swatch(f.color), icon(f.icon), f.name),
        h("div", { class: "value" }, zecCompact(v), h("span", { class: "unit" }, "ZEC")),
        h("div", { class: "share" }, `${pctStr(pct(v, total))} of supply`),
        h("p", {}, f.desc))
    );
  }
  const when = fmtDay.format(new Date(S.chain.time * 1000));
  $("#asof").textContent = `As of block ${fmtInt.format(S.chain.height)} (${when}). Total supply ${zecFull(total)} ZEC.`;
  $("#foot-data").textContent = `Data: block ${fmtInt.format(S.chain.height)} · ${S.tool}`;
}

function renderFate(S) {
  const R = S.risk;
  const total = R.total_zat;
  $("#fate-total").textContent = `${zecFull(total)} ZEC total`;
  const bar = $("#segbar");
  bar.replaceChildren();
  const parts = FATES.map((f) => ({ f, v: R[f.key] || 0 })).filter((p) => p.v > 0);
  for (const { f, v } of parts) {
    const share = pct(v, total);
    const seg = h("div", {
      class: "seg", tabindex: 0, role: "img",
      "aria-label": `${f.name}: ${zecFull(v)} ZEC, ${pctStr(share)} of supply`,
      style: `flex:${v} 1 0px;background:var(${f.color});color:var(${f.on})`,
    });
    seg.dataset.label = pctStr(share);
    const rows = [{ color: f.color, value: `${zecFull(v)} ZEC`, name: `${f.name} · ${pctStr(share)}` }];
    seg.addEventListener("pointermove", (e) => showTip(e.clientX, e.clientY, "Share of all ZEC", rows));
    seg.addEventListener("pointerleave", hideTip);
    seg.addEventListener("focus", () => anchorTip(seg, "Share of all ZEC", rows));
    seg.addEventListener("blur", hideTip);
    bar.append(seg);
  }
  requestAnimationFrame(() => {
    const ctx = document.createElement("canvas").getContext("2d");
    ctx.font = "650 12.8px " + css("--sans");
    for (const seg of bar.children) {
      const need = ctx.measureText(seg.dataset.label).width + 16;
      seg.textContent = seg.clientWidth >= need ? seg.dataset.label : "";
    }
  });
  const legend = $("#fate-legend");
  legend.replaceChildren();
  for (const { f } of parts) legend.append(h("span", { class: "item" }, swatch(f.color), icon(f.icon), f.name));
  const list = $("#fate-list");
  list.replaceChildren();
  for (const { f, v } of parts) {
    list.append(h("div", { class: "fate" },
      h("h4", {}, swatch(f.color), icon(f.icon), f.name),
      h("div", { class: "amt small" }, `${zecFull(v)} ZEC · ${pctStr(pct(v, total))}`),
      h("p", {}, f.desc)));
  }
  const rows = FATES.map((f) => [f.name, zecExact(R[f.key] || 0), pctStr(pct(R[f.key] || 0, total)), ["exposed", "hash", "unknown"].includes(f.id) ? "Shorline UTXO replay" : "Zebra valuePools"]);
  rows.push(["Unspendable / other transparent", zecExact(R.unspendable_zat), pctStr(pct(R.unspendable_zat, total)), "Shorline UTXO replay"]);
  $("#fate-table").replaceChildren(table([{ label: "Fate" }, { label: "ZEC", num: true }, { label: "Share", num: true }, { label: "Source" }], rows));
}

function renderVerify(S) {
  const c = S.cross_check;
  const badge = $("#verify-badge");
  const led = $("#verify-ledger");
  led.replaceChildren();
  if (c) {
    badge.replaceChildren(h("span", { class: "badge " + (c.match ? "ok" : "bad") }, icon(c.match ? "good" : "critical"),
      c.match ? `Exact match at block ${fmtInt.format(c.height)}` : `Mismatch of ${fmtInt.format(c.difference_zat)} zatoshis`));
    led.append(
      h("tr", {}, h("td", {}, `Zebra transparent pool (${c.node_build || "Zebra"})`), h("td", {}, zecExact(c.zebra_transparent_zat))),
      h("tr", {}, h("td", {}, "Shorline reconstructed UTXO set"), h("td", {}, zecExact(c.shorline_transparent_zat))),
      h("tr", {}, h("td", {}, "Difference (zatoshis)"), h("td", {}, String(c.difference_zat))));
  } else {
    badge.replaceChildren(h("span", { class: "badge" }, "Cross-check unavailable for this snapshot"));
  }
  const sc = S.scan;
  const st = $("#scan-stats");
  st.replaceChildren();
  for (const [v, l] of [[sc.blocks, "blocks replayed"], [sc.transactions, "transactions"], [sc.inputs, "transparent inputs"], [sc.outputs, "transparent outputs"], [sc.utxos, "live UTXOs"], [sc.missing_prevouts, "unmatched inputs"]]) {
    st.append(h("div", {}, h("b", {}, fmtInt.format(v)), h("span", {}, l)));
  }
}

const HISTORY_SERIES = [
  { id: "exposed", name: "Exposed", color: "--exp", cols: ["p2pkh_exposed", "p2sh_seen", "p2pk", "bare_multisig"] },
  { id: "hash", name: "Hash-protected", color: "--hash", cols: ["p2pkh_hidden"] },
  { id: "unknown", name: "Unknown P2SH", color: "--unk", cols: ["p2sh_unseen"] },
];

function renderHistory(T, S) {
  const ci = Object.fromEntries(T.columns.map((c, i) => [c, i]));
  const rows = T.rows.filter((r) => r[ci.time] > 0);
  const xs = rows.map((r) => r[ci.time]);
  const series = HISTORY_SERIES.map((se) => ({ ...se, values: rows.map((r) => se.cols.reduce((a, c) => a + r[ci[c]], 0) / 1e8) }));
  series.heights = rows.map((r) => r[ci.height]);
  const annotations = [
    { h: 419200, label: "Sapling" },
    { h: 1046400, label: "Canopy" },
    { h: 1687104, label: "NU5 · Orchard" },
    { h: 3428143, label: "Ironwood" },
  ].map((a) => ({ ...a, t: timeAt(a.h) }));
  // Largest rise in exposure over any 10-sample (10,000-block) window that came from reveals
  // (hash-protected falling at the same time), for the callout.
  let flip = null;
  for (let i = 10; i < rows.length; i++) {
    const dE = series[0].values[i] - series[0].values[i - 10];
    const dH = series[1].values[i - 10] - series[1].values[i];
    const moved = Math.min(dE, dH);
    if (!flip || moved > flip.moved) flip = { moved, i0: i - 10, i1: i };
  }
  if (flip && flip.moved > 0) {
    state.flip = { zat: flip.moved * 1e8, from: fmtDay.format(new Date(xs[flip.i0] * 1000)), to: fmtDay.format(new Date(xs[flip.i1] * 1000)) };
  }
  const leg = $("#history-legend");
  leg.replaceChildren(...series.map((se) => h("span", { class: "item" }, lineKey(se.color), se.name)));
  const draw = () => lineChart($("#history-chart"), { series, xs, annotations });
  draw();
  onResize(draw);
  // Table view: one row per year-end sample.
  const byYear = new Map();
  rows.forEach((r, i) => byYear.set(new Date(r[ci.time] * 1000).getUTCFullYear(), i));
  const trows = [...byYear.entries()].map(([y, i]) => [String(y), fmtInt.format(series.heights[i]), ...series.map((se) => fmtInt.format(Math.round(se.values[i])))]);
  $("#history-table").replaceChildren(table([{ label: "Year (last sample)" }, { label: "Block", num: true }, ...series.map((se) => ({ label: se.name + " (ZEC)", num: true }))], trows));
}

function renderAge(S) {
  const years = S.exposed_by_reveal_year;
  const cats = years.map((y) => String(y.year));
  const vals = years.map((y) => y.zat / 1e8);
  const drawY = () => columnChart($("#years-chart"), { cats, series: [{ name: "Exposed ZEC still at address", color: "--exp", values: vals }], label: "Exposed ZEC by year the key was revealed" });
  drawY();
  onResize(drawY);
  $("#years-table").replaceChildren(table([{ label: "Key revealed in" }, { label: "Exposed ZEC still there", num: true }], years.map((y) => [String(y.year), zecFull(y.zat)])));

  const dz = S.dormancy;
  const dcats = dz.map((d) => d.bucket.replace("y", " yr").replace("6 yr+", "6+ yr"));
  const dser = [
    { name: "Exposed", color: "--exp", values: dz.map((d) => d.exposed_zat / 1e8) },
    { name: "Hash-protected", color: "--hash", values: dz.map((d) => d.hidden_zat / 1e8) },
  ];
  $("#dormancy-legend").replaceChildren(...dser.map((se) => h("span", { class: "item" }, swatch(se.color), se.name)));
  const drawD = () => columnChart($("#dormancy-chart"), { cats: dcats, series: dser, height: 240, label: "Transparent ZEC by time since last activity" });
  drawD();
  onResize(drawD);
  $("#dormancy-table").replaceChildren(table([{ label: "Since last activity" }, { label: "Exposed ZEC", num: true }, { label: "Hash-protected ZEC", num: true }], dz.map((d, i) => [dcats[i], zecFull(d.exposed_zat), zecFull(d.hidden_zat)])));
}

function renderReuse(S) {
  const u = S.reuse;
  const box = $("#reuse-tiles");
  box.replaceChildren();
  const items = [
    [u.sent_to_exposed_last_30d ? zecCompact(u.sent_to_exposed_last_30d.zat) + " ZEC" : "n/a", "of payment volume in the last 30 days went to addresses whose key was already public. Coins cycling through reused hot wallets count on every pass."],
    [fmtInt.format(u.exposed_addresses_with_balance_that_received_after_reveal), "funded addresses kept receiving after their key went public"],
    [state.flip ? `${zecCompact(state.flip.zat)} ZEC` : "n/a", state.flip ? `flipped from hash-protected to exposed between ${state.flip.from} and ${state.flip.to}, the largest such shift on record. Large holders spent from never-spent addresses and left the rest behind.` : ""],
  ];
  for (const [v, l] of items) box.append(h("div", { class: "tile" }, h("div", { class: "value" }, v), h("p", {}, l)));
}

function renderZip2007(S, P) {
  const cats = S.transparent.categories;
  const ttotal = S.transparent.total_zat;
  const rows = cats.map((c, i) => [CAT_INFO[i].label, CAT_INFO[i].zip, zecFull(c.zat), pctStr(pct(c.zat, ttotal)), fmtInt.format(c.addresses), fmtInt.format(c.utxos)]);
  $("#zip2007-table").replaceChildren(table([{ label: "Category" }, { label: "ZIP 2007 status" }, { label: "ZEC", num: true }, { label: "Share", num: true }, { label: "Funded addrs", num: true }, { label: "UTXOs", num: true }], rows));
  const ps = S.p2sh_survey;
  if (ps) {
    const label = (t) => {
      let m = /^multisig_(\d+)_of_(\d+)$/.exec(t);
      if (m) return `${m[1]}-of-${m[2]} multisig`;
      m = /^salted_multisig_(\d+)_of_(\d+)$/.exec(t);
      if (m) return `Salted ${m[1]}-of-${m[2]} multisig (one key set, many addresses)`;
      return {
        p2pkh_wrapped: "P2SH-wrapped P2PKH",
        p2pk_wrapped: "P2SH-wrapped P2PK",
        data_envelope: "Data envelope (key + CHECKSIGVERIFY + DROPs)",
        salted_single_key: "Salted single key",
        other: "Other (HTLCs, timelocks, exotic)",
      }[t] || t;
    };
    const small = (z) => (z >= 1e8 ? zecFull(z) : z >= 1e6 ? fmt2.format(toZec(z)) : toZec(z).toFixed(4));
    const r = [...ps.by_redeem_type].sort((a, b) => b.zat - a.zat).map((x) => [label(x.type), fmtInt.format(x.addresses), small(x.zat)]);
    $("#p2sh-table").replaceChildren(table([{ label: "Redeem script" }, { label: "Addresses", num: true }, { label: "ZEC", num: true }], r));
    const w = ps.by_redeem_type.filter((x) => x.type === "p2pkh_wrapped" || x.type === "p2pk_wrapped");
    const wa = w.reduce((a, x) => a + x.addresses, 0), wz = w.reduce((a, x) => a + x.zat, 0);
    $("#p2sh-note").textContent = `${fmtInt.format(ps.classified)} of ${fmtInt.format(ps.addresses_with_balance)} funded, revealed t3 addresses were classified from their first spend. ` +
      (wa === 0 ? "No funded address uses a P2SH-wrapped P2PKH or P2PK script." : `On #1302's question: P2SH-wrapped P2PKH and P2PK do occur, but only at ${wa} funded addresses holding ${fmt2.format(toZec(wz))} ZEC, which is negligible.`);
  }
}

function renderSalted(SALT) {
  if (!SALT || !SALT.templates || !SALT.templates.length) return;
  const t = SALT.templates[0];
  const box = $("#salted");
  box.hidden = false;
  box.replaceChildren(
    h("h3", {}, "One key set, many addresses: the salted-multisig sweep"),
    h("p", { class: "sub small" },
      `${fmtInt.format(t.revealed_addresses)} revealed addresses holding ${zecFull(t.revealed_zat)} ZEC share a single 2-of-3 key set. ` +
      `The only difference between them is a random ${t.redeem.salt_bytes}-byte salt in the script: `),
    h("pre", {}, "OP_2 <k1> <k2> <k3> OP_3 OP_CHECKMULTISIGVERIFY <salt> OP_DROP OP_DEPTH OP_0 OP_EQUAL"),
    h("p", { class: "sub small" },
      `Because those keys are public, any never-spent address in the same family is exposed too: an adversary only has to enumerate the salt. ` +
      `Shorline did exactly that, hashing all ${fmtInt.format(t.salts_searched)} salts in ${Math.round(t.seconds)} s and matching them against all ${fmtInt.format(SALT.unseen_p2sh_funded)} funded "unknown" P2SH addresses. ` +
      `It rediscovered ${t.rediscovered_revealed} of ${t.revealed_addresses} revealed addresses as a self-check, and found ${fmtInt.format(SALT.matched_addresses)} never-spent addresses (${fmt2.format(toZec(SALT.matched_zat))} ZEC) that are exposed in practice. ` +
      `ZIP 2007 notes that unseen P2SH "can't be definitively classified as recoverable based on public information". For templated custody, they can be classified as exposed.`));
}

function renderTop(TOP) {
  const kinds = { p2pkh_exposed: "t1, key revealed", p2sh_seen: "t3, script revealed", p2pk: "P2PK", bare_multisig: "Bare multisig" };
  const all = Object.keys(kinds).flatMap((k) => (TOP[k] || []).map((e) => ({ ...e, kind: kinds[k] })));
  all.sort((a, b) => b.zat - a.zat);
  const rows = all.slice(0, 25).map((e, i) => {
    const isAddr = e.address.startsWith("t");
    const a = isAddr ? h("a", { href: `${EXPLORER}/address/${encodeURIComponent(e.address)}`, rel: "noopener", target: "_blank", title: e.address }, e.address.slice(0, 10) + "…" + e.address.slice(-6)) : h("span", { title: e.address }, e.address.slice(0, 18) + "…");
    return [String(i + 1), a, e.kind, zecFull(e.zat), e.revealed_time ? fmtMonth.format(new Date(e.revealed_time * 1000)) : "at creation", fmtMonth.format(new Date(e.last_seen_time * 1000)), e.received_after_reveal_zat > 0 ? zecCompact(e.received_after_reveal_zat) : "–"];
  });
  $("#top-table").replaceChildren(table([{ label: "#", num: true }, { label: "Address", cls: "addr" }, { label: "Type" }, { label: "ZEC", num: true }, { label: "Key revealed" }, { label: "Last active" }, { label: "Received after reveal", num: true }], rows));
}

function renderYcash(Y) {
  if (!Y || !Y.checked) return;
  $("#ycash").hidden = false;
  const box = $("#ycash-tiles");
  box.replaceChildren(
    h("div", { class: "tile" }, h("div", { class: "value" }, zecCompact(Y.revealed_zat), h("span", { class: "unit" }, "ZEC")),
      h("p", {}, `at ${fmtInt.format(Y.revealed_count)} addresses that look hash-protected on Zcash, but whose keys were revealed by spends on Ycash`)),
    h("div", { class: "tile" }, h("div", { class: "value" }, fmtInt.format(Y.checked)),
      h("p", {}, `pre-fork addresses checked (${zecCompact(Y.checked_zat)} ZEC of ${zecCompact(Y.candidates_zat)} ZEC funded before block ${fmtInt.format(Y.fork_height)} and still unspent on Zcash)`)),
    h("div", { class: "tile" }, h("div", { class: "value" }, pctStr(pct(Y.revealed_zat, Y.checked_zat))),
      h("p", {}, "of the checked pre-fork hash-protected value is actually exposed, so the on-chain survey understates exposure")));
  const rows = Y.revealed.slice(0, 15).map((r, i) => [
    String(i + 1),
    h("a", { href: `${EXPLORER}/address/${encodeURIComponent(r.address)}`, rel: "noopener", target: "_blank", title: r.address }, r.address.slice(0, 10) + "…" + r.address.slice(-6)),
    zecFull(r.zat),
    `Ycash block ${fmtInt.format(r.ycash_height)}`,
    h("span", { class: "mono small", title: r.ycash_txid }, r.ycash_txid.slice(0, 12) + "…"),
  ]);
  if (rows.length) {
    $("#ycash-table").replaceChildren(table([{ label: "#", num: true }, { label: "Zcash address", cls: "addr" }, { label: "ZEC still there", num: true }, { label: "Key revealed" }, { label: "Ycash tx" }], rows));
  }
  state.ycash = new Map(Y.revealed.map((r) => [r.address, r]));
}

// ---------------------------------------------------------------- checker
const shardCache = new Map();
async function loadShard(name) {
  if (!shardCache.has(name)) {
    shardCache.set(name, fetch(`${DATA}lookup/${name}.json`).then((r) => (r.ok ? r.json() : { e: [] })).catch(() => null));
  }
  return shardCache.get(name);
}

const STATUS = {
  0: { fate: "hash", title: "Hash-protected", advice: "This address has never been spent from, so its public key isn't on-chain yet. Shor's algorithm can't reach it until you spend, but spending reveals the key and puts any change left here at risk. Sweep everything to a fresh Ironwood address in one transaction." },
  1: { fate: "exposed", title: "Exposed", advice: "This address has been spent from, so its public key is permanently on-chain. A discrete-log-breaking adversary could forge spends of everything here. Move the funds to a fresh Ironwood shielded address and never send to this address again." },
  2: { fate: "unknown", title: "Unknown (P2SH script never revealed)", advice: "The redeem script has never appeared on-chain, so its keys are still hidden. Spending will reveal them. If this is a multisig, recreate it as a FROST threshold key (ZIP 312) in the Ironwood pool." },
  3: { fate: "exposed", title: "Exposed (P2SH script revealed)", advice: "This P2SH address has been spent from, which revealed its redeem script and keys. Move the funds to Ironwood. A multisig can be recreated as a FROST threshold key (ZIP 312)." },
};

async function onCheck(e) {
  e.preventDefault();
  const out = $("#check-result");
  let addr = $("#check-input").value.trim().replace(/\s+/g, "");
  out.replaceChildren();
  out.classList.add("show");
  const msg = (title, text, ic = "unknown") => out.replaceChildren(h("div", { class: "state" }, icon(ic), title), h("p", { class: "advice" }, text));
  if (!addr) return msg("Enter an address", "Paste a t1…, t3… or tex1… address.");
  let note = null;
  if (/^tex1/i.test(addr)) {
    const t1 = await texToT1(addr);
    if (!t1) return msg("Not a valid TEX address", "The Bech32m checksum didn't verify.", "critical");
    note = `TEX address (ZIP 320) decoded to ${t1}`;
    addr = t1;
  }
  if (/^(u1|zs1|zc)/i.test(addr)) {
    const pool = /^zs1/i.test(addr) ? "Sapling" : /^zc/i.test(addr) ? "Sprout" : "a Unified Address";
    return msg(`Shielded address (${pool})`,
      `Shielded balances can't be seen on-chain, which is the point. If the funds sit in Sapling, Orchard or Sprout, migrate them to Ironwood: ZIP 2005 says those pools would be inaccessible once disabled. Also note that a quantum adversary who knows a shielded address could decrypt notes sent to it, so avoid publishing long-lived shielded addresses. A Unified Address's transparent receiver, if it has one, can be checked as a t1 address.`, "serious");
  }
  if (!/^t[13]/.test(addr) || !(await checkT(addr))) return msg("Not a valid mainnet t-address", "Check for typos. Shorline covers mainnet t1… (P2PKH) and t3… (P2SH) addresses.", "critical");
  const shard = shardOf(addr);
  const data = await loadShard(shard);
  if (!data) return msg("Lookup failed", "Couldn't download the lookup shard. Try again, or run `shorline check` locally.", "critical");
  const suffix = addr.slice(4);
  const row = (data.e || []).find((r) => r[0] === suffix);
  const asof = state.summary ? `block ${fmtInt.format(state.summary.chain.height)}` : "the snapshot";
  if (!row) {
    return msg("No balance at this address",
      (note ? note + ". " : "") +
      `No unspent transparent outputs as of ${asof}. If you've spent from this address before, its public key is on-chain, so never receive funds there again. ` +
      `(This shard holds ${fmtInt.format((data.e || []).length)} funded addresses; your browser downloaded all of them, not just yours.)`, "good");
  }
  const [, cat, bal, revealed, first, last] = row;
  let st = STATUS[cat] || { fate: "exposed", title: "Exposed", advice: "" };
  const yc = state.ycash && state.ycash.get(addr);
  if (yc) {
    st = { fate: "exposed", title: "Exposed via Ycash", advice: `This address was never spent from on Zcash, but its ${addr.startsWith("t1") ? "public key" : "redeem script"} was published at Ycash block ${fmtInt.format(yc.ycash_height)} (tx ${yc.ycash_txid.slice(0, 16)}…) when the same pre-fork coins were spent on the Ycash chain. Treat these funds as exposed and move them to Ironwood.` };
  }
  const f = FATES.find((x) => x.id === st.fate);
  const dl = h("dl", {},
    h("dt", {}, "Balance"), h("dd", {}, `${zecExact(bal)} ZEC`),
    h("dt", {}, "Type"), h("dd", {}, addr.startsWith("t1") ? "P2PKH (t1)" : "P2SH (t3)"),
    h("dt", {}, addr.startsWith("t1") ? "Public key revealed" : "Script revealed"),
    h("dd", {}, revealed >= 0 ? `block ${fmtInt.format(revealed)} (${dateOfHeight(revealed)})` : yc ? `never on Zcash · Ycash block ${fmtInt.format(yc.ycash_height)}` : "never"),
    h("dt", {}, "First seen"), h("dd", {}, `block ${fmtInt.format(first)} (${dateOfHeight(first)})`),
    h("dt", {}, "Last active"), h("dd", {}, `block ${fmtInt.format(last)} (${dateOfHeight(last)})`));
  out.replaceChildren(...[
    h("div", { class: "state" }, swatch(f.color), icon(f.icon), st.title),
    note ? h("p", { class: "small muted" }, note) : null,
    dl,
    h("p", { class: "advice" }, st.advice),
    h("p", { class: "small muted" }, `Snapshot as of ${asof}. Your browser downloaded a shard of ${fmtInt.format(data.e.length)} funded addresses and searched it locally.`),
  ].filter(Boolean));
}

// ---------------------------------------------------------------- boot
const resizers = [];
function onResize(fn) { resizers.push(fn); }
let rt;
let lastW = window.innerWidth;
window.addEventListener("resize", () => {
  if (window.innerWidth === lastW) return;
  lastW = window.innerWidth;
  clearTimeout(rt);
  rt = setTimeout(() => { resizers.forEach((f) => f()); renderFate(state.summary); }, 150);
});

$("#theme").addEventListener("click", () => {
  const root = document.documentElement;
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("shorline-theme", root.dataset.theme); } catch (e) {}
});
$("#check-form").addEventListener("submit", (e) => onCheck(e).catch((err) => {
  const out = $("#check-result");
  out.classList.add("show");
  out.replaceChildren(h("p", {}, "Something went wrong: " + err.message));
}));

const state = {};

// ---- NFC: deep link (#check=<address>) + Web NFC scan/write (Chrome on Android).
// iPhones read the same tag natively: tapping opens the URL, and the hash triggers the check.
const SITE = "https://jmohak2004.github.io/shorline/";
function checkFromHash() {
  const m = /[#&]check=([^&]+)/.exec(location.hash);
  if (!m) return;
  $("#check-input").value = decodeURIComponent(m[1]).trim();
  $("#check").scrollIntoView();
  $("#check-form").requestSubmit();
}
function nfcSetup() {
  const msg = $("#nfc-msg");
  if (!("NDEFReader" in window)) return; // unsupported browsers keep the plain checker
  $("#nfc-box").hidden = false;
  $("#nfc-scan").addEventListener("click", async () => {
    try {
      const r = new NDEFReader();
      await r.scan();
      msg.textContent = "Hold a tag against the back of your phone…";
      r.onreading = (e) => {
        for (const rec of e.message.records) {
          const text = new TextDecoder(rec.encoding || "utf-8").decode(rec.data);
          const m = /check=([^&#\s]+)/.exec(text) || /\b(t[13][1-9A-HJ-NP-Za-km-z]{30,36}|tex1[a-z0-9]{30,})\b/.exec(text);
          if (m) { $("#check-input").value = decodeURIComponent(m[1]); $("#check-form").requestSubmit(); msg.textContent = "Tag read."; return; }
        }
        msg.textContent = "That tag has no Zcash address on it.";
      };
    } catch (err) { msg.textContent = "NFC unavailable: " + err.message; }
  });
  $("#nfc-write").addEventListener("click", async () => {
    const addr = $("#check-input").value.trim();
    if (!/^(t[13]|tex1)/i.test(addr)) { msg.textContent = "Type a t1…, t3… or tex1… address first."; return; }
    try {
      msg.textContent = "Hold a blank tag against your phone to write it…";
      await new NDEFReader().write({ records: [{ recordType: "url", data: SITE + "#check=" + encodeURIComponent(addr) }] });
      msg.textContent = "Done. Tapping this tag now opens Shorline with the address pre-filled.";
    } catch (err) { msg.textContent = "Couldn't write the tag: " + err.message; }
  });
}
async function loadJSON(name) {
  const r = await fetch(DATA + name, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
  return r.json();
}

(async function boot() {
  try {
    const optional = (name) => fetch(DATA + name, { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    const [S, T, TOP, Y, SALT] = await Promise.all([loadJSON("summary.json"), loadJSON("timeseries.json"), loadJSON("top.json"), optional("ycash_exposure.json"), optional("salted_exposure.json")]);
    state.summary = S;
    const ci = Object.fromEntries(T.columns.map((c, i) => [c, i]));
    HT = T.rows.filter((r) => r[ci.time] > 0).map((r) => [r[ci.height], r[ci.time]]);
    renderHero(S, Y, SALT);
    renderFate(S);
    renderVerify(S);
    renderHistory(T, S);
    renderAge(S);
    renderReuse(S);
    renderZip2007(S);
    renderSalted(SALT);
    renderYcash(Y);
    renderTop(TOP);
    nfcSetup();
    checkFromHash();
  } catch (err) {
    $("#hero-caption").textContent = "Couldn't load the dataset: " + err.message;
    console.error(err);
  }
})();
