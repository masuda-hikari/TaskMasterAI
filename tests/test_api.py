"""
API Module テスト

FastAPI Webインターフェースのユニットテスト
"""

import pytest
from datetime import datetime, timedelta
from src.api import AuthService, User, FASTAPI_AVAILABLE


class TestAuthService:
    """AuthServiceのテスト"""

    @pytest.fixture
    def auth_service(self):
        """AuthServiceのフィクスチャ"""
        return AuthService(secret_key="test-secret-key")

    def test_create_user(self, auth_service):
        """ユーザー作成"""
        user = auth_service.create_user(
            email="test@example.com",
            password="password123",
            name="Test User"
        )
        assert user is not None
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert user.plan == "free"
        assert user.id is not None

    def test_create_duplicate_user(self, auth_service):
        """重複ユーザーの作成"""
        auth_service.create_user(
            email="test@example.com",
            password="password123"
        )
        user2 = auth_service.create_user(
            email="test@example.com",
            password="password456"
        )
        assert user2 is None

    def test_authenticate_success(self, auth_service):
        """認証成功"""
        auth_service.create_user(
            email="test@example.com",
            password="password123"
        )
        user = auth_service.authenticate("test@example.com", "password123")
        assert user is not None
        assert user.email == "test@example.com"

    def test_authenticate_wrong_password(self, auth_service):
        """パスワード間違い"""
        auth_service.create_user(
            email="test@example.com",
            password="password123"
        )
        user = auth_service.authenticate("test@example.com", "wrong_password")
        assert user is None

    def test_authenticate_nonexistent_user(self, auth_service):
        """存在しないユーザー"""
        user = auth_service.authenticate("nonexistent@example.com", "password")
        assert user is None

    def test_create_access_token(self, auth_service):
        """アクセストークン生成"""
        token = auth_service.create_access_token("test_user_id")
        assert token is not None
        assert len(token) > 0

    def test_verify_token(self, auth_service):
        """トークン検証"""
        token = auth_service.create_access_token("test_user_id")
        user_id = auth_service.verify_token(token)
        assert user_id == "test_user_id"

    def test_verify_invalid_token(self, auth_service):
        """無効なトークンの検証"""
        user_id = auth_service.verify_token("invalid_token")
        assert user_id is None

    def test_get_user(self, auth_service):
        """ユーザー取得"""
        created_user = auth_service.create_user(
            email="test@example.com",
            password="password123"
        )
        user = auth_service.get_user(created_user.id)
        assert user is not None
        assert user.email == "test@example.com"

    def test_get_nonexistent_user(self, auth_service):
        """存在しないユーザーの取得"""
        user = auth_service.get_user("nonexistent_id")
        assert user is None

    def test_password_hashing(self, auth_service):
        """パスワードハッシュ化"""
        user = auth_service.create_user(
            email="test@example.com",
            password="password123"
        )
        # パスワードが平文で保存されていないことを確認
        assert user.password_hash != "password123"
        assert len(user.password_hash) > 0


class TestUser:
    """Userデータクラスのテスト"""

    def test_user_creation(self):
        """ユーザー作成"""
        user = User(
            id="test_id",
            email="test@example.com",
            password_hash="hashed",
            name="Test User",
            plan="free",
            created_at=datetime.now()
        )
        assert user.id == "test_id"
        assert user.email == "test@example.com"
        assert user.plan == "free"


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPIがインストールされていません")
class TestFastAPIEndpoints:
    """FastAPIエンドポイントのテスト"""

    @pytest.fixture
    def client(self):
        """テストクライアントのフィクスチャ"""
        from fastapi.testclient import TestClient
        from src.api import create_app

        app = create_app()
        return TestClient(app)

    def test_health_check(self, client):
        """ヘルスチェック"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data

    def test_register_user(self, client):
        """ユーザー登録"""
        response = client.post("/auth/register", json={
            "email": "newuser@example.com",
            "password": "password123",
            "name": "New User"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["name"] == "New User"
        assert data["plan"] == "free"
        assert "id" in data

    def test_register_duplicate_user(self, client):
        """重複ユーザー登録"""
        client.post("/auth/register", json={
            "email": "dup@example.com",
            "password": "password123"
        })
        response = client.post("/auth/register", json={
            "email": "dup@example.com",
            "password": "password456"
        })
        assert response.status_code == 400

    def test_login_success(self, client):
        """ログイン成功"""
        # ユーザー登録
        client.post("/auth/register", json={
            "email": "login@example.com",
            "password": "password123"
        })

        # ログイン
        response = client.post("/auth/login", json={
            "email": "login@example.com",
            "password": "password123"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data

    def test_login_failure(self, client):
        """ログイン失敗"""
        response = client.post("/auth/login", json={
            "email": "nonexistent@example.com",
            "password": "password123"
        })
        assert response.status_code == 401

    def test_get_me_authenticated(self, client):
        """認証済みユーザー情報取得"""
        # ユーザー登録
        client.post("/auth/register", json={
            "email": "me@example.com",
            "password": "password123",
            "name": "Me User"
        })

        # ログイン
        login_response = client.post("/auth/login", json={
            "email": "me@example.com",
            "password": "password123"
        })
        token = login_response.json()["access_token"]

        # ユーザー情報取得
        response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "me@example.com"
        assert data["name"] == "Me User"

    def test_get_me_unauthenticated(self, client):
        """未認証でのユーザー情報取得"""
        response = client.get("/auth/me")
        assert response.status_code in [401, 403]

    def test_email_summarize(self, client):
        """メール要約エンドポイント"""
        # ユーザー登録＆ログイン
        client.post("/auth/register", json={
            "email": "email@example.com",
            "password": "password123"
        })
        login_response = client.post("/auth/login", json={
            "email": "email@example.com",
            "password": "password123"
        })
        token = login_response.json()["access_token"]

        # メール要約リクエスト
        response = client.post(
            "/email/summarize",
            json={"max_emails": 10},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "summaries" in data
        assert "count" in data

    def test_schedule_propose(self, client):
        """スケジュール提案エンドポイント"""
        # ユーザー登録＆ログイン
        client.post("/auth/register", json={
            "email": "schedule@example.com",
            "password": "password123"
        })
        login_response = client.post("/auth/login", json={
            "email": "schedule@example.com",
            "password": "password123"
        })
        token = login_response.json()["access_token"]

        # スケジュール提案リクエスト
        response = client.post(
            "/schedule/propose",
            json={
                "title": "Team Meeting",
                "duration_minutes": 30,
                "attendees": ["alice@example.com"]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "proposals" in data
        assert "count" in data

    def test_get_usage(self, client):
        """使用量取得エンドポイント"""
        # ユーザー登録＆ログイン
        client.post("/auth/register", json={
            "email": "usage@example.com",
            "password": "password123"
        })
        login_response = client.post("/auth/login", json={
            "email": "usage@example.com",
            "password": "password123"
        })
        token = login_response.json()["access_token"]

        # 使用量取得
        response = client.get(
            "/usage",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "plan" in data
        assert "status" in data
        assert "email_summaries" in data
        assert "schedule_proposals" in data


class TestFastAPIAvailability:
    """FastAPI利用可能性のテスト"""

    def test_fastapi_available_flag(self):
        """FASTAPI_AVAILABLEフラグのテスト"""
        # FastAPIがインストールされているかどうかに関わらず
        # フラグが正しく設定されていることを確認
        assert isinstance(FASTAPI_AVAILABLE, bool)

    @pytest.mark.skipif(FASTAPI_AVAILABLE, reason="FastAPIがインストールされています")
    def test_create_app_without_fastapi(self):
        """FastAPIなしでのcreate_app"""
        from src.api import create_app
        with pytest.raises(RuntimeError):
            create_app()
