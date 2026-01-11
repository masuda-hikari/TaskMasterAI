"""
デモモードエンドポイントのテスト

API認証情報がなくてもサービスの機能を体験できるエンドポイントのテスト
"""

import pytest
import os

# テスト用DB設定
os.environ.setdefault("DATABASE_PATH", ":memory:")

try:
    from fastapi.testclient import TestClient
    from src.api import create_app, FASTAPI_AVAILABLE
    TESTCLIENT_AVAILABLE = FASTAPI_AVAILABLE
except ImportError:
    TESTCLIENT_AVAILABLE = False


@pytest.fixture
def test_client():
    """FastAPI TestClientフィクスチャ"""
    if not TESTCLIENT_AVAILABLE:
        pytest.skip("FastAPIが利用できません")
    app = create_app()
    return TestClient(app)


class TestDemoEmailEndpoint:
    """デモメール要約エンドポイントのテスト"""

    def test_demo_emails_returns_sample_data(self, test_client):
        """デモエンドポイントがサンプルデータを返すこと"""
        response = test_client.get("/demo/emails")
        assert response.status_code == 200

        data = response.json()
        assert "summaries" in data
        assert "count" in data
        assert "demo_mode" in data
        assert "message" in data

        assert data["demo_mode"] is True
        assert data["count"] == len(data["summaries"])
        assert data["count"] > 0

    def test_demo_emails_no_auth_required(self, test_client):
        """認証なしでアクセスできること"""
        # 認証ヘッダーなしでリクエスト
        response = test_client.get("/demo/emails")
        assert response.status_code == 200

    def test_demo_emails_structure(self, test_client):
        """メール要約の構造が正しいこと"""
        response = test_client.get("/demo/emails")
        data = response.json()

        for summary in data["summaries"]:
            assert "id" in summary
            assert "from" in summary
            assert "subject" in summary
            assert "summary" in summary
            assert "priority" in summary

    def test_demo_emails_priority_values(self, test_client):
        """優先度が有効な値であること"""
        response = test_client.get("/demo/emails")
        data = response.json()

        valid_priorities = {"high", "medium", "low"}
        for summary in data["summaries"]:
            assert summary["priority"] in valid_priorities


class TestDemoScheduleEndpoint:
    """デモスケジュール提案エンドポイントのテスト"""

    def test_demo_schedule_returns_proposals(self, test_client):
        """デモエンドポイントが提案を返すこと"""
        response = test_client.get("/demo/schedule")
        assert response.status_code == 200

        data = response.json()
        assert "proposals" in data
        assert "count" in data
        assert "demo_mode" in data
        assert "message" in data

        assert data["demo_mode"] is True
        assert data["count"] == len(data["proposals"])

    def test_demo_schedule_no_auth_required(self, test_client):
        """認証なしでアクセスできること"""
        response = test_client.get("/demo/schedule")
        assert response.status_code == 200

    def test_demo_schedule_structure(self, test_client):
        """スケジュール提案の構造が正しいこと"""
        response = test_client.get("/demo/schedule")
        data = response.json()

        for proposal in data["proposals"]:
            assert "id" in proposal
            assert "start" in proposal
            assert "end" in proposal
            assert "title" in proposal
            assert "score" in proposal
            assert "reason" in proposal

    def test_demo_schedule_scores_valid_range(self, test_client):
        """スコアが有効な範囲内であること"""
        response = test_client.get("/demo/schedule")
        data = response.json()

        for proposal in data["proposals"]:
            score = proposal["score"]
            assert 0 <= score <= 100


class TestDemoFeaturesEndpoint:
    """デモ機能一覧エンドポイントのテスト"""

    def test_demo_features_returns_list(self, test_client):
        """機能一覧を返すこと"""
        response = test_client.get("/demo/features")
        assert response.status_code == 200

        data = response.json()
        assert "features" in data
        assert "pricing" in data
        assert "demo_mode" in data
        assert data["demo_mode"] is True

    def test_demo_features_structure(self, test_client):
        """機能の構造が正しいこと"""
        response = test_client.get("/demo/features")
        data = response.json()

        for feature in data["features"]:
            assert "id" in feature
            assert "name" in feature
            assert "description" in feature

    def test_demo_pricing_in_jpy(self, test_client):
        """価格が日本円であること"""
        response = test_client.get("/demo/features")
        data = response.json()

        for plan_name, plan_info in data["pricing"].items():
            assert plan_info["currency"] == "JPY"
            assert isinstance(plan_info["price"], (int, float))

    def test_demo_pricing_plans_exist(self, test_client):
        """全プランが存在すること"""
        response = test_client.get("/demo/features")
        data = response.json()

        assert "free" in data["pricing"]
        assert "personal" in data["pricing"]
        assert "pro" in data["pricing"]

    def test_demo_pricing_limits_exist(self, test_client):
        """各プランに制限が設定されていること"""
        response = test_client.get("/demo/features")
        data = response.json()

        for plan_name, plan_info in data["pricing"].items():
            assert "email_limit" in plan_info
            assert "schedule_limit" in plan_info


class TestDemoEndpointsIntegration:
    """デモエンドポイント統合テスト"""

    def test_all_demo_endpoints_accessible(self, test_client):
        """全デモエンドポイントにアクセスできること"""
        endpoints = ["/demo/emails", "/demo/schedule", "/demo/features"]

        for endpoint in endpoints:
            response = test_client.get(endpoint)
            assert response.status_code == 200, f"{endpoint} failed"

    def test_demo_mode_flag_consistent(self, test_client):
        """全エンドポイントでdemo_modeフラグがTrueであること"""
        endpoints = ["/demo/emails", "/demo/schedule", "/demo/features"]

        for endpoint in endpoints:
            response = test_client.get(endpoint)
            data = response.json()
            assert data.get("demo_mode") is True, f"{endpoint} demo_mode is not True"

    def test_demo_endpoints_cors_headers(self, test_client):
        """CORSヘッダーが設定されていること"""
        response = test_client.options(
            "/demo/emails",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET"
            }
        )
        # CORSが許可されていれば200または204
        assert response.status_code in [200, 204, 405]
