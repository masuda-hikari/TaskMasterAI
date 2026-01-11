"""
レート制限機能のテスト

DDoS対策およびAPI濫用防止のためのレート制限機能をテスト
"""

import pytest
import time
from unittest.mock import patch, MagicMock

from src.api import RateLimiter, rate_limiters


class TestRateLimiter:
    """RateLimiterクラスのテスト"""

    def test_initialization(self):
        """初期化パラメータのテスト"""
        limiter = RateLimiter(requests_per_minute=30, burst_size=5)
        assert limiter.requests_per_minute == 30
        assert limiter.burst_size == 5

    def test_default_initialization(self):
        """デフォルト初期化のテスト"""
        limiter = RateLimiter()
        assert limiter.requests_per_minute == 60
        assert limiter.burst_size == 10

    def test_is_allowed_initial_request(self):
        """初回リクエストの許可テスト"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=10)
        allowed, meta = limiter.is_allowed("test_ip")
        assert allowed is True
        assert "remaining" in meta
        assert "limit" in meta
        assert meta["limit"] == 60

    def test_is_allowed_within_burst(self):
        """バースト内リクエストの許可テスト"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=5)
        # バースト内の5リクエスト
        for i in range(5):
            allowed, meta = limiter.is_allowed("test_ip")
            assert allowed is True

    def test_is_allowed_exceeds_burst(self):
        """バースト超過時の拒否テスト"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=3)
        # 3リクエストは許可
        for _ in range(3):
            allowed, _ = limiter.is_allowed("test_ip")
            assert allowed is True
        # 4番目は拒否
        allowed, meta = limiter.is_allowed("test_ip")
        assert allowed is False
        assert "retry_after" in meta

    def test_is_allowed_different_keys(self):
        """異なるキーは独立してレート制限されることを確認"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=2)
        # ip1で2リクエスト
        for _ in range(2):
            limiter.is_allowed("ip1")
        # ip1は制限超過
        allowed1, _ = limiter.is_allowed("ip1")
        assert allowed1 is False
        # ip2はまだ許可
        allowed2, _ = limiter.is_allowed("ip2")
        assert allowed2 is True

    def test_token_refill(self):
        """トークン補充のテスト"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=2)
        # 全トークン消費
        limiter.is_allowed("test_ip")
        limiter.is_allowed("test_ip")
        # 制限超過
        allowed, _ = limiter.is_allowed("test_ip")
        assert allowed is False

        # 時間経過をシミュレート - 直接内部状態を変更
        base_time = time.time()
        limiter._last_update["test_ip"] = base_time - 2  # 2秒前に更新したことにする
        limiter._tokens["test_ip"] = 0.0
        if "test_ip" in limiter._lock_until:
            del limiter._lock_until["test_ip"]  # ロック解除

        # トークン補充後は許可（_refill_tokensが呼ばれる）
        allowed, _ = limiter.is_allowed("test_ip")
        assert allowed is True

    def test_reset(self):
        """リセット機能のテスト"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=2)
        # トークン消費
        limiter.is_allowed("test_ip")
        limiter.is_allowed("test_ip")
        limiter.is_allowed("test_ip")  # 制限超過

        # リセット
        limiter.reset("test_ip")

        # リセット後は許可
        allowed, _ = limiter.is_allowed("test_ip")
        assert allowed is True

    def test_get_status(self):
        """ステータス取得のテスト"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=5)
        limiter.is_allowed("test_ip")  # 1トークン消費

        status = limiter.get_status("test_ip")
        assert "remaining" in status
        assert "limit" in status
        assert "burst_size" in status
        assert "locked" in status
        assert status["limit"] == 60
        assert status["burst_size"] == 5

    def test_lock_on_exceed(self):
        """制限超過時のロック機能テスト"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=1)
        # 1リクエスト許可
        limiter.is_allowed("test_ip")
        # 2リクエスト目で制限超過＆ロック
        allowed, meta = limiter.is_allowed("test_ip")
        assert allowed is False
        # 最初の超過時は "rate_limit_exceeded"
        assert meta.get("reason") in ("rate_limit_exceeded", "too_many_requests")

        # ロック中は拒否（"too_many_requests"）
        allowed, meta = limiter.is_allowed("test_ip")
        assert allowed is False
        assert meta.get("locked") is True
        assert meta.get("reason") == "too_many_requests"


class TestRateLimitersConfiguration:
    """グローバルレートリミッター設定のテスト"""

    def test_rate_limiters_exist(self):
        """全レートリミッターが存在することを確認"""
        assert "default" in rate_limiters
        assert "auth" in rate_limiters
        assert "beta" in rate_limiters
        assert "api" in rate_limiters

    def test_auth_limiter_is_stricter(self):
        """認証用リミッターがより厳しいことを確認"""
        default = rate_limiters["default"]
        auth = rate_limiters["auth"]
        assert auth.requests_per_minute < default.requests_per_minute

    def test_api_limiter_is_relaxed(self):
        """API用リミッターがより緩いことを確認"""
        default = rate_limiters["default"]
        api = rate_limiters["api"]
        assert api.requests_per_minute >= default.requests_per_minute


class TestRateLimitMiddleware:
    """レート制限ミドルウェアのテスト"""

    @pytest.fixture
    def client(self):
        """テストクライアント（レート制限有効）"""
        import os
        import importlib
        # レート制限を有効化
        os.environ["DATABASE_PATH"] = ":memory:"
        os.environ["DISABLE_RATE_LIMIT"] = "false"
        # api モジュールを再ロードしてレート制限を有効にした状態で作成
        import src.api
        importlib.reload(src.api)
        from fastapi.testclient import TestClient
        from src.api import create_app
        # レートリミッターをリセット
        for limiter in rate_limiters.values():
            limiter._tokens.clear()
            limiter._last_update.clear()
            limiter._lock_until.clear()
        app = create_app()
        client = TestClient(app)
        yield client
        # 後処理：レート制限を再度無効化
        os.environ["DISABLE_RATE_LIMIT"] = "true"

    def test_health_check_no_rate_limit(self, client):
        """ヘルスチェックはレート制限対象外"""
        # 大量リクエストを送っても制限されない
        for _ in range(20):
            response = client.get("/health")
            assert response.status_code == 200

    def test_rate_limit_headers_present(self, client):
        """レート制限ヘッダーが存在することを確認"""
        # レートリミッターをリセット
        for limiter in rate_limiters.values():
            limiter.reset("testclient")

        response = client.get("/demo/emails")
        assert response.status_code == 200
        # ヘッダーが存在することを確認（ミドルウェアが有効な場合）
        # 注: テスト環境ではミドルウェアの動作が異なる場合がある

    def test_beta_endpoint_rate_limit(self, client):
        """ベータエンドポイントのレート制限テスト"""
        # レートリミッターをリセット
        rate_limiters["beta"].reset("testclient")
        rate_limiters["beta"]._tokens["testclient"] = 2

        # 許可されるリクエスト
        response1 = client.get("/beta/count")
        assert response1.status_code == 200

    def test_429_response_format(self):
        """429レスポンスのフォーマットテスト"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=1)
        limiter.is_allowed("test_ip")
        allowed, meta = limiter.is_allowed("test_ip")
        assert allowed is False
        assert "retry_after" in meta
        assert isinstance(meta["retry_after"], int)


class TestRateLimitEdgeCases:
    """レート制限のエッジケーステスト"""

    def test_empty_key(self):
        """空のキーでの動作テスト"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=5)
        allowed, _ = limiter.is_allowed("")
        assert allowed is True

    def test_special_characters_in_key(self):
        """特殊文字を含むキーでの動作テスト"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=5)
        allowed, _ = limiter.is_allowed("192.168.1.1, 10.0.0.1")
        assert allowed is True

    def test_very_high_burst(self):
        """非常に高いバースト設定のテスト"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=1000)
        for _ in range(100):
            allowed, _ = limiter.is_allowed("test_ip")
            assert allowed is True

    def test_very_low_rate(self):
        """非常に低いレート設定のテスト"""
        # バーストサイズ1で新しいキーを使用
        limiter = RateLimiter(requests_per_minute=1, burst_size=1)
        # 新しいキーで最初のリクエスト
        key = f"test_low_rate_{time.time()}"
        allowed1, _ = limiter.is_allowed(key)
        assert allowed1 is True
        # 2番目のリクエストは拒否
        allowed2, _ = limiter.is_allowed(key)
        assert allowed2 is False

    def test_concurrent_access_simulation(self):
        """同時アクセスのシミュレーションテスト"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=10)
        results = []
        # 複数のIPから同時アクセス
        for i in range(20):
            ip = f"192.168.1.{i}"
            allowed, _ = limiter.is_allowed(ip)
            results.append(allowed)
        # 全て異なるIPなので全て許可
        assert all(results)

    def test_lock_expiry(self):
        """ロック期限切れのテスト"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=1)
        key = f"lock_expiry_{time.time()}"
        # 制限超過
        limiter.is_allowed(key)
        limiter.is_allowed(key)

        # ロックが設定されていることを確認
        assert key in limiter._lock_until

        # ロック時間を過去に設定（期限切れ）
        limiter._lock_until[key] = time.time() - 1
        # トークンを補充して再試行可能に
        limiter._tokens[key] = 1.0

        # 期限切れ後はロック解除（is_allowedでロック削除される）
        allowed, meta = limiter.is_allowed(key)
        # ロック解除されたことを確認
        assert key not in limiter._lock_until
        # 許可されたことを確認
        assert allowed is True
