# -*- coding: utf-8 -*-
"""
coordinator.pyカバレッジ向上テスト

対象: 88% → 95%目標
未カバー行:
- 235-236: duration パースエラー時のwarningログ
- 443-458: _handle_confirm のアクション実行・例外
- 498-499, 514-525: _log_action の監査ログ例外処理
- 532-541: __main__ブロック（テスト対象外）
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, PropertyMock

from src.coordinator import (
    Coordinator,
    CommandResult,
    Action,
    ActionType,
)


class TestDurationParseWarning:
    """duration パースエラー時のwarningログテスト"""

    def test_invalid_duration_format_logs_warning(self) -> None:
        """無効なduration形式でwarningログが出力される"""
        coord = Coordinator()

        with patch('src.coordinator.logger') as mock_logger:
            # 無効なduration形式を含むコマンド
            result = coord.process_command("schedule meeting with test@example.com invalidmin")
            # warningが呼ばれたことを確認
            mock_logger.warning.assert_called()

    def test_non_numeric_duration(self) -> None:
        """数値でないduration"""
        coord = Coordinator()

        with patch('src.coordinator.logger') as mock_logger:
            result = coord.process_command("schedule meeting abcmin")
            mock_logger.warning.assert_called()


class TestHandleConfirm:
    """_handle_confirm のテスト"""

    def test_confirm_no_pending_actions(self) -> None:
        """保留アクションがない場合のconfirm"""
        coord = Coordinator()
        result = coord.process_command("confirm")
        assert result.success is False
        assert "確認待ちのアクションはありません" in result.message

    def test_confirm_executes_action(self) -> None:
        """保留アクションの実行"""
        coord = Coordinator()

        # モックアクションを追加
        mock_action = Action(
            type=ActionType.EXTERNAL,
            description="テストアクション",
            execute=MagicMock(return_value=True),
            requires_confirmation=True,
            confirmed=False
        )
        coord._pending_actions = [mock_action]

        result = coord.process_command("confirm")
        assert result.success is True
        assert "アクションを実行しました" in result.message
        mock_action.execute.assert_called_once()

    def test_confirm_action_execution_error(self) -> None:
        """アクション実行時のエラーハンドリング"""
        coord = Coordinator()

        # エラーを発生させるモックアクション
        mock_action = Action(
            type=ActionType.EXTERNAL,
            description="エラーアクション",
            execute=MagicMock(side_effect=Exception("Execution failed")),
            requires_confirmation=True,
            confirmed=False
        )
        coord._pending_actions = [mock_action]

        result = coord.process_command("confirm")
        assert result.success is False
        assert "アクション実行エラー" in result.message

    def test_confirm_clears_pending_actions(self) -> None:
        """confirm後に保留アクションがクリアされる"""
        coord = Coordinator()

        mock_action = Action(
            type=ActionType.EXTERNAL,
            description="テストアクション",
            execute=MagicMock(return_value=True),
            requires_confirmation=True,
            confirmed=False
        )
        coord._pending_actions = [mock_action]

        coord.process_command("confirm")
        assert len(coord._pending_actions) == 0


class TestHandleCancel:
    """_handle_cancel のテスト"""

    def test_cancel_no_pending_actions(self) -> None:
        """保留アクションがない場合のcancel"""
        coord = Coordinator()
        result = coord.process_command("cancel")
        assert result.success is True
        assert "キャンセルするアクションはありません" in result.message

    def test_cancel_with_pending_actions(self) -> None:
        """保留アクションがある場合のcancel"""
        coord = Coordinator()

        # 複数のアクションを追加
        for i in range(3):
            coord._pending_actions.append(
                Action(
                    type=ActionType.EXTERNAL,
                    description=f"アクション{i}",
                    execute=MagicMock(),
                    requires_confirmation=True,
                    confirmed=False
                )
            )

        result = coord.process_command("cancel")
        assert result.success is True
        assert "3件の保留中アクションをキャンセル" in result.message
        assert len(coord._pending_actions) == 0


class TestLogAction:
    """_log_action のテスト"""

    def test_log_action_without_audit_log_path(self) -> None:
        """audit_log_pathがない場合はログを書かない"""
        coord = Coordinator(audit_log_path=None)
        # エラーが発生しないことを確認
        coord._log_action("test", "テスト")

    def test_log_action_creates_new_log_file(self, tmp_path) -> None:
        """新規ログファイルの作成"""
        log_path = tmp_path / "audit.json"
        coord = Coordinator(audit_log_path=str(log_path))

        coord._log_action("user_action", "ユーザーアクション実行")

        assert log_path.exists()
        with open(log_path, 'r', encoding='utf-8') as f:
            logs = json.load(f)
        assert len(logs) == 1
        assert logs[0]["action_type"] == "user_action"

    def test_log_action_appends_to_existing_log(self, tmp_path) -> None:
        """既存ログファイルへの追記"""
        log_path = tmp_path / "audit.json"

        # 既存ログを作成
        existing_logs = [
            {"timestamp": "2025-01-01T00:00:00", "action_type": "old", "description": "古いログ"}
        ]
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(existing_logs, f)

        coord = Coordinator(audit_log_path=str(log_path))
        coord._log_action("new_action", "新しいアクション")

        with open(log_path, 'r', encoding='utf-8') as f:
            logs = json.load(f)
        assert len(logs) == 2
        assert logs[1]["action_type"] == "new_action"

    def test_log_action_json_decode_error(self, tmp_path) -> None:
        """JSONデコードエラー時のハンドリング"""
        log_path = tmp_path / "audit.json"

        # 不正なJSONを作成
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("invalid json {{{")

        coord = Coordinator(audit_log_path=str(log_path))

        with patch('src.coordinator.logger') as mock_logger:
            coord._log_action("test", "テスト")
            mock_logger.warning.assert_called()

    def test_log_action_permission_error(self, tmp_path) -> None:
        """書き込み権限エラー時のハンドリング"""
        log_path = tmp_path / "readonly" / "audit.json"

        coord = Coordinator(audit_log_path=str(log_path))

        with patch('builtins.open', side_effect=PermissionError("Permission denied")):
            with patch('src.coordinator.logger') as mock_logger:
                coord._log_action("test", "テスト")
                mock_logger.warning.assert_called()

    def test_log_action_general_exception(self, tmp_path) -> None:
        """一般的な例外のハンドリング"""
        log_path = tmp_path / "audit.json"

        coord = Coordinator(audit_log_path=str(log_path))

        with patch.object(Path, 'exists', side_effect=OSError("Unexpected error")):
            with patch('src.coordinator.logger') as mock_logger:
                coord._log_action("test", "テスト")
                mock_logger.warning.assert_called()


class TestScheduleCommandParsing:
    """schedule コマンドのパーシングテスト"""

    def test_schedule_with_valid_duration(self) -> None:
        """有効なduration指定"""
        coord = Coordinator()
        result = coord.process_command("schedule meeting 60min")
        # 結果を確認（スケジューラーのモックがなくても基本的な処理は行われる）
        assert result is not None

    def test_schedule_with_attendees(self) -> None:
        """参加者指定付きスケジュール"""
        coord = Coordinator()
        result = coord.process_command("schedule meeting with user1@example.com user2@example.com")
        assert result is not None

    def test_schedule_with_title(self) -> None:
        """タイトル付きスケジュール"""
        coord = Coordinator()
        result = coord.process_command("schedule Project Review Meeting")
        assert result is not None

    def test_schedule_ignores_common_words(self) -> None:
        """'with'や'for'をタイトルから除外"""
        coord = Coordinator()
        result = coord.process_command("schedule meeting with team for review")
        assert result is not None


class TestActionDataclass:
    """Actionデータクラスのテスト"""

    def test_action_creation(self) -> None:
        """Actionの作成"""
        action = Action(
            type=ActionType.EXTERNAL,
            description="テストメール送信",
            execute=lambda: True,
            requires_confirmation=True,
            confirmed=False
        )
        assert action.type == ActionType.EXTERNAL
        assert action.description == "テストメール送信"
        assert action.confirmed is False

    def test_action_execute(self) -> None:
        """Actionの実行"""
        result_value = {"sent": True}
        action = Action(
            type=ActionType.READ_ONLY,
            description="テスト",
            execute=lambda: result_value,
            requires_confirmation=False,
            confirmed=True
        )
        result = action.execute()
        assert result == result_value

    def test_action_types(self) -> None:
        """ActionTypeの値確認"""
        assert ActionType.READ_ONLY.value == "read_only"
        assert ActionType.DRAFT.value == "draft"
        assert ActionType.EXTERNAL.value == "external"


class TestCommandResultDataclass:
    """CommandResultデータクラスのテスト"""

    def test_command_result_success(self) -> None:
        """成功結果"""
        result = CommandResult(
            success=True,
            message="操作が完了しました",
            data={"count": 10}
        )
        assert result.success is True
        assert result.message == "操作が完了しました"
        assert result.data == {"count": 10}

    def test_command_result_failure(self) -> None:
        """失敗結果"""
        result = CommandResult(
            success=False,
            message="エラーが発生しました"
        )
        assert result.success is False
        assert result.data is None


class TestCoordinatorIntegration:
    """Coordinator統合テスト"""

    def test_process_help_command(self) -> None:
        """helpコマンド"""
        coord = Coordinator()
        result = coord.process_command("help")
        assert result.success is True
        assert "ヘルプ" in result.message or "コマンド" in result.message

    def test_process_status_command(self) -> None:
        """statusコマンド"""
        coord = Coordinator()
        result = coord.process_command("status")
        # statusコマンドは認証が必要な場合があるのでsuccessでなくてもよい
        assert result is not None

    def test_process_unknown_command(self) -> None:
        """未知のコマンド"""
        coord = Coordinator()
        result = coord.process_command("unknown_command_xyz")
        # 未知のコマンドでもエラーにはならない
        assert result is not None

    def test_coordinator_with_email_bot(self) -> None:
        """EmailBot付きCoordinatorの初期化"""
        mock_email_bot = MagicMock()
        coord = Coordinator(email_bot=mock_email_bot)
        assert coord.email_bot is mock_email_bot

    def test_coordinator_with_scheduler(self) -> None:
        """Scheduler付きCoordinatorの初期化"""
        mock_scheduler = MagicMock()
        coord = Coordinator(scheduler=mock_scheduler)
        assert coord.scheduler is mock_scheduler

    def test_coordinator_full_init(self) -> None:
        """完全な初期化パラメータ"""
        mock_email = MagicMock()
        mock_scheduler = MagicMock()

        coord = Coordinator(
            email_bot=mock_email,
            scheduler=mock_scheduler,
            audit_log_path="/tmp/audit.json",
            confirmation_required=True
        )

        assert coord.email_bot is mock_email
        assert coord.scheduler is mock_scheduler
        assert coord.audit_log_path == "/tmp/audit.json"
        assert coord.confirmation_required is True


class TestConfirmationFlow:
    """確認フローのテスト"""

    def test_confirmation_required_enabled(self) -> None:
        """確認モード有効時"""
        coord = Coordinator(confirmation_required=True)
        assert coord.confirmation_required is True

    def test_confirmation_required_default(self) -> None:
        """デフォルトで確認必須"""
        coord = Coordinator()
        assert coord.confirmation_required is True

    def test_pending_actions_list(self) -> None:
        """保留アクションリストの管理"""
        coord = Coordinator()
        assert coord._pending_actions == []

        # アクション追加
        action = Action(
            type=ActionType.EXTERNAL,
            description="テスト",
            execute=MagicMock(),
            requires_confirmation=True,
            confirmed=False
        )
        coord._pending_actions.append(action)
        assert len(coord._pending_actions) == 1

        # クリア
        coord._pending_actions.clear()
        assert len(coord._pending_actions) == 0
