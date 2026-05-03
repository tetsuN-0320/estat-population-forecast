"""データ変換モジュール。

population_long.parquet から分析・可視化に使いやすい形式を生成する:
- age_pyramid.parquet: 人口ピラミッド用（男性/女性を横に並べた形式）
- population_wide.parquet: 時系列予測用（都道府県 × 年の横持ち形式）
"""

import pandas as pd

from src.preprocessing.cleaner import AGE_GROUPS_INDIVIDUAL
from src.utils.logger import logger

# 年齢区分の表示順（0-4 → 85+ の昇順）
AGE_ORDER = AGE_GROUPS_INDIVIDUAL  # cleaner.py で定義済み


def build_age_pyramid(df: pd.DataFrame) -> pd.DataFrame:
    """人口ピラミッド用 DataFrame を生成する。

    Args:
        df: population_long.parquet から読み込んだ DataFrame。

    Returns:
        列: pref_code, pref_name, year, age_group, male, female
        male 列は正値、female 列も正値で格納する。
        可視化時は male を負方向に描画することでピラミッド形状になる。
    """
    # 個別年齢区分 × 男女別のみに絞る
    df_ind = df[
        df["age_group"].isin(AGE_GROUPS_INDIVIDUAL)
        & df["sex"].isin(["男", "女"])
    ].copy()

    # ピボット: sex を列方向に展開
    pyramid = df_ind.pivot_table(
        index=["pref_code", "pref_name", "year", "age_group"],
        columns="sex",
        values="population",
        aggfunc="first",
    ).reset_index()

    pyramid.columns.name = None  # ピボット後の列名クリーンアップ
    pyramid = pyramid.rename(columns={"男": "male", "女": "female"})

    # 年齢区分を昇順にソート
    pyramid["age_order"] = pyramid["age_group"].map(
        {ag: i for i, ag in enumerate(AGE_ORDER)}
    )
    pyramid = pyramid.sort_values(
        ["pref_code", "year", "age_order"]
    ).drop(columns="age_order").reset_index(drop=True)

    logger.info(f"age_pyramid 生成完了: {len(pyramid):,}行")
    return pyramid


def build_population_wide(df: pd.DataFrame) -> pd.DataFrame:
    """時系列予測用の横持ち DataFrame を生成する。

    各都道府県・年齢区分・性別について年を列にしたワイド形式。
    Prophet / ARIMA の入力として使いやすい ds/y 形式は models/ 側で変換する。

    Args:
        df: population_long.parquet から読み込んだ DataFrame。

    Returns:
        列: pref_code, pref_name, sex, age_group, 1990, 1995, ..., 2020
    """
    df_ind = df[
        df["age_group"].isin(AGE_GROUPS_INDIVIDUAL)
        & df["sex"].isin(["男", "女"])
    ].copy()

    wide = df_ind.pivot_table(
        index=["pref_code", "pref_name", "sex", "age_group"],
        columns="year",
        values="population",
        aggfunc="first",
    ).reset_index()

    wide.columns.name = None
    # 列名を文字列に統一（parquet 保存時の互換性）
    wide.columns = [
        str(c) if isinstance(c, int) else c for c in wide.columns
    ]

    logger.info(f"population_wide 生成完了: {len(wide):,}行")
    return wide
