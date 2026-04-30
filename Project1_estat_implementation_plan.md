# 第1案 実装計画書

**プロジェクト名**: e-Stat 人口動態の未来予測（Population Dynamics Forecast Japan）
**作成日**: 2026年4月30日
**想定実装期間**: 12日間（実働、1日3〜4時間）／カレンダー上3週間

---

## 1. プロジェクト概要

過去30年（1990〜2020）の都道府県別人口データを e-Stat API から取得し、**コーホート要因法**と**時系列モデル（Prophet / ARIMA）**の2系統で 2040年・2050年の人口を予測する。インタラクティブな日本地図、人口ピラミッドのアニメーション、時系列グラフで「日本の未来」を可視化し、データ分析の一連のプロセス（取得→前処理→モデリング→可視化→ストーリー化）をひとつの作品として提示する。

**最終成果物**

1. GitHub Pages で公開する静的 Web サイト（`/web/`）
2. 分析プロセスを示す Jupyter Notebook 群（`/notebooks/`）
3. 再現可能なコードベース（`/src/`）と README
4. ポートフォリオ用の解説記事（プロジェクトの背景・手法・発見）

---

## 2. ファイル構成

```
estat-population-forecast/
│
├── README.md                       # プロジェクト概要、セットアップ手順、成果物リンク
├── .gitignore                      # APIキー、生データ、キャッシュを除外
├── .env.example                    # 環境変数テンプレート（ESTAT_APP_ID 等）
├── requirements.txt                # 依存ライブラリ（pip install -r 用）
├── pyproject.toml                  # black/ruff 設定
│
├── config/
│   └── settings.py                 # 統計表ID、都道府県コード、定数の集中管理
│
├── data/
│   ├── raw/                        # API取得直後の生JSON/CSV（gitignore推奨）
│   │   └── estat_cache.sqlite      # API レスポンスのキャッシュ
│   ├── processed/                  # クレンジング済みデータ（pickle/parquet）
│   │   ├── population_long.parquet
│   │   └── age_pyramid.parquet
│   └── forecast/                   # モデル予測結果
│       ├── cohort_2050.parquet
│       └── prophet_2050.parquet
│
├── notebooks/
│   ├── 01_data_exploration.ipynb   # 探索的データ分析（EDA）
│   ├── 02_preprocessing.ipynb      # データ前処理プロセスの可視化
│   ├── 03_forecasting_models.ipynb # 予測モデル比較・評価
│   └── 04_visualization_proto.ipynb# 可視化プロトタイプ
│
├── src/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── estat_client.py         # e-Stat API ラッパー
│   │   └── data_fetcher.py         # 取得タスクのオーケストレーション
│   ├── preprocessing/
│   │   ├── __init__.py
│   │   ├── cleaner.py              # 欠損値処理、型変換、表記揺れ補正
│   │   └── transformer.py          # ピボット・集計・年齢階級リサンプル
│   ├── models/
│   │   ├── __init__.py
│   │   ├── cohort_method.py        # コーホート要因法の実装
│   │   ├── prophet_model.py        # Prophet による時系列予測
│   │   ├── arima_model.py          # ARIMA による時系列予測
│   │   └── evaluator.py            # MAPE/RMSE、社人研推計との比較
│   ├── visualization/
│   │   ├── __init__.py
│   │   ├── maps.py                 # 都道府県コロプレスマップ
│   │   ├── pyramids.py             # 人口ピラミッド（アニメーション）
│   │   └── timeseries.py           # 時系列グラフ
│   └── utils/
│       ├── __init__.py
│       └── logger.py               # loguru ベースのロガー
│
├── web/
│   ├── index.html                  # トップ：日本地図 + 年代スライダー
│   ├── prefecture.html             # 都道府県詳細：ピラミッド・時系列
│   ├── about.html                  # データソース・手法・免責事項
│   ├── static/
│   │   ├── css/
│   │   │   ├── main.css
│   │   │   └── responsive.css
│   │   ├── js/
│   │   │   ├── map.js              # 地図インタラクション
│   │   │   ├── slider.js           # 年代スライダー制御
│   │   │   └── charts.js           # Plotly チャート差し替え
│   │   └── data/
│   │       ├── prefectures.json    # 集計済み（フロント用、軽量化済み）
│   │       └── japan_geo.json      # 都道府県境界 GeoJSON
│   └── assets/
│       └── images/                 # OG画像、サイトロゴ
│
├── tests/
│   ├── test_api.py                 # APIクライアントのユニットテスト
│   ├── test_preprocessing.py       # 前処理関数のテスト
│   └── test_models.py              # モデルの基本動作テスト
│
└── scripts/
    ├── fetch_data.py               # CLI: 一括データ取得
    ├── run_forecast.py             # CLI: 予測実行
    └── build_site.py               # CLI: フロント用JSON生成・ビルド
```

### 設計上の主なポイント

- **`src/` と `notebooks/` の分離**: ノートブックは「分析プロセスの記録・公開」用、`src/` は再利用可能な関数・クラスを置く（DRY原則）。ノートブックは `from src.api.estat_client import EstatClient` のように `src/` を import する
- **`data/raw/` は gitignore**: 生データはサイズが大きく、APIキーで再取得可能なため
- **SQLite キャッシュ**: 同じAPIを何度も叩かないように `data/raw/estat_cache.sqlite` でレスポンスをキャッシュし、開発効率を上げる
- **`web/static/data/` は集計済みJSONのみ**: フロントエンドは生データを扱わない。バックエンドで集計し、軽量JSONを書き出す（パフォーマンスとプライバシーの両立）

---

## 3. 必要ライブラリ

### 3.1 requirements.txt（推奨バージョン）

```
# === API・HTTP ===
requests>=2.31.0
python-dotenv>=1.0.0

# === データ処理 ===
pandas>=2.1.0
numpy>=1.26.0
pyarrow>=14.0.0          # parquet読み書き
pyjanitor>=0.26.0        # 便利な前処理関数

# === 時系列予測 ===
prophet>=1.1.5           # Facebook Prophet
statsmodels>=0.14.0      # ARIMA、指数平滑法
scikit-learn>=1.3.0      # スケーリング、評価指標

# === 可視化 ===
plotly>=5.17.0           # インタラクティブグラフ（HTMLエクスポート可）
kaleido>=0.2.1           # Plotly の静的画像書き出し
folium>=0.15.0           # （補助）地図
geopandas>=0.14.0        # 地理データ処理（GeoJSON操作）
matplotlib>=3.8.0        # EDA時のスケッチ用

# === 開発ツール ===
jupyter>=1.0.0
ipywidgets>=8.1.0        # ノートブック内インタラクティブ
black>=23.10.0           # コードフォーマッタ
ruff>=0.1.5              # 高速リンター
pytest>=7.4.0            # テスト
mypy>=1.6.0              # 静的型チェック

# === ロギング ===
loguru>=0.7.2            # シンプルなロガー
```

### 3.2 ライブラリ選定の根拠

| カテゴリ      | 採用ライブラリ          | 理由                                                    |
| --------- | ---------------- | ----------------------------------------------------- |
| 時系列予測     | Prophet          | 非エンジニアにも説明しやすい、季節性・休日効果を自動考慮、信頼区間が標準で出る               |
| 時系列予測（補助） | statsmodels      | ARIMA で「古典的アプローチ」と Prophet の比較ができ、分析の厚みが増す            |
| 可視化       | Plotly           | HTML エクスポートで GitHub Pages にそのまま載せられる、3D・地図・アニメーション全対応 |
| 地理データ     | geopandas        | 都道府県 GeoJSON の操作・座標変換に必須                              |
| データ保存     | parquet（pyarrow） | CSV より圧縮率が高く読込が速い、列志向で部分読み込み可                         |
| ロギング      | loguru           | 標準 logging より設定が圧倒的にシンプル、API 取得の進捗追跡に便利               |

### 3.3 別途必要なもの

- **e-Stat アプリケーション ID**: [https://www.e-stat.go.jp/api/](https://www.e-stat.go.jp/api/) で無料登録（メール認証のみ、即時発行）
- **都道府県境界 GeoJSON**: 国土地理院 または GitHub の公開リポジトリ（[dataofjapan/land](https://github.com/dataofjapan/land) 等）から取得
- **Python バージョン**: 3.11 以上を推奨（Prophet の互換性の都合）

---

## 4. 週次マイルストーン

実働12日を3週間に分割。1日あたり3〜4時間想定。

### Week 1（Day 1〜4）: データ基盤の構築

**ゴール**: 全都道府県・年齢階級別の人口データが pandas DataFrame として手元にある状態

| Day | 主タスク                                                                                                                           | 成果物                                      |
| --- | ------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------- |
| 1   | プロジェクト初期化／e-Stat APIキー取得／GitHubリポジトリ作成／ディレクトリ構造構築／`.env.example`・`.gitignore`・`requirements.txt` 整備／仮想環境セットアップ                 | リポジトリの初期コミット                             |
| 2   | e-Stat APIクライアント（`src/api/estat_client.py`）の実装／1都道府県・1年分のデータ取得テスト／レート制限・エラーハンドリングの実装                                           | API クライアント＋ユニットテスト                       |
| 3   | 全47都道府県・1990〜2020年分の人口データ取得（年齢階級別含む）／SQLite キャッシュへの保存／取得スクリプト `scripts/fetch_data.py` 完成                                       | `data/raw/estat_cache.sqlite`（数十MB想定）    |
| 4   | EDA ノートブック（`01_data_exploration.ipynb`）／データ品質チェック（欠損・外れ値）／前処理パイプライン（`src/preprocessing/`）／`02_preprocessing.ipynb` で処理プロセスを可視化 | `data/processed/population_long.parquet` |

**Week 1 の完了判定**:

- 47都道府県 × 31年（1990〜2020）× 年齢階級のデータが parquet で保存されている
- 同じスクリプトを再実行しても結果が再現される（キャッシュ含む）

---

### Week 2（Day 5〜8）: 予測モデルの構築・検証

**ゴール**: 2040年・2050年の予測値が確定し、社人研の公式推計と比較できる状態

| Day | 主タスク                                                                                        | 成果物                                       |
| --- | ------------------------------------------------------------------------------------------- | ----------------------------------------- |
| 5   | コーホート要因法の実装（`src/models/cohort_method.py`）／出生率・死亡率・移動率の算出／2025〜2050年の推計実行                   | `data/forecast/cohort_2050.parquet`       |
| 6   | Prophet による時系列予測（`src/models/prophet_model.py`）／ARIMA による補助予測／都道府県ごとに自動学習・予測する仕組み           | `data/forecast/prophet_2050.parquet`      |
| 7   | モデル評価（MAPE / RMSE）／2015〜2020年を検証期間として精度測定／社人研推計値との突合／`03_forecasting_models.ipynb` で比較レポート化 | 評価レポート Notebook                           |
| 8   | フロント用 JSON の生成（`scripts/build_site.py`）／集計・軽量化（47都道府県 × 年代 × 年齢階級）／GeoJSON とのマージ            | `web/static/data/prefectures.json`（数MB以下） |

**Week 2 の完了判定**:

- コーホート法・Prophet の2モデルで 2050年予測値が手元にある
- 社人研推計との誤差が ±5% 以内に収まる（収まらない場合は原因を文書化）
- フロント用JSONが完成し、ブラウザから fetch できる形式になっている

---

### Week 3（Day 9〜12）: フロントエンド実装・公開

**ゴール**: 一般の閲覧者が触って楽しめる Web サイトとして公開できる状態

| Day | 主タスク                                                                                       | 成果物                   |
| --- | ------------------------------------------------------------------------------------------ | --------------------- |
| 9   | トップページ（`web/index.html`）の実装／日本地図のコロプレスマップ（Plotly Mapbox）／年代スライダー（1990→2050）／クリックで都道府県詳細へ遷移 | `index.html` 動作版      |
| 10  | 都道府県詳細ページ（`web/prefecture.html`）／人口ピラミッドのアニメーション／時系列グラフ（実績＋予測＋信頼区間）／戻る動線                   | `prefecture.html` 動作版 |
| 11  | スタイリング（`main.css` / `responsive.css`）／スマホ対応／`about.html`（データソース・手法・免責事項）／解説テキスト執筆／OG画像作成   | デザイン完成版               |
| 12  | GitHub Pages 設定／カスタムドメイン（任意）／README整備（セットアップ・スクリーンショット・分析ハイライト）／LinkedIn・ポートフォリオサイトへのリンク追加 | 公開URL                 |

**Week 3 の完了判定**:

- 公開URLにアクセスして、地図→都道府県選択→ピラミッドの一連が動く
- スマホで閲覧できる
- README から「データの取得 → 予測 → 公開」の手順が再現できる

---

## 5. リスクと対策

| リスク                     | 影響度 | 対策                                                                    |
| ----------------------- | --- | --------------------------------------------------------------------- |
| e-Stat API のレート制限・障害    | 中   | SQLite キャッシュで2回目以降は再取得不要に。`tenacity` でリトライ実装                          |
| Prophet のインストール失敗（OS依存） | 中   | 失敗時は ARIMA 単独でも作品成立する設計に。Docker化も視野                                   |
| GeoJSON のサイズが大きく重い      | 低   | `mapshaper` で簡略化（ファイルサイズを 1/10 に圧縮可）                                  |
| 予測精度が社人研より大きく外れる        | 中   | 「公的推計と比較した考察」自体を作品の見どころにする（精度競争でなく手法理解のアピール）                          |
| 12日で終わらない               | 中   | Week 3 の Day 11（スタイリング）と Day 12（公開準備）は圧縮可能。最低限 `index.html` だけでも公開を優先 |

---

## 6. 完成の定義（Definition of Done）

公開時点で次の全項目が満たされていること。

- 公開URL（GitHub Pages）が存在し、リンクをクリックして閲覧できる
- トップ画面で年代スライダーを動かすと地図の色が即座に変わる
- 都道府県をクリックすると詳細ページに遷移し、人口ピラミッドが30秒以内のアニメーションで1990→2050を再生する
- About ページにデータソース（e-Stat）、手法（コーホート要因法 / Prophet）、免責事項（あくまで個人による試算）が明記されている
- README に最低限「セットアップ手順・データ取得コマンド・ライセンス」が書かれている
- リポジトリが Public で誰でも閲覧できる
- LinkedIn または個人ポートフォリオから当サイトへのリンクが設置されている

---

## 7. 次のアクション

着手にあたっての最初の3ステップ。

1. **e-Stat アプリケーションIDの取得**（[https://www.e-stat.go.jp/api/](https://www.e-stat.go.jp/api/)、所要10分）
2. **GitHub リポジトリの作成**（リポジトリ名: `estat-population-forecast` 推奨、Public）
3. **Day 1 の作業開始**（仮想環境構築・初期ファイル整備）

---

*本計画書は実装の進捗に応じて随時更新する。仕様変更・スコープ調整があった場合は本書末尾に変更履歴を記載する。*
