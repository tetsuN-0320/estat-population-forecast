/**
 * prefecture.js — 都道府県詳細ページのロジック
 *
 * URL パラメータ: ?code=13 (都道府県コード)
 * ・人口ピラミッド（D3.js）: 年別アニメーション
 * ・時系列グラフ（Chart.js）: 実績 + 3モデル予測 + 社人研推計
 */

"use strict";

// ===== 定数 =====
const ALL_YEARS      = [1990, 1995, 2000, 2005, 2010, 2015, 2020, 2025, 2030, 2035, 2040, 2045, 2050];
const HIST_YEARS     = [1990, 1995, 2000, 2005, 2010, 2015, 2020];
const FORE_YEARS     = [2025, 2030, 2035, 2040, 2045, 2050];
const PYRAMID_YEARS  = [1990, 2000, 2010, 2020, 2030, 2040, 2050];

const MODEL_CONFIG = {
  cohort:  { label: "コーホート要因法", color: "#e05c2b", dash: [] },
  prophet: { label: "Prophet",          color: "#27ae60", dash: [5, 3] },
  arima:   { label: "ARIMA",            color: "#8e44ad", dash: [3, 3] },
};

// 社人研推計（全国）万人
const IPSS_NATIONAL = {
  2025: 12254, 2030: 11913, 2035: 11530,
  2040: 11092, 2045: 10642, 2050: 10469,
};

// ===== URL から都道府県コードを取得 =====
const params   = new URLSearchParams(window.location.search);
// code は "01000" 形式（map.js から渡される）または数値文字列の両方を許容
const rawCode  = params.get("code") || "13000";
// "13" → "13000"、"13000" → そのまま
const prefCode = rawCode.length <= 2
  ? rawCode.padStart(2, "0") + "000"
  : rawCode;

// ===== データ読み込み =====
d3.json("static/data/prefectures.json").then(data => {
  const pref = data.prefectures.find(p => String(p.code) === String(prefCode));
  if (!pref) {
    document.getElementById("pref-name").textContent = "都道府県が見つかりません";
    return;
  }

  // ページタイトル
  document.title = `${pref.name} — 日本の人口動態予測`;
  document.getElementById("pref-name").textContent = pref.name;

  // 変化率バッジ
  const chg = pref.change_pct_2020_2050;
  if (chg !== null) {
    const badge = document.getElementById("pref-change-badge");
    badge.style.cssText = `
      background: ${chg < 0 ? "#fde8e5" : "#e8f4fd"};
      color: ${chg < 0 ? "#c0392b" : "#1a5276"};
      padding: .25rem .7rem; border-radius: 99px; font-size: .85rem; font-weight: 600;
    `;
    badge.textContent = `2020→2050: ${chg >= 0 ? "+" : ""}${chg.toFixed(1)}%（コーホート法）`;
  }

  renderSummaryCards(pref);
  renderPyramidButtons(pref);
  renderPyramid(pref, 2020);
  renderTimeseries(pref);
  renderPrefNav(data.prefectures, String(prefCode));
});

// ===== サマリーカード =====
function renderSummaryCards(pref) {
  const pop2020 = pref.history["2020"]?.total;
  const pop1990 = pref.history["1990"]?.total;
  const pop2050 = pref.forecast?.cohort?.["2050"]?.total;

  const cards = [
    {
      label: "2020年 総人口（実績）",
      value: pop2020 ? (pop2020 / 10000).toFixed(1) + " 万人" : "−",
      sub: "",
    },
    {
      label: "1990→2020年 変化",
      value: (pop1990 && pop2020)
        ? `${((pop2020 / pop1990 - 1) * 100).toFixed(1)}%`
        : "−",
      sub: pop1990 ? pop1990.toLocaleString() + " 人 → " + pop2020.toLocaleString() + " 人" : "",
      color: (pop1990 && pop2020 && pop2020 > pop1990) ? "#1a5276" : "#922b21",
    },
    {
      label: "2050年 予測人口（コーホート）",
      value: pop2050 ? (pop2050 / 10000).toFixed(1) + " 万人" : "−",
      sub: "",
    },
    {
      label: "2020→2050年 変化率",
      value: pref.change_pct_2020_2050 !== null
        ? `${pref.change_pct_2020_2050 >= 0 ? "+" : ""}${pref.change_pct_2020_2050.toFixed(1)}%`
        : "−",
      sub: "コーホート法による推計",
      color: pref.change_pct_2020_2050 < 0 ? "#922b21" : "#1a5276",
    },
  ];

  const container = document.getElementById("summary-cards");
  container.innerHTML = cards.map(c => `
    <div class="card" style="padding:1rem">
      <div style="font-size:.75rem;color:var(--color-muted);margin-bottom:.3rem">${c.label}</div>
      <div style="font-size:1.4rem;font-weight:700;color:${c.color || "var(--color-primary)"}">${c.value}</div>
      ${c.sub ? `<div style="font-size:.72rem;color:var(--color-muted);margin-top:.15rem">${c.sub}</div>` : ""}
    </div>
  `).join("");
}

// ===== ピラミッド年ボタン =====
function renderPyramidButtons(pref) {
  const wrap = document.getElementById("pyramid-year-btns");
  wrap.innerHTML = PYRAMID_YEARS.map(y => `
    <button
      class="pyramid-year-btn ${y === 2020 ? "active" : ""} ${y > 2020 ? "forecast-year" : ""}"
      data-year="${y}"
    >${y}${y > 2020 ? "予" : ""}</button>
  `).join("");

  wrap.querySelectorAll(".pyramid-year-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      wrap.querySelectorAll(".pyramid-year-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      renderPyramid(pref, +btn.dataset.year);
    });
  });
}

// ===== 人口ピラミッド（D3） =====
function renderPyramid(pref, year) {
  const AGE_ORDER = [
    "0-4","5-9","10-14","15-19","20-24","25-29","30-34","35-39",
    "40-44","45-49","50-54","55-59","60-64","65-69","70-74","75-79","80-84","85+",
  ];

  const pyramidData = pref.pyramid?.[String(year)];
  if (!pyramidData) return;

  // SVG サイズ
  const svgEl = document.getElementById("pyramid-svg");
  const totalW = svgEl.clientWidth || 400;
  const margin = { top: 10, right: 20, bottom: 30, left: 40 };
  const W = totalW - margin.left - margin.right;
  const H = 360 - margin.top - margin.bottom;

  d3.select("#pyramid-svg").selectAll("*").remove();
  const svg = d3.select("#pyramid-svg")
    .attr("height", H + margin.top + margin.bottom)
    .append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);

  // データを AGE_ORDER 順に整列（逆順で上が高齢）
  const rows = AGE_ORDER.map(age => {
    const d = pyramidData.find(r => r.age === age) || { male: 0, female: 0 };
    return { age, male: d.male, female: d.female };
  }).reverse();

  // スケール
  const maxVal = d3.max(rows, r => Math.max(r.male, r.female)) || 1;
  const halfW  = W / 2 - 30;  // 中心ラベルのスペース

  const xLeft  = d3.scaleLinear().domain([0, maxVal]).range([0, halfW]);
  const xRight = d3.scaleLinear().domain([0, maxVal]).range([0, halfW]);
  const y = d3.scaleBand().domain(rows.map(r => r.age)).range([0, H]).padding(0.08);
  const cx = W / 2;  // 中心 X

  // 男性（左）
  svg.append("g").selectAll("rect")
    .data(rows).join("rect")
      .attr("x",      r => cx - xLeft(r.male) - 1)
      .attr("y",      r => y(r.age))
      .attr("width",  r => xLeft(r.male))
      .attr("height", y.bandwidth())
      .attr("fill", "#2471a3")
      .attr("opacity", .85);

  // 女性（右）
  svg.append("g").selectAll("rect")
    .data(rows).join("rect")
      .attr("x",      cx + 1)
      .attr("y",      r => y(r.age))
      .attr("width",  r => xRight(r.female))
      .attr("height", y.bandwidth())
      .attr("fill", "#c0392b")
      .attr("opacity", .85);

  // 年齢ラベル（中央）
  svg.append("g").selectAll("text")
    .data(rows).join("text")
      .attr("x", cx)
      .attr("y", r => y(r.age) + y.bandwidth() / 2 + 4)
      .attr("text-anchor", "middle")
      .attr("font-size", "9px")
      .attr("fill", "#555")
      .text(r => r.age);

  // X 軸ラベル（万人単位）
  const fmtK = v => v >= 10000 ? (v / 10000).toFixed(0) + "万" : (v / 1000).toFixed(0) + "千";
  const ticks = [0, Math.round(maxVal * 0.5 / 1000) * 1000, maxVal];

  // 左軸ティック
  svg.append("g").selectAll("text.xtick-left")
    .data(ticks).join("text")
      .attr("x",            v => cx - xLeft(v) - 1)
      .attr("y",            H + 18)
      .attr("text-anchor",  "middle")
      .attr("font-size",    "9px")
      .attr("fill",         "#888")
      .text(v => v === 0 ? "0" : fmtK(v));

  // 右軸ティック
  svg.append("g").selectAll("text.xtick-right")
    .data(ticks.slice(1)).join("text")
      .attr("x",            v => cx + xRight(v) + 1)
      .attr("y",            H + 18)
      .attr("text-anchor",  "middle")
      .attr("font-size",    "9px")
      .attr("fill",         "#888")
      .text(v => fmtK(v));

  // 中心線
  svg.append("line")
    .attr("x1", cx).attr("x2", cx)
    .attr("y1", 0) .attr("y2", H)
    .attr("stroke", "#ccc").attr("stroke-width", 1);

  // 年ラベル
  svg.append("text")
    .attr("x", W / 2).attr("y", -2)
    .attr("text-anchor", "middle")
    .attr("font-size", "11px")
    .attr("font-weight", "600")
    .attr("fill", year > 2020 ? "#e05c2b" : "#1a4a8a")
    .text(`${year}年${year > 2020 ? "（予測）" : "（実績）"}`);
}

// ===== 時系列グラフ（Chart.js） =====
function renderTimeseries(pref) {
  const MAN = 10000;  // 万人単位

  // 実績データ
  const histPop = HIST_YEARS.map(y => {
    const v = pref.history[String(y)]?.total;
    return v != null ? +(v / MAN).toFixed(2) : null;
  });

  // 全期間ラベル
  const labels = ALL_YEARS.map(String);

  // モデル予測データ（実績年は null、予測年のみ値）
  function modelSeries(modelKey) {
    return ALL_YEARS.map(y => {
      if (y <= 2020) return null;
      const v = pref.forecast[modelKey]?.[String(y)]?.total;
      return v != null ? +(v / MAN).toFixed(2) : null;
    });
  }

  // 2020年をつなぐための接続点（実績最終値）
  const pop2020 = pref.history["2020"]?.total;
  const pop2020_man = pop2020 != null ? +(pop2020 / MAN).toFixed(2) : null;

  function modelSeriesWithBase(modelKey) {
    return ALL_YEARS.map(y => {
      if (y < 2020) return null;
      if (y === 2020) return pop2020_man;  // 2020 の接続点
      const v = pref.forecast[modelKey]?.[String(y)]?.total;
      return v != null ? +(v / MAN).toFixed(2) : null;
    });
  }

  const datasets = [
    // 実績
    {
      label: "実績値",
      data: ALL_YEARS.map((y, i) => i < HIST_YEARS.length ? histPop[i] : null),
      borderColor: "#1a4a8a",
      backgroundColor: "rgba(26,74,138,.1)",
      borderWidth: 2.5,
      pointRadius: 4,
      tension: 0.3,
      fill: false,
    },
    // 各モデル
    ...Object.entries(MODEL_CONFIG).map(([key, cfg]) => ({
      label: cfg.label,
      data: modelSeriesWithBase(key),
      borderColor: cfg.color,
      backgroundColor: "transparent",
      borderWidth: 2,
      borderDash: cfg.dash,
      pointRadius: 3,
      tension: 0.3,
      fill: false,
    })),
  ];

  const ctx = document.getElementById("timeseries-chart").getContext("2d");
  new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      aspectRatio: 1.6,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: item => {
              const v = item.raw;
              if (v == null) return null;
              return ` ${item.dataset.label}: ${v.toFixed(1)} 万人`;
            },
          },
        },
        annotation: {
          annotations: {
            forecastLine: {
              type: "line",
              x: "2020",
              borderColor: "#aaa",
              borderWidth: 1,
              borderDash: [4, 4],
              label: {
                content: "予測 →",
                display: true,
                position: "end",
                font: { size: 10 },
                color: "#999",
                backgroundColor: "transparent",
              },
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(0,0,0,.06)" },
          ticks: { font: { size: 11 } },
        },
        y: {
          grid: { color: "rgba(0,0,0,.06)" },
          ticks: {
            font: { size: 11 },
            callback: v => v.toFixed(0) + "万",
          },
          title: {
            display: true,
            text: "万人",
            font: { size: 11 },
            color: "#888",
          },
        },
      },
    },
  });

  // 手動凡例
  const legendWrap = document.getElementById("model-legend");
  const legendItems = [
    { label: "実績値", color: "#1a4a8a", dash: false },
    ...Object.values(MODEL_CONFIG).map(c => ({ label: c.label, color: c.color, dash: c.dash.length > 0 })),
  ];
  legendWrap.innerHTML = legendItems.map(item => `
    <div class="model-legend-item">
      <span class="legend-line" style="
        background: ${item.dash ? "none" : item.color};
        border-bottom: 3px ${item.dash ? "dashed" : "solid"} ${item.color};
        height: 0;
      "></span>
      <span style="font-size:.78rem">${item.label}</span>
    </div>
  `).join("");
}

// ===== 都道府県ナビゲーション =====
function renderPrefNav(prefectures, currentCode) {
  const wrap = document.getElementById("pref-nav");
  wrap.innerHTML = prefectures.map(p => {
    const isCurrent = String(p.code) === currentCode;
    return `
      <a href="prefecture.html?code=${encodeURIComponent(p.code)}" style="
        display:inline-block;
        padding:.2rem .55rem;
        border:1px solid ${isCurrent ? "var(--color-primary)" : "var(--color-border)"};
        border-radius:4px;
        font-size:.75rem;
        color: ${isCurrent ? "#fff" : "var(--color-text)"};
        background: ${isCurrent ? "var(--color-primary)" : "var(--color-surface)"};
        text-decoration:none;
        transition: all .15s;
      ">${p.name}</a>
    `;
  }).join("");
}
