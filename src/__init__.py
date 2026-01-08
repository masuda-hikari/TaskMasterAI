"""
TaskMasterAI - AI-Powered Virtual Executive Assistant

自動化モジュール:
- email_bot: メール処理・要約
- scheduler: カレンダー管理・スケジューリング
- coordinator: 中央調整・コマンド処理
- errors: 統一エラーハンドリング
- logging_config: 構造化ロギング
"""

__version__ = "0.1.0"
__author__ = "TaskMasterAI Team"

# ロギング設定の初期化
from .logging_config import configure_logging, get_logger

# エラーハンドリングのエクスポート
from .errors import (
    ErrorCode,
    ErrorSeverity,
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
)
