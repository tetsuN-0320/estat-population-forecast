"""e-Stat API クライアントのユニットテスト。

実際のAPIを叩くテストには @pytest.mark.integration を付けて分離する。
通常の `pytest` では integration マークのテストは実行されない。
"""

import pytest


class TestEstatClientInit:
    """EstatClient の初期化テスト（Day 2 に実装予定）。"""

    def test_placeholder(self) -> None:
        """プレースホルダー: Day 2 に EstatClient 実装後にテストを追加する。"""
        assert True
