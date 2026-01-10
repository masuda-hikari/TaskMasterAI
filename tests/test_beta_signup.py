"""
ベータ登録エンドポイントのテスト
"""

import pytest
import uuid

# FastAPI利用可能性チェック
try:
    from fastapi.testclient import TestClient
    from src.api import create_app, FASTAPI_AVAILABLE
    FASTAPI_INSTALLED = FASTAPI_AVAILABLE
except ImportError:
    FASTAPI_INSTALLED = False


def unique_email(prefix: str = "test") -> str:
    """テスト用ユニークメールアドレス生成"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


@pytest.mark.skipif(not FASTAPI_INSTALLED, reason="FastAPIが利用不可")
class TestBetaSignup:
    """ベータ登録エンドポイントのテスト"""

    @pytest.fixture
    def client(self):
        """テストクライアント"""
        app = create_app()
        return TestClient(app)

    def test_beta_signup_success(self, client):
        """正常なベータ登録"""
        email = unique_email("success")
        response = client.post(
            "/beta/signup",
            json={"email": email}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "登録ありがとうございます" in data["message"]
        assert data["email"] == email

    def test_beta_signup_duplicate(self, client):
        """重複登録の処理"""
        email = unique_email("duplicate")
        # 1回目の登録
        client.post("/beta/signup", json={"email": email})

        # 2回目の登録（重複）
        response = client.post(
            "/beta/signup",
            json={"email": email}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "既に登録済み" in data["message"]

    def test_beta_signup_case_insensitive(self, client):
        """メールアドレスの大文字小文字を区別しない"""
        # ユニークなメールアドレス生成
        base = f"case_{uuid.uuid4().hex[:8]}"
        email_lower = f"{base}@example.com"
        email_upper = f"{base.upper()}@EXAMPLE.COM"

        # 小文字で登録
        client.post("/beta/signup", json={"email": email_lower})

        # 大文字混じりで再登録
        response = client.post(
            "/beta/signup",
            json={"email": email_upper}
        )

        assert response.status_code == 200
        data = response.json()
        assert "既に登録済み" in data["message"]

    def test_beta_signup_invalid_email(self, client):
        """無効なメールアドレス"""
        response = client.post(
            "/beta/signup",
            json={"email": "invalid-email"}
        )

        assert response.status_code == 422  # Validation Error

    def test_beta_signup_empty_email(self, client):
        """空のメールアドレス"""
        response = client.post(
            "/beta/signup",
            json={"email": ""}
        )

        assert response.status_code == 422  # Validation Error

    def test_beta_signup_missing_email(self, client):
        """メールアドレスなし"""
        response = client.post(
            "/beta/signup",
            json={}
        )

        assert response.status_code == 422  # Validation Error

    def test_beta_count(self, client):
        """ベータ登録者数の取得"""
        # 初期状態の取得
        response = client.get("/beta/count")
        assert response.status_code == 200
        initial_count = response.json()["count"]

        # 新規登録（ユニークなメールアドレス）
        email = unique_email("count")
        client.post("/beta/signup", json={"email": email})

        # カウント確認
        response = client.get("/beta/count")
        assert response.status_code == 200
        assert response.json()["count"] == initial_count + 1

    def test_beta_signup_various_domains(self, client):
        """様々なドメインのメールアドレス"""
        unique_suffix = uuid.uuid4().hex[:6]
        test_emails = [
            f"user_{unique_suffix}@gmail.com",
            f"user_{unique_suffix}@yahoo.co.jp",
            f"user_{unique_suffix}@company.example.com",
            f"user+tag_{unique_suffix}@example.com",
        ]

        for email in test_emails:
            response = client.post(
                "/beta/signup",
                json={"email": email}
            )
            assert response.status_code == 200
            assert response.json()["success"] is True
