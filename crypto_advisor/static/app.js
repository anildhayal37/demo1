"use strict";

const $ = (id) => document.getElementById(id);
const fmtUsd = (v) => (v < 0 ? "-$" : "$") + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtPrice = (v) => "$" + Number(v).toLocaleString("en-US", { minimumFractionDigits: v < 1 ? 4 : 2, maximumFractionDigits: v < 1 ? 6 : 2 });
const fmtQty = (v) => Number(v).toLocaleString("en-US", { maximumFractionDigits: 6 });

let state = {
  symbol: "BTCUSDT",
  interval: "1m",
  snapshot: null,
};

// ── init ──────────────────────────────────────────────────────────────────────
async function init() {
  const res = await fetch("/api/symbols").then((r) => r.json());
  const symSel = $("symbol");
  res.symbols.forEach((s) => {
    const o = document.createElement("option");
    o.value = s.symbol;
    o.textContent = `${s.label} (${s.symbol.replace("USDT", "")})`;
    symSel.appendChild(o);
  });
  const intSel = $("interval");
  res.intervals.forEach((i) => {
    const o = document.createElement("option");
    o.value = i;
    o.textContent = i;
    intSel.appendChild(o);
  });

  symSel.value = state.symbol;
  intSel.value = state.interval;
  symSel.addEventListener("change", () => { state.symbol = symSel.value; refresh(); });
  intSel.addEventListener("change", () => { state.interval = intSel.value; refresh(); });

  // trade controls
  $("buy").addEventListener("click", () => trade("buy"));
  $("sell").addEventListener("click", () => trade("sell", { pct: 100 }));
  $("reset").addEventListener("click", resetPortfolio);
  document.querySelectorAll(".quick .chip").forEach((b) =>
    b.addEventListener("click", () => { $("amount").value = b.dataset.amt; }));
  document.querySelectorAll(".sell-opts .chip").forEach((b) =>
    b.addEventListener("click", () => trade("sell", { pct: Number(b.dataset.pct) })));

  window.addEventListener("resize", () => { if (state.snapshot) drawChart(state.snapshot); });

  await refresh();
  setInterval(refresh, 3000); // keep an eye on the market
}

// ── data ────────────────────────────────────────────────────────────────────
async function refresh() {
  try {
    const snap = await fetch(`/api/snapshot?symbol=${state.symbol}&interval=${state.interval}&limit=200`).then((r) => r.json());
    if (snap.error) return;
    state.snapshot = snap;
    render(snap);
  } catch (e) {
    // network hiccup — keep last view
  }
}

async function trade(side, opts = {}) {
  const symbol = state.symbol;
  let body;
  if (side === "buy") {
    const usd = Number($("amount").value);
    body = { symbol, usd };
  } else {
    body = { symbol, ...opts };
  }
  const r = await fetch(`/api/${side}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((x) => x.json());

  const msg = $("trade-msg");
  if (r.ok) {
    msg.className = "trade-msg ok";
    if (side === "buy") {
      msg.textContent = `Bought ${fmtQty(r.qty)} ${symbol.replace("USDT", "")} @ ${fmtPrice(r.price)}.`;
    } else {
      const pnl = r.pnl >= 0 ? `profit ${fmtUsd(r.pnl)}` : `loss ${fmtUsd(r.pnl)}`;
      msg.textContent = `Sold ${fmtQty(r.qty)} ${symbol.replace("USDT", "")} @ ${fmtPrice(r.price)} · ${pnl}.`;
    }
  } else {
    msg.className = "trade-msg err";
    msg.textContent = r.error || "Trade failed.";
  }
  refresh();
}

async function resetPortfolio() {
  if (!confirm("Reset your paper balance back to $100,000 and clear all trades?")) return;
  await fetch("/api/reset", { method: "POST" });
  $("trade-msg").className = "trade-msg";
  $("trade-msg").textContent = "Portfolio reset to $100,000.";
  refresh();
}

// ── render ────────────────────────────────────────────────────────────────────
function render(snap) {
  const short = snap.symbol.replace("USDT", "");
  $("price-tag").textContent = snap.price != null ? fmtPrice(snap.price) : "—";
  $("chart-title").textContent = `${short}/USDT · ${snap.interval}`;
  $("trade-symbol").textContent = short;
  const srcTag = $("source-tag");
  srcTag.textContent = snap.source === "live" ? "live data" : "demo data";
  srcTag.className = "source-tag " + (snap.source === "live" ? "live" : "synthetic");

  renderSignal(snap.signal);
  renderPortfolio(snap.portfolio);
  drawChart(snap);
}

function renderSignal(sig) {
  const badge = $("signal-badge");
  badge.textContent = sig.action;
  badge.className = "signal-badge " + sig.action.toLowerCase();
  $("conf-fill").style.width = sig.confidence + "%";
  $("conf-text").textContent = `Confidence ${sig.confidence}%  ·  score ${sig.score}`;

  const ul = $("reasons");
  ul.innerHTML = "";
  (sig.reasons || []).forEach((r) => {
    const li = document.createElement("li");
    li.className = r.bias;
    li.textContent = r.text;
    ul.appendChild(li);
  });

  const ind = sig.indicators || {};
  const cells = [
    ["RSI (14)", ind.rsi != null ? ind.rsi : "—"],
    ["MACD hist", ind.macd_hist != null ? ind.macd_hist : "—"],
    ["SMA 20", ind.sma20 != null ? fmtPrice(ind.sma20) : "—"],
    ["SMA 50", ind.sma50 != null ? fmtPrice(ind.sma50) : "—"],
    ["BB upper", ind.bb_upper != null ? fmtPrice(ind.bb_upper) : "—"],
    ["BB lower", ind.bb_lower != null ? fmtPrice(ind.bb_lower) : "—"],
  ];
  $("indi-grid").innerHTML = cells.map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join("");
}

function renderPortfolio(p) {
  $("equity").textContent = fmtUsd(p.equity);
  const chip = $("total-pnl");
  const sign = p.total_pnl >= 0 ? "+" : "";
  chip.textContent = `${sign}${fmtUsd(p.total_pnl)} (${sign}${p.total_pnl_pct.toFixed(2)}%)`;
  chip.className = "pnl-chip " + (p.total_pnl >= 0 ? "pos" : "neg");

  $("cash").textContent = fmtUsd(p.cash);
  $("holdings-value").textContent = fmtUsd(p.holdings_value);
  setPnl($("realized"), p.realized_pnl);
  setPnl($("unrealized"), p.unrealized_pnl);

  // positions
  const tb = $("positions");
  if (!p.positions.length) {
    tb.innerHTML = `<tr><td colspan="6" class="empty">No open positions.</td></tr>`;
  } else {
    tb.innerHTML = p.positions.map((pos) => {
      const cls = pos.pnl >= 0 ? "pos" : "neg";
      const sign = pos.pnl >= 0 ? "+" : "";
      return `<tr>
        <td>${pos.short}</td>
        <td>${fmtQty(pos.qty)}</td>
        <td>${fmtPrice(pos.avg_cost)}</td>
        <td>${fmtPrice(pos.price)}</td>
        <td>${fmtUsd(pos.value)}</td>
        <td class="${cls}">${sign}${fmtUsd(pos.pnl)} (${sign}${pos.pnl_pct.toFixed(2)}%)</td>
      </tr>`;
    }).join("");
  }

  // history
  const hb = $("history");
  if (!p.trades.length) {
    hb.innerHTML = `<tr><td colspan="7" class="empty">No trades yet.</td></tr>`;
  } else {
    hb.innerHTML = p.trades.map((t) => {
      const time = new Date(t.time * 1000).toLocaleTimeString();
      const pnlCell = t.side === "SELL"
        ? `<td class="${t.pnl >= 0 ? "pos" : "neg"}">${t.pnl >= 0 ? "+" : ""}${fmtUsd(t.pnl)}</td>`
        : `<td class="muted">—</td>`;
      return `<tr>
        <td>${time}</td>
        <td class="side-${t.side.toLowerCase()}">${t.side}</td>
        <td>${t.short}</td>
        <td>${fmtQty(t.qty)}</td>
        <td>${fmtPrice(t.price)}</td>
        <td>${fmtUsd(t.usd)}</td>
        ${pnlCell}
      </tr>`;
    }).join("");
  }
}

function setPnl(el, v) {
  el.textContent = (v >= 0 ? "+" : "") + fmtUsd(v);
  el.className = v >= 0 ? "pos" : "neg";
}

// ── canvas candlestick chart ─────────────────────────────────────────────────
function drawChart(snap) {
  const canvas = $("chart");
  const candles = snap.candles || [];
  if (!candles.length) return;

  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas.clientWidth;
  const cssH = canvas.clientHeight;
  canvas.width = cssW * dpr;
  canvas.height = cssH * dpr;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);

  const padL = 8, padR = 64, padT = 12, padB = 22;
  const plotW = cssW - padL - padR;
  const plotH = cssH - padT - padB;

  const series = snap.signal.series || {};
  // y-range from candle highs/lows + bollinger bands
  let lo = Infinity, hi = -Infinity;
  candles.forEach((c) => { lo = Math.min(lo, c.low); hi = Math.max(hi, c.high); });
  (series.bb_upper || []).forEach((v) => { if (v != null) hi = Math.max(hi, v); });
  (series.bb_lower || []).forEach((v) => { if (v != null) lo = Math.min(lo, v); });
  const range = hi - lo || 1;
  lo -= range * 0.04; hi += range * 0.04;

  const n = candles.length;
  const x = (i) => padL + (plotW * (i + 0.5)) / n;
  const y = (p) => padT + plotH * (1 - (p - lo) / (hi - lo));

  // grid + price axis
  ctx.strokeStyle = "rgba(38,50,71,0.6)";
  ctx.fillStyle = "#8b9bb4";
  ctx.font = "11px -apple-system, sans-serif";
  ctx.lineWidth = 1;
  const gridN = 5;
  for (let g = 0; g <= gridN; g++) {
    const py = padT + (plotH * g) / gridN;
    const price = hi - ((hi - lo) * g) / gridN;
    ctx.beginPath(); ctx.moveTo(padL, py); ctx.lineTo(padL + plotW, py); ctx.stroke();
    ctx.fillText(fmtPrice(price), padL + plotW + 6, py + 4);
  }

  // Bollinger band fill
  const bbU = series.bb_upper || [], bbL = series.bb_lower || [];
  ctx.beginPath();
  let started = false;
  for (let i = 0; i < n; i++) {
    if (bbU[i] == null) continue;
    if (!started) { ctx.moveTo(x(i), y(bbU[i])); started = true; }
    else ctx.lineTo(x(i), y(bbU[i]));
  }
  for (let i = n - 1; i >= 0; i--) {
    if (bbL[i] == null) continue;
    ctx.lineTo(x(i), y(bbL[i]));
  }
  if (started) { ctx.closePath(); ctx.fillStyle = "rgba(93,107,134,0.10)"; ctx.fill(); }

  // candles
  const cw = Math.max(1.5, (plotW / n) * 0.6);
  candles.forEach((c, i) => {
    const up = c.close >= c.open;
    ctx.strokeStyle = up ? "#1fbf75" : "#ff5470";
    ctx.fillStyle = up ? "#1fbf75" : "#ff5470";
    const cx = x(i);
    // wick
    ctx.beginPath(); ctx.moveTo(cx, y(c.high)); ctx.lineTo(cx, y(c.low)); ctx.stroke();
    // body
    const yo = y(c.open), yc = y(c.close);
    const top = Math.min(yo, yc);
    const h = Math.max(1, Math.abs(yc - yo));
    ctx.fillRect(cx - cw / 2, top, cw, h);
  });

  // moving averages
  drawLine(ctx, series.sma20, x, y, n, "#4f8cff");
  drawLine(ctx, series.sma50, x, y, n, "#c061ff");
  drawLine(ctx, bbU, x, y, n, "rgba(93,107,134,0.5)");
  drawLine(ctx, bbL, x, y, n, "rgba(93,107,134,0.5)");

  // historical buy/sell markers from SMA20/SMA50 crossovers
  const s20 = series.sma20 || [], s50 = series.sma50 || [];
  for (let i = 1; i < n; i++) {
    if (s20[i] == null || s50[i] == null || s20[i - 1] == null || s50[i - 1] == null) continue;
    const crossUp = s20[i - 1] <= s50[i - 1] && s20[i] > s50[i];
    const crossDn = s20[i - 1] >= s50[i - 1] && s20[i] < s50[i];
    if (crossUp) marker(ctx, x(i), y(candles[i].low), "#1fbf75", "▲");
    else if (crossDn) marker(ctx, x(i), y(candles[i].high), "#ff5470", "▼");
  }

  // live signal marker on the last candle
  const last = candles[n - 1];
  const act = snap.signal.action;
  if (act === "BUY") marker(ctx, x(n - 1), y(last.low), "#1fbf75", "▲", true);
  else if (act === "SELL") marker(ctx, x(n - 1), y(last.high), "#ff5470", "▼", true);
}

function drawLine(ctx, arr, x, y, n, color) {
  if (!arr) return;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  let started = false;
  for (let i = 0; i < n; i++) {
    if (arr[i] == null) continue;
    if (!started) { ctx.moveTo(x(i), y(arr[i])); started = true; }
    else ctx.lineTo(x(i), y(arr[i]));
  }
  ctx.stroke();
}

function marker(ctx, px, py, color, glyph, big = false) {
  const off = glyph === "▲" ? 10 : -4;
  ctx.fillStyle = color;
  ctx.font = (big ? "16px" : "11px") + " -apple-system, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(glyph, px, py + off);
  ctx.textAlign = "start";
}

init();
