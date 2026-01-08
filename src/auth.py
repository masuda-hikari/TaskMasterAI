"""
Auth Module - 認証管理

Google API認証の一元管理と認証状態のキャッシュ
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from enum import Enum

from .logging_config import get_logger, RequestContext
from .errors import (
    AuthError,
    ErrorCode,
    ErrorContext,
    ErrorSeverity,
)

logger = get_logger(__name__, "auth")


class AuthProvider(Enum):
    """認証プロバイダー"""
    GOOGLE = "google"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass
class AuthStatus:
    """認証状態"""
    provider: AuthProvider
    is_authenticated: bool
    user_email: Optional[str] = None
    scopes: list[str] = None
    expires_at: Optional[datetime] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.scopes is None:
            self.scopes = []


class AuthManager:
    """
    認証マネージャー

    複数のAPIプロバイダーの認証を一元管理
    """

    # Google APIスコープ
    GMAIL_SCOPES = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.compose',
    ]

    CALENDAR_SCOPES = [
        'https://www.googleapis.com/auth/calendar.readonly',
        'https://www.googleapis.com/auth/calendar.events',
    ]

    def __init__(
        self,
        credentials_dir: Optional[Path] = None
    ):
        """
        初期化

        Args:
            credentials_dir: 認証情報ディレクトリ
        """
        self.credentials_dir = credentials_dir or Path("config/credentials")
        self._google_creds = None
        self._auth_cache: dict[AuthProvider, AuthStatus] = {}

        logger.info(f"AuthManager初期化", data={"credentials_dir": str(self.credentials_dir)})

    @property
    def google_oauth_path(self) -> Path:
        """Google OAuth認証情報ファイルパス"""
        return self.credentials_dir / "google_oauth.json"

    @property
    def google_token_path(self) -> Path:
        """Googleトークンファイルパス"""
        return self.credentials_dir / "token.json"

    def check_credentials_exist(self, provider: AuthProvider) -> bool:
        """
        認証情報ファイルの存在確認

        Args:
            provider: 認証プロバイダー

        Returns:
            認証情報が存在する場合True
        """
        if provider == AuthProvider.GOOGLE:
            return self.google_oauth_path.exists()
        return False

    def get_auth_status(self, provider: AuthProvider) -> AuthStatus:
        """
        認証状態を取得

        Args:
            provider: 認証プロバイダー

        Returns:
            AuthStatus
        """
        # キャッシュから取得
        if provider in self._auth_cache:
            return self._auth_cache[provider]

        # 新規チェック
        if provider == AuthProvider.GOOGLE:
            return self._check_google_auth()

        return AuthStatus(
            provider=provider,
            is_authenticated=False,
            error_message="未対応のプロバイダー"
        )

    def _check_google_auth(self) -> AuthStatus:
        """Google認証状態をチェック"""
        if not self.google_oauth_path.exists():
            logger.warning(
                "OAuth認証情報が見つかりません",
                data={"path": str(self.google_oauth_path)}
            )
            return AuthStatus(
                provider=AuthProvider.GOOGLE,
                is_authenticated=False,
                error_message=f"OAuth認証情報が見つかりません: {self.google_oauth_path}"
            )

        if not self.google_token_path.exists():
            logger.warning("トークンファイルが見つかりません")
            return AuthStatus(
                provider=AuthProvider.GOOGLE,
                is_authenticated=False,
                error_message="トークンがありません。認証が必要です。"
            )

        try:
            # トークンの検証
            with open(self.google_token_path, 'r') as f:
                token_data = json.load(f)

            # 有効期限チェック（簡易）
            expiry = token_data.get('expiry')
            if expiry:
                expiry_dt = datetime.fromisoformat(expiry.replace('Z', '+00:00'))
                if expiry_dt < datetime.now(expiry_dt.tzinfo):
                    # 期限切れだがrefresh_tokenがあれば認証済みとみなす
                    if not token_data.get('refresh_token'):
                        logger.warning("トークン期限切れ、リフレッシュトークンなし")
                        return AuthStatus(
                            provider=AuthProvider.GOOGLE,
                            is_authenticated=False,
                            error_message="トークンが期限切れです。再認証が必要です。"
                        )

            status = AuthStatus(
                provider=AuthProvider.GOOGLE,
                is_authenticated=True,
                scopes=self.GMAIL_SCOPES + self.CALENDAR_SCOPES
            )

            self._auth_cache[AuthProvider.GOOGLE] = status
            logger.debug("Google認証状態: 有効")
            return status

        except json.JSONDecodeError as e:
            logger.error(
                "トークンファイルのJSONパースエラー",
                data={"path": str(self.google_token_path), "error": str(e)}
            )
            return AuthStatus(
                provider=AuthProvider.GOOGLE,
                is_authenticated=False,
                error_message=f"トークン検証エラー: {e}"
            )
        except Exception as e:
            logger.error(
                "トークン検証エラー",
                data={"error": str(e)}
            )
            return AuthStatus(
                provider=AuthProvider.GOOGLE,
                is_authenticated=False,
                error_message=f"トークン検証エラー: {e}"
            )

    def authenticate_google(
        self,
        scopes: Optional[list[str]] = None,
        headless: bool = False
    ) -> AuthStatus:
        """
        Google認証を実行

        Args:
            scopes: 要求するスコープ（Noneの場合はデフォルト）
            headless: ヘッドレスモード（ブラウザを開かない）

        Returns:
            AuthStatus

        Raises:
            AuthError: 認証処理で重大なエラーが発生した場合
        """
        if scopes is None:
            scopes = self.GMAIL_SCOPES + self.CALENDAR_SCOPES

        if not self.google_oauth_path.exists():
            logger.warning(
                "OAuth認証情報が見つかりません",
                data={"path": str(self.google_oauth_path)}
            )
            return AuthStatus(
                provider=AuthProvider.GOOGLE,
                is_authenticated=False,
                error_message=f"OAuth認証情報が見つかりません: {self.google_oauth_path}"
            )

        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request

            creds = None

            # 既存トークンの読み込み
            if self.google_token_path.exists():
                creds = Credentials.from_authorized_user_file(
                    str(self.google_token_path), scopes
                )

            # トークンの更新または新規取得
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    logger.info("トークンを更新中")
                    try:
                        creds.refresh(Request())
                    except Exception as refresh_err:
                        logger.warning(
                            "トークン更新失敗、再認証が必要",
                            data={"error": str(refresh_err)}
                        )
                        creds = None

                if not creds:
                    logger.info("新規認証フローを開始")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self.google_oauth_path), scopes
                    )

                    if headless:
                        # ヘッドレスモード: URLを出力
                        auth_url, _ = flow.authorization_url(prompt='consent')
                        return AuthStatus(
                            provider=AuthProvider.GOOGLE,
                            is_authenticated=False,
                            error_message=f"ブラウザで以下のURLにアクセスしてください:\n{auth_url}"
                        )
                    else:
                        creds = flow.run_local_server(port=0)

                # トークンを保存
                self.credentials_dir.mkdir(parents=True, exist_ok=True)
                with open(self.google_token_path, 'w') as token:
                    token.write(creds.to_json())

            # 認証成功
            self._google_creds = creds

            status = AuthStatus(
                provider=AuthProvider.GOOGLE,
                is_authenticated=True,
                scopes=scopes
            )

            self._auth_cache[AuthProvider.GOOGLE] = status
            logger.info("Google認証成功", data={"scopes_count": len(scopes)})
            return status

        except ImportError as e:
            error = AuthError(
                code=ErrorCode.AUTH_CREDENTIALS_MISSING,
                message="Google認証ライブラリがインストールされていません",
                details={"missing_package": str(e)},
                cause=e
            )
            error.log()
            return AuthStatus(
                provider=AuthProvider.GOOGLE,
                is_authenticated=False,
                error_message=str(e)
            )
        except Exception as e:
            logger.error(
                "Google認証エラー",
                data={"error": str(e), "error_type": type(e).__name__}
            )
            return AuthStatus(
                provider=AuthProvider.GOOGLE,
                is_authenticated=False,
                error_message=str(e)
            )

    def get_google_credentials(self):
        """
        Google認証情報を取得

        Returns:
            google.oauth2.credentials.Credentials or None
        """
        if self._google_creds:
            return self._google_creds

        # キャッシュされたトークンから復元を試みる
        if self.google_token_path.exists():
            try:
                from google.oauth2.credentials import Credentials
                scopes = self.GMAIL_SCOPES + self.CALENDAR_SCOPES
                self._google_creds = Credentials.from_authorized_user_file(
                    str(self.google_token_path), scopes
                )
                logger.debug("トークンを復元しました")
                return self._google_creds
            except Exception as e:
                logger.warning(
                    "トークン復元エラー",
                    data={"error": str(e), "path": str(self.google_token_path)}
                )

        return None

    def revoke_google_auth(self) -> bool:
        """
        Google認証を取り消し

        Returns:
            成功時True
        """
        try:
            if self.google_token_path.exists():
                self.google_token_path.unlink()
                logger.debug("トークンファイルを削除しました")

            self._google_creds = None
            if AuthProvider.GOOGLE in self._auth_cache:
                del self._auth_cache[AuthProvider.GOOGLE]

            logger.info("Google認証を取り消しました")
            return True

        except PermissionError as e:
            logger.error(
                "トークンファイルの削除権限がありません",
                data={"path": str(self.google_token_path), "error": str(e)}
            )
            return False
        except Exception as e:
            logger.error(
                "認証取り消しエラー",
                data={"error": str(e), "error_type": type(e).__name__}
            )
            return False

    def get_all_auth_status(self) -> dict[AuthProvider, AuthStatus]:
        """
        全プロバイダーの認証状態を取得

        Returns:
            プロバイダー別AuthStatus辞書
        """
        return {
            AuthProvider.GOOGLE: self.get_auth_status(AuthProvider.GOOGLE),
        }


def create_mock_auth_manager() -> AuthManager:
    """
    テスト用モックAuthManagerを作成

    Returns:
        モック設定済みのAuthManager
    """
    import tempfile

    temp_dir = Path(tempfile.mkdtemp())
    manager = AuthManager(credentials_dir=temp_dir)

    # モック認証済み状態を設定
    manager._auth_cache[AuthProvider.GOOGLE] = AuthStatus(
        provider=AuthProvider.GOOGLE,
        is_authenticated=True,
        user_email="test@example.com",
        scopes=AuthManager.GMAIL_SCOPES + AuthManager.CALENDAR_SCOPES
    )

    return manager


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=== 認証状態チェック ===")
    manager = AuthManager()

    for provider, status in manager.get_all_auth_status().items():
        print(f"\n{provider.value}:")
        print(f"  認証済み: {status.is_authenticated}")
        if status.error_message:
            print(f"  エラー: {status.error_message}")
        if status.scopes:
            print(f"  スコープ: {len(status.scopes)}件")
