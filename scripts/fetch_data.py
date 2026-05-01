"""e-Stat からの人口データ一括取得スクリプト。

実行方法:
    python scripts/fetch_data.py

オプション:
    --force   既存のキャッシュを無視して再取得する（未実装）
    --check   取得済みデータのサマリーを表示する

出力:
    data/processed/population_long.parquet
"""

import argparse
import sys
from pathlib import Path

# プロジェクトルートを sys.path に追加（src/ を import できるように）
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import pandas as pd

from config.settings import PROCESSED_DIR
from src.api.data_fetcher import PopulationDataFetcher
from src.utils.logger import logger

OUTPUT_PATH = PROCESSED_DIR / "population_long.parquet"


def fetch(force: bool = False) -> None:
    """データを取得して parquet に保存する。

    Args:
        force: True の場合、既存ファイルがあっても再取得する。
    """
    if OUTPUT_PATH.exists() and not force:
        logger.info(f"既存ファイルが見つかりました: {OUTPUT_PATH}")
        logger.info("再取得する場合は --force オプションを付けてください")
        _print_summary(pd.read_parquet(OUTPUT_PATH))
        return

    logger.info("=== データ取得開始 ===")
    fetcher = PopulationDataFetcher()
    df = fetcher.fetch_all()

    if df.empty:
        logger.error("データが取得できませんでした")
        sys.exit(1)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_PATH, index=False)
    logger.info(f"保存完了: {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size / 1024:.1f} KB)")

    _print_summary(df)


def check() -> None:
    """保存済みデータのサマリーを表示する。"""
    if not OUTPUT_PATH.exists():
        logger.warning(f"データファイルが見つかりません: {OUTPUT_PATH}")
        logger.info("まず fetch_data.py を実行してください")
        sys.exit(1)

    df = pd.read_parquet(OUTPUT_PATH)
    _print_summary(df)


def _print_summary(df: pd.DataFrame) -> None:
    """DataFrame のサマリーを見やすく出力する。"""
    print("\n" + "=" * 50)
    print("【データサマリー】")
    print("=" * 50)
    print(f"  総レコード数  : {len(df):,}件")
    print(f"  都道府県数    : {df['pref_name'].nunique()}都道府県")
    print(f"  対象年        : {sorted(df['year'].unique())}")
    print(f"  性別区分      : {sorted(df['sex'].unique())}")
    print(f"  年齢区分数    : {df['age_group'].nunique()}区分")
    print(f"  欠損値数      : {df['population'].isna().sum()}件")
    print()
    print("【先頭5行】")
    print(df.head().to_string(index=False))
    print()
    print("【都道府県別 2020年 総数 (総数) 上位5件】")
    top5 = (
        df.query("year == 2020 and sex == '総数' and age_group == '総数'")
        .nlargest(5, "population")[["pref_name", "population"]]
    )
    print(top5.to_string(index=False))
    print("=" * 50 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="e-Stat 人口データ取得スクリプト")
    parser.add_argument("--force", action="store_true", help="キャッシュを無視して再取得")
    parser.add_argument("--check", action="store_true", help="保存済みデータのサマリーを表示")
    args = parser.parse_args()

    if args.check:
        check()
    else:
        fetch(force=args.force)


if __name__ == "__main__":
    main()
