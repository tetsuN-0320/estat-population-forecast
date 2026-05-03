"""データクレンジングモジュール。

population_long.parquet に対して以下を行う:
- データ型の最適化
- 値の妥当性チェック（負値・異常値の検出）
- 「総数」行と個別年齢行の分離
"""

import pandas as pd

from src.utils.logger import logger

# 分析に使う個別年齢区分（「総数」と「再掲」を除いたもの）
AGE_GROUPS_INDIVIDUAL = [
    "0-4", "5-9", "10-14", "15-19", "20-24",
    "25-29", "30-34", "35-39", "40-44", "45-49",
    "50-54", "55-59", "60-64", "65-69", "70-74",
    "75-79", "80-84", "85+",
]


def validate(df: pd.DataFrame) -> dict[str, int]:
    """データ品質をチェックし、問題件数を返す。

    Args:
        df: population_long.parquet から読み込んだ DataFrame。

    Returns:
        チェック項目と問題件数の辞書。
    """
    issues: dict[str, int] = {
        "欠損値": int(df["population"].isna().sum()),
        "負値": int((df["population"] < 0).sum()),
        "ゼロ値": int((df["population"] == 0).sum()),
    }

    # 都道府県 × 年 × 性別「総数」の件数チェック（47 × 7 × 1 = 329件が期待値）
    totals = df.query("age_group == '総数' and sex == '総数'")
    expected_total_rows = 47 * 7
    issues["総数行の過不足"] = abs(len(totals) - expected_total_rows)

    for key, count in issues.items():
        if count > 0:
            logger.warning(f"品質問題: {key} = {count}件")
        else:
            logger.debug(f"品質OK: {key} = {count}件")

    return issues


def split_totals(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """「総数」行と個別年齢区分行に分割する。

    「総数」行は整合性チェックに使い、モデリングでは個別年齢行を使う。

    Returns:
        (個別年齢行の DataFrame, 総数行の DataFrame)
    """
    mask_individual = (
        df["age_group"].isin(AGE_GROUPS_INDIVIDUAL)
        & (df["sex"] != "総数")  # 男女別のみ（総数は合計チェック用）
    )
    df_individual = df[mask_individual].copy()
    df_totals = df[~mask_individual].copy()

    logger.info(
        f"分割完了: 個別年齢行={len(df_individual):,}件, "
        f"総数・再掲行={len(df_totals):,}件"
    )
    return df_individual, df_totals


def check_sex_sum(df: pd.DataFrame, tolerance: float = 0.01) -> pd.DataFrame:
    """男女の合計が「総数」と一致するか検証する。

    Args:
        df: population_long.parquet 全体の DataFrame。
        tolerance: 許容誤差（デフォルト 1%）。

    Returns:
        不整合があった行の DataFrame（空なら問題なし）。
    """
    # 男女合計を計算
    sex_sum = (
        df[df["sex"].isin(["男", "女"])]
        .groupby(["pref_code", "year", "age_group"])["population"]
        .sum()
        .reset_index()
        .rename(columns={"population": "sum_male_female"})
    )

    # 総数と突合
    totals = (
        df[df["sex"] == "総数"][["pref_code", "year", "age_group", "population"]]
        .rename(columns={"population": "total"})
    )

    merged = sex_sum.merge(totals, on=["pref_code", "year", "age_group"])
    merged["diff_ratio"] = abs(merged["sum_male_female"] - merged["total"]) / merged["total"]
    problems = merged[merged["diff_ratio"] > tolerance]

    if problems.empty:
        logger.info("男女合計の整合性チェック: 問題なし")
    else:
        logger.warning(f"男女合計の不整合: {len(problems)}件（許容誤差 {tolerance*100:.0f}%超）")

    return problems
