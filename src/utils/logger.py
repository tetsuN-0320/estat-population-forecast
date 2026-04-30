"""loguru ベースのロガー設定。

全モジュールから `from src.utils.logger import logger` でインポートして使う。
ログレベルは環境変数 LOG_LEVEL で切り替え可能（デフォルト: INFO）。
"""

import os
import sys

from loguru import logger

# デフォルト設定を削除してカスタム設定を追加
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=os.getenv("LOG_LEVEL", "INFO"),
    colorize=True,
)

__all__ = ["logger"]
