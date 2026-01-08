"""
TaskMasterAI テスト共通設定

pytest共通フィクスチャとフック

Note: 警告フィルターはpytest.iniで設定
"""

import gc
import pytest


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
