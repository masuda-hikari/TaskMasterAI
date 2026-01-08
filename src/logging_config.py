"""
ロギング設定モジュール - 構造化ロギングシステム

JSON形式のログ出力、コンテキスト追跡、メトリクス収集を提供
"""

import json
import logging
import logging.handlers
import os
import sys
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# コンテキスト変数（リクエスト追跡用）
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")
operation_var: ContextVar[str] = ContextVar("operation", default="")


class LogLevel(Enum):
    """ログレベル"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class LogContext:
    """ログコンテキスト情報"""
    request_id: str = ""
    user_id: str = ""
    operation: str = ""
    component: str = ""
    additional: dict = field(default_factory=dict)

    @classmethod
    def from_context_vars(cls, component: str = "") -> "LogContext":
        """コンテキスト変数から生成"""
        return cls(
            request_id=request_id_var.get(),
            user_id=user_id_var.get(),
            operation=operation_var.get(),
            component=component
        )


@dataclass
class StructuredLogRecord:
    """構造化ログレコード"""
    timestamp: str
    level: str
    message: str
    logger_name: str
    context: LogContext
    data: Optional[dict] = None
    error: Optional[dict] = None
    duration_ms: Optional[float] = None

    def to_dict(self) -> dict:
        """辞書形式に変換"""
        result = {
            "timestamp": self.timestamp,
            "level": self.level,
            "message": self.message,
            "logger": self.logger_name,
            "context": {
                "request_id": self.context.request_id,
                "user_id": self.context.user_id,
                "operation": self.context.operation,
                "component": self.context.component,
            }
        }

        if self.context.additional:
            result["context"]["additional"] = self.context.additional

        if self.data:
            result["data"] = self.data

        if self.error:
            result["error"] = self.error

        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms

        return result

    def to_json(self) -> str:
        """JSON形式に変換"""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


class JSONFormatter(logging.Formatter):
    """JSON形式ログフォーマッタ"""

    def format(self, record: logging.LogRecord) -> str:
        # コンテキスト取得
        context = LogContext.from_context_vars(
            component=getattr(record, "component", record.name)
        )

        # 追加データ取得
        data = getattr(record, "data", None)
        duration_ms = getattr(record, "duration_ms", None)

        # エラー情報
        error = None
        if record.exc_info:
            error = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info) if record.exc_info[2] else None
            }

        log_record = StructuredLogRecord(
            timestamp=datetime.fromtimestamp(record.created).isoformat(),
            level=record.levelname,
            message=record.getMessage(),
            logger_name=record.name,
            context=context,
            data=data,
            error=error,
            duration_ms=duration_ms
        )

        return log_record.to_json()


class ColoredConsoleFormatter(logging.Formatter):
    """コンソール用カラーフォーマッタ"""

    COLORS = {
        "DEBUG": "\033[36m",     # シアン
        "INFO": "\033[32m",      # 緑
        "WARNING": "\033[33m",   # 黄
        "ERROR": "\033[31m",     # 赤
        "CRITICAL": "\033[35m",  # マゼンタ
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)

        # コンテキスト情報
        request_id = request_id_var.get()
        user_id = user_id_var.get()
        operation = operation_var.get()

        context_parts = []
        if request_id:
            context_parts.append(f"req={request_id[:8]}")
        if user_id:
            context_parts.append(f"user={user_id[:8]}")
        if operation:
            context_parts.append(f"op={operation}")

        context_str = f" [{', '.join(context_parts)}]" if context_parts else ""

        # タイムスタンプ
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # フォーマット
        formatted = (
            f"{timestamp} "
            f"{color}{record.levelname:8}{self.RESET} "
            f"[{record.name}]{context_str} "
            f"{record.getMessage()}"
        )

        # 追加データ
        data = getattr(record, "data", None)
        if data:
            formatted += f" | data={json.dumps(data, ensure_ascii=False, default=str)}"

        duration_ms = getattr(record, "duration_ms", None)
        if duration_ms is not None:
            formatted += f" | duration={duration_ms:.2f}ms"

        # 例外情報
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)

        return formatted


class TaskMasterLogger:
    """TaskMasterAI用ロガー"""

    def __init__(self, name: str, component: str = ""):
        self._logger = logging.getLogger(name)
        self._component = component

    def _log(
        self,
        level: int,
        message: str,
        data: Optional[dict] = None,
        duration_ms: Optional[float] = None,
        exc_info: bool = False
    ) -> None:
        """ログ出力"""
        extra = {
            "component": self._component,
            "data": data,
            "duration_ms": duration_ms
        }
        self._logger.log(level, message, extra=extra, exc_info=exc_info)

    def debug(self, message: str, data: Optional[dict] = None) -> None:
        """デバッグログ"""
        self._log(logging.DEBUG, message, data)

    def info(self, message: str, data: Optional[dict] = None, duration_ms: Optional[float] = None) -> None:
        """情報ログ"""
        self._log(logging.INFO, message, data, duration_ms)

    def warning(self, message: str, data: Optional[dict] = None) -> None:
        """警告ログ"""
        self._log(logging.WARNING, message, data)

    def error(self, message: str, data: Optional[dict] = None, exc_info: bool = True) -> None:
        """エラーログ"""
        self._log(logging.ERROR, message, data, exc_info=exc_info)

    def critical(self, message: str, data: Optional[dict] = None, exc_info: bool = True) -> None:
        """致命的エラーログ"""
        self._log(logging.CRITICAL, message, data, exc_info=exc_info)

    def operation_start(self, operation: str, data: Optional[dict] = None) -> str:
        """操作開始ログ（リクエストIDを返す）"""
        req_id = str(uuid.uuid4())
        request_id_var.set(req_id)
        operation_var.set(operation)
        self.info(f"操作開始: {operation}", data)
        return req_id

    def operation_end(self, operation: str, duration_ms: float, success: bool = True, data: Optional[dict] = None) -> None:
        """操作終了ログ"""
        status = "成功" if success else "失敗"
        self.info(f"操作終了: {operation} ({status})", data, duration_ms)
        operation_var.set("")


def get_logger(name: str, component: str = "") -> TaskMasterLogger:
    """TaskMasterLogger取得"""
    return TaskMasterLogger(name, component)


class RequestContext:
    """リクエストコンテキストマネージャ"""

    def __init__(
        self,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        operation: Optional[str] = None
    ):
        self._request_id = request_id or str(uuid.uuid4())
        self._user_id = user_id or ""
        self._operation = operation or ""
        self._tokens: list = []

    def __enter__(self) -> "RequestContext":
        self._tokens.append(request_id_var.set(self._request_id))
        self._tokens.append(user_id_var.set(self._user_id))
        self._tokens.append(operation_var.set(self._operation))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        for token in self._tokens:
            # ContextVarのresetは存在しないため、空文字列を設定
            pass
        request_id_var.set("")
        user_id_var.set("")
        operation_var.set("")

    @property
    def request_id(self) -> str:
        return self._request_id


def set_user_context(user_id: str) -> None:
    """ユーザーコンテキストを設定"""
    user_id_var.set(user_id)


def set_operation_context(operation: str) -> None:
    """操作コンテキストを設定"""
    operation_var.set(operation)


def configure_logging(
    level: str = "INFO",
    log_dir: Optional[str] = None,
    json_format: bool = True,
    console_output: bool = True,
    file_output: bool = True,
    max_file_size_mb: int = 10,
    backup_count: int = 5
) -> None:
    """
    ロギング設定を構成

    Args:
        level: ログレベル
        log_dir: ログディレクトリ
        json_format: JSON形式で出力するか
        console_output: コンソール出力するか
        file_output: ファイル出力するか
        max_file_size_mb: 最大ファイルサイズ（MB）
        backup_count: バックアップファイル数
    """
    # 環境変数からのオーバーライド
    level = os.getenv("LOG_LEVEL", level).upper()
    log_dir = os.getenv("LOG_DIR", log_dir)

    # ルートロガー設定
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level, logging.INFO))

    # 既存ハンドラーをクリア
    root_logger.handlers.clear()

    # コンソールハンドラー
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)

        if json_format and os.getenv("ENVIRONMENT", "development") == "production":
            console_handler.setFormatter(JSONFormatter())
        else:
            console_handler.setFormatter(ColoredConsoleFormatter())

        root_logger.addHandler(console_handler)

    # ファイルハンドラー
    if file_output and log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # 通常ログ
        file_handler = logging.handlers.RotatingFileHandler(
            log_path / "taskmaster.log",
            maxBytes=max_file_size_mb * 1024 * 1024,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)

        # エラーログ（別ファイル）
        error_handler = logging.handlers.RotatingFileHandler(
            log_path / "taskmaster_error.log",
            maxBytes=max_file_size_mb * 1024 * 1024,
            backupCount=backup_count,
            encoding="utf-8"
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(error_handler)

    # サードパーティライブラリのログレベル調整
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


class PerformanceTimer:
    """パフォーマンス計測用タイマー"""

    def __init__(self, logger: TaskMasterLogger, operation: str):
        self._logger = logger
        self._operation = operation
        self._start_time: Optional[float] = None

    def __enter__(self) -> "PerformanceTimer":
        import time
        self._start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        import time
        if self._start_time:
            duration_ms = (time.perf_counter() - self._start_time) * 1000
            success = exc_type is None
            self._logger.operation_end(self._operation, duration_ms, success)


class MetricsCollector:
    """メトリクス収集クラス"""

    _instance: Optional["MetricsCollector"] = None

    def __new__(cls) -> "MetricsCollector":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._metrics = {}
            cls._instance._counters = {}
        return cls._instance

    def increment(self, name: str, value: int = 1, tags: Optional[dict] = None) -> None:
        """カウンターをインクリメント"""
        key = self._make_key(name, tags)
        self._counters[key] = self._counters.get(key, 0) + value

    def gauge(self, name: str, value: float, tags: Optional[dict] = None) -> None:
        """ゲージ値を設定"""
        key = self._make_key(name, tags)
        self._metrics[key] = value

    def timing(self, name: str, duration_ms: float, tags: Optional[dict] = None) -> None:
        """タイミングを記録"""
        key = self._make_key(name, tags)
        if key not in self._metrics:
            self._metrics[key] = {"count": 0, "total_ms": 0, "min_ms": float("inf"), "max_ms": 0}

        metric = self._metrics[key]
        metric["count"] += 1
        metric["total_ms"] += duration_ms
        metric["min_ms"] = min(metric["min_ms"], duration_ms)
        metric["max_ms"] = max(metric["max_ms"], duration_ms)

    def _make_key(self, name: str, tags: Optional[dict]) -> str:
        """メトリクスキーを生成"""
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}[{tag_str}]"

    def get_all(self) -> dict:
        """全メトリクスを取得"""
        return {
            "counters": self._counters.copy(),
            "gauges": {k: v for k, v in self._metrics.items() if not isinstance(v, dict)},
            "timings": {k: v for k, v in self._metrics.items() if isinstance(v, dict)}
        }

    def reset(self) -> None:
        """メトリクスをリセット"""
        self._metrics.clear()
        self._counters.clear()


def get_metrics() -> MetricsCollector:
    """MetricsCollector取得"""
    return MetricsCollector()


if __name__ == "__main__":
    # テスト実行
    configure_logging(
        level="DEBUG",
        log_dir="logs",
        json_format=False,
        console_output=True,
        file_output=False
    )

    print("=== ロギングシステムテスト ===\n")

    logger = get_logger(__name__, "test")

    # 基本ログ
    logger.debug("デバッグメッセージ")
    logger.info("情報メッセージ", data={"key": "value"})
    logger.warning("警告メッセージ")

    # コンテキスト付きログ
    with RequestContext(user_id="test_user", operation="test_operation") as ctx:
        logger.info(f"コンテキスト付きログ request_id={ctx.request_id}")

    # パフォーマンス計測
    import time
    with PerformanceTimer(logger, "test_operation"):
        time.sleep(0.1)

    # メトリクス
    metrics = get_metrics()
    metrics.increment("api_calls", tags={"endpoint": "/test"})
    metrics.timing("response_time", 150.5, tags={"endpoint": "/test"})
    print(f"\nメトリクス: {metrics.get_all()}")
