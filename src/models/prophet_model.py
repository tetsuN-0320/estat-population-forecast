"""Prophet による都道府県別総人口の時系列予測モジュール。

## 設計方針
- 47都道府県それぞれについて男女合計の総人口を Prophet で予測する
- データ点数が7点（1990〜2020年の5年間隔）と少ないため、
  季節性をすべて無効化し、トレンドのみを学習させる
- 予測結果は 2025〜2050年の5年間隔で出力する
- 年齢区分別の内訳はコーホート法の年齢構成比を使って按分する

## 出力形式
cohort_2050.parquet と同一スキーマ:
  pref_code, pref_name, year, age_group, male, female
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from src.utils.logger import logger

FORECAST_YEARS = [2025, 2030, 2035, 2040, 2045, 2050]
HISTORICAL_YEARS = [1990, 1995, 2000, 2005, 2010, 2015, 2020]


class ProphetPopulationForecaster:
    """Prophet を使った都道府県別人口予測クラス。

    Args:
        n_changepoints: トレンド変化点の数（デフォルト 3。データ点が少ないため小さめに設定）
        changepoint_prior_scale: 変化点の柔軟性（大きいほど急な変化を許容）
    """

    def __init__(
        self,
        n_changepoints: int = 3,
        changepoint_prior_scale: float = 0.05,
    ) -> None:
        self.n_changepoints = n_changepoints
        self.changepoint_prior_scale = changepoint_prior_scale
        self._models: dict[str, object] = {}
        self._forecasts: dict[str, pd.DataFrame] = {}

    def fit_predict(self, df_pyramid: pd.DataFrame) -> pd.DataFrame:
        """全都道府県の人口を予測する。

        Args:
            df_pyramid: age_pyramid.parquet の DataFrame。

        Returns:
            cohort_2050.parquet と同スキーマの予測結果 DataFrame。
        """
        try:
            from prophet import Prophet  # type: ignore[import]
        except ImportError:
            raise ImportError(
                "Prophet がインストールされていません。\n"
                "  pip install prophet\n"
                "を実行してください。"
            )

        logger.info("Prophet による人口予測を開始します（47都道府県）")

        # 総人口（男女合計、全年齢合計）の時系列を都道府県ごとに集計
        total_pop = (
            df_pyramid[df_pyramid["age_group"] != "総数"]
            .groupby(["pref_code", "pref_name", "year"])[["male", "female"]]
            .sum()
            .assign(total=lambda d: d["male"] + d["female"])
            .reset_index()
        )

        # 男性比率（将来の男女配分に使用）
        sex_ratio = (
            df_pyramid[df_pyramid["age_group"] != "総数"]
            .groupby(["pref_code", "year"])[["male", "female"]]
            .sum()
            .assign(male_ratio=lambda d: d["male"] / (d["male"] + d["female"]))
            .reset_index()[["pref_code", "year", "male_ratio"]]
        )
        # 直近3期間の平均男性比率を将来に使用
        recent_sex_ratio = (
            sex_ratio[sex_ratio["year"].isin([2010, 2015, 2020])]
            .groupby("pref_code")["male_ratio"]
            .mean()
        )

        # 年齢構成比（コーホート法の構成比を借用して按分する）
        age_struct = self._calc_age_structure(df_pyramid)

        results = []
        pref_codes = total_pop["pref_code"].unique()
        for i, pref_code in enumerate(pref_codes, 1):
            pref_data = total_pop[total_pop["pref_code"] == pref_code]
            pref_name = pref_data["pref_name"].iloc[0]

            # Prophet 用 DataFrame（ds: datetime, y: population）
            df_prophet = pd.DataFrame({
                "ds": pd.to_datetime(
                    pref_data["year"].astype(str) + "-01-01"
                ),
                "y": pref_data["total"].values,
            })

            # Prophet モデルの学習
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = Prophet(
                    yearly_seasonality=False,
                    weekly_seasonality=False,
                    daily_seasonality=False,
                    n_changepoints=self.n_changepoints,
                    changepoint_prior_scale=self.changepoint_prior_scale,
                )
                model.fit(df_prophet)

            # 将来の ds を生成（5年間隔）
            future = pd.DataFrame({
                "ds": pd.to_datetime(
                    [f"{y}-01-01" for y in FORECAST_YEARS]
                )
            })
            forecast = model.predict(future)

            # 予測値（負値は0に補正）
            predicted_totals = np.maximum(forecast["yhat"].values, 0)

            # 男性比率・年齢構成比を使って男女別・年齢別に按分
            male_ratio = recent_sex_ratio.get(pref_code, 0.487)
            pref_age_struct = age_struct[age_struct["pref_code"] == pref_code]

            for year, total in zip(FORECAST_YEARS, predicted_totals):
                for _, row in pref_age_struct.iterrows():
                    age_group = row["age_group"]
                    age_share = row["share"]
                    age_total = total * age_share
                    results.append({
                        "pref_code": pref_code,
                        "pref_name": pref_name,
                        "year": year,
                        "age_group": age_group,
                        "male": max(0, round(age_total * male_ratio)),
                        "female": max(0, round(age_total * (1 - male_ratio))),
                    })

            if i % 10 == 0:
                logger.info(f"  進捗: {i}/{len(pref_codes)} 都道府県完了")

        logger.info("Prophet 予測完了")
        df_result = pd.DataFrame(results)
        df_result["year"] = df_result["year"].astype("int16")
        return df_result

    def _calc_age_structure(self, df_pyramid: pd.DataFrame) -> pd.DataFrame:
        """直近（2020年）の年齢構成比を都道府県ごとに計算する。

        Returns:
            列: pref_code, age_group, share
        """
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
