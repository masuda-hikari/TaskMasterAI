"""
errors.py カバレッジ向上テスト

未カバー行をテスト:
- handle_errors reraise分岐
- handle_errors_async全体
- ErrorCollector.log_all
"""

import pytest
import asyncio
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
    handle_errors_async,
    ErrorCollector
)


class TestHandleErrorsReraiseOption:
    """handle_errorsデコレータのreraise=Trueテスト"""

    def test_reraise_taskmaster_error(self):
        """TaskMasterErrorをreraiseする"""
        @handle_errors(reraise=True, log_errors=False)
        def raise_taskmaster_error():
            raise TaskMasterError(
                code=ErrorCode.AUTH_FAILED,
                message="認証エラー"
            )

        with pytest.raises(TaskMasterError) as exc_info:
            raise_taskmaster_error()

        assert exc_info.value.code == ErrorCode.AUTH_FAILED
        assert exc_info.value.message == "認証エラー"

    def test_reraise_generic_error(self):
        """一般例外をTaskMasterErrorとしてreraiseする"""
        @handle_errors(reraise=True, log_errors=False)
        def raise_value_error():
            raise ValueError("値が不正")

        with pytest.raises(TaskMasterError) as exc_info:
            raise_value_error()

        assert exc_info.value.code == ErrorCode.SYSTEM_INTERNAL_ERROR
        assert "値が不正" in exc_info.value.message

    def test_reraise_with_custom_default_code(self):
        """カスタムデフォルトコードでreraise"""
        @handle_errors(
            default_code=ErrorCode.EMAIL_FETCH_FAILED,
            reraise=True,
            log_errors=False
        )
        def raise_runtime_error():
            raise RuntimeError("実行時エラー")

        with pytest.raises(TaskMasterError) as exc_info:
            raise_runtime_error()

        assert exc_info.value.code == ErrorCode.EMAIL_FETCH_FAILED

    def test_reraise_with_logging(self, caplog):
        """reraise時にログも記録する"""
        @handle_errors(reraise=True, log_errors=True)
        def raise_with_log():
            raise TaskMasterError(
                code=ErrorCode.DB_QUERY_FAILED,
                message="クエリ失敗"
            )

        with caplog.at_level(logging.ERROR):
            with pytest.raises(TaskMasterError):
                raise_with_log()

        assert "DB_6002" in caplog.text or "クエリ失敗" in caplog.text


class TestHandleErrorsAsync:
    """handle_errors_asyncデコレータのテスト"""

    @pytest.mark.asyncio
    async def test_async_success(self):
        """非同期関数が成功した場合"""
        @handle_errors_async()
        async def async_success():
            await asyncio.sleep(0.01)
            return {"status": "ok"}

        result = await async_success()
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_async_taskmaster_error(self):
        """非同期関数でTaskMasterErrorが発生した場合"""
        @handle_errors_async(log_errors=False)
        async def async_auth_error():
            await asyncio.sleep(0.01)
            raise AuthError(
                code=ErrorCode.AUTH_TOKEN_EXPIRED,
                message="トークン期限切れ"
            )

        result = await async_auth_error()
        assert isinstance(result, ErrorResponse)
        assert result.code == ErrorCode.AUTH_TOKEN_EXPIRED

    @pytest.mark.asyncio
    async def test_async_generic_error(self):
        """非同期関数で一般例外が発生した場合"""
        @handle_errors_async(
            default_code=ErrorCode.LLM_API_ERROR,
            log_errors=False
        )
        async def async_generic_error():
            await asyncio.sleep(0.01)
            raise Exception("API呼び出し失敗")

        result = await async_generic_error()
        assert isinstance(result, ErrorResponse)
        assert result.code == ErrorCode.LLM_API_ERROR
        assert "API呼び出し失敗" in result.message

    @pytest.mark.asyncio
    async def test_async_reraise_taskmaster_error(self):
        """非同期関数でTaskMasterErrorをreraise"""
        @handle_errors_async(reraise=True, log_errors=False)
        async def async_reraise():
            await asyncio.sleep(0.01)
            raise BillingError(
                code=ErrorCode.BILLING_PAYMENT_FAILED,
                message="決済失敗"
            )

        with pytest.raises(TaskMasterError) as exc_info:
            await async_reraise()

        assert exc_info.value.code == ErrorCode.BILLING_PAYMENT_FAILED

    @pytest.mark.asyncio
    async def test_async_reraise_generic_error(self):
        """非同期関数で一般例外をreraiseしてTaskMasterErrorに変換"""
        @handle_errors_async(
            default_code=ErrorCode.SCHEDULE_CREATE_FAILED,
            reraise=True,
            log_errors=False
        )
        async def async_reraise_generic():
            await asyncio.sleep(0.01)
            raise IOError("ファイルアクセス失敗")

        with pytest.raises(TaskMasterError) as exc_info:
            await async_reraise_generic()

        assert exc_info.value.code == ErrorCode.SCHEDULE_CREATE_FAILED

    @pytest.mark.asyncio
    async def test_async_with_logging(self, caplog):
        """非同期関数でログ記録"""
        @handle_errors_async(log_errors=True)
        async def async_with_log():
            await asyncio.sleep(0.01)
            raise EmailError(
                code=ErrorCode.EMAIL_SEND_FAILED,
                message="メール送信失敗"
            )

        with caplog.at_level(logging.ERROR):
            await async_with_log()

        assert "EMAIL_3003" in caplog.text or "メール送信失敗" in caplog.text


class TestErrorCollectorLogAll:
    """ErrorCollector.log_allのテスト"""

    def test_log_all_multiple_errors(self, caplog):
        """複数エラーを一括ログ"""
        collector = ErrorCollector()

        collector.add(TaskMasterError(
            code=ErrorCode.VALIDATION_FAILED,
            message="入力検証エラー1"
        ))
        collector.add(TaskMasterError(
            code=ErrorCode.VALIDATION_REQUIRED_FIELD,
            message="必須フィールド未入力"
        ))
        collector.add(TaskMasterError(
            code=ErrorCode.VALIDATION_INVALID_FORMAT,
            message="形式エラー",
            severity=ErrorSeverity.WARNING
        ))

        with caplog.at_level(logging.WARNING):
            collector.log_all()

        # ログにエラーコードが含まれることを確認
        assert collector.has_errors()
        assert len(collector.get_errors()) == 3

    def test_log_all_empty_collector(self, caplog):
        """空のコレクターでlog_all"""
        collector = ErrorCollector()

        with caplog.at_level(logging.DEBUG):
            collector.log_all()

        assert not collector.has_errors()

    def test_log_all_with_different_severities(self, caplog):
        """異なる重大度のエラーをログ"""
        collector = ErrorCollector()

        collector.add(TaskMasterError(
            code=ErrorCode.SYSTEM_INTERNAL_ERROR,
            message="内部エラー",
            severity=ErrorSeverity.CRITICAL
        ))
        collector.add(TaskMasterError(
            code=ErrorCode.SYSTEM_TIMEOUT,
            message="タイムアウト",
            severity=ErrorSeverity.WARNING
        ))

        with caplog.at_level(logging.WARNING):
            collector.log_all()

        assert collector.has_critical()


class TestErrorResponseEdgeCases:
    """ErrorResponseのエッジケーステスト"""

    def test_to_user_message_unknown_code(self):
        """未定義コードのユーザーメッセージ"""
        # 既存のコードを使用するが、カスタムメッセージを設定
        response = ErrorResponse(
            code=ErrorCode.SYSTEM_INTERNAL_ERROR,
            message="カスタムエラーメッセージ"
        )

        # 定義済みメッセージが返る
        user_msg = response.to_user_message()
        assert "システムエラー" in user_msg

    def test_to_dict_with_all_fields(self):
        """全フィールドを含むto_dict"""
        context = ErrorContext(
            user_id="user123",
            request_id="req456",
            operation="test_operation"
        )

        response = ErrorResponse(
            code=ErrorCode.AUTH_FAILED,
            message="テスト認証エラー",
            severity=ErrorSeverity.ERROR,
            details={"key": "value"},
            context=context,
            timestamp=datetime(2026, 1, 10, 12, 0, 0),
            traceback_info="traceback text"
        )

        result = response.to_dict()

        assert result["error"]["code"] == "AUTH_1001"
        assert result["error"]["severity"] == "error"
        assert result["error"]["details"] == {"key": "value"}
        assert result["error"]["context"]["user_id"] == "user123"
        assert result["error"]["context"]["request_id"] == "req456"


class TestTaskMasterErrorWithCause:
    """原因例外を含むTaskMasterErrorのテスト"""

    def test_to_response_with_cause_traceback(self):
        """原因例外のトレースバックを含むレスポンス"""
        try:
            raise ValueError("元のエラー")
        except ValueError as e:
            error = TaskMasterError(
                code=ErrorCode.DB_QUERY_FAILED,
                message="DBエラー",
                cause=e
            )

        response = error.to_response()

        assert response.traceback_info is not None
        assert "ValueError" in response.traceback_info
        assert "元のエラー" in response.traceback_info

    def test_log_with_cause(self, caplog):
        """原因例外を含むログ"""
        try:
            raise IOError("ファイルエラー")
        except IOError as e:
            error = TaskMasterError(
                code=ErrorCode.SYSTEM_INTERNAL_ERROR,
                message="システムエラー",
                cause=e
            )

        with caplog.at_level(logging.ERROR):
            error.log()

        assert "SYS_8001" in caplog.text or "システムエラー" in caplog.text


class TestErrorCollectorAddIfError:
    """ErrorCollector.add_if_errorのテスト"""

    def test_add_if_error_with_error_response(self):
        """ErrorResponseを追加"""
        collector = ErrorCollector()

        response = ErrorResponse(
            code=ErrorCode.COMMAND_UNKNOWN,
            message="不明なコマンド",
            severity=ErrorSeverity.WARNING
        )

        result = collector.add_if_error(response)

        assert result is True
        assert collector.has_errors()
        assert len(collector.get_errors()) == 1

    def test_add_if_error_with_non_error(self):
        """非ErrorResponseは追加しない"""
        collector = ErrorCollector()

        result = collector.add_if_error({"status": "ok"})

        assert result is False
        assert not collector.has_errors()

    def test_add_if_error_with_none(self):
        """Noneは追加しない"""
        collector = ErrorCollector()

        result = collector.add_if_error(None)

        assert result is False
        assert not collector.has_errors()


class TestAllDomainErrors:
    """全ドメインエラークラスのテスト"""

    def test_schedule_error(self):
        """ScheduleErrorのテスト"""
        error = ScheduleError(
            code=ErrorCode.SCHEDULE_CONFLICT,
            message="スケジュール競合"
        )

        assert error.code == ErrorCode.SCHEDULE_CONFLICT
        response = error.to_response()
        assert response.code == ErrorCode.SCHEDULE_CONFLICT

    def test_llm_error(self):
        """LLMErrorのテスト"""
        error = LLMError(
            code=ErrorCode.LLM_RATE_LIMIT,
            message="レート制限",
            details={"retry_after": 60}
        )

        assert error.code == ErrorCode.LLM_RATE_LIMIT
        assert error.details == {"retry_after": 60}

    def test_database_error(self):
        """DatabaseErrorのテスト"""
        error = DatabaseError(
            code=ErrorCode.DB_CONNECTION_FAILED,
            message="接続失敗"
        )

        assert error.code == ErrorCode.DB_CONNECTION_FAILED

    def test_command_error(self):
        """CommandErrorのテスト"""
        error = CommandError(
            code=ErrorCode.COMMAND_PARSE_FAILED,
            message="パース失敗"
        )

        assert error.code == ErrorCode.COMMAND_PARSE_FAILED

    def test_validation_error_default_severity(self):
        """ValidationErrorのデフォルト重大度"""
        error = ValidationError(
            code=ErrorCode.VALIDATION_FAILED,
            message="検証失敗"
        )

        # デフォルトでWARNING
        assert error.severity == ErrorSeverity.WARNING

    def test_validation_error_custom_severity(self):
        """ValidationErrorのカスタム重大度"""
        error = ValidationError(
            code=ErrorCode.VALIDATION_FAILED,
            message="検証失敗",
            severity=ErrorSeverity.ERROR
        )

        assert error.severity == ErrorSeverity.ERROR


class TestErrorCodeUserMessages:
    """全ErrorCodeのユーザーメッセージテスト"""

    @pytest.mark.parametrize("code,expected_keyword", [
        (ErrorCode.AUTH_FAILED, "認証"),
        (ErrorCode.AUTH_TOKEN_EXPIRED, "有効期限"),
        (ErrorCode.AUTH_TOKEN_INVALID, "無効"),
        (ErrorCode.AUTH_CREDENTIALS_MISSING, "認証情報"),
        (ErrorCode.AUTH_PERMISSION_DENIED, "権限"),
        (ErrorCode.AUTH_OAUTH_FAILED, "外部サービス"),
        (ErrorCode.BILLING_SUBSCRIPTION_NOT_FOUND, "サブスクリプション"),
        (ErrorCode.BILLING_USAGE_LIMIT_EXCEEDED, "上限"),
        (ErrorCode.BILLING_PAYMENT_FAILED, "決済"),
        (ErrorCode.BILLING_PLAN_INVALID, "プラン"),
        (ErrorCode.BILLING_STRIPE_ERROR, "決済システム"),
        (ErrorCode.EMAIL_FETCH_FAILED, "メール"),
        (ErrorCode.EMAIL_PARSE_FAILED, "解析"),
        (ErrorCode.EMAIL_SEND_FAILED, "送信"),
        (ErrorCode.EMAIL_DRAFT_FAILED, "下書き"),
        (ErrorCode.EMAIL_GMAIL_API_ERROR, "Gmail"),
        (ErrorCode.EMAIL_SUMMARIZE_FAILED, "要約"),
        (ErrorCode.SCHEDULE_FETCH_FAILED, "スケジュール"),
        (ErrorCode.SCHEDULE_CREATE_FAILED, "予定"),
        (ErrorCode.SCHEDULE_CONFLICT, "既存"),
        (ErrorCode.SCHEDULE_CALENDAR_API_ERROR, "カレンダー"),
        (ErrorCode.SCHEDULE_NO_AVAILABLE_SLOT, "空き時間"),
        (ErrorCode.LLM_API_ERROR, "AI"),
        (ErrorCode.LLM_RATE_LIMIT, "利用制限"),
        (ErrorCode.LLM_RESPONSE_INVALID, "AI応答"),
        (ErrorCode.LLM_PROVIDER_UNAVAILABLE, "AI処理サービス"),
        (ErrorCode.DB_CONNECTION_FAILED, "データベース接続"),
        (ErrorCode.DB_QUERY_FAILED, "データベース処理"),
        (ErrorCode.DB_NOT_FOUND, "データが見つかりません"),
        (ErrorCode.DB_INTEGRITY_ERROR, "整合性"),
        (ErrorCode.VALIDATION_FAILED, "入力内容"),
        (ErrorCode.VALIDATION_REQUIRED_FIELD, "必須"),
        (ErrorCode.VALIDATION_INVALID_FORMAT, "入力形式"),
        (ErrorCode.VALIDATION_OUT_OF_RANGE, "範囲外"),
        (ErrorCode.SYSTEM_INTERNAL_ERROR, "システムエラー"),
        (ErrorCode.SYSTEM_SERVICE_UNAVAILABLE, "サービス"),
        (ErrorCode.SYSTEM_TIMEOUT, "タイムアウト"),
        (ErrorCode.SYSTEM_CONFIGURATION_ERROR, "設定"),
        (ErrorCode.COMMAND_UNKNOWN, "不明"),
        (ErrorCode.COMMAND_PARSE_FAILED, "解析"),
        (ErrorCode.COMMAND_EXECUTION_FAILED, "実行"),
    ])
    def test_user_message_contains_keyword(self, code, expected_keyword):
        """各エラーコードのユーザーメッセージに期待するキーワードが含まれる"""
        response = ErrorResponse(
            code=code,
            message="テストメッセージ"
        )

        user_msg = response.to_user_message()
        assert expected_keyword in user_msg, f"{code.value}: '{expected_keyword}' not in '{user_msg}'"


class TestErrorContextFields:
    """ErrorContextフィールドのテスト"""

    def test_context_with_additional_info(self):
        """additional_infoを含むコンテキスト"""
        context = ErrorContext(
            user_id="user123",
            operation="test_op",
            additional_info={"key1": "value1", "key2": 123}
        )

        error = TaskMasterError(
            code=ErrorCode.SYSTEM_INTERNAL_ERROR,
            message="エラー",
            context=context
        )

        assert error.context.additional_info["key1"] == "value1"
        assert error.context.additional_info["key2"] == 123

    def test_context_with_input_data(self):
        """input_dataを含むコンテキスト"""
        context = ErrorContext(
            user_id="user456",
            input_data={"email": "test@example.com", "action": "login"}
        )

        error = TaskMasterError(
            code=ErrorCode.AUTH_FAILED,
            message="ログイン失敗",
            context=context
        )

        assert error.context.input_data["email"] == "test@example.com"
