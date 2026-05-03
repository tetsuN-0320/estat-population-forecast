"""フロントエンド用データ生成スクリプト。

parquet ファイルを読み込み、Web サイト用の軽量 JSON を生成する。

実行方法:
    python scripts/build_site.py

出力:
    web/static/data/prefectures.json  ← 地図・ピラミッド用メインデータ
    web/static/data/national.json     ← 全国トレンド用

## JSON 設計方針
- フロントエンドが fetch して即座に使える形式
- 地図スライダー用: 都道府県 × 年の総人口
- ピラミッド用: 都道府県 × 年 × 年齢区分の男女別人口
- ファイルサイズを最小化（整数値・不要フィールドを除外）
"""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import pandas as pd

from config.settings import FORECAST_DIR, PROCESSED_DIR, WEB_DATA_DIR
from src.utils.logger import logger

# ピラミッド用に出力する年（全年だとサイズが大きいので絞る）
PYRAMID_YEARS = [1990, 2000, 2010, 2020, 2030, 2040, 2050]

# 年齢区分の表示順
AGE_ORDER = [
    "0-4", "5-9", "10-14", "15-19", "20-24",
    "25-29", "30-34", "35-39", "40-44", "45-49",
    "50-54", "55-59", "60-64", "65-69", "70-74",
    "75-79", "80-84", "85+",
]


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    """全データを読み込む。"""
    logger.info("データ読み込み中...")
    df_hist = pd.read_parquet(PROCESSED_DIR / "age_pyramid.parquet")

    forecasts: dict[str, pd.DataFrame] = {}
    for model in ["cohort", "prophet", "arima"]:
        fpath = FORECAST_DIR / f"{model}_2050.parquet"
        if fpath.exists():
            forecasts[model] = pd.read_parquet(fpath)
            logger.info(f"  {model}: {len(forecasts[model]):,}行")
        else:
            logger.warning(f"  {model}: ファイルなし（スキップ）")

    return df_hist, forecasts


def build_prefectures_json(
    df_hist: pd.DataFrame,
    forecasts: dict[str, pd.DataFrame],
) -> list[dict]:
    """都道府県ごとのデータを組み立てる。"""
    pref_list = []
    pref_codes = sorted(df_hist["pref_code"].unique())

    for pref_code in pref_codes:
        pref_name = df_hist.loc[df_hist["pref_code"] == pref_code, "pref_name"].iloc[0]

        # ---- 総人口時系列（地図スライダー用）----
        # 実績（1990〜2020）
        hist_pref = df_hist[
            (df_hist["pref_code"] == pref_code)
            & (df_hist["age_group"] != "総数")
        ]
        history: dict[str, dict] = {}
        for year, grp in hist_pref.groupby("year"):
            history[str(year)] = {
                "total": int((grp["male"] + grp["female"]).sum()),
                "male":  int(grp["male"].sum()),
                "female": int(grp["female"].sum()),
            }

        # 予測（2025〜2050）各モデル
        forecast_totals: dict[str, dict[str, dict]] = {}
        for model, df_fore in forecasts.items():
            fore_pref = df_fore[df_fore["pref_code"] == pref_code]
            model_data: dict[str, dict] = {}
            for year, grp in fore_pref.groupby("year"):
                model_data[str(year)] = {
                    "total": int((grp["male"] + grp["female"]).sum()),
                    "male":  int(grp["male"].sum()),
                    "female": int(grp["female"].sum()),
                }
            forecast_totals[model] = model_data

        # ---- 人口ピラミッド（アニメーション用）----
        pyramid: dict[str, list] = {}

        # 実績年のピラミッド
        for year in [y for y in PYRAMID_YEARS if y <= 2020]:
            yr_data = hist_pref[hist_pref["year"] == year].set_index("age_group")
            pyramid[str(year)] = [
                {
                    "age": age,
                    "male":   int(yr_data.at[age, "male"])   if age in yr_data.index else 0,
                    "female": int(yr_data.at[age, "female"]) if age in yr_data.index else 0,
                }
                for age in AGE_ORDER
            ]

        # 予測年のピラミッド（コーホート法を使用）
        if "cohort" in forecasts:
            fore_pref = forecasts["cohort"][forecasts["cohort"]["pref_code"] == pref_code]
            for year in [y for y in PYRAMID_YEARS if y > 2020]:
                yr_data = fore_pref[fore_pref["year"] == year].set_index("age_group")
                pyramid[str(year)] = [
                    {
                        "age": age,
                        "male":   int(yr_data.at[age, "male"])   if age in yr_data.index else 0,
                        "female": int(yr_data.at[age, "female"]) if age in yr_data.index else 0,
                    }
                    for age in AGE_ORDER
                ]

        # ---- 変化率（2020→2050, コーホート法）----
        pop_2020 = history.get("2020", {}).get("total", 0)
        pop_2050_cohort = forecast_totals.get("cohort", {}).get("2050", {}).get("total", 0)
        change_pct = (
            round((pop_2050_cohort / pop_2020 - 1) * 100, 1)
            if pop_2020 > 0 and pop_2050_cohort > 0 else None
        )

        pref_list.append({
            "code":       pref_code,
            "name":       pref_name,
            "history":    history,
            "forecast":   forecast_totals,
            "pyramid":    pyramid,
            "change_pct_2020_2050": change_pct,
        })

    return pref_list


def build_national_json(
    df_hist: pd.DataFrame,
    forecasts: dict[str, pd.DataFrame],
) -> dict:
    """全国トレンドデータを組み立てる。"""
    hist_total = (
        df_hist[df_hist["age_group"] != "総数"]
        .groupby("year")[["male", "female"]].sum()
        .assign(total=lambda d: d["male"] + d["female"])
        .reset_index()
    )

    history = {
        str(int(row["year"])): {
            "total":  int(row["total"]),
            "male":   int(row["male"]),
            "female": int(row["female"]),
        }
        for _, row in hist_total.iterrows()
    }

    forecast_totals: dict[str, dict] = {}
    for model, df_fore in forecasts.items():
        fore_total = (
            df_fore.groupby("year")[["male", "female"]].sum()
            .assign(total=lambda d: d["male"] + d["female"])
            .reset_index()
        )
        forecast_totals[model] = {
            str(int(row["year"])): {
                "total":  int(row["total"]),
                "male":   int(row["male"]),
                "female": int(row["female"]),
            }
            for _, row in fore_total.iterrows()
        }

    # 社人研推計（参考値）
    ipss = {
        "2025": 122540000, "2030": 119130000, "2035": 115300000,
        "2040": 110920000, "2045": 106420000, "2050": 104690000,
    }

    return {
        "history": history,
        "forecast": forecast_totals,
        "ipss": ipss,
    }


def main() -> None:
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)

    df_hist, forecasts = load_data()

    # ---- prefectures.json ----
    logger.info("prefectures.json を生成中...")
    pref_data = build_prefectures_json(df_hist, forecasts)

    output = {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "historical_years": [1990, 1995, 2000, 2005, 2010, 2015, 2020],
            "forecast_years":   [2025, 2030, 2035, 2040, 2045, 2050],
            "pyramid_years":    PYRAMID_YEARS,
            "models":           list(forecasts.keys()),
        },
        "prefectures": pref_data,
    }

    out_pref = WEB_DATA_DIR / "prefectures.json"
    with open(out_pref, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = out_pref.stat().st_size / 1024
    logger.info(f"保存: {out_pref} ({size_kb:.1f} KB)")

    # ---- national.json ----
    logger.info("national.json を生成中...")
    national = build_national_json(df_hist, forecasts)

    out_nat = WEB_DATA_DIR / "national.json"
    with open(out_nat, "w", encoding="utf-8") as f:
        json.dump(national, f, ensure_ascii=False, separators=(",", ":"))

    size_kb_nat = out_nat.stat().st_size / 1024
    logger.info(f"保存: {out_nat} ({size_kb_nat:.1f} KB)")

    # ---- サマリー ----
    print("\n" + "=" * 55)
    print("【build_site.py 完了】")
    print("=" * 55)
    print(f"  prefectures.json : {out_pref.stat().st_size / 1024:.1f} KB  ({len(pref_data)}都道府県)")
    print(f"  national.json    : {out_nat.stat().st_size / 1024:.1f} KB")
    print(f"  含まれるモデル   : {', '.join(forecasts.keys())}")
    print(f"  ピラミッド年     : {PYRAMID_YEARS}")
    print()
    print("【2050年 人口変化率 上位・下位】")
    sorted_prefs = sorted(pref_data, key=lambda p: p["change_pct_2020_2050"] or 0)
    print("  減少率 Top5:")
    for p in sorted_prefs[:5]:
        print(f"    {p['name']}: {p['change_pct_2020_2050']:+.1f}%")
    print("  増加/減少少 Top5:")
    for p in sorted_prefs[-5:]:
        print(f"    {p['name']}: {p['change_pct_2020_2050']:+.1f}%")
    print("=" * 55)


if __name__ == "__main__":
    main()
