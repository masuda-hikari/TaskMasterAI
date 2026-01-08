"""
Auth モジュールのテスト
"""

import json
import pytest
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.auth import (
    AuthProvider,
    AuthStatus,
    AuthManager,
    create_mock_auth_manager
)


class TestAuthStatus:
    """AuthStatusデータクラスのテスト"""

    def test_status_creation(self):
        """AuthStatusオブジェクトの作成テスト"""
        status = AuthStatus(
            provider=AuthProvider.GOOGLE,
            is_authenticated=True,
            user_email="test@example.com",
            scopes=["scope1", "scope2"]
        )

        assert status.provider == AuthProvider.GOOGLE
        assert status.is_authenticated is True
        assert status.user_email == "test@example.com"
        assert len(status.scopes) == 2

    def test_status_default_values(self):
        """デフォルト値のテスト"""
        status = AuthStatus(
            provider=AuthProvider.GOOGLE,
            is_authenticated=False
        )

        assert status.scopes == []
        assert status.user_email is None
        assert status.error_message is None

    def test_status_with_error(self):
        """エラーメッセージ付きステータス"""
        status = AuthStatus(
            provider=AuthProvider.GOOGLE,
            is_authenticated=False,
            error_message="認証情報が見つかりません"
        )

        assert status.is_authenticated is False
        assert "認証情報" in status.error_message


class TestAuthManager:
    """AuthManagerのテスト"""

    @pytest.fixture
    def temp_credentials_dir(self):
        """一時認証情報ディレクトリ"""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    def test_initialization(self, temp_credentials_dir):
        """初期化テスト"""
        manager = AuthManager(credentials_dir=temp_credentials_dir)

        assert manager.credentials_dir == temp_credentials_dir
        assert manager._google_creds is None

    def test_credential_paths(self, temp_credentials_dir):
        """認証情報パスのテスト"""
        manager = AuthManager(credentials_dir=temp_credentials_dir)

        assert manager.google_oauth_path == temp_credentials_dir / "google_oauth.json"
        assert manager.google_token_path == temp_credentials_dir / "token.json"

    def test_check_credentials_not_exist(self, temp_credentials_dir):
        """認証情報が存在しない場合"""
        manager = AuthManager(credentials_dir=temp_credentials_dir)

        assert manager.check_credentials_exist(AuthProvider.GOOGLE) is False

    def test_check_credentials_exist(self, temp_credentials_dir):
        """認証情報が存在する場合"""
        manager = AuthManager(credentials_dir=temp_credentials_dir)

        # 認証情報ファイルを作成
        manager.google_oauth_path.write_text('{"test": true}')

        assert manager.check_credentials_exist(AuthProvider.GOOGLE) is True

    def test_get_auth_status_no_credentials(self, temp_credentials_dir):
        """認証情報なしの認証状態"""
        manager = AuthManager(credentials_dir=temp_credentials_dir)

        status = manager.get_auth_status(AuthProvider.GOOGLE)

        assert status.is_authenticated is False
        assert "見つかりません" in status.error_message

    def test_get_auth_status_with_oauth_no_token(self, temp_credentials_dir):
        """OAuth情報あり、トークンなしの状態"""
        manager = AuthManager(credentials_dir=temp_credentials_dir)

        # OAuth情報を作成
        manager.google_oauth_path.write_text('{"installed": {"client_id": "test"}}')

        status = manager.get_auth_status(AuthProvider.GOOGLE)

        assert status.is_authenticated is False
        assert "トークンがありません" in status.error_message

    def test_get_auth_status_with_valid_token(self, temp_credentials_dir):
        """有効なトークンがある場合"""
        manager = AuthManager(credentials_dir=temp_credentials_dir)

        # OAuth情報とトークンを作成
        manager.google_oauth_path.write_text('{"installed": {"client_id": "test"}}')

        # 有効期限が未来のトークン
        future_expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        token_data = {
            "token": "test_token",
            "refresh_token": "test_refresh",
            "expiry": future_expiry
        }
        manager.google_token_path.write_text(json.dumps(token_data))

        status = manager.get_auth_status(AuthProvider.GOOGLE)

        assert status.is_authenticated is True
        assert status.error_message is None

    def test_get_auth_status_with_expired_token_no_refresh(self, temp_credentials_dir):
        """期限切れトークン（リフレッシュトークンなし）"""
        manager = AuthManager(credentials_dir=temp_credentials_dir)

        # OAuth情報とトークンを作成
        manager.google_oauth_path.write_text('{"installed": {"client_id": "test"}}')

        # 有効期限が過去のトークン（リフレッシュトークンなし）
        past_expiry = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        token_data = {
            "token": "test_token",
            "expiry": past_expiry
        }
        manager.google_token_path.write_text(json.dumps(token_data))

        status = manager.get_auth_status(AuthProvider.GOOGLE)

        assert status.is_authenticated is False
        assert "期限切れ" in status.error_message

    def test_get_auth_status_with_expired_token_with_refresh(self, temp_credentials_dir):
        """期限切れトークン（リフレッシュトークンあり）"""
        manager = AuthManager(credentials_dir=temp_credentials_dir)

        # OAuth情報とトークンを作成
        manager.google_oauth_path.write_text('{"installed": {"client_id": "test"}}')

        # 有効期限が過去だがリフレッシュトークンあり
        past_expiry = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        token_data = {
            "token": "test_token",
            "refresh_token": "test_refresh",
            "expiry": past_expiry
        }
        manager.google_token_path.write_text(json.dumps(token_data))

        status = manager.get_auth_status(AuthProvider.GOOGLE)

        # リフレッシュトークンがあれば認証済みとみなす
        assert status.is_authenticated is True

    def test_revoke_google_auth(self, temp_credentials_dir):
        """Google認証の取り消し"""
        manager = AuthManager(credentials_dir=temp_credentials_dir)

        # トークンファイルを作成
        manager.google_token_path.write_text('{"token": "test"}')

        assert manager.google_token_path.exists()

        result = manager.revoke_google_auth()

        assert result is True
        assert not manager.google_token_path.exists()

    def test_get_all_auth_status(self, temp_credentials_dir):
        """全プロバイダーの認証状態取得"""
        manager = AuthManager(credentials_dir=temp_credentials_dir)

        all_status = manager.get_all_auth_status()

        assert AuthProvider.GOOGLE in all_status
        assert isinstance(all_status[AuthProvider.GOOGLE], AuthStatus)


class TestMockAuthManager:
    """モックAuthManagerのテスト"""

    def test_create_mock_auth_manager(self):
        """モックAuthManagerの作成"""
        manager = create_mock_auth_manager()

        status = manager.get_auth_status(AuthProvider.GOOGLE)

        assert status.is_authenticated is True
        assert status.user_email == "test@example.com"

    def test_mock_has_scopes(self):
        """モックが正しいスコープを持っている"""
        manager = create_mock_auth_manager()

        status = manager.get_auth_status(AuthProvider.GOOGLE)

        assert len(status.scopes) > 0
        assert any("gmail" in scope for scope in status.scopes)
        assert any("calendar" in scope for scope in status.scopes)


class TestAuthProvider:
    """AuthProviderのテスト"""

    def test_provider_values(self):
        """プロバイダー値のテスト"""
        assert AuthProvider.GOOGLE.value == "google"
        assert AuthProvider.OPENAI.value == "openai"
        assert AuthProvider.ANTHROPIC.value == "anthropic"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
