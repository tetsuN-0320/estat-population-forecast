/**
 * national.js — 全国総人口グラフ（index.html 下部セクション）
 *
 * national.json を読み込み:
 *  1. 統計カード（2020年実績・2050年予測・変化率・社人研比較）
 *  2. Chart.js 折れ線グラフ（1990〜2050年、3モデル＋社人研＋不確実性帯）
 */

"use strict";

const MAN = 10000;  // 万人換算

const NAT_MODEL_CONFIG = {
  cohort:  { label: "コーホート要因法", color: "#e05c2b", dash: [] },
  prophet: { label: "Prophet",          color: "#27ae60", dash: [6, 3] },
  arima:   { label: "ARIMA",            color: "#8e44ad", dash: [3, 3] },
};

const ALL_YEARS  = [1990, 1995, 2000, 2005, 2010, 2015, 2020, 2025, 2030, 2035, 2040, 2045, 2050];
const HIST_YEARS = [1990, 1995, 2000, 2005, 2010, 2015, 2020];
const FORE_YEARS = [2025, 2030, 2035, 2040, 2045, 2050];

fetch("static/data/national.json")
  .then(r => r.json())
  .then(data => {
    renderNationalStats(data);
    renderNationalChart(data);
  })
  .catch(err => console.error("national.json 読み込みエラー:", err));

// ===== 統計カード =====
function renderNationalStats(data) {
  const pop2020 = data.history["2020"]?.total;
  const pop1990 = data.history["1990"]?.total;
  const pop2050c = data.forecast?.cohort?.["2050"]?.total;
  const ipss2050 = data.ipss?.["2050"];   // 社人研（実数）

  const chg9020 = (pop1990 && pop2020)
    ? ((pop2020 / pop1990 - 1) * 100).toFixed(1)
    : null;
  const chg2050 = (pop2020 && pop2050c)
    ? ((pop2050c / pop2020 - 1) * 100).toFixed(1)
    : null;
  const diffIpss = (pop2050c && ipss2050)
    ? (((pop2050c - ipss2050) / ipss2050) * 100).toFixed(1)
    : null;

  const cards = [
    {
      label: "1990年 総人口（実績）",
      value: pop1990 ? (pop1990 / MAN).toFixed(0) + " 万人" : "−",
      sub: "",
      color: "var(--color-primary)",
    },
    {
      label: "2020年 総人口（実績）",
      value: pop2020 ? (pop2020 / MAN).toFixed(0) + " 万人" : "−",
      sub: chg9020 ? `1990年比 ${chg9020 >= 0 ? "+" : ""}${chg9020}%` : "",
      color: "var(--color-primary)",
    },
    {
      label: "2050年 予測人口（コーホート法）",
      value: pop2050c ? (pop2050c / MAN).toFixed(0) + " 万人" : "−",
      sub: chg2050 ? `2020年比 ${chg2050}%` : "",
      color: parseFloat(chg2050) < 0 ? "#922b21" : "var(--color-primary)",
    },
    {
      label: "社人研推計 2050年",
      value: ipss2050 ? (ipss2050 / MAN).toFixed(0) + " 万人" : "−",
      sub: diffIpss !== null ? `本推計との差: ${diffIpss >= 0 ? "+" : ""}${diffIpss}%` : "",
      color: "var(--color-muted)",
    },
  ];

  const container = document.getElementById("national-stats");
  if (!container) return;

  container.innerHTML = cards.map(c => `
    <div class="card" style="padding:.9rem 1rem">
      <div style="font-size:.72rem;color:var(--color-muted);margin-bottom:.25rem;line-height:1.4">${c.label}</div>
      <div style="font-size:1.35rem;font-weight:700;color:${c.color};font-variant-numeric:tabular-nums">${c.value}</div>
      ${c.sub ? `<div style="font-size:.72rem;color:var(--color-muted);margin-top:.2rem">${c.sub}</div>` : ""}
    </div>
  `).join("");
}

// ===== グラフ =====
function renderNationalChart(data) {
  const labels = ALL_YEARS.map(String);

  // 実績（1990〜2020）
  const histSeries = ALL_YEARS.map(y => {
    if (y > 2020) return null;
    const v = data.history[String(y)]?.total;
    return v != null ? +(v / MAN).toFixed(1) : null;
  });

  // 2020年の接続点
  const pop2020_man = data.history["2020"]?.total != null
    ? +(data.history["2020"].total / MAN).toFixed(1)
    : null;

  // モデル予測（2020年を接続点に含める）
  function modelSeries(key) {
    return ALL_YEARS.map(y => {
      if (y < 2020) return null;
      if (y === 2020) return pop2020_man;
      const v = data.forecast[key]?.[String(y)]?.total;
      return v != null ? +(v / MAN).toFixed(1) : null;
    });
  }

  // 社人研推計（2020年接続点 + 2025〜2050）
  const ipssSeries = ALL_YEARS.map(y => {
    if (y < 2020) return null;
    if (y === 2020) return pop2020_man;
    const v = data.ipss?.[String(y)];
    return v != null ? +(v / MAN).toFixed(1) : null;
  });

  // モデル幅（min〜max の帯）
  const bandMin = ALL_YEARS.map(y => {
    if (y < 2020) return null;
    if (y === 2020) return pop2020_man;
    const vals = Object.keys(NAT_MODEL_CONFIG)
      .map(k => data.forecast[k]?.[String(y)]?.total)
      .filter(v => v != null);
    return vals.length ? +(Math.min(...vals) / MAN).toFixed(1) : null;
  });

  const bandMax = ALL_YEARS.map(y => {
    if (y < 2020) return null;
    if (y === 2020) return pop2020_man;
    const vals = Object.keys(NAT_MODEL_CONFIG)
      .map(k => data.forecast[k]?.[String(y)]?.total)
      .filter(v => v != null);
    return vals.length ? +(Math.max(...vals) / MAN).toFixed(1) : null;
  });

  const datasets = [
    // 帯：上限（fill で下限との間を塗る）
    {
      label: "_band_max",
      data: bandMax,
      borderColor: "transparent",
      backgroundColor: "rgba(224,92,43,.13)",
      fill: "+1",
      pointRadius: 0,
      tension: 0.35,
    },
    // 帯：下限
    {
      label: "_band_min",
      data: bandMin,
      borderColor: "transparent",
      backgroundColor: "rgba(224,92,43,.13)",
      fill: false,
      pointRadius: 0,
      tension: 0.35,
    },
    // 実績
    {
      label: "実績値（国勢調査）",
      data: histSeries,
      borderColor: "#1a4a8a",
      backgroundColor: "rgba(26,74,138,.1)",
      borderWidth: 2.5,
      pointRadius: 4,
      pointHoverRadius: 6,
      tension: 0.3,
      fill: false,
    },
    // 各モデル
    ...Object.entries(NAT_MODEL_CONFIG).map(([key, cfg]) => ({
      label: cfg.label,
      data: modelSeries(key),
      borderColor: cfg.color,
      backgroundColor: "transparent",
      borderWidth: 2,
      borderDash: cfg.dash,
      pointRadius: 3,
      pointHoverRadius: 5,
      tension: 0.35,
      fill: false,
    })),
    // 社人研
    {
      label: "社人研推計（令和5年・参考）",
      data: ipssSeries,
      borderColor: "#555",
      backgroundColor: "transparent",
      borderWidth: 1.5,
      borderDash: [8, 4],
      pointRadius: 3,
      pointStyle: "triangle",
      tension: 0.35,
      fill: false,
    },
  ];

  const ctx = document.getElementById("national-chart");
  if (!ctx) return;

  new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: item => {
              if (item.dataset.label.startsWith("_")) return null;
              const v = item.raw;
              if (v == null) return null;
              return ` ${item.dataset.label}: ${v.toFixed(0)} 万人`;
            },
          },
          filter: item => !item.dataset.label.startsWith("_"),
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(0,0,0,.05)" },
          ticks: { font: { size: 11 }, maxTicksLimit: 14 },
        },
        y: {
          grid: { color: "rgba(0,0,0,.05)" },
          ticks: {
            font: { size: 11 },
            callback: v => v.toLocaleString() + " 万",
          },
          title: {
            display: true, text: "万人",
            font: { size: 11 }, color: "#888",
          },
          suggestedMin: 8000,
        },
      },
    },
  });

  // 手動凡例
  const legendWrap = document.getElementById("national-legend");
  if (!legendWrap) return;

  const items = [
    { label: "実績値（国勢調査）",     color: "#1a4a8a", dash: false, band: false },
    { label: "コーホート要因法",        color: "#e05c2b", dash: false, band: false },
    { label: "Prophet",                color: "#27ae60", dash: true,  band: false },
    { label: "ARIMA",                  color: "#8e44ad", dash: true,  band: false },
    { label: "社人研推計（参考）",      color: "#555",    dash: true,  band: false },
    { label: "モデル幅（不確実性）",    color: "rgba(224,92,43,.35)", band: true },
  ];

  legendWrap.innerHTML = items.map(item => `
    <div class="model-legend-item">
      ${item.band
        ? `<span style="width:18px;height:10px;background:${item.color};border-radius:2px;display:inline-block;flex-shrink:0"></span>`
        : `<span style="width:20px;height:0;border-bottom:2.5px ${item.dash ? "dashed" : "solid"} ${item.color};display:inline-block;flex-shrink:0"></span>`
      }
      <span style="font-size:.76rem;white-space:nowrap">${item.label}</span>
    </div>
  `).join("");
}
