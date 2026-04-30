"""e-Stat API ラッパークライアント。

e-Stat REST API v3.0 へのリクエストを担当するクラス。
SQLite キャッシュにより同一リクエストの再送信を防ぐ。
レート制限対策として、リクエスト間に待機時間を設ける。

使い方:
    from src.api.estat_client import EstatClient

    client = EstatClient()
    data = client.get_stats_data(stats_data_id="0003007907", cd_area="11000")
"""

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_fixed

from src.utils.logger import logger

# .env からAPIキーを読み込む
load_dotenv()

import os

ESTAT_API_BASE = "https://api.e-stat.go.jp/rest/3.0/app/json"


class EstatApiError(Exception):
    """e-Stat API がエラーレスポンスを返した場合の例外。"""
    pass


class EstatClient:
    """e-Stat REST API v3.0 クライアント。

    Args:
        app_id: e-Stat アプリケーションID。省略時は環境変数 ESTAT_APP_ID を使用。
        cache_db_path: SQLite キャッシュファイルのパス。
        rate_limit_wait: リクエスト間の待機秒数（サーバー負荷配慮）。
    """

    def __init__(
        self,
        app_id: str | None = None,
        cache_db_path: Path | None = None,
        rate_limit_wait: float = 0.5,
    ) -> None:
        self.app_id = app_id or os.environ.get("ESTAT_APP_ID", "")
        if not self.app_id:
            raise ValueError(
                "e-Stat アプリケーションIDが設定されていません。"
                " .env に ESTAT_APP_ID を記入してください。"
            )

        if cache_db_path is None:
            # デフォルトは data/raw/estat_cache.sqlite
            root = Path(__file__).parent.parent.parent
            cache_db_path = root / "data" / "raw" / "estat_cache.sqlite"

        self.cache_db_path = cache_db_path
        self.rate_limit_wait = rate_limit_wait
        self._init_cache()
        logger.info(f"EstatClient 初期化完了（キャッシュ: {self.cache_db_path}）")

    # ------------------------------------------------------------------
    # キャッシュ管理
    # ------------------------------------------------------------------

    def _init_cache(self) -> None:
        """SQLite キャッシュテーブルを初期化する。"""
        self.cache_db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.cache_db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key      TEXT PRIMARY KEY,
                    response TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)

    def _cache_key(self, params: dict[str, Any]) -> str:
        """パラメータ辞書からキャッシュキー（SHA256）を生成する。"""
        # app_id はキャッシュキーに含めない（秘匿情報のため）
        params_copy = {k: v for k, v in sorted(params.items()) if k != "appId"}
        serialized = json.dumps(params_copy, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def _get_cache(self, key: str) -> dict[str, Any] | None:
        """キャッシュからレスポンスを取得する。なければ None を返す。"""
        with sqlite3.connect(self.cache_db_path) as conn:
            row = conn.execute(
                "SELECT response FROM cache WHERE key = ?", (key,)
            ).fetchone()
        if row:
            logger.debug(f"キャッシュヒット: {key[:8]}...")
            return json.loads(row[0])
        return None

    def _set_cache(self, key: str, response: dict[str, Any]) -> None:
        """レスポンスをキャッシュに保存する。"""
        with sqlite3.connect(self.cache_db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, response) VALUES (?, ?)",
                (key, json.dumps(response, ensure_ascii=False)),
            )
        logger.debug(f"キャッシュ保存: {key[:8]}...")

    # ------------------------------------------------------------------
    # HTTP リクエスト
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(5),
        retry=retry_if_not_exception_type(EstatApiError),  # APIロジックエラーはリトライしない
    )
    def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        """e-Stat API へ GET リクエストを送信する。

        キャッシュがあればAPIを叩かずに返す。
        失敗時は最大3回、5秒間隔でリトライする（tenacity）。
        """
        params["appId"] = self.app_id
        cache_key = self._cache_key(params)

        # キャッシュ確認
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        # API リクエスト
        url = f"{ESTAT_API_BASE}/{endpoint}"
        logger.info(f"API リクエスト: {endpoint} params={_safe_params(params)}")
        time.sleep(self.rate_limit_wait)  # レート制限対策

        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        # e-Stat 独自のエラーレスポンスを確認
        _check_estat_error(data)

        self._set_cache(cache_key, data)
        return data

    # ------------------------------------------------------------------
    # 公開API
    # ------------------------------------------------------------------

    def get_stats_list(self, search_word: str = "", **kwargs: Any) -> dict[str, Any]:
        """統計表の一覧を取得する（getStatsList）。

        Args:
            search_word: 検索キーワード（例: "国勢調査 人口"）。
            **kwargs: その他の API パラメータ。

        Returns:
            API レスポンス（辞書形式）。
        """
        params: dict[str, Any] = {"searchWord": search_word, "lang": "J"}
        params.update(kwargs)
        return self._request("getStatsList", params)

    def get_meta_info(self, stats_data_id: str) -> dict[str, Any]:
        """統計表のメタ情報（コード定義など）を取得する（getMetaInfo）。

        Args:
            stats_data_id: 統計表ID。

        Returns:
            API レスポンス（辞書形式）。
        """
        params: dict[str, Any] = {"statsDataId": stats_data_id, "lang": "J"}
        return self._request("getMetaInfo", params)

    def get_stats_data(
        self,
        stats_data_id: str,
        cd_area: str | None = None,
        start_position: int = 1,
        limit: int = 100000,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """統計データを取得する（getStatsData）。

        Args:
            stats_data_id: 統計表ID。
            cd_area: 都道府県コード（例: "01000" = 北海道）。
            start_position: 取得開始位置（ページング用）。
            limit: 最大取得件数（上限 100000）。
            **kwargs: その他の API パラメータ（cdCat01 等）。

        Returns:
            API レスポンス（辞書形式）。
        """
        params: dict[str, Any] = {
            "statsDataId": stats_data_id,
            "startPosition": start_position,
            "limit": limit,
            "lang": "J",
        }
        if cd_area:
            params["cdArea"] = cd_area
        params.update(kwargs)
        return self._request("getStatsData", params)


# ------------------------------------------------------------------
# ユーティリティ関数（モジュール内部用）
# ------------------------------------------------------------------

def _safe_params(params: dict[str, Any]) -> dict[str, Any]:
    """ログ出力用にappIdをマスクしたパラメータ辞書を返す。"""
    return {k: ("***" if k == "appId" else v) for k, v in params.items()}


def _check_estat_error(data: dict[str, Any]) -> None:
    """e-Stat APIのエラーレスポンスを確認し、エラー時は例外を送出する。"""
    # レスポンスの構造: {"GET_STATS_LIST": {"RESULT": {"STATUS": 0, ...}}}
    for key in data:
        result = data[key].get("RESULT", {})
        status = result.get("STATUS", 0)
        if status != 0:
            error_msg = result.get("ERROR_MSG", "不明なエラー")
            raise EstatApiError(f"e-Stat API エラー (STATUS={status}): {error_msg}")
