"""モデル評価モジュール。

バックテスト（2015・2020年の事後検証）と社人研推計との比較を行う。

## 評価の流れ
1. 1990〜2010年のデータで各モデルを学習
2. 2015年・2020年を予測
3. 実績値と比較して MAPE / RMSE を算出
4. 社人研の公式推計（全国・都道府県）と突合

## 社人研推計について
出典: 国立社会保障・人口問題研究所「日本の地域別将来推計人口（令和5年推計）」
     https://www.ipss.go.jp/pp-shicyoson/j/shicyoson23/t-page.asp
全国推計: 「日本の将来推計人口（令和5年推計）」出生中位・死亡中位
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.utils.logger import logger

# ===== 社人研推計値（全国）=====
# 出典: 日本の将来推計人口（令和5年推計）出生中位・死亡中位 総人口
IPSS_NATIONAL: dict[int, float] = {
    2025: 12_254,  # 万人
    2030: 11_913,
    2035: 11_530,
    2040: 11_092,
    2045: 10_642,
    2050: 10_469,
}

# 社人研 都道府県別 2050年推計（出生中位・死亡中位）単位: 千人
# 出典: 日本の地域別将来推計人口（令和5年推計）
IPSS_PREF_2050_THOUSAND: dict[str, float] = {
    "北海道": 3_866, "青森県": 792, "岩手県": 897, "宮城県": 1_681,
    "秋田県": 565, "山形県": 704, "福島県": 1_195, "茨城県": 1_890,
    "栃木県": 1_310, "群馬県": 1_274, "埼玉県": 5_128, "千葉県": 4_444,
    "東京都": 13_759, "神奈川県": 6_705, "新潟県": 1_448, "富山県": 707,
    "石川県": 800, "福井県": 503, "山梨県": 530, "長野県": 1_399,
    "岐阜県": 1_261, "静岡県": 2_391, "愛知県": 5_709, "三重県": 1_158,
    "滋賀県": 1_051, "京都府": 1_780, "大阪府": 6_588, "兵庫県": 3_832,
    "奈良県": 855, "和歌山県": 594, "鳥取県": 363, "島根県": 439,
    "岡山県": 1_340, "広島県": 1_904, "山口県": 870, "徳島県": 454,
    "香川県": 631, "愛媛県": 888, "高知県": 453, "福岡県": 4_047,
    "佐賀県": 570, "長崎県": 913, "熊本県": 1_230, "大分県": 790,
    "宮崎県": 775, "鹿児島県": 1_131, "沖縄県": 1_225,
}


class ModelEvaluator:
    """人口推計モデルの精度評価クラス。"""

    # ------------------------------------------------------------------
    # バックテスト
    # ------------------------------------------------------------------

    def backtest_cohort(self, df_pyramid: pd.DataFrame) -> pd.DataFrame:
        """コーホート法のバックテスト（1990〜2010年で学習 → 2015・2020年を予測）。

        Returns:
            列: pref_code, pref_name, year, actual_total, predicted_total,
                mape, rmse（都道府県 × 年の DataFrame）
        """
        from src.models.cohort_method import CohortProjector

        logger.info("コーホート法バックテスト開始（学習: 1990〜2010、検証: 2015・2020）")

        train = df_pyramid[df_pyramid["year"] <= 2010].copy()
        actual = df_pyramid[df_pyramid["year"].isin([2015, 2020])].copy()

        # 2010年までで学習し 2015・2020を予測
        projector = CohortProjector(n_recent_periods=3)
        projector.fit(train)

        # predict は fit に渡した pyramid の最終年（2010）から予測する
        # ただし predict() は df_pyramid の2020年を起点にするので、
        # 2010年を起点に予測するよう一時的に上書きして呼び出す
        results = []
        for pref_code in train["pref_code"].unique():
            pref_base = train[
                (train["pref_code"] == pref_code) & (train["year"] == 2010)
            ].copy()
            pref_name = pref_base["pref_name"].iloc[0]

            curr: dict[str, dict[str, float]] = {}
            for row in pref_base.itertuples():
                curr[row.age_group] = {
                    "male": float(row.male), "female": float(row.female)
                }

            # 2015・2020 の2期分だけ投影
            pref_rates = projector._rates[projector._rates["pref_code"] == pref_code]
            pred_years = [2015, 2020]
            for year in pred_years:
                nxt = projector._project_one_step(curr, pref_rates)
                total_pred = sum(v["male"] + v["female"] for v in nxt.values())
                # 実績値
                actual_pref = actual[
                    (actual["pref_code"] == pref_code)
                    & (actual["year"] == year)
                    & (actual["age_group"] != "総数")
                ]
                if not actual_pref.empty:
                    total_act = (actual_pref["male"] + actual_pref["female"]).sum()
                    results.append({
                        "pref_code": pref_code,
                        "pref_name": pref_name,
                        "year": year,
                        "actual": int(total_act),
                        "predicted": int(total_pred),
                    })
                curr = nxt

        df = pd.DataFrame(results)
        df["error"] = df["predicted"] - df["actual"]
        df["mape"] = abs(df["error"]) / df["actual"] * 100
        df["rmse_sq"] = df["error"] ** 2
        return df

    # ------------------------------------------------------------------
    # 精度サマリー
    # ------------------------------------------------------------------

    @staticmethod
    def summarize(df_eval: pd.DataFrame, model_name: str) -> dict[str, float]:
        """MAPE・RMSE のサマリーを計算して返す。

        Args:
            df_eval: backtest_cohort() の戻り値。
            model_name: モデル名（ログ出力用）。

        Returns:
            {"mape_mean": ..., "mape_median": ..., "rmse": ...}
        """
        mape_mean   = float(df_eval["mape"].mean())
        mape_median = float(df_eval["mape"].median())
        rmse = float(np.sqrt(df_eval["rmse_sq"].mean()))

        logger.info(
            f"{model_name} 精度: "
            f"MAPE平均={mape_mean:.2f}%, "
            f"MAPE中央値={mape_median:.2f}%, "
            f"RMSE={rmse/10000:.1f}万人"
        )
        return {"mape_mean": mape_mean, "mape_median": mape_median, "rmse": rmse}

    # ------------------------------------------------------------------
    # 社人研との比較
    # ------------------------------------------------------------------

    @staticmethod
    def compare_with_ipss(
        df_forecast: pd.DataFrame,
        model_name: str,
    ) -> pd.DataFrame:
        """社人研推計と比較した差異テーブルを返す。

        Args:
            df_forecast: cohort_2050.parquet 等の予測結果。
            model_name: モデル名。

        Returns:
            列: year, model_total_man, ipss_total_man, diff_man, diff_pct
        """
        records = []
        for year, ipss_val in IPSS_NATIONAL.items():
            year_data = df_forecast[df_forecast["year"] == year]
            if year_data.empty:
                continue
            model_total = (year_data["male"] + year_data["female"]).sum() / 10000
            diff = model_total - ipss_val
            records.append({
                "year": year,
                f"{model_name}_万人": round(model_total, 0),
                "社人研_万人": ipss_val,
                "差_万人": round(diff, 0),
                "差_%": round(diff / ipss_val * 100, 1),
            })

        df = pd.DataFrame(records)
        return df

    @staticmethod
    def compare_pref_2050(
        df_forecast: pd.DataFrame,
        model_name: str,
    ) -> pd.DataFrame:
        """2050年の都道府県別推計を社人研と比較する。

        Returns:
            列: pref_name, model_千人, ipss_千人, diff_千人, diff_%
        """
        model_2050 = (
            df_forecast[df_forecast["year"] == 2050]
            .groupby("pref_name")[["male", "female"]].sum()
            .assign(total=lambda d: d["male"] + d["female"])
            .reset_index()
        )

        records = []
        for _, row in model_2050.iterrows():
            pref = row["pref_name"]
            ipss = IPSS_PREF_2050_THOUSAND.get(pref)
            if ipss is None:
                continue
            model_val = row["total"] / 1000
            diff = model_val - ipss
            records.append({
                "pref_name": pref,
                f"{model_name}_千人": round(model_val, 0),
                "社人研_千人": ipss,
                "差_千人": round(diff, 0),
                "差_%": round(diff / ipss * 100, 1),
            })

        return pd.DataFrame(records).sort_values("差_%")
