"""コーホート要因法による人口推計モジュール。

国勢調査（1990〜2020年）の実績値から「コーホート変化率」を算出し、
2025〜2050年の都道府県別・年齢階級別・男女別人口を推計する。

## コーホート要因法の原理
5年ごとの国勢調査データを使い、各コーホート（同一年齢階級集団）が
次の5年間でどのくらい変化したか（生残り＋純移動）を実績から推定する。

  変化率(age, t→t+5) = P(age+5, t+5) / P(age, t)

この変化率は死亡・移動を一括して捉えた「純変化率」。
出生（0〜4歳）は女性の出産年齢層（15〜49歳）に対する幼児比率（CWR）で推計。

## 推計の手順
1. 過去の変化率を期間ごとに計算
2. 直近 n 期間の平均変化率を採用（デフォルト: 直近3期間 = 2005〜2020）
3. 2020年を起点に 5年ステップで 2050年まで投影
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.utils.logger import logger

# 分析対象の年齢区分（昇順）
AGE_GROUPS: list[str] = [
    "0-4", "5-9", "10-14", "15-19", "20-24",
    "25-29", "30-34", "35-39", "40-44", "45-49",
    "50-54", "55-59", "60-64", "65-69", "70-74",
    "75-79", "80-84", "85+",
]

# 年齢区分 → インデックスの対応表
AGE_INDEX: dict[str, int] = {ag: i for i, ag in enumerate(AGE_GROUPS)}

# 女性の出産可能年齢層（CWR 計算に使用）
CHILDBEARING_AGES: list[str] = [
    "15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49"
]

# 推計期間
HISTORICAL_YEARS = [1990, 1995, 2000, 2005, 2010, 2015, 2020]
FORECAST_YEARS   = [2025, 2030, 2035, 2040, 2045, 2050]


class CohortProjector:
    """コーホート変化率法による人口推計クラス。

    Args:
        n_recent_periods: 変化率の平均を取る直近期間数（デフォルト 3 = 2005〜2020）。
    """

    def __init__(self, n_recent_periods: int = 3) -> None:
        self.n_recent_periods = n_recent_periods
        self._rates: pd.DataFrame | None = None  # 算出済み変化率（キャッシュ）

    # ------------------------------------------------------------------
    # 公開API
    # ------------------------------------------------------------------

    def fit(self, df_pyramid: pd.DataFrame) -> "CohortProjector":
        """実績データから変化率を算出する。

        Args:
            df_pyramid: age_pyramid.parquet の DataFrame。
                        列: pref_code, pref_name, year, age_group, male, female

        Returns:
            self（メソッドチェーン可）
        """
        logger.info("コーホート変化率の算出を開始します")
        rates = self._calc_cohort_rates(df_pyramid)
        self._rates = self._average_recent_rates(rates)
        logger.info(
            f"変化率算出完了（直近{self.n_recent_periods}期間平均）: "
            f"{self._rates['pref_code'].nunique()}都道府県"
        )
        return self

    def predict(self, df_pyramid: pd.DataFrame) -> pd.DataFrame:
        """2025〜2050年の人口を推計する。

        Args:
            df_pyramid: age_pyramid.parquet の DataFrame（2020年データが必要）。

        Returns:
            列: pref_code, pref_name, year, age_group, male, female
            forecast_years 分の行を含む DataFrame。
        """
        if self._rates is None:
            raise RuntimeError("fit() を先に呼んでください")

        logger.info("人口推計を開始します（2025〜2050年）")
        base = df_pyramid[df_pyramid["year"] == 2020].copy()

        # 都道府県ごとに推計
        results = []
        for pref_code in base["pref_code"].unique():
            pref_result = self._project_prefecture(
                base[base["pref_code"] == pref_code],
                pref_code,
            )
            results.append(pref_result)

        df_forecast = pd.concat(results, ignore_index=True)
        df_forecast["year"] = df_forecast["year"].astype("int16")
        logger.info(f"推計完了: {len(df_forecast):,}行")
        return df_forecast

    def fit_predict(self, df_pyramid: pd.DataFrame) -> pd.DataFrame:
        """fit() と predict() を一括実行する。"""
        return self.fit(df_pyramid).predict(df_pyramid)

    # ------------------------------------------------------------------
    # 内部処理
    # ------------------------------------------------------------------

    def _calc_cohort_rates(self, df: pd.DataFrame) -> pd.DataFrame:
        """期間ごとのコーホート変化率を計算する。

        各期間 t→t+5 について:
          - age 0-4〜80-84: rate = P(next_age, t+5) / P(age, t)
          - age 85+        : rate = P(85+, t+5) / [P(80-84, t) + P(85+, t)]
          - CWR (幼児比率) : P(0-4, t) / Σ P(women_childbearing, t)
        """
        records = []
        years = sorted(df["year"].unique())

        for t, t_next in zip(years[:-1], years[1:]):
            for pref_code in df["pref_code"].unique():
                pref_name = df.loc[df["pref_code"] == pref_code, "pref_name"].iloc[0]
                curr = df[(df["pref_code"] == pref_code) & (df["year"] == t)].set_index("age_group")
                nxt  = df[(df["pref_code"] == pref_code) & (df["year"] == t_next)].set_index("age_group")

                for sex in ["male", "female"]:
                    # コーホート変化率（0-4〜80-84 → 次の年齢区分）
                    for i, age in enumerate(AGE_GROUPS[:-2]):  # 0-4〜80-84
                        next_age = AGE_GROUPS[i + 1]
                        if age in curr.index and next_age in nxt.index:
                            p_curr = curr.at[age, sex]
                            p_next = nxt.at[next_age, sex]
                            rate = p_next / p_curr if p_curr > 0 else np.nan
                            records.append({
                                "pref_code": pref_code,
                                "pref_name": pref_name,
                                "period": f"{t}-{t_next}",
                                "t_start": t,
                                "sex": sex,
                                "rate_type": "cohort",
                                "age_group": age,
                                "rate": rate,
                            })

                    # 85+ の変化率（80-84 と 85+ の合計からの生残り）
                    if "80-84" in curr.index and "85+" in curr.index and "85+" in nxt.index:
                        p_curr_85plus = curr.at["80-84", sex] + curr.at["85+", sex]
                        p_next_85plus = nxt.at["85+", sex]
                        rate_85 = p_next_85plus / p_curr_85plus if p_curr_85plus > 0 else np.nan
                        records.append({
                            "pref_code": pref_code,
                            "pref_name": pref_name,
                            "period": f"{t}-{t_next}",
                            "t_start": t,
                            "sex": sex,
                            "rate_type": "cohort_85plus",
                            "age_group": "85+",
                            "rate": rate_85,
                        })

                # 幼児比率 CWR（女性の出産年齢層に対する 0〜4 歳人口比）
                if "0-4" in curr.index:
                    women_cb = sum(
                        curr.at[a, "female"] for a in CHILDBEARING_AGES if a in curr.index
                    )
                    cwr = curr.at["0-4", "female"] + curr.at["0-4", "male"]
                    cwr_rate = (cwr / women_cb) if women_cb > 0 else np.nan
                    records.append({
                        "pref_code": pref_code,
                        "pref_name": pref_name,
                        "period": f"{t}-{t_next}",
                        "t_start": t,
                        "sex": "both",
                        "rate_type": "cwr",
                        "age_group": "0-4",
                        "rate": cwr_rate,
                    })

        return pd.DataFrame(records)

    def _average_recent_rates(self, rates: pd.DataFrame) -> pd.DataFrame:
        """直近 n 期間の平均変化率を計算する。"""
        # 直近 n 期間を選択（t_start の大きい順）
        recent_starts = sorted(rates["t_start"].unique())[-self.n_recent_periods:]
        recent = rates[rates["t_start"].isin(recent_starts)]

        avg = (
            recent
            .groupby(["pref_code", "pref_name", "sex", "rate_type", "age_group"])["rate"]
            .mean()
            .reset_index()
            .rename(columns={"rate": "avg_rate"})
        )
        return avg

    def _project_prefecture(
        self,
        base: pd.DataFrame,
        pref_code: str,
    ) -> pd.DataFrame:
        """1つの都道府県について 2025〜2050年を推計する。"""
        pref_rates = self._rates[self._rates["pref_code"] == pref_code]
        pref_name = base["pref_name"].iloc[0]

        # 現在の人口をインデックス付き辞書で管理
        curr: dict[str, dict[str, float]] = {}
        for row in base.itertuples():
            curr[row.age_group] = {"male": float(row.male), "female": float(row.female)}

        results = []
        for year in FORECAST_YEARS:
            nxt: dict[str, dict[str, float]] = {}

            def get_rate(rate_type: str, age: str, sex: str) -> float:
                """変化率を取得（なければ後退補完として直近実績を使う）。"""
                r = pref_rates[
                    (pref_rates["rate_type"] == rate_type)
                    & (pref_rates["age_group"] == age)
                    & (pref_rates["sex"] == sex)
                ]["avg_rate"]
                return float(r.iloc[0]) if not r.empty and not np.isnan(r.iloc[0]) else 1.0

            # 5-9〜80-84: コーホート変化率を適用
            for i, age in enumerate(AGE_GROUPS[:-2]):  # 0-4〜80-84
                next_age = AGE_GROUPS[i + 1]
                nxt[next_age] = {
                    "male":   curr[age]["male"]   * get_rate("cohort", age, "male"),
                    "female": curr[age]["female"] * get_rate("cohort", age, "female"),
                }

            # 85+: 80-84 と 85+ の合計にレートを適用
            pool_male   = curr["80-84"]["male"]   + curr["85+"]["male"]
            pool_female = curr["80-84"]["female"] + curr["85+"]["female"]
            nxt["85+"] = {
                "male":   pool_male   * get_rate("cohort_85plus", "85+", "male"),
                "female": pool_female * get_rate("cohort_85plus", "85+", "female"),
            }

            # 0-4: CWR × 推計後の女性出産年齢層合計
            cwr = get_rate("cwr", "0-4", "both")
            women_cb_next = sum(nxt[a]["female"] for a in CHILDBEARING_AGES if a in nxt)
            total_04 = cwr * women_cb_next
            # 男女比は過去実績から（男児比率 ≒ 0.513 が日本の平均）
            sex_ratio_m = (
                curr["0-4"]["male"] /
                (curr["0-4"]["male"] + curr["0-4"]["female"])
                if (curr["0-4"]["male"] + curr["0-4"]["female"]) > 0 else 0.513
            )
            nxt["0-4"] = {
                "male":   total_04 * sex_ratio_m,
                "female": total_04 * (1 - sex_ratio_m),
            }

            # 結果を行として記録
            for age_group, vals in nxt.items():
                results.append({
                    "pref_code": pref_code,
                    "pref_name": pref_name,
                    "year": year,
                    "age_group": age_group,
                    "male": max(0, round(vals["male"])),
                    "female": max(0, round(vals["female"])),
                })

            curr = nxt  # 次期の起点に更新

        return pd.DataFrame(results)

    def _project_one_step(
        self,
        curr: dict[str, dict[str, float]],
        pref_rates: pd.DataFrame,
    ) -> dict[str, dict[str, float]]:
        """1期分（5年）の人口投影を行い、次期の人口辞書を返す。

        evaluator.py のバックテストから呼び出される共通ロジック。
        """
        def get_rate(rate_type: str, age: str, sex: str) -> float:
            r = pref_rates[
                (pref_rates["rate_type"] == rate_type)
                & (pref_rates["age_group"] == age)
                & (pref_rates["sex"] == sex)
            ]["avg_rate"]
            return float(r.iloc[0]) if not r.empty and not np.isnan(r.iloc[0]) else 1.0

        nxt: dict[str, dict[str, float]] = {}

        for i, age in enumerate(AGE_GROUPS[:-2]):
            next_age = AGE_GROUPS[i + 1]
            nxt[next_age] = {
                "male":   curr.get(age, {}).get("male", 0)   * get_rate("cohort", age, "male"),
                "female": curr.get(age, {}).get("female", 0) * get_rate("cohort", age, "female"),
            }

        pool_male   = curr.get("80-84", {}).get("male", 0)   + curr.get("85+", {}).get("male", 0)
        pool_female = curr.get("80-84", {}).get("female", 0) + curr.get("85+", {}).get("female", 0)
        nxt["85+"] = {
            "male":   pool_male   * get_rate("cohort_85plus", "85+", "male"),
            "female": pool_female * get_rate("cohort_85plus", "85+", "female"),
        }

        cwr = get_rate("cwr", "0-4", "both")
        women_cb_next = sum(nxt.get(a, {}).get("female", 0) for a in CHILDBEARING_AGES)
        total_04 = cwr * women_cb_next
        p04_m = curr.get("0-4", {}).get("male", 0)
        p04_f = curr.get("0-4", {}).get("female", 0)
        sex_ratio_m = p04_m / (p04_m + p04_f) if (p04_m + p04_f) > 0 else 0.513
        nxt["0-4"] = {
            "male":   total_04 * sex_ratio_m,
            "female": total_04 * (1 - sex_ratio_m),
        }
        return nxt
