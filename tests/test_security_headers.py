# -*- coding: utf-8 -*-
"""
セキュリティヘッダーミドルウェアのテスト

OWASP推奨のセキュリティヘッダーが正しく付与されることを検証
"""

import pytest
from fastapi.testclient import TestClient
import os


class TestSecurityHeadersMiddleware:
    """セキュリティヘッダーミドルウェアのテスト"""

    @pytest.fixture
    def client(self):
        """テストクライアント"""
        from src.api import create_app
        app = create_app()
        return TestClient(app)

    def test_x_content_type_options(self, client):
        """X-Content-Type-Optionsヘッダーがnosniffで設定されること"""
        response = client.get("/health")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_xss_protection(self, client):
        """X-XSS-Protectionヘッダーが設定されること"""
        response = client.get("/health")
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"

    def test_x_frame_options(self, client):
        """X-Frame-OptionsヘッダーがDENYで設定されること"""
        response = client.get("/health")
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_content_security_policy(self, client):
        """Content-Security-Policyヘッダーが設定されること"""
        response = client.get("/health")
        csp = response.headers.get("Content-Security-Policy")
        assert csp is not None
        assert "default-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_referrer_policy(self, client):
        """Referrer-Policyヘッダーが設定されること"""
        response = client.get("/health")
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_permissions_policy(self, client):
        """Permissions-Policyヘッダーが設定されること"""
        response = client.get("/health")
        pp = response.headers.get("Permissions-Policy")
        assert pp is not None
        assert "camera=()" in pp
        assert "microphone=()" in pp

    def test_cache_control_on_auth_endpoints(self, client):
        """認証エンドポイントでキャッシュ無効化ヘッダーが設定されること"""
        response = client.post(
            "/auth/login",
            json={"email": "test@example.com", "password": "wrong"}
        )
        # 認証失敗でもヘッダーは設定される
        assert response.headers.get("Cache-Control") == "no-store, no-cache, must-revalidate, private"
        assert response.headers.get("Pragma") == "no-cache"

    def test_hsts_not_set_in_development(self, client):
        """開発環境ではHSTSが設定されないこと"""
        # デフォルトはdevelopment
        response = client.get("/health")
        # HSTSは本番環境のみ
        assert response.headers.get("Strict-Transport-Security") is None

    def test_security_headers_on_all_endpoints(self, client):
        """全エンドポイントでセキュリティヘッダーが設定されること"""
        endpoints = [
            ("/health", "GET"),
            ("/demo/emails", "GET"),
            ("/demo/schedule", "GET"),
            ("/demo/features", "GET"),
            ("/beta/count", "GET"),
        ]

        for path, method in endpoints:
            if method == "GET":
                response = client.get(path)
            else:
                response = client.post(path)

            assert response.headers.get("X-Content-Type-Options") == "nosniff", f"Failed for {path}"
            assert response.headers.get("X-Frame-Options") == "DENY", f"Failed for {path}"

    def test_security_headers_on_error_responses(self, client):
        """エラーレスポンスでもセキュリティヘッダーが設定されること"""
        # 存在しないエンドポイント
        response = client.get("/nonexistent")
        assert response.status_code == 404
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_security_headers_on_beta_signup(self, client):
        """ベータ登録エンドポイントでセキュリティヘッダーが設定されること"""
        response = client.post(
            "/beta/signup",
            json={"email": "sectest@example.com"}
        )
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"


class TestSecurityHeadersProduction:
    """本番環境でのセキュリティヘッダーテスト"""

    @pytest.fixture
    def production_client(self, monkeypatch):
        """本番環境をシミュレートしたテストクライアント"""
        monkeypatch.setenv("ENVIRONMENT", "production")
        # アプリを再作成してミドルウェアを再適用
        from importlib import reload
        import src.api
        reload(src.api)
        app = src.api.create_app()
        return TestClient(app)

    def test_hsts_set_in_production(self, production_client):
        """本番環境ではHSTSが設定されること"""
        response = production_client.get("/health")
        hsts = response.headers.get("Strict-Transport-Security")
        assert hsts is not None
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts


class TestSecurityMitigations:
    """セキュリティ対策のテスト"""

    @pytest.fixture
    def client(self):
        """テストクライアント"""
        from src.api import create_app
        app = create_app()
        return TestClient(app)

    def test_clickjacking_protection(self, client):
        """クリックジャッキング対策が有効であること"""
        response = client.get("/health")
        # X-Frame-Options: DENY またはCSPのframe-ancestors
        x_frame = response.headers.get("X-Frame-Options")
        csp = response.headers.get("Content-Security-Policy")

        assert x_frame == "DENY" or "frame-ancestors 'none'" in (csp or "")

    def test_mime_sniffing_protection(self, client):
        """MIMEスニッフィング対策が有効であること"""
        response = client.get("/health")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_xss_protection(self, client):
        """XSS対策ヘッダーが設定されていること"""
        response = client.get("/health")
        # X-XSS-ProtectionまたはCSP
        xss = response.headers.get("X-XSS-Protection")
        csp = response.headers.get("Content-Security-Policy")

        assert xss is not None or csp is not None
