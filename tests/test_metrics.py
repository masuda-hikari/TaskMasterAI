"""
メトリクス機能のテスト

MetricsCollector、メトリクスエンドポイントのテスト
"""

import time
import pytest
from unittest.mock import patch


class TestMetricsCollector:
    """MetricsCollectorクラスのテスト"""

    def test_init(self):
        """初期化テスト"""
        from src.api import MetricsCollector
        collector = MetricsCollector()

        assert collector._start_time > 0
        assert len(collector._request_count) == 0
        assert len(collector._error_count) == 0
        assert len(collector._response_times) == 0
        assert len(collector._status_codes) == 0

    def test_record_request_success(self):
        """リクエスト記録（成功）テスト"""
        from src.api import MetricsCollector
        collector = MetricsCollector()

        collector.record_request(
            endpoint="/health",
            method="GET",
            status_code=200,
            response_time_ms=15.5
        )

        assert collector._request_count["GET:/health"] == 1
        assert collector._status_codes[200] == 1
        assert len(collector._response_times["GET:/health"]) == 1
        assert collector._response_times["GET:/health"][0] == 15.5

    def test_record_request_error(self):
        """リクエスト記録（エラー）テスト"""
        from src.api import MetricsCollector
        collector = MetricsCollector()

        collector.record_request(
            endpoint="/auth/login",
            method="POST",
            status_code=401,
            response_time_ms=25.0
        )

        assert collector._request_count["POST:/auth/login"] == 1
        assert collector._error_count["POST:/auth/login"] == 1
        assert collector._status_codes[401] == 1

    def test_record_multiple_requests(self):
        """複数リクエスト記録テスト"""
        from src.api import MetricsCollector
        collector = MetricsCollector()

        for i in range(5):
            collector.record_request(
                endpoint="/health",
                method="GET",
                status_code=200,
                response_time_ms=10.0 + i
            )

        assert collector._request_count["GET:/health"] == 5
        assert collector._status_codes[200] == 5
        assert len(collector._response_times["GET:/health"]) == 5

    def test_max_response_samples(self):
        """レスポンスタイムサンプル数上限テスト"""
        from src.api import MetricsCollector
        collector = MetricsCollector()
        collector._max_response_samples = 10  # テスト用に小さくする

        for i in range(20):
            collector.record_request(
                endpoint="/test",
                method="GET",
                status_code=200,
                response_time_ms=float(i)
            )

        # 最新の10件のみ保持
        assert len(collector._response_times["GET:/test"]) == 10
        # 古いものが削除され、10-19のみ残る
        assert collector._response_times["GET:/test"][0] == 10.0
        assert collector._response_times["GET:/test"][-1] == 19.0

    def test_get_metrics(self):
        """メトリクス取得テスト"""
        from src.api import MetricsCollector
        collector = MetricsCollector()

        collector.record_request("/health", "GET", 200, 10.0)
        collector.record_request("/health", "GET", 200, 20.0)
        collector.record_request("/auth/login", "POST", 401, 50.0)

        metrics = collector.get_metrics()

        assert "uptime_seconds" in metrics
        assert metrics["total_requests"] == 3
        assert metrics["total_errors"] == 1
        assert metrics["error_rate"] > 0
        assert metrics["avg_response_time_ms"] > 0
        assert metrics["max_response_time_ms"] == 50.0
        assert 200 in metrics["status_codes"]
        assert 401 in metrics["status_codes"]
        assert "GET:/health" in metrics["endpoints"]

    def test_get_metrics_empty(self):
        """空のメトリクス取得テスト"""
        from src.api import MetricsCollector
        collector = MetricsCollector()

        metrics = collector.get_metrics()

        assert metrics["total_requests"] == 0
        assert metrics["total_errors"] == 0
        assert metrics["error_rate"] == 0
        assert metrics["avg_response_time_ms"] == 0
        assert metrics["max_response_time_ms"] == 0

    def test_get_prometheus_metrics(self):
        """Prometheusメトリクス出力テスト"""
        from src.api import MetricsCollector
        collector = MetricsCollector()

        collector.record_request("/health", "GET", 200, 10.0)
        collector.record_request("/auth/login", "POST", 401, 50.0)

        prom_output = collector.get_prometheus_metrics()

        # 必須メトリクスの存在確認
        assert "taskmasterai_uptime_seconds" in prom_output
        assert "taskmasterai_requests_total" in prom_output
        assert "taskmasterai_errors_total" in prom_output
        assert "taskmasterai_error_rate" in prom_output
        assert "taskmasterai_response_time_avg_ms" in prom_output
        assert "taskmasterai_http_status" in prom_output
        assert "taskmasterai_endpoint_requests" in prom_output
        # ラベル確認
        assert 'code="200"' in prom_output
        assert 'code="401"' in prom_output
        assert 'method="GET"' in prom_output
        assert 'path="/health"' in prom_output

    def test_reset(self):
        """リセットテスト"""
        from src.api import MetricsCollector
        collector = MetricsCollector()

        collector.record_request("/health", "GET", 200, 10.0)
        collector.record_request("/auth/login", "POST", 401, 50.0)

        collector.reset()

        assert len(collector._request_count) == 0
        assert len(collector._error_count) == 0
        assert len(collector._response_times) == 0
        assert len(collector._status_codes) == 0


class TestMetricsEndpoints:
    """メトリクスエンドポイントのテスト"""

    @pytest.fixture
    def client(self):
        """テストクライアント"""
        import os
        os.environ["DISABLE_RATE_LIMIT"] = "true"
        os.environ["DATABASE_PATH"] = ":memory:"

        from src.api import create_app, FASTAPI_AVAILABLE
        if not FASTAPI_AVAILABLE:
            pytest.skip("FastAPI not available")

        from fastapi.testclient import TestClient
        app = create_app()
        return TestClient(app)

    def test_metrics_endpoint(self, client):
        """メトリクスエンドポイント（JSON）テスト"""
        response = client.get("/metrics")
        assert response.status_code == 200

        data = response.json()
        assert "uptime_seconds" in data
        assert "total_requests" in data
        assert "total_errors" in data
        assert "error_rate" in data
        assert "avg_response_time_ms" in data
        assert "max_response_time_ms" in data
        assert "status_codes" in data
        assert "endpoints" in data

    def test_prometheus_metrics_endpoint(self, client):
        """Prometheusメトリクスエンドポイントテスト"""
        response = client.get("/metrics/prometheus")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

        content = response.text
        assert "# HELP" in content
        assert "# TYPE" in content
        assert "taskmasterai_uptime_seconds" in content
        assert "taskmasterai_requests_total" in content

    def test_metrics_after_requests(self, client):
        """リクエスト後のメトリクス確認テスト"""
        # いくつかのリクエストを実行
        client.get("/health")
        client.get("/health")
        client.get("/demo/features")

        response = client.get("/metrics")
        data = response.json()

        # リクエストがカウントされている
        assert data["total_requests"] >= 3

    def test_metrics_not_counting_self(self, client):
        """メトリクスエンドポイント自体がカウントされないテスト"""
        # 初期状態を取得
        response1 = client.get("/metrics")
        initial_count = response1.json()["total_requests"]

        # メトリクスを複数回取得
        client.get("/metrics")
        client.get("/metrics")
        client.get("/metrics/prometheus")

        # 再度確認（カウントは増えていないはず）
        response2 = client.get("/metrics")
        final_count = response2.json()["total_requests"]

        # 差分は0であるべき（メトリクスエンドポイント自体はカウント対象外）
        assert final_count == initial_count


class TestMetricsMiddleware:
    """MetricsMiddlewareのテスト"""

    @pytest.fixture
    def client_with_metrics(self):
        """メトリクス有効なテストクライアント"""
        import os
        os.environ["DISABLE_RATE_LIMIT"] = "true"
        os.environ["DISABLE_METRICS"] = "false"
        os.environ["DATABASE_PATH"] = ":memory:"

        from src.api import create_app, FASTAPI_AVAILABLE, metrics_collector
        if not FASTAPI_AVAILABLE:
            pytest.skip("FastAPI not available")

        # メトリクスをリセット
        metrics_collector.reset()

        from fastapi.testclient import TestClient
        app = create_app()
        return TestClient(app)

    def test_middleware_records_successful_requests(self, client_with_metrics):
        """ミドルウェアが成功リクエストを記録するテスト"""
        from src.api import metrics_collector

        initial = metrics_collector.get_metrics()["total_requests"]

        client_with_metrics.get("/health")

        after = metrics_collector.get_metrics()["total_requests"]
        assert after > initial

    def test_middleware_records_error_requests(self, client_with_metrics):
        """ミドルウェアがエラーリクエストを記録するテスト"""
        from src.api import metrics_collector

        # 存在しないエンドポイント
        client_with_metrics.get("/nonexistent")

        metrics = metrics_collector.get_metrics()
        assert 404 in metrics["status_codes"]

    def test_middleware_tracks_response_time(self, client_with_metrics):
        """ミドルウェアがレスポンスタイムを記録するテスト"""
        from src.api import metrics_collector

        client_with_metrics.get("/health")

        metrics = metrics_collector.get_metrics()
        assert metrics["avg_response_time_ms"] >= 0
