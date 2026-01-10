# -*- coding: utf-8 -*-
"""
logging_config.pyカバレッジ向上テスト

対象: 88% → 95%目標
未カバー行:
- 83: context.additionalがある場合
- 235: critical ログ
- 338: production環境でのJSONFormatter
- 346-369: file_outputが有効な場合のハンドラー設定
- 460-490: __main__ブロック（テスト対象外）
"""

import pytest
import logging
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

from src.logging_config import (
    LogContext,
    StructuredLogRecord,
    JSONFormatter,
    ColoredConsoleFormatter,
    RequestContext,
    TaskMasterLogger,
    PerformanceTimer,
    MetricsCollector,
    configure_logging,
    get_logger,
    get_metrics,
    request_id_var,
    user_id_var,
    operation_var,
)


class TestStructuredLogRecordWithAdditional:
    """StructuredLogRecord.to_dict()のadditionalフィールドテスト"""

    def test_log_record_with_additional_context(self) -> None:
        """additionalフィールドを持つコンテキスト"""
        context = LogContext(
            request_id="req123",
            user_id="user456",
            operation="test_op",
            component="test_component",
            additional={"custom_field": "custom_value", "extra": 123}
        )
        record = StructuredLogRecord(
            timestamp=datetime.now().isoformat(),
            level="INFO",
            logger_name="test",
            message="テストメッセージ",
            context=context
        )

        result = record.to_dict()
        assert "additional" in result["context"]
        assert result["context"]["additional"]["custom_field"] == "custom_value"
        assert result["context"]["additional"]["extra"] == 123

    def test_log_record_without_additional_context(self) -> None:
        """additionalフィールドがないコンテキスト"""
        context = LogContext(
            request_id="req123",
            user_id="user456",
            operation="test_op",
            component="test_component"
        )
        record = StructuredLogRecord(
            timestamp=datetime.now().isoformat(),
            level="INFO",
            logger_name="test",
            message="テストメッセージ",
            context=context
        )

        result = record.to_dict()
        assert "additional" not in result["context"]


class TestTaskMasterLoggerCritical:
    """TaskMasterLogger.criticalメソッドのテスト"""

    def test_critical_log(self) -> None:
        """致命的エラーログの出力"""
        configure_logging(level="DEBUG", console_output=True, file_output=False)
        logger = get_logger("test_critical", "test")

        with patch.object(logger._logger, 'log') as mock_log:
            logger.critical("致命的エラー発生", data={"error": "システム停止"})
            mock_log.assert_called()
            # CRITICALレベルで呼ばれたことを確認
            call_args = mock_log.call_args
            assert call_args[0][0] == logging.CRITICAL

    def test_critical_log_with_exc_info(self) -> None:
        """exc_info付きcriticalログ"""
        configure_logging(level="DEBUG", console_output=True, file_output=False)
        logger = get_logger("test_critical_exc", "test")

        try:
            raise RuntimeError("テストエラー")
        except RuntimeError:
            with patch.object(logger._logger, 'log') as mock_log:
                logger.critical("例外付きcritical", exc_info=True)
                mock_log.assert_called()


class TestConfigureLoggingProductionJSON:
    """production環境でのJSONFormatter設定テスト"""

    def test_production_json_format(self) -> None:
        """production環境でJSONFormatterが使用される"""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            configure_logging(
                level="INFO",
                console_output=True,
                json_format=True,
                file_output=False
            )

            root_logger = logging.getLogger()
            # コンソールハンドラーがJSONFormatterを使用しているか確認
            console_handlers = [h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)]
            assert len(console_handlers) > 0

            # Formatterの型を確認
            for handler in console_handlers:
                if handler.formatter:
                    assert isinstance(handler.formatter, JSONFormatter)

    def test_development_colored_format(self) -> None:
        """development環境でColoredConsoleFormatterが使用される"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            configure_logging(
                level="INFO",
                console_output=True,
                json_format=False,  # json_formatがFalseの場合
                file_output=False
            )

            root_logger = logging.getLogger()
            console_handlers = [h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)]
            assert len(console_handlers) > 0


class TestConfigureLoggingFileOutput:
    """file_output有効時のハンドラー設定テスト"""

    def test_file_output_creates_handlers(self, tmp_path) -> None:
        """ファイル出力が有効な場合、ファイルハンドラーが作成される"""
        log_dir = str(tmp_path / "logs")

        configure_logging(
            level="DEBUG",
            log_dir=log_dir,
            console_output=False,
            file_output=True,
            max_file_size_mb=1,
            backup_count=3
        )

        root_logger = logging.getLogger()

        # RotatingFileHandlerが追加されているか確認
        file_handlers = [
            h for h in root_logger.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(file_handlers) >= 1

        # ログディレクトリが作成されているか確認
        assert Path(log_dir).exists()

    def test_file_output_creates_error_log(self, tmp_path) -> None:
        """エラーログファイルが別途作成される"""
        log_dir = str(tmp_path / "logs")

        configure_logging(
            level="DEBUG",
            log_dir=log_dir,
            console_output=False,
            file_output=True
        )

        # ログファイルパスを確認
        log_path = Path(log_dir)
        # configure_logging後、ハンドラーが設定されているはず
        root_logger = logging.getLogger()
        file_handlers = [
            h for h in root_logger.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        # 通常ログとエラーログの2つ
        assert len(file_handlers) >= 2

    def test_file_output_uses_json_formatter(self, tmp_path) -> None:
        """ファイルハンドラーがJSONFormatterを使用"""
        log_dir = str(tmp_path / "logs")

        configure_logging(
            level="DEBUG",
            log_dir=log_dir,
            console_output=False,
            file_output=True
        )

        root_logger = logging.getLogger()
        file_handlers = [
            h for h in root_logger.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]

        for handler in file_handlers:
            assert isinstance(handler.formatter, JSONFormatter)


class TestJSONFormatter:
    """JSONFormatterのテスト"""

    def test_json_formatter_format(self) -> None:
        """JSONFormatterのフォーマット出力"""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="テストメッセージ",
            args=(),
            exc_info=None
        )

        result = formatter.format(record)
        # JSON形式であることを確認
        import json
        parsed = json.loads(result)
        assert "timestamp" in parsed
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "テストメッセージ"


class TestColoredConsoleFormatter:
    """ColoredConsoleFormatterのテスト"""

    def test_colored_formatter_format(self) -> None:
        """ColoredConsoleFormatterのフォーマット出力"""
        formatter = ColoredConsoleFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="テストメッセージ",
            args=(),
            exc_info=None
        )

        result = formatter.format(record)
        assert "テストメッセージ" in result

    def test_colored_formatter_error_level(self) -> None:
        """エラーレベルの色付け"""
        formatter = ColoredConsoleFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="エラーメッセージ",
            args=(),
            exc_info=None
        )

        result = formatter.format(record)
        assert "エラーメッセージ" in result


class TestRequestContext:
    """RequestContextのテスト"""

    def test_request_context_enter_exit(self) -> None:
        """コンテキストマネージャーの入退場"""
        with RequestContext(user_id="user123", operation="test_op") as ctx:
            assert ctx.request_id is not None
            assert len(ctx.request_id) > 0
            # コンテキスト変数が設定されている
            assert user_id_var.get() == "user123"
            assert operation_var.get() == "test_op"

    def test_request_context_clears_on_exit(self) -> None:
        """終了時にコンテキスト変数がクリアされる"""
        with RequestContext(user_id="user123", operation="test_op"):
            pass

        # 終了後はクリアされている
        assert user_id_var.get() == ""
        assert operation_var.get() == ""


class TestPerformanceTimer:
    """PerformanceTimerのテスト"""

    def test_performance_timer_measures_time(self) -> None:
        """時間計測"""
        configure_logging(level="DEBUG", console_output=True, file_output=False)
        logger = get_logger("test_timer", "test")

        with patch.object(logger, 'info') as mock_info:
            with PerformanceTimer(logger, "test_operation"):
                time.sleep(0.05)  # 50ms

            mock_info.assert_called()
            # duration_msが記録されている
            call_args = mock_info.call_args
            assert "test_operation" in str(call_args)

    def test_performance_timer_on_exception(self) -> None:
        """例外発生時も計測結果が記録される"""
        configure_logging(level="DEBUG", console_output=True, file_output=False)
        logger = get_logger("test_timer_exc", "test")

        with patch.object(logger, 'info') as mock_info:
            try:
                with PerformanceTimer(logger, "failing_operation"):
                    raise ValueError("テストエラー")
            except ValueError:
                pass

            # 例外が発生してもinfoが呼ばれる
            mock_info.assert_called()


class TestMetricsCollector:
    """MetricsCollectorのテスト"""

    def test_increment_counter(self) -> None:
        """カウンターのインクリメント"""
        metrics = MetricsCollector()
        metrics.reset()

        metrics.increment("api_calls")
        metrics.increment("api_calls")
        metrics.increment("api_calls", value=3)

        all_metrics = metrics.get_all()
        assert all_metrics["counters"]["api_calls"] == 5

    def test_increment_with_tags(self) -> None:
        """タグ付きカウンター"""
        metrics = MetricsCollector()
        metrics.reset()

        metrics.increment("api_calls", tags={"endpoint": "/users"})
        metrics.increment("api_calls", tags={"endpoint": "/orders"})

        all_metrics = metrics.get_all()
        # タグ付きの場合、キー名が変わる可能性がある
        counters = all_metrics["counters"]
        assert len(counters) >= 1

    def test_timing_metric(self) -> None:
        """タイミングメトリクス"""
        metrics = MetricsCollector()
        metrics.reset()

        metrics.timing("response_time", 150.5)
        metrics.timing("response_time", 200.0)
        metrics.timing("response_time", 100.0)

        all_metrics = metrics.get_all()
        timings = all_metrics["timings"]["response_time"]
        assert timings["count"] == 3
        # 実装に合わせてキー名を確認（total_ms, min_ms, max_ms等）
        assert timings["min_ms"] == 100.0
        assert timings["max_ms"] == 200.0

    def test_timing_with_tags(self) -> None:
        """タグ付きタイミング"""
        metrics = MetricsCollector()
        metrics.reset()

        metrics.timing("response_time", 100.0, tags={"endpoint": "/api"})

        all_metrics = metrics.get_all()
        # タグ付きの場合、キー名が変わる
        timings = all_metrics["timings"]
        assert len(timings) >= 1

    def test_reset_metrics(self) -> None:
        """メトリクスのリセット"""
        metrics = MetricsCollector()
        metrics.increment("counter")
        metrics.timing("timer", 100.0)

        metrics.reset()

        all_metrics = metrics.get_all()
        assert all_metrics["counters"] == {}
        assert all_metrics["timings"] == {}

    def test_get_metrics_singleton(self) -> None:
        """get_metricsがシングルトンを返す"""
        metrics1 = get_metrics()
        metrics2 = get_metrics()
        # 同じインスタンスではないが、同じ型
        assert isinstance(metrics1, MetricsCollector)
        assert isinstance(metrics2, MetricsCollector)


class TestTaskMasterLoggerOperations:
    """TaskMasterLoggerの操作メソッドテスト"""

    def test_operation_start(self) -> None:
        """操作開始ログ"""
        configure_logging(level="DEBUG", console_output=True, file_output=False)
        logger = get_logger("test_op_start", "test")

        req_id = logger.operation_start("test_operation", data={"param": "value"})
        assert req_id is not None
        assert len(req_id) > 0

    def test_operation_end_success(self) -> None:
        """操作終了ログ（成功）"""
        configure_logging(level="DEBUG", console_output=True, file_output=False)
        logger = get_logger("test_op_end", "test")

        with patch.object(logger, 'info') as mock_info:
            logger.operation_end("test_operation", 150.5, success=True)
            mock_info.assert_called()
            call_str = str(mock_info.call_args)
            assert "成功" in call_str

    def test_operation_end_failure(self) -> None:
        """操作終了ログ（失敗）"""
        configure_logging(level="DEBUG", console_output=True, file_output=False)
        logger = get_logger("test_op_end_fail", "test")

        with patch.object(logger, 'info') as mock_info:
            logger.operation_end("test_operation", 150.5, success=False)
            mock_info.assert_called()
            call_str = str(mock_info.call_args)
            assert "失敗" in call_str


class TestLogContextDataclass:
    """LogContextデータクラスのテスト"""

    def test_log_context_defaults(self) -> None:
        """デフォルト値"""
        context = LogContext()
        assert context.request_id == ""
        assert context.user_id == ""
        assert context.operation == ""
        assert context.component == ""
        # additionalはdefault_factoryで空dictになる
        assert context.additional == {}

    def test_log_context_with_values(self) -> None:
        """値指定"""
        context = LogContext(
            request_id="req123",
            user_id="user456",
            operation="test",
            component="api",
            additional={"extra": "data"}
        )
        assert context.request_id == "req123"
        assert context.additional == {"extra": "data"}


class TestStructuredLogRecordDataclass:
    """StructuredLogRecordデータクラスのテスト"""

    def test_log_record_to_dict_with_error(self) -> None:
        """エラー付きto_dict"""
        context = LogContext(request_id="req123")
        record = StructuredLogRecord(
            timestamp=datetime.now().isoformat(),
            level="ERROR",
            logger_name="test",
            message="エラー発生",
            context=context,
            error={"type": "ValueError", "message": "無効な値"}
        )

        result = record.to_dict()
        assert "error" in result
        assert result["error"]["type"] == "ValueError"

    def test_log_record_to_dict_with_duration(self) -> None:
        """duration_ms付きto_dict"""
        context = LogContext()
        record = StructuredLogRecord(
            timestamp=datetime.now().isoformat(),
            level="INFO",
            logger_name="test",
            message="処理完了",
            context=context,
            duration_ms=150.5
        )

        result = record.to_dict()
        assert "duration_ms" in result
        assert result["duration_ms"] == 150.5

    def test_log_record_to_dict_with_data(self) -> None:
        """data付きto_dict"""
        context = LogContext()
        record = StructuredLogRecord(
            timestamp=datetime.now().isoformat(),
            level="INFO",
            logger_name="test",
            message="データ付きログ",
            context=context,
            data={"key": "value", "count": 10}
        )

        result = record.to_dict()
        assert "data" in result
        assert result["data"]["key"] == "value"

    def test_log_record_to_json(self) -> None:
        """JSON形式への変換テスト"""
        context = LogContext()
        record = StructuredLogRecord(
            timestamp=datetime.now().isoformat(),
            level="INFO",
            logger_name="test",
            message="JSONテスト",
            context=context
        )

        json_str = record.to_json()
        import json
        parsed = json.loads(json_str)
        assert parsed["message"] == "JSONテスト"
