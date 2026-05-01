"""e-Stat からの人口データ取得を統括するモジュール。

EstatClient を使って統計表からデータを取得し、
pandas DataFrame に整形して返す。

使い方:
    from src.api.data_fetcher import PopulationDataFetcher

    fetcher = PopulationDataFetcher()
    df = fetcher.fetch_all()
"""

import pandas as pd

from config.settings import (
    AGE_CODE_TO_LABEL,
    ESTAT_STATS_IDS,
    PREFECTURE_CODES,
    SEX_CODE_TO_LABEL,
    TIME_CODE_TO_YEAR,
)
from src.api.estat_client import EstatClient
from src.utils.logger import logger

# 取得対象の時間軸コード（1990〜2020年の国勢調査）
TARGET_TIME_CODES = ",".join(TIME_CODE_TO_YEAR.keys())

# 表章項目コード: 020=人口（割合・性比は取得しない）
TAB_CODE_POPULATION = "020"


class PopulationDataFetcher:
    """都道府県別・年齢階級別・男女別人口データの取得クラス。

    e-Stat の統計表 0003410381（1920〜2020年 時系列）から
    1990〜2020年分のデータを取得して DataFrame に整形する。

    Args:
        client: EstatClient インスタンス。省略時は自動生成。
    """

    def __init__(self, client: EstatClient | None = None) -> None:
        self.client = client or EstatClient()
        self.stats_id = ESTAT_STATS_IDS["census_age_sex_pref_timeseries"]

    def fetch_all(self) -> pd.DataFrame:
        """全47都道府県・1990〜2020年の人口データを取得して返す。

        Returns:
            列: pref_code, pref_name, year, sex, age_group, population
        """
        logger.info("全都道府県データの取得を開始します")

        # 1回のAPIコールで全都道府県・全期間を取得する
        # （キャッシュにより2回目以降は即座に返る）
        raw = self.client.get_stats_data(
            stats_data_id=self.stats_id,
            cdTab=TAB_CODE_POPULATION,
            cdTime=TARGET_TIME_CODES,
            limit=100000,
        )

        values = (
            raw.get("GET_STATS_DATA", {})
            .get("STATISTICAL_DATA", {})
            .get("DATA_INF", {})
            .get("VALUE", [])
        )
        if isinstance(values, dict):
            values = [values]

        logger.info(f"取得レコード数: {len(values)}件")

        df = self._parse_values(values)
        logger.info(
            f"DataFrame 生成完了: {len(df)}行 "
            f"({df['pref_name'].nunique()}都道府県 × "
            f"{df['year'].nunique()}年 × "
            f"{df['age_group'].nunique()}年齢区分 × "
            f"{df['sex'].nunique()}性別)"
        )
        return df

    def _parse_values(self, values: list[dict]) -> pd.DataFrame:
        """API レスポンスの VALUE リストを DataFrame に変換する。

        Args:
            values: e-Stat API の VALUE 要素のリスト。

        Returns:
            整形済みの DataFrame。
        """
        records = []
        skipped = 0

        for v in values:
            area_code = v.get("@area", "")
            time_code = v.get("@time", "")
            sex_code = v.get("@cat01", "")
            age_code = v.get("@cat02", "")
            population_str = v.get("$", "")

            # 対象外の都道府県・年・コードはスキップ
            if area_code not in PREFECTURE_CODES:
                skipped += 1
                continue
            if time_code not in TIME_CODE_TO_YEAR:
                skipped += 1
                continue
            if age_code not in AGE_CODE_TO_LABEL:
                skipped += 1
                continue

            # 人口値の変換（"-" や空文字は欠損値扱い）
            try:
                population = int(population_str.replace(",", ""))
            except (ValueError, AttributeError):
                population = None

            records.append({
                "pref_code": area_code,
                "pref_name": PREFECTURE_CODES[area_code],
                "year": TIME_CODE_TO_YEAR[time_code],
                "sex": SEX_CODE_TO_LABEL.get(sex_code, sex_code),
                "age_group": AGE_CODE_TO_LABEL[age_code],
                "population": population,
            })

        if skipped > 0:
            logger.debug(f"スキップレコード数: {skipped}件（対象外の地域・年など）")

        df = pd.DataFrame(records)
        if df.empty:
            return df

        # 型の最適化
        df["year"] = df["year"].astype("int16")
        df["population"] = pd.to_numeric(df["population"], errors="coerce")

        # ソート
        df = df.sort_values(["pref_code", "year", "sex", "age_group"]).reset_index(drop=True)
        return df
