"""予測モデル実行スクリプト。

実行方法:
    python scripts/run_forecast.py            # 全モデル実行
    python scripts/run_forecast.py --model cohort
    python scripts/run_forecast.py --model prophet
    python scripts/run_forecast.py --model arima

出力:
    data/forecast/cohort_2050.parquet
    data/forecast/prophet_2050.parquet
    data/forecast/arima_2050.parquet
"""

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import pandas as pd

from config.settings import FORECAST_DIR, PROCESSED_DIR
from src.models.cohort_method import CohortProjector
from src.utils.logger import logger


def run_cohort(df_pyramid: pd.DataFrame) -> None:
    logger.info("--- コーホート要因法 ---")
    projector = CohortProjector(n_recent_periods=3)
    df = projector.fit_predict(df_pyramid)
    out = FORECAST_DIR / "cohort_2050.parquet"
    df.to_parquet(out, index=False)
    logger.info(f"保存: {out} ({out.stat().st_size / 1024:.1f} KB)")
    _print_total_summary("コーホート法", df)


def run_prophet(df_pyramid: pd.DataFrame) -> None:
    logger.info("--- Prophet 時系列予測 ---")
    from src.models.prophet_model import ProphetPopulationForecaster
    forecaster = ProphetPopulationForecaster()
    df = forecaster.fit_predict(df_pyramid)
    out = FORECAST_DIR / "prophet_2050.parquet"
    df.to_parquet(out, index=False)
    logger.info(f"保存: {out} ({out.stat().st_size / 1024:.1f} KB)")
    _print_total_summary("Prophet", df)


def run_arima(df_pyramid: pd.DataFrame) -> None:
    logger.info("--- ARIMA 時系列予測 ---")
    from src.models.arima_model import ArimaPopulationForecaster
    forecaster = ArimaPopulationForecaster()
    df = forecaster.fit_predict(df_pyramid)
    out = FORECAST_DIR / "arima_2050.parquet"
    df.to_parquet(out, index=False)
    logger.info(f"保存: {out} ({out.stat().st_size / 1024:.1f} KB)")
    _print_total_summary("ARIMA", df)


def _print_total_summary(model_name: str, df: pd.DataFrame) -> None:
    """全国総人口の推移を表示する。"""
    total = (
        df.groupby("year")[["male", "female"]].sum()
        .assign(total=lambda d: d["male"] + d["female"])["total"]
    )
    print(f"\n【{model_name}】全国総人口（万人）")
    for year, pop in total.items():
        print(f"  {year}年: {pop / 10000:,.0f}万人")


def main() -> None:
    parser = argparse.ArgumentParser(description="人口予測モデル実行スクリプト")
    parser.add_argument(
        "--model",
        choices=["cohort", "prophet", "arima", "all"],
        default="all",
        help="実行するモデル（デフォルト: all）",
    )
    args = parser.parse_args()

    input_path = PROCESSED_DIR / "age_pyramid.parquet"
    if not input_path.exists():
        logger.error(f"入力ファイルが見つかりません: {input_path}")
        logger.info("先に scripts/preprocess.py を実行してください")
        sys.exit(1)

    FORECAST_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("=== 予測モデル実行開始 ===")
    df_pyramid = pd.read_parquet(input_path)

    targets = (
        ["cohort", "prophet", "arima"] if args.model == "all" else [args.model]
    )

    for model in targets:
        try:
            if model == "cohort":
                run_cohort(df_pyramid)
            elif model == "prophet":
                run_prophet(df_pyramid)
            elif model == "arima":
                run_arima(df_pyramid)
        except ImportError as e:
            logger.warning(f"{model} をスキップ: {e}")

    logger.info("=== 全モデル完了 ===")


if __name__ == "__main__":
    main()
