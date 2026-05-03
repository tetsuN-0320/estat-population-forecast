"""予測モデル実行スクリプト。

実行方法:
    python scripts/run_forecast.py

出力:
    data/forecast/cohort_2050.parquet
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import pandas as pd

from config.settings import FORECAST_DIR, PROCESSED_DIR
from src.models.cohort_method import CohortProjector
from src.utils.logger import logger


def main() -> None:
    input_path = PROCESSED_DIR / "age_pyramid.parquet"
    if not input_path.exists():
        logger.error(f"入力ファイルが見つかりません: {input_path}")
        logger.info("先に scripts/preprocess.py を実行してください")
        sys.exit(1)

    logger.info("=== 予測モデル実行開始 ===")
    df_pyramid = pd.read_parquet(input_path)

    # コーホート要因法
    projector = CohortProjector(n_recent_periods=3)
    df_forecast = projector.fit_predict(df_pyramid)

    FORECAST_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FORECAST_DIR / "cohort_2050.parquet"
    df_forecast.to_parquet(out_path, index=False)
    logger.info(f"保存完了: {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")

    # サマリー表示
    _print_summary(df_pyramid, df_forecast)


def _print_summary(df_hist: pd.DataFrame, df_fore: pd.DataFrame) -> None:
    print("\n" + "=" * 55)
    print("【コーホート要因法 推計結果サマリー】")
    print("=" * 55)

    # 全国総人口の推移
    hist_total = (
        df_hist[df_hist["age_group"] != "総数"]
        .groupby("year")[["male", "female"]].sum()
        .assign(total=lambda d: d["male"] + d["female"])["total"]
    )
    fore_total = (
        df_fore.groupby("year")[["male", "female"]].sum()
        .assign(total=lambda d: d["male"] + d["female"])["total"]
    )

    print("\n【全国総人口（万人）】")
    print("  実績:")
    for year, pop in hist_total.items():
        print(f"    {year}年: {pop/10000:,.0f}万人")
    print("  推計:")
    for year, pop in fore_total.items():
        print(f"    {year}年: {pop/10000:,.0f}万人")

    # 都道府県別 2050年 人口トップ5・ワースト5
    pref_2050 = (
        df_fore[df_fore["year"] == 2050]
        .groupby(["pref_code", "pref_name"])[["male", "female"]].sum()
        .assign(total=lambda d: d["male"] + d["female"])
        .reset_index()
        .sort_values("total", ascending=False)
    )
    print("\n【2050年 都道府県別人口 上位5】")
    for _, row in pref_2050.head(5).iterrows():
        print(f"  {row['pref_name']}: {row['total']/10000:,.0f}万人")
    print("【2050年 都道府県別人口 下位5】")
    for _, row in pref_2050.tail(5).iterrows():
        print(f"  {row['pref_name']}: {row['total']/10000:,.0f}万人")

    # 2020→2050 の変化率（都道府県別）
    pref_2020 = (
        df_fore[df_fore["year"] == 2020]  # ない場合は hist から取る
    )
    hist_2020 = (
        df_hist[(df_hist["year"] == 2020) & (df_hist["age_group"] != "総数")]
        .groupby(["pref_code", "pref_name"])[["male", "female"]].sum()
        .assign(total_2020=lambda d: d["male"] + d["female"])
        .reset_index()
    )
    fore_2050_merge = pref_2050[["pref_code", "total"]].rename(columns={"total": "total_2050"})
    change = hist_2020.merge(fore_2050_merge, on="pref_code").assign(
        change_pct=lambda d: (d["total_2050"] / d["total_2020"] - 1) * 100
    ).sort_values("change_pct")

    print("\n【2020→2050 人口変化率 最大減少5都道府県】")
    for _, row in change.head(5).iterrows():
        print(f"  {row['pref_name']}: {row['change_pct']:+.1f}%")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
