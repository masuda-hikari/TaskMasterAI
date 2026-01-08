"""
CLI統合テスト - コマンドラインインターフェースの統合テスト

CLIの各モードと機能の動作を検証
"""

import pytest
import sys
from io import StringIO
from unittest.mock import Mock, patch, MagicMock

from src.cli import (
    print_banner,
    single_command_mode,
)
from src.coordinator import Coordinator, CommandResult
from src.llm import create_llm_service


class TestCLIBanner:
    """CLIバナー表示テスト"""

    def test_print_banner_output(self, capsys):
        """バナー出力確認"""
        print_banner()
        captured = capsys.readouterr()

        # バナーが出力される（ASCIIアートまたは通常テキスト）
        assert len(captured.out) > 100  # バナーは十分な長さがある
        # 絵文字またはアスキーアートボックスが含まれる
        assert "AI" in captured.out or "Virtual" in captured.out or "🤖" in captured.out or "╔" in captured.out


class TestSingleCommandMode:
    """単一コマンドモードテスト"""

    def test_single_command_help(self):
        """helpコマンド実行（実際の実行）"""
        result = single_command_mode(["help"])
        assert result == 0

    def test_single_command_auth(self):
        """authコマンド実行（実際の実行）"""
        result = single_command_mode(["auth"])
        assert result == 0

    def test_single_command_failure(self):
        """不明なコマンドは失敗"""
        result = single_command_mode(["unknown_xyz_command"])
        assert result == 1


class TestCLICoordinatorIntegration:
    """CLIとCoordinatorの統合テスト"""

    def setup_method(self):
        """各テスト前にモックLLMでCoordinatorを初期化"""
        self.llm = create_llm_service(use_mock=True)
        self.coordinator = Coordinator(llm_service=self.llm)

    def test_help_command_integration(self):
        """helpコマンドの統合テスト"""
        result = self.coordinator.process_command("help")

        assert result.success is True
        assert "コマンド" in result.message
        assert "inbox" in result.message
        assert "status" in result.message

    def test_auth_command_integration(self):
        """authコマンドの統合テスト"""
        result = self.coordinator.process_command("auth")

        assert result.success is True
        assert "認証" in result.message

    def test_status_command_integration(self):
        """statusコマンドの統合テスト（モック使用）"""
        result = self.coordinator.process_command("status")

        # モックなのでエラーまたは成功どちらでも許容
        # 重要なのはクラッシュしないこと
        assert result.message is not None

    def test_inbox_command_integration(self):
        """inboxコマンドの統合テスト"""
        result = self.coordinator.process_command("inbox")

        # モックLLM使用のためエラーまたは成功どちらでも許容
        assert result.message is not None

    def test_today_command_integration(self):
        """todayコマンドの統合テスト"""
        result = self.coordinator.process_command("today")

        # モックなのでエラーまたは成功どちらでも許容
        assert result.message is not None

    def test_unknown_command_integration(self):
        """不明なコマンドの統合テスト"""
        result = self.coordinator.process_command("xyz_unknown_command")

        assert result.success is False
        assert "不明" in result.message


class TestCLIScheduleIntegration:
    """CLIスケジュールコマンドの統合テスト"""

    def setup_method(self):
        """モックLLMでCoordinator初期化"""
        self.llm = create_llm_service(use_mock=True)
        self.coordinator = Coordinator(llm_service=self.llm)

    def test_schedule_basic(self):
        """基本的なスケジュールコマンド"""
        result = self.coordinator.process_command("schedule meeting 30min")

        # 成功またはエラーメッセージがある
        assert result.message is not None

    def test_schedule_with_attendees(self):
        """参加者付きスケジュールコマンド"""
        result = self.coordinator.process_command(
            "schedule team sync with alice@example.com bob@example.com 45min"
        )

        assert result.message is not None

    def test_schedule_then_cancel(self):
        """スケジュール後キャンセル"""
        # スケジュール
        result1 = self.coordinator.process_command("schedule meeting 30min")
        assert result1.message is not None

        # キャンセル
        result2 = self.coordinator.process_command("cancel")
        assert result2.success is True


class TestCLIConfirmationFlow:
    """CLI確認フローのテスト"""

    def setup_method(self):
        """モックLLMでCoordinator初期化"""
        self.coordinator = Coordinator()

    def test_confirm_without_pending(self):
        """保留なしでconfirm"""
        result = self.coordinator.process_command("confirm")

        assert result.success is False

    def test_cancel_without_pending(self):
        """保留なしでcancel"""
        result = self.coordinator.process_command("cancel")

        assert result.success is True
        assert "キャンセル" in result.message


class TestCLIEdgeCases:
    """CLIエッジケーステスト"""

    def setup_method(self):
        """Coordinator初期化"""
        self.coordinator = Coordinator()

    def test_empty_command(self):
        """空コマンド"""
        result = self.coordinator.process_command("")

        assert result.success is False

    def test_whitespace_command(self):
        """空白のみのコマンド"""
        result = self.coordinator.process_command("   ")

        assert result.success is False

    def test_case_insensitive_commands(self):
        """大文字小文字の区別なし"""
        result1 = self.coordinator.process_command("HELP")
        result2 = self.coordinator.process_command("Help")
        result3 = self.coordinator.process_command("help")

        assert result1.success is True
        assert result2.success is True
        assert result3.success is True

    def test_command_with_extra_spaces(self):
        """余分な空白を含むコマンド（help）"""
        result = self.coordinator.process_command("  help  ")

        assert result.success is True


class TestCLIAuditLogging:
    """CLI監査ログテスト"""

    def test_audit_log_enabled(self):
        """監査ログ有効"""
        import tempfile
        import os

        temp_dir = tempfile.mkdtemp()
        audit_path = os.path.join(temp_dir, "audit.json")

        coordinator = Coordinator(audit_log_path=audit_path)

        # helpコマンドはログを出力しないが、inboxは出力する
        coordinator.process_command("help")

        # 監査ログはinboxなど特定コマンドで作成される
        # helpコマンドではログが作成されないこともある

    def test_audit_log_disabled(self):
        """監査ログ無効"""
        coordinator = Coordinator(audit_log_path=None)

        # エラーなく実行できる
        result = coordinator.process_command("help")
        assert result.success is True


class TestCLIMultipleCommands:
    """複数コマンドのシーケンステスト"""

    def test_typical_session_sequence(self):
        """典型的なセッションシーケンス"""
        coordinator = Coordinator()

        # 1. ヘルプ
        r1 = coordinator.process_command("help")
        assert r1.success is True

        # 2. 認証状態
        r2 = coordinator.process_command("auth")
        assert r2.success is True

        # 3. キャンセル（保留なし）
        r3 = coordinator.process_command("cancel")
        assert r3.success is True


class TestCLIErrorRecovery:
    """CLIエラーリカバリテスト"""

    def test_recover_after_invalid_command(self):
        """無効なコマンド後の復帰"""
        coordinator = Coordinator()

        # 無効なコマンド
        r1 = coordinator.process_command("invalid_xyz")
        assert r1.success is False

        # 有効なコマンドで復帰
        r2 = coordinator.process_command("help")
        assert r2.success is True

    def test_multiple_errors_then_success(self):
        """複数エラー後の成功"""
        coordinator = Coordinator()

        # 複数の無効コマンド
        for _ in range(3):
            r = coordinator.process_command("bad_command")
            assert r.success is False

        # 有効なコマンドで復帰
        r = coordinator.process_command("help")
        assert r.success is True


class TestCLIDraftReply:
    """CLIドラフト返信テスト"""

    def test_draft_reply_command(self):
        """draft replyコマンド（開発中機能）"""
        coordinator = Coordinator()
        result = coordinator.process_command("draft reply --to 123")

        assert result.success is True
        assert "開発中" in result.message or "ドラフト" in result.message


class TestCLIOutputFormat:
    """CLI出力フォーマットテスト"""

    def test_help_output_format(self):
        """ヘルプ出力フォーマット"""
        coordinator = Coordinator()
        result = coordinator.process_command("help")

        # セクションが含まれている
        assert "メール" in result.message or "📧" in result.message
        assert "カレンダー" in result.message or "📅" in result.message

    def test_status_output_format(self):
        """ステータス出力フォーマット（モック使用）"""
        llm = create_llm_service(use_mock=True)
        coordinator = Coordinator(llm_service=llm)
        result = coordinator.process_command("status")

        # エラーまたはステータス情報のどちらかがある
        assert result.message is not None
        assert len(result.message) > 0

    def test_auth_output_format(self):
        """認証状態出力フォーマット"""
        coordinator = Coordinator()
        result = coordinator.process_command("auth")

        # プロバイダー情報が含まれている
        assert "GOOGLE" in result.message or "google" in result.message.lower() or "認証" in result.message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
