/**
 * prefecture.js — 都道府県詳細ページのロジック（Day 10 強化版）
 *
 * URL パラメータ: ?code=01000 （都道府県コード）
 *
 * 主な機能:
 *  - 人口ピラミッド（D3.js）: アニメーション自動再生（1990→2050 約28秒）
 *  - 時系列グラフ（Chart.js）: 実績 + 3モデル予測 + モデル幅（信頼区間代替）
 *  - サマリーカード: 老年人口比率・生産年齢人口比率
 */

"use strict";

// ===== 定数 =====
const ALL_YEARS     = [1990, 1995, 2000, 2005, 2010, 2015, 2020, 2025, 2030, 2035, 2040, 2045, 2050];
const HIST_YEARS    = [1990, 1995, 2000, 2005, 2010, 2015, 2020];
const FORE_YEARS    = [2025, 2030, 2035, 2040, 2045, 2050];
const PYRAMID_YEARS = [1990, 2000, 2010, 2020, 2030, 2040, 2050];

const AGE_ORDER = [
  "0-4","5-9","10-14","15-19","20-24","25-29","30-34","35-39",
  "40-44","45-49","50-54","55-59","60-64","65-69","70-74","75-79","80-84","85+",
];

// 老年人口（65歳以上）
const ELDERLY_AGES = ["65-69","70-74","75-79","80-84","85+"];
// 生産年齢（15〜64歳）
const WORKING_AGES = [
  "15-19","20-24","25-29","30-34","35-39",
  "40-44","45-49","50-54","55-59","60-64",
];
// 年少人口（0〜14歳）
const YOUNG_AGES   = ["0-4","5-9","10-14"];

const MODEL_CONFIG = {
  cohort:  { label: "コーホート要因法", color: "#e05c2b", dash: [] },
  prophet: { label: "Prophet",          color: "#27ae60", dash: [6, 3] },
  arima:   { label: "ARIMA",            color: "#8e44ad", dash: [3, 3] },
};

// アニメーション: 各年の表示時間（ms）
const ANIM_INTERVAL_MS = 1400;

// ===== URL から都道府県コードを取得 =====
const params  = new URLSearchParams(window.location.search);
const rawCode = params.get("code") || "13000";
const prefCode = rawCode.length <= 2
  ? rawCode.padStart(2, "0") + "000"
  : rawCode;

// ===== 状態 =====
let pyramidState = {
  yearIdx:  PYRAMID_YEARS.indexOf(2020),
  playing:  false,
  timer:    null,
};

// ===== データ読み込み =====
d3.json("static/data/prefectures.json").then(data => {
  const pref = data.prefectures.find(p => String(p.code) === String(prefCode));
  if (!pref) {
    document.getElementById("pref-name").textContent = "都道府県が見つかりません";
    return;
  }

  document.title = `${pref.name} — 日本の人口動態予測`;
  document.getElementById("pref-name").textContent = pref.name;

  // 変化率バッジ
  const chg = pref.change_pct_2020_2050;
  if (chg !== null) {
    const badge = document.getElementById("pref-change-badge");
    badge.style.cssText = `
      background:${chg < 0 ? "#fde8e5" : "#e8f4fd"};
      color:${chg < 0 ? "#c0392b" : "#1a5276"};
      padding:.25rem .7rem; border-radius:99px;
      font-size:.85rem; font-weight:600;
      vertical-align:middle;
    `;
    badge.textContent = `2020→2050: ${chg >= 0 ? "+" : ""}${chg.toFixed(1)}%（コーホート法）`;
  }

  renderSummaryCards(pref);
  renderPyramidSection(pref);
  renderTimeseries(pref);
  renderPrefNav(data.prefectures, String(prefCode));
});

// ===== サマリーカード =====
function renderSummaryCards(pref) {
  const pop2020 = pref.history["2020"]?.total;
  const pop1990 = pref.history["1990"]?.total;
  const pop2050 = pref.forecast?.cohort?.["2050"]?.total;

  // 老年人口比率（2020年）
  const pyr2020 = pref.pyramid?.["2020"] || [];
  const totalPyr2020 = pyr2020.reduce((s, r) => s + r.male + r.female, 0);
  const elderlyPop   = pyr2020
    .filter(r => ELDERLY_AGES.includes(r.age))
    .reduce((s, r) => s + r.male + r.female, 0);
  const workingPop   = pyr2020
    .filter(r => WORKING_AGES.includes(r.age))
    .reduce((s, r) => s + r.male + r.female, 0);
  const elderlyRatio = totalPyr2020 > 0 ? (elderlyPop / totalPyr2020 * 100) : null;
  const workingRatio = totalPyr2020 > 0 ? (workingPop / totalPyr2020 * 100) : null;

  // 2050年 老年人口比率
  const pyr2050 = pref.pyramid?.["2050"] || [];
  const totalPyr2050 = pyr2050.reduce((s, r) => s + r.male + r.female, 0);
  const elderly2050  = pyr2050
    .filter(r => ELDERLY_AGES.includes(r.age))
    .reduce((s, r) => s + r.male + r.female, 0);
  const elderlyRatio2050 = totalPyr2050 > 0 ? (elderly2050 / totalPyr2050 * 100) : null;

  const cards = [
    {
      label: "2020年 総人口（実績）",
      value: pop2020 ? (pop2020 / 10000).toFixed(1) + " 万人" : "−",
      sub: "",
      color: "var(--color-primary)",
    },
    {
      label: "老年人口比率（2020年）",
      value: elderlyRatio !== null ? elderlyRatio.toFixed(1) + "%" : "−",
      sub: "65歳以上 / 総人口",
      color: elderlyRatio > 30 ? "#922b21" : "var(--color-primary)",
    },
    {
      label: "生産年齢人口比率（2020年）",
      value: workingRatio !== null ? workingRatio.toFixed(1) + "%" : "−",
      sub: "15〜64歳 / 総人口",
      color: "var(--color-primary)",
    },
    {
      label: "2050年 老年人口比率（予測）",
      value: elderlyRatio2050 !== null ? elderlyRatio2050.toFixed(1) + "%" : "−",
      sub: "コーホート法 / 65歳以上",
      color: elderlyRatio2050 > 40 ? "#922b21" : "#c0392b",
    },
  ];

  const container = document.getElementById("summary-cards");
  container.innerHTML = cards.map(c => `
    <div class="card" style="padding:1rem">
      <div style="font-size:.75rem;color:var(--color-muted);margin-bottom:.3rem">${c.label}</div>
      <div style="font-size:1.4rem;font-weight:700;color:${c.color}">${c.value}</div>
      ${c.sub ? `<div style="font-size:.72rem;color:var(--color-muted);margin-top:.15rem">${c.sub}</div>` : ""}
    </div>
  `).join("");
}

// ===== ピラミッドセクション =====
function renderPyramidSection(pref) {
  // 年ボタン
  const btnWrap = document.getElementById("pyramid-year-btns");
  btnWrap.innerHTML = PYRAMID_YEARS.map((y, i) => `
    <button
      class="pyramid-year-btn ${i === pyramidState.yearIdx ? "active" : ""} ${y > 2020 ? "forecast-year" : ""}"
      data-idx="${i}"
    >${y}${y > 2020 ? "予" : ""}</button>
  `).join("");

  btnWrap.querySelectorAll(".pyramid-year-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      stopPyramidAnim();
      setActiveYear(pref, +btn.dataset.idx);
    });
  });

  // 再生ボタンを追加
  const playWrap = document.getElementById("pyramid-play-wrap");
  if (playWrap) {
    playWrap.innerHTML = `
      <button class="play-btn" id="pyramid-play-btn" style="margin-top:.5rem;font-size:.82rem;padding:.4rem .9rem">
        <span id="pyr-play-icon">▶</span>
        <span id="pyr-play-label">1990→2050 再生</span>
      </button>
    `;
    document.getElementById("pyramid-play-btn").addEventListener("click", () => {
      if (pyramidState.playing) {
        stopPyramidAnim();
      } else {
        startPyramidAnim(pref);
      }
    });
  }

  // 初期描画
  drawPyramid(pref, PYRAMID_YEARS[pyramidState.yearIdx], false);
}

function setActiveYear(pref, idx) {
  pyramidState.yearIdx = idx;
  document.querySelectorAll(".pyramid-year-btn").forEach((b, i) => {
    b.classList.toggle("active", i === idx);
  });
  drawPyramid(pref, PYRAMID_YEARS[idx], true);
}

function startPyramidAnim(pref) {
  pyramidState.playing = true;
  const btn   = document.getElementById("pyramid-play-btn");
  const icon  = document.getElementById("pyr-play-icon");
  const label = document.getElementById("pyr-play-label");
  if (btn) { btn.classList.add("playing"); }
  if (icon) icon.textContent  = "⏸";
  if (label) label.textContent = "停止";

  // 先頭から再生
  if (pyramidState.yearIdx >= PYRAMID_YEARS.length - 1) {
    setActiveYear(pref, 0);
  }

  pyramidState.timer = setInterval(() => {
    const nextIdx = pyramidState.yearIdx + 1;
    if (nextIdx >= PYRAMID_YEARS.length) {
      stopPyramidAnim();
      return;
    }
    setActiveYear(pref, nextIdx);
  }, ANIM_INTERVAL_MS);
}

function stopPyramidAnim() {
  pyramidState.playing = false;
  clearInterval(pyramidState.timer);
  const btn   = document.getElementById("pyramid-play-btn");
  const icon  = document.getElementById("pyr-play-icon");
  const label = document.getElementById("pyr-play-label");
  if (btn) { btn.classList.remove("playing"); }
  if (icon) icon.textContent  = "▶";
  if (label) label.textContent = "1990→2050 再生";
}

// ===== 人口ピラミッド描画（D3、スムーズトランジション付き） =====
function drawPyramid(pref, year, animate) {
  const pyramidData = pref.pyramid?.[String(year)];
  if (!pyramidData) return;

  const svgEl  = document.getElementById("pyramid-svg");
  const totalW = svgEl.clientWidth || 420;
  const margin = { top: 24, right: 16, bottom: 30, left: 18 };
  const W = totalW - margin.left - margin.right;
  const H = 380 - margin.top - margin.bottom;

  // 初回のみ SVG 構造を作成
  let svg = d3.select("#pyramid-svg").select("g.pyramid-g");
  const isFirstDraw = svg.empty();

  if (isFirstDraw) {
    d3.select("#pyramid-svg")
      .attr("height", H + margin.top + margin.bottom);
    svg = d3.select("#pyramid-svg")
      .append("g")
      .attr("class", "pyramid-g")
      .attr("transform", `translate(${margin.left},${margin.top})`);
  }

  // データ整列（逆順で上が高齢）
  const rows = AGE_ORDER.map(age => {
    const d = pyramidData.find(r => r.age === age) || { male: 0, female: 0 };
    return { age, male: d.male, female: d.female };
  }).reverse();

  const maxVal = d3.max(rows, r => Math.max(r.male, r.female)) || 1;
  const halfW  = (W / 2) - 28;
  const cx     = W / 2;

  const xLeft  = d3.scaleLinear().domain([0, maxVal]).range([0, halfW]);
  const xRight = d3.scaleLinear().domain([0, maxVal]).range([0, halfW]);
  const y      = d3.scaleBand().domain(rows.map(r => r.age)).range([0, H]).padding(0.1);
  const dur    = animate ? 600 : 0;

  // ---- 年齢ラベル（中央）----
  svg.selectAll("text.age-label")
    .data(rows, d => d.age)
    .join("text")
      .attr("class", "age-label")
      .attr("x", cx)
      .attr("y", r => y(r.age) + y.bandwidth() / 2 + 4)
      .attr("text-anchor", "middle")
      .attr("font-size", "9px")
      .attr("fill", "#666");

  // ---- 男性バー（左）----
  svg.selectAll("rect.male-bar")
    .data(rows, d => d.age)
    .join(
      enter => enter.append("rect")
        .attr("class", "male-bar")
        .attr("x",      r => cx - xLeft(r.male))
        .attr("y",      r => y(r.age))
        .attr("width",  0)
        .attr("height", y.bandwidth())
        .attr("fill", "#2471a3")
        .attr("opacity", .85),
      update => update,
    )
    .transition().duration(dur)
      .attr("x",      r => cx - xLeft(r.male) - 1)
      .attr("y",      r => y(r.age))
      .attr("width",  r => xLeft(r.male))
      .attr("height", y.bandwidth())
      .attr("fill", d => {
        if (ELDERLY_AGES.includes(d.age)) return "#1a5276";
        if (YOUNG_AGES.includes(d.age))   return "#5dade2";
        return "#2471a3";
      });

  // ---- 女性バー（右）----
  svg.selectAll("rect.female-bar")
    .data(rows, d => d.age)
    .join(
      enter => enter.append("rect")
        .attr("class", "female-bar")
        .attr("x",     cx + 1)
        .attr("y",     r => y(r.age))
        .attr("width", 0)
        .attr("height", y.bandwidth())
        .attr("fill", "#c0392b")
        .attr("opacity", .85),
      update => update,
    )
    .transition().duration(dur)
      .attr("x",      cx + 1)
      .attr("y",      r => y(r.age))
      .attr("width",  r => xRight(r.female))
      .attr("height", y.bandwidth())
      .attr("fill", d => {
        if (ELDERLY_AGES.includes(d.age)) return "#922b21";
        if (YOUNG_AGES.includes(d.age))   return "#e59866";
        return "#c0392b";
      });

  // ---- 年齢ラベル（再セット）----
  svg.selectAll("text.age-label")
    .data(rows, d => d.age)
    .attr("x", cx)
    .attr("y", r => y(r.age) + y.bandwidth() / 2 + 4);

  // ---- 中心線 ----
  if (isFirstDraw) {
    svg.append("line").attr("class", "center-line")
      .attr("x1", cx).attr("x2", cx)
      .attr("y1", 0) .attr("y2", H)
      .attr("stroke", "#ccc").attr("stroke-width", 1);
  }

  // ---- 年ラベル ----
  if (isFirstDraw) {
    svg.append("text").attr("class", "year-label")
      .attr("x", W / 2).attr("y", -6)
      .attr("text-anchor", "middle")
      .attr("font-size", "12px").attr("font-weight", "700");
  }
  svg.select("text.year-label")
    .attr("fill", year > 2020 ? "#e05c2b" : "#1a4a8a")
    .text(`${year}年 ${year > 2020 ? "（予測）" : "（実績）"}`);

  // ---- X 軸目盛り ----
  const fmtK = v => v >= 10000 ? (v / 10000).toFixed(0) + "万" : (v / 1000).toFixed(0) + "千";
  const tick1 = Math.round(maxVal * 0.5 / 1000) * 1000;

  svg.selectAll("text.xtick").remove();
  [0, tick1, maxVal].forEach(v => {
    // 左
    svg.append("text").attr("class", "xtick")
      .attr("x", cx - xLeft(v) - 1).attr("y", H + 18)
      .attr("text-anchor", "middle").attr("font-size", "9px").attr("fill", "#999")
      .text(v === 0 ? "0" : fmtK(v));
    // 右（0以外）
    if (v > 0) {
      svg.append("text").attr("class", "xtick")
        .attr("x", cx + xRight(v) + 1).attr("y", H + 18)
        .attr("text-anchor", "middle").attr("font-size", "9px").attr("fill", "#999")
        .text(fmtK(v));
    }
  });

  // ---- 構成比バー（右上に小さく）----
  updateAgeComposition(pref, year, rows);
}

// ===== 年齢3区分 構成比バー =====
function updateAgeComposition(pref, year, rows) {
  const total = rows.reduce((s, r) => s + r.male + r.female, 0);
  if (!total) return;

  const young   = rows.filter(r => YOUNG_AGES.includes(r.age))  .reduce((s, r) => s + r.male + r.female, 0);
  const working = rows.filter(r => WORKING_AGES.includes(r.age)).reduce((s, r) => s + r.male + r.female, 0);
  const elderly = rows.filter(r => ELDERLY_AGES.includes(r.age)).reduce((s, r) => s + r.male + r.female, 0);

  const compEl = document.getElementById("age-composition");
  if (!compEl) return;

  const pctY = (young   / total * 100).toFixed(1);
  const pctW = (working / total * 100).toFixed(1);
  const pctE = (elderly / total * 100).toFixed(1);

  compEl.innerHTML = `
    <div style="font-size:.75rem;color:var(--color-muted);margin-bottom:.35rem">年齢3区分構成比</div>
    <div style="display:flex;height:14px;border-radius:4px;overflow:hidden;margin-bottom:.3rem">
      <div style="width:${pctY}%;background:#5dade2" title="年少 ${pctY}%"></div>
      <div style="width:${pctW}%;background:#2471a3" title="生産 ${pctW}%"></div>
      <div style="width:${pctE}%;background:#1a5276" title="老年 ${pctE}%"></div>
    </div>
    <div style="display:flex;gap:1rem;font-size:.72rem;color:var(--color-muted)">
      <span><span style="color:#5dade2">■</span> 年少 ${pctY}%</span>
      <span><span style="color:#2471a3">■</span> 生産 ${pctW}%</span>
      <span><span style="color:#1a5276">■</span> 老年 ${pctE}%</span>
    </div>
  `;
}

// ===== 時系列グラフ（Chart.js）=====
function renderTimeseries(pref) {
  const MAN = 10000;

  // 実績データ
  const histPop = ALL_YEARS.map(y => {
    if (y > 2020) return null;
    const v = pref.history[String(y)]?.total;
    return v != null ? +(v / MAN).toFixed(2) : null;
  });

  // 2020年の実績値（モデルとの接続点）
  const pop2020_man = pref.history["2020"]?.total != null
    ? +(pref.history["2020"].total / MAN).toFixed(2)
    : null;

  // モデル予測（2020年を接続点として含める）
  function modelSeries(key) {
    return ALL_YEARS.map(y => {
      if (y < 2020) return null;
      if (y === 2020) return pop2020_man;
      const v = pref.forecast[key]?.[String(y)]?.total;
      return v != null ? +(v / MAN).toFixed(2) : null;
    });
  }

  // モデル幅（min〜max の帯）: 予測年のみ
  const bandMin = ALL_YEARS.map(y => {
    if (y < 2020) return null;
    if (y === 2020) return pop2020_man;
    const vals = Object.keys(MODEL_CONFIG)
      .map(k => pref.forecast[k]?.[String(y)]?.total)
      .filter(v => v != null);
    return vals.length ? +(Math.min(...vals) / MAN).toFixed(2) : null;
  });

  const bandMax = ALL_YEARS.map(y => {
    if (y < 2020) return null;
    if (y === 2020) return pop2020_man;
    const vals = Object.keys(MODEL_CONFIG)
      .map(k => pref.forecast[k]?.[String(y)]?.total)
      .filter(v => v != null);
    return vals.length ? +(Math.max(...vals) / MAN).toFixed(2) : null;
  });

  const labels = ALL_YEARS.map(String);

  const datasets = [
    // モデル幅 上限（帯の上辺、legendなし）
    {
      label: "モデル幅 上限",
      data: bandMax,
      borderColor: "transparent",
      backgroundColor: "rgba(224,92,43,.15)",
      fill: "+1",     // 次のデータセット（下限）との間を塗る
      pointRadius: 0,
      tension: 0.3,
    },
    // モデル幅 下限
    {
      label: "モデル幅 下限",
      data: bandMin,
      borderColor: "transparent",
      backgroundColor: "rgba(224,92,43,.15)",
      fill: false,
      pointRadius: 0,
      tension: 0.3,
    },
    // 実績
    {
      label: "実績値",
      data: histPop,
      borderColor: "#1a4a8a",
      backgroundColor: "rgba(26,74,138,.08)",
      borderWidth: 2.5,
      pointRadius: 4,
      pointHoverRadius: 6,
      tension: 0.3,
      fill: false,
    },
    // 各モデル
    ...Object.entries(MODEL_CONFIG).map(([key, cfg]) => ({
      label: cfg.label,
      data: modelSeries(key),
      borderColor: cfg.color,
      backgroundColor: "transparent",
      borderWidth: 2,
      borderDash: cfg.dash,
      pointRadius: 3,
      pointHoverRadius: 5,
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
      aspectRatio: 1.5,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: item => {
              if (item.dataset.label.startsWith("モデル幅")) return null;
              const v = item.raw;
              if (v == null) return null;
              return ` ${item.dataset.label}: ${v.toFixed(1)} 万人`;
            },
          },
          filter: item => !item.dataset.label.startsWith("モデル幅"),
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(0,0,0,.05)" },
          ticks: { font: { size: 11 }, maxTicksLimit: 13 },
        },
        y: {
          grid: { color: "rgba(0,0,0,.05)" },
          ticks: {
            font: { size: 11 },
            callback: v => v.toFixed(0) + "万",
          },
          title: {
            display: true, text: "万人",
            font: { size: 11 }, color: "#888",
          },
        },
      },
    },
  });

  // 手動凡例
  const legendWrap = document.getElementById("model-legend");
  const legendItems = [
    { label: "実績値",          color: "#1a4a8a", dash: false },
    { label: "コーホート要因法", color: "#e05c2b", dash: false },
    { label: "Prophet",          color: "#27ae60", dash: true },
    { label: "ARIMA",            color: "#8e44ad", dash: true },
    { label: "モデル幅（不確実性）", color: "rgba(224,92,43,.4)", band: true },
  ];
  legendWrap.innerHTML = legendItems.map(item => `
    <div class="model-legend-item">
      ${item.band
        ? `<span style="width:20px;height:10px;background:${item.color};border-radius:2px;display:inline-block"></span>`
        : `<span style="width:20px;height:0;border-bottom:3px ${item.dash ? "dashed" : "solid"} ${item.color};display:inline-block"></span>`
      }
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
        border-radius:4px; font-size:.75rem;
        color:${isCurrent ? "#fff" : "var(--color-text)"};
        background:${isCurrent ? "var(--color-primary)" : "var(--color-surface)"};
        text-decoration:none; transition:all .15s;
      ">${p.name}</a>
    `;
  }).join("");
}
