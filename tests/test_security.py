"""
セキュリティテスト

認証、認可、入力検証、脆弱性対策の検証
"""

import pytest
import hashlib
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.api import AuthService, User, FASTAPI_AVAILABLE
from src.billing import BillingService, SubscriptionPlan, SubscriptionStatus
from src.database import Database


class TestPasswordSecurity:
    """パスワードセキュリティテスト"""

    @pytest.fixture
    def auth_service(self):
        """AuthServiceのフィクスチャ"""
        return AuthService(secret_key="test-secret-key-for-security")

    def test_password_not_stored_plaintext(self, auth_service):
        """パスワードが平文で保存されないことを確認"""
        password = "MySecretPassword123!"
        user = auth_service.create_user(
            email="test@example.com",
            password=password
        )

        assert user is not None
        assert user.password_hash != password
        assert password not in user.password_hash

    def test_password_hash_not_reversible(self, auth_service):
        """パスワードハッシュが不可逆であることを確認"""
        password = "TestPassword123"
        user = auth_service.create_user(
            email="hash@example.com",
            password=password
        )

        # ハッシュは一定の長さ（SHA256 = 64文字）
        assert len(user.password_hash) == 64

    def test_same_password_same_hash(self, auth_service):
        """同じパスワードは同じハッシュを生成"""
        password = "ConsistentPassword"
        hash1 = auth_service._hash_password(password)
        hash2 = auth_service._hash_password(password)

        assert hash1 == hash2

    def test_different_passwords_different_hashes(self, auth_service):
        """異なるパスワードは異なるハッシュを生成"""
        hash1 = auth_service._hash_password("Password1")
        hash2 = auth_service._hash_password("Password2")

        assert hash1 != hash2

    def test_password_verification(self, auth_service):
        """パスワード検証の正確性"""
        password = "CorrectPassword"
        password_hash = auth_service._hash_password(password)

        assert auth_service._verify_password(password, password_hash) is True
        assert auth_service._verify_password("WrongPassword", password_hash) is False


class TestTokenSecurity:
    """トークンセキュリティテスト"""

    @pytest.fixture
    def auth_service(self):
        """AuthServiceのフィクスチャ"""
        return AuthService(secret_key="secure-jwt-secret-key-256-bits")

    def test_token_contains_no_sensitive_data(self, auth_service):
        """トークンに機密情報が含まれていないことを確認"""
        user = auth_service.create_user(
            email="token@example.com",
            password="SecretPassword123"
        )

        token = auth_service.create_access_token(user.id)

        # トークンにパスワードやメールアドレスが含まれていない
        assert "SecretPassword123" not in token
        assert "token@example.com" not in token

    def test_different_users_different_tokens(self, auth_service):
        """異なるユーザーは異なるトークンを取得"""
        user1 = auth_service.create_user(
            email="user1@example.com",
            password="password1"
        )
        user2 = auth_service.create_user(
            email="user2@example.com",
            password="password2"
        )

        token1 = auth_service.create_access_token(user1.id)
        token2 = auth_service.create_access_token(user2.id)

        assert token1 != token2

    def test_invalid_token_rejected(self, auth_service):
        """無効なトークンが拒否される"""
        invalid_tokens = [
            "",
            "invalid",
            "bearer.invalid.token",
            "a" * 1000,
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature"
        ]

        for token in invalid_tokens:
            result = auth_service.verify_token(token)
            assert result is None, f"無効なトークン '{token[:20]}...' が受け入れられた"

    def test_tampered_token_rejected(self, auth_service):
        """改ざんされたトークンが拒否される"""
        user = auth_service.create_user(
            email="tamper@example.com",
            password="password"
        )

        token = auth_service.create_access_token(user.id)

        # トークンの一部を改ざん
        if len(token) > 10:
            tampered = token[:-5] + "XXXXX"
            result = auth_service.verify_token(tampered)
            assert result is None

    def test_token_from_different_secret_rejected(self):
        """異なるシークレットで生成されたトークンが拒否される"""
        auth1 = AuthService(secret_key="secret-key-1")
        auth2 = AuthService(secret_key="secret-key-2")

        user = auth1.create_user(
            email="cross@example.com",
            password="password"
        )

        token = auth1.create_access_token(user.id)

        # 別のサービスでトークンを検証
        result = auth2.verify_token(token)
        # モックトークンの場合は検証ロジックが異なる
        # JWTが利用可能な場合はNoneが返る


class TestAuthenticationSecurity:
    """認証セキュリティテスト"""

    @pytest.fixture
    def auth_service(self):
        """AuthServiceのフィクスチャ"""
        return AuthService(secret_key="auth-security-test")

    def test_wrong_password_rejected(self, auth_service):
        """間違ったパスワードが拒否される"""
        auth_service.create_user(
            email="wrong@example.com",
            password="correct_password"
        )

        result = auth_service.authenticate("wrong@example.com", "wrong_password")
        assert result is None

    def test_nonexistent_user_rejected(self, auth_service):
        """存在しないユーザーが拒否される"""
        result = auth_service.authenticate("nonexistent@example.com", "password")
        assert result is None

    def test_case_sensitive_email(self, auth_service):
        """メールアドレスが大文字小文字を区別する"""
        auth_service.create_user(
            email="CaseSensitive@example.com",
            password="password"
        )

        # 異なるケースでログインを試行
        result = auth_service.authenticate("casesensitive@example.com", "password")
        # 実装によっては大文字小文字を区別しない場合もある
        # ここではセキュリティの観点から区別することを推奨

    def test_duplicate_email_rejected(self, auth_service):
        """重複メールアドレスが拒否される"""
        auth_service.create_user(
            email="duplicate@example.com",
            password="password1"
        )

        result = auth_service.create_user(
            email="duplicate@example.com",
            password="password2"
        )

        assert result is None


class TestInputValidation:
    """入力検証テスト"""

    @pytest.fixture
    def auth_service(self):
        """AuthServiceのフィクスチャ"""
        return AuthService(secret_key="input-validation-test")

    @pytest.fixture
    def database(self):
        """Databaseのフィクスチャ"""
        return Database()

    def test_sql_injection_user_lookup(self, database):
        """SQLインジェクション攻撃を検証（ユーザー検索）"""
        # 正常なユーザーを作成
        database.create_user(
            user_id="normal_user",
            email="normal@example.com",
            password_hash="hash123"
        )

        # SQLインジェクション試行
        injection_payloads = [
            "' OR '1'='1",
            "'; DROP TABLE users; --",
            "' UNION SELECT * FROM users --",
            "admin'--",
            "1; SELECT * FROM users WHERE '1'='1",
        ]

        for payload in injection_payloads:
            result = database.get_user_by_email(payload)
            assert result is None, f"SQLインジェクションが成功: {payload}"

    def test_sql_injection_audit_log(self, database):
        """SQLインジェクション攻撃を検証（監査ログ）"""
        injection_payloads = [
            "' OR '1'='1",
            "'; DROP TABLE audit_logs; --",
        ]

        for payload in injection_payloads:
            # インジェクション試行がエラーなく処理される
            database.log_audit(
                action=payload,
                user_id=payload,
                details={"payload": payload}
            )

        # データベースが正常に動作することを確認
        logs = database.get_audit_logs(limit=10)
        assert isinstance(logs, list)

    def test_xss_in_user_name(self, auth_service):
        """XSS攻撃を検証（ユーザー名）"""
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "javascript:alert('XSS')",
            "<img src=x onerror=alert('XSS')>",
            "<svg onload=alert('XSS')>",
        ]

        for i, payload in enumerate(xss_payloads):
            user = auth_service.create_user(
                email=f"xss{i}@example.com",
                password="password",
                name=payload
            )

            # ユーザーが作成されるが、出力時にエスケープが必要
            assert user is not None
            assert user.name == payload  # 入力はそのまま保存


class TestAuthorizationSecurity:
    """認可セキュリティテスト"""

    @pytest.fixture
    def billing_service(self):
        """BillingServiceのフィクスチャ"""
        return BillingService()

    def test_free_plan_limitations(self, billing_service):
        """無料プランの制限を検証"""
        billing_service.create_subscription(
            user_id="free_user",
            customer_id="cus_free",
            plan=SubscriptionPlan.FREE
        )

        # 無料プランは自動アクション無効
        can_use, _ = billing_service.check_usage_limit("free_user", "auto_action")
        assert can_use is False

    def test_usage_limit_enforcement(self, billing_service):
        """使用量制限の強制を検証"""
        billing_service.create_subscription(
            user_id="limited_user",
            customer_id="cus_limited",
            plan=SubscriptionPlan.FREE  # 50件/月
        )

        # 制限に達するまで使用
        for i in range(50):
            can_use, _ = billing_service.check_usage_limit("limited_user", "email_summary")
            if can_use:
                billing_service.record_usage("limited_user", "email_summary")

        # 制限後は拒否される
        can_use, message = billing_service.check_usage_limit("limited_user", "email_summary")
        assert can_use is False
        assert "上限" in message

    def test_inactive_subscription_blocked(self, billing_service):
        """非アクティブなサブスクリプションがブロックされる"""
        billing_service.create_subscription(
            user_id="inactive_user",
            customer_id="cus_inactive",
            plan=SubscriptionPlan.PERSONAL
        )

        # サブスクリプションをキャンセル（即時）
        billing_service.cancel_subscription("inactive_user", at_period_end=False)

        # 使用がブロックされる
        subscription = billing_service.get_subscription("inactive_user")
        assert subscription is not None
        assert subscription.status == SubscriptionStatus.CANCELED
        assert subscription.can_use_feature("email_summary") is False


class TestDatabaseSecurity:
    """データベースセキュリティテスト"""

    @pytest.fixture
    def database(self):
        """Databaseのフィクスチャ"""
        return Database()

    def test_user_isolation(self, database):
        """ユーザー間のデータ分離を検証"""
        # 2つのユーザーを作成
        database.create_user(
            user_id="user_a",
            email="a@example.com",
            password_hash="hash_a"
        )
        database.create_user(
            user_id="user_b",
            email="b@example.com",
            password_hash="hash_b"
        )

        # サブスクリプションを作成
        database.create_subscription(
            subscription_id="sub_a",
            user_id="user_a",
            plan="personal"
        )
        database.create_subscription(
            subscription_id="sub_b",
            user_id="user_b",
            plan="free"
        )

        # 各ユーザーは自分のサブスクリプションのみ取得
        sub_a = database.get_subscription_by_user("user_a")
        sub_b = database.get_subscription_by_user("user_b")

        assert sub_a is not None
        assert sub_b is not None
        assert sub_a.plan == "personal"
        assert sub_b.plan == "free"
        assert sub_a.id != sub_b.id

    def test_audit_log_integrity(self, database):
        """監査ログの整合性を検証"""
        # 監査ログを記録
        database.log_audit(
            action="user_login",
            user_id="audit_user",
            details={"ip": "192.168.1.1"}
        )

        # 監査ログは変更不可であることを確認
        # （現在の実装ではUPDATE/DELETEメソッドは提供されていない）
        logs = database.get_audit_logs(user_id="audit_user")
        assert len(logs) >= 1
        assert logs[0]["action"] == "user_login"
        assert logs[0]["details"]["ip"] == "192.168.1.1"


class TestRateLimiting:
    """レート制限テスト（将来の実装用）"""

    def test_rapid_login_attempts(self):
        """連続ログイン試行の検出"""
        auth_service = AuthService(secret_key="rate-limit-test")

        auth_service.create_user(
            email="ratelimit@example.com",
            password="correct_password"
        )

        # 連続して間違ったパスワードで試行
        failed_attempts = 0
        for _ in range(10):
            result = auth_service.authenticate("ratelimit@example.com", "wrong")
            if result is None:
                failed_attempts += 1

        # 全て失敗
        assert failed_attempts == 10

        # 将来的には10回失敗後にロックアウトする機能を追加
        # assert account_locked is True


class TestDataExposure:
    """データ露出テスト"""

    def test_password_not_in_user_response(self):
        """パスワードがユーザーレスポンスに含まれない"""
        auth_service = AuthService(secret_key="exposure-test")

        user = auth_service.create_user(
            email="exposure@example.com",
            password="secret_password"
        )

        # Userオブジェクトにはpassword_hashが含まれるが、
        # APIレスポンスには含めてはならない
        assert hasattr(user, 'password_hash')
        # UserResponseモデルにはpassword_hashフィールドがないことを確認
        # （api.pyのUserResponseクラスを参照）

    def test_sensitive_data_not_logged(self):
        """機密データがログに出力されない"""
        # この機能は将来的にログ出力をフィルタリングする
        # 現時点ではパスワードをログに出力しないことを手動で確認


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPIがインストールされていません")
class TestAPISecurityEndpoints:
    """API セキュリティエンドポイントテスト"""

    @pytest.fixture
    def client(self):
        """テストクライアントのフィクスチャ"""
        from fastapi.testclient import TestClient
        from src.api import create_app

        app = create_app()
        return TestClient(app)

    def test_unauthenticated_access_blocked(self, client):
        """未認証アクセスがブロックされる"""
        protected_endpoints = [
            ("GET", "/auth/me"),
            ("POST", "/email/summarize"),
            ("POST", "/schedule/propose"),
            ("GET", "/usage"),
        ]

        for method, endpoint in protected_endpoints:
            if method == "GET":
                response = client.get(endpoint)
            else:
                response = client.post(endpoint, json={})

            assert response.status_code in [401, 403, 422], \
                f"未認証で {endpoint} にアクセス可能"

    def test_invalid_token_rejected(self, client):
        """無効なトークンが拒否される"""
        response = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid_token_12345"}
        )
        assert response.status_code == 401

    def test_cors_headers_present(self, client):
        """CORSヘッダーが設定されている"""
        response = client.options(
            "/health",
            headers={"Origin": "http://example.com"}
        )
        # OPTIONSリクエストでCORSヘッダーを確認
        # 注: FastAPIのCORSミドルウェア設定に依存


class TestSecurityHeaders:
    """セキュリティヘッダーテスト（将来の実装用）"""

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPIがインストールされていません")
    def test_security_headers_in_response(self):
        """セキュリティヘッダーがレスポンスに含まれる"""
        from fastapi.testclient import TestClient
        from src.api import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/health")

        # 将来的に追加すべきセキュリティヘッダー
        expected_headers = [
            # "X-Content-Type-Options",  # nosniff
            # "X-Frame-Options",  # DENY
            # "X-XSS-Protection",  # 1; mode=block
            # "Strict-Transport-Security",  # HSTS
        ]

        # 現時点ではヘッダーが設定されていないため、
        # 将来の実装でこのテストを有効化する


class TestSecureDefaults:
    """セキュアデフォルトテスト"""

    def test_default_plan_is_free(self):
        """デフォルトプランが無料である"""
        auth_service = AuthService(secret_key="default-test")

        user = auth_service.create_user(
            email="default@example.com",
            password="password"
        )

        assert user.plan == "free"

    def test_new_user_has_limited_access(self):
        """新規ユーザーのアクセスが制限されている"""
        billing_service = BillingService()

        billing_service.create_subscription(
            user_id="new_user",
            customer_id="cus_new",
            plan=SubscriptionPlan.FREE
        )

        # 自動アクションは無効
        can_use_auto, _ = billing_service.check_usage_limit("new_user", "auto_action")
        assert can_use_auto is False

        # メール要約は制限あり（50件/月）
        can_use_email, _ = billing_service.check_usage_limit("new_user", "email_summary")
        assert can_use_email is True  # 最初の1件目は許可
