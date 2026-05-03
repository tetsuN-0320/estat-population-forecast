"""モデル評価スクリプト。

実行方法:
    python scripts/evaluate.py

出力:
    - バックテスト結果（2015・2020年の予測精度）
    - 社人研推計との比較（全国・都道府県別）
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import pandas as pd

from config.settings import FORECAST_DIR, PROCESSED_DIR
from src.models.evaluator import ModelEvaluator
from src.utils.logger import logger


def main() -> None:
    df_pyramid = pd.read_parquet(PROCESSED_DIR / "age_pyramid.parquet")
    evaluator = ModelEvaluator()

    # ----------------------------------------------------------------
    # 1. コーホート法バックテスト
    # ----------------------------------------------------------------
    logger.info("=== バックテスト開始 ===")
    df_bt = evaluator.backtest_cohort(df_pyramid)
    stats = evaluator.summarize(df_bt, "コーホート法")

    print("\n" + "=" * 60)
    print("【バックテスト結果】1990〜2010年で学習 → 2015・2020年を予測")
    print("=" * 60)
    print(f"  MAPE（平均絶対誤差率）平均  : {stats['mape_mean']:.2f}%")
    print(f"  MAPE 中央値                : {stats['mape_median']:.2f}%")
    print(f"  RMSE                       : {stats['rmse']/10000:.1f}万人")

    # 年別 MAPE
    print("\n  年別 MAPE:")
    for year, grp in df_bt.groupby("year"):
        print(f"    {year}年: MAPE平均={grp['mape'].mean():.2f}%")

    # 誤差の大きい都道府県 Top5
    worst = df_bt.nlargest(5, "mape")[["pref_name", "year", "actual", "predicted", "mape"]]
    print("\n  誤差が大きかった都道府県 Top5:")
    print(worst.to_string(index=False))

    # 誤差の小さい都道府県 Top5
    best = df_bt.nsmallest(5, "mape")[["pref_name", "year", "actual", "predicted", "mape"]]
    print("\n  誤差が小さかった都道府県 Top5:")
    print(best.to_string(index=False))

    # ----------------------------------------------------------------
    # 2. 社人研推計との比較（全国）
    # ----------------------------------------------------------------
    print("\n" + "=" * 60)
    print("【社人研推計との比較（全国総人口）】")
    print("=" * 60)

    model_files = {
        "コーホート法": "cohort_2050.parquet",
        "Prophet":     "prophet_2050.parquet",
        "ARIMA":       "arima_2050.parquet",
    }

    for model_name, fname in model_files.items():
        fpath = FORECAST_DIR / fname
        if not fpath.exists():
            print(f"  {model_name}: ファイルなし（スキップ）")
            continue
        df_fore = pd.read_parquet(fpath)
        df_cmp = evaluator.compare_with_ipss(df_fore, model_name)
        print(f"\n  ── {model_name} ──")
        print(df_cmp.to_string(index=False))

    # ----------------------------------------------------------------
    # 3. 社人研推計との比較（都道府県別 2050年）
    # ----------------------------------------------------------------
    print("\n" + "=" * 60)
    print("【社人研との比較（都道府県別 2050年）コーホート法】")
    print("=" * 60)

    cohort_path = FORECAST_DIR / "cohort_2050.parquet"
    if cohort_path.exists():
        df_cohort = pd.read_parquet(cohort_path)
        df_pref = evaluator.compare_pref_2050(df_cohort, "コーホート法")
        mape_pref = df_pref["差_%"].abs().mean()
        print(f"\n  都道府県別 MAPE（社人研比）: {mape_pref:.1f}%")
        print("\n  差が大きい都道府県（過大推計 上位5）:")
        print(df_pref.tail(5).to_string(index=False))
        print("\n  差が大きい都道府県（過小推計 上位5）:")
        print(df_pref.head(5).to_string(index=False))

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
