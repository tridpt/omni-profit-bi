/**
 * ProfitPulse BI — Interactive Frontend Controller & Custom SVG Chart Engine
 */

const state = {
  datasets: [],
  currentDatasetId: "vn_fashion_omni",
  activeTab: "tab-pnl",
  overviewData: null,
  skuBadgeFilter: "ALL",
  rfmData: null,
  inventoryData: null,
  abcSelectedCell: null,
  sqlWorkbench: null,
  lastSqlResult: null,
};

// ============================================================================
// FORMATTING HELPERS (VIETNAMESE VND & COMPACT UNITS)
// ============================================================================
const fmtInt = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });
const fmtDec = new Intl.NumberFormat("vi-VN", { minimumFractionDigits: 1, maximumFractionDigits: 2 });

function formatVND(val) {
  if (val === null || val === undefined || Number.isNaN(Number(val))) return "—";
  return `${fmtInt.format(Math.round(Number(val)))} đ`;
}

function formatCompactVND(val) {
  const n = Number(val) || 0;
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1_000_000_000) return `${sign}${(abs / 1_000_000_000).toFixed(2)} tỷ`;
  if (abs >= 1_000_000) return `${sign}${(abs / 1_000_000).toFixed(1)} tr`;
  if (abs >= 1_000) return `${sign}${Math.round(abs / 1_000)}k`;
  return `${sign}${Math.round(abs)}`;
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ============================================================================
// TOOLTIP CONTROLLER
// ============================================================================
const tooltipEl = document.getElementById("chartTooltip");

function showTooltip(evt, html) {
  tooltipEl.innerHTML = html;
  tooltipEl.classList.remove("hidden");
  moveTooltip(evt);
}

function moveTooltip(evt) {
  const pad = 14;
  let x = evt.clientX + pad;
  let y = evt.clientY + pad;
  const rect = tooltipEl.getBoundingClientRect();
  if (x + rect.width > window.innerWidth - 12) x = evt.clientX - rect.width - pad;
  if (y + rect.height > window.innerHeight - 12) y = evt.clientY - rect.height - pad;
  tooltipEl.style.left = `${x}px`;
  tooltipEl.style.top = `${y}px`;
}

function hideTooltip() {
  tooltipEl.classList.add("hidden");
}

// ============================================================================
// API FETCH WRAPPER
// ============================================================================
async function apiGet(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Lỗi kết nối máy chủ");
  }
  return res.json();
}

async function apiPost(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Lỗi xử lý yêu cầu");
  }
  return res.json();
}

// ============================================================================
// DATASET & FILTER INITIALIZATION
// ============================================================================
async function loadDatasets(preferredId = null) {
  const data = await apiGet("/api/datasets");
  state.datasets = data.datasets || [];
  if (!state.datasets.length) return;

  if (preferredId && state.datasets.some((d) => d.dataset_id === preferredId)) {
    state.currentDatasetId = preferredId;
  } else if (!state.datasets.some((d) => d.dataset_id === state.currentDatasetId)) {
    state.currentDatasetId = state.datasets[0].dataset_id;
  }

  const sel = document.getElementById("datasetSelect");
  sel.innerHTML = state.datasets
    .map(
      (d) =>
        `<option value="${escapeHtml(d.dataset_id)}" ${
          d.dataset_id === state.currentDatasetId ? "selected" : ""
        }>${escapeHtml(d.name)} (${fmtInt.format(d.total_orders)} đơn)</option>`
    )
    .join("");

  applyDatasetMetadata();
}

function getCurrentDatasetMeta() {
  return state.datasets.find((d) => d.dataset_id === state.currentDatasetId) || state.datasets[0];
}

function applyDatasetMetadata() {
  const ds = getCurrentDatasetMeta();
  if (!ds) return;

  document.getElementById("industryBadge").textContent = ds.industry;
  document.getElementById("scenarioDesc").textContent = ds.description;

  const delBtn = document.getElementById("deleteDatasetBtn");
  delBtn.classList.toggle("hidden", Boolean(ds.is_builtin));

  // Populate global channel filter
  const chanSel = document.getElementById("channelFilter");
  chanSel.innerHTML =
    `<option value="ALL">Tất cả các kênh (${ds.channels.length})</option>` +
    ds.channels.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");

  // Populate date bounds
  const startIn = document.getElementById("startDateFilter");
  const endIn = document.getElementById("endDateFilter");
  startIn.min = ds.min_date || "";
  startIn.max = ds.max_date || "";
  endIn.min = ds.min_date || "";
  endIn.max = ds.max_date || "";
  startIn.value = ds.min_date || "";
  endIn.value = ds.max_date || "";

  // Populate Simulator dropdowns
  const simSkuSel = document.getElementById("simSkuSelect");
  simSkuSel.innerHTML =
    `<option value="ALL">📦 Toàn bộ danh mục (${ds.skus.length} SKU)</option>` +
    ds.skus
      .map(
        (s) =>
          `<option value="${escapeHtml(s.sku_code)}">${escapeHtml(s.sku_code)} — ${escapeHtml(
            s.product_name
          )} (${formatCompactVND(s.list_price)})</option>`
      )
      .join("");

  const simChanSel = document.getElementById("simChannelSelect");
  simChanSel.innerHTML =
    `<option value="ALL">🌐 Tất cả các kênh</option>` +
    ds.channels.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
}

async function refreshActiveTab() {
  if (state.activeTab === "tab-pnl") {
    await loadPnlOverview();
  } else if (state.activeTab === "tab-rfm") {
    await loadRfmTab();
  } else if (state.activeTab === "tab-inventory") {
    await loadInventoryTab();
  } else if (state.activeTab === "tab-simulator") {
    await runSimulation();
  } else if (state.activeTab === "tab-predictive") {
    await loadPredictiveTab();
  } else if (state.activeTab === "tab-sql") {
    await loadSqlWorkbench();
  }
}

// ============================================================================
// TAB 1: P&L OVERVIEW, WATERFALL, VARIANCE BRIDGE & SKU MATRIX
// ============================================================================
async function loadPnlOverview() {
  const chan = document.getElementById("channelFilter").value;
  const start = document.getElementById("startDateFilter").value;
  const end = document.getElementById("endDateFilter").value;
  const qs = new URLSearchParams({
    dataset_id: state.currentDatasetId,
    channel: chan,
    start_date: start,
    end_date: end,
  });

  const data = await apiGet(`/api/overview?${qs.toString()}`);
  state.overviewData = data;

  renderPnlKpis(data.kpis);
  renderWaterfallSvg("waterfallChart", data.waterfall);
  renderVarianceSection(data.variance_bridge);
  renderChannelTable(data.channels_pnl);
  renderMonthlyTrendSvg("monthlyTrendChart", data.monthly_trend);
  renderSkuPnlTable();
}

function renderPnlKpis(k) {
  const isProfitable = k.true_net_profit >= 0;
  const feeTotal = k.platform_and_payment_fees + k.affiliate_fee + k.shipping_seller;
  const feeRatio = k.net_revenue > 0 ? ((feeTotal / k.net_revenue) * 100).toFixed(1) : "0.0";

  document.getElementById("pnlKpiGrid").innerHTML = `
    <div class="kpi-card">
      <span class="kpi-label">Doanh Thu Thuần (Net Rev)</span>
      <div class="kpi-value">${formatCompactVND(k.net_revenue)}</div>
      <span class="kpi-sub">GMV: ${formatCompactVND(k.completed_gross)} • Voucher: -${formatCompactVND(k.seller_discount)}</span>
    </div>
    <div class="kpi-card ${isProfitable ? "highlight-profit" : "highlight-loss"}">
      <span class="kpi-label">Lãi Ròng Thực Bỏ Túi</span>
      <div class="kpi-value ${isProfitable ? "text-emerald" : "text-rose"}">${formatCompactVND(k.true_net_profit)}</div>
      <span class="kpi-sub">Biên ròng: <strong>${k.net_margin_pct}%</strong> (Gộp: ${k.gross_margin_pct}%)</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-label">Phí Sàn + Affiliate + Ship</span>
      <div class="kpi-value text-amber">-${formatCompactVND(feeTotal)}</div>
      <span class="kpi-sub">Chiếm <strong>${feeRatio}%</strong> doanh thu thuần</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-label">Thiệt Hại Đơn Hoàn / Bom</span>
      <div class="kpi-value text-rose">-${formatCompactVND(k.return_loss)}</div>
      <span class="kpi-sub">Tỷ lệ hoàn: <strong>${k.return_rate_pct}%</strong> (${fmtInt.format(k.returned_orders)} đơn)</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-label">Chi Phí Ads &amp; Hiệu Suất</span>
      <div class="kpi-value">${formatCompactVND(k.ad_spend)}</div>
      <span class="kpi-sub">ROAS: <strong>${k.roas}x</strong> • POAS Lãi: <strong class="text-cyan">${k.poas}x</strong></span>
    </div>
    <div class="kpi-card">
      <span class="kpi-label">Quy Mô Đơn Thành Công</span>
      <div class="kpi-value">${fmtInt.format(k.completed_orders)} đơn</div>
      <span class="kpi-sub">AOV: ${formatVND(k.aov)} • ${fmtInt.format(k.units_sold)} SP</span>
    </div>
  `;
}

function renderWaterfallSvg(containerId, steps) {
  const el = document.getElementById(containerId);
  if (!steps || !steps.length) {
    el.innerHTML = `<div class="muted-sm">Không đủ dữ liệu vẽ biểu đồ.</div>`;
    return;
  }

  // Compute floating y0 -> y1 intervals
  let running = 0;
  const bars = steps.map((st) => {
    let startVal, endVal;
    if (st.type === "total" || st.type === "subtotal" || st.type === "final" || st.type === "start" || st.type === "end") {
      startVal = 0;
      endVal = st.value;
      running = st.value;
    } else {
      startVal = running;
      endVal = running + st.value;
      running = endVal;
    }
    return { ...st, startVal, endVal };
  });

  const allVals = bars.flatMap((b) => [b.startVal, b.endVal, 0]);
  const maxVal = Math.max(...allVals, 1);
  const minVal = Math.min(...allVals, 0);
  const range = (maxVal - minVal) * 1.18 || 1;
  const topVal = maxVal + (maxVal - minVal) * 0.12;

  const W = 740;
  const H = 300;
  const padL = 58;
  const padR = 16;
  const padT = 26;
  const padB = 64;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const yScale = (v) => padT + ((topVal - v) / range) * plotH;
  const zeroY = yScale(0);
  const stepW = plotW / bars.length;
  const barW = Math.min(48, stepW * 0.62);

  let gridSvg = "";
  for (let i = 0; i <= 4; i++) {
    const gv = minVal + ((maxVal - minVal) * i) / 4;
    const gy = yScale(gv);
    gridSvg += `
      <line x1="${padL}" y1="${gy}" x2="${W - padR}" y2="${gy}" stroke="#1e293b" stroke-dasharray="3,3" />
      <text x="${padL - 8}" y="${gy + 4}" text-anchor="end" fill="#64748b" font-size="10.5">${formatCompactVND(gv)}</text>
    `;
  }

  let barsSvg = "";
  bars.forEach((b, idx) => {
    const cx = padL + stepW * idx + stepW / 2;
    const x = cx - barW / 2;
    const yTop = yScale(Math.max(b.startVal, b.endVal));
    const yBot = yScale(Math.min(b.startVal, b.endVal));
    const h = Math.max(3, yBot - yTop);

    let fill = "#6366f1";
    if (b.type === "subtotal") fill = "#0ea5e9";
    else if (b.type === "final" || b.type === "end") fill = b.value >= 0 ? "#10b981" : "#f43f5e";
    else if (b.type === "deduct" || (b.type === "delta" && b.value < 0)) fill = "#f43f5e";
    else if (b.type === "delta" && b.value >= 0) fill = "#10b981";

    // Connector line to next bar
    if (idx < bars.length - 1) {
      const nextX = padL + stepW * (idx + 1) + stepW / 2 - barW / 2;
      const connY = yScale(b.endVal);
      barsSvg += `<line x1="${x + barW}" y1="${connY}" x2="${nextX}" y2="${connY}" stroke="#475569" stroke-dasharray="2,2" />`;
    }

    const labelVal = (b.value > 0 && b.type === "delta" ? "+" : "") + formatCompactVND(b.value);
    const labelY = b.value >= 0 || b.type === "total" || b.type === "subtotal" ? yTop - 6 : yBot + 13;

    const words = b.label.split(" ");
    const mid = Math.ceil(words.length / 2);
    const line1 = words.slice(0, mid).join(" ");
    const line2 = words.slice(mid).join(" ");

    barsSvg += `
      <g class="wf-bar" data-tip="<strong>${escapeHtml(b.label)}</strong><br/>Giá trị: <strong>${formatVND(b.value)}</strong>">
        <rect x="${x}" y="${yTop}" width="${barW}" height="${h}" rx="4" fill="${fill}" opacity="0.92" />
        <text x="${cx}" y="${labelY}" text-anchor="middle" fill="#e2e8f0" font-size="10.5" font-weight="700">${labelVal}</text>
        <text x="${cx}" y="${H - padB + 18}" text-anchor="middle" fill="#94a3b8" font-size="10">
          <tspan x="${cx}" dy="0">${escapeHtml(line1)}</tspan>
          <tspan x="${cx}" dy="13">${escapeHtml(line2)}</tspan>
        </text>
      </g>
    `;
  });

  el.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" width="100%" height="300">
      ${gridSvg}
      <line x1="${padL}" y1="${zeroY}" x2="${W - padR}" y2="${zeroY}" stroke="#475569" stroke-width="1.2" />
      ${barsSvg}
    </svg>
  `;

  el.querySelectorAll(".wf-bar").forEach((node) => {
    node.addEventListener("mouseenter", (e) => showTooltip(e, node.dataset.tip));
    node.addEventListener("mousemove", moveTooltip);
    node.addEventListener("mouseleave", hideTooltip);
  });
}

function renderVarianceSection(vb) {
  const titleEl = document.getElementById("varianceTitle");
  const insEl = document.getElementById("varianceInsights");
  if (!vb || !vb.available) {
    titleEl.textContent = "Giải Phẫu Biến Động Lãi Ròng (Cần ít nhất 2 tháng dữ liệu)";
    document.getElementById("varianceChart").innerHTML = `<div class="muted-sm">Hãy mở rộng khoảng ngày lọc để so sánh giữa 2 tháng.</div>`;
    insEl.innerHTML = "";
    return;
  }
  titleEl.textContent = `Giải Phẫu Biến Động Lãi Ròng (${vb.prev_month} ➔ ${vb.curr_month})`;
  renderWaterfallSvg("varianceChart", vb.steps);
  insEl.innerHTML = vb.insights.map((line) => `<div>• ${escapeHtml(line)}</div>`).join("");
}

function renderChannelTable(channels) {
  const wrap = document.getElementById("channelTableWrap");
  wrap.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Kênh Bán</th>
          <th class="num">Đơn TC</th>
          <th class="num">Hoàn %</th>
          <th class="num">Doanh Thu Thuần</th>
          <th class="num">Phí + Ads %</th>
          <th class="num">Lãi Ròng Thực</th>
          <th class="num">Biên Ròng</th>
        </tr>
      </thead>
      <tbody>
        ${channels
          .map(
            (c) => `
          <tr>
            <td><strong>${escapeHtml(c.channel)}</strong></td>
            <td class="num">${fmtInt.format(c.completed_orders)}</td>
            <td class="num ${c.return_rate_pct >= 14 ? "text-rose" : ""}">${c.return_rate_pct}%</td>
            <td class="num">${formatCompactVND(c.net_rev)}</td>
            <td class="num ${c.fee_and_ads_pct >= 24 ? "text-amber" : ""}">${c.fee_and_ads_pct}%</td>
            <td class="num ${c.net_profit >= 0 ? "text-emerald" : "text-rose"}"><strong>${formatCompactVND(c.net_profit)}</strong></td>
            <td class="num"><strong>${c.net_margin_pct}%</strong></td>
          </tr>
        `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderMonthlyTrendSvg(containerId, months) {
  const el = document.getElementById(containerId);
  if (!months || !months.length) {
    el.innerHTML = `<div class="muted-sm">Không có dữ liệu theo tháng.</div>`;
    return;
  }

  const W = 680;
  const H = 285;
  const padL = 56;
  const padR = 24;
  const padT = 26;
  const padB = 42;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const maxRev = Math.max(...months.map((m) => Math.max(m.net_revenue, m.net_profit)), 1) * 1.15;
  const minVal = Math.min(0, ...months.map((m) => m.net_profit));
  const span = maxRev - minVal;
  const yScale = (v) => padT + ((maxRev - v) / span) * plotH;
  const zeroY = yScale(0);
  const stepW = plotW / months.length;
  const barW = Math.min(28, stepW * 0.32);

  let grid = "";
  for (let i = 0; i <= 4; i++) {
    const v = minVal + (span * i) / 4;
    const y = yScale(v);
    grid += `
      <line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#1e293b" stroke-dasharray="3,3" />
      <text x="${padL - 8}" y="${y + 4}" text-anchor="end" fill="#64748b" font-size="10.5">${formatCompactVND(v)}</text>
    `;
  }

  let bars = "";
  const profitPts = [];

  months.forEach((m, i) => {
    const cx = padL + stepW * i + stepW / 2;
    const revY = yScale(m.net_revenue);
    const revH = Math.max(2, zeroY - revY);
    const costTot = m.fees_and_returns + m.ad_spend;
    const costY = yScale(costTot);
    const costH = Math.max(2, zeroY - costY);
    const profY = yScale(m.net_profit);
    profitPts.push(`${cx},${profY}`);

    const tip = `
      <strong>Tháng ${escapeHtml(m.month)}</strong> (${fmtInt.format(m.completed_orders)} đơn)<br/>
      • Doanh thu thuần: <strong>${formatVND(m.net_revenue)}</strong><br/>
      • Phí + Đơn hoàn + Ads: <span class="text-rose">${formatVND(costTot)}</span><br/>
      • Lãi ròng thực: <strong class="text-emerald">${formatVND(m.net_profit)} (${m.net_margin_pct}%)</strong>
    `;

    bars += `
      <g class="trend-grp" data-tip="${escapeHtml(tip)}">
        <rect x="${cx - barW - 2}" y="${revY}" width="${barW}" height="${revH}" rx="3" fill="#4f46e5" opacity="0.82" />
        <rect x="${cx + 2}" y="${costY}" width="${barW}" height="${costH}" rx="3" fill="#f59e0b" opacity="0.78" />
        <text x="${cx}" y="${H - 14}" text-anchor="middle" fill="#94a3b8" font-size="11">${escapeHtml(m.month)}</text>
      </g>
    `;
  });

  const dots = months
    .map((m, i) => {
      const cx = padL + stepW * i + stepW / 2;
      const py = yScale(m.net_profit);
      return `
        <circle cx="${cx}" cy="${py}" r="4.5" fill="#10b981" stroke="#070d19" stroke-width="2" />
        <text x="${cx}" y="${py - 9}" text-anchor="middle" fill="#34d399" font-size="10.5" font-weight="700">${m.net_margin_pct}%</text>
      `;
    })
    .join("");

  el.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" width="100%" height="285">
      ${grid}
      <line x1="${padL}" y1="${zeroY}" x2="${W - padR}" y2="${zeroY}" stroke="#475569" />
      ${bars}
      <polyline fill="none" stroke="#10b981" stroke-width="2.6" points="${profitPts.join(" ")}" />
      ${dots}
      <g transform="translate(${padL + 8}, 12)" font-size="11" fill="#cbd5e1">
        <rect x="0" y="-8" width="10" height="10" rx="2" fill="#4f46e5" />
        <text x="14" y="0">Doanh thu thuần</text>
        <rect x="122" y="-8" width="10" height="10" rx="2" fill="#f59e0b" />
        <text x="136" y="0">Phí sàn + Hoàn + Ads</text>
        <circle cx="276" cy="-3" r="4" fill="#10b981" />
        <text x="285" y="0">Lãi ròng &amp; Biên %</text>
      </g>
    </svg>
  `;

  el.querySelectorAll(".trend-grp").forEach((g) => {
    g.addEventListener("mouseenter", (e) => showTooltip(e, g.dataset.tip));
    g.addEventListener("mousemove", moveTooltip);
    g.addEventListener("mouseleave", hideTooltip);
  });
}

function renderSkuPnlTable() {
  if (!state.overviewData) return;
  const rows = state.overviewData.sku_pnl.filter(
    (s) => state.skuBadgeFilter === "ALL" || s.badge === state.skuBadgeFilter
  );

  const badgeCls = (b) => {
    if (b === "BLEEDER") return "badge badge-bleeder";
    if (b === "STAR") return "badge badge-star";
    if (b === "CASH_COW") return "badge badge-cow";
    return "badge badge-niche";
  };

  document.getElementById("skuPnlTableWrap").innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Mã SKU &amp; Sản Phẩm</th>
          <th class="num">SL Bán</th>
          <th class="num">Hoàn %</th>
          <th class="num">Doanh Thu Thuần</th>
          <th class="num">Giá Vốn+Gói</th>
          <th class="num">Phí Sàn+Aff</th>
          <th class="num">Lỗ Hoàn+Ads</th>
          <th class="num">Lãi Ròng Thực</th>
          <th class="num">Lãi / 1 SP</th>
          <th>Phân Nhóm &amp; Khuyến Nghị</th>
          <th>Thao tác</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (s) => `
          <tr>
            <td>
              <strong>${escapeHtml(s.sku_code)}</strong>
              <div class="muted-sm">${escapeHtml(s.product_name)}</div>
            </td>
            <td class="num">${fmtInt.format(s.units_sold)}</td>
            <td class="num ${s.return_rate_pct >= 14 ? "text-rose" : ""}">${s.return_rate_pct}%</td>
            <td class="num">${formatCompactVND(s.net_revenue)}</td>
            <td class="num">-${formatCompactVND(s.cogs_pack)}</td>
            <td class="num">-${formatCompactVND(s.fees_total)}</td>
            <td class="num">-${formatCompactVND(s.return_loss + s.ad_spend)}</td>
            <td class="num ${s.net_profit >= 0 ? "text-emerald" : "text-rose"}">
              <strong>${formatVND(s.net_profit)}</strong>
              <div class="muted-sm">${s.net_margin_pct}%</div>
            </td>
            <td class="num ${s.profit_per_unit >= 0 ? "text-emerald" : "text-rose"}">${formatVND(s.profit_per_unit)}</td>
            <td>
              <span class="${badgeCls(s.badge)}">${escapeHtml(s.badge_label)}</span>
              <div class="muted-sm" style="max-width: 280px; margin-top: 3px;">${escapeHtml(s.advice)}</div>
            </td>
            <td>
              <button class="btn btn-secondary btn-sm jump-sim-btn" data-sku="${escapeHtml(s.sku_code)}">🎛️ Giả lập</button>
            </td>
          </tr>
        `
          )
          .join("")}
      </tbody>
    </table>
  `;

  document.querySelectorAll(".jump-sim-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const sku = btn.dataset.sku;
      document.getElementById("simSkuSelect").value = sku;
      switchTab("tab-simulator");
    });
  });
}

// ============================================================================
// TAB 2: RFM, COHORT RETENTION & BUDGET OPTIMIZER
// ============================================================================
async function loadRfmTab() {
  const budget = Number(document.getElementById("retentionBudgetInput").value) || 15000000;
  const qs = new URLSearchParams({
    dataset_id: state.currentDatasetId,
    budget_vnd: String(budget),
  });
  const data = await apiGet(`/api/rfm-cohort?${qs.toString()}`);
  state.rfmData = data;

  const s = data.summary;
  document.getElementById("rfmSummaryGrid").innerHTML = `
    <div class="kpi-card">
      <span class="kpi-label">Tổng Khách Hàng Đã Mua</span>
      <div class="kpi-value">${fmtInt.format(s.active_customers)}</div>
      <span class="kpi-sub">Tính đến mốc ${escapeHtml(data.reference_date)}</span>
    </div>
    <div class="kpi-card highlight-profit">
      <span class="kpi-label">LTV Lợi Nhuận Gộp / Khách</span>
      <div class="kpi-value text-emerald">${formatVND(s.avg_ltv_profit)}</div>
      <span class="kpi-sub">Đã trừ giá vốn, phí sàn &amp; đơn hoàn</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-label">Chi Phí Thu Hút TB (CAC)</span>
      <div class="kpi-value">${formatVND(s.avg_cac)}</div>
      <span class="kpi-sub">Chi phí Marketing thu hút đơn đầu</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-label">Tỷ Số Sức Khỏe LTV : CAC</span>
      <div class="kpi-value ${s.blended_ltv_cac >= 3 ? "text-emerald" : "text-amber"}">${s.blended_ltv_cac}x</div>
      <span class="kpi-sub">Chuẩn bền vững TMĐT: ≥ 3.0x</span>
    </div>
  `;

  document.getElementById("rfmSegmentsWrap").innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Phân Khúc RFM</th>
          <th class="num">Số Khách</th>
          <th class="num">Tỷ Trọng</th>
          <th class="num">Recency TB</th>
          <th class="num">Số Đơn TB</th>
          <th class="num">LTV Lãi / Khách</th>
          <th class="num">LTV / CAC</th>
        </tr>
      </thead>
      <tbody>
        ${data.segments
          .map(
            (seg) => `
          <tr>
            <td><strong>${escapeHtml(seg.segment_name)}</strong></td>
            <td class="num">${fmtInt.format(seg.customer_count)}</td>
            <td class="num">${seg.share_pct}%</td>
            <td class="num">${seg.avg_recency_days} ngày</td>
            <td class="num">${seg.avg_frequency}</td>
            <td class="num ${seg.avg_ltv_profit >= 0 ? "text-emerald" : "text-rose"}">${formatVND(seg.avg_ltv_profit)}</td>
            <td class="num"><strong>${seg.ltv_cac_ratio}x</strong></td>
          </tr>
        `
          )
          .join("")}
      </tbody>
    </table>
  `;

  // Cohort Heatmap
  const monthsCols = ["M0", "M1", "M2", "M3", "M4", "M5"];
  document.getElementById("cohortHeatmapWrap").innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Cohort</th>
          <th class="num">Khách Mới</th>
          ${monthsCols.map((m) => `<th class="num">${m}</th>`).join("")}
          <th class="num">LTV Lãi Lũy Kế</th>
        </tr>
      </thead>
      <tbody>
        ${data.cohort_matrix
          .map((row) => {
            const cells = monthsCols
              .map((mk) => {
                const v = row.retention[mk];
                if (v === undefined) return `<td class="heat-cell muted-sm">—</td>`;
                const alpha = mk === "M0" ? 0.25 : Math.min(0.82, Math.max(0.1, v / 42));
                const bg = mk === "M0" ? "rgba(99, 102, 241, 0.22)" : `rgba(16, 185, 129, ${alpha.toFixed(2)})`;
                return `<td class="heat-cell num" style="background:${bg}">${v}%</td>`;
              })
              .join("");
            return `
              <tr>
                <td><strong>${escapeHtml(row.cohort_month)}</strong></td>
                <td class="num">${fmtInt.format(row.cohort_size)}</td>
                ${cells}
                <td class="num text-emerald"><strong>${formatVND(row.cum_ltv_profit)}</strong> <span class="muted-sm">(${row.payback_ratio}x CAC)</span></td>
              </tr>
            `;
          })
          .join("")}
      </tbody>
    </table>
  `;

  // Optimizer results
  const opt = data.optimizer;
  document.getElementById("optimizerKpiStrip").innerHTML = `
    <div class="mini-stat">
      <span>Số Khách Hàng Được Chọn Cứu</span>
      <strong class="text-cyan">${fmtInt.format(opt.customers_selected)} / ${fmtInt.format(opt.eligible_pool)} KH</strong>
    </div>
    <div class="mini-stat">
      <span>Ngân Sách Thực Dùng</span>
      <strong>${formatVND(opt.budget_used)}</strong>
    </div>
    <div class="mini-stat">
      <span>Doanh Thu Tăng Thêm Kỳ Vọng</span>
      <strong>${formatVND(opt.projected_incremental_revenue)}</strong>
    </div>
    <div class="mini-stat">
      <span>Lãi Ròng Tăng Thêm Kỳ Vọng</span>
      <strong class="text-emerald">+${formatVND(opt.projected_incremental_net_profit)}</strong>
    </div>
    <div class="mini-stat">
      <span>Tỷ Suất Sinh Lời Chiến Dịch (Net ROI)</span>
      <strong class="text-emerald">+${opt.net_roi_pct}%</strong>
    </div>
  `;

  document.getElementById("optimizerTableWrap").innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Mã KH &amp; Họ Tên</th>
          <th>Phân Khúc &amp; Điểm RFM</th>
          <th class="num">Chưa Mua</th>
          <th class="num">LTV Lãi Cũ</th>
          <th>Kịch Bản Hành Động Đề Xuất</th>
          <th class="num">Chi Phí Dự Kiến</th>
          <th class="num">Lãi Tăng Kỳ Vọng</th>
          <th class="num">ROI</th>
        </tr>
      </thead>
      <tbody>
        ${opt.top_targets
          .slice(0, 35)
          .map(
            (t) => `
          <tr>
            <td>
              <strong>${escapeHtml(t.customer_id)}</strong> — ${escapeHtml(t.customer_name)}
              <div class="muted-sm">${escapeHtml(t.phone_masked)} • ${escapeHtml(t.city)}</div>
            </td>
            <td>
              <span class="badge badge-warn">${escapeHtml(t.segment_name)}</span>
              <span class="muted-sm">(${escapeHtml(t.rfm_code)})</span>
            </td>
            <td class="num">${t.recency_days} ngày</td>
            <td class="num">${formatVND(t.historical_profit)}</td>
            <td>${escapeHtml(t.campaign_action)}</td>
            <td class="num">${formatVND(t.budget_cost)}</td>
            <td class="num text-emerald"><strong>+${formatVND(t.expected_inc_profit)}</strong></td>
            <td class="num text-cyan"><strong>${t.roi_multiple}x</strong></td>
          </tr>
        `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

// ============================================================================
// TAB 3: SMART INVENTORY ABC-XYZ & REPLENISHMENT
// ============================================================================
async function loadInventoryTab() {
  const data = await apiGet(`/api/inventory?dataset_id=${encodeURIComponent(state.currentDatasetId)}`);
  state.inventoryData = data;
  state.abcSelectedCell = null;
  document.getElementById("clearAbcFilterBtn").classList.add("hidden");

  const s = data.summary;
  document.getElementById("invSummaryGrid").innerHTML = `
    <div class="kpi-card">
      <span class="kpi-label">Tổng Vốn Nằm Trong Kho</span>
      <div class="kpi-value">${formatCompactVND(s.total_stock_value_vnd)}</div>
      <span class="kpi-sub">Trên tổng số ${s.total_skus} mã SKU</span>
    </div>
    <div class="kpi-card ${s.stockout_risk_skus > 0 ? "highlight-loss" : ""}">
      <span class="kpi-label">Cảnh Báo Nguy Cơ Đứt Hàng</span>
      <div class="kpi-value ${s.stockout_risk_skus > 0 ? "text-rose" : "text-emerald"}">${s.stockout_risk_skus} SKU</div>
      <span class="kpi-sub">Số ngày đủ bán (DOI) &lt; Thời gian chờ nhập</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-label">Vốn Chôn Ở Hàng Tồn Chậm</span>
      <div class="kpi-value text-amber">${formatCompactVND(s.dead_stock_value_vnd)}</div>
      <span class="kpi-sub">Chiếm <strong>${s.dead_stock_share_pct}%</strong> tổng giá trị kho</span>
    </div>
    <div class="kpi-card highlight-profit">
      <span class="kpi-label">Ngân Sách Đề Xuất Nhập Hàng</span>
      <div class="kpi-value text-cyan">${formatCompactVND(s.total_reorder_budget_vnd)}</div>
      <span class="kpi-sub">Đảm bảo mức phục vụ Safety Stock 95%</span>
    </div>
  `;

  renderAbcXyzMatrix();
  renderInventoryTable();
}

function renderAbcXyzMatrix() {
  const matrix = state.inventoryData.matrix;
  const cellsOrder = ["AX", "AY", "AZ", "BX", "BY", "BZ", "CX", "CY", "CZ"];
  const cellTint = {
    AX: "rgba(16, 185, 129, 0.16)",
    AY: "rgba(16, 185, 129, 0.10)",
    AZ: "rgba(245, 158, 11, 0.14)",
    BX: "rgba(6, 182, 212, 0.12)",
    BY: "rgba(99, 102, 241, 0.10)",
    BZ: "rgba(245, 158, 11, 0.10)",
    CX: "rgba(148, 163, 184, 0.08)",
    CY: "rgba(148, 163, 184, 0.10)",
    CZ: "rgba(244, 63, 94, 0.16)",
  };

  document.getElementById("abcXyzMatrix").innerHTML = cellsOrder
    .map((key) => {
      const c = matrix[key] || { sku_count: 0, stock_value: 0 };
      const selected = state.abcSelectedCell === key ? "selected" : "";
      return `
        <div class="abc-cell ${selected}" data-cell="${key}" style="background:${cellTint[key]}">
          <div class="abc-cell-title">
            <span>${key}</span>
            <span class="text-cyan">${c.sku_count} SKU</span>
          </div>
          <div class="abc-cell-val">Vốn: ${formatCompactVND(c.stock_value)}</div>
        </div>
      `;
    })
    .join("");

  document.querySelectorAll(".abc-cell").forEach((el) => {
    el.addEventListener("click", () => {
      const cell = el.dataset.cell;
      state.abcSelectedCell = state.abcSelectedCell === cell ? null : cell;
      document.getElementById("clearAbcFilterBtn").classList.toggle("hidden", !state.abcSelectedCell);
      renderAbcXyzMatrix();
      renderInventoryTable();
    });
  });
}

function renderInventoryTable() {
  const items = state.inventoryData.items.filter(
    (it) => !state.abcSelectedCell || it.abc_xyz === state.abcSelectedCell
  );

  const stCls = (st) => {
    if (st === "STOCKOUT_RISK") return "badge badge-bleeder";
    if (st === "REORDER_SOON") return "badge badge-warn";
    if (st === "OVERSTOCK_DEAD") return "badge badge-niche";
    return "badge badge-star";
  };

  document.getElementById("inventoryTableWrap").innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Mã SKU &amp; Sản Phẩm</th>
          <th>Hạng</th>
          <th class="num">Tồn Kho</th>
          <th class="num">Bán/Ngày</th>
          <th class="num">Safety Stock</th>
          <th class="num">Điểm ROP</th>
          <th class="num">Đủ Bán (DOI)</th>
          <th class="num">Vốn Tồn Kho</th>
          <th class="num">Đề Xuất Nhập</th>
          <th>Trạng Thái &amp; Hành Động</th>
        </tr>
      </thead>
      <tbody>
        ${items
          .map(
            (it) => `
          <tr>
            <td>
              <strong>${escapeHtml(it.sku_code)}</strong>
              <div class="muted-sm">${escapeHtml(it.product_name)}</div>
            </td>
            <td><span class="badge badge-cow">${it.abc_xyz}</span></td>
            <td class="num"><strong>${fmtInt.format(it.current_stock)}</strong></td>
            <td class="num">${it.avg_daily_demand}</td>
            <td class="num">${fmtInt.format(it.safety_stock)}</td>
            <td class="num">${fmtInt.format(it.reorder_point)}</td>
            <td class="num ${it.days_of_inventory < it.lead_time_days ? "text-rose" : ""}">
              <strong>${it.days_of_inventory >= 900 ? "999+" : it.days_of_inventory} ngày</strong>
              <div class="muted-sm">LT: ${it.lead_time_days} ngày</div>
            </td>
            <td class="num">${formatCompactVND(it.stock_value_vnd)}</td>
            <td class="num ${it.suggested_order_qty > 0 ? "text-cyan" : "muted-sm"}">
              ${it.suggested_order_qty > 0 ? `<strong>+${fmtInt.format(it.suggested_order_qty)} SP</strong><div class="muted-sm">${formatCompactVND(it.reorder_budget_vnd)}</div>` : "—"}
            </td>
            <td>
              <span class="${stCls(it.status)}">${escapeHtml(it.status_label)}</span>
              <div class="muted-sm" style="margin-top:3px">${escapeHtml(it.action_text)}</div>
            </td>
          </tr>
        `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

// ============================================================================
// TAB 4: WHAT-IF ELASTIC PRICING & BREAK-EVEN SIMULATOR
// ============================================================================
let simTimer = null;
function scheduleSimulation() {
  updateSliderLabels();
  clearTimeout(simTimer);
  simTimer = setTimeout(runSimulation, 120);
}

function updateSliderLabels() {
  const fmtSigned = (v, unit) => `${Number(v) > 0 ? "+" : ""}${v}${unit}`;
  document.getElementById("valPriceChg").textContent = fmtSigned(document.getElementById("simPriceChg").value, "%");
  document.getElementById("valVoucherChg").textContent = fmtSigned(document.getElementById("simVoucherChg").value, " pt");
  document.getElementById("valFeeChg").textContent = fmtSigned(document.getElementById("simFeeChg").value, " pt");
  document.getElementById("valReturnChg").textContent = fmtSigned(document.getElementById("simReturnChg").value, " pt");
  document.getElementById("valCogsChg").textContent = fmtSigned(document.getElementById("simCogsChg").value, "%");
  document.getElementById("valAdsChg").textContent = fmtSigned(document.getElementById("simAdsChg").value, "%");

  const useCustomEl = document.getElementById("useCustomElasticity").checked;
  document.getElementById("valElasticity").textContent = useCustomEl
    ? document.getElementById("simElasticity").value
    : "Mặc định SKU";
}

async function runSimulation() {
  updateSliderLabels();
  const useCustomEl = document.getElementById("useCustomElasticity").checked;
  const payload = {
    dataset_id: state.currentDatasetId,
    sku_code: document.getElementById("simSkuSelect").value,
    channel: document.getElementById("simChannelSelect").value,
    price_change_pct: Number(document.getElementById("simPriceChg").value),
    voucher_change_pts: Number(document.getElementById("simVoucherChg").value),
    platform_fee_change_pts: Number(document.getElementById("simFeeChg").value),
    return_rate_change_pts: Number(document.getElementById("simReturnChg").value),
    cogs_change_pct: Number(document.getElementById("simCogsChg").value),
    ads_change_pct: Number(document.getElementById("simAdsChg").value),
    elasticity_override: useCustomEl ? Number(document.getElementById("simElasticity").value) : null,
  };

  const res = await apiPost("/api/simulate", payload);
  const b = res.baseline;
  const s = res.simulated;
  const opt = res.optimal_price_suggestion;

  const alertEl = document.getElementById("simAlertBanner");
  if (res.negative_unit_margin) {
    alertEl.classList.remove("hidden");
    alertEl.innerHTML = `🚨 <strong>BÁO ĐỘNG BẪY LỖ ĐƠN VỊ:</strong> Lãi đóng góp trên mỗi sản phẩm bán ra đang ÂM (${formatVND(
      s.unit_contribution
    )}/SP). Ở cấu hình giá/voucher/phí này, <strong>càng chạy Ads bán nhiều đơn công ty càng lỗ nặng!</strong>`;
  } else {
    alertEl.classList.add("hidden");
  }

  const deltaSign = s.profit_delta >= 0 ? "+" : "";
  const reqVolTxt =
    s.required_vol_change_for_same_profit_pct !== null
      ? `${s.required_vol_change_for_same_profit_pct > 0 ? "+" : ""}${s.required_vol_change_for_same_profit_pct}% SL`
      : "Không thể hòa vốn";

  document.getElementById("simComparisonCards").innerHTML = `
    <div class="kpi-card ${s.profit_delta >= 0 ? "highlight-profit" : "highlight-loss"}">
      <span class="kpi-label">Lãi Ròng Kịch Bản Mới</span>
      <div class="kpi-value ${s.net_profit >= 0 ? "text-emerald" : "text-rose"}">${formatCompactVND(s.net_profit)}</div>
      <span class="kpi-sub">Chênh lệch: <strong>${deltaSign}${formatVND(s.profit_delta)}</strong> (Biên: ${s.net_margin_pct}%)</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-label">Lãi Đóng Góp / 1 Đơn Vị SP</span>
      <div class="kpi-value ${s.unit_contribution > 0 ? "text-cyan" : "text-rose"}">${formatVND(s.unit_contribution)}</div>
      <span class="kpi-sub">Hiện tại: ${formatVND(b.unit_contribution)} • Độ co giãn ε = ${res.elasticity_used}</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-label">Ngưỡng Hòa Vốn &amp; Giữ Lãi</span>
      <div class="kpi-value">${s.breakeven_units !== null ? `${fmtInt.format(s.breakeven_units)} SP` : "Vô nghiệm"}</div>
      <span class="kpi-sub">Cần đạt <strong>${reqVolTxt}</strong> để giữ nguyên mức lãi cũ</span>
    </div>
  `;

  renderSensitivityCurveSvg("simCurveChart", res.sensitivity_curve, payload.price_change_pct, opt);

  document.getElementById("simDetailTable").innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Chỉ Số Kinh Tế Đơn Vị (Unit Economics)</th>
          <th class="num">Hiện Tại (Baseline)</th>
          <th class="num">Kịch Bản Mô Phỏng</th>
          <th class="num">Thay Đổi</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Sản lượng bán dự kiến (Units)</td>
          <td class="num">${fmtInt.format(b.units)} SP</td>
          <td class="num"><strong>${fmtInt.format(s.units)} SP</strong></td>
          <td class="num ${s.units_change_pct >= 0 ? "text-emerald" : "text-amber"}">${s.units_change_pct > 0 ? "+" : ""}${s.units_change_pct}%</td>
        </tr>
        <tr>
          <td>Giá thực thu bình quân / 1 SP (sau Voucher)</td>
          <td class="num">${formatVND(b.unit_net_price)}</td>
          <td class="num">${formatVND(s.unit_net_price)}</td>
          <td class="num">${formatVND(s.unit_net_price - b.unit_net_price)}</td>
        </tr>
        <tr>
          <td>Lãi gộp đóng góp / 1 SP (trước Ads)</td>
          <td class="num">${formatVND(b.unit_contribution)}</td>
          <td class="num ${s.unit_contribution >= 0 ? "text-emerald" : "text-rose"}"><strong>${formatVND(s.unit_contribution)}</strong></td>
          <td class="num">${formatVND(s.unit_contribution - b.unit_contribution)}</td>
        </tr>
        <tr>
          <td>Tổng Doanh Thu Thuần</td>
          <td class="num">${formatVND(b.net_revenue)}</td>
          <td class="num">${formatVND(s.net_revenue)}</td>
          <td class="num">${formatVND(s.net_revenue - b.net_revenue)}</td>
        </tr>
        <tr>
          <td><strong>Tổng Lãi Ròng Thực Tế (Sau Ads)</strong></td>
          <td class="num"><strong>${formatVND(b.net_profit)}</strong></td>
          <td class="num ${s.net_profit >= 0 ? "text-emerald" : "text-rose"}"><strong>${formatVND(s.net_profit)}</strong></td>
          <td class="num ${s.profit_delta >= 0 ? "text-emerald" : "text-rose"}"><strong>${deltaSign}${formatVND(s.profit_delta)}</strong></td>
        </tr>
      </tbody>
    </table>
  `;
}

function renderSensitivityCurveSvg(containerId, curve, activePriceChg, optPoint) {
  const el = document.getElementById(containerId);
  const W = 740;
  const H = 265;
  const padL = 62;
  const padR = 28;
  const padT = 28;
  const padB = 40;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const minX = curve[0].price_change_pct;
  const maxX = curve[curve.length - 1].price_change_pct;
  const vals = curve.map((c) => c.net_profit);
  const maxY = Math.max(...vals, 0) + Math.abs(Math.max(...vals, 1)) * 0.14;
  const minY = Math.min(...vals, 0) - Math.abs(Math.max(...vals, 1)) * 0.08;
  const spanY = maxY - minY || 1;

  const xScale = (x) => padL + ((x - minX) / (maxX - minX)) * plotW;
  const yScale = (y) => padT + ((maxY - y) / spanY) * plotH;
  const zeroY = yScale(0);

  const pts = curve.map((c) => `${xScale(c.price_change_pct)},${yScale(c.net_profit)}`).join(" ");
  const optX = xScale(optPoint.price_change_pct);
  const optY = yScale(optPoint.net_profit);

  const circles = curve
    .map((c) => {
      const cx = xScale(c.price_change_pct);
      const cy = yScale(c.net_profit);
      const isZero = Math.abs(c.price_change_pct) < 0.01;
      const tip = `Giá ${c.price_change_pct > 0 ? "+" : ""}${c.price_change_pct}% ➔ SL: ${fmtInt.format(
        c.units
      )} SP • Lãi ròng: <strong>${formatVND(c.net_profit)}</strong>`;
      return `<circle class="curve-pt" data-tip="${escapeHtml(tip)}" cx="${cx}" cy="${cy}" r="${
        isZero ? 5 : 3.5
      }" fill="${isZero ? "#f8fafc" : "#38bdf8"}" />`;
    })
    .join("");

  const xTicks = [-20, -10, 0, 10, 20, 25]
    .map(
      (xv) =>
        `<text x="${xScale(xv)}" y="${H - 12}" text-anchor="middle" fill="#94a3b8" font-size="11">${
          xv > 0 ? `+${xv}%` : `${xv}%`
        }</text>`
    )
    .join("");

  el.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" width="100%" height="265">
      <line x1="${padL}" y1="${zeroY}" x2="${W - padR}" y2="${zeroY}" stroke="#475569" stroke-dasharray="3,3" />
      <text x="${padL - 8}" y="${zeroY + 4}" text-anchor="end" fill="#94a3b8" font-size="10.5">0 đ</text>
      <text x="${padL - 8}" y="${yScale(optPoint.net_profit) + 4}" text-anchor="end" fill="#34d399" font-size="10.5">${formatCompactVND(optPoint.net_profit)}</text>
      <polyline fill="none" stroke="#06b6d4" stroke-width="2.8" points="${pts}" />
      ${circles}
      <circle cx="${optX}" cy="${optY}" r="7" fill="#10b981" stroke="#fff" stroke-width="2" />
      <text x="${optX}" y="${optY - 12}" text-anchor="middle" fill="#6ee7b7" font-size="11" font-weight="700">
        ⭐ Đỉnh tối ưu (${optPoint.price_change_pct > 0 ? "+" : ""}${optPoint.price_change_pct}%: ${formatCompactVND(optPoint.net_profit)})
      </text>
      ${xTicks}
    </svg>
  `;

  el.querySelectorAll(".curve-pt").forEach((pt) => {
    pt.addEventListener("mouseenter", (e) => showTooltip(e, pt.dataset.tip));
    pt.addEventListener("mousemove", moveTooltip);
    pt.addEventListener("mouseleave", hideTooltip);
  });
}

// ============================================================================
// TAB 5: PREDICTIVE 30D FORECAST, SCIPY HYPOTHESIS TESTS & MARKET BASKET LIFT
// ============================================================================
async function loadPredictiveTab() {
  const chan = document.getElementById("channelFilter").value;
  const qs = new URLSearchParams({
    dataset_id: state.currentDatasetId,
    channel: chan,
  });
  const data = await apiGet(`/api/predictive?${qs.toString()}`);
  const fc = data.forecast_30d;

  if (fc && fc.available) {
    const s = fc.summary_30d;
    document.getElementById("forecastModelBadge").textContent = `Độ chính xác Backtest: ${fc.backtest_accuracy_pct}% (WAPE ${fc.backtest_wape_pct}%)`;
    document.getElementById("predKpiGrid").innerHTML = `
      <div class="kpi-card">
        <span class="kpi-label">Doanh Thu Dự Báo 30 Ngày (P50)</span>
        <div class="kpi-value text-cyan">${formatCompactVND(s.rev_p50)}</div>
        <span class="kpi-sub">Dải P10–P90: ${formatCompactVND(s.rev_p10)} ➔ ${formatCompactVND(s.rev_p90)}</span>
      </div>
      <div class="kpi-card highlight-profit">
        <span class="kpi-label">Lãi Ròng Dự Báo 30 Ngày (P50)</span>
        <div class="kpi-value text-emerald">${formatCompactVND(s.profit_p50)}</div>
        <span class="kpi-sub">Thận trọng P10: ${formatCompactVND(s.profit_p10)} • Lạc quan P90: ${formatCompactVND(s.profit_p90)}</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Vốn Lưu Động Cần Chuẩn Bị</span>
        <div class="kpi-value text-amber">${formatCompactVND(s.working_capital_needed)}</div>
        <span class="kpi-sub">Cho Giá vốn nhập hàng + Bao bì + Ngân sách Ads (~${fmtInt.format(s.expected_orders)} đơn)</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Độ Tin Cậy Mô Hình (Holdout 21N)</span>
        <div class="kpi-value text-emerald">${fc.backtest_accuracy_pct}%</div>
        <span class="kpi-sub">Sai số WAPE: ${fc.backtest_wape_pct}% • Hệ số bùng nổ Sale: ${fc.promo_surge_multiplier}x</span>
      </div>
    `;
    renderForecastFanSvg("forecastFanChart", fc.history_tail, fc.forecast);
  } else {
    document.getElementById("predKpiGrid").innerHTML = "";
    document.getElementById("forecastFanChart").innerHTML = `<div class="muted-sm">${escapeHtml(fc?.message || "Không đủ dữ liệu chuỗi thời gian.")}</div>`;
  }

  // Render SciPy Statistical Hypothesis Tests
  const testsWrap = document.getElementById("hypothesisTestsWrap");
  testsWrap.innerHTML = (data.hypothesis_tests || [])
    .map(
      (t) => `
      <div class="stat-test-card">
        <div class="stat-test-head">
          <span class="stat-test-title">${escapeHtml(t.test_name)}</span>
          <span class="badge ${t.significant ? "badge-star" : "badge-niche"}">
            p = ${t.p_value < 0.0001 ? "< 0.0001" : t.p_value} • ${escapeHtml(t.verdict)}
          </span>
        </div>
        <div class="muted-sm">${escapeHtml(t.null_hypothesis)}</div>
        <div class="stat-meta-row">
          <span>Chỉ số: ${escapeHtml(t.statistic_label)}</span>
          <span>|</span>
          <span>${escapeHtml(t.metric_compared)}</span>
        </div>
        <div class="stat-conclusion">💡 <strong>Kết luận DA:</strong> ${escapeHtml(t.business_conclusion)}</div>
      </div>
    `
    )
    .join("");

  // Render SPC Z-Score Anomalies
  const anomWrap = document.getElementById("anomaliesListWrap");
  const anoms = data.anomalies || [];
  anomWrap.innerHTML = anoms.length
    ? anoms
        .slice(0, 5)
        .map(
          (a) => `
        <div class="stat-test-card">
          <div class="stat-test-head">
            <span class="stat-test-title">${escapeHtml(a.subject)} — ${escapeHtml(a.category)}</span>
            <span class="badge ${a.severity === "HIGH" ? "badge-bleeder" : "badge-warn"}">Z-Score = +${a.z_score}σ</span>
          </div>
          <div class="stat-meta-row"><span>${escapeHtml(a.metric_detail)}</span></div>
          <div class="stat-conclusion">🛠️ <strong>Hành động:</strong> ${escapeHtml(a.recommended_action)}</div>
        </div>
      `
        )
        .join("")
    : `<div class="muted-sm">Không phát hiện điểm dị biệt vượt ngưỡng 2.3σ.</div>`;

  // Render Market Basket Association Rules & Bundle Profit Rescue Table
  const mbWrap = document.getElementById("marketBasketTableWrap");
  const bundles = data.market_basket_bundles || [];
  mbWrap.innerHTML = bundles.length
    ? `
    <table class="data-table">
      <thead>
        <tr>
          <th>Cặp Sản Phẩm Gợi Ý Ghép Combo (A + B)</th>
          <th>Chiến Lược</th>
          <th class="num">Đơn Chung</th>
          <th class="num">Conf (A➔B)</th>
          <th class="num">Hệ Số Lift</th>
          <th class="num">Giá Bán Combo (-8%)</th>
          <th class="num">Lãi Cũ (2 Đơn Rời)</th>
          <th class="num">Lãi Combo (1 Kiện)</th>
          <th class="num">Lãi Tăng Thêm</th>
        </tr>
      </thead>
      <tbody>
        ${bundles
          .map(
            (b) => `
          <tr>
            <td>
              <div><strong>A: ${escapeHtml(b.trigger_sku)}</strong> — ${escapeHtml(b.trigger_name)} <span class="${b.trigger_unit_profit < 0 ? "text-rose" : "muted-sm"}">(${formatVND(b.trigger_unit_profit)}/SP)</span></div>
              <div style="margin-top:2px"><strong>B: ${escapeHtml(b.partner_sku)}</strong> — ${escapeHtml(b.partner_name)} <span class="text-emerald">(+${formatVND(b.partner_unit_profit)}/SP)</span></div>
            </td>
            <td><span class="badge ${b.is_bleeder_rescue ? "badge-bleeder" : "badge-cow"}">${escapeHtml(b.strategy_tag)}</span></td>
            <td class="num">${fmtInt.format(b.co_orders)} đơn</td>
            <td class="num">${b.confidence_pct}%</td>
            <td class="num text-cyan"><strong>${b.lift}x</strong></td>
            <td class="num">
              <strong>${formatVND(b.suggested_bundle_price)}</strong>
              <div class="muted-sm">Gốc: ${formatVND(b.combined_list_price)}</div>
            </td>
            <td class="num ${b.standalone_profit < 0 ? "text-rose" : ""}">${formatVND(b.standalone_profit)}</td>
            <td class="num text-emerald">
              <strong>${formatVND(b.bundle_net_profit)}</strong>
              <div class="muted-sm">Biên: ${b.bundle_margin_pct}%</div>
            </td>
            <td class="num text-emerald"><strong>+${formatVND(b.profit_uplift_vnd)}</strong></td>
          </tr>
        `
          )
          .join("")}
      </tbody>
    </table>
  `
    : `<div class="muted-sm">Chưa đủ đơn hàng đa sản phẩm để tính hệ số kết hợp Lift.</div>`;
}

function renderForecastFanSvg(containerId, hist, fc) {
  const el = document.getElementById(containerId);
  const totalLen = hist.length + fc.length;
  const W = 1080;
  const H = 290;
  const padL = 62;
  const padR = 24;
  const padT = 26;
  const padB = 42;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const allMax = Math.max(
    ...hist.map((h) => h.net_revenue),
    ...fc.map((f) => f.rev_p90),
    1
  ) * 1.12;

  const xScale = (idx) => padL + (idx / Math.max(1, totalLen - 1)) * plotW;
  const yScale = (v) => padT + ((allMax - v) / allMax) * plotH;
  const zeroY = yScale(0);

  let grid = "";
  for (let i = 0; i <= 4; i++) {
    const gv = (allMax * i) / 4;
    const gy = yScale(gv);
    grid += `
      <line x1="${padL}" y1="${gy}" x2="${W - padR}" y2="${gy}" stroke="#1e293b" stroke-dasharray="3,3" />
      <text x="${padL - 8}" y="${gy + 4}" text-anchor="end" fill="#64748b" font-size="10.5">${formatCompactVND(gv)}</text>
    `;
  }

  const histPts = hist.map((h, i) => `${xScale(i)},${yScale(h.net_revenue)}`).join(" ");
  const splitIdx = hist.length - 1;
  const splitX = xScale(splitIdx);
  const lastHistPt = hist[hist.length - 1];

  // Build Fan Polygon (P90 upper -> reversed P10 lower) anchored from last historical point
  const upperPts = [`${splitX},${yScale(lastHistPt.net_revenue)}`];
  const lowerPts = [`${splitX},${yScale(lastHistPt.net_revenue)}`];
  const p50Pts = [`${splitX},${yScale(lastHistPt.net_revenue)}`];

  fc.forEach((f, j) => {
    const x = xScale(hist.length + j);
    upperPts.push(`${x},${yScale(f.rev_p90)}`);
    lowerPts.unshift(`${x},${yScale(f.rev_p10)}`);
    p50Pts.push(`${x},${yScale(f.rev_p50)}`);
  });

  const fanPolygon = [...upperPts, ...lowerPts].join(" ");

  const interactiveDots = [
    ...hist.map((h, i) => ({
      x: xScale(i),
      y: yScale(h.net_revenue),
      promo: h.is_promo,
      isFc: false,
      date: h.date,
      tip: `<strong>Lịch sử ${escapeHtml(h.date)}</strong>${h.is_promo ? " 🔥 Sale" : ""}<br/>• Doanh thu thuần: <strong>${formatVND(h.net_revenue)}</strong><br/>• Lãi ròng: <strong class="text-emerald">${formatVND(h.net_profit)}</strong>`,
    })),
    ...fc.map((f, j) => ({
      x: xScale(hist.length + j),
      y: yScale(f.rev_p50),
      promo: f.is_promo,
      isFc: true,
      date: f.date,
      tip: `<strong>Dự báo ${escapeHtml(f.date)}</strong>${f.is_promo ? " 🚀 Kỳ vọng Ngày Đôi!" : ""}<br/>• Doanh thu P50: <strong>${formatVND(f.rev_p50)}</strong><br/>• Dải P10–P90: ${formatCompactVND(f.rev_p10)} ➔ ${formatCompactVND(f.rev_p90)}<br/>• Lãi ròng dự kiến: <strong class="text-emerald">${formatVND(f.profit_p50)}</strong>`,
    })),
  ];

  const dotsSvg = interactiveDots
    .map(
      (d) => `
      <circle class="fc-pt" data-tip="${escapeHtml(d.tip)}" cx="${d.x}" cy="${d.y}" r="${
        d.promo ? 5.2 : 3
      }" fill="${d.promo ? "#f59e0b" : d.isFc ? "#38bdf8" : "#818cf8"}" />
    `
    )
    .join("");

  const dateLabels = interactiveDots
    .filter((_, idx) => idx % 8 === 0 || idx === interactiveDots.length - 1)
    .map(
      (d) =>
        `<text x="${d.x}" y="${H - 12}" text-anchor="middle" fill="#94a3b8" font-size="10.5">${escapeHtml(
          d.date.slice(5)
        )}</text>`
    )
    .join("");

  el.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" width="100%" height="290">
      ${grid}
      <line x1="${padL}" y1="${zeroY}" x2="${W - padR}" y2="${zeroY}" stroke="#475569" />
      <polygon points="${fanPolygon}" fill="rgba(6, 182, 212, 0.17)" />
      <line x1="${splitX}" y1="${padT}" x2="${splitX}" y2="${zeroY}" stroke="#f59e0b" stroke-dasharray="4,4" />
      <text x="${splitX + 6}" y="${padT + 12}" fill="#fbbf24" font-size="10.5" font-weight="700">Bắt đầu Dự báo 30 ngày ➔</text>
      <polyline fill="none" stroke="#818cf8" stroke-width="2.4" points="${histPts}" />
      <polyline fill="none" stroke="#06b6d4" stroke-width="2.5" stroke-dasharray="5,3" points="${p50Pts.join(" ")}" />
      ${dotsSvg}
      ${dateLabels}
      <g transform="translate(${padL + 10}, 12)" font-size="11" fill="#cbd5e1">
        <line x1="0" y1="-4" x2="18" y2="-4" stroke="#818cf8" stroke-width="2.5" />
        <text x="23" y="0">28 Ngày Thực Tế</text>
        <line x1="130" y1="-4" x2="148" y2="-4" stroke="#06b6d4" stroke-width="2.5" stroke-dasharray="4,2" />
        <text x="153" y="0">Dự Báo P50</text>
        <rect x="235" y="-9" width="12" height="10" fill="rgba(6, 182, 212, 0.35)" />
        <text x="252" y="0">Dải Tin Cậy P10–P90</text>
        <circle cx="385" cy="-4" r="4.5" fill="#f59e0b" />
        <text x="394" y="0">Ngày Đôi / Sale Lớn</text>
      </g>
    </svg>
  `;

  el.querySelectorAll(".fc-pt").forEach((pt) => {
    pt.addEventListener("mouseenter", (e) => showTooltip(e, pt.dataset.tip));
    pt.addEventListener("mousemove", moveTooltip);
    pt.addEventListener("mouseleave", hideTooltip);
  });
}

// ============================================================================
// TAB 6: LIVE SQL ANALYTICS WORKBENCH
// ============================================================================
async function loadSqlWorkbench() {
  const data = await apiGet(`/api/sql/workbench?dataset_id=${encodeURIComponent(state.currentDatasetId)}`);
  state.sqlWorkbench = data;

  const tplList = document.getElementById("sqlTemplateList");
  tplList.innerHTML = data.templates
    .map(
      (t, idx) => `
      <div class="tpl-item ${idx === 0 ? "active" : ""}" data-idx="${idx}">
        <div class="tpl-title">${escapeHtml(t.title)}</div>
        <div class="tpl-tags">
          ${t.skill_tags.map((tg) => `<span class="tpl-tag">${escapeHtml(tg)}</span>`).join("")}
        </div>
      </div>
    `
    )
    .join("");

  tplList.querySelectorAll(".tpl-item").forEach((el) => {
    el.addEventListener("click", () => {
      tplList.querySelectorAll(".tpl-item").forEach((n) => n.classList.remove("active"));
      el.classList.add("active");
      selectSqlTemplate(Number(el.dataset.idx));
    });
  });

  document.getElementById("sqlSchemaAccordion").innerHTML = data.schema
    .map(
      (tbl) => `
      <div class="schema-table-box">
        <div class="schema-table-head">
          <span>${escapeHtml(tbl.name)} <small class="muted-sm">(${tbl.type})</small></span>
          <span class="muted-sm">${fmtInt.format(tbl.row_count)} dòng</span>
        </div>
        <div class="schema-cols">
          ${tbl.columns.map((c) => `<span>${escapeHtml(c.name)}</span>`).join(" • ")}
        </div>
      </div>
    `
    )
    .join("");

  if (data.templates.length > 0) {
    await selectSqlTemplate(0);
  }
}

async function selectSqlTemplate(idx) {
  const tpl = state.sqlWorkbench.templates[idx];
  if (!tpl) return;
  document.getElementById("activeSqlTitle").textContent = tpl.title;
  document.getElementById("activeSqlQuestion").textContent = `Bài toán: ${tpl.business_question}`;
  document.getElementById("sqlEditor").value = tpl.sql;
  await executeCurrentSql();
}

async function executeCurrentSql() {
  const sql = document.getElementById("sqlEditor").value;
  const statusEl = document.getElementById("sqlStatusBar");
  const wrap = document.getElementById("sqlResultWrap");
  statusEl.innerHTML = `<span>⏳ Đang thực thi truy vấn SQL...</span>`;

  try {
    const res = await apiPost("/api/sql/execute", { sql, max_rows: 300 });
    state.lastSqlResult = res;
    statusEl.innerHTML = `
      <span class="text-emerald">✔ Thực thi thành công: <strong>${res.row_count} dòng</strong>${
      res.truncated ? ` (đã giới hạn ${res.max_rows} dòng)` : ""
    }</span>
      <span>⏱ Thời gian: <strong>${res.elapsed_ms} ms</strong></span>
    `;

    if (!res.columns.length || !res.rows.length) {
      wrap.innerHTML = `<div class="muted-sm">Truy vấn trả về 0 dòng dữ liệu.</div>`;
      return;
    }

    wrap.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            ${res.columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}
          </tr>
        </thead>
        <tbody>
          ${res.rows
            .map(
              (row) => `
            <tr>
              ${res.columns
                .map((col) => {
                  const val = row[col];
                  const isNum = typeof val === "number" && !col.includes("id") && !col.includes("year");
                  const formatted = isNum
                    ? Number.isInteger(val)
                      ? fmtInt.format(val)
                      : fmtDec.format(val)
                    : escapeHtml(val ?? "NULL");
                  const cls = isNum ? (val < 0 ? "num text-rose" : "num") : "";
                  return `<td class="${cls}">${formatted}</td>`;
                })
                .join("")}
            </tr>
          `
            )
            .join("")}
        </tbody>
      </table>
    `;
  } catch (err) {
    statusEl.innerHTML = `<span class="text-rose">✖ ${escapeHtml(err.message)}</span>`;
  }
}

// ============================================================================
// CSV DOWNLOAD HELPER (UTF-8 WITH BOM FOR VIETNAMESE EXCEL)
// ============================================================================
function downloadCsv(filename, columns, rows) {
  const escCsv = (v) => {
    const s = String(v ?? "");
    if (s.includes(",") || s.includes('"') || s.includes("\n")) {
      return `"${s.replace(/"/g, '""')}"`;
    }
    return s;
  };
  const lines = [
    columns.map(escCsv).join(","),
    ...rows.map((r) => columns.map((c) => escCsv(r[c])).join(",")),
  ];
  const blob = new Blob(["\uFEFF" + lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ============================================================================
// TAB SWITCHING & GLOBAL EVENT LISTENERS
// ============================================================================
function switchTab(tabId) {
  state.activeTab = tabId;
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabId));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === tabId));
  refreshActiveTab();
}

document.addEventListener("DOMContentLoaded", async () => {
  // Tabs
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  // Dataset change
  document.getElementById("datasetSelect").addEventListener("change", async (e) => {
    state.currentDatasetId = e.target.value;
    applyDatasetMetadata();
    await refreshActiveTab();
  });

  // Delete custom dataset
  document.getElementById("deleteDatasetBtn").addEventListener("click", async () => {
    if (!confirm("Bạn có chắc muốn xóa bộ dữ liệu tải lên này khỏi kho SQL?")) return;
    await fetch(`/api/datasets/${encodeURIComponent(state.currentDatasetId)}`, { method: "DELETE" });
    await loadDatasets("vn_fashion_omni");
    await refreshActiveTab();
  });

  // Global filters
  ["channelFilter", "startDateFilter", "endDateFilter"].forEach((id) => {
    document.getElementById(id).addEventListener("change", () => {
      if (state.activeTab === "tab-pnl") loadPnlOverview();
      else if (state.activeTab === "tab-predictive" && id === "channelFilter") loadPredictiveTab();
    });
  });

  document.getElementById("resetFilterBtn").addEventListener("click", () => {
    applyDatasetMetadata();
    refreshActiveTab();
  });

  // Export Executive XLSX
  document.getElementById("exportExecReportBtn").addEventListener("click", () => {
    window.location.href = `/api/export/report.xlsx?dataset_id=${encodeURIComponent(state.currentDatasetId)}`;
  });

  // SKU badge filter pills
  document.querySelectorAll("#skuBadgeFilters .pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      document.querySelectorAll("#skuBadgeFilters .pill").forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      state.skuBadgeFilter = pill.dataset.badge;
      renderSkuPnlTable();
    });
  });

  // RFM Optimizer
  document.getElementById("runOptimizerBtn").addEventListener("click", loadRfmTab);
  document.getElementById("exportTargetCsvBtn").addEventListener("click", () => {
    if (!state.rfmData?.optimizer?.top_targets?.length) return;
    const cols = [
      "customer_id",
      "customer_name",
      "phone_masked",
      "city",
      "segment_name",
      "rfm_code",
      "recency_days",
      "campaign_action",
      "budget_cost",
      "expected_inc_profit",
      "roi_multiple",
    ];
    downloadCsv(`Danh_Sach_Cuu_Khach_${state.currentDatasetId}.csv`, cols, state.rfmData.optimizer.top_targets);
  });

  // Clear ABC cell filter
  document.getElementById("clearAbcFilterBtn").addEventListener("click", () => {
    state.abcSelectedCell = null;
    document.getElementById("clearAbcFilterBtn").classList.add("hidden");
    renderAbcXyzMatrix();
    renderInventoryTable();
  });

  // Simulator controls
  [
    "simSkuSelect",
    "simChannelSelect",
    "simPriceChg",
    "simVoucherChg",
    "simFeeChg",
    "simReturnChg",
    "simCogsChg",
    "simAdsChg",
    "simElasticity",
    "useCustomElasticity",
  ].forEach((id) => {
    document.getElementById(id).addEventListener("input", scheduleSimulation);
    document.getElementById(id).addEventListener("change", scheduleSimulation);
  });

  document.getElementById("resetSimBtn").addEventListener("click", () => {
    ["simPriceChg", "simVoucherChg", "simFeeChg", "simReturnChg", "simCogsChg", "simAdsChg"].forEach((id) => {
      document.getElementById(id).value = "0";
    });
    document.getElementById("useCustomElasticity").checked = false;
    runSimulation();
  });

  // SQL Workbench buttons & shortcut
  document.getElementById("runSqlBtn").addEventListener("click", executeCurrentSql);
  document.getElementById("sqlEditor").addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      executeCurrentSql();
    }
  });
  document.getElementById("exportSqlCsvBtn").addEventListener("click", () => {
    if (!state.lastSqlResult?.rows?.length) return;
    downloadCsv(`SQL_Result_${state.currentDatasetId}.csv`, state.lastSqlResult.columns, state.lastSqlResult.rows);
  });

  // Import Modal
  const modal = document.getElementById("importModal");
  const fileIn = document.getElementById("importFileInput");
  document.getElementById("openImportModalBtn").addEventListener("click", () => {
    document.getElementById("importAuditResult").classList.add("hidden");
    modal.classList.remove("hidden");
  });
  document.getElementById("closeImportModalBtn").addEventListener("click", () => modal.classList.add("hidden"));
  fileIn.addEventListener("change", () => {
    if (fileIn.files[0]) {
      document.getElementById("dropzoneText").innerHTML = `📄 Đã chọn tệp: <strong>${escapeHtml(fileIn.files[0].name)}</strong>`;
    }
  });

  document.getElementById("importForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!fileIn.files[0]) return;
    const btn = document.getElementById("submitImportBtn");
    const auditEl = document.getElementById("importAuditResult");
    btn.disabled = true;
    btn.textContent = "⏳ Đang làm sạch & nạp dữ liệu...";

    try {
      const fd = new FormData();
      fd.append("file", fileIn.files[0]);
      fd.append("dataset_name", document.getElementById("customDatasetName").value);

      const res = await fetch("/api/import", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Lỗi nhập tệp");

      const a = data.audit;
      auditEl.classList.remove("hidden");
      auditEl.innerHTML = `
        <strong>✅ Đã nạp thành công vào kho SQL (${escapeHtml(data.name)})!</strong><br/>
        • Tổng dòng đọc: ${a.raw_rows} ➔ Nạp hợp lệ: <strong>${a.imported_lines} dòng</strong> (${a.unique_orders} đơn, ${a.unique_skus} SKU, ${a.unique_customers} KH)<br/>
        • Tự động làm sạch: <strong>${a.dirty_numbers_cleaned} ô tiền tệ bẩn</strong>, <strong>${a.dirty_dates_standardized} ngày lệch chuẩn</strong>, loại bỏ ${a.duplicates_removed} dòng trùng!
      `;
      await loadDatasets(data.dataset_id);
      await refreshActiveTab();
    } catch (err) {
      alert(err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "🚀 Phân Tích & Nạp Vào Kho SQL";
    }
  });

  // Initial boot
  await loadDatasets();
  await loadPnlOverview();
});
