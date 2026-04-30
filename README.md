# e-Stat 人口動態の未来予測

過去30年（1990〜2020）の都道府県別人口データを e-Stat API から取得し、**コーホート要因法**と**時系列モデル（Prophet / ARIMA）**で 2050年の人口を予測するデータ分析プロジェクトです。

インタラクティブな日本地図・人口ピラミッドのアニメーション・時系列グラフで「日本の未来」を可視化します。

**[▶ Web サイトを見る](#)** <!-- GitHub Pages 公開後にURLを追記 -->

---

## セットアップ手順

### 1. リポジトリのクローン

```bash
git clone https://github.com/tetsuN-0320/estat-population-forecast.git
cd estat-population-forecast
```

### 2. 仮想環境の作成

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### 3. 依存ライブラリのインストール

```bash
pip install -r requirements.txt
```

### 4. 環境変数の設定

e-Stat API のアプリケーションIDを取得してください（[https://www.e-stat.go.jp/api/](https://www.e-stat.go.jp/api/)）。

```bash
cp .env.example .env
# .env を開いて ESTAT_APP_ID に取得したIDを記入
```

---

## データ取得・予測の実行

```bash
# 全都道府県のデータを取得（初回のみ数分かかります）
python scripts/fetch_data.py

# 予測モデルを実行
python scripts/run_forecast.py

# フロントエンド用JSONを生成
python scripts/build_site.py
```

---

## ディレクトリ構成

```
estat-population-forecast/
├── config/         # 定数・設定値の集中管理
├── data/           # データ（gitignore対象）
│   ├── raw/        # API取得直後の生データ・キャッシュ
│   ├── processed/  # クレンジング済みデータ
│   └── forecast/   # 予測結果
├── notebooks/      # 分析プロセスを示す Jupyter Notebook
├── src/            # 再利用可能なPythonコード
│   ├── api/        # e-Stat APIクライアント
│   ├── preprocessing/  # データ前処理
│   ├── models/     # 予測モデル
│   ├── visualization/  # 可視化
│   └── utils/      # ユーティリティ
├── web/            # GitHub Pages で公開するフロントエンド
├── tests/          # ユニットテスト
└── scripts/        # CLI スクリプト
```

---

## 技術スタック

| 分類 | 使用技術 |
|---|---|
| データ取得 | e-Stat API、requests、SQLite キャッシュ |
| データ処理 | pandas、pyarrow（parquet） |
| 予測モデル | Prophet、statsmodels（ARIMA） |
| 可視化 | Plotly |
| 地理データ | geopandas、GeoJSON |
| フロントエンド | HTML/CSS/JavaScript、Plotly.js |

---

## ライセンス

- コード: MIT License
- データ: [e-Stat（政府統計の総合窓口）利用規約](https://www.e-stat.go.jp/terms-of-use) に準拠

---

*作成者: 中江哲夫 / ポートフォリオ第1作*
