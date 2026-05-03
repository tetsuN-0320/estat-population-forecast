/**
 * map.js — 日本コロプレスマップ
 *
 * ・D3.js v7 を使用
 * ・japan_geo.json (GeoJSON) + prefectures.json を読み込み
 * ・年スライダー / モデル選択 / ホバーツールチップ / クリックで詳細ページへ
 */

"use strict";

// ===== 定数 =====
const YEARS = [1990, 1995, 2000, 2005, 2010, 2015, 2020, 2025, 2030, 2035, 2040, 2045, 2050];
const FORECAST_YEARS = new Set([2025, 2030, 2035, 2040, 2045, 2050]);
const BASE_YEAR = 2020;
const COLOR_DOMAIN = [-50, 0, 15];   // % の三点（min, neutral, max）

// カラースケール: 減少=赤 → 0=白 → 増加=青
const colorScale = d3.scaleDiverging(d3.interpolateRdYlBu)
  .domain(COLOR_DOMAIN);

// グレー（データなし）
const NO_DATA_COLOR = "#d0d7e3";

// ===== 状態 =====
let state = {
  year: 2020,
  model: "cohort",
  prefData: null,   // code(int) → pref object
  geoData: null,
  playing: false,
  playTimer: null,
  selectedCode: null,
};

// ===== 初期化 =====
Promise.all([
  d3.json("static/data/japan_geo.json"),
  d3.json("static/data/prefectures.json"),
]).then(([geo, data]) => {
  // 都道府県データを 2桁コード→object のマップに変換
  // prefectures.json の code は "01000" 形式 → 先頭2桁を使用
  state.prefData = new Map(data.prefectures.map(p => [String(p.code).slice(0, 2), p]));
  state.geoData = geo;

  drawMap();
  drawLegend();
  updateRanking();

  document.getElementById("map-loading").classList.add("hidden");
}).catch(err => {
  console.error("データ読み込みエラー:", err);
  document.getElementById("map-loading").innerHTML =
    '<p style="color:red;padding:1rem">データの読み込みに失敗しました</p>';
});

// ===== 地図描画 =====
function drawMap() {
  const svg = d3.select("#japan-map");
  const container = document.getElementById("map-card");
  const W = container.clientWidth - 24;   // padding 分引く
  const H = 520;

  svg.attr("viewBox", `0 0 ${W} ${H}`);

  // 投影（日本全土が収まるよう調整）
  const projection = d3.geoMercator()
    .center([136.5, 35.5])
    .scale(W * 1.6)
    .translate([W / 2, H / 2]);

  const path = d3.geoPath().projection(projection);

  const g = svg.append("g");

  // 都道府県パスを描画
  g.selectAll("path")
    .data(state.geoData.features)
    .join("path")
      .attr("class", "prefecture-path")
      .attr("d", path)
      .attr("fill", d => fillColor(d))
      .on("mousemove", onMouseMove)
      .on("mouseleave", onMouseLeave)
      .on("click", onPrefClick);

  // ズーム（スマホ対応）
  const zoom = d3.zoom()
    .scaleExtent([0.8, 8])
    .on("zoom", e => g.attr("transform", e.transform));
  svg.call(zoom);
}

// パスの塗り色を返す
function fillColor(feature) {
  // geo の pref_code は "01"〜"47"（2桁ゼロ埋め）
  const code = feature.properties.pref_code;
  const pref = state.prefData?.get(code);
  if (!pref) return NO_DATA_COLOR;

  const changePct = getChangePct(pref, state.year, state.model);
  if (changePct === null) return NO_DATA_COLOR;
  return colorScale(Math.max(COLOR_DOMAIN[0], Math.min(COLOR_DOMAIN[2], changePct)));
}

// 2020年比の変化率（%）
function getChangePct(pref, year, model) {
  const pop = getPopulation(pref, year, model);
  const pop2020 = pref.history["2020"]?.total;
  if (!pop || !pop2020) return null;
  return (pop / pop2020 - 1) * 100;
}

// 年・モデルに対応する総人口を返す
function getPopulation(pref, year, model) {
  const yr = String(year);
  if (year <= BASE_YEAR) {
    return pref.history[yr]?.total ?? null;
  }
  return pref.forecast[model]?.[yr]?.total ?? null;
}

// ===== 地図の色を再描画 =====
function updateMapColors() {
  d3.selectAll(".prefecture-path")
    .attr("fill", d => fillColor(d));
}

// ===== 凡例キャンバス =====
function drawLegend() {
  const canvas = document.getElementById("legend-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.offsetWidth || 200;
  canvas.width = W;
  canvas.height = 14;
  for (let i = 0; i < W; i++) {
    const t = i / (W - 1);
    const pct = COLOR_DOMAIN[0] + (COLOR_DOMAIN[2] - COLOR_DOMAIN[0]) * t;
    ctx.fillStyle = colorScale(pct);
    ctx.fillRect(i, 0, 1, 14);
  }
}

// ===== ツールチップ =====
function onMouseMove(event, d) {
  const code = d.properties.pref_code;  // "01"〜"47"
  state.selectedCode = code;
  updateInfoPanel(code);
  const pref = state.prefData?.get(code);
  if (!pref) return;

  const pop = getPopulation(pref, state.year, state.model);
  const chg = getChangePct(pref, state.year, state.model);

  document.getElementById("tip-name").textContent = pref.name;
  document.getElementById("tip-pop").textContent =
    pop ? `総人口: ${pop.toLocaleString()} 人` : "データなし";

  const tipChg = document.getElementById("tip-chg");
  if (chg !== null) {
    tipChg.textContent = `2020年比: ${chg >= 0 ? "+" : ""}${chg.toFixed(1)}%`;
    tipChg.className = "tip-chg " + (chg < 0 ? "neg" : "pos");
  } else {
    tipChg.textContent = "";
  }

  const tt = document.getElementById("tooltip");
  tt.style.display = "block";
  tt.style.left = (event.clientX + 14) + "px";
  tt.style.top  = (event.clientY - 10) + "px";
}

function onMouseLeave() {
  document.getElementById("tooltip").style.display = "none";
}

// ===== クリック → 詳細ページ =====
function onPrefClick(event, d) {
  // code は "01000" 形式で渡す（prefectures.json との一致のため）
  const twoDigit = d.properties.pref_code;
  const pref = state.prefData?.get(twoDigit);
  if (!pref) return;
  window.location.href = `prefecture.html?code=${encodeURIComponent(pref.code)}`;
}

// ===== 情報パネル更新 =====
function updateInfoPanel(code) {
  const panel = document.getElementById("info-panel");
  if (!code) {
    panel.innerHTML = '<p class="info-placeholder">都道府県を選択してください</p>';
    return;
  }
  const pref = state.prefData?.get(code);
  if (!pref) return;

  const pop = getPopulation(pref, state.year, state.model);
  const chg = getChangePct(pref, state.year, state.model);
  const chgLabel = chg !== null
    ? `${chg >= 0 ? "+" : ""}${chg.toFixed(1)}%`
    : "−";
  const chgClass = chg !== null ? (chg < 0 ? "negative" : "positive") : "";

  panel.innerHTML = `
    <div class="info-pref-name">${pref.name}</div>
    <div class="info-pop">${pop ? pop.toLocaleString() + " 人" : "−"}</div>
    <div class="info-change ${chgClass}">2020年比 ${chgLabel}</div>
    <div style="margin-top:.75rem;font-size:.78rem;color:var(--color-muted)">
      クリックで詳細を表示 →
    </div>
  `;
}

// ===== ランキング更新 =====
function updateRanking() {
  if (!state.prefData) return;

  const model = state.model;
  const prefs = [...state.prefData.values()];
  const withChg = prefs
    .map(p => ({ code: p.code, name: p.name, chg: p.change_pct_2020_2050 }))
    .filter(p => p.chg !== null)
    .sort((a, b) => a.chg - b.chg);

  const bottom5 = withChg.slice(0, 5);
  const top5    = withChg.slice(-5).reverse();

  function renderList(listId, items) {
    const ul = document.getElementById(listId);
    ul.innerHTML = items.map((p, i) => `
      <li onclick="window.location.href='prefecture.html?code=${encodeURIComponent(p.code)}'">
        <span class="rank">${i + 1}</span>
        <span class="pref">${p.name}</span>
        <span class="val ${p.chg < 0 ? "negative" : "positive"}">
          ${p.chg >= 0 ? "+" : ""}${p.chg.toFixed(1)}%
        </span>
      </li>
    `).join("");
  }

  renderList("rank-decrease", bottom5);
  renderList("rank-increase", top5);

  const labelMap = { cohort: "コーホート法", prophet: "Prophet", arima: "ARIMA" };
  document.getElementById("ranking-model-label").textContent =
    "（" + (labelMap[model] || model) + "）";
}

// ===== 年スライダー =====
const slider = document.getElementById("year-slider");
const yearDisplay = document.getElementById("year-display");
const yearTag     = document.getElementById("year-tag");

slider.addEventListener("input", () => {
  state.year = YEARS[+slider.value];
  yearDisplay.textContent = state.year;
  yearTag.textContent  = FORECAST_YEARS.has(state.year) ? "予測値" : "実績値";
  yearTag.className    = "year-tag " + (FORECAST_YEARS.has(state.year) ? "forecast" : "historical");
  updateMapColors();
  updateInfoPanel(state.selectedCode);
});

// ===== 再生ボタン =====
const playBtn   = document.getElementById("play-btn");
const playIcon  = document.getElementById("play-icon");
const playLabel = document.getElementById("play-label");

playBtn.addEventListener("click", () => {
  state.playing = !state.playing;
  if (state.playing) {
    playIcon.textContent  = "⏸";
    playLabel.textContent = "停止";
    playBtn.classList.add("playing");
    runAnimation();
  } else {
    stopAnimation();
  }
});

function runAnimation() {
  state.playTimer = setInterval(() => {
    const nextIdx = Math.min(+slider.value + 1, YEARS.length - 1);
    slider.value = nextIdx;
    slider.dispatchEvent(new Event("input"));
    if (nextIdx >= YEARS.length - 1) stopAnimation();
  }, 800);
}

function stopAnimation() {
  clearInterval(state.playTimer);
  state.playing = false;
  playIcon.textContent  = "▶";
  playLabel.textContent = "アニメーション再生";
  playBtn.classList.remove("playing");
}

// ===== モデルボタン =====
document.querySelectorAll(".model-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".model-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    state.model = btn.dataset.model;
    updateMapColors();
    updateInfoPanel(state.selectedCode);
    updateRanking();
  });
});

// ===== ウィンドウリサイズ =====
let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    d3.select("#japan-map").selectAll("*").remove();
    drawMap();
    drawLegend();
    updateMapColors();
  }, 250);
});
