"""
エラーハンドリングモジュールのテスト
"""

import pytest
import logging
from datetime import datetime

from src.errors import (
    ErrorCode,
    ErrorSeverity,
    ErrorContext,
    ErrorResponse,
    TaskMasterError,
    AuthError,
    BillingError,
    EmailError,
    ScheduleError,
    LLMError,
    DatabaseError,
    ValidationError,
    CommandError,
    handle_errors,
    ErrorCollector,
)


class TestErrorCode:
    """ErrorCodeのテスト"""

    def test_auth_error_codes(self):
        """認証エラーコードのテスト"""
        assert ErrorCode.AUTH_FAILED.value == "AUTH_1001"
        assert ErrorCode.AUTH_TOKEN_EXPIRED.value == "AUTH_1002"
        assert ErrorCode.AUTH_TOKEN_INVALID.value == "AUTH_1003"

    def test_billing_error_codes(self):
        """課金エラーコードのテスト"""
        assert ErrorCode.BILLING_SUBSCRIPTION_NOT_FOUND.value == "BILL_2001"
        assert ErrorCode.BILLING_USAGE_LIMIT_EXCEEDED.value == "BILL_2002"

    def test_email_error_codes(self):
        """メールエラーコードのテスト"""
        assert ErrorCode.EMAIL_FETCH_FAILED.value == "EMAIL_3001"
        assert ErrorCode.EMAIL_SUMMARIZE_FAILED.value == "EMAIL_3006"


class TestErrorContext:
    """ErrorContextのテスト"""

    def test_default_context(self):
        """デフォルトコンテキスト"""
        context = ErrorContext()
        assert context.user_id is None
        assert context.request_id is None
        assert context.operation is None

    def test_context_with_values(self):
        """値付きコンテキスト"""
        context = ErrorContext(
            user_id="user123",
            request_id="req456",
            operation="fetch_emails"
        )
        assert context.user_id == "user123"
        assert context.request_id == "req456"
        assert context.operation == "fetch_emails"

    def test_context_additional_info(self):
        """追加情報付きコンテキスト"""
        context = ErrorContext(
            additional_info={"key": "value"}
        )
        assert context.additional_info["key"] == "value"


class TestErrorResponse:
    """ErrorResponseのテスト"""

    def test_basic_response(self):
        """基本レスポンス"""
        response = ErrorResponse(
            code=ErrorCode.AUTH_FAILED,
            message="認証に失敗しました"
        )
        assert response.code == ErrorCode.AUTH_FAILED
        assert response.message == "認証に失敗しました"
        assert response.severity == ErrorSeverity.ERROR

    def test_to_dict(self):
        """辞書変換"""
        response = ErrorResponse(
            code=ErrorCode.AUTH_FAILED,
            message="認証に失敗しました",
            details={"reason": "invalid_password"}
        )
        result = response.to_dict()
        assert result["error"]["code"] == "AUTH_1001"
        assert result["error"]["message"] == "認証に失敗しました"
        assert result["error"]["details"]["reason"] == "invalid_password"

    def test_to_dict_with_context(self):
        """コンテキスト付き辞書変換"""
        context = ErrorContext(user_id="user123", operation="login")
        response = ErrorResponse(
            code=ErrorCode.AUTH_FAILED,
            message="認証に失敗しました",
            context=context
        )
        result = response.to_dict()
        assert result["error"]["context"]["user_id"] == "user123"
        assert result["error"]["context"]["operation"] == "login"

    def test_to_user_message(self):
        """ユーザーメッセージ生成"""
        response = ErrorResponse(
            code=ErrorCode.AUTH_TOKEN_EXPIRED,
            message="Token expired"
        )
        user_msg = response.to_user_message()
        assert "セッション" in user_msg or "再ログイン" in user_msg

    def test_to_user_message_billing(self):
        """課金エラーのユーザーメッセージ"""
        response = ErrorResponse(
            code=ErrorCode.BILLING_USAGE_LIMIT_EXCEEDED,
            message="Usage limit exceeded"
        )
        user_msg = response.to_user_message()
        assert "上限" in user_msg or "アップグレード" in user_msg


class TestTaskMasterError:
    """TaskMasterErrorのテスト"""

    def test_basic_error(self):
        """基本エラー"""
        error = TaskMasterError(
            code=ErrorCode.AUTH_FAILED,
            message="認証に失敗しました"
        )
        assert error.code == ErrorCode.AUTH_FAILED
        assert error.message == "認証に失敗しました"
        assert str(error) == "認証に失敗しました"

    def test_error_with_cause(self):
        """原因例外付きエラー"""
        cause = ValueError("Original error")
        error = TaskMasterError(
            code=ErrorCode.SYSTEM_INTERNAL_ERROR,
            message="システムエラー",
            cause=cause
        )
        assert error.cause is cause

    def test_error_to_response(self):
        """ErrorResponseへの変換"""
        error = TaskMasterError(
            code=ErrorCode.AUTH_FAILED,
            message="認証に失敗しました",
            severity=ErrorSeverity.WARNING,
            details={"attempt": 3}
        )
        response = error.to_response()
        assert response.code == ErrorCode.AUTH_FAILED
        assert response.severity == ErrorSeverity.WARNING
        assert response.details["attempt"] == 3

    def test_error_timestamp(self):
        """タイムスタンプ"""
        error = TaskMasterError(
            code=ErrorCode.AUTH_FAILED,
            message="認証に失敗しました"
        )
        assert isinstance(error.timestamp, datetime)


class TestSpecificErrors:
    """特定ドメインエラーのテスト"""

    def test_auth_error(self):
        """AuthError"""
        error = AuthError(
            code=ErrorCode.AUTH_TOKEN_INVALID,
            message="無効なトークン"
        )
        assert isinstance(error, TaskMasterError)
        assert error.code == ErrorCode.AUTH_TOKEN_INVALID

    def test_billing_error(self):
        """BillingError"""
        error = BillingError(
            code=ErrorCode.BILLING_PAYMENT_FAILED,
            message="決済失敗"
        )
        assert isinstance(error, TaskMasterError)

    def test_email_error(self):
        """EmailError"""
        error = EmailError(
            code=ErrorCode.EMAIL_FETCH_FAILED,
            message="メール取得失敗"
        )
        assert isinstance(error, TaskMasterError)

    def test_schedule_error(self):
        """ScheduleError"""
        error = ScheduleError(
            code=ErrorCode.SCHEDULE_CONFLICT,
            message="予定重複"
        )
        assert isinstance(error, TaskMasterError)

    def test_llm_error(self):
        """LLMError"""
        error = LLMError(
            code=ErrorCode.LLM_RATE_LIMIT,
            message="レート制限"
        )
        assert isinstance(error, TaskMasterError)

    def test_database_error(self):
        """DatabaseError"""
        error = DatabaseError(
            code=ErrorCode.DB_CONNECTION_FAILED,
            message="接続失敗"
        )
        assert isinstance(error, TaskMasterError)

    def test_validation_error(self):
        """ValidationError（デフォルトでWARNING）"""
        error = ValidationError(
            code=ErrorCode.VALIDATION_REQUIRED_FIELD,
            message="必須項目"
        )
        assert error.severity == ErrorSeverity.WARNING

    def test_command_error(self):
        """CommandError"""
        error = CommandError(
            code=ErrorCode.COMMAND_UNKNOWN,
            message="不明なコマンド"
        )
        assert isinstance(error, TaskMasterError)


class TestHandleErrorsDecorator:
    """handle_errorsデコレータのテスト"""

    def test_successful_function(self):
        """正常終了関数"""
        @handle_errors()
        def success_func():
            return "success"

        result = success_func()
        assert result == "success"

    def test_taskmaster_error_handling(self):
        """TaskMasterErrorの処理"""
        @handle_errors()
        def error_func():
            raise TaskMasterError(
                code=ErrorCode.AUTH_FAILED,
                message="認証失敗"
            )

        result = error_func()
        assert isinstance(result, ErrorResponse)
        assert result.code == ErrorCode.AUTH_FAILED

    def test_generic_exception_handling(self):
        """一般例外の処理"""
        @handle_errors(default_code=ErrorCode.EMAIL_FETCH_FAILED)
        def error_func():
            raise ValueError("Generic error")

        result = error_func()
        assert isinstance(result, ErrorResponse)
        assert result.code == ErrorCode.EMAIL_FETCH_FAILED

    def test_reraise_option(self):
        """reraiseオプション"""
        @handle_errors(reraise=True)
        def error_func():
            raise TaskMasterError(
                code=ErrorCode.AUTH_FAILED,
                message="認証失敗"
            )

        with pytest.raises(TaskMasterError):
            error_func()


class TestErrorCollector:
    """ErrorCollectorのテスト"""

    def test_add_error(self):
        """エラー追加"""
        collector = ErrorCollector()
        error = TaskMasterError(
            code=ErrorCode.AUTH_FAILED,
            message="認証失敗"
        )
        collector.add(error)
        assert collector.has_errors()
        assert len(collector.get_errors()) == 1

    def test_no_errors(self):
        """エラーなし"""
        collector = ErrorCollector()
        assert not collector.has_errors()
        assert collector.get_first_error() is None

    def test_has_critical(self):
        """重大エラー検出"""
        collector = ErrorCollector()
        collector.add(TaskMasterError(
            code=ErrorCode.AUTH_FAILED,
            message="認証失敗",
            severity=ErrorSeverity.WARNING
        ))
        assert not collector.has_critical()

        collector.add(TaskMasterError(
            code=ErrorCode.SYSTEM_INTERNAL_ERROR,
            message="システムエラー",
            severity=ErrorSeverity.CRITICAL
        ))
        assert collector.has_critical()

    def test_get_first_error(self):
        """最初のエラー取得"""
        collector = ErrorCollector()
        error1 = TaskMasterError(code=ErrorCode.AUTH_FAILED, message="エラー1")
        error2 = TaskMasterError(code=ErrorCode.BILLING_PAYMENT_FAILED, message="エラー2")
        collector.add(error1)
        collector.add(error2)
        assert collector.get_first_error() is error1

    def test_clear(self):
        """エラークリア"""
        collector = ErrorCollector()
        collector.add(TaskMasterError(
            code=ErrorCode.AUTH_FAILED,
            message="認証失敗"
        ))
        assert collector.has_errors()
        collector.clear()
        assert not collector.has_errors()

    def test_to_responses(self):
        """ErrorResponse変換"""
        collector = ErrorCollector()
        collector.add(TaskMasterError(
            code=ErrorCode.AUTH_FAILED,
            message="認証失敗"
        ))
        collector.add(TaskMasterError(
            code=ErrorCode.BILLING_PAYMENT_FAILED,
            message="決済失敗"
        ))
        responses = collector.to_responses()
        assert len(responses) == 2
        assert all(isinstance(r, ErrorResponse) for r in responses)

    def test_add_if_error(self):
        """ErrorResponse判定追加"""
        collector = ErrorCollector()

        # ErrorResponseの場合
        response = ErrorResponse(code=ErrorCode.AUTH_FAILED, message="エラー")
        assert collector.add_if_error(response) is True
        assert collector.has_errors()

        # 通常の値の場合
        collector.clear()
        assert collector.add_if_error("success") is False
        assert not collector.has_errors()


class TestErrorSeverity:
    """ErrorSeverityのテスト"""

    def test_severity_values(self):
        """重大度の値"""
        assert ErrorSeverity.DEBUG.value == "debug"
        assert ErrorSeverity.INFO.value == "info"
        assert ErrorSeverity.WARNING.value == "warning"
        assert ErrorSeverity.ERROR.value == "error"
        assert ErrorSeverity.CRITICAL.value == "critical"


class TestErrorLogging:
    """エラーロギングのテスト"""

    def test_error_log(self, caplog):
        """ログ出力"""
        with caplog.at_level(logging.ERROR):
            error = TaskMasterError(
                code=ErrorCode.AUTH_FAILED,
                message="認証に失敗しました",
                context=ErrorContext(user_id="test_user", operation="login")
            )
            error.log()

        assert "AUTH_1001" in caplog.text
        assert "認証に失敗しました" in caplog.text

    def test_warning_log(self, caplog):
        """警告ログ出力"""
        with caplog.at_level(logging.WARNING):
            error = TaskMasterError(
                code=ErrorCode.VALIDATION_FAILED,
                message="検証失敗",
                severity=ErrorSeverity.WARNING
            )
            error.log()

        assert "VAL_7001" in caplog.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
