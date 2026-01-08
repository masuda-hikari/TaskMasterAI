"""
Coordinator Module テスト

ユーザーコマンド処理と各モジュール連携のテスト
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from src.coordinator import (
    Coordinator,
    CommandResult,
    Action,
    ActionType
)
from src.email_bot import EmailBot, Email, EmailSummary
from src.scheduler import Scheduler, CalendarEvent, TimeSlot, MeetingProposal
from src.auth import AuthManager, AuthStatus, AuthProvider
from src.llm import LLMService


class TestCommandResult:
    """CommandResult データクラスのテスト"""

    def test_success_result(self):
        """成功結果の作成"""
        result = CommandResult(
            success=True,
            message="操作が成功しました"
        )
        assert result.success is True
        assert result.message == "操作が成功しました"
        assert result.data is None
        assert result.pending_actions is None

    def test_failure_result(self):
        """失敗結果の作成"""
        result = CommandResult(
            success=False,
            message="エラーが発生しました"
        )
        assert result.success is False
        assert result.message == "エラーが発生しました"

    def test_result_with_data(self):
        """データ付き結果"""
        result = CommandResult(
            success=True,
            message="成功",
            data={"count": 5, "items": ["a", "b", "c"]}
        )
        assert result.data == {"count": 5, "items": ["a", "b", "c"]}


class TestAction:
    """Action データクラスのテスト"""

    def test_action_creation(self):
        """アクションの作成"""
        action = Action(
            type=ActionType.READ_ONLY,
            description="メール取得",
            execute=lambda: None
        )
        assert action.type == ActionType.READ_ONLY
        assert action.description == "メール取得"
        assert action.requires_confirmation is False
        assert action.confirmed is False

    def test_action_with_confirmation(self):
        """確認が必要なアクション"""
        action = Action(
            type=ActionType.EXTERNAL,
            description="メール送信",
            execute=lambda: None,
            requires_confirmation=True
        )
        assert action.type == ActionType.EXTERNAL
        assert action.requires_confirmation is True


class TestCoordinatorInitialization:
    """Coordinator 初期化テスト"""

    def test_default_initialization(self):
        """デフォルト初期化"""
        coord = Coordinator()

        assert coord.email_bot is not None
        assert coord.scheduler is not None
        assert coord.auth_manager is not None
        assert coord.llm_service is not None
        assert coord.confirmation_required is True

    def test_custom_initialization(self):
        """カスタム初期化"""
        mock_email_bot = Mock(spec=EmailBot)
        mock_scheduler = Mock(spec=Scheduler)

        coord = Coordinator(
            email_bot=mock_email_bot,
            scheduler=mock_scheduler,
            confirmation_required=False
        )

        assert coord.email_bot is mock_email_bot
        assert coord.scheduler is mock_scheduler
        assert coord.confirmation_required is False


class TestCoordinatorHelp:
    """help コマンドのテスト"""

    def test_help_command(self):
        """helpコマンドの実行"""
        coord = Coordinator()
        result = coord.process_command("help")

        assert result.success is True
        assert "TaskMasterAI" in result.message
        assert "inbox" in result.message
        assert "schedule" in result.message
        assert "auth" in result.message

    def test_help_includes_all_commands(self):
        """helpに全コマンドが含まれる"""
        coord = Coordinator()
        result = coord.process_command("help")

        commands = ["inbox", "schedule", "status", "auth", "confirm", "cancel", "help"]
        for cmd in commands:
            assert cmd in result.message.lower()


class TestCoordinatorInbox:
    """inbox/summarize inbox コマンドのテスト"""

    def test_inbox_command(self):
        """inboxコマンドの実行"""
        # モックのEmailBotを作成
        mock_email_bot = Mock(spec=EmailBot)
        mock_email_bot.summarize_inbox.return_value = [
            EmailSummary(
                email_id="1",
                subject="テストメール",
                sender="test@example.com",
                summary="テストの要約",
                priority="medium",
                action_items=["確認する"]
            )
        ]

        coord = Coordinator(email_bot=mock_email_bot)
        result = coord.process_command("inbox")

        assert result.success is True
        assert "テストメール" in result.message
        assert "test@example.com" in result.message
        mock_email_bot.summarize_inbox.assert_called_once()

    def test_summarize_inbox_command(self):
        """summarize inboxコマンドの実行"""
        mock_email_bot = Mock(spec=EmailBot)
        mock_email_bot.summarize_inbox.return_value = []

        coord = Coordinator(email_bot=mock_email_bot)
        result = coord.process_command("summarize inbox")

        assert result.success is True
        assert "未読メール" in result.message

    def test_inbox_with_high_priority(self):
        """高優先度メールの表示"""
        mock_email_bot = Mock(spec=EmailBot)
        mock_email_bot.summarize_inbox.return_value = [
            EmailSummary(
                email_id="1",
                subject="緊急：対応必要",
                sender="boss@example.com",
                summary="すぐに確認してください",
                priority="high",
                action_items=[]
            )
        ]

        coord = Coordinator(email_bot=mock_email_bot)
        result = coord.process_command("inbox")

        assert result.success is True
        assert "🔴" in result.message  # 高優先度アイコン
        assert result.data is not None
        assert len(result.data["summaries"]) == 1

    def test_inbox_with_action_items(self):
        """アクション項目の表示"""
        mock_email_bot = Mock(spec=EmailBot)
        mock_email_bot.summarize_inbox.return_value = [
            EmailSummary(
                email_id="1",
                subject="会議招集",
                sender="manager@example.com",
                summary="来週の会議について",
                priority="medium",
                action_items=["出席を確認", "資料を準備"]
            )
        ]

        coord = Coordinator(email_bot=mock_email_bot)
        result = coord.process_command("inbox")

        assert result.success is True
        assert "出席を確認" in result.message
        assert "資料を準備" in result.message


class TestCoordinatorSchedule:
    """schedule コマンドのテスト"""

    def test_schedule_basic(self):
        """基本的なスケジュールコマンド"""
        mock_scheduler = Mock(spec=Scheduler)
        mock_scheduler.propose_meeting.return_value = [
            MeetingProposal(
                title="Team Meeting",
                slot=TimeSlot(
                    start=datetime.now() + timedelta(hours=1),
                    end=datetime.now() + timedelta(hours=2)
                ),
                attendees=["alice@example.com"],
                score=0.8
            )
        ]

        coord = Coordinator(scheduler=mock_scheduler)
        result = coord.process_command("schedule team meeting with alice@example.com 30min")

        assert result.success is True
        assert "会議提案" in result.message
        mock_scheduler.propose_meeting.assert_called_once()

    def test_schedule_no_slots(self):
        """空き時間がない場合"""
        mock_scheduler = Mock(spec=Scheduler)
        mock_scheduler.propose_meeting.return_value = []

        coord = Coordinator(scheduler=mock_scheduler)
        result = coord.process_command("schedule meeting")

        assert result.success is True
        assert "見つかりません" in result.message

    def test_schedule_creates_pending_actions(self):
        """保留アクションが作成される"""
        mock_scheduler = Mock(spec=Scheduler)
        mock_scheduler.propose_meeting.return_value = [
            MeetingProposal(
                title="Meeting",
                slot=TimeSlot(
                    start=datetime.now() + timedelta(hours=1),
                    end=datetime.now() + timedelta(hours=2)
                ),
                attendees=[],
                score=0.9
            )
        ]

        coord = Coordinator(scheduler=mock_scheduler)
        result = coord.process_command("schedule quick sync")

        assert result.pending_actions is not None
        assert len(result.pending_actions) > 0
        assert result.pending_actions[0].requires_confirmation is True


class TestCoordinatorStatus:
    """status/today コマンドのテスト"""

    def test_status_command(self):
        """statusコマンドの実行"""
        mock_scheduler = Mock(spec=Scheduler)
        mock_scheduler.get_today_schedule.return_value = []
        mock_scheduler.format_schedule.return_value = "予定なし"

        coord = Coordinator(scheduler=mock_scheduler)
        result = coord.process_command("status")

        assert result.success is True
        assert "ステータス" in result.message
        mock_scheduler.get_today_schedule.assert_called_once()

    def test_today_command(self):
        """todayコマンドの実行"""
        mock_scheduler = Mock(spec=Scheduler)
        mock_scheduler.get_today_schedule.return_value = []
        mock_scheduler.format_schedule.return_value = "予定なし"

        coord = Coordinator(scheduler=mock_scheduler)
        result = coord.process_command("today")

        assert result.success is True
        assert "ステータス" in result.message

    def test_status_with_events(self):
        """イベントがある場合のステータス"""
        mock_scheduler = Mock(spec=Scheduler)
        mock_scheduler.get_today_schedule.return_value = [
            CalendarEvent(
                id="1",
                summary="朝会",
                start=datetime.now().replace(hour=9, minute=0),
                end=datetime.now().replace(hour=10, minute=0)
            )
        ]
        mock_scheduler.format_schedule.return_value = "09:00 - 10:00 朝会"

        coord = Coordinator(scheduler=mock_scheduler)
        result = coord.process_command("status")

        assert result.success is True
        assert result.data is not None


class TestCoordinatorAuth:
    """auth コマンドのテスト"""

    def test_auth_status_command(self):
        """auth statusコマンドの実行"""
        mock_auth = Mock(spec=AuthManager)
        mock_auth.get_all_auth_status.return_value = {
            AuthProvider.GOOGLE: AuthStatus(
                provider=AuthProvider.GOOGLE,
                is_authenticated=False,
                error_message="認証情報がありません"
            )
        }

        mock_llm = Mock(spec=LLMService)
        mock_llm.get_available_providers.return_value = []

        coord = Coordinator(auth_manager=mock_auth, llm_service=mock_llm)
        result = coord.process_command("auth")

        assert result.success is True
        assert "認証状態" in result.message

    def test_auth_shows_authenticated(self):
        """認証済みの表示"""
        mock_auth = Mock(spec=AuthManager)
        mock_auth.get_all_auth_status.return_value = {
            AuthProvider.GOOGLE: AuthStatus(
                provider=AuthProvider.GOOGLE,
                is_authenticated=True,
                user_email="user@gmail.com",
                scopes=["https://www.googleapis.com/auth/gmail.readonly"]
            )
        }

        mock_llm = Mock(spec=LLMService)
        mock_llm.get_available_providers.return_value = []

        coord = Coordinator(auth_manager=mock_auth, llm_service=mock_llm)
        result = coord.process_command("auth status")

        assert result.success is True
        assert "✅" in result.message
        assert "user@gmail.com" in result.message


class TestCoordinatorConfirmCancel:
    """confirm/cancel コマンドのテスト"""

    def test_confirm_without_pending(self):
        """保留アクションがない場合のconfirm"""
        coord = Coordinator()
        result = coord.process_command("confirm")

        assert result.success is False
        assert "確認待ち" in result.message

    def test_cancel_without_pending(self):
        """保留アクションがない場合のcancel"""
        coord = Coordinator()
        result = coord.process_command("cancel")

        assert result.success is True
        assert "キャンセルする" in result.message

    def test_cancel_with_pending(self):
        """保留アクションがある場合のcancel"""
        coord = Coordinator()
        # 保留アクションを手動で追加
        coord._pending_actions = [
            Action(
                type=ActionType.EXTERNAL,
                description="テストアクション",
                execute=lambda: None,
                requires_confirmation=True
            )
        ]

        result = coord.process_command("cancel")

        assert result.success is True
        assert "キャンセル" in result.message
        assert len(coord._pending_actions) == 0


class TestCoordinatorUnknownCommand:
    """不明なコマンドのテスト"""

    def test_unknown_command(self):
        """不明なコマンドへの応答"""
        coord = Coordinator()
        result = coord.process_command("unknown command xyz")

        assert result.success is False
        assert "不明なコマンド" in result.message
        assert "help" in result.message

    def test_empty_command(self):
        """空コマンドへの応答"""
        coord = Coordinator()
        result = coord.process_command("")

        assert result.success is False


class TestCoordinatorDraftReply:
    """draft reply コマンドのテスト"""

    def test_draft_reply_in_development(self):
        """draft replyが開発中であることを確認"""
        coord = Coordinator()
        result = coord.process_command("draft reply --to 123")

        assert result.success is True
        assert "開発中" in result.message


class TestCoordinatorCaseInsensitive:
    """コマンドの大文字小文字を無視するテスト"""

    def test_uppercase_command(self):
        """大文字コマンド"""
        coord = Coordinator()
        result = coord.process_command("HELP")

        assert result.success is True

    def test_mixed_case_command(self):
        """大文字小文字混在コマンド"""
        coord = Coordinator()
        result = coord.process_command("HeLp")

        assert result.success is True

    def test_command_with_whitespace(self):
        """前後の空白があるコマンド"""
        coord = Coordinator()
        result = coord.process_command("  help  ")

        assert result.success is True


class TestCoordinatorAuditLog:
    """監査ログのテスト"""

    def test_audit_log_disabled(self):
        """監査ログが無効の場合"""
        coord = Coordinator(audit_log_path=None)

        # ログパスがNoneでもエラーにならない
        coord._log_action("test", "テストアクション")

    def test_audit_log_enabled(self, tmp_path):
        """監査ログが有効の場合"""
        import json

        log_path = tmp_path / "audit.json"
        coord = Coordinator(audit_log_path=str(log_path))

        # _log_actionを直接呼び出してテスト
        coord._log_action("test_action", "テストアクションの説明")

        # ログファイルが作成されていることを確認
        assert log_path.exists()

        with open(log_path, 'r', encoding='utf-8') as f:
            logs = json.load(f)

        assert len(logs) > 0
        assert "timestamp" in logs[0]
        assert "action_type" in logs[0]
        assert logs[0]["action_type"] == "test_action"


class TestCoordinatorErrorHandling:
    """エラーハンドリングのテスト"""

    def test_inbox_error_handling(self):
        """inbox実行中のエラーハンドリング"""
        mock_email_bot = Mock(spec=EmailBot)
        mock_email_bot.summarize_inbox.side_effect = Exception("API接続エラー")

        coord = Coordinator(email_bot=mock_email_bot)
        result = coord.process_command("inbox")

        assert result.success is False
        assert "エラー" in result.message

    def test_schedule_error_handling(self):
        """schedule実行中のエラーハンドリング"""
        mock_scheduler = Mock(spec=Scheduler)
        mock_scheduler.propose_meeting.side_effect = Exception("カレンダーAPI接続エラー")

        coord = Coordinator(scheduler=mock_scheduler)
        result = coord.process_command("schedule meeting")

        assert result.success is False
        assert "エラー" in result.message

    def test_status_error_handling(self):
        """status実行中のエラーハンドリング"""
        mock_scheduler = Mock(spec=Scheduler)
        mock_scheduler.get_today_schedule.side_effect = Exception("予定取得エラー")

        coord = Coordinator(scheduler=mock_scheduler)
        result = coord.process_command("status")

        assert result.success is False
        assert "エラー" in result.message
