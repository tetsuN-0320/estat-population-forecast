"""ARIMA による都道府県別総人口の時系列予測モジュール（Prophet の補助・代替）。

## 設計方針
- Prophet と同じ入出力インターフェースを持つ
- データ点数が少ない（7点）ため、自由度の低いモデルを使う
  - ARIMA(1,1,0): 1次差分＋AR(1) 項 → トレンドを捉えやすい
  - 収束しない場合は指数平滑法（SimpleExpSmoothing）にフォールバック
- 出力形式は cohort_2050.parquet と同一

## 使用方法
    from src.models.arima_model import ArimaPopulationForecaster
    forecaster = ArimaPopulationForecaster()
    df_forecast = forecaster.fit_predict(df_pyramid)
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from src.utils.logger import logger

FORECAST_YEARS = [2025, 2030, 2035, 2040, 2045, 2050]


class ArimaPopulationForecaster:
    """ARIMA を使った都道府県別人口予測クラス。

    Args:
        order: ARIMA の (p, d, q) オーダー（デフォルト (1, 1, 0)）。
    """

    def __init__(self, order: tuple[int, int, int] = (1, 1, 0)) -> None:
        self.order = order

    def fit_predict(self, df_pyramid: pd.DataFrame) -> pd.DataFrame:
        """全都道府県の人口を予測する。

        Args:
            df_pyramid: age_pyramid.parquet の DataFrame。

        Returns:
            cohort_2050.parquet と同スキーマの予測結果 DataFrame。
        """
        try:
            from statsmodels.tsa.arima.model import ARIMA  # type: ignore[import]
            from statsmodels.tsa.holtwinters import SimpleExpSmoothing  # type: ignore[import]
        except ImportError:
            raise ImportError(
                "statsmodels がインストールされていません。\n"
                "  pip install statsmodels\n"
                "を実行してください。"
            )

        logger.info("ARIMA による人口予測を開始します（47都道府県）")

        # 総人口（男女合計）の時系列を集計
        total_pop = (
            df_pyramid[df_pyramid["age_group"] != "総数"]
            .groupby(["pref_code", "pref_name", "year"])[["male", "female"]]
            .sum()
            .assign(total=lambda d: d["male"] + d["female"])
            .reset_index()
            .sort_values(["pref_code", "year"])
        )

        # 直近3期間の平均男性比率
        recent_sex_ratio = (
            total_pop[total_pop["year"].isin([2010, 2015, 2020])]
            .assign(male_ratio=lambda d: d["male"] / d["total"])
            .groupby("pref_code")["male_ratio"]
            .mean()
        )

        # 年齢構成比（2020年基準）
        age_struct = self._calc_age_structure(df_pyramid)

        results = []
        pref_codes = total_pop["pref_code"].unique()

        for i, pref_code in enumerate(pref_codes, 1):
            pref_data = total_pop[total_pop["pref_code"] == pref_code].sort_values("year")
            pref_name = pref_data["pref_name"].iloc[0]
            y = pref_data["total"].values.astype(float)

            # ARIMA フィット（失敗時は指数平滑法にフォールバック）
            predicted = self._fit_and_predict(y, ARIMA, SimpleExpSmoothing)

            male_ratio = recent_sex_ratio.get(pref_code, 0.487)
            pref_age = age_struct[age_struct["pref_code"] == pref_code]

            for year, total in zip(FORECAST_YEARS, predicted):
                for _, row in pref_age.iterrows():
                    age_total = total * row["share"]
                    results.append({
                        "pref_code": pref_code,
                        "pref_name": pref_name,
                        "year": year,
                        "age_group": row["age_group"],
                        "male": max(0, round(age_total * male_ratio)),
                        "female": max(0, round(age_total * (1 - male_ratio))),
                    })

            if i % 10 == 0:
                logger.info(f"  進捗: {i}/{len(pref_codes)} 都道府県完了")

        logger.info("ARIMA 予測完了")
        df_result = pd.DataFrame(results)
        df_result["year"] = df_result["year"].astype("int16")
        return df_result

    def _fit_and_predict(self, y: np.ndarray, ARIMA: type, SES: type) -> np.ndarray:
        """ARIMA でフィットし、6期先（2025〜2050）を予測する。

        直近3期間（2010〜2020）のトレンドを重視した予測を行う。
        ARIMA が定数予測になる場合は直近トレンド外挿にフォールバック。
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            # 直近3期間の平均変化量（5年あたり）をベースラインとして先に計算
            recent_trend = float(np.mean(np.diff(y[-4:])))

            try:
                model = ARIMA(y, order=self.order)
                result = model.fit()
                forecast = result.forecast(steps=6)
                predicted = np.maximum(forecast, 0)

                # 定数予測（標準偏差が小さすぎる）になった場合は直近トレンド外挿に切替
                if np.std(predicted) < abs(recent_trend) * 0.1:
                    raise ValueError("ARIMA が定数予測になったためトレンド外挿に切替")

                return predicted

            except Exception:
                # 直近トレンド外挿（減少・増加トレンドを確実に反映）
                return np.array([
                    max(0, y[-1] + recent_trend * (k + 1))
                    for k in range(6)
                ])

    def _calc_age_structure(self, df_pyramid: pd.DataFrame) -> pd.DataFrame:
        """直近（2020年）の年齢構成比を都道府県ごとに計算する。"""
        df_2020 = df_pyramid[
            (df_pyramid["year"] == 2020)
            & (df_pyramid["age_group"] != "総数")
        ].copy()
        df_2020["total"] = df_2020["male"] + df_2020["female"]
        pref_total = df_2020.groupby("pref_code")["total"].sum()
        df_2020["share"] = df_2020.apply(
            lambda r: r["total"] / pref_total[r["pref_code"]]
            if pref_total[r["pref_code"]] > 0 else 0,
            axis=1,
        )
        return df_2020[["pref_code", "age_group", "share"]].copy()
