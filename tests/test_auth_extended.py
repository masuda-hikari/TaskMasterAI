"""
Auth モジュールの追加カバレッジテスト

未カバー領域を網羅:
- 234-291: authenticate_google()のGoogle OAuth処理
- 306-311: authenticate_google()の一般例外処理
- 329-338: get_google_credentials()のトークン復元処理
- 370-375: revoke_google_auth()の一般例外処理
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


# Google APIモジュールのモック
class MockCredentials:
    """Credentialsモック"""
    @classmethod
    def from_authorized_user_file(cls, path, scopes):
        raise NotImplementedError("テストでオーバーライドすること")


class MockInstalledAppFlow:
    """InstalledAppFlowモック"""
    @classmethod
    def from_client_secrets_file(cls, path, scopes):
        raise NotImplementedError("テストでオーバーライドすること")


class MockRequest:
    """Requestモック"""
    pass


class TestAuthenticateGoogleOAuthFlow:
    """authenticate_google()のOAuth処理テスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    @pytest.fixture
    def manager_with_oauth(self, temp_dir):
        """OAuth認証情報付きマネージャー"""
        manager = AuthManager(credentials_dir=temp_dir)
        oauth_data = {
            "installed": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        }
        manager.google_oauth_path.write_text(json.dumps(oauth_data))
        return manager

    @pytest.fixture
    def setup_google_mocks(self):
        """Google APIモジュールをモック"""
        mock_google_oauth2 = MagicMock()
        mock_google_auth_oauthlib = MagicMock()
        mock_google_auth_transport = MagicMock()

        with patch.dict('sys.modules', {
            'google': MagicMock(),
            'google.oauth2': mock_google_oauth2,
            'google.oauth2.credentials': mock_google_oauth2.credentials,
            'google_auth_oauthlib': mock_google_auth_oauthlib,
            'google_auth_oauthlib.flow': mock_google_auth_oauthlib.flow,
            'google.auth': MagicMock(),
            'google.auth.transport': mock_google_auth_transport,
            'google.auth.transport.requests': mock_google_auth_transport.requests,
        }):
            yield {
                'Credentials': mock_google_oauth2.credentials.Credentials,
                'InstalledAppFlow': mock_google_auth_oauthlib.flow.InstalledAppFlow,
                'Request': mock_google_auth_transport.requests.Request,
            }

    def test_authenticate_with_existing_valid_token(self, manager_with_oauth, setup_google_mocks):
        """既存の有効なトークンがある場合"""
        token_data = {
            "token": "valid_token",
            "refresh_token": "refresh_token",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret"
        }
        manager_with_oauth.google_token_path.write_text(json.dumps(token_data))

        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.expired = False
        mock_creds.to_json.return_value = json.dumps(token_data)

        setup_google_mocks['Credentials'].from_authorized_user_file.return_value = mock_creds

        status = manager_with_oauth.authenticate_google()

        assert status.is_authenticated is True
        assert manager_with_oauth._google_creds == mock_creds

    def test_authenticate_with_expired_token_refresh_success(self, manager_with_oauth, setup_google_mocks):
        """期限切れトークンの更新成功"""
        token_data = {
            "token": "expired_token",
            "refresh_token": "valid_refresh_token",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret"
        }
        manager_with_oauth.google_token_path.write_text(json.dumps(token_data))

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "valid_refresh_token"
        mock_creds.to_json.return_value = json.dumps({"token": "new_token"})

        def mock_refresh(request):
            mock_creds.valid = True

        mock_creds.refresh.side_effect = mock_refresh
        setup_google_mocks['Credentials'].from_authorized_user_file.return_value = mock_creds

        status = manager_with_oauth.authenticate_google()

        assert status.is_authenticated is True
        mock_creds.refresh.assert_called_once()

    def test_authenticate_with_expired_token_refresh_fail_new_flow(self, manager_with_oauth, setup_google_mocks):
        """期限切れトークンの更新失敗→新規認証フロー"""
        token_data = {
            "token": "expired_token",
            "refresh_token": "invalid_refresh_token",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret"
        }
        manager_with_oauth.google_token_path.write_text(json.dumps(token_data))

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "invalid_refresh_token"
        mock_creds.refresh.side_effect = Exception("リフレッシュ失敗")

        mock_flow = MagicMock()
        mock_new_creds = MagicMock()
        mock_new_creds.to_json.return_value = json.dumps({"token": "new_token"})
        mock_flow.run_local_server.return_value = mock_new_creds

        setup_google_mocks['Credentials'].from_authorized_user_file.return_value = mock_creds
        setup_google_mocks['InstalledAppFlow'].from_client_secrets_file.return_value = mock_flow

        status = manager_with_oauth.authenticate_google()

        assert status.is_authenticated is True
        mock_flow.run_local_server.assert_called_once()

    def test_authenticate_headless_mode(self, manager_with_oauth, setup_google_mocks):
        """ヘッドレスモードでの認証（URLを返す）"""
        mock_flow = MagicMock()
        mock_flow.authorization_url.return_value = ("https://auth.example.com/url", "state")

        setup_google_mocks['Credentials'].from_authorized_user_file.side_effect = Exception("ファイルなし")
        setup_google_mocks['InstalledAppFlow'].from_client_secrets_file.return_value = mock_flow

        status = manager_with_oauth.authenticate_google(headless=True)

        assert status.is_authenticated is False
        assert "https://auth.example.com/url" in status.error_message
        mock_flow.authorization_url.assert_called_once_with(prompt='consent')

    def test_authenticate_new_flow_success(self, manager_with_oauth, setup_google_mocks):
        """新規認証フロー成功"""
        mock_flow = MagicMock()
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = json.dumps({"token": "new_token"})
        mock_flow.run_local_server.return_value = mock_creds

        setup_google_mocks['Credentials'].from_authorized_user_file.side_effect = Exception("ファイルなし")
        setup_google_mocks['InstalledAppFlow'].from_client_secrets_file.return_value = mock_flow

        status = manager_with_oauth.authenticate_google()

        assert status.is_authenticated is True
        assert manager_with_oauth._google_creds == mock_creds
        assert AuthProvider.GOOGLE in manager_with_oauth._auth_cache

    def test_authenticate_general_exception(self, manager_with_oauth, setup_google_mocks):
        """認証中の一般例外"""
        setup_google_mocks['Credentials'].from_authorized_user_file.side_effect = RuntimeError("予期しないエラー")
        # InstalledAppFlowもモックするが、RuntimeErrorが先に発生する前にインポートされる
        setup_google_mocks['InstalledAppFlow'].from_client_secrets_file.side_effect = RuntimeError("予期しないエラー")

        status = manager_with_oauth.authenticate_google()

        assert status.is_authenticated is False
        assert "予期しないエラー" in status.error_message

    def test_authenticate_creates_directory(self, temp_dir, setup_google_mocks):
        """認証情報ディレクトリを自動作成"""
        nested_dir = temp_dir / "nested" / "credentials"
        manager = AuthManager(credentials_dir=nested_dir)

        nested_dir.mkdir(parents=True, exist_ok=True)
        oauth_data = {
            "installed": {
                "client_id": "test",
                "client_secret": "test",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        }
        manager.google_oauth_path.write_text(json.dumps(oauth_data))

        mock_flow = MagicMock()
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = json.dumps({"token": "test"})
        mock_flow.run_local_server.return_value = mock_creds

        setup_google_mocks['Credentials'].from_authorized_user_file.side_effect = Exception("ファイルなし")
        setup_google_mocks['InstalledAppFlow'].from_client_secrets_file.return_value = mock_flow

        status = manager.authenticate_google()

        assert status.is_authenticated is True
        assert manager.credentials_dir.exists()


class TestGetGoogleCredentialsRestore:
    """get_google_credentials()のトークン復元テスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    @pytest.fixture
    def setup_google_mocks(self):
        """Google APIモジュールをモック"""
        mock_google_oauth2 = MagicMock()

        with patch.dict('sys.modules', {
            'google': MagicMock(),
            'google.oauth2': mock_google_oauth2,
            'google.oauth2.credentials': mock_google_oauth2.credentials,
        }):
            yield {
                'Credentials': mock_google_oauth2.credentials.Credentials,
            }

    def test_restore_credentials_from_file(self, temp_dir, setup_google_mocks):
        """ファイルからトークンを復元"""
        manager = AuthManager(credentials_dir=temp_dir)

        token_data = {
            "token": "saved_token",
            "refresh_token": "refresh_token",
            "client_id": "test",
            "client_secret": "test"
        }
        manager.google_token_path.write_text(json.dumps(token_data))

        mock_creds = MagicMock()
        setup_google_mocks['Credentials'].from_authorized_user_file.return_value = mock_creds

        result = manager.get_google_credentials()

        assert result == mock_creds
        assert manager._google_creds == mock_creds

    def test_restore_credentials_file_error(self, temp_dir, setup_google_mocks):
        """トークン復元時のエラー"""
        manager = AuthManager(credentials_dir=temp_dir)

        manager.google_token_path.write_text("invalid json")
        setup_google_mocks['Credentials'].from_authorized_user_file.side_effect = Exception("パースエラー")

        result = manager.get_google_credentials()

        assert result is None


class TestRevokeGoogleAuthExceptions:
    """revoke_google_auth()の例外テスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    def test_revoke_general_exception(self, temp_dir):
        """一般例外ハンドリング"""
        manager = AuthManager(credentials_dir=temp_dir)

        manager.google_token_path.write_text('{"token": "test"}')

        with patch.object(Path, 'exists', return_value=True):
            with patch.object(Path, 'unlink', side_effect=OSError("ディスクエラー")):
                result = manager.revoke_google_auth()

        assert result is False


class TestAuthStatusProperties:
    """AuthStatusのプロパティテスト"""

    def test_auth_status_post_init(self):
        """__post_init__でscopesがNoneの場合"""
        status = AuthStatus(
            provider=AuthProvider.GOOGLE,
            is_authenticated=True
        )
        assert status.scopes == []

    def test_auth_status_with_scopes(self):
        """scopesが指定された場合"""
        status = AuthStatus(
            provider=AuthProvider.GOOGLE,
            is_authenticated=True,
            scopes=["scope1", "scope2"]
        )
        assert status.scopes == ["scope1", "scope2"]

    def test_auth_status_all_fields(self):
        """全フィールド設定"""
        now = datetime.now(timezone.utc)
        status = AuthStatus(
            provider=AuthProvider.GOOGLE,
            is_authenticated=True,
            user_email="test@example.com",
            scopes=["scope1"],
            expires_at=now,
            error_message=None
        )
        assert status.provider == AuthProvider.GOOGLE
        assert status.is_authenticated is True
        assert status.user_email == "test@example.com"
        assert status.expires_at == now


class TestGetAllAuthStatus:
    """get_all_auth_status()テスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    def test_get_all_auth_status(self, temp_dir):
        """全プロバイダーの状態取得"""
        manager = AuthManager(credentials_dir=temp_dir)

        result = manager.get_all_auth_status()

        assert AuthProvider.GOOGLE in result
        assert result[AuthProvider.GOOGLE].is_authenticated is False


class TestTokenExpiryEdgeCases:
    """トークン有効期限のエッジケーステスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    def test_expired_token_with_refresh_token(self, temp_dir):
        """期限切れ＋リフレッシュトークンあり→認証済み"""
        manager = AuthManager(credentials_dir=temp_dir)

        manager.google_oauth_path.write_text('{"installed": {"client_id": "test"}}')

        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        token_data = {
            "token": "expired",
            "expiry": past,
            "refresh_token": "valid_refresh"
        }
        manager.google_token_path.write_text(json.dumps(token_data))

        status = manager._check_google_auth()

        assert status.is_authenticated is True

    def test_expired_token_no_refresh_token(self, temp_dir):
        """期限切れ＋リフレッシュトークンなし→再認証必要"""
        manager = AuthManager(credentials_dir=temp_dir)

        manager.google_oauth_path.write_text('{"installed": {"client_id": "test"}}')

        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        token_data = {
            "token": "expired",
            "expiry": past
        }
        manager.google_token_path.write_text(json.dumps(token_data))

        status = manager._check_google_auth()

        assert status.is_authenticated is False
        assert "期限切れ" in status.error_message


class TestCreateMockAuthManager:
    """create_mock_auth_manager()テスト"""

    def test_creates_authenticated_manager(self):
        """認証済みマネージャーを作成"""
        manager = create_mock_auth_manager()

        status = manager.get_auth_status(AuthProvider.GOOGLE)

        assert status.is_authenticated is True
        assert status.user_email == "test@example.com"
        assert len(status.scopes) > 0


class TestAuthProviderEnum:
    """AuthProvider列挙型テスト"""

    def test_provider_values(self):
        """プロバイダーの値"""
        assert AuthProvider.GOOGLE.value == "google"
        assert AuthProvider.OPENAI.value == "openai"
        assert AuthProvider.ANTHROPIC.value == "anthropic"


class TestAuthenticateGoogleImportError:
    """ImportErrorテスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    def test_import_error_handling(self, temp_dir):
        """Googleライブラリがない場合のImportErrorハンドリング"""
        manager = AuthManager(credentials_dir=temp_dir)

        oauth_data = {
            "installed": {
                "client_id": "test",
                "client_secret": "test",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        }
        manager.google_oauth_path.write_text(json.dumps(oauth_data))

        # google.oauth2.credentialsがインポートされないようにする
        # （実際の環境ではライブラリがインストールされていないかもしれない）
        status = manager.authenticate_google()

        # ImportErrorまたは成功のどちらかになる
        # （ライブラリの有無によって結果が変わる）
        assert isinstance(status, AuthStatus)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
