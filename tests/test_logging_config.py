"""
ロギング設定モジュールのテスト
"""

import pytest
import logging
import json
from datetime import datetime

from src.logging_config import (
    LogLevel,
    LogContext,
    StructuredLogRecord,
    JSONFormatter,
    ColoredConsoleFormatter,
    TaskMasterLogger,
    RequestContext,
    configure_logging,
    get_logger,
    set_user_context,
    set_operation_context,
    request_id_var,
    user_id_var,
    operation_var,
    PerformanceTimer,
    MetricsCollector,
    get_metrics,
)


class TestLogLevel:
    """LogLevelのテスト"""

    def test_log_levels(self):
        """ログレベル値"""
        assert LogLevel.DEBUG.value == "DEBUG"
        assert LogLevel.INFO.value == "INFO"
        assert LogLevel.WARNING.value == "WARNING"
        assert LogLevel.ERROR.value == "ERROR"
        assert LogLevel.CRITICAL.value == "CRITICAL"


class TestLogContext:
    """LogContextのテスト"""

    def test_default_context(self):
        """デフォルトコンテキスト"""
        context = LogContext()
        assert context.request_id == ""
        assert context.user_id == ""
        assert context.operation == ""
        assert context.component == ""

    def test_context_with_values(self):
        """値付きコンテキスト"""
        context = LogContext(
            request_id="req123",
            user_id="user456",
            operation="fetch_emails",
            component="email_bot"
        )
        assert context.request_id == "req123"
        assert context.user_id == "user456"
        assert context.operation == "fetch_emails"
        assert context.component == "email_bot"

    def test_from_context_vars(self):
        """コンテキスト変数からの生成"""
        request_id_var.set("test_req")
        user_id_var.set("test_user")
        operation_var.set("test_op")

        context = LogContext.from_context_vars(component="test")
        assert context.request_id == "test_req"
        assert context.user_id == "test_user"
        assert context.operation == "test_op"
        assert context.component == "test"

        # クリーンアップ
        request_id_var.set("")
        user_id_var.set("")
        operation_var.set("")


class TestStructuredLogRecord:
    """StructuredLogRecordのテスト"""

    def test_basic_record(self):
        """基本レコード"""
        context = LogContext(request_id="req123")
        record = StructuredLogRecord(
            timestamp=datetime.now().isoformat(),
            level="INFO",
            message="テストメッセージ",
            logger_name="test",
            context=context
        )
        assert record.level == "INFO"
        assert record.message == "テストメッセージ"

    def test_to_dict(self):
        """辞書変換"""
        context = LogContext(
            request_id="req123",
            user_id="user456",
            operation="test_op"
        )
        record = StructuredLogRecord(
            timestamp="2024-01-01T00:00:00",
            level="INFO",
            message="テストメッセージ",
            logger_name="test",
            context=context,
            data={"key": "value"},
            duration_ms=100.5
        )
        result = record.to_dict()

        assert result["timestamp"] == "2024-01-01T00:00:00"
        assert result["level"] == "INFO"
        assert result["message"] == "テストメッセージ"
        assert result["context"]["request_id"] == "req123"
        assert result["data"]["key"] == "value"
        assert result["duration_ms"] == 100.5

    def test_to_json(self):
        """JSON変換"""
        context = LogContext()
        record = StructuredLogRecord(
            timestamp="2024-01-01T00:00:00",
            level="INFO",
            message="テスト",
            logger_name="test",
            context=context
        )
        json_str = record.to_json()
        parsed = json.loads(json_str)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "テスト"


class TestJSONFormatter:
    """JSONFormatterのテスト"""

    def test_format_basic(self):
        """基本フォーマット"""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="テストメッセージ",
            args=(),
            exc_info=None
        )
        result = formatter.format(record)
        parsed = json.loads(result)

        assert parsed["level"] == "INFO"
        assert parsed["message"] == "テストメッセージ"
        assert parsed["logger"] == "test"

    def test_format_with_exception(self):
        """例外情報付きフォーマット"""
        formatter = JSONFormatter()
        try:
            raise ValueError("テストエラー")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="エラー発生",
            args=(),
            exc_info=exc_info
        )
        result = formatter.format(record)
        parsed = json.loads(result)

        assert parsed["error"]["type"] == "ValueError"
        assert "テストエラー" in parsed["error"]["message"]


class TestColoredConsoleFormatter:
    """ColoredConsoleFormatterのテスト"""

    def test_format_basic(self):
        """基本フォーマット"""
        formatter = ColoredConsoleFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="テストメッセージ",
            args=(),
            exc_info=None
        )
        result = formatter.format(record)

        assert "INFO" in result
        assert "テストメッセージ" in result
        assert "test" in result

    def test_format_with_context(self):
        """コンテキスト付きフォーマット"""
        request_id_var.set("req123")
        user_id_var.set("user456")

        formatter = ColoredConsoleFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="テスト",
            args=(),
            exc_info=None
        )
        result = formatter.format(record)

        assert "req=" in result or "user=" in result

        # クリーンアップ
        request_id_var.set("")
        user_id_var.set("")


class TestTaskMasterLogger:
    """TaskMasterLoggerのテスト"""

    def test_basic_logging(self, caplog):
        """基本ログ出力"""
        with caplog.at_level(logging.DEBUG):
            logger = get_logger("test_logger", "test_component")
            logger.debug("デバッグ")
            logger.info("情報")
            logger.warning("警告")

        assert "デバッグ" in caplog.text
        assert "情報" in caplog.text
        assert "警告" in caplog.text

    def test_logging_with_data(self, caplog):
        """データ付きログ"""
        with caplog.at_level(logging.INFO):
            logger = get_logger("test")
            logger.info("データ付き", data={"key": "value"})

        # dataは追加情報として記録される
        assert "データ付き" in caplog.text

    def test_operation_start_end(self, caplog):
        """操作開始・終了ログ"""
        with caplog.at_level(logging.INFO):
            logger = get_logger("test")
            req_id = logger.operation_start("test_operation", data={"input": "test"})
            logger.operation_end("test_operation", duration_ms=100.0, success=True)

        assert req_id is not None
        assert len(req_id) > 0


class TestRequestContext:
    """RequestContextのテスト"""

    def test_context_manager(self):
        """コンテキストマネージャ"""
        with RequestContext(user_id="test_user", operation="test_op") as ctx:
            assert ctx.request_id is not None
            assert request_id_var.get() == ctx.request_id
            assert user_id_var.get() == "test_user"
            assert operation_var.get() == "test_op"

        # コンテキスト外では空
        assert request_id_var.get() == ""
        assert user_id_var.get() == ""
        assert operation_var.get() == ""

    def test_custom_request_id(self):
        """カスタムリクエストID"""
        with RequestContext(request_id="custom_req_123") as ctx:
            assert ctx.request_id == "custom_req_123"
            assert request_id_var.get() == "custom_req_123"


class TestSetContextFunctions:
    """コンテキスト設定関数のテスト"""

    def test_set_user_context(self):
        """ユーザーコンテキスト設定"""
        set_user_context("user123")
        assert user_id_var.get() == "user123"
        user_id_var.set("")

    def test_set_operation_context(self):
        """操作コンテキスト設定"""
        set_operation_context("operation123")
        assert operation_var.get() == "operation123"
        operation_var.set("")


class TestConfigureLogging:
    """configure_loggingのテスト"""

    def test_basic_configuration(self):
        """基本設定"""
        configure_logging(
            level="DEBUG",
            console_output=True,
            file_output=False
        )

        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG
        assert len(root_logger.handlers) > 0

    def test_log_level_override(self):
        """ログレベルオーバーライド"""
        configure_logging(level="WARNING", console_output=True, file_output=False)
        root_logger = logging.getLogger()
        assert root_logger.level == logging.WARNING


class TestPerformanceTimer:
    """PerformanceTimerのテスト"""

    def test_timer_context_manager(self, caplog):
        """タイマーコンテキストマネージャ"""
        import time

        with caplog.at_level(logging.INFO):
            logger = get_logger("test")
            with PerformanceTimer(logger, "test_operation"):
                time.sleep(0.01)  # 10ms

        assert "操作終了" in caplog.text or "test_operation" in caplog.text

    def test_timer_with_exception(self, caplog):
        """例外時のタイマー"""
        with caplog.at_level(logging.INFO):
            logger = get_logger("test")
            try:
                with PerformanceTimer(logger, "failing_operation"):
                    raise ValueError("Test error")
            except ValueError:
                pass

        # 失敗時もログが出力される
        assert "操作終了" in caplog.text or "failing_operation" in caplog.text


class TestMetricsCollector:
    """MetricsCollectorのテスト"""

    def test_singleton(self):
        """シングルトン"""
        metrics1 = get_metrics()
        metrics2 = get_metrics()
        assert metrics1 is metrics2

    def test_increment(self):
        """カウンターインクリメント"""
        metrics = get_metrics()
        metrics.reset()

        metrics.increment("test_counter")
        metrics.increment("test_counter")
        metrics.increment("test_counter", value=3)

        all_metrics = metrics.get_all()
        assert all_metrics["counters"]["test_counter"] == 5

    def test_increment_with_tags(self):
        """タグ付きカウンター"""
        metrics = get_metrics()
        metrics.reset()

        metrics.increment("api_calls", tags={"endpoint": "/test"})
        metrics.increment("api_calls", tags={"endpoint": "/other"})
        metrics.increment("api_calls", tags={"endpoint": "/test"})

        all_metrics = metrics.get_all()
        assert all_metrics["counters"]["api_calls[endpoint=/test]"] == 2
        assert all_metrics["counters"]["api_calls[endpoint=/other]"] == 1

    def test_gauge(self):
        """ゲージ値"""
        metrics = get_metrics()
        metrics.reset()

        metrics.gauge("memory_usage", 1024.5)
        metrics.gauge("memory_usage", 2048.0)

        all_metrics = metrics.get_all()
        assert all_metrics["gauges"]["memory_usage"] == 2048.0

    def test_timing(self):
        """タイミング記録"""
        metrics = get_metrics()
        metrics.reset()

        metrics.timing("response_time", 100.0)
        metrics.timing("response_time", 200.0)
        metrics.timing("response_time", 150.0)

        all_metrics = metrics.get_all()
        timing = all_metrics["timings"]["response_time"]
        assert timing["count"] == 3
        assert timing["total_ms"] == 450.0
        assert timing["min_ms"] == 100.0
        assert timing["max_ms"] == 200.0

    def test_reset(self):
        """メトリクスリセット"""
        metrics = get_metrics()
        metrics.increment("counter")
        metrics.gauge("gauge", 100)

        metrics.reset()

        all_metrics = metrics.get_all()
        assert len(all_metrics["counters"]) == 0
        assert len(all_metrics["gauges"]) == 0


class TestIntegration:
    """統合テスト"""

    def test_logging_with_context_and_metrics(self, caplog):
        """コンテキストとメトリクス付きロギング"""
        configure_logging(level="DEBUG", console_output=True, file_output=False)
        metrics = get_metrics()
        metrics.reset()

        with caplog.at_level(logging.INFO):
            with RequestContext(user_id="integration_user", operation="integration_test") as ctx:
                logger = get_logger("integration", "test_component")
                logger.info("Integration test start", data={"test_id": ctx.request_id})

                metrics.increment("integration_test_runs")

                logger.info("Integration test end", duration_ms=50.0)

        # メトリクスが正しく記録されていることを確認
        assert metrics.get_all()["counters"]["integration_test_runs"] == 1
        # コンテキストが正しく設定されていることを確認（ログ出力は環境依存）
        assert ctx.request_id is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
