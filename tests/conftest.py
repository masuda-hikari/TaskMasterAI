"""
TaskMasterAI テスト共通設定

pytest共通フィクスチャとフック

Note: 警告フィルターはpytest.iniで設定
"""

import gc
import os
import pytest


def pytest_configure(config):
    """
    pytest設定時に実行される

    テスト環境用の環境変数を設定
    """
    # テスト実行時はレート制限を無効化
    os.environ["DISABLE_RATE_LIMIT"] = "true"
    # テスト用DBをインメモリに設定
    os.environ.setdefault("DATABASE_PATH", ":memory:")


@pytest.fixture(autouse=True)
def cleanup_db_connections():
    """
    各テスト後にDBコネクションをクリーンアップ

    sqlite3の未クローズ接続警告を防止する。
    ガベージコレクションを強制実行し、
    未解放のDatabase/Connectionオブジェクトを回収。
    """
    yield
    # テスト後にガベージコレクションを実行
    gc.collect()
