"""
Auth モジュールのカバレッジ向上テスト

カバレッジ目標: 52% → 70%+
未カバー領域:
- 179-194: JSONパースエラー・一般例外
- 218-311: authenticate_google()
- 324-343: get_google_credentials()
- 359, 364-375: revoke_google_auth()例外
"""

import json
import pytest
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.auth import (
    AuthProvider,
    AuthStatus,
    AuthManager,
    create_mock_auth_manager
)


class TestAuthManagerJSONErrors:
    """AuthManager JSONパースエラーのテスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    def test_invalid_json_token(self, temp_dir):
        """不正なJSONトークンファイル"""
        manager = AuthManager(credentials_dir=temp_dir)

        # OAuth情報を作成
        manager.google_oauth_path.write_text('{"installed": {"client_id": "test"}}')
        # 不正なJSON
        manager.google_token_path.write_text('invalid json {{{')

        status = manager.get_auth_status(AuthProvider.GOOGLE)

        assert status.is_authenticated is False
        assert "トークン検証エラー" in status.error_message

    def test_token_general_exception(self, temp_dir):
        """トークン読み取り中の一般例外"""
        manager = AuthManager(credentials_dir=temp_dir)

        # OAuth情報を作成
        manager.google_oauth_path.write_text('{"installed": {"client_id": "test"}}')

        # トークンファイル作成（不正なJSONではなくエラーを誘発するデータ）
        manager.google_token_path.write_text('{"token": "test", "expiry": "invalid-date-format"}')

        status = manager._check_google_auth()

        # 不正な日付形式でエラーが発生する
        assert status.is_authenticated is False


class TestAuthenticateGoogle:
    """authenticate_google()メソッドのテスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    def test_no_oauth_credentials(self, temp_dir):
        """OAuth認証情報がない場合"""
        manager = AuthManager(credentials_dir=temp_dir)

        status = manager.authenticate_google()

        assert status.is_authenticated is False
        assert "OAuth認証情報が見つかりません" in status.error_message

    def test_authenticate_with_custom_scopes(self, temp_dir):
        """カスタムスコープでの認証"""
        manager = AuthManager(credentials_dir=temp_dir)

        status = manager.authenticate_google(scopes=["custom.scope"])

        assert status.is_authenticated is False  # OAuth情報がないため

    def test_authenticate_import_error(self, temp_dir):
        """Googleライブラリがない場合"""
        manager = AuthManager(credentials_dir=temp_dir)

        # OAuth情報を作成
        manager.google_oauth_path.write_text('{"installed": {"client_id": "test"}}')

        with patch.dict('sys.modules', {'google.oauth2.credentials': None}):
            with patch('builtins.__import__', side_effect=ImportError("モジュールなし")):
                status = manager.authenticate_google()

        assert status.is_authenticated is False


class TestGetGoogleCredentials:
    """get_google_credentials()メソッドのテスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    def test_get_cached_credentials(self, temp_dir):
        """キャッシュされた認証情報を返す"""
        manager = AuthManager(credentials_dir=temp_dir)

        mock_creds = Mock()
        manager._google_creds = mock_creds

        result = manager.get_google_credentials()

        assert result == mock_creds

    def test_get_credentials_no_token(self, temp_dir):
        """トークンファイルがない場合"""
        manager = AuthManager(credentials_dir=temp_dir)

        result = manager.get_google_credentials()

        assert result is None


class TestRevokeGoogleAuth:
    """revoke_google_auth()メソッドのテスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    def test_revoke_no_token(self, temp_dir):
        """トークンがない場合の取り消し"""
        manager = AuthManager(credentials_dir=temp_dir)

        result = manager.revoke_google_auth()

        assert result is True

    def test_revoke_with_cache(self, temp_dir):
        """キャッシュありの取り消し"""
        manager = AuthManager(credentials_dir=temp_dir)
        manager._google_creds = Mock()
        manager._auth_cache[AuthProvider.GOOGLE] = AuthStatus(
            provider=AuthProvider.GOOGLE,
            is_authenticated=True
        )

        # トークンファイル作成
        manager.google_token_path.write_text('{"token": "test"}')

        result = manager.revoke_google_auth()

        assert result is True
        assert manager._google_creds is None
        assert AuthProvider.GOOGLE not in manager._auth_cache

    def test_revoke_file_delete_error(self, temp_dir):
        """ファイル削除エラーのテスト（より簡単な方法）"""
        manager = AuthManager(credentials_dir=temp_dir)

        # トークンファイルを作成し、読み取り専用にする
        manager.google_token_path.write_text('{"token": "test"}')

        # 元のunlinkをモック
        original_unlink = manager.google_token_path.unlink

        def mock_unlink(*args, **kwargs):
            raise PermissionError("アクセス拒否")

        # Pathクラスをモック
        with patch.object(Path, 'unlink', mock_unlink):
            result = manager.revoke_google_auth()

        # パーミッションエラーでFalse
        assert result is False


class TestAuthStatusCaching:
    """認証状態キャッシングのテスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    def test_cache_hit(self, temp_dir):
        """キャッシュヒットのテスト"""
        manager = AuthManager(credentials_dir=temp_dir)

        # キャッシュに設定
        cached_status = AuthStatus(
            provider=AuthProvider.GOOGLE,
            is_authenticated=True,
            user_email="cached@example.com"
        )
        manager._auth_cache[AuthProvider.GOOGLE] = cached_status

        result = manager.get_auth_status(AuthProvider.GOOGLE)

        assert result.user_email == "cached@example.com"

    def test_unsupported_provider(self, temp_dir):
        """未対応プロバイダーのテスト"""
        manager = AuthManager(credentials_dir=temp_dir)

        # キャッシュにない未対応プロバイダー
        status = manager.get_auth_status(AuthProvider.OPENAI)

        assert status.is_authenticated is False
        assert "未対応" in status.error_message


class TestCheckCredentialsExist:
    """check_credentials_exist()メソッドのテスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    def test_unsupported_provider(self, temp_dir):
        """未対応プロバイダーの確認"""
        manager = AuthManager(credentials_dir=temp_dir)

        result = manager.check_credentials_exist(AuthProvider.OPENAI)

        assert result is False


class TestTokenExpiryParsing:
    """トークン有効期限パースのテスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    def test_token_without_expiry(self, temp_dir):
        """有効期限なしトークン"""
        manager = AuthManager(credentials_dir=temp_dir)

        # OAuth情報とトークンを作成
        manager.google_oauth_path.write_text('{"installed": {"client_id": "test"}}')

        # 有効期限なしトークン
        token_data = {"token": "test_token"}
        manager.google_token_path.write_text(json.dumps(token_data))

        status = manager.get_auth_status(AuthProvider.GOOGLE)

        # 有効期限がない場合は認証済みとみなす
        assert status.is_authenticated is True

    def test_token_with_z_suffix_expiry(self, temp_dir):
        """Zサフィックス付き有効期限"""
        manager = AuthManager(credentials_dir=temp_dir)

        # OAuth情報とトークンを作成
        manager.google_oauth_path.write_text('{"installed": {"client_id": "test"}}')

        # Zサフィックス付き有効期限（未来）
        future_expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        token_data = {
            "token": "test_token",
            "expiry": future_expiry
        }
        manager.google_token_path.write_text(json.dumps(token_data))

        status = manager.get_auth_status(AuthProvider.GOOGLE)

        assert status.is_authenticated is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
