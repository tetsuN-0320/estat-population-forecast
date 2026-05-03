"""前処理パイプライン実行スクリプト。

population_long.parquet を読み込み、検証・変換を行って以下を出力する:
  - data/processed/age_pyramid.parquet
  - data/processed/population_wide.parquet

実行方法:
    python scripts/preprocess.py
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import pandas as pd

from config.settings import PROCESSED_DIR
from src.preprocessing.cleaner import check_sex_sum, split_totals, validate
from src.preprocessing.transformer import build_age_pyramid, build_population_wide
from src.utils.logger import logger

INPUT_PATH = PROCESSED_DIR / "population_long.parquet"


def main() -> None:
    if not INPUT_PATH.exists():
        logger.error(f"入力ファイルが見つかりません: {INPUT_PATH}")
        logger.info("先に scripts/fetch_data.py を実行してください")
        sys.exit(1)

    logger.info("=== 前処理パイプライン開始 ===")
    df = pd.read_parquet(INPUT_PATH)
    logger.info(f"読み込み完了: {len(df):,}行")

    # 1. データ品質チェック
    logger.info("--- データ品質チェック ---")
    issues = validate(df)
    if any(v > 0 for v in issues.values()):
        logger.warning(f"品質問題あり: {issues}")
    else:
        logger.info("品質チェック: 全項目 OK")

    # 2. 男女合計の整合性チェック
    problems = check_sex_sum(df)
    if not problems.empty:
        logger.warning(f"男女合計の不整合サンプル:\n{problems.head()}")

    # 3. age_pyramid.parquet の生成
    logger.info("--- age_pyramid 生成 ---")
    df_pyramid = build_age_pyramid(df)
    out_pyramid = PROCESSED_DIR / "age_pyramid.parquet"
    df_pyramid.to_parquet(out_pyramid, index=False)
    logger.info(f"保存: {out_pyramid} ({out_pyramid.stat().st_size / 1024:.1f} KB)")

    # 4. population_wide.parquet の生成
    logger.info("--- population_wide 生成 ---")
    df_wide = build_population_wide(df)
    out_wide = PROCESSED_DIR / "population_wide.parquet"
    df_wide.to_parquet(out_wide, index=False)
    logger.info(f"保存: {out_wide} ({out_wide.stat().st_size / 1024:.1f} KB)")

    # 5. サマリー表示
    print("\n" + "=" * 50)
    print("【前処理完了サマリー】")
    print("=" * 50)
    print(f"  age_pyramid    : {len(df_pyramid):,}行  →  {out_pyramid.name}")
    print(f"  population_wide: {len(df_wide):,}行  →  {out_wide.name}")
    print()
    print("【age_pyramid サンプル（東京都 2020年）】")
    sample = df_pyramid.query("pref_name == '東京都' and year == 2020").head(5)
    print(sample[["age_group", "male", "female"]].to_string(index=False))
    print("=" * 50)


if __name__ == "__main__":
    main()
