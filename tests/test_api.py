"""e-Stat API クライアントのユニットテスト。

実際のAPIを叩くテストには @pytest.mark.integration を付けて分離する。
通常の `pytest` では integration マークのテストは実行されない。
"""

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.api.estat_client import EstatApiError, EstatClient


@pytest.fixture
def tmp_cache(tmp_path: Path) -> Path:
    """テスト用の一時SQLiteキャッシュパスを返す。"""
    return tmp_path / "test_cache.sqlite"


@pytest.fixture
def client(tmp_cache: Path) -> EstatClient:
    """テスト用EstatClientインスタンス（ダミーAPIキー）。"""
    return EstatClient(app_id="dummy_app_id", cache_db_path=tmp_cache)


class TestEstatClientInit:
    """EstatClient の初期化テスト。"""

    def test_init_with_explicit_app_id(self, tmp_cache: Path) -> None:
        """明示的にapp_idを渡した場合に正常に初期化できる。"""
        c = EstatClient(app_id="test_id", cache_db_path=tmp_cache)
        assert c.app_id == "test_id"

    def test_init_without_app_id_raises(self, tmp_cache: Path) -> None:
        """app_idが未設定の場合にValueErrorが発生する。"""
        with patch.dict("os.environ", {}, clear=True):
            # ESTAT_APP_ID 環境変数も消した状態でテスト
            import os
            env_backup = os.environ.pop("ESTAT_APP_ID", None)
            try:
                with pytest.raises(ValueError, match="ESTAT_APP_ID"):
                    EstatClient(app_id="", cache_db_path=tmp_cache)
            finally:
                if env_backup:
                    os.environ["ESTAT_APP_ID"] = env_backup

    def test_cache_db_created(self, tmp_cache: Path) -> None:
        """初期化時にSQLiteファイルとテーブルが作成される。"""
        EstatClient(app_id="test_id", cache_db_path=tmp_cache)
        assert tmp_cache.exists()
        with sqlite3.connect(tmp_cache) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        assert ("cache",) in tables


class TestCacheLogic:
    """キャッシュの読み書きテスト。"""

    def test_cache_hit_avoids_api_call(self, client: EstatClient) -> None:
        """キャッシュがある場合はAPIを叩かない。"""
        fake_response = {"GET_STATS_LIST": {"RESULT": {"STATUS": 0}}}
        # 事前にキャッシュに書き込む
        params = {"statsDataId": "0003007907", "lang": "J", "appId": "dummy_app_id"}
        key = client._cache_key(params)
        client._set_cache(key, fake_response)

        with patch("requests.get") as mock_get:
            result = client.get_meta_info("0003007907")
            mock_get.assert_not_called()  # APIは呼ばれていない

        assert result == fake_response

    def test_cache_miss_calls_api(self, client: EstatClient) -> None:
        """キャッシュがない場合はAPIを呼び出す。"""
        fake_response = {"GET_STATS_DATA": {"RESULT": {"STATUS": 0}}}
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_response
        mock_resp.raise_for_status.return_value = None

        with patch("requests.get", return_value=mock_resp) as mock_get:
            result = client.get_stats_data("0003007907")
            mock_get.assert_called_once()

        assert result == fake_response


class TestEstatApiError:
    """APIエラーレスポンスの処理テスト。"""

    def test_error_status_raises_exception(self, client: EstatClient) -> None:
        """e-StatがSTATUS!=0を返した場合にEstatApiErrorが発生する。"""
        error_response = {
            "GET_STATS_DATA": {
                "RESULT": {"STATUS": 1, "ERROR_MSG": "統計表IDが不正です"}
            }
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = error_response
        mock_resp.raise_for_status.return_value = None

        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(EstatApiError, match="統計表IDが不正です"):
                client.get_stats_data("invalid_id")


# ----------------------------------------------------------------
# 結合テスト（実際のAPIを叩く。通常のCIでは除外）
# ----------------------------------------------------------------

@pytest.mark.integration
def test_real_api_get_stats_list() -> None:
    """実際のAPIでgetStatsListが動くことを確認する。"""
    client = EstatClient()  # .env から app_id を読む
    result = client.get_stats_list(search_word="国勢調査 人口 都道府県")
    assert "GET_STATS_LIST" in result
    assert result["GET_STATS_LIST"]["RESULT"]["STATUS"] == 0
