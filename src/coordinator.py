"""
Coordinator Module - 中央調整・コマンド処理

各モジュール間の調整とユーザーコマンドの処理を行う
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Callable

from .email_bot import EmailBot, EmailSummary
from .scheduler import Scheduler, MeetingProposal
from .auth import AuthManager, AuthProvider
from .llm import LLMService, create_llm_service

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """アクションの種類"""
    READ_ONLY = "read_only"       # 読み取りのみ
    DRAFT = "draft"              # 下書き作成
    EXTERNAL = "external"         # 外部への影響あり（要確認）


@dataclass
class Action:
    """実行アクション"""
    type: ActionType
    description: str
    execute: Callable
    requires_confirmation: bool = False
    confirmed: bool = False


@dataclass
class CommandResult:
    """コマンド実行結果"""
    success: bool
    message: str
    data: Optional[dict] = None
    pending_actions: Optional[list[Action]] = None


class Coordinator:
    """
    中央調整モジュール

    - ユーザーコマンドの解析
    - 各モジュールへのタスク振り分け
    - 確認フローの管理
    - 監査ログの記録
    """

    def __init__(
        self,
        email_bot: Optional[EmailBot] = None,
        scheduler: Optional[Scheduler] = None,
        auth_manager: Optional[AuthManager] = None,
        llm_service: Optional[LLMService] = None,
        confirmation_required: bool = True,
        audit_log_path: Optional[str] = None
    ):
        """
        初期化

        Args:
            email_bot: EmailBotインスタンス
            scheduler: Schedulerインスタンス
            auth_manager: AuthManagerインスタンス
            llm_service: LLMServiceインスタンス
            confirmation_required: 外部アクション前に確認が必要か
            audit_log_path: 監査ログのパス
        """
        self.auth_manager = auth_manager or AuthManager()
        self.llm_service = llm_service or create_llm_service(use_mock=True)
        self.email_bot = email_bot or EmailBot(llm_service=self.llm_service)
        self.scheduler = scheduler or Scheduler()
        self.confirmation_required = confirmation_required
        self.audit_log_path = audit_log_path
        self._pending_actions: list[Action] = []

        logger.info("Coordinator初期化完了")

    def process_command(self, command: str) -> CommandResult:
        """
        ユーザーコマンドを処理

        Args:
            command: ユーザー入力コマンド

        Returns:
            CommandResult
        """
        command = command.strip().lower()

        # コマンドのルーティング
        if command.startswith("summarize inbox") or command == "inbox":
            return self._handle_summarize_inbox()

        elif command.startswith("schedule"):
            return self._handle_schedule_meeting(command)

        elif command == "status" or command == "today":
            return self._handle_today_status()

        elif command.startswith("draft reply"):
            return self._handle_draft_reply(command)

        elif command == "auth" or command == "auth status":
            return self._handle_auth_status()

        elif command == "help":
            return self._handle_help()

        elif command == "confirm":
            return self._handle_confirm()

        elif command == "cancel":
            return self._handle_cancel()

        else:
            return CommandResult(
                success=False,
                message=f"不明なコマンド: {command}\n'help'で利用可能なコマンドを確認してください"
            )

    def _handle_summarize_inbox(self) -> CommandResult:
        """受信トレイの要約"""
        try:
            summaries = self.email_bot.summarize_inbox(max_emails=10)

            if not summaries:
                return CommandResult(
                    success=True,
                    message="未読メールはありません。"
                )

            # 結果をフォーマット
            lines = ["📧 受信トレイ要約", "=" * 40]

            for i, summary in enumerate(summaries, 1):
                priority_icon = {
                    'high': '🔴',
                    'medium': '🟡',
                    'low': '🟢'
                }.get(summary.priority, '⚪')

                lines.append(f"\n{i}. {priority_icon} {summary.subject[:50]}")
                lines.append(f"   From: {summary.sender}")
                lines.append(f"   {summary.summary}")

                if summary.action_items:
                    lines.append("   📋 アクション:")
                    for item in summary.action_items:
                        lines.append(f"      - {item}")

            self._log_action("summarize_inbox", f"{len(summaries)}件の要約を生成")

            return CommandResult(
                success=True,
                message="\n".join(lines),
                data={"summaries": [s.__dict__ for s in summaries]}
            )

        except Exception as e:
            logger.error(f"受信トレイ要約エラー: {e}")
            return CommandResult(
                success=False,
                message=f"エラーが発生しました: {str(e)}"
            )

    def _handle_schedule_meeting(self, command: str) -> CommandResult:
        """会議スケジュール"""
        # 簡易パース（実際にはより高度なNLPを使用）
        # 例: "schedule team meeting with alice@example.com bob@example.com 30min"

        try:
            # デフォルト値
            title = "Meeting"
            attendees = []
            duration = 30

            # 簡易パース
            parts = command.replace("schedule", "").strip().split()

            # 会議名を抽出
            name_parts = []
            for part in parts:
                if "@" in part:
                    attendees.append(part)
                elif part.endswith("min"):
                    duration = int(part.replace("min", ""))
                elif part not in ["with", "for"]:
                    name_parts.append(part)

            if name_parts:
                title = " ".join(name_parts).title()

            # 会議提案を取得
            proposals = self.scheduler.propose_meeting(
                title=title,
                duration_minutes=duration,
                attendees=attendees,
                max_proposals=5
            )

            if not proposals:
                return CommandResult(
                    success=True,
                    message="指定された条件で空き時間が見つかりませんでした。"
                )

            # 結果をフォーマット
            lines = [f"📅 '{title}' の会議提案", "=" * 40]

            for i, proposal in enumerate(proposals, 1):
                lines.append(f"\n{i}. {proposal.slot}")
                lines.append(f"   スコア: {'⭐' * int(proposal.score * 5)}")

            lines.append("\n選択するには 'confirm 番号' を入力してください")
            lines.append("キャンセルするには 'cancel' を入力してください")

            # 保留アクションとして登録
            self._pending_actions = [
                Action(
                    type=ActionType.EXTERNAL,
                    description=f"会議を作成: {p.slot}",
                    execute=lambda p=p: self.scheduler.create_event(
                        title=p.title,
                        start=p.slot.start,
                        end=p.slot.end,
                        attendees=p.attendees
                    ),
                    requires_confirmation=True
                )
                for p in proposals
            ]

            return CommandResult(
                success=True,
                message="\n".join(lines),
                data={"proposals": [str(p) for p in proposals]},
                pending_actions=self._pending_actions
            )

        except Exception as e:
            logger.error(f"スケジュールエラー: {e}")
            return CommandResult(
                success=False,
                message=f"エラーが発生しました: {str(e)}"
            )

    def _handle_today_status(self) -> CommandResult:
        """今日のステータス"""
        try:
            events = self.scheduler.get_today_schedule()
            schedule_text = self.scheduler.format_schedule(events)

            now = datetime.now()
            lines = [
                f"📊 {now.strftime('%Y年%m月%d日')} のステータス",
                "=" * 40,
                "",
                "📅 今日の予定:",
                schedule_text,
            ]

            self._log_action("today_status", "ステータス確認")

            return CommandResult(
                success=True,
                message="\n".join(lines),
                data={"events": [e.__dict__ for e in events]}
            )

        except Exception as e:
            logger.error(f"ステータス取得エラー: {e}")
            return CommandResult(
                success=False,
                message=f"エラーが発生しました: {str(e)}"
            )

    def _handle_draft_reply(self, command: str) -> CommandResult:
        """返信ドラフト作成"""
        # 実装予定
        return CommandResult(
            success=True,
            message="返信ドラフト機能は開発中です。"
        )

    def _handle_auth_status(self) -> CommandResult:
        """認証状態の確認"""
        lines = ["🔐 認証状態", "=" * 40]

        all_status = self.auth_manager.get_all_auth_status()

        for provider, status in all_status.items():
            icon = "✅" if status.is_authenticated else "❌"
            lines.append(f"\n{icon} {provider.value.upper()}")

            if status.is_authenticated:
                if status.user_email:
                    lines.append(f"   ユーザー: {status.user_email}")
                lines.append(f"   スコープ: {len(status.scopes)}件")
            else:
                lines.append(f"   エラー: {status.error_message}")

        # LLMプロバイダー状態
        lines.append("\n🤖 LLMプロバイダー")
        for p in self.llm_service.get_available_providers():
            lines.append(f"   ✅ {p.value}")

        return CommandResult(
            success=True,
            message="\n".join(lines)
        )

    def _handle_help(self) -> CommandResult:
        """ヘルプ表示"""
        help_text = """
🤖 TaskMasterAI コマンド一覧
============================

📧 メール関連:
  inbox, summarize inbox  - 未読メールを要約
  draft reply --to <id>   - 返信ドラフトを作成

📅 カレンダー関連:
  status, today           - 今日のスケジュール確認
  schedule <title> with <emails> <duration>min
                          - 会議をスケジュール

🔐 認証関連:
  auth, auth status       - 認証状態を確認

⚙️ システム:
  confirm <番号>          - 保留中のアクションを実行
  cancel                  - 保留中のアクションをキャンセル
  help                    - このヘルプを表示

例:
  schedule team sync with alice@example.com 30min
  inbox
  status
  auth
"""
        return CommandResult(success=True, message=help_text)

    def _handle_confirm(self) -> CommandResult:
        """保留アクションの確認・実行"""
        if not self._pending_actions:
            return CommandResult(
                success=False,
                message="確認待ちのアクションはありません。"
            )

        # 最初のアクションを実行（実際にはユーザーが選択）
        action = self._pending_actions[0]
        action.confirmed = True

        try:
            result = action.execute()
            self._pending_actions = []

            self._log_action("confirm", action.description)

            return CommandResult(
                success=True,
                message=f"✅ アクションを実行しました: {action.description}"
            )

        except Exception as e:
            return CommandResult(
                success=False,
                message=f"アクション実行エラー: {str(e)}"
            )

    def _handle_cancel(self) -> CommandResult:
        """保留アクションのキャンセル"""
        count = len(self._pending_actions)
        self._pending_actions = []

        if count == 0:
            return CommandResult(
                success=True,
                message="キャンセルするアクションはありません。"
            )

        self._log_action("cancel", f"{count}件のアクションをキャンセル")

        return CommandResult(
            success=True,
            message=f"🚫 {count}件の保留中アクションをキャンセルしました。"
        )

    def _log_action(self, action_type: str, description: str) -> None:
        """監査ログに記録"""
        import json
        from pathlib import Path

        if not self.audit_log_path:
            return

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action_type": action_type,
            "description": description
        }

        try:
            log_path = Path(self.audit_log_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            # 既存ログの読み込み
            if log_path.exists():
                with open(log_path, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            else:
                logs = []

            logs.append(log_entry)

            # ログの書き込み
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.warning(f"監査ログ記録エラー: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # テスト実行
    print("=== Coordinator テスト ===")

    coord = Coordinator()
    result = coord.process_command("help")
    print(result.message)
