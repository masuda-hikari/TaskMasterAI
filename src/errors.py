"""
エラーハンドリングモジュール - 統一エラー管理

カスタム例外、エラーコード、エラーレスポンス形式を定義
"""

import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from functools import wraps

logger = logging.getLogger(__name__)


class ErrorCode(Enum):
    """エラーコード定義"""
    # 認証関連 (1000-1999)
    AUTH_FAILED = "AUTH_1001"
    AUTH_TOKEN_EXPIRED = "AUTH_1002"
    AUTH_TOKEN_INVALID = "AUTH_1003"
    AUTH_CREDENTIALS_MISSING = "AUTH_1004"
    AUTH_PERMISSION_DENIED = "AUTH_1005"
    AUTH_OAUTH_FAILED = "AUTH_1006"

    # 課金関連 (2000-2999)
    BILLING_SUBSCRIPTION_NOT_FOUND = "BILL_2001"
    BILLING_USAGE_LIMIT_EXCEEDED = "BILL_2002"
    BILLING_PAYMENT_FAILED = "BILL_2003"
    BILLING_PLAN_INVALID = "BILL_2004"
    BILLING_STRIPE_ERROR = "BILL_2005"

    # メール関連 (3000-3999)
    EMAIL_FETCH_FAILED = "EMAIL_3001"
    EMAIL_PARSE_FAILED = "EMAIL_3002"
    EMAIL_SEND_FAILED = "EMAIL_3003"
    EMAIL_DRAFT_FAILED = "EMAIL_3004"
    EMAIL_GMAIL_API_ERROR = "EMAIL_3005"
    EMAIL_SUMMARIZE_FAILED = "EMAIL_3006"

    # スケジュール関連 (4000-4999)
    SCHEDULE_FETCH_FAILED = "SCHED_4001"
    SCHEDULE_CREATE_FAILED = "SCHED_4002"
    SCHEDULE_CONFLICT = "SCHED_4003"
    SCHEDULE_CALENDAR_API_ERROR = "SCHED_4004"
    SCHEDULE_NO_AVAILABLE_SLOT = "SCHED_4005"

    # LLM関連 (5000-5999)
    LLM_API_ERROR = "LLM_5001"
    LLM_RATE_LIMIT = "LLM_5002"
    LLM_RESPONSE_INVALID = "LLM_5003"
    LLM_PROVIDER_UNAVAILABLE = "LLM_5004"

    # データベース関連 (6000-6999)
    DB_CONNECTION_FAILED = "DB_6001"
    DB_QUERY_FAILED = "DB_6002"
    DB_NOT_FOUND = "DB_6003"
    DB_INTEGRITY_ERROR = "DB_6004"

    # 入力検証関連 (7000-7999)
    VALIDATION_FAILED = "VAL_7001"
    VALIDATION_REQUIRED_FIELD = "VAL_7002"
    VALIDATION_INVALID_FORMAT = "VAL_7003"
    VALIDATION_OUT_OF_RANGE = "VAL_7004"

    # システム関連 (8000-8999)
    SYSTEM_INTERNAL_ERROR = "SYS_8001"
    SYSTEM_SERVICE_UNAVAILABLE = "SYS_8002"
    SYSTEM_TIMEOUT = "SYS_8003"
    SYSTEM_CONFIGURATION_ERROR = "SYS_8004"

    # コマンド関連 (9000-9999)
    COMMAND_UNKNOWN = "CMD_9001"
    COMMAND_PARSE_FAILED = "CMD_9002"
    COMMAND_EXECUTION_FAILED = "CMD_9003"


class ErrorSeverity(Enum):
    """エラー重大度"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ErrorContext:
    """エラーコンテキスト情報"""
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    operation: Optional[str] = None
    input_data: Optional[dict] = None
    additional_info: dict = field(default_factory=dict)


@dataclass
class ErrorResponse:
    """標準化されたエラーレスポンス"""
    code: ErrorCode
    message: str
    severity: ErrorSeverity = ErrorSeverity.ERROR
    details: Optional[dict] = None
    context: Optional[ErrorContext] = None
    timestamp: datetime = field(default_factory=datetime.now)
    traceback_info: Optional[str] = None

    def to_dict(self) -> dict:
        """辞書形式に変換"""
        result = {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "severity": self.severity.value,
                "timestamp": self.timestamp.isoformat(),
            }
        }

        if self.details:
            result["error"]["details"] = self.details

        if self.context:
            result["error"]["context"] = {
                "user_id": self.context.user_id,
                "request_id": self.context.request_id,
                "operation": self.context.operation,
            }

        return result

    def to_user_message(self) -> str:
        """ユーザー向けメッセージを生成"""
        # エラーコードに基づいた日本語メッセージ
        user_messages = {
            ErrorCode.AUTH_FAILED: "認証に失敗しました。再度ログインしてください。",
            ErrorCode.AUTH_TOKEN_EXPIRED: "セッションの有効期限が切れました。再ログインしてください。",
            ErrorCode.AUTH_TOKEN_INVALID: "無効な認証情報です。",
            ErrorCode.AUTH_CREDENTIALS_MISSING: "認証情報が設定されていません。",
            ErrorCode.AUTH_PERMISSION_DENIED: "この操作を行う権限がありません。",
            ErrorCode.AUTH_OAUTH_FAILED: "外部サービスとの認証に失敗しました。",

            ErrorCode.BILLING_SUBSCRIPTION_NOT_FOUND: "サブスクリプションが見つかりません。",
            ErrorCode.BILLING_USAGE_LIMIT_EXCEEDED: "使用量の上限に達しました。プランのアップグレードをご検討ください。",
            ErrorCode.BILLING_PAYMENT_FAILED: "決済処理に失敗しました。",
            ErrorCode.BILLING_PLAN_INVALID: "指定されたプランは無効です。",
            ErrorCode.BILLING_STRIPE_ERROR: "決済システムでエラーが発生しました。",

            ErrorCode.EMAIL_FETCH_FAILED: "メールの取得に失敗しました。",
            ErrorCode.EMAIL_PARSE_FAILED: "メールの解析に失敗しました。",
            ErrorCode.EMAIL_SEND_FAILED: "メールの送信に失敗しました。",
            ErrorCode.EMAIL_DRAFT_FAILED: "下書きの作成に失敗しました。",
            ErrorCode.EMAIL_GMAIL_API_ERROR: "Gmail APIでエラーが発生しました。",
            ErrorCode.EMAIL_SUMMARIZE_FAILED: "メールの要約に失敗しました。",

            ErrorCode.SCHEDULE_FETCH_FAILED: "スケジュールの取得に失敗しました。",
            ErrorCode.SCHEDULE_CREATE_FAILED: "予定の作成に失敗しました。",
            ErrorCode.SCHEDULE_CONFLICT: "指定した時間に既存の予定があります。",
            ErrorCode.SCHEDULE_CALENDAR_API_ERROR: "カレンダーAPIでエラーが発生しました。",
            ErrorCode.SCHEDULE_NO_AVAILABLE_SLOT: "空き時間が見つかりませんでした。",

            ErrorCode.LLM_API_ERROR: "AI処理でエラーが発生しました。",
            ErrorCode.LLM_RATE_LIMIT: "APIの利用制限に達しました。しばらくしてからお試しください。",
            ErrorCode.LLM_RESPONSE_INVALID: "AI応答の処理に失敗しました。",
            ErrorCode.LLM_PROVIDER_UNAVAILABLE: "AI処理サービスが利用できません。",

            ErrorCode.DB_CONNECTION_FAILED: "データベース接続に失敗しました。",
            ErrorCode.DB_QUERY_FAILED: "データベース処理に失敗しました。",
            ErrorCode.DB_NOT_FOUND: "データが見つかりませんでした。",
            ErrorCode.DB_INTEGRITY_ERROR: "データ整合性エラーが発生しました。",

            ErrorCode.VALIDATION_FAILED: "入力内容に問題があります。",
            ErrorCode.VALIDATION_REQUIRED_FIELD: "必須項目が入力されていません。",
            ErrorCode.VALIDATION_INVALID_FORMAT: "入力形式が正しくありません。",
            ErrorCode.VALIDATION_OUT_OF_RANGE: "入力値が範囲外です。",

            ErrorCode.SYSTEM_INTERNAL_ERROR: "システムエラーが発生しました。",
            ErrorCode.SYSTEM_SERVICE_UNAVAILABLE: "サービスが一時的に利用できません。",
            ErrorCode.SYSTEM_TIMEOUT: "処理がタイムアウトしました。",
            ErrorCode.SYSTEM_CONFIGURATION_ERROR: "システム設定にエラーがあります。",

            ErrorCode.COMMAND_UNKNOWN: "不明なコマンドです。",
            ErrorCode.COMMAND_PARSE_FAILED: "コマンドの解析に失敗しました。",
            ErrorCode.COMMAND_EXECUTION_FAILED: "コマンドの実行に失敗しました。",
        }

        return user_messages.get(self.code, self.message)


class TaskMasterError(Exception):
    """TaskMasterAI基底例外クラス"""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        details: Optional[dict] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.severity = severity
        self.details = details or {}
        self.context = context
        self.cause = cause
        self.timestamp = datetime.now()

    def to_response(self) -> ErrorResponse:
        """ErrorResponseに変換"""
        tb = None
        if self.cause:
            tb = traceback.format_exception(type(self.cause), self.cause, self.cause.__traceback__)
            tb = "".join(tb)

        return ErrorResponse(
            code=self.code,
            message=self.message,
            severity=self.severity,
            details=self.details,
            context=self.context,
            timestamp=self.timestamp,
            traceback_info=tb
        )

    def log(self) -> None:
        """エラーをログに記録"""
        log_method = {
            ErrorSeverity.DEBUG: logger.debug,
            ErrorSeverity.INFO: logger.info,
            ErrorSeverity.WARNING: logger.warning,
            ErrorSeverity.ERROR: logger.error,
            ErrorSeverity.CRITICAL: logger.critical,
        }.get(self.severity, logger.error)

        log_message = f"[{self.code.value}] {self.message}"
        if self.details:
            log_message += f" | details={self.details}"
        if self.context:
            log_message += f" | user={self.context.user_id} op={self.context.operation}"

        log_method(log_message, exc_info=self.cause)


# 特定ドメイン用の例外クラス
class AuthError(TaskMasterError):
    """認証関連エラー"""

    def __init__(self, code: ErrorCode, message: str, **kwargs):
        super().__init__(code, message, **kwargs)


class BillingError(TaskMasterError):
    """課金関連エラー"""

    def __init__(self, code: ErrorCode, message: str, **kwargs):
        super().__init__(code, message, **kwargs)


class EmailError(TaskMasterError):
    """メール関連エラー"""

    def __init__(self, code: ErrorCode, message: str, **kwargs):
        super().__init__(code, message, **kwargs)


class ScheduleError(TaskMasterError):
    """スケジュール関連エラー"""

    def __init__(self, code: ErrorCode, message: str, **kwargs):
        super().__init__(code, message, **kwargs)


class LLMError(TaskMasterError):
    """LLM関連エラー"""

    def __init__(self, code: ErrorCode, message: str, **kwargs):
        super().__init__(code, message, **kwargs)


class DatabaseError(TaskMasterError):
    """データベース関連エラー"""

    def __init__(self, code: ErrorCode, message: str, **kwargs):
        super().__init__(code, message, **kwargs)


class ValidationError(TaskMasterError):
    """入力検証関連エラー"""

    def __init__(self, code: ErrorCode, message: str, **kwargs):
        if "severity" not in kwargs:
            kwargs["severity"] = ErrorSeverity.WARNING
        super().__init__(code, message, **kwargs)


class CommandError(TaskMasterError):
    """コマンド関連エラー"""

    def __init__(self, code: ErrorCode, message: str, **kwargs):
        super().__init__(code, message, **kwargs)


def handle_errors(
    default_code: ErrorCode = ErrorCode.SYSTEM_INTERNAL_ERROR,
    log_errors: bool = True,
    reraise: bool = False
):
    """
    エラーハンドリングデコレータ

    Args:
        default_code: TaskMasterError以外の例外に使用するデフォルトエラーコード
        log_errors: エラーをログに記録するか
        reraise: TaskMasterErrorとして再スローするか

    Usage:
        @handle_errors(default_code=ErrorCode.EMAIL_FETCH_FAILED)
        def fetch_emails():
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except TaskMasterError as e:
                if log_errors:
                    e.log()
                if reraise:
                    raise
                return e.to_response()
            except Exception as e:
                error = TaskMasterError(
                    code=default_code,
                    message=str(e),
                    cause=e
                )
                if log_errors:
                    error.log()
                if reraise:
                    raise error from e
                return error.to_response()
        return wrapper
    return decorator


def handle_errors_async(
    default_code: ErrorCode = ErrorCode.SYSTEM_INTERNAL_ERROR,
    log_errors: bool = True,
    reraise: bool = False
):
    """非同期関数用のエラーハンドリングデコレータ"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except TaskMasterError as e:
                if log_errors:
                    e.log()
                if reraise:
                    raise
                return e.to_response()
            except Exception as e:
                error = TaskMasterError(
                    code=default_code,
                    message=str(e),
                    cause=e
                )
                if log_errors:
                    error.log()
                if reraise:
                    raise error from e
                return error.to_response()
        return wrapper
    return decorator


class ErrorCollector:
    """複数エラーの収集・管理クラス"""

    def __init__(self):
        self._errors: list[TaskMasterError] = []

    def add(self, error: TaskMasterError) -> None:
        """エラーを追加"""
        self._errors.append(error)

    def add_if_error(self, result: Any) -> bool:
        """結果がErrorResponseならエラーとして追加"""
        if isinstance(result, ErrorResponse):
            self._errors.append(TaskMasterError(
                code=result.code,
                message=result.message,
                severity=result.severity
            ))
            return True
        return False

    def has_errors(self) -> bool:
        """エラーがあるか"""
        return len(self._errors) > 0

    def has_critical(self) -> bool:
        """重大エラーがあるか"""
        return any(e.severity == ErrorSeverity.CRITICAL for e in self._errors)

    def get_errors(self) -> list[TaskMasterError]:
        """全エラーを取得"""
        return self._errors.copy()

    def get_first_error(self) -> Optional[TaskMasterError]:
        """最初のエラーを取得"""
        return self._errors[0] if self._errors else None

    def clear(self) -> None:
        """エラーをクリア"""
        self._errors.clear()

    def log_all(self) -> None:
        """全エラーをログに記録"""
        for error in self._errors:
            error.log()

    def to_responses(self) -> list[ErrorResponse]:
        """全エラーをErrorResponse形式で取得"""
        return [e.to_response() for e in self._errors]


if __name__ == "__main__":
    # テスト実行
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    print("=== エラーハンドリングテスト ===")

    # 基本的なエラー作成
    error = TaskMasterError(
        code=ErrorCode.AUTH_FAILED,
        message="認証に失敗しました",
        context=ErrorContext(user_id="test_user", operation="login")
    )
    error.log()

    response = error.to_response()
    print(f"ErrorResponse: {response.to_dict()}")
    print(f"ユーザーメッセージ: {response.to_user_message()}")

    # デコレータテスト
    @handle_errors(default_code=ErrorCode.EMAIL_FETCH_FAILED)
    def test_function():
        raise ValueError("テストエラー")

    result = test_function()
    print(f"デコレータ結果: {result.to_dict() if isinstance(result, ErrorResponse) else result}")
