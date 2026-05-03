# 日本の人口動態予測（Population Forecast Japan 1990–2050）

[![Deploy to GitHub Pages](https://github.com/tetsuN-0320/estat-population-forecast/actions/workflows/deploy.yml/badge.svg)](https://github.com/tetsuN-0320/estat-population-forecast/actions/workflows/deploy.yml)

過去30年（1990〜2020）の都道府県別人口データを **e-Stat API** から取得し、  
**コーホート要因法 / Prophet / ARIMA** の3モデルで **2050年の人口**を予測するデータ分析ポートフォリオです。

インタラクティブな日本地図・人口ピラミッドアニメーション・時系列グラフで「日本の未来」を可視化しています。

**[▶ Web サイトを見る](https://tetsuN-0320.github.io/estat-population-forecast/)**

---

## 分析ハイライト

### 予測結果（コーホート要因法, 2050年）

**減少率が大きい都道府県**（2020→2050年）:  
秋田県・高知県・青森県・山形県・岩手県 などの地方圏

**変化が比較的小さい都道府県**:  
東京都・沖縄県・神奈川県 などの大都市圏

### バックテスト精度（1990〜2010年で学習 → 2015・2020年を検証）

| 指標 | 値 |
|---|---|
| MAPE（平均絶対誤差率）平均 | 約 2〜4% |
| RMSE | 約 3〜8 万人 |

---

## 使用技術

### バックエンド（データ処理・予測）

| ライブラリ | 用途 |
|---|---|
| `requests` + `tenacity` | e-Stat API 取得・リトライ |
| `pandas` / `pyarrow` | データ前処理・parquet 保存 |
| `prophet` | 時系列予測（Meta 製） |
| `statsmodels` | ARIMA 予測 |
| `geopandas` | GeoJSON 簡略化（12MB→451KB） |
| `loguru` | ロギング |

### フロントエンド（可視化）

| ライブラリ | 用途 |
|---|---|
| [D3.js v7](https://d3js.org/) | コロプレスマップ・人口ピラミッド（アニメーション） |
| [Chart.js v4](https://www.chartjs.org/) | 時系列グラフ（3モデル＋不確実性帯） |
| バニラ HTML/CSS/JS | レイアウト・インタラクション |

---

## セットアップ手順

### 1. リポジトリをクローン

```bash
git clone https://github.com/tetsuN-0320/estat-population-forecast.git
cd estat-population-forecast
```

### 2. 仮想環境の作成

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. e-Stat API キーの設定

[e-Stat アプリケーション登録](https://www.e-stat.go.jp/api/) でアプリケーション ID を取得し、`.env` ファイルに記入します。

```bash
cp .env.example .env
# .env を編集して ESTAT_APP_ID=<あなたのID> を設定
```

### 4. データ取得〜Web サイト生成まで一括実行

```bash
# ① e-Stat からデータ取得（SQLite キャッシュあり、初回のみ API 呼び出し）
python scripts/fetch_data.py

# ② 前処理（年齢コードの整理・parquet 保存）
python scripts/preprocess.py

# ③ 人口予測（コーホート法 / Prophet / ARIMA）
python scripts/run_forecast.py --model all

# ④ モデル評価（バックテスト・社人研比較）
python scripts/evaluate.py

# ⑤ Web サイト用 JSON 生成
python scripts/build_site.py

# ⑥ ローカル確認（http://localhost:8080）
cd web && python -m http.server 8080
```

---

## プロジェクト構成

```
estat-population-forecast/
├── config/
│   └── settings.py          # 定数・パス設定
├── data/
│   ├── raw/                 # API 取得生データ（SQLite キャッシュ）
│   ├── processed/           # 前処理済み parquet
│   └── forecasts/           # 予測結果 parquet
├── src/
│   ├── api/
│   │   ├── estat_client.py  # e-Stat API クライアント
│   │   └── data_fetcher.py  # データ取得・整形
│   ├── preprocessing/
│   │   ├── cleaner.py       # データ検証・クレンジング
│   │   └── transformer.py   # ピラミッド形式に変換
│   ├── models/
│   │   ├── cohort_method.py # コーホート要因法
│   │   ├── prophet_model.py # Prophet
│   │   ├── arima_model.py   # ARIMA
│   │   └── evaluator.py     # モデル評価
│   └── utils/
│       └── logger.py        # ロギング設定
├── scripts/
│   ├── fetch_data.py        # データ取得 CLI
│   ├── preprocess.py        # 前処理 CLI
│   ├── run_forecast.py      # 予測実行 CLI
│   ├── evaluate.py          # モデル評価 CLI
│   └── build_site.py        # Web 用 JSON 生成
├── web/                     # フロントエンド（GitHub Pages で公開）
│   ├── index.html           # トップページ（コロプレスマップ）
│   ├── prefecture.html      # 都道府県詳細（ピラミッド・グラフ）
│   ├── about.html           # プロジェクト概要
│   └── static/
│       ├── css/main.css
│       ├── js/map.js
│       ├── js/prefecture.js
│       └── data/            # 生成済み JSON（prefectures.json, national.json, japan_geo.json）
├── notebooks/               # Jupyter Notebook（分析過程）
├── tests/                   # pytest テスト
├── .github/workflows/
│   └── deploy.yml           # GitHub Actions（GitHub Pages 自動デプロイ）
├── .env.example
├── requirements.txt
└── README.md
```

---

## 分析手法の詳細

### コーホート要因法（主推計）

国勢調査5年ごとのコーホート変化率（同一年齢集団の5年間変化）を直近3期間（2005〜2020年）の平均から算出し、2020年を起点に投影します。

```
変化率(age, t→t+5) = P(age+5, t+5) / P(age, t)
```

- **出生**: CWR（幼児女性比）方式 — `P(0-4, t) / Σ P(女性15-49, t)`
- **85歳以上**: 80-84 + 85+ の合計からの生残り率を使用
- **精度**: 社人研方式と同原理のため、公的推計に近い結果が得られる

### Prophet（Meta 製時系列モデル）

都道府県別の総人口トレンドを Prophet で予測し、2020年の年齢構成比で分配。変化点を3箇所に限定し過学習を抑制。

### ARIMA(1,1,0)

データ点数が少ない（7点）ため自由度の低いモデルを選択。定数予測に落ちる場合は直近3期間のトレンド外挿にフォールバック。

---

## データ出典

| データ | 提供元 |
|---|---|
| 国勢調査 人口・年齢・男女別 | 総務省統計局 [e-Stat](https://www.e-stat.go.jp/) 統計表 ID: 0003410381 |
| 将来推計人口（参考値） | 国立社会保障・人口問題研究所（社人研）日本の将来推計人口（令和5年推計）出生中位・死亡中位 |
| 都道府県別将来推計（参考値） | 社人研「日本の地域別将来推計人口（令和5年推計）」 |
| 都道府県境界 GeoJSON | [dataofjapan/land](https://github.com/dataofjapan/land)（geopandas で簡略化） |

---

## 免責事項

本プロジェクトの予測値は個人が学習目的で実装したものであり、公的機関の推計値ではありません。  
意思決定等への利用は国立社会保障・人口問題研究所の公式推計をご参照ください。

---

## 制作者

**中江 哲夫（Tetsu Nakae）**  
株式会社ダイアローグ研究所 代表取締役 / データアナリスト（東京都荒川区）

- Python エンジニア認定（基礎・データ分析）
- 基本情報技術者
- Google Data Analytics Professional Certificate
- データ分析マスター認定（ピーシーアシスト）

> 本作品はデータアナリストとしてのポートフォリオです。  
> API データ取得 → 統計モデリング → インタラクティブ Web 可視化の一連のスキルを示しています。
